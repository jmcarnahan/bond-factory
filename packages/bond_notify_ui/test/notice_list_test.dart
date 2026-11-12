import 'package:bond_notify/bond_notify.dart';
import 'package:bond_notify_ui/bond_notify_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

Notice n(String id, {bool read = false}) => Notice(
      id: id,
      title: 'Title $id',
      actions: const ['done'],
      createdAt: kNow.subtract(const Duration(hours: 2)),
      readAt: read ? kNow : null,
    );

void main() {
  testWidgets('loading shows a line and no empty text', (t) async {
    await atBothWidths(t, () => BondNoticeList(notices: const [], now: kNow, loading: true), check: (_) async {
      expect(find.text('Loading notifications'), findsOneWidget);
      expect(find.text('No notifications'), findsNothing);
    });
  });

  testWidgets('empty shows the empty line and no Mark all read', (t) async {
    await atBothWidths(t, () => BondNoticeList(notices: const [], now: kNow), check: (_) async {
      expect(find.text('No notifications'), findsOneWidget);
      expect(find.text('Mark all read'), findsNothing);
    });
  });

  testWidgets('error shows a line and retry calls onRetry', (t) async {
    var retries = 0;
    await atBothWidths(
      t,
      () => BondNoticeList(notices: const [], now: kNow, error: 'boom', onRetry: () => retries++),
      check: (_) async {
        expect(find.text('Notifications could not be loaded'), findsOneWidget);
        expect(find.text('No notifications'), findsNothing);
        await t.tap(find.text('Try again'));
      },
    );
    expect(retries, 2);
  });

  testWidgets('header counts unread and Mark all read fires', (t) async {
    var marks = 0;
    await atBothWidths(
      t,
      () => BondNoticeList(notices: [n('a'), n('b'), n('c', read: true)], now: kNow, onMarkAllRead: () => marks++),
      check: (_) async {
        expect(find.text('Notifications'), findsOneWidget);
        expect(find.text('2 unread'), findsOneWidget);
        expect(find.text('Title a'), findsOneWidget);
        expect(find.text('Title c'), findsOneWidget);
        await t.tap(find.text('Mark all read'));
      },
    );
    expect(marks, 2);
  });

  testWidgets('undo line shows under the named row only and calls onUndo', (t) async {
    final undone = <String>[];
    await atBothWidths(
      t,
      () => BondNoticeList(notices: [n('a'), n('b')], now: kNow, undoNoticeId: 'b', onUndo: (x) => undone.add(x.id)),
      check: (_) async {
        expect(find.text('Marked done.'), findsOneWidget);
        expect(t.getTopLeft(find.text('Marked done.')).dy, greaterThan(t.getTopLeft(find.text('Title b')).dy));
        await t.tap(find.text('Undo'));
      },
    );
    expect(undone, ['b', 'b']);
  });

  testWidgets('no undo line without undoNoticeId; row actions and dismiss pass through', (t) async {
    final log = <String>[];
    await pumpAt(
      t,
      BondNoticeList(
        notices: [n('a')],
        now: kNow,
        onAction: (x, a) => log.add('${x.id}:$a'),
        onDismiss: (x) => log.add('dismiss ${x.id}'),
        onOpen: (x) => log.add('open ${x.id}'),
        semanticsPrefix: 'p',
      ),
    );
    expect(find.text('Marked done.'), findsNothing);
    await t.tap(find.text('Done'));
    await t.tap(find.byIcon(Icons.close));
    await t.tap(find.text('Title a'));
    expect(log, ['a:done', 'dismiss a', 'open a']);
  });

  testWidgets('semantics ids use the prefix', (t) async {
    final h = t.ensureSemantics();
    await pumpAt(
      t,
      BondNoticeList(
        notices: [n('a')],
        now: kNow,
        onMarkAllRead: () {},
        onOpen: (_) {},
        undoNoticeId: 'a',
        onUndo: (_) {},
        semanticsPrefix: 'p',
      ),
    );
    for (final id in ['p.row-a', 'p.row-a-done', 'p.mark-all', 'p.undo']) {
      expect(byId(id), findsOneWidget, reason: id);
    }
    h.dispose();
  });

  testWidgets('each row is keyed by its notice id', (t) async {
    await pumpAt(t, BondNoticeList(notices: [n('a'), n('b')], now: kNow));
    expect(find.byKey(const ValueKey('a')), findsOneWidget);
    expect(find.byKey(const ValueKey('b')), findsOneWidget);
    expect(t.widget(find.byKey(const ValueKey('a'))), isA<BondNoticeRow>());
  });

  testWidgets('a dismissed row does not hand its element to the next', (t) async {
    await pumpAt(t, BondNoticeList(notices: [n('a'), n('b')], now: kNow));
    final before = t.element(find.byKey(const ValueKey('b')));
    await pumpAt(t, BondNoticeList(notices: [n('b')], now: kNow));
    expect(t.element(find.byKey(const ValueKey('b'))), same(before));
  });

  testWidgets('unreadCount from the server wins over the loaded rows', (t) async {
    final rows = [for (var i = 0; i < 50; i++) n('r$i')];
    await atBothWidths(t, () => BondNoticeList(notices: rows, now: kNow, unreadCount: 75), check: (_) async {
      expect(find.text('75 unread'), findsOneWidget);
      expect(find.text('50 unread'), findsNothing);
    });
  });

  testWidgets('unreadCount 0 hides the count even with unread rows; null derives', (t) async {
    await pumpAt(t, BondNoticeList(notices: [n('a')], now: kNow, unreadCount: 0));
    expect(find.text('1 unread'), findsNothing);
    await pumpAt(t, BondNoticeList(notices: [n('a'), n('b')], now: kNow));
    expect(find.text('2 unread'), findsOneWidget);
  });
}
