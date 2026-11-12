# bond_notify_ui
Role: Flutter notice widgets over bond_notify and bond_ui: list, row with actions, badge.

## Key files
- `lib/bond_notify_ui.dart` is the barrel; code is in `lib/src/`.
- `bond_notice_row.dart`, `bond_notice_list.dart`, `bond_notice_badge.dart`; `notice_when.dart` (pure `noticeWhen`).
- Tests: `test/support.dart` (`pumpAt` at 1280 and 390, `atBothWidths`, `byId`); one test file per source file.
- Strings live in `NoticeLabels` (packages/bond_notify/lib/src/notice_labels.dart).

## Commands
- `make test T=test/notice_row_test.dart`
- `make analyze`

## Rules
- No popups, dialogs, sheets, tooltips or snack bars. No raw colours (use BondTokens). No intl, riverpod, go_router.
- Every user-visible string comes from `NoticeLabels`. `now` is a parameter: never read the clock.
- Every tappable has a semantics id. Depends on bond_notify and bond_ui only.
- Actions are wire ids `done`, `snooze`, `cancel`, shown in that order; unknown ids are ignored.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
