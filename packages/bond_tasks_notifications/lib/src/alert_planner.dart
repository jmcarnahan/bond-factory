/// Which local alerts the open tasks want: filtering, budget and the content fingerprint.
library;

import 'package:bond_tasks/bond_tasks.dart';

import 'alert_labels.dart';
import 'alert_plugin.dart';

/// The alerts wanted at [now], nearest first: only stages with a send time later than now + 2 s, none
/// for a stage in [handledElsewhere], at most [perTask] per task, at most [budget] in total.
List<AlertRequest> planAlerts({
  required List<Task> tasks,
  required DateTime now,
  required TaskPrefs prefs,
  required String userId,
  required List<StageTime> Function(Task, TaskPrefs, DateTime nowUtc) stages,
  required Set<String> handledElsewhere,
  required int perTask,
  required int budget,
  required AlertLabels labels,
}) {
  final horizon = now.add(const Duration(seconds: 2));
  final all = <AlertRequest>[];
  for (final t in tasks) {
    if (!t.isOpen) continue;
    final mine = <AlertRequest>[];
    for (final s in stages(t, prefs, now)) {
      final at = s.sendAt;
      if (at == null || !at.isAfter(horizon)) continue;
      if (handledElsewhere.contains(s.stage)) continue;
      mine.add(_request(t, s, at, userId, labels));
    }
    mine.sort(_byTime);
    all.addAll(mine.take(perTask));
  }
  all.sort(_byTime);
  return all.take(budget).toList();
}

/// Everything that shows on the notification: a change in any part means it must be rescheduled.
String alertFingerprint(AlertRequest r) => [
      r.atUtc.microsecondsSinceEpoch,
      r.title,
      r.body,
      r.route,
      r.taskId,
      r.actions.map((a) => a.wire).join(','),
    ].join('\u0001');

int _byTime(AlertRequest a, AlertRequest b) {
  final c = a.atUtc.compareTo(b.atUtc);
  return c != 0 ? c : a.id.compareTo(b.id);
}

AlertRequest _request(Task t, StageTime s, DateTime at, String userId, AlertLabels labels) {
  final nid = noticeId(t.id, userId, s.stage, s.seq, deadlineToken(t));
  return AlertRequest(
    id: fnv1a31(nid),
    noticeId: nid,
    taskId: t.id,
    title: labels.titleFor(s.stage, last: s.last),
    body: t.title,
    atUtc: at.toUtc(),
    route: '/tasks/${t.id}',
    actions: [
      NoticeAction.done,
      NoticeAction.snooze,
      if (userId == t.ownerUserId) NoticeAction.cancel,
    ],
  );
}
