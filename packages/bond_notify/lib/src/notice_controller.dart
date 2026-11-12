/// Framework-free inbox state with optimistic read and dismiss.
library;

import 'notice.dart';
import 'notice_feed.dart';

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
  NoticeController(this.feed);

  final NoticeFeed feed;

  Stream<NoticeState> get states => throw UnimplementedError('NoticeController.states is not implemented yet');

  /// Fires once per notice id that arrives unread.
  Stream<Notice> get newUnread => throw UnimplementedError('NoticeController.newUnread is not implemented yet');

  Future<void> start() => throw UnimplementedError('NoticeController.start is not implemented yet');
  Future<void> markRead(String id) => throw UnimplementedError('NoticeController.markRead is not implemented yet');
  Future<void> dismiss(String id) => throw UnimplementedError('NoticeController.dismiss is not implemented yet');
  void dispose() {}
}
