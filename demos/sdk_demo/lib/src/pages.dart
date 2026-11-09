import 'package:flutter/widgets.dart';

import 'pages/api_page.dart';
import 'pages/auth_page.dart';
import 'pages/connections_page.dart';
import 'pages/home_page.dart';
import 'pages/sync_page.dart';
import 'pages/tasks_page.dart';
import 'pages/ui_page.dart';

/// One route of the demo. Owners replace only their own page file; the class
/// names below stay stable.
class DemoPage {
  const DemoPage({
    required this.path,
    required this.title,
    required this.id,
    required this.builder,
    required this.module,
    required this.phase,
  });

  final String path;
  final String title;

  /// Used in semantics identifiers: `sdk.<id>.<element>` and `sdk.nav.<id>`.
  final String id;
  final WidgetBuilder builder;
  final String module;
  final int phase;
}

Widget _home(BuildContext context) => const HomePage();
Widget _ui(BuildContext context) => const UiPage();
Widget _api(BuildContext context) => const ApiPage();
Widget _auth(BuildContext context) => const AuthPage();
Widget _sync(BuildContext context) => const SyncPage();
Widget _connections(BuildContext context) => const ConnectionsPage();
Widget _tasks(BuildContext context) => const TasksPage();

const demoPages = [
  DemoPage(path: '/', title: 'Home', id: 'home', builder: _home, module: 'sdk_demo', phase: 1),
  DemoPage(path: '/ui', title: 'UI', id: 'ui', builder: _ui, module: 'bond_ui', phase: 1),
  DemoPage(path: '/api', title: 'API', id: 'api', builder: _api, module: 'bond_api', phase: 1),
  DemoPage(path: '/auth', title: 'Auth', id: 'auth', builder: _auth, module: 'bond_auth', phase: 2),
  DemoPage(path: '/sync', title: 'Sync', id: 'sync', builder: _sync, module: 'bond_sync', phase: 2),
  DemoPage(
    path: '/connections',
    title: 'Connections',
    id: 'connections',
    builder: _connections,
    module: 'bond_connections',
    phase: 3,
  ),
  DemoPage(path: '/tasks', title: 'Tasks', id: 'tasks', builder: _tasks, module: 'bond_tasks', phase: 3),
];
