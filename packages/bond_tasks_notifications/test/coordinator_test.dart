import 'dart:async';

import 'package:bond_notify/bond_notify.dart';
import 'package:bond_push/bond_push.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_notifications/bond_tasks_notifications.dart';
import 'package:bond_tasks_notifications/testing.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fakes.dart';

final _now = DateTime.utc(2026, 3, 10, 12);

class _FakeTaps implements PushTaps {
  final ctl = StreamController<PushTap>.broadcast();
  PushTap? initial;
  @override
  Stream<PushTap> get taps => ctl.stream;
  @override
  Future<PushTap?> initialTap() async => initial;
}

class _NoDevices implements PushDevices {
  @override
  Future<void> register(PushToken t, {required String deviceId, String? topic}) async {}
  @override
  Future<void> unregister(String deviceId) async {}
}

class _FakeRegistrar extends PushRegistrar {
  _FakeRegistrar() : super(const NoPushTokenSource(), _NoDevices(), deviceId: 'd1');
  int starts = 0;
  int unregisters = 0;
  int disposes = 0;
  Object? unregisterFails;

  @override
  Future<void> start() async => starts++;

  @override
  Future<void> unregister() async {
    unregisters++;
    if (unregisterFails != null) throw unregisterFails!;
  }

  @override
  void dispose() => disposes++;
}

void main() {
  late FakeRepo repo;
  late FakeFeed feed;
  late FakeAlertPlugin plugin;
  late List<String> opened;
  late List<Object> errors;
  late TaskAlertsCoordinator coordinator;
  late _FakeTaps pushTaps;

  const task = Task(id: 'a', title: 'Task a', ownerUserId: 'me', dueDate: '2026-03-12');
  final due = StageTime(
      stage: 'due', seq: 0, at: _now.add(const Duration(hours: 1)), sendAt: _now.add(const Duration(hours: 1)));
  final nid = noticeId('a', 'me', 'due', 0, deadlineToken(task));

  Notice notice({DateTime? created, bool read = false}) => Notice(
        id: nid,
        title: 'Due now',
        body: 'Task a',
        taskId: 'a',
        route: '/tasks/a',
        actions: const ['done', 'snooze'],
        createdAt: created ?? _now,
        readAt: read ? _now : null,
      );

  setUp(() {
    repo = FakeRepo();
    feed = FakeFeed();
    plugin = FakeAlertPlugin();
    opened = [];
    errors = [];
    pushTaps = _FakeTaps();
    coordinator = TaskAlertsCoordinator(
      repository: repo,
      feed: feed,
      plugin: plugin,
      prefs: const TaskPrefs(),
      userId: 'me',
      pushTaps: pushTaps,
      onOpen: opened.add,
      clock: TaskClock(() => _now),
      onError: (e, s) => errors.add(e),
      stages: (t, p, n) => [due],
    );
  });

  test('one start() wires everything: plugin, schedule, feed, taps', () async {
    await coordinator.start();
    expect(plugin.initialised, isTrue);
    repo.push([task]);
    await settle();
    expect(plugin.scheduled.single.id, fnv1a31(nid));
    // plain tap opens its route
    plugin.fireTap(AlertTap(noticeId: nid, taskId: 'a', route: '/tasks/a'));
    await settle();
    expect(opened, ['/tasks/a']);
    coordinator.dispose();
  });

  test('an action tap completes the task, marks the notice read and clears the notification', () async {
    await coordinator.start();
    plugin.fireTap(AlertTap(noticeId: nid, taskId: 'a', action: NoticeAction.done));
    await settle();
    expect(repo.completed, ['a']);
    expect(feed.read, [nid]);
    expect(plugin.cancelled, contains(fnv1a31(nid)));
    expect(opened, isEmpty);
    coordinator.dispose();
  });

  test('a push action tap finds its task through the feed', () async {
    await coordinator.start();
    feed.push([notice(read: true)]);
    await settle();
    pushTaps.ctl.add(PushTap(noticeId: nid, action: 'cancel'));
    await settle();
    expect(repo.cancelled, ['a']);
    coordinator.dispose();
  });

  test('a push plain tap opens the route; the launch tap is replayed', () async {
    plugin.launch = AlertTap(noticeId: nid, taskId: 'a', route: '/tasks/a');
    pushTaps.initial = const PushTap(route: '/tasks/zzz');
    await coordinator.start();
    expect(opened, ['/tasks/a', '/tasks/zzz']);
    coordinator.dispose();
  });

  test('a stage that is both scheduled and synced alerts once', () async {
    await coordinator.start();
    repo.push([task]);
    await settle();
    feed.push(const []); // baseline
    await settle();
    expect(plugin.scheduled, hasLength(1));
    feed.push([notice()]);
    await settle();
    feed.push([notice()]);
    await settle();
    expect(plugin.scheduled, isEmpty, reason: 'the scheduled copy was cancelled');
    expect(plugin.shown, hasLength(1));
    expect(plugin.shown.single.id, fnv1a31(nid));
    coordinator.dispose();
  });

  test('the first snapshot and stale notices are not posted, but their scheduled copies are cancelled', () async {
    await coordinator.start();
    feed.push([notice()]); // first snapshot: baseline only
    await settle();
    expect(plugin.shown, isEmpty);
    expect(plugin.cancelled, contains(fnv1a31(nid)));
    final old = Notice(id: 'old', taskId: 'a', createdAt: _now.subtract(const Duration(days: 1)));
    feed.push([notice(), old]);
    await settle();
    expect(plugin.shown, isEmpty);
    coordinator.dispose();
  });

  test('freshness is 10 minutes: 11 minutes old is not posted, 9 minutes old is', () async {
    await coordinator.start();
    feed.push(const []);
    await settle();
    final stale = Notice(id: 'stale', taskId: 'a', createdAt: _now.subtract(const Duration(minutes: 11)));
    final fresh = Notice(id: 'fresh', taskId: 'a', createdAt: _now.subtract(const Duration(minutes: 9)));
    feed.push([stale, fresh]);
    await settle();
    expect(plugin.shown.map((r) => r.noticeId), ['fresh']);
    coordinator.dispose();
  });

  test('the same tap from launchTap and the response callback is handled once', () async {
    final tap = AlertTap(noticeId: nid, taskId: 'a', action: NoticeAction.done);
    plugin.launch = tap;
    await coordinator.start();
    plugin.fireTap(tap);
    await settle();
    expect(repo.completed, ['a']);
    plugin.fireTap(AlertTap(noticeId: nid, taskId: 'a', route: '/tasks/a')); // another action: not a duplicate
    await settle();
    expect(opened, ['/tasks/a']);
    coordinator.dispose();
  });

  test('updatePrefs re-plans the local alerts', () async {
    final c = TaskAlertsCoordinator(
      repository: repo,
      feed: feed,
      plugin: plugin,
      prefs: const TaskPrefs(),
      userId: 'me',
      clock: TaskClock(() => _now),
      stages: (t, p, n) => [
        StageTime(stage: 'due', seq: 0, at: _now, sendAt: _now.add(Duration(minutes: p.leadMinutes))),
      ],
    );
    await c.start();
    repo.push([task]);
    await settle();
    expect(plugin.scheduled.single.atUtc, _now.add(const Duration(minutes: 60)));
    c.updatePrefs(const TaskPrefs(leadMinutes: 90));
    await settle();
    expect(plugin.scheduled.single.atUtc, _now.add(const Duration(minutes: 90)));
    c.dispose();
  });

  test('postNow false never posts', () async {
    final quiet = TaskAlertsCoordinator(
      repository: repo,
      feed: feed,
      plugin: plugin,
      prefs: const TaskPrefs(),
      userId: 'me',
      postNow: false,
      clock: TaskClock(() => _now),
      stages: (t, p, n) => const [],
    );
    await quiet.start();
    feed.push(const []);
    await settle();
    feed.push([notice()]);
    await settle();
    expect(plugin.shown, isEmpty);
    quiet.dispose();
  });

  test('handledElsewhere is passed on: nothing scheduled for a handled stage', () async {
    final pushOn = TaskAlertsCoordinator(
      repository: repo,
      feed: feed,
      plugin: plugin,
      prefs: const TaskPrefs(),
      userId: 'me',
      handledElsewhere: const {'close', 'due', 'past'},
      clock: TaskClock(() => _now),
      stages: (t, p, n) => [due],
    );
    await pushOn.start();
    repo.push([task]);
    await settle();
    expect(plugin.scheduled, isEmpty);
    pushOn.dispose();
  });

  test('a failing action reports the error and leaves the notice unread', () async {
    repo.failWith = StateError('offline');
    await coordinator.start();
    plugin.fireTap(AlertTap(noticeId: nid, taskId: 'a', action: NoticeAction.done));
    await settle();
    expect(errors, hasLength(1));
    expect(feed.read, isEmpty);
    coordinator.dispose();
  });

  test('dispose is clean: later events do nothing, twice is fine', () async {
    await coordinator.start();
    coordinator.dispose();
    coordinator.dispose();
    repo.push([task]);
    feed.push([notice()]);
    plugin.fireTap(AlertTap(noticeId: nid, taskId: 'a', route: '/tasks/a'));
    await settle();
    expect(plugin.scheduled, isEmpty);
    expect(opened, isEmpty);
    expect(errors, isEmpty);
  });

  group('priming', () {
    TaskAlertsCoordinator make({PushRegistrar? registrar, TaskClock? clock}) => TaskAlertsCoordinator(
          repository: repo,
          feed: feed,
          plugin: plugin,
          prefs: const TaskPrefs(),
          userId: 'me',
          push: registrar,
          clock: clock ?? TaskClock(() => _now),
          onError: (e, s) => errors.add(e),
          stages: (t, p, n) => [due],
        );

    test('a repository that emits only after refresh() still gets scheduled after start()', () async {
      repo.serverTasks = [task];
      final c = make();
      await c.start();
      await settle();
      expect(repo.refreshCalls, greaterThan(0));
      expect(feed.refreshCalls, greaterThan(0));
      expect(plugin.scheduled, hasLength(1));
      c.dispose();
    });

    test('resume() refreshes both sources and picks up a server-side change', () async {
      repo.serverTasks = [task];
      final c = make();
      await c.start();
      await settle();
      final before = repo.refreshCalls;
      final beforeFeed = feed.refreshCalls;
      repo.serverTasks = const []; // the task was completed elsewhere
      await c.resume();
      await settle();
      expect(repo.refreshCalls, before + 1);
      expect(feed.refreshCalls, beforeFeed + 1);
      expect(plugin.scheduled, isEmpty);
      c.dispose();
    });

    test('resume() survives a failing refresh and a failing sync', () async {
      final c = make();
      await c.start();
      repo.refreshFails = StateError('offline');
      await c.resume();
      expect(errors, hasLength(1));
      c.dispose();
    });
  });

  group('push registrar and sign-out', () {
    test('start() starts the registrar once; signOut unregisters and cancels; dispose leaves it usable', () async {
      final reg = _FakeRegistrar();
      final c = TaskAlertsCoordinator(
        repository: repo,
        feed: feed,
        plugin: plugin,
        prefs: const TaskPrefs(),
        userId: 'me',
        push: reg,
        clock: TaskClock(() => _now),
        stages: (t, p, n) => [due],
      );
      await c.start();
      repo.push([task]);
      await settle();
      expect(reg.starts, 1);
      expect(plugin.scheduled, hasLength(1));
      await c.signOut();
      expect(reg.unregisters, 1);
      expect(plugin.scheduled, isEmpty);
      c.dispose();
      expect(reg.disposes, 0, reason: 'the app owns the registrar');
    });

    test('signOut carries on when unregister fails, and forgets seen notices', () async {
      final reg = _FakeRegistrar()..unregisterFails = StateError('offline');
      final c = TaskAlertsCoordinator(
        repository: repo,
        feed: feed,
        plugin: plugin,
        prefs: const TaskPrefs(),
        userId: 'me',
        push: reg,
        clock: TaskClock(() => _now),
        onError: (e, s) => errors.add(e),
        stages: (t, p, n) => [due],
      );
      await c.start();
      repo.push([task]);
      await settle();
      await c.signOut();
      expect(errors, hasLength(1));
      expect(plugin.scheduled, isEmpty);
      // the next user: the first snapshot is a baseline again, nothing is posted
      await c.start();
      feed.push([notice()]);
      await settle();
      expect(plugin.shown, isEmpty);
      c.dispose();
    });
  });
}
