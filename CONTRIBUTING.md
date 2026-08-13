# Contributing

Contributions, bug reports, and ideas are welcome. Please open a GitHub issue before a
large change so the approach can be discussed before significant work begins.

## Development setup

pi-stream-deck requires macOS for cmux and physical-device integration, but its automated
test suite runs without a Stream Deck.

```sh
git clone https://github.com/raldred/pi-stream-deck.git
cd pi-stream-deck
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests -q
```

Runtime dependencies are listed in `requirements.txt`; test-only dependencies belong in
`requirements-dev.txt`.

## Useful commands

After running `scripts/install.sh --no-launchd`, these commands are useful while developing:

```sh
pi-deck status                          # joined workspace/agent model as JSON
pi-deck scene                           # key specs for the workspace overview
pi-deck scene agents <workspace-uuid>   # key specs for an agents view
pi-deck selftest                        # paint a demo scene on a connected deck
pi-deck run -v                          # run the daemon with console logging
pi-deck doctor                          # check device, cmux, and session reporting
```

Set `PI_DECK_HOME` to isolate development data from your normal installation:

```sh
export PI_DECK_HOME="$(mktemp -d)"
pi-deck status
```

## Project structure

| Path | Responsibility |
|---|---|
| `extension/pi-deck.ts` | Pi lifecycle extension and session status reporter |
| `pideck/` | Python daemon, model, layout, rendering, and device integration |
| `tests/` | Hardware-free pytest suite |
| `scripts/install.sh` | User installation and launchd setup |
| `assets/` | README preview images |
| `docs/` | User configuration and architecture documentation |

For the runtime architecture and data flow, read [How it works](docs/how-it-works.md).

## Testing

Run the complete suite before submitting a pull request:

```sh
.venv/bin/python -m pytest tests -q
bash -n scripts/install.sh bin/pi-deck
```

The tests cover:

- agent/workspace state and priority
- subagent attachment and roll-up
- cmux topology joining and outage handling
- six-key pagination and input actions
- Pillow rendering
- Stream Deck protocol behaviour with fake devices
- configuration and data-directory resolution

Add or update tests for behavioural changes. Hardware-specific fixes should still include a
unit test around the smallest testable boundary where possible.

## Testing with hardware

Only one application can own a Stream Deck at a time. Quit Elgato's Stream Deck software
and stop the installed launch agent before starting a development daemon:

```sh
launchctl unload ~/Library/LaunchAgents/com.pideck.agent.plist 2>/dev/null || true
pi-deck run -v
```

Restore the normal launchd installation afterwards with:

```sh
scripts/install.sh
```

Use a new Pi session or run `/reload` after changing `extension/pi-deck.ts`.

## Pull requests

Keep pull requests focused and include:

1. A short explanation of the user-visible change.
2. Tests for new or changed behaviour.
3. Documentation updates when configuration, installation, or controls change.
4. Confirmation that the test suite passes.

Please do not include session status files, local configuration, logs, virtual environments,
or credentials. These are already covered by the repository's ignore rules where they can
occur inside the checkout.
