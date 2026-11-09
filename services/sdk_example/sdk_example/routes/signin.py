"""Mounts direct sign-in. Sorts after `connections`, which builds `app.state.oauth` (the providers it needs)."""

from fastapi import FastAPI

from ..signin_wiring import install_signin


def register(app: FastAPI) -> None:
    install_signin(app, app.state.oauth)
