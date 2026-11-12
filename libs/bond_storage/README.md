# bond_storage

S3-compatible object storage, recipient download links and image helpers. Depends on `boto3`, `pillow`, `fastapi` and
`sqlalchemy`. It imports no sibling lib.

## Pieces

| Piece | What it is |
| --- | --- |
| `StorageService` | ABC: `upload`, `download`, `get_url`, `delete`; concrete `list_keys`, `supports_presigned`, `upload_bytes`, `download_bytes` (missing -> `FileNotFoundError`), `exists` |
| `LocalStorageService(base_dir)` | disk backend, traversal guard, URLs are `/uploads/<key>`, `list_keys` implemented |
| `S3StorageService(bucket, region=, endpoint_url=, addressing_style=)` | boto3 s3v4, presigned `get_object` with disposition and type, paginated `list_keys`, clients cached by (region, endpoint, style) |
| `StorageSettings.from_env(bucket_env=, prefix=)`, `build_storage` | settings from the environment, backend factory |
| `company_key(company_id, *parts, private=False)` | `c/<company>/[private/]a/b` |
| `GrantsMixin`, `mint`, `resolve`, `claim`, `revoke...` | opaque-token download links, only the sha256 stored |
| `make_download_router(...)` | `GET /d/{token}`, one identical 410 for every failure. Options: `delivery="redirect"` (302 to a signed URL for `presign_seconds`), `on_claim`, `gone_body`, `enabled`, `client_ip`, `enforce_cap` |
| `images` | `sniff`, `image_from_bytes`, `guard_bomb`, `strip_metadata`, `thumbnail`, `exif_transpose`, `encode` |

## Environment

A name is read as `<prefix><NAME>` first, then `<NAME>`. The bucket variable is named by the app and has no default.

| Variable | Meaning | Default |
| --- | --- | --- |
| `STORAGE_BACKEND` | `local` or `s3` | `local` |
| your bucket variable | bucket name, required for `s3` | none |
| `S3_REGION`, then `AWS_REGION` | region | `us-east-1` |
| `S3_ENDPOINT_URL`, then `AWS_ENDPOINT_URL_S3` | custom endpoint (Railway Buckets, R2, MinIO) | AWS |
| `S3_ADDRESSING_STYLE` | `virtual` or `path` (anything else is `virtual`) | `virtual` |
| `S3_CONNECT_TIMEOUT`, `S3_READ_TIMEOUT`, `S3_MAX_ATTEMPTS` | seconds, seconds, retries | 5, 60, 3 |
| `UPLOADS_DIR` | local backend directory | `uploads` |

Pass the bucket variable your app already uses, each app its own:
`StorageSettings.from_env(bucket_env="MYAPP_S3_BUCKET")`. The per-app names (and the migration steps) belong in
`docs/migration/bond_storage.md`. Set the addressing style explicitly when an endpoint is set: with a custom endpoint
most providers want `path`.

## Grants

```python
class DownloadGrant(GrantsMixin, Base):  # table download_grants; the app migrates it
    __table_args__ = (sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),)

grant, raw = mint(session, document, grant_model=DownloadGrant, user_id=user.id)   # send raw to the recipient, once
app.include_router(make_download_router(storage=storage, grant_model=DownloadGrant,
                                        document_loader=lambda s, i: s.get(Document, i),
                                        session_factory=factory, rate_limit=my_limit))
```

- `document` needs `id`, `storage_key`, `filename`, `content_type`, `kind` (`DocumentLike`).
- `resolve` raises one `GrantUnavailable` for an empty, unknown, over-128-character, revoked, expired or used-up token
  and for a missing document. `claim` is a single guarded UPDATE, so a single-use link cannot be won twice.
- The route answers a missing object 410, other storage errors 503 text. `rate_limit(token_hash, ip)` returns False to
  answer 429. Only pictures and PDFs open inline; everything else, and `attachment_kinds`, downloads.
- Times are naive UTC; every function takes `now=` for tests.

## Images

`image_from_bytes(data, max_pixels=40_000_000)` refuses a bomb from the header size before decoding.
`strip_metadata` applies the EXIF orientation, then copies the pixels, so no EXIF, ICC, XMP or text chunk survives.
HEIC works only when `pillow-heif` is installed.

## Notes

- Libs ship no migrations: assert the mixin against your engine with `bond_service_kit.schema_contract`.
- Keys under `private/` are never served by the local uploads mount; recipient access goes through grants.
