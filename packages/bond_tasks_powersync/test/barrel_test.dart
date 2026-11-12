import 'package:bond_sync_powersync/testing.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('public names exist and nothing is left unimplemented', () async {
    expect(kTasksTable, 'tasks');
    expect(tasksTables(), hasLength(1));
    final repo = PowerSyncTaskRepository(FakeSyncDb(), userId: 'u');
    expect(repo.userId, 'u');
    await repo.refresh();
    repo.dispose();
    expect(taskFromRow, isA<Function>());
  });
}
