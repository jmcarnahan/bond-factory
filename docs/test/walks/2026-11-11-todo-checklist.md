# TODO checklist walk (2026-11-11)

What was walked: the TODO checklist build (plan phases 1 to 3: libraries, packages, example service, demo),
commit 99012b7, per docs/test/WEB.md "TODO checklist walk" and docs/test/MOBILE.md, by one Sonnet walker.
Stack: `make serve-example` (:8012, fake mode, state reset) and `make demo-sdk-web` (:8078, debug build).
Driver: Playwright from node scripts (`demos/sdk_demo/e2e/node_modules`), headless Chromium; no MCP driver
was available. Phone on web: the same demo at a plain 390x844 viewport. Simulator: iPhone 17, iOS 26.5,
build and launch only (no tool could tap the simulator).
Shots pass: skipped: no make shots target.

## Web (1280x800)
| Step | User | Result | Note |
|---|---|---|---|
| 01 Today by hand: priority, link, due today | demo | FAIL | Row shows the High chip but no link chip; the API returns the link (W1) |
| 02 Capture: three drafts, flip, accept | demo | PASS | Parsing alone created nothing; "Created 2 tasks and sent 1 event" |
| 03 Capture with the model off; rate limit | demo | PASS | One degraded draft, no error; limit 0 shows an inline 429 text (W3) |
| 04 Calendar: marker, due lane, event, "Missed" | demo | PASS | A past event reads "Missed", never "Overdue" |
| 05 Settings: end of day, zone | demo | PASS | Date-only due time follows both; with no stored zone it was computed in UTC (W2) |
| 06 Stages: due soon, due now, overdue | demo | PASS | One notice per stage; badge equals the unread count |
| 07 Inbox: polling and watch feeds | demo | PASS | Same rows; read and dismiss persist across a feed switch |
| 08 Complete and undo | demo | PASS | Notices put away, no notice on later ticks, Undo reopens |
| 09 Same instant twice | demo | PASS / SKIP | One notice per stage; the push half is SKIP (the web demo registers no device) |
| 12 Done, Snooze, Cancel on row and banner | demo | PASS | Same results in both places; the next stage still arrives after Snooze |
| 12 Assignee sees no Cancel | second user | PASS | Row and banner show Done and Snooze only |
| 13 Today to Overdue as the clock passes | demo | PASS | List, header count, calendar marker and lane together |
| 14 Past-due series | demo | PASS | Five mornings, the fifth says it is the last reminder, none after |
| 15 Quiet hours in words; evening task | demo | PASS | Date-only notice moves with the end of day; a 21:00 task alerts at 20:30 |
| Dialogs/popups on every page visited | | 0 | No page error; one expected console 401 on the first signed-out load |

## Phone
| Step | Lane | User | Result | Note |
|---|---|---|---|---|
| 01 Today by hand | phone on web 390x844 | demo | FAIL | Same as web (P1 = W1) |
| 02 Capture | phone on web | demo | PASS | Controls reachable by scroll |
| 06 One stage | phone on web | demo | PASS | |
| 07 Two feeds | phone on web | demo | PASS | |
| 12 Row actions | phone on web | demo | PASS | Every button inside the 390 px width |
| Five pages: overflow, dialogs | phone on web | demo | PASS | No overflow message; body width reads 468 on the settings page with nothing visibly cut (P2) |
| 10 Build, install, launch | simulator | none | PASS | `flutter build ios --simulator --debug` succeeded; the app launched and rendered the home page |
| 10 Permission prompt, notification, three buttons, tap | simulator | | SKIP | No tool to tap the simulator in this session; needs a hand test |
| Console / runtime errors, popups | | | clean, 0 | |

Previous walk's open items: none for this feature (first walk of the TODO checklist).

Defects:
- W1 / P1 (major): a task row shows no chip for its links. Created a TODO with a contact link; the row showed
  title, date and priority only. Expected a link chip.
- W2 (minor): with no stored time zone, saving settings computed a date-only due time in UTC while the page
  runs in the device zone. Expected the device zone to be stored first.
- W3 (copy): after a 429 on parse the previous review stays under a generic "Too many requests" line.
- W4 (question, by design): a zone change moves date-only tasks; a timed task keeps its instant.
- W5 (seen once, not reproduced): a time typed as 12:00 PM saved as 21:00.
- P2 (minor): `document.body.scrollWidth` 468 at 390 wide on the settings page, nothing visibly overflowing.
- Recipe: seven corrections to docs/test/WEB.md (marker id, zone result id, where accepted capture tasks
  show, the calendar and the fake clock, the fixed fixture titles, the expected first-load 401).
The screenshots were deleted at cleanup.

Timing: web about 45 minutes, 60 script runs; phone on web about 10 minutes, 12 script runs; simulator build
about 2 minutes.

## Re-walk after the fix round (same day, uncommitted tree on top of 99012b7)

| Step | Lane | Result | Note |
|---|---|---|---|
| 01 Today by hand | web and phone on web | PASS | The row shows the priority chip and one chip per link (W1 fixed) |
| First signed-out load of /today | web | PASS, then reverted | The change that removed the first-load refresh 401 was reverted after review (it could leave a real cookie session unresumed); one console 401 on the first signed-out load is expected again and was not re-walked |
| Device zone for a fresh user | web and phone on web | PASS | The stored zone becomes the device zone on the first TODO page load; a date-only due time is 18:00 in that zone (W2 fixed) |
| Capture rate limit | web | PASS | Own label text; the earlier review is cleared (W3 fixed) |
| Calendar follows the fake clock | web | PASS | Clock line, selected day and lane follow the pinned day |
| Time field | web | PASS with a note | PM then 12 saves 12:00. An invalid hour ("91") shows the inline error and disables Save while the box has focus; on leaving the box it falls back to the last valid digit shown ("9") and that shown value is what saves (W6, minor: the error text has no semantics label) |
| Dialogs, console errors, overflow | web and phone on web | PASS | 0 on the five pages |

Open after the re-walk: W6 (minor; the error text has since been given the id `<fieldId>-hour-error`), P2 (minor), and every simulator step past launch (hand test).
