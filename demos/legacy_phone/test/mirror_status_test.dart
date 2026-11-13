@Tags(['real_db'])
@TestOn('vm')
library;

import 'package:bond_tasks/bond_tasks.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

Future<String?> stored(LegacyEnv env, String id) async => (await env.row(id))['mirror_status'] as String?;

void main() {
  forEachStage('create: undated skipped, dated pending, flag off skipped', (env) async {
    await env.repo.create(const TaskDraft(title: 'a', id: 'n-undated'));
    await env.repo.create(const TaskDraft(title: 'b', id: 'n-dated', dueDate: '2026-03-20'));
    await env.repo.create(const TaskDraft(title: 'c', id: 'n-off', dueDate: '2026-03-20', mirrorEnabled: false));
    expect([await stored(env, 'n-undated'), await stored(env, 'n-dated'), await stored(env, 'n-off')], ['skipped', 'pending', 'skipped']);
    // the task a write returns says the same
    final t = await env.repo.getTask('n-dated');
    expect(t!.mirrorStatus, MirrorStatus.pending);
  });

  forEachStage('clearing the date of a pending task skips it', (env) async {
    await env.repo.create(const TaskDraft(title: 'b', id: 'n-dated', dueDate: '2026-03-20', dueTime: '10:00'));
    env.tick();
    final t = await env.repo.update('n-dated', const TaskPatch(dueDate: Present(null)));
    expect(await stored(env, 'n-dated'), 'skipped');
    expect(t.mirrorStatus, MirrorStatus.skipped);
  });

  forEachStage('complete of a mirrored task is pending (the event must go); complete of a pending one is skipped', (env) async {
    expect(await stored(env, 'o-timed'), 'mirrored');
    env.tick();
    await env.repo.complete('o-timed');
    expect(await stored(env, 'o-timed'), 'pending');
    env.tick();
    await env.repo.complete('o-later');
    expect(await stored(env, 'o-later'), 'skipped');
  });

  forEachStage('reopen of a dated task is pending, of an undated one skipped; cancel follows complete', (env) async {
    env.tick();
    await env.repo.reopen('o-done'); // dated 2026-03-10, flag on
    expect(await stored(env, 'o-done'), 'pending');
    await env.repo.complete('o-none');
    env.tick();
    await env.repo.reopen('o-none');
    expect(await stored(env, 'o-none'), 'skipped');
    env.tick();
    await env.repo.cancel('o-later');
    expect(await stored(env, 'o-later'), 'skipped');
    env.tick();
    await env.repo.cancel('o-timed'); // mirrored: the event must go
    expect(await stored(env, 'o-timed'), 'pending');
  });

  forEachStage('a failed row is recomputed on the next update', (env) async {
    await env.db.execute("UPDATE tasks SET mirror_status = 'failed' WHERE id = 'o-later'");
    await drain(env.db);
    expect((await env.repo.getTask('o-later'))!.mirrorStatus, MirrorStatus.failed, reason: 'a read shows the stored state');
    env.tick();
    await env.repo.update('o-later', const TaskPatch(title: 'again'));
    expect(await stored(env, 'o-later'), 'pending');
  });

  forEachStage('an update that writes nothing does not touch mirror_status', (env) async {
    await env.db.execute("UPDATE tasks SET mirror_status = 'failed' WHERE id = 'o-later'");
    await drain(env.db);
    env.tick();
    await env.repo.update('o-later', const TaskPatch());
    expect(await stored(env, 'o-later'), 'failed');
    expect(await drain(env.db), isEmpty);
  });

  forEachStage('a write returns the same state the next read shows', (env) async {
    env.tick();
    final t = await env.repo.complete('o-timed');
    expect(t.mirrorStatus, (await env.repo.getTask('o-timed'))!.mirrorStatus);
  });
}
