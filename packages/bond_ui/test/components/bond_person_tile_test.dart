import 'package:bond_ui/src/components/bond_person_tile.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../primitives/host.dart';

void main() {
  for (final phone in [true, false]) {
    testWidgets('name, subtitle, initials, trailing and tap, phone=$phone', (t) async {
      final sem = t.ensureSemantics();
      var taps = 0;
      await pumpBond(
        t,
        BondPersonTile(
          name: 'Alex Rivera',
          subtitle: 'Crew lead',
          trailing: const Text('3'),
          onTap: () => taps++,
          semanticsId: 'pt',
        ),
        phone: phone,
      );
      expect(find.text('AR'), findsOneWidget);
      expect(find.text('Crew lead'), findsOneWidget);
      expect(find.text('3'), findsOneWidget);
      expect(find.bySemanticsIdentifier('pt'), findsOneWidget);
      await t.tap(find.text('Alex Rivera'));
      expect(taps, 1);
      await expectNoOverlays(t);
      expect(t.takeException(), isNull);
      sem.dispose();
    });
  }

  test('initialsOf handles one word, blanks and extra spaces', () {
    expect(BondPersonTile.initialsOf('  mia  '), 'M');
    expect(BondPersonTile.initialsOf(''), '?');
    expect(BondPersonTile.initialsOf('a b c'), 'AB');
  });
}
