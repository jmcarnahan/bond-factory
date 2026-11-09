"""``GET /auth/providers`` (optional): the app's payload plus ``signin``, ``break_glass``, ``default_flow``."""

from __future__ import annotations

from fastapi import APIRouter

from ._common import Deps


def register(router: APIRouter, deps: Deps) -> None:
    @router.get("/auth/providers")
    def providers() -> dict:
        payload = dict(deps.providers_payload() if deps.providers_payload else {})
        payload.setdefault("signin", [{"id": p, "label": deps.labels.get(p, p.title())}
                                      for p in deps.settings.providers])
        payload.setdefault("break_glass", deps.settings.break_glass)
        payload.setdefault("default_flow", "signin" if deps.settings.providers else "firebase")
        return payload
