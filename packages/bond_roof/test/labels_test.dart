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
      expect(d.copyWith({'legend_hip': null, 'squares': ''}), d);
    });

    test('equality follows the text; copyWith applies overrides', () {
      final es = RoofLabels.fromMap(spanishLabels);
      expect(es, isNot(const RoofLabels()));
      expect(es, RoofLabels.fromMap(spanishLabels));
      expect(es.hashCode, RoofLabels.fromMap(spanishLabels).hashCode);
      expect(const RoofLabels().copyWith({'squares': 'Sq'}).squares, 'Sq');
      expect(const RoofLabels().copyWith({'squares': 'Sq'}).facets, 'Facets');
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

    test('feetInches, pitchLabel and the n/a cell use the labels', () {
      final es = RoofLabels.fromMap(spanishLabels);
      expect(feetInches(209.67), '209ft 8in');
      expect(feetInches(209.67, labels: es), '209pies 8pulg');
      expect(pitchLabel(0.2), 'Flat');
      expect(pitchLabel(0.2, labels: es), 'Plano');
      final m = loadModels().first;
      final enArea = sceneToSvg(AreaDiagram.build(m));
      final esArea = sceneToSvg(AreaDiagram.build(m, labels: es));
      expect(enArea, contains('>n/a<'));
      expect(esArea, contains('>n/d<'));
      expect(esArea, isNot(contains('>n/a<')));
    });
  });

  group('Spanish labels render every fixture in both layouts', () {
    final es = RoofLabels.fromMap(spanishLabels);
    for (final f in loadFixtures()) {
      for (final layout in ReportLayout.values) {
        test('${f.name} ${layout.name}', () {
          final m = RoofModel.fromJson(f.json);
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
          // Longer text must not push labels off the plan: numeric labels hide exactly as in English.
          expect(scenes[0].hiddenLabels, enLen.hiddenLabels);
          expect(scenes[1].hiddenLabels, enArea.hiddenLabels);
          if (layout == ReportLayout.wide) {
            final labellable = scenes[0].hiddenLabels + scenes[0].placedLabels;
            expect(scenes[0].hiddenLabels, lessThanOrEqualTo((labellable * 0.3).floor()));
            expect(scenes[1].hiddenLabels, lessThanOrEqualTo((m.facets.length * 0.3).floor()));
          }
          // Text items against the wide English scene: at most 30% of them are gone.
          final wideEn = LengthDiagram.build(m);
          expect(_texts(scenes[0]), greaterThanOrEqualTo((_texts(wideEn) * 0.7).ceil()),
              reason: '${_texts(scenes[0])} vs wide English ${_texts(wideEn)}');
          final svg = sceneToSvg(scenes[0]);
          expect(svg, contains('Aleros'));
          expect(svg, contains(feetInches(m.totals.lengthsFt[EdgeType.eave]!, labels: es)));
          expect(sceneToSvg(scenes[2]), contains('Fuente'));
          expect(sceneToSvg(scenes[2]), isNot(contains('>Source<')));
        });
      }
    }

    test('a Spanish report builds a PDF', () async {
      final m = loadModels().first;
      final bytes = await scenesToPdf([
        LengthDiagram.build(m, labels: es),
        AreaDiagram.build(m, labels: es),
        SummaryBlock.build(m, labels: es),
      ], labels: es);
      expect(String.fromCharCodes(bytes.sublist(0, 5)), '%PDF-');
    });
  });
}
