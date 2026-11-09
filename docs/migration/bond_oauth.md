# Migrating to bond_oauth

`libs/bond_oauth` replaces the two OAuth halves the apps grew separately: avalon-crm's Gmail connection (app A) and
sbel-crm's Microsoft Graph connection (app S). paga-time (app P) has no OAuth connection and adopts nothing.
Contract: PKCE S256 for both providers; an encrypted stateless `state`; tokens Fernet-encrypted (key
`BOND_OAUTH_KEY`, two HKDF subkeys for tokens and state); one table `oauth_connections` with one live row per
(user_id, provider, connection_name). The working example is `services/sdk_example` (`routes/connections.py`).

## 1. What it replaces

| App | Today | Becomes |
|---|---|---|
| A | `services/google_oauth.py` (start, callback, revoke, access token) | `start_flow / complete / disconnect / access_token` with `GoogleOAuth` |
| A | `services/secrets.py` (Fernet, own key) | `TokenCipher` |
| A | `UserMailConnectionRecord` (`user_mail_connections`) | a class on `ConnectionsMixin` (`oauth_connections`) |
| A | `rest/routers/mail.py` connect routes; signed-JWT `state` without PKCE | routes below; encrypted state with the PKCE verifier |
| S | `microsoft_graph_service.py` OAuth half (PKCE, exchange, refresh, scopes) | `MicrosoftOAuth` + `service.py` |
| S | `OAuthTokenRecord` (`oauth_tokens`), `oauth_states` table | `oauth_connections`; the states table is dropped |
| S | `auth/token_encryption.py` (AES-GCM, key from the JWT secret, fixed info string) | `TokenCipher` |
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

Why both cookies: a nonce cookie set by an open `/go` does not bind, because an attacker can send the victim the
attacker's `/go` link. The session cookie (same-site, SameSite=Lax) says who; the nonce says which flow.

## 3. Call-site changes

- A: `email` is `account_email`; `provider` is `google` (was `gmail`); `reply_to` goes on the app's subclass; the shared
  office mailbox keeps `user_id` NULL (`start_flow(..., shared=True)` after the app's own owner check); the mock mode
  `AVALON_EMAIL_PROVIDER=mock` becomes a `FakeOAuth` provider.
- `access_token(session, row, provider=, cipher=, mark=, on_reconnect_needed=fn)` replaces `_reconnect_needed`; it raises
  `ReconnectRequired` (was `PermanentFailure`) and `RetryableError` (was `RuntimeError`). The cache lives
  `min(50 min, expires_in - 120 s)`.
- S: refresh passes the STORED scopes (kept); `missing_graph_scopes` becomes `scope_drift`; a rejected refresh now
  marks `last_error` and fires the hook once instead of returning None.
- Scope change (A): `calendar.events.readonly` becomes `calendar.events`. `scope_drift(row.scopes, wanted)` reports it
  missing, so each person reconnects once; show "Reconnect".

## 4. Data

1. Add `BOND_OAUTH_KEY` (32+ random bytes, `python -c "import secrets; print(secrets.token_urlsafe(32))"`) to the secrets.
2. Alembic revision from the model. It includes the partial unique index `uq_oauth_connections_live`
   (`coalesce(user_id, ''), provider, connection_name WHERE revoked_at IS NULL`), which autogenerate cannot compare.
3. One-off copy, decrypting with the OLD scheme and encrypting with `TokenCipher` (A: Fernet to Fernet, new key; S:
   AES-GCM to Fernet): A `user_mail_connections` to rows with `provider` google, `connection_name` google; S `oauth_tokens`
   to `provider` microsoft with `expires_at` and `scopes` copied.
4. Rows that fail to decrypt are skipped and listed; those people reconnect. Keep the old tables one release, then drop
   them (and `oauth_states`).

## 5. Acceptance

- `make -C libs/bond_oauth test` and `lint` pass; the boundary test allows only httpx, cryptography, sqlalchemy, stdlib.
- In the app: connect, see `connected`, force an `invalid_grant` refresh, see `needs_reconnect` and one hook call,
  reconnect, disconnect. The example's connection tests do this, plus the attacker-link and expired-state cases.
- A pre-change consent shows the reconnect prompt, not a failed send. No use of the old JWT `state`, `oauth_states` or
  `OAuthTokenRecord` remains.

## 6. Known gaps

- Native-app variant not built: phone apps need a code-exchange callback (the callback redirects to the app with a
  one-time code the app exchanges with its bearer token); not built in this plan. Native apps have no browser session
  cookie, so the web binding does not apply to them.
- Microsoft has no per-token revoke call: disconnect closes the row only.
- `FakeOAuth` keeps requested scopes in memory; a restart between start and callback gives `invalid_code`.
- The state is expired at its `exp`, not after it (10 minutes, real clock).
