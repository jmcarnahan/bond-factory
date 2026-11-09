"""The storage contract every backend implements."""

import tempfile
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


def attachment_disposition(filename: str) -> str:
    """A ``Content-Disposition: attachment`` value that survives non-ASCII names.

    Emits the bare ``filename=`` (old clients) and the RFC 5987 ``filename*=`` form, and strips quotes and line breaks so a
    hostile stored filename cannot split the header.
    """
    safe = (filename or "download").replace('"', "").replace("\\", "")
    safe = "".join(ch for ch in safe if ord(ch) >= 0x20 and ord(ch) != 0x7F).strip() or "download"
    ascii_fallback = safe.encode("ascii", "ignore").decode("ascii") or "download"
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(safe, safe='')}"


class StorageService(ABC):
    """File storage by key. The byte helpers are concrete so a subclass or test double need only implement the four."""

    @abstractmethod
    def upload(self, local_path: Path, key: str) -> str:
        """Upload a file and return its storage key."""

    @abstractmethod
    def download(self, key: str, local_path: Path) -> Path:
        """Download ``key`` to ``local_path``."""

    @abstractmethod
    def get_url(self, key: str, expires_in: int = 3600, *, download_filename: str | None = None,
                content_type: str | None = None) -> str:
        """A URL for the stored file. ``download_filename`` / ``content_type`` ask the backend to force a download with
        that name and type; a backend that cannot influence response headers ignores them (see ``supports_presigned``)."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete ``key``. A missing key is not an error."""

    def list_keys(self, prefix: str) -> list[tuple[str, datetime]]:
        """``(key, last_modified)`` for every key starting with ``prefix``; times are aware UTC."""
        raise NotImplementedError(f"{type(self).__name__} cannot list keys")

    @property
    def supports_presigned(self) -> bool:
        """True when ``get_url`` is self-authorising and expiring. False means the URL only works for an authenticated
        caller of this app, so anything recipient-facing has to proxy the bytes."""
        return False

    def upload_bytes(self, content: bytes, key: str, *, content_type: str | None = None) -> str:
        """Store ``content`` at ``key`` (default: through a temp file and ``upload``)."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        try:
            return self.upload(tmp_path, key)
        finally:
            tmp_path.unlink(missing_ok=True)

    def download_bytes(self, key: str) -> bytes:
        """Read ``key``. A missing object raises ``FileNotFoundError`` on every backend, so a caller can tell a missing
        file from an outage without knowing the backend."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            self.download(key, tmp_path)
            return tmp_path.read_bytes()
        finally:
            tmp_path.unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        """Is there an object at ``key``? A storage failure propagates: "not there" and "cannot tell" differ."""
        try:
            self.download_bytes(key)
            return True
        except FileNotFoundError:
            return False
