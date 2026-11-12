import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'bond_link_picker_row.dart';

/// The priority choice (none, low, normal, high) and the links of the task
/// form. The links picker shows only when [onSearchLinks] is given.
class BondTaskFormExtras extends StatelessWidget {
  const BondTaskFormExtras({
    super.key,
    required this.labels,
    required this.priority,
    required this.onPriority,
    required this.links,
    required this.onLinks,
    required this.onSearchLinks,
    required this.idOf,
  });

  final TaskLabels labels;
  final TaskPriority? priority;
  final ValueChanged<TaskPriority?> onPriority;
  final List<TaskLink> links;
  final ValueChanged<List<TaskLink>> onLinks;
  final Future<List<TaskLink>> Function(String kind, String query)? onSearchLinks;
  final String? Function(String part) idOf;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(labels.priority, style: BondText(t).smallStrong),
        BondSpace.h4,
        BondSegmented<int>(
          segments: [
            BondSegment(0, labels.noPriority),
            for (final p in TaskPriority.values) BondSegment(p.wire, labels.priorityText(p)),
          ],
          value: priority?.wire ?? 0,
          onChanged: (v) => onPriority(TaskPriority.fromWire(v)),
          semanticsId: idOf('priority'),
        ),
        if (onSearchLinks != null) ...[
          BondSpace.h12,
          BondLinkPickerRow(
            links: links,
            onSearch: onSearchLinks!,
            onChanged: onLinks,
            labels: labels,
            semanticsId: idOf('links'),
          ),
        ],
      ],
    );
  }
}
