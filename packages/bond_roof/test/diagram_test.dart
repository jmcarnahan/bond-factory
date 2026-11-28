import 'package:bond_roof/bond_roof.dart';
import 'package:test/test.dart';

import 'scene_checks.dart';
import 'support.dart';

const _style = DiagramStyle.report;

void main() {
  final m = sampleModel();

  test('palette covers every edge type and keeps the contract colours', () {
    for (final t in EdgeType.values) {
      expect(_style.edgeColors.containsKey(t), isTrue, reason: t.json);
    }
    const contract = <EdgeType, int>{
      EdgeType.eave: 0xFF2E7D32,
      EdgeType.ridge: 0xFF8BC34A,
      EdgeType.hip: 0xFF5E35B1,
      EdgeType.valley: 0xFFE53935,
      EdgeType.rake: 0xFFFBC02D,
      EdgeType.stepFlashing: 0xFF8D6E63,
      EdgeType.wallFlashing: 0xFF1E88E5,
      EdgeType.transition: 0xFFD81B60,
      EdgeType.unspecified: 0xFF26A69A,
    };
    for (final e in contract.entries) {
      expect(_style.edgeColors[e.key], e.value, reason: e.key.json);
    }
    expect(_style.flatFill, 0xFFE3F2FD);
    expect(_style.slopedFill, 0xFFFFF8E1);
    expect(_style.dashedTypes, {EdgeType.stepFlashing, EdgeType.wallFlashing});
  });

  for (final size in [(1600.0, 1000.0), (800.0, 600.0)]) {
    group('${size.$1.toInt()}x${size.$2.toInt()}', () {
      test('length diagram: fits, well-formed, every edge accounted for', () {
        final s = LengthDiagram.build(m, width: size.$1, height: size.$2);
        expect(s.width, size.$1);
        final labellable = m.edges.where((e) => e.type != EdgeType.flatSeam && !isHoleOutlineEdge(m, e)).length;
        expect(s.hiddenLabels + s.placedLabels, labellable);
        expect(s.hiddenLabels, lessThanOrEqualTo((labellable * 0.3).floor()), reason: '${s.hiddenLabels} of $labellable hidden');
        expectFits(s);
        expectWellFormedSvg(sceneToSvg(s));
      });

      test('area diagram: fits, well-formed, every facet labelled or counted hidden', () {
        final s = AreaDiagram.build(m, width: size.$1, height: size.$2);
        expect(s.hiddenLabels + s.placedLabels, m.facets.length);
        expect(s.hiddenLabels, lessThanOrEqualTo((m.facets.length * 0.3).floor()));
        expectFits(s);
        expectWellFormedSvg(sceneToSvg(s));
      });
    });
  }

  test('compact layout: 400 x 500, two columns, nothing renders under 12 px at a 358 px card', () {
    const compact = ReportLayout.compact;
    final len = LengthDiagram.build(m, layout: compact);
    final area = AreaDiagram.build(m, layout: compact);
    final sum = SummaryBlock.build(m, layout: compact);
    expect((len.width, len.height), (400.0, 500.0));
    expect((area.width, area.height), (400.0, 500.0));
    expect(sum.width, 400.0);
    const cardScale = 358 / 400;
    for (final s in [len, area, sum]) {
      expectFits(s);
      expectWellFormedSvg(sceneToSvg(s));
      for (final t in s.prims.whereType<TextPrim>()) {
        expect(t.size * cardScale, greaterThanOrEqualTo(12), reason: '"${t.text}" ${t.size} in ${s.title}');
      }
    }
    // Legend swatches: two columns compact, three wide.
    double legendCols(Scene s) => {
          for (final p in s.prims)
            if (p is LinePrim && p.a.y < 200 && p.b.x - p.a.x > 10 && (p.b.x - p.a.x) < 60) p.a.x.round()
        }.length.toDouble();
    expect(legendCols(len), 2);
    expect(legendCols(LengthDiagram.build(m)), 3);
    final labellable = m.edges.where((e) => !isHoleOutlineEdge(m, e)).length;
    expect(len.hiddenLabels + len.placedLabels, labellable);
    expect(area.hiddenLabels + area.placedLabels, m.facets.length);
  });

  group('the length legend lists only what the roof has', () {
    final texts = textsOf(LengthDiagram.build(m));

    test('names, in the owner\'s words', () {
      expect(texts, containsAll([
        'Eaves', 'Rakes', 'Flat roof edges', 'Exposed edges inside the roof', 'Eave + rake', 'Ridges', 'Ridge + hip',
        'Sidewall flashing', 'Headwall flashing', 'Transitions', 'Chimney', 'Roof lantern',
      ]));
      for (final gone in ['Hips', 'Valleys', 'Level changes', 'Unspecified', 'Step flashing', 'Wall flashing', 'Parapet walls']) {
        expect(texts, isNot(contains(gone)), reason: gone);
      }
    });

    test('values: the drawn sums, with feet and inches', () {
      final e = m.totals.engine!;
      expect(texts, containsAll([
        feetInches(e.eaveFt!), feetInches(e.eaveRakeFt!), feetInches(e.exposedEdgeFt!), feetInches(e.stepFlashingFt!),
        feetInches(e.wallFlashingFt!), feetInches(e.transitionFt!), feetInches(e.flatEdgeFt!), feetInches(e.rakeFt!),
      ]));
      expect(texts, contains('12ft 0in'));
      expect(texts, contains('9ft 0in'));
    });

    test('a roof with no hip, valley or step has none of those rows; a flat seam never has one', () {
      final j = sampleJson()['model'] as Map<String, dynamic>;
      j['edges'] = [for (final e in j['edges'] as List) if (const {'eave', 'ridge', 'rake'}.contains(e['type'])) e];
      j['totals'] = {'total_area_sqft': 1000.0};
      j['objects'] = <Object?>[];
      final t = textsOf(LengthDiagram.build(RoofModel.fromJson(j)));
      expect(t, containsAll(['Eaves', 'Rakes', 'Ridges']));
      for (final gone in ['Hips', 'Valleys', 'Sidewall flashing', 'Headwall flashing', 'Transitions', 'Chimney', 'Roof lantern', 'Flat roof seams']) {
        expect(t, isNot(contains(gone)), reason: gone);
      }
    });

    test('the footer says lengths are rounded', () {
      expect(sceneToSvg(LengthDiagram.build(m)), contains('Measurements in diagram are rounded for display.'));
    });
  });

  group('sidewall and headwall', () {
    final s = LengthDiagram.build(m);

    test('are drawn as different lines (colour) and both dashed', () {
      final side = _style.colorOf(EdgeType.stepFlashing), head = _style.colorOf(EdgeType.wallFlashing);
      expect(side, isNot(head));
      final lines = s.prims.whereType<LinePrim>();
      expect(lines.where((p) => p.color == side && p.dashed && p.width > 0), isNotEmpty);
      expect(lines.where((p) => p.color == head && p.dashed && p.width > 0), isNotEmpty);
    });

    test('carry their step in the label like a level change does: "12, 8 ft step", "9, 8 ft step"', () {
      expect(textsOf(s), containsAll(['12, 8 ft step', '9, 8 ft step']));
    });

    test('a jump under 3 ft, or none, shows the length only', () {
      final j = sampleJson()['model'] as Map<String, dynamic>;
      for (final e in j['edges'] as List) {
        if (e['type'] == 'step_flashing') e['jump_ft'] = 2.0;
        if (e['type'] == 'wall_flashing') e.remove('jump_ft');
      }
      final t = textsOf(LengthDiagram.build(RoofModel.fromJson(j)));
      expect(t.where((x) => x.contains('step')), isEmpty);
      expect(t, containsAll(['12', '9']));
    });
  });

  group('pitch labels: the whole number with the fit beside it', () {
    test('the area diagram labels each facet; 4.31 reads "4/12 (4.3)", 6.02 reads "6/12"', () {
      final j = sampleJson()['model'] as Map<String, dynamic>;
      for (final f in j['facets'] as List) {
        if (f['id'] == 'f3') f['pitch_rise'] = 4.31;
      }
      final t = textsOf(AreaDiagram.build(RoofModel.fromJson(j)));
      expect(t, contains('4/12 (4.3)'));
      expect(t.where((x) => x == '6/12'), isNotEmpty);
      expect(t, contains('Flat'));
    });

    test('the sample\'s own wing is 4.31', () {
      expect(textsOf(AreaDiagram.build(m)), contains('4/12 (4.3)'));
    });

    test('the area header and the summary show the weighted pitch the same way', () {
      expect(textsOf(AreaDiagram.build(m)), contains('6/12 (5.9)'));
      expect(textsOf(SummaryBlock.build(m)), contains('6/12 (5.9)'));
    });

    test('the footers no longer say pitch is rounded to the half', () {
      expect(sceneToSvg(AreaDiagram.build(m)), isNot(contains('nearest half')));
      expect(const RoofLabels().footerArea, isNot(contains('half')));
    });
  });

  group('the area header', () {
    test('shows the totals the roof has: area, pitched and flat roofing, pitch, chimneys, lanterns', () {
      final t = textsOf(AreaDiagram.build(m));
      expect(t, containsAll(['Total area', '1,418 sq ft', 'Pitched roofing', 'Flat roofing', 'Pitch', 'Chimneys', 'Roof lanterns']));
      for (final gone in ['n/a', 'Two-story area', 'Two-layer area', 'Unspecified pitch area', 'Predominant pitch']) {
        expect(t, isNot(contains(gone)), reason: gone);
      }
    });

    test('a roof of one kind has no pitched / flat split', () {
      final j = sampleJson()['model'] as Map<String, dynamic>;
      j['totals'] = {'area_sqft': 1000.0, 'roofing_pitched_sqft': 1000.0, 'roofing_flat_sqft': 0.0};
      j['objects'] = <Object?>[];
      final t = textsOf(AreaDiagram.build(RoofModel.fromJson(j)));
      expect(t, isNot(contains('Pitched roofing')));
      expect(t, isNot(contains('Chimneys')));
    });
  });

  group('summary block', () {
    final texts = textsOf(SummaryBlock.build(m));

    test('prints the totals rows of the roof', () {
      expect(texts, containsAll([
        'Total area', 'Pitch', 'Eaves', 'Rakes', 'Eave + rake', 'Ridges', 'Ridge + hip', 'Sidewall flashing', 'Headwall flashing',
        'Transitions', 'Chimneys', 'Facets', 'Confidence',
      ]));
      expect(texts, isNot(contains('Hips')));
      expect(texts, contains('1,418 sq ft  (14.18 squares)'));
    });

    test('the method is named, the plane engine reads as LiDAR + footprint', () {
      expect(texts, contains('Method: LiDAR point cloud + building footprint'));
      expect(texts.any((t) => t.contains('Solar')), isFalse);
    });

    test('grows with content and fits', () {
      final s = SummaryBlock.build(m);
      expect(s.height, greaterThan(200));
      expectFits(s);
      expectWellFormedSvg(sceneToSvg(s));
    });
  });

  test('length labels: upright, no label overlap, no edge crossed', () {
    expectLengthLabelsClean(LengthDiagram.build(m));
  });

  group('robustness', () {
    test('control characters are stripped from SVG text', () {
      final json = sampleJson()['model'] as Map<String, dynamic>;
      json['address'] = {'formatted': 'A\u0001B\u0008C\u000bD\tE'};
      final svg = sceneToSvg(LengthDiagram.build(RoofModel.fromJson(json)));
      expect(svg, contains('>ABCD\tE<'));
      expect(RegExp(r'[\x00-\x08\x0B-\x1F]').hasMatch(svg), isFalse);
    });

    test('text is XML-escaped in SVG', () {
      final json = sampleJson()['model'] as Map<String, dynamic>;
      json['address'] = {'formatted': 'A & B <St> "x"'};
      final svg = sceneToSvg(LengthDiagram.build(RoofModel.fromJson(json)));
      expect(svg, contains('A &amp; B &lt;St&gt; &quot;x&quot;'));
    });

    test('an empty model does not throw', () {
      const e = RoofModel(totals: RoofTotals(totalAreaSqft: 0, pitchedAreaSqft: 0, flatAreaSqft: 0, squares: 0, lengthsFt: {}));
      for (final layout in ReportLayout.values) {
        expect(LengthDiagram.build(e, layout: layout).prims, isNotEmpty);
        expect(AreaDiagram.build(e, layout: layout).prims, isNotEmpty);
        expect(SummaryBlock.build(e, layout: layout).prims, isNotEmpty);
      }
    });
  });
}
