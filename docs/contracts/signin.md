# Sign-in contract

Normative for `libs/bond_signin`, the sign-in half of `bond_oauth`, the sessions half of `bond_auth_py`,
`bond_signin` and `bond_signin_ui`. Routes sit under the app's prefix; the example uses `/auth`. Errors use
`docs/contracts/error_body.md`. Session JWT, refresh row, user shape: `docs/contracts/auth.md`.

## Routes

| Route | Body or query | Answer | Errors |
|---|---|---|---|
| `POST /auth/signin/{p}/start` | `{redirect_to, mode: "web"\|"native", device_challenge?, attempt?}` | `200 {url}`; web also sets the nonce cookie | 400 `invalid_request`, 403 `invalid_origin`, 404 unknown provider |
| `GET /auth/signin/{p}/callback` | `state`, `code` or `error` | `302` (below); no body | 400 `invalid_state` without the matching cookie; refusals ride `reason=` / `error=` |
| `POST /auth/signin/redeem` | `{code, device_secret}` | `200 {token, expires_in, refresh_token, user}` | 401 `invalid_handoff`, 401 `session_revoked`, 403 `deactivated`; body delivery, so no cookies are set |
| `POST /auth/refresh` | `{refresh_token?, rotation_id?}`, cookie, or `{id_token}` | `{token, expires_in, user, refresh_token?}`; `delivery` rules in `auth.md` | 401 `refresh_reused\|refresh_expired\|refresh_revoked\|invalid_token` |
| `POST /auth/logout` | cookie or `{refresh_token}` | `{"status": "logged_out"}`, clears the cookies | 403 `invalid_origin` on cookie delivery without an allowed Origin; otherwise never fails |
| `POST /auth/sessions/revoke-all` | none, signed in | `{revoked: n}` | 401 |
| `GET /auth/providers` | none | `auth.md` payload plus `signin`, `break_glass`, `default_flow` | none |
| `GET /app/return/{p}` | any query | a static "Return to the app" page; the query is not logged | none |
| `GET /connections` | none, signed in | `{connections: [...], wanted: [...]}`, always an object (`wanted` is empty without a policy) | 401 |
| `GET /connections/{p}/start?set=<id>` | existing query plus `set` | `{url}` | 400 unknown set; native needs `device_challenge` and `attempt` (400 without) |
| `GET /.well-known/apple-app-site-association`, `/.well-known/assetlinks.json` | none | JSON, below | none |

Start, web: `{"redirect_to": "https://<app origin>/auth", "mode": "web"}`. Start, native: `{"redirect_to":
"https://<api host>/app/return/google", "mode": "native", "device_challenge": "<64 hex>", "attempt": "<id>"}`.
The answer is `{"url": "<authorize url>"}`. The callback URI at the provider is `<public_base>/auth/signin/{p}/callback`
for sign-in and `<public_base>/connections/{p}/callback` for connect; register both.

Callback outcomes:

| Mode | Success | Refusal |
|---|---|---|
| web | sets the access and refresh cookies, `302 redirect_to?signin=ok` | `302 redirect_to?signin=error&reason=<code>`, no row written |
| native | `302 <return>?attempt=<id>&code=<handoff>` | `302 <return>?attempt=<id>&error=<code>` |

A provider `error=access_denied` becomes `consent_declined`. A missing or mismatched nonce cookie answers 400
and never redirects, because the target comes from a link the person did not request. The cookie is cleared on
every outcome.

## Cookies

| Cookie | Set by | Flags |
|---|---|---|
| `<app>_access_token` | callback, refresh | HttpOnly, SameSite=Lax, Path `/`, Secure per setting |
| `<app>_refresh_token` | callback, refresh | HttpOnly, SameSite=Lax, Path is the sign-in prefix (default `/auth`; `CookiePolicy(refresh_path)`), Max-Age = refresh TTL, Secure per setting, never in JSON on web |
| `bond_signin_<8hex>` | start (web) | HttpOnly, SameSite=Lax, Path `<prefix>/signin` (default `/auth/signin`), Max-Age 600, Secure per setting |

The nonce cookie name is `bond_signin_` plus the first 8 hex of `sha256(state nonce)`. The callback decodes the
state, derives the name, compares, clears it. Two tabs do not collide. A sibling subdomain can toss cookies onto
the parent domain: host the API on a name no untrusted sibling controls. Not verified in a browser.

## Origin rule

Every cookie-delivery POST (`start`, `refresh`, `logout`, `revoke-all`) needs an `Origin` header, or a `Referer`
origin, that is in `redirect_allowlist` or equals the API's own origin. A missing header or `Origin: null` answers
403 `invalid_origin`. Requests that deliver by body (native, bearer) skip the rule. `redirect_to` must also be in
the allowlist (web) or equal `<public_base>/app/return/<p>` or a configured native scheme (native).

## Refusal codes and order

The lib runs one fixed order for every app; the first failure wins and writes no row:
`tenant_mismatch`, `email_not_verified`, `not_invited`, `check_allowed` (`company_suspended`,
`provider_not_allowed`), `deactivated`, `identity_mismatch`, `session_revoked` (exchange rule), then link the
identity, store the connection, issue the session, bookkeeping.

| Status | Code | Note |
|---|---|---|
| 403 | `tenant_mismatch` | Microsoft `tid` is not the pinned tenant, or a guest account (`#EXT#`, `idtyp` guest) |
| 403 | `email_not_verified`, `not_invited`, `company_suspended`, `provider_not_allowed`, `deactivated`, `identity_mismatch` | as in `auth.md` |
| 401 | `session_revoked` | the sign-in is older than `sessions_valid_after` |
| 403 | `consent_declined` | the person cancelled at the provider |
| 400 | `signin_expired`, `invalid_state` | stale or foreign state; `invalid_request` for a bad body |
| 401 | `invalid_handoff` | unknown, used, expired, wrong purpose or wrong device secret |
| 403 | `account_mismatch` | connect only: the provider account is not the bound identity (shared connects exempt) |

Same codes in a refusal redirect are plain strings in `reason=` or `error=`. `bond_signin` maps any exception
carrying a string `code` through its own table; an unknown code is a 500 and logs the code only. At the callback an unmapped provider failure redirects with
`reason=provider_error` (502 when answered directly); `invalid_id_token`, `invalid_code` and an unknown provider
(404 at start) are the other exchange-time codes.

## Native return and device binding

- The app makes a 32-byte secret (`Random.secure()`, base64url) and an `attempt` (16 random bytes, hex). It sends
  `device_challenge = sha256 hex of the base64url text of the secret` at start and the secret itself only in the redeem body, over TLS.
- Return URL: `https://<api host>/app/return/<provider>` (universal or app link, system auth session). A reverse-domain
  scheme listed in `native_schemes` is a dev and test fallback only (iOS 17.4 is the production floor); the device secret makes an
  intercepted code useless, the residual risk is denial of service. Connect-native accepts the same return forms. Embedded web views are never used.
- `attempt` is opaque to the server: echoed only, at most 64 characters of `[A-Za-z0-9_-]`. The client drops any
  return whose `attempt` is not the pending one.
- `code` is `token_urlsafe(32)`. The server stores only its sha256. Sign-in payloads hold `{user_id, provider,
  auth_time, attempt}`, never tokens; the sign-in connection is stored under the identified user at the callback.

Hand-off table `oauth_handoffs` (mixin `HandoffsMixin`):

| Column | Note |
|---|---|
| `id` uuid, `code_hash` unique, `device_hash` | hash of the code and of the device secret |
| `purpose` (`signin` or `connect`), `provider`, `attempt_id` | a code is valid for one purpose |
| `payload_enc` | cipher-sealed JSON; connect payloads carry provider tokens here, never in a URL |
| `created_at`, `expires_at`, `used_at` | life 120 s; pruned after 1 h |

Redeem is one statement: `UPDATE ... SET used_at = now WHERE code_hash = :h AND used_at IS NULL AND expires_at > now`;
exactly one row or `invalid_handoff`. Then the device secret is compared in constant time. A mismatch fails and the
row stays burned (one try). Connect redeem also needs the bearer of the user who started the flow and answers 400 `invalid_handoff`.

## Well-known files

Served unauthenticated over https, never redirected, `application/json`, `Cache-Control: public, max-age=300`.
Values come from the app's env (`BOND_APPLE_APP_IDS`, `BOND_ANDROID_APPS` as `package=FP;FP,pkg2=FP`, fingerprints separated by `;`, apps by `,`). The router lives in
`bond_service_kit` and answers 404 while its env is empty.

```json
{"applinks": {"details": [{"appIDs": ["<TEAMID>.<bundle id>"], "components": [{"/": "/app/return/*"}]}]},
 "webcredentials": {"apps": ["<TEAMID>.<bundle id>"]}}
```

```json
[{"relation": ["delegate_permission/common.handle_all_urls"],
  "target": {"namespace": "android_app", "package_name": "<package>", "sha256_cert_fingerprints": ["<sha256>"]}}]
```

## The `wanted` JSON

`GET /connections` reports, on every read, the sets the signed-in person's capabilities want from the policy:

```json
{"connections": [{"provider": "google", "connected": true, "needs_reconnect": false, "scopes": ["..."]}],
 "wanted": [{"id": "mail_send", "provider": "google", "label": "Send mail", "scopes": ["..."], "granted": false}]}
```

`granted` is true when the live connection holds every scope of the set. A promotion shows the ask on the next
load. The ask is the existing connect flow with `start?set=<id>`: session-bound, `prompt=consent`,
`access_type=offline`, Google `include_granted_scopes=true`; for Microsoft the request carries the union of granted
scopes and the set. The connect `authorize_url` carries `login_hint=<signed-in e-mail>`. A web connect whose consent leaves the asked set unticked stores no row and returns
`consent_declined`; a declined ask leaves the set wanted. The connect callback re-checks the capability behind the set
(the example uses `connections.manage`) before it stores anything.

## Security model

1. Login CSRF (research FINDINGS §6 B1): a nonce cookie set by a link is worthless. Start is a same-origin POST from
   the person's own page, with the Origin rule; there is no `/go` link for sign-in.
2. Lured victim on a phone (B2): the code is useless without the device secret; the app ignores returns for an
   unknown attempt; a wrong secret burns the code.
3. nOAuth (B3): identity is `(provider, subject)`, Google `sub`, Microsoft `tid:oid`. E-mail is only the first
   sign-in hint, must be verified, and is never used for authorization after that.
4. Microsoft sign-in refuses `common`, `organizations` and `consumers` at startup, any other `tid`
   (`tenant_mismatch`) and guests. `email_verified` is true only for the pinned tenant.
5. The id_token comes straight from the token endpoint over TLS, so its claims (`iss`, `aud`, `exp`, `nonce`) are
   checked and its signature is not (OIDC Core 3.1.3.7). `alg: none` is refused except for `FakeOAuth`.
6. Reuse detection (B4): a rotated refresh token replayed after 20 s revokes its whole family, committed before the
   error is raised. Revocation compares the family's `auth_time`, never `now`.
7. Logout, reuse and the device limit end the refresh side at once and access tokens within
   `session_access_ttl_minutes` (60); a `sid` claim names the family.
8. Identity-only sign-in requests no offline access and stores no connection.
9. Tokens and secrets are never logged, never in a URL and never written into records. A hand-off code is not a token.
10. The system auth sheet on a phone is an OS requirement of RFC 8252, not an app popup.
