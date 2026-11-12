# Tasks contract

Normative for `libs/bond_tasks_py`, `packages/bond_tasks`, `packages/bond_tasks_ui`, `packages/bond_tasks_powersync`
and the task routes an app mounts (the example mounts them in `services/sdk_example/sdk_example/routes/tasks.py`).
Notices, stages and the ledger are in `docs/contracts/notices.md`. Reasons for the rules:
`docs/decisions/2026-11-11-due-instant.md`. Errors use `docs/contracts/error_body.md`. Shared cases:
`fixtures/tasks/`. All instants are naive UTC in storage and ISO 8601 with a trailing `Z` on the wire.

## Words

- A task past its due instant is **overdue**. It is the only flag. There is no `late` key.
- An event in the past is **missed**. Bond has no events module: the word binds labels, capture review and docs.
- `overdue` = the task is open and `due_at < now`. A dated task whose `due_at` is not computed yet falls back to
  `due_date` before the viewer's today. Every count, list section and widget uses this one test. `now` is required in `task_item`, `task_items`,
  `list_tasks` and `summary`.

## The due instant (`due_at`)

1. `due_at` is computed by the server, truncated to the minute, and null if and only if `due_date` is null. A dated
   task with a null `due_at` is "not yet computed": the sweep repairs it. It is never read as undated.
2. A timed task (`due_time` set): `due_at` is `due_date` + `due_time` read in a zone. The zone is the one sent with
   the write (`time_zone`), else the `writer_zone` the host passes, else the actor's stored zone read from `prefs` (none or empty means not stored), else the app default. A timed task uses the actor's
   zone, not the assignee's. A sent zone name is checked: an unknown one is 422 `invalid_time_zone`. The sync path does the same lookup.
3. A client `due_at` is a hint for a timed task only. It is accepted when the offset from the wall clock is a multiple
   of 15 minutes within -12:00 to +14:00 and, if a `time_zone` came with the same write, equals that zone's result.
   Otherwise it is ignored and recomputed. A write is never refused because of `due_at`, and an unparseable `due_at`, on REST or sync, is ignored and the server computes it.
4. A date-only task: `due_at` is `due_date` at the responsible user's `end_of_day`. The responsible user is the
   assignee, else the owner. The zone is that user's stored zone. If none is stored and the actor is the
   responsible user, the zone of the write (rule 2). Else the app default. A client `due_at` is ignored.
5. A task write never stores a zone for anyone. A zone is stored only by that user's settings update.
6. Recompute only when a write changes `due_date`, `due_time` or `assigned_user_id` to a value that differs from the
   stored one, or through `recompute_day_due` (the responsible user changed `end_of_day` or `time_zone`). A timed task
   is never recomputed by settings or by a reassignment. Clearing `due_date` clears `due_time` and `due_at`.
7. A replayed create for an existing owned id returns the row and changes nothing (another owner's id is `id_taken`).
   A replayed patch re-applies rules 2 to 6 against the current settings.
8. Daylight saving: a local time that does not exist moves forward. An ambiguous one takes the first occurrence.
   A lead is subtracted from the instant, not from the wall clock.
9. The day of a task for a viewer is `due_date` for a date-only task, else the viewer-zone date of `due_at`.
10. Sort: `due_at` ascending with nulls last, then `created_at` descending, then `id`.
11. A device sends `due_at` only for a timed task, computed in its own current zone. It sends none for a date-only
    task and shows `due_date` when `due_at` is null.

## Sections of the day view

Exclusive, for a viewer at `now` (the lists show only tasks the viewer owns or is assigned, unless the app allows
`scope=all`):

| Section | Test |
|---|---|
| overdue | open and `due_at < now` |
| today | open, not overdue, day is the viewer's today or earlier |
| undated | open and no `due_date` |
| done_today | done, `completed_at` inside the viewer's local today |

An open task due on a later day is in no section. `GET /tasks/summary` counts `open`, `overdue`, `due_today`
(the today section) and `no_date` with the same tests, so the numbers agree with the lists.

## `remind_minutes_before`

| Value | Meaning |
|---|---|
| `-3` | use my default (`lead_minutes` of the recipient). The default for a new task. |
| `-2` | no close notice |
| `-1` | the morning of the due date, at the recipient's `start_of_day` (none if that is not before `due_at`) |
| `N >= 0` | N minutes before `due_at` |

Input is accepted from -3 to 525600. The lead in use is capped at 10080 minutes. Nothing here queues a reminder:
the notice stages read this value (`notices.md`).

## Settings

`GET /tasks/settings` and `PUT /tasks/settings`. No row means the app's defaults.

| Field | Type | Default | Rule |
|---|---|---|---|
| `time_zone` | IANA name or null | null (the app default) | unknown name: 422 `invalid_time_zone` |
| `start_of_day` | `HH:MM` | `08:00` | must differ from `end_of_day` (422 `invalid_work_day`) |
| `end_of_day` | `HH:MM` | `17:00` | a work day across midnight is allowed |
| `lead_minutes` | integer 0 to 10080 | 60 | |

The defaults in the table are the library's. An app may set its own (`defaults=` of `get_settings`, `update_settings`
and `StoredPreferences`, one `UserPrefs`). A column that is NULL means "follow the app default"; a stored value is the
person's own choice.

Answer: the four EFFECTIVE values (what the person stored, else the app default), `warnings`, and
`"overridden": [names]`, the fields the person has stored, in the order `time_zone`, `start_of_day`, `end_of_day`,
`lead_minutes`. A settings screen shows "default" for the rest and offers a reset.

```json
{"time_zone": "America/Los_Angeles", "start_of_day": "08:00", "end_of_day": "17:00", "lead_minutes": 60,
 "warnings": [], "overridden": []}
```

A PUT changes only the fields it sends: a field that is absent is unchanged, and a field that is present and `null`
resets it to the app default (NULL is stored). A reset that changes the effective end of day or zone recomputes due
instants like any other change, and a reset can be refused with `invalid_work_day` when the default equals the other
stored bound. In the Dart client `TaskSettings.overridden` is null when the server did not send the list (an older server): the
settings form then shows no default hints and sends every field on Save, as before. `toJson` writes `overridden`
whenever it is not null. Changing `end_of_day` or
`time_zone` recomputes `due_at` of the user's open date-only tasks only, in the same transaction. A timed task keeps its instant: its `due_time` is the wall time in the zone it was written in. `update_settings(..., on_recomputed=)`
calls `on_recomputed(task, old_due_at)` once per task whose `due_at` really changed: the host calls `dismiss_stale` there. Warnings never block:

| Warning | When |
|---|---|
| `lead_longer_than_work_day` | `lead_minutes` is longer than the work day |
| `time_zone_unknown` | the work day changed and the user has no stored zone |

Quiet hours are not a setting. They are derived: after `end_of_day` until `start_of_day` (`notices.md`).

## TaskItem

24 keys, in this order: `id`, `title`, `notes`, `due_date`, `due_time`, `priority`, `due_at`, `status`,
`owner_user_id`, `owner_name`, `assigned_user_id`, `assignee_name`, `checklist`, `remind_minutes_before`, `links`,
`completed_at`, `mirror_enabled`, `mirror_status`, `external_provider`, `external_event_id`, `source`, `created_at`,
`updated_at`, `overdue`. `priority` is 1 low, 2 normal, 3 high or null. `status` is `open`, `done` or `cancelled`.
`checklist` is `[{id, text, done_at}]`, `links` is `[{kind, id, label}]` (a repeated kind and id keeps the first).
`overdue` is computed per response and never stored. A link's `label` is read at response time when the app passes a
`LinkResolver.labels` callable to `task_items(labels=)`: the current label replaces the stored one, so a renamed contact
shows its new name. A link the resolver does not know keeps its stored label. The single-reminder keys `remind_at` and `reminded_at` are gone.
Fixture: `fixtures/tasks/task.json`. `libs/bond_tasks_py` pins the list as `ITEM_KEYS`.

## Routes

The query `time_zone` tells the server the viewer's zone. The example ignores the old `today` query: the viewer's day is `now` read in that zone.

| Route | Request | Answer |
|---|---|---|
| `GET /tasks` | filters, `time_zone`, `today`, `limit`, `offset` | `{items, total, limit, offset}` |
| `GET /tasks/summary` | `time_zone`, `today` | `{open, overdue, due_today, no_date}` |
| `GET /tasks/today` | `time_zone`, `today` | `{overdue, today, undated, done_today: [TaskItem], counts: {overdue, today, undated, done_today}}` |
| `GET /tasks/{id}` | | `TaskItem` |
| `POST /tasks` (201), `PUT /tasks/{id}` | task fields, `priority`, `due_at`, `time_zone` | `TaskItem` |
| `POST /tasks/{id}/complete`, `/reopen`, `/cancel` | none | `TaskItem` |
| `DELETE /tasks/{id}` | none | 204 |
| `PUT /tasks/{id}/checklist/{item_id}` | `{done}` | `TaskItem` |
| `GET /tasks/settings`, `PUT /tasks/settings` | the settings fields | the settings and `warnings` |
| `POST /tasks/parse` | `{text (1 to 500), today?, time_zone?}` | `{items, degraded, reason}`; creates nothing |
| `GET /tasks/links/search` | `kind`, `q` | `{items: [{kind, id, label}]}` |

List filters: `scope` (`mine` or `all`), `status` (`open`, `done`, `cancelled`, `active` (open and done), `all`), `on_or_before`, `due_from`, `due_to`,
`include_undated`, `no_date`, `owner_user_id`, `assigned_user_id`, `assigned_to_me`, `link_kind`, `link_id`.
An app with older clients that cannot tell a cancelled task apart filters cancelled rows out of its sync stream.
`list_tasks(extra_where=)` takes SQLAlchemy criteria on the app's own columns, applied before the count and the paging.
Complete and reopen need `can_complete`. Cancel, reassign and delete need `can_own`. Undoing a cancel (reopen or
complete of a cancelled task) also needs `can_own`. In the default `DefaultPermissions` the owner owns and
the owner or assignee completes. An omitted field in a write is unchanged and an explicit `null` clears `notes`,
`due_date`, `due_time`, `priority` and `assigned_user_id`.

Parse answer: a task item is `{kind: "task", title, due_date, due_time, due_defaulted, priority, links, confidence,
flags, degraded}`, an event item is `{kind: "event", title, start_date, start_time, all_day, end_date, end_time,
links, confidence, flags, degraded}`. A link is `{text, kind, candidates: [{id, label}]}`. At most 8 items and 5 links
per item. `flags`: `low_confidence` (below 0.5), and `missed` on an event dated before today. `reason` is null,
`model_unavailable` or `invalid_output`. `dropped` (items discarded) appears only above zero. A guard refusal is 429.

## Error codes

Body: `{"detail": {"code", "message"}}` (`error_body.md`). Sync verdicts carry the same code as the message.

| Status | Code |
|---|---|
| 403 | `not_task_editor`, `not_task_owner` |
| 404 | `task_not_found`, `checklist_item_not_found` |
| 409 | `id_taken` |
| 422 | `unknown_assignee`, `title_required`, `due_time_requires_date`, `invalid_time_zone`, `invalid_action`, `invalid_work_day`, `invalid_priority`, `text_required`, `text_too_long` |
| 429 | `capture_denied` |

`not_task_owner` also answers a cancel the user may not make from a notice action. Notice codes
(`notice_not_found`, `not_notice_owner`, `invalid_cursor`) are in `notices.md`. The library raises `invalid_priority` on the sync path. The example maps a priority outside 1 to 3 to 422 `invalid_priority`, and a bad zone in the body or query to 422 `invalid_time_zone`, with a body pre-check on POST and PUT /tasks and PUT /tasks/settings.

## Sync field lists

Bond ships no stream rules. The app's stream file names every column.

| Table | Streamed columns | Device may write |
|---|---|---|
| `tasks` | every stored column, the 25 keys of `TASK_COLUMNS`, `WHERE owner_user_id = auth.user_id() OR assigned_user_id = auth.user_id()` | `title`, `notes`, `due_date`, `due_time`, `priority`, `due_at` (hint), `assigned_user_id`, `remind_minutes_before`, `mirror_enabled`, `checklist`, `links`, `source`, and `status` of `open` or `done` |
| `task_user_settings` | not synced: read and written over REST | none |

Device lifecycle writes carry `_metadata` `{"action": "complete" | "reopen" | "cancel"}` so the upload picks the route.
Owner, `created_by`, `completed_*`, `mirror_*` and `external_*` are server-owned. A lone `due_at` patch changes nothing.
The notices and push device tables are in `notices.md`.

Client extras. The Dart `Task` keeps every key outside the 24 item keys in `Task.extras` (`Map<String, Object?>`,
default empty). `Task.toJson` does not write them, so the fixtures stay exact. `TaskDraft.extras` and `TaskPatch.extras`
are merged into the write body after the known keys and never override them. With `bond_tasks_powersync`, extra
columns declared with `tasksTables(extraColumns:)` round-trip through the same map.

An app may refuse a write with a rule of its own through `prepare(session, task or None, actor, extras)` on `create`,
`update` and `sync_routes`. It runs after the permission check and before anything is written, on the REST and the sync
path alike, and a `TaskError` it raises (a 403 becomes the sync verdict `forbidden`) writes nothing.
