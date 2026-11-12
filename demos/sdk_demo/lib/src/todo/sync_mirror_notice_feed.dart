import 'dart:convert';

import 'package:bond_notify/bond_notify.dart';
import 'package:bond_notify_powersync/bond_notify_powersync.dart';
import 'package:bond_sync_powersync/testing.dart';

/// The watch feed of the demo: a real [WatchNoticeFeed] over an in-memory [FakeSyncDb] that this
/// class fills from `GET /notices` (the stand-in for the sync download) and whose local reads and
/// dismissals it sends to the REST routes (the stand-in for the sync upload). So the page shows
/// the same notices through either feed, and a read or dismissal persists on the server.
class SyncMirrorNoticeFeed implements NoticeFeed {
  SyncMirrorNoticeFeed(this.api, {required String userId, DateTime Function()? now})
      : db = FakeSyncDb.tables(
          {kNoticesTable: []},
          applySql: true,
          columns: {
            kNoticesTable: {'id', ...kNoticeColumns},
          },
        ) {
    _inner = WatchNoticeFeed(db, userId: userId, now: now);
  }

  final NoticesApi api;
  final FakeSyncDb db;
  late final WatchNoticeFeed _inner;

  @override
  Stream<List<Notice>> watch() => _inner.watch();

  /// Downloads the first page and replaces the local rows.
  @override
  Future<void> refresh() async {
    final page = await api.list(limit: 50);
    db.tables[kNoticesTable] = [
      for (final n in page.items) _row(n),
    ];
    db.changes.add(null);
  }

  static Map<String, Object?> _row(Notice n) {
    final j = n.toJson();
    return {...j, 'data': jsonEncode(j['data'])};
  }

  @override
  Future<void> markRead(String id) async {
    await _inner.markRead(id);
    await api.read(id);
  }

  @override
  Future<void> dismiss(String id) async {
    await _inner.dismiss(id);
    await api.dismiss(id);
  }

  @override
  Future<void> markAllRead() async {
    await _inner.markAllRead();
    await api.readAll();
  }

  @override
  int? get serverUnreadCount => _inner.serverUnreadCount;

  @override
  void dispose() => _inner.dispose();
}
