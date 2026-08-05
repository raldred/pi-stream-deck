"""Reads the per-session status files written by the pi-deck pi extension and
joins them onto the live cmux topology.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import cmux, paths
from .model import Agent, Workspace, pid_alive, STALE_AFTER


def read_agents(status_dir: Path | None = None, now: float | None = None) -> list[Agent]:
    now = time.time() if now is None else now
    directory = status_dir or paths.status_dir()
    agents: list[Agent] = []
    if not directory.is_dir():
        return agents
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        agent = Agent.from_json(data, source=str(path))
        stale = now - (agent.updated_at or 0) > STALE_AFTER
        if agent.state == "ended" or (stale and not pid_alive(agent.pid)):
            _reap(path, agent, now)
            continue
        agents.append(agent)
    return agents


def _reap(path: Path, agent: Agent, now: float) -> None:
    """Delete tombstones once they're old enough to have been seen."""
    if now - (agent.updated_at or 0) > STALE_AFTER:
        try:
            path.unlink()
        except OSError:
            pass


def build_workspaces(topology: cmux.Topology, agents: list[Agent],
                     only_with_agents: bool = False) -> list[Workspace]:
    """cmux workspaces in sidebar order, each carrying its pi agents.

    Agents whose workspace is unknown to cmux (e.g. run outside cmux) are
    collected into a synthetic trailing workspace so they're never invisible.
    """
    by_workspace: dict[str, list[Agent]] = {}
    for agent in agents:
        by_workspace.setdefault(agent.workspace_id or "", []).append(agent)

    workspaces: list[Workspace] = []
    for index, ws in enumerate(topology.workspaces):
        mine = by_workspace.pop(ws["id"], [])
        if only_with_agents and not mine:
            continue
        workspaces.append(Workspace(
            workspace_id=ws["id"],
            title=ws["title"],
            window_id=ws["window_id"],
            index=index,
            selected=ws["selected"],
            agents=_order_agents(mine, topology, ws["id"]),
        ))

    orphans = [a for group in by_workspace.values() for a in group]
    if orphans:
        workspaces.append(Workspace(
            workspace_id="__orphans__",
            title="elsewhere",
            index=len(workspaces),
            agents=sorted(orphans, key=lambda a: a.label),
        ))
    return workspaces


def _order_agents(agents: list[Agent], topology: cmux.Topology,
                  workspace_id: str) -> list[Agent]:
    """Keep agents in the tab order cmux shows, so key order matches the UI."""
    ws = topology.workspace(workspace_id) or {}
    order = {s["id"]: i for i, s in enumerate(ws.get("surfaces") or [])}
    return sorted(agents, key=lambda a: (order.get(a.surface_id, 999), a.label))


def snapshot(only_with_agents: bool = False) -> list[Workspace]:
    return build_workspaces(cmux.topology(), read_agents(),
                            only_with_agents=only_with_agents)
