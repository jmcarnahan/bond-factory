/// Keeps the device registered: retries while the token is late, re-registers on refresh.
library;

import 'dart:async';

import 'push_devices.dart';
import 'push_token.dart';

class PushRegistrar {
  /// [retries] is how many more times the token is read after the first read
  /// came back empty, [retryDelay] apart (the Apple token arrives late). [delay]
  /// is injectable so tests do not wait.
  PushRegistrar(
    this.source,
    this.devices, {
    required this.deviceId,
    this.topic,
    this.retries = 5,
    this.retryDelay = const Duration(seconds: 2),
    Future<void> Function(Duration)? delay,
  }) : _delay = delay ?? Future<void>.delayed;

  final PushTokenSource source;
  final PushDevices devices;
  final String deviceId;
  final String? topic;
  final int retries;
  final Duration retryDelay;
  final Future<void> Function(Duration) _delay;

  final _errors = StreamController<Object>.broadcast();
  StreamSubscription<PushToken>? _refresh;
  int _run = 0; // bumped by every start and unregister; an older loop sees it change and stops
  bool _started = false;
  final _inFlight = <Future<bool>>{};
  bool _disposed = false;

  /// Failures of reading, registering or unregistering; `start` never throws.
  Stream<Object> get errors => _errors.stream;

  /// Registers now and again on every token refresh. A missing token and a
  /// failed register are both retried, [retries] times [retryDelay] apart;
  /// each failure goes to [errors]. It does not ask for permission: the app
  /// decides when to do that. Calling it while already started does nothing.
  Future<void> start() async {
    if (_started || _disposed) return;
    _started = true;
    final run = ++_run;
    _refresh ??= source.onRefresh.listen((t) => _registerRetrying(t, run), onError: _report);
    for (var attempt = 0; attempt <= retries; attempt++) {
      if (attempt > 0) await _delay(retryDelay);
      if (!_live(run)) return;
      PushToken? t;
      try {
        t = await source.token();
      } catch (e) {
        _report(e);
      }
      if (t != null) {
        await _registerRetrying(t, run);
        return;
      }
    }
  }

  bool _live(int run) => run == _run && !_disposed;

  /// Registers [t]; on failure waits and tries again, up to [retries] more times.
  Future<void> _registerRetrying(PushToken t, int run) async {
    for (var attempt = 0; attempt <= retries; attempt++) {
      if (attempt > 0) await _delay(retryDelay);
      if (!_live(run)) return;
      if (await _tryRegister(t)) return;
    }
  }

  /// One register call, tracked so [unregister] can wait for it.
  Future<bool> _tryRegister(PushToken t) {
    final call = () async {
      try {
        await devices.register(t, deviceId: deviceId, topic: topic);
        return true;
      } catch (e) {
        _report(e);
        return false;
      }
    }();
    _inFlight.add(call);
    return call.whenComplete(() => _inFlight.remove(call));
  }

  void _report(Object e, [StackTrace? st]) {
    if (!_errors.isClosed) _errors.add(e);
  }

  /// Stops listening and unregisters the device; call before sign-out. A
  /// failure goes to [errors] so it cannot block the sign-out. It waits for a
  /// register call in flight, and no later register happens. The registrar
  /// can [start] again afterwards (a new sign-in).
  Future<void> unregister() async {
    _run++;
    _started = false;
    await _refresh?.cancel();
    _refresh = null;
    // A register already on the wire must finish first, or it could land after
    // the unregister and leave the device registered.
    await Future.wait(_inFlight.toList());
    try {
      await devices.unregister(deviceId);
    } catch (e) {
      _report(e);
    }
  }

  void dispose() {
    _disposed = true;
    _refresh?.cancel();
    _refresh = null;
    _errors.close();
  }
}
