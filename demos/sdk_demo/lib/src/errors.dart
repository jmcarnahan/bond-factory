import 'package:flutter/foundation.dart';

/// Runtime errors shown as an inline strip at the top of the shell, so a walk
/// can read them without any dialog. Newest first, exact duplicates dropped,
/// at most [maxEntries] kept.
final class DemoErrors extends ValueNotifier<List<String>> {
  DemoErrors() : super(const <String>[]);

  static const int maxEntries = 20;
  static final DemoErrors instance = DemoErrors();

  void add(String message) {
    // Defer: errors can be reported while a frame is building.
    Future<void>.microtask(() {
      if (value.contains(message)) return;
      value = <String>[message, ...value].take(maxEntries).toList(growable: false);
    });
  }

  void clear() => value = const <String>[];
}

/// Routes framework and async errors into [DemoErrors] and still lets the
/// previous handlers run.
void installErrorCapture() {
  final previous = FlutterError.onError;
  FlutterError.onError = (details) {
    DemoErrors.instance.add(details.exceptionAsString());
    previous?.call(details);
  };
  final previousPlatform = PlatformDispatcher.instance.onError;
  PlatformDispatcher.instance.onError = (error, stack) {
    DemoErrors.instance.add(error.toString());
    return previousPlatform?.call(error, stack) ?? false;
  };
}
