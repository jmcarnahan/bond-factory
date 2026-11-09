import 'package:flutter/material.dart';

import '../tokens/tokens.dart';

/// A circle with initials.
class BondAvatar extends StatelessWidget {
  const BondAvatar({
    super.key,
    required this.initials,
    this.size = BondLayout.controlSm,
    this.color,
    this.foreground,
  });

  final String initials;
  final double size;

  /// Fill; defaults to the ink token.
  final Color? color;

  /// Initials colour; defaults to the on-fill token.
  final Color? foreground;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: color ?? t.ink, shape: BoxShape.circle),
      child: Text(
        initials,
        style: BondText(t).style(BondText.label13, BondText.semibold,
            color: foreground ?? t.onFill),
      ),
    );
  }
}
