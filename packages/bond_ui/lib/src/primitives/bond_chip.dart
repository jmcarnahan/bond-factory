import 'package:flutter/material.dart';

import '../semantics.dart';
import '../tokens/tokens.dart';
import 'bond_pressable.dart';

/// A pill used for filters and choices. Tapping toggles [selected] in the
/// caller's state. The label wraps rather than being cut.
class BondChip extends StatelessWidget {
  const BondChip({
    super.key,
    required this.label,
    this.selected = false,
    this.onTap,
    this.leading,
    this.count,
    this.countLabel,
    this.tone,
    this.semanticsId,
  });

  final String label;
  final bool selected;
  final VoidCallback? onTap;
  final Widget? leading;
  final int? count;

  /// Replaces the plain [count] text (for example `200+`); [count] still
  /// decides whether a count shows.
  final String? countLabel;

  /// Null is neutral.
  final BondToneRole? tone;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final c = t.colorsFor(tone);
    final plain = tone == null || selected;
    final Color bg = selected ? t.ink : t.surface;
    final Color fg = selected ? t.onFill : c.foreground;
    final Color border = selected ? t.ink : t.lineStrong;
    final chip = Container(
      constraints: const BoxConstraints(minHeight: BondLayout.controlSm),
      padding: const EdgeInsets.symmetric(
          horizontal: BondSpace.s12, vertical: BondSpace.s4),
      decoration: BoxDecoration(
        color: plain ? bg : c.background,
        borderRadius: BondRadius.pillAll,
        border: Border.all(color: plain ? border : c.border),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (leading != null) ...[leading!, BondSpace.w8],
          Flexible(
            child: Text(label,
                style: BondText(t)
                    .style(BondText.small14, BondText.medium, color: fg)),
          ),
          if (count != null) ...[
            BondSpace.w8,
            Text(countLabel ?? '$count',
                style: BondText(t).style(BondText.label13, BondText.semibold,
                    color: selected ? t.onFill : t.muted)),
          ],
        ],
      ),
    );
    // With a count the label and the count are spoken together, in order.
    final spoken = count == null ? null : '$label, ${countLabel ?? count}';
    if (onTap == null) {
      return bondSemantics(
        id: semanticsId,
        label: spoken,
        excludeChildren: spoken != null,
        child: chip,
      );
    }
    return bondSemantics(
      id: semanticsId,
      label: spoken,
      button: true,
      selected: selected,
      onTap: onTap,
      child: BondPressable(
        onTap: onTap,
        borderRadius: BondRadius.pillAll,
        child: spoken == null ? chip : ExcludeSemantics(child: chip),
      ),
    );
  }
}
