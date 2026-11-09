# bond_sync
Role: backend-agnostic sync core: wire models, transport, failure mapping, uploader, `SyncStore` seam. Pure Dart.

## Key files
- `lib/src/uploader.dart`: `SyncUploader` (chunks, verdicts, give-up). `store.dart`: the `SyncStore` seam.
- `lib/src/outcome.dart`: `planOutcome`, the plan every store runs. `failure.dart`: `mapSyncFailure`.
- `lib/src/models.dart`, `transport.dart`: wire shapes and `ApiSyncTransport`.
- `lib/testing.dart`: `FakeSyncStore`, `FakeSyncTransport`, `RecordingTransport`.
- Contract: `docs/contracts/sync_upload.md`; fixtures `../../fixtures/sync`.

## Commands
- `make test T=test/uploader_test.dart`
- `make analyze`

## Rules
- No database, Flutter or `dart:io` import in `lib/` (`test/boundary_test.dart` enforces).
- Database work goes behind `SyncStore`; the PowerSync side lives in `bond_sync_powersync`.
- No codegen; hand-write fromJson.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
