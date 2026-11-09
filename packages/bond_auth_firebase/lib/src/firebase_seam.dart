/// The few FirebaseAuth calls the token source uses, behind small interfaces so
/// tests run with a fake and no Firebase app.
library;

import 'package:firebase_auth/firebase_auth.dart';

/// The signed-in Firebase user, as far as this package needs it.
abstract interface class FirebaseUserLike {
  String? get email;

  /// Provider ids linked to the account (`password`, `google.com`).
  List<String> get providerIds;

  Future<String?> getIdToken({bool forceRefresh = false});

  /// Re-reads the account from the server.
  Future<void> reload();

  Future<void> linkWithCredential(AuthCredential credential);

  /// Proves the current password (Firebase wants a recent sign-in to change it).
  Future<void> reauthenticateWithPassword(String email, String password);

  Future<void> updatePassword(String next);
}

/// `FirebaseAuth`, as far as this package needs it.
abstract interface class FirebaseAuthLike {
  FirebaseUserLike? get currentUser;

  Future<FirebaseUserLike?> signInWithEmailAndPassword(String email, String password);

  Future<FirebaseUserLike?> signInWithCredential(AuthCredential credential);

  Future<void> sendPasswordResetEmail(String email);

  Future<void> signOut();
}

/// The real [FirebaseAuth] behind [FirebaseAuthLike]. Needs an initialised
/// Firebase app, so it is not unit tested.
class FirebaseAuthAdapter implements FirebaseAuthLike {
  FirebaseAuthAdapter([FirebaseAuth? auth]) : _auth = auth;

  final FirebaseAuth? _auth;
  FirebaseAuth get _a => _auth ?? FirebaseAuth.instance;

  @override
  FirebaseUserLike? get currentUser {
    final u = _a.currentUser;
    return u == null ? null : FirebaseUserAdapter(u);
  }

  @override
  Future<FirebaseUserLike?> signInWithEmailAndPassword(String email, String password) async {
    final cred = await _a.signInWithEmailAndPassword(email: email, password: password);
    final u = cred.user;
    return u == null ? null : FirebaseUserAdapter(u);
  }

  @override
  Future<FirebaseUserLike?> signInWithCredential(AuthCredential credential) async {
    final cred = await _a.signInWithCredential(credential);
    final u = cred.user;
    return u == null ? null : FirebaseUserAdapter(u);
  }

  @override
  Future<void> sendPasswordResetEmail(String email) => _a.sendPasswordResetEmail(email: email);

  @override
  Future<void> signOut() => _a.signOut();
}

class FirebaseUserAdapter implements FirebaseUserLike {
  FirebaseUserAdapter(this._user);

  final User _user;

  @override
  String? get email => _user.email;

  @override
  List<String> get providerIds => [for (final p in _user.providerData) p.providerId];

  @override
  Future<String?> getIdToken({bool forceRefresh = false}) => _user.getIdToken(forceRefresh);

  @override
  Future<void> reload() => _user.reload();

  @override
  Future<void> linkWithCredential(AuthCredential credential) => _user.linkWithCredential(credential);

  @override
  Future<void> reauthenticateWithPassword(String email, String password) =>
      _user.reauthenticateWithCredential(EmailAuthProvider.credential(email: email, password: password));

  @override
  Future<void> updatePassword(String next) => _user.updatePassword(next);
}
