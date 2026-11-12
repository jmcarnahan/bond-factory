# bond_tasks_ui

Task widgets for the bond apps (Flutter; depends on `bond_tasks` and `bond_ui`). Pure widgets: data and callbacks
in, no API calls, no clock reads. Import `package:bond_tasks_ui/bond_tasks_ui.dart`.

## Rules
- `today` (the person's wall date) and `now` (the instant) are always passed in. With `now`, "overdue" follows
  `isOverdue` and sections follow `sectionTasks`, so a screen that re-renders each minute stays right.
- Every string comes from `TaskLabels` (`bond_tasks`; `CaptureLabels`, `SettingsLabels` for capture and settings),
  with English defaults. Colours come from `BondTokens`.
- Nothing opens over the page: no dialogs, sheets, snack bars or tooltips. Pickers, search results, delete
  confirmation and the stage banner all expand inline.
- Single widgets take `semanticsId`; composite ones take `semanticsPrefix` and derive `<prefix>.row-<id>`,
  `<prefix>.complete-<id>`, `<prefix>.form-<part>`.
- A task is "overdue" once its due instant has passed; an event in the past is "missed".

## Widgets
- `BondTaskList(tasks, today, now?, onTap, onComplete, rowExtra)`: sections Overdue, Today, Upcoming, No date, Done.
- `BondTaskRow(task, now?, onTap, onComplete)`: one task: complete button, title, due text, priority chip.
- `BondTodayList(today: TaskToday, now, onTap, onComplete)`: the day view; Overdue, Today, No date, Done today
  with counts; each task in exactly one section, decided by `now`.
- `BondDueLane(tasks, day, now, onTap, onComplete)`: one calendar day for a day view; timed tasks with local time.
- `BondDueMarker(count, overdue)`: a small count for a `BondMonthGrid` cell (pass `daySemantics` to the grid).
- `BondStageBanner(task, stage, last, actions, onAction)`: inline banner for close, due and past stages with
  Done, Snooze and Cancel task; nothing for `none` and `upcoming`.
- `BondTaskForm(today, onSubmit, initial, assignees, onSearchLinks)`: title, notes, date, time, assignee,
  priority, links, checklist, reminder (including "Use my default"), calendar mirror.
- `BondTaskQuickAdd`, `BondChecklist`, `BondTaskChecklistEditor`, `BondCheckRow`: one-line add and checklists.
- `BondTaskSummaryCard`, `BondTaskDeleteControl`: counts and an inline two-step delete.
- `BondPriorityChip(priority)`, `BondLinkChip(link, onTap, onRemove)`, `BondLinkPickerRow(links, onSearch, onChanged)`.
- `BondCaptureReview(items, degraded, onAccept, onDiscard, linkSearch, dictation, now, today)`: review what
  natural-language capture found: edit title, kind, date, time, priority and link match; Accept returns the edits.
- `BondDictationSlot(builder)`: a place the app fills with its own dictation control.
- `BondTaskSettingsForm(settings, onSubmit, busy)`: work day start and end, lead minutes, zone, quiet hours text.
- Helpers: `dueDateString`, `parseDueDate`, `parseDueTime`, `dueTimeString`, `sectionOf`, `formatDue`,
  `formatTimeOfDay`.

## A Today page
```dart
class _TodayState extends State<TodayPage> {
  late final c = TaskController(widget.repo)..load();
  late final ticker = TaskTicker();
  DateTime now = DateTime.now().toUtc();
  @override Widget build(BuildContext context) => StreamBuilder<DateTime>(
    stream: ticker.minutes, // a new `now` each minute re-sorts overdue
    builder: (_, tick) => StreamBuilder<TaskControllerState>(
      stream: c.states,
      builder: (_, s) {
        final today = s.data?.today;
        if (today == null) return const BondLoadingState();
        return BondTodayList(today: today, now: tick.data ?? now,
            onTap: widget.onOpen, onComplete: (t) => c.complete(t.id));
      }));
}
// Under a task that has reached a stage:
BondStageBanner(task: task, stage: stageOf(task, prefs, now), onAction: (a) {
  if (a == NoticeAction.done) c.complete(task.id);
});
```

## Capture review
```dart
BondCaptureReview(
  items: parsed.items, degraded: parsed.degraded, now: now, today: today,
  linkSearch: linkSearch, // a LinkSearch; optional
  onDiscard: () => setState(() => parsed = null),
  onAccept: (items) {
    for (final i in items.whereType<TaskCandidate>()) {
      final links = [for (final l in i.links) TaskLink(kind: l.kind, id: l.candidates.first.id)];
      repo.create(i.toDraft(links: links));
    }
  });
```
A link set to "No match" is dropped from its item; the chosen match is first among its alternatives.
