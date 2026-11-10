# Migrating to bond_oauth

`libs/bond_oauth` replaces the two OAuth halves the apps grew separately: avalon-crm's Gmail connection (app A) and
sbel-crm's Microsoft Graph connection (app S). paga-time (app P) has no OAuth connection and adopts nothing.
Contract: PKCE S256; an encrypted stateless `state`; Fernet tokens (key `BOND_OAUTH_KEY`, two HKDF subkeys); one table
`oauth_connections`, one live row per (user_id, provider, connection_name). Version 0.2.0 adds sign-in (below) and the
`oauth_handoffs` table. Example: `services/sdk_example` (`routes/connections.py`, `signin_wiring.py`).

## 1. What it replaces

| App | Today | Becomes |
|---|---|---|
| A | `services/google_oauth.py` (start, callback, revoke, access token) | `start_flow / complete / disconnect / access_token` with `GoogleOAuth` |
| A | `services/secrets.py` (Fernet, own key); `UserMailConnectionRecord` | `TokenCipher`; a class on `ConnectionsMixin` (`oauth_connections`) |
| A | `rest/routers/mail.py` connect routes; signed-JWT `state` without PKCE | routes below; encrypted state with the PKCE verifier |
| S | `microsoft_graph_service.py` OAuth half (PKCE, exchange, refresh, scopes) | `MicrosoftOAuth` + `service.py` |
| S | `OAuthTokenRecord` (`oauth_tokens`), `oauth_states`; `auth/token_encryption.py` (AES-GCM) | `oauth_connections`, no states table; `TokenCipher` |
| S | `rest/routers/connections.py` start/callback/status/disconnect | routes below |

The Graph REST half of S (mail and calendar calls) stays in the app until `bond_calendar` takes the calendar part.

## 2. The adapter

Four app routes over the service functions (see the example):
- `GET /connections/{provider}/start` (authenticated XHR): validate `redirect_to` against an origin allowlist, call
  `start_flow(...)`, return the app's own `/go?state=` URL.
- `GET /connections/{provider}/go` (top-level navigation): needs the session; 403 unless the state's user is the
  session user; set `StartedFlow.nonce` as an httponly SameSite=Lax cookie (Path `/connections`, Max-Age 600, Secure
  outside local dev); redirect to `provider.authorize_url(...)`.
- `GET /connections/{provider}/callback`: needs the session and the nonce cookie; `complete(..., expected_user_id=,
  expected_nonce=)`; redirect to `redirect_to?connection=connected|error`. Without the session or cookie answer 400/401
  and do not redirect (the target comes from an untrusted link). Clear the cookie on every outcome.
- `DELETE /connections/{provider}`: `disconnect(...)` (best-effort provider revoke).

### Phone apps (native flow)

A phone has no browser session, so a device secret binds the flow instead (`docs/contracts/signin.md`):
1. The app calls `GET /connections/{provider}/start?mode=native&redirect_to=<return url>&device_challenge=<sha256 hex>&attempt=<id>`
   with its bearer token. `redirect_to` is the same https app link or native scheme as sign-in (`SDK_EXAMPLE_NATIVE_REDIRECTS` is a deprecated alias).
2. The app opens the URL in the system browser session (never an embedded web view). `/go` needs no session for a native state.
3. The callback exchanges the provider code but STORES NOTHING. It seals the `PendingConnection` (tokens inside the DB row,
   not the URL) with `HandoffStore.issue(purpose="connect", ...)` and redirects to `<return>?attempt=<id>&code=<handoff>`.
4. The app calls `POST /connections/{provider}/redeem {code, device_secret}` with its bearer token. `HandoffStore.redeem`
   claims the row with one `UPDATE`, checks the secret, and the route inserts the row only for the user who started the flow.

Guarantee: nothing is stored until the starting user redeems with the right secret. An intercepted code is useless without
the secret and a wrong secret burns it. Residual risk of a scheme fallback is denial of service. `HandoffsMixin` adds the
`oauth_handoffs` table (columns in the contract); schedule `HandoffStore.prune` (the example does not call it; add it to the app's job tick).
### Sign-in (new in 0.2.0)

`SignInFlow(providers, cipher, client_ids, public_base, pinned_tenants, clock)` has `start`, `complete` and `store`, and
satisfies `bond_signin.IdentityFlow` by shape. `complete` needs the web nonce or the device hash, exchanges the code,
builds an `OidcIdentity` with `identity_from_token_response` (claims checked, no signature, `alg: none` refused unless the
provider sets `unsigned_ids_ok`), and STORES NOTHING; `store` writes the connection only after the checks pass.
Scopes come from `GOOGLE_SIGNIN`, `MICROSOFT_SIGNIN(_FULL)` and the app's policy, never `GOOGLE_DEFAULT`.

Role asks: the connect `authorize_url` carries `login_hint=<signed-in e-mail>` and `complete` compares the provider subject
with the user's bound identity: a different account redirects with `connection=error&reason=account_mismatch` (an `OAuthError`, not an HTTP 403), except
`shared=True` (A's office mailbox) and users with no bound identity. A web connect whose consent omits the asked set stores no row
(`consent_declined`).

## 3. Call-site changes

- A: `email` is `account_email`; `provider` is `google` (was `gmail`); `reply_to` goes on the app's subclass; the shared
  office mailbox keeps `user_id` NULL (`start_flow(..., shared=True)` after the app's own owner check); the mock mode
  `AVALON_EMAIL_PROVIDER=mock` becomes a `FakeOAuth` provider.
- `access_token(session, row, provider=, cipher=, mark=, on_reconnect_needed=fn)` replaces `_reconnect_needed`; it raises
  `ReconnectRequired` (was `PermanentFailure`) and `RetryableError` (was `RuntimeError`). Cache: `min(50 min, expires_in - 120 s)`.
- S: refresh passes the STORED scopes; `missing_graph_scopes` becomes `scope_drift`; a rejected refresh marks `last_error` and
  fires the hook once. Scope change (A): `calendar.events.readonly` becomes `calendar.events`; each person reconnects once.

## 4. Data

1. Add `BOND_OAUTH_KEY` (32+ random bytes, `python -c "import secrets; print(secrets.token_urlsafe(32))"`) to the secrets.
2. Alembic revision from the models (connections and hand-offs). It includes the partial unique index `uq_oauth_connections_live`
   (`coalesce(user_id, ''), provider, connection_name WHERE revoked_at IS NULL`), which autogenerate cannot compare.
3. One-off copy, decrypting with the OLD scheme and encrypting with `TokenCipher` (A: Fernet to Fernet, new key; S:
   AES-GCM to Fernet): A `user_mail_connections` to rows with `provider` google, `connection_name` google; S `oauth_tokens`
   to `provider` microsoft with `expires_at` and `scopes` copied.
4. Rows that fail to decrypt are skipped and listed; those people reconnect. Keep the old tables one release, then drop them.

## 5. Acceptance

- `make -C libs/bond_oauth test` and `lint` pass; the boundary test allows only httpx, cryptography, sqlalchemy, stdlib.
- In the app: connect, see `connected`, force an `invalid_grant` refresh, see `needs_reconnect` and one hook call,
  reconnect, disconnect. The example's connection tests do this, plus the attacker-link and expired-state cases.
- A pre-change consent shows the reconnect prompt, not a failed send. No old JWT `state`, `oauth_states` or `OAuthTokenRecord` remains.
- Sign-in: the attacker-link and lured-victim tests of the example pass; a wrong device secret burns the hand-off.

## 6. Known gaps

- `GoogleOAuth` and `MicrosoftOAuth` have run only against `httpx.MockTransport`; no live exchange, refresh or revoke has
  been made. The first adopter does the first live run (see `bond_signin.md` section 6) and records it in `docs/sdk/sdk-pins.md`.
- `issue_handoff`/`redeem_handoff`/`forget_handoffs` stay as deprecated wrappers in 0.2.0 and go in 0.3.0; use `HandoffStore`. The example no
  longer uses the old process-local registry; the old functions still run it until 0.3.0.
- `FakeOAuth` mints an unsigned `id_token` (`unsigned_ids_ok = True`); the consent form posts `mock:<b64 e-mail>[;decline=<set ids>]`
  so a walk can sign in as any identity, as an uninvited one, or decline a set. A provider name starting `fake` is refused at
  startup outside fake mode. It keeps requested scopes in memory: a restart between start and callback gives `invalid_code`.
- Microsoft has no per-token revoke call: disconnect closes the row only.
- The state is expired at its `exp`, not after it (10 minutes, real clock).

S specifics: `sbel.md` §3 to §6.
