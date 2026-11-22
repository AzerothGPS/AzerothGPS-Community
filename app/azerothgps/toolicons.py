"""The road and wall tools' legend icons (`agps toolicons`; asked 2026-11-19 for 1.3.10: the tools' hint at the top of
the map was "a wall of colored text"; now a list on the map's left, one action a row, each with a small pixel icon for
its input, as the controller's buttons are shown). Our own: drawn from numbers alone, nothing of the game's.

Icons (Media/Tools/<name>_<px>.tga): the mouse with its left button lit (gold), its right button lit (red: erasing),
its wheel rolled (ridged), and the Shift and Ctrl keys as keycaps twice as wide as high; and the stairs glyph the map
draws along a stairs road with the road tools on (`Stairs<d>`: three treads narrowing and lightening toward the top, an
arrow uphill; one file per STAIR_DIRS way it points, d = 0 up, then clockwise by 45 degrees, each drawn turned rather
than turned in the game, which would filter it). And Search Places' Pin button
(asked 2026-11-19: "a literal pixel-art map pin"): a push-pin, its round red head up right and its short silver needle
pointing down left, and PinLit, the same with its head brighter (the mouse over it). Each drawn
at each of ICON_PX pixels high, pixel for pixel (never scaled in the game: the client's LINEAR filter blurs a shrunk
one, and nothing above LINEAR may be asked, it crashes WoW Forever), in the top-left corner of the smallest square
power-of-two canvas that holds it, as the corner logo is (media.on_canvas); GPSFrame's G.ToolIconFile picks the size
nearest the icon's pixels on the screen and shows only the drawing (SetTexCoord). Keep in step with GPSFrame's
G.TOOL_ICON_PX / G.TOOL_ICON_WIDE."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .coast import tga_rgba

TOOLS_DIR = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS" / "Media" / "Tools"
ICON_PX = (12, 14, 16, 18, 20, 24, 28, 32, 40)
WIDE = {"Shift": 2, "Ctrl": 2}  # (keycaps: this many times as wide as high)

OUTLINE = (12, 10, 8)
MOUSE = (196, 196, 202)  # (the mouse: light gray, readable on the legend's dark tint)
MOUSE_SHADE = (150, 150, 158)
SEAM = (70, 70, 78)  # (the line between its buttons)
LIT = (255, 209, 0)  # (the options' gold: the button used)
ERASE = (220, 56, 48)  # (the right button: erasing, as the eraser's red stroke)
KEY = (58, 58, 64)  # (a keycap: the controller icons' plastic)
KEY_TOP = (92, 92, 100)
TEXT = (255, 255, 255)
PIN_HEAD = ((200, 34, 30), (142, 20, 18), (255, 132, 120))  # (its red, its shaded side, its shine)
PIN_HEAD_LIT = ((246, 62, 52), (186, 34, 28), (255, 190, 180))
PIN_RIM = (52, 8, 8)
NEEDLE = ((214, 216, 224), (128, 130, 140))  # (silver: its lit and its shaded side)

FONT3 = {
    "S": ("###", "#..", "###", "..#", "###"), "H": ("#.#", "#.#", "###", "#.#", "#.#"),
    "I": ("###", ".#.", ".#.", ".#.", "###"), "F": ("###", "#..", "##.", "#..", "#.."),
    "T": ("###", ".#.", ".#.", ".#.", ".#."), "C": ("###", "#..", "#..", "#..", "###"),
    "R": ("##.", "#.#", "##.", "#.#", "#.#"), "L": ("#..", "#..", "#..", "#..", "###"),
}
FONT5 = {
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "C": (".####", "#....", "#....", "#....", "#....", "#....", ".####"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
}


def text_mask(text: str, max_w: int, max_h: int) -> np.ndarray:
    """`text` in the pixel font, the biggest that fits max_w x max_h (whole-number scales only): a bool array."""
    best = None
    for font, gw, gh in ((FONT3, 3, 5), (FONT5, 5, 7)):
        for k in (1, 2, 3, 4):
            w, h = (len(text) * gw + len(text) - 1) * k, gh * k
            if w <= max_w and h <= max_h and (best is None or h > best[3]):
                best = (font, gw, gh, h, k)
    font, gw, gh, _, k = best or (FONT3, 3, 5, 5, 1)
    cols = []
    for i, ch in enumerate(text):
        if i:
            cols.append(np.zeros((gh, 1), bool))
        cols.append(np.array([[c == "#" for c in row] for row in font[ch]], bool))
    return np.kron(np.concatenate(cols, axis=1), np.ones((k, k), bool)).astype(bool)


def _grid(w, h):
    return (np.arange(w) + 0.5)[None, :], (np.arange(h) + 0.5)[:, None]


def rrect(w, h, x0, y0, x1, y1, r):
    """A rounded rectangle [x0, x1) x [y0, y1) on a w x h grid, its corners' radius r."""
    x, y = _grid(w, h)
    inside = (x >= x0) & (x < x1) & (y >= y0) & (y < y1)
    qx, qy = np.clip(x, x0 + r, x1 - r), np.clip(y, y0 + r, y1 - r)
    return inside & ((x - qx) ** 2 + (y - qy) ** 2 <= r * r)


def edge(mask):
    p = np.pad(mask, 1)
    inner = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    return mask & ~inner


def paint(img, mask, rgb):
    img[mask] = (*rgb, 255)


def mouse(n: int, lit: str | None) -> np.ndarray:
    """The mouse, n x n: `lit` "left", "right", "middle" (the wheel pressed) or "wheel" (the wheel rolled)."""
    img = np.zeros((n, n, 4), np.uint8)
    bw = max(10, int(round(n * 0.76)) // 2 * 2)  # (even: its middle on a pixel edge)
    x0 = (n - bw) // 2
    x1, mid = x0 + bw, n / 2
    body = rrect(n, n, x0, 0, x1, n, bw * 0.45)
    paint(img, body, MOUSE)
    x, y = _grid(n, n)
    split = max(4, int(round(n * 0.45)))  # (the buttons above this row)
    paint(img, body & (y > n - max(2, n // 5)), MOUSE_SHADE)  # (its round back, shaded)
    seam_y = body & (y >= split) & (y < split + 1)
    seam_x = body & (y < split) & (np.abs(x - mid) < 0.6 + n // 24)
    ww = max(2, n // 6) // 2 * 2  # (the wheel: even wide, on the middle)
    wheel = (np.abs(x - mid) < ww / 2 + 0.01) & (y >= max(2, round(n * 0.12))) & (y < split - 1 + max(0, n // 12))
    left = body & (y < split) & (x < mid) & ~seam_x & ~wheel
    right = body & (y < split) & (x > mid) & ~seam_x & ~wheel
    if lit == "left":
        paint(img, left, LIT)
    elif lit == "right":
        paint(img, right, ERASE)
    paint(img, seam_y | seam_x, SEAM)
    if n >= 16:
        paint(img, grow_x(wheel) & body & (y < split), OUTLINE)  # (the wheel's slot)
    if lit == "middle":
        paint(img, wheel, LIT)
    elif lit == "wheel":
        rows = (np.floor(y) % 2 == 0)
        paint(img, wheel & rows, LIT)
        paint(img, wheel & ~rows, (150, 110, 0))
    else:
        paint(img, wheel, SEAM)
    paint(img, edge(body), OUTLINE)
    return img


def grow_x(mask):
    p = np.pad(mask, 1)
    return p[1:-1, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:] | p[:-2, 1:-1] | p[2:, 1:-1]


def key(n: int, text: str) -> np.ndarray:
    """A keycap n high and WIDE[text] * n wide with `text` on it."""
    w = WIDE[text] * n
    img = np.zeros((n, w, 4), np.uint8)
    cap = rrect(w, n, 0, 0, w, n, max(1.5, n / 6))
    paint(img, cap, KEY)
    x, y = _grid(w, n)
    top = rrect(w, n, 1, 1, w - 1, n - max(2, n // 6), max(1, n / 8))
    paint(img, top & cap, KEY_TOP)
    label = text.upper()
    # (both keys' text the same size: the one that fits SHIFT, the longer)
    fit = text_mask("SHIFT", WIDE["Shift"] * n - 4, n - max(2, n // 6) - 3)
    m = text_mask(label, w - 4, fit.shape[0])
    h, mw = m.shape
    tx = (w - mw) // 2
    ty = max(1, (n - max(2, n // 6) - h) // 2 + (1 if n >= 16 else 0))
    sub = img[ty:ty + h, tx:tx + mw]
    sub[m[:sub.shape[0], :sub.shape[1]]] = (*TEXT, 255)
    paint(img, edge(cap), OUTLINE)
    return img


STAIR_DIRS = 8
TREAD_FOOT = (165, 165, 160)  # (the stairs' lowest tread: darker; the top one white, so the climb reads)
TREAD_TOP = (255, 255, 250)
# (each tread: from and to along the way up, and its half width, as shares of the icon's side; foot first)
TREADS = ((-0.42, -0.18, 0.46), (-0.11, 0.11, 0.32), (0.18, 0.40, 0.18))


def _treads(n: int, d: int, scale: float) -> list:
    """Each tread's pixels (4 x 4 samples a pixel, half or more inside), the glyph `scale` times its size."""
    a = np.radians(d * 360.0 / STAIR_DIRS)
    ux, uy = np.sin(a), -np.cos(a)  # (uphill, the image's y down)
    vx, vy = np.cos(a), np.sin(a)
    ss = 4
    g = (np.arange(n * ss) + 0.5) / ss - n / 2
    x, y = g[None, :], g[:, None]
    along, across = (x * ux + y * uy) / (n * scale), (x * vx + y * vy) / (n * scale)
    out = []
    for p0, p1, w in TREADS:
        inside = (along >= p0) & (along < p1) & (np.abs(across) <= w)
        out.append(inside.reshape(n, ss, n, ss).mean(axis=(1, 3)) >= 0.5)
    return out


def stairs(n: int, d: int) -> np.ndarray:
    """The stairs glyph, n x n, pointing uphill d * 45 degrees clockwise from up: the treads as big as fit with a pixel
    round them for the dark outline (a turned one a little smaller), the foot's darker, the top's white."""
    img = np.zeros((n, n, 4), np.uint8)
    scale = 1.0
    while True:
        treads = _treads(n, d, scale)
        lit = np.any(treads, axis=0)
        ys, xs = np.nonzero(lit)
        if scale < 0.5 or (len(xs) and xs.min() >= 1 and ys.min() >= 1 and xs.max() <= n - 2 and ys.max() <= n - 2):
            break
        scale *= 0.96
    for k, cover in enumerate(treads):
        t = k / (len(treads) - 1)
        paint(img, cover, tuple(int(round(f + (h - f) * t)) for f, h in zip(TREAD_FOOT, TREAD_TOP)))
    paint(img, grow_8(lit) & ~lit, OUTLINE)
    return img


def grow_8(mask):
    p = np.pad(mask, 1)
    out = mask.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            out |= p[1 + dy:1 + dy + mask.shape[0], 1 + dx:1 + dx + mask.shape[1]]
    return out


def pin(n: int, lit: bool = False) -> np.ndarray:
    """The map pin, n x n: a round head up right, a needle at 45 degrees from under it to the bottom-left corner."""
    img = np.zeros((n, n, 4), np.uint8)
    x, y = _grid(n, n)
    cx = int(n * 0.62) + 0.5  # (on a pixel's middle, and the needle's line x + y = n through pixels' middles)
    cy = n - cx
    r = n * 0.31
    # the needle: pixels on x + y = n (a second row on its shaded side when the pin is big), from the head to the tip
    d = x + y - n
    along = (x < cx) & (x >= 0.5 + (1 if n >= 16 else 0))
    width = 2 if n >= 24 else 1
    paint(img, along & (np.abs(d) < 0.01), NEEDLE[0])
    if width == 2:
        paint(img, along & (np.abs(d - 1) < 0.01), NEEDLE[1])
    # the head over its top
    face, shade, shine = PIN_HEAD_LIT if lit else PIN_HEAD
    head = (x - cx) ** 2 + (y - cy) ** 2 <= r * r
    paint(img, head, face)
    paint(img, head & ((x - cx) + (y - cy) > r * 0.55), shade)
    sr = max(0.75, r * 0.3)
    paint(img, head & ((x - (cx - r * 0.38)) ** 2 + (y - (cy - r * 0.38)) ** 2 <= sr * sr), shine)
    paint(img, edge(head), PIN_RIM)
    return img


ICONS = {
    "MouseLeft": lambda n: mouse(n, "left"),
    "MouseRight": lambda n: mouse(n, "right"),
    "MouseWheel": lambda n: mouse(n, "wheel"),
    "Shift": lambda n: key(n, "Shift"),
    "Ctrl": lambda n: key(n, "Ctrl"),
    "Pin": lambda n: pin(n),
    "PinLit": lambda n: pin(n, True),
}
for _d in range(STAIR_DIRS):
    ICONS[f"Stairs{_d}"] = (lambda d: lambda n: stairs(n, d))(_d)


def icon(name: str, n: int) -> np.ndarray:
    """The icon's drawing alone: n high, n (a keycap: WIDE times n) wide."""
    return ICONS[name](n)


def canvas_side(name: str, n: int) -> int:
    """The square power-of-two canvas the drawing sits in (its top-left corner)."""
    side, pot = WIDE.get(name, 1) * n, 1
    while pot < side:
        pot *= 2
    return pot


def on_canvas(name: str, n: int) -> np.ndarray:
    art = icon(name, n)
    side = canvas_side(name, n)
    out = np.zeros((side, side, 4), np.uint8)
    out[:art.shape[0], :art.shape[1]] = art
    return out


# The map editor's legend icons: the developer addon's own (its Media/Tools, private_paths.DEV_ADDON; the editor left
# AzerothGPS in 1.3.14), written there when that checkout is next to this one.
EDITOR_ICONS = ("MouseLeft", "MouseRight", "MouseWheel", "Shift", "Ctrl")


def editor_tools_dir() -> Path | None:
    """The dev addon's Media/Tools (private_paths.DEV_ADDON next to this repo), or None."""
    try:
        from .private_paths import DEV_ADDON
    except ImportError:
        return None
    return Path(__file__).resolve().parents[3].joinpath(*DEV_ADDON) / "Media" / "Tools"


def icon_file(name: str, n: int, tools_dir: Path | None = None) -> Path:
    if tools_dir is None and name in EDITOR_ICONS:
        tools_dir = editor_tools_dir()
    return (tools_dir or TOOLS_DIR) / f"{name}_{n}.tga"


def write(tools_dir: Path | None = None) -> list[Path]:
    """Every icon at every size (only files that changed rewritten; stale ones of ours removed). Returns the files."""
    tools_dir = tools_dir or TOOLS_DIR
    tools_dir.mkdir(parents=True, exist_ok=True)
    keep = []
    editor = editor_tools_dir()
    for name in ICONS:
        if name in EDITOR_ICONS and tools_dir == TOOLS_DIR:  # (the dev addon's, when it's checked out)
            if editor and editor.parent.is_dir():
                editor.mkdir(exist_ok=True)
                for n in ICON_PX:
                    f = icon_file(name, n, editor)
                    data = tga_rgba(on_canvas(name, n))
                    if not f.exists() or f.read_bytes() != data:
                        f.write_bytes(data)
            continue
        for n in ICON_PX:
            f = icon_file(name, n, tools_dir)
            data = tga_rgba(on_canvas(name, n))
            if not f.exists() or f.read_bytes() != data:
                f.write_bytes(data)
            keep.append(f)
    for f in tools_dir.glob("*.tga"):
        if f not in keep:
            f.unlink()
    return keep


def preview(out_dir: Path, scale: int = 8) -> list[Path]:
    """Each icon's drawing enlarged `scale` times on a dark ground (PNG), to look at."""
    from PIL import Image
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for n in ICON_PX:
        arts = [icon(name, n) for name in ICONS]
        w = sum(a.shape[1] for a in arts) + 2 * (len(arts) + 1)
        sheet = np.zeros((n + 4, w, 4), np.uint8)
        sheet[...] = (30, 30, 34, 255)
        x = 2
        for a in arts:
            sub = sheet[2:2 + n, x:x + a.shape[1]]
            on = a[..., 3] > 0
            sub[on] = a[on]
            x += a.shape[1] + 2
        img = Image.fromarray(sheet).resize((sheet.shape[1] * scale, sheet.shape[0] * scale), Image.NEAREST)
        p = out_dir / f"tools_{n}.png"
        img.save(p)
        files.append(p)
    return files
