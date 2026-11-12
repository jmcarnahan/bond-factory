/// The task as the server returns it (`TaskItem`).
library;

import 'package:bond_json/bond_json.dart';

import 'task_enums.dart';
import 'task_priority.dart';

/// One checklist line. [doneAt] is null while open.
class ChecklistItem {
  const ChecklistItem({required this.id, required this.text, this.doneAt});

  factory ChecklistItem.fromJson(Object? json) {
    final m = _asMap(json, 'checklist item');
    return ChecklistItem(id: jstr(m, 'id') ?? '', text: jstr(m, 'text') ?? '', doneAt: jtime(m, 'done_at'));
  }

  final String id;
  final String text;
  final DateTime? doneAt;

  bool get done => doneAt != null;

  Map<String, Object?> toJson() => {'id': id, 'text': text, 'done_at': doneAt == null ? null : jiso(doneAt!)};

  ChecklistItem copyWith({String? text, DateTime? doneAt, bool clearDone = false}) =>
      ChecklistItem(id: id, text: text ?? this.text, doneAt: clearDone ? null : (doneAt ?? this.doneAt));

  @override
  bool operator ==(Object other) =>
      other is ChecklistItem && other.id == id && other.text == text && other.doneAt == doneAt;

  @override
  int get hashCode => Object.hash(id, text, doneAt);
}

/// A reference from a task to an app record (`kind` is app defined).
class TaskLink {
  const TaskLink({required this.kind, required this.id, this.label});

  factory TaskLink.fromJson(Object? json) {
    final m = _asMap(json, 'link');
    return TaskLink(kind: jstr(m, 'kind') ?? '', id: jstr(m, 'id') ?? '', label: jstr(m, 'label'));
  }

  final String kind;
  final String id;
  final String? label;

  Map<String, Object?> toJson() => {'kind': kind, 'id': id, 'label': label};

  @override
  bool operator ==(Object other) => other is TaskLink && other.kind == kind && other.id == id && other.label == label;

  @override
  int get hashCode => Object.hash(kind, id, label);
}

/// The keys of the `TaskItem` wire shape; every other key lands in [Task.extras].
const Set<String> kTaskItemKeys = {
  'id', 'title', 'notes', 'due_date', 'due_time', 'priority', 'due_at', 'status', 'owner_user_id', 'owner_name',
  'assigned_user_id', 'assignee_name', 'checklist', 'remind_minutes_before', 'links', 'completed_at',
  'mirror_enabled', 'mirror_status', 'external_provider', 'external_event_id', 'source', 'created_at',
  'updated_at', 'overdue', //
};

/// A task. [dueDate] is `YYYY-MM-DD` and [dueTime] `HH:MM`, both local wall
/// clock and kept as the wire strings so no time zone can shift them.
class Task {
  const Task({
    required this.id,
    required this.title,
    this.notes,
    this.dueDate,
    this.dueTime,
    this.priority,
    this.dueAt,
    this.status = TaskStatus.open,
    this.ownerUserId = '',
    this.ownerName,
    this.assignedUserId,
    this.assigneeName,
    this.checklist = const [],
    this.remindMinutesBefore = kRemindNone,
    this.links = const [],
    this.completedAt,
    this.mirrorEnabled = true,
    this.mirrorStatus = MirrorStatus.pending,
    this.externalProvider,
    this.externalEventId,
    this.source = 'manual',
    this.createdAt,
    this.updatedAt,
    this.overdue = false,
    this.extras = const {},
  });

  factory Task.fromJson(Map<String, Object?> m) => Task(
        id: jstr(m, 'id') ?? '',
        title: jstr(m, 'title') ?? '',
        notes: jstr(m, 'notes'),
        dueDate: jstr(m, 'due_date'),
        dueTime: jstr(m, 'due_time'),
        priority: TaskPriority.fromWire(jint(m, 'priority')),
        dueAt: jtime(m, 'due_at'),
        status: TaskStatus.fromWire(jstr(m, 'status')),
        ownerUserId: jstr(m, 'owner_user_id') ?? '',
        ownerName: jstr(m, 'owner_name'),
        assignedUserId: jstr(m, 'assigned_user_id'),
        assigneeName: jstr(m, 'assignee_name'),
        checklist: jlist(m, 'checklist', ChecklistItem.fromJson),
        remindMinutesBefore: jint(m, 'remind_minutes_before') ?? kRemindNone,
        links: jlist(m, 'links', TaskLink.fromJson),
        completedAt: jtime(m, 'completed_at'),
        mirrorEnabled: jbool(m, 'mirror_enabled') ?? true,
        mirrorStatus: MirrorStatus.fromWire(jstr(m, 'mirror_status')),
        externalProvider: jstr(m, 'external_provider'),
        externalEventId: jstr(m, 'external_event_id'),
        source: jstr(m, 'source') ?? 'manual',
        createdAt: jtime(m, 'created_at'),
        updatedAt: jtime(m, 'updated_at'),
        overdue: jbool(m, 'overdue') ?? false,
        extras: Map.unmodifiable({
          for (final e in m.entries)
            if (!kTaskItemKeys.contains(e.key)) e.key: e.value,
        }),
      );

  final String id;
  final String title;
  final String? notes;
  final String? dueDate;
  final String? dueTime;
  final TaskPriority? priority;

  /// The server's due instant (UTC); null for an undated task or an old server.
  final DateTime? dueAt;
  final TaskStatus status;
  final String ownerUserId;
  final String? ownerName;
  final String? assignedUserId;
  final String? assigneeName;
  final List<ChecklistItem> checklist;

  /// [kRemindNone], [kRemindMorningOf] or minutes before the due time.
  final int remindMinutesBefore;
  final List<TaskLink> links;
  final DateTime? completedAt;
  final bool mirrorEnabled;
  final MirrorStatus mirrorStatus;
  final String? externalProvider;
  final String? externalEventId;
  final String source;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  /// Open and due before the client's today, as the server computed it.
  final bool overdue;

  /// Every key outside the known `TaskItem` keys (an adopting app's own
  /// columns). Never written by [toJson].
  final Map<String, Object?> extras;

  bool get isOpen => status == TaskStatus.open;
  bool get isDone => status == TaskStatus.done;
  int get checklistDone => checklist.where((c) => c.done).length;

  /// A copy with the fields the controller changes optimistically, plus the display names and
  /// [extras] (what a `TaskEnricher` fills in).
  Task copyWith({
    TaskStatus? status,
    DateTime? completedAt,
    bool? overdue,
    bool clearCompleted = false,
    String? ownerName,
    String? assigneeName,
    Map<String, Object?>? extras,
  }) =>
      Task(
        id: id,
        title: title,
        notes: notes,
        dueDate: dueDate,
        dueTime: dueTime,
        priority: priority,
        dueAt: dueAt,
        status: status ?? this.status,
        ownerUserId: ownerUserId,
        ownerName: ownerName ?? this.ownerName,
        assignedUserId: assignedUserId,
        assigneeName: assigneeName ?? this.assigneeName,
        checklist: checklist,
        remindMinutesBefore: remindMinutesBefore,
        links: links,
        completedAt: clearCompleted ? null : (completedAt ?? this.completedAt),
        mirrorEnabled: mirrorEnabled,
        mirrorStatus: mirrorStatus,
        externalProvider: externalProvider,
        externalEventId: externalEventId,
        source: source,
        createdAt: createdAt,
        updatedAt: updatedAt,
        overdue: overdue ?? this.overdue,
        extras: extras ?? this.extras,
      );

  /// Exactly the `TaskItem` keys.
  Map<String, Object?> toJson() => {
        'id': id,
        'title': title,
        'notes': notes,
        'due_date': dueDate,
        'due_time': dueTime,
        'priority': priority?.wire,
        'due_at': dueAt == null ? null : jiso(dueAt!),
        'status': status.wire,
        'owner_user_id': ownerUserId,
        'owner_name': ownerName,
        'assigned_user_id': assignedUserId,
        'assignee_name': assigneeName,
        'checklist': [for (final c in checklist) c.toJson()],
        'remind_minutes_before': remindMinutesBefore,
        'links': [for (final l in links) l.toJson()],
        'completed_at': completedAt == null ? null : jiso(completedAt!),
        'mirror_enabled': mirrorEnabled,
        'mirror_status': mirrorStatus.wire,
        'external_provider': externalProvider,
        'external_event_id': externalEventId,
        'source': source,
        'created_at': createdAt == null ? null : jiso(createdAt!),
        'updated_at': updatedAt == null ? null : jiso(updatedAt!),
        'overdue': overdue,
      };
}

Map<Object?, Object?> _asMap(Object? v, String what) {
  if (v is Map) return v;
  throw JsonShapeError(what, 'Map', describeJsonType(v));
}
