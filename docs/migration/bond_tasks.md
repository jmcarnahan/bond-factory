# Migrating to bond_tasks and bond_tasks_ui

Task models and the REST client (`packages/bond_tasks`, pure Dart: needs `bond_json`, `bond_api`) and the task widgets
(`packages/bond_tasks_ui`: needs `bond_tasks`, `bond_ui`). The server half is `bond_tasks_py` (`docs/migration/bond_tasks_py.md`).
Legend: `docs/migration/README.md`. Wire shape: `fixtures/tasks/task.json`.

## 1. What it replaces

| App | Goes away | Becomes |
|---|---|---|
| S web | `flutterui/lib/data/models/task_models.dart` 416, `data/services/task_api_service.dart` 201, `presentation/widgets/tasks/` 9 files 1,977 | `Task`, `TaskDraft`/`TaskPatch`, `TaskFilters`, `TasksApi`; `BondTaskRow`, `BondTaskList`, `BondTaskForm`, `BondTaskQuickAdd`, `BondTaskSummaryCard`, `BondTaskDeleteControl` |
| S phone | `mobile/crm_proposals/lib/data/tasks/task_models.dart` 394, `features/today_v2/widgets/{task_form 338, task_list 124, task_undo_line 64, entity_tasks_section 231}` | the same widgets; `entity_tasks_section` becomes a `BondTaskList` filtered with `link_kind` + `link_id` |
| A | `flutterui/apps/crew_mobile/lib/features/today/{add_event_composer 111, event_draft_card 433, my_day_timeline 440}` and `PersonalEvent`/`EventDraft`/`EventInput` in `avalon_core/lib/src/models/my_day.dart` (personal events) | personal events become tasks with a due date and time; the reminder encoding is unchanged (-2 none, -1 08:00 on the day, N minutes before; 0 is the start) |

S keeps `TaskParse`, `TaskContactMatch`, `TaskLoanCandidate` and the LLM `parse` call app-side. A keeps the day timeline layout
and `MyDay`; only the item source changes.

## 2. The adapter

The app supplies four things and nothing else.

```dart
// Strings: one object, English defaults. Override what the app words differently.
const labels = TaskLabels(complete: 'Mark done', mirror: 'Add to Outlook calendar');

// Names: the form takes people as a list, the row takes the server's `assignee_name`.
final people = [for (final p in directory.active) TaskAssignee(p.id, p.displayName)];

// The client's wall date, from the app clock: the server computes `overdue` against it.
final today = DateTime(clock.now().year, clock.now().month, clock.now().day);
final api = TasksApi(apiClient);          // prefix '/tasks'; pass prefix: for another mount
```

- **Routing**: row tap and the "new task" button go to the app's own routes; the widgets only call back.
- **Edit**: `onSubmit` gives a `TaskDraft`; send `api.update(id, TaskPatch.fromDraft(draft), today: ...)`. Build a
  `TaskPatch` by hand to change one field; `Present(null)` clears `notes`, `due_date`, `due_time` or `assigned_user_id`.
- **Links**: S `contact_id`/`loan_id` become `TaskLink(kind: 'contact' | 'loan', id, label)`; A uses `job`/`property`.
- **Theme**: widgets read `BondTokens` and `BondLabelsScope`; see `docs/migration/bond_ui.md`.

## 3. Call-site changes

| Old | New |
|---|---|
| S `TaskItem.fromJson`, `status` as a string | `Task.fromJson`, `TaskStatus` enum; `status == 'open'` becomes `task.isOpen` |
| S `outlookEventId`, `mirrorToOutlook` | `externalEventId` (with `externalProvider: 'microsoft'`), `mirrorEnabled` |
| S `contactName`, `loanLabel`, `loanStage` | `links[].label`; the stage is app data, not a task field |
| S `taskDateString(DateTime)` | `dueDateString(DateTime)` (in `bond_tasks_ui`, `task_format.dart`; `bond_tasks` keeps dates as strings) |
| S `TaskApiException` | `ApiException` subtypes: `NotFound` (`task_not_found`), `Forbidden` (`not_task_owner`, `not_task_editor`), `Conflict` (`id_taken`), `ValidationError` |
| A `PersonalEvent.day/startAt/allDay` | `dueDate` + optional `dueTime`; no end time, no duration |
| A `remindMinutesBefore`, `remindAt`, `done` | same names on `Task`; `done` is `status == done` |

Find them: `grep -rnE "TaskItem|TaskApiService|PersonalEvent|EventDraft" flutterui mobile`.

## 4. Data

- Tasks and personal events become rows of `tasks` (`bond_tasks_py`). Copy A events with `source = 'personal_event'`,
  `due_time` from the local start (null for an all-day event) and `mirror_enabled = false`.
- Due time is a local wall-clock string; never convert it to UTC on the client.
- Ids: a client may choose `^[\w-]{1,64}$`; replaying a create returns the row, another owner's id answers 409 `id_taken`.

## 5. Acceptance

- `make -C packages/bond_tasks test` (round trip of the shared fixture, patch wire shape, filters, client) and `analyze`.
- `make -C packages/bond_tasks_ui test` (each widget at 1280 and 390 px, validation, draft, tick) and `analyze`.
- `make -C demos/sdk_demo test T=test/tasks_page_test.dart`; walk `/tasks` against the example: add, tick, complete, delete,
  mirror (`sdk.tasks.external-<id>`), run due jobs (`sdk.tasks.run-due-jobs`), notices (`sdk.tasks.notices`).
- In the app: its task tests pass against the adapter, then the full suite once before the PR.

## 6. Known gaps (behaviour the module dropped)

- No quick-add text parsing, no inline editor, no undo line, no loan picker: they stay in the app.
- Grouping: the list judges overdue by the supplied `today` as well as the server flag; a done task never shows as overdue.
- `TaskStatus.cancelled` exists on the wire; the widgets show it as a done-style row.
- A all-day events with an end time lose the end; multi-day events are not tasks.
- `DemoJobsApi` (`POST /jobs/tick`, `GET /tasks/notices`) exists only in the fake-mode example; do not call it from an app.
