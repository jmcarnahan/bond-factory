/// Request bodies: create ([TaskDraft]) and update ([TaskPatch]).
library;

import 'task.dart';
import 'task_enums.dart';

/// A value that was supplied, possibly as an explicit null.
///
/// `null` for a patch field means "leave unchanged" (the key is omitted from
/// the body); `Present(null)` means "clear it" (the key is sent as `null`).
class Present<T> {
  const Present(this.value);

  final T? value;

  @override
  bool operator ==(Object other) => other is Present<T> && other.value == value;

  @override
  int get hashCode => Object.hash(Present, value);
}

/// What is wrong with a draft; the form shows it inline.
enum TaskProblem { titleRequired, titleTooLong, dueTimeRequiresDate }

/// The longest title the server accepts.
const int kTaskTitleMaxLength = 255;

/// The body of `POST /tasks`.
class TaskDraft {
  const TaskDraft({
    required this.title,
    this.id,
    this.notes,
    this.dueDate,
    this.dueTime,
    this.assignedUserId,
    this.checklist = const [],
    this.remindMinutesBefore = kRemindNone,
    this.mirrorEnabled = true,
    this.links = const [],
    this.source,
  });

  final String title;

  /// A client chosen id (`^[\w-]{1,64}$`); a replay returns the existing row.
  final String? id;
  final String? notes;
  final String? dueDate;
  final String? dueTime;
  final String? assignedUserId;
  final List<ChecklistItem> checklist;
  final int remindMinutesBefore;
  final bool mirrorEnabled;
  final List<TaskLink> links;
  final String? source;

  /// Empty when the draft can be sent.
  List<TaskProblem> validate() => [
        if (title.trim().isEmpty) TaskProblem.titleRequired,
        if (title.trim().length > kTaskTitleMaxLength) TaskProblem.titleTooLong,
        if (_has(dueTime) && !_has(dueDate)) TaskProblem.dueTimeRequiresDate,
      ];

  /// Absent values are omitted rather than sent as null.
  Map<String, Object?> toJson() => {
        if (id != null) 'id': id,
        'title': title.trim(),
        if (_has(notes)) 'notes': notes,
        if (_has(dueDate)) 'due_date': dueDate,
        if (_has(dueTime)) 'due_time': dueTime,
        if (_has(assignedUserId)) 'assigned_user_id': assignedUserId,
        'checklist': [for (final c in checklist) c.toJson()],
        'remind_minutes_before': remindMinutesBefore,
        'mirror_enabled': mirrorEnabled,
        'links': [for (final l in links) l.toJson()],
        if (source != null) 'source': source,
      };
}

/// The body of `PUT /tasks/{id}`: omitted fields stay, `Present(null)` clears.
///
/// Only `notes`, `dueDate`, `dueTime` and `assignedUserId` can be cleared;
/// `title` and `mirrorEnabled` cannot be null.
class TaskPatch {
  const TaskPatch({
    this.title,
    this.notes,
    this.dueDate,
    this.dueTime,
    this.assignedUserId,
    this.checklist,
    this.remindMinutesBefore,
    this.mirrorEnabled,
    this.links,
  });

  /// A patch that sets every editable field from [d] (a form save): fields the
  /// draft leaves empty are cleared.
  factory TaskPatch.fromDraft(TaskDraft d) => TaskPatch(
        title: d.title.trim(),
        notes: Present(_has(d.notes) ? d.notes : null),
        dueDate: Present(_has(d.dueDate) ? d.dueDate : null),
        dueTime: Present(_has(d.dueTime) ? d.dueTime : null),
        assignedUserId: Present(_has(d.assignedUserId) ? d.assignedUserId : null),
        checklist: d.checklist,
        remindMinutesBefore: d.remindMinutesBefore,
        mirrorEnabled: d.mirrorEnabled,
        links: d.links,
      );

  final String? title;
  final Present<String>? notes;
  final Present<String>? dueDate;
  final Present<String>? dueTime;
  final Present<String>? assignedUserId;
  final List<ChecklistItem>? checklist;
  final int? remindMinutesBefore;
  final bool? mirrorEnabled;
  final List<TaskLink>? links;

  Map<String, Object?> toJson() => {
        if (title != null) 'title': title,
        if (notes != null) 'notes': notes!.value,
        if (dueDate != null) 'due_date': dueDate!.value,
        if (dueTime != null) 'due_time': dueTime!.value,
        if (assignedUserId != null) 'assigned_user_id': assignedUserId!.value,
        if (checklist != null) 'checklist': [for (final c in checklist!) c.toJson()],
        if (remindMinutesBefore != null) 'remind_minutes_before': remindMinutesBefore,
        if (mirrorEnabled != null) 'mirror_enabled': mirrorEnabled,
        if (links != null) 'links': [for (final l in links!) l.toJson()],
      };
}

bool _has(String? s) => s != null && s.isNotEmpty;
