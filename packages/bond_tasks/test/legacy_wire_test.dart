// The SDK's task types against a legacy host's wire (fixtures/legacy_host/).
import 'dart:convert';
import 'dart:io';

import 'package:bond_tasks/bond_tasks.dart';
import 'package:test/test.dart';

Map<String, Object?> _map(String name) =>
    jsonDecode(File('../../fixtures/legacy_host/$name').readAsStringSync()) as Map<String, Object?>;

Object? _wire(Map<String, Object?> body) => jsonDecode(jsonEncode(body));

const _legacyOnly = ['sync_to_calendar', 'calendar_event_id', 'client_ref', 'case_ref', 'client_name', 'case_label'];

TaskDraft _draft() => TaskDraft(
      id: 'task-draft-1',
      title: 'Send the signed form',
      notes: 'Use the blue folder',
      dueDate: '2026-11-09',
      dueTime: '09:30',
      assignedUserId: 'u-editor',
      checklist: [
        const ChecklistItem(id: 'ci-1', text: 'Print'),
        ChecklistItem(id: 'ci-2', text: 'Sign', doneAt: DateTime.utc(2026, 11, 8, 9)),
      ],
      remindMinutesBefore: 30,
      mirrorEnabled: true,
      links: const [TaskLink(kind: 'contact', id: 'c-1', label: 'Pat Example')],
      source: 'manual',
      priority: TaskPriority.high,
      dueAt: DateTime.utc(2026, 11, 9, 17, 30),
      timeZone: 'America/Los_Angeles',
      extras: const {'client_ref': 'cl-1', 'case_ref': 'ca-1'},
    );

void main() {
  group('legacy host responses', () {
    test('task_item.json parses with every SDK field', () {
      final t = Task.fromJson(_map('task_item.json'));
      expect(t.id, 'task-draft-1');
      expect(t.title, 'Send the signed form');
      expect(t.notes, 'Use the blue folder');
      expect((t.dueDate, t.dueTime), ('2026-11-09', '09:30'));
      expect(t.priority, TaskPriority.high);
      expect(t.status, TaskStatus.open);
      expect((t.ownerUserId, t.ownerName), ('u-owner', 'Olive Owner'));
      expect((t.assignedUserId, t.assigneeName), ('u-editor', 'Eddie Editor'));
      expect(t.checklist.map((c) => c.text), ['Print', 'Sign']);
      expect(t.checklist[0].doneAt, isNull);
      expect(t.remindMinutesBefore, 30);
      expect(t.links.single, const TaskLink(kind: 'contact', id: 'c-1', label: 'Pat Example'));
      expect(t.completedAt, isNull);
      expect(t.mirrorEnabled, isTrue);
      expect(t.mirrorStatus, MirrorStatus.pending);
      expect((t.externalProvider, t.externalEventId), (null, null));
      expect(t.source, 'manual');
      expect(t.overdue, isFalse);
    });

    test('naive timestamps are read as UTC instants', () {
      final t = Task.fromJson(_map('task_item.json'));
      expect(t.dueAt, DateTime.utc(2026, 11, 9, 17, 30));
      expect(t.dueAt!.isUtc, isTrue);
      expect(t.createdAt, DateTime.utc(2026, 11, 8, 10));
      expect(t.updatedAt, DateTime.utc(2026, 11, 8, 10));
      expect(t.createdAt!.millisecondsSinceEpoch, DateTime.utc(2026, 11, 8, 10).millisecondsSinceEpoch);
      expect(t.checklist[1].doneAt, DateTime.utc(2026, 11, 8, 9));
    });

    test('legacy keys land in extras and agree with the SDK fields', () {
      final src = _map('task_item.json');
      final t = Task.fromJson(src);
      expect(t.extras.keys.toSet(), _legacyOnly.toSet());
      for (final k in _legacyOnly) {
        expect(t.extras[k], src[k], reason: k);
      }
      expect(t.extras['sync_to_calendar'], true);
      expect(t.mirrorEnabled, t.extras['sync_to_calendar']);
      expect(t.extras['client_ref'], 'cl-1');
      expect(t.extras['case_label'], 'Case One');
    });

    test('task_list.json: envelope and every item parse', () {
      final src = _map('task_list.json');
      expect(src.keys.toSet(), {'items', 'total'});
      final items = [for (final i in src['items']! as List) Task.fromJson(i as Map<String, Object?>)];
      expect(items.length, src['total']);
      expect(items.map((t) => t.id), ['task-draft-1', 'task-plain-1']);
      final plain = items[1];
      expect(plain.dueAt, isNull);
      expect(plain.priority, isNull);
      expect(plain.remindMinutesBefore, -3);
      expect(plain.mirrorStatus, MirrorStatus.skipped);
      expect(plain.extras['client_ref'], isNull);
      expect(plain.extras.containsKey('client_ref'), isTrue);
    });
  });

  group('new client requests on the legacy wire', () {
    test('TaskDraft.toJson equals draft_request.json', () {
      expect(_wire(_draft().toJson()), _map('draft_request.json'));
    });

    test('TaskPatch.toJson equals patch_request.json', () {
      final patch = const TaskPatch(
        title: 'Send the form',
        notes: Present(null),
        dueTime: Present(null),
        assignedUserId: Present(null),
        links: [],
        mirrorEnabled: false,
        priority: Present(null),
        dueAt: Present(null),
        extras: {'case_ref': 'ca-2'},
      );
      final body = _wire(patch.toJson()) as Map;
      expect(body, _map('patch_request.json'));
      for (final k in ['due_date', 'checklist', 'remind_minutes_before', 'time_zone', 'client_ref', 'id']) {
        expect(body.containsKey(k), isFalse, reason: 'omitted field $k');
      }
    });

    test('round trip from a recorded task keeps the app refs', () {
      final t = Task.fromJson(_map('task_item.json'));
      final draft = TaskDraft(
        title: t.title,
        notes: t.notes,
        dueDate: t.dueDate,
        dueTime: t.dueTime,
        extras: t.extras,
      );
      final patch = _wire(TaskPatch.fromDraft(draft).toJson()) as Map;
      expect(patch['client_ref'], 'cl-1');
      expect(patch['case_ref'], 'ca-1');
      // The package echoes every non-wire extra, response-only ones included.
      expect(patch['client_name'], 'Acme Test Co');
      expect(patch['case_label'], 'Case One');
      expect(patch['sync_to_calendar'], true);
      expect(patch['calendar_event_id'], isNull);
      // Known TaskItem keys never come back through extras.
      for (final k in ['owner_name', 'assignee_name', 'mirror_status', 'created_at', 'overdue', 'status']) {
        expect(patch.containsKey(k), isFalse, reason: k);
      }
    });
  });
}
