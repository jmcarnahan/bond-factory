import 'package:flutter/painting.dart';

/// Layout and colour tokens for the widgets in this package. Diagram colours
/// themselves come from the Scene (DiagramStyle in bond_roof).
abstract final class RoofUiTokens {
  /// US Letter landscape at 150 dpi.
  static const double pageWidthPx = 1650;
  static const double pageHeightPx = 1275;

  static const double gap = 12;
  static const double gapLarge = 24;
  static const double hairline = 1;
  static const double dashOn = 6;
  static const double dashOff = 4;
  static const double minViewExtent = 1;

  static const Color frame = Color(0xFFBDBDBD);
  static const Color error = Color(0xFFB3261E);
  static const Color ok = Color(0xFF2E7D32);
  static const Color mutedText = Color(0xFF616161);

  static const String pdfFontAsset =
      'packages/bond_roof_ui/assets/fonts/Roboto-Regular.ttf';
  static const String pdfTitle = 'Roof measurement report';
  static const List<String> pageTitles = ['Length diagram', 'Area diagram', 'Summary'];
}
