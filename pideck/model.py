"""Domain model: agent status records, workspaces, and status precedence.

An *agent* is one pi session, running in one cmux surface (terminal tab).
A *workspace* is a cmux workspace, which may hold several agents.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

# Ordered worst-first: the workspace roll-up shows the most attention-hungry
# state among its agents.
STATE_PRIORITY = (
    "blocked",     # blocked on a permission prompt — you must answer
    "question",    # waiting for an answer to an agent-authored question
    "waiting",     # finished its turn, waiting on you
    "idle",        # alive but has done nothing for a while
    "compacting",  # compacting context
    "working",     # busy, leave it alone
    "ended",       # session gone
)
NEEDS_YOU = frozenset({"blocked", "question", "waiting", "idle"})
BUSY = frozenset({"working", "compacting"})

# A "waiting" agent left this long becomes stuck (faster, darker blink).
STUCK_AFTER = 5 * 60
# A "waiting" agent with no activity this long is downgraded to idle.
IDLE_AFTER = 20 * 60
# Records not refreshed within this window with a dead pid are dropped.
STALE_AFTER = 60


def state_rank(state: str) -> int:
    try:
        return STATE_PRIORITY.index(state)
    except ValueError:
        return len(STATE_PRIORITY)


def worst(states) -> str:
    states = list(states)
    if not states:
        return "empty"
    return min(states, key=state_rank)


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@dataclass
class Agent:
    session_id: str
    pid: int | None = None
    state: str = "idle"
    label: str = "?"
    branch: str | None = None
    activity: str | None = None
    cwd: str | None = None
    workspace_id: str | None = None
    surface_id: str | None = None
    updated_at: float = 0.0
    state_since: float = 0.0
    source: str = ""
    role: str = "main"                       # "main" | "subagent"
    parent_session_id: str | None = None
    children: list["Agent"] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict, source: str = "") -> "Agent":
        cmux = data.get("cmux") or {}
        return cls(
            session_id=str(data.get("sessionId") or source),
            pid=data.get("pid"),
            state=str(data.get("state") or "idle"),
            label=str(data.get("label") or "?"),
            branch=data.get("branch"),
            activity=data.get("activity"),
            cwd=data.get("cwd"),
            workspace_id=cmux.get("workspaceId"),
            surface_id=cmux.get("surfaceId"),
            updated_at=float(data.get("updatedAt") or 0.0),
            state_since=float(data.get("stateSince") or data.get("updatedAt") or 0.0),
            source=source,
            role=str(data.get("role") or "main"),
            parent_session_id=data.get("parentSessionId"),
        )

    def live_children(self, now: float | None = None) -> list["Agent"]:
        return [c for c in self.children if c.effective_state(now) != "ended"]

    def effective_state(self, now: float | None = None) -> str:
        """State after time-based decay and liveness checks."""
        now = time.time() if now is None else now
        if self.state == "ended":
            return "ended"
        if self.pid and not pid_alive(self.pid):
            return "ended"
        if self.state == "waiting" and now - self.state_since > IDLE_AFTER:
            return "idle"
        return self.state

    def stuck(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return (self.effective_state(now) in NEEDS_YOU
                and now - self.state_since > STUCK_AFTER)

    def age_seconds(self, now: float | None = None) -> float:
        now = time.time() if now is None else now
        return max(0.0, now - (self.state_since or self.updated_at or now))


@dataclass
class Workspace:
    workspace_id: str
    title: str
    window_id: str | None = None
    index: int = 0
    selected: bool = False
    agents: list[Agent] = field(default_factory=list)

    def state(self, now: float | None = None) -> str:
        return worst(a.effective_state(now) for a in self.live_agents(now))

    def live_agents(self, now: float | None = None) -> list[Agent]:
        return [a for a in self.agents if a.effective_state(now) != "ended"]

    def counts(self, now: float | None = None) -> dict[str, int]:
        out: dict[str, int] = {}
        for a in self.live_agents(now):
            s = a.effective_state(now)
            out[s] = out.get(s, 0) + 1
        return out

    def subagent_count(self, now: float | None = None) -> int:
        return sum(len(a.live_children(now)) for a in self.live_agents(now))

    def needs_you(self, now: float | None = None) -> int:
        return sum(1 for a in self.live_agents(now)
                   if a.effective_state(now) in NEEDS_YOU)

    def stuck(self, now: float | None = None) -> bool:
        return any(a.stuck(now) for a in self.live_agents(now))

    def last_change(self, now: float | None = None) -> float | None:
        stamps = [a.state_since or a.updated_at for a in self.live_agents(now)]
        return max(stamps) if stamps else None


def relative_time(seconds: float) -> str:
    if seconds < 10:
        return "now"
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"
