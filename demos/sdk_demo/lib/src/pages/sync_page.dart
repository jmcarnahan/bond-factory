import 'dart:async';

import 'package:bond_api/bond_api.dart';
import 'package:bond_json/bond_json.dart';
import 'package:bond_sync/bond_sync.dart';
import 'package:bond_sync/testing.dart';
import 'package:flutter/material.dart';

import '../example_api.dart';
import 'page_scaffold.dart';

/// Local rows in a [FakeSyncStore] go to the live `POST /sync/upload` through
/// [ApiSyncTransport]; every row shows its verdict inline, one row is refused
/// on purpose, and the page then fixes it, sends again, and shows the server
/// clock and a sync token. No database: PowerSync on the web needs wasm assets,
/// so the adapter is covered by unit tests only. Ids are `sdk.sync.<element>`.
class SyncPage extends StatefulWidget {
  const SyncPage({super.key, this.transport, this.ensureSignedIn});

  /// Defaults to [ApiSyncTransport] over the shared demo client.
  final SyncTransport? transport;

  /// Defaults to [DemoSession.ensureSignedIn].
  final Future<Object?> Function()? ensureSignedIn;

  @override
  State<SyncPage> createState() => _SyncPageState();
}

class _SyncPageState extends State<SyncPage> {
  static const String _table = 'notes';

  final FakeSyncStore _store = FakeSyncStore(coalesce: true);
  final ServerClock _clock = ServerClock();
  late final SyncTransport _transport = widget.transport ?? ApiSyncTransport(DemoSession.api);
  late final SyncUploader _uploader = SyncUploader(
    store: _store,
    transport: _transport,
    clock: _clock,
    onServerNow: (t) => _serverNow = t,
  );

  List<Map<String, Object?>> _rows = const [];
  List<SyncRejection> _notes = const [];
  Map<String, UploadOutcome> _verdicts = const {};
  final Set<String> _onServer = {};
  DateTime? _serverNow;
  String? _tokenText;
  String? _error;
  String? _info;
  bool _busy = false;
  int _n = 0;

  Future<void> _reload() async {
    final rows = await _store.rows(_table);
    final notes = await _store.rejections();
    if (mounted) {
      setState(() {
        _rows = rows;
        _notes = notes;
      });
    }
  }

  void _add({required bool bad}) {
    _n += 1;
    _store.put(_table, newId(), {
      'title': bad ? '' : 'Note $_n',
      'body': bad ? 'This note has no title' : 'Written offline',
      'updated_at': isoOf(_clock.now()),
    });
    unawaited(_reload());
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
      _info = null;
    });
    try {
      await action();
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = _describe(e));
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  static String _describe(ApiException e) => e is ServerError && e.code != null
      ? 'code: ${e.code} | message: ${e.message}'
      : '${e.runtimeType} | message: ${e.message}';

  Future<void> _signIn() => (widget.ensureSignedIn ?? DemoSession.ensureSignedIn)();

  Future<void> _upload() => _run(() async {
        await _signIn();
        final s = await _uploader.uploadPending();
        await _reload();
        if (!mounted) return;
        setState(() {
          _verdicts = {for (final o in s.outcomes) o.op.id: o};
          for (final o in s.outcomes) {
            if (o.verdict.isOk || !o.verdict.needsAction) _onServer.add(o.op.id);
          }
          _info = s.retryLater != null
              ? 'Stopped early: offline or the server is busy. The rest stays queued.'
              : s.isEmpty
                  ? 'Nothing was waiting.'
                  : 'Sent ${s.outcomes.length}: ${s.ok} accepted, ${s.rejected} refused, ${s.skipped} skipped.';
        });
      });

  /// Edits the refused row's title, queues the write again and clears the note.
  Future<void> _fixRow() => _run(() async {
        if (_notes.isEmpty) return;
        final note = _notes.first;
        final row = _rows.firstWhere((r) => r['id'] == note.rowId, orElse: () => const {});
        _store.put(_table, note.rowId, {
          'body': row['body'] ?? '',
          'title': 'Fixed title',
          'updated_at': isoOf(_clock.now()),
        });
        await _store.clearRejection(note.id);
        _verdicts = {for (final e in _verdicts.entries) if (e.key != note.rowId) e.key: e.value};
        await _reload();
      });

  Future<void> _fetchToken() => _run(() async {
        await _signIn();
        final t = await _transport.fetchToken();
        final now = t.serverNow;
        if (now != null) {
          _clock.note(now);
          _serverNow = now;
        }
        if (!mounted) return;
        final tail = t.token.length <= 6 ? t.token : t.token.substring(t.token.length - 6);
        setState(() => _tokenText = 'Token ends $tail | expires_at ${jiso(t.expiresAt)} | endpoint ${t.endpoint ?? 'none'}');
      });

  @override
  Widget build(BuildContext context) {
    final queued = _store.queuedOps;
    return PageFrame(
      title: 'Sync',
      children: [
        Wrap(spacing: 8, runSpacing: 8, children: [
          _button('add-row', 'Add row', () => _add(bad: false), enabled: true),
          _button('add-bad-row', 'Add bad row', () => _add(bad: true), enabled: true),
          _button('upload', 'Upload', _upload, filled: true),
          _button('fix-row', 'Fix row', _fixRow, enabled: _notes.isNotEmpty),
          _button('resend', 'Send again', _upload),
          _button('fetch-token', 'Fetch token', _fetchToken),
        ]),
        const SizedBox(height: 12),
        _labelled('queued', 'Queued writes: $queued'),
        if (_info != null) _labelled('info', _info!),
        if (_error != null) _labelled('error', _error!, color: Theme.of(context).colorScheme.error),
        const SizedBox(height: 12),
        Semantics(
          identifier: 'sdk.sync.rows',
          container: true,
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            if (_rows.isEmpty) const Text('No rows yet. Add one.'),
            for (final r in _rows) _rowTile(r),
          ]),
        ),
        const SizedBox(height: 12),
        _labelled('server-clock', _clockText()),
        if (_tokenText != null) ...[
          const SizedBox(height: 8),
          _labelled('token', _tokenText!),
        ],
      ],
    );
  }

  /// A text a walk reads: the visible text is also the semantics label (the
  /// identifier carries no text), and the inner Text is hidden from the tree so
  /// it is not read twice.
  Widget _labelled(String id, String text, {Color? color}) => Semantics(
        identifier: 'sdk.sync.$id',
        label: text,
        container: true,
        excludeSemantics: true,
        child: Text(text, style: color == null ? null : TextStyle(color: color)),
      );

  String _clockText() {
    final now = _serverNow;
    if (now == null) return 'Server clock: not known yet';
    final ms = _clock.skew.inMilliseconds;
    return 'Server clock: server_now ${jiso(now)} | skew ${ms >= 0 ? '+' : ''}$ms ms (server minus device)';
  }

  Widget _rowTile(Map<String, Object?> row) {
    final id = row['id'] as String;
    final title = (row['title'] as String?) ?? '';
    final outcome = _verdicts[id];
    return Card(
      key: ValueKey('sync-row-$id'),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title.isEmpty ? '(no title)' : title, style: Theme.of(context).textTheme.titleSmall),
          Text('${row['body'] ?? ''}'),
          Text('id ${id.length > 8 ? id.substring(0, 8) : id}', style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 6),
          if (outcome != null)
            _verdict(outcome)
          else
            Text(_onServer.contains(id) ? 'On the server' : 'Waiting to be sent', style: Theme.of(context).textTheme.bodySmall),
        ]),
      ),
    );
  }

  Widget _verdict(UploadOutcome o) {
    final v = o.verdict;
    final text = !v.needsAction && v.isOk
        ? 'ok${v.resolvedId == null ? '' : ' (server id ${v.resolvedId})'}'
        : !v.needsAction
            ? '${v.status}: ${v.code}'
            : '${v.status}: ${v.code ?? v.status} | ${verdictText(v.code ?? v.status, message: v.message)}'
                '${v.message == null ? '' : ' (server said: ${v.message})'}';
    return _labelled(
      'verdict-${o.op.seq}',
      text,
      color: v.needsAction ? Theme.of(context).colorScheme.error : null,
    );
  }

  Widget _button(String id, String label, VoidCallback onPressed, {bool filled = false, bool enabled = true}) {
    final tap = _busy || !enabled ? null : onPressed;
    return Semantics(
      identifier: 'sdk.sync.$id',
      label: label,
      child: filled ? FilledButton(onPressed: tap, child: Text(label)) : OutlinedButton(onPressed: tap, child: Text(label)),
    );
  }
}
