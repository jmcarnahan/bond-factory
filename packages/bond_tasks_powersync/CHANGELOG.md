# Changelog

## 0.1.0 - unreleased
- First API. `tasksTables()` (with `kTaskColumns`), `taskFromRow` and `PowerSyncTaskRepository` are implemented: day view and
  counts computed on the device, writes as local SQL (status changes carry a `_metadata` action).
