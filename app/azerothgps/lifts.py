"""The open world's lifts (asked 2026-11-22, Kooki3z: "freewind post lift seems to be ignored, its a must for passage to
freewind post. Make sure all lifts/portals are considered"): the inventory of every elevator (gameobject type 11) on the
continents, and each lift's two cars' stops with their heights. The lifts themselves are the Router's lift roads (its
source 5: Thunder Bluff's in Data/Capitals.lua, Freewind Post's and the Great Lift's in the road data); the world grid's
bake joins their ends at these stops' heights (worldbake._lift_link). `lua_text` writes them as rides in
ns.Transports' format, not shipped (they'd be the roads' lifts twice).

From the CMaNGOS classic dump (data/thirdparty/cmangos-classic-db, offline). Thunder Bluff's lifts (Data/Capitals.lua's
lift roads) and Undercity's (Data/Transports.lua, its level) are modeled already; the others in the dump on the
continents and why they aren't here: LIFT_SKIPPED.
"""

from __future__ import annotations

import gzip
import math
import re
from pathlib import Path

from .paths import ADDON_DIR, data_dir

DUMP = "thirdparty/cmangos-classic-db/ClassicDB_1_12_1_z2815.sql.gz"
# (entry of the car spawned at the top, of the one at the bottom; the names of the two ends)
LIFTS = (
    (11898, 11899, "The Great Lift, Thousand Needles", "The Great Lift, The Barrens"),
    (11898, 11899, "Below Freewind Post, Thousand Needles", "Freewind Post, Thousand Needles"),
)
LIFT_SECONDS = 30  # the wait for a car (about 15 s on average: two cars, each up and down) and its ride (about 15 s)
LIFT_PAIR_YD = 60  # yards: a lift's top car and bottom car are this near each other
LIFT_SKIPPED = {
    4170: "Thunder Bluff's (Data/Capitals.lua's lift roads)", 4171: "Thunder Bluff's", 47296: "Thunder Bluff's",
    47297: "Thunder Bluff's", 20649: "Undercity's (its level, Data/Transports.lua)", 20652: "Undercity's",
    20655: "Undercity's", 149045: "Searing Gorge's scaffold cars: along a path the dump doesn't give, not up and down",
    149046: "Searing Gorge's scaffold cars", 80022: "Gnomeregan's way in (a dungeon's: 12 yd)", 80023: "Gnomeregan's",
    20650: "Undercity's lift doors", 20651: "Undercity's lift doors", 20653: "Undercity's lift doors",
    20654: "Undercity's lift doors", 20656: "Undercity's lift doors", 20657: "Undercity's lift doors",
    152614: "an 'Elevator' spawned alone in Dun Morogh, Durotar and Tanaris (no other stop: not one players ride)",
}


def _rows(txt: str, table: str):
    for blk in re.findall(r"INSERT INTO `%s` VALUES (.*?);\n" % table, txt, re.S):
        i, n = 0, len(blk)
        while i < n:
            if blk[i] != "(":
                i += 1
                continue
            j, vals, cur, q = i + 1, [], "", False
            while j < n:
                ch = blk[j]
                if q:
                    if ch == "\\":
                        cur += blk[j:j + 2]
                        j += 2
                        continue
                    if ch == "'":
                        q = False
                    cur += ch
                elif ch == "'":
                    q = True
                    cur += ch
                elif ch == ",":
                    vals.append(cur)
                    cur = ""
                elif ch == ")":
                    vals.append(cur)
                    break
                else:
                    cur += ch
                j += 1
            yield vals
            i = j + 1


def _cols(txt: str, table: str) -> list:
    m = re.search(r"CREATE TABLE `%s` \((.*?)\) ENGINE" % table, txt, re.S)
    return [c.strip().split()[0].strip("`") for c in m.group(1).split("\n") if c.strip().startswith("`")]


def elevators(path: Path | None = None) -> list:
    """Every elevator (gameobject type 11) spawned on the continents: [(entry, name, map, x, y, z)]."""
    txt = gzip.open(path or data_dir() / DUMP, "rt", encoding="utf-8", errors="replace").read()
    tc = _cols(txt, "gameobject_template")
    ti, ei, ni = tc.index("type"), tc.index("entry"), tc.index("name")
    names = {}
    for v in _rows(txt, "gameobject_template"):
        try:
            if int(v[ti]) == 11:
                names[int(v[ei])] = v[ni].strip("'")
        except (ValueError, IndexError):
            pass
    gc = _cols(txt, "gameobject")
    ii, mi, xi, yi, zi = (gc.index(k) for k in ("id", "map", "position_x", "position_y", "position_z"))
    out = []
    for v in _rows(txt, "gameobject"):
        try:
            e, m = int(v[ii]), int(v[mi])
        except (ValueError, IndexError):
            continue
        if e in names and m in (0, 1):
            out.append((e, names[e], m, float(v[xi]), float(v[yi]), float(v[zi])))
    return out


def lifts(spawns: list) -> list:
    """[(cont, bottom (x, y, z), top (x, y, z), name of the bottom's end, of the top's)] for LIFTS."""
    out = []
    used = set()
    for top_e, bot_e, n_bot, n_top in LIFTS:
        tops = [s for s in spawns if s[0] == top_e and s not in used]
        # (each of this entry's top cars with the bottom car nearest it; the lifts in LIFTS' order, north first)
        tops.sort(key=lambda s: -s[3])
        for t in tops:
            bots = [s for s in spawns if s[0] == bot_e and s[2] == t[2] and s not in used
                    and math.dist(s[3:5], t[3:5]) <= LIFT_PAIR_YD]
            if not bots:
                continue
            b = min(bots, key=lambda s: math.dist(s[3:5], t[3:5]))
            used.update((t, b))
            out.append((t[2], b[3:6], t[3:6], n_bot, n_top))
            break
    return out


# (every lift's two cars, the entry spawned at the top and the one at the bottom: each car runs in its own shaft, up and
# down between the two stops' heights; Kooki3z 2026-11-22: "for the great lift there are 2", each reached by its own
# ramp. Thunder Bluff's too, for the city grid)
SHAFT_PAIRS = ((11898, 11899), (4170, 4171), (47297, 47296))


def shafts(spawns: list, cont: int | None = None) -> list:
    """Every lift's cars as shafts: [{"x", "y", "lo", "hi", "lift"}] (a car's shaft at its spawn's x, y; `lo`, `hi` the
    pair's two stops' heights; `lift` the pair's index: a lift's two shafts share it), on `cont` (all when None)."""
    out = []
    used = set()
    k = 0
    for top_e, bot_e in SHAFT_PAIRS:
        for t in sorted((s for s in spawns if s[0] == top_e), key=lambda s: -s[3]):
            if t in used or (cont is not None and t[2] != cont):
                continue
            bots = [s for s in spawns if s[0] == bot_e and s[2] == t[2] and s not in used
                    and math.dist(s[3:5], t[3:5]) <= LIFT_PAIR_YD]
            if not bots:
                continue
            b = min(bots, key=lambda s: math.dist(s[3:5], t[3:5]))
            used.update((t, b))
            lo, hi = min(b[5], t[5]), max(b[5], t[5])
            for s in (t, b):
                out.append({"x": s[3], "y": s[4], "lo": lo, "hi": hi, "lift": k, "cont": s[2]})
            k += 1
    return out


LIFT_ROAD_YD = 120.0  # yards: a lift road (the Router's source 5) with an end this near a car's shaft is that lift's
LIFT_PLATFORM_YD = 10.0  # yards round a car's shaft its platforms' floors are (the floor players stand on to board) ...
LIFT_PLATFORM_Z = 2.5  # ... this near the stop's height (never the ground under a raised platform: 4 yd lower at the
# Great Lift's foot, 9 at Thunder Bluff's)
LIFT_GROUND_YD = 60.0  # yards: the mesh's pieces going on this far from a shaft are the ground's (a ramp's, a walkway's)
LIFT_GROUND_Z = 40.0  # ... within this of the stop's height (the other stop's ground isn't it)


def ground_piece(vs: list, nb: list, x: float, y: float, z: float, ok=None) -> set:
    """The polys (indices of `vs`, their outlines; `nb` their neighbors; `ok(i)` walkable) round a lift's stop (x, y,
    z) of the mesh's pieces going on LIFT_GROUND_YD or farther from it within LIFT_GROUND_Z of its height: the ground's,
    reached by a ramp, stairs or a walkway. Not a pocket of the shaft, the structure between two cars, a roof. Those
    within LIFT_PLATFORM_YD * 2 of the shaft."""
    def mid(i):
        v = vs[i]
        return sum(p[0] for p in v) / len(v), sum(p[1] for p in v) / len(v), sum(p[2] for p in v) / len(v)
    near = {}
    for i in range(len(vs)):
        if ok is not None and not ok(i):
            continue
        mx, my, mz = mid(i)
        d = math.dist((mx, my), (x, y))
        if d <= LIFT_GROUND_YD * 2.5 and abs(mz - z) <= LIFT_GROUND_Z:
            near[i] = d
    comp, far = {}, set()
    for s0 in sorted(near):
        if s0 in comp:
            continue
        comp[s0], st = s0, [s0]
        while st:
            p = st.pop()
            if near[p] >= LIFT_GROUND_YD:
                far.add(s0)
            for q in nb[p]:
                if q in near and q not in comp:
                    comp[q] = s0
                    st.append(q)
    return {i for i, d in near.items() if comp[i] in far and d <= LIFT_PLATFORM_YD * 2}


def lua_text(rows: list) -> str:
    lines = ["-- (app/azerothgps/lifts.py) from the CMaNGOS classic dump.",
             "-- The open world's lifts as rides (ns.Transports' format, kind \"lift\"): each its bottom car's stop and its",
             "-- top car's, their heights (z1, z2). Thunder Bluff's and Undercity's are modeled elsewhere.",
             "local _, ns = ...",
             "ns.Transports = ns.Transports or {}"]
    for cont, b, t, n1, n2 in rows:
        lines.append(f'table.insert(ns.Transports, {{ {cont}, {b[0]:.1f}, {b[1]:.1f}, {cont}, {t[0]:.1f}, {t[1]:.1f}, '
                     f'{LIFT_SECONDS}, "lift", "{n1}", "{n2}", "lift", z1 = {b[2]:.1f}, z2 = {t[2]:.1f} }})')
    return "\n".join(lines) + "\n"


def out_path() -> Path:
    return ADDON_DIR / "Data" / "Lifts.lua"


def run(log=print) -> list:
    spawns = elevators()
    rows = lifts(spawns)
    for e in sorted({s[0] for s in spawns}):
        for s in [s for s in spawns if s[0] == e]:
            log(f"  {e} {s[1]}: map {s[2]} ({s[3]:.1f}, {s[4]:.1f}, {s[5]:.1f})"
                + (f"  [not modeled: {LIFT_SKIPPED[e]}]" if e in LIFT_SKIPPED else ""))
    for cont, b, t, n1, n2 in rows:
        log(f"lift {n1} ({b[0]:.1f}, {b[1]:.1f}, {b[2]:.1f}) <-> {n2} ({t[0]:.1f}, {t[1]:.1f}, {t[2]:.1f}), {LIFT_SECONDS} s")
    return rows


# ---------------------------------------------------------------------------------------------------------------------
# Lift timing (item 118, 1.4.1): each car's loop from the client's own TransportAnimation (its keyframes by the car's
# gameobject entry, TransportID; every SequenceID's frames merged by time, as servers read the table: the loop's length
# its last frame's time). Where a car stops at each end and for how long: Data/LiftTimes.lua, phased in game from the
# rides the player is seen taking (Lifts.lua). The cars spawned per the CMaNGOS dump (each car's shaft and spawn height).
# ---------------------------------------------------------------------------------------------------------------------
# (the cars timed: Thunder Bluff's two lifts of two cars, the Great Lift's two, Freewind Post's two, Undercity's three;
# 644415-644423 in the client are copies of Undercity's 20649-20657, the same frames; Gnomeregan's 80023 is a dungeon's)
TIMED_CARS = {
    4170: "Thunder Bluff", 4171: "Thunder Bluff", 47296: "Thunder Bluff", 47297: "Thunder Bluff",
    11898: "Thousand Needles", 11899: "Thousand Needles",
    20649: "Undercity", 20652: "Undercity", 20655: "Undercity",
}
UNDERCITY_LEVEL = 10001  # (Undercity's lifts: the bottom is down in its level, the top the Ruins of Lordaeron's)
DOCK_Z = 2.0  # yards: a car this near an end's height is stopped there (boarded, stepped off)
TIMES_PAIR_YD = 30.0  # yards: a car this near another (not Undercity's) is the same lift's, side by side


def car_track(rows: list) -> tuple[float, list]:
    """A car's loop from its TransportAnimation rows: (period in seconds, [(t, dz)]) with every sequence's frames merged
    by time (the same time twice: its first), the height offsets from its spawn."""
    seen: dict[int, float] = {}
    for r in sorted(rows, key=lambda r: (r["TimeIndex"], r["SequenceID"])):
        seen.setdefault(r["TimeIndex"], r["Pos"][2])
    track = sorted((t / 1000.0, z) for t, z in seen.items())
    return track[-1][0], track


def _z_at(track: list, period: float, t: float) -> float:
    t %= period
    pts = track + [(track[0][0] + period, track[0][1])]
    if t < pts[0][0]:
        t += period
    for (t0, z0), (t1, z1) in zip(pts, pts[1:]):
        if t0 <= t <= t1:
            return z0 if t1 == t0 else z0 + (z1 - z0) * (t - t0) / (t1 - t0)
    return pts[-1][1]


def dock_window(track: list, period: float, near) -> tuple[float, float]:
    """When in the loop the car is stopped at an end (`near(dz)`: within DOCK_Z of it): (arrives, leaves) in seconds into
    the loop (leaves may be past the period: the window wraps). Exactly one window per end (else ValueError)."""
    step = 0.01
    n = int(round(period / step))
    inside = [near(_z_at(track, period, k * step)) for k in range(n)]
    starts = [k for k in range(n) if inside[k] and not inside[k - 1]]
    if len(starts) != 1:
        raise ValueError(f"{len(starts)} stops at an end in one loop")
    k0 = starts[0]
    k = k0
    while inside[(k + 1) % n]:
        k += 1
    return round(k0 * step, 2), round((k + 1) * step, 2)


def car_times(cd, spawns: list | None = None) -> list:
    """Every timed car: [{entry, place, cont, x, y, lo, hi, period, bottom (arrives, leaves), top (...), station, city}]
    (`lo`, `hi` the ends' heights; `station` the index of the lift it's one car of; `city` Undercity's level)."""
    spawns = spawns if spawns is not None else elevators()
    frames: dict[int, list] = {}
    for r in cd.table("TransportAnimation"):
        if r["TransportID"] in TIMED_CARS:
            frames.setdefault(r["TransportID"], []).append(r)
    out = []
    for s in sorted((s for s in spawns if s[0] in TIMED_CARS), key=lambda s: (s[2], s[3], s[4])):
        entry, _, cont, x, y, z = s
        if entry not in frames:
            raise ValueError(f"no TransportAnimation for lift car {entry}")
        period, track = car_track(frames[entry])
        dzs = [dz for _, dz in track]
        lo, hi = min(dzs), max(dzs)
        bottom = dock_window(track, period, lambda dz, lo=lo: dz <= lo + DOCK_Z)
        top = dock_window(track, period, lambda dz, hi=hi: dz >= hi - DOCK_Z)
        out.append({"entry": entry, "place": TIMED_CARS[entry], "cont": cont, "x": x, "y": y, "lo": z + lo,
                    "hi": z + hi, "period": period, "bottom": bottom, "top": top,
                    "city": UNDERCITY_LEVEL if TIMED_CARS[entry] == "Undercity" else None})
    # (a lift's cars: Thunder Bluff's and the Thousand Needles' come in pairs side by side, Undercity's one a shaft)
    station = 0
    for c in out:
        if "station" in c:
            continue
        station += 1
        c["station"] = station
        if c["city"]:
            continue
        for o in out:
            if "station" not in o and o["cont"] == c["cont"] and not o["city"] \
                    and math.dist((o["x"], o["y"]), (c["x"], c["y"])) <= TIMES_PAIR_YD:
                o["station"] = station
    return out


def times_lua(cars: list, version: str = "") -> str:
    lines = [f"-- GENERATED by `agps lifts --times` (app/azerothgps/lifts.py) from client {version}. Do not edit by hand.",
             "-- The lifts' cars and their loops (item 118): the client's TransportAnimation by each car's gameobject entry,",
             "-- the cars' shafts from the CMaNGOS classic dump. Each car: its shaft (cont, x, y), its ends' heights (lo, hi),",
             "-- its loop (period, s) and when in it it's stopped at the bottom and at the top ({ arrives, leaves }, seconds",
             "-- into the loop; leaves past the period: it wraps). `station`: the lift it's a car of (its cars side by side);",
             "-- `city`: Undercity's level (down in it is the bottom). Phased in game from the rides seen (Lifts.lua).",
             "local _, ns = ...",
             "ns.LiftCars = {"]
    for c in cars:
        city = f", city = {c['city']}" if c["city"] else ""
        lines.append(f'  {{ entry = {c["entry"]}, place = "{c["place"]}", station = {c["station"]}, cont = {c["cont"]}, '
                     f'x = {c["x"]:.1f}, y = {c["y"]:.1f}, lo = {c["lo"]:.1f}, hi = {c["hi"]:.1f}, '
                     f'period = {c["period"]:.3f}, bottom = {{ {c["bottom"][0]:.2f}, {c["bottom"][1]:.2f} }}, '
                     f'top = {{ {c["top"][0]:.2f}, {c["top"][1]:.2f} }}{city} }},')
    lines.append("}")
    return "\n".join(lines) + "\n"


def times_path() -> Path:
    return ADDON_DIR / "Data" / "LiftTimes.lua"


def write_times(cd, log=print) -> Path:
    """Data/LiftTimes.lua from the client's TransportAnimation and the dump's cars."""
    cars = car_times(cd)
    for c in cars:
        log(f"  {c['place']} car {c['entry']} ({c['x']:.1f}, {c['y']:.1f}) station {c['station']}: loop "
            f"{c['period']:.3f} s, {c['lo']:.1f}..{c['hi']:.1f}; bottom {c['bottom'][0]:.2f}-{c['bottom'][1]:.2f}, "
            f"top {c['top'][0]:.2f}-{c['top'][1]:.2f}")
    p = times_path()
    p.write_text(times_lua(cars, cd.casc.version), encoding="utf-8", newline="\n")
    return p
