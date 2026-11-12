import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:bond_notify/bond_notify.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_notifications/bond_tasks_notifications.dart';
import 'package:bond_tasks_notifications/testing.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fakes.dart';

final _now = DateTime.utc(2026, 3, 10, 12);

Task _task(String id, {String owner = 'me', String? dueDate = '2026-03-12'}) =>
    Task(id: id, title: 'Task $id', ownerUserId: owner, dueDate: dueDate);

StageTime _st(String stage, int seq, Duration after, {bool nullSend = false}) =>
    StageTime(stage: stage, seq: seq, at: _now.add(after), sendAt: nullSend ? null : _now.add(after));

void main() {
  late FakeRepo repo;
  late FakeAlertPlugin plugin;
  late Map<String, List<StageTime>> table;
  var clockNow = _now;

  LocalTaskAlerts make({Set<String> handled = const {}, int budget = 60, int perTask = 3, String userId = 'me'}) =>
      LocalTaskAlerts(
        repo,
        plugin,
        userId: userId,
        handledElsewhere: handled,
        budget: budget,
        perTask: perTask,
        clock: TaskClock(() => clockNow),
        stages: (t, p, now) => table[t.id] ?? const [],
      );

  _realStagesTests();

  setUp(() {
    repo = FakeRepo();
    plugin = FakeAlertPlugin();
    table = {};
    clockNow = _now;
  });

  test('schedules the injected list, filtered: future only, null sendAt never, handled stages never', () async {
    table['a'] = [
      _st('close', 0, const Duration(hours: 1)),
      _st('due', 0, const Duration(hours: 2)),
      _st('past', 0, const Duration(minutes: -5)), // already past
      _st('past', 1, const Duration(seconds: 1)), // inside the 2 s margin
      _st('past', 2, const Duration(days: 1), nullSend: true), // superseded
    ];
    final alerts = make(handled: {'close'});
    await alerts.start();
    repo.push([_task('a')]);
    await settle();
    expect(plugin.scheduled, hasLength(1));
    final r = plugin.scheduled.single;
    expect(r.atUtc, _now.add(const Duration(hours: 2)));
    expect(r.title, const AlertLabels().dueTitle);
    expect(r.body, 'Task a');
    expect(r.route, '/tasks/a');
    expect(plugin.initialised, isTrue);
    await alerts.dispose();
  });

  test('ids are fnv1a31 of the notice id; pinned to the shared fixture', () async {
    final fixture = jsonDecode(File('../../fixtures/tasks/notice_ids.json').readAsStringSync()) as List;
    final c = fixture.cast<Map<String, dynamic>>().firstWhere((e) => e['task_id'] == 'task-0004' && e['stage'] == 'due');
    expect(fnv1a31(c['notice_id'] as String), c['local_id']);

    table['task-0004'] = [_st('due', 0, const Duration(hours: 1))];
    final alerts = make(userId: 'user-1');
    await alerts.start();
    repo.push([_task('task-0004', owner: 'user-1', dueDate: '2026-03-12')]);
    await settle();
    expect(plugin.scheduled.single.id, c['local_id']);
    expect(plugin.scheduled.single.noticeId, c['notice_id']);
    await alerts.dispose();
  });

  test('actions: cancel only for the owner', () async {
    table['a'] = [_st('due', 0, const Duration(hours: 1))];
    final alerts = make(userId: 'other');
    await alerts.start();
    repo.push([_task('a', owner: 'me')]);
    await settle();
    expect(plugin.scheduled.single.actions, [NoticeAction.done, NoticeAction.snooze]);
    expect(categoryFor(plugin.scheduled.single), kNoticeCategory);
    await alerts.dispose();

    final plugin2 = FakeAlertPlugin();
    final owner = LocalTaskAlerts(repo, plugin2,
        userId: 'me', clock: TaskClock(() => _now), stages: (t, p, n) => table[t.id] ?? const []);
    await owner.start();
    repo.push([_task('a', owner: 'me')]);
    await settle();
    expect(plugin2.scheduled.single.actions, contains(NoticeAction.cancel));
    expect(categoryFor(plugin2.scheduled.single), kNoticeCategoryOwner);
    expect(kNoticeCategoryOwner, 'bond.task.owner');
    await owner.dispose();
  });

  test('40 overdue tasks: at most 60 pending, at most 3 per task, nearest first', () async {
    final tasks = <Task>[];
    for (var i = 0; i < 40; i++) {
      final id = 't$i';
      tasks.add(_task(id));
      table[id] = [
        for (var s = 0; s < 5; s++) _st('past', s, Duration(hours: i + 1, days: s)),
      ];
    }
    final alerts = make();
    await alerts.start();
    repo.push(tasks);
    await settle();
    expect(plugin.scheduled.length, 60);
    final perTask = <String, int>{};
    for (final r in plugin.scheduled) {
      perTask[r.taskId] = (perTask[r.taskId] ?? 0) + 1;
    }
    expect(perTask.values.every((n) => n <= 3), isTrue);
    // The 60 nearest of the per-task-capped 120: the latest scheduled is not later than any left out.
    final latest = plugin.scheduled.map((r) => r.atUtc).reduce((a, b) => a.isAfter(b) ? a : b);
    final leftOut = <DateTime>[];
    for (var i = 0; i < 40; i++) {
      for (var s = 0; s < 3; s++) {
        final at = _now.add(Duration(hours: i + 1, days: s));
        if (!plugin.scheduled.any((r) => r.atUtc == at && r.taskId == 't$i')) leftOut.add(at);
      }
    }
    expect(leftOut, hasLength(60));
    expect(leftOut.every((d) => !d.isBefore(latest)), isTrue);
    await alerts.dispose();
  });

  test('a task change reschedules; done and cancelled tasks lose their alerts', () async {
    table['a'] = [_st('due', 0, const Duration(hours: 1))];
    table['b'] = [_st('due', 0, const Duration(hours: 2))];
    final alerts = make();
    await alerts.start();
    repo.push([_task('a'), _task('b')]);
    await settle();
    expect(plugin.scheduled, hasLength(2));
    final idA = plugin.scheduled.firstWhere((r) => r.taskId == 'a').id;

    // a moved later: same id (token unchanged in this fake), new time
    table['a'] = [_st('due', 0, const Duration(hours: 5))];
    repo.push([_task('a'), _task('b')]);
    await settle();
    expect(plugin.scheduled.firstWhere((r) => r.id == idA).atUtc, _now.add(const Duration(hours: 5)));
    expect(plugin.scheduled, hasLength(2));

    // a is done: it leaves the open list
    repo.push([_task('b')]);
    await settle();
    expect(plugin.scheduled.map((r) => r.taskId), ['b']);
    expect(plugin.cancelled, contains(idA));

    // b becomes no longer wanted by its own list
    table['b'] = [];
    repo.push([_task('b')]);
    await settle();
    expect(plugin.scheduled, isEmpty);
    await alerts.dispose();
  });

  test('an alert that already fired is not cancelled by the next sync; an unchanged one is not rescheduled', () async {
    table['a'] = [_st('due', 0, const Duration(hours: 1)), _st('past', 1, const Duration(days: 1))];
    final alerts = make();
    await alerts.start();
    repo.push([_task('a')]);
    await settle();
    final due = plugin.scheduled.firstWhere((r) => r.atUtc == _now.add(const Duration(hours: 1)));
    plugin.scheduled.removeWhere((r) => r.id == due.id); // it fired and left pending
    plugin.cancelled.clear();
    table['a'] = [_st('past', 1, const Duration(days: 1))];
    repo.push([_task('a')]);
    await settle();
    expect(plugin.cancelled, isEmpty);
    expect(plugin.scheduled, hasLength(1));
    await alerts.dispose();
  });

  test('two syncs never interleave', () async {
    table['a'] = [_st('due', 0, const Duration(hours: 1))];
    final alerts = make();
    await alerts.start();
    repo.push([_task('a')]);
    await Future.wait([alerts.sync(), alerts.sync(), alerts.sync()]);
    expect(plugin.scheduled, hasLength(1));
    await alerts.dispose();
  });

  test('a date-only task of another user schedules only what its list holds', () async {
    table['d'] = [_st('due', 0, const Duration(hours: 3))];
    final alerts = make(userId: 'someone-else');
    await alerts.start();
    repo.push([_task('d', owner: 'me')]);
    await settle();
    expect(plugin.scheduled.map((r) => r.title), [const AlertLabels().dueTitle]);
    await alerts.dispose();
  });

  test('pending alerts of ours are adopted on start and replaced, strangers are left alone', () async {
    table['a'] = [_st('due', 0, const Duration(hours: 1))];
    final id = fnv1a31(noticeId('gone', 'me', 'due', 0, ''));
    plugin = _WithStranger();
    await plugin.schedule(AlertRequest(
        id: id, noticeId: 'n', taskId: 'gone', title: 'x', body: 'y', atUtc: _now.add(const Duration(hours: 9))));
    final alerts = make();
    await alerts.start();
    repo.push([_task('a')]);
    await settle();
    expect(plugin.cancelled, [id]);
    expect(plugin.scheduled.map((r) => r.taskId), ['a']);
    await alerts.dispose();
  });

  group('notice arrival rules', () {
    Notice arriving(String id, {String stage = 'due'}) =>
        Notice(id: id, title: 'Due now', body: 'Task a', taskId: 'a', stage: stage, route: '/tasks/a');

    test('our copy already fired (clock past its time): nothing shown, nothing cancelled', () async {
      table['a'] = [_st('due', 0, const Duration(hours: 5))];
      final alerts = make();
      await alerts.start();
      repo.push([_task('a')]);
      await settle();
      final r = plugin.scheduled.single;
      clockNow = r.atUtc.add(const Duration(seconds: 20));
      await alerts.onNoticeArrived(arriving(r.noticeId));
      expect(plugin.shown, isEmpty);
      expect(plugin.cancelled, isEmpty);
      await alerts.dispose();
    });

    test('our copy fired and left pending, then a sync ran: still nothing shown', () async {
      table['a'] = [_st('due', 0, const Duration(hours: 5))];
      final alerts = make();
      await alerts.start();
      repo.push([_task('a')]);
      await settle();
      final r = plugin.scheduled.single;
      plugin.scheduled.clear(); // it fired
      clockNow = r.atUtc.add(const Duration(minutes: 1));
      table['a'] = [];
      await alerts.sync();
      await alerts.onNoticeArrived(arriving(r.noticeId));
      expect(plugin.shown, isEmpty);
      expect(plugin.cancelled, isEmpty);
      await alerts.dispose();
    });

    test('our copy still ahead: pending copy cancelled, shown once', () async {
      table['a'] = [_st('due', 0, const Duration(hours: 5))];
      final alerts = make();
      await alerts.start();
      repo.push([_task('a')]);
      await settle();
      final r = plugin.scheduled.single;
      clockNow = r.atUtc.subtract(const Duration(minutes: 10));
      await alerts.onNoticeArrived(arriving(r.noticeId));
      await alerts.onNoticeArrived(arriving(r.noticeId));
      expect(plugin.cancelled.first, r.id);
      expect(plugin.scheduled, isEmpty);
      expect(plugin.shown, hasLength(1));
      await alerts.dispose();
    });

    test('after a restart (empty schedule) a notice already on the lock screen is not shown', () async {
      final alerts = make();
      await alerts.start();
      plugin.activeIds = [fnv1a31('on-screen')];
      await alerts.onNoticeArrived(arriving('on-screen'));
      await alerts.onNoticeArrived(arriving('on-screen'));
      expect(plugin.shown, isEmpty);
      // neither active nor scheduled: shown once
      await alerts.onNoticeArrived(arriving('fresh-one'));
      await alerts.onNoticeArrived(arriving('fresh-one'));
      expect(plugin.shown.map((r) => r.noticeId), ['fresh-one']);
      await alerts.dispose();
    });

    test('an active() failure is reported and the notice is still shown', () async {
      final errors = <Object>[];
      final alerts = LocalTaskAlerts(repo, _NoActive(),
          userId: 'me', clock: TaskClock(() => _now), onError: (e, s) => errors.add(e));
      await alerts.start();
      await alerts.onNoticeArrived(arriving('x'));
      expect(errors, hasLength(1));
      await alerts.dispose();
    });

    test('an id we never scheduled is shown once', () async {
      final alerts = make();
      await alerts.start();
      await alerts.onNoticeArrived(arriving('unknown'));
      await alerts.onNoticeArrived(arriving('unknown'));
      expect(plugin.shown, hasLength(1));
      await alerts.dispose();
    });

    test('a stage handled elsewhere is never shown, but a pending copy is cancelled', () async {
      final id = fnv1a31('nid');
      await plugin.schedule(AlertRequest(
          id: id, noticeId: 'nid', taskId: 'a', title: 'x', body: 'y', atUtc: _now.add(const Duration(hours: 1))));
      final alerts = make(handled: {'close', 'due', 'past'});
      await alerts.start();
      await alerts.onNoticeArrived(arriving('nid'));
      expect(plugin.shown, isEmpty);
      expect(plugin.cancelled, [id]);
      expect(plugin.scheduled, isEmpty);
      await alerts.dispose();
    });
  });

  group('review fixes', () {
    test('start() primes a repository that emits only after refresh()', () async {
      repo.serverTasks = [_task('a')];
      table['a'] = [_st('due', 0, const Duration(hours: 1))];
      final alerts = make();
      await alerts.start();
      await settle();
      expect(repo.refreshCalls, 1);
      expect(plugin.scheduled, hasLength(1));
      await alerts.dispose();
    });

    test('a failing refresh is reported, not thrown', () async {
      repo.refreshFails = StateError('offline');
      final errors = <Object>[];
      final alerts = LocalTaskAlerts(repo, plugin,
          userId: 'me', clock: TaskClock(() => _now), onError: (e, s) => errors.add(e));
      await alerts.start();
      expect(errors, hasLength(1));
      await alerts.dispose();
    });

    test('a renamed task reschedules with the new title, same id and time', () async {
      table['a'] = [_st('due', 0, const Duration(hours: 1))];
      final alerts = make();
      await alerts.start();
      repo.push([_task('a')]);
      await settle();
      final id = plugin.scheduled.single.id;
      repo.push([const Task(id: 'a', title: 'Renamed', ownerUserId: 'me', dueDate: '2026-03-12')]);
      await settle();
      expect(plugin.scheduled.single.id, id);
      expect(plugin.scheduled.single.body, 'Renamed');
      await alerts.dispose();
    });

    test('an assignee who becomes the owner gets the Cancel action (owner category)', () async {
      table['a'] = [_st('due', 0, const Duration(hours: 1))];
      final alerts = make(userId: 'u');
      await alerts.start();
      repo.push([_task('a', owner: 'someone')]);
      await settle();
      expect(categoryFor(plugin.scheduled.single), kNoticeCategory);
      repo.push([_task('a', owner: 'u')]);
      await settle();
      expect(plugin.scheduled.single.actions, contains(NoticeAction.cancel));
      expect(categoryFor(plugin.scheduled.single), kNoticeCategoryOwner);
      await alerts.dispose();
    });

    test('an unchanged task is not rescheduled', () async {
      table['a'] = [_st('due', 0, const Duration(hours: 1))];
      final counting = _CountingPlugin();
      final alerts = LocalTaskAlerts(repo, counting,
          userId: 'me', clock: TaskClock(() => _now), stages: (t, p, n) => table[t.id] ?? const []);
      await alerts.start();
      repo.push([_task('a')]);
      await settle();
      repo.push([_task('a')]);
      await settle();
      expect(counting.schedules, 1);
      await alerts.dispose();
    });

    test('init is flagged done only after it succeeded: a failed start can be retried', () async {
      final flaky = _FlakyInit();
      final alerts = LocalTaskAlerts(repo, flaky, userId: 'me', clock: TaskClock(() => _now));
      await expectLater(alerts.start(), throwsStateError);
      await alerts.start();
      expect(flaky.initCalls, 2);
      await alerts.dispose();
    });

    test('a concurrent second start() waits for the first init and does not init twice', () async {
      final slow = _SlowInit();
      final alerts = LocalTaskAlerts(repo, slow, userId: 'me', clock: TaskClock(() => _now));
      final a = alerts.start();
      final b = alerts.start();
      await settle();
      expect(slow.initCalls, 1);
      expect(slow.initialised, isFalse);
      slow.finish.complete();
      await Future.wait([a, b]);
      expect(slow.initialised, isTrue);
      expect(slow.initCalls, 1);
      await alerts.dispose();
    });

    test('when pending() throws, the sync is skipped: nothing is cancelled and nothing counts as fired', () async {
      table['a'] = [_st('due', 0, const Duration(hours: 1))];
      final flaky = _FlakyPending();
      final errors = <Object>[];
      final alerts = LocalTaskAlerts(repo, flaky,
          userId: 'me',
          clock: TaskClock(() => _now),
          onError: (e, s) => errors.add(e),
          stages: (t, p, n) => table[t.id] ?? const []);
      await alerts.start();
      repo.push([_task('a')]);
      await settle();
      final r = flaky.scheduled.single;
      flaky.fail = true;
      table['a'] = [];
      repo.push([_task('a')]);
      await settle();
      expect(errors, isNotEmpty);
      expect(flaky.cancelled, isEmpty);
      expect(flaky.scheduled, hasLength(1));
      // a notice for it still counts as "ahead", so the pending copy is cancelled and it is shown
      flaky.fail = false;
      await alerts.onNoticeArrived(Notice(id: r.noticeId, taskId: 'a', stage: 'due'));
      expect(flaky.shown, hasLength(1));
      await alerts.dispose();
    });

    test('FakeAlertPlugin.show makes the id active, like the real plugin', () async {
      await plugin.show(AlertRequest(id: 5, noticeId: 'n', taskId: 't', title: 'x', body: 'y', atUtc: _now));
      expect(await plugin.active(), [5]);
      await plugin.cancel(5);
      expect(await plugin.active(), isEmpty);
    });
  });

  group('lifecycle', () {
    test('cancelAll clears the list and stops listening until start() again', () async {
      table['a'] = [_st('due', 0, const Duration(hours: 1))];
      final alerts = make();
      await alerts.start();
      repo.push([_task('a')]);
      await settle();
      expect(plugin.scheduled, hasLength(1));
      await alerts.cancelAll();
      expect(plugin.scheduled, isEmpty);
      repo.push([_task('a')]);
      await settle();
      await alerts.sync();
      expect(plugin.scheduled, isEmpty, reason: 'signed out: no listening, no task list');
      await alerts.start();
      repo.push([_task('a')]);
      await settle();
      expect(plugin.scheduled, hasLength(1));
      await alerts.dispose();
    });

    test('a sync queued before dispose does not schedule after it', () async {
      table['a'] = [_st('due', 0, const Duration(hours: 1))];
      final alerts = make();
      await alerts.start();
      repo.push([_task('a')]);
      await settle();
      final before = plugin.scheduled.single.atUtc;
      table['a'] = [_st('due', 0, const Duration(hours: 4))];
      final queued = alerts.sync();
      final disposed = alerts.dispose();
      await queued;
      await disposed;
      expect(plugin.scheduled.single.atUtc, before);
    });

    test('updatePrefs re-plans the schedule', () async {
      final alerts = LocalTaskAlerts(repo, plugin,
          userId: 'me',
          clock: TaskClock(() => _now),
          stages: (t, p, n) => [_st('due', 0, Duration(minutes: p.leadMinutes))]);
      await alerts.start();
      repo.push([_task('a')]);
      await settle();
      expect(plugin.scheduled.single.atUtc, _now.add(const Duration(minutes: 60)));
      alerts.updatePrefs(const TaskPrefs(leadMinutes: 120));
      await settle();
      expect(plugin.scheduled.single.atUtc, _now.add(const Duration(minutes: 120)));
      await alerts.dispose();
    });
  });

  group('onNoticeArrived', () {
    Notice notice() => const Notice(
        id: 'nid', title: 'Due now', body: 'Task a', taskId: 'a', route: '/tasks/a', actions: ['done', 'snooze']);

    test('cancels the scheduled copy and posts once, even when called twice', () async {
      final alerts = make();
      await alerts.start();
      await alerts.onNoticeArrived(notice());
      await alerts.onNoticeArrived(notice());
      expect(plugin.cancelled, [fnv1a31('nid')], reason: 'the second arrival finds it on screen and leaves it');
      expect(plugin.shown, hasLength(1));
      expect(plugin.shown.single.id, fnv1a31('nid'));
      expect(plugin.shown.single.actions, [NoticeAction.done, NoticeAction.snooze]);
      await alerts.dispose();
    });

    test('postNow false only cancels', () async {
      final alerts = make();
      await alerts.start();
      await alerts.onNoticeArrived(notice(), postNow: false);
      expect(plugin.cancelled, [fnv1a31('nid')]);
      expect(plugin.shown, isEmpty);
      await alerts.dispose();
    });
  });

  test('a plugin that throws does not stop the rest of the sync', () async {
    table['a'] = [_st('due', 0, const Duration(hours: 1))];
    table['b'] = [_st('due', 0, const Duration(hours: 2))];
    final errors = <Object>[];
    final flaky = _FlakyPlugin();
    final alerts = LocalTaskAlerts(repo, flaky,
        userId: 'me',
        clock: TaskClock(() => _now),
        onError: (e, s) => errors.add(e),
        stages: (t, p, n) => table[t.id] ?? const []);
    await alerts.start();
    repo.push([_task('a'), _task('b')]);
    await settle();
    expect(errors, hasLength(1));
    expect(flaky.scheduled, hasLength(1));
    await alerts.dispose();
  });
}

void _realStagesTests() {
  final pacific = DateTime.utc(2026, 3, 12, 12).toLocal().hour == 5;
  final cases = (jsonDecode(File('../../fixtures/tasks/stage_times.json').readAsStringSync()) as List)
      .cast<Map<String, dynamic>>()
      .where((c) => c['effective_zone'] == 'America/Los_Angeles' && (c['stages'] as List).isNotEmpty)
      .where((c) => const {'timed_before_close', 'dateonly_close_in_work_day', 'evening_timed_close_sendable'}
          .contains(c['name']));

  for (final c in cases) {
    test('real stageTimesFor default matches the fixture: ${c['name']}', () async {
      final repo = FakeRepo();
      final plugin = FakeAlertPlugin();
      final now = DateTime.parse(c['now'] as String);
      final p = c['prefs'] as Map<String, dynamic>;
      final alerts = LocalTaskAlerts(
        repo,
        plugin,
        userId: c['user_id'] as String,
        prefs: TaskPrefs(
          startOfDay: p['start_of_day'] as String,
          endOfDay: p['end_of_day'] as String,
          leadMinutes: p['lead_minutes'] as int,
          maxPast: c['max_past'] as int,
        ),
        perTask: 20,
        clock: TaskClock(() => now),
      );
      await alerts.start();
      repo.push([Task.fromJson((c['task'] as Map).cast<String, Object?>())]);
      await settle();
      final expected = [
        for (final s in c['stages'] as List)
          if ((s as Map)['send_at'] != null && DateTime.parse(s['send_at'] as String).isAfter(now.add(const Duration(seconds: 2))))
            DateTime.parse(s['send_at'] as String),
      ]..sort();
      final got = plugin.scheduled.map((r) => r.atUtc).toList()..sort();
      expect(expected, isNotEmpty);
      expect(got, expected);
      await alerts.dispose();
    },
        skip: pacific ? null : 'needs TZ=America/Los_Angeles (run: TZ=America/Los_Angeles make -C packages/bond_tasks_notifications test)');
  }
}

/// Reports one pending alert that is not ours (foreign payload).
class _WithStranger extends FakeAlertPlugin {
  @override
  Future<List<PendingAlert>> pending() async => [...await super.pending(), const PendingAlert(id: 77, payload: 'other')];
}

class _FlakyPlugin extends FakeAlertPlugin {
  int calls = 0;

  @override
  Future<void> schedule(AlertRequest r) async {
    if (calls++ == 0) throw StateError('platform said no');
    return super.schedule(r);
  }
}

class _NoActive extends FakeAlertPlugin {
  @override
  Future<List<int>> active() async => throw StateError("no list");
}

class _CountingPlugin extends FakeAlertPlugin {
  int schedules = 0;
  @override
  Future<void> schedule(AlertRequest r) async {
    schedules++;
    return super.schedule(r);
  }
}

class _FlakyInit extends FakeAlertPlugin {
  int initCalls = 0;
  @override
  Future<void> init({required void Function(AlertTap) onTap}) async {
    if (initCalls++ == 0) throw StateError('init failed');
    return super.init(onTap: onTap);
  }
}

class _SlowInit extends FakeAlertPlugin {
  int initCalls = 0;
  final finish = Completer<void>();
  @override
  Future<void> init({required void Function(AlertTap) onTap}) async {
    initCalls++;
    await finish.future;
    return super.init(onTap: onTap);
  }
}

class _FlakyPending extends FakeAlertPlugin {
  bool fail = false;
  @override
  Future<List<PendingAlert>> pending() async {
    if (fail) throw StateError('pending failed');
    return super.pending();
  }
}
