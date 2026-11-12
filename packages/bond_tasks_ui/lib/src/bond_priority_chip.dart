import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

/// A small pill for a task's priority: high is danger, low is neutral, normal
/// is info.
class BondPriorityChip extends StatelessWidget {
  const BondPriorityChip({
    super.key,
    required this.priority,
    this.labels = const TaskLabels(),
    this.semanticsId,
  });

  final TaskPriority priority;
  final TaskLabels labels;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final tone = switch (priority) {
      TaskPriority.high => BondToneRole.danger,
      TaskPriority.normal => BondToneRole.info,
      TaskPriority.low => null,
    };
    return BondStatusChip(
      BondStatus(labels.priorityText(priority), tone: tone, icon: priority == TaskPriority.high ? Icons.flag : null),
      semanticsId: semanticsId,
    );
  }
}
