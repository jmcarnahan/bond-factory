# Changelog

## 0.1.0 - unreleased
Note
- The `remind_at` and `reminded_at` columns are not part of the tasks table or stream query (removed with the queued reminder).

- First API. `tasksTables()` (with `kTaskColumns`), `taskFromRow` and `PowerSyncTaskRepository` are implemented: day view and
  counts computed on the device, writes as local SQL (status changes carry a `_metadata` action).
