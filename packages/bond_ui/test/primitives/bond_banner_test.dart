import 'package:bond_ui/src/primitives/bond_banner.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  testWidgets('shows title and message with a default icon per tone', (t) async {
    await pumpBond(
      t,
      const Column(children: [
        BondBanner(title: 'Heads up', message: 'Details here'),
        BondBanner(title: 'Broken', tone: BondToneRole.danger),
        BondBanner(title: 'Saved', tone: BondToneRole.positive),
      ]),
    );
    expect(find.text('Heads up'), findsOneWidget);
    expect(find.text('Details here'), findsOneWidget);
    expect(find.byIcon(Icons.info_outline), findsOneWidget);
    expect(find.byIcon(Icons.error_outline), findsOneWidget);
    expect(find.byIcon(Icons.check_circle_outline), findsOneWidget);
    await expectNoOverlays(t);
  });

  testWidgets('action and dismiss fire and carry derived ids', (t) async {
    final sem = t.ensureSemantics();
    var acted = 0;
    var dismissed = 0;
    await pumpBond(
      t,
      BondBanner(
        title: 'Update available',
        actionLabel: 'Refresh',
        onAction: () => acted++,
        onDismiss: () => dismissed++,
        semanticsId: 'banner',
      ),
    );
    expect(find.bySemanticsIdentifier('banner'), findsOneWidget);
    expect(find.bySemanticsIdentifier('banner-action'), findsOneWidget);
    expect(find.bySemanticsIdentifier('banner-dismiss'), findsOneWidget);
    await t.tap(find.text('Refresh'));
    await t.tap(find.byIcon(Icons.close));
    await t.pump();
    expect(acted, 1);
    expect(dismissed, 1);
    // The dismiss button is named from the labels.
    expect(find.bySemanticsLabel('Dismiss'), findsOneWidget);
    await expectNoOverlays(t);
    sem.dispose();
  });

  testWidgets('stackAction puts the action under the text', (t) async {
    await pumpBond(
      t,
      BondBanner(
        title: 'Title',
        actionLabel: 'Go',
        stackAction: true,
        onAction: () {},
      ),
    );
    final title = t.getTopLeft(find.text('Title'));
    final action = t.getTopLeft(find.text('Go'));
    expect(action.dy, greaterThan(title.dy));
    expect(t.takeException(), isNull);
  });

  testWidgets('large text moves the action under the text, no overflow', (t) async {
    setPhone(t);
    await t.pumpWidget(MaterialApp(
      home: MediaQuery(
        data: const MediaQueryData(
          size: Size(390, 844),
          textScaler: TextScaler.linear(2),
        ),
        child: Scaffold(
          body: BondBanner(
            title: 'A banner with a fairly long title',
            message: 'And a message that also runs long on a phone',
            actionLabel: 'Retry now',
            onAction: () {},
            onDismiss: () {},
          ),
        ),
      ),
    ));
    expect(t.takeException(), isNull);
  });

  testWidgets('a null tone is neutral and uses the ink title', (t) async {
    await pumpBond(t, const BondBanner(title: 'Plain', tone: null));
    final style = t.widget<Text>(find.text('Plain')).style!;
    expect(style.color, BondTokens.fallback.ink);
  });
}
