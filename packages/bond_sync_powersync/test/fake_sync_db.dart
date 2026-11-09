import 'dart:async';

import 'package:bond_sync_powersync/bond_sync_powersync.dart';

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
class FakeSyncDb implements SyncDb {
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

  final StreamController<List<SyncRow>> watchController = StreamController.broadcast();

  Iterable<String> get sqls => statements.map((s) => s.sql);
  List<Stmt> where(String fragment) => [for (final s in statements) if (s.sql.contains(fragment)) s];

  Future<void> _exec(String sql, List<Object?> p, bool inTx) async {
    statements.add(Stmt(sql, p, inTx: inTx));
    if (failWhen?.call(sql) ?? false) throw StateError('scripted failure');
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
    return onGetAll?.call(sql, parameters) ?? const [];
  }

  @override
  Future<SyncRow?> getOptional(String sql, [List<Object?> parameters = const []]) async {
    statements.add(Stmt(sql, parameters, inTx: false));
    return onGetOptional?.call(sql, parameters);
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
    return watchController.stream;
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
    return db.onGetAll?.call(sql, parameters) ?? const [];
  }

  @override
  Future<SyncRow?> getOptional(String sql, [List<Object?> parameters = const []]) async {
    db.statements.add(Stmt(sql, parameters, inTx: true));
    return db.onGetOptional?.call(sql, parameters);
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
