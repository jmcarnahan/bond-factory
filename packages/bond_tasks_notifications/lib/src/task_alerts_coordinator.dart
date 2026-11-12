/// The one object an app creates for task alerts.
library;

import 'dart:async';

import 'package:bond_notify/bond_notify.dart';
import 'package:bond_push/bond_push.dart';
import 'package:bond_tasks/bond_tasks.dart';

import 'alert_labels.dart';
import 'alert_plugin.dart';
import 'local_task_alerts.dart';
import 'notice_action_handler.dart';

/// Wires local alerts, synced notices, push taps and the action handler.
///
/// New unread notices come from `feed.watch()` (the coordinator subscribes itself; it does not
/// need a NoticeController). The first snapshot is only a baseline, and a notice older than
/// [freshFor] (10 minutes, as in bond_notify's NoticeController) is never posted, so a launch does
/// not replay the inbox. An app must not feed a NoticeController's `newUnread` into a second alert
/// path beside the coordinator: the person would be told twice.
///
/// A notice whose scheduled copy already fired is not shown again; see `LocalTaskAlerts.onNoticeArrived`.
/// The same tap reported twice within 3 seconds (the launch tap and the response callback on a cold
/// start) is handled once.
///
/// Push: an app that turns push on passes `handledElsewhere: {'close', 'due', 'past'}`, or the
/// person is told twice. The coordinator never sets it by itself.
class TaskAlertsCoordinator {
  TaskAlertsCoordinator({
    required this.repository,
    required this.feed,
    required this.plugin,
    required this.prefs,
    required this.userId,
    this.push,
    this.pushTaps,
    this.onOpen,
    this.postNow = true,
    this.handledElsewhere = const {},
    this.budget = 60,
    this.perTask = 3,
    this.freshFor = const Duration(minutes: 10),
    this.clock = const TaskClock(),
    this.labels = const AlertLabels(),
    this.onError,
    List<StageTime> Function(Task, TaskPrefs, DateTime nowUtc)? stages,
  }) : alerts = LocalTaskAlerts(
          repository,
          plugin,
          prefs: prefs,
          userId: userId,
          handledElsewhere: handledElsewhere,
          budget: budget,
          perTask: perTask,
          clock: clock,
          labels: labels,
          onError: onError,
          stages: stages,
        ) {
    _handler = NoticeActionHandler(repository, feed, plugin: plugin);
  }

  final TaskRepository repository;
  final NoticeFeed feed;
  final AlertPlugin plugin;
  TaskPrefs prefs;
  final String userId;
  final PushRegistrar? push;
  final PushTaps? pushTaps;

  /// Called with the route of a plain tap.
  final void Function(String route)? onOpen;

  /// Show a synced notice at once (the app is running). Turn off to only cancel scheduled copies.
  final bool postNow;
  final Set<String> handledElsewhere;
  final int budget;
  final int perTask;
  final Duration freshFor;
  final TaskClock clock;
  final AlertLabels labels;
  final void Function(Object error, StackTrace stack)? onError;

  /// The local scheduler, for `requestPermission()` and `cancelAll()` (sign-out).
  final LocalTaskAlerts alerts;

  late final NoticeActionHandler _handler;
  final List<StreamSubscription<Object?>> _subs = [];
  final Map<String, Notice> _known = {};
  final Map<String, DateTime> _recentTaps = {};
  bool _baselined = false;
  bool _disposed = false;

  Future<void> start() async {
    _subs.add(alerts.taps.listen((t) => _handle(t.noticeId, t.taskId, t.route, t.action)));
    await alerts.start();
    _subs.add(feed.watch().listen(_onNotices, onError: _report));
    await _guard(feed.refresh); // a feed that waits for its poll interval would stay empty until then
    final pt = pushTaps;
    if (pt != null) {
      _subs.add(pt.taps.listen(_onPushTap, onError: _report));
    }
    try {
      await push?.start();
    } catch (e, st) {
      _report(e, st);
    }
    try {
      final launch = await plugin.launchTap();
      if (launch != null) _handle(launch.noticeId, launch.taskId, launch.route, launch.action);
      final first = await pt?.initialTap();
      if (first != null) _onPushTap(first);
    } catch (e, st) {
      _report(e, st);
    }
  }

  /// Call when the app returns to the foreground: refreshes the tasks and the feed (a change made on
  /// the server while the app was closed is picked up) and re-plans the alerts.
  Future<void> resume() async {
    await _guard(repository.refresh);
    await _guard(feed.refresh);
    await _guard(alerts.sync);
  }

  /// Sign-out: unregisters the device from push, cancels every local alert, stops listening to the
  /// repository and forgets the notices seen. Call [start] again for the next user. The coordinator
  /// does not dispose the [PushRegistrar]: the app owns it.
  Future<void> signOut() async {
    await _guard(() async => push?.unregister());
    await _guard(alerts.cancelAll);
    for (final sub in _subs) {
      await sub.cancel();
    }
    _subs.clear();
    _known.clear();
    _recentTaps.clear();
    _baselined = false;
  }

  Future<void> _guard(Future<void> Function() call) async {
    try {
      await call();
    } catch (e, st) {
      _report(e, st);
    }
  }

  void dispose() {
    if (_disposed) return;
    _disposed = true;
    for (final s in _subs) {
      s.cancel();
    }
    _subs.clear();
    alerts.dispose();
  }

  void _onNotices(List<Notice> items) {
    final now = clock.nowUtc();
    for (final n in items) {
      final isNew = !_known.containsKey(n.id);
      _known[n.id] = n;
      if (!isNew || !n.unread) continue;
      final created = n.createdAt;
      final fresh = created == null || now.difference(created) <= freshFor;
      alerts.onNoticeArrived(n, postNow: postNow && _baselined && fresh).catchError(_report);
    }
    _baselined = true;
  }

  void _onPushTap(PushTap t) {
    final id = t.noticeId;
    var taskId = id == null ? null : _known[id]?.taskId;
    final route = t.route;
    if (taskId == null && route != null && route.startsWith('/tasks/')) taskId = route.substring(7);
    _handle(id ?? '', taskId ?? '', route, NoticeAction.fromWire(t.action));
  }

  /// The person's work day changed: re-plans every local alert.
  void updatePrefs(TaskPrefs value) {
    prefs = value;
    alerts.updatePrefs(value);
  }

  void _handle(String noticeId, String taskId, String? route, NoticeAction? action) {
    if (_disposed) return;
    final now = clock.nowUtc();
    final key = '$noticeId|${action?.wire}';
    _recentTaps.removeWhere((_, at) => now.difference(at) > const Duration(seconds: 3));
    if (noticeId.isNotEmpty && _recentTaps.containsKey(key)) return;
    _recentTaps[key] = now;
    if (action != null && noticeId.isNotEmpty && taskId.isNotEmpty) {
      _handler.apply(noticeId, taskId, action).catchError(_report);
      return;
    }
    final r = route ?? (taskId.isEmpty ? null : '/tasks/$taskId');
    if (r != null) onOpen?.call(r);
  }

  void _report(Object e, StackTrace st) => onError?.call(e, st);
}
