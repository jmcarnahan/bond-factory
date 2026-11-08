// Helvetica advance widths (1/1000 em) for ASCII 32..126, from the standard AFM.
const _helvetica = <int>[
  278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, // space .. /
  556, 556, 556, 556, 556, 556, 556, 556, 556, 556, // 0-9
  278, 278, 584, 584, 584, 556, 1015, // : .. @
  667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, // A-M
  722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, // N-Z
  278, 278, 278, 469, 556, 333, // [ .. `
  556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, // a-m
  556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, // n-z
  334, 260, 334, 584, // { .. ~
];

/// Width of [s] in the same units as [size], using Helvetica metrics so SVG, PDF and the
/// label placer agree. Bold is approximated (digits and spaces keep their width).
double textWidth(String s, double size, {bool bold = false}) {
  var w = 0.0;
  for (final c in s.codeUnits) {
    final base = (c >= 32 && c <= 126) ? _helvetica[c - 32] : 556;
    final isNarrow = (c >= 48 && c <= 57) || c == 32;
    w += bold && !isNarrow ? base * 1.06 : base;
  }
  return w * size / 1000;
}
