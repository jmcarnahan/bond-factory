/// [NoticeFeed] over the synced SQLite store.
library;

import 'dart:convert';

import 'package:bond_notify/bond_notify.dart';
import 'package:bond_sync_powersync/bond_sync_powersync.dart';

import 'notify_tables.dart';

String _isoZ(DateTime t) => DateTime.fromMillisecondsSinceEpoch(t.millisecondsSinceEpoch, isUtc: true).toIso8601String();

/// Decodes a `notices` row. `data` is JSON text; a malformed cell reads as empty. A datetime
/// without a Z is UTC.
Notice noticeFromRow(SyncRow row) {
  Object? data = row['data'];
  if (data is String) {
    try {
      data = jsonDecode(data);
    } catch (_) {
      data = null;
    }
  }
  final m = <String, Object?>{
    'id': row['id']?.toString(),
    'user_id': row['user_id']?.toString(),
    'kind': row['kind']?.toString(),
    'title': row['title']?.toString(),
    'body': row['body']?.toString(),
    'data': data is Map ? data : null,
    'created_at': _time(row['created_at']),
    'read_at': _time(row['read_at']),
    'dismissed_at': _time(row['dismissed_at']),
  };
  try {
    return Notice.fromJson(m);
  } catch (_) {
    // A data cell of the wrong shape inside: keep the notice, drop the task fields.
    return Notice.fromJson({...m, 'data': null});
  }
}

String? _time(Object? v) {
  if (v is! String || v.trim().isEmpty) return null;
  final s = v.trim();
  final zoned = RegExp(r'(Z|[+-]\d{2}(:?\d{2})?)$', caseSensitive: false).hasMatch(s);
  final d = DateTime.tryParse(zoned ? s : '${s}Z');
  return d == null ? null : _isoZ(d);
}

/// Notices from the local store, newest first, dismissed ones hidden. [markRead] and [dismiss]
/// are local updates of `read_at` / `dismissed_at` to the device's UTC time (ISO with a Z); the
/// server replaces it with its own clock on upload. [refresh] does nothing: sync keeps the store current.
class WatchNoticeFeed implements NoticeFeed {
  WatchNoticeFeed(this.db, {required this.userId, DateTime Function()? now}) : _now = now ?? DateTime.now;

  final SyncDb db;
  final String userId;
  final DateTime Function() _now;

  @override
  Stream<List<Notice>> watch() => watchSnapshot(db, [kNoticesTable], (sql) async {
        final rows = await sql.getAll(
          'SELECT * FROM $kNoticesTable WHERE user_id = ? AND dismissed_at IS NULL ORDER BY created_at DESC, id DESC',
          [userId],
        );
        return [for (final r in rows) noticeFromRow(r)];
      });

  @override
  Future<void> refresh() async {}

  Future<void> _stamp(String column, String id) => db.writeTransaction(
        (tx) => tx.execute(
          'UPDATE $kNoticesTable SET $column = ? WHERE id = ? AND user_id = ? AND $column IS NULL',
          [_isoZ(_now()), id, userId],
        ),
      );

  @override
  Future<void> markRead(String id) => _stamp('read_at', id);

  @override
  Future<void> dismiss(String id) => _stamp('dismissed_at', id);

  /// One local UPDATE of the user's unread, undismissed rows: each queues one patch holding only `read_at`.
  @override
  Future<void> markAllRead() => db.writeTransaction(
        (tx) => tx.execute(
          'UPDATE $kNoticesTable SET read_at = ? WHERE user_id = ? AND read_at IS NULL AND dismissed_at IS NULL',
          [_isoZ(_now()), userId],
        ),
      );

  /// Always null: the store holds every row, so the list is complete.
  @override
  int? get serverUnreadCount => null;

  @override
  void dispose() {}
}
