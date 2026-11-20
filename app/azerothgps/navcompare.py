"""The routing data's roads in the cities against our own Recast meshes of them (asked 2026-11-18: "evaluate all navmesh
data in all cities combined with our roadmap data ... to improve our roads and pathing"). A dev tool only: nothing ships.

For each city mesh (recastmesh.sources: the five capitals and Undercity):
- **Roads off the mesh:** every road the Router has inside the mesh's box, sampled every yard at its height (a capital's
  and a building's roads by their nodes' `nz`, read straight between the two ends as the game reads a road's floor;
  Undercity's by its level's `z` (the game's heights); a land road with no height: any floor under it). A sample is on the mesh
  when a walkable poly lies within ON_XY of it and ON_Z of its height. Runs of OFF_RUN yards or more off it are listed:
  a road through a wall, over a gap, along a floor the mesh left out, or a road whose height is wrong.
- **Ground no road reaches:** the mesh's walkable polys (its biggest connected piece and the pieces over GAP_MIN_AREA)
  more than GAP_YD from every road sample, joined into blobs on a GAP_CELL grid; the blobs over GAP_MIN_AREA listed with
  the city places in or near them: streets, rooms or terraces the roads miss (or plazas that need none).

Read the mesh's verdict with care: it is built from the same collision faces as the capital grids (recastmesh.py), with a
player-sized agent, but doors, gates and lifts the server spawns (gameobjects) aren't in it, and its doodads are only those
with collision placed in the ADTs. It is a second opinion, not the truth: drawn roads (source 2) are the truth.
Writes data/debug/navcompare/<city>.md, .json, .png and summary.md."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from . import navmesh as NM
from . import recastmesh as RM

ON_XY = 1.5  # yards: a sample this near a walkable poly (across) ...
ON_Z = 2.5  # ... and this near its height there is on the mesh
OFF_RUN = 3.0  # yards: runs off the mesh this long or longer are listed
INDEX_CELL = 8.0  # yards: the polys' lookup grid
GAP_YD = 20.0  # yards: a walkable poly this far from every road sample is ground no road reaches
GAP_CELL = 6.0  # yards: the gaps' grid
GAP_MIN_AREA = 150.0  # square yards: smaller gap blobs (a corner, a stall's back) aren't listed
SKIP_SOURCES = (4, 5, 7)  # drops, lifts and swims: off the walked floors by nature
NO_HEIGHT = -9000.0  # (a node's height under this is a marker for none: -10000)
SOURCES = {0: "extracted", 1: "texture", 2: "drawn", 3: "npc path", 4: "drop", 5: "lift", 6: "stairs", 7: "swim"}


class PolyIndex:
    """A mesh's walkable polys (2D outline, heights) and a grid to find those near a spot."""

    def __init__(self, mesh: NM.NavMesh):
        self.mesh = mesh
        self.keys, self.vs, self.area = [], [], []
        for key, i, t, p in mesh._polys():
            self.keys.append((key, i))
            self.vs.append([t.verts[v] for v in p["verts"]])
            self.area.append(p["area"])
        self.grid = defaultdict(list)
        self.bbox = []
        for pid, vs in enumerate(self.vs):
            xs = [v[0] for v in vs]
            ys = [v[1] for v in vs]
            self.bbox.append((min(xs), min(ys), max(xs), max(ys)))
            for gx in range(int(math.floor(min(xs) / INDEX_CELL)), int(math.floor(max(xs) / INDEX_CELL)) + 1):
                for gy in range(int(math.floor(min(ys) / INDEX_CELL)), int(math.floor(max(ys) / INDEX_CELL)) + 1):
                    self.grid[(gx, gy)].append(pid)
        allx = [b[0] for b in self.bbox] + [b[2] for b in self.bbox]
        ally = [b[1] for b in self.bbox] + [b[3] for b in self.bbox]
        self.box = (min(allx), min(ally), max(allx), max(ally)) if allx else (0, 0, 0, 0)

    def near(self, x, y, reach):
        seen = set()
        for gx in range(int(math.floor((x - reach) / INDEX_CELL)), int(math.floor((x + reach) / INDEX_CELL)) + 1):
            for gy in range(int(math.floor((y - reach) / INDEX_CELL)), int(math.floor((y + reach) / INDEX_CELL)) + 1):
                for pid in self.grid.get((gx, gy), ()):
                    if pid in seen:
                        continue
                    seen.add(pid)
                    b = self.bbox[pid]
                    if b[0] - reach <= x <= b[2] + reach and b[1] - reach <= y <= b[3] + reach:
                        yield pid

    def floors(self, x, y, reach=ON_XY):
        """[(dz-free height, pid, dist across)] of the walkable polys within `reach` of (x, y)."""
        out = []
        for pid in self.near(x, y, reach):
            vs = self.vs[pid]
            if NM._in_poly(vs, x, y):
                out.append((NM._height_on(vs, x, y), pid, 0.0))
            else:
                d = math.sqrt(NM._dist2_poly(vs, x, y))
                if d <= reach:
                    px, py = NM._closest_on_poly(vs, x, y)
                    out.append((NM._height_on(vs, px, py), pid, d))
        return out

    def on(self, x, y, z):
        """(on the mesh?, the nearest floor's height or None, how far off in height)"""
        fl = self.floors(x, y)
        if not fl:
            return False, None, None
        if z is None:
            return True, fl[0][0], 0.0
        h = min(fl, key=lambda f: abs(f[0] - z))[0]
        return abs(h - z) <= ON_Z, h, h - z

    def centroid(self, pid):
        vs = self.vs[pid]
        return (sum(v[0] for v in vs) / len(vs), sum(v[1] for v in vs) / len(vs), sum(v[2] for v in vs) / len(vs))

    def poly_area(self, pid):
        vs = self.vs[pid]
        return abs(sum(vs[k][0] * vs[(k + 1) % len(vs)][1] - vs[(k + 1) % len(vs)][0] * vs[k][1]
                       for k in range(len(vs)))) / 2


def components(mesh: NM.NavMesh, index: PolyIndex) -> list[int]:
    """Each poly's connected piece of the mesh (0 the biggest)."""
    pid_of = {k: p for p, k in enumerate(index.keys)}
    comp = [-1] * len(index.keys)
    sizes = []
    for start in range(len(index.keys)):
        if comp[start] >= 0:
            continue
        c = len(sizes)
        comp[start] = c
        stack, n = [start], 0
        while stack:
            p = stack.pop()
            n += 1
            key, i = index.keys[p]
            for nb, _edge in mesh.neighbors(key, i):
                q = pid_of.get(nb)
                if q is not None and comp[q] < 0:
                    comp[q] = c
                    stack.append(q)
        sizes.append(n)
    order = sorted(range(len(sizes)), key=lambda c: -sizes[c])
    rank = {c: r for r, c in enumerate(order)}
    return [rank[c] for c in comp]


def road_samples(g, box, zoff: float = 0.0, step: float = 1.0):
    """The graph's roads within `box` (x0, y0, x1, y1), each sampled every `step` yards: [(edge id, source, [(x, y,
    z or None)])]. Heights from `g.z` (a level's, plus zoff) or `g.nz` (a capital's or building's floors), read straight
    between the edge's ends by the distance along it."""
    x0, y0, x1, y1 = box
    hz = g.z if g.z is not None else g.nz
    out = []
    for eid in g.e.keys():
        e = g.e[eid]
        if int(e[4]) in SKIP_SOURCES:
            continue
        pts = [(e[k], e[k + 1]) for k in range(5, len(e), 2)]
        if not any(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in pts):
            continue
        za = hz[e[1]] if hz is not None else None
        zb = hz[e[2]] if hz is not None else None
        if (za is not None and za < NO_HEIGHT) or (zb is not None and zb < NO_HEIGHT):
            za = zb = None
        if za is not None and g.z is None and za == 0 and zb == 0:
            za = zb = None  # (a land road: no height of its own)
        length = sum(math.dist(pts[k], pts[k + 1]) for k in range(len(pts) - 1)) or 1.0
        samples, along = [], 0.0
        for k in range(len(pts) - 1):
            (ax, ay), (bx, by) = pts[k], pts[k + 1]
            d = math.dist(pts[k], pts[k + 1])
            n = max(1, int(d / step))
            for s in range(n):
                t = s / n
                a = along + d * t
                z = None if za is None or zb is None else za + (zb - za) * a / length + zoff
                samples.append((ax + (bx - ax) * t, ay + (by - ay) * t, z))
            along += d
        z = None if za is None or zb is None else zb + zoff
        samples.append((pts[-1][0], pts[-1][1], z))
        out.append((int(eid), int(e[4]), samples))
    return out


def compare(name: str, cont: int, level, tiles: dict, g, places=(), zoff: float = 0.0, log=print, inside=None) -> dict:
    """One city's comparison (see the module's doc): a dict for the report. `inside(x, y)`: whether a spot is the
    city's own ground (its grid's cells, not the land round it): only gaps there are listed."""
    mesh = RM.RecastMesh(tiles, cont)
    index = PolyIndex(mesh)
    comp = components(mesh, index)
    x0, y0, x1, y1 = index.box
    roads = road_samples(g, (x0, y0, x1, y1), zoff)
    runs, total, off_total, nohit = [], 0, 0, 0
    road_pts = []
    for eid, src, samples in roads:
        cur = None
        for (x, y, z) in samples:
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                if cur:
                    runs.append(cur)
                    cur = None
                continue
            total += 1
            road_pts.append((x, y))
            ok, h, dz = index.on(x, y, z)
            if ok:
                if cur:
                    runs.append(cur)
                    cur = None
                continue
            off_total += 1
            if h is None:
                nohit += 1
            if cur is None:
                cur = {"edge": eid, "source": SOURCES.get(src, str(src)), "pts": [], "dz": []}
            cur["pts"].append((round(x, 1), round(y, 1), None if z is None else round(z, 1)))
            cur["dz"].append(None if dz is None else round(dz, 1))
        if cur:
            runs.append(cur)
    runs = [r for r in runs if len(r["pts"]) >= OFF_RUN]
    for r in runs:
        dzs = [d for d in r["dz"] if d is not None]
        r["yards"] = len(r["pts"])
        r["why"] = ("no walkable floor under it (a wall, rock or a gap)" if not dzs else
                    f"the nearest floor is {abs(np.median(dzs)):.0f} yd {'over' if np.median(dzs) > 0 else 'under'} the road")
        r["at"] = r["pts"][len(r["pts"]) // 2]
    runs.sort(key=lambda r: -r["yards"])
    # ground no road reaches
    gaps = []
    if road_pts:
        from scipy.spatial import cKDTree

        tree = cKDTree(np.array(road_pts))
        cells = defaultdict(lambda: [0.0, [], 0.0])
        sizes = defaultdict(float)
        for pid in range(len(index.keys)):
            sizes[comp[pid]] += index.poly_area(pid)
        for pid in range(len(index.keys)):
            if comp[pid] != 0 and sizes[comp[pid]] < GAP_MIN_AREA:
                continue  # (a roof, a ledge, a table: pieces no one walks onto)
            cx, cy, cz = index.centroid(pid)
            if inside is not None and not inside(cx, cy):
                continue
            d, _ = tree.query((cx, cy))
            if d <= GAP_YD:
                continue
            c = cells[(int(cx // GAP_CELL), int(cy // GAP_CELL))]
            c[0] += index.poly_area(pid)
            c[1].append((cx, cy, cz))
            c[2] = max(c[2], d)
        seen = set()
        for start in list(cells):
            if start in seen:
                continue
            blob, stack = [], [start]
            seen.add(start)
            while stack:
                k = stack.pop()
                blob.append(k)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nk = (k[0] + dx, k[1] + dy)
                        if nk in cells and nk not in seen:
                            seen.add(nk)
                            stack.append(nk)
            area = sum(cells[k][0] for k in blob)
            if area < GAP_MIN_AREA:
                continue
            pts = [p for k in blob for p in cells[k][1]]
            xs, ys, zs = [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts]
            mid = (sum(xs) / len(xs), sum(ys) / len(ys))
            near = [p[0] for p in places if math.dist(mid, (p[1], p[2])) <= 30 + max(max(xs) - min(xs), max(ys) - min(ys)) / 2]
            gaps.append({"at": (round(mid[0], 1), round(mid[1], 1), round(float(np.median(zs)), 1)),
                         "area": round(area), "box": (round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))),
                         "far": round(max(cells[k][2] for k in blob)), "places": near})
        gaps.sort(key=lambda b: -b["area"])
    out = {"city": name, "cont": cont, "level": level, "polys": len(index.keys), "box": index.box,
           "roads": len(roads), "samples": total, "off": off_total, "off_no_floor": nohit,
           "off_share": round(off_total / max(total, 1), 4), "runs": runs, "gaps": gaps}
    log(f"  {name}: {len(roads)} roads, {total} yards sampled, {off_total} off the mesh ({out['off_share']:.1%}; "
        f"{nohit} over no floor at all), {len(runs)} runs of {OFF_RUN:.0f}+ yd, {len(gaps)} gap areas")
    return out


def render(res: dict, index: PolyIndex, roads, out: Path, scale: float = 2.0) -> None:
    """The mesh (gray), the roads (blue), the runs off it (red) and the gaps (yellow boxes); north up."""
    from PIL import Image, ImageDraw

    x0, y0, x1, y1 = res["box"]
    W, H = int((y1 - y0) * scale) + 1, int((x1 - x0) * scale) + 1  # (north up: world x up, world y left)

    def px(x, y):
        return ((y1 - y) * scale, (x1 - x) * scale)
    im = Image.new("RGB", (W, H), (20, 20, 24))
    d = ImageDraw.Draw(im)
    for pid, vs in enumerate(index.vs):
        d.polygon([px(v[0], v[1]) for v in vs], fill=(70, 80, 95) if index.area[pid] == 9 else (105, 105, 105))
    for _eid, _src, samples in roads:
        d.line([px(s[0], s[1]) for s in samples], fill=(60, 140, 255), width=2)
    for r in res["runs"]:
        d.line([px(p[0], p[1]) for p in r["pts"]], fill=(255, 50, 50), width=3)
    for b in res["gaps"]:
        bx0, by0, bx1, by1 = b["box"]
        a, c = px(bx1, by1), px(bx0, by0)
        d.rectangle([a, c], outline=(255, 220, 0), width=2)
    im.save(out)


def report_md(res: dict, png: str) -> str:
    lines = [f"# {res['city']}: roads against the Recast mesh", "",
             f"- Mesh: {res['polys']} walkable polys. Roads in its box: {res['roads']}, {res['samples']} yards sampled.",
             f"- Off the mesh: {res['off']} yd ({res['off_share']:.1%}), of which {res['off_no_floor']} yd over no "
             f"walkable floor at all; {len(res['runs'])} runs of {OFF_RUN:.0f} yd or more.",
             f"- Ground no road comes within {GAP_YD:.0f} yd of: {len(res['gaps'])} areas over {GAP_MIN_AREA:.0f} sq yd.",
             "", f"![render]({png})", "", "## Runs off the mesh (longest first)", "",
             "| yd | road | source | middle (x, y, z) | why |", "|---|---|---|---|---|"]
    for r in res["runs"][:60]:
        lines.append(f"| {r['yards']} | {r['edge']} | {r['source']} | {r['at']} | {r['why']} |")
    lines += ["", "## Ground no road reaches (largest first)", "",
              "| sq yd | middle (x, y, z) | box | furthest from a road | places near |", "|---|---|---|---|---|"]
    for b in res["gaps"][:40]:
        lines.append(f"| {b['area']} | {b['at']} | {b['box']} | {b['far']} yd | {', '.join(b['places'][:4])} |")
    return "\n".join(lines) + "\n"


def run(only=None, log=print) -> list[dict]:
    """Every city mesh built (data/navmesh/*.pkl) against the addon's roads, under the game harness."""
    from .capitals import CAPITALS, map_places
    from .gameharness import start
    from .paths import data_dir

    out_dir = data_dir() / "debug" / "navcompare"
    out_dir.mkdir(parents=True, exist_ok=True)
    lua, ns = start()
    R = ns.Router
    caps = {c.name: c for c in CAPITALS}
    results = []
    for name, cont, level, _fn in RM.sources():
        if only and not any(o.lower() in name.lower() for o in only):
            continue
        p = RM.mesh_path(name)
        if not p.exists():
            log(f"  {name}: no mesh at {p} (agps navmesh build)")
            continue
        tiles = RM.load(p)
        gl = level if level is not None else cont
        mesh = RM.RecastMesh(tiles, cont)
        box = PolyIndex(mesh).box
        R.NearestEdges(gl, (box[0] + box[2]) / 2, (box[1] + box[3]) / 2)  # (the level's roads built)
        g = R.DebugGraph(gl)
        zoff = 0.0  # (the graph's heights on a level are the game's already: Router adds the level's zoff)
        cap = caps.get(name)
        places = map_places(cap) if cap else []
        inside = None
        if level is None:  # (a capital: its own grid's cells, not the continent's round it)
            ov = ns.Passability.Overlay

            def inside(x, y, cont=cont, ov=ov):
                return ov(cont, x, y) not in (None, 1)
        res = compare(name, cont, level, tiles, g, places, zoff, log, inside)
        key = name.lower().replace(" ", "_")
        index = PolyIndex(mesh)
        render(res, index, road_samples(g, index.box, zoff), out_dir / f"{key}.png")
        (out_dir / f"{key}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
        (out_dir / f"{key}.md").write_text(report_md(res, f"{key}.png"), encoding="utf-8")
        results.append(res)
    summary = ["# Roads against the Recast meshes", "", "| city | roads | yards | off the mesh | over no floor | runs | gap areas |",
               "|---|---|---|---|---|---|---|"]
    for r in results:
        summary.append(f"| {r['city']} | {r['roads']} | {r['samples']} | {r['off']} ({r['off_share']:.1%}) | "
                       f"{r['off_no_floor']} | {len(r['runs'])} | {len(r['gaps'])} |")
    (out_dir / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    log(f"wrote {out_dir}")
    return results
