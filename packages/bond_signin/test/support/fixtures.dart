import 'dart:convert';
import 'dart:io';

/// Reads `../../fixtures/signin/<name>.json` (tests only).
Object? signinFixture(String name) =>
    jsonDecode(File('../../fixtures/signin/$name.json').readAsStringSync());

Map<String, Object?> signinMap(String name) => (signinFixture(name)! as Map).cast<String, Object?>();
