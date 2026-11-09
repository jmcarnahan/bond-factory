# Migrating to bond_auth_py

Firebase id-token verification (injected, mock, firebase-admin tiers), session JWT, revocation checks, identity admin,
identity janitor and capability policies (`libs/bond_auth_py`). Contract: `docs/contracts/auth.md`. Legend: `docs/migration/README.md`.

## 1. What it replaces

Paths: A `backend/avalon/`, P `backend/pagatime/`, S `sbelcrm/`.

| App | Goes away or shrinks | Stays app-side |
|---|---|---|
| A | `auth/firebase.py` 620 becomes a 30-line shim, `auth/capabilities.py` 22 keeps constants, `rest/routers/auth.py` 284 loses `create_access_token` (:40-55) and the janitor (:144-181), `rest/dependencies/auth.py` 212 loses the decode and revocation code (:65-181); `tests/test_firebase_admin.py` 196 | routes, `build_user`, `rest/models/auth.py` 52, `users_admin`, `office_phone`, startup checks (`rest/main.py`), `tests/test_firebase_auth.py` 241 |
| P | `auth/firebase.py` 544, `auth/capabilities.py` 22, `rest/routers/auth.py` 247 and `rest/dependencies/auth.py` 232 in the same way; `tests/test_firebase_admin.py` (identical to A's) | `company` in the login answer, `company_suspended` and `provider_not_allowed` checks, `test_firebase_auth.py`, `test_firebase_auth_proxy.py` |
| S | later (D4): `auth/firebase.py` 743, `auth/token_encryption.py` 42 (goes to `bond_oauth`) | S signs `sub` = e-mail, no `iat`, `error_code` bodies, no revocation: its own contract migration comes first |

## 2. The adapter (A; P the same with `PT_` and `pagatime`)

`auth/settings.py`. Env names `JWT_SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `FIREBASE_PROJECT_ID`, `FIREBASE_SERVICE_ACCOUNT_JSON`/`_FILE`
and `FIREBASE_WEB_API_KEY` are read as they are. The rest map in; issuer and audience come from the brand so live sessions still verify:

```python
import os
from bond_auth_py import AuthSettings, ClaimListPolicy, create_access_token, has_any

_MAP = {"AVALON_FIREBASE_MOCK": "BOND_AUTH_MOCK", "FIREBASE_GOOGLE_ENABLED": "BOND_AUTH_GOOGLE",
        "FIREBASE_APPLE_ENABLED": "BOND_AUTH_APPLE", "FIREBASE_GOOGLE_WEB_CLIENT_ID": "BOND_AUTH_GOOGLE_WEB_CLIENT_ID"}

def auth_settings() -> AuthSettings:
    env = {**os.environ, **{new: os.environ[old] for old, new in _MAP.items() if old in os.environ}}
    return AuthSettings.from_env(env=env, issuer=jwt_issuer(), audience=jwt_audience(), app_name="avalon",
                                 demo_enabled=Config.config().demo_auth_enabled())  # A defaults demo auth ON

def token_for_user(user) -> str:  # was create_access_token(dict); P adds extra_claims={"company_id": user.company.id}
    return create_access_token(sub=user.id, name=user.name, capabilities=list(user.capabilities or []),
                               settings=auth_settings())

OWNER = ClaimListPolicy(superuser="owner")
def has(caps, *any_of): return has_any(caps, *any_of, policy=OWNER)  # same call shape as capabilities.has
```

P's policy (admin passes all, a foreman passes worker checks):

```python
class PagaPolicy(ClaimListPolicy):
    def has(self, source, cap): return super().has(source, cap) or (cap == "worker" and super().has(source, "foreman"))
POLICY = PagaPolicy(superuser="admin")
```

A's `auth/firebase.py` can stay as a shim for its 114 `firebase.<name>` uses. Excerpt; it returns the dict A callers index:

```python
from bond_auth_py import (AuthUnavailable as FirebaseUnavailable, EmailNotVerified, FirebaseIdentityAdmin, IdentityExists,
                          IdentityNotFound, MailNotSent, MockIdentityAdmin, TokenError, admin_ready as _ready,
                          default_mock as mock_identities, mock_active, register_mock_token, set_verifier, verify_id_token as _verify)

def _admin(): s = auth_settings(); return MockIdentityAdmin() if mock_active(s) else FirebaseIdentityAdmin(s)
def admin_ready() -> bool: return _ready(auth_settings())
def verify_id_token(token: str) -> dict:
    i = _verify(token, auth_settings())
    return {"uid": i.uid, "email": i.email, "name": i.name, "auth_time": i.auth_time,
            "sign_in_provider": i.sign_in_provider, "identities": i.identities}
def create_identity(email, name=None): return _admin().create_user(email, name)
def disable(uid): _admin().disable_user(uid)
def enable(uid): _admin().disable_user(uid, disabled=False)
```

Revocation: `class UsersRevocation` with `sessions_valid_after(user_id)` as in `services/sdk_example/sdk_example/auth_dep.py`; call
`check_session(claims, UsersRevocation(session))` before the `is_active` check and `check_exchange(identity, rev, settings, user_id=user.id)` in the exchange.

## 3. Call-site changes

| Old (`firebase.` or router) | New | Find |
|---|---|---|
| `create_access_token(data, expires_delta)` | `create_access_token(sub=, name=, capabilities=, settings=, extra_claims=, ttl=)` | `grep -rn "create_access_token("` |
| `jwt.decode(...)` in the dependency | `decode_claims(token, settings)`; P reads `claims.extra["company_id"]` | `grep -rn "jwt.decode"` |
| `get_identity_by_email` (3), `revoke` (4), `delete_identity` (6), `update_identity_email` (2) | `admin.get_user(email=)`, `.revoke_sessions`, `.delete_user`, `.update_email` | `grep -rn "firebase\."` |
| `send_set_password_mail` (7), `set_password_link` (4), `set_password` (2) | `admin.send_password_reset(email, language)`, `.password_reset_link(email)`, `.set_password` | |
| `firebase.janitor_uninvited(identity, now=, still_stray=)` (14) | `janitor_after_refusal(identity=, admin=, user_exists=, now=, audit=)`; `user_exists` ends the read snapshot first | |
| `register_mock_token` (26), `set_verifier` (9) | unchanged names and arguments | |
| `except FirebaseUnavailable` | `except AuthUnavailable` (answer 503 `auth_unavailable`) | |
| `capabilities.has(caps, *any_of)` (A 6 importers) | the `has` above | |

## 4. Data

No table and no revision: `users.sessions_valid_after` (nullable `DateTime`) already exists in A (`db/models.py:46`) and P (`:108`).
S adds it, nullable, in its own revision. Cookie names stay (`avalon_access_token` is `cookie_name("avalon")`).
The 20/minute limit on the exchange routes moves to `rate_limit_dependency` (see `bond_service_kit`).

## 5. Acceptance

- `pytest backend/tests/test_firebase_auth.py` (and P's proxy test), then the whole auth-dependent suite and `ruff check`.
- A test that a token minted by the old code (same secret, issuer, audience) passes `decode_claims`.
- `assert_startup_safe(auth_settings())` at startup, beside A's other checks (`rest/main.py`); `sessions_valid_after` is nullable on `users`.

## 6. Known gaps

- Not lifted: users table, routes, dependencies, `users_admin`, `build_user`, `office_phone`, the demo-clock payload, the rate limiter, the
  `Config` singleton. The two P codes (`company_suspended`, `provider_not_allowed`) are constants only.
- A ANDed the Google and Apple flags with "Firebase login is live"; `providers_payload` reports the flag alone.
- A mock requested outside tests falls through to the Firebase tier; only `assert_startup_safe` stops it. `decode_claims` allows 10 s of leeway.
