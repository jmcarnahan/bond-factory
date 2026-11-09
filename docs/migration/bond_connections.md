# Migrating to bond_connections and bond_connections_ui

`bond_connections` (pure Dart) holds the status model and the API client. `bond_connections_ui` holds the card, the
list and the return banner. The server half is `bond_oauth` (see `bond_oauth.md`); the routes are the ones in
`services/sdk_example/sdk_example/routes/connections.py`.

## 1. What the packages give you

| Name | Role |
|---|---|
| `ConnectionStatus` | One row of `GET /connections`: provider, connected, email, connectedAt, needsReconnect, scopes |
| `ConnectionPhase` | disconnected, connected, needsReconnect (derived; a needed reconnect wins). Not called `ConnectionState`: Flutter exports that name |
| `ConnectionsApi(ApiClient)` | `list()` (bare array only), `listAll()` (the `{connections, wanted}` answer; use it), `wanted()`, `startUrl(provider, redirectTo:, native:, set:, deviceChallenge:, attempt:)`, `redeem(provider, code, deviceSecret:)`, `disconnect(provider)` |
| `ConnectionList`, `WantedSet` | `{connections, wanted}`; a set is `{id, provider, label, scopes, granted}`; `listAll()` reads a bare array as no sets |
| `DemoConnectionsApi` | `simulateExpiry(provider)`, fake mode only |
| `ConnectionReturn.parse(Uri)` | Reads `connection=connected\|error`, `provider`, `reason`, `code` and `attempt` (native) from the address the browser came back to; null when absent |
| `ConnectionLabels` | Every string, English defaults, `{provider}` placeholders, reason codes in plain words (including `consent_declined`, `account_mismatch`) |
| `BondConnectionCard`, `BondConnectionsList`, `BondConnectionReturnBanner` | The widgets; `semanticsId` is a prefix (`sdk.connections` gives `.card-<p>`, `.connect-<p>`, `.reconnect-<p>`, `.disconnect-<p>`) |

## 2. App A: connect_gmail_card

- `ConnectGmailCard` becomes `BondConnectionCard` for provider `google`, fed by `ConnectionsApi.listAll()`.
- Its mail connection provider and notifier stay in the app: they only hold what `listAll()` returned and a busy flag.
- `?mail=connected|error` becomes `ConnectionReturn.parse(Uri.base)` shown by `BondConnectionReturnBanner`.
- `onOpenUrl` stays the app's choice. Web: navigate the whole window to `startUrl`. Phone: see section 4.
- The inline disconnect confirm is built in (two-step `BondConfirm`, no dialog).
- Dropped: the calendar permission line, the "fallback mailbox" line and the phone "check again" button. They are app
  details; keep them next to the card, or read `scopes` for the calendar one.
- The resume hook (`didChangeAppLifecycleState`) stays in the app: call `listAll()` again, there is nothing else to restore.

## 3. App S: connect_microsoft_screen and microsoft_status

- `MicrosoftStatus` and `GET /connections/microsoft/status` become `ConnectionStatus` and `GET /connections`.
- `needsConnect` (not connected, or stale scopes) is `phase != connected`. The server reports stale scopes as
  `needs_reconnect`; until the server does, compare `ConnectionStatus.scopes` with the wanted scopes in the app.
- `/connections/microsoft/authorize?token=` (a token in the query string) is replaced by `startUrl` and `/go`, which use
  the session cookie. No token is put in an address.
- `?connection=microsoft&status=success|error&message=` becomes `connection=connected|error&provider=microsoft&reason=`.
- The mandatory connect step after sign-in stays in the app's router; it reads `listAll()` and checks `phase`.
- The embedded web view, its redirect interception and the URL rewriting for a phone are not lifted (section 4).

## 4. The /go flow, the session cookie and the native limit

1. The app calls `startUrl(provider, redirectTo: '<origin>/connections')` with its bearer token. `redirectTo` must be on
   the server allowlist (`SDK_EXAMPLE_REDIRECT_ALLOWLIST`).
2. The app navigates the whole window to the returned `.../connections/<provider>/go?state=...`. The browser sends the
   API session cookie; the server checks the state belongs to that person, sets an httponly nonce cookie and redirects
   to the provider.
3. The callback needs both cookies, then redirects to `redirectTo` with `connection=` and `provider=`.
4. The app loads afresh. It reads the return parameters, shows the banner, and calls `listAll()`. Nothing is kept in memory
   across the trip.

On web the HTTP client must send cookies to the API origin (the demo uses a browser client with credentials, see
`demos/sdk_demo/lib/src/example_http_client_web.dart`) and the API and app must be same-site (SameSite=Lax).
Native apps have no browser session cookie, so they use the code-exchange variant below.

### Phone apps

1. Make a device secret and its sha256 challenge (`SignInAttempt` in `bond_signin`). `startUrl(provider, redirectTo: <return url>,
   native: true, deviceChallenge:, attempt:)` with the bearer token; `redirectTo` is the same https app link or native scheme as sign-in.
2. Open that URL in the system browser session (`BrowserAuth` in `bond_signin_ui`); no cookie is needed or set.
3. The server redirects to the return URL with `connection=connected&provider=<p>&attempt=<id>&code=<handoff>` (or `connection=error`).
   Read it with `ConnectionReturn.parse(uri)`.
4. Call `redeem(provider, code, deviceSecret: secret)` with the bearer token. The connection is stored only now, only for the user who
   started the flow and only with the right secret; the code works once, within 120 s. It returns the status.

## 5. Role asks (`wanted` sets)

- `GET /connections` reports `wanted` on every read: the sets the person's capabilities want that the live connection does not
  hold. A set is asked through the same flow, `startUrl(provider, set: <id>)`; an unknown set is 400. A promotion shows the ask on
  the next load; a declined ask leaves the set wanted with `consent_declined`.
- `BondScopeAskCard(wanted, onAsk)` (in `bond_signin_ui`) shows each ungranted set inline with one button; no dialog.
  `BondConnectionsList` keeps showing status and reconnect.
- Native: `startUrl(..., native: true)` needs `deviceChallenge` and `attempt`; the return carries `attempt` as well as `code`. The app drops
  a return whose `attempt` is not the pending one and passes its device secret to `redeem`. Return URL rules: `bond_signin.md`.
- A connect for a different account than the signed-in one returns `connection=error&reason=account_mismatch`, except shared connects.
  A consent that leaves the asked set unticked stores no row and returns `consent_declined`.

## 6. Acceptance

- `make -C packages/bond_connections test` and `analyze`; `make -C packages/bond_connections_ui test` and `analyze`.
- `make -C demos/sdk_demo test` and `analyze`; `make gates`.
- In the app: list shows each provider; connect leaves for the consent page and returns with the banner and the live
  status; simulate or suffer an expiry and see Reconnect; disconnect asks twice; no dialog or modal appears.
- No use of the old per-provider status route, the token-in-query authorize address or the web-view interception.

## 7. Known gaps

- Hand-offs are DB rows (`oauth_handoffs`); the old process-local registry is deprecated until 0.3.0. See `bond_oauth.md` section 6.
- The navigation helpers moved from the demo into `bond_signin_ui` (`lib/src/browser/`); the demo imports them.
- `ConnectionReturn.cleaned` gives the address without the return parameters; the demo clears the address after the first read.
- Display names and logos are the app's: pass `ConnectionLabels.providerNames` and `logo`.
