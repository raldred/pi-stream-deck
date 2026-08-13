#!/usr/bin/env bash
# Installs pi-deck: Pi package, hidapi, Python venv, CLI, and a launchd agent.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
AGENT_DIR="${PI_CODING_AGENT_DIR:-$HOME/.pi/agent}"
DATA_DIR="${PI_DECK_HOME:-$AGENT_DIR/pi-stream-deck}"
EXT_DIR="$AGENT_DIR/extensions"
VERSION="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["version"])' "$ROOT/package.json")"
PACKAGE_SOURCE="git:github.com/raldred/pi-stream-deck@v$VERSION"
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

if ! command -v pi >/dev/null 2>&1; then
  echo "!! Pi is required: https://github.com/earendil-works/pi-coding-agent" >&2
  exit 1
fi
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

echo "==> Pi package $PACKAGE_SOURCE"
pi install "$PACKAGE_SOURCE"
# Remove the pre-release development symlink if this checkout created it.
LEGACY_EXTENSION="$EXT_DIR/pi-deck.ts"
if [[ -L "$LEGACY_EXTENSION" && "$(readlink "$LEGACY_EXTENSION")" == "$ROOT/extension/pi-deck.ts" ]]; then
  rm "$LEGACY_EXTENSION"
fi

echo "==> CLI -> $HOME/.local/bin/pi-deck"
mkdir -p "$HOME/.local/bin"
ln -sf "$ROOT/bin/pi-deck" "$HOME/.local/bin/pi-deck"

mkdir -p "$DATA_DIR/status"
chmod 700 "$DATA_DIR" "$DATA_DIR/status"

if [[ "$INSTALL_LAUNCHD" == true ]]; then
  echo "==> launchd agent $LABEL"
  CMUX_PASSWORD_XML=""
  if [[ -f "$DATA_DIR/cmux-password" ]]; then
    # Escape plist metacharacters so passwords containing &, <, >, or quotes
    # still produce valid XML.
    CMUX_PASSWORD="$(python3 -c 'import html, sys; print(html.escape(sys.stdin.read(), quote=True), end="")' < "$DATA_DIR/cmux-password")"
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
    <key>PI_DECK_HOME</key><string>$DATA_DIR</string>
    $CMUX_PASSWORD_XML
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardErrorPath</key><string>$DATA_DIR/launchd.err.log</string>
  <key>StandardOutPath</key><string>$DATA_DIR/launchd.out.log</string>
</dict>
</plist>
PLISTEOF
  chmod 600 "$PLIST"
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  echo "    loaded — logs in $DATA_DIR/"
fi

echo
echo "Done. Next:"
echo "  pi-deck doctor        # check deck + cmux + reporting sessions"
if [[ "$INSTALL_LAUNCHD" == true ]]; then
  echo "  daemon runs automatically — logs are in $DATA_DIR/"
else
  echo "  pi-deck run -v        # drive the deck in the foreground"
fi
echo "  (start a NEW pi session so the extension loads)"
