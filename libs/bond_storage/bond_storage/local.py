"""Local-disk backend for development and tests."""

import shutil
from datetime import UTC, datetime
from pathlib import Path

from .service import StorageService


class LocalStorageService(StorageService):
    """Files under ``base_dir``. ``get_url`` is ``/uploads/<key>``; keys under ``private/`` must never be served by the
    uploads mount (``bond_service_kit.mount_uploads`` refuses them)."""

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, key: str) -> Path:
        """The absolute path for ``key``, refusing anything that resolves outside ``base_dir``."""
        resolved = (self.base_dir / key).resolve()
        if not resolved.is_relative_to(self.base_dir):
            raise ValueError(f"Storage key {key!r} resolves outside the base directory")
        return resolved

    def upload(self, local_path: Path, key: str) -> str:
        dest = self._safe_path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(local_path), str(dest))
        return key

    def download(self, key: str, local_path: Path) -> Path:
        src = self._safe_path(key)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(local_path))
        return local_path

    def get_url(self, key: str, expires_in: int = 3600, *, download_filename: str | None = None,
                content_type: str | None = None) -> str:
        # A static path cannot carry response headers: callers needing a forced download proxy the bytes.
        self._safe_path(key)
        return f"/uploads/{key}"

    def delete(self, key: str) -> None:
        self._safe_path(key).unlink(missing_ok=True)

    def upload_bytes(self, content: bytes, key: str, *, content_type: str | None = None) -> str:
        dest = self._safe_path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return key

    def download_bytes(self, key: str) -> bytes:
        return self._safe_path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._safe_path(key).is_file()

    def list_keys(self, prefix: str) -> list[tuple[str, datetime]]:
        out: list[tuple[str, datetime]] = []
        for path in self.base_dir.rglob("*"):
            if not path.is_file():
                continue
            key = path.relative_to(self.base_dir).as_posix()
            if key.startswith(prefix):
                out.append((key, datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)))
        return sorted(out)
