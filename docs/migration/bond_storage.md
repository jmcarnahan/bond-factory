# Migrating to bond_storage

Object storage, download grants and image helpers (`libs/bond_storage`). Needs `boto3`, `pillow`, `fastapi` and `sqlalchemy`;
no sibling lib. Legend: `docs/migration/README.md`.

## 1. What it replaces

Paths: A `backend/avalon/`, P `backend/pagatime/`, S `sbelcrm/`.

| App | Goes away or shrinks | Stays app-side |
|---|---|---|
| A | `services/storage.py` 369, `rest/routers/downloads.py` 82, `DownloadGrantRecord` (`db/models.py:760`) becomes a mixin class, `services/grants.py` 137 becomes 15 lines of wrappers, image helpers in `services/photos.py` 373 (`sniff`, `_open`, `_jpeg`, `make_thumb`, ~110 lines); `tests/test_uploads_storage.py` 81 | photo access rules, `add_photo`, keys, `document_loader` |
| P | `services/storage.py` 350 (`company_key` :40), `services/grants.py` 138, `rest/routers/downloads.py` 82, `_clean` (`services/photos.py:84`) | `services/export_grants.py` 130 (its discard becomes an `after_download` hook), photo rules |
| S | `services/video/storage_service.py` 363; `tests/test_storage_service_presign.py` 163 moves to the lib | video keys; S has no grants |

## 2. The adapter

A `services/storage.py` shrinks to this, so the 19 files that import `get_storage_service` are untouched (P: 14 with `PT_`,
S: 17 uses with `VIDEO_S3_BUCKET`). It restores A's old defaults, which differ from the lib's:

```python
import os
from dataclasses import replace
from bond_storage import StorageService, StorageSettings, build_storage, reset_clients

def get_storage_service(backend: str | None = None) -> StorageService:
    s = StorageSettings.from_env(bucket_env="AVALON_S3_BUCKET", prefix="AVALON_")  # tries AVALON_S3_REGION, then S3_REGION
    if backend:
        s = replace(s, backend=backend)
    if s.endpoint_url and not (os.getenv("AVALON_S3_ADDRESSING_STYLE") or os.getenv("S3_ADDRESSING_STYLE")):
        s = replace(s, addressing_style="path")  # A used path style whenever an endpoint was set
    if not any(os.getenv(n) for n in ("AVALON_S3_REGION", "S3_REGION", "AWS_REGION")):
        s = replace(s, region="us-west-1")  # the lib defaults to us-east-1
    s = replace(s, local_dir=str(Config.config().uploads_dir()))  # the lib's default is cwd-relative "uploads"; A's is absolute
    return build_storage(replace(s, bucket=s.bucket or "avalon-crm-files"))  # the lib has no default bucket
```

The grant table and wrappers (`models.py`, `services/grants.py`). Mixin columns are SQLAlchemy 2 style; a classic `declarative_base()` works:

```python
from functools import partial
from bond_storage import GrantsMixin, has_live_link as _live, mint as _mint, resolve as _resolve, revoke_for_owner as _revoke
from sqlalchemy import ForeignKeyConstraint

class DownloadGrantRecord(GrantsMixin, Base):  # table name `download_grants` comes from the mixin
    __table_args__ = (ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
                      ForeignKeyConstraint(["created_by"], ["users.id"]))

mint = partial(_mint, grant_model=DownloadGrantRecord)  # claim, revoke and record_download keep their signatures
has_live_link = partial(_live, grant_model=DownloadGrantRecord)
revoke_for_owner = partial(_revoke, grant_model=DownloadGrantRecord)  # `purpose` is keyword-only now
resolve = partial(_resolve, grant_model=DownloadGrantRecord, document_loader=load_document)
```

The route (`rest/routers/downloads.py` becomes): `router = make_download_router(storage=get_storage_service(),
grant_model=DownloadGrantRecord, document_loader=load_document, session_factory=<callable returning a Session>,
rate_limit=allow_hit)`. `allow_hit(token_hash, ip) -> bool`, `attachment_kinds` and `after_download` are optional.

Optional route seams (all default to the behaviour above):

- `delivery="redirect"`, `presign_seconds=60`: the route checks the object exists, signs the URL, claims, then answers 302. A signing fault answers 503 and does not burn a single-use link.
  Use it when links should hand the bytes to the storage service. The local backend cannot presign, so it streams.
  Do not combine it with `after_download` (the bytes never reach the process; construction raises `ValueError`): do the
  work in `on_claim` instead. The stream path still loads the whole object, because no backend offers a chunked read.
- `on_claim(session, grant, ip)`: runs in the claim's transaction. Write an audit row there. If it raises, the claim rolls back and
  the request fails (an unhandled error, not the 410).
- `mint(..., extra={"my_column": value})` sets the app's own columns. A key naming a lib column raises `ValueError`.
- `resolve(..., enforce_cap=False)` and `claim(..., enforce_cap=False)` ignore `max_downloads`; the router takes
  `enforce_cap=False` too.
- `gone_body` (HTML string, or a callable taking the request; it must not vary by failure reason), `enabled` (callable,
  checked per request; false answers 404), `client_ip` (callable taking the request).

## 3. Call-site changes

| Old | New | Find |
|---|---|---|
| `get_storage_service(...)` | unchanged through the adapter | |
| `reset_storage_clients()` (A 4 lines) | `reset_clients()` | `grep -rn reset_storage_clients` |
| `LocalStorageService()` (no argument) | `LocalStorageService(config.uploads_dir())` | `grep -rn "LocalStorageService("` |
| `grants.mint/resolve/revoke_for_owner/has_live_link` (A 21) | unchanged through the partials; `revoke_for_owner(..., purpose=x)` by keyword | `grep -rn "grants\."` |
| `photos.sniff`, `_open(data, kind)`, `make_thumb(img)` | `images.sniff`, `images.image_from_bytes(data)`, `images.encode(images.thumbnail(img, 400))` | `grep -rn "photos\.\(sniff\|make_thumb\)"` |
| `TooLarge`, `UnsupportedMedia` | `images.ImageTooLarge`, `images.UnreadableImage` | |
| P `_clean(img)` | `images.strip_metadata(img)` | |
| P `company_key(...)` (8) | same name, stricter: `.`, `..` and slashes in `company_id` raise `ValueError` | |

## 4. Data

- Env: A `AVALON_S3_BUCKET`, `AVALON_S3_REGION`, `AVALON_S3_ENDPOINT_URL`, `AVALON_UPLOADS_DIR`; P the same with `PT_`; S plain
  `S3_REGION`, `S3_ENDPOINT_URL`, `S3_ADDRESSING_STYLE` and `VIDEO_S3_BUCKET`. All keep their names.
  Set `S3_ADDRESSING_STYLE` explicitly where an endpoint is used, so the adapter's rule can go.
  New inputs for A and P: the lib also reads plain `S3_ENDPOINT_URL` and `AWS_ENDPOINT_URL_S3`, which they never read.
- Table: A and P already have `download_grants` with the same 15 columns (read from both models; compare with `libs/bond_storage/tests/test_schema.py`). The mixin differs in string lengths, and
  `created_at`/`updated_at` are NOT NULL (A and P: nullable). Override those two columns in the subclass
  (`Column(DateTime, default=func.now())`) and no Alembic revision is needed; otherwise backfill NULLs first. P's default
  `purpose` was `view`; the mixin's is `share`: pass it. S creates nothing.

## 5. Acceptance

- `schema_contract(Base.metadata, tables=["download_grants"]).assert_matches(engine)` (from `bond_service_kit`, which the app adds to its test dependencies) on the migrated engine.
- A `backend/tests/test_uploads_storage.py`, S `tests/test_storage_service_presign.py` (repo root, not under `sbelcrm/`), P's grant and photo tests under `backend/tests/`; then `ruff check`.
- `GET /d/<bad token>` answers 410 `text/html` with the same bytes for unknown, expired, revoked and exhausted links.

## 6. Known gaps

- Not lifted: the `Config` singleton, brand names, the photo service beyond image helpers, `export_grants.discard`
  (use `after_download`), S3 reads at client-build time (now `StorageSettings`).
- The S3 client cache is keyed by region, endpoint and style; timeouts are fixed when a client is first built.
- `mint` and `claim` use naive UTC and accept `now=`; `claim` commits (unless `commit=False`) and refreshes the grant.
