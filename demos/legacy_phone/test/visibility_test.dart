@Tags(['real_db'])
@TestOn('vm')
library;

/// Who sees what: the local database holds other users' rows too (a global stream), and the app picks in SQL.
import 'package:bond_tasks/bond_tasks.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

Future<void> addOthers(LegacyEnv env) async {
  for (var i = 1; i <= 3; i++) {
    await env.db.execute(
      "INSERT INTO tasks (id, owner_user_id, created_by, title, client_ref, status, due_date, source, created_at, updated_at) "
      "VALUES (?, 'u-other', 'u-other', ?, 'cl-1', 'open', '2026-03-1$i', 'app', ?, ?)",
      ['x-$i', 'Other $i', '2026-03-0${i}T10:00:00.000Z', '2026-03-0${i}T10:00:00.000Z'],
    );
  }
  await drain(env.db);
}

void main() {
  const mineAll = ['o-done', 'o-timed', 'o-pm', 'o-dated', 'o-next', 'o-later', 'o-none'];

  forEachStage('mine: owner or assignee, in SQL, with limit and total', (env) async {
    await addOthers(env);
    final all = await env.repo.listWhere({}, mine: true);
    expect(ids(all.items), mineAll);
    expect((all.total, all.limit, all.offset), (7, 25, 0));
    final page = await env.repo.listWhere({}, mine: true, limit: 3, offset: 2);
    expect(ids(page.items), mineAll.sublist(2, 5));
    expect((page.total, page.items.length), (7, 3), reason: 'total counts every match of mine');
    final open = await env.repo.listWhere({}, mine: true, status: 'open');
    expect(ids(open.items), ids(await env.repo.watchOpen().first), reason: 'the same list as watchOpen');
    expect(open.total, 6);
    expect(ids((await env.repoFor('u-editor').listWhere({}, mine: true)).items), ['o-pm', 'o-theirs'],
        reason: 'the editor owns none and is assigned two');
  });

  forEachStage('a linked record: everyone on it, or only mine', (env) async {
    await addOthers(env);
    final everyone = await env.repo.listWhere({'client_ref': 'cl-1'});
    expect(everyone.total, 7);
    expect(ids(everyone.items).toSet(), {'o-done', 'o-timed', 'o-theirs', 'o-none', 'x-1', 'x-2', 'x-3'});
    final mine = await env.repo.listWhere({'client_ref': 'cl-1'}, mine: true);
    expect(mine.total, 3);
    expect(ids(mine.items), ['o-done', 'o-timed', 'o-none']);
    final page = await env.repo.listWhere({'client_ref': 'cl-1'}, limit: 2, offset: 4);
    expect((page.total, page.items.length), (7, 2));
  });

  forEachStage('everyone: an empty filter, with limit and total', (env) async {
    await addOthers(env);
    final all = await env.repo.listWhere({}, limit: 4);
    expect((all.total, all.items.length), (11, 4));
    expect((await env.repo.listWhere({}, status: 'done')).total, 1);
    expect((await env.repo.listWhere({}, status: 'open')).total, 10);
    expect((await env.repo.listWhere({}, offset: 10)).items.length, 1);
  });

  forEachStage('watchWhere over everyone grows with another user\'s row; mine does not', (env) async {
    final everyone = Watch(env.repo.watchWhere({}));
    final mine = Watch(env.repo.watchWhere({}, mine: true));
    try {
      expect((await everyone.first()).total, 8);
      expect((await mine.first()).total, 7);
      await addOthers(env);
      expect((await everyone.next((p) => p.total == 11)).total, 11);
      expect((await env.repo.listWhere({}, mine: true)).total, 7);
      await env.repo.create(const TaskDraft(title: 'Mine too', id: 'n-1'));
      expect((await mine.next((p) => p.total == 8)).total, 8);
    } finally {
      await Future.wait([everyone.cancel(), mine.cancel()]);
    }
  });
}
