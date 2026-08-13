"""The pi-deck daemon: joins pi session status to cmux topology, paints the
Stream Deck, and turns presses into cmux focus commands.

Loop shape: a short poll (status files + cmux topology) rebuilds the scene; key
presses mutate the view and wake the loop immediately.
"""

from __future__ import annotations

import json
import logging
import signal
import threading
import time

from . import cmux, paths, store
from .device import Deck, NoDeviceError, enumerate_decks
from .layout import View, build

log = logging.getLogger("pideck")

DEFAULTS = {
    "brightness": 60,
    "poll_interval": 1.0,          # seconds between status refreshes
    "topology_interval": 3.0,      # seconds between cmux topology refreshes
    "agents_view_timeout": 25.0,   # auto-return to the workspaces view
    "only_with_agents": False,     # hide cmux workspaces with no pi sessions
    "focus_single_agent_directly": True,
    "reconnect_interval": 3.0,
    "topology_grace": 20.0,        # keep the last good topology at most this long
                                   # after cmux goes unreachable, then drop it so
                                   # closed workspaces can't linger as phantoms
}


def load_config() -> dict:
    config = dict(DEFAULTS)
    path = paths.config_file()
    if path.is_file():
        try:
            config.update(json.loads(path.read_text()))
        except (OSError, ValueError) as exc:
            log.warning("ignoring bad config %s: %s", path, exc)
    return config


class Daemon:
    def __init__(self, config: dict | None = None, once: bool = False):
        self.config = config or load_config()
        self.once = once
        self.view = View()
        self.deck: Deck | None = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._actions: list[dict | None] = []
        self._topology: cmux.Topology | None = None
        self._topology_at = 0.0          # monotonic time of the last attempt
        self._topology_ok_at = 0.0       # monotonic time of the last success
        self._topology_failing = False   # are we in a run of failed fetches?
        self._last_press = 0.0

    # MARK: - run loop

    def run(self) -> int:
        paths.ensure_dirs()
        while not self._stop.is_set():
            try:
                self.deck = Deck(on_press=self._on_press,
                                 brightness=int(self.config["brightness"])).open()
            except NoDeviceError:
                if self.once:
                    log.error("no Stream Deck found")
                    return 1
                log.info("waiting for a Stream Deck…")
                self._stop.wait(float(self.config["reconnect_interval"]))
                continue
            log.info("deck connected (%s keys, serial %s)",
                     self.deck.key_count, self.deck.serial())
            self.deck.start_frames()
            try:
                self._serve()
            except Exception as exc:                       # device unplugged etc.
                log.warning("deck loop ended: %s", exc)
            finally:
                self.deck.close()
                self.deck = None
            if self.once or self._stop.is_set():
                break
            self._stop.wait(float(self.config["reconnect_interval"]))
        return 0

    def _serve(self) -> None:
        while not self._stop.is_set():
            self.refresh()
            if self.once:
                return
            self._wake.wait(float(self.config["poll_interval"]))
            self._wake.clear()

    def stop(self, *_) -> None:
        self._stop.set()
        self._wake.set()

    # MARK: - scene

    def topology(self, force: bool = False) -> cmux.Topology:
        now = time.monotonic()
        stale = now - self._topology_at > float(self.config["topology_interval"])
        if force or stale or self._topology is None:
            self._topology_at = now
            try:
                self._topology = cmux.topology()
                self._topology_ok_at = now
                if self._topology_failing:
                    log.info("cmux topology recovered")
                    self._topology_failing = False
            except cmux.CmuxError as exc:
                # Log once per outage (WARNING so it reaches the file log), not
                # every poll.
                if not self._topology_failing:
                    log.warning("cmux topology unavailable: %s", exc)
                    self._topology_failing = True
                # Serving a frozen snapshot forever is what strands live
                # sessions under "elsewhere" and leaves closed workspaces on the
                # deck as phantoms. Once cmux has been unreachable past the
                # grace window, drop the stale topology entirely.
                grace = float(self.config["topology_grace"])
                expired = now - self._topology_ok_at > grace
                if self._topology is None or expired:
                    self._topology = cmux.Topology({})
        return self._topology

    def workspaces(self, force_topology: bool = False):
        return store.build_workspaces(
            self.topology(force=force_topology), store.read_agents(),
            only_with_agents=bool(self.config["only_with_agents"]))

    def refresh(self, force_topology: bool = False) -> list[dict]:
        self._expire_agents_view()
        workspaces = self.workspaces(force_topology)
        key_count = self.deck.key_count if self.deck else 6
        keys, self.view = build(workspaces, self.view, key_count=key_count)
        self._actions = [k.action for k in keys]
        specs = [k.spec for k in keys]
        if self.deck:
            self.deck.set_scene(specs)
        return specs

    def _expire_agents_view(self) -> None:
        timeout = float(self.config["agents_view_timeout"])
        if (self.view.mode == "agents" and timeout > 0 and self._last_press
                and time.monotonic() - self._last_press > timeout):
            self.view = View()

    # MARK: - input

    def _on_press(self, index: int, long: bool) -> None:
        self._last_press = time.monotonic()
        action = self._actions[index] if index < len(self._actions) else None
        if action is None:
            return
        try:
            self._dispatch(action, long)
        except cmux.CmuxError as exc:
            log.warning("cmux action failed: %s", exc)
        self._wake.set()

    def _dispatch(self, action: dict, long: bool) -> None:
        kind = action.get("type")
        if kind == "back":
            self.view = View()
        elif kind == "page":
            self.view = self.view.with_page(int(action.get("page", 0)))
        elif kind == "drill":
            self._drill(action, long)
        elif kind == "focus_agent":
            self._focus_agent(action)

    def _drill(self, action: dict, long: bool) -> None:
        workspace_id = action["workspaceId"]
        if long:                                   # hold = just go to the workspace
            cmux.focus_workspace(workspace_id, action.get("windowId"))
            self.view = View()
            return
        agents = self._agents_of(workspace_id)
        if not agents:                             # nothing to drill into
            cmux.focus_workspace(workspace_id, action.get("windowId"))
            self.view = View()
            return
        if len(agents) == 1 and self.config["focus_single_agent_directly"]:
            cmux.focus_surface(agents[0].surface_id, workspace_id,
                               action.get("windowId"))
            self.view = View()
            return
        self.view = View(mode="agents", workspace_id=workspace_id)

    def _focus_agent(self, action: dict) -> None:
        surface_id = action.get("surfaceId")
        if surface_id:
            cmux.focus_surface(surface_id, action.get("workspaceId"),
                               action.get("windowId"))
        elif action.get("workspaceId"):
            cmux.focus_workspace(action["workspaceId"], action.get("windowId"))
        self.view = View()

    def _agents_of(self, workspace_id: str):
        for workspace in self.workspaces():
            if workspace.workspace_id == workspace_id:
                return [a for a in workspace.live_agents() if a.surface_id]
        return []


def setup_logging(verbose: bool = False) -> None:
    paths.ensure_dirs()
    handlers: list[logging.Handler] = [logging.FileHandler(paths.log_file())]
    if verbose:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        handlers=handlers)


def main(verbose: bool = False) -> int:
    setup_logging(verbose)
    daemon = Daemon()
    signal.signal(signal.SIGTERM, daemon.stop)
    signal.signal(signal.SIGINT, daemon.stop)
    if not enumerate_decks():
        log.info("no Stream Deck attached yet")
    return daemon.run()
