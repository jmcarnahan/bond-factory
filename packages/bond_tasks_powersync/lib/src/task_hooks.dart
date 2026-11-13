/// The hooks an app can run inside a task write.
library;

import 'package:bond_sync_powersync/bond_sync_powersync.dart';

/// Which write a [TaskWrite] describes.
enum TaskWriteKind { create, update, complete, reopen, cancel, delete }

/// One write as the hooks see it. Column names are the LOCAL table's.
class TaskWrite {
  const TaskWrite({required this.kind, required this.id, this.before, this.values = const {}});

  final TaskWriteKind kind;
  final String id;

  /// The stored row before the write; null on create and on a delete of a missing row.
  final SyncRow? before;

  /// Local column name to the value the statement writes (never `id` or `_metadata`). `updated_at` is
  /// included once it is decided: on create from the start, on update after `prepare` has run. Empty for delete.
  final Map<String, Object?> values;
}

/// Runs inside the write transaction of a create or an update, before the statement. Returns the values to
/// write (it may change values and add keys; an added key must be one of `extraColumns`, already in
/// `write.values`, or a declared local column other than `id`, else [ArgumentError] and nothing is written). It may
/// read any table through [tx]. For an update it is called even when the patch produced no column; an empty
/// result writes nothing. A create must still return every column the table needs (`owner_user_id`, `assigned_user_id`, `title`,
/// `status`, `due_date`, `due_time`, `completed_at`, `created_at`, `updated_at`), so `{}` cannot insert a bare row; an update may not
/// add or change `status`, `completed_at` or `completed_by` (use complete, reopen or cancel); both throw [ArgumentError].
typedef TaskPrepare = Future<Map<String, Object?>> Function(SyncSql tx, TaskWrite write);

/// Runs inside the write transaction after the statement ran (any kind). Not called when a status action is
/// already satisfied or an update writes nothing.
typedef TaskAfterWrite = Future<void> Function(SyncSql tx, TaskWrite write);

/// Gives the `mirror_status` to store with a write. [after] is the row as it will be stored ([before] merged
/// with the written values, local names, `id` included); a non-null result is written to `mirror_status` in
/// the same statement; null keeps today's behaviour (create writes `pending`, the others do not touch it).
/// A throw fails the write and rolls the transaction back.
typedef MirrorStatusOnWrite = String? Function(SyncRow after, SyncRow? before);
