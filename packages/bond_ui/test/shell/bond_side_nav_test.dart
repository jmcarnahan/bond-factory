import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/shell/bond_side_nav.dart';
import 'package:bond_ui/src/shell/bond_side_nav_item.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../components/kit_host.dart';

const _groups = [
  BondNavGroup(items: [
    BondNavDestination(id: '/home', icon: Icons.home, label: 'Home', semanticsId: 'nav.home'),
    BondNavDestination(id: '/inbox', icon: Icons.inbox, label: 'Inbox', count: 3, semanticsId: 'nav.inbox'),
  ]),
  BondNavGroup(label: 'Manage', collapsible: true, semanticsId: 'nav.manage', items: [
    BondNavDestination(id: '/people', icon: Icons.people, label: 'People', semanticsId: 'nav.people'),
  ]),
];

Widget _nav(String? selected, ValueChanged<String> onSelected, {bool rail = false}) => Align(
      alignment: Alignment.centerLeft,
      child: BondSideNav(groups: _groups, selectedId: selected, onSelected: onSelected, rail: rail),
    );

Color? _fillOf(WidgetTester t, String label) {
  final material = t.widget<Material>(find.ancestor(of: find.text(label), matching: find.byType(Material)).first);
  return material.color;
}

void main() {
  testWidgets('highlights the selected id and reports taps', (t) async {
    setWideScreen(t);
    final handle = t.ensureSemantics();
    String? tapped;
    String selected = '/home';
    await pumpKit(t, StatefulBuilder(builder: (c, set) => _nav(selected, (id) => set(() {
          tapped = id;
          selected = id;
        }))));
    expect(_fillOf(t, 'Home'), BondTokens.fallback.ground);
    expect(_fillOf(t, 'Inbox'), isNot(BondTokens.fallback.ground));
    expect(byId('nav.inbox'), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
    await t.tap(find.text('Inbox'));
    await t.pump();
    expect(tapped, '/inbox');
    expect(_fillOf(t, 'Inbox'), BondTokens.fallback.ground);
    expect(_fillOf(t, 'Home'), isNot(BondTokens.fallback.ground));
    await expectNoOverlays(t);
    handle.dispose();
  });

  testWidgets('collapsible group folds inline', (t) async {
    setWideScreen(t);
    await pumpKit(t, _nav(null, (_) {}));
    expect(find.text('People'), findsOneWidget);
    await t.tap(find.text('Manage'));
    await t.pump();
    expect(find.text('People'), findsNothing);
    await t.tap(find.text('Manage'));
    await t.pump();
    expect(find.text('People'), findsOneWidget);
    await expectNoOverlays(t);
  });

  testWidgets('folded state follows the group, not its index', (t) async {
    setWideScreen(t);
    const manage = BondNavGroup(label: 'Manage', collapsible: true, startsExpanded: false, semanticsId: 'nav.manage', items: [
      BondNavDestination(id: '/people', icon: Icons.people, label: 'People'),
    ]);
    const extra = BondNavGroup(label: 'Admin', collapsible: true, semanticsId: 'nav.admin', items: [
      BondNavDestination(id: '/audit', icon: Icons.fact_check, label: 'Audit'),
    ]);
    late StateSetter rebuild;
    var groups = const [manage];
    await pumpKit(
      t,
      StatefulBuilder(builder: (c, set) {
        rebuild = set;
        return Align(
          alignment: Alignment.centerLeft,
          child: BondSideNav(groups: groups, selectedId: null, onSelected: (_) {}),
        );
      }),
    );
    expect(find.text('People'), findsNothing);
    rebuild(() => groups = const [extra, manage]);
    await t.pump();
    expect(find.text('Audit'), findsOneWidget);
    expect(find.text('People'), findsNothing);
    await t.tap(find.text('Manage'));
    await t.pump();
    expect(find.text('People'), findsOneWidget);
    expect(find.text('Audit'), findsOneWidget);
    await expectNoOverlays(t);
  });

  testWidgets('selecting an item inside a folded group opens it', (t) async {
    setWideScreen(t);
    const manage = BondNavGroup(label: 'Manage', collapsible: true, startsExpanded: false, items: [
      BondNavDestination(id: '/people', icon: Icons.people, label: 'People'),
    ]);
    String? selected;
    late StateSetter rebuild;
    await pumpKit(
      t,
      StatefulBuilder(builder: (c, set) {
        rebuild = set;
        return Align(
          alignment: Alignment.centerLeft,
          child: BondSideNav(groups: const [manage], selectedId: selected, onSelected: (_) {}),
        );
      }),
    );
    expect(find.text('People'), findsNothing);
    rebuild(() => selected = '/people');
    await t.pump();
    expect(find.text('People'), findsOneWidget);
    await expectNoOverlays(t);
  });

  testWidgets('rail mode is narrow, icons only', (t) async {
    setWideScreen(t);
    await pumpKit(t, _nav('/home', (_) {}, rail: true));
    expect(t.getSize(find.byType(BondSideNav)).width, 72);
    expect(find.text('Inbox'), findsNothing);
    expect(find.byIcon(Icons.inbox), findsOneWidget);
    expect(t.takeException(), isNull);
  });

  testWidgets('open user card scrolls with the nav', (t) async {
    setWideScreen(t, size: const Size(1280, 300));
    await pumpKit(
      t,
      Align(
        alignment: Alignment.centerLeft,
        child: BondSideNav(
          groups: _groups,
          selectedId: null,
          onSelected: (_) {},
          userCard: const SizedBox(height: 200, child: Text('card')),
          userCardExpanded: true,
        ),
      ),
    );
    await t.pump();
    expect(find.byKey(const ValueKey('bond-side-nav-whole-scroll')), findsOneWidget);
    expect(t.takeException(), isNull);
  });
}
