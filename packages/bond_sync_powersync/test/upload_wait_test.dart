import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_sync_powersync/testing.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const entry = SyncCrudEntry(clientId: 1, op: 'put', table: 't', id: 'a');

  test('true at once when the queue is empty', () async {
    expect(await waitForUploadDrain(FakeSyncDb()), isTrue);
  });

  test('true once the queue empties while polling', () async {
    final db = FakeSyncDb();
    db.crud.add(CrudRig().tx([entry]));
    Future<void>.delayed(const Duration(milliseconds: 60), db.crud.clear);
    expect(await waitForUploadDrain(db, poll: const Duration(milliseconds: 10)), isTrue);
  });

  test('false when the queue is still full at the timeout', () async {
    final db = FakeSyncDb();
    db.crud.add(CrudRig().tx([entry]));
    expect(
      await waitForUploadDrain(db, timeout: const Duration(milliseconds: 50), poll: const Duration(milliseconds: 10)),
      isFalse,
    );
  });
}
