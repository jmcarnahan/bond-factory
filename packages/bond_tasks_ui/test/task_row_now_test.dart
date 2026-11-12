import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

final DateTime _now = DateTime(2026, 3, 12, 12);

Task _timed({bool flag = false, TaskPriority? priority}) => Task(
      id: 'a',
      title: 'Timed',
      dueDate: '2026-03-12',
      dueTime: '08:00',
      dueAt: DateTime(2026, 3, 12, 8).toUtc(),
      overdue: flag,
      priority: priority,
    );

void main() {
  testWidgets('with now the row is overdue by the one rule even when the flag is stale', (t) async {
    await pumpAt(t, BondTaskRow(task: _timed(), now: _now));
    expect(find.text('Overdue'), findsOneWidget);
  });

  testWidgets('with now a flagged task that is not past its instant is not overdue', (t) async {
    final early = DateTime(2026, 3, 12, 6);
    await pumpAt(t, BondTaskRow(task: _timed(flag: true), now: early));
    expect(find.text('Overdue'), findsNothing);
  });

  testWidgets('without now the flag still decides', (t) async {
    await pumpAt(t, BondTaskRow(task: _timed(flag: true)));
    expect(find.text('Overdue'), findsOneWidget);
    await pumpAt(t, BondTaskRow(task: _timed()));
    expect(find.text('Overdue'), findsNothing);
  });

  testWidgets('a high or low priority shows a chip, normal and none do not', (t) async {
    await pumpAt(t, BondTaskRow(task: _timed(priority: TaskPriority.high)));
    expect(find.text('High'), findsOneWidget);
    await pumpAt(t, BondTaskRow(task: _timed(priority: TaskPriority.low)));
    expect(find.text('Low'), findsOneWidget);
    await pumpAt(t, BondTaskRow(task: _timed(priority: TaskPriority.normal)));
    expect(find.text('Normal'), findsNothing);
    await pumpAt(t, BondTaskRow(task: _timed()));
    expect(find.text('High'), findsNothing);
  });

  testWidgets('the row shows the due instant in the device zone', (t) async {
    await pumpAt(t, BondTaskRow(task: _timed()));
    expect(find.textContaining('8:00 AM'), findsOneWidget);
  });

  testWidgets('the list sections follow now', (t) async {
    await expectCleanAtBothWidths(
      t,
      () => BondTaskList(tasks: [_timed()], today: kToday, now: _now),
    );
    expect(find.text('Overdue (1)'), findsOneWidget);
    await pumpAt(t, BondTaskList(tasks: [_timed()], today: kToday, now: DateTime(2026, 3, 12, 6)));
    expect(find.text('Today (1)'), findsOneWidget);
  });
}
