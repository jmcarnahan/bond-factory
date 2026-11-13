# Changelog

## 0.1.0 - unreleased
- Test-only host of an app that already exists: renamed columns, app columns, a legacy REST wire, tables that
  pre-date the modules. One test file per trait (see README).
- The calendar mirror opts in to `transport_pending`: no answer from the provider leaves the task `pending`.
- `push_devices` is mounted on the sync upload (the device writes its own row); no REST route.
- Replays what the legacy phone store (`demos/legacy_phone`) queues: an eighth trait.
