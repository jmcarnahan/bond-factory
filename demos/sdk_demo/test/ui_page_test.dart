import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/pages/ui_page.dart';
import 'package:sdk_demo/src/theme.dart';

/// One finder per bond_ui widget the page must show.
final Map<String, Finder> _everyWidget = {
  'BondActionRow': find.byType(BondActionRow),
  'BondAvatar': find.byType(BondAvatar),
  'BondBanner': find.byType(BondBanner),
  'BondButton': find.byType(BondButton),
  'BondCard': find.byType(BondCard),
  'BondChip': find.byType(BondChip),
  'BondConfirm': find.byType(BondConfirm),
  'BondDashedBorder': find.byType(BondDashedBorder),
  'BondDateField': find.byType(BondDateField),
  'BondIconButton': find.byType(BondIconButton),
  'BondInlineField': find.byType(BondInlineField),
  'BondListRow': find.byType(BondListRow),
  'BondPhoto': find.byType(BondPhoto),
  'BondPressable': find.byType(BondPressable),
  'BondSegmented': find.byType(BondSegmented<String>),
  'BondSelect': find.byType(BondSelect<String>),
  'BondStatusChip': find.byType(BondStatusChip),
  'BondTextField': find.byType(BondTextField),
  'BondSearchField': find.byType(BondSearchField),
  'BondTimeField': find.byType(BondTimeField),
  'BondAccountCard': find.byType(BondAccountCard),
  'BondBottomNav': find.byType(BondBottomNav),
  'BondNavTile': find.byType(BondNavTile),
  'BondRailCard': find.byType(BondRailCard),
  'BondRightRail': find.byType(BondRightRail),
  'BondSideNav': find.byType(BondSideNav),
  'BondDeactivated': find.byType(BondDeactivated),
  'BondEmailSignIn': find.byType(BondEmailSignIn),
  'BondGoogleSignInButton': find.byType(BondGoogleSignInButton),
  'BondLogoMark': find.byType(BondLogoMark),
  'BondMessagePreview': find.byType(BondMessagePreview),
  'BondPageHeader': find.byType(BondPageHeader),
  'BondPersonChip': find.byType(BondPersonChip),
  'BondStaleBanner': find.byType(BondStaleBanner),
  'BondStartupFailed': find.byType(BondStartupFailed),
  'BondEmptyState': find.byType(BondEmptyState),
  'BondLoadingState': find.byType(BondLoadingState),
  'BondErrorState': find.byType(BondErrorState),
  'BondTable': find.byType(BondTable),
  'BondTabs': find.byType(BondTabs),
  'BondTimelineList': find.byType(BondTimelineList),
};

Future<void> _pumpPage(WidgetTester t) => pumpApp(t, const UiPage(), theme: buildDemoTheme());

/// Scrolls the page (the outermost scrollable) until [f] exists, then brings its first match on screen.
Future<void> _show(WidgetTester t, Finder f) async {
  final position = t.state<ScrollableState>(find.byType(Scrollable).first).position;
  position.jumpTo(0);
  await t.pump();
  for (var i = 0; i < 200 && f.evaluate().isEmpty; i++) {
    position.jumpTo(position.pixels + 300);
    await t.pump();
  }
  expect(f, findsWidgets);
  await t.ensureVisible(f.first);
  await t.pump();
}

Future<void> _walk(WidgetTester t) async {
  for (final entry in _everyWidget.entries) {
    await _show(t, entry.value);
    expect(entry.value, findsWidgets, reason: '${entry.key} is on the page');
  }
  expect(t.takeException(), isNull);
  await expectNoOverlays(t);
}

void main() {
  testWidgets('shows every bond_ui widget at 1280 px without overflow or overlays', (t) async {
    setWideScreen(t);
    await _pumpPage(t);
    await _walk(t);
  });

  testWidgets('shows every bond_ui widget at 390 px without overflow or overlays', (t) async {
    setPhone(t);
    await _pumpPage(t);
    await _walk(t);
  });

  testWidgets('has the three sections and sdk.ui ids for the walked widgets', (t) async {
    setWideScreen(t);
    final sem = t.ensureSemantics();
    await _pumpPage(t);
    for (final id in ['sdk.ui.section-primitives', 'sdk.ui.button', 'sdk.ui.select', 'sdk.ui.confirm']) {
      await _show(t, find.bySemanticsIdentifier(id));
      expect(find.bySemanticsIdentifier(id), findsOneWidget, reason: id);
    }
    await _show(t, find.bySemanticsIdentifier('sdk.ui.section-shell'));
    await _show(t, find.bySemanticsIdentifier('sdk.ui.section-components'));
    sem.dispose();
  });

  testWidgets('the select opens inline and picks an option', (t) async {
    setWideScreen(t);
    await _pumpPage(t);
    await _show(t, find.text('Expanding (opens inline)'));
    expect(find.text('Delta'), findsNothing);
    await t.tap(find.text('Select'));
    await t.pump();
    expect(find.text('Delta'), findsOneWidget);
    await t.tap(find.text('Delta'));
    await t.pump();
    await expectNoOverlays(t);
    expect(find.text('Delta'), findsWidgets);
  });

  testWidgets('the confirm needs two taps and counts one send', (t) async {
    setWideScreen(t);
    await _pumpPage(t);
    await _show(t, find.text('Send (0 sent)'));
    await t.tap(find.text('Send (0 sent)'));
    await t.pump();
    expect(find.text('Confirm'), findsOneWidget);
    expect(find.text('Send (1 sent)'), findsNothing);
    await t.tap(find.text('Confirm'));
    await t.pump();
    await expectNoOverlays(t);
    // The undo window is a 5 s timer; let it end so the test leaves nothing pending.
    await t.pump(const Duration(seconds: 6));
    expect(find.text('Send (1 sent)'), findsOneWidget);
  });

  testWidgets('the date field opens its calendar in the flow around a fixed today', (t) async {
    setWideScreen(t);
    final sem = t.ensureSemantics();
    await _pumpPage(t);
    await _show(t, find.bySemanticsIdentifier('sdk.ui.date-field'));
    await t.tap(find.bySemanticsIdentifier('sdk.ui.date-field'));
    await t.pump();
    final day = find.bySemanticsIdentifier('sdk.ui.date-field-day-2026-03-04');
    expect(day, findsOneWidget);
    await expectNoOverlays(t);
    sem.dispose();
  });

  testWidgets('the chip toggles and the dismissed banner leaves a note', (t) async {
    setWideScreen(t);
    await _pumpPage(t);
    await _show(t, find.text('Open'));
    await t.tap(find.text('Open').first);
    await t.pump();
    final sem = t.ensureSemantics();
    await _show(t, find.text('Heads up'));
    await t.tap(find.bySemanticsIdentifier('sdk.ui.banner-dismiss'));
    await t.pump();
    expect(find.text('Banner dismissed'), findsOneWidget);
    sem.dispose();
  });
}
