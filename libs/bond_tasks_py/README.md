# bond_tasks_py

Tasks the app owns: a `tasks` table, status, checklist, reminders and an optional calendar mirror. Google Calendar and
Microsoft Graph are mirrors behind a Protocol, never the source of truth. Imports only SQLAlchemy, pydantic and the
standard library. The queue and the calendar arrive through Protocols the app wires.

## Wire it
```python
from bond_tasks_py import TasksMixin

class Task(TasksMixin, Base):      # table "tasks"; the lib ships no migration, write your own revision
    pass
```
`TASK_COLUMNS` lists every column and its nullability; assert it against your engine in a test.

## Service functions
All take a session, flush and never commit, so a task write and its reminder job commit together.

| Call | Notes |
|---|---|
| `create(session, *, task_model, owner_user_id, actor_user_id, data: TaskCreate, now, tz, user_exists)` | A client-chosen id (`[A-Za-z0-9_-]{1,64}`) replayed by its owner returns the row, also when two creates race; another owner's id is `id_taken`. NUL characters in text are refused. |
| `update(session, *, task, actor_user_id, data: TaskUpdate, now, tz, user_exists)` | Omitted = unchanged. `None` clears `due_date` (and the time), `due_time`, `assigned_user_id`, `notes`. |
| `complete` / `reopen` / `cancel` / `delete` / `get` | `complete`, `reopen` and `cancel` are idempotent; a second `delete` is `task_not_found`. `cancel`, `delete` and reassigning are owner-only, and so is `complete` or `reopen` on a cancelled task. The owner or the assignee may do the rest. `get` has no access rule: the app decides who may read. |
| `list_tasks(session, *, task_model, user_id, filters: TaskFilters, limit, offset)` | Soonest due first, undated last. Returns `(rows, total)`. `scope="mine"` (owner or assignee) always applies; `scope="all"`, and so any wider read, is the app's to gate. |
| `summary(session, *, task_model, user_id, today)` | `{open, overdue, due_today, no_date}`. |
| `set_checklist_item(task, item_id, done, now, *, actor_user_id=None)` | Items are `{id, text, done_at}`. Pass `actor_user_id` to enforce the editor rule. |
| `task_item(task, *, today, names)` / `task_items(...)` | The wire JSON (`ITEM_KEYS`), shared fixture `fixtures/tasks/task.json`. |

Refusals raise `TaskError(code, message, status)`: `not_task_editor` 403, `not_task_owner` 403, `task_not_found` 404,
`checklist_item_not_found` 404, `unknown_assignee` 422, `title_required` 422, `due_time_requires_date` 422, `id_taken` 409.

## Reminders
`remind_minutes_before`: `-2` none, `-1` 08:00 local on the due date, `N` minutes before the due time (a task with no
time counts as 08:00). `schedule_reminder(session, task, scheduler, *, tz)` cancels the earlier job, then enqueues job
type `task_reminder` `{task_id}` at the computed instant under the key `task_reminder:<id>`.
`fire_reminder(session, task_model, task_id, notify, *, now)` claims `reminded_at` with one conditional UPDATE, so two workers notify once; a failing `notify`
re-raises so the queue retries. The `Scheduler` Protocol is `enqueue(session, *, job_type, payload, run_at,
dedupe_key)` plus `cancel(session, *, dedupe_key)`; `cancel` must also clear a finished job so a moved reminder can run. Known narrow race: `cancel` spares a job that is running, so a reschedule in that instant finds the key taken and enqueues nothing; the next edit schedules it.

## Mirror
Two passes for one task never leave two events: the pointer is recorded compare-and-set and the loser deletes its event. A task is mirrored when `mirror_enabled`, it has a due date and it is open. Writes only set `mirror_status` to
`pending` or `skipped`. After the commit, run `sync_mirror(session_factory, task_model, task_id, providers, tz=...)`
as a background task. It never raises and records `mirrored`, `skipped` or `failed` plus the provider, event id,
mailbox and etag. Updates send the stored etag; a stale one re-reads and updates once. A reassign deletes the event in the
old mailbox and creates one in the new. `MirrorProviders.for_user(session, user_id)` returns `(provider name,
CalendarMirror)` or None. After a hard delete, `remove_event(session_factory, providers, pointer)` removes the event.
Provider errors are recognised by class name (`NotFound`, `EtagMismatch`, `ReconnectRequired`) or by `status`.

## Sync
`sync_routes(task_model, scheduler=..., after_write=..., after_delete=...)` returns handlers for `("tasks", None)`
put/patch/delete and `("tasks", "complete")` / `("tasks", "reopen")`. Wrap each as the sync lib's `Route(r.ops,
r.handler, r.reads)` and map errors with `verdict_for(exc)` in the host's `reject_for` hook.

See `services/sdk_example` (`tasks_wiring.py`, `routes/tasks.py`) for a complete wiring.
