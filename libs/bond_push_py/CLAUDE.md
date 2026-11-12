# bond_push_py
Role: Apple push delivery (iOS only; no FCM sender). `tests/test_schema.py` pins the table.
State: implemented; real delivery is proven only by the opt-in live test / `send_test` (needs an Apple key and a device token).

## Key files
- `models.py` `PushDevicesMixin` + `PUSH_DEVICE_COLUMNS`; `messages.py` `PushMessage`, `PushResult`
- `protocols.py` `PushSender`; `senders.py` Null and Mock; `apns.py` `ApnsSender` (ES256 token cache, mock-transport tests)
- `devices.py` register/unregister/devices_for; `notifier.py` `PushNotifier`
- `send_test.py` `python -m` live check (BOND_PUSH_* variables); `tests/test_live_apns.py` opt-in, skipped by default
- `sync_routes.py` `DeviceRoute`, `device_routes`, `verdict_for`; `errors.py` coded `PushError`

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_x.py`
- `make lint`

## Rules
- No imports from sibling bond_* libs; a notice is read by attribute. No network in tests (mock transport).
- `apns.py` must not import `h2` itself; the client is built lazily. Never log tokens or keys.
- Service functions take a session, flush, never commit. 300-line soft cap. No secrets or emails.
- Tests generate their ES256 key in code; never commit a key file.
