"""Static mounts: the built web app (SPA fallback) and the local uploads directory (never ``private/``)."""

import logging
import os
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

LOGGER = logging.getLogger(__name__)

#: Paths that belong to the server, never to the web app: a mistyped one keeps its real 404.
RESERVED_PREFIXES = ("api/", "d/", "uploads/")
RESERVED_EXACT = ("health", "docs", "openapi.json", "redoc")

#: Types a browser may render in place from the uploads mount. SVG is absent on purpose: it can carry script.
_INLINE_PREFIXES = ("video/", "audio/")
_INLINE_TYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp", "application/pdf"})


class SpaStaticFiles(StaticFiles):
    """Serves files; an unknown GET/HEAD path falls back to the index. Directories are never listed."""

    def __init__(self, *, directory: str, index: str = "index.html",
                 reserved_prefixes: tuple[str, ...] = RESERVED_PREFIXES,
                 reserved_exact: tuple[str, ...] = RESERVED_EXACT) -> None:
        super().__init__(directory=directory, html=True)
        self.index, self.reserved_prefixes, self.reserved_exact = index, reserved_prefixes, reserved_exact

    def _reserved(self, path: str) -> bool:
        clean = path.lstrip("/")
        return clean in self.reserved_exact or clean.startswith(self.reserved_prefixes)

    async def get_response(self, path: str, scope: Scope):  # type: ignore[no-untyped-def]
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or self._reserved(path) or scope.get("method") not in ("GET", "HEAD"):
                raise
            return await super().get_response(self.index, scope)


def mount_web(app: FastAPI, dir: str | Path, *, index: str = "index.html",
              reserved_prefixes: tuple[str, ...] = RESERVED_PREFIXES) -> bool:
    """Mount the built web app at ``/``; call it LAST so every API route wins. False when ``dir/index`` is missing."""
    directory = Path(dir)
    if not (directory / index).is_file():
        LOGGER.warning("%s has no %s; not serving the web app", directory, index)
        return False
    app.mount("/", SpaStaticFiles(directory=str(directory), index=index, reserved_prefixes=reserved_prefixes), name="web")
    return True


def _attachment(filename: str) -> str:
    safe = (filename or "download").replace('"', "").replace("\\", "").replace("\r", "").replace("\n", "").strip()
    safe = safe or "download"
    ascii_name = safe.encode("ascii", "ignore").decode("ascii") or "download"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(safe, safe='')}"


def _inline_safe(media_type: str) -> bool:
    base = (media_type or "").split(";", 1)[0].strip().lower()
    return base in _INLINE_TYPES or base.startswith(_INLINE_PREFIXES)


class GuardedUploads(StaticFiles):
    """``StaticFiles`` that refuses a private prefix (the same 404 as a missing file) and serves only media inline."""

    def __init__(self, *, directory: str, private_prefix: str = "private/") -> None:
        super().__init__(directory=directory)
        self.private = private_prefix.strip("/").casefold()

    def _blocked(self, path: str) -> bool:
        # Case-insensitive: macOS and Windows resolve ``Private/x`` to the same file a case-sensitive check would allow.
        normalized = path.replace(os.sep, "/").strip("/").casefold()
        return bool(self.private) and (normalized == self.private or normalized.startswith(self.private + "/"))

    async def get_response(self, path: str, scope: Scope):  # type: ignore[no-untyped-def]
        if self._blocked(path):
            LOGGER.warning("Refused an uploads request for a private key: %s", path)
            raise StarletteHTTPException(status_code=404)
        response = await super().get_response(path, scope)
        if response.status_code == 200 and not _inline_safe(response.headers.get("content-type", "")):
            response.headers["content-type"] = "application/octet-stream"
            response.headers["content-disposition"] = _attachment(Path(path).name)
        return response


def mount_uploads(app: FastAPI, dir: str | Path, *, private_prefix: str = "private/") -> bool:
    """Mount ``dir`` at ``/uploads`` for LOCAL development only (the app decides when to call it; never in production
    with a remote bucket). Anything under ``private_prefix`` is never served."""
    directory = Path(dir)
    directory.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", GuardedUploads(directory=str(directory), private_prefix=private_prefix), name="uploads")
    return True
