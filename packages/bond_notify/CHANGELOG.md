# Changelog

## 0.1.0 - unreleased
- `Notice` and `NoticePage` (wire shape with task fields under `data`), `NoticesApi` (`list`, `read`, `dismiss`,
  `readAll`, `act`). `act` returns a `NoticeActResult { notice, task }` so the task is not dropped.
- `NoticeFeed` seam and `PollingNoticeFeed` (polls the first page of 50 while listened to; replays the last list;
  drops a stale answer; errors go to the stream and polling continues; `clock` stamps a local read).
- `NoticeController` and `NoticeState`: replaying `states`, optimistic `markRead` and `dismiss` with revert and
  `error`, and `newUnread`: each id once, only for unread notices created within `fresh` (default 10 minutes,
  by the controller's `clock`) of now; a notice with no `createdAt` never alerts. Constructor:
  `NoticeController(feed, {fresh, clock})`.
- `NoticeFeed` gains `markAllRead()` and `int? get serverUnreadCount` (null when the feed holds every row).
  `PollingNoticeFeed` carries the server's `unread_count` (more than the 50 held) and implements `markAllRead`
  through `NoticesApi.readAll`. `NoticeController` gains `refresh()` (errors go to `state.error`) and
  `markAllRead()` (optimistic, reverts on failure), and its badge uses the server count when there is one.
- `make test-web` compiles the browser alert with dart2js (`tool/web_check.dart`); not part of `make test`.
- `NoticeAlert` and `browserNoticeAlert()`: on web the browser Notification API through `dart:js_interop` (shown
  only when permission is granted and the page is hidden; the tag is the notice id); a no-op elsewhere.
- `NoticeLabels`, now also with `loading`, `loadError`, `retry`, `dismiss`, `unread`, `markedDone`, `justNow`,
  `yesterday`, `minutesAgoSuffix`, `hoursAgoSuffix`, `monthsShort` and the methods `minutesAgo`, `hoursAgo`,
  `dateText` (existing fields unchanged).
