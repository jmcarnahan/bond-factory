import 'dart:async';

import 'package:bond_tasks/bond_tasks.dart';
import 'package:test/test.dart';

Task _task(String id, {DateTime? dueAt, String? date}) => Task(
      id: id,
      title: id,
      dueDate: date ?? (dueAt == null ? null : '2026-03-12'),
      dueTime: dueAt == null ? null : '09:30',
      dueAt: dueAt,
      ownerUserId: 'u',
    );

class _FakeRepo implements TaskRepository {
  _FakeRepo(this.tasks);

  List<Task> tasks;
  Object? completeError;
  Completer<void>? gate;
  final List<String> calls = [];
  final StreamController<List<Task>> _open = StreamController<List<Task>>.broadcast();

  @override
  Stream<List<Task>> watchOpen() => _open.stream;
  void push(List<Task> l) => _open.add(l);

  @override
  Future<TaskToday> today() async {
    todayCalls++;
    return TaskToday(
      today: [for (final t in tasks) t],
      counts: TaskTodayCounts(today: tasks.length, doneToday: doneCount),
    );
  }

  int todayCalls = 0;
  int doneCount = 0;

  @override
  Future<TaskPage> list(TaskFilters f) async => TaskPage(items: tasks, total: tasks.length);

  @override
  Future<Task> complete(String id) async {
    calls.add('complete $id');
    await gate?.future;
    if (completeError != null) throw completeError!;
    return tasks.firstWhere((t) => t.id == id).copyWith(status: TaskStatus.done);
  }

  @override
  Future<Task> reopen(String id) async {
    calls.add('reopen $id');
    return tasks.firstWhere((t) => t.id == id);
  }

  @override
  Future<TaskSummary> summary() async => const TaskSummary();
  @override
  Future<Task> create(TaskDraft d) => throw UnimplementedError();
  @override
  Future<Task> update(String id, TaskPatch p) => throw UnimplementedError();
  @override
  Future<Task> cancel(String id) => throw UnimplementedError();
  @override
  Future<void> delete(String id) async {}
  @override
  Future<void> refresh() async {}
  @override
  void dispose() {}
}

void main() {
  late _FakeRepo repo;
  late DateTime now;
  late TaskController c;

  setUp(() {
    now = DateTime.utc(2026, 3, 12, 10);
    repo = _FakeRepo([_task('a', date: '2026-03-12'), _task('b', date: '2026-03-12'), _task('c', date: '2026-03-12')]);
    c = TaskController(repo, clock: TaskClock(() => now));
  });
  tearDown(() => c.dispose());

  test('load reads the day view and the open list', () async {
    await c.load();
    expect(c.state.open.map((t) => t.id), ['a', 'b', 'c']);
    expect(c.state.today!.today.length, 3);
    expect(c.state.loading, isFalse);
    expect(c.state.error, isNull);
  });

  test('a new listener first gets the current state', () async {
    await c.load();
    final first = await c.states.first;
    expect(first.open.length, 3);
    final seen = <int>[];
    final sub = c.states.listen((s) => seen.add(s.open.length));
    await Future<void>.delayed(Duration.zero);
    expect(seen, [3]);
    await c.complete('a');
    await Future<void>.delayed(Duration.zero);
    expect(seen.last, 2);
    await sub.cancel();
  });

  test('complete removes the task at once, before the call finishes', () async {
    await c.load();
    repo.gate = Completer<void>();
    final f = c.complete('b');
    expect(c.state.open.map((t) => t.id), ['a', 'c']);
    expect(c.state.today!.today.map((t) => t.id), ['a', 'c']);
    expect(c.state.today!.counts.today, 2);
    expect(c.state.undoTaskId, 'b');
    repo.gate!.complete();
    await f;
    expect(c.state.open.map((t) => t.id), ['a', 'c']);
    expect(c.state.error, isNull);
  });

  test('a repository emission during the call does not bring the task back', () async {
    await c.load();
    repo.gate = Completer<void>();
    final f = c.complete('b');
    repo.push([_task('a', date: '2026-03-12'), _task('b', date: '2026-03-12'), _task('c', date: '2026-03-12')]);
    await Future<void>.delayed(Duration.zero);
    expect(c.state.open.map((t) => t.id), ['a', 'c']);
    repo.gate!.complete();
    await f;
  });

  test('a failed complete puts back only that task and keeps what arrived meanwhile', () async {
    await c.load();
    repo.gate = Completer<void>();
    repo.completeError = StateError('offline');
    final f = c.complete('b');
    // The stream brings a new task d and drops a, while the call is still in flight.
    repo.push([_task('c', date: '2026-03-12'), _task('d', date: '2026-03-12')]);
    await Future<void>.delayed(Duration.zero);
    expect(c.state.open.map((t) => t.id), ['c', 'd']);
    repo.gate!.complete();
    await f;
    expect(c.state.open.map((t) => t.id), ['b', 'c', 'd'], reason: 'b returns before the task that followed it');
    expect(c.state.today!.today.map((t) => t.id), ['b', 'c', 'd']);
    expect(c.state.today!.counts.today, 3);
    expect(c.state.error, isA<StateError>());
    expect(c.state.undoTaskId, isNull);
  });

  test('a task of a later day enters today when the day changes', () async {
    repo = _FakeRepo([_task('x', date: '2026-03-13')]);
    final ctl = TaskController(repo, clock: TaskClock(() => now));
    await ctl.load();
    expect(ctl.state.today!.today, isEmpty, reason: 'tomorrow is upcoming: in no section');
    expect(ctl.state.open.map((t) => t.id), ['x']);
    now = DateTime.utc(2026, 3, 13, 12);
    ctl.refreshDerived();
    expect(ctl.state.today!.today.map((t) => t.id), ['x']);
    expect(ctl.state.today!.counts.today, 1);
    ctl.dispose();
  });

  test('a failed complete restores the lists and sets the error', () async {
    await c.load();
    repo.completeError = StateError('offline');
    await c.complete('b');
    expect(c.state.open.map((t) => t.id), ['a', 'b', 'c']);
    expect(c.state.today!.today.map((t) => t.id), ['a', 'b', 'c']);
    expect(c.state.today!.counts.today, 3);
    expect(c.state.error, isA<StateError>());
    expect(c.state.undoTaskId, isNull);
  });

  test('undo reopens the task and puts it back where it was', () async {
    await c.load();
    await c.complete('b');
    await c.undo();
    expect(repo.calls, ['complete b', 'reopen b']);
    expect(c.state.open.map((t) => t.id), ['a', 'b', 'c']);
    expect(c.state.today!.today.map((t) => t.id), ['a', 'b', 'c']);
    expect(c.state.today!.counts.today, 3);
    expect(c.state.undoTaskId, isNull);
  });

  test('undo with nothing to undo does nothing', () async {
    await c.load();
    await c.undo();
    expect(repo.calls, isEmpty);
  });

  test('a second complete replaces the undo target', () async {
    await c.load();
    await c.complete('a');
    await c.complete('c');
    expect(c.state.undoTaskId, 'c');
    await c.undo();
    expect(repo.calls.last, 'reopen c');
    expect(c.state.open.map((t) => t.id), ['b', 'c']);
  });

  test('refreshDerived flips overdue at the due minute and not before', () async {
    repo.tasks = [_task('a', dueAt: DateTime.utc(2026, 3, 12, 16, 30)), _task('u')];
    await c.load();
    expect(c.state.open.first.overdue, isFalse);
    final emitted = <TaskControllerState>[];
    final sub = c.states.skip(1).listen(emitted.add);

    now = DateTime.utc(2026, 3, 12, 16, 30);
    c.refreshDerived();
    await Future<void>.delayed(Duration.zero);
    expect(c.state.open.first.overdue, isFalse, reason: 'due at the instant is not yet past it');
    expect(emitted, isEmpty, reason: 'nothing changed, nothing emitted');

    now = DateTime.utc(2026, 3, 12, 16, 31);
    c.refreshDerived();
    await Future<void>.delayed(Duration.zero);
    expect(c.state.open.first.overdue, isTrue);
    expect(c.state.today!.overdue.single.overdue, isTrue);
    expect(c.state.open.last.overdue, isFalse);
    expect(emitted, hasLength(1));
    c.refreshDerived();
    await Future<void>.delayed(Duration.zero);
    expect(emitted, hasLength(1), reason: 'a second tick with no change emits nothing');
    await sub.cancel();
  });

  test('a task due 17:00 moves from today to overdue at 17:01 and the counts follow', () async {
    DateTime at(int h, int m) => DateTime.utc(2026, 3, 12, h, m);
    repo = _FakeRepo([
      _task('early', dueAt: at(23, 0)),
      _task('t5', dueAt: at(17, 0)),
      _task('no-time', date: '2026-03-12'),
      _task('old', dueAt: at(9, 0)),
    ]);
    // Ordered by the server: `old` is already overdue; the others are today.
    final server = TaskToday(
      overdue: [repo.tasks[3]],
      today: [repo.tasks[0], repo.tasks[1], repo.tasks[2]],
      counts: const TaskTodayCounts(overdue: 1, today: 3),
    );
    final r = _SectionRepo(repo.tasks, server);
    final ctl = TaskController(r, clock: TaskClock(() => now));
    now = at(16, 59);
    await ctl.load();
    // At load the stale server section is already corrected: `old` was overdue, nothing else is.
    expect(ctl.state.today!.today.map((t) => t.id), ['t5', 'early', 'no-time']);
    expect(ctl.state.today!.overdue.map((t) => t.id), ['old']);

    now = at(17, 1);
    ctl.refreshDerived();
    expect(ctl.state.today!.overdue.map((t) => t.id), ['old', 't5'], reason: 'by dueAt ascending');
    expect(ctl.state.today!.today.map((t) => t.id), ['early', 'no-time']);
    expect(ctl.state.today!.counts.overdue, 2);
    expect(ctl.state.today!.counts.today, 2);
    // Nobody is in two sections.
    final all = [...ctl.state.today!.overdue, ...ctl.state.today!.today, ...ctl.state.today!.undated].map((t) => t.id);
    expect(all.toSet().length, all.length);
    ctl.dispose();
  });

  test('refreshDerived leaves done tasks alone', () async {
    final done = _task('d', dueAt: DateTime.utc(2026, 3, 12, 9)).copyWith(status: TaskStatus.done);
    final server = TaskToday(
      today: [_task('a', dueAt: DateTime.utc(2026, 3, 12, 23))],
      doneToday: [done],
      counts: const TaskTodayCounts(today: 1, doneToday: 1),
    );
    final ctl = TaskController(_SectionRepo([_task('a', dueAt: DateTime.utc(2026, 3, 12, 23))], server),
        clock: TaskClock(() => now));
    await ctl.load();
    final before = ctl.state;
    now = DateTime.utc(2026, 3, 12, 22);
    ctl.refreshDerived();
    expect(identical(ctl.state, before), isTrue, reason: 'nothing changed, nothing emitted');
    expect(ctl.state.today!.doneToday.single.overdue, isFalse);
    now = DateTime.utc(2026, 3, 12, 23, 1);
    ctl.refreshDerived();
    expect(ctl.state.today!.doneToday.single.id, 'd');
    expect(ctl.state.today!.counts.doneToday, 1);
    expect(ctl.state.today!.overdue.map((t) => t.id), ['a']);
    ctl.dispose();
  });

  test('load reads every page of the open list', () async {
    final many = [for (var i = 0; i < 450; i++) _task('t$i')];
    final r = _PagedRepo(many);
    final ctl = TaskController(r, clock: TaskClock(() => now));
    await ctl.load();
    expect(ctl.state.open.length, 450);
    expect(r.offsets, [0, 200, 400]);
    ctl.dispose();
  });

  test('a server overdue flag that went stale is corrected on load', () async {
    repo.tasks = [_task('a', dueAt: DateTime.utc(2026, 3, 12, 9)).copyWith(overdue: false)];
    await c.load();
    expect(c.state.open.single.overdue, isTrue);
  });

  group('races', () {
    Task d(String id) => _task(id, date: '2026-03-12');
    Future<void> settle([int ms = 5]) => Future<void>.delayed(Duration(milliseconds: ms));

    test('an older overlapping load does not overwrite a newer one', () async {
      final r = _GatedRepo([d('a'), d('b'), d('c')]);
      final ctl = TaskController(r, clock: TaskClock(() => now));
      final g1 = r.listGate(), g2 = r.listGate();
      final load1 = ctl.load();
      await settle();
      r.tasks = [d('x')];
      final load2 = ctl.load();
      await settle();
      g2.complete([d('x')]);
      await load2;
      g1.complete([d('a'), d('b'), d('c')]); // the older read answers last
      await load1;
      expect(ctl.state.open.map((t) => t.id), ['x']);
      expect(ctl.state.today!.today.map((t) => t.id), ['x']);
      expect(ctl.state.loading, isFalse);
      ctl.dispose();
    });

    test('a load that began before a complete finished does not bring the task back', () async {
      final r = _GatedRepo([d('a'), d('b')]);
      final ctl = TaskController(r, clock: TaskClock(() => now));
      await ctl.load();
      final g = r.listGate();
      final slow = ctl.load(); // reads the list while a is still open on the server
      await settle();
      await ctl.complete('a');
      g.complete([d('a'), d('b')]);
      await slow;
      expect(ctl.state.open.map((t) => t.id), ['b']);
      expect(ctl.state.today!.today.map((t) => t.id), ['b']);
      ctl.dispose();
    });

    test('undo waits for the complete that is still in flight', () async {
      final r = _FakeRepo([d('a'), d('b')]);
      final ctl = TaskController(r, clock: TaskClock(() => now));
      await ctl.load();
      r.gate = Completer<void>();
      final done = ctl.complete('b');
      final undone = ctl.undo();
      await settle();
      expect(r.calls, ['complete b'], reason: 'reopen must not run before complete has finished');
      r.gate!.complete();
      await Future.wait([done, undone]);
      expect(r.calls, ['complete b', 'reopen b']);
      expect(ctl.state.open.map((t) => t.id), ['a', 'b']);
      ctl.dispose();
    });

    test('undo does nothing when the complete it waited for failed', () async {
      final r = _FakeRepo([d('a'), d('b')]);
      final ctl = TaskController(r, clock: TaskClock(() => now));
      await ctl.load();
      r.gate = Completer<void>();
      r.completeError = StateError('offline');
      final done = ctl.complete('b');
      final undone = ctl.undo();
      r.gate!.complete();
      await Future.wait([done, undone]);
      expect(r.calls, ['complete b']);
      expect(ctl.state.open.map((t) => t.id), ['a', 'b']);
      ctl.dispose();
    });

    test('a double complete shares one request and keeps the task out until it ends', () async {
      final r = _FakeRepo([d('a'), d('b')]);
      final ctl = TaskController(r, clock: TaskClock(() => now));
      await ctl.load();
      r.gate = Completer<void>();
      final f1 = ctl.complete('b');
      final f2 = ctl.complete('b');
      r.push([d('a'), d('b')]); // a stale emission while the call runs
      await settle();
      expect(ctl.state.open.map((t) => t.id), ['a']);
      expect(r.calls, ['complete b']);
      r.gate!.complete();
      await Future.wait([f1, f2]);
      expect(ctl.state.open.map((t) => t.id), ['a']);
      expect(r.calls, ['complete b']);
      ctl.dispose();
    });
  });

  group('reload after a task vanished from the stream', () {
    Task d(String id) => _task(id, date: '2026-03-12');

    test('counts are refreshed by one debounced load', () async {
      final r = _FakeRepo([d('a'), d('b'), d('c')]);
      final ctl = TaskController(r, clock: TaskClock(() => now), reloadDelay: const Duration(milliseconds: 40));
      await ctl.load();
      expect(r.todayCalls, 1);
      r.doneCount = 1; // b was completed on another device
      r.tasks = [d('a'), d('c')];
      r.push([d('a'), d('c')]);
      await Future<void>.delayed(const Duration(milliseconds: 5));
      r.push([d('a')]); // restarts the wait: still one reload
      r.tasks = [d('a')];
      await Future<void>.delayed(const Duration(milliseconds: 15));
      expect(ctl.state.today!.counts.doneToday, 0, reason: 'not yet');
      await Future<void>.delayed(const Duration(milliseconds: 100));
      expect(r.todayCalls, 2);
      expect(ctl.state.today!.counts.doneToday, 1);
      expect(ctl.state.open.map((t) => t.id), ['a']);
      ctl.dispose();
    });

    test('a task this screen completed does not trigger a reload', () async {
      final r = _FakeRepo([d('a'), d('b')]);
      final ctl = TaskController(r, clock: TaskClock(() => now), reloadDelay: const Duration(milliseconds: 20));
      await ctl.load();
      await ctl.complete('b');
      r.push([d('a')]);
      await Future<void>.delayed(const Duration(milliseconds: 80));
      expect(r.todayCalls, 1);
      ctl.dispose();
    });

    test('dispose cancels the pending reload', () async {
      final r = _FakeRepo([d('a'), d('b')]);
      final ctl = TaskController(r, clock: TaskClock(() => now), reloadDelay: const Duration(milliseconds: 20));
      await ctl.load();
      r.push([d('a')]);
      await Future<void>.delayed(const Duration(milliseconds: 5));
      ctl.dispose();
      await Future<void>.delayed(const Duration(milliseconds: 80));
      expect(r.todayCalls, 1);
    });
  });

  test('a failed load sets the error', () async {
    final bad = TaskController(_Failing());
    await bad.load();
    expect(bad.state.error, isA<StateError>());
    expect(bad.state.loading, isFalse);
    bad.dispose();
  });
}

/// A repository whose open-list reads wait for a gate the test opens.
class _GatedRepo extends _FakeRepo {
  _GatedRepo(super.tasks);
  final List<Completer<List<Task>>> _gates = [];

  Completer<List<Task>> listGate() {
    final c = Completer<List<Task>>();
    _gates.add(c);
    return c;
  }

  @override
  Future<TaskPage> list(TaskFilters f) async {
    if (_gates.isEmpty) return super.list(f);
    final items = await _gates.removeAt(0).future;
    return TaskPage(items: items, total: items.length);
  }
}

class _SectionRepo extends _FakeRepo {
  _SectionRepo(super.tasks, this.server);
  final TaskToday server;
  @override
  Future<TaskToday> today() async => server;
}

class _PagedRepo extends _FakeRepo {
  _PagedRepo(super.tasks);
  final List<int> offsets = [];
  @override
  Future<TaskPage> list(TaskFilters f) async {
    offsets.add(f.offset ?? 0);
    final from = f.offset ?? 0;
    final to = (from + f.limit!) > tasks.length ? tasks.length : from + f.limit!;
    return TaskPage(items: tasks.sublist(from, to), total: tasks.length);
  }
}

class _Failing extends _FakeRepo {
  _Failing() : super([]);
  @override
  Future<TaskToday> today() => throw StateError('down');
}
