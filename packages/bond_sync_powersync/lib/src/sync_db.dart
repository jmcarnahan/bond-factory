/// The minimal database surface the adapter uses. [PowerSyncDb] wraps a real
/// `PowerSyncDatabase`; tests fake [SyncDb] and need no service and no sqlite.
library;

import 'package:powersync/powersync.dart';

typedef SyncRow = Map<String, Object?>;

/// SQL access: the database itself, or a transaction's context.
abstract interface class SyncSql {
  Future<void> execute(String sql, [List<Object?> parameters]);
  Future<List<SyncRow>> getAll(String sql, [List<Object?> parameters]);
  Future<SyncRow?> getOptional(String sql, [List<Object?> parameters]);
}

/// One queued change as PowerSync records it.
class SyncCrudEntry {
  const SyncCrudEntry({
    required this.clientId,
    required this.op,
    required this.table,
    required this.id,
    this.opData,
    this.metadata,
  });

  final int clientId;

  /// `put`, `patch` or `delete`.
  final String op;
  final String table;
  final String id;
  final Map<String, Object?>? opData;

  /// The write's `_metadata` JSON (`{"action": ...}`), when the table tracks it.
  final String? metadata;
}

/// The oldest queued transaction.
class SyncCrudTransaction {
  const SyncCrudTransaction({this.transactionId, required this.entries, required this.complete});

  final int? transactionId;
  final List<SyncCrudEntry> entries;
  final Future<void> Function() complete;
}

abstract interface class SyncDb implements SyncSql {
  Future<void> initialize();
  Future<T> writeTransaction<T>(Future<T> Function(SyncSql tx) body);
  Future<T> readTransaction<T>(Future<T> Function(SyncSql tx) body);

  /// A pulse each time one of [tables] (view or raw table names) changes.
  Stream<void> onChange(List<String> tables, {Duration throttle});
  Stream<List<SyncRow>> watch(String sql, [List<Object?> parameters]);
  Future<SyncCrudTransaction?> nextCrudTransaction();
  Future<void> disconnect();
  Future<void> close();
}

/// [SyncDb] over a real `PowerSyncDatabase`.
class PowerSyncDb implements SyncDb {
  PowerSyncDb(this.database);

  final PowerSyncDatabase database;

  static List<SyncRow> _rows(Iterable<Object?> rows) => [
        for (final r in rows) SyncRow.of((r! as Map).cast<String, Object?>()),
      ];

  @override
  Future<void> initialize() => database.initialize();

  @override
  Future<void> execute(String sql, [List<Object?> parameters = const []]) async {
    await database.execute(sql, parameters);
  }

  @override
  Future<List<SyncRow>> getAll(String sql, [List<Object?> parameters = const []]) async =>
      _rows(await database.getAll(sql, parameters));

  @override
  Future<SyncRow?> getOptional(String sql, [List<Object?> parameters = const []]) async {
    final r = await database.getOptional(sql, parameters);
    return r == null ? null : SyncRow.of((r as Map).cast<String, Object?>());
  }

  @override
  Future<T> writeTransaction<T>(Future<T> Function(SyncSql tx) body) =>
      database.writeTransaction((tx) => body(_TxSql(tx)));

  @override
  Future<T> readTransaction<T>(Future<T> Function(SyncSql tx) body) =>
      database.readTransaction((tx) => body(_TxSql(tx)));

  @override
  Stream<void> onChange(List<String> tables, {Duration throttle = const Duration(milliseconds: 30)}) =>
      database.onChange(tables, throttle: throttle).map<void>((_) {});

  @override
  Stream<List<SyncRow>> watch(String sql, [List<Object?> parameters = const []]) =>
      database.watch(sql, parameters: parameters).map(_rows);

  @override
  Future<SyncCrudTransaction?> nextCrudTransaction() async {
    final tx = await database.getNextCrudTransaction();
    if (tx == null) return null;
    return SyncCrudTransaction(
      transactionId: tx.transactionId,
      entries: [
        for (final e in tx.crud)
          SyncCrudEntry(
            clientId: e.clientId,
            op: switch (e.op) {
              UpdateType.put => 'put',
              UpdateType.patch => 'patch',
              UpdateType.delete => 'delete',
            },
            table: e.table,
            id: e.id,
            opData: e.opData?.cast<String, Object?>(),
            metadata: e.metadata,
          ),
      ],
      complete: () => tx.complete(),
    );
  }

  @override
  Future<void> disconnect() => database.disconnect();

  @override
  Future<void> close() => database.close();
}

class _TxSql implements SyncSql {
  _TxSql(this._tx);

  // A `SqliteWriteContext`; typed dynamic so the package needs no sqlite_async import.
  final dynamic _tx;

  @override
  Future<void> execute(String sql, [List<Object?> parameters = const []]) async {
    await _tx.execute(sql, parameters);
  }

  @override
  Future<List<SyncRow>> getAll(String sql, [List<Object?> parameters = const []]) async =>
      PowerSyncDb._rows(await _tx.getAll(sql, parameters) as Iterable<Object?>);

  @override
  Future<SyncRow?> getOptional(String sql, [List<Object?> parameters = const []]) async {
    final r = await _tx.getOptional(sql, parameters);
    return r == null ? null : SyncRow.of((r as Map).cast<String, Object?>());
  }
}
