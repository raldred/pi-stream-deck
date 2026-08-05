# pi-deck

Turns a Stream Deck Mini into a live status board for the [pi](https://github.com/earendil-works/pi-coding-agent)
agents running in your [cmux](https://cmux.com) workspaces — and a remote control for them.

**Top level: your cmux workspaces.** One key per workspace, in sidebar order, so key
positions match what you already see. Each key shows the workspace title, a coloured band
for the most attention-hungry agent in it, one dot per pi session, an `Nπ` badge, and how
long since anything changed. A pulsing amber/red key means an agent in there is waiting on
you; the pulse gets faster and darker the longer you ignore it.

**Press a workspace → its agents.** One key per pi session in that workspace: repo (or
session name), what it's doing right now (`bash: bundle exec rspec`), state, and age. The
bottom-right key goes back.

**Press an agent → you're there.** cmux is brought to the front with that workspace
selected and that terminal surface focused.

**Subagents don't get their own key.** A headless `pi -p` child spawned by a session shows
up as small purple dots trailing that workspace's agent dots, and on the agent key as a
purple `⤷N` pill plus a subtitle (`⤷ audit the schema`, or `⤷ 3 subagents`). Only sessions
you can actually sit in front of get a key of their own.

Shortcuts: a workspace with exactly one agent focuses it directly (one press). **Hold** a
workspace key to jump straight to the workspace without drilling in. The agents view
returns to the workspace view on its own after ~25s.

## Colours

| Band | State | Meaning |
|---|---|---|
| 🟢 green | `working` | agent is running — leave it alone |
| 🔵 blue ⇊ | `compacting` | compacting context |
| 🟠 amber ✓ | `waiting` | finished its turn, your move |
| 🟡 gold … | `idle` | alive, but nothing has happened for a while |
| 🔴 red 🔒 | `blocked` | blocked on a prompt |
| ⚫️ grey | *(empty)* | cmux workspace with no pi sessions |

## Install

Requires macOS, a Stream Deck Mini, cmux, `python3`, and `brew install hidapi`.

```sh
scripts/install.sh              # venv + extension link + `pi-deck` on PATH
scripts/install.sh --launchd    # …and run the daemon at login
```

Then:

```sh
pi-deck doctor    # deck? cmux? any sessions reporting?
pi-deck run -v    # drive the deck in the foreground
```

Start a **new** pi session for the extension to load (`/reload` works in an existing one).
The Stream Deck can only be driven by one app at a time — quit Elgato's Stream Deck app
(and Claude Deck Mini, if you run it) first.

## How it works

```
pi session ──(extension)──► ~/.pi-deck/status/<sessionId>.json ──┐
                                                                 ├─► pideck daemon ──► Stream Deck
cmux ──`cmux tree --all --json`──► workspaces / surfaces ────────┘        │
                                                                key press ▼
                                              `cmux rpc surface.focus` / `workspace.select`
```

- **`extension/pi-deck.ts`** — a pi extension loaded into every session. It writes one
  small JSON file per session (state, label, branch, current activity) and tags it with the
  cmux workspace and surface IDs cmux puts in each terminal's environment
  (`CMUX_WORKSPACE_ID`, `CMUX_SURFACE_ID`). Writes are coalesced, plus a 15s heartbeat so
  the daemon can tell a live session from a crashed one; `session_shutdown` leaves a
  tombstone the daemon reaps.
- **`pideck/`** — the daemon. `store.py` joins status files onto the live cmux topology,
  `layout.py` turns that into 6 key specs (pure, fully unit-tested), `render.py` paints
  them with Pillow, `device.py` talks to the deck and reports short/long presses,
  `cmux.py` reads topology and issues focus RPCs, `daemon.py` is the loop.
- Sessions running outside cmux aren't lost: they're grouped into a trailing
  **elsewhere** workspace.

State comes from pi's own lifecycle events (`before_agent_start`, `turn_start`,
`tool_execution_start`, `agent_settled`, `session_before_compact`, `session_shutdown`), so
there's no polling of pi internals and no screen scraping. `waiting` decays to `idle` after
20 minutes; a dead pid reads as `ended` even if the process never got to write its
tombstone.

Subagent detection needs no cooperation from the subagent extension: the parent stamps its
session id into `PI_DECK_PARENT`, and because children are `spawn`ed with an inherited
environment, each child sees it and reports `role: "subagent"` plus its parent's id. A
headless session (`ctx.hasUI === false`) counts as a subagent even without the marker, and
one whose parent can't be found is promoted to a key of its own rather than vanishing.

## Config

`~/.pi-deck/config.json` (all optional):

```json
{
  "brightness": 60,
  "poll_interval": 1.0,
  "topology_interval": 3.0,
  "agents_view_timeout": 25.0,
  "only_with_agents": false,
  "focus_single_agent_directly": true
}
```

`only_with_agents: true` hides idle cmux workspaces (denser, but key positions move around).

## Develop

```sh
.venv/bin/python -m pytest tests -q     # model, layout, store, render — no hardware
pi-deck status                          # the joined model as JSON
pi-deck scene                           # the key specs for the workspaces view
pi-deck scene agents <workspace-uuid>   # …for an agents view
pi-deck selftest                        # paint a demo scene on the device
```

`PI_DECK_HOME` relocates the status/config/log directory (handy for testing against a fake
set of sessions).
