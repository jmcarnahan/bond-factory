import 'package:flutter/painting.dart';

/// Elevation shadows. A neutral translucent ink; there is no popup elevation.
abstract final class BondShadows {
  static const Color _ink = Color(0x1416181D);

  static const List<BoxShadow> card = [
    BoxShadow(color: _ink, blurRadius: 12, offset: Offset(0, 2)),
  ];
  static const List<BoxShadow> raised = [
    BoxShadow(color: _ink, blurRadius: 24, offset: Offset(0, 8)),
  ];
  static const List<BoxShadow> none = [];
}
