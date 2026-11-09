import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/components/bond_page_header.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'kit_host.dart';

void main() {
  testWidgets('wide: actions sit beside the title', (t) async {
    setWideScreen(t);
    await pumpKit(t, const BondPageHeader(title: 'People', subtitle: 'Everyone', actions: [Text('Add')]));
    expect(find.text('People'), findsOneWidget);
    expect(find.text('Everyone'), findsOneWidget);
    expect(t.getTopLeft(find.text('Add')).dx, greaterThan(t.getTopRight(find.text('People')).dx));
    expect(t.getTopLeft(find.text('Add')).dx, greaterThan(1000));
  });

  testWidgets('phone: actions wrap under the title without overflow', (t) async {
    setPhone(t);
    await pumpKit(t, const BondPageHeader(title: 'People', actions: [Text('Add'), Text('Export')]));
    expect(t.getTopLeft(find.text('Add')).dy, greaterThan(t.getBottomLeft(find.text('People')).dy - 1));
    expect(t.takeException(), isNull);
  });

  testWidgets('breadcrumbs: earlier crumbs are tappable, the last is plain', (t) async {
    setPhone(t);
    final handle = t.ensureSemantics();
    var taps = 0;
    await pumpKit(
      t,
      BondPageHeader(
        title: 'Detail',
        eyebrow: 'Section',
        breadcrumbs: [
          BondCrumb('Home', onTap: () => taps++, semanticsId: 'crumb.home'),
          BondCrumb('Detail', onTap: () => taps += 10),
        ],
      ),
    );
    expect(byId('crumb.home'), findsOneWidget);
    await t.tap(find.text('Home'));
    await t.tap(find.text('Detail').first);
    expect(taps, 1);
    expect(find.text('Section'), findsOneWidget);
    await expectNoOverlays(t);
    handle.dispose();
  });
}
