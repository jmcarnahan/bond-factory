import 'dart:math' as math;

import 'metrics.dart';
import 'model.dart';
import 'scene.dart';
import 'style.dart';

/// Oriented rectangle (centre, half extents, rotation in radians) used for label collisions.
class Obb {
  const Obb(this.cx, this.cy, this.hw, this.hh, [this.angle = 0]);

  final double cx, cy, hw, hh, angle;

  Pt get _u => (x: math.cos(angle), y: math.sin(angle));
  Pt get _v => (x: -math.sin(angle), y: math.cos(angle));

  List<Pt> get corners {
    final u = _u, v = _v;
    return [
      for (final (sx, sy) in const [(-1, -1), (1, -1), (1, 1), (-1, 1)])
        (x: cx + u.x * hw * sx + v.x * hh * sy, y: cy + u.y * hw * sx + v.y * hh * sy),
    ];
  }

  /// Separating axis test.
  bool overlaps(Obb o, {double margin = 0}) {
    final axes = [_u, _v, o._u, o._v];
    for (final ax in axes) {
      double radius(Obb b, double m) {
        final u = b._u, v = b._v;
        return (b.hw + m) * (ax.x * u.x + ax.y * u.y).abs() + (b.hh + m) * (ax.x * v.x + ax.y * v.y).abs();
      }

      final d = ((o.cx - cx) * ax.x + (o.cy - cy) * ax.y).abs();
      if (d > radius(this, margin) + radius(o, 0)) return false;
    }
    return true;
  }

  /// True when any part of segment a-b lies within the box grown by [margin] (Liang-Barsky).
  bool crossesSegment(Pt a, Pt b, {double margin = 0}) {
    final u = _u, v = _v;
    double lx(Pt p) => (p.x - cx) * u.x + (p.y - cy) * u.y;
    double ly(Pt p) => (p.x - cx) * v.x + (p.y - cy) * v.y;
    final x0 = lx(a), y0 = ly(a), dx = lx(b) - x0, dy = ly(b) - y0;
    var t0 = 0.0, t1 = 1.0;
    bool clip(double p, double q) {
      if (p == 0) return q >= 0;
      final r = q / p;
      if (p < 0) {
        if (r > t1) return false;
        if (r > t0) t0 = r;
      } else {
        if (r < t0) return false;
        if (r < t1) t1 = r;
      }
      return true;
    }

    final w = hw + margin, h = hh + margin;
    return clip(-dx, x0 + w) && clip(dx, w - x0) && clip(-dy, y0 + h) && clip(dy, h - y0);
  }

  bool insideRect(double l, double t, double r, double b) =>
      corners.every((c) => c.x >= l && c.x <= r && c.y >= t && c.y <= b);
}

class Seg {
  const Seg(this.a, this.b);
  final Pt a, b;
  double get length => math.sqrt(math.pow(b.x - a.x, 2) + math.pow(b.y - a.y, 2));
}

/// Greedy label placer. Labels go along edges, on the outward side first, then the inward
/// side, sliding along the edge if the middle is taken. A candidate is rejected when it leaves
/// the drawing area, overlaps a placed label or a reserved box, or touches ANY edge.
class LabelPlacer {
  /// Shortest edge, as a fraction of the label width, that may still carry a label.
  static const double shortEdgeFactor = 0.5;

  LabelPlacer({
    required this.edges,
    required this.area,
    this.reserved = const [],
    this.clearance = 1.5,
  });

  final List<Seg> edges;
  final ({double l, double t, double r, double b}) area;
  final List<Obb> reserved;
  final double clearance;
  final List<Obb> placed = [];

  bool _fits(Obb box) {
    if (!box.insideRect(area.l, area.t, area.r, area.b)) return false;
    for (final o in placed) {
      if (box.overlaps(o, margin: 2)) return false;
    }
    for (final o in reserved) {
      if (box.overlaps(o)) return false;
    }
    for (final s in edges) {
      if (box.crossesSegment(s.a, s.b, margin: clearance)) return false;
    }
    return true;
  }

  /// Tries to place a [w] x [h] label along [seg]; [centroid] decides which side is outward.
  /// Returns the box (already registered) or null when the label must be hidden.
  Obb? placeAlong(Seg seg, double w, double h, Pt centroid, {double strokeWidth = 3}) {
    final len = seg.length;
    final pad = 4.0;
    // The label sits beside the edge, not on it, so an edge may be shorter than its label: it
    // only has to be at least half as long. Collision checks below still decide.
    if (len < shortEdgeFactor * w) return null;
    var ang = math.atan2(seg.b.y - seg.a.y, seg.b.x - seg.a.x);
    if (ang > math.pi / 2 + 1e-9) ang -= math.pi;
    if (ang <= -math.pi / 2 + 1e-9) ang += math.pi;
    var nx = -math.sin(ang), ny = math.cos(ang);
    final mid = (x: (seg.a.x + seg.b.x) / 2, y: (seg.a.y + seg.b.y) / 2);
    if ((mid.x - centroid.x) * nx + (mid.y - centroid.y) * ny < 0) {
      nx = -nx;
      ny = -ny;
    }
    final hw = w / 2 + 1.5, hh = h * 0.55;
    final off = hh + strokeWidth / 2 + 2.5;
    final ux = math.cos(ang), uy = math.sin(ang);
    // Shifts along the edge, as a fraction of the room left on each side of the label.
    final room = math.max(0.0, (len - w - 2 * pad) / 2);
    final shifts = <double>[0];
    if (room > 0) {
      for (final f in const [0.35, 0.7, 1.0]) {
        shifts..add(f * room)..add(-f * room);
      }
    }
    for (final side in const [1.0, -1.0]) {
      for (final s in shifts) {
        final cx = mid.x + ux * s + nx * off * side, cy = mid.y + uy * s + ny * off * side;
        final box = Obb(cx, cy, hw, hh, ang);
        if (_fits(box)) {
          placed.add(box);
          return box;
        }
      }
    }
    return null;
  }
}

/// Maps model feet (y north) into a pixel rectangle (y down), keeping the aspect ratio and
/// centring the model.
class PlanFit {
  PlanFit(RoofModel m, {required double left, required double top, required double right, required double bottom}) {
    final b = m.bounds;
    minX = b.min.x;
    minY = b.min.y;
    final w = math.max(b.max.x - b.min.x, 1e-6), h = math.max(b.max.y - b.min.y, 1e-6);
    scale = math.min((right - left) / w, (bottom - top) / h);
    ox = left + ((right - left) - w * scale) / 2;
    oy = bottom - ((bottom - top) - h * scale) / 2;
  }

  late final double minX, minY, scale, ox, oy;

  Pt map(Pt p) => (x: ox + (p.x - minX) * scale, y: oy - (p.y - minY) * scale);
  List<Pt> mapAll(List<Pt> ps) => [for (final p in ps) map(p)];
}

/// Area-weighted centroid of the facets (falls back to the bounds centre), in model space.
Pt roofCentroid(RoofModel m) {
  var a = 0.0, cx = 0.0, cy = 0.0;
  for (final f in m.facets) {
    var fa = 0.0, fx = 0.0, fy = 0.0;
    final p = f.polygon;
    for (var i = 0, j = p.length - 1; i < p.length; j = i++) {
      final c = p[j].x * p[i].y - p[i].x * p[j].y;
      fa += c;
      fx += (p[j].x + p[i].x) * c;
      fy += (p[j].y + p[i].y) * c;
    }
    if (fa.abs() < 1e-9) continue;
    final w = fa.abs() / 2;
    cx += fx / (3 * fa) * w;
    cy += fy / (3 * fa) * w;
    a += w;
  }
  if (a > 0) return (x: cx / a, y: cy / a);
  final b = m.bounds;
  return (x: (b.min.x + b.max.x) / 2, y: (b.min.y + b.max.y) / 2);
}

/// Shrinks [size] (never below [minSize]) until [text] fits in [maxWidth].
double fitSize(String text, double maxWidth, double size, double minSize, {bool bold = false}) {
  final w = textWidth(text, size, bold: bold);
  return w <= maxWidth ? size : math.max(minSize, size * maxWidth / w);
}

/// Greedy word wrap using Helvetica metrics.
List<String> wrapText(String text, double maxWidth, double size, {bool bold = false}) {
  final lines = <String>[];
  var cur = '';
  for (final word in text.split(RegExp(r'\s+')).where((w) => w.isNotEmpty)) {
    final next = cur.isEmpty ? word : '$cur $word';
    if (cur.isNotEmpty && textWidth(next, size, bold: bold) > maxWidth) {
      lines.add(cur);
      cur = word;
    } else {
      cur = next;
    }
  }
  if (cur.isNotEmpty) lines.add(cur);
  return lines;
}

/// Scale factor for a scene relative to the 1600 x 1000 design size.
double sceneScale(double width, double height) => math.max(0.4, math.min(width / 1600, height / 1000));

/// Adds a compass rose centred at [c] with radius [r] (north up).
void addCompass(List<Prim> out, Pt c, double r, DiagramStyle style, double k, {String north = 'N'}) {
  final n = (x: c.x, y: c.y - r);
  final s = (x: c.x, y: c.y + r);
  final w = r * 0.28;
  out
    ..add(PolyPrim(
      pts: [n, (x: c.x + w, y: c.y), (x: c.x - w, y: c.y)],
      fill: style.textColor,
      stroke: style.textColor,
      width: 1,
    ))
    ..add(PolyPrim(
      pts: [s, (x: c.x + w, y: c.y), (x: c.x - w, y: c.y)],
      fill: 0xFFFFFFFF,
      stroke: style.textColor,
      width: 1.2 * k,
    ))
    ..add(TextPrim(
      at: (x: c.x, y: c.y - r - 13 * k),
      text: north,
      size: 16 * k,
      color: style.textColor,
      bold: true,
    ));
}

/// Adds the footer line, left aligned, at the bottom of the scene.
void addFooter(List<Prim> out, String text, double width, double height, DiagramStyle style, double k,
    {double? size}) {
  size ??= 13 * k;
  final lines = wrapText(text, width - 48 * k - 150 * k, size);
  for (final (i, l) in lines.indexed) {
    out.add(TextPrim(
      at: (x: 48 * k, y: height - 26 * k - (lines.length - 1 - i) * size * 1.4),
      text: l,
      size: size,
      color: 0xFF616161,
      anchor: TextAnchor.start,
    ));
  }
}
