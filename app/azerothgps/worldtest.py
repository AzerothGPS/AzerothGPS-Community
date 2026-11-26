"""The world grid's route test (asked 2026-11-22: "Test going from city to open world spots and vice versa. I want 10000
test routes to various NPCs"): trips between shipped NPC spawns (Data/Npcs.lua, with their heights) on both
continents, each routed by the Router with the world grid's option off (today's routing) and on (the world grid, the
capitals' grids with it), each route walked over our own Recast meshes of the map (worldmesh.py): yards off the mesh,
runs off it past CHECK_OFF_YD (through a wall, over a gap), impossible climbs, and the end's floor against the NPC's.

Dev only. Output (data and report) to OUT (outside the repos)."""

from __future__ import annotations

import json
import math
import os
import random
import re
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np

from . import navmesh as NM
from . import worldmesh as WM
from .paths import ADDON_DIR, data_dir

OUT = Path(os.environ.get("AGPS_WORLDTEST_OUT") or data_dir() / "debug" / "worldgrid" / "test")  # (kept outside the repos)
STEP = 2.0  # yards: a route walked this often over the mesh
ON_XY = 1.5  # yards: a point is on the mesh with a walkable poly this near across ...
ON_Z = 3.5  # ... and this near its height, when the route has one
CHECK_OFF_YD = 3.0  # a run off the mesh this long: through a wall or over a gap
CLIMB_MAX = 4.0  # yards up between two samples STEP apart with no floor between: a climb no player makes ...
CLIMB_REACH = 4.0  # ... and none of the floor it was on within this many yards across
END_FLOOR_Z = 5.0  # the route's end this far over or under the NPC's height: the wrong floor
MIX = (("city>open", 0.2), ("open>city", 0.2), ("open>open", 0.45), ("city>city", 0.15))
MAX_YD = 5000.0  # straight yards between a trip's ends (a walk; a farther one is the planner's, with rides)


# --- the trips ----------------------------------------------------------------------------------------------------------

def npc_spots() -> list:
    """[(id, name, cont, x, y, z)]: each shipped NPC's spawns on the continents (one per NPC per 100 yd)."""
    txt = (ADDON_DIR / "Data" / "Npcs.lua").read_text(encoding="utf-8")
    body = txt[txt.index("[==[") + 4:txt.index("]==]")]
    out = []
    for line in body.splitlines():
        p = line.split("|")
        if len(p) < 7:
            continue
        seen = []
        for sp in p[6].split(";"):
            m = re.match(r"\s*(-?\d+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)", sp)
            if not m:
                continue
            lv, x, y, z = int(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))
            if lv not in (0, 1) or any(math.dist((x, y), s) < 100 for s in seen):
                continue
            seen.append((x, y))
            out.append((int(p[0]), p[1], lv, x, y, z))
    return out


def make_trips(n: int, seed: int = 10000) -> list:
    """`n` trips by MIX: each {kind, cont, from (name, x, y, z), to (name, x, y, z)} with its ends at most MAX_YD apart."""
    from .gameharness import start

    lua, ns = start()
    CG = ns.CityGrid
    spots = npc_spots()
    city, open_ = {0: [], 1: []}, {0: [], 1: []}
    for s in spots:
        c = CG.CityFor(s[2], s[3], s[4])
        (city if c else open_)[s[2]].append(s + (c,))
    rnd = random.Random(seed)
    trips = []
    for kind, share in MIX:
        want = int(round(n * share))
        a_city, b_city = kind.startswith("city"), kind.endswith("city")
        got = 0
        tries = 0
        while got < want and tries < want * 200:
            tries += 1
            cont = rnd.choice((0, 1))
            A = (city if a_city else open_)[cont]
            B = (city if b_city else open_)[cont]
            a = rnd.choice(A)
            far = rnd.uniform(300.0, MAX_YD)  # (the trips' lengths spread over the range, not all near the most)
            near = [b for b in B if b is not a and 60 <= math.dist(a[3:5], b[3:5]) <= far]
            if not near:
                continue
            b = rnd.choice(near)
            trips.append({"id": len(trips), "kind": kind, "cont": cont, "from": [a[1], a[3], a[4], a[5], a[6]],
                          "to": [b[1], b[3], b[4], b[5], b[6]]})
            got += 1
    rnd.shuffle(trips)
    for k, t in enumerate(trips):
        t["id"] = k
    return trips


# --- the mesh ------------------------------------------------------------------------------------------------------------

class MeshIndex:
    """The world meshes' walkable polys near a spot, tiles loaded as asked (a few kept)."""

    CELL = 8.0

    def __init__(self, cont: int, keep: int = 24):
        self.cont, self.keep = cont, keep
        self.tiles: OrderedDict = OrderedDict()

    def _tile(self, tx, ty):
        k = (tx, ty)
        if k in self.tiles:
            self.tiles.move_to_end(k)
            return self.tiles[k]
        path = WM.tile_path(self.cont, tx, ty)
        got = WM.parse(path.read_bytes()) if path.exists() and path.stat().st_size >= 12 else None
        idx = None
        if got is not None:
            polys = [p for p in got if p[2]]
            bx = WM.tile_box(tx, ty)
            grid = {}
            for pi, (vs, _ns, _a) in enumerate(polys):
                x0, y0 = vs[:, 0].min(), vs[:, 1].min()
                x1, y1 = vs[:, 0].max(), vs[:, 1].max()
                if x1 < bx[0] - 2 or x0 > bx[2] + 2 or y1 < bx[1] - 2 or y0 > bx[3] + 2:
                    continue
                for gx in range(int(math.floor(x0 / self.CELL)), int(math.floor(x1 / self.CELL)) + 1):
                    for gy in range(int(math.floor(y0 / self.CELL)), int(math.floor(y1 / self.CELL)) + 1):
                        grid.setdefault((gx, gy), []).append(pi)
            idx = ([[tuple(v) for v in p[0]] for p in polys], grid)
        self.tiles[k] = idx
        while len(self.tiles) > self.keep:
            self.tiles.popitem(last=False)
        return idx

    def water(self, x: float, y: float) -> bool:
        """Whether the terrain grid has water at (x, y) (Data/Terrain.lua's 1; the world grid swims there)."""
        from . import worldgrid as W
        if not hasattr(self, "wg"):
            self.wg = W.water_grid(self.cont)
        return bool(self.wg) and W.terrain_water(self.wg, x, y)

    def floors(self, x: float, y: float, reach: float = ON_XY) -> list:
        """The heights of the walkable polys within `reach` of (x, y)."""
        tx, ty = WM.tile_of(x, y)
        t = self._tile(tx, ty)
        if t is None:
            return []
        vss, grid = t
        out = []
        seen = set()
        for gx in range(int(math.floor((x - reach) / self.CELL)), int(math.floor((x + reach) / self.CELL)) + 1):
            for gy in range(int(math.floor((y - reach) / self.CELL)), int(math.floor((y + reach) / self.CELL)) + 1):
                for pi in grid.get((gx, gy), ()):
                    if pi in seen:
                        continue
                    seen.add(pi)
                    vs = vss[pi]
                    if NM._in_poly(vs, x, y):
                        out.append(NM._height_on(vs, x, y))
                    elif NM._dist2_poly(vs, x, y) <= reach * reach:
                        px, py = NM._closest_on_poly(vs, x, y)
                        out.append(NM._height_on(vs, px, py))
        return out


def judge(index: MeshIndex, pts: list, hs: list | None, z0: float | None, z1: float | None, skip=None) -> dict:
    """A route (flat points x, y, ...; heights or None) walked over the mesh every STEP: yards, yards off it, runs off
    it past CHECK_OFF_YD, climbs past CLIMB_MAX, and the floor it ends on (followed from the start's height)."""
    n = len(pts) // 2
    total = off = run = 0.0
    walls = climbs = drops = 0
    worst = swum = linked = 0.0
    fz = z0
    retake = False
    for i in range(n - 1):
        ax, ay, bx, by = pts[2 * i], pts[2 * i + 1], pts[2 * i + 2], pts[2 * i + 3]
        za = hs[i] if hs else None
        zb = hs[i + 1] if hs else None
        L = math.hypot(bx - ax, by - ay)
        if skip and skip[i]:  # (a ride, a drop or a road link over what the mesh lacks: not judged, counted)
            total += L
            linked += L
            run = 0.0
            # (the floor taken again past it, at the route's own height when it has one: else the next step past a
            # road link up a gap, a lift or a drop was a climb from the floor at its foot; main's and the grid's alike)
            retake = zb if zb is not None else True
            continue
        m = max(1, int(L / STEP))
        for q in range(m):
            t = q / m
            x, y = ax + (bx - ax) * t, ay + (by - ay) * t
            z = za + (zb - za) * t if (za is not None and zb is not None) else None
            fl = index.floors(x, y)
            if z is not None:
                fl_ok = [f for f in fl if abs(f - z) <= ON_Z]
            else:
                fl_ok = fl
            step = L / m
            total += step
            if not fl_ok and index.water(x, y):
                swum += step  # (swum: the terrain grid's water, Recast doesn't swim)
                if run > CHECK_OFF_YD:
                    walls += 1
                run = 0.0
                continue
            if fl_ok:
                if run > CHECK_OFF_YD:
                    walls += 1
                run = 0.0
                # (the floor followed: the nearest to the last one; with the route's height, the nearest to it)
                ref = z if z is not None else fz
                if retake is not False and retake is not True:
                    ref = retake
                nf = min(fl_ok, key=lambda f: abs(f - ref)) if ref is not None else min(fl_ok)
                if retake is not False:
                    retake = False
                elif fz is not None and abs(nf - fz) > CLIMB_MAX:
                    # (the floor it was on, a few yards off: a line along a ledge's edge or a branch's, still on it)
                    wide = [f for f in index.floors(x, y, CLIMB_REACH) if abs(f - fz) <= CLIMB_MAX]
                    if wide:
                        nf = min(wide, key=lambda f: abs(f - fz))
                    elif nf > fz:
                        climbs += 1
                    elif fz - nf > 2 * CLIMB_MAX:
                        drops += 1
                fz = nf
            else:
                off += step
                run += step
                worst = max(worst, run)
    if run > CHECK_OFF_YD:
        walls += 1
    end_off = abs(fz - z1) if (fz is not None and z1 is not None) else None
    return {"yd": round(total, 1), "off_yd": round(off, 1), "swum_yd": round(swum, 1), "link_yd": round(linked, 1), "walls": walls, "worst_off": round(worst, 1),
            "climbs": climbs, "drops": drops, "end_floor_off": None if end_off is None else round(end_off, 1)}


# --- routing (a worker each) ----------------------------------------------------------------------------------------------

_H: dict = {}


def _route(ns, lua, cont, a, b, world: bool):
    R = ns.Router
    ns.settings.gps.worldGrid = world
    ns.settings.gps.cityGrid = False
    if world:
        ns.WorldGrid.routes, ns.WorldGrid.order = lua.table(), lua.table()
        ns.CityGrid.routes, ns.CityGrid.order = lua.table(), lua.table()
    t = time.perf_counter()
    r = R.Route(cont, a[1], a[2], b[1], b[2], lua.table(z=a[3], tz=b[3]))
    ms = (time.perf_counter() - t) * 1000
    ns.settings.gps.worldGrid = False
    if r is None or r.pts is None or len(r.pts) < 4:
        return {"found": False, "ms": round(ms, 1)}, None, None
    pts = [float(r.pts[i]) for i in range(1, len(r.pts) + 1)]
    hz = r.fz if r.fz is not None else r.zs
    hs = None
    if hz is not None:
        hs = []
        for i in range(1, len(pts) // 2 + 1):
            v = hz[i]
            hs.append(float(v) if (v is not None and v is not False and v > -9000) else None)
        gp = r.gpts  # (CityGrid's Concat: which points' heights are a grid's own; the Router's road's are left out)
        if gp is not None:
            hs = [h if gp[i + 1] else None for i, h in enumerate(hs)]
        elif not (r.worldGrid or r.cityGrid):
            hs = None
        if hs is not None and all(h is None for h in hs):
            hs = None
    kinds = [int(r.kinds[i]) for i in range(1, len(r.kinds) + 1)] if r.kinds is not None else []
    road = sum(math.hypot(pts[2 * i + 2] - pts[2 * i], pts[2 * i + 3] - pts[2 * i + 1]) for i, k in enumerate(kinds) if k == 0)
    out = {"found": not (r.noWay or r.unconnected), "yd": round(float(r.length), 1), "ms": round(ms, 1),
           "points": len(pts) // 2, "road_yd": round(road, 1), "grid": bool(r.worldGrid) or bool(r.cityGrid),
           "city": bool(r.cityGrid), "hops": int(r.hops or 0), "blocked": bool(r.blocked)}
    onl = r.onLink
    out["skip"] = [bool(k in (4, 5, 6) or (onl is not None and onl[i + 1])) for i, k in enumerate(kinds)]
    return out, pts, hs


def run_trip(trip: dict) -> dict:
    if "ns" not in _H:
        from .gameharness import start
        alt = os.environ.get("AGPS_WT_DATA_DIR")  # (a trial bake's addon folders instead: AGPS_WORLDGRID_OUT's)
        rep = None
        if alt:
            rep = {f"Data/{p.name}": p.read_text(encoding="utf-8")
                   for p in (Path(alt) / "AzerothGPS" / "Data").glob("WorldGrid*.lua")}
            os.environ["AGPS_WG_ADDONS_DIR"] = alt  # (its regions' folders, gameharness's LoadAddOn)
        lua, ns = start(replace=rep)
        ns.Router.SYNC_WALKS = True
        road = os.environ.get("AGPS_WG_ROAD")  # (the road preference tried at another value than the data's)
        if road:
            for c in (0, 1, 2991):
                if ns.WorldGridData[c] is not None:
                    ns.WorldGridData[c].road = float(road)
        tol = os.environ.get("AGPS_WT_ROAD_TOL")  # (Options > Routing's Road tolerance at another value than the default)
        if tol:
            ns.settings.gps.roadTolerance = float(tol)
        for k in ("LINE_TOL", "LINE_TOL_EDGE"):  # (a trial's string-pulling tolerance, WorldGrid.lua's)
            v = os.environ.get("AGPS_WG_" + k)
            if v:
                ns.WorldGrid[k] = float(v)
        _H.update(lua=lua, ns=ns, idx={})
    lua, ns = _H["lua"], _H["ns"]
    cont = trip["cont"]
    index = _H["idx"].setdefault(cont, MeshIndex(cont))
    a, b = trip["from"], trip["to"]
    res = dict(trip)
    engines = os.environ.get("AGPS_WT_ENGINES", "main,grid").split(",")  # (a sweep of the grid alone: "grid")
    for name, world in (("main", False), ("grid", True)):
        if name not in engines:
            continue
        try:
            ns.Router.Reset()
            r, pts, hs = _route(ns, lua, cont, a, b, world)
            if pts:
                # (both judged without their heights: the Router's own carry a start's height on over the land, its
                # roads have none; the floor is followed over the mesh from the start's NPC height)
                r.update(judge(index, pts, None, a[3], b[3], r.get("skip")))
                if hs is not None and r.get("grid"):
                    # (and with the route's own heights, where it has them: the grid's surfaces. Without them the floor
                    # followed over the mesh can take a tunnel's under a road and see the road as a climb where the
                    # route's own heights never left it; Dun Algaz's road over its tunnel, 2026-11-22)
                    h = judge(index, pts, hs, a[3], b[3], r.get("skip"))
                    r["h"] = {k: h[k] for k in ("climbs", "walls", "off_yd", "end_floor_off")}
                r["clean"] = bool(r["found"] and r["walls"] == 0 and r["climbs"] == 0
                                  and (r["end_floor_off"] is None or r["end_floor_off"] <= END_FLOOR_Z))
                r["line"] = [round(v, 1) for v in pts]
            res[name] = r
        except Exception as e:  # (one trip's error is reported, the rest go on)
            res[name] = {"found": False, "error": repr(e)[:300]}
    return res


def run(n: int = 10000, workers: int = 7, seed: int = 10000, log=print) -> dict:
    import multiprocessing as mp

    OUT.mkdir(parents=True, exist_ok=True)
    src = os.environ.get("AGPS_WT_TRIPS")  # (another run's trips.json: the same trips again, its first n)
    trips = json.loads(Path(src).read_text(encoding="utf-8"))[:n] if src else make_trips(n, seed)
    (OUT / "trips.json").write_text(json.dumps(trips), encoding="utf-8")
    log(f"{len(trips)} trips: " + ", ".join(f"{k} {sum(t['kind'] == k for t in trips)}" for k, _ in MIX))
    t0 = time.time()
    out = []
    with mp.get_context("spawn").Pool(workers, maxtasksperchild=400) as pool, (OUT / "results.jsonl").open("w", encoding="utf-8") as f:
        for k, r in enumerate(pool.imap_unordered(run_trip, trips, chunksize=4), 1):
            out.append(r)
            f.write(json.dumps(r) + "\n")
            if k % 250 == 0:
                f.flush()
                log(f"  {k}/{len(trips)} ({time.time() - t0:.0f} s)")
    log(f"routed {len(out)} trips in {time.time() - t0:.0f} s")
    rep = report(out)
    (OUT / "report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    return rep


# --- the report ---------------------------------------------------------------------------------------------------------

def _stats(rows: list, eng: str) -> dict:
    rs = [r[eng] for r in rows if eng in r]
    found = [r for r in rs if r.get("found") and "yd" in r and "off_yd" in r]
    n = max(1, len(rs))
    yd = [r["yd"] for r in found]
    return {"trips": len(rs), "found_pct": round(100 * len(found) / n, 1),
            "clean_pct": round(100 * sum(r.get("clean", False) for r in rs) / n, 1),
            "yd_median": round(float(np.median(yd)), 0) if yd else None,
            "ms_median": round(float(np.median([r["ms"] for r in rs if "ms" in r])), 1) if rs else None,
            "ms_p95": round(float(np.percentile([r["ms"] for r in rs if "ms" in r], 95)), 1) if rs else None,
            "walls_per_100": round(100 * sum(r["walls"] for r in found) / max(1, len(found)), 1),
            "off_yd_per_100": round(100 * sum(r["off_yd"] for r in found) / max(1, len(found)), 1),
            "climbs_per_100": round(100 * sum(r["climbs"] for r in found) / max(1, len(found)), 1),
            "climbs_per_100_own_heights": round(100 * sum((r.get("h") or r)["climbs"] for r in found) / max(1, len(found)), 1),
            "wrong_floor_end_pct": round(100 * sum((r["end_floor_off"] or 0) > END_FLOOR_Z for r in found) / max(1, len(found)), 1),
            "on_grid_pct": round(100 * sum(r.get("grid", False) for r in rs) / n, 1),
            "errors": sum("error" in r for r in rs)}


def report(rows: list) -> dict:
    kinds = sorted({r["kind"] for r in rows})
    rep = {"all": {e: _stats(rows, e) for e in ("main", "grid")}}
    for k in kinds:
        sub = [r for r in rows if r["kind"] == k]
        rep[k] = {e: _stats(sub, e) for e in ("main", "grid")}
    both = [r for r in rows if r.get("main", {}).get("found") and r.get("grid", {}).get("found")
            and "off_yd" in r["main"] and "off_yd" in r["grid"]]

    def bad(r):
        return r["walls"] * 100 + r["climbs"] * 100 + r["off_yd"]
    wins = {"grid_shorter": sum(r["grid"]["yd"] < r["main"]["yd"] - 5 for r in both),
            "main_shorter": sum(r["main"]["yd"] < r["grid"]["yd"] - 5 for r in both),
            "grid_cleaner": sum(r["grid"].get("clean") and not r["main"].get("clean") for r in both),
            "main_cleaner": sum(r["main"].get("clean") and not r["grid"].get("clean") for r in both),
            "both": len(both)}
    rep["wins"] = wins
    for e in ("main", "grid"):
        rows_e = [r for r in rows if r.get(e, {}).get("found") and "off_yd" in r[e]]
        worst = sorted(rows_e, key=lambda r: -bad(r[e]))[:10]
        rep[f"worst_{e}"] = [{"id": r["id"], "kind": r["kind"], "cont": r["cont"], "from": r["from"][:4],
                              "to": r["to"][:4], **{k: r[e][k] for k in ("yd", "off_yd", "walls", "worst_off", "climbs",
                                                                       "end_floor_off")}} for r in worst]
    return rep
