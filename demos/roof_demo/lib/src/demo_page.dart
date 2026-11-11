import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show AssetManifest, rootBundle;
import 'package:bond_roof_ui/bond_roof_ui.dart';
import 'package:bond_roof/bond_roof.dart';

import 'labels_es.dart';
import 'model_panel.dart';
import 'service_client.dart';
import 'tokens.dart';

class _Loaded {
  const _Loaded(this.label, this.measurement);
  final String label;
  final RoofMeasurement measurement;
}

/// The single screen: address, method, measure, fixtures, report.
class DemoPage extends StatefulWidget {
  const DemoPage({super.key});

  @override
  State<DemoPage> createState() => _DemoPageState();
}

class _DemoPageState extends State<DemoPage> {
  final _address = TextEditingController(text: DemoTokens.defaultAddress);
  final _service = ServiceClient();
  MeasureMethod _method = MeasureMethod.auto;
  bool _busy = false;
  bool _spanish = false;
  String? _status;
  String? _error;
  _Loaded? _loaded;
  List<String> _bundled = const [];
  List<String> _remote = const [];
  String? _selected;

  @override
  void initState() {
    super.initState();
    _loadFixtureLists();
  }

  @override
  void dispose() {
    _address.dispose();
    super.dispose();
  }

  Future<void> _loadFixtureLists() async {
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
    final remote = await _service.fixtures();
    if (!mounted) return;
    setState(() {
      final have = {for (final n in _bundled) ServiceClient.fixtureStem(n)};
      _remote = remote.where((n) => !have.contains(n)).toList();
    });
  }

  Future<void> _run(String label, Future<Map<String, dynamic>> Function() job) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final json = await job();
      // Envelopes (0.2) and bare models (0.1) both load.
      final measurement = RoofMeasurement.parseAny(json);
      if (!mounted) return;
      setState(() => _loaded = _Loaded(label, measurement));
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = '$e');
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _status = null;
        });
      }
    }
  }

  Future<void> _measure() {
    _selected = null;
    return _run(
      _method.label,
      () => _service.measure(
        _address.text.trim(),
        _method,
        onStatus: (s) {
          if (mounted) setState(() => _status = s);
        },
      ),
    );
  }

  Future<void> _loadBundled(String name) {
    setState(() => _selected = name);
    return _run(name, () async {
      final text = await rootBundle.loadString('${DemoTokens.fixtureAssetDir}$name');
      return jsonDecode(text) as Map<String, dynamic>;
    });
  }

  Future<void> _loadRemote(String name) {
    setState(() => _selected = 'remote:$name');
    return _run(name, () => _service.fixtureJson(name));
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
              TextField(
                controller: _address,
                decoration: const InputDecoration(
                  labelText: 'Address',
                  border: OutlineInputBorder(),
                ),
                onSubmitted: (_) => _busy ? null : _measure(),
              ),
              const SizedBox(height: DemoTokens.gap),
              Wrap(
                spacing: DemoTokens.gap,
                runSpacing: DemoTokens.gap,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  SegmentedButton<MeasureMethod>(
                    showSelectedIcon: false,
                    segments: [
                      for (final m in MeasureMethod.values)
                        ButtonSegment(value: m, label: Text(m.label)),
                    ],
                    selected: {_method},
                    onSelectionChanged: (s) => setState(() => _method = s.first),
                  ),
                  FilledButton(
                    onPressed: _busy ? null : _measure,
                    child: const Text('Measure'),
                  ),
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
                      onSelected: _busy ? null : (_) => _loadBundled(n),
                    ),
                  for (final n in _remote)
                    ChoiceChip(
                      label: Text('${n.replaceAll('.json', '')} (service)'),
                      selected: _selected == 'remote:$n',
                      onSelected: _busy ? null : (_) => _loadRemote(n),
                    ),
                  if (_bundled.isEmpty && _remote.isEmpty)
                    Text('No fixtures bundled. Run make sync-fixtures.',
                        style: theme.textTheme.bodySmall),
                ],
              ),
              const SizedBox(height: DemoTokens.gap),
              if (_busy)
                const LinearProgressIndicator(minHeight: DemoTokens.progressHeight),
              if (_status != null)
                Padding(
                  padding: const EdgeInsets.only(top: DemoTokens.gap / 2),
                  child: Text(_status!, style: theme.textTheme.bodyMedium),
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
              ] else if (!_busy)
                Padding(
                  padding: const EdgeInsets.only(top: DemoTokens.gapLarge),
                  child: Text(
                    'Pick a fixture or press Measure to see the diagrams.',
                    style: theme.textTheme.bodyMedium,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
