# Changelog

## 0.1.0 - unreleased
- `Notice` and `NoticePage` (wire shape with task fields under `data`), `NoticesApi` (`list`, `read`, `dismiss`,
  `readAll`, `act`).
- `NoticeFeed` seam, `PollingNoticeFeed`, `NoticeController` and `NoticeState` (behaviour not implemented yet; the classes throw `UnimplementedError`).
- `NoticeAlert` and `browserNoticeAlert()` (conditional import; no-op for now), `PollingNoticeFeed` takes an optional `clock`, `NoticeLabels`.
