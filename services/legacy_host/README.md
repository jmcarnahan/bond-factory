# legacy_host

A second, test-only host. `sdk_example` is a NEW build whose columns and wire are whatever the modules prefer; this
one differs the way an app that already exists differs. Each trait has a test file that runs in `make test`.

```
make -C services/legacy_host test
make -C services/legacy_host lint
```

| Trait | What it shows | Test file |
|---|---|---|
| 1 Legacy column names | `mirror_enabled`, `external_event_id`, `external_account_user_id` live in `sync_to_calendar`, `calendar_event_id`, `calendar_event_user_id`; rows written by the old app (NULL in every column the mixin added) list, serialise, update, complete | `tests/test_legacy_columns.py` |
| 2 App-owned columns | `client_ref`, `case_ref` through `host_columns` + `prepare`; only the owner or an admin relinks | `tests/test_app_columns.py` |
| 3 Legacy wire | bond's keys plus the app's, naive ISO instants with microseconds, `error_code` errors, both request vocabularies | `tests/test_legacy_wire.py` |
| 4 Old clients on sync | the sync upload an installed client sends (host-sync) | `tests/test_old_client_sync.py` |
| 5 New clients on the legacy wire | the SDK's `TaskDraft` / `TaskPatch` bodies in, recorded answers out | `tests/test_new_client_wire.py` |
| 6 Pre-existing tables | grants in `file_share_grants`, settings in `user_prefs` | `tests/test_existing_tables.py` |
| 7 Provider-side edits | the calendar mirror (host-sync) | `tests/test_provider_edits.py` |
| 8 An existing phone database | the SDK phone store over a local `tasks` table the app already ships (missing columns, renamed flag, app columns, old rows, joined tables); the queues it records (tasks, checklist ticks, settings) are replayed here unchanged | `demos/legacy_phone`: `make -C demos/legacy_phone test`; `tests/test_phone_store_upload.py`, `tests/test_phone_checklist_upload.py`, `tests/test_phone_settings_upload.py` |
| 9 An existing provider seam | a module adopted behind an interface and a table the app already has: an app that already signs through a third-party vendor (`esign_envelopes`, an `EsignProvider` Protocol, its own `EsignError` and `CANNOT_VOID`) adopts `bond_esign` beside it: `NativeProvider` (under 150 lines, `legacy_host/esign_native.py`) next to a vendor stand-in; old rows and the app's `legacy_estimate_id` survive; rows route by their `provider` column; the host's status words and error code come out of the adapter; send, sign on the host's page, fetch the signed PDF | `tests/test_esign_existing_tables.py`, `tests/test_esign_two_providers.py`, `tests/test_esign_legacy_wire.py`, `tests/test_esign_native_flow.py`, `tests/test_esign_adapter_size.py` |

## Tables that pre-date the modules

`legacy_host/legacy_ddl.py` holds the old `tasks`, `file_share_grants` and `user_prefs` as raw DDL and `ADOPT`, the
migration that adds only what the mixins need and the old table lacks. Every added column is nullable with no default,
which is what `ADD COLUMN` leaves in the rows that exist. The one value a row needs is `file_share_grants.purpose`
(server default `'share'`).

| Table | Mixin column the old table lacks (ADDED by the migration) | Renamed or kept nullable |
|---|---|---|
| `tasks` | `priority`, `due_at`, `checklist`, `links`, `remind_minutes_before`, `mirror_status`, `external_provider`, `external_etag`, `source` | `sync_to_calendar`, `calendar_event_id`, `calendar_event_user_id` |
| `file_share_grants` | `purpose`, `owner_type`, `owner_id`, `last_downloaded_at`, `last_ip`, `updated_at` | `attachment_id`, `sender_id`, `hits` (nullable), `created_at` (nullable); app column `recipient_note` |
| `user_prefs` | none | `uid`, `tz`, `day_start`, `day_end`, `remind_lead`; app column `theme` |
| `esign_envelopes`, `estimates` | the three bond_esign tables arrive whole through `ADOPT` (`esign_requests` carries the app column `legacy_estimate_id`); the old tables are untouched | rows of `provider` `fakevendor` stay readable |

Push devices over sync: a phone registers its own `push_devices` row through `POST /sync/upload` (no REST route); see `tests/test_push_devices_sync.py`.

Mirror `pending` opt-in: the phone store can write `mirror_status` itself (`mirrorStatusOnWrite` in `demos/legacy_phone/lib/src/legacy_store.dart`), so a row that waits for the calendar says `pending` on the device before the server's answer syncs back.

Known limits are pinned in the tests and listed in `docs/migration/bond_tasks_py_host.md` section 5.

## Routes

`POST/GET /tasks`, `GET/PUT/DELETE /tasks/{id}`, `POST /tasks/{id}/complete|reopen`, `GET/PUT /prefs`, `POST /shares`,
`GET /shares/{token}`, `GET|POST /estimates/{id}/sign?sign=1&t=<token>` (the native signing page) and `GET /esign/static/{name}`. The caller is the header `X-User` (401 without it).
