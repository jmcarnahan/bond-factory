# Existing phone store walk (2026-11-12)

What was walked: round 3 (mirror "pending" on no answer, the phone store seams, push devices over sync), working tree on
c638728 before its commit, per docs/test/WEB.md "TODO checklist walk" page set, by one Sonnet walker. The build changed
no demo and no widget, so this is a regression walk: the library defaults must look the same as before.
Stack: `make serve-example` (:8012, fake mode) and `make demo-sdk-web` (:8078, debug build), started from the build's
worktree. Driver: Playwright from node scripts, headless Chromium, a fresh browser per script as the demo user; no MCP
driver was available. Phone on web: the same demo at 390x844. Simulator: not booted (nothing needs iOS itself).
Shots pass: skipped: no make shots target.

## Web (1280x800)
| Step | User | Result | Note |
|---|---|---|---|
| /today renders | demo-user-1 | PASS | form and clock strip, no error banner |
| Create a dated, timed task with a checklist item | demo-user-1 | PASS | on /tasks; the link picker was not exercised (see W1 for the time) |
| Mirror state settles | demo-user-1 | PASS | "Calendar: skipped" (no connected calendar in fake mode), never "failed" |
| Edit the title | demo-user-1 | SKIP | the demo has no edit control |
| Complete, then reopen | demo-user-1 | PASS | summary Open 1, 0, 1; no error |
| /calendar | demo-user-1 | PASS | the day cell reads "13, 1 due" |
| /inbox, act Done on a notice | demo-user-1 | SKIP | page loads; no notice existed and the clock tick was out of scope |
| /todo-settings | demo-user-1 | PASS | three "Default" hints |
| /capture | demo-user-1 | PASS | page loads |
| /auth | signed out | PASS | fake provider buttons; not signed in |
| Dialogs/popups on every page visited | | 0 | |

## Phone (390x844, phone on web)
| Step | Lane | User | Result | Note |
|---|---|---|---|---|
| /today and /tasks, no horizontal overflow | phone on web | demo-user-1 | PASS | scrollWidth 390 |
| /todo-settings and /inbox, no horizontal overflow | phone on web | demo-user-1 | PASS | document width 390 (see W2) |
| Console / runtime errors, popups | | | clean, 0 | only the expected 401 of the first signed-out refresh |

Previous walk's open items: none carried.

Defects (neither is in code this build changed; both need a hand re-check before being treated as defects):
- W1 (minor, unconfirmed): a time typed as 9:30 was saved as 09:00. The walker typed into the minute box with select-all,
  so the driver is the likely cause.
- W2 (minor, unconfirmed): on /todo-settings at 390 the body's scroll width read 468 while the document's read 390.
Timing: one walker, about 12 scripted browser sessions.
