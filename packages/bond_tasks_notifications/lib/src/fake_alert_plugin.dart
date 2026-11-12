/// An in-memory [AlertPlugin] for tests.
library;

import 'alert_plugin.dart';

class FakeAlertPlugin implements AlertPlugin {
  FakeAlertPlugin({this.permission = true});

  bool permission;
  bool initialised = false;
  AlertTap? launch;
  final List<AlertRequest> scheduled = [];
  final List<AlertRequest> shown = [];
  final List<int> cancelled = [];
  void Function(AlertTap)? _onTap;

  @override
  Future<void> init({required void Function(AlertTap) onTap}) async {
    initialised = true;
    _onTap = onTap;
  }

  @override
  Future<bool> requestPermission() async => permission;

  @override
  Future<void> schedule(AlertRequest r) async {
    scheduled.removeWhere((s) => s.id == r.id);
    scheduled.add(r);
  }

  @override
  Future<void> show(AlertRequest r) async {
    shown.add(r);
    if (!activeIds.contains(r.id)) activeIds.add(r.id);
  }

  @override
  Future<void> cancel(int id) async {
    cancelled.add(id);
    activeIds.remove(id);
    scheduled.removeWhere((s) => s.id == id);
  }

  @override
  Future<List<PendingAlert>> pending() async => [
        for (final r in scheduled)
          PendingAlert(
            id: r.id,
            payload: AlertTap(noticeId: r.noticeId, taskId: r.taskId, route: r.route).toPayload(),
          ),
      ];

  /// What [active] reports: set it to pretend notifications are on the lock screen.
  List<int> activeIds = [];

  @override
  Future<List<int>> active() async => List.of(activeIds);

  @override
  Future<AlertTap?> launchTap() async => launch;

  /// Lets a test fire a tap, as if the person tapped the notification.
  void fireTap(AlertTap tap) => _onTap?.call(tap);
}
