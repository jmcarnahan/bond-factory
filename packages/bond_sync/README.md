# bond_sync

Backend-agnostic sync core: wire models, transport, failure mapping, an uploader that chunks queued writes
and handles the server's per-op verdicts, and the `SyncStore` seam a local database sits behind. Pure Dart.
The PowerSync implementation is `bond_sync_powersync`. The wire contract is `docs/contracts/sync_upload.md`.

```dart
final uploader = SyncUploader(
  store: store,                        // a SyncStore (FakeSyncStore in tests)
  transport: ApiSyncTransport(api),    // POST /sync/upload, POST /sync/token
  clock: ServerClock(),
);
final summary = await uploader.uploadPending();
for (final o in summary.outcomes) {
  print('${o.op.id}: ${o.verdict.status} ${o.verdict.code ?? ''}');
}
```

- Give sync an `ApiClient` without a hook that signs the person out; a 401 reaches the uploader, which asks
  `refreshSession()` once and sends again.
- A refused write keeps a note (`Rejections`) shown next to the row; `kVerdictText` has plain words per code.
- Tests: `package:bond_sync/testing.dart` has `FakeSyncStore`, `FakeSyncTransport`, `RecordingTransport`.
