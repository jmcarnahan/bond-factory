@Tags(['real_db'])
@TestOn('vm')
library;

import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:legacy_phone/legacy_phone.dart';

import 'support.dart';

const _mine = ['o-timed', 'o-pm', 'o-dated', 'o-next', 'o-later', 'o-none'];

void main() {
  forEachStage('watchOpen: owner or assignee, open only, date then time, undated last', (env) async {
    final open = await env.repo.watchOpen().first;
    expect(ids(open), _mine);
    expect(ids(await env.repoFor('u-editor').watchOpen().first), ['o-pm', 'o-theirs'], reason: 'assigned to the editor, not owned');
  });

  forEachStage('watchOpen re-emits a created task in its place, newest created first within a day', (env) async {
    final w = Watch(env.repo.watchOpen());
    try {
      expect(ids(await w.first()), _mine, reason: 'before the write');
      env.tick();
      await env.repo.create(const TaskDraft(title: 'Fresh', id: 'n-1', dueDate: '2026-03-11', dueTime: '09:00'));
      final l = await w.next((l) => l.length == 7);
      expect(ids(l), ['n-1', 'o-timed', 'o-pm', 'o-dated', 'o-next', 'o-later', 'o-none'], reason: 'same date and time: newest created first');
    } finally {
      await w.cancel();
    }
  });

  forEachStage('old rows with no due_at: the instant comes from the date and time', (env) async {
    final timed = (await env.repo.getTask('o-timed'))!;
    expect(timed.dueAt, deviceDueAt('2026-03-11', '09:00'));
    expect(timed.overdue, isTrue, reason: '09:00 is before 13:00 local');
    final pm = (await env.repo.getTask('o-pm'))!;
    expect(pm.dueAt, deviceDueAt('2026-03-11', '17:00'));
    expect(pm.overdue, isFalse);
    final dated = (await env.repo.getTask('o-dated'))!;
    expect(dated.dueAt, isNull, reason: 'a date-only task has no instant');
    expect((await env.repo.getTask('o-none'))!.dueAt, isNull);
  });

  forEachStage('blank cells read as null; a NULL flag reads on and 0 reads off', (env) async {
    expect((await env.repo.getTask('o-timed'))!.assignedUserId, isNull, reason: "'' in assigned_user_id");
    expect((await env.repo.getTask('o-pm'))!.assignedUserId, 'u-editor');
    expect((await env.repo.getTask('o-pm'))!.mirrorEnabled, isTrue, reason: 'NULL sync_to_calendar means on');
    expect((await env.repo.getTask('o-dated'))!.mirrorEnabled, isFalse);
    final t = (await env.repo.getTask('o-timed'))!;
    expect(t.extras.keys, isNot(contains('sync_to_calendar')), reason: 'the renamed column is the flag, not an extra');
    expect(t.extras.keys, containsAll(['client_ref', 'case_ref', 'case_file_no']));
    expect(t.extras['case_file_no'], 101);
  });

  forEachStage('mirror state of rows read: stored when set, the write rule when the old build left none', (env) async {
    expect((await env.repo.getTask('o-timed'))!.mirrorStatus, MirrorStatus.mirrored);
    expect((await env.repo.getTask('o-dated'))!.mirrorStatus, MirrorStatus.skipped);
    expect((await env.repo.getTask('o-none'))!.mirrorStatus, MirrorStatus.skipped, reason: 'NULL and undated');
  });

  forEachStage('getTask and watchTask: a missing id is null', (env) async {
    expect(await env.repo.getTask('nope'), isNull);
    expect(await env.repo.watchTask('nope').first, isNull);
    expect((await env.repo.getTask('o-later'))!.title, 'Old later');
    expect((await env.repo.watchTask('o-later').first)!.id, 'o-later');
    // not owner-filtered: a task of somebody else still reads by id
    expect((await env.repo.getTask('o-theirs'))!.title, 'Not mine');
  });

  forEachStage('watchTask re-emits an update and then null after a delete', (env) async {
    final w = Watch(env.repo.watchTask('o-later'));
    try {
      expect((await w.first())!.title, 'Old later');
      env.tick();
      await env.repo.update('o-later', const TaskPatch(title: 'Renamed'));
      expect((await w.next((t) => t?.title == 'Renamed'))!.title, 'Renamed');
      await env.repo.delete('o-later');
      expect(await w.next((t) => t == null), isNull);
    } finally {
      await w.cancel();
    }
  });

  forEachStage('summary counts open, overdue, due today and no date by the device clock', (env) async {
    final s = await env.repo.summary();
    expect((s.open, s.overdue, s.dueToday, s.noDate), (6, 1, 2, 1));
  });

  forEachStage('today(): overdue, today, no date and done today', (env) async {
    final t = await env.repo.today();
    expect(ids(t.overdue), ['o-timed']);
    expect(ids(t.today), ['o-pm', 'o-dated']);
    expect(ids(t.undated), ['o-none']);
    expect(ids(t.doneToday), ['o-done']);
    expect((t.counts.overdue, t.counts.today, t.counts.undated, t.counts.doneToday), (1, 2, 1, 1));
  });

  forEachStage('list(): the same order, a status filter and a page', (env) async {
    final open = await env.repo.list(const TaskFilters(status: 'open'));
    expect(ids(open.items), _mine);
    final all = await env.repo.list(const TaskFilters(status: 'all', limit: 3));
    expect((all.total, all.items.length), (7, 3));
    final page = await env.repo.list(const TaskFilters(status: 'open', limit: 2, offset: 2));
    expect(ids(page.items), ['o-dated', 'o-next']);
    expect(ids((await env.repo.list(const TaskFilters(status: 'done'))).items), ['o-done']);
    expect(ids((await env.repo.list(const TaskFilters(status: 'open', noDate: true))).items), ['o-none']);
  });

  forEachStage('watchList is the list as a live snapshot', (env) async {
    final w = Watch(env.repo.watchList(const TaskFilters(status: 'open')));
    try {
      expect((await w.first()).total, 6);
      env.tick();
      await env.repo.create(const TaskDraft(title: 'More', id: 'n-2'));
      final p = await w.next((p) => p.total == 7);
      expect(ids(p.items).sublist(4), ['o-later', 'n-2', 'o-none'], reason: 'undated: newest created first');
    } finally {
      await w.cancel();
    }
  });

  // A limit, pinned: the shape picks `dateThenTime` by itself only while `due_at` is absent. After the app adds the
  // column its old rows still have none, so the app names the order (legacy_store.dart does).
  test('limit: at the wide stage the default order is by due_at, which the old rows lack [widened]', () async {
    final env = await openEnv(LegacyStage.widened);
    try {
      final repo = PowerSyncTaskRepository(
        env.db,
        userId: 'u-owner',
        clock: env.clock,
        shape: const TaskTableShape(rename: {'mirror_enabled': 'sync_to_calendar'}),
        extraColumns: const {'client_ref', 'case_ref', 'case_file_no'},
      );
      expect(ids(await repo.watchOpen().first), ['o-none', 'o-later', 'o-next', 'o-dated', 'o-pm', 'o-timed'],
          reason: 'every row ties on a NULL due_at, so the newest created comes first');
    } finally {
      await env.close();
    }
  });
}
