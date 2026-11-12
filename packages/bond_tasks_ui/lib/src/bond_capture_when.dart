import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'bond_check_row.dart';
import 'bond_task_form_due.dart';
import 'task_format.dart';

/// The editable date and time of a captured item, inline. A task has a date and
/// an optional time ("Add a time" / "Remove time"); an event adds an all-day
/// switch, and all-day hides the time. State lives in the card.
class BondCaptureWhen extends StatelessWidget {
  const BondCaptureWhen({
    super.key,
    required this.isEvent,
    required this.allDay,
    required this.date,
    required this.time,
    required this.today,
    required this.onDate,
    required this.onClearDate,
    required this.onTime,
    required this.onAllDay,
    required this.idOf,
    this.showTimeNeedsDate = false,
    this.labels = const CaptureLabels(),
    this.taskLabels = const TaskLabels(),
  });

  final bool isEvent;
  final bool allDay;

  /// `YYYY-MM-DD` and `HH:MM`, or null.
  final String? date;
  final String? time;
  final DateTime today;
  final ValueChanged<DateTime> onDate;
  final VoidCallback onClearDate;

  /// A new time, or null to remove it.
  final ValueChanged<String?> onTime;
  final ValueChanged<bool> onAllDay;
  final String? Function(String part) idOf;
  final CaptureLabels labels;
  final TaskLabels taskLabels;

  /// Show "pick a date to set a time" (a time with no date cannot be accepted).
  final bool showTimeNeedsDate;

  @override
  Widget build(BuildContext context) {
    final d = parseDueDate(date);
    final dateOnly = isEvent && allDay;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (isEvent) ...[
          BondCheckRow(checked: allDay, label: labels.allDay, onChanged: onAllDay, semanticsId: idOf('all-day')),
          BondSpace.h8,
        ],
        if (dateOnly)
          BondDateField(
            label: taskLabels.dueDate,
            placeholder: taskLabels.noDueDate,
            value: d,
            today: today,
            onChanged: (v) => onDate(DateTime(v.year, v.month, v.day)),
            onCleared: onClearDate,
            semanticsId: idOf('date'),
          )
        else
          BondTaskFormDue(
            labels: taskLabels,
            today: today,
            date: d,
            time: parseDueTime(time),
            badDate: null,
            badTime: null,
            timeNeedsDate: showTimeNeedsDate && time != null && d == null,
            canAddTime: d != null,
            onDate: onDate,
            onClearDate: onClearDate,
            onAddTime: () => onTime('09:00'),
            onTime: (v) => onTime(dueTimeString(v)),
            onRemoveTime: () => onTime(null),
            idOf: idOf,
          ),
      ],
    );
  }
}
