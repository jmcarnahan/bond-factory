import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:bond_roof/bond_roof.dart';
import 'package:bond_roof_ui/bond_roof_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';

/// The all-flat two-level example of bond_roof (invented geometry): paints it and, when ROOF_FLAT_PNG names a file,
/// writes the picture there so a person can look at it.
void main() {
  testWidgets('the all-flat two-level roof paints its seams as thin dark lines', (tester) async {
    final m = RoofMeasurement.parseAny(jsonDecode(File('../bond_roof/test/flat_seams/synthetic_flat_two_level.json').readAsStringSync())
        as Map<String, dynamic>);
    final scene = LengthDiagram.build(m.model);
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = Size(scene.width, scene.height);
    addTearDown(tester.view.reset);
    final key = GlobalKey();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        backgroundColor: Colors.white,
        body: RepaintBoundary(key: key, child: SizedBox(width: scene.width, height: scene.height, child: RoofDiagramView(scene))),
      ),
    ));
    expect(tester.takeException(), isNull);
    late ui.Image img;
    late ByteData png;
    late ByteData raw;
    await tester.runAsync(() async {
      final b = key.currentContext!.findRenderObject()! as RenderRepaintBoundary;
      img = await b.toImage();
      png = (await img.toByteData(format: ui.ImageByteFormat.png))!;
      raw = (await img.toByteData())!;
    });
    final out = Platform.environment['ROOF_FLAT_PNG'];
    if (out != null && out.isNotEmpty) {
      // The test font draws letters as blocks, so the readable twin is the SVG beside it.
      File(out).writeAsBytesSync(png.buffer.asUint8List());
      File(out.replaceAll(RegExp(r'\.png$'), '.svg')).writeAsStringSync(sceneToSvg(scene));
    }
    // The seam is 1.2 px, so its pixels are anti-aliased greys; count grey pixels around 0x5A.
    var seamPixels = 0;
    for (var i = 0; i < raw.lengthInBytes; i += 4) {
      final v = raw.getUint32(i);
      final r = (v >> 24) & 255, g = (v >> 16) & 255, bl = (v >> 8) & 255;
      if (r == g && g == bl && r >= 0x50 && r <= 0x70) seamPixels++;
    }
    expect(seamPixels, greaterThan(50), reason: 'the 0xFF5A5A5A seam colour is on the page');
  });
}
