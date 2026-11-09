# Changelog

## Unreleased
- `SignInAttempt`, `SignInReturn`, `SignInApi` (alias `SignInClient`), `OidcAuthGateway`, `SignInLabels`.
- `SignInLabels`: messages for company_suspended, provider_not_allowed, invalid_request, invalid_origin, provider_error, invalid_id_token, unknown_provider, invalid_code.
- `SignInAttempt.fromJson` throws FormatException when the challenge is not sha256 of the secret.
- `SignInApi.redeem` and `OidcAuthGateway.completeNative` take an optional `deviceLabel` (sent as `device_label`). Labels for invalid_token and not_found.
- `startNative` takes `returnUrl` (a Uri, sent as redirect_to unchanged) instead of `returnBase`; `SignInApi` takes `prefix` and `OidcAuthGateway` `authPrefix` (default `/auth`).
