# Direct sign-in walk (2026-11-09)

What was walked: phases 1-2 of `local/plan/2026-11-09-direct-signin` (sign-in with the fake Google and Microsoft
providers, refresh and reuse detection, the uninvited refusal, role scope asks with decline then grant, break-glass,
Microsoft full-scope sign-in), commit c6c8fed, per `docs/test/WEB.md` "Sign-in walk", by a Sonnet walker with the
Playwright test runner (headless Chromium, one worker, spec kept under `tmp/handtest`, deleted at cleanup).
Stack: example API on :8012 in fake mode on a fresh database (`services/sdk_example/out/` deleted first), demo debug
web-server on :8078; step 7 ran against the example restarted with `SDK_EXAMPLE_BREAKGLASS=1`, then restarted without
it. Phone on web: the same demo at 390x844 (no separate target). Simulator: not booted.
Shots pass: skipped: no `make shots` target.

## Web (1280x800)
| Step | User | Result | Note |
|---|---|---|---|
| 01 Surface signed out: two provider buttons, invite-only line, no e-mail form, no break-glass | - | PASS | |
| 02 Sign in via fake-google consent, chips, HttpOnly cookies, /auth/me and refresh by cookie after reload | demo@example.com | PASS | `document.cookie` empty; both fetches 200 |
| 03 Refresh: new token tail, chips unchanged | demo | PASS | |
| 04 Simulate reuse: signed out with the reuse message; sign in again works | demo | PASS | |
| 05 Uninvited identity: return with reason not_invited, inline message, /auth/me 401 | uninvited@example.com | PASS | |
| 06 Role asks: two sets wanted; untick then allow → consent_declined banner, set still wanted; allow → granted, Google connected | demo | PASS | W2 |
| 07 Break-glass (flag on): link visible, inline form, demo signs in, crew refused provider_not_allowed | demo, crew | PASS | W3 |
| 08 Microsoft: connected at once, no asks | demo.microsoft@example.com | PASS | |
| Dialogs/popups on every page visited | | 0 | `sdk.errors` absent at every step |

## Phone (390x844, phone-on-web lane)
| Step | Lane | User | Result | Note |
|---|---|---|---|---|
| 01 Surface | phone-on-web | - | PASS | scrollWidth 390 |
| 02 Sign in | phone-on-web | demo | PASS | scrollWidth 390 |
| 06 Ask card | phone-on-web | demo | PASS | only the calendar ask remained (mail granted in the web lane); W2 |
| Console / runtime errors, popups | | | clean except W1, 0 | |

## Re-walk after the fix round (commit f9f1105: W2 ask names, W3 error line)
| Step | Lane | User | Result | Note |
|---|---|---|---|---|
| 06 Role asks: names "Allow Send mail" / "Allow Calendar", decline then grant the calendar set | web 1280x800 | demo | PASS | W2 fixed |
| 06 Role asks on a fresh database: both asks, decline then grant, no overflow | phone-on-web 390x844 | demo | PASS | scrollWidth 390 |
| Dialogs / console / pageerror / `sdk.errors` | both | | 0 / W1 only / 0 / absent | |
W3 (error line) was verified by the demo's widget tests only; the break-glass step was not re-walked.

Previous walk's open items (2026-11-08-sdk-initial): W1-W6 fixed in that walk's round 2; nothing re-walked today.

Defects: W1 (minor): every signed-out page load logs one console error "Failed to load resource: 401" because the
demo's startup probe posts `/auth/refresh` with no refresh cookie; harmless, and the browser logs any 4xx resource.
W2 (copy, minor): the ask buttons' accessible name is just "Allow"; the set name is not in the control's name.
W3 (copy, minor): the break-glass error line shows the raw "code: … | message: …" form instead of the message alone.
Timing: web lane about 1.5 minutes of runtime over four runs (three spent on the driver), 12 screenshots; phone lane
inline in the same run, 3 screenshots; step 7 one extra run.
