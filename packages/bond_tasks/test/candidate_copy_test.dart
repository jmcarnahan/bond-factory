import 'package:bond_tasks/bond_tasks.dart';
import 'package:test/test.dart';

void main() {
  const link = LinkCandidate(text: 'Sam', candidates: [LinkOption(id: 'c1', label: 'Sam Lee')]);
  const task = TaskCandidate(
    title: 'Call Sam',
    links: [link],
    confidence: 0.6,
    flags: ['low_confidence'],
    degraded: true,
    dueDate: '2026-03-12',
    dueTime: '09:30',
    dueDefaulted: true,
    priority: TaskPriority.high,
  );

  group('TaskCandidate.copyWith', () {
    test('no arguments keeps every field', () {
      final c = task.copyWith();
      expect((c.title, c.dueDate, c.dueTime, c.dueDefaulted, c.priority), ('Call Sam', '2026-03-12', '09:30', true, TaskPriority.high));
      expect(c.links.single, same(link));
      expect((c.confidence, c.degraded), (0.6, true));
      expect(c.flags, ['low_confidence']);
    });

    test('changes only what is given', () {
      final c = task.copyWith(title: 'Call Sam Lee', dueDate: '2026-03-13', dueDefaulted: false, priority: TaskPriority.low);
      expect((c.title, c.dueDate, c.dueTime, c.dueDefaulted, c.priority), ('Call Sam Lee', '2026-03-13', '09:30', false, TaskPriority.low));
      expect(c.confidence, 0.6);
    });

    test('clear flags set null and win over a value', () {
      final c = task.copyWith(clearDueTime: true, clearPriority: true, dueTime: '10:00');
      expect(c.dueTime, isNull);
      expect(c.priority, isNull);
      expect(c.dueDate, '2026-03-12');
      expect(task.copyWith(clearDueDate: true).dueDate, isNull);
    });

    test('an edited copy builds the draft', () {
      final d = task.copyWith(dueTime: '11:15', clearPriority: true).toDraft();
      expect((d.dueDate, d.dueTime, d.priority), ('2026-03-12', '11:15', null));
    });

    test('links can be replaced', () {
      expect(task.copyWith(links: const []).links, isEmpty);
    });
  });

  group('EventCandidate.copyWith', () {
    const event = EventCandidate(
      title: 'Walkthrough',
      links: [link],
      confidence: 0.9,
      startDate: '2026-03-12',
      startTime: '14:00',
      endDate: '2026-03-12',
      endTime: '15:00',
    );

    test('no arguments keeps every field', () {
      final e = event.copyWith();
      expect((e.title, e.startDate, e.startTime, e.allDay, e.endDate, e.endTime), ('Walkthrough', '2026-03-12', '14:00', false, '2026-03-12', '15:00'));
      expect(e.links.single, same(link));
      expect(e.confidence, 0.9);
    });

    test('changes and clears', () {
      final e = event.copyWith(allDay: true, clearStartTime: true, clearEndTime: true, startDate: '2026-03-14');
      expect((e.allDay, e.startTime, e.endTime, e.startDate, e.endDate), (true, null, null, '2026-03-14', '2026-03-12'));
      expect(event.copyWith(clearEndDate: true).endDate, isNull);
      expect(event.copyWith(clearStartDate: true).startDate, isNull);
      expect(event.copyWith(title: 'Site visit').title, 'Site visit');
    });
  });
}
