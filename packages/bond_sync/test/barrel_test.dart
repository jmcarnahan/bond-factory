import 'package:bond_api/bond_api.dart' as api;
import 'package:bond_sync/bond_sync.dart';
import 'package:test/test.dart';

void main() {
  test('the barrel exports the contract names', () {
    // Types and constants named by the sync contract.
    const SyncUploadOp(seq: 0, op: 'put', table: 't', id: 'i');
    expect(kVerdictText, isNotEmpty);
    expect(SyncFailure.values, hasLength(5));
    expect(kChunkSize, 100);
    expect(kTransientMaxCount, 8);
    const FailureMapper mapper = mapSyncFailure;
    expect(mapper(StateError('x')), SyncFailure.transientCounted);
  });

  test('SessionRefresh is bond_api\'s, re-exported', () {
    expect(identical(SessionRefresh.renewed, api.SessionRefresh.renewed), isTrue);
  });
}
