import 'package:flutter_test/flutter_test.dart';
import 'package:roof_demo/main.dart';

void main() {
  testWidgets('demo page shows the language switch and the fixture chips, and no Measure button', (tester) async {
    await tester.pumpWidget(const RoofDemoApp());
    await tester.pump();
    expect(find.text('Load fixture'), findsOneWidget);
    expect(find.text('EN'), findsOneWidget);
    expect(find.text('ES'), findsOneWidget);
    expect(find.text('Measure'), findsNothing);
    expect(find.text('Address'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
