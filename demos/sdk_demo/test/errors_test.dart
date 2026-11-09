import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/app.dart';
import 'package:sdk_demo/src/errors.dart';

void main() {
  tearDown(() => DemoErrors.instance.clear());

  test('caps at 20, drops duplicates, newest first', () async {
    final errors = DemoErrors.instance;
    for (var i = 0; i < 30; i++) {
      errors.add('error $i');
      errors.add('error $i');
    }
    await Future<void>.delayed(Duration.zero);
    expect(errors.value.length, DemoErrors.maxEntries);
    expect(errors.value.first, 'error 29');
    expect(errors.value.toSet().length, errors.value.length);
  });

  testWidgets('strip shows the count and the newest error', (tester) async {
    await tester.pumpWidget(const SdkDemoApp());
    await tester.pumpAndSettle();
    expect(find.textContaining('Runtime errors'), findsNothing);

    DemoErrors.instance.add('first');
    DemoErrors.instance.add('second\nline two');
    DemoErrors.instance.add('first');
    await tester.pumpAndSettle();

    expect(find.text('Runtime errors: 2'), findsOneWidget);
    final newest = tester.getTopLeft(find.textContaining('second')).dy;
    final oldest = tester.getTopLeft(find.text('first')).dy;
    expect(newest, lessThan(oldest));
  });
}
