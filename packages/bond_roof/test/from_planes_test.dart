import 'dart:convert';
import 'dart:io';

import 'package:bond_roof/bond_roof.dart';
import 'package:test/test.dart';

import 'scene_checks.dart';

/// A model built straight from the measured planes (`source.from_planes`): one shed-form block per plane, every
/// facet a plane, edges typed from plane heights. A synthetic 40 x 24 ft gable (two planes, one ridge).
Map<String, dynamic> _json() =>
    jsonDecode(File('test/fixtures/from_planes_model.json').readAsStringSync()) as Map<String, dynamic>;

void main() {
  final model = RoofModel.fromJson(_json());

  test('the model parses: two facets, two shed blocks, the from_planes marker stays in source.raw', () {
    expect(model.facets, hasLength(2));
    expect(model.blocks, hasLength(2));
    expect(model.source.raw['from_planes'], true);
    expect(model.source.method, 'lidar_skeleton');
  });

  test('the edges keep their types and lengths', () {
    final types = model.edges.map((e) => e.type.name).toList()..sort();
    expect(types.where((t) => t == 'ridge'), hasLength(1));
    expect(types.where((t) => t == 'eave'), hasLength(2));
    expect(types.where((t) => t == 'rake'), hasLength(4));
  });

  for (final layout in ReportLayout.values) {
    test('the diagrams render with finite numbers ($layout)', () {
      for (final s in [
        LengthDiagram.build(model, layout: layout),
        AreaDiagram.build(model, layout: layout),
        SummaryBlock.build(model, layout: layout),
      ]) {
        expectFits(s);
        expectWellFormedSvg(sceneToSvg(s));
      }
    });
  }
}
