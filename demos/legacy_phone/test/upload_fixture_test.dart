@Tags(['real_db'])
@TestOn('vm')
library;

/// What the legacy store queues, as the upload connector would send it, against `fixtures/legacy_host/upload_phone_store.json`.
/// `BOND_REGEN_FIXTURES=1 make test T=test/upload_fixture_test.dart` rewrites the file; otherwise the queue must equal it.
/// `services/legacy_host/tests/test_phone_store_upload.py` replays the same file against the legacy server, which has
/// not changed: an app can adopt the store before its server changes.
import 'dart:convert';
import 'dart:io';

import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:legacy_phone/legacy_phone.dart';

import 'support.dart';

const _paths = {
  LegacyStage.asShipped: '../../fixtures/legacy_host/upload_phone_store.json',
  LegacyStage.widened:
      '../../fixtures/legacy_host/upload_phone_store_widened.json',
};

Future<List<Object?>> _requests(LegacyEnv env) async {
  final store = PowerSyncSyncStore.withDb(
    env.db,
    policy: SyncPolicy(schema: legacySchema(env.stage)),
  );
  final out = <Object?>[];
  while (true) {
    final batch = await store.nextBatch();
    if (batch == null) return out;
    out.add({
      'user': 'u-owner',
      'body': {
        'ops': [for (final o in batch.ops) o.toJson()],
      },
    });
    await batch.complete();
  }
}

void main() {
  for (final stage in LegacyStage.values) {
    test(
      'the queue of a create, an edit, a complete, a reopen and a delete is the recorded upload [${stage.name}]',
      () async {
        final env = await openEnv(stage);
        final path = _paths[stage]!;
        try {
          final repo = env.repo;
          await repo.create(
            const TaskDraft(
              title: 'Call the client',
              id: 'ph-1',
              notes: 'bring docs',
              dueDate: '2026-11-20',
              dueTime: '09:30',
              extras: {'client_ref': 'cl-1', 'case_ref': 'ca-1'},
            ),
          );
          env.tick();
          await repo.update(
            'ph-1',
            const TaskPatch(
              title: 'Call the client back',
              extras: {'case_ref': null},
            ),
          );
          env.tick();
          await repo.complete('ph-1');
          env.tick();
          await repo.reopen('ph-1');
          env.tick();
          await repo.create(
            const TaskDraft(
              title: 'Water the plants',
              id: 'ph-2',
              dueDate: '2026-11-21',
              mirrorEnabled: false,
            ),
          );
          env.tick();
          await repo.delete('ph-2');

          final recorded = {
            'note':
                'What the legacy phone store queues at stage ${stage.name} (demos/legacy_phone, test/upload_fixture_test.dart): '
                'the app\'s own column names only. Regenerate with BOND_REGEN_FIXTURES=1. `user` is the session user of each request; '
                'requests are replayed in order.',
            'requests': await _requests(env),
          };
          if (Platform.environment['BOND_REGEN_FIXTURES'] == '1') {
            File(path).writeAsStringSync(
              '${const JsonEncoder.withIndent('  ').convert(recorded)}\n',
            );
          }
          final file = jsonDecode(File(path).readAsStringSync()) as Map;
          expect(
            jsonDecode(jsonEncode(recorded['requests'])),
            file['requests'],
          );
          expect((file['requests'] as List), hasLength(6));
        } finally {
          await env.close();
        }
      },
    );
  }
}
