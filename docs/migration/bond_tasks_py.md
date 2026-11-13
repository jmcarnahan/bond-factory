# Migrating to bond_tasks_py

Task table, due instant, per-user settings, link index, three-stage notice ledger and sweep, calendar mirror
(`libs/bond_tasks_py`). The wire is `docs/contracts/tasks.md` and `docs/contracts/notices.md`. Wired in
`services/sdk_example` (`tasks_wiring.py`, `routes/task_routers.py`, `routes/jobs.py`). Legend: `docs/migration/README.md`.
Dart side: `bond_tasks.md`. Adoption order: `todo-checklist.md`.

## 1. What it replaces

| App | Goes away | Stays app-side |
|---|---|---|
| S | `TaskRecord` body, `task_service.py` (CRUD, roles, list, summary, `to_item`), `task_outlook_mirror.py`, the `/tasks` router except parse, `handlers_tasks.py` | contact and loan columns, `relink_loan_ids`, parse (LLM), loan-actor rule, admin override |
| A | `PersonalEventRecord`, `personal_events.py` reminder code, the `/me/events` router | the interpret route, the Today day grouping, the reminder job body |

Column renames from S: `mirror_to_outlook` is `mirror_enabled`. `outlook_event_id`, `outlook_event_user_id` are
`external_event_id`, `external_account_user_id` (new `external_provider`, `external_etag`). Contact and loan ids become
`links` `[{kind, id, label}]` (keep your FK columns on your subclass and list them in `host_columns`). Error codes are
lower case (`task_not_found`) in `{"detail": {code, message}}`. A: checklist items (no start) become date-only tasks, timed
entries keep `due_time`, `done_at` becomes `status = done`, `removed_at` has no equivalent (cancel instead).

## 2. What the app adds
Six new tables in the SAME database as `tasks`, and two new columns on it. The lib ships no migration: write one
revision and assert each `*_COLUMNS` constant in a test (`schema_contract` from `bond_service_kit`).

| Mixin | Table |
|---|---|
| `TasksMixin` | `tasks`: new `priority`, `due_at`, index `(status, due_at)` |
| `TaskUserSettingsMixin`, `TaskLinkIndexMixin` | `task_user_settings`, `task_link_index` |
| `NoticeLedgerMixin`, `NoticeOutboxMixin` | `task_notice_ledger`, `task_notice_outbox` |
| `NoticesMixin`, `PushDevicesMixin` (sibling libs) | `notices`, `push_devices` |

Routes: mount `make_tasks_router` and `make_notices_router`; `services/sdk_example/sdk_example/routes/task_routers.py` shows the wiring. `bond_tasks_py_host.md` lists every route, its service call, the
signatures and the models block. Notice and device routes: `bond_notify_py.md`, `bond_push_py.md`. `now` is required in `task_item`, `list_tasks` and `summary` (no `today`). Pass the link index model to `delete`.
Wire `after_write=make_link_hook(LinkIndex)`. `sync_routes(on_deleted=)` is called `(ctx, session, task_id, owner_user_id)`: dismiss notices there.

## 3. The reminder is removed
Old queued reminder: `reminders.py`, the `Scheduler` protocol, `schedule_reminder`, `fire_reminder`, `cancel_reminder`, `compute_remind_at`, `refresh_remind_at`, `dedupe_key`, `JOB_TYPE`, the `scheduler=` parameter of `sync_routes`,
the columns `remind_at` and `reminded_at`, the wire keys of the same names (TaskItem has 24 keys). Drop both columns in
your revision and delete your `task_reminder` job type, its `Scheduler` and its `cancel_reminder` calls. A pending
reminder job does nothing useful after the upgrade: let it drain or delete it.
`remind_minutes_before` stays, with `-3` use my default now the default for new rows. Existing rows keep their value
(`-2` stays "no close notice"). The due and past notices still go out for every open dated task, so pass `since=` on
the first sweep. The sweep reads the value and no job is queued.

## 4. SQLite savepoint setup
On SQLite call `sqlite_savepoint_setup(engine)` once, before the engine's first connection. Without it `sweep_due` and
`deliver_pending` raise `RuntimeError`, because a released savepoint would commit the outer transaction. SQLite 3.35 or
later is needed (`RETURNING`). PostgreSQL needs nothing.

## 5. Running the sweep
From a `bond_jobs` tick, as the `before` hook, throttled with `before_every`:
```python
# imports and models: bond_tasks_py_host.md (its `Notice` Protocol clashes with a model named Notice: import the module); push = PushNotifier(PushDevice, ApnsSender(key_pem, key_id, team_id))
KW = dict(task_model=Task, ledger_model=TaskNoticeLedger, outbox_model=TaskNoticeOutbox)
def sweep(session, now):  # bond_jobs.tick(..., before=sweep, before_every=60); tick commits after the hook
    sweep_due(session, now=now, prefs=StoredPreferences(TaskUserSettings), tz="UTC",
              transactional=[InboxNotifier(Notice)], channels=["push"], **KW)
```

Run `deliver_pending` as a job (it needs a `commit` callable). Or a plain script, every minute:

```python
with Session(engine) as s:   # engine = sqlite_savepoint_setup(create_engine(url)) on SQLite
    sweep(s, now)            # pass since=activation_time on the first run
    s.commit()
    deliver_pending(s, ledger_model=TaskNoticeLedger, outbox_model=TaskNoticeOutbox, task_model=Task,
                    notifiers={"push": push}, now=now, commit=s.commit)
    prune_ledger(s, now=now, **KW)  # daily, then bond_notify_py.prune_notices(s, Notice, now)
    s.commit()
```

Pass `since=` on first activation (old stage times are then skipped). List `"push"` only when a real sender is configured.

## 6. A chat-tool Notifier in 15 lines

A `Notifier` runs after commit and must be idempotent on `notice_id`. Return one of four strings.

```python
class ChatNotifier:
    def __init__(self, post, seen): self.post, self.seen = post, seen  # post(text, key) -> bool
    def send(self, session, notice):
        if notice.notice_id in self.seen: return "ok"
        try: sent = self.post(f"{notice.title}: {notice.body}", notice.notice_id)
        except TimeoutError: return "retryable"
        if not sent: return "failed"
        self.seen.add(notice.notice_id)
        return "ok"
# sweep_due(..., channels=["chat"]); deliver_pending(..., notifiers={"chat": ChatNotifier(post, seen)})
```

### Switching the sweep on over old data
- `since=` only skips stages that start before it. A task already overdue is still claimed on each following morning up to
  `max_past`, so thousands of old tasks would send a notice per task per morning for up to five mornings.
- Pass `grandfather_before=<activation time>` instead: a task whose `due_at` is before it is recorded `skipped` for every
  stage (close, due, all past sequences), so no later pass claims it. A task due at or after it is untouched.
- Rows with a NULL `due_at` are invisible to the sweep. The sweep's built-in backfill fills at most `limit` rows per
  pass (default 500), so a large adopter runs `backfill_due_at(..., limit=..., open_only=True)` in a loop until it returns 0,
  and only then activates with `grandfather_before=`.

### The calendar event and delivery attempts
- `sync_mirror(..., draft_for=hook)`: `hook(session, task, draft)` returns the draft to send, so the app adds a body with
  a link, categories, its own reminder or event length. If it raises, or returns something that is not a `MirrorDraft`, the row ends `failed` before any provider call and the next write sets `pending` again. The hook must not write: a flush is rolled back, a commit would persist. If it fails during a reassignment the old event stays until the next good sync.
- `Notice.attempt` is 1 on the first delivery and one more for each later lease. A notifier for a service with no
  idempotency key checks for a duplicate only when `attempt > 1`. For a channel where a repeat is worse than a loss, pass
  `deliver_pending(..., at_most_once=["chat"])`: `delivered_at` is stamped and committed before the send; if the send then fails or raises, `failed_at` is set too, so a monitor on `failed_at` sees it.

## 6b. Mount the routes instead of copying them

Install with the `http` extra (the lib is not on a package index; the git form is in `docs/sdk/README.md`, "Python"):
Poetry `bond_tasks_py = { git = "https://github.com/jmcarnahan/bond-factory.git", rev = "<sha>", subdirectory = "libs/bond_tasks_py", extras = ["http"] }`,
pip `pip install "bond_tasks_py[http] @ git+https://github.com/jmcarnahan/bond-factory.git@<sha>#subdirectory=libs/bond_tasks_py"`.
Then (module `bond_tasks_py.routes`; the package never imports fastapi):

```python
from bond_service_kit import make_session_factory, session_scope   # or your own equivalent
from bond_tasks_py.routes import make_tasks_router
app.include_router(make_tasks_router(
    task_model=Task, settings_model=TaskUserSettings, link_index_model=TaskLinkIndex,
    session_scope=lambda: session_scope(app.state.session_factory),  # a context manager factory: commit on exit
    user_dep=current_user_id, write_dep=require_capability("tasks.write"), read_all_dep=require_read_all,
    now=clock.utcnow_naive, tz=settings.tz, defaults=default_prefs, prefs=todo_prefs, link_hook=link_hook,
    prepare=owner_edits_closed, names=lambda s, ids: ..., labels=contacts.labels, user_exists=lambda s, uid: ...,
    after_write=lambda s, task, now, before: ..., after_commit=queue_mirror))
```

`session_scope` must return a context manager that commits on exit and rolls back on an error; `bond_service_kit.session_scope(factory)` does, and `make_session_factory(url)` returns `(engine, sessionmaker)` for `app.state.session_factory`.

Include it AFTER the app's own static `/tasks/<name>` routes (such as `/tasks/export`): routes match in registration order, and `/{id}` would swallow them with 404 `task_not_found` if the factory came first. `scope=all` and other people's tasks
are refused with 403 `forbidden` unless `read_all_dep(request)` is given. `error_map(TaskError) -> (status, body)` keeps
a legacy error body; `item_extras(task)` adds keys after the 24 (never replaces one); `extra_where_for(request,
user_id)` narrows the LIST route and its count only (not `/summary`, `/today` or `/{id}`); it is not a visibility rule, use `permissions` and `read_all_dep` for that. `error_map` must return `(status, body)`; anything else raises a `TypeError` naming it. `after_write(session, task, now, before)` runs in the transaction after every
write (`before` = `snapshot(session, task_id)` taken before an update, else None); `after_commit(background, task)`
queues work for after the response; `after_delete` and `after_delete_commit(background, pointer)` do the same for delete.

## 7. Call-site changes and checks

- On done, cancel and delete call `dismiss_for_source`, and when `due_date`, `due_time` or the assignee changes call
  `dismiss_stale` (both are in `bond_notify_py`, not this lib). `apply_notice_action` is the one handler (done or cancel on a closed task does nothing). After a reassign use `notice_recipients(task)` and `bond_notify_py.dismiss_for_source(..., user_ids=)`.
- Notes for adopters: a column you renamed works through a SQLAlchemy `synonym` named in `host_columns`; an app with one org zone passes `tz=` only; "drop `remind_at`" does not apply if you never had it; a custom act route must run the notice owner check first. Details: `bond_tasks_py_host.md`.
- Settings: `update_settings(..., on_recomputed=)` returns `(prefs, warnings)`; in the hook call `bond_notify_py.dismiss_stale`. Pass `time_zone` with client writes.
- Order: revision, backfill, wire the sweep, swap the router. Assert every `*_COLUMNS`, round-trip
  `fixtures/tasks/task.json` through `task_item`, run `make -C libs/bond_tasks_py test`.
- Test: a fake clock sweep over close, due and past with an `InboxNotifier`, and one `sweep_due` twice (second claims 0).
- Known limits: with both a Google and a Microsoft connection the example mirrors to Google only. A multi-process
  SQLite app must retry on a busy error.

## 8. Proved by the legacy host (2026-11-12)

A test-only host (legacy column names, app columns, a legacy wire, an old sync client, a user-edited calendar event) drove the
sync and mirror traits. Fixes, each with a lib test:

- Sync, unreadable hint: an unreadable `due_at` sent with a valid title was rejected `invalid` by the dispatcher's coercion
  although `sync_routes` drops a bad hint. `TaskRoute.optional` lists `due_at`, `priority` and `remind_minutes_before`; pass it on
  (`Route(r.ops, r.handler, r.reads, r.optional)`, needs the sync lib that has `Route.optional`) and a blank or unreadable value
  of those keys is left out. An unreadable non-blank priority is also treated as not sent; a readable one outside 1 to 3 is still
  `invalid_priority`.
- Sync, blank numbers: an old client's `priority: ""` and `remind_minutes_before: ""` are "not sent" (same seam, and `_fields`).
- Sync, closing ops: `complete`, `reopen` and `cancel` read no data (`NO_READS`); one unreadable ignored key no longer rejects them.
- Mirror, partial ownership: `MirrorDraft.leave = frozenset({"location", "categories", "reminder_minutes"})` (set in `draft_for`
  with `dataclasses.replace`) makes an update send the rest only. The first push still sends every field. Left fields are the
  person's after that: the task's own change to them (for example `remind_minutes_before` and the event reminder) is NOT
  propagated; the task's notices still follow the task. Name `start`, `end` and `is_all_day` together or not at all.
- Sync, JSON text: `checklist` and `links` arriving as JSON text (what a phone store writes) are parsed by the lib's handler, so a host does NOT need `client_json` for these two; blank text is not sent, and text that is not a JSON list is `invalid`.
- Mirror, no answer from the provider: `sync_mirror(..., transport_pending=True)` leaves a task `pending` (pointer, etag and
  provider untouched) when the create or update got no HTTP answer: a timeout or connect failure (`classify` returns
  `transport`: error `status` exactly `0`, or a class named `TransportError`, `ConnectError`, `TimeoutException`,
  `ConnectionError` or `TimeoutError`). The next edit of the task retries. Default False: such a failure ends `failed`, as
  before. Use it when an existing app treats "provider unreachable" as not-yet-mirrored. Trade-off: a request that reached the
  provider but whose answer was lost is retried on the next edit and can create a second event, and nothing retries until
  that next edit. A task that was completed, deleted or reassigned while the provider did not answer keeps the state its newer write left. A provider answer (5xx) is still `failed`; a 401 is still `skipped`.
- Old rows: a NULL `remind_minutes_before` (column added by ALTER TABLE) reads as the default in stages, the sweep, the mirror draft and the item, so no backfill is needed (a backfill to -3 is still harmless).

What applies to EVERY adopter without opting in: a NULL `remind_minutes_before` reads as the default (stages, sweep, mirror
draft, and the item now shows -3); a blank `priority` / `remind_minutes_before` from a device is treated as not sent inside the
lib's handler; the `complete`, `reopen` and `cancel` routes read no data. What the host must opt in to: `transport_pending` (see above), `Route.optional` (pass it
on, so an unreadable `due_at` or priority is dropped before the dispatcher rejects it) and `MirrorDraft.leave` (in `draft_for`).

Checked, no lib change (recipes):
- Old-client keys: a renamed flag works in sync when the host widens `reads` with the old key (the dispatcher coerces it by the
  table column) and renames it to `mirror_enabled` in a wrapper. The lib's own key already takes 1/0/"0"/"1" through the schema.
- Blank app columns: `BLANK_IS_NONE` covers the lib's own four fields. A host column keeps `""` unless `prepare` returns `None`
  for it (the legacy host's `prepare` does, and it is also where an owner-only relink is enforced).
- `source` is device-writable on a put (and ignored on a patch); owner, `created_by`, `completed_*`, `mirror_*`, `external_*` and
  `*_at` stamps in a payload are never read.

Recorded limits: the mirror's bookkeeping write (`mirror_status`, the event pointer) touches the row, so the mixin's
`updated_at` `onupdate` stamps the REAL clock on a mirrored row even when the app clock is pinned. The calendar lib's fake keeps
no event reminder, so a reminder is checked by the patch it was (not) sent in. The example passes `r.optional` on, so it has these fixes.

## 9. Settings over sync

`settings_routes(settings_model, task_model, now=, defaults=, tz=, on_recomputed=)` returns one route keyed by the settings
table's name (`(settings_model.__tablename__, None)`, for example `task_user_settings`), put and patch only (no delete). Wrap
it as the sync lib's `Route(r.ops, r.handler, r.reads, r.optional)`, add the table to `Host.tables` and its name to
`single_action`; `settings_verdict_for` is the same mapper as `verdict_for` (a host that already maps `TaskError` needs no
change).
- **Meaning.** Put and patch are the same: a key present with a value sets it, a key present with null resets it to the app
  default (NULL is stored), an absent key is unchanged, and no row yet is created. Unknown keys, and a `user_id` key, are
  ignored. The handler runs `update_settings` inside the op's transaction, so the user's date-only due instants are recomputed
  there (pass `on_recomputed(session, task, old_due_at, now)` to put away stale notices, as the REST route's hook does).
- **Row id.** The op's row id must be the signed-in user's id, else a `forbidden` verdict with the message `not_settings_owner`;
  nothing is written. The payload never names the user.
- **Refusals.** A bad `HH:MM`, zone or lead is an `invalid` verdict whose message is `invalid_start_of_day`,
  `invalid_end_of_day`, `invalid_time_zone` or `invalid_lead_minutes`; equal start and end is `invalid_work_day`. A value of the
  wrong storage type (a number for an `HH:MM` column, text for the lead) is refused by the dispatcher's coercion with the plain
  message `invalid` when the host's column names match the wire keys.
- **What does not travel.** The server's warnings (`lead_longer_than_work_day`, `time_zone_unknown`) are REST-only; a phone
  derives `overridden` from the non-null cells of its own row, and reads the app default itself.
- **Stream rule.** A device syncs its own row only: `WHERE user_id = auth.user_id()` (the renamed column for a legacy table).
- **Row id on the phone.** The phone's row id has to equal the user id. Whether a sync stream may select `user_id AS id` is
  UNVERIFIED on a real sync service. The documented fallback is a real `id` column that always equals `user_id`: a stored or
  generated column in the database, or a column the app fills when it creates the row, and the stream selects `id` as it is.
- **Renamed columns.** The wire keys are the lib's attribute names. A host whose columns are renamed adapts keys before the
  lib's handler, as for tasks (the legacy host's `sync_settings.adapt` widens `reads` with the legacy column names and renames
  them; a lib key wins when both are sent). A legacy row whose time keeps seconds (`08:00:00`) cannot be read by the lib: a
  settings write for that user is refused `invalid` until the adoption migration trims it.
