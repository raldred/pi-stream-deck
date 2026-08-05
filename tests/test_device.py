"""Device tests with a fake Stream Deck: scene diffing, marquee continuity, presses."""

from __future__ import annotations

import time

from pideck.device import LONG_PRESS, Deck


class FakeDeck:
    """Enough of the StreamDeck API for PILHelper and Deck to work headless."""

    def __init__(self, keys=6):
        self._keys = keys
        self.images: dict[int, object] = {}
        self.writes: list[int] = []
        self.brightness = None
        self.callback = None

    def open(self):
        pass

    def reset(self):
        self.images.clear()

    def close(self):
        pass

    def set_brightness(self, value):
        self.brightness = value

    def set_key_callback(self, cb):
        self.callback = cb

    def key_count(self):
        return self._keys

    def key_image_format(self):
        return {"size": (80, 80), "format": "BMP", "flip": (False, True), "rotation": 90}

    def get_serial_number(self):
        return "FAKE1"

    def set_key_image(self, index, image):
        self.images[index] = image
        self.writes.append(index)


def deck(on_press=None) -> tuple[Deck, FakeDeck]:
    fake = FakeDeck()
    return Deck(on_press=on_press, device=fake).open(), fake


WORKSPACE = {"kind": "workspace", "title": "a workspace with a long name",
             "status": "waiting", "dots": ["waiting"], "count": 1, "age": "1m"}


def test_blank_keys_are_switched_off_not_painted_dark():
    d, fake = deck()
    d.set_scene([WORKSPACE, WORKSPACE])
    assert fake.images[0] is not None
    d.set_scene([{"kind": "blank"}] * 6)
    assert fake.images[0] is None and fake.images[1] is None


def test_unchanged_keys_are_not_repainted():
    d, fake = deck()
    d.set_scene([WORKSPACE])
    fake.writes.clear()
    d.set_scene([WORKSPACE])
    assert fake.writes == []


def test_ticking_age_repaints_but_keeps_the_scroll_offset():
    d, fake = deck()
    d.set_scene([WORKSPACE])
    for _ in range(8):                       # let the marquee get going
        d._animate(0, WORKSPACE, 1)
    scrolled = d._anim[0]["title"]["scroll"]
    assert scrolled > 0

    d.set_scene([{**WORKSPACE, "age": "2m"}])
    assert 0 in fake.writes                  # it did repaint
    assert d._anim[0]["title"]["scroll"] >= scrolled   # …without restarting


def test_changing_the_title_resets_the_scroll():
    d, _ = deck()
    d.set_scene([WORKSPACE])
    for _ in range(8):
        d._animate(0, WORKSPACE, 1)
    assert d._anim[0]["title"]["scroll"] > 0
    d.set_scene([{**WORKSPACE, "title": "a different long workspace name"}])
    assert d._anim.get(0, {}).get("title", {}).get("scroll", 0) == 0


def test_short_and_long_presses_are_distinguished():
    seen: list[tuple[int, bool]] = []
    d, fake = deck(on_press=lambda i, long: seen.append((i, long)))
    fake.callback(fake, 2, True)
    fake.callback(fake, 2, False)
    assert seen == [(2, False)]

    seen.clear()
    fake.callback(fake, 3, True)
    d._down[3] = time.monotonic() - (LONG_PRESS + 0.1)
    d._check_long_press()                    # fires while still held
    fake.callback(fake, 3, False)            # release must not double-fire
    assert seen == [(3, True)]
