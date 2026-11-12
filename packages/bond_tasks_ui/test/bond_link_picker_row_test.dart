import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

const _dana = TaskLink(kind: 'contact', id: 'c1', label: 'Dana Fox');
const _eli = TaskLink(kind: 'contact', id: 'c2', label: 'Eli Stone');

void main() {
  for (final phone in [false, true]) {
    testWidgets('search, pick and remove (phone=$phone)', (t) async {
      final changes = <List<TaskLink>>[];
      final asked = <String>[];
      var links = <TaskLink>[_dana];
      await pumpAt(
        t,
        StatefulBuilder(
          builder: (context, set) => BondLinkPickerRow(
            links: links,
            onSearch: (kind, q) async {
              asked.add('$kind:$q');
              return [_dana, _eli];
            },
            onChanged: (v) => set(() {
              links = v;
              changes.add(v);
            }),
            semanticsId: 'lp',
          ),
        ),
        phone: phone,
      );
      expect(find.text('Dana Fox'), findsOneWidget);
      await t.enterText(find.byType(TextField), 'fo');
      await t.pump(const Duration(milliseconds: 300));
      await t.pump();
      expect(asked, ['contact:fo']);
      // The already linked contact is not offered again.
      expect(find.text('Dana Fox'), findsOneWidget);
      await t.tap(find.text('Eli Stone'));
      await t.pump();
      expect(changes.last, [_dana, _eli]);
      await t.tap(find.text('Dana Fox'));
      await t.pump();
      expect(changes.last, [_eli]);
      await expectNoOverlays(t);
      expect(t.takeException(), isNull);
    });
  }

  testWidgets('a link with the same kind and id is not added twice', (t) async {
    final changes = <List<TaskLink>>[];
    await pumpAt(
      t,
      BondLinkPickerRow(
        links: const [TaskLink(kind: 'contact', id: 'c1')],
        onSearch: (k, q) async => [_dana],
        onChanged: changes.add,
      ),
    );
    await t.enterText(find.byType(TextField), 'da');
    await t.pump(const Duration(milliseconds: 300));
    await t.pump();
    await t.tap(find.text('Dana Fox'));
    await t.pump();
    expect(changes, isEmpty);
  });
}
