import 'dart:async';

import 'package:bond_ui/src/primitives/bond_search_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

const _short = Duration(milliseconds: 10);

Widget _picker({
  required Future<List<String>> Function(String) onSearch,
  List<String> picked = const [],
  void Function(String)? onPick,
  void Function(String)? onRemove,
}) =>
    BondSearchPicker<String>(
      onSearch: onSearch,
      labelOf: (s) => s,
      onPick: onPick ?? (_) {},
      picked: picked,
      onRemove: onRemove,
      debounce: _short,
      semanticsId: 'sp',
    );

void main() {
  for (final phone in [true, false]) {
    testWidgets('search shows inline results and a pick fires, phone=$phone', (t) async {
      final sem = t.ensureSemantics();
      String? got;
      await pumpBond(t, _picker(onSearch: (q) async => ['$q one', '$q two'], onPick: (s) => got = s), phone: phone);
      await t.enterText(find.byType(TextField), 'ab');
      await t.pump(_short);
      await t.pump();
      expect(find.text('ab one'), findsOneWidget);
      expect(find.bySemanticsIdentifier('sp-result-1'), findsOneWidget);
      await expectNoOverlays(t);
      await t.tap(find.text('ab two'));
      await t.pump();
      expect(got, 'ab two');
      expect(find.text('ab one'), findsNothing, reason: 'results clear after a pick');
      expect(t.takeException(), isNull);
      sem.dispose();
    });
  }

  testWidgets('fewer than minChars does not search', (t) async {
    var calls = 0;
    await pumpBond(t, _picker(onSearch: (q) async {
      calls++;
      return [];
    }));
    await t.enterText(find.byType(TextField), 'a');
    await t.pump(const Duration(seconds: 1));
    expect(calls, 0);
  });

  testWidgets('a stale answer is dropped', (t) async {
    final first = Completer<List<String>>();
    await pumpBond(t, _picker(onSearch: (q) => q == 'ab' ? first.future : Future.value(['fresh'])));
    await t.enterText(find.byType(TextField), 'ab');
    await t.pump(_short);
    await t.enterText(find.byType(TextField), 'abc');
    await t.pump(_short);
    await t.pump();
    expect(find.text('fresh'), findsOneWidget);
    first.complete(['stale']);
    await t.pump();
    expect(find.text('stale'), findsNothing);
    expect(find.text('fresh'), findsOneWidget);
  });

  testWidgets('busy, empty and error lines show inline', (t) async {
    final c = Completer<List<String>>();
    await pumpBond(t, _picker(onSearch: (q) => q == 'zz' ? Future.error('x') : c.future));
    await t.enterText(find.byType(TextField), 'ab');
    await t.pump(_short);
    expect(find.text('Searching'), findsOneWidget);
    c.complete([]);
    await t.pump();
    expect(find.text('No results'), findsOneWidget);
    await t.enterText(find.byType(TextField), 'zz');
    await t.pump(_short);
    await t.pump();
    expect(find.text('Search failed. Try again.'), findsOneWidget);
    await expectNoOverlays(t);
  });

  testWidgets('a picked chip says that activating it removes the item, and keeps its id', (t) async {
    final sem = t.ensureSemantics();
    String? removed;
    await pumpBond(t, _picker(onSearch: (q) async => [], picked: const ['Ann'], onRemove: (s) => removed = s));
    expect(find.bySemanticsLabel('Remove: Ann'), findsOneWidget);
    expect(find.bySemanticsIdentifier('sp-picked-0'), findsOneWidget);
    await t.tap(find.text('Ann'));
    expect(removed, 'Ann');
    // Without a remove callback it is just a label.
    await pumpBond(t, _picker(onSearch: (q) async => [], picked: const ['Ann']));
    expect(find.bySemanticsLabel('Remove: Ann'), findsNothing);
    sem.dispose();
  });

  testWidgets('picked items are chips that remove, and are left out of results', (t) async {
    String? removed;
    await pumpBond(
      t,
      _picker(onSearch: (q) async => ['Ann', 'Bob'], picked: const ['Ann'], onRemove: (s) => removed = s),
    );
    await t.enterText(find.byType(TextField), 'an');
    await t.pump(_short);
    await t.pump();
    expect(find.text('Ann'), findsOneWidget, reason: 'only the chip');
    expect(find.text('Bob'), findsOneWidget);
    await t.tap(find.text('Ann'));
    expect(removed, 'Ann');
  });
}
