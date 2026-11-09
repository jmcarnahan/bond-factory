import 'package:bond_auth_firebase/bond_auth_firebase.dart';
import 'package:firebase_auth/firebase_auth.dart' show AuthCredential, FirebaseAuthException;

class FakeUser implements FirebaseUserLike {
  FakeUser({this.email = 'a@example.com', List<String>? providers}) : providerIds = providers ?? ['password'];

  @override
  String? email;
  @override
  List<String> providerIds;

  int tokenCount = 0;
  final List<String> calls = [];
  Object? tokenError;
  Object? reloadError;
  Object? reauthError;
  AuthCredential? linked;

  @override
  Future<String?> getIdToken({bool forceRefresh = false}) async {
    calls.add(forceRefresh ? 'getIdToken(force)' : 'getIdToken');
    final e = tokenError;
    if (e != null) throw e;
    return 'id-${++tokenCount}';
  }

  @override
  Future<void> reload() async {
    calls.add('reload');
    final e = reloadError;
    if (e != null) throw e;
  }

  @override
  Future<void> linkWithCredential(AuthCredential credential) async => linked = credential;

  @override
  Future<void> reauthenticateWithPassword(String email, String password) async {
    calls.add('reauth:$password');
    final e = reauthError;
    if (e != null) throw e;
  }

  @override
  Future<void> updatePassword(String next) async => calls.add('updatePassword:$next');
}

class FakeAuth implements FirebaseAuthLike {
  FakeAuth([this.currentUser]);

  @override
  FakeUser? currentUser;

  Object? signInError;
  AuthCredential? credentialUsed;
  final List<String> calls = [];

  @override
  Future<FirebaseUserLike?> signInWithEmailAndPassword(String email, String password) async {
    calls.add('signIn:$email');
    final e = signInError;
    if (e != null) throw e;
    return currentUser = FakeUser(email: email);
  }

  @override
  Future<FirebaseUserLike?> signInWithCredential(AuthCredential credential) async {
    credentialUsed = credential;
    final e = signInError;
    if (e != null) throw e;
    return currentUser = FakeUser();
  }

  @override
  Future<void> sendPasswordResetEmail(String email) async => calls.add('reset:$email');

  @override
  Future<void> signOut() async {
    calls.add('signOut');
    currentUser = null;
  }
}

FirebaseAuthException authError(String code) => FirebaseAuthException(code: code, message: 'm');
