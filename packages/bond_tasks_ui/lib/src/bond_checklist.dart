import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'bond_check_row.dart';

/// The lines of a task's checklist, each one tickable.
///
/// With [semanticsPrefix] line n (from 0) is `'<prefix>-<n>'`, and its remove
/// button, when [onRemove] is given, `'<prefix>-remove-<n>'`.
class BondChecklist extends StatelessWidget {
  const BondChecklist({
    super.key,
    required this.items,
    required this.onToggle,
    this.onRemove,
    this.labels = const TaskLabels(),
    this.semanticsPrefix,
  });

  final List<ChecklistItem> items;

  /// Called with the line and whether it should now be done.
  final void Function(ChecklistItem item, bool done) onToggle;
  final ValueChanged<ChecklistItem>? onRemove;
  final TaskLabels labels;
  final String? semanticsPrefix;

  String? _id(String part) => semanticsPrefix == null ? null : '$semanticsPrefix-$part';

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 0; i < items.length; i++)
          BondCheckRow(
            checked: items[i].done,
            strikeWhenChecked: true,
            label: items[i].text,
            semanticsId: _id('$i'),
            onChanged: (v) => onToggle(items[i], v),
            trailing: onRemove == null
                ? null
                : BondIconButton(
                    icon: Icons.close,
                    label: labels.removeItem,
                    semanticsId: _id('remove-$i'),
                    onPressed: () => onRemove!(items[i]),
                  ),
          ),
      ],
    );
  }
}
