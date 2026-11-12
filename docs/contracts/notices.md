# Notices contract

Normative for the three-stage notices of a task: `libs/bond_tasks_py` (stages, ledger, outbox, sweep),
`libs/bond_notify_py` (inbox), `libs/bond_push_py` (Apple push), `packages/bond_notify`, `bond_push`,
`bond_tasks_notifications`, `bond_notify_powersync`. The due instant and the task routes are in
`docs/contracts/tasks.md`. Reasons: `docs/decisions/2026-11-11-notify-ledger.md`. Shared cases:
`fixtures/tasks/stage_times.json`, `fixtures/tasks/notice_ids.json`, `fixtures/notify/`.

## Stages and recipients

Per recipient R with settings P and zone Z (R's stored zone if it is a known name, else the app default):

| Stage | Seq | Starts | Ends |
|---|---|---|---|
| `close` | 0 | `due_at` minus the lead (see `remind_minutes_before` in `tasks.md`) | `due_at` |
| `due` | 0 | `due_at` | `due_at` + 15 minutes |
| `past` | 0 | `due_at` + 15 minutes | the first morning |
| `past` | k = 1 to `max_past` | the k-th local calendar morning after the due date, at `start_of_day` | the next morning |

- Exactly one stage is current per task and recipient at an instant. Local calendar dates are used, never 24-hour
  blocks. Seq 0 of `past` is left out when the first morning comes at or before `due_at` + 15 minutes.
- `max_past` is a parameter of the sweep and of the phone scheduler, default 5. The notice with seq `max_past` has
  `last = true` and nothing is claimed after it. The task stays overdue in lists and in the inbox. Only alerts stop.
- Each tick claims only the current stage and seq, never earlier ones. A missed day makes seq jump. Two sweeps in a
  day make one row. `since` marks stage times before it as ledger status `skipped` (not sent) so a first run does not flood.
- Only open tasks with a non-null `due_at` have stages. A timed task whose `due_at` is null has no stages.
- Recipients (`default_recipients(task, stage)`). The responsible user is the assignee, else the owner. An app may pass its own `Recipients`.

| Stage | Gets the notice |
|---|---|
| `close` | the responsible user |
| `due` | the responsible user |
| `past` | the responsible user and the owner (once if they are the same person) |

## Quiet hours

Quiet hours are not a setting. They are the local times strictly after `end_of_day` and strictly before
`start_of_day` (neither end is quiet). Equal times mean no quiet hours. The rule:

- `due` is always sendable in its 15-minute window, timed or date-only.
- `close` of a TIMED task is sent at its time, even outside the work day. A user who sets 19:00 hears at 19:00.
- `close` of a date-only task and every `past` notice wait. The stage that is current when the work day starts
  is claimed then (deferred, not dropped). If a later stage replaces it first, it is never sent (`send_at` null).

## Ids

```
deadline_token = epoch minutes of due_at          (timed task)
               = ISO due_date, e.g. "2026-11-12"  (date-only task)
               = ""                               (undated, or timed with no due_at)
notice_id      = sha256("task_id|user_id|stage|seq|token") first 32 hex characters
local_id       = FNV-1a 32-bit over the UTF-8 bytes of notice_id, masked to 31 bits
```

Python and Dart both compute these from the same task row; `fixtures/tasks/notice_ids.json` pins them (a list of `{task_id, user_id, stage, seq, token, notice_id, local_id}`).
The Dart stage functions use the DEVICE zone and Python the user's stored zone. Before `ZoneReporter`'s report lands, local alert ids can differ from server ids and a duplicate alert is possible. The `notice_id` is the ledger id, the
`notices` primary key, the Apple collapse id and (through `local_id`) the local notification id. Moving the deadline
changes the token, so a postponed task notices again. A zone change does not change a date-only token.

## Ledger and outbox

- Ledger key: unique `(task_id, user_id, stage, seq, deadline_token)`. Status `claimed` or `skipped`. The claim is one
  set-based `INSERT ... ON CONFLICT DO NOTHING RETURNING` with no conflict target, rows in (task id, user id) order,
  inside a savepoint. Only the rows returned are won. Transactional notifiers (the inbox) and the outbox rows are
  written for the won rows in the same savepoint.
- A transactional notifier that raises cancels its batch. The batch is retried row by row. A row that still fails
  writes nothing, is counted in `SweepResult.errors` and is retried by the next sweep.
- Outbox: one row per `(ledger_id, channel)` for each external channel (push, chat, mail). The inbox has no outbox
  row. `deliver_pending` leases rows (default 300 s), commits the lease, then sends and stamps each row and commits.
  A notifier answers `ok`, `retryable`, `unregistered` (stamp `failed_at`) or `failed` (permanent, stamp at once).
  A retryable row fails after `max_attempts` (default 5). A row whose task is done, cancelled, deleted or postponed is
  failed with `last_error` "superseded" and not sent. A row for a channel with no notifier stays pending and fails after 7 days.
- Retention (`prune_ledger`, `prune_notices`): the rules are in their docstrings. Run both daily. Deleting a ledger row of a current
  stage would re-send it, so the rules keep the newest past row of each deadline.

## Delivery is at least once

A crash between a send and its stamp sends again after the lease. An app must tolerate this:

- Every channel is idempotent on `notice_id`: the inbox insert ignores a repeat, Apple replaces by collapse id, and
  the phone replaces a local notification of the same `local_id`.
- A chat or mail channel must dedupe on `notice_id` itself.
- A notice that reaches the phone twice (local copy and push or sync) is shown once. The phone cancels the pending
  local copy when the synced notice arrives, and skips one still shown in the notification centre.
- A device registered a minute after a notice was sent does not receive that notice.

## Notice wire shape

`{id, user_id, kind, title, body, data, created_at, read_at, dismissed_at}`. `kind` is `task_due`. `data` is
`{task_id, stage, seq, due_at, priority, route, actions, last}`: `route` is `/tasks/<task_id>`, `actions` is the subset
of `done`, `snooze`, `cancel` that this recipient may use, `last` marks the final past notice. `source_id` (the task
id) is server-only. Fixtures: `fixtures/notify/notice.json`, `notices_page.json`. Title is cut to 255 characters.

## Actions

| Action | Effect | Who may |
|---|---|---|
| `done` | completes the task | who may complete (`can_complete`) |
| `snooze` | changes nothing on the task. The notice is marked read. The next scheduled notice still comes. | everyone |
| `cancel` | cancels the task | who may own it (`can_own`); the notice lists `cancel` only for them |

One handler applies them through the task repository on every path (inbox row, stage banner, phone button). On done
or cancel the app also puts away every unread notice of the task for every recipient (`dismiss_for_source`), and when
a task's due time changes it puts away the notices of the old time (`dismiss_stale`). `done` or `cancel` on a task that is not open is a no-op. After a reassignment the host dismisses the task's notices for users
who left: `notice_recipients(task)` (tasks lib) gives who should keep them, then `dismiss_for_source(..., user_ids=...)`. A cancel by someone who may not
is 403 `not_task_owner`. An action id other than the three is 422 `invalid_action`.

## Routes

| Route | Request | Answer |
|---|---|---|
| `GET /notices` | `unread`, `limit`, `before` (cursor `<created_at>\|<id>`) | `{items: [Notice], unread_count, next_cursor}` |
| `POST /notices/{id}/read`, `POST /notices/{id}/dismiss` | none | `Notice` (dismiss also reads) |
| `POST /notices/read-all` | none | `{unread_count}` |
| `POST /notices/{id}/act` | `{action: "done" \| "snooze" \| "cancel"}` | `{notice, task}` |
| `POST /push/devices` (201) | `{device_id, token, platform (ios), environment, topic?}` | `{device_id}` |
| `DELETE /push/devices/{device_id}` (204) | none | none |

`act` applies the action, marks the notice read, and on done or cancel puts away the task's other notices. The
`act` route and the device routes are the app's own. In the example, `act` needs the `tasks.write` capability (read and dismiss need only a session). `GET /notices` shows the user's own, undismissed notices, newest
first by `(created_at, id)`. `list_notices` also returns the next cursor: an app that pages sends it as `before`. Errors: 404 `notice_not_found`, 403 `not_notice_owner`, 422 `invalid_cursor`. Device
errors (`PushError`): 422 `invalid_platform`, `invalid_environment`, `token_required`, `device_id_required`,
`token_too_long`, `device_id_too_long`, `invalid_topic`, `topic_too_long`; 404 `device_not_found`; 403
`not_device_owner`; 409 `device_conflict`; 503 `push_not_configured`.

## Phone notifications (iOS only)

- Payload of a local notification and of an Apple push: the JSON `{notice_id, task_id, route}`.
- Two iOS categories for local notifications: `bond.task` (Done, Snooze) and `bond.task.owner` (Done, Snooze,
  Cancel). The owner category is used when the notice lists `cancel`. All buttons open the app in the foreground and are
  applied there through the repository. No background isolate is used.
- An Apple push carries NO action category by default (`PushNotifier(category=None)`). The push plugin cannot report
  which button of a remote notification was pressed, so a push has no buttons and a tap opens the task, where the
  banner offers the three actions. The server sends a category only if the app passes one.
- iOS keeps at most 64 pending local notifications. The scheduler keeps 60, at most 3 per task, nearest first.
- When push is on, the app tells the coordinator the three stages are handled elsewhere, or the person is told twice.
- Sandbox and production tokens are not interchangeable. The device row stores `environment` and the server picks
  the Apple host by it. The app passes the environment from its build configuration.

## Devices

`push_devices` row id on REST and on the phone: `"d_"` + first 32 hex characters of `sha256("<user_id>|<device_id>")`
(`device_row_id`). The server sets `user_id` from the session and never trusts the client's. A device may insert its
row (a sync put must use id `device_row_id(user, device_id)`, else `not_device_owner`), patch `token`, `platform`, `environment` and `topic`, and delete it. `last_seen_at` and `disabled_at` are the
server's. A token reported dead by Apple is disabled, not deleted. Only `ios` is accepted as a platform (`android` and `web` are 422 `invalid_platform`), and only `ios` rows are sent to.

## Sync field lists

| Table | Streamed columns | Device may write |
|---|---|---|
| `notices` | `id, user_id, kind, title, body, data, created_at, read_at, dismissed_at` `WHERE user_id = auth.user_id()` | `read_at`, `dismissed_at` (the server stores its own clock) |
| `push_devices` | `id, user_id, device_id, token, platform, environment, topic, last_seen_at, disabled_at, created_at` `WHERE user_id = auth.user_id()` | its own row: insert, patch of `token`, `platform`, `environment`, `topic`, delete |

Streams allow no ORDER or LIMIT, so `prune_notices` keeps the synced set small.
