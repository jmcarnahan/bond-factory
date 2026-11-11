# Web walk recipe: demos/sdk_demo

How to drive the SDK demo in a browser with Playwright. The demo is a Flutter web harness (never shipped);
the example API is `services/sdk_example` in fake mode. Run everything from the repo root.

## Start

1. Example API (fake mode, no secrets, no network), backgrounded, pid saved: `make serve-example`
   (uvicorn on :8012). `curl -s localhost:8012/health` must return `"mode": "fake"`.
2. Demo, backgrounded, pid saved: `make demo-sdk-web` (debug `web-server` on :8078, runs
   `flutter run -d web-server --web-hostname 0.0.0.0 --web-port 8078 --no-web-experimental-hot-reload
   --dart-define=SDK_EXAMPLE_URL=http://localhost:8012`).
3. Save pids and logs under `tmp/logs/` (`sdk_demo.pid`, `sdk_example.pid`; gitignored).
4. Wait until `http://localhost:8078/main.dart.js` answers. The first compile takes minutes. A cold first
   browser can sit blank: retry on a fresh page.

Rules for the server:
- Serve a DEBUG build. No `flutter build web`, no renderer flags.
- `--no-web-experimental-hot-reload` is mandatory. Without it the debug service wedges after a few connect
  cycles and pages stay blank (dart-lang/sdk#60289). Recover by killing the pid and restarting.
- A debug build does not rebuild while running. Restart it (or `kill -USR2 <pid>`) after code changes.

Sign-in: `/auth` and `/connections` use real sign-in against the fake providers: see "Sign-in walk" below. A page that is
opened signed out first tries `completeWeb()` (the refresh cookie), then `DemoSession.ensureSignedIn()` falls back to
`POST /auth/demo` as `demo-user-1`; `/connections` still does this fallback. Opening `/connections` while signed out therefore silently signs in as the demo user, so the signed-out and uninvited steps must stay on `/auth`. The session cookies are same-site between :8078
and :8012 (same host, different port), so the connect flow's top-level navigation carries them.

## Page setup

- After EVERY full page load (`goto`, `reload`, a redirect back from the consent page) switch the semantics
  tree on when the placeholder is present: `page.locator('flt-semantics-placeholder').dispatchEvent('click')`
  (the demo calls `ensureSemantics()`, so it is usually already gone; click only if present). With the MCP server:
  `browser_evaluate` of `() => { document.querySelector('flt-semantics-placeholder').click(); return 'ok'; }`.
  A real click fails with "outside of the viewport". In-app navigation keeps semantics on. The demo also
  calls `ensureSemantics()` in `main()` as a convenience; do not rely on it.
- Viewports: 1280x800 (desktop, left nav) and 390x844 (phone lane, `/ui` and `/tasks`; below 600 px the nav is
  a scrolling strip under the page, same `sdk.nav.<id>` ids). Nothing may overflow at 390.

## Selectors

- Convention: `Semantics(identifier: 'sdk.<page>.<element>')`, exposed as the DOM attribute
  `flt-semantics-identifier`: `page.locator('[flt-semantics-identifier="sdk.auth.sign-in"]')`, or
  `getByRole('button', {name: /Sign in/})`. `ValueKey`s are not in the DOM.
- Select or segmented options are `<id>-<value>`. A confirm control is `<id>`, then `<id>-confirm`
  or `<id>-cancel`. Static text is found by text. A labelled card or button exposes only its label.
- Every `sdk.*` text node exposes its text as the semantics label, so read `getAttribute('aria-label')` or
  the accessible name instead of taking screenshots.
- Elements below the fold are absent from the tree: wheel-scroll until they appear.
- Helpers in `demos/sdk_demo/e2e/lib.mjs`: `enableSemantics(page)`, `sid(page, id)`, `typeInto(locator,
  text)`, `collectErrors(page)`.
- `locator.fill` empties Flutter fields. Click the field, wait 400 ms, `ControlOrMeta+a`, then
  `pressSequentially(text, {delay: 25})`. A text field has a disabled twin: use `.first()` or `:not([disabled])`.

## Error check (every route, every step)

Zero `[role=dialog],[role=alertdialog]`; empty `pageerror` list; no console message of type `error`
(`page.on('dialog' | 'console' | 'pageerror')`; MCP: `browser_console_messages`); the inline strip
`sdk.errors` is absent (it shows `sdk.errors.count`, newest error first, when the framework reports one).

## Routes

| Route | Nav id | Shows |
|---|---|---|
| `/` | `sdk.nav.home` | The seven routes, one line each with module and phase |
| `/ui` | `sdk.nav.ui` | `bond_ui` gallery: primitives, inputs, select, confirm, navigation, states; `sdk.ui.last-event` |
| `/api` | `sdk.nav.api` | Three probe buttons and one inline result line |
| `/auth` | `sdk.nav.auth` | Sign-in buttons per fake provider, claims chips, refresh, simulate reuse, break-glass link (flag), sign out |
| `/sync` | `sdk.nav.sync` | Row editor, upload with per-row verdicts, server clock, sync token |
| `/connections` | `sdk.nav.connections` | A card per fake provider, return banner, simulate expiry, the wanted-scope ask card |
| `/tasks` | `sdk.nav.tasks` | Landing: summary, list, quick add, form, run due jobs, reminder notices, mirror ids |

## Walk steps (ids are `[flt-semantics-identifier=...]`)

1. **Home.** `sdk.home.route-<id>` for home, ui, api, auth, sync, connections, tasks; `sdk.errors` absent.
2. **UI.** Sections `sdk.ui.section-<id>`; widgets `sdk.ui.button`, `.text-field`, `.select`,
   `.select-chips`, `.select-radio`, `.segmented`, `.confirm`, `.banner`, `.table`, `.bottom-tasks`, `.nav-tasks`,
   `.error-state-retry`. Open `sdk.ui.select`: the list expands inline, no dialog. Confirm is two steps:
   `sdk.ui.confirm`, then `sdk.ui.confirm-confirm` (or `-cancel`). Read `sdk.ui.last-event`. Repeat at 390x844.
3. **API.** Click `sdk.api.health`, then `sdk.api.not-found`, then `sdk.api.validation`; after each, read
   `sdk.api.result` (health ok; a not-found message; code, message and hint for validation).
4. **Auth.** The sign-in chain, steps 1 to 5 and 7 of "Sign-in walk" below, in that order. Ids: `sdk.signin.fake-google`,
   `sdk.signin.fake-microsoft`, `sdk.signin.error`, `sdk.signin.break-glass`, `sdk.auth.user`, `sdk.auth.capabilities`,
   `sdk.auth.token-tail`, `sdk.auth.refresh`, `sdk.auth.refresh-result`, `sdk.auth.simulate-reuse`, `sdk.auth.sign-out`,
   `sdk.auth.signed-out`, `sdk.auth.loading`, `sdk.auth.ended`, `sdk.auth.error`, `sdk.auth.force-401` with
   `sdk.auth.force-401-result` and `sdk.auth.renewals`. The break-glass form holds `sdk.auth.email`, `sdk.auth.sign-in`,
   `sdk.auth.sign-in-demo` and `sdk.auth.not-invited`.
5. **Sync.** Click `sdk.sync.add-row` twice and `sdk.sync.add-bad-row` once; read `sdk.sync.queued`, `sdk.sync.rows`.
   Click `sdk.sync.upload`; read `sdk.sync.verdict-0`, `-1`, `-2` (two accepted, one rejected). Click
   `sdk.sync.fix-row`, then `sdk.sync.resend`: the fixed row is accepted. Read `sdk.sync.server-clock` (skew);
   `sdk.sync.fetch-token` shows `sdk.sync.token`: the fake example mints a sync token by default (stand-in endpoint), so it always appears. Errors land in `sdk.sync.error`, notes in `sdk.sync.info`.
6. **Connections.** Start with steps 6 and 8 of "Sign-in walk" (role asks, then Microsoft), then the plain connect round trip. Wait for
   `sdk.connections.list`. Click `sdk.connections.connect-fake-google`. The window leaves
   the app: `:8012/connections/fake-google/go?state=...` sets the nonce cookie and redirects to the fake
   consent page `:8012/connections/fake/consent`; click `#sdk-consent-allow` (plain HTML, a normal click).
   The API redirects to `http://localhost:8078/connections?connection=connected&provider=fake-google`, a full load:
   click the semantics placeholder again. Assert `sdk.connections.return` (it carries the banner label; dismiss it with `sdk.connections.return-dismiss`) and
   `sdk.connections.state-fake-google` (connected). Click `sdk.connections.simulate-expiry-fake-google`: the
   state becomes needs-reconnect; click `sdk.connections.reconnect-fake-google` and repeat the round trip.
   Disconnect is two steps: `sdk.connections.disconnect-fake-google`, then `...-confirm`. Repeat with
   `fake-microsoft`. A failure shows in `sdk.connections.error`; a headless run that cannot navigate shows
   `sdk.connections.start-url`.
7. **Tasks.** Quick add: `sdk.tasks.quick-add`, then `sdk.tasks.quick-add-add`. Form: `sdk.tasks.form-title`;
   checklist input `sdk.tasks.form-checklist-add` and `sdk.tasks.form-checklist-add-button` (twice). A reminder
   needs a due moment: `sdk.tasks.form-due-date` (opens an inline calendar, pick a day), then
   `sdk.tasks.form-due-time-add` and `sdk.tasks.form-due-time` (`-remove` clears it). Then
   `sdk.tasks.form-reminder` and its option "1 minute before", `sdk.tasks.form-mirror` for the calendar mirror,
   `sdk.tasks.form-save`. Row `sdk.tasks.row-<id>`; tick a checklist item; `sdk.tasks.complete-<id>` completes
   and reopens. Click `sdk.tasks.run-due-jobs` (the example ticks with `now` two minutes ahead), then read
   `sdk.tasks.notices` and `sdk.tasks.notice-<n>` (or click `sdk.tasks.show-notices`). The mirror shows
   `sdk.tasks.external-<id>` (the external id). Turn it off with the per-row toggle `sdk.tasks.mirror-<id>`:
   `sdk.tasks.external-<id>` is then absent. Click `sdk.tasks.reload` after saving or toggling the mirror: the
   mirror runs after the response as a background task, so the first answer does not carry its result yet.
   Delete is two steps: `sdk.tasks.delete-<id>`, then `-confirm`. Messages: `sdk.tasks.info`, `sdk.tasks.error`.
8. **Error check** after every step (section above).

## Sign-in walk (`/auth` and `/connections`)

State chain: each step starts from the state the previous one left, so run them in order in ONE browser context. The example
runs in fake mode with its seeded rows: `demo@example.com` (capabilities include `connections.manage`, `allow_password` true),
`crew@example.com` (no mail asks, `allow_password` false), `demo.microsoft@example.com` (fake-microsoft) and NO row for
`uninvited@example.com`. Lanes: 1280x800 and 390x844. After every full load (including each return from the consent page)
click the semantics placeholder. The fake consent page (`:8012/connections/fake/consent`) is plain HTML: `#sdk-consent-identity`
(select, preselected per provider), `#sdk-consent-email` (free text, wins over the select), `#sdk-consent-set-mail_send` and
`#sdk-consent-set-calendar` (connect only, ticked by default), `#sdk-consent-allow`, `#sdk-consent-deny`.

1. **Surface, signed out.** `/auth` shows `sdk.signin.fake-google` and `sdk.signin.fake-microsoft`, the invite-only line and
   no e-mail form. `sdk.signin.break-glass` is ABSENT (flag off). No dialog.
2. **Sign in.** Click `sdk.signin.fake-google`. The window leaves the app (`POST /auth/signin/fake-google/start` set the nonce
   cookie, then the browser goes to the consent page). Keep the preselected demo identity, click `#sdk-consent-allow`. The
   API redirects to `http://localhost:8078/auth?signin=ok` (full load). Assert `sdk.auth.user`, `sdk.auth.capabilities`,
   `sdk.auth.token-tail`. Cookie proof is behavioural: `document.cookie` holds neither `sdk_example_access_token` nor
   `sdk_example_refresh_token` (both HttpOnly); after a full reload `fetch('http://localhost:8012/auth/me', {credentials:
   'include'})` answers 200 with no bearer, and `POST /auth/refresh` with body `{}`, credentials and the demo origin succeeds.
   Not executed in a browser by the builders: the walker proves it.
3. **Refresh.** Click `sdk.auth.refresh`: `sdk.auth.refresh-result` reads "Refreshed: token ends <tail>" with a new tail, the
   chips are unchanged, no error strip.
4. **Simulate reuse.** Click `sdk.auth.simulate-reuse` (`POST /auth/simulate-reuse`: the example rotates, ages the old row past
   the grace, replays it and answers 401 `refresh_reused`). The page signs out; `sdk.auth.ended` shows "You were signed out
   because this session was used somewhere else. Sign in again." Sign in again as in step 2: it works (a new family).
5. **Uninvited.** Click `sdk.auth.sign-out` first (start signed out). Click `sdk.signin.fake-google`, type `uninvited@example.com`
   into `#sdk-consent-email`, allow. The return is `/auth?signin=error&reason=not_invited`: `sdk.signin.error` shows the inline
   message and `GET /auth/me` answers 401. No user row exists.
6. **Role asks.** Sign in as the demo identity again. Open `/connections`: two sets are wanted and ungranted, "Send mail"
   (`sdk.scopes.ask-mail_send`) and "Calendar" (`sdk.scopes.ask-calendar`). Click the mail ask. First decline: untick
   `#sdk-consent-set-mail_send` (or click `#sdk-consent-deny`) and allow. The return is `/connections?connection=error&reason=
   consent_declined`, the banner reads "You did not allow that access. You can allow it later.", NO row was stored and the set is
   still wanted. Ask again, leave both ticked, allow: the set is granted and the Google connection is connected. The ask stays
   inline, no dialog.
7. **Break-glass.** Sign out. Stop the example and restart it with `SDK_EXAMPLE_BREAKGLASS=1 make serve-example`, then reload `/auth`:
   `sdk.signin.break-glass` is visible and opens the inline e-mail form (no dialog). `demo@example.com` signs in
   (`sdk.auth.sign-in`); `crew@example.com` answers 403 `provider_not_allowed` in `sdk.auth.error`. Restart without the flag afterwards.
8. **Microsoft.** Sign out, then `sdk.signin.fake-microsoft` with its preselected demo identity. `/connections` shows the Microsoft
   connection connected at once (full scopes at sign-in) and the wanted list is empty.
9. **Phone lane (390x844).** Steps 1, 2 and 6 wrap without horizontal overflow; the ask card and buttons stay reachable.
10. **Error check** after every step: no dialog, no console error, no `pageerror`, `sdk.errors` absent.

## Cleanup

Kill the pids in `tmp/logs/` (`kill $(cat tmp/logs/sdk_demo.pid) $(cat tmp/logs/sdk_example.pid)`) and confirm
ports 8078 and 8012 are free. State lives in `services/sdk_example/out/` (gitignored); delete it to reset.
`demos/sdk_demo/e2e/` holds `package.json`, `playwright.config.mjs` (one worker, base URL
`http://localhost:8078`, no `webServer` block) and `lib.mjs`; run `npm install` once, then `npx playwright test`.

# Web walk recipe: demos/roof_demo

The roof demo is a Flutter web harness for `bond_roof_ui` against the `roof_measure` service. Run everything from
the repo root. Written from the 2026-11-11 roof-module-v1 walk.

## Start

1. Service, backgrounded, pid saved: `ROOF_MEASURE_AUTH=off ROOF_MEASURE_HOST=127.0.0.1 ROOF_MEASURE_DEBUG=1
   DATA_DIR=tmp/walk-data services/roof_measure/.venv/bin/uvicorn roof_measure.api:app --host 127.0.0.1 --port 8011`
   (`tmp/logs/roof_measure.pid`). `curl -s localhost:8011/healthz` must return `{"status":"ok", ...}`. Auth off is
   allowed only on a loopback host; `ROOF_MEASURE_DEBUG=1` exposes the fixture routes the demo's "(service)" chips use.
   A real-address job needs the network (Census, Overpass, USGS 3DEP); the address comes from the gitignored
   `local/spike-sites.json` and must never be written into a record.
2. Demo, backgrounded, pid saved (`tmp/logs/roof_demo.pid`): from `demos/roof_demo`, `tool/sync_fixtures.sh` then
   `flutter run -d web-server --web-hostname 0.0.0.0 --web-port 8077 --no-web-experimental-hot-reload
   --dart-define=ROOF_SERVICE=http://localhost:8011`. Same server rules as the SDK demo above (debug build,
   no hot reload, restart after code changes). Wait until `http://localhost:8077/main.dart.js` answers.
3. CORS: the service's default origin regex allows localhost, so :8077 → :8011 works without a flag.

## Page setup

- The demo does NOT call `ensureSemantics()`: after every full load click the placeholder,
  `page.locator('flt-semantics-placeholder').dispatchEvent('click')`, before any locator.
- No `flt-semantics-identifier` attributes exist in this demo. Locate by role and accessible name:
  `getByRole('button', {name: 'Measure'})`, `getByRole('button', {name: /EN|ES/})` (segmented buttons),
  `getByRole('checkbox', {name: 'roof_measurement_0.2_pass', exact: true})` (fixture chips are ChoiceChips and
  expose role checkbox; a "(service)" variant appears only for a service fixture that is not bundled),
  `getByRole('textbox')` (the address field), `getByText(...)` for inline status, totals rows and
  warnings. Method segments are `getByRole('button', {name: /lidar_skeleton|lidar_agent|solar_agent|auto/})`.
- Viewports: 1280x800 and 390x844. Below 600 px the report strip switches to the compact layout (800x1000 design
  size, two-column legend); above it the wide layout. Nothing may overflow at 390.
- Print and Save/Share PDF: Print calls `Printing.layoutPdf` (the browser print dialog is allowed by the no-popups
  rule; headless Chromium never fires `beforeprint`, so assert the iframe the package inserts or SKIP); Save PDF
  and Share PDF both download the file on web. Playwright: `page.waitForEvent('download')`. The PDF is vector:
  about 12 KB for three Letter pages with the Roboto subset embedded.
- Restarting the demo web-server while a page is open yields a one-off requirejs "Script error for
  web_entrypoint.dart" page error; reload after `main.dart.js` answers again. Playwright's `isMobile`/`hasTouch`
  emulation raises a Flutter "ViewInsets cannot be negative" assertion at load; use a plain 390x844 viewport.
- The service is a separate process: restart it after service code changes, or lazy imports fail with ImportError.

## Walk steps

1. **Load.** Title "Roof measurement demo"; address field, method segments, Measure, EN/ES, "Load fixture" chips.
2. **Pass envelope.** Click the `roof_measurement_0.2_pass` chip: diagram visible, totals table with the paired
   variant rows (drip edge eave / eave+rake; ridge cap ridge / ridge+hip), the verdict line, the generated-at line.
3. **Spanish.** Click `ES`: every label changes (e.g. "Aleros"), no overflow, chips still work. Click `EN` back.
4. **390x844.** Repeat 2 at the phone viewport: compact layout, legible, no overflow, buttons reachable.
5. **PDF.** Click Save PDF: a download named `*.pdf` whose first page is the length diagram (size > 20 KB).
   Print: the dialog is the browser's; assert the call was made (a `beforeprint` listener) or SKIP headless.
6. **Adjusted and fail.** Load `roof_measurement_0.2_adjusted` and `_fail`: the verification line shows the
   verdict label and the first note. There are no "(service)" chips when every service fixture is also bundled
   (the demo hides duplicates); `GET /fixtures` on :8011 lists the same ten names.
7. **Service job.** Type an address from `local/spike-sites.json` (one that measured in the spike), method
   `lidar_skeleton`, click Measure: the inline status goes queued → running → done within 90 s and the report
   renders; or an inline `code: message` error line on failure. No dialogs.
8. **Wrong token.** Not walkable with auth off; SKIP (covered by `tests/test_auth.py`).
9. **Error check** after every step: no `[role=dialog]`, no console error, no `pageerror`.

## Cleanup

`kill $(cat tmp/logs/roof_demo.pid) $(cat tmp/logs/roof_measure.pid)`; confirm :8077 and :8011 are free;
`rm -rf tmp/walk-data tmp/handtest`.
