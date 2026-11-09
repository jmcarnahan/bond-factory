import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/app.dart';

void main() {
  testWidgets('renders home with seven nav entries and no overlays', (tester) async {
    await tester.pumpWidget(const SdkDemoApp());
    await tester.pumpAndSettle();

    expect(tester.widget<Text>(find.byKey(const Key('page-title'))).data, 'Home');
    expect(find.byType(ListTile), findsNWidgets(7));
    expect(find.byType(Dialog), findsNothing);
    expect(find.byType(BottomSheet), findsNothing);
    expect(find.byType(Drawer), findsNothing);
  });
}
