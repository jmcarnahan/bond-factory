import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'bond_link_chip.dart';
import 'bond_priority_chip.dart';
import 'task_format.dart';

const int _kMaxLinks = 3;

/// One task: complete button, title, due text, assignee, status and checklist
/// progress. Tapping the body calls [onTap]; the leading button calls
/// [onComplete] (the caller completes or reopens by the task's status).
class BondTaskRow extends StatelessWidget {
  const BondTaskRow({
    super.key,
    required this.task,
    this.onTap,
    this.onComplete,
    this.labels = const TaskLabels(),
    this.semanticsId,
    this.completeSemanticsId,
    this.now,
    this.onLinkTap,
  });

  /// With a [now] the row judges overdue by the one rule (`isOverdue`); without
  /// it the task's own `overdue` flag decides. A normal priority shows no chip.
  final DateTime? now;

  /// Called when a link chip is tapped; null leaves the chips not tappable.
  final ValueChanged<TaskLink>? onLinkTap;
  final Task task;
  final VoidCallback? onTap;
  final VoidCallback? onComplete;
  final TaskLabels labels;
  final String? semanticsId;
  final String? completeSemanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final bl = BondLabels.of(context);
    final done = task.status != TaskStatus.open;
    final due = formatDue(task, bl);
    final late = !done && (now != null ? isOverdue(task, now!) : task.overdue);
    final p = task.priority;
    final progress = task.checklist.isEmpty
        ? null
        : labels.checklistProgress(task.checklistDone, task.checklist.length);
    final details = [
      ?due,
      if (progress != null) '${labels.checklist} $progress',
    ].join('  ·  ');
    final titleStyle = done
        ? text.bodyStrong.copyWith(color: t.muted, decoration: TextDecoration.lineThrough, decorationColor: t.muted)
        : text.bodyStrong;
    final completeLabel = done ? labels.reopen : labels.complete;
    final body = Padding(
      padding: const EdgeInsets.symmetric(vertical: BondSpace.s8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(task.title, maxLines: 2, overflow: TextOverflow.ellipsis, style: titleStyle),
          if (details.isNotEmpty)
            Text(
              details,
              style: text.small.copyWith(color: late ? t.danger.press : t.body),
            ),
          BondSpace.h4,
          Wrap(
            spacing: BondSpace.s8,
            runSpacing: BondSpace.s4,
            children: [
              if (task.assignedUserId != null) BondPersonChip(label: task.assigneeName ?? labels.unassigned, slot: 0),
              if (p != null && p != TaskPriority.normal && !done) BondPriorityChip(priority: p, labels: labels),
              if (late) BondStatusChip(BondStatus(labels.overdue, tone: BondToneRole.danger)),
              if (done) BondStatusChip(BondStatus(labels.statusText(task.status), tone: BondToneRole.positive)),
            ],
          ),
        ],
      ),
    );
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: BondSpace.s4),
      decoration: BoxDecoration(
        color: late ? t.danger.wash : t.surface,
        borderRadius: BondRadius.r12All,
        border: Border.all(color: late ? t.danger.soft : t.line),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          BondIconButton(
            icon: done ? Icons.check_circle : Icons.radio_button_unchecked,
            label: completeLabel,
            color: done ? t.positive.base : t.muted,
            semanticsId: completeSemanticsId,
            onPressed: onComplete,
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                BondPressable(
                  onTap: onTap,
                  semanticLabel: task.title,
                  semanticsId: semanticsId,
                  child: body,
                ),
                // Outside the tappable body so each chip is its own control.
                if (task.links.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(bottom: BondSpace.s8),
                    child: Wrap(
                      spacing: BondSpace.s8,
                      runSpacing: BondSpace.s4,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        for (var n = 0; n < task.links.length && n < _kMaxLinks; n++)
                          BondLinkChip(
                            link: task.links[n],
                            labels: labels,
                            onTap: onLinkTap == null ? null : () => onLinkTap!(task.links[n]),
                            semanticsId: semanticsId == null ? null : '$semanticsId-link-$n',
                          ),
                        if (task.links.length > _kMaxLinks)
                          Text(labels.moreLinksText(task.links.length - _kMaxLinks), style: text.small.copyWith(color: t.muted)),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
