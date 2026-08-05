"""Stream Deck device driver: paints scenes, animates them, reports presses.

Runs in-process (no helper protocol): the daemon hands over a list of key specs,
this class diffs them against the current scene, paints only what changed, and
animates marquee titles plus the pulsing band on keys that need you.

Presses are reported as short or long (hold) presses. A long press fires as soon
as the hold threshold passes, so it feels immediate.
"""

from __future__ import annotations

import math
import os
import threading
import time
from typing import Callable

FRAME_INTERVAL = 0.2       # 5fps
SCROLL_STRIDE = 3
SCROLL_HOLD_FRAMES = 3
CALM_PULSE_PERIOD = 8
CALM_PULSE_MIN = 0.5
STUCK_PULSE_PERIOD = 4
STUCK_PULSE_MIN = 0.15
LONG_PRESS = 0.55         # seconds


def _ensure_hidapi_prefix() -> None:
    """The streamdeck lib loads `$HOMEBREW_PREFIX/lib/libhidapi.dylib`; when we
    are launched by launchd there is no PATH for its `brew --prefix` fallback."""
    if os.environ.get("HOMEBREW_PREFIX"):
        return
    here = os.path.dirname(os.path.abspath(__file__))
    for prefix in (os.path.join(here, "vendor"), "/opt/homebrew", "/usr/local"):
        if os.path.exists(os.path.join(prefix, "lib", "libhidapi.dylib")):
            os.environ["HOMEBREW_PREFIX"] = prefix
            return


_ensure_hidapi_prefix()

from StreamDeck.DeviceManager import DeviceManager      # noqa: E402
from StreamDeck.ImageHelpers import PILHelper           # noqa: E402

from . import render                                     # noqa: E402


def _pulse(frame: int, stuck: bool) -> float:
    period = STUCK_PULSE_PERIOD if stuck else CALM_PULSE_PERIOD
    floor = STUCK_PULSE_MIN if stuck else CALM_PULSE_MIN
    phase = 2 * math.pi * (frame % period) / period
    return floor + (1 - floor) * (0.5 + 0.5 * math.sin(phase))


class NoDeviceError(RuntimeError):
    pass


def enumerate_decks():
    return DeviceManager().enumerate()


class Deck:
    def __init__(self, on_press: Callable[[int, bool], None] | None = None,
                 brightness: int = 60, device=None):
        decks = [device] if device is not None else enumerate_decks()
        if not decks:
            raise NoDeviceError("no Stream Deck found")
        self.deck = decks[0]
        self.on_press = on_press
        self._brightness = brightness
        self._lock = threading.RLock()
        self._size = (80, 80)
        self._scene: list[dict] = []
        self._anim: dict[int, dict] = {}
        self._animated: set[int] = set()
        self._frame = 0
        self._down: dict[int, float] = {}
        self._long_fired: set[int] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # MARK: - lifecycle

    def open(self) -> "Deck":
        self.deck.open()
        self.deck.reset()
        self.deck.set_brightness(self._brightness)
        self.deck.set_key_callback(self._on_key)
        self._size = self.deck.key_image_format()["size"]
        self._scene = [{"kind": "blank"} for _ in range(self.key_count)]
        return self

    @property
    def key_count(self) -> int:
        return self.deck.key_count()

    def serial(self) -> str | None:
        try:
            return self.deck.get_serial_number()
        except Exception:
            return None

    def start_frames(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run_frames, daemon=True)
            self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=FRAME_INTERVAL * 2)
        try:
            self.deck.reset()
            self.deck.close()
        except Exception:
            pass

    def set_brightness(self, value: int) -> None:
        self._brightness = max(0, min(100, int(value)))
        with self._lock:
            self.deck.set_brightness(self._brightness)

    # MARK: - scene

    def set_scene(self, specs: list[dict]) -> None:
        """Paint `specs` (one per key). Keys whose text is unchanged keep their
        marquee offsets, so a ticking age line never restarts the scroll."""
        with self._lock:
            padded = list(specs[:self.key_count])
            padded += [{"kind": "blank"}] * (self.key_count - len(padded))
            for index, spec in enumerate(padded):
                old = self._scene[index] if index < len(self._scene) else None
                if old == spec:
                    continue
                if not self._same_text(old, spec):
                    self._anim.pop(index, None)
                self._scene[index] = spec
                self._animated.discard(index)
                if self._needs_animation(spec):
                    self._animated.add(index)
                    self._animate(index, spec, self._frame)   # resume mid-scroll
                else:
                    self._paint(index, spec)
            self._scene = padded

    @staticmethod
    def _same_text(old: dict | None, spec: dict) -> bool:
        """True when the scrolling lines are identical, so their offsets still
        apply — only volatile fields (age, dots, pulse) changed."""
        if old is None:
            return False
        return all(old.get(field) == spec.get(field)
                   for field in ("kind", "title", "subtitle", "status"))

    def _needs_animation(self, spec: dict) -> bool:
        title_over, _ = render.title_overflow(spec, self._size)
        sub_over, _ = render.subtitle_overflow(spec, self._size)
        return bool(title_over or sub_over or spec.get("status") in render.NEEDS_YOU)

    def _paint(self, index: int, spec: dict, scroll_x=0, marquee=False, pulse=1.0,
               sub_scroll_x=0, sub_marquee=False) -> None:
        if not (0 <= index < self.key_count):
            return
        if spec.get("kind", "blank") == "blank":
            # Truly dark, not a faintly-lit dark grey square.
            with self._lock:
                self.deck.set_key_image(index, None)
            return
        if not marquee and not sub_marquee and pulse == 1.0:
            marquee, _ = render.title_overflow(spec, self._size)
            sub_marquee, _ = render.subtitle_overflow(spec, self._size)
        image = render.paint_key(spec, size=self._size, scroll_x=scroll_x,
                                 marquee=marquee, pulse=pulse,
                                 sub_scroll_x=sub_scroll_x, sub_marquee=sub_marquee)
        native = PILHelper.to_native_format(self.deck, image)
        with self._lock:
            self.deck.set_key_image(index, native)

    # MARK: - animation

    def _run_frames(self) -> None:
        while not self._stop.wait(FRAME_INTERVAL):
            with self._lock:
                self._frame += 1
                for index in list(self._animated):
                    self._animate(index, self._scene[index], self._frame)
                self._check_long_press()

    def _advance(self, state: dict, text_w: int) -> int:
        period = text_w + render.SCROLL_GAP
        if state["hold"] < SCROLL_HOLD_FRAMES:
            state["hold"] += 1
        else:
            state["scroll"] += SCROLL_STRIDE
            if state["scroll"] >= period:
                state["scroll"], state["hold"] = 0, 0
        return state["scroll"]

    def _animate(self, index: int, spec: dict, frame: int) -> None:
        title_over, title_w = render.title_overflow(spec, self._size)
        sub_over, sub_w = render.subtitle_overflow(spec, self._size)
        lines = self._anim.setdefault(index, {})
        scroll_x = self._advance(lines.setdefault("title", {"scroll": 0, "hold": 0}),
                                 title_w) if title_over else 0
        sub_scroll_x = self._advance(lines.setdefault("sub", {"scroll": 0, "hold": 0}),
                                     sub_w) if sub_over else 0
        pulse = (_pulse(frame, bool(spec.get("stuck")))
                 if spec.get("status") in render.NEEDS_YOU else 1.0)
        self._paint(index, spec, scroll_x=scroll_x, marquee=title_over, pulse=pulse,
                    sub_scroll_x=sub_scroll_x, sub_marquee=sub_over)

    # MARK: - input

    def _on_key(self, deck, index: int, pressed: bool) -> None:
        now = time.monotonic()
        if pressed:
            self._down[index] = now
            return
        started = self._down.pop(index, None)
        long_fired = index in self._long_fired
        self._long_fired.discard(index)
        if started is None or long_fired:
            return
        self._emit(index, long=(now - started) >= LONG_PRESS)

    def _check_long_press(self) -> None:
        now = time.monotonic()
        for index, started in list(self._down.items()):
            if index not in self._long_fired and now - started >= LONG_PRESS:
                self._long_fired.add(index)
                self._emit(index, long=True)

    def _emit(self, index: int, long: bool) -> None:
        if self.on_press is None:
            return
        try:
            self.on_press(index, long)
        except Exception:
            pass
