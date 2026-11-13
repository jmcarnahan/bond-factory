# Migrating to bond_service_kit

FastAPI and SQLAlchemy plumbing (`libs/bond_service_kit`): error body, middleware, rate limits, clock, session
factory, health, web and uploads mounts. Legend: `docs/migration/README.md`.
Contracts: `docs/contracts/error_body.md`.

## 1. What it replaces
Paths: A `backend/avalon/`, P `backend/pagatime/`, S `sbelcrm/`.

| App | Goes away | Stays app-side |
|---|---|---|
| A | `rest/middleware/{security_headers 27, errors 46, rate_limiter 44}.py`, `upload_limit.py` 89 (in part), `rest/uploads_mount.py` 135, `rest/web_mount.py` 51, `LoggingCORSMiddleware` (`rest/main.py:113`); `clock.py` 56 shrinks to a 20-line adapter | `rest/middleware/db_session.py` 53 and `db/session.py` 292 (context-var session, pool sizing), `rest/limiters.py` 33 (sizes tied to the pool), the `/health` body |
| P | same set: `security_headers 31`, `errors 46`, `rate_limiter 44`, `upload_limit 85`, `uploads_mount 133`, `web_mount 51`, `rest/errors.py` 50 (the normaliser the kit took), `clock.py` 85 shrinks | `db_session.py` 51, `db/session.py` 229, `limiters.py` 29, `_HealthSlot` (`rest/main.py:213`) until health moves |
| S | `rest/middleware/security_headers.py` 23 and `rest/uploads_mount.py` 135 only | `rate_limiter.py` 132, `db_session.py` 39, `db/session.py` 140, bodies with `error_code` (later) |

## 2. The adapter

A's `rest/main.py` (P the same). Add the error handlers first, then the middleware: the first added is innermost.

```python
from bond_service_kit import (LoggingCORSMiddleware, SecurityHeadersMiddleware, UnhandledErrorMiddleware,
                              UploadLimit, install_error_handlers, limiters, mount_uploads, mount_web)

install_error_handlers(app, legacy_detail_string=True)  # A's tests and the old clients still read string details
app.add_middleware(UnhandledErrorMiddleware, legacy_detail_string=True)  # innermost: a 500 keeps its CORS headers
app.add_middleware(UploadLimit, max_bytes=SYNC_MAX_REQUEST_BYTES, paths=(SYNC_PREFIX,))  # one call per limit
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(LoggingCORSMiddleware, allow_origins=config.get_cors_origins(), allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.add_middleware(DBSessionMiddleware)  # A's own; the kit's puts one session on request.state.db instead
limiters.enabled = config.rate_limit_enabled()
if uploads_enabled():  # A's existing check (backend is not s3); the kit no longer gates on it
    mount_uploads(app, config.uploads_dir())
...
if config.serve_web():
    mount_web(app, config.web_dir())  # last, so every API route wins
```

A route-level limit, replacing a slowapi decorator (the `request: Request` first-argument and `Annotated` rules go away):

```python
from bond_service_kit import rate_limit_dependency
from bond_service_kit.rate_limit import client_ip

@router.post("/demo-login", dependencies=[Depends(rate_limit_dependency(
    "demo_login", rate=os.getenv("RATE_LIMIT_DEMO_LOGIN", "10/minute")))])  # read once at start, not per request
def demo_login(body: DemoBody): ...
# user-keyed (was user_rate_limit): pass key=lambda r: user_id_from_request(r) or client_ip(r)
```

The clock keeps its module-level functions, so the 95 importers of `avalon.clock` (P: 33) are untouched:

```python
from datetime import UTC, datetime
from zoneinfo import ZoneInfo
from bond_service_kit import Clock

def _source() -> datetime:
    demo = Config.config().demo_today()
    if demo is None:
        return datetime.now(UTC)
    return datetime(demo.year, demo.month, demo.day, 9, 0, tzinfo=ZoneInfo(get_brand().timezone))

_clock = Clock(_source)
real_now, unfreeze = _clock.real_now, _clock.unfreeze
def now() -> datetime: return _clock.now()
def today(): return _clock.today(get_brand().timezone)
def local_now() -> datetime: return _clock.local_now(get_brand().timezone)
def freeze(dt: datetime) -> None: _clock.freeze(dt, get_brand().timezone)  # naive = brand-local
```

## 3. Call-site changes

| Old | New | Find |
|---|---|---|
| `@limiter.limit(...)`, `@ip_rate_limit(...)`, `@user_rate_limit(...)` (A 28, P 13) | `dependencies=[Depends(rate_limit_dependency(...))]` | `grep -rnE "@(ip_rate_limit\|user_rate_limit\|limiter)"` |
| `app.state.limiter`, `RateLimitExceeded` handler | `RateLimited` (handled by `install_error_handlers`, 429 + `Retry-After: 60`) | `grep -rn slowapi` |
| `UploadLimitMiddleware` with a regex path (A photos) | `UploadLimit` subclass overriding `_applies(scope)` | |
| `from avalon.rest.middleware.errors import UnhandledErrorMiddleware` | `from bond_service_kit import UnhandledErrorMiddleware` | |
| `HTTPException(detail={"code": ..., "message": ...})` | unchanged, or `raise ApiError(code, message, status=409, hint=...)` | |

## 4. Data

None. Set `legacy_detail_string=True` now; P already sends object bodies and can keep the default. Optional:
`make_session_factory(url)` returns `(engine, sessionmaker)`; `session_scope(factory)` serves scripts and jobs.

## 5. Acceptance

- The app's own backend suite (A `backend/tests`, P `backend/tests`), `ruff check`, and the retired seed tests
  (`test_robust_cors.py`, `test_clock.py`) deleted in favour of the kit's.
- `GET /nonexistent` answers 404 with a string detail (legacy) or `{"detail": {"code": "not_found", ...}}`.
- 21 requests to a `20/minute` route end in 429 with `Retry-After`. A frozen clock must not move the window.

## 6. Known gaps

- Not lifted: slowapi and its decorator rules, per-request env rates, per-prefix upload limits (one `UploadLimit` per limit),
  the context-var session scope and pool sizing, `_sync_state` and `demo_clock` health fields, the uploads-mount backend gate.
- `health_router` answers `{"status": "ok"|"degraded", "checks": {...}}` with 503 when degraded; A's `{"status": "healthy", "db": "ok"}`
  body differs, so keep the app route until nothing reads `healthy`.
- Legacy mode keeps only string details: 422 and 429 bodies are always the object form. The limiter is in memory per process.

## 7. Added after the first release
- `install_error_handlers(app, code_aliases=("error_code",))`: a dict detail with no `code` takes it from the alias key (kept). Use it
  while old clients still read `error_code`.
- `fake_clock_router(clock, enabled=lambda: settings.mode == "fake", dependencies=[Depends(auth)])` replaces a hand-written
  `/fake/clock`. `clock` is the kit `Clock` or anything with `frozen`, `now()`, `freeze(at)`, `unfreeze()`. Decide `enabled` in the app. While `enabled()` is false the path behaves as if it were not mounted (404, same body, any verb).
  Only `null` or an absent `now` releases the pin.
- `RateLimiter(rate=callable)`, `limiters.register(name, callable)`, `rate_limit_dependency(name, rate=callable)`: an app that reads
  its limits from the environment per request passes `lambda: os.environ.get("LOGIN_RATE", "10/minute")`. This replaces
  the "per-request env rates" gap in section 6. A callable is first called on first use, so it may read settings that load after
  import. A bad later value keeps the last good rate and logs a warning.
- A lib error class can set `db_unavailable = True` and `UnhandledErrorMiddleware` answers it 503 `db_unavailable`.

## 8. Notes
- 2026-11-12: the uploads guard (`mount_uploads`) now resolves the path before deciding, following parent-directory segments and
  symbolic links, and a null byte answers 404. An app that carried its own override of the guard can delete it at its next pin.
