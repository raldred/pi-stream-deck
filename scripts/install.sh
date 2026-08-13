#!/usr/bin/env bash
# Installs pi-deck: hidapi, Python venv, pi extension link, and a launchd agent.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
EXT_DIR="$HOME/.pi/agent/extensions"
PLIST="$HOME/Library/LaunchAgents/com.pideck.agent.plist"
LABEL="com.pideck.agent"
INSTALL_LAUNCHD=true

usage() {
  echo "Usage: scripts/install.sh [--no-launchd]"
  echo "  --no-launchd  install without starting the daemon at login"
}

case "${1:-}" in
  "") ;;
  --no-launchd) INSTALL_LAUNCHD=false ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { usage >&2; exit 2; }

if ! command -v brew >/dev/null 2>&1; then
  echo "!! Homebrew is required: https://brew.sh" >&2
  exit 1
fi
if ! brew --prefix hidapi >/dev/null 2>&1; then
  echo "==> installing hidapi with Homebrew"
  brew install hidapi
fi

echo "==> python venv"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$ROOT/requirements.txt"

echo "==> pi extension -> $EXT_DIR/pi-deck.ts"
mkdir -p "$EXT_DIR"
ln -sf "$ROOT/extension/pi-deck.ts" "$EXT_DIR/pi-deck.ts"

echo "==> CLI -> $HOME/.local/bin/pi-deck"
mkdir -p "$HOME/.local/bin"
ln -sf "$ROOT/bin/pi-deck" "$HOME/.local/bin/pi-deck"

mkdir -p "$HOME/.pi-deck/status"

if [[ "$INSTALL_LAUNCHD" == true ]]; then
  echo "==> launchd agent $LABEL"
  CMUX_PASSWORD_XML=""
  if [[ -f "$HOME/.pi-deck/cmux-password" ]]; then
    # Escape plist metacharacters so passwords containing &, <, >, or quotes
    # still produce valid XML.
    CMUX_PASSWORD="$(python3 -c 'import html, sys; print(html.escape(sys.stdin.read(), quote=True), end="")' < "$HOME/.pi-deck/cmux-password")"
    CMUX_PASSWORD_XML="<key>CMUX_SOCKET_PASSWORD</key><string>$CMUX_PASSWORD</string>"
  fi
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
  <dict>
    <key>HOMEBREW_PREFIX</key><string>$(brew --prefix 2>/dev/null || echo /opt/homebrew)</string>
    $CMUX_PASSWORD_XML
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardErrorPath</key><string>$HOME/.pi-deck/launchd.err.log</string>
  <key>StandardOutPath</key><string>$HOME/.pi-deck/launchd.out.log</string>
</dict>
</plist>
PLISTEOF
  chmod 600 "$PLIST"
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  echo "    loaded — logs in ~/.pi-deck/"
fi

echo
echo "Done. Next:"
echo "  pi-deck doctor        # check deck + cmux + reporting sessions"
if [[ "$INSTALL_LAUNCHD" == true ]]; then
  echo "  daemon runs automatically — logs are in ~/.pi-deck/"
else
  echo "  pi-deck run -v        # drive the deck in the foreground"
fi
echo "  (start a NEW pi session so the extension loads)"
