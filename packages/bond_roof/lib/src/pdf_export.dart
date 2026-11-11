import 'dart:typed_data';

import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:vector_math/vector_math_64.dart' show Matrix4;

import 'labels.dart';
import 'scene.dart';

/// Page width in PDF points for a landscape letter sheet; taller scenes use the same width.
const _pageWidthPt = 792.0;

/// Draws each scene onto its own PDF page, scaled to 792 pt wide. Pass [fontTtf] (a TrueType
/// font file) for text outside Latin-1; without it the built-in Helvetica is used and other
/// characters become "?". The document title is [title], or `labels.pdfTitle` when omitted.
Future<Uint8List> scenesToPdf(
  List<Scene> pages, {
  Uint8List? fontTtf,
  String? title,
  RoofLabels labels = const RoofLabels(),
}) async {
  if (pages.isEmpty) throw ArgumentError.value(pages, 'pages', 'at least one scene is required');
  final doc = pw.Document(title: title ?? labels.pdfTitle, creator: 'bond_roof');
  final pw.Font regular, bold;
  if (fontTtf != null) {
    regular = pw.Font.ttf(ByteData.sublistView(fontTtf));
    bold = regular;
  } else {
    regular = pw.Font.helvetica();
    bold = pw.Font.helveticaBold();
  }
  String clean(String s) => fontTtf != null
      ? s
      : String.fromCharCodes(s.runes.map((r) => r <= 0xFF ? r : 0x3F));

  for (final s in pages) {
    final k = _pageWidthPt / s.width;
    final w = s.width * k, h = s.height * k;
    doc.addPage(pw.Page(
      pageFormat: PdfPageFormat(w, h, marginAll: 0),
      build: (ctx) => pw.CustomPaint(
        size: PdfPoint(w, h),
        painter: (PdfGraphics g, PdfPoint size) {
          PdfColor col(int v) => PdfColor.fromInt(0xFF000000 | (v & 0xFFFFFF));
          double x(double v) => v * k;
          double y(double v) => h - v * k;

          void alpha(int c) {
            final a = ((c >> 24) & 0xFF) / 255;
            g.setGraphicState(PdfGraphicState(opacity: a));
          }

          void dash(bool d, double width) {
            if (d) {
              g.setLineDashPattern([width * 2.6 * k, width * 1.8 * k], 0);
            } else {
              g.setLineDashPattern();
            }
          }

          g
            ..setFillColor(col(s.background))
            ..drawRect(0, 0, w, h)
            ..fillPath();
          for (final p in s.prims) {
            switch (p) {
              case LinePrim():
                alpha(p.color);
                dash(p.dashed, p.width);
                g
                  ..setStrokeColor(col(p.color))
                  ..setLineWidth(p.width * k)
                  ..setLineCap(p.dashed ? PdfLineCap.butt : PdfLineCap.round)
                  ..moveTo(x(p.a.x), y(p.a.y))
                  ..lineTo(x(p.b.x), y(p.b.y))
                  ..strokePath();
              case PolyPrim():
                if (p.pts.length < 2) break;
                dash(p.dashed, p.width);
                g.setLineJoin(PdfLineJoin.round);
                if (p.fill != null) {
                  alpha(p.fill!);
                  g.setFillColor(col(p.fill!));
                }
                if (p.stroke != null) {
                  alpha(p.stroke!);
                  g
                    ..setStrokeColor(col(p.stroke!))
                    ..setLineWidth(p.width * k);
                }
                g.moveTo(x(p.pts.first.x), y(p.pts.first.y));
                for (final q in p.pts.skip(1)) {
                  g.lineTo(x(q.x), y(q.y));
                }
                g.closePath();
                if (p.fill != null && p.stroke != null) {
                  g.fillAndStrokePath();
                } else if (p.fill != null) {
                  g.fillPath();
                } else if (p.stroke != null) {
                  g.strokePath();
                } else {
                  g.closePath();
                }
              case TextPrim():
                alpha(p.color);
                dash(false, 1);
                final font = (p.bold ? bold : regular).getFont(ctx);
                final text = clean(p.text);
                final size = p.size * k;
                final tw = font.stringMetrics(text).width * size;
                final dx = switch (p.anchor) {
                  TextAnchor.start => 0.0,
                  TextAnchor.middle => -tw / 2,
                  TextAnchor.end => -tw,
                };
                g
                  ..saveContext()
                  ..setTransform(Matrix4.translationValues(x(p.at.x), y(p.at.y), 0)
                    ..rotateZ(-p.angleDeg * 3.141592653589793 / 180))
                  ..setFillColor(col(p.color))
                  ..drawString(font, size, text, dx, -size * 0.35)
                  ..restoreContext();
            }
          }
        },
      ),
    ));
  }
  return doc.save();
}
