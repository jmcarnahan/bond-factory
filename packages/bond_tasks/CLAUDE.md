# bond_tasks
Role: Pure Dart task model, request bodies, filters and REST client for the `/tasks` routes (the `TaskItem` wire shape).

## Key files
- `lib/src/task.dart` (`Task`, `ChecklistItem`, `TaskLink`), `task_enums.dart` (`TaskStatus`, `MirrorStatus`, `kRemind*`).
- `lib/src/task_draft.dart` (`TaskDraft`, `TaskPatch`, `Present`), `task_filters.dart` (`TaskFilters`, `TaskPage`, `TaskSummary`).
- `lib/src/tasks_api.dart` (`TasksApi`, fake-mode-only `DemoJobsApi`), `task_labels.dart` (`TaskLabels`).
- `lib/src/task_stage.dart` (stages, `noticeId`), `task_due.dart`, `task_today.dart`, `task_candidates.dart`, `task_settings*.dart`,
  `task_repository.dart`, `task_controller.dart`; bodies that throw `UnimplementedError` are not built yet.
- Shared fixtures: `../../fixtures/tasks/task.json`, `task_cancelled.json` and the other `fixtures/tasks/*.json`.

## Commands
- `make test T=test/task_test.dart`
- `make analyze`

## Rules
- No Flutter imports, no `dart:io` in lib. Tests use `MockClient` from `package:http/testing.dart`.
- `Task.toJson` writes exactly the `TaskItem` keys; due date and time stay `YYYY-MM-DD` / `HH:MM` strings.
- `TaskPatch`: omitted field stays, `Present(null)` sends an explicit null.
- Keep `DemoJobsApi` apart from `TasksApi`; apps must not get the fake routes by accident.
- No codegen; hand-write fromJson. Stage tests, when written, assert only `stage_times.json` cases whose `effective_zone` is America/Los_Angeles (run under `TZ=America/Los_Angeles`).
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
