"""Buildings' insides as roads with floors and stairs (addon/AzerothGPS/Data/Indoors.lua).

Asked 2026-10-06 (the user, in Brill: "we need indoor routes in all buildings like cities"): a route to a trainer
upstairs in an inn went to the building and stopped there, with "(upstairs)" said; the player's floor wasn't known,
so the hint stayed once they were up there, and the stairs icon was by the stop. Here each building's walkable faces
(the ones a character stands on, as the caves', the capitals' and the dungeons' are read) are made into a walk
network with walknet, its floors over floors split into layers with layers.py (as a dungeon's), and kept inside the
building: its floors' roads, the stairs between them, and its doors, each door's road on to the land's road. The
addon merges them into the continent's roads (one ns.RoadOverlays entry per continent, Data/Roads.lua's format):
each node's floor height (`nz`: Router.OnFloor puts a stop with a height on its floor's road, and the player's
floor followed along them, Nav.TrackCityZ, puts the start on theirs), stairs as source 6 (Router.StairAt: "Stairs
up", the map's stairs icon on them), doors only for gap links (the rest of the inside isn't linked out through the
walls).

The first step: TOWNS (Brill), every building there with an inside a door leads into. docs/plan.md has the plan for
every building.
"""

from __future__ import annotations

import heapq
import math
from pathlib import Path

import numpy as np

from . import layers, walknet
from .buildings import buildings
from .caves import Ground, pack_points, shipped_roads
from .extract.spike import ClientData
from .paths import ADDON_DIR

FILE = ADDON_DIR / "Data" / "Indoors.lua"
# the towns built: name -> (continent, x, y, radius)
TOWNS = {
    "Brill": (0, 2265.0, 290.0, 120.0),
    # (phase 5, 2026-10-06: the towns whose guards give directions, TownPlaces: the middle of their own places; and the
    # Crossroads, Pois.lua. `agps indoors --check`: 45 of 49 places reached on their floors through the insides)
    "Goldshire": (0, -9456.0, 39.0, 150.0),
    "Kharanos": (0, -5593.0, -527.0, 160.0),
    "Dolanaar": (1, 9819.0, 947.0, 120.0),
    "Bloodhoof Village": (1, -2306.0, -392.0, 140.0),
    "Razor Hill": (1, 322.0, -4764.0, 110.0),
    "The Crossroads": (1, -456.0, -2652.0, 100.0),
}
# (towns being looked at before they're written: built with --town, not by default)
TOWNS_NEXT: dict = {}
FLOOR_SLOPE = 0.64  # a floor's normal at least this upright (as the capitals' and dungeons')
GROUND_PAD = 8.0  # yards of the land round a building walked into (its doors' outsides)
PRUNE = 4.0  # yards: dead-end road stubs shorter than this go
STAIR_SEARCH = 40.0  # yards: the longest way a stair between floors is looked for
SMOOTH = 2.0  # yards: the roads simplified this much on their floors
STAIR_MIN_Z = 3.0  # an edge whose ends are this far apart in height is stairs (as Router.STAIR_MIN_Z)
FLOOR_GAP = 4.0  # node heights this far apart are two floors
DOOR_JOIN_YD = 12.0  # a door this near the land's road: a straight road from it onto that road
WALK_JOIN_YD = 150.0  # one further, up to this: the walk to that road on the terrain, the addon's own (walk_joins)
FAR_WALK_YD = 600.0  # (a door's walk to that road this long at most: Booty Bay's house, 1,500 yd round the bay)
INSIDE_PAD = 1  # cells round the model's floors still inside (a doorstep)
LAYER_REACH = 6.0  # yards: a point's floor, this near the height it's followed at (as cities.py's)
LEDGE = 3.0
CLIMB_SLOPE = 0.25  # a yard along rising or falling this much is on stairs (a ramp's or steps')
CLIMB_JOIN_YD = 2.0  # climbing stretches this near each other are one flight
STEP_CAP = 2.0  # yards: a step on foot between neighboring cells at most (walknet.STEP_CAP; a stair rises a yard a yard)
SPUR_YD = 25.0  # a town place inside: a road from it onto the nearest road on its floor this near (spurs)
SPUR_Z = 3.5  # (that road's height about the place's)
SPUR_FLOOR = 0.85  # (the spur's points over its floor, a yard apart: this share at least, the last 2 yd aside)
# A road on a roof: raised over the ground by RAISED_Z at all its points, nothing of the model over it (COVER_Z) at
# more than COVER_SHARE of them (a chimney): left out. A tent's canvas is walkable and reached up its side, and routes
# to someone in it with no height went up onto it (Bloodhoof Village's huts, 2026-10-06)
RAISED_Z = 2.5
COVER_Z = 1.5
COVER_SHARE = 0.1


def building_faces(cd: ClientData, p) -> tuple[list, list]:
    """A placed building's floors and walls in the world, walknet.build's format."""
    xf = walknet.Placed(p)
    floors, walls, _liquids = walknet.model_faces(cd, p.wmo, FLOOR_SLOPE)
    fl, wl = [], []
    for _gi, _z, tri in floors:
        w3 = [xf(v) for v in tri]
        fl.append(([(q[0], q[1]) for q in w3], [q[2] for q in w3], False, True))
    for _gi, _zr, tri in walls:
        w3 = [xf(v) for v in tri]
        zs = [q[2] for q in w3]
        wl.append(((min(zs), max(zs)), [(q[0], q[1]) for q in w3], zs))
    return fl, wl


def town_places(cont: int) -> list:
    """The towns' places with heights (Data/CityPlaces.lua's TownPlaces): (name, x, y, z)."""
    import re

    text = (ADDON_DIR / "Data" / "CityPlaces.lua").read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r'\{ x = (-?[\d.]+), y = (-?[\d.]+), "([^"]+)", z = (-?[\d.]+)', text):
        out.append((m.group(3), float(m.group(1)), float(m.group(2)), float(m.group(4))))
    return out


def floors_of(zs: list) -> list:
    """The floor heights among the floors' roads' ends `zs`: heights within 1.5 yd of each other one group, a group
    of one between two others (a landing on the stairs) left out, groups under FLOOR_GAP apart one floor."""
    groups = []
    for z in sorted(float(z) for z in zs if z is not None):
        if groups and z - groups[-1][-1] <= 1.5:
            groups[-1].append(z)
        else:
            groups.append([z])
    kept = [g for i, g in enumerate(groups) if len(g) > 1 or i in (0, len(groups) - 1)]
    out = []
    for g in kept:
        mid = sorted(g)[len(g) // 2]
        if out and mid - out[-1] < FLOOR_GAP:
            continue
        out.append(round(mid, 1))
    return out


def road_heights(lay: dict, u: dict, eid, e, pts: list, za: float, zb: float) -> tuple[list, list, list]:
    """A road's points a yard apart (its own kept), each at its floor's height followed from its start (a stair's own
    heights, else its layer's, else the floor nearest the last point's): (points, heights, kept)."""
    u2, f = lay.get("u", u), lay["floors"]
    NB, H, W = f.shape
    Z0 = u2["Z0"]

    def floor_near(x, y, z, reach=LAYER_REACH):
        cx, cy = u2["cellxy"](x, y)
        r, c = int(cy), int(cx)
        best = None
        for rr in range(max(0, r - 1), min(H, r + 2)):
            for cc in range(max(0, c - 1), min(W, c + 2)):
                for b in np.nonzero(f[:, rr, cc])[0]:
                    fz = Z0 + b + 0.5
                    d = abs(fz - z) + (0 if (rr, cc) == (r, c) else 0.5)
                    if d <= reach and (best is None or d < best[0]):
                        best = (d, fz)
        return best[1] if best else None

    ez = lay["edge_z"].get(eid)
    if e.source == "stair" and ez and len(ez) == len(e.pts):
        return list(pts), [za] + list(ez[1:-1]) + [zb], [True] * len(pts)
    dense, kept = [], []
    for i in range(len(pts) - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        n = max(1, int(math.hypot(x2 - x1, y2 - y1)))
        for s_ in range(n):
            dense.append((x1 + (x2 - x1) * s_ / n, y1 + (y2 - y1) * s_ / n))
            kept.append(s_ == 0)
    dense.append(tuple(pts[-1]))
    kept.append(True)
    on = layers.point_heights(lay, u2, eid, dense)
    hs = [za]
    for q, h in zip(dense[1:-1], on[1:-1]):
        if h is None or abs(h - hs[-1]) > LEDGE + 1.0:
            h = floor_near(q[0], q[1], hs[-1], LEDGE + 1.0) or hs[-1]
        hs.append(h)
    hs.append(zb)
    return dense, hs, kept


def climbs(pts: list, hs: list) -> list:
    """The stretches of a road (points and heights) that climb a floor: [(i0, i1)], each rising or falling at least
    STAIR_MIN_Z in all, steps CLIMB_SLOPE steep or more (CLIMB_JOIN_YD apart joined)."""
    runs = []
    for i in range(len(pts) - 1):
        d = math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        if d > 0 and abs(hs[i + 1] - hs[i]) / d >= CLIMB_SLOPE:
            if runs and math.hypot(pts[i][0] - pts[runs[-1][1]][0], pts[i][1] - pts[runs[-1][1]][1]) <= CLIMB_JOIN_YD:
                runs[-1][1] = i + 1
            else:
                runs.append([i, i + 1])
    return [(a, b) for a, b in runs if abs(hs[b] - hs[a]) >= STAIR_MIN_Z]


def build_building(cd: ClientData, p, ground: Ground, places: list, log=print, spurs: bool = True) -> dict | None:
    """One building's inside: {name, uid, nodes [(x, y)], zs, edges [(a, b, pts, src)], doors, floors}, or None
    (no floors, or nothing kept). `spurs`: each place given a road of its own (a town's places); without, the places
    only seed the walk and keep the ways to them over a roof (phase 6's NPCs: no NPC data in the roads)."""
    fl, wl = building_faces(cd, p)
    if not fl:
        return None
    x0, y0, x1, y1 = p.bounds
    inside_places = [q for q in places if x0 <= q[1] <= x1 and y0 <= q[2] <= y1]
    seeds = [(x, y, z) for _n, x, y, z in inside_places]

    def gnd(X, Y):
        h, ok = ground.sample(X, Y)
        X, Y = np.asarray(X, float), np.asarray(Y, float)
        near = (X >= x0 - GROUND_PAD) & (X <= x1 + GROUND_PAD) & (Y >= y0 - GROUND_PAD) & (Y <= y1 + GROUND_PAD)
        return h, ok & near

    name = (cd.name(p.wmo) or str(p.wmo)).split("/")[-1].removesuffix(".wmo")
    silent = lambda *a: None  # noqa: E731
    # (steps on foot of at most STEP_CAP, a diagonal's too, as Undercity's: a stair landing's side 4 yd over the passage
    # was one diagonal step under LEDGE's, and the stairs road went up it, issue #842)
    cap, walknet.STEP_CAP = walknet.STEP_CAP, STEP_CAP
    try:
        u = walknet.build(fl, wl, [], label=name, ground=gnd, ground_reach=GROUND_PAD + 2, prune=PRUNE, fill=0,
                          top_reached=True, road_pieces=True, seeds=seeds or None, stair_max=STAIR_SEARCH, log=silent)
        lay = layers.build(u, seeds, prune=PRUNE, fill=0, log=silent, step_lip=True)
    finally:
        walknet.STEP_CAP = cap
    nodes, edges, _drops, zs = layers.roads(lay, u, SMOOTH)
    if not edges:
        return None
    from scipy import ndimage

    model = ndimage.binary_dilation(u["model"], iterations=INSIDE_PAD)
    H, W = model.shape
    # (the model's faces over each point: a roof's road has none, RAISED_Z over the ground)
    from .roads.recorded import Faces

    tris = [[(q[0], q[1], z) for q, z in zip(f[0], f[1])] for f in fl] +         [[(q[0], q[1], z) for q, z in zip(w[1], w[2])] for w in wl]
    cover = Faces(np.array(tris, float), touch=0.0) if tris else None
    roof_ids = set()  # (the pieces on a roof, by their point lists)

    def roof(pts, hs) -> bool:
        if cover is None or not pts:
            return False
        X, Y, Hs = (np.array([q[0] for q in pts], float), np.array([q[1] for q in pts], float),
                    np.array(hs, float))
        g, _ok = ground.sample(X, Y)
        if not (np.all(np.isfinite(g)) and np.all(Hs > g + RAISED_Z)):
            return False
        pi, z = cover.heights(X, Y)
        over = np.zeros(len(pts), bool)
        np.logical_or.at(over, pi, z > Hs[pi] + COVER_Z)
        return bool(over.mean() <= COVER_SHARE)

    def inside(x, y):
        r, c = u["world_to_px"](x, y)
        return 0 <= r < H and 0 <= c < W and bool(model[r, c])

    # the inside: each road's points in the building, a road crossing out of it cut just past its last point in
    # (the doorstep, a door); roads all outside it (the land round it) left out
    out_nodes, out_zs, out_edges, doors = [], [], [], []
    index = {}

    def node(key, xy, z):
        if key not in index:
            index[key] = len(out_nodes)
            out_nodes.append((float(xy[0]), float(xy[1])))
            out_zs.append(z)
        return index[key]

    for (a, b, pts), (eid, e) in zip(edges, lay["graph"].edges.items()):
        full = [tuple(nodes[a])] + [tuple(q[:2]) for q in pts[1:-1]] + [tuple(nodes[b])]
        dense, hs, kept = road_heights(lay, u, eid, e, full, zs[a], zs[b])
        ins = [inside(*q) for q in dense]
        if not any(ins):
            continue
        # (a road into the building kept whole, its end outside a door: cut at the doorstep, two roads meeting just
        # outside it were two ends, and the inside came apart from its door, 2026-10-06)
        lo, hi = 0, len(dense) - 1
        # (cut where it climbs a floor: the stairs a road of their own, source 6, between nodes at their ends)
        cuts = {lo, hi}
        runs = [(max(lo, s0), min(hi, s1)) for s0, s1 in climbs(dense, hs) if s1 > lo and s0 < hi]
        for s0, s1 in runs:
            cuts |= {s0, s1}
        cuts = sorted(cuts)
        for k in range(len(cuts) - 1):
            i, j = cuts[k], cuts[k + 1]
            if j <= i:
                continue
            piece = [dense[t] for t in range(i, j + 1) if t in (i, j) or kept[t]]
            key_a = ("n", a) if i == 0 else ("c", eid, i)
            key_b = ("n", b) if j == len(dense) - 1 else ("c", eid, j)
            na, nb = node(key_a, dense[i], hs[i]), node(key_b, dense[j], hs[j])
            if na == nb:
                continue
            # (and any piece whose ends are a floor apart: a climb too gentle for `climbs` is still stairs)
            stair = any(s0 <= i and j <= s1 for s0, s1 in runs) or abs(hs[i] - hs[j]) >= STAIR_MIN_Z
            out_edges.append((na, nb, piece, 6 if stair else 0))
            if roof(dense[i:j + 1], hs[i:j + 1]):
                roof_ids.add(id(piece))
    # (the doors: the roads' ends outside the building)
    doors = [i for i, (x, y) in enumerate(out_nodes) if not inside(x, y)]
    door_set = set(doors)

    def reached_only(edges, what):
        """(road pieces no door reaches (a roof, a ledge, floors over floors the walk didn't join): left out, a route
        couldn't get there)"""
        parent = list(range(len(out_nodes)))

        def root(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for a, c, _p, _s in edges:
            parent[root(a)] = root(c)
        reached = {root(d) for d in doors}
        kept = [e for e in edges if root(e[0]) in reached]
        if len(kept) < len(edges):
            log(f"    {name}: {len(edges) - len(kept)} roads {what} left out")
        return kept
    out_edges = reached_only(out_edges, "no door reaches")
    # (each town place inside: a short road from it onto the nearest road on its floor, over that floor (walknet's
    # floor_at along it; the last yards by the NPC aside, a counter): the route ends at the NPC, not a walk from the
    # nearest road, 16 yd at Goldshire's trainers, 2026-10-06)
    used = {v for e in out_edges for v in e[:2]}
    floor_at = u.get("floor_at")
    spurred = []  # (the places a road leads to: a spur, or a road there already)
    place_nodes = set()
    for pname, qx, qy, qz in inside_places:
        if not inside(qx, qy):
            log(f"    {name}: no spur for {pname}: outside its walls")
            continue
        best, why = None, "no road on its floor within SPUR_YD"
        for i in used:
            nx, ny = out_nodes[i]
            nz = out_zs[i]
            if nz is None or abs(nz - qz) > SPUR_Z:
                continue
            d = math.hypot(nx - qx, ny - qy)
            if d > SPUR_YD or (best and d >= best[0]):
                continue
            if d >= 1.0 and floor_at is not None:
                k_n = max(0, int(d) - 2)
                on = sum(1 for k in range(k_n) if floor_at(nx + (qx - nx) * k / d, ny + (qy - ny) * k / d, qz))
                if k_n > 0 and on < SPUR_FLOOR * k_n:
                    why = f"the way from the road {d:.0f} yd off isn't over its floor ({on} of {k_n} yd)"
                    continue
            best = (d, i)
        if not best:
            log(f"    {name}: no spur for {pname} (z {qz:.1f}): {why}")
            continue
        if not spurs:  # (its way kept over a roof, no road of its own)
            place_nodes.add(best[1])
            continue
        spurred.append(pname)
        if best[0] >= 1.0:
            j = len(out_nodes)
            out_nodes.append((float(qx), float(qy)))
            out_zs.append(float(qz))
            out_edges.append((best[1], j, [out_nodes[best[1]], (float(qx), float(qy))], 0))
            place_nodes.add(j)
        else:
            place_nodes.add(best[1])
    # (the ways from the doors to the places stay, over a roof too: Razor Hill's Rogue trainer up on the troll burrow's
    # terrace; the rest of a roof goes)
    adj: dict = {}
    for a, c, pts, _s in out_edges:
        L = sum(math.dist(pts[k], pts[k + 1]) for k in range(len(pts) - 1))
        adj.setdefault(a, []).append((c, L, id(pts)))
        adj.setdefault(c, []).append((a, L, id(pts)))
    dist, prev = {d: 0.0 for d in doors}, {}
    heap = [(0.0, d) for d in doors]
    heapq.heapify(heap)
    while heap:
        du, v = heapq.heappop(heap)
        if du > dist.get(v, math.inf):
            continue
        for w, L, k in adj.get(v, ()):
            if du + L < dist.get(w, math.inf):
                dist[w], prev[w] = du + L, (v, k)
                heapq.heappush(heap, (du + L, w))
    needed = set()
    for v in place_nodes:
        while v in prev:
            v, k = prev[v]
            needed.add(k)
    before = len(out_edges)
    out_edges = [e for e in out_edges if id(e[2]) not in roof_ids or id(e[2]) in needed]
    if len(out_edges) < before:
        log(f"    {name}: {before - len(out_edges)} roads on its roof left out")
    # (and what's left of a roof: a dead end up to a spot raised over the ground with nothing over it, again and again
    # (the stairs up to it too); a room upstairs under the roof stays, a way to nowhere on top doesn't, a place's does)
    trimmed = 0
    while True:
        deg: dict = {}
        for a_, c_, _p, _s in out_edges:
            deg[a_], deg[c_] = deg.get(a_, 0) + 1, deg.get(c_, 0) + 1
        leaves = {v for v, d in deg.items() if d == 1 and v not in door_set and v not in place_nodes
                  and out_zs[v] is not None and roof([out_nodes[v]], [out_zs[v]])}
        if not leaves:
            break
        before = len(out_edges)
        out_edges = [e for e in out_edges if e[0] not in leaves and e[1] not in leaves]
        trimmed += before - len(out_edges)
    if trimmed:
        log(f"    {name}: {trimmed} roads up onto its roof left out")
    out_edges = reached_only(out_edges, "cut off with the roof")
    floors = floors_of([out_zs[i] for a, b, _p, src in out_edges if src == 0 for i in (a, b)])
    stairs = sum(1 for e in out_edges if e[3] == 6)
    # (every building with an inside a door leads into: one floor too, a stop inside is reached by its door, not
    # through its wall; asked 2026-10-06, "indoor routes in all buildings")
    if not out_edges or not doors:
        return None
    return {"name": name, "uid": p.uid, "bounds": p.bounds, "nodes": out_nodes, "zs": out_zs, "edges": out_edges,
            "doors": sorted(set(doors)), "floors": floors, "stairs": stairs,
            "places": [q[0] for q in inside_places if inside(q[1], q[2])], "spurred": spurred}


# Phase 6 (asked 2026-10-06: "go ahead, merged and pruned"): every building with an NPC upstairs or in a cellar (the
# server data's NPCs, `agps floors`' report: offline only, to pick the buildings and to check the routes; no NPC data
# ships, "keep NPC data out of the shipped addon"). Their insides pruned by the buildings alone: kept, the ways in from
# the doors joined to the land's road that bring every part of every road within COVER_YD of a kept one along the roads,
# then chains of short pieces one road each. No spurs to the NPCs: their stops' heights are learned in game (Layers'
# NPC floors).
COVER_YD = 6.0
COVER_STEP = 2.0  # yards: the points along each road that must be covered (not only its nodes)
CHAIN_DZ = 0.5  # yards: a node left out of a chain only where the road's height there is its ends' in between, this near
NPC_PLACE_MAX_YD = 400.0  # (a building's name: the map's town or place nearest it, as the floors report's)
JOIN_SPREAD_YD = 20.0  # yards: a building's doors joined to the land's road at least this far apart (spread_joins)


def _road_points(pts: list, step: float):
    """Points along a road every `step` yards, both ends included: [(yards along, x, y)]."""
    out = [(0.0, float(pts[0][0]), float(pts[0][1]))]
    acc = 0.0
    nxt = step
    for p, q in zip(pts, pts[1:]):
        seg = math.dist(p, q)
        while seg > 0 and nxt < acc + seg:
            f = (nxt - acc) / seg
            out.append((nxt, p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f))
            nxt += step
        acc += seg
    if acc > out[-1][0]:
        out.append((acc, float(pts[-1][0]), float(pts[-1][1])))
    return out


def prune_cover(b: dict, cover_yd: float = COVER_YD) -> int:
    """Building `b`'s roads cut down to the ways in that bring every part of every road within `cover_yd` of a kept
    road, along the roads (not across a wall or between floors: a room's NPC is then near a road in that room; the
    points every COVER_STEP along them, not only where roads meet: an NPC stands anywhere along a corridor), the
    farthest first: each a road kept whole with its shortest way from the doors joined to the land's road (`joins`; a
    part none of them leads to is left out). Every joined door kept with its way onto those, and the joins. Returns how
    many roads were left out."""
    edges = b["edges"]
    if not edges:
        return 0
    joins = set(b.get("joins", ()))
    adj: dict = {}
    lengths = []
    for k, (a, c, pts, _s) in enumerate(edges):
        L = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        lengths.append(L)
        adj.setdefault(a, []).append((c, L, k))
        adj.setdefault(c, []).append((a, L, k))

    def dijkstra(sources):
        dist, prev = {s: 0.0 for s in sources}, {}
        heap = [(0.0, s) for s in sources]
        heapq.heapify(heap)
        while heap:
            du, v = heapq.heappop(heap)
            if du > dist.get(v, math.inf):
                continue
            for w, L, k in adj.get(v, ()):
                if du + L < dist.get(w, math.inf):
                    dist[w], prev[w] = du + L, (v, k)
                    heapq.heappush(heap, (du + L, w))
        return dist, prev

    # (the ways in: the doors joined to the land's road. A piece of the inside none of them is on is left out: no gap
    # link reaches a phase 6 building's doors, and a route couldn't get there)
    joined = {e[0] for e in edges if e[1] in joins} | {e[1] for e in edges if e[0] in joins}
    dist, prev = dijkstra(sorted(joined))

    kept: set = set()
    nd: dict = {}  # (each node's yards along the roads to the nearest kept road, up to cover_yd)
    heap: list = []

    def add_road(k):
        if k in kept:
            return
        kept.add(k)
        for v in edges[k][:2]:
            if nd.get(v, math.inf) > 0:
                nd[v] = 0.0
                heapq.heappush(heap, (0.0, v))
        while heap:
            du, v = heapq.heappop(heap)
            if du > nd.get(v, math.inf):
                continue
            for w, L, _k in adj.get(v, ()):
                if du + L <= cover_yd and du + L < nd.get(w, math.inf):
                    nd[w] = du + L
                    heapq.heappush(heap, (du + L, w))

    def keep_path(v):
        while v in prev:
            u, k = prev[v]
            add_road(k)
            v = u
    samples = []  # (how far in from the ways in, road, yards along it, its end on the way in)
    for k, (a, c, pts, _s) in enumerate(edges):
        if a in joins or c in joins:
            continue  # (a join: outside, kept below)
        da, dc = dist.get(a, math.inf), dist.get(c, math.inf)
        if da == math.inf and dc == math.inf:
            continue
        for t, _x, _y in _road_points(pts, COVER_STEP):
            via_a, via_c = da + t, dc + lengths[k] - t
            samples.append((min(via_a, via_c), k, t, a if via_a <= via_c else c))
    samples.sort(key=lambda s: -s[0])
    for _d, k, t, end in samples:
        a, c = edges[k][0], edges[k][1]
        # (covered: a kept road within cover_yd along the roads, not across a wall or a floor)
        if k in kept or min(nd.get(a, math.inf) + t, nd.get(c, math.inf) + lengths[k] - t) <= cover_yd:
            continue
        add_road(k)
        keep_path(end)
    # (each joined door: its way onto what's kept, a door is a way in; and the joins themselves, always)
    on = {v for k in kept for v in edges[k][:2]}
    for d in sorted(joined):
        if d in on or d not in adj:
            continue
        dd, pp = dijkstra([d])
        target = min((u for u in on if u in dd), key=lambda u: dd[u], default=None)
        v = target
        while v is not None and v in pp:
            u, k = pp[v]
            add_road(k)
            v = u
        on = {v for k in kept for v in edges[k][:2]}
    for k, e in enumerate(edges):
        if e[0] in joins or e[1] in joins:
            kept.add(k)
    before = len(edges)
    b["edges"] = [e for k, e in enumerate(edges) if k in kept]
    return before - len(b["edges"])


def spread_joins(b: dict, spread_yd: float = JOIN_SPREAD_YD) -> int:
    """Building `b`'s doors joined to the land's road thinned to ways in at least `spread_yd` apart, the shortest join
    first: of a few doors side by side one is way enough, and each join costs the routing graph a road and a land road
    split (phase 6's 551 joins were 2 MB of its 9.5; Menethil's barracks had 20, 2026-10-06). Each piece of the inside
    keeps its shortest join whatever: Darkshire's town hall's dais, a piece of its own, lost its only one and its NPC's
    route ended 16 yd off. Returns how many joins were left out."""
    joins = list(b.get("joins", ()))
    if len(joins) <= 1:
        return 0
    js = set(joins)
    parent: dict = {}

    def root(v):
        parent.setdefault(v, v)
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v
    by_join = {}
    for a, c, pts, _s in b["edges"]:
        L = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        if c in js:
            by_join[c] = (a, L)
        elif a in js:
            by_join[a] = (c, L)
        else:
            parent[root(a)] = root(c)  # (the pieces of the inside, its joins aside)
    order = sorted((j for j in joins if j in by_join), key=lambda j: by_join[j][1])
    kept, pieces = [], set()
    for j in order:  # (each piece's shortest)
        piece = root(by_join[j][0])
        if piece not in pieces:
            pieces.add(piece)
            kept.append(j)
    for j in order:  # (then the rest, spread out)
        d = by_join[j][0]
        if j not in kept and all(math.dist(b["nodes"][d], b["nodes"][by_join[k][0]]) >= spread_yd for k in kept):
            kept.append(j)
    drop = js - set(kept)
    b["edges"] = [e for e in b["edges"] if e[0] not in drop and e[1] not in drop]
    b["joins"] = [j for j in joins if j in set(kept)]
    return len(drop)


def collapse_chains(b: dict) -> int:
    """Chains of roads through nodes where only two meet (not a door, a join, nor where stairs begin or end) as one
    road each, its points end to end: the graph's cost is mostly per road. A node stays where the road's height isn't
    its ends' in between (CHAIN_DZ): the game reads a road's floor along it from its ends' (Router.RoadFloor), and a
    corridor merged into its ramp up was a floor between the two (Stonard's great hall, 2026-10-06). Returns how many
    roads fewer."""
    edges, zs = b["edges"], b["zs"]
    keep_nodes = set(b["doors"]) | set(b.get("joins", ()))
    inc: dict = {}
    for k, (a, c, _p, _s) in enumerate(edges):
        inc.setdefault(a, []).append(k)
        inc.setdefault(c, []).append(k)
    through = {v for v, ks in inc.items() if len(ks) == 2 and ks[0] != ks[1] and v not in keep_nodes
               and edges[ks[0]][3] == edges[ks[1]][3] and zs[v] is not None}
    used: set = set()
    out = []

    def oriented(k, v):
        """Road k's points from its end at node v, and the node at its other end."""
        a, c, p, _s = edges[k]
        return (list(p), c) if a == v else (list(reversed(p)), a)

    def walk(v, cur):
        """From node v (road `cur` behind), on along the chain: [(road's points away from v, the node it ends at)]."""
        seq = []
        while v in through:
            nxt = [kk for kk in inc[v] if kk != cur and kk not in used]
            if not nxt:
                break
            cur = nxt[0]
            used.add(cur)
            pts, v = oriented(cur, v)
            seq.append((pts, v))
        return seq

    for k, (a, c, pts, s) in enumerate(edges):
        if k in used:
            continue
        used.add(k)
        fwd = walk(c, k)
        back = walk(a, k)
        # the chain's nodes and roads in order: from the far end behind a, through a and c, to the far end past c
        steps = [(list(reversed(p)), None) for p, _v in reversed(back)]
        starts = [v for _p, v in reversed(back)] + [a]
        seq_nodes = starts + [c] + [v for _p, v in fwd]
        seq_pts = [p for p, _v in steps] + [list(pts)] + [p for p, _v in fwd]
        # (cut where the heights aren't in line: each piece's inner nodes within CHAIN_DZ of its ends' line)
        lens = [sum(math.dist(p[i], p[i + 1]) for i in range(len(p) - 1)) for p in seq_pts]
        i = 0
        while i < len(seq_pts):
            j = i + 1  # (the piece: roads i .. j-1, from node seq_nodes[i] to seq_nodes[j])
            while j < len(seq_pts):
                z0, z1 = zs[seq_nodes[i]], zs[seq_nodes[j + 1]]
                total = sum(lens[i:j + 1])
                ok = z0 is not None and z1 is not None
                acc = 0.0
                for m in range(i + 1, j + 1):
                    acc += lens[m - 1]
                    zm = zs[seq_nodes[m]]
                    if not ok or zm is None or abs(zm - (z0 + (z1 - z0) * acc / max(total, 1e-9))) > CHAIN_DZ:
                        ok = False
                        break
                if not ok:
                    break
                j += 1
            P: list = []
            for p in seq_pts[i:j]:
                for q in p:
                    if not P or P[-1] != q:
                        P.append(q)
            out.append((seq_nodes[i], seq_nodes[j], P, s))
            i = j
    fewer = len(edges) - len(out)
    b["edges"] = out
    return fewer


def compact(b: dict) -> None:
    """Building `b`'s nodes renumbered to those its roads, doors and joins use (the rest left out of the data)."""
    used = sorted({v for e in b["edges"] for v in e[:2]})
    index = {v: i for i, v in enumerate(used)}
    b["nodes"] = [b["nodes"][v] for v in used]
    b["zs"] = [b["zs"][v] for v in used]
    b["edges"] = [(index[a], index[c], pts, s) for a, c, pts, s in b["edges"]]
    b["doors"] = sorted(index[d] for d in b["doors"] if d in index)
    b["joins"] = [index[j] for j in b.get("joins", ()) if j in index]


def npc_buildings(cd: ClientData, log=print) -> dict:
    """The buildings with an NPC upstairs or in a cellar, from `agps floors`' report (data/debug/floors/floors.json,
    made when it's missing): { cont: { placement uid: [(name, x, y, z, place), ...] } }. Offline only."""
    from . import floors as F
    from .paths import data_dir

    DATA = data_dir()
    path = DATA / "debug" / "floors" / "floors.json"
    if not path.exists():
        log("  the floors report first (agps floors)")
        F.report(F.classify(cd, F.load(DATA)), path.parent)
    import json

    out: dict = {}
    for n in json.loads(path.read_text(encoding="utf-8"))["npcs"]:
        if n.get("kind") in ("up", "down") and n.get("building"):
            out.setdefault(n["cont"], {}).setdefault(n["building"], []).append(
                (n["name"], n["x"], n["y"], n["z"], n.get("place")))
    return out


# Phase 7 (asked 2026-11-21: "if routing to an NPC in the building you just get a dotted line to it through walls, not
# directions to go around to the entrance then inside"): every building with a shipped NPC (Data/Npcs.lua, since
# 2026-11-14) standing inside it where Data/Buildings.lua blocks the ground, built as phase 6's (no spurs, pruned). Its
# NPC within NPC_IN_YD of the building's footprint (buildings.footprint: its walls, doorways closed, the inside filled)
# and on one of its blocked cells: an NPC by a hut too small to block a cell is walked to over the land as ever.
NPC_IN_YD = 1
SHIPPED = "Npcs.lua"  # (phase 7's NPCs' fifth value, where phase 6's has the floors report's place)


def shipped_spawns(path: Path | None = None) -> list:
    """Data/Npcs.lua's spawns on the continents (0 and 1; not Undercity's): [(name, cont, x, y, z), ...]."""
    text = (path or ADDON_DIR / "Data" / "Npcs.lua").read_text(encoding="utf-8")
    body = text.split("ns.NpcsPacked = [==[", 1)[1].split("]==]", 1)[0]
    out = []
    for line in body.strip().splitlines():
        f = line.split("|")
        if len(f) < 7:
            continue
        for s_ in f[6].split(";"):
            q = s_.split()
            if len(q) == 4 and q[0] in ("0", "1"):
                out.append((f[1], int(q[0]), float(q[1]), float(q[2]), float(q[3])))
    return out


def blocked_building_cells(path: Path | None = None) -> dict:
    """Data/Buildings.lua's blocked cells: { cont: {row * 65536 + col} }."""
    import re

    text = (path or ADDON_DIR / "Data" / "Buildings.lua").read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"\[(\d+)\] = \{([^}]*)\}", text):
        vals = [int(v) for v in re.findall(r"-?\d+", m.group(2))]
        cells = set()
        for i in range(0, len(vals) - 2, 3):
            r, c, n = vals[i:i + 3]
            cells.update(r * 65536 + c + k for k in range(n))
        out[int(m.group(1))] = cells
    return out


def shipped_npc_buildings(cd: ClientData, log=print) -> dict:
    """Phase 7's buildings: those with a shipped NPC standing inside on a blocked cell (NPC_IN_YD of the footprint),
    { cont: { placement uid: [(name, x, y, z, SHIPPED), ...] } }, as npc_buildings'. Capitals' and caves' models aren't
    buildings (buildings.buildings); an NPC over a capital's or a cave's own grid is left out (its own roads)."""
    from . import buildings as BL
    from .gameharness import start

    _lua, ns = start()
    P = ns.Passability

    def own_grid(cont, x, y):
        r = P.OverlayRaw(cont, x, y)
        v, grid = r if isinstance(r, tuple) else (r, None)
        return v is not None and grid is not None and bool(grid.cave or grid.capital)
    frames = BL.grid_frames()
    cells = blocked_building_cells()
    spawns = shipped_spawns()
    out: dict = {}
    for cont in (0, 1):
        mine = [q for q in spawns if q[1] == cont]
        if not mine or cont not in frames:
            continue
        X = np.array([q[2] for q in mine])
        Y = np.array([q[3] for q in mine])
        rr, cc = BL.to_cell(frames[cont], X, Y)
        on = [i for i, k in enumerate((rr * 65536 + cc).tolist()) if k in cells.get(cont, ())
              and not own_grid(cont, mine[i][2], mine[i][3])]
        ground = Ground(cd, cont)
        taken: set = set()
        for p in BL.buildings(cd, cont):
            x0, y0, x1, y1 = p.bounds
            hit = [i for i in on if i not in taken and x0 - NPC_IN_YD <= X[i] <= x1 + NPC_IN_YD
                   and y0 - NPC_IN_YD <= Y[i] <= y1 + NPC_IN_YD]
            if not hit:
                continue
            fp = BL.footprint(BL.cut(cd, p, ground))
            if fp is None:
                continue
            fx, fy, m = fp
            inside = []
            for i in hit:
                a, b = int(X[i] - fx), int(Y[i] - fy)
                if m[max(0, a - NPC_IN_YD):max(0, a + NPC_IN_YD + 1), max(0, b - NPC_IN_YD):max(0, b + NPC_IN_YD + 1)].any():
                    inside.append(i)
            if not inside:
                continue
            taken.update(inside)
            seen = set()
            for i in inside:
                name, _c, x, y, z = mine[i]
                if (name, round(x), round(y)) not in seen:
                    seen.add((name, round(x), round(y)))
                    out.setdefault(cont, {}).setdefault(p.uid, []).append((name, x, y, z, SHIPPED))
        log(f"  [{cont}] {len(out.get(cont, {}))} buildings with a shipped NPC inside ({len(taken)} spawns)")
    return out


def all_npc_buildings(cd: ClientData, log=print) -> dict:
    """Phase 6's buildings (an NPC upstairs or in a cellar, npc_buildings) and phase 7's (a shipped NPC inside,
    shipped_npc_buildings), each building's NPCs both lists' (the same spot once)."""
    out: dict = {}
    for src in (npc_buildings(cd, log), shipped_npc_buildings(cd, log)):
        for cont, by_uid in src.items():
            for uid, npcs in by_uid.items():
                have = out.setdefault(cont, {}).setdefault(uid, [])
                for q in npcs:
                    if not any(o[0] == q[0] and math.hypot(o[1] - q[1], o[2] - q[2]) < 2 for o in have):
                        have.append(q)
    return out


def npc_insides(cd: ClientData, log=print, by_cont: dict | None = None, skip=()) -> list:
    """Phase 6's and 7's buildings as built, before the pruning: every building with an NPC upstairs or in a cellar or
    a shipped NPC inside (`by_cont`, else all_npc_buildings), but those in TOWNS (built whole) and those whose middle is
    within 3 yd of one in `skip` ((cont, x, y): ones built already), each inside built (its NPCs as the walk's seeds
    only, no spurs) and joined onto the land's road (join_doors, then walk_joins: the ways in known before the pruning).
    Each with `npcs` for the check."""
    from .townplaces import _labels

    labels = _labels("23")  # (the map's town and place names: the building's, the nearest within NPC_PLACE_MAX_YD)
    built = []
    for cont, by_uid in sorted((all_npc_buildings(cd, log) if by_cont is None else by_cont).items()):
        ground = Ground(cd, cont)
        roads = shipped_roads(cont)
        placed = {p.uid: p for p in buildings(cd, cont)}
        towns = [(X, Y, R) for c, X, Y, R in TOWNS.values() if c == cont]
        for uid, npcs in sorted(by_uid.items()):
            p = placed.get(uid)
            if p is None:
                continue  # (a capital's, a cave's, a model too big to be a building)
            x0, y0, x1, y1 = p.bounds
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            if any(math.hypot(mx - X, my - Y) <= R for X, Y, R in towns):
                continue  # (a town's: built whole with it)
            if any(c == cont and math.hypot(mx - X, my - Y) <= 3 for c, X, Y in skip):
                continue  # (built already: the shipped file's, spliced onto)
            try:
                b = build_building(cd, p, ground, [q[:4] for q in npcs], log=lambda *a: None, spurs=False)
            except Exception as ex:  # (a model this reader can't take)
                log(f"  building {uid}: unreadable ({ex!r})")
                continue
            if b is None:
                continue
            join_doors(b, roads)
            near = min(((math.hypot(lx - mx, ly - my), name) for lx, ly, name in labels.get(cont, ())), default=None)
            b["town"] = near[1] if near and near[0] <= NPC_PLACE_MAX_YD else "the wilds"
            b["cont"], b["npcs"] = cont, [q[:4] for q in npcs]
            built.append(b)
    walk_joins(built, log, longest=FAR_WALK_YD)  # (no walk far round to a road)
    for b in built:
        b["walked"] = True  # (walk_joins again leaves it be)
    return built


STAIR_STEEP = 1.6  # yards up a yard of road: no stair is that steep (test_indoors_stairs.py's STEEP)
STAIR_RISE = 2.0  # (and at least this much in all)


def steep_stairs(b: dict) -> int:
    """How many of building `b`'s stairs roads (source 6) rise more than STAIR_STEEP a yard, STAIR_RISE at least."""
    n = 0
    for a, c, pts, src in b["edges"]:
        za, zc = b["zs"][a], b["zs"][c]
        if src != 6 or za is None or zc is None:
            continue
        d = max(math.dist(b["nodes"][a], b["nodes"][c]),
                sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)))
        if abs(zc - za) >= STAIR_RISE and abs(zc - za) / max(d, 0.1) > STAIR_STEEP:
            n += 1
    return n


def build_npc_buildings(cd: ClientData, log=print, built: list | None = None, skip=()) -> list:
    """Phase 6: npc_insides (or `built`, those), each with its ways in spread out (spread_joins), pruned (prune_cover)
    and its chains one road each (collapse_chains). One with no door joined to the land's road is left out: a route couldn't get in, and went
    straight to the NPC over everything (Sen'jin Village's huts, 260 yd from a road; 2026-10-06)."""
    out = []
    for b in npc_insides(cd, log, skip=skip) if built is None else built:
        if not b["joins"]:
            log(f"  {b['town']}: {b['name']} ({b['uid']}): left out, no door joined to the land's road")
            continue
        before = len(b["edges"])
        thinned = spread_joins(b)
        pruned = prune_cover(b)
        fewer = collapse_chains(b)
        compact(b)
        if not b["edges"] or not b["doors"]:
            continue
        steep = steep_stairs(b)
        if steep:  # (a ledge, not a stair: the walk up it fails in game, #842; none added, test_indoors_stairs.py)
            log(f"  {b['town']}: {b['name']} ({b['uid']}): left out, {steep} stairs roads steeper than a stair")
            continue
        b["bridge"] = []  # (no gap links: in by its joins, indoors_lua)
        log(f"  {b['town']}: {b['name']} ({b['uid']}): floors {b['floors']}, {before} roads, {thinned} joins thinned, "
            f"{pruned} pruned, {fewer} joined into chains: {len(b['edges'])} left, {len(b['joins'])} ways in")
        out.append(b)
    return out


def road_segments(roads):
    """The land's roads (caves.shipped_roads) as segments: arrays A, B of their ends."""
    segs = []
    for e in (roads.edges.values() if isinstance(roads.edges, dict) else roads.edges):
        P = [(float(q[0]), float(q[1])) for q in e.pts]
        segs += list(zip(P, P[1:]))
    if not segs:
        return None, None
    return np.array([s_[0] for s_ in segs]), np.array([s_[1] for s_ in segs])


def nearest_road(A, B, x, y):
    """The land's road nearest (x, y): its point there and how far, or None."""
    if A is None:
        return None
    V = B - A
    L2 = np.maximum((V ** 2).sum(1), 1e-9)
    t = np.clip(((x - A[:, 0]) * V[:, 0] + (y - A[:, 1]) * V[:, 1]) / L2, 0, 1)
    Q = A + V * t[:, None]
    dist = np.hypot(Q[:, 0] - x, Q[:, 1] - y)
    k = int(np.argmin(dist))
    return float(Q[k, 0]), float(Q[k, 1]), float(dist[k])


def join_doors(b: dict, roads, ground=None, others=()) -> int:
    """Each door within DOOR_JOIN_YD of the land's road: a straight road from it onto the road's nearest point (a node
    there, which the addon's JoinOnto splits the road at). The rest: walk_joins. Returns how many were joined."""
    pts = [(float(q[0]), float(q[1])) for e in (roads.edges.values() if isinstance(roads.edges, dict) else roads.edges)
           for q in e.pts]
    segs = []
    for e in (roads.edges.values() if isinstance(roads.edges, dict) else roads.edges):
        P = [(float(q[0]), float(q[1])) for q in e.pts]
        segs += list(zip(P, P[1:]))
    if not segs or not pts:
        b["joins"] = []
        return 0
    A = np.array([s[0] for s in segs])
    B = np.array([s[1] for s in segs])
    joins, n = [], 0
    for d in b["doors"]:
        x, y = b["nodes"][d]
        V = B - A
        L2 = np.maximum((V ** 2).sum(1), 1e-9)
        t = np.clip(((x - A[:, 0]) * V[:, 0] + (y - A[:, 1]) * V[:, 1]) / L2, 0, 1)
        Q = A + V * t[:, None]
        dist = np.hypot(Q[:, 0] - x, Q[:, 1] - y)
        k = int(np.argmin(dist))
        if dist[k] > DOOR_JOIN_YD:
            continue
        qx, qy = float(Q[k, 0]), float(Q[k, 1])
        j = len(b["nodes"])
        b["nodes"].append((qx, qy))
        b["zs"].append(None)
        b["edges"].append((d, j, [(x, y), (qx, qy)], 0))
        joins.append(j)
        n += 1
    b["joins"] = joins
    return n


def walk_joins(built: list, log=print, reach: float = WALK_JOIN_YD, longest: float | None = None) -> int:
    """The doors no short straight road joined (join_doors), each walked on the terrain to the land's road nearest it
    within `reach` (WALK_JOIN_YD): the addon's own walk search (Passability.FindPath in the game harness: round the buildings'
    cells and the cliffs), the walk a road from the door onto that road (a node there). A building with a door joined
    so isn't walked from again. Returns how many were joined."""
    from .gameharness import start

    if not built:
        return 0
    lua, ns = start()
    P = ns.Passability
    segs = {}
    n = 0
    for b in built:
        if b.get("walked"):
            continue  # (phase 6's: walked before its pruning)
        cont = b["cont"]
        if cont not in segs:
            segs[cont] = road_segments(shipped_roads(cont))
        A, B = segs[cont]
        joined = {e[0] for e in b["edges"] if e[1] in set(b["joins"])}
        tried = []
        for d in b["doors"]:
            if d in joined:
                continue
            x, y = b["nodes"][d]
            near = nearest_road(A, B, x, y)
            if not near or near[2] > reach:
                continue
            tried.append((near[2], d, x, y, near[0], near[1]))
        for _dist, d, x, y, qx, qy in sorted(tried):
            res = P.FindPath(cont, x, y, qx, qy)
            if not isinstance(res, tuple) or not res[0] or not res[1]:  # (no way there: nil alone)
                continue
            cost, path = res[0], res[1]
            pts = [(float(path[i]), float(path[i + 1])) for i in range(1, len(path), 2)]
            if len(pts) < 2:
                continue
            if longest and sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) > longest:
                continue  # (a walk far round, FAR_WALK_YD)
            pts[0], pts[-1] = (x, y), (qx, qy)
            j = len(b["nodes"])
            b["nodes"].append((qx, qy))
            b["zs"].append(None)
            b["edges"].append((d, j, pts, 0))
            b["joins"].append(j)
            n += 1
        if tried:
            log(f"  {b['town']}: {b['name']}: {sum(1 for t in tried if any(e[0] == t[1] for e in b['edges'] if e[1] in b['joins']))}"
                f" of {len(tried)} doors walked to the road")
    return n


def build_town(cd: ClientData, town: str, log=print) -> list:
    """A town's buildings' insides (TOWNS[town], or TOWNS_NEXT's), each joined onto the land's road."""
    cont, X, Y, R = TOWNS.get(town) or TOWNS_NEXT[town]
    ground = Ground(cd, cont)
    places = [q for q in town_places(cont) if math.hypot(q[1] - X, q[2] - Y) <= R]
    roads = shipped_roads(cont)
    out = []
    for p in buildings(cd, cont):
        x0, y0, x1, y1 = p.bounds
        if not (x1 >= X - R and x0 <= X + R and y1 >= Y - R and y0 <= Y + R):
            continue
        try:
            b = build_building(cd, p, ground, places, log)
        except Exception as ex:  # (a model this reader can't take)
            log(f"  {town}: building {p.uid}: unreadable ({ex!r})")
            continue
        if b is None:
            continue
        joined = join_doors(b, roads)
        b["town"], b["cont"] = town, cont
        log(f"  {town}: {b['name']} ({b['uid']}): floors {b['floors']}, {len(b['nodes'])} nodes, {len(b['edges'])} roads,"
            f" {b['stairs']} stairs, {len(b['doors'])} doors ({joined} joined to the road)"
            + (f"; places: {', '.join(b['places'])}" if b["places"] else ""))
        out.append(b)
    return out


def _cont_parts(lst: list, base: int = 0, attach: bool = False) -> dict:
    """One continent's buildings as Indoors.lua's pieces, their nodes numbered on from `base` (how many come before):
    `n`, `nz` (the numbers as text), `e` (each road's line), `joins`, `bridge` (1-based), `info` (ns.Indoors' lines)."""
    n_all, nz, e_lines, joins, bridge, info = [], [], [], [], [], []
    for b in lst:
        off = base + len(n_all) // 2
        n_all += [f"{v:.1f}" for xy in b["nodes"] for v in xy]
        nz += ["0" if z is None else f"{z:.1f}" for z in b["zs"]]
        for a, c, pts, src in b["edges"]:
            P = [(int(round(q[0])), int(round(q[1]))) for q in pts]
            P = [q for i, q in enumerate(P) if i == 0 or q != P[i - 1]]
            if len(P) == 1:
                P = P * 2
            length = sum(math.hypot(q[0] - p_[0], q[1] - p_[1]) for p_, q in zip(pts, pts[1:]))
            e_lines.append(f"    {{{a + off + 1},{c + off + 1},{max(1.0, length):.0f},{src},\"{pack_points(P)}\"}},")
        joins += [j + off + 1 for j in b["joins"]]
        # (the nodes gap links may use: a town's doors; phase 6's none, its joins are its ways in: a door is any road's
        # end out of the model, a balcony's too, and a gap link went straight up to one; and each door's six links
        # cost memory)
        bridge += [d + off + 1 for d in (b["doors"] if b.get("bridge") is None else b["bridge"])]
        x0, y0, x1, y1 = b["bounds"]
        mx, my, r = (x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0) / 2
        info.append(f'  {{ "{b["town"]}: {b["name"]}", x = {mx:.0f}, y = {my:.0f}, r = {r:.0f}, '
                    + ("attach = true, " if attach else "") + 'floors = { '
                    + ", ".join(f"{z:.1f}" for z in b["floors"]) + " } },")
    return {"n": n_all, "nz": nz, "e": e_lines, "joins": [str(j) for j in joins],
            "bridge": [str(j) for j in sorted(set(bridge))], "info": info}


def indoors_lua(cd: ClientData, built: list) -> str:
    """Data/Indoors.lua: per continent one ns.RoadOverlays entry with every building's inside, and ns.Indoors (each
    building's name, middle and floors: the plans and the tracker's checks)."""
    out = ["-- GENERATED by `agps indoors` (app/azerothgps/indoors.py) from client "
           f"{cd.casc.version}. Do not edit by hand.",
           "-- Buildings' insides as roads with floors (asked 2026-10-06): per continent one entry of ns.RoadOverlays",
           "-- (Data/Roads.lua's format): `nz` each node's floor height, source 6 the stairs, `joins` the doors' roads'",
           "-- ends on the land's road, `bridge` the doors (the only nodes gap links may use). ns.Indoors: each building.",
           "local _, ns = ...",
           "ns.RoadOverlays = ns.RoadOverlays or {}",
           "ns.Indoors = ns.Indoors or {}"]
    by_cont: dict = {}
    for b in built:
        by_cont.setdefault(b["cont"], []).append(b)
    for cont, lst in sorted(by_cont.items()):
        q = _cont_parts(lst)
        out.append(f"ns.Indoors[{cont}] = {{")
        out += q["info"]
        out.append("}")
        out.append("do")
        out.append(f"  local overlays = ns.RoadOverlays[{cont}] or {{}}")
        out.append(f"  ns.RoadOverlays[{cont}] = overlays")
        out.append("  overlays[#overlays + 1] = { indoor = true,")
        out.append("  n = {" + ",".join(q["n"]) + "},")
        out.append("  nz = {" + ",".join(q["nz"]) + "},")
        out.append("  e = {")
        out += q["e"]
        out.append("  },")
        out.append("  joins = {" + ",".join(q["joins"]) + "},")
        out.append("  bridge = {" + ",".join(q["bridge"]) + "},")
        out.append("  }")
        out.append("end")
    return "\n".join(out) + "\n"


def shipped_middles(text: str | None = None) -> list:
    """The buildings in the shipped Data/Indoors.lua (or `text`): [(cont, x, y), ...], their middles (ns.Indoors)."""
    import re

    text = FILE.read_text(encoding="utf-8") if text is None else text
    out = []
    for m in re.finditer(r"^ns\.Indoors\[(\d+)\] = \{\n(.*?)^\}", text, re.S | re.M):
        out += [(int(m.group(1)), float(x), float(y)) for x, y in re.findall(r"x = (-?\d+), y = (-?\d+)", m.group(2))]
    return out


def splice_lua(text: str, built: list) -> str:
    """`text` (the shipped Data/Indoors.lua) with the buildings in `built` added, `attach`ed (phase 7, 2026-11-21): their
    ns.Indoors lines after each continent's list (`attach = true`), their roads an ns.RoadOverlays entry of their own
    after the continent's (`attach = true`: the Router doesn't split the land's road at their joins; a trip to or from
    one goes in by them, R.AttachTrip; joined as the others, they changed other trips' roads, 12 sample trips worse).
    Every building already in it is left as it is (a full --write moves every building: the client and the land's roads
    have changed under them since; #846 spliced Brill's inn the same way)."""
    by_cont: dict = {}
    for b in built:
        by_cont.setdefault(b["cont"], []).append(b)
    lines = text.split("\n")
    for cont, lst in sorted(by_cont.items()):
        head = lines.index(f"ns.Indoors[{cont}] = {{")
        close = lines.index("}", head)
        start = lines.index(f"  local overlays = ns.RoadOverlays[{cont}] or {{}}", close)
        end = lines.index("end", start)
        q = _cont_parts(lst, attach=True)
        block = ["do", f"  local overlays = ns.RoadOverlays[{cont}] or {{}}", f"  ns.RoadOverlays[{cont}] = overlays",
                 "  overlays[#overlays + 1] = { indoor = true, attach = true,",
                 "  n = {" + ",".join(q["n"]) + "},", "  nz = {" + ",".join(q["nz"]) + "},", "  e = {"] + q["e"] + [
                 "  },", "  joins = {" + ",".join(q["joins"]) + "},", "  bridge = {" + ",".join(q["bridge"]) + "},",
                 "  }", "end"]
        lines[end + 1:end + 1] = block
        lines[close:close] = q["info"]
    return "\n".join(lines)


CHECK_FROM = 40.0  # yards out from a building's edge: where a check's route starts (on the land's road there)
CHECK_LAST_YD = 8.0  # a place reached: the route's last stretch off the roads this short at most
CHECK_NPC_LAST_YD = 12.0  # (phase 6's NPCs: no spur to them, no NPC data in the roads; the kept road nearest on their
# floor is COVER_YD along the roads from where the walk went by them, and some stand off it, behind a counter)
CHECK_FLOOR_Z = 3.5  # and on its floor: the route's last floor this near the place's height
CHECK_GROUND_Z = 2.0  # a place no inside road leads to, standing on the terrain (this near it): reached over the land
# (Bloodhoof's trainers under a tent's canvas, open at the sides)


def check(cd: ClientData, built: list, log=print, onto: str | None = None) -> list[dict]:
    """Each town place inside a building, routed to from outside as the addon does (the game harness, with this data
    in place of Data/Indoors.lua): {town, building, place, ok, floor, z, last, why}. Reached: the route ends on the
    building's roads, on the place's floor (CHECK_FLOOR_Z), its last stretch off the roads at most CHECK_LAST_YD.
    `onto`: a shipped Indoors.lua's text, `built` spliced onto it (splice_lua) for the routes."""
    from .gameharness import start

    text = indoors_lua(cd, built) if onto is None else splice_lua(onto, built)
    lua, ns = start(replace={"Data/Indoors.lua": text})
    R = ns.Router
    places = {q[0]: q for q in town_places(0)}
    grounds: dict = {}
    out = []
    for b in built:
        cont = b["cont"]
        x0, y0, x1, y1 = b["bounds"]
        mx, my, r = (x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0) / 2
        start_pt = None
        # (a start out on the land's roads: the nearest land road point CHECK_FROM yd or more out from the building)
        for k in range(8):
            a = k * math.pi / 4
            sx, sy = mx + (r + CHECK_FROM) * math.cos(a), my + (r + CHECK_FROM) * math.sin(a)
            cands = R.NearestEdges(cont, sx, sy)
            g = R.DebugGraph(cont)
            best = None
            for c in cands.values():
                e = g.e[c.edge]
                far = math.hypot(float(c.px) - mx, float(c.py) - my) >= r + CHECK_FROM / 2
                if far and g.nz[e[1]] is None and g.nz[e[2]] is None and (best is None or c.dist < best[0]):
                    best = (float(c.dist), float(c.px), float(c.py))
            if best and (start_pt is None or best[0] < start_pt[0]):
                start_pt = best
        if start_pt:
            start_pt = start_pt[1:]
        for name, px, py, pz in (b.get("npcs") or [places[n] for n in b["places"]]):
            res = {"town": b["town"], "building": b["name"], "place": name, "z": pz, "ok": False}
            out.append(res)
            if not start_pt:
                res["why"] = "no land road near to start from"
                continue
            route = R.Route(cont, start_pt[0], start_pt[1], px, py, lua.table_from({"tz": pz}))
            n = len(route.pts) // 2
            kinds = [route.kinds[i] for i in range(1, n)]
            fz = route.fz and [route.fz[i] for i in range(1, n + 1)]
            last = 0.0
            i = n - 1
            while i >= 1 and kinds[i - 1] == R.KIND_OFFROAD:
                ax, ay = route.pts[2 * i - 1], route.pts[2 * i]
                bx, by = route.pts[2 * i + 1], route.pts[2 * i + 2]
                last += math.hypot(bx - ax, by - ay)
                i -= 1
            res["last"] = round(last, 1)
            res["floor"] = fz and round(fz[-1], 1)
            # (through the inside first: phase 7's NPCs stand on the ground floor, and the walk over the land
            # straight in to one (SegmentCost: a stop in a building's cells is reached) was "reached", and every
            # building of theirs left out as reaching none)
            if not fz or fz[-1] is None:
                res["why"] = "never on the building's roads"
            elif abs(fz[-1] - pz) > CHECK_FLOOR_Z:
                res["why"] = f"ends on the {fz[-1]:.1f} floor"
            elif last > (CHECK_NPC_LAST_YD if b.get("npcs") else CHECK_LAST_YD):
                res["why"] = f"{last:.0f} yd off the roads at the end"
            else:
                res["ok"] = True
                continue
            if name not in b.get("spurred", ()):
                if cont not in grounds:
                    grounds[cont] = Ground(cd, cont)
                h, _ok = grounds[cont].sample([px], [py])
                # (and the last stretch there open: not through the building's walls, Passability's cells)
                ax, ay = float(route.pts[2 * i + 1]), float(route.pts[2 * i + 2])
                if (math.isfinite(float(h[0])) and abs(float(h[0]) - pz) <= CHECK_GROUND_Z
                        and ns.Passability.SegmentCost(cont, ax, ay, px, py) is not None):
                    res["ok"], res["why"] = True, "on the ground, reached over the land"
        n_here = len(b.get("npcs") or b["places"])
        for res in out[-n_here:] if n_here else []:
            log(f"  {'ok' if res['ok'] else '! '} {res['town']}: {res['building']}: {res['place']} (z {res['z']:.1f})"
                + (f": {res.get('why')}" if res.get("why") else ""))
    return out


def npc_reached(cd: ClientData, built: list, log=print, onto: str | None = None) -> list:
    """Of phase 6's buildings (`npcs`), those whose inside the check takes a route to one of their NPCs by at least
    (not one standing on the ground, reached over the land: the inside didn't); the rest left out, their insides don't
    get to the floors their NPCs stand on (Theramore's barracks upstairs, Nethergarde's mage tower's top: no stairs
    found up), so they'd only cost memory."""
    res = check(cd, built, log=lambda *a: None, onto=onto)
    out, i = [], 0
    for b in built:
        n = len(b.get("npcs") or b["places"])
        mine, i = res[i:i + n], i + n
        if b.get("npcs") and not any(r["ok"] and not str(r.get("why", "")).startswith("on the ground") for r in mine):
            log(f"  {b['town']}: {b['name']} ({b['uid']}): left out, its inside reaches none of its NPCs")
            continue
        out.append(b)
    return out


def render(cd: ClientData, b: dict, path: Path, scale: int = 12) -> None:
    """A building's inside as a picture (north up): its floors gray by height, its roads by height (low blue, high
    red), stairs thick cyan, doors green, the ways onto the land's road yellow, its places yellow dots."""
    from PIL import Image, ImageDraw

    from .buildings import buildings as all_buildings

    p = next((q for q in all_buildings(cd, b["cont"]) if q.uid == b["uid"]), None)
    fl, _wl = building_faces(cd, p) if p else ([], [])
    x0, y0, x1, y1 = b["bounds"]
    X0, Y0, X1, Y1 = x0 - 12, y0 - 12, x1 + 12, y1 + 12
    S = scale
    img = Image.new("RGB", (int((Y1 - Y0) * S), int((X1 - X0) * S)), (18, 22, 18))
    dr = ImageDraw.Draw(img)

    def px(x, y):
        return (Y1 - y) * S, (X1 - x) * S
    allz = [z for f in fl for z in f[1]] or [0.0]
    lo, hi = min(allz), max(allz)
    for tri, vz, _a, _b in sorted(fl, key=lambda f: sum(f[1])):
        c = int(45 + 140 * ((sum(vz) / 3 - lo) / max(1.0, hi - lo)))
        dr.polygon([px(*q) for q in tri], fill=(c, c, c))
    zs = [z for z in b["zs"] if z is not None] or [0.0]
    zl, zh = min(zs), max(zs)
    for a, c, pts, src in b["edges"]:
        za, zb = b["zs"][a], b["zs"][c]
        if za is None or zb is None:
            col, w = (240, 210, 40), 3
        elif src == 6:
            col, w = (40, 230, 240), 6
        else:
            k = ((za + zb) / 2 - zl) / max(1.0, zh - zl)
            col, w = (int(60 + 195 * k), 70, int(60 + 195 * (1 - k))), 3
        dr.line([px(*q[:2]) for q in pts], fill=col, width=w)
    for i, (x, y) in enumerate(b["nodes"]):
        a_, b_ = px(x, y)
        door = i in b["doors"]
        dr.ellipse([a_ - 4, b_ - 4, a_ + 4, b_ + 4], outline=(60, 240, 60) if door else (255, 255, 255), width=2)
        if b["zs"][i] is not None:
            dr.text((a_ + 5, b_ - 5), f"{b['zs'][i]:.0f}", fill=(255, 255, 255))
    for name, x, y, _z in [q for q in town_places(b["cont"]) if q[0] in b["places"]]:
        a_, b_ = px(x, y)
        dr.ellipse([a_ - 5, b_ - 5, a_ + 5, b_ + 5], fill=(255, 220, 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def write(cd: ClientData, towns=None, log=print, out: Path | None = None) -> list:
    built = []
    for town in towns or TOWNS:
        built += build_town(cd, town, log)
    if towns is None:
        built += npc_reached(cd, build_npc_buildings(cd, log), log)
    walk_joins(built, log)
    (out or FILE).write_text(indoors_lua(cd, built), encoding="utf-8")
    return built
