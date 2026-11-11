import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:roof_demo/src/demo_page.dart';
import 'package:roof_demo/src/service_client.dart';

ServiceClient _client(String finalBody) => ServiceClient(
      baseUrl: 'http://test',
      token: 't',
      pollInterval: Duration.zero,
      client: MockClient((r) async =>
          r.method == 'POST' ? http.Response('{"id":"j1","status":"queued"}', 202) : http.Response(finalBody, 200)),
    );

Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 10; i++) {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
    await tester.pump();
  }
}

void main() {
  testWidgets('a failed Measure clears the fixture report and shows only the error', (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1280, 4000);
    addTearDown(tester.view.reset);
    final failed = _client('{"id":"j1","status":"failed","error":{"code":"no_lidar_coverage","message":"No LiDAR here.","retryable":false}}');
    await tester.pumpWidget(MaterialApp(home: DemoPage(service: failed)));
    await _settle(tester);

    await tester.tap(find.widgetWithText(ChoiceChip, 'synthetic_hip'));
    await _settle(tester);
    expect(find.textContaining('Report: synthetic_hip'), findsOneWidget);
    expect(find.text('Drip edge (eave only)'), findsOneWidget);

    await tester.tap(find.text('Measure'));
    await _settle(tester);
    expect(find.textContaining('no_lidar_coverage: No LiDAR here.'), findsOneWidget);
    expect(find.textContaining('Report:'), findsNothing);
    expect(find.text('Drip edge (eave only)'), findsNothing);
    expect(find.text('Total area'), findsNothing);
    expect(tester.widget<ChoiceChip>(find.widgetWithText(ChoiceChip, 'synthetic_hip')).selected, isFalse);
  });
}
