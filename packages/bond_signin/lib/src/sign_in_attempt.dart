import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';

/// One native sign-in attempt: the app is the PKCE client of the server.
///
/// [deviceChallenge] goes to `start`; [deviceSecret] is shown once, to
/// `redeem`, and never travels in a URL. Persist an attempt only in secure
/// storage, never in preferences. [id] is echoed back in the return
/// address so the app can drop a return that belongs to no pending attempt.
class SignInAttempt {
  const SignInAttempt({required this.id, required this.deviceSecret, required this.deviceChallenge});

  /// Makes a fresh attempt from the platform's secure random source. [random]
  /// is for tests only.
  factory SignInAttempt.generate({Random? random}) {
    final r = random ?? Random.secure();
    List<int> bytes(int n) => [for (var i = 0; i < n; i++) r.nextInt(256)];
    final id = bytes(16).map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    final secret = base64Url.encode(bytes(32)).replaceAll('=', '');
    return SignInAttempt(id: id, deviceSecret: secret, deviceChallenge: challengeFor(secret));
  }

  /// Reads a persisted attempt (an app keeps a pending one across a cold start).
  /// Throws [FormatException] when the challenge is not the sha256 of the secret.
  factory SignInAttempt.fromJson(Map<Object?, Object?> json) {
    final id = json['id'];
    final secret = json['device_secret'];
    final challenge = json['device_challenge'];
    if (id is! String || secret is! String || challenge is! String || id.isEmpty || secret.isEmpty) {
      throw const FormatException('not a sign-in attempt');
    }
    if (challenge != challengeFor(secret)) throw const FormatException('challenge does not match the secret');
    return SignInAttempt(id: id, deviceSecret: secret, deviceChallenge: challenge);
  }

  /// The challenge for [secret]: sha256 of its UTF-8 string, lowercase hex.
  static String challengeFor(String secret) => sha256.convert(utf8.encode(secret)).toString();

  /// 16 random bytes as 32 hex characters.
  final String id;

  /// 32 random bytes, base64url without padding.
  final String deviceSecret;

  /// sha256 hex (64 characters) of [deviceSecret].
  final String deviceChallenge;

  Map<String, Object?> toJson() => {'id': id, 'device_secret': deviceSecret, 'device_challenge': deviceChallenge};

  // Deliberately no secret in the text form: attempts end up in logs.
  @override
  String toString() => 'SignInAttempt($id)';
}
