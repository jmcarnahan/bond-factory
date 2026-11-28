import 'dart:convert';

import 'package:bond_roof/bond_roof.dart';
import 'package:test/test.dart';

import 'support.dart';

/// A small 0.6-shaped model: one flat facet, a flat edge, a sidewall step, a chimney and a skylight hole.
Map<String, dynamic> _minimal() => {
      'schema': 'bond.roof_model/0.1',
      'generated_at': '2026-11-07T21:00:00Z',
      'address': {'line1': '1 A St', 'city': 'B', 'state': 'CA', 'zip': '90000', 'formatted': '1 A ST, B, CA'},
      'origin': {'lat': 1.0, 'lng': 2.0},
      'source': {'method': 'planes', 'footprint': {'provider': 'x'}},
      'facets': [
        {
          'id': 'f1',
          'kind': 'flat',
          'polygon': [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]],
          'pitch_rise': 0.0,
          'aspect_deg': null,
          'plan_area_sqft': 100.0,
          'area_sqft': 100.0,
        }
      ],
      'edges': [
        {'id': 'e1', 'type': 'flat_edge', 'points': [[0.0, 0.0], [10.0, 0.0]], 'length_ft': 10.0, 'facets': ['f1']},
        {
          'id': 'e2', 'type': 'step_flashing', 'points': [[10.0, 0.0], [10.0, 10.0]], 'length_ft': 10.0,
          'facets': ['f1'], 'jump_ft': 6.5,
        },
      ],
      'holes': [
        {'id': 'h1', 'kind': 'skylight', 'polygon': [[1.0, 1.0], [2.0, 1.0], [2.0, 2.0]], 'area_sqft': 0.5}
      ],
      'objects': [
        {'id': 'o1', 'kind': 'chimney', 'center': [5.0, 5.0], 'size_ft': [3.0, 3.0], 'height_ft': 3.0, 'facet': 'f1', 'returns': 12},
      ],
      'totals': {
        'total_area_sqft': 100.0,
        'pitched_area_sqft': 0.0,
        'flat_area_sqft': 100.0,
        'squares': 1.0,
        'lengths_ft': {'flat_edge': 10.0, 'step_flashing': 10.0},
      },
      'confidence': {'overall': 'low', 'notes': ['n']},
      'warnings': ['w'],
      'debug': {'png': 'x.png'},
    };

/// Round trip through real JSON text so int/double differences cannot hide.
Map<String, dynamic> _roundTrip(Map<String, dynamic> j) =>
    jsonDecode(jsonEncode(RoofModel.fromJson(j).toJson())) as Map<String, dynamic>;

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
    test('inline minimal model keeps everything it models and every key it does not', () {
      final j = _minimal();
      final m = RoofModel.fromJson(j);
      expect(m.edges.first.type, EdgeType.flatEdge);
      expect(m.edges.last.type, EdgeType.stepFlashing);
      expect(m.edges.last.jumpFt, 6.5);
      expect(m.objects.single.kind, ObjectKind.chimney);
      expect(m.extra['debug'], {'png': 'x.png'});
      final out = _roundTrip(j);
      expect(_canon(out), _canon(jsonDecode(jsonEncode(j))));
      expect(_roundTrip(out), out, reason: 'a second trip changes nothing');
    });

    test('the 0.6 sample round-trips: facets, edges, objects, totals, quality, source', () {
      final j = sampleJson()['model'] as Map<String, dynamic>;
      final out = _roundTrip(j);
      for (final k in ['facets', 'edges', 'objects', 'quality', 'source', 'address', 'confidence']) {
        expect(_canon(out[k]), _canon(j[k]), reason: k);
      }
      expect(_roundTrip(out), out);
    });
  });

  group('the 0.6 sample', () {
    final m = sampleModel();

    test('parses with no parse notes and no key the reader does not know', () {
      expect(m.parseNotes, isEmpty);
      expect(unknownEnvelopeKeys(sampleJson()), isEmpty);
      expect(m.facets.length, 4);
      expect(m.facets.map((f) => f.isFlatRoofType), [false, false, false, true]);
    });

    test('has every edge type it claims and no type the engine does not emit', () {
      final types = m.edges.map((e) => e.type).toSet();
      expect(types, containsAll([
        EdgeType.eave, EdgeType.rake, EdgeType.ridge, EdgeType.flatEdge,
        EdgeType.stepFlashing, EdgeType.wallFlashing, EdgeType.transition,
      ]));
      expect(types, isNot(contains(EdgeType.unspecified)));
    });

    test('the totals agree with the facets and edges (areas 0.5 sq ft, lengths 0.05 ft)', () {
      final r = m.recomputeTotals();
      expect(r.totalAreaSqft, closeTo(m.totals.totalAreaSqft, 0.5));
      expect(r.pitchedAreaSqft, closeTo(m.totals.pitchedAreaSqft, 0.5));
      expect(r.flatAreaSqft, closeTo(m.totals.flatAreaSqft, 0.5));
      for (final t in EdgeType.values) {
        expect(r.lengthsFt[t], closeTo(m.totals.lengthsFt[t]!, 0.05), reason: t.json);
      }
      final e = m.totals.engine!;
      expect(e.areaSqft, closeTo(r.totalAreaSqft, 0.5));
      expect(e.eaveRakeFt, closeTo(e.eaveFt! + e.rakeFt! + e.flatEdgeFt! + e.exposedEdgeFt!, 0.01));
      expect(e.ridgeHipFt, closeTo(e.ridgeFt! + e.hipFt!, 0.01));
      expect(e.roofingPitchedSqft! + e.roofingFlatSqft!, closeTo(e.areaSqft!, 0.01));
    });

    test('step edges carry their jump', () {
      for (final e in m.edges.where((e) => e.type.hasJump)) {
        expect(e.jumpFt, isNotNull, reason: e.id);
      }
      expect(m.edges.where((e) => !e.type.hasJump).every((e) => e.jumpFt == null), isTrue);
    });

    test('objects: kind, centre, size, height, facet, returns', () {
      final c = m.objects.firstWhere((o) => o.kind == ObjectKind.chimney);
      expect((c.sizeFt.$1, c.sizeFt.$2), (3.0, 3.0));
      expect(c.center, (x: 20.0, y: 6.0));
      expect(c.facet, 'f1');
      expect(c.returns, isNotNull);
      expect(m.objects.firstWhere((o) => o.kind == ObjectKind.lantern).sizeFt, (5.0, 5.0));
    });

    test('the bounds cover the facets and ignore objects', () {
      final b = m.bounds;
      expect((b.min.x, b.max.x), (-10.0, 49.0));
      expect((b.min.y, b.max.y), (0.0, 24.0));
    });
  });

  group('old shapes still open', () {
    test('a model of the old block shape parses; blocks and from_planes stay in extra and are written back', () {
      final j = _minimal()
        ..['blocks'] = [
          {'id': 'b1', 'form': 'flat', 'polygon': [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]], 'pitch_rise': 0.0}
        ];
      (j['source'] as Map)['from_planes'] = true;
      (j['facets'] as List)[0]['block'] = 'b1';
      final m = RoofModel.fromJson(j);
      expect(m.facets, hasLength(1));
      expect(m.extra['blocks'], isNotNull);
      expect(_roundTrip(j)['blocks'], jsonDecode(jsonEncode(j['blocks'])));
      expect((_roundTrip(j)['source'] as Map)['from_planes'], true);
    });

    test('a parapet edge reads as unspecified and is noted; its length key is kept', () {
      final j = _minimal();
      (j['edges'] as List)[0]['type'] = 'parapet';
      ((j['totals'] as Map)['lengths_ft'] as Map)['parapet'] = 10.0;
      final m = RoofModel.fromJson(j);
      expect(m.edges[0].type, EdgeType.unspecified);
      expect(m.totals.extraLengths, {'parapet': 10.0});
      expect(m.parseNotes, hasLength(2));
      expect(m.parseNotes.first, allOf(startsWith('edges[0].type'), contains('parapet'), contains('unspecified')));
    });

    test('totals without the 0.1 sums (only the 0.6 keys) are recomputed from the facets and edges', () {
      final j = _minimal();
      j['totals'] = {'area_sqft': 100.0, 'eave_ft': 0.0, 'plane_count': 1};
      final m = RoofModel.fromJson(j);
      expect(m.totals.totalAreaSqft, 100.0);
      expect(m.totals.flatAreaSqft, 100.0);
      expect(m.totals.lengthsFt[EdgeType.flatEdge], 10.0);
      expect(m.totals.engine!.planeCount, 1);
    });
  });

  group('tolerant parser', () {
    test('unknown edge type reads as unspecified and is noted', () {
      final j = _minimal();
      (j['edges'] as List)[1]['type'] = 'gutter';
      final m = RoofModel.fromJson(j);
      expect(m.edges[1].type, EdgeType.unspecified);
      expect(m.parseNotes.single, allOf(startsWith('edges[1].type'), contains('gutter'), contains('unspecified')));
      expect(m.edges[1].toJson()['type'], 'unspecified');
    });

    test('unknown facet kind is chosen from the pitch', () {
      final j = _minimal();
      final f = (j['facets'] as List)[0] as Map<String, dynamic>;
      f['kind'] = 'dome';
      f['pitch_rise'] = 4.0;
      expect(RoofModel.fromJson(j).facets[0].kind, FacetKind.sloped);
      f['pitch_rise'] = 0.0;
      expect(RoofModel.fromJson(j).facets[0].kind, FacetKind.flat);
    });

    test('unknown object kind reads as unknown and is noted', () {
      final j = _minimal();
      ((j['objects'] as List)[0] as Map)['kind'] = 'antenna';
      final m = RoofModel.fromJson(j);
      expect(m.objects.single.kind, ObjectKind.unknown);
      expect(m.parseNotes.single, allOf(startsWith('objects[0].kind'), contains('antenna')));
    });

    test('unknown lengths_ft key is kept, noted and written back', () {
      final j = _minimal();
      ((j['totals'] as Map)['lengths_ft'] as Map)['gutter'] = 12.5;
      final m = RoofModel.fromJson(j);
      expect(m.totals.extraLengths, {'gutter': 12.5});
      expect(m.parseNotes.single, startsWith('totals.lengths_ft.gutter'));
      expect((m.totals.toJson()['lengths_ft'] as Map)['gutter'], 12.5);
    });

    test('a model without objects has none and writes none', () {
      final j = _minimal()..remove('objects');
      final m = RoofModel.fromJson(j);
      expect(m.objects, isEmpty);
      expect(m.toJson().containsKey('objects'), isFalse);
    });
  });

  group('objects are decoration: a bad one is skipped with a note, never the roof', () {
    RoofModel withObjects(Object? objects) => RoofModel.fromJson(_minimal()..['objects'] = objects);

    test('missing kind', () {
      final m = withObjects([{'id': 'a', 'center': [1.0, 1.0], 'size_ft': [1.0, 1.0]}]);
      expect(m.objects, isEmpty);
      expect(m.parseNotes.single, allOf(startsWith('objects[0]: skipped'), contains('kind')));
      expect(m.facets, hasLength(1));
    });
    test('missing size_ft and no polygon', () {
      final m = withObjects([{'id': 'a', 'kind': 'chimney', 'center': [1.0, 1.0]}]);
      expect(m.objects, isEmpty);
      expect(m.parseNotes.single, contains('size_ft'));
    });
    test('non-numeric or short size_ft, no polygon', () {
      for (final size in [['a', 1.0], [3.0], 'big']) {
        final m = withObjects([{'id': 'a', 'kind': 'chimney', 'center': [1.0, 1.0], 'size_ft': size}]);
        expect(m.objects, isEmpty, reason: '$size');
        expect(m.parseNotes.single, startsWith('objects[0]: skipped'));
      }
    });
    test('empty or short polygon', () {
      for (final poly in [<Object?>[], [[0.0, 0.0], [1.0, 0.0]]]) {
        final m = withObjects([{'id': 'a', 'kind': 'chimney', 'center': [1.0, 1.0], 'size_ft': [1.0, 1.0], 'polygon': poly}]);
        expect(m.objects, isEmpty, reason: '$poly');
        expect(m.parseNotes.single, contains('polygon'));
      }
    });
    test('objects that is not a list, and an entry that is not an object', () {
      final m = withObjects({'a': 1});
      expect(m.objects, isEmpty);
      expect(m.parseNotes.single, startsWith('objects: expected an array'));
      final n = withObjects([5, {'id': 'ok', 'kind': 'chimney', 'center': [1.0, 1.0], 'size_ft': [1.0, 1.0]}]);
      expect(n.objects.map((o) => o.id), ['ok']);
      expect(n.parseNotes.single, startsWith('objects[0]: skipped'));
    });
    test('a polygon and no size_ft (or an unreadable one) takes its size and centre from the polygon', () {
      final poly = [[10.0, 2.0], [14.0, 2.0], [14.0, 5.0], [10.0, 5.0]];
      for (final extra in [<String, Object?>{}, {'size_ft': 'x'}]) {
        final m = withObjects([{'id': 'a', 'kind': 'lantern', 'polygon': poly, ...extra}]);
        final o = m.objects.single;
        expect((o.sizeFt.$1, o.sizeFt.$2), (4.0, 3.0));
        expect(o.center, (x: 12.0, y: 3.5));
        expect(o.perimeterFt, closeTo(14.0, 1e-9));
      }
    });
    test('an object whose centre is off the roof is kept, noted, and not on the roof', () {
      final m = withObjects([{'id': 'a', 'kind': 'chimney', 'center': [500.0, 500.0], 'size_ft': [1.0, 1.0]}]);
      expect(m.objects, hasLength(1));
      expect(m.parseNotes.single, contains('outside the roof'));
      expect(m.objectOnRoof(m.objects.single), isFalse);
      expect(m.objectOnRoof(RoofModel.fromJson(_minimal()).objects.single), isTrue);
    });
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
      expect(RoofModel.fromJson(_minimal()..['units'] = 'ft').extra['units'], 'ft');
    });
    test('edges not a list', () => expectPath(_minimal()..['edges'] = {'a': 1}, 'edges'));
  });
}
