@Tags(['real_db'])
@TestOn('vm')
library;

/// The shared UI contract: the legacy store is a `TaskRepository`, so the SDK's widgets and the alerts coordinator run
/// over it unchanged. A real database inside `testWidgets` runs under `tester.runAsync` (FakeAsync would never see it).
import 'package:bond_notify/bond_notify.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_notifications/bond_tasks_notifications.dart';
import 'package:bond_tasks_notifications/testing.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:legacy_phone/legacy_phone.dart';

import 'support.dart';

class _NoFeed implements NoticeFeed {
  @override
  Stream<List<Notice>> watch() => const Stream.empty();
  @override
  Future<void> refresh() async {}
  @override
  Future<void> markRead(String id) async {}
  @override
  Future<void> dismiss(String id) async {}
  @override
  Future<void> markAllRead() async {}
  @override
  int? get serverUnreadCount => null;
  @override
  void dispose() {}
}

void main() {
  forEachStage('the store is a TaskRepository', (env) async {
    expect(env.repo, isA<TaskRepository>());
    final TaskRepository asContract = env.repo;
    expect((await asContract.summary()).open, 6);
  });

  for (final stage in LegacyStage.values) {
    testWidgets(
      'the today list over the legacy store shows a seeded task and completes it [${stage.name}]',
      (t) async {
        final sem = t.ensureSemantics();
        late LegacyEnv env;
        late TaskController controller;
        await t.runAsync(() async {
          env = await openEnv(stage);
          controller = TaskController(env.repo, clock: env.clock);
        });
        try {
          await t.runAsync(() => controller.load());
          setPhone(t);
          await pumpApp(
            t,
            StreamBuilder<TaskControllerState>(
              stream: controller.states,
              initialData: controller.state,
              builder: (context, s) => SingleChildScrollView(
                child: BondTodayList(
                  today: s.data!.today ?? const TaskToday(),
                  now: env.clock.nowLocal(),
                  onComplete: (task) => controller.complete(task.id),
                  semanticsPrefix: 'p',
                ),
              ),
            ),
            theme: BondTheme.build(BondTokens.fallback),
          );
          await t.pump();
          expect(
            find.text('Old timed'),
            findsOneWidget,
            reason:
                'overdue by its date and time, though the row has no due_at',
          );
          expect(find.text('Old afternoon'), findsOneWidget);
          expect(find.text('Old undated'), findsOneWidget);
          expect(find.text('Overdue (1)'), findsOneWidget);

          await t.tap(find.bySemanticsIdentifier('p.complete-o-timed'));
          // The tap's chain of database calls resumes in the fake zone: alternate real time and a pump until it is done.
          var status = 'open';
          for (var i = 0; i < 50 && status != 'done'; i++) {
            await t.runAsync(() async {
              await Future<void>.delayed(const Duration(milliseconds: 100));
              status = (await env.row('o-timed'))['status'] as String;
            });
            await t.pump();
          }
          expect(
            status,
            'done',
            reason:
                'the widget completed it through the repository, in the database',
          );
          expect(find.text('Overdue (1)'), findsNothing);
        } finally {
          sem.dispose();
          await t.runAsync(() async {
            controller.dispose();
            await env.close();
          });
        }
      },
    );
  }

  for (final stage in LegacyStage.values) {
    test(
      'the alerts coordinator plans an alert for a seeded timed task [${stage.name}]',
      () async {
        final env = await openEnv(stage);
        final plugin = FakeAlertPlugin();
        final errors = <Object>[];
        final coordinator = TaskAlertsCoordinator(
          repository: env.repo,
          feed: _NoFeed(),
          plugin: plugin,
          prefs: const TaskPrefs(),
          userId: 'u-owner',
          clock: env.clock,
          onError: (e, s) => errors.add(e),
        );
        try {
          await coordinator.start();
          await nextWhere(
            Stream<void>.periodic(const Duration(milliseconds: 50)),
            (_) => plugin.scheduled.any((r) => r.taskId == 'o-pm'),
          );
          expect(
            plugin.scheduled.map((r) => r.taskId),
            isNot(contains('o-theirs')),
            reason: 'only this user\'s tasks',
          );
          final r = plugin.scheduled.firstWhere((r) => r.taskId == 'o-pm');
          expect(r.atUtc.isAfter(env.now), isTrue);
          expect(errors, isEmpty);
        } finally {
          coordinator.dispose();
          await env.close();
        }
      },
    );
  }
}
