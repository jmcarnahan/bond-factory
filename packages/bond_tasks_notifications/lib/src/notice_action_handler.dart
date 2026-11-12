/// Applies a notice action to its task.
library;

import 'package:bond_notify/bond_notify.dart';
import 'package:bond_tasks/bond_tasks.dart';

import 'alert_plugin.dart';

/// Done completes the task, cancel cancels it, snooze only puts the notice away;
/// in every case the notice is marked read and its phone notification cleared.
class NoticeActionHandler {
  NoticeActionHandler(this.repository, this.feed, {this.plugin});

  final TaskRepository repository;
  final NoticeFeed feed;
  final AlertPlugin? plugin;

  Future<void> apply(String noticeId, String taskId, NoticeAction action) => throw UnimplementedError('NoticeActionHandler.apply is not implemented yet');
}
