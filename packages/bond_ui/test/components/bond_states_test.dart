import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/labels.dart';
import 'package:bond_ui/src/components/bond_states.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'kit_host.dart';

void main() {
  testWidgets('empty state shows title, message and a working action', (t) async {
    setPhone(t);
    final handle = t.ensureSemantics();
    var taps = 0;
    await pumpKit(
      t,
      BondEmptyState(
        title: 'No items',
        message: 'Add one to begin.',
        actionLabel: 'Add item',
        onAction: () => taps++,
        actionSemanticsId: 'empty.add',
      ),
    );
    expect(find.text('No items'), findsOneWidget);
    expect(find.text('Add one to begin.'), findsOneWidget);
    expect(byId('empty.add'), findsOneWidget);
    await t.tap(find.text('Add item'));
    expect(taps, 1);
    await expectNoOverlays(t);
    handle.dispose();
  });

  testWidgets('loading state uses default and custom labels', (t) async {
    await pumpKit(t, const BondLoadingState());
    expect(find.text('Loading'), findsOneWidget);
    await pumpKit(t, const BondLabelsScope(labels: BondLabels(loading: 'Cargando'), child: BondLoadingState()));
    expect(find.text('Cargando'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });

  testWidgets('error state shows message and retry only when given a callback', (t) async {
    final handle = t.ensureSemantics();
    var retries = 0;
    await pumpKit(t, BondErrorState(message: 'Boom', onRetry: () => retries++, semanticsId: 'err.msg'));
    expect(find.text('Boom'), findsOneWidget);
    expect(byId('err.msg'), findsOneWidget);
    await t.tap(find.text('Retry'));
    expect(retries, 1);
    await pumpKit(t, const BondErrorState());
    expect(find.text('Something went wrong'), findsOneWidget);
    expect(find.text('Retry'), findsNothing);
    handle.dispose();
  });
}
