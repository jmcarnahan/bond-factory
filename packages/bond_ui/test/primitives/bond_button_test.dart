import 'package:bond_ui/src/primitives/bond_button.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  testWidgets('tap fires, id and label are exposed', (t) async {
    final sem = t.ensureSemantics();
    var taps = 0;
    await pumpBond(
      t,
      BondButton(label: 'Save', onPressed: () => taps++, semanticsId: 'save'),
    );
    expect(find.bySemanticsIdentifier('save'), findsOneWidget);
    await t.tap(find.text('Save'));
    await t.pump();
    expect(taps, 1);
    await expectNoOverlays(t);
    sem.dispose();
  });

  testWidgets('disabled and loading buttons do not fire', (t) async {
    var taps = 0;
    await pumpBond(
      t,
      Column(children: [
        const BondButton(label: 'Off', onPressed: null),
        BondButton(label: 'Busy', loading: true, onPressed: () => taps++),
      ]),
    );
    await t.tap(find.text('Off'));
    await t.tap(find.text('Busy'));
    await t.pump();
    expect(taps, 0);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });

  testWidgets('every variant and size renders at phone width', (t) async {
    await pumpBond(
      t,
      Column(children: [
        for (final v in BondButtonVariant.values)
          for (final s in BondButtonSize.values)
            BondButton(
              label: '${v.name} ${s.name}',
              variant: v,
              size: s,
              icon: Icons.check,
              expand: true,
              onPressed: () {},
            ),
      ]),
    );
    expect(find.byType(BondButton), findsNWidgets(8));
  });

  testWidgets('a long label wraps instead of overflowing', (t) async {
    await pumpBond(
      t,
      BondButton(
        label: 'A very long label written by the server that must wrap '
            'rather than be cut off at the edge of the screen',
        wrapLabel: true,
        expand: true,
        onPressed: () {},
      ),
    );
    expect(t.takeException(), isNull);
  });

  testWidgets('selected shows and announces the chosen state', (t) async {
    final sem = t.ensureSemantics();
    await pumpBond(
      t,
      BondButton(label: 'Pick', selected: true, onPressed: () {}),
    );
    expect(find.text('Pick'), findsOneWidget);
    expect(t.getSemantics(find.bySemanticsLabel('Pick')),
        matchesSemantics(
          label: 'Pick',
          isButton: true,
          isSelected: true,
          isEnabled: true,
          hasEnabledState: true,
          hasSelectedState: true,
          hasTapAction: true,
        ));
    sem.dispose();
  });
}
