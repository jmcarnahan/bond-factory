import 'package:flutter/material.dart';

import '../semantics.dart';
import '../tokens/tokens.dart';
import 'bond_pressable.dart';

/// A surface with a hairline border. [onTap] makes it a button.
class BondCard extends StatelessWidget {
  const BondCard({
    super.key,
    required this.child,
    this.padding = BondSpace.all20,
    this.onTap,
    this.color,
    this.borderColor,
    this.semanticLabel,
    this.semanticsId,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;

  /// Fill; defaults to the surface token.
  final Color? color;

  /// Border; defaults to the line token.
  final Color? borderColor;
  final String? semanticLabel;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final box = Container(
      padding: padding,
      decoration: BoxDecoration(
        color: color ?? t.surface,
        borderRadius: BondRadius.r16All,
        border: Border.all(color: borderColor ?? t.line),
        boxShadow: BondShadows.card,
      ),
      child: child,
    );
    if (onTap == null) {
      return bondSemantics(
          id: semanticsId, explicitChildNodes: true, child: box);
    }
    return BondPressable(
      onTap: onTap,
      borderRadius: BondRadius.r16All,
      semanticLabel: semanticLabel,
      semanticsId: semanticsId,
      child: box,
    );
  }
}
