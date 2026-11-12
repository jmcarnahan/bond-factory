import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'page_scaffold.dart';

/// Under a task row on the Tasks page: checklist, calendar mirror switch, mirror
/// result and the two-step delete. Ids are `<idPrefix>.check-<id>`, `.mirror-<id>`,
/// `.external-<id>`, `.delete-<id>`.
class TaskRowExtra extends StatelessWidget {
  const TaskRowExtra({
    super.key,
    required this.task,
    required this.idPrefix,
    required this.busy,
    required this.onChecklist,
    required this.onMirror,
    required this.onDelete,
  });

  final Task task;
  final String idPrefix;
  final bool busy;
  final void Function(ChecklistItem item, bool done) onChecklist;
  final ValueChanged<bool> onMirror;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final t = task;
    final text = BondText.of(context);
    final tokens = BondTokens.of(context);
    final external = t.externalProvider == null
        ? 'Calendar: ${t.mirrorStatus.wire}'
        : 'Calendar: ${t.externalProvider} ${t.externalEventId ?? ''}'.trim();
    return Padding(
      padding: const EdgeInsets.only(left: BondSpace.s16, top: BondSpace.s4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (t.checklist.isNotEmpty)
            BondChecklist(
              items: t.checklist,
              semanticsPrefix: '$idPrefix.check-${t.id}',
              onToggle: onChecklist,
            ),
          BondCheckRow(
            checked: t.mirrorEnabled,
            label: 'Add to my calendar',
            semanticsId: '$idPrefix.mirror-${t.id}',
            onChanged: busy ? null : onMirror,
          ),
          Row(
            children: [
              Expanded(
                child: t.mirrorEnabled
                    ? labelledText('$idPrefix.external-${t.id}', external, text.caption.copyWith(color: tokens.muted))
                    : Text('Calendar: off', style: text.caption.copyWith(color: tokens.muted)),
              ),
              BondTaskDeleteControl(taskId: t.id, semanticsId: '$idPrefix.delete-${t.id}', onDelete: onDelete),
            ],
          ),
        ],
      ),
    );
  }
}
