/// The seam over the platform's local notifications, and its data classes.
library;

import 'dart:convert';

import 'package:bond_tasks/bond_tasks.dart';

/// The iOS category with Done, Snooze and Cancel: for the owner of a task. `kNoticeCategory`
/// (Done and Snooze only) is for everyone else. A push that wants the same buttons must use these ids.
const kNoticeCategoryOwner = 'bond.task.owner';

/// The category id a request is posted under: the owner one when it carries a cancel action.
String categoryFor(AlertRequest r) =>
    r.actions.contains(NoticeAction.cancel) ? kNoticeCategoryOwner : kNoticeCategory;

/// One notification to schedule or show.
class AlertRequest {
  const AlertRequest({
    required this.id,
    required this.noticeId,
    required this.taskId,
    required this.title,
    required this.body,
    required this.atUtc,
    this.route,
    this.actions = const [],
  });

  /// The platform's integer id (derive it with `fnv1a31(noticeId)`).
  final int id;
  final String noticeId;
  final String taskId;
  final String title;
  final String body;
  final DateTime atUtc;
  final String? route;
  final List<NoticeAction> actions;
}

/// A scheduled notification as the platform reports it.
class PendingAlert {
  const PendingAlert({required this.id, this.payload});

  final int id;
  final String? payload;
}

/// A tap on a notification or on one of its action buttons.
class AlertTap {
  const AlertTap({required this.noticeId, required this.taskId, this.route, this.action});

  final String noticeId;
  final String taskId;
  final String? route;
  final NoticeAction? action;

  /// The notification payload: JSON `{notice_id, task_id, route}`.
  String toPayload() => jsonEncode({'notice_id': noticeId, 'task_id': taskId, 'route': route});

  /// Reads a payload; null when it is empty or not ours.
  static AlertTap? fromPayload(String? payload, {NoticeAction? action}) {
    if (payload == null || payload.isEmpty) return null;
    try {
      final m = jsonDecode(payload);
      if (m is! Map) return null;
      final n = m['notice_id'];
      final t = m['task_id'];
      if (n is! String || t is! String) return null;
      final r = m['route'];
      return AlertTap(noticeId: n, taskId: t, route: r is String ? r : null, action: action);
    } on FormatException {
      return null;
    }
  }
}

abstract interface class AlertPlugin {
  Future<void> init({required void Function(AlertTap) onTap});
  Future<bool> requestPermission();
  Future<void> schedule(AlertRequest r);
  Future<void> show(AlertRequest r);
  Future<void> cancel(int id);
  Future<List<PendingAlert>> pending();

  /// Ids of notifications delivered and still shown (the lock screen or the notification list).
  Future<List<int>> active();

  /// The tap that launched the app, if any.
  Future<AlertTap?> launchTap();
}
