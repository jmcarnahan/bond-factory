"""COPY AS IS. The provider objects, cipher, client ids and scope policy, built once and shared.

Sign-in (`routes/signin.py`) and the connect routes (`routes/connections.py`) both call `ensure_wiring`, so sign-in
works in an app that has no connections module: delete that module and nothing here changes.
"""

from __future__ import annotations

from fastapi import FastAPI

from .oauth_wiring import OAuthWiring, build_wiring


def ensure_wiring(app: FastAPI) -> OAuthWiring:
    """Build once, keep on `app.state.oauth`. Raises RuntimeError at startup when the cipher key is missing."""
    if getattr(app.state, "oauth", None) is None:
        app.state.oauth = build_wiring(app.state.settings)
    return app.state.oauth
