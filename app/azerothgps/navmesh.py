"""A test server's navigation mesh, read for checking AzerothGPS's routing (asked 2026-11-17: "easiest way
to get topology scan of entire map including city interiors to know what paths a player could actually walk on/
through/under/into", then "proceed on a feature branch so we can compare routing").

The server (an AzerothCore-based core) paths its NPCs over Recast/Detour meshes it built from the
client's collision: the terrain, every building and city model, solid doodads. One `.mmtile` per map tile, under
`data/ref/mmaps-<build>/mmaps/` (copied from the server's `data\\mmaps`; git-ignored, never shipped: a checking tool
only, as Shortest Path Forever's lines are). The copy here was cut from client build 70058 (a September beta): where
WoW Forever changed a place since, the mesh is the old one.

Formats (AzerothCore's MapBuilder / Detour 1.4):
- `MMMM.mmap`: dtNavMeshParams: orig[3], tileWidth, tileHeight (floats), maxTiles, maxPolys (ints).
- `MMMMYYXX.mmtile`: MmapTileHeader (magic "MMAP", dtVersion, mmapVersion, size, usesLiquids + 3 pad bytes), then
  Detour's tile: dtMeshHeader, verts, polys, links (empty in the file), detail meshes, detail verts, detail tris,
  BV tree, off-mesh connections, each 4-byte aligned.
- Recast's axes are the game's (y, z, x): a vertex (rx, ry, rz) is world x = rz, y = rx, height = ry.
- A poly's `neis[k]`: 0 none, n (1-based) a poly of the same tile, with 0x8000 a link out of the tile (the low bits its
  side); the links to other tiles are made here by matching border edges (Detour's connectExtLinks).
- Area ids (AzerothCore's NavArea): 11 ground, 10 steep ground, 9 water, 8 magma and slime.
"""

from __future__ import annotations

import heapq
import math
import struct
from collections import defaultdict
from pathlib import Path

from .paths import data_dir

DT_EXT_LINK = 0x8000
VERTS_PER_POLY = 6
AREA_GROUND, AREA_STEEP, AREA_WATER, AREA_MAGMA = 11, 10, 9, 8
# yards: two border edges of neighbor tiles this near in height are one walkable seam
SEAM_CLIMB = 2.0
# the cost of a yard by the poly's area: water swum slower, magma and slime never by choice
AREA_COST = {AREA_GROUND: 1.0, AREA_STEEP: 1.5, AREA_WATER: 1.5, AREA_MAGMA: 50.0}


def mmaps_dir(build: str | None = None) -> Path:
    base = data_dir() / "ref"
    if build:
        return base / f"mmaps-{build}" / "mmaps"
    found = sorted(base.glob("mmaps-*/mmaps"))
    if not found:
        raise FileNotFoundError(f"no navmesh under {base} (copy the server's data\\mmaps to mmaps-<build>/mmaps)")
    return found[-1]


def _align4(n: int) -> int:
    return (n + 3) & ~3


class Tile:
    """One tile's polys: `verts` [(x, y, z) world], `polys` [{verts, neis, area, flags}]."""

    __slots__ = ("tx", "ty", "verts", "polys", "bmin", "bmax", "climb")

    def __init__(self, path: Path):
        b = path.read_bytes()
        magic, dtv, mv, size, liquids = struct.unpack_from("<IIIIB", b, 0)
        if magic != 0x4D4D4150:
            raise ValueError(f"{path.name}: not an mmtile")
        o = 20
        hdr = struct.unpack_from("<iiiiiI" + "i" * 9 + "fff" + "fff" + "fff" + "f", b, o)
        (dmagic, dver, x, y, layer, user, npoly, nvert, maxlink, ndm, ndv, ndt, nbv, noff, offbase,
         wh, wr, wc, b0, b1, b2, c0, c1, c2, qf) = hdr
        if dmagic != 0x444E4156:
            raise ValueError(f"{path.name}: no Detour tile")
        self.tx, self.ty, self.climb = x, y, wc
        self.bmin, self.bmax = (b2, b0, b1), (c2, c0, c1)  # (world x, y, z)
        o += _align4(struct.calcsize("<iiiiiI" + "i" * 9 + "fff" * 3 + "f"))
        raw = struct.unpack_from("<%df" % (nvert * 3), b, o)
        self.verts = [(raw[3 * i + 2], raw[3 * i], raw[3 * i + 1]) for i in range(nvert)]
        o += _align4(nvert * 12)
        self.polys = []
        for i in range(npoly):
            first, *rest = struct.unpack_from("<I6H6HHBB", b, o + 32 * i)
            vs, ns, flags, nv, at = rest[0:6], rest[6:12], rest[12], rest[13], rest[14]
            self.polys.append({"verts": vs[:nv], "neis": ns[:nv], "flags": flags, "area": at & 0x3F,
                               "type": at >> 6})


class NavMesh:
    """A continent's mesh, its tiles loaded as asked (`load_box`), and the walk between two spots (`path`)."""

    def __init__(self, cont: int, build: str | None = None):
        self.cont, self.dir = cont, mmaps_dir(build)
        params = struct.unpack("<5f2i", (self.dir / f"{cont:04d}.mmap").read_bytes()[:28])
        self.orig = params[0:3]  # (recast x, y, z)
        self.tile_w = params[3]
        self.tiles: dict[tuple[int, int], Tile | None] = {}
        self._centers: dict = {}

    # ---- tiles
    def _tile_of(self, x: float, y: float) -> tuple[int, int]:
        """The tile (tx, ty) holding world (x, y): recast's (rx = y, rz = x) from the mesh's origin."""
        return (int(math.floor((y - self.orig[0]) / self.tile_w)), int(math.floor((x - self.orig[2]) / self.tile_w)))

    def tile(self, tx: int, ty: int) -> Tile | None:
        key = (tx, ty)
        if key not in self.tiles:
            # (AzerothCore names a tile by the game's own grid, MMMM + gx + gy: gx = 32 - x / 533.33, gy = 32 - y / 533.33
            # at the tile's middle; the mesh's own indices are from its origin, the header's x, y)
            xc = self.orig[2] + (ty + 0.5) * self.tile_w
            yc = self.orig[0] + (tx + 0.5) * self.tile_w
            gx, gy = int(math.floor(32 - xc / self.tile_w)), int(math.floor(32 - yc / self.tile_w))
            p = self.dir / f"{self.cont:04d}{gx:02d}{gy:02d}.mmtile"
            t = None
            if p.exists():
                cand = Tile(p)
                if (cand.tx, cand.ty) == (tx, ty):
                    t = cand
            self.tiles[key] = t
        return self.tiles[key]

    def load_box(self, x0, x1, y0, y1):
        a = self._tile_of(min(x0, x1), min(y0, y1))
        b = self._tile_of(max(x0, x1), max(y0, y1))
        for tx in range(min(a[0], b[0]), max(a[0], b[0]) + 1):
            for ty in range(min(a[1], b[1]), max(a[1], b[1]) + 1):
                self.tile(tx, ty)

    # ---- polys
    def _polys(self):
        for key, t in self.tiles.items():
            if t is None:
                continue
            for i, p in enumerate(t.polys):
                if p["type"] == 0 and p["area"] != 0:
                    yield key, i, t, p

    def center(self, key, i):
        c = self._centers.get((key, i))
        if c is None:
            t = self.tiles[key]
            vs = [t.verts[v] for v in t.polys[i]["verts"]]
            c = (sum(v[0] for v in vs) / len(vs), sum(v[1] for v in vs) / len(vs), sum(v[2] for v in vs) / len(vs))
            self._centers[(key, i)] = c
        return c

    def neighbors(self, key, i):
        """((key2, j), (a, b) the shared edge's ends, world) of poly i of tile `key`."""
        t = self.tiles[key]
        p = t.polys[i]
        out = []
        nv = len(p["verts"])
        for k, n in enumerate(p["neis"]):
            a, b = t.verts[p["verts"][k]], t.verts[p["verts"][(k + 1) % nv]]
            if n == 0:
                continue
            if not n & DT_EXT_LINK:
                out.append(((key, n - 1), (a, b)))
                continue
            for other in self._across(key, a, b):
                out.append(other)
        return out

    def _across(self, key, a, b):
        """The polys of the tile beside `key` sharing border edge a-b (Detour's connectExtLinks, by overlap)."""
        t = self.tiles[key]
        found = []
        # the side: the edge on the tile's min or max x or y (world)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nk = (key[0] + dx, key[1] + dy)
            u = self.tile(*nk)
            if u is None:
                continue
            for j, q in enumerate(u.polys):
                if q["type"] != 0:
                    continue
                nq = len(q["verts"])
                for k, n in enumerate(q["neis"]):
                    if not n & DT_EXT_LINK:
                        continue
                    c, d = u.verts[q["verts"][k]], u.verts[q["verts"][(k + 1) % nq]]
                    seg = _overlap(a, b, c, d)
                    if seg:
                        found.append(((nk, j), seg))
        return found

    def nearest(self, x, y, z=None, reach=10.0):
        """The poly under/nearest (x, y) [at height z]: (key, i, (px, py, pz)) or None."""
        self.load_box(x - reach, x + reach, y - reach, y + reach)
        best = None
        for key, i, t, p in self._polys():
            vs = [t.verts[v] for v in p["verts"]]
            if min(v[0] for v in vs) - reach > x or max(v[0] for v in vs) + reach < x:
                continue
            if min(v[1] for v in vs) - reach > y or max(v[1] for v in vs) + reach < y:
                continue
            inside = _in_poly(vs, x, y)
            h = _height_on(vs, x, y)
            d2 = 0.0 if inside else _dist2_poly(vs, x, y)
            dz = abs(h - z) if z is not None else 0.0
            score = d2 + dz * dz * 4
            if best is None or score < best[0]:
                px, py = (x, y) if inside else _closest_on_poly(vs, x, y)
                best = (score, key, i, (px, py, _height_on(vs, px, py)))
        return None if best is None else best[1:]

    def path(self, sx, sy, sz, tx, ty, tz, margin=300.0, max_nodes=400000):
        """The walk from (sx, sy, sz) to (tx, ty, tz) over the mesh: { pts [(x, y, z)], yards, polys, found }."""
        self.load_box(min(sx, tx) - margin, max(sx, tx) + margin, min(sy, ty) - margin, max(sy, ty) + margin)
        s = self.nearest(sx, sy, sz)
        g = self.nearest(tx, ty, tz)
        if not s or not g:
            return {"pts": [], "yards": None, "found": False, "why": "no mesh at an end"}
        start, goal = (s[0], s[1]), (g[0], g[1])
        gc = g[2]
        openq = [(0.0, 0, start)]
        came = {start: None}
        portal = {start: None}
        cost = {start: 0.0}
        seen = 0
        while openq:
            _, _, cur = heapq.heappop(openq)
            if cur == goal:
                break
            seen += 1
            if seen > max_nodes:
                return {"pts": [], "yards": None, "found": False, "why": "search too big"}
            cc = self.center(*cur)
            for nxt, edge in self.neighbors(*cur):
                if self.tiles.get(nxt[0]) is None:
                    continue
                q = self.tiles[nxt[0]].polys[nxt[1]]
                if q["type"] != 0 or q["area"] == 0:
                    continue
                mid = ((edge[0][0] + edge[1][0]) / 2, (edge[0][1] + edge[1][1]) / 2, (edge[0][2] + edge[1][2]) / 2)
                nc = self.center(*nxt)
                w = AREA_COST.get(q["area"], 1.0)
                c = cost[cur] + (math.dist(cc, mid) + math.dist(mid, nc)) * w
                if c < cost.get(nxt, math.inf):
                    cost[nxt], came[nxt], portal[nxt] = c, cur, edge
                    heapq.heappush(openq, (c + math.dist(nc, gc), seen, nxt))
        if goal not in came:
            return {"pts": [], "yards": None, "found": False, "why": "not connected"}
        chain, portals = [], []
        n = goal
        while n is not None:
            chain.append(n)
            portals.append(portal[n])
            n = came[n]
        chain.reverse()
        portals = [p for p in reversed(portals) if p]
        pts = _funnel(s[2], g[2], portals)
        yards = sum(math.dist(pts[k], pts[k + 1]) for k in range(len(pts) - 1))
        return {"pts": pts, "yards": yards, "found": True, "polys": len(chain),
                "areas": sorted({self.tiles[k].polys[i]["area"] for k, i in chain})}


# ---- geometry (world x, y; z the height)
def _cross2(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _in_poly(vs, x, y):
    sign = 0
    for k in range(len(vs)):
        c = _cross2(vs[k], vs[(k + 1) % len(vs)], (x, y))
        if abs(c) < 1e-9:
            continue
        s = 1 if c > 0 else -1
        if sign == 0:
            sign = s
        elif s != sign:
            return False
    return True


def _height_on(vs, x, y):
    """The poly's height at (x, y): its fan's triangle there, else its nearest vertex's."""
    for k in range(1, len(vs) - 1):
        a, b, c = vs[0], vs[k], vs[k + 1]
        det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(det) < 1e-9:
            continue
        l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / det
        l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / det
        l3 = 1 - l1 - l2
        if min(l1, l2, l3) >= -1e-6:
            return l1 * a[2] + l2 * b[2] + l3 * c[2]
    return min(vs, key=lambda v: (v[0] - x) ** 2 + (v[1] - y) ** 2)[2]


def _closest_seg(a, b, x, y):
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - a[0]) * vx + (y - a[1]) * vy) / L2))
    return a[0] + vx * t, a[1] + vy * t


def _closest_on_poly(vs, x, y):
    best = None
    for k in range(len(vs)):
        px, py = _closest_seg(vs[k], vs[(k + 1) % len(vs)], x, y)
        d = (px - x) ** 2 + (py - y) ** 2
        if best is None or d < best[0]:
            best = (d, px, py)
    return best[1], best[2]


def _dist2_poly(vs, x, y):
    px, py = _closest_on_poly(vs, x, y)
    return (px - x) ** 2 + (py - y) ** 2


def _overlap(a, b, c, d, tol=0.1):
    """The shared stretch of two border edges a-b and c-d (one tile's and its neighbor's), or None."""
    # (both on one line: x the same, or y the same)
    for ax in (0, 1):
        if abs(a[ax] - b[ax]) < tol and abs(c[ax] - d[ax]) < tol and abs(a[ax] - c[ax]) < tol:
            o = 1 - ax
            lo, hi = max(min(a[o], b[o]), min(c[o], d[o])), min(max(a[o], b[o]), max(c[o], d[o]))
            if hi - lo < 0.01:
                return None

            def at(p, q, v):
                t = 0.0 if abs(q[o] - p[o]) < 1e-9 else (v - p[o]) / (q[o] - p[o])
                return p[2] + (q[2] - p[2]) * t
            for v in (lo, hi):
                if abs(at(a, b, v) - at(c, d, v)) > SEAM_CLIMB:
                    return None
            e0 = [0.0, 0.0, at(a, b, lo)]
            e1 = [0.0, 0.0, at(a, b, hi)]
            e0[ax] = e1[ax] = a[ax]
            e0[o], e1[o] = lo, hi
            return (tuple(e0), tuple(e1))
    return None


def _tri(o, a, b):
    """Recast's triarea2: twice the signed area the funnel tests by (the opposite sign of _cross2 in the world's axes)."""
    return -_cross2(o, a, b)


def _funnel(start, goal, portals):
    """The shortest line through the portals (the simple stupid funnel), in 2D, heights from the portals."""
    if not portals:
        return [start, goal]
    # (each portal's left and right as seen walking through it)
    lefts, rights = [start], [start]
    prev = start
    for a, b in portals:
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if _cross2(prev, mid, a) > 0:
            lefts.append(a)
            rights.append(b)
        else:
            lefts.append(b)
            rights.append(a)
        prev = mid
    lefts.append(goal)
    rights.append(goal)
    pts = [start]
    apex, li, ri = start, 0, 0
    left, right = lefts[0], rights[0]
    i = 1
    while i < len(lefts):
        L, R = lefts[i], rights[i]
        if _tri(apex, right, R) <= 0:
            if apex == right or _tri(apex, left, R) > 0:
                right, ri = R, i
            else:
                pts.append(left)
                apex, ri = left, li
                right = apex
                i = li + 1
                continue
        if _tri(apex, left, L) >= 0:
            if apex == left or _tri(apex, right, L) < 0:
                left, li = L, i
            else:
                pts.append(right)
                apex, li = right, ri
                left = apex
                i = ri + 1
                continue
        i += 1
    if pts[-1] != goal:
        pts.append(goal)
    return pts
