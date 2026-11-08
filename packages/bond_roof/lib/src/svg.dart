import 'dart:math' as math;

import 'scene.dart';

String _hex(int c) => '#${(c & 0xFFFFFF).toRadixString(16).padLeft(6, '0')}';

String _opacity(String attr, int c) {
  final a = (c >> 24) & 0xFF;
  return a == 0xFF ? '' : ' $attr-opacity="${(a / 255).toStringAsFixed(3)}"';
}

String _n(double v) {
  final s = v.toStringAsFixed(2);
  return s.contains('.') ? s.replaceFirst(RegExp(r'\.?0+$'), '') : s;
}

/// Escapes text for XML 1.0: control characters other than tab and newline cannot appear in a
/// document at all, so they are dropped.
String _esc(String s) => s
    .replaceAll(RegExp(r'[\x00-\x08\x0B-\x1F]'), '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');

String _dash(double w) => ' stroke-dasharray="${_n(w * 2.6)} ${_n(w * 1.8)}"';

/// Serialises a scene to a standalone SVG document string.
String sceneToSvg(Scene s) {
  final b = StringBuffer()
    ..write('<svg xmlns="http://www.w3.org/2000/svg" width="${_n(s.width)}" height="${_n(s.height)}" '
        'viewBox="0 0 ${_n(s.width)} ${_n(s.height)}">')
    ..write('<title>${_esc(s.title)}</title>')
    ..write('<rect width="${_n(s.width)}" height="${_n(s.height)}" fill="${_hex(s.background)}"/>');
  for (final p in s.prims) {
    switch (p) {
      case LinePrim():
        b.write('<line x1="${_n(p.a.x)}" y1="${_n(p.a.y)}" x2="${_n(p.b.x)}" y2="${_n(p.b.y)}" '
            'stroke="${_hex(p.color)}"${_opacity('stroke', p.color)} stroke-width="${_n(p.width)}" '
            'stroke-linecap="${p.dashed ? 'butt' : 'round'}"${p.dashed ? _dash(p.width) : ''}/>');
      case PolyPrim():
        final pts = p.pts.map((e) => '${_n(e.x)},${_n(e.y)}').join(' ');
        b.write('<polygon points="$pts" fill="${p.fill == null ? 'none' : _hex(p.fill!)}"'
            '${p.fill == null ? '' : _opacity('fill', p.fill!)} '
            'stroke="${p.stroke == null ? 'none' : _hex(p.stroke!)}"'
            '${p.stroke == null ? '' : _opacity('stroke', p.stroke!)} stroke-width="${_n(p.width)}" '
            'stroke-linejoin="round"${p.dashed ? _dash(p.width) : ''}/>');
      case TextPrim():
        final anchor = switch (p.anchor) {
          TextAnchor.start => 'start',
          TextAnchor.middle => 'middle',
          TextAnchor.end => 'end',
        };
        final rot = p.angleDeg.abs() < 1e-6 ? '' : ' rotate(${_n(p.angleDeg)})';
        b.write('<text transform="translate(${_n(p.at.x)} ${_n(p.at.y)})$rot" text-anchor="$anchor" '
            'dy="${_n(math.max(p.size, 0) * 0.35)}" font-family="Helvetica, Arial, sans-serif" '
            'font-size="${_n(p.size)}" font-weight="${p.bold ? 700 : 400}" fill="${_hex(p.color)}"'
            '${_opacity('fill', p.color)}>${_esc(p.text)}</text>');
    }
  }
  b.write('</svg>');
  return b.toString();
}
