import 'dart:math' as math;

import 'facet_draw.dart';
import 'figures.dart';
import 'format.dart';
import 'labels.dart';
import 'layout.dart';
import 'metrics.dart';
import 'model.dart';
import 'object_draw.dart';
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

/// A step edge (level change, sidewall or headwall flashing) shows its length like every other edge ("24"); a jump of
/// [levelChangeStepMinFt] or more is added ("24, 5 ft step").
String _stepText(RoofEdge e, RoofLabels labels) {
  final len = wholeFeet(e.lengthFt);
  final jump = e.jumpFt;
  if (jump == null || !(jump >= levelChangeStepMinFt)) return len;
  return RoofLabels.fill(labels.levelChangeStep, {'len': len, 'jump': '${wholeFeet(jump)} ${labels.unitFt}'});
}

/// One row of the legend: an edge type (coloured swatch), a derived total (no swatch), or a kind of object (its mark).
class _LegendRow {
  const _LegendRow(this.name, this.value, {this.type, this.object});
  final String name, value;
  final EdgeType? type;
  final ObjectKind? object;
}

const _edgeOfRow = <String, EdgeType>{
  'eave': EdgeType.eave,
  'rake': EdgeType.rake,
  'flat_edge': EdgeType.flatEdge,
  'ridge': EdgeType.ridge,
  'hip': EdgeType.hip,
  'valley': EdgeType.valley,
  'step_flashing': EdgeType.stepFlashing,
  'wall_flashing': EdgeType.wallFlashing,
  'transition': EdgeType.transition,
  'level_change': EdgeType.levelChange,
  'unspecified': EdgeType.unspecified,
};

/// The totals rows that are lengths or objects: the legend prints exactly these, in the same order as the totals table.
bool _inLegend(TotalRow r) => _edgeOfRow.containsKey(r.id) || const {'exposed_edge', 'eave_rake', 'ridge_hip', 'chimneys', 'lanterns'}.contains(r.id);

/// The ids of the legend's rows (the totals rows of [totalRows] that are lengths or objects).
List<String> legendRowIds(RoofModel m) => [for (final r in totalRows(m, const RoofLabels())) if (_inLegend(r)) r.id];

/// The legend of the roof, built from the same rows as the totals table: edge rows (swatch), the derived sums (no swatch)
/// and the objects (their mark and count).
List<_LegendRow> _legendRows(RoofModel m, RoofLabels l) => [
      for (final r in totalRows(m, l))
        if (_inLegend(r))
          switch (r.id) {
            'chimneys' => _LegendRow(l.legendChimney, r.value, object: ObjectKind.chimney),
            'lanterns' => _LegendRow(l.legendLantern, r.value, object: ObjectKind.lantern),
            final id when _edgeOfRow.containsKey(id) => _LegendRow(l.edgeName(_edgeOfRow[id]!), r.value, type: _edgeOfRow[id]),
            _ => _LegendRow(r.label, r.value),
          },
    ];

/// Plan view with every edge coloured by type, a whole-foot label on each edge that has room, the chimneys and lanterns
/// as marks, a legend of totals at the top (three columns wide, two compact), a compass rose and the
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

    // Header: address, then the legend in columns, filled column by column.
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
    final legend = _legendRows(m, labels);
    final perCol = layout.legendRowsFor(legend.length);
    var idx = 0;
    for (var c = 0; c < cols; c++) {
      for (var r = 0; r < perCol[c]; r++) {
        final row = legend[idx++];
        final x0 = sp.margin + c * colW, y = sp.legendTop + r * sp.legendPitch;
        final valueX = x0 + colW - sp.legendValueInset;
        final nameX = x0 + sp.legendTextX;
        final type = row.type, object = row.object;
        if (type != null) {
          prims.add(LinePrim(
            a: (x: x0, y: y),
            b: (x: x0 + sp.swatchLen, y: y),
            color: style.colorOf(type),
            width: style.strokeWidth * k,
            dashed: style.dashedTypes.contains(type),
          ));
        } else if (object != null) {
          addObjectMark(prims, (x: x0 + sp.swatchLen / 2, y: y), sp.legendSize * 1.35, object, style, labels, sp.legendSize, k);
        }
        prims
          ..add(TextPrim(
            at: (x: nameX, y: y),
            text: layout == ReportLayout.wide
                ? row.name
                : ellipsize(row.name, valueX - textWidth(row.value, sp.legendSize, bold: true) - 6 - nameX, sp.legendSize),
            size: sp.legendSize,
            color: style.textColor,
            anchor: TextAnchor.start,
          ))
          ..add(TextPrim(
            at: (x: valueX, y: y),
            text: row.value,
            size: sp.legendSize,
            color: style.textColor,
            anchor: TextAnchor.end,
            bold: true,
          ));
      }
    }

    // Plan.
    final footer = footerLines(labels.footerLength, width, sp);
    final legendBottom = sp.legendTop + (math.max(perCol.reduce(math.max), 1) - 1) * sp.legendPitch + sp.legendPlanPad;
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

    final marks = objectMarks(m, fit, objectMinSide(layout, k));
    addObjectMarks(prims, marks, style, labels, layout, k);

    // Labels, longest edge first.
    final size = layout == ReportLayout.wide ? math.max(layout.minLabelSize, style.fontSize * k) : layout.minLabelSize;
    final placer = LabelPlacer(
        edges: segs,
        area: (l: sp.labelAreaSide, t: area.t, r: width - sp.labelAreaSide, b: area.b + sp.labelAreaSide),
        reserved: [for (final mk in marks) mk.box]);
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
      // A step edge shows its length, plus the step height when the jump is tall.
      final text = e.type.hasJump ? _stepText(e, labels) : wholeFeet(e.lengthFt);
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
