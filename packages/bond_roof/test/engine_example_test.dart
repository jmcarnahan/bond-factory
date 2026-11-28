import 'dart:convert';

import 'package:bond_roof/bond_roof.dart';
import 'package:test/test.dart';

import 'scene_checks.dart';
import 'support.dart';

/// The generated 0.7 example (fixtures/roof_engine/roof_measurement_0.7_engine.json): what the engine really writes, on a
/// synthetic two-level roof with a chimney, a lantern and a unit.
void main() {
  final j = engineJson();
  final m = RoofMeasurement.parseAny(j);
  final model = m.model;

  test('every totals key, edge type and object kind in it is one the reader knows; nothing is mapped or noted', () {
    expect(unknownEnvelopeKeys(j), isEmpty);
    expect(model.parseNotes, isEmpty);
    expect(m.pipelineVersion, startsWith('0.7'));
    expect(m.methodUsed, 'planes');
  });

  test('the envelope totals are the 27 contract keys and model.totals carries the same values', () {
    expect(m.totals.toJson().keys.toSet(), RoofEngineTotals.knownKeys.toSet());
    expect(model.totals.engine, m.totals);
  });

  test('objects: a chimney, a lantern and a unit with closed-ring polygons that round-trip', () {
    expect(model.objects.map((o) => o.kind).toSet(), {ObjectKind.chimney, ObjectKind.lantern, ObjectKind.unit});
    for (final o in model.objects) {
      expect(o.polygon, isNotNull);
      expect(o.returns, isNotNull);
      expect(RoofObject.fromJson(o.toJson(), 'o').polygon, o.polygon);
    }
  });

  test('a step edge carries jump and the upper facet, and writes them back', () {
    final step = model.edges.firstWhere((e) => e.type == EdgeType.stepFlashing);
    expect(step.jumpFt, isNotNull);
    expect(step.upper, isNotNull);
    expect(model.facets.map((f) => f.id), contains(step.upper));
    final back = RoofModel.fromJson(jsonDecode(jsonEncode(model.toJson())) as Map<String, dynamic>);
    expect(back.edges.firstWhere((e) => e.id == step.id).upper, step.upper);
  });

  test('exposed edges follow the contract: sidewall + headwall + lantern perimeters, from its own edges', () {
    double sum(EdgeType t) => model.edges.where((e) => e.type == t).fold(0.0, (a, e) => a + e.lengthFt);
    final lanterns = model.objects.where((o) => o.kind == ObjectKind.lantern).fold(0.0, (a, o) => a + o.perimeterFt);
    expect(m.totals.exposedEdgeFt, closeTo(sum(EdgeType.stepFlashing) + sum(EdgeType.wallFlashing) + lanterns, 0.1));
  });

  test('quality keys the engine adds survive (roof_part_missed_sqft)', () {
    expect(model.quality!.raw, contains('roof_part_missed_sqft'));
    expect(jsonEncode(model.toJson()['quality']), jsonEncode((j['model'] as Map)['quality']));
  });

  for (final layout in ReportLayout.values) {
    test('the three scenes draw it (${layout.name}): sidewall line and label, chimney and lantern marks, pitch label', () {
      final len = LengthDiagram.build(model, layout: layout);
      final area = AreaDiagram.build(model, layout: layout);
      final sum = SummaryBlock.build(model, layout: layout);
      for (final s in [len, area, sum]) {
        expectFits(s);
        expectWellFormedSvg(sceneToSvg(s));
      }
      final t = textsOf(len);
      bool has(String name) => t.any((x) => x.startsWith(name.length > 8 ? name.substring(0, 8) : name)); // the compact legend may ellipsize
      expect([has('Sidewall flashing'), has('Chimney'), has('Roof lantern')], everyElement(isTrue));
      expect(t.any((x) => x.startsWith('Headwall')), isFalse, reason: 'the roof has none');
      // The step is 2 ft (under 3): its label is its length only.
      expect(model.edges.firstWhere((e) => e.type == EdgeType.stepFlashing).jumpFt, lessThan(3));
      expect(t.where((x) => x.contains('step')), isEmpty);
      expect(textsOf(area).any((x) => RegExp(r'^\d+/12( \(\d+\.\d\))?$').hasMatch(x)), isTrue);
      expect(textsOf(sum).any((x) => RegExp(r'^\d+/12').hasMatch(x)), isTrue);
    });
  }

  test('the legend and the totals table list the same rows', () {
    final ids = [for (final r in totalRows(model, const RoofLabels())) r.id];
    expect(ids, containsAll(['step_flashing', 'exposed_edge', 'eave_rake', 'chimneys', 'lanterns']));
    expect(ids, isNot(contains('wall_flashing')));
  });
}
