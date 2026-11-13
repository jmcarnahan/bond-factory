@Tags(['real_db'])
@TestOn('vm')
library;

/// Facts an adopter pinned: what an old build and an old row do to the store.
import 'package:bond_tasks/bond_tasks.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:legacy_phone/legacy_phone.dart';

import 'support.dart';

void main() {
  forEachStage('an edit of an old row never queues a column it did not change (the new columns stay unwritten)', (env) async {
    env.tick();
    await env.repo.update('o-later', const TaskPatch(title: 'Edited'));
    env.tick();
    await env.repo.complete('o-pm');
    env.tick();
    await env.repo.reopen('o-done');
    final q = await drain(env.db);
    expect(q, hasLength(3));
    for (final e in q) {
      expect(e.opData!.keys.toSet().difference(env.columns), isEmpty, reason: 'only declared columns');
      expect(e.opData!.keys.toSet().intersection(kMissingColumns.toSet()), isEmpty,
          reason: '${e.id}: a column that was NULL and was not changed is not sent (stage ${env.stage.name})');
    }
    expect(q.first.opData!.keys.toSet(), {'title', 'updated_at'});
  });

  forEachStage('a blank id in a patch means NULL: client, case and assignee', (env) async {
    env.tick();
    await env.repo.update('o-timed', const TaskPatch(assignedUserId: Present(''), extras: {'case_ref': ''}));
    final a = await env.row('o-timed');
    expect((a['assigned_user_id'], a['case_ref'], a['case_file_no']), (null, null, null));
    env.tick();
    await env.repo.update('o-none', const TaskPatch(extras: {'client_ref': ''})); // no case: the client may go
    expect((await env.row('o-none'))['client_ref'], isNull);
  });

  forEachStage("'' for the client of a task that has a case is refused: nothing written, nothing queued", (env) async {
    env.tick();
    await expectLater(
        env.repo.update('o-timed', const TaskPatch(title: 'changed', extras: {'client_ref': ''})), throwsA(isA<StateError>()));
    final row = await env.row('o-timed');
    expect((row['title'], row['client_ref'], row['case_ref']), ('Old timed', 'cl-1', 'ca-1'));
    expect(await drain(env.db), isEmpty);
    // clearing both in one write is fine
    await env.repo.update('o-timed', const TaskPatch(extras: {'client_ref': '', 'case_ref': ''}));
    final r = await env.row('o-timed');
    expect((r['client_ref'], r['case_ref']), (null, null));
  });

  forEachStage('a cancelled row shows cancelled; when sync removes it every watch re-emits without it', (env) async {
    final open = Watch(env.repo.watchOpen());
    final one = Watch(env.repo.watchTask('o-later'));
    final linked = Watch(env.repo.watchWhere({'client_ref': 'cl-1'}));
    try {
      expect(ids(await open.first()), contains('o-timed'));
      expect((await one.first())!.status, TaskStatus.open);
      await linked.first();
      await env.db.execute("UPDATE tasks SET client_ref = 'cl-1' WHERE id = 'o-later'");
      await linked.next((p) => p.items.any((t) => t.id == 'o-later'));
      env.tick();
      final cancelled = await env.repo.cancel('o-later');
      expect(cancelled.status, TaskStatus.cancelled);
      expect((await one.next((t) => t?.status == TaskStatus.cancelled))!.status, TaskStatus.cancelled);
      expect(ids(await open.next((l) => !l.any((t) => t.id == 'o-later'))), isNot(contains('o-later')));
      expect(ids((await linked.next((p) => p.items.any((t) => t.id == 'o-later' && t.status == TaskStatus.cancelled))).items),
          contains('o-later'));
      await env.db.execute("DELETE FROM tasks WHERE id = 'o-later'"); // the stream no longer holds it
      expect(await one.next((t) => t == null), isNull);
      expect(ids((await linked.next((p) => !p.items.any((t) => t.id == 'o-later'))).items), isNot(contains('o-later')));
    } finally {
      await Future.wait([open.cancel(), one.cancel(), linked.cancel()]);
    }
  });

  forEachStage('a cancelled row is listed by client only when the status is null or all, never under open', (env) async {
    env.tick();
    await env.repo.cancel('o-none'); // cl-1
    final every = await env.repo.listWhere({'client_ref': 'cl-1'});
    expect(ids(every.items), contains('o-none'));
    expect(ids((await env.repo.listWhere({'client_ref': 'cl-1'}, status: 'all')).items), contains('o-none'));
    expect(ids((await env.repo.listWhere({'client_ref': 'cl-1'}, status: 'open')).items), isNot(contains('o-none')));
    expect(ids((await env.repo.listWhere({'client_ref': 'cl-1'}, status: 'cancelled')).items), ['o-none']);
  });
}
