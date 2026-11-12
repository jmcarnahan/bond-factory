/// Schedules the local notices of the open tasks.
library;

import 'package:bond_notify/bond_notify.dart';
import 'package:bond_tasks/bond_tasks.dart';

import 'alert_plugin.dart';

class LocalTaskAlerts {
  LocalTaskAlerts(
    this.repository,
    this.plugin, {
    this.prefs = const TaskPrefs(),
    required this.userId,
    this.handledElsewhere = const {},
    this.budget = 60,
    this.perTask = 3,
    this.stages = stageTimes,
  });

  /// The schedule of one task; defaults to bond_tasks' `stageTimes`. Tests inject their own.
  final List<StageTime> Function(Task, TaskPrefs, DateTime nowUtc) stages;

  final TaskRepository repository;
  final AlertPlugin plugin;
  final TaskPrefs prefs;
  final String userId;

  /// Notice ids the push channel already delivers; never scheduled locally.
  final Set<String> handledElsewhere;

  /// At most this many pending alerts in total (iOS allows 64).
  final int budget;

  /// At most this many pending alerts per task, nearest first.
  final int perTask;

  Stream<AlertTap> get taps => throw UnimplementedError('LocalTaskAlerts.taps is not implemented yet');

  Future<void> start() => throw UnimplementedError('LocalTaskAlerts.start is not implemented yet');

  Future<void> sync() => throw UnimplementedError('LocalTaskAlerts.sync is not implemented yet');

  /// A synced notice arrived: post it now and cancel its scheduled copy.
  Future<void> onNoticeArrived(Notice notice) => throw UnimplementedError('LocalTaskAlerts.onNoticeArrived is not implemented yet');

  Future<bool> requestPermission() => throw UnimplementedError('LocalTaskAlerts.requestPermission is not implemented yet');
}
