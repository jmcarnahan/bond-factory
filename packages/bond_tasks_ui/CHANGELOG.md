# Changelog

## 0.2.0 - unreleased
- `BondTaskFormDue.onTimeValid` (internal); `BondTaskForm` disables Save while the time box holds an invalid time.
- `BondTaskRow` shows up to 3 link chips and "+N"; `onLinkTap` on the row, `BondTaskList`, `BondTodayList`.
- `BondTaskSettingsForm.zoneOptions` (`List<String>?`): choose the zone inline; capture cards carry `<prefix>.review-item-<n>`.
Removed
- Uses of `Task.remindAt` / `remindedAt`. Changed: a new task in `BondTaskForm` starts at "use my default" (-3).

- Not exported (internal splits): `BondTaskFormDue`, `BondTaskFormExtras`, `BondCaptureLinkRow`, `BondCaptureWhen`.
- `sectionOf(..., now:)` is exactly `sectionTasks`; `BondStageBanner` draws nothing for `upcoming`; a time needs a
  date in the capture card (no "Add a time" without a date, Accept refuses it); the capture card reads a UTC `now`
  in the local zone; `BondTaskSettingsForm` follows settings that load later unless the person edited; rows in
  the lists carry the task id as key. `make test` sets `TZ=America/Los_Angeles`.
- New widgets: `BondPriorityChip`, `BondLinkChip`, `BondLinkPickerRow`, `BondTodayList` (Overdue, Today, No date,
  Done today with counts), `BondDueLane` (one calendar day), `BondDueMarker` (a count for a `BondMonthGrid` cell),
  `BondStageBanner` (inline, with Done, Snooze, Cancel task), `BondCaptureReview`, `BondCaptureItemCard`,
  `BondCaptureLinkRow`, `BondDictationSlot`, `BondTaskSettingsForm`.
- The capture card edits date, time and priority inline (`BondCaptureWhen`: the date field, the time field, "Add a
  time" / "Remove time", and an all-day switch for an event that clears the time); a new date clears "date guessed".
  `BondCaptureReview` and `BondCaptureItemCard` take an optional `today`.
- `BondTaskForm` gains priority (none, low, normal, high), links (`onSearchLinks`) and the reminder choice "Use my
  default" (-3); the due part and the priority and links part are now `BondTaskFormDue` and `BondTaskFormExtras`.
- `BondTaskRow` and `BondTaskList` take an optional `now`: overdue then follows `isOverdue`, not the stale flag. A
  row shows a chip for a high or low priority. `sectionOf(..., {now})`; `formatDue` shows a timed task's instant in
  the device zone; new `formatTimeOfDay`.
- Labels (in `bond_tasks`): `TaskLabels.remindDefault` now reads "Use my default"; new strings for priority, links,
  the day views and markers; `CaptureLabels` and `SettingsLabels` gain a few strings.

## 0.1.0 - unreleased
- `BondTaskRow`, `BondTaskList` (sections overdue, today, upcoming, no date, done; empty, loading and error
  states), `BondTaskForm` (title, notes, date, time, assignee, checklist, reminder, mirror; inline validation),
  `BondTaskQuickAdd`, `BondChecklist`, `BondTaskChecklistEditor`, `BondTaskSummaryCard`, `BondTaskDeleteControl`
  (inline two-step), `BondCheckRow`, and the helpers `dueDateString`, `parseDueDate`, `parseDueTime`,
  `dueTimeString`, `sectionOf`, `formatDue`.
- The form's reminder choices: none, morning of, 1, 15, 60 and 1440 minutes before.
- The form blocks a title over 255 characters with an inline message, and keeps a due date or time it cannot read
  (shown as unrecognised, sent back unchanged until the person picks or clears one). `parseDueDate` rejects
  impossible dates such as 2026-13-45.
- `BondCheckRow.strikeWhenChecked` (new, default false). Before it, every checked row was struck through; now only
  `BondChecklist` lines are, so the mirror switch is not.
- `BondTaskRow` always gives its body the task title as the semantics label (before, only when `onTap` was set).
- Every string comes from `TaskLabels`; no dialogs, sheets or snack bars.
- Semantics ids: single widgets take `semanticsId`; composite ones take a prefix (`semanticsPrefix`,
  `semanticsBase`) and derive `<prefix>.row-<id>`, `<prefix>.form-title` and so on.
- Dropped from the seed: the LLM parse preview, the loan picker, the inline editor, the undo line.
