"""Underground destinations sweep (`agps underground-sweep`): routes to places that sit below the ground (or another
floor) above them, through the whole addon as in the game (gameharness, city and world routing on), and flags a route
that gets there through a floor instead of the place's real way in.

Destinations:
  * NPCs (Data/Npcs.lua) on the continents standing on a floor the world grid has, with another of the grid's floors
    UNDER_YD or more over their heads (caves, mines, cellars, Blackrock Mountain's lower floors, the capitals' lower
    halls), one per CLUSTER_YD square, and the ones down in Undercity (its level, 10001);
  * every dungeon's and raid's way in (Data/Instances.lua's portals): a stop just inside it, so the walk on the
    continent ends at the portal.

Starts, each destination: the nearest flight master of its side (`fm`), the nearest named place at least NEAR_MIN_YD
away (`near`), and for an NPC a spot on the floor over its head (`above`, the player's height given: the case of a
player standing right over the stop).

A route fails with:
  * noway      no route at all (`cliff`: none but a cliff)
  * portal     a portal taken to another dungeon than the stop's (or any, to a stop on the continent)
  * through    a drop or a jump whose foot is under another floor of the grid's between its top and foot (a "Jump
               down here" through a floor), or a stretch climbing or falling more than a slope can (STEEP)
  * bigdrop    a drop higher than the safe drop
  * overhead   the walk to the stop (or to the portal) ends on another floor than the stop's (FLOOR_YD): "arrived" over
               its head or under its feet
  * straight   a straight walking piece of PIECE_YD or more within NEAR_END_YD of the stop (or the portal) the grid
               can't walk on any of its floors (WorldGrid.Open: through rock, a wall, a floor)
Writes data/debug/underground-sweep/report.json and report.md (counts and the worst cases).
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

from .paths import ADDON_DIR

UNDER_YD = 8.0  # a floor this much over an NPC's head: the NPC is under it
FLOOR_YD = 6.0  # a walk ending this near the stop's height is on its floor
CLUSTER_YD = 60.0  # one NPC per square this size
NEAR_MIN_YD = 150.0
FM_MAX_YD = 4000.0
PIECE_YD = 8.0
GRID_PIECE_YD = 40.0  # (the world grid's and city grids' own pieces: this long or more)
NEAR_END_YD = 200.0
STEEP_MIN_DZ = 18.0  # a piece (not a drop, jump or lift) rising or falling this much ...
STEEP_SLOPE = 1.43  # ... and more than this many yards a yard along (+ STEEP_MIN_DZ): through a floor or a ceiling.
# (more than one of the grids' links climbs: citygrid.dz_max over a cell's diagonal, 17.8 yd at 55 degrees. A link's
# own climb drawn over a yard of the route (its points at the cells' edges) is the bake's, counted as `steeplink` notes)
LINK_MIN_DZ = 6.0
THROUGH_GAP = 2.5  # a floor this far from a drop's top and foot, between them, is one it falls through
UNDERCITY = 10001
LEVEL = 60
HOP_KINDS = (4, 8)  # Router.KIND_DROP, KIND_JUMP
LIFT_KINDS = (5, 6)


# --- destinations ------------------------------------------------------------------------------------------------

def shipped_npcs() -> list[dict]:
    """Data/Npcs.lua's lines: {id, name, side, spawns: [(level, x, y, z)]}."""
    text = (ADDON_DIR / "Data" / "Npcs.lua").read_text(encoding="utf-8")
    body = text.split("[==[", 1)[1].split("]==]", 1)[0]
    out = []
    for line in body.strip().splitlines():
        f = line.split("|")
        if len(f) < 7:
            continue
        spawns = []
        for s in f[6].split(";"):
            v = s.split()
            if len(v) == 4:
                spawns.append((int(v[0]), float(v[1]), float(v[2]), float(v[3])))
        out.append({"id": int(f[0]), "name": f[1], "side": f[5], "spawns": spawns})
    return out


def _surfaces(ns, cont, x, y):
    WG = ns.WorldGrid
    c = WG.Cont(cont)
    if not c:
        return []
    s = WG.SurfacesAt(c, x, y)
    return sorted(float(s[i].z) for i in range(1, len(s) + 1)) if s else []


def underground_npcs(ns, log=print, limit: int | None = None) -> list[dict]:
    """The NPCs on the continents with a floor of the grid's over their heads (one per CLUSTER_YD square, the deepest
    under it first), and Undercity's (one per square)."""
    seen, out = set(), []
    for npc in shipped_npcs():
        for lvl, x, y, z in npc["spawns"]:
            key = (lvl, math.floor(x / CLUSTER_YD), math.floor(y / CLUSTER_YD))
            if key in seen:
                continue
            if lvl == UNDERCITY:
                seen.add(key)
                out.append({"kind": "npc", "name": npc["name"], "id": npc["id"], "side": npc["side"], "cont": lvl,
                            "x": x, "y": y, "z": z, "over": None, "base": 0})
                continue
            if lvl not in (0, 1):
                continue
            zs = _surfaces(ns, lvl, x, y)
            if not zs or not any(abs(h - z) <= 4 for h in zs):
                continue  # (not on a floor the grid has: nothing to judge by)
            over = [h for h in zs if h >= z + UNDER_YD]
            if not over:
                continue
            seen.add(key)
            out.append({"kind": "npc", "name": npc["name"], "id": npc["id"], "side": npc["side"], "cont": lvl,
                        "x": x, "y": y, "z": z, "over": min(over), "base": lvl})
    log(f"  {len(out)} underground NPC spots")
    return out[:limit] if limit else out


# (the ways in inside a capital: walked to by its own side; the other's is never routed through the city)
CITY_SIDE = {"Ragefire Chasm": "H", "Ruins of Lordaeron": "H", "The Stockade": "A", "Stormwind Stockade": "A"}


def instance_entrances(ns) -> list[dict]:
    """Every portal into a dungeon or raid from a continent: the stop just inside it."""
    out = []
    rows = ns.Transports
    for i in range(1, len(rows) + 1):
        t = rows[i]
        if t[8] != "portal" or int(t[1]) not in (0, 1):
            continue
        out.append({"kind": "instance", "name": str(t[10]), "side": CITY_SIDE.get(str(t[10]), "B"), "cont": int(t[4]), "x": float(t[5]),
                    "y": float(t[6]), "z": None, "base": int(t[1]), "door": (float(t[2]), float(t[3])),
                    "doorZ": float(t.z1) if t.z1 is not None else None})
    return out


# --- starts --------------------------------------------------------------------------------------------------------

def _pois(ns, cont, kinds):
    for p in (ns.Pois[cont] or {}).values():
        if p[1] in kinds:
            yield p


def _open_ground(ns, cont, x, y) -> bool:
    """Whether (x, y) is out in the open: one floor of the grid's there, not over a cave's cells (a named place can be
    a cave, a mine: the start would be in it, and its floor isn't the case looked at)."""
    if len(_surfaces(ns, cont, x, y)) != 1:
        return False
    P = ns.Passability
    r = P.OverlayRaw(cont, x, y) if P and P.OverlayRaw else None
    grid = r[1] if isinstance(r, tuple) else None
    return not (grid is not None and (grid.cave or grid.capital))


def starts_for(ns, d) -> list[dict]:
    cont = d["base"]
    gx, gy = d.get("door") or (d["x"], d["y"])
    out = []
    side = "A" if d["side"] in ("A", "B") else "H"
    best = None
    for p in _pois(ns, cont, (1,)):
        if p[6] and side in str(p[6]) and not str(p[4]).startswith("zz"):
            dd = math.hypot(float(p[2]) - gx, float(p[3]) - gy)
            if dd <= FM_MAX_YD and (best is None or dd < best[0]):
                best = (dd, float(p[2]), float(p[3]), str(p[4]))
    if best:
        out.append({"start": "fm", "x": best[1], "y": best[2], "name": best[3]})
    best = None
    for p in _pois(ns, cont, (2, 3)):
        dd = math.hypot(float(p[2]) - gx, float(p[3]) - gy)
        if dd >= NEAR_MIN_YD and (best is None or dd < best[0]) and _open_ground(ns, cont, float(p[2]), float(p[3])):
            best = (dd, float(p[2]), float(p[3]), str(p[4]))
    if best:
        out.append({"start": "near", "x": best[1], "y": best[2], "name": best[3]})
    if d["kind"] == "npc" and d.get("over") is not None:
        # (on the floor over its head, a little way off: a cell of the grid's there with a floor UNDER_YD over it)
        for r in (25, 40, 60):
            spot = None
            for a in range(8):
                x, y = d["x"] + r * math.cos(a * math.pi / 4), d["y"] + r * math.sin(a * math.pi / 4)
                up = [h for h in _surfaces(ns, cont, x, y) if h >= d["z"] + UNDER_YD]
                if up:
                    spot = (x, y, min(up))
                    break
            if spot:
                out.append({"start": "above", "x": spot[0], "y": spot[1], "z": spot[2], "name": "over its head"})
                break
    return out


# --- the checks ----------------------------------------------------------------------------------------------------

def _on_floor(ns, cont, x, y, z, near=3.0) -> bool:
    return any(abs(h - z) <= near for h in _surfaces(ns, cont, x, y))


def floor_reached(ns, cont, x, y, z):
    """The grid's floor at (x, y) within 4 yd of z: True when the bake reached it on foot (F_REACH), False when it's
    there but cut off (an island: a bake gap), None when the grid has no such floor."""
    WG = ns.WorldGrid
    c = WG.Cont(cont) if cont in (0, 1) else None
    if not c or z is None:
        return None
    s = WG.SurfacesAt(c, x, y)
    best = None
    for i in range(1, len(s) + 1 if s else 1):
        if abs(float(s[i].z) - z) <= 4:
            reach = int(s[i].f) // 4 % 2 == 1
            best = reach if best is None else (best or reach)
    return best


def _list(t):
    return [t[i] for i in range(1, len(t) + 1)] if t is not None else []


def check_route(lua, ns, r, d) -> list[dict]:
    """The failures of route r to destination d (see the module's doc)."""
    WG = ns.WorldGrid
    issues = []
    notes = check_route.notes = []
    parts = [r.parts[i] for i in range(1, len(r.parts) + 1)] if r.parts else []
    legs = _list(r.legs) if r.legs else []
    rides = [lg.ride for lg in legs if lg.ride]
    # (the portal into the stop's dungeon: since #964 a stretch to a stop inside one ends at the portal, its walks
    # inside and the portal left out of the legs, kept as the stretch's `inside` (Nav.OutsideInstances))
    st = r.firstStretch
    if st is not None and st.inside is not None and st.inside.ride is not None:
        rides.append(st.inside.ride)
    for t in rides:
        if t[8] == "portal" and not (d["kind"] == "instance" and d["cont"] in (int(t[4]), int(t[1]))):
            issues.append({"kind": "portal", "to": str(t[10]), "at": [round(float(t[2]), 1), round(float(t[3]), 1)]})
    if d["kind"] == "instance" and not any(t[8] == "portal" for t in rides):
        issues.append({"kind": "portal", "missing": True})
    safe = float(ns.Nav.SafeDrop())
    # the walk that ends at the stop (an NPC) or at the portal (a dungeon)
    if d["kind"] == "instance":
        gx, gy = d["door"]
        gz = d.get("doorZ")
    else:
        gx, gy, gz = d["x"], d["y"], d["z"]
    last = None
    for p in parts:
        if p.leg and p.pts and len(p.pts) >= 4 and int(p.cont) in (d["base"], d["cont"]):
            px, py = float(p.pts[len(p.pts) - 1]), float(p.pts[len(p.pts)])
            if math.hypot(px - gx, py - gy) < 15:
                last = p
    sources = lua.eval("AGPS_SOURCE")
    for p in parts:
        if not (p.leg and p.pts and len(p.pts) >= 4):
            continue
        src = (sources[p.pts] if sources is not None else None) or "own"
        cont = int(p.cont)
        pts = _list(p.pts)
        xy = [(pts[i], pts[i + 1]) for i in range(0, len(pts), 2)]
        kinds = _list(p.kinds)
        fz = _list(p.fz) if p.fz else (_list(p.zs) if p.zs else [])
        base = cont if cont in (0, 1) else None
        for i in range(len(xy) - 1):
            k = kinds[i] if i < len(kinds) else None
            (x0, y0), (x1, y1) = xy[i], xy[i + 1]
            L = math.hypot(x1 - x0, y1 - y0)
            z0 = fz[i] if i < len(fz) else None
            z1 = fz[i + 1] if i + 1 < len(fz) else None
            if z0 is not None and z1 is not None:
                dz = z1 - z0
                # (heights that are floors of the grid's there: a route's own guess, the Router's road heights, isn't
                # one, and a jump in those isn't the player's)
                real = base is None or (_on_floor(ns, base, x0, y0, z0) and _on_floor(ns, base, x1, y1, z1))
                if k in HOP_KINDS:
                    if -dz > safe + 1:
                        issues.append({"kind": "bigdrop", "at": [round(x0, 1), round(y0, 1)], "dz": round(-dz, 1),
                                       "src": src})
                    # (the world grid's drops are the mesh's own, onto the highest floor under the ledge (worldgrid.py's
                    # mesh_walk): one through a floor is the city grid's or the Router's)
                    if base is not None and src != "wg" and -dz > 2 * THROUGH_GAP:
                        mid = [h for h in _surfaces(ns, base, x1, y1) if z1 + THROUGH_GAP < h < z0 - THROUGH_GAP]
                        if mid:
                            issues.append({"kind": "through", "drop": True, "at": [round(x0, 1), round(y0, 1)],
                                           "top": round(z0, 1), "foot": round(z1, 1), "floor": round(mid[0], 1),
                                           "src": src})
                elif k not in LIFT_KINDS and real and abs(dz) > STEEP_SLOPE * L + STEEP_MIN_DZ:
                    issues.append({"kind": "through", "steep": True, "at": [round(x0, 1), round(y0, 1)],
                                   "dz": round(dz, 1), "yd": round(L, 1), "src": src})
                elif k not in LIFT_KINDS and real and abs(dz) > STEEP_SLOPE * L + LINK_MIN_DZ:
                    notes.append({"kind": "steeplink", "at": [round(x0, 1), round(y0, 1)], "dz": round(dz, 1),
                                  "yd": round(L, 1), "src": src})
            if (k == 1 and base is not None and L >= PIECE_YD and p is last
                    and min(math.hypot(x0 - gx, y0 - gy), math.hypot(x1 - gx, y1 - gy)) <= NEAR_END_YD):
                c = WG.Cont(base)
                # (a grid's own short pieces: its string-pulled lines, walked cell to cell within LINE_TOL; Open's
                # stricter cell walk calls some of those shut. Only its long ones are looked at)
                if src != "own" and L < GRID_PIECE_YD:
                    continue
                if c and WG.Open(c, x0, y0, x1, y1) is False and WG.Open(c, x1, y1, x0, y0) is False:
                    issues.append({"kind": "straight", "at": [round(x0, 1), round(y0, 1)], "to": [round(x1, 1), round(y1, 1)],
                                   "yd": round(L), "src": src})
    if last is not None:
        src = (sources[last.pts] if sources is not None else None) or "own"
        if src == "own" and gz is not None and d["base"] in (0, 1):
            if any(h > gz + UNDER_YD for h in _surfaces(ns, d["base"], gx, gy)):
                # (not a failure by itself: the Router's own walks into the caves by their roads, from their mouths; a
                # straight line of it through the rock is, `straight`)
                notes.append({"kind": "own", "note": "the last walk is the Router's own (no floors), under a floor"})
    if last is not None and gz is not None:
        fz = _list(last.fz) if last.fz else (_list(last.zs) if last.zs else [])
        if fz:
            if fz[-1] > gz + FLOOR_YD:
                issues.append({"kind": "overhead", "ends": round(fz[-1], 1), "stop": round(gz, 1)})
            elif fz[-1] < gz - FLOOR_YD:
                # (at the foot of the stop's building, its own floor up the stairs out of the grid's reach: Nav says
                # it's above; the stairs are the bake's to find. A fail only far under it)
                (issues if fz[-1] < gz - 40 else notes).append(
                    {"kind": "overhead" if fz[-1] < gz - 40 else "below", "ends": round(fz[-1], 1), "stop": round(gz, 1)})
    return issues


# --- running -------------------------------------------------------------------------------------------------------

def _game():
    from .gameharness import start

    lua, ns = start()
    ns.Nav.FUN = False
    ns.settings.gps.cityGrid = True
    ns.settings.gps.worldGrid = True
    ns.settings.gps.fastestOrder = False
    ns.settings.gps.useFlights = False
    ns.Nav.FlightsChanged()
    lua.execute(f"AGPS_LEVEL = {LEVEL}")
    # (which grid each walk came from, by its points' table: the world grid's, a city grid's, or the Router's own)
    lua.execute("""
      AGPS_SOURCE = setmetatable({}, { __mode = "k" })
      local R = AGPS_NS.Router
      local route = R.Route
      R.Route = function(...)
        local r = route(...)
        if type(r) == "table" and r.pts then
          AGPS_SOURCE[r.pts] = r.worldGrid and "wg" or r.cityGrid and "cg" or "own"
        end
        return r
      end
    """)
    return lua, ns


def route_one(lua, ns, d, s) -> dict:
    """One trip: the route's summary and its failures."""
    N = ns.Nav
    faction = "Horde" if d["side"] == "H" else "Alliance"
    lua.execute(f"UnitFactionGroup = function() return '{faction}' end")
    ns.CharDB().faction = faction
    N.Clear()
    cont = d["base"]
    z = s.get("z")
    lua.execute(f"AGPS_POS = {{ {s['x']}, {s['y']}, {cont}{', ' + str(z) if z is not None else ''} }}")
    zpart = f", z = {d['z']}" if d.get("z") is not None else ""
    N.SetStops(lua.eval(f"{{ {{ x = {d['x']}, y = {d['y']}, cont = {d['cont']}{zpart}, name = 'stop' }} }}"), False, "red")
    N.Invalidate(True, True)
    ns.Router.WallsChanged()
    row = {"dest": d["name"], "kind": d["kind"], "cont": d["cont"], "to": [round(d["x"], 1), round(d["y"], 1), d.get("z")],
           "start": s["start"], "from": [round(s["x"], 1), round(s["y"], 1), z], "via": s.get("name")}
    t0 = time.perf_counter()
    try:
        r = N.Route(s["x"], s["y"], cont)
        row["secs"] = round(time.perf_counter() - t0, 1)
        if not r:
            row["issues"] = [{"kind": "noway", "cliff": bool(N.noWayCliff)}]
            return row
        steps = N.Steps()
        row["steps"] = [str(steps[i]) for i in range(1, len(steps) + 1)]
        row["yd"] = round(float(r.totalYards or 0))
        row["issues"] = check_route(lua, ns, r, d)
        row["notes"] = check_route.notes
        if d["kind"] == "instance":
            row["reached"] = floor_reached(ns, d["base"], d["door"][0], d["door"][1], d.get("doorZ"))
        else:
            row["reached"] = floor_reached(ns, d["base"], d["x"], d["y"], d.get("z"))
    except Exception as e:  # (a failure in the addon's Lua: a finding too)
        row["issues"] = [{"kind": "error", "error": str(e)[:300]}]
    return row


def _dests(ns, only=None, limit=None, log=print):
    ds = instance_entrances(ns) + underground_npcs(ns, log)
    if only:
        ds = [d for d in ds if only.lower() in d["name"].lower()]
    return ds[:limit] if limit else ds


def _run_shard(args):
    i, n, only, limit = args
    lua, ns = _game()
    out = []
    for k, d in enumerate(_dests(ns, only, limit, log=lambda *_: None)):
        if k % n != i:
            continue
        for s in starts_for(ns, d):
            out.append(route_one(lua, ns, d, s))
    return out


def sweep(jobs: int = 1, only: str | None = None, limit: int | None = None, log=print) -> dict:
    t0 = time.time()
    if jobs > 1:
        import multiprocessing as mp

        with mp.get_context("spawn").Pool(jobs) as pool:
            rows = [r for part in pool.map(_run_shard, [(i, jobs, only, limit) for i in range(jobs)]) for r in part]
    else:
        rows = _run_shard((0, 1, only, limit))
    return summarize(rows, time.time() - t0)


FAIL_KINDS = ("noway", "portal", "through", "bigdrop", "overhead", "straight", "error")


def summarize(rows: list[dict], secs: float = 0.0) -> dict:
    counts = {k: 0 for k in FAIL_KINDS}
    failed = []
    for r in rows:
        ks = {i["kind"] for i in r.get("issues", [])}
        for k in ks:
            counts[k] = counts.get(k, 0) + 1
        if ks:
            failed.append(r)
    notes = {}
    for r in rows:
        for i in r.get("notes", []):
            notes[i["kind"]] = notes.get(i["kind"], 0) + 1
    unreached = sorted({(r["dest"], tuple(r["to"])) for r in rows if r.get("reached") is False})
    dests = {(r["dest"], tuple(r["to"])) for r in rows}
    bad_dests = {(r["dest"], tuple(r["to"])) for r in failed}
    return {"trips": len(rows), "destinations": len(dests), "failed_trips": len(failed),
            "failed_destinations": len(bad_dests), "counts": counts, "notes": notes,
            "unreached_floors": [list(u) for u in unreached], "secs": round(secs), "rows": rows}


def _worst(rows):
    order = {k: i for i, k in enumerate(("portal", "through", "overhead", "straight", "bigdrop", "noway", "error"))}

    def key(r):
        ks = [order.get(i["kind"], 9) for i in r.get("issues", [])]
        return (min(ks) if ks else 99, -len(ks))
    return sorted((r for r in rows if r.get("issues")), key=key)


def write_report(result: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    lines = ["# Underground destinations sweep", "",
             f"{result['trips']} trips to {result['destinations']} destinations, {result['secs']} s.",
             f"Failed: {result['failed_trips']} trips, {result['failed_destinations']} destinations.", "",
             "| Failure | Trips |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in result["counts"].items()]
    lines += ["", f"Notes (not failures): {result.get('notes')}.",
              f"Stops whose floor the world grid has but never reached on foot (a bake gap): "
              f"{len(result.get('unreached_floors', []))}."]
    lines += ["", "## Worst cases", ""]
    for r in _worst(result["rows"])[:60]:
        what = "; ".join(f"{i['kind']} " + json.dumps({k: v for k, v in i.items() if k != 'kind'}) for i in r["issues"][:3])
        lines.append(f"- {r['dest']} ({r['kind']}, level {r['cont']}, {r['to']}) from {r['start']} {r['via']}: {what}")
    p = out_dir / "report.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p
