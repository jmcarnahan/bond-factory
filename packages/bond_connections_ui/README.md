# bond_connections_ui

Connection widgets on `bond_ui` and `bond_connections`: a card per provider, a list, and the inline notice shown
after the browser returns from the provider. No dialogs: disconnect is an inline two-step `BondConfirm`.

| Widget | Shows |
|---|---|
| `BondConnectionCard` | Name (optional logo), state chip, e-mail, connected date, buttons by state |
| `BondConnectionsList` | One card per status; callbacks get the provider id; inline empty state |
| `BondConnectionReturnBanner` | Positive notice for `connected`, danger notice with the reason in words for `error` |

Buttons by state: disconnected shows Connect; connected shows Disconnect (two steps); needs reconnect shows a hint,
Reconnect and Disconnect. A button whose callback is null is left out, and `busy` makes the buttons wait.

```dart
BondConnectionsList(
  statuses: statuses,                          // from ConnectionsApi.list()
  labels: const ConnectionLabels(providerNames: {'google': 'Google'}),
  onConnect: (p) => start(p),
  onReconnect: (p) => start(p),
  onDisconnect: (p) => disconnect(p),
  busyProvider: busy,
  semanticsId: 'app.connections',
);
if (back != null) BondConnectionReturnBanner(back, onDismiss: clear);
```

- `semanticsId` is a prefix. `app.connections` gives `app.connections.card-<provider>`, `.state-<provider>`,
  `.connect-<provider>`, `.reconnect-<provider>`, `.disconnect-<provider>` (the confirm step adds `-confirm`
  and `-cancel`). The state chip node `.state-<provider>` and the banner node `<id>` carry their text as the
  semantics label, so a walk can read them; the banner's dismiss button is `<id>-dismiss`.
- Dates go through `formatDate`; the default is `YYYY-MM-DD` in UTC. Strings come from `ConnectionLabels`.
- The connect flow itself (start address, top-level navigation, session cookie) is described in
  `docs/migration/bond_connections.md`; `demos/sdk_demo/lib/src/pages/connections_page.dart` is a working page.
- Dismissing the banner does not touch the address bar. Replace the location with `ConnectionReturn.cleaned`
  if the router allows it.

Tests: `make test T=test/connections_ui_test.dart`. They pump with `pumpApp(t, widget, theme:
BondTheme.build(BondTokens.fallback))`, use `setPhone` for 390 px and end with `expectNoOverlays`.
