import 'dart:convert';
import 'dart:io';

import 'package:bond_roof/bond_roof.dart';
import 'package:test/test.dart';

import 'support.dart';

/// An all-flat roof with two levels (invented geometry): three flat facets, two flat_seam edges, a 24 ft level change with a
/// 5 ft jump and a 10 ft one with a 1.5 ft jump.
Map<String, dynamic> _json() =>
    jsonDecode(File('test/flat_seams/synthetic_flat_two_level.json').readAsStringSync()) as Map<String, dynamic>;

List<String> _texts(Scene s) => [for (final p in s.prims) if (p is TextPrim) p.text];

void main() {
  const st = DiagramStyle.report;
  for (final layout in ReportLayout.values) {
    group('all-flat two-level roof ($layout)', () {
      final measurement = RoofMeasurement.parseAny(_json());
      final model = measurement.model;
      final scene = LengthDiagram.build(model, layout: layout);

      test('the fixture has 3 flat facets, 2 seams and 2 level changes', () {
        expect(model.facets.length, 3);
        expect(model.facets.every((f) => f.isFlatRoofType), isTrue);
        expect(model.edges.where((e) => e.type == EdgeType.flatSeam), hasLength(2));
        expect(model.edges.where((e) => e.type == EdgeType.levelChange).map((e) => e.lengthFt), [24.0, 10.0]);
      });

      test('seams are drawn thin and dark, never labelled, never in the legend or totals', () {
        final seams = scene.prims.whereType<LinePrim>().where((p) => p.color == st.colorOf(EdgeType.flatSeam)).toList();
        expect(seams, hasLength(2));
        final eaves = scene.prims.whereType<LinePrim>().where((p) => p.color == st.colorOf(EdgeType.flatEdge));
        expect(seams.first.width, lessThan(eaves.first.width));
        expect(st.colorOf(EdgeType.flatSeam), 0xFF5A5A5A);
        expect(_texts(scene), isNot(contains(const RoofLabels().legendFlatSeam)));
        expect(model.totals.lengthsFt[EdgeType.flatSeam] ?? 0, 0);
        expect(RoofTotals.recompute(model.facets, model.edges).lengthsFt[EdgeType.flatSeam], 0);
        expect(model.toJson()['totals']['lengths_ft'], isNot(contains('flat_seam')));
      });

      test('flat facets are outlined in the seam colour, 1.2 px', () {
        final outlines = scene.prims.whereType<PolyPrim>().where((p) => p.fill == null && p.stroke == st.colorOf(EdgeType.flatSeam));
        expect(outlines, hasLength(3));
        for (final p in outlines) {
          expect(p.width, lessThan(2));
        }
      });

      test('level changes keep their length; a 3 ft jump or more adds the step', () {
        final t = _texts(scene);
        expect(t, contains('24, 5 ft step'));
        expect(t, contains('10'));
        expect(t.where((x) => x.contains('step')), ['24, 5 ft step']);
      });

      test('Spanish labels give the same shape (when the longer label has room)', () {
        final es = RoofLabels.fromMap({'level_change_step': '{len}, escalón de {jump}', 'unit_ft': 'pies'});
        expect(_texts(LengthDiagram.build(model, layout: layout, labels: es)), contains('24, escalón de 5 pies'));
      }, skip: layout == ReportLayout.compact ? 'the compact page has no room for the longer label' : false);
    });
  }

  test('a level change with no jump, or a jump under 3 ft, shows its length only', () {
    final j = _json();
    final edges = (j['model'] as Map)['edges'] as List;
    for (final e in edges) {
      if (e['type'] == 'level_change') e.remove('jump_ft');
    }
    final t = _texts(LengthDiagram.build(RoofMeasurement.parseAny(j).model));
    expect(t, containsAll(['24', '10']));
    expect(t.where((x) => x.contains('step')), isEmpty);
  });

  test('an unknown edge type does not crash the painter or the totals', () {
    final j = _json();
    ((j['model'] as Map)['edges'] as List).add({
      'id': 'ex', 'type': 'future_kind', 'points': [[0, 0], [5, 0]], 'length_ft': 5.0, 'facets': ['f1'],
    });
    final m = RoofMeasurement.parseAny(j).model;
    expect(() => sceneToSvg(LengthDiagram.build(m)), returnsNormally);
    expect(() => sceneToSvg(AreaDiagram.build(m)), returnsNormally);
  });

  test('a model without flat_seam edges draws no seam-coloured line', () {
    final j = _json();
    final edges = (j['model'] as Map)['edges'] as List;
    edges.removeWhere((e) => e['type'] == 'flat_seam');
    final s = LengthDiagram.build(RoofMeasurement.parseAny(j).model);
    expect(s.prims.whereType<LinePrim>().where((p) => p.color == st.colorOf(EdgeType.flatSeam)), isEmpty);
  });

  test('the 0.6 sample parses with flat_share, no notes', () {
    final j = sampleJson();
    final m = RoofMeasurement.parseAny(j);
    final raw = ((j['model'] as Map)['quality'] as Map)['flat_share'];
    expect(raw, isNotNull);
    expect(m.model.quality!.flatShare, (raw as num).toDouble());
    expect(m.model.parseNotes, isEmpty);
  });
}
