import 'dart:math' as math;

import 'labels.dart';
import 'layout.dart';
import 'model.dart';
import 'report_layout.dart';
import 'scene.dart';
import 'style.dart';

/// One chimney or lantern on the plan, in scene pixels: its outline ([polygon]) and the kind. The outline is the measured
/// polygon when the object has one, else the axis-aligned `size_ft` rectangle.
class ObjectMark {
  const ObjectMark(this.object, this.center, this.polygon);
  final RoofObject object;
  final Pt center;
  final List<Pt> polygon;

  double get _minX => polygon.map((p) => p.x).reduce(math.min);
  double get _maxX => polygon.map((p) => p.x).reduce(math.max);
  double get _minY => polygon.map((p) => p.y).reduce(math.min);
  double get _maxY => polygon.map((p) => p.y).reduce(math.max);

  /// Half extents of the bounding box.
  double get halfW => (_maxX - _minX) / 2;
  double get halfH => (_maxY - _minY) / 2;

  /// The shorter side of the outline's bounding box (the letter is sized from it).
  double get side => math.min(halfW, halfH) * 2;

  Obb get box => Obb(center.x, center.y, halfW, halfH);
}

/// The drawn objects of [m]: every chimney and lantern that stands on the roof (an `unknown` object, one off the roof, a
/// degenerate one and any object of a model with no geometry are never drawn). The outline is the object's polygon (or its
/// size rectangle) at the plan scale; an axis of its bounding box shorter than [minSide] pixels is stretched to [minSide]
/// about the centre, so the mark stays readable and a sliver can never blow up.
List<ObjectMark> objectMarks(RoofModel m, PlanFit fit, double minSide) {
  final out = <ObjectMark>[];
  for (final o in m.objects) {
    if (o.kind == ObjectKind.unknown || !m.objectOnRoof(o)) continue;
    final c = fit.map(o.center);
    final ring = o.polygon ??
        [
          (x: o.center.x - o.sizeFt.$1 / 2, y: o.center.y - o.sizeFt.$2 / 2),
          (x: o.center.x + o.sizeFt.$1 / 2, y: o.center.y - o.sizeFt.$2 / 2),
          (x: o.center.x + o.sizeFt.$1 / 2, y: o.center.y + o.sizeFt.$2 / 2),
          (x: o.center.x - o.sizeFt.$1 / 2, y: o.center.y + o.sizeFt.$2 / 2),
        ];
    var pts = fit.mapAll(ring);
    // A closed ring may repeat its first point.
    if (pts.length > 3 && pts.first == pts.last) pts = pts.sublist(0, pts.length - 1);
    if (pts.any((p) => !p.x.isFinite || !p.y.isFinite)) continue;
    final xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
    final minX = xs.reduce(math.min), maxX = xs.reduce(math.max), minY = ys.reduce(math.min), maxY = ys.reduce(math.max);
    final w = maxX - minX, h = maxY - minY;
    if (w < 1e-9 || h < 1e-9) continue; // no area: nothing to draw
    final bx = (minX + maxX) / 2, by = (minY + maxY) / 2;
    final kx = w < minSide ? minSide / w : 1.0, ky = h < minSide ? minSide / h : 1.0;
    if (kx != 1.0 || ky != 1.0) {
      pts = [for (final p in pts) (x: bx + (p.x - bx) * kx, y: by + (p.y - by) * ky)];
    }
    out.add(ObjectMark(o, c, pts));
  }
  return out;
}

/// Smallest side of an object mark in pixels: big enough to hold its one-letter mark in this layout.
double objectMinSide(ReportLayout layout, double k) => layout == ReportLayout.compact ? 18 : 18 * k;

/// The size of the mark letter inside a mark whose shorter side is [side].
double objectLetterSize(ReportLayout layout, double side, double k) =>
    layout == ReportLayout.compact ? ReportLayout.compactMinText : math.max(10.0, math.min(side * 0.7, 24 * k));

/// Draws [marks]: an outlined rectangle with a bold one-letter mark, never a facet. The letter is a label key.
void addObjectMarks(List<Prim> out, List<ObjectMark> marks, DiagramStyle style, RoofLabels labels, ReportLayout layout, double k) {
  for (final m in marks) {
    final kind = m.object.kind;
    out
      ..add(PolyPrim(pts: m.polygon, fill: style.objectFill, stroke: style.objectColorOf(kind), width: 2 * k))
      ..add(TextPrim(
        at: m.center,
        text: _letter(kind, labels),
        size: objectLetterSize(layout, m.side, k),
        color: style.objectColorOf(kind),
        bold: true,
      ));
  }
}

/// A mark for the legend: a square of [side] pixels centred at [c], with the letter at [letterSize].
void addObjectMark(List<Prim> out, Pt c, double side, ObjectKind kind, DiagramStyle style, RoofLabels labels,
    double letterSize, double k) {
  final h = side / 2;
  out
    ..add(PolyPrim(
      pts: [(x: c.x - h, y: c.y - h), (x: c.x + h, y: c.y - h), (x: c.x + h, y: c.y + h), (x: c.x - h, y: c.y + h)],
      fill: style.objectFill,
      stroke: style.objectColorOf(kind),
      width: 1.5 * k,
    ))
    ..add(TextPrim(at: c, text: _letter(kind, labels), size: letterSize, color: style.objectColorOf(kind), bold: true));
}

String _letter(ObjectKind kind, RoofLabels l) => kind == ObjectKind.lantern ? l.markLantern : l.markChimney;
