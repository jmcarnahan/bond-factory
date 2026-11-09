/// The one-time value that ties a Sign in with Apple answer to this attempt.
library;

import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';

/// Apple gets [hashed] (SHA-256 of [raw], lowercase hex); Firebase gets [raw]
/// and checks that Apple's token carries its hash.
class AppleNonce {
  const AppleNonce(this.raw);

  /// 32 random bytes as 64 hex characters, from a secure source unless a test
  /// passes its own [Random].
  factory AppleNonce.generate([Random? random]) {
    final r = random ?? Random.secure();
    final bytes = List<int>.generate(32, (_) => r.nextInt(256));
    return AppleNonce(bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join());
  }

  final String raw;

  String get hashed => sha256.convert(utf8.encode(raw)).toString();
}
