# Changelog

## 0.1.0 - unreleased
- Providers: `GoogleOAuth`, `MicrosoftOAuth`, `FakeOAuth`; `OAuthProvider` protocol, `TokenSet`.
- `TokenCipher` (Fernet), PKCE S256, stateless encrypted state, named scope sets and `scope_drift`.
- `ConnectionsMixin` (`oauth_connections`); service: `start`, `complete`, `status`, `disconnect`, `access_token`.
- `start_flow` returns `StartedFlow(state, authorize_url, nonce)`; `complete` requires `expected_nonce` (and an explicit
  `expected_user_id`), so a flow cannot be completed unbound by accident.
- Partial unique index `uq_oauth_connections_live`; `complete` retries once on a lost race, else `OAuthError("conflict")`.
- Access-token cache lifetime follows `expires_in` (`min(50 min, expires_in - 120 s)`).
- `TokenCipher` derives separate token and state subkeys (HKDF); `encrypt_state` / `decrypt_state` added.
- Errors: `OAuthError`, `ProviderError`, `RetryableError`, `ReconnectRequired`.
