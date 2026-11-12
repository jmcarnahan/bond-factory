/// Framework-free inbox state with optimistic read and dismiss.
library;

import 'dart:async';
import 'dart:math' as math;

import 'notice.dart';
import 'notice_feed.dart';
import 'replay_stream.dart';

class NoticeState {
  const NoticeState({this.items = const [], this.unreadCount = 0, this.loading = false, this.error});

  final List<Notice> items;
  final int unreadCount;
  final bool loading;
  final Object? error;

  NoticeState copyWith({List<Notice>? items, int? unreadCount, bool? loading, Object? error, bool clearError = false}) =>
      NoticeState(
        items: items ?? this.items,
        unreadCount: unreadCount ?? this.unreadCount,
        loading: loading ?? this.loading,
        error: clearError ? null : (error ?? this.error),
      );
}

class NoticeController {
  NoticeController(this.feed, {this.fresh = const Duration(minutes: 10), DateTime Function()? clock})
      : clock = clock ?? DateTime.now;

  final NoticeFeed feed;

  /// How recent a notice must be (by `createdAt`) to count as new for [newUnread].
  final Duration fresh;

  /// The source of "now", injectable for tests.
  final DateTime Function() clock;

  final _states = ReplayStream<NoticeState>();
  final _new = StreamController<Notice>.broadcast();
  StreamSubscription<List<Notice>>? _sub;
  NoticeState _state = const NoticeState();
  final _seen = <String>{};
  bool _started = false;
  bool _disposed = false;

  /// Replays the latest state to each new listener.
  Stream<NoticeState> get states => _states.stream;

  /// Fires exactly once per notice id that is unread, has not been emitted
  /// before, and was created no longer than [fresh] before now. Opening the app
  /// after a gap alerts for nothing older; the inbox still shows everything.
  /// A notice without `createdAt` is never emitted.
  Stream<Notice> get newUnread => _new.stream;

  void _set(NoticeState s) {
    _state = s;
    if (!_disposed) _states.add(s);
  }

  static int _unread(List<Notice> items) => items.where((n) => n.unread).length;

  /// The unread count after a change of [delta] to a count that was [current]:
  /// the server's count is adjusted (it can exceed the list); otherwise the
  /// list is counted.
  int _count(List<Notice> items, int current, int delta) =>
      feed.serverUnreadCount != null ? math.max(0, current + delta) : _unread(items);

  /// Asks the feed to refresh now. A failure lands in [NoticeState.error]; it is never thrown.
  Future<void> refresh() async {
    if (_disposed) return;
    try {
      await feed.refresh();
    } catch (e) {
      if (!_disposed) _set(_state.copyWith(loading: false, error: e));
    }
  }

  /// Marks every notice read: the state changes first; on failure the notices
  /// that were unread are put back and [NoticeState.error] is set.
  Future<void> markAllRead() async {
    final before = _state;
    final wasUnread = {for (final n in before.items) if (n.unread) n.id: n};
    final at = clock().toUtc();
    _set(_state.copyWith(
      items: [for (final n in before.items) n.unread ? n.copyWith(readAt: at) : n],
      unreadCount: 0,
      clearError: true,
    ));
    try {
      await feed.markAllRead();
    } catch (e) {
      if (_disposed) return;
      _set(_state.copyWith(
        items: [for (final n in _state.items) wasUnread[n.id] ?? n],
        unreadCount: before.unreadCount,
        error: e,
      ));
    }
  }

  /// Subscribes to the feed and asks it for a first refresh.
  Future<void> start() async {
    if (_started || _disposed) return;
    _started = true;
    _set(_state.copyWith(loading: true));
    _sub = feed.watch().listen(_onItems, onError: _onError);
    await feed.refresh();
  }

  void _onItems(List<Notice> items) {
    if (_disposed) return;
    final cutoff = clock().toUtc().subtract(fresh);
    for (final n in items) {
      final at = n.createdAt;
      if (n.unread && at != null && !at.isBefore(cutoff) && _seen.add(n.id)) _new.add(n);
    }
    _set(NoticeState(items: items, unreadCount: feed.serverUnreadCount ?? _unread(items)));
  }

  void _onError(Object e, StackTrace st) => _set(_state.copyWith(loading: false, error: e));

  Future<void> markRead(String id) => _optimistic(id, (n) => n.copyWith(readAt: clock().toUtc()), feed.markRead);

  Future<void> dismiss(String id) => _optimistic(id, null, feed.dismiss);

  /// Changes the state first, then calls the feed; on failure puts the one
  /// notice back and sets [NoticeState.error].
  Future<void> _optimistic(String id, Notice Function(Notice)? change, Future<void> Function(String) call) async {
    final i = _state.items.indexWhere((n) => n.id == id);
    if (i < 0) return;
    final before = _state.items[i];
    final drop = before.unread ? -1 : 0;
    final next = [..._state.items];
    if (change == null) {
      next.removeAt(i);
    } else {
      next[i] = change(before);
    }
    _set(_state.copyWith(items: next, unreadCount: _count(next, _state.unreadCount, drop), clearError: true));
    try {
      await call(id);
    } catch (e) {
      if (_disposed) return;
      final now = [..._state.items];
      final j = now.indexWhere((n) => n.id == id);
      if (change == null) {
        if (j < 0) now.insert(i.clamp(0, now.length), before);
      } else if (j >= 0) {
        now[j] = before;
      }
      _set(_state.copyWith(items: now, unreadCount: _count(now, _state.unreadCount, -drop), error: e));
    }
  }

  void dispose() {
    _disposed = true;
    _sub?.cancel();
    _sub = null;
    _states.close();
    _new.close();
  }
}
