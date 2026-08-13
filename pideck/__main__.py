"""pi-deck CLI.

    pideck run [-v]        drive the deck (default)
    pideck status          print the workspace/agent model as JSON
    pideck scene           print the key specs the deck would show
    pideck selftest        paint a demo scene for a few seconds
    pideck doctor          check deck, cmux, and extension wiring
"""

from __future__ import annotations

import json
import sys
import time

from . import cmux, daemon, paths, store
from .device import Deck, NoDeviceError, enumerate_decks
from .layout import View, build


def _status_payload() -> dict:
    now = time.time()
    workspaces = store.snapshot()
    return {
        "workspaces": [
            {
                "id": w.workspace_id,
                "title": w.title,
                "selected": w.selected,
                "state": w.state(now),
                "needsYou": w.needs_you(now),
                "agents": [
                    {
                        "sessionId": a.session_id,
                        "label": a.label,
                        "state": a.effective_state(now),
                        "activity": a.activity,
                        "branch": a.branch,
                        "surfaceId": a.surface_id,
                        "pid": a.pid,
                        "ageSeconds": round(a.age_seconds(now)),
                        "stuck": a.stuck(now),
                    }
                    for a in w.agents
                ],
            }
            for w in workspaces
        ],
    }


def cmd_status() -> int:
    print(json.dumps(_status_payload(), indent=2))
    return 0


def cmd_scene(mode: str | None = None, workspace_id: str | None = None) -> int:
    view = View(mode=mode or "workspaces", workspace_id=workspace_id)
    keys, _ = build(store.snapshot(), view)
    print(json.dumps([{"index": i, **k.spec, "action": k.action}
                      for i, k in enumerate(keys)], indent=2))
    return 0


def cmd_selftest(seconds: float = 8.0) -> int:
    demo = [
        {"kind": "workspace", "title": "Pi Agent", "status": "waiting",
         "dots": ["working", "waiting", "idle"], "count": 3, "age": "2m",
         "selected": True, "stuck": False},
        {"kind": "workspace", "title": "foundations api", "status": "working",
         "dots": ["working"], "count": 1, "age": "now"},
        {"kind": "workspace", "title": "porch", "status": "blocked",
         "dots": ["blocked", "working"], "count": 2, "age": "7m", "stuck": True},
        {"kind": "workspace", "title": "~", "status": "empty", "dots": [], "count": 0},
        {"kind": "agent", "title": "my-project", "subtitle": "bash: pytest",
         "status": "working", "age": "now"},
        {"kind": "back", "title": "Pi Agent"},
    ]
    try:
        deck = Deck(brightness=70).open()
    except NoDeviceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    deck.set_scene(demo)
    deck.start_frames()
    time.sleep(seconds)
    deck.close()
    return 0


def cmd_doctor() -> int:
    ok = True
    decks = enumerate_decks()
    if decks:
        d = decks[0]
        d.open()
        print(f"deck      ok    {d.deck_type()} ({d.key_count()} keys)")
        d.close()
    else:
        ok = False
        print("deck      FAIL  no Stream Deck found (is another app holding it?)")

    if cmux.available():
        topo = cmux.topology()
        print(f"cmux      ok    {len(topo.workspaces)} workspaces, "
              f"{len(topo.surfaces)} surfaces")
    else:
        ok = False
        print(f"cmux      FAIL  cannot talk to cmux ({cmux.CMUX_BIN})")

    agents = store.read_agents()
    directory = paths.status_dir()
    if agents:
        print(f"agents    ok    {len(agents)} reporting in {directory}")
    else:
        print(f"agents    warn  none reporting in {directory} — "
              "is the pi extension installed and a pi session running?")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    verbose = "-v" in argv or "--verbose" in argv
    argv = [a for a in argv if a not in ("-v", "--verbose")]
    command = argv[0] if argv else "run"
    if command in ("run", "daemon"):
        return daemon.main(verbose=verbose)
    if command == "status":
        return cmd_status()
    if command == "scene":
        return cmd_scene(*argv[1:3])
    if command == "selftest":
        return cmd_selftest(float(argv[1]) if len(argv) > 1 else 8.0)
    if command == "doctor":
        return cmd_doctor()
    print(__doc__)
    return 2 if command not in ("-h", "--help", "help") else 0


if __name__ == "__main__":
    sys.exit(main())
