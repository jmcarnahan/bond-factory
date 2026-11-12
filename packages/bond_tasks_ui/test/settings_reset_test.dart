import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

const _def = TaskSettings(timeZone: 'America/Los_Angeles', overridden: {});
const _set = TaskSettings(
  timeZone: 'America/Los_Angeles',
  endOfDay: '18:00',
  leadMinutes: 15,
  overridden: {'end_of_day', 'lead_minutes'},
);

Finder _key(String f) => find.byKey(ValueKey('task-settings-reset-$f'));

void main() {
  testWidgets('the control shows only for overridden fields; the others say Default', (t) async {
    await pumpAt(t, BondTaskSettingsForm(settings: _set, onSubmit: (_) {}));
    expect(_key('end_of_day'), findsOneWidget);
    expect(_key('lead_minutes'), findsOneWidget);
    expect(_key('start_of_day'), findsNothing);
    expect(_key('time_zone'), findsNothing);
    expect(find.text('Reset to default'), findsNWidgets(2));
    expect(find.text('Default'), findsNWidgets(2));
    await pumpAt(t, BondTaskSettingsForm(settings: _def, onSubmit: (_) {}));
    expect(find.text('Reset to default'), findsNothing);
    expect(find.text('Default'), findsNWidgets(4));
  });

  for (final phone in [false, true]) {
    testWidgets('tapping Reset sends only that field in reset, no dialog (phone=$phone)', (t) async {
      final sem = t.ensureSemantics();
      final got = <TaskSettingsPatch>[];
      await pumpAt(t, BondTaskSettingsForm(settings: _set, onSubmit: got.add, semanticsPrefix: 's'), phone: phone);
      expect(find.bySemanticsIdentifier('s.settings-reset-end'), findsOneWidget);
      await t.ensureVisible(_key('end_of_day'));
      await t.tap(_key('end_of_day'));
      await t.pump();
      expect(got, hasLength(1));
      expect(got.single.reset, {'end_of_day'});
      expect(got.single.toJson(), {'end_of_day': null});
      await expectNoOverlays(t);
      expect(t.takeException(), isNull);
      sem.dispose();
    });
  }

  testWidgets('after the reload the reset field shows the default, other edits stay', (t) async {
    final got = <TaskSettingsPatch>[];
    String text(int i) => t.widget<TextField>(find.byType(TextField).at(i)).controller!.text;
    await pumpAt(t, BondTaskSettingsForm(settings: _set, onSubmit: got.add));
    await t.enterText(find.byType(TextField).at(0), '07:00');
    await t.pump();
    await t.ensureVisible(_key('end_of_day'));
    await t.tap(_key('end_of_day'));
    await t.pump();
    await pumpAt(t, BondTaskSettingsForm(settings: const TaskSettings(timeZone: 'America/Los_Angeles', leadMinutes: 15, overridden: {'lead_minutes'}), onSubmit: got.add));
    expect(text(1), '17:00');
    expect(text(0), '07:00');
    expect(_key('end_of_day'), findsNothing);
  });

  testWidgets('busy disables the reset control', (t) async {
    final got = <TaskSettingsPatch>[];
    await pumpAt(t, BondTaskSettingsForm(settings: _set, busy: true, onSubmit: got.add));
    await t.ensureVisible(_key('end_of_day'));
    await t.tap(_key('end_of_day'), warnIfMissed: false);
    await t.pump();
    expect(got, isEmpty);
  });
}
