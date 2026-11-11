# Changelog

## 0.1.0 - unreleased
- Protocols: `UserDirectory`, `UserRef`, `IdentityFlow`, `HandoffStore`, `SessionIssuer`, plus the plain
  `SessionSpec` and `IssuedSession` dataclasses (same field names as the sessions lib).
- `make_signin_router`: `POST /auth/signin/{p}/start`, `GET /auth/signin/{p}/callback`, `POST /auth/signin/redeem`,
  `POST /auth/refresh`, `POST /auth/logout`, `POST /auth/sessions/revoke-all`, optional `GET /auth/providers`,
  `GET /app/return/{p}`.
- `order.sign_in`: the fixed refusal order. `ScopePolicy`, `wanted_sets`, `connect_scopes`, `normalize_email`.
- `SignInSettings` and `from_env`; `finish_session`, `CookiePolicy`, `require_origin`.
- Error seam: `refusal_code`, `http_error`, `STATUS_FOR_CODE`, `MESSAGES`; exceptions are matched by a `code` attribute.
- `prefix` argument (routes, nonce and refresh cookie paths, return page move together); `CookiePolicy.refresh_path`.
- `IdentityTaken` and `SignInRefused` exported; `find_invite(..., subject=)`; a `redirect_to` fragment is kept after the query.
- Optional `apply_profile(session, user, profile, *, provider, first)` on the app's directory (detected by attribute,
  never part of `UserDirectory`): called on every successful sign-in, in the sign-in transaction and before the first
  token, only with a usable display name (whitespace collapsed; control, surrogate, private-use and invisible format
  characters dropped (ZWNJ, ZWJ, LRM, RLM kept); at most 256 characters; must contain a letter or digit). An error from it is raised as `ProfileHookError`, never a refusal. Exports `IdentityProfile`,
  `ProfileDirectory`, `ProfileHookError`, `profile_of`.
