import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/components/bond_stale_banner.dart';
import 'package:flutter_test/flutter_test.dart';

import 'kit_host.dart';

void main() {
  testWidgets('uses the supplied formatter and never a clock', (t) async {
    setPhone(t);
    final handle = t.ensureSemantics();
    var retries = 0;
    await pumpKit(
      t,
      BondStaleBanner(
        asOf: DateTime.utc(2026, 1, 2, 11, 42),
        formatTime: (d) => '${d.hour}:${d.minute}',
        onRetry: () => retries++,
      ),
    );
    expect(find.text('Not updated since 11:42'), findsOneWidget);
    expect(byId('stale-banner'), findsOneWidget);
    expect(byId('stale-banner-retry'), findsOneWidget);
    await t.tap(find.text('Retry'));
    expect(retries, 1);
    await expectNoOverlays(t);
    handle.dispose();
  });

  testWidgets('null asOf says not updated yet', (t) async {
    await pumpKit(t, BondStaleBanner(asOf: null, formatTime: (_) => 'x', onRetry: () {}));
    expect(find.text('Not updated yet'), findsOneWidget);
  });
}
