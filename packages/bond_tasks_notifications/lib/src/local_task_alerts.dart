/// Schedules the local notices of the open tasks.
library;

import 'dart:async';

import 'package:bond_notify/bond_notify.dart';
import 'package:bond_tasks/bond_tasks.dart';

import 'alert_labels.dart';
import 'alert_planner.dart';
import 'alert_plugin.dart';

/// Keeps the phone's pending alerts equal to the notices the open tasks will need.
///
/// Every operation runs through one queue, so two syncs never interleave. The phone holds at most 64
/// pending alerts: [budget] (default 60) caps the total, [perTask] caps one task, nearest first.
class LocalTaskAlerts {
  LocalTaskAlerts(
    this.repository,
    this.plugin, {
    this.prefs = const TaskPrefs(),
    required this.userId,
    this.handledElsewhere = const {},
    this.budget = 60,
    this.perTask = 3,
    List<StageTime> Function(Task, TaskPrefs, DateTime nowUtc)? stages,
    this.clock = const TaskClock(),
    this.labels = const AlertLabels(),
    this.onError,
  }) : stages = stages ?? ((t, p, now) => stageTimesFor(t, p, now, userId: userId));

  /// The schedule of one task; defaults to bond_tasks' `stageTimesFor` for [userId]. Tests inject their own.
  final List<StageTime> Function(Task, TaskPrefs, DateTime nowUtc) stages;

  final TaskRepository repository;
  final AlertPlugin plugin;
  /// The person's work day; change it with [updatePrefs].
  TaskPrefs prefs;
  final String userId;

  /// Stage names (`close`, `due`, `past`) another channel (push) already delivers; never scheduled here.
  final Set<String> handledElsewhere;

  /// At most this many pending alerts in total (iOS allows 64).
  final int budget;

  /// At most this many pending alerts per task, nearest first.
  final int perTask;

  final TaskClock clock;
  final AlertLabels labels;

  /// Called with an error from one plugin call or from the task stream; the sync carries on.
  final void Function(Object error, StackTrace stack)? onError;

  final _taps = StreamController<AlertTap>.broadcast();
  final Set<String> _posted = {};

  /// Pending alerts that are ours: id to the time we scheduled (null when rebuilt after a restart).
  final Map<int, DateTime?> _times = {};
  /// Ids of our alerts that left the pending list: they fired.
  final Set<int> _fired = {};
  final Map<int, String> _prints = {};
  bool _inited = false;
  Future<void>? _initing;
  List<Task>? _tasks;
  StreamSubscription<List<Task>>? _sub;
  Future<void> _tail = Future<void>.value();
  bool _disposed = false;

  /// Taps on notifications and their buttons (fed by the plugin once [start] has run).
  Stream<AlertTap> get taps => _taps.stream;

  /// Initialises the plugin (no permission prompt), rebuilds the snapshot from what is pending,
  /// and syncs on every change of the open tasks. Do not init the plugin elsewhere.
  /// Then refreshes the repository (errors go to [onError]). Safe to call again after [cancelAll];
  /// a second call while the first is running waits for it.
  Future<void> start() async {
    if (_disposed) return;
    if (!_inited) {
      final running = _initing;
      if (running != null) {
        await running; // a concurrent start waits for the first one (and sees its failure)
      } else {
        final f = plugin.init(onTap: (t) {
          if (!_taps.isClosed) _taps.add(t);
        });
        _initing = f;
        try {
          await f;
          _inited = true; // only after init succeeded, so a failed start can be retried
        } finally {
          _initing = null;
        }
      }
    }
    await _enqueue(() async {
      _times.clear();
      for (final p in await _safePending()) {
        if (AlertTap.fromPayload(p.payload) != null) _times[p.id] = null;
      }
    });
    if (_disposed || _sub != null) return;
    _sub = repository.watchOpen().listen((tasks) {
      _tasks = tasks;
      sync().catchError(_report);
    }, onError: _report);
    // A repository such as the REST one emits only after a refresh: prime it.
    await _guard(repository.refresh);
  }

  /// Asks the person for notification permission. Never called by [start].
  Future<bool> requestPermission() => plugin.requestPermission();

  /// Brings the pending alerts in line with the latest open tasks.
  Future<void> sync() {
    if (_disposed) return Future<void>.value();
    return _enqueue(_runSync);
  }

  /// The person's work day changed: store it and re-plan every alert.
  void updatePrefs(TaskPrefs value) {
    prefs = value;
    sync().catchError(_report);
  }

  /// A synced notice arrived.
  /// - Its id is among the plugin's delivered, still shown notifications: not shown again.
  /// - Our own scheduled copy has already fired (or is firing): the person has seen it, so nothing
  ///   is shown and nothing is cancelled (that would clear the delivered one).
  /// - Otherwise a pending scheduled copy is cancelled, and when [postNow] (the app is running)
  ///   and the notice's stage is not in [handledElsewhere], it is shown at once under the same id.
  /// A notice id is shown at most once. Nothing is persisted.
  Future<void> onNoticeArrived(Notice notice, {bool postNow = true}) => _enqueue(() async {
        if (_disposed) return;
        final id = fnv1a31(notice.id);
        final at = _times[id];
        final fired = _fired.contains(id) || (at != null && !at.isAfter(clock.nowUtc()));
        if (fired) {
          _times.remove(id);
          _fired.add(id);
          return;
        }
        // Already on the lock screen (it fired while the app was closed): leave it alone. Cancelling
        // would clear it, and showing would repeat it.
        List<int> active = const [];
        try {
          active = await plugin.active();
        } catch (e, st) {
          _report(e, st);
        }
        if (active.contains(id)) {
          _times.remove(id);
          _posted.add(notice.id);
          return;
        }
        await _guard(() => plugin.cancel(id));
        _times.remove(id);
        final taskId = notice.taskId;
        if (!postNow || taskId == null || handledElsewhere.contains(notice.stage)) return;
        if (_posted.contains(notice.id)) return;
        _posted.add(notice.id);
        await _guard(() => plugin.show(AlertRequest(
              id: id,
              noticeId: notice.id,
              taskId: taskId,
              title: notice.title,
              body: notice.body,
              atUtc: clock.nowUtc(),
              route: notice.route,
              actions: [
                for (final a in notice.actions)
                  if (NoticeAction.fromWire(a) != null) NoticeAction.fromWire(a)!,
              ],
            )));
      });

  /// Sign-out: cancels every pending alert of ours, forgets the task list and stops listening to the
  /// repository until [start] is called again.
  Future<void> cancelAll() => _enqueue(() async {
        await _sub?.cancel();
        _sub = null;
        _tasks = null;
        for (final id in _times.keys.toList()) {
          await _guard(() => plugin.cancel(id));
        }
        _times.clear();
        _prints.clear();
        _fired.clear();
        _posted.clear();
      });

  Future<void> dispose() async {
    _disposed = true;
    await _sub?.cancel();
    _sub = null;
    await _taps.close();
  }

  // ---- internals ----

  Future<void> _runSync() async {
    final tasks = _tasks;
    if (tasks == null || _disposed) return;
    final wanted = planAlerts(
      tasks: tasks,
      now: clock.nowUtc(),
      prefs: prefs,
      userId: userId,
      stages: stages,
      handledElsewhere: handledElsewhere,
      perTask: perTask,
      budget: budget,
      labels: labels,
    );
    final List<PendingAlert> list;
    try {
      list = await plugin.pending();
    } catch (e, st) {
      // Without the pending list every id would look fired: skip this sync.
      _report(e, st);
      return;
    }
    if (_disposed) return;
    final pending = {for (final p in list) p.id};
    // Alerts that fired are no longer pending: remember that, never cancel them (that would clear the delivered one).
    for (final id in _times.keys.where((id) => !pending.contains(id))) {
      _fired.add(id);
    }
    _times.removeWhere((id, _) => !pending.contains(id));
    for (final p in list) {
      if (AlertTap.fromPayload(p.payload) != null) _times.putIfAbsent(p.id, () => null);
    }
    final keep = {for (final r in wanted) r.id};
    for (final id in _times.keys.toList()) {
      if (keep.contains(id)) continue;
      await _guard(() => plugin.cancel(id));
      _times.remove(id);
    }
    for (final r in wanted) {
      if (_disposed) return;
      final print = alertFingerprint(r);
      if (pending.contains(r.id) && _times[r.id] == r.atUtc && _prints[r.id] == print) continue;
      if (await _guard(() => plugin.schedule(r))) {
        _times[r.id] = r.atUtc;
        _prints[r.id] = print;
        _fired.remove(r.id);
      }
    }
  }

  Future<T> _enqueue<T>(Future<T> Function() op) {
    final done = Completer<T>();
    _tail = _tail.then((_) async {
      try {
        done.complete(await op());
      } catch (e, st) {
        done.completeError(e, st);
      }
    });
    return done.future;
  }

  Future<List<PendingAlert>> _safePending() async {
    try {
      return await plugin.pending();
    } catch (e, st) {
      _report(e, st);
      return const [];
    }
  }

  Future<bool> _guard(Future<void> Function() call) async {
    try {
      await call();
      return true;
    } catch (e, st) {
      _report(e, st);
      return false;
    }
  }

  void _report(Object e, StackTrace st) => onError?.call(e, st);
}
