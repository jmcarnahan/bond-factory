/// Firebase's error codes, folded into the few reasons a sign-in screen words.
library;

import 'package:bond_auth/bond_auth.dart';
import 'package:firebase_auth/firebase_auth.dart' show FirebaseAuthException;

/// Unknown e-mail and wrong password are one reason: a screen never reveals
/// which accounts exist.
AuthFailure failureFor(FirebaseAuthException e) => AuthFailure(
      switch (e.code) {
        'invalid-credential' ||
        'wrong-password' ||
        'user-not-found' ||
        'invalid-login-credentials' =>
          AuthFailureReason.wrongCredentials,
        'invalid-email' || 'missing-email' => AuthFailureReason.invalidEmail,
        'too-many-requests' => AuthFailureReason.rateLimited,
        'user-disabled' => AuthFailureReason.disabled,
        // A transient provider fault is not a refusal of the person.
        'network-request-failed' || 'internal-error' => AuthFailureReason.network,
        'account-exists-with-different-credential' => AuthFailureReason.accountExistsWithDifferentCredential,
        'credential-already-in-use' || 'provider-already-linked' => AuthFailureReason.alreadyLinked,
        'weak-password' || 'password-does-not-meet-requirements' => AuthFailureReason.weakPassword,
        'admin-restricted-operation' => AuthFailureReason.notInvited,
        'web-context-cancelled' || 'popup-closed-by-user' || 'canceled' || 'sign_in_canceled' =>
          AuthFailureReason.cancelled,
        _ => AuthFailureReason.other,
      },
      code: e.code,
      message: e.message,
    );
