# Changelog

## 0.2.0 - unreleased
- Refresh sessions: `SessionsMixin` (table `auth_sessions`, one row per refresh token), `SessionStore`,
  `issue_session`, `rotate`, `revoke_token`, `revoke_family`, `revoke_user`, `prune_sessions`, `SessionSpec`,
  `IssuedSession`. Rotating tokens with reuse detection (20 s grace, `rotation_id` retry), 60-day sliding and
  180-day absolute lifetimes, 10 families per user, daily IdP liveness probe, access JWT 60 min with a `sid` claim.
- Errors: `REFRESH_REUSED`, `REFRESH_EXPIRED`, `REFRESH_REVOKED` (401; `ReuseDetected`, `RefreshExpired`,
  `RefreshRevoked`), `TENANT_MISMATCH`, `CONSENT_DECLINED`, `SIGNIN_EXPIRED`, `ACCOUNT_MISMATCH`, `INVALID_ORIGIN` (403; `SIGNIN_EXPIRED` is 400).
- Also in REFUSALS: `invalid_request`, `invalid_state`, `invalid_code`, `invalid_id_token`, `signin_expired` (400), `invalid_handoff` (401),
  `unknown_provider` (404), `provider_error` (502). A raising liveness probe counts as unknown and never breaks refresh.
- Settings: `session_access_ttl_minutes`, `refresh_ttl_days`, `refresh_max_days`, `refresh_reuse_grace_seconds`,
  `refresh_retry_seconds`, `refresh_max_sessions_per_user`, `refresh_probe_hours`, `refresh_cookie_path` (env
  `BOND_AUTH_*`). `refresh_cookie_params`, `refresh_cookie_name`; `session_cookie_params(..., ttl_minutes=)`.
- `providers_payload(signin=, break_glass=, default_flow=)`: each key is served only when set.
- `firebase-admin` is the optional `firebase` extra: without it the Firebase tier and admin raise
  `AuthNotConfigured("install bond_auth_py[firebase]")`. `sqlalchemy` is now a dependency.

## 0.1.0 - unreleased
- Settings: `AuthSettings`, `from_env`, `mock_active`, `assert_startup_safe`.
- Verification: `verify_id_token` with three tiers (installed verifier, mock, firebase-admin), `Identity`,
  `TokenError`, `EmailNotVerified`, `AuthUnavailable`, `MockIdentities`.
- Session JWT: `create_access_token`, `decode_claims`, `cookie_name`, `session_cookie_params`,
  `read_bearer_or_cookie`.
- Revocation: `RevocationCheck`, `check_session`, `check_exchange`.
- Policies: `ClaimListPolicy`, `RolePolicy`. Errors: code strings and `AuthRefused`.
- `providers_payload` and `firebase_runtime_config` for `GET /auth/providers`.
- `IdentityAdmin` with `FirebaseIdentityAdmin` and `MockIdentityAdmin`; `janitor_after_refusal`.
- `create_access_token(..., ttl=)` overrides the settings minutes.
- An empty JWT secret never signs or verifies (`TokenError("misconfigured")`) and `assert_startup_safe` refuses it;
  requires PyJWT >= 2.10.
- `decode_claims` allows 10 s of clock skew on `iat` and `exp`; the revocation comparison stays exact.
- Network and certificate-fetch failures in the Firebase tier raise `AuthUnavailable` (503 `auth_unavailable`),
  not `TokenError`, so a provider outage does not sign people out. `AuthNotConfigured` (subclass) keeps 501
  `firebase_not_configured` for a missing configuration or verifier.
- The set-password mail uses the standard library HTTP client (no new runtime dependency).
