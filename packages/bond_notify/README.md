# bond_notify

Inbox notices for the bond apps. Pure Dart (`bond_json`, `bond_api`), no Flutter, no `dart:io`. State is exposed as
Streams. Widgets are in `bond_notify_ui`. The server half is `libs/bond_notify_py`. Wire: `docs/contracts/notices.md`.
Migration note: `docs/migration/bond_notify.md`.

## Parts
- `Notice`: the wire shape of `GET /notices` (`fixtures/notify/notice.json`). Top-level keys `id`, `user_id`, `kind`,
  `title`, `body`, `data`, `created_at`, `read_at`, `dismissed_at`. The task fields sit under `data`: `task_id`, `stage`
  (`close`, `due`, `past`), `seq`, `due_at`, `priority`, `route`, `actions` (a subset of `done`, `snooze`, `cancel`), `last`.
  `Notice` exposes them as `taskId`, `stage`, `seq`, `dueAt`, `priority`, `route`, `actions`, `last`, and `unread`.
- `NoticePage`: `{items, unread_count}`, the list envelope.
- `NoticesApi(client, {prefix: '/notices'})`: `list({unread, limit, before})`, `read`, `dismiss`, `readAll` (returns the new
  unread count), `act(id, action)` (`'done'`, `'snooze'`, `'cancel'`; returns the notice and the task map).
- `NoticeFeed` is the seam: `watch()`, `refresh()`, `markRead`, `dismiss`, `markAllRead`, `serverUnreadCount` (null when
  the list is complete), `dispose()`. `PollingNoticeFeed(api, {interval: 30 s})` polls the REST API while someone listens.
  A sync-store feed lives in `bond_notify_powersync`.
- `NoticeController(feed, {fresh: 10 min, clock})`: `states` (a stream, there is no synchronous `state` getter; it replays the current `NoticeState`: `items`, `unreadCount`,
  `loading`, `error`), `start()` (returns before the first read lands: the first state is `loading` with no items, wait for `loading == false`), `refresh()`, `markRead`, `dismiss`, `markAllRead`, `dispose()`. Read and dismiss are
  optimistic and revert on failure. `newUnread` fires once per notice id, and only for a notice created within `fresh`.
- `NoticeLabels`: every user-visible string, English defaults (inbox title, empty, mark all read, Done, Snooze, Cancel
  task, Undo, Last reminder, unread count, loading, retry, relative times). No other string is in the package.
- `browserNoticeAlert()` returns a `NoticeAlert` (`requestPermission()`, `show(notice)`). It uses `dart:js_interop` behind a
  conditional import and is a no-op off the web.

## Example
```dart
final api = NoticesApi(apiClient); // prefix '/notices'
final controller = NoticeController(PollingNoticeFeed(api));
await controller.start();
controller.states.listen((s) => print('${s.items.length} notices, ${s.unreadCount} unread'));
controller.newUnread.listen(browserNoticeAlert().show); // web only; ask requestPermission() on a user action
await controller.markRead('4bef1b8888fef279d89a41fdbd63b326'); // optimistic, reverts on failure
await controller.markAllRead();
controller.dispose();
```

## Rules
- Do not also feed `newUnread` into the phone alerts coordinator's path: the person would be told twice.
- Tests: `make test`. A fake `NoticeFeed` is enough; no network.
