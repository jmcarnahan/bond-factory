import 'package:flutter/material.dart';

import '../tokens/tokens.dart';
import 'bond_pressable.dart';

/// An icon-only (or icon plus visible label) button. A [label] is required:
/// it is the accessible name, and with [showLabel] it is also drawn. There is
/// no hover text.
class BondIconButton extends StatelessWidget {
  const BondIconButton({
    super.key,
    required this.icon,
    required this.label,
    required this.onPressed,
    this.showLabel = false,
    this.color,
    this.semanticsId,
  });

  final IconData icon;
  final String label;
  final VoidCallback? onPressed;
  final bool showLabel;

  /// Icon colour; defaults to the ink token.
  final Color? color;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    return BondPressable(
      onTap: onPressed,
      semanticLabel: label,
      semanticsId: semanticsId,
      borderRadius: BondRadius.r12All,
      minSize: BondLayout.minTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(
            horizontal: BondSpace.s12, vertical: BondSpace.s8),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon,
                size: BondLayout.icon,
                color: onPressed == null ? t.muted : (color ?? t.ink)),
            if (showLabel) ...[
              BondSpace.w8,
              Text(label, style: BondText(t).smallStrong),
            ],
          ],
        ),
      ),
    );
  }
}
