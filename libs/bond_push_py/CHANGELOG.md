# Changelog

## 0.1.0 - unreleased
- `PushDevicesMixin`, `PUSH_DEVICE_COLUMNS`, `PushMessage`, `PushResult`, `PushSender`, `NullSender`,
  `MockSender`, `PushError`, APNs host constants.
- `ApnsSender(key_pem, key_id, team_id, *, client=None, now=None)`: HTTP/2, ES256 provider token cached 50
  minutes, one retry after `ExpiredProviderToken`, status and reason mapping to `PushResult`.
- `register_device` (optional `row_id`), `unregister_device`, `devices_for`.
- `PushNotifier(device_model, sender, *, expires_in=600, category=None, now=utcnow)`; no category by default.
- `device_routes`, `verdict_for`. A sync patch accepts `token`, `platform`, `environment`, `topic`, validated
  like `register_device`.
- Hardening: non-string device input is a coded `PushError` (new `invalid_topic`); `to_naive_utc` applied at every
  entry point; `devices_for(..., platform="ios")` and the notifier send to iOS rows only; `register_device` and the
  sync patch survive concurrent writers (savepoint, one retry, `device_conflict`).
- `ApnsSender`: `close()` and context manager; 408/502/504 and every 403 and a missing `h2` are retryable; 413
  and payloads over 4096 bytes are permanent `payload_too_large`; one forced provider-token refresh per 20 minutes.
- Row-id squatting closed: a sync put for a new row must use `device_row_id(ctx user, device_id)`, else
  `not_device_owner`. `PLATFORMS` is now `("ios",)`; "android" and "web" are `invalid_platform`
  (message "Platform must be ios.").
- `device_row_id(user_id, device_id)`: the default id of a new device row, shared with the phone.
- `PushNotifier.send` returns "retryable" when any device was retryable, even if another accepted.
- `postgres`-marked tests (env `BOND_TEST_POSTGRES_URL`); `psycopg[binary]` in the dev extra.
- New error codes: `token_too_long`, `device_id_too_long`, `topic_too_long`, `device_not_found`,
  `not_device_owner`, `device_conflict`.
