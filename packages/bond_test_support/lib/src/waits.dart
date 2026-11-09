/// Waiting helpers. Every wait ends on its positive signal and fails on its
/// cap: hitting a cap is a bug in the test or the code, never a reason to wait
/// longer.
library;

import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

const Duration kWaitTimeout = Duration(seconds: 5);

/// Pumps 50 ms frames (fake time) until [finder] matches something. Fails with
/// a readable message when [timeout] of fake time has passed.
Future<void> pumpUntil(
  WidgetTester t,
  Finder finder, {
  Duration timeout = kWaitTimeout,
}) =>
    pumpUntilThat(t, () => finder.evaluate().isNotEmpty, what: finder.describeMatch(Plurality.one), timeout: timeout);

/// Like [pumpUntil] for any condition; [what] names it in the failure.
Future<void> pumpUntilThat(
  WidgetTester t,
  bool Function() ok, {
  required String what,
  Duration timeout = kWaitTimeout,
}) async {
  const step = Duration(milliseconds: 50);
  var waited = Duration.zero;
  await t.pump();
  while (!ok()) {
    if (waited >= timeout) {
      throw TestFailure('pumpUntil timed out after ${timeout.inMilliseconds} ms waiting for $what');
    }
    await t.pump(step);
    waited += step;
  }
}

/// Calls [probe] every [every] (real time) until it returns a value, and
/// returns it. Fails after [timeout]. For plain `test(` bodies; inside a
/// widget test wrap the call in `tester.runAsync`.
Future<T> pollUntil<T>(
  Future<T?> Function() probe, {
  Duration timeout = kWaitTimeout,
  Duration every = const Duration(milliseconds: 20),
  String what = 'a value',
}) async {
  final clock = Stopwatch()..start();
  while (true) {
    final v = await probe();
    if (v != null) return v;
    if (clock.elapsed > timeout) {
      throw TestFailure('pollUntil timed out after ${clock.elapsed.inMilliseconds} ms waiting for $what');
    }
    await Future<void>.delayed(every);
  }
}

/// Collects what a stream emits so a test can wait for the emission it needs
/// instead of sleeping. Cancels itself at teardown.
class Emissions<T> {
  Emissions(Stream<T> stream) {
    _sub = stream.listen(
      (v) {
        values.add(v);
        _wake();
      },
      onError: (Object e, StackTrace st) {
        errors.add(e);
        _wake();
      },
      onDone: () {
        done = true;
        _wake();
      },
    );
    addTearDown(cancel);
  }

  /// Values in arrival order.
  final List<T> values = [];

  /// Errors in arrival order.
  final List<Object> errors = [];

  /// True once the stream has closed.
  bool done = false;

  late final StreamSubscription<T> _sub;
  final List<(bool Function(), Completer<void>)> _waiters = [];

  void _wake() {
    for (final w in List.of(_waiters)) {
      if (w.$1()) {
        _waiters.remove(w);
        w.$2.complete();
      }
    }
  }

  /// Completes when [ok] holds (checked now and after every event). Fails
  /// after [timeout] of real time.
  Future<void> until(bool Function() ok, {String what = 'a condition', Duration timeout = kWaitTimeout}) async {
    if (ok()) return;
    final c = Completer<void>();
    final w = (ok, c);
    _waiters.add(w);
    final timer = Timer(timeout, () {
      if (c.isCompleted) return;
      _waiters.remove(w);
      c.completeError(TestFailure('timed out after ${timeout.inMilliseconds} ms waiting for $what'));
    });
    try {
      await c.future;
    } finally {
      timer.cancel();
    }
  }

  /// Waits until at least [n] values have arrived and returns them.
  Future<List<T>> take(int n, {Duration timeout = kWaitTimeout}) async {
    await until(() => values.length >= n, what: '$n values (have ${values.length})', timeout: timeout);
    return List.of(values);
  }

  /// Waits until the stream closes.
  Future<void> untilDone({Duration timeout = kWaitTimeout}) =>
      until(() => done, what: 'the stream to close', timeout: timeout);

  Future<void> cancel() => _sub.cancel();
}
