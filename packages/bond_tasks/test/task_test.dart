import 'dart:convert';
import 'dart:io';

import 'package:bond_json/bond_json.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:test/test.dart';

Map<String, Object?> _fixture([String name = 'task.json']) =>
    jsonDecode(File('../../fixtures/tasks/$name').readAsStringSync()) as Map<String, Object?>;

/// The fixture writes timestamps without milliseconds; `jiso` writes them with.
/// Compare instants, not spellings.
Object? _canon(Object? v, [String key = '']) {
  if (v is Map) return {for (final e in v.entries) e.key: _canon(e.value, e.key as String)};
  if (v is List) return [for (final e in v) _canon(e, key)];
  if (v is String && (key.endsWith('_at'))) return jiso(DateTime.parse(v));
  return v;
}

void main() {
  group('Task JSON', () {
    test('fixture reads into typed fields', () {
      final t = Task.fromJson(_fixture());
      expect(t.id, 'task-0001');
      expect(t.dueDate, '2026-03-12');
      expect(t.dueTime, '09:30');
      expect(t.status, TaskStatus.open);
      expect(t.assigneeName, 'Viewer User');
      expect(t.remindMinutesBefore, 15);
      expect(t.mirrorStatus, MirrorStatus.mirrored);
      expect(t.externalProvider, 'google');
      expect(t.externalEventId, 'evt-0001');
      expect(t.overdue, isFalse);
    });

    test('checklist and links read', () {
      final t = Task.fromJson(_fixture());
      expect(t.checklist, hasLength(2));
      expect(t.checklist[0].done, isTrue);
      expect(t.checklist[1].done, isFalse);
      expect(t.checklistDone, 1);
      expect(t.links.single.kind, 'contact');
      expect(t.links.single.label, 'Sample Customer');
    });

    test('round trip writes exactly the TaskItem keys and values', () {
      final src = _fixture();
      final out = Task.fromJson(src).toJson();
      expect(out.keys.toSet(), src.keys.toSet());
      expect(_canon(out), _canon(src));
    });

    test('the cancelled fixture round trips with its nulls and empty lists', () {
      final src = _fixture('task_cancelled.json');
      final t = Task.fromJson(src);
      expect(t.status, TaskStatus.cancelled);
      expect(t.mirrorStatus, MirrorStatus.skipped);
      expect(t.dueDate, isNull);
      expect(t.dueTime, isNull);
      expect(t.checklist, isEmpty);
      expect(t.externalEventId, isNull);
      expect(t.remindMinutesBefore, kRemindNone);
      final out = t.toJson();
      expect(out.keys.toSet(), src.keys.toSet());
      expect(_canon(out), _canon(src));
    });

    test('re-encoded JSON text decodes to the same map', () {
      final out = Task.fromJson(_fixture()).toJson();
      final again = Task.fromJson(jsonDecode(jsonEncode(out)) as Map<String, Object?>).toJson();
      expect(jsonEncode(again), jsonEncode(out));
    });

    test('missing keys take safe defaults', () {
      final t = Task.fromJson({'id': 'x', 'title': 'T'});
      expect(t.status, TaskStatus.open);
      expect(t.remindMinutesBefore, kRemindNone);
      expect(t.mirrorEnabled, isTrue);
      expect(t.checklist, isEmpty);
      expect(t.dueDate, isNull);
    });

    test('unknown status and mirror status do not throw', () {
      final t = Task.fromJson({'id': 'x', 'title': 'T', 'status': 'archived', 'mirror_status': 'later'});
      expect(t.status, TaskStatus.open);
      expect(t.mirrorStatus, MirrorStatus.pending);
    });

    test('a wrong typed field throws JsonShapeError', () {
      expect(() => Task.fromJson({'id': 'x', 'title': 5}), throwsA(isA<JsonShapeError>()));
    });

    test('reminder constants', () {
      expect(kRemindNone, -2);
      expect(kRemindMorningOf, -1);
    });

    test('done status and completed_at survive', () {
      final t = Task.fromJson({'id': 'x', 'title': 'T', 'status': 'done', 'completed_at': '2026-03-12T10:00:00Z'});
      expect(t.isDone, isTrue);
      expect(t.toJson()['status'], 'done');
      expect(t.completedAt, DateTime.utc(2026, 3, 12, 10));
    });
  });

  group('TaskLabels', () {
    test('remindText covers the encoded values', () {
      const l = TaskLabels();
      expect(l.remindText(kRemindNone), 'No reminder');
      expect(l.remindText(kRemindMorningOf), 'Morning of');
      expect(l.remindText(1), '1 minute before');
      expect(l.remindText(60), '1 hour before');
      expect(l.remindText(45), '45 minutes before');
    });
  });
}
