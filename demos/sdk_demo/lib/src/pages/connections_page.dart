import 'package:bond_api/bond_api.dart';
import 'package:bond_connections/bond_connections.dart';
import 'package:bond_connections_ui/bond_connections_ui.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import '../example_api.dart';
import '../theme.dart';
import 'connections_nav_io.dart' if (dart.library.js_interop) 'connections_nav_web.dart';
import 'page_scaffold.dart';

const _labels = ConnectionLabels(providerNames: {
  'fake-google': 'Fake Google',
  'fake-microsoft': 'Fake Microsoft',
  'google': 'Google',
  'microsoft': 'Microsoft',
});

/// OAuth connections against the example API. On build it signs in and reads
/// `GET /connections`; Connect asks for the start address and sends the whole
/// browser window there (top level, so the API session cookie goes along). The
/// provider, or in fake mode the consent page, then sends the browser back to
/// `/connections?connection=connected&provider=...`, the app loads afresh and
/// shows the return banner. Nothing is kept in memory across that trip: every
/// state on screen comes from `GET /connections`. Dismissing the banner does not
/// touch the address bar: the return query stays until the next navigation (an app
/// with a router can replace the location with `ConnectionReturn.cleaned`).
/// Ids are `sdk.connections.<element>`.
class ConnectionsPage extends StatefulWidget {
  const ConnectionsPage({super.key, this.currentUrl, this.ensureSignedIn, this.navigate, this.replaceUrl});

  /// The address the page was opened with; defaults to the browser's.
  final Uri? currentUrl;

  /// Defaults to [DemoSession.ensureSignedIn].
  final Future<Object?> Function()? ensureSignedIn;

  /// Sends the browser to the start address and returns true; returns false
  /// when there is no browser (the page then shows the address). Defaults to a
  /// real top-level navigation on web.
  final bool Function(Uri url)? navigate;

  /// Puts the cleaned address (return parameters removed) in the address bar.
  /// Defaults to `history.replaceState` on web and nothing elsewhere.
  final void Function(Uri url)? replaceUrl;

  @override
  State<ConnectionsPage> createState() => _ConnectionsPageState();
}

class _ConnectionsPageState extends State<ConnectionsPage> {
  late final ConnectionsApi _api = ConnectionsApi(DemoSession.api);
  late final DemoConnectionsApi _demo = DemoConnectionsApi(DemoSession.api);

  /// What the address said, until the first list read judges it.
  late ConnectionReturn? _claimed = ConnectionReturn.parse(_here);

  /// The banner on screen: the claim after it was checked against the list.
  ConnectionReturn? _return;

  /// Whether the session may change connections; null until signed in.
  bool? _canManage;

  List<ConnectionStatus>? _statuses;
  String? _busy;
  String? _error;
  Uri? _startUrl;

  Uri get _here => widget.currentUrl ?? Uri.base;

  /// Where the provider sends the browser back to: this app's /connections.
  String? get _redirectTo => _here.scheme.startsWith('http') ? '${_here.origin}/connections' : null;

  @override
  void initState() {
    super.initState();
    _run(null, () async {});
  }

  Future<void> _signIn() => (widget.ensureSignedIn ?? DemoSession.ensureSignedIn)();

  /// Runs [action] for [provider] (null = the page itself), then reads the list again.
  Future<void> _run(String? provider, Future<void> Function() action) async {
    setState(() {
      _busy = provider ?? '';
      _error = null;
    });
    try {
      await _signIn();
      // No session object (an injected sign-in) means unknown: leave the decision to the server.
      final caps = DemoSession.session?.capabilities;
      final allowed = caps == null || caps.contains('connections.manage');
      await action();
      final fresh = await _api.list();
      if (mounted) {
        setState(() {
          _canManage = allowed;
          _statuses = fresh;
          _judgeReturn(fresh);
        });
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = _describe(e));
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }

  /// Once, after the first list read: a "connected" claim in the address only
  /// counts when the list says so (a typed address proves nothing); otherwise
  /// the banner says nothing changed. Then the return parameters leave the
  /// address bar, so a reload or a later disconnect cannot bring the banner back.
  void _judgeReturn(List<ConnectionStatus> fresh) {
    final claim = _claimed;
    if (claim == null) return;
    _claimed = null;
    final provider = claim.provider;
    final confirmed = provider == null
        ? fresh.any((s) => s.connected)
        : fresh.any((s) => s.provider == provider && s.connected);
    _return = claim.isError || confirmed
        ? claim
        : ConnectionReturn(ConnectionOutcome.error, provider: provider, reason: 'not_confirmed');
    final cleaned = ConnectionReturn.cleaned(_here);
    final custom = widget.replaceUrl;
    if (custom != null) {
      custom(cleaned);
    } else {
      final failure = replaceAddress(cleaned);
      if (failure != null) _error = failure;
    }
  }

  /// The server's error code when the answer carried one, else the exception type.
  static String _describe(ApiException e) {
    final code = switch (e) {
      Unauthorized(:final code) => code,
      Forbidden(:final code) => code,
      NotFound(:final code) => code,
      Conflict(:final code) => code,
      BadRequest(:final code) => code,
      ValidationError(:final code) => code,
      ServerError(:final code) => code,
      _ => null,
    };
    return code != null ? 'code: $code | message: ${e.message}' : '${e.runtimeType} | message: ${e.message}';
  }

  Future<void> _connect(String provider) async {
    setState(() {
      _busy = provider;
      _error = null;
      _startUrl = null;
    });
    try {
      await _signIn();
      final url = await _api.startUrl(provider, redirectTo: _redirectTo);
      final left = (widget.navigate ?? navigateTopLevel)(url);
      if (!left && mounted) setState(() => _startUrl = url);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = _describe(e));
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }

  static const String _noManage = 'This account cannot change connections (it needs the connections.manage capability).';

  /// A text node a walk can find: the identifier AND the text as the semantics
  /// label, on its own node (`container`) so it never merges into an ancestor.
  /// [keepChild] leaves the child's own semantics in place (selectable text keeps
  /// its selection actions); the text is then read by the child as well.
  static Widget _labeled(String id, String text, Widget child, {bool keepChild = false}) => Semantics(
        identifier: 'sdk.connections.$id',
        label: text,
        container: true,
        excludeSemantics: !keepChild,
        child: child,
      );

  @override
  Widget build(BuildContext context) {
    final statuses = _statuses;
    return DemoScope(
      child: PageFrame(
        title: 'Connections',
        children: [
          if (_return != null) ...[
            BondConnectionReturnBanner(
              _return!,
              labels: _labels,
              onDismiss: () => setState(() => _return = null),
              semanticsId: 'sdk.connections.return',
            ),
            BondSpace.h12,
          ],
          if (_canManage == false)
            _labeled(
              'no-manage',
              _noManage,
              const Padding(padding: EdgeInsets.only(bottom: 12), child: Text(_noManage)),
            ),
          if (_error != null)
            _labeled('error', _error!, Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error))),
          if (_startUrl != null)
            _labeled(
              'start-url',
              'Open this address in a browser: $_startUrl',
              SelectableText('Open this address in a browser: $_startUrl'),
              keepChild: true,
            ),
          if (statuses == null && _error == null)
            _labeled('loading', 'Loading connections...', const Text('Loading connections...')),
          if (statuses != null)
            Semantics(
              identifier: 'sdk.connections.list',
              container: true,
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                for (final s in statuses) ...[_provider(s), BondSpace.h12],
              ]),
            ),
        ],
      ),
    );
  }

  Widget _provider(ConnectionStatus s) {
    final busy = _busy == s.provider || _busy == '';
    final manage = _canManage != false;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      BondConnectionCard(
        key: ValueKey('connection-${s.provider}'),
        status: s,
        labels: _labels,
        busy: busy,
        semanticsId: 'sdk.connections',
        onConnect: manage ? () => _connect(s.provider) : null,
        onReconnect: manage ? () => _connect(s.provider) : null,
        onDisconnect: manage ? () => _run(s.provider, () => _api.disconnect(s.provider)) : null,
      ),
      if (manage && s.phase == ConnectionPhase.connected) ...[
        BondSpace.h4,
        BondButton(
          label: 'Simulate expiry',
          variant: BondButtonVariant.quiet,
          onPressed: busy ? null : () => _run(s.provider, () => _demo.simulateExpiry(s.provider)),
          semanticsId: 'sdk.connections.simulate-expiry-${s.provider}',
        ),
      ],
    ]);
  }
}
