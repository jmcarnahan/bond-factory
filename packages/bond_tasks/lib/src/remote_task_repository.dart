/// [TaskRepository] over [TasksApi]: the path with no sync store.
library;

import 'dart:async';

import 'task.dart';
import 'task_clock.dart';
import 'task_draft.dart';
import 'task_due.dart';
import 'task_filters.dart';
import 'task_repository.dart';
import 'task_today.dart';
import 'tasks_api.dart';

class RemoteTaskRepository implements TaskRepository {
  RemoteTaskRepository(this.api, {this.clock = const TaskClock(), this.timeZone});

  final TasksApi api;
  final TaskClock clock;

  /// The device's IANA zone name, read for every call.
  final String? Function()? timeZone;

  static const int _pageSize = 200;
  late final StreamController<List<Task>> _open = StreamController<List<Task>>.broadcast(onListen: _firstListen);
  bool _disposed = false;
  bool _started = false;

  /// Counts the re-reads; only the newest one may emit, so a slow older read cannot bring back a task
  /// a later write removed.
  int _generation = 0;

  /// The first listener gets the open list without having to call [refresh] (guarded: once only).
  void _firstListen() {
    if (_started || _disposed) return;
    _started = true;
    unawaited(_notify());
  }

  String get _today {
    final d = clock.nowLocal();
    return '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
  }

  String? get _zone => timeZone?.call();

  /// Emits the open tasks after [refresh] and after every write made through this repository; a failed
  /// re-read arrives as a stream error. No timer runs inside: the caller decides when to refresh.
  @override
  Stream<List<Task>> watchOpen() => _open.stream;

  @override
  Future<TaskToday> today() => api.today(today: _today, timeZone: _zone);

  @override
  Future<TaskPage> list(TaskFilters f) => api.list(_withDevice(f));

  @override
  Future<TaskSummary> summary() => api.summary(today: _today, timeZone: _zone);

  @override
  Future<Task> create(TaskDraft d) async {
    final t = await api.create(_draft(d), today: _today, timeZone: d.timeZone ?? _zone);
    await _notify();
    return t;
  }

  @override
  Future<Task> update(String id, TaskPatch p) async {
    final t = await api.update(id, _patch(p), today: _today, timeZone: p.timeZone ?? _zone);
    await _notify();
    return t;
  }

  @override
  Future<Task> complete(String id) async {
    final t = await api.complete(id, today: _today, timeZone: _zone);
    await _notify();
    return t;
  }

  @override
  Future<Task> reopen(String id) async {
    final t = await api.reopen(id, today: _today, timeZone: _zone);
    await _notify();
    return t;
  }

  @override
  Future<Task> cancel(String id) async {
    final t = await api.cancel(id, today: _today, timeZone: _zone);
    await _notify();
    return t;
  }

  @override
  Future<void> delete(String id) async {
    await api.delete(id);
    await _notify();
  }

  @override
  Future<void> refresh() => _notify(rethrowErrors: true);

  @override
  void dispose() {
    _disposed = true;
    _open.close();
  }

  TaskFilters _withDevice(TaskFilters f) => TaskFilters(
        scope: f.scope,
        status: f.status,
        today: f.today ?? _today,
        onOrBefore: f.onOrBefore,
        dueFrom: f.dueFrom,
        dueTo: f.dueTo,
        includeUndated: f.includeUndated,
        noDate: f.noDate,
        ownerUserId: f.ownerUserId,
        assignedUserId: f.assignedUserId,
        assignedToMe: f.assignedToMe,
        linkKind: f.linkKind,
        linkId: f.linkId,
        limit: f.limit,
        offset: f.offset,
        timeZone: f.timeZone ?? _zone,
      );

  /// Timed task: the device's due instant. Date-only task: none (the server decides).
  TaskDraft _draft(TaskDraft d) => TaskDraft(
        title: d.title,
        id: d.id,
        notes: d.notes,
        dueDate: d.dueDate,
        dueTime: d.dueTime,
        assignedUserId: d.assignedUserId,
        checklist: d.checklist,
        remindMinutesBefore: d.remindMinutesBefore,
        mirrorEnabled: d.mirrorEnabled,
        links: d.links,
        source: d.source,
        priority: d.priority,
        dueAt: deviceDueAt(d.dueDate, d.dueTime),
        timeZone: d.timeZone ?? _zone,
      );

  /// A due instant is sent only when the patch sets both a date and a time.
  TaskPatch _patch(TaskPatch p) {
    final at = deviceDueAt(p.dueDate?.value, p.dueTime?.value);
    return TaskPatch(
      title: p.title,
      notes: p.notes,
      dueDate: p.dueDate,
      dueTime: p.dueTime,
      assignedUserId: p.assignedUserId,
      checklist: p.checklist,
      remindMinutesBefore: p.remindMinutesBefore,
      mirrorEnabled: p.mirrorEnabled,
      links: p.links,
      priority: p.priority,
      dueAt: at == null ? null : Present(at),
      timeZone: p.timeZone ?? _zone,
    );
  }

  Future<List<Task>> _readOpen() async {
    final out = <Task>[];
    for (var offset = 0;; offset += _pageSize) {
      final page = await api.list(TaskFilters(
        scope: 'mine',
        status: 'open',
        today: _today,
        timeZone: _zone,
        limit: _pageSize,
        offset: offset,
      ));
      out.addAll(page.items);
      if (page.items.length < _pageSize || out.length >= page.total) return out;
    }
  }

  Future<void> _notify({bool rethrowErrors = false}) async {
    if (_disposed) return;
    final gen = ++_generation;
    try {
      final tasks = await _readOpen();
      if (!_disposed && gen == _generation) _open.add(tasks);
    } catch (e, st) {
      if (!_disposed && gen == _generation) _open.addError(e, st);
      if (rethrowErrors) rethrow;
    }
  }
}
