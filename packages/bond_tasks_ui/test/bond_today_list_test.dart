import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

final DateTime _now = DateTime(2026, 3, 12, 12);

Task _t(String id, String title, {String? date, String? time, DateTime? at, TaskStatus s = TaskStatus.open}) =>
    Task(id: id, title: title, dueDate: date, dueTime: time, dueAt: at, status: s);

TaskToday _today() => TaskToday(
      overdue: [_t('o', 'Late one', date: '2026-03-12', time: '09:00', at: DateTime(2026, 3, 12, 9).toUtc())],
      today: [_t('d', 'Due later', date: '2026-03-12', time: '17:00', at: DateTime(2026, 3, 12, 17).toUtc())],
      undated: [_t('u', 'Someday')],
      doneToday: [_t('x', 'Finished', date: '2026-03-12', s: TaskStatus.done)],
      counts: const TaskTodayCounts(overdue: 1, today: 1, undated: 1, doneToday: 1),
    );

void main() {
  for (final phone in [false, true]) {
    testWidgets('four sections with counts, rows, taps (phone=$phone)', (t) async {
      final sem = t.ensureSemantics();
      final tapped = <String>[];
      final completed = <String>[];
      await pumpAt(
        t,
        BondTodayList(
          today: _today(),
          now: _now,
          onTap: (k) => tapped.add(k.id),
          onComplete: (k) => completed.add(k.id),
          semanticsPrefix: 'p',
        ),
        phone: phone,
      );
      expect(find.text('Overdue (1)'), findsOneWidget);
      expect(find.text('Today (1)'), findsOneWidget);
      expect(find.text('No date (1)'), findsOneWidget);
      expect(find.text('Done today (1)'), findsOneWidget);
      expect(find.bySemanticsIdentifier('p.row-o'), findsOneWidget);
      expect(find.bySemanticsIdentifier('p.complete-d'), findsOneWidget);
      await t.tap(find.text('Due later'));
      await t.tap(find.bySemanticsIdentifier('p.complete-u'));
      expect(tapped, ['d']);
      expect(completed, ['u']);
      await expectNoOverlays(t);
      expect(t.takeException(), isNull);
      sem.dispose();
    });
  }

  testWidgets('empty sections are left out and the server count wins when larger', (t) async {
    await pumpAt(
      t,
      BondTodayList(
        today: TaskToday(
          today: [_t('d', 'Only one', date: '2026-03-12')],
          counts: const TaskTodayCounts(today: 7),
        ),
        now: _now,
      ),
    );
    expect(find.text('Today (7)'), findsOneWidget);
    expect(find.textContaining('Overdue'), findsNothing);
    expect(find.textContaining('Done today'), findsNothing);
  });

  for (final phone in [false, true]) {
    testWidgets('a list built at 16:59 shown at 17:01 draws the 17:00 task under Overdue once (phone=$phone)', (t) async {
      final at = DateTime(2026, 3, 12, 17).toUtc();
      final built = TaskToday(
        today: [_t('d', 'Five o clock', date: '2026-03-12', time: '17:00', at: at), _t('e', 'Later', date: '2026-03-12', time: '20:00', at: DateTime(2026, 3, 12, 20).toUtc())],
        counts: const TaskTodayCounts(today: 2),
      );
      await pumpAt(t, BondTodayList(today: built, now: DateTime(2026, 3, 12, 17, 1)), phone: phone);
      expect(find.text('Overdue (1)'), findsOneWidget);
      expect(find.text('Today (1)'), findsOneWidget, reason: 'the count follows the tasks, not the stale server count');
      expect(find.text('Five o clock'), findsOneWidget, reason: 'never in two sections');
      // It sits above the Today header.
      expect(t.getTopLeft(find.text('Five o clock')).dy < t.getTopLeft(find.text('Today (1)')).dy, isTrue);
      // At 16:59 the same list keeps it in Today.
      await pumpAt(t, BondTodayList(today: built, now: DateTime(2026, 3, 12, 16, 59)), phone: phone);
      expect(find.text('Today (2)'), findsOneWidget);
      expect(find.textContaining('Overdue ('), findsNothing);
      expect(t.takeException(), isNull);
    });
  }

  testWidgets('a task listed twice shows once; a listed-overdue task not yet past moves to Today', (t) async {
    final early = _t('o', 'Not yet', date: '2026-03-12', time: '17:00', at: DateTime(2026, 3, 12, 17).toUtc());
    await pumpAt(
      t,
      BondTodayList(today: TaskToday(overdue: [early], today: [early]), now: _now),
    );
    expect(find.text('Not yet'), findsOneWidget);
    expect(find.text('Today (1)'), findsOneWidget);
    expect(find.textContaining('Overdue ('), findsNothing);
  });

  testWidgets('a date-only task dated yesterday whose dueAt is still ahead is drawn under Today', (t) async {
    // The instant (a viewer in a far zone, say) has not passed, though the date is earlier.
    final task = _t('y', 'Yesterday by date', date: '2026-03-11', at: DateTime(2026, 3, 12, 20).toUtc());
    await pumpAt(t, BondTodayList(today: TaskToday(overdue: [task]), now: _now));
    expect(find.text('Today (1)'), findsOneWidget);
    expect(find.textContaining('Overdue ('), findsNothing);
    expect(find.text('Yesterday by date'), findsOneWidget);
    // Same rule in the section helper.
    expect(sectionOf(task, '2026-03-12', now: _now), TaskSection.today);
  });

  testWidgets('nothing at all shows the empty line', (t) async {
    await pumpAt(t, BondTodayList(today: const TaskToday(), now: _now));
    expect(find.text('Nothing due. Enjoy the day.'), findsOneWidget);
    await expectNoOverlays(t);
  });

  testWidgets('a row past its instant is marked overdue from now, not from the stale flag', (t) async {
    // In the "today" section by the server, but its instant has passed by `now`.
    final late = TaskToday(today: [_t('d', 'Slipped', date: '2026-03-12', time: '08:00', at: DateTime(2026, 3, 12, 8).toUtc())]);
    await pumpAt(t, BondTodayList(today: late, now: _now));
    expect(find.text('Overdue'), findsOneWidget, reason: 'the chip on the row');
  });
}
