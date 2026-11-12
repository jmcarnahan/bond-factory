/// `POST /tasks/parse`: what natural-language capture found. Nothing is created
/// until the user confirms; [TaskCandidate.toDraft] makes the create body.
library;

import 'package:bond_json/bond_json.dart';

import 'task.dart';
import 'task_draft.dart';
import 'task_enums.dart';
import 'task_filters.dart';
import 'task_priority.dart';

/// A person or record the text mentioned, with the app's matches.
class LinkOption {
  const LinkOption({required this.id, required this.label});

  factory LinkOption.fromJson(Object? o) {
    final m = jmapOf(o);
    return LinkOption(id: jstr(m, 'id') ?? '', label: jstr(m, 'label') ?? '');
  }

  final String id;
  final String label;
}

class LinkCandidate {
  const LinkCandidate({required this.text, this.kind = 'contact', this.candidates = const []});

  factory LinkCandidate.fromJson(Object? o) {
    final m = jmapOf(o);
    return LinkCandidate(
      text: jstr(m, 'text') ?? '',
      kind: jstr(m, 'kind') ?? 'contact',
      candidates: jlist(m, 'candidates', LinkOption.fromJson),
    );
  }

  final String text;
  final String kind;
  final List<LinkOption> candidates;
}

sealed class CaptureItem {
  const CaptureItem({
    required this.title,
    this.links = const [],
    this.confidence = 1,
    this.flags = const [],
    this.degraded = false,
  });

  final String title;
  final List<LinkCandidate> links;
  final double confidence;

  /// For example `low_confidence`.
  final List<String> flags;
  final bool degraded;

  /// An item of a kind this client does not know is skipped (null).
  static CaptureItem? fromJson(Object? o) {
    final m = jmapOf(o);
    return switch (jstr(m, 'kind')) {
      'task' => TaskCandidate.fromJson(m),
      'event' => EventCandidate.fromJson(m),
      _ => null,
    };
  }
}

class TaskCandidate extends CaptureItem {
  const TaskCandidate({
    required super.title,
    super.links,
    super.confidence,
    super.flags,
    super.degraded,
    this.dueDate,
    this.dueTime,
    this.dueDefaulted = false,
    this.priority,
  });

  factory TaskCandidate.fromJson(Map<String, Object?> m) => TaskCandidate(
        title: jstr(m, 'title') ?? '',
        links: jlist(m, 'links', LinkCandidate.fromJson),
        confidence: jnum(m, 'confidence') ?? 1,
        flags: jlist(m, 'flags', (o) => o.toString()),
        degraded: jbool(m, 'degraded') ?? false,
        dueDate: jstr(m, 'due_date'),
        dueTime: jstr(m, 'due_time'),
        dueDefaulted: jbool(m, 'due_defaulted') ?? false,
        priority: TaskPriority.fromWire(jint(m, 'priority')),
      );

  final String? dueDate;
  final String? dueTime;

  /// The date was not in the text; the server filled in a default.
  final bool dueDefaulted;
  final TaskPriority? priority;

  /// An edited copy for the review screen. A `clear*` flag sets that field to null (it wins over the
  /// value). Confidence, flags and `degraded` are kept.
  TaskCandidate copyWith({
    String? title,
    String? dueDate,
    String? dueTime,
    bool? dueDefaulted,
    TaskPriority? priority,
    List<LinkCandidate>? links,
    bool clearDueDate = false,
    bool clearDueTime = false,
    bool clearPriority = false,
  }) =>
      TaskCandidate(
        title: title ?? this.title,
        links: links ?? this.links,
        confidence: confidence,
        flags: flags,
        degraded: degraded,
        dueDate: clearDueDate ? null : (dueDate ?? this.dueDate),
        dueTime: clearDueTime ? null : (dueTime ?? this.dueTime),
        dueDefaulted: dueDefaulted ?? this.dueDefaulted,
        priority: clearPriority ? null : (priority ?? this.priority),
      );

  /// The create body; [links] are the matches the user confirmed.
  TaskDraft toDraft({List<TaskLink> links = const []}) => TaskDraft(
        title: title,
        dueDate: dueDate,
        dueTime: dueTime,
        priority: priority,
        remindMinutesBefore: kRemindUseDefault,
        links: links,
        source: 'capture',
      );
}

class EventCandidate extends CaptureItem {
  const EventCandidate({
    required super.title,
    super.links,
    super.confidence,
    super.flags,
    super.degraded,
    this.startDate,
    this.startTime,
    this.allDay = false,
    this.endDate,
    this.endTime,
  });

  factory EventCandidate.fromJson(Map<String, Object?> m) => EventCandidate(
        title: jstr(m, 'title') ?? '',
        links: jlist(m, 'links', LinkCandidate.fromJson),
        confidence: jnum(m, 'confidence') ?? 1,
        flags: jlist(m, 'flags', (o) => o.toString()),
        degraded: jbool(m, 'degraded') ?? false,
        startDate: jstr(m, 'start_date'),
        startTime: jstr(m, 'start_time'),
        allDay: jbool(m, 'all_day') ?? false,
        endDate: jstr(m, 'end_date'),
        endTime: jstr(m, 'end_time'),
      );

  final String? startDate;
  final String? startTime;
  final bool allDay;
  final String? endDate;
  final String? endTime;

  /// An edited copy for the review screen. A `clear*` flag sets that field to null (it wins over the
  /// value). Confidence, flags and `degraded` are kept.
  EventCandidate copyWith({
    String? title,
    String? startDate,
    String? startTime,
    bool? allDay,
    String? endDate,
    String? endTime,
    List<LinkCandidate>? links,
    bool clearStartDate = false,
    bool clearStartTime = false,
    bool clearEndDate = false,
    bool clearEndTime = false,
  }) =>
      EventCandidate(
        title: title ?? this.title,
        links: links ?? this.links,
        confidence: confidence,
        flags: flags,
        degraded: degraded,
        startDate: clearStartDate ? null : (startDate ?? this.startDate),
        startTime: clearStartTime ? null : (startTime ?? this.startTime),
        allDay: allDay ?? this.allDay,
        endDate: clearEndDate ? null : (endDate ?? this.endDate),
        endTime: clearEndTime ? null : (endTime ?? this.endTime),
      );
}

class ParseResult {
  const ParseResult({this.items = const [], this.degraded = false, this.reason, this.dropped = 0});

  factory ParseResult.fromJson(Map<String, Object?> m) => ParseResult(
        items: [
          for (final o in (m['items'] as List<Object?>? ?? const []))
            ?CaptureItem.fromJson(o),
        ],
        degraded: jbool(m, 'degraded') ?? false,
        reason: jstr(m, 'reason'),
        dropped: _nonNegative(jint(m, 'dropped')),
      );

  final List<CaptureItem> items;
  final bool degraded;

  /// How many items the model returned that the server discarded; the key is sent only above zero.
  final int dropped;

  /// Null, `model_unavailable` or `invalid_output`.
  final String? reason;
}

int _nonNegative(int? v) => v == null || v < 0 ? 0 : v;
