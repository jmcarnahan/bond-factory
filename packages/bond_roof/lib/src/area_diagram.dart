import 'dart:math' as math;

import 'format.dart';
import 'layout.dart';
import 'metrics.dart';
import 'model.dart';
import 'polylabel.dart';
import 'scene.dart';
import 'style.dart';

/// Plan view with facet outlines and a two-line label per facet (pitch, then area), dashed
/// holes, and the eight totals in a block at the top.
class AreaDiagram {
  const AreaDiagram._();

  static Scene build(
    RoofModel m, {
    double width = 1600,
    double height = 1000,
    DiagramStyle style = DiagramStyle.report,
  }) {
    final k = sceneScale(width, height);
    final prims = <Prim>[];
    final t = m.totals;

    prims
      ..add(TextPrim(
        at: (x: 48 * k, y: 40 * k),
        text: m.address.display.isEmpty ? 'Roof area diagram' : m.address.display,
        size: 25 * k,
        color: style.textColor,
        anchor: TextAnchor.start,
        bold: true,
      ))
      ..add(TextPrim(
        at: (x: 48 * k, y: 66 * k),
        text: 'Area diagram',
        size: 14 * k,
        color: 0xFF757575,
        anchor: TextAnchor.start,
      ));
    String sq(double v) => '${sqft(v)} sq ft';
    final cells = <(String, String)>[
      ('Total area', sq(t.totalAreaSqft)),
      ('Total pitched area', sq(t.pitchedAreaSqft)),
      ('Total flat area', sq(t.flatAreaSqft)),
      ('Predominant pitch', pitchLabel(t.predominantPitchRise)),
      ('Predominant pitch area', sq(t.predominantPitchAreaSqft)),
      ('Two-story area', 'n/a'),
      ('Two-layer area', 'n/a'),
      ('Unspecified pitch area', 'n/a'),
    ];
    final colW = (width - 96 * k) / 4;
    for (final (i, c) in cells.indexed) {
      final x0 = 48 * k + (i % 4) * colW, y0 = (96 + (i ~/ 4) * 58) * k;
      prims
        ..add(TextPrim(at: (x: x0, y: y0), text: c.$1, size: 13 * k, color: 0xFF757575, anchor: TextAnchor.start))
        ..add(TextPrim(
          at: (x: x0, y: y0 + 24 * k),
          text: c.$2,
          size: 22 * k,
          color: c.$2 == 'n/a' ? 0xFF9E9E9E : style.textColor,
          anchor: TextAnchor.start,
          bold: true,
        ));
    }

    final area = (l: 56 * k, t: 214 * k, r: width - 56 * k, b: height - 96 * k);
    final fit = PlanFit(m, left: area.l + 12 * k, top: area.t + 18 * k, right: area.r - 12 * k, bottom: area.b - 12 * k);
    final polys = [for (final f in m.facets) fit.mapAll(f.polygon)];
    final holes = [for (final h in m.holes) fit.mapAll(h.polygon)];
    for (final (i, f) in m.facets.indexed) {
      prims.add(PolyPrim(
        pts: polys[i],
        fill: f.kind == FacetKind.flat ? style.flatFill : style.slopedFill,
        stroke: 0xFF455A64,
        width: 1.8 * k,
      ));
    }
    for (final h in m.holes) {
      prims.add(PolyPrim(
        pts: fit.mapAll(h.polygon),
        stroke: style.holeStroke,
        width: 1.8 * k,
        dashed: true,
      ));
    }

    // Facet labels at the pole of inaccessibility; shrink the text until the label box fits
    // inside the facet, hide it if it never does.
    final maxSize = math.max(10.0, style.fontSize * 1.2 * k);
    final minSize = 8.5 * k;
    var hidden = 0, placed = 0;
    final labelPrims = <Prim>[];
    for (final (i, f) in m.facets.indexed) {
      final pole = polylabel([polys[i]], precision: 0.5 * k);
      final line1 = pitchLabel(f.kind == FacetKind.flat ? 0 : f.pitchRise);
      final line2 = sqft(f.areaSqft);
      double? chosen;
      var at = pole.point;
      // Candidate centres: the pole first, then a grid of points inside the facet, nearest first.
      List<Pt>? grid;
      search:
      for (var s = maxSize; s >= minSize; s -= 0.5) {
        final hw = (math.max(textWidth(line1, s, bold: true), textWidth(line2, s)) + 4) / 2;
        final hh = s * 2.35 / 2;
        if (_labelFits(polys[i], holes, pole.point, hw, hh)) {
          chosen = s;
          at = pole.point;
          break;
        }
        grid ??= _grid(polys[i], pole.point, 5 * k);
        for (final c in grid) {
          if (_labelFits(polys[i], holes, c, hw, hh)) {
            chosen = s;
            at = c;
            break search;
          }
        }
      }
      if (chosen == null) {
        hidden++;
        continue;
      }
      placed++;
      labelPrims
        ..add(TextPrim(
          at: (x: at.x, y: at.y - chosen * 0.62),
          text: line1,
          size: chosen,
          color: style.textColor,
          bold: true,
        ))
        ..add(TextPrim(
          at: (x: at.x, y: at.y + chosen * 0.62),
          text: line2,
          size: chosen,
          color: style.textColor,
        ));
    }
    prims.addAll(labelPrims);

    addCompass(prims, (x: width - 76 * k, y: height - 54 * k), 28 * k, style, k);
    addFooter(prims, footerArea, width, height, style, k);

    return Scene(
      width: width,
      height: height,
      background: style.background,
      prims: prims,
      hiddenLabels: hidden,
      placedLabels: placed,
      title: 'Area diagram',
    );
  }

  /// Grid points inside [poly] at least a few steps from its outline, nearest to [near] first.
  static List<Pt> _grid(List<Pt> poly, Pt near, double step) {
    var minX = double.infinity, minY = double.infinity, maxX = -double.infinity, maxY = -double.infinity;
    for (final p in poly) {
      minX = math.min(minX, p.x);
      minY = math.min(minY, p.y);
      maxX = math.max(maxX, p.x);
      maxY = math.max(maxY, p.y);
    }
    final pts = <Pt>[];
    for (var x = minX + step; x < maxX; x += step) {
      for (var y = minY + step; y < maxY; y += step) {
        if (signedDistanceToPolygon((x: x, y: y), poly) > step) pts.add((x: x, y: y));
      }
    }
    double d(Pt p) => math.pow(p.x - near.x, 2) + math.pow(p.y - near.y, 2).toDouble();
    pts.sort((a, b) => d(a).compareTo(d(b)));
    return pts;
  }

  /// True when the axis-aligned box centred at [c] lies inside [poly] and clear of every hole.
  static bool _labelFits(List<Pt> poly, List<List<Pt>> holes, Pt c, double hw, double hh) {
    if (!_boxInside(poly, c, hw, hh)) return false;
    final box = Obb(c.x, c.y, hw, hh);
    for (final h in holes) {
      if (pointInPolygon(c, h)) return false;
      for (var i = 0, j = h.length - 1; i < h.length; j = i++) {
        if (box.crossesSegment(h[j], h[i], margin: 3)) return false;
      }
    }
    return true;
  }

  /// True when the axis-aligned box centred at [c] lies inside [poly] (perimeter sampled, and no
  /// polygon vertex pokes into the box).
  static bool _boxInside(List<Pt> poly, Pt c, double hw, double hh) {
    const steps = 6;
    for (var i = 0; i <= steps; i++) {
      final fx = -hw + 2 * hw * i / steps, fy = -hh + 2 * hh * i / steps;
      for (final p in [
        (x: c.x + fx, y: c.y - hh),
        (x: c.x + fx, y: c.y + hh),
        (x: c.x - hw, y: c.y + fy),
        (x: c.x + hw, y: c.y + fy),
      ]) {
        if (!pointInPolygon(p, poly)) return false;
      }
    }
    for (final v in poly) {
      if ((v.x - c.x).abs() < hw && (v.y - c.y).abs() < hh) return false;
    }
    return true;
  }
}
