import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/shell/bond_right_rail.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../components/kit_host.dart';

void main() {
  testWidgets('has the rail width and shows title and content', (t) async {
    setWideScreen(t);
    await pumpKit(
      t,
      const Align(alignment: Alignment.topRight, child: BondRightRail(title: 'Details', trailing: Text('x'), child: Text('content'))),
    );
    expect(find.text('Details'), findsOneWidget);
    expect(find.text('content'), findsOneWidget);
    expect(t.getSize(find.byType(BondRightRail)).width, 360);
    await expectNoOverlays(t);
  });
}
