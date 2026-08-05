"""Store + render tests: status file parsing, cmux joining, headless painting."""

from __future__ import annotations

import json
import os

from pideck import cmux, render, store

TREE = {
    "windows": [
        {
            "id": "WIN1",
            "workspaces": [
                {
                    "id": "WSA", "title": "Pi Agent", "index": 0, "selected": True,
                    "panes": [{
                        "id": "P1",
                        "surfaces": [
                            {"id": "S1", "title": "π - residently", "type": "terminal"},
                            {"id": "S2", "title": "π - porch", "type": "terminal"},
                        ],
                    }],
                },
                {
                    "id": "WSB", "title": "~", "index": 1, "selected": False,
                    "panes": [{"id": "P2", "surfaces": [
                        {"id": "S3", "title": "~", "type": "terminal"}]}],
                },
            ],
        }
    ]
}


def write_status(tmp_path, session_id, **overrides):
    payload = {
        "v": 1, "sessionId": session_id, "pid": os.getpid(), "state": "working",
        "label": session_id, "cwd": "/tmp", "updatedAt": 1e9, "stateSince": 1e9,
        "cmux": {"workspaceId": "WSA", "surfaceId": "S1"},
    }
    payload.update(overrides)
    (tmp_path / f"{session_id}.json").write_text(json.dumps(payload))
    return payload


def test_topology_flattens_windows_workspaces_surfaces():
    topo = cmux.Topology(TREE)
    assert [w["title"] for w in topo.workspaces] == ["Pi Agent", "~"]
    assert topo.window_of_workspace("WSB") == "WIN1"
    assert topo.surfaces["S2"]["workspace_id"] == "WSA"


def test_read_agents_skips_ended_and_stale(tmp_path):
    write_status(tmp_path, "alive")
    write_status(tmp_path, "dead", state="ended")
    write_status(tmp_path, "stale", pid=999_999_999, updatedAt=1.0, stateSince=1.0)
    (tmp_path / "junk.json").write_text("not json")
    agents = store.read_agents(tmp_path, now=1e9)
    assert [a.session_id for a in agents] == ["alive"]


def test_build_workspaces_joins_agents_in_tab_order(tmp_path):
    write_status(tmp_path, "second", cmux={"workspaceId": "WSA", "surfaceId": "S2"})
    write_status(tmp_path, "first", cmux={"workspaceId": "WSA", "surfaceId": "S1"})
    workspaces = store.build_workspaces(cmux.Topology(TREE),
                                        store.read_agents(tmp_path, now=1e9))
    assert [w.title for w in workspaces] == ["Pi Agent", "~"]
    assert [a.session_id for a in workspaces[0].agents] == ["first", "second"]
    assert workspaces[1].agents == []


def test_build_workspaces_can_hide_empty_ones(tmp_path):
    write_status(tmp_path, "one")
    workspaces = store.build_workspaces(cmux.Topology(TREE),
                                        store.read_agents(tmp_path, now=1e9),
                                        only_with_agents=True)
    assert [w.title for w in workspaces] == ["Pi Agent"]


def test_agents_outside_cmux_land_in_a_synthetic_workspace(tmp_path):
    write_status(tmp_path, "lonely", cmux={})
    workspaces = store.build_workspaces(cmux.Topology(TREE),
                                        store.read_agents(tmp_path, now=1e9))
    assert workspaces[-1].title == "elsewhere"
    assert [a.session_id for a in workspaces[-1].agents] == ["lonely"]


# MARK: - render

def test_paint_key_returns_correct_size_for_every_kind():
    specs = [
        {"kind": "blank"},
        {"kind": "workspace", "title": "Pi Agent", "status": "waiting",
         "dots": ["working", "waiting"], "count": 2, "age": "2m", "selected": True},
        {"kind": "workspace", "title": "empty ws", "status": "empty", "dots": []},
        {"kind": "agent", "title": "residently", "subtitle": "bash: rspec",
         "status": "working", "age": "now"},
        {"kind": "agent", "title": "a very long repository name here",
         "subtitle": "an equally long activity line", "status": "blocked", "age": "9m"},
        {"kind": "back", "title": "Pi Agent"},
        {"kind": "more", "remaining": 4},
        {"kind": "message", "text": "no cmux"},
        {"kind": "banner", "text": "pi-deck", "index": 3},
    ]
    for spec in specs:
        assert render.paint_key(spec, size=(80, 80)).size == (80, 80)


def test_long_titles_report_overflow_for_the_marquee():
    over, width = render.title_overflow(
        {"kind": "agent", "title": "an extremely long repository label", "status": "working"})
    assert over and width > 80
    assert render.title_overflow({"kind": "agent", "title": "short", "status": "working"})[0] is False


def test_pulse_dims_the_status_band():
    spec = {"kind": "agent", "title": "x", "status": "waiting", "age": "1m"}
    bright = render.paint_key(spec).getpixel((40, 2))
    dark = render.paint_key(spec, pulse=0.2).getpixel((40, 2))
    assert sum(dark) < sum(bright)
