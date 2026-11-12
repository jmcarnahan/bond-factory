/// HTTP client of the notice routes.
library;

import 'package:bond_api/bond_api.dart';
import 'package:bond_json/bond_json.dart';

import 'notice.dart';

/// The notice routes under [prefix]. Failures are the `bond_api` exceptions.
class NoticesApi {
  NoticesApi(this.client, {this.prefix = '/notices'});

  final ApiClient client;
  final String prefix;

  String _one(String id) => '$prefix/${Uri.encodeComponent(id)}';

  Future<NoticePage> list({bool unread = false, int? limit, String? before}) async => NoticePage.fromJson(
      await client.getJson(prefix, query: {
        if (unread) 'unread': 'true',
        'limit': ?limit,
        'before': ?before,
      }));

  Future<Notice> read(String id) async => Notice.fromJson(await client.postJson('${_one(id)}/read'));

  Future<Notice> dismiss(String id) async => Notice.fromJson(await client.postJson('${_one(id)}/dismiss'));

  /// Marks every notice read; returns the new unread count.
  Future<int> readAll() async => jint(await client.postJson('$prefix/read-all'), 'unread_count') ?? 0;

  /// Applies [action] (`done`, `snooze` or `cancel`) to the notice's task.
  /// Returns the updated notice and the task as the server sent it.
  Future<NoticeActResult> act(String id, String action) async {
    final m = await client.postJson('${_one(id)}/act', body: {'action': action});
    final n = jmap(m, 'notice');
    if (n == null) throw const JsonShapeError('notice', 'Map', 'null');
    return NoticeActResult(Notice.fromJson(n), jmap(m, 'task'));
  }
}

/// The answer to `POST /notices/{id}/act`: the notice and the task it changed.
class NoticeActResult {
  const NoticeActResult(this.notice, this.task);

  final Notice notice;

  /// The `TaskItem` wire map, or null when the server sent none.
  final Map<String, Object?>? task;
}
