import 'dart:convert';

import 'package:bond_roof/bond_roof.dart';
import 'package:test/test.dart';

import 'support.dart';

Map<String, dynamic> _base() =>
    jsonDecode(jsonEncode(loadBareModels().firstWhere((f) => f.name == 'synthetic_hip').json)) as Map<String, dynamic>;

void main() {
  test('a model that only uses known values has no parse notes', () {
    for (final f in loadFixtures()) {
      expect(RoofModel.fromJson(f.json).parseNotes, isEmpty, reason: f.name);
    }
  });

  test('unknown edge type reads as unspecified and is noted', () {
    final j = _base();
    final edges = j['edges'] as List;
    final id = edges[2]['id'];
    edges[2]['type'] = 'gutter';
    final m = RoofModel.fromJson(j);
    expect(m.edges[2].id, id);
    expect(m.edges[2].type, EdgeType.unspecified);
    expect(m.parseNotes, hasLength(1));
    expect(m.parseNotes.single, allOf(startsWith('edges[2].type'), contains('gutter'), contains('unspecified')));
    expect(m.edges[2].toJson()['type'], 'unspecified');
  });

  test('unknown facet kind is chosen from the pitch', () {
    final j = _base();
    final facets = j['facets'] as List;
    facets[0]['kind'] = 'dome';
    facets[0]['pitch_rise'] = 4.0;
    facets[1]['kind'] = 'barrel';
    facets[1]['pitch_rise'] = 0.0;
    final m = RoofModel.fromJson(j);
    expect(m.facets[0].kind, FacetKind.sloped);
    expect(m.facets[1].kind, FacetKind.flat);
    expect(m.parseNotes, hasLength(2));
    expect(m.parseNotes[0], allOf(startsWith('facets[0].kind'), contains('sloped')));
    expect(m.parseNotes[1], allOf(startsWith('facets[1].kind'), contains('flat')));
  });

  test('unknown block form reads as flat', () {
    final j = _base();
    (j['blocks'] as List)[0]['form'] = 'mansard';
    final m = RoofModel.fromJson(j);
    expect(m.blocks[0].form, BlockForm.flat);
    expect(m.parseNotes.single, allOf(startsWith('blocks[0].form'), contains('mansard')));
  });

  test('unknown lengths_ft key is kept, noted and written back', () {
    final j = _base();
    ((j['totals'] as Map)['lengths_ft'] as Map)['gutter'] = 12.5;
    final m = RoofModel.fromJson(j);
    expect(m.totals.extraLengths, {'gutter': 12.5});
    expect(m.totals.lengthsFt.length, EdgeType.values.length);
    expect(m.parseNotes.single, startsWith('totals.lengths_ft.gutter'));
    expect((m.totals.toJson()['lengths_ft'] as Map)['gutter'], 12.5);
    // Variants ignore the unknown key.
    expect(RoofTotalsVariants.of(m.totals).dripEdgeEaveFt, m.totals.lengthsFt[EdgeType.eave]);
  });

  test('every mapping adds one note, in document order', () {
    final j = _base();
    (j['blocks'] as List)[0]['form'] = 'mansard';
    (j['facets'] as List)[0]['kind'] = 'dome';
    (j['edges'] as List)[0]['type'] = 'gutter';
    (j['edges'] as List)[1]['type'] = 'drain';
    ((j['totals'] as Map)['lengths_ft'] as Map)['gutter'] = 1.0;
    final m = RoofModel.fromJson(j);
    expect([for (final n in m.parseNotes) n.split(':').first],
        ['blocks[0].form', 'facets[0].kind', 'edges[0].type', 'edges[1].type', 'totals.lengths_ft.gutter']);
  });

  test('still throws for structural errors', () {
    final j = _base();
    (j['edges'] as List)[0]['type'] = 7;
    expect(() => RoofModel.fromJson(j), throwsFormatException);
    final k = _base();
    (k['facets'] as List)[0]['polygon'] = [[0.0, 0.0]];
    expect(() => RoofModel.fromJson(k), throwsFormatException);
  });

  test('a tolerant envelope parses and the diagrams still build', () {
    final j = _base();
    (j['edges'] as List)[0]['type'] = 'gutter';
    final m = RoofModel.fromJson(j);
    expect(LengthDiagram.build(m).placedLabels, greaterThan(0));
    expect(RoofMeasurement.parseAny(j).model.parseNotes, hasLength(1));
  });
}
