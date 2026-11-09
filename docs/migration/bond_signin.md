# Migrating to bond_signin

Direct Google/Microsoft sign-in with our own refresh sessions, replacing Firebase sign-in. Server: `libs/bond_signin`
(Protocol-only router factory, check order, `ScopePolicy`) over `bond_oauth` (`SignInFlow`, `HandoffStore`) and
`bond_auth_py` (`SessionStore`). Client: `bond_signin`, `bond_signin_ui`. Contract: `docs/contracts/signin.md`.
Reference adapter: `services/sdk_example/sdk_example/signin_wiring.py`. Legend: `docs/migration/README.md`.

The app writes ONLY a `UserDirectory`, a `ScopePolicy`, settings and a mount. Order of work: land the SDK pin and
`bond_auth`/`bond_auth_py` first, then this (see README order). The first LIVE provider run happens here (section 6).

## 1. What each app writes (INFERENCE sizes; before to after: A ~3,080 to ~940, S ~4,580 to ~1,100, P ~2,000 to ~625 lines)

| File | A | S | P |
|---|---|---|---|
| `auth/directory.py` | ~90: identity lookup, invite by `lower(email)` not removed, capabilities from `user_capabilities`, bookkeeping | ~110: role to capabilities, admin e-mail list promotes inside `find_invite`, invite is UPN or `mail` | ~80: invite lookup, `company_suspended`, `company_id` extra claim, audit |
| Settings and policy | ~70 | ~60 | ~40 |
| Models and revisions | `identity_provider`, `identity_subject` (unique pair, nullable); `SessionsMixin`, `HandoffsMixin`; two revisions | same plus `sessions_valid_after` (S has none) and the connections table; three revisions | same minus connections; one revision |
| Router and deps | keeps `/me`, `PATCH /me`, `/demo`, `/providers`, `/firebase` (break-glass); mounts the SDK router | same; first moves to the SDK auth contract | same |
| Flutter | `OidcAuthGateway`, `SecureRefreshTokenStore`, login screens on `BondSignInScreen`, return handling | same; the connect web view is replaced, not patched | admin web and crew phone screens |

`UserDirectory` methods (the app writes all): `find_by_identity`, `find_by_id`, `find_invite(session, emails,
provider)`, `link_identity` (raises `IdentityTaken`), `check_allowed`, `capabilities`, `session_spec`, `public`,
`mark_sessions_invalid`, `provider_alive`, `record_sign_in`, `record_refusal`. Signatures: `libs/bond_signin/README.md`.

## 2. ScopePolicy

| | Sign-in scopes | Asked after sign-in (by capability) | Notes |
|---|---|---|---|
| A (Google) | `openid email profile`, `access_type=online` | owner, office, sales: set `mail_send` (`gmail.send`) and `calendar` (`calendar.events`); crew none; owner and office the shared mailbox | identity-only sign-in stores no connection |
| S (Microsoft) | `openid profile email` plus `offline_access User.Read Mail.Send Mail.Read Calendars.ReadWrite` | none | tenant pinned; `MailboxSettings.Read` dropped (no caller); admin pre-consent shows no consent screen |
| P (Google) | `openid email profile` | none (empty policy) | no mail code, no connections table |

Roles are granted after sign-in, so `wanted` is recomputed on every `GET /connections`. Sign-in always succeeds with
identity scopes alone; a declined ask leaves the set `wanted`.

## 3. Settings and env

`SignInSettings` fields: providers, redirect allowlist (origins), public base (https outside fake mode), `native_return_base`, `native_schemes`,
break-glass flag (default off). Provider env: `BOND_GOOGLE_CLIENT_ID`/`_SECRET`, `BOND_MS_CLIENT_ID`/`_SECRET`, `BOND_MS_TENANT` (a GUID: `common`,
`organizations`, `consumers` refuse at startup), `BOND_OAUTH_KEY`, `BOND_AUTH_*` refresh lifetimes, `BOND_APPLE_APP_IDS` (csv),
`BOND_ANDROID_APPS` (`package=FP;FP,pkg2=FP`). The example reads the rest as `SDK_EXAMPLE_*` (`docs/sdk/examples.md`); an app picks its own prefix.
`services/sdk_example/README.md` has a copy-as-is / replace table for every example file (copy `directory.py` and `scope_policy.py`
as the shape; keep `break_glass.py` and `routes/connect_native.py` only if the app uses them).

## 4. Console setup (the app owner does this; nothing here is a secret)

- **Google (A, P).** Client type Web. Register BOTH callbacks: `<api host>/auth/signin/google/callback` and
  `<api host>/connections/google/callback`. The app is External (users are on plain Gmail). The identity-only sign-in
  client carries no sensitive scope and needs no scope verification. The role asks (`gmail.send`, `calendar.events`)
  are sensitive: brand and scope verification is the app's console task before more than 100 test users. Any Gmail
  READ scope would be restricted (annual assessment); do not add one. Testing mode shortens refresh tokens to 7 days.
- **Microsoft (S).** Single-tenant registration, tenant GUID `<tenant GUID>`. Both callbacks under Web. Grant tenant-wide
  admin consent for the five Graph scopes. Guests are refused; everyone signs in on the company tenant.
- **Apple (A, P, S phones).** Associated Domains entitlement `applinks:<api host>` and `webcredentials:<api host>`; AASA for
  `<TEAMID>.<bundle id>` served by `well_known_router`. A private dev host needs the `?mode=developer` suffix.
- **Android (optional; S and A have no `android/` today).** `autoVerify` https intent filter for `/app/return/*`,
  `android:taskAffinity=""`, and `assetlinks.json` with debug and Play-signing SHA-256 fingerprints.
- **iOS floor.** The apps build for iOS 15.0; the https return is honoured from iOS 17.4 and below it the plugin
  silently never returns. The app picks the return per device through `NativeReturn.choose(...)`: https on 17.4+, a
  device-bound reverse-domain scheme below it. Whether the apps raise their iOS floor to 17.4 is the owners' decision (the open
  iOS-floor question in the decision note). Not verified on a device.
- Apple sign-in is dropped from A. Apple guideline 4.8: Google sign-in must be paired with an equivalent option unless it is
  an enterprise or business app requiring an existing enterprise account. S fits; A and P rely on reviewer judgment, with
  the break-glass password form as the reviewer path.

## 5. Break-glass, linking, copies, what stays

- **Break-glass.** The `/auth/firebase` route stays behind `BOND_SIGNIN_BREAKGLASS` for admin rows and the store
  reviewer. A boolean column `allow_password`, owned by the app, gates who may use it (the example seeds it true for its demo user only; other rows answer
  403 `provider_not_allowed`). It issues the same refresh sessions
  (`finish_session`, provider `password`). `firebase-admin` becomes `bond_auth_py[firebase]`.
- **Existing Firebase users.** `identity_provider`/`identity_subject` start null. The first Google or Microsoft sign-in
  links once by a VERIFIED e-mail match in `find_invite` (P: the Firebase `identities` list already holds the Google
  subject). A second subject for the same row is `identity_mismatch`.
- **Connections.** One-off copy of the old connection rows into `oauth_connections` (A `user_mail_connections`, S
  `oauth_tokens`; steps in `bond_oauth.md`), so nobody reconnects. Rows that fail to decrypt are listed.
- **Stays in the app.** FCM push and its Firebase init, users, invites, admin, audit, role mapping, the A shared office mailbox
  connect (`shared=True`), the S Graph REST half, the A estimate-send banner.

## 6. Acceptance

- [ ] `make -C libs/bond_signin test`, `make -C libs/bond_oauth test`, `make -C libs/bond_auth_py test`, then the app suite.
- [ ] In fake mode: sign in, refresh, reuse refused, uninvited refused, role ask granted and declined (the walk in `docs/test/WEB.md`).
- [ ] `alembic upgrade head` then `alembic revision --autogenerate` shows an empty diff.
- [ ] First LIVE run per provider (never run so far; only `MockTransport` and `FakeOAuth` have been): sign in, read the `sid` and
      refresh cookies, rotate once, wait for a provider refresh, role ask, disconnect, sign out. Record it in `docs/sdk/sdk-pins.md`.
- [ ] A phone: https return on iOS 17.4+, scheme fallback below, wrong-secret redeem refused.
- [ ] No use of Firebase sign-in outside the break-glass route; no embedded web view.

## 7. Known gaps

- Claims-only id_token check (no JWKS signature); a JWKS check is an additive follow-up (~80 lines).
- IdP liveness (`provider_alive`) runs at most once per 24 h per family; identity-only apps skip it.
- The scheme fallback can be claimed by another app on Android: denial of service, not takeover (the secret binds).
- Register placeholder PyPI names `bond-oauth`, `bond-auth-py`, `bond-signin`; an app that omits a sibling declaration would
  otherwise pull a squatter. Not done in this build.
