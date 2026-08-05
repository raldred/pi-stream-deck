"""Turns the workspace/agent model into a 6-key Stream Deck scene.

Two views:

  workspaces  one key per cmux workspace: status band = worst agent state,
              a dot per agent, and an "Nπ" badge. Press drills in, long press
              focuses the workspace itself.
  agents      one key per pi session inside the chosen workspace. Press focuses
              that cmux workspace + surface. Last key goes back.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace

from .model import Workspace, relative_time


@dataclass(frozen=True)
class View:
    mode: str = "workspaces"          # "workspaces" | "agents"
    workspace_id: str | None = None
    page: int = 0

    def with_page(self, page: int) -> "View":
        return replace(self, page=page)


@dataclass(frozen=True)
class Key:
    spec: dict
    action: dict | None = None


def paginate(items: list, slots: int, page: int):
    """Return (visible, page, pages, remaining_after) for a 0-based page."""
    if slots <= 0:
        return [], 0, 1, len(items)
    pages = max(1, -(-len(items) // slots))
    page = page % pages
    start = page * slots
    visible = items[start:start + slots]
    remaining = len(items) - (start + len(visible))
    return visible, page, pages, remaining


def build(workspaces: list[Workspace], view: View, key_count: int = 6,
          now: float | None = None) -> tuple[list[Key], View]:
    """Build the scene for `view`; returns keys plus a possibly-corrected view."""
    now = time.time() if now is None else now
    if view.mode == "agents":
        workspace = next((w for w in workspaces if w.workspace_id == view.workspace_id),
                         None)
        if workspace is None:                      # workspace vanished — bounce out
            view = View()
        else:
            return _agents_scene(workspace, view, key_count, now)
    return _workspaces_scene(workspaces, view, key_count, now)


def _blank_keys(key_count: int) -> list[Key]:
    return [Key({"kind": "blank"}) for _ in range(key_count)]


def _workspaces_scene(workspaces: list[Workspace], view: View, key_count: int,
                      now: float) -> tuple[list[Key], View]:
    view = View(mode="workspaces", page=view.page)
    if not workspaces:
        keys = _blank_keys(key_count)
        keys[0] = Key({"kind": "message", "text": "no cmux"})
        return keys, view

    needs_pager = len(workspaces) > key_count
    slots = key_count - 1 if needs_pager else key_count
    visible, page, pages, remaining = paginate(workspaces, slots, view.page)
    view = view.with_page(page)

    keys = _blank_keys(key_count)
    for i, workspace in enumerate(visible):
        keys[i] = Key(_workspace_spec(workspace, now), {
            "type": "drill",
            "workspaceId": workspace.workspace_id,
            "windowId": workspace.window_id,
        })
    if needs_pager:
        keys[key_count - 1] = Key(
            {"kind": "more", "remaining": remaining if remaining > 0 else len(workspaces) - len(visible)},
            {"type": "page", "page": (page + 1) % pages})
    return keys, view


def _workspace_spec(workspace: Workspace, now: float) -> dict:
    agents = workspace.live_agents(now)
    last = workspace.last_change(now)
    return {
        "kind": "workspace",
        "title": workspace.title,
        "status": workspace.state(now),
        "dots": [a.effective_state(now) for a in agents],
        "count": len(agents),
        "subagents": workspace.subagent_count(now),
        "age": relative_time(now - last) if last else None,
        "selected": workspace.selected,
        "stuck": workspace.stuck(now),
    }


def _agents_scene(workspace: Workspace, view: View, key_count: int,
                  now: float) -> tuple[list[Key], View]:
    agents = workspace.live_agents(now)
    back_index = key_count - 1
    available = key_count - 1
    needs_pager = len(agents) > available
    slots = available - 1 if needs_pager else available
    visible, page, pages, remaining = paginate(agents, slots, view.page)
    view = View(mode="agents", workspace_id=workspace.workspace_id, page=page)

    keys = _blank_keys(key_count)
    for i, agent in enumerate(visible):
        keys[i] = Key(_agent_spec(agent, now), {
            "type": "focus_agent",
            "surfaceId": agent.surface_id,
            "workspaceId": workspace.workspace_id,
            "windowId": workspace.window_id,
            "sessionId": agent.session_id,
        })
    if not agents:
        keys[0] = Key({"kind": "message", "text": "no agents"})
    if needs_pager:
        keys[slots] = Key({"kind": "more", "remaining": max(remaining, 0)},
                          {"type": "page", "page": (page + 1) % pages})
    keys[back_index] = Key({"kind": "back", "title": workspace.title},
                           {"type": "back"})
    return keys, view


def _agent_spec(agent, now: float) -> dict:
    state = agent.effective_state(now)
    children = agent.live_children(now)
    return {
        "kind": "agent",
        "title": agent.label,
        "subtitle": _agent_subtitle(agent, children),
        "status": state,
        "subagents": len(children),
        "age": relative_time(agent.age_seconds(now)),
        "stuck": agent.stuck(now),
    }


def _agent_subtitle(agent, children: list) -> str | None:
    """Subagents are what the session is really doing, so they win the line."""
    if children:
        if len(children) == 1:
            return f"⤷ {children[0].label}"
        return f"⤷ {len(children)} subagents"
    return agent.activity or agent.branch
