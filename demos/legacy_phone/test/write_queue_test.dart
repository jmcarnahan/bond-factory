@Tags(['real_db'])
@TestOn('vm')
library;

import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:legacy_phone/legacy_phone.dart';

import 'support.dart';

/// Every key an entry queues is a column of the stage's table, never the module's name for the flag.
void expectLegacyKeys(LegacyEnv env, SyncCrudEntry e, {Set<String>? exactly, Set<String> required = const {}}) {
  final keys = e.opData!.keys.toSet();
  expect(keys.difference(env.columns), isEmpty, reason: '${e.op} ${e.id} names a column the table lacks');
  expect(keys, isNot(contains('mirror_enabled')));
  expect(keys, isNot(contains('id')));
  if (env.stage == LegacyStage.asShipped) expect(keys.intersection(kMissingColumns.toSet()), isEmpty);
  if (exactly != null) expect(keys, exactly, reason: '${e.op} ${e.id}');
  expect(keys, containsAll(required));
}

void main() {
  forEachStage('create, update, complete, reopen, cancel, delete queue only legacy columns', (env) async {
    final wide = env.stage == LegacyStage.widened;
    final created = await env.repo.create(const TaskDraft(
      title: 'Call',
      id: 'n-1',
      dueDate: '2026-03-20',
      dueTime: '09:30',
      priority: TaskPriority.high,
      checklist: [ChecklistItem(id: 'c1', text: 'one')],
      extras: {'client_ref': 'cl-1', 'case_ref': 'ca-1'},
    ));
    expect(created.title, 'Call');
    expect(created.priority, wide ? TaskPriority.high : isNull, reason: 'an absent column drops the value, silently');
    expect(created.checklist, wide ? hasLength(1) : isEmpty);
    env.tick();
    await env.repo.update('n-1', const TaskPatch(title: 'Call back', extras: {'case_ref': null}));
    env.tick();
    final done = await env.repo.complete('n-1');
    expect(done.status, TaskStatus.done);
    env.tick();
    await env.repo.reopen('n-1');
    env.tick();
    final cancelled = await env.repo.cancel('n-1');
    expect(cancelled.status, TaskStatus.cancelled);
    env.tick();
    await env.repo.delete('n-1');

    final q = await drain(env.db);
    expect(q.map((e) => (e.op, e.table, e.id)), [
      ('put', 'tasks', 'n-1'),
      ('patch', 'tasks', 'n-1'),
      ('patch', 'tasks', 'n-1'),
      ('patch', 'tasks', 'n-1'),
      ('patch', 'tasks', 'n-1'),
      ('delete', 'tasks', 'n-1'),
    ]);
    final put = q[0];
    expectLegacyKeys(env, put, required: {
      'title', 'owner_user_id', 'created_by', 'status', 'sync_to_calendar', 'client_ref', 'case_ref', 'case_file_no',
      'mirror_status', 'due_date', 'due_time', 'source', 'created_at', 'updated_at', //
    });
    expect(put.opData!['title'], 'Call');
    expect(put.opData!['owner_user_id'], 'u-owner');
    expect(put.opData!['sync_to_calendar'], 1, reason: 'the flag lives in sync_to_calendar');
    expect((put.opData!['client_ref'], put.opData!['case_ref'], put.opData!['case_file_no']), ('cl-1', 'ca-1', 101));
    expect((put.opData!['status'], put.opData!['mirror_status'], put.opData!['source']), ('open', 'pending', 'manual'));
    expect(put.opData!.containsKey('priority'), wide);
    expect(put.opData!.containsKey('due_at'), wide);
    if (wide) {
      expect(put.opData!['priority'], 3);
      expect(put.opData!['due_at'], isNotNull);
    }
    expectLegacyKeys(env, q[1], exactly: {'title', 'case_ref', 'case_file_no', 'updated_at'});
    expect((q[1].opData!['title'], q[1].opData!['case_ref'], q[1].opData!['case_file_no']), ('Call back', null, null));
    expect(q[1].metadata, isNull);
    expectLegacyKeys(env, q[2], exactly: {'status', 'completed_at', 'completed_by', 'mirror_status', 'updated_at'});
    expect(q[2].metadata, '{"action":"complete"}');
    expect(q[3].metadata, '{"action":"reopen"}');
    expectLegacyKeys(env, q[3], exactly: {'status', 'completed_at', 'completed_by', 'mirror_status', 'updated_at'});
    expect(q[4].metadata, '{"action":"cancel"}');
    expectLegacyKeys(env, q[4], exactly: {'status', 'mirror_status', 'updated_at'});
    expect(q[4].opData!['status'], 'cancelled');
    expect(q[5].opData, isNull);
  });

  forEachStage('the flag goes to sync_to_calendar as 0 or 1 and reads back', (env) async {
    await env.repo.create(const TaskDraft(title: 'Off', id: 'n-1', mirrorEnabled: false));
    await env.repo.create(const TaskDraft(title: 'On', id: 'n-2'));
    expect(((await env.row('n-1'))['sync_to_calendar'], (await env.row('n-2'))['sync_to_calendar']), (0, 1));
    env.tick();
    final back = await env.repo.update('n-1', const TaskPatch(mirrorEnabled: true));
    expect(back.mirrorEnabled, isTrue);
    expect((await env.row('n-1'))['sync_to_calendar'], 1);
    final patch = (await drain(env.db)).where((e) => e.op == 'patch').single;
    expectLegacyKeys(env, patch, exactly: {'sync_to_calendar', 'updated_at'});
    expect(patch.opData!['sync_to_calendar'], 1);
  });

  forEachStage('a patch of an absent column writes nothing and queues nothing', (env) async {
    env.tick();
    await env.repo.update('o-later', const TaskPatch(priority: Present(TaskPriority.low)));
    final q = await drain(env.db);
    if (env.stage == LegacyStage.asShipped) {
      expect(q, isEmpty, reason: 'the only column the patch names is not in the table');
    } else {
      expect(q.single.opData!['priority'], 1);
    }
  });

  forEachStage('a timed update at the wide stage writes the instant, at the narrow stage it does not exist', (env) async {
    env.tick();
    await env.repo.update('o-later', const TaskPatch(dueTime: Present('10:15')));
    final e = (await drain(env.db)).single;
    expectLegacyKeys(env, e, required: {'due_time', 'updated_at'});
    expect(e.opData!.containsKey('due_at'), env.stage == LegacyStage.widened);
    expect((await env.repo.getTask('o-later'))!.dueAt, deviceDueAt('2026-03-20', '10:15'));
  });

  forEachStage('writes on old rows: complete a row the old build wrote', (env) async {
    env.tick();
    final t = await env.repo.complete('o-timed');
    expect((t.status, t.completedAt), (TaskStatus.done, env.now));
    final e = (await drain(env.db)).single;
    expect(e.op, 'patch');
    expect(e.metadata, '{"action":"complete"}');
    expect(e.opData!['status'], 'done');
  });
}
