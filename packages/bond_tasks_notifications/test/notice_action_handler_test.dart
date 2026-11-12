import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_notifications/bond_tasks_notifications.dart';
import 'package:bond_tasks_notifications/testing.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fakes.dart';

void main() {
  late FakeRepo repo;
  late FakeFeed feed;
  late FakeAlertPlugin plugin;
  late NoticeActionHandler handler;

  setUp(() {
    repo = FakeRepo();
    feed = FakeFeed();
    plugin = FakeAlertPlugin();
    handler = NoticeActionHandler(repo, feed, plugin: plugin);
  });

  test('done completes the task, marks read, clears the notification', () async {
    await handler.apply('n1', 't1', NoticeAction.done);
    expect(repo.completed, ['t1']);
    expect(repo.cancelled, isEmpty);
    expect(feed.read, ['n1']);
    expect(plugin.cancelled, [fnv1a31('n1')]);
  });

  test('cancel cancels the task', () async {
    await handler.apply('n1', 't1', NoticeAction.cancel);
    expect(repo.cancelled, ['t1']);
    expect(repo.completed, isEmpty);
    expect(feed.read, ['n1']);
  });

  test('snooze leaves the task alone but puts the notice away', () async {
    await handler.apply('n1', 't1', NoticeAction.snooze);
    expect(repo.completed, isEmpty);
    expect(repo.cancelled, isEmpty);
    expect(feed.read, ['n1']);
    expect(plugin.cancelled, [fnv1a31('n1')]);
  });

  test('a repository failure propagates and the notice stays unread and shown', () async {
    repo.failWith = StateError('offline');
    await expectLater(handler.apply('n1', 't1', NoticeAction.done), throwsStateError);
    expect(feed.read, isEmpty);
    expect(plugin.cancelled, isEmpty);
  });

  test('a notice that is gone does not fail the action', () async {
    feed.failRead = StateError('not found');
    await handler.apply('n1', 't1', NoticeAction.done);
    expect(repo.completed, ['t1']);
    expect(plugin.cancelled, [fnv1a31('n1')]);
  });

  group('a task that no longer exists', () {
    for (final entry in <String, Object>{
      'task_not_found state error': StateError('task_not_found: t1'),
      'status code 404': _Http(statusCode: 404),
      'status code 410': _Http(statusCode: 410),
      'status 404': _Http(status: 404),
    }.entries) {
      test('${entry.key}: notice put away, nothing rethrown', () async {
        repo.failWith = entry.value;
        await handler.apply('n1', 't1', NoticeAction.done);
        expect(feed.read, ['n1']);
        expect(plugin.cancelled, [fnv1a31('n1')]);
      });
    }

    test('other errors still propagate, including a 500', () async {
      repo.failWith = _Http(statusCode: 500);
      await expectLater(handler.apply('n1', 't1', NoticeAction.cancel), throwsA(isA<_Http>()));
      expect(feed.read, isEmpty);
    });

    test('a custom isGone replaces the default', () async {
      repo.failWith = StateError('weird');
      final h = NoticeActionHandler(repo, feed, plugin: plugin, isGone: (e) => e is StateError);
      await h.apply('n1', 't1', NoticeAction.done);
      expect(feed.read, ['n1']);
    });
  });

  test('works without a plugin', () async {
    await NoticeActionHandler(repo, feed).apply('n1', 't1', NoticeAction.done);
    expect(feed.read, ['n1']);
  });
}

class _Http implements Exception {
  _Http({this.statusCode, this.status});
  final int? statusCode;
  final int? status;
}
