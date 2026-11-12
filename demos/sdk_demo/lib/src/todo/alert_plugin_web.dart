import 'package:bond_tasks_notifications/bond_tasks_notifications.dart';

/// Web: local phone notifications do not exist here, so the plugin does nothing. The browser alert
/// (`browserNoticeAlert`) is the web path and is wired on the Inbox page.
AlertPlugin createAlertPlugin() => _NoopAlertPlugin();

class _NoopAlertPlugin implements AlertPlugin {
  @override
  Future<void> init({required void Function(AlertTap) onTap}) async {}

  @override
  Future<bool> requestPermission() async => false;

  @override
  Future<void> schedule(AlertRequest r) async {}

  @override
  Future<void> show(AlertRequest r) async {}

  @override
  Future<void> cancel(int id) async {}

  @override
  Future<List<PendingAlert>> pending() async => const [];

  @override
  Future<List<int>> active() async => const [];

  @override
  Future<AlertTap?> launchTap() async => null;
}
