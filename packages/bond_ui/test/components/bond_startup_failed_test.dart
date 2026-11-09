import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/components/bond_startup_failed.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('is a whole app showing the cause and the server address', (t) async {
    setPhone(t);
    final handle = t.ensureSemantics();
    await t.pumpWidget(const BondStartupFailed(error: 'storage unavailable', baseUrl: 'http://localhost:1', appName: 'Demo'));
    expect(find.text('Demo'), findsOneWidget);
    expect(find.text('The app could not start'), findsOneWidget);
    expect(find.text('storage unavailable'), findsOneWidget);
    expect(find.text('http://localhost:1'), findsOneWidget);
    expect(find.bySemanticsIdentifier('startup-failed'), findsOneWidget);
    await expectNoOverlays(t);
    expect(t.takeException(), isNull);
    handle.dispose();
  });
}
