import 'dart:math' as math;

import 'model.dart';
import 'scene.dart';

/// Diagonal hatch lines (45 degrees, rising to the right on screen) clipped to [poly], as plain
/// [LinePrim]s so SVG, PDF and the Flutter painter need no new primitive. [spacing] and [width]
/// are in scene pixels. Works for concave polygons (even-odd scanline per hatch line).
List<LinePrim> hatchLines(List<Pt> poly, {required double spacing, required double width, required int color}) {
  if (poly.length < 3 || spacing <= 0) return const [];
  // Hatch line: x + y = c (screen y is down, so this rises to the right).
  var lo = double.infinity, hi = -double.infinity;
  for (final p in poly) {
    lo = math.min(lo, p.x + p.y);
    hi = math.max(hi, p.x + p.y);
  }
  final out = <LinePrim>[];
  final step = spacing * math.sqrt2;
  for (var c = (lo / step).floor() * step + step / 2; c < hi; c += step) {
    // Parameterise along the line by x: points (x, c - x). Collect crossings with each edge.
    final xs = <double>[];
    for (var i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      final a = poly[j], b = poly[i];
      final da = a.x + a.y - c, db = b.x + b.y - c;
      if ((da < 0) == (db < 0)) continue;
      final t = da / (da - db);
      xs.add(a.x + (b.x - a.x) * t);
    }
    xs.sort();
    for (var k = 0; k + 1 < xs.length; k += 2) {
      if (xs[k + 1] - xs[k] < 1e-6) continue;
      out.add(LinePrim(
        a: (x: xs[k], y: c - xs[k]),
        b: (x: xs[k + 1], y: c - xs[k + 1]),
        color: color,
        width: width,
      ));
    }
  }
  return out;
}
