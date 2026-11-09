# bond_signin
Role: direct Google/Microsoft sign-in. Protocol seams, scope policy, fixed check order, router factory.

## Key files (to come, PLAN §3.4 and §3.8)
- `protocols.py` structural Protocols the app and the sibling libs satisfy (IdentityFlow, HandoffStore, SessionIssuer, UserDirectory)
- `order.py` the fixed refusal order; `policy.py` ScopePolicy and `normalize_email`
- `routes_web.py`, `routes_native.py`, `routes_session.py` router factory parts; `finish.py` `finish_session`
- The AASA and assetlinks router lives in bond_service_kit (`well_known.py`), not here.

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_x.py`
- `make lint`

## Rules
- Imports fastapi, pydantic, sqlalchemy and the standard library only.
- No imports of any sibling bond_* lib (tool/boundary_gate.sh); seams are Protocols, errors are matched by a `code` attribute.
- No network in tests. No secrets, emails or customer data.
- Public API change: update `__init__.py` and CHANGELOG.md together. 300-line soft cap per source file.
