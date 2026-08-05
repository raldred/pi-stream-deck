"""Layout + model tests (no hardware needed): python3 -m pytest tests/ -q"""

from __future__ import annotations

import time

from pideck.layout import View, build, paginate
from pideck.model import Agent, Workspace, worst

NOW = 1_700_000_000.0


def agent(state="working", surface="s1", label="repo", since=NOW, pid=None):
    return Agent(session_id=f"sess-{surface}", pid=pid, state=state, label=label,
                 surface_id=surface, updated_at=since, state_since=since)


def workspace(title="ws", agents=None, wid=None, index=0, selected=False):
    return Workspace(workspace_id=wid or f"w-{title}", title=title, window_id="win",
                     index=index, selected=selected, agents=list(agents or []))


# MARK: - model

def test_worst_prefers_attention_states():
    assert worst(["working", "waiting", "compacting"]) == "waiting"
    assert worst(["working", "blocked", "waiting"]) == "blocked"
    assert worst([]) == "empty"


def test_waiting_decays_to_idle():
    a = agent(state="waiting", since=NOW - 3600)
    assert a.effective_state(NOW) == "idle"
    assert a.stuck(NOW)


def test_dead_pid_reads_as_ended():
    a = agent(pid=999_999_999)
    assert a.effective_state(NOW) == "ended"


def test_workspace_rollup_counts():
    ws = workspace(agents=[agent("working"), agent("waiting", "s2"), agent("waiting", "s3")])
    assert ws.state(NOW) == "waiting"
    assert ws.needs_you(NOW) == 2
    assert ws.counts(NOW) == {"working": 1, "waiting": 2}


# MARK: - pagination

def test_paginate_wraps():
    items = list(range(11))
    visible, page, pages, remaining = paginate(items, 5, 0)
    assert visible == [0, 1, 2, 3, 4] and pages == 3 and remaining == 6
    visible, page, _, _ = paginate(items, 5, 3)          # wraps back to page 0
    assert page == 0 and visible[0] == 0


# MARK: - workspaces view

def test_workspaces_view_fills_all_keys_when_it_fits():
    workspaces = [workspace(title=f"w{i}", agents=[agent()]) for i in range(6)]
    keys, view = build(workspaces, View(), key_count=6, now=NOW)
    assert view.mode == "workspaces"
    assert [k.spec["kind"] for k in keys] == ["workspace"] * 6
    assert all(k.action["type"] == "drill" for k in keys)


def test_workspaces_view_reserves_a_pager_when_overflowing():
    workspaces = [workspace(title=f"w{i}", agents=[agent()]) for i in range(8)]
    keys, _ = build(workspaces, View(), key_count=6, now=NOW)
    assert [k.spec["kind"] for k in keys[:5]] == ["workspace"] * 5
    assert keys[5].spec["kind"] == "more"
    assert keys[5].action == {"type": "page", "page": 1}


def test_workspace_key_shows_dots_and_rollup():
    ws = workspace(agents=[agent("working"), agent("waiting", "s2")])
    keys, _ = build([ws], View(), key_count=6, now=NOW)
    spec = keys[0].spec
    assert spec["status"] == "waiting"
    assert spec["dots"] == ["working", "waiting"]
    assert spec["count"] == 2


def test_empty_workspace_renders_grey_with_no_agents():
    keys, _ = build([workspace()], View(), key_count=6, now=NOW)
    assert keys[0].spec["status"] == "empty"
    assert keys[0].spec["dots"] == []


def test_no_workspaces_shows_a_message():
    keys, _ = build([], View(), key_count=6, now=NOW)
    assert keys[0].spec == {"kind": "message", "text": "no cmux"}


# MARK: - agents view

def test_agents_view_lists_agents_with_back_key():
    ws = workspace(agents=[agent("working", "s1"), agent("waiting", "s2")])
    keys, view = build([ws], View(mode="agents", workspace_id=ws.workspace_id),
                       key_count=6, now=NOW)
    assert view.mode == "agents"
    assert [k.spec["kind"] for k in keys] == ["agent", "agent", "blank", "blank",
                                              "blank", "back"]
    assert keys[0].action["type"] == "focus_agent"
    assert keys[0].action["surfaceId"] == "s1"
    assert keys[5].action == {"type": "back"}


def test_agents_view_pages_when_more_than_four_and_keeps_back():
    ws = workspace(agents=[agent(surface=f"s{i}") for i in range(7)])
    keys, _ = build([ws], View(mode="agents", workspace_id=ws.workspace_id),
                    key_count=6, now=NOW)
    assert [k.spec["kind"] for k in keys] == ["agent"] * 4 + ["more", "back"]
    assert keys[4].action == {"type": "page", "page": 1}


def test_agents_view_falls_back_when_workspace_disappears():
    keys, view = build([workspace(title="other")],
                       View(mode="agents", workspace_id="gone"), key_count=6, now=NOW)
    assert view.mode == "workspaces"
    assert keys[0].spec["title"] == "other"


def test_agent_key_shows_activity_and_age():
    a = agent("working", since=NOW - 90)
    a.activity = "bash: rspec"
    keys, _ = build([workspace(agents=[a])],
                    View(mode="agents", workspace_id="w-ws"), key_count=6, now=NOW)
    assert keys[0].spec["subtitle"] == "bash: rspec"
    assert keys[0].spec["age"] == "1m"


# MARK: - subagents

def sub(parent=None, surface="s1", label="task", state="working"):
    a = agent(state=state, surface=surface, label=label)
    a.role = "subagent"
    a.parent_session_id = parent
    return a


def test_subagents_do_not_take_their_own_key():
    from pideck.store import attach_subagents
    main = agent("working", "s1", "residently")
    agents = attach_subagents([main, sub(main.session_id), sub(main.session_id)])
    assert [a.session_id for a in agents] == [main.session_id]
    keys, _ = build([workspace(agents=agents)],
                    View(mode="agents", workspace_id="w-ws"), key_count=6, now=NOW)
    assert [k.spec["kind"] for k in keys[:2]] == ["agent", "blank"]
    assert keys[0].spec["subagents"] == 2
    assert keys[0].spec["subtitle"] == "⤷ 2 subagents"


def test_single_subagent_is_named_on_the_parent_key():
    from pideck.store import attach_subagents
    main = agent("working", "s1", "residently")
    agents = attach_subagents([main, sub(main.session_id, label="audit the schema")])
    keys, _ = build([workspace(agents=agents)],
                    View(mode="agents", workspace_id="w-ws"), key_count=6, now=NOW)
    assert keys[0].spec["subtitle"] == "⤷ audit the schema"


def test_subagents_are_matched_by_surface_when_parent_id_is_missing():
    from pideck.store import attach_subagents
    main = agent("working", "s1", "residently")
    agents = attach_subagents([main, sub(None, surface="s1")])
    assert len(agents) == 1 and len(main.children) == 1


def test_orphan_subagent_is_promoted_so_it_stays_visible():
    from pideck.store import attach_subagents
    orphan = sub("nobody", surface="s9", label="stray run")
    agents = attach_subagents([orphan])
    assert [a.session_id for a in agents] == [orphan.session_id]


def test_workspace_key_counts_subagents_separately():
    from pideck.store import attach_subagents
    main = agent("working", "s1")
    agents = attach_subagents([main, sub(main.session_id), sub(main.session_id)])
    keys, _ = build([workspace(agents=agents)], View(), key_count=6, now=NOW)
    assert keys[0].spec["count"] == 1
    assert keys[0].spec["dots"] == ["working"]
    assert keys[0].spec["subagents"] == 2


def test_dead_subagents_stop_counting():
    from pideck.store import attach_subagents
    main = agent("working", "s1")
    dead = sub(main.session_id)
    dead.pid = 999_999_999
    agents = attach_subagents([main, dead, sub(main.session_id)])
    keys, _ = build([workspace(agents=agents)], View(), key_count=6, now=NOW)
    assert keys[0].spec["subagents"] == 1
