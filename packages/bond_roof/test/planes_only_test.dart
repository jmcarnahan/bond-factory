import 'dart:convert';
import 'dart:io';

import 'package:bond_roof/bond_roof.dart';
import 'package:test/test.dart';

import 'scene_checks.dart';

/// A planes-only envelope (fixtures/roof_planes_only): the service could not build the simple roof diagram and
/// returns the measured planes instead. `model.facets`, `model.blocks` and `model.edges` are empty and
/// `model.source.planes_only` is true; the totals carry the planes' surface area and the outline perimeter.
Map<String, dynamic> _json() =>
    jsonDecode(File('../../fixtures/roof_planes_only/roof_measurement_0.3_planes_only.json').readAsStringSync())
        as Map<String, dynamic>;

void main() {
  final json = _json();
  final m = RoofMeasurement.parseAny(json);

  test('the envelope parses: no facets, no edges, the plane totals as the area', () {
    expect(m.model.facets, isEmpty);
    expect(m.model.edges, isEmpty);
    expect(m.model.blocks, isEmpty);
    expect(m.totals.facets, 0);
    expect(m.totals.areaSqft, 1012.0);
    expect(m.totals.eaveFt, 128.0);
    expect(m.warningCodes, ['model_failed']);
    expect(m.verification.verdict, RoofVerdict.unverified);
    expect(m.model.source.method, 'lidar_skeleton');
    expect(m.model.confidence.overall, 'low');
  });

  test('RoofModel.fromJson reads the bare model too, and the planes_only marker stays in source.raw', () {
    final model = RoofModel.fromJson(json['model'] as Map<String, dynamic>);
    expect(model.facets, isEmpty);
    expect(model.source.raw['planes_only'], true);
    expect(model.extra['planes'], isA<List<dynamic>>());
  });

  for (final layout in ReportLayout.values) {
    group('diagram builders on zero facets ($layout)', () {
      test('LengthDiagram.build renders without throwing and with finite numbers', () {
        final s = LengthDiagram.build(m.model, layout: layout);
        expectFits(s);
        expectWellFormedSvg(sceneToSvg(s));
        expect(s.placedLabels + s.hiddenLabels, 0);
      });
      test('AreaDiagram.build renders without throwing and with finite numbers', () {
        final s = AreaDiagram.build(m.model, layout: layout);
        expectFits(s);
        expectWellFormedSvg(sceneToSvg(s));
        expect(s.placedLabels + s.hiddenLabels, 0);
      });
      test('SummaryBlock.build renders without throwing and with finite numbers', () {
        final s = SummaryBlock.build(m.model, layout: layout);
        expectFits(s);
        expectWellFormedSvg(sceneToSvg(s));
      });
    });
  }
}
