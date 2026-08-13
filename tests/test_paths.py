"""Filesystem-location tests shared by the extension and daemon conventions."""

from pideck import paths


def test_default_root_lives_under_pi_agent_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)
    monkeypatch.delenv("PI_DECK_HOME", raising=False)

    assert paths.root() == tmp_path / ".pi" / "agent" / "pi-stream-deck"


def test_root_follows_custom_pi_agent_directory(monkeypatch, tmp_path):
    agent_dir = tmp_path / "custom-agent"
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(agent_dir))
    monkeypatch.delenv("PI_DECK_HOME", raising=False)

    assert paths.root() == agent_dir / "pi-stream-deck"


def test_explicit_pi_deck_home_takes_precedence(monkeypatch, tmp_path):
    override = tmp_path / "deck-data"
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path / "custom-agent"))
    monkeypatch.setenv("PI_DECK_HOME", str(override))

    assert paths.root() == override
    assert paths.status_dir() == override / "status"
    assert paths.config_file() == override / "config.json"
    assert paths.log_file() == override / "pideck.log"
