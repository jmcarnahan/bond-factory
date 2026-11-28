import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:bond_roof/bond_roof.dart';
import 'package:bond_roof_ui/bond_roof_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';

/// The hand-written 0.6 sample envelope (no real address or geometry).
RoofMeasurement _sample() => RoofMeasurement.parseAny(
    jsonDecode(File('../../fixtures/roof_engine/roof_measurement_0.6_sample.json').readAsStringSync()) as Map<String, dynamic>);

/// An envelope of the old block shape (0.2): it opens, and shows less.
RoofMeasurement _old() => RoofMeasurement.parseAny(
    jsonDecode(File('../../fixtures/roof_measurement_0.2_pass.json').readAsStringSync()) as Map<String, dynamic>);

Widget _host(Widget child) => MaterialApp(home: Scaffold(body: child));

Future<void> _size(WidgetTester tester, double w, double h) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = Size(w, h);
  addTearDown(tester.view.reset);
}

Offset _centreOf(Scene s, String id, Size box) {
  final r = s.regions.firstWhere((r) => r.id == id);
  final cx = r.pts.map((p) => p.x).reduce((a, b) => a + b) / r.pts.length;
  final cy = r.pts.map((p) => p.y).reduce((a, b) => a + b) / r.pts.length;
  final f = sceneFit(s, box, BoxFit.contain);
  return Offset(f.dx + cx * f.k, f.dy + cy * f.k);
}

Future<List<int>> _pixels(WidgetTester tester, GlobalKey key) async {
  late ui.Image img;
  await tester.runAsync(() async {
    final b = key.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    img = await b.toImage();
  });
  late ByteData data;
  await tester.runAsync(() async => data = (await img.toByteData())!);
  return [for (var i = 0; i < data.lengthInBytes; i += 4) data.getUint32(i)];
}

void main() {
  group('RoofTotalsTable', () {
    testWidgets('lists the totals the sample has, in the owner\'s words, and nothing it does not have', (tester) async {
      await tester.pumpWidget(_host(SingleChildScrollView(child: RoofTotalsTable(_sample()))));
      for (final t in [
        'Total area', 'Pitched roofing', 'Flat roofing', 'Pitch', 'Eaves', 'Rakes', 'Flat roof edges', 'Exposed edges inside the roof',
        'Eave + rake', 'Ridges', 'Ridge + hip', 'Sidewall flashing', 'Headwall flashing', 'Transitions', 'Chimneys', 'Facets',
        'Confidence', 'Generated',
      ]) {
        expect(find.text(t), findsOneWidget, reason: t);
      }
      for (final t in ['Hips', 'Valleys', 'Level changes', 'Verification', 'Drip edge (eave only)', 'Ridge cap (ridge + hip)']) {
        expect(find.text(t), findsNothing, reason: t);
      }
      expect(find.textContaining('14.18 squares'), findsOneWidget);
      expect(find.text('6/12 (5.9)'), findsOneWidget);
    });

    testWidgets('each row carries its own number', (tester) async {
      await tester.pumpWidget(_host(SingleChildScrollView(child: RoofTotalsTable(_sample()))));
      String valueOf(String label) {
        final row = find.ancestor(of: find.text(label), matching: find.byType(Row)).first;
        return tester.widgetList<Text>(find.descendant(of: row, matching: find.byType(Text))).map((t) => t.data).join(' ');
      }

      expect(valueOf('Sidewall flashing'), contains('12ft 0in'));
      expect(valueOf('Headwall flashing'), contains('9ft 0in'));
      expect(valueOf('Chimneys'), contains('1'));
      expect(valueOf('Eave + rake'), contains(feetInches(_sample().totals.eaveRakeFt!)));
    });

    testWidgets('the row texts come from the labels', (tester) async {
      final l = const RoofLabels().copyWith({
        'totals_sidewall': 'Tapajuntas lateral',
        'totals_headwall': 'Tapajuntas frontal',
        'totals_chimneys': 'Chimeneas',
        'totals_eave_rake': 'Alero + hastial',
      });
      await tester.pumpWidget(_host(SingleChildScrollView(child: RoofTotalsTable(_sample(), labels: l))));
      for (final t in ['Tapajuntas lateral', 'Tapajuntas frontal', 'Chimeneas', 'Alero + hastial']) {
        expect(find.text(t), findsOneWidget, reason: t);
      }
      expect(find.text('Chimneys'), findsNothing);
    });

    testWidgets('an old envelope opens and shows only what its facets and edges give: no verdict, no flashing it lacks', (tester) async {
      await tester.pumpWidget(_host(SingleChildScrollView(child: RoofTotalsTable(_old()))));
      expect(find.text('Total area'), findsOneWidget);
      expect(find.text('Verification'), findsNothing);
      for (final t in ['Pitched roofing', 'Flat roofing', 'Chimneys', 'Sidewall flashing', 'Headwall flashing']) {
        expect(find.text(t), findsNothing, reason: t);
      }
    });
  });

  group('RoofDiagramView', () {
    final scene = AreaDiagram.build(_sample().model);
    const box = Size(800, 500);

    testWidgets('a tap on a facet reports its id; a tap on no facet reports nothing', (tester) async {
      await _size(tester, 800, 500);
      final taps = <String>[];
      await tester.pumpWidget(_host(SizedBox(width: 800, height: 500, child: RoofDiagramView(scene, onFacetTap: taps.add))));
      final origin = tester.getTopLeft(find.byType(RoofDiagramView));
      for (final id in ['f1', 'f2', 'f3']) {
        await tester.tapAt(origin + _centreOf(scene, id, box));
      }
      expect(taps, ['f1', 'f2', 'f3']);
      await tester.tapAt(origin + const Offset(2, 2));
      expect(taps, hasLength(3));
      // The package draws nothing over the page: no dialog, sheet or barrier.
      expect(find.byType(Dialog), findsNothing);
      expect(find.byType(BottomSheet), findsNothing);
      expect(find.byType(ModalBarrier).evaluate().where((e) => (e.widget as ModalBarrier).dismissible == true), isEmpty);
    });

    testWidgets('without a callback there is no gesture layer', (tester) async {
      await tester.pumpWidget(_host(SizedBox(width: 800, height: 500, child: RoofDiagramView(scene))));
      expect(find.descendant(of: find.byType(RoofDiagramView), matching: find.byType(GestureDetector)), findsNothing);
    });

    test('facetIdAt follows the same fit as the painter, for contain and cover', () {
      for (final fit in [BoxFit.contain, BoxFit.cover]) {
        const size = Size(500, 900);
        final f = sceneFit(scene, size, fit);
        final r = scene.regions.firstWhere((r) => r.id == 'f2');
        final c = (x: r.pts.map((p) => p.x).reduce((a, b) => a + b) / 4, y: r.pts.map((p) => p.y).reduce((a, b) => a + b) / 4);
        expect(facetIdAt(scene, size, Offset(f.dx + c.x * f.k, f.dy + c.y * f.k), fit: fit), 'f2');
      }
      expect(facetIdAt(scene, Size.zero, Offset.zero), isNull);
    });

    testWidgets('flat facets are painted hatched, pitched ones are not', (tester) async {
      await _size(tester, 800, 500);
      // The length diagram has no text inside the facets, so the only marks there are the hatch.
      final plan = LengthDiagram.build(_sample().model);
      final key = GlobalKey();
      await tester.pumpWidget(_host(Center(
        child: RepaintBoundary(key: key, child: SizedBox(width: 800, height: 500, child: RoofDiagramView(plan))),
      )));
      final px = await _pixels(tester, key);
      int luma(int rgba) => ((rgba >> 24) & 0xFF) + ((rgba >> 16) & 0xFF) + ((rgba >> 8) & 0xFF);
      // Pixels clearly darker than the fill, in the middle of a facet (8 px in from its outline).
      ({int dark, int total}) probe(String id) {
        final r = plan.regions.firstWhere((r) => r.id == id);
        final fit = sceneFit(plan, const Size(800, 500), BoxFit.contain);
        final xs = r.pts.map((p) => fit.dx + p.x * fit.k), ys = r.pts.map((p) => fit.dy + p.y * fit.k);
        final x0 = xs.reduce((a, b) => a < b ? a : b).ceil() + 8, x1 = xs.reduce((a, b) => a > b ? a : b).floor() - 8;
        final y0 = ys.reduce((a, b) => a < b ? a : b).ceil() + 8, y1 = ys.reduce((a, b) => a > b ? a : b).floor() - 8;
        final fill = px[((y0 + y1) ~/ 2) * 800 + x0];
        var dark = 0, total = 0;
        for (var y = y0; y < y1; y++) {
          for (var x = x0; x < x1; x++) {
            total++;
            if (luma(px[y * 800 + x]) < luma(fill) - 30) dark++;
          }
        }
        return (dark: dark, total: total);
      }

      final flat = probe('f4');
      final pitched = probe('f1');
      expect(flat.total, greaterThan(1000));
      expect(flat.dark / flat.total, greaterThan(0.05), reason: 'hatch lines across the flat facet');
      // Edge labels may sit inside a pitched facet; the hatch would darken a quarter of it.
      expect(pitched.dark / pitched.total, lessThan(0.03), reason: 'a pitched facet is a plain fill');
      // The flat facet uses the neutral fill, the pitched one the warm fill.
      final fit = sceneFit(plan, const Size(800, 500), BoxFit.contain);
      Color at(String id) {
        final r = plan.regions.firstWhere((r) => r.id == id);
        // A point 6 px inside the facet's left-middle edge region.
        final x = (fit.dx + (r.pts.map((p) => p.x).reduce((a, b) => a < b ? a : b)) * fit.k).round() + 10;
        final y = (fit.dy + (r.pts.map((p) => p.y).reduce((a, b) => a + b) / r.pts.length * fit.k)).round();
        final v = px[y * 800 + x];
        return Color.fromARGB(255, (v >> 24) & 0xFF, (v >> 16) & 0xFF, (v >> 8) & 0xFF);
      }

      expect(at('f1'), Color(DiagramStyle.report.slopedFill));
    });
  });

  group('RoofReportStrip', () {
    testWidgets('passes onFacetTap to the diagrams and shows the flat and pitched rows', (tester) async {
      await _size(tester, 1280, 4000);
      final taps = <String>[];
      await tester.pumpWidget(_host(SingleChildScrollView(child: RoofReportStrip(measurement: _sample(), onFacetTap: taps.add))));
      await tester.pump();
      expect(tester.takeException(), isNull);
      expect(find.text('Pitched roofing'), findsOneWidget);
      expect(find.text('Sidewall flashing'), findsOneWidget);
      final views = find.byType(RoofDiagramView);
      expect(views, findsNWidgets(3));
      final area = tester.widget<RoofDiagramView>(views.at(1));
      final box = tester.getSize(views.at(1));
      await tester.tapAt(tester.getTopLeft(views.at(1)) + _centreOf(area.scene, 'f3', box));
      expect(taps, ['f3']);
      // The summary page has no facets: a tap there reports nothing.
      await tester.tapAt(tester.getCenter(views.at(2)));
      expect(taps, ['f3']);
    });

    testWidgets('without onFacetTap the strip is unchanged: no gesture layer in the diagrams', (tester) async {
      await _size(tester, 1280, 4000);
      await tester.pumpWidget(_host(SingleChildScrollView(child: RoofReportStrip(measurement: _old()))));
      await tester.pump();
      expect(find.descendant(of: find.byType(RoofDiagramView), matching: find.byType(GestureDetector)), findsNothing);
      expect(find.text('Pitched roofing'), findsNothing);
    });
  });
}
