# bond_notify_ui

Flutter notice widgets over `bond_notify` and `bond_ui`: an inbox list, a row with action buttons, and an unread
badge. Tokens only, no popups, every string from `NoticeLabels` (English defaults), no clock reads.

## Widgets

- `BondNoticeRow(notice, now, onOpen, onAction, onDismiss, labels, semanticsId)`: unread mark, title, body (two
  lines), relative time, a "Last reminder" mark when `notice.last`, one button per entry of `notice.actions` in
  the order done, snooze, cancel (unknown ids are ignored), and a dismiss control. Tapping the text calls `onOpen`.
- `BondNoticeList(notices, now, loading, error, onRetry, unreadCount, onOpen, onAction, onDismiss, onMarkAllRead, onUndo,
  undoNoticeId, labels, semanticsPrefix)`: header (title, unread count, Mark all read), rows, and inline loading,
  empty and error lines. When `undoNoticeId` names a row, "Marked done. Undo" shows under it. It does not scroll;
  put it in the page's scroll view.
- `BondNoticeBadge(unread, labels, semanticsId, child)`: a count over the top right of `child` (or alone). Hidden
  at 0, "99+" above 99, accessible name from `labels.unreadCount(n)`. It is not tappable; wrap it in the button
  that opens the inbox.
- `noticeWhen(createdAt, now, labels)`: the relative time text (just now, N min ago, N h ago, yesterday, a date).

## Example

```dart
final controller = NoticeController(feed)..start();

StreamBuilder<NoticeState>(
  stream: controller.states,
  initialData: const NoticeState(loading: true),
  builder: (context, snap) {
    final s = snap.data!;
    return SingleChildScrollView(
      child: BondNoticeList(
        notices: s.items,
        unreadCount: s.unreadCount,
        now: DateTime.now(),
        loading: s.loading,
        error: s.error,
        onRetry: controller.refresh,
        onOpen: (n) => router.openTask(n.taskId),
        onDismiss: (n) => controller.dismiss(n.id),
        onMarkAllRead: controller.markAllRead,
        onAction: onNoticeAction,
        semanticsPrefix: 'app.inbox',
      ),
    );
  },
);
```

`unreadCount` is the server's number, which can exceed the loaded rows; leave it null to count the loaded rows.
`BondNoticeBadge(unread: s.unreadCount, child: ...)` takes the same number. Rows are keyed by notice id.

## Mapping actions to your handler

`onAction` gets the notice and the wire id: `'done'`, `'snooze'` or `'cancel'` (the same ids as the phone
notification buttons). Route all three through the one handler the app already uses for notifications
(`NoticeActionHandler.apply` in `bond_tasks_notifications`), so they behave the same on every path:

```dart
void onNoticeAction(Notice n, String wire) {
  final action = NoticeAction.fromWire(wire); // from bond_tasks
  final taskId = n.taskId;
  if (action != null && taskId != null) handler.apply(n.id, taskId, action);
}
```

For the undo line, remember the notice id after Done, pass it as `undoNoticeId`, and clear it after a few seconds
or when `onUndo` fires.

## Semantics ids

Row `<prefix>.row-<id>`, its buttons `<row id>-done`, `-snooze`, `-cancel`, `-dismiss`; list `<prefix>.mark-all`,
`<prefix>.retry`, `<prefix>.undo`.
