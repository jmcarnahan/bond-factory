import 'package:bond_notify_powersync/bond_notify_powersync.dart';
import 'package:bond_push/bond_push.dart';
import 'package:bond_sync_powersync/testing.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('shell names exist', () {
    expect(kNoticesTable, 'notices');
    expect(kPushDevicesTable, 'push_devices');
    expect(noticesTables, throwsUnimplementedError);
    expect(pushDevicesTables, throwsUnimplementedError);
    final feed = WatchNoticeFeed(FakeSyncDb(), userId: 'u');
    expect(feed.refresh, throwsUnimplementedError);
    feed.dispose();
    final devices = SyncPushDevices(FakeSyncDb(), userId: 'u');
    expect(() => devices.unregister('d'), throwsUnimplementedError);
    expect(() => devices.register(const PushToken(value: 'x'), deviceId: 'd'), throwsUnimplementedError);
  });
}
