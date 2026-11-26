"""The open world's layered walk grid (asked 2026-11-22: "do the same logic used for city grid for the entire map",
with "current road data in the open world, give it a slightly higher weight for road preference (only open world, cities
are wiped using city grid routing only)"; docs/world-grid-1.4.0.md).

The city grid's recipe (citygrid.py) over both continents, from our own Recast meshes of every map tile
(worldmesh.py, `agps world-grid mesh`; dev data, never shipped):

1. **Surfaces** per cell (CELL yards, aligned to the map tiles: 128 a tile at 4.17 yd), each walkable poly touching a
   cell a surface at its height there, joined polys within citygrid.MERGE_Z one (citygrid.rasterize / merge_cell).
2. **Links** to the 8 neighbors' surfaces where the mesh joins them and the climb fits (citygrid.build_links), across
   the map tiles' seams too (each tile is built with a ring of its neighbors' cells; a link into the ring is matched to
   the neighbor tile's own surface at that height).
3. **Water** (Recast doesn't swim): a cell over the terrain grid's water (Data/Terrain.lua's 1, so its closed sea stays
   closed) with no mesh surface near the water's top gets a swim surface at the top (KIND_SWIM), linked to the water
   round it and to the shore's surfaces within SHORE_Z.
4. **Roads** (the open world's only: inside the capitals the city grid routes, so no city road is taken): the land's
   roads of the Router's graph are walked every yard; the surfaces they cross (within ROAD_HALF_YD) are road ground,
   a yard there costing ROAD_PREF (a little cheaper: routes keep to roads when about as short); where a road leaves the
   grid and comes back with no way between on it within citygrid.ROAD_DETOUR, the road's stretch is a road link
   (citygrid.road_links: a bridge deck, a ledge, a gate the mesh lacks).
5. **Pruning:** pieces smaller than MIN_PIECE surfaces that no road touches (roofs, rocks' tops) are left out.

Shipped as numbers only (Data/WorldGrid0.lua, WorldGrid1.lua; read by WorldGrid.lua): see `encode_tile`.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from . import citygrid as CGP
from . import navmesh as NM
from . import worldmesh as WM
from .paths import ADDON_DIR, data_dir

CELL_PER_TILE = 64  # cells a map tile's side: 8.33 yd, the terrain grid's (128: 4.17 yd, four times the surfaces and
# the file; `agps world-grid bake --per 128` to compare)
SHORE_Z = 1.5  # yards: a swim surface and a land surface this near in height join (the shore, a wade)
MIN_PIECE = 200  # surfaces: smaller pieces no road touches are left out (a roof, a rock's top, a ledge)
ROAD_HALF_YD = 3.0  # yards either side of a road's line its ground is road ground
ROAD_PREF = 0.70  # a yard of road ground costs this many (the open world's roads preferred; the cleanest of 0.70-1.0 at Road tolerance +3, docs/world-grid-1.4.0.md)
SWIM_COST = 1.5  # a yard swum (Passability.SWIM_COST)
KIND_GROUND, KIND_SWIM = 0, 1
FLAG_ROAD = 2
ALPHA = CGP.ALPHA
DIRS = CGP.DIRS


def cell_yd(per_tile: int = CELL_PER_TILE) -> float:
    return WM.T / per_tile


def tile_origin(tx: int, ty: int, per_tile: int = CELL_PER_TILE) -> tuple:
    """A tile's first cell, global (gx, gy): gx = floor(X / cell), gy = floor(Y / cell)."""
    return (31 - ty) * per_tile, (31 - tx) * per_tile


def tile_of_cell(gx: int, gy: int, per_tile: int = CELL_PER_TILE) -> tuple:
    return 31 - gy // per_tile, 31 - gx // per_tile


# --- one tile's grid ---------------------------------------------------------------------------------------------------

HOPS = int(os.environ.get("AGPS_WG_HOPS", CGP.HOPS))  # polys this many links apart join two cells' surfaces (the
# city grid's 2; tried against 1 for these bigger cells: docs/world-grid-1.4.0.md)


class _Mesh(CGP.Mesh):
    def near(self, pid: int) -> set:
        s = self._near.get(pid)
        if s is None:
            s, frontier = {pid}, {pid}
            for _ in range(HOPS):
                nxt = set()
                for p in frontier:
                    nxt |= self.nb[p]
                nxt -= s
                s |= nxt
                frontier = nxt
            self._near[pid] = s
        return s


def _mesh(polys, nbs):
    """The tile's mesh as citygrid.Mesh (its walkable polys only; `near` by HOPS), with each poly's edges' neighbors
    (`ens`: the poly across each edge, -1 none (the mesh's edge), -2 one of `nb` (a sub-tile's side))."""
    m = _Mesh.__new__(_Mesh)
    keep = [i for i, p in enumerate(polys) if p[2]]
    new = {o: n for n, o in enumerate(keep)}
    m.keys = keep
    # (Python floats: numpy's scalars made the mesh walk about 3x slower)
    m.vs = [[tuple(map(float, v)) for v in polys[o][0]] for o in keep]
    m.nb = [{new[q] for q in nbs[o] if q in new} for o in keep]
    m.ens = [[new.get(q, -1) if q >= 0 else q for q in polys[o][1]] for o in keep]
    m.box = [(min(v[0] for v in vs), min(v[1] for v in vs), max(v[0] for v in vs), max(v[1] for v in vs)) for vs in m.vs]
    m._near = {}
    return m


# --- the mesh walk: whether a grid link is walked on the mesh (asked 2026-11-22: no impossible climbs) ----------------

def _nav_const(name: str, default: float) -> float:
    import re
    txt = (ADDON_DIR / "Nav.lua").read_text(encoding="utf-8")
    m = re.search(r"^N\.%s = ([\d.]+)" % name, txt, re.M)
    return float(m.group(1)) if m else default


# yards: the highest drop off a ledge a link is baked for. Nav.SafeDrop out of combat with the health hidden is about 39
# (FALL_FREE and what FALL_SECRET_HEALTH over FALL_KEEP buys at FALL_PER_YD: SAFE_DROP_HIDDEN); the data goes to 60 so the
# drops a fall spell makes safe (Slow Fall, Levitate, a parachute) are there too. At route time the player's own
# SafeDrop decides (WorldGrid.lua's x.maxDrop: a drop past it is never taken).
SAFE_DROP_HIDDEN = _nav_const("FALL_FREE", 14) + max(0.0, _nav_const("FALL_SECRET_HEALTH", 0.8) - _nav_const("FALL_KEEP", 0.3)) / _nav_const("FALL_PER_YD", 0.02)
DROP_MAX = 60.0
# yards: the highest one-way drop off a ledge the walked links are baked for (bake8, for Expert jumper: a fall spell
# makes a drop of any height safe, FallSpells.lua's DROP_CAP 400 the most taken). Drops only: a climb is the mesh's,
# and the roads' and recorded walks' links keep DROP_MAX (worldbake.py). The game takes a drop only within the
# player's own safe drop (WorldGrid.lua's x.maxDrop), so a bigger one costs nothing to anyone without a fall spell.
DROP_FAR = float(os.environ.get("AGPS_WG_DROP_FAR", "400"))  # (the env: a trial's)
DROP_MIN = 1.5  # yards: a step off a poly's edge onto one this much lower or more is a drop (less: Recast's own climb)
# A sheer cliff: its foot's floor starts the agent's room (and more) off the face, not under the top's edge, so a drop
# off it is looked for on along the line, up to DROP_SCAN_YD, onto a floor DROP_SCAN_MIN or more under the edge (a
# fall only a fall spell or Expert jumper makes: no wall's other side, a step or two lower, is ever one). bake9:
# Skywatcher Plateau's east edge, 130 yd over Mulgore's plain, had no drop link at all.
DROP_SCAN_YD = 3.0
DROP_SCAN_MIN = 40.0
# A drop's landing never under another floor between the edge's height and its own (DROP_CLEAR_Z over the foot): a fall
# through the ground or a floor (bake9: the Barrens' ridge, 208, straight down 176 yd into Darkmist Cavern's tunnels,
# the ridge's own ground over them).
DROP_CLEAR_Z = 2.5
DROP_CLEAR_MIN = 20.0  # yards: only a drop this big is checked so (a step down under a tower's ramp is no fall)


def _clear_over(mesh, polys, px, py, hq, h):
    """Whether no poly of `polys` at (px, py) lies between hq + DROP_CLEAR_Z and h + DROP_CLEAR_Z (a floor fallen through,
    or ground going on past the edge at its height, a piece of its own over the foot)."""
    for q in polys:
        if _inside(mesh, q, px, py):
            hz = NM._height_on(mesh.vs[q], px, py)
            if hq + DROP_CLEAR_Z < hz < h + DROP_CLEAR_Z:
                return False
    return True
WALK_END_Z = 2.5  # yards: the walk arrives on the neighbor's surface with a poly of it or one this near its height
WALK, DROP = 1, 2


def _poly_at(mesh, pids, x, y, z):
    """Of polys `pids`, the one at (x, y) whose height there is nearest z (none containing it: the nearest across)."""
    best, bk = None, None
    for p in pids:
        vs = mesh.vs[p]
        if NM._in_poly(vs, x, y):
            k = (0, abs(NM._height_on(vs, x, y) - z))
        else:
            k = (1, NM._dist2_poly(vs, x, y))
        if bk is None or k < bk:
            best, bk = p, k
    return best


def _inside(mesh, q, x, y):
    b = mesh.box[q]
    return b[0] - 1e-6 <= x <= b[2] + 1e-6 and b[1] - 1e-6 <= y <= b[3] + 1e-6 and NM._in_poly(mesh.vs[q], x, y)


def _sign(vs) -> float:
    """1 for a poly wound counter-clockwise (its area's sign), else -1."""
    n = len(vs)
    area = 0.0
    for k in range(n):
        area += vs[k][0] * vs[(k + 1) % n][1] - vs[(k + 1) % n][0] * vs[k][1]
    return 1.0 if area >= 0 else -1.0


def _exit(vs, ax, ay, bx, by, t0, sg=None):
    """Where the segment (a, b) leaves convex poly vs after t0: (t, edge), t > 1 when it doesn't before b. `sg`: vs's
    _sign, when known."""
    n = len(vs)
    if sg is None:
        sg = _sign(vs)
    best, be = 2.0, -1
    for k in range(n):
        a, b = vs[k], vs[(k + 1) % n]
        c0 = sg * ((b[0] - a[0]) * (ay - a[1]) - (b[1] - a[1]) * (ax - a[0]))
        c1 = sg * ((b[0] - a[0]) * (by - a[1]) - (b[1] - a[1]) * (bx - a[0]))
        if c1 < c0 and c1 < 0:  # (going out over this edge's line)
            t = c0 / (c0 - c1)
            if t >= t0 - 1e-7 and t < best:
                best, be = t, k
    return best, be


def mesh_walk(mesh, near_polys, p0, pid0, p1, tpids, tz, drop_max=None):
    """Walks the mesh straight from p0 (x, y, z) on poly pid0 to (x1, y1) of p1: WALK (poly to joined poly the whole way,
    arriving on one of `tpids` or one within WALK_END_Z of tz), DROP (the same, but off a mesh's edge onto a poly
    DROP_MIN to drop_max lower once or more: one way down), or None (a wall, a ledge up, nothing there).
    `near_polys(x, y)`: the polys round a spot (for the floor under a ledge)."""
    drop_max = DROP_MAX if drop_max is None else drop_max
    ax, ay = p0[0], p0[1]
    bx, by = p1[0], p1[1]
    L = math.hypot(bx - ax, by - ay)
    if L < 1e-6:
        return WALK
    eps = min(0.02, 0.05 / L)
    cur, t, how = pid0, 0.0, WALK
    sgs = mesh.__dict__.get("sg")
    if sgs is None:
        sgs = mesh.sg = [None] * len(mesh.vs)  # (each poly's _sign, worked out once)
    for _ in range(300):
        vs = mesh.vs[cur]
        sg = sgs[cur]
        if sg is None:
            sg = sgs[cur] = _sign(vs)
        te, k = _exit(vs, ax, ay, bx, by, t, sg)
        if te >= 1.0 or k < 0:
            # (arrived: on one of the surface's polys, or one joined to them within HOPS links at about its height.
            # Not by the height alone: a surface's point on a corner two pieces of the mesh share (a wall's end) was
            # arrived at from the other piece, and Gurubashi Arena's Battle Ring was walked into through its wall, bake8)
            if cur in tpids or (abs(NM._height_on(vs, bx, by) - tz) <= WALK_END_Z and not mesh.near(cur).isdisjoint(tpids)):
                return how
            return None
        hx, hy = ax + (bx - ax) * te, ay + (by - ay) * te
        h = NM._height_on(vs, hx, hy)
        t = te + eps
        yx, yy = ax + (bx - ax) * t, ay + (by - ay) * t
        nxt = None
        e = mesh.ens[cur][k] if k < len(mesh.ens[cur]) else -2
        if e >= 0:
            nxt = e  # (Recast's own neighbor across that edge)
        elif e == -2:
            best = None
            for q in mesh.nb[cur]:
                if _inside(mesh, q, yx, yy):
                    d = abs(NM._height_on(mesh.vs[q], yx, yy) - h)
                    if best is None or d < best:
                        nxt, best = q, d
            if nxt is None:
                # (past a corner of the poly: its neighbors' neighbors)
                for r in mesh.nb[cur]:
                    for q in mesh.nb[r]:
                        if q != cur and _inside(mesh, q, yx, yy) and abs(NM._height_on(mesh.vs[q], yx, yy) - h) <= 2.0:
                            nxt = q
                            break
                    if nxt is not None:
                        break
        if nxt is None:
            # (off the mesh's edge: a drop onto a poly under it, the highest within reach)
            hi = None
            box = mesh.box
            near = near_polys(yx, yy)
            for q in near:
                if q == cur:
                    continue
                b = box[q]  # (_inside, written out: the walk's hottest loop)
                if not (b[0] - 1e-6 <= yx <= b[2] + 1e-6 and b[1] - 1e-6 <= yy <= b[3] + 1e-6
                        and NM._in_poly(mesh.vs[q], yx, yy)):
                    continue
                hq = NM._height_on(mesh.vs[q], yx, yy)
                if DROP_MIN <= h - hq <= drop_max and (hi is None or hq > hi):
                    nxt, hi = q, hq
            if nxt is not None and h - hi >= DROP_CLEAR_MIN and not _clear_over(mesh, near, yx, yy, hi, h):
                return None
            if nxt is None and drop_max >= DROP_SCAN_MIN:
                # (on along the line: a sheer cliff's foot, DROP_SCAN_MIN or more under the edge)
                for m in range(1, int(DROP_SCAN_YD / 0.5) + 1):
                    ts = te + m * 0.5 / L
                    if ts >= 1.0:
                        break
                    px, py = ax + (bx - ax) * ts, ay + (by - ay) * ts
                    near = near_polys(px, py)
                    for q in near:
                        if q == cur or not _inside(mesh, q, px, py):
                            continue
                        hq = NM._height_on(mesh.vs[q], px, py)
                        if DROP_SCAN_MIN <= h - hq <= drop_max and (hi is None or hq > hi):
                            nxt, hi = q, hq
                    if nxt is not None:
                        if h - hi >= DROP_CLEAR_MIN and not _clear_over(mesh, near, px, py, hi, h):
                            return None
                        t = ts + eps
                        break
            if nxt is None:
                return None
            how = DROP
        cur = nxt
    return None


def merge_cell(samples, mesh, middle):
    """A cell's samples as its surfaces, [z, {pids}, px, py] by height: samples within citygrid.MERGE_Z of each other
    whose polys are within citygrid.HOPS links on the mesh are one surface (citygrid.merge_cell joins only neighbors:
    a map tile's cell is crossed by many small polys, and the city's rule left two or three surfaces of one slope).
    Its point: the cell's middle when one of its polys covers it, else the first sample's."""
    n = len(samples)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(n):
        near = mesh.near(samples[i][1])
        for j in range(i + 1, n):
            if abs(samples[i][0] - samples[j][0]) <= CGP.MERGE_Z and samples[j][1] in near:
                parent[find(j)] = find(i)
    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(samples[i])
    out = []
    mx, my = middle
    for g in groups.values():
        z = 0.0
        for s in g:  # (added in turn, as numpy's scalars were: sum() of Python floats rounds otherwise, and a cell's
            z += s[0]  # surfaces a hair apart in height swapped places against the bakes before)
        z /= len(g)
        mid = [s for s in g if abs(s[2] - mx) < 1e-6 and abs(s[3] - my) < 1e-6]
        p = mid[0] if mid else g[0]
        out.append([mid[0][0] if mid else z, {s[1] for s in g}, p[2], p[3]])
    return sorted(out, key=lambda s: s[0])


def water_grid(cont: int):
    """The terrain grid (Data/Terrain.lua's, data/pass_<cont>_clean.npy): (array rows x cols, tx0, ty0), 8.33 yd cells,
    row = south from tile ty0, col = east from tile tx0."""

    import re
    if not (data_dir() / f"pass_{cont}_clean.npy").exists():
        # (none: Zephras Isle's sea has no water in the grid, so no swims there. A continent's missing is a bake's error
        # before it starts, worldbake.need_bake_data: item 72's data/ without it baked no seas or lakes)
        return False
    txt = (ADDON_DIR / "Data" / "Terrain.lua").read_text(encoding="utf-8")
    m = re.search(r"\[%d\] = \{ tx0 = (\d+), ty0 = (\d+)," % cont, txt)
    return np.load(data_dir() / f"pass_{cont}_clean.npy"), int(m.group(1)), int(m.group(2))


def terrain_water(wg, x: float, y: float) -> bool:
    """Whether the terrain grid has water (1) at world (x, y)."""
    g, tx0, ty0 = wg
    col = int(math.floor((32 - y / WM.T - tx0) * 64))
    row = int(math.floor((32 - x / WM.T - ty0) * 64))
    return 0 <= row < g.shape[0] and 0 <= col < g.shape[1] and g[row, col] == 1


WALKED = os.environ.get("AGPS_WG_LINKS", "walk") == "walk"  # ("hops": the first bake's rule, citygrid.build_links)


ROUND_Z = 2.0  # yards: two neighbor cells' surfaces about this level are linked when the mesh joins their polys within
# the cells (a corner, a narrow ramp's turn: the straight line between their points clips the mesh's edge)


def joined_within(mesh, a: set, b: set, allowed: set) -> bool:
    """Whether a poly of `a` reaches one of `b` over joined polys, all of them in `allowed`."""
    if a & b:
        return True
    seen = set(a) & allowed
    front = list(seen)
    while front:
        p = front.pop()
        for q in mesh.nb[p]:
            if q in b:
                return True
            if q in allowed and q not in seen:
                seen.add(q)
                front.append(q)
    return False


def walked_links(surf: dict, mesh, cell: float, samples: dict, x0: float, y0: float) -> dict:
    """{(i, j, k): [the neighbor surface's k in each DIRS direction, or -1]}: a link only where the mesh is walked straight
    from the surface's point to the neighbor's (mesh_walk): both ways on joined polys (a walk), or one way off a ledge's
    edge down onto the floor under it within DROP_FAR (a drop: the foot never links back up). The nearest in height of
    those walked (a walk before a drop). Diagonals only where a square way round is linked too (citygrid.build_links).
    Not walked: a link between the top of a ledge and its foot whose polys meet round its end (the first bake's HOPS
    rule, the 10,000-route test's impossible climbs)."""
    if not WALKED:
        return CGP.build_links(surf, mesh, cell)

    near_cache = {}

    def near_polys(x, y):
        key = (int((x - x0) // cell), int((y - y0) // cell))
        got = near_cache.get(key)
        if got is None:
            got = samples.get(key)
            got = near_cache[key] = {sm[1] for sm in got} if got else ()
        return got
    start = {}

    def cells_polys(i, j, dx, dy):
        out = set()
        for key in ((i, j), (i + dx, j + dy), (i + dx, j), (i, j + dy)):
            for sm in samples.get(key, ()):
                out.add(sm[1])
        return out

    def pid_of(i, j, k):
        key = (i, j, k)
        p = start.get(key)
        if p is None:
            s = surf[(i, j)][k]
            p = start[key] = _poly_at(mesh, s[1], s[2], s[3], s[0]) if s[1] else -1
        return p
    if accel() == "numba":
        from . import worldgrid_nb as WNB
        up = [CGP.dz_max(cell * (math.sqrt(2) if dx and dy else 1)) for dx, dy in DIRS]
        links = WNB.links(surf, mesh, cell, samples, x0, y0, DIRS, up, [max(u, DROP_FAR) for u in up],
                          DROP_FAR, DROP_MIN, WALK_END_Z, ROUND_Z, DROP_SCAN_YD, DROP_SCAN_MIN, DROP_CLEAR_Z,
                          DROP_CLEAR_MIN)
    else:
        links = _walk_links(surf, mesh, cell, pid_of, near_polys, cells_polys)
    return _diagonals(links)


def accel() -> str:
    """How walked_links walks: "numba" (worldgrid_nb, compiled; byte-equal) when Numba is installed, else "python".
    AGPS_WG_ACCEL=off: Python always; =numba: Numba or an error."""
    want = os.environ.get("AGPS_WG_ACCEL", "auto").lower()
    if want in ("off", "python", "0"):
        return "python"
    from . import worldgrid_nb as WNB
    if WNB.AVAILABLE and HOPS == 2:  # (the compiled walk's arrival looks two links round)
        return "numba"
    if want == "numba":
        raise RuntimeError("AGPS_WG_ACCEL=numba but numba isn't installed")
    return "python"


def _walk_links(surf, mesh, cell, pid_of, near_polys, cells_polys) -> dict:
    """walked_links' straight links in Python (worldgrid_nb walks the same, compiled)."""
    links = {}
    for (i, j), ss in surf.items():
        for k, s in enumerate(ss):
            row = [-1] * 8
            if not s[1]:  # (a swim surface: linked by the water's rule)
                links[(i, j, k)] = row
                continue
            p0 = pid_of(i, j, k)
            for d, (dx, dy) in enumerate(DIRS):
                tt = surf.get((i + dx, j + dy))
                if not tt:
                    continue
                dist = cell * (math.sqrt(2) if dx and dy else 1)
                up = CGP.dz_max(dist)
                down = max(up, DROP_FAR)
                # (the nearest in height first: the first walk found is the best, a drop only while no walk is)
                cands = sorted((abs(t[0] - s[0]), kk) for kk, t in enumerate(tt)
                               if t[1] and t[0] - s[0] <= up and s[0] - t[0] <= down)
                best, drop = -1, -1
                for adz, kk in cands:
                    t = tt[kk]
                    how = mesh_walk(mesh, near_polys, (s[2], s[3], s[0]), p0, (t[2], t[3]), t[1], t[0], DROP_FAR)
                    if how is None and adz <= ROUND_Z and joined_within(mesh, s[1], t[1], cells_polys(i, j, dx, dy)):
                        how = WALK  # (round a corner, about level: the straight line clips the mesh's edge)
                    if how == WALK:
                        best = kk
                        break
                    if how == DROP and drop < 0:
                        drop = kk
                row[d] = best if best >= 0 else drop
            links[(i, j, k)] = row
    return links


def _diagonals(links: dict) -> dict:
    """(diagonals: only where a square way round is linked too)"""
    for (i, j, k), row in links.items():
        for d in range(4, 8):
            if row[d] < 0:
                continue
            dx, dy = DIRS[d]
            ok = False
            for a, b in ((DIRS.index((dx, 0)), DIRS.index((0, dy))), (DIRS.index((0, dy)), DIRS.index((dx, 0)))):
                k1 = row[a]
                if k1 < 0:
                    continue
                ax, ay = DIRS[a]
                r1 = links.get((i + ax, j + ay, k1))
                if r1 and r1[b] >= 0:
                    ok = True
                    break
            if not ok:
                row[d] = -1
    return links


# --- item 72: the links that cross a model's wall ---------------------------------------------------------------------
# Kooki3z 2026-11-24/25 ("make sure we are checking the whole map for these thin wall conditions"): the walk mesh's voxels
# lose a wall thinner than a voxel (a palisade, a fence, a barricade's planks), and the grid's links run through it. Each
# link checked against the tile's building and prop collision triangles (worldmesh.models_path, from the client): cut
# where the line from surface to surface, at WALL_BODY_Z over each end's floor, crosses a steep face (|normal z| <
# WALL_STEEP_NZ: a wall, not a floor or a ceiling) at every one of those heights (a step's riser or a curb only at the
# lowest: kept). A level link (its ends WALL_MAX_DZ apart or less), or one linked back (a stair, a ramp: walked both
# ways) is judged along its line; a drop (one way, down) along a level line at its top floor's heights, since it's
# walked off the edge up there (a stair judged so ran through its stairwell's walls: six upstairs innkeepers lost) (a straight line from top to foot
# runs through the very face it goes down: the first bake cut 1.1 million links that way, median 42 yd drops), so a
# wall on the rim cuts it (item 43, Red Cloud Mesa's palisade) and a cliff face under the edge doesn't.
WALL_BODY_Z = (0.5, 1.2)
WALL_MAX_DZ = 1.5
WALL_STEEP_NZ = 0.7
WALL_BUCKET = 4.0


def _wall_index(tris: np.ndarray):
    """The steep triangles, bucketed by WALL_BUCKET yards (their xy box): (tris, {bucket: [index]})."""
    if not len(tris):
        return tris, {}
    e1, e2 = tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
    n = np.cross(e1, e2)
    ln = np.linalg.norm(n, axis=1)
    ok = ln > 1e-9
    nz = np.zeros(len(tris))
    nz[ok] = np.abs(n[ok, 2]) / ln[ok]
    steep = tris[ok & (nz < WALL_STEEP_NZ)]
    idx = {}
    lo, hi = steep.min(axis=1), steep.max(axis=1)
    for i in range(len(steep)):
        for bx in range(int(lo[i, 0] // WALL_BUCKET), int(hi[i, 0] // WALL_BUCKET) + 1):
            for by in range(int(lo[i, 1] // WALL_BUCKET), int(hi[i, 1] // WALL_BUCKET) + 1):
                idx.setdefault((bx, by), []).append(i)
    return steep, idx


def _segment_hits(p0, p1, T) -> bool:
    """Whether segment p0-p1 crosses any of triangles T (N, 3, 3): Moller-Trumbore, vectorized."""
    return _segment_hit_t(p0, p1, T) is not None


def _segment_hit_t(p0, p1, T):
    """Where along p0-p1 (0..1) it first crosses one of triangles T (N, 3, 3), else None: Moller-Trumbore, vectorized."""
    if not len(T):
        return None
    d = p1 - p0
    e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    h = np.cross(d, e2)
    a = np.einsum("ij,ij->i", e1, h)
    ok = np.abs(a) > 1e-9
    f = np.zeros_like(a)
    f[ok] = 1.0 / a[ok]
    s = p0 - T[:, 0]
    u = f * np.einsum("ij,ij->i", s, h)
    q = np.cross(s, e1)
    v = f * (q @ d)
    t = f * np.einsum("ij,ij->i", e2, q)
    hit = ok & (u >= 0) & (u <= 1) & (v >= 0) & (u + v <= 1) & (t > 1e-6) & (t < 1 - 1e-6)
    return float(t[hit].min()) if hit.any() else None


# A wall the mesh knows (a building's inner wall, a cliff) leaves a gap in it, the agent's radius each side: the grid's
# 8 yd link across it stands for the mesh's way round (through a door): kept. One it lost runs over the mesh: cut only
# there, the mesh walkable at the line's height WALL_MESH_DZ just before the wall, at it and just after (WALL_MESH_STEP).
WALL_MESH_DZ, WALL_MESH_STEP = 1.5, 0.6


def _mesh_index(mesh):
    """The mesh's polys bucketed by WALL_BUCKET yards (xy boxes), for _on_mesh: (vs, {bucket: [pid]})."""
    idx = {}
    for pid, vs in enumerate(mesh.vs):
        xs, ys = [v[0] for v in vs], [v[1] for v in vs]
        for bx in range(int(min(xs) // WALL_BUCKET), int(max(xs) // WALL_BUCKET) + 1):
            for by in range(int(min(ys) // WALL_BUCKET), int(max(ys) // WALL_BUCKET) + 1):
                idx.setdefault((bx, by), []).append(pid)
    return mesh.vs, idx


def _on_mesh(mi, x: float, y: float, z: float) -> bool:
    """Whether a walkable poly holds (x, y) with its height within WALL_MESH_DZ of z."""
    vs_all, idx = mi
    for pid in idx.get((int(x // WALL_BUCKET), int(y // WALL_BUCKET)), ()):
        vs = vs_all[pid]
        inside = False
        n = len(vs)
        for a in range(n):
            x1, y1 = vs[a][0], vs[a][1]
            x2, y2 = vs[(a + 1) % n][0], vs[(a + 1) % n][1]
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
        if inside and abs(sum(v[2] for v in vs) / n - z) <= WALL_MESH_DZ:
            return True
    return False


# A surface at a rim with a model's wall standing on it (item 43, Red Cloud Mesa's palisade, which the mesh knows: no
# link there to cut, but the search's falls off a rim, WorldGrid.FarDrops, went over it): out of it a way it isn't
# linked and the ground falls away (the next cell has no surface within RIM_LEVEL_Z of its height: a rim, not a wall or a
# trunk on level ground, which flagged a fifth of all surfaces), a level line at its height RIM_WALL_CELLS cells long
# crosses a steep face at every WALL_BODY_Z. Flagged (F_RIM_WALL): no fall starts there.
# A wall, not a trunk or a post: it stands across RIM_WIDE lines side by side, RIM_WIDE_YD apart (a trunk on a slope
# flagged a tenth of all surfaces; a player steps round it).
RIM_WALL_CELLS = 2
RIM_LEVEL_Z = 4.0
RIM_WIDE, RIM_WIDE_YD = 3, 1.5
# A drop past a wall the mesh knows is cut (a palisade on a mesa's rim, item 78a) only off the ground's own rim: its top
# within RIM_GROUND_Z of the terrain there and falling RIM_DROP_MAX or less. Off a roof, a crown or a wall's top too, it
# cut 290k more links and the searches round them grew half again (the ALT budgets' trips, warrior 77k for 50k)
RIM_GROUND_Z, RIM_DROP_MAX = 3.0, 10.0
_GROUND = {}


def _ground_at(cont: int, x: float, y: float):
    """The terrain's height at (x, y) (worldbake.Heights, Data/Heights.lua), or None."""
    h = _GROUND.get(cont)
    if h is None:
        try:
            from .worldbake import Heights
            h = _GROUND[cont] = Heights(cont)
        except Exception:
            h = _GROUND[cont] = False
    if h is False:
        return None
    v = h.sample(np.array([x], float), np.array([y], float))[0]
    return None if v != v else float(v)


def cut_wall_links(surf: dict, links: dict, models: Path, mesh=None, rim: set | None = None, cell: float = 0.0,
                   cont: int | None = None) -> int:
    """The links (walked_links') crossing a model's wall the mesh lost cut (set -1); how many were cut. `mesh`: the
    tile's (None: every crossing cut). `rim` (a set, with `cell`): filled with the surfaces (i, j, k) walled at a rim."""
    if not models.exists() or os.environ.get("AGPS_NO_WALL_CUTS"):  # (the switch: a baseline bake without them)
        return 0
    tris = np.load(models)
    steep, idx = _wall_index(np.asarray(tris, np.float64))
    if not idx:
        return 0

    def near(ax, ay, bx, by):
        cand = set()
        for qx in range(int(min(ax, bx) // WALL_BUCKET), int(max(ax, bx) // WALL_BUCKET) + 1):
            for qy in range(int(min(ay, by) // WALL_BUCKET), int(max(ay, by) // WALL_BUCKET) + 1):
                cand.update(idx.get((qx, qy), ()))
        return steep[sorted(cand)] if cand else None
    mi = _mesh_index(mesh) if mesh is not None else None
    cut = 0
    before = {key: tuple(row) for key, row in links.items()}  # (linked back: as made, not as cut so far)
    for (i, j, k), row in links.items():
        ss = surf.get((i, j))
        if not ss or k >= len(ss):
            continue
        s = ss[k]
        for d, (dx, dy) in enumerate(DIRS):
            t = row[d]
            if t is None or t < 0:
                continue
            tt = surf.get((i + dx, j + dy))
            if not tt or t >= len(tt):
                continue
            o = tt[t]
            za, zb = s[0], o[0]
            drop = False
            if abs(zb - za) > WALL_MAX_DZ:
                back = before.get((i + dx, j + dy, t))
                if not (back and back[DIRS.index((-dx, -dy))] == k):  # (a drop: not linked back)
                    za = zb = max(za, zb)
                    drop = True
            ax, ay, bx, by = s[2], s[3], o[2], o[3]
            T = near(ax, ay, bx, by)
            if T is None:
                continue
            hits = [_segment_hit_t(np.array([ax, ay, za + h]), np.array([bx, by, zb + h]), T) for h in WALL_BODY_Z]
            if any(h is None for h in hits):
                continue
            if mi is not None and drop:
                rim_ok = cont is None  # (no continent, no ground to tell by: the rule as it was)
                if cont is not None and abs(s[0] - o[0]) <= RIM_DROP_MAX:
                    tx_, ty_ = (ax, ay) if s[0] >= o[0] else (bx, by)
                    g = _ground_at(cont, tx_, ty_)
                    rim_ok = g is not None and abs(max(s[0], o[0]) - g) <= RIM_GROUND_Z
                if not rim_ok:
                    drop = False  # (not off the ground's rim: as any link, cut only by a wall the mesh lost)
            if mi is not None and drop:
                # (a drop past a wall the mesh knows: cut only by a wide one (RIM_WIDE lines RIM_WIDE_YD apart all
                # blocked: a palisade, item 78a), never a trunk or a post on a wooded slope, whose downhill links are
                # one way too: cutting at any wall cut 505k links and stranded 65k surfaces of the biggest pieces)
                L = math.hypot(bx - ax, by - ay) or 1.0
                px, py = -(by - ay) / L, (bx - ax) / L
                wide = True
                for w in range(RIM_WIDE):
                    off = (w - (RIM_WIDE - 1) / 2) * RIM_WIDE_YD
                    if off == 0:
                        continue
                    T2 = near(ax + px * off, ay + py * off, bx + px * off, by + py * off)
                    if T2 is None or not all(_segment_hits(np.array([ax + px * off, ay + py * off, za + h]),
                                                           np.array([bx + px * off, by + py * off, zb + h]), T2)
                                             for h in WALL_BODY_Z):
                        wide = False
                        break
                if not wide and not all(_on_mesh(mi, ax + (bx - ax) * f, ay + (by - ay) * f, za)
                                        for f in (max(0.0, hits[0] - WALL_MESH_STEP / L), hits[0],
                                                  min(1.0, hits[0] + WALL_MESH_STEP / L))):
                    continue
            if mi is not None and not drop:
                # (the mesh walkable through the wall: lost it. Not asked of a drop: it stands for no way round, it's
                # a jump off the edge, and a wall on the edge stops it whether the mesh knows the wall or not. Item
                # 78a, Kooki3z on 1e503bf8: Red Cloud Mesa's palisade, which the mesh knows, still jumped through by a
                # 3.5 yd drop link at (-2779, -245))
                L = math.hypot(bx - ax, by - ay) or 1.0
                f0 = hits[0]
                if not all(_on_mesh(mi, ax + (bx - ax) * f, ay + (by - ay) * f, za + (zb - za) * f)
                           for f in (max(0.0, f0 - WALL_MESH_STEP / L), f0, min(1.0, f0 + WALL_MESH_STEP / L))):
                    continue
            row[d] = -1
            cut += 1
    if rim is not None and cell:
        for (i, j, k), row in links.items():
            ss = surf.get((i, j))
            if not ss or k >= len(ss) or not ss[k][1]:  # (a swim's surface: no falls start there)
                continue
            s = ss[k]
            for d, (dx, dy) in enumerate(DIRS):
                if row[d] is not None and row[d] >= 0:
                    continue
                if any(abs(o[0] - s[0]) <= RIM_LEVEL_Z for o in surf.get((i + dx, j + dy), ())):
                    continue  # (level ground on: no rim that way)
                L = cell * RIM_WALL_CELLS
                n = math.hypot(dx, dy)
                ux, uy = dx / n, dy / n
                px, py = -uy, ux  # (across the way out)
                ok = True
                for w in range(RIM_WIDE):
                    off = (w - (RIM_WIDE - 1) / 2) * RIM_WIDE_YD
                    ax, ay = s[2] + px * off, s[3] + py * off
                    bx, by = ax + ux * L, ay + uy * L
                    T = near(ax, ay, bx, by)
                    if T is None or not all(_segment_hits(np.array([ax, ay, s[0] + h]), np.array([bx, by, s[0] + h]), T)
                                            for h in WALL_BODY_Z):
                        ok = False
                        break
                if ok:
                    rim.add((i, j, k))
                    break
    return cut


def build_tile_grid(cont: int, tx: int, ty: int, per_tile: int = CELL_PER_TILE, wg=None) -> dict | None:
    """One tile's surfaces and links: arrays over its own cells (a, b: 0..per_tile-1, cell a * per_tile + b), each
    surface's z, its point's offset (x step * 8 + y step), kind, and per direction the linked surface: its index k in
    that cell (when the cell is the tile's) or -2 with the height there (a neighbor tile's: matched in `assemble`)."""
    got = WM.load_tile(cont, tx, ty)
    if got is None:
        return None
    polys, nbs = got
    mesh = _mesh(polys, nbs)
    c = cell_yd(per_tile)
    gx0, gy0 = tile_origin(tx, ty, per_tile)
    x0, y0 = (gx0 - 1) * c, (gy0 - 1) * c  # (with a ring of the neighbors' cells)
    n = per_tile + 2
    samples = CGP.rasterize(mesh, x0, y0, n, n, c) if mesh.vs else {}
    surf = {k: merge_cell(s, mesh, (x0 + (k[0] + 0.5) * c, y0 + (k[1] + 0.5) * c)) for k, s in samples.items()}
    links = None  # (worked out once the water's surfaces are in)
    # (water: the terrain grid's, where no mesh surface is near its top)
    p = WM.tile_path(cont, tx, ty).with_suffix(".water.npy")
    water = np.load(p) if p.exists() else np.zeros((0, 6), np.float32)
    wtop = {}
    for wx0, wy0, wx1, wy1, top, _g in water:
        mx, my = (wx0 + wx1) / 2, (wy0 + wy1) / 2
        i, j = int((mx - x0) // c), int((my - y0) // c)
        if wg is False:
            break
        if 0 <= i < n and 0 <= j < n and (wg is None or terrain_water(wg, mx, my)):
            wtop[(i, j)] = max(wtop.get((i, j), -1e9), float(top))
    swims = set()
    for (i, j), top in wtop.items():
        ss = surf.setdefault((i, j), [])
        if any(abs(s[0] - top) <= SHORE_Z or (s[0] > top - 0.2 and s[0] < top + 3) for s in ss):
            continue
        ss.append([top, set(), x0 + (i + 0.5) * c, y0 + (j + 0.5) * c])
        ss.sort(key=lambda s: s[0])
        swims.add((i, j, top))
    # (the links, with the water's surfaces in: theirs below)
    links = walked_links(surf, mesh, c, samples, x0, y0) if surf else {}
    # (and those crossing a model's wall the mesh's voxels lost: item 72)
    rim = set()
    wall_cuts = cut_wall_links(surf, links, WM.models_path(cont, tx, ty), mesh, rim, c, cont) if surf else 0
    if swims:
        is_swim = {(i, j, k) for (i, j), ss in surf.items() for k, s in enumerate(ss) if not s[1]}
        for (i, j, k) in is_swim:
            s = surf[(i, j)][k]
            row = links[(i, j, k)]
            for d, (dx, dy) in enumerate(DIRS):
                tt = surf.get((i + dx, j + dy))
                if not tt:
                    continue
                best, bd = -1, None
                for kk, t in enumerate(tt):
                    dz = abs(t[0] - s[0])
                    if dz <= SHORE_Z and (bd is None or dz < bd):
                        best, bd = kk, dz
                row[d] = best
                if best >= 0 and tt[best][1]:  # (and the shore's way into the water, where it has none that way)
                    back = links[(i + dx, j + dy, best)]
                    if back[DIRS.index((-dx, -dy))] < 0:
                        back[DIRS.index((-dx, -dy))] = k
    # (the tile's own cells, as arrays)
    cells, zs, offs, kinds, lk, lz, rims = [], [], [], [], [], [], []
    for a in range(per_tile):
        for b in range(per_tile):
            ss = surf.get((a + 1, b + 1))
            if not ss:
                continue
            for k, s in enumerate(ss[:CGP.MAX_IN_CELL]):
                cx0, cy0 = x0 + (a + 1) * c, y0 + (b + 1) * c
                ox = min(7, max(0, int((s[2] - cx0) / c * 8 + 1e-6)))  # (the middle exactly 4: no float's 3.9999)
                oy = min(7, max(0, int((s[3] - cy0) / c * 8 + 1e-6)))
                cells.append(a * per_tile + b)
                zs.append(s[0])
                offs.append(ox * 8 + oy)
                kinds.append(KIND_GROUND if s[1] else KIND_SWIM)
                rims.append(1 if (a + 1, b + 1, k) in rim else 0)
                row = links.get((a + 1, b + 1, k), [-1] * 8)
                r1, r2 = [], []
                for d, (dx, dy) in enumerate(DIRS):
                    t = row[d]
                    na, nb = a + dx, b + dy
                    if t < 0 or t >= CGP.MAX_IN_CELL:
                        r1.append(-1)
                        r2.append(0.0)
                    elif 0 <= na < per_tile and 0 <= nb < per_tile:
                        r1.append(t)
                        r2.append(0.0)
                    else:
                        r1.append(-2)
                        r2.append(surf[(na + 1, nb + 1)][t][0])
                lk.append(r1)
                lz.append(r2)
    return {"cont": cont, "tile": (tx, ty), "per_tile": per_tile, "wall_cuts": wall_cuts, "cell": np.array(cells, np.int32),
            "z": np.array(zs, np.float32), "off": np.array(offs, np.uint8), "kind": np.array(kinds, np.uint8),
            "lk": np.array(lk, np.int8).reshape(-1, 8), "lz": np.array(lz, np.float32).reshape(-1, 8),
            "rim": np.array(rims, np.uint8)}


def grid_dir() -> Path:
    env = os.environ.get("AGPS_WORLDGRID_DIR")  # (a trial's tiles apart from the shipped bake's)
    return Path(env) if env else WM.mesh_dir() / "grid"


def tile_grid_path(cont, tx, ty, per_tile=CELL_PER_TILE) -> Path:
    return grid_dir() / f"{cont}_{tx}_{ty}_{per_tile}.npz"


_WG: dict = {}
_STAMP: dict = {}


def tile_stamp(cont: int, tx: int, ty: int, per_tile: int = CELL_PER_TILE) -> str:
    """What a tile's grid is made from: its mesh and water, the continent's terrain grid, and the code and settings that
    make it (this module, citygrid's, navmesh's and worldmesh's). Saved in the tile's .npz (`stamp`); `agps world-grid
    grid --changed` builds only the tiles whose stamp differs."""
    base = _STAMP.get(cont)
    if base is None:
        h = hashlib.sha1()
        for mod in (__file__, CGP.__file__, NM.__file__, WM.__file__):
            h.update(Path(mod).read_bytes())
        h.update(repr((HOPS, WALKED, DROP_MAX, DROP_FAR, DROP_SCAN_YD, DROP_SCAN_MIN, DROP_CLEAR_Z, DROP_CLEAR_MIN, DROP_MIN, WALK_END_Z, ROUND_Z, SHORE_Z, CGP.MERGE_Z, CGP.WALK_SLOPE,
                       CGP.CLIMB, CGP.MAX_IN_CELL)).encode())
        tw = data_dir() / f"pass_{cont}_clean.npy"
        h.update(tw.read_bytes() if tw.exists() else b"-")
        m = re.search(r"\[%d\] = \{ tx0 = (\d+), ty0 = (\d+)," % cont,
                      (ADDON_DIR / "Data" / "Terrain.lua").read_text(encoding="utf-8")) if tw.exists() else None
        h.update(repr(m.groups() if m else None).encode())
        base = _STAMP[cont] = h.hexdigest()
    h = hashlib.sha1(f"{base}|{per_tile}".encode())
    for p in (WM.tile_path(cont, tx, ty), WM.tile_path(cont, tx, ty).with_suffix(".water.npy"), WM.models_path(cont, tx, ty)):
        h.update(p.read_bytes() if p.exists() else b"-")
    return h.hexdigest()[:16]


def tile_current(cont: int, tx: int, ty: int, per_tile: int = CELL_PER_TILE) -> bool:
    """Whether the tile's grid on disk was made from what tile_stamp says now."""
    p = tile_grid_path(cont, tx, ty, per_tile)
    if not p.exists():
        return False
    try:
        with np.load(p) as d:
            return "stamp" in d.files and str(d["stamp"]) == tile_stamp(cont, tx, ty, per_tile)
    except Exception:
        return False


def build_tile_job(job) -> dict:
    cont, tx, ty, per_tile = job
    t = time.time()
    try:
        wg = _WG.get(cont)
        if wg is None:
            wg = _WG[cont] = water_grid(cont)
        stamp = np.array(tile_stamp(cont, tx, ty, per_tile))
        g = build_tile_grid(cont, tx, ty, per_tile, wg)
        p = tile_grid_path(cont, tx, ty, per_tile)
        p.parent.mkdir(parents=True, exist_ok=True)
        if g is None:
            np.savez(p, empty=np.zeros(0), stamp=stamp)
            return {"tile": [cont, tx, ty], "ok": True, "n": 0, "s": round(time.time() - t, 1)}
        np.savez(p, cell=g["cell"], z=g["z"], off=g["off"], kind=g["kind"], lk=g["lk"], lz=g["lz"], rim=g["rim"], stamp=stamp)
        return {"tile": [cont, tx, ty], "ok": True, "n": int(len(g["z"])), "wall_cuts": int(g.get("wall_cuts", 0)),
                "s": round(time.time() - t, 1)}
    except Exception as e:
        import traceback
        return {"tile": [cont, tx, ty], "ok": False, "err": traceback.format_exc()[-600:], "s": round(time.time() - t, 1)}


def build_tiles(jobs: list, workers: int = 8, log=print) -> list:
    import multiprocessing as mp

    out = []
    t0 = time.time()
    with mp.get_context("spawn").Pool(workers, maxtasksperchild=50) as pool:
        for k, r in enumerate(pool.imap_unordered(build_tile_job, jobs), 1):
            out.append(r)
            if not r["ok"] or k % 50 == 0 or k == len(jobs):
                log(f"  grid {k}/{len(jobs)} tiles ({time.time() - t0:.0f} s){'' if r['ok'] else ': ' + str(r)}")
    return out


# --- the continent's grid ----------------------------------------------------------------------------------------------

class Grid:
    """A continent's surfaces (global ids 0..n-1, by tile, cell, height) and their links (n x 8, -1 none), with what the
    tiles' arrays gave; plus road links and flags once `roads` runs."""

    def __init__(self, cont: int, tiles: list, per_tile: int = CELL_PER_TILE, log=print):
        self.cont, self.per_tile, self.cell = cont, per_tile, cell_yd(per_tile)
        parts = []
        for tx, ty in tiles:
            p = tile_grid_path(cont, tx, ty, per_tile)
            if not p.exists():
                continue
            d = np.load(p)
            if "empty" in d.files or not len(d["z"]):
                continue
            gx0, gy0 = tile_origin(tx, ty, per_tile)
            a, b = d["cell"] // per_tile, d["cell"] % per_tile
            parts.append((gx0 + a, gy0 + b, d))
        gx = np.concatenate([p[0] for p in parts]).astype(np.int32)
        gy = np.concatenate([p[1] for p in parts]).astype(np.int32)
        self.z = np.concatenate([p[2]["z"] for p in parts])
        self.off = np.concatenate([p[2]["off"] for p in parts])
        self.kind = np.concatenate([p[2]["kind"] for p in parts])
        self.rim = np.concatenate([p[2]["rim"] if "rim" in p[2] else np.zeros(len(p[2]["z"]), np.uint8) for p in parts])
        lk = np.concatenate([p[2]["lk"] for p in parts]).astype(np.int32)
        lz = np.concatenate([p[2]["lz"] for p in parts])
        # (sorted by cell, then height: a cell's surfaces one after another)
        order = np.lexsort((self.z, gy, gx))
        gx, gy, self.z, self.off, self.kind, lk, lz = gx[order], gy[order], self.z[order], self.off[order], self.kind[order], lk[order], lz[order]
        self.rim = self.rim[order]
        self.gx, self.gy = gx, gy
        self.gxmin, self.gymin = int(gx.min()), int(gy.min())
        self.W, self.H = int(gx.max()) - self.gxmin + 1, int(gy.max()) - self.gymin + 1
        flat = (gx - self.gxmin).astype(np.int64) * self.H + (gy - self.gymin)
        self.first = np.full(self.W * self.H, -1, np.int64)
        self.count = np.zeros(self.W * self.H, np.int8)
        starts = np.r_[0, np.nonzero(np.diff(flat))[0] + 1]
        self.first[flat[starts]] = starts
        np.add.at(self.count, flat, 1)
        self.n = len(self.z)
        # (each surface's k in its cell)
        kin = np.arange(self.n) - self.first[flat]
        # (links: global ids)
        L = np.full((self.n, 8), -1, np.int64)
        for d, (dx, dy) in enumerate(DIRS):
            nx, ny = gx + dx - self.gxmin, gy + dy - self.gymin
            inside = (nx >= 0) & (ny >= 0) & (nx < self.W) & (ny < self.H)
            nflat = np.where(inside, nx.astype(np.int64) * self.H + ny, 0)
            f, cnt = self.first[nflat], self.count[nflat]
            own = (lk[:, d] >= 0) & inside & (lk[:, d] < cnt)
            L[own, d] = f[own] + lk[own, d]
            ring = (lk[:, d] == -2) & inside & (cnt > 0)
            idx = np.nonzero(ring)[0]
            best = np.full(len(idx), -1, np.int64)
            bd = np.full(len(idx), 1e9)
            for k in range(CGP.MAX_IN_CELL):
                has = cnt[idx] > k
                cand = np.where(has, f[idx] + k, 0)
                dz = np.where(has, np.abs(self.z[cand] - lz[idx, d]), 1e9)
                take = (dz < bd) & (dz <= CGP.MERGE_Z)
                best[take], bd[take] = cand[take], dz[take]
            L[idx, d] = best
        self.links = L
        self.flags = np.zeros(self.n, np.uint8)
        self.road = []  # [(a, b, cost, kind, pts)]
        self.kin = kin
        log(f"  cont {cont}: {self.n} surfaces in {len(starts)} cells over {len(parts)} tiles")

    # (citygrid's Grid's interface for road_links: surf, cell, x0, y0, road_out, links by node)
    def at(self, x: float, y: float, z: float | None, reach_z: float = CGP.ROAD_ON_Z):
        gx, gy = int(math.floor(x / self.cell)) - self.gxmin, int(math.floor(y / self.cell)) - self.gymin
        if not (0 <= gx < self.W and 0 <= gy < self.H):
            return None
        f, cnt = int(self.first[gx * self.H + gy]), int(self.count[gx * self.H + gy])
        if cnt <= 0:
            return None
        if z is None:
            # (no height: a land road's. The ground's: the surface in the cell nearest the terrain, else the lowest)
            if cnt == 1 or self._ground is None:
                return f
            return f + int(np.argmin(np.abs(self.z[f:f + cnt] - self.ground_z(x, y))))
        best, bd = None, None
        for s in range(f, f + cnt):
            dz = abs(float(self.z[s]) - z)
            if dz <= reach_z and (bd is None or dz < bd):
                best, bd = s, dz
        return best

    _ground = None

    def ground_z(self, x, y):
        h = self._ground.sample(np.array([x]), np.array([y]))
        return float(h[0]) if np.isfinite(h[0]) else 0.0

    def step_cost(self, s: int, d: int, t: int) -> float:
        dx, dy = DIRS[d]
        step = self.cell * (math.sqrt(2) if dx and dy else 1)
        dz = float(self.z[t] - self.z[s])
        c = math.sqrt(step * step + dz * dz) + abs(dz) * 0.5
        if self.kind[s] == KIND_SWIM or self.kind[t] == KIND_SWIM:
            return c * SWIM_COST
        if self.flags[s] & FLAG_ROAD and self.flags[t] & FLAG_ROAD:
            return c * ROAD_PREF
        return c

    def neighbors(self, s: int):
        row = self.links[s]
        for d in range(8):
            t = int(row[d])
            if t >= 0:
                yield t, self.step_cost(s, d, t)
        for a, b, cost, _k, _p in self.road_out.get(s, ()):
            yield b, cost

    road_out: dict = {}

    def dist(self, a: int, b: int, limit: float) -> float:
        if a == b:
            return 0.0
        import heapq
        dist = {a: 0.0}
        h = [(0.0, a)]
        while h:
            d, n = heapq.heappop(h)
            if n == b:
                return d
            if d > dist.get(n, math.inf) or d > limit:
                continue
            for m, c in self.neighbors(n):
                nd = d + c
                if nd < dist.get(m, math.inf) and nd <= limit:
                    dist[m] = nd
                    heapq.heappush(h, (nd, m))
        return math.inf

    def point(self, s: int) -> tuple:
        o = int(self.off[s])
        return ((self.gx[s] + (o // 8 + 0.5) / 8) * self.cell, (self.gy[s] + (o % 8 + 0.5) / 8) * self.cell)
