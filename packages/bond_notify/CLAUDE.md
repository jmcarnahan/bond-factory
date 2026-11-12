# bond_notify
Role: Pure Dart inbox notices: `Notice` model, `NoticesApi` (REST), `NoticeFeed`, `NoticeController`, browser alert hook.

## Key files
- `lib/src/notice.dart` (`Notice`, `NoticePage`), `notices_api.dart` (`NoticesApi`).
- `lib/src/notice_feed.dart` (`NoticeFeed`), `polling_notice_feed.dart` (`PollingNoticeFeed`).
- `lib/src/notice_controller.dart` (`NoticeController`, `NoticeState`), `notice_labels.dart` (`NoticeLabels`).
- `lib/src/notice_alert*.dart` (`NoticeAlert`; conditional import: `_stub` elsewhere, `_web` on `dart.library.js_interop`).
- `lib/src/replay_stream.dart` (internal: broadcast stream that replays its last value).
- Shared fixtures: `../../fixtures/notify/notice.json`, `notices_page.json`.

## Commands
- `make test T=test/notice_test.dart`
- `make analyze`

## Rules
- No Flutter, no `dart:io` in lib. Framework-free: Streams, no ChangeNotifier. Tests use `MockClient`.
- `Notice` task fields live under the wire key `data`; the id is the one id on every delivery path (sync, local, push).
- Barrel + CHANGELOG.md updated on every public API change.
- No codegen; hand-write fromJson. 300-line soft cap per source file.
