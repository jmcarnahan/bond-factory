import 'dart:convert';
import 'dart:io';

import 'package:bond_api/bond_api.dart';
import 'package:bond_json/bond_json.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:test/test.dart';

Object? _load(String name) => jsonDecode(File('../../fixtures/tasks/$name').readAsStringSync());
Map<String, Object?> _map(String name) => _load(name) as Map<String, Object?>;

http.Response _json(Object? body) =>
    http.Response(jsonEncode(body), 200, headers: {'content-type': 'application/json'});

Object? _canon(Object? v, [String key = '']) {
  if (v is Map) return {for (final e in v.entries) e.key: _canon(e.value, e.key as String)};
  if (v is List) return [for (final e in v) _canon(e, key)];
  if (v is String && key.endsWith('_at')) return jiso(DateTime.parse(v));
  return v;
}

void main() {
  group('task fixtures', () {
    for (final f in ['task.json', 'task_cancelled.json', 'task_timed.json', 'task_day_self.json', 'task_day_other_null_due.json', 'task_overdue.json']) {
      test('$f round trips with 26 keys', () {
        final src = _map(f);
        final out = Task.fromJson(src).toJson();
        expect(out.length, 26);
        expect(_canon(out), _canon(src));
      });
    }

    test('old shape parses with null priority and dueAt', () {
      final t = Task.fromJson(_map('task_old_shape.json'));
      expect(t.priority, isNull);
      expect(t.dueAt, isNull);
    });

    test('timed task carries priority and dueAt', () {
      final t = Task.fromJson(_map('task_timed.json'));
      expect(t.dueAt, isNotNull);
      expect(t.dueAt!.isUtc, isTrue);
    });
  });

  test('TaskPriority.fromWire', () {
    expect(TaskPriority.fromWire(3), TaskPriority.high);
    expect(TaskPriority.fromWire(9), isNull);
    expect(TaskPriority.fromWire(null), isNull);
  });

  test('draft and patch carry the new keys only when set', () {
    expect(const TaskDraft(title: 'x').toJson().containsKey('priority'), isFalse);
    final d = TaskDraft(
        title: 'x', priority: TaskPriority.high, dueAt: DateTime.utc(2026, 3, 12, 16, 30), timeZone: 'America/Los_Angeles');
    expect(d.toJson(), containsPair('priority', 3));
    expect(d.toJson(), containsPair('due_at', '2026-03-12T16:30:00.000Z'));
    expect(d.toJson(), containsPair('time_zone', 'America/Los_Angeles'));
    expect(const TaskPatch().toJson(), isEmpty);
    expect(const TaskPatch(priority: Present(null)).toJson(), {'priority': null});
  });

  test('today.json parses', () {
    final t = TaskToday.fromJson(_map('today.json'));
    expect(t.counts.overdue, t.overdue.length);
    expect(t.overdue.single.id, 'task-0006');
    expect(t.toJson()['counts'], isA<Map>());
  });

  test('settings.json parses and the patch sends only set fields', () {
    final s = TaskSettings.fromJson(_map('settings.json'));
    expect(s.timeZone, 'America/Los_Angeles');
    expect(s.startOfDay, '08:00');
    expect(s.leadMinutes, 60);
    expect(s.toJson(), _map('settings.json'));
    expect(const TaskSettingsPatch(leadMinutes: 30).toJson(), {'lead_minutes': 30});
  });

  test('parse_response.json gives two tasks and an event', () {
    final r = ParseResult.fromJson(_map('parse_response.json'));
    expect(r.items.length, 3);
    expect(r.degraded, isFalse);
    final t = r.items[1] as TaskCandidate;
    expect(t.priority, TaskPriority.high);
    expect(t.links.single.candidates.single.id, 'contact-2');
    final draft = t.toDraft(links: const [TaskLink(kind: 'contact', id: 'contact-2')]);
    expect(draft.dueTime, '12:00');
    expect(draft.links.single.id, 'contact-2');
    final e = r.items[2] as EventCandidate;
    expect(e.allDay, isTrue);
  });

  test('parse_response_degraded.json and unknown kinds', () {
    final r = ParseResult.fromJson(_map('parse_response_degraded.json'));
    expect(r.degraded, isTrue);
    expect(r.reason, 'model_unavailable');
    expect(r.items.single.degraded, isTrue);
    final odd = ParseResult.fromJson({
      'items': [
        {'kind': 'reminder', 'title': 'x'},
        {'kind': 'task', 'title': 'y'},
      ],
    });
    expect(odd.items.length, 1);
  });

  test('notice ids match the shared fixture', () {
    for (final c in (_load('notice_ids.json') as List).cast<Map<String, Object?>>()) {
      final id = noticeId(c['task_id'] as String, c['user_id'] as String, c['stage'] as String, c['seq'] as int, c['token'] as String);
      expect(id, c['notice_id']);
      expect(fnv1a31(id), c['local_id']);
    }
  });

  test('TaskClock', () {
    final c = TaskClock(() => DateTime.utc(2026, 3, 12, 9));
    expect(c.nowUtc(), DateTime.utc(2026, 3, 12, 9));
    expect(c.nowLocal().isUtc, isFalse);
  });

  group('new routes', () {
    late List<http.Request> seen;
    late TasksApi api;
    late TaskSettingsApi settings;

    void rig(Object? body) {
      seen = [];
      final client = ApiClient(
        baseUrl: Uri.parse('https://api.test/v1'),
        http: MockClient((r) async {
          seen.add(r);
          return _json(body);
        }),
      );
      api = TasksApi(client);
      settings = TaskSettingsApi(client);
    }

    test('today', () async {
      rig(_map('today.json'));
      await api.today(timeZone: 'America/Los_Angeles', today: '2026-03-12');
      expect(seen.single.method, 'GET');
      expect(seen.single.url.path, '/v1/tasks/today');
      expect(seen.single.url.queryParameters, {'time_zone': 'America/Los_Angeles', 'today': '2026-03-12'});
    });

    test('cancel', () async {
      rig(_map('task_cancelled.json'));
      final t = await api.cancel('task-0001', today: '2026-03-12');
      expect(seen.single.method, 'POST');
      expect(seen.single.url.path, '/v1/tasks/task-0001/cancel');
      expect(t.status, TaskStatus.cancelled);
    });

    test('parse', () async {
      rig(_map('parse_response.json'));
      final r = await api.parse('call Sam', today: '2026-11-11', timeZone: 'America/Los_Angeles');
      expect(seen.single.url.path, '/v1/tasks/parse');
      expect(jsonDecode(seen.single.body), {'text': 'call Sam', 'today': '2026-11-11', 'time_zone': 'America/Los_Angeles'});
      expect(r.items.length, 3);
    });

    test('searchLinks', () async {
      rig({
        'items': [
          {'kind': 'contact', 'id': 'c1', 'label': 'Sam Example'}
        ]
      });
      final l = await api.searchLinks('contact', 'sam');
      expect(seen.single.url.path, '/v1/tasks/links/search');
      expect(seen.single.url.queryParameters, {'kind': 'contact', 'q': 'sam'});
      expect(l.single.label, 'Sam Example');
    });

    test('timeZone is passed as time_zone on task calls', () async {
      rig(_map('task.json'));
      await api.complete('task-0001', timeZone: 'Europe/Paris');
      expect(seen.single.url.queryParameters, {'time_zone': 'Europe/Paris'});
      await api.list(const TaskFilters(timeZone: 'Europe/Paris'));
      expect(seen.last.url.queryParameters['time_zone'], 'Europe/Paris');
    });

    test('settings get and update', () async {
      rig(_map('settings.json'));
      final s = await settings.get();
      expect(seen.single.url.path, '/v1/tasks/settings');
      expect(s.endOfDay, '17:00');
      await settings.update(const TaskSettingsPatch(endOfDay: '18:00'));
      expect(seen.last.method, 'PUT');
      expect(jsonDecode(seen.last.body), {'end_of_day': '18:00'});
    });
  });
}
