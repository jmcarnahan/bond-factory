# Migrating to bond_tasks_py

Task table, services, reminders and calendar mirror (`libs/bond_tasks_py`). Wired end to end in
`services/sdk_example` (`tasks_wiring.py`, `routes/tasks.py`, `routes/jobs.py`). Legend: `docs/migration/README.md`.
Paths: S `sbelcrm/`, A `backend/avalon/`. The Dart side is `docs/migration/bond_tasks.md`.

## 1. What it replaces

| App | Goes away | Stays app-side |
|---|---|---|
| S | `TaskRecord` body (`db/models.py:2597`), `services/task_service.py` (CRUD, roles, list, summary, `to_item`), `services/task_outlook_mirror.py`, the `/tasks` router except `POST /tasks/parse`, `sync/app/handlers_tasks.py` | contact and loan columns and links, `relink_loan_ids`, `capture_service` and `/tasks/parse` (LLM), loan-actor co-edit rule, admin override |
| A | `PersonalEventRecord` (`db/models.py:1626`) and `services/personal_events.py` reminder code (`schedule_reminder`, `_compute_remind`), `/me/events` router | the interpret route (LLM), the Today screen's day grouping, `worker.py` handler `event_reminder` body (becomes `notify`) |

## 2. S: table and service diff

`TaskRecord` to `TasksMixin` (same table name `tasks`, same two composite indexes):

| S column | Mixin | Do |
|---|---|---|
| `contact_id`, `loan_id`, `bytepro_file_data_id` | `links` JSON `[{kind, id, label}]` | keep your columns on your subclass if you need the FK or the backfill relink; also write `links` |
| `mirror_to_outlook` | `mirror_enabled` | rename |
| `outlook_event_id`, `outlook_event_user_id` | `external_event_id`, `external_account_user_id` | rename; also new `external_provider`, `external_etag` |
| `due_time` `String(5)` | same | unchanged: local `HH:MM`, requires `due_date` |
| (none) | `checklist`, `remind_minutes_before`, `remind_at`, `reminded_at` | new, defaults `[]`, `-2`, null, null |

- Error codes lose their upper case: `TASK_NOT_FOUND` is `task_not_found`, and bodies are `{"detail": {code, message}}`
  (was `{error_code, message}`). `bond_api` parses both; update S's Dart `TaskError` mapping.
- Hard delete stays. The service returns a `MirrorPointer`; remove the event in a background task.
- The mirror moves from Graph-only to any connection: build a `MirrorProviders` over `bond_oauth` + `bond_calendar`
  (`sdk_example/tasks_wiring.py`). The calendar stays the source of truth for events; only the id and etag are stored.
- `mirror_status` is now `mark_mirror`'s `pending` when an event exists but the task is no longer eligible, so the pass deletes it.
- Sync handlers: replace `handlers_tasks.py` with `sync_routes(Task, scheduler=..., after_write=...)`, wrap each as
  `Route(r.ops, r.handler, r.reads)` and map `TaskError` with `verdict_for` in `Host.reject_for`.

## 3. A: personal events become tasks

- Checklist items (`start_at` NULL) become tasks with `due_date = day` and `due_time` null. Timed entries keep
  `due_time` as local `HH:MM` of `start_at`; `end_at` has no column (a mirrored event lasts 30 minutes).
- `done_at` becomes `status = done` plus `completed_at`. `removed_at` (soft delete, `/restore`) has no equivalent:
  the lib hard-deletes. Keep your `restore` route only if the product needs undo, by cancelling instead (`status = cancelled`).
- Reminder encoding is kept as is: `-2` none, `-1` morning of (08:00 local), `N` minutes before. A task with no due time
  counts as due at 08:00 local for `N` minutes before. The job key changes from `event_reminder:<id>:<minute>` to `task_reminder:<id>`.
- Data move: one INSERT ... SELECT per app into `tasks` (`owner_user_id = user_id`, `created_by = user_id`,
  `source = 'user'` kept), then drop `personal_events` after one release. Pending `event_reminder` jobs: let them drain
  or re-enqueue through `schedule_reminder`.
- `PATCH /me/events/{id}` becomes `PUT /tasks/{id}` (omitted = unchanged, null clears); `done: true` becomes `POST /tasks/{id}/complete`.

## 4. Reminders and the queue

- Provide a `Scheduler`: `enqueue` calls `bond_jobs.enqueue(..., key=dedupe_key)`; `cancel` deletes the non-running jobs with
  that key (a done job must go too, or a moved reminder never runs again). The enqueue happens in the write's transaction.
- Register the job type `task_reminder` (`JOB_TYPE`) calling `fire_reminder(session, Task, payload["task_id"], notify,
  now=now)`. `notify` is the app's push or e-mail; the example appends to a list that `GET /tasks/notices` returns.
- A reminder moved to a past instant fires on the next pass. Pass the app's IANA zone as `tz`; the example uses UTC.

## 5. Routers

Both apps' routers shrink to the example's `routes/tasks.py`: `unit(request)` (one transaction, `TaskError` to
`ApiError`), `after_write` (reschedule, queue `sync_mirror` after commit). Keep S's company-wide visibility, loan-actor and
admin rules in your own `require_*` wrapper before calling `update` or `delete`; the lib only knows owner and assignee.
`GET /tasks` gains `link_kind` + `link_id` (replaces `contact_id`/`loan_id`; S's company-wide entity list is `scope=all` plus the link) and `status` `all` (includes cancelled). The example gates `scope=all` and reading another person's task behind capability `tasks.read_all`; `POST /tasks/{id}/cancel` is owner-only.
Google write-back needs `calendar.events` scope: app A's users hold the read-only scope and must re-consent.

## 6. Order and checks

1. Add the mixin and a revision (copy `alembic/versions/0002_phase3.py`); backfill from `TaskRecord` or `personal_events`.
2. Wire scheduler, reminder handler and `MirrorProviders`; swap the router; run the app's task tests.
3. Assert `TASK_COLUMNS` against your engine; round-trip `fixtures/tasks/task.json` through `task_item`.
4. Known limit: if an account holds both Google and Microsoft connections the example mirrors to Google only.
