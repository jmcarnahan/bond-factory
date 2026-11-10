# sbel-crm: per-app facts for the module migration

S facts for the sign-in, auth, oauth, connections and api notes. Paths are sbel-crm paths unless they start with `libs/`,
`packages/` or `services/`. Measured 2026-11-09 on main `26760f02`; re-run the greps. Order of work: `bond_signin-cutover.md`.

## 1. Contract migration (auth)

| Claim | Today (`sbelcrm/rest/routers/auth.py:149-163`) | SDK (`libs/bond_auth_py/bond_auth_py/tokens.py:45-46`) |
|---|---|---|
| `sub` | e-mail | user id |
| `user_id` | user id | user id (same value as `sub`) |
| `role`, `is_admin`, `provider`, `iss` | set | dropped: `capabilities` list; the row decides |
| `iat` | absent | required |
| `sid` | absent | session id (set by `sessions_base.py:78` on issue and rotate) |

- **Safe swap.** The decoder rejects a token without `sub` or `user_id` (`sbelcrm/rest/dependencies/auth.py:84`) and loads
  the user by `UserRecord.id == claims["user_id"]` (`:98`), so role, `is_admin` and `is_active` come from the row. The
  SDK token carries both claims. The `?token=` path in `routers/connections.py:181,231` uses the same decoder.
- **Shim.** Keep `create_access_token` in `routers/auth.py:31` under its name and let it emit both claim sets for the
  tests: `grep -rl create_access_token tests | wc -l` gives 50 files (helpers: `tests/conftest.py:197`, `:358`).
- **Code map.** Today `{"error_code", "detail"}` (`routers/auth.py:46-47`, `_refuse`). The SDK body is `{"detail": {"code", "message"}}`.

| Today (`routers/auth.py`) | Status | SDK code | Status (`libs/bond_auth_py/bond_auth_py/errors.py:38-63`) |
|---|---|---|---|
| `NOT_INVITED` (:91) | 403 | `not_invited` | 403 |
| `USER_DEACTIVATED` (:96) | 403 | `deactivated` | 403 |
| `INVALID_ID_TOKEN` (:77) | 401 | `invalid_id_token` (sign-in), `invalid_token` (session) | 400, 401 |
| `AUTH_UNAVAILABLE` (:79) | 503 | `provider_error` (sign-in) | 502 |
| `EMAIL_NOT_VERIFIED` (:74) | 403 | `email_not_verified` | 403 |
| `IDENTITY_MISMATCH` (:101, :109, :123) | 409 | `identity_mismatch` | 403 |

- **Dart switches** that parse the codes: web `flutterui/lib/data/services/id_token_source.dart:87-95` (reads
  `errorCode`), phone `mobile/crm_proposals/lib/core/auth/firebase_gateway.dart:183-191` (`e.errorCode`). Both match
  upper-case strings and a flat body; each moves to `AuthFailure.code` (lower case) with the SDK gateways.
- **Stale cookie.** Today a present cookie wins, and a bad access cookie is a 401 even when a valid bearer header is present (section 2). The SDK
  (`services/sdk_example/sdk_example/auth_dep.py:69-75`) reads the bearer first, then only the new cookie name, and a
  bad token is a 401 `invalid_token` that the client answers with one `POST /auth/refresh` and a replay. The old
  `access_token` cookie is never read again, so it counts as absent.

## 2. Cookie map

| | Today | SDK |
|---|---|---|
| Access cookie | `access_token`, HttpOnly, SameSite=Lax, path `/`, Secure from `COOKIE_SECURE`, max-age = access minutes (`routers/auth.py:169-176`) | `<app>_access_token` (`bond_auth_py/tokens.py:77`), same flags, Secure from `BOND_SIGNIN_COOKIE_SECURE` |
| Refresh cookie | none | HttpOnly, SameSite=Lax, path `/auth` (`refresh_cookie_path`, `bond_auth_py/settings.py:44`) |
| Set by / cleared by | `POST /auth/firebase` (deleted with the migration); `POST /auth/logout` (`:185`) | the sign-in router and `finish_session`; logout clears both and the old `access_token` |
| Read | cookie FIRST; a bad cookie is a 401 even with a valid bearer header (`dependencies/auth.py:30-41`) | bearer first, then the new cookie only (`bond_auth_py/tokens.py:103-113`) |

Web renewal: the access token is kept fresh from the refresh cookie (`docs/sdk/examples.md`, Web token delivery); auth routes are called at
the origin root because the refresh cookie Path is `/auth`.

Rule: on the first SDK deploy, clear the old `access_token` at sign-in and at logout, and treat a bad old cookie as
absent. Every web user signs in once more (a one-time web logout); say so in the release note.

## 3. Settings map

| sbel env (`sbelcrm/config.py`) | SDK env or argument | Verified |
|---|---|---|
| `JWT_SECRET_KEY` (:72) | `BOND_AUTH_JWT_SECRET`, else `JWT_SECRET_KEY` (`bond_auth_py/settings.py:97`), so the name can stay | yes |
| `ACCESS_TOKEN_EXPIRE_MINUTES` 1440 (:78) | leave the SDK default 60 min (`bond_auth_py/settings.py:37`); do NOT set `BOND_AUTH_SESSION_ACCESS_TTL_MINUTES=1440` (renewal is built); the old name still feeds the non-session `access_ttl_minutes` | yes |
| `JWT_ISSUER`, `JWT_AUDIENCE` (`branding.py:138-139`, defaults `sbelcrm`, `sbelcrm-api`) | `BOND_AUTH_ISSUER=sbelcrm`, `BOND_AUTH_AUDIENCE=sbelcrm-api` (`bond_auth_py/settings.py:117-118`); the SDK defaults `bond`/`bond-api` would invalidate live tokens | yes |
| `COOKIE_SECURE` (`routers/auth.py:168`) | `BOND_SIGNIN_COOKIE_SECURE` (default on; `bond_signin/settings.py:92`) | yes |
| `FRONTEND_URL` (:96), `CORS_ALLOWED_ORIGINS` (:92) | `BOND_SIGNIN_PUBLIC_BASE` (https) and `BOND_SIGNIN_REDIRECT_ALLOWLIST` (origins) | yes |
| `MICROSOFT_CLIENT_ID`, `_SECRET`, `_TENANT_ID` (:712-714) | `BOND_MS_CLIENT_ID`, `BOND_MS_CLIENT_SECRET`, `BOND_MS_TENANT` (GUID; `common` refused) (`services/sdk_example/sdk_example/oauth_wiring.py:67-70`) | yes |
| `MICROSOFT_REDIRECT_URI` (:715) | derived: `<base>/auth/signin/microsoft/callback` (`bond_signin/settings.py:70`) and `<base>/connections/microsoft/callback` (`oauth_wiring.py:78`) | yes |
| `ADMIN_USERS` (:88) | S writes the promotion inside its own `find_invite`/`record_sign_in` (the example has none; docstring `directory.py:41`) | yes |
| `MICROSOFT_OFFICE_TOOLS_ENABLED` (:122) | the ScopePolicy list (section 4) | yes |
| new | `BOND_OAUTH_KEY`, `BOND_SIGNIN_PROVIDERS=microsoft`, `BOND_SIGNIN_NATIVE_SCHEMES` (the phone's reverse-domain scheme, always on: S uses the scheme return) | yes; not used by S: `BOND_SIGNIN_BREAKGLASS` (no break-glass), `BOND_APPLE_APP_IDS`/`BOND_ANDROID_APPS` (no app link yet) |

## 4. Scopes

Requested today: `Mail.Send Mail.Read Calendars.ReadWrite MailboxSettings.Read User.Read`, plus `Contacts.ReadWrite
Files.ReadWrite` when `microsoft_office_tools_enabled`, plus `offline_access` (`sbelcrm/config.py:707-710`; the flag is
`MICROSOFT_OFFICE_TOOLS_ENABLED`, default false, `:122`, and stays false: S does not need the office pair yet). `microsoft_graph_service.py:35-36` only lists the required
subset for drift checks. Decision 2026-11-09: keep the scopes. S's sign-in set is `MICROSOFT_SIGNIN + MICROSOFT_BASE`
(plus `MICROSOFT_OFFICE` when the flag is on), composed from the named sets in `libs/bond_oauth/bond_oauth/scopes.py:13-18`:
`MICROSOFT_BASE` is `Mail.Send Mail.Read Calendars.ReadWrite MailboxSettings.Read User.Read offline_access` and `MICROSOFT_OFFICE` is
`Contacts.ReadWrite Files.ReadWrite`. `MICROSOFT_SIGNIN_FULL` (`:19`) lacks the last two groups, so S does not use it.

## 5. Data copy (connections)

- **Source** `oauth_tokens` (`sbelcrm/db/models.py:599-622`): `id`, `user_id`, `connection_name`, `access_token_encrypted`,
  `refresh_token_encrypted`, `token_type`, `expires_at`, `scopes`, `provider_metadata`, `created_at`, `updated_at`;
  unique on (`user_id`, `connection_name`). Copy rows where `connection_name = 'microsoft'` only. AES-GCM, key = HKDF
  of `JWT_SECRET_KEY` (`sbelcrm/auth/token_encryption.py:20-24`).
- **Target** `oauth_connections` (`libs/bond_oauth/bond_oauth/models.py:22-57`): `id`, `user_id`, `provider`,
  `connection_name`, `account_email`, `scopes`, `access_token_enc`, `refresh_token_enc` (not null), `token_type`,
  `expires_at`, `provider_metadata`, `connected_at`, `revoked_at`, `last_error`, `created_at`, `updated_at`. Fernet, `BOND_OAUTH_KEY`.
  `account_email` source is the user row (INFERENCE).
- Rows that fail to decrypt, or have no refresh token, are listed and not copied; those people reconnect. The old
  table stays for rollback. `oauth_states` is dropped later: the SDK state is stateless.
- **Shim.** `get_valid_token(user_id)` (`services/microsoft_graph_service.py:61`, called at `:358`) becomes a wrapper over
  `bond_oauth.access_token`. `grep -rn get_valid_token sbelcrm | wc -l` gives 6, of which 2 are Notion's own
  (`notion_service.py:97,317`) and one is a docstring (`send_as.py:4`). The Microsoft callers are `:358` and
  `services/msgraph/client.py:64`. Two direct readers of the table stay to be ported: `services/send_as.py:76` and
  `services/email_ingest/maintenance.py:173`.

## 6. Route collisions

`sbelcrm/rest/routers/connections.py` (922 lines) mixes three families:

| Family | Decorators |
|---|---|
| ByteProbe | `/connections/bytepro/status` (:101), two POSTs (:108, :132) |
| Microsoft | `/connections/microsoft/status` (:167), `/authorize` (:199), `/callback` (:313), `POST /disconnect` (:410) |
| Notion | `/connections/notion/...` (:444-886) |

Rule: the SDK connections router mounts first under `/connections`. S moves Notion and ByteProbe into their own file
that mounts after it. Microsoft routes in `connections.py` are removed. The phone hard-gates on
`GET /connections/microsoft/status` (`mobile/crm_proposals/lib/core/auth/auth_controller.dart:284,301`; web
`flutterui/lib/data/services/connection_api_service.dart:67`); both are rewritten against `GET /connections` in the same release,
and S has no compatibility window (the installed phone build is replaced through TestFlight at cutover), so the old
status route (`connections.py:155-167`) is deleted, not aliased.

## 7. Infra

- **nginx.** The railway template proxies `/api/ /auth/ /webhooks/ /connections/ /uploads/ /d/ /w/` only; `deployment/nginx.conf`
  also proxies `/login/` (`:80`). Add two blocks in both files, after the `/connections/` block (it ends `:113` in the template,
  `:133` in `nginx.conf`): `location /app/` for the native return page and `location /.well-known/` for the association files. Copy
  the style of `location /auth/` (`railway/nginx.conf.template:60-76`): `proxy_pass http://127.0.0.1:8000/<path>/;` with `Host`,
  `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`, then the five `add_header ... always;` lines (nginx does not inherit them).
- **Log scrubbing.** The return URL carries a one-time code in the query. Neither file sets `access_log` for the main
  server (`grep access_log deployment` finds only `nginx.dev.conf:33`), so the distro default logs the request line
  (INFERENCE). Add a `log_format` that logs `$uri` instead of `$request` and `$request_uri`, and keep the code out of app logs.
- **Build.** The Python stage installs no `git` (`deployment/railway/Dockerfile:44-60`; only the web stage does, `:16`),
  so Poetry `git+...#subdirectory=` pins need `git` added to the apt line. The Dart pins are `git: {url, ref: <40-char sha>,
  path: packages/<pkg>}` in both pubspecs (`flutterui`, `mobile/crm_proposals`), plus a gitignored
  `pubspec_overrides.yaml` for local dev (root `CLAUDE.md`).

## 8. Entra checklist (text for the tenant admin)

1. Add the redirect URI `<base>/auth/signin/microsoft/callback` under Web for each host (production, staging).
2. Keep the existing production `<base>/connections/microsoft/callback` redirect URI and add the same path for staging.
3. Confirm the registration is single-tenant (authority `https://login.microsoftonline.com/<tenant GUID>`).
4. Confirm the nine section 4 scopes (without the office pair) are consented tenant-wide. Identity scopes (`openid`, `profile`, `email`, `offline_access`) need no admin consent, but consenting them too keeps the consent screen away.
5. Tell us the client-secret expiry date and provide at least two test users (invited in the app).

## 9. iOS

First release: the SCHEME return only (the app's reverse-domain bundle id in `Info.plist` `CFBundleURLTypes`, listed in
`BOND_SIGNIN_NATIVE_SCHEMES`). The three bullets below (17.4 floor, entitlements, association file) belong to the https app
link and are post-demo hardening; none is needed for the scheme return.

- Post-demo hardening: raise `IPHONEOS_DEPLOYMENT_TARGET` from 15.0 to 17.4 at the three sites in
  `mobile/crm_proposals/ios/Runner.xcodeproj/project.pbxproj` (lines 454, 585, 637); the Podfile platform line is
  commented out (`ios/Podfile:2`): set `platform :ios, '17.4'`.
- Post-demo hardening: there is no `Runner.entitlements` and no `CODE_SIGN_ENTITLEMENTS`. Create it with Associated Domains `applinks:<host>`
  (host from the build environment, never in docs) and add the capability in Xcode.
- Post-demo hardening: serve the association file with `well_known_router` (`libs/bond_service_kit/bond_service_kit/well_known.py:17`); env
  `BOND_APPLE_APP_IDS` (`<TEAMID>.<bundle id>`, csv) and `BOND_ANDROID_APPS` (S has no `android/`).
- The reverse-domain scheme in `Info.plist` is the first-release return, not a dev-only fallback. The embedded
  web view connect screen (`connect_microsoft_screen.dart`) is replaced. SDK side: `local/plan/2026-11-09-direct-signin/reports/phone-flow.md`.

## 10. Test fixtures and first live run

- Token helpers: `tests/conftest.py:193-200` (`_auth_header`, `sub` = e-mail) and `:352-362` (admin). The Firebase fake
  (`FakeFirebase` `:366`, fixture `fake_firebase` `:444`) and the `FIREBASE_*` pins (`:9-13`) go with `sbelcrm.auth.firebase`.
- Narrowest lanes: `make tests-for ARGS="<changed files>"` prints the command (`make/tests.mk:115`). A full backend run
  first runs `lenders-pinned` (`Makefile:152`); a scoped `ARGS=` run does not. About 7,600 tests: run once, pre-PR.
- `demo_local.db` is built by `create_all`, not Alembic: delete it before `make demo-seed-local DEMO_WIPE=1` after a revision.
- First live run record (into `docs/sdk/sdk-pins.md`): provider, tenant kind, scopes granted, the refusal codes seen
  (section 1), hand-off timing on a device (start tap to signed-in screen).

## 11. Rollback

The columns are additive (identity columns and `sessions_valid_after`, which S adds itself: the directory needs it, `bond_signin/order.py:83`; no `allow_password`, S has no break-glass) and so are the tables
(`auth_sessions`, `oauth_handoffs`, `oauth_connections`), so the previous image runs unchanged on the migrated schema.
There is no break-glass: a rollback is the previous image (Firebase accounts were never deleted, so Firebase sign-in returns on it).
`oauth_tokens` is untouched, so the old image still connects (INFERENCE: a token the new image refreshed is not seen by it).
Client side: after a rollback web users sign in again (the old image never reads the new cookie); phone users reinstall the
previous TestFlight build. The new phone build must not reach external testers before the server cutover, and the old build
stops at cutover (no compatibility window): the two releases are done back to back.
