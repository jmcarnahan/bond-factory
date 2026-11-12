# bond_push_py

Apple push delivery for the task checklist: device table, sender seam, an APNs sender over HTTP/2, and a notifier
the sweep calls after commit. iOS only; there is no FCM sender (the `PushSender` Protocol leaves room for one).
Status: scaffold (0.1.0); stubs raise `NotImplementedError` until they are filled in.

## Table

`PushDevicesMixin` is `push_devices`: `id`, `user_id`, `device_id` (unique with `user_id`), `token` (unique),
`platform`, `environment` ("sandbox" or "production"; not interchangeable), `topic`, `last_seen_at`,
`disabled_at`, `created_at`. No migration ships. `PUSH_DEVICE_COLUMNS` is pinned by a test.

## API

- `PushMessage(token, environment, topic, title, body, collapse_id, data, expires_at, priority, thread_id,
  category)`, `PushResult(ok, unregistered, retryable, error)`: frozen dataclasses.
- `PushSender.send(messages) -> list[PushResult]`. `NullSender` fails each message with `push_not_configured`;
  `MockSender` records `.sent` and can be told to fail. `ApnsSender(key_pem, key_id, team_id, *, client=None)`
  uses `APNS_HOST_PRODUCTION` or `APNS_HOST_SANDBOX` by the message's environment.
- `register_device`, `unregister_device`, `devices_for`: session in, flush, never commit.
- `PushNotifier(device_model, sender, *, expires_in=600).send(session, notice) -> "ok" | "retryable" |
  "unregistered"`; reads the notice by attribute.
- `device_routes(device_model, now=...)`: `{("push_devices", None): DeviceRoute}`; the server sets `user_id`.

## Boundary

No other bond lib is imported. Tokens and keys are never logged.
