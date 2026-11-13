# Changelog

## 0.1.0 - unreleased
- A NULL `download_count` (a legacy table whose count column is nullable) counts as 0: `claim` stored NULL + 1 = NULL and
  never matched, and the cap comparison never matched either, so such a link resolved but could not be claimed. Both now
  use `coalesce(download_count, 0)`; `has_live_link` too. No API change.
- Grant seams, all defaulting to today's behaviour:
  - `make_download_router(delivery="stream"|"redirect", presign_seconds=60)`: redirect mode checks the object exists,
    signs the URL, claims, then answers 302 (a signing fault answers 503 and leaves the download unclaimed). The local backend (no presign) still streams. `after_download` cannot be
    combined with redirect (`ValueError`): the bytes never reach the process.
  - `make_download_router(on_claim=fn(session, grant, ip))`: runs in the claim's transaction; if it raises, the claim
    rolls back and the request fails.
  - `make_download_router(gone_body=str | fn(request), enabled=fn(), client_ip=fn(request), enforce_cap=True)`.
    `enabled()` is checked per request; false answers 404 with the no-store headers. A custom
    `client_ip` result is cut to 45 characters before the rate limiter and `on_claim` see it.
  - `mint(..., extra=Mapping)` sets the app's own columns; a key naming a lib column raises `ValueError`.
  - `resolve(..., enforce_cap=True)` and `claim(..., enforce_cap=True, commit=True)`. `claim(commit=False)` leaves the
    transaction open for the caller.
  - The stream path still reads the whole object (no backend offers a chunked read yet).
- `StorageService`, `LocalStorageService`, `S3StorageService` (endpoint, addressing style, timeouts, client cache), `attachment_disposition`.
- `StorageSettings.from_env`, `build_storage`, `company_key`.
- `GrantsMixin`, `mint`, `resolve`, `claim`, `record_download`, `has_live_link`, `revoke_for_owner`, `revoke`, `make_download_router`.
- `images`: `sniff`, `image_from_bytes`, `guard_bomb`, `strip_metadata`, `exif_transpose`, `thumbnail`, `encode`.
- Dependencies added: `fastapi`, `sqlalchemy`.
