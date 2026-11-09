"""Storage settings read from the environment, and the factory that builds a backend from them."""

import os
from collections.abc import Mapping
from dataclasses import dataclass

from .local import LocalStorageService
from .s3 import S3StorageService
from .service import StorageService

DEFAULT_REGION = "us-east-1"


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except ValueError:
        return default


@dataclass(frozen=True)
class StorageSettings:
    backend: str = "local"
    bucket: str | None = None
    region: str = DEFAULT_REGION
    endpoint_url: str | None = None
    addressing_style: str = "virtual"
    connect_timeout: int = 5
    read_timeout: int = 60
    max_attempts: int = 3
    local_dir: str = "uploads"

    @classmethod
    def from_env(cls, *, bucket_env: str, prefix: str = "", env: Mapping[str, str] | None = None) -> "StorageSettings":
        """Read the settings. ``bucket_env`` is the app's own bucket variable name.

        Every other name is tried as ``<prefix><NAME>`` first, then plain ``<NAME>``:
        ``STORAGE_BACKEND`` (``local`` | ``s3``), ``S3_REGION`` then ``AWS_REGION`` (default ``us-east-1``),
        ``S3_ENDPOINT_URL`` then ``AWS_ENDPOINT_URL_S3`` (Railway Buckets, R2, MinIO), ``S3_ADDRESSING_STYLE``
        (``virtual`` | ``path``; anything else is ``virtual``), ``S3_CONNECT_TIMEOUT``, ``S3_READ_TIMEOUT``,
        ``S3_MAX_ATTEMPTS`` and ``UPLOADS_DIR`` (local backend).
        """
        source = os.environ if env is None else env

        def get(*names: str) -> str | None:
            for name in names:
                for candidate in ((prefix + name, name) if prefix else (name,)):
                    value = source.get(candidate)
                    if value:
                        return value
            return None

        backend = (get("STORAGE_BACKEND") or "local").strip().lower()
        if backend not in ("local", "s3"):
            raise ValueError(f"STORAGE_BACKEND must be 'local' or 's3', not {backend!r}")
        style = (get("S3_ADDRESSING_STYLE") or "virtual").strip().lower()
        return cls(
            backend=backend,
            bucket=source.get(bucket_env) or None,
            region=get("S3_REGION", "AWS_REGION") or DEFAULT_REGION,
            endpoint_url=get("S3_ENDPOINT_URL", "AWS_ENDPOINT_URL_S3"),
            addressing_style=style if style in ("virtual", "path") else "virtual",
            connect_timeout=_int(get("S3_CONNECT_TIMEOUT"), 5),
            read_timeout=_int(get("S3_READ_TIMEOUT"), 60),
            max_attempts=_int(get("S3_MAX_ATTEMPTS"), 3),
            local_dir=get("UPLOADS_DIR") or "uploads",
        )


def build_storage(settings: StorageSettings) -> StorageService:
    """The backend ``settings`` describe. The s3 backend needs a bucket: there is no default one."""
    if settings.backend == "s3":
        if not settings.bucket:
            raise ValueError("STORAGE_BACKEND=s3 needs a bucket name (the app's bucket environment variable)")
        return S3StorageService(
            settings.bucket, region=settings.region, endpoint_url=settings.endpoint_url,
            addressing_style=settings.addressing_style, connect_timeout=settings.connect_timeout,
            read_timeout=settings.read_timeout, max_attempts=settings.max_attempts)
    return LocalStorageService(settings.local_dir)
