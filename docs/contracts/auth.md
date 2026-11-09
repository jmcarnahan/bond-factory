# Auth contract

Normative for `bond_auth_py`, `bond_auth` and `bond_auth_firebase`. Routes sit under the app's prefix;
the example uses `/auth`. Errors use `docs/contracts/error_body.md`. Direct Google/Microsoft sign-in, hand-offs and
the sign-in routes: `docs/contracts/signin.md`.

## Routes

| Route | Body | Answer |
|---|---|---|
| `POST /auth/firebase` | `{id_token}` | `200 {token, user}` |
| `POST /auth/refresh` | one of `{refresh_token, rotation_id?, delivery?}`, the refresh cookie, or `{id_token}` | `{token, user, refresh_token?}`; see Refresh sessions |
| `POST /auth/demo` | `{user_id, delivery?}` | `{token, user}` only when demo auth is on, else 404 |
| `GET /auth/providers` | none | public client config, below |
| `GET /auth/me`, `PATCH /auth/me` | `{language}` | the user |
| `POST /auth/logout` | none, the refresh cookie, or `{refresh_token}` | `{"status": "logged_out"}`, revokes the refresh token, clears the cookies; 403 `invalid_origin` on cookie delivery without an allowed Origin, otherwise never fails |
| `POST /auth/sessions/revoke-all` | none, signed in | `{revoked: n}`; also sets `sessions_valid_after` |

`sign_in=false` on firebase skips accepted, last-sign-in and audit bookkeeping. Refresh ignores `sign_in`: it is always a renewal.
Rate limit on firebase and refresh: app policy; the example uses `20/minute`.
An app that has not turned sessions on keeps the old refresh: a re-exchange of a fresh Firebase id token, no refresh token.

## User

`{id, email, name, initials, language, capabilities: [str], ...app fields}`. The library does not build it: the
app assembles the payload in this shape and adds its own fields. Capability vocabularies belong to the app, behind a
`CapabilityPolicy`.

## Session JWT

- HS256, secret from settings, default lifetime 10080 minutes. With sessions on, the lifetime is
  `session_access_ttl_minutes` (60) and both `issue_session` and `rotate` mint with it.
- Claims: `sub` (user id), `user_id` (user id; both required on verify), `name`, `capabilities`
  (informational: authority is re-read from the database per request), `iat` (float epoch, real clock), `exp`,
  `aud` (list), `iss`, and with sessions on `sid` (the refresh family id, for later per-session revocation).
  `create_access_token` takes an `extra_claims` dict for app claims.
- Read from `Authorization: Bearer` first, then the `<app>_access_token` cookie (httponly, samesite lax,
  secure by setting).

## Revocation

`users.sessions_valid_after` is a nullable UTC datetime. Verify fails with 401 `session_revoked` when
`iat < sessions_valid_after`, checked before `is_active`. Exchange fails the same way when the id token's
`auth_time + 5 s < sessions_valid_after`. Set it on email change, sign-out-everywhere, deactivate and remove.
Always compare on the real clock.

## Refresh sessions

Table `auth_sessions` (mixin `SessionsMixin`), one row per refresh token; only the sha256 is stored. Lifetimes
(env `BOND_AUTH_`): `refresh_ttl_days` 90 sliding idle, `refresh_max_days` unset (no absolute cap; set it to cap from the sign-in), `refresh_probe_hours` 0 (IdP liveness probe off; opt-in), `refresh_reuse_grace_seconds`
20, `refresh_max_sessions_per_user` 10 families (the least recently used is revoked, reason `limit`),
`refresh_cookie_path` `/auth`, `session_access_ttl_minutes` 60. Env names: `BOND_AUTH_REFRESH_TTL_DAYS`, `_MAX_DAYS`,
`_MAX_DAYS` (0 or empty: none), `_PROBE_HOURS`, `_REUSE_GRACE_SECONDS`, `_MAX_SESSIONS_PER_USER`, `BOND_AUTH_SESSION_ACCESS_TTL_MINUTES`.

- Body: `refresh_token` wins over the cookie. The delivery follows the client's token source: a client with no refresh-token store (web) gets the
  token in a cookie and not in the JSON; a client with a store (phone) sends `delivery: body` and gets it in `refresh_token`. The answer is `{token, user,
  refresh_token?}` and a rotated cookie on web.
- `rotation_id`: a random client string sent with every refresh and stored on the child row. A replay of the parent
  with the same `rotation_id` within 10 minutes while the child is unused is a retry: the unused child is revoked
  (`reason=retry`) and a fresh sibling is issued. Without a matching id the 20 s grace rule applies; after it, reuse.
- Reuse: the family is revoked and the change committed before `refresh_reused` is raised. Revocation compares the
  family's `auth_time` plus 5 s with `sessions_valid_after`, never `now`.
- Cookie `<app>_refresh_token`: HttpOnly, SameSite=Lax, Path `/auth`, set again on every rotation. Cookie POSTs need
  the Origin rule of `signin.md`.
- Break-glass and demo sign-ins issue the same sessions, provider `password` or `demo`.
- Logout, reuse and the device limit act on refresh at once and on access tokens within 60 minutes.

## Error codes

| Status | Code | Note |
|---|---|---|
| 403 | `not_invited` | hint `apple_relay` for an Apple private-relay address |
| 403 | `identity_mismatch` | |
| 403 | `deactivated` | |
| 403 | `email_not_verified` | |
| 401 | `invalid_token` | |
| 401 | `session_revoked` | |
| 401 | `refresh_reused` | "This session was ended for your security. Sign in again." |
| 401 | `refresh_expired` | either lifetime ended; an expired attempt does not burn the token |
| 401 | `refresh_revoked` | unknown, malformed, revoked, or the user left the directory; unknown tokens create no row |
| 403 | `tenant_mismatch`, `consent_declined` | sign-in only; see `signin.md` |
| 400 | `signin_expired` | stale sign-in state; see `signin.md` |
| 501 | `firebase_not_configured` | |
| 403 | `provider_not_allowed`, `company_suspended` | optional policy hooks |

## Verifier tiers

1. An injected verifier object or callable.
2. The mock verifier, only when the mock flag is on AND (pytest is running OR the test-env flag is set).
3. `firebase-admin`, an optional extra (`bond_auth_py[firebase]`); without it the tier raises
   `AuthNotConfigured` with an install hint. `check_revoked` only with a service account; a missing email is
   `invalid_token`; `email_verified` false is `email_not_verified`.

These tiers are the Firebase path only. Direct sign-in has no verifier: the identity comes from the token response
of the code exchange over TLS (claims checked, no signature check; `signin.md`), so `FakeOAuth` and real
providers share one path.

A token that is empty or longer than 8192 characters is malformed. The verifier returns `{uid, email
(lowercased), name, auth_time, sign_in_provider, identities}`.

## Mock tokens

Register one with `register_mock_token(...)` or use the literal `"mock:<email>"` (uid is the known mock
identity's uid, else `mock-<email>`; provider `password`). Mock identity uids are `mock-uid-<n>`.
Env names: `BOND_AUTH_MOCK`, `BOND_AUTH_TEST_ENV`, `FIREBASE_PROJECT_ID`, `FIREBASE_SERVICE_ACCOUNT_JSON` or
`_FILE`, `FIREBASE_WEB_API_KEY`.

## Identity janitor (opt-in)

After a refused `not_invited` Google or Apple sign-in, delete the Firebase user only when the provider is
`google.com` or `apple.com`, it was created under 60 s ago (5 s skew), provider data is exactly that provider,
and no users row exists by uid or lowercased email (re-checked after rollback). Callback `audit(uid,
provider)`. The response stays 403. Sign-in only, never refresh.

## `GET /auth/providers`

```json
{"demo": false, "email_password": true, "google": true, "google_web_client_id": null, "apple": false,
 "mock": false,
 "firebase": {"project_id": "...", "auth_domain": "...", "messaging_sender_id": "...",
              "web": {"api_key": "...", "app_id": "..."},
              "ios": {"api_key": "...", "app_id": "...", "bundle_id": "..."}},
 "sync": {"url": null}}
```

With direct sign-in the payload adds `signin: [{"id": "google", "label": "Google"}]`, `break_glass: bool` (the
Firebase e-mail form is offered only when true) and `default_flow: "signin" | "firebase"`. Clients ignore keys they
do not know. With the break-glass flag off, `email_password` is false.

`firebase` is `null` when unconfigured. Every value is public client config; clients initialise Firebase at
runtime from it. No `firebase_options.dart` ships in any shared package.
