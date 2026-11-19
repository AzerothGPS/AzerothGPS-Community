"""Import the roads drawn (or erased) in game (Draw a road / Erase a road) into overrides/*.geojson."""

from __future__ import annotations

import json
from pathlib import Path

from ..savedvars.packed import unpacked
from ..savedvars.parser import load_savedvariables

SV_NAME = "AzerothGPS.lua"
WALL_FLOOR_Z = 8.0  # Passability.WALL_FLOOR_Z: a wall eraser takes out the walls drawn within this of its height


def floor_of(t: dict) -> dict:
    """A drawn edit's floor, where floors lie over each other (the addon's Record `z`, `indoors`,
    `down`: the player's height, whether indoors, and down in a cave or under a capital's floor), as
    feature properties: only those it has."""
    out = {}
    if t.get("z") is not None:
        out["z"] = round(float(t["z"]), 1)
    if t.get("indoors") is not None:
        out["indoors"] = bool(t["indoors"])
    if t.get("down"):
        out["down"] = True
    return out


class WallLine(list):
    """A wall's points ([x, y] pairs), with its floor's height `z` when it has one."""
    z: float | None = None


def read_tracks(wtf_account_dir: Path) -> list[dict]:
    tracks = []
    for f in sorted(Path(wtf_account_dir).glob(f"*/SavedVariables/{SV_NAME}")):
        db = load_savedvariables(f).get("AzerothGPSDB") or {}
        raw = db.get("tracks") or []
        for t in raw if isinstance(raw, list) else []:
            t = unpacked(t)  # (1.1.6 saves the points packed, `pk`/`zk`)
            pts = t.get("pts") or []
            # (roads and walls a player imported in the Import and Share window: their own, never the addon's data)
            if len(pts) < 4 or t.get("imported"):
                continue
            heights = heights_of(t, len(pts) // 2)
            tracks.append({
                "continent": int(t.get("continent", -1)),
                "op": t.get("op", "add"),
                "zone": t.get("zone", "?"),
                "time": int(t.get("time", 0)),
                "area": bool(t.get("area")),
                "coords": [[pts[i], pts[i + 1]] for i in range(0, len(pts) - 1, 2)],
                **floor_of(t),
                **heights,
                **recorded_of(t, len(pts) // 2),
                **edit_of(t, len(pts) // 2),
                **ground_of(t, len(pts) // 2),
            })
    return tracks


KINDS = ("ground", "floor", "bridge", "stairs", "lift")  # Router.TRACK_KINDS


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def edit_of(t: dict, n: int) -> dict:
    """A road edited afterwards with the road tools' Edit Road (1.3.10, issue #640): {"kind": one of KINDS,
    "replaces": the time of the track it replaces, "rpart": that track's piece (None: all of it), "edit_stairs": (first,
    last) point of its stairs stretch}: what of it is well formed. {} for none."""
    out = {}
    if t.get("kind") in KINDS:
        out["kind"] = t["kind"]
    if _num(t.get("replaces")):
        out["replaces"] = int(t["replaces"])
        out["rpart"] = int(t["rpart"]) if _num(t.get("rpart")) else None
    raw = _lua_list(t.get("stairs"))
    if not t.get("recorded") and len(raw) == 2 and all(_num(v) for v in raw) and 1 <= int(raw[0]) < int(raw[1]) <= n:
        out["edit_stairs"] = (int(raw[0]), int(raw[1]))
    return out


def edit_pieces(t: dict) -> list[dict]:
    """An edited track's pieces (Router.TrackPieces): its stairs stretch a stairs piece of its own, the rest as the track
    is; each {"coords", "zs", "stair", "kind"}. Without a stairs stretch (or heights for it): the track whole."""
    coords, zs, st = t["coords"], t.get("zs"), t.get("edit_stairs")
    whole = [{"coords": coords, "zs": zs, "stair": bool(t.get("stair")), "kind": t.get("kind")}]
    if not st or not zs:
        return whole
    i, j = st
    out = []
    for a, b, stair in ((1, i, False), (i, j, True), (j, len(coords), False)):
        if b > a:
            out.append({"coords": coords[a - 1:b], "zs": zs[a - 1:b], "stair": stair,
                        "kind": "stairs" if stair else t.get("kind")})
    return out


def apply_replaced(doc: dict) -> set[int]:
    """Take out of an overrides document the drawn roads an edit in it replaced (its features' `replaces`, `rpart`: a
    piece, by its `part`; none: all of them). The times left with no feature at all: to list as dropped (the addon
    forgets its copy, and the watcher never takes it in again)."""
    gone: dict[int, set | None] = {}
    for f in doc["features"]:
        p = f.get("properties", {})
        if p.get("source") == "recorded" and p.get("replaces") is not None:
            r, part = int(p["replaces"]), p.get("rpart")
            if part is None:
                gone[r] = None
            elif r not in gone or gone[r] is not None:
                gone.setdefault(r, set()).add(int(part))
    if not gone:
        return set()

    def replaced(p):
        if p.get("source") != "recorded" or p.get("time") not in gone:
            return False
        parts = gone[p["time"]]
        return parts is None or int(p.get("part") or 0) in parts

    taken = {f["properties"]["time"] for f in doc["features"] if replaced(f.get("properties", {}))}
    doc["features"] = [f for f in doc["features"] if not replaced(f.get("properties", {}))]
    left = {f["properties"].get("time") for f in doc["features"] if f.get("properties", {}).get("source") == "recorded"}
    # (only those it had: a recorded walk not in yet comes in later, cut then)
    return {int(t) for t in taken if t not in left}


def add_dropped(overrides_dir: Path, times) -> None:
    """List `times` in overrides/dropped_tracks.json (dropped_times)."""
    times = {int(t) for t in times}
    if not times:
        return
    f = Path(overrides_dir) / "dropped_tracks.json"
    doc = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    have = set(doc.get("times", []))
    if times <= have:
        return
    doc["times"] = sorted(have | times)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(doc, indent=1), encoding="utf-8")


def _lua_list(v) -> list:
    """A Lua list read back ({1: .., 2: ..} or a list) as a list."""
    if isinstance(v, dict):
        return [v[k] for k in sorted(k for k in v if isinstance(k, int))]
    return list(v) if isinstance(v, list) else []


def recorded_of(t: dict, n: int) -> dict:
    """A walk recorded in game (the road tools' Record, 1.1.6) of `n` points: {"recorded": True, "ind": "01?.." (indoors
    at each point, or None), "zt": [(point, zone text), ..] (where the minimap's zone text changed), "stairs": [(first,
    last), ..] (the player's Stairs Start / End marks, points from 1)}: what of it is well formed. {} for a stroke."""
    if not t.get("recorded"):
        return {}
    rec = t.get("rec") if isinstance(t.get("rec"), dict) else {}
    ind = rec.get("ind")
    ind = ind if isinstance(ind, str) and len(ind) == n and not ind.strip("01?") else None
    raw = _lua_list(rec.get("zt"))
    zt = [(int(raw[i]), str(raw[i + 1])) for i in range(0, len(raw) - 1, 2)
          if isinstance(raw[i], (int, float)) and 1 <= int(raw[i]) <= n and isinstance(raw[i + 1], str)]
    raw = _lua_list(t.get("stairs"))
    stairs = [(int(raw[i]), int(raw[i + 1])) for i in range(0, len(raw) - 1, 2)
              if all(isinstance(v, (int, float)) for v in raw[i:i + 2]) and 1 <= int(raw[i]) < int(raw[i + 1]) <= n]
    # (the floors picked with Shift + wheel while recording, where the pick changed: false for none; `zs` is those
    # filled in for the game, not what was picked)
    raw = _lua_list(rec.get("pk"))
    pk = [(int(raw[i]), float(raw[i + 1]) if isinstance(raw[i + 1], (int, float)) and raw[i + 1] is not True
           and raw[i + 1] is not False else None) for i in range(0, len(raw) - 1, 2)
          if isinstance(raw[i], (int, float)) and 1 <= int(raw[i]) <= n]
    return {"recorded": True, "ind": ind, "zt": zt, "stairs": stairs, "pk": pk}


def heights_of(t: dict, n: int) -> dict:
    """A drawn road's heights (1.1.6's road tools): {"zs": [a height per point], "stair": True}, the parts it has;
    a `zs` not a height for each of its `n` points is left out."""
    out = {}
    zs = t.get("zs")
    if isinstance(zs, dict):  # (a Lua list read back: {1: .., 2: ..})
        zs = [zs[k] for k in sorted(zs)]
    if isinstance(zs, list) and len(zs) == n and all(isinstance(z, (int, float)) for z in zs):
        out["zs"] = [float(z) for z in zs]
    if t.get("stair") and "zs" in out:
        out["stair"] = True
    return out


def ground_of(t: dict, n: int) -> dict:
    """A drawn road's ground heights from the map's data (Ground.lua, 1.3.10, issue #685): {"gz": [a height or None per
    point]} when it has a list of `n` with at least one height; {} otherwise. Taken in as the road's starting heights
    (`gz` on its feature), never as a floor (`zs`): a land road stays a land road."""
    raw = _lua_list(t.get("gz"))
    if len(raw) != n:
        return {}
    gz = [round(float(v), 1) if _num(v) else None for v in raw]
    return {"gz": gz} if any(v is not None for v in gz) else {}


def floor_tracks(overrides_dir: Path) -> dict[int, list[dict]]:
    """The drawn roads with their heights (1.1.6's road tools: a height per point, stairs), per continent: the data
    ships them as they were drawn (Data/Roads.lua's ns.FloorTracks) and the addon puts them on its roads as it does a
    player's own (Router.WithTracks), on their floors; the flat land's build leaves them out. Each {op, time, pts, zs,
    stair, area}."""
    out: dict[int, list[dict]] = {}
    for f in sorted(Path(overrides_dir).glob("roads_*.geojson")):
        cont = int(f.stem.split("_", 1)[1])
        for feat in load_overrides(f)["features"]:
            props = feat.get("properties", {})
            if props.get("source") != "recorded" or props.get("zs") is None:
                continue
            coords = feat["geometry"]["coordinates"]
            out.setdefault(cont, []).append({"op": props.get("op", "add"), "time": int(props.get("time", 0)),
                                             "pts": [v for p in coords for v in p[:2]], "zs": props["zs"],
                                             "stair": bool(props.get("stair")), "area": bool(props.get("area")),
                                             "part": int(props.get("part") or 0),
                                             "kind": props.get("kind") if props.get("kind") in KINDS else None})
    for lst in out.values():
        lst.sort(key=lambda t: (t["time"], t["part"]))
    return out


def parse_shared(text: str) -> list[dict]:
    """Roads from the share page's "Copy road data" text (Feedback.RoadsText), as tracks: "R op continent
    time [z=height] [indoors=1|0] [down=1] x,y x,y ..."."""
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 6 or parts[0] != "R" or parts[1] not in ("add", "remove", "area", "wall", "unwall", "unwallarea",
                                                                   "stair"):
            continue
        fl, rest = {}, parts[4:]
        while rest and "=" in rest[0]:
            k, _, v = rest.pop(0).partition("=")
            fl[k] = v
        try:
            cont, t = int(parts[2]), int(parts[3])
            coords = [[float(a) for a in p.split(",")] for p in rest]
            floor = floor_of({"z": float(fl["z"]) if "z" in fl else None,
                              "indoors": (fl["indoors"] == "1") if "indoors" in fl else None,
                              "down": fl.get("down") == "1"})
        except ValueError:
            continue
        if len(coords) < 2 or any(len(c) != 2 for c in coords):
            continue
        heights = {}
        if "zs" in fl:  # (a height per point: 1.1.6's road tools)
            try:
                zs = [float(v) for v in fl["zs"].split(",")]
            except ValueError:
                continue
            if len(zs) != len(coords):
                continue
            heights = {"zs": zs, **({"stair": True} if parts[1] == "stair" else {})}
        elif parts[1] == "stair":
            continue
        if "gz" in fl:  # (a drawn road's ground heights from the map's data, "-" for none: 1.3.10)
            try:
                gz = [None if v == "-" else float(v) for v in fl["gz"].split(",")]
            except ValueError:
                gz = []
            if len(gz) == len(coords) and any(v is not None for v in gz):
                heights["gz"] = gz
        op = {"area": "remove", "unwallarea": "unwall", "stair": "add"}.get(parts[1], parts[1])
        out.append({"continent": cont, "op": op, "area": parts[1] in ("area", "unwallarea"),
                    "zone": "shared", "time": t, "coords": coords, **floor, **heights})
    return out


def import_shared(text: str, overrides_dir: Path, per_continent: dict | None = None) -> int:
    """Add the shared roads not in the overrides yet (by continent and time)."""
    added = 0
    by_cont: dict[int, list[dict]] = {}
    for t in parse_shared(text):
        by_cont.setdefault(t["continent"], []).append(t)
    for cont, tracks in by_cont.items():
        path = overrides_path(overrides_dir, cont)
        doc = load_overrides(path)
        seen = {f["properties"].get("time") for f in doc["features"] if f["properties"].get("source") == "recorded"}
        new = 0
        for t in tracks:
            if t["time"] in seen:
                continue
            seen.add(t["time"])
            doc["features"].append({
                "type": "Feature",
                "properties": {"op": t["op"], "source": "recorded", "zone": t["zone"], "time": t["time"], "trim": True,
                               **({"area": True} if t["area"] else {}), **floor_of(t),
                               **{k: t[k] for k in ("zs", "stair") if k in t},
                               **({"gz": t["gz"]} if t.get("gz") and "zs" not in t and t["op"] == "add" else {})},
                "geometry": {"type": "LineString", "coordinates": t["coords"]},
            })
            new += 1
        if new:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
            if per_continent is not None:
                per_continent[cont] = per_continent.get(cont, 0) + new
        added += new
    return added


def walls(overrides_dir: Path) -> dict[int, list[list[float]]]:
    """The walls drawn in game per continent (or city level), as the addon has them
    (Passability.WallLines): each "wall" in order, an "unwall" taking out the walls near it
    (or inside it, drawn as a loop) on its floor (both drawn within WALL_FLOOR_Z of each other's
    height, when both have one). { continent: [ WallLine([[x, y], ...]), ... ] }"""
    import math

    def in_loop(poly, x, y):
        inside, j = False, len(poly) - 1
        for i in range(len(poly)):
            (xi, yi), (xj, yj) = poly[i], poly[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
            j = i
        return inside

    def near(line, x, y, r=12.0):
        for (ax, ay), (bx, by) in zip(line, line[1:]):
            vx, vy = bx - ax, by - ay
            L2 = vx * vx + vy * vy
            t = max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / L2)) if L2 > 0 else 0.0
            if math.hypot(ax + vx * t - x, ay + vy * t - y) <= r:
                return True
        return False

    out: dict[int, list] = {}
    for f in sorted(Path(overrides_dir).glob("roads_*.geojson")):
        try:
            cont = int(f.stem.split("_", 1)[1])
        except ValueError:
            continue
        ws: list = []
        for feat in load_overrides(f)["features"]:
            props = feat.get("properties", {})
            line = feat["geometry"]["coordinates"]
            if props.get("op") == "wall":
                w = WallLine(line)
                w.z = props.get("z")
                ws.append(w)
            elif props.get("op") == "unwall":
                area, z = props.get("area"), props.get("z")
                ws = [w for w in ws if not (
                    (z is None or w.z is None or abs(w.z - z) <= WALL_FLOOR_Z)
                    and any(in_loop(line, x, y) if area else near(line, x, y) for x, y in w))]
        if ws:
            out[cont] = ws
    return out


def wall_opens(overrides_dir: Path) -> dict[int, list[dict]]:
    """The wall erasers drawn in game per continent: they also open the terrain's blocked
    ground under them (Passability.OpenAreas). { continent: [ {"pts": [[x, y], ...], "area": bool} ] }"""
    out: dict[int, list] = {}
    for f in sorted(Path(overrides_dir).glob("roads_*.geojson")):
        try:
            cont = int(f.stem.split("_", 1)[1])
        except ValueError:
            continue
        for feat in load_overrides(f)["features"]:
            props = feat.get("properties", {})
            if props.get("op") == "unwall":
                out.setdefault(cont, []).append({"pts": feat["geometry"]["coordinates"], "area": bool(props.get("area"))})
    return out


def dropped_times(overrides_dir: Path) -> set[int]:
    """Drawn roads set aside on purpose (overrides/dropped_tracks.json: {"times": [...]}): never imported,
    and listed as shipped so the addon forgets them (e.g. Undercity strokes drawn before they had a floor)."""
    f = Path(overrides_dir) / "dropped_tracks.json"
    return set(json.loads(f.read_text(encoding="utf-8")).get("times", [])) if f.exists() else set()


def shipped_times(overrides_dir: Path) -> list[int]:
    """The times of the drawn roads the overrides have (the addon drops those from its own list), and
    the dropped ones."""
    out = set(dropped_times(overrides_dir))
    for f in sorted(Path(overrides_dir).glob("roads_*.geojson")):
        for feat in load_overrides(f)["features"]:
            props = feat.get("properties", {})
            if props.get("source") == "recorded" and props.get("time"):
                out.add(int(props["time"]))
    return sorted(out)


def overrides_path(overrides_dir: Path, continent: int) -> Path:
    return Path(overrides_dir) / f"roads_{continent}.geojson"


def load_overrides(path: Path) -> dict:
    if Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return {"type": "FeatureCollection", "features": []}


def import_tracks(wtf_account_dir: Path, overrides_dir: Path, per_continent: dict | None = None,
                  walks=None, only=None) -> int:
    """Append tracks not yet imported (keyed by continent+time) to the GeoJSON overrides.
    `per_continent` (if given) gets the count added per continent. `walks(track)`: a recorded walk's pieces with their
    heights (roads/recorded.py's `walk_pieces`, needing the client), or None when they can't be worked out yet; without
    it, recorded walks wait in the saved variables (never in as flat land roads: one up a building's stairs isn't).
    `only(track)`: the tracks to take, the rest left where they are (another client's: its recorded walks)."""
    added = 0
    by_cont: dict[int, list[dict]] = {}
    dropped = dropped_times(overrides_dir)
    for t in read_tracks(wtf_account_dir):
        if t["time"] in dropped:
            continue
        by_cont.setdefault(t["continent"], []).append(t)
    for cont, tracks in by_cont.items():
        path = overrides_path(overrides_dir, cont)
        doc = load_overrides(path)
        new = 0
        seen = {f["properties"].get("time") for f in doc["features"] if f["properties"].get("source") == "recorded"}
        for t in tracks:
            if t["time"] in seen or (only is not None and not only(t)):
                continue
            if t.get("recorded"):
                pieces = walks(t) if walks else None
                if not pieces:
                    continue
                seen.add(t["time"])
                for k, pc in enumerate(pieces):
                    doc["features"].append({
                        "type": "Feature",
                        "properties": {"op": "add", "source": "recorded", "zone": t["zone"], "time": t["time"],
                                       "trim": True, "recorded": True, **({"part": k} if k else {}),
                                       **({"zs": pc["zs"]} if pc.get("zs") else {}),
                                       **({"stair": True} if pc.get("stair") and pc.get("zs") else {})},
                        "geometry": {"type": "LineString", "coordinates": pc["coords"]},
                    })
            elif t["op"] == "add" and (t.get("kind") or t.get("replaces") is not None or t.get("edit_stairs")):
                # (an edit, Edit Road: as its pieces, each with its kind; the one it replaced taken out below)
                seen.add(t["time"])
                ed = {k: t[k] for k in ("replaces", "rpart") if k in t}
                for k, pc in enumerate(edit_pieces(t)):
                    doc["features"].append({
                        "type": "Feature",
                        "properties": {"op": "add", "source": "recorded", "zone": t["zone"], "time": t["time"],
                                       "trim": True, "edit": True, **({"part": k} if k else {}),
                                       **({"kind": pc["kind"]} if pc.get("kind") else {}),
                                       **({"zs": pc["zs"]} if pc.get("zs") else {}),
                                       **({"stair": True} if pc.get("stair") and pc.get("zs") else {}), **ed},
                        "geometry": {"type": "LineString", "coordinates": pc["coords"]},
                    })
            else:
                seen.add(t["time"])
                doc["features"].append({
                    "type": "Feature",
                    "properties": {"op": t["op"], "source": "recorded", "zone": t["zone"], "time": t["time"],
                                   "trim": True, **({"area": True} if t.get("area") else {}), **floor_of(t),
                                   **{k: t[k] for k in ("zs", "stair") if k in t},
                                   **({"gz": t["gz"]} if t.get("gz") and "zs" not in t and t["op"] == "add" else {})},
                    "geometry": {"type": "LineString", "coordinates": t["coords"]},
                })
            if per_continent is not None:
                per_continent[cont] = per_continent.get(cont, 0) + 1
            added += 1
            new += 1
        if new:
            # (the roads the edits replaced: out, and listed dropped where nothing of them is left)
            add_dropped(overrides_dir, apply_replaced(doc))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return added
