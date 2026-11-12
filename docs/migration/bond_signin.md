# Migrating to bond_signin

Direct Google/Microsoft sign-in with our own refresh sessions, replacing Firebase sign-in. Server: `libs/bond_signin`
(Protocol-only router factory, check order, `ScopePolicy`) over `bond_oauth` (`SignInFlow`, `HandoffStore`) and
`bond_auth_py` (`SessionStore`). Client: `bond_signin`, `bond_signin_ui`. Contract: `docs/contracts/signin.md`.
Reference adapter: `services/sdk_example/sdk_example/signin_wiring.py`. Decision: `docs/decisions/2026-11-09-direct-signin.md`.
Order of work, prefix mount, installed-build cutover, Postgres run: `bond_signin-cutover.md`. Legend: `docs/migration/README.md`.

The app writes ONLY a `UserDirectory`, a `ScopePolicy`, settings and a mount. Order of work: land the SDK pin and
`bond_auth`/`bond_auth_py` first, then this (see README order). The first LIVE provider run happens here (section 6). S moves to the SDK auth contract before any of this.

## 1. What each app writes (INFERENCE sizes; before to after: A ~3,080 to ~940, S ~4,580 to ~1,100, P ~2,000 to ~625 lines)

| File | A | S | P |
|---|---|---|---|
| `auth/directory.py` | ~90: identity lookup, invite by `lower(email)` not removed, capabilities from `user_capabilities`, bookkeeping, `apply_profile` fill-only-when-empty | ~110: role to capabilities, admin e-mail list promotes inside `find_invite`, invite is UPN or `mail`, `apply_profile` fill-only-when-empty | ~80: invite lookup, `company_suspended`, `company_id` extra claim, audit, `apply_profile` fill-only-when-empty |
| Settings and policy | ~70 | ~60 | ~40 |
| Models and revisions | `identity_provider`, `identity_subject` (unique pair, nullable); `SessionsMixin`, `HandoffsMixin`; two revisions | same plus `sessions_valid_after` (S has none) and the connections table; three revisions | same minus connections; one revision |
| Router and deps | keeps `/me`, `PATCH /me`, `/demo`, `/providers`, `/firebase` (break-glass); mounts the SDK router | same; first moves to the SDK auth contract | same |
| Flutter | `OidcAuthGateway`, `SecureRefreshTokenStore` (package `bond_auth_secure_storage`, phones only), login screens on `BondSignInScreen`, return handling | same; the connect web view is replaced, not patched | admin web and crew phone screens |

`UserDirectory` methods (the app writes all): `find_by_identity`, `find_by_id`, `find_invite(session, emails,
provider)`, `link_identity` (raises `IdentityTaken`), `check_allowed`, `capabilities`, `session_spec`, `public`,
`mark_sessions_invalid`, `provider_alive`, `record_sign_in`, `record_refusal`; optional `apply_profile(session, user,
profile, *, provider, first)` (receives the IdP display name; fill an empty name). Signatures: `libs/bond_signin/README.md`.

## 2. ScopePolicy

| | Sign-in scopes | Asked after sign-in (by capability) | Notes |
|---|---|---|---|
| A (Google) | `openid email profile`, `access_type=online` | owner, office, sales: set `mail_send` (`gmail.send`) and `calendar` (`calendar.events`); crew none; owner and office the shared mailbox | identity-only sign-in stores no connection |
| S (Microsoft) | `openid profile email offline_access User.Read Mail.Send Mail.Read Calendars.ReadWrite MailboxSettings.Read`, plus `Contacts.ReadWrite Files.ReadWrite` when `MICROSOFT_OFFICE_TOOLS_ENABLED` is true (`sbelcrm/config.py:707-710`) | none | S's set is `MICROSOFT_SIGNIN + MICROSOFT_BASE` (+ `MICROSOFT_OFFICE` when the flag is on), composed from the named sets (`libs/bond_oauth/bond_oauth/scopes.py:13-18`); sign-in stores the connection, the old Connect step goes; tenant pinned; admin pre-consent shows no consent screen |
| P (Google) | `openid email profile` | none (empty policy) | no mail code, no connections table |

Roles are granted after sign-in, so `wanted` is recomputed on every `GET /connections`. Sign-in always succeeds with
identity scopes alone; a declined ask leaves the set `wanted`.

## 3. Settings and env

`SignInSettings` fields: providers, redirect allowlist (origins), public base (https outside fake mode), `native_return_base`, `native_schemes`,
break-glass flag (default off). `BOND_SIGNIN_BREAKGLASS` is the key the lib's `from_env(prefix="BOND_SIGNIN_")` reads
(`libs/bond_signin/bond_signin/settings.py:96`). `SDK_EXAMPLE_BREAKGLASS` is the example-only flag (`sdk_example/settings.py:130`): the example
builds `SignInSettings` itself (`signin_wiring.py:68`) and never reads `BOND_SIGNIN_*`.

Which env family sets what (an app picks its own prefixes; the per-app map is `docs/migration/sbel.md`):

| Family | Names | Read by |
|---|---|---|
| `BOND_SIGNIN_*` | `PROVIDERS PUBLIC_BASE REDIRECT_ALLOWLIST NATIVE_RETURN_BASE NATIVE_SCHEMES BREAKGLASS COOKIE_SECURE ALLOW_HTTP PREFIX` | lib `from_env` |
| `BOND_AUTH_*` | `JWT_SECRET`, `SESSION_ACCESS_TTL_MINUTES`, `REFRESH_TTL_DAYS`, `REFRESH_MAX_DAYS`, `REFRESH_PROBE_HOURS`, `REFRESH_COOKIE_PATH`, more in `bond_auth_py` | `AuthSettings.from_env` |
| `BOND_MS_CLIENT_ID/_CLIENT_SECRET/_TENANT`, `BOND_GOOGLE_CLIENT_ID/_CLIENT_SECRET` | provider credentials; the tenant is a GUID (`common`, `organizations`, `consumers` refuse at startup) | the example's `oauth_wiring.py` (the libs take arguments) |
| `BOND_OAUTH_KEY`, `BOND_APPLE_APP_IDS`, `BOND_ANDROID_APPS` | token key; link files (`package=FP;FP,pkg2=FP`) | the example's `settings.py` |
| `SDK_EXAMPLE_*` | example-only flags (`docs/sdk/examples.md`) | the example's `settings.py` |

`services/sdk_example/README.md` has a copy-as-is / replace table for every example file (copy `directory.py` and `scope_policy.py`
as the shape; keep `break_glass.py` and `routes/connect_native.py` only if the app uses them).

## 4. Console setup (the app owner does this; nothing here is a secret)

- **Google (A, P).** Client type Web. Register BOTH callbacks: `<api host>/auth/signin/google/callback` and
  `<api host>/connections/google/callback`. The app is External (users are on plain Gmail). The identity-only sign-in
  client carries no sensitive scope and needs no scope verification. The role asks (`gmail.send`, `calendar.events`)
  are sensitive: brand and scope verification is the app's console task before more than 100 test users. Any Gmail
  READ scope would be restricted (annual assessment); do not add one. Publish the app out of Testing before real users: Testing caps 100 users and expires refresh tokens in 7 days.
- **Microsoft (S).** Single-tenant registration, tenant GUID `<tenant GUID>`; the SDK refuses a non-GUID tenant. Under Web register BOTH
  callbacks: sign-in `<base><prefix>/signin/microsoft/callback` and connect `<base>/connections/microsoft/callback` (the app's connections
  route; the example: `oauth_wiring.py:78`). Check: the registered scope names match section 2; tenant-wide admin consent is granted
  (Enterprise applications, Permissions, Grant admin consent); the client-secret expiry date is diarised (an expired secret ends every
  sign-in and refresh); the testers are members of the tenant. Guests are refused. The lib matches invites on Graph `mail`, then the token
  `email`, then the UPN: key invites on the mailbox address or store both.
- **Apple (A, P phones; S's first release uses the scheme return instead).** Associated Domains entitlement `applinks:<api host>` and `webcredentials:<api host>`; AASA for
  `<TEAMID>.<bundle id>` served by `well_known_router`. A private dev host needs the suffix in the entitlement string: `applinks:<api host>?mode=developer`.
- **Android (optional; S and A have no `android/` today).** `autoVerify` https intent filter for `/app/return/*`,
  `android:taskAffinity=""`, and `assetlinks.json` with debug and Play-signing SHA-256 fingerprints.
- **iOS floor (decided: 17.4).** The apps build for iOS 15.0 today; raise `IPHONEOS_DEPLOYMENT_TARGET` and the Podfile platform to
  17.4 at migration. The https universal-link return is production; below 17.4 the plugin silently never returns, so the
  device-bound reverse-domain scheme (`NativeReturn.choose`) is for dev builds only (S excepted: it is S's first-release return). Not verified on a device.
- Apple sign-in is dropped from A. Apple guideline 4.8: Google sign-in must be paired with an equivalent option unless it is
  an enterprise or business app requiring an existing enterprise account. S fits; A and P rely on reviewer judgment, with
  the break-glass password form as the reviewer path (A, P; S has no break-glass).

## 5. Break-glass, linking, copies, what stays

- **Break-glass.** The `/auth/firebase` route stays behind the break-glass flag (section 3) for admin rows and the store
  reviewer. A boolean column `allow_password`, owned by the app, gates who may use it (the example seeds it true for its demo user only; other rows answer
  403 `provider_not_allowed`). It issues the same refresh sessions
  (`finish_session`, provider `password`). `firebase-admin` becomes `bond_auth_py[firebase]`.
- **Existing Firebase users.** `identity_provider`/`identity_subject` start null. The first Google or Microsoft sign-in
  links once by a VERIFIED e-mail match in `find_invite` (P: the Firebase `identities` list already holds the Google
  subject). A second subject for the same row is `identity_mismatch`.
- **Display name.** Implement `apply_profile` (optional) so an e-mail-only invitee gets the IdP's name at first sign-in;
  see `libs/bond_signin/README.md`.
- **Connections.** One-off copy of the old connection rows into `oauth_connections` (A `user_mail_connections`, S
  `oauth_tokens`; steps in `bond_oauth.md`), so nobody reconnects. Rows that fail to decrypt are listed.
- **Stays in the app.** FCM push and its Firebase init (A, P; S has no `firebase_messaging` and removes Firebase from both clients with direct sign-in), users, invites, admin, audit, role mapping, the A shared office mailbox
  connect (`shared=True`), the S Graph REST half, the A estimate-send banner.

## 6. Acceptance

- [ ] `make -C libs/bond_signin test`, `make -C libs/bond_oauth test`, `make -C libs/bond_auth_py test`, then the app suite.
- [ ] In fake mode: sign in, refresh, reuse refused, uninvited refused, role ask granted and declined (the walk in `docs/test/WEB.md`).
- [ ] `alembic upgrade head` then `alembic revision --autogenerate` shows an empty diff.
- [ ] First LIVE run per provider (never run so far; only `MockTransport` and `FakeOAuth` have been): sign in, read the `sid` and
      refresh cookies, rotate once, wait for a provider refresh, role ask, disconnect, sign out. Record it in `docs/sdk/sdk-pins.md`.
- [ ] A phone: https return on iOS 17.4, wrong-secret redeem refused; the scheme only in a dev build.
- [ ] No use of Firebase sign-in outside the break-glass route; no embedded web view.

## 7. Known gaps

- Claims-only id_token check (no JWKS signature); a JWKS check is an additive follow-up (~80 lines).
- IdP liveness (`provider_alive`) is opt-in (`refresh_probe_hours`, default 0); identity-only apps skip it. Sessions have no absolute cap.
- The dev scheme fallback can be claimed by another app: denial of service, not takeover (the secret binds).
- Register placeholder PyPI names `bond-oauth`, `bond-auth-py`, `bond-signin`; an app that omits a sibling declaration would
  otherwise pull a squatter. Not done in this build.

## Secure refresh-token store moved (2026-11-12)

`SecureRefreshTokenStore` is no longer in `bond_signin_ui`. It is in the new package `bond_auth_secure_storage`
(`bond_auth_secure_storage.md`). `bond_signin_ui` no longer depends on `flutter_secure_storage`.

- Old: `import 'package:bond_signin_ui/bond_signin_ui.dart';`
- New: `import 'package:bond_auth_secure_storage/bond_auth_secure_storage.dart';`
- `bond_signin_ui` no longer exports `SecureRefreshTokenStore`, so an old import of it fails to compile.
- Pubspec: a phone app adds `bond_auth_secure_storage`. A web app adds nothing and uses `NoRefreshTokenStore`
  (`import 'package:bond_auth/bond_auth.dart';`) or a cookie session.
