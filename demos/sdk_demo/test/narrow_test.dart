import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/app.dart';
import 'package:sdk_demo/src/pages.dart';
import 'package:sdk_demo/src/pages/page_scaffold.dart';

Finder _nav(String id) =>
    find.byWidgetPredicate((w) => w is Semantics && w.properties.identifier == 'sdk.nav.$id');

Finder _selectedNav(String id) => find.byWidgetPredicate(
      (w) => w is Semantics && w.properties.identifier == 'sdk.nav.$id' && w.properties.selected == true,
    );

void main() {
  testWidgets('at 390x844 the page keeps at least 320 px and every route is reachable', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(const SdkDemoApp());
    await tester.pumpAndSettle();

    expect(tester.getSize(find.byType(PageFrame)).width, greaterThanOrEqualTo(320));
    expect(find.byType(ListTile), findsNothing);
    expect(_selectedNav('home'), findsOneWidget);

    for (final page in demoPages) {
      expect(_nav(page.id), findsOneWidget, reason: 'sdk.nav.${page.id} is in the strip');
      await tester.ensureVisible(_nav(page.id));
      await tester.tap(_nav(page.id));
      await tester.pumpAndSettle();

      expect(tester.widget<Text>(find.byKey(const Key('page-title'))).data, page.title);
      expect(_selectedNav(page.id), findsOneWidget);
      expect(tester.getSize(find.byType(PageFrame)).width, greaterThanOrEqualTo(320));
    }
  });
}
