import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_sync_powersync/testing.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('every new public name exists', () async {
    const shape = TaskTableShape(absent: {'priority'}, rename: {'source': 'src'}, dueOrder: TaskDueOrder.dueAt);
    expect(TaskDueOrder.values, hasLength(2));
    expect(TaskWriteKind.values.map((k) => k.name), ['create', 'update', 'complete', 'reopen', 'cancel', 'delete']);
    const w = TaskWrite(kind: TaskWriteKind.create, id: 'a');
    expect((w.kind, w.id, w.before), (TaskWriteKind.create, 'a', null));
    expect(w.values, isEmpty);
    Future<Map<String, Object?>> prepare(SyncSql tx, TaskWrite w) async => w.values;
    Future<void> after(SyncSql tx, TaskWrite w) async {}
    String? mirror(SyncRow after, SyncRow? before) => null;
    final TaskPrepare p = prepare;
    final TaskAfterWrite a = after;
    final MirrorStatusOnWrite m = mirror;
    final repo = PowerSyncTaskRepository(FakeSyncDb(), userId: 'u', shape: shape, writeCompletedBy: true, mirrorStatusOnWrite: m, prepare: p, afterWrite: a);
    expect(repo.shape.absent, {'priority'});
    expect(repo.shape.rename, {'source': 'src'});
    expect(repo.shape.dueOrder, TaskDueOrder.dueAt);
    expect(repo.writeCompletedBy, isTrue);
    expect(shape.local('source'), 'src');
    expect(repo.getTask, isA<Function>());
    expect(repo.watchTask, isA<Function>());
    expect(repo.listWhere, isA<Function>());
    expect(repo.watchWhere, isA<Function>());
    expect(repo.watchList, isA<Function>());
    expect(taskFromRow, isA<Function>());
  });
}
