# Changelog

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
