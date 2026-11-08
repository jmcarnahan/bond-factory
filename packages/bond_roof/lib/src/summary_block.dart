import 'dart:math' as math;

import 'format.dart';
import 'layout.dart';
import 'model.dart';
import 'scene.dart';
import 'style.dart';

String _methodName(String m) => switch (m) {
      'lidar_skeleton' => 'LiDAR point cloud + building footprint',
      'solar_agent' => 'Google Solar data + agent',
      'manual' => 'Manual digitisation',
      'fixture' => 'Test fixture',
      _ => m,
    };

/// A text report: address, source and data dates, areas, pitch, confidence and warnings.
/// The height is computed from the content.
class SummaryBlock {
  const SummaryBlock._();

  static Scene build(RoofModel m, {double width = 1600, DiagramStyle style = DiagramStyle.report}) {
    final k = sceneScale(width, 1000 * width / 1600);
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

    text('Roof measurement summary', 14 * k, color: 0xFF757575, gapAfter: 30 * k);
    text(m.address.display.isEmpty ? 'Address not given' : m.address.display, 28 * k, bold: true, gapAfter: 40 * k);

    // Key figures in four columns.
    final t = m.totals;
    final figs = <(String, String)>[
      ('Total area', '${sqft(t.totalAreaSqft)} sq ft'),
      ('Squares', t.squares.toStringAsFixed(2)),
      ('Pitched area', '${sqft(t.pitchedAreaSqft)} sq ft'),
      ('Flat area', '${sqft(t.flatAreaSqft)} sq ft'),
      ('Predominant pitch', '${pitchLabel(t.predominantPitchRise)}  (${sqft(t.predominantPitchAreaSqft)} sq ft)'),
      ('Facets', '${m.facets.length}'),
      ('Edge total', feetInches(t.lengthsFt.values.fold(0.0, (a, b) => a + b))),
      ('Confidence', m.confidence.overall),
    ];
    final colW = textW / 4;
    for (var row = 0; row < 2; row++) {
      for (var c = 0; c < 4; c++) {
        final (cap, val) = figs[row * 4 + c];
        final x = left + c * colW;
        prims
          ..add(TextPrim(at: (x: x, y: y), text: cap, size: 13 * k, color: 0xFF757575, anchor: TextAnchor.start))
          ..add(TextPrim(
              at: (x: x, y: y + 24 * k), text: val, size: 20 * k, color: style.textColor, anchor: TextAnchor.start, bold: true));
      }
      y += 66 * k;
    }
    y += 6 * k;

    // Source and data dates.
    text('Source', 17 * k, bold: true, gapAfter: 26 * k);
    final raw = m.source.raw;
    final lines = <String>['Method: ${_methodName(m.source.method)}'];
    final fp = raw['footprint'];
    if (fp is Map) {
      lines.add('Footprint: ${fp['provider'] ?? 'unknown'}${fp['id'] != null ? ' (id ${fp['id']})' : ''}'
          '${fp['area_sqft'] is num ? ', ${sqft((fp['area_sqft'] as num).toDouble())} sq ft' : ''}');
    }
    final lidar = raw['lidar'];
    if (lidar is Map) {
      lines.add('LiDAR: ${lidar['project'] ?? 'unknown'}, acquired ${lidar['acquired'] ?? 'unknown'}'
          '${lidar['points_on_roof'] != null ? ', ${lidar['points_on_roof']} points on the roof' : ''}');
    }
    final solar = raw['solar'];
    if (solar is Map) {
      lines.add('Solar imagery: ${solar['imagery_date'] ?? 'unknown'}, quality ${solar['imagery_quality'] ?? 'unknown'}'
          '${solar['segments'] != null ? ', ${solar['segments']} segments' : ''}');
    }
    final gen = m.extra['generated_at'];
    if (gen is String) lines.add('Model generated: $gen');
    for (final l in lines) {
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

    bullets('Confidence notes', m.confidence.notes);
    bullets('Warnings', m.warnings, bullet: 0xFFE53935);
    if (m.holes.isNotEmpty) {
      final byKind = <String, int>{};
      for (final h in m.holes) {
        byKind[h.kind] = (byKind[h.kind] ?? 0) + 1;
      }
      bullets('Excluded openings', [
        'Excluded from the areas: ${byKind.entries.map((e) => '${e.value} ${e.key}').join(', ')}.',
      ]);
    }

    final height = math.max(y + 24 * k, 240 * k);
    return Scene(
      width: width,
      height: height,
      background: style.background,
      prims: prims,
      title: 'Summary',
    );
  }
}
