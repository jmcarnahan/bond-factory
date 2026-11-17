import 'dart:convert';
import 'dart:io';

import 'package:bond_roof/bond_roof.dart';
import 'package:bond_roof_ui/bond_roof_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A planes-only envelope: no facets, no edges (see packages/bond_roof/test/planes_only_test.dart).
RoofMeasurement _planesOnly() => RoofMeasurement.parseAny(
    jsonDecode(File('../../fixtures/roof_planes_only/roof_measurement_0.3_planes_only.json').readAsStringSync())
        as Map<String, dynamic>);

void main() {
  test('RoofReport.pages builds the three scenes without throwing on zero facets, in both layouts', () {
    final m = _planesOnly();
    for (final layout in ReportLayout.values) {
      final pages = RoofReport.pages(m.model, layout: layout);
      expect(pages.length, 3);
      for (final s in pages) {
        expect(s.width, greaterThan(0));
        expect(s.height, greaterThan(0));
        expect(s.width.isFinite && s.height.isFinite, isTrue);
      }
    }
  });

  for (final width in [1280.0, 390.0]) {
    testWidgets('RoofReportStrip renders a planes-only measurement at $width px without errors', (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = Size(width, 4000);
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: SingleChildScrollView(child: SizedBox(width: width, child: RoofReportStrip(measurement: _planesOnly())))),
      ));
      await tester.pump();
      expect(tester.takeException(), isNull);
      expect(find.byType(RoofDiagramView), findsWidgets);
    });
  }
}
