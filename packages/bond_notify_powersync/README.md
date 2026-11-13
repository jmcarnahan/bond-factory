# bond_notify_powersync

`NoticeFeed` and `PushDevices` over the synced SQLite store (`bond_sync_powersync`): the inbox works offline and
registering a device is a local write that the sync upload carries.

## Add the tables

```dart
final schema = Schema([...noticesTables(), ...pushDevicesTables(), ...syncSupportTables()]);
```

## Stream queries (on the app's sync service)

```sql
SELECT id, user_id, kind, title, body, data, created_at, read_at, dismissed_at
FROM notices WHERE user_id = auth.user_id()

SELECT id, user_id, device_id, platform, environment, topic, last_seen_at, disabled_at, created_at
FROM push_devices WHERE user_id = auth.user_id()
```

`data` is JSON text (`task_id`, `stage`, `seq`, `due_at`, `priority`, `route`, `actions`, `last`). Streams allow
no ORDER or LIMIT, so keep the synced set small with the server's prune job.

## What the device writes

- notices: `read_at` and `dismissed_at` only, set to the device's UTC time (ISO with a Z) when still null. The
  server replaces it with its own clock on upload.
- push_devices: its own row. The id is `d_` + the first 32 hex characters of sha256 of `<userId>|<deviceId>`
  (`SyncPushDevices.rowId`), so it always fits the sync id rule `[A-Za-z0-9_-]{1,64}`. First register is an insert
  (`id`, `user_id`, `device_id`, `token`, `platform`, `environment`, `topic`, `last_seen_at`, `created_at`); later
  ones update only `token`, `platform`, `environment` and `topic`, so the queued patch holds just what changed
  (a debug build to a release build sends `token` and `environment`). `last_seen_at` and `disabled_at` are
  server-owned. Unregister deletes the row. The server takes `user_id` from the session, never from the device.

## Use

```dart
final feed = WatchNoticeFeed(db, userId: userId);   // db is a SyncDb
feed.watch();            // newest first (created_at, id), dismissed hidden
await feed.markRead(id);
await feed.dismiss(id);
await feed.markAllRead(); // one UPDATE of every unread, undismissed row; serverUnreadCount is null (the list is complete)

final devices = SyncPushDevices(db, userId: userId);
await devices.register(token, deviceId: deviceId, topic: bundleId);
await devices.unregister(deviceId);
```

`noticeFromRow(row)` decodes one row (a malformed `data` cell keeps the notice and drops the task fields).
`refresh()` does nothing: sync keeps the store current. Both classes take an optional `now` for tests.

## Sign-out order

`unregister` finishes when the local DELETE is written, not when it is uploaded. Sign out in this order:

```dart
await devices.unregister(deviceId);
await waitForUploadDrain(db);   // bond_sync_powersync: true when the queue is empty, false on timeout
await db.disconnect();          // then clear the database
```

Clearing the database first loses the DELETE and leaves the token registered on the server.

## Wiring with the alerts coordinator

```dart
final tasks = PowerSyncTaskRepository(db, userId: userId);   // bond_tasks_powersync
final feed = WatchNoticeFeed(db, userId: userId);
final devices = SyncPushDevices(db, userId: userId);
final alerts = TaskAlertsCoordinator(/* tasks, feed, alert plugin, registrar built on devices */);
alerts.start();
```

See `bond_tasks_notifications` for the coordinator's parameters.

## Tests

`make test`. Tests use `FakeSyncDb.tables(..., applySql: true, columns: ...)` from `bond_sync_powersync/testing.dart`.
