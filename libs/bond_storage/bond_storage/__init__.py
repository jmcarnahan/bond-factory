"""S3-compatible object storage, download grants and image helpers."""

from . import images
from .grants import (
    DEFAULT_MAX_DOWNLOADS,
    DEFAULT_TTL_DAYS,
    MAX_TOKEN_LEN,
    SHARE,
    TOKEN_BYTES,
    VIEW,
    DocumentLike,
    GrantsMixin,
    GrantUnavailable,
    claim,
    has_live_link,
    hash_token,
    mint,
    record_download,
    resolve,
    revoke,
    revoke_for_owner,
)
from .keys import company_key
from .local import LocalStorageService
from .router import make_download_router
from .s3 import S3StorageService, reset_clients
from .service import StorageService, attachment_disposition
from .settings import StorageSettings, build_storage

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_MAX_DOWNLOADS", "DEFAULT_TTL_DAYS", "MAX_TOKEN_LEN", "SHARE", "TOKEN_BYTES", "VIEW", "DocumentLike",
    "GrantUnavailable", "GrantsMixin", "LocalStorageService", "S3StorageService", "StorageService", "StorageSettings",
    "attachment_disposition", "build_storage", "claim", "company_key", "has_live_link", "hash_token", "images",
    "make_download_router", "mint", "record_download", "reset_clients", "resolve", "revoke", "revoke_for_owner",
]
