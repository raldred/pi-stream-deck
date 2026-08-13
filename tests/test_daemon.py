"""Daemon topology-cache tests: a cmux outage must not leave phantom
workspaces on the deck or strand live sessions under 'elsewhere'.
"""

from __future__ import annotations

import pytest

from pideck import cmux, daemon as daemon_mod
from pideck.daemon import Daemon

TREE = {
    "windows": [{
        "id": "WIN1",
        "workspaces": [{
            "id": "WSA", "title": "Agent updates", "index": 0, "selected": True,
            "panes": [{"id": "P1", "surfaces": [
                {"id": "S1", "title": "π", "type": "terminal"}]}],
        }],
    }]
}


@pytest.fixture
def clock(monkeypatch):
    t = {"now": 1000.0}
    monkeypatch.setattr(daemon_mod.time, "monotonic", lambda: t["now"])
    return t


def _daemon(grace=20.0):
    return Daemon(config={
        "topology_interval": 3.0, "topology_grace": grace, "poll_interval": 1.0,
    })


def test_serves_last_good_topology_during_a_brief_blip(clock, monkeypatch):
    d = _daemon(grace=20.0)
    monkeypatch.setattr(cmux, "topology", lambda: cmux.Topology(TREE))
    assert [w["title"] for w in d.topology().workspaces] == ["Agent updates"]

    # cmux goes away; within the grace window we keep the last good snapshot.
    monkeypatch.setattr(cmux, "topology",
                        lambda: (_ for _ in ()).throw(cmux.CmuxError("down")))
    clock["now"] += 10.0
    assert [w["title"] for w in d.topology(force=True).workspaces] == ["Agent updates"]


def test_drops_stale_topology_once_cmux_is_gone_past_the_grace(clock, monkeypatch):
    d = _daemon(grace=20.0)
    monkeypatch.setattr(cmux, "topology", lambda: cmux.Topology(TREE))
    d.topology()

    monkeypatch.setattr(cmux, "topology",
                        lambda: (_ for _ in ()).throw(cmux.CmuxError("down")))
    clock["now"] += 30.0                       # past the grace window
    # No phantom "Agent updates" left behind — the board goes honestly empty.
    assert d.topology(force=True).workspaces == []


def test_recovers_after_the_outage(clock, monkeypatch):
    d = _daemon(grace=5.0)
    monkeypatch.setattr(cmux, "topology",
                        lambda: (_ for _ in ()).throw(cmux.CmuxError("down")))
    assert d.topology().workspaces == []
    assert d._topology_failing is True

    monkeypatch.setattr(cmux, "topology", lambda: cmux.Topology(TREE))
    clock["now"] += 1.0
    assert [w["title"] for w in d.topology(force=True).workspaces] == ["Agent updates"]
    assert d._topology_failing is False
