# Cutting an app over to bond_signin

Read with `bond_signin.md` (what each app writes, console setup) and `docs/contracts/signin.md`. This note is the order of
work, the mount details and the traps found in the dry run. Pointers are into `services/sdk_example/sdk_example/` (the
reference adapter); `README.md` there has a copy-as-is / replace table for every file.

## 1. Mount under the app's prefix (A, P: `/api/v1/auth`; S: the default `/auth`)

- `make_signin_router(..., prefix="/api/v1/auth")` on the server; the Dart side takes the same string:
  `OidcAuthGateway(authPrefix:)` and `SignInApi(prefix:)`. The default is `/auth`. The mount is `signin_wiring.py` `install_signin`.
- The prefix moves every route (start, callback, redeem, refresh, logout, revoke-all, providers). The native return page and
  the well-known files sit at the parent of the prefix (`/api/v1/app/return/<provider>`); register that as the app link path. The app's own routers (`/me`, `/demo`, break-glass) carry their own prefix.
- S serves `/auth` and `/connections` at the root (`sbelcrm/rest/routers/auth.py:50`, `connections.py:167`), so its prefix is the default `/auth`:
  pass no `prefix=`.
- Register at the provider only the sign-in callback `<public_base><prefix>/signin/<provider>/callback`, plus the connect
  callback when the app has connections.

## 2. Apps without connections (P)

Delete `routes/connections.py`, `routes/connect_native.py` and `models/connections.py`; no connect callback is registered and
the connection model is not passed to the router. Provider fields come from `providers_wiring.py` `ensure_wiring` (the example's one place that
builds the provider objects and the wiring). `oauth_wiring.py` is replaced by that file plus the settings.
This applies to identity-only sign-in (P, and A's login). A sign-in set that carries `offline_access` or any mail or
calendar scope (S) stores a connection at sign-in, so S keeps `models/connections.py` and the connection model.

## 3. Router arguments that are required in practice

- `providers_payload=` is REQUIRED with `include_providers=True` (`signin_wiring.py` `install_signin`, the `payload` function): without it the app's own
  `/providers` fields (Firebase config, flags) vanish from the answer. `AuthSettings.email_password_enabled` follows the
  break-glass flag (`wiring.py` `build_auth_settings`).
- `legacy_refresh=` is REQUIRED while installed builds still post `{id_token}` to refresh (`break_glass.py`); drop it when the
  minimum build no longer does.
- Env names come from `bond_signin.from_env(prefix="BOND_SIGNIN_")`: `PROVIDERS`, `PUBLIC_BASE`, `REDIRECT_ALLOWLIST`,
  `NATIVE_RETURN_BASE`, `NATIVE_SCHEMES`, `BREAKGLASS`, `COOKIE_SECURE` (default true), `ALLOW_HTTP`, `PREFIX`. `BOND_SIGNIN_BREAKGLASS` is
  that lib key; `SDK_EXAMPLE_BREAKGLASS` is the example-only flag (the example never reads `BOND_SIGNIN_*`). The other families: `bond_signin.md` section 3.
- Providers: `GoogleOAuth(client_id, client_secret, http)` and `MicrosoftOAuth(client_id, client_secret, http, tenant=<GUID>,
  pinned_tenant=<GUID>)` (`oauth_wiring.py` `build_wiring`). The pin is enforced in ONE place: `SignInFlow(pinned_tenants=...)`
  (`signin_wiring.py` `build_signin`); a non-GUID tenant refuses at startup.

## 4. Cutover for installed builds

- `POST /auth/firebase` answers 404 unless break-glass is on; `GET /connections` is now an object `{connections, wanted}`;
  access tokens last 60 minutes. Builds that call the old routes break the day the server changes.
- Renewal paths that held a 7-day token (PowerSync credential fetch, background upload, token bridges) must renew through the
  gateway's single flight, or they hold a dead token after an hour.
- Decide one of: release the client first (server keeps `legacy_refresh` and the old shapes), or a compatibility window with a
  minimum build date after which the server drops them. Do not switch the server first.

## 5. Postgres before cutover

The reuse and claim race, the hand-off claim, the partial unique index, the `lower(email)` lookup and the Alembic autogenerate
check all ran on SQLite only. Before cutover run `make -C libs/bond_auth_py test` and `make -C libs/bond_oauth test` against
Postgres, apply the app's sign-in revision (section 7) to a Postgres copy, and check `alembic revision
--autogenerate` shows an empty diff. Treat any difference as a blocker.

## 6. Web

- App and API share one registrable domain (SameSite=Lax); the refresh cookie path is the prefix.
- Use the path URL strategy. Fragments survive the return now, but hash routing stays discouraged.
- The app's own cookie-authenticated mutations need the Origin rule: copy `origin_rule.py` as is. The sign-in routes check it
  themselves.
- `client_ip` must use the last `X-Forwarded-For` hop, the one the nearest proxy appended (`wiring.py` `client_ip`); earlier hops are
  client-controlled and must not key the rate limit.

## 7. Data

- Columns and indexes: copy the contents of `alembic/versions/0003_signin.py` into a revision named by the app's own scheme (S:
  `NNN_<name>.py` after head 082): `uq_users_identity`, the `auth_sessions` and `oauth_handoffs` indexes. `user_fk_target = None` on the sessions model when the app's user ids are not strings.
- `find_invite(session, emails, provider, *, subject=None)` may match a pre-known subject; `directory.py` `Directory.find_invite`. Export
  `IdentityTaken` and `SignInRefused` from `bond_signin`.
- Backfill sketch (one-off script, run once): for each users row with a Firebase uid, read the Firebase `providerData` entry for
  `google.com` and write its `uid` to `identity_subject` with `identity_provider = "google"`. Rows without one link at first
  sign-in by verified e-mail. A subject already on another row is `identity_mismatch`; list those for a person to decide.
- Run the prune job: `signin_prune.py` enqueues one job a day for hand-offs and sessions; an app with its own scheduler calls
  both libraries' `prune` there.

## 8. S before sign-in

S moves to the SDK auth contract first (`bond_auth.md` section 1: `sub` = user id, `iat`, code bodies, 403 for a mismatch).

- Invite matching for S: the lib tries the Graph `mail` address, then the id_token `email`, then the UPN. Invites key on the mailbox
  address (decision 2026-11-09), which equals the invite e-mail; or store both addresses on the row.
- Cookie rename: S today sets a plain `access_token` (`routers/auth.py:166-185`) and reads it first (`dependencies/auth.py:33-35`), so a
  bad access cookie is a 401 even when a valid bearer header is present. Rename to the SDK name `<app>_access_token` and clear the old
  cookie at the first sign-in; the SDK reads the bearer first, then the new cookie name, and never the old cookie.
- `needs_reconnect` is supported on the server: `bond_oauth` `access_token` raises `ReconnectRequired` and writes `last_error`, and the
  status route reports it.

## 8a. Session defaults

Refresh sessions slide over 90 idle days with no absolute cap; they end by sign-out, reuse detection, an admin action or idleness.
Set `BOND_AUTH_REFRESH_MAX_DAYS` to add a cap (S with Conditional Access may need one). The IdP probe is off; set
`BOND_AUTH_REFRESH_PROBE_HOURS` and implement `provider_alive` to turn it on.

## 9. Order

1. SDK pin bump, raise `IPHONEOS_DEPLOYMENT_TARGET` and the Podfile platform to 17.4 (https return is production), `bond_auth` and `bond_auth_py` adoption, `bond_oauth` adoption with `bond_connections` (connections cut over here; existing notes).
2. Models, revision, directory, policy, settings; tests in fake mode; Postgres run (section 5).
3. Console setup, then the FIRST LIVE provider run in a staging copy.
4. Client release with the new gateway; then the server mount; then drop `legacy_refresh` after the minimum build date.
5. Backfill, prune job, `docs/sdk/sdk-pins.md` row, delete the dead Firebase sign-in code (A, P; S keeps the break-glass path).
