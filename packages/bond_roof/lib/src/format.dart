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

/// The pitch as roofers say it: the whole number (half up), with the fitted value beside it when the two differ at
/// the tenth. 4.31 -> "4/12 (4.3)", 5.0 -> "5/12", 4.5 -> "5/12 (4.5)", 0.19 -> "Flat" (rise <= 0.5).
String pitchLabel(double rise, {RoofLabels labels = const RoofLabels()}) {
  // Not a pitch (NaN, infinite, absurdly large) reads like "no pitch", never an exception.
  if (!(rise > 0.5) || rise > 1000) return labels.pitchFlat;
  final whole = (rise + 0.5).floor();
  final tenths = (rise * 10 + 0.5).floor();
  if (tenths == whole * 10) return '$whole/12';
  return '$whole/12 (${tenths ~/ 10}.${tenths % 10})';
}
