# 2026-11-11 Notifications: stages, the ledger claim, delivery

Status: accepted. Dated, append-only. Evidence: a prototype on Postgres 18 with 2 and 4 worker processes over
6,000 claims, and a 30-task day-by-day simulation (2026-11-11, kept outside the repo).

## Stages

Per recipient, in the recipient's zone and settings. Exactly one stage is current at an instant.

| Stage | When |
|---|---|
| close | from `due_at` minus the lead until `due_at` |
| due | from `due_at` for 15 minutes |
| past | from `due_at` + 15 minutes: one notice then, and one each morning at the start of the work day |

- The past series is numbered by local calendar days, not 24-hour blocks, and stops after 5 mornings. The last
  notice says it is the last. The task stays overdue; only alerts stop. The number is a parameter.
- The due notice is always sent within its 15 minutes. Quiet hours (outside the work day) defer the past
  notices of any task and the close notice of a date-only task. The close notice of a task with an explicit
  time is sent at its time.
- Recipients: close and due go to the responsible user; past goes to the responsible user and the owner.
- A sweep claims only the current stage. A missed day does not flood. Stage times before an activation
  instant `since` are recorded as skipped.
- Every notice carries actions: done, snooze (put this notice away; the next still comes), cancel (cancel the
  task; only for a user who may). The same three appear on the phone notification, the inbox and in the app.

## The claim

- Ledger key: (task, user, stage, sequence, deadline token). The token is `due_at` in epoch minutes for a
  timed task and the ISO due date for a date-only task. Measured: with no token a postponed task got no
  notice for its new time; with an epoch token on date-only tasks a zone change re-sent 50 of 50; with this
  rule, none. The token is never null (a null in a unique key removes uniqueness).
- One id on every path: `sha256("task|user|stage|sequence|token")[:32]`. It is the ledger id, the notice id,
  the push collapse id and, through a 31-bit FNV-1a hash, the local notification id.
- The claim is one set-based `INSERT ... ON CONFLICT DO NOTHING RETURNING` with no conflict target, rows in a
  fixed order, inside a savepoint. Only returned rows are won. Measured: 0 duplicates in every variant;
  per-row claims deadlocked 20 to 56 times when workers walked tasks in different orders; the set-based claim
  never did; a conflict target on the unique key raised on the primary key; `SKIP LOCKED` alone was not
  exactly-once.

## Delivery

- `TransactionalNotifier.write(session, notices)` runs inside the claim (the inbox). A raise cancels the batch.
- `Notifier.send(session, notice)` runs after commit, from an outbox keyed (ledger id, channel), leased by
  compare-and-set. The lease is committed before anything is sent. A notifier answers ok, retryable,
  unregistered or failed; a failed or given-up row is never leased again. At-least-once: a channel must be idempotent on the notice id. Measured: a single
  delivered stamp on the ledger duplicated push or lost chat when one channel failed; the outbox did neither.
- No library imports another. Notifiers read the notice by attribute.

## Retention

Rows of tasks closed for 30 days are deleted. For open tasks, close and due rows go after 8 days and past
rows keep only the newest sequence. Deleting more re-sent notices in the simulation. Notices: read or
dismissed for 30 days, or older than 90 days. Sync streams allow no ORDER or LIMIT, so pruning is what keeps
the synced set small.

## Three ways to reach the user

Synced notices (app open), local notifications (app closed, stages known at the last sync), Apple push (app
closed, changes since the last sync). All use the one id, so a second arrival replaces the first.

## Notes

- A date-only task is due at the end of the work day, so its "shortly after due" notice falls in quiet hours
  and is superseded by the next morning's notice before it can be sent. A date-only task therefore gets the
  due notice and five mornings; a task with an explicit time gets the due notice, one shortly after, and
  five mornings.
- One row that a notifier cannot write must not block its batch: the sweep retries a failed batch row by row
  and records the row that still fails.
- The lead for "close" is capped at 10080 minutes when it is used. A larger stored value is accepted on
  input, as before, and treated as 10080.
- Amended during the build: a row whose notifier cannot write is NOT recorded. It is logged, counted in the
  sweep's result, and tried again by the next sweep while its stage is current, so an outage of the inbox
  loses nothing. (This replaces "records the row that still fails" above.)
- Delivery stamps and commits one row at a time, leases an exact number of rows, and, when given the task
  model, drops a queued notice whose task was finished, cancelled, deleted or postponed.
- Retention, in full: rows of tasks closed for 30 days; for open tasks, close and due rows after 8 days, past
  rows older than 2 days except the newest, and rows of an earlier deadline after 8 days.
- The inbox puts away a task's older notices when a notice for a new due time is written; the app calls
  `dismiss_for_source` when a task is finished and `dismiss_stale` when its due time changes.
