# Migrating to bond_notify_ui

Notice widgets (`packages/bond_notify_ui`, Flutter: needs `bond_notify`, `bond_ui`): an inbox list, a row with action
buttons and an unread badge. Pure widgets: tokens only, no popups, every string from `NoticeLabels`, no clock reads.
The headless layer is `bond_notify.md`. Legend: `docs/migration/README.md`. Order: `todo-checklist.md`.

## 1. What it replaces

No app has an inbox widget today, so nothing goes away. An app with its own notification list swaps the list body for
`BondNoticeList` and keeps its screen.

## 2. What the app supplies

- `now` (the instant) on every call. The widgets never read the clock. Pass a fresh `now` each minute so "5 min ago" stays right.
- A `NoticeController` (or any list of `Notice`) and its state.
- Labels (`NoticeLabels`) and the theme (`BondTokens`, `BondLabelsScope`).
- Handlers: `onOpen` goes to the app's route, `onDismiss` and `onMarkAllRead` call the controller, `onAction` calls the one
  action handler.
- A place for the list. `BondNoticeList` does not scroll: put it in the page's scroll view.

## 3. Smallest working example

```dart
StreamBuilder<NoticeState>(
  stream: controller.states,
  initialData: const NoticeState(loading: true),
  builder: (context, snap) {
    final s = snap.data!;
    return SingleChildScrollView(
      child: BondNoticeList(
        notices: s.items, unreadCount: s.unreadCount, now: DateTime.now(), loading: s.loading, error: s.error,
        onRetry: controller.refresh, onOpen: (n) => router.openTask(n.taskId),
        onDismiss: (n) => controller.dismiss(n.id), onMarkAllRead: controller.markAllRead,
        onAction: onNoticeAction, semanticsPrefix: 'app.inbox',
      ),
    );
  },
);
```

The badge: `BondNoticeBadge(unread: s.unreadCount, child: inboxButton)`. It shows nothing at 0 and "99+" above 99, and it is not
tappable, so wrap it in the button that opens the inbox. `unreadCount` is the server's number and can exceed the loaded rows.

## 4. The three actions

`onAction(notice, wire)` gets `'done'`, `'snooze'` or `'cancel'`, the same ids as the phone buttons. A row shows one button
per entry of `notice.actions`, in the order done, snooze, cancel, so a recipient who may not cancel sees no Cancel. Send all
three to the handler the notifications use, so they behave the same everywhere:

```dart
void onNoticeAction(Notice n, String wire) {
  final action = NoticeAction.fromWire(wire);              // from bond_tasks
  final taskId = n.taskId;
  if (action != null && taskId != null) handler.apply(n.id, taskId, action);  // NoticeActionHandler
}
```

For the undo line ("Marked done. Undo") remember the notice id after Done, pass it as `undoNoticeId` and clear it after a
few seconds or when `onUndo` fires. The row marks the final past notice with "Last reminder".

## 5. What to test

- `make -C packages/bond_notify_ui test` and `analyze`. Each widget at 1280 and 390 px.
- A notice with `actions: ['done', 'snooze']` shows no Cancel. Tapping the text calls `onOpen` only.
- Semantics ids: row `<prefix>.row-<id>`, buttons `<row id>-done`, `-snooze`, `-cancel`, `-dismiss`, list
  `<prefix>.mark-all`, `.retry`, `.undo`.
- Walk the demo inbox (`docs/test/WEB.md`): same actions, same results as the stage banner.
