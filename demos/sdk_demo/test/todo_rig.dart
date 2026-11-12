import 'dart:async';

import 'package:bond_api/bond_api.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_test_support/bond_test_support.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:sdk_demo/src/todo/todo_services.dart';

Finder byId(String id) => find.byWidgetPredicate((w) => w is Semantics && w.properties.identifier == id);

/// 2026-03-12 16:00 UTC is 09:00 in America/Los_Angeles (the zone the tests run in).
final DateTime kNow = DateTime.utc(2026, 3, 12, 16);

/// A task as the server sends it.
Map<String, Object?> taskJson(
  String id,
  String title, {
  String? date,
  String? time,
  DateTime? dueAt,
  TaskPriority? priority,
  TaskStatus status = TaskStatus.open,
  String owner = 'demo-user-1',
  String? assigned,
  bool overdue = false,
}) =>
    Task(
      id: id,
      title: title,
      dueDate: date,
      dueTime: time,
      dueAt: dueAt,
      priority: priority,
      status: status,
      ownerUserId: owner,
      assignedUserId: assigned,
      overdue: overdue,
      remindMinutesBefore: kRemindUseDefault,
    ).toJson();

Map<String, Object?> todayJson({
  List<Map<String, Object?>> overdue = const [],
  List<Map<String, Object?>> today = const [],
  List<Map<String, Object?>> undated = const [],
  List<Map<String, Object?>> done = const [],
}) =>
    {
      'overdue': overdue,
      'today': today,
      'undated': undated,
      'done_today': done,
      'counts': {'overdue': overdue.length, 'today': today.length, 'undated': undated.length, 'done_today': done.length},
    };

Map<String, Object?> noticeJson(
  String id,
  String title, {
  String stage = 'close',
  String taskId = 't1',
  int seq = 0,
  bool last = false,
  List<String> actions = const ['done', 'snooze', 'cancel'],
  String? readAt,
  String createdAt = '2026-03-12T15:55:00Z',
}) =>
    {
      'id': id,
      'user_id': 'demo-user-1',
      'kind': 'task',
      'title': title,
      'body': 'Due soon',
      'data': {
        'task_id': taskId,
        'stage': stage,
        'seq': seq,
        'due_at': '2026-03-12T17:00:00Z',
        'priority': null,
        'route': '/tasks/$taskId',
        'actions': actions,
        'last': last,
      },
      'created_at': createdAt,
      'read_at': readAt,
      'dismissed_at': null,
    };

class TodoRig {
  TodoRig({DateTime? now, bool fake = true, String user = 'demo-user-1', Future<Object?> Function()? ensureSignedIn}) {
    services = TodoServices(
      client: ApiClient(baseUrl: Uri.parse('http://example.test'), http: _Holding(canned, holds)),
      userId: user,
      ensureSignedIn: ensureSignedIn,
      fakeMode: fake,
      deviceNow: () => now ?? kNow,
      zone: 'America/Los_Angeles',
    );
  }

  final CannedHttpClient canned = CannedHttpClient();

  /// Requests (`METHOD /path`) held until the completer is completed: the answer is "in flight".
  final Map<String, Completer<void>> holds = {};
  late final TodoServices services;

  CannedResponses get on => canned.responses;

  RecordedRequest only(String method, String path) => canned.requestsTo(method, path).single;
  List<RecordedRequest> all(String method, String path) => canned.requestsTo(method, path);

  /// The routes every page reads.
  void baseline({Map<String, Object?>? today, List<Map<String, Object?>> open = const [], List<Map<String, Object?>> notices = const []}) {
    on.json('GET', '/tasks/today', today ?? todayJson());
    on.json('GET', '/tasks', {'items': open, 'total': open.length});
    on.json('GET', '/tasks/settings', {
      'time_zone': 'America/Los_Angeles',
      'start_of_day': '08:00',
      'end_of_day': '17:00',
      'lead_minutes': 60,
      'warnings': <Object?>[],
    });
    on.json('GET', '/notices', {'items': notices, 'unread_count': notices.length});
  }
}

Future<void> pumpPage(WidgetTester t, Widget page, {bool phone = false}) async {
  if (phone) {
    setPhone(t, size: const Size(390, 3600));
  } else {
    setWideScreen(t, size: const Size(1280, 3600));
  }
  await pumpApp(t, page);
  await settle(t);
}

Future<void> settle(WidgetTester t, [int frames = 8]) async {
  for (var i = 0; i < frames; i++) {
    await t.pump(const Duration(milliseconds: 30));
  }
}

/// Ends the test with the page gone, so its timers are cancelled.
Future<void> leave(WidgetTester t) async {
  await t.pumpWidget(const SizedBox.shrink());
  await t.pump(const Duration(milliseconds: 50));
}

String labelOf(WidgetTester t, String id) => t.getSemantics(byId(id).first).label;

/// Delays the answer of a held request until its completer completes.
class _Holding extends http.BaseClient {
  _Holding(this.inner, this.holds);

  final CannedHttpClient inner;
  final Map<String, Completer<void>> holds;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final gate = holds['${request.method} ${request.url.path}'];
    if (gate != null) await gate.future;
    return inner.send(request);
  }
}
