import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

const _settings = TaskSettings(timeZone: 'America/Los_Angeles', startOfDay: '08:00', endOfDay: '17:00', leadMinutes: 60);

Future<void> _tap(WidgetTester t, String text) async {
  final f = find.text(text);
  await t.ensureVisible(f);
  await t.tap(f);
  await t.pump();
}

void main() {
  for (final phone in [false, true]) {
    testWidgets('shows values, zone and the quiet hours sentence (phone=$phone)', (t) async {
      final sem = t.ensureSemantics();
      await pumpAt(t, BondTaskSettingsForm(settings: _settings, onSubmit: (_) {}, semanticsPrefix: 's'), phone: phone);
      expect(find.text('America/Los_Angeles'), findsOneWidget);
      expect(find.text('Reminders for dated tasks wait while you are off, from 17:00 to 08:00.'), findsOneWidget);
      expect(find.bySemanticsIdentifier('s.settings-start'), findsOneWidget);
      expect(find.bySemanticsIdentifier('s.settings-save'), findsOneWidget);
      await expectNoOverlays(t);
      expect(t.takeException(), isNull);
      sem.dispose();
    });
  }

  testWidgets('the sentence follows the typed times', (t) async {
    await pumpAt(t, BondTaskSettingsForm(settings: _settings, onSubmit: (_) {}));
    await t.enterText(find.byType(TextField).at(0), '7:30');
    await t.enterText(find.byType(TextField).at(1), '18:00');
    await t.pump();
    expect(find.textContaining('from 18:00 to 07:30'), findsOneWidget);
  });

  testWidgets('a valid save sends the three values', (t) async {
    final got = <TaskSettingsPatch>[];
    await pumpAt(t, BondTaskSettingsForm(settings: _settings, onSubmit: got.add));
    await t.enterText(find.byType(TextField).at(0), '7:30');
    await t.enterText(find.byType(TextField).at(2), '15');
    await _tap(t, 'Save');
    expect(got, hasLength(1));
    expect(got.single.toJson(), {'start_of_day': '07:30', 'end_of_day': '17:00', 'lead_minutes': 15});
  });

  testWidgets('start equal to end shows a message, hides the sentence and blocks save', (t) async {
    final got = <TaskSettingsPatch>[];
    await pumpAt(t, BondTaskSettingsForm(settings: _settings, onSubmit: got.add));
    await t.enterText(find.byType(TextField).at(1), '08:00');
    await t.pump();
    expect(find.text('The start and the end must be different times.'), findsOneWidget);
    expect(find.textContaining('wait while you are off'), findsNothing);
    await _tap(t, 'Save');
    expect(got, isEmpty);
  });

  testWidgets('bad times and a bad lead show inline and block save', (t) async {
    final got = <TaskSettingsPatch>[];
    await pumpAt(t, BondTaskSettingsForm(settings: _settings, onSubmit: got.add));
    await t.enterText(find.byType(TextField).at(0), '25:00');
    await t.enterText(find.byType(TextField).at(2), '-3');
    await t.pump();
    expect(find.text('Use the form HH:MM, for example 08:00.'), findsOneWidget);
    expect(find.text('Enter a whole number of minutes from 0 to 10080.'), findsOneWidget);
    await _tap(t, 'Save');
    expect(got, isEmpty);
  });

  testWidgets('settings that load after the first build replace the defaults, unless the person edited', (t) async {
    const loaded = TaskSettings(timeZone: 'Europe/Paris', startOfDay: '09:30', endOfDay: '18:15', leadMinutes: 45);
    Future<void> show(TaskSettings s, List<TaskSettingsPatch> got) =>
        pumpAt(t, BondTaskSettingsForm(settings: s, onSubmit: got.add));
    String text(int i) => t.widget<TextField>(find.byType(TextField).at(i)).controller!.text;

    final got = <TaskSettingsPatch>[];
    await show(const TaskSettings(), got);
    expect(text(0), '08:00');
    await show(loaded, got);
    expect([text(0), text(1), text(2)], ['09:30', '18:15', '45'], reason: 'untouched form follows the load');
    await _tap(t, 'Save');
    expect(got.single.toJson(), {'start_of_day': '09:30', 'end_of_day': '18:15', 'lead_minutes': 45});

    // A second form: edit first, then the load arrives.
    got.clear();
    await pumpAt(t, const SizedBox());
    await show(const TaskSettings(), got);
    await t.enterText(find.byType(TextField).at(0), '07:00');
    await t.pump();
    await show(loaded, got);
    expect(text(0), '07:00', reason: 'the edit is kept');
    expect(text(1), '17:00', reason: 'and nothing else is overwritten either');
  });

  for (final phone in [false, true]) {
    testWidgets('zoneOptions: search, pick inline, and the zone is in the patch (phone=$phone)', (t) async {
      final got = <TaskSettingsPatch>[];
      await pumpAt(
        t,
        BondTaskSettingsForm(
          settings: _settings,
          onSubmit: got.add,
          zoneOptions: const ['America/Los_Angeles', 'Europe/Paris', 'Europe/Berlin'],
          semanticsPrefix: 's',
        ),
        phone: phone,
      );
      expect(find.bySemanticsIdentifier('s.settings-zone'), findsOneWidget);
      await t.enterText(find.byType(TextField).first, 'paris');
      await t.pump(const Duration(milliseconds: 300));
      await t.pump();
      await _tap(t, 'Europe/Paris');
      await _tap(t, 'Save');
      expect(got.single.timeZone, 'Europe/Paris');
      await expectNoOverlays(t);
      expect(t.takeException(), isNull);
    });
  }

  testWidgets('without zoneOptions the zone is read-only and not sent', (t) async {
    final got = <TaskSettingsPatch>[];
    await pumpAt(t, BondTaskSettingsForm(settings: _settings, onSubmit: got.add));
    await _tap(t, 'Save');
    expect(got.single.timeZone, isNull);
  });

  testWidgets('busy turns Save off; the zone is not editable', (t) async {
    final got = <TaskSettingsPatch>[];
    await pumpAt(t, BondTaskSettingsForm(settings: _settings, busy: true, onSubmit: got.add));
    expect(t.widget<BondButton>(find.byType(BondButton)).onPressed, isNull);
    expect(got, isEmpty);
    expect(find.byType(TextField), findsNWidgets(3), reason: 'start, end and lead only');
  });
}
