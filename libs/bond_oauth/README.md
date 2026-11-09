# bond_oauth

OAuth2 flows and encrypted token storage for Google and Microsoft. Depends on httpx, cryptography and SQLAlchemy only.

```python
class OAuthConnection(ConnectionsMixin, Base): ...          # table oauth_connections

cipher = TokenCipher.from_env("BOND_OAUTH_KEY")
flow = start_flow(session, user_id=uid, provider_name="google", provider=google, scopes=list(GOOGLE_DEFAULT),
                  redirect_to=app_page, cipher=cipher, redirect_uri=callback_url)   # flow.state, .authorize_url, .nonce
row = complete(session, state=state, code=code, providers={"google": google}, cipher=cipher,
               connection_model=OAuthConnection, redirect_uri=callback_url,
               expected_user_id=session_user, expected_nonce=nonce_cookie)   # both REQUIRED (TypeError if missing)
token = access_token(session, row, provider=google, cipher=cipher, on_reconnect_needed=notify)
status(session, user_id=uid, provider="google", connection_model=OAuthConnection)   # ConnectionStatus
disconnect(session, user_id=uid, provider_name="google", connection_model=OAuthConnection, provider=google, cipher=cipher)
```

- PKCE S256 for both providers. `state` is an encrypted payload (sub, provider, connection_name, nonce, exp, verifier,
  redirect_to, shared) valid 10 minutes on the real clock: `OAuthError("invalid_state" | "expired_state")`.
- Bind the flow to the browser that started it (login-CSRF defence). `start_flow(...)` returns `StartedFlow(state,
  authorize_url, nonce)`. The nonce cookie alone is NOT enough: an attacker can send a victim their own link, and
  the victim's browser would receive the attacker's nonce. The binding is therefore the app's signed-in session
  cookie plus the nonce cookie:
  1. The authenticated start call returns an app URL (`/go?state=`), not the provider URL.
  2. `/go` requires the session (a same-site, SameSite=Lax cookie is sent on top-level navigation), refuses with 403
     unless the state's `sub` is the session user, then sets `nonce` as an httponly SameSite=Lax cookie and
     redirects to the provider.
  3. The callback requires the session again and calls `complete(..., expected_user_id=<session user>,
     expected_nonce=<cookie>)`. A mismatch raises `OAuthError("invalid_state")` and stores nothing.
  `start` is a thin wrapper that returns only the URL and gives no binding.
- Native apps have no browser session cookie, so this web binding does not cover them. They use the code-exchange
  variant: `start_flow(..., native=True)` marks the state native; the callback calls `complete(...,
  expected_nonce=None, expected_user_id=None)` (accepted ONLY for a native state), which exchanges the code but
  STORES NOTHING and returns a `PendingConnection`. `issue_handoff(pending, cipher=)` seals it (encrypted tokens
  included) into a 120 s one-time code. The app redeems it with its bearer token via `redeem_handoff(session, code=,
  user_id=, cipher=, connection_model=)`, which inserts the row only for the user who started the flow. A victim
  lured through an attacker's link gets a code bound to the attacker, is refused and nothing is stored. Expired,
  used, damaged or another user's codes raise `OAuthError("invalid_handoff")`. Single use is a process-local registry:
  a replay within 120 s after a restart, or in another process, re-stores the connection and can undo a disconnect;
  for multi-process deployments keep a nonce table in the app. The code is bound to the user, not the device: a
  custom URL scheme can be claimed by another app on the phone, so use universal/app links in production (a consent
  screen cannot prevent it). The code carries the encrypted tokens and can reach about 5 KB with provider-sized
  tokens (fine for iOS and Android intents, but long). `redeem_handoff(..., expected_provider=)` refuses a code for another provider before
  anything is stored.
- One live row per (owner, provider, connection_name) is also enforced by the partial unique index
  `uq_oauth_connections_live`. A callback that loses a race is retried once after revoking the winner's row, then
  raises `OAuthError("conflict")`.
- The access-token cache lives `min(50 minutes, expires_in - 120 s)`; a token with under two minutes left is not cached.
- `TokenCipher` is Fernet over two HKDF-SHA256 subkeys derived from the one master secret (`info`
  `bond_oauth/tokens` and `bond_oauth/state`), so a state blob never decrypts as a token and the reverse. The secret
  may be a Fernet key or any string; outside fake mode use 32 or more random bytes:
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`. A wrong key or wrong purpose raises `ValueError`.
- `provider` on the row is the name the app registered the provider under (`google`, `microsoft`, or a fake's name).
- `access_token`: cached 50 minutes per connection and refresh ciphertext; refresh sends the STORED scopes.
  `invalid_grant`, `unauthorized_client`, `invalid_client` and HTTP 401 raise `ReconnectRequired`, set `last_error` and
  fire `on_reconnect_needed` once. Timeouts and 5xx raise `RetryableError`. `mark=False` never writes the row.
- Service functions commit the rows they change.
- `FakeOAuth` needs no network: its consent page is the app's, `exchange(code="mock")` mints tokens.
- `scope_drift(granted, wanted)` lists missing scopes, comparing short names case-insensitively.
- `ConnectionsMixin.user_id` references `users.id`; set `user_fk_target` on the subclass to change or drop it.
