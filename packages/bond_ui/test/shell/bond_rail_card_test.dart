import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/shell/bond_rail_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../components/kit_host.dart';

void main() {
  testWidgets('title, trailing and child render; fits phone width', (t) async {
    setPhone(t);
    await pumpKit(t, const BondRailCard(title: 'Notes', trailing: Text('Edit'), child: Text('body')));
    expect(find.text('Notes'), findsOneWidget);
    expect(find.text('Edit'), findsOneWidget);
    expect(find.text('body'), findsOneWidget);
    expect(t.takeException(), isNull);
    await expectNoOverlays(t);
  });

  testWidgets('without a title only the child shows', (t) async {
    await pumpKit(t, const BondRailCard(child: Text('only')));
    expect(find.text('only'), findsOneWidget);
    await expectNoOverlays(t);
  });
}
