# bond_auth_py
Role: Firebase ID token verification and auth dependencies. Phase 1.

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_x.py`
- `make lint`

## Rules
- No imports from sibling bond_* libs.
- No network in tests.
- 300-line soft cap per source file.
- No secrets, emails or customer data.
