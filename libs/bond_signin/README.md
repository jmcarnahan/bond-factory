# bond_signin

Direct Google/Microsoft sign-in for a FastAPI service: Protocol seams, a scope policy, the fixed refusal order and
a router factory. It imports `fastapi` (with starlette) and the standard library only. No sibling `bond_*`
lib is imported: `bond_oauth` (`SignInFlow`, `HandoffStore`) and `bond_auth_py` (`SessionStore`) ship classes whose
shapes satisfy the Protocols here, and errors are matched by a `code` attribute.

## What the app writes
1. A `UserDirectory` (below): the one file that knows your users table.
2. Settings: `SignInSettings` (or `from_env()`), a `ScopePolicy`, and a `CookiePolicy` from your auth settings.
3. One mount: `app.include_router(make_signin_router(...))`.

```python
from bond_signin import IdentityTaken, SessionSpec  # IdentityTaken: raise it from link_identity

class Directory:  # structurally a bond_signin.UserDirectory; `user` is your row (id, is_active, identity, sessions_valid_after)
    def find_by_identity(self, s, provider, subject):
        return s.scalar(select(User).where(User.idp == provider, User.idp_subject == subject))
    def find_by_id(self, s, user_id): return s.get(User, user_id)
    def find_invite(self, s, emails, provider, *, subject=None):  # subject: match a pre-known IdP subject too
        rows = {u.id: u for u in s.scalars(select(User).where(func.lower(User.email).in_(emails), User.removed.is_(False)))}
        return next(iter(rows.values())) if len(rows) == 1 else None  # none or ambiguous: not_invited
    def link_identity(self, s, user, provider, subject):
        user.idp, user.idp_subject = provider, subject  # raise IdentityTaken() if the pair is taken
    def check_allowed(self, s, user, provider): ...  # raise AuthRefused("company_suspended" | "provider_not_allowed")
    def capabilities(self, s, user): return list(user.capabilities)
    def session_spec(self, s, user): return SessionSpec(sub=user.id, name=user.name, capabilities=list(user.capabilities))
    def public(self, s, user): return user.public()  # the `user` JSON of every answer, same as /auth/me
    def record_sign_in(self, s, user, *, provider, ip, first): user.last_sign_in_at = utcnow()
    def record_refusal(self, s, reason, *, email, user, provider, ip): s.add(AuditRow(reason=reason, email=email))
    def mark_sessions_invalid(self, s, user, at): user.sessions_valid_after = at.replace(tzinfo=None)
    def provider_alive(self, s, user, provider): return None  # identity-only apps; else probe the stored connection

router = make_signin_router(
    directory=Directory(), flow=sign_in_flow, handoffs=handoff_store, sessions=session_store,
    policy=ScopePolicy(signin={"google": ("openid", "email", "profile")}), settings=from_env(),
    cookies=CookiePolicy("app_access_token", "app_refresh_token", access_params, refresh_params),
    session_dep=optional_user, client_ip=client_ip, session_scope=lambda: session_scope(factory),
    connection_model=Connection, rate_limit=lambda request, key: limiter.check(f"{key}:{client_ip(request)}"),
    include_providers=True)
```
`session_scope()` (no arguments) must commit on exit and roll back on an exception. Refusals and refresh reuse are caught
inside it so the audit row and the family revoke are committed.

## Routes
| Route (under `prefix`, default `/auth`; return page at `/app/return`) | Body or query | Answer | Errors |
|---|---|---|---|
| `POST /auth/signin/{p}/start` | `{redirect_to, mode: web or native, device_challenge?, attempt?}` | `{url}`, web also sets the nonce cookie | 400 `invalid_request`, 403 `invalid_origin`, 404 |
| `GET /auth/signin/{p}/callback` | `state`, `code` or `error` | 302 to `redirect_to?signin=ok` or `?signin=error&reason=` (native: `?attempt=&code=` or `&error=`) | 400 `invalid_state` (no redirect) |
| `POST /auth/signin/redeem` | `{code, device_secret, device_label?}` | `{token, expires_in, refresh_token, user}` | 401 `invalid_handoff`, 403 `deactivated`, 401 `session_revoked` |
| `POST /auth/refresh` | `{refresh_token?, rotation_id?, delivery?}` or `{id_token}` (legacy) | `{token, expires_in, user, refresh_token?}` | 401 `refresh_reused`, `refresh_expired`, `refresh_revoked`, `invalid_token` |
| `POST /auth/logout` | cookie or `{refresh_token}` | `{"status": "logged_out"}` | 403 `invalid_origin` on cookie delivery without an allowed Origin; otherwise never fails (a revoke error is swallowed) |
| `POST /auth/sessions/revoke-all` | signed in | `{revoked: n}` | 401 `invalid_token` |
| `GET /auth/providers` | optional (`include_providers`) | your payload plus `signin`, `break_glass`, `default_flow` | |
| `GET /app/return/{p}` | | static "Return to the app" page | |

Cookie delivery (web) sets the access cookie and an HttpOnly `SameSite=Lax` refresh cookie and keeps the refresh
token out of the JSON; body delivery (native) returns it in the JSON and sets no cookie. Every cookie-delivery POST
needs an `Origin` (or `Referer`) in `redirect_allowlist` or the API's own origin: 403 `invalid_origin` otherwise.
The web nonce cookie is per flow, `bond_signin_<8 hex of sha256(nonce)>`, set by the start POST, never by a link.

## Factory arguments the app must supply
| Argument | Meaning |
|---|---|
| `session_scope` | `() -> context manager` yielding the DB session; commits on exit, rolls back on an exception |
| `connection_model` | the app's connection table class, passed to `flow.store` when a sign-in carries offline scopes |
| `cookies` | `CookiePolicy(access_name, refresh_name, access_cookie(secure), refresh_cookie(secure), refresh_path=None)` |
| `providers_payload` | REQUIRED with `include_providers=True`: your own `/providers` fields, else they vanish from the answer |
| `legacy_refresh` | `(request, body) -> answer`; REQUIRED while installed builds still post `{id_token}` to refresh |
| `labels` | optional `{provider: button label}` for the `signin` list |
| `clock` | optional `() -> epoch seconds`, passed as `now` to sessions, hand-offs and the order |
| `prefix` | default `settings.prefix` (`/auth`). Routes, the nonce cookie (`<prefix>/signin`) and the refresh cookie (`<prefix>`) move together; the return page is at `<parent>/app/return/{p}`. Set the flow's `public_base` to match |

`from_env(prefix="BOND_SIGNIN_")` names (all prefixed):
| Name | Default | Meaning |
|---|---|---|
| `PROVIDERS` | empty | comma list of provider ids |
| `PUBLIC_BASE` | required | https base of the API (http only with `ALLOW_HTTP`) |
| `REDIRECT_ALLOWLIST` | empty | comma list of web origins allowed as `Origin` and `redirect_to` |
| `NATIVE_RETURN_BASE` | `<PUBLIC_BASE><parent of PREFIX>/app/return` | the https return URL the phone app is sent to |
| `NATIVE_SCHEMES` | empty | reverse-domain custom schemes allowed as a fallback |
| `BREAKGLASS` | off | break-glass flag; `AuthSettings.email_password_enabled` must follow it |
| `COOKIE_SECURE` | on (off with `ALLOW_HTTP`) | Secure flag of the cookies |
| `ALLOW_HTTP` | off | local runs only |
| `PREFIX` | `/auth` | where the routes mount; `make_signin_router` and `callback_url` both use it |

Origin rule for your own routes: any cookie-authenticated mutation outside this router needs the same check; see
`services/sdk_example/sdk_example/origin_rule.py` (bearer requests skip it).

Log hygiene: scrub the `code`, `state` and `attempt` query parameters from access logs for `/auth/signin/*/callback`
and `/app/return/*`.

## Refusal order (`order.sign_in`)
`tenant_mismatch` (upstream, in the flow) then `email_not_verified`, `not_invited`, `check_allowed`
(`company_suspended`, `provider_not_allowed`), `deactivated`, `identity_mismatch`, `session_revoked`, link. Every
refusal calls `record_refusal` and nothing is stored. Then: store connection, issue session, `record_sign_in`.

## Other helpers
- `ScopePolicy`, `wanted_sets(policy, caps, provider, granted)` for `GET /connections`, `connect_scopes(policy,
  set_id, granted)` for `start?set=`, `normalize_email(provider, email)` (gmail dots and `+tag`, matching only).
- `finish_session(response, issued, settings=, cookies=, delivery=)` for break-glass and demo routes.
- `refusal_code(exc)`, `http_error(code)`, `STATUS_FOR_CODE`, `MESSAGES`.
- The AASA and assetlinks files: `bond_service_kit.well_known_router`.
