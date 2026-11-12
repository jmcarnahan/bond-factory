/// The seam between where notices come from and the controller.
library;

import 'notice.dart';

abstract interface class NoticeFeed {
  Stream<List<Notice>> watch();
  Future<void> refresh();
  Future<void> markRead(String id);
  Future<void> dismiss(String id);

  /// Marks every notice read, including those the feed does not hold.
  Future<void> markAllRead();

  /// The server's count of unread notices when it can exceed the list the feed
  /// holds (a REST feed fetches one page); null when the list is complete, as
  /// for a sync-store feed that has every row. Valid when [watch] emits.
  int? get serverUnreadCount;

  void dispose();
}
