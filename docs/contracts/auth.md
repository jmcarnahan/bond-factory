# Auth contract

Normative for `bond_auth_py`, `bond_auth` and `bond_auth_firebase`. Routes sit under the app's prefix;
the example uses `/auth`. Errors use `docs/contracts/error_body.md`.

## Routes

| Route | Body | Answer |
|---|---|---|
| `POST /auth/firebase` | `{id_token}` | `200 {token, user}` |
| `POST /auth/refresh` | `{id_token}` | same body; a re-exchange of a fresh id token, there is no refresh token |
| `POST /auth/demo` | `{user_id}` | `{token, user}` only when demo auth is on, else 404 |
| `GET /auth/providers` | none | public client config, below |
| `GET /auth/me`, `PATCH /auth/me` | `{language}` | the user |
| `POST /auth/logout` | none | `{"status": "logged_out"}`, clears the cookie |

`sign_in=false` on firebase skips accepted, last-sign-in and audit bookkeeping. Refresh ignores `sign_in`: it is always a renewal.
Rate limit on firebase and refresh: `20/minute` by default.

## User

`{id, email, name, initials, language, capabilities: [str], ...app fields}`. The library returns the generic
part; an `extra_user_fields(user)` hook adds the rest. Capability vocabularies belong to the app, behind a
`CapabilityPolicy`.

## Session JWT

- HS256, secret from settings, default lifetime 10080 minutes.
- Claims: `sub` (user id), `user_id` (user id; both required on verify), `name`, `capabilities`
  (informational: authority is re-read from the database per request), `iat` (float epoch, real clock), `exp`,
  `aud` (list), `iss`. An `extra_claims(user)` hook adds more.
- Read from `Authorization: Bearer` first, then the `<app>_access_token` cookie (httponly, samesite lax,
  secure by setting).

## Revocation

`users.sessions_valid_after` is a nullable UTC datetime. Verify fails with 401 `session_revoked` when
`iat < sessions_valid_after`, checked before `is_active`. Exchange fails the same way when the id token's
`auth_time + 5 s < sessions_valid_after`. Set it on email change, sign-out-everywhere, deactivate and remove.
Always compare on the real clock.

## Error codes

| Status | Code | Note |
|---|---|---|
| 403 | `not_invited` | hint `apple_relay` for an Apple private-relay address |
| 403 | `identity_mismatch` | |
| 403 | `deactivated` | |
| 403 | `email_not_verified` | |
| 401 | `invalid_token` | |
| 401 | `session_revoked` | |
| 501 | `firebase_not_configured` | |
| 403 | `provider_not_allowed`, `company_suspended` | optional policy hooks |

## Verifier tiers

1. An injected verifier object or callable.
2. The mock verifier, only when the mock flag is on AND (pytest is running OR the test-env flag is set).
3. `firebase-admin`. `check_revoked` only with a service account; a missing email is `invalid_token`;
   `email_verified` false is `email_not_verified`.

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
and no users row exists by uid or lowercased email (re-checked after rollback). Hook `on_janitor(uid,
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

`firebase` is `null` when unconfigured. Every value is public client config; clients initialise Firebase at
runtime from it. No `firebase_options.dart` ships in any shared package.
