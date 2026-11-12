import 'package:bond_notify/bond_notify.dart';
import 'package:bond_notify_ui/bond_notify_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

Notice notice({
  List<String> actions = const ['done', 'snooze', 'cancel'],
  bool last = false,
  bool read = false,
  String title = 'Call the supplier',
  String body = 'Due at 3 pm',
}) =>
    Notice(
      id: 'n1',
      title: title,
      body: body,
      actions: actions,
      last: last,
      createdAt: kNow.subtract(const Duration(minutes: 5)),
      readAt: read ? kNow : null,
    );

Widget row(Notice n, {void Function(Notice, String)? onAction, void Function(Notice)? onOpen, void Function(Notice)? onDismiss}) =>
    BondNoticeRow(notice: n, now: kNow, onAction: onAction, onOpen: onOpen, onDismiss: onDismiss, semanticsId: 'r1');

void main() {
  testWidgets('all three actions show in order and report their wire ids', (t) async {
    final got = <String>[];
    await atBothWidths(
      t,
      () => row(notice(actions: const ['cancel', 'done', 'snooze', 'bogus']), onAction: (n, a) => got.add(a)),
      check: (_) async {
        expect(find.text('Done'), findsOneWidget);
        expect(find.text('Snooze'), findsOneWidget);
        expect(find.text('Cancel task'), findsOneWidget);
        expect(find.text('bogus'), findsNothing);
        // Reading order: top to bottom, then left to right (the buttons wrap at 390).
        final p = [for (final s in ['Done', 'Snooze', 'Cancel task']) t.getTopLeft(find.text(s))];
        for (var i = 1; i < p.length; i++) {
          expect(p[i].dy > p[i - 1].dy || (p[i].dy == p[i - 1].dy && p[i].dx > p[i - 1].dx), isTrue);
        }
        for (final s in ['Done', 'Snooze', 'Cancel task']) {
          await t.tap(find.text(s));
        }
      },
    );
    expect(got, ['done', 'snooze', 'cancel', 'done', 'snooze', 'cancel']);
  });

  testWidgets('no cancel action: no cancel button', (t) async {
    await atBothWidths(t, () => row(notice(actions: const ['done', 'snooze'])), check: (_) async {
      expect(find.text('Done'), findsOneWidget);
      expect(find.text('Cancel task'), findsNothing);
    });
  });

  testWidgets('no actions: no buttons but the row, time and dismiss remain', (t) async {
    await atBothWidths(t, () => row(notice(actions: const [])), check: (_) async {
      expect(find.text('Done'), findsNothing);
      expect(find.text('Snooze'), findsNothing);
      expect(find.text('5 min ago'), findsOneWidget);
      expect(find.byIcon(Icons.close), findsOneWidget);
    });
  });

  testWidgets('last reminder mark only when last', (t) async {
    await atBothWidths(t, () => row(notice(last: true)), check: (_) async {
      expect(find.text('Last reminder'), findsOneWidget);
    });
    await atBothWidths(t, () => row(notice()), check: (_) async {
      expect(find.text('Last reminder'), findsNothing);
    });
  });

  testWidgets('unread shows the mark, read does not', (t) async {
    await atBothWidths(t, () => row(notice()), check: (_) async {
      expect(find.byKey(const ValueKey('notice-unread-mark')), findsOneWidget);
    });
    await atBothWidths(t, () => row(notice(read: true)), check: (_) async {
      expect(find.byKey(const ValueKey('notice-unread-mark')), findsNothing);
    });
  });

  testWidgets('tapping the text opens, the cross dismisses', (t) async {
    final log = <String>[];
    await pumpAt(
      t,
      row(notice(), onOpen: (n) => log.add('open ${n.id}'), onDismiss: (n) => log.add('dismiss ${n.id}')),
    );
    await t.tap(find.text('Call the supplier'));
    await t.tap(find.byIcon(Icons.close));
    expect(log, ['open n1', 'dismiss n1']);
  });

  testWidgets('long title and body do not overflow at 390', (t) async {
    final long = List.filled(40, 'unbreakable').join(' ');
    await atBothWidths(t, () => row(notice(title: long, body: long, last: true)));
    expect(find.text(long), findsNWidgets(2));
  });

  testWidgets('semantics ids on tappables', (t) async {
    final h = t.ensureSemantics();
    await pumpAt(t, row(notice(), onAction: (_, _) {}, onDismiss: (_) {}, onOpen: (_) {}));
    for (final id in ['r1', 'r1-done', 'r1-snooze', 'r1-cancel', 'r1-dismiss']) {
      expect(byId(id), findsOneWidget, reason: id);
    }
    h.dispose();
  });
}
