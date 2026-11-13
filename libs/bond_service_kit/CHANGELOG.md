# Changelog

## 0.1.0 - unreleased
- Errors: `ApiError`, `RateLimited`, `error_body`, `install_error_handlers(legacy_detail_string=)`, `UnhandledErrorMiddleware`.
- Middleware: `SecurityHeadersMiddleware`, `DBSessionMiddleware` / `db_session_middleware`, `LoggingCORSMiddleware`, `UploadLimit`.
- Rate limiting: `RateLimiter`, `limiters`, `rate_limit_dependency`, `ThreadLimiter`, `thread_limiter`.
- `Clock` and `clock`; `make_session_factory`, `session_scope`, `schema_contract`; `health_router`, `HealthSlot`;
  `mount_web`, `mount_uploads`.
- `well_known_router`: `/.well-known/apple-app-site-association` and `/.well-known/assetlinks.json` for app-link return URLs.
- `error_body(..., code_aliases=())` and `install_error_handlers(..., code_aliases=())`: a dict detail with no `code` takes it
  from the first alias key present (the alias key is kept). Default unchanged.
- `fake_clock_router(clock, *, enabled, dependencies=())` and the `PinnableClock` Protocol: `GET` / `PUT /fake/clock`
  `{"now": ISO | null}`. Whenever `enabled()` is false (checked per request) every request to `/fake/clock` (any verb, any body, with
  or without auth or a trailing slash) answers what an unmounted path answers (404, same body), before the body is read. Only
  `null` or an absent `now` releases the pin; a bad or empty string, or an instant outside `datetime` range, is 422 `invalid_now`.
- `RateLimiter`, `LimiterRegistry.register` and `rate_limit_dependency` accept `rate: str | Callable[[], str]`, read on every
  call and parsed once per distinct string. A callable is first called on first use, not in `__init__`; if a later call returns a
  bad value the last good rate stays and a warning is logged. `rate`, `limit` and `window` have setters again (`limit` and
  `window` override until `rate` is next set).
- `code_aliases` given as a plain string is one alias.
- `UnhandledErrorMiddleware` answers 503 `db_unavailable` for any exception with a truthy `db_unavailable` attribute.
- The uploads guard decides on the resolved path as well as the raw one: parent-directory segments and symbolic links are
  resolved first, so neither can reach the private prefix; a null byte in the path answers 404.
