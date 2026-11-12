import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

/// The due date and time part of the task form. State lives in the form; this
/// draws it and reports changes. [idOf] maps a part name to a semantics id.
class BondTaskFormDue extends StatelessWidget {
  const BondTaskFormDue({
    super.key,
    required this.labels,
    required this.today,
    required this.date,
    required this.time,
    required this.badDate,
    required this.badTime,
    required this.timeNeedsDate,
    required this.onDate,
    required this.onClearDate,
    required this.onAddTime,
    required this.onTime,
    required this.onRemoveTime,
    required this.idOf,
    this.canAddTime = true,
    this.onTimeValid,
  });

  final TaskLabels labels;
  final DateTime today;
  final DateTime? date;
  final BondTime? time;

  /// A date or time the server sent that could not be read; shown inline.
  final String? badDate;
  final String? badTime;
  final bool timeNeedsDate;
  final ValueChanged<DateTime> onDate;
  final VoidCallback onClearDate;
  final VoidCallback onAddTime;
  final ValueChanged<BondTime> onTime;
  final VoidCallback onRemoveTime;
  final String? Function(String part) idOf;

  /// False while there is no date: a task with no date has no time.
  final bool canAddTime;

  /// Told when the time boxes become invalid (false) or valid again (true).
  final ValueChanged<bool>? onTimeValid;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final l = labels;
    Widget problem(String s) => Padding(
          padding: const EdgeInsets.only(top: BondSpace.s4),
          child: Text(s, style: text.small.copyWith(color: t.danger.press)),
        );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        BondDateField(
          label: l.dueDate,
          placeholder: l.noDueDate,
          value: date,
          today: today,
          onChanged: (d) => onDate(DateTime(d.year, d.month, d.day)),
          onCleared: onClearDate,
          semanticsId: idOf('due-date'),
        ),
        if (badDate != null) problem('${l.unrecognisedDate}: $badDate'),
        BondSpace.h12,
        if (time == null && canAddTime)
          Align(
            alignment: Alignment.centerLeft,
            child: BondButton(
              label: l.addTime,
              variant: BondButtonVariant.secondary,
              onPressed: onAddTime,
              semanticsId: idOf('due-time-add'),
            ),
          )
        else if (time != null) ...[
          BondTimeField(label: l.dueTime, value: time!, onChanged: onTime, onValidChanged: onTimeValid, semanticsId: idOf('due-time')),
          Align(
            alignment: Alignment.centerLeft,
            child: BondButton(
              label: l.removeTime,
              variant: BondButtonVariant.quiet,
              onPressed: onRemoveTime,
              semanticsId: idOf('due-time-remove'),
            ),
          ),
        ],
        if (badTime != null) problem('${l.unrecognisedTime}: $badTime'),
        if (timeNeedsDate) problem(l.dueTimeNeedsDate),
      ],
    );
  }
}
