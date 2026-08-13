# Configuration

pi-stream-deck works without a configuration file. Add one only when you want to change
the display, polling, navigation, or workspace filtering behaviour.

## Configuration file

The default path is:

```text
~/.pi/agent/pi-stream-deck/config.json
```

The directory follows Pi's configured agent directory. The complete resolution order is:

1. `$PI_DECK_HOME/config.json` when `PI_DECK_HOME` is set.
2. `$PI_CODING_AGENT_DIR/pi-stream-deck/config.json` when Pi's agent directory is set.
3. `~/.pi/agent/pi-stream-deck/config.json` otherwise.

The file must contain a JSON object. You only need to include values you want to override:

```json
{
  "brightness": 60,
  "poll_interval": 1.0,
  "topology_interval": 3.0,
  "topology_grace": 20.0,
  "agents_view_timeout": 25.0,
  "only_with_agents": false,
  "focus_single_agent_directly": true,
  "reconnect_interval": 3.0
}
```

## Settings

| Setting | Type | Default | Description |
|---|---:|---:|---|
| `brightness` | integer | `60` | Stream Deck brightness from `0` to `100`. |
| `poll_interval` | seconds | `1.0` | How often the daemon reads session status files and refreshes the scene. Lower values react faster but do more work. |
| `topology_interval` | seconds | `3.0` | How often the daemon asks cmux for its current windows, workspaces, and surfaces. |
| `topology_grace` | seconds | `20.0` | How long the last good cmux topology remains visible during an outage. After this, stale workspaces are removed. |
| `agents_view_timeout` | seconds | `25.0` | Time after the last key press before an agents view returns to the workspace overview. Set to `0` to disable automatic return. |
| `only_with_agents` | boolean | `false` | Hide cmux workspaces that do not contain a reporting Pi session. This creates a denser view, but key positions can move. |
| `focus_single_agent_directly` | boolean | `true` | When a workspace has one agent, pressing it focuses that agent immediately. Set to `false` to always open the agents view first. |
| `reconnect_interval` | seconds | `3.0` | Delay before retrying when the Stream Deck is absent, busy, or disconnected. |

Configuration is read when the daemon starts; it is not hot-reloaded.

### Restart after changing configuration

For the default launchd installation:

```sh
launchctl kickstart -k "gui/$(id -u)/com.pideck.agent"
```

If you used `scripts/install.sh --no-launchd`, stop the foreground daemon with `Ctrl-C`
and run it again:

```sh
pi-deck run -v
```

## Environment variables

| Variable | Purpose |
|---|---|
| `PI_CODING_AGENT_DIR` | Relocates Pi's complete global agent directory. pi-stream-deck stores its data in a `pi-stream-deck/` child directory. |
| `PI_DECK_HOME` | Overrides only pi-stream-deck's config, status, and log directory. It takes precedence over `PI_CODING_AGENT_DIR`. |
| `PI_DECK_CMUX_BIN` | Overrides the path to the `cmux` executable. Normally it is found on `PATH` or inside `/Applications/cmux.app`. |
| `CMUX_SOCKET_PASSWORD` | Password used to communicate with a password-protected cmux socket. See below for launchd setup. |

`PI_DECK_HOME` must resolve to the same directory for both the Pi extension and daemon. The
installer handles this for launchd by writing the resolved path into its plist.

## Password-protected cmux sockets

Launchd does not inherit your interactive shell environment. If cmux uses
`CMUX_SOCKET_PASSWORD`, store only the password in the pi-stream-deck data directory before
installing:

```sh
mkdir -p ~/.pi/agent/pi-stream-deck
printf '%s' "$CMUX_SOCKET_PASSWORD" > ~/.pi/agent/pi-stream-deck/cmux-password
chmod 600 ~/.pi/agent/pi-stream-deck/cmux-password
scripts/install.sh
```

When `PI_CODING_AGENT_DIR` or `PI_DECK_HOME` is set, place `cmux-password` in the resolved
pi-stream-deck data directory instead. The installer XML-escapes the value, writes it into
the launchd environment, and restricts the generated plist to your user (`0600`).

For a foreground daemon, export `CMUX_SOCKET_PASSWORD` normally before running
`pi-deck run`.

## Data and logs

The resolved data directory contains:

```text
pi-stream-deck/
├── config.json
├── cmux-password          # optional
├── status/                # one heartbeat file per Pi session
├── pideck.log             # daemon log
├── launchd.out.log
└── launchd.err.log
```

The installer restricts the data and status directories to your user (`0700`). Session
status files contain local metadata such as the working directory, branch, model, activity,
and cmux surface identifiers; they are not sent over the network.

Use these commands when troubleshooting:

```sh
pi-deck doctor
pi-deck status
pi-deck scene
tail -f ~/.pi/agent/pi-stream-deck/pideck.log
tail -f ~/.pi/agent/pi-stream-deck/launchd.err.log
```

If the config file is invalid JSON, the daemon ignores it, uses defaults, and writes a
warning to `pideck.log`.
