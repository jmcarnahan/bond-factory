import 'package:bond_ui/src/primitives/bond_text_field.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  testWidgets('shows the label and reports typing', (t) async {
    final sem = t.ensureSemantics();
    final typed = <String>[];
    final submitted = <String>[];
    await pumpBond(
      t,
      BondTextField(
        label: 'Name',
        hint: 'Full name',
        onChanged: typed.add,
        onSubmitted: submitted.add,
        semanticsId: 'name',
      ),
    );
    expect(find.text('Name'), findsOneWidget);
    expect(find.bySemanticsIdentifier('name'), findsOneWidget);
    await t.enterText(find.byType(TextField), 'Ada');
    await t.testTextInput.receiveAction(TextInputAction.done);
    await t.pump();
    expect(typed, ['Ada']);
    expect(submitted, ['Ada']);
    await expectNoOverlays(t);
    sem.dispose();
  });

  testWidgets('the validation message shows inline under the field', (t) async {
    await pumpBond(
      t,
      const BondTextField(label: 'Email', errorText: 'Enter a valid email'),
    );
    expect(find.text('Enter a valid email'), findsOneWidget);
    final field = t.getBottomLeft(find.byType(TextField));
    expect(t.getTopLeft(find.text('Enter a valid email')).dy,
        greaterThanOrEqualTo(field.dy - 24));
    await expectNoOverlays(t);
  });

  testWidgets('the counter turns danger past the limit and never cuts', (t) async {
    await pumpBond(t, const BondTextField(label: 'Note', maxLength: 5));
    await t.enterText(find.byType(TextField), 'abcdefgh');
    await t.pump();
    final counter = t.widget<Text>(find.text('8/5'));
    expect(counter.style!.color, BondTokens.fallback.danger.base);
    expect(t.widget<TextField>(find.byType(TextField)).controller, isNull);
    expect(find.text('abcdefgh'), findsOneWidget);
  });

  testWidgets('obscure, disabled and prefix render', (t) async {
    await pumpBond(
      t,
      const Column(children: [
        BondTextField(label: 'Secret', obscureText: true),
        BondTextField(label: 'Locked', enabled: false),
        BondTextField(label: 'With prefix', prefix: Icon(Icons.person)),
      ]),
    );
    expect(find.byIcon(Icons.person), findsOneWidget);
    expect(
        t.widget<TextField>(find.byType(TextField).at(1)).enabled, isFalse);
  });

  testWidgets('search field has a magnifier, id and submit unfocuses', (t) async {
    final sem = t.ensureSemantics();
    final submitted = <String>[];
    await pumpBond(
      t,
      BondSearchField(
        hint: 'Search people',
        onSubmitted: submitted.add,
        semanticsId: 'search',
      ),
    );
    expect(find.byIcon(Icons.search), findsOneWidget);
    expect(find.bySemanticsIdentifier('search'), findsOneWidget);
    await t.enterText(find.byType(TextField), 'ann');
    await t.testTextInput.receiveAction(TextInputAction.search);
    await t.pump();
    expect(submitted, ['ann']);
    await expectNoOverlays(t);
    sem.dispose();
  });

  group('error message', () {
    Future<void> show(WidgetTester t, {String? id, String? error}) =>
        pumpBond(t, BondTextField(label: 'Name', errorText: error, semanticsId: id));

    bool redBorder(WidgetTester t) {
      final d = t.widget<InputDecorator>(find.byType(InputDecorator)).decoration;
      return d.errorText != null || d.error != null;
    }

    testWidgets('with an id and an error: its own live-region node carrying the message', (t) async {
      final sem = t.ensureSemantics();
      await show(t, id: 'name', error: 'Required');
      final node = t.getSemantics(find.bySemanticsIdentifier('name-error'));
      expect(node.label, 'Required');
      expect(node.flagsCollection.isLiveRegion, isTrue);
      expect(find.text('Required'), findsOneWidget, reason: 'drawn once');
      expect(redBorder(t), isTrue, reason: 'the field still shows the error state');
      sem.dispose();
    });

    testWidgets('with an id and no error: no error node', (t) async {
      final sem = t.ensureSemantics();
      await show(t, id: 'name');
      expect(find.bySemanticsIdentifier('name-error'), findsNothing);
      expect(redBorder(t), isFalse);
      sem.dispose();
    });

    testWidgets('without an id: Flutter\'s own error text is used, as before', (t) async {
      await show(t, error: 'Required');
      final d = t.widget<InputDecorator>(find.byType(InputDecorator)).decoration;
      expect(d.errorText, 'Required');
      expect(d.error, isNull);
      expect(find.text('Required'), findsOneWidget);
    });
  });
}
