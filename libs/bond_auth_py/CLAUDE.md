# bond_auth_py
Role: Firebase ID token verification, session JWTs, revocation, identity admin, janitor. Contract: docs/contracts/auth.md.

## Key files
- `settings.py` config + mock gate; `verify.py` tiers; `mock.py` mock store; `firebase_app.py` lazy firebase-admin
- `tokens.py` session JWT; `session.py` revocation; `admin.py` + `janitor.py` identity lifecycle
- `errors.py` codes + `AuthRefused`; `providers.py` `/auth/providers` payload; `capabilities.py` policies

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_x.py`
- `make lint`

## Rules
- No imports from sibling bond_* libs; no web framework imports. Apps map `AuthRefused` to their error body.
- `firebase_admin` is imported only inside functions; tests substitute a fake module (see tests/conftest.py).
- No network in tests. 300-line soft cap per source file. No secrets, emails or customer data.
- `iat` and revocation checks use the real clock, never an app's offset clock.
