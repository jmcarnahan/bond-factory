import 'package:flutter_test/flutter_test.dart';
import 'package:roof_demo/main.dart';

void main() {
  testWidgets('demo page shows the controls', (tester) async {
    await tester.pumpWidget(const RoofDemoApp());
    await tester.pump();
    expect(find.text('Measure'), findsOneWidget);
    expect(find.text('Load fixture'), findsOneWidget);
    expect(find.text('EN'), findsOneWidget);
    expect(find.text('ES'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
