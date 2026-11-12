# Adoption gaps walk (2026-11-12)

What was walked: the adoption-gaps build (wave A and wave B), commit 6ef1974, per docs/test/WEB.md "TODO checklist
walk" (steps 2, 4, 5, 5a, 6, 12, 13) and its error check, by one Sonnet walker.
Stack: `make serve-example` (:8012, fake mode, state reset) and `make demo-sdk-web` (:8078, debug build).
Driver: Playwright from node scripts in a scratch copy of `demos/sdk_demo/e2e`, headless Chromium; no MCP driver was
available. Each script opened a fresh browser context as the demo user. Phone on web: the same demo at a plain 390x844
viewport. Simulator: not booted (the build changed nothing that needs iOS itself).
Shots pass: skipped: no make shots target.

## Web (1280x800)
| Step | User | Result | Note |
|---|---|---|---|
| 01 Settings, fresh page: default hints, no reset control | demo | PASS with a note | "Default" under start, end and lead. `settings-reset-zone` IS present: the device zone is stored at sign-in, so the zone is the person's own value (`overridden` = `time_zone`). The step's expectation was wrong, not the page |
| 02 Change only the end of day to 18:00 and save | demo | PASS | The PUT carried `end_of_day` and the already-set `time_zone`, not start or lead; `reset-end` appeared, `reset-start` and `reset-lead` did not |
| 03 Reset the end of day | demo | PASS | PUT `{"end_of_day": null}`; the field read 17:00, the control became "Default", `overridden` lost `end_of_day`, a date-only task's `due_at` moved from 18:00 to 17:00 local; no dialog |
| 04 Fake clock: pin, overdue, release | demo | PASS | `GET /fake/clock` gave the pinned instant; the task moved to Overdue; Real time gave `now: null` |
| 05 Stages, then Done and Snooze on inbox notices | demo | PASS | One notice per stage; Done completed the task and put away its notices (served by the notices router); Snooze marked the notice read and left the task open |
| 06 Capture: parse, review, accept; rich parse through the API | demo | PASS | Parsing created nothing; "Events sent: 1"; with `rich: true` the event carried location, notes, duration_minutes and attendees; the default answer had none of those keys |
| 07 Calendar: grid labels, due lane, accepted event, clock line | demo | PASS | Labels read "12, 5 due" and, under the pinned clock, "12, 5 overdue" (W3) |
| 08 `/tasks` and `/ui` render; corners still rounded | demo | PASS | Judged from screenshots (computed radius is not exposed on semantics nodes); a banner was not captured |
| 09 `/auth` page | demo | PASS | Signed in; no error strip; no provider sign-in started |
| Dialogs/popups on every page visited | | 0 | No page error; one expected console 401 on a fresh signed-out load |

## Phone
| Step | Lane | User | Result | Note |
|---|---|---|---|---|
| 01 Settings, fresh page | phone on web 390x844 | demo | PASS with a note | Same as the web lane |
| 03 Reset the end of day; control height | phone on web 390x844 | demo | PASS | The reset control is 48 px high; same PUT and result |
| 05 Done on an inbox notice | phone on web 390x844 | demo | PASS | Task done, its two notices gone, unread 4 to 2 (P2) |
| 06, 07, 08, 09 | phone on web 390x844 | demo | PASS | Same results; nothing overflows (scrollWidth equals the viewport) |
| Console / runtime errors, popups | | | clean, 0 | |

Previous walk's open items (2026-11-11 TODO checklist): not re-walked. Simulator steps past launch are still a hand test.

Defects:
- W2 (copy): after a reset the page still shows the "Settings saved" line from the earlier save. A reset is also a save,
  so the text is true, but it does not change to confirm the reset.
- W3 (minor): the accepted all-day event on `/calendar` had no `sdk.calendar.event-<n>` id in the semantics tree, although
  the recipe lists it. Not changed by this build; not investigated.
- P2 (minor): the inbox Done and Snooze buttons are 44 px high at 390, under the 48 px tap target. Not changed by this build.
The screenshots were deleted at cleanup.

Timing: about 40 minutes and 45 calls in total (about 28 calls at 1280, 12 at 390).
