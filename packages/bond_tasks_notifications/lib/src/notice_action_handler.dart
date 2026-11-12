/// Applies a notice action to its task.
library;

import 'package:bond_notify/bond_notify.dart';
import 'package:bond_tasks/bond_tasks.dart';

import 'alert_plugin.dart';

/// True for the errors that mean the task no longer exists: a `StateError` whose message starts with
/// `task_not_found`, or any error carrying a `statusCode` or `status` of 404 or 410 (bond_api's
/// `ApiException` family has `statusCode`).
bool defaultIsGone(Object error) {
  if (error is StateError && error.message.startsWith('task_not_found')) return true;
  final dynamic e = error;
  for (final read in <Object? Function()>[() => e.statusCode, () => e.status]) {
    try {
      final v = read();
      if (v == 404 || v == 410) return true;
    } catch (_) {
      // The error has no such field.
    }
  }
  return false;
}

/// Done completes the task, cancel cancels it, snooze only puts the notice away;
/// in every case the notice is marked read and its phone notification cleared.
///
/// A repository error propagates and the notice is left unread, so the person can retry, except
/// when [isGone] says the task no longer exists: then the notice is still put away and nothing is
/// rethrown. Once the task change worked, a failure to mark the notice read is ignored.
class NoticeActionHandler {
  NoticeActionHandler(this.repository, this.feed, {this.plugin, bool Function(Object error)? isGone})
      : isGone = isGone ?? defaultIsGone;

  final TaskRepository repository;
  final NoticeFeed feed;
  final AlertPlugin? plugin;
  final bool Function(Object error) isGone;

  Future<void> apply(String noticeId, String taskId, NoticeAction action) async {
    try {
      switch (action) {
        case NoticeAction.done:
          await repository.complete(taskId);
        case NoticeAction.cancel:
          await repository.cancel(taskId);
        case NoticeAction.snooze:
          break;
      }
    } catch (e) {
      if (!isGone(e)) rethrow;
    }
    try {
      await feed.markRead(noticeId);
    } catch (_) {
      // The notice may already be gone; the action itself succeeded.
    }
    try {
      await plugin?.cancel(fnv1a31(noticeId));
    } catch (_) {
      // Clearing the phone notification is best effort.
    }
  }
}
