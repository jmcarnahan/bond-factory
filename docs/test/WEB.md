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

Sign-in: the first page that needs the API calls `DemoSession.ensureSignedIn()`, which does `POST /auth/demo`
as `demo-user-1`. The session cookie is same-site between :8078 and :8012 (same host, different port), so
the connect flow's top-level navigation carries it. Reloading the page signs in again.

## Page setup

- After EVERY full page load (`goto`, `reload`, a redirect back from the consent page) switch the semantics
  tree on: `page.locator('flt-semantics-placeholder').dispatchEvent('click')`. With the MCP server:
  `browser_evaluate` of `() => { document.querySelector('flt-semantics-placeholder').click(); return 'ok'; }`.
  A real click fails with "outside of the viewport". In-app navigation keeps semantics on. The demo also
  calls `ensureSemantics()` in `main()` as a convenience; do not rely on it.
- Viewports: 1280x800 (desktop) and 390x844 (phone lane, `/ui` and `/tasks`). Nothing may overflow at 390.

## Selectors

- Convention: `Semantics(identifier: 'sdk.<page>.<element>')`, exposed as the DOM attribute
  `flt-semantics-identifier`: `page.locator('[flt-semantics-identifier="sdk.auth.sign-in"]')`, or
  `getByRole('button', {name: /Sign in/})`. `ValueKey`s are not in the DOM.
- Select or segmented options are `<id>-<value>`. A confirm control is `<id>`, then `<id>-confirm`
  or `<id>-cancel`. Static text is found by text. A labelled card or button exposes only its label.
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
| `/auth` | `sdk.nav.auth` | Sign-in (mock identity, demo user, not-invited), claims, refresh, forced 401, sign out |
| `/sync` | `sdk.nav.sync` | Row editor, upload with per-row verdicts, server clock, sync token |
| `/connections` | `sdk.nav.connections` | A card per fake provider, return banner, simulate expiry |
| `/tasks` | `sdk.nav.tasks` | Landing: summary, list, quick add, form, run due jobs, reminder notices, mirror ids |

## Walk steps (ids are `[flt-semantics-identifier=...]`)

1. **Home.** `sdk.home.route-<id>` for home, ui, api, auth, sync, connections, tasks; `sdk.errors` absent.
2. **UI.** Sections `sdk.ui.section-<id>`; widgets `sdk.ui.button`, `.text-field`, `.select`,
   `.select-chips`, `.select-radio`, `.segmented`, `.confirm`, `.banner`, `.table`, `.bottom-tasks`, `.nav-tasks`,
   `.error-state-retry`. Open `sdk.ui.select`: the list expands inline, no dialog. Confirm is two steps:
   `sdk.ui.confirm`, then `sdk.ui.confirm-confirm` (or `-cancel`). Read `sdk.ui.last-event`. Repeat at 390x844.
3. **API.** Click `sdk.api.health`, then `sdk.api.not-found`, then `sdk.api.validation`; after each, read
   `sdk.api.result` (health ok; a not-found message; code, message and hint for validation).
4. **Auth.** Type the e-mail into `sdk.auth.email`; click `sdk.auth.sign-in`; assert `sdk.auth.user`,
   `sdk.auth.capabilities`, `sdk.auth.token-tail`. Click `sdk.auth.refresh` then read `sdk.auth.refresh-result`.
   Click `sdk.auth.force-401`: read `sdk.auth.force-401-result` and `sdk.auth.renewals` (one renewal).
   Click `sdk.auth.not-invited`: read `sdk.auth.error`. Click `sdk.auth.sign-out`: `sdk.auth.signed-out`.
   `sdk.auth.sign-in-demo` signs in as the demo user.
5. **Sync.** Click `sdk.sync.add-row` twice and `sdk.sync.add-bad-row` once; read `sdk.sync.queued`, `sdk.sync.rows`.
   Click `sdk.sync.upload`; read `sdk.sync.verdict-0`, `-1`, `-2` (two accepted, one rejected). Click
   `sdk.sync.fix-row`, then `sdk.sync.resend`: the fixed row is accepted. Read `sdk.sync.server-clock` (skew);
   `sdk.sync.fetch-token` shows `sdk.sync.token`. Errors land in `sdk.sync.error`, notes in `sdk.sync.info`.
6. **Connections.** Wait for `sdk.connections.list`. Click `sdk.connections.connect-fake-google`. The window leaves
   the app: `:8012/connections/fake-google/go?state=...` sets the nonce cookie and redirects to the fake
   consent page `:8012/connections/fake/consent`; click `#sdk-consent-allow` (plain HTML, a normal click).
   The API redirects to `http://localhost:8078/connections?connection=connected&provider=fake-google`, a full load:
   click the semantics placeholder again. Assert `sdk.connections.return` and
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

## Cleanup

Kill the pids in `tmp/logs/` (`kill $(cat tmp/logs/sdk_demo.pid) $(cat tmp/logs/sdk_example.pid)`) and confirm
ports 8078 and 8012 are free. State lives in `services/sdk_example/out/` (gitignored); delete it to reset.
`demos/sdk_demo/e2e/` holds `package.json`, `playwright.config.mjs` (one worker, base URL
`http://localhost:8078`, no `webServer` block) and `lib.mjs`; run `npm install` once, then `npx playwright test`.
