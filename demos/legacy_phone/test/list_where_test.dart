@Tags(['real_db'])
@TestOn('vm')
library;

import 'package:bond_tasks/bond_tasks.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:legacy_phone/legacy_phone.dart';

import 'support.dart';

void main() {
  forEachStage('listWhere by client_ref: every status, not owner-filtered, the app order', (env) async {
    final page = await env.repo.listWhere({'client_ref': 'cl-1'});
    expect(ids(page.items), ['o-done', 'o-timed', 'o-theirs', 'o-none']);
    expect((page.total, page.limit, page.offset), (4, 25, 0));
    final other = await env.repoFor('u-editor').listWhere({'client_ref': 'cl-1'});
    expect(ids(other.items), ids(page.items), reason: 'the caller does not narrow it');
  });

  forEachStage('listWhere by case_ref, with a status, a limit and an offset', (env) async {
    expect(ids((await env.repo.listWhere({'case_ref': 'ca-1'})).items), ['o-timed']);
    expect(ids((await env.repo.listWhere({'case_ref': 'ca-2'})).items), ['o-next'], reason: 'owned by someone else');
    expect(ids((await env.repo.listWhere({'client_ref': 'cl-1'}, status: 'open')).items), ['o-timed', 'o-theirs', 'o-none']);
    expect(ids((await env.repo.listWhere({'client_ref': 'cl-1'}, status: 'done')).items), ['o-done']);
    expect((await env.repo.listWhere({'client_ref': 'cl-1'}, status: 'all')).total, 4, reason: 'not a status: no filter');
    final page = await env.repo.listWhere({'client_ref': 'cl-1'}, limit: 2, offset: 1);
    expect(ids(page.items), ['o-timed', 'o-theirs']);
    expect((page.total, page.limit, page.offset), (4, 2, 1), reason: 'total counts every match, not the page');
    expect((await env.repo.listWhere({'client_ref': 'cl-1'}, limit: 2, offset: 9)).items, isEmpty);
  });

  forEachStage('listWhere: two keys, a null value, a module name through the shape', (env) async {
    expect(ids((await env.repo.listWhere({'client_ref': 'cl-1', 'case_ref': 'ca-1'})).items), ['o-timed']);
    final nulls = await env.repo.listWhere({'case_ref': null}, status: 'open');
    expect(ids(nulls.items).toSet(), {'o-pm', 'o-dated', 'o-later', 'o-none', 'o-theirs'}, reason: 'IS NULL, not the blank');
    final off = await env.repo.listWhere({'mirror_enabled': 0});
    expect(ids(off.items), ['o-dated'], reason: 'mirror_enabled is sync_to_calendar here');
    expect(ids((await env.repo.listWhere({'assigned_user_id': 'u-editor'})).items), ['o-pm', 'o-theirs']);
  });

  forEachStage('listWhere refuses an empty map and an unknown key', (env) async {
    expect(() => env.repo.listWhere({}), throwsArgumentError);
    expect(() => env.repo.listWhere({'bogus': 1}), throwsArgumentError);
    expect(() => env.repo.listWhere({'sync_to_calendar': 1}), throwsArgumentError, reason: 'a local name is not a module name');
    expect(() => env.repo.listWhere({'id; DROP TABLE tasks': 1}), throwsArgumentError);
    if (env.stage == LegacyStage.asShipped) {
      expect(() => env.repo.listWhere({'priority': 3}), throwsArgumentError, reason: 'a column the table lacks is never named');
    }
  });

  forEachStage('the filter and the count run in SQL', (env) async {
    final rec = RecordingDb(env.db);
    final repo = env.repoFor('u-owner', rec);
    await repo.listWhere({'client_ref': 'cl-1'}, limit: 2);
    final selects = rec.sql.where((q) => q.contains('FROM tasks')).toList();
    expect(selects.any((q) => RegExp(r'^SELECT \* FROM tasks WHERE client_ref = \? .*LIMIT \? OFFSET \?$').hasMatch(q.trim())), isTrue,
        reason: selects.join('\n'));
    expect(selects.any((q) => q.contains('SELECT COUNT(*) AS n FROM tasks WHERE client_ref = ?')), isTrue, reason: selects.join('\n'));
  });

  forEachStage('watchWhere re-emits when a matching row is written or leaves the filter', (env) async {
    final w = Watch(env.repo.watchWhere({'client_ref': 'cl-1'}));
    try {
      expect((await w.first()).total, 4, reason: 'before any write');
      env.tick();
      await env.repo.create(const TaskDraft(title: 'Another', id: 'n-1', extras: {'client_ref': 'cl-1'}));
      final five = await w.next((p) => p.total == 5);
      expect(ids(five.items), contains('n-1'));
      env.tick();
      await env.repo.update('n-1', const TaskPatch(extras: {'client_ref': 'cl-2'}));
      final back = await w.next((p) => p.total == 4);
      expect(ids(back.items), isNot(contains('n-1')), reason: 'the row left the client');
    } finally {
      await w.cancel();
    }
  });

  forEachStage('a case filter reads the case of a task written through the store', (env) async {
    env.tick();
    await env.repo.create(const TaskDraft(title: 'On the case', id: 'n-2', extras: {'case_ref': 'ca-3'}));
    final page = await env.repo.listWhere({'case_ref': 'ca-3'});
    expect(ids(page.items), ['n-2']);
    expect(page.items.single.extras['client_ref'], 'cl-1', reason: 'the case implied its client');
    expect(page.items.single.extras['case_file_no'], 303);
  });
}
