import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

final DateTime _now = DateTime(2026, 3, 12, 12);
final DateTime _day = DateTime(2026, 3, 12);

Task _timed(String id, String title, int h, int m, {TaskStatus s = TaskStatus.open}) => Task(
      id: id,
      title: title,
      dueDate: '2026-03-12',
      dueTime: '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}',
      dueAt: DateTime(2026, 3, 12, h, m).toUtc(),
      status: s,
    );

void main() {
  final tasks = [
    _timed('b', 'Afternoon call', 15, 30),
    const Task(id: 'a', title: 'All day thing', dueDate: '2026-03-12'),
    _timed('c', 'Morning call', 9, 5),
    const Task(id: 'z', title: 'Another day', dueDate: '2026-03-13'),
    _timed('k', 'Cancelled one', 10, 0, s: TaskStatus.cancelled),
  ];

  for (final phone in [false, true]) {
    testWidgets('only that day, date-only first then by time, with local times (phone=$phone)', (t) async {
      final sem = t.ensureSemantics();
      final tapped = <String>[];
      await pumpAt(
        t,
        BondDueLane(tasks: tasks, day: _day, now: _now, onTap: (k) => tapped.add(k.id), onComplete: (_) {}, semanticsPrefix: 'l'),
        phone: phone,
      );
      expect(find.text('Another day'), findsNothing);
      expect(find.text('Cancelled one'), findsNothing);
      final order = ['All day thing', 'Morning call', 'Afternoon call'];
      final ys = [for (final s in order) t.getTopLeft(find.text(s)).dy];
      expect(ys, [...ys]..sort());
      expect(find.text('Any time'), findsOneWidget);
      expect(find.text('9:05 AM'), findsOneWidget);
      expect(find.text('3:30 PM'), findsOneWidget);
      expect(find.bySemanticsIdentifier('l.row-c'), findsOneWidget);
      await t.tap(find.text('Morning call'));
      expect(tapped, ['c']);
      await expectNoOverlays(t);
      expect(t.takeException(), isNull);
      sem.dispose();
    });
  }

  testWidgets('a long "Any time" label stays on one line at 390 with no overflow', (t) async {
    const long = 'Anytime of the day!!'; // 20 characters
    await pumpAt(
      t,
      BondDueLane(
        tasks: const [Task(id: 'a', title: 'All day thing', dueDate: '2026-03-12')],
        day: _day,
        now: _now,
        labels: const TaskLabels(anytime: long),
      ),
      phone: true,
    );
    expect(t.takeException(), isNull);
    expect(t.getSize(find.text(long)).height, lessThan(24), reason: 'one line, not wrapped into the 72 px lane');
    await expectNoOverlays(t);
  });

  testWidgets('a task past its instant is marked overdue; a later one is not', (t) async {
    await pumpAt(t, BondDueLane(tasks: tasks, day: _day, now: _now));
    // 9:05 and the all-day task (end of day) : only 9:05 has passed at noon.
    expect(find.text('Overdue'), findsOneWidget);
  });

  testWidgets('a task of another day shows nothing; an empty day shows the line', (t) async {
    await pumpAt(t, BondDueLane(tasks: tasks, day: DateTime(2026, 4, 1), now: _now));
    expect(find.text('Nothing due this day.'), findsOneWidget);
  });

  testWidgets('a done task is struck and its button reopens', (t) async {
    final done = <String>[];
    await pumpAt(
      t,
      BondDueLane(tasks: [_timed('d', 'Did it', 8, 0, s: TaskStatus.done)], day: _day, now: _now, onComplete: (k) => done.add(k.id)),
    );
    expect(find.text('Overdue'), findsNothing, reason: 'done is never overdue');
    await t.tap(find.bySemanticsLabel('Reopen'));
    expect(done, ['d']);
  });
}
