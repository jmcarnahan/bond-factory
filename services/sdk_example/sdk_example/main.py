"""FastAPI reference app. Route modules under routes/ are discovered, not listed.

Run with `uvicorn sdk_example.main:create_app --factory`; nothing is built at import.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models, routes  # noqa: F401  (models import attaches every mixin to Base)
from .db import make_engine, make_session_factory
from .settings import Settings

log = logging.getLogger("sdk_example")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    if settings.mode == "fake":
        log.warning("sdk_example running in FAKE mode (mock identities, demo auth)")
    app = FastAPI(title="sdk_example")
    app.state.settings = settings
    app.state.engine = make_engine(settings)
    app.state.session_factory = make_session_factory(app.state.engine)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    for info in pkgutil.iter_modules(routes.__path__):
        importlib.import_module(f"{routes.__name__}.{info.name}").register(app)
    return app
