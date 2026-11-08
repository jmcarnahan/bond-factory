import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:bond_roof_ui/bond_roof_ui.dart';
import 'package:bond_roof/bond_roof.dart';

void main() {
  testWidgets('RoofDiagramView paints a hand-built scene', (tester) async {
    const scene = Scene(
      width: 200,
      height: 100,
      background: 0xFFFFFFFF,
      prims: <Prim>[
        LinePrim(a: (x: 10, y: 10), b: (x: 190, y: 10), color: 0xFF2E7D32, width: 2, dashed: false),
        LinePrim(a: (x: 10, y: 90), b: (x: 190, y: 90), color: 0xFF1E88E5, width: 2, dashed: true),
        PolyPrim(
          pts: [(x: 20, y: 20), (x: 180, y: 20), (x: 100, y: 80)],
          fill: 0xFFE3F2FD,
          stroke: 0xFF000000,
          width: 1,
          dashed: true,
        ),
        TextPrim(at: (x: 100, y: 50), text: '12 ft', angleDeg: 30, size: 12, color: 0xFF000000, anchor: TextAnchor.middle, bold: true),
      ],
      hiddenLabels: 0,
      title: 'tiny',
    );
    await tester.pumpWidget(const Directionality(
      textDirection: TextDirection.ltr,
      child: SizedBox(width: 400, height: 300, child: RoofDiagramView(scene)),
    ));
    expect(tester.takeException(), isNull);
    expect(find.byType(RoofDiagramView), findsOneWidget);
  });
}
