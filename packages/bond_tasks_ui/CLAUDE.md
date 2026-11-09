# bond_tasks_ui
Role: Flutter task widgets over `bond_tasks` and `bond_ui`: list, row, form, quick add, checklist, summary, delete.

## Key files
- `lib/src/bond_task_form.dart` (`BondTaskForm`, `TaskAssignee`), `bond_task_checklist_editor.dart`, `bond_checklist.dart`.
- `lib/src/bond_task_list.dart`, `bond_task_row.dart`, `bond_task_quick_add.dart`, `bond_task_summary_card.dart`,
  `bond_task_delete_control.dart`, `bond_check_row.dart`.
- `lib/src/task_format.dart` (`dueDateString`, `parseDueDate`, `sectionOf`, `formatDue`).
- Tests: `test/task_widgets_test.dart`, `test/task_form_test.dart`, `test/support.dart` (`pumpAt`, both widths).

## Commands
- `make test T=test/task_form_test.dart`
- `make analyze`

## Rules
- No popups, dialogs, sheets or snack bars; state shows inline. Every test checks `expectNoOverlays` at 1280 and 390.
- Every string comes from `TaskLabels`; the person's wall date is passed in as `today`, never read from the clock.
- Single widgets take `semanticsId`; composite ones take `semanticsPrefix` and derive `<prefix>.row-<id>`, `<prefix>.form-<part>`.
- No codegen; hand-write fromJson.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
