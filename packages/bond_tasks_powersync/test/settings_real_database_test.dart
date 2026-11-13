@Tags(['real_db'])
@TestOn('vm')
library;

import 'dart:convert';
import 'dart:io';

import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:powersync/powersync.dart';

const renames = {'time_zone': 'tz', 'start_of_day': 'day_start', 'end_of_day': 'day_end', 'lead_minutes': 'remind_lead'};

Future<List<SyncCrudEntry>> drain(SyncDb db) async {
  final out = <SyncCrudEntry>[];
  while (true) {
    final tx = await db.nextCrudTransaction();
    if (tx == null) return out;
    out.addAll(tx.entries);
    await tx.complete();
  }
}

class _Zone implements TimeZoneSource {
  @override
  Future<String?> currentZone() async => 'Europe/Paris';
}

Future<void> tick() => Future<void>.delayed(const Duration(milliseconds: 150));

void main() {
  late Directory dir;
  late PowerSyncDatabase raw;
  late SyncDb db;

  Future<void> open(List<Table> tables) async {
    dir = Directory.systemTemp.createTempSync('btp_settings_real');
    raw = PowerSyncDatabase(schema: Schema([...tables, ...syncSupportTables()]), path: '${dir.path}/t.db');
    await raw.initialize();
    db = PowerSyncDb(raw);
  }

  tearDown(() async {
    await raw.close();
    dir.deleteSync(recursive: true);
  });

  test('no row, put, patch, reset, empty patch, bad value, watch (local write and a synced row)', () async {
    await open(taskSettingsTables());
    final store = PowerSyncTaskSettingsStore(db, userId: 'u1');
    final first = await store.get();
    expect((first.startOfDay, first.leadMinutes, first.timeZone), ('08:00', 60, null));
    expect(first.overridden, isEmpty);

    final seen = <TaskSettings>[];
    final sub = store.watch().listen(seen.add);
    await tick();

    final a = await store.update(const TaskSettingsPatch(timeZone: 'Europe/Paris', leadMinutes: 15));
    expect((a.timeZone, a.leadMinutes), ('Europe/Paris', 15));
    expect(a.overridden, {'time_zone', 'lead_minutes'});
    final put = await drain(db);
    expect(put, hasLength(1));
    expect((put.single.op, put.single.table, put.single.id), ('put', 'task_user_settings', 'u1'));
    expect(put.single.opData, {'time_zone': 'Europe/Paris', 'lead_minutes': 15});

    await store.update(const TaskSettingsPatch(endOfDay: '18:30', leadMinutes: 15)); // lead unchanged: not in the patch
    final patch = await drain(db);
    expect(patch.single.op, 'patch');
    expect(patch.single.opData, {'end_of_day': '18:30'});

    final r = await store.update(const TaskSettingsPatch(reset: {'end_of_day'}));
    expect(r.endOfDay, '17:00');
    expect(r.overridden, {'time_zone', 'lead_minutes'});
    final reset = await drain(db);
    expect(reset.single.op, 'patch');
    expect(reset.single.opData, {'end_of_day': null});

    await store.update(const TaskSettingsPatch());
    expect(await drain(db), isEmpty);
    await expectLater(store.update(const TaskSettingsPatch(startOfDay: '7:00')), throwsArgumentError);
    expect(await drain(db), isEmpty);
    expect((await store.get()).startOfDay, '08:00');

    await tick();
    expect(seen.last.overridden, {'time_zone', 'lead_minutes'}, reason: 'the watch followed the local writes');
    final before = seen.length;

    // a row arrives as a sync would write it
    await raw.execute('UPDATE ps_data__task_user_settings SET data = ? WHERE id = ?', [jsonEncode({'time_zone': 'Asia/Tokyo', 'start_of_day': '06:30'}), 'u1']);
    await tick();
    expect(seen.length, greaterThan(before));
    expect(seen.last.timeZone, 'Asia/Tokyo');
    expect(seen.last.startOfDay, '06:30');
    expect(seen.last.overridden, {'time_zone', 'start_of_day'});
    await sub.cancel();

    // another user's row, written as sync does, reaches that user's store
    await raw.execute('INSERT INTO ps_data__task_user_settings (id, data) VALUES (?, ?)', ['u2', jsonEncode({'lead_minutes': 5})]);
    expect((await PowerSyncTaskSettingsStore(db, userId: 'u2').get()).leadMinutes, 5);
  });

  test('rename: the table and queued opData use the local names', () async {
    await open(taskSettingsTables(table: 'user_prefs', rename: renames));
    final store = PowerSyncTaskSettingsStore(db, userId: 'u1', table: 'user_prefs', rename: renames);
    await store.update(const TaskSettingsPatch(timeZone: 'UTC', startOfDay: '07:00'));
    final put = (await drain(db)).single;
    expect((put.op, put.table, put.id), ('put', 'user_prefs', 'u1'));
    expect(put.opData, {'tz': 'UTC', 'day_start': '07:00'});
    final s = await store.update(const TaskSettingsPatch(leadMinutes: 10, reset: {'time_zone'}));
    expect((await drain(db)).single.opData, {'remind_lead': 10, 'tz': null});
    expect((s.timeZone, s.leadMinutes), (null, 10));
    expect(s.overridden, {'start_of_day', 'lead_minutes'});
  });

  test('a ZoneReporter over the store queues the device zone once', () async {
    await open(taskSettingsTables());
    final reporter = ZoneReporter(_Zone(), PowerSyncTaskSettingsStore(db, userId: 'u1'));
    await reporter.reportIfChanged();
    await reporter.reportIfChanged();
    final q = await drain(db);
    expect(q, hasLength(1));
    expect(q.single.opData, {'time_zone': 'Europe/Paris'});
  });
}
