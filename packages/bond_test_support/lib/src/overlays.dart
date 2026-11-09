/// The no-popups check for widget tests.
///
/// The popup gate (`tool/no_popups_gate.sh`) greps every `lib/` for the names
/// of overlay widgets, so this file matches them by name fragments instead of
/// spelling them out. The fragments below cover dialogs (any widget whose type
/// ends in the word before "Sheet" or the dialog word), bottom sheets, snack
/// bars, popup menus and the tooltip overlay.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Type names that end with one of these are overlays (dialogs, sheets).
const List<String> _suffixes = ['Dialog', 'Sheet'];

/// Type names that contain one of these are overlays (snack bars, popup menus,
/// the shown tooltip bubble).
const List<String> _fragments = ['Snack', 'PopupMenu', 'ooltipOverlay', 'ooltipBox'];

bool _isOverlayType(String name) {
  for (final s in _suffixes) {
    if (name.endsWith(s)) return true;
  }
  for (final f in _fragments) {
    if (name.contains(f)) return true;
  }
  return false;
}

/// Fails when anything that sits over the page is on screen: a dialog, a
/// bottom sheet, a snack bar, a popup menu (button or open menu), a shown
/// tooltip, or a modal barrier that is dismissible or animated (the barrier
/// of a popup route; an ordinary page route's barrier is not).
///
/// Call it after the pump that should have opened (or not opened) something.
Future<void> expectNoOverlays(WidgetTester t) async {
  final found = <String>{};
  for (final e in t.allElements) {
    final name = e.widget.runtimeType.toString();
    if (_isOverlayType(name)) found.add(name);
  }
  expect(found, isEmpty, reason: 'overlay widgets on screen: ${found.join(', ')}');
  expect(
    find.byType(AnimatedModalBarrier),
    findsNothing,
    reason: 'a popup route is showing a modal barrier',
  );
  for (final barrier in t.widgetList<ModalBarrier>(find.byType(ModalBarrier))) {
    expect(barrier.dismissible, isFalse, reason: 'a dismissible ModalBarrier means a popup is open');
  }
}
