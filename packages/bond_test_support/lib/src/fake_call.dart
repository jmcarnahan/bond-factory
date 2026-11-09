/// A recording stand-in for one function.
library;

/// Records every call and answers with canned results or errors.
///
/// ```dart
/// final load = FakeCall<int>()..returns(1)..throwsOnce(StateError('x'));
/// ```
/// Answers are served in the order they were queued; the last [returns] value
/// stays as the answer once the queue is empty. A queued error is thrown once.
class FakeCall<T> {
  FakeCall({T? result}) {
    if (result is T) returns(result);
  }

  final List<Object?> _args = [];
  final List<_Answer<T>> _queue = [];
  _Answer<T>? _sticky;

  /// The argument of each call, oldest first. Pass a record, list or map to
  /// capture several values.
  List<Object?> get calls => List.unmodifiable(_args);

  int get count => _args.length;

  bool get wasCalled => _args.isNotEmpty;

  /// The argument of the latest call.
  Object? get last => _args.isEmpty ? null : _args.last;

  /// Answer every call from now on with [value] (after any queued answers).
  void returns(T value) => _sticky = _Answer<T>.value(value);

  /// Queue [values], each answering one call.
  void returnsInOrder(Iterable<T> values) => _queue.addAll(values.map(_Answer<T>.value));

  /// Queue an error thrown by the next unanswered call.
  void throwsOnce(Object error) => _queue.add(_Answer<T>.error(error));

  /// Throw [error] on every call from now on (after any queued answers).
  void throwsAlways(Object error) => _sticky = _Answer<T>.error(error);

  /// Forget recorded calls and every queued or sticky answer.
  void reset() {
    _args.clear();
    _queue.clear();
    _sticky = null;
  }

  /// Records [args] and answers.
  T call([Object? args]) {
    _args.add(args);
    final answer = _queue.isNotEmpty ? _queue.removeAt(0) : _sticky;
    if (answer == null) throw StateError('FakeCall has no answer queued (call #${_args.length})');
    return answer.get();
  }

  /// [call] as a future, for async seams.
  Future<T> callAsync([Object? args]) async => call(args);
}

class _Answer<T> {
  _Answer.value(T this._value) : _error = null;
  _Answer.error(Object this._error) : _value = null;

  final T? _value;
  final Object? _error;

  T get() {
    final e = _error;
    if (e != null) throw e;
    return _value as T;
  }
}
