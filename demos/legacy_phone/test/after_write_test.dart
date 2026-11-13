@Tags(['real_db'])
@TestOn('vm')
library;

import 'package:bond_tasks/bond_tasks.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

Future<void> reject(LegacyEnv env, String id, {String n = '1'}) => env.db.execute(
      'INSERT INTO sync_rejections (id, table_name, row_id, action, code, message, payload, created_at, op) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
      ['r-$id-$n', 'tasks', id, null, 'forbidden', 'not_task_owner', '{}', '2026-03-11T19:00:00.000Z', 'patch'],
    );

Future<List<String>> noted(LegacyEnv env) async =>
    [for (final r in await env.db.getAll('SELECT row_id FROM sync_rejections ORDER BY row_id')) r['row_id']! as String];

void main() {
  forEachStage('create clears an earlier refusal of the same id', (env) async {
    await reject(env, 'n-1');
    await reject(env, 'o-later');
    await env.repo.create(const TaskDraft(title: 'x', id: 'n-1'));
    expect(await noted(env), ['o-later']);
  });

  forEachStage('update, complete, reopen and delete each clear the note of their task and only theirs', (env) async {
    final other = 'o-none';
    await reject(env, other);
    for (final (id, act) in <(String, Future<Object?> Function(String))>[
      ('o-later', (i) => env.repo.update(i, const TaskPatch(title: 'edited'))),
      ('o-timed', env.repo.complete),
      ('o-done', env.repo.reopen),
      ('o-pm', env.repo.cancel),
      ('o-dated', env.repo.delete),
    ]) {
      await reject(env, id);
      env.tick();
      await act(id);
      expect(await noted(env), [other], reason: 'after the write of $id');
    }
  });

  forEachStage('a write that changes nothing leaves the note', (env) async {
    await reject(env, 'o-done');
    await env.repo.complete('o-done'); // already done
    await reject(env, 'o-later');
    await env.repo.update('o-later', const TaskPatch());
    expect(await noted(env), ['o-done', 'o-later']);
  });

  forEachStage('a write that fails leaves the note', (env) async {
    await reject(env, 'o-timed');
    await expectLater(env.repo.update('o-timed', const TaskPatch(extras: {'case_ref': 'ca-2'})), throwsStateError);
    expect(await noted(env), ['o-timed']);
  });
}
