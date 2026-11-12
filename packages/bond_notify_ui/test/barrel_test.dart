import 'package:bond_notify/bond_notify.dart';
import 'package:bond_notify_ui/bond_notify_ui.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('shell widgets build as placeholders', (t) async {
    await t.pumpWidget(
      const Directionality(
        textDirection: TextDirection.ltr,
        child: Column(
          children: [
            BondNoticeList(notices: [Notice(id: 'a')], semanticsPrefix: 'p'),
            BondNoticeRow(notice: Notice(id: 'a'), semanticsId: 'r'),
            BondNoticeBadge(count: 2, semanticsId: 'b'),
          ],
        ),
      ),
    );
    expect(t.takeException(), isNull);
  });
}
