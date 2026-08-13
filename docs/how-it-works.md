# How it works

pi-stream-deck has two cooperating parts: a small TypeScript extension running inside each
Pi session and a Python daemon driving the Stream Deck. cmux provides the live workspace
and terminal topology that joins them together.

```text
Pi session ── extension ──► status/<sessionId>.json ──┐
                                                       ├─► Python daemon ──► Stream Deck
cmux ── `cmux tree --all --json` ──► live topology ───┘         │
                                                           key press
                                                               ▼
                                        cmux surface/workspace focus RPCs
```

All communication is local. The project does not send session status or configuration over
the network.

## Pi session reporter

[`extension/pi-deck.ts`](../extension/pi-deck.ts) is loaded into every Pi session. It
subscribes to Pi lifecycle events and writes a compact JSON snapshot containing:

- session ID and process ID
- state and current activity
- repository or session label
- Git branch and model
- working directory
- cmux workspace, surface, and pane identifiers
- subagent role and parent session ID
- state and heartbeat timestamps

Writes are coalesced to avoid unnecessary disk activity. A 15-second heartbeat lets the
daemon distinguish a quiet live session from a process that disappeared. A graceful
`session_shutdown` writes an `ended` tombstone for the daemon to reap.

The reporter uses Pi events rather than polling Pi internals or scraping terminal output:

| Event | Reported effect |
|---|---|
| `before_agent_start`, `turn_start` | agent is working |
| `tool_execution_start` | current tool and a short activity summary |
| `ask_user`, `ask_user_form` execution | waiting for an answer |
| `tool_execution_end` | returns to thinking |
| `session_before_compact`, `session_compact` | enters/leaves compacting state |
| `agent_settled` | turn is complete and waiting for the user |
| `session_shutdown` | session ended |

## Shared status store

Snapshots are written under the resolved data directory, normally:

```text
~/.pi/agent/pi-stream-deck/status/<sessionId>.json
```

See the [configuration guide](configuration.md) for directory resolution and environment
overrides. Atomic temporary-file renames prevent the daemon from reading partial JSON.
Dead processes and shutdown tombstones are filtered or reaped when status files are read.

## cmux topology

[`pideck/cmux.py`](../pideck/cmux.py) calls:

```sh
cmux tree --all --json --id-format both
```

The result is flattened into windows, workspaces, panes, and terminal surfaces. The live
surface location is authoritative: if a terminal moves between workspaces, the daemon uses
its current cmux location instead of the workspace ID inherited when the terminal started.
Pi sessions outside cmux remain visible in a trailing **elsewhere** workspace.

The daemon caches the last good topology through short cmux interruptions. If cmux remains
unavailable past `topology_grace`, the cache is dropped so closed workspaces do not linger
as phantom keys.

## Model and layout

[`pideck/store.py`](../pideck/store.py) joins session snapshots to the cmux topology and
produces workspace models. [`pideck/layout.py`](../pideck/layout.py) then turns that model
into six key specifications.

The workspace overview shows:

- one key per cmux workspace, in cmux sidebar order
- one coloured dot per top-level Pi session
- smaller purple dots for attached subagents
- the most attention-hungry state as the key's colour band
- session count, latest activity age, and selected-workspace marker

Pressing a workspace opens its agents view unless it has exactly one agent and direct focus
is enabled. The agents view shows each session's label, activity, state, age, and subagent
count. The final key returns to the workspace overview; pagination uses another key when a
view has more entries than available slots.

The ordering used for workspace state roll-up is:

```text
blocked → question → waiting → idle → compacting → working → ended
```

This makes a session needing human attention win over background work.

## Subagents

The reporter places the current Pi session ID in `PI_DECK_PARENT`, which child processes
inherit. Headless children identify themselves as subagents and
report that parent ID. The store attaches them to the top-level interactive session rather
than assigning each child a full-size key.

A single child contributes its task label to the parent key. Multiple children appear as a
purple `⤷N` badge. If a headless session's parent cannot be found, it is promoted instead
of disappearing.

## Rendering and device input

[`pideck/render.py`](../pideck/render.py) paints 80×80 RGB key images with Pillow.
[`pideck/device.py`](../pideck/device.py) sends changed images to the Stream Deck, animates
long-title marquees and attention pulses, and distinguishes short presses from holds.

Input is translated back into cmux actions:

- press a workspace to drill in or directly focus its only agent
- hold a workspace to focus it without drilling in
- press an agent to focus its terminal surface
- press **back** to return to the workspace overview

Focusing uses cmux `window.focus`, `workspace.select`, and `surface.focus` RPCs before
bringing cmux to the foreground.

## Daemon loop

[`pideck/daemon.py`](../pideck/daemon.py) coordinates topology refreshes, status reads,
layout, rendering, and key actions. It reconnects automatically when the Stream Deck is
unplugged or busy. With the default installation, launchd keeps this daemon running and
starts it at login.

The major modules are:

| Path | Responsibility |
|---|---|
| `extension/pi-deck.ts` | Report Pi session state |
| `pideck/cmux.py` | Read cmux topology and issue focus RPCs |
| `pideck/store.py` | Read snapshots, attach subagents, and join topology |
| `pideck/model.py` | Workspace and agent state model |
| `pideck/layout.py` | Convert models into six key specifications |
| `pideck/render.py` | Paint key images |
| `pideck/device.py` | Stream Deck transport, animation, and presses |
| `pideck/daemon.py` | Main runtime loop |
