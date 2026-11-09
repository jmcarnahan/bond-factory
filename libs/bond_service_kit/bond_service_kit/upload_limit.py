"""Refuse an oversized request BEFORE the route reads it."""

import json
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send


class UploadLimit:
    """Pure-ASGI size cap: 413 ``too_large`` when ``Content-Length`` is over ``max_bytes``.

    A body with no length header (chunked) is counted as it streams and refused at the cap, then replayed to the app.
    ``paths`` limits the cap to those path prefixes (default: every path); ``methods`` are the methods checked.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int, paths: tuple[str, ...] | None = None,
                 methods: tuple[str, ...] = ("POST", "PUT", "PATCH")) -> None:
        self.app, self.max_bytes, self.paths, self.methods = app, max_bytes, paths, methods

    def _applies(self, scope: Scope) -> bool:
        if scope["type"] != "http" or scope["method"] not in self.methods:
            return False
        return self.paths is None or scope["path"].startswith(self.paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._applies(scope):
            return await self.app(scope, receive, send)
        length = dict(scope.get("headers") or []).get(b"content-length")
        if length is not None and length.isdigit():
            if int(length) > self.max_bytes:
                return await self._refuse(send)
            return await self.app(scope, receive, send)
        await self._buffered(scope, receive, send)

    async def _refuse(self, send: Send) -> None:
        text = f"Request too large (max {self.max_bytes} bytes)"
        body = json.dumps({"detail": {"code": "too_large", "message": text}}).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    async def _buffered(self, scope: Scope, receive: Receive, send: Send) -> None:
        chunks: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            part = message.get("body", b"")
            total += len(part)
            if total > self.max_bytes:
                return await self._refuse(send)
            chunks.append(part)
            if not message.get("more_body", False):
                break
        replay: dict[str, Any] | None = {"type": "http.request", "body": b"".join(chunks), "more_body": False}

        async def replaying_receive() -> Any:
            nonlocal replay
            if replay is not None:
                message, replay = replay, None
                return message
            return await receive()

        await self.app(scope, replaying_receive, send)
