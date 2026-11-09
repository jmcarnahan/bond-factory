# Migrating to bond_connections and bond_connections_ui

`bond_connections` (pure Dart) holds the status model and the API client. `bond_connections_ui` holds the card, the
list and the return banner. The server half is `bond_oauth` (see `bond_oauth.md`); the routes are the ones in
`services/sdk_example/sdk_example/routes/connections.py`.

## 1. What the packages give you

| Name | Role |
|---|---|
| `ConnectionStatus` | One row of `GET /connections`: provider, connected, email, connectedAt, needsReconnect, scopes |
| `ConnectionPhase` | disconnected, connected, needsReconnect (derived; a needed reconnect wins). Not called `ConnectionState`: Flutter exports that name |
| `ConnectionsApi(ApiClient)` | `list()`, `startUrl(provider, redirectTo:)`, `disconnect(provider)` |
| `DemoConnectionsApi` | `simulateExpiry(provider)`, fake mode only |
| `ConnectionReturn.parse(Uri)` | Reads `connection=connected\|error`, `provider`, `reason` from the address the browser came back to; null when absent |
| `ConnectionLabels` | Every string, English defaults, `{provider}` placeholders, reason codes in plain words |
| `BondConnectionCard`, `BondConnectionsList`, `BondConnectionReturnBanner` | The widgets; `semanticsId` is a prefix (`sdk.connections` gives `.card-<p>`, `.connect-<p>`, `.reconnect-<p>`, `.disconnect-<p>`) |

## 2. App A: connect_gmail_card

- `ConnectGmailCard` becomes `BondConnectionCard` for provider `google`, fed by `ConnectionsApi.list()`.
- Its mail connection provider and notifier stay in the app: they only hold what `list()` returned and a busy flag.
- `?mail=connected|error` becomes `ConnectionReturn.parse(Uri.base)` shown by `BondConnectionReturnBanner`.
- `onOpenUrl` stays the app's choice. Web: navigate the whole window to `startUrl`. Phone: see section 4.
- The inline disconnect confirm is built in (two-step `BondConfirm`, no dialog).
- Dropped: the calendar permission line, the "fallback mailbox" line and the phone "check again" button. They are app
  details; keep them next to the card, or read `scopes` for the calendar one.
- The resume hook (`didChangeAppLifecycleState`) stays in the app: call `list()` again, there is nothing else to restore.

## 3. App S: connect_microsoft_screen and microsoft_status

- `MicrosoftStatus` and `GET /connections/microsoft/status` become `ConnectionStatus` and `GET /connections`.
- `needsConnect` (not connected, or stale scopes) is `phase != connected`. The server reports stale scopes as
  `needs_reconnect`; until the server does, compare `ConnectionStatus.scopes` with the wanted scopes in the app.
- `/connections/microsoft/authorize?token=` (a token in the query string) is replaced by `startUrl` and `/go`, which use
  the session cookie. No token is put in an address.
- `?connection=microsoft&status=success|error&message=` becomes `connection=connected|error&provider=microsoft&reason=`.
- The mandatory connect step after sign-in stays in the app's router; it reads `list()` and checks `phase`.
- The embedded web view, its redirect interception and the URL rewriting for a phone are not lifted (section 4).

## 4. The /go flow, the session cookie and the native limit

1. The app calls `startUrl(provider, redirectTo: '<origin>/connections')` with its bearer token. `redirectTo` must be on
   the server allowlist (`SDK_EXAMPLE_REDIRECT_ALLOWLIST`).
2. The app navigates the whole window to the returned `.../connections/<provider>/go?state=...`. The browser sends the
   API session cookie; the server checks the state belongs to that person, sets an httponly nonce cookie and redirects
   to the provider.
3. The callback needs both cookies, then redirects to `redirectTo` with `connection=` and `provider=`.
4. The app loads afresh. It reads the return parameters, shows the banner, and calls `list()`. Nothing is kept in memory
   across the trip.

On web the HTTP client must send cookies to the API origin (the demo uses a browser client with credentials, see
`demos/sdk_demo/lib/src/example_http_client_web.dart`) and the API and app must be same-site (SameSite=Lax).
Native apps have no browser session cookie, so `/go` answers them 401. They need the code-exchange variant that
`bond_oauth.md` lists as not built. Until then a phone app opens the web app's connections page in the system browser.

## 5. Acceptance

- `make -C packages/bond_connections test` and `analyze`; `make -C packages/bond_connections_ui test` and `analyze`.
- `make -C demos/sdk_demo test` and `analyze`; `make gates`.
- In the app: list shows each provider; connect leaves for the consent page and returns with the banner and the live
  status; simulate or suffer an expiry and see Reconnect; disconnect asks twice; no dialog or modal appears.
- No use of the old per-provider status route, the token-in-query authorize address or the web-view interception.

## 6. Known gaps

- Native code-exchange variant is not built (section 4).
- The demo navigates with `dart:js_interop`; an app that already depends on `package:web` can use `window.location.href`.
- The return parameters stay in the address bar after the banner is dismissed; `ConnectionReturn.cleaned` gives the
  address without them for apps whose router can replace the location.
- Display names and logos are the app's: pass `ConnectionLabels.providerNames` and `logo`.
