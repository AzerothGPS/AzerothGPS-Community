"""Route quality check (`agps route-check`): runs the addon's own routing (its Lua, under
lupa) on random trips in every zone and flags bad off-road routes.

For each trip the off-road route is compared with the shortest walk the terrain grid
allows (Passability's grid search with generous limits: the best the data knows):

  * detour:  the route is much longer than that walk (routing picked a poor way round)
  * blocked: an off-road stretch of the route crosses terrain the grid calls impassable
             (away from the ends, where the player or the stop may stand on rocks)

Trips from or to a spot over a cave (Data/Caves.lua) are left out: such a spot is down in the
cave, which the flat reference walk can't judge (the caves have their own checks: `agps caves`
and the tests); so are trips from or to a capital's own cells (Data/Capitals.lua: levels over
each other, lifts up its mesas; `agps capitals --check` walks those routes in 3D).

Writes data/debug/route-check/report.json (every flagged trip, worst first) and prints a
table per zone. Flagged trips can be turned into regression tests in app/tests.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from .paths import ADDON_DIR

DETOUR_SHARE, DETOUR_YD = 1.4, 150  # flagged when longer than max(share x, + yd) the grid walk
ROAD_DETOUR_SHARE, ROAD_DETOUR_YD = 2.5, 300  # the same for road routes (they keep to the roads)
BLOCKED_RUN_YD = 25  # flagged when an off-road stretch crosses this much impassable ground
END_ALLOW_YD = 60  # blocked ground this close to either end doesn't count
GUARDS_YD = 50  # with a faction: a reference walk this far past the other faction's guards explains a longer route


def _runtime(faction: str | None = None):
    """The addon's routing in a Lua runtime of its own. `faction` ("A" or "H"): the other faction's guards weighed as
    in the game (Data/Hostile.lua, Router.HostileSide by Nav.Faction); none, they aren't."""
    import lupa

    lua = lupa.LuaRuntime()
    lua.execute('issecretvalue = nil\nCreateFrame = function() error("no frames here") end\n'
                "GetTime = function() return 0 end")
    ns = lua.table()
    ns.IsSecret = lua.eval("function(v) return false end")
    ns.db = lua.eval("{}")
    loader = lua.eval("function(src, name) return assert(load(src, '@' .. name)) end")
    for name in ("Geo.lua", "GPSFrame.lua", "Data/Maps.lua", "Data/Roads.lua", "Data/Terrain.lua", "Data/Buildings.lua", "Data/TerrainHPA.lua", "Data/Caves.lua",
                 "Data/Capitals.lua", "Passability.lua", "Router.lua"):
        loader((ADDON_DIR / name).read_text(encoding="utf-8"), name)("AzerothGPS", ns)
    if faction:
        loader((ADDON_DIR / "Data/Hostile.lua").read_text(encoding="utf-8"), "Data/Hostile.lua")("AzerothGPS", ns)
        ns.Nav = lua.eval("function(side) return { Faction = function() return side end } end")(faction)
    ns.Router.SYNC_WALKS = True
    return lua, ns


def _pts(r) -> tuple[list[tuple[float, float]], list[int]]:
    flat = [r.pts[i] for i in range(1, len(r.pts) + 1)]
    kinds = [r.kinds[i] for i in range(1, len(r.kinds) + 1)]
    return [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)], kinds


TILE = 1600 / 3
GRID_WRONG_YD = 40.0  # blocked cells this close to a road that runs over blocked cells: the grid's error


def _in_cave(P, cont, x, y) -> bool:
    """Whether (x, y) is over one of the caves' own cells (Data/Caves.lua), or a capital's
    (Data/Capitals.lua: its levels, lifts and mesas are more than the flat walk can judge;
    `agps capitals --check` walks its routes in 3D instead)."""
    r = P.OverlayRaw(cont, x, y) if P.OverlayRaw else None
    v, grid = r if isinstance(r, tuple) else (r, None)
    return v is not None and grid is not None and bool(grid.cave or grid.capital)


def _walked_at(P, cont, x, y, terrain, rows) -> int:
    """The grid's value at (x, y) as the walks judge it: over a cave's own grid, closed only where both it and the
    continent's cell under it are (FindPath walks the continent's cells, ignoring the caves' grids; a straight leg
    goes by the cave's: its mouth open to the sky over the land's closed cells, Blasted Lands. 1.3.14's grid opened a
    valley in the Wetlands over a cave's tunnels, whose rock the cave's grid closes there). `terrain`: ns.Terrain[cont];
    `rows`: Passability.BaseRow's rows, remembered by the caller."""
    r = P.OverlayRaw(cont, x, y) if P.OverlayRaw else None
    v, grid = r if isinstance(r, tuple) else (r, None)
    at = P.At(cont, x, y)
    if at != 2 or terrain is None or v is None or grid is None or not grid.cave or grid.capital:
        return at
    k = TILE / terrain.cell  # (as Passability's ToCell)
    col = math.floor(((32 - y / TILE) - terrain.tx0) * k) + 1
    row = math.floor(((32 - x / TILE) - terrain.ty0) * k) + 1
    if row < 1 or row > terrain.h or col < 1 or col > terrain.w:
        return 2
    if row not in rows:
        rows[row] = P.BaseRow(cont, row)
    return int(rows[row][col - 1])


def _blocked_run(P, cont, pts, kinds, start, stop, terrain=None) -> float:
    """Longest run (yards) of impassable ground crossed by the route's off-road stretches,
    ignoring END_ALLOW_YD around the start and the stop, and ground beside a road that
    itself runs over "impassable" cells (a road there, e.g. drawn in game, says the grid is
    wrong there: getting on or off it isn't a routing error)."""
    wrong, rows = [], {}
    for i, k in enumerate(kinds):
        if k == 0:
            for (x, y) in (pts[i], pts[i + 1]):
                if P.At(cont, x, y) == 2:
                    wrong.append((x, y))
    worst, run = 0.0, 0.0
    for i, k in enumerate(kinds):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        seg = math.hypot(x2 - x1, y2 - y1)
        n = max(1, int(seg / 3))
        for j in range(n + 1):
            x, y = x1 + (x2 - x1) * j / n, y1 + (y2 - y1) * j / n
            near_end = math.hypot(x - start[0], y - start[1]) < END_ALLOW_YD or                 math.hypot(x - stop[0], y - stop[1]) < END_ALLOW_YD
            beside = any(math.hypot(x - wx, y - wy) < GRID_WRONG_YD for wx, wy in wrong)
            if k == 1 and not near_end and not beside and _walked_at(P, cont, x, y, terrain, rows) == 2:
                run += seg / n
                worst = max(worst, run)
            else:
                run = 0.0
    return worst


def guard_yards(R, cont, ref, faction) -> float:
    """Yards of the grid's reference walk (FindPath's (yards, path)) within reach of the guards hostile to `faction`."""
    if not faction or not isinstance(ref, tuple) or not ref[1]:
        return 0.0
    path = [ref[1][i] for i in range(1, len(ref[1]) + 1)]
    return sum(R.HostileYards(cont, path[i], path[i + 1], path[i + 2], path[i + 3], faction)
               for i in range(0, len(path) - 3, 2))


def check(samples: int = 20, seed: int = 1, only: str | None = None, log=print, modes=("offroad",),
          faction: str | None = None) -> dict:
    """Random trips per zone, routed in each of `modes` ("offroad", "road"); with `faction`, as that faction's
    character (the other faction's guards weighed)."""
    from .extract.pipeline import CONTINENTS

    lua, ns = _runtime(faction)
    P, R = ns.Passability, ns.Router
    limits = (P.PATH_MAX_EXPANSIONS, P.PATH_MAX_CELLS)  # the addon's own, for its routes
    rnd = random.Random(seed)
    zones = []
    for mid in ns.Maps.keys():
        m = ns.Maps[mid]
        if m.type == 3 and m.bounds and m.continent in CONTINENTS and ns.Terrain[m.continent]:
            if only and only.lower() not in m.name.lower():
                continue
            zones.append((m.name, mid, m.continent, [m.bounds[i] for i in range(1, 5)]))
    zones.sort()
    flagged, table = [], []
    for name, mid, cont, (x0, y0, x1, y1) in zones:
        tried = done = detours = blocked = unreachable = around = 0
        while done < samples and tried < samples * 15:
            tried += 1
            sx, sy = rnd.uniform(x0, x1), rnd.uniform(y0, y1)
            tx, ty = rnd.uniform(x0, x1), rnd.uniform(y0, y1)
            straight = math.hypot(tx - sx, ty - sy)
            if not (100 <= straight <= 1500) or P.At(cont, sx, sy) != 0 or P.At(cont, tx, ty) != 0:
                continue
            if _in_cave(P, cont, sx, sy) or _in_cave(P, cont, tx, ty):
                continue  # (a spot over a cave is down in it: the grid's flat walk can't judge that way)
            # the reference walk: search as far as it takes
            P.PATH_MAX_EXPANSIONS, P.PATH_MAX_CELLS = 400000, 900 * 900
            ref = P.FindPath(cont, sx, sy, tx, ty)
            P.PATH_MAX_EXPANSIONS, P.PATH_MAX_CELLS = limits
            R.Reset()  # routes search again with the addon's limits
            if ref is None:
                unreachable += 1
                continue
            done += 1
            grid = ref[0] if isinstance(ref, tuple) else ref
            # (with a faction, the route goes round the other faction's guards, as the addon's option has it; the grid's
            # walk doesn't: a longer route is no detour when that walk passes them. Western Plaguelands' Bulwark, the
            # overnight sweep, 2026-10-07)
            guards = guard_yards(R, cont, ref, faction)
            for mode in modes:
                R.Reset()
                r = R.Route(cont, sx, sy, tx, ty, lua.table(offroad=(mode == "offroad")))
                pts, kinds = _pts(r)
                run = _blocked_run(P, cont, pts, kinds, (sx, sy), (tx, ty), ns.Terrain[cont])
                share, extra = (DETOUR_SHARE, DETOUR_YD) if mode == "offroad" else (ROAD_DETOUR_SHARE, ROAD_DETOUR_YD)
                issue = None
                if r.length > max(grid * share, grid + extra):
                    if guards >= GUARDS_YD:
                        around += 1
                    else:
                        detours += 1
                        issue = "detour"
                if run >= BLOCKED_RUN_YD:
                    blocked += 1
                    issue = "blocked" if not issue else issue + "+blocked"
                if issue:
                    flagged.append({"zone": name, "uiMap": mid, "cont": cont, "mode": mode, "issue": issue,
                                    "start": [round(sx, 1), round(sy, 1)], "stop": [round(tx, 1), round(ty, 1)],
                                    "route_yd": round(r.length), "grid_walk_yd": round(grid),
                                    "straight_yd": round(straight), "blocked_run_yd": round(run)})
        table.append((name, done, detours, blocked, unreachable))
        log(f"  {name:32s} trips {done:3d}  detours {detours:2d}  blocked {blocked:2d}  (no walk {unreachable})"
            + (f"  (round the other faction's guards {around})" if around else ""))
    flagged.sort(key=lambda f: f["route_yd"] / max(1, f["grid_walk_yd"]), reverse=True)
    return {"samples": samples, "seed": seed, "modes": list(modes), "faction": faction, "zones": [
        {"zone": z, "trips": d, "detours": de, "blocked": b, "unreachable": u} for z, d, de, b, u in table],
        "flagged": flagged}


def write_report(result: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "report.json"
    p.write_text(json.dumps(result, indent=1), encoding="utf-8")
    return p
