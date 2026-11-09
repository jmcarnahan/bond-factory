# Migrating to bond_sync

Contracts: `docs/contracts/sync_upload.md`. Fixtures: `fixtures/sync/`. `bond_sync` is the pure-Dart half (no database,
no Flutter, no `dart:io`); the PowerSync half is `bond_sync_powersync` (see `bond_sync_powersync.md`).

## 1. What it replaces

| Piece | Holds |
|---|---|
| models | `SyncToken`, `SyncUploadOp`, `UploadRequest`, `SyncOpResult`, `UploadResponse` |
| transport | `SyncTransport`, `ApiSyncTransport(ApiClient, {renewal, tokenPath, uploadPath})`, `SessionRefresh` (from bond_api) |
| failures | `SyncFailure`, `FailureMapper`, `mapSyncFailure` |
| uploader | `SyncUploader`, `UploadLimits`, `UploadSummary`, `SyncRetryLater`, `TransientTracker` |
| seam | `SyncStore`, `SyncBatch`, `planOutcome` + `OutcomeRules`, `Rejections`, `SyncRejection` |
| misc | `ServerClock`, `SyncSummary`, `kVerdictText`, `BondSyncNames`, `syncDbPath`, `newId` |
| testing | `package:bond_sync/testing.dart`: `FakeSyncStore`, `FakeSyncTransport`, `RecordingTransport` |

App S (sbel-crm), `mobile/crm_proposals/lib/sync`:

| Seed file | Becomes |
|---|---|
| `core/transport.dart` | `bond_sync` models and `SyncTransport` as is (token and upload shapes unchanged) |
| `app/transport_api.dart` | `ApiSyncTransport(api, renewal: ..., tokenPath: '/powersync/token', uploadPath: '/powersync/upload')`; keep the dedicated sync `ApiClient` with no sign-out hook |
| `core/connector.dart` (596) | upload loop, chunking, verdicts, give-up: `SyncUploader`; database calls: `SyncStore`; the connector class: `bond_sync_powersync` |
| `core/rejections.dart`, `resend.dart` | note model and `Rejections` here; SQL in the adapter |
| `core/store_open.dart`, `store_reads.dart` | adapter only (`openSyncStore`, `watchSnapshot`); `syncDbPath` here as a string function |
| `core/server_clock.dart`, `sync_summary.dart`, `ids.dart`, `write_support.dart` | `ServerClock`, `SyncSummary`, `newId`/`isoOf`/`actionOf` unchanged |
| `app/failure_map.dart` | `mapSyncFailure` over bond_api exceptions; keep only the app's extra verdict texts: `{...kVerdictText, ...appTexts}` |

App A (avalon-crm), `flutterui/packages/avalon_core/lib/src/sync`: `connector.dart` (776) and `sync_database.dart` (474)
split into app policy and the shared packages (see 2 and 3).

## 2. The adapter

- The seam: everything that touched `PowerSyncDatabase` or `Schema` is behind `SyncStore`. The uploader asks for the next
  transaction as plain `SyncUploadOp`s, applies verdicts in one local step, and keeps give-up counters through
  `readMeta`/`writeMeta` (the `sync_meta` table).
- Names: S uses `BondSyncNames(prefix: 'sbel', loggerName: 'sbel.sync')`, so the file name `sbel_<user>.db` and the log
  name stay and existing local databases are found. A uses `prefix: 'avalon'`. The seed default is gone from the package.
- Paths: the defaults are `/sync/token` and `/sync/upload`; S keeps its `/powersync/*` routes through the path arguments.
- Failure map decision: the seed's connector comment said 5xx counts toward giving up, its mapper said it does not. The
  mapper won: 5xx is `transientNoCount`; 403, 408 and an unreadable body count. The seed's edge answers (400, 404, 405,
  429 not counted) are kept; 409, 410, 413, 422 and other 4xx refuse the chunk.
- A stays app-side: `device_now` in the upload body (wrap the transport and add the field before posting), the time policy,
  A's id pattern `^[A-Za-z0-9._:-]{1,200}$`, photo upload, and the `demo_clock` stamp (extra token keys are ignored).

## 3. Call-site changes

- S: delete `core/` after switching imports; check S tests that assert a 5xx count (it is not counted now).
- A constants map: `kSyncUploadChunk` to `UploadLimits.chunkSize`; `kSyncUploadSendCap` to `sendCaps: {'messages:send': 20}`;
  `kSyncTransient*` to `UploadLimits.transient*`; `syncDbPath(Directory dir, ...)` to `syncDbPath(dir.path, ..., prefix: 'avalon')`.
- `newId()` is a uuid v4 and fits the server rule `[A-Za-z0-9_-]{1,64}`; A's ids with `.` or `:` do not.

## 4. Data

None. Local databases keep their file names through the prefix; the wire shapes are unchanged.

## 5. Acceptance

1. `make -C packages/bond_sync test` passes with the fixtures: every file in `fixtures/sync/` round-trips.
2. The app transport posts an envelope the app's server accepts: `transaction_id` is omitted when null, `action` when null.
3. A 401 on upload renews once and sends again; a rejected renewal retries later and never signs the person out.
4. 5xx never dead-letters the queue; eight counted failures spanning 15 minutes (`kTransientMaxCount`,
   `kTransientMaxSpan`) refuse the transaction with `server_error`.
5. A refused create removes the optimistic row and leaves one note per cause; the note text comes from the app's verdict texts.
6. The old local database is opened under the same file name (prefix), and the app's tests pass with `core/` deleted.

## 6. Known gaps (the app keeps these)

- A's stricter time-table give-up (24 hours, parked notes, `bad_time`) has no hook: `UploadLimits` holds one span. Keep that
  rule in an app-side `SyncStore` wrapper, or add a per-op span hook to the package before A adopts it.
- `device_now`, the time policy, the id pattern, photo upload: app-side by design.
