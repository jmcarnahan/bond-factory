# Hosting bond_tasks_py: models, routes and service calls

The code an app writes around `libs/bond_tasks_py`. The reference host is `services/sdk_example/sdk_example/`, mainly
`routes/tasks.py` (CRUD and lifecycle), `routes/task_today.py` (day view and settings), `routes/notices.py`, `routes/push.py`
and `task_support.py`. The note for the library is `bond_tasks_py.md`, the wire is `docs/contracts/tasks.md`.

## 1. The models

The libs ship mixins and no migrations. All seven classes live in ONE database. The names below are the reference host's.

```python
from sqlalchemy.orm import DeclarativeBase
from bond_tasks_py import (NoticeLedgerMixin, NoticeOutboxMixin, TaskLinkIndexMixin, TasksMixin, TaskUserSettingsMixin)
from bond_notify_py import NoticesMixin
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

In a test, `create_engine("sqlite://")` (in memory) works once you call `sqlite_savepoint_setup(engine)`.

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
| `list_tasks` | `list_tasks(session, *, task_model, user_id, filters=None, limit=25, offset=0, link_index_model=None, viewer_zone=None, now)` returns `(rows, total)` |
| `summary` | `summary(session, *, task_model, user_id, now, viewer_zone)` |
| `today` | `today(session, *, task_model, user_id, now, viewer_zone)` |
| `task_item` | `task_item(task, *, today, now, names=None)` (`today` is `viewer_today(now, zone)`); `task_items(tasks, *, today, now, names=None)` for a list, `names` being a callable from user ids to a name map |
| settings | `get_settings(session, settings_model, user_id)`, `update_settings(session, *, settings_model, task_model, user_id, data, tz, now, on_recomputed=None)` |

## 3. Routes and the call behind each

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
| `POST /notices/{id}/act` | `apply_notice_action`, then mark read and `dismiss_for_source` on done or cancel |

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
