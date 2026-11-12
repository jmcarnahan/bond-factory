import 'dart:math' as math;

import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'bond_task_row.dart';
import 'task_format.dart';

/// The day view: Overdue, Today, No date and Done today, each with its count.
/// Empty sections are left out; with nothing at all an empty line shows.
/// [now] decides the overdue mark (pass the app clock, never read here).
///
/// With [semanticsPrefix]: rows `<prefix>.row-<id>`, complete buttons
/// `<prefix>.complete-<id>`, headers `<prefix>.section-<name>`.
class BondTodayList extends StatelessWidget {
  const BondTodayList({
    super.key,
    required this.today,
    required this.now,
    this.onTap,
    this.onComplete,
    this.labels = const TaskLabels(),
    this.semanticsPrefix,
    this.onLinkTap,
  });

  final TaskToday today;
  final DateTime now;
  final ValueChanged<Task>? onTap;

  /// Called for the complete button of any row (complete an open task, reopen
  /// a done one).
  final ValueChanged<Task>? onComplete;
  final TaskLabels labels;
  final String? semanticsPrefix;

  /// Called when a link chip on a row is tapped.
  final ValueChanged<TaskLink>? onLinkTap;

  String? _id(String part, [String? id]) =>
      semanticsPrefix == null ? null : '$semanticsPrefix.$part${id == null ? '' : '-$id'}';

  /// Puts each task in exactly one section by the one overdue rule at [now]:
  /// an open task past its instant is Overdue even if the day view was built a
  /// minute before; one listed as overdue that is not past yet is Today.
  ({List<Task> overdue, List<Task> today, List<Task> undated, List<Task> done}) _derive() {
    final seen = <String>{};
    final overdue = <Task>[], todayL = <Task>[], undated = <Task>[], done = <Task>[];
    void put(Task k, List<Task> own, {bool wasOverdue = false}) {
      if (!seen.add(k.id)) return;
      if (k.status != TaskStatus.open) {
        done.add(k);
      } else if (isOverdue(k, now)) {
        overdue.add(k);
      } else if (k.dueDate != null && (dayFor(k, (u) => u.toLocal()) ?? k.dueDate!).compareTo(dueDateString(now.toLocal())) <= 0) {
        // Open, not overdue, day today or earlier: Today (never in no section).
        todayL.add(k);
      } else {
        (wasOverdue && own == today.overdue ? todayL : own == today.undated ? undated : own == today.doneToday ? done : todayL)
            .add(k);
      }
    }

    for (final k in today.overdue) {
      put(k, today.overdue, wasOverdue: true);
    }
    for (final k in today.today) {
      put(k, today.today);
    }
    for (final k in today.undated) {
      put(k, today.undated);
    }
    for (final k in today.doneToday) {
      put(k, today.doneToday);
    }
    return (overdue: overdue, today: todayL, undated: undated, done: done);
  }

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final d = _derive();
    final moved = d.overdue.length != today.overdue.length ||
        d.today.length != today.today.length ||
        d.undated.length != today.undated.length ||
        d.done.length != today.doneToday.length;
    // The server's counts only apply while no task changed section.
    int count(int server, List<Task> own) => moved ? own.length : math.max(server, own.length);
    final sections = <(String, String, List<Task>, int)>[
      ('overdue', labels.sectionOverdue, d.overdue, count(today.counts.overdue, d.overdue)),
      ('today', labels.sectionToday, d.today, count(today.counts.today, d.today)),
      ('undated', labels.sectionUndated, d.undated, count(today.counts.undated, d.undated)),
      ('done-today', labels.sectionDoneToday, d.done, count(today.counts.doneToday, d.done)),
    ];
    final children = <Widget>[];
    for (final (name, title, tasks, count) in sections) {
      if (tasks.isEmpty) continue;
      children.add(Padding(
        padding: const EdgeInsets.only(top: BondSpace.s16, bottom: BondSpace.s8),
        child: Semantics(
          identifier: _id('section', name),
          header: true,
          child: Text('$title ($count)', style: text.eyebrow.copyWith(color: t.muted)),
        ),
      ));
      for (final k in tasks) {
        children.add(Padding(
          key: ValueKey(k.id),
          padding: const EdgeInsets.only(bottom: BondSpace.s8),
          child: BondTaskRow(
            task: k,
            now: now,
            onLinkTap: onLinkTap,
            labels: labels,
            semanticsId: _id('row', k.id),
            completeSemanticsId: _id('complete', k.id),
            onTap: onTap == null ? null : () => onTap!(k),
            onComplete: onComplete == null ? null : () => onComplete!(k),
          ),
        ));
      }
    }
    if (children.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: BondSpace.s16),
        child: Text(labels.todayEmpty, key: const ValueKey('today-empty'), style: text.body.copyWith(color: t.muted)),
      );
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, mainAxisSize: MainAxisSize.min, children: children);
  }
}
