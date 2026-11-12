import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

/// An inline banner for a task at a notice stage: "Due soon", "Due now" or
/// "Overdue", the task title, a "Last reminder" line when [last], and one
/// button per action in [actions] (Done, Snooze, Cancel task). It is a plain
/// container in the page flow, never a popup. Stage [TaskStage.none] draws
/// nothing, as does [TaskStage.upcoming] (a task due far ahead is not news).
///
/// With [semanticsPrefix]: `<prefix>.banner` and `<prefix>.banner-<action>`.
class BondStageBanner extends StatelessWidget {
  const BondStageBanner({
    super.key,
    required this.task,
    required this.stage,
    required this.onAction,
    this.last = false,
    this.actions = const [NoticeAction.done, NoticeAction.snooze, NoticeAction.cancel],
    this.labels = const TaskLabels(),
    this.semanticsPrefix,
  });

  final Task task;
  final TaskStage stage;
  final bool last;
  final List<NoticeAction> actions;
  final ValueChanged<NoticeAction> onAction;
  final TaskLabels labels;
  final String? semanticsPrefix;

  String? _stageText() => switch (stage) {
        TaskStage.none || TaskStage.upcoming => null,
        TaskStage.close => labels.stageDueSoon,
        TaskStage.due => labels.stageDueNow,
        TaskStage.past => labels.stageOverdue,
      };

  @override
  Widget build(BuildContext context) {
    final head = _stageText();
    if (head == null) return const SizedBox.shrink();
    final t = BondTokens.of(context);
    final text = BondText(t);
    final tone = switch (stage) {
      TaskStage.past => BondToneRole.danger,
      TaskStage.due => BondToneRole.caution,
      _ => BondToneRole.info,
    };
    final c = t.colorsFor(tone);
    String actionLabel(NoticeAction a) => switch (a) {
          NoticeAction.done => labels.actionDone,
          NoticeAction.snooze => labels.actionSnooze,
          NoticeAction.cancel => labels.actionCancelTask,
        };
    final id = semanticsPrefix == null ? null : '$semanticsPrefix.banner';
    return Semantics(
      identifier: id,
      container: true,
      explicitChildNodes: true,
      child: Container(
        padding: BondSpace.all16,
        decoration: BoxDecoration(
          color: c.background,
          borderRadius: BondRadius.r12All,
          border: Border.all(color: c.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(head, style: text.bodyStrong.copyWith(color: c.foreground)),
            Text(task.title, maxLines: 2, overflow: TextOverflow.ellipsis, style: text.body),
            if (last) Text(labels.lastReminder, style: text.small.copyWith(color: c.foreground)),
            if (actions.isNotEmpty) ...[
              BondSpace.h12,
              Wrap(
                spacing: BondSpace.s8,
                runSpacing: BondSpace.s8,
                children: [
                  for (final a in actions)
                    BondButton(
                      label: actionLabel(a),
                      variant: switch (a) {
                        NoticeAction.done => BondButtonVariant.primary,
                        NoticeAction.snooze => BondButtonVariant.secondary,
                        NoticeAction.cancel => BondButtonVariant.quiet,
                      },
                      onPressed: () => onAction(a),
                      semanticsId: id == null ? null : '$id-${a.wire}',
                    ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}
