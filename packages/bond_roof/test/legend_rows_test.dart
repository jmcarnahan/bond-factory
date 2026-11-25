import 'dart:convert';
import 'dart:io';

import 'package:bond_roof/bond_roof.dart';
import 'package:test/test.dart';

Map<String, dynamic> _load(String path) => jsonDecode(File(path).readAsStringSync()) as Map<String, dynamic>;

List<String> _texts(Scene s) => [for (final p in s.prims) if (p is TextPrim) p.text];

void main() {
  for (final layout in ReportLayout.values) {
    group('length legend ($layout)', () {
      test('a flat engine model lists only the types with length, no zero rows', () {
        final m = RoofMeasurement.parseAny(_load('test/flat_seams/synthetic_flat_two_level.json')).model;
        final t = _texts(LengthDiagram.build(m, layout: layout));
        expect(t, containsAll([EdgeType.flatEdge, EdgeType.levelChange].map((e) => const RoofLabels().edgeName(e))));
        expect(t, isNot(contains('0ft 0in')));
        expect(t.where((s) => s == const RoofLabels().edgeName(EdgeType.ridge)), isEmpty);
      });

      test('a pitched engine model has no zero legend rows', () {
        final m = RoofMeasurement.parseAny(_load('test/envelope04/synthetic_mixed_0.4.json')).model;
        expect(m.facets.any((f) => f.roofType != null), isTrue);
        expect(_texts(LengthDiagram.build(m, layout: layout)), isNot(contains('0ft 0in')));
      });

      test('a model without roof types keeps all ten legacy rows', () {
        final m = RoofModel.fromJson(_load('test/fixtures/minimal_hip.json'));
        expect(m.facets.every((f) => f.roofType == null), isTrue);
        final t = _texts(LengthDiagram.build(m, layout: layout));
        for (final e in EdgeType.legacy) {
          expect(t, contains(const RoofLabels().edgeName(e)));
        }
      });
    });
  }
}
