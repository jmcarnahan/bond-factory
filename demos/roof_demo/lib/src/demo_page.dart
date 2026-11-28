import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show AssetManifest, rootBundle;
import 'package:bond_roof_ui/bond_roof_ui.dart';
import 'package:bond_roof/bond_roof.dart';

import 'labels_es.dart';
import 'model_panel.dart';
import 'tokens.dart';

class _Loaded {
  const _Loaded(this.label, this.measurement);
  final String label;
  final RoofMeasurement measurement;
}

/// The single screen: fixtures, language, report. It reads the bundled fixtures only; no service is called.
class DemoPage extends StatefulWidget {
  const DemoPage({super.key});

  @override
  State<DemoPage> createState() => _DemoPageState();
}

class _DemoPageState extends State<DemoPage> {
  bool _spanish = false;
  String? _error;
  _Loaded? _loaded;
  List<String> _bundled = const [];
  String? _selected;

  @override
  void initState() {
    super.initState();
    _loadFixtureList();
  }

  Future<void> _loadFixtureList() async {
    try {
      final manifest = await AssetManifest.loadFromAssetBundle(rootBundle);
      final names = manifest
          .listAssets()
          .where((a) => a.startsWith(DemoTokens.fixtureAssetDir) && a.endsWith('.json'))
          .map((a) => a.substring(DemoTokens.fixtureAssetDir.length))
          .toList()
        ..sort();
      if (mounted) setState(() => _bundled = names);
    } catch (e) {
      if (mounted) setState(() => _error = 'Could not list bundled fixtures: $e');
    }
  }

  Future<void> _load(String name) async {
    setState(() {
      _selected = name;
      _error = null;
    });
    try {
      final text = await rootBundle.loadString('${DemoTokens.fixtureAssetDir}$name');
      // Envelopes and bare models both load.
      final measurement = RoofMeasurement.parseAny(jsonDecode(text) as Map<String, dynamic>);
      if (!mounted) return;
      setState(() => _loaded = _Loaded(name, measurement));
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loaded = null;
        _error = '$e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final loaded = _loaded;
    return Scaffold(
      appBar: AppBar(title: const Text('Roof measurement demo')),
      body: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: DemoTokens.maxContentWidth),
          child: ListView(
            padding: const EdgeInsets.all(DemoTokens.pad),
            children: [
              Wrap(
                spacing: DemoTokens.gap,
                runSpacing: DemoTokens.gap,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  SegmentedButton<bool>(
                    showSelectedIcon: false,
                    segments: const [
                      ButtonSegment(value: false, label: Text('EN')),
                      ButtonSegment(value: true, label: Text('ES')),
                    ],
                    selected: {_spanish},
                    onSelectionChanged: (s) => setState(() => _spanish = s.first),
                  ),
                ],
              ),
              const SizedBox(height: DemoTokens.gap),
              Text('Load fixture', style: theme.textTheme.titleSmall),
              const SizedBox(height: DemoTokens.gap / 2),
              Wrap(
                spacing: DemoTokens.gap / 2,
                runSpacing: DemoTokens.gap / 2,
                children: [
                  for (final n in _bundled)
                    ChoiceChip(
                      label: Text(n.replaceAll('.json', '')),
                      selected: _selected == n,
                      onSelected: (_) => _load(n),
                    ),
                  if (_bundled.isEmpty) Text('No fixtures bundled. Run make sync-fixtures.', style: theme.textTheme.bodySmall),
                ],
              ),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: DemoTokens.gap / 2),
                  child: SelectableText(
                    _error!,
                    style: theme.textTheme.bodyMedium?.copyWith(color: DemoTokens.error),
                  ),
                ),
              if (loaded != null) ...[
                const SizedBox(height: DemoTokens.gapLarge),
                Text('Report: ${loaded.label}', style: theme.textTheme.titleLarge),
                const SizedBox(height: DemoTokens.gap),
                ModelPanel(loaded.measurement.model.toJson(), extraNotes: loaded.measurement.warnings),
                const SizedBox(height: DemoTokens.gap),
                RoofReportStrip(
                  measurement: loaded.measurement,
                  labels: _spanish ? RoofLabels.fromMap(roofLabelsEs) : const RoofLabels(),
                ),
              ] else
                Padding(
                  padding: const EdgeInsets.only(top: DemoTokens.gapLarge),
                  child: Text('Pick a fixture to see the diagrams.', style: theme.textTheme.bodyMedium),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
