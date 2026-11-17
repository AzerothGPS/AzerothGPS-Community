"""The controller's buttons as pixel-art icons, and Options > Controller's diagram (`agps padicons`; asked 2026-11-16:
"generate a set of pixel like controller icons to use on the map for controls instead of just using the letter" and
"lets convert the Controller option page to look something like this but more AzerothGPS options themed. Like
transparent background with gold controller drawn lines"). Our own: drawn from numbers alone, nothing of the game's.

Icons (Media/Pad/<name>_<px>.tga): each drawn at each of ICON_PX, pixel for pixel (no smoothing: crisp pixel art at
the size it's shown; the game's LINEAR filter shrinking a bigger one blurs it, and nothing above LINEAR is allowed);
Pad.lua's Pad.IconFile picks the size nearest the icon's pixels on the screen (Pad.ICON_UNITS UI units). The Xbox
set (A B X Y round in their colors, LB RB bumpers, LT RT triggers, the sticks and their press, the D-pad and each
direction lit, View and Menu) and the PlayStation shapes (Cross Circle Square Triangle, L1 R1 L2 R2) for a pad whose
labels are shapes.

The diagram (Media/Pad/Diagram_<s>.tga): the controller drawn in the options' gold lines on a clear background, a
leader line from each button out to the left or right edge at its label's row (DIAGRAM_LEFT / DIAGRAM_RIGHT, rows
DIAGRAM_ROW0 + i * DIAGRAM_ROW_STEP); drawn at each of DIAGRAM_SCALES pixels a unit (DIAGRAM_W x DIAGRAM_H units),
Options shows the one nearest its pixels a UI unit, 1:1. Keep in step with Pad.lua's Pad.ICON_PX / Pad.DIAGRAM."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .coast import tga_rgba

PAD_DIR = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS" / "Media" / "Pad"
ICON_PX = (12, 14, 16, 18, 20, 24, 28, 32, 40)

# ---------------------------------------------------------------- the pixel font (3 x 5 and 5 x 7)
FONT3 = {
    "A": (".#.", "#.#", "###", "#.#", "#.#"), "B": ("##.", "#.#", "##.", "#.#", "##."),
    "X": ("#.#", "#.#", ".#.", "#.#", "#.#"), "Y": ("#.#", "#.#", ".#.", ".#.", ".#."),
    "L": ("#..", "#..", "#..", "#..", "###"), "R": ("##.", "#.#", "##.", "#.#", "#.#"),
    "T": ("###", ".#.", ".#.", ".#.", ".#."), "1": (".#.", "##.", ".#.", ".#.", "###"),
    "2": ("##.", "..#", ".#.", "#..", "###"), "3": ("##.", "..#", ".#.", "..#", "##."),
}
FONT5 = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "X": ("#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": ("####.", "....#", "....#", ".###.", "....#", "....#", "####."),
}


def text_mask(text: str, max_w: int, max_h: int) -> np.ndarray:
    """`text` in the pixel font, the biggest that fits max_w x max_h (each glyph scaled by a whole number, 1 px
    apart at scale 1): a bool array."""
    best = None
    for font, gw, gh in ((FONT3, 3, 5), (FONT5, 5, 7)):
        for k in (1, 2, 3, 4):
            w = (len(text) * gw + (len(text) - 1)) * k
            h = gh * k
            if w <= max_w and h <= max_h and (best is None or h > best[3] or (h == best[3] and gw > best[1])):
                best = (font, gw, gh, h, k)
    font, gw, gh, _, k = best or (FONT3, 3, 5, 5, 1)
    cols = []
    for i, ch in enumerate(text):
        g = np.array([[c == "#" for c in row] for row in font[ch]], bool)
        if i:
            cols.append(np.zeros((gh, 1), bool))
        cols.append(g)
    m = np.concatenate(cols, axis=1)
    return np.kron(m, np.ones((k, k), bool)).astype(bool)


# ---------------------------------------------------------------- shapes on an n x n pixel grid
def _grid(n):
    c = np.arange(n) + 0.5
    return c[None, :], c[:, None]  # (x, y) at each pixel's middle


def disc(n, cx, cy, r):
    x, y = _grid(n)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def rrect(n, x0, y0, x1, y1, r):
    """A rounded rectangle [x0, x1) x [y0, y1) (pixel edges), its corners' radius r."""
    x, y = _grid(n)
    inside = (x >= x0) & (x < x1) & (y >= y0) & (y < y1)
    qx = np.clip(x, x0 + r, x1 - r)
    qy = np.clip(y, y0 + r, y1 - r)
    return inside & ((x - qx) ** 2 + (y - qy) ** 2 <= r * r)


def edge(mask):
    """The outer pixels of `mask` (in it, next to a pixel out of it): its outline."""
    p = np.pad(mask, 1)
    inner = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    return mask & ~inner


def grow(mask):
    p = np.pad(mask, 1)
    return p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]


def paint(img, mask, rgb, a=255):
    img[mask] = (*rgb, a)


def place(img, m, cx=None, cy=None, rgb=(255, 255, 255)):
    """Glyph mask `m` centered on the pixel grid at (cx, cy) (default the middle)."""
    n = img.shape[0]
    h, w = m.shape
    x0 = int(round((n if cx is None else 2 * cx) / 2 - w / 2))
    y0 = int(round((n if cy is None else 2 * cy) / 2 - h / 2))
    sub = img[y0:y0 + h, x0:x0 + w]
    sub[m[:sub.shape[0], :sub.shape[1]]] = (*rgb, 255)


OUTLINE = (12, 10, 8)  # every icon edged in near-black: readable on the map's light and dark ground
BODY = (58, 58, 64)  # the pad's plastic: the bumpers, triggers, sticks, D-pad, View / Menu
BODY_HI = (92, 92, 100)
LIT = (255, 209, 0)  # the options' gold: a D-pad direction lit, a stick's press ring
XBOX = {"A": (88, 178, 52), "B": (214, 52, 44), "X": (36, 112, 214), "Y": (236, 186, 20)}
PS = {"Cross": (122, 170, 236), "Circle": (240, 96, 96), "Square": (226, 132, 196), "Triangle": (64, 210, 150)}


def _round_button(n, fill):
    img = np.zeros((n, n, 4), np.uint8)
    r = n / 2
    body = disc(n, r, r, r - 0.3)
    paint(img, body, fill)
    hi = disc(n, r, r - max(1, n // 10), r - max(1.5, n / 7)) & ~disc(n, r, r + max(1, n // 12), r - max(1.5, n / 7))
    paint(img, hi & body, tuple(min(255, c + 40) for c in fill))  # (a lighter rim along its top)
    paint(img, edge(body), OUTLINE)
    return img, body


def face(n, letter):
    img, body = _round_button(n, XBOX[letter])
    m = text_mask(letter, int(n * 0.62), int(n * 0.58))
    place(img, m, rgb=(40, 30, 0) if letter == "Y" else (255, 255, 255))
    return img


def ps_face(n, shape):
    img, body = _round_button(n, (40, 40, 46))
    col = PS[shape]
    c = n / 2
    s = n * 0.27  # the symbol's half size
    t = max(1.0, n / 11)  # its line
    x, y = _grid(n)
    if shape == "Cross":
        d1 = np.abs((x - c) - (y - c)) / np.sqrt(2)
        d2 = np.abs((x - c) + (y - c)) / np.sqrt(2)
        m = ((d1 <= t * 0.75) | (d2 <= t * 0.75)) & (np.abs(x - c) <= s) & (np.abs(y - c) <= s)
    elif shape == "Circle":
        d = np.hypot(x - c, y - c)
        m = np.abs(d - s) <= t * 0.6
    elif shape == "Square":
        m = (np.maximum(np.abs(x - c), np.abs(y - c)) <= s) & (np.maximum(np.abs(x - c), np.abs(y - c)) > s - t)
    else:  # Triangle
        top, bot = c - s * 1.05, c + s * 0.8
        h = bot - top
        half = (y - top) / h * s * 1.1
        inside = (y >= top) & (y <= bot) & (np.abs(x - c) <= half)
        ih = (y >= top + t * 1.9) & (y <= bot - t) & (np.abs(x - c) <= half - t * 1.25)
        m = inside & ~ih
    paint(img, m & body, col)
    return img


def bumper(n, text):
    """LB / RB (L1 / R1): a wide rounded bar."""
    img = np.zeros((n, n, 4), np.uint8)
    h = max(7, round(n * 0.62))
    y0 = (n - h) // 2
    body = rrect(n, 0, y0, n, y0 + h, max(1.5, h * 0.3))
    paint(img, body, BODY)
    paint(img, rrect(n, 1, y0 + 1, n - 1, y0 + 2 + n // 16, 0) & body, BODY_HI)
    paint(img, edge(body), OUTLINE)
    place(img, text_mask(text, n - 4, h - 2), cy=y0 + h / 2)
    return img


def trigger(n, text):
    """LT / RT (L2 / R2): a trigger, rounded big on top, square at its foot."""
    img = np.zeros((n, n, 4), np.uint8)
    w = max(9, round(n * 0.84))
    x0 = (n - w) // 2
    top = rrect(n, x0, 0, x0 + w, n, max(2.5, w * 0.42))
    foot = rrect(n, x0, n // 2, x0 + w, n, max(1, n / 12))
    body = top | foot
    paint(img, body, BODY)
    paint(img, rrect(n, x0 + 1, 1, x0 + w - 1, 2 + n // 16, w * 0.4) & body, BODY_HI)
    paint(img, edge(body), OUTLINE)
    place(img, text_mask(text, w - 4, n - 4), cy=n / 2 + n / 14)
    return img


def stick(n, text, press):
    """A stick from above, its letter in the middle; pressed: a gold ring around it."""
    img = np.zeros((n, n, 4), np.uint8)
    c = n / 2
    outer = disc(n, c, c, c - 0.3)
    g = max(1, round(n / 12))  # (the press ring's gold, inside its dark edge)
    r = c - g - 1.3 if press else c - 0.3
    cap = disc(n, c, c, r)
    if press:
        paint(img, outer, LIT)
        paint(img, edge(outer), OUTLINE)
    paint(img, cap, BODY)
    paint(img, cap & ~disc(n, c, c, r - max(1, n / 9)), BODY_HI)  # (its grippy rim)
    paint(img, edge(cap), OUTLINE)
    place(img, text_mask(text, int(r * 1.2), int(r * 1.1)))
    return img


def dpad(n, lit=None):
    """The D-pad's cross, the direction `lit` ("Up", "Down", "Left", "Right") in gold."""
    img = np.zeros((n, n, 4), np.uint8)
    a = max(3, round(n * 0.36))
    if (n - a) % 2:
        a += 1
    o = (n - a) // 2
    vert = rrect(n, o, 0, o + a, n, max(1, n / 14))
    horz = rrect(n, 0, o, n, o + a, max(1, n / 14))
    body = vert | horz
    paint(img, body, BODY)
    if lit:
        arm = {"Up": (o, 0, o + a, o), "Down": (o, o + a, o + a, n), "Left": (0, o, o, o + a),
               "Right": (o + a, o, n, o + a)}[lit]
        paint(img, rrect(n, *arm, 0) & body, LIT)
    paint(img, edge(body), OUTLINE)
    if not lit and n >= 16:  # (the middle's dimple)
        paint(img, disc(n, n / 2, n / 2, max(1, n / 12)), BODY_HI)
    return img


def small_button(n, kind):
    """View (Back: two squares) and Menu (Start: three lines), on a small dark round button."""
    img = np.zeros((n, n, 4), np.uint8)
    c = n / 2
    body = disc(n, c, c, c - 0.3)
    paint(img, body, BODY)
    paint(img, edge(body), OUTLINE)
    t = max(1, round(n / 14))
    if kind == "Menu":
        w = max(4, round(n * 0.44))
        if (n - w) % 2:
            w += 1
        x0 = (n - w) // 2
        gap = max(2, round(n / 6))
        y0 = round(c - gap - t / 2)
        for i in range(3):
            img[y0 + i * gap:y0 + i * gap + t, x0:x0 + w] = (255, 255, 255, 255)
    else:
        s = max(4, round(n * 0.32))
        off = max(1, round(n / 10))
        bx, by = round(c - s / 2 - off / 2), round(c - s / 2 - off / 2)
        back = rrect(n, bx, by, bx + s, by + s, 0)
        front = rrect(n, bx + off, by + off, bx + off + s, by + off + s, 0)
        paint(img, edge(back) & ~front, (200, 200, 205))
        paint(img, front, BODY)
        paint(img, edge(front), (255, 255, 255))
    return img


# the icons: name -> drawing; Pad.lua's Pad.ICONS maps the pad's keys to these names
ICONS = {
    "A": lambda n: face(n, "A"), "B": lambda n: face(n, "B"), "X": lambda n: face(n, "X"), "Y": lambda n: face(n, "Y"),
    "LB": lambda n: bumper(n, "LB"), "RB": lambda n: bumper(n, "RB"),
    "LT": lambda n: trigger(n, "LT"), "RT": lambda n: trigger(n, "RT"),
    "LStick": lambda n: stick(n, "L", False), "RStick": lambda n: stick(n, "R", False),
    "LStickPress": lambda n: stick(n, "L", True), "RStickPress": lambda n: stick(n, "R", True),
    "DPad": lambda n: dpad(n), "DPadUp": lambda n: dpad(n, "Up"), "DPadDown": lambda n: dpad(n, "Down"),
    "DPadLeft": lambda n: dpad(n, "Left"), "DPadRight": lambda n: dpad(n, "Right"),
    "View": lambda n: small_button(n, "View"), "Menu": lambda n: small_button(n, "Menu"),
    "Cross": lambda n: ps_face(n, "Cross"), "Circle": lambda n: ps_face(n, "Circle"),
    "Square": lambda n: ps_face(n, "Square"), "Triangle": lambda n: ps_face(n, "Triangle"),
    "L1": lambda n: bumper(n, "L1"), "R1": lambda n: bumper(n, "R1"),
    "L2": lambda n: trigger(n, "L2"), "R2": lambda n: trigger(n, "R2"),
}


def icon(name: str, n: int) -> np.ndarray:
    return ICONS[name](n)


def icon_file(name: str, n: int) -> Path:
    return PAD_DIR / f"{name}_{n}.tga"


# ---------------------------------------------------------------- the options' diagram
DIAGRAM_W, DIAGRAM_H = 200, 186  # units (Options shows it 1:1: DIAGRAM_W * s / pixels a unit)
DIAGRAM_SCALES = (1, 1.5, 2, 2.5, 3)  # pixels a unit drawn
DIAGRAM_ROW0, DIAGRAM_ROW_STEP = 14, 22  # its labels' rows (units from its top)
GOLD = (255, 209, 0)  # the options' headers (GameFontNormal's 1, 0.82, 0)
LINE_UNITS = 1.0
SS = 4  # (each pixel sampled SS x SS times)

# the buttons on each side, top to bottom (their labels' rows), each with its leader line: the button's point, then the
# line's bends; it ends at the edge, at its row (Pad.DIAGRAM's left / right: the same keys in the same order)
DIAGRAM_LEFT = (
    ("PADLTRIGGER", [(64, 38), (44, 14)]),
    ("PADLSHOULDER", [(56, 69), (40, 36)]),
    ("PADBACK", [(90.1, 88.9), (88, 58)]),
    ("PADLSTICK", [(55.8, 91.4), (44, 80)]),
    ("PADDUP", [(80.9, 104.2), (76, 102)]),
    ("PADDLEFT", [(70.6, 114.5), (62, 124)]),
    ("PADDDOWN", [(80.9, 124.8), (72, 146)]),
    ("PADDRIGHT", [(91.2, 114.5), (96, 120), (96, 168)]),
)
DIAGRAM_RIGHT = (
    ("PADRTRIGGER", [(136, 38), (156, 14)]),
    ("PADRSHOULDER", [(144, 69), (160, 36)]),
    ("PADFORWARD", [(110.1, 88.9), (112, 58)]),
    ("PAD4", [(141.4, 82.9), (156, 80)]),
    ("PAD2", [(151.4, 92.4), (160, 102)]),
    ("PAD1", [(136.6, 107.2), (144, 124)]),
    ("PAD3", [(129.2, 96.6), (132, 146)]),
    ("PADRSTICK", [(118.4, 122.5), (118.4, 168)]),
)

# The controller's lines, traced from the picture the player gave (asked 2026-11-16: "use this literal image for the
# controller outline"), in units: the body's outline (closed; the bumpers are its two humps), and the lines inside it
# at the top (the bumpers' lower edges, the middle's dip). Its parts below sit where the picture has them.
OUTLINE_BODY = [(49.7, 73.9), (49, 74.7), (46.5, 77.1), (45.8, 78), (44.9, 79.5), (42.2, 85.5), (39.3, 93), (35.8, 103.5), (32.2, 115.5), (30.5, 123.5), (30.1, 126.5), (29.4, 129.5), (29.1, 134), (28.5, 138), (28.4, 139.5), (28.7, 142), (29.4, 145), (29.9, 146.5), (30.9, 148.5), (32.5, 151), (34.8, 153.4), (37.3, 155.4), (39.8, 156.7), (41.8, 157.2), (43.2, 157.1), (44.2, 156.8), (45.2, 156.3), (46.2, 155.7), (47.8, 154.4), (55.2, 147.1), (62.8, 140.1), (66.2, 137.2), (68.8, 135.7), (71.8, 134.3), (75.2, 133.4), (78.2, 133), (82.2, 133), (86.3, 133.3), (89.8, 133), (93.2, 133), (98.2, 133.3), (101.8, 133), (105.2, 133), (111.3, 133.5), (116.2, 133.1), (119.8, 133.4), (124.2, 133.4), (126.8, 133.9), (128.8, 134.6), (130.8, 135.6), (132.8, 136.9), (134.8, 138.4), (141.2, 144.1), (151.2, 153.8), (154.2, 156.2), (155.2, 156.7), (156.2, 157.1), (157.3, 157.2), (158.8, 157), (160.3, 156.5), (162.2, 155.5), (164.2, 154.1), (165.6, 152.8), (166.8, 151.5), (167.9, 150), (169.3, 147.5), (169.8, 146), (170.2, 144.5), (170.7, 141.5), (170.7, 137.5), (170.2, 131), (169.6, 127.5), (168.1, 119.5), (166.9, 114.5), (165, 107.5), (163, 101), (158.6, 88.5), (156, 82), (154.8, 79.5), (153.9, 78), (150.5, 74.2), (148.3, 70.6), (147.6, 69.7), (146.7, 69), (144.2, 67.7), (138.2, 65.1), (135.8, 64.3), (132.8, 63.5), (130.2, 63.1), (127.2, 63), (125.2, 63.2), (123.8, 63.7), (119.8, 65.6), (118.8, 65.9), (117.2, 66), (83.1, 66), (81.3, 65.8), (79.5, 65.3), (75.8, 63.6), (74.2, 63.2), (72.8, 63), (70.2, 63), (67.8, 63.3), (63.2, 64.5), (58.8, 66.2), (55.3, 67.8), (52.8, 69.2), (51.6, 70.2), (50.7, 71.5)]
OUTLINE_INNER = (
    [(50.8, 74), (51.8, 73.7), (55.2, 72.2), (60.2, 70.3), (64.2, 69.2), (69.8, 68.1), (71.3, 68.3), (72.8, 68.9), (73.7, 69.6), (76.2, 71.8), (77.2, 72.5)],
    [(77.8, 72.5), (79.3, 70.5), (80.6, 68), (81.2, 66.5)],
    [(121.8, 73.5), (120.7, 75), (117.8, 78), (115.2, 81), (113.7, 82.3), (112.3, 83), (110.8, 83.4), (109.3, 83.5), (90.8, 83.5), (89.3, 83.4), (87.3, 83), (85.8, 82.3), (84.9, 81.5), (83.2, 79.5), (79.9, 76), (78.4, 74.1), (77.8, 73)],
    [(118.2, 66.5), (118.9, 68), (120.5, 71), (121.8, 72.5)],
    [(148.8, 74), (142.8, 71.4), (140.2, 70.5), (136.8, 69.7), (132.8, 68.6), (130.3, 68.1), (129.2, 68.1), (128.3, 68.3), (126.8, 68.9), (125.3, 70.1), (122.2, 73)],
)
DIAGRAM_STICKS = ((64.3, 91.4), (118.4, 114.0))  # (the rings: 8.5 and 5 units)
DIAGRAM_DPAD = (80.9, 114.5, 3.4, 10.3)  # middle, an arm's half width and length
DIAGRAM_SMALL = ((90.1, 91.9, 3), (110.1, 91.9, 3), (100.1, 75.2, 6.5))  # View, Menu, the middle button
DIAGRAM_FACE = ((136.6, 82.9), (126.8, 92.4), (146.6, 92.4), (136.6, 102.2))  # Y, X, B, A (5 units)


def diagram(s: float) -> np.ndarray:
    """The diagram at `s` pixels a unit: (h, w, 4) uint8, gold lines (anti-aliased curves, straight runs on whole
    pixels) on clear."""
    w, h = round(DIAGRAM_W * s), round(DIAGRAM_H * s)
    lw = max(1, round(LINE_UNITS * s))  # the line, whole pixels
    half = lw / 2
    S = SS * 1.0
    cov = Image.new("L", (w * SS, h * SS), 0)
    fill = Image.new("L", (w * SS, h * SS), 0)
    d, df = ImageDraw.Draw(cov), ImageDraw.Draw(fill)

    def snap(v):  # a line's middle on the pixel grid (odd widths: a pixel's middle)
        return (round(v * s - (lw % 2) / 2) + (lw % 2) / 2) * S

    def P(pt):
        return snap(pt[0]), snap(pt[1])

    def seg(a, b):
        (x0, y0), (x1, y1) = P(a), P(b)
        r = half * S
        if abs(y0 - y1) < 1e-6 or abs(x0 - x1) < 1e-6:  # (straight across or down: a rectangle, crisp)
            d.rectangle([min(x0, x1) - r, min(y0, y1) - r, max(x0, x1) + r - 1, max(y0, y1) + r - 1], fill=255)
        else:
            v = np.array([x1 - x0, y1 - y0])
            nrm = np.array([-v[1], v[0]]) / np.hypot(*v) * r
            quad = [(x0 + nrm[0], y0 + nrm[1]), (x1 + nrm[0], y1 + nrm[1]), (x1 - nrm[0], y1 - nrm[1]),
                    (x0 - nrm[0], y0 - nrm[1])]
            d.polygon(quad, fill=255)
            for x, y in ((x0, y0), (x1, y1)):
                d.ellipse([x - r, y - r, x + r, y + r], fill=255)

    def curve(pts, closed=True):
        pp = [(x * s * S, y * s * S) for x, y in pts]
        if closed:
            pp.append(pp[0])
        d.line(pp, fill=255, width=max(1, round(lw * S)), joint="curve")

    def ring(cx, cy, r):
        cx, cy, r = cx * s * S, cy * s * S, r * s * S
        o, i = r + half * S, r - half * S
        d.ellipse([cx - o, cy - o, cx + o, cy + o], fill=255)
        d.ellipse([cx - i, cy - i, cx + i, cy + i], fill=0)

    def ring_fill(cx, cy, r):
        cx, cy, r = cx * s * S, cy * s * S, r * s * S
        df.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)

    df.polygon([(x * s * S, y * s * S) for x, y in OUTLINE_BODY], fill=255)
    curve(OUTLINE_BODY)
    for pts in OUTLINE_INNER:
        curve(pts, closed=False)
    for m in (1, -1):  # the triggers, over the bumpers
        def X(x):
            return x if m == 1 else 200 - x
        curve([(X(55), 56), (X(55), 44), (X(58), 39), (X(64), 37), (X(70), 39), (X(73), 44), (X(73), 56)])
    for cx, cy in DIAGRAM_STICKS:
        ring(cx, cy, 8.5)
        ring(cx, cy, 5)
        ring_fill(cx, cy, 8.5)
    cx, cy, a, L = DIAGRAM_DPAD
    cross = [(cx - a, cy - L), (cx + a, cy - L), (cx + a, cy - a), (cx + L, cy - a), (cx + L, cy + a), (cx + a, cy + a),
             (cx + a, cy + L), (cx - a, cy + L), (cx - a, cy + a), (cx - L, cy + a), (cx - L, cy - a),
             (cx - a, cy - a)]
    for i in range(len(cross)):
        seg(cross[i], cross[(i + 1) % len(cross)])
    for cx, cy, r in DIAGRAM_SMALL:
        ring(cx, cy, r)
    for cx, cy in DIAGRAM_FACE:
        ring(cx, cy, 5)
        ring_fill(cx, cy, 5)
    # the leader lines: from each button, by its bends, out to its edge at its row
    for side, rows, edge_x in ((0, DIAGRAM_LEFT, 0), (1, DIAGRAM_RIGHT, DIAGRAM_W)):
        for i, (_key, pts) in enumerate(rows):
            y = DIAGRAM_ROW0 + i * DIAGRAM_ROW_STEP
            path = list(pts)
            if path[-1][1] != y:
                path.append((path[-1][0], y))
            path.append((edge_x, y))
            for p, q in zip(path, path[1:]):
                seg(p, q)
            bx, by = pts[0]
            r = 1.6
            d.ellipse([(bx * s - r * s) * S, (by * s - r * s) * S, (bx * s + r * s) * S, (by * s + r * s) * S], fill=255)
    line = np.asarray(cov.resize((w, h), Image.BOX), float) / 255
    tint = np.asarray(fill.resize((w, h), Image.BOX), float) / 255 * 0.10  # (the body and buttons faintly gold)
    a = np.clip(line + tint * (1 - line), 0, 1)
    out = np.zeros((h, w, 4), np.uint8)
    out[..., :3] = GOLD
    out[..., 3] = np.round(a * 255).astype(np.uint8)
    return out


def diagram_file(s: float) -> Path:
    return PAD_DIR / f"Diagram_{int(round(s * 10))}.tga"


def row_y(i: int) -> float:
    return DIAGRAM_ROW0 + i * DIAGRAM_ROW_STEP


# ---------------------------------------------------------------- writing
def write(pad_dir: Path | None = None) -> list[Path]:
    """Every icon at every size, and the diagram at every scale (only files that changed rewritten; stale ones of
    ours removed). Returns the files."""
    pad_dir = pad_dir or PAD_DIR
    pad_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for name in ICONS:
        for n in ICON_PX:
            out.append((pad_dir / f"{name}_{n}.tga", tga_rgba(icon(name, n))))
    for s in DIAGRAM_SCALES:
        out.append((pad_dir / diagram_file(s).name, tga_rgba(diagram(s))))
    keep = set()
    for f, data in out:
        keep.add(f.name)
        if not f.exists() or f.read_bytes() != data:
            f.write_bytes(data)
    for f in pad_dir.glob("*.tga"):
        if f.name not in keep:
            f.unlink()
    return [f for f, _ in out]


def preview(out_dir: Path, labels: dict | None = None) -> list[Path]:
    """Pictures to look at (not shipped): the icon sheet (every icon at every size, and 4x bigger), and the diagram on
    the options' dark at 1x and 2x with sample labels."""
    from PIL import ImageFont

    out_dir.mkdir(parents=True, exist_ok=True)
    bg = (24, 20, 16, 255)
    names = list(ICONS)
    cell = max(ICON_PX) + 8
    sheet = Image.new("RGBA", (110 + cell * len(ICON_PX), 8 + cell * len(names)), bg)
    try:
        font = ImageFont.truetype("arial.ttf", 12)
    except OSError:
        font = ImageFont.load_default()
    dr = ImageDraw.Draw(sheet)
    for r, name in enumerate(names):
        dr.text((6, 8 + r * cell + cell // 2 - 8), name, fill=(255, 209, 0), font=font)
        for c, n in enumerate(ICON_PX):
            im = Image.fromarray(icon(name, n), "RGBA")
            sheet.alpha_composite(im, (110 + c * cell + (cell - n) // 2, 8 + r * cell + (cell - n) // 2))
    p1 = out_dir / "pad-icons-sheet.png"
    sheet.save(p1)
    big = sheet.resize((sheet.width * 3, sheet.height * 3), Image.NEAREST)
    p2 = out_dir / "pad-icons-sheet-3x.png"
    big.save(p2)
    out = [p1, p2]
    labels = labels or {}
    for s in (1, 2):
        dg = Image.fromarray(diagram(s), "RGBA")
        page_w = round(400 * s)
        im = Image.new("RGBA", (page_w + round(20 * s), dg.height + round(20 * s)), bg)
        x0 = (im.width - dg.width) // 2
        y0 = round(10 * s)
        im.alpha_composite(dg, (x0, y0))
        try:
            f2 = ImageFont.truetype("arialbd.ttf", round(10 * s))
        except OSError:
            f2 = font
        dr = ImageDraw.Draw(im)
        isz = 14 if s == 1 else 28
        for side, rows in ((0, DIAGRAM_LEFT), (1, DIAGRAM_RIGHT)):
            for i, (key, _) in enumerate(rows):
                text = labels.get(key)
                if not text:
                    continue
                icon_name, words = text
                y = y0 + round(row_y(i) * s)
                ic = Image.fromarray(icon(icon_name, isz), "RGBA") if icon_name else None
                tw = dr.textlength(words, font=f2)
                if side == 0:
                    right = x0 - round(4 * s)
                    dr.text((right - tw, y), words, fill=(255, 255, 255), font=f2, anchor="lm")
                    if ic:
                        im.alpha_composite(ic, (int(right - tw - isz - 3 * s), y - isz // 2))
                else:
                    left = x0 + dg.width + round(4 * s)
                    if ic:
                        im.alpha_composite(ic, (left, y - isz // 2))
                        left += isz + round(3 * s)
                    dr.text((left, y), words, fill=(255, 255, 255), font=f2, anchor="lm")
        p = out_dir / f"pad-diagram-{s}x.png"
        im.save(p)
        out.append(p)
    return out
