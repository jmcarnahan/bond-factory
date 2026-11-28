import 'dart:convert';

import 'package:bond_roof/bond_roof.dart';
import 'package:test/test.dart';

import 'scene_checks.dart';
import 'support.dart';

/// What an envelope or model of an older shape (the block path of 0.2 and 0.3, the 0.4 and 0.5 engine) does now: it must
/// not throw, and it may draw less. It draws its facets and edges with the totals the facets and edges give, with no
/// verdict line, no parapet row and no chimney or lantern mark.
void main() {
  _layoutGroup();
  final old = loadOldFixtures();
  test('the old fixtures are found; neither 0.7 example is among them', () {
    expect(old.length, greaterThanOrEqualTo(9));
    expect(old.map((f) => f.name).where((n) => n.contains('0.7')), isEmpty);
  });

  for (final f in old) {
    group(f.name, () {
      final measurement = RoofMeasurement.parseAny(f.json);
      final m = measurement.model;

      test('parses, and an old key this package no longer models is kept and written back', () {
        expect(m.facets, isNotEmpty);
        final out = jsonDecode(jsonEncode(m.toJson())) as Map<String, dynamic>;
        final src = (f.json['model'] ?? f.json) as Map<String, dynamic>;
        if (src['blocks'] != null) expect(out['blocks'], jsonDecode(jsonEncode(src['blocks'])));
        if (f.json['verification'] != null) expect(measurement.toJson()['verification'], f.json['verification']);
        expect(m.objects, isEmpty);
      });

      for (final layout in ReportLayout.values) {
        test('the three scenes build and fit (${layout.name})', () {
          final scenes = [
            LengthDiagram.build(m, layout: layout),
            AreaDiagram.build(m, layout: layout),
            SummaryBlock.build(m, layout: layout),
          ];
          for (final s in scenes) {
            expectFits(s);
            expectWellFormedSvg(sceneToSvg(s));
          }
          final all = [for (final s in scenes) ...textsOf(s)];
          for (final gone in [
            'Verification', 'Verified', 'Not verified', 'Parapet walls', 'Predominant pitch', 'Drip edge (eave only)',
            'Ridge cap (ridge only)', 'Step flashing', 'Wall flashing', 'Chimney', 'Roof lantern', 'n/a',
          ]) {
            expect(all, isNot(contains(gone)), reason: gone);
          }
          if (m.edges.any((e) => e.type == EdgeType.eave)) expect(textsOf(scenes[0]), contains('Eaves'));
          expect(textsOf(scenes[2]), contains('Total area'));
        });
      }

      test('the totals rows come from the facets and edges: area, pitch (weighted), lengths of the types it has', () {
        final rows = totalRows(m, const RoofLabels());
        final ids = [for (final r in rows) r.id];
        expect(ids, containsAll(['area', 'facets']));
        final f = RoofFigures.of(m);
        expect(f.areaSqft, greaterThan(0));
        expect(f.ridgeHipFt, greaterThanOrEqualTo(f.lengths[EdgeType.ridge]!));
        if (m.totals.lengthsFt[EdgeType.hip]! == 0) expect(ids, isNot(contains('hip')));
      });
    });
  }

  test('the closed-form hip: eaves, ridge, hips, valleys-free, with the pitch weighted over its facets', () {
    final m = RoofModel.fromJson(old.firstWhere((f) => f.name == 'synthetic_hip').json);
    final rows = {for (final r in totalRows(m, const RoofLabels())) r.id: r.value};
    expect(rows.keys, containsAll(['area', 'pitch', 'eave', 'ridge', 'hip', 'ridge_hip']));
    expect(rows.keys, isNot(contains('valley')));
    expect(rows['pitch'], startsWith('4/12'));
  });

  test('a parapet edge of the old flat roof is drawn as an unspecified line and listed as such', () {
    final m = RoofModel.fromJson(old.firstWhere((f) => f.name == 'synthetic_flat_parapet').json);
    expect(m.edges.any((e) => e.type == EdgeType.unspecified), isTrue);
    expect(m.parseNotes.any((n) => n.contains('parapet')), isTrue);
    expect(textsOf(LengthDiagram.build(m)), contains('Unspecified'));
  });

  test('an old step_flashing edge reads as the sidewall and an old wall_flashing edge as the headwall', () {
    final m = RoofModel.fromJson(old.firstWhere((f) => f.name == 'synthetic_flat_curbs').json);
    final t = textsOf(LengthDiagram.build(m));
    expect(t, contains('Sidewall flashing'));
    expect(t, contains('Headwall flashing'));
  });
}

/// Label layout on geometry other than the sample: diagonal edges of the hips and the zigzag eave.
void _layoutGroup() {
  group('label layout on diagonal geometry', () {
    for (final name in ['synthetic_hip', 'synthetic_hip_zigzag', 'synthetic_gable']) {
      final m = RoofModel.fromJson(loadOldFixtures().firstWhere((f) => f.name == name).json);
      for (final size in [(1600.0, 1000.0), (800.0, 600.0)]) {
        test('$name ${size.$1.toInt()}x${size.$2.toInt()}: upright, no overlap, no edge crossed, at most 30% hidden', () {
          final s = LengthDiagram.build(m, width: size.$1, height: size.$2);
          final labellable = m.edges.where((e) => e.type != EdgeType.flatSeam && !isHoleOutlineEdge(m, e)).length;
          expect(s.hiddenLabels + s.placedLabels, labellable);
          expect(s.hiddenLabels, lessThanOrEqualTo((labellable * 0.3).floor()));
          expectLengthLabelsClean(s);
          final a = AreaDiagram.build(m, width: size.$1, height: size.$2);
          expect(a.hiddenLabels + a.placedLabels, m.facets.length);
          expect(a.hiddenLabels, lessThanOrEqualTo((m.facets.length * 0.3).floor()));
        });
      }
      test('$name compact: every edge is labelled or counted hidden, labels are clean', () {
        final s = LengthDiagram.build(m, layout: ReportLayout.compact);
        expect(s.hiddenLabels + s.placedLabels, m.edges.length);
        expectLengthLabelsClean(s);
      });
    }

    test('synthetic_flat_curbs: hole-outline edges carry no label', () {
      final m = RoofModel.fromJson(loadOldFixtures().firstWhere((f) => f.name == 'synthetic_flat_curbs').json);
      expect(m.holes.length, 17);
      final holeEdges = m.edges.where((e) => isHoleOutlineEdge(m, e)).length;
      expect(holeEdges, greaterThanOrEqualTo(17 * 4 - 8));
      final s = LengthDiagram.build(m);
      expect(s.hiddenLabels + s.placedLabels, m.edges.length - holeEdges);
      expect(s.placedLabels, lessThanOrEqualTo(m.edges.length - holeEdges));
    });
  });
}
