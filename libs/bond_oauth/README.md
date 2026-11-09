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
  STORES NOTHING and returns a `PendingConnection`. The app seals it with
  `HandoffStore.issue(purpose="connect", ...)` (tokens stay in the database row, never in a URL; 120 s, single use by
  one `UPDATE`, bound to the device secret) and redeems it with its bearer token and the device secret; the route then
  stores through `store_connection` only for the user who started the flow. A victim lured through an attacker's link
  gets a code bound to the attacker, is refused and nothing is stored. See the example's `routes/connect_native.py`.
  The old `issue_handoff` / `redeem_handoff` / `forget_handoffs` (process-local registry) are deprecated, kept for
  0.2.x compatibility and removed in 0.3.0. A custom URL scheme can be claimed by another app on the phone; the device
  secret makes an intercepted code useless, and universal/app links remain the production choice.
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

## Sign-in (0.2.0)

`SignInFlow` identifies a person with the provider's code flow. It stores nothing; the app decides who the person is,
then calls `store`.

```python
flow = SignInFlow(providers={"google": google}, cipher=cipher, client_ids={"google": GOOGLE_CLIENT_ID},
                  public_base="https://api.example.org", pinned_tenants={"microsoft": TENANT_GUID})
started = flow.start(provider="google", scopes=GOOGLE_SIGNIN, redirect_to=app_page)   # .url, .nonce, .state
# web: the start POST sets .nonce as a cookie; native: pass device_hash=sha256_hex(device_secret) instead
result = flow.complete(state=state, code=code, expected_nonce=cookie, expected_device_hash=None)
result.identity            # OidcIdentity: provider, subject, tenant, email, email_verified, name, auth_time, hd
result.pending             # PendingConnection when mail/calendar scopes came with a refresh token, else None
flow.store(session, OAuthConnection, owner=user_id, result=result)   # one live row per (owner, provider, name)
```

- The callback is `<public_base>/auth/signin/<provider>/callback`. Identity-only scopes (`is_identity_only`:
  Google openid/email/profile; Microsoft those plus `User.Read` and no `offline_access`) ask Google for
  `access_type=online`, `prompt=select_account`, so a login never mints a refresh token. Microsoft always sends
  `prompt=select_account`. Sets: `GOOGLE_SIGNIN`, `MICROSOFT_SIGNIN`, `MICROSOFT_SIGNIN_FULL`, `GOOGLE_MAIL_SEND`,
  `GOOGLE_CALENDAR`. A sign-in never uses `GOOGLE_DEFAULT`.
- `complete` refuses a `connect` state (`invalid_state`), a wrong cookie nonce or device hash (`invalid_state`) and an
  old state (`signin_expired`). The OIDC `nonce` sent to the provider is sha256 hex of the state nonce.
- `identity_from_token_response` checks `iss`, `aud`, `exp`, `nonce` and reads `sub` (Google) or `tid:oid` (Microsoft).
  The signature is NOT checked (the token came straight from the token endpoint over TLS); `alg: none` is refused
  unless the provider sets `unsigned_ids_ok` (only `FakeOAuth`). Never call it with a token from anywhere else.
  Microsoft: a `tid` other than the pinned tenant, a guest (`idtyp`, `#EXT#`) is `tenant_mismatch`; `email_verified` is
  true only when a tenant is pinned. Google `email_verified` may be a bool or `"true"`/`"false"`.
- `flow.peek(state=)` decodes a state with no network (`StateInfo`, incl. `expired`; unauthentic is `invalid_state`).
  A real Microsoft provider needs a GUID tenant pin at construction (`common` and the like are refused).
  Native connect goes through `HandoffStore` (the example's `routes/connect_native.py`).
- Role asks (connect) bind to the account: `start_flow(login_hint=, expected_subject=)`; `complete` raises
  `account_mismatch` for another account, except `shared=True`.
- `HandoffStore(model, cipher)` over `HandoffsMixin` (table `oauth_handoffs`): `issue` (sealed payload, device hash,
  120 s), `redeem(code, device_secret, purpose)` (one `UPDATE` claims the row; a wrong secret or purpose burns it;
  `invalid_handoff`), `prune`. The module `handoff.py` (process-local registry) is deprecated, removed in 0.3.0.
- `FakeOAuth(consent_base, email, *, client_id, kind="google"|"microsoft", pinned_tenant, set_scopes)`: the code
  `mock` or `fake.mock_code(email, decline_set_ids)` picks the identity and the declined sets; it returns an unsigned
  `id_token`, and a refresh token only for an offline flow (Microsoft: `offline_access`).
