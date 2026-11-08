import 'dart:math' as math;

import 'package:bond_roof/bond_roof.dart';
import 'package:bond_roof/src/layout.dart';
import 'package:test/test.dart';

import 'support.dart';

/// Rough extent check for a text primitive: the rotated box around its anchor.
Obb _textBox(TextPrim t) {
  final w = textWidth(t.text, t.size, bold: t.bold), h = t.size * 0.9;
  final off = switch (t.anchor) {
    TextAnchor.start => w / 2,
    TextAnchor.middle => 0.0,
    TextAnchor.end => -w / 2,
  };
  final a = t.angleDeg * math.pi / 180;
  return Obb(t.at.x + off * math.cos(a), t.at.y + off * math.sin(a), w / 2, h / 2, a);
}

void _expectFits(Scene s) {
  const eps = 0.51;
  bool inside(Pt p) => p.x >= -eps && p.y >= -eps && p.x <= s.width + eps && p.y <= s.height + eps;
  for (final p in s.prims) {
    switch (p) {
      case LinePrim():
        expect(inside(p.a) && inside(p.b), isTrue, reason: 'line $p.a $p.b');
      case PolyPrim():
        for (final q in p.pts) {
          expect(inside(q), isTrue, reason: 'poly point $q');
        }
      case TextPrim():
        for (final c in _textBox(p).corners) {
          expect(inside(c), isTrue, reason: 'text "${p.text}" corner $c in ${s.width}x${s.height}');
        }
    }
  }
}

void _expectWellFormedSvg(String svg) {
  expect(svg.startsWith('<svg'), isTrue);
  expect(svg.trimRight().endsWith('</svg>'), isTrue);
  expect('<'.allMatches(svg).length, '>'.allMatches(svg).length);
  expect('<text'.allMatches(svg).length, '</text>'.allMatches(svg).length);
  expect('<title>'.allMatches(svg).length, '</title>'.allMatches(svg).length);
  expect('<svg'.allMatches(svg).length, 1);
  expect(RegExp(r'NaN|Infinity').hasMatch(svg), isFalse);
  // Every opening tag is either self-closed or closed explicitly.
  final open = RegExp(r'<([a-z]+)[^>]*?(/?)>').allMatches(svg);
  var depth = 0;
  for (final m in open) {
    if (m.group(2) == '/') continue;
    depth++;
  }
  expect(depth, '</'.allMatches(svg).length);
}

void main() {
  final fixtures = loadFixtures();
  test('fixtures found', () => expect(fixtures.length, greaterThanOrEqualTo(2)));

  test('palette covers every edge type', () {
    for (final t in EdgeType.values) {
      expect(DiagramStyle.roofr.edgeColors.containsKey(t), isTrue, reason: t.json);
    }
    // Pinned to the contract's hex values (docs/contracts/roof_model.md section 4), not to the code.
    const contract = <EdgeType, int>{
      EdgeType.eave: 0xFF2E7D32,
      EdgeType.ridge: 0xFF8BC34A,
      EdgeType.hip: 0xFF5E35B1,
      EdgeType.valley: 0xFFE53935,
      EdgeType.rake: 0xFFFBC02D,
      EdgeType.stepFlashing: 0xFF8D6E63,
      EdgeType.wallFlashing: 0xFF1E88E5,
      EdgeType.parapet: 0xFFFB8C00,
      EdgeType.transition: 0xFFD81B60,
      EdgeType.unspecified: 0xFF26A69A,
    };
    expect(contract.length, 10);
    for (final e in contract.entries) {
      expect(DiagramStyle.roofr.edgeColors[e.key], e.value, reason: e.key.json);
    }
    expect(DiagramStyle.roofr.flatFill, 0xFFE3F2FD);
    expect(DiagramStyle.roofr.slopedFill, 0xFFFFF8E1);
    expect(DiagramStyle.roofr.dashedTypes, {EdgeType.stepFlashing, EdgeType.wallFlashing});
  });

  for (final f in fixtures) {
    group(f.name, () {
      final m = RoofModel.fromJson(f.json);

      for (final size in [(1600.0, 1000.0), (800.0, 600.0)]) {
        test('length diagram ${size.$1.toInt()}x${size.$2.toInt()}', () {
          final s = LengthDiagram.build(m, width: size.$1, height: size.$2);
          expect(s.width, size.$1);
          final labellable = m.edges.where((e) => !isHoleOutlineEdge(m, e)).length;
          expect(s.hiddenLabels + s.placedLabels, labellable);
          expect(s.hiddenLabels, lessThanOrEqualTo((labellable * 0.3).floor()),
              reason: '${s.hiddenLabels} of $labellable hidden');
          _expectFits(s);
          _expectWellFormedSvg(sceneToSvg(s));
        });

        test('area diagram ${size.$1.toInt()}x${size.$2.toInt()}', () {
          final s = AreaDiagram.build(m, width: size.$1, height: size.$2);
          expect(s.hiddenLabels + s.placedLabels, m.facets.length);
          expect(s.hiddenLabels, lessThanOrEqualTo((m.facets.length * 0.3).floor()));
          _expectFits(s);
          _expectWellFormedSvg(sceneToSvg(s));
        });
      }

      test('every edge type used is drawn in its palette colour', () {
        final s = LengthDiagram.build(m);
        final colours = <int>{for (final p in s.prims) if (p is LinePrim) p.color};
        for (final e in m.edges) {
          expect(colours, contains(DiagramStyle.roofr.edgeColors[e.type]), reason: e.type.json);
        }
      });

      test('length labels: upright, no label overlap, no edge crossed', () {
        final s = LengthDiagram.build(m);
        final labels = [
          for (final p in s.prims)
            if (p is TextPrim && RegExp(r'^\d+$').hasMatch(p.text)) p
        ];
        expect(labels.length, s.placedLabels);
        final edges = [
          for (final p in s.prims)
            if (p is LinePrim && p.a.y > 200) p // plan edges only; the legend is above
        ];
        final boxes = <Obb>[];
        for (final l in labels) {
          expect(l.angleDeg, greaterThan(-90));
          expect(l.angleDeg, lessThanOrEqualTo(90));
          final b = _textBox(l);
          for (final o in boxes) {
            expect(b.overlaps(o), isFalse, reason: 'label ${l.text} overlaps another label');
          }
          for (final e in edges) {
            expect(b.crossesSegment(e.a, e.b), isFalse, reason: 'label ${l.text} touches an edge');
          }
          boxes.add(b);
        }
      });

      test('summary block builds and grows with content', () {
        final s = SummaryBlock.build(m);
        expect(s.height, greaterThan(200));
        _expectFits(s);
        _expectWellFormedSvg(sceneToSvg(s));
        expect(sceneToSvg(s), contains(sqft(m.totals.totalAreaSqft)));
      });
    });
  }

  test('site1_truth: hole-outline edges carry no label, legend totals unchanged', () {
    final m = RoofModel.fromJson(fixtures.firstWhere((f) => f.name == 'site1_truth').json);
    final holeEdges = m.edges.where((e) => isHoleOutlineEdge(m, e)).toList();
    expect(holeEdges.length, greaterThanOrEqualTo(17 * 4 - 8));
    final s = LengthDiagram.build(m);
    expect(s.placedLabels, lessThanOrEqualTo(m.edges.length - holeEdges.length));
    expect(s.hiddenLabels + s.placedLabels, m.edges.length - holeEdges.length);
    final digits = s.prims.whereType<TextPrim>().where((p) => RegExp(r'^\d+$').hasMatch(p.text)).length;
    expect(digits, s.placedLabels);
    // Hole edges are still drawn, dashed where the palette says so.
    final drawn = s.prims.whereType<LinePrim>().length;
    expect(drawn, greaterThanOrEqualTo(m.edges.length));
    // Legend totals come from the model and still print the full wall-flashing length.
    final svg = sceneToSvg(s);
    expect(svg, contains(feetInches(m.totals.lengthsFt[EdgeType.wallFlashing]!)));
    expect(svg, contains(feetInches(m.totals.lengthsFt[EdgeType.stepFlashing]!)));
  });

  test('length legend prints Xft Yin and all ten names', () {
    final m = loadModels().first;
    final svg = sceneToSvg(LengthDiagram.build(m));
    expect(svg, contains(feetInches(m.totals.lengthsFt[EdgeType.eave]!)));
    for (final n in ['Eaves', 'Rakes', 'Ridges', 'Hips', 'Valleys', 'Step flashing', 'Wall flashing', 'Parapet', 'Transition', 'Unspecified']) {
      expect(svg, contains(n));
    }
    expect(svg, contains('Measurements in diagram are rounded for display.'));
  });

  test('area diagram shows pitch and area labels and n/a totals', () {
    final svg = sceneToSvg(AreaDiagram.build(RoofModel.fromJson(fixtures.firstWhere((f) => f.name == 'minimal_hip').json)));
    expect(svg, contains('>4/12<'));
    expect(svg, contains('>n/a<'));
    expect(svg, contains('959 sq ft'));
  });

  test('minimal_hip length diagram prints exactly the nine expected labels', () {
    final m = RoofModel.fromJson(fixtures.firstWhere((f) => f.name == 'minimal_hip').json);
    final s = LengthDiagram.build(m);
    final labels = [
      for (final p in s.prims)
        if (p is TextPrim && RegExp(r'^\d+$').hasMatch(p.text)) p.text
    ]..sort();
    expect(labels, ['19', '19', '19', '19', '26', '26', '35', '35', '9']);
    expect(s.hiddenLabels, 0);
  });

  test('mixed_flat_hip area diagram header and labels', () {
    final m = RoofModel.fromJson(fixtures.firstWhere((f) => f.name == 'mixed_flat_hip').json);
    final s = AreaDiagram.build(m);
    final texts = [for (final p in s.prims) if (p is TextPrim) p.text];
    int count(String t) => texts.where((x) => x == t).length;
    expect(texts, containsAll(['2,017 sq ft', '830 sq ft', '1,187 sq ft', 'Total area', 'Total flat area']));
    expect(count('1,187 sq ft'), 2); // flat area and predominant pitch area
    expect(count('Flat'), 2); // the predominant pitch value and the flat facet's label
    expect(count('6/12'), 4);
    expect(count('4/12'), 4);
    expect(count('n/a'), 3);
    expect(s.hiddenLabels, 0);
  });

  test('control characters are stripped from SVG text', () {
    final json = Map.of(loadFixtures().first.json);
    json['address'] = {'formatted': 'A\u0001B\u0008C\u000bD\tE'};
    final svg = sceneToSvg(LengthDiagram.build(RoofModel.fromJson(json)));
    expect(svg, contains('>ABCD\tE<'));
    expect(RegExp(r'[\x00-\x08\x0B-\x1F]').hasMatch(svg), isFalse);
  });

  test('empty model does not throw', () {
    const m = RoofModel(totals: RoofTotals(
      totalAreaSqft: 0, pitchedAreaSqft: 0, flatAreaSqft: 0, predominantPitchRise: 0,
      predominantPitchAreaSqft: 0, squares: 0, lengthsFt: {},
    ));
    expect(LengthDiagram.build(m).prims, isNotEmpty);
    expect(AreaDiagram.build(m).prims, isNotEmpty);
    expect(SummaryBlock.build(m).prims, isNotEmpty);
  });

  test('text is XML-escaped in SVG', () {
    final json = Map.of(loadFixtures().first.json);
    json['address'] = {'formatted': 'A & B <St> "x"'};
    final svg = sceneToSvg(LengthDiagram.build(RoofModel.fromJson(json)));
    expect(svg, contains('A &amp; B &lt;St&gt; &quot;x&quot;'));
  });
}
