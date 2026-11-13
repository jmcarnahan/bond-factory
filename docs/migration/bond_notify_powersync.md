# Migrating to bond_notify_powersync

`NoticeFeed` and `PushDevices` over the synced SQLite store (`packages/bond_notify_powersync`, Flutter: needs `bond_notify`,
`bond_push`, `bond_sync_powersync`, `powersync`). The inbox works offline and registering a device is a local write that the
sync upload carries. Server half: `bond_notify_py.md` and `bond_push_py.md`. Legend: `docs/migration/README.md`.
Order: `todo-checklist.md`.

## 1. What it replaces

The REST feed, for an app that already syncs. `WatchNoticeFeed` takes the place of `PollingNoticeFeed`. `SyncPushDevices` takes
the place of `PushDevicesApi`, so device registration needs no REST route and works offline. The controller, the widgets
and the coordinator do not change.

## 2. What the app adds

- The tables: `Schema([...noticesTables(), ...pushDevicesTables(), ...syncSupportTables()])`.
- The two streams on the sync service:

```sql
SELECT id, user_id, kind, title, body, data, created_at, read_at, dismissed_at
FROM notices WHERE user_id = auth.user_id()

SELECT id, user_id, device_id, token, platform, environment, topic, last_seen_at, disabled_at, created_at
FROM push_devices WHERE user_id = auth.user_id()
```

- The upload routes on the server: `notice_routes(Notice)` and `device_routes(PushDevice)`, each wrapped as the sync lib's
  `Route`. Streams allow no ORDER or LIMIT, so run `prune_notices` regularly to keep the synced set small.
- `data` arrives as JSON text.

## 3. Smallest working example

```dart
final feed = WatchNoticeFeed(db, userId: userId);          // db is a SyncDb
feed.watch();                  // newest first (created_at, id), dismissed hidden
await feed.markRead(id);
await feed.dismiss(id);
await feed.markAllRead();      // one UPDATE of every unread, undismissed row; serverUnreadCount is null (the list is complete)

final devices = SyncPushDevices(db, userId: userId);
await devices.register(token, deviceId: deviceId, topic: bundleId);
await devices.unregister(deviceId);
```

`noticeFromRow(row)` decodes one row. A malformed `data` cell keeps the notice and drops the task fields. `refresh()` does
nothing, because sync keeps the store current. Both classes take an optional `now` for tests.

## 4. What the device writes

- notices: only `read_at` and `dismissed_at`, set to the device's UTC time (ISO with Z) when still null. The server replaces
  it with its own clock on upload.
- push_devices: its own row. The id is `d_` + the first 32 hex characters of `sha256("<userId>|<deviceId>")`
  (`SyncPushDevices.rowId`), which fits the sync id rule `[A-Za-z0-9_-]{1,64}` and equals the server's `device_row_id`.
  The first register inserts (`id`, `user_id`, `device_id`, `token`, `platform`, `environment`, `topic`, `last_seen_at`,
  `created_at`). Later ones update only `token`, `platform`, `environment` and `topic`, so the queued patch holds just what
  changed. `last_seen_at` and `disabled_at` are the server's. Unregister deletes the row. The server takes `user_id` from the
  session, never from the device.

## 5. Sign-out order

`unregister` finishes when the local DELETE is written, not when it is uploaded. Then:

```dart
await devices.unregister(deviceId);
await waitForUploadDrain(db);   // bond_sync_powersync: true when the queue is empty, false on timeout
await db.disconnect();          // then clear the database
```

Clearing first loses the DELETE and leaves the token registered on the server.

## 5a. The server side for an app that already exists

`SyncPushDevices` is the RECOMMENDED way to register a device when the app syncs; the REST pair in the example service is for
apps without sync. The server needs no new route: `device_routes` mounted in the app's upload host. Stream rule (set in the app's sync service; not
testable here): only the user's own device rows (`WHERE user_id = auth.user_id()`), so another user's `token` never reaches a phone. The server owns
`user_id`, `last_seen_at`, `disabled_at` and `created_at`. The verdict table, the fixture and the host wiring are in
`docs/migration/bond_push_py.md` section 6a; `test/legacy_upload_test.dart` proves the phone queues exactly the ops the
legacy host replays.

## 6. What to test

- `make -C packages/bond_notify_powersync test`. Use `FakeSyncDb.tables(..., applySql: true, columns: ...)` from
  `bond_sync_powersync/testing.dart`.
- Mark a notice read offline: the queued write holds only `read_at`. A re-register after a debug-to-release move sends `token`
  and `environment` only.
- A shared check: `SyncPushDevices.rowId` for a user and device equals `device_row_id` in Python for the same pair.
- Not proven here: a real PowerSync service, how fast a new notice reaches an open app, and an upload of the device row.
