"""``GET /app/return/{provider}``: shown only when the app is not installed to catch the link (§3.8 G)."""

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


def register(router: APIRouter) -> None:
    @router.get("/app/return/{provider}", include_in_schema=False)
    def return_page(provider: str) -> HTMLResponse:  # the query (attempt, code) is never read or logged
        return HTMLResponse(PAGE, headers=HEADERS)
