# bond_calendar
Role: calendar provider clients (Microsoft Graph, Google) behind one protocol, plus an in-memory fake. Stores nothing.

## Key files
- `protocol.py` the contract; `models.py` event, draft, page, patch; `errors.py` typed failures
- `graph.py`, `google.py` providers; `normalize.py` payload to event; `times.py` UTC helpers; `transport.py` HTTP + error map
- `fake.py` `FakeCalendarProvider` (etag `W/"n"`, `fail_next`, `events`, `calls`)

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_graph.py`
- `make lint`

## Rules
- Imports only httpx and the standard library (tests/test_fake.py checks it). No sibling bond_* imports.
- UTC end-to-end: aware datetimes, all-day at midnight UTC. No network in tests (httpx.MockTransport).
- 300-line soft cap per source file. No secrets, emails or customer data (only *@example.com).
