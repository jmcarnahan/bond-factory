import 'dart:async';

import 'package:bond_notify/bond_notify.dart';
import 'package:bond_push/bond_push.dart';
import 'package:bond_push_apple/bond_push_apple.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_notifications/bond_tasks_notifications.dart';
import 'package:flutter/foundation.dart';

import '../example_api.dart';
import 'alert_plugin_io.dart' if (dart.library.js_interop) 'alert_plugin_web.dart';
import 'todo_services.dart';

/// Turns Apple push on (needs the push capability and a real Apple key on the service); off by
/// default so the local notifications of the close, due and past stages are what a walk sees.
const bool kDemoPush = bool.fromEnvironment('SDK_DEMO_PUSH');

/// The ONE alert wiring of the demo: a [TaskAlertsCoordinator]. `main()` calls [install]; the
/// coordinator starts after a sign-in, stops on sign-out, and gets the new prefs after a settings
/// save ([updatePrefs]). On web the plugin does nothing (see alert_plugin_web.dart).
class TodoAlerts {
  const TodoAlerts._();

  static TaskAlertsCoordinator? _coordinator;
  static PushRegistrar? _registrar;

  /// The user the running coordinator belongs to.
  static String? _runningFor;

  /// Every start and stop runs in this order, one at a time, so a stop during a start waits for it
  /// and a start after a stop builds the new person's coordinator.
  static Future<void> _queue = Future<void>.value();

  static Future<void> _enqueue(Future<void> Function() job) {
    final f = _queue.then((_) => job());
    _queue = f.then((_) {}, onError: (Object _) {});
    return f;
  }

  /// The route of the last plain tap on a phone notification (the demo only records it).
  static final ValueNotifier<String?> openedRoute = ValueNotifier<String?>(null);

  /// The task a plain tap asked to open (from `/tasks/<id>`); the Today page shows it.
  static final ValueNotifier<String?> openedTask = ValueNotifier<String?>(null);

  static bool get running => _coordinator != null;

  /// The user the running coordinator belongs to; null when none.
  @visibleForTesting
  static String? get runningFor => _runningFor;

  /// Completes when every queued start and stop has run.
  @visibleForTesting
  static Future<void> get settled => _queue;

  /// Makes the local-notification plugin; tests replace it.
  @visibleForTesting
  static AlertPlugin Function() pluginFactory = createAlertPlugin;

  /// Hooks the coordinator into the session. Call once from `main()`, never from tests.
  static void install({TodoServices? services}) {
    DemoSession.signInHooks.add(() async {
      // Not awaited: the page that signed in must not wait for the first sweep of alerts.
      unawaited(start(services ?? TodoServices.shared).catchError((Object _) {}));
    });
    DemoSession.signOutHooks.add(stop);
  }

  /// Creates and starts the coordinator for the signed-in person. Starting again for the same person
  /// does nothing; for another person it first stops the earlier coordinator.
  static Future<void> start(TodoServices s, {AlertPlugin? plugin, TaskSettingsApi? settingsApi}) {
    final user = s.userId;
    return _enqueue(() async {
      if (_coordinator != null && _runningFor == user) return;
      await _stop();
      await _start(s, user, plugin, settingsApi);
    });
  }

  static Future<void> _start(TodoServices s, String user, AlertPlugin? plugin, TaskSettingsApi? settingsApi) async {
    var prefs = const TaskPrefs();
    try {
      prefs = TodoServices.prefsOf(await (settingsApi ?? s.settings).get());
    } catch (_) {
      // The defaults stand until the person saves settings.
    }
    final usePush = kDemoPush && !kIsWeb && defaultTargetPlatform == TargetPlatform.iOS;
    final registrar = usePush
        ? PushRegistrar(
            PluginPushTokenSource(environment: kReleaseMode ? 'production' : 'sandbox'),
            PushDevicesApi(s.client),
            deviceId: 'sdk-demo-ios',
          )
        : null;
    final coordinator = TaskAlertsCoordinator(
      repository: s.repo,
      feed: PollingNoticeFeed(s.notices, clock: s.now),
      plugin: plugin ?? pluginFactory(),
      prefs: prefs,
      userId: user,
      push: registrar,
      pushTaps: usePush ? PluginPushTaps() : null,
      handledElsewhere: usePush ? const {'close', 'due', 'past'} : const {},
      clock: s.taskClock,
      onOpen: open,
    );
    // Registered before start() so a failing start is still cleaned up by the next stop.
    _coordinator = coordinator;
    _registrar = registrar;
    _runningFor = user;
    await coordinator.start();
  }

  /// A plain tap on a notification: records the route and the task. The app listens to [openedRoute]
  /// and goes to the Today page, where [openedTask] is shown.
  static void open(String route) {
    final parts = route.split('/').where((p) => p.isNotEmpty).toList();
    openedTask.value = parts.length >= 2 && parts.first == 'tasks' ? parts[1] : null;
    openedRoute.value = null; // so the same route twice still notifies
    openedRoute.value = route;
  }

  /// Sign-out: unregisters push, cancels the local alerts, stops listening. Waits for a start that is
  /// still running, then stops what it built.
  static Future<void> stop() => _enqueue(_stop);

  static Future<void> _stop() async {
    final c = _coordinator;
    final r = _registrar;
    _coordinator = null;
    _registrar = null;
    _runningFor = null;
    if (c == null) return;
    try {
      await c.signOut();
    } finally {
      c.dispose();
      r?.dispose();
    }
  }

  /// The person saved the work day: the alerts are planned again.
  static void updatePrefs(TaskSettings settings) => _coordinator?.updatePrefs(TodoServices.prefsOf(settings));

  /// The permission prompt, at a moment the person chooses (never at launch).
  static Future<bool> requestPermission() async => await _coordinator?.alerts.requestPermission() ?? false;
}
