"""A capital's roads without the spiderweb (issue #829, Kooki3z 2026-11-20: "there are spiderweb routing in open areas
that just don't make sense ... Org and UC are full of zigzag road paths when its not necessary"; then "probably start with
navmesh data ... and what isn't sure of i record myself").

The capitals' roads (Data/Capitals.lua) are the road skeleton of the city models' floors (walknet, capitals.streets): over
a wide open floor a skeleton is a web of branches and zigzags. This is a post-process of the shipped roads over our own
Recast mesh of the city (recastmesh.py, `agps navmesh build`; a dev tool's data, nothing of the mesh ships), so the
capitals aren't built again:

1. **Straight roads** (`straighten`): each plain road (source 0) walked over the mesh at its own heights, point to point
   (`MeshWalk.walk`: every STEP yards a walkable poly within ON_XY across and within CLIMB of the height before; it must
   end within END_Z of the road's height there), then string-pulled: a shape point goes wherever the straight line
   between its neighbors walks on the mesh too. A road the mesh can't walk keeps its points and is flagged.
2. **No web** (`thin`): the plain roads in order of length, shortest first, each kept only when the roads kept so far
   don't already join its ends within STRETCH times its length and SLACK_YD more (a greedy spanner): a plaza's loops
   and parallel branches go, a corridor's one road stays. Gates' joins, drops, lifts, stairs and swims are kept as they
   are and never dropped; a road the mesh couldn't walk is never dropped (it may be the only way the mesh misses).
   Dead ends shorter than STUB_YD go (`prune_stubs`: a stop there is reached by a dotted leg off the road, as stops off
   roads are elsewhere).
3. **Fewer pieces** (`merge`): a node left with two plain roads and no other use (not a join, not a drop's, lift's,
   stair's or swim's end) joins them into one when the joined road's heights, read straight between its two ends as the
   game reads a road's floor, stay within MERGE_Z of the mesh's floor along it; then that road is straightened again.
4. **Flagged** (`Result.flags`): the plain roads the mesh couldn't walk (through a wall, over a gap, a floor the mesh left
   out, a door the server spawns): for Kooki3z to record in game (the recorder's road kinds); his recordings win.

`agps city-roads [--city Orgrimmar] [--write]` (cli.py): the report, before/after pictures and the flags into
data/debug/cityroads/; --write patches only that city's roads in Capitals.lua (the other capitals' roads in its entry,
its grids and everything else stay byte for byte).
"""

from __future__ import annotations

import heapq
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import navcompare as NC
from . import navmesh as NM

STEP = 0.5  # yards: a walk over the mesh looks this often
ON_XY = 1.5  # yards: a walkable poly this near across (the roads' points are whole yards, the mesh kept 0.4 off walls)
CLIMB = 2.5  # yards: up or down from one look to the next (the mesh's polys' heights are rough: no detail mesh)
START_Z = 6.0  # yards: a road's end on the floor within this of its node's height (the nodes' heights are rounded
END_Z = 6.0  # ... to even yards and read off the grid's top floor) and the walk must end within this of the height there
PULL_XY = 0.5  # yards: a straight line in place of a road's points keeps this near the mesh across ...
END_ROOM = 1.5  # ... but within this of its ends (on the road's own points: ON_XY) ...
PULL_CLIMB = 1.5  # ... climbs at most this from one look to the next ...
PULL_Z = 1.5  # ... and starts and ends within this of the floor the road had there
STRETCH = 1.25  # a plain road goes when the others join its ends within this times its length ...
SLACK_YD = 4.0  # ... and this many yards more
STUB_YD = 8.0  # yards: dead-end plain roads shorter than this go
MERGE_Z = 2.0  # yards: two roads joined into one when its straight heights stay this near the floor ...
PLACE_NODE_YD = 25.0  # yards: the nodes this near a city place are never joined over
NODE_Z = 1.0  # ... and the heights read on it stay this near those of the nodes it joins over
PLAIN = 0  # the plain roads' source (capitals.capitals_lua: 3 drop, 5 lift, 6 stairs, 7 swim)
CITIES = {"Orgrimmar": 1}  # the cities done so far, their continent (Undercity's Cities.lua is a format of its own)

_ALPHA = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
_PACK = {ch: i for i, ch in enumerate(_ALPHA)}
_EDGE = re.compile(r'^\s*\{(\d+),(\d+),(\d+),(\d+),"([^"]*)"\},?\s*$')


# --- the entry in Capitals.lua --------------------------------------------------------------------------------------

@dataclass
class Edge:
    a: int
    b: int
    length: int  # the file's yards (a lift's wait and ride counted in)
    src: int
    pts: list  # [(x, y)] whole yards, node a's first and node b's last


@dataclass
class Entry:
    head: str  # its first line
    nodes: list  # [(x, y)]
    nz: list  # [height or None]
    edges: list  # [Edge]
    joins: list  # node indices (0-based)
    drops: dict  # edge index (0-based) -> yards
    bridge: list | None = None
    span: tuple = (0, 0)  # its lines in the file: [first, last]


def unpack(s: str, x: int, y: int) -> list:
    pts = [(x, y)]
    for i in range(0, len(s) - 3, 4):
        x += _PACK[s[i]] * 64 + _PACK[s[i + 1]] - 2048
        y += _PACK[s[i + 2]] * 64 + _PACK[s[i + 3]] - 2048
        pts.append((x, y))
    return pts


def pack(pts) -> str:
    out = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        for d in (x1 - x0, y1 - y0):
            v = int(d) + 2048
            assert 0 <= v < 4096, d
            out.append(_ALPHA[v >> 6] + _ALPHA[v & 63])
    return "".join(out)


def _nums(line: str) -> list:
    body = line[line.index("{") + 1:line.rindex("}")]
    return [int(v) for v in body.split(",") if v.strip()]


def read_entry(lines: list, cont: int, label: str = "capitals") -> Entry:
    """The ns.RoadOverlays[cont] entry of capitals.capitals_lua with that label, from the file's lines."""
    sect = None
    for i, line in enumerate(lines):
        if line.startswith(f"  local overlays = ns.RoadOverlays[{cont}]"):
            sect = i
        if sect is not None and line.startswith(f'  overlays[#overlays + 1] = {{ capital = "{label}",'):
            first = i
            break
    else:
        raise ValueError(f"no {label!r} roads for continent {cont}")
    e = Entry(lines[first], [], [], [], [], {})
    i = first + 1
    while True:
        s = lines[i].strip()
        if s.startswith("n = {"):
            v = _nums(s)
            e.nodes = [(v[k], v[k + 1]) for k in range(0, len(v), 2)]
        elif s.startswith("nz = {"):
            e.nz = [None if h == 0 else h for h in _nums(s)]
        elif s == "e = {":
            i += 1
            while lines[i].strip() != "},":
                m = _EDGE.match(lines[i])
                a, b, ln, src = (int(m.group(k)) for k in range(1, 5))
                e.edges.append(Edge(a - 1, b - 1, ln, src, unpack(m.group(5), *e.nodes[a - 1])))
                i += 1
        elif s.startswith("joins = {"):
            e.joins = [j - 1 for j in _nums(s)]
        elif s.startswith("bridge = {"):
            e.bridge = [j - 1 for j in _nums(s)]
        elif s.startswith("drops = {"):
            body = s[s.index("{") + 1:s.rindex("}")]
            e.drops = {int(k) - 1: int(v) for k, v in re.findall(r"\[(\d+)\] = (\d+)", body)}
        elif s == "}":
            e.span = (first, i)
            return e
        i += 1


def entry_lines(e: Entry) -> list:
    """The entry written as capitals.capitals_lua writes it."""
    out = [e.head,
           "  n = {" + ",".join(f"{x},{y}" for x, y in e.nodes) + "},",
           "  nz = {" + ",".join("0" if h is None else str(h) for h in e.nz) + "},",
           "  e = {"]
    for ed in e.edges:
        out.append(f'    {{{ed.a + 1},{ed.b + 1},{ed.length},{ed.src},"{pack(ed.pts)}"}},')
    out.append("  },")
    out.append("  joins = {" + ",".join(str(j + 1) for j in e.joins) + "},")
    if e.bridge is not None:
        out.append("  bridge = {" + ",".join(str(j + 1) for j in e.bridge) + "},")
    out.append("  drops = {" + ", ".join(f"[{i + 1}] = {h}" for i, h in sorted(e.drops.items())) + "},")
    out.append("  }")
    return out


def path_yards(pts) -> float:
    return sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))


# --- walking over the mesh ------------------------------------------------------------------------------------------

class MeshWalk:
    """A city's mesh (navcompare.PolyIndex) and walks over it at a height."""

    def __init__(self, index: NC.PolyIndex):
        self.index = index
        self._memo = {}

    def floors(self, x, y) -> list:
        """[(height, yards across)] of the walkable polys within ON_XY of (x, y)."""
        k = (round(x * 4), round(y * 4))
        f = self._memo.get(k)
        if f is None:
            f = [(h, d) for h, _pid, d in self.index.floors(x, y, ON_XY)]
            self._memo[k] = f
        return f

    def floor_near(self, x, y, z, reach, xy=ON_XY) -> float | None:
        best = None
        for h, d in self.floors(x, y):
            if d <= xy and abs(h - z) <= reach and (best is None or abs(h - z) < abs(best - z)):
                best = h
        return best

    def walk(self, pts, z0, z1=None, strict=False) -> list | None:
        """Walk the polyline `pts` from height z0 (None: any floor at its start): each point's floor height, or None when
        it leaves the mesh (no floor within CLIMB of the last) or (with z1) doesn't end within END_Z of z1. `strict`: a
        straight line tried in place of a road's points (z0 and z1 the mesh's own heights there): within PULL_XY across
        but near its ends, PULL_CLIMB up or down a look, ending within PULL_Z."""
        climb, start, end = (PULL_CLIMB, PULL_Z, PULL_Z) if strict else (CLIMB, START_Z, END_Z)
        x, y = pts[0]
        if z0 is None:
            fl = [h for h, _d in self.floors(x, y)]
            if not fl:
                return None
            z = fl[0] if z1 is None else min(fl, key=lambda h: abs(h - z1))
        else:
            z = self.floor_near(x, y, z0, start)
            if z is None:
                return None
        hs = [z]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            d = math.hypot(bx - ax, by - ay)
            n = max(1, math.ceil(d / STEP))
            for s in range(1, n + 1):
                t = s / n
                xy = PULL_XY if strict and END_ROOM < d * t < d - END_ROOM else ON_XY
                h = self.floor_near(ax + (bx - ax) * t, ay + (by - ay) * t, z, climb, xy)
                if h is None:
                    return None
                z = h
            hs.append(z)
        if z1 is not None and abs(z - z1) > end:
            return None
        return hs

    def pull(self, pts, hs) -> list:
        """The points kept when the polyline (walked: its heights `hs`) is string-pulled over the mesh: from each kept
        point the furthest later one a straight walk (strict) reaches at its height."""
        out, i = [pts[0]], 0
        while i < len(pts) - 1:
            j = len(pts) - 1
            while j > i + 1:
                if self.walk([pts[i], pts[j]], hs[i], hs[j], strict=True) is not None:
                    break
                j -= 1
            out.append(pts[j])
            i = j
        return out


# --- the city's roads -----------------------------------------------------------------------------------------------

@dataclass
class Result:
    city: str
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    flags: list = field(default_factory=list)  # [{edge, at, yards, why}]


def city_edges(e: Entry, box) -> set:
    """The edges with a point inside the box (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    return {i for i, ed in enumerate(e.edges) if any(x0 <= x <= x1 and y0 <= y <= y1 for x, y in ed.pts)}


def _fixed_nodes(e: Entry, mine: set) -> set:
    """Nodes that stay: joins, and any end of a road not plain or not the city's."""
    keep = set(e.joins)
    for i, ed in enumerate(e.edges):
        if i not in mine or ed.src != PLAIN or i in e.drops:
            keep.update((ed.a, ed.b))
    return keep


def _z(e: Entry, n: int):
    return e.nz[n] if n < len(e.nz) else None


def stats(e: Entry, mine: set) -> dict:
    plain = [i for i in mine if e.edges[i].src == PLAIN and i not in e.drops]
    nodes = {n for i in mine for n in (e.edges[i].a, e.edges[i].b)}
    return {"roads": len(mine), "plain": len(plain), "nodes": len(nodes),
            "points": sum(len(e.edges[i].pts) for i in mine),
            "yards": round(sum(path_yards(e.edges[i].pts) for i in mine))}


def walk_edge(w: MeshWalk, e: Entry, ed: Edge):
    return w.walk(ed.pts, _z(e, ed.a), _z(e, ed.b))


def straighten(w: MeshWalk, e: Entry, mine: set, walked: dict) -> int:
    """String-pull each plain road of the city that walks on the mesh; the points dropped."""
    dropped = 0
    for i in sorted(mine):
        ed = e.edges[i]
        if ed.src != PLAIN or i in e.drops or len(ed.pts) <= 2:
            continue
        hs = walked.get(i)
        if hs is None:
            continue
        pts = w.pull(ed.pts, hs)
        hs2 = w.walk(pts, _z(e, ed.a), _z(e, ed.b)) if len(pts) < len(ed.pts) else None
        if hs2 is not None:
            dropped += len(ed.pts) - len(pts)
            ed.pts = pts
            ed.length = round(path_yards(pts))
            walked[i] = hs2
    return dropped


def _dist_within(adj, a, b, limit) -> bool:
    """Whether the kept roads (adj: node -> [(node, yards)]) join a and b within `limit` yards."""
    best = {a: 0.0}
    pq = [(0.0, a)]
    while pq:
        d, n = heapq.heappop(pq)
        if n == b:
            return True
        if d > best.get(n, math.inf):
            continue
        for m, yd in adj.get(n, ()):
            nd = d + yd
            if nd <= limit and nd < best.get(m, math.inf):
                best[m] = nd
                heapq.heappush(pq, (nd, m))
    return False


def thin(e: Entry, mine: set, walked: dict) -> set:
    """The plain roads of the city a greedy spanner leaves out (see the module's doc); returns the edges to drop."""
    adj: dict = {}

    def add(ed, yd):
        adj.setdefault(ed.a, []).append((ed.b, yd))
        adj.setdefault(ed.b, []).append((ed.a, yd))
    cand = []
    for i, ed in enumerate(e.edges):
        yd = path_yards(ed.pts) if ed.src != 5 else ed.length
        if i in mine and ed.src == PLAIN and i not in e.drops and walked.get(i) is not None and ed.a != ed.b:
            cand.append((yd, i))
        elif i in mine:
            add(ed, yd)  # (kept whatever: not plain, or not walked on the mesh)
    drop = set()
    for yd, i in sorted(cand):
        ed = e.edges[i]
        if _dist_within(adj, ed.a, ed.b, yd * STRETCH + SLACK_YD):
            drop.add(i)
        else:
            add(ed, yd)
    return drop


def _degree(e: Entry, live) -> dict:
    deg: dict = {}
    for i in live:
        ed = e.edges[i]
        deg[ed.a] = deg.get(ed.a, 0) + 1
        deg[ed.b] = deg.get(ed.b, 0) + 1
    return deg


def prune_stubs(e: Entry, mine: set, gone: set, walked: dict) -> set:
    """Dead-end plain roads of the city shorter than STUB_YD, again until none (their far end used by nothing else)."""
    fixed = _fixed_nodes(e, mine)
    out = set()
    while True:
        live = [i for i in range(len(e.edges)) if i not in gone and i not in out]
        deg = _degree(e, live)
        more = set()
        for i in live:
            ed = e.edges[i]
            if (i not in mine or ed.src != PLAIN or i in e.drops or walked.get(i) is None
                    or path_yards(ed.pts) >= STUB_YD):
                continue
            for end, other in ((ed.a, ed.b), (ed.b, ed.a)):
                if deg.get(end) == 1 and end not in fixed and deg.get(other, 0) > 1:
                    more.add(i)
                    break
        if not more:
            return out
        out |= more


def merge(w: MeshWalk, e: Entry, mine: set, gone: set, walked: dict, places=()) -> int:
    """Join two plain roads at a node they alone use into one (see the module's doc); the nodes joined over. Edges
    merged into another are added to `gone`; the road kept takes the joined points. The nodes within PLACE_NODE_YD of a
    place (x, y) stay: a stop there gets on the roads by them (from the Mining Trainer the way on went round a wall)."""
    fixed = _fixed_nodes(e, mine)
    for x, y in places:
        fixed.update(n for n, (nx, ny) in enumerate(e.nodes) if math.hypot(nx - x, ny - y) <= PLACE_NODE_YD)
    merged = 0
    ghosts: dict = {}  # edge -> [(x, y, height)]: the nodes merged over, whose heights its own must still read
    changed = True
    while changed:
        changed = False
        live = [i for i in range(len(e.edges)) if i not in gone]
        at: dict = {}
        for i in live:
            at.setdefault(e.edges[i].a, []).append(i)
            at.setdefault(e.edges[i].b, []).append(i)
        for n, es in at.items():
            if len(es) != 2 or n in fixed or es[0] == es[1]:
                continue
            i, j = es
            if not all(k in mine and e.edges[k].src == PLAIN and k not in e.drops and walked.get(k) is not None
                       for k in (i, j)):
                continue
            p, q = e.edges[i], e.edges[j]
            pi = p.pts if p.b == n else p.pts[::-1]
            qj = q.pts if q.a == n else q.pts[::-1]
            a, b = (p.a if p.b == n else p.b), (q.b if q.a == n else q.a)
            if a == b:
                continue
            pts = pi + qj[1:]
            za, zb = _z(e, a), _z(e, b)
            hs = w.walk(pts, za, zb)
            if hs is None or za is None or zb is None:
                continue
            pulled = w.pull(pts, hs)
            hs2 = w.walk(pulled, za, zb)
            if hs2 is None:
                pulled, hs2 = pts, hs
            # (the game reads the road's floor straight between its ends' heights: the floor along it must stay that
            # near the straight line between the floor's heights at its ends, as the two roads' did at the node)
            if not straight_heights(w, pulled, za, zb):
                continue
            # (and the heights the game reads along it, straight between its ends' `nz`, stay within NODE_Z of the
            # nodes' it passes: a stop's floor is matched by them, Router.OnFloor; else a road on another floor won)
            gh = ghosts.get(i, []) + ghosts.get(j, []) + [(*e.nodes[n], _z(e, n))]
            if any(hz is None or abs(read_height(pulled, za, zb, gx, gy) - hz) > NODE_Z for gx, gy, hz in gh):
                continue
            ghosts[i] = gh
            p.a, p.b, p.pts = a, b, pulled
            p.length = round(path_yards(pulled))
            walked[i] = hs2
            gone.add(j)
            walked.pop(j, None)
            merged += 1
            changed = True
            break
    return merged


def read_height(pts, za, zb, x, y) -> float:
    """The height the game reads on the road `pts` at its point nearest (x, y): straight between its ends' by yards."""
    total = path_yards(pts) or 1.0
    best, along = None, 0.0
    for p, q in zip(pts, pts[1:]):
        d = math.dist(p, q)
        t = 0.0 if d == 0 else max(0.0, min(1.0, ((x - p[0]) * (q[0] - p[0]) + (y - p[1]) * (q[1] - p[1])) / d / d))
        cx, cy = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
        dd = math.hypot(cx - x, cy - y)
        if best is None or dd < best[0]:
            best = (dd, along + d * t)
        along += d
    return za + (zb - za) * best[1] / total


def densify(pts, step: float = 2.0) -> list:
    out = [pts[0]]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        n = max(1, math.ceil(math.hypot(bx - ax, by - ay) / step))
        out += [(ax + (bx - ax) * s / n, ay + (by - ay) * s / n) for s in range(1, n + 1)]
    return out


def straight_heights(w: MeshWalk, pts, za, zb) -> bool:
    """Whether the floor along the road (walked from za to zb) stays within MERGE_Z of the straight line between the
    floor's heights at its two ends, by the yards along it."""
    dense = densify(pts)
    hs = w.walk(dense, za, zb)
    if hs is None:
        return False
    total = path_yards(dense) or 1.0
    along = 0.0
    for k, h in enumerate(hs):
        if k:
            along += math.dist(dense[k - 1], dense[k])
        if abs(h - (hs[0] + (hs[-1] - hs[0]) * along / total)) > MERGE_Z:
            return False
    return True


def compact(e: Entry, gone: set) -> None:
    """Drop the edges `gone` and the nodes no road uses (but joins), renumbering the rest."""
    keep_e = [i for i in range(len(e.edges)) if i not in gone]
    used = set(e.joins)
    for i in keep_e:
        used.update((e.edges[i].a, e.edges[i].b))
    if e.bridge:
        used.update(e.bridge)
    order = {n: k for k, n in enumerate(n for n in range(len(e.nodes)) if n in used)}
    e.nodes = [e.nodes[n] for n in sorted(order)]
    e.nz = [e.nz[n] for n in sorted(order)]
    new_e, drops = [], {}
    for k, i in enumerate(keep_e):
        ed = e.edges[i]
        ed.a, ed.b = order[ed.a], order[ed.b]
        if i in e.drops:
            drops[k] = e.drops[i]
        new_e.append(ed)
    e.edges, e.drops = new_e, drops
    e.joins = [order[j] for j in e.joins]
    if e.bridge is not None:
        e.bridge = [order[j] for j in e.bridge]


def process(e: Entry, w: MeshWalk, box, city: str, log=print, places=()) -> Result:
    res = Result(city)
    mine = city_edges(e, box)
    res.before = stats(e, mine)
    walked = {}
    for i in sorted(mine):
        ed = e.edges[i]
        if ed.src != PLAIN or i in e.drops:
            continue
        hs = walk_edge(w, e, ed)
        walked[i] = hs
        if hs is None:
            res.flags.append(_flag(w, e, i))
    log(f"  {city}: {res.before['roads']} roads, {res.before['plain']} plain, {len(res.flags)} the mesh can't walk")
    pulled = straighten(w, e, mine, walked)
    gone = thin(e, mine, walked)
    stubs = prune_stubs(e, mine, gone, walked)
    gone |= stubs
    merged = merge(w, e, mine, gone, walked, places)
    log(f"  {city}: {pulled} shape points pulled straight, {len(gone) - len(stubs) - merged} web roads and "
        f"{len(stubs)} stubs dropped, {merged} joined into one")
    res.after = stats(e, mine - gone)
    res.after["dropped"] = len(gone) - merged
    res.after["merged"] = merged
    flagged = {f["edge"] for f in res.flags}
    old = {i: k for k, i in enumerate(k for k in range(len(e.edges)) if k not in gone)}
    compact(e, gone)
    for f in res.flags:
        f["edge"] = old[f["edge"]] + 1 if f["edge"] in old else None
    assert all(f["edge"] is not None for f in res.flags), flagged
    return res


def city_places(city: str) -> list:
    """The city's places' spots (CityPlaces and the checks' own: capitals.map_places)."""
    from .capitals import CAPITALS, map_places

    return [(x, y) for _n, x, y in map_places(next(c for c in CAPITALS if c.name == city))]


def _flag(w: MeshWalk, e: Entry, i: int) -> dict:
    """Where a road leaves the mesh: its first point no walk reaches, and why."""
    ed = e.edges[i]
    za, zb = _z(e, ed.a), _z(e, ed.b)
    at, why = ed.pts[0], "its start is on no floor of the mesh at its height"
    if w.walk(ed.pts[:1], za) is not None:
        why = "it leaves the mesh"
        for k in range(1, len(ed.pts)):
            if w.walk(ed.pts[:k + 1], za) is None:
                at = ed.pts[k]
                break
        else:
            at, why = ed.pts[-1], "it ends off its end's height"
    return {"edge": i, "at": [at[0], at[1]], "z": [za, zb], "yards": round(path_yards(ed.pts)), "why": why}


# --- the file -------------------------------------------------------------------------------------------------------

def capitals_path() -> Path:
    return Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS" / "Data" / "Capitals.lua"


def mesh_walk(city: str) -> MeshWalk:
    from . import recastmesh as RM

    p = RM.mesh_path(city)
    if not p.exists():
        raise FileNotFoundError(f"no mesh for {city} at {p} (agps navmesh build)")
    return MeshWalk(NC.PolyIndex(RM.RecastMesh(RM.load(p), CITIES[city])))


def run(city: str = "Orgrimmar", write: bool = False, path: Path | None = None, log=print) -> Result:
    """One city's roads straightened and thinned (see the module's doc): the report, pictures and flags in
    data/debug/cityroads/, and with `write` Capitals.lua patched."""
    from .paths import data_dir

    path = path or capitals_path()
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    cont = CITIES[city]
    w = mesh_walk(city)
    e = read_entry(lines, cont)
    before = Entry(e.head, list(e.nodes), list(e.nz), [Edge(d.a, d.b, d.length, d.src, list(d.pts)) for d in e.edges],
                   list(e.joins), dict(e.drops), e.bridge, e.span)
    box = w.index.box
    res = process(e, w, box, city, log, city_places(city))
    out_dir = data_dir() / "debug" / "cityroads"
    out_dir.mkdir(parents=True, exist_ok=True)
    key = city.lower().replace(" ", "_")
    render(w.index, before, e, box, out_dir / f"{key}.png", res.flags)
    (out_dir / f"{key}_flags.json").write_text(json.dumps(res.flags, indent=1), encoding="utf-8")
    (out_dir / f"{key}.md").write_text(report_md(res, f"{key}.png"), encoding="utf-8")
    log(f"  {city}: before {res.before}, after {res.after}; wrote {out_dir}")
    if write:
        a, b = e.span
        lines[a:b + 1] = entry_lines(e)
        path.write_text("\n".join(lines), encoding="utf-8")
        log(f"  wrote {path}")
    return res


def render(index: NC.PolyIndex, before: Entry, after: Entry, box, out: Path, flags=(), scale: float = 1.5) -> None:
    """Before (left) and after (right): the mesh gray, plain roads blue, stairs yellow, lifts and drops orange, the
    flagged roads red; north up."""
    from PIL import Image, ImageDraw

    x0, y0, x1, y1 = box
    W, H = int((y1 - y0) * scale) + 1, int((x1 - x0) * scale) + 1
    im = Image.new("RGB", (W * 2 + 10, H), (20, 20, 24))
    d = ImageDraw.Draw(im)
    colors = {0: (60, 140, 255), 3: (255, 140, 0), 5: (255, 140, 0), 6: (255, 220, 0), 7: (0, 200, 200)}
    for k, e in enumerate((before, after)):
        ox = k * (W + 10)

        def px(x, y, ox=ox):
            return (ox + (y1 - y) * scale, (x1 - x) * scale)
        for vs in index.vs:
            d.polygon([px(v[0], v[1]) for v in vs], fill=(70, 70, 70))
        for i, ed in enumerate(e.edges):
            if not any(x0 <= x <= x1 and y0 <= y <= y1 for x, y in ed.pts):
                continue
            c = colors.get(3 if i in e.drops else ed.src, (200, 200, 200))
            d.line([px(x, y) for x, y in ed.pts], fill=c, width=2)
        if k == 1:
            for f in flags:
                ed = e.edges[f["edge"] - 1]
                d.line([px(x, y) for x, y in ed.pts], fill=(255, 50, 50), width=3)
    im.save(out)


def report_md(res: Result, png: str) -> str:
    b, a = res.before, res.after
    lines = [f"# {res.city}: roads straightened over the navmesh (issue #829)", "",
             "| | roads | plain | nodes | points | yards |", "|---|---|---|---|---|---|",
             f"| before | {b['roads']} | {b['plain']} | {b['nodes']} | {b['points']} | {b['yards']} |",
             f"| after | {a['roads']} | {a['plain']} | {a['nodes']} | {a['points']} | {a['yards']} |", "",
             f"Dropped {a['dropped']} roads (web and stubs), joined {a['merged']} pairs into one.", "",
             f"![before and after]({png})", "",
             "## For recording in game (the mesh can't walk these roads)", "",
             "| road | where (x, y) | heights (ends) | yd | why |", "|---|---|---|---|---|"]
    for f in res.flags:
        lines.append(f"| {f['edge']} | {f['at'][0]}, {f['at'][1]} | {f['z'][0]}, {f['z'][1]} | {f['yards']} | {f['why']} |")
    return "\n".join(lines) + "\n"


# --- the check ------------------------------------------------------------------------------------------------------

CHECK_PAIRS = 150  # place-to-place trips besides the one from outside to each place
TURN_DEG = 20.0  # a bend in a route sharper than this counts as a turn (the zigzags)


def _route_rows(city: str, replace: dict | None, seed: int = 829) -> list:
    """Routes in the city (the Router's own, under lupa, over the data as it is or as `replace` has it): from outside to
    each place (CityPlaces, the check's) at its height, and CHECK_PAIRS between two places. Each { trip, yards, turns,
    points, noWay }."""
    import random

    from .capitals import CAPITALS, map_places, place_heights
    from .gameharness import start

    cap = next(c for c in CAPITALS if c.name == city)
    lua, ns = start(replace=replace)
    R = ns.Router
    heights = place_heights(cap)
    places = map_places(cap)
    start_pt = ("outside", *(cap.outside or cap.gates[0]))
    trips = [(start_pt, p) for p in places]
    rnd = random.Random(seed)
    for _ in range(CHECK_PAIRS):
        a, b = rnd.sample(places, 2)
        trips.append((a, b))
    rows = []
    for (an, ax, ay), (bn, bx, by) in trips:
        R.Reset()
        za, zb = heights.get(an), heights.get(bn)
        opts = {k: v for k, v in (("z", za), ("tz", zb)) if v is not None}
        r = R.Route(cap.cont, ax, ay, bx, by, lua.table_from(opts))
        row = {"trip": f"{an} -> {bn}", "noWay": bool(r is None or r.noWay)}
        if r is not None and r.pts:
            flat = [r.pts[i] for i in range(1, len(r.pts) + 1)]
            pts = [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]
            row["yards"] = round(path_yards(pts), 1)
            row["points"] = len(pts)
            turns = 0
            for p, q, s in zip(pts, pts[1:], pts[2:]):
                h1 = math.atan2(q[1] - p[1], q[0] - p[0])
                h2 = math.atan2(s[1] - q[1], s[0] - q[0])
                if abs((math.degrees(h2 - h1) + 180) % 360 - 180) > TURN_DEG and math.dist(p, q) > 0.5:
                    turns += 1
            row["turns"] = turns
        rows.append(row)
    return rows


def check(city: str = "Orgrimmar", against: str = "HEAD", log=print) -> dict:
    """The city's routes over Capitals.lua as `against` had it and as it is now, side by side: yards, turns, way found."""
    import subprocess

    repo = Path(__file__).resolve().parents[2]
    old = subprocess.run(["git", "show", f"{against}:addon/AzerothGPS/Data/Capitals.lua"], cwd=repo, capture_output=True,
                         check=True).stdout.decode("utf-8")
    before = _route_rows(city, {"Data/Capitals.lua": old})
    after = _route_rows(city, None)
    out = {"trips": len(after), "lost": [], "found": [], "longer": [], "rows": []}
    tot = {"yards": [0.0, 0.0], "turns": [0, 0]}
    for b, a in zip(before, after):
        out["rows"].append({"trip": a["trip"], "before": b, "after": a})
        if a["noWay"] and not b["noWay"]:
            out["lost"].append(a["trip"])
        elif b["noWay"] and not a["noWay"]:
            out["found"].append(a["trip"])
        elif not a["noWay"] and "yards" in a and "yards" in b:
            for k in tot:
                tot[k][0] += b[k]
                tot[k][1] += a[k]
            if a["yards"] > b["yards"] * 1.10 + 10:
                out["longer"].append((a["trip"], b["yards"], a["yards"]))
    out["totals"] = tot
    log(f"  {city}: {len(after)} trips; yards {tot['yards'][0]:.0f} -> {tot['yards'][1]:.0f}, turns {tot['turns'][0]} -> "
        f"{tot['turns'][1]}; ways lost {len(out['lost'])}, found "
        f"{len(out['found'])}; 10% and 10 yd longer: {len(out['longer'])}")
    for t in out["lost"] + [f"{t} ({b:.0f} -> {a:.0f} yd)" for t, b, a in out["longer"]]:
        log(f"    {t}")
    return out
