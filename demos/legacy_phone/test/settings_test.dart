@Tags(['real_db'])
@TestOn('vm')
library;

/// Settings over sync: the app's own `user_prefs` table (renamed columns, row id = user id) under the SDK's settings store.
import 'dart:convert';
import 'dart:io';

import 'package:bond_tasks/bond_tasks.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:legacy_phone/legacy_phone.dart';

import 'support.dart';

const _path = '../../fixtures/legacy_host/upload_phone_settings.json';

class _Zone implements TimeZoneSource {
  _Zone(this.zone);
  String? zone;
  @override
  Future<String?> currentZone() async => zone;
}

void main() {
  forEachStage('no row: every field is the app default and nothing is overridden', (env) async {
    final s = await legacyTaskSettingsStore(env.db, 'u-owner').get();
    expect((s.timeZone, s.startOfDay, s.endOfDay, s.leadMinutes), (null, '08:00', '17:00', 60));
    expect(s.overridden, isEmpty);
    expect(s.warnings, isEmpty);
  });

  forEachStage('a write of zone and end of day queues a put with the app\'s column names; the next one a patch', (env) async {
    final store = legacyTaskSettingsStore(env.db, 'u-owner');
    final s = await store.update(const TaskSettingsPatch(timeZone: 'America/Denver', endOfDay: '18:30'));
    expect((s.timeZone, s.endOfDay, s.startOfDay), ('America/Denver', '18:30', '08:00'));
    expect(s.overridden, {'time_zone', 'end_of_day'});
    final put = (await drain(env.db)).single;
    expect((put.op, put.table, put.id), ('put', 'user_prefs', 'u-owner'));
    expect(put.opData, {'tz': 'America/Denver', 'day_end': '18:30'});
    final row = await env.db.getOptional('SELECT * FROM user_prefs WHERE id = ?', ['u-owner']);
    expect((row!['tz'], row['day_end'], row['day_start'], row['remind_lead']), ('America/Denver', '18:30', null, null));
    await store.update(const TaskSettingsPatch(leadMinutes: 15));
    final patch = (await drain(env.db)).single;
    expect(patch.op, 'patch');
    expect(patch.opData, {'remind_lead': 15});
  });

  forEachStage('a reset writes NULL and the field reads as the default again', (env) async {
    final store = legacyTaskSettingsStore(env.db, 'u-owner');
    await store.update(const TaskSettingsPatch(timeZone: 'America/Denver', endOfDay: '18:30'));
    await drain(env.db);
    final s = await store.update(const TaskSettingsPatch(reset: {'end_of_day'}));
    expect((s.endOfDay, s.timeZone), ('17:00', 'America/Denver'));
    expect(s.overridden, {'time_zone'});
    final patch = (await drain(env.db)).single;
    expect(patch.opData, {'day_end': null});
  });

  forEachStage('an empty patch writes nothing; a bad HH:MM throws and writes nothing', (env) async {
    final store = legacyTaskSettingsStore(env.db, 'u-owner');
    await store.update(const TaskSettingsPatch());
    expect(() => store.update(const TaskSettingsPatch(endOfDay: '25:00')), throwsArgumentError);
    expect(() => store.update(const TaskSettingsPatch(startOfDay: '8am')), throwsArgumentError);
    expect(await drain(env.db), isEmpty);
    expect(await env.db.getOptional('SELECT id FROM user_prefs'), isNull);
  });

  forEachStage('watch re-emits the new value; one user\'s row is not another\'s', (env) async {
    final store = legacyTaskSettingsStore(env.db, 'u-owner');
    final w = Watch(store.watch());
    try {
      expect((await w.first()).endOfDay, '17:00');
      await legacyTaskSettingsStore(env.db, 'u-other').update(const TaskSettingsPatch(endOfDay: '12:00'));
      await store.update(const TaskSettingsPatch(endOfDay: '19:00'));
      expect((await w.next((s) => s.endOfDay == '19:00')).endOfDay, '19:00');
      expect((await store.get()).endOfDay, '19:00');
      expect((await legacyTaskSettingsStore(env.db, 'u-other').get()).endOfDay, '12:00');
    } finally {
      await w.cancel();
    }
  });

  forEachStage('ZoneReporter over the store writes the device zone once', (env) async {
    final store = legacyTaskSettingsStore(env.db, 'u-owner');
    final source = _Zone('Europe/Paris');
    final reporter = ZoneReporter(source, store);
    await reporter.reportIfChanged();
    await reporter.reportIfChanged();
    expect((await store.get()).timeZone, 'Europe/Paris');
    final q = await drain(env.db);
    expect(q.single.opData, {'tz': 'Europe/Paris'}, reason: 'the second call saw no change');
    source.zone = 'Asia/Tokyo';
    await reporter.reportIfChanged();
    expect((await drain(env.db)).single.opData, {'tz': 'Asia/Tokyo'});
  });

  test('the queue of a task, a zone and end-of-day write and a reset is the recorded upload (stage two)', () async {
    final env = await openEnv(LegacyStage.widened);
    try {
      final store = legacyTaskSettingsStore(env.db, 'u-owner');
      await env.repo.create(const TaskDraft(title: 'Date only', id: 'ph-s1', dueDate: '2026-11-20'));
      env.tick();
      await store.update(const TaskSettingsPatch(timeZone: 'America/Denver', endOfDay: '18:30'));
      env.tick();
      await store.update(const TaskSettingsPatch(reset: {'end_of_day'}));
      final recorded = {
        'note': 'What the legacy phone store queues for a date-only task, a zone and end-of-day write into the app\'s `user_prefs` '
            '(columns tz, day_end) and a reset of the end of day (demos/legacy_phone, test/settings_test.dart). Regenerate with BOND_REGEN_FIXTURES=1.',
        'requests': await queuedRequests(env),
      };
      if (Platform.environment['BOND_REGEN_FIXTURES'] == '1') {
        File(_path).writeAsStringSync('${const JsonEncoder.withIndent('  ').convert(recorded)}\n');
      }
      final file = jsonDecode(File(_path).readAsStringSync()) as Map;
      expect(jsonDecode(jsonEncode(recorded['requests'])), file['requests']);
      expect(file['requests'] as List, hasLength(3));
    } finally {
      await env.close();
    }
  });
}
