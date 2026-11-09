# Changelog

## 0.1.0 - unreleased
- Native-app flow: `start_flow(native=True)`, `StatePayload.native`, `complete(expected_nonce=None)` for native states
  only (returns `PendingConnection`, stores nothing), `issue_handoff(pending)` and `redeem_handoff` (inserts the row
  for the user who started the flow; one-time 120 s code, process-local single use; `invalid_handoff`).
- Providers: `GoogleOAuth`, `MicrosoftOAuth`, `FakeOAuth`; `OAuthProvider` protocol, `TokenSet`.
- `TokenCipher` (Fernet), PKCE S256, stateless encrypted state, named scope sets and `scope_drift`.
- `ConnectionsMixin` (`oauth_connections`); service: `start`, `complete`, `status`, `disconnect`, `access_token`.
- `start_flow` returns `StartedFlow(state, authorize_url, nonce)`; `complete` requires `expected_nonce` (and an explicit
  `expected_user_id`), so a flow cannot be completed unbound by accident.
- Partial unique index `uq_oauth_connections_live`; `complete` retries once on a lost race, else `OAuthError("conflict")`.
- Access-token cache lifetime follows `expires_in` (`min(50 min, expires_in - 120 s)`).
- `TokenCipher` derives separate token and state subkeys (HKDF); `encrypt_state` / `decrypt_state` added.
- Errors: `OAuthError`, `ProviderError`, `RetryableError`, `ReconnectRequired`.
