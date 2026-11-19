"""The coastline masks for the seamless map's edge blend (issue #73): addon/AzerothGPS/Data/Coast.lua and
addon/AzerothGPS/Media/Coast/*.tga.

In the terrain view zoomed out, the seamless map's world art shows where the terrain has no tile (#62). The tiles'
own sea pixels stayed dark, and the art came in only past the tiles' square edges. Here the terrain's sea is worked out
from the shipped passability grid (Data/Terrain.lua: water cells, 8.33 yd) and the minimap tiles there are
(Data/Minimap.lua): the sea is the open water joined to where there's no terrain at all (rivers, narrow inlets and the
lakes inland are land: narrower than OPEN_YD, or joined to no tile-less cell), and the void itself. Each minimap tile
gets an alpha mask of MASK_PX x MASK_PX: 1 on land, fading over FEATHER_YD out into the sea (a smoothstep by the
distance from the shore), 0 past it. In game (GPSFrame's G.LayoutMinimap) a coastal tile, and the dark mask under it,
are drawn through its mask, so the art shows in its sea right up to the shore; a tile all sea isn't drawn at all.

The masks are our own: white, only their alpha varies, made from the generated grid's numbers (no game art in them;
test_coast.py checks they're white). Data/Coast.lua: ns.Coast[cont][tx * 64 + ty] = 0 (all sea: not drawn) or, for a
coastal tile (its mask Media/Coast/<cont>_<tx>_<ty>.tga), the box of its pixels not all land (`sea_box`: x0, y0, x1, y1
in its 64 px, packed as code(); the map's edge blend turns on only with that box in view); tiles all land aren't
listed.

`--write` also writes Media/Feather.tga (feather(): the interiors' edge blend's soft square, issue #85).

`agps coast` reports; `--write` writes both; `--render X Y R [--cont N]` a picture of the masks there.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

import numpy as np

from .paths import ADDON_DIR
from .roads.terrain import decode_row

FILE = ADDON_DIR / "Data" / "Coast.lua"
MEDIA = ADDON_DIR / "Media" / "Coast"
TILE = 1600 / 3
FEATHER_YD = 60.0  # yards from the shore out into the sea over which the terrain fades out (GPSFrame's EDGE_FEATHER_YD)
OPEN_YD = 50.0  # water narrower than about this is a river or an inlet, the land's (an opening of this diameter)
STEEP_REACH_YD = 200.0  # a steep cell is judged by the open cells this far round it ...
STEEP_WATER_SHARE = 0.85  # ... the sea's when this share of them is water
ISLE_MIN_CELLS = 150  # land out in the sea smaller than this many cells (about 100 yd across) is the sea's
MASK_PX = 64  # a mask's side: one pixel a grid cell (8.33 yd)
LAND_MIN = 254  # a tile whose mask is this or more everywhere is all land (no mask)
SEA_MAX = 1  # ... this or less everywhere, all sea (not drawn)


def grids(path: Path | None = None) -> dict:
    """Data/Terrain.lua's grids: cont -> (tx0, ty0, cells (h, w) uint8; row = south, col = east)."""
    text = (path or ADDON_DIR / "Data" / "Terrain.lua").read_text(encoding="utf-8")
    text = text[:text.find("ns.Hills")]
    out = {}
    for m in re.finditer(r"^  \[(\d+)\] = \{ tx0 = (-?\d+), ty0 = (-?\d+), cell = [\d.]+, w = (\d+), h = (\d+), "
                         r"(?:deep = (\d+), )?rows = \{\n(.*?)\n  \} \},", text, re.S | re.M):
        w, h = int(m.group(4)), int(m.group(5))
        rows = [decode_row(r.strip().strip('",')) for r in m.group(7).splitlines()]
        cells = np.array(rows, np.uint8)
        if m.group(6):  # (deep water far out, closed for routes: the sea's here, water)
            cells[cells == int(m.group(6))] = 1
        assert cells.shape == (h, w), (m.group(1), cells.shape)
        out[int(m.group(1))] = (int(m.group(2)), int(m.group(3)), cells)
    return out


def minimap_tiles(path: Path | None = None) -> dict:
    """Data/Minimap.lua's tiles: cont -> set of tx * 64 + ty."""
    text = (path or ADDON_DIR / "Data" / "Minimap.lua").read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"^  \[(\d+)\] = \{(.*?)\}", text, re.S | re.M):
        out[int(m.group(1))] = {int(k) for k in re.findall(r"\[(\d+)\]\s*=", m.group(2))}
    return out


def has_tile(tx0: int, ty0: int, shape, tiles: set) -> np.ndarray:
    """(h, w) bool: the cells in a minimap tile."""
    h, w = shape
    nty, ntx = -(-h // MASK_PX), -(-w // MASK_PX)
    t = np.zeros((nty, ntx), bool)
    for k in tiles:
        tx, ty = divmod(k, 64)
        if 0 <= tx - tx0 < ntx and 0 <= ty - ty0 < nty:
            t[ty - ty0, tx - tx0] = True
    return np.repeat(np.repeat(t, MASK_PX, 0), MASK_PX, 1)[:h, :w]


def underwater(cells: np.ndarray) -> np.ndarray:
    """(h, w) bool: the water cells, and the steep (2) ones out in it. The grid marks a slope steep under water too
    (the seabed's ridges off Westfall, 200 yd wide, cut its coast off the open sea): a steep cell whose open cells
    round it (STEEP_REACH_YD) are nearly all water (STEEP_WATER_SHARE) is the sea's; a cliff on the shore, with land
    behind it, isn't."""
    from scipy import ndimage

    water = cells == 1
    steep = cells == 2
    n = 2 * int(round(STEEP_REACH_YD / (TILE / MASK_PX))) + 1
    w = ndimage.uniform_filter(water.astype(np.float32), n, mode="constant")
    land = ndimage.uniform_filter((cells == 0).astype(np.float32), n, mode="constant")
    share = w / np.maximum(w + land, 1e-6)
    return water | (steep & (w + land > 0.5 / (n * n)) & (share >= STEEP_WATER_SHARE))


def sea(cells: np.ndarray, tiled: np.ndarray) -> np.ndarray:
    """(h, w) bool: the sea, the open water joined to the void (no tile), and the void."""
    from scipy import ndimage

    # (past the grid's edge is no terrain either: an isle's sea, Zephras's; a cell of it round the grid)
    cells = np.pad(cells, 1, constant_values=1)
    void = ~np.pad(tiled, 1, constant_values=False)
    water = underwater(cells)
    r = max(1, int(round(OPEN_YD / 2 / (TILE / MASK_PX))))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    wide = ndimage.binary_opening(water, structure=xx * xx + yy * yy <= r * r)
    lab, n = ndimage.label(wide | void)
    if not n:
        return void[1:-1, 1:-1]
    keep = np.zeros(n + 1, bool)
    keep[np.unique(lab[void])] = True
    keep[0] = False
    out = keep[lab] | void
    # specks of land out in it (rocks, the seabed's steep bits the share left) are the sea's
    lab, n = ndimage.label(~out)
    if n:
        sizes = np.bincount(lab.ravel())
        small = sizes < ISLE_MIN_CELLS
        small[0] = False
        out |= small[lab]
    return out[1:-1, 1:-1]


def alpha(sea_: np.ndarray, cell: float = TILE / MASK_PX) -> np.ndarray:
    """(h, w) uint8: 255 on land, fading over FEATHER_YD into the sea (smoothstep), 0 past it."""
    from scipy import ndimage

    d = ndimage.distance_transform_edt(sea_) * cell  # (a sea cell's centre to the nearest land cell's)
    t = np.clip((d - cell / 2) / FEATHER_YD, 0, 1)
    a = 1 - t * t * (3 - 2 * t)
    return np.round(a * 255).astype(np.uint8)


def tile_masks(tx0: int, ty0: int, cells: np.ndarray, tiles: set) -> dict:
    """Each minimap tile's mask: key -> 0 (all sea), or a (MASK_PX, MASK_PX) uint8 array (row = south); all land left
    out."""
    a = alpha(sea(cells, has_tile(tx0, ty0, cells.shape, tiles)))
    out = {}
    for k in sorted(tiles):
        tx, ty = divmod(k, 64)
        r, c = (ty - ty0) * MASK_PX, (tx - tx0) * MASK_PX
        if r < 0 or c < 0 or r + MASK_PX > a.shape[0] or c + MASK_PX > a.shape[1]:
            continue  # (outside the grid: not the continent's terrain)
        m = a[r:r + MASK_PX, c:c + MASK_PX]
        if m.min() >= LAND_MIN:
            continue
        out[k] = 0 if m.max() <= SEA_MAX else m.copy()
    return out


def sea_box(m: np.ndarray) -> tuple[int, int, int, int]:
    """A coastal mask's pixels not all land: (x0, y0, x1, y1), x east, y south, inclusive."""
    ys, xs = np.nonzero(m < 255)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def code(box) -> int:
    """sea_box packed as one number (GPSFrame's G.CoastBox unpacks it): 1 + x0 + 64 y0 + 64^2 x1 + 64^3 y1."""
    x0, y0, x1, y1 = box
    return 1 + x0 + 64 * (y0 + 64 * (x1 + 64 * y1))


def tga(m: np.ndarray) -> bytes:
    """A 32-bit uncompressed TGA of mask `m` (row 0 the top): white, its alpha `m` (stored bottom up, as the Atlas's
    masks are)."""
    h, w = m.shape
    head = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, 32, 8)
    px = np.empty((h, w, 4), np.uint8)
    px[..., :3] = 255
    px[..., 3] = m
    return head + px[::-1].tobytes()


def read_tga_alpha(data: bytes) -> tuple[np.ndarray, np.ndarray]:
    """(rgb (h, w, 3), alpha (h, w)) of a tga() file, row 0 the top (for the tests)."""
    w, h = struct.unpack_from("<HH", data, 12)
    px = np.frombuffer(data[18:18 + w * h * 4], np.uint8).reshape(h, w, 4)
    if not data[17] & 0x20:
        px = px[::-1]
    return px[..., :3], px[..., 3]


def build(log=print) -> dict:
    """cont -> tile masks, for every continent in Terrain.lua with minimap tiles."""
    g, mm = grids(), minimap_tiles()
    out = {}
    for cont, (tx0, ty0, cells) in sorted(g.items()):
        if cont not in mm:
            continue
        masks = tile_masks(tx0, ty0, cells, mm[cont])
        nsea = sum(1 for v in masks.values() if isinstance(v, int))
        log(f"  [{cont}] {len(mm[cont])} tiles: {len(masks) - nsea} coastal (masked), {nsea} all sea")
        out[cont] = masks
    return out


def lua(masks: dict) -> str:
    out = ["-- GENERATED by `agps coast --write` (app/azerothgps/coast.py) from Data/Terrain.lua and Data/Minimap.lua.",
           "-- Do not edit by hand. The seamless map's coastline (issue #73): per continent, its minimap tiles by",
           "-- tx * 64 + ty: 0 all sea (not drawn over the art), else a coastal tile drawn through its mask",
           "-- (Media\\Coast\\<cont>_<tx>_<ty>), the number the box of its pixels not all land (coast.py's code());",
           "-- tiles all land aren't listed.",
           "local _, ns = ...",
           f"ns.CoastFeatherYd = {FEATHER_YD:g}",
           "ns.Coast = {"]
    for cont, m in sorted(masks.items()):
        items = [f"[{k}]={0 if isinstance(v, int) else code(sea_box(v))}" for k, v in sorted(m.items())]
        out.append(f"  [{cont}] = {{")
        for i in range(0, len(items), 10):
            out.append("    " + ", ".join(items[i:i + 10]) + ",")
        out.append("  },")
    out.append("}")
    return "\n".join(out) + "\n"


FEATHER_FILE = ADDON_DIR / "Media" / "Feather.tga"
FEATHER_PX = 32  # its side
FEATHER_CUT = 0.25  # the share at each side that's its feather (GPSFrame's INTERIOR_FEATHER_CUT)


def feather() -> np.ndarray:
    """The interiors' edge blend's soft square (issue #85; GPSFrame's G.InteriorGround cuts it in nine): (32, 32) uint8
    alpha, 255 in its middle half, fading out (a smoothstep) by the distance from it over the outer FEATHER_CUT of each
    side, the corners round. Our own: made from numbers alone."""
    n, edge = FEATHER_PX, FEATHER_PX * FEATHER_CUT
    c = np.arange(n) + 0.5
    d = np.maximum(np.maximum(edge - c, 0), c - (n - edge))  # (each axis' distance out of the middle)
    t = np.clip(np.hypot(d[:, None], d[None, :]) / edge, 0, 1)
    return np.round((1 - t * t * (3 - 2 * t)) * 255).astype(np.uint8)


RING_DIR = ADDON_DIR / "Media"
# Drawn at each size it's shown at, pixel for pixel (asked 2026-11-14 with a screenshot: "these icon borders seem poorly
# downscaled"; one 64 px ring shrunk to 16 px broke up): GPSFrame's G.RING_SIZES picks the nearest.
RING_SIZES = (10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 32, 36, 40, 44, 48, 64)
RING_EDGE_PX = 0.8  # the black edge outside
RING_GOLD_SHARE = 0.11  # the gold band, a share of the radius ...
RING_GOLD_MIN_PX = 1.4  # ... at least this many pixels
RING_LINE_PX = 0.8  # the dark line inside it


def ring_file(n: int) -> Path:
    return RING_DIR / f"IconRing{n}.tga"


def ring(n: int = 64) -> np.ndarray:
    """The round map icons' ring (asked 2026-11-14: "round icons ... color appropriate rings for class trainers and gold
    rings as the default", then a picture of the look wanted: a thin bevelled gold rim with a dark edge; GPSFrame's
    G.RoundIcon tints it), drawn at `n` px: (n, n, 4) uint8 RGBA, clear inside and outside the circle; from the outside
    a black edge (RING_EDGE_PX), the band (white, bevelled lighter in its middle: the tint makes it gold; at least
    RING_GOLD_MIN_PX), a dark line (RING_LINE_PX); every edge anti-aliased by the pixel's coverage. Our own: made from
    numbers alone."""
    ss = 4  # (each pixel sampled 4 x 4 times)
    c = (np.arange(n * ss) + 0.5) / ss - n / 2
    d = np.hypot(c[:, None], c[None, :])  # (px from the middle)
    R = n / 2
    gold = max(RING_GOLD_MIN_PX, RING_GOLD_SHARE * R)
    g1 = R - RING_EDGE_PX
    g0 = g1 - gold
    inner = g0 - RING_LINE_PX
    on = (d <= R) & (d >= inner)
    band = (d < g1) & (d >= g0)
    mid = (g0 + g1) / 2
    bevel = 1 - 0.35 * np.clip(np.abs(d - mid) / (gold / 2), 0, 1) ** 2
    light = np.where(band, bevel, 0.0)
    alpha = np.where(on, np.where(band, 1.0, 0.92), 0.0)
    def down(a):  # (the samples averaged back to pixels)
        return a.reshape(n, ss, n, ss).mean(axis=(1, 3))
    a = down(alpha)
    lit = down(light * alpha)
    lum = np.divide(lit, a, out=np.zeros_like(a), where=a > 0)
    rgba = np.zeros((n, n, 4), np.uint8)
    rgba[..., :3] = np.round(np.clip(lum, 0, 1) * 255).astype(np.uint8)[..., None]
    rgba[..., 3] = np.round(np.clip(a, 0, 1) * 255).astype(np.uint8)
    return rgba


def tga_rgba(px: np.ndarray) -> bytes:
    """A 32-bit uncompressed TGA of RGBA pixels `px` (row 0 the top; stored bottom up, as tga())."""
    h, w = px.shape[:2]
    head = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, 32, 8)
    bgra = px[..., [2, 1, 0, 3]]
    return head + bgra[::-1].tobytes()


# The map's round buttons drawn sharp (asked 2026-11-18, for 1.3.9: "use right scaled images for that and all the menu
# buttons"): GPSFrame's G.FitRoundButton sizes each button to whole screen pixels these are drawn at. The round frame
# (Media/MapMenu.tga, our own 64 px art: the map menu button, the quick buttons' gray frame, the glows, the controller's
# focus ring) at each of FRAME_SIZES (64: MapMenu.tga itself), and a disc (the icons' round mask, anti-aliased) at each
# icon size drawn (RING_SIZES: iconscale.py's). Keep in step with GPSFrame's G.BUTTON_FRAME_SIZES.
BUTTON_DIR = ADDON_DIR / "Media" / "Buttons"
MAP_MENU_FILE = ADDON_DIR / "Media" / "MapMenu.tga"
FRAME_SIZES = tuple(range(12, 49, 2)) + (52, 56, 60, 64, 72, 80, 96, 112, 128)
DISC_SIZES = RING_SIZES


def frame_file(n: int) -> Path:
    return MAP_MENU_FILE if n == 64 else BUTTON_DIR / f"Frame{n}.tga"


def disc_file(n: int) -> Path:
    return BUTTON_DIR / f"Disc{n}.tga"


def read_tga_rgba(path: Path) -> np.ndarray:
    """An uncompressed 32-bit TGA's RGBA pixels (row 0 the top), as tga_rgba writes them."""
    data = path.read_bytes()
    idlen, w, h, bpp, desc = data[0], *struct.unpack("<HH", data[12:16]), data[16], data[17]
    assert data[2] == 2 and bpp == 32, path
    px = np.frombuffer(data[18 + idlen:18 + idlen + w * h * 4], np.uint8).reshape(h, w, 4)[..., [2, 1, 0, 3]]
    return px if desc & 0x20 else px[::-1]


def frame(n: int) -> np.ndarray:
    """The round frame at `n` px: MapMenu.tga resized (Lanczos, colors weighted by their alpha so its clear edge doesn't
    darken), (n, n, 4) uint8 RGBA."""
    from PIL import Image

    src = Image.fromarray(read_tga_rgba(MAP_MENU_FILE).copy(), "RGBA")
    if n == src.width:
        return np.asarray(src)
    out = src.convert("RGBa").resize((n, n), Image.LANCZOS, reducing_gap=None).convert("RGBA")
    return np.asarray(out)


def disc(n: int) -> np.ndarray:
    """A white disc filling `n` px, its edge anti-aliased by each pixel's coverage (sampled 4 x 4), clear outside: the
    round buttons' icon mask drawn at the icon's size (the game's portrait mask shrunk to 16 px was jagged). Our own:
    made from numbers alone. (n, n, 4) uint8 RGBA."""
    ss = 4
    c = (np.arange(n * ss) + 0.5) / ss - n / 2
    inside = (np.hypot(c[:, None], c[None, :]) <= n / 2).astype(float)
    a = inside.reshape(n, ss, n, ss).mean(axis=(1, 3))
    rgba = np.full((n, n, 4), 255, np.uint8)
    rgba[..., 3] = np.round(a * 255).astype(np.uint8)
    return rgba


def button_files() -> dict[Path, bytes]:
    """{ path: bytes } of the buttons' art: each frame size but 64 (MapMenu.tga itself) and each disc."""
    out = {frame_file(n): tga_rgba(frame(n)) for n in FRAME_SIZES if n != 64}
    out.update({disc_file(n): tga_rgba(disc(n)) for n in DISC_SIZES})
    return out


def write_buttons(log=print) -> list[Path]:
    """Media/Buttons/*.tga (button_files), the files no longer made removed."""
    BUTTON_DIR.mkdir(parents=True, exist_ok=True)
    files = button_files()
    for p, data in files.items():
        if not p.exists() or p.read_bytes() != data:
            p.write_bytes(data)
    for p in BUTTON_DIR.glob("*.tga"):
        if p not in files:
            p.unlink()
    log(f"button art: {len(files)} files, {sum(len(d) for d in files.values()) / 1e3:.0f} KB in Media/Buttons")
    return list(files)


def write(log=print) -> None:
    data = tga(feather())
    if not FEATHER_FILE.exists() or FEATHER_FILE.read_bytes() != data:
        FEATHER_FILE.write_bytes(data)
    for n in RING_SIZES:
        data = tga_rgba(ring(n))
        f = ring_file(n)
        if not f.exists() or f.read_bytes() != data:
            f.write_bytes(data)
    old = RING_DIR / "IconRing.tga"  # (the one size before)
    if old.exists():
        old.unlink()
    write_buttons(log)
    masks = build(log)
    MEDIA.mkdir(parents=True, exist_ok=True)
    keep = set()
    for cont, m in masks.items():
        for k, v in m.items():
            if isinstance(v, int):
                continue
            tx, ty = divmod(k, 64)
            name = f"{cont}_{tx}_{ty}.tga"
            keep.add(name)
            p = MEDIA / name
            data = tga(v)
            if not p.exists() or p.read_bytes() != data:
                p.write_bytes(data)
    for p in MEDIA.glob("*.tga"):
        if p.name not in keep:
            p.unlink()
    FILE.write_text(lua(masks), encoding="utf-8", newline="\n")
    log(f"wrote {FILE.relative_to(ADDON_DIR.parent.parent)} and {len(keep)} masks in Media/Coast")


def render(cont: int, X: float, Y: float, R: float, out: Path) -> Path:
    """A picture of the masks round world (X, Y): land white, the fade grey, the sea blue, tiles' edges drawn."""
    from PIL import Image

    tx0, ty0, cells = grids()[cont]
    tiles = minimap_tiles()[cont]
    tiled = has_tile(tx0, ty0, cells.shape, tiles)
    a = alpha(sea(cells, tiled))
    cell = TILE / MASK_PX
    c0 = int(((32 - (Y + R) / TILE) - tx0) * MASK_PX)
    c1 = int(((32 - (Y - R) / TILE) - tx0) * MASK_PX)
    r0 = int(((32 - (X + R) / TILE) - ty0) * MASK_PX)
    r1 = int(((32 - (X - R) / TILE) - ty0) * MASK_PX)
    c0, r0 = max(c0, 0), max(r0, 0)
    sub = a[r0:r1, c0:c1].astype(float) / 255
    water = cells[r0:r1, c0:c1] == 1
    img = np.zeros(sub.shape + (3,), np.uint8)
    sea_rgb, land_rgb = np.array([40, 70, 120]), np.array([200, 190, 150])
    img[:] = (sub[..., None] * land_rgb + (1 - sub[..., None]) * sea_rgb).astype(np.uint8)
    img[water & (sub > 0.99)] = [90, 140, 170]  # (water kept as land: rivers, lakes)
    img[(np.arange(r0, r0 + sub.shape[0]) % MASK_PX == 0), :] = [255, 0, 0]
    img[:, (np.arange(c0, c0 + sub.shape[1]) % MASK_PX == 0)] = [255, 0, 0]
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(img).resize((img.shape[1] * 3, img.shape[0] * 3), Image.NEAREST).save(out)
    return out
