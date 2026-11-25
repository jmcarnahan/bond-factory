import 'dart:math' as math;

import 'facet_draw.dart';
import 'format.dart';
import 'labels.dart';
import 'layout.dart';
import 'metrics.dart';
import 'model.dart';
import 'polylabel.dart';
import 'report_layout.dart';
import 'scene.dart';
import 'style.dart';

/// True when both endpoints of [e] lie on the outline of one of the model's holes (within
/// 0.05 ft). Such edges are drawn and counted in the totals but never labelled.
bool isHoleOutlineEdge(RoofModel m, RoofEdge e) {
  for (final h in m.holes) {
    if (signedDistanceToPolygon(e.a, h.polygon).abs() <= 0.05 &&
        signedDistanceToPolygon(e.b, h.polygon).abs() <= 0.05) {
      return true;
    }
  }
  return false;
}

/// A level change shows its length like every other edge ("24"); a jump of [levelChangeStepMinFt] or more
/// is added ("24, 5 ft step").
String _levelChangeText(RoofEdge e, RoofLabels labels) {
  final len = wholeFeet(e.lengthFt);
  final jump = e.jumpFt;
  if (jump == null || !(jump >= levelChangeStepMinFt)) return len;
  return RoofLabels.fill(labels.levelChangeStep, {'len': len, 'jump': '${wholeFeet(jump)} ${labels.unitFt}'});
}

/// Plan view with every edge coloured by type, a whole-foot label on each edge that has room,
/// a legend of totals at the top (three columns wide, two compact), a compass rose and the
/// rounding footer. All text comes from [labels]; [layout] picks the page geometry (the
/// default size is the layout's design size).
class LengthDiagram {
  const LengthDiagram._();

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

    // Header: address, then the legend in columns (wide 4 + 3 + 3 rows, compact 5 + 5).
    final title = m.address.display.isEmpty ? labels.lengthTitle : m.address.display;
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
        text: labels.lengthCaption,
        size: sp.captionSize,
        color: 0xFF757575,
        anchor: TextAnchor.start,
      ));
    final cols = layout.legendColumns;
    final colW = (width - 2 * sp.margin) / cols;
    // The ten edge types of contract 0.2 always; the 0.4 types only when the model has them.
    final legacyTypes = [
      ...EdgeType.legacy,
      for (final t in EdgeType.values)
        if (t.isNew04 && t != EdgeType.flatSeam && (m.edges.any((e) => e.type == t) || (m.totals.lengthsFt[t] ?? 0) > 0)) t,
    ];
    // An engine model (facets carry a roof type) lists only the types that have length: a flat roof is not shown a column of
    // zeros. A model without roof types keeps the ten legacy rows. Never an empty legend.
    final present = [
      for (final t in [...EdgeType.legacy, ...EdgeType.values.where((t) => t.isNew04)])
        if (t != EdgeType.flatSeam && (m.totals.lengthsFt[t] ?? 0) > 0) t,
    ];
    final legendTypes = m.facets.any((f) => f.roofType != null) && present.isNotEmpty ? present : legacyTypes;
    final perCol = layout.legendRowsFor(legendTypes.length);
    var idx = 0;
    for (var c = 0; c < cols; c++) {
      for (var r = 0; r < perCol[c]; r++) {
        final t = legendTypes[idx++];
        final x0 = sp.margin + c * colW, y = sp.legendTop + r * sp.legendPitch;
        final value = feetInches(m.totals.lengthsFt[t] ?? 0, labels: labels);
        final valueX = x0 + colW - sp.legendValueInset;
        final nameX = x0 + sp.legendTextX;
        prims
          ..add(LinePrim(
            a: (x: x0, y: y),
            b: (x: x0 + sp.swatchLen, y: y),
            color: style.colorOf(t),
            width: style.strokeWidth * k,
            dashed: style.dashedTypes.contains(t),
          ))
          ..add(TextPrim(
            at: (x: nameX, y: y),
            text: layout == ReportLayout.wide
                ? labels.edgeName(t)
                : ellipsize(labels.edgeName(t), valueX - textWidth(value, sp.legendSize, bold: true) - 6 - nameX, sp.legendSize),
            size: sp.legendSize,
            color: style.textColor,
            anchor: TextAnchor.start,
          ))
          ..add(TextPrim(
            at: (x: valueX, y: y),
            text: value,
            size: sp.legendSize,
            color: style.textColor,
            anchor: TextAnchor.end,
            bold: true,
          ));
      }
    }

    // Plan.
    final footer = footerLines(labels.footerLength, width, sp);
    final legendBottom = sp.legendTop + (perCol.reduce(math.max) - 1) * sp.legendPitch + sp.legendPlanPad;
    final bottomReserve = layout == ReportLayout.wide ? sp.planBottomMin : math.max(sp.planBottomMin, footerHeight(footer, sp));
    final area = (l: sp.planSide, t: legendBottom, r: width - sp.planSide, b: height - bottomReserve);
    final fit = PlanFit(m,
        left: area.l + sp.planInsetX, top: area.t + sp.planInsetTop, right: area.r - sp.planInsetX, bottom: area.b - sp.planInsetBottom);
    final regions = <SceneRegion>[];
    for (final f in m.facets) {
      final pts = fit.mapAll(f.polygon);
      regions.add(SceneRegion(id: f.id, pts: pts));
      addFacetPrims(prims, f, pts, style,
          stroke: 0xFFE0E0E0, strokeWidth: 1, k: k, flatStroke: style.edgeColors[EdgeType.flatSeam], flatStrokeWidth: flatSeamStrokePx * k);
    }
    for (final h in m.holes) {
      prims.add(PolyPrim(
        pts: fit.mapAll(h.polygon),
        stroke: style.holeStroke,
        width: 1.8 * k,
        dashed: true,
      ));
    }
    final segs = [for (final e in m.edges) Seg(fit.map(e.a), fit.map(e.b))];
    for (final (i, e) in m.edges.indexed) {
      prims.add(LinePrim(
        a: segs[i].a,
        b: segs[i].b,
        color: style.colorOf(e.type),
        width: e.type == EdgeType.flatSeam ? flatSeamStrokePx * k : style.strokeWidth * k * style.widthScaleOf(e.type),
        dashed: style.dashedTypes.contains(e.type),
      ));
    }

    // Labels, longest edge first.
    final size = layout == ReportLayout.wide ? math.max(layout.minLabelSize, style.fontSize * k) : layout.minLabelSize;
    final placer = LabelPlacer(
        edges: segs, area: (l: sp.labelAreaSide, t: area.t, r: width - sp.labelAreaSide, b: area.b + sp.labelAreaSide));
    final centroid = fit.map(roofCentroid(m));
    final order = [for (var i = 0; i < m.edges.length; i++) i]
      ..sort((a, b) => segs[b].length.compareTo(segs[a].length));
    final edgeLabels = <TextPrim>[];
    var hidden = 0;
    final onHole = [for (final e in m.edges) isHoleOutlineEdge(m, e)];
    for (final i in order) {
      // Opening outlines are drawn dashed but carry no length label. They are neither placed
      // nor counted as hidden.
      if (onHole[i]) continue;
      final e = m.edges[i];
      if (e.type == EdgeType.flatSeam) continue; // drawn thin, never labelled
      // A level change shows its length, plus the step height when the jump is tall.
      final text = e.type == EdgeType.levelChange ? _levelChangeText(e, labels) : wholeFeet(e.lengthFt);
      Obb? box;
      if (segs[i].length >= style.minLabelPx * k) {
        box = placer.placeAlong(segs[i], textWidth(text, size, bold: true), size, centroid,
            strokeWidth: style.strokeWidth * k);
      }
      if (box == null) {
        hidden++;
        continue;
      }
      edgeLabels.add(TextPrim(
        at: (x: box.cx, y: box.cy),
        text: text,
        angleDeg: box.angle * 180 / math.pi,
        size: size,
        color: style.textColor,
        bold: true,
      ));
    }
    prims.addAll(edgeLabels);

    addCompass(prims, (x: width - sp.compassInsetX, y: height - sp.compassInsetY), sp, style, north: labels.compassNorth);
    addFooter(prims, footer, height, style, sp);

    return Scene(
      width: width,
      height: height,
      background: style.background,
      prims: prims,
      hiddenLabels: hidden,
      placedLabels: edgeLabels.length,
      title: labels.lengthCaption,
      regions: regions,
    );
  }
}
