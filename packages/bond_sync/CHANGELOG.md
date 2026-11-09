# Changelog

## 0.1.0 - unreleased
First API. Pure Dart; depends on bond_json and bond_api; imports no database, no Flutter, no `dart:io`.
Wire shapes follow `docs/contracts/sync_upload.md` and are tested against `fixtures/sync/`.

- Wire models: `SyncToken`, `SyncUploadOp` (`toJson` omits a null `action`), `UploadRequest`
  (omits a null `transaction_id`; the server reads absent and null alike), `SyncOpResult`, `UploadResponse`.
- `SyncTransport` (`fetchToken`, `upload`, `refreshSession`; never signs out) and `ApiSyncTransport(ApiClient,
  {renewal, tokenPath = '/sync/token', uploadPath = '/sync/upload'})`: the paths are the app's choice.
  `SessionRefresh` is re-exported from bond_api.
- `SyncFailure`, `FailureMapper`, `mapSyncFailure` over bond_api exceptions.
- `SyncUploader`: chunking (`UploadLimits`: 100 ops, 512 KiB, per-kind caps), verdict handling, give-up
  bookkeeping (`transientMaxCount = 8`, `transientMaxSpan = 15 min`, `transientStale = 10 min`),
  `uploadNext()` (throws `SyncRetryLater`) and `uploadPending()` (reports the retry in the summary).
- `SyncStore` seam, `SyncBatch`, `SyncResendResult`; `planOutcome` / `OutcomeRules` (the pure plan every
  store runs: re-key, remove a refused create, one note per cause, silent writes).
- `SyncRejection`, `Rejections`, `kSyncRejectionKeep`; `SyncSummary`; `ServerClock` (`skew`);
  `kVerdictText` + `verdictText` (extensible; includes `upload_rejected`, the device-side verdict for a
  chunk the server refused outright); `BondSyncNames`, `syncDbPath` (pure string function);
  `newId`, `isoOf`, `actionOf`.
- `package:bond_sync/testing.dart`: `FakeSyncStore` (optional `coalesce`), `FakeSyncTransport`, `RecordingTransport`.

### Seam sort (which seed core files touched the database)
Six of the ten seed core files imported the database package. Their types moved as follows.
- connector: split. Credentials, the upload loop, chunking, verdict handling and give-up counting are
  `SyncUploader` here; the database calls (next CRUD transaction, complete, re-key, raw-table delete,
  `ps_crud` purge) are behind `SyncStore`; the connector class itself is in `bond_sync_powersync`.
- store_open: all database; moved to `bond_sync_powersync` (`openSyncStore`). Only the path function stays here.
- store_reads: all database (`onChange`, read transactions); moved to the adapter's store.
- rejections: the note model, keep window and reads are here; the SQL is the adapter's.
- resend: the result enum is here; the SQL rebuild is the adapter's.
- transport, sync_summary, server_clock, ids, write_support: no database; lifted as is.

### Decision: the 5xx contradiction
The seed's connector comment said 5xx is counted toward giving up; its failure mapper said not counted.
The mapper wins: 5xx is `transientNoCount` (the upload route answers 5xx only when its database is down;
an op-level bug is a `server_error` verdict inside a 200), so an outage of any length never dead-letters the
queue. 403, 408 and an unreadable body are `transientCounted`.
Also kept from the seed's mapper: 400, 404, 405 and 429 are edge answers (`transientNoCount`), not a verdict
on the data. Only 409, 410, 413, 422 and other 4xx refuse the chunk (`permanent`).

### Dropped from the seed
App-specific verdict texts, app table names and policy, the Riverpod providers, the app's dedicated client
wiring (the app builds its own `ApiClient` without a sign-out hook and passes it to `ApiSyncTransport`).
