# pi-stream-deck

[![Tests](https://github.com/raldred/pi-stream-deck/actions/workflows/test.yml/badge.svg)](https://github.com/raldred/pi-stream-deck/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Turn an Elgato Stream Deck Mini into a live status board and remote control for
[pi](https://github.com/earendil-works/pi-coding-agent) agents running in
[cmux](https://cmux.com) workspaces.

> The project is named **pi-stream-deck**; its command and local configuration keep the
> shorter `pi-deck` name.

## What it does

**Top level: your cmux workspaces.** One key per workspace, in sidebar order, so key
positions match what you already see. Each key shows the workspace title, a coloured band
for the most attention-hungry agent in it, one dot per pi session, an `Nπ` badge, and how
long since anything changed. A pulsing amber/red key means an agent in there is waiting on
you; the pulse gets faster and darker the longer you ignore it.

**Press a workspace → its agents.** One key per pi session in that workspace: repo (or
session name), what it is doing right now (`bash: pytest`), state, and age. The bottom-right
key goes back.

**Press an agent → you are there.** cmux is brought to the front with that workspace
selected and that terminal surface focused.

**Subagents do not get their own key.** A headless `pi -p` child spawned by a session shows
up as small purple dots trailing that workspace's agent dots, and on the agent key as a
purple `⤷N` pill plus a subtitle (`⤷ audit the schema`, or `⤷ 3 subagents`). Only sessions
you can actually sit in front of get a key of their own.

Shortcuts: a workspace with exactly one agent focuses it directly (one press). **Hold** a
workspace key to jump straight to the workspace without drilling in. The agents view
returns to the workspace view on its own after about 25 seconds.

## Colours

| Band | State | Meaning |
|---|---|---|
| 🟢 green | `working` | agent is running — leave it alone |
| 🔵 blue ⇊ | `compacting` | compacting context |
| 🟠 amber ? | `question` | waiting for you to answer a question |
| 🟠 amber ✓ | `waiting` | finished its turn, your move |
| 🟡 gold … | `idle` | alive, but nothing has happened for a while |
| 🔴 red 🔒 | `blocked` | blocked on a permission prompt |
| ⚫️ grey | *(empty)* | cmux workspace with no pi sessions |

## Requirements

- macOS
- An Elgato Stream Deck Mini (the six-key model)
- [pi](https://github.com/earendil-works/pi-coding-agent)
- [cmux](https://cmux.com)
- Python 3
- [Homebrew](https://brew.sh) (the installer uses it to install `hidapi`)

The layout and rendering code assumes six keys. Other Stream Deck models have not yet been
tested.

## Install

```sh
git clone https://github.com/raldred/pi-stream-deck.git
cd pi-stream-deck
scripts/install.sh
```

The installer installs `hidapi` with Homebrew, creates a project-local Python virtual
environment, links the pi extension into `~/.pi/agent/extensions/`, links `pi-deck` into
`~/.local/bin/`, and creates a launch agent so the daemon starts automatically.

To install without the launch agent and run the daemon yourself:

```sh
scripts/install.sh --no-launchd
```

Make sure `~/.local/bin` is on your `PATH`, then check the installation:

```sh
pi-deck doctor    # deck? cmux? any sessions reporting?
pi-deck run -v    # drive the deck in the foreground (if not using launchd)
```

Start a **new** pi session for the extension to load; `/reload` also works in an existing
session. The Stream Deck can only be driven by one app at a time, so quit Elgato's Stream
Deck app (and any other app controlling the device) first.

### Password-protected cmux sockets

If cmux requires `CMUX_SOCKET_PASSWORD`, put only the password in
`~/.pi-deck/cmux-password` before running `scripts/install.sh`:

```sh
mkdir -p ~/.pi-deck
printf '%s' "$CMUX_SOCKET_PASSWORD" > ~/.pi-deck/cmux-password
chmod 600 ~/.pi-deck/cmux-password
scripts/install.sh
```

The generated launch-agent plist is also restricted to your user (`0600`).

## How it works

```text
pi session ──(extension)──► ~/.pi-deck/status/<sessionId>.json ──┐
                                                                 ├─► pideck daemon ──► Stream Deck
cmux ──`cmux tree --all --json`──► workspaces / surfaces ────────┘        │
                                                                key press ▼
                                              `cmux rpc surface.focus` / `workspace.select`
```

- **`extension/pi-deck.ts`** is a pi extension loaded into every session. It writes one
  small JSON file per session (state, label, branch, current activity) and tags it with the
  cmux workspace and surface IDs cmux puts in each terminal's environment
  (`CMUX_WORKSPACE_ID`, `CMUX_SURFACE_ID`). The live cmux topology is authoritative for a
  surface's workspace, so moving an existing terminal does not strand it under
  **elsewhere**. Writes are coalesced, plus a 15-second heartbeat so the daemon can tell a
  live session from a crashed one; `session_shutdown` leaves a tombstone the daemon reaps.
- **`pideck/`** is the Python daemon. `store.py` joins status files onto the live cmux
  topology, `layout.py` turns that into six key specs, `render.py` paints them with Pillow,
  `device.py` talks to the deck and reports short/long presses, `cmux.py` reads topology
  and issues focus RPCs, and `daemon.py` runs the loop.
- Sessions running outside cmux are grouped into a trailing **elsewhere** workspace.

State comes from pi's lifecycle events (`before_agent_start`, `turn_start`,
`tool_execution_start`, `tool_execution_end`, `agent_settled`, `session_before_compact`,
`session_shutdown`), so there is no polling of pi internals and no screen scraping.
`waiting` decays to `idle` after 20 minutes; a dead pid reads as `ended` even if the process
never wrote its tombstone.

Subagent detection needs no cooperation from the subagent extension: the parent stamps its
session id into `PI_DECK_PARENT`, and children inherit it through their environment. Each
headless child reports `role: "subagent"` plus its parent's id. Interactive sessions remain
top-level after `/reload` or session replacement. A headless session without a marker still
counts as a subagent, and one whose parent cannot be found is promoted to a key of its own
rather than vanishing.

All session status and configuration stays on the local machine. The project makes no
network requests.

## Configuration

`~/.pi-deck/config.json` (all optional):

```json
{
  "brightness": 60,
  "poll_interval": 1.0,
  "topology_interval": 3.0,
  "topology_grace": 20.0,
  "agents_view_timeout": 25.0,
  "only_with_agents": false,
  "focus_single_agent_directly": true
}
```

`only_with_agents: true` hides idle cmux workspaces (denser, but key positions move around).

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests -q

pi-deck status                          # joined model as JSON
pi-deck scene                           # key specs for the workspaces view
pi-deck scene agents <workspace-uuid>   # key specs for an agents view
pi-deck selftest                        # paint a demo scene on the device
```

The test suite covers the model, layout, status store, rendering, device protocol, and
daemon topology handling without requiring hardware. `PI_DECK_HOME` relocates the
status/config/log directory, which is useful when testing against fake sessions.

Contributions and bug reports are welcome through GitHub issues and pull requests.

## License

[MIT](LICENSE) © 2026 Rob Aldred
