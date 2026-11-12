# sdk_demo

Flutter web harness for the bond SDK packages (plus an iOS runner for the phone alerts). Never shipped.
Twelve pages: Home lists the routes, UI is the `bond_ui` widget gallery, API probes health and errors,
Sign in (`/auth`) runs direct sign-in against the example's fake providers (system-browser round trip, cookie
session, renew, replayed-token sign-out, break-glass form behind a server flag), Sync uploads rows with
per-row verdicts, Connections runs the fake OAuth round trip and the role scope ask card, and Tasks manages
tasks with a calendar mirror and a fake-clock job run. Wiring is shown in `docs/sdk/examples.md`; the browser walk recipe is
`docs/test/WEB.md`.

## The TODO checklist pages (all against `services/sdk_example` in fake mode)

| Route | Page | What it shows |
|---|---|---|
| `/today` | Today | `BondTodayList` over `TaskController` + `RemoteTaskRepository`; `BondStageBanner` (Done, Snooze, Cancel task; no Cancel for a non-owner); inline Undo after Done; `BondTaskForm` with priority and a contact link; the fake-clock strip |
| `/capture` | Capture | text, `POST /tasks/parse`, `BondCaptureReview` (flip task/event, edit, degraded and dropped notices), Accept creates tasks and sends events to `POST /capture/events`; a fake-mode switch calls `PUT /fake/capture` (model off) |
| `/calendar` | Calendar | `BondMonthGrid` with `BondDueMarker` cells, `BondDueLane` for the selected day, accepted events (past ones read "Missed") |
| `/todo-settings` | TODO settings | `BondTaskSettingsForm` over `GET/PUT /tasks/settings` (quiet hours in words, warnings), a zone field, the iOS permission button |
| `/inbox` | Inbox | `BondNoticeList` + `BondNoticeBadge`; switch between the polling feed and the watch feed (an in-memory `FakeSyncDb` the page fills from `GET /notices` and writes read/dismiss back to REST); row actions via `POST /notices/{id}/act`; browser alert on web |

- Fake clock (Today and Inbox, fake mode): type an ISO instant, press Tick. It calls `POST /jobs/tick {now}`,
  moves every TODO page's clock there and re-reads. Real time returns on reload.
- Alerts: `TaskAlertsCoordinator` is the only alert wiring (`lib/src/todo/todo_alerts.dart`). `main()` hooks it
  to sign-in and sign-out; the settings page calls `updatePrefs`. On web the local-notification plugin is a no-op.
  Apple push is off unless built with `--dart-define=SDK_DEMO_PUSH=true`.
- iOS: `ios/` was made by `flutter create --platforms=ios .` (bundle id `com.example.sdkDemo`, no team, no
  signing). `AppDelegate.swift` sets the notification-center delegate before plugins register. Add the Push
  Notifications capability yourself for push. Nothing here builds or runs a simulator.
- Test rig: `test/todo_rig.dart` (canned HTTP, `TodoServices`, fixed clock 2026-03-12 16:00 UTC). Tests run with
  `TZ=America/Los_Angeles` (the Makefile sets it).
