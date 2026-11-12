# iOS simulator walk recipe: demos/sdk_demo

How to prove, on the iOS simulator, the one step of the TODO walk that needs iOS itself: a local notification, its
permission prompt and its three buttons. Everything else is walked in the browser (`docs/test/WEB.md`). The demo is a
harness (never shipped). The example API is `services/sdk_example` in fake mode. Run everything from the repo root.
Phones are iOS only: there is no Android lane.

## Status

On 2026-11-11 the demo was built for the simulator (`flutter build ios --simulator --debug`), installed and launched on an iPhone 17
simulator, and rendered its home page. Steps 1 to 9 below (permission, notification, buttons, tap) have NOT been run, because no
tool could tap the simulator. They need a hand test. The first build runs `pod install` and writes `ios/Podfile.lock`.

## What this lane can and cannot prove

| Can | Cannot |
|---|---|
| The permission prompt, the grant, a local notification delivered with the title and body of a stage | A real Apple push. It needs an Apple push key, a bundle id registered with Apple and a physical phone |
| The two categories: Done and Snooze for everyone, Cancel too for the owner, each button opening the app | An Apple push with buttons. A remote notification carries none by design (the plugin cannot report the pressed button) |
| Done, Snooze and Cancel applied through the repository, and the notification cleared | The order of the two notification delegates (local and push plugin) on a device with push on |
| A tap opening the task route (`TodoAlerts.openedRoute`) | Delivery while the app is force-quit for a long time, battery and focus settings |

## Start

1. Example API in fake mode, backgrounded, pid saved under `tmp/logs/`: `make serve-example` (uvicorn on :8012).
   `curl -s localhost:8012/health` must return `"mode": "fake"`. The simulator reaches the host as `localhost`.
2. A booted simulator: `xcrun simctl list devices booted`. If none is booted, `xcrun simctl boot "<an iPhone name>"`, then
   `open -a Simulator`.
3. `demos/sdk_demo/ios` exists. Run it from `demos/sdk_demo`: `flutter run -d <simulator udid> --dart-define=SDK_EXAMPLE_URL=http://localhost:8012`.
   (`make demo-ios` at the root runs the roof demo, not this one.) The first build takes minutes.
4. Leave `SDK_DEMO_PUSH` unset. The demo then wires local notifications only, through `TaskAlertsCoordinator`. Push in the demo is off unless it is built with
   `--dart-define=SDK_DEMO_PUSH=true`. It needs the capability and a real key, and cannot work in the simulator.
5. In the app tap Auth, then Sign in with the fake Google provider (or open any TODO page: it falls back to the demo user).
   The coordinator starts after the sign-in.

## Driving the simulator

- Use the Mobile MCP tools (tap, type, screenshot) against the booted simulator, or `xcrun simctl io booted screenshot`.
  Flutter text controls are found by their accessible labels. The `sdk.*` ids are semantics identifiers: read the
  labels, not DOM attributes.
- Alerts appear as banners: open Notification Centre by swiping down from the top, and press and hold (or pull down) a
  notification to show its buttons.
- Reset the permission between runs by uninstalling the app (`xcrun simctl uninstall booted <bundle id>`) or erasing the
  simulator (`xcrun simctl erase <udid>`, while it is shut down).

## Walk (step 10 of the TODO walk)

The coordinator posts a synced notice at once when the app runs, so the fake clock gives a notification in seconds:
`POST /jobs/tick` makes the server claim the stage, and the polling feed brings the notice to the phone. A scheduled
local copy is also set for each stage at its real time.

1. **Permission.** Open the TODO settings page. Tap "Allow phone alerts" (`sdk.todo.alerts-permission`). The system prompt
   appears. Tap Allow. The page reads that alerts are allowed (`sdk.todo.alerts-state`). (Check the denial path once too: reset, tap Don't Allow,
   the page says not allowed and nothing crashes.)
2. **Create a TODO.** On Today create a timed TODO due 30 minutes after the fake clock, reminder "Use my default" (60
   minutes). Create two more the same way.
3. **Close stage notification.** On Today set the fake clock (`sdk.today.clock-now`) to 30 minutes before the due time and tap
   Tick (`sdk.today.clock-tick`: it pins the server clock, runs the sweep and refreshes; `sdk.today.clock-real` unpins). A notification "Due soon: ..." is delivered. Pull it down: three buttons, Done, Snooze, Cancel (the owner
   category `bond.task.owner`).
4. **Done.** Tap Done on the first. The app opens, the TODO is completed (it leaves Today), and the notification is cleared.
5. **Snooze.** On the second task tap Snooze. The notification is cleared and the TODO is unchanged. Tick the clock to the
   due time: the next stage (due now) still arrives.
6. **Cancel.** On the third task tap Cancel. The TODO is cancelled (it leaves Today) and the notification is cleared.
7. **Plain tap.** Make a fourth notification and tap its body: the app opens `/today` and shows `sdk.today.opened` ("Opened from a notification"; dismiss with `sdk.today.opened-dismiss`).
8. **No dialogs.** Besides the one system permission prompt, nothing opens over the page: no sheet, no alert, no snack bar.
   No red error strip (`sdk.errors`).
9. **Assignee.** A task assigned to someone who does not own it shows a notification with Done and Snooze only
   (category `bond.task`), no Cancel.

## If it fails

- No notification after Tick: the simulator denied permission (uninstall the app and retry), or the sweep did not claim the stage
  (read `POST /jobs/tick`'s `sweep` counts, and `GET /notices`).
- A tap does nothing: the notification-centre delegate was set after the plugins registered. The app delegate must set
  it before `GeneratedPluginRegistrant.register` (`docs/migration/bond_push.md`).
- Taps arrive twice: the same tap within 3 seconds is deduplicated. A second one after that is a real second tap.

## Cleanup

Kill the pids in `tmp/logs/` (`kill $(cat tmp/logs/sdk_example.pid)`) and confirm port 8012 is free. Stop the demo
with `q` in its terminal. State lives in `services/sdk_example/out/` (gitignored). To remove the simulator app:
`xcrun simctl uninstall booted <bundle id>`.
