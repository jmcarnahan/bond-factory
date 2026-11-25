import 'dart:convert';
import 'dart:io';

import 'package:bond_roof/bond_roof.dart';
import 'package:test/test.dart';

/// Three 1020 sq ft facets (invented). The first has a 0.6/12 pitch: the totals count it pitched (cut at 0.5/12 by
/// contract) while the engine typed it flat, which is what the drawing hatches.
Map<String, dynamic> _json({bool roofTypes = true}) {
  final j = jsonDecode(File('test/flat_seams/synthetic_flat_two_level.json').readAsStringSync()) as Map<String, dynamic>;
  final m = j['model'] as Map<String, dynamic>;
  final facets = (m['facets'] as List).cast<Map<String, dynamic>>();
  facets[0]['pitch_rise'] = 0.6;
  if (!roofTypes) for (final f in facets) f.remove('roof_type');
  final t = m['totals'] as Map<String, dynamic>;
  t['pitched_area_sqft'] = 1020.0;
  t['flat_area_sqft'] = 2040.0;
  return j;
}

void main() {
  test('with roof types the split follows the hatching: a facet typed flat is flat whatever its pitch', () {
    final m = RoofMeasurement.parseAny(_json()).model;
    expect(m.flatAreaSqftByRoofType, 3060.0);
    expect(m.pitchedAreaSqftByRoofType, 0.0);
    expect(m.totals.flatAreaSqft, 2040.0); // the totals keep their own cut
  });

  test('a mixed split sums only the facets typed flat', () {
    final j = _json();
    final f = ((j['model'] as Map)['facets'] as List).cast<Map<String, dynamic>>();
    f[1]['roof_type'] = 'pitched';
    final m = RoofMeasurement.parseAny(j).model;
    expect(m.flatAreaSqftByRoofType, 2040.0);
    expect(m.pitchedAreaSqftByRoofType, 1020.0);
  });

  test('a legacy model without roof types reads the totals as before', () {
    final m = RoofMeasurement.parseAny(_json(roofTypes: false)).model;
    expect(m.flatAreaSqftByRoofType, 2040.0);
    expect(m.pitchedAreaSqftByRoofType, 1020.0);
  });

  test('pitched is never negative when facets outweigh a smaller total', () {
    final j = _json();
    ((j['model'] as Map)['totals'] as Map)['total_area_sqft'] = 1000.0;
    final m = RoofMeasurement.parseAny(j).model;
    expect(m.flatAreaSqftByRoofType, 3060.0);
    expect(m.pitchedAreaSqftByRoofType, 0.0);
  });

  test('the area diagram header uses the split', () {
    final m = RoofMeasurement.parseAny(_json()).model;
    final texts = [for (final p in AreaDiagram.build(m).prims) if (p is TextPrim) p.text];
    expect(texts.any((s) => s.contains('3,060') || s.contains('3060')), isTrue);
    expect(texts.where((s) => s.contains('2,040') || s.contains('2040')), isEmpty);
  });
}
