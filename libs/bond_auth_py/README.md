# bond_auth_py

Firebase ID token verification, the app's own session JWT, revocation, identity admin and an opt-in janitor.
Framework-free: no FastAPI, no service kit, no database. The app wires these pieces into its routes.

## Pieces

| Module | What it gives you |
|---|---|
| `settings` | `AuthSettings` dataclass, `from_env`, `mock_active`, `assert_startup_safe` |
| `verify` | `verify_id_token(token, settings) -> Identity`, `set_verifier`, mock tier |
| `tokens` | `create_access_token`, `decode_claims`, `cookie_name`, `read_bearer_or_cookie` |
| `session` | `check_session` (every request), `check_exchange` (sign-in), `RevocationCheck` |
| `capabilities` | `ClaimListPolicy`, `RolePolicy`, `has`, `has_any` |
| `errors` | code strings, `AuthRefused(code, message, hint, status)`, `not_invited(email)` |
| `providers` | `providers_payload` for `GET /auth/providers` |
| `admin`, `janitor` | `IdentityAdmin` (Firebase or mock), `janitor_after_refusal` |

Verifier tiers, in order: an installed verifier (`set_verifier`), the mock (tier `mock` AND pytest running or the
test-env flag), then firebase-admin (imported lazily; `check_revoked` only with a service account).

## Wiring `POST /auth/firebase` (FastAPI)

```python
settings = AuthSettings.from_env(app_name="myapp")
assert_startup_safe(settings)                      # at startup: refuses the mock outside tests

@router.post("/auth/firebase")
def firebase_login(body: LoginBody, request: Request):
    try:
        identity = verify_id_token(body.id_token, settings)
    except EmailNotVerified:
        raise refused(AuthRefused("email_not_verified"))
    except TokenError:                             # one answer for every reason
        raise refused(AuthRefused("invalid_token"))
    except AuthNotConfigured:                      # 501
        raise refused(AuthRefused("firebase_not_configured"))
    except AuthUnavailable:                        # 503: provider outage, the client must NOT sign the person out
        raise refused(AuthRefused("auth_unavailable"))
    user = db.user_by_email(identity.email)        # app code
    if user is None or user.removed:
        if janitor_after_refusal(identity=identity, admin=admin, now=datetime.now(UTC),
                                 user_exists=db.has_uid_or_email, audit=db.audit_janitor):
            db.commit()
        raise refused(not_invited(identity.email))
    if not user.is_active:
        raise refused(AuthRefused("deactivated"))
    check_exchange(identity, db_revocation, settings, user_id=user.id)   # raises SessionRevoked
    token = create_access_token(sub=user.id, name=user.name, capabilities=user.caps, settings=settings,
                                extra_claims={"company_id": user.company_id})
    response = JSONResponse({"token": token, "user": user.public()})
    response.set_cookie(cookie_name("myapp"), token, **session_cookie_params(settings, secure=True))
    return response

def refused(exc: AuthRefused) -> HTTPException:    # the app owns its error body
    return HTTPException(exc.status, {"detail": exc.detail()})
```

Per request: `read_bearer_or_cookie(request.headers, request.cookies, cookie_name("myapp"))`, then
`decode_claims`, then `check_session(claims, db_revocation)` BEFORE any `is_active` check (an old token of a
deactivated person gets `session_revoked`, like any dead session). `RevocationCheck` is one method,
`sessions_valid_after(user_id) -> datetime | None` (naive datetimes are UTC). Authority (capabilities, active)
is always re-read from the database; the token's `capabilities` claim is informational.

Session JWT: HS256, claims `sub`, `user_id`, `name`, `capabilities`, `iat` (float, real clock), `exp`, `aud`
(list), `iss`. `check_exchange` refuses an ID token when `auth_time + skew < sessions_valid_after` (skew 5 s).
Janitor: only after `not_invited` on sign-in (not refresh); deletes a Google or Apple identity created under
60 s ago whose provider list is exactly that provider and that has no users row (asked twice); never raises.

## Mock tier (tests and demos)

```python
set_verifier(None); default_mock().register_mock_token("tok", "uid-1", "a@example.com", "A")
settings = AuthSettings(jwt_secret="...", tier="mock")
verify_id_token("tok", settings)                   # or the literal "mock:a@example.com"
```

`default_mock().load_file(path)` seeds identities from a JSON list of `{email, name?, uid?, token?}`.
`MockIdentityAdmin` is the in-memory admin over `default_mock()`; set `fail_mail`, `fail_link` or `unavailable`
on `default_mock()` (the `MockIdentities` store it wraps) to force error paths.

## Environment (`AuthSettings.from_env(prefix="BOND_AUTH_", firebase_prefix="FIREBASE_")`)

| Variable | Field |
|---|---|
| `BOND_AUTH_JWT_SECRET` (or `JWT_SECRET_KEY`) | `jwt_secret` |
| `BOND_AUTH_ISSUER`, `_AUDIENCE` | `issuer` (`bond`), `audience` (`bond-api`) |
| `BOND_AUTH_ACCESS_TTL_MINUTES` (or `ACCESS_TOKEN_EXPIRE_MINUTES`) | `access_ttl_minutes` (10080) |
| `BOND_AUTH_AUTH_TIME_SKEW_SECONDS` | `auth_time_skew_seconds` (5) |
| `BOND_AUTH_MOCK`, `_TEST_ENV`, `_MOCK_IDENTITIES_FILE` | mock tier, second switch, identities file |
| `BOND_AUTH_GOOGLE`, `_GOOGLE_WEB_CLIENT_ID`, `_APPLE`, `_EMAIL_PASSWORD`, `_DEMO` | provider flags |
| `FIREBASE_PROJECT_ID`, `_SERVICE_ACCOUNT_JSON`, `_SERVICE_ACCOUNT_FILE`, `_WEB_API_KEY` | server config |
| `FIREBASE_AUTH_DOMAIN`, `_MESSAGING_SENDER_ID`, `_WEB_APP_ID`, `_IOS_API_KEY`, `_IOS_APP_ID`, `_IOS_BUNDLE_ID` | public client config for `/auth/providers` |

An app with its own variable names builds `AuthSettings(...)` directly or passes a different prefix.
