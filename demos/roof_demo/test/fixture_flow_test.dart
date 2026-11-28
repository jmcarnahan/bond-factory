import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roof_demo/src/demo_page.dart';

Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 10; i++) {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
    await tester.pump();
  }
}

void main() {
  testWidgets('picking the 0.7 sample shows its report and totals; the language switch relabels them', (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1280, 6000);
    addTearDown(tester.view.reset);
    await tester.pumpWidget(const MaterialApp(home: DemoPage()));
    await _settle(tester);

    expect(find.widgetWithText(ChoiceChip, 'roof_measurement_0.7_sample'), findsOneWidget);
    await tester.tap(find.widgetWithText(ChoiceChip, 'roof_measurement_0.7_sample'));
    await _settle(tester);
    expect(find.textContaining('Report: roof_measurement_0.7_sample'), findsOneWidget);
    expect(find.text('Sidewall flashing'), findsWidgets);
    expect(find.text('Headwall flashing'), findsWidgets);
    expect(find.text('Chimneys'), findsWidgets);

    await tester.tap(find.text('ES'));
    await _settle(tester);
    expect(find.text('Tapajuntas de pared lateral'), findsWidgets);
    expect(find.text('Chimeneas'), findsWidgets);
  });

  testWidgets('an old envelope opens and shows no verification row', (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1280, 6000);
    addTearDown(tester.view.reset);
    await tester.pumpWidget(const MaterialApp(home: DemoPage()));
    await _settle(tester);
    await tester.tap(find.widgetWithText(ChoiceChip, 'roof_measurement_0.2_pass'));
    await _settle(tester);
    expect(find.textContaining('Report: roof_measurement_0.2_pass'), findsOneWidget);
    expect(find.text('Verification'), findsNothing);
    expect(find.text('Total area'), findsWidgets);
  });
}
