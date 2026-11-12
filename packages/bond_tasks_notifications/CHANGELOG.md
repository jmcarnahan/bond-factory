# Changelog

## 0.1.0 - unreleased
- First API: local alerts for open tasks (`LocalTaskAlerts`), the iOS plugin (`FlutterLocalAlertPlugin`),
  `NoticeActionHandler`, `TaskAlertsCoordinator`, `FlutterTimeZoneSource`, `AlertLabels`, and `FakeAlertPlugin`
  in `testing.dart`.
- Two iOS categories: `kNoticeCategory` (Done, Snooze) and `kNoticeCategoryOwner` = 'bond.task.owner'
  (adds Cancel); `categoryFor(AlertRequest)` picks one from the request's actions.
- `updatePrefs(TaskPrefs)` on `LocalTaskAlerts` and the coordinator; `NoticeActionHandler` takes `isGone`
  (default `defaultIsGone`: a vanished task still puts the notice away); a notice whose scheduled copy
  already fired is not shown again; `cancelAll()` stops listening until `start()`; identical taps within 3 s
  are handled once; `freshFor` defaults to 10 minutes.
- `AlertPlugin.active()` (ids of delivered, still shown notifications); `FakeAlertPlugin.activeIds`.
  A notice already on screen is not shown again.
- `start()` and `resume()` refresh the repository and the feed (guarded); `TaskAlertsCoordinator.signOut()`;
  the coordinator never disposes the `PushRegistrar`; an alert is rescheduled when its title, body, actions,
  route or time changed; a failing `pending()` skips the sync; a concurrent second `start()` waits for the first.
- `LocalTaskAlerts` takes `clock`, `labels`, `onError`; `onNoticeArrived(notice, {postNow})`; `cancelAll()`; `dispose()`.
- `TaskAlertsCoordinator` takes `postNow`, `handledElsewhere`, `budget`, `perTask`, `freshFor`, `stages`; `resume()`.
