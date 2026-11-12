import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

export 'package:bond_test_support/bond_test_support.dart' show expectNoOverlays;

final DateTime kToday = DateTime(2026, 3, 12);

/// Pumps [child] in a scrolling page at the wide (1280) or phone (390) width.
Future<void> pumpAt(WidgetTester t, Widget child, {bool phone = false}) async {
  if (phone) {
    setPhone(t);
  } else {
    setWideScreen(t);
  }
  await pumpApp(
    t,
    SingleChildScrollView(padding: const EdgeInsets.all(16), child: child),
    theme: BondTheme.build(BondTokens.fallback),
  );
}

/// Both widths: no overlay, no layout exception.
Future<void> expectCleanAtBothWidths(
  WidgetTester t,
  Widget Function() build,
) async {
  for (final phone in [false, true]) {
    await pumpAt(t, build(), phone: phone);
    await expectNoOverlays(t);
    expect(t.takeException(), isNull, reason: phone ? 'at 390' : 'at 1280');
  }
}
