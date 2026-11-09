# bond_storage
Role: S3-compatible storage, recipient download grants and Pillow image helpers.

## Key files
- bond_storage/service.py, local.py, s3.py, settings.py, keys.py: backends and settings
- bond_storage/grants.py + router.py: `GrantsMixin`, mint/resolve/claim, `GET /d/{token}`
- bond_storage/images.py: sniff, bomb guard, metadata strip, thumbnail

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_x.py`
- `make lint`

## Rules
- No imports from sibling bond_* libs (the uploads mount and rate limits live in bond_service_kit; the app wires them).
- No app-specific env names, app names or default bucket names; the bucket env var is a parameter.
- The 410 body and its three headers are byte-identical for every failure. Never add a distinguishing branch.
- Only the sha256 of a token is stored. No network in tests; S3 via `botocore.stub.Stubber`.
- 300-line soft cap per source file.
