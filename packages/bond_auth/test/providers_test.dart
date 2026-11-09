import 'package:bond_auth/bond_auth.dart';
import 'package:test/test.dart';

Map<String, Object?> firebaseJson({bool web = true, bool ios = true}) => {
      'project_id': 'demo-project',
      'auth_domain': 'demo-project.example.org',
      'messaging_sender_id': '123',
      if (web) 'web': {'api_key': 'k-web', 'app_id': 'a-web'},
      if (ios) 'ios': {'api_key': 'k-ios', 'app_id': 'a-ios', 'bundle_id': 'org.example.app'},
    };

void main() {
  group('FirebaseRuntimeConfig', () {
    test('complete web and ios blocks', () {
      final c = FirebaseRuntimeConfig.fromProviders({'firebase': firebaseJson()})!;
      expect(c.projectId, 'demo-project');
      expect(c.webComplete, isTrue);
      expect(c.iosComplete, isTrue);
      expect(c.web!.apiKey, 'k-web');
      expect(c.ios!.bundleId, 'org.example.app');
    });

    test('only the web block is complete', () {
      final c = FirebaseRuntimeConfig.fromProviders({'firebase': firebaseJson(ios: false)})!;
      expect(c.webComplete, isTrue);
      expect(c.iosComplete, isFalse);
      expect(c.ios, isNull);
    });

    test('a block missing a key counts as absent', () {
      final json = firebaseJson(ios: false);
      json['web'] = {'api_key': 'k-web'};
      expect(FirebaseRuntimeConfig.fromProviders({'firebase': json}), isNull);
    });

    test('null or missing firebase object gives null', () {
      expect(FirebaseRuntimeConfig.fromProviders({'firebase': null}), isNull);
      expect(FirebaseRuntimeConfig.fromProviders({}), isNull);
    });

    test('a missing project id gives null', () {
      final json = firebaseJson()..remove('project_id');
      expect(FirebaseRuntimeConfig.fromProviders({'firebase': json}), isNull);
    });

    test('web needs the auth domain', () {
      final json = firebaseJson(ios: false)..['auth_domain'] = '';
      expect(FirebaseRuntimeConfig.fromProviders({'firebase': json}), isNull);
    });
  });

  group('AuthProviders', () {
    test('parses the merged shape', () {
      final p = AuthProviders.fromJson({
        'demo': true,
        'email_password': true,
        'google': true,
        'google_web_client_id': 'cid',
        'apple': false,
        'mock': true,
        'firebase': firebaseJson(),
        'sync': {'url': 'https://sync.example.org'},
      });
      expect(p.demo && p.emailPassword && p.google && p.mock, isTrue);
      expect(p.apple, isFalse);
      expect(p.googleWebClientId, 'cid');
      expect(p.firebase!.projectId, 'demo-project');
      expect(p.syncUrl, Uri.parse('https://sync.example.org'));
    });

    test('an empty object is all off', () {
      final p = AuthProviders.fromJson({});
      expect(p.demo || p.emailPassword || p.google || p.apple || p.mock, isFalse);
      expect(p.firebase, isNull);
      expect(p.syncUrl, isNull);
    });

    test('null sync url stays null', () {
      expect(AuthProviders.fromJson({'sync': {'url': null}}).syncUrl, isNull);
    });
  });
}
