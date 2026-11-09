import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/app.dart';
import 'package:sdk_demo/src/pages.dart';

void main() {
  for (final page in demoPages) {
    testWidgets('${page.path} shows ${page.title}', (tester) async {
      await tester.pumpWidget(SdkDemoApp(initialLocation: page.path));
      await tester.pumpAndSettle();

      expect(tester.widget<Text>(find.byKey(const Key('page-title'))).data, page.title);
    });
  }

  testWidgets('tapping a nav entry navigates', (tester) async {
    await tester.pumpWidget(const SdkDemoApp());
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(ListTile, 'Tasks'));
    await tester.pumpAndSettle();

    expect(tester.widget<Text>(find.byKey(const Key('page-title'))).data, 'Tasks');
    expect(find.textContaining('arrives in phase 3'), findsOneWidget);
  });
}
