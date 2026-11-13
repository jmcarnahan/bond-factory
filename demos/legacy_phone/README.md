# legacy_phone

The Dart twin of `services/legacy_host`: a test-only package that shows the SDK's `PowerSyncTaskRepository` working over a
phone database an app already has. It is the eighth trait of the adopter proof (`docs/decisions/2026-11-12-adopter-proof.md`).

The local `tasks` table has nine columns the SDK knows missing, the calendar flag in `sync_to_calendar` (0/1, NULL meaning
on), the app's own `client_ref`, `case_ref` and `case_file_no`, and rows an old build wrote (no `due_at`, `''` in
`assigned_user_id` and `client_ref`). The task screens join `users`, `clients` and `cases`. `legacyTaskRepository` in
`lib/src/legacy_store.dart` is the whole adoption: one `TaskTableShape`, an enricher, two mirror rules, an app rule and an
after-write hook. Every test runs at two stages: the table as shipped, and the same database file opened again after the
app adds the nine columns to its schema.

```
make -C demos/legacy_phone test
make -C demos/legacy_phone analyze
BOND_REGEN_FIXTURES=1 make -C demos/legacy_phone test T=test/upload_fixture_test.dart   # rewrite the recorded upload
make -C services/legacy_host test T=tests/test_phone_store_upload.py                      # the legacy server takes it
```

| Test file | What it proves |
|---|---|
| `read_test.dart` | open list order, `getTask`/`watchTask`, summary, day view, old rows with no `due_at` |
| `list_where_test.dart` | `listWhere`/`watchWhere` by client and case: SQL filter, total, status, not owner-filtered |
| `names_test.dart` | owner, assignee, client and case names on every read; re-emit when a joined row changes |
| `write_queue_test.dart` | writes name only the stage's columns; the real upload queue carries the app's keys |
| `completed_by_test.dart`, `mirror_status_test.dart` | the two status rules |
| `app_rules_test.dart`, `after_write_test.dart` | the app's prepare rule and after-write hook |
| `ui_contract_test.dart` | `bond_tasks_ui` day list and the `bond_tasks_notifications` coordinator over the store |
| `upload_fixture_test.dart` | the queue equals `fixtures/legacy_host/upload_phone_store.json` |
