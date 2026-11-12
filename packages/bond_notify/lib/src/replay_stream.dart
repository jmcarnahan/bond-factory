/// A broadcast stream that gives each new listener the last value first.
library;

import 'dart:async';

/// Broadcast fan-out with replay of the latest value. [onFirstListen] and
/// [onNoListeners] fire as the listener count goes 0 to 1 and 1 to 0.
class ReplayStream<T> {
  ReplayStream({this.onFirstListen, this.onNoListeners});

  final void Function()? onFirstListen;
  final void Function()? onNoListeners;

  final _live = StreamController<T>.broadcast();
  T? _value;
  bool _has = false;
  int _listeners = 0;

  bool get hasValue => _has;
  T? get value => _value;
  int get listenerCount => _listeners;

  void add(T v) {
    _value = v;
    _has = true;
    if (!_live.isClosed) _live.add(v);
  }

  void addError(Object e, [StackTrace? st]) {
    if (!_live.isClosed) _live.addError(e, st);
  }

  /// A new broadcast stream per call; it first replays the held value.
  Stream<T> get stream {
    late StreamController<T> c;
    StreamSubscription<T>? sub;
    c = StreamController<T>.broadcast(
      onListen: () {
        _listeners++;
        if (_has) c.add(_value as T);
        sub = _live.stream.listen(c.add, onError: c.addError);
        if (_listeners == 1) onFirstListen?.call();
      },
      onCancel: () {
        sub?.cancel();
        sub = null;
        _listeners--;
        if (_listeners == 0) onNoListeners?.call();
      },
    );
    return c.stream;
  }

  Future<void> close() async {
    await _live.close();
  }
}
