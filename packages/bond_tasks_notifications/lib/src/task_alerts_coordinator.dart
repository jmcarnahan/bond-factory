/// The one object an app creates for task alerts.
library;

import 'package:bond_notify/bond_notify.dart';
import 'package:bond_push/bond_push.dart';
import 'package:bond_tasks/bond_tasks.dart';

import 'alert_plugin.dart';

class TaskAlertsCoordinator {
  TaskAlertsCoordinator({
    required this.repository,
    required this.feed,
    required this.plugin,
    required this.prefs,
    required this.userId,
    this.push,
    this.pushTaps,
    this.onOpen,
  });

  final TaskRepository repository;
  final NoticeFeed feed;
  final AlertPlugin plugin;
  final TaskPrefs prefs;
  final String userId;
  final PushRegistrar? push;
  final PushTaps? pushTaps;

  /// Called with the route of a plain tap.
  final void Function(String route)? onOpen;

  Future<void> start() => throw UnimplementedError('TaskAlertsCoordinator.start is not implemented yet');

  void dispose() {}
}
