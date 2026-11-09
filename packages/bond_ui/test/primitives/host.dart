import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/theme/theme.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

export 'package:bond_test_support/bond_test_support.dart'
    show expectNoOverlays, setPhone, setWideScreen;

/// Pumps [child] on a 390 px phone with the fallback tokens installed. The
/// child gets the full width (a scroll view gives unbounded height), so any
/// horizontal overflow fails the test.
Future<void> pumpBond(
  WidgetTester t,
  Widget child, {
  bool phone = true,
  Brightness brightness = Brightness.light,
}) async {
  if (phone) setPhone(t);
  await pumpApp(
    t,
    SingleChildScrollView(
      padding: BondSpace.all16,
      child: child,
    ),
    theme: BondTheme.build(BondTokens.fallback, brightness: brightness),
  );
}
