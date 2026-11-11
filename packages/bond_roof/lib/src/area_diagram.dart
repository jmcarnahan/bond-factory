import 'dart:math' as math;

import 'format.dart';
import 'labels.dart';
import 'layout.dart';
import 'metrics.dart';
import 'model.dart';
import 'polylabel.dart';
import 'report_layout.dart';
import 'scene.dart';
import 'style.dart';

/// Plan view with facet outlines and a two-line label per facet (pitch, then area), dashed
/// holes, and the eight totals in a block at the top (four columns wide, two compact). All
/// text comes from [labels]; [layout] picks the page geometry.
class AreaDiagram {
  const AreaDiagram._();

  static Scene build(
    RoofModel m, {
    double? width,
    double? height,
    DiagramStyle style = DiagramStyle.report,
    RoofLabels labels = const RoofLabels(),
    ReportLayout layout = ReportLayout.wide,
  }) {
    width ??= layout.designWidth;
    height ??= layout.designHeight;
    final k = layoutScale(layout, width, height);
    final sp = LayoutSpec(layout, k);
    final prims = <Prim>[];
    final t = m.totals;

    final title = m.address.display.isEmpty ? labels.areaTitle : m.address.display;
    prims
      ..add(TextPrim(
        at: (x: sp.margin, y: sp.titleY),
        text: title,
        size: fitSize(title, width - 2 * sp.margin, sp.titleSize, sp.titleMin, bold: true),
        color: style.textColor,
        anchor: TextAnchor.start,
        bold: true,
      ))
      ..add(TextPrim(
        at: (x: sp.margin, y: sp.captionY),
        text: labels.areaCaption,
        size: sp.captionSize,
        color: 0xFF757575,
        anchor: TextAnchor.start,
      ));
    String sq(double v) => '${sqft(v)} ${labels.unitSqft}';
    // A null value is "not available" (drawn grey); the cell is chosen by the null, not by text.
    final cells = <(String, String?)>[
      (labels.totalArea, sq(t.totalAreaSqft)),
      (labels.totalPitchedArea, sq(t.pitchedAreaSqft)),
      (labels.totalFlatArea, sq(t.flatAreaSqft)),
      (labels.predominantPitch, pitchLabel(t.predominantPitchRise, labels: labels)),
      (labels.predominantPitchArea, sq(t.predominantPitchAreaSqft)),
      (labels.twoStoryArea, null),
      (labels.twoLayerArea, null),
      (labels.unspecifiedPitchArea, null),
    ];
    final cols = layout.figureColumns;
    final colW = (width - 2 * sp.margin) / cols;
    final rows = ReportLayout.rowsFor(cells.length, cols);
    for (final (i, c) in cells.indexed) {
      final x0 = sp.margin + (i % cols) * colW, y0 = sp.areaHeaderTop + (i ~/ cols) * sp.areaRowPitch;
      final capText = layout == ReportLayout.wide ? c.$1 : ellipsize(c.$1, colW - 6, sp.areaCaptionSize);
      prims
        ..add(TextPrim(at: (x: x0, y: y0), text: capText, size: sp.areaCaptionSize, color: 0xFF757575, anchor: TextAnchor.start))
        ..add(TextPrim(
          at: (x: x0, y: y0 + sp.areaValueDy),
          text: c.$2 ?? labels.notAvailable,
          size: sp.areaValueSize,
          color: c.$2 == null ? 0xFF9E9E9E : style.textColor,
          anchor: TextAnchor.start,
          bold: true,
        ));
    }

    final footer = footerLines(labels.footerArea, width, sp);
    final bottomReserve = layout == ReportLayout.wide ? sp.planBottomMin : math.max(sp.planBottomMin, footerHeight(footer, sp));
    final area = (
      l: sp.planSide,
      t: sp.areaHeaderTop + sp.areaPlanPad + rows * sp.areaRowPitch,
      r: width - sp.planSide,
      b: height - bottomReserve,
    );
    final fit = PlanFit(m,
        left: area.l + sp.planInsetX, top: area.t + sp.planInsetTop, right: area.r - sp.planInsetX, bottom: area.b - sp.planInsetBottom);
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
    final maxSize = layout == ReportLayout.wide ? math.max(layout.minLabelSize, style.fontSize * 1.2 * k) : 16.0;
    final minSize = layout == ReportLayout.wide ? 8.5 * k : layout.minLabelSize;
    var hidden = 0, placed = 0;
    final labelPrims = <Prim>[];
    for (final (i, f) in m.facets.indexed) {
      final pole = polylabel([polys[i]], precision: 0.5 * k);
      final line1 = pitchLabel(f.kind == FacetKind.flat ? 0 : f.pitchRise, labels: labels);
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

    addCompass(prims, (x: width - sp.compassInsetX, y: height - sp.compassInsetY), sp, style, north: labels.compassNorth);
    addFooter(prims, footer, height, style, sp);

    return Scene(
      width: width,
      height: height,
      background: style.background,
      prims: prims,
      hiddenLabels: hidden,
      placedLabels: placed,
      title: labels.areaCaption,
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
