import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/main.dart';

void main() {
  testWidgets('app shows its name', (tester) async {
    await tester.pumpWidget(const SdkDemoApp());
    expect(find.text('sdk_demo'), findsOneWidget);
  });
}
