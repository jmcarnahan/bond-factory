import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/app.dart';
import 'package:sdk_demo/src/pages.dart';

void main() {
  testWidgets('renders home with one nav entry per page and no overlays', (tester) async {
    await tester.pumpWidget(const SdkDemoApp());
    await tester.pumpAndSettle();

    expect(tester.widget<Text>(find.byKey(const Key('page-title'))).data, 'Home');
    expect(find.byType(ListTile), findsNWidgets(demoPages.length));
    expect(
      [for (final p in demoPages) p.path],
      ['/', '/ui', '/api', '/auth', '/sync', '/connections', '/tasks', '/today', '/capture', '/calendar', '/todo-settings', '/inbox'],
    );
    expect(find.byType(Dialog), findsNothing);
    expect(find.byType(BottomSheet), findsNothing);
    expect(find.byType(Drawer), findsNothing);
  });
}
