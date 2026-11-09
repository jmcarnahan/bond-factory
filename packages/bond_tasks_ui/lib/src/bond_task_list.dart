import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'bond_task_row.dart';
import 'task_format.dart';

/// Tasks in sections: overdue, today, upcoming, no date, done. Empty sections
/// are left out. Shows a loading state while [tasks] is null and no [error]
/// is set, an error state with retry for [error], and an empty state for none.
///
/// [today] is the wall date of the person (pass the app clock; the list never
/// reads the device clock). With [semanticsPrefix] a row is
/// `'<prefix>.row-<id>'` and its complete button `'<prefix>.complete-<id>'`.
/// [rowExtra] puts a widget under a row (a checklist, a delete control).
class BondTaskList extends StatelessWidget {
  const BondTaskList({
    super.key,
    required this.tasks,
    required this.today,
    this.error,
    this.onRetry,
    this.onTap,
    this.onComplete,
    this.rowExtra,
    this.labels = const TaskLabels(),
    this.semanticsPrefix,
  });

  final List<Task>? tasks;
  final DateTime today;
  final String? error;
  final VoidCallback? onRetry;
  final ValueChanged<Task>? onTap;

  /// Called for the complete button of any row, whether the task is open
  /// (complete it) or done (reopen it).
  final ValueChanged<Task>? onComplete;
  final Widget Function(BuildContext context, Task task)? rowExtra;
  final TaskLabels labels;
  final String? semanticsPrefix;

  String? _id(String part, String id) => semanticsPrefix == null ? null : '$semanticsPrefix.$part-$id';

  String _title(TaskSection s) => switch (s) {
        TaskSection.overdue => labels.sectionOverdue,
        TaskSection.today => labels.sectionToday,
        TaskSection.upcoming => labels.sectionUpcoming,
        TaskSection.noDate => labels.sectionNoDate,
        TaskSection.done => labels.sectionDone,
      };

  @override
  Widget build(BuildContext context) {
    final list = tasks;
    if (error != null) {
      return BondErrorState(
        message: error,
        onRetry: onRetry,
        semanticsId: semanticsPrefix == null ? null : '$semanticsPrefix.list-error',
        retrySemanticsId: semanticsPrefix == null ? null : '$semanticsPrefix.list-retry',
      );
    }
    if (list == null) return BondLoadingState(label: labels.loading);
    if (list.isEmpty) return BondEmptyState(title: labels.empty, message: labels.emptyMessage);
    final todayText = dueDateString(today);
    final t = BondTokens.of(context);
    final text = BondText(t);
    final children = <Widget>[];
    for (final s in TaskSection.values) {
      final inSection = [for (final k in list) if (sectionOf(k, todayText) == s) k];
      if (inSection.isEmpty) continue;
      children.add(Padding(
        padding: const EdgeInsets.only(top: BondSpace.s16, bottom: BondSpace.s8),
        child: Text('${_title(s)} (${inSection.length})', style: text.eyebrow.copyWith(color: t.muted)),
      ));
      for (final k in inSection) {
        children.add(Padding(
          padding: const EdgeInsets.only(bottom: BondSpace.s8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              BondTaskRow(
                task: k,
                labels: labels,
                semanticsId: _id('row', k.id),
                completeSemanticsId: _id('complete', k.id),
                onTap: onTap == null ? null : () => onTap!(k),
                onComplete: onComplete == null ? null : () => onComplete!(k),
              ),
              if (rowExtra != null) rowExtra!(context, k),
            ],
          ),
        ));
      }
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, mainAxisSize: MainAxisSize.min, children: children);
  }
}
