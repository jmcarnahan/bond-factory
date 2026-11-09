/// Every string the connection widgets show, with English defaults. Titles
/// and messages use `{provider}` for the provider's display name.
class ConnectionLabels {
  const ConnectionLabels({
    this.providerNames = const {},
    this.connect = 'Connect',
    this.reconnect = 'Reconnect',
    this.disconnect = 'Disconnect',
    this.stateConnected = 'Connected',
    this.stateDisconnected = 'Not connected',
    this.stateNeedsReconnect = 'Needs reconnect',
    this.connectedAs = 'Connected as {email}',
    this.connectedOn = 'Since {date}',
    this.needsReconnectHint = 'Access was withdrawn or expired. Connect again to keep it working.',
    this.returnConnectedTitle = '{provider} connected',
    this.returnErrorTitle = 'Could not connect {provider}',
    this.returnErrorGeneric = 'Something went wrong. Try again.',
    this.returnReasons = const {
      'access_denied': 'Access was declined.',
      'unavailable': 'The provider could not be reached. Try again in a moment.',
      'invalid_state': 'The sign-in was not started in this browser. Start again.',
      'expired_state': 'The sign-in took too long. Start again.',
      'not_confirmed': 'Nothing changed: this provider is not connected.',
      'account_mismatch': 'That is a different account than the one you signed in with.',
      'consent_declined': 'You did not allow that access. You can allow it later.',
      'forbidden': 'You do not have permission to connect this.',
    },
    this.dismiss = 'Dismiss',
    this.emptyTitle = 'No providers',
    this.emptyMessage = 'No connections are set up here.',
  });

  /// Display names by provider id; an id with no entry is shown as is.
  final Map<String, String> providerNames;
  final String connect;
  final String reconnect;
  final String disconnect;
  final String stateConnected;
  final String stateDisconnected;
  final String stateNeedsReconnect;
  final String connectedAs;
  final String connectedOn;
  final String needsReconnectHint;
  final String returnConnectedTitle;
  final String returnErrorTitle;
  final String returnErrorGeneric;

  /// Server error codes to plain text.
  final Map<String, String> returnReasons;
  final String dismiss;
  final String emptyTitle;
  final String emptyMessage;

  String providerName(String provider) => providerNames[provider] ?? provider;

  /// [template] with `{name}` placeholders replaced from [values].
  static String fill(String template, Map<String, String> values) =>
      values.entries.fold(template, (s, e) => s.replaceAll('{${e.key}}', e.value));

  String connectedTitleFor(String? provider) =>
      fill(returnConnectedTitle, {'provider': provider == null ? '' : providerName(provider)}).trim();

  String errorTitleFor(String? provider) =>
      fill(returnErrorTitle, {'provider': provider == null ? 'the provider' : providerName(provider)});

  /// Plain text for a server error [reason]; the generic line when unknown.
  String reasonText(String? reason) => returnReasons[reason] ?? returnErrorGeneric;
}
