# Migrating to bond_push_py

Apple push delivery (`libs/bond_push_py`: SQLAlchemy, httpx with HTTP/2, PyJWT, cryptography): a device table, a sender
seam, an APNs sender, a notifier the sweep calls after commit, and sync routes so a phone registers itself. iOS only.
There is no Firebase and no second sender (`PushSender` leaves room for one). Wire: `docs/contracts/notices.md`.
Dart side: `bond_push.md`. Legend: `docs/migration/README.md`.

## 1. What it replaces

Apps that sent push through Firebase Cloud Messaging for Apple devices can drop that path for task notices. Keep
Firebase where it still serves something else. The lib does not read or write an FCM token. Existing device tables
stay: map the app's rows to `PushDevicesMixin` by a view or a one-time copy.

## 2. What the Apple side needs

- A push key (a `.p8` file) from the developer account. Keep its text in the secret store, never in the repo.
- The key id (10 characters), the team id (10 characters) and the bundle id, which is the `topic` of every device row.
- The Push Notifications capability on the iOS app target.
- Sandbox and production tokens are different. A debug build gets a sandbox token, a TestFlight or store build a
  production one. The row stores `environment` and the sender picks `APNS_HOST_SANDBOX` or `APNS_HOST_PRODUCTION`.

## 3. What the app adds

- Platform is `ios` only (`android` and `web` are `invalid_platform`). A table: `class PushDevice(PushDevicesMixin, Base): ...` in the SAME database as `tasks`, and a revision. Assert
  `PUSH_DEVICE_COLUMNS`. Unique on `(user_id, device_id)` and on `token`.
- Device routes, either REST or sync:

```python
register_device(session, PushDevice, user_id=uid, device_id=body.device_id, token=body.token,
                platform=body.platform, environment=body.environment, topic=body.topic, now=now)  # POST /push/devices
unregister_device(session, PushDevice, user_id=uid, device_id=device_id)                          # DELETE, True if found
```

  `PushError` carries `code`,
  `message` and `status` (`invalid_platform`, `invalid_environment`, `token_required`, `device_id_required`,
  `device_conflict` 409, ...). Map it to your error body.
- Sync: `device_routes(PushDevice)` returns `{("push_devices", None): DeviceRoute}` (put, patch, delete). The device
  writes only its own row and `user_id` comes from the session. A put with any other id is `not_device_owner`. The row id is `device_row_id(user_id, device_id)`, which
  is `"d_"` + the first 32 hex of `sha256("<user_id>|<device_id>")`, the same value the phone computes.
- The sender and notifier, built once per process and closed at shutdown:

```python
sender = ApnsSender(key_pem, key_id, team_id)             # or MockSender() in tests
push = PushNotifier(PushDevice, sender)                   # category=None: no Apple action buttons
sweep_due(..., channels=["push"]); deliver_pending(..., notifiers={"push": push}, ...)
```

  List the `"push"` channel only when a real sender is configured. With `NullSender` every send is "failed".

## 4. Smallest working example

Register a device, claim a due notice with `channels=["push"]`, deliver with `MockSender`: the sender holds one
`PushMessage` with `collapse_id` equal to the notice id and `data` `{notice_id, task_id, route}`. The same task swept
again sends nothing new.

## 5. What to know

- `PushNotifier.send` returns "ok" when at least one device accepted or there is no live device, "retryable" if any
  device answered a retryable error (the sweep sends again, and the collapse id makes the repeat replace the first),
  "unregistered" when every device was dead (they are disabled), else "failed".
- Retryable Apple answers: 408, 429, 500, 502, 503, 504, network errors and every 403 (a wrong key is a deployment
  mistake). `BadDeviceToken`, 410 and `Unregistered` disable the token. A payload over 4096 bytes is never sent.
- No Apple `category` goes out by default. An Apple push has no action buttons. A tap opens the task and the in-app
  banner offers Done, Snooze and Cancel. `PushNotifier(category=...)` can set one, but the phone plugin cannot report which button was pressed, so leave it off.
- Tokens and keys are never logged. A device registered after a notice was sent does not receive it.

## 6. What to test

- `make -C libs/bond_push_py test`. Tests use `httpx.MockTransport` and a key generated in the test.
- Assert `PUSH_DEVICE_COLUMNS`. Round-trip `fixtures/push/device_register.json`.
- Re-register the same device with a new token: one row, the token moved. Two users, one token: the token moves.
- A dead token (`MockSender(fail_tokens={token: PushResult(ok=False, unregistered=True)})`) disables the device and the notice is "unregistered".
- A build moving from sandbox to release changes `environment`. The sender must follow it.

## 6a. Devices over sync (recommended)

The sync path, `device_routes(PushDevice, now=...)` on the server and `SyncPushDevices` on the phone, is the RECOMMENDED
way to register devices when the app already syncs. The REST pair in `services/sdk_example` is an example for apps without
sync. No new REST route is needed: wrap `DeviceRoute` as the dispatcher's `Route`, mount `("push_devices", None)` beside the
task routes, add the table to `tables` and `single_action`, and let `reject_for` try `verdict_for` after the task one
(`services/legacy_host/legacy_host/sync_wiring.py`). The table is new for an app that never had one: the adoption migration
creates it (`legacy_ddl.py` shows the DDL).

- Stream rule (the app's sync service configuration; this repository cannot test it, so check it there): a device's rows go only to their own user, `... FROM push_devices WHERE user_id = auth.user_id()`. Never
  stream another user's row: `token` must not leave the server for anyone but the user whose device it is.
- Server-owned: `user_id` (the session, never the payload), `last_seen_at` (the host clock on every accepted write),
  `disabled_at` (cleared by a write) and `created_at`. A payload that names them is ignored.
- Unregister (a `delete`) removes the row; deleting a row that is gone is still `ok`. A token held by another row moves to the
  new registrant (the old row is deleted), whichever user held it.
- Verdicts, proven by `services/legacy_host/tests/test_push_devices_sync.py` (always a 200 answer, one verdict per op, the
  other ops of the upload still apply):

| code | message | meaning |
|---|---|---|
| `forbidden` | `not_device_owner` | the id is another user's row, or a new row's id is not the caller's own formula id |
| `not_found` | `device_not_found` | a patch of a row that does not exist |
| `invalid` | `invalid_platform`, `invalid_environment`, `token_required`, `token_too_long`, `device_id_required`, `device_id_too_long` | the value failed `register_device`'s checks |
| `invalid` | `invalid` | a non-string `token` or `topic`: the dispatcher's column coercion refuses it before the lib sees it |

- Fixture: `fixtures/legacy_host/upload_push_devices.json` (put, patch of `token`, delete) is what `SyncPushDevices` queues
  (`packages/bond_notify_powersync/test/legacy_upload_test.dart`) and what the legacy host replays.
- Sign-out order: `unregister`, wait for the upload drain, `disconnect`, then clear the local database.

## 7. Not proven

Default tests prove nothing about Apple. To prove a key, team id and app capability before wiring anything, set
`BOND_PUSH_KEY_PATH`, `BOND_PUSH_KEY_ID`, `BOND_PUSH_TEAM_ID`, `BOND_PUSH_TOPIC` and `BOND_PUSH_DEVICE_TOKEN` (a token from a
development build on a phone) and run `python -m bond_push_py.send_test`. It sends one alert to the sandbox host (`--environment production` for the other) and exits 0
only when Apple accepts it. The verdict line names the host used. `BOND_PUSH_NETWORK=1 make -C libs/bond_push_py test T=tests/test_live_apns.py` runs the same
as two checks (accepted, and a made-up token comes back `BadDeviceToken` or `Unregistered`). Use placeholders in any doc or script you commit; never
commit the key, key id, team id or token. See `docs/test/MOBILE.md`.
