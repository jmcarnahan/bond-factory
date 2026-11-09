# SDK initial modules walk (2026-11-08)

What was walked: the shared SDK demo (`demos/sdk_demo`) against the example API (`services/sdk_example`, fake mode),
phases 1-3 of the initial-modules plan, commit 8af40b7 (round 1) and the walk fixes committed as 5437aa8 (round 2), per `docs/test/WEB.md`,
by a Sonnet walker with `@playwright/test` (headless Chromium).
Stack: `make serve-example` (:8012, fake mode, fresh `out/`) and `make demo-sdk-web` (:8078, debug web-server), both
started by the walk. Phone on web: the same demo at 390x844 for steps 2 and 7. Simulator: not booted (web-only plan).
Shots pass: skipped, no `make shots` target.

## Web (1280x800), round 1
| Step | User | Result | Note |
|---|---|---|---|
| 01 Home: seven route rows | demo-user-1 | PASS | |
| 02 UI: sections, inline select, two-step confirm | demo-user-1 | PASS | W1, W2 |
| 03 API: health, not-found, validation inline | demo-user-1 | PASS | |
| 04 Auth: sign in, chips, refresh, forced 401 (1 renewal), not_invited, sign out | demo-user-1 | PASS | |
| 05 Sync: 3 rows, 2 ok + 1 rejected, fix + resend, clock skew, token | demo-user-1 | FAIL | W3 (token: sync_off in fake mode) |
| 06 Connections: connect, expiry, reconnect, disconnect, both providers | demo-user-1 | PASS | W4 (error line under the banner) |
| 07 Tasks: quick add, full form, checklist, reminder notice, mirror id | demo-user-1 | PARTIAL | reopen, mirror off, delete not verified (W5, W6) |
| Dialogs/popups on every page visited | | 0 | |

## Phone on web (390x844), round 1
| Step | Lane | User | Result | Note |
|---|---|---|---|---|
| 02p UI at 390: no overflow, sections reachable, select inline | phone-on-web | demo-user-1 | PASS | |
| 07p Tasks at 390: no overflow, form and quick add reachable | phone-on-web | demo-user-1 | PASS | P1 |
| Console / runtime errors, popups | | | clean, 0 | only the deliberate 404/422/401/403/503 resource lines |

Previous walk's open items: none, first walk.

Defects (round 1):
- W1 (minor): `sdk.ui.table` not in the semantics tree at any scroll position on /ui.
- W2 (minor, unconfirmed): `sdk.ui.last-event` stayed "nothing yet" after the confirm flow.
- W3 (major): "Fetch token" on /sync showed `sync_off` (503) because fake mode had no sync endpoint by default.
- W4 (major): after every return from the fake consent page, /connections showed a `replaceState` TypeError line under the
  green banner (the js_interop call passed no arguments); the connection itself succeeded.
- W5 (minor): the "Add to my calendar" toggle label was struck through whenever checked, on the form and every row.
- W6 (unverified): complete/reopen clicks landed on different rows after the completed row moved to the Done section.
- P1 (minor): at 390 px the shell kept a 120 px side nav, leaving about 270 px for content.
- Doc: the semantics placeholder is already gone (the demo enables semantics itself); result texts exposed no label.

## Round 2 (re-walk of the failed and partial steps, fresh database)
| Step | Lane | User | Result | Note |
|---|---|---|---|---|
| 02 UI: `sdk.ui.table` present; confirm updates `sdk.ui.last-event` | web | demo-user-1 | PASS | W1, W2 fixed |
| 02p UI at 390: no overflow, nav strip under the page | phone-on-web | demo-user-1 | PASS | P1 fixed |
| 05 Sync: verdicts, fix + resend, skew, token with endpoint | web | demo-user-1 | PASS | W3 fixed |
| 06 Connections: both providers, expiry, reconnect, disconnect, no error line | web | demo-user-1 | PASS | W4 fixed |
| 07 Tasks: quick add, full form, checklist, complete/reopen, reminder notice, mirror on/off, delete | web | demo-user-1 | PASS | W5 fixed; W6 see open item |
| 07p Tasks at 390 | phone-on-web | demo-user-1 | PASS | |
| 08 Errors: dialogs 0, no pageerror, no console error, `sdk.errors` never seen | all | | PASS | |

Open item for a hand test (not reproduced in isolation): in one round-2 run the complete button still read "Complete"
after the first tap although the row had already moved to Done, and the second tap left it Done. A label lag or a tap
during the list reload; the isolated check (complete, reopen, complete on the same row id) passed both directions.

Walkability change made during the fix round: every `sdk.*` text node now exposes its visible text as the semantics
label (`container: true`, inner text excluded), so a walker reads the accessible name instead of screenshots.
Timing: round 1 about 55 minutes, round 2 about 25 minutes, both on the web lane with the phone lane inline (Playwright test runner, headless Chromium; roughly 90 and 60 driver calls).
