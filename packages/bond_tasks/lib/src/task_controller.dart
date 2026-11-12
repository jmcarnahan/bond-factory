/// Framework-free task list state: optimistic complete with undo.
library;

import 'dart:async';

import 'task.dart';
import 'task_clock.dart';
import 'task_controller_state.dart';
import 'task_controller_support.dart';
import 'task_due.dart';
import 'task_filters.dart';
import 'task_repository.dart';
import 'task_sections.dart';
import 'task_today.dart';

export 'task_controller_state.dart';

/// Holds the open list and the day view, with no UI framework. Listen to [states]; a new listener first
/// receives the current state. The day sections are derived on the device with [sectionTasks].
class TaskController {
  /// [reloadDelay] is the wait before the day view is re-read after a task vanished from the open
  /// stream (completed elsewhere): it refreshes counts such as `doneToday`; a new emission restarts it.
  TaskController(this.repo, {this.clock = const TaskClock(), this.reloadDelay = const Duration(milliseconds: 500)});

  final TaskRepository repo;
  final TaskClock clock;
  final Duration reloadDelay;

  int _loadGen = 0;
  int _seq = 0;
  Timer? _reload;

  /// When (in [_seq] order) each task finished completing, so a load that started earlier cannot bring it back.
  final Map<String, int> _completedAt = {};

  /// The running `complete` call of each id; a second call for the same id shares it.
  final Map<String, Future<void>> _inflight = {};

  final StreamController<TaskControllerState> _ctrl = StreamController<TaskControllerState>.broadcast();
  TaskControllerState _state = const TaskControllerState();
  StreamSubscription<List<Task>>? _watch;
  bool _disposed = false;

  /// Ids completed on screen whose call has not finished; a repository emission must not bring them back.
  final Set<String> _pending = {};

  /// The completed tasks as they stood, so a failure or [undo] can put each back where it was.
  final Map<String, RemovedTask> _removed = {};

  Stream<TaskControllerState> get states => Stream<TaskControllerState>.multi((c) {
    c.add(_state);
    final sub = _ctrl.stream.listen(c.add, onError: c.addError, onDone: c.close);
    c.onCancel = sub.cancel;
  }, isBroadcast: true);

  TaskControllerState get state => _state;

  /// Reads the day view and the open list, then follows the repository's open-task stream.
  ///
  /// Only the newest `load` may change the state (an older overlapping one is dropped), and a task whose
  /// `complete` started or finished after this load began is left out of its answer.
  Future<void> load() async {
    final gen = ++_loadGen;
    final start = ++_seq;
    bool live(Task t) => !_pending.contains(t.id) && (_completedAt[t.id] ?? 0) <= start;
    _emit(_state.copyWith(loading: true, clearError: true));
    try {
      _watch ??= repo.watchOpen().listen(_onOpen, onError: (Object e) => _emit(_state.copyWith(error: e)));
      final server = await repo.today();
      final items = (await _readOpen()).where(live).toList();
      if (gen != _loadGen) return;
      final known = [
        for (final t in [...server.overdue, ...server.today, ...server.undated, ...items])
          if (live(t)) t,
      ];
      _completedAt.clear();
      _emit(
        TaskControllerState(
          open: _derive(items),
          today: sectionTasks(
            known,
            clock.nowUtc(),
            doneToday: server.doneToday,
            doneTodayCount: server.counts.doneToday,
          ),
          undoTaskId: _state.undoTaskId,
        ),
      );
    } catch (e) {
      if (gen == _loadGen) _emit(_state.copyWith(loading: false, error: e));
    }
  }

  /// Every page of the open list, so a server default page size cannot truncate it.
  Future<List<Task>> _readOpen() async {
    const size = 200;
    final out = <Task>[];
    for (var offset = 0; ; offset += size) {
      final page = await repo.list(TaskFilters(scope: 'mine', status: 'open', limit: size, offset: offset));
      out.addAll(page.items);
      if (page.items.length < size || out.length >= page.total) return out;
    }
  }

  /// Optimistic: the task leaves the lists at once. If the call fails only that task comes back (at its
  /// place in the lists as they are now, so changes that arrived meanwhile stay) and the error is set. A
  /// second call replaces the undo target.
  ///
  /// A second call for an id that is still completing shares the first call (no second request).
  Future<void> complete(String id) {
    final running = _inflight[id];
    if (running != null) return running;
    final f = _complete(id).whenComplete(() {
      _inflight.remove(id); // a block body: returning the removed future would make it wait on itself
    });
    _inflight[id] = f;
    return f;
  }

  Future<void> _complete(String id) async {
    final i = _state.open.indexWhere((t) => t.id == id);
    final inSection = _flatten(_state.today).where((t) => t.id == id);
    final task = i >= 0 ? _state.open[i] : (inSection.isEmpty ? null : inSection.first);
    final removed = task == null
        ? null
        : RemovedTask(task, [for (final t in _state.open) t.id], [for (final t in _flatten(_state.today)) t.id]);
    if (removed != null) _removed[id] = removed;
    final previousUndo = _state.undoTaskId;
    _pending.add(id);
    _emit(_without(id).copyWith(undoTaskId: id, clearError: true));
    try {
      await repo.complete(id);
      _completedAt[id] = ++_seq;
      _pending.remove(id);
    } catch (e) {
      _pending.remove(id);
      _removed.remove(id);
      final back = removed == null ? _state : _restore(removed, removed.task);
      _emit(
        TaskControllerState(
          open: back.open,
          today: back.today,
          undoTaskId: _state.undoTaskId == id ? previousUndo : _state.undoTaskId,
          error: e,
        ),
      );
    }
  }

  /// Reopens the task that [complete] last finished and puts it back in its place.
  Future<void> undo() async {
    final id = _state.undoTaskId;
    if (id == null) return;
    final running = _inflight[id];
    if (running != null) {
      await running; // reopen only after the complete call has finished
      if (_state.undoTaskId != id) return; // it failed and the task is back: nothing to undo
    }
    final removed = _removed.remove(id);
    try {
      final reopened = await repo.reopen(id);
      final base = removed ?? RemovedTask(reopened, const [], const []);
      _emit(_restore(base, reopened).copyWith(clearUndo: true, clearError: true));
    } catch (e) {
      if (removed != null) _removed[id] = removed;
      _emit(_state.copyWith(error: e));
    }
  }

  /// Re-derives `overdue` of every task from `dueAt` and the clock and re-sections the day view
  /// ([sectionTasks]: a task whose due instant passed moves from `today` to `overdue`, counts follow);
  /// call it from a minute ticker. Emits only when something changed. A new calendar day also changes
  /// the sections, so call it (or [load]) after the day changes.
  void refreshDerived() {
    final t = _state.today;
    final next = _state.copyWith(
      open: _derive(_state.open),
      today: t == null
          ? null
          : sectionTasks(
              [..._flatten(t), ..._state.open],
              clock.nowUtc(),
              doneToday: t.doneToday,
              doneTodayCount: t.counts.doneToday,
            ),
    );
    if (controllerShape(next) == controllerShape(_state)) return;
    _emit(next);
  }

  void dispose() {
    _disposed = true;
    _reload?.cancel();
    _watch?.cancel();
    _ctrl.close();
  }

  void _onOpen(List<Task> tasks) {
    final open = _derive(tasks.where((t) => !_pending.contains(t.id)).toList());
    final ids = {for (final t in tasks) t.id};
    if (_state.open.any((t) => !ids.contains(t.id) && !_pending.contains(t.id))) {
      // A task left the open list that this screen did not complete: it was done or cancelled elsewhere,
      // so counts such as doneToday are stale. Re-read the day view once the emissions settle.
      _reload?.cancel();
      _reload = Timer(reloadDelay, () {
        if (!_disposed) load();
      });
    }
    final t = _state.today;
    if (t == null) return _emit(_state.copyWith(open: open));
    // Keep the sections' existing order among equal due instants.
    final byId = {for (final x in open) x.id: x};
    final ordered = [
      for (final x in _flatten(t))
        if (byId.containsKey(x.id)) byId[x.id]!,
      ...open,
    ];
    _emit(
      _state.copyWith(
        open: open,
        today: sectionTasks(ordered, clock.nowUtc(), doneToday: t.doneToday, doneTodayCount: t.counts.doneToday),
      ),
    );
  }

  void _emit(TaskControllerState s) {
    _state = s;
    if (!_disposed) _ctrl.add(s);
  }

  List<Task> _derive(List<Task> l) {
    final now = clock.nowUtc();
    return [for (final t in l) isOverdue(t, now) == t.overdue ? t : t.copyWith(overdue: !t.overdue)];
  }

  List<Task> _flatten(TaskToday? t) => t == null ? const [] : [...t.overdue, ...t.today, ...t.undated];

  TaskControllerState _without(String id) {
    List<Task> drop(List<Task> l) => [
      for (final t in l)
        if (t.id != id) t,
    ];
    final t = _state.today;
    int less(List<Task> l, int n) => l.any((x) => x.id == id) ? (n > 0 ? n - 1 : 0) : n;
    return TaskControllerState(
      open: drop(_state.open),
      today: t == null
          ? null
          : TaskToday(
              overdue: drop(t.overdue),
              today: drop(t.today),
              undated: drop(t.undated),
              doneToday: t.doneToday,
              counts: TaskTodayCounts(
                overdue: less(t.overdue, t.counts.overdue),
                today: less(t.today, t.counts.today),
                undated: less(t.undated, t.counts.undated),
                doneToday: t.counts.doneToday,
              ),
            ),
      undoTaskId: _state.undoTaskId,
    );
  }

  /// Puts [task] back into the current lists, before the first task that followed it when it was removed
  /// (else after the one before it, else at the end), and re-sections.
  TaskControllerState _restore(RemovedTask r, Task task) {
    final wasOpen = r.openOrder.contains(task.id);
    final open = wasOpen || r.openOrder.isEmpty ? insertInOrder(_state.open, task, r.openOrder) : _state.open;
    final t = _state.today;
    if (t == null) return _state.copyWith(open: _derive(open));
    final flat = insertInOrder(_flatten(t), task, r.sectionOrder.isEmpty ? r.openOrder : r.sectionOrder);
    return _state.copyWith(
      open: _derive(open),
      today: sectionTasks(
        flat,
        clock.nowUtc(),
        doneToday: [
          for (final x in t.doneToday)
            if (x.id != task.id) x,
        ],
        doneTodayCount: t.counts.doneToday,
      ),
    );
  }
}
