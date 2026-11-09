import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/components/bond_message_preview.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'kit_host.dart';

void main() {
  testWidgets('shows the selected variant and switches on tap', (t) async {
    setPhone(t);
    final handle = t.ensureSemantics();
    var selected = 'en';
    await pumpKit(
      t,
      StatefulBuilder(
        builder: (context, set) => BondMessagePreview(
          variants: const [
            BondMessageVariant(id: 'en', label: 'English', body: 'Hello there'),
            BondMessageVariant(id: 'es', label: 'Spanish', body: 'Hola'),
          ],
          selectedId: selected,
          onSelected: (id) => set(() => selected = id),
          sentLabel: 'Sent 5:00 PM',
          semanticsId: 'msg',
        ),
      ),
    );
    expect(find.text('Hello there'), findsOneWidget);
    expect(find.text('Sent 5:00 PM'), findsOneWidget);
    expect(byId('msg-es'), findsOneWidget);
    await t.tap(find.text('Spanish'));
    await t.pump();
    expect(find.text('Hola'), findsOneWidget);
    expect(find.text('Hello there'), findsNothing);
    await expectNoOverlays(t);
    handle.dispose();
  });
}
