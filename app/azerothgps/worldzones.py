"""The world grid's sample zones and search helpers (worldgrid.py): the grid's pieces, an A* over it as the addon's, and the
sample zones' mesh walls against today's (asked 2026-11-22: "compare its walls against today's"). Dev only."""

from __future__ import annotations

import heapq
import json
import math
import time
from collections import defaultdict

import numpy as np

from . import worldgrid as W
from .paths import data_dir


def pieces(g: W.Grid):
    """Each surface's piece (links either way, road links too), 0 the biggest: (labels, sizes by rank)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    src = np.repeat(np.arange(g.n), 8)
    dst = g.links.ravel()
    ok = dst >= 0
    src, dst = src[ok], dst[ok]
    if g.road:
        src = np.r_[src, [a for a, *_ in g.road]]
        dst = np.r_[dst, [b for _a, b, *_ in g.road]]
    m = coo_matrix((np.ones(len(src), np.int8), (src, dst)), shape=(g.n, g.n))
    nc, lab = connected_components(m, directed=True, connection="weak")
    sizes = np.bincount(lab, minlength=nc)
    order = np.argsort(-sizes)
    rank = np.empty(nc, np.int64)
    rank[order] = np.arange(nc)
    return rank[lab], sizes[order]


def search(g: W.Grid, starts: list, goals: dict, tx: float, ty: float, max_nodes: int = 2_000_000, hw: float = 1.0):
    """A* over the grid (the in-game search's rule): starts [(s, cost)], goals {s: extra}; (the surfaces' way, its
    cost) or None."""
    gc, prev = {}, {}
    h = []
    for s, c in starts:
        if c < gc.get(s, math.inf):
            gc[s] = c
            px, py = g.point(s)
            heapq.heappush(h, (c + hw * W.ROAD_PREF * math.hypot(px - tx, py - ty), s))
    closed = set()
    best, found = None, None
    k = 0
    while h:
        f, s = heapq.heappop(h)
        if s in closed:
            continue
        closed.add(s)
        k += 1
        if k > max_nodes:
            break
        if s in goals:
            tot = gc[s] + goals[s]
            if best is None or tot < best:
                best, found = tot, s
        if found is not None and f >= best:
            break
        for t, c in g.neighbors(s):
            nc = gc[s] + c
            if nc < gc.get(t, math.inf):
                gc[t], prev[t] = nc, s
                px, py = g.point(t)
                heapq.heappush(h, (nc + hw * W.ROAD_PREF * math.hypot(px - tx, py - ty), t))
    g.last_nodes = k
    if found is None:
        return None
    out = [found]
    while out[-1] in prev:
        out.append(prev[out[-1]])
    return out[::-1], best


def ends(g: W.Grid, x: float, y: float, z: float | None, reach: int = 2) -> list:
    """The surfaces a spot may start or end on: [(s, cost)] (its cell's; none: the nearest cells' within `reach`)."""
    c = g.cell
    gx, gy = int(math.floor(x / c)) - g.gxmin, int(math.floor(y / c)) - g.gymin
    for r in range(reach + 1):
        out = []
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r or not (0 <= gx + dx < g.W and 0 <= gy + dy < g.H):
                    continue
                k = (gx + dx) * g.H + gy + dy
                f, n = int(g.first[k]), int(g.count[k])
                for s in range(f, f + max(n, 0)):
                    px, py = g.point(s)
                    dz = abs(float(g.z[s]) - z) if z is not None else 0.0
                    out.append((s, math.hypot(px - x, py - y) + max(0.0, dz - 4.0) * 6.0))
        if out:
            if z is None:
                return out
            near = [o for o in out if abs(float(g.z[o[0]]) - z) <= 4.0]
            return near or [min(out, key=lambda o: o[1])]
    return []


ZONES = {  # (zones with known trouble: their map tiles)
    "Loch Modan": (0, [(tx, ty) for tx in range(35, 40) for ty in range(40, 45)]),
    "Durotar": (1, [(tx, ty) for tx in range(38, 43) for ty in range(28, 35)]),
}
ZONE_TRIPS = {  # the hop tests' trips (test_routecheck_regressions, test_cliff_walls): walked on the grid
    "Loch Modan": [((-5743.0, -2820.0), (-6116.7, -3250.0)), ((-6116.7, -3250.0), (-5743.0, -2820.0)),
                   ((-5800.0, -3350.0), (-5834.1, -2752.3))],
    "Durotar": [((-1000.0, -4000.0), (-1060.0, -3950.0)), ((300.0, -4700.0), (-600.0, -4250.0))],
}


def zones(names=None, per_tile: int = W.CELL_PER_TILE, log=print, build: bool = True) -> dict:
    """The sample zones' grids against today's: the terrain grid (Passability.At: the land's grid, Buildings.lua's cells,
    the capitals'), the shipped walls (grid links across one), the hop tests' trips walked on the grid. Renders and
    numbers in data/debug/worldgrid/."""
    from PIL import Image

    from .gameharness import start

    lua, ns = start()
    P = ns.Passability
    out_dir = data_dir() / "debug" / "worldgrid"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {}
    for name, (cont, tiles) in ZONES.items():
        if names and name not in names:
            continue
        if build:
            W.build_tiles([(cont, tx, ty, per_tile) for tx, ty in tiles], log=log)
        g = W.Grid(cont, tiles, per_tile, log)
        lab, sizes = pieces(g)
        c = g.cell
        img = np.zeros((g.W, g.H, 3), np.uint8)  # (rows: x, the map's north; cols: y, the map's west)
        cls = defaultdict(int)
        main = lab == 0
        flat = (g.gx - g.gxmin).astype(np.int64) * g.H + (g.gy - g.gymin)
        top = {}
        for s in range(g.n):
            k = int(flat[s])
            v = 2 if g.kind[s] == W.KIND_SWIM else (1 if main[s] else 0)
            if v > top.get(k, -1):
                top[k] = v
        for k in range(g.W * g.H):
            i, j = divmod(k, g.H)
            x, y = (g.gxmin + i + 0.5) * c, (g.gymin + j + 0.5) * c
            t = P.At(cont, x, y)
            mine = top.get(k, -1)
            if t == 1 or mine == 2:
                col, key = (40, 90, 200), "water"
            elif t == 0 and mine == 1:
                col, key = (60, 150, 60), "both open"
            elif t == 0 and mine == 0:
                col, key = (150, 150, 40), "terrain open, mesh: a piece apart"
            elif t == 0:
                col, key = (220, 40, 40), "terrain open, mesh closed"
            elif mine == 1:
                col, key = (60, 200, 255), "terrain closed, mesh open"
            elif mine == 0:
                col, key = (90, 70, 40), "terrain closed, mesh: a piece apart"
            else:
                col, key = (20, 20, 20), "both closed"
            if g.count[k] > 1:
                col = tuple(min(255, int(v * 0.6 + 100)) for v in col)
            cls[key] += 1
            img[g.W - 1 - i, g.H - 1 - j] = col
        across = 0
        for s in np.nonzero(main)[0]:
            x, y = g.point(s)
            for d in range(8):
                t = int(g.links[s, d])
                if t > s:
                    x2, y2 = g.point(t)
                    if P.CrossesWall(cont, x, y, x2, y2):
                        across += 1
                        img[g.W - 1 - (g.gx[s] - g.gxmin), g.H - 1 - (g.gy[s] - g.gymin)] = (255, 255, 255)
        Image.fromarray(img).save(out_dir / f"zones_{name.lower().replace(' ', '_')}_{per_tile}.png")
        trips = []
        for (sx, sy), (tx_, ty_) in ZONE_TRIPS.get(name, []):
            st, gl = ends(g, sx, sy, None), {s: cst for s, cst in ends(g, tx_, ty_, None)}
            t0 = time.time()
            got = search(g, st, gl, tx_, ty_)
            ms = (time.time() - t0) * 1000
            if got is None:
                trips.append({"from": [sx, sy], "to": [tx_, ty_], "found": False, "nodes": g.last_nodes})
                continue
            path, cost = got
            pts = [g.point(s) for s in path]
            yd = sum(math.dist(pts[q], pts[q + 1]) for q in range(len(pts) - 1))
            walls = sum(bool(P.CrossesWall(cont, *pts[q], *pts[q + 1])) for q in range(len(pts) - 1))
            blocked = sum(P.SegmentCost(cont, *pts[q], *pts[q + 1]) is None for q in range(len(pts) - 1))
            trips.append({"from": [sx, sy], "to": [tx_, ty_], "found": True, "yd": round(yd), "cost": round(cost),
                          "nodes": g.last_nodes, "ms": round(ms), "steps_across_walls": walls,
                          "steps_over_terrain_closed": blocked, "straight": round(math.dist((sx, sy), (tx_, ty_)))})
        report[name] = {"cont": cont, "tiles": len(tiles), "cell": round(c, 3), "surfaces": int(g.n),
                        "stacked_cells": int((g.count > 1).sum()), "pieces": int(len(sizes)),
                        "main_piece": int(sizes[0]), "in_pieces_under_min": int(sizes[sizes < W.MIN_PIECE].sum()),
                        "cells": {k: v for k, v in sorted(cls.items())}, "links_across_shipped_walls": across,
                        "trips": trips}
        log(json.dumps(report[name], indent=1))
    (out_dir / f"zones_{per_tile}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report
