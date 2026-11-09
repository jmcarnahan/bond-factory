import 'package:flutter/material.dart';

import '../tokens/tokens.dart';
import 'bond_theme.dart';

/// The one injection point apps use: wraps [child] in a [Theme] built from
/// [tokens], with the [BondTokens] extension installed so `BondTokens.of`
/// finds it. Use it under `MaterialApp` (via `builder`) or around a test
/// widget.
class BondScope extends StatelessWidget {
  const BondScope({
    super.key,
    required this.child,
    this.tokens = BondTokens.fallback,
    this.brightness = Brightness.light,
  });

  final Widget child;
  final BondTokens tokens;
  final Brightness brightness;

  @override
  Widget build(BuildContext context) => Theme(
        data: BondTheme.build(tokens, brightness: brightness),
        child: child,
      );
}
