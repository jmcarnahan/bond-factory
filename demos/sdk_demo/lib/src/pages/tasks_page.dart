import 'package:flutter/widgets.dart';

import 'page_scaffold.dart';

class TasksPage extends StatelessWidget {
  const TasksPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const PlaceholderPage(id: 'tasks', title: 'Tasks', module: 'bond_tasks', phase: 3);
  }
}
