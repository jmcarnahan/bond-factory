/// List filters, the list envelope and the summary counts.
library;

import 'package:bond_json/bond_json.dart';

import 'task.dart';

/// Query of `GET /tasks`. Null and false-by-default fields are not sent.
class TaskFilters {
  const TaskFilters({
    this.scope,
    this.status,
    this.today,
    this.onOrBefore,
    this.dueFrom,
    this.dueTo,
    this.includeUndated = false,
    this.noDate = false,
    this.ownerUserId,
    this.assignedUserId,
    this.assignedToMe = false,
    this.linkKind,
    this.linkId,
    this.limit,
    this.offset,
    this.timeZone,
  });

  /// `mine` or `all`.
  final String? scope;

  /// `open`, `done` or `all`.
  final String? status;

  /// The client's today (`YYYY-MM-DD`); the server marks `overdue` against it.
  final String? today;
  final String? onOrBefore;
  final String? dueFrom;
  final String? dueTo;
  final bool includeUndated;
  final bool noDate;
  final String? ownerUserId;
  final String? assignedUserId;
  final bool assignedToMe;
  final String? linkKind;
  final String? linkId;
  final int? limit;
  final int? offset;

  /// The viewer's IANA zone name (query `time_zone`).
  final String? timeZone;

  Map<String, Object?> toQuery() => {
        if (scope != null) 'scope': scope,
        if (status != null) 'status': status,
        if (today != null) 'today': today,
        if (onOrBefore != null) 'on_or_before': onOrBefore,
        if (dueFrom != null) 'due_from': dueFrom,
        if (dueTo != null) 'due_to': dueTo,
        if (includeUndated) 'include_undated': 'true',
        if (noDate) 'no_date': 'true',
        if (ownerUserId != null) 'owner_user_id': ownerUserId,
        if (assignedUserId != null) 'assigned_user_id': assignedUserId,
        if (assignedToMe) 'assigned_to_me': 'true',
        if (linkKind != null) 'link_kind': linkKind,
        if (linkId != null) 'link_id': linkId,
        if (limit != null) 'limit': limit,
        if (offset != null) 'offset': offset,
        if (timeZone != null) 'time_zone': timeZone,
      };
}

/// `{items, total, limit, offset}`.
class TaskPage {
  const TaskPage({required this.items, required this.total, this.limit, this.offset});

  factory TaskPage.fromJson(Map<String, Object?> m) {
    final items = jlist(m, 'items', (o) => Task.fromJson(jmapOf(o)));
    return TaskPage(items: items, total: jint(m, 'total') ?? items.length, limit: jint(m, 'limit'), offset: jint(m, 'offset'));
  }

  final List<Task> items;
  final int total;
  final int? limit;
  final int? offset;
}

/// `GET /tasks/summary`.
class TaskSummary {
  const TaskSummary({this.open = 0, this.overdue = 0, this.dueToday = 0, this.noDate = 0});

  factory TaskSummary.fromJson(Map<String, Object?> m) => TaskSummary(
        open: jint(m, 'open') ?? 0,
        overdue: jint(m, 'overdue') ?? 0,
        dueToday: jint(m, 'due_today') ?? 0,
        noDate: jint(m, 'no_date') ?? 0,
      );

  final int open;
  final int overdue;
  final int dueToday;
  final int noDate;
}

/// A decoded list element as a string-keyed map.
Map<String, Object?> jmapOf(Object? o) {
  if (o is Map) return {for (final e in o.entries) e.key.toString(): e.value};
  throw JsonShapeError('', 'Map', describeJsonType(o));
}
