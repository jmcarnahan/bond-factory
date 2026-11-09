import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/theme/theme.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Pumps [child] in a MaterialApp whose theme carries [BondTokens.fallback].
Future<void> pumpKit(WidgetTester t, Widget child) =>
    pumpApp(t, child, theme: BondTheme.build(BondTokens.fallback));

/// True when a semantics node with this identifier is on screen.
Finder byId(String id) => find.bySemanticsIdentifier(id);
