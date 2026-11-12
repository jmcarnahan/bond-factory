# Migrating to bond_tasks_ui

Task widgets (`packages/bond_tasks_ui`, Flutter: needs `bond_tasks`, `bond_ui`). Pure widgets: data and callbacks in, no
API calls, no clock reads. The headless layer is `bond_tasks.md`. Legend: `docs/migration/README.md`.

## 1. What it replaces

| App | Goes away | Becomes |
|---|---|---|
| S web | `presentation/widgets/tasks/` (9 files) | `BondTaskRow`, `BondTaskList`, `BondTaskForm`, `BondTaskQuickAdd`, `BondTaskSummaryCard`, `BondTaskDeleteControl` |
| S phone | `task_form`, `task_list`, `task_undo_line`, `entity_tasks_section` | the same widgets. The entity section is a `BondTaskList` filtered by link |
| A | `add_event_composer`, `event_draft_card`, `my_day_timeline` | `BondTaskForm`, `BondTodayList`, `BondDueLane` |

## 2. What the app supplies

- `today` (the person's wall date) and `now` (the instant). The widgets never read the clock. Pass a new `now` each
  minute (`TaskTicker.minutes`) so overdue and the sections stay right.
- Labels: `TaskLabels`, `CaptureLabels`, `SettingsLabels` (in `bond_tasks`), English defaults, one object each.
- Theme: `BondTokens` and `BondLabelsScope` from `bond_ui`. Colours are tokens only.
- Callbacks: row tap and "new task" go to the app's own routes. The form's `onSubmit` gives a `TaskDraft`.
- `BondTaskForm` sends no time zone. The page's save handler adds it: `api.create(draft, timeZone: zone)`.
- People for the assignee list: `[for (final p in directory) TaskAssignee(p.id, p.displayName)]`.
- Nothing opens over the page. Pickers, search results, delete confirmation and the banner expand inline. The repo's
  gate fails on dialogs, sheets, snack bars and tooltips.

## 3. The widgets

| Widget | Use |
|---|---|
| `BondTodayList(today, now, onTap, onComplete)` | the day view: Overdue, Today, No date, Done today with counts |
| `BondTaskList`, `BondTaskRow` | the full list, with sections Overdue, Today, Upcoming, No date, Done |
| `BondDueLane(tasks, day, now, ...)`, `BondDueMarker(count, overdue)` | a calendar day lane, and a count for a `BondMonthGrid` cell (`daySemantics`) |
| `BondStageBanner(task, stage, last, actions, onAction)` | inline banner for close, due, past with Done, Snooze, Cancel |
| `BondTaskForm(today, onSubmit, initial, assignees, onSearchLinks)` | all fields, priority, links, "Use my default" reminder |
| `BondCaptureReview(items, degraded, onAccept, onDiscard, linkSearch, dictation, now, today)` | review what capture found |
| `BondDictationSlot(builder)` | a place for the app's own dictation control |
| `BondTaskSettingsForm(settings, onSubmit, busy, zoneOptions)` | work day, lead minutes, zone (with `zoneOptions`), the quiet hours sentence |
| `BondPriorityChip`, `BondLinkChip`, `BondLinkPickerRow` | chips and the link picker |

Smallest page:

```dart
BondTodayList(today: today, now: now, onTap: openTask, onComplete: (t) => controller.complete(t.id));
// under a task that reached a stage:
BondStageBanner(task: task, stage: stageOf(task, prefs, now), onAction: (a) { /* NoticeAction */ });
```

Route the banner's action through the same handler as notices (`NoticeActionHandler.apply` in
`bond_tasks_notifications.md`) so Done, Snooze and Cancel behave the same on every path.

## 4. Words and rules to keep

- A task past its due instant shows "Overdue". An event in the past shows "Missed". Never "Overdue" on an event.
- A banner exists for `close`, `due` and `past` only. `upcoming` and none show nothing.
- Capture: a link set to "No match" is dropped from its item. The chosen match is first among its alternatives.
  `BondCaptureReview.onAccept` gives the edited items. An edit keeps every field the card does not show (an event's location, notes, duration and attendees; a task's notes); changing the kind carries the notes across. The app creates each one through the normal create call.
- Semantics ids: single widgets take `semanticsId`. Composite ones take `semanticsPrefix` and derive
  `<prefix>.row-<id>`, `<prefix>.complete-<id>`, `<prefix>.form-<part>`.

## 5. Call-site changes

| Old | New |
|---|---|
| S `taskDateString(DateTime)` | `dueDateString(DateTime)` |
| a date-only overdue badge | `BondTaskRow(now: ...)`: overdue follows `isOverdue` |
| A reminder pick list | `BondTaskForm` reminder with "Use my default" (-3) |

## 5a. Settings reset (adoption gaps)
`BondTaskSettingsForm` shows a quiet "Default" under a setting that follows the app default. Once the setting is in
`TaskSettings.overridden` it shows an inline "Reset to default" control instead. Tapping it calls `onSubmit` with a
`TaskSettingsPatch(reset: {field})`; the app sends it as the usual save. Keys: `task-settings-reset-<wire field>`; with a
`semanticsPrefix`, `<prefix>.settings-reset-zone`, `-start`, `-end`, `-lead`. Words: `SettingsLabels.resetToDefault`, `usingDefault`; screen reader names `resetTimeZone`, `resetWorkDayStart`, `resetWorkDayEnd`, `resetLeadMinutes`. The control is 48 high. An older server (no `overridden`) shows neither hint nor control. Save sends only the fields that changed or are already set, and does nothing when none changed (against an older server, which does not send `overridden`, Save sends every field as before). Keep `busy` true while a save or reset runs; when it ends with the field still overridden the reset counts as failed.

## 6. What to test

- `make -C packages/bond_tasks_ui test` and `analyze`: each widget at 1280 and 390 px.
- Walk `/tasks` in the demo (`docs/test/WEB.md`) against the example service: add with a priority, tick, complete,
  advance the fake clock past a stage and watch the banner and the badges change.
- No overflow at 390 px, no dialog, no console error.
