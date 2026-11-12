/// A [NoticeFeed] over the REST API, refreshed on a timer.
library;

import 'dart:async';

import 'notice.dart';
import 'notice_feed.dart';
import 'notices_api.dart';
import 'replay_stream.dart';

/// Polls the first page of notices every [interval] while someone listens to
/// [watch]. The list is newest first. A refresh that is overtaken by a newer
/// refresh or by a local change is dropped, so an old answer never wins.
class PollingNoticeFeed implements NoticeFeed {
  PollingNoticeFeed(this.api, {this.interval = const Duration(seconds: 30), DateTime Function()? clock})
      : clock = clock ?? DateTime.now {
    _out = ReplayStream<List<Notice>>(onFirstListen: _startTimer, onNoListeners: _stopTimer);
  }

  final NoticesApi api;
  final Duration interval;

  /// The source of "now", injectable for tests; stamps `readAt` on a local read.
  final DateTime Function() clock;

  late final ReplayStream<List<Notice>> _out;
  Timer? _timer;
  int _generation = 0;
  bool _disposed = false;
  List<Notice> _items = const [];
  int? _serverUnread;

  /// The server's unread count from the last page (it may exceed the 50 held).
  @override
  int? get serverUnreadCount => _serverUnread;

  @override
  Stream<List<Notice>> watch() => _out.stream;

  void _startTimer() {
    if (_disposed) return;
    _timer?.cancel();
    _timer = Timer.periodic(interval, (_) => refresh());
  }

  void _stopTimer() {
    _timer?.cancel();
    _timer = null;
  }

  void _emit(List<Notice> items) {
    _items = List.unmodifiable(items);
    if (!_disposed) _out.add(_items);
  }

  void _drop() {
    final s = _serverUnread;
    if (s != null && s > 0) _serverUnread = s - 1;
  }

  /// Fetches the first page (50) and emits it. A failure goes to the stream as
  /// an error; the timer keeps running and the next refresh may recover.
  @override
  Future<void> refresh() async {
    if (_disposed) return;
    final mine = ++_generation;
    try {
      final page = await api.list(limit: 50);
      if (_disposed || mine != _generation) return;
      _serverUnread = page.unreadCount;
      _emit(page.items);
    } catch (e, st) {
      if (_disposed || mine != _generation) return;
      _out.addError(e, st);
    }
  }

  Notice? _held(String id) {
    for (final n in _items) {
      if (n.id == id) return n;
    }
    return null;
  }

  @override
  Future<void> markRead(String id) async {
    final n = await api.read(id);
    _generation++;
    if (_held(id)?.unread ?? false) _drop();
    final stamped = n.readAt == null && n.dismissedAt == null ? n.copyWith(readAt: clock().toUtc()) : n;
    _emit([for (final o in _items) o.id == id ? stamped : o]);
  }

  @override
  Future<void> dismiss(String id) async {
    await api.dismiss(id);
    _generation++;
    if (_held(id)?.unread ?? false) _drop();
    _emit([
      for (final n in _items)
        if (n.id != id) n,
    ]);
  }

  @override
  Future<void> markAllRead() async {
    final count = await api.readAll();
    _generation++;
    _serverUnread = count;
    final at = clock().toUtc();
    _emit([for (final n in _items) n.unread ? n.copyWith(readAt: at) : n]);
  }

  @override
  void dispose() {
    _disposed = true;
    _stopTimer();
    _out.close();
  }
}
