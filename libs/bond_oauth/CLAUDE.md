# bond_oauth
Role: OAuth2 flows (Google, Microsoft, fake) and encrypted token storage. Contract: the README.

## Key files
- `service.py` start/complete/status/disconnect/access_token; `state.py` + `pkce.py` + `cipher.py`
- `google.py`, `microsoft.py`, `fake.py` providers behind `providers.py`; `models.py` mixin; `scopes.py`

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_x.py`
- `make lint`

## Rules
- Imports only httpx, cryptography, sqlalchemy and the standard library (tests/test_scopes_fake_boundary.py).
- No imports from sibling bond_* libs. No network in tests (httpx.MockTransport).
- State expiry uses the real clock. 300-line soft cap per source file. No secrets, emails or customer data.
