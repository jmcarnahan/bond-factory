# bond_notify

Inbox notices for the bond apps. Pure Dart (`bond_json`, `bond_api`), no Flutter.

```dart
final api = NoticesApi(apiClient); // prefix '/notices'
final controller = NoticeController(PollingNoticeFeed(api));
await controller.start();
controller.states.listen((s) => print(s.unreadCount));
```

- `Notice` is the wire shape of `GET /notices` (`fixtures/notify/notice.json`); task fields sit under `data`.
- `NoticesApi`: `list`, `read`, `dismiss`, `readAll`, `act(id, action)`.
- `NoticeFeed` is the seam: `PollingNoticeFeed` polls the REST API; a sync-store feed lives in `bond_notify_powersync`.
- `NoticeController`: optimistic read and dismiss with revert; `newUnread` fires once per id.
- `browserNoticeAlert()` is the web notification hook (a no-op outside a browser).
- `NoticeLabels` holds every user-visible string, English defaults.
