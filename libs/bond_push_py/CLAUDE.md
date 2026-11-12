# bond_push_py
Role: Apple push delivery (iOS only; no FCM sender). `tests/test_schema.py` pins the table.
State: scaffold. Mixin, messages, `NullSender`, `MockSender`, errors are real; `ApnsSender`, devices, notifier, routes are stubs.

## Key files
- `models.py` `PushDevicesMixin` + `PUSH_DEVICE_COLUMNS`; `messages.py` `PushMessage`, `PushResult`
- `protocols.py` `PushSender`; `senders.py` Null and Mock; `apns.py` `ApnsSender` (stub, hosts constants)
- `devices.py` register/unregister/devices_for (stubs); `notifier.py` `PushNotifier` (stub)
- `sync_routes.py` `DeviceRoute`, `device_routes` (stub)

## Commands
- `make setup-py` at the repo root, once (workspace venv)
- `make test T=tests/test_x.py`
- `make lint`

## Rules
- No imports from sibling bond_* libs; a notice is read by attribute. No network in tests (mock transport).
- `apns.py` must not import `h2` itself; build the HTTP client lazily. Never log tokens or keys.
- Service functions take a session, flush, never commit. 300-line soft cap. No secrets or emails.
