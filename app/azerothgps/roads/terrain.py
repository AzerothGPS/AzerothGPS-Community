"""Passability grid from terrain heightmaps and water, for offroad routing.

Each continent is divided into cells of CELL_QUADS x CELL_QUADS terrain quads
(a quad is 1/8 of a chunk, 4.17 yd). A cell is:
  0 passable, 1 water (swimmable, slower), 2 blocked (too steep to climb, or deep water: fatigue).
"""

from __future__ import annotations

import struct

import numpy as np

from ..extract import adt
from ..extract.spike import ClientData

QUAD_YD = adt.CHUNK_YD / 8  # 4.17 yd
CELL_QUADS = 2  # cell = 8.33 yd
MAX_SLOPE = 1.19  # tan(50 deg): about what a character can walk up
BLOCK_FRACTION = 0.5  # a cell is blocked when at least this share of its quads is too steep
HILL_SLOPE = 0.58  # tan(30 deg): a climb
HILL_FRACTION = 0.25  # a cell is hilly when this share of its quads is a climb
HILL_SPECK = 16  # cells: smaller hilly bits are left out
HILL_BLOCK = 4  # the hills grid is this many cells to a side coarser (33 yd)
# yd: a quad whose highest point is this far under the sea is swum, however steep its bed. The sea's only: a lake's
# steep bed stays closed (off the Ruins of Lordaeron, a 25 yd cliff down into the lake ended a straight leg the end
# slack let through, and the lake behind it opened)
SWIM_DEPTH = 2.0
# The client's water marks its open sea "deep" (MH2O's attributes: the deep mask, none given: all deep, what server
# cores swim into fatigue as). A route from the Wetlands' coast to Southshore swam 2 km straight over the strait into
# fatigue (reported 2026-11-19, 1.3.9). Fatigue takes about a minute to run out, so deep water is closed, as steep
# ground, only DEEP_REACH_YD or more from water that isn't deep: a crossing of a narrow deep band stays a swim (from
# Alterac's coast to Silverpine, walked over 130 yd of it, issue #271). A cell is deep with DEEP_FRACTION of its quads.
DEEP_FRACTION = 0.5
DEEP_REACH_YD = 100.0
# The client's deep mask leaves wide bands of open sea "shallow" (the Wetlands-Southshore strait: a 270 yd band
# down Arathi's coast), where players still tire (200 yd out from the Wetlands, 2026-11-19). So the sea (its
# LiquidTypes, `sea_types`) is closed too SEA_REACH_YD or more from any shore, deep mask or not.
SEA_REACH_YD = 150.0
# In Data/Terrain.lua such a cell is written as this value (the grid's `deep`), read as 2 by Passability.lua: the
# seamless map's coastline (coast.py) keeps it the sea's
DEEP_VALUE = 3
MCNK_HEADER = 128


def chunk_slopes(mcvt: np.ndarray) -> np.ndarray:
    """8x8 steepest slope (rise/run) per quad. mcvt = 145 heights (9x9 outer + 8x8 inner)."""
    rows = [mcvt[i * 17 : i * 17 + 9] for i in range(9)]
    outer = np.array(rows)  # (9, 9) [row = south, col = east]
    inner = np.array([mcvt[i * 17 + 9 : i * 17 + 17] for i in range(8)])  # (8, 8) quad centres
    a, b = outer[:-1, :-1], outer[:-1, 1:]
    c, d = outer[1:, :-1], outer[1:, 1:]
    diag = QUAD_YD * np.sqrt(2)
    half = diag / 2
    g = np.maximum.reduce([
        np.abs(a - d) / diag, np.abs(b - c) / diag,
        np.abs(inner - a) / half, np.abs(inner - b) / half, np.abs(inner - c) / half, np.abs(inner - d) / half,
    ])
    return g


def chunk_steep_quads(mcvt: np.ndarray) -> np.ndarray:
    """8x8 bool: quads whose slope exceeds MAX_SLOPE."""
    return chunk_slopes(mcvt) > MAX_SLOPE


def chunk_tops(mcvt: np.ndarray) -> np.ndarray:
    """8x8 highest point per quad (its four corners and its middle), over the chunk's base height."""
    outer = np.array([mcvt[i * 17 : i * 17 + 9] for i in range(9)])
    inner = np.array([mcvt[i * 17 + 9 : i * 17 + 17] for i in range(8)])
    return np.maximum.reduce([outer[:-1, :-1], outer[:-1, 1:], outer[1:, :-1], outer[1:, 1:], inner])


def tile_grid(root: bytes, hills: bool = False, swim_types=None, deep_out=None, sea_out=None):
    """(steep, water) as 128x128 quad grids for one ADT tile [row = south, col = east];
    with `hills`, also the quads that are a climb (steeper than HILL_SLOPE). `deep_out` (a 128x128 bool array, or
    None): set where the water is deep (fatigue). With `swim_types` (the
    LiquidType ids swum through: the sea's), a quad SWIM_DEPTH under one of those liquids isn't steep: a
    steep seabed is swum over (Alterac's coast to Silverpine, walked: issue #271)."""
    steep = np.zeros((128, 128), bool)
    water = np.zeros((128, 128), bool)
    hill = np.zeros((128, 128), bool)
    top = np.full((128, 128), np.inf, np.float32)  # each quad's highest point (world height)
    surface = np.full((128, 128), -np.inf, np.float32)  # the swum liquid's surface over it (its layer's lowest)
    for magic, a, b in adt.iter_chunks(root):
        if magic == "MCNK":
            ix, iy = struct.unpack_from("<II", root, a + 4)
            if ix >= 16 or iy >= 16:
                continue
            base = struct.unpack_from("<f", root, a + 0x68 + 8)[0]
            for m2, a2, b2 in adt.iter_chunks(root, a + MCNK_HEADER, b):
                if m2 == "MCVT" and b2 - a2 >= 145 * 4:
                    mcvt = np.frombuffer(root[a2 : a2 + 145 * 4], np.float32)
                    sl = chunk_slopes(mcvt)
                    steep[iy * 8 : iy * 8 + 8, ix * 8 : ix * 8 + 8] = sl > MAX_SLOPE
                    hill[iy * 8 : iy * 8 + 8, ix * 8 : ix * 8 + 8] = sl > HILL_SLOPE
                    top[iy * 8 : iy * 8 + 8, ix * 8 : ix * 8 + 8] = chunk_tops(mcvt) + base
                    break
        elif magic == "MH2O":
            for ci in range(256):
                off_inst, n_layers, off_attr = struct.unpack_from("<III", root, a + ci * 12)
                if not n_layers or not off_inst:
                    continue
                cy, cx = divmod(ci, 16)
                if deep_out is not None:  # (fishable u64, then deep u64: bit y * 8 + x; none given: all deep, as
                    # server cores read it)
                    deep_bits = struct.unpack_from("<Q", root, a + off_attr + 8)[0] if off_attr else (1 << 64) - 1
                    if deep_bits:
                        bits = np.array([(deep_bits >> i) & 1 for i in range(64)], bool).reshape(8, 8)
                        deep_out[cy * 8 : cy * 8 + 8, cx * 8 : cx * 8 + 8] |= bits
                for li in range(n_layers):
                    p = a + off_inst + li * 24
                    ltype, _f, low, _mx, x0, y0, w, h, off_mask, _ov = struct.unpack_from("<HHffBBBBII", root, p)
                    cells = np.zeros((8, 8), bool)
                    if off_mask:
                        nbits = w * h
                        raw = root[a + off_mask : a + off_mask + (nbits + 7) // 8]
                        bits = np.unpackbits(np.frombuffer(raw, np.uint8), bitorder="little")[:nbits]
                        cells[y0 : y0 + h, x0 : x0 + w] = bits.reshape(h, w).astype(bool)
                    else:
                        cells[y0 : y0 + h, x0 : x0 + w] = True
                    water[cy * 8 : cy * 8 + 8, cx * 8 : cx * 8 + 8] |= cells
                    if swim_types is not None and ltype in swim_types:
                        surface[cy * 8 : cy * 8 + 8, cx * 8 : cx * 8 + 8][cells] = np.maximum(
                            surface[cy * 8 : cy * 8 + 8, cx * 8 : cx * 8 + 8][cells], low)
    if swim_types is not None:  # (the MH2O chunk comes before the MCNKs: judged once both are read)
        deep = surface - top >= SWIM_DEPTH
        steep &= ~deep
        if sea_out is not None:  # (under the sea's surface)
            sea_out |= surface > -np.inf
    if hills:
        return steep, water, hill
    return steep, water


def sea_types(cd: ClientData) -> set:
    """The LiquidType ids of the sea: the old Ocean (its SoundBank 1) and the PBR ones named so."""
    return {r["ID"] for r in cd.table("LiquidType") if r["SoundBank"] == 1 or "Ocean" in (r["Name"] or "")}


_GRIDS: dict = {}  # (client, continent) -> the grid (the caves read it again after Terrain.lua)


def continent_grid(cd: ClientData, continent: int, log=print) -> dict:
    """Cell grid over the continent's terrain bounding box."""
    key = (id(cd), continent)
    if key not in _GRIDS:
        _GRIDS[key] = _continent_grid(cd, continent, log)
    return _GRIDS[key]


def _continent_grid(cd: ClientData, continent: int, log=print) -> dict:
    m = next(r for r in cd.table("Map") if r["ID"] == continent)
    wdt = adt.parse_wdt(cd.casc.read(m["WdtFileDataID"]))
    tiles = [k for k, t in wdt.tiles.items() if t.root]
    tx0, ty0 = min(x for x, _ in tiles), min(y for _, y in tiles)
    tx1, ty1 = max(x for x, _ in tiles), max(y for _, y in tiles)
    qpt = 128  # quads per tile edge
    H, W = (ty1 - ty0 + 1) * qpt, (tx1 - tx0 + 1) * qpt
    steep = np.zeros((H, W), bool)
    water = np.zeros((H, W), bool)
    land = np.zeros((H, W), bool)
    hill = np.zeros((H, W), bool)
    deep = np.zeros((H, W), bool)
    sea = np.zeros((H, W), bool)
    swim = sea_types(cd)
    for (tx, ty) in tiles:
        try:
            dp = np.zeros((qpt, qpt), bool)
            se = np.zeros((qpt, qpt), bool)
            s, w, hl = tile_grid(cd.casc.read(wdt.tiles[(tx, ty)].root), hills=True, swim_types=swim, deep_out=dp, sea_out=se)
        except Exception:
            continue
        r, c = (ty - ty0) * qpt, (tx - tx0) * qpt
        deep[r : r + qpt, c : c + qpt] = dp & w
        sea[r : r + qpt, c : c + qpt] = se & w
        steep[r : r + qpt, c : c + qpt] = s
        water[r : r + qpt, c : c + qpt] = w
        hill[r : r + qpt, c : c + qpt] = hl
        land[r : r + qpt, c : c + qpt] = True
    k = CELL_QUADS
    def pool(a):
        return a.reshape(H // k, k, W // k, k).mean(axis=(1, 3))
    cells = np.zeros((H // k, W // k), np.uint8)
    cells[pool(water) >= 0.5] = 1
    cells[pool(steep) >= BLOCK_FRACTION] = 2
    from scipy import ndimage

    far = pool(deep) >= DEEP_FRACTION
    far &= ndimage.distance_transform_edt(far) * QUAD_YD * k > DEEP_REACH_YD
    open_sea = pool(sea) >= 0.5
    open_sea &= ndimage.distance_transform_edt(pool(water) >= 0.5) * QUAD_YD * k > SEA_REACH_YD  # (from dry ground)
    far |= open_sea
    cells[pool(land) < 0.5] = 2  # no terrain: void / off the map
    cells = despeckle(cells)
    # (closed after the despeckle, which would otherwise turn the specks of sea they leave into land: the coast
    # masks read DEEP_VALUE as sea)
    far &= cells == 1  # (water till now: what Data/Terrain.lua writes as DEEP_VALUE)
    cells[far] = 2  # (far out in fatigue water: never swum)
    # hilly: open ground that's a climb (the route may wind for a reason there)
    hilly = ndimage.binary_closing(pool(hill) >= HILL_FRACTION, iterations=2) & (cells == 0)
    lab, n = ndimage.label(hilly)
    if n:
        sizes = np.bincount(lab.ravel())
        hilly &= sizes[lab] >= HILL_SPECK
    log(f"  [{continent}] passability grid {cells.shape[1]}x{cells.shape[0]} cells "
        f"({QUAD_YD * k:.2f} yd): {np.mean(cells == 2) * 100:.0f}% blocked, {np.mean(cells == 1) * 100:.0f}% water")
    return {"continent": continent, "tileX0": tx0, "tileY0": ty0, "cellYd": QUAD_YD * k, "cells": cells,
            "hilly": hilly, "deep": far & (cells == 2)}


def runs(row: np.ndarray) -> list[int]:
    """Run-length encoding: [end1, value1, end2, value2, ...] with 1-based inclusive ends."""
    out = []
    change = np.flatnonzero(np.diff(row.astype(np.int16))) + 1
    starts = np.concatenate([[0], change])
    ends = np.concatenate([change, [len(row)]])
    for s, e in zip(starts, ends):
        out += [int(e), int(row[s])]
    return out


SPECK = 6  # cells: smaller blocked bits and ponds are noise for routing
MIN_OPEN = 400  # cells (~170 yd square): smaller open pockets are ledges and plateaus inside mountains


def despeckle(cells: np.ndarray) -> np.ndarray:
    from scipy import ndimage

    out = cells.copy()

    def small(mask):
        lab, n = ndimage.label(mask)
        if n == 0:
            return np.zeros_like(mask)
        sizes = ndimage.sum(mask, lab, range(1, n + 1))
        return np.isin(lab, np.flatnonzero(sizes < SPECK) + 1)

    out[small(out == 2)] = 0  # lone steep cells on open ground
    # Close one-cell gaps in ridges, so straight lines can't slip through a mountain range.
    blocked = out == 2
    out[ndimage.binary_closing(blocked) & ~blocked] = 2
    # Open pockets enclosed by steep ground (ledges, plateaus, mountain tops) can't be reached.
    lab, n = ndimage.label(out != 2)
    if n:
        sizes = ndimage.sum(out != 2, lab, range(1, n + 1))
        out[np.isin(lab, np.flatnonzero(sizes < MIN_OPEN) + 1)] = 2
    out[small(out == 1)] = 0  # puddles
    return out


# Row encoding: printable characters, one per run of <= 21 cells.
ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
SHORT = 21


def encode_row(row: np.ndarray, short: int = SHORT, long: int = 3) -> str:
    """Runs as characters: ALPHABET[v * short + len - 1] for len <= short (and values that
    fit: 0 to 2 with the usual 21, 0 to 3 with a cave's 15), else '_' + str(v) + `long`
    base-64 digits of the length (3, or a cave's 2)."""
    out = []
    r = runs(row)
    prev = 0
    for i in range(0, len(r), 2):
        end, v = r[i], r[i + 1]
        n = end - prev
        prev = end
        if n <= short and (v + 1) * short < len(ALPHABET):
            out.append(ALPHABET[v * short + n - 1])
        else:
            assert n < 64 ** long, n
            out.append("_" + str(v) + "".join(ALPHABET[n >> 6 * k & 63] for k in range(long - 1, -1, -1)))
    return "".join(out)


def decode_row(text: str, short: int = SHORT, long: int = 3) -> list[int]:
    """Inverse of encode_row: the cell values (for tests)."""
    out, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch == "_":
            v = int(text[i + 1])
            n = 0
            for k in range(long):
                n = n << 6 | ALPHABET.index(text[i + 2 + k])
            i += 2 + long
        else:
            k = ALPHABET.index(ch)
            v, n = divmod(k, short)
            n += 1
            i += 1
        out += [v] * n
    return out


def terrain_lua(cd: ClientData, continents=None, log=print) -> str:
    if continents is None:
        from ..extract.pipeline import CONTINENTS as continents  # the shared list
    hills = []
    out = [f"-- GENERATED by `agps gen-addon-data` from client {cd.casc.version}. Do not edit by hand.",
           "-- Passability per continent for offroad routing: cells of cell yards, row = south,",
           "-- col = east, from terrain tile (tx0, ty0). Values: 0 open, 1 water, 2 blocked (too steep), `deep`",
           "-- (3) deep water far out (fatigue): blocked too.",
           "-- Each row is run-length encoded; see app/azerothgps/roads/terrain.py (encode_row).",
           "local _, ns = ...", "ns.Terrain = {"]
    for cont in continents:
        g = continent_grid(cd, cont, log)
        cells = g["cells"].copy()
        cells[g["deep"]] = DEEP_VALUE
        out.append(f"  [{cont}] = {{ tx0 = {g['tileX0']}, ty0 = {g['tileY0']}, cell = {g['cellYd']:.6f}, "
                   f"w = {cells.shape[1]}, h = {cells.shape[0]}, deep = {DEEP_VALUE}, rows = {{")
        for r in cells:
            out.append(f'    "{encode_row(r)}",')
        out.append("  } },")
        hills.append((cont, g))
    out.append("}")
    out.append("-- Hilly ground (open, but a climb: 1), the same grid: a route winding there may be taking")
    out.append("-- the slope the easy way, not just wobbling (Router.Smooth leaves it as it is).")
    out.append("ns.Hills = {")
    for cont, g in hills:
        m = g["hilly"]
        k = HILL_BLOCK
        H2, W2 = -(-m.shape[0] // k), -(-m.shape[1] // k)
        pad = np.zeros((H2 * k, W2 * k), bool)
        pad[: m.shape[0], : m.shape[1]] = m
        h = (pad.reshape(H2, k, W2, k).mean(axis=(1, 3)) >= 0.25).astype(np.uint8)
        out.append(f"  [{cont}] = {{ tx0 = {g['tileX0']}, ty0 = {g['tileY0']}, cell = {g['cellYd'] * k:.6f}, "
                   f"w = {h.shape[1]}, h = {h.shape[0]}, rows = {{")
        for r in h:
            out.append(f'    "{encode_row(r)}",')
        out.append("  } },")
    out.append("}")
    return "\n".join(out) + "\n"
