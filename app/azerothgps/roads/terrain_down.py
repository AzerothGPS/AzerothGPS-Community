"""One-way ground for the terrain grid (`agps terrain-down --write`): Data/TerrainDown.lua.

Item 107 (1.4.1, SPF parity; issue #271). Data/Terrain.lua closes a cell too steep to walk up (half its quads over
50 degrees) both ways. A character goes down such ground: it slides, or it falls a little. A closed cell is **one way,
downhill** when:
  - the shipped grid closes it (value 2: not water, not the deep sea, not off the map) and the terrain's own rule is
    why (STEEP_SHARE of its quads too steep: never a cell the ridge filling or the pockets closed, which keep straight
    lines out of mountain ranges and plateaus: the one variant of #271's phase 2 that kept every wall test);
  - none of its quads is steeper than DOWN_SLOPE (70 degrees: a sheer face is a cliff, not a slope);
  - its ground falls at least FALL_MIN_SLOPE a yard (its fall line is clear);
  - and every way down through it, from the open ground where it starts to the open ground where it ends, falls at
    most the biggest of FALLS (U + D below). That bound is per cell, so any way through cells of one class falls no
    more than that class's yards: the game gates the class by the player's safe drop (Passability.DropMax), as the
    world grid gates its slopes' and ledges' drops (Kooki3z 2026-11-23: "too steep only blocks going UP"; down it is a
    drop of its height). FALLS[0] is the fall that costs no health (Nav.FALL_FREE, 14; the server's 14.57).

A step between two cells is a way down when it goes down (the next cell's ground DOWN_STEP_Z or more lower) and,
where either cell is one-way, within DOWN_CONE of that cell's fall line (Passability.lua's DownMove, the same rule).

Each cell's fall line is one of DIRS16 directions (22.5 degrees apart, in the grid's own axes: +col east, +row south),
its class one of FALLS: code = class * 16 + dir, one character of the grids' alphabet. Per grid row with any: runs of
one-way cells, each "cc" (its first column, 1-based, two base-64 digits) + "n" (its length - 1, one digit) + one code
character a cell.
"""

from __future__ import annotations

import hashlib
import math
import struct

import numpy as np

from ..extract import adt
from . import terrain as T

ALPHABET = T.ALPHABET
STEEP_SHARE = T.BLOCK_FRACTION  # (the terrain rule's own share)
DOWN_SLOPE = math.tan(math.radians(70))
FALL_MIN_SLOPE = math.tan(math.radians(20))
FALLS = (14.0, 25.0, 39.0, 60.0)  # yards: the classes' biggest fall (Passability.DOWN_FALLS)
DOWN_CONE = math.cos(math.radians(60))  # (Passability.DOWN_CONE)
DOWN_STEP_Z = 0.5  # yards: a step down at least this much (Passability.DOWN_STEP_Z, against Ground's heights)
ROUNDS = 3  # (cells over the biggest class out, the bounds worked out again: they were what pushed their neighbors' up)

# the 8 steps (dc, dr) and the 16 fall lines
STEPS = [(dc, dr) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dc or dr]
DIRS16 = [(math.cos(k * math.pi / 8), math.sin(k * math.pi / 8)) for k in range(16)]


def quad_grids(cd, continent: int, log=print):
    """(steep share pool input, quad max slope, quad z, land) over the continent's tiles, as terrain._continent_grid."""
    m = next(r for r in cd.table("Map") if r["ID"] == continent)
    wdt = adt.parse_wdt(cd.casc.read(m["WdtFileDataID"]))
    tiles = [k for k, t in wdt.tiles.items() if t.root]
    tx0, ty0 = min(x for x, _ in tiles), min(y for _, y in tiles)
    tx1, ty1 = max(x for x, _ in tiles), max(y for _, y in tiles)
    q = 128
    H, W = (ty1 - ty0 + 1) * q, (tx1 - tx0 + 1) * q
    slope = np.zeros((H, W), np.float32)
    z = np.zeros((H, W), np.float32)
    land = np.zeros((H, W), bool)
    for (tx, ty) in tiles:
        try:
            root = cd.casc.read(wdt.tiles[(tx, ty)].root)
        except Exception:
            continue
        r0, c0 = (ty - ty0) * q, (tx - tx0) * q
        for magic, a, b in adt.iter_chunks(root):
            if magic != "MCNK":
                continue
            ix, iy = struct.unpack_from("<II", root, a + 4)
            if ix >= 16 or iy >= 16:
                continue
            base = struct.unpack_from("<f", root, a + 0x68 + 8)[0]
            for m2, a2, b2 in adt.iter_chunks(root, a + T.MCNK_HEADER, b):
                if m2 == "MCVT" and b2 - a2 >= 145 * 4:
                    mcvt = np.frombuffer(root[a2:a2 + 145 * 4], np.float32)
                    rr, cc = r0 + iy * 8, c0 + ix * 8
                    slope[rr:rr + 8, cc:cc + 8] = T.chunk_slopes(mcvt)
                    z[rr:rr + 8, cc:cc + 8] = np.array([mcvt[i * 17 + 9:i * 17 + 17] for i in range(8)]) + base
                    land[rr:rr + 8, cc:cc + 8] = True
                    break
    log(f"  [{continent}] quads {W}x{H}")
    return tx0, ty0, slope, z, land


def cell_fields(slope, z, land):
    """Per cell (CELL_QUADS a side): the share of steep quads, the steepest quad, the mean height, all land."""
    k = T.CELL_QUADS
    H, W = slope.shape

    def pool(a, f):
        return f(a.reshape(H // k, k, W // k, k), axis=(1, 3))

    share = pool((slope > T.MAX_SLOPE).astype(np.float32), np.mean)
    top = pool(slope, np.max)
    zc = pool(z, np.mean)
    whole = pool(land, np.all)
    return share, top, zc, whole


def fall_lines(zc: np.ndarray, cell: float):
    """Each cell's fall line: (its slope, a yard, and its direction index 0-15 in (col, row) axes)."""
    gr = np.zeros_like(zc)
    gc = np.zeros_like(zc)
    gr[1:-1, :] = (zc[2:, :] - zc[:-2, :]) / (2 * cell)
    gc[:, 1:-1] = (zc[:, 2:] - zc[:, :-2]) / (2 * cell)
    mag = np.hypot(gr, gc)
    ang = np.arctan2(-gr, -gc)  # (downhill: against the gradient; atan2(row, col))
    d = np.round(ang / (math.pi / 8)).astype(np.int64) % 16
    return mag, d


def _cos_tables():
    """cos between each of the 8 steps and each of the 16 fall lines: (8, 16)."""
    out = np.zeros((8, 16))
    for i, (dc, dr) in enumerate(STEPS):
        L = math.hypot(dc, dr)
        for k, (ux, uy) in enumerate(DIRS16):
            out[i, k] = (dc * ux + dr * uy) / L
    return out


COS = _cos_tables()


def _bounds_py(order, zf, kind, dirs, H, W, cos, up):
    """U (up=True: the most fall from open ground above into each one-way cell) or D (the most fall from it down to
    open ground) by the cells in `order`; kind: 0 closed, 1 open, 2 one-way (candidate). -1 where there's none."""
    out = np.full(H * W, -1.0)
    for n in order:
        r, c = divmod(int(n), W)
        best = -1.0
        for i in range(8):
            dc, dr = STEPS[i]
            # (up: the step from the neighbor into this cell; down: from this cell into the neighbor)
            rr, cc = r - dr if up else r + dr, c - dc if up else c + dc
            if rr < 0 or rr >= H or cc < 0 or cc >= W:
                continue
            m = rr * W + cc
            km = kind[m]
            if km == 0:
                continue
            hi, lo = (m, n) if up else (n, m)
            dz = zf[hi] - zf[lo]
            if dz < DOWN_STEP_Z:
                continue
            if kind[hi] == 2 and cos[i, dirs[hi]] < DOWN_CONE:
                continue
            if kind[lo] == 2 and cos[i, dirs[lo]] < DOWN_CONE:
                continue
            if dr and dc:  # (a diagonal: the two cells beside it not closed)
                if kind[r * W + (c - dc if up else c + dc)] == 0 or kind[(r - dr if up else r + dr) * W + c] == 0:
                    continue
            if km == 1:
                v = dz
            else:
                if out[m] < 0:
                    continue
                v = dz + out[m]
            if v > best:
                best = v
        out[n] = best
    return out


try:
    import numba as _nb

    _STEPS_A = np.array(STEPS, np.int64)

    @_nb.njit(cache=True)
    def _bounds_nb(order, zf, kind, dirs, H, W, cos, up, steps, step_z, cone):
        out = np.full(H * W, -1.0)
        for n in order:
            r, c = n // W, n % W
            best = -1.0
            for i in range(8):
                dc, dr = steps[i, 0], steps[i, 1]
                if up:
                    rr, cc = r - dr, c - dc
                else:
                    rr, cc = r + dr, c + dc
                if rr < 0 or rr >= H or cc < 0 or cc >= W:
                    continue
                m = rr * W + cc
                km = kind[m]
                if km == 0:
                    continue
                if up:
                    hi, lo = m, n
                else:
                    hi, lo = n, m
                dz = zf[hi] - zf[lo]
                if dz < step_z:
                    continue
                if kind[hi] == 2 and cos[i, dirs[hi]] < cone:
                    continue
                if kind[lo] == 2 and cos[i, dirs[lo]] < cone:
                    continue
                if dr != 0 and dc != 0:
                    if up:
                        s1, s2 = r * W + (c - dc), (r - dr) * W + c
                    else:
                        s1, s2 = r * W + (c + dc), (r + dr) * W + c
                    if kind[s1] == 0 or kind[s2] == 0:
                        continue
                if km == 1:
                    v = dz
                else:
                    if out[m] < 0:
                        continue
                    v = dz + out[m]
                if v > best:
                    best = v
            out[n] = best
        return out

    def _bounds(order, zf, kind, dirs, H, W, cos, up):
        return _bounds_nb(order, zf, kind, dirs, H, W, cos, up, _STEPS_A, DOWN_STEP_Z, DOWN_CONE)
except ImportError:  # (numba is the bake's optional accelerator; the rule's the same)
    _bounds = _bounds_py


def one_way(cells: np.ndarray, share, top, zc, whole, cell: float, log=print):
    """The one-way cells' codes (h x w int16: class * 16 + dir, -1 none) for a shipped grid's `cells` (0 open, 1 water,
    2 closed, 3 deep) and the terrain's per-cell fields."""
    H, W = cells.shape
    mag, dirs = fall_lines(zc, cell)
    cand = (cells == 2) & whole & (share >= STEEP_SHARE) & (top <= DOWN_SLOPE) & (mag >= FALL_MIN_SLOPE)
    # (the frame: never one-way, so the steps never leave the grid)
    cand[0, :] = cand[-1, :] = False
    cand[:, 0] = cand[:, -1] = False
    openc = (cells == 0) | (cells == 1)
    zf = zc.astype(np.float64).ravel()
    dflat = dirs.astype(np.int64).ravel()
    fall = np.full(H * W, np.inf)
    for _ in range(ROUNDS):
        kind = np.zeros(H * W, np.int8)
        kind[openc.ravel()] = 1
        kind[cand.ravel()] = 2
        idx = np.flatnonzero(cand.ravel())
        down = idx[np.argsort(-zf[idx], kind="stable")]  # (highest first: U from above)
        U = _bounds(down, zf, kind, dflat, H, W, COS, True)
        D = _bounds(down[::-1].copy(), zf, kind, dflat, H, W, COS, False)
        fall = np.where((U >= 0) & (D >= 0), U + D, np.inf)
        over = cand.ravel() & ~(fall <= FALLS[-1])
        if not over.any():
            break
        cand = cand & ~over.reshape(H, W)
    code = np.full(H * W, -1, np.int16)
    ok = cand.ravel() & (fall <= FALLS[-1])
    cls = np.searchsorted(np.array(FALLS), fall, side="left")
    code[ok] = (cls[ok] * 16 + dflat[ok]).astype(np.int16)
    code = code.reshape(H, W)
    n = int((code >= 0).sum())
    log(f"    one-way cells: {n} of {int((cells == 2).sum())} closed "
        f"({', '.join(f'{int(((code >= 0) & (code // 16 == k)).sum())} <= {FALLS[k]:g}' for k in range(len(FALLS)))})")
    return code


def encode_row(codes: np.ndarray) -> str:
    """A row's one-way cells (above): runs of up to 64."""
    out = []
    c, W = 0, len(codes)
    while c < W:
        if codes[c] < 0:
            c += 1
            continue
        s = c
        while c < W and codes[c] >= 0 and c - s < 64:
            c += 1
        col = s + 1
        out.append(ALPHABET[col >> 6] + ALPHABET[col & 63] + ALPHABET[c - s - 1]
                   + "".join(ALPHABET[int(v)] for v in codes[s:c]))
    return "".join(out)


def decode_row(text: str, w: int) -> np.ndarray:
    """Inverse of encode_row (for tests)."""
    out = np.full(w, -1, np.int16)
    i = 0
    while i < len(text):
        col = ALPHABET.index(text[i]) * 64 + ALPHABET.index(text[i + 1])
        n = ALPHABET.index(text[i + 2]) + 1
        for k in range(n):
            out[col - 1 + k] = ALPHABET.index(text[i + 3 + k])
        i += 3 + n
    return out


def shipped_cells(cont: int, text: str | None = None) -> tuple[dict, np.ndarray]:
    """Data/Terrain.lua's grid for `cont`: (its header, its cells with the deep sea as 3)."""
    import re

    from ..paths import ADDON_DIR

    text = text or (ADDON_DIR / "Data" / "Terrain.lua").read_text(encoding="utf-8")
    head = re.search(rf"\[{cont}\] = \{{ tx0 = (\d+), ty0 = (\d+), cell = ([\d.]+), w = (\d+), h = (\d+), deep = (\d+), "
                     r"rows = \{\n(.*?)\n  \} \},", text, re.S)
    tx0, ty0, cell, w, h, deep = (int(head.group(1)), int(head.group(2)), float(head.group(3)), int(head.group(4)),
                                  int(head.group(5)), int(head.group(6)))
    rows = re.findall(r'"([^"]*)"', head.group(7))
    assert len(rows) == h, (cont, len(rows), h)
    cells = np.array([T.decode_row(r) for r in rows], np.int8)
    assert cells.shape == (h, w), (cells.shape, h, w)
    return {"tx0": tx0, "ty0": ty0, "cell": cell, "w": w, "h": h, "deep": deep}, cells


def stamp_of(rows_text: str) -> str:
    return hashlib.sha1(rows_text.encode()).hexdigest()[:16]


def terrain_down_lua(cd, continents=None, log=print) -> str:
    from ..extract.pipeline import CONTINENTS

    from ..paths import ADDON_DIR

    terrain = (ADDON_DIR / "Data" / "Terrain.lua").read_text(encoding="utf-8")
    out = ["-- GENERATED by `agps terrain-down --write` (app/azerothgps/roads/terrain_down.py) from client "
           f"{cd.casc.version}. Do not edit by hand.",
           "-- One-way ground over Data/Terrain.lua's closed cells: walked down only, never up (item 107; see",
           "-- terrain_down.py). Per grid row: runs of 'cc' (first column, base 64) 'n' (length - 1), then a code a cell:",
           "-- class * 16 + fall line (16 ways, +col east, +row south); the class's fall: Passability.DOWN_FALLS.",
           "-- `terrain`: the Terrain.lua grid's rows it was made for (a hash: test_one_way_slopes.py fails when they differ).",
           "local _, ns = ...", "ns.TerrainDown = {"]
    for cont in continents or CONTINENTS:
        head, cells = shipped_cells(cont, terrain)
        tx0, ty0, slope, z, land = quad_grids(cd, cont, log)
        assert (tx0, ty0) == (head["tx0"], head["ty0"]), (cont, tx0, ty0, head)
        share, top, zc, whole = cell_fields(slope, z, land)
        assert share.shape == cells.shape, (share.shape, cells.shape)
        code = one_way(cells, share, top, zc, whole, head["cell"], log)
        rows = {}
        for r in range(cells.shape[0]):
            s = encode_row(code[r])
            if s:
                rows[r + 1] = s
        out.append(f'  [{cont}] = {{ w = {head["w"]}, h = {head["h"]}, terrain = "{terrain_stamp(terrain, cont)}", '
                   f"rows = {{")
        for r, s in rows.items():
            out.append(f'    [{r}] = "{s}",')
        out.append("  } },")
    out.append("}")
    return "\n".join(out) + "\n"


def terrain_stamp(terrain_text: str, cont: int) -> str:
    """A hash of the Terrain.lua grid's rows for `cont`."""
    import re

    head = re.search(rf"\[{cont}\] = \{{ tx0 = .*?rows = \{{\n(.*?)\n  \}} \}},", terrain_text, re.S)
    return stamp_of(head.group(1))
