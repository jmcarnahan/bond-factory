import 'package:bond_roof/bond_roof.dart';
import 'package:bond_roof/src/length_diagram.dart' show legendRowIds;
import 'package:test/test.dart';

import 'support.dart';

RoofModel _withTotals(Map<String, Object?> totals, {List<Map<String, Object?>> objects = const [], bool edges = true}) {
  final j = sampleJson()['model'] as Map<String, dynamic>;
  j['totals'] = totals;
  j['objects'] = objects;
  if (!edges) j['edges'] = <Object?>[];
  return RoofModel.fromJson(j);
}

TotalRow? _row(List<TotalRow> rows, String id) => rows.where((r) => r.id == id).firstOrNull;

void main() {
  group('RoofEngineTotals reads the 0.7 keys', () {
    test('every key of the contract is read and written back', () {
      final t = RoofEngineTotals.fromJson(sampleJson()['totals'] as Map<String, dynamic>)!;
      expect(t.toJson().keys.toSet(), RoofEngineTotals.knownKeys.toSet());
      expect(t.areaSqft, closeTo(1417.518, 1e-9));
      expect(t.chimneyCount, 1);
      expect(t.lanternCount, 1);
      expect(t.eaveRakeFt, closeTo(210.825, 1e-9));
    });

    test('a missing key is null, never zero', () {
      final t = RoofEngineTotals.fromJson({'area_sqft': 1000.0})!;
      expect(t.areaSqft, 1000.0);
      expect(t.hipFt, isNull);
      expect(t.wallFlashingFt, isNull);
      expect(t.chimneyCount, isNull);
      expect(t.toJson(), {'area_sqft': 1000.0});
    });

    test('totals without any 0.7 key give no engine totals', () {
      expect(RoofEngineTotals.fromJson({'total_area_sqft': 5.0}), isNull);
    });

    test('keys that were removed at 0.6 or 0.7 are not read', () {
      final t = RoofEngineTotals.fromJson({
        'area_sqft': 1.0,
        'planes_surface_area_sqft': 2.0, 'area_sqft_wall_line': 3.0, 'outline_perimeter_ft': 4.0, 'outline_perimeter_wall_ft': 5.0,
        'overhang_ft_median': 6.0, 'drip_edge_eave_ft': 7.0, 'drip_edge_eave_rake_ft': 8.0, 'ridge_cap_ridge_ft': 9.0,
        'ridge_cap_ridge_hip_ft': 10.0, 'predominant_pitch': 11.0, 'roofing_pitched_squares': 12.0, 'roofing_flat_squares': 13.0,
        'area_sqft_roof_edge': 14.0,
      })!;
      expect(t.toJson(), {'area_sqft': 1.0});
    });

    test('a wrong type names the path', () {
      expect(() => RoofEngineTotals.fromJson({'eave_ft': 'long'}),
          throwsA(isA<FormatException>().having((e) => e.message, 'message', startsWith('totals.eave_ft'))));
    });
  });

  group('totals rows: only what the roof has', () {
    const l = RoofLabels();

    test('the sample lists every row, in report order', () {
      final rows = totalRows(sampleModel(), l);
      expect([for (final r in rows) r.id], [
        'area', 'pitched', 'flat', 'pitch', 'eave', 'rake', 'flat_edge', 'exposed_edge', 'eave_rake', 'ridge', 'ridge_hip',
        'step_flashing', 'wall_flashing', 'transition', 'chimneys', 'lanterns', 'lantern_sides', 'lantern_hips', 'units', 'facets',
      ]);
      expect(_row(rows, 'area')!.value, '1,418 sq ft  (14.18 squares)');
      expect(_row(rows, 'pitch')!.value, '6/12 (5.9)');
      expect(_row(rows, 'step_flashing')!.label, 'Sidewall flashing');
      expect(_row(rows, 'wall_flashing')!.label, 'Headwall flashing');
      expect(_row(rows, 'eave_rake')!.label, 'Eave + rake');
      expect(_row(rows, 'exposed_edge')!.label, 'Exposed edges inside the roof');
      expect(_row(rows, 'chimneys')!.value, '1');
    });

    test('no hip, valley, level change or low-slope-confirm row when the roof has none', () {
      final ids = [for (final r in totalRows(sampleModel(), l)) r.id];
      for (final id in ['hip', 'valley', 'level_change', 'low_slope']) {
        expect(ids, isNot(contains(id)));
      }
    });

    test('the pitch is computed from the pitched facets when the key is missing; no split when the roof has one kind', () {
      final m = _withTotals({'area_sqft': 100.0, 'roofing_flat_sqft': 100.0, 'roofing_pitched_sqft': 0.0, 'eave_ft': 40.0});
      final f = RoofFigures.of(m);
      expect(f.hasBothKinds, isFalse);
      final rows = totalRows(m, l);
      expect(_row(rows, 'pitch')!.value, '6/12 (5.9)', reason: 'area-weighted over the pitched facets of the model');
      expect(_row(rows, 'pitched'), isNull);
    });

    test('a key that is missing, with no drawn edge to sum, is not shown as a zero row', () {
      final m = _withTotals({'area_sqft': 100.0, 'eave_ft': 40.0, 'ridge_ft': 40.0}, edges: false);
      final ids = [for (final r in totalRows(m, l)) r.id];
      expect(ids, containsAll(['eave', 'ridge']));
      for (final id in ['hip', 'valley', 'rake', 'step_flashing', 'wall_flashing', 'exposed_edge']) {
        expect(ids, isNot(contains(id)), reason: id);
      }
    });

    test('ridge + hip is never smaller than ridge', () {
      final m = _withTotals({'area_sqft': 100.0, 'ridge_ft': 40.0, 'hip_ft': 10.0, 'ridge_hip_ft': 12.0});
      expect(RoofFigures.of(m).ridgeHipFt, 40.0);
      final ok = _withTotals({'area_sqft': 100.0, 'ridge_ft': 40.0, 'hip_ft': 10.0});
      expect(RoofFigures.of(ok).ridgeHipFt, 50.0);
      final given = _withTotals({'area_sqft': 100.0, 'ridge_ft': 40.0, 'hip_ft': 10.0, 'ridge_hip_ft': 50.0});
      expect(RoofFigures.of(given).ridgeHipFt, 50.0);
    });

    test('eave + rake is the service value, else eave + rake + flat edge + exposed', () {
      expect(RoofFigures.of(_withTotals({'area_sqft': 1.0, 'eave_rake_ft': 123.0})).eaveRakeFt, 123.0);
      final m = _withTotals({'area_sqft': 1.0, 'eave_ft': 50.0, 'rake_ft': 30.0, 'flat_edge_ft': 10.0, 'exposed_edge_ft': 5.0});
      expect(RoofFigures.of(m).eaveRakeFt, 95.0);
    });

    test('chimney and lantern counts come from the key, else from the objects', () {
      final obj = [
        {'id': 'a', 'kind': 'chimney', 'center': [1.0, 1.0], 'size_ft': [2.0, 2.0]},
        {'id': 'b', 'kind': 'chimney', 'center': [2.0, 2.0], 'size_ft': [2.0, 2.0]},
        {'id': 'c', 'kind': 'unknown', 'center': [3.0, 3.0], 'size_ft': [2.0, 2.0]},
      ];
      final fromObjects = RoofFigures.of(_withTotals({'area_sqft': 1.0}, objects: obj));
      expect((fromObjects.chimneys, fromObjects.lanterns), (2, 0));
      final fromKey = RoofFigures.of(_withTotals({'area_sqft': 1.0, 'chimney_count': 5}, objects: obj));
      expect(fromKey.chimneys, 5);
    });


    test('the table, the legend and the summary print the same rows (sample and an old flat roof)', () {
      const nonLegend = {'area', 'pitched', 'flat', 'low_slope', 'pitch', 'facets', 'lantern_sides', 'lantern_hips'};
      final old = RoofModel.fromJson(loadOldFixtures().firstWhere((f) => f.name == 'synthetic_flat_parapet').json);
      for (final model in [sampleModel(), old]) {
        final table = [for (final r in totalRows(model, l)) if (!nonLegend.contains(r.id)) r.id];
        expect(legendRowIds(model), table);
        final summary = textsOf(SummaryBlock.build(model));
        for (final r in totalRows(model, l)) {
          expect(summary, contains(r.label), reason: r.id);
        }
      }
      expect(legendRowIds(old), contains('unspecified'));
      expect([for (final r in totalRows(sampleModel(), l)) r.id], containsAll(['lanterns']));
    });

    test('the three 0.7 keys are read, written back, and read as null when the service sent none', () {
      final t = RoofEngineTotals.fromJson({
        'area_sqft': 1.0, 'lantern_sides_ft': 20.0, 'lantern_hips_ft': 13.86, 'unit_count': 2,
      })!;
      expect((t.lanternSidesFt, t.lanternHipsFt, t.unitCount), (20.0, 13.86, 2));
      expect(RoofEngineTotals.fromJson(t.toJson()), t);
      final none = RoofEngineTotals.fromJson({'area_sqft': 1.0})!;
      expect((none.lanternSidesFt, none.lanternHipsFt, none.unitCount), (null, null, null));
    });

    test('a totals key this package does not know is ignored without error, and so is an unknown object kind', () {
      final t = RoofEngineTotals.fromJson({'area_sqft': 1.0, 'a_key_of_a_later_contract_ft': 3.0})!;
      expect(t.toJson(), {'area_sqft': 1.0});
      final m = _withTotals({'area_sqft': 100.0}, objects: [
        {'id': 'a', 'kind': 'a_kind_of_a_later_contract', 'center': [1.0, 1.0], 'size_ft': [2.0, 2.0]},
      ]);
      expect(m.objects.single.kind, ObjectKind.unknown);
      expect(RoofFigures.of(m).units, 0);
      expect(() => totalRows(m, const RoofLabels()), returnsNormally);
    });

    test('the unit, lantern sides, lantern hips rows show only when the value is over 0', () {
      const rowOf = {'unit_count': 'units', 'lantern_sides_ft': 'lantern_sides', 'lantern_hips_ft': 'lantern_hips'};
      const labelOf = {
        'units': 'Rooftop units',
        'lantern_sides': 'Roof lantern sides (in eave + rake)',
        'lantern_hips': 'Roof lantern hips (not in ridge + hip)',
      };
      for (final key in rowOf.keys) {
        final id = rowOf[key]!;
        final shown = totalRows(_withTotals({'area_sqft': 100.0, key: key == 'unit_count' ? 3 : 24.0}), l);
        expect(_row(shown, id)?.label, labelOf[id], reason: key);
        expect(_row(shown, id)!.value, key == 'unit_count' ? '3' : '24ft 0in', reason: key);
        for (final zero in [0, 0.0, null]) {
          final hidden = totalRows(_withTotals({'area_sqft': 100.0, key: ?zero}), l);
          expect(_row(hidden, id), isNull, reason: '$key = $zero');
        }
      }
    });

    test('the units row counts the unit objects when the key is absent, like the chimney count', () {
      final obj = [
        {'id': 'a', 'kind': 'unit', 'center': [1.0, 1.0], 'size_ft': [2.0, 2.0]},
        {'id': 'b', 'kind': 'unit', 'center': [5.0, 5.0], 'size_ft': [2.0, 2.0]},
      ];
      expect(RoofFigures.of(_withTotals({'area_sqft': 1.0}, objects: obj)).units, 2);
      expect(RoofFigures.of(_withTotals({'area_sqft': 1.0, 'unit_count': 7}, objects: obj)).units, 7);
    });

    test('model totals that carry only a few keys lose nothing from a full envelope totals (read key by key)', () {
      final j = sampleJson();
      (j['model'] as Map<String, dynamic>)['totals'] = {
        'squares': 14.0, 'area_sqft': 1400.0, 'lengths_ft': {'eave': 1.0},
      };
      final m = RoofMeasurement.parseAny(j);
      final rows = {for (final r in totalRows(m.model, l, envelope: m.totals)) r.id: r.value};
      expect(rows['area'], contains('1,400'), reason: 'the model value wins');
      expect(rows['eave'], '98ft 0in', reason: 'the envelope fills the key the model lacks');
      for (final id in ['eave_rake', 'exposed_edge', 'step_flashing', 'wall_flashing', 'chimneys', 'lanterns']) {
        expect(rows, contains(id));
      }
    });

    test('a totals key of 0 wins over the drawn edges: the row is not shown', () {
      final m = _withTotals({'area_sqft': 100.0, 'eave_ft': 0.0});
      expect([for (final r in totalRows(m, l)) r.id], isNot(contains('eave')));
      expect(RoofFigures.of(m).lengths[EdgeType.eave], 0.0);
    });

    test('with eave + rake and exposed edges absent they are computed: exposed = sidewall + headwall + lantern perimeters', () {
      final m = _withTotals({'area_sqft': 100.0}, objects: [
        {'id': 'l', 'kind': 'lantern', 'center': [25.0, 18.0], 'size_ft': [5.0, 5.0]},
        {'id': 'c', 'kind': 'chimney', 'center': [20.0, 6.0], 'size_ft': [3.0, 3.0]},
      ]);
      final f = RoofFigures.of(m);
      double sum(EdgeType t) => m.edges.where((e) => e.type == t).fold(0.0, (a, e) => a + e.lengthFt);
      expect(f.exposedEdgeFt, closeTo(sum(EdgeType.stepFlashing) + sum(EdgeType.wallFlashing) + 20.0, 1e-9));
      expect(f.eaveRakeFt,
          closeTo(sum(EdgeType.eave) + sum(EdgeType.rake) + sum(EdgeType.flatEdge) + f.exposedEdgeFt, 1e-9));
    });

    test('the sample\'s own exposed and eave + rake totals follow from its edges and its lantern, none copied from the file', () {
      final m = sampleModel();
      double sum(EdgeType t) => m.edges.where((e) => e.type == t).fold(0.0, (a, e) => a + e.lengthFt);
      final lantern = m.objects.firstWhere((o) => o.kind == ObjectKind.lantern);
      final exposed = sum(EdgeType.stepFlashing) + sum(EdgeType.wallFlashing) + lantern.perimeterFt;
      final eaveRake = sum(EdgeType.eave) + sum(EdgeType.rake) + sum(EdgeType.flatEdge) + exposed;
      final e = m.totals.engine!;
      expect(e.exposedEdgeFt, closeTo(exposed, 0.01));
      expect(e.eaveRakeFt, closeTo(eaveRake, 0.01));
      expect(e.eaveFt, closeTo(sum(EdgeType.eave), 0.01));
      expect(e.ridgeHipFt, closeTo(sum(EdgeType.ridge) + sum(EdgeType.hip), 0.01));
    });

    test('model.totals and the envelope totals of the sample are the same dict', () {
      final j = sampleJson();
      expect((j['model'] as Map)['totals'], j['totals']);
    });

    test('the table of an envelope reads the envelope totals when the model has no 0.7 keys', () {
      final j = sampleJson();
      (j['model'] as Map<String, dynamic>)['totals'] = {'total_area_sqft': 1000.0};
      (j['totals'] as Map<String, dynamic>)['step_flashing_ft'] = 99.0;
      final m = RoofMeasurement.parseAny(j);
      expect(m.model.totals.engine, isNull);
      expect(_row(totalRows(m.model, l, envelope: m.totals), 'step_flashing')!.value, '99ft 0in');
      expect(_row(totalRows(m.model, l), 'step_flashing')!.value, '12ft 0in', reason: 'without the envelope: the drawn edges');
    });
  });
}
