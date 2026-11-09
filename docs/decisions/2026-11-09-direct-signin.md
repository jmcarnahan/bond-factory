# 2026-11-09 Direct Google/Microsoft sign-in (D1 to D14, condensed)

Status: accepted. Dated, append-only. Apps are called A, S and P here; `docs/migration/bond_signin.md` names them. The
research and plan live outside the repo. Contracts: `docs/contracts/signin.md`, `docs/contracts/auth.md`.

## Why

Each app ran Firebase sign-in plus a separate "connect mail and calendar" step. One step is enough: sign in with the
account the person already has, and connect mail and calendar from the same account where the role needs it. Firebase stays
only as an admin break-glass and for push. Expected app code after migration: A about 3,080 to 940 lines, S about 4,580
to 1,100, P about 2,000 to 625 (estimates; each app keeps one directory file, one settings file and thin routers).

## Decisions

- **D1 Scopes per app.** S: Microsoft only, one tenant pinned, full Graph scopes at sign-in (admin pre-consent, no consent
  screen). A and P: Google, identity scopes only at sign-in; mail and calendar are asked per role after sign-in through the
  existing connect flow (A's owner, office and sales; crew none; P's policy is empty). Sign-in always succeeds with identity
  scopes alone.
- **D2 Sessions.** Our own rotating refresh tokens in `bond_auth_py` (`SessionsMixin`, table `auth_sessions`): reuse detection
  with a 20 s grace and a client `rotation_id` for lost responses, 60 days sliding, 180 days absolute, 10 families per user,
  access JWT 60 minutes with a `sid` claim. A provider liveness probe runs at most once per 24 h per family.
- **D3 Break-glass.** Firebase e-mail and password stays behind `BOND_SIGNIN_BREAKGLASS` (default off) for admin rows and the
  store reviewer. Those sign-ins get the same refresh sessions. `firebase-admin` is the optional extra `bond_auth_py[firebase]`.
- **D4 Identity.** `(identity_provider, identity_subject)` bound on first sign-in: Google `sub`, Microsoft `tid:oid`. E-mail is
  only the first-sign-in hint and must be verified; existing Firebase users link once by verified e-mail. The `email` claim is
  never used for authorization. Microsoft refuses a foreign `tid` (`tenant_mismatch`), guests, and `common` at startup.
- **D5 Web binding.** Start is a same-origin POST that sets the nonce cookie and returns the authorize URL. There is no `/go`
  link for sign-in, and `Origin` must be allowlisted.
- **D6 Native binding.** The app is the PKCE client of OUR server: a 32-byte device secret, its sha256 sent at start, the
  secret presented at redeem. Hand-off codes live in a DB table, are single use by one `UPDATE`, burn on mismatch and expire in
  120 s. Return URL is an https app link where the iOS floor allows it; a device-bound reverse-domain scheme is allowed in
  production as the fallback (residual risk: denial of service); connect-native accepts the same return forms. Embedded web views are forbidden.
- **D7 Connect-native** keeps "store nothing until redeem"; sign-in-native stores the connection under the identified user at
  the callback and hands off only `{user_id, provider, auth_time, attempt}`.
- **D8 `bond_signin`** is a Protocol-only lib with the router factory, the check order and `ScopePolicy`. It imports neither
  `bond_oauth` nor `bond_auth_py`; their classes satisfy its Protocols by shape, so the app writes only a `UserDirectory`,
  settings and a mount. It reads exception codes by a string `code` attribute, never by class.
- **D9 Dart.** `packages/bond_signin` (pure) and `packages/bond_signin_ui` (Flutter: widgets and the system-browser port).
  Sign-in UI is not in `bond_connections_ui`: P must not import connection UI to sign in.
- **D10 Scopes** come from the app's `ScopePolicy`, never from `GOOGLE_DEFAULT`. Identity-only sign-in requests no offline access
  and stores no connection. S drops `MailboxSettings.Read` (no caller).
- **D11 Refusal order** is fixed in the lib and the same for every app: `tenant_mismatch`, `email_not_verified`, `not_invited`,
  `check_allowed`, `deactivated`, `identity_mismatch`, `sessions_valid_after`, then link, store connection, issue session, bookkeeping.
- **D12 Role asks** are the existing connect flow with `start?set=<id>`: session-bound, `prompt=consent`, `access_type=offline`.
  `GET /connections` reports `wanted` sets on every read. The ask carries `login_hint` and a different account is refused
  `account_mismatch`, except shared connects.
- **D13 id_token.** In the code flow the claims are validated (`iss`, `aud`, `exp`, `nonce`, `email_verified`) and the signature
  is not: OIDC Core 3.1.3.7 allows it when the token comes straight from the token endpoint over TLS. The function requires three
  segments, refuses `alg: none` unless the provider sets `unsigned_ids_ok` (only `FakeOAuth`), and its docstring forbids use
  on any other token. Not re-opened in review.
- **D14 Scaffold first.** The three new modules (`libs/bond_signin`, `packages/bond_signin`, `packages/bond_signin_ui`) were
  registered in one short step before parallel builders started, and every dependency change was made in it.

## Rejected: a real dependency between libs

D11 of the architecture decision (no lib imports another) stands. A real `bond_signin` dependency on `bond_oauth` and
`bond_auth_py` was tested with two tiny libs, uv 0.13.7 and Poetry 2.3.2:

- uv resolves a workspace pair, and `uv build` records `Requires-Dist` for the sibling.
- pip installs the two wheels only when both are named in one call; the dependent wheel alone fails.
- Poetry path and git (`rev` plus `subdirectory`) dependencies work only when the consumer declares EVERY sibling at the same
  rev; declaring only the dependent fails loudly at lock time. Version floors are enforced.
- Residual risk: the names `bond-oauth`, `bond-auth-py` and `bond-signin` are free on PyPI, so a consumer that omits a
  declaration could pull a squatter; revision skew between siblings; a consumer-side rule the apps can get wrong.

Cost: reverse a decision, rewrite a gate, add a per-app rule. The Protocol-only lib has none of these. A gate
(`tool/boundary_gate.sh`) now also fails when a lib's `pyproject.toml` lists a `bond_` dependency.

## Positions and follow-ups

- **System auth sheet.** On a phone the sign-in page opens in the OS authentication session (RFC 8252 requires an external user
  agent; Google blocks embedded views). It is an OS requirement, not an app popup, and no helper is named `*WithPopup`.
- **Apple guideline 4.8.** Apple sign-in is dropped from A. An app that offers Google sign-in must offer an equivalent option
  unless it is an enterprise or business app requiring an existing account: S fits plausibly, A and P rely on reviewer judgment,
  and the break-glass password form is the reviewer path. Enforcement is discretionary.
- **PyPI placeholders.** Register `bond-oauth`, `bond-auth-py` and `bond-signin` as empty projects so a missing sibling
  declaration cannot resolve to a squatter. Not done in this build.
- **JWKS follow-up.** An additive signature check of the id_token against the provider keys (about 80 lines) behind a setting.
- **iOS floor.** The plugin's https return works from iOS 17.4; below it the app uses the device-bound scheme. Whether the apps
  raise their floor is the owners' decision.
- **Live run.** Nothing in this stack has run against a live Google or Microsoft endpoint; the first adopter does the first run.

## Consequences

- Access tokens outlive logout, reuse and the device limit by up to 60 minutes; refresh ends at once.
- `bond_oauth` 0.2.0 is additive: the old hand-off functions stay as deprecated wrappers until 0.3.0.
- The migration order and per-app steps are in `docs/migration/bond_signin.md`; the walk is in `docs/test/WEB.md`.
