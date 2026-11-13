# Hosting bond_tasks_py: models, routes and service calls

The code an app writes around `libs/bond_tasks_py`. The reference host is `services/sdk_example/sdk_example/`, mainly
`routes/task_routers.py` (mounts `make_tasks_router` for CRUD, lifecycle, day view and settings, and `make_notices_router`
for the inbox), `routes/push.py` and `task_support.py`. The note for the library is `bond_tasks_py.md`, the wire is `docs/contracts/tasks.md`.

## 1. The models

The libs ship mixins and no migrations. All seven classes live in ONE database. The names below are the reference host's.

```python
from datetime import UTC, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session
import bond_tasks_py as tasks      # the module: it exports a `Notice` Protocol, so do not import that name next to a model `Notice`
from bond_tasks_py import (NoticeLedgerMixin, NoticeOutboxMixin, StoredPreferences, TaskCreate, TaskFilters,
                           TaskLinkIndexMixin, TasksMixin, TaskUserSettingsMixin, make_link_hook, sqlite_savepoint_setup)
from bond_notify_py import InboxNotifier, NoticesMixin, dismiss_for_source, dismiss_stale
from bond_push_py import PushDevicesMixin

class Base(DeclarativeBase): pass
class Task(TasksMixin, Base): pass
class TaskUserSettings(TaskUserSettingsMixin, Base): pass
class TaskLinkIndex(TaskLinkIndexMixin, Base): pass
class TaskNoticeLedger(NoticeLedgerMixin, Base): pass
class TaskNoticeOutbox(NoticeOutboxMixin, Base): pass
class Notice(NoticesMixin, Base): pass          # bond_notify_py
class PushDevice(PushDevicesMixin, Base): pass  # bond_push_py
```

In a test, `create_engine("sqlite://")` (in memory) works once you call `sqlite_savepoint_setup(engine)`, but an in-memory
database is per connection and thread: single-threaded use only. With a threaded server or a `TestClient` use a file URL or `StaticPool`,
or `make_session_factory("sqlite://")` from `bond_service_kit`, which shares one connection for an in-memory URL.

When you mount the routes (`bond_tasks_py.md` section 6b), `session_scope=lambda: session_scope(app.state.session_factory)` needs
`from bond_service_kit import make_session_factory, session_scope` (or your own equivalent). The callable must return a context
manager that commits on exit and rolls back on an error.

## 2. Service calls

All take a session first, flush and never commit. `now` is a datetime (naive UTC or aware). Import from `bond_tasks_py` (or `service`).

| Call | Signature |
|---|---|
| `create` | `create(session, *, task_model, owner_user_id, actor_user_id, data: TaskCreate, now, tz="UTC", user_exists=None, writer_zone=None, prefs=None, extras=None, host_columns=(), after_write=None)` |
| `update` | `update(session, *, task, actor_user_id, data: TaskUpdate, now, tz="UTC", user_exists=None, writer_zone=None, prefs=None, permissions=None, extras=None, host_columns=(), after_write=None)` |
| `complete`, `reopen`, `cancel` | `complete(session, task, actor_user_id, now, *, permissions=None)` |
| `delete` | `delete(session, task, actor_user_id, *, permissions=None, link_index_model=None)` returns a `MirrorPointer` or None |
| `get` | `get(session, task_model, task_id)` raises `task_not_found` |
| `set_checklist_item` | `set_checklist_item(task, item_id, done, now, *, actor_user_id=None, permissions=None)` (no session) |
| `apply_notice_action` | `apply_notice_action(session, *, task, action, actor_user_id, now, permissions=None)`: `"done"`, `"cancel"`, `"snooze"` (no change) |
| `list_tasks` | `list_tasks(session, *, task_model, user_id, filters=None, limit=25, offset=0, link_index_model=None, viewer_zone=None, now, extra_where=())` returns `(rows, total)`. `extra_where` is a sequence of SQLAlchemy criteria on your own columns (a single clause raises `TypeError`), applied before the count and the paging. `TaskFilters.status` is `open`, `done`, `cancelled`, `active` (open and done) or `all` (an unknown value acts like `all`). If older clients cannot show a cancelled task, filter cancelled rows out of your sync stream. |
| `summary` | `summary(session, *, task_model, user_id, now, viewer_zone)` |
| `today` | `today(session, *, task_model, user_id, now, viewer_zone)` |
| `task_item` | `task_item(task, *, today, now, names=None, labels=None)` (`today` is `viewer_today(now, zone)`); `task_items(tasks, *, today, now, names=None, labels=None)` for a list, `names` being a callable from user ids to a name map. `labels` is a Mapping `{(kind, id): label}` for `task_item` and a callable for `task_items`; the callable gets every link of the page once (`[{kind, id, label}]`) and returns `{(kind, id): label}`; a returned label replaces the stored one, so a renamed contact shows its new name |
| settings | `get_settings(session, settings_model, user_id, defaults=None)`, `update_settings(session, *, settings_model, task_model, user_id, data, tz, now, on_recomputed=None, defaults=None)`, `settings_overridden(row)`, `settings_item(prefs, warnings=(), overridden=None)` |

What three arguments of `create` and `update` mean:
- `prefs`: a `Preferences` such as `StoredPreferences(TaskUserSettings)`. It supplies each user's zone and work day. With `None` everyone has the defaults.
- `writer_zone`: the zone to use for this write when the request sent none. A zone sent with the write wins over it. If `writer_zone` is
  None and `prefs` is given, the actor's stored zone is read from `prefs`. Then the app default `tz`. A timed task uses the actor's zone, not the assignee's. A date-only task uses it only when the actor is the
  responsible user (that user's own stored zone wins). The device `due_at` hint is checked only against a zone SENT with the write.
- `user_exists`: a callable `(user_id) -> bool` checked for `assigned_user_id`. With `None` the check is skipped and any assignee id is accepted
  (`unknown_assignee` is never raised).

More arguments of `create` and `update` (and `sync_routes`):
- `prepare(session, task_or_None, actor_user_id, extras) -> dict`: runs after the permission check and before the app columns are stored. On update it sees the stored task before any field changes. It runs on create, update and sync put/patch only, not on complete, reopen, cancel, delete or a status-only patch, and it sees the extras (filtered to `host_columns`), not the other new values. The dict it returns is trusted server code: every key is stored if it is a column of your task model that the lib does not own, so it may add derived columns outside `host_columns`; a lib column or unknown name raises `ValueError` and a non-Mapping raises `TypeError`. It may raise `TaskError` and then nothing is written: `from bond_tasks_py import TaskError`, then `raise TaskError("relink_needs_owner", "Only the owner can change this.", 403)`. The route answers that status with `{"detail": {"code", "message"}}`. Use it for rules such as "relinking needs owner rights". `sync_routes(prepare=)` runs it on put and patch too.
- `sync_routes(fields=)`: a list of the device-writable names (a subset of `FIELDS`); other fields from a device are dropped. It narrows the `FIELDS` columns only: status changes, cancel, delete and `host_columns` extras are not narrowed.
- A `Permissions` object that needs a session can get it with `sqlalchemy.orm.object_session(task)`.
- A renamed column works through a SQLAlchemy `synonym` named in `host_columns`. Streams stay the app's file.
- An app with one org zone passes `tz=` and nothing else: no `prefs`, no `writer_zone`, no `zone_of`.
- The act route must check that the notice belongs to the user (`bond_notify_py` ownership check) before it calls `apply_notice_action`, which never sees the notice.

Work-day defaults: build ONE `StoredPreferences(TaskUserSettings, defaults)` and pass it everywhere preferences are read (`create`, `update` and `sync_routes` `prefs=`, `sweep_due`, `backfill_due_at`, `recompute_day_due`; with `prefs=None` those use the lib constants), and `defaults=` to `get_settings` and `update_settings`. Leave `defaults.time_zone` as None: `tz=` is the app zone for a user with none stored, and a zone in `defaults` would be reported as the user's zone and hide the `time_zone_unknown` warning. Rows written before this change hold explicit values and read as overridden: a migration may set to NULL the values equal to the old constants (08:00, 17:00, 60). A reset can be refused with `invalid_work_day` when the default equals the other stored bound: reset both together. A user with no row, and any field a user has not set, takes it. The three time columns are nullable (NULL = not set). A settings answer is `settings_item(prefs, warnings, settings_overridden(session.get(Settings, user_id)))`, which adds `"overridden": [names]` (in the order time_zone, start_of_day, end_of_day, lead_minutes). A `PUT` with a field set to null resets it. Your revision must drop NOT NULL on the three columns.

## 3. Routes and the call behind each

Register the static paths (`/tasks/today`, `/tasks/settings`, `/tasks/parse`, `/tasks/links/search`, `/tasks/summary`) BEFORE `/tasks/{id}`,
or the id route swallows them. The viewer zone is, in order: the `time_zone` query value, the person's stored zone, the app default
(`effective_zone`). `GET /tasks/today` uses `today(...)` and `task_item(..., today=viewer_today(now, zone))`. In `task_item(names=)` the names
are a dict (user id to name), in `task_items(names=)` a callable that takes the list of ids. A `PUT` handler takes the parsed body as a
`TaskUpdate` model (not a dict with defaults filled in), so an omitted field is unchanged and an explicit null clears it.

| Route | Calls |
|---|---|
| `GET /tasks` | `list_tasks` then `task_items` (`scope=all` is the app's gate) |
| `GET /tasks/summary` | `summary` |
| `GET /tasks/today` | `today` then `task_item` per row |
| `GET /tasks/{id}` | `get` then `task_item` |
| `POST /tasks` (201) | `create` with `after_write=make_link_hook(TaskLinkIndex)` |
| `PUT /tasks/{id}` | `notice_recipients(task)` before, `update`, then the after-write hook; after a reassign `dismiss_for_source(..., user_ids=)` for users who left |
| `POST /tasks/{id}/complete`, `/reopen`, `/cancel` | `get` then `complete`, `reopen` or `cancel`, then the after-write hook |
| `DELETE /tasks/{id}` | `delete` with `link_index_model=`, then `dismiss_for_source` |
| `PUT /tasks/{id}/checklist/{item_id}` | `get` then `set_checklist_item` |
| `GET`, `PUT /tasks/settings` | `get_settings`, `update_settings` (with `on_recomputed` calling `dismiss_stale`), then `settings_item` |
| `POST /notices/{id}/act` | `session.get(Notice, id)` (404 `notice_not_found`), check `notice.user_id` (403 `not_notice_owner`), `get` the task, `apply_notice_action`, `mark_read`, `dismiss_for_source` on done or cancel |

Run the sweep every minute, and never less often than every 15 minutes: the `due` stage lasts 15 minutes and a later sweep claims `past` instead.

`dismiss_for_source(session, Notice, task_id, now, *, user_ids=None)` and `dismiss_stale(session, Notice, task_id, due_at, now)`
live in `bond_notify_py`, not `bond_tasks_py`. The reference host's after-write hook (`todo_wiring.after_task_write`) runs after every task write, REST or sync: for a closed
task it calls `dismiss_for_source`, for an open task `dismiss_stale` with the current `due_at`. Task write and notice clean-up share one transaction.

## 4. Who gets which notice

`default_recipients(task, stage)` in `bond_tasks_py`. The responsible user is the assignee, else the owner.

| Stage | Recipients |
|---|---|
| `close` | the responsible user |
| `due` | the responsible user |
| `past` | the responsible user and the owner (once if they are the same person) |

Pass `recipients=` to `sweep_due` for another rule (`Recipients.for_stage(session, task, stage)`).

## 5. Proved by the legacy host

`services/legacy_host` is a test-only host that differs from `sdk_example` the way an app that already exists does; one
test file per trait (table in its README). Everything below worked without a change to the lib unless a limit says so.

Works unchanged:
- **Renamed columns**: override the mixin attribute (`mirror_enabled = Column("sync_to_calendar", Boolean, ...)`,
  `external_event_id`, `external_account_user_id`; the same for `TaskUserSettingsMixin` and `GrantsMixin`). Service
  calls, serialisation, queries and the mirror use the attribute; SQL goes to the old column.
- **App columns**: `host_columns=("client_ref", "case_ref")` plus a `prepare(session, task, actor, extras)` rule. The
  rule gets only the allow-listed extras, may raise `TaskError` (nothing is written, including the other fields of the
  same request), and returns the extras to store; blank to NULL, "changing needs the owner or an admin" (a resent
  unchanged value is not a change) and "a case implies its client" all fit there.
- **Own routes over `service.*`** instead of `make_tasks_router`: a different wire (extra keys, naive timestamps with
  microseconds, an error body with `error_code`), request bodies in two vocabularies, and a `Permissions` object that
  also lets an admin edit. `task_items(...)` gives bond's dict; the host adds keys and rewrites the instants.
- **Write extras**: build them from the app's own fields, not from `Task.extras` wholesale; a host that accepts both vocabularies lets bond's key win and never writes response-only keys (`calendar_event_id`, `client_name`, `case_label`).
- **A NULL `remind_minutes_before`** (applies to every adopter, no opt-in; opt-in changes are `Route.optional` and `MirrorDraft.leave`, see `bond_tasks_py.md` section 8) (the column was added after the rows existed) reads as `USE_DEFAULT_REMINDER` in the stages, the sweep, the mirror draft and the item: no backfill needed (`test_an_old_row_with_a_null_reminder_follows_the_default`).
- **Tables that pre-date the modules**: old rows with NULL in every column the mixin added list, serialise, update,
  complete and reopen; `today` and `summary` count them. Old `user_prefs` rows with NULLs follow the app default and a
  stored `07:30` reads as an override.

Limits pinned in the tests:
- A stored work-day time with seconds (`08:00:00`) makes every read of that user's preferences raise `ValueError`;
  normalise the column to `HH:MM` in the migration.
- Checklist items keep bond's `done_at` shape (`...Z`, no microseconds) on the legacy wire; only the four task instants
  are rewritten.
- A rule that returns a key the lib owns, or a name that is not a model column, raises `ValueError` (a 500): keep
  `prepare` to the app's columns.

