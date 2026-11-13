@Tags(['real_db'])
@TestOn('vm')
library;

import 'package:bond_tasks/bond_tasks.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

void expectNames(Task t, {String? owner, String? assignee, String? client, String? kase}) {
  expect((t.ownerName, t.assigneeName, t.extras['client_name'], t.extras['case_label']), (owner, assignee, client, kase), reason: t.id);
}

void main() {
  forEachStage('every read carries owner and assignee names, the client name and the case label', (env) async {
    // o-timed: owner Olive, no assignee ('' in the row), client Ada Lovelace, case Contract review
    void timed(Task? t) => expectNames(t!, owner: 'Olive Owner', client: 'Ada Lovelace', kase: 'Contract review');
    timed((await env.repo.watchOpen().first).firstWhere((t) => t.id == 'o-timed'));
    timed(await env.repo.getTask('o-timed'));
    timed(await env.repo.watchTask('o-timed').first);
    timed((await env.repo.list(const TaskFilters(status: 'all'))).items.firstWhere((t) => t.id == 'o-timed'));
    timed((await env.repo.listWhere({'case_ref': 'ca-1'})).items.single);
    timed((await env.repo.today()).overdue.single);
    timed((await env.repo.watchList(const TaskFilters(status: 'open')).first).items.firstWhere((t) => t.id == 'o-timed'));
    timed((await env.repo.watchWhere({'case_ref': 'ca-1'}).first).items.single);
  });

  forEachStage('a name falls back to the email; one name part is enough; unknown ids read null', (env) async {
    expectNames((await env.repo.getTask('o-pm'))!, owner: 'Olive Owner', assignee: 'editor@example.com');
    expectNames((await env.repo.getTask('o-next'))!, owner: 'Otto Other', assignee: 'Olive Owner', client: 'Grace', kase: 'Estate');
    expectNames((await env.repo.getTask('o-dated'))!, owner: 'Olive Owner'); // client_ref '' reads no name
    await env.db.execute("UPDATE tasks SET client_ref = 'gone', case_ref = 'gone-too' WHERE id = 'o-later'");
    expectNames((await env.repo.getTask('o-later'))!, owner: 'Olive Owner');
  });

  forEachStage('the day view carries names for done rows too', (env) async {
    expectNames((await env.repo.today()).doneToday.single, owner: 'Olive Owner', client: 'Ada Lovelace');
  });

  /// Starts the three watches, checks each first emission holds the OLD name, runs [write], and needs a later emission with the new one.
  Future<void> reemitsAll(LegacyEnv env, bool Function(Task?) isOld, bool Function(Task?) isNew, Future<void> Function() write) async {
    final open = Watch(env.repo.watchOpen());
    final one = Watch(env.repo.watchTask('o-timed'));
    final page = Watch(env.repo.watchWhere({'client_ref': 'cl-1', 'case_ref': 'ca-1'}));
    try {
      expect((await open.first()).firstWhere((t) => t.id == 'o-timed'), predicate<Task>(isOld), reason: 'watchOpen before');
      expect(await one.first(), predicate<Task?>(isOld), reason: 'watchTask before');
      expect((await page.first()).items.single, predicate<Task>(isOld), reason: 'watchWhere before');
      await write();
      expect((await open.next((l) => l.any(isNew))).firstWhere((t) => t.id == 'o-timed'), predicate<Task>(isNew));
      expect(await one.next(isNew), predicate<Task?>(isNew));
      expect((await page.next((p) => p.items.any(isNew))).items.single, predicate<Task>(isNew));
    } finally {
      await Future.wait([open.cancel(), one.cancel(), page.cancel()]);
    }
  }

  forEachStage('a users row update re-emits watchOpen, watchTask and watchWhere with the new name', (env) async {
    await reemitsAll(env, (t) => t?.ownerName == 'Olive Owner', (t) => t?.ownerName == 'Olive Renamed',
        () => env.db.execute("UPDATE users SET name = 'Olive Renamed' WHERE id = 'u-owner'"));
  });

  forEachStage('a clients row update re-emits all three with the new client name', (env) async {
    await reemitsAll(env, (t) => t?.extras['client_name'] == 'Ada Lovelace', (t) => t?.extras['client_name'] == 'Ada Byron',
        () => env.db.execute("UPDATE clients SET last_name = 'Byron' WHERE id = 'cl-1'"));
  });

  forEachStage('a cases row update re-emits all three with the new case label', (env) async {
    await reemitsAll(env, (t) => t?.extras['case_label'] == 'Contract review', (t) => t?.extras['case_label'] == 'Contract renewed',
        () => env.db.execute("UPDATE cases SET label = 'Contract renewed' WHERE id = 'ca-1'"));
  });

  forEachStage('a create returns the task with its names', (env) async {
    env.tick();
    final t = await env.repo.create(const TaskDraft(title: 'New', id: 'n-1', assignedUserId: 'u-editor', extras: {'case_ref': 'ca-1'}));
    expectNames(t, owner: 'Olive Owner', assignee: 'editor@example.com', client: 'Ada Lovelace', kase: 'Contract review');
  });
}
