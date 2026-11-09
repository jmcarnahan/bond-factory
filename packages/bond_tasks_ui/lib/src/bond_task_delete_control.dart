import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

/// A delete button that asks again in place (no dialog): tap, then Confirm or
/// Cancel. With [semanticsId] the button is the id and the two steps are
/// `'<id>-confirm'` and `'<id>-cancel'`.
class BondTaskDeleteControl extends StatelessWidget {
  const BondTaskDeleteControl({
    super.key,
    required this.taskId,
    required this.onDelete,
    this.labels = const TaskLabels(),
    this.semanticsId,
  });

  final String taskId;
  final VoidCallback onDelete;
  final TaskLabels labels;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    return BondConfirm(
      identity: taskId,
      semanticsId: semanticsId,
      onConfirm: onDelete,
      trigger: (arm) => BondIconButton(
        icon: Icons.delete_outline,
        label: labels.delete,
        color: t.danger.press,
        semanticsId: semanticsId,
        onPressed: arm,
      ),
    );
  }
}
