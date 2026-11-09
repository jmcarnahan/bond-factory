/// Starts Firebase from the server's public client config, so the app compiles
/// in no generated options file.
library;

import 'dart:async';

import 'package:bond_auth/bond_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart' show visibleForTesting;

typedef FirebaseInitializer = Future<void> Function(FirebaseOptions options);

Future<bool>? _ready;

/// The options for this platform, or null when its block is incomplete.
FirebaseOptions? firebaseOptionsFor(FirebaseRuntimeConfig c, {required bool isWeb}) {
  if (isWeb) {
    final w = c.web;
    if (!c.webComplete || w == null) return null;
    return FirebaseOptions(
      apiKey: w.apiKey,
      appId: w.appId,
      messagingSenderId: c.messagingSenderId,
      projectId: c.projectId,
      authDomain: c.authDomain,
    );
  }
  final i = c.ios;
  if (!c.iosComplete || i == null) return null;
  return FirebaseOptions(
    apiKey: i.apiKey,
    appId: i.appId,
    messagingSenderId: c.messagingSenderId,
    projectId: c.projectId,
    iosBundleId: i.bundleId,
  );
}

/// Calls `Firebase.initializeApp` once, and only when no app exists yet.
/// Returns false when this platform's config block is incomplete (nothing was
/// started). A success is remembered; a failure is not, so the next call tries
/// again. [initializer] and [appsEmpty] exist for tests.
Future<bool> initFirebaseFromRuntimeConfig(
  FirebaseRuntimeConfig config, {
  required bool isWeb,
  FirebaseInitializer? initializer,
  bool Function()? appsEmpty,
}) {
  final running = _ready;
  if (running != null) return running;
  final options = firebaseOptionsFor(config, isWeb: isWeb);
  if (options == null) return Future.value(false);
  final f = _start(options, initializer, appsEmpty);
  _ready = f;
  unawaited(f.then((_) {}, onError: (Object _) {
    if (identical(_ready, f)) _ready = null;
  }));
  return f;
}

Future<bool> _start(FirebaseOptions options, FirebaseInitializer? initializer, bool Function()? appsEmpty) async {
  final isEmpty = (appsEmpty ?? () => Firebase.apps.isEmpty)();
  if (isEmpty) await (initializer ?? (o) => Firebase.initializeApp(options: o))(options);
  return true;
}

/// Forgets the remembered start (tests).
@visibleForTesting
void resetFirebaseInit() => _ready = null;
