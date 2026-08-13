# How it works

pi-stream-deck is one Pi package containing a TypeScript session reporter and a detached
Node daemon. cmux supplies the live workspace and terminal topology.

```text
Pi session ── extension ──► status/<sessionId>.json ──┐
                                                       ├─► Node daemon ──► Stream Deck
cmux ── `cmux tree --all --json` ──► live topology ───┘       │
                                                         key press
                                                             ▼
                                      cmux surface/workspace focus RPCs
```

Everything is local; no session status or configuration is sent over the network.

## Session reporter

[`extension/pi-deck.ts`](../extension/pi-deck.ts) subscribes to Pi lifecycle events and
writes an atomic JSON snapshot containing session state, activity, repository or session
label, branch, model, working directory, cmux identifiers, and subagent relationship.
Writes are coalesced and a 15-second heartbeat distinguishes quiet sessions from dead
processes.

The same extension registers `/pi-stream-deck`. Its setup command invokes the bundled Node
entrypoint to write and load a launchd plist. Diagnostics and uninstall use that entrypoint
too, so no shell CLI or external checkout is needed.

## Node daemon

[`node/daemon.mjs`](../node/daemon.mjs) reads session snapshots, refreshes cmux topology,
builds a six-key scene, and sends it to the device. It reconnects automatically after an
unplug or device conflict. launchd starts it at login and keeps it alive.

The supporting modules are:

| Path | Responsibility |
|---|---|
| `node/core.mjs` | Paths, state model, status store, layout, and cmux RPCs |
| `node/render.mjs` | 80×80 RGBA key images rendered with `@napi-rs/canvas` |
| `node/device.mjs` | `@elgato-stream-deck/node` transport, animation, and presses |
| `node/daemon.mjs` | Runtime loop, launchd setup, diagnostics, and self-test |

The npm dependencies provide prebuilt macOS hardware and rendering bindings. Python,
Pillow, Homebrew hidapi, and Elgato's desktop application are not used.

## State and topology

The reporter uses Pi events rather than polling internals or scraping terminal output.
Working, question, waiting, compacting, idle, blocked, and ended states roll up to the
workspace key, with human-attention states taking priority.

The daemon calls:

```sh
cmux tree --all --json --id-format both
```

Live surface location overrides the workspace inherited when a terminal started, so moved
terminals appear in the correct workspace. Sessions outside cmux are grouped under
**elsewhere**. A short topology grace period masks brief cmux interruptions without leaving
closed workspaces on the deck indefinitely.

## Subagents

The reporter places the interactive session ID in `PI_DECK_PARENT`; headless children
inherit it. The store attaches those children to their top-level session. One child shows
its task label, while multiple children show a purple count badge and dots. An orphaned
headless session is promoted rather than hidden.

## Rendering and controls

`@napi-rs/canvas` paints raw RGBA images, which `@elgato-stream-deck/node` converts to the
Mini's native device format. The device module diffs scenes, preserves marquee position
through age updates, animates attention pulses, and distinguishes short presses from holds.

- Press a workspace to drill in, or directly focus its sole agent.
- Hold a workspace to focus it without drilling in.
- Press an agent to focus its cmux terminal surface.
- Press **back** to return to the workspace overview.

Focusing uses cmux `window.focus`, `workspace.select`, and `surface.focus` RPCs before
bringing cmux to the foreground.
