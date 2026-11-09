"""Runs `wiring.install(app)` before any other route module.

main.py imports route modules in alphabetical order and may not be edited, so this module is named `a0_wiring`
to sort before `auth`, `connections`, `health`, `storage` and `sync`. Middleware and error handlers must be added
before the first request; `register` runs at app build time, which satisfies that.
"""

from fastapi import FastAPI

from ..wiring import install


def register(app: FastAPI) -> None:
    install(app)
