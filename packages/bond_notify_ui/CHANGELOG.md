# Changelog

## 0.1.0 - unreleased
- `BondNoticeRow`: title, body, relative time, unread and last-reminder marks, Done / Snooze / Cancel buttons
  (wire ids `done`, `snooze`, `cancel`), dismiss control. Takes `now` and `onDismiss`.
- `BondNoticeList`: header with unread count and Mark all read, inline loading, empty and error (with retry)
  lines, inline undo line under `undoNoticeId`. Takes `now`, `error`, `onRetry`, `onDismiss`, `onUndo`,
  `undoNoticeId`, and an optional `unreadCount` (the server number; null counts the loaded rows). Rows are keyed
  by notice id.
- `BondNoticeBadge`: parameter `count` is now `unread`, wraps an optional `child`, "99+" above 99; the `onTap`
  parameter is gone (the badge is not tappable).
- `noticeWhen`: pure relative-time function. `kNoticeActionOrder` is exported.
