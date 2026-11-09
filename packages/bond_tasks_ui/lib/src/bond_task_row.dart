import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'task_format.dart';

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
  });

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
    final late = task.overdue && !done;
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
            child: BondPressable(
              onTap: onTap,
              semanticLabel: task.title,
              semanticsId: semanticsId,
              child: body,
            ),
          ),
        ],
      ),
    );
  }
}
