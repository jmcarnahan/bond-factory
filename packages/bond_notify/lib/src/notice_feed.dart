/// The seam between where notices come from and the controller.
library;

import 'notice.dart';

abstract interface class NoticeFeed {
  Stream<List<Notice>> watch();
  Future<void> refresh();
  Future<void> markRead(String id);
  Future<void> dismiss(String id);
  void dispose();
}
