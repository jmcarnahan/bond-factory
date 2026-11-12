import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

const _def = TaskSettings(timeZone: 'America/Los_Angeles', overridden: {});
const _set = TaskSettings(timeZone: 'America/Los_Angeles', endOfDay: '18:00', overridden: {'end_of_day'});

Finder _key(String f) => find.byKey(ValueKey('task-settings-reset-$f'));

Future<void> _save(WidgetTester t) async {
  final f = find.text('Save');
  await t.ensureVisible(f);
  await t.tap(f);
  await t.pump();
}

void main() {
  testWidgets('settings_form_save_sends_only_changed_fields', (t) async {
    final got = <TaskSettingsPatch>[];
    await pumpAt(t, BondTaskSettingsForm(settings: _def, onSubmit: got.add));
    await t.enterText(find.byType(TextField).at(2), '15');
    await _save(t);
    expect(got.single.toJson(), {'lead_minutes': 15});
  });

  testWidgets('settings_form_save_with_nothing_changed_sends_nothing', (t) async {
    final got = <TaskSettingsPatch>[];
    await pumpAt(t, BondTaskSettingsForm(settings: _def, onSubmit: got.add));
    await _save(t);
    expect(got, isEmpty);
  });

  testWidgets('settings_form_save_keeps_an_already_set_field', (t) async {
    final got = <TaskSettingsPatch>[];
    await pumpAt(t, BondTaskSettingsForm(settings: _set, onSubmit: got.add));
    await t.enterText(find.byType(TextField).at(2), '15');
    await _save(t);
    expect(got.single.toJson(), {'end_of_day': '18:00', 'lead_minutes': 15});
  });

  testWidgets('settings_form_old_server_unknown_shows_no_hint_and_no_reset', (t) async {
    final got = <TaskSettingsPatch>[];
    const old = TaskSettings(timeZone: 'America/Los_Angeles', endOfDay: '18:00');
    await pumpAt(t, BondTaskSettingsForm(settings: old, onSubmit: got.add));
    expect(find.text('Default'), findsNothing);
    expect(find.text('Reset to default'), findsNothing);
    await t.enterText(find.byType(TextField).at(2), '15');
    await _save(t);
    expect(got.single.toJson(), {'start_of_day': '08:00', 'end_of_day': '18:00', 'lead_minutes': 15},
        reason: 'a server that does not say what is overridden gets every field, as before');
  });

  for (final phone in [false, true]) {
    testWidgets('reset_control_is_48_high_with_a_name_per_field (phone=$phone)', (t) async {
      final sem = t.ensureSemantics();
      const all = TaskSettings(
        timeZone: 'America/Los_Angeles',
        overridden: {'time_zone', 'start_of_day', 'end_of_day', 'lead_minutes'},
      );
      await pumpAt(t, BondTaskSettingsForm(settings: all, onSubmit: (_) {}), phone: phone);
      final names = <String>{};
      for (final f in ['time_zone', 'start_of_day', 'end_of_day', 'lead_minutes']) {
        expect(t.getRect(_key(f)).height, greaterThanOrEqualTo(48), reason: f);
        names.add(t.getSemantics(_key(f)).label);
      }
      expect(names, hasLength(4));
      expect(names, contains('Reset time zone to default'));
      sem.dispose();
    });
  }

  testWidgets('reset_labels_are_injectable', (t) async {
    final sem = t.ensureSemantics();
    await pumpAt(t, BondTaskSettingsForm(settings: _set, onSubmit: (_) {}, labels: const SettingsLabels(resetWorkDayEnd: 'X end')));
    expect(t.getSemantics(_key('end_of_day')).label, 'X end');
    sem.dispose();
  });

  testWidgets('failed_reset_does_not_let_a_later_reload_overwrite_typing', (t) async {
    String text(int i) => t.widget<TextField>(find.byType(TextField).at(i)).controller!.text;
    await pumpAt(t, BondTaskSettingsForm(settings: _set, onSubmit: (_) {}));
    await t.enterText(find.byType(TextField).at(0), '07:00');
    await t.pump();
    await t.ensureVisible(_key('end_of_day'));
    await t.tap(_key('end_of_day'));
    await t.pump();
    await pumpAt(t, BondTaskSettingsForm(settings: _set, busy: true, onSubmit: (_) {}));
    await pumpAt(t, BondTaskSettingsForm(settings: _set, onSubmit: (_) {})); // the reset failed
    await pumpAt(t, BondTaskSettingsForm(settings: _def, onSubmit: (_) {})); // a later, unrelated reload
    expect(text(1), '18:00', reason: 'the field is no longer tracked as resetting');
    expect(text(0), '07:00');
  });
}
