import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:bond_roof/bond_roof.dart';
import 'package:bond_roof_ui/bond_roof_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';

/// Paints the length and the area diagram of the hand-written 0.6 sample (wide and compact) through the real painter. The
/// chimney and lantern marks must be on the picture. When ROOF_PROOF_DIR names a folder the pictures are written there as
/// PNG (the test font draws letters as blocks) with the SVG of each scene beside it (readable text).
void main() {
  const style = DiagramStyle.report;

  for (final (tag, file) in [
    ('sample', 'roof_measurement_0.6_sample.json'),
    ('engine', 'roof_measurement_0.6_engine.json'),
  ]) {
    final measurement = RoofMeasurement.parseAny(
      jsonDecode(File('../../fixtures/roof_engine/$file').readAsStringSync())
          as Map<String, dynamic>,
    );
    for (final layout in ReportLayout.values) {
      for (final (name, build) in [
        ('length', (RoofModel m) => LengthDiagram.build(m, layout: layout)),
        ('area', (RoofModel m) => AreaDiagram.build(m, layout: layout)),
      ]) {
        testWidgets(
          '$tag $name diagram, ${layout.name}: the chimney and the lantern are on the picture',
          (tester) async {
            final scene = build(measurement.model);
            tester.view.devicePixelRatio = 1;
            tester.view.physicalSize = Size(scene.width, scene.height);
            addTearDown(tester.view.reset);
            final key = GlobalKey();
            await tester.pumpWidget(
              MaterialApp(
                home: Scaffold(
                  backgroundColor: Colors.white,
                  body: RepaintBoundary(
                    key: key,
                    child: SizedBox(
                      width: scene.width,
                      height: scene.height,
                      child: RoofDiagramView(scene),
                    ),
                  ),
                ),
              ),
            );
            expect(tester.takeException(), isNull);
            late ByteData png, raw;
            await tester.runAsync(() async {
              final img =
                  await (key.currentContext!.findRenderObject()!
                          as RenderRepaintBoundary)
                      .toImage();
              png = (await img.toByteData(format: ui.ImageByteFormat.png))!;
              raw = (await img.toByteData())!;
            });
            final out = Platform.environment['ROOF_PROOF_DIR'];
            if (out != null && out.isNotEmpty) {
              Directory(out).createSync(recursive: true);
              File(
                '$out/roof06_${tag}_${name}_${layout.name}.png',
              ).writeAsBytesSync(png.buffer.asUint8List());
              File(
                '$out/roof06_${tag}_${name}_${layout.name}.svg',
              ).writeAsStringSync(sceneToSvg(scene));
            }
            int near(int rgb) {
              var n = 0;
              for (var i = 0; i < raw.lengthInBytes; i += 4) {
                final v = raw.getUint32(i);
                if (((v >> 24) & 255) == ((rgb >> 16) & 255) &&
                    ((v >> 16) & 255) == ((rgb >> 8) & 255) &&
                    ((v >> 8) & 255) == (rgb & 255)) {
                  n++;
                }
              }
              return n;
            }

            expect(
              near(style.objectColorOf(ObjectKind.chimney)),
              greaterThan(30),
              reason: 'the chimney outline and letter',
            );
            expect(
              near(style.objectColorOf(ObjectKind.lantern)),
              greaterThan(30),
              reason: 'the lantern outline and letter',
            );
          },
        );
      }
    }
  }
}
