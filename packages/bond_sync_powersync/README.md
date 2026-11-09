# bond_sync_powersync

PowerSync connector and store opener for `bond_sync`.

```dart
final policy = SyncPolicy(
  schema: Schema([...appTables, ...syncSupportTables()]),
  createPuts: {'notes': null},
);
final open = await openSyncStore(
  policy: policy,
  path: syncDbPath(dir.path, userId, prefix: 'myapp'),
  names: const BondSyncNames(prefix: 'myapp', loggerName: 'myapp.sync'),
);
final connector = SyncConnector(
  transport: ApiSyncTransport(api),
  clock: ServerClock(),
  policy: policy,
);
await open.powerSync!.connect(connector: connector);
```

- Uploading never throws for a permanent outcome; anything to retry reaches the SDK as a plain `Exception`.
- Refused writes become notes in the local-only `sync_rejections` table; read them through `open.store`.
- Unit tested against a fake `SyncDb`; PowerSync on the web needs sqlite wasm assets this package does not ship.
