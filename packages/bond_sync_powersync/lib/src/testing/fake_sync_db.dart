import 'dart:async';

import '../sync_db.dart';
import 'fake_sql.dart' as sql_engine;

/// One statement the adapter ran.
class Stmt {
  const Stmt(this.sql, this.params, {required this.inTx});
  final String sql;
  final List<Object?> params;
  final bool inTx;

  @override
  String toString() => '${inTx ? 'tx ' : ''}$sql $params';
}

/// A scripted [SyncDb]: records every statement, serves canned reads, and
/// holds a queue of CRUD transactions. No sqlite, no service.
///
/// LIMITS of the table mode (`FakeSyncDb.tables`):
/// - `execute` does NOT change [tables]; writes are only recorded in [statements].
/// - WHERE and ORDER BY are IGNORED: every read returns all rows of the named table unless
///   [refineRows] is given.
/// - A non-empty table OVERRIDES an [onGetAll] that returns an empty list.
class FakeSyncDb implements SyncDb {
  FakeSyncDb({this.emitOnListen = false}) : tables = {};

  /// A table-backed fake: `SELECT ... FROM <name>` reads answer from [tables]
  /// (rows are copied), unless [onGetAll] / [onGetOptional] answer first.
  /// [refineRows] narrows the rows for a given SQL (WHERE, ORDER) when a test needs it.
  ///
  /// With [applySql] the fake evaluates the SQL itself (see fake_sql.dart): INSERT / UPDATE / DELETE change
  /// [tables] and pulse [changes]; SELECT honours WHERE, ORDER BY and LIMIT. [columns] (table -> names,
  /// including `id`) makes an unknown column name in a statement throw. [refineRows] still wins when set.
  FakeSyncDb.tables(
    Map<String, List<SyncRow>> tables, {
    this.emitOnListen = false,
    this.applySql = false,
    Map<String, Set<String>> columns = const {},
  })  : tables = {for (final e in tables.entries) e.key: [for (final r in e.value) SyncRow.of(r)]},
        columns = {...columns};

  /// Evaluate SQL against [tables] (off by default: writes are only recorded).
  bool applySql = false;

  /// Known column names per table, checked only when [applySql] is on.
  Map<String, Set<String>> columns = {};

  /// Rows by table name for the table-backed mode (empty otherwise).
  Map<String, List<SyncRow>> tables;

  /// Extends the table mode: receives the SQL, parameters and the table's rows, returns the answer.
  List<SyncRow> Function(String sql, List<Object?> params, List<SyncRow> rows)? refineRows;

  /// When true, each `watch` listener first receives the current read of that SQL.
  bool emitOnListen;

  final List<Stmt> statements = [];
  final List<SyncCrudTransaction> crud = [];
  int transactions = 0;
  int initCalls = 0;
  int disconnects = 0;
  int closes = 0;

  /// Number of `initialize` calls that throw before one succeeds.
  int initFailures = 0;

  /// Answers `getOptional` / `getAll` by SQL (null means no row / no rows).
  SyncRow? Function(String sql, List<Object?> params)? onGetOptional;
  List<SyncRow> Function(String sql, List<Object?> params)? onGetAll;

  /// Throw from `execute` when this returns true for the SQL.
  bool Function(String sql)? failWhen;

  /// The old single controller: its events reach every `watch` listener.
  final StreamController<List<SyncRow>> watchController = StreamController.broadcast();
  final Map<String, StreamController<List<SyncRow>>> _watchers = {};

  /// The controller for one SQL string; events added here reach only listeners of that SQL.
  StreamController<List<SyncRow>> watchControllerFor(String sql) =>
      _watchers.putIfAbsent(sql, StreamController<List<SyncRow>>.broadcast);

  static final RegExp _from = RegExp(r'\bfrom\s+([A-Za-z_][A-Za-z0-9_]*)', caseSensitive: false);

  List<SyncRow> _read(String sql, List<Object?> params) {
    final scripted = onGetAll?.call(sql, params);
    if (scripted != null && (scripted.isNotEmpty || tables.isEmpty)) return scripted;
    final name = _from.firstMatch(sql)?.group(1);
    final rows = name == null ? null : tables[name];
    if (rows == null) return scripted ?? const [];
    final copy = [for (final r in rows) SyncRow.of(r)];
    final refined = refineRows?.call(sql, params, copy);
    if (refined != null) return refined;
    return applySql ? sql_engine.select(sql, params, copy, columns[name]) : copy;
  }

  SyncRow? _readOne(String sql, List<Object?> params) {
    final r = onGetOptional?.call(sql, params);
    if (r != null || tables.isEmpty) return r;
    final rows = _read(sql, params);
    return rows.isEmpty ? null : rows.first;
  }

  Iterable<String> get sqls => statements.map((s) => s.sql);
  List<Stmt> where(String fragment) => [for (final s in statements) if (s.sql.contains(fragment)) s];

  Future<void> _exec(String sql, List<Object?> p, bool inTx) async {
    statements.add(Stmt(sql, p, inTx: inTx));
    if (failWhen?.call(sql) ?? false) throw StateError('scripted failure');
    if (applySql && sql_engine.applyWrite(tables, columns, sql, p)) changes.add(null);
  }

  @override
  Future<void> initialize() async {
    initCalls += 1;
    if (initFailures > 0) {
      initFailures -= 1;
      throw StateError('cannot open');
    }
  }

  @override
  Future<void> execute(String sql, [List<Object?> parameters = const []]) => _exec(sql, parameters, false);

  @override
  Future<List<SyncRow>> getAll(String sql, [List<Object?> parameters = const []]) async {
    statements.add(Stmt(sql, parameters, inTx: false));
    return _read(sql, parameters);
  }

  @override
  Future<SyncRow?> getOptional(String sql, [List<Object?> parameters = const []]) async {
    statements.add(Stmt(sql, parameters, inTx: false));
    return _readOne(sql, parameters);
  }

  @override
  Future<T> writeTransaction<T>(Future<T> Function(SyncSql tx) body) {
    transactions += 1;
    return body(_Tx(this));
  }

  /// Names handed to `onChange`, newest last.
  final List<List<String>> changeSubscriptions = [];
  final StreamController<void> changes = StreamController<void>.broadcast();
  int reads = 0;

  @override
  Future<T> readTransaction<T>(Future<T> Function(SyncSql tx) body) {
    reads += 1;
    return body(_Tx(this));
  }

  @override
  Stream<void> onChange(List<String> tables, {Duration throttle = Duration.zero}) {
    changeSubscriptions.add(tables);
    return changes.stream;
  }

  @override
  Stream<List<SyncRow>> watch(String sql, [List<Object?> parameters = const []]) {
    statements.add(Stmt(sql, parameters, inTx: false));
    final own = watchControllerFor(sql);
    return Stream<List<SyncRow>>.multi((c) {
      if (emitOnListen) c.add(_read(sql, parameters));
      final subs = [watchController.stream.listen(c.add), own.stream.listen(c.add)];
      c.onCancel = () => Future.wait([for (final s in subs) s.cancel()]);
    }, isBroadcast: true);
  }

  @override
  Future<SyncCrudTransaction?> nextCrudTransaction() async => crud.isEmpty ? null : crud.first;

  @override
  Future<void> disconnect() async => disconnects += 1;

  @override
  Future<void> close() async => closes += 1;
}

class _Tx implements SyncSql {
  _Tx(this.db);
  final FakeSyncDb db;

  @override
  Future<void> execute(String sql, [List<Object?> parameters = const []]) => db._exec(sql, parameters, true);

  @override
  Future<List<SyncRow>> getAll(String sql, [List<Object?> parameters = const []]) async {
    db.statements.add(Stmt(sql, parameters, inTx: true));
    return db._read(sql, parameters);
  }

  @override
  Future<SyncRow?> getOptional(String sql, [List<Object?> parameters = const []]) async {
    db.statements.add(Stmt(sql, parameters, inTx: true));
    return db._readOne(sql, parameters);
  }
}

/// A queued CRUD transaction whose `complete` is counted by [completed].
class CrudRig {
  int completed = 0;

  SyncCrudTransaction tx(List<SyncCrudEntry> entries, {int? id = 1}) => SyncCrudTransaction(
        transactionId: id,
        entries: entries,
        complete: () async => completed += 1,
      );
}
