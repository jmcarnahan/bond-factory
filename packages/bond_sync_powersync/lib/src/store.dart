/// [SyncStore] over PowerSync.
library;

import 'package:bond_sync/bond_sync.dart';
import 'package:powersync/powersync.dart';

import 'crud_ops.dart';
import 'policy.dart';
import 'store_apply.dart';
import 'store_resend.dart';
import 'sync_db.dart';

class PowerSyncSyncStore implements SyncStore {
  PowerSyncSyncStore(PowerSyncDatabase db, {required SyncPolicy policy}) : this.withDb(PowerSyncDb(db), policy: policy);

  /// Over any [SyncDb] (a fake in tests).
  PowerSyncSyncStore.withDb(this.db, {required this.policy});

  final SyncDb db;
  final SyncPolicy policy;

  @override
  Future<SyncBatch?> nextBatch() async {
    final tx = await db.nextCrudTransaction();
    if (tx == null || tx.entries.isEmpty) return null;
    return SyncBatch(
      key: batchKey(tx),
      transactionId: tx.transactionId,
      ops: [for (var i = 0; i < tx.entries.length; i++) opFor(i, tx.entries[i])],
      complete: tx.complete,
    );
  }

  @override
  Future<void> applyVerdicts(List<SyncUploadOp> ops, Map<int, SyncVerdict> verdicts, DateTime now) =>
      applyOutcome(db, policy, ops, verdicts, now);

  @override
  Future<String?> readMeta(String key) async {
    final row = await db.getOptional('SELECT value FROM sync_meta WHERE key = ?', [key]);
    return row?['value'] as String?;
  }

  @override
  Future<void> writeMeta(String key, String value) =>
      db.execute('INSERT OR REPLACE INTO sync_meta (id, key, value) VALUES (?, ?, ?)', [key, key, value]);

  @override
  Future<void> deleteMeta(String key) => db.execute('DELETE FROM sync_meta WHERE key = ?', [key]);

  @override
  Future<void> pruneRejections(DateTime now) => db.execute(
        'DELETE FROM sync_rejections WHERE created_at < ?',
        [now.toUtc().subtract(kSyncRejectionKeep).toIso8601String()],
      );

  static const String _listNotes = 'SELECT * FROM sync_rejections ORDER BY created_at, id';

  @override
  Future<List<SyncRejection>> rejections() async => [
        for (final r in await db.getAll(_listNotes)) SyncRejection.fromRow(r),
      ];

  @override
  Future<void> clearRejection(String id) => db.execute('DELETE FROM sync_rejections WHERE id = ?', [id]);

  @override
  Stream<List<SyncRejection>> watchRejections() =>
      db.watch(_listNotes).map((rows) => [for (final r in rows) SyncRejection.fromRow(r)]);

  @override
  Future<SyncResendResult> resend(SyncRejection note) => resendNote(db, policy, note);

  @override
  Future<List<Map<String, Object?>>> rows(String table) {
    final known = policy.schema.tables.any((t) => t.name == table);
    if (!known || !sqlName.hasMatch(table)) throw ArgumentError.value(table, 'table', 'not in the schema');
    return db.getAll('SELECT * FROM $table');
  }
}
