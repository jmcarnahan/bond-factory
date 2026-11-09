import 'package:bond_ui/src/primitives/bond_photo.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  testWidgets('no url shows the placeholder icon at the given size', (t) async {
    await pumpBond(
      t,
      const BondPhoto(url: null, width: 120, height: 88, icon: Icons.person),
    );
    expect(find.byIcon(Icons.person), findsOneWidget);
    expect(find.byType(Image), findsNothing);
    expect(t.getSize(find.byType(BondPhoto)), const Size(120, 88));
    await expectNoOverlays(t);
  });

  testWidgets('empty url is treated as no image', (t) async {
    await pumpBond(t, const BondPhoto(url: '', width: 60, height: 60));
    expect(find.byType(Image), findsNothing);
  });

  testWidgets('a url builds a network image carrying the headers', (t) async {
    await pumpBond(
      t,
      const BondPhoto(
        url: 'http://localhost.invalid/photo.png',
        width: 60,
        height: 60,
        headers: {'Authorization': 'Bearer test'},
        semanticLabel: 'A photo',
      ),
    );
    expect(find.byType(Image), findsOneWidget);
    final provider = t.widget<Image>(find.byType(Image)).image as NetworkImage;
    expect(provider.headers, {'Authorization': 'Bearer test'});
    // The test host has no network; the failed load shows the placeholder.
    await t.pump();
    await t.pump();
  });
}
