# sdk_demo

Flutter web harness for the bond SDK packages. Never shipped. Seven pages: Home lists the routes, UI is the
`bond_ui` widget gallery, API probes health and errors, Sign in (`/auth`) runs direct sign-in against the example's fake providers (system-browser round trip, cookie session, renew, replayed-token sign-out, break-glass form behind a server flag), Sync uploads rows
with per-row verdicts, Connections runs the fake OAuth round trip and the role scope ask card, and Tasks manages tasks with reminders and a
calendar mirror. Wiring is shown in `docs/sdk/examples.md`; the browser walk recipe is `docs/test/WEB.md`.
