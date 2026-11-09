# Changelog

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
- Every string comes from `TaskLabels`; no dialogs, sheets or snack bars.
- Semantics ids: single widgets take `semanticsId`; composite ones take a prefix (`semanticsPrefix`,
  `semanticsBase`) and derive `<prefix>.row-<id>`, `<prefix>.form-title` and so on.
- Dropped from the seed: the LLM parse preview, the loan picker, the inline editor, the undo line.
