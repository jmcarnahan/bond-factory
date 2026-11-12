# bond_service_kit

FastAPI and SQLAlchemy plumbing shared by the bond services. Depends on `fastapi` and `sqlalchemy` only. It imports no
sibling lib, and libs never import it (they take sessions and callables instead).

## What each piece replaces in an app

| Piece | Replaces |
| --- | --- |
| `ApiError`, `error_body`, `install_error_handlers` | the app's own error normaliser; one body `{"detail": {"code", "message", "hint"?}}` |
| `UnhandledErrorMiddleware` | a catch-all 500 kept inside CORS; also answers 503 `db_unavailable` on a lost database |
| `SecurityHeadersMiddleware` | hand-rolled nosniff, frame, referrer, HSTS and permissions headers |
| `db_session_middleware(factory)` | per-request session scope; `request.state.db`, rolled back and closed after the response |
| `LoggingCORSMiddleware` | stock CORS plus one log line per refused origin |
| `UploadLimit(max_bytes, paths=...)` | route-level size checks that run after the body is spooled; answers 413 `too_large` |
| `RateLimiter`, `limiters`, `rate_limit_dependency` | an in-memory limiter ("20/minute", sliding window, injectable `Clock`) |
| `fake_clock_router(clock, enabled=...)` | a hand-written `/fake/clock` test route: pin the clock, read it, release it |
| `thread_limiter(name, tokens)` | per-event-loop `CapacityLimiter`s for work that must not queue behind route threads |
| `Clock`, `clock` | the app's `now()` / `today(tz)` module; `real_now()` ignores freeze for security stamps |
| `make_session_factory`, `session_scope` | engine and sessionmaker setup (SQLite FKs on, in-memory SQLite shared) |
| `schema_contract(metadata).assert_matches(engine)` | the test that an app's tables carry a lib mixin's columns |
| `health_router(checks, slot=...)`, `HealthSlot` | `/health` with named checks on bounded worker threads |
| `mount_web(app, dir)`, `mount_uploads(app, dir)` | SPA static mount; local uploads mount that never serves `private/` |

## Wiring

```python
app = FastAPI()
engine, factory = make_session_factory(url)
install_error_handlers(app)                       # add legacy_detail_string=True while clients expect strings
app.add_middleware(UnhandledErrorMiddleware)      # innermost
app.add_middleware(UploadLimit, max_bytes=10_000_000)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(LoggingCORSMiddleware, allow_origins=["https://app.example.com"])
app.add_middleware(db_session_middleware(factory))  # outermost
app.include_router(health_router({"db": lambda: db_ok(factory)}))
limiters.register("login", "10/minute")           # route: Depends(rate_limit_dependency("login"))
mount_web(app, "web/")                            # last, so every API route wins
```

## Behaviour worth knowing

- `error_body`: a dict keeps its fields and gains `code` / `message`; a snake_case string becomes the code; any other
  string becomes the message with a code by status (400 `bad_request` ... 503 `unavailable`).
- `code_aliases=("error_code",)` on `install_error_handlers` / `error_body`: a dict detail with no `code` takes it from the
  first alias key present, and keeps the alias key. Without it such a body gains a status-derived code.
- `fake_clock_router(clock, *, enabled, dependencies=())`: `GET` / `PUT /fake/clock` with `{"now": ISO | null}`. `enabled()` is
  called on every request. When it is false every request to `/fake/clock` (any verb, body or trailing slash, with or without
  auth) answers what an unmounted path answers (404, same body), before the body is read; the lib reads no environment. Only
  `null` or an absent `now` releases the pin; an empty or out-of-range value is 422. `clock` is any `PinnableClock` (`frozen`, `now()`, `freeze(at)`, `unfreeze()`); `Clock` is one.
- `RateLimiter(rate)` takes a string or a callable returning one, read on every call (limits from the environment per request). A callable is first called on first use. A bad
  later value keeps the last good rate and logs a warning.
- An exception with a truthy `db_unavailable` attribute is answered 503 `db_unavailable` by `UnhandledErrorMiddleware`.
- Validation errors answer 422 `validation_error` with `errors[{loc, msg, type}]` and never echo input.
- `RateLimited` answers 429 with `Retry-After: 60`; an unhandled error answers 500 `internal_error`.
- `legacy_detail_string=True` leaves string details as plain strings (`{"detail": "Not found"}`); dict details and
  `ApiError` stay in the object form.
- `health_router`: any check that returns False, a message or raises makes the status `degraded` with HTTP 503 (change
  with `degraded_status`). A hung check keeps its slot until its thread ends, so probes cannot pile up threads.
- `Clock.freeze(at, tz)` reads a naive `at` in `tz`. `Clock(source=...)` lets an app supply its own demo time.
- The rate limiter is per process. Run it behind one worker or accept per-worker counts.
- Libs ship no migrations: assert a mixin against your engine with `schema_contract(...)`.
