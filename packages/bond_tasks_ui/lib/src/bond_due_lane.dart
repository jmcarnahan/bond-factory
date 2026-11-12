import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'task_format.dart';

/// The TODOs of one calendar day, for an app's day view: those whose day
/// (`dayFor`, in the device zone) is [day]. Date-only tasks come first under
/// "Any time"; timed ones follow in time order with their local time. An
/// overdue task is marked. [now] is passed in, never read.
///
/// With [semanticsPrefix]: `<prefix>.row-<id>` and `<prefix>.complete-<id>`.
class BondDueLane extends StatelessWidget {
  const BondDueLane({
    super.key,
    required this.tasks,
    required this.day,
    required this.now,
    this.onTap,
    this.onComplete,
    this.labels = const TaskLabels(),
    this.semanticsPrefix,
  });

  final List<Task> tasks;
  final DateTime day;
  final DateTime now;
  final ValueChanged<Task>? onTap;
  final ValueChanged<Task>? onComplete;
  final TaskLabels labels;
  final String? semanticsPrefix;

  String? _id(String part, String id) => semanticsPrefix == null ? null : '$semanticsPrefix.$part-$id';

  List<Task> _forDay() {
    final key = dueDateString(day);
    final mine = [
      for (final k in tasks)
        if (k.status != TaskStatus.cancelled && dayFor(k, (u) => u.toLocal()) == key) k,
    ];
    DateTime? at(Task k) => k.dueTime == null ? null : k.dueAt?.toLocal();
    mine.sort((a, b) {
      final x = at(a);
      final y = at(b);
      if (x == null && y == null) return a.title.compareTo(b.title);
      if (x == null) return -1;
      if (y == null) return 1;
      return x.compareTo(y);
    });
    return mine;
  }

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final bl = BondLabels.of(context);
    final list = _forDay();
    if (list.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: BondSpace.s12),
        child: Text(labels.laneEmpty, style: BondText(t).body.copyWith(color: t.muted)),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final k in list)
          Padding(
            key: ValueKey(k.id),
            padding: const EdgeInsets.only(bottom: BondSpace.s8),
            child: _row(context, k, bl),
          ),
      ],
    );
  }

  Widget _row(BuildContext context, Task k, BondLabels bl) {
    final t = BondTokens.of(context);
    final done = k.status != TaskStatus.open;
    final late = isOverdue(k, now);
    final local = k.dueTime == null ? null : k.dueAt?.toLocal();
    final wall = parseDueTime(k.dueTime);
    final timeText = local != null
        ? formatTimeOfDay(local, bl)
        : (wall != null ? formatTimeOfDay(DateTime(2000, 1, 1, wall.hour24, wall.minute), bl) : labels.anytime);
    return BondListRow(
      title: k.title,
      subtitle: late ? labels.overdue : null,
      urgent: late,
      done: done,
      leadingWidth: 72,
      leading: FittedBox(
        fit: BoxFit.scaleDown,
        child: Text(timeText, maxLines: 1, softWrap: false, style: BondText(t).smallStrong),
      ),
      trailing: BondIconButton(
        icon: done ? Icons.check_circle : Icons.radio_button_unchecked,
        label: done ? labels.reopen : labels.complete,
        color: done ? t.positive.base : t.muted,
        onPressed: onComplete == null ? null : () => onComplete!(k),
        semanticsId: _id('complete', k.id),
      ),
      onTap: onTap == null ? null : () => onTap!(k),
      semanticsId: _id('row', k.id),
    );
  }
}
