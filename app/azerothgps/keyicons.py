"""The controller's on-screen keyboard's key caps (`agps keyicons`; Kooki3z 2026-11-20: "Keep keyboard themed with pixel
art buttons like the controller"). Our own, drawn from numbers alone, in the controller icons' plastic (padicons.py,
toolicons.py's keycaps): a dark cap with a lighter top face and a dark outline, and its lit state (the key the D-pad is
on) with a warm top and a gold rim. No letters on them: PadKeys.lua writes each key's letter over its cap as text, so
every layout (Latin, Cyrillic, Hangul) uses the same caps.

Caps (Media/Keyboard/<name>_<px>.tga): `Key` one key wide (square), `Key2` two wide (Delete, Done), `Key4` four wide
(Space), each with a `Lit` twin. Each drawn at each of ICON_PX pixels high, pixel for pixel (never scaled in the game:
the client's LINEAR filter blurs a shrunk one, and nothing above LINEAR may be asked, it crashes WoW Forever), in the
top-left corner of the smallest power-of-two canvas that holds it (each side its own power of two); PadKeys.lua picks
the size nearest the key's pixels on the screen and shows only the drawing (SetTexCoord). Keep in step with
PadKeys.lua's K.ART_PX / K.ART_WIDE."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .coast import tga_rgba
from .toolicons import KEY, KEY_TOP, LIT, OUTLINE, edge, paint, rrect

KEYS_DIR = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS" / "Media" / "Keyboard"
ICON_PX = (12, 14, 16, 18, 20, 24, 28, 32, 40)
WIDE = {"Key": 1, "Key2": 2, "Key4": 4}
KEY_TOP_LIT = (132, 104, 34)  # (the lit key's top: warm, so the white letter on it still reads)
KEY_LIT = (92, 70, 18)


def cap(n: int, wide: int, lit: bool) -> np.ndarray:
    """A key cap n high and `wide` * n wide: its body, its top face over a lip at the bottom, its outline."""
    w = wide * n
    img = np.zeros((n, w, 4), np.uint8)
    body = rrect(w, n, 0, 0, w, n, max(1.5, n / 6))
    paint(img, body, KEY_LIT if lit else KEY)
    lip = max(2, n // 6)
    top = rrect(w, n, 1, 1, w - 1, n - lip, max(1, n / 8))
    paint(img, top & body, KEY_TOP_LIT if lit else KEY_TOP)
    rim = edge(body)
    paint(img, rim, LIT if lit else OUTLINE)
    if lit and n >= 20:  # (big enough: the gold rim two pixels thick, so it reads as the one chosen)
        paint(img, edge(body & ~rim), LIT)
    return img


ICONS = {}
for _name, _wide in WIDE.items():
    ICONS[_name] = (lambda k: lambda n: cap(n, k, False))(_wide)
    ICONS[_name + "Lit"] = (lambda k: lambda n: cap(n, k, True))(_wide)


def wide(name: str) -> int:
    return WIDE[name[:-3] if name.endswith("Lit") else name]


def icon(name: str, n: int) -> np.ndarray:
    """The cap's drawing alone: n high, its width times n wide."""
    return ICONS[name](n)


def pot(v: int) -> int:
    p = 1
    while p < v:
        p *= 2
    return p


def canvas_size(name: str, n: int) -> tuple[int, int]:
    """The power-of-two canvas (width, height) the drawing sits in (its top-left corner)."""
    return pot(wide(name) * n), pot(n)


def on_canvas(name: str, n: int) -> np.ndarray:
    art = icon(name, n)
    cw, ch = canvas_size(name, n)
    out = np.zeros((ch, cw, 4), np.uint8)
    out[:art.shape[0], :art.shape[1]] = art
    return out


def icon_file(name: str, n: int, keys_dir: Path | None = None) -> Path:
    return (keys_dir or KEYS_DIR) / f"{name}_{n}.tga"


def write(keys_dir: Path | None = None) -> list[Path]:
    """Every cap at every size (only files that changed rewritten; stale ones of ours removed). Returns the files."""
    keys_dir = keys_dir or KEYS_DIR
    keys_dir.mkdir(parents=True, exist_ok=True)
    keep = []
    for name in ICONS:
        for n in ICON_PX:
            f = icon_file(name, n, keys_dir)
            data = tga_rgba(on_canvas(name, n))
            if not f.exists() or f.read_bytes() != data:
                f.write_bytes(data)
            keep.append(f)
    for f in keys_dir.glob("*.tga"):
        if f not in keep:
            f.unlink()
    return keep


def preview(out_dir: Path, scale: int = 8) -> list[Path]:
    """Each cap enlarged `scale` times on a dark ground (PNG), to look at."""
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
        p = out_dir / f"keys_{n}.png"
        img.save(p)
        files.append(p)
    return files
