# Changelog

## 0.1.0 - unreleased
- `StorageService`, `LocalStorageService`, `S3StorageService` (endpoint, addressing style, timeouts, client cache), `attachment_disposition`.
- `StorageSettings.from_env`, `build_storage`, `company_key`.
- `GrantsMixin`, `mint`, `resolve`, `claim`, `record_download`, `has_live_link`, `revoke_for_owner`, `revoke`, `make_download_router`.
- `images`: `sniff`, `image_from_bytes`, `guard_bomb`, `strip_metadata`, `exif_transpose`, `thumbnail`, `encode`.
- Dependencies added: `fastapi`, `sqlalchemy`.
