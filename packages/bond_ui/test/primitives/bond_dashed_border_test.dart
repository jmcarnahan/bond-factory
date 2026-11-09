import 'package:bond_ui/src/primitives/bond_dashed_border.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  testWidgets('wraps its child and paints in the foreground', (t) async {
    await pumpBond(
      t,
      const BondDashedBorder(
        fill: Color(0xFFEEEEEE),
        child: SizedBox(height: 60, child: Center(child: Text('Empty slot'))),
      ),
    );
    expect(find.text('Empty slot'), findsOneWidget);
    final paint = t.widget<CustomPaint>(find.descendant(
        of: find.byType(BondDashedBorder), matching: find.byType(CustomPaint)));
    expect(paint.foregroundPainter, isNotNull);
    expect(t.getSize(find.byType(BondDashedBorder)).width, 390 - 32);
    await expectNoOverlays(t);
  });

  testWidgets('repaints when colour or radius change', (t) async {
    await pumpBond(t, const BondDashedBorder(child: SizedBox(height: 20)));
    final first = t
        .widget<CustomPaint>(find.descendant(
            of: find.byType(BondDashedBorder),
            matching: find.byType(CustomPaint)))
        .foregroundPainter!;
    await pumpBond(
      t,
      const BondDashedBorder(radius: 4, child: SizedBox(height: 20)),
    );
    final second = t
        .widget<CustomPaint>(find.descendant(
            of: find.byType(BondDashedBorder),
            matching: find.byType(CustomPaint)))
        .foregroundPainter!;
    expect(second.shouldRepaint(first), isTrue);
  });
}
