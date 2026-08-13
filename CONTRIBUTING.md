# Contributing

Contributions, bug reports, and ideas are welcome. Open an issue before a large change so
the approach can be discussed first.

## Development setup

```sh
git clone https://github.com/raldred/pi-stream-deck.git
cd pi-stream-deck
npm install
npm test
```

The automated tests do not require a Stream Deck. Runtime dependencies are ordinary npm
packages with prebuilt macOS binaries; no Python or Homebrew libraries are required.

## Project structure

| Path | Responsibility |
|---|---|
| `extension/pi-deck.ts` | Pi lifecycle reporter and `/pi-stream-deck` command |
| `node/core.mjs` | Paths, models, status store, layout, and cmux integration |
| `node/render.mjs` | Canvas-based key rendering |
| `node/device.mjs` | Stream Deck transport, animation, and key presses |
| `node/daemon.mjs` | Daemon loop, diagnostics, and launchd setup |
| `node/tests/` | Hardware-free Node test suite |
| `assets/` | README preview images |
| `docs/` | Configuration and architecture documentation |

See [How it works](docs/how-it-works.md) for the runtime architecture.

## Testing local extension changes

Remove the released package temporarily and load the checkout directly:

```sh
pi remove git:github.com/raldred/pi-stream-deck
pi -e .
```

Use `/reload` after changing `extension/pi-deck.ts`. Restore the release package when you
are done.

## Hardware testing

Only one application can own a Stream Deck at a time. Quit Elgato's software, then load the
local extension and run:

```text
/pi-stream-deck setup
/pi-stream-deck doctor
/pi-stream-deck selftest
```

Remove the development launch agent before deleting or moving the checkout:

```text
/pi-stream-deck uninstall
```

## Pull requests

Before submitting:

```sh
npm test
node --check node/core.mjs
node --check node/render.mjs
node --check node/device.mjs
node --check node/daemon.mjs
```

Keep pull requests focused, add tests for behavioural changes, and update documentation
when configuration, installation, or controls change. Never commit status files, local
configuration, logs, or credentials.
