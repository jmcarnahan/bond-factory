"""Mounts direct sign-in. Needs no connections module: `ensure_wiring` builds the providers either way."""

from fastapi import FastAPI

from ..fake_routes import register_fake
from ..providers_wiring import ensure_wiring
from ..signin_wiring import install_signin


def register(app: FastAPI) -> None:
    install_signin(app, ensure_wiring(app))
    if app.state.settings.mode == "fake":
        register_fake(app, app.state.oauth)  # the fake consent page sign-in redirects to
