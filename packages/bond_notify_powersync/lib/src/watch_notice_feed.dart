/// [NoticeFeed] over the synced SQLite store.
library;

import 'package:bond_notify/bond_notify.dart';
import 'package:bond_sync_powersync/bond_sync_powersync.dart';

class WatchNoticeFeed implements NoticeFeed {
  WatchNoticeFeed(this.db, {required this.userId});

  final SyncDb db;
  final String userId;

  @override
  Stream<List<Notice>> watch() => throw UnimplementedError('WatchNoticeFeed.watch is not implemented yet');

  @override
  Future<void> refresh() => throw UnimplementedError('WatchNoticeFeed.refresh is not implemented yet');

  @override
  Future<void> markRead(String id) => throw UnimplementedError('WatchNoticeFeed.markRead is not implemented yet');

  @override
  Future<void> dismiss(String id) => throw UnimplementedError('WatchNoticeFeed.dismiss is not implemented yet');

  @override
  void dispose() {}
}
