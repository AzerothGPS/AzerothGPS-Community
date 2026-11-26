"""The world grid's bake (worldgrid.py's tiles into a continent's grid and Data/WorldGrid<cont>.lua): the seams, the
open world's roads (road ground, road links), pruning, and the file's format (`encode_tiles`)."""

from __future__ import annotations

import hashlib
import math
import os
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

from . import citygrid as CGP
from . import worldmesh as WM
from .paths import ADDON_DIR, data_dir
from .worldgrid import (ALPHA, CELL_PER_TILE, DIRS, DROP_MAX, DROP_MIN, FLAG_ROAD, KIND_SWIM, MIN_PIECE, ROAD_PREF, SHORE_Z, SWIM_COST, Grid,
                        grid_dir, tile_origin)


# --- the shipped terrain heights (Data/Heights.lua, as Ground.lua's GD.Sample reads them) -----------------------------

class Heights:
    """Data/Heights.lua's ground heights, sampled as the addon's GD.Sample does (a ground surface's height in game)."""

    def __init__(self, cont: int):
        from . import heights as HT
        txt = (ADDON_DIR / "Data" / "Heights.lua").read_text(encoding="utf-8")
        self.n = int(re.search(r"ns\.Heights = \{ n = (\d+)", txt).group(1))
        a = txt.find(f"ns.Heights[{cont}] = {{")
        if a < 0:  # (none: Zephras Isle)
            self.raw, self._g, self.HT = {}, {}, HT
            return
        b = txt.index("\n}", a)
        self.raw = {}
        for k, v in re.findall(r'\[(\d+)\] = "((?:[^"\\]|\\.)*)"', txt[a:b]):
            self.raw[int(k)] = v.replace('\\"', '"').replace("\\\\", "\\")
        self._g = {}
        self.HT = HT

    def grid(self, key):
        g = self._g.get(key)
        if g is None and key in self.raw:
            d = self.HT.decode(self.raw[key], self.n + 1)
            g = np.array([[np.nan if v is None else v for v in row] for row in d], float)
            self._g[key] = g
        return g

    def sample(self, X, Y) -> np.ndarray:
        X, Y = np.asarray(X, float), np.asarray(Y, float)
        out = np.full(X.shape, np.nan)
        T, n = WM.T, self.n
        tx = np.floor(32 - Y / T).astype(int)
        ty = np.floor(32 - X / T).astype(int)
        for key in set(zip(tx.tolist(), ty.tolist())):
            g = self.grid(key[0] * 64 + key[1])
            if g is None:
                continue
            sel = (tx == key[0]) & (ty == key[1])
            q = T / n
            fi, fj = ((32 - key[1]) * T - X[sel]) / q, ((32 - key[0]) * T - Y[sel]) / q
            i, j = np.minimum(np.floor(fi).astype(int), n - 1), np.minimum(np.floor(fj).astype(int), n - 1)
            u, v = fi - i, fj - j
            out[sel] = (g[i, j] * (1 - u) * (1 - v) + g[i + 1, j] * u * (1 - v) + g[i, j + 1] * (1 - u) * v
                        + g[i + 1, j + 1] * u * v)
        return out


# --- roads (the open world's), pruning ----------------------------------------------------------------------------------

def land_roads(cont: int, log=print) -> list:
    """The continent's roads outside the capitals (the Router's graph under the game harness, drawn roads too), every
    citygrid.ROAD_STEP: [(edge id, source, oneway, [(x, y, z or None)], the Router's yards)]."""
    from .gameharness import start
    from .navcompare import NO_HEIGHT

    lua, ns = start()
    R = ns.Router
    R.NearestEdges(cont, 0, 0)
    g = R.DebugGraph(cont)
    hz = g.nz if g.nz is not None else g.z
    drops = g.drops
    roads = []
    for eid in g.e.keys():
        e = g.e[eid]
        src = int(e[4])
        if src in CGP.SKIP_SOURCES:
            continue
        pts = [(e[k], e[k + 1]) for k in range(5, len(e) + 1, 2) if e[k] is not None and e[k + 1] is not None]
        if len(pts) < 2 or any(R.CapitalAt(cont, p[0], p[1]) for p in pts):
            continue
        za = hz[e[1]] if hz is not None else None
        zb = hz[e[2]] if hz is not None else None
        if za is None or zb is None or za < NO_HEIGHT or zb < NO_HEIGHT or (za == 0 and zb == 0):
            za = zb = None
        length = sum(math.dist(pts[q], pts[q + 1]) for q in range(len(pts) - 1)) or 1.0
        samples, along = [], 0.0
        for q in range(len(pts) - 1):
            (ax, ay), (bx, by) = pts[q], pts[q + 1]
            d = math.dist(pts[q], pts[q + 1])
            m = max(1, int(d / CGP.ROAD_STEP))
            for s in range(m):
                t = s / m
                samples.append((ax + (bx - ax) * t, ay + (by - ay) * t,
                                None if za is None else za + (zb - za) * (along + d * t) / length))
            along += d
        samples.append((pts[-1][0], pts[-1][1], zb))
        oneway = bool(drops is not None and drops[eid]) or src == 4
        roads.append((int(eid), src, oneway, samples, float(e[3])))
    log(f"  cont {cont}: {len(roads)} roads outside the capitals")
    return roads


def capital_cells(g: Grid) -> np.ndarray:
    """Each surface in a capital's own cells (Router.CapitalAt: the city grid routes there), under the game harness."""
    from .gameharness import start
    lua, ns = start()
    out = np.zeros(g.n, bool)
    X = (g.gx + 0.5) * g.cell
    Y = (g.gy + 0.5) * g.cell
    for cap in CGP.CITIES:
        if cap.cont != g.cont or cap.level is not None:
            continue
        d = ns.CityGridData[cap.name] if ns.CityGridData else None
        if d is None:
            continue
        x0, y0 = float(d.x0), float(d.y0)
        x1, y1 = x0 + d.w * d.cell, y0 + d.h * d.cell
        for s in np.nonzero((X >= x0) & (X < x1) & (Y >= y0) & (Y < y1))[0]:
            if ns.Router.CapitalAt(g.cont, float(X[s]), float(Y[s])):
                out[s] = True
    return out


def _lift_stops(cont: int) -> list:
    """The lifts' cars' stops on `cont` (lifts.elevators: the CMaNGOS dump's elevators), [(x, y, z)]; none without it."""
    try:
        from . import lifts
        return [s[3:6] for s in lifts.elevators() if s[2] == cont]
    except Exception:
        return []


LIFT_STOP_YD = 25.0  # yards: a lift road's end takes the height of a car's stop this near it


def _lift_link(g: Grid, samples, yards: float, stops: list, out: list) -> bool:
    """A lift road (the Router's source 5: Thunder Bluff's, Freewind Post's, the Great Lift's): links both ways between
    the floors round its two ends' car stops (each at the stop's height, else the cell's highest floor at the top and its
    lowest at the foot), whatever their heights apart (the ride climbs it), costing the road's own yards (the wait and
    the ride). Every floor within LIFT_FLOOR_YD of a stop at its height gets its link to the other end's (the car's own
    resting floor is often a pocket of the shaft: the platform beside it is the floor players stand on). Kind KIND_LIFT:
    WorldGrid draws and says it as "Take the lift up/down". (Kooki3z 2026-11-22: "freewind post lift seems to be
    ignored": the road-link height check refused it.)"""
    # (the data's lifts are laid from the top to the foot, Router.LiftKind: the first end's the top, the last the foot)
    (ax, ay, _za), (bx, by, _zb) = samples[0], samples[-1]

    def floors(x, y, top):
        near = [s for s in stops if math.dist(s[:2], (x, y)) <= LIFT_STOP_YD]
        if near:
            st = max(near, key=lambda s: s[2]) if top else min(near, key=lambda s: s[2])
            cx, cy, z = st
        else:
            cx, cy, z = x, y, None
        out_ = []
        r = int(math.ceil(LIFT_FLOOR_YD / g.cell))
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                kx = int(math.floor(cx / g.cell)) + di - g.gxmin
                ky = int(math.floor(cy / g.cell)) + dj - g.gymin
                if not (0 <= kx < g.W and 0 <= ky < g.H):
                    continue
                f, cnt = int(g.first[kx * g.H + ky]), int(g.count[kx * g.H + ky])
                for s_ in range(f, f + max(cnt, 0)):
                    px, py = g.point(s_)
                    if math.dist((px, py), (cx, cy)) > LIFT_FLOOR_YD:
                        continue
                    out_.append(s_)
        if not out_:
            return []
        if z is None:
            z = max(float(g.z[s_]) for s_ in out_) if top else min(float(g.z[s_]) for s_ in out_)
        return sorted([s_ for s_ in out_ if abs(float(g.z[s_]) - z) <= 6.0],
                      key=lambda s_: math.dist(g.point(s_), (cx, cy)))[:LIFT_FLOORS]
    tops, foots = floors(ax, ay, True), floors(bx, by, False)
    if not tops or not foots:
        return False
    cost = max(yards, 1.0) * ROAD_PREF
    for a in tops:
        for b in foots:
            pa, pb = (*g.point(a), float(g.z[a])), (*g.point(b), float(g.z[b]))
            for x_, y_, pp in ((a, b, [pa, pb]), (b, a, [pb, pa])):
                out.append((x_, y_, cost, CGP.KIND_LIFT, pp))
                g.road_out[x_].append((x_, y_, cost, CGP.KIND_LIFT, pp))
    return True


LIFT_FLOOR_YD = 12.0  # yards round a lift's car stop whose floors at its height get the lift's links ...
LIFT_FLOORS = 4  # ... the nearest this many at each end


ROAD_FOLLOW_Z = 6.0  # yards: a road with no heights stays on the surface it was on when the next cell has one this near
ROAD_LINK_DZ = 3.0  # yards a road link's ends may differ in height past its slope's climb (ROAD_LINK_SLOPE a yard)
ROAD_LINK_SLOPE = 1.0  # (45 degrees: a road's own steepest; stairs 1 too)
ROAD_FLOORS = "carried"  # (road_floors: a road's floor carried from the road joined at its end; in the bake's stamp)
ROAD_LINK_SPAN_SLOPE = 0.5  # (a road link's climb may also be this much a yard between its surfaces' points: a ramp's
#  4 yd over 8, never a mesa's edge, 9.5 over 12 in Thousand Needles; in the stamp)


def _follow(g: Grid, samples, start=None) -> list:
    """The surface under each of a road's samples: at its height where it has one; with none, the surface nearest the one
    before it within ROAD_FOLLOW_Z (the first: `start`'s), else the ground's (g.at). By the ground alone a road along a
    mesa's edge (Thousand Needles) went from the canyon's floor to the mesa's top and back cell by cell, and its links
    joined them (Kooki3z 2026-11-22)."""
    on, prev = [], start
    for x, y, z in samples:
        s_ = None
        if z is None and prev is not None:
            s_ = g.at(x, y, float(g.z[prev]), ROAD_FOLLOW_Z)
        if s_ is None:
            s_ = g.at(x, y, z)
        on.append(s_)
        if s_ is not None:
            prev = s_
    return on


def _cell_count(g: Grid, x: float, y: float) -> int:
    kx, ky = int(math.floor(x / g.cell)) - g.gxmin, int(math.floor(y / g.cell)) - g.gymin
    if not (0 <= kx < g.W and 0 <= ky < g.H):
        return 0
    return max(0, int(g.count[kx * g.H + ky]))


def road_floors(g: Grid, roads) -> list:
    """Each road's surfaces (`_follow`'s, a list per road; None for a lift), the floor carried from road to road where
    they meet: a road with no heights starts on the floor the road joined at its end was found on, not on the ground's
    surface. Seeded where a road's end has a height or its cell one surface only, then along the roads from there;
    roads none of those reach start on the ground's as before. (Dun Algaz, 2026-11-22: north of the tunnel the gorge
    runs under an overhang, the terrain's height there is the mountain top's 100 yd over the road, and each short road
    piece started up there: the gorge floor wasn't road ground and its step under the gate got no road link, so the
    grid had no way from Loch Modan into the Wetlands.)"""
    from collections import deque

    def key(p):
        return (round(p[0], 1), round(p[1], 1))
    floors = [None] * len(roads)
    ends = defaultdict(list)  # node -> [(road, at its first sample)]
    for i, (_eid, src, _oneway, samples, _own) in enumerate(roads):
        if src == 5 or len(samples) < 2:
            continue
        ends[key(samples[0])].append((i, True))
        ends[key(samples[-1])].append((i, False))
    node_s = {}
    queue = deque()

    def seed(k, s_):
        if s_ is not None and k not in node_s:
            node_s[k] = s_
            queue.append(k)
    # (a dead end's seed waits until the roads through are done, then they go one at a time, the longest road's first:
    # the road extraction's short stubs poke into a gorge's side, where the cell may have only the mountain top over
    # it; Dun Algaz's three did, and the first carried the top back onto the gorge's road)
    later = []
    for k, lst in ends.items():
        through = sum(1 for i, first in lst if key(roads[i][3][-1 if first else 0]) != k) >= 2
        for i, first in lst:
            p = roads[i][3][0 if first else -1]
            s_ = None
            if p[2] is not None:
                s_ = g.at(p[0], p[1], p[2])
            elif _cell_count(g, p[0], p[1]) == 1:
                s_ = g.at(p[0], p[1], None)
            if s_ is not None:
                if through:
                    seed(k, s_)
                else:
                    later.append((-float(roads[i][4]), len(later), k, s_))
                break
    later.sort()  # (the longest dead-end road's first, one at a time: a long road's end over a short stub's)
    todo = sorted(i for i in range(len(roads)) if roads[i][1] != 5 and len(roads[i][3]) >= 2)
    nxt = 0
    while True:
        if not queue and later:
            _yd, _n, k, s_ = later.pop(0)
            seed(k, s_)
            continue
        while queue:
            k = queue.popleft()
            for i, first in ends[k]:
                if floors[i] is not None:
                    continue
                samples = roads[i][3]
                if first:
                    on = _follow(g, samples, node_s[k])
                else:
                    on = list(reversed(_follow(g, list(reversed(samples)), node_s[k])))
                floors[i] = on
                far = key(samples[-1] if first else samples[0])
                seed(far, on[-1] if first else on[0])
        # (a road no seed reaches: from the ground's surface, as before; its ends seed on from there)
        while nxt < len(todo) and floors[todo[nxt]] is not None:
            nxt += 1
        if nxt >= len(todo):
            break
        i = todo[nxt]
        samples = roads[i][3]
        floors[i] = _follow(g, samples)
        seed(key(samples[0]), floors[i][0])
        seed(key(samples[-1]), floors[i][-1])
    for i, (_eid, src, _oneway, samples, _own) in enumerate(roads):
        if floors[i] is None and src != 5:
            floors[i] = _follow(g, samples)
    return floors


def mark_roads(g: Grid, roads, log=print) -> int:
    """Road ground (FLAG_ROAD) under the roads' samples (on the floors `road_floors` carries along them), and road links
    where a road crosses what the grid has no way over within citygrid.ROAD_DETOUR (citygrid.road_links' rule; a drop's
    one way). Returns the surfaces marked."""
    g.road_out = defaultdict(list)
    marked = 0
    out = []

    def nbr(s):
        return {int(t) for t in g.links[s] if t >= 0} | {r[1] for r in g.road_out.get(s, ())}
    refused = 0
    lifts_ = _lift_stops(g.cont)
    floors = road_floors(g, roads)
    shafts = lift_shafts(g.cont)
    g.lift_yards = {}
    for ri, (_eid, src, oneway, samples, _own) in enumerate(roads):
        if src == 5:  # (a lift: its own links, each car's shaft from its platforms: lift_links, after the walls)
            near = [s_ for s_ in shafts if min(math.dist(samples[0][:2], (s_["x"], s_["y"])),
                                                math.dist(samples[-1][:2], (s_["x"], s_["y"]))) <= LIFT_ROAD_YD]
            if near:
                for s_ in near:
                    g.lift_yards[s_["lift"]] = _own
                continue
            n_ = _lift_link(g, samples, _own, lifts_, out)
            if n_:
                continue
        on = floors[ri] if floors[ri] is not None else _follow(g, samples)
        for s in on:
            if s is not None and not g.flags[s] & FLAG_ROAD:
                g.flags[s] |= FLAG_ROAD
                marked += 1
        last = None
        for idx, node in enumerate(on):
            if node is None:
                continue
            if last is not None and on[last] != node and (idx - last > 1 or node not in nbr(on[last])):
                a = on[last]
                stretch = samples[last:idx + 1]
                yd = sum(math.dist(stretch[q][:2], stretch[q + 1][:2]) for q in range(len(stretch) - 1))
                limit = yd * CGP.ROAD_DETOUR + CGP.ROAD_DETOUR_YD
                if g.dist(a, node, limit) > limit:
                    pts = [stretch[0]]
                    along = 0.0
                    for q in range(1, len(stretch) - 1):
                        along += math.dist(stretch[q - 1][:2], stretch[q][:2])
                        if along >= CGP.ROAD_LINK_PTS_YD:
                            pts.append(stretch[q])
                            along = 0.0
                    pts.append(stretch[-1])
                    za_, zb_ = float(g.z[a]), float(g.z[node])
                    kind = CGP.KIND_DROP if src == 4 else CGP.KIND_STAIRS if src == 6 else CGP.KIND_WALK
                    # (a link climbs no more than its road can over its yards: a walk's or stairs' slope, a drop down
                    # within worldgrid.DROP_MAX one way; never a floor tens of yards over or under the road's)
                    dz = zb_ - za_
                    # (over the yards between the two surfaces' own points, where their heights are, when that's more
                    # than the road's stretch: a road crosses from one cell's surface to the next in a yard, and a
                    # ramp in the tunnel north of Dun Algaz to the Wetlands' east (86.5 to 90.6 yd, its points 8 yd
                    # apart) was refused as a 4 yd climb in one; ROAD_LINK_SPAN_SLOPE)
                    span = math.dist(g.point(a), g.point(node))
                    if kind == CGP.KIND_DROP:
                        ok_ = -DROP_MAX - ROAD_LINK_DZ <= dz <= ROAD_LINK_DZ
                    else:
                        ok_ = abs(dz) <= ROAD_LINK_DZ + max(yd * (1.0 if kind == CGP.KIND_STAIRS else ROAD_LINK_SLOPE),
                                                            span * ROAD_LINK_SPAN_SLOPE)
                    if not ok_:
                        refused += 1
                        last = idx
                        continue
                    pts = [(p[0], p[1], p[2] if p[2] is not None else za_ + (zb_ - za_) * q / max(1, len(pts) - 1))
                           for q, p in enumerate(pts)]
                    cost = max(yd, 1.0) * ROAD_PREF
                    for x_, y_, pp in ((a, node, pts), (node, a, list(reversed(pts)))):
                        out.append((x_, y_, cost, kind, pp))
                        g.road_out[x_].append((x_, y_, cost, kind, pp))
                        if oneway:
                            break
            last = idx
    g.road = out
    g.links_refused = refused
    log(f"  cont {g.cont}: {marked} surfaces of road ground, {len(out)} road links ({refused} refused: their ends' heights "
        f"apart more than the road climbs)")
    return marked


# --- the lifts' cars, each its own shaft (Kooki3z 2026-11-22 at the Great Lift: "there are 2, ramp to them is in red") ----

from .lifts import LIFT_PLATFORM_YD, LIFT_PLATFORM_Z, LIFT_ROAD_YD  # noqa: E402 (the lifts' own, shared with the city grid)

LIFT_ON_MESH_Z = 1.5  # yards: a platform's floor is a surface whose cell the ground's piece crosses this near its height


def lift_shafts(cont: int) -> list:
    """The continent's lifts' cars as shafts (lifts.shafts: the CMaNGOS dump's elevators; none without it: a bake
    checks it's there first, need_bake_data)."""
    try:
        from . import lifts
        return lifts.shafts(lifts.elevators(), cont)
    except Exception:
        return []


def _ground_polys(cont: int, x: float, y: float, z: float):
    """The mesh's polys round a lift's stop (x, y, z) of the ground's pieces (lifts.ground_piece): [verts], or None
    without the mesh."""
    from .lifts import ground_piece
    try:
        got = WM.load_tile(cont, int(math.floor(32 - y / WM.T)), int(math.floor(32 - x / WM.T)))
    except Exception:
        got = None
    if got is None:
        return None
    polys, nbs = got
    return [polys[i][0] for i in sorted(ground_piece([p[0] for p in polys], nbs, x, y, z, lambda i: polys[i][2]))]


def platform_floors(g: Grid, cont: int, x: float, y: float, z: float) -> list:
    """The surfaces players board a lift's car from at its stop (x, y, z): within LIFT_PLATFORM_YD of the shaft and
    LIFT_PLATFORM_Z of the stop's height, on the mesh's floor that reaches the ground round it (_ground_polys: a ramp's
    platform, a walkway's end; never a pocket of the shaft, the structure between two cars or the ground under a raised
    platform), nearest the shaft first."""
    from . import navmesh as NM
    ground = _ground_polys(cont, x, y, z)
    r = int(math.ceil(LIFT_PLATFORM_YD / g.cell))
    out = []
    for di in range(-r, r + 1):
        for dj in range(-r, r + 1):
            kx = int(math.floor(x / g.cell)) + di - g.gxmin
            ky = int(math.floor(y / g.cell)) + dj - g.gymin
            if not (0 <= kx < g.W and 0 <= ky < g.H):
                continue
            f, cnt = int(g.first[kx * g.H + ky]), int(g.count[kx * g.H + ky])
            for s in range(f, f + max(cnt, 0)):
                px, py = g.point(s)
                sz = float(g.z[s])
                if math.dist((px, py), (x, y)) > LIFT_PLATFORM_YD or abs(sz - z) > LIFT_PLATFORM_Z or g.kind[s] == KIND_SWIM:
                    continue
                cx, cy = (g.gx[s] + 0.5) * g.cell, (g.gy[s] + 0.5) * g.cell
                if ground is not None and not any(
                        NM._dist2_poly(vs, cx, cy) <= (g.cell / 2) ** 2 and abs(NM._height_on(vs, px, py) - sz) <= LIFT_ON_MESH_Z
                        for vs in ground):
                    continue
                out.append(s)
    return sorted(out, key=lambda s: math.dist(g.point(s), (x, y)))[:LIFT_FLOORS]


def lift_links(g: Grid, log=print) -> int:
    """Each lift car's ride (KIND_LIFT) both ways between its shaft's platforms at its two stops (platform_floors),
    drawn from the platform to the shaft, up or down it, and off onto the other platform; costing the lift road's own
    yards (the wait and the ride), else lifts.LIFT_SECONDS'. Returns the links."""
    from . import lifts
    n = 0
    for sh in lift_shafts(g.cont):
        x, y = sh["x"], sh["y"]
        lo, hi = platform_floors(g, g.cont, x, y, sh["lo"]), platform_floors(g, g.cont, x, y, sh["hi"])
        if not lo or not hi:
            log(f"  cont {g.cont}: a lift car at ({x:.0f}, {y:.0f}) has no platform at {'its foot' if not lo else 'its top'}")
            continue
        yards = getattr(g, "lift_yards", {}).get(sh["lift"])
        cost = max(yards or lifts.LIFT_SECONDS * 7, 1.0) * ROAD_PREF
        for a in lo:
            for b in hi:
                pa, pb = (*g.point(a), float(g.z[a])), (*g.point(b), float(g.z[b]))
                for s0, s1, pp in ((a, b, [pa, (x, y, pa[2]), (x, y, pb[2]), pb]),
                                   (b, a, [pb, (x, y, pb[2]), (x, y, pa[2]), pa])):
                    r_ = (s0, s1, cost, CGP.KIND_LIFT, pp)
                    g.road.append(r_)
                    g.road_out[s0].append(r_)
                    n += 1
    log(f"  cont {g.cont}: {n} lift links")
    return n


# --- the players' recorded walks and drawn roads with heights (Kooki3z 2026-11-22: "I already recorded pathing for
# darkcloud pinnacle, use that"): drawn and recorded roads are truth ----------------------------------------------------

REC_DROP_DZ = 1.5  # yards: a recorded step falling this much more than its yards (a 45-degree slope) is a drop: one way
REC_FOLLOW_Z = 3.0  # yards: a recorded walk's point with no height stays on the surface nearest the one before this near
# (yards from a lift car's shaft: the walk's own step up or down there is the car's ride, a lift link (Kooki3z rode
# Freewind Post's east car with Record on: its 130 yd climb in a step was a walk link up and a drop down, taken over the
# car's own ride with a zigzag over the foot's road ground to it, 2026-11-23)
REC_RIDE_YD = 12.0


def recorded_walks(cont: int) -> list:
    """The continent's roads walked or drawn by players with heights, as the data has them (overrides/roads_<cont>.geojson:
    recorded walks' pieces, `recorded`, on the ground flat or on a floor with `zs`; drawn roads with `zs`, ns.FloorTracks):
    [(time, part, [(x, y, z or None)], stairs)] by time and part. A piece with no heights was put on the ground by the
    import; its heights are the grid's (recorded_heights)."""
    import json
    from .paths import RESOURCES
    p = RESOURCES / "overrides" / f"roads_{cont}.geojson"
    if not p.exists():
        return []
    out = []
    for f in json.loads(p.read_text(encoding="utf-8")).get("features", []):
        pr, geo = f.get("properties") or {}, f.get("geometry") or {}
        if pr.get("op", "add") != "add" or geo.get("type") != "LineString":
            continue
        zs = pr.get("zs")
        if not (pr.get("recorded") or zs):
            continue
        pts = geo.get("coordinates") or []
        if len(pts) < 2:
            continue
        if zs and len(zs) == len(pts):
            pts = [(p_[0], p_[1], float(z)) for p_, z in zip(pts, zs)]
        else:
            pts = [(p_[0], p_[1], None) for p_ in pts]
        out.append((pr.get("time") or 0, pr.get("part") or 0, pts, bool(pr.get("stair"))))
    return sorted(out, key=lambda w: (w[0], w[1]))


def _surfaces(g: Grid, x: float, y: float):
    kx, ky = int(math.floor(x / g.cell)) - g.gxmin, int(math.floor(y / g.cell)) - g.gymin
    if not (0 <= kx < g.W and 0 <= ky < g.H):
        return range(0)
    f, cnt = int(g.first[kx * g.H + ky]), int(g.count[kx * g.H + ky])
    return range(f, f + max(cnt, 0))


def recorded_heights(g: Grid, pts: list, z0: float | None) -> list:
    """A piece's points every citygrid.ROAD_STEP with heights [(x, y, z, jump)]: its own (`zs`), else each on the grid's
    surface nearest the height before (within REC_FOLLOW_Z, and a yard more for each yard since the last: a slope the
    grid lacks; none that near: the height before, the walk over what the grid lacks: a rope bridge's deck between two
    needles; once one is near again, the heights between it and the last straight between them: no step up a cliff where
    the deck rose), the first on z0 (the piece before's end) or the ground's."""
    out = []
    prev = z0
    lost = 0.0  # (yards since the last surface near the height: the next may be as far off as a slope's climb more)
    gap = None  # (the first sample of the run with no surface near, since the last with one)
    for q in range(len(pts) - 1):
        (ax, ay, az), (bx, by, bz) = pts[q], pts[q + 1]
        d = math.dist((ax, ay), (bx, by))
        m = max(1, int(d / CGP.ROAD_STEP))
        measured = az is not None and bz is not None
        # (the walk's own step between two of its points: a drop down (-1) or up (1) where it falls or climbs
        # REC_DROP_DZ more than its yards; the grid's guessed heights are never one)
        jump = 0
        if measured and abs(bz - az) > REC_DROP_DZ + d:
            jump = 1 if bz > az else -1
        for k in range(m + (1 if q == len(pts) - 2 else 0)):
            t = k / m
            x, y = ax + (bx - ax) * t, ay + (by - ay) * t
            if measured:
                z = az + (bz - az) * t
                gap, lost = None, 0.0
            else:
                z = None
                ss = list(_surfaces(g, x, y))
                if prev is None and ss:
                    s_ = g.at(x, y, None)
                    z = float(g.z[s_]) if s_ is not None else None
                elif ss:
                    best = min(ss, key=lambda s_: abs(float(g.z[s_]) - prev))
                    if abs(float(g.z[best]) - prev) <= REC_FOLLOW_Z + lost:
                        z = float(g.z[best])
                if z is None:
                    z = prev if prev is not None else (g.ground_z(x, y) if g._ground is not None else 0.0)
                    lost += CGP.ROAD_STEP
                    if gap is None:
                        gap = len(out)
                else:
                    if gap is not None and gap > 0:
                        z0_, n_ = out[gap - 1][2], len(out) - gap + 1
                        for j in range(gap, len(out)):
                            o = out[j]
                            out[j] = (o[0], o[1], z0_ + (z - z0_) * (j - gap + 1) / n_, o[3])
                    lost, gap = 0.0, None
            out.append((x, y, z, jump))
            prev = z
    return out


def mark_recorded(g: Grid, walks: list, log=print) -> int:
    """The recorded walks and drawn roads with heights (recorded_walks) as the grid's truth: every surface they walk over
    is road ground, and where the grid has no link between two surfaces one after another on the walk (a narrow ledge or
    a rope bridge the 8.33 yd cells miss, a step the mesh doesn't join), the walk's stretch is a link (kind walk, or
    stairs), at its own heights, its yards at ROAD_PREF: never refused for the heights its ends differ by (each step was
    walked). A stretch with a drop in it (a step of the walk's own heights falling REC_DROP_DZ more than its yards) is one
    way, down; one with such a step up, walked up, is a drop the other way (a piece the import put on the ground has its
    heights from the grid: never a drop). Such a step within REC_RIDE_YD of a lift car's shaft is the car's ride: a lift
    link both ways between where the walk got on and off (lift_links' cost and drawing); one falling more than
    worldgrid.DROP_MAX elsewhere is no link. Never cut by the shipped walls (walked). Returns the links."""
    ends = {}  # (a piece's last point, rounded: its height, for the next piece's first)
    n_links, marked, rides = 0, 0, 0
    from . import lifts
    shafts = lift_shafts(g.cont)

    def ride(stretch):
        """The shaft a step of the walk's own climbing or falling past a slope is by (REC_RIDE_YD): the walk rode that
        lift's car; else True for a step falling more than worldgrid.DROP_MAX (a fall to its death: no link), else
        None."""
        for q in range(len(stretch) - 1):
            if not stretch[q][3]:
                continue
            for sh in shafts:
                if math.dist(stretch[q][:2], (sh["x"], sh["y"])) <= REC_RIDE_YD:
                    return sh
            if abs(stretch[q + 1][2] - stretch[q][2]) > DROP_MAX:
                return True
        return None

    def nbr(s):
        return {int(t) for t in g.links[s] if t >= 0} | {r[1] for r in g.road_out.get(s, ())}
    for _time, _part, pts, stairs in walks:
        z0 = pts[0][2] if pts[0][2] is not None else ends.get((round(pts[0][0]), round(pts[0][1])))
        samples = recorded_heights(g, pts, z0)
        if not samples:
            continue
        ends[(round(pts[-1][0]), round(pts[-1][1]))] = samples[-1][2]
        on = [g.at(x, y, z, CGP.ROAD_ON_Z) for x, y, z, _m in samples]
        for s in on:
            if s is not None and not g.flags[s] & FLAG_ROAD:
                g.flags[s] |= FLAG_ROAD
                marked += 1
        last = None
        for idx, node in enumerate(on):
            if node is None:
                continue
            if last is not None and on[last] != node:
                a = on[last]
                fwd, back = node not in nbr(a), a not in nbr(node)
                if fwd or back:
                    stretch = samples[last:idx + 1]
                    sh = ride(stretch)
                    if sh is not None:
                        # (the car's ride, kind lift, both ways between where the walk got on and off: its platforms
                        # may lie off the stop's height (Freewind Post's east car is boarded from the ground 5 yd under
                        # its stop's, out of lift_links' platforms), as lift_links draws it)
                        if sh is not True:
                            yards = getattr(g, "lift_yards", {}).get(sh["lift"])
                            cost = max(yards or lifts.LIFT_SECONDS * 7, 1.0) * ROAD_PREF
                            pa, pb = (*g.point(a), float(g.z[a])), (*g.point(node), float(g.z[node]))
                            x_, y_ = sh["x"], sh["y"]
                            for s0, s1, pp in ((a, node, [pa, (x_, y_, pa[2]), (x_, y_, pb[2]), pb]),
                                               (node, a, [pb, (x_, y_, pb[2]), (x_, y_, pa[2]), pa])):
                                if s1 not in nbr(s0):
                                    r_ = (s0, s1, cost, CGP.KIND_LIFT, pp)
                                    g.road.append(r_)
                                    g.road_out[s0].append(r_)
                            rides += 1
                        last = idx
                        continue
                    yd, up, down = 0.0, False, False
                    for q in range(len(stretch) - 1):
                        d = math.dist(stretch[q][:2], stretch[q + 1][:2])
                        dz = stretch[q + 1][2] - stretch[q][2]
                        yd += math.sqrt(d * d + dz * dz)
                        down |= stretch[q][3] < 0  # (the walk's own step down: recorded_heights)
                        up |= stretch[q][3] > 0
                    pts_ = [stretch[0]]
                    along = 0.0
                    for q in range(1, len(stretch) - 1):
                        along += math.dist(stretch[q - 1][:2], stretch[q][:2])
                        if along >= CGP.ROAD_LINK_PTS_YD or abs(stretch[q][2] - pts_[-1][2]) >= 1.0:
                            pts_.append(stretch[q])
                            along = 0.0
                    pts_.append(stretch[-1])
                    pts_ = [p[:3] for p in pts_]
                    cost = max(yd, 1.0) * ROAD_PREF
                    walk = CGP.KIND_STAIRS if stairs else CGP.KIND_WALK
                    if fwd:
                        r_ = (a, node, cost, CGP.KIND_DROP if down else walk, pts_)
                        g.road.append(r_)
                        g.road_out[a].append(r_)
                        n_links += 1
                    if back and not down:
                        r_ = (node, a, cost, CGP.KIND_DROP if up else walk, list(reversed(pts_)))
                        g.road.append(r_)
                        g.road_out[node].append(r_)
                        n_links += 1
            last = idx
    log(f"  cont {g.cont}: {len(walks)} recorded or drawn pieces with heights: {marked} more surfaces of road ground, "
        f"{n_links} recorded links, {rides} lift rides")
    return n_links


# --- the stops' floors (NPCs, dungeons' doors) joined along the mesh's own polys (bake7, 2026-11-23) -----------------
# (the 8.33 yd cells miss a building's stairs, a walkway's step, a door: the floors NPCs stand on in towns were pieces
# apart, no way to them on the grid: Booty Bay's tailor up his walkway, Brill's bat master up the tower, Nijel's Point's
# upper floor, Uldaman's and Gnomeregan's front doors; bake6's 10,000-route test lost 37 short trips in towns so)

STOP_ON_Z = 4.0  # yards: a stop's floor is the grid's surface this near its height
STOP_MESH_YD = 3.0  # yards: the mesh's polys this near a stop are its floor's
STOP_SAFE_DROP = 14.0  # yards: a drop the game's search takes for every player (Nav.FALL_FREE: in combat too)
STOP_THIN_YD = 0.75  # yards a mesh way's points may be thinned off its line (about the agent's room off a wall)
STOP_DETOUR, STOP_DETOUR_YD = 2.0, 20.0  # (a way round a stop: the grid's this many times the mesh's + yards, or longer)
STOP_NEAR_YD = 80.0  # yards of the mesh's way round a stop looked at for a way shorter than the grid's ...
STOP_SHORTCUTS = 3  # ... and at most this many of them a stop
STOP_STEPS = 8  # pieces a stop's floor is joined through at most on its way to the reached ground
STOP_PATH_YD = 300.0  # yards: the mesh's way from a stop's floor to the reached ground, this long at most (a tower's ramp)
STOP_REACH_Z = 2.0  # yards: a poly of the way is on a reached surface of its cell this near its height


def stop_spots(cont: int) -> list:
    """The spots routes stop at on `cont` with their heights, outside the capitals: every shipped NPC's spawn
    (Data/Npcs.lua) and every dungeon's and raid's door (ns.Transports' portals' outside ends): [(x, y, z, name)]."""
    from .gameharness import start
    from .undergroundsweep import shipped_npcs
    lua, ns = start()
    R = ns.Router
    out = []
    for npc in shipped_npcs():
        for lvl, x, y, z in npc["spawns"]:
            if lvl == cont and not R.CapitalAt(cont, x, y):
                out.append((x, y, z, npc["name"]))
    rows = ns.Transports
    for i in range(1, len(rows) + 1):
        t = rows[i]
        if t[8] == "portal" and int(t[1]) == cont and t.z1 is not None and not R.CapitalAt(cont, t[2], t[3]):
            out.append((float(t[2]), float(t[3]), float(t.z1), str(t[10])))
    return out


CAVE_UNDER_YD = 8.0  # yards: a cave road's node with no height of its own is on the floors this far under the ground
CAVE_NODE_EVERY = 4  # (every this many of a cave's own road nodes inside it a spot: one joined, its piece's others are)


def cave_spots(cont: int) -> list:
    """The caves' and mines' spots (Data/Caves.lua) for stop_links: each way in (its patch of ground at an opening) and
    every CAVE_NODE_EVERY'th node of the cave's own roads inside it, [(x, y, z or None, name, under)]: a node's height
    when the data has one (a layered cave's `nz`), else None, every floor of its cell (`under`: only those CAVE_UNDER_YD
    or more under the ground, a node inside; a way in's every one). The cave sweep's no ways (test_cave_sweep.py,
    KNOWN_NO_WAY): a mouth on a ledge the grid's links leave only by a drop down, its slope up narrower than its
    cells."""
    from .gameharness import start
    lua, ns = start()
    rows = lua.eval(r"""
    function(cont)
      local WG = AGPS_NS.WorldGrid
      local out = {}
      local function add(x, y, z, name, under) out[#out + 1] = { x, y, z or false, name, under } end
      for _, cv in ipairs(AGPS_NS.Caves[cont] or {}) do
        local ways = cv[5] or {}
        for k = 1, #ways - 1, 2 do add(ways[k], ways[k + 1], nil, cv[1] ~= "" and cv[1] or cv[2], false) end
      end
      local names = {}
      for _, cv in ipairs(AGPS_NS.Caves[cont] or {}) do names[cv[2]] = cv[1] ~= "" and cv[1] or cv[2] end
      local seen = {}
      for _, ov in ipairs(AGPS_NS.RoadOverlays[cont] or {}) do
        if ov.cave then
          local n, nz = ov.n, ov.nz
          for i = 1, #n / 2 do
            local x, y = n[2 * i - 1], n[2 * i]
            local cave = WG.CaveAt(cont, x, y)
            if cave then
              seen[cave] = (seen[cave] or 0) + 1
              if seen[cave] % AGPS_EVERY == 1 or AGPS_EVERY == 1 then
                add(x, y, nz and nz[i] ~= 0 and nz[i] or nil, names[cave] or cave, true)
              end
            end
          end
        end
      end
      return out
    end""")
    lua.globals().AGPS_EVERY = CAVE_NODE_EVERY
    ns.WorldGrid.Set(True)
    t = rows(cont)
    out = []
    for i in range(1, len(t) + 1):
        r = t[i]
        out.append((float(r[1]), float(r[2]), float(r[3]) if r[3] is not False else None, str(r[4]), bool(r[5])))
    return out


class _Meshes:
    """The world meshes' tiles, loaded as asked (worldmesh.load_tile): each's polys, neighbors and polys' middles."""

    def __init__(self, cont: int):
        self.cont, self.tiles, self.boxes = cont, {}, {}

    def get(self, key):
        if key not in self.tiles:
            try:
                got = WM.load_tile(self.cont, *key)
            except Exception:
                got = None
            self.tiles[key] = got and (*got, np.array([np.mean(np.asarray(p[0], float), axis=0) for p in got[0]]))
            self.boxes[key] = got and np.array([(*np.asarray(p[0], float)[:, :2].min(axis=0),
                                                 *np.asarray(p[0], float)[:, :2].max(axis=0)) for p in got[0]])
        return self.tiles[key]

    @staticmethod
    def key(x, y):
        return (int(math.floor(32 - y / WM.T)), int(math.floor(32 - x / WM.T)))

    def polys_at(self, x, y, z, dz, r=0.5):
        """[(tile, poly)] of the walkable polys within r yards of (x, y) and dz of z there, of the tile it's in."""
        from . import navmesh as NM
        k = self.key(x, y)
        t = self.get(k)
        if not t:
            return []
        polys = t[0]
        # (by each poly's box: a big floor's middle can be far off the spot, an arena's ring, a courtyard; by the middles
        # within 40 yd, bake7's, the Battle Ring's floor in Gurubashi Arena was never found)
        b = self.boxes[k]
        near = np.nonzero((b[:, 0] - r <= x) & (b[:, 2] + r >= x) & (b[:, 1] - r <= y) & (b[:, 3] + r >= y))[0]
        return [(k, int(i)) for i in near if polys[i][2]
                and (NM._in_poly(polys[i][0], x, y) or NM._dist2_poly(polys[i][0], x, y) <= r * r)
                and abs(NM._height_on(polys[i][0], x, y) - z) <= dz]


def _mesh_way(M: _Meshes, x, y, z, done, max_yd: float):
    """The mesh's way (Dijkstra over its polys, from the walkable poly under (x, y) at z) to the nearest poly `done`
    says yes to: [(x, y, z)] (the polys' middles and the edges' middles between them), or None. With `done` None, every
    poly within max_yd: ({poly: (yards, middle)}, the way to one), or None. A map tile's mesh is built over its box and a
    ring round it: a poly whose middle is in the ring goes on as the next tile's poly there."""
    import heapq

    def mid(n):
        return tuple(float(v) for v in M.get(n[0])[2][n[1]])

    def portal(n, m):
        if n[0] != m[0]:
            return None
        polys = M.get(n[0])[0]
        vs, ns_ = polys[n[1]][0], polys[n[1]][1]
        k = len(vs)
        es = [e for e in range(k) if ns_[e] == m[1]] or [e for e in range(k) if ns_[e] == -2]
        if not es:
            return None
        mj = mid(m)
        e = min(es, key=lambda e: math.dist(((vs[e][0] + vs[(e + 1) % k][0]) / 2,
                                             (vs[e][1] + vs[(e + 1) % k][1]) / 2), mj[:2]))
        a, b = vs[e], vs[(e + 1) % k]
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)

    def nexts(n):
        polys, nbs, _m = M.get(n[0])
        for j in nbs[n[1]]:
            if polys[j][2]:
                yield (n[0], j)
        mx, my, mz = mid(n)
        if M.key(mx, my) != n[0]:  # (in the ring: the same ground in the next tile's mesh)
            yield from M.polys_at(mx, my, mz, 1.0)
    # (an NPC stands by a wall or a counter, where the mesh is eroded by the agent's radius: the polys near)
    start = M.polys_at(x, y, z, STOP_ON_Z, STOP_MESH_YD)
    if not start:
        return None
    dist, prev, h = {}, {}, []

    def way_to(n):
        way = [mid(n)]
        while n in prev:
            p_ = prev[n]
            pt = portal(p_, n)
            if pt:
                way.append(pt)
            if math.dist(mid(p_), way[-1]) > 0.5:
                way.append(mid(p_))
            n = p_
        way.append((x, y, z))
        return list(reversed(way))
    for n in start:
        dist[n] = 0.0
        heapq.heappush(h, (0.0, n))
    while h:
        d, n = heapq.heappop(h)
        if d > dist.get(n, math.inf):
            continue
        m_ = mid(n)
        if done is not None and done(n, m_):
            return way_to(n)
        for q in nexts(n):
            nd = d + math.dist(m_, mid(q))
            if nd <= max_yd and nd < dist.get(q, math.inf):
                dist[q], prev[q] = nd, n
                heapq.heappush(h, (nd, q))
    if done is None:  # (the whole tree: each poly's yards and middle, and the way to it)
        return {n: (d, mid(n)) for n, d in dist.items()}, way_to
    return None


def _thin(pts: list, xy: float = STOP_THIN_YD, z: float = 1.0) -> list:
    """A way's points thinned (Douglas-Peucker): the ones off the line between their neighbors kept, by `xy` yards
    across or `z` in height."""
    if len(pts) <= 2:
        return list(pts)
    (ax, ay, az), (bx, by, bz) = pts[0][:3], pts[-1][:3]
    L = math.dist((ax, ay), (bx, by))
    worst, wi = 0.0, 0
    for i in range(1, len(pts) - 1):
        px, py, pz = pts[i][:3]
        t = 0.0 if L < 1e-6 else max(0.0, min(1.0, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / (L * L)))
        off = max(math.dist((px, py), (ax + (bx - ax) * t, ay + (by - ay) * t)) / xy, abs(pz - (az + (bz - az) * t)) / z)
        if off > worst:
            worst, wi = off, i
    if worst <= 1.0:
        return [pts[0], pts[-1]]
    return _thin(pts[:wi + 1], xy, z)[:-1] + _thin(pts[wi:], xy, z)


def walled_boxes(cont: int) -> list:
    """WorldGrid.lua's WG.WALLED boxes on `cont` (buildings whose walls the meshes lack): [(x0, y0, x1, y1)]."""
    from .gameharness import start
    lua, ns = start()
    W = ns.WorldGrid.WALLED or {}
    out = []
    for i in range(1, len(W) + 1):
        b = W[i]
        if int(b[1]) == cont:
            out.append((float(b[2]), float(b[3]), float(b[4]), float(b[5])))
    return out


def stop_links(g: Grid, walls: list, log=print) -> int:
    """Each stop's floor (stop_spots) the grid's links and road links leave apart from the ground players reach (not
    in a piece of REACH_PIECE surfaces joined both ways: a walkway's floor joined to the ground under it only by drops
    down is no way up) joined to it along the mesh's own polys (_mesh_way: its stairs, a walkway's step, a door the
    8.33 yd cells miss): a link each way (kind walk) between the stop's surface and the first surface of a bigger piece
    the way comes onto (a hall onto the next, up to STOP_STEPS of them, till the reached ground), at the way's heights,
    its yards its cost (Recast walks it: never refused for its yards). Never across a shipped wall, nor in a WG.WALLED
    building (walled_boxes). Returns the links;
    `g.stop_apart` the stops left apart."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    # (the ways the game's search takes whatever the player: no drop past STOP_SAFE_DROP, a grid link down a ledge (no
    # link back, as WG.Search's Drop) or a road link down. In Ironforge the halls were one piece by drops of 20-40 yd
    # back the other way, and the search from Pithwick's floor ended in 75 surfaces)
    src = np.repeat(np.arange(g.n), 8)
    dst = g.links.ravel()
    ok = dst >= 0
    opp = [DIRS.index((-dx, -dy)) for dx, dy in DIRS]
    d_ = np.tile(np.arange(8), g.n)
    t_ = np.maximum(dst, 0)
    back = g.links[t_, np.array(opp)[d_]] == src
    ok &= back | (g.z[t_] - g.z[src] > -STOP_SAFE_DROP)
    road = [r for r in g.road if not (r[3] == CGP.KIND_DROP and r[4][0][2] - r[4][-1][2] > STOP_SAFE_DROP)]
    src, dst = np.r_[src[ok], [r[0] for r in road]], np.r_[dst[ok], [r[1] for r in road]]
    _nc, lab = connected_components(coo_matrix((np.ones(len(src), np.int8), (src, dst)), shape=(g.n, g.n)),
                                    directed=True, connection="strong")
    size = np.bincount(lab).astype(np.int64)
    up = np.arange(len(size))  # (the pieces joined here: union-find over the strong pieces)

    def find(p):
        while up[p] != p:
            up[p] = up[up[p]]
            p = up[p]
        return p

    def reached(t):
        return size[find(lab[t])] >= REACH_PIECE
    M = _Meshes(g.cont)
    walled = walled_boxes(g.cont)

    def blocked(way):
        # (across a shipped wall, or anywhere in a building Kooki3z found walked through that the meshes lack the wall
        # of: WorldGrid.lua's WG.WALLED, Nethergarde Keep's, where the mesh's way to Bernie Heisten went through it)
        if any(_cross(way[q][0], way[q][1], way[q + 1][0], way[q + 1][1], ax, ay, bx, by)
               for q in range(len(way) - 1) for ax, ay, bx, by, _d in walls
               if min(ax, bx) - 50 < way[q][0] < max(ax, bx) + 50 and min(ay, by) - 50 < way[q][1] < max(ay, by) + 50):
            return True
        for x0, y0, x1, y1 in walled:
            for q in range(len(way) - 1):
                m = max(1, int(math.dist(way[q][:2], way[q + 1][:2])))
                for k in range(m + 1):
                    px = way[q][0] + (way[q + 1][0] - way[q][0]) * k / m
                    py = way[q][1] + (way[q + 1][1] - way[q][1]) * k / m
                    if x0 <= px <= x1 and y0 <= py <= y1:
                        return True
        return False
    n, tried, joined = 0, 0, 0
    why = defaultdict(int)  # (the stops not joined, by why)
    g.stop_apart = []
    spots = [(x, y, z, name, False) for x, y, z, name in stop_spots(g.cont)]
    # (and the caves' ways in and inside, each floor of its cell with no height of its own: cave_spots)
    for x, y, z, name, under in cave_spots(g.cont):
        if z is not None:
            spots.append((x, y, z, name, True))
            continue
        gz = g.ground_z(x, y) if under else None
        for s in _surfaces(g, x, y):
            if not under or (gz is not None and not np.isnan(gz) and float(g.z[s]) <= gz - CAVE_UNDER_YD):
                spots.append((x, y, float(g.z[s]), name, True))
    cave_tried = cave_joined = 0
    for x, y, z, name, cave in spots:
        s = g.at(x, y, z, STOP_ON_Z)
        if s is None or reached(s):
            continue
        tried += 1
        cave_tried += cave
        # (onto the nearest piece bigger than the stop's own (a town's hall onto the next, Ironforge's halls one after
        # another), till the ground players reach)
        for _step in range(STOP_STEPS):
            own = find(lab[s])
            end = []

            def done(_n, m):
                for t in _surfaces(g, m[0], m[1]):
                    p = find(lab[t])
                    if abs(float(g.z[t]) - m[2]) <= STOP_REACH_Z and p != own and size[p] > size[own]:
                        end.append(t)
                        return True
                return False
            way = _mesh_way(M, x, y, z, done, STOP_PATH_YD)
            if not way or not end:
                why["no way on the mesh"] += 1
                break
            t = end[-1]
            if blocked(way):
                why["across a wall"] += 1
                break
            yd = sum(math.dist(way[q], way[q + 1]) for q in range(len(way) - 1))
            pts = _thin([(*g.point(s), float(g.z[s]))] + [tuple(float(v) for v in p) for p in way]
                        + [(*g.point(t), float(g.z[t]))])
            for a_, b_, pp in ((s, t, pts), (t, s, list(reversed(pts)))):
                r_ = (a_, b_, max(yd, 1.0), CGP.KIND_WALK, pp)
                g.road.append(r_)
                g.road_out[a_].append(r_)
                n += 1
            p = find(lab[t])
            up[own] = p
            size[p] += size[own]
            if reached(s):
                joined += 1
                cave_joined += cave
                break
        if not reached(s) and not cave:
            g.stop_apart.append((x, y, z, name))
    # (then each stop's floor and the floors round it the mesh walks to much shorter than the grid's way does (a town's
    # levels the grid joins only far round: Booty Bay's docks and its walkways, 1,310 yd from Auctioneer Kresky to
    # Grarnik Goodstitch up the walkway 64 yd off): the mesh's way, a link each way, for the most yards saved, up to
    # STOP_SHORTCUTS of them (the grid's way longer than STOP_DETOUR times the mesh's + STOP_DETOUR_YD)
    opp_ = np.array(opp)

    def safe_next(u):
        for d in range(8):
            t = int(g.links[u, d])
            if t < 0 or (g.z[t] - g.z[u] <= -STOP_SAFE_DROP and int(g.links[t, opp_[d]]) != u):
                continue
            yield t, g.step_cost(u, d, t)
        for r in g.road_out.get(u, ()):
            if not (r[3] == CGP.KIND_DROP and r[4][0][2] - r[4][-1][2] > STOP_SAFE_DROP):
                yield r[1], r[2]

    def grid_dists(a, limit):
        import heapq
        dist, h = {a: 0.0}, [(0.0, a)]
        while h:
            d, u = heapq.heappop(h)
            if d > dist.get(u, math.inf):
                continue
            for t, c in safe_next(u):
                nd = d + c
                if nd <= limit and nd < dist.get(t, math.inf):
                    dist[t] = nd
                    heapq.heappush(h, (nd, t))
        return dist
    short = 0
    for x, y, z, name in stop_spots(g.cont):
        s = g.at(x, y, z, STOP_ON_Z)
        if s is None or not reached(s):
            continue
        tree = _mesh_way(M, x, y, z, None, STOP_NEAR_YD)
        if not tree:
            continue
        polys, way_to = tree
        cand = []
        for n_, (dm, m) in polys.items():
            for t in _surfaces(g, m[0], m[1]):
                if abs(float(g.z[t]) - m[2]) <= STOP_REACH_Z and t != s and reached(t):
                    cand.append((dm, t, n_))
        tried_t = set()
        for _round in range(STOP_SHORTCUTS):
            dg = grid_dists(s, STOP_DETOUR * STOP_NEAR_YD + STOP_DETOUR_YD)
            best = None
            for dm, t, n_ in cand:
                got = dg.get(t, math.inf)
                if t in tried_t or got <= dm * STOP_DETOUR + STOP_DETOUR_YD:
                    continue
                gain = min(got, 10 * STOP_NEAR_YD) - dm
                if best is None or gain > best[0]:
                    best = (gain, t, n_)
            if best is None:
                break
            _gain, t, n_ = best
            tried_t.add(t)
            way = way_to(n_)
            if blocked(way):
                continue
            yd = sum(math.dist(way[q], way[q + 1]) for q in range(len(way) - 1))
            pts = _thin([(*g.point(s), float(g.z[s]))] + [tuple(float(v) for v in p) for p in way]
                        + [(*g.point(t), float(g.z[t]))])
            for a_, b_, pp in ((s, t, pts), (t, s, list(reversed(pts)))):
                r_ = (a_, b_, max(yd, 1.0), CGP.KIND_WALK, pp)
                g.road.append(r_)
                g.road_out[a_].append(r_)
                n += 1
            short += 1
    log(f"  cont {g.cont}: {tried} stops' floors apart from the reached ground, {joined} joined to it along the mesh "
        f"({n} links; not: {dict(why)}; caves' spots: {cave_joined} of {cave_tried} joined); {short} ways shorter on "
        f"the mesh to the floors round a stop")
    return n


def shipped_walls(cont: int) -> list:
    """The continent's shipped walls (Roads.lua's ns.Walls, as Passability.WallLines takes them): [(ax, ay, bx, by,
    down (nx, ny) or None: a cliff walked down that way is no wall)]."""
    from .gameharness import start
    lua, ns = start()
    out = []
    for w in (ns.Passability.WallLines(cont) or {}).values():
        pts = [w[i] for i in range(1, len(w) + 1)]
        for i in range(0, len(pts) - 3, 2):
            ax, ay, bx, by = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
            down = None
            if w.kind == "cliff":  # (Passability's WallGrid: a cliff's section open, a wall, or one walked down)
                how, nx, ny, _dz = ns.Passability.CliffSection(w, (i + 2) // 2)
                if how == "open":
                    continue
                if how == "down":
                    down = (nx, ny)
            out.append((ax, ay, bx, by, down))
    # (the thin tall walls from the models' collision, Data/ModelWalls.lua: item 78, Red Cloud Mesa's palisade; the
    # addon refuses the links across them as it searches too, Passability.CrossesModelWall)
    for w in ns.Passability.ModelWallOutlines(cont).values():
        pts = [w[i] for i in range(1, len(w) + 1)]
        for i in range(0, len(pts) - 3, 2):
            out.append((pts[i], pts[i + 1], pts[i + 2], pts[i + 3], None))
    return out


def _cross(ax, ay, bx, by, cx, cy, dx, dy) -> bool:
    def o(px, py, qx, qy, rx, ry):
        v = float((qx - px) * (ry - py) - (qy - py) * (rx - px))
        return (v > 1e-9) - (v < -1e-9)
    return (o(ax, ay, bx, by, cx, cy) * o(ax, ay, bx, by, dx, dy) < 0
            and o(cx, cy, dx, dy, ax, ay) * o(cx, cy, dx, dy, bx, by) < 0)


def cut_walls(g: Grid, walls: list, log=print) -> int:
    """The shipped walls are truth (drawn in game, "no wall hopping allowed"): every grid link and road link across one
    is dropped (a cliff's wall only the way up). Returns the links dropped."""
    cut = 0
    c = g.cell
    for ax, ay, bx, by, down in walls:
        i0, i1 = int(math.floor(min(ax, bx) / c)) - 1, int(math.floor(max(ax, bx) / c)) + 1
        j0, j1 = int(math.floor(min(ay, by) / c)) - 1, int(math.floor(max(ay, by) / c)) + 1
        for gx in range(i0, i1 + 1):
            for gy in range(j0, j1 + 1):
                kx, ky = gx - g.gxmin, gy - g.gymin
                if not (0 <= kx < g.W and 0 <= ky < g.H):
                    continue
                f, n = int(g.first[kx * g.H + ky]), int(g.count[kx * g.H + ky])
                for s in range(f, f + max(n, 0)):
                    px, py = g.point(s)
                    for d in range(8):
                        t = int(g.links[s, d])
                        if t < 0:
                            continue
                        qx, qy = g.point(t)
                        if _cross(px, py, qx, qy, ax, ay, bx, by):
                            if down is not None and (qx - px) * down[0] + (qy - py) * down[1] > 0:
                                continue
                            g.links[s, d] = -1
                            cut += 1
    keep = []
    for r in g.road:
        pts = r[4]
        hit = any(_cross(pts[q][0], pts[q][1], pts[q + 1][0], pts[q + 1][1], ax, ay, bx, by) and down is None
                  for q in range(len(pts) - 1) for ax, ay, bx, by, down in walls
                  if min(ax, bx) - 50 < pts[q][0] < max(ax, bx) + 50 and min(ay, by) - 50 < pts[q][1] < max(ay, by) + 50)
        if hit:
            cut += 1
        else:
            keep.append(r)
    g.road = keep
    g.road_out = defaultdict(list)
    for r in keep:
        g.road_out[r[0]].append(r)
    log(f"  cont {g.cont}: {len(walls)} shipped wall pieces, {cut} links across them dropped")
    return cut


UNDER_GROUND_Z = 6.0  # yards: a floor this far under the terrain's height there is under the ground (a cave, a tunnel)
HOLE_DROP_MIN = 8.0  # yards: a drop this far at least onto a cave's floor under a hole through a floor (bake9)
CEILING_DROP_MIN = 12.0  # yards: a drop through the ground this far at least (Data/Heights.lua's 16.7 yd samples
# can't tell a smaller ledge's foot from a cave's floor)


def cut_ceiling_drops(g: Grid, log=print) -> int:
    """Every one-way drop link from a floor on the ground (not UNDER_GROUND_Z under the terrain's height, Data/Heights.lua)
    down onto one under the ground is dropped: the mesh's walk fell off the edge of a hole in the terrain onto the cave
    or tunnel under it, through the rock the hole is covered by (bake8: Moonbrook's hill over the Deadmines' tunnel, the
    walk to the portal went over the hill and fell 20 yd through it, not in by the Defias hideout's way in). Drops inside
    a cave (its top under the ground too), off a cliff or a building onto the ground stay. Returns the links dropped."""
    opp = np.array([DIRS.index((-dx, -dy)) for dx, dy in DIRS])
    pts = np.array([g.point(s) for s in range(g.n)]) if g.n else np.zeros((0, 2))
    ground = g._ground.sample(pts[:, 0], pts[:, 1]) if g._ground is not None and g.n else np.full(g.n, np.nan)
    under = np.isfinite(ground) & (g.z < ground - UNDER_GROUND_Z)
    on = ~np.isfinite(ground) | (g.z >= ground - UNDER_GROUND_Z)
    # (a cave's floor under walkable ground, Data/Caves.lua's 3, down under the terrain: a drop onto it from the
    # ground is into the cave's insides from outside, wherever the ground's edge is: bake9, Darkmist Cavern's tunnels
    # 176 yd under the Barrens' ridge, "those should only be routes available outside the cave once going through the
    # entrance" (Kooki3z). A cave is entered by its mouths, walked)
    hole = ~np.isfinite(ground)
    in_cave = cave_floor_cells(g.cont, pts, under | hole) if g.n else np.zeros(0, bool)
    # (and where the terrain has a hole, a building's over a cave's way down (no height there): a drop onto a cave's
    # floor with another floor of its cell between the foot and just over the top (UNDER_GROUND_Z) falls through that
    # floor: bake9, the Defias hideout's house in Moonbrook, from its floor 45 straight down to the tunnel's 24, under the
    # ramp's 36 and the house's own floor, or by the ramp's 36 in two drops of 12 and 11; walked down the ramp)
    flat = ((g.gx - g.gxmin).astype(np.int64) * g.H + (g.gy - g.gymin)) if g.n else np.zeros(0, np.int64)
    order = np.lexsort((g.z, flat)) if g.n else np.zeros(0, np.int64)
    fs, zs = flat[order], g.z[order]

    def floor_between(tt, lo, hi):
        out = np.zeros(len(tt), bool)
        for k, (t, a, b) in enumerate(zip(tt, lo, hi)):
            i, j = np.searchsorted(fs, flat[t], "left"), np.searchsorted(fs, flat[t], "right")
            col = zs[i:j]
            out[k] = bool(((col > a) & (col < b)).any())
        return out
    cut = cave = 0
    for d in range(8):
        t = g.links[:, d]
        has = t >= 0
        tt = np.maximum(t, 0)
        back = g.links[tt, opp[d]] == np.arange(g.n)
        down = has & ~back & (g.z[tt] < g.z - DROP_MIN) & on & under[tt]
        # (and the terrain over the foot about as high as the top: a hole in the ground, not a cliff whose foot the
        # coarse heights put under the slope's middle; off a cliff the ground at the foot is the foot's own)
        drop = (down & (g.z[tt] < g.z - CEILING_DROP_MIN)
                & np.isfinite(ground[tt]) & (ground[tt] >= g.z - UNDER_GROUND_Z))
        into = down & in_cave[tt] & ~drop
        fall = has & ~back & on & hole[tt] & in_cave[tt] & (g.z[tt] < g.z - HOLE_DROP_MIN) & ~drop & ~into
        w = np.nonzero(fall)[0]
        if len(w):
            fall[w] = floor_between(tt[w], g.z[tt[w]] + UNDER_GROUND_Z, g.z[w] + UNDER_GROUND_Z)
        into |= fall
        cut += int(drop.sum())
        cave += int(into.sum())
        g.links[drop | into, d] = -1
    g.cave_drops = cave
    log(f"  cont {g.cont}: {cut} drops from the ground down through it into a cave or tunnel dropped, {cave} more "
        f"onto a cave's floor under the ground (Data/Caves.lua)")
    return cut + cave


def cave_floor_cells(cont: int, pts: np.ndarray, which: np.ndarray) -> np.ndarray:
    """Whether each point (of those `which` says) is over a cave's cells (Data/Caves.lua's 0, 2 or 3: its own, by
    Passability's overlay grids, the game harness's)."""
    out = np.zeros(len(pts), bool)
    idx = np.nonzero(which)[0]
    if not len(idx):
        return out
    from .gameharness import start
    lua, ns = start()
    f = lua.eval("""function(cont, xs, ys, n)
      local P, out = AGPS_NS.Passability, {}
      for i = 1, n do
        local v, o = P.OverlayRaw(cont, xs[i], ys[i])
        out[i] = (v ~= nil and o and o.cave) and 1 or 0
      end
      return out
    end""")
    step = 50000
    for a in range(0, len(idx), step):
        part = idx[a:a + step]
        got = f(cont, lua.table(*pts[part, 0].tolist()), lua.table(*pts[part, 1].tolist()), len(part))
        out[part] = [got[i + 1] == 1 for i in range(len(part))]
    return out


REACH_PIECE = 2000  # surfaces: a piece this big is ground a player reaches (an island), not a rock's top or a roof


def grid_tiles(cont: int, per_tile: int = CELL_PER_TILE) -> list:
    return sorted({(int(p.stem.split("_")[1]), int(p.stem.split("_")[2]))
                   for p in grid_dir().glob(f"{cont}_*_{per_tile}.npz")})


def assemble(cont: int, per_tile: int = CELL_PER_TILE, log=print, roads=True, tiles=None, edge=None) -> Grid:
    """The continent's grid from its tiles' (worldgrid.build_tiles first): seams matched, roads marked and linked, small
    pieces no road touches left out, the capitals' own cells left to the city grid. `tiles`: only those (a window,
    bake_regions); `edge`: its outer tiles, whose pieces go on outside it (kept, reached)."""
    from .worldzones import pieces

    tiles = grid_tiles(cont, per_tile) if tiles is None else sorted(tiles)
    g = Grid(cont, tiles, per_tile, log)
    g._ground = Heights(cont)
    if roads:
        mark_roads(g, land_roads(cont, log), log)
    cut_ceiling_drops(g, log)
    walls = shipped_walls(cont)
    cut_walls(g, walls, log)
    if roads:
        lift_links(g, log)
        mark_recorded(g, recorded_walks(cont), log)
        stop_links(g, walls, log)
    lab, sizes = pieces(g)
    touched = np.unique(lab[(g.flags & FLAG_ROAD) > 0])
    keep = (sizes[lab] >= MIN_PIECE) | np.isin(lab, touched)
    caps = capital_cells(g)
    keep &= ~caps
    g.reach = (lab == 0) | np.isin(lab, touched) | (sizes[lab] >= REACH_PIECE)
    if edge:
        ttx, tty = 31 - g.gy // per_tile, 31 - g.gx // per_tile
        on_edge = np.isin(ttx * 64 + tty, [tx * 64 + ty for tx, ty in edge])
        out_ = np.isin(lab, np.unique(lab[on_edge]))
        keep |= out_ & ~caps
        g.reach |= out_
    g.piece = lab
    log(f"  cont {cont}: {len(sizes)} pieces (biggest {sizes[:3].tolist()}); kept {int(keep.sum())} of {g.n} surfaces "
        f"({int(caps.sum())} in the capitals' own cells, left to the city grid)")
    prune(g, keep)
    return g


def prune(g: Grid, keep: np.ndarray) -> None:
    """Only the surfaces `keep` says (ids renumbered, links to the others dropped)."""
    new = np.cumsum(keep) - 1
    remap = np.where(keep, new, -1)
    L = g.links[keep]
    g.links = np.where(L >= 0, remap[np.maximum(L, 0)], -1)
    for name in ("gx", "gy", "z", "off", "kind", "flags", "reach", "piece", "rim"):
        setattr(g, name, getattr(g, name)[keep])
    g.road = [(int(remap[a]), int(remap[b]), c, k, p) for a, b, c, k, p in g.road if keep[a] and keep[b]]
    g.road_out = defaultdict(list)
    for r in g.road:
        g.road_out[r[0]].append(r)
    g.n = int(keep.sum())
    flat = (g.gx - g.gxmin).astype(np.int64) * g.H + (g.gy - g.gymin)
    g.first = np.full(g.W * g.H, -1, np.int64)
    g.count = np.zeros(g.W * g.H, np.int8)
    if g.n:
        starts = np.r_[0, np.nonzero(np.diff(flat))[0] + 1]
        g.first[flat[starts]] = starts
        np.add.at(g.count, flat, 1)


# --- the file -----------------------------------------------------------------------------------------------------------

ZQ = 0.5  # yards a height step
Z0 = -2000.0  # (an escaped height: 3 characters from Z0; the map's floors are -1001 to 2627, Teldrassil's crown at
# 1,300-1,500: the first file's 2 characters from -1000 clipped them all to 1,047)
REP = "."  # (a repeat: the token before, again ALPHA's value + 2 times)
ZESC = 62  # (a height not near its prediction: this, then 2 characters)
F_SWIM, F_ROAD, F_REACH, F_RIM_WALL = 1, 2, 4, 8  # (F_RIM_WALL: worldgrid.RIM_WALL_CELLS, no fall starts there)
# Links implied by the heights (written only where they differ, encode_tiles): in each direction, the surface of the
# neighbor cell nearest in height, when within IMPLIED_Q height steps and in the same map tile, else none (WorldGrid.lua's
# WG.Tile does the same on decoding)
IMPLIED_Q = int(os.environ.get("AGPS_WG_IMPLIED_Q", "4"))
# Map tiles a side of a region: each region one load-on-demand addon folder (AzerothGPS_WG<cont>_<rx>_<ry>), loaded by
# the game only when a route's search first reaches one of its tiles (WorldGrid.lua's WG.LoadRegion)
REGION = int(os.environ.get("AGPS_WG_REGION", "8"))


def tile_index(g: Grid):
    """Each surface's tile key (tx * 64 + ty) and index in its tile (by cell, column by column, then height)."""
    per = g.per_tile
    ttx, tty = 31 - g.gy // per, 31 - g.gx // per
    key = (ttx * 64 + tty).astype(np.int64)
    gx0, gy0 = (31 - tty) * per, (31 - ttx) * per
    local = (g.gx - gx0).astype(np.int64) * per + (g.gy - gy0)
    order = np.lexsort((g.z, local, key))
    kk = key[order]
    starts = np.r_[0, np.nonzero(np.diff(kk))[0] + 1]
    pos = np.arange(g.n) - np.repeat(starts, np.diff(np.r_[starts, g.n]))
    idx = np.empty(g.n, np.int64)
    idx[order] = pos
    return key, local, idx, order


def _rle(tokens: list) -> str:
    A = ALPHA
    res, prev, run = [], None, 0
    for t in tokens + [None]:
        if t == prev and run < 65:
            run += 1
            continue
        if prev is not None:
            res.append(prev)
            if run == 2:
                res.append(prev)
            elif run > 2:
                res.append(REP + A[run - 3])
        prev, run = t, 1
    return "".join(res)


def link_rows(g: Grid) -> np.ndarray:
    """Each surface's links as the file has them: per direction the neighbor cell's surface 1-7, 0 none."""
    flat = (g.gx - g.gxmin).astype(np.int64) * g.H + (g.gy - g.gymin)
    kin = np.arange(g.n) - g.first[flat]
    return np.minimum(np.where(g.links >= 0, kin[np.maximum(g.links, 0)] + 1, 0), 7)


def implied_rows(g: Grid, zq: np.ndarray) -> np.ndarray:
    """Each surface's links as the heights alone give them (IMPLIED_Q): the decoder's rule. Per direction: the neighbor
    cell's surface nearest in height (the lower on a tie), when within IMPLIED_Q steps and the cell in the same tile."""
    per = g.per_tile
    out = np.zeros((g.n, 8), np.int64)
    ttx, tty = 31 - g.gy // per, 31 - g.gx // per
    for d, (dx, dy) in enumerate(DIRS):
        nx, ny = g.gx + dx, g.gy + dy
        same = ((31 - ny // per) == ttx) & ((31 - nx // per) == tty)
        kx, ky = nx - g.gxmin, ny - g.gymin
        inside = same & (kx >= 0) & (ky >= 0) & (kx < g.W) & (ky < g.H)
        nflat = np.where(inside, kx.astype(np.int64) * g.H + ky, 0)
        f, cnt = g.first[nflat], np.where(inside, g.count[nflat], 0)
        best = np.full(g.n, 10 ** 9, np.int64)
        bk = np.zeros(g.n, np.int64)
        for k in range(7):
            has = cnt > k
            cand = np.where(has, f + k, 0)
            dz = np.where(has, np.abs(zq[cand] - zq), 10 ** 9)
            take = dz < best
            best[take], bk[take] = dz[take], k + 1
        out[:, d] = np.where(best <= IMPLIED_Q, bk, 0)
    return out


def encode_tiles(g: Grid, log=print) -> dict:
    """{tile key (tx * 64 + ty): its string}: four parts by "|". Its cells' counts (a character each, column by column:
    cell a * per + b, a along x); its surfaces' records in that order (a cell's by height), each flags (F_*) and its
    point's spot in the cell (x step * 8 + y step); its surfaces' heights in that order, each against its prediction (the
    same surface k of the cell before in the column, else that cell's last, else the last height): ALPHA[d + 31] for a
    step of d * ZQ (|d| <= 30), else ZESC and 3 characters ((z - Z0) / ZQ); its surfaces' links against those the heights
    give (implied_rows): "0" where they're the same, else "1" and 4 characters, two directions each, (link - implied) % 8
    (a link: the neighbor cell's surface 1-7, 0 none; worldgrid.DIRS' order). REP and a character n repeats the token
    before n + 2 more times (in each part)."""
    per = g.per_tile
    zq = np.clip(np.round((g.z - Z0) / ZQ).astype(np.int64), 0, 64 ** 3 - 1)
    L = link_rows(g)
    diff = (L - implied_rows(g, zq)) % 8
    implied = (diff == 0).all(1)
    flags = ((g.kind == KIND_SWIM) * F_SWIM) | (((g.flags & FLAG_ROAD) > 0) * F_ROAD) | (g.reach * F_REACH)
    flags = flags | ((getattr(g, "rim", None) if getattr(g, "rim", None) is not None else 0) > 0) * F_RIM_WALL
    key, local, _idx, order = tile_index(g)
    bounds = np.r_[0, np.nonzero(np.diff(key[order]))[0] + 1, g.n]
    A = ALPHA
    out = {}
    for q in range(len(bounds) - 1):
        ids = order[bounds[q]:bounds[q + 1]]
        cnt = np.zeros(per * per, int)
        np.add.at(cnt, local[ids], 1)
        recs, zs, lks = [], [], []
        prev_cell, last = [], None
        pos = 0
        loc = local[ids]
        for ci in range(per * per):
            n = cnt[ci]
            if ci % per == 0:
                prev_cell = []
            if not n:
                prev_cell = []
                continue
            cell_z = []
            for k in range(n):
                s = int(ids[pos + k])
                recs.append(A[int(flags[s])] + A[int(g.off[s])])
                lks.append("0" if implied[s] else "1" + "".join(A[int(diff[s, 2 * m]) * 8 + int(diff[s, 2 * m + 1])] for m in range(4)))
                pred = prev_cell[k] if k < len(prev_cell) else (prev_cell[-1] if prev_cell else last)
                v = int(zq[s])
                d = v - pred if pred is not None else 999
                zs.append(A[d + 31] if -30 <= d <= 30 else A[ZESC] + A[v >> 12] + A[(v >> 6) & 63] + A[v & 63])
                last = v
                cell_z.append(v)
            prev_cell = cell_z
            pos += n
        assert pos == len(ids) and (np.diff(loc) >= 0).all()
        out[int(key[ids[0]])] = "|".join((_rle([A[c] for c in cnt.tolist()]), _rle(recs), _rle(zs), _rle(lks)))
    g.implied_share = float(implied.mean())
    log(f"  cont {g.cont}: {len(out)} tiles, {sum(len(v) for v in out.values()) / 1e6:.2f} MB; links implied by the "
        f"heights on {100 * g.implied_share:.1f}% of surfaces")
    return out


def region_of(key: int) -> tuple:
    return (key // 64) // REGION, (key % 64) // REGION


def encode_links(g: Grid) -> dict:
    """The road links by the region of their first end's tile: {region: "ka:ia,kb:ib,yards,kind,x,y,z,...;..."} (each end
    its tile's key and its index in the tile; a yard of one costs the data's `road`, WorldGrid.lua)."""
    key, _local, idx, _o = tile_index(g)
    parts = defaultdict(list)
    for a, b, cost, kind, pts in g.road:
        flat = ",".join(f"{p[0]:.1f},{p[1]:.1f},{p[2]:.1f}" for p in pts)
        ka = int(key[a])
        parts[region_of(ka)].append(f"{ka}:{idx[a]},{key[b]}:{idx[b]},{cost / ROAD_PREF:.0f},{kind},{flat}")
    return {r: ";".join(v) for r, v in parts.items()}


BAKE_PARAMS = ("ZQ", "Z0", "REACH_PIECE", "IMPLIED_Q", "REGION", "ROAD_FOLLOW_Z", "ROAD_LINK_DZ", "ROAD_LINK_SLOPE",
               "ROAD_FLOORS", "ROAD_LINK_SPAN_SLOPE", "REC_RIDE_YD", "STOP_ON_Z", "STOP_MESH_YD", "STOP_SAFE_DROP",
               "STOP_THIN_YD", "STOP_DETOUR", "STOP_DETOUR_YD", "STOP_NEAR_YD", "STOP_SHORTCUTS", "STOP_STEPS",
               "STOP_PATH_YD", "STOP_REACH_Z", "UNDER_GROUND_Z",
               "CEILING_DROP_MIN", "HOLE_DROP_MIN")


def bake_stamp() -> str:
    from . import worldgrid as W
    parts = [f"{k}={globals()[k]!r}" for k in BAKE_PARAMS]
    parts += [f"{k}={getattr(W, k)!r}" for k in ("CELL_PER_TILE", "SHORE_Z", "MIN_PIECE", "ROAD_PREF", "SWIM_COST", "HOPS",
                                                  "WALKED", "DROP_MAX", "DROP_FAR", "DROP_MIN", "ROUND_Z")]
    parts += [f"WM.PAD={WM.PAD}", f"WM.WADE={WM.WADE}", f"CGP.WALK_SLOPE={CGP.WALK_SLOPE}", f"CGP.MERGE_Z={CGP.MERGE_Z}"]
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


def addons_root() -> Path:
    env = os.environ.get("AGPS_WORLDGRID_OUT")  # (a trial's files apart from the addon's: an addon/ like folder)
    return Path(env) if env else ADDON_DIR.parent


def out_path(cont: int) -> Path:
    return addons_root() / "AzerothGPS" / "Data" / f"WorldGrid{cont}.lua"


CONT_NAMES = {0: "Eastern Kingdoms", 1: "Kalimdor", 2991: "Zephras Isle"}


def region_folder(cont: int, r: tuple) -> str:
    return f"AzerothGPS_WG{cont}_{r[0]}_{r[1]}"


def toc_interface() -> str:
    m = re.search(r"^## Interface: *(\S+)", (ADDON_DIR / "AzerothGPS.toc").read_text(encoding="utf-8"), re.M)
    return m.group(1)


# The game's AddOn List (its own Blizzard_AddOnList, read from CASC 2026-11-23) shows every addon folder: no toc field
# hides one. A `## Group` naming another addon puts the folder's row under that addon's (indented; that row's
# right-click turns the whole group on or off), and `## IconTexture` replaces the red question mark. So each region
# reads as a part of AzerothGPS, under it, with AzerothGPS's own icon.
REGION_NOTES = "Part of AzerothGPS, loaded automatically when needed. Keep it enabled."
REGION_ICON = "Interface\\AddOns\\AzerothGPS\\Media\\Device"


TITLE_COLOR = "2680ff"  # (the AddOn List title's blue: the first route's, Nav.MARKER_COLORS[6], as AzerothGPS.toc's)


def region_title(cont: int, r: tuple) -> str:
    return f"|cff{TITLE_COLOR}AzerothGPS map data: {CONT_NAMES.get(cont, cont)} {r[0]}-{r[1]}|r"


def region_toc(cont: int, r: tuple, root: Path | None = None) -> str:
    """A region folder's toc (its data is Data.lua; its landmark fields Alt.lua when the folder has them, worldalt.py:
    kept listed over a grid bake, an old bake's left unused by WG.LoadRegion till `agps world-grid alt --write`)."""
    alt = ((root or addons_root()) / region_folder(cont, r) / "Alt.lua").is_file()
    return "\n".join([f"## Interface: {toc_interface()}",
                      f"## Title: {region_title(cont, r)}",
                      f"## Notes: {REGION_NOTES}",
                      "## Author: AzerothGPS",
                      "## Group: AzerothGPS",
                      f"## IconTexture: {REGION_ICON}",
                      "## LoadOnDemand: 1",
                      "## Dependencies: AzerothGPS",
                      "", "Data.lua"] + (["Alt.lua"] if alt else []) + [""])


def write_region_tocs(addon_root: Path | None = None) -> list:
    """Writes every region folder's toc again, its Data.lua untouched (`agps world-grid tocs`: no bake)."""
    root = addon_root or ADDON_DIR.parent
    out = []
    for d in sorted(root.glob("AzerothGPS_WG*")):
        m = re.fullmatch(r"AzerothGPS_WG(\d+)_(\d+)_(\d+)", d.name)
        if not (m and d.is_dir()):
            continue
        p = d / f"{d.name}.toc"
        p.write_text(region_toc(int(m.group(1)), (int(m.group(2)), int(m.group(3))), root), encoding="utf-8", newline="\n")
        out.append(p)
    return out


def header_text(g: Grid, regions: dict) -> str:
    rs = ", ".join(f'["{r[0]}:{r[1]}"] = {n}' for r, n in sorted(regions.items()))
    return "\n".join([
        "-- GENERATED by `agps world-grid --write` (app/azerothgps/worldbake.py). Do not edit by hand.",
        "-- The open world's layered walk grid (1.4.0's world routing, being tested; docs/world-grid-1.4.0.md): this",
        "-- continent's numbers only. Its map tiles are in the load-on-demand folders AzerothGPS_WG<cont>_<rx>_<ry>",
        "-- (`regions`: each one's count of tiles), loaded when a route's search first reaches one (WG.LoadRegion).",
        "local _, ns = ...",
        "ns.WorldGridData = ns.WorldGridData or {}",
        f"ns.WorldGridData[{g.cont}] = {{ per = {g.per_tile}, cell = {g.cell:.6f}, zq = {ZQ:g}, z0 = {Z0:g}, "
        f'road = {ROAD_PREF:g}, swim = {SWIM_COST:g}, bake = "{bake_stamp()}", n = {g.n}, implied = {IMPLIED_Q}, '
        f"rb = {REGION}, regions = {{ {rs} }} }}", ""])


def region_texts(g: Grid, tiles: dict, links: dict) -> dict:
    """{folder name: {file name: text}}: each region's load-on-demand addon (its toc and its data)."""
    by = defaultdict(dict)
    for k, v in tiles.items():
        by[region_of(k)][k] = v
    out = {}
    stamp = bake_stamp()
    for r, ts in sorted(by.items()):
        name = region_folder(g.cont, r)
        toc = region_toc(g.cont, r)
        lines = ["-- GENERATED by `agps world-grid --write` (app/azerothgps/worldbake.py). Do not edit by hand.",
                 "-- AzerothGPS's world grid: one region's map tiles (numbers only), taken by WorldGrid.lua (WG.LoadRegion).",
                 "local all = AzerothGPS_WorldGridTiles or {}",
                 "AzerothGPS_WorldGridTiles = all",
                 f'all["{g.cont}:{r[0]}:{r[1]}"] = {{ bake = "{stamp}", t = {{']
        for k in sorted(ts):
            lines.append(f'  [{k}] = "{ts[k]}",')
        lines.append("  },")
        lines.append(f'  links = "{links.get(r, "")}",')
        lines.append("}")
        out[name] = {f"{name}.toc": toc, "Data.lua": "\n".join(lines) + "\n"}
    return out


def _surface_count(tile: str) -> int:
    """A tile string's surfaces (its counts' sum; encode_tiles)."""
    part, out, i, last = tile.split("|")[0], 0, 0, 0
    while i < len(part):
        if part[i] == REP:
            out += last * (ALPHA.index(part[i + 1]) + 2)
            i += 2
        else:
            last = ALPHA.index(part[i])
            out += last
            i += 1
    return out


def region_window(regions, have, ring: int = 2) -> tuple:
    """(the tiles of `have` in `regions`, those and the ones within `ring` tiles of them): what bake_regions assembles,
    and so the tiles `agps world-grid grid --regions` builds again."""
    regions = {tuple(r) for r in regions}
    want = {t for t in have if region_of(t[0] * 64 + t[1]) in regions}
    window = {(tx + a, ty + b) for tx, ty in want for a in range(-ring, ring + 1)
              for b in range(-ring, ring + 1)} & set(have)
    return want, window


def bake_regions(cont: int, regions: list, per_tile: int = CELL_PER_TILE, ring: int = 2, write: bool = False,
                 log=print) -> dict:
    """Only `regions`' load-on-demand folders baked again (a change there, small enough for any PC): their tiles and a
    ring of `ring` map tiles round them assembled (the ring's pieces going on outside the window kept and reached, as
    the whole continent's bake has them), their tiles and road links encoded; the header's count and the regions' tile
    counts updated. Each tile outside the changes encodes as the whole bake's did: `same` (tile keys) and `differ` say
    so against the folders there now, the ring's tiles too (a road link of a written region into one keys its surfaces
    by their index there)."""
    if write:
        need_bake_data(cont)
    regions = {tuple(r) for r in regions}
    alltiles = grid_tiles(cont, per_tile)
    have = set(alltiles)
    want, window = region_window(regions, have, ring)
    edge = {t for t in window if any((t[0] + a, t[1] + b) in have - window for a in (-1, 0, 1) for b in (-1, 0, 1))}
    g = assemble(cont, per_tile, log, tiles=window, edge=edge)
    tiles = encode_tiles(g, log)
    links = encode_links(g)
    old = {}
    for folder in addons_root().glob(f"AzerothGPS_WG{cont}_*"):
        f = folder / "Data.lua"
        if f.exists():
            old.update({int(k): v for k, v in re.findall(r'\n  \[(\d+)\] = "([^"]*)",', f.read_text(encoding="utf-8"))})
    same = sorted(k for k, v in tiles.items() if old.get(k) == v)
    differ = sorted(k for k, v in tiles.items() if old.get(k) != v)
    wanted = {k: v for k, v in tiles.items() if (k // 64, k % 64) in want}
    ring_differ = sorted(k for k in differ if (k // 64, k % 64) not in want)
    texts = region_texts(g, wanted, {r: v for r, v in links.items() if r in regions})
    st = {"cont": cont, "regions": sorted(regions), "tiles": len(wanted), "window": len(window),
          "same": len([k for k in same if (k // 64, k % 64) in want]),
          "differ": [k for k in differ if (k // 64, k % 64) in want], "ring_differ": ring_differ,
          "road_links": len(g.road),
          "bytes_new": sum(len(t) for f in texts.values() for t in f.values())}
    root = addons_root()
    st["bytes_old"] = sum((root / n / fn).stat().st_size for n, f in texts.items() for fn in f if (root / n / fn).exists())
    log(f"  {st}")
    if write:
        for name, files in texts.items():
            (root / name).mkdir(parents=True, exist_ok=True)
            for fn, text in files.items():
                (root / name / fn).write_text(text, encoding="utf-8", newline="\n")
        head = out_path(cont).read_text(encoding="utf-8")
        m = re.search(r"n = (\d+),", head)
        counts = defaultdict(int)
        for k in set(old) | set(tiles):
            if (k // 64, k % 64) in want and k not in tiles:
                continue
            if k in tiles and (k // 64, k % 64) not in want and k not in old:
                continue
            counts[region_of(k)] += 1
        rs = ", ".join(f'["{r[0]}:{r[1]}"] = {n}' for r, n in sorted(counts.items()))
        head = re.sub(r"regions = \{ .*? \} \}", "regions = { " + rs + " } }", head)
        allt = {k: v for k, v in old.items() if (k // 64, k % 64) not in want}
        allt.update(wanted)
        n = sum(_surface_count(v) for v in allt.values())
        head = re.sub(r"n = \d+,", f"n = {n},", head, count=1)
        log(f"wrote {len(texts)} region folders (header n {m.group(1) if m else '?'} -> {n})")
        out_path(cont).write_text(head, encoding="utf-8", newline="\n")
    return st


def need_bake_data(cont: int) -> None:
    """The reference data a bake reads, there (item 72: a checkout's data/ without the lifts' dump or the terrain's water
    baked no lifts and no seas, silently): an error naming the file, AZEROTHGPS_DATA the full data/ to use."""
    from . import lifts
    if cont in (0, 1):
        for p in (data_dir() / lifts.DUMP, data_dir() / f"pass_{cont}_clean.npy"):
            if not p.exists():
                raise FileNotFoundError(f"{p}: the bake needs it (AZEROTHGPS_DATA: the full data/ folder)")


def bake(cont: int, per_tile: int = CELL_PER_TILE, write: bool = False, log=print) -> dict:
    """The continent's grid baked: its numbers; `write`: Data/WorldGrid<cont>.lua (the header) and its regions'
    load-on-demand folders (AzerothGPS_WG<cont>_*; this continent's old ones removed)."""
    import shutil
    if write:
        need_bake_data(cont)
    g = assemble(cont, per_tile, log)
    opp = [DIRS.index((-dx, -dy)) for dx, dy in DIRS]
    g.one_way = 0
    for d in range(8):
        t = g.links[:, d]
        has = t >= 0
        back = g.links[np.maximum(t, 0), opp[d]]
        g.one_way += int((has & (back != np.arange(g.n))).sum())
    tiles = encode_tiles(g, log)
    links = encode_links(g)
    regions = region_texts(g, tiles, links)
    counts = defaultdict(int)
    for k in tiles:
        counts[region_of(k)] += 1
    head = header_text(g, dict(counts))
    sizes = {n: sum(len(t) for t in f.values()) for n, f in regions.items()}
    st = {"cont": cont, "per_tile": per_tile, "cell": round(g.cell, 3), "surfaces": g.n,
          "stacked_cells": int((g.count > 1).sum()), "cells": int((g.count > 0).sum()),
          "road_ground": int(((g.flags & FLAG_ROAD) > 0).sum()), "road_links": len(g.road),
          "swim": int((g.kind == KIND_SWIM).sum()), "implied_pct": round(100 * g.implied_share, 1),
          "one_way": int(getattr(g, "one_way", 0)), "road_links_refused": int(getattr(g, "links_refused", 0)), "header_bytes": len(head), "regions": len(regions),
          "bytes": sum(sizes.values()), "region_bytes_max": max(sizes.values()) if sizes else 0,
          "region_bytes_median": int(np.median(list(sizes.values()))) if sizes else 0}
    log(f"  {st}")
    if write:
        root = addons_root()
        out_path(cont).parent.mkdir(parents=True, exist_ok=True)
        out_path(cont).write_text(head, encoding="utf-8", newline="\n")
        for old in root.glob(f"AzerothGPS_WG{cont}_*"):
            if old.is_dir() and old.name not in regions:
                shutil.rmtree(old)
        for name, files in regions.items():
            (root / name).mkdir(parents=True, exist_ok=True)
            for fn, text in files.items():
                (root / name / fn).write_text(text, encoding="utf-8", newline="\n")
        log(f"wrote {out_path(cont)} and {len(regions)} region folders ({st['bytes'] / 1e6:.2f} MB)")
    return st
