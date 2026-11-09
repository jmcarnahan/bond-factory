# bond_signin
Role: direct Google/Microsoft sign-in. Protocol seams, scope policy, fixed check order, router factory.

## Key files
- `protocols.py` structural Protocols the app and the sibling libs satisfy (IdentityFlow, HandoffStore, SessionIssuer, UserDirectory)
- `order.py` the fixed refusal order; `policy.py` ScopePolicy and `normalize_email`
- `routes_web.py`, `routes_native.py`, `routes_session.py`, `routes_providers.py` router parts (`router.py` is the factory); `_callback.py` shared callback core
- `finish.py` `finish_session`/`CookiePolicy`; `origin.py` Origin rule; `settings.py`; `errors.py` code table; `return_page.py`
- The AASA and assetlinks router lives in bond_service_kit (`well_known.py`), not here.

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_x.py`
- `make lint`

## Rules
- Imports fastapi (with starlette) and the standard library only.
- No imports of any sibling bond_* lib (tool/boundary_gate.sh); seams are Protocols, errors are matched by a `code` attribute.
- No network in tests. No secrets, emails or customer data.
- Public API change: update `__init__.py` and CHANGELOG.md together. 300-line soft cap per source file.
