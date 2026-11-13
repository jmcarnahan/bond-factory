import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_sync_powersync/testing.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:powersync/powersync.dart' show Table;

const renames = {'time_zone': 'tz', 'start_of_day': 'day_start', 'end_of_day': 'day_end', 'lead_minutes': 'remind_lead'};

FakeSyncDb settingsDb({String table = 'task_user_settings', Set<String>? cols, List<SyncRow> rows = const []}) => FakeSyncDb.tables(
      {table: rows},
      applySql: true,
      columns: {table: cols ?? {'id', ...kTaskSettingsColumns}},
    );

List<Stmt> writes(FakeSyncDb db) => [
      for (final s in db.statements)
        if (RegExp(r'^(INSERT|UPDATE|DELETE)').hasMatch(s.sql)) s,
    ];

class _Zone implements TimeZoneSource {
  _Zone(this.zone);
  String zone;
  @override
  Future<String?> currentZone() async => zone;
}

void main() {
  test('names and the table definition', () {
    expect(kTaskSettingsTable, 'task_user_settings');
    expect(kTaskSettingsColumns, ['time_zone', 'start_of_day', 'end_of_day', 'lead_minutes']);
    final t = taskSettingsTables().single;
    expect(t.name, 'task_user_settings');
    expect([for (final c in t.columns) c.name], kTaskSettingsColumns);
    final r = taskSettingsTables(table: 'user_prefs', rename: renames).single;
    expect(r.name, 'user_prefs');
    expect([for (final c in r.columns) c.name], ['tz', 'day_start', 'day_end', 'remind_lead']);
    expect(t, isA<Table>());
  });

  test('no row: the app defaults, nothing overridden, no warnings', () async {
    final db = settingsDb();
    final s = await PowerSyncTaskSettingsStore(db, userId: 'u1').get();
    expect((s.timeZone, s.startOfDay, s.endOfDay, s.leadMinutes), (null, '08:00', '17:00', 60));
    expect(s.overridden, isEmpty);
    expect(s.warnings, isEmpty);
    expect(db.statements.single.toString(), 'tx SELECT * FROM task_user_settings WHERE id = ? [u1]');
    final d = await PowerSyncTaskSettingsStore(db, userId: 'u1', defaults: const TaskSettings(startOfDay: '09:00', leadMinutes: 30, timeZone: 'UTC')).get();
    expect((d.timeZone, d.startOfDay, d.leadMinutes), ('UTC', '09:00', 30));
  });

  test('a row: NULL cells follow the defaults, set cells win and are overridden', () async {
    final db = settingsDb(rows: [
      {'id': 'u1', 'time_zone': 'Europe/Paris', 'start_of_day': null, 'end_of_day': '18:30', 'lead_minutes': 15},
    ]);
    final s = await PowerSyncTaskSettingsStore(db, userId: 'u1', defaults: const TaskSettings(startOfDay: '09:00')).get();
    expect((s.timeZone, s.startOfDay, s.endOfDay, s.leadMinutes), ('Europe/Paris', '09:00', '18:30', 15));
    expect(s.overridden, {'time_zone', 'end_of_day', 'lead_minutes'});
    expect(s.warnings, isEmpty);
  });

  test('update with no row inserts id plus only the columns set; a row updates only those', () async {
    final db = settingsDb();
    final store = PowerSyncTaskSettingsStore(db, userId: 'u1');
    final a = await store.update(const TaskSettingsPatch(timeZone: 'Europe/Paris', endOfDay: '18:30'));
    expect(writes(db).single.sql, 'INSERT INTO task_user_settings (id, time_zone, end_of_day) VALUES (?, ?, ?)');
    expect(writes(db).single.params, ['u1', 'Europe/Paris', '18:30']);
    expect(a.overridden, {'time_zone', 'end_of_day'});
    expect((a.timeZone, a.endOfDay, a.startOfDay), ('Europe/Paris', '18:30', '08:00'));
    db.statements.clear();
    final b = await store.update(const TaskSettingsPatch(leadMinutes: 15));
    expect(writes(db).single.sql, 'UPDATE task_user_settings SET lead_minutes = ? WHERE id = ?');
    expect(writes(db).single.params, [15, 'u1']);
    expect(b.leadMinutes, 15);
    expect(b.overridden, {'time_zone', 'end_of_day', 'lead_minutes'});
  });

  test('reset writes NULL (and wins over a value); the field leaves overridden; a reset with no row inserts NULLs', () async {
    final db = settingsDb();
    final store = PowerSyncTaskSettingsStore(db, userId: 'u1');
    await store.update(const TaskSettingsPatch(startOfDay: '07:00', endOfDay: '16:00'));
    db.statements.clear();
    final s = await store.update(const TaskSettingsPatch(endOfDay: '19:00', reset: {'end_of_day'}));
    expect(writes(db).single.sql, 'UPDATE task_user_settings SET end_of_day = ? WHERE id = ?');
    expect(writes(db).single.params, [null, 'u1']);
    expect(s.endOfDay, '17:00');
    expect(s.overridden, {'start_of_day'});
    final db2 = settingsDb();
    await PowerSyncTaskSettingsStore(db2, userId: 'u2').update(const TaskSettingsPatch(reset: {'lead_minutes'}));
    expect(writes(db2).single.sql, 'INSERT INTO task_user_settings (id, lead_minutes) VALUES (?, ?)');
    expect(writes(db2).single.params, ['u2', null]);
  });

  test('an empty patch writes nothing and returns the settings', () async {
    final db = settingsDb();
    final s = await PowerSyncTaskSettingsStore(db, userId: 'u1').update(const TaskSettingsPatch());
    expect(writes(db), isEmpty);
    expect(s.overridden, isEmpty);
  });

  test('a bad HH:MM throws ArgumentError and writes nothing', () async {
    final db = settingsDb();
    final store = PowerSyncTaskSettingsStore(db, userId: 'u1');
    for (final bad in ['25:00', '8:00', '', '12:60', 'noon', '08:00:00']) {
      await expectLater(store.update(TaskSettingsPatch(startOfDay: bad)), throwsArgumentError, reason: bad);
      await expectLater(store.update(TaskSettingsPatch(timeZone: 'UTC', endOfDay: bad)), throwsArgumentError, reason: bad);
    }
    expect(writes(db), isEmpty);
    await store.update(const TaskSettingsPatch(startOfDay: '00:00', endOfDay: '23:59'));
    expect(writes(db), hasLength(1));
  });

  test('lead_minutes outside 0..10080 throws ArgumentError and writes nothing; the bounds are accepted; the zone is not checked', () async {
    final db = settingsDb();
    final store = PowerSyncTaskSettingsStore(db, userId: 'u1');
    for (final bad in [-1, 10081]) {
      await expectLater(store.update(TaskSettingsPatch(timeZone: 'UTC', leadMinutes: bad)), throwsArgumentError, reason: '$bad');
    }
    expect(writes(db), isEmpty);
    await store.update(const TaskSettingsPatch(leadMinutes: 0));
    await store.update(const TaskSettingsPatch(leadMinutes: 10080));
    await store.update(const TaskSettingsPatch(timeZone: 'Not/AZone'));
    expect(writes(db), hasLength(3));
  });

  test('rename: SQL and rows use the local names; the wire names still come back', () async {
    final cols = {'id', ...renames.values};
    final db = settingsDb(table: 'user_prefs', cols: cols);
    final store = PowerSyncTaskSettingsStore(db, userId: 'u1', table: 'user_prefs', rename: renames);
    final a = await store.update(const TaskSettingsPatch(timeZone: 'UTC', leadMinutes: 5));
    expect(writes(db).single.sql, 'INSERT INTO user_prefs (id, tz, remind_lead) VALUES (?, ?, ?)');
    expect(db.tables['user_prefs']!.single['tz'], 'UTC');
    expect(a.overridden, {'time_zone', 'lead_minutes'});
    db.statements.clear();
    await store.update(const TaskSettingsPatch(startOfDay: '07:00', reset: {'time_zone'}));
    expect(writes(db).single.sql, 'UPDATE user_prefs SET tz = ?, day_start = ? WHERE id = ?');
    expect(writes(db).single.params, [null, '07:00', 'u1']);
    expect(db.statements.map((s) => s.sql).join(' '), isNot(contains('time_zone')));
  });

  test('an unsafe table or column name throws ArgumentError', () {
    PowerSyncTaskSettingsStore make({String table = 'task_user_settings', Map<String, String> rename = const {}}) =>
        PowerSyncTaskSettingsStore(settingsDb(), userId: 'u', table: table, rename: rename);
    for (final t in ['x; DROP TABLE y', 'Upper', 'a b', '', 'order', '1abc']) {
      expect(() => make(table: t), throwsArgumentError, reason: t);
      expect(() => taskSettingsTables(table: t), throwsArgumentError, reason: t);
    }
    for (final r in [
      {'nope': 'x'},
      {'time_zone': 'tz; --'},
      {'time_zone': 'Tz'},
      {'time_zone': 'id'},
      {'time_zone': '_metadata'},
      {'time_zone': 'start_of_day'},
      {'time_zone': 'group'},
      {'time_zone': 'z', 'lead_minutes': 'z'},
    ]) {
      expect(() => make(rename: r), throwsArgumentError, reason: '$r');
      expect(() => taskSettingsTables(rename: r), throwsArgumentError, reason: '$r');
    }
    make(rename: {'time_zone': 'time_zone'});
  });

  test('watch emits the settings and re-emits after a local write', () async {
    final db = settingsDb();
    final store = PowerSyncTaskSettingsStore(db, userId: 'u1');
    final seen = <TaskSettings>[];
    final sub = store.watch().listen(seen.add);
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    await store.update(const TaskSettingsPatch(leadMinutes: 15));
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    await sub.cancel();
    expect(db.changeSubscriptions.last, containsAll(['task_user_settings', 'ps_data__task_user_settings']));
    expect(seen.first.leadMinutes, 60);
    expect(seen.first.overridden, isEmpty);
    expect(seen.last.leadMinutes, 15);
    expect(seen.last.overridden, {'lead_minutes'});
  });

  test('a ZoneReporter over the store writes the device zone once, and not again when unchanged', () async {
    final db = settingsDb();
    final zone = _Zone('Europe/Paris');
    final reporter = ZoneReporter(zone, PowerSyncTaskSettingsStore(db, userId: 'u1'));
    await reporter.reportIfChanged();
    await reporter.reportIfChanged();
    expect(writes(db), hasLength(1));
    expect(writes(db).single.params, ['u1', 'Europe/Paris']);
    zone.zone = 'Asia/Tokyo';
    await reporter.reportIfChanged();
    expect(writes(db), hasLength(2));
    expect(writes(db).last.sql, 'UPDATE task_user_settings SET time_zone = ? WHERE id = ?');
    // a restart (new reporter) reads the stored zone and does not write it again
    await ZoneReporter(zone, PowerSyncTaskSettingsStore(db, userId: 'u1')).reportIfChanged();
    expect(writes(db), hasLength(2));
  });
}
