"""Thin tall walls from the client's model collision, shipped as hard barriers (Data/ModelWalls.lua, ns.ModelWalls).

Item 78 again (Kooki3z 2026-11-25, the 1.4.0 build): Red Cloud Mesa's palisade was "fixed" twice by cutting the
world grid's links at sampled heights (worldgrid.cut_wall_links, F_RIM_WALL) and each time the route jumped through the
next stretch of it. Now the footprint in plan view of every palisade, fence, barricade and railing on the map, from the
models' own collision triangles, is a barrier for every link that crosses it, whatever its kind or heights
(Passability.CrossesModelWall, Passability.CrossesWall; WorldGrid.Search's steps, far drops, road and drop links; the
Router's legs and spell jumps), and the bake drops the grid's links across them (worldbake.shipped_walls).

How the walls are found (`agps world-grid model-walls`, from every map tile's `<tile>.models.npy` and its walk mesh,
`agps world-grid models` and `mesh`):

1. `tile_cells`: each map tile's model triangles rasterized at RES yards. A cell is a wall's where the steep faces
   (worldgrid.WALL_STEEP_NZ) over it rise TALL_YD or more (a curb, a step, a rock's lip not); a cell is roofed where
   flat model faces lie TALL_YD or more over each other (a floor and a ceiling: inside a building).
2. `pieces`: the wall cells' 8-connected pieces, by blocks of REGION map tiles with a tile's ring round them (each piece
   once, by its corner cell's tile). Candidates: LONG_YD or more across and at most THIN_YD wide on average (a
   palisade, a fence, a barricade; a tent, a trunk, a hut not), with at most ROOF_SHARE of the ground round them roofed
   (a house's walls, which the walk mesh has and whose doors the grid's links stand for, not).
3. `refine`: the cells the walk mesh walks under left out (a floor HEAD_YD to UNDER_YD under the faces' lowest point,
   on the mesh or a model's floor: a gate's arch, a door's lintel, a beam over a road), the piece split there; each
   part kept when SUPPORT_SHARE of its cells have a walkable floor within 2 yd that the wall rises out of (from 1.5 yd
   under its lowest point to FOOT_TOP_YD under its top: a wall standing on ground players walk; a bridge's under-beams
   and a cliff's rocks, a floor at their top, not), still LONG_YD across and thin, and not
   a closed ring round more than RING_YD2 (a stone circle, a tree's ring of roots; a pen whose gate is shut a player
   can't reach anyway).
4. `outlines`: the capitals left out (their city grids have their own walls); every Router road and recorded walk
   (worldbake.recorded_walks) crossing a wall opens it PUNCH_YD either side (a road through a gate: the ways players
   walk are kept, a road never crosses a model wall: the Router's roads are cut by walls at load without them,
   Passability.CrossesWall's `noModel`); what's left of a piece kept from MIN_AFTER_YD across; each part's outline
   (skimage's contours, simplified within SIMPLIFY_CELLS) a closed wall line. A part within STOP_YD of a stop (an
   NPC's spawn, a dungeon's door: a stall's walls round its vendor) or OPEN_YD of one of OPEN's reviewed places (the
   coverage sweep's: a way through narrower than the grid's cells) is left out.

The data: per continent the outlines, each "x,y,dx,dy,..." in half yards, and by MODEL_REGION squares the outlines over
each (Passability decodes a square's the first time a route piece comes over it).

The known cases (test_model_walls_140.py): Red Cloud Mesa's palisade one piece, west cliffs to east rocks (the road from
Camp Narache leaves round its west end); Cragpool Lake's barricade across the pass (its road taken out in game, #996);
the Crossroads' and Razor Hill's fences with their road gaps open; Thunder Bluff left to its city grid; Southshore and
Dun Algaz (their walls are buildings' and the walk mesh's).
"""

from __future__ import annotations

import json
import math
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

RES = 0.5  # yards a raster cell's side
TALL_YD = 2.5  # the steep faces over a cell rise this much: a wall's body there
STEEP_NZ = 0.7  # (worldgrid.WALL_STEEP_NZ: a face this steep or steeper is a wall's)
LONG_YD = 15.0  # a piece's box diagonal at least this: a wall, not a post
THIN_YD = 3.0  # and its area over that diagonal at most this: thin (a hut, a tent, a rock not)
ROOF_SHARE = 0.15  # the ground 1-4 yd round a piece roofed at most this share: not a building's walls
HEAD_YD = 1.8  # a floor this far under the faces' lowest point or more: walked under (an arch, a lintel)
UNDER_YD = 12.0  # ... and at most this far (a floor far below is a cliff's foot, not under the wall)
SUPPORT_SHARE = 0.3  # a part's cells with a walkable floor at their foot (2 yd round), the wall rising out of it ...
FOOT_TOP_YD = 1.5  # ... this much at least
RING_YD2 = 12.0  # square yards: a piece closed round more than this is a ring, not a wall
PUNCH_YD = 1.5  # yards either side of a road or recorded walk where it crosses a wall: open
MIN_AFTER_YD = 4.0  # a punched piece's parts kept from this across (a fence's end by a gate)
SIMPLIFY_CELLS = 1.0  # outline points within this many cells of the line kept off
STOP_YD = 2.0  # a wall's part this near a stop (an NPC's spawn, a dungeon's door) is left out: a stop is reached
OPEN_YD = 2.0  # ... and this near a point of OPEN
# The coverage sweep's (`agps world-grid coverage`) stops these walls cut off, reviewed: where the grid's way to each
# went through one, its part left out ((cont, x, y) on the wall, why). A wall's way through narrower than the grid's
# cells (8.33 yd: a gate's, a ramp's between railings), or a stall's walls round its vendor.
OPEN = [
    (0, -12624.0, -111.0, "Se'Jib, Stranglethorn: his stall's walls"),
    (0, -11916.5, -1307.2, "Zul'Gurub's door: the gate's walls either side of the way in"),
    (0, -11916.0, -1157.0, "Zul'Gurub's door: the gate's walls either side of the way in"),
    (0, -7841.5, -3227.0, "Marshal Ryan, Burning Steppes: Morgan's Vigil's way up"),
    (0, -7817.8, -3209.0, "Marshal Ryan, Burning Steppes: Morgan's Vigil's way up"),
    (0, -7786.0, -3177.2, "Marshal Ryan, Burning Steppes: his post's walls"),
    (0, -2862.2, -1464.5, "Wenna Silkbeard, the Wetlands: her stall's walls"),
    (0, -2861.8, -1458.8, "Wenna Silkbeard, the Wetlands: her stall's walls"),
    (1, -6200.5, -3917.2, "Race Master Kronkrider, the Shimmering Flats: the stands' rails"),
    (1, -6179.0, -3876.2, "Race Master Kronkrider, the Shimmering Flats: the stands' rails"),
    (1, 2324.0, 1825.0, "Stonetalon Peak: the railings of the way up to the Cenarion druids"),
    (1, 2329.2, 1809.8, "Stonetalon Peak: the railings of the way up to the Cenarion druids"),
    (1, 2341.5, 1833.5, "Stonetalon Peak: the railings of the way up to the Cenarion druids"),
    (1, 2322.5, 1812.5, "Stonetalon Peak: the railings of the way up to the Cenarion druids"),
    (1, 2327.8, 1822.5, "Stonetalon Peak: the railings of the way up to the Cenarion druids"),
]
REGION = 8  # map tiles a block of the piece search (worldbake.REGION's)
MODEL_REGION = 512  # yards a square of the data's index (Passability.MODEL_REGION)
Q = 0.5  # yards a unit of the outlines' numbers
O = -32 * 533.3333333333334  # (the raster's origin, world yards: cell i's x from O + i RES)
PARAMS = ("RES", "TALL_YD", "STEEP_NZ", "LONG_YD", "THIN_YD", "ROOF_SHARE", "HEAD_YD", "UNDER_YD", "SUPPORT_SHARE", "FOOT_TOP_YD",
          "RING_YD2", "PUNCH_YD", "MIN_AFTER_YD", "SIMPLIFY_CELLS", "STOP_YD", "OPEN_YD")
CONTS = (0, 1, 2991)


# --- 1. each tile's raster ----------------------------------------------------------------------------------------------

def _faces(T: np.ndarray, steep: bool) -> np.ndarray:
    e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    n = np.cross(e1, e2)
    ln = np.linalg.norm(n, axis=1)
    ok = ln > 1e-6
    nz = np.ones(len(T))
    nz[ok] = np.abs(n[ok, 2]) / ln[ok]
    return T[ok & ((nz < STEEP_NZ) if steep else (nz >= STEEP_NZ))]


def raster(S: np.ndarray, i0: int, j0: int, nx: int, ny: int):
    """The lowest and highest point of triangles S over each cell of the raster (rows by x from cell i0, columns by y
    from j0): (zlo, zhi), inf / -inf where none. Each triangle sampled every half cell; samples off the raster dropped."""
    zlo = np.full(nx * ny, np.inf, np.float32)
    zhi = np.full(nx * ny, -np.inf, np.float32)
    if not len(S):
        return zlo.reshape(nx, ny), zhi.reshape(nx, ny)
    L = np.max(np.ptp(S, axis=1), axis=1)
    n = np.maximum(2, (L / (RES / 2)).astype(int) + 2)
    for k in np.unique(n):
        G = S[n == k]
        u, v = np.meshgrid(np.linspace(0, 1, k), np.linspace(0, 1, k))
        m = (u + v) <= 1
        u, v = u[m], v[m]
        step = max(1, 2_000_000 // len(u))
        for a in range(0, len(G), step):
            g = G[a:a + step]
            P = (g[:, None, 0] + u[None, :, None] * (g[:, None, 1] - g[:, None, 0])
                 + v[None, :, None] * (g[:, None, 2] - g[:, None, 0])).reshape(-1, 3)
            i = np.floor((P[:, 0] - O) / RES).astype(np.int64) - i0
            j = np.floor((P[:, 1] - O) / RES).astype(np.int64) - j0
            ok = (i >= 0) & (i < nx) & (j >= 0) & (j < ny)
            idx = i[ok] * ny + j[ok]
            z = P[ok, 2].astype(np.float32)
            np.minimum.at(zlo, idx, z)
            np.maximum.at(zhi, idx, z)
    return zlo.reshape(nx, ny), zhi.reshape(nx, ny)


def tile_cells(job):
    """A map tile's wall cells (global raster indices, the steep faces' low and high points, the lowest flat face
    there) and its roofed cells: ((cont, tx, ty), (ii, jj, zlo, zhi, zflat, ri, rj)) or None without models."""
    from . import worldmesh as WM
    cont, tx, ty = job
    p = WM.models_path(cont, tx, ty)
    if not p.exists():
        return job, None
    T = np.load(p).astype(np.float64)
    x0, y0, x1, y1 = WM.tile_box(tx, ty)
    ci0, ci1 = int(math.ceil((x0 - O) / RES - 1e-6)), int(math.ceil((x1 - O) / RES - 1e-6))
    cj0, cj1 = int(math.ceil((y0 - O) / RES - 1e-6)), int(math.ceil((y1 - O) / RES - 1e-6))
    nx, ny = ci1 - ci0, cj1 - cj0
    zlo, zhi = raster(_faces(T, True), ci0, cj0, nx, ny)
    flo, fhi = raster(_faces(T, False), ci0, cj0, nx, ny)
    ii, jj = np.nonzero((zhi - zlo) >= TALL_YD)
    ri, rj = np.nonzero((fhi - flo) >= TALL_YD)
    return job, ((ii + ci0).astype(np.int32), (jj + cj0).astype(np.int32), zlo[ii, jj], zhi[ii, jj], flo[ii, jj],
                 (ri + ci0).astype(np.int32), (rj + cj0).astype(np.int32))


# --- 2. pieces ----------------------------------------------------------------------------------------------------------

def _shape(m: np.ndarray) -> tuple:
    """(box diagonal, area over it, the biggest enclosed hole's area) of a piece's cells, yards."""
    from scipy import ndimage
    h, w = m.shape
    diag = math.hypot(h * RES, w * RES)
    filled = ndimage.binary_fill_holes(m)
    lab, n = ndimage.label(filled & ~m)
    hole = float(np.bincount(lab.ravel())[1:].max()) * RES * RES if n else 0.0
    return diag, m.sum() * RES * RES / diag, hole


def pieces(cells: dict, cont: int, log=print) -> list:
    """The continent's candidate pieces: [{i0, j0, m (cells), z, zh, zf}] (step 2)."""
    from scipy import ndimage

    from . import worldmesh as WM
    tiles = {(tx, ty): r for (c, tx, ty), r in cells.items() if c == cont and r is not None and len(r[0])}
    blocks = defaultdict(list)
    for tx, ty in tiles:
        blocks[(tx // REGION, ty // REGION)].append((tx, ty))
    out, seen = [], 0
    for _b, ts in sorted(blocks.items()):
        core = set(ts)
        win = {(tx + a, ty + b) for tx, ty in ts for a in (-1, 0, 1) for b in (-1, 0, 1)} & set(tiles)
        cat = [np.concatenate([tiles[t][k] for t in win]) for k in range(7)]
        I, J = cat[0], cat[1]
        i0, j0 = int(I.min()) - 1, int(J.min()) - 1
        shape = (int(I.max()) - i0 + 2, int(J.max()) - j0 + 2)
        A = np.zeros(shape, bool)
        A[I - i0, J - j0] = True
        Z = [np.full(shape, np.nan, np.float32) for _ in range(3)]
        for k in range(3):
            Z[k][I - i0, J - j0] = cat[2 + k]
        RI, RJ = cat[5] - i0, cat[6] - j0
        ok = (RI >= 0) & (RI < shape[0]) & (RJ >= 0) & (RJ < shape[1])
        roof = np.zeros(shape, bool)
        roof[RI[ok], RJ[ok]] = True
        lab, _n = ndimage.label(A, structure=np.ones((3, 3)))
        for k, sl in enumerate(ndimage.find_objects(lab), 1):
            gi, gj = sl[0].start + i0, sl[1].start + j0
            if WM.tile_of(O + (gi + 0.5) * RES, O + (gj + 0.5) * RES) not in core:
                continue
            seen += 1
            m = lab[sl] == k
            h, w = m.shape
            diag = math.hypot(h * RES, w * RES)
            if diag < LONG_YD or m.sum() * RES * RES / diag > THIN_YD:
                continue
            P = 8  # (cells: 4 yd round)
            s2 = (slice(max(0, sl[0].start - P), sl[0].stop + P), slice(max(0, sl[1].start - P), sl[1].stop + P))
            mm = lab[s2] == k
            band = ndimage.binary_dilation(mm, iterations=P) & ~ndimage.binary_dilation(mm, iterations=2)
            if band.any() and roof[s2][band].mean() > ROOF_SHARE:
                continue
            out.append({"i0": gi, "j0": gj, "m": m, "z": Z[0][sl][m], "zh": Z[1][sl][m], "zf": Z[2][sl][m]})
    log(f"  cont {cont}: {seen} pieces of wall cells, {len(out)} long, thin and unroofed")
    return out


# --- 3. refined against the walk mesh ----------------------------------------------------------------------------------

_MESH: dict = {}
MESH_BUCKET = 8.0


def _mesh_tile(cont: int, tx: int, ty: int):
    from . import worldmesh as WM
    k = (cont, tx, ty)
    if k not in _MESH:
        if len(_MESH) > 200:
            _MESH.clear()
        polys, idx = [], defaultdict(list)
        p = WM.tile_path(cont, tx, ty)
        if p.exists() and p.stat().st_size >= 12:
            for vs, _ns, area in WM.parse(p.read_bytes()):
                if not area:
                    continue
                polys.append(vs)
                lo, hi = vs.min(0), vs.max(0)
                for bx in range(int(lo[0] // MESH_BUCKET), int(hi[0] // MESH_BUCKET) + 1):
                    for by in range(int(lo[1] // MESH_BUCKET), int(hi[1] // MESH_BUCKET) + 1):
                        idx[(bx, by)].append(len(polys) - 1)
        _MESH[k] = (polys, idx)
    return _MESH[k]


def _polys_near(cont: int, x0, x1, y0, y1) -> list:
    from . import worldmesh as WM
    t0, t1 = WM.tile_of(x1, y1), WM.tile_of(x0, y0)
    out, seen = [], set()
    for tx in range(min(t0[0], t1[0]), max(t0[0], t1[0]) + 1):
        for ty in range(min(t0[1], t1[1]), max(t0[1], t1[1]) + 1):
            polys, idx = _mesh_tile(cont, tx, ty)
            for bx in range(int(x0 // MESH_BUCKET), int(x1 // MESH_BUCKET) + 1):
                for by in range(int(y0 // MESH_BUCKET), int(y1 // MESH_BUCKET) + 1):
                    for pi in idx.get((bx, by), ()):
                        if (tx, ty, pi) not in seen:
                            seen.add((tx, ty, pi))
                            out.append(polys[pi])
    return out


def mesh_floor(cont: int, X, Y, LO, HI, r: float = 2.0) -> np.ndarray:
    """Which points (X, Y) have a walkable mesh floor at a height in [LO, HI] there or r yards round (8 ways)."""
    out = np.zeros(len(X), bool)
    offs = [(0.0, 0.0)] + ([(r * math.cos(a), r * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 8, endpoint=False)]
                           if r else [])
    polys = _polys_near(cont, X.min() - r, X.max() + r, Y.min() - r, Y.max() + r)
    for ox, oy in offs:
        x0, y0 = X + ox, Y + oy
        for vs in polys:
            lo, hi = vs.min(0), vs.max(0)
            sel = np.nonzero((x0 >= lo[0]) & (x0 <= hi[0]) & (y0 >= lo[1]) & (y0 <= hi[1]) & ~out)[0]
            if not len(sel):
                continue
            x, y = x0[sel], y0[sel]
            a = vs[0]
            for q in range(1, len(vs) - 1):
                b, c = vs[q], vs[q + 1]
                d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
                if abs(d) < 1e-9:
                    continue
                l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / d
                l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / d
                inside = (l1 >= -1e-6) & (l2 >= -1e-6) & (1 - l1 - l2 >= -1e-6)
                h = l1 * a[2] + l2 * b[2] + (1 - l1 - l2) * c[2]
                out[sel[inside & (h >= LO[sel]) & (h <= HI[sel])]] = True
    return out


def refine(job) -> list:
    """A candidate's parts kept (step 3): [{i0, j0, m}] (a worker's job: (cont, piece))."""
    from scipy import ndimage
    cont, p = job
    m = p["m"].copy()
    ii, jj = np.nonzero(m)
    X = O + (p["i0"] + ii + 0.5) * RES
    Y = O + (p["j0"] + jj + 0.5) * RES
    z, zh, zf = p["z"].astype(float), p["zh"].astype(float), p["zf"].astype(float)
    under = mesh_floor(cont, X, Y, z - UNDER_YD, z - HEAD_YD, 0) | ((zf <= z - HEAD_YD) & (zf >= z - UNDER_YD))
    # (a floor the wall rises out of: from 1.5 yd under its lowest point (posts sunk in the ground, Cragpool Lake's
    # barricade) to FOOT_TOP_YD under its top; a deck at a beam's top, a ledge at a rock's top, is no foot)
    foot = mesh_floor(cont, X, Y, z - 1.5, zh - FOOT_TOP_YD)
    S = np.zeros(m.shape, bool)
    S[ii[foot], jj[foot]] = True
    m[ii[under], jj[under]] = False
    lab, _n = ndimage.label(m, structure=np.ones((3, 3)))
    out = []
    for k, sl in enumerate(ndimage.find_objects(lab), 1):
        mm = lab[sl] == k
        if S[sl][mm].mean() < SUPPORT_SHARE:
            continue
        diag, thin, hole = _shape(mm)
        if diag >= LONG_YD and thin <= THIN_YD and hole <= RING_YD2:
            out.append({"i0": p["i0"] + sl[0].start, "j0": p["j0"] + sl[1].start, "m": mm})
    return out


# --- 4. outlines --------------------------------------------------------------------------------------------------------

_NS: list = []


def _ns():
    """The addon under the game harness (one for the run)."""
    if not _NS:
        from .gameharness import start
        _NS.append(start()[1])
    return _NS[0]


def ways(cont: int) -> list:
    """The ways players walk through walls: every Router road (all its sources, the capitals' too) and recorded walk,
    [[(x, y), ...]]."""
    from . import worldbake
    R = _ns().Router
    R.NearestEdges(cont, 0, 0)
    g = R.DebugGraph(cont)
    out = []
    for eid in g.e.keys():
        e = g.e[eid]
        pts = [(float(e[k]), float(e[k + 1])) for k in range(5, len(e) + 1, 2) if e[k] is not None and e[k + 1] is not None]
        if len(pts) >= 2:
            out.append(pts)
    out += [[(p[0], p[1]) for p in w[2]] for w in worldbake.recorded_walks(cont)]
    return out


def _seg_dist(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy
    t = np.clip(((px - ax) * vx + (py - ay) * vy) / L2, 0, 1) if L2 > 1e-9 else np.zeros_like(px)
    return np.hypot(ax + vx * t - px, ay + vy * t - py)


def stops(cont: int) -> list:
    """The points no wall may cut off: every stop outside the capitals (worldbake.stop_spots) and OPEN's: [(x, y, yd)]."""
    from . import worldbake
    _ns()
    return ([(x, y, STOP_YD) for x, y, _z, _n in worldbake.stop_spots(cont)]
            + [(x, y, OPEN_YD) for c, x, y, _why in OPEN if c == cont])


def outlines(cont: int, parts: list, roads: list, log=print) -> list:
    """The parts' outlines (step 4): [[(x, y), ...]] each closed."""
    from scipy import ndimage
    from skimage import measure

    R = _ns().Router
    keep_open = defaultdict(list)
    for x, y, r in stops(cont):
        keep_open[(int(x // 32), int(y // 32))].append((x, y, r))
    B = 32.0
    idx = defaultdict(list)
    for pts in roads:
        for q in range(len(pts) - 1):
            (ax, ay), (bx, by) = pts[q], pts[q + 1]
            for kx in range(int(min(ax, bx) // B), int(max(ax, bx) // B) + 1):
                for ky in range(int(min(ay, by) // B), int(max(ay, by) // B) + 1):
                    idx[(kx, ky)].append((ax, ay, bx, by))
    out, capital, punched, by_stop = [], 0, 0, 0
    for p in parts:
        m = p["m"].copy()
        ii, jj = np.nonzero(m)
        X = O + (p["i0"] + ii + 0.5) * RES
        Y = O + (p["j0"] + jj + 0.5) * RES
        if any(R.CapitalAt(cont, float(x), float(y)) for x, y in ((X.mean(), Y.mean()), (X[0], Y[0]), (X[-1], Y[-1]))):
            capital += 1
            continue
        near = set()
        for kx in range(int((X.min() - PUNCH_YD) // B), int((X.max() + PUNCH_YD) // B) + 1):
            for ky in range(int((Y.min() - PUNCH_YD) // B), int((Y.max() + PUNCH_YD) // B) + 1):
                near.update(idx.get((kx, ky), ()))
        cut = np.zeros(len(X), bool)
        for s in near:
            cut |= _seg_dist(X, Y, *s) <= PUNCH_YD
        if cut.any():
            punched += 1
            m[ii[cut], jj[cut]] = False
        lab, _n = ndimage.label(m, structure=np.ones((3, 3)))
        for k, sl in enumerate(ndimage.find_objects(lab), 1):
            mm = lab[sl] == k
            h, w = mm.shape
            if math.hypot(h * RES, w * RES) < (MIN_AFTER_YD if cut.any() else LONG_YD):
                continue
            i0, j0 = p["i0"] + sl[0].start, p["j0"] + sl[1].start
            qi, qj = np.nonzero(mm)
            QX, QY = O + (i0 + qi + 0.5) * RES, O + (j0 + qj + 0.5) * RES
            near_stop = False
            for kx in range(int((QX.min() - 4) // 32), int((QX.max() + 4) // 32) + 1):
                for ky in range(int((QY.min() - 4) // 32), int((QY.max() + 4) // 32) + 1):
                    for x, y, r in keep_open.get((kx, ky), ()):
                        if np.min(np.hypot(QX - x, QY - y)) <= r:
                            near_stop = True
            if near_stop:  # (a stall's walls round its vendor, a gate narrower than the grid's cells: OPEN)
                by_stop += 1
                continue
            hl, _hn = ndimage.label(ndimage.binary_fill_holes(mm) & ~mm)
            for q, hs in enumerate(ndimage.find_objects(hl), 1):  # (a post's hollow: filled)
                if (hl[hs] == q).sum() * RES * RES <= 4.0:
                    mm[hs] |= hl[hs] == q
            for c in measure.find_contours(np.pad(mm, 1).astype(float), 0.5, fully_connected="high"):
                c = measure.approximate_polygon(c, SIMPLIFY_CELLS)
                pts = []
                for a, b in c:
                    q_ = (round((O + (i0 + a - 0.5) * RES) / Q), round((O + (j0 + b - 0.5) * RES) / Q))
                    if not pts or pts[-1] != q_:
                        pts.append(q_)
                if len(pts) >= 3:
                    if pts[0] != pts[-1]:
                        pts.append(pts[0])
                    w_ = [(x * Q, y * Q) for x, y in pts]
                    if any(R.CapitalAt(cont, x, y) for x, y in w_):  # (a wall reaching into a capital: its city grid's)
                        capital += 1
                        continue
                    out.append(w_)
    log(f"  cont {cont}: {len(parts)} walls, {capital} in the capitals left out, {punched} opened where a road or "
        f"recorded walk goes through, {by_stop} parts by a stop or OPEN's places left out; {len(out)} outlines, "
        f"{sum(len(w) for w in out)} points")
    return out


def build(conts=CONTS, workers: int = 8, log=print) -> dict:
    """{cont: [outline, ...]} for the whole map (needs the models' triangles and the meshes: `agps world-grid models`,
    `mesh`)."""
    import multiprocessing as mp

    from . import worldmesh as WM
    out = {}
    for cont in conts:
        t0 = time.time()
        jobs = []
        for p in WM.mesh_dir().glob(f"{cont}_*.models.npy"):
            c, tx, ty = map(int, p.name.split(".")[0].split("_"))
            jobs.append((c, tx, ty))
        with mp.get_context("spawn").Pool(workers) as pool:
            cells = dict(pool.imap_unordered(tile_cells, jobs, chunksize=4))
        log(f"  cont {cont}: {len(jobs)} tiles rasterized ({time.time() - t0:.0f} s)")
        cand = pieces(cells, cont, log)
        del cells
        with mp.get_context("spawn").Pool(workers) as pool:
            parts = [q for r in pool.imap_unordered(refine, [(cont, p) for p in cand], chunksize=8) for q in r]
        log(f"  cont {cont}: {len(parts)} walls the walk mesh says stand on its ground ({time.time() - t0:.0f} s)")
        out[cont] = outlines(cont, parts, ways(cont), log)
    return out


# --- the data -----------------------------------------------------------------------------------------------------------

def encode(w: list) -> str:
    """An outline as "x,y,dx,dy,..." in Q yards."""
    q = [(int(round(x / Q)), int(round(y / Q))) for x, y in w]
    vals = [q[0][0], q[0][1]]
    for (ax, ay), (bx, by) in zip(q, q[1:]):
        vals += [bx - ax, by - ay]
    return ",".join(str(v) for v in vals)


def regions_of(walls: list) -> dict:
    """{rx * 4096 + ry: [outline index, 1-based]}: the MODEL_REGION squares each outline's box is over."""
    out = defaultdict(list)
    for k, w in enumerate(walls, 1):
        xs, ys = [p[0] for p in w], [p[1] for p in w]
        for rx in range(math.floor(min(xs) / MODEL_REGION), math.floor(max(xs) / MODEL_REGION) + 1):
            for ry in range(math.floor(min(ys) / MODEL_REGION), math.floor(max(ys) / MODEL_REGION) + 1):
                out[rx * 4096 + ry].append(k)
    return out


def stamp() -> str:
    return ",".join(f"{k}={globals()[k]:g}" for k in PARAMS)


def lua_text(walls: dict) -> str:
    lines = ["-- GENERATED by `agps world-grid model-walls --write` (app/azerothgps/modelwalls.py). Do not edit by hand.",
             "-- Thin tall walls from the client's model collision (palisades, fences, barricades): each a closed outline",
             "-- in plan view, a hard barrier for every route piece that crosses one (Passability.CrossesModelWall,",
             "-- Passability.CrossesWall). Per continent: `w` the outlines (x, y, then each point's step, in half yards),",
             f"-- `r` [rx * 4096 + ry] = the outlines over that {MODEL_REGION} yd square (decoded the first time a route comes over it).",
             "local _, ns = ...",
             f'ns.ModelWalls = {{ stamp = "{stamp()}",']
    for cont in sorted(walls):
        ws = walls[cont]
        lines.append(f"  [{cont}] = {{")
        lines.append("    w = {")
        for w in ws:
            lines.append(f'      "{encode(w)}",')
        lines.append("    },")
        lines.append("    r = {")
        for key, ks in sorted(regions_of(ws).items()):
            lines.append(f"      [{key}] = {{ {','.join(str(k) for k in ks)} }},")
        lines.append("    },")
        lines.append("  },")
    lines.append("}")
    return "\n".join(lines) + "\n"


def write(walls: dict, addon_dir: Path | None = None) -> Path:
    from .paths import ADDON_DIR
    p = Path(addon_dir or ADDON_DIR) / "Data" / "ModelWalls.lua"
    p.write_text(lua_text(walls), encoding="utf-8", newline="\n")
    return p


def save_json(walls: dict, path: Path) -> None:
    path.write_text(json.dumps({str(c): w for c, w in walls.items()}), encoding="utf-8")


def segments(walls: dict, cont: int) -> list:
    """The walls' segments on `cont`: [(ax, ay, bx, by)]."""
    out = []
    for w in walls.get(cont, []):
        for (ax, ay), (bx, by) in zip(w, w[1:]):
            out.append((ax, ay, bx, by))
    return out


def summary(walls: dict) -> str:
    return json.dumps({c: [len(w) for w in ws] for c, ws in walls.items()})
