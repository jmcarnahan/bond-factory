import 'dart:typed_data';

import 'package:flutter/services.dart' show rootBundle;
import 'package:printing/printing.dart';
import 'package:bond_roof/bond_roof.dart';
import 'package:bond_roof/roof_pdf.dart';

import 'tokens.dart';

/// The three report pages as scenes.
abstract final class RoofReport {
  static const double pageWidth = RoofUiTokens.pageWidthPx;
  static const double pageHeight = RoofUiTokens.pageHeightPx;

  /// Length, area and summary scenes sized for US Letter landscape at 150 dpi.
  static List<Scene> pages(RoofModel m, {DiagramStyle? style}) {
    final s = style ?? const DiagramStyle();
    return [
      LengthDiagram.build(m, width: pageWidth, height: pageHeight, style: s),
      AreaDiagram.build(m, width: pageWidth, height: pageHeight, style: s),
      SummaryBlock.build(m, width: pageWidth, style: s),
    ];
  }
}

Future<Uint8List> _pdfBytes(RoofModel m, String title) async {
  Uint8List? font;
  try {
    final data = await rootBundle.load(RoofUiTokens.pdfFontAsset);
    font = data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
  } catch (_) {
    font = null; // fall back to the PDF built-in font
  }
  return scenesToPdf(RoofReport.pages(m), fontTtf: font, title: title);
}

/// Opens the platform print flow (browser print dialog on web, system print
/// UI on iOS). Those are OS-owned, not app popups.
Future<void> printReport(RoofModel m,
    {String jobName = RoofUiTokens.pdfTitle}) async {
  await Printing.layoutPdf(
    name: jobName,
    onLayout: (_) => _pdfBytes(m, jobName),
  );
}

/// Hands the PDF to the platform: a download on web, the share sheet on iOS.
Future<void> shareReport(RoofModel m,
    {String filename = 'roof-report.pdf'}) async {
  final bytes = await _pdfBytes(m, RoofUiTokens.pdfTitle);
  await Printing.sharePdf(bytes: bytes, filename: filename);
}
