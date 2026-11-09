import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/components/bond_logo_mark.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'kit_host.dart';

void main() {
  testWidgets('places the given logo at the given size', (t) async {
    await pumpKit(t, const Center(child: BondLogoMark(logo: SizedBox(key: ValueKey('logo'), width: 10, height: 10), size: 40)));
    expect(find.byKey(const ValueKey('logo')), findsOneWidget);
    final box = t.getSize(find.byType(BondLogoMark));
    expect(box, const Size(40, 40));
    await expectNoOverlays(t);
  });

  testWidgets('decorative by default, labelled when asked', (t) async {
    final handle = t.ensureSemantics();
    await pumpKit(t, const BondLogoMark(logo: Icon(Icons.star)));
    expect(find.bySemanticsLabel('Brand'), findsNothing);
    await pumpKit(t, const BondLogoMark(logo: Icon(Icons.star), semanticLabel: 'Brand'));
    expect(find.bySemanticsLabel('Brand'), findsOneWidget);
    await expectNoOverlays(t);
    handle.dispose();
  });
}
