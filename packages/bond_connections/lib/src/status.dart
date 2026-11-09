import 'package:bond_json/bond_json.dart';

/// Where one connection stands, derived from a [ConnectionStatus]. Not named
/// `ConnectionState`: Flutter's widgets library already exports that name.
enum ConnectionPhase {
  /// Nothing connected for this provider.
  disconnected,

  /// A live connection whose tokens work.
  connected,

  /// A connection exists but the provider refused the stored grant: the
  /// person has to connect again.
  needsReconnect,
}

/// One row of `GET /connections`:
/// `{provider, connected, email, connected_at, needs_reconnect, scopes}`.
class ConnectionStatus {
  const ConnectionStatus({
    required this.provider,
    this.connected = false,
    this.email,
    this.connectedAt,
    this.needsReconnect = false,
    this.scopes = const [],
  });

  /// Reads one status. A missing key reads as empty or false; a value of the
  /// wrong type throws [JsonShapeError]. `scopes` may be a space-separated
  /// string or a list of strings.
  factory ConnectionStatus.fromJson(Object? json) {
    if (json is! Map) throw JsonShapeError('', 'Map', describeJsonType(json));
    final raw = json['scopes'];
    final List<String> scopes;
    if (raw is String) {
      scopes = raw.split(RegExp(r'\s+')).where((s) => s.isNotEmpty).toList();
    } else {
      scopes = jlist<String>(json, 'scopes', (v) {
        if (v is String) return v;
        throw JsonShapeError('', 'String', describeJsonType(v));
      });
    }
    return ConnectionStatus(
      provider: jstr(json, 'provider') ?? '',
      connected: jbool(json, 'connected') ?? false,
      email: jstr(json, 'email'),
      connectedAt: jtime(json, 'connected_at'),
      needsReconnect: jbool(json, 'needs_reconnect') ?? false,
      scopes: scopes,
    );
  }

  /// The registered provider name (`google`, `microsoft`, `fake-google`).
  final String provider;
  final bool connected;
  final String? email;
  final DateTime? connectedAt;
  final bool needsReconnect;
  final List<String> scopes;

  /// A needed reconnect wins over `connected`.
  ConnectionPhase get phase {
    if (needsReconnect) return ConnectionPhase.needsReconnect;
    if (connected) return ConnectionPhase.connected;
    return ConnectionPhase.disconnected;
  }

  Map<String, Object?> toJson() => {
        'provider': provider,
        'connected': connected,
        'email': email,
        'connected_at': connectedAt == null ? null : jiso(connectedAt!),
        'needs_reconnect': needsReconnect,
        'scopes': scopes,
      };

  @override
  bool operator ==(Object other) =>
      other is ConnectionStatus &&
      other.provider == provider &&
      other.connected == connected &&
      other.email == email &&
      other.connectedAt == connectedAt &&
      other.needsReconnect == needsReconnect &&
      other.scopes.join(' ') == scopes.join(' ');

  @override
  int get hashCode => Object.hash(provider, connected, email, connectedAt, needsReconnect, scopes.join(' '));

  @override
  String toString() => 'ConnectionStatus($provider, $phase)';
}
