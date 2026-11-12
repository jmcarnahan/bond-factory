# bond_push_py

Apple push delivery for the task checklist: a device table, a sender seam, an APNs sender over HTTP/2, a
notifier the sweep calls after commit, and sync routes so a phone registers its own device. iOS only; there is no
FCM sender (the `PushSender` Protocol leaves room for one). Version 0.1.0.

## What the app needs from Apple

- A push key: a `.p8` file (an Apple developer account, Keys, Apple Push Notifications service). Keep its text in
  your secret store, never in the repo.
- The key id (10 characters) and the team id (10 characters).
- The bundle id, which is the `topic` of every device row (`apns-topic`).
- The Push Notifications capability (entitlement) on the iOS app.
- Sandbox and production tokens are different: a debug build gets a sandbox token, a TestFlight or App Store
  build a production token, and each works only on its own Apple host. The device row stores `environment`, and
  `ApnsSender` picks `APNS_HOST_SANDBOX` or `APNS_HOST_PRODUCTION` per message. The app passes the environment
  from its build configuration.

## Table

`PushDevicesMixin` is `push_devices`: `id`, `user_id`, `device_id` (unique with `user_id`), `token` (unique),
`platform`, `environment`, `topic`, `last_seen_at`, `disabled_at`, `created_at`. No migration ships;
`PUSH_DEVICE_COLUMNS` is pinned by a test.

## Calls

- `register_device(session, Device, user_id=, device_id=, token=, platform=, environment=, topic=, now=)`:
  idempotent per (user, device); a token held by another row moves to this one. Bad input raises a coded
  `PushError` (`invalid_platform`, `invalid_environment`, `token_required`, `device_id_required`, ...).
  Non-text input is refused the same way. Two writers racing on one device or token are safe (a savepoint and one
  re-read; a persistent clash is `device_conflict`, never an `IntegrityError`). `now` may be aware; it is stored
  as naive UTC. `unregister_device(...) -> bool`, `devices_for(session, Device, user_id, platform="ios")` (live
  rows; `platform=None` for all). `PLATFORMS` is `("ios",)`: only APNs can deliver here, so registering "android"
  or "web" is `invalid_platform` (the column stays a plain string; an old row with another value is skipped).
- `ApnsSender(key_pem, key_id, team_id)`: `send(messages) -> list[PushResult]`. The ES256 provider token is cached
  50 minutes, and a forced refresh (after `ExpiredProviderToken`) happens at most once per 20 minutes. 410,
  `BadDeviceToken`, `DeviceTokenNotForTopic` and `Unregistered` give `unregistered`. Retryable: 408, 429, 500,
  502, 503, 504, network errors, a missing `h2`, and every 403 (a wrong key or key id is a deployment mistake, so
  notices retry until the sweep's attempt limit while the operator fixes it). 413 and a payload over 4096 bytes
  (never sent) are permanent `payload_too_large`. Never raises for one message; 10 s timeout. Use one sender per
  process and `close()` it (or use `with`) at shutdown; a client you pass in is yours to close. `NullSender` and
  `MockSender` need no network.
- `PushNotifier(Device, sender, *, expires_in=600, category=None)`: `send(session, notice)` returns "ok",
  "retryable", "unregistered" or "failed". It sends to every live device of `notice.user_id`, with the notice id
  as Apple's collapse id, disables tokens Apple reports dead, and reads the notice by attribute only. "retryable"
  wins when any device was retryable: the sweep sends the notice again to all devices and the collapse id makes
  the repeat replace the first on a device that already has it. "ok" means no device was retryable and at least
  one accepted, or there is no live device: by design, a device registered a minute later does not receive that
  notice. Only "ios" rows are sent to; an old row of another platform is skipped and left alone. It sends no Apple `category` unless given, because the phone plugin cannot say which
  action button of a remote notification was pressed; a tap opens the task.

## Plugging into the task sweep

The notifier satisfies the tasks lib's `Notifier` by shape. List it as an outbox channel only when a real sender
is configured (with `NullSender` every send is "failed"):

```python
sender = ApnsSender(key_pem, key_id, team_id)
notifiers = {"push": PushNotifier(PushDevice, sender)}  # passed to deliver_pending(..., notifiers=notifiers)
```

## Registering a device

- Synced table: `device_routes(PushDevice)` returns `{("push_devices", None): DeviceRoute}` (put, patch,
  delete). The device writes only its own row; `user_id` comes from the session, never the client. A patch may
  change `token`, `platform`, `environment` and `topic` (a debug build becoming a release build), validated as
  `register_device` does; `last_seen_at` is the server's clock. Every row id is
  `device_row_id(user_id, device_id)` = `"d_"` + the first 32 hex of `sha256("<user_id>|<device_id>")`, on REST
  and on the phone alike. A sync put (or patch) whose row id is not the caller's own `device_row_id` is refused
  `not_device_owner`, so nobody can squat another user's row id. If a user has an older row for that device under a random id (made before this
  formula), a put updates that row and it keeps its id. Wrap the route
  for your sync lib and map errors with `verdict_for(exc)`.
- REST: call `register_device` and `unregister_device` from your own routes (`POST /push/devices`,
  `DELETE /push/devices/{device_id}`); `PushError.status` and `.code` give the response.

## Not testable here

Tests use `httpx.MockTransport` and a key generated in the test. Real delivery needs an Apple key and a device;
nothing here proves Apple accepts the requests.

## Boundary

No other bond lib is imported. Tokens and keys are never logged or put in an error string. `h2` is loaded only
when the first real request is made.
