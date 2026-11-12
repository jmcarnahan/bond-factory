/// A [NoticeFeed] over the REST API, refreshed on a timer.
library;

import 'notice.dart';
import 'notice_feed.dart';
import 'notices_api.dart';

class PollingNoticeFeed implements NoticeFeed {
  PollingNoticeFeed(this.api, {this.interval = const Duration(seconds: 30), DateTime Function()? clock})
      : clock = clock ?? DateTime.now;

  final NoticesApi api;
  final Duration interval;

  /// The source of "now", injectable for tests.
  final DateTime Function() clock;

  @override
  Stream<List<Notice>> watch() => throw UnimplementedError('PollingNoticeFeed.watch is not implemented yet');

  @override
  Future<void> refresh() => throw UnimplementedError('PollingNoticeFeed.refresh is not implemented yet');

  @override
  Future<void> markRead(String id) => throw UnimplementedError('PollingNoticeFeed.markRead is not implemented yet');

  @override
  Future<void> dismiss(String id) => throw UnimplementedError('PollingNoticeFeed.dismiss is not implemented yet');

  @override
  void dispose() {}
}
