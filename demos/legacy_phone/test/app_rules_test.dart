@Tags(['real_db'])
@TestOn('vm')
library;

import 'package:bond_tasks/bond_tasks.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

Future<List<Object?>> links(LegacyEnv env, String id) async {
  final r = await env.row(id);
  return [r['client_ref'], r['case_ref'], r['case_file_no']];
}

void main() {
  forEachStage('a blank link is stored NULL', (env) async {
    await env.repo.create(const TaskDraft(title: 'x', id: 'n-1', extras: {'client_ref': '', 'case_ref': '  '}));
    expect(await links(env, 'n-1'), [null, null, null]);
    env.tick();
    await env.repo.update('o-timed', const TaskPatch(extras: {'client_ref': ''}));
    expect((await env.row('o-timed'))['client_ref'], isNull);
  });

  forEachStage('a case implies its client', (env) async {
    await env.repo.create(const TaskDraft(title: 'x', id: 'n-1', extras: {'case_ref': 'ca-2'}));
    expect(await links(env, 'n-1'), ['cl-2', 'ca-2', 202]);
    // an old row with a case and a blank client gets the client when the case is written again
    await env.db.execute("UPDATE tasks SET client_ref = '' WHERE id = 'o-timed'");
    env.tick();
    await env.repo.update('o-timed', const TaskPatch(extras: {'case_ref': 'ca-3'}));
    expect(await links(env, 'o-timed'), ['cl-1', 'ca-3', 303]);
  });

  forEachStage('changing the case re-derives case_file_no from cases', (env) async {
    expect(await links(env, 'o-timed'), ['cl-1', 'ca-1', 101]);
    env.tick();
    await env.repo.update('o-timed', const TaskPatch(extras: {'case_ref': 'ca-3'}));
    expect(await links(env, 'o-timed'), ['cl-1', 'ca-3', 303]);
    await env.db.execute("UPDATE cases SET file_no = 304 WHERE id = 'ca-3'");
    env.tick();
    await env.repo.update('o-timed', const TaskPatch(title: 'a title edit leaves the number alone'));
    expect((await env.row('o-timed'))['case_file_no'], 303);
  });

  forEachStage('clearing the case clears case_file_no; an unknown case has no number; a number named in the write wins', (env) async {
    env.tick();
    await env.repo.update('o-timed', const TaskPatch(extras: {'case_ref': null}));
    expect(await links(env, 'o-timed'), ['cl-1', null, null]);
    env.tick();
    await env.repo.update('o-timed', const TaskPatch(extras: {'case_ref': 'no-such-case'}));
    expect(await links(env, 'o-timed'), ['cl-1', 'no-such-case', null]);
    env.tick();
    await env.repo.update('o-timed', const TaskPatch(extras: {'case_ref': 'ca-3', 'case_file_no': 999}));
    expect(await links(env, 'o-timed'), ['cl-1', 'ca-3', 999]);
  });

  forEachStage('a rule that throws leaves no row and no queue entry', (env) async {
    // ca-1 belongs to cl-1: refused for a task of cl-2
    await expectLater(
      env.repo.create(const TaskDraft(title: 'x', id: 'n-1', extras: {'client_ref': 'cl-2', 'case_ref': 'ca-1'})),
      throwsA(isA<StateError>().having((e) => e.message, 'message', 'case_belongs_to_another_client')),
    );
    expect(await env.exists('n-1'), isFalse);
    expect(await drain(env.db), isEmpty);
    env.tick();
    await expectLater(env.repo.update('o-timed', const TaskPatch(title: 'changed', extras: {'case_ref': 'ca-2'})), throwsStateError);
    expect((await env.row('o-timed'))['title'], 'Old timed', reason: 'the whole write rolled back');
    expect(await links(env, 'o-timed'), ['cl-1', 'ca-1', 101]);
    expect(await drain(env.db), isEmpty);
  });

  forEachStage('a status change is not an occasion for the link rules', (env) async {
    await env.db.execute("UPDATE tasks SET client_ref = '' WHERE id = 'o-timed'");
    await drain(env.db);
    env.tick();
    await env.repo.complete('o-timed');
    expect((await env.row('o-timed'))['client_ref'], '', reason: 'complete writes the status columns only');
  });
}
