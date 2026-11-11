import 'dart:convert';
import 'dart:math' as math;

import 'package:bond_roof/bond_roof.dart';
import 'package:test/test.dart';

import 'support.dart';

Map<String, dynamic> _minimal() => {
      'schema': 'bond.roof_model/0.1',
      'generated_at': '2026-11-07T21:00:00Z',
      'address': {'line1': '1 A St', 'city': 'B', 'state': 'CA', 'zip': '90000', 'formatted': '1 A ST, B, CA'},
      'origin': {'lat': 1.0, 'lng': 2.0},
      'source': {'method': 'manual', 'footprint': {'provider': 'x'}},
      'blocks': [
        {
          'id': 'b1',
          'form': 'flat',
          'polygon': [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]],
          'pitch_rise': 0.0,
          'gable_edges': <int>[],
          'plan_area_sqft': 100.0,
        }
      ],
      'facets': [
        {
          'id': 'f1',
          'block': 'b1',
          'kind': 'flat',
          'polygon': [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]],
          'pitch_rise': 0.0,
          'aspect_deg': null,
          'plan_area_sqft': 100.0,
          'area_sqft': 100.0,
        }
      ],
      'edges': [
        {'id': 'e1', 'type': 'parapet', 'points': [[0.0, 0.0], [10.0, 0.0]], 'length_ft': 10.0, 'facets': ['f1']},
        {'id': 'e2', 'type': 'step_flashing', 'points': [[10.0, 0.0], [10.0, 10.0]], 'length_ft': 10.0, 'facets': ['f1']},
      ],
      'holes': [
        {'id': 'h1', 'kind': 'skylight', 'polygon': [[1.0, 1.0], [2.0, 1.0], [2.0, 2.0]], 'area_sqft': 0.5}
      ],
      'totals': {
        'total_area_sqft': 100.0,
        'pitched_area_sqft': 0.0,
        'flat_area_sqft': 100.0,
        'predominant_pitch_rise': 0.0,
        'predominant_pitch_area_sqft': 100.0,
        'squares': 1.0,
        'lengths_ft': {
          'eave': 0.0, 'rake': 0.0, 'ridge': 0.0, 'hip': 0.0, 'valley': 0.0, 'step_flashing': 10.0,
          'wall_flashing': 0.0, 'parapet': 10.0, 'transition': 0.0, 'unspecified': 0.0,
        },
      },
      'confidence': {'overall': 'low', 'notes': ['n']},
      'warnings': ['w'],
      'debug': {'png': 'x.png'},
    };

/// Round trip through real JSON text so int/double differences cannot hide.
Map<String, dynamic> _roundTrip(Map<String, dynamic> j) =>
    jsonDecode(jsonEncode(RoofModel.fromJson(j).toJson())) as Map<String, dynamic>;

/// Canonical JSON text: object keys sorted recursively.
String _canon(Object? v) => jsonEncode(_sorted(v));

Object? _sorted(Object? v) {
  if (v is Map) {
    final keys = v.keys.map((k) => '$k').toList()..sort();
    return {for (final k in keys) k: _sorted(v[k])};
  }
  if (v is List) return [for (final x in v) _sorted(x)];
  return v;
}

void main() {
  group('round trip', () {
    test('inline minimal model', () {
      final j = _minimal();
      final m = RoofModel.fromJson(j);
      expect(m.edges.first.type, EdgeType.parapet);
      expect(m.edges.last.type, EdgeType.stepFlashing);
      expect(m.facets.single.aspectDeg, isNull);
      expect(m.extra['debug'], {'png': 'x.png'});
      final out = _roundTrip(j);
      // Everything survives: holes, address, confidence, warnings, source, extras.
      expect(_canon(out), _canon(jsonDecode(jsonEncode(j))));
      expect(out['edges'], jsonDecode(jsonEncode(j['edges'])));
      expect(out['facets'], jsonDecode(jsonEncode(j['facets'])));
      expect(out['blocks'], jsonDecode(jsonEncode(j['blocks'])));
      expect(out['totals'], jsonDecode(jsonEncode(j['totals'])));
      expect(out['debug'], j['debug']);
      expect(out['origin'], j['origin']);
      expect(out['source'], jsonDecode(jsonEncode(j['source'])));
      // And it is stable: a second trip changes nothing.
      expect(_roundTrip(out), out);
    });

    final fixtures = loadFixtures();
    test('fixtures found', () => expect(fixtures, isNotEmpty));
    for (final f in fixtures) {
      test('fixture ${f.name}', () {
        final once = _roundTrip(f.json);
        expect(_roundTrip(once), once);
        final m = RoofModel.fromJson(f.json);
        expect(m.facets, isNotEmpty);
        expect(m.edges, isNotEmpty);
        // Content survives: same ids and counts.
        final back = RoofModel.fromJson(once);
        expect([for (final e in back.edges) e.id], [for (final e in m.edges) e.id]);
        expect([for (final e in back.facets) e.areaSqft], [for (final e in m.facets) e.areaSqft]);
      });
    }
  });

  /// Generated models must agree to 0.5 sq ft / 0.05 ft. A hand-digitised ("manual") model
  /// copies printed totals that cannot be reproduced from its facets and edges, so it gets 3
  /// percent on areas and 5 percent on the lengths of eave, hip, ridge, rake and parapet; wall
  /// and step flashing are expected to fall short and are skipped.
  void expectTotalsAgree(RoofModel m) {
    final r = m.recomputeTotals();
    final manual = m.source.method == 'manual';
    double area(double v) => manual ? math.max(0.5, v * 0.03) : 0.5;
    expect(r.totalAreaSqft, closeTo(m.totals.totalAreaSqft, area(r.totalAreaSqft)));
    expect(r.pitchedAreaSqft, closeTo(m.totals.pitchedAreaSqft, area(r.totalAreaSqft)));
    expect(r.flatAreaSqft, closeTo(m.totals.flatAreaSqft, area(r.totalAreaSqft)));
    expect(r.predominantPitchAreaSqft, closeTo(m.totals.predominantPitchAreaSqft, area(r.totalAreaSqft)));
    expect(r.squares, closeTo(m.totals.squares, manual ? 3.0 : 0.005));
    const skippedWhenManual = {EdgeType.wallFlashing, EdgeType.stepFlashing};
    for (final t in EdgeType.values) {
      if (manual && skippedWhenManual.contains(t)) continue;
      final want = m.totals.lengthsFt[t]!;
      expect(r.lengthsFt[t], closeTo(want, manual ? math.max(0.05, want * 0.05) : 0.05), reason: t.json);
    }
  }

  group('recomputeTotals', () {
    for (final f in loadFixtures()) {
      test(f.name, () => expectTotalsAgree(RoofModel.fromJson(f.json)));
    }

    test('manual-source branch: printed totals within 3 percent of the facets', () {
      final j = _minimal(); // manual source, one flat 100 sq ft facet, parapet 10 ft, step flashing 10 ft
      final totals = (j['totals'] as Map<String, dynamic>)
        ..['total_area_sqft'] = 102.0
        ..['flat_area_sqft'] = 102.0
        ..['predominant_pitch_area_sqft'] = 102.0
        ..['squares'] = 1.02;
      (totals['lengths_ft'] as Map<String, dynamic>)
        ..['parapet'] = 10.4
        ..['step_flashing'] = 14.0; // flashing is skipped for manual models
      final m = RoofModel.fromJson(j);
      expect(m.source.method, 'manual');
      expectTotalsAgree(m);
      // The same drift on a generated model is a failure.
      final strict = RoofModel.fromJson(Map.of(j)..['source'] = {'method': 'lidar_skeleton'});
      expect(() => expectTotalsAgree(strict), throwsA(anything));
    });

    test('predominant pitch groups by half pitch and weights the rise', () {
      final j = _minimal();
      j['totals'] = null;
      j['facets'] = [
        for (final (i, r) in [3.9, 4.1, 8.0].indexed)
          {
            'id': 'f$i', 'block': 'b1', 'kind': 'sloped',
            'polygon': [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
            'pitch_rise': r, 'aspect_deg': 0.0, 'plan_area_sqft': 100.0, 'area_sqft': 100.0,
          }
      ];
      final t = RoofModel.fromJson(j).totals; // totals absent -> recomputed
      expect(t.predominantPitchAreaSqft, 200.0);
      expect(t.predominantPitchRise, closeTo(4.0, 1e-9));
      expect(t.pitchedAreaSqft, 300.0);
      expect(t.lengthsFt.length, 10);
    });
  });

  group('predominant pitch is the winning half-pitch bucket', () {
    RoofTotals totalsFor(List<(double, double)> riseAndArea) {
      final j = _minimal();
      j['totals'] = null;
      j['facets'] = [
        for (final (i, ra) in riseAndArea.indexed)
          {
            'id': 'f$i', 'block': 'b1', 'kind': 'sloped',
            'polygon': [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
            'pitch_rise': ra.$1, 'aspect_deg': 0.0, 'plan_area_sqft': ra.$2, 'area_sqft': ra.$2,
          }
      ];
      return RoofModel.fromJson(j).totals;
    }

    test('returns the bucket, not the weighted mean', () {
      final t = totalsFor([(3.9, 100), (4.1, 100)]);
      expect(t.predominantPitchRise, 4.0);
      expect(t.predominantPitchAreaSqft, 200);
    });

    test('4.1 and 4.4 fall in different buckets (4.0 and 4.5)', () {
      final t = totalsFor([(4.1, 150), (4.4, 100)]);
      expect(t.predominantPitchRise, 4.0);
      expect(t.predominantPitchAreaSqft, 150);
      final u = totalsFor([(4.1, 100), (4.4, 150)]);
      expect(u.predominantPitchRise, 4.5);
      expect(u.predominantPitchAreaSqft, 150);
    });

    test('equal areas: the lower pitch wins, in either input order', () {
      expect(totalsFor([(8.0, 100), (4.0, 100)]).predominantPitchRise, 4.0);
      expect(totalsFor([(4.0, 100), (8.0, 100)]).predominantPitchRise, 4.0);
    });

    test('flat counts as bucket 0 and can win', () {
      final j = _minimal(); // one flat 100 sq ft facet
      j['totals'] = null;
      (j['facets'] as List).add({
        'id': 'f2', 'block': 'b1', 'kind': 'sloped',
        'polygon': [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
        'pitch_rise': 4.0, 'aspect_deg': 0.0, 'plan_area_sqft': 50.0, 'area_sqft': 50.0,
      });
      final t = RoofModel.fromJson(j).totals;
      expect(t.predominantPitchRise, 0.0);
      expect(t.predominantPitchAreaSqft, 100.0);
    });
  });

  test('bounds cover all geometry', () {
    final b = RoofModel.fromJson(_minimal()).bounds;
    expect((b.min.x, b.min.y, b.max.x, b.max.y), (0.0, 0.0, 10.0, 10.0));
  });

  group('bad input names the path', () {
    void expectPath(Map<String, dynamic> j, String path) {
      expect(
        () => RoofModel.fromJson(j),
        throwsA(isA<FormatException>().having((e) => e.message, 'message', startsWith(path))),
      );
    }

    test('wrong schema', () => expectPath(_minimal()..['schema'] = 'other/1', 'schema'));
    test('missing schema', () => expectPath(_minimal()..remove('schema'), 'schema'));
    test('bad edge type is not a number', () {
      final j = _minimal();
      (j['edges'] as List)[1]['type'] = 7;
      expectPath(j, 'edges[1].type');
    });
    test('bad point', () {
      final j = _minimal();
      (j['facets'] as List)[0]['polygon'][2] = [1.0];
      expectPath(j, 'facets[0].polygon[2]');
    });
    test('non-number area', () {
      final j = _minimal();
      (j['facets'] as List)[0]['area_sqft'] = 'big';
      expectPath(j, 'facets[0].area_sqft');
    });
    test('edge with three points', () {
      final j = _minimal();
      (j['edges'] as List)[0]['points'] = [[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]];
      expectPath(j, 'edges[0].points');
    });
    test('non-number totals length value', () {
      final j = _minimal();
      (j['totals'] as Map)['lengths_ft'] = <String, dynamic>{'gutter': 'long'};
      expectPath(j, 'totals.lengths_ft.gutter');
    });
    test('units other than ft are rejected', () {
      expectPath(_minimal()..['units'] = 'm', 'units');
      expectPath(_minimal()..['units'] = 5, 'units');
    });
    test('units ft or absent are accepted', () {
      expect(RoofModel.fromJson(_minimal()..['units'] = 'ft').extra['units'], 'ft');
      expect(RoofModel.fromJson(_minimal()).extra.containsKey('units'), isFalse);
    });
    test('edges not a list', () => expectPath(_minimal()..['edges'] = {'a': 1}, 'edges'));
  });
}
