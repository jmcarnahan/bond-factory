// Reads each 0.6 envelope (or bare model) file and lists what this package's reader does not know: totals keys, edge
// types, object kinds. Exit code 1 when any file has something unknown or does not parse.
// Run from packages/bond_roof:  dart run tool/check_envelope.dart <file.json>...
// ignore_for_file: avoid_print
import 'dart:convert';
import 'dart:io';

import 'package:bond_roof/bond_roof.dart';

import '../test/support.dart' show unknownEnvelopeKeys;

void main(List<String> args) {
  if (args.isEmpty) {
    print('usage: dart run tool/check_envelope.dart <file.json>...');
    exit(2);
  }
  var bad = 0;
  for (final path in args) {
    try {
      final json = jsonDecode(File(path).readAsStringSync()) as Map<String, dynamic>;
      final m = RoofMeasurement.parseAny(json);
      final unknown = unknownEnvelopeKeys(json);
      print('$path: ${m.model.facets.length} facets, ${m.model.edges.length} edges, ${m.model.objects.length} objects; '
          '${unknown.isEmpty ? 'all keys known' : 'UNKNOWN: ${unknown.join(', ')}'}'
          '${m.model.parseNotes.isEmpty ? '' : '; parse notes: ${m.model.parseNotes.join(' | ')}'}');
      if (unknown.isNotEmpty || m.model.parseNotes.isNotEmpty) bad++;
    } catch (e) {
      print('$path: does not parse: $e');
      bad++;
    }
  }
  exit(bad == 0 ? 0 : 1);
}
