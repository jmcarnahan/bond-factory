@Tags(['real_db'])
@TestOn('vm')
library;

import 'package:bond_tasks/bond_tasks.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

void main() {
  forEachStage('complete writes completed_by as the user; reopen clears it; cancel clears it', (env) async {
    env.tick();
    final done = await env.repo.complete('o-timed');
    expect(done.status, TaskStatus.done);
    expect((await env.row('o-timed'))['completed_by'], 'u-owner');
    env.tick();
    await env.repo.reopen('o-timed');
    expect((await env.row('o-timed'))['completed_by'], isNull);
    env.tick();
    await env.repo.complete('o-timed');
    env.tick();
    await env.repo.cancel('o-timed');
    final row = await env.row('o-timed');
    expect((row['status'], row['completed_by'], row['completed_at']), ('cancelled', null, null));
  });

  forEachStage('the assignee completing a task is the one recorded', (env) async {
    env.tick();
    await env.repoFor('u-editor').complete('o-pm');
    expect((await env.row('o-pm'))['completed_by'], 'u-editor');
  });

  forEachStage('reopening a task the old build completed clears its completed_by', (env) async {
    expect((await env.row('o-done'))['completed_by'], 'u-owner');
    env.tick();
    await env.repo.reopen('o-done');
    final row = await env.row('o-done');
    expect((row['status'], row['completed_by'], row['completed_at']), ('open', null, null));
  });

  forEachStage('a status already reached writes nothing', (env) async {
    env.tick();
    await env.repo.complete('o-done');
    await env.repo.reopen('o-later');
    expect(await drain(env.db), isEmpty);
  });
}
