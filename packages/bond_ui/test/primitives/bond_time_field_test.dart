import 'package:bond_ui/src/primitives/bond_time_field.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  test('BondTime converts between 24h and clock face', () {
    const t = BondTime(hour24: 0, minute: 5);
    expect(t.hour12, 12);
    expect(t.isPm, isFalse);
    expect(BondTime.from12(12, 0, pm: true).hour24, 12);
    expect(BondTime.from12(12, 0, pm: false).hour24, 0);
    expect(BondTime.from12(3, 30, pm: true), const BondTime(hour24: 15, minute: 30));
    expect(const BondTime(hour24: 13, minute: 0).hour12, 1);
    expect(t == const BondTime(hour24: 0, minute: 5), isTrue);
  });

  Widget field({
    required List<BondTime> got,
    List<bool>? valid,
    BondTime value = const BondTime(hour24: 9, minute: 5),
  }) =>
      BondTimeField(
        label: 'Start',
        value: value,
        semanticsId: 'start',
        onChanged: got.add,
        onValidChanged: valid?.add,
      );

  testWidgets('shows hour, minute and AM/PM from the value', (t) async {
    final sem = t.ensureSemantics();
    await pumpBond(t, field(got: []));
    final fields = find.byType(TextField);
    expect(t.widget<TextField>(fields.at(0)).controller!.text, '9');
    expect(t.widget<TextField>(fields.at(1)).controller!.text, '05');
    expect(find.text('Hour'), findsOneWidget);
    expect(find.text('Minute'), findsOneWidget);
    expect(find.bySemanticsIdentifier('start-hour'), findsOneWidget);
    expect(find.bySemanticsIdentifier('start-minute'), findsOneWidget);
    expect(find.bySemanticsIdentifier('start-meridiem-pm'), findsOneWidget);
    await expectNoOverlays(t);
    sem.dispose();
  });

  testWidgets('typing a valid hour and minute reports the time', (t) async {
    final got = <BondTime>[];
    await pumpBond(t, field(got: got));
    await t.enterText(find.byType(TextField).at(0), '11');
    await t.pump();
    expect(got.last, const BondTime(hour24: 11, minute: 5));
    await t.enterText(find.byType(TextField).at(1), '45');
    await t.pump();
    expect(got.last, const BondTime(hour24: 11, minute: 45));
    await expectNoOverlays(t);
  });

  testWidgets('PM flips the half of the day and keeps hour and minute', (t) async {
    final got = <BondTime>[];
    await pumpBond(t, field(got: got));
    await t.tap(find.text('PM'));
    await t.pump();
    expect(got.last, const BondTime(hour24: 21, minute: 5));
    await t.tap(find.text('AM'));
    await t.pump();
    expect(got.last, const BondTime(hour24: 9, minute: 5));
  });

  testWidgets('an invalid hour says so inline and reports nothing', (t) async {
    final got = <BondTime>[];
    final valid = <bool>[];
    await pumpBond(t, field(got: got, valid: valid));
    await t.enterText(find.byType(TextField).at(0), '13');
    await t.pump();
    expect(find.text('Enter a time like 11:45'), findsOneWidget);
    expect(got, isEmpty);
    expect(valid, [false]);
    // A valid entry clears the message and reports valid again.
    await t.enterText(find.byType(TextField).at(0), '12');
    await t.pump();
    expect(find.text('Enter a time like 11:45'), findsNothing);
    expect(valid, [false, true]);
    // 12 AM is midnight.
    expect(got.last, const BondTime(hour24: 0, minute: 5));
  });

  testWidgets('an invalid minute and an empty box are rejected', (t) async {
    final got = <BondTime>[];
    await pumpBond(t, field(got: got));
    await t.enterText(find.byType(TextField).at(1), '75');
    await t.pump();
    expect(find.text('Enter a time like 11:45'), findsOneWidget);
    await t.enterText(find.byType(TextField).at(1), '');
    await t.pump();
    expect(find.text('Enter a time like 11:45'), findsOneWidget);
    expect(got, isEmpty);
  });

  testWidgets('leaving an invalid box restores the last valid value', (t) async {
    final valid = <bool>[];
    await pumpBond(
      t,
      Column(children: [
        field(got: [], valid: valid),
        const TextField(key: ValueKey('other')),
      ]),
    );
    await t.tap(find.byType(TextField).at(0));
    await t.enterText(find.byType(TextField).at(0), '0');
    await t.pump();
    expect(find.text('Enter a time like 11:45'), findsOneWidget);
    await t.tap(find.byKey(const ValueKey('other')));
    await t.pump();
    await t.pump();
    expect(find.text('Enter a time like 11:45'), findsNothing);
    expect(t.widget<TextField>(find.byType(TextField).at(0)).controller!.text, '9');
    expect(valid, [false, true]);
  });

  testWidgets('follows a value changed from outside', (t) async {
    await pumpBond(t, field(got: []));
    await pumpBond(
      t,
      field(got: [], value: const BondTime(hour24: 14, minute: 30)),
    );
    await t.pump();
    expect(t.widget<TextField>(find.byType(TextField).at(0)).controller!.text, '2');
    expect(t.widget<TextField>(find.byType(TextField).at(1)).controller!.text, '30');
  });

  testWidgets('phone width 390 renders without overflow', (t) async {
    await pumpBond(t, field(got: []));
    expect(t.takeException(), isNull);
  });
}
