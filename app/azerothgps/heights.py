"""The map's ground heights, baked from the client's terrain (addon/AzerothGPS/Data/Heights.lua; 1.3.10, issue #685).

WoW Forever gives addons no player height (UnitPosition's z is always 0), so the road and wall tools take the ground's
height from here: drawn roads start with real heights, the tools show "Ground: 123 yd" at the pointer, and a cliff
wall's sides are filled in. Terrain only (no building or cave floors).

Per map tile (533 yd, the ADTs'), a grid of (N + 1) x (N + 1) heights at the tile's vertices every TILE_YD / N yards,
row = south, column = east from its north-west corner (as Ground.sample and Data/Terrain.lua), in whole yards. "None"
where the terrain has a hole (a cave's or a cellar's way down) at the spot. Where there's water over the ground, a
second grid of the water's surface (none where there's no water); the first keeps the bed's height.

Each grid is one string: each value predicted from its neighbors (left + up - up-left, as many of them as are known)
and the difference written as one character when small (ALPHABET), longer codes for big jumps, runs of equal steps and
runs of none (encode / decode; the addon's Heights.lua decodes the same way, a tile at a time, only while the road or
wall tools are open).
"""

from __future__ import annotations

import math
import struct

import numpy as np

from .extract import adt
from .paths import ADDON_DIR

FILE = ADDON_DIR / "Data" / "Heights.lua"
CONTINENTS = (0, 1)
MAX_BYTES = 4 * 1024 * 1024  # (8 yd if both continents' grids fit in this, else 16 yd)

# The characters: '#' (35) .. '~' (126) but '\' (92): 91, each one's number its place here.
ALPHABET = "".join(chr(c) for c in range(35, 127) if c != 92)
BASE = len(ALPHABET)  # 91
SMALL = 40  # a difference within +-SMALL: one character (0 .. 80)
NONE = 81  # one "none"
NONE_RUN = 82  # "none" k times: the next character's number + 2
ZERO_RUN = 83  # the prediction exactly, k times: the next character's number + 2
BIG = 84  # a bigger difference: the next two characters, base 91, minus BIG_OFF
BIG_OFF = BASE * BASE // 2
_INDEX = {c: i for i, c in enumerate(ALPHABET)}


def _predict(g, i: int, j: int, last):
    """The prediction for value (i, j) of grid `g` (lists of rows, None for none): left + up - up-left when all three
    are known, else the left, else the up, else the last value written (`last`), else 0."""
    left = g[i][j - 1] if j > 0 else None
    up = g[i - 1][j] if i > 0 else None
    ul = g[i - 1][j - 1] if i > 0 and j > 0 else None
    if left is not None and up is not None and ul is not None:
        return left + up - ul
    if left is not None:
        return left
    if up is not None:
        return up
    return last if last is not None else 0


def encode(g) -> str:
    """A grid of whole numbers (rows; None: none) as a string (see the module's notes)."""
    out = []
    last = None
    rows = [list(r) for r in g]
    n = len(rows[0])
    flat = [(i, j) for i in range(len(rows)) for j in range(n)]
    k = 0
    while k < len(flat):
        i, j = flat[k]
        v = rows[i][j]
        if v is None:
            run = 1
            while k + run < len(flat) and run < BASE + 1 and rows[flat[k + run][0]][flat[k + run][1]] is None:
                run += 1
            if run == 1:
                out.append(ALPHABET[NONE])
            else:
                out.append(ALPHABET[NONE_RUN] + ALPHABET[run - 2])
            k += run
            continue
        p = _predict(rows, i, j, last)
        d = v - p
        if d == 0:
            # (a run of exact predictions: each predicted from those before it, as decode does)
            run = 1
            while k + run < len(flat) and run < BASE + 1:
                i2, j2 = flat[k + run]
                v2 = rows[i2][j2]
                if v2 is None or v2 != _predict(rows, i2, j2, v):
                    break
                run += 1
            if run >= 3:
                out.append(ALPHABET[ZERO_RUN] + ALPHABET[run - 2])
                last = rows[flat[k + run - 1][0]][flat[k + run - 1][1]]
                k += run
                continue
        if -SMALL <= d <= SMALL:
            out.append(ALPHABET[d + SMALL])
        else:
            c = d + BIG_OFF
            if not 0 <= c < BASE * BASE:
                raise ValueError(f"height step {d} too big")
            out.append(ALPHABET[BIG] + ALPHABET[c // BASE] + ALPHABET[c % BASE])
        last = v
        k += 1
    return "".join(out)


def decode(s: str, n: int) -> list[list]:
    """A string from encode as its grid: n rows of n (None: none)."""
    g = [[None] * n for _ in range(n)]
    last = None
    k = 0
    pos = 0

    def put(v):
        nonlocal k
        g[k // n][k % n] = v
        k += 1

    while pos < len(s):
        c = _INDEX[s[pos]]
        pos += 1
        if c == NONE:
            put(None)
        elif c == NONE_RUN:
            for _ in range(_INDEX[s[pos]] + 2):
                put(None)
            pos += 1
        elif c == ZERO_RUN:
            for _ in range(_INDEX[s[pos]] + 2):
                v = _predict(g, k // n, k % n, last)
                put(v)
                last = v
            pos += 1
        else:
            if c == BIG:
                d = _INDEX[s[pos]] * BASE + _INDEX[s[pos + 1]] - BIG_OFF
                pos += 2
            else:
                d = c - SMALL
            v = _predict(g, k // n, k % n, last) + d
            put(v)
            last = v
    if k != n * n:
        raise ValueError(f"{k} values for {n} x {n}")
    return g


def _water_tops(root: bytes) -> np.ndarray:
    """Each of a tile's 128 x 128 quads' water surface (its liquids' highest top), NaN with none."""
    top = np.full((128, 128), np.nan)
    for magic, a, _b in adt.iter_chunks(root):
        if magic != "MH2O":
            continue
        for ci in range(256):
            off_inst, n_layers, _ = struct.unpack_from("<III", root, a + ci * 12)
            if not n_layers or not off_inst:
                continue
            cy, cx = divmod(ci, 16)
            for li in range(n_layers):
                p = a + off_inst + li * 24
                _t, _f, _mn, mx, x0, y0, w, h, off_mask, _ov = struct.unpack_from("<HHffBBBBII", root, p)
                cells = np.zeros((8, 8), bool)
                if off_mask:
                    raw = root[a + off_mask: a + off_mask + (w * h + 7) // 8]
                    bits = np.unpackbits(np.frombuffer(raw, np.uint8), bitorder="little")[:w * h]
                    cells[y0:y0 + h, x0:x0 + w] = bits.reshape(h, w).astype(bool)
                else:
                    cells[y0:y0 + h, x0:x0 + w] = True
                blk = top[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8]
                blk[cells] = np.fmax(blk[cells], mx)
    return top


def _around(q: np.ndarray, step: int, fn) -> np.ndarray:
    """Per vertex of the (128 / step + 1)^2 grid, `fn` over the 128-grid quads touching it (up to four)."""
    n = 128 // step
    out = []
    for i in range(n + 1):
        row = []
        for j in range(n + 1):
            vi, vj = i * step, j * step
            row.append(fn(q[max(0, vi - 1):min(128, vi + 1), max(0, vj - 1):min(128, vj + 1)]))
        out.append(row)
    return np.array(out)


def tile_grids(ground, tx: int, ty: int, step: int):
    """A tile's (ground, water) grids every `step` of its 128 quads (2: 8.3 yd, 4: 16.7 yd), whole yards, None for
    none; (None, None) with no terrain there. `ground`: a caves.Ground."""
    t = ground._tile(tx, ty)
    if t is None:
        return None, None
    V, _bad, holes = t
    H = V[::step, ::step]
    hole = _around(holes, step, np.any)
    gr = [[None if (hole[i][j] or not np.isfinite(H[i, j])) else int(round(float(H[i, j])))
           for j in range(H.shape[1])] for i in range(H.shape[0])]
    wt = None
    t2 = ground.wdt.tiles.get((tx, ty))
    if t2 and t2.root:
        tops = _water_tops(ground.cd.casc.read(t2.root))
        if np.isfinite(tops).any():
            W = _around(tops, step, lambda a: np.nanmax(a) if np.isfinite(a).any() else np.nan)
            wt = [[None if not np.isfinite(W[i, j]) else int(round(float(W[i, j]))) for j in range(W.shape[1])]
                  for i in range(W.shape[0])]
            if all(v is None for r in wt for v in r):
                wt = None
    if all(v is None for r in gr for v in r) and wt is None:
        return None, None
    return gr, wt


def continent_tiles(cd, cont: int, step: int, log=print) -> dict:
    """{(tx, ty): (ground string, water string or None)} for every tile of the continent with terrain."""
    from .caves import Ground

    ground = Ground(cd, cont)
    out = {}
    keys = sorted(k for k, t in ground.wdt.tiles.items() if t and t.root)
    for n, (tx, ty) in enumerate(keys):
        gr, wt = tile_grids(ground, tx, ty, step)
        ground.tiles.pop((tx, ty), None)  # (one tile at a time: the continent's won't fit in memory)
        if gr is None:
            continue
        out[(tx, ty)] = (encode(gr), encode(wt) if wt else None)
        if n % 100 == 0:
            log(f"  [{cont}] {n}/{len(keys)} tiles")
    return out


def heights_lua(tiles: dict, step: int, version: str = "?") -> str:
    """Data/Heights.lua from {cont: continent_tiles}."""
    n = 128 // step
    out = [f"-- GENERATED by `agps heights --write` from client {version}. Do not edit by hand.",
           "-- The ground's height per map tile (Heights.lua, app/azerothgps/heights.py): a grid of (n + 1) x (n + 1)",
           "-- whole yards at the tile's vertices every cell yards, row = south, col = east, each one string;",
           "-- water[cont][key]: the water's surface where there's water. key = tx * 64 + ty.",
           "local _, ns = ...",
           f"ns.Heights = {{ n = {n}, cell = {adt.TILE_YD / n:.6f}, water = {{}} }}"]
    for cont, tl in sorted(tiles.items()):
        out.append(f"ns.Heights[{cont}] = {{")
        for (tx, ty), (g, _w) in sorted(tl.items()):
            out.append(f'  [{tx * 64 + ty}] = "{g}",')
        out.append("}")
        out.append(f"ns.Heights.water[{cont}] = {{")
        for (tx, ty), (_g, w) in sorted(tl.items()):
            if w:
                out.append(f'  [{tx * 64 + ty}] = "{w}",')
        out.append("}")
    return "\n".join(out) + "\n"


def grid_at(tiles: dict, n: int, x: float, y: float, water: bool = False):
    """The baked height at world (x, y) from {(tx, ty): (ground, water) strings}: bilinear over the tile's grid, None
    off the map or where a corner is none. As Heights.lua's H.At (the tests check the two agree)."""
    T = adt.TILE_YD
    tx, ty = math.floor(32 - y / T), math.floor(32 - x / T)
    s = tiles.get((tx, ty))
    s = s and s[1 if water else 0]
    if not s:
        return None
    g = decode(s, n + 1)
    fi = ((32 - ty) * T - x) / (T / n)
    fj = ((32 - tx) * T - y) / (T / n)
    i, j = min(int(fi), n - 1), min(int(fj), n - 1)
    u, v = fi - i, fj - j
    c = (g[i][j], g[i + 1][j], g[i][j + 1], g[i + 1][j + 1])
    if any(a is None for a in c):
        return None
    return c[0] * (1 - u) * (1 - v) + c[1] * u * (1 - v) + c[2] * (1 - u) * v + c[3] * u * v
