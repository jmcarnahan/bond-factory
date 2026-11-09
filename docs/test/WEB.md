# Web walk recipe: demos/sdk_demo

How to drive the SDK demo in a browser with Playwright. The demo is a Flutter web harness (never shipped);
the example API is `services/sdk_example` in fake mode. Run everything from the repo root.

Phase 1 state: the demo is a shell. Home and the navigation work; the other six pages are placeholders
(`sdk.<page>.placeholder`) and the example serves only `GET /health`. The page behaviours in the Routes table
are the targets for phases 2 and 3; walk only what exists.

## Start

1. Example API (fake mode, no secrets, no network), backgrounded, pid saved:
   `make serve-example` (uvicorn on :8012). Check `curl -s localhost:8012/health` returns `"mode": "fake"`.
2. Demo, backgrounded, pid saved: `make demo-sdk-web` (debug `web-server` on :8078, runs
   `flutter run -d web-server --web-hostname 0.0.0.0 --web-port 8078 --no-web-experimental-hot-reload
   --dart-define=SDK_EXAMPLE_URL=http://localhost:8012`).
3. Save pids and logs under `tmp/logs/` (gitignored), for example `tmp/logs/sdk_demo.pid`,
   `tmp/logs/sdk_example.pid`.
4. Wait until `http://localhost:8078/main.dart.js` answers. The first compile takes minutes. A cold first
   browser can sit blank: retry on a fresh page.

Rules for the server:
- Serve a DEBUG build. No `flutter build web`, no renderer flags.
- `--no-web-experimental-hot-reload` is mandatory. Without it the debug service wedges after a few connect
  cycles and pages stay blank (dart-lang/sdk#60289). Recover by killing the pid and restarting.
- A debug build does not rebuild while running. Restart it (or `kill -USR2 <pid>`) after code changes.

## Page setup

- After EVERY full page load (`goto`, `reload`, a redirect back from the example's consent page) switch the
  semantics tree on: `page.locator('flt-semantics-placeholder').dispatchEvent('click')`. With the MCP server:
  `browser_evaluate` of `() => { document.querySelector('flt-semantics-placeholder').click(); return 'ok'; }`.
  A real click fails with "outside of the viewport". In-app navigation keeps semantics on.
  The demo also calls `ensureSemantics()` in `main()` as a convenience; do not rely on it.
- Viewports: 1280x800 for the desktop lane, 390x844 for the phone lane. The UI must not overflow at 390.

## Selectors

- Convention: `Semantics(identifier: 'sdk.<page>.<element>', label: '<human name>')`. The identifier is the DOM
  attribute `flt-semantics-identifier`:
  `page.locator('[flt-semantics-identifier="sdk.auth.sign-in"]')`, or `getByRole('button', {name: /Sign in/})`.
- Select or segmented options use `<key>-<value>`. `ValueKey`s are not in the DOM.
- Static text is found by text. A labelled card or button exposes only its label, not its inner text.
- Elements below the fold are absent from the tree: wheel-scroll until they appear.
- Helpers live in `demos/sdk_demo/e2e/lib.mjs`: `enableSemantics(page)`, `sid(page, id)`,
  `typeInto(locator, text)`, `collectErrors(page)`.

## Typing into a field

`locator.fill` empties Flutter fields. Click the field, wait 400 ms, press `ControlOrMeta+a`, then
`pressSequentially(text, {delay: 25})`. A text field has a disabled twin with the same label: use `.first()`
or `:not([disabled])`.

## Error check (every route, every step)

- Zero `[role=dialog],[role=alertdialog]` elements.
- Empty `pageerror` list and no console message of type `error`
  (`page.on('dialog' | 'console' | 'pageerror')`; MCP: `browser_console_messages`).
- The demo's inline error strip, `[flt-semantics-identifier="sdk.errors"]`, is absent. It appears when the
  Flutter framework reports an error, so a walk can read errors without any popup.

## Routes

| Route | Nav id | Shows |
|---|---|---|
| `/` | `sdk.nav.home` | Home: the seven routes with their phase |
| `/ui` | `sdk.nav.ui` | `bond_ui` widget gallery (target; placeholder until it lands) |
| `/api` | `sdk.nav.api` | `bond_api` health, not-found and validation errors (target) |
| `/auth` | `sdk.nav.auth` | `bond_auth`: demo sign-in, refresh, forced 401, sign out (target) |
| `/sync` | `sdk.nav.sync` | `bond_sync`: upload rows, accepted and rejected inline (target) |
| `/connections` | `sdk.nav.connections` | Fake OAuth connect, expiry, reconnect, disconnect (target) |
| `/tasks` | `sdk.nav.tasks` | Tasks with checklist, reminder run, calendar mirror (target) |

A page that has not landed shows `sdk.<name>.placeholder` ("`<Module>` arrives in phase N").
Deep links work (`usePathUrlStrategy`): `http://localhost:8078/connections?connection=connected` reloads
into the app. Remember the semantics click after the reload.

## Cleanup

Kill the pids in `tmp/logs/` (`kill $(cat tmp/logs/sdk_demo.pid) $(cat tmp/logs/sdk_example.pid)`), then
confirm ports 8078 and 8012 are free. The example's database and keys are under `services/sdk_example/out/`
(gitignored); delete that folder to reset state.

## Playwright test runner

`demos/sdk_demo/e2e/` holds `package.json`, `playwright.config.mjs` (one worker, base URL
`http://localhost:8078`, no `webServer` block) and `lib.mjs`. Run `npm install` there once, then
`npx playwright test` against servers you started above. `node_modules/` is gitignored.
