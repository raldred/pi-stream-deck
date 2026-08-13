"""Paints Stream Deck key images with Pillow.

The daemon decides *what* each key shows (a spec dict); this module owns *how*
it is painted. Key specs:

    {"kind": "workspace", "title":.., "status":.., "dots":[status,..],
     "count": n, "age": "2m", "selected": bool, "stuck": bool}
    {"kind": "agent", "title":.., "subtitle":.., "status":.., "age":..,
     "stuck": bool}
    {"kind": "back", "title": ".."}
    {"kind": "more", "remaining": n}
    {"kind": "banner", "text": "..", "index": n}
    {"kind": "blank"}
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

STATUS_COLORS = {
    "blocked": (220, 60, 60),      # red — blocked on a permission prompt
    "question": (235, 150, 40),    # amber — waiting for an answer
    "waiting": (235, 150, 40),     # amber — finished its turn, your move
    "idle": (205, 180, 70),        # gold — alive but stale
    "compacting": (70, 130, 220),  # blue — compacting context
    "working": (60, 180, 90),      # green — busy
    "ended": (70, 70, 70),         # grey tombstone
    "empty": (52, 52, 58),         # grey — workspace with no pi agents
}
NEEDS_YOU = frozenset({"blocked", "question", "waiting", "idle"})
GLYPH_STATUSES = frozenset({"blocked", "question", "waiting", "idle", "compacting"})
GLYPH_GUTTER = 16

BG = (24, 24, 27)
FG = (235, 235, 235)
DIM = (120, 120, 130)
ACCENT = (150, 130, 245)

PAD = 6
TITLE_SIZE = 14
SUB_SIZE = 11
AGE_SIZE = 10
BANNER_SIZE = 26
SCROLL_GAP = 16
LINE_H = 18
BAND_H = 5


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in (
        "/System/Library/Fonts/SFNSRounded.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _text_width(text: str, font) -> int:
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    return int(draw.textlength(text, font=font))


def _truncate(draw, text, font, max_width):
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text + "…" if text else ""


def _dim(color, factor: float):
    return tuple(max(0, min(255, int(c * factor))) for c in color)


# MARK: - marquee support (the daemon animates long titles)

def title_of(spec: dict):
    if spec.get("kind") not in ("workspace", "agent"):
        return None
    return str(spec.get("title") or "?")


def subtitle_of(spec: dict):
    if spec.get("kind") != "agent":
        return None
    sub = spec.get("subtitle")
    return str(sub) if sub else None


def _title_gutter(spec: dict) -> int:
    return GLYPH_GUTTER if spec.get("status") in GLYPH_STATUSES else 0


def title_overflow(spec: dict, size=(80, 80)):
    text = title_of(spec)
    if text is None:
        return (False, 0)
    max_w = size[0] - 2 * PAD - _title_gutter(spec)
    tw = _text_width(text, _font(TITLE_SIZE))
    return (tw > max_w, tw)


def subtitle_overflow(spec: dict, size=(80, 80)):
    text = subtitle_of(spec)
    if text is None:
        return (False, 0)
    max_w = size[0] - 2 * PAD
    tw = _text_width(text, _font(SUB_SIZE))
    return (tw > max_w, tw)


def _draw_marquee(base, text, font, x0, y, max_width, scroll_x, fill=FG):
    tw = _text_width(text, font)
    period = tw + SCROLL_GAP
    off = scroll_x % period if period else 0
    strip = Image.new("RGB", (max_width, LINE_H), BG)
    d = ImageDraw.Draw(strip)
    x = -off
    while x < max_width:
        d.text((x, 0), text, font=font, fill=fill)
        x += period
    base.paste(strip, (x0, y))


# MARK: - key painting

def paint_key(spec: dict, size=(80, 80), scroll_x=0, marquee=False, pulse=1.0,
              sub_scroll_x=0, sub_marquee=False) -> Image.Image:
    kind = spec.get("kind", "blank")
    img = Image.new("RGB", size, BG)
    draw = ImageDraw.Draw(img)
    w, h = size

    if kind == "blank":
        return Image.new("RGB", size, (0, 0, 0))
    if kind == "banner":
        return paint_banner_cell(spec.get("text", ""), int(spec.get("index", 0)), size)
    if kind == "more":
        _paint_centered(draw, f"▶ {spec.get('remaining', 0)} more", size)
        return img
    if kind == "back":
        _paint_back(img, draw, spec, size)
        return img
    if kind == "message":
        _paint_centered(draw, str(spec.get("text", "")), size, color=DIM)
        return img

    status = spec.get("status", "idle")
    color = STATUS_COLORS.get(status, DIM)
    if pulse < 1.0:
        color = _dim(color, pulse)
    draw.rectangle([0, 0, w, BAND_H], fill=color)

    if spec.get("selected"):
        # a thin accent rule down the left edge marks the focused workspace
        draw.rectangle([0, BAND_H + 1, 2, h], fill=ACCENT)

    title_font = _font(TITLE_SIZE)
    y = PAD + 4
    title = title_of(spec) or "?"
    title_w = w - 2 * PAD - _title_gutter(spec)
    if marquee:
        _draw_marquee(img, title, title_font, PAD, y, title_w, scroll_x)
    else:
        draw.text((PAD, y), _truncate(draw, title, title_font, title_w),
                  font=title_font, fill=FG)
    y += LINE_H

    if kind == "workspace":
        _paint_dots(draw, spec, PAD, y + 2, w)
    else:
        sub = subtitle_of(spec)
        if sub:
            if sub_marquee:
                _draw_marquee(img, sub, _font(SUB_SIZE), PAD, y, w - 2 * PAD,
                              sub_scroll_x, fill=DIM)
            else:
                draw.text((PAD, y), _truncate(draw, sub, _font(SUB_SIZE), w - 2 * PAD),
                          font=_font(SUB_SIZE), fill=DIM)

    age = spec.get("age")
    if age:
        draw.text((PAD, h - 16), _truncate(draw, str(age), _font(AGE_SIZE), w - 2 * PAD),
                  font=_font(AGE_SIZE), fill=DIM)

    if kind == "workspace":
        count = int(spec.get("count", 0) or 0)
        if count:
            _paint_count_badge(draw, count, w, h)
    elif int(spec.get("subagents", 0) or 0) > 0:
        _paint_subagent_badge(draw, int(spec["subagents"]), w, h)
    if status in GLYPH_STATUSES:
        _draw_status_glyph(draw, status, w, h)
    return img


def _paint_centered(draw, text, size, color=FG, font_size=15):
    w, h = size
    font = _font(font_size)
    tw = draw.textlength(text, font=font)
    draw.text(((w - tw) / 2, h / 2 - 10), text, font=font, fill=color)


def _paint_back(img, draw, spec, size):
    w, h = size
    font = _font(15)
    text = "◀ back"
    tw = draw.textlength(text, font=font)
    draw.text(((w - tw) / 2, h / 2 - 16), text, font=font, fill=FG)
    title = spec.get("title")
    if title:
        sub = _font(SUB_SIZE)
        label = _truncate(draw, str(title), sub, w - 2 * PAD)
        sw = draw.textlength(label, font=sub)
        draw.text(((w - sw) / 2, h / 2 + 4), label, font=sub, fill=DIM)


def _paint_dots(draw, spec, x0, y, w):
    """One dot per top-level pi session, coloured by state — the glanceable
    roll-up. Subagents trail behind as smaller purple dots, so a busy session
    with helpers reads differently from three separate sessions."""
    dots = list(spec.get("dots") or [])
    subagents = int(spec.get("subagents", 0) or 0)
    if not dots:
        draw.text((x0, y - 2), "no agents", font=_font(SUB_SIZE), fill=DIM)
        return
    radius, gap = 4, 5
    sub_radius, sub_gap = 2, 4
    budget = w - 2 * PAD
    sub_width = subagents * (2 * sub_radius + sub_gap) + (4 if subagents else 0)
    max_dots = max(1, (budget - sub_width + gap) // (2 * radius + gap))
    shown = dots[:max_dots]
    x = x0
    for status in shown:
        draw.ellipse([x, y, x + 2 * radius, y + 2 * radius],
                     fill=STATUS_COLORS.get(status, DIM))
        x += 2 * radius + gap
    if len(dots) > len(shown):
        draw.text((x, y - 3), f"+{len(dots) - len(shown)}",
                  font=_font(AGE_SIZE), fill=DIM)
        return
    if subagents:
        x += 2
        mid = y + radius - sub_radius
        for _ in range(subagents):
            if x + 2 * sub_radius > w - PAD:
                break
            draw.ellipse([x, mid, x + 2 * sub_radius, mid + 2 * sub_radius], fill=ACCENT)
            x += 2 * sub_radius + sub_gap


def _paint_subagent_badge(draw, count, w, h):
    """A purple pill counting the subagents this session has running."""
    label = f"⤷{count}"
    font = _font(SUB_SIZE)
    tw = draw.textlength(label, font=font)
    bw, bh = int(tw) + 10, 15
    x1, y1 = w - PAD + 2, h - PAD + 1
    x0, y0 = x1 - bw, y1 - bh
    draw.rounded_rectangle([x0, y0, x1, y1], radius=bh // 2, fill=ACCENT)
    draw.text((x0 + (bw - tw) / 2, y0 + 1), label, font=font, fill=(255, 255, 255))


def _paint_count_badge(draw, count, w, h):
    label = f"{count}\u03c0"           # e.g. "3π"
    font = _font(SUB_SIZE)
    tw = draw.textlength(label, font=font)
    bw, bh = int(tw) + 10, 15
    x1, y1 = w - PAD + 2, h - PAD + 1
    x0, y0 = x1 - bw, y1 - bh
    draw.rounded_rectangle([x0, y0, x1, y1], radius=bh // 2, fill=(44, 44, 52))
    draw.text((x0 + (bw - tw) / 2, y0 + 1), label, font=font, fill=FG)


def _draw_status_glyph(draw, status, w, h):
    white = (255, 255, 255)
    x1, y0 = w - 5, 7
    x0 = x1 - 14
    if status == "blocked":                     # padlock
        draw.arc([x0 + 3, y0, x1 - 3, y0 + 11], start=180, end=360, fill=white, width=2)
        draw.rectangle([x0 + 1, y0 + 6, x1 - 1, y0 + 14], fill=white)
    elif status == "question":                  # question mark
        font = _font(16)
        draw.text((x0 + 3, y0 - 5), "?", font=font, fill=white)
    elif status == "waiting":                   # checkmark
        draw.line([(x0 + 1, y0 + 7), (x0 + 5, y0 + 12), (x1, y0 + 1)], fill=white, width=2)
    elif status == "idle":                      # ellipsis
        for i in range(3):
            cx = x0 + 2 + i * 5
            draw.ellipse([cx, y0 + 9, cx + 2, y0 + 11], fill=white)
    elif status == "compacting":                # double chevron
        for dy in (0, 4):
            draw.line([(x0 + 1, y0 + dy + 2), (x0 + 7, y0 + dy + 7), (x1 - 1, y0 + dy + 2)],
                      fill=white, width=2)


def paint_banner_cell(text: str, index: int, size=(80, 80), cols=3, rows=2) -> Image.Image:
    w, h = size
    full = Image.new("RGB", (w * cols, h * rows), BG)
    draw = ImageDraw.Draw(full)
    font = _font(BANNER_SIZE)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((w * cols - tw) / 2 - bbox[0], (h * rows - th) / 2 - bbox[1]),
              text, font=font, fill=FG)
    col, row = index % cols, index // cols
    return full.crop((col * w, row * h, col * w + w, row * h + h))
