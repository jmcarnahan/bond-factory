import 'package:bond_json/bond_json.dart';

import 'status.dart';

/// One scope set the signed-in person's role wants connected but that may not
/// be granted yet: `{id, provider, label, scopes, granted}`.
class WantedSet {
  const WantedSet({
    required this.id,
    required this.provider,
    required this.label,
    this.scopes = const [],
    this.granted = false,
  });

  factory WantedSet.fromJson(Object? json) {
    if (json is! Map) throw JsonShapeError('', 'Map', describeJsonType(json));
    return WantedSet(
      id: jstr(json, 'id') ?? '',
      provider: jstr(json, 'provider') ?? '',
      label: jstr(json, 'label') ?? '',
      scopes: jlist<String>(json, 'scopes', (v) {
        if (v is String) return v;
        throw JsonShapeError('', 'String', describeJsonType(v));
      }),
      granted: jbool(json, 'granted') ?? false,
    );
  }

  /// The set id passed as `set=` to the connect start route.
  final String id;
  final String provider;
  final String label;
  final List<String> scopes;
  final bool granted;

  @override
  String toString() => 'WantedSet($id, $provider, granted: $granted)';
}

/// The `GET /connections` answer: one status per provider plus the wanted sets.
/// A server that predates the sets answers a bare array; that reads as no sets.
class ConnectionList {
  const ConnectionList({this.connections = const [], this.wanted = const []});

  /// Reads either the bare array or `{connections: [...], wanted: [...]}`.
  factory ConnectionList.fromJson(Object? json) {
    if (json is List) return ConnectionList(connections: jlistOf(json, ConnectionStatus.fromJson));
    if (json is! Map) throw JsonShapeError('', 'Map or List', describeJsonType(json));
    return ConnectionList(
      connections: jlist(json, 'connections', ConnectionStatus.fromJson),
      wanted: jlist(json, 'wanted', WantedSet.fromJson),
    );
  }

  final List<ConnectionStatus> connections;

  /// Sets the role wants and the policy reports on every read; empty when none.
  final List<WantedSet> wanted;
}
