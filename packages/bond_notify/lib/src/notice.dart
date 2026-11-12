/// The notice as the server returns it, and the list envelope.
library;

import 'package:bond_json/bond_json.dart';

/// One inbox notice. The task fields live under the wire key `data`.
class Notice {
  const Notice({
    required this.id,
    this.userId = '',
    this.kind = '',
    this.title = '',
    this.body = '',
    this.taskId,
    this.stage,
    this.seq = 0,
    this.dueAt,
    this.priority,
    this.route,
    this.actions = const [],
    this.last = false,
    this.createdAt,
    this.readAt,
    this.dismissedAt,
  });

  factory Notice.fromJson(Map<String, Object?> m) {
    final d = jmap(m, 'data') ?? const <String, Object?>{};
    return Notice(
      id: jstr(m, 'id') ?? '',
      userId: jstr(m, 'user_id') ?? '',
      kind: jstr(m, 'kind') ?? '',
      title: jstr(m, 'title') ?? '',
      body: jstr(m, 'body') ?? '',
      taskId: jstr(d, 'task_id'),
      stage: jstr(d, 'stage'),
      seq: jint(d, 'seq') ?? 0,
      dueAt: jtime(d, 'due_at'),
      priority: jint(d, 'priority'),
      route: jstr(d, 'route'),
      actions: jlist(d, 'actions', (o) => o.toString()),
      last: jbool(d, 'last') ?? false,
      createdAt: jtime(m, 'created_at'),
      readAt: jtime(m, 'read_at'),
      dismissedAt: jtime(m, 'dismissed_at'),
    );
  }

  final String id;
  final String userId;
  final String kind;
  final String title;
  final String body;
  final String? taskId;

  /// `close`, `due` or `past` for a task notice.
  final String? stage;
  final int seq;
  final DateTime? dueAt;

  /// 1 low, 2 normal, 3 high (the task priority wire value).
  final int? priority;
  final String? route;

  /// Wire action ids: `done`, `snooze`, `cancel`.
  final List<String> actions;

  /// True on the final past-due notice.
  final bool last;
  final DateTime? createdAt;
  final DateTime? readAt;
  final DateTime? dismissedAt;

  bool get unread => readAt == null && dismissedAt == null;

  Notice copyWith({DateTime? readAt, DateTime? dismissedAt, bool clearRead = false, bool clearDismissed = false}) =>
      Notice(
        id: id,
        userId: userId,
        kind: kind,
        title: title,
        body: body,
        taskId: taskId,
        stage: stage,
        seq: seq,
        dueAt: dueAt,
        priority: priority,
        route: route,
        actions: actions,
        last: last,
        createdAt: createdAt,
        readAt: clearRead ? null : (readAt ?? this.readAt),
        dismissedAt: clearDismissed ? null : (dismissedAt ?? this.dismissedAt),
      );

  Map<String, Object?> toJson() => {
        'id': id,
        'user_id': userId,
        'kind': kind,
        'title': title,
        'body': body,
        'data': {
          'task_id': taskId,
          'stage': stage,
          'seq': seq,
          'due_at': dueAt == null ? null : jiso(dueAt!),
          'priority': priority,
          'route': route,
          'actions': actions,
          'last': last,
        },
        'created_at': createdAt == null ? null : jiso(createdAt!),
        'read_at': readAt == null ? null : jiso(readAt!),
        'dismissed_at': dismissedAt == null ? null : jiso(dismissedAt!),
      };
}

/// `{items, unread_count}`.
class NoticePage {
  const NoticePage({required this.items, this.unreadCount = 0});

  factory NoticePage.fromJson(Map<String, Object?> m) => NoticePage(
        items: jlist(m, 'items', (o) => Notice.fromJson(_map(o))),
        unreadCount: jint(m, 'unread_count') ?? 0,
      );

  final List<Notice> items;
  final int unreadCount;
}

Map<String, Object?> _map(Object? o) {
  if (o is Map) return {for (final e in o.entries) e.key.toString(): e.value};
  throw JsonShapeError('notice', 'Map', describeJsonType(o));
}
