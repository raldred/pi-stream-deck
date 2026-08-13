# Configuration

pi-stream-deck works without a configuration file. Add one only to change display,
polling, navigation, or workspace filtering behaviour.

## Configuration file

The default path is:

```text
~/.pi/agent/pi-stream-deck/config.json
```

Resolution order:

1. `$PI_DECK_HOME/config.json`
2. `$PI_CODING_AGENT_DIR/pi-stream-deck/config.json`
3. `~/.pi/agent/pi-stream-deck/config.json`

Only include values you want to override:

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

| Setting | Type | Default | Description |
|---|---:|---:|---|
| `brightness` | integer | `60` | Stream Deck brightness from `0` to `100`. |
| `poll_interval` | seconds | `1.0` | Status-file and scene refresh frequency. |
| `topology_interval` | seconds | `3.0` | How often the daemon refreshes cmux topology. |
| `topology_grace` | seconds | `20.0` | How long the last good topology survives a cmux interruption. |
| `agents_view_timeout` | seconds | `25.0` | Delay before returning to the workspace overview; `0` disables it. |
| `only_with_agents` | boolean | `false` | Hide cmux workspaces without a reporting Pi session. |
| `focus_single_agent_directly` | boolean | `true` | Focus a workspace's sole agent without opening the agents view. |
| `reconnect_interval` | seconds | `3.0` | Delay before retrying an absent or disconnected Stream Deck. |

Configuration is read when the daemon starts. Restart it after editing:

```text
/pi-stream-deck setup
```

## Pi commands

```text
/pi-stream-deck setup       install or refresh launchd and start the daemon
/pi-stream-deck doctor      check package, daemon, deck, cmux, and reporters
/pi-stream-deck status      show the joined workspace and agent model
/pi-stream-deck selftest    paint a demonstration scene for eight seconds
/pi-stream-deck uninstall   stop the daemon and remove its launchd service
```

`uninstall` removes the service but leaves configuration and status data intact. Remove the
Pi package separately with `pi remove git:github.com/raldred/pi-stream-deck` when desired.

## Environment variables

| Variable | Purpose |
|---|---|
| `PI_CODING_AGENT_DIR` | Relocates Pi's global agent directory. |
| `PI_DECK_HOME` | Overrides only pi-stream-deck's config, status, and logs. |
| `PI_DECK_CMUX_BIN` | Overrides the path to the cmux executable. |
| `CMUX_SOCKET_PASSWORD` | Password for a protected cmux socket. |

`PI_DECK_HOME` must resolve to the same directory for the extension and daemon. The setup
command writes the resolved path into the launchd plist.

## Password-protected cmux sockets

Launchd does not inherit your shell environment. Save the password before setup:

```sh
mkdir -p ~/.pi/agent/pi-stream-deck
printf '%s' "$CMUX_SOCKET_PASSWORD" > ~/.pi/agent/pi-stream-deck/cmux-password
chmod 600 ~/.pi/agent/pi-stream-deck/cmux-password
```

Then run `/pi-stream-deck setup`. When `PI_CODING_AGENT_DIR` or `PI_DECK_HOME` is set, put
`cmux-password` in the resolved data directory instead.

## Data and logs

```text
pi-stream-deck/
├── config.json
├── cmux-password          # optional
├── daemon.pid
├── status/                # one heartbeat file per Pi session
├── pideck.log
├── launchd.out.log
└── launchd.err.log
```

Status files contain local metadata such as working directory, branch, model, activity,
and cmux surface identifiers. Nothing is sent over the network.

Troubleshooting starts with:

```text
/pi-stream-deck doctor
/pi-stream-deck status
```

For daemon errors, inspect `~/.pi/agent/pi-stream-deck/pideck.log` and
`launchd.err.log`. Invalid JSON configuration is ignored and defaults are used.
