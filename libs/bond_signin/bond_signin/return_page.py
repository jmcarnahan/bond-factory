"""``GET <parent of prefix>/app/return/{provider}`` (``/app/return/...`` by default): shown only when the app is not installed to catch the link (§3.8 G)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

PAGE = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1">'
    '<meta name="referrer" content="no-referrer"><title>Return to the app</title>'
    "<style>body{font:16px system-ui,sans-serif;margin:3rem 1.5rem;text-align:center}</style></head>"
    "<body><p>Return to the app</p></body></html>"
)
HEADERS = {
    "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
}


def register(router: APIRouter, *, prefix: str = "/auth") -> None:
    """Served at ``<parent of prefix>/app/return/{provider}``: ``/app/return/...`` for ``/auth``,
    ``/api/v1/app/return/...`` for ``/api/v1/auth``."""
    parent = prefix.rsplit("/", 1)[0]

    @router.get(f"{parent}/app/return/{{provider}}", include_in_schema=False)
    def return_page(provider: str) -> HTMLResponse:  # the query (attempt, code) is never read or logged
        return HTMLResponse(PAGE, headers=HEADERS)
