/// [TaskRepository] over the synced SQLite store.
library;

import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_tasks/bond_tasks.dart';

import 'extra_names.dart';
import 'task_hooks.dart';
import 'task_queries.dart';
import 'task_row.dart';
import 'task_table_shape.dart';
import 'task_views.dart';
import 'task_write_flow.dart';
import 'tasks_tables.dart';

/// Fills in what the store does not hold (owner and assignee names, say). It runs inside the same
/// read snapshot as the query, gets the decoded tasks in order, and returns them (same length).
typedef TaskEnricher = Future<List<Task>> Function(SyncSql sql, List<Task> tasks);

/// Reads and writes the user's tasks in the local store. Reads are computed on the device with
/// the server's rules; writes are local SQL that the sync upload carries (see `task_writes.dart`
/// for the column values). [refresh] does nothing: the store is kept current by sync.
class PowerSyncTaskRepository implements TaskRepository {
  PowerSyncTaskRepository(
    SyncDb db, {
    required String userId,
    TaskClock clock = const TaskClock(),
    Set<String> extraColumns = const {},
    TaskEnricher? enricher,
    List<String> extraWatchTables = const [],
    MirrorStatusFor? mirrorStatusFor,
    TaskTableShape shape = const TaskTableShape(),
    bool writeCompletedBy = false,
    MirrorStatusOnWrite? mirrorStatusOnWrite,
    TaskPrepare? prepare,
    TaskAfterWrite? afterWrite,
  }) : this._(
          db,
          userId,
          clock,
          Set.unmodifiable(extraColumns),
          enricher,
          List.unmodifiable(extraWatchTables),
          mirrorStatusFor,
          copyShape(shape),
          writeCompletedBy,
          mirrorStatusOnWrite,
          prepare,
          afterWrite,
        );

  // The shape, [extraColumns] and [extraWatchTables] are copied: changing the caller's collections later changes nothing.
  PowerSyncTaskRepository._(
    this.db,
    this.userId,
    this.clock,
    this.extraColumns,
    this.enricher,
    this.extraWatchTables,
    this.mirrorStatusFor,
    this.shape,
    this.writeCompletedBy,
    MirrorStatusOnWrite? mirrorStatusOnWrite,
    TaskPrepare? prepare,
    TaskAfterWrite? afterWrite,
  )   : _sql = TaskSql(shape),
        _writer = TaskWriter(
          userId: userId,
          clock: clock,
          extraColumns: extraColumns,
          shape: shape,
          writeCompletedBy: writeCompletedBy,
          mirrorOnWrite: mirrorStatusOnWrite,
          prepare: prepare,
          afterWrite: afterWrite,
        ) {
    checkExtraColumnNames(extraColumns);
    shape.check(extraColumns);
  }

  final SyncDb db;
  final String userId;
  final TaskClock clock;

  /// The app's own columns (see `tasksTables`): inserts and patches write these keys of the draft's
  /// or patch's `extras` and ignore the others.
  final Set<String> extraColumns;

  /// Runs on every decoded read, inside the read snapshot (and inside the write transaction for a
  /// write's result).
  final TaskEnricher? enricher;

  /// Other tables [enricher] reads: a change in one re-emits [watchOpen].
  final List<String> extraWatchTables;

  /// Lets the app show the right mirror state while a row is offline (the server sets
  /// `mirror_status` and a row that has not synced still says `pending`). Called with each stored
  /// row, synchronously, on every read and on a write's result. Return a `MirrorStatus` wire value
  /// (`pending`, `mirrored`, `skipped`, `failed`) to show it instead of the stored one, or null to
  /// keep the stored one. Null (the default) uses the stored value for every row. The hook only
  /// changes what is read: nothing is written back.
  final MirrorStatusFor? mirrorStatusFor;

  /// How the local `tasks` table differs from the module's (an app whose phone build already shipped a table
  /// of its own). Default: the module's own table, and every SQL string is today's. See [TaskTableShape].
  final TaskTableShape shape;

  /// When true, complete writes `completed_by` = [userId] and reopen and cancel write it as NULL (skipped when
  /// the shape marks the column absent). Default false: the status statement is today's.
  final bool writeCompletedBy;

  final TaskSql _sql;
  final TaskWriter _writer;

  Future<List<Task>> _enrich(SyncSql sql, List<Task> tasks) async {
    final e = enricher;
    if (e == null || tasks.isEmpty) return tasks;
    final out = await e(sql, tasks);
    if (out.length != tasks.length) {
      throw StateError('TaskEnricher returned ${out.length} tasks for ${tasks.length}; it must return the same number, in order');
    }
    return out;
  }

  List<Task> _decode(List<SyncRow> rows, DateTime now) => [for (final r in rows) taskFromRow(r, nowUtc: now, mirrorStatusFor: mirrorStatusFor, shape: shape)];

  Future<List<Task>> _open(SyncSql sql, DateTime now) async => _decode(
        await sql.getAll("SELECT * FROM $kTasksTable WHERE ${_sql.c('status')} = 'open' AND ${_sql.mine} ${_sql.order}", [userId, userId]),
        now,
      );

  @override
  Stream<List<Task>> watchOpen() => watchSnapshot(
        db,
        [kTasksTable, ...extraWatchTables],
        (sql) async => _enrich(sql, await _open(sql, clock.nowUtc())),
      );

  @override
  Future<TaskToday> today() => readSnapshot(db, (sql) async {
        final now = clock.nowUtc();
        final (start, end) = localDayBounds(now);
        // The text bounds are coarse (a date prefix); computeToday does the exact test.
        final done = await sql.getAll(
          "SELECT * FROM $kTasksTable WHERE ${_sql.c('status')} = 'done' AND ${_sql.mine} AND ${_sql.c('completed_at')} >= ? AND ${_sql.c('completed_at')} < ? ${_sql.order}",
          [userId, userId, isoZ(start).substring(0, 10), isoZ(end.add(const Duration(days: 1))).substring(0, 10)],
        );
        final open = await _open(sql, now);
        final doneTasks = _decode(done, now);
        final all = await _enrich(sql, [...open, ...doneTasks]);
        return computeToday(all.sublist(0, open.length), all.sublist(open.length), now);
      });

  @override
  Future<TaskSummary> summary() => readSnapshot(db, (sql) async {
        final now = clock.nowUtc();
        return computeSummary(await _open(sql, now), now);
      });

  @override
  Future<TaskPage> list(TaskFilters f) => readSnapshot(db, (sql) => _list(sql, f));

  /// [list] as a live snapshot: it runs again after every change to the tasks table or [extraWatchTables].
  Stream<TaskPage> watchList(TaskFilters f) => watchSnapshot(db, [kTasksTable, ...extraWatchTables], (sql) => _list(sql, f));

  Future<TaskPage> _list(SyncSql sql, TaskFilters f) async {
    final now = clock.nowUtc();
    final (q, args) = _sql.listQuery(f, userId);
    var tasks = _decode(await sql.getAll(q, args), now);
    if (!f.noDate) tasks = tasksInRange(tasks, f);
    if (f.linkId != null) {
      tasks = [
        for (final t in tasks)
          if (t.links.any((l) => l.id == f.linkId && (f.linkKind == null || l.kind == f.linkKind))) t,
      ];
    }
    final offset = f.offset ?? 0, limit = f.limit ?? 25;
    final page = await _enrich(sql, tasks.skip(offset).take(limit).toList());
    return TaskPage(items: page, total: tasks.length, limit: limit, offset: offset);
  }

  /// One task by id, enriched; null when there is no such row.
  Future<Task?> getTask(String id) => readSnapshot(db, (sql) => _one(sql, id));

  /// [getTask] as a live snapshot over the tasks table and [extraWatchTables].
  Stream<Task?> watchTask(String id) => watchSnapshot(db, [kTasksTable, ...extraWatchTables], (sql) => _one(sql, id));

  Future<Task?> _one(SyncSql sql, String id) async {
    final row = await sql.getOptional('SELECT * FROM $kTasksTable WHERE id = ?', [id]);
    return row == null ? null : _decodeOne(sql, row);
  }

  /// A page of the tasks whose columns equal [equals] (module column names or [extraColumns]; a null value
  /// means `IS NULL`); an empty map matches every row. NOT limited to this user's tasks unless [mine] is true (owner or assignee, in SQL, after the equals conditions and before the status). [status] `open`, `done` or `cancelled` also filters;
  /// any other value (or null) does not. [limit] defaults to 25 and [offset] to 0; `total` counts every match.
  /// Throws [ArgumentError] for an unknown key, a column the shape marks absent or a negative limit or offset ([watchWhere] throws at call time).
  Future<TaskPage> listWhere(Map<String, Object?> equals, {bool mine = false, String? status, int? limit, int? offset}) =>
      readSnapshot(db, (sql) => _where(sql, equals, mine, status, limit, offset));

  /// [listWhere] as a live snapshot over the tasks table and [extraWatchTables].
  Stream<TaskPage> watchWhere(Map<String, Object?> equals, {bool mine = false, String? status, int? limit, int? offset}) {
    _sql.equalsWhere(equals, extraColumns, status, mine: mine, userId: userId); // these throw now, before anything subscribes
    _checkPaging(limit, offset);
    return watchSnapshot(db, [kTasksTable, ...extraWatchTables], (sql) => _where(sql, equals, mine, status, limit, offset));
  }

  void _checkPaging(int? limit, int? offset) {
    if ((limit ?? 0) < 0 || (offset ?? 0) < 0) throw ArgumentError('limit and offset must not be negative');
  }

  Future<TaskPage> _where(SyncSql sql, Map<String, Object?> equals, bool mine, String? status, int? limit, int? offset) async {
    final (where, args) = _sql.equalsWhere(equals, extraColumns, status, mine: mine, userId: userId);
    _checkPaging(limit, offset);
    final lim = limit ?? 25, off = offset ?? 0;
    final w = where.isEmpty ? '' : ' WHERE ${where.join(' AND ')}';
    final rows = await sql.getAll('SELECT * FROM $kTasksTable$w ${_sql.order} LIMIT ? OFFSET ?', [...args, lim, off]);
    final count = await sql.getOptional('SELECT COUNT(*) AS n FROM $kTasksTable$w', args);
    final total = (count?['n'] as num?)?.toInt() ?? 0;
    final items = await _enrich(sql, _decode(rows, clock.nowUtc()));
    return TaskPage(items: items, total: total, limit: lim, offset: off);
  }

  Future<Task> _decodeOne(SyncSql sql, SyncRow row) async {
    final task = taskFromRow(row, nowUtc: clock.nowUtc(), mirrorStatusFor: mirrorStatusFor, shape: shape);
    return (await _enrich(sql, [task])).single;
  }

  Future<Task> _read(SyncSql sql, String id) async => _decodeOne(sql, await _row(sql, id));

  Future<SyncRow> _row(SyncSql sql, String id) async {
    final row = await sql.getOptional('SELECT * FROM $kTasksTable WHERE id = ?', [id]);
    if (row == null) throw StateError('task_not_found: $id');
    return row;
  }

  @override
  Future<Task> create(TaskDraft d) => db.writeTransaction((tx) async => _read(tx, await _writer.create(tx, d)));

  @override
  Future<Task> update(String id, TaskPatch p) => db.writeTransaction((tx) async {
        await _writer.update(tx, id, await _row(tx, id), p);
        return _read(tx, id);
      });

  Future<Task> _status(String id, String action) => db.writeTransaction((tx) async {
        final row = await _row(tx, id);
        final current = await _decodeOne(tx, row);
        final target = switch (action) { 'complete' => TaskStatus.done, 'reopen' => TaskStatus.open, _ => TaskStatus.cancelled };
        if (current.status == target) return current; // already there: no write, no queued patch
        await _writer.status(tx, id, action, row);
        return _read(tx, id);
      });

  @override
  Future<Task> complete(String id) => _status(id, 'complete');

  @override
  Future<Task> reopen(String id) => _status(id, 'reopen');

  @override
  Future<Task> cancel(String id) => _status(id, 'cancel');

  @override
  Future<void> delete(String id) => db.writeTransaction((tx) => _writer.delete(tx, id));

  @override
  Future<void> refresh() async {}

  @override
  void dispose() {}
}
