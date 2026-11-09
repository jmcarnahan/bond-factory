/// The seam between the uploader and a local database.
///
/// Everything the seed connector did through `PowerSyncDatabase` (the next
/// CRUD transaction, completing it, re-keying rows, writing refusal notes,
/// reading rows) is behind [SyncStore], so the core imports no database.
library;

import 'models.dart';
import 'rejections.dart';
import 'verdicts.dart';

/// One queued local transaction: its writes as plain [SyncUploadOp]s.
class SyncBatch {
  const SyncBatch({required this.key, this.transactionId, required this.ops, required this.complete});

  /// Stable across attempts for the same transaction (`tx<id>` or `c<clientId>`).
  final String key;
  final int? transactionId;

  /// `seq` is the position in the transaction, from 0.
  final List<SyncUploadOp> ops;

  /// Removes the transaction from the queue. Call only after every op has a verdict.
  final Future<void> Function() complete;
}

/// What [SyncStore.resend] did.
enum SyncResendResult {
  /// The same write is queued again and the note is gone.
  queued,

  /// A patch whose row is not on the device any more: nothing queued, the note stays.
  rowGone,

  /// The note cannot be turned back into a write; it stays.
  unsupported,
}

abstract interface class SyncStore {
  /// The oldest queued transaction, or null when nothing waits.
  Future<SyncBatch?> nextBatch();

  /// Applies the verdicts of [ops] in ONE local transaction: re-keys rows the
  /// server re-keyed, removes optimistic rows whose create was refused, and
  /// writes the refusal notes (see `planOutcome`).
  Future<void> applyVerdicts(List<SyncUploadOp> ops, Map<int, SyncVerdict> verdicts, DateTime now);

  /// Small key/value bookkeeping (the give-up counters, the clock offset).
  Future<String?> readMeta(String key);
  Future<void> writeMeta(String key, String value);
  Future<void> deleteMeta(String key);

  /// Clears notes older than [kSyncRejectionKeep].
  Future<void> pruneRejections(DateTime now);

  /// The notes, oldest first.
  Future<List<SyncRejection>> rejections();
  Future<void> clearRejection(String id);
  Stream<List<SyncRejection>> watchRejections();

  /// Queues a refused write again: the SAME op, row id and data as the note's
  /// payload records.
  Future<SyncResendResult> resend(SyncRejection note);

  /// The local rows of [table] as mutable maps, for screens and demos.
  Future<List<Map<String, Object?>>> rows(String table);
}
