# Migrating to bond_tasks_powersync

`TaskRepository` over the synced SQLite store (`packages/bond_tasks_powersync`, Flutter: needs `bond_tasks`,
`bond_sync_powersync`, `powersync`). Reads are computed on the device with the server's rules. Writes are local SQL that the
sync upload carries, so the list works offline. Table shapes come from `bond_tasks_py`. Legend: `docs/migration/README.md`.
Order: `todo-checklist.md`. Sync adapter: `bond_sync_powersync.md`.

## 1. What it replaces

An app's own synced task tables and the code that reads them The
controller, the widgets and the alerts coordinator do not change: they take a `TaskRepository`, and this is another one.

## 2. What the app adds

- The table in the schema: `Schema([...tasksTables(), ...syncSupportTables()])`. `tasksTables()` declares every stored column
  as text (`priority`, `remind_minutes_before`, `mirror_enabled` are integers), three indexes and `trackMetadata`. Names
  not stored: `owner_name`, `assignee_name` (null on the `Task`). `overdue` is derived, never stored.
- The stream on the sync service:

```sql
SELECT id, owner_user_id, created_by, assigned_user_id, title, notes, due_date, due_time, priority, due_at,
       status, completed_at, completed_by, checklist, remind_minutes_before,
       mirror_enabled, mirror_status, external_provider, external_event_id, external_account_user_id,
       external_etag, links, source, created_at, updated_at
FROM tasks WHERE owner_user_id = auth.user_id() OR assigned_user_id = auth.user_id()
```

- The upload routes on the server: `sync_routes(Task, ...)` from `bond_tasks_py` handles put, patch, delete and the
  `complete`, `reopen` and `cancel` actions. The sync service needs a `cancel` action route.
- The sign-out order (below).

## 3. Smallest working example

```dart
final repo = PowerSyncTaskRepository(db, userId: userId);   // db is a SyncDb
repo.watchOpen();                 // my open tasks, due soonest first, undated last
await repo.today();               // overdue / today / undated / done today, plus counts
await repo.summary();             // open, overdue, due today, no date
await repo.create(const TaskDraft(title: 'Call back', dueDate: '2026-11-12', dueTime: '15:30'));
await repo.complete(id);
```

`today()` and `summary()` use the device's local day. `list` supports scope, status, owner, assignee, no-date, date range
(by the task's local day) and link filters. Paging is local. `refresh()` does nothing. `taskFromRow(row, nowUtc: now)` decodes
one row. A malformed JSON cell gives an empty list.

## 4. What the device writes

- create: every column, `status` open, `source` (default `manual`), `due_at` the device instant for a timed task and null for
  a date-only task. A date-only task has no `due_at` until the server's answer syncs back, so its `overdue` is date-based
  until then. The id is a client v4 UUID. A supplied id must match `[A-Za-z0-9_-]{1,64}` or `create` throws.
- update: only the patched columns plus `updated_at`. `due_at` is written only for a timed result. Clearing the date also
  nulls `due_time` and `due_at`.
- complete, reopen, cancel: `status`, `completed_at`, `updated_at` and `_metadata` `{"action": ...}` so the upload picks the
  route. Asking for the status a task already has writes nothing. Delete: `DELETE ... WHERE id = ?`.
- The server stays the authority: it replaces `completed_at` and `updated_at` and computes `due_at` of date-only tasks.

## 4a. Own columns, names and extra tables (adoption gaps)
- `tasksTables(extraColumns:, extraIndexes:)` adds the app's columns (and its indexes) to the same table; a name clash, an unsafe name (not `^[a-z_][a-z0-9_]*$`) or an index name that repeats a built-in one throws `ArgumentError`; the repository constructor checks `extraColumns` the same way. A bool extra is stored as 0/1 and reads back as `int`.
- `PowerSyncTaskRepository(extraColumns: {...})` writes only those keys of `extras` on insert and patch, and `taskFromRow` returns the
  rest of the row in `Task.extras`. Add the columns to the sync stream query and the upload route yourself.
- `enricher:` (must return the same number of tasks, else `StateError`) fills owner and assignee names (null from the synced store) inside the read snapshot; `extraWatchTables:` re-emits
  `watchOpen` when one of those tables changes.
- `mirrorStatusFor: (SyncRow row) => ...` returns a mirror state wire value (`pending`, `mirrored`, `skipped`, `failed`) to show for a row, or null to keep the stored one. Use it so an offline row shows the right state (for example `skipped` when the row has mirroring off) before the server sets it. It only changes what is read; nothing is written back. An unknown string shows as `pending`. A hook that throws keeps the stored value for that row and the list still shows. Default null: the stored value shows.
- Opt-in seams for a phone database that already exists (all default to today's behaviour; see "An existing phone database"):
  `shape: TaskTableShape(absent:, rename:, dueOrder:)` (module columns the local table lacks, module column to local column,
  `TaskDueOrder.dueAt` or `dateThenTime`; default: the module's own table); `writeCompletedBy: true` (complete writes
  `completed_by` = the user, reopen and cancel write NULL; default false); `mirrorStatusOnWrite: (after, before) => String?`
  (a non-null result is written to `mirror_status` in the same statement; default null: create writes `pending`, nothing else
  touches it); `prepare: (tx, TaskWrite) async => values` and `afterWrite: (tx, TaskWrite) async {}` (app rules inside the write
  transaction; default null); reads `getTask`, `watchTask`, `listWhere`, `watchWhere` (equality filters on module or extra columns,
  not owner-filtered, `total` in the same snapshot) and `watchList(TaskFilters)`; `taskFromRow(..., shape:)`.
- Guards: a `prepare` for a create must still return every required column (`owner_user_id`, `assigned_user_id`, `title`, `status`,
  `due_date`, `due_time`, `completed_at`, `created_at`, `updated_at`), and a `prepare` for an update may not add or change `status`,
  `completed_at` or `completed_by` (use complete, reopen or cancel); both throw `ArgumentError` and write nothing. SQLite keywords
  (`order`, `group`, `select`, `key`, `values` ...) are rejected as a rename target and, new by default, as an `extraColumns` name. The
  repository copies `shape`, `extraColumns` and `extraWatchTables` at construction. A negative `limit` or `offset` throws.
- Changed by default (a tolerant reader, only how blank input reads): `''` in `assigned_user_id`, `notes`, `due_date` or `due_time`
  now reads as null. A timed row with no `due_at` reads `deviceDueAt(due_date, due_time)` only under a shape with `absent`, `rename`
  or `dateThenTime`.

## 4b. An existing phone database

For an app whose local `tasks` table is its own (proved by `demos/legacy_phone`, which runs every claim below against a real local
database at both stages). At stage one nothing here needs a server change: the upload carries the app's own column names, and
`services/legacy_host` takes the recorded queue (`fixtures/legacy_host/upload_phone_store.json`) unchanged. At stage two the put also carries
`checklist` and `links` as JSON text (as every put of this module does); `bond_tasks_py`'s sync routes parse that text, and
`upload_phone_store_widened.json` replays ok on the legacy host.

**The table at two stages.** Declare your table as you already do (not `tasksTables()`). Stage one is the table as shipped: it lacks
some module columns (`priority`, `due_at`, `checklist`, `remind_minutes_before`, `links`, `external_provider`, `external_event_id`,
`external_account_user_id`, `external_etag`), keeps the calendar flag in its own integer column (`sync_to_calendar`, NULL meaning on)
and has app columns (`client_ref`, `case_ref`, `case_file_no`). Stage two adds the missing columns to the same declaration: PowerSync
schemas are declarative, so opening the same database file with the wider schema keeps every old row (new cells read NULL). Only
change the `shape` between the stages: `absent` shrinks to `{}` and `dueOrder: TaskDueOrder.dateThenTime` is set (it is no longer the default once `due_at` exists, and the old rows have none).

**The repository.** This is the whole adoption (`demos/legacy_phone/lib/src/legacy_store.dart`; `LegacyStage` is the demo's switch
between the two stages):

```dart
PowerSyncTaskRepository legacyTaskRepository(
  SyncDb db, {
  required String userId,
  required LegacyStage stage,
  TaskClock clock = const TaskClock(),
}) =>
    PowerSyncTaskRepository(
      db,
      userId: userId,
      clock: clock,
      // The table: nine columns missing until the app adds them; the flag lives in `sync_to_calendar`.
      shape: TaskTableShape(
        absent: stage == LegacyStage.asShipped ? kMissingColumns.toSet() : const {},
        rename: const {'mirror_enabled': 'sync_to_calendar'},
        dueOrder: stage == LegacyStage.widened ? TaskDueOrder.dateThenTime : null, // old rows have no `due_at`
      ),
      extraColumns: const {'client_ref', 'case_ref', 'case_file_no'},
      extraWatchTables: const ['users', 'clients', 'cases'],
      enricher: _names,
      // A row with no stored state (written before the app had one) shows what a write would give it.
      mirrorStatusFor: (row) => _s(row['mirror_status']) == null ? _mirror(row, null) : null,
      mirrorStatusOnWrite: _mirror,
      writeCompletedBy: true,
      prepare: _rules,
      afterWrite: (tx, w) => tx.execute("DELETE FROM sync_rejections WHERE table_name = 'tasks' AND row_id = ?", [w.id]),
    );

String? _s(Object? v) => v is String && v.trim().isNotEmpty ? v.trim() : null;

/// One rule for reads and writes: a dated, open task with the flag on (NULL is on) waits for the calendar.
String _mirror(SyncRow after, SyncRow? before) {
  final eligible = after['sync_to_calendar'] != 0 && _s(after['due_date']) != null && after['status'] == 'open';
  return eligible || before?['mirror_status'] == 'mirrored' ? 'pending' : 'skipped';
}

/// One query per table over the ids in the page.
Future<List<Task>> _names(SyncSql sql, List<Task> tasks) async {
  Future<Map<String, SyncRow>> byId(String table, String cols, Iterable<String?> ids) async {
    final set = {for (final i in ids) if (_s(i) != null) i!};
    if (set.isEmpty) return {};
    final rows = await sql.getAll('SELECT id, $cols FROM $table WHERE id IN (${List.filled(set.length, '?').join(', ')})', [...set]);
    return {for (final r in rows) r['id']! as String: r};
  }

  final users = await byId('users', 'name, email', [for (final t in tasks) ...[t.ownerUserId, t.assignedUserId]]);
  final clients = await byId('clients', 'first_name, last_name', [for (final t in tasks) t.extras['client_ref'] as String?]);
  final cases = await byId('cases', 'label', [for (final t in tasks) t.extras['case_ref'] as String?]);
  String? user(String? id) => users[id] == null ? null : _s(users[id]!['name']) ?? _s(users[id]!['email']);
  String? client(String? id) {
    final r = clients[id];
    final name = r == null ? '' : '${_s(r['first_name']) ?? ''} ${_s(r['last_name']) ?? ''}'.trim();
    return name.isEmpty ? null : name;
  }

  return [
    for (final t in tasks)
      t.copyWith(
        ownerName: user(t.ownerUserId),
        assigneeName: user(t.assignedUserId),
        extras: {
          ...t.extras,
          'client_name': client(t.extras['client_ref'] as String?),
          'case_label': cases[t.extras['case_ref']]?['label'],
        },
      ),
  ];
}

/// The app's rules, inside the write transaction: blank links are NULL, a case implies its client (and a case of
/// another client is refused), and `case_file_no` follows the case.
Future<Map<String, Object?>> _rules(SyncSql tx, TaskWrite w) async {
  final v = {...w.values};
  for (final k in const ['client_ref', 'case_ref']) {
    if (v.containsKey(k)) v[k] = _s(v[k]);
  }
  if (!v.containsKey('case_ref')) return v;
  final c = v['case_ref'] == null ? null : await tx.getOptional('SELECT client_id, file_no FROM cases WHERE id = ?', [v['case_ref']]);
  final client = v.containsKey('client_ref') ? v['client_ref'] : _s(w.before?['client_ref']);
  if (c != null && client != null && c['client_id'] != client) throw StateError('case_belongs_to_another_client');
  if (c != null && client == null) v['client_ref'] = c['client_id'];
  if (!v.containsKey('case_file_no')) v['case_file_no'] = c?['file_no'];
  return v;
}
```

**What each piece does.**
- `shape.absent`: SQL never names these columns. A draft or patch value for one is dropped silently (no error), a read gives null,
  and the upload queue carries only columns the table has. A patch that names only absent columns writes and queues nothing.
  `listWhere` with an absent column throws `ArgumentError`.
- `shape.rename`: the module's `mirror_enabled` is read from and written to `sync_to_calendar` (bool as 1 or 0, NULL reads as on). A
  renamed column never lands in `Task.extras` and never appears as `mirror_enabled` in the queue.
- `extraColumns` are the app's own columns. The enricher runs inside the read snapshot: one query per table over the ids of the page.
  Treat `''` in a link column as no link (an old build wrote it). `extraWatchTables` re-emits every watch (`watchOpen`, `watchTask`,
  `watchWhere`, `watchList`) when `users`, `clients` or `cases` change; without it the names go stale on screen.
- `mirrorStatusFor` shapes what is read; here only a row the old build left without a state shows what a write would give it.
  `mirrorStatusOnWrite` shapes what is stored: eligible (flag on, dated, open) is `pending`, a task that was `mirrored` is `pending`
  too (the event must go), anything else `skipped`. `before` is null on create. Both run on the row in local column names.
- `prepare` and `afterWrite` run inside the one write transaction, so a throw leaves no row and no queue entry (the `afterWrite` here
  clears an earlier refusal note of the task). `prepare` may read any table through `tx` and may add only declared columns.
  Status actions (`complete`, `reopen`, `cancel`) do not run `prepare`.

**Order.** `dateThenTime` is `ORDER BY due_date IS NULL, due_date, due_time IS NULL, due_time, created_at DESC, id`: date, then time
(a date-only task after the timed ones of its day), undated last, newest created first. It is the default only while `due_at` is
absent. After stage two the old rows still have no `due_at`, so name `dueOrder: TaskDueOrder.dateThenTime` yourself or the old rows
all tie and the newest created comes first (pinned in `read_test.dart`). A timed old row with no `due_at` reads `deviceDueAt(date,
time)`, so overdue, `today()`, `summary()` and the local alerts all work on it.

**Limits found.**
- The default read of a link column keeps `''` as it is stored; the enricher above is where it becomes "no link".
- `mirrorStatusFor` is not asked for a stored `mirrored` or `failed` row in this recipe: a server-owned state is shown as stored.
- The case-implies-client rule runs when the write names `case_ref`, not on a title edit or a status change, so an old row with a case
  and a blank client keeps it until the case is written again.
- The put of a create carries every non-null column the table has, including the server-owned ones (`created_by`, `created_at`,
  `mirror_status`, `source`). A server that ignores them (the legacy host does) is fine; one that rejects unknown or owned keys
  needs its own upload filter.
- The server ignores the phone's `mirror_status`, `completed_by` and app-derived columns it does not know (`case_file_no`) and owns `created_at`; on the device they are an optimistic local display until the next download overwrites them.
- A real database inside a widget test needs `tester.runAsync` alternating with `pump` (a plain `await` never resumes under FakeAsync).

## 5. Sign-out

Local writes upload later. Wait for the queue before clearing: `waitForUploadDrain(db)`, then disconnect, then clear the
database. Clearing first loses queued writes. With push: unregister the device, wait for the drain, disconnect, clear.

## 6. What to test

- `make -C packages/bond_tasks_powersync test` (it sets TZ=America/Los_Angeles, and the day-view tests on the shared fixtures
  skip with a message in another zone).
- Use `FakeSyncDb.tables(..., applySql: true, columns: ...)` from `bond_sync_powersync/testing.dart`: a wrong column or WHERE
  fails the test.
- Complete a task offline, then drain: the upload names the `complete` route.
- Not proven here: a real PowerSync service, and how fast a change reaches an open app.
