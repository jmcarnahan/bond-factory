/// [AlertPlugin] over flutter_local_notifications (iOS only).
library;

import 'alert_plugin.dart';

class FlutterLocalAlertPlugin implements AlertPlugin {
  FlutterLocalAlertPlugin();

  @override
  Future<void> init({required void Function(AlertTap) onTap}) => throw UnimplementedError('FlutterLocalAlertPlugin.init is not implemented yet');

  @override
  Future<bool> requestPermission() => throw UnimplementedError('FlutterLocalAlertPlugin.requestPermission is not implemented yet');

  @override
  Future<void> schedule(AlertRequest r) => throw UnimplementedError('FlutterLocalAlertPlugin.schedule is not implemented yet');

  @override
  Future<void> show(AlertRequest r) => throw UnimplementedError('FlutterLocalAlertPlugin.show is not implemented yet');

  @override
  Future<void> cancel(int id) => throw UnimplementedError('FlutterLocalAlertPlugin.cancel is not implemented yet');

  @override
  Future<List<PendingAlert>> pending() => throw UnimplementedError('FlutterLocalAlertPlugin.pending is not implemented yet');

  @override
  Future<AlertTap?> launchTap() => throw UnimplementedError('FlutterLocalAlertPlugin.launchTap is not implemented yet');
}
