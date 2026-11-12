import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

/// Remembers the id it was first built for; a recycled element keeps showing the old one.
class _Probe extends StatefulWidget {
  const _Probe(this.id);
  final String id;

  @override
  State<_Probe> createState() => _ProbeState();
}

class _ProbeState extends State<_Probe> {
  late final String first = widget.id;

  @override
  Widget build(BuildContext context) => Text('probe-$first');
}

const _a = Task(id: 'a', title: 'First', dueDate: '2026-03-12');
const _b = Task(id: 'b', title: 'Second', dueDate: '2026-03-12');
final DateTime _now = DateTime(2026, 3, 12, 12);

void main() {
  testWidgets('removing the first row of a list does not hand its state to the next row', (t) async {
    Widget list(List<Task> tasks) => BondTaskList(
          tasks: tasks,
          today: kToday,
          now: _now,
          rowExtra: (c, k) => _Probe(k.id),
        );
    await pumpAt(t, list([_a, _b]));
    expect(find.text('probe-b'), findsOneWidget);
    await pumpAt(t, list([_b]));
    expect(find.text('probe-b'), findsOneWidget, reason: 'the second task keeps its own state');
    expect(find.text('probe-a'), findsNothing);
  });

  testWidgets('every row of the today list and the due lane carries the task id as its key', (t) async {
    await pumpAt(t, BondTodayList(today: const TaskToday(today: [_a, _b]), now: _now));
    expect(find.byKey(const ValueKey('a')), findsOneWidget);
    expect(find.byKey(const ValueKey('b')), findsOneWidget);
    await pumpAt(t, BondDueLane(tasks: const [_a, _b], day: DateTime(2026, 3, 12), now: _now));
    expect(find.byKey(const ValueKey('a')), findsOneWidget);
    expect(find.byKey(const ValueKey('b')), findsOneWidget);
  });
}
