import 'dart:math' as math;

import 'format.dart';
import 'labels.dart';
import 'layout.dart';
import 'model.dart';
import 'report_layout.dart';
import 'scene.dart';
import 'style.dart';

String _methodName(String m, RoofLabels l) => switch (m) {
      'lidar_skeleton' => l.methodLidarSkeleton,
      'lidar_agent' => l.methodLidarAgent,
      'solar_agent' => l.methodSolarAgent,
      'manual' => l.methodManual,
      'fixture' => l.methodFixture,
      _ => m,
    };

/// The "Source" lines: method, footprint, LiDAR, Solar imagery and the model date.
List<String> sourceLines(RoofModel m, RoofLabels l) {
  final raw = m.source.raw;
  String known(Object? v) => v == null ? l.unknown : '$v';
  final lines = <String>[RoofLabels.fill(l.sourceMethod, {'method': _methodName(m.source.method, l)})];
  final fp = raw['footprint'];
  if (fp is Map) {
    final id = fp['id'] != null ? ' (${RoofLabels.fill(l.footprintId, {'id': '${fp['id']}'})})' : '';
    final area = fp['area_sqft'] is num
        ? ', ${RoofLabels.fill(l.footprintArea, {'area': sqft((fp['area_sqft'] as num).toDouble())})}'
        : '';
    lines.add('${RoofLabels.fill(l.sourceFootprint, {'provider': known(fp['provider'])})}$id$area');
  }
  final lidar = raw['lidar'];
  if (lidar is Map) {
    final pts = lidar['points_on_roof'] != null
        ? ', ${RoofLabels.fill(l.lidarPoints, {'n': '${lidar['points_on_roof']}'})}'
        : '';
    lines.add('${RoofLabels.fill(l.sourceLidar, {'project': known(lidar['project']), 'date': known(lidar['acquired'])})}$pts');
  }
  final solar = raw['solar'];
  if (solar is Map) {
    final seg = solar['segments'] != null ? ', ${RoofLabels.fill(l.solarSegments, {'n': '${solar['segments']}'})}' : '';
    lines.add('${RoofLabels.fill(l.sourceSolar, {'date': known(solar['imagery_date']), 'quality': known(solar['imagery_quality'])})}$seg');
  }
  final gen = m.extra['generated_at'];
  if (gen is String) lines.add(RoofLabels.fill(l.modelGenerated, {'date': gen}));
  return lines;
}

/// A text report: address, source and data dates, areas, pitch, confidence and warnings.
/// The height is computed from the content. Text comes from [labels]; [layout] picks four
/// figure columns (wide) or two (compact).
class SummaryBlock {
  const SummaryBlock._();

  static Scene build(
    RoofModel m, {
    double? width,
    DiagramStyle style = DiagramStyle.report,
    RoofLabels labels = const RoofLabels(),
    ReportLayout layout = ReportLayout.wide,
  }) {
    width ??= layout.designWidth;
    final k = layoutScale(layout, width, 1000 * width / layout.designWidth);
    final prims = <Prim>[];
    final left = 48 * k;
    final textW = width - 2 * left;
    var y = 44 * k;

    void text(String s, double size, {bool bold = false, int? color, double x = 0, double? gapAfter}) {
      prims.add(TextPrim(
        at: (x: left + x, y: y),
        text: s,
        size: size,
        color: color ?? style.textColor,
        anchor: TextAnchor.start,
        bold: bold,
      ));
      y += gapAfter ?? size * 1.5;
    }

    void paragraph(String s, double size, {int? color, double indent = 0}) {
      for (final line in wrapText(s, textW - indent, size)) {
        prims.add(TextPrim(
          at: (x: left + indent, y: y),
          text: line,
          size: size,
          color: color ?? style.textColor,
          anchor: TextAnchor.start,
        ));
        y += size * 1.45;
      }
    }

    text(labels.summaryCaption, 14 * k, color: 0xFF757575, gapAfter: 30 * k);
    final address = m.address.display.isEmpty ? labels.addressMissing : m.address.display;
    text(address, fitSize(address, textW, 28 * k, 18 * k, bold: true), bold: true, gapAfter: 40 * k);

    // Key figures in columns.
    final t = m.totals;
    String sq(double v) => '${sqft(v)} ${labels.unitSqft}';
    final figs = <(String, String)>[
      (labels.totalArea, sq(t.totalAreaSqft)),
      (labels.squares, t.squares.toStringAsFixed(2)),
      (labels.pitchedArea, sq(t.pitchedAreaSqft)),
      (labels.flatArea, sq(t.flatAreaSqft)),
      (
        labels.predominantPitch,
        '${pitchLabel(t.predominantPitchRise, labels: labels)}  (${sq(t.predominantPitchAreaSqft)})'
      ),
      (labels.facets, '${m.facets.length}'),
      (labels.edgeTotal, feetInches(t.lengthsFt.values.fold(0.0, (a, b) => a + b), labels: labels)),
      (labels.confidence, m.confidence.overall),
    ];
    final cols = layout.figureColumns;
    final colW = textW / cols;
    for (var row = 0; row < ReportLayout.rowsFor(figs.length, cols); row++) {
      for (var c = 0; c < cols; c++) {
        final (cap, val) = figs[row * cols + c];
        final x = left + c * colW;
        prims
          ..add(TextPrim(at: (x: x, y: y), text: cap, size: layout.textSize(13, k), color: 0xFF757575, anchor: TextAnchor.start))
          ..add(TextPrim(
              at: (x: x, y: y + 24 * k), text: val, size: 20 * k, color: style.textColor, anchor: TextAnchor.start, bold: true));
      }
      y += 66 * k;
    }
    y += 6 * k;

    text(labels.sourceHeading, 17 * k, bold: true, gapAfter: 26 * k);
    for (final l in sourceLines(m, labels)) {
      paragraph(l, 15 * k, indent: 12 * k);
    }
    y += 12 * k;

    void bullets(String title, List<String> items, {int bullet = 0xFF757575}) {
      if (items.isEmpty) return;
      text(title, 17 * k, bold: true, gapAfter: 26 * k);
      for (final n in items) {
        prims.add(TextPrim(
            at: (x: left + 12 * k, y: y), text: '-', size: 15 * k, color: bullet, anchor: TextAnchor.start, bold: true));
        paragraph(n, 15 * k, indent: 30 * k);
      }
      y += 12 * k;
    }

    bullets(labels.confidenceNotesHeading, m.confidence.notes);
    bullets(labels.warnings, m.warnings, bullet: 0xFFE53935);
    if (m.holes.isNotEmpty) {
      final byKind = <String, int>{};
      for (final h in m.holes) {
        byKind[h.kind] = (byKind[h.kind] ?? 0) + 1;
      }
      bullets(labels.excludedOpeningsHeading, [
        RoofLabels.fill(labels.excludedFromAreas, {'items': byKind.entries.map((e) => '${e.value} ${e.key}').join(', ')}),
      ]);
    }

    return Scene(
      width: width,
      height: math.max(y + 24 * k, 240 * k),
      background: style.background,
      prims: prims,
      title: labels.summaryPageTitle,
    );
  }
}
