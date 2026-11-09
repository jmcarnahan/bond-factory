import 'package:bond_tasks/bond_tasks.dart';
import 'package:test/test.dart';

void main() {
  group('TaskDraft', () {
    test('create body omits empty optionals', () {
      final j = const TaskDraft(title: ' Call back ').toJson();
      expect(j['title'], 'Call back');
      expect(j.containsKey('notes'), isFalse);
      expect(j.containsKey('due_date'), isFalse);
      expect(j['remind_minutes_before'], kRemindNone);
      expect(j['mirror_enabled'], isTrue);
      expect(j['checklist'], isEmpty);
    });

    test('create body carries every set field', () {
      final j = const TaskDraft(
        id: 'client-1',
        title: 'T',
        notes: 'n',
        dueDate: '2026-03-12',
        dueTime: '09:30',
        assignedUserId: 'u2',
        checklist: [ChecklistItem(id: 'a', text: 'one')],
        remindMinutesBefore: 60,
        mirrorEnabled: false,
        links: [TaskLink(kind: 'job', id: 'j1', label: 'Job')],
      ).toJson();
      expect(j['id'], 'client-1');
      expect(j['due_time'], '09:30');
      expect(j['assigned_user_id'], 'u2');
      expect(j['mirror_enabled'], isFalse);
      expect((j['checklist'] as List).single, {'id': 'a', 'text': 'one', 'done_at': null});
      expect((j['links'] as List).single, {'kind': 'job', 'id': 'j1', 'label': 'Job'});
    });

    test('validate: title required', () {
      expect(const TaskDraft(title: '  ').validate(), [TaskProblem.titleRequired]);
    });

    test('validate: title length limit is 255 after trimming', () {
      expect(TaskDraft(title: 'a' * 255).validate(), isEmpty);
      expect(TaskDraft(title: ' ${'a' * 255} ').validate(), isEmpty);
      expect(TaskDraft(title: 'a' * 256).validate(), [TaskProblem.titleTooLong]);
    });

    test('validate: time requires date', () {
      expect(const TaskDraft(title: 'T', dueTime: '09:00').validate(), [TaskProblem.dueTimeRequiresDate]);
      expect(const TaskDraft(title: 'T', dueDate: '2026-03-12', dueTime: '09:00').validate(), isEmpty);
    });
  });

  group('TaskPatch', () {
    test('an empty patch sends nothing', () {
      expect(const TaskPatch().toJson(), isEmpty);
    });

    test('omitted and explicit null differ on the wire', () {
      final omitted = const TaskPatch(title: 'T').toJson();
      final cleared = const TaskPatch(title: 'T', dueDate: Present(null)).toJson();
      expect(omitted.containsKey('due_date'), isFalse);
      expect(cleared.containsKey('due_date'), isTrue);
      expect(cleared['due_date'], isNull);
    });

    test('all four clearable fields can be nulled', () {
      final j = const TaskPatch(
        notes: Present(null),
        dueDate: Present(null),
        dueTime: Present(null),
        assignedUserId: Present(null),
      ).toJson();
      expect(j.keys.toSet(), {'notes', 'due_date', 'due_time', 'assigned_user_id'});
      expect(j.values.every((v) => v == null), isTrue);
    });

    test('a present value is sent', () {
      expect(const TaskPatch(notes: Present('hello')).toJson(), {'notes': 'hello'});
    });

    test('fromDraft clears what the draft leaves empty', () {
      final j = TaskPatch.fromDraft(const TaskDraft(title: 'T', dueDate: '2026-03-12')).toJson();
      expect(j['due_date'], '2026-03-12');
      expect(j.containsKey('due_time'), isTrue);
      expect(j['due_time'], isNull);
      expect(j['notes'], isNull);
      expect(j['mirror_enabled'], isTrue);
    });

    test('Present equality', () {
      expect(const Present<String>('a'), const Present<String>('a'));
      expect(const Present<String>(null), isNot(const Present<String>('a')));
    });
  });

  group('TaskFilters', () {
    test('default sends nothing', () {
      expect(const TaskFilters().toQuery(), isEmpty);
    });

    test('names follow the route contract', () {
      final q = const TaskFilters(
        scope: 'all',
        status: 'open',
        today: '2026-03-12',
        onOrBefore: '2026-03-13',
        dueFrom: '2026-03-01',
        dueTo: '2026-03-31',
        includeUndated: true,
        noDate: true,
        ownerUserId: 'u1',
        assignedUserId: 'u2',
        assignedToMe: true,
        linkKind: 'contact',
        linkId: 'c1',
        limit: 20,
        offset: 40,
      ).toQuery();
      expect(q.keys.toSet(), {
        'scope', 'status', 'today', 'on_or_before', 'due_from', 'due_to', 'include_undated', 'no_date',
        'owner_user_id', 'assigned_user_id', 'assigned_to_me', 'link_kind', 'link_id', 'limit', 'offset',
      });
      expect(q['include_undated'], 'true');
    });

    test('TaskSummary and TaskPage parse', () {
      final s = TaskSummary.fromJson({'open': 4, 'overdue': 1, 'due_today': 2, 'no_date': 1});
      expect((s.open, s.overdue, s.dueToday, s.noDate), (4, 1, 2, 1));
      final p = TaskPage.fromJson({'items': [{'id': 'a', 'title': 'A'}], 'total': 9, 'limit': 1, 'offset': 0});
      expect(p.items.single.id, 'a');
      expect(p.total, 9);
    });
  });
}
