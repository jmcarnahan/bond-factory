import 'dart:convert';
import 'dart:io';

import 'package:bond_roof/bond_roof.dart';
import 'package:bond_roof_ui/bond_roof_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

RoofMeasurement _envelope(String verdict) => RoofMeasurement.parseAny(
    jsonDecode(File('../../fixtures/roof_measurement_0.2_$verdict.json').readAsStringSync()) as Map<String, dynamic>);

const _es = {
  'action_print': 'Imprimir',
  'action_save_pdf': 'Guardar PDF',
  'action_share_pdf': 'Compartir PDF',
  'variant_drip_edge_eave': 'Gotero (solo alero)',
  'variant_drip_edge_eave_rake': 'Gotero (alero + hastial)',
  'variant_ridge_cap_ridge': 'Remate de cumbrera (solo cumbrera)',
  'variant_ridge_cap_ridge_hip': 'Remate de cumbrera (cumbrera + limas)',
  'verification': 'Verificación',
  'verdict_adjusted': 'Ajustado tras la revisión',
  'length_caption': 'Diagrama de longitudes',
  'legend_eave': 'Aleros',
};

Widget _host(double width, Widget strip) => MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(child: SizedBox(width: width, child: strip)),
      ),
    );

/// Pumps [strip] at [width]. Overflow and other Flutter errors surface through
/// `tester.takeException()`; callers expect it to be null.
Future<void> _pump(WidgetTester tester, double width, Widget strip) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = Size(width, 4000);
  addTearDown(tester.view.reset);
  await tester.pumpWidget(_host(width, strip));
  await tester.pump();
}

List<Scene> _scenes(WidgetTester tester) => [for (final v in tester.widgetList<RoofDiagramView>(find.byType(RoofDiagramView))) v.scene];

void main() {
  group('RoofReportStrip', () {
    for (final width in [1280.0, 390.0]) {
      testWidgets('renders at $width px without errors, with all three actions and the variant rows', (tester) async {
        final m = _envelope('adjusted');
        await _pump(tester, width, RoofReportStrip(measurement: m));
        expect(tester.takeException(), isNull);
        for (final t in ['Print', 'Save PDF', 'Share PDF']) {
          expect(find.text(t), findsOneWidget, reason: t);
        }
        for (final t in ['Drip edge (eave only)', 'Drip edge (eave + rake)', 'Ridge cap (ridge only)', 'Ridge cap (ridge + hip)']) {
          expect(find.text(t), findsOneWidget, reason: t);
        }
        expect(find.text('Verification'), findsOneWidget);
        expect(find.textContaining('Adjusted after review'), findsOneWidget);
        expect(find.text('Generated'), findsOneWidget);
        expect(find.byType(RoofDiagramView), findsNWidgets(3));
        // No popups of any kind in the tree.
        expect(find.byType(Tooltip), findsNothing);
        expect(find.byType(Dialog), findsNothing);
      });
    }

    testWidgets('width under 600 builds compact (800 x 1000) scenes, wider builds wide scenes', (tester) async {
      final m = _envelope('pass').model;
      await _pump(tester, 390, RoofReportStrip(model: m));
      expect(_scenes(tester).take(2).map((s) => (s.width, s.height)), everyElement((800.0, 1000.0)));
      await _pump(tester, 1280, RoofReportStrip(model: m));
      expect(_scenes(tester).take(2).map((s) => (s.width, s.height)), everyElement((RoofReport.pageWidth, RoofReport.pageHeight)));
    });

    testWidgets('Spanish labels are applied to the strip and its diagrams', (tester) async {
      final m = _envelope('adjusted');
      await _pump(tester, 390, RoofReportStrip(measurement: m, labels: RoofLabels.fromMap(_es)));
      expect(tester.takeException(), isNull);
      for (final t in ['Imprimir', 'Guardar PDF', 'Compartir PDF', 'Gotero (solo alero)', 'Gotero (alero + hastial)',
        'Remate de cumbrera (solo cumbrera)', 'Remate de cumbrera (cumbrera + limas)', 'Verificación']) {
        expect(find.text(t), findsOneWidget, reason: t);
      }
      expect(find.textContaining('Ajustado tras la revisión'), findsOneWidget);
      expect(find.text('Print'), findsNothing);
      expect(find.text('Drip edge (eave only)'), findsNothing);
      // The baked-in scene text follows the labels too.
      final legend = _scenes(tester).first.prims.whereType<TextPrim>().map((t) => t.text);
      expect(legend, contains('Aleros'));
      expect(legend, isNot(contains('Eaves')));
    });

    testWidgets('showActions false hides the action row', (tester) async {
      await _pump(tester, 1280, RoofReportStrip(measurement: _envelope('pass'), showActions: false));
      expect(find.text('Print'), findsNothing);
      expect(find.text('Save PDF'), findsNothing);
      expect(find.text('Share PDF'), findsNothing);
      expect(find.text('Drip edge (eave only)'), findsOneWidget);
    });

    testWidgets('a bare model shows the totals table as not verified', (tester) async {
      final m = _envelope('pass').model;
      await _pump(tester, 1280, RoofReportStrip(model: m));
      expect(find.text('Not verified'), findsOneWidget);
      expect(find.text('Ridge cap (ridge + hip)'), findsOneWidget);
    });

    testWidgets('every verdict has its own text', (tester) async {
      const expected = {
        'pass': 'Verified',
        'adjusted': 'Adjusted after review',
        'fail': 'Failed verification',
        'unverified': 'Not verified',
      };
      for (final e in expected.entries) {
        await _pump(tester, 1280, RoofReportStrip(measurement: _envelope(e.key), showActions: false));
        expect(find.textContaining(e.value), findsOneWidget, reason: e.key);
      }
    });

    testWidgets('scenes are cached per model and labels, and rebuilt when they change', (tester) async {
      final m = _envelope('pass');
      await _pump(tester, 1280, RoofReportStrip(measurement: m));
      final first = _scenes(tester);
      await tester.pumpWidget(_host(1280, RoofReportStrip(measurement: m, filename: 'other.pdf')));
      expect(identical(_scenes(tester).first, first.first), isTrue, reason: 'same model and labels reuse scenes');
      await tester.pumpWidget(_host(1280, RoofReportStrip(measurement: m, labels: RoofLabels.fromMap(_es))));
      expect(identical(_scenes(tester).first, first.first), isFalse, reason: 'labels changed');
      final other = _envelope('fail');
      await tester.pumpWidget(_host(1280, RoofReportStrip(measurement: other)));
      expect(identical(_scenes(tester).first, first.first), isFalse, reason: 'model changed');
    });

    testWidgets('a failing action shows an inline status and calls onStatus', (tester) async {
      final seen = <String>[];
      // The printing plugin is not available in tests: make every call fail.
      const channel = MethodChannel('net.nfet.printing');
      tester.binding.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async => throw PlatformException(code: 'none', message: 'no printer'));
      addTearDown(() => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(channel, null));
      await _pump(tester, 1280, RoofReportStrip(measurement: _envelope('pass'), onStatus: seen.add));
      await tester.tap(find.text('Print'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      expect(seen.first, 'Preparing print view...');
      expect(seen.last, startsWith('Failed:'), reason: seen.join(' | '));
      expect(find.textContaining('Failed:'), findsOneWidget);
      expect(find.byType(Dialog), findsNothing);
    });

    testWidgets('no generated line when the envelope has no timestamp', (tester) async {
      final j = jsonDecode(File('../../fixtures/roof_measurement_0.2_pass.json').readAsStringSync()) as Map<String, dynamic>
        ..remove('generated_at');
      await _pump(tester, 1280, RoofReportStrip(measurement: RoofMeasurement.parseAny(j), showActions: false));
      expect(find.text('Generated'), findsNothing);
      expect(find.text('Verification'), findsOneWidget);
    });

    test('exactly one of model or measurement is required', () {
      expect(() => RoofReportStrip(), throwsAssertionError);
      final m = _envelope('pass');
      expect(() => RoofReportStrip(model: m.model, measurement: m), throwsAssertionError);
    });
  });

  group('RoofTotalsTable', () {
    testWidgets('shows both variants of each pair', (tester) async {
      final m = _envelope('pass');
      await tester.pumpWidget(_host(500, RoofTotalsTable(m)));
      expect(find.text('Drip edge (eave only)'), findsOneWidget);
      expect(find.text('Drip edge (eave + rake)'), findsOneWidget);
      final v = m.totals.variants;
      expect(find.text(feetInches(v.dripEdgeEaveRakeFt)), findsWidgets);
      expect(find.text(feetInches(v.ridgeCapRidgeHipFt)), findsWidgets);
    });
  });

  group('RoofReport', () {
    test('pages: three scenes per layout', () {
      final m = _envelope('pass').model;
      final wide = RoofReport.pages(m);
      final compact = RoofReport.pages(m, layout: ReportLayout.compact);
      expect(wide.length, 3);
      expect(compact.length, 3);
      expect((wide[0].width, wide[0].height), (RoofReport.pageWidth, RoofReport.pageHeight));
      expect((compact[0].width, compact[0].height), (800.0, 1000.0));
      expect(wide[2].title, 'Summary');
    });

    test('pdfBytes builds a PDF with the given labels and font', () async {
      final m = _envelope('pass').model;
      final font = File('assets/fonts/Roboto-Regular.ttf').readAsBytesSync();
      final bytes = await RoofReport.pdfBytes(m, labels: RoofLabels.fromMap(_es), fontTtf: font, title: 'T');
      expect(String.fromCharCodes(bytes.sublist(0, 5)), '%PDF-');
    });
  });
}
