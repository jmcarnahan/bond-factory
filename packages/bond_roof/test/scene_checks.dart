import 'dart:math' as math;

import 'package:bond_roof/bond_roof.dart';
import 'package:bond_roof/src/layout.dart';
import 'package:test/test.dart';

/// Rough extent check for a text primitive: the rotated box around its anchor.
Obb textBox(TextPrim t) {
  final w = textWidth(t.text, t.size, bold: t.bold), h = t.size * 0.9;
  final off = switch (t.anchor) {
    TextAnchor.start => w / 2,
    TextAnchor.middle => 0.0,
    TextAnchor.end => -w / 2,
  };
  final a = t.angleDeg * math.pi / 180;
  return Obb(t.at.x + off * math.cos(a), t.at.y + off * math.sin(a), w / 2, h / 2, a);
}

void expectFits(Scene s) {
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
        for (final c in textBox(p).corners) {
          expect(inside(c), isTrue, reason: 'text "${p.text}" corner $c in ${s.width}x${s.height}');
        }
    }
  }
}

void expectWellFormedSvg(String svg) {
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

/// The length labels of [s] are upright, overlap nothing and touch no edge (the hatch is fill, not an edge). The plan starts
/// at the first facet polygon; the legend is drawn before it.
void expectLengthLabelsClean(Scene s) {
  const st = DiagramStyle.report;
  final facetFills = {st.flatFill, st.slopedFill, st.flatRoofFill};
  final plan = s.prims.skipWhile((p) => !(p is PolyPrim && facetFills.contains(p.fill))).toList();
  final labels = [
    for (final p in plan)
      if (p is TextPrim && RegExp(r'^\d+(, \d+ ft step)?$').hasMatch(p.text)) p
  ];
  expect(labels.length, s.placedLabels);
  final edges = [for (final p in plan) if (p is LinePrim && p.color != st.hatchColor) p];
  final boxes = <Obb>[];
  for (final l in labels) {
    expect(l.angleDeg, greaterThan(-90));
    expect(l.angleDeg, lessThanOrEqualTo(90));
    final b = textBox(l);
    for (final o in boxes) {
      expect(b.overlaps(o), isFalse, reason: 'label ${l.text} overlaps another label');
    }
    for (final e in edges) {
      expect(b.crossesSegment(e.a, e.b), isFalse, reason: 'label ${l.text} touches an edge');
    }
    boxes.add(b);
  }
}
