import 'package:bond_ui/src/primitives/bond_month_grid.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

Widget _grid({
  int firstWeekday = DateTime.sunday,
  Widget Function(BuildContext, DateTime)? dayBuilder,
  void Function(DateTime)? onSelect,
}) =>
    BondMonthGrid(
      visibleMonth: DateTime(2026, 3),
      selected: null,
      today: DateTime(2026, 3, 12),
      onPrevious: () {},
      onNext: () {},
      onSelect: onSelect ?? (_) {},
      isSelectable: (_) => true,
      semanticsId: 'g',
      firstWeekday: firstWeekday,
      dayBuilder: dayBuilder,
    );

List<String?> _initials(WidgetTester t) => t.widgetList<Text>(find.byType(Text)).map((w) => w.data).skip(1).take(7).toList();

void main() {
  for (final phone in [true, false]) {
    testWidgets('default Sunday-first grid, phone=$phone', (t) async {
      await pumpBond(t, _grid(), phone: phone);
      if (!phone) setWideScreen(t);
      expect(_initials(t), ['S', 'M', 'T', 'W', 'T', 'F', 'S']);
      await expectNoOverlays(t);
      expect(t.takeException(), isNull);
    });
  }

  testWidgets('Monday-first puts Sunday last, so 1 March 2026 is in the last column', (t) async {
    await pumpBond(t, _grid(firstWeekday: DateTime.monday));
    expect(_initials(t), ['M', 'T', 'W', 'T', 'F', 'S', 'S']);
    final one = t.getTopLeft(find.text('1').first);
    final two = t.getTopLeft(find.text('2').first);
    expect(one.dx > two.dx, isTrue);
  });

  testWidgets('dayBuilder draws under the day number', (t) async {
    await pumpBond(t, _grid(dayBuilder: (c, d) => d.day == 12 ? const Text('x3') : const SizedBox.shrink()));
    expect(find.text('x3'), findsOneWidget);
    expect(t.getCenter(find.text('x3')).dy > t.getCenter(find.text('12')).dy, isTrue);
    expect(t.takeException(), isNull);
  });

  testWidgets('daySemantics text is appended to the cell label (the marker itself is hidden)', (t) async {
    final sem = t.ensureSemantics();
    await pumpBond(
      t,
      BondMonthGrid(
        visibleMonth: DateTime(2026, 3),
        selected: null,
        today: DateTime(2026, 3, 12),
        onPrevious: () {},
        onNext: () {},
        onSelect: (_) {},
        isSelectable: (_) => true,
        semanticsId: 'g',
        dayBuilder: (c, d) => d.day == 12 ? const Text('3') : const SizedBox.shrink(),
        daySemantics: (d) => d.day == 12 ? '3 overdue' : '',
      ),
    );
    expect(find.bySemanticsLabel('12, 3 overdue'), findsOneWidget);
    expect(find.bySemanticsLabel('13'), findsOneWidget, reason: 'an empty text adds nothing');
    sem.dispose();
  });

  testWidgets('a day tap selects it', (t) async {
    DateTime? picked;
    await pumpBond(t, _grid(onSelect: (d) => picked = d));
    await t.tap(find.text('12'));
    expect(picked, DateTime(2026, 3, 12));
  });
}
