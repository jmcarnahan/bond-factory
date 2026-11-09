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

### Phone apps (native flow)

A phone app has no browser session, so the web binding cannot apply. The variant exchanges a one-time code:
1. The app calls `GET /connections/{provider}/start?mode=native&redirect_to=<app-scheme url>` with its bearer token.
   The route runs `start_flow(..., native=True)`; `redirect_to` must match an entry of
   `SDK_EXAMPLE_NATIVE_REDIRECTS` (default `sdkdemo://connections`).
2. The app opens the returned URL in the system browser (ASWebAuthenticationSession or a custom tab). `/go` needs no
   session for a native state and sets no cookie.
3. The callback completes with `expected_nonce=None, expected_user_id=None` (accepted only for a native state). That
   exchanges the provider code but STORES NOTHING: it returns a `PendingConnection`, which `issue_handoff(pending)`
   seals (encrypted tokens included) into a one-time code. It redirects to
   `redirect_to?connection=connected&provider=<p>&code=<handoff>`.
4. The app receives the scheme redirect and calls `POST /connections/{provider}/redeem {code}` with its bearer token.
   `redeem_handoff` inserts the row (revoking older live rows) only for the user who started the flow, and only once.
   The answer is the connection status.

Guarantee: nothing is stored until the starting user redeems. A victim lured through an attacker's native link gets a
code bound to the attacker's user; the code goes to the victim's app scheme, the victim redeems as themself and is
refused (`invalid_handoff`), and no row is written. The attacker does not receive the code over the web. The residual risk is on the phone: a custom URL scheme can be
claimed by another app, and a malicious app holding the attacker's bearer token could redeem a code delivered to it.
Use universal links / app links in production; a consent screen cannot prevent this. The code carries the encrypted tokens and can reach about 5 KB with
provider-sized tokens (fine for iOS and Android intents, but long). The route passes
`expected_provider`, so a code redeemed at another provider's route is refused before anything is stored.

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

- The native hand-off keeps its single-use registry in process memory (`bond_oauth.handoff`). With several server
  processes, or a restart inside the 120 s life of a code, a replayed code re-stores the connection and can undo a disconnect made
  in between; use a database table (unique on the nonce) in the app for multi-process deployments. A native flow has no browser binding (see "Phone apps" in section 2).
- Microsoft has no per-token revoke call: disconnect closes the row only.
- `FakeOAuth` keeps requested scopes in memory; a restart between start and callback gives `invalid_code`.
- The state is expired at its `exp`, not after it (10 minutes, real clock).
