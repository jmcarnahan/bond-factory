import 'dart:convert';

import 'package:bond_api/bond_api.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import '../example_api.dart';
import '../theme.dart';
import 'page_scaffold.dart';

/// Three calls against the example service and how bond_api reports each:
/// `GET /health` (JSON), `GET /nope` (NotFound) and `POST /auth/firebase {}`
/// (ValidationError with its fields). The outcome shows inline under
/// `sdk.api.result`.
class ApiPage extends StatefulWidget {
  const ApiPage({super.key});

  @override
  State<ApiPage> createState() => _ApiPageState();
}

class _ApiPageState extends State<ApiPage> {
  String _result = 'No call yet.';
  bool _busy = false;

  Future<void> _run(Future<String> Function() call) async {
    setState(() {
      _busy = true;
      _result = 'Calling...';
    });
    String text;
    try {
      text = await call();
    } on ApiException catch (e) {
      text = describeFailure(e);
    }
    if (!mounted) return;
    setState(() {
      _busy = false;
      _result = text;
    });
  }

  Future<String> _health() async =>
      const JsonEncoder.withIndent('  ').convert(await DemoSession.health());

  Future<String> _notFound() async {
    await DemoSession.api.getJson('/nope');
    return 'Unexpected: /nope answered.';
  }

  Future<String> _validation() async {
    await DemoSession.api.postJson('/auth/firebase', body: <String, Object?>{});
    return 'Unexpected: an empty sign-in was accepted.';
  }

  @override
  Widget build(BuildContext context) {
    return DemoScope(
      child: PageFrame(
        title: 'API',
        children: [
          Wrap(spacing: 8, runSpacing: 8, children: [
            BondButton(
              label: 'Health',
              onPressed: _busy ? null : () => _run(_health),
              semanticsId: 'sdk.api.health',
            ),
            BondButton(
              label: 'Not found',
              variant: BondButtonVariant.secondary,
              onPressed: _busy ? null : () => _run(_notFound),
              semanticsId: 'sdk.api.not-found',
            ),
            BondButton(
              label: 'Validation',
              variant: BondButtonVariant.secondary,
              onPressed: _busy ? null : () => _run(_validation),
              semanticsId: 'sdk.api.validation',
            ),
          ]),
          const SizedBox(height: 16),
          Semantics(
            identifier: 'sdk.api.result',
            container: true,
            child: SelectableText(_result, key: const Key('api-result')),
          ),
        ],
      ),
    );
  }
}

/// A failure as readable lines: its type, status, code, message and, for a
/// validation failure, one line per field.
String describeFailure(ApiException e) {
  final lines = <String>['${e.runtimeType}${e.statusCode == null ? '' : ' (${e.statusCode})'}'];
  final code = switch (e) {
    NotFound(:final code) => code,
    Unauthorized(:final code) => code,
    Forbidden(:final code) => code,
    Conflict(:final code) => code,
    BadRequest(:final code) => code,
    ValidationError(:final code) => code,
    ServerError(:final code) => code,
    _ => null,
  };
  if (code != null) lines.add('code: $code');
  lines.add('message: ${e.message}');
  if (e is ValidationError) {
    for (final f in e.fields.entries) {
      lines.add('field ${f.key}: ${f.value}');
    }
  }
  return lines.join('\n');
}
