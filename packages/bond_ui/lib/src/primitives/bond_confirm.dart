import 'dart:async';

import 'package:flutter/material.dart';

import '../labels.dart';
import '../semantics.dart' show bondSemanticsOption;
import '../tokens/tokens.dart';
import 'bond_confirm_line.dart';

/// Inline two-step confirmation for risky actions, with no dialog.
///
/// Idle: shows [trigger]. Tapping it calls `arm` and the row becomes
/// "Confirm . Cancel". The armed state ends by itself after [armTimeout]
/// (calling [onCancel]). Confirming runs [onConfirm]; when [undoWindow] is set
/// the row then shows "Sent . Undo" for that long and [onUndo] runs if the
/// person taps it.
///
/// With [semanticsId] the buttons are identified as `'<id>-confirm'`,
/// `'<id>-cancel'` and `'<id>-undo'`.
///
/// [identity] ties the armed state to one record: when the widget is reused
/// for another record the state resets. Pass a stable, value-equal id.
class BondConfirm extends StatefulWidget {
  const BondConfirm({
    super.key,
    required this.identity,
    required this.trigger,
    required this.onConfirm,
    this.confirmLabel,
    this.cancelLabel,
    this.doneLabel,
    this.undoLabel,
    this.onCancel,
    this.onUndo,
    this.undoWindow,
    this.armTimeout = const Duration(seconds: 10),
    this.initiallyDone = false,
    this.stacked = false,
    this.immediate = false,
    this.semanticsId,
  });

  final Object identity;
  final Widget Function(VoidCallback arm) trigger;
  final VoidCallback onConfirm;
  final String? confirmLabel;
  final String? cancelLabel;
  final String? doneLabel;
  final String? undoLabel;

  /// Runs when the armed state ends without confirming (cancel, timeout or a
  /// new [identity]).
  final VoidCallback? onCancel;

  /// Runs when the person undoes inside [undoWindow].
  final VoidCallback? onUndo;

  /// How long "Sent . Undo" shows after confirming. Null skips that state.
  final Duration? undoWindow;

  /// How long the armed "Confirm . Cancel" state waits before it disarms.
  /// Null waits forever.
  final Duration? armTimeout;

  /// Start in the "Sent . Undo" state, for an action that already happened.
  /// [undoWindow] is then the time left; when it is null or zero the widget
  /// starts idle.
  final bool initiallyDone;

  /// Lay the two actions one above the other (no dot between them) for a
  /// narrow, short space. They also stack at large text sizes.
  final bool stacked;

  /// One tap with undo: the trigger's `arm` confirms at once (no armed step),
  /// then "Sent . Undo" shows for [undoWindow]. For low-risk actions.
  final bool immediate;
  final String? semanticsId;

  @override
  State<BondConfirm> createState() => _BondConfirmState();
}

enum _Phase { idle, armed, done }

class _BondConfirmState extends State<BondConfirm> {
  _Phase _phase = _Phase.idle;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    final window = widget.undoWindow;
    if (widget.initiallyDone && window != null && window > Duration.zero) {
      _phase = _Phase.done;
      _startTimer(window, () => _phase = _Phase.idle);
    }
  }

  @override
  void didUpdateWidget(BondConfirm oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.identity != oldWidget.identity) {
      final wasArmed = _phase == _Phase.armed;
      _timer?.cancel();
      _phase = _Phase.idle;
      if (wasArmed) widget.onCancel?.call();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _startTimer(Duration d, void Function() end) {
    _timer?.cancel();
    _timer = Timer(d, () {
      if (mounted) setState(end);
    });
  }

  void _arm() {
    setState(() => _phase = _Phase.armed);
    final limit = widget.armTimeout;
    if (limit == null) return;
    _timer?.cancel();
    _timer = Timer(limit, _disarmByTimeout);
  }

  /// Sets the phase first, then tells the caller, so a throwing `onCancel`
  /// cannot leave the widget armed. The error is reported to the framework
  /// (a timer has no caller to rethrow to).
  void _disarmByTimeout() {
    if (!mounted) return;
    setState(() => _phase = _Phase.idle);
    try {
      widget.onCancel?.call();
    } catch (e, s) {
      FlutterError.reportError(FlutterErrorDetails(
        exception: e,
        stack: s,
        library: 'bond_ui',
        context: ErrorDescription('while cancelling an armed BondConfirm'),
      ));
    }
  }

  void _confirm() {
    final window = widget.undoWindow;
    if (window == null) {
      _timer?.cancel();
      setState(() => _phase = _Phase.idle);
      widget.onConfirm();
      return;
    }
    setState(() => _phase = _Phase.done);
    _startTimer(window, () => _phase = _Phase.idle);
    widget.onConfirm();
  }

  void _undo() {
    _timer?.cancel();
    setState(() => _phase = _Phase.idle);
    widget.onUndo?.call();
  }

  void _cancel() {
    _timer?.cancel();
    setState(() => _phase = _Phase.idle);
    widget.onCancel?.call();
  }

  @override
  Widget build(BuildContext context) {
    final labels = BondLabels.of(context);
    final t = BondTokens.of(context);
    final id = widget.semanticsId;
    switch (_phase) {
      case _Phase.idle:
        return widget.trigger(widget.immediate ? _confirm : _arm);
      case _Phase.armed:
        return BondConfirmLine(
          first: widget.confirmLabel ?? labels.confirm,
          firstColor: t.danger.press,
          onFirst: _confirm,
          second: widget.cancelLabel ?? labels.cancel,
          onSecond: _cancel,
          stacked: widget.stacked,
          firstId: id == null ? null : bondSemanticsOption(id, 'confirm'),
          secondId: id == null ? null : bondSemanticsOption(id, 'cancel'),
        );
      case _Phase.done:
        return BondConfirmLine(
          first: widget.doneLabel ?? labels.sent,
          firstColor: t.positive.base,
          onFirst: null,
          second: widget.undoLabel ?? labels.undo,
          onSecond: _undo,
          secondId: id == null ? null : bondSemanticsOption(id, 'undo'),
        );
    }
  }
}
