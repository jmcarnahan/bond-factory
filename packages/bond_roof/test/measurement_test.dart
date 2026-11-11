import 'dart:convert';

import 'package:bond_roof/bond_roof.dart';
import 'package:test/test.dart';

import 'support.dart';

/// Deep equality that treats 4 and 4.0 as the same number.
bool deepEq(Object? a, Object? b) {
  if (a is Map && b is Map) {
    return a.length == b.length && a.keys.every((k) => b.containsKey(k) && deepEq(a[k], b[k]));
  }
  if (a is List && b is List) {
    return a.length == b.length && [for (var i = 0; i < a.length; i++) deepEq(a[i], b[i])].every((x) => x);
  }
  return a == b;
}

Map<String, dynamic> _copy(Map<String, dynamic> j) => jsonDecode(jsonEncode(j)) as Map<String, dynamic>;

void main() {
  final envelopes = loadEnvelopes();

  test('the four envelope fixtures are present, one per verdict', () {
    expect(envelopes.length, greaterThanOrEqualTo(4));
    expect({for (final e in envelopes) e.measurement.verification.verdict},
        containsAll([RoofVerdict.pass, RoofVerdict.adjusted, RoofVerdict.unverified, RoofVerdict.fail]));
  });

  for (final e in envelopes) {
    group('envelope ${e.name}', () {
      final m = e.measurement;

      test('top-level fields', () {
        expect(m.contract, startsWith('bond.roof_model/0.'));
        expect(m.pipelineVersion, isNotEmpty);
        expect(m.methodUsed, isNotEmpty);
        expect(m.footprintSource, isNotEmpty);
        expect(m.generatedAt!.year, greaterThan(2000));
        expect(m.confidenceScore, inInclusiveRange(0, 1));
        expect(m.model.edges, isNotEmpty);
        expect(m.model.facets, isNotEmpty);
      });

      test('the fourteen totals are read as written', () {
        final t = e.json['totals'] as Map<String, dynamic>;
        expect(t.length, 14);
        expect(m.totals.toJson(), isA<Map<String, dynamic>>());
        expect(deepEq(m.totals.toJson(), t), isTrue, reason: '${m.totals.toJson()} vs $t');
        expect(m.totals.facets, m.model.facets.length);
      });

      test('verification and warnings', () {
        final v = e.json['verification'] as Map<String, dynamic>;
        expect(m.verification.verdict.json, v['verdict']);
        expect(m.verification.notes, (v['notes'] as List).cast<String>());
        expect(m.verification.adjustments.length, (v['adjustments'] as List).length);
        expect(m.warnings, (e.json['warnings'] as List).cast<String>());
        expect(m.warningCodes, (e.json['warning_codes'] as List).cast<String>());
        expect(m.warningCodes.length, m.warnings.length, reason: 'warning_codes parallels warnings');
      });

      test('JSON round trip keeps every envelope field', () {
        final out = m.toJson();
        for (final k in e.json.keys.where((k) => k != 'model')) {
          expect(deepEq(out[k], e.json[k]), isTrue, reason: k);
        }
        final again = RoofMeasurement.parseAny(out);
        expect(deepEq(again.toJson(), out), isTrue);
        expect(deepEq(again.model.toJson(), m.model.toJson()), isTrue);
      });
    });
  }

  test('unfinished verification keys survive: original totals, model id, rounds, usage', () {
    final adjusted = envelopes.firstWhere((e) => e.measurement.verification.verdict == RoofVerdict.adjusted);
    final v = adjusted.measurement.verification;
    expect(v.adjustments, isNotEmpty);
    expect(v.adjustments.first, containsPair('op', isA<String>()));
    final raw = adjusted.json['verification'] as Map<String, dynamic>;
    expect(v.originalTotals != null, raw.containsKey('original_totals'));
    expect(v.modelId, raw['model']);
    expect(v.rounds, raw['rounds']);
  });

  group('tolerant envelope parsing', () {
    final base = envelopes.first.json;

    test('unknown top-level keys are kept in extra and written back', () {
      final j = _copy(base)..['future_field'] = {'a': 1};
      final m = RoofMeasurement.parseAny(j);
      expect(m.extra, {'future_field': {'a': 1}});
      expect(m.toJson()['future_field'], {'a': 1});
    });

    test('unknown verification keys and codes are kept', () {
      final j = _copy(base);
      (j['verification'] as Map)['verdict'] = 'maybe';
      (j['verification'] as Map)['future'] = 7;
      j['warnings'] = ['w1', 'w2'];
      j['warning_codes'] = ['footprint_osm', 'brand_new_code'];
      final m = RoofMeasurement.parseAny(j);
      expect(m.verification.verdict, RoofVerdict.unknown);
      expect(m.verification.extra, {'future': 7});
      expect(m.warningCodes, ['footprint_osm', 'brand_new_code']);
    });

    test('missing optional blocks are tolerated', () {
      final j = _copy(base)
        ..remove('totals')
        ..remove('verification')
        ..remove('warnings')
        ..remove('warning_codes')
        ..remove('confidence')
        ..remove('generated_at')
        ..remove('pipeline_version')
        ..remove('method_used')
        ..remove('footprint_source');
      final m = RoofMeasurement.parseAny(j);
      expect(m.verification.verdict, RoofVerdict.unverified);
      expect(m.warnings, isEmpty);
      expect(m.warningCodes, isEmpty);
      expect(m.methodUsed, m.model.source.method);
      expect(m.totals.areaSqft, closeTo(m.model.totals.totalAreaSqft, 1e-9));
      expect(m.totals.dripEdgeEaveRakeFt, closeTo(RoofTotalsVariants.of(m.model.totals).dripEdgeEaveRakeFt, 1e-9));
      expect(m.confidenceScore, inInclusiveRange(0, 1));
    });

    test('a missing single totals key falls back to the model', () {
      final j = _copy(base);
      (j['totals'] as Map).remove('ridge_cap_ridge_hip_ft');
      final m = RoofMeasurement.parseAny(j);
      expect(m.totals.ridgeCapRidgeHipFt, closeTo(RoofTotalsVariants.of(m.model.totals).ridgeCapRidgeHipFt, 1e-9));
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
  });

  group('parseAny on bare 0.x models', () {
    final bare = loadBareModels();
    test('bare fixtures found', () => expect(bare.length, greaterThanOrEqualTo(3)));

    for (final f in bare) {
      test(f.name, () {
        final m = RoofMeasurement.parseAny(f.json);
        final model = RoofModel.fromJson(f.json);
        expect(m.verification.verdict, RoofVerdict.unverified);
        expect(m.methodUsed, model.source.method);
        expect(m.warnings, model.warnings);
        expect(m.totals.facets, model.facets.length);
        expect(m.totals.areaSqft, model.totals.totalAreaSqft);
        expect(m.confidenceScore, switch (model.confidence.overall) { 'high' => 0.9, 'medium' => 0.7, _ => 0.5 });
        expect(m.contract, startsWith('bond.roof_model/'));
        final provider = (model.source.raw['footprint'] as Map?)?['provider'];
        if (provider == 'synthetic' || provider == 'test') expect(m.footprintSource, 'unknown');
        if ('$provider'.contains('lariac')) expect(m.footprintSource, 'lariac');
        // The wrapped measurement is itself a valid envelope.
        expect(deepEq(RoofMeasurement.parseAny(m.toJson()).toJson(), m.toJson()), isTrue);
      });
    }

    test('footprint provider mapping', () {
      Map<String, dynamic> withProvider(String? p) => _copy(bare.first.json)
        ..['source'] = {
          'method': 'lidar_skeleton',
          if (p != null) 'footprint': {'provider': p},
        };
      const cases = {
        'lacounty_lariac_2020': 'lariac',
        'la_county_parcels': 'lariac',
        'osm': 'osm',
        'osm_overpass': 'osm',
        'overpass': 'osm',
        'solar': 'solar',
        'solar_bbox_hull': 'solar',
        'lidar_hull': 'lidar_hull',
        'lidar': 'lidar_hull',
        'something_else': 'unknown',
      };
      for (final e in cases.entries) {
        expect(RoofMeasurement.parseAny(withProvider(e.key)).footprintSource, e.value, reason: e.key);
      }
      expect(RoofMeasurement.parseAny(withProvider(null)).footprintSource, 'unknown');
    });

    test('confidence mapping high 0.9, medium 0.7, low 0.5', () {
      for (final (word, score) in [('high', 0.9), ('medium', 0.7), ('low', 0.5), ('weird', 0.5)]) {
        final j = _copy(bare.first.json)..['confidence'] = {'overall': word, 'notes': <String>[]};
        expect(RoofMeasurement.parseAny(j).confidenceScore, score, reason: word);
      }
    });
  });

  group('strict envelope details', () {
    final base = envelopes.first.json;

    test('an unknown verdict string is kept and written back', () {
      final j = _copy(base);
      (j['verification'] as Map)['verdict'] = 'bogus';
      final m = RoofMeasurement.parseAny(j);
      expect(m.verification.verdict, RoofVerdict.unknown);
      expect(m.verification.verdictRaw, 'bogus');
      expect(m.toJson()['verification']['verdict'], 'bogus');
    });

    test('only 0.x contracts are accepted', () {
      for (final c in ['bond.roof_model/9.9', 'bond.roof_model/0', 'bond.roof_model/', 'bond.roof_model/1.0']) {
        expect(() => RoofMeasurement.parseAny(_copy(base)..['contract'] = c), throwsFormatException, reason: c);
      }
      expect(RoofMeasurement.parseAny(_copy(base)..['contract'] = 'bond.roof_model/0.3').contract, 'bond.roof_model/0.3');
    });

    test('confidence is clamped to 0..1', () {
      expect(RoofMeasurement.parseAny(_copy(base)..['confidence'] = 7).confidenceScore, 1.0);
      expect(RoofMeasurement.parseAny(_copy(base)..['confidence'] = -2).confidenceScore, 0.0);
    });

    test('a missing or unparseable generated_at is null and not written', () {
      for (final j in [_copy(base)..remove('generated_at'), _copy(base)..['generated_at'] = 'last tuesday']) {
        final m = RoofMeasurement.parseAny(j);
        expect(m.generatedAt, isNull);
        expect(m.toJson().containsKey('generated_at'), isFalse);
      }
    });
  });
}
