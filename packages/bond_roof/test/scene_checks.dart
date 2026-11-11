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
