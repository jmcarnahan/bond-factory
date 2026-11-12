import 'dart:async';

import 'package:bond_notify/bond_notify.dart';
import 'package:bond_tasks/bond_tasks.dart';

/// A repository whose open list a test pushes by hand. Unused methods throw.
class FakeRepo implements TaskRepository {
  final controller = StreamController<List<Task>>.broadcast();
  final completed = <String>[];
  final cancelled = <String>[];
  Object? failWith;

  /// When set, the stream emits nothing until [refresh] is called, then emits this list (the REST repository).
  List<Task>? serverTasks;
  int refreshCalls = 0;
  Object? refreshFails;

  @override
  Stream<List<Task>> watchOpen() => controller.stream;

  void push(List<Task> tasks) => controller.add(tasks);

  @override
  Future<void> refresh() async {
    refreshCalls++;
    if (refreshFails != null) throw refreshFails!;
    final s = serverTasks;
    if (s != null) controller.add(s);
  }

  @override
  Future<Task> complete(String id) async {
    if (failWith != null) throw failWith!;
    completed.add(id);
    return Task(id: id, title: 't');
  }

  @override
  Future<Task> cancel(String id) async {
    if (failWith != null) throw failWith!;
    cancelled.add(id);
    return Task(id: id, title: 't');
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnimplementedError('${invocation.memberName}');
}

class FakeFeed implements NoticeFeed {
  final controller = StreamController<List<Notice>>.broadcast();
  final read = <String>[];
  Object? failRead;

  @override
  Stream<List<Notice>> watch() => controller.stream;

  void push(List<Notice> items) => controller.add(items);

  int refreshCalls = 0;

  @override
  Future<void> refresh() async => refreshCalls++;

  @override
  Future<void> markRead(String id) async {
    if (failRead != null) throw failRead!;
    read.add(id);
  }

  @override
  Future<void> dismiss(String id) async {}

  @override
  Future<void> markAllRead() async => allRead = true;

  bool allRead = false;

  @override
  int? get serverUnreadCount => null;

  @override
  void dispose() {}
}

/// Lets queued futures and stream events run.
Future<void> settle() async {
  for (var i = 0; i < 20; i++) {
    await Future<void>.delayed(Duration.zero);
  }
}
