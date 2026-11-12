import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/app.dart';
import 'package:sdk_demo/src/pages.dart';
import 'package:sdk_demo/src/todo/todo_alerts.dart';

void main() {
  for (final page in demoPages) {
    testWidgets('${page.path} shows ${page.title}', (tester) async {
      await tester.pumpWidget(SdkDemoApp(initialLocation: page.path));
      await tester.pumpAndSettle();

      expect(tester.widget<Text>(find.byKey(const Key('page-title'))).data, page.title);
    });
  }

  testWidgets('tapping each nav entry shows that page title', (tester) async {
    await tester.pumpWidget(const SdkDemoApp());
    await tester.pumpAndSettle();

    for (final page in demoPages) {
      await tester.tap(find.widgetWithText(ListTile, page.title));
      await tester.pumpAndSettle();

      expect(tester.widget<Text>(find.byKey(const Key('page-title'))).data, page.title);
    }
  });

  testWidgets('a plain tap on a notification opens the task on the Today page', (tester) async {
    addTearDown(() => TodoAlerts.openedTask.value = null);
    await tester.pumpWidget(const SdkDemoApp(initialLocation: '/inbox'));
    await tester.pumpAndSettle();
    TodoAlerts.open('/tasks/t7');
    await tester.pumpAndSettle();
    expect(tester.widget<Text>(find.byKey(const Key('page-title'))).data, 'Today');
    expect(TodoAlerts.openedTask.value, 't7');
  });
}
