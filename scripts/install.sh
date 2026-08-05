#!/usr/bin/env bash
# Installs pi-deck: python venv, pi extension link, and (optionally) a launchd agent.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
EXT_DIR="$HOME/.pi/agent/extensions"
PLIST="$HOME/Library/LaunchAgents/com.pideck.agent.plist"
LABEL="com.pideck.agent"

echo "==> python venv"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$ROOT/requirements.txt"

if ! brew --prefix hidapi >/dev/null 2>&1; then
  echo "!! hidapi not found — run: brew install hidapi" >&2
fi

echo "==> pi extension -> $EXT_DIR/pi-deck.ts"
mkdir -p "$EXT_DIR"
ln -sf "$ROOT/extension/pi-deck.ts" "$EXT_DIR/pi-deck.ts"

echo "==> CLI -> $HOME/.local/bin/pi-deck"
mkdir -p "$HOME/.local/bin"
ln -sf "$ROOT/bin/pi-deck" "$HOME/.local/bin/pi-deck"

mkdir -p "$HOME/.pi-deck/status"

if [[ "${1:-}" == "--launchd" ]]; then
  echo "==> launchd agent $LABEL"
  cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$VENV/bin/python</string>
    <string>-m</string><string>pideck</string><string>run</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>EnvironmentVariables</key>
  <dict><key>HOMEBREW_PREFIX</key><string>$(brew --prefix 2>/dev/null || echo /opt/homebrew)</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardErrorPath</key><string>$HOME/.pi-deck/launchd.err.log</string>
  <key>StandardOutPath</key><string>$HOME/.pi-deck/launchd.out.log</string>
</dict>
</plist>
PLISTEOF
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  echo "    loaded — logs in ~/.pi-deck/"
fi

echo
echo "Done. Next:"
echo "  pi-deck doctor        # check deck + cmux + reporting sessions"
echo "  pi-deck run -v        # drive the deck in the foreground"
echo "  (start a NEW pi session so the extension loads)"
