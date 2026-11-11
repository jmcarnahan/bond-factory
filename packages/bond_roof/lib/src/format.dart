import 'labels.dart';

/// 209.67 -> "209ft 8in"; inches are rounded and carried (11.99 -> "12ft 0in"). The unit texts
/// come from [labels].
String feetInches(double ft, {RoofLabels labels = const RoofLabels()}) {
  final totalIn = (ft.isFinite ? ft : 0).abs() * 12;
  final rounded = totalIn.round();
  final sign = ft < 0 && rounded > 0 ? '-' : '';
  return '$sign${rounded ~/ 12}${labels.unitFt} ${rounded % 12}${labels.unitIn}';
}

/// 35.4 -> "35". The diagram prints whole feet.
String wholeFeet(double ft) => (ft.isFinite ? ft : 0).round().toString();

/// 2121.4 -> "2,121". Whole square feet with thousands separators.
String sqft(double a) {
  final r = (a.isFinite ? a : 0).round();
  final digits = r.abs().toString();
  final b = StringBuffer(r < 0 ? '-' : '');
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) b.write(',');
    b.write(digits[i]);
  }
  return b.toString();
}

/// 0.19 -> "Flat" (rise <= 0.5); 3.9 -> "4/12"; 4.6 -> "4.5/12" (nearest whole or half).
String pitchLabel(double rise, {RoofLabels labels = const RoofLabels()}) {
  if (!(rise > 0.5)) return labels.pitchFlat;
  final p = (rise * 2).round() / 2;
  return p == p.truncateToDouble() ? '${p.toInt()}/12' : '$p/12';
}
