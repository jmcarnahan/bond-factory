"""FastAPI and SQLAlchemy plumbing shared by the bond services."""

from .clock import Clock, clock
from .db import SchemaContract, make_session_factory, schema_contract, session_scope
from .errors import (
    ApiError,
    RateLimited,
    UnhandledErrorMiddleware,
    error_body,
    install_error_handlers,
)
from .health import HealthBusy, HealthSlot, health_router
from .middleware import (
    DBSessionMiddleware,
    LoggingCORSMiddleware,
    SecurityHeadersMiddleware,
    db_session_middleware,
    security_headers_middleware,
)
from .mounts import mount_uploads, mount_web
from .rate_limit import (
    LimiterRegistry,
    RateLimiter,
    ThreadLimiter,
    limiters,
    parse_rate,
    rate_limit_dependency,
    thread_limiter,
)
from .upload_limit import UploadLimit
from .well_known import well_known_router

__version__ = "0.1.0"

__all__ = [
    "ApiError", "Clock", "DBSessionMiddleware", "HealthBusy", "HealthSlot", "LimiterRegistry",
    "LoggingCORSMiddleware", "RateLimited", "RateLimiter", "SchemaContract", "SecurityHeadersMiddleware",
    "ThreadLimiter", "UnhandledErrorMiddleware", "UploadLimit", "clock", "db_session_middleware",
    "error_body", "health_router", "install_error_handlers", "limiters", "make_session_factory", "mount_uploads",
    "mount_web", "parse_rate", "rate_limit_dependency", "schema_contract", "security_headers_middleware",
    "session_scope", "thread_limiter", "well_known_router",
]
