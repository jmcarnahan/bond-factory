# Reading the SDK examples

`services/sdk_example` (FastAPI, port 8012) and `demos/sdk_demo` (Flutter web, port 8078) wire every module end to
end in fake mode. Use them as few-shot examples: find the module in the table, open the files named for it, copy the
shape into the app. They are never shipped. `README.md` in this folder covers consuming the modules, and
`docs/migration/README.md` points to the per-app adapters. The `*Labels` objects (`ApiLabels`, `BondLabels`,
`TaskLabels`, `ConnectionLabels`) are documented in each package README; mapping them to an app's translations is the app's job.

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
| `SDK_EXAMPLE_SYNC_URL` | fake mode: `http://localhost:8012/powersync-fake`; real mode: empty | sync endpoint handed out by `POST /sync/token`; set it to empty to turn sync off (real mode: sync is off until it is set) |
| `BOND_OAUTH_KEY` | generated in `out/oauth.key` (fake mode) | token encryption key; real mode fails at startup without it |
| `SDK_EXAMPLE_PUBLIC_BASE` | fake mode: `http://localhost:8012`; real mode: required, https | public base of the API; the sign-in and connect callbacks and the native return base derive from it; must match what the providers registered |
| `BOND_GOOGLE_CLIENT_ID`, `BOND_GOOGLE_CLIENT_SECRET` | unset | real mode: Google is offered only when both are set |
| `BOND_MS_CLIENT_ID`, `BOND_MS_CLIENT_SECRET` | unset | real mode: Microsoft is offered only when both are set |
| `BOND_MS_TENANT` | unset | Microsoft tenant; sign-in needs a GUID and refuses `common`, `organizations`, `consumers` at startup |
| `SDK_EXAMPLE_SIGNIN_PROVIDERS` | fake mode: `fake-google,fake-microsoft`; real mode: none | sign-in providers offered; real names (`google`, `microsoft`) need their `BOND_GOOGLE_*` / `BOND_MS_*` pairs; a `fake*` name is refused outside fake mode |
| `SDK_EXAMPLE_NATIVE_RETURN_BASE` | `<public base>/app/return` | native return base; https app link in production |
| `SDK_EXAMPLE_NATIVE_SCHEMES` | `org.example.sdkdemo` | device-bound reverse-domain scheme fallback for the native return (the lib needs a dot); allowed in production too, list only what the app registers. `SDK_EXAMPLE_NATIVE_REDIRECTS` is a deprecated alias |
| `SDK_EXAMPLE_ALLOW_FAKE_PUBLIC` | unset | fake mode on an https public base is refused at startup unless this is set |
| `SDK_EXAMPLE_BREAKGLASS` | off | `1` serves `POST /auth/firebase` as break-glass for rows with `allow_password` (the demo user only), shows the link on the sign-in screen and sets `email_password` true in `/auth/providers` |
| `BOND_APPLE_APP_IDS`, `BOND_ANDROID_APPS` | unset | values for `/.well-known/apple-app-site-association` and `assetlinks.json` (`BOND_APPLE_APP_IDS` csv; `BOND_ANDROID_APPS` as `package=FP;FP,pkg2=FP`); both answer 404 while empty |
| `BOND_AUTH_REFRESH_TTL_DAYS`, `BOND_AUTH_REFRESH_MAX_DAYS`, `BOND_AUTH_REFRESH_REUSE_GRACE_SECONDS`, `BOND_AUTH_REFRESH_MAX_SESSIONS_PER_USER`, `BOND_AUTH_SESSION_ACCESS_TTL_MINUTES` | 60, 180, 20, 10, 60 | refresh lifetimes, grace, families per user, access lifetime |
| `BOND_SYNC_*` | unset | read by `SyncTokenSettings.from_env()`: `PRIVATE_KEY`, `PRIVATE_KEY_FILE`, `KID`, `PREVIOUS_KEY`, `PREVIOUS_KEY_FILE`, `PREVIOUS_KID`, `AUDIENCE`, `MINUTES`; in fake mode a missing key is generated into `out/sync_key.pem` |

## Which module shows where

| Module | Service files (`services/sdk_example/sdk_example/`) | Demo page (`demos/sdk_demo/lib/src/pages/`) | Walk route |
|---|---|---|---|
| `bond_api`, `bond_json` | `routes/health.py` | `api_page.dart`: health, a 404, a validation error | `/api` |
| `bond_ui` | none | `ui_page.dart` and `ui/`: every widget once | `/ui` |
| `bond_test_support` | none | every `test/<page>_test.dart` (`pumpApp`, `expectNoOverlays`) | none |
| `bond_service_kit` | `wiring.py`: error handlers, middleware, clock, limiters; `db.py` | none | none |
| `bond_auth_py`, `bond_auth`, `bond_auth_firebase` | `routes/auth.py` (`/auth/firebase` break-glass, `/auth/demo`, `/auth/me`), `auth_dep.py`, `models/auth.py`, `models/sessions.py` | `auth_page.dart`: sign in, refresh, forced 401, simulate reuse, sign out | `/auth` |
| `bond_signin` (lib), `bond_signin`, `bond_signin_ui` | `signin_wiring.py` (`UserDirectory`, `ScopePolicy`, `SignInFlow`, the mount of `make_signin_router` and `well_known_router`), `models/handoffs.py`, `models/sessions.py`; routes `POST /auth/signin/{p}/start`, `GET /auth/signin/{p}/callback`, `POST /auth/signin/redeem`, `POST /auth/refresh`, `POST /auth/logout`, `POST /auth/sessions/revoke-all`, `POST /auth/simulate-reuse` (fake mode); `routes/signin.py`, `connect_helpers.py`, `fake_routes.py` (consent page `GET /connections/fake/consent`, ids `sdk-consent-identity`, `-email`, `-set-<id>`, `-allow`, `-deny`, then `/consent/submit`), `routes/connect_native.py`, `break_glass.py`, `directory.py`, `scope_policy.py` | `auth_page.dart` on `BondSignInScreen`; `connections_page.dart` with `BondScopeAskCard` | `/auth`, `/connections` |
| `bond_storage` | `routes/storage.py` (upload, share, `GET /d/{token}`), `models/grants.py` | none; see `tests/test_storage.py` | none |
| `bond_jobs` | `models/jobs.py`, the registry in `wiring.py` | none | none |
| `bond_sync_py`, `bond_sync`, `bond_sync_powersync` | `routes/sync.py`, `models/sync.py` | `sync_page.dart`: rows, upload verdicts, token | `/sync` |
| `bond_oauth` | `routes/connections.py`, `oauth_wiring.py`, `models/connections.py`; routes: `GET /connections`, `GET /connections/{provider}/start`, `GET /connections/{provider}/go?state=` (sets the nonce cookie, then redirects to the provider), `GET /connections/{provider}/callback`, `POST /connections/{provider}/redeem` (device secret), `DELETE /connections/{provider}`, `GET /connections/fake/consent`, `POST /connections/{provider}/simulate-expiry` | `connections_page.dart` | `/connections` |
| `bond_tasks_py`, `bond_tasks`, `bond_tasks_ui` | `tasks_wiring.py` (scheduler, `task_reminder` handler, mirror providers), `routes/tasks.py` (CRUD, `/tasks/summary`, `/tasks/notices`), `routes/jobs.py` (`POST /jobs/tick`), `models/tasks.py` | `tasks_page.dart`: quick add, list, mirror, summary, run due jobs, notices | `/tasks` |
| `bond_calendar` | `calendar_wiring.py` (one provider per OAuth connection, fake calendars in fake mode), `routes/calendar.py` (`GET /calendar/events`) | none; the task mirror shows the external id | none |
| `bond_connections`, `bond_connections_ui` | the `bond_oauth` routes above | `connections_page.dart` (navigation helpers come from `bond_signin_ui`): status list, start URL, return banner, simulate expiry | `/connections` |

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
| `signin_wiring.py`, `directory.py`, `scope_policy.py` | the reference adapter: `UserDirectory` (about 110 lines), `ScopePolicy`, the flow and mount; the service README has a copy-as-is / replace table |
| `alembic/versions/` | one revision chain; `tests/test_schema.py` fails on any drift |
| `tests/conftest.py` | a fake-mode app on a temporary SQLite file, built from the environment alone |

## demos/sdk_demo

| File | What to copy from it |
|---|---|
| `lib/main.dart` | path URL strategy, `ensureSemantics()`, error capture before `runApp` (a walk harness only) |
| `lib/src/pages.dart` | the `demoPages` registry: path, title, id, builder, module, phase |
| `lib/src/example_api.dart` | `DemoSession`: one shared `ApiClient`, `OidcAuthGateway` (`oidc`), `NoRefreshTokenStore` on web (the cookie carries it), `signInWith()`, `completeWeb()`, `simulateReuse()`, `ensureSignedIn()` (tries `completeWeb`, then `POST /auth/demo`), renewal on 401 |
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
| `sdk.tasks.<element>` (also per row: `mirror-<id>`, `delete-<id>`) | `sdk.tasks.quick-add`, `sdk.tasks.summary`, `sdk.tasks.run-due-jobs`, `sdk.tasks.show-notices` |
| `sdk.signin.<element>` | `sdk.signin.fake-google`, `sdk.signin.fake-microsoft`, `sdk.signin.error`, `sdk.signin.break-glass` |
| `sdk.auth.<element>` (signed in) | `.user`, `.capabilities`, `.token-tail`, `.refresh`, `.refresh-result`, `.simulate-reuse`, `.sign-out`, `.signed-out`, `.loading`, `.ended`, `.error`, `.force-401`, `.force-401-result`, `.renewals`; the break-glass form: `.email`, `.sign-in`, `.sign-in-demo`, `.not-invited` |
| `sdk.scopes.ask-<set>` | `sdk.scopes.ask-mail_send`, `sdk.scopes.ask-calendar` (one button per ungranted wanted set) |
| `sdk.connections.<element>` | `sdk.connections.list`, `sdk.connections.start-url`, `sdk.connections.return`, `sdk.connections.simulate-expiry-<provider>` |
| `<key>-<value>` for segmented and select options | `<key>` is the field id |
| `sdk.errors` | the error strip; it must be absent after every step |

`bond_ui` widgets take an optional `semanticsId` and wrap themselves, so an app inherits walkable widgets.

## Real mode

The examples run in fake mode only. For a real Firebase id-token source, real identity-provider settings and PowerSync
endpoints, read `docs/contracts/` (`auth.md`, `sync_upload.md`, `error_body.md`) and the module READMEs
(`packages/bond_auth_firebase`, `packages/bond_sync_powersync`, `libs/bond_auth_py`, `libs/bond_sync_py`).

## Walking it

The recipe (start both servers, enable semantics after each load, selectors, typing into fields, the error check on every route,
cleanup) is `docs/test/WEB.md`. Servers are started in the background with their pids saved under `tmp/logs/`.
