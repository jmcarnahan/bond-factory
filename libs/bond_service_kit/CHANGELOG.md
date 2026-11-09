# Changelog

## 0.1.0 - unreleased
- Errors: `ApiError`, `RateLimited`, `error_body`, `install_error_handlers(legacy_detail_string=)`, `UnhandledErrorMiddleware`.
- Middleware: `SecurityHeadersMiddleware`, `DBSessionMiddleware` / `db_session_middleware`, `LoggingCORSMiddleware`, `UploadLimit`.
- Rate limiting: `RateLimiter`, `limiters`, `rate_limit_dependency`, `ThreadLimiter`, `thread_limiter`.
- `Clock` and `clock`; `make_session_factory`, `session_scope`, `schema_contract`; `health_router`, `HealthSlot`;
  `mount_web`, `mount_uploads`.
- `well_known_router`: `/.well-known/apple-app-site-association` and `/.well-known/assetlinks.json` for app-link return URLs.
