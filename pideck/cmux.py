"""Thin wrapper around the `cmux` CLI: read topology, focus things.

Topology comes from `cmux tree --all --json --id-format both`, which returns
windows -> workspaces -> panes -> surfaces with stable UUIDs. Focusing uses the
socket RPCs (`window.focus`, `workspace.select`, `surface.focus`).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

CMUX_BIN = os.environ.get("PI_DECK_CMUX_BIN") or shutil.which("cmux") \
    or "/Applications/cmux.app/Contents/Resources/bin/cmux"
BUNDLE_ID = "com.cmuxterm.app"


class CmuxError(RuntimeError):
    pass


def _run(args: list[str], timeout: float = 5.0) -> str:
    env = dict(os.environ, CMUX_QUIET="1")
    try:
        proc = subprocess.run([CMUX_BIN, *args], capture_output=True, text=True,
                              timeout=timeout, env=env)
    except FileNotFoundError as exc:
        raise CmuxError(f"cmux CLI not found at {CMUX_BIN}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CmuxError(f"cmux {' '.join(args)} timed out") from exc
    if proc.returncode != 0:
        raise CmuxError((proc.stderr or proc.stdout or "cmux failed").strip())
    return proc.stdout


def available() -> bool:
    try:
        _run(["ping"], timeout=2.0)
        return True
    except CmuxError:
        return False


def tree() -> dict:
    return json.loads(_run(["tree", "--all", "--json", "--id-format", "both"]))


def rpc(method: str, params: dict) -> dict:
    out = _run(["rpc", method, json.dumps(params)])
    return json.loads(out) if out.strip() else {}


# MARK: - topology

class Topology:
    """Flattened view of the cmux tree, keyed by UUID."""

    def __init__(self, data: dict):
        self.raw = data
        self.workspaces: list[dict] = []
        self.surfaces: dict[str, dict] = {}
        for window in data.get("windows") or []:
            wid = window.get("id")
            for ws in window.get("workspaces") or []:
                surfaces = []
                for pane in ws.get("panes") or []:
                    for surface in pane.get("surfaces") or []:
                        record = {
                            "id": surface.get("id"),
                            "title": surface.get("title"),
                            "type": surface.get("type"),
                            "tty": surface.get("tty"),
                            "workspace_id": ws.get("id"),
                            "window_id": wid,
                            "pane_id": pane.get("id"),
                        }
                        surfaces.append(record)
                        if record["id"]:
                            self.surfaces[record["id"]] = record
                self.workspaces.append({
                    "id": ws.get("id"),
                    "title": ws.get("title") or "workspace",
                    "index": ws.get("index", 0),
                    "selected": bool(ws.get("selected")),
                    "window_id": wid,
                    "surfaces": surfaces,
                })

    def workspace(self, workspace_id: str) -> dict | None:
        return next((w for w in self.workspaces if w["id"] == workspace_id), None)

    def window_of_workspace(self, workspace_id: str) -> str | None:
        ws = self.workspace(workspace_id)
        return ws["window_id"] if ws else None


def topology() -> Topology:
    return Topology(tree())


# MARK: - actions

def activate_app() -> None:
    subprocess.run(["open", "-b", BUNDLE_ID], capture_output=True)


def focus_workspace(workspace_id: str, window_id: str | None = None) -> None:
    if window_id:
        try:
            rpc("window.focus", {"window_id": window_id})
        except CmuxError:
            pass
    rpc("workspace.select", {"workspace_id": workspace_id})
    activate_app()


def focus_surface(surface_id: str, workspace_id: str | None = None,
                  window_id: str | None = None) -> None:
    if window_id:
        try:
            rpc("window.focus", {"window_id": window_id})
        except CmuxError:
            pass
    if workspace_id:
        try:
            rpc("workspace.select", {"workspace_id": workspace_id})
        except CmuxError:
            pass
    rpc("surface.focus", {"surface_id": surface_id})
    activate_app()
