"""S3-compatible backend (AWS S3, Railway Buckets, R2, MinIO)."""

import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .service import StorageService, attachment_disposition

_CLIENTS: dict[tuple[str, str | None, str], Any] = {}
_CLIENT_LOCK = threading.Lock()
# NoSuchBucket is deliberately absent: a wrong or deleted bucket is a storage fault, not a missing file.
_MISSING_CODES = ("NoSuchKey", "404", "NotFound")


def _client(region: str, endpoint_url: str | None, addressing_style: str, connect_timeout: int, read_timeout: int,
            max_attempts: int) -> Any:
    """A cached boto3 client keyed by ``(region, endpoint, style)``.

    Timeouts and retries are set here and nowhere else: a shared client with botocore's 60 s defaults lets one wedged call
    hold a request thread far longer than any caller expects. The first caller for a key fixes its timeouts.
    """
    key = (region, endpoint_url, addressing_style)
    client = _CLIENTS.get(key)
    if client is not None:
        return client
    with _CLIENT_LOCK:  # boto3.client() off the default session is not safe to call concurrently
        client = _CLIENTS.get(key)
        if client is None:
            import boto3
            from botocore.config import Config

            client = boto3.client(
                "s3", region_name=region, endpoint_url=endpoint_url,
                config=Config(signature_version="s3v4", s3={"addressing_style": addressing_style},
                              connect_timeout=connect_timeout, read_timeout=read_timeout,
                              retries={"max_attempts": max_attempts, "mode": "standard"}),
            )
            _CLIENTS[key] = client
    return client


def reset_clients() -> None:
    """Drop cached clients (tests that change the environment)."""
    with _CLIENT_LOCK:
        _CLIENTS.clear()


class S3StorageService(StorageService):
    def __init__(self, bucket: str, *, region: str, endpoint_url: str | None = None,
                 addressing_style: str = "virtual", connect_timeout: int = 5, read_timeout: int = 60,
                 max_attempts: int = 3, client: Any = None) -> None:
        if addressing_style not in ("virtual", "path"):
            raise ValueError("addressing_style must be 'virtual' or 'path'")
        self.bucket = bucket
        self.s3 = client or _client(region, endpoint_url, addressing_style, connect_timeout, read_timeout, max_attempts)

    @property
    def supports_presigned(self) -> bool:
        return True

    @staticmethod
    def _is_missing(exc: Exception) -> bool:
        """True when botocore says "no such object", not "outage"."""
        return getattr(exc, "response", {}).get("Error", {}).get("Code") in _MISSING_CODES

    def upload(self, local_path: Path, key: str) -> str:
        self.s3.upload_file(str(local_path), self.bucket, key)
        return key

    def download(self, key: str, local_path: Path) -> Path:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.s3.download_file(self.bucket, key, str(local_path))
        except Exception as exc:
            if self._is_missing(exc):
                raise FileNotFoundError(key) from exc
            raise
        return local_path

    def get_url(self, key: str, expires_in: int = 3600, *, download_filename: str | None = None,
                content_type: str | None = None) -> str:
        params: dict[str, str] = {"Bucket": self.bucket, "Key": key}
        if download_filename:
            params["ResponseContentDisposition"] = attachment_disposition(download_filename)
        if content_type:
            params["ResponseContentType"] = content_type
        return self.s3.generate_presigned_url("get_object", Params=params, ExpiresIn=expires_in)

    def delete(self, key: str) -> None:
        self.s3.delete_object(Bucket=self.bucket, Key=key)

    def list_keys(self, prefix: str) -> list[tuple[str, datetime]]:
        out: list[tuple[str, datetime]] = []
        for page in self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                modified = obj["LastModified"]
                if modified.tzinfo is None:
                    modified = modified.replace(tzinfo=UTC)
                out.append((obj["Key"], modified.astimezone(UTC)))
        return out

    def upload_bytes(self, content: bytes, key: str, *, content_type: str | None = None) -> str:
        # put_object, not upload_file: managed transfer switches to multipart above 8 MB, and service credentials may
        # lack s3:AbortMultipartUpload.
        extra = {"ContentType": content_type} if content_type else {}
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=content, **extra)
        return key

    def exists(self, key: str) -> bool:
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:
            if self._is_missing(exc):
                return False
            raise

    def download_bytes(self, key: str) -> bytes:
        try:
            return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except Exception as exc:
            if self._is_missing(exc):
                raise FileNotFoundError(key) from exc
            raise
