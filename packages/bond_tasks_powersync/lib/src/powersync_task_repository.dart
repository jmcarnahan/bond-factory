/// [TaskRepository] over the synced SQLite store.
library;

import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_tasks/bond_tasks.dart';

import 'task_row.dart';
import 'task_views.dart';
import 'task_writes.dart';
import 'tasks_tables.dart';

const String _mine = '(owner_user_id = ? OR assigned_user_id = ?)';
const String _order = 'ORDER BY due_at IS NULL, due_at, created_at DESC, id';

/// Reads and writes the user's tasks in the local store. Reads are computed on the device with
/// the server's rules; writes are local SQL that the sync upload carries (see `task_writes.dart`
/// for the column values). [refresh] does nothing: the store is kept current by sync.
class PowerSyncTaskRepository implements TaskRepository {
  PowerSyncTaskRepository(this.db, {required this.userId, this.clock = const TaskClock()});

  final SyncDb db;
  final String userId;
  final TaskClock clock;

  List<Task> _decode(List<SyncRow> rows, DateTime now) => [for (final r in rows) taskFromRow(r, nowUtc: now)];

  Future<List<Task>> _open(SyncSql sql, DateTime now) async => _decode(
        await sql.getAll("SELECT * FROM $kTasksTable WHERE status = 'open' AND $_mine $_order", [userId, userId]),
        now,
      );

  @override
  Stream<List<Task>> watchOpen() => watchSnapshot(db, [kTasksTable], (sql) => _open(sql, clock.nowUtc()));

  @override
  Future<TaskToday> today() => readSnapshot(db, (sql) async {
        final now = clock.nowUtc();
        final (start, end) = localDayBounds(now);
        // The text bounds are coarse (a date prefix); computeToday does the exact test.
        final done = await sql.getAll(
          "SELECT * FROM $kTasksTable WHERE status = 'done' AND $_mine AND completed_at >= ? AND completed_at < ? $_order",
          [userId, userId, isoZ(start).substring(0, 10), isoZ(end.add(const Duration(days: 1))).substring(0, 10)],
        );
        return computeToday(await _open(sql, now), _decode(done, now), now);
      });

  @override
  Future<TaskSummary> summary() => readSnapshot(db, (sql) async {
        final now = clock.nowUtc();
        return computeSummary(await _open(sql, now), now);
      });

  @override
  Future<TaskPage> list(TaskFilters f) => readSnapshot(db, (sql) async {
        final now = clock.nowUtc();
        final where = <String>[];
        final args = <Object?>[];
        final status = f.status ?? 'open';
        if (status == 'open' || status == 'done' || status == 'cancelled') {
          where.add('status = ?');
          args.add(status);
        }
        if ((f.scope ?? 'mine') == 'mine') {
          where.add(_mine);
          args.addAll([userId, userId]);
        }
        if (f.ownerUserId != null) {
          where.add('owner_user_id = ?');
          args.add(f.ownerUserId);
        }
        if (f.assignedUserId != null) {
          where.add('assigned_user_id = ?');
          args.add(f.assignedUserId);
        }
        if (f.assignedToMe) {
          where.add('assigned_user_id = ?');
          args.add(userId);
        }
        if (f.noDate) where.add('due_date IS NULL');
        final q = 'SELECT * FROM $kTasksTable${where.isEmpty ? '' : ' WHERE ${where.join(' AND ')}'} $_order';
        var tasks = _decode(await sql.getAll(q, args), now);
        if (!f.noDate) tasks = _inRange(tasks, f);
        if (f.linkId != null) {
          tasks = [
            for (final t in tasks)
              if (t.links.any((l) => l.id == f.linkId && (f.linkKind == null || l.kind == f.linkKind))) t,
          ];
        }
        final offset = f.offset ?? 0, limit = f.limit ?? 25;
        return TaskPage(items: tasks.skip(offset).take(limit).toList(), total: tasks.length, limit: limit, offset: offset);
      });

  List<Task> _inRange(List<Task> tasks, TaskFilters f) {
    final hiParts = [if (f.onOrBefore != null) f.onOrBefore!, if (f.dueTo != null) f.dueTo!]..sort();
    final lo = f.dueFrom, hi = hiParts.isEmpty ? null : hiParts.first;
    if (lo == null && hi == null) return tasks;
    return [
      for (final t in tasks)
        if (_dayIn(dayFor(t, (u) => u.toLocal()), lo, hi, f.includeUndated)) t,
    ];
  }

  bool _dayIn(String? day, String? lo, String? hi, bool includeUndated) {
    if (day == null) return includeUndated;
    return (lo == null || day.compareTo(lo) >= 0) && (hi == null || day.compareTo(hi) <= 0);
  }

  Future<Task> _read(SyncSql sql, String id) async {
    final row = await sql.getOptional('SELECT * FROM $kTasksTable WHERE id = ?', [id]);
    if (row == null) throw StateError('task_not_found: $id');
    return taskFromRow(row, nowUtc: clock.nowUtc());
  }

  @override
  Future<Task> create(TaskDraft d) => db.writeTransaction((tx) async {
        final id = await insertTask(tx, d, userId: userId, nowUtc: clock.nowUtc());
        return _read(tx, id);
      });

  @override
  Future<Task> update(String id, TaskPatch p) => db.writeTransaction((tx) async {
        final row = await tx.getOptional('SELECT * FROM $kTasksTable WHERE id = ?', [id]);
        if (row == null) throw StateError('task_not_found: $id');
        await updateColumns(tx, id, patchColumns(row, p), clock.nowUtc());
        return _read(tx, id);
      });

  Future<Task> _status(String id, String action) => db.writeTransaction((tx) async {
        final current = await _read(tx, id);
        final target = switch (action) { 'complete' => TaskStatus.done, 'reopen' => TaskStatus.open, _ => TaskStatus.cancelled };
        if (current.status == target) return current; // already there: no write, no queued patch
        await setStatus(tx, id, action, clock.nowUtc());
        return _read(tx, id);
      });

  @override
  Future<Task> complete(String id) => _status(id, 'complete');

  @override
  Future<Task> reopen(String id) => _status(id, 'reopen');

  @override
  Future<Task> cancel(String id) => _status(id, 'cancel');

  @override
  Future<void> delete(String id) => db.writeTransaction((tx) => tx.execute('DELETE FROM $kTasksTable WHERE id = ?', [id]));

  @override
  Future<void> refresh() async {}

  @override
  void dispose() {}
}
