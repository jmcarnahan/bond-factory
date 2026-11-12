# Migrating to bond_notify

Inbox notices for the apps (`packages/bond_notify`, pure Dart: `bond_json`, `bond_api`, no Flutter). The `Notice` model,
the REST client, the feed seam, a controller with optimistic read and dismiss, and the browser notification hook. Widgets
are in `bond_notify_ui.md`. Server half: `bond_notify_py.md`. Wire: `docs/contracts/notices.md`. Legend:
`docs/migration/README.md`. Order: `todo-checklist.md`.

## 1. What it replaces

Nothing in the three apps has a stored inbox, so there is nothing to delete. An app with its own notification list maps its
rows to `Notice` and swaps the REST calls for `NoticesApi`.

## 2. What the app supplies

- The server routes `GET /notices`, `POST /notices/{id}/read`, `/dismiss`, `/read-all` and `/act` (`bond_notify_py.md`).
- One feed. REST or sync, same controller:

```dart
final api = NoticesApi(apiClient);                         // prefix '/notices'
final controller = NoticeController(PollingNoticeFeed(api)); // polls every 30 seconds while someone listens
await controller.start();
controller.states.listen((s) => render(s.items, s.unreadCount, s.loading, s.error));
controller.markRead(id);  controller.dismiss(id);          // optimistic, revert on failure
await controller.markAllRead();
```

  With a sync store use `WatchNoticeFeed` from `bond_notify_powersync` (`bond_notify_powersync.md`) in place of
  `PollingNoticeFeed`. Nothing else changes.
- Task fields sit under `Notice.data`: `notice.taskId`, `stage`, `seq`, `dueAt`, `priority`, `route`, `actions`, `last`.
- Strings: `NoticeLabels`, English defaults. No other string is in the package.

## 3. The seam and the controller

- `NoticeFeed`: `watch()`, `refresh()`, `markRead`, `dismiss`, `markAllRead` (every notice, including ones the feed does not
  hold) and `serverUnreadCount` (the server's number when it can exceed the loaded page, null when the list is complete).
- `NoticeController`: `states`, `start`, `refresh`, `markRead`, `dismiss`, `markAllRead`, `dispose`. `newUnread` fires once
  per notice id, and only for a notice created in the last ten minutes, so a launch does not replay the inbox.
- `NoticesApi.act(id, action)` takes `'done'`, `'snooze'` or `'cancel'` and returns the notice and the task map. The
  alerts coordinator applies actions through the task repository instead (`bond_tasks_notifications.md`), which works
  offline with a sync store. Use `act` only for a REST-only app that has no coordinator.
- `NoticePage.fromJson` reads `{items, unread_count}`. Fixtures: `fixtures/notify/notice.json` and `notices_page.json`.

## 4. Browser notifications

`browserNoticeAlert()` returns a `NoticeAlert` (`requestPermission()`, `show(notice)`). Outside a browser it does
nothing. Feed `controller.newUnread` into it for web. Do NOT also feed `newUnread` into the phone coordinator's alert path:
the person would be told twice. Ask for permission on a user action, never at launch. About 30 lines of `dart:js_interop`
behind a conditional import. Not exercised in a real browser by the builders.

## 5. What to test

- `make -C packages/bond_notify test` and `analyze`.
- Round-trip the two fixtures through `Notice.fromJson` and `NoticePage.fromJson`.
- A fake `NoticeFeed`: a failed `markRead` puts the notice back unread, a failed `dismiss` brings the row back, and
  `newUnread` fires once for an id.
- With the example service: the inbox gains one notice per stage as the fake clock advances (`docs/test/WEB.md`, step 6 and 7).

## 6. Known limits

- The polling feed reads the first page only. `unreadCount` comes from the server and can exceed the rows.
- Web notifications need the browser's permission and a secure origin.
