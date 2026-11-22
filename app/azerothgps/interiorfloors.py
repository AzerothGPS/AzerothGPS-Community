"""The floors' heights in the buildings' inside maps, for the road and wall tools (1.3.10; Data/InteriorFloors.lua).

Asked 2026-11-19: zoomed in over a building with the tools on, its own roads are edited on its inside map, and each of
its floors should have a height, as the land has "Ground: N yd" (Data/Heights.lua): shown at the pointer and given to
the roads drawn there (their `gz`, never `zs`). The game gives addons no player height, so it's all from data:

1. **The model's floors** (the fast, complete source): each room (a model group with an inside map, ns.WMOs's) has the
   faces a character stands on (walknet.model_faces, MOPY's solid faces, normal at least FLOOR_SLOPE upright). The flat
   ones (FLAT_YD of height or less across) are gathered by height (CHAIN_YD apart: one floor), each floor's height the
   middle of its area, kept with MIN_AREA square yards or more; floors closer than MERGE_YD are one (the bigger's
   height: a dais, a step down).
2. **The NPCs on them** (a check, and a fill): every creature spawn of the CMaNGOS dump (hostile.DUMP) that walks, in a
   placed building's room: over one of the room's floor faces at about its height (NPC_UNDER_YD under, NPC_OVER_YD
   over it): that floor's confirmed; a floor face there that the gathering left out (a small balcony): its floor added
   from the NPC. In the room with no face under it and no floor near its height: a conflict, for the survey.
3. **Surveyed in game** (overrides/interior_floors.json): heights measured where neither gave one; added to the room's
   floors, replacing one within SURVEY_SAME_YD.

What's left goes to the survey's list (FILE_TODO): rooms with no floor (a room of ROOM_MIN_AREA or more, ROOM_MIN_HIGH
tall), and NPCs standing at a height no floor has. One spot per model's room: its floors are the model's, the same in
every placement.

Heights are the model's own (its groups' frame; the addon adds the placement's z), a list per room in ns.WMOs's group
order (only the groups with art). `agps interior-floors` reports; `--write` writes the Lua and the survey list;
`--import FILE` takes surveyed heights (the survey's export) into the overrides first.
"""

from __future__ import annotations

import bisect
import gzip
import json
import math
import re
from collections import defaultdict
from pathlib import Path

from .paths import ADDON_DIR, RESOURCES

FILE = ADDON_DIR / "Data" / "InteriorFloors.lua"
FILE_TODO = Path(__file__).resolve().parent / "data" / "floor_survey_todo.json"
OVERRIDES = RESOURCES / "overrides" / "interior_floors.json"
CONTINENTS = (0, 1)
FLOOR_SLOPE = 0.64  # (as indoors.py's: a face this upright is stood on)
FLAT_YD = 0.6  # a face with this little height across it is flat: a floor's
CHAIN_YD = 0.75  # flat faces this near in height: one floor
MIN_AREA = 6.0  # square yards: a floor smaller is a shelf, a step, a table
MERGE_YD = 2.5  # floors this near: one (a dais, a step down)
SURVEY_SAME_YD = 1.0  # a floor in the data this near a surveyed height: the same floor (the measured height kept)
NPC_UNDER_YD, NPC_OVER_YD = 1.0, 2.5  # an NPC's spot this far under or over a floor face: standing on it
NPC_FLOOR_YD = 2.5  # an NPC this near a room's floor in height is on it (no face under it: a rug, a doodad)
ROOM_MIN_AREA, ROOM_MIN_HIGH = 25.0, 2.5  # a room with no floor smaller or lower: a chimney, a beam, not to survey
SURVEY_OVER_YD = 1.5  # the survey's spot: this over the guessed floor (the player lands on it)
FLY, SWIM = 4, 2  # (creature_template.InhabitType)
ON_GROUND_YD = 3.0  # an NPC with no floor face under it this near the terrain's height: out on the ground, not inside


# --- reading the shipped interiors (Data/Interiors.lua: the models' rooms and where they're placed) ---------------

def shipped_interiors(text: str | None = None) -> tuple[dict, dict]:
    """(wmos {fid: [ {bbox, name, in} per group with art, in order ]}, places {cont: [(fid, x, y, z, yaw, x0, y0, x1,
    y1)]}) from Data/Interiors.lua."""
    if text is None:
        text = (ADDON_DIR / "Data" / "Interiors.lua").read_text(encoding="utf-8")
    wmos: dict = {}
    places: dict = defaultdict(list)
    part = text.split("ns.Interiors = {", 1)
    cur = None
    for line in part[0].splitlines():
        m = re.match(r"\s*\[(\d+)\] = \{ groups = \{", line)
        if m:
            cur = wmos.setdefault(int(m.group(1)), [])
            continue
        m = re.match(r'\s*\{([-\d.,]+), n = "((?:[^"\\]|\\.)*)", \["in"\] = (true|false)', line)
        if m and cur is not None:
            bb = tuple(float(v) for v in m.group(1).split(","))
            cur.append({"bbox": bb, "name": m.group(2), "in": m.group(3) == "true"})
    cont = None
    for line in part[1].splitlines() if len(part) > 1 else ():
        m = re.match(r"\s*\[(\d+)\] = \{$", line)
        if m:
            cont = int(m.group(1))
            continue
        m = re.match(r"\s*\{(\d+),([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)\},", line)
        if m and cont is not None:
            v = [float(g) for g in m.groups()]
            places[cont].append((int(v[0]),) + tuple(v[1:]))
    return wmos, dict(places)


def to_local(p, x: float, y: float, z: float) -> tuple[float, float, float]:
    """World (x, y, z) in placement `p`'s model frame (as the addon's G.FindInterior)."""
    dx, dy = x - p[1], y - p[2]
    c, s = math.cos(p[4]), math.sin(p[4])
    return dx * c + dy * s, -dx * s + dy * c, z - p[3]


def to_world(p, lx: float, ly: float, lz: float) -> tuple[float, float, float]:
    c, s = math.cos(p[4]), math.sin(p[4])
    return p[1] + lx * c - ly * s, p[2] + lx * s + ly * c, p[3] + lz


# --- the model's floors --------------------------------------------------------------------------------------------

def _area(tri) -> float:
    (x1, y1, _), (x2, y2, _), (x3, y3, _) = tri
    return abs((x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)) / 2


def room_floors(tris: list) -> list[tuple[float, float]]:
    """A room's floors from its floor faces [(z middle, triangle)]: [(height, area)], bottom up."""
    flat = []
    for _zc, tri in tris:
        zs = [v[2] for v in tri]
        a = _area(tri)
        if a > 0 and max(zs) - min(zs) <= FLAT_YD:
            flat.append((sum(zs) / 3, a))
    # (greedy peaks: the heights with the most floor within CHAIN_YD, each MERGE_YD from those taken; not a chain of
    # heights, which runs up a stairs' treads from one floor to the next)
    out: list[tuple[float, float]] = []
    if not flat:
        return out
    flat.sort()
    zs = [z for z, _a in flat]
    ca, cza = [0.0], [0.0]  # (running sums of area and height x area: a window's in two lookups)
    for z, a in flat:
        ca.append(ca[-1] + a)
        cza.append(cza[-1] + z * a)
    for z, _a in sorted(flat, key=lambda t: -t[1]):
        if any(abs(z - o) < MERGE_YD for o, _ in out):
            continue
        i, j = bisect.bisect_left(zs, z - CHAIN_YD), bisect.bisect_right(zs, z + CHAIN_YD)
        total = ca[j] - ca[i]
        if total < MIN_AREA:
            continue
        out.append(((cza[j] - cza[i]) / total, total))
    out.sort()
    return out


def face_z_at(tri, x: float, y: float) -> float | None:
    """The height of triangle `tri` at (x, y), or None when (x, y) isn't over it."""
    (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = tri
    det = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    if abs(det) < 1e-9:
        return None
    a = ((y2 - y3) * (x - x3) + (x3 - x2) * (y - y3)) / det
    b = ((y3 - y1) * (x - x3) + (x1 - x3) * (y - y3)) / det
    c = 1 - a - b
    if a < -1e-6 or b < -1e-6 or c < -1e-6:
        return None
    return a * z1 + b * z2 + c * z3


def g_has_faces(g, k: int) -> bool:
    """Whether room `k` of a model's floors (model_floors's) has any face stood on."""
    return bool(g and g["tris"][k])


def match_groups(geo_groups: list, shipped: list) -> list[int | None]:
    """The model's group number for each shipped room (by its box, rounded as the Lua has it)."""
    out = []
    for g in shipped:
        hit = None
        for gi, (_flags, bb) in enumerate(geo_groups):
            if all(abs(round(a, 1) - b) <= 0.051 for a, b in zip(bb, g["bbox"])):
                hit = gi
                break
        out.append(hit)
    return out


def model_floors(cd, wmos: dict, used: set, log=print) -> dict:
    """{fid: {"floors": [[(z, area)] per shipped room], "tris": [[triangles] per shipped room]}} for the models in
    `used`, from the client."""
    from . import interiors as I
    from . import walknet

    out = {}
    for n, fid in enumerate(sorted(used)):
        rooms = wmos[fid]
        geo = I.read_wmo(cd, fid)
        if geo is None:
            out[fid] = None
            continue
        gis = match_groups(geo.groups, rooms)
        want = {gi for gi in gis if gi is not None}
        try:
            floors, _walls, _liq = walknet.model_faces(cd, fid, FLOOR_SLOPE, groups=want)
        except Exception as e:  # (a model the client can't read: every room to the survey)
            log(f"  model {fid}: {e}")
            out[fid] = None
            continue
        by = defaultdict(list)
        for gi, zc, tri in floors:
            by[gi].append((zc, tri))
        out[fid] = {"floors": [room_floors(by.get(gi, [])) if gi is not None else [] for gi in gis],
                    "tris": [[t for _z, t in by.get(gi, [])] if gi is not None else [] for gi in gis]}
        if (n + 1) % 50 == 0:
            log(f"  {n + 1}/{len(used)} models")
    return out


# --- the NPCs ------------------------------------------------------------------------------------------------------

def npc_spawns(data_dir: Path) -> list[tuple]:
    """Every creature spawn on the continents that walks: (map, x, y, z, entry, name)."""
    from .hostile import DUMP, _rows

    txt = gzip.open(Path(data_dir) / DUMP, "rt", encoding="utf-8", errors="replace").read()
    tmpl = {r["Entry"]: (int(r["InhabitType"] or 0), r["Name"]) for r in _rows(txt, "creature_template")}
    out = []
    for r in _rows(txt, "creature"):
        m = int(r["map"])
        inhabit, name = tmpl.get(r["id"], (1, "?"))
        if m not in CONTINENTS or inhabit in (FLY, SWIM):
            continue
        out.append((m, float(r["position_x"]), float(r["position_y"]), float(r["position_z"]), int(r["id"]), name))
    return out


def _rooms_at(rooms: list, lx: float, ly: float, lz: float) -> list[int]:
    out = []
    for k, g in enumerate(rooms):
        b = g["bbox"]
        if g["in"] and b[0] <= lx <= b[3] and b[1] <= ly <= b[4] and b[2] - 1 <= lz <= b[5] + 1:
            out.append(k)
    return out


def shipped_ground(text: str | None = None):
    """The terrain's height at (cont, x, y) from Data/Heights.lua (heights.grid_at; tiles decoded once): a function."""
    from . import heights as HT

    if text is None:
        path = HT.FILE
        if not path.exists():
            return lambda c, x, y: None
        text = path.read_text(encoding="utf-8")
    n = int(re.search(r"ns\.Heights = \{ n = (\d+)", text).group(1))
    raw: dict = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r"ns\.Heights(\.water)?\[(\d+)\] = \{", line)
        if m:
            cur = None if m.group(1) else raw.setdefault(int(m.group(2)), {})
            continue
        m = re.match(r'  \[(\d+)\] = "(.*)",$', line)
        if m and cur is not None:
            key = int(m.group(1))
            cur[(key // 64, key % 64)] = m.group(2)
    grids: dict = {}

    def at(c, x, y):
        T = HT.adt.TILE_YD
        tx, ty = math.floor(32 - y / T), math.floor(32 - x / T)
        k = (c, tx, ty)
        if k not in grids:
            s = raw.get(c, {}).get((tx, ty))
            grids[k] = HT.decode(s, n + 1) if s else None
        g = grids[k]
        if g is None:
            return None
        fi, fj = ((32 - ty) * T - x) / (T / n), ((32 - tx) * T - y) / (T / n)
        i, j = min(int(fi), n - 1), min(int(fj), n - 1)
        u, v = fi - i, fj - j
        q = (g[i][j], g[i + 1][j], g[i][j + 1], g[i + 1][j + 1])
        if any(a is None for a in q):
            return None
        return q[0] * (1 - u) * (1 - v) + q[1] * u * (1 - v) + q[2] * (1 - u) * v + q[3] * u * v

    return at


# --- the whole build -----------------------------------------------------------------------------------------------

def load_overrides(path: Path = OVERRIDES) -> dict:
    """{(fid, room): [heights]} surveyed in game (the model's own heights)."""
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for key, v in doc.get("rooms", {}).items():
        fid, k = key.split(":")
        out[(int(fid), int(k))] = sorted(float(h) for h in v["heights"])
    return out


def build(cd, data_dir: Path, log=print, interiors_text: str | None = None, spawns=None, geometry=None,
          ground=None) -> dict:
    """{"floors": {fid: [[heights] per room]}, "todo": [...], "report": {...}}."""
    wmos, places = shipped_interiors(interiors_text)
    used = {p[0] for c in CONTINENTS for p in places.get(c, ())}
    used = {f for f in used if f in wmos}
    geo = geometry if geometry is not None else model_floors(cd, wmos, used, log)
    over = load_overrides()
    spawns = spawns if spawns is not None else npc_spawns(data_dir)
    ground = ground if ground is not None else shipped_ground()
    # the floors per room, and where they came from
    floors: dict = {}
    src: dict = {}  # (fid, k) -> {z: "model" | "npc" | "survey"}
    for fid in sorted(used):
        g = geo.get(fid)
        rooms = wmos[fid]
        floors[fid] = []
        for k, room in enumerate(rooms):
            hs = [round(z, 1) for z, _a in (g["floors"][k] if g else [])]
            floors[fid].append(hs)
            src[(fid, k)] = {h: "model" for h in hs}
    # the NPCs: each in a placed building's room
    by_cell: dict = defaultdict(list)
    for c in CONTINENTS:
        for p in places.get(c, ()):
            if p[0] in used:
                for cx in range(int(p[5] // 64), int(p[7] // 64) + 1):
                    for cy in range(int(p[6] // 64), int(p[8] // 64) + 1):
                        by_cell[(c, cx, cy)].append(p)
    confirmed: set = set()
    conflicts: dict = {}  # (fid, k) -> (place, npc, lz)
    npc_added = 0
    for m, x, y, z, entry, name in spawns:
        for p in by_cell.get((m, int(x // 64), int(y // 64)), ()):
            if not (p[5] <= x <= p[7] and p[6] <= y <= p[8]):
                continue
            fid = p[0]
            lx, ly, lz = to_local(p, x, y, z)
            g = geo.get(fid)
            ks = _rooms_at(wmos[fid], lx, ly, lz)
            if not ks:
                continue
            # (over every room there: a face under it at about its height, else a floor near it; the rooms' boxes
            # overlap, upstairs over downstairs, so one of them is enough)
            best = None  # (k, height, from a face)
            for k in ks:
                hs = floors[fid][k]
                under = None
                for tri in (g["tris"][k] if g else ()):
                    fz = face_z_at(tri, lx, ly)
                    if fz is not None and -NPC_UNDER_YD <= lz - fz <= NPC_OVER_YD and (under is None or fz > under):
                        under = fz
                near = min(hs, key=lambda h: abs(h - lz)) if hs else None
                if under is not None and near is not None and abs(near - under) <= MERGE_YD:
                    best = (k, near, False)
                    break
                if under is not None and (best is None or best[2] is None):
                    best = (k, round(under, 1), True)
                elif near is not None and abs(near - lz) <= NPC_FLOOR_YD and best is None:
                    best = (k, near, None)
            if best is None:
                gh = ground(m, x, y)
                if gh is not None and abs(z - gh) <= ON_GROUND_YD:
                    continue  # (out on the ground over a room's box: a cave's under it, a roof's edge)
                k = ks[0]
                if (fid, k) not in conflicts:
                    conflicts[(fid, k)] = (p, (m, x, y, z, entry, name), lz)
                continue
            k, h, added = best
            if added:  # (a floor the gathering left out, a balcony: from the face under the NPC)
                hs = floors[fid][k]
                if all(abs(h - o) > MERGE_YD for o in hs):
                    hs.append(h)
                    hs.sort()
                    src[(fid, k)][h] = "npc"
                    npc_added += 1
            confirmed.add((fid, k, h))
    # the survey's heights win
    surveyed = 0
    for (fid, k), hs in over.items():
        if fid in floors and k < len(floors[fid]):
            floors[fid][k] = _merged(floors[fid][k], [round(h, 1) for h in hs])
            src.setdefault((fid, k), {}).update({round(h, 1): "survey" for h in hs})
            conflicts.pop((fid, k), None)
            surveyed += 1
    # what's left: the survey's list (one placement per model's room)
    first_place: dict = {}
    for c in CONTINENTS:
        for p in places.get(c, ()):
            first_place.setdefault(p[0], (c, p))
    todo = []
    for (fid, k), (p, npc, lz) in sorted(conflicts.items()):
        m, x, y, z, entry, name = npc
        room = wmos[fid][k]
        todo.append({"id": f"{fid}:{k}", "map": m, "wmo": fid, "room": k, "name": room["name"],
                     "x": round(x, 1), "y": round(y, 1), "z": round(z + SURVEY_OVER_YD, 1),
                     "go": f".go xyz {x:.1f} {y:.1f} {z + SURVEY_OVER_YD:.1f} {m}",
                     "need": f"the floor {name} stands on (NPC {entry}; the model has no floor at that height)",
                     "known": floors[fid][k], "place": [round(v, 2) for v in p[1:5]],
                     "expect": round(z, 1), "band": [round(p[3] + room["bbox"][2], 1), round(p[3] + room["bbox"][5], 1)],
                     "ground": _round(ground(m, x, y))})
    for fid in sorted(used):
        cp = first_place.get(fid)
        if not cp:
            continue
        c, p = cp
        for k, room in enumerate(wmos[fid]):
            b = room["bbox"]
            if floors[fid][k] or not room["in"] or (fid, k) in over:
                continue
            if g_has_faces(geo.get(fid), k):  # (only stairs or a ramp, no flat floor: a stairwell, no floor to find)
                continue
            if (b[3] - b[0]) * (b[4] - b[1]) < ROOM_MIN_AREA or b[5] - b[2] < ROOM_MIN_HIGH:
                continue
            lx, ly = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2
            x, y, z = to_world(p, lx, ly, b[2] + SURVEY_OVER_YD)
            todo.append({"id": f"{fid}:{k}", "map": c, "wmo": fid, "room": k, "name": room["name"],
                         "x": round(x, 1), "y": round(y, 1), "z": round(z, 1),
                         "go": f".go xyz {x:.1f} {y:.1f} {z:.1f} {c}",
                         "need": "the room's floor (the model has none there)", "known": [],
                         "place": [round(v, 2) for v in p[1:5]], "expect": None,
                         "band": [round(p[3] + b[2], 1), round(p[3] + b[5], 1)], "ground": _round(ground(c, x, y))})
    n_model = sum(1 for d in src.values() for s in d.values() if s == "model")
    n_npc = npc_added
    rooms_with = sum(1 for fid in floors for hs in floors[fid] if hs)
    report = {"models": len(used), "rooms": sum(len(wmos[f]) for f in used), "rooms_with_floors": rooms_with,
              "floors_model": n_model, "floors_npc": n_npc, "floors_survey": sum(len(v) for v in over.values()),
              "rooms_surveyed": surveyed, "npc_confirmed": len(confirmed), "todo": len(todo)}
    return {"floors": floors, "todo": todo, "report": report}


def _round(v):
    return None if v is None else round(float(v), 1)


# --- checking a height measured for a room (the survey's own rule; the survey addon's Lua does the same) -------------
NEAR_SPOT_YD = 12.0  # a reading this near the room's spot (same map) is for that room
BAND_SLACK_YD = 1.5  # a reading in the room's heights, give or take this
EXPECT_YD = 3.0  # a room with an NPC's height: the reading this near it
GROUND_YD = 1.0  # a reading this near the terrain where the floor isn't: out on the ground


def check_reading(row: dict, map_id: int, x: float, y: float, z: float) -> tuple[bool, str]:
    """(ok, what to say) for a height measured at (x, y, z) on `map_id` for survey row `row`."""
    if map_id != row["map"] or math.hypot(x - row["x"], y - row["y"]) > NEAR_SPOT_YD:
        d = math.hypot(x - row["x"], y - row["y"]) if map_id == row["map"] else None
        return False, (f"Not it: you're {d:.0f} yd from the spot. Teleport there first." if d is not None
                       else "Not it: you're on another map. Teleport there first.")
    lo, hi = row["band"]
    if z < lo - BAND_SLACK_YD:
        return False, f"Not it: z {z:.1f} is under the room (it's {lo:.0f} to {hi:.0f}). Go up."
    if z > hi + BAND_SLACK_YD:
        return False, f"Not it: z {z:.1f} is over the room (it's {lo:.0f} to {hi:.0f}). Go down."
    exp, gr = row.get("expect"), row.get("ground")
    if gr is not None and abs(z - gr) <= GROUND_YD and (exp is None or abs(exp - gr) > EXPECT_YD):
        return False, f"Not it: you're on the ground outside (z {z:.1f}). Go inside."
    if exp is not None and abs(z - exp) > EXPECT_YD:
        way = "up" if z < exp else "down"
        return False, f"Not it: z {z:.1f}, the floor should be about {exp:.0f}. Go {way}."
    return True, f"Captured: {z:.1f} yd"


def lua_text(floors: dict) -> str:
    out = ["-- GENERATED by `agps interior-floors --write` from the client's models, the NPCs' spots and heights surveyed",
           "-- in game (app/azerothgps/interiorfloors.py). Do not edit by hand.",
           "-- The floors' heights in the buildings' inside maps, for the road and wall tools: per model (ns.WMOs's key),",
           "-- per room in ns.WMOs's group order, its floors' heights in the model's own frame (the placement's z added),",
           "-- bottom up, \" \" between; \"\" for none.",
           "local _, ns = ...",
           "ns.InteriorFloors = {"]
    for fid in sorted(floors):
        rooms = floors[fid]
        if not any(rooms):
            continue
        cells = ['"' + " ".join(f"{h:g}" for h in hs) + '"' for hs in rooms]
        out.append(f"  [{fid}] = {{ {', '.join(cells)} }},")
    out.append("}")
    return "\n".join(out) + "\n"


def import_survey(path: Path, out: Path = OVERRIDES) -> int:
    """Heights surveyed in game into the overrides: a JSON {"rooms": {"fid:room": {"z": world z, "place": [x, y, z,
    yaw]}}} (the survey's export); each the model's own height (the world z less the placement's). Returns how many."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    have = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {"rooms": {}}
    n = 0
    for key, v in doc.get("rooms", {}).items():
        zs = v.get("zs") or [v["z"]]
        if not zs:
            continue
        pz = float(v["place"][2])
        hs = sorted({round(float(z) - pz, 1) for z in zs})
        old = have["rooms"].get(key, {}).get("heights", [])
        merged = sorted(set(old) | set(hs))
        have["rooms"][key] = {"heights": merged}
        n += 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(have, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return n


def write_todo(todo: list, path: Path = FILE_TODO) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"todo": todo}, indent=1) + "\n", encoding="utf-8", newline="\n")


def load_todo(path: Path = FILE_TODO) -> list:
    return json.loads(path.read_text(encoding="utf-8"))["todo"] if path.exists() else []


def _merged(have: list, surveyed: list) -> list:
    """A room's floors with the surveyed heights added: a floor within SURVEY_SAME_YD of a surveyed one gives way to it
    (measured beats derived); the room's other floors are kept (a survey measures one floor, not the room's all)."""
    out = [h for h in have if all(abs(h - v) > SURVEY_SAME_YD for v in surveyed)]
    return sorted(set(out) | set(surveyed))


def patch_lua(text: str, over: dict, rooms_of: dict) -> str:
    """Data/InteriorFloors.lua with the surveyed rooms' heights added in ({(fid, room): [heights]}); `rooms_of` {fid:
    number of rooms} for a model the file has no line for yet."""
    lines = text.splitlines()
    by_fid = defaultdict(dict)
    for (fid, k), hs in over.items():
        by_fid[fid][k] = hs
    seen = set()
    for i, line in enumerate(lines):
        m = re.match(r"  \[(\d+)\] = \{ (.*) \},$", line)
        if not m or int(m.group(1)) not in by_fid:
            continue
        fid = int(m.group(1))
        cells = re.findall(r'"([^"]*)"', m.group(2))
        for k, hs in by_fid[fid].items():
            while len(cells) <= k:
                cells.append("")
            cells[k] = " ".join(f"{h:g}" for h in _merged([float(v) for v in cells[k].split()], hs))
        lines[i] = f"  [{fid}] = {{ {', '.join(chr(34) + c + chr(34) for c in cells)} }},"
        seen.add(fid)
    end = max(i for i, line in enumerate(lines) if line == "}")
    for fid in sorted(set(by_fid) - seen):
        cells = [""] * max(rooms_of.get(fid, 0), max(by_fid[fid]) + 1)
        for k, hs in by_fid[fid].items():
            cells[k] = " ".join(f"{h:g}" for h in hs)
        lines.insert(end, f"  [{fid}] = {{ {', '.join(chr(34) + c + chr(34) for c in cells)} }},")
        end += 1
    return "\n".join(lines) + "\n"


# --- the survey: its list into the survey addon's folder, its heights back --------------------------------------------
# (any addon in an AddOns folder whose .toc lists SURVEY_FILE takes the list; its SavedVariables hold what was measured)

SURVEY_FILE = "FloorSurvey.lua"


def survey_addons(addons: Path, file: str = SURVEY_FILE) -> list[tuple[Path, str]]:
    """The addons in AddOns folder `addons` that load `file` (SURVEY_FILE): [(their folder, their saved variable)]."""
    out = []
    if not Path(addons).is_dir():
        return out
    for toc in sorted(Path(addons).glob("*/*.toc")):
        text = toc.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"^\s*" + re.escape(file) + r"\s*$", text, re.M):
            continue
        m = re.search(r"^## SavedVariables:\s*(\w+)", text, re.M)
        out.append((toc.parent, m.group(1) if m else ""))
    return out


def survey_lua(todo: list) -> str:
    """The survey's list as Lua data: `ns.FloorSurvey`, one row per room to measure, in the list's order."""
    def q(s):
        return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'
    out = ["-- GENERATED by `agps floor-survey export` from AzerothGPS's floor list. Do not edit by hand.",
           "-- Each row: a room whose floor height the data couldn't settle. id = model:room; map, x, y, z: where to go;",
           "-- place = the model's placement (x, y, z, yaw); known = the model's floors there (its own heights).",
           "local _, ns = ...",
           "ns.FloorSurvey = {"]
    for e in todo:
        known = ", ".join(f"{h:g}" for h in e.get("known", []))
        place = ", ".join(f"{v:g}" for v in e["place"])
        band = ", ".join(f"{v:g}" for v in e.get("band") or (e["z"] - 10, e["z"] + 10))
        extra = "".join(f", {k} = {e[k]:g}" for k in ("expect", "ground") if e.get(k) is not None)
        out.append(f"  {{ id = {q(e['id'])}, map = {e['map']}, x = {e['x']:g}, y = {e['y']:g}, z = {e['z']:g}, "
                   f"name = {q(e.get('name', ''))}, need = {q(e['need'])}, known = {{ {known} }}, place = {{ {place} }}, "
                   f"band = {{ {band} }}{extra} }},")
    out.append("}")
    return "\n".join(out) + "\n"


def export_survey(addons_dirs, todo: list | None = None, log=print) -> int:
    """Writes the survey's list into every survey addon in `addons_dirs`; how many were written."""
    todo = load_todo() if todo is None else todo
    n = 0
    for addons in addons_dirs:
        for folder, _sv in survey_addons(addons):
            path = folder / SURVEY_FILE
            text = survey_lua(todo)
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                path.write_text(text, encoding="utf-8", newline="\n")
                log(f"floor survey: {len(todo)} rooms to measure -> {path}")
            n += 1
    return n


def read_survey(addons_dirs, captures: Path | None = None) -> dict:
    """The heights measured so far, from the survey addons' SavedVariables (every account under the client's WTF):
    {"rooms": {id: {"zs": [world z], "place": [x, y, z, yaw]}}} (import_survey's input)."""
    from .savedvars.parser import load_savedvariables

    rooms: dict = {}
    # (the survey window's file first: kept as each height came in; the addons' saved heights after, for the rooms it
    # hasn't)
    if captures is not None and Path(captures).exists():
        for key, v in json.loads(Path(captures).read_text(encoding="utf-8")).get("rooms", {}).items():
            if v.get("z") is not None and v.get("place"):
                rooms[str(key)] = {"zs": [float(v["z"])], "place": [float(a) for a in v["place"]]}
    from_file = set(rooms)
    for addons in addons_dirs:
        wtf = Path(addons).parent.parent / "WTF" / "Account"
        for folder, sv in survey_addons(addons):
            if not sv:
                continue
            for f in sorted(wtf.glob(f"*/SavedVariables/{folder.name}.lua")):
                db = load_savedvariables(f).get(sv) or {}
                for key, v in (db.get("floorSurvey") or {}).items():
                    if not isinstance(v, dict) or v.get("z") is None or not v.get("place") or str(key) in from_file:
                        continue
                    place = v["place"]
                    if isinstance(place, dict):
                        place = [place[k] for k in sorted(place)]
                    r = rooms.setdefault(str(key), {"zs": [], "place": [float(a) for a in place]})
                    r["zs"].append(float(v["z"]))
    return {"rooms": rooms}
