import 'dart:typed_data';

import 'package:flutter/services.dart' show rootBundle;
import 'package:printing/printing.dart';
import 'package:bond_roof/bond_roof.dart';
import 'package:bond_roof/roof_pdf.dart';

import 'tokens.dart';

/// The three report pages as scenes, and the PDF, print and share hand-offs.
abstract final class RoofReport {
  static const double pageWidth = RoofUiTokens.pageWidthPx;
  static const double pageHeight = RoofUiTokens.pageHeightPx;

  /// Length, area and summary scenes. [ReportLayout.wide] is sized for US Letter landscape at
  /// 150 dpi; [ReportLayout.compact] uses the 400 x 500 phone-width design size.
  static List<Scene> pages(
    RoofModel m, {
    DiagramStyle? style,
    RoofLabels labels = const RoofLabels(),
    ReportLayout layout = ReportLayout.wide,
  }) {
    final s = style ?? DiagramStyle.report;
    final wide = layout == ReportLayout.wide;
    return [
      LengthDiagram.build(m,
          width: wide ? pageWidth : null, height: wide ? pageHeight : null, style: s, labels: labels, layout: layout),
      AreaDiagram.build(m,
          width: wide ? pageWidth : null, height: wide ? pageHeight : null, style: s, labels: labels, layout: layout),
      SummaryBlock.build(m, width: wide ? pageWidth : null, style: s, labels: labels, layout: layout),
    ];
  }

  /// The PDF (always the wide, landscape pages). [fontTtf] defaults to the bundled Roboto,
  /// falling back to the PDF built-in font; [title] defaults to `labels.pdfTitle`.
  static Future<Uint8List> pdfBytes(
    RoofModel m, {
    RoofLabels labels = const RoofLabels(),
    Uint8List? fontTtf,
    String? title,
  }) async {
    var font = fontTtf;
    if (font == null) {
      try {
        final data = await rootBundle.load(RoofUiTokens.pdfFontAsset);
        font = data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
      } catch (_) {
        font = null; // fall back to the PDF built-in font
      }
    }
    return scenesToPdf(pages(m, labels: labels), fontTtf: font, title: title ?? labels.pdfTitle, labels: labels);
  }

  /// Opens the platform print flow (browser print dialog on web, system print UI on iOS).
  /// Those are OS-owned, not app popups.
  static Future<void> printReport(RoofModel m, {RoofLabels labels = const RoofLabels(), String? jobName}) async {
    final name = jobName ?? labels.pdfTitle;
    await Printing.layoutPdf(name: name, onLayout: (_) => pdfBytes(m, labels: labels, title: name));
  }

  /// Hands the PDF to the platform as a file named [filename]: a download on web.
  static Future<void> saveReport(RoofModel m,
      {RoofLabels labels = const RoofLabels(), String filename = 'roof-report.pdf'}) async {
    final bytes = await pdfBytes(m, labels: labels);
    await Printing.sharePdf(bytes: bytes, filename: filename);
  }

  /// Hands the PDF to the OS share sheet (iOS, Android); a download on web.
  static Future<void> shareReport(RoofModel m,
      {RoofLabels labels = const RoofLabels(), String filename = 'roof-report.pdf'}) async {
    final bytes = await pdfBytes(m, labels: labels);
    await Printing.sharePdf(bytes: bytes, filename: filename, subject: labels.pdfTitle);
  }
}

/// [RoofReport.printReport] (kept from 0.1).
Future<void> printReport(RoofModel m, {String? jobName, RoofLabels labels = const RoofLabels()}) =>
    RoofReport.printReport(m, labels: labels, jobName: jobName);

/// [RoofReport.saveReport] (the 0.1 name for the file hand-off).
Future<void> shareReport(RoofModel m, {String filename = 'roof-report.pdf', RoofLabels labels = const RoofLabels()}) =>
    RoofReport.saveReport(m, labels: labels, filename: filename);
