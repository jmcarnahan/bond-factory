/// Every string the sign-in widgets show, with English defaults.
class SignInLabels {
  const SignInLabels({
    this.title = 'Sign in',
    this.continueWithTemplate = 'Continue with {provider}',
    this.inviteOnly = 'Access is by invitation. Use the account your administrator invited.',
    this.breakGlass = 'Administrator sign-in',
    this.working = 'Signing in...',
    this.scopesTitle = 'Turn on access for your role',
    this.allow = 'Allow',
    this.messages = defaultMessages,
  });

  /// The refusal and session-end codes the server uses, in the order the
  /// contract lists them. Every one has a default message.
  static const List<String> codes = [
    'not_invited',
    'deactivated',
    'identity_mismatch',
    'email_not_verified',
    'tenant_mismatch',
    'consent_declined',
    'signin_expired',
    'invalid_state',
    'invalid_handoff',
    'account_mismatch',
    'refresh_reused',
    'refresh_expired',
    'refresh_revoked',
    'session_revoked',
    'company_suspended',
    'provider_not_allowed',
    'invalid_request',
    'invalid_origin',
    'provider_error',
    'invalid_id_token',
    'unknown_provider',
    'invalid_code',
    'invalid_token',
    'not_found',
    'unknown',
  ];

  static const Map<String, String> defaultMessages = {
    'not_invited': 'This account has not been invited. Ask your administrator for access.',
    'deactivated': 'This account has been deactivated. Contact your administrator.',
    'identity_mismatch': 'This sign-in does not match the account on file. Use the account you signed up with.',
    'email_not_verified': 'The e-mail address on this account is not verified. Verify it with the provider and try again.',
    'tenant_mismatch': 'This account belongs to a different organisation. Use your work account.',
    'consent_declined': 'Sign-in was cancelled. Try again when you are ready.',
    'signin_expired': 'The sign-in took too long. Start again.',
    'invalid_state': 'The sign-in was not started in this browser. Start again.',
    'invalid_handoff': 'The sign-in could not be completed. Start again.',
    'account_mismatch': 'That is not the account you are signed in with. Choose the same account.',
    'refresh_reused': 'You were signed out because this session was used somewhere else. Sign in again.',
    'refresh_expired': 'Your session expired. Sign in again.',
    'refresh_revoked': 'Your session was ended. Sign in again.',
    'session_revoked': 'Your session was ended. Sign in again.',
    'company_suspended': 'Your organisation\'s access is suspended. Contact your administrator.',
    'provider_not_allowed': 'This sign-in method is not allowed for your account. Use the one your administrator set up.',
    'invalid_request': 'The sign-in request was not valid. Start again.',
    'invalid_origin': 'Sign-in was started from an address that is not allowed. Open the app from its usual address.',
    'provider_error': 'The sign-in provider could not be reached. Try again in a moment.',
    'invalid_id_token': 'The provider\'s answer could not be verified. Try again.',
    'unknown_provider': 'That sign-in provider is not available here.',
    'invalid_code': 'The sign-in code was not valid. Start again.',
    'invalid_token': 'Your session is not valid. Sign in again.',
    'not_found': 'That sign-in could not be found. Start again.',
    'unknown': 'Sign-in failed. Try again.',
  };

  final String title;

  /// Uses `{provider}` for the provider's name.
  final String continueWithTemplate;
  final String inviteOnly;

  /// The link that reveals the administrator (break-glass) sign-in.
  final String breakGlass;
  final String working;

  /// Heading of the scope-ask card, and the button on each of its rows.
  final String scopesTitle;
  final String allow;

  /// Message per code; a code with no entry reads as `unknown`.
  final Map<String, String> messages;

  String continueWith(String provider) => continueWithTemplate.replaceAll('{provider}', provider);

  /// The message for [code] (null or unlisted codes read as `unknown`).
  String messageFor(String? code) => messages[code] ?? messages['unknown'] ?? defaultMessages['unknown']!;
}
