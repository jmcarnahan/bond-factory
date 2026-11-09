import 'package:flutter/material.dart';

import '../semantics.dart';
import '../tokens/tokens.dart';

/// A tappable region with ink, focus and a minimum tap size. The one place
/// primitives get tap handling from.
class BondPressable extends StatelessWidget {
  const BondPressable({
    super.key,
    required this.child,
    required this.onTap,
    this.borderRadius = BondRadius.r8All,
    this.semanticLabel,
    this.semanticsId,
    this.semanticToggled,
    this.minSize = 0,
    this.color,
    this.focusNode,
    this.exposeChildren = false,
  });

  final Widget child;
  final VoidCallback? onTap;
  final BorderRadius borderRadius;

  /// Names the region as one button for screen readers.
  final String? semanticLabel;

  /// Stable identifier for test drivers.
  final String? semanticsId;

  /// For a switch: whether it is on. Announced as toggled or untoggled.
  final bool? semanticToggled;

  /// Minimum height and width of the hit area.
  final double minSize;
  final Color? color;
  final FocusNode? focusNode;

  /// With a [semanticLabel], keep the children as their own semantics nodes
  /// beside the label instead of hiding them (a row that carries a keyed
  /// status chip). The row is still one button named by the label.
  final bool exposeChildren;

  @override
  Widget build(BuildContext context) {
    final body = Material(
      color: color ?? BondTokens.transparent,
      borderRadius: borderRadius,
      child: InkWell(
        onTap: onTap,
        borderRadius: borderRadius,
        focusNode: focusNode,
        child: minSize > 0
            ? ConstrainedBox(
                constraints:
                    BoxConstraints(minHeight: minSize, minWidth: minSize),
                child: child,
              )
            : child,
      ),
    );
    if (semanticLabel == null) {
      return bondSemantics(id: semanticsId, child: body);
    }
    return bondSemantics(
      id: semanticsId,
      label: semanticLabel,
      button: true,
      enabled: onTap != null,
      toggled: semanticToggled,
      // The ink is excluded below, so this node carries the tap itself.
      onTap: exposeChildren ? null : onTap,
      excludeChildren: !exposeChildren,
      explicitChildNodes: exposeChildren,
      child: body,
    );
  }
}
