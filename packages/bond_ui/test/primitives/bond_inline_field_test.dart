import 'package:bond_ui/src/primitives/bond_inline_field.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  testWidgets('commits the trimmed text on submit, once', (t) async {
    final sem = t.ensureSemantics();
    final committed = <String>[];
    await pumpBond(
      t,
      BondInlineField(
        value: '10',
        onCommit: committed.add,
        width: 120,
        semanticLabel: 'Quantity',
        semanticsId: 'qty',
        suffix: '%',
      ),
    );
    expect(find.bySemanticsIdentifier('qty'), findsOneWidget);
    await t.enterText(find.byType(TextField), ' 25 ');
    await t.testTextInput.receiveAction(TextInputAction.done);
    await t.pump();
    expect(committed, ['25']);
    // Leaving the field right after does not commit the same text again.
    FocusManager.instance.primaryFocus?.unfocus();
    await t.pump();
    expect(committed, ['25']);
    await expectNoOverlays(t);
    sem.dispose();
  });

  testWidgets('does not commit an unchanged value', (t) async {
    final committed = <String>[];
    await pumpBond(
      t,
      BondInlineField(value: '10', onCommit: committed.add),
    );
    await t.enterText(find.byType(TextField), '10');
    await t.testTextInput.receiveAction(TextInputAction.done);
    await t.pump();
    expect(committed, isEmpty);
  });

  testWidgets('commits when focus leaves', (t) async {
    final committed = <String>[];
    await pumpBond(
      t,
      Column(children: [
        BondInlineField(value: '1', onCommit: committed.add),
        const TextField(key: ValueKey('other')),
      ]),
    );
    await t.tap(find.byType(TextField).first);
    await t.enterText(find.byType(TextField).first, '7');
    await t.tap(find.byKey(const ValueKey('other')));
    await t.pump();
    expect(committed, ['7']);
  });

  testWidgets('numeric fields filter letters', (t) async {
    await pumpBond(t, BondInlineField(value: '', onCommit: (_) {}));
    await t.enterText(find.byType(TextField), 'ab12.5');
    expect(t.widget<TextField>(find.byType(TextField)).controller!.text, '12.5');
  });

  testWidgets('follows an outside value when not focused', (t) async {
    await pumpBond(t, BondInlineField(value: 'a', onCommit: (_) {}));
    await pumpBond(t, BondInlineField(value: 'b', onCommit: (_) {}));
    await t.pump();
    expect(t.widget<TextField>(find.byType(TextField)).controller!.text, 'b');
  });
}
