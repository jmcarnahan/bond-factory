# Reading the SDK examples

`services/sdk_example` (FastAPI, port 8012) and `demos/sdk_demo` (Flutter web, port 8078) wire every module end to
end in fake mode. Use them as few-shot examples: find the module in the table, open its files, copy the shape into the
app. They are never shipped. `README.md` here covers consuming; `docs/migration/README.md` points to the per-app adapters.
The `*Labels` objects (`ApiLabels`, `BondLabels`, `TaskLabels`, `ConnectionLabels`) are in each package README; mapping them to an app's translations is the app's job.

## Run both

- Once: `make setup-py` at the repo root (workspace virtual environment).
- API: `make serve-example` serves on :8012 through the `create_app` factory. With no environment variables it starts in
  fake mode (mock identities, demo sign-in, generated keys) and logs one warning. Check it with `curl -s localhost:8012/health`.
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
| `SDK_EXAMPLE_NATIVE_SCHEMES` | `org.example.sdkdemo` | device-bound reverse-domain scheme for the native return (the lib needs a dot); a dev and test fallback only, the https app link is production. `SDK_EXAMPLE_NATIVE_REDIRECTS` is a deprecated alias |
| `SDK_EXAMPLE_ALLOW_FAKE_PUBLIC` | unset | fake mode on an https public base is refused at startup unless this is set |
| `SDK_EXAMPLE_BREAKGLASS` | off | `1` serves `POST /auth/firebase` as break-glass for rows with `allow_password` (the demo user only), shows the link on the sign-in screen and sets `email_password` true in `/auth/providers` |
| `BOND_APPLE_APP_IDS`, `BOND_ANDROID_APPS` | unset | values for `/.well-known/apple-app-site-association` and `assetlinks.json` (`BOND_APPLE_APP_IDS` csv; `BOND_ANDROID_APPS` as `package=FP;FP,pkg2=FP`); both answer 404 while empty |
| `BOND_AUTH_REFRESH_TTL_DAYS`, `BOND_AUTH_REFRESH_MAX_DAYS`, `BOND_AUTH_REFRESH_PROBE_HOURS`, `BOND_AUTH_REFRESH_REUSE_GRACE_SECONDS`, `BOND_AUTH_REFRESH_MAX_SESSIONS_PER_USER`, `BOND_AUTH_SESSION_ACCESS_TTL_MINUTES` | 90, none, 0 (off), 20, 10, 60 | idle window, absolute cap, IdP probe hours, grace, families per user, access lifetime |
| `BOND_SYNC_*` | unset | read by `SyncTokenSettings.from_env()`: `PRIVATE_KEY`, `PRIVATE_KEY_FILE`, `KID`, `PREVIOUS_KEY`, `PREVIOUS_KEY_FILE`, `PREVIOUS_KID`, `AUDIENCE`, `MINUTES`; in fake mode a missing key is generated into `out/sync_key.pem` |

## Which module shows where

| Module | Service files (`services/sdk_example/sdk_example/`) | Demo page (`demos/sdk_demo/lib/src/pages/`) | Walk route |
|---|---|---|---|
| `bond_api`, `bond_json` | `routes/health.py` | `api_page.dart`: health, a 404, a validation error | `/api` |
| `bond_ui` | none | `ui_page.dart` and `ui/`: every widget once | `/ui` |
| `bond_test_support` | none | every `test/<page>_test.dart` (`pumpApp`, `expectNoOverlays`) | none |
| `bond_service_kit` | `wiring.py`: error handlers, middleware, clock, limiters; `db.py`; `routes/fake_todo.py` mounts `fake_clock_router` (with `clock_pin.py`) | none | none |
| `bond_auth_py`, `bond_auth`, `bond_auth_firebase` | `routes/auth.py` (`/auth/firebase` break-glass, `/auth/demo`, `/auth/me`), `auth_dep.py`, `models/auth.py`, `models/sessions.py` | `auth_page.dart`: sign in, refresh, forced 401, simulate reuse, sign out | `/auth` |
| `bond_signin` (lib), `bond_signin`, `bond_signin_ui` | `signin_wiring.py` (`UserDirectory`, `ScopePolicy`, `SignInFlow`, the mount of `make_signin_router` and `well_known_router`), `models/handoffs.py`, `models/sessions.py`; routes `POST /auth/signin/{p}/start`, `GET /auth/signin/{p}/callback`, `POST /auth/signin/redeem`, `POST /auth/refresh`, `POST /auth/logout`, `POST /auth/sessions/revoke-all`, `POST /auth/simulate-reuse` (fake mode); `routes/signin.py`, `connect_helpers.py`, `fake_routes.py` (consent page `GET /connections/fake/consent`, ids `sdk-consent-identity`, `-email`, `-set-<id>`, `-allow`, `-deny`, then `/consent/submit`), `routes/connect_native.py`, `break_glass.py`, `directory.py` (with the optional `apply_profile` hook, which fills an e-mail-only invitee's name at first sign-in), `scope_policy.py`, `providers_wiring.py` (providers and the providers payload), `origin_rule.py`, `signin_prune.py` | `auth_page.dart` on `BondSignInScreen`; `connections_page.dart` with `BondScopeAskCard` | `/auth`, `/connections` |
| `bond_storage` | `routes/storage.py` (upload, share, `GET /d/{token}`), `models/grants.py` | none; see `tests/test_storage.py` | none |
| `bond_jobs` | `models/jobs.py`, the registry in `wiring.py`; `scripts/sweep_interval.py` runs `run_schedule` | none | none (the sweep row below) |
| `bond_sync_py`, `bond_sync`, `bond_sync_powersync` | `routes/sync.py`, `models/sync.py` | `sync_page.dart`: rows, upload verdicts, token | `/sync` |
| `bond_oauth` | `routes/connections.py`, `oauth_wiring.py`, `models/connections.py`; routes: `GET /connections`, `GET /connections/{provider}/start`, `GET /connections/{provider}/go?state=` (sets the nonce cookie, then redirects to the provider), `GET /connections/{provider}/callback`, `POST /connections/{provider}/redeem` (device secret), `DELETE /connections/{provider}`, `GET /connections/fake/consent`, `POST /connections/{provider}/simulate-expiry` | `connections_page.dart` | `/connections` |
| `bond_tasks_py`, `bond_tasks`, `bond_tasks_ui` | `tasks_wiring.py` (mirror providers, name lookups), `todo_wiring.py` (preferences, link resolver, inbox, push sender, capture model and guard), `task_support.py` (one transaction, the viewer's zone, the wire item, the write hook), `routes/tasks.py` (CRUD, lifecycle, `/tasks/summary`), `routes/task_today.py` (`/tasks/today`, `/tasks/settings`), `routes/jobs.py` (`POST /jobs/tick`), `models/tasks.py`, `models/task_settings.py`, `models/task_links.py`, `models/task_ledger.py` | `tasks_page.dart`: quick add, list, mirror, summary; `today_page.dart`, `todo_calendar_page.dart`, `todo_settings_page.dart` | `/tasks`, `/today`, `/calendar`, `/todo-settings` |
| `bond_jobs` with the notice sweep | `sweep_wiring.py` (`run_sweep` claims then delivers, `before_hook` for `bond_jobs.tick(..., before=, before_every=)`, `sweep_app`), `routes/jobs.py` (fake-mode `POST /jobs/tick {now}` runs the sweep, then the due jobs), `scripts/sweep_interval.py` (the same sweep from a plain timer, no jobs table; `--every` must be at least 1) | the fake-clock strip on `/today` and `/inbox` | `/today`, `/inbox` |
| `bond_notify_py`, `bond_notify`, `bond_notify_ui` | `models/notices.py`, `routes/notices.py` (`GET /notices`, read, dismiss, read-all, `POST /notices/{id}/act`), `InboxNotifier` in the sweep | `inbox_page.dart`: badge, polling and watch feeds, rows with the three actions, undo | `/inbox` |
| `bond_push_py`, `bond_push`, `bond_tasks_notifications` | `models/push.py`, `routes/push.py` (`POST /push/devices`, `DELETE /push/devices/{id}`), the mock sender and `GET /fake/push/sent` in `routes/fake_todo.py`; real mode builds an `ApnsSender` only when `SDK_EXAMPLE_APNS_KEY_FILE`, `_KEY_ID` and `_TEAM_ID` are set | `lib/src/todo/todo_alerts.dart` (the coordinator, the only alert wiring; the plugin classes `PushPlugin`, `DefaultPushPlugin`, `PluginPushTokenSource` and `PluginPushTaps` come from `package:bond_push_apple/bond_push_apple.dart`, the rest from `bond_push`), the iOS simulator lane | `docs/test/MOBILE.md` |
| `bond_capture_py` | `capture_wiring.py` (the replay model, the rate guard, the accepted-event log), `routes/task_capture.py` (`POST /tasks/parse`, `GET /tasks/links/search`, the event stub), `contacts.py` (the link resolver and entity resolver over invented contacts) | `capture_page.dart`: note field, review, events sent | `/capture` |
| `bond_sync_powersync` and the two TODO sync adapters | `sync_todo.py` (the sync upload hosts `notes`, `tasks`, `notices` (patch `read_at`, `dismissed_at`) and `push_devices` (put, patch, delete), through the libs' handlers), `routes/sync.py` | `lib/src/todo/sync_mirror_notice_feed.dart` (the demo's stand-in for the watch feed) | `/inbox` (Watch feed) |
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
| `signin_wiring.py`, `directory.py`, `scope_policy.py` | the reference adapter: `UserDirectory` (about 110 lines, with the optional `apply_profile` hook that fills an e-mail-only invitee's name at first sign-in), `ScopePolicy`, the flow and mount; the service README has a copy-as-is / replace table |
| `alembic/versions/` | one revision chain; `tests/test_schema.py` fails on any drift. `0004_tasks_due.py` adds `priority` and `due_at`, `0005_todo_tables.py` the six TODO tables and drops `remind_at` and `reminded_at` |
| `todo_wiring.py`, `sweep_wiring.py`, `capture_wiring.py`, `contacts.py` | the TODO reference wiring. Files that say REPLACE in their first line (the fake model, the contact list) are the parts an app swaps for its own |
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
| `sdk.tasks.<element>` (also per row: `mirror-<id>`, `delete-<id>`) | `sdk.tasks.quick-add`, `sdk.tasks.summary`, `sdk.tasks.reload` |
| `sdk.today.<element>`, `sdk.inbox.<element>`, `sdk.capture.<element>`, `sdk.calendar.<element>`, `sdk.todo.<element>` (the settings page) | `sdk.today.row-<id>`, `.complete-<id>`, `.section-overdue`, `.task-<id>.banner-done`, `.form-title`, `sdk.inbox.badge`, `.feed-watch`, `.list.row-<id>-snooze`, `sdk.capture.text`, `.parse`, `.review-accept`, `sdk.calendar.grid-<date>` (the day cell: click it to select the day, read its label such as "12, 2 due"), `sdk.calendar.marker-<date>` (the count marker inside the cell, whose own label is the count text such as "2 due"), `sdk.todo.settings-end`; the fake-clock strip: `<page>.clock-now`, `.clock-tick`, `.clock-state` |
| `sdk.signin.<element>` | `sdk.signin.fake-google`, `sdk.signin.fake-microsoft`, `sdk.signin.error`, `sdk.signin.break-glass` |
| `sdk.auth.<element>` (signed in) | `.user`, `.capabilities`, `.token-tail`, `.refresh`, `.refresh-result`, `.simulate-reuse`, `.sign-out`, `.signed-out`, `.loading`, `.ended`, `.error`, `.force-401`, `.force-401-result`, `.renewals`; the break-glass form: `.email`, `.sign-in`, `.sign-in-demo`, `.not-invited` |
| `sdk.scopes.ask-<set>` | `sdk.scopes.ask-mail_send`, `sdk.scopes.ask-calendar` (one button per ungranted wanted set) |
| `sdk.connections.<element>` | `sdk.connections.list`, `sdk.connections.start-url`, `sdk.connections.return`, `sdk.connections.simulate-expiry-<provider>` |
| `<key>-<value>` for segmented and select options | `<key>` is the field id |
| `sdk.errors` | the error strip; it must be absent after every step |

`bond_ui` widgets take an optional `semanticsId` and wrap themselves, so an app inherits walkable widgets.

## Riverpod wiring

Names come from the barrels of `bond_api`, `bond_auth`, `bond_signin`, `bond_signin_ui` and (for the keychain store)
`bond_auth_secure_storage`; the shape is `DemoSession` in
`lib/src/example_api.dart`. One `ApiClient`, one `TokenStore`, one `RefreshTokenStore`, and two gateways over them:
`OidcAuthGateway` (direct sign-in) and `FirebaseAuthGateway` (break-glass). An `AuthGateway` provider names the gateway that
made the session, so renewal goes through it; gateway and client each keep one single flight, so parallel 401s renew once.

```dart
import 'package:bond_auth_secure_storage/bond_auth_secure_storage.dart'; // SecureRefreshTokenStore moved here from bond_signin_ui

final tokensProvider = Provider<TokenStore>((_) => InMemoryTokenStore());
final refreshStoreProvider = Provider<RefreshTokenStore>((_) =>
    kIsWeb ? const NoRefreshTokenStore() : SecureRefreshTokenStore(appKey: 'app'));
final apiProvider = Provider((r) => ApiClient(baseUrl: base, http: client, isWeb: kIsWeb, tokens: r.watch(tokensProvider)));
final oidcProvider = Provider((r) => OidcAuthGateway(api: r.watch(apiProvider), authPrefix: '/auth',
    tokens: r.watch(tokensProvider), refreshTokens: r.watch(refreshStoreProvider)));
final breakGlassProvider = Provider((r) => FirebaseAuthGateway(api: r.watch(apiProvider), source: idTokenSource,
    tokens: r.watch(tokensProvider), refreshTokens: r.watch(refreshStoreProvider)));
final gatewayProvider = StateProvider<AuthGateway>((r) => r.watch(oidcProvider)); // Riverpod 2; Riverpod 3 apps use a Notifier. Break-glass success sets the other
// AuthNotifier.build: api.onUnauthorized = () => renewalHook(ref.read(gatewayProvider), expectedUserId: state.userId)();
// AuthNotifier._from(AuthSession s) => AuthState(userId: s.userId, capabilities: s.capabilities, user: s.user);
```

Also set the client's `onSessionExpired`, `onSessionRevoked`, `onDeactivated` to clear the state; `AuthFailure.code` is the server code.

## Adoption-gap seams in three snippets

A phone client whose server answers 401 with a business code. The default treats every 401 as a lost session; this keeps
the session when the code is the app's own:

```dart
final api = ApiClient(
  baseUrl: base, http: client, tokens: tokens,
  endsSession: (ErrorBody e) => e.code != 'mail_account_not_connected', // false: no renewal, no hooks, Unauthorized with the code
);
```

A worker with no jobs table: two schedules on one thread, fixed rate, stopped cleanly by SIGTERM
(`services/sdk_example/scripts/sweep_interval.py`):

```python
from bond_jobs import Every, run_schedule

run_schedule([Every(60, sweep, name="sweep"), Every(3600, prune, name="prune")],
             on_result=lambda entry, result, error: print(entry.name, error or "ok"))
```

A clock the walk can pin, closed unless the app says otherwise (`routes/fake_todo.py`):

```python
from bond_service_kit import fake_clock_router

app.include_router(fake_clock_router(clock, enabled=lambda: settings.mode == "fake",
                                     dependencies=[Depends(current_user_id)]))
```

## Web token delivery

As `example_api.dart` and `example_http_client_web.dart` do: the refresh token is an HttpOnly cookie, so the store is
`NoRefreshTokenStore` and the client is a `BrowserClient` with `withCredentials = true`; same-origin calls carry the cookie. The
access token stays in memory; after a `signin=ok` return or a reload, `OidcAuthGateway.completeWeb()` fetches it (`POST /auth/refresh`).
A cookie-authenticated mutation needs an allowed `Origin` (`origin_rule.py`). A 401 calls `refreshSession()` once, then replays
(`test/auth_page_test.dart`, "a forced 401 renews exactly once").

## Real mode and walking it

The examples run in fake mode only. Real Firebase, identity-provider and PowerSync settings: `docs/contracts/` (`auth.md`,
`sync_upload.md`, `error_body.md`) and the package READMEs. Walk recipe: `docs/test/WEB.md` (servers in the background, pids under `tmp/logs/`).
