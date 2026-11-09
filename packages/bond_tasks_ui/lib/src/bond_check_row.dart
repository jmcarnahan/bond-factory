import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

/// A tick box with a text, the whole row one toggle button. Used for checklist
/// lines and the mirror switch.
class BondCheckRow extends StatelessWidget {
  const BondCheckRow({
    super.key,
    required this.checked,
    required this.label,
    required this.onChanged,
    this.semanticsId,
    this.trailing,
    this.strikeWhenChecked = false,
  });

  final bool checked;
  final String label;

  /// Null makes the row read-only.
  final ValueChanged<bool>? onChanged;
  final String? semanticsId;

  /// Shown after the text, outside the toggle's hit area.
  final Widget? trailing;

  /// Draws the text muted and struck through while checked (a finished
  /// checklist line). A switch such as the mirror toggle leaves this off.
  final bool strikeWhenChecked;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final style = checked && strikeWhenChecked
        ? text.body.copyWith(color: t.muted, decoration: TextDecoration.lineThrough, decorationColor: t.muted)
        : text.body;
    final on = onChanged;
    return Row(
      children: [
        Expanded(
          child: BondPressable(
            onTap: on == null ? null : () => on(!checked),
            semanticLabel: label,
            semanticsId: semanticsId,
            semanticToggled: checked,
            minSize: BondLayout.minTap,
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: BondSpace.s4),
              child: Row(
                children: [
                  Icon(
                    checked ? Icons.check_box : Icons.check_box_outline_blank,
                    size: BondLayout.icon,
                    color: checked ? t.positive.base : t.muted,
                  ),
                  BondSpace.w8,
                  Expanded(child: Text(label, style: style)),
                ],
              ),
            ),
          ),
        ),
        ?trailing,
      ],
    );
  }
}
