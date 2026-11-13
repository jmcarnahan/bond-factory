@Tags(['real_db'])
@TestOn('vm')
library;

/// Ticking and unticking a checklist item over the legacy store, offline and then synced. Stage one has no checklist
/// column: the value is dropped silently. The recorded queue (`fixtures/legacy_host/upload_phone_checklist.json`) is
/// asserted here and replayed by services/legacy_host/tests/test_phone_checklist_upload.py.
import 'dart:convert';
import 'dart:io';

import 'package:bond_tasks/bond_tasks.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:legacy_phone/legacy_phone.dart';

import 'support.dart';

const _path = '../../fixtures/legacy_host/upload_phone_checklist.json';
const _items = [
  ChecklistItem(id: 'a', text: 'Bring ID'),
  ChecklistItem(id: 'b', text: 'Sign form'),
];

List<Object?> _stored(Object? cell) =>
    jsonDecode(cell! as String) as List<Object?>;

void main() {
  test(
    'stage one: a checklist has no column, so a draft or tick is dropped and nothing is queued for it',
    () async {
      final env = await openEnv(LegacyStage.asShipped);
      try {
        final t = await env.repo.create(
          const TaskDraft(title: 'Has items', id: 'ck-0', checklist: _items),
        );
        expect(t.checklist, isEmpty);
        await drain(env.db);
        env.tick();
        await env.repo.update(
          'ck-0',
          TaskPatch(
            checklist: [
              _items[0].copyWith(doneAt: env.now),
              _items[1],
            ],
          ),
        );
        expect(
          await drain(env.db),
          isEmpty,
          reason: 'the only column the patch names is not in the table',
        );
      } finally {
        await env.close();
      }
    },
  );

  test(
    'stage two: a tick stamps the item, an untick clears it; offline, then drained',
    () async {
      final env = await openEnv(LegacyStage.widened);
      try {
        await env.repo.create(
          const TaskDraft(title: 'Has items', id: 'ck-1', checklist: _items),
        );
        await drain(env.db);
        env.tick();
        final ticked = await env.repo.update(
          'ck-1',
          TaskPatch(
            checklist: [
              _items[0].copyWith(doneAt: env.now),
              _items[1],
            ],
          ),
        );
        expect([for (final c in ticked.checklist) c.done], [true, false]);
        var row = _stored((await env.row('ck-1'))['checklist']).cast<Map>();
        expect(
          row[0]['done_at'],
          isNotNull,
          reason:
              'a ticked item sends its stamp; `done: true` would make the server stamp its own clock',
        );
        expect(row[0].containsKey('done'), isFalse);
        expect((row[1].containsKey('done'), row[1]['done_at']), (false, null), reason: 'never ticked: no done key');
        env.tick();
        final unticked = await env.repo.update(
          'ck-1',
          TaskPatch(
            checklist: [
              ticked.checklist[0].copyWith(clearDone: true),
              ticked.checklist[1],
            ],
          ),
        );
        expect([for (final c in unticked.checklist) c.done], [false, false]);
        row = _stored((await env.row('ck-1'))['checklist']).cast<Map>();
        expect(
          (row[0]['done'], row[0]['done_at']),
          (false, null),
          reason: 'the untick says done: false, not only a missing stamp',
        );
        final q = await drain(env.db);
        expect(q.map((e) => e.op), ['patch', 'patch']);
        for (final e in q) {
          expect(e.opData!.keys.toSet(), {'checklist', 'updated_at'});
          expect(
            _stored(e.opData!['checklist']).cast<Map>().map((m) => m['id']),
            ['a', 'b'],
          );
        }
        expect(
          _stored(q[1].opData!['checklist']).cast<Map>()[0]['done'],
          false,
        );
      } finally {
        await env.close();
      }
    },
  );

  test(
    'the queue of a create, a tick, an untick and an added item is the recorded upload',
    () async {
      final env = await openEnv(LegacyStage.widened);
      try {
        await env.repo.create(
          const TaskDraft(
            title: 'Bring the papers',
            id: 'ck-1',
            checklist: _items,
          ),
        );
        env.tick();
        await env.repo.update(
          'ck-1',
          TaskPatch(
            checklist: [
              _items[0].copyWith(doneAt: env.now),
              _items[1],
            ],
          ),
        ); // offline
        final ticked = (await env.repo.getTask('ck-1'))!;
        env.tick();
        await env.repo.update(
          'ck-1',
          TaskPatch(
            checklist: [
              ticked.checklist[0].copyWith(clearDone: true),
              ticked.checklist[1],
            ],
          ),
        ); // and back
        final after = (await env.repo.getTask('ck-1'))!;
        env.tick();
        await env.repo.update(
          'ck-1',
          TaskPatch(
            checklist: [
              ...after.checklist,
              const ChecklistItem(id: 'c', text: 'Pay fee'),
            ],
          ),
        ); // add one
        final recorded = {
          'note':
              'What the legacy phone store queues at stage widened for a create with a two-item checklist, a tick of item a, '
              'an untick through copyWith(clearDone: true) and an added item (no `done` key anywhere) (demos/legacy_phone, test/checklist_test.dart). Regenerate with BOND_REGEN_FIXTURES=1.',
          'requests': await queuedRequests(env),
        };
        if (Platform.environment['BOND_REGEN_FIXTURES'] == '1') {
          File(_path).writeAsStringSync(
            '${const JsonEncoder.withIndent('  ').convert(recorded)}\n',
          );
        }
        final file = jsonDecode(File(_path).readAsStringSync()) as Map;
        expect(jsonDecode(jsonEncode(recorded['requests'])), file['requests']);
        expect((file['requests'] as List), hasLength(4));
      } finally {
        await env.close();
      }
    },
  );
}
