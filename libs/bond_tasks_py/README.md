# bond_tasks_py

Tasks the app owns: a `tasks` table, status, checklist, a stored due instant, three-stage notices with a ledger and
outbox, per-user settings, a link index and an optional calendar mirror. Google Calendar and Microsoft Graph are
mirrors behind a Protocol, never the source of truth. Imports only SQLAlchemy, pydantic and the standard library;
the queue, the calendar and every notice channel arrive through Protocols the app wires.

## What it owns
Host models, every service call's signature and the route list: `docs/migration/bond_tasks_py_host.md`.
The lib ships no migration: write your own revision and assert each `*_COLUMNS` (name -> nullable) in a test.

| Mixin (table) | Columns constant |
|---|---|
| `TasksMixin` (`tasks`) | `TASK_COLUMNS` |
| `TaskUserSettingsMixin` (`task_user_settings`) | `TASK_USER_SETTINGS_COLUMNS` |
| `TaskLinkIndexMixin` (`task_link_index`, server only) | `TASK_LINK_INDEX_COLUMNS` |
| `NoticeLedgerMixin` (`task_notice_ledger`) | `TASK_NOTICE_LEDGER_COLUMNS` |
| `NoticeOutboxMixin` (`task_notice_outbox`) | `TASK_NOTICE_OUTBOX_COLUMNS` |

App columns on `tasks` (a contact id, say) pass through create, update and sync by an allow-list (`host_columns`).
Service functions take a session, flush and never commit. Datetimes are naive UTC; the wire is ISO 8601 with `Z`.

## Seams the app supplies
- `Preferences.for_user(session, user_id) -> UserPrefs`: work day and zone; `StoredPreferences(Settings)` reads the table.
- `Permissions` (`can_edit`, `can_own`, `can_complete`): who may do what; `DefaultPermissions` is owner or assignee.
- `LinkResolver` (`labels`, `search`): current labels and picker search; the lib owns no contact data.
- `AfterWrite` `(session, task)`: runs after the flush in create and update; `make_link_hook(Index)` is one.
- `TransactionalNotifier.write(session, notices)`: the inbox; runs inside the claim, a raise cancels the batch.
- `Notifier.send(session, notice) -> "ok" | "retryable" | "unregistered" | "failed"`: push, chat, email; after commit.
- `Recipients.for_stage(session, task, stage)`: who gets a stage. `default_recipients`: `close` and `due` go to the responsible user (assignee, else owner); `past` goes to that user and the owner (once if the same).
- `Compose` `(task, stage, seq, prefs) -> (title, body)`: wording; the default is `default_compose`.
- `sync_routes(on_deleted=)`: `(ctx, session, task_id, owner_user_id)` after each delete; `after_delete` still gets the mirror pointer.
- `CalendarMirror`, `MirrorProviders`: calendar provider, per-user lookup.

## Create, settings, links
```python
from datetime import UTC, date, datetime
from bond_tasks_py import (SettingsUpdate, StoredPreferences, TaskCreate, TaskFilters, list_tasks,
                           make_link_hook, service, settings_item, update_settings)

now = datetime.now(UTC)
task = service.create(
    session, task_model=Task, owner_user_id=uid, actor_user_id=uid, now=now, tz="UTC",
    data=TaskCreate(title="Call back", due_date=date(2026, 11, 20), due_time="14:30", priority=3,
                    remind_minutes_before=-3, links=[{"kind": "contact", "id": "c1", "label": "Ann"}]),
    writer_zone="America/Chicago", prefs=StoredPreferences(Settings),  # no zone sent: writer_zone, else the actor's stored zone
    extras={"contact_id": "c1"}, host_columns=("contact_id",), after_write=make_link_hook(LinkIndex))

prefs, warnings = update_settings(session, settings_model=Settings, task_model=Task, user_id=uid,
                                  data=SettingsUpdate(end_of_day="18:00"), tz="UTC", now=now)
body = settings_item(prefs, warnings)   # time_zone, start_of_day, end_of_day, lead_minutes, warnings

rows, total = list_tasks(session, task_model=Task, user_id=uid, link_index_model=LinkIndex,
                         filters=TaskFilters(link_kind="contact", link_id="c1"), viewer_zone="America/Chicago", now=now)
```
`update_settings` recomputes `due_at` of the user's open date-only tasks when `end_of_day` or `time_zone` changes.
`retarget_links` (a merge) and `remove_links` (a delete) keep links true. `today(...)` returns four sections
(overdue, today, undated, done today) with counts; TODAY holds every open task that is not overdue and whose day is
the viewer's today or earlier. `summary(..., now=, viewer_zone=)` and list date ranges use the same test.
`update_settings(..., on_recomputed=)` reports tasks whose instant moved; `notice_recipients(task)` is owner plus assignee.
`now` is required in `task_item`, `task_items`, `list_tasks` and `summary` (no date-only fallback). A priority outside 1 to 3 on a sync write is `invalid_priority`.
`list_tasks` and `today` show only tasks the viewer owns or is assigned (`TaskFilters.scope="mine"`, the default);
`scope="all"` lists every task and the app decides who may ask for it. `update_settings` warnings (never blocking):
`lead_longer_than_work_day`, and `time_zone_unknown` when the work day changed and no zone is stored.

## Sync
```python
routes = sync_routes(Task, tz="UTC", prefs=StoredPreferences(Settings), host_columns=("contact_id",),
                     zone_of=lambda ctx, session, user_id: get_settings(session, Settings, user_id).time_zone,
                     link_hook=make_link_hook(LinkIndex), link_index_model=LinkIndex)
```
Handlers for `("tasks", None)` put, patch, delete and for `complete`, `reopen`, `cancel`. Wrap each as the sync lib's
`Route(r.ops, r.handler, r.reads)`; map errors with `verdict_for(exc)` in the host's `reject_for` hook. `zone_of`
supplies the writer's stored zone, because a sync op carries none. A put also accepts `source`; a patch carrying only a `due_at` hint changes nothing. A hard delete
removes the task's link-index rows when `link_index_model` is given. A device's `due_at` is a hint, dropped if unreadable.

## Notices: sweep, deliver, prune
Run from an interval script (every minute). On SQLite call `sqlite_savepoint_setup(engine)` once; `sweep_due` and
`deliver_pending` call `ensure_savepoint_safe(session)` first and raise `RuntimeError` on an unprepared engine.
```python
now = datetime.now(UTC)   # naive or aware both work
sweep_due(session, task_model=Task, ledger_model=Ledger, outbox_model=Outbox, now=now,
          prefs=StoredPreferences(Settings), tz="UTC", transactional=[inbox], channels=["push"])
session.commit()
deliver_pending(session, ledger_model=Ledger, outbox_model=Outbox, task_model=Task,
                notifiers={"push": push}, now=now, commit=session.commit)
prune_ledger(session, task_model=Task, ledger_model=Ledger, outbox_model=Outbox, now=now)   # daily
session.commit()
```
`sweep_due` also fills a missing `due_at` (`repaired`); an idle sweep issues no INSERT. `Recipients` is asked only
for the current stage. A row whose notifier fails even alone writes nothing, is retried by the next sweep and
counts in `SweepResult.errors`. Pass `since=` on first activation so older stage times are recorded as skipped.
`deliver_pending` requires `task_model` (pass `None` for no check) and takes at most `limit` rows, stamps and commits per row, and with `task_model` stamps rows of a
done, cancelled, deleted or postponed task "superseded" (`DeliverResult.superseded`). Rows of a channel with no
notifier stay pending (`unrouted`) and fail after 7 days. `prune_ledger` also removes rows of an old deadline. The claim needs SQLite 3.35 or later (`RETURNING`).

## Rules to know
- One overdue meaning: an open task is overdue when `due_at < now`. Summary, today and the list agree (`is_overdue`).
- `due_at` is server-computed, naive UTC, null only when `due_date` is null. A timed task uses the writer's zone
  (sent, else `writer_zone`, else the actor's stored zone read from `prefs`, else app default); a date-only task uses the responsible user's end of day and zone. A client
  `due_at` is a hint for a timed task only, checked only against a zone sent with the same write (`sent_zone`);
  it never causes a refusal.
- `due_at` is recomputed only when a write changes the date, time or assignee, or the user's end of day or zone
  changes (date-only tasks). A nonexistent local time moves forward; an ambiguous one takes the first occurrence.
- Stages per recipient: close (from `due_at` minus the lead, at most 10080 minutes), due (15 minutes), past (one at
  15 minutes, then each morning at start of day, 5 mornings; the last one says so). `stage_times` omits an
  impossible "past 0"; `past_days` is a window by start time; quiet hours compare at minute precision.
- `remind_minutes_before`: -3 use my default (`lead_minutes`), -2 no close notice, -1 morning of the due date, N minutes.
- Quiet hours are after `end_of_day` until `start_of_day`. Due always goes; the close notice of a timed task goes at
  its time; past notices and the close notice of a date-only task wait for the work day.
- The ledger id `sha256("task|user|stage|seq|token")[:32]` is the notice id, outbox key and push collapse id;
  `fnv1a31` of it is the local notification id. Channels must be idempotent on it (delivery is at least once).
- The queued single reminder is gone; the stages are the only reminder. A new task defaults to -3.
- On plain SQLite with the default driver a SAVEPOINT can commit the outer transaction. Use SQLAlchemy's documented
  `isolation_level=None` on connect plus a `BEGIN` in the engine `begin` event: call `sqlite_savepoint_setup(engine)`
  once per engine, which does exactly that. Postgres is unaffected.

Refusals raise `TaskError(code, message, status)`; `CODES` lists them (`not_task_editor`, `invalid_time_zone`, ...).
The calendar mirror (`sync_mirror`, `remove_event`) is unchanged: see its docstrings and the CHANGELOG.
