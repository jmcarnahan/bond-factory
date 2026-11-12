import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

/// A task's link as a pill: its label (or id). Tapping it calls [onTap]; with
/// [onRemove] a small remove button follows. Ids: `<id>` and `<id>-remove`.
class BondLinkChip extends StatelessWidget {
  const BondLinkChip({
    super.key,
    required this.link,
    this.onTap,
    this.onRemove,
    this.labels = const TaskLabels(),
    this.semanticsId,
  });

  final TaskLink link;
  final VoidCallback? onTap;
  final VoidCallback? onRemove;
  final TaskLabels labels;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final text = (link.label ?? '').isEmpty ? link.id : link.label!;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Flexible(
          child: BondChip(label: text, leading: const Icon(Icons.link, size: BondLayout.iconSm), onTap: onTap, semanticsId: semanticsId),
        ),
        if (onRemove != null)
          BondIconButton(
            icon: Icons.close,
            label: '${labels.removeLink}: $text',
            onPressed: onRemove,
            semanticsId: semanticsId == null ? null : '$semanticsId-remove',
          ),
      ],
    );
  }
}
