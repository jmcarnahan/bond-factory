import 'dart:convert';

import 'package:bond_roof/bond_roof.dart';
import 'package:test/test.dart';

import 'support.dart';

Map<String, dynamic> _copy(Map<String, dynamic> j) => jsonDecode(jsonEncode(j)) as Map<String, dynamic>;

void main() {
  final base = sampleJson();

  group('the 0.6 sample envelope', () {
    final m = RoofMeasurement.parseAny(base);

    test('top-level fields', () {
      expect(m.contract, startsWith('bond.roof_model/0.'));
      expect(m.pipelineVersion, '0.7.0');
      expect(m.methodUsed, 'planes');
      expect(m.footprintSource, 'lariac');
      expect(m.generatedAt!.year, 2026);
      expect(m.confidenceScore, 0.6);
      expect(m.model.address.display, '100 Example Ave, Sampletown, CA 90000');
    });

    test('the envelope totals are the 0.6 keys, as written', () {
      expect(m.totals.toJson(), base['totals']);
      expect(m.totals.planeCount, m.model.facets.length);
    });

    test('JSON round trip keeps every envelope field', () {
      final out = m.toJson();
      for (final k in base.keys.where((k) => k != 'model')) {
        expect(jsonEncode(out[k]), jsonEncode(base[k]), reason: k);
      }
      final again = RoofMeasurement.parseAny(jsonDecode(jsonEncode(out)) as Map<String, dynamic>);
      expect(jsonEncode(again.toJson()), jsonEncode(out));
    });
  });

  group('tolerant envelope parsing', () {
    test('unknown top-level keys are kept in extra and written back', () {
      final j = _copy(base)..['future_field'] = {'a': 1};
      final m = RoofMeasurement.parseAny(j);
      expect(m.extra, {'future_field': {'a': 1}});
      expect(m.toJson()['future_field'], {'a': 1});
    });

    test('an old verification block is kept as an extra key, not modelled', () {
      final j = _copy(base)..['verification'] = {'verdict': 'pass', 'notes': ['n']};
      final m = RoofMeasurement.parseAny(j);
      expect(m.extra['verification'], {'verdict': 'pass', 'notes': ['n']});
      expect(m.toJson()['verification'], {'verdict': 'pass', 'notes': ['n']});
    });

    test('warning codes are kept as strings, unknown ones too', () {
      final j = _copy(base)
        ..['warnings'] = ['w1', 'w2']
        ..['warning_codes'] = ['footprint_osm', 'brand_new_code'];
      expect(RoofMeasurement.parseAny(j).warningCodes, ['footprint_osm', 'brand_new_code']);
    });

    test('missing optional blocks are tolerated; totals fall back to the model\'s own 0.6 keys', () {
      final j = _copy(base)
        ..remove('totals')
        ..remove('warnings')
        ..remove('warning_codes')
        ..remove('confidence')
        ..remove('generated_at')
        ..remove('pipeline_version')
        ..remove('method_used')
        ..remove('footprint_source');
      final m = RoofMeasurement.parseAny(j);
      expect(m.warnings, isEmpty);
      expect(m.methodUsed, m.model.source.method);
      expect(m.totals.areaSqft, m.model.totals.engine!.areaSqft);
      expect(m.generatedAt, isNull);
      expect(m.confidenceScore, inInclusiveRange(0, 1));
    });

    test('a model with no 0.6 keys gives empty envelope totals: not available, not zero', () {
      final j = _copy(base)..remove('totals');
      (j['model'] as Map<String, dynamic>)['totals'] = {'total_area_sqft': 10.0};
      final m = RoofMeasurement.parseAny(j);
      expect(m.totals.areaSqft, isNull);
      expect(m.totals.toJson(), isEmpty);
    });

    test('bad input names the path', () {
      expect(() => RoofMeasurement.parseAny({'x': 1}), throwsFormatException);
      expect(() => RoofMeasurement.fromJson(_copy(base)..['contract'] = 'other/1'),
          throwsA(isA<FormatException>().having((e) => e.message, 'message', startsWith('contract'))));
      expect(() => RoofMeasurement.fromJson(_copy(base)..['model'] = 5),
          throwsA(isA<FormatException>().having((e) => e.message, 'message', startsWith('model'))));
      expect(() => RoofMeasurement.fromJson(_copy(base)..['confidence'] = 'high'),
          throwsA(isA<FormatException>().having((e) => e.message, 'message', startsWith('confidence'))));
    });

    test('only 0.x contracts are accepted', () {
      for (final c in ['bond.roof_model/9.9', 'bond.roof_model/0', 'bond.roof_model/', 'bond.roof_model/1.0']) {
        expect(() => RoofMeasurement.parseAny(_copy(base)..['contract'] = c), throwsFormatException, reason: c);
      }
      expect(RoofMeasurement.parseAny(_copy(base)..['contract'] = 'bond.roof_model/0.6').contract, 'bond.roof_model/0.6');
    });

    test('confidence is clamped to 0..1', () {
      expect(RoofMeasurement.parseAny(_copy(base)..['confidence'] = 7).confidenceScore, 1.0);
      expect(RoofMeasurement.parseAny(_copy(base)..['confidence'] = -2).confidenceScore, 0.0);
    });

    test('an unparseable generated_at is null and not written', () {
      final m = RoofMeasurement.parseAny(_copy(base)..['generated_at'] = 'last tuesday');
      expect(m.generatedAt, isNull);
      expect(m.toJson().containsKey('generated_at'), isFalse);
    });
  });

  group('parseAny on a bare model', () {
    final bare = _copy(base['model'] as Map<String, dynamic>);

    test('is wrapped: method, warnings, totals from the model, confidence from the word', () {
      final m = RoofMeasurement.parseAny(bare);
      final model = RoofModel.fromJson(bare);
      expect(m.methodUsed, model.source.method);
      expect(m.warnings, model.warnings);
      expect(m.totals, model.totals.engine);
      expect(m.confidenceScore, 0.7);
      expect(m.contract, startsWith('bond.roof_model/'));
      expect(jsonEncode(RoofMeasurement.parseAny(m.toJson()).toJson()), jsonEncode(m.toJson()));
    });

    test('footprint provider mapping', () {
      Map<String, dynamic> withProvider(String? p) => _copy(bare)
        ..['source'] = {
          'method': 'planes',
          if (p != null) 'footprint': {'provider': p},
        };
      const cases = {
        'lacounty_lariac_2020': 'lariac',
        'la_county_parcels': 'lariac',
        'osm': 'osm',
        'osm_overpass': 'osm',
        'overpass': 'osm',
        'lidar_hull': 'lidar_hull',
        'lidar': 'lidar_hull',
        'solar': 'unknown',
        'something_else': 'unknown',
      };
      for (final e in cases.entries) {
        expect(RoofMeasurement.parseAny(withProvider(e.key)).footprintSource, e.value, reason: e.key);
      }
      expect(RoofMeasurement.parseAny(withProvider(null)).footprintSource, 'unknown');
    });

    test('confidence mapping high 0.9, medium 0.7, low 0.5', () {
      for (final (word, score) in [('high', 0.9), ('medium', 0.7), ('low', 0.5), ('weird', 0.5)]) {
        final j = _copy(bare)..['confidence'] = {'overall': word, 'notes': <String>[]};
        expect(RoofMeasurement.parseAny(j).confidenceScore, score, reason: word);
      }
    });
  });

  group('what the reader knows (the one-line check for an engine envelope)', () {
    test('the sample uses only keys, edge types and object kinds the reader knows', () {
      expect(unknownEnvelopeKeys(base), isEmpty);
    });

    test('the helper names an unknown totals key, edge type and object kind', () {
      final j = _copy(base);
      (j['totals'] as Map)['brand_new_ft'] = 1.0;
      ((j['model'] as Map)['edges'] as List)[0]['type'] = 'gutter';
      (((j['model'] as Map)['objects'] as List)[0] as Map)['kind'] = 'antenna';
      expect(unknownEnvelopeKeys(j),
          unorderedEquals(['totals.brand_new_ft', 'model.edges[0].type=gutter', 'model.objects[0].kind=antenna']));
    });

    test('a removed 0.5 key counts as unknown', () {
      final j = _copy(base);
      (j['totals'] as Map)['drip_edge_eave_ft'] = 1.0;
      expect(unknownEnvelopeKeys(j), ['totals.drip_edge_eave_ft']);
    });
  });
}
