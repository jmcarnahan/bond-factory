import 'package:bond_roof/bond_roof.dart';
import 'package:bond_roof/roof_pdf.dart';
import 'package:test/test.dart';

import 'scene_checks.dart';
import 'spanish_labels.dart';
import 'support.dart';

int _texts(Scene s) => s.prims.whereType<TextPrim>().length;

void main() {
  group('RoofLabels', () {
    test('keys are unique snake_case names and match toMap', () {
      expect(RoofLabels.keys.toSet().length, RoofLabels.keys.length);
      expect(RoofLabels.keys.length, const RoofLabels().toMap().length);
      expect(RoofLabels.keys.toSet(), const RoofLabels().toMap().keys.toSet());
      for (final k in RoofLabels.keys) {
        expect(k, matches(RegExp(r'^[a-z][a-z_]*$')));
      }
      expect(RoofLabels.keys.length, greaterThanOrEqualTo(60));
    });

    test('every key is overridable and only that key changes', () {
      final base = const RoofLabels().toMap();
      for (final k in RoofLabels.keys) {
        final l = RoofLabels.fromMap({k: 'X-$k'});
        expect(l[k], 'X-$k', reason: k);
        final m = l.toMap();
        for (final other in RoofLabels.keys.where((o) => o != k)) {
          expect(m[other], base[other], reason: '$k changed $other');
        }
      }
    });

    test('fromMap ignores unknown keys and keeps defaults for missing ones', () {
      final l = RoofLabels.fromMap({'legend_eave': 'Aleros', 'not_a_key': 'x'});
      expect(l.legendEave, 'Aleros');
      expect(l.legendRake, const RoofLabels().legendRake);
      expect(l.toMap().containsKey('not_a_key'), isFalse);
      expect(RoofLabels.fromMap(const {}), const RoofLabels());
      expect(RoofLabels.fromMap(const {}).hashCode, const RoofLabels().hashCode);
    });

    test('empty, blank and null values keep the default; nullable maps are accepted', () {
      final l = RoofLabels.fromMap(<String, String?>{
        'legend_eave': '',
        'legend_rake': '   ',
        'legend_ridge': null,
        'legend_hip': 'Limas',
      });
      const d = RoofLabels();
      expect(l.legendEave, d.legendEave);
      expect(l.legendRake, d.legendRake);
      expect(l.legendRidge, d.legendRidge);
      expect(l.legendHip, 'Limas');
      expect(d.copyWith({'legend_hip': null, 'pitch': ''}), d);
    });

    test('equality follows the text; copyWith applies overrides', () {
      final es = RoofLabels.fromMap(spanishLabels);
      expect(es, isNot(const RoofLabels()));
      expect(es, RoofLabels.fromMap(spanishLabels));
      expect(es.hashCode, RoofLabels.fromMap(spanishLabels).hashCode);
      expect(const RoofLabels().copyWith({'pitch': 'Slope'}).pitch, 'Slope');
      expect(const RoofLabels().copyWith({'pitch': 'Slope'}).facets, 'Facets');
      expect(() => const RoofLabels()['nope'], throwsArgumentError);
    });

    test('fill replaces known placeholders only', () {
      expect(RoofLabels.fill('Method: {method} {x}', {'method': 'LiDAR'}), 'Method: LiDAR {x}');
      expect(RoofLabels.fill(const RoofLabels().statusFailed, {'error': 'boom'}), 'Failed: boom');
    });

    test('the Spanish sample covers every key', () {
      expect(spanishLabels.keys.toSet(), RoofLabels.keys.toSet());
      expect(RoofLabels.fromMap(spanishLabels).toMap(), spanishLabels);
    });

    test('feetInches, pitchLabel and the area header use the labels', () {
      final es = RoofLabels.fromMap(spanishLabels);
      expect(feetInches(209.67), '209ft 8in');
      expect(feetInches(209.67, labels: es), '209pies 8pulg');
      expect(pitchLabel(0.2), 'Flat');
      expect(pitchLabel(0.2, labels: es), 'Plano');
      final m = sampleModel();
      expect(textsOf(AreaDiagram.build(m)), containsAll(['Total area', 'Pitch', 'Chimneys']));
      final t = textsOf(AreaDiagram.build(m, labels: es));
      expect(t, containsAll(['Área total', 'Pendiente', 'Chimeneas']));
      expect(t, isNot(contains('Pitch')));
    });

    test('the new keys of 0.6 are all there and in English the owner\'s words', () {
      const l = RoofLabels();
      expect(l.legendStepFlashing, 'Sidewall flashing');
      expect(l.legendWallFlashing, 'Headwall flashing');
      expect([l.legendChimney, l.legendLantern, l.markChimney, l.markLantern], ['Chimney', 'Roof lantern', 'C', 'L']);
      expect([l.totalsEaveRake, l.totalsExposedEdge, l.totalsRidgeHip], ['Eave + rake', 'Exposed edges inside the roof', 'Ridge + hip']);
      expect([l.totalsSidewall, l.totalsHeadwall, l.totalsTransition, l.totalsChimneys],
          ['Sidewall flashing', 'Headwall flashing', 'Transitions', 'Chimneys']);
    });

    test('the keys of removed totals and removed things are gone', () {
      const gone = [
        'legend_parapet', 'totals_priced_area', 'totals_as_drawn', 'predominant_pitch', 'predominant_pitch_area', 'two_story_area',
        'two_layer_area', 'unspecified_pitch_area', 'variant_drip_edge_eave', 'variant_drip_edge_eave_rake',
        'variant_ridge_cap_ridge', 'variant_ridge_cap_ridge_hip', 'verification', 'verdict_pass', 'verdict_adjusted', 'verdict_fail',
        'verdict_unverified', 'edge_total', 'source_solar', 'solar_segments', 'method_lidar_agent', 'method_solar_agent',
      ];
      for (final k in gone) {
        expect(RoofLabels.keys, isNot(contains(k)), reason: k);
      }
    });
  });

  group('Spanish labels render every fixture in both layouts', () {
    final es = RoofLabels.fromMap(spanishLabels);
    for (final f in [(name: 'sample_0.6', json: sampleJson()['model'] as Map<String, dynamic>), ...loadOldFixtures()]) {
      for (final layout in ReportLayout.values) {
        test('${f.name} ${layout.name}', () {
          final m = RoofMeasurement.parseAny(f.json).model;
          final enLen = LengthDiagram.build(m, layout: layout);
          final enArea = AreaDiagram.build(m, layout: layout);
          final scenes = [
            LengthDiagram.build(m, labels: es, layout: layout),
            AreaDiagram.build(m, labels: es, layout: layout),
            SummaryBlock.build(m, labels: es, layout: layout),
          ];
          for (final s in scenes) {
            expectFits(s);
            expectWellFormedSvg(sceneToSvg(s));
          }
          // Longer text must not push labels off the plan: numeric labels hide exactly as in English (the facet labels
          // are numbers too, so they hide the same unless a longer legend moves the plan).
          expect(scenes[0].hiddenLabels, enLen.hiddenLabels);
          expect(scenes[1].hiddenLabels, enArea.hiddenLabels);
          if (layout == ReportLayout.wide) {
            final labellable = scenes[0].hiddenLabels + scenes[0].placedLabels;
            expect(scenes[0].hiddenLabels, lessThanOrEqualTo((labellable * 0.3).floor()));
            expect(scenes[1].hiddenLabels, lessThanOrEqualTo((m.facets.length * 0.3).floor()));
          }
          // Text items against the wide English scene: at most 30% of them are gone (wide only; the
          // compact plan is a quarter the size, so it hides more labels by design).
          final wideEn = LengthDiagram.build(m);
          if (layout == ReportLayout.wide) {
            expect(_texts(scenes[0]), greaterThanOrEqualTo((_texts(wideEn) * 0.7).ceil()),
                reason: '${_texts(scenes[0])} vs wide English ${_texts(wideEn)}');
          } else {
            expect(_texts(scenes[0]), _texts(enLen), reason: 'same text count as English compact, modulo ellipsis');
          }
          final svg = sceneToSvg(scenes[0]);
          if (m.edges.any((e) => e.type == EdgeType.eave)) {
            expect(svg, contains('Aleros'));
            expect(svg, contains(feetInches(RoofFigures.of(m).lengths[EdgeType.eave]!, labels: es)));
          }
          expect(sceneToSvg(scenes[2]), contains('Fuente'));
          expect(sceneToSvg(scenes[2]), isNot(contains('>Source<')));
        });
      }
    }

    test('a Spanish report builds a PDF', () async {
      final m = sampleModel();
      final bytes = await scenesToPdf([
        LengthDiagram.build(m, labels: es),
        AreaDiagram.build(m, labels: es),
        SummaryBlock.build(m, labels: es),
      ], labels: es);
      expect(String.fromCharCodes(bytes.sublist(0, 5)), '%PDF-');
    });
  });
}
