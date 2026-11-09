import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

/// The demo theme: the shared bond theme built from the fallback tokens.
ThemeData buildDemoTheme() => BondTheme.build(BondTokens.fallback);

/// Puts the bond tokens and English labels in scope for the widgets below it.
/// Pages that show bond_ui widgets wrap their content in it, so they render the
/// same whether or not the app theme already carries the tokens.
class DemoScope extends StatelessWidget {
  const DemoScope({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return BondScope(
      tokens: BondTokens.fallback,
      child: BondLabelsScope(labels: BondLabels.defaults, child: child),
    );
  }
}
