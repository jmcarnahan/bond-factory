# Changelog

## 0.2.0 - unreleased
Additive: every 0.1.0 call keeps working. Native connect goes through `HandoffStore(purpose="connect")` (the example's
`routes/connect_native.py`); the process-local registry functions in `handoff.py` are deprecated, kept for 0.2.x
compatibility and removed in 0.3.0.
- `SignInFlow.peek(state=)` and `StateInfo`: pure decode (no network). Raises `invalid_state` for an unauthentic state;
  an authentic expired state is returned with `expired=True` (`complete` raises `signin_expired`).
- Tenant pin at construction: `SignInFlow` raises `ValueError` for a Microsoft provider (not `unsigned_ids_ok`) without a
  GUID pin (`pinned_tenants` or `MicrosoftOAuth.pinned_tenant`); `MicrosoftOAuth(pinned_tenant=)` must be a GUID.
- Guest refusal: `MicrosoftOAuth.userinfo` adds `upn` and `user_type`; `#EXT#` in UPN, `Guest` user type or a foreign
  `idp` claim is `tenant_mismatch`. `StartedSignIn`, `SignInResult.pending` and `StateInfo.nonce`/`device_hash` hide secrets from `repr`.
- `identity_from_token_response`: `exp` must be finite (NaN/inf refused); a non-string `email` claim counts as missing.
  A real Microsoft provider fails the sign-in when `/me` fails (it carries the guest markers); Google ignores a failed userinfo.
- `SignInFlow` (`signin.py`): `start`, `complete`, `store`, `callback_url`; `StartedSignIn`, `SignInResult`. `complete`
  stores nothing; `pending` only for non-identity-only grants with a refresh token; web binds the cookie nonce, native
  the device hash; `expired_state` becomes `signin_expired`.
- `OidcIdentity` and `identity_from_token_response` (`identity.py`): claim checks without a signature check (D13),
  `alg: none` refused unless `unsigned_ids_ok`, Microsoft tenant pin and guest refusal (`tenant_mismatch`),
  `invalid_id_token`, bool-or-string `email_verified`.
- `HandoffStore` and `HandoffsMixin` (`handoff_store.py`, table `oauth_handoffs`): device-bound, single-use by one
  `UPDATE`, burns on mismatch, `prune`. `issue_handoff`/`redeem_handoff`/`forget_handoffs` are deprecated (0.3.0).
- State: `StatePayload` and `encode_state` gain `intent`, `device_hash`, `attempt_id`, `oidc_nonce`, `set_id`,
  `login_hint`, `expected_subject` (and `nonce=`); `sub` may be None for a sign-in; old states decode as `connect`.
  `decode_state` refuses a connect state without `sub` and unknown intents. Connect `complete` refuses sign-in states.
- Scopes: `GOOGLE_SIGNIN`, `MICROSOFT_SIGNIN`, `MICROSOFT_SIGNIN_FULL`, `GOOGLE_MAIL_SEND`, `GOOGLE_CALENDAR`,
  `is_identity_only(provider_name, scopes)`.
- `OAuthProvider.authorize_url` gains `offline`, `prompt`, `nonce`, `login_hint` (Google: `access_type=online` and
  `prompt=select_account` when not offline); `MicrosoftOAuth(pinned_tenant=)`; `MicrosoftOAuth.userinfo` adds `mail`.
- `start_flow(device_hash=, attempt_id=)` store a native connect's device hash and attempt id in the state (same
  validation as `SignInFlow.start`: `invalid_request`); `store_connection` is exported from the barrel.
- Connect account binding: `start_flow(login_hint=, expected_subject=, set_id=)`; `complete` raises `account_mismatch`
  (skipped for `shared`). `service.connection_fields` builds the row values.
- `FakeOAuth`: `unsigned_ids_ok`, `client_id`, `kind`, `pinned_tenant`, `set_scopes`, `clock`; codes `mock` and
  `mock:<b64 email>[;decline=<ids>]` (`fake.mock_code`); unsigned `id_token`; refresh token only for an offline flow.

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
