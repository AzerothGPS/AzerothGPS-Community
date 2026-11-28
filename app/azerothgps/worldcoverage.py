"""The grids' coverage sweep (`agps world-grid coverage`, bake8; Kooki3z 2026-11-23: "imo fall back can't be trusted and
should identify where that would be needed and just correct it"): every place a route stops at, walked on the grids
alone (no Router's own walk, no fallback) from a few starts round it, and each one the grid can't reach listed with its
cause, for the bake to fix.

Stops (`stops`): every shipped NPC's spawn (Data/Npcs.lua, on the continents), the towns' places (ns.TownPlaces, with
their heights), every dungeon's and raid's door (ns.Transports' portals' outside ends) and the flight masters
(Data/Pois.lua's kind 1, no height), one per STOP_SAME_YD. Outside the capitals the world grid walks (WorldGrid.lua's
WG.Walk); inside one its city grid (CityGrid.lua's CG.Walk: `grid` "city").

Starts (`starts_for`): up to START_N spots START_YD round the stop (directions apart) on the ground players reach (a cell
whose one floor has F_REACH; in a capital: other stops of its grid at its floors), the stop's height given.

Each stop's result (`check`):
  ok        a start walked to it on the grid, ending on its floor (within END_Z), no piece across a shipped wall
  noway     no start got a walk (`some`, a note: some did, some didn't: a start's island)
  wall      a walk's piece crosses a shipped wall (Passability.CrossesWall): reached, but counted apart (`crossing`)
  foot      the walk ends under the stop (WG.UnderGoals: the foot of its building, its own floor no way up)
  nostart   no reached ground round it to start from (an island, a ship)
Notes: `nofloor` (the grid has no floor within FLOOR_Z of the stop's height in its cell) and `unreached` (the floor is
there, not flagged reached on foot): the data's side (`floor_gaps`), a failure only with one of the above.
Causes (`diagnose`, with the meshes: AGPS_WORLDMESH_DIR): `mesh hole` (no walkable poly at the stop), `cell too coarse`
(a poly there, no grid floor: the cell's floors merged or pruned), `mesh apart` (the mesh has no way from its floor to
the reached ground: needs a recorded walk), `missing link` (the mesh walks it; the grid's 8.33 yd cells miss the
walkway, stair or door), `search` (its floor reached, no walk from the starts: their side, or the costs).

Writes <out>/report.json and report.md. `EXCEPTIONS` (reviewed: genuinely unreachable on foot) are listed apart.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

STOP_SAME_YD = 3.0  # stops this near (and FLOOR_Z in height) are one
START_YD = (90.0, 130.0, 60.0, 180.0, 250.0)  # yards round a stop a start is looked for at, in turn
START_DIRS = 8
START_N = 3
FLOOR_Z = 4.0  # yards: the grid's floor this near the stop's height is its floor (worldbake.STOP_ON_Z)
END_Z = 6.0  # yards: a walk ending this near the stop's height is on its floor (undergroundsweep.FLOOR_YD)
CONTS = (0, 1, 2991)
CITY_START_MIN, CITY_START_MAX = 40.0, 250.0

# Stops reviewed as out of reach on foot on our own mesh (Kooki3z's rule: "No way there found" is right there till a
# recorded walk or a mesh look covers them): (name, x, y) rounded to the yard, with why. Kept short; a new one needs a
# reason (bake8's sweep, 2026-11-23).
EXCEPTIONS: dict = {
    ('Wallace the Blind', -755, 1497): "overhead: no walkable floor in our mesh at the spot",
    ('Archmage Ansirem Runeweaver', 35, 256): "overhead: no walkable floor in our mesh at the spot",
    ('Meridith the Mermaiden', -10293, -4319): "overhead: no walkable floor in our mesh at the spot",
    ('Torta', -7056, -4813): "overhead: no walkable floor in our mesh at the spot",
    ("Pao'ka Swiftmountain", -5157, -1220): "noway: our mesh has no way from its floor to the ground players walk",
    ('Kalin Windflight', -3286, 2004): "noway: our mesh has no way from its floor to the ground players walk",
    ('Duke Hydraxis', 2850, -7297): "nostart: no ground walked to round it (out at sea)",
    ('Nyrill', 3777, -4619): "noway: our mesh has no way from its floor to the ground players walk",
    ('Coral Moongale', 3943, -4781): "noway: our mesh has no way from its floor to the ground players walk",
    ('Archmage Xylem', 3982, -4760): "noway: our mesh has no way from its floor to the ground players walk",
    ('Great Cat Spirit', 7360, -2729): "overhead: no walkable floor in our mesh at the spot",
    ('Rivern Frostwind', 8068, -3862): "foot: no walkable floor in our mesh at the spot",
    ('Mist', 10758, 2209): "noway: no walkable floor in our mesh at the spot",
    ('Spirit Healer', 16320, 16244): "nostart: our mesh has no way from its floor to the ground players walk",
    ("Urs'endris", 2679, 349): "noway: our mesh has no way from its floor to the ground players walk",
}
# The bake's own gaps the sweep still lists (bake8: 59, bake9: 58), with their cause: the next bakes' work. The tests let none
# be added and want each taken off once reached.
KNOWN_GAPS: dict = {
    ("Auctioneer O'reely", -14417, 524): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Short John Mithril', -13184, 333): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Spirit Healer', -10575, -3377): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Haromm', -10507, -3328): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Rartar', -10490, -3264): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Sunken Temple', -10177, -3995): "noway: its floor is reached; no walk from the starts round it",
    ('Maginor Dumas', -9012, 867): "noway: the city grid's",
    ('Elsharin', -9006, 885): "noway: the city grid's",
    ('Larimaine Purdue', -8992, 848): "noway: the city grid's",
    ('Jennea Cannon', -8990, 862): "noway: the city grid's",
    ('Thulman Flintcrag', -8419, 647): "noway: the city grid's",
    ('Lothos Riftwaker', -7509, -1040): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Slave Worker', -6887, -1257): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Slave Worker', -6881, -1239): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Uldaman: Front Entrance', -6066, -2955): "noway: its floor is reached; no walk from the starts round it",
    ('Hammertoe Grez', -6065, -3022): "noway: its floor is reached; no walk from the starts round it",
    ('Gnomeregan: Front Entrance', -5163, 928): "noway: its floor is reached; no walk from the starts round it",
    ('Namdo Bizzfizzle', -4923, 726): "noway: its floor is reached; no walk from the starts round it",
    ('The Hall of Thanes', -4822, -932): "noway: its floor is reached; no walk from the starts round it",
    ('Mountaineer Angst', -4753, -3333): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ("Maiden's Virtue Crewman", -3892, -661): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Timothy Clark', -3714, -812): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Foggy MacKreel', -2357, -2423): "foot: the grid's cell has another floor than the spot's",
    ("Atal'ai Exile", -464, -2874): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Scarlet Monastery: Armory', 2886, -836): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Scarlet Monastery: Cathedral', 2915, -824): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Rifleman Torrig', -6764, 772): "foot: the grid's cell has another floor than the spot's",
    ('Cloud Skydancer', -6759, 776): "foot: the grid's cell has another floor than the spot's",
    ('Vish Kozus', -6740, 770): "noway: the grid's cell has another floor than the spot's",
    ("Ralo'shan the Eternal Watcher", -6547, 92): "noway: the grid's cell has another floor than the spot's",
    ('Kindal Moonweaver', -4482, 858): "foot: the grid's cell has another floor than the spot's",
    ("Jer'kai Moonweaver", -4480, 858): "foot: the grid's cell has another floor than the spot's",
    ('Bethan Bluewater', -4406, 3187): "noway: its floor is reached; no walk from the starts round it",
    ('Quintis Jonespyre', -4396, 3187): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Griniblix the Spectator', -3763, 1136): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Commander Samaul', -3738, -4546): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Captain Garran Vimes', -3735, -4556): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Captain Evencane', -3728, -4538): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Clerk Lendry', -3722, -4539): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Theramore Lieutenant', -3720, -4552): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Adjutant Tesoran', -3717, -4547): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Minor Manifestation of Earth', -878, -4290): "noway: the grid's cell has another floor than the spot's",
    ('Telf Joolam', -270, -4001): "noway: the grid's cell has another floor than the spot's",
    ('Hgarth', 1055, 844): "noway: the grid's cell has another floor than the spot's",
    ("X'yera", 1453, -4186): "foot: the city grid's",
    ('Zayus', 1461, -4182): "foot: the city grid's",
    ('Framnali', 2251, -2503): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Ashenvale Sentinel', 2401, -1721): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Ashenvale Sentinel', 2408, -1726): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Rayan Dawnrisen', 3983, -4799): "noway: the grid's cell has another floor than the spot's",
    ('Haleh', 6110, -4189): "noway: its floor is reached; no walk from the starts round it",
    # (the sample's since 1.4.2's camp NPCs left the shipped stops; her spot unchanged: from the west the grid stays on
    # the floor below hers, 711.5 under 743.5, to her x, y)
    ('Syurana', 7122, -3978): "foot: the grid's cell has another floor than the spot's",
    ('Frahun Shadewhisper', 10519, 778): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Alyissia', 10527, 778): "foot: the mesh walks to it; the grid's 8.33 yd cells miss the stairs or door",
    ('Halaan Hawk-Eye', 4065, 1795): "foot: the grid's cell has another floor than the spot's",
    ('Myriaal Mistwake', 4065, 1804): "foot: the grid's cell has another floor than the spot's",
}


def _f(v):
    return None if v is None else float(v)


def stops(ns, conts=CONTS) -> list[dict]:
    """[{kind, name, cont, x, y, z}]: the shipped stops on `conts`, one per STOP_SAME_YD (and FLOOR_Z in height)."""
    from .undergroundsweep import shipped_npcs
    out, seen = [], {}

    def add(kind, name, cont, x, y, z):
        if cont not in conts:
            return
        key = (cont, round(x / STOP_SAME_YD), round(y / STOP_SAME_YD))
        for zz in seen.get(key, ()):
            if z is None or zz is None or abs(zz - z) <= FLOOR_Z:
                return
        seen.setdefault(key, []).append(z)
        out.append({"kind": kind, "name": name, "cont": cont, "x": round(x, 1), "y": round(y, 1),
                    "z": None if z is None else round(z, 1)})
    for npc in shipped_npcs():
        for lvl, x, y, z in npc["spawns"]:
            add("npc", npc["name"], lvl, x, y, z)
    tp = ns.TownPlaces or {}
    for _k, town in tp.items():
        for i in range(1, len(town) + 1):
            p = town[i]
            if p.x is not None and p.z is not None:
                add("town", str(p[1]), int(town.cont or 0), float(p.x), float(p.y), float(p.z))
    rows = ns.Transports
    for i in range(1, len(rows) + 1):
        t = rows[i]
        if t[8] == "portal" and t.z1 is not None:
            add("door", str(t[10]), int(t[1]), float(t[2]), float(t[3]), float(t.z1))
    for cont in conts:
        for p in (ns.Pois[cont] or {}).values():
            if p[1] == 1 and not str(p[4]).startswith("zz"):
                add("flight", str(p[4]), cont, float(p[2]), float(p[3]), None)
    return out


def _surfaces(ns, c, x, y):
    s = ns.WorldGrid.SurfacesAt(c, x, y)
    return [s[i] for i in range(1, len(s) + 1)] if s else []


def _reach(s) -> bool:
    return int(s.f) // 4 % 2 == 1


def _swim(s) -> bool:
    return int(s.f) % 2 == 1


def starts_for(ns, c, d) -> list[dict]:
    """Up to START_N starts round stop d on the world grid, directions apart: a cell with one floor, reached on foot, not
    water, on the stop's side of the shipped walls; on road ground first (where players come from: a mountain side's
    reached ground can be a piece of its own, Aerie Peak's slopes over its gryphon master), then any."""
    WG = ns.WorldGrid
    R = ns.Router
    out = []
    used = []
    for road in (True, False):
        for r in START_YD:
            for k in range(START_DIRS):
                a = 2 * math.pi * k / START_DIRS
                if any(abs((a - u + math.pi) % (2 * math.pi) - math.pi) < 2 * math.pi / START_DIRS * 1.5 for u in used):
                    continue
                x, y = d["x"] + r * math.cos(a), d["y"] + r * math.sin(a)
                if R.CapitalAt(d["cont"], x, y) or WG.NotMeshed(d["cont"], x, y):
                    continue
                ss = _surfaces(ns, c, x, y)
                land = [s for s in ss if not _swim(s)]
                if len(land) != 1 or not _reach(land[0]) or abs(float(land[0].x) - x) > c.cell                         or abs(float(land[0].y) - y) > c.cell:
                    continue
                if road and int(land[0].f) // 2 % 2 != 1:
                    continue
                # (not a spot a shipped wall parts from its cell's floor: the walk's first step would cross it, a
                # town's palisade beside the start, Hammerfall's and Brill's)
                if ns.Passability.CrossesWall(d["cont"], x, y, float(land[0].x), float(land[0].y)):
                    continue
                out.append({"x": round(x, 1), "y": round(y, 1), "z": round(float(land[0].z), 1), "road": road})
                used.append(a)
                if len(out) >= START_N:
                    return out
    return out


def _list(t):
    return [t[i] for i in range(1, len(t) + 1)] if t is not None else []


def _walk_issues(ns, cont, r, d) -> list[dict]:
    P = ns.Passability
    p = _list(r.pts)
    fz = _list(r.fz) if r.fz else []
    out = []
    for i in range(0, len(p) - 3, 2):
        x0, y0, x1, y1 = p[i], p[i + 1], p[i + 2], p[i + 3]
        if P.CrossesWall(cont, x0, y0, x1, y1):
            out.append({"kind": "wall", "at": [round(x0, 1), round(y0, 1)], "to": [round(x1, 1), round(y1, 1)]})
            break
    if d["z"] is not None and fz and fz[-1] is not None:
        if fz[-1] < d["z"] - END_Z:
            out.append({"kind": "foot", "ends": round(fz[-1], 1)})
        elif fz[-1] > d["z"] + END_Z:
            out.append({"kind": "overhead", "ends": round(fz[-1], 1)})
    return out


def check_world(lua, ns, d) -> dict:
    WG = ns.WorldGrid
    c = WG.Cont(d["cont"])
    row = dict(d, grid="world")
    if not c:
        row["issues"] = [{"kind": "nogrid"}]
        return row
    ss = _surfaces(ns, c, d["x"], d["y"])
    if d["z"] is not None:
        fl = [s for s in ss if abs(float(s.z) - d["z"]) <= FLOOR_Z and not _swim(s)]
        if not fl:
            row["issues"] = [{"kind": "nofloor", "floors": [round(float(s.z), 1) for s in ss][:6]}]
            row["floor"] = None
        else:
            row["floor"] = round(float(fl[0].z), 1)
            row["reached"] = any(_reach(s) for s in fl)
    issues = list(row.get("issues", []))
    if d["z"] is not None and row.get("floor") is not None and not row.get("reached"):
        issues.append({"kind": "unreached"})
    starts = starts_for(ns, c, d)
    row["starts"] = len(starts)
    if not starts:
        issues.append({"kind": "nostart"})
        row["issues"] = issues
        return row
    got, walks = 0, []
    for s in starts:
        WG.routes, WG.order = lua.table(), lua.table()
        WG.targets = lua.table()
        t0 = time.perf_counter()
        try:
            r = WG.Walk(c, s["x"], s["y"], s["z"], d["x"], d["y"], d["z"], lua.table())
        except Exception as e:  # (a failure in the addon's Lua: a finding too)
            issues.append({"kind": "error", "error": str(e)[:300]})
            continue
        ms = round((time.perf_counter() - t0) * 1000)
        if not r:
            walks.append({"from": [s["x"], s["y"]], "ms": ms, "found": False})
            continue
        got += 1
        wi = _walk_issues(ns, d["cont"], r, d)
        walks.append({"from": [s["x"], s["y"]], "ms": ms, "found": True, "yd": round(float(r.length or 0))})
        for i in wi:
            if not any(j["kind"] == i["kind"] for j in issues):
                issues.append(i)
    if got == 0:
        issues.append({"kind": "noway"})
    elif got < len(starts):
        issues.append({"kind": "some", "found": got, "of": len(starts)})
    row["walks"] = walks
    row["issues"] = issues
    return row


def check_city(lua, ns, d, name, city_stops) -> dict:
    CG = ns.CityGrid
    row = dict(d, grid="city", city=name)
    cc = CG.City(name)
    if not cc:
        row["issues"] = [{"kind": "nogrid"}]
        return row
    starts = []
    for e in sorted(city_stops, key=lambda e: abs(math.dist((e["x"], e["y"]), (d["x"], d["y"])) - 120)):
        dd = math.dist((e["x"], e["y"]), (d["x"], d["y"]))
        if CITY_START_MIN <= dd <= CITY_START_MAX and e["z"] is not None and all(
                math.dist((e["x"], e["y"]), (s["x"], s["y"])) > 40 for s in starts):
            starts.append(e)
        if len(starts) >= START_N:
            break
    row["starts"] = len(starts)
    issues, got, walks = [], 0, []
    if not starts:
        row["issues"] = [{"kind": "nostart"}]
        return row
    for s in starts:
        CG.routes, CG.order = lua.table(), lua.table()
        t0 = time.perf_counter()
        try:
            r = CG.Walk(cc, s["x"], s["y"], s["z"], d["x"], d["y"], d["z"])
        except Exception as e:
            issues.append({"kind": "error", "error": str(e)[:300]})
            continue
        ms = round((time.perf_counter() - t0) * 1000)
        if not r or r == "pending":
            walks.append({"from": [s["x"], s["y"]], "ms": ms, "found": False})
            continue
        got += 1
        walks.append({"from": [s["x"], s["y"]], "ms": ms, "found": True, "yd": round(float(r.length or 0))})
        for i in _walk_issues(ns, d["cont"], r, d):
            if not any(j["kind"] == i["kind"] for j in issues):
                issues.append(i)
    if got == 0:
        issues.append({"kind": "noway"})
    elif got < len(starts):
        issues.append({"kind": "some", "found": got, "of": len(starts)})
    row["walks"] = walks
    row["issues"] = issues
    return row


def _game():
    from .gameharness import start
    lua, ns = start()
    ns.Router.SYNC_WALKS = True
    ns.settings.gps.worldGrid = True
    ns.settings.gps.cityGrid = True
    return lua, ns


def _run_shard(args):
    i, n, only, conts = args
    lua, ns = _game()
    CG = ns.CityGrid
    all_ = stops(ns, conts)
    city_of = {}
    for k, d in enumerate(all_):
        # (as WorldGrid.lua's WG.Leg and WG.CityWalk: a stop over a city grid's cells (CityGrid.GridCityAt: a capital's,
        # Thunder Bluff's mesas, Ironforge's halls under the mountain the capital's outline leaves out) is its walk;
        # the Ruins of Lordaeron's the Router's)
        nm = CG.CityFor(d["cont"], d["x"], d["y"]) or CG.GridCityAt(d["cont"], d["x"], d["y"])
        if nm:
            city_of[k] = nm
        elif ns.WorldGrid.NotMeshed(d["cont"], d["x"], d["y"]):
            city_of[k] = "-"
    by_city = {}
    for k, nm in city_of.items():
        by_city.setdefault(nm, []).append(all_[k])
    out = []
    for k, d in enumerate(all_):
        if k % n != i or (only and only.lower() not in d["name"].lower()):
            continue
        nm = city_of.get(k)
        if nm == "-":
            out.append(dict(d, grid="none", issues=[{"kind": "notmeshed"}]))
        elif nm:
            out.append(check_city(lua, ns, d, nm, by_city[nm]))
        else:
            out.append(check_world(lua, ns, d))
    return out


# (a stop counts as reached when a start's walk gets to it, on its floor; `nofloor`, `unreached` and `some` are
# notes: the floor the cell's middle has can be another one than the stop's spot's, its neighbors' taken (WG.Ends))
FAIL_KINDS = ("noway", "foot", "overhead", "nostart", "error")
# (a walk that gets there but crosses a shipped wall on the way: listed and counted apart, `crossing`)
CROSS_KINDS = ("wall",)


def failed(row) -> bool:
    return any(i["kind"] in FAIL_KINDS for i in row.get("issues", []))


def exception_key(row) -> tuple:
    return (row["name"], round(row["x"]), round(row["y"]))


def summarize(rows: list[dict], secs: float = 0.0) -> dict:
    counts = {}
    for r in rows:
        for k in {i["kind"] for i in r.get("issues", [])}:
            counts[k] = counts.get(k, 0) + 1
    by_grid = {}
    for r in rows:
        g = by_grid.setdefault(r.get("grid", "?"), {"stops": 0, "failed": 0})
        g["stops"] += 1
        g["failed"] += failed(r)
    bad = [r for r in rows if failed(r)]
    crossing = [r for r in rows if not failed(r) and any(i["kind"] in CROSS_KINDS for i in r.get("issues", []))]
    exc = [r for r in bad if exception_key(r) in EXCEPTIONS]
    ms = sorted(w["ms"] for r in rows for w in r.get("walks", []) if w.get("found"))
    return {"stops": len(rows), "failed": len(bad), "crossing": len(crossing), "exceptions": len(exc), "counts": counts,
            "by_grid": by_grid,
            "by_kind": {k: sum(1 for r in bad if r["kind"] == k) for k in ("npc", "town", "door", "flight")},
            "ms_median": ms[len(ms) // 2] if ms else None, "ms_p95": ms[int(len(ms) * 0.95)] if ms else None,
            "secs": round(secs), "rows": rows}


def diagnose(result: dict, log=print) -> None:
    """Each failed world-grid stop's cause, from our own meshes (worldbake's _mesh_way over the map tiles): `cause`."""
    from . import navmesh as NM
    from . import worldbake as WB
    lua, ns = _game()
    WG = ns.WorldGrid
    meshes = {}
    for r in result["rows"]:
        if r.get("grid") != "world" or not (failed(r) or any(i["kind"] in CROSS_KINDS for i in r.get("issues", []))):
            continue
        kinds = {i["kind"] for i in r["issues"]}
        cont = r["cont"]
        c = WG.Cont(cont)
        M = meshes.setdefault(cont, WB._Meshes(cont))
        x, y, z = r["x"], r["y"], r["z"]
        if "nostart" in kinds and len(kinds) == 1:
            r["cause"] = "no reached ground round it"
            continue
        if z is None:
            r["cause"] = "search" if "noway" in kinds or "some" in kinds else "line"
            continue
        polys = M.polys_at(x, y, z, FLOOR_Z, WB.STOP_MESH_YD)
        if "nofloor" in kinds:
            r["cause"] = "cell too coarse" if polys else "mesh hole"
            continue
        if "unreached" in kinds or "foot" in kinds:
            if not polys:
                r["cause"] = "mesh hole"
                continue

            def done(_n, m):
                for s in _surfaces(ns, c, m[0], m[1]):
                    if _reach(s) and abs(float(s.z) - m[2]) <= WB.STOP_REACH_Z:
                        return True
                return False
            way = WB._mesh_way(M, x, y, z, done, WB.STOP_PATH_YD)
            r["cause"] = "missing link" if way else "mesh apart"
            if way:
                r["mesh_way"] = [[round(v, 1) for v in p] for p in way[:: max(1, len(way) // 12)]]
            continue
        if "wall" in kinds:
            r["cause"] = "across a wall"
            continue
        r["cause"] = "search"
    _ = NM
    log(f"  causes: {_count([r.get('cause') for r in result['rows'] if r.get('cause')])}")


def _count(xs):
    out = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return out


def sweep(jobs: int = 1, only: str | None = None, conts=CONTS, log=print) -> dict:
    t0 = time.time()
    if jobs > 1:
        import multiprocessing as mp
        with mp.get_context("spawn").Pool(jobs) as pool:
            rows = [r for part in pool.map(_run_shard, [(i, jobs, only, tuple(conts)) for i in range(jobs)]) for r in part]
    else:
        rows = _run_shard((0, 1, only, tuple(conts)))
    rows.sort(key=lambda r: (r["cont"], r["x"], r["y"]))
    return summarize(rows, time.time() - t0)


def write_report(result: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    lines = ["# The grids' coverage", "",
             f"{result['stops']} stops, {result['failed']} the grids can't reach ({result['exceptions']} reviewed "
             f"exceptions), {result.get('crossing')} more reached across a shipped wall, {result['secs']} s. "
             f"Walks: median {result['ms_median']} ms, 95th percentile {result['ms_p95']} ms.",
             "", f"By grid: {result['by_grid']}", f"Failed by kind: {result['by_kind']}", "",
             "| issue | stops |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in sorted(result["counts"].items())]
    causes = _count([r.get("cause") for r in result["rows"] if failed(r)])
    lines += ["", f"Causes: {causes}", "", "## Failed stops", ""]
    for r in result["rows"]:
        if failed(r) or any(i["kind"] in CROSS_KINDS for i in r.get("issues", [])):
            what = "; ".join(i["kind"] for i in r["issues"])
            lines.append(f"- {r['name']} ({r['kind']}, {r['cont']}: {r['x']}, {r['y']}, {r['z']}) {r.get('grid')}: "
                         f"{what}{' — ' + r['cause'] if r.get('cause') else ''}"
                         f"{' [exception: ' + EXCEPTIONS[exception_key(r)] + ']' if exception_key(r) in EXCEPTIONS else ''}")
    p = out_dir / "report.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def floor_gaps(lua, ns, kinds=("npc", "town", "door")) -> list[dict]:
    """The world grid's stops (with heights, outside the city grids) whose floor it hasn't, or hasn't reached on foot:
    the data's side of the sweep, quick enough for the tests (by map tile, each decoded once)."""
    WG, CG = ns.WorldGrid, ns.CityGrid
    todo = []
    for d in stops(ns):
        if d["kind"] not in kinds or d["z"] is None or CG.CityFor(d["cont"], d["x"], d["y"]) \
                or CG.GridCityAt(d["cont"], d["x"], d["y"]) or WG.NotMeshed(d["cont"], d["x"], d["y"]):
            continue
        todo.append(d)
    todo.sort(key=lambda d: (d["cont"], math.floor(d["x"] / 533.33), math.floor(d["y"] / 533.33)))
    out = []
    for d in todo:
        c = WG.Cont(d["cont"])
        if not c:
            continue
        fl = [s for s in _surfaces(ns, c, d["x"], d["y"]) if abs(float(s.z) - d["z"]) <= FLOOR_Z and not _swim(s)]
        if not fl:
            out.append(dict(d, gap="nofloor"))
        elif not any(_reach(s) for s in fl):
            out.append(dict(d, gap="unreached"))
    return out
