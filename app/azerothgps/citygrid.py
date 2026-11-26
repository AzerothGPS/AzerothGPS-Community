"""The capitals' layered walk grids for 1.4.0's city routing (docs/city-rework-1.4.0.md; asked 2026-11-21: "replace the
zig-zag road graph inside the capitals with a layered walk grid baked from our Recast meshes").

Baked offline from our own Recast meshes of the cities (recastmesh.py, `agps navmesh build`: data/navmesh/*.pkl, never
shipped) into `Data/CityGrid.lua`: numbers only (heights, links), no game art, no mesh.

For each city (CITIES):
1. **Surfaces.** A square grid of CELL yards over the mesh. Every walkable poly touching a cell gives that cell a
   surface at the poly's height at the cell's middle (or the poly's point nearest it, inside the cell): floors stacked
   over each other (Undercity's rings, the Drag over the Cleft of Shadow, a hall over a street) are each a surface of
   the cell. Surfaces of one cell within MERGE_Z of each other and joined on the mesh (the same poly or neighbors) are
   one. Each keeps its point's offset in the cell (OFF_STEPS a side), so lines drawn through a narrow door keep to it.
2. **Links.** A surface is linked to a surface of each of its 8 neighbor cells when the mesh joins them (the same
   poly, neighbors, or neighbors' neighbors: Recast's polys never join across a wall) and the climb between them is
   at most what a slope of WALK_SLOPE and a step of CLIMB allow; diagonals only where one of the two square ways round
   is linked too (no corner cut through a wall's end). The link is the surface's own (one way): every mesh link is
   both ways, the roads' drops one way.
3. **Road links** (`road_links`, the hybrid): the mesh comes in pieces where the city's roads still walk (stairs taller
   than Recast's climb, a bank's counter floor, bridge decks, Undercity's canal walkways): every city road of the
   Router's graph (Capitals.lua, Cities.lua; drawn roads too) is walked every yard at its height; where it leaves the
   grid and comes back (or steps between two surfaces the grid doesn't link), and the grid has no way between those two
   surfaces within ROAD_DETOUR times the road's yards, the road's stretch is a link of its own (its points, its yards
   times ROAD_FACTOR; a drop's one way). A lift's (Thunder Bluff's, source 5) stretch up its shaft (LIFT_RISE) is
   KIND_LIFT and costs the Router's own yards for it (capitals.LIFT_SECONDS: the wait and the ride).
4. **Pruning.** Only the city: cells of a capital's own grid (Passability.Overlay not the continent's) and MARGIN_YD
   round them (its gates' ground); Undercity's level: the mesh's pieces its roads touch. Pieces of the grid smaller than
   MIN_PIECE surfaces with no road link are left out (roof tops and ledges Recast found walkable). Surfaces kept are
   those near a road's height (NEAR_ROAD_Z; a city's own `near_z`: Darnassus's ramps climb past it). An NPC's floor
   cut off from the city's (a bank's counter) is joined across it (reach_links).

The format (Data/CityGrid.lua, read by CityGrid.lua): `ns.CityGridData[name] = { cont, level, whole (City.whole), cell, x0, y0, w,
h, zmin, zq, n (surfaces), cells = "<one char a cell, column by column (i major, cell i * h + j): its count of surfaces>",
s = "<SURF (7) chars a surface: z (2), its point in the cell (1: x step * OFF_STEPS + y step), links (4, two directions
a character: the first's * 8 + the second's, each the neighbor cell's surface 1-7, 0 none)>", base = "<the first
surface (0-based) of every BLOCK cells, by commas>", links = "a,b,cost,kind,x,y,z,x,y,z...;..." (road links, a to b,
1-based surfaces), mesh = the mesh's stamp }`. Characters from ALPHA (6 bits each). Directions: DIRS (dx, dy) in that order.
"""

from __future__ import annotations

import bisect
import dataclasses
import hashlib
import heapq
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from . import navmesh as NM
from . import recastmesh as RM
from .paths import ADDON_DIR, data_dir

ALPHA = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
DIRS = ((1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (-1, 1), (-1, -1), (1, -1))
CELL = 2.0  # yards a cell (compare: `agps city-grid --cells 2,3,4`)
MERGE_Z = 2.0  # yards: a cell's surfaces from joined polys this near in height are one
OFF_STEPS = 8  # a surface's point in its cell: this many steps a side
ZQ = 0.25  # yards a height step
CLIMB = 1.0  # yards: a step up (recastmesh.AGENT_CLIMB)
WALK_SLOPE = 55.0  # degrees: the steepest way walked from cell to cell (Recast's 50, with its polys' rough heights)
HOPS = 2  # polys this many links apart on the mesh join two neighbor cells' surfaces
WALK_DZ = 2.0  # yards: a link climbing this much (up: never a drop) between two surfaces whose polys aren't neighbors (joined only through a
# third) is walked on the mesh first
WALK_GAP = 0.6  # ... its straight way within this of a poly (Recast leaves slivers between a flight's polys) ...
WALK_Z = 1.5  # ... at its height there within this of the way's (the two ends' heights, straight between) ...
WALK_STEP_YD = 0.5  # ... looked at every this many yards along it (and its ends) ...
WALK_STEP_Z = 1.5  # ... each height within this of one the look before (navfeatures.STEP_UP: no taller step)
WALK_ROAD_YD = 3.0  # ... unless both ends are on a city road (within this across and ROAD_ON_Z in height): its stairs
# and ramps (the Hall of Thanes' recorded walk up a 3 yd step the mesh leaves)
MARGIN_YD = 30.0  # yards of the land round a capital's own cells kept (its gates)
MIN_PIECE = 60  # surfaces: smaller pieces with no road link are left out
ROAD_STEP = 1.0  # yards: a road walked this often for its links
ROAD_ON_Z = 2.5  # yards: a road's point is on a surface this near its height
ROAD_DETOUR = 1.3  # a road's stretch is a link when the grid's way between its ends is longer than this times its yards
ROAD_DETOUR_YD = 6.0  # ... plus this many
ROAD_FACTOR = 1.5  # a road link's yard costs this many (the grid's own walk first)
ROAD_LINK_PTS_YD = 4.0  # a road link's points kept this far apart (its bends)
BLOCK = 32  # cells a `base` entry
NEAR_ROAD_YD = 30.0  # yards: a surface is the city's when one of its roads runs this near across ...
NEAR_ROAD_Z = 8.0  # ... and this near in height (road_heights)
NEAR_ROAD_BUCKET = 10.0
KIND_WALK, KIND_STAIRS, KIND_DROP, KIND_LIFT, KIND_SWIM = 0, 6, 4, 5, 7
KIND_BRIDGE, KIND_JUMP = 8, 9  # (navfeatures: a link along a bridge found; a running jump across a gap)
LIFT_RISE = 10.0  # yards: a lift road's stretch climbing this much is its ride (KIND_LIFT, the Router's own yards for it)
SKIP_SOURCES = (7,)  # swims: never a link (the canals' water is its own level)
ANCHOR_SOURCE = -1  # (an NPC's spot among the roads: road_heights only)
LIFT_SOURCE = -2  # (a lift's foot among the roads, a transport's: navfeatures' known lifts)
FEATURES = True  # navfeatures.py: steps and jumps the mesh lacks as links, the road links' kinds, the stairs and bridges
REACH_YD = 4.0  # yards: an NPC's floor cut off from the city's (behind a bank's counter) is joined to the city's nearest
REACH_Z = 2.0  # ... floor this near across and in height (reach_links)
WET_Z = 0.3  # yards: a surface this far under a liquid's top is in it (City.dry)
REACH_COST = 10.0  # yards a reach link costs more than its own


@dataclass
class City:
    name: str
    mesh: str  # recastmesh.mesh_path's name
    cont: int  # the continent (its map)
    level: int | None = None  # an underground city's routing level (Undercity: 10001)
    cell: float = CELL
    near_z: float = 0.0  # yards: NEAR_ROAD_Z for this city (0: that). Darnassus's ramps and spiral stairs climb 20-30 yd
    # between its roads' floors (the Temple of the Moon's balcony, the Cenarion Enclave's treetops), Ironforge's stairs
    # 22 to the Mystic Ward's balcony: at 8 the climb's middle was cut out and the floors over it left unreached;
    # neither has land under the city to keep out (Ironforge's mountain top is 200 yd over it)
    found_jumps: bool = True  # navfeatures' jumps found in the mesh become links (not Undercity's: its rings' railings
    # aren't in the collision read, and a found jump went off the ring "through the wall", Kooki3z 2026-11-22)
    dry: bool = False  # no surface under its models' liquid (Undercity's slime canals: the grid walked their shallow edges
    # across, Kooki3z 2026-11-22, "the actual bridge here"; navfeatures.Tris' liquids)
    whole: bool = False  # every floor of its grid within the capital's rectangle is the city's (CityGrid.CityFor;
    # `whole = true` in the data), not only over the capital's own cells: Darnassus, whose treetops aren't among them;
    # Ironforge, whose cells are its halls and leave out the shops and rooms off them (Nissa Firestone's First Aid room)


CITIES = [
    City("Orgrimmar", "orgrimmar", 1, cell=3.0),
    City("Stormwind City", "stormwind_city", 0, cell=3.0),
    City("Undercity", "undercity", 0, 10001, cell=2.0, found_jumps=False, dry=True),
    City("Ironforge", "ironforge", 0, cell=3.0, near_z=16.0, whole=True),
    City("Thunder Bluff", "thunder_bluff", 1, cell=2.0, found_jumps=False),  # (its mesas' rails and fences: as Undercity's)
    City("Darnassus", "darnassus", 1, cell=3.0, near_z=16.0, whole=True),
]


WALL_CHARS = 4  # characters a walled cell's index takes in `walls` (64^4 cells) ...
WALL_SEG_CHARS = 5  # ... and its wall's way through it after: its ends' shares of the cell, a character each (0-63),
# all four 0 the cell walled whole; then the surface it's over (its index in the cell, 0-based)


def enc(v: int, n: int) -> str:
    """v as n characters of ALPHA, most significant first."""
    out = []
    for _ in range(n):
        out.append(ALPHA[v & 63])
        v >>= 6
    return "".join(reversed(out))


def dec(s: str) -> int:
    v = 0
    for ch in s:
        v = v * 64 + ALPHA.index(ch)
    return v


# --- the mesh ---------------------------------------------------------------------------------------------------------

class Mesh:
    """A city mesh's walkable polys: outlines, neighbors and the neighbors within HOPS."""

    def __init__(self, tiles: dict, cont: int):
        m = RM.RecastMesh(tiles, cont)
        self.keys, self.vs = [], []
        pid_of = {}
        for key, i, t, p in m._polys():
            if p["area"] == 0:
                continue
            pid_of[(key, i)] = len(self.keys)
            self.keys.append((key, i))
            self.vs.append([t.verts[v] for v in p["verts"]])
        self.nb = [set() for _ in self.keys]
        for pid, (key, i) in enumerate(self.keys):
            for nbk, _edge in m.neighbors(key, i):
                q = pid_of.get(nbk)
                if q is not None and q != pid:
                    self.nb[pid].add(q)
                    self.nb[q].add(pid)
        self._near = {}

    def near(self, pid: int) -> set:
        """The polys within HOPS links of pid (itself too)."""
        s = self._near.get(pid)
        if s is None:
            s = {pid}
            frontier = {pid}
            for _ in range(HOPS):
                nxt = set()
                for p in frontier:
                    nxt |= self.nb[p]
                nxt -= s
                s |= nxt
                frontier = nxt
            self._near[pid] = s
        return s


def _clamp_in_cell(px, py, cx0, cy0, cell):
    return min(max(px, cx0), cx0 + cell), min(max(py, cy0), cy0 + cell)


def rasterize(mesh: Mesh, x0: float, y0: float, w: int, h: int, cell: float, keep=None):
    """{(i, j): [(z, pid, px, py)]}: every walkable poly's sample in each cell it touches (`keep(i, j)`: cells kept)."""
    out = defaultdict(list)
    for pid, vs in enumerate(mesh.vs):
        xs = [v[0] for v in vs]
        ys = [v[1] for v in vs]
        i0, i1 = max(0, int((min(xs) - x0) // cell)), min(w - 1, int((max(xs) - x0) // cell))
        j0, j1 = max(0, int((min(ys) - y0) // cell)), min(h - 1, int((max(ys) - y0) // cell))
        for i in range(i0, i1 + 1):
            cx0 = x0 + i * cell
            for j in range(j0, j1 + 1):
                if keep is not None and not keep(i, j):
                    continue
                cy0 = y0 + j * cell
                mx, my = cx0 + cell / 2, cy0 + cell / 2
                if NM._in_poly(vs, mx, my):
                    px, py = mx, my
                else:
                    px, py = NM._closest_on_poly(vs, mx, my)
                    if not (cx0 - 1e-6 <= px <= cx0 + cell + 1e-6 and cy0 - 1e-6 <= py <= cy0 + cell + 1e-6):
                        continue  # (the poly only grazes the cell's box round its middle's way: not in it)
                out[(i, j)].append((NM._height_on(vs, px, py), pid, px, py))
    return out


@dataclass
class Grid:
    city: City
    x0: float
    y0: float
    w: int
    h: int
    cell: float
    surf: dict  # (i, j) -> [ [z, pids(set), px, py] ] sorted by z
    links: dict  # (i, j, k) -> [target k in each DIRS neighbor or -1]
    road: list  # [(a (i, j, k), b, cost, kind, pts [(x, y, z)])]


def merge_cell(samples, mesh: Mesh):
    """A cell's samples as its surfaces: [z, {pids}, px, py] by height, joined polys within MERGE_Z one surface."""
    samples = sorted(samples)
    out = []
    for z, pid, px, py in samples:
        hit = None
        for s in out:
            if abs(s[0] - z) <= MERGE_Z and any(p in mesh.nb[pid] or p == pid for p in s[1]):
                hit = s
                break
        if hit:
            n = len(hit[1])
            hit[1].add(pid)
            # (the point: the middle-most sample's, the height the mean)
            hit[0] = (hit[0] * n + z) / (n + 1)
        else:
            out.append([z, {pid}, px, py])
    return sorted(out, key=lambda s: s[0])


def dz_max(dist: float) -> float:
    return dist * math.tan(math.radians(WALK_SLOPE)) + CLIMB


def walked(mesh: Mesh, s, t, near: set) -> bool:
    """Whether the straight way between two surfaces' points walks on the mesh: every WALK_STEP_YD of it over a poly of
    `near` (s's polys' HOPS round) or t's (within WALK_GAP), at the way's height there within WALK_Z, and no taller than
    WALK_STEP_Z from a height the look before. Stormwind's 1,000-trip comparison, 2026-11-23: links whose polys the mesh
    joins only through a third one elsewhere (a deck's edge and the street under it; two ramps crossing over each other)
    climbed up to 5.3 yd over a 3 yd cell: walked, the way runs off the mesh's height or steps up a wall between them.
    Where it's over none of them (Orgrimmar's wind rider tower's stairs coil round a core tighter than a cell) it's
    crossed as before, the steps counted afresh after it."""
    cand = near | t[1]
    for p in t[1]:
        cand |= mesh.near(p)
    n = max(2, math.ceil(math.dist(s[2:4], t[2:4]) / WALK_STEP_YD))
    prev = None
    for m in range(n + 1):
        f = m / n
        x, y, z = s[2] + (t[2] - s[2]) * f, s[3] + (t[3] - s[3]) * f, s[0] + (t[0] - s[0]) * f
        hs, under = [], False
        for p in cand:
            vs = mesh.vs[p]
            q = (x, y) if NM._in_poly(vs, x, y) else NM._closest_on_poly(vs, x, y)
            if math.dist(q, (x, y)) <= WALK_GAP:
                under = True
                hz = NM._height_on(vs, *q)
                if abs(hz - z) <= WALK_Z and (prev is None or any(abs(hz - g) <= WALK_STEP_Z for g in prev)):
                    hs.append(hz)
        if not under:
            prev = None
            continue  # (over none of them: a stair's core or a gap the mesh leaves, crossed as the grid always has)
        if not hs:
            return False
        prev = hs
    return True


def road_on(roads):
    """on(x, y, z): whether a city road's walked point is within WALK_ROAD_YD across and ROAD_ON_Z in height."""
    B = WALK_ROAD_YD
    idx = defaultdict(list)
    for _eid, _src, _ow, smp, *_own in roads:
        for x, y, z in smp:
            if z is not None:
                idx[(int(x // B), int(y // B))].append((x, y, z))

    def on(x, y, z):
        bx, by = int(x // B), int(y // B)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for px, py, pz in idx.get((bx + dx, by + dy), ()):
                    if (px - x) ** 2 + (py - y) ** 2 <= B * B and abs(pz - z) <= ROAD_ON_Z:
                        return True
        return False
    return on


def build_links(surf: dict, mesh: Mesh, cell: float, on_road=None) -> dict:
    links = {}
    for (i, j), ss in surf.items():
        for k, s in enumerate(ss):
            near, joined = set(), set(s[1])
            for p in s[1]:
                near |= mesh.near(p)
                joined |= mesh.nb[p]
            row = [-1] * 8
            for d, (dx, dy) in enumerate(DIRS):
                tt = surf.get((i + dx, j + dy))
                if not tt:
                    continue
                dist = cell * (math.sqrt(2) if dx and dy else 1)
                best, bd = -1, None
                for kk, t in enumerate(tt):
                    dz = abs(t[0] - s[0])
                    if dz > dz_max(dist) or not (near & t[1]):
                        continue
                    # (a climb only: down a ledge the mesh leaves is a drop, walked; the Hall of Thanes' 4 yd one)
                    if (t[0] - s[0] >= WALK_DZ and not (joined & t[1]) and not walked(mesh, s, t, near)
                            and not (on_road and on_road(s[2], s[3], s[0]) and on_road(t[2], t[3], t[0]))):
                        continue
                    if bd is None or dz < bd:
                        best, bd = kk, dz
                row[d] = best
            links[(i, j, k)] = row
    # (diagonals: only where a square way round is linked too)
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


def neighbors(g: Grid, node):
    """(next node, yards) of a node's grid links and road links."""
    i, j, k = node
    row = g.links.get(node)
    if row:
        for d, kk in enumerate(row):
            if kk >= 0:
                dx, dy = DIRS[d]
                yield (i + dx, j + dy, kk), g.cell * (math.sqrt(2) if dx and dy else 1)
    for a, b, cost, _kind, _pts in g.road_out.get(node, ()):
        yield b, cost


def grid_dist(g: Grid, a, b, limit: float) -> float:
    """The grid's way from a to b (yards, its links' costs), or inf past `limit`."""
    if a == b:
        return 0.0
    dist = {a: 0.0}
    h = [(0.0, a)]
    while h:
        d, n = heapq.heappop(h)
        if n == b:
            return d
        if d > dist.get(n, math.inf) or d > limit:
            continue
        for m, c in neighbors(g, n):
            nd = d + c
            if nd < dist.get(m, math.inf) and nd <= limit:
                dist[m] = nd
                heapq.heappush(h, (nd, m))
    return math.inf


def surface_at(g: Grid, x: float, y: float, z: float | None, reach_z: float = ROAD_ON_Z):
    i, j = int((x - g.x0) // g.cell), int((y - g.y0) // g.cell)
    ss = g.surf.get((i, j))
    if not ss:
        return None
    if z is None:
        return (i, j, 0) if len(ss) == 1 else None
    best, bd = None, None
    for k, s in enumerate(ss):
        dz = abs(s[0] - z)
        if dz <= reach_z and (bd is None or dz < bd):
            best, bd = (i, j, k), dz
    return best


def road_links(g: Grid, roads, log=print, keep: bool = False) -> list:
    """The road links (see the module's doc) from `roads` [(edge id, source, oneway, [(x, y, z)] every ROAD_STEP)].
    `keep`: the grid's links in g.road_out already (navfeatures' steps and jumps) kept, and walked over."""
    out = []
    if not keep:
        g.road_out = defaultdict(list)
    for eid, src, oneway, samples, *own in roads:
        if src in SKIP_SOURCES or len(samples) < 2:
            continue
        on = [surface_at(g, x, y, z) for x, y, z in samples]
        last = None  # (index of the last sample on the grid)
        for idx, node in enumerate(on):
            if node is None:
                continue
            if last is not None:
                a = on[last]
                stretch = samples[last:idx + 1]
                yd = sum(math.dist(stretch[q][:2], stretch[q + 1][:2]) for q in range(len(stretch) - 1))
                if a != node and (idx - last > 1 or node not in {m for m, _ in neighbors(g, a)}):
                    limit = yd * ROAD_DETOUR + ROAD_DETOUR_YD
                    if grid_dist(g, a, node, limit) > limit:
                        rise = abs((stretch[-1][2] or 0) - (stretch[0][2] or 0)) if None not in (stretch[0][2], stretch[-1][2]) else 0
                        # (a lift's road leaves and meets the ground a few times at its foot: those stretches are walks,
                        # only the one up the shaft is the ride)
                        lift = src == 5 and rise >= LIFT_RISE
                        kind = (KIND_DROP if src == 4 else KIND_LIFT if lift else KIND_STAIRS if src == 6 else KIND_WALK)
                        pts = [stretch[0]]
                        along = 0.0
                        for q in range(1, len(stretch) - 1):
                            along += math.dist(stretch[q - 1][:2], stretch[q][:2])
                            if along >= ROAD_LINK_PTS_YD:
                                pts.append(stretch[q])
                                along = 0.0
                        pts.append(stretch[-1])
                        if any(p[2] is None for p in pts):  # (a land road's: its ends' floors, straight between)
                            za_, zb_ = g.surf[a[:2]][a[2]][0], g.surf[node[:2]][node[2]][0]
                            pts = [(p[0], p[1], za_ + (zb_ - za_) * q / max(1, len(pts) - 1)) for q, p in enumerate(pts)]
                        cost = max(yd, 1.0) * ROAD_FACTOR
                        if lift and own and own[0]:
                            cost = max(cost, own[0])  # (a lift: the Router's own yards for it, the wait and the ride)
                        out.append((a, node, cost, kind, pts))
                        g.road_out[a].append((a, node, cost, kind, pts))
                        if not oneway:
                            back = list(reversed(pts))
                            out.append((node, a, cost, kind, back))
                            g.road_out[node].append((node, a, cost, kind, back))
            last = idx
    log(f"  {g.city.name}: {len(out)} road links")
    return out


def lift_platforms(g: Grid, mesh: Mesh, x: float, y: float, z: float) -> list:
    """The surfaces players board a lift's car from at its stop (x, y, z): within lifts.LIFT_PLATFORM_YD of its shaft and
    LIFT_PLATFORM_Z of the stop's height, on the mesh's piece that reaches the ground round it (lifts.ground_piece: up
    its stairs or ramp; never the ground under a raised platform, nor the structure between two cars), nearest first."""
    from . import lifts as LF
    ground = LF.ground_piece(mesh.vs, mesh.nb, x, y, z)
    r = int(math.ceil(LF.LIFT_PLATFORM_YD / g.cell))
    i0, j0 = int((x - g.x0) // g.cell), int((y - g.y0) // g.cell)
    out = []
    for i in range(i0 - r, i0 + r + 1):
        for j in range(j0 - r, j0 + r + 1):
            for k, sf in enumerate(g.surf.get((i, j), ())):
                if (math.dist((sf[2], sf[3]), (x, y)) <= LF.LIFT_PLATFORM_YD and abs(sf[0] - z) <= LF.LIFT_PLATFORM_Z
                        and sf[1] & ground):
                    out.append((i, j, k))
    return sorted(out, key=lambda n: math.dist(g.surf[n[:2]][n[2]][2:4], (x, y)))[:LIFT_FLOORS]


LIFT_FLOORS = 4  # a lift car's platform floors linked at each stop, the nearest its shaft


def lift_shaft_links(g: Grid, mesh: Mesh, links: list, log=print) -> list:
    """The city's lift roads' rides (KIND_LIFT, road_links) made each car's own (lifts.shafts: the dump's elevators, two
    cars a lift, each in its shaft): both ways between its platforms at its two stops (lift_platforms), drawn from the
    platform to the shaft, up or down it and off onto the other platform, costing the lift road's ride (Kooki3z
    2026-11-22 at Thunder Bluff's: the ride was joined to the ground at the stairs' foot, not the platform they lead
    to). Without the dump, or a lift none of whose cars' platforms are found, its road's rides as they were."""
    try:
        from . import lifts as LF
        shafts = [sh for sh in LF.shafts(LF.elevators(), g.city.cont)
                  if g.x0 <= sh["x"] < g.x0 + g.w * g.cell and g.y0 <= sh["y"] < g.y0 + g.h * g.cell]
    except Exception:
        return links
    if g.city.level is not None or not shafts:
        return links
    made, cost_of, rides = [], {}, defaultdict(list)
    for sh in shafts:
        lo = lift_platforms(g, mesh, sh["x"], sh["y"], sh["lo"])
        hi = lift_platforms(g, mesh, sh["x"], sh["y"], sh["hi"])
        if lo and hi:
            made.append((sh, lo, hi))
    lifted = {sh["lift"] for sh, _lo, _hi in made}
    out = []
    for r in links:
        a, b, cost, kind, pts = r
        if kind == KIND_LIFT:
            near = [sh for sh in shafts if sh["lift"] in lifted
                    and min(math.dist(pts[0][:2], (sh["x"], sh["y"])), math.dist(pts[-1][:2], (sh["x"], sh["y"]))) <= LF.LIFT_ROAD_YD]
            if near:
                for sh in near:
                    cost_of[sh["lift"]] = max(cost_of.get(sh["lift"], 0.0), cost)
                    rides[sh["lift"]].append(r)
                continue
        out.append(r)
    n = 0
    for sh, lo, hi in made:
        cost = cost_of.get(sh["lift"])
        if cost is None:
            continue
        x, y = sh["x"], sh["y"]
        for a in lo:
            for b in hi:
                sa, sb = g.surf[a[:2]][a[2]], g.surf[b[:2]][b[2]]
                pa, pb = (sa[2], sa[3], sa[0]), (sb[2], sb[3], sb[0])
                out.append((a, b, cost, KIND_LIFT, [pa, (x, y, pa[2]), (x, y, pb[2]), pb]))
                out.append((b, a, cost, KIND_LIFT, [pb, (x, y, pb[2]), (x, y, pa[2]), pa]))
                n += 2
    g.road_out = defaultdict(list)
    for r in out:
        g.road_out[r[0]].append(r)
    log(f"  {g.city.name}: {n} lift links from {len(made)} cars' platforms ({sum(len(v) for v in rides.values())} of the "
        f"roads' rides replaced)")
    return out


def pieces(g: Grid) -> dict:
    """Each surface's piece (links both ways), 0 the biggest: {node: piece}, and the pieces' sizes."""
    adj = defaultdict(set)
    for node in g.links:
        for m, _c in neighbors(g, node):
            adj[node].add(m)
            adj[m].add(node)
    piece, sizes = {}, []
    for start in g.links:
        if start in piece:
            continue
        c = len(sizes)
        piece[start] = c
        st, n = [start], 0
        while st:
            p = st.pop()
            n += 1
            for q in adj[p]:
                if q not in piece:
                    piece[q] = c
                    st.append(q)
        sizes.append(n)
    order = sorted(range(len(sizes)), key=lambda c: -sizes[c])
    rank = {c: r for r, c in enumerate(order)}
    return {n: rank[c] for n, c in piece.items()}, [sizes[c] for c in order]


# --- the city's roads and cells (the addon's own, under the game harness) -------------------------------------------

def harness_inputs(city: City, box, cell: float, log=print):
    """(keep(i, j) or None, roads) from the addon itself: a capital's own cells (MARGIN_YD round them), and the
    city's roads every ROAD_STEP at their heights: [(edge id, source, oneway, [(x, y, z)])]."""
    from .gameharness import start
    from .navcompare import NO_HEIGHT

    lua, ns = start()
    R = ns.Router
    gl = city.level if city.level is not None else city.cont
    x0, y0, x1, y1 = box
    R.NearestEdges(gl, (x0 + x1) / 2, (y0 + y1) / 2)  # (the level's roads built)
    g = R.DebugGraph(gl)
    hz = g.z if g.z is not None else g.nz
    roads = []
    drops = g.drops
    for eid in g.e.keys():
        e = g.e[eid]
        src = int(e[4])
        pts = [(e[k], e[k + 1]) for k in range(5, len(e) + 1, 2) if e[k] is not None and e[k + 1] is not None]
        if len(pts) < 2 or not any(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in pts):
            continue
        za = hz[e[1]] if hz is not None else None
        zb = hz[e[2]] if hz is not None else None
        land = za is None or zb is None or za < NO_HEIGHT or zb < NO_HEIGHT or (g.z is None and za == 0 and zb == 0)
        if land:
            # (a land road, no height of its own: only one through a capital's own cells, its gate's way in, taken
            # where a cell has one floor (surface_at with no height). Stormwind's gate road: the mesh has a gap of a
            # few yards at the gate, and the grid's streets were cut off from the land)
            if city.level is not None or not any(
                    (lambda v: v is not None and v != 1)(ns.Passability.Overlay(city.cont, p[0], p[1])) for p in pts):
                continue
            za = zb = None
        length = sum(math.dist(pts[q], pts[q + 1]) for q in range(len(pts) - 1)) or 1.0
        samples, along = [], 0.0
        for q in range(len(pts) - 1):
            (ax, ay), (bx, by) = pts[q], pts[q + 1]
            d = math.dist(pts[q], pts[q + 1])
            n = max(1, int(d / ROAD_STEP))
            for s in range(n):
                t = s / n
                samples.append((ax + (bx - ax) * t, ay + (by - ay) * t,
                                None if land else za + (zb - za) * (along + d * t) / length))
            along += d
        samples.append((pts[-1][0], pts[-1][1], zb))
        oneway = bool(drops is not None and drops[eid]) or src == 4
        roads.append((int(eid), src, oneway, samples, float(e[3])))
    # (the NPCs' spots in the city, Data/NpcFloors.lua: halls no road goes into, Grommash Hold, count as the city's too;
    # a road of no length, ANCHOR_SOURCE, that road_links passes over)
    nf = ns.NpcFloors and ns.NpcFloors[gl]
    if nf is not None:
        for k in range(1, len(nf) - 1, 3):
            x, y, z = nf[k], nf[k + 1], nf[k + 2]
            if x0 <= x <= x1 and y0 <= y <= y1:
                roads.append((-k, ANCHOR_SOURCE, False, [(x, y, z)]))
    # (the level's lifts up out of it, Undercity's to the Ruins: a road of no length, LIFT_SOURCE, for navfeatures'
    # lifts: their shafts found on the mesh)
    if city.level is not None:
        for i in range(1, len(ns.Transports) + 1):
            t = ns.Transports[i]
            if t[1] == city.level and t[8] == "lift" and t.z1 is not None:
                roads.append((-100000 - i, LIFT_SOURCE, False, [(t[2], t[3], t.z1)], float(t[7])))
    keep = None
    if city.level is None:
        ov = ns.Passability.Overlay
        w, h = int((x1 - x0) // cell) + 1, int((y1 - y0) // cell) + 1
        own = set()
        for i in range(w):
            for j in range(h):
                v = ov(city.cont, x0 + (i + 0.5) * cell, y0 + (j + 0.5) * cell)
                if v is not None and v != 1:
                    own.add((i, j))
        m = int(math.ceil(MARGIN_YD / cell))
        kept = set()
        for (i, j) in own:
            for di in range(-m, m + 1):
                for dj in range(-m, m + 1):
                    kept.add((i + di, j + dj))
        log(f"  {city.name}: {len(own)} cells of its own grid, {len(kept)} with the margin")
        keep = lambda i, j: (i, j) in kept  # noqa: E731
    return keep, roads


# --- building ---------------------------------------------------------------------------------------------------------

def road_heights(roads, near_z: float = NEAR_ROAD_Z):
    """near(x, y, z): whether a city road runs within NEAR_ROAD_YD across and NEAR_ROAD_Z in height of (x, y, z). Recast
    walks the land under a city's model where the model stands clear of it (Orgrimmar's east half has a floor at 9 under
    its streets at 20-70, joined to the land at the model's edges): ground no road of the city is near in height is
    ground the game never lets a player reach."""
    B = NEAR_ROAD_BUCKET
    raw = defaultdict(list)
    for _eid, _src, _ow, smp, *_own in roads:
        for x, y, z in smp:
            if z is not None:
                raw[(int(x // B), int(y // B))].append(z)
    r = int(math.ceil(NEAR_ROAD_YD / B))
    dil = defaultdict(list)
    for (bx, by), zs in raw.items():
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                dil[(bx + dx, by + dy)].extend(zs)
    for k in dil:
        dil[k] = sorted(set(round(z, 1) for z in dil[k]))

    def near(x, y, z):
        zs = dil.get((int(x // B), int(y // B)))
        if not zs:
            return False
        i = bisect.bisect_left(zs, z - near_z)
        return i < len(zs) and zs[i] <= z + near_z
    return near


def build(city: City, log=print, inputs=None) -> Grid:
    tiles = RM.load(RM.mesh_path(city.mesh))
    mesh = Mesh(tiles, city.cont)
    xs = [v[0] for vs in mesh.vs for v in vs]
    ys = [v[1] for vs in mesh.vs for v in vs]
    cell = city.cell
    x0, y0 = math.floor(min(xs) / cell) * cell, math.floor(min(ys) / cell) * cell
    w, h = int((max(xs) - x0) // cell) + 1, int((max(ys) - y0) // cell) + 1
    keep, roads = inputs if inputs is not None else harness_inputs(city, (x0, y0, max(xs), max(ys)), cell, log)
    samples = rasterize(mesh, x0, y0, w, h, cell, keep)
    surf = {c: merge_cell(s, mesh) for c, s in samples.items()}
    if city.dry:
        from . import navfeatures as NF
        tris = NF.Tris.load(city.mesh)
        if tris is not None:
            before_wet = sum(len(ss) for ss in surf.values())
            surf = {c: kept for c, ss in surf.items()
                    if (kept := [q for q in ss if not tris.wet(q[2], q[3], q[0] + WET_Z, 0.0)])}
            log(f"  {city.name}: {before_wet - sum(len(ss) for ss in surf.values())} surfaces under its liquid left out")
    near_road = road_heights(roads, city.near_z or NEAR_ROAD_Z)
    before = sum(len(ss) for ss in surf.values())
    surf = {c: kept for c, ss in surf.items()
            if (kept := [s for s in ss if near_road(x0 + (c[0] + 0.5) * cell, y0 + (c[1] + 0.5) * cell, s[0])])}
    log(f"  {city.name}: {before} surfaces, {sum(len(ss) for ss in surf.values())} near a road's height")
    links = build_links(surf, mesh, cell, road_on(roads))
    if FEATURES:  # (links joined only by a door's polys two hops off, through the wall beside it: cut)
        from . import navfeatures as NF
        tris = NF.Tris.load(city.mesh)
        cut = NF.cut_wall_links(surf, links, mesh, tris, cell, log)
        walled = NF.walled_cells(surf, tris, cell, x0, y0, cut, log)
    else:
        walled = {}
    g = Grid(city, x0, y0, w, h, cell, surf, links, [])
    g.walled = walled
    g.road = road_links(g, roads, log)
    # (pruning: the pieces kept)
    piece, sizes = pieces(g)
    linked = {a for a, *_ in g.road} | {b for _a, b, *_ in g.road}
    piece_linked = {piece[n] for n in linked if n in piece}
    # (the pieces the city's roads touch: its streets, halls and places. Not the canyon's rims, the roofs and wall
    # tops Recast found walkable, the land round it no road of the city's reaches)
    touched = set()
    for _eid, _src, _ow, smp, *_own in roads:
        for x, y, z in smp:
            n = surface_at(g, x, y, z)
            if n is not None and n in piece:
                touched.add(piece[n])
    keep_p = {p for p in touched if sizes[p] >= MIN_PIECE} | piece_linked
    _prune(g, lambda n: piece.get(n) in keep_p)
    n_road = len(g.road)
    reach_links(g, roads, log)
    log(f"  {city.name}: {len(sizes)} pieces, {len(keep_p)} kept, {count(g)} surfaces in {len(g.surf)} cells")
    g.features = None
    if FEATURES:
        from . import navfeatures as NF
        NF.apply(g, mesh, roads, g.road[n_road:], log)
    # (the lift roads' rides as each car's own, from its platforms: last, the road links as made above otherwise)
    g.road = lift_shaft_links(g, mesh, g.road, log)
    return g


def reach_links(g: Grid, roads, log=print) -> None:
    """An NPC's floor the city's grid has no way onto (Darnassus's bank: its bankers stand behind a round counter, a floor
    of its own, and no road goes in) joined to the city's floor round it, within REACH_YD across and REACH_Z in height:
    from each side (the nearest in each eighth round the floor's middle) a road link each way (KIND_WALK, REACH_COST more
    than its yards: never a way through), so a route ends at the counter's nearest front and across it to the NPC, as the
    Router's own does, instead of no way at all."""
    piece, sizes = pieces(g)
    by_piece = defaultdict(list)
    for n, p in piece.items():
        by_piece[p].append(n)
    anchored = set()
    for _eid, src, _ow, smp, *_own in roads:
        if src == ANCHOR_SOURCE:
            n = surface_at(g, *smp[0])
            if n is not None and piece.get(n, 0) != 0:
                anchored.add(piece[n])
    r = int(math.ceil(REACH_YD / g.cell))
    added = 0
    for p in sorted(anchored):
        nodes = by_piece[p]
        mx = sum(g.surf[n[:2]][n[2]][2] for n in nodes) / len(nodes)
        my = sum(g.surf[n[:2]][n[2]][3] for n in nodes) / len(nodes)
        best = {}  # (eighth round the middle) -> (yards, city floor, NPC floor, their points)
        for (i, j, k) in nodes:
            s = g.surf[(i, j)][k]
            for di in range(-r, r + 1):
                for dj in range(-r, r + 1):
                    for kk, t in enumerate(g.surf.get((i + di, j + dj), ())):
                        m = (i + di, j + dj, kk)
                        if piece.get(m) != 0 or abs(t[0] - s[0]) > REACH_Z:
                            continue
                        d = math.dist(s[2:4], t[2:4])
                        if d > REACH_YD:
                            continue
                        side = int((math.atan2(t[3] - my, t[2] - mx) + math.pi) / (math.pi / 4)) % 8
                        if side not in best or d < best[side][0]:
                            best[side] = (d, m, (i, j, k), (t[2], t[3], t[0]), (s[2], s[3], s[0]))
        for d, a, b, pa, pb in best.values():
            cost = max(d, 1.0) * ROAD_FACTOR + REACH_COST
            for x, y, pts in ((a, b, [pa, pb]), (b, a, [pb, pa])):
                g.road.append((x, y, cost, KIND_WALK, pts))
                g.road_out[x].append((x, y, cost, KIND_WALK, pts))
        if best:
            added += 1
    if added:
        log(f"  {g.city.name}: {added} NPC floors joined to the city's across a counter")


def _prune(g: Grid, ok) -> None:
    """Only the surfaces ok(node) says, renumbered in their cells; links to the others dropped."""
    remap = {}
    surf = {}
    for (i, j), ss in g.surf.items():
        kept = [k for k in range(len(ss)) if ok((i, j, k))]
        if not kept:
            continue
        surf[(i, j)] = [ss[k] for k in kept]
        for nk, k in enumerate(kept):
            remap[(i, j, k)] = (i, j, nk)
    links = {}
    for node, row in g.links.items():
        nn = remap.get(node)
        if nn is None:
            continue
        i, j, _k = node
        new = []
        for d, kk in enumerate(row):
            dx, dy = DIRS[d]
            t = remap.get((i + dx, j + dy, kk)) if kk >= 0 else None
            new.append(t[2] if t else -1)
        links[nn] = new
    road = []
    for a, b, cost, kind, pts in g.road:
        if a in remap and b in remap:
            road.append((remap[a], remap[b], cost, kind, pts))
    g.surf, g.links, g.road = surf, links, road
    g.road_out = defaultdict(list)
    for a, b, cost, kind, pts in road:
        g.road_out[a].append((a, b, cost, kind, pts))


def count(g: Grid) -> int:
    return sum(len(ss) for ss in g.surf.values())


# --- writing ----------------------------------------------------------------------------------------------------------

MAX_IN_CELL = 7  # (3 bits a direction's target: 1-7)


def encode(g: Grid) -> dict:
    """The city's entry's fields (see the module's doc)."""
    # (the cells' box: only where surfaces are)
    ii = [c[0] for c in g.surf]
    jj = [c[1] for c in g.surf]
    i0, j0 = min(ii), min(jj)
    w, h = max(ii) - i0 + 1, max(jj) - j0 + 1
    x0, y0 = g.x0 + i0 * g.cell, g.y0 + j0 * g.cell
    zs = [s[0] for ss in g.surf.values() for s in ss] + [p[2] for *_x, pts in g.road for p in pts]
    zmin = math.floor(min(zs)) - 1
    order = {}  # (i, j, k) -> 0-based surface index in the file
    cells, s_out, base = [], [], []
    n = 0
    for i in range(w):
        for j in range(h):
            c = i * h + j
            if c % BLOCK == 0:
                base.append(n)
            ss = g.surf.get((i + i0, j + j0), [])
            ss = ss[:MAX_IN_CELL]
            cells.append(ALPHA[len(ss)])
            for k, s in enumerate(ss):
                order[(i + i0, j + j0, k)] = n
                n += 1
    for i in range(w):
        for j in range(h):
            ss = g.surf.get((i + i0, j + j0), [])[:MAX_IN_CELL]
            for k, s in enumerate(ss):
                zq = int(round((s[0] - zmin) / ZQ))
                assert 0 <= zq < 4096, (g.city.name, s[0], zmin)
                cx0, cy0 = g.x0 + (i + i0) * g.cell, g.y0 + (j + j0) * g.cell
                ox = min(OFF_STEPS - 1, max(0, int((s[2] - cx0) / g.cell * OFF_STEPS)))
                oy = min(OFF_STEPS - 1, max(0, int((s[3] - cy0) / g.cell * OFF_STEPS)))
                row = g.links.get((i + i0, j + j0, k), [-1] * 8)
                t = [row[d] + 1 if 0 <= row[d] < MAX_IN_CELL else 0 for d in range(8)]
                links = "".join(ALPHA[t[2 * m] * 8 + t[2 * m + 1]] for m in range(4))
                s_out.append(enc(zq, 2) + ALPHA[ox * OFF_STEPS + oy] + links)
    rl = []
    for a, b, cost, kind, pts in g.road:
        if a not in order or b not in order:
            continue
        flat = ",".join(f"{p[0]:.1f},{p[1]:.1f},{p[2]:.1f}" for p in pts)
        rl.append(f"{order[a] + 1},{order[b] + 1},{cost:.0f},{kind},{flat}")
    feat = ""
    if getattr(g, "features", None) is not None:
        from . import navfeatures as NF
        feat = ";".join(f"{k},{w:.1f}," + ",".join(f"{p[0]:.1f},{p[1]:.1f},{p[2]:.1f}" for p in pts)
                        for k, w, pts in NF.feature_lines(g.features, g.road))
    exits = ";".join(",".join(f"{p[0]:.1f},{p[1]:.1f},{p[2]:.1f}" for p in e) for e in getattr(g, "lift_exits", None) or [])
    # (the walled cells, navfeatures.cut_wall_links: each cell's index i * h + j in the box, WALL_CHARS characters)
    walled = getattr(g, "walled", None) or {}

    def seg_chars(v):
        if v is None:
            return ALPHA[0] * WALL_SEG_CHARS
        k, v = v[0], v[1:]
        q = [min(63, max(0, round(f * 63))) for f in v]
        if q[0] == q[2] and q[1] == q[3]:
            q[2] = min(63, q[2] + 1)  # (never all four alike: that's walled whole)
        if not any(q):
            q[2] = 1
        return "".join(ALPHA[k] for k in q) + ALPHA[k]
    walls = "".join(enc((i - i0) * h + (j - j0), WALL_CHARS) + seg_chars(v) for i, j in sorted(walled)
                    if (i, j) in g.surf for v in (walled[(i, j)] or [None]))
    return {"x0": x0, "y0": y0, "w": w, "h": h, "zmin": zmin, "n": n, "cells": "".join(cells), "s": "".join(s_out),
            "base": base, "links": ";".join(rl), "feat": feat, "exits": exits, "walls": walls}


BAKE_PARAMS = ("CELL", "MERGE_Z", "OFF_STEPS", "ZQ", "CLIMB", "WALK_SLOPE", "HOPS", "MARGIN_YD", "MIN_PIECE", "ROAD_STEP",
               "ROAD_ON_Z", "ROAD_DETOUR", "ROAD_DETOUR_YD", "ROAD_FACTOR", "ROAD_LINK_PTS_YD", "BLOCK", "NEAR_ROAD_YD",
               "NEAR_ROAD_Z", "NEAR_ROAD_BUCKET", "MAX_IN_CELL", "REACH_YD", "REACH_Z", "REACH_COST", "LIFT_RISE", "WET_Z",
               "WALK_DZ", "WALK_GAP", "WALK_Z", "WALK_STEP_YD", "WALK_STEP_Z", "WALK_ROAD_YD")


def bake_stamp() -> str:
    """The bake's parameters and cities, hashed: written into the data, so a change to them without a new bake fails
    test_city_grid's staleness test."""
    g = globals()
    parts = [f"{k}={g[k]!r}" for k in BAKE_PARAMS] + [repr(c) for c in CITIES]
    if FEATURES:  # (navfeatures' parameters too: they decide the links found and the stairs and bridges)
        from . import navfeatures as NF
        parts += [f"{k}={getattr(NF, k)!r}" for k in NF.BAKE_PARAMS]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]


def stamp_of(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def mesh_stamp(city: City) -> str:
    p = RM.mesh_path(city.mesh)
    return hashlib.sha1(p.read_bytes()).hexdigest()[:12] if p.exists() else "none"


def lua_text(grids: list, client: str = "") -> str:
    lines = [f"-- GENERATED by `agps city-grid --write` (app/azerothgps/citygrid.py){' from client ' + client if client else ''}."
             " Do not edit by hand.",
             "-- The capitals' layered walk grids (1.4.0's city routing, docs/city-rework-1.4.0.md): numbers only, baked",
             "-- from our own Recast meshes of the cities' collision. Read by CityGrid.lua.",
             "local _, ns = ...",
             "ns.CityGridData = ns.CityGridData or {}"]
    for g in grids:
        e = encode(g)
        c = g.city
        lv = f" level = {c.level}," if c.level is not None else ""
        lv += " whole = true," if c.whole else ""
        body = (f'{{ cont = {c.cont},{lv} cell = {g.cell:g}, x0 = {e["x0"]:.1f}, y0 = {e["y0"]:.1f}, w = {e["w"]}, '
                f'h = {e["h"]}, zmin = {e["zmin"]}, zq = {ZQ:g}, offs = {OFF_STEPS}, block = {BLOCK}, n = {e["n"]},\n'
                f'  mesh = "{mesh_stamp(c)}", bake = "{bake_stamp()}",{tris_line(c)}\n'
                f'  cells = "{e["cells"]}",\n'
                f'  s = "{e["s"]}",\n'
                f'  base = "{",".join(map(str, e["base"]))}",\n'
                f'  links = "{e["links"]}",\n'
                + (f'  feat = "{e["feat"]}",\n' if e["feat"] else "")
                + (f'  exits = "{e["exits"]}",\n' if e["exits"] else "")
                + (f'  walls = "{e["walls"]}",\n' if e["walls"] else "") + "}")
        lines.append(f"ns.CityGridData[{c.name!r}] = {body}".replace("'", '"'))
    text = "\n".join(lines) + "\n"
    return text


def tris_line(city: City) -> str:
    """` tris = "<stamp>",`: the collision triangles navfeatures read (its links' checks), where it ran."""
    if not FEATURES:
        return ""
    from . import navfeatures as NF
    return f' tris = "{NF.tris_stamp(city.mesh)}",'


def out_path() -> Path:
    return ADDON_DIR / "Data" / "CityGrid.lua"


def stats(g: Grid) -> dict:
    e = encode(g)
    nlinks = sum(1 for row in g.links.values() for t in row if t >= 0)
    multi = sum(1 for ss in g.surf.values() if len(ss) > 1)
    return {"city": g.city.name, "cell": g.cell, "surfaces": e["n"], "cells": len(g.surf), "stacked_cells": multi,
            "links": nlinks, "road_links": len(g.road), "w": e["w"], "h": e["h"],
            "bytes": len(e["cells"]) + len(e["s"]) + len(e["links"]) + len(e["feat"]) + 6 * len(e["base"]),
            "feat_bytes": len(e["feat"]), "link_bytes": len(e["links"])}


def run(only=None, cells=None, write=False, log=print) -> list:
    """Bake the cities (`only`: names), report each one's size (`cells`: sizes to compare), write Data/CityGrid.lua."""
    out_dir = data_dir() / "debug" / "citygrid"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, grids = [], []
    for city in CITIES:
        if only and not any(o.lower() in city.name.lower() for o in only):
            continue
        tiles = RM.load(RM.mesh_path(city.mesh))
        mesh = Mesh(tiles, city.cont)
        xs = [v[0] for vs in mesh.vs for v in vs]
        ys = [v[1] for vs in mesh.vs for v in vs]
        for c in (cells or [city.cell]):
            sub = dataclasses.replace(city, cell=c)
            x0, y0 = math.floor(min(xs) / c) * c, math.floor(min(ys) / c) * c
            inputs = harness_inputs(sub, (x0, y0, max(xs), max(ys)), c, log)
            g = build(sub, log, inputs)
            st = stats(g)
            log(f"  {st}")
            rows.append(st)
            if c == city.cell:
                grids.append(g)
    (out_dir / "stats.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    if write and grids and not only:
        text = lua_text(grids)
        out_path().write_text(text, encoding="utf-8", newline="\n")
        log(f"wrote {out_path()} ({len(text) / 1e6:.2f} MB)")
    return rows


# --- checking ---------------------------------------------------------------------------------------------------------

CHECK_PLACES = {  # (shipped NPCs: Data/Npcs.lua's names) the trips checked in each city, every one to every other
    "Orgrimmar": ["Innkeeper Gryshka", "Thrall", "Doras", "Zevrost", "Ur'kyo", "Sorek", "Gest", "Karus"],
    "Stormwind City": ["Dungar Longdrink", "High Priestess Laurena", "Demisette Cloyce", "Osborne the Night Man",
                       "General Marcus Jonathan", "Ander Germaine", "Lord Grayson Shadowbreaker", "Thurman Mullby"],
    "Undercity": ["Michael Garrett", "Master Apothecary Faranell", "Kaal Soulreaper", "Randolph Montague",
                  "Varimathras", "Armand Cromwell", "Charles Seaton", "Sydney Upton"],
    # (the Commons, the throne room, the gryphons over the Great Forge, the Military and Mystic Wards, the Forlorn
    # Cavern, Tinker Town by the tram, the bank)
    "Ironforge": ["Innkeeper Firebrew", "King Magni Bronzebeard", "Gryth Thurden", "Kelstrum Stonebreaker",
                  "Milstaff Stormeye", "Hulfdan Blackbeard", "Tinkmaster Overspark", "Barnum Stonemantle"],
    # (the central mesa, the wind rider tower, the Elder, Hunter and Spirit Rises, the Pools of Vision under the last)
    "Thunder Bluff": ["Innkeeper Pala", "Cairne Bloodhoof", "Tal", "Torn", "Turak Runetotem", "Kary Thunderhorn",
                      "Siln Skychaser", "Archmage Shymm"],
    # (the Craftsmen's Terrace, the Temple of the Moon, up the Cenarion Enclave's trees (spiral stairs), the Warrior's
    # Terrace, the bank, the rogues' hollow under the Enclave)
    "Darnassus": ["Innkeeper Saelienne", "Tyrande Whisperwind", "Arch Druid Fandral Staghelm", "Jeen'ra Nightrunner",
                  "Arias'ta Bladesinger", "Idriana", "Syurna", "Me'lynn"],
}
CHECK_STEP = 0.5  # yards: a route walked this often over the mesh
CHECK_XY = 1.5  # yards: a point is on the mesh with a walkable poly this near across ...
CHECK_Z = 3.0  # ... and this near its height (a route's heights are its ends', straight between: a ramp's middle can
# be off a little)
CHECK_OFF_YD = 3.0  # yards: a run off the mesh this long is a fault (through a wall, over a gap)


def npc_spots(names):
    """{name: (level, x, y, z)} of shipped NPCs (Data/Npcs.lua: their first spawn)."""
    import re
    txt = (ADDON_DIR / "Data" / "Npcs.lua").read_text(encoding="utf-8")
    out = {}
    for line in txt.splitlines():
        parts = line.split("|")
        if len(parts) >= 7 and parts[1] in names and parts[1] not in out:
            m = re.search(r"(-?\d+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)", parts[6])
            if m:
                out[parts[1]] = (int(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)))
    return out


def walk_on_mesh(index, pts, hs, skip=None):
    """A route's points (x, y flat) and heights walked over the mesh: (yards, yards off it, the longest run off it).
    `skip(i)`: pieces not judged (a road link's: stairs or a drop the mesh lacks)."""
    total = off = run = worst = 0.0
    n = len(pts) // 2
    for i in range(n - 1):
        ax, ay, bx, by = pts[2 * i], pts[2 * i + 1], pts[2 * i + 2], pts[2 * i + 3]
        za, zb = hs[i] if hs else None, hs[i + 1] if hs else None
        L = math.hypot(bx - ax, by - ay)
        if skip and skip(i):
            total += L
            run = 0.0
            continue
        m = max(1, int(L / CHECK_STEP))
        for q in range(m):
            t = q / m
            x, y = ax + (bx - ax) * t, ay + (by - ay) * t
            z = za + (zb - za) * t if (za is not None and zb is not None and za is not False and zb is not False) else None
            fl = index.floors(x, y, CHECK_XY)
            ok = bool(fl) and (z is None or any(abs(f[0] - z) <= CHECK_Z for f in fl))
            step = L / m
            total += step
            if ok:
                run = 0.0
            else:
                off += step
                run += step
                worst = max(worst, run)
    return total, off, worst


def check(only=None, log=print) -> list:
    """Every CHECK_PLACES trip routed with the option on (the grid) and off (the Router's own): yards each, and the grid's
    walked over the mesh (runs off it: through a wall, over a gap). data/debug/citygrid/check.json."""
    from .gameharness import start
    from .navcompare import PolyIndex

    lua, ns = start()
    R, CG = ns.Router, ns.CityGrid
    out = []
    for city in CITIES:
        if only and not any(o.lower() in city.name.lower() for o in only):
            continue
        index = PolyIndex(RM.RecastMesh(RM.load(RM.mesh_path(city.mesh)), city.cont))
        spots = npc_spots(set(CHECK_PLACES[city.name]))
        names = [n for n in CHECK_PLACES[city.name] if n in spots]
        for a in names:
            for b in names:
                if a == b:
                    continue
                la, xa, ya, za = spots[a]
                _lb, xb, yb, zb = spots[b]
                ns.settings.gps.cityGrid = False
                own = R.Route(la, xa, ya, xb, yb, lua.table(z=za, tz=zb))
                ns.settings.gps.cityGrid = True
                CG.routes, CG.order = lua.table(), lua.table()
                import time
                t = time.perf_counter()
                r = R.Route(la, xa, ya, xb, yb, lua.table(z=za, tz=zb))
                ms = (time.perf_counter() - t) * 1000
                ns.settings.gps.cityGrid = False
                grid = r.cityGrid is not None
                pts = [r.pts[i] for i in range(1, len(r.pts) + 1)]
                hz = r.zs if r.zs is not None else r.fz
                hs = [hz[i] if hz[i] is not False else None for i in range(1, len(hz) + 1)] if hz is not None else None
                kinds = [r.kinds[i] for i in range(1, len(r.kinds) + 1)]
                link = r.onLink
                total, off, worst = walk_on_mesh(index, pts, hs, skip=lambda i: kinds[i] not in (0, 1) or (
                    link is not None and link[i + 1])) if grid else (0, 0, 0)
                # (the Router's own walked too, its straight legs only (its roads are drawn and traced, the truth): a
                # longer grid route against an own one through a wall is no fault)
                opts_ = [own.pts[i] for i in range(1, len(own.pts) + 1)]
                okinds = [own.kinds[i] for i in range(1, len(own.kinds) + 1)]
                ohz = own.zs if own.zs is not None else own.fz
                ohs = ([ohz[i] if ohz[i] is not False and ohz[i] > -9000 else None for i in range(1, len(ohz) + 1)]
                       if ohz is not None else None)
                _t, own_off, own_worst = walk_on_mesh(index, opts_, ohs, skip=lambda i: okinds[i] != 1)
                row = {"city": city.name, "from": a, "to": b, "grid": grid, "yd": round(r.length, 1),
                       "own_yd": round(own.length, 1), "pts": len(pts) // 2, "own_pts": len(own.pts) // 2,
                       "ms": round(ms, 1), "nodes": CG.lastNodes, "off_yd": round(off, 1), "worst_off": round(worst, 1),
                       "own_off_yd": round(own_off, 1), "own_worst_off": round(own_worst, 1),
                       "ok": grid and worst < CHECK_OFF_YD}
                out.append(row)
                log(f"  {city.name}: {a} -> {b}: {'grid' if grid else 'own'} {row['yd']} yd (own {row['own_yd']}), "
                    f"{row['pts']} points (own {row['own_pts']}), off the mesh {row['off_yd']} yd (longest {row['worst_off']}),"
                    f" {row['ms']} ms")
    d = data_dir() / "debug" / "citygrid"
    d.mkdir(parents=True, exist_ok=True)
    (d / "check.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for city in {r["city"] for r in out}:
        rows = [r for r in out if r["city"] == city]
        g = [r for r in rows if r["grid"]]
        log(f"{city}: {len(g)} of {len(rows)} on the grid; yards {sum(r['yd'] for r in g):.0f} against the Router's "
            f"{sum(r['own_yd'] for r in g):.0f}; shorter {sum(r['yd'] < r['own_yd'] - 1 for r in g)}, longer "
            f"{sum(r['yd'] > r['own_yd'] + 1 for r in g)}; off the mesh past {CHECK_OFF_YD} yd: "
            f"{sum(not r['ok'] for r in g)}")
    return out


def check_gates(only=None, log=print) -> list:
    """`capitals --check`'s trips with the option on: from outside each capital's gate (Undercity: from its lifts'
    bottoms) to every city place (Data/CityPlaces.lua, with its NPC's height), the grid's route against the Router's
    own: yards, whether it ends on the place's floor, and the grid's walked over the mesh.
    data/debug/citygrid/gates.json."""
    from . import capitals as CP
    from .gameharness import start
    from .navcompare import PolyIndex

    lua, ns = start()
    R, CG = ns.Router, ns.CityGrid
    caps = {c.name: c for c in CP.CAPITALS}
    out = []
    for city in CITIES:
        if only and not any(o.lower() in city.name.lower() for o in only):
            continue
        index = PolyIndex(RM.RecastMesh(RM.load(RM.mesh_path(city.mesh)), city.cont))
        if city.level is None:
            cap = caps[city.name]
            starts = [(cap.cont, *(cap.outside or cap.gates[0]), None)]
            heights = CP.place_heights(cap)
            places = [(n, x, y, heights.get(n)) for n, x, y in CP.map_places(cap)]
        else:
            starts = []
            for i in range(1, len(ns.Transports) + 1):
                t = ns.Transports[i]
                if t[1] == city.level and t.z1 is not None:
                    starts.append((city.level, t[2], t[3], t.z1))
            places = []
            for nm in CHECK_PLACES[city.name]:
                sp = npc_spots({nm}).get(nm)
                if sp:
                    places.append((nm, sp[1], sp[2], sp[3]))
        for lv, sx, sy, sz in starts[:2]:
            for name, x, y, z in places:
                opts = {"offroad": False}
                if z is not None:
                    opts["tz"] = z
                if sz is not None:
                    opts["z"] = sz
                ns.settings.gps.cityGrid = False
                own = R.Route(lv, sx, sy, x, y, lua.table(**opts))
                ns.settings.gps.cityGrid = True
                r = R.Route(lv, sx, sy, x, y, lua.table(**opts))
                ns.settings.gps.cityGrid = False
                grid = r.cityGrid is not None
                pts = [r.pts[i] for i in range(1, len(r.pts) + 1)]
                hz = r.zs if r.zs is not None else r.fz
                hs = [hz[i] if hz[i] is not False else None for i in range(1, len(hz) + 1)] if hz is not None else None
                kinds = [r.kinds[i] for i in range(1, len(r.kinds) + 1)]
                link = r.onLink
                end = next((h for h in reversed(hs or []) if h is not None), None)
                off_floor = abs(end - z) if end is not None and z is not None else 0.0
                # (only the grid's part judged: the land's roads up to the gate are the Router's own, as ever, and so is
                # its road on into the city up to where the grid's walk takes over (kind 0): Stormwind's gate road
                # crosses the moat's bridge, which the mesh lacks)
                inside = [i for i in range(len(kinds)) if CG.CityFor(lv, pts[2 * i], pts[2 * i + 1]) is not None]
                total, off, worst = walk_on_mesh(index, pts, hs, skip=lambda i: i not in inside or kinds[i] != 1
                                                 or (link is not None and link[i + 1])) if grid else (0, 0, 0)
                row = {"city": city.name, "from": [round(sx), round(sy)], "to": name, "grid": grid,
                       "yd": round(r.length, 1), "own_yd": round(own.length, 1), "pts": len(pts) // 2,
                       "own_pts": len(own.pts) // 2, "off_floor": round(off_floor, 1), "worst_off": round(worst, 1),
                       "ok": (not grid) or (worst < CHECK_OFF_YD and off_floor <= 5)}
                out.append(row)
                log(f"{' ' if row['ok'] else '!'} {city.name}: {row['from']} -> {name}: "
                    f"{'grid' if grid else 'own'} {row['yd']} yd (own {row['own_yd']}), ends {row['off_floor']} yd off "
                    f"its floor, longest off the mesh {row['worst_off']} yd")
    d = data_dir() / "debug" / "citygrid"
    d.mkdir(parents=True, exist_ok=True)
    (d / "gates.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for city in sorted({r["city"] for r in out}):
        rows = [r for r in out if r["city"] == city]
        g = [r for r in rows if r["grid"]]
        log(f"{city}: {len(g)} of {len(rows)} on the grid; yards {sum(r['yd'] for r in g):.0f} against "
            f"{sum(r['own_yd'] for r in g):.0f}; shorter {sum(r['yd'] < r['own_yd'] - 1 for r in g)}, longer "
            f"{sum(r['yd'] > r['own_yd'] + 1 for r in g)}; flagged {sum(not r['ok'] for r in rows)}")
    return out
