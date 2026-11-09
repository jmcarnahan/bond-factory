# Reading the SDK examples

`services/sdk_example` (FastAPI, port 8012) and `demos/sdk_demo` (Flutter web, port 8078) wire every module end to
end in fake mode. Use them as few-shot examples: find the module in the table, open the files named for it, copy the
shape into the app. They are never shipped. `README.md` in this folder covers consuming the modules.

## Run both

- Once: `make setup-py` at the repo root (workspace virtual environment).
- API: `make serve-example` serves on :8012 through the `create_app` factory. With no environment variables it starts in
  fake mode (mock identities, demo sign-in, generated keys) and logs one warning. Check it:

  ```
  curl -s localhost:8012/health
  ```

  The answer is `{"status": "ok", "mode": "fake"}`. The database, uploads and generated keys live in
  `services/sdk_example/out/` (ignored by git); delete that folder to start clean.
- Demo: `make demo-sdk-web` serves a debug build on :8078 and talks to `http://localhost:8012`. To point it elsewhere, run
  `make -C demos/sdk_demo serve-web SDK_EXAMPLE_URL=<url>`.
- Tests: `make test-example`, `make -C services/sdk_example migrate` (Alembic to head), `make -C demos/sdk_demo test T=test/smoke_test.dart`.
- Settings are read once by `Settings.from_env()`:

| Variable | Default | Note |
|---|---|---|
| `SDK_EXAMPLE_MODE` | `fake` | `real` needs `SDK_EXAMPLE_AUTH_SECRET` or startup fails |
| `SDK_EXAMPLE_DATABASE_URL` | `sqlite:///out/sdk_example.db` | |
| `SDK_EXAMPLE_CORS_ORIGINS` | `http://localhost:8078` | `*` is refused (credentials are on) |
| `SDK_EXAMPLE_REDIRECT_ALLOWLIST` | `http://localhost:8078` | OAuth `redirect_to` must match; no open redirect |
| `SDK_EXAMPLE_TZ` | `UTC` | time zone the example uses for local times |
| `SDK_EXAMPLE_SYNC_URL` | empty | sync endpoint handed out by `POST /sync/token`; empty means sync is off |
| `BOND_OAUTH_KEY` | generated in `out/oauth.key` (fake mode) | token encryption key; real mode fails at startup without it |
| `BOND_OAUTH_REDIRECT_BASE` | the request's own base URL | public base URL for the OAuth callback; must match what the provider registered |
| `BOND_GOOGLE_CLIENT_ID`, `BOND_GOOGLE_CLIENT_SECRET` | unset | real mode: Google is offered only when both are set |
| `BOND_MS_CLIENT_ID`, `BOND_MS_CLIENT_SECRET` | unset | real mode: Microsoft is offered only when both are set |
| `BOND_MS_TENANT` | `common` | Microsoft tenant |
| `BOND_SYNC_*` | unset | read by `SyncTokenSettings.from_env()`: `PRIVATE_KEY`, `PRIVATE_KEY_FILE`, `KID`, `PREVIOUS_KEY`, `PREVIOUS_KEY_FILE`, `PREVIOUS_KID`, `AUDIENCE`, `MINUTES`; in fake mode a missing key is generated into `out/sync_key.pem` |

## Which module shows where

| Module | Service files (`services/sdk_example/sdk_example/`) | Demo page (`demos/sdk_demo/lib/src/pages/`) | Walk route |
|---|---|---|---|
| `bond_api`, `bond_json` | `routes/health.py` | `api_page.dart`: health, a 404, a validation error | `/api` |
| `bond_ui` | none | `ui_page.dart` and `ui/`: every widget once | `/ui` |
| `bond_test_support` | none | every `test/<page>_test.dart` (`pumpApp`, `expectNoOverlays`) | none |
| `bond_service_kit` | `wiring.py`: error handlers, middleware, clock, limiters; `db.py` | none | none |
| `bond_auth_py`, `bond_auth`, `bond_auth_firebase` | `routes/auth.py`, `auth_dep.py`, `models/auth.py` | `auth_page.dart`: sign in, refresh, forced 401, not-invited, sign out | `/auth` |
| `bond_storage` | `routes/storage.py` (upload, share, `GET /d/{token}`), `models/grants.py` | none; see `tests/test_storage.py` | none |
| `bond_jobs` | `models/jobs.py`, the registry in `wiring.py` | none | none |
| `bond_sync_py`, `bond_sync`, `bond_sync_powersync` | `routes/sync.py`, `models/sync.py` | `sync_page.dart`: rows, upload verdicts, token | `/sync` |
| `bond_oauth` | `routes/connections.py`, `oauth_wiring.py`, `models/connections.py`; routes: `GET /connections`, `GET /connections/{provider}/start`, `GET /connections/{provider}/go?state=` (sets the nonce cookie, then redirects to the provider), `GET /connections/{provider}/callback`, `DELETE /connections/{provider}`, `GET /connections/fake/consent`, `POST /connections/{provider}/simulate-expiry` | `connections_page.dart` | `/connections` |
| tasks, calendar, connections UI | the same pattern: a `routes/<module>.py` and a `models/<module>.py` | `tasks_page.dart`, `connections_page.dart` | `/tasks` |

A page whose module has not landed shows a placeholder under `sdk.<id>.placeholder`.

## services/sdk_example

| File | What to copy from it |
|---|---|
| `main.py` | `create_app()`; nothing is built at import; route modules are found with `pkgutil`, no list to edit |
| `settings.py`, `db.py` | an explicit settings dataclass; `Base`, `make_engine`, `session_scope` |
| `wiring.py` | one `install(app)`: auth settings, storage, job registry, clock, limiters, middleware order, fake-mode schema bootstrap |
| `routes/a0_wiring.py` | runs `install` first because route modules load alphabetically |
| `auth_dep.py` | `current_claims`, `current_user`, `require_capability`, the revocation check before `is_active` |
| `models/<module>.py` | one file per lib that attaches its mixin to `Base`; `models/__init__.py` imports them all |
| `routes/<module>.py` | `def register(app)` per module, thin handlers over library functions |
| `alembic/versions/` | one revision chain; `tests/test_schema.py` fails on any drift |
| `tests/conftest.py` | a fake-mode app on a temporary SQLite file, built from the environment alone |

## demos/sdk_demo

| File | What to copy from it |
|---|---|
| `lib/main.dart` | path URL strategy, `ensureSemantics()`, error capture before `runApp` (a walk harness only) |
| `lib/src/pages.dart` | the `demoPages` registry: path, title, id, builder, module, phase |
| `lib/src/example_api.dart` | `DemoSession`: one shared `ApiClient`, an in-memory token store, gateways, `ensureSignedIn()`, renewal on 401 |
| `lib/src/errors.dart` | `DemoErrors`: framework errors shown in an inline strip, so no dialog is needed |
| `lib/src/theme.dart` | `BondTheme.build(BondTokens.fallback)` and a `DemoScope` that installs tokens and labels |
| `lib/src/pages/page_scaffold.dart` | `PageFrame`, `PlaceholderPage` |
| `test/<page>_test.dart`, `e2e/` | widget tests per page; the Playwright scaffold |

## Semantics ids

Every interactive or asserted element wears `Semantics(identifier: 'sdk.<page>.<element>', label: '<human name>')`.
The identifier is the DOM attribute `flt-semantics-identifier`, so a walk selects
`[flt-semantics-identifier="sdk.auth.user"]`. A `ValueKey` is not in the DOM.

| Pattern | Example |
|---|---|
| `sdk.<page>.<element>` | `sdk.api.result`, `sdk.sync.rows`, `sdk.ui.button` |
| `sdk.nav.<id>` and `sdk.home.route-<id>` | `sdk.nav.auth` |
| `sdk.<id>.placeholder` | `sdk.tasks.placeholder` |
| `<key>-<value>` for segmented and select options | `<key>` is the field id |
| `sdk.errors` | the error strip; it must be absent after every step |

`bond_ui` widgets take an optional `semanticsId` and wrap themselves, so an app inherits walkable widgets.

## Walking it

The recipe (start both servers, enable semantics after each load, selectors, typing into fields, the error check on every route,
cleanup) is `docs/test/WEB.md`. Servers are started in the background with their pids saved under `tmp/logs/`.
