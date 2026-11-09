import 'package:bond_ui/src/primitives/bond_chip.dart';
import 'package:bond_ui/src/primitives/bond_date_field.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  // Sunday, Nov 8 2026 is "today" for these tests.
  final today = DateTime(2026, 11, 8);

  Widget field({
    DateTime? value,
    required List<DateTime> picked,
    List<String>? log,
    BondDateMode mode = BondDateMode.date,
    bool clearable = false,
    DateTime? firstDate,
    DateTime? lastDate,
    bool open = false,
  }) =>
      BondDateField(
        label: 'Due',
        placeholder: 'Pick a date',
        value: value,
        today: today,
        mode: mode,
        firstDate: firstDate,
        lastDate: lastDate,
        initiallyOpen: open,
        semanticsId: 'due',
        onChanged: picked.add,
        onCleared: clearable ? () => log?.add('cleared') : null,
      );

  testWidgets('shows the placeholder, then the formatted date', (t) async {
    await pumpBond(t, field(picked: []));
    expect(find.text('Pick a date'), findsOneWidget);
    await pumpBond(t, field(value: DateTime(2026, 11, 10), picked: []));
    expect(find.text('Tue, Nov 10, 2026'), findsOneWidget);
    await expectNoOverlays(t);
  });

  testWidgets('opens inline, picks a day, closes; no overlay', (t) async {
    final sem = t.ensureSemantics();
    final picked = <DateTime>[];
    await pumpBond(t, field(picked: picked));
    expect(find.text('November 2026'), findsNothing);
    await t.tap(find.text('Pick a date'));
    await t.pump();
    expect(find.text('November 2026'), findsOneWidget);
    expect(find.bySemanticsIdentifier('due-day-2026-11-17'), findsOneWidget);
    await expectNoOverlays(t);

    await t.tap(find.text('17'));
    await t.pump();
    expect(picked, [DateTime(2026, 11, 17)]);
    // Date only closes the picker.
    expect(find.text('November 2026'), findsNothing);
    await expectNoOverlays(t);
    sem.dispose();
  });

  testWidgets('pages months without committing', (t) async {
    final picked = <DateTime>[];
    await pumpBond(t, field(picked: picked, open: true));
    await t.tap(find.byIcon(Icons.chevron_right));
    await t.pump();
    expect(find.text('December 2026'), findsOneWidget);
    await t.tap(find.byIcon(Icons.chevron_left));
    await t.tap(find.byIcon(Icons.chevron_left));
    await t.pump();
    expect(find.text('October 2026'), findsOneWidget);
    expect(picked, isEmpty);
  });

  testWidgets('clear calls onCleared; Today picks today', (t) async {
    final sem = t.ensureSemantics();
    final picked = <DateTime>[];
    final log = <String>[];
    await pumpBond(
      t,
      field(
        value: DateTime(2026, 11, 12),
        picked: picked,
        log: log,
        clearable: true,
        open: true,
      ),
    );
    expect(find.bySemanticsIdentifier('due-clear'), findsOneWidget);
    await t.tap(find.text('Today'));
    await t.pump();
    expect(picked, [DateTime(2026, 11, 8)]);

    await pumpBond(
      t,
      field(
        value: DateTime(2026, 11, 12),
        picked: picked,
        log: log,
        clearable: true,
        open: true,
      ),
    );
    // Today closed the picker; open it again, then clear.
    await t.tap(find.text('Thu, Nov 12, 2026'));
    await t.pump();
    await t.tap(find.text('Clear'));
    await t.pump();
    expect(log, ['cleared']);
    expect(find.text('November 2026'), findsNothing);
    await expectNoOverlays(t);
    sem.dispose();
  });

  testWidgets('days outside first and last date cannot be picked', (t) async {
    final picked = <DateTime>[];
    await pumpBond(
      t,
      field(
        picked: picked,
        open: true,
        firstDate: DateTime(2026, 11, 10),
        lastDate: DateTime(2026, 11, 20),
      ),
    );
    await t.tap(find.text('3').first);
    await t.pump();
    expect(picked, isEmpty);
    await t.tap(find.text('25').first);
    await t.pump();
    expect(picked, isEmpty);
    await t.tap(find.text('15').first);
    await t.pump();
    expect(picked, [DateTime(2026, 11, 15)]);
  });

  testWidgets('date plus time stays open and picks a time chip', (t) async {
    final picked = <DateTime>[];
    await pumpBond(
      t,
      field(
        value: DateTime(2026, 11, 12, 9, 0),
        picked: picked,
        mode: BondDateMode.dateTime,
        open: true,
      ),
    );
    expect(find.text('Thu, Nov 12, 2026 · 9:00 AM'), findsOneWidget);
    await t.tap(find.text('14'));
    await t.pump();
    expect(picked.last, DateTime(2026, 11, 14, 9, 0));
    expect(find.text('November 2026'), findsOneWidget);
    await t.ensureVisible(find.text('10:15 AM'));
    await t.tap(find.text('10:15 AM'));
    await t.pump();
    expect(picked.last, DateTime(2026, 11, 12, 10, 15));
    await expectNoOverlays(t);
  });

  testWidgets('time mode shows only the chips', (t) async {
    final picked = <DateTime>[];
    await pumpBond(
      t,
      field(
        value: DateTime(2026, 11, 12, 13, 30),
        picked: picked,
        mode: BondDateMode.time,
        open: true,
      ),
    );
    expect(find.text('1:30 PM'), findsWidgets);
    expect(find.text('November 2026'), findsNothing);
  });

  testWidgets('dateTime with no value: a day reports midnight, no chip lit',
      (t) async {
    final picked = <DateTime>[];
    await pumpBond(
      t,
      field(picked: picked, mode: BondDateMode.dateTime, open: true),
    );
    await t.tap(find.text('17'));
    await t.pump();
    expect(picked, [DateTime(2026, 11, 17)]);
    // Still open for a time, and no time chip is selected.
    expect(find.text('November 2026'), findsOneWidget);
    final chips = t.widgetList<BondChip>(find.byType(BondChip));
    expect(chips, isNotEmpty);
    expect(chips.where((c) => c.selected), isEmpty);
  });

  testWidgets('time mode: Clear is offered and clears', (t) async {
    final sem = t.ensureSemantics();
    final log = <String>[];
    await pumpBond(
      t,
      field(
        value: DateTime(2026, 11, 12, 13, 30),
        picked: [],
        log: log,
        clearable: true,
        mode: BondDateMode.time,
        open: true,
      ),
    );
    expect(find.bySemanticsIdentifier('due-clear'), findsOneWidget);
    expect(find.text('Today'), findsNothing);
    await t.tap(find.text('Clear'));
    await t.pump();
    expect(log, ['cleared']);
    sem.dispose();
  });

  testWidgets('with no value the grid follows a new today', (t) async {
    Widget f(DateTime day) => BondDateField(
          value: null,
          today: day,
          initiallyOpen: true,
          onChanged: (_) {},
        );
    await pumpBond(t, f(DateTime(2026, 11, 8)));
    expect(find.text('November 2026'), findsOneWidget);
    await pumpBond(t, f(DateTime(2026, 12, 2)));
    await t.pump();
    expect(find.text('December 2026'), findsOneWidget);
  });

  testWidgets('a disabled field does not open', (t) async {
    await pumpBond(
      t,
      BondDateField(
        value: null,
        today: today,
        enabled: false,
        placeholder: 'Pick a date',
        onChanged: (_) {},
      ),
    );
    await t.tap(find.text('Pick a date'));
    await t.pump();
    expect(find.text('November 2026'), findsNothing);
  });

  testWidgets('the open panel fits 390 px without overflow', (t) async {
    await pumpBond(
      t,
      field(
        value: DateTime(2026, 11, 12, 9),
        picked: [],
        mode: BondDateMode.dateTime,
        open: true,
        clearable: true,
      ),
    );
    expect(t.takeException(), isNull);
  });
}
