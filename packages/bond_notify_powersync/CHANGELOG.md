# Changelog

## 0.1.0 - unreleased
- First API. `noticesTables()`, `pushDevicesTables()`, `noticeFromRow`, `WatchNoticeFeed` and `SyncPushDevices` (both take an optional `now`) are implemented. Device row ids are hashed to fit the sync id rule; an update writes only token, platform, environment and topic. Adds a `crypto` dependency.
