"""Interior maps (caves, mines, cellars, a city's halls) from another WoW version, where the interior is laid out as
WoW Forever's (Data/InteriorMaps.lua, `agps interior-maps`; issue #41, as dungeonmaps.py did for dungeons, #4).

WoW Forever's client has no maps of its own for the interiors on its continents (no micro maps: its map rules are
Classic Era's), so a cave's map in the addon is its models' minimap art (G.CaveArt). The retail client's tables have
them (UiMap Type 5, a micro map, and Types 4 and 6, assigned to a continent's models), and their art's textures are
in WoW Forever's own client too, byte for byte: the addon draws them by FileDataID at runtime; nothing is shipped.

Each candidate floor is checked against WoW Forever's own client with dungeonmaps.verify_floor:
- a map of a model's **indoor rooms** (the source ties it to WMO groups and every one is indoor, MOGI 0x2000): every
  model over the box round its rooms (`ROOMS_PAD_YD` more) placed alike, its rooms' footprint alike
  (`FOOTPRINT_MATCH`), inside its bounds (`ALIGN_SHARE`), every art tile in WoW Forever's client with the same
  content. Its art draws those rooms only (a parchment round them), not the land over them, so the ground over its
  bounds (Cataclysm's reshaped hills over Fargodeep Mine) is evidence, not a check (`ground_matched`);
- any other (a map of the land, or of outdoor pieces): as a dungeon's with terrain, every model over its whole
  bounds placed alike and its ground the same (`TERRAIN_SHARE`).
A floor that fails any is skipped with its reason; an interior with none accepted keeps its map as it was.

The inventory (`inventory`) accounts for every candidate the source has on WoW Forever's continents, the capitals
(WoW Forever's own maps), and every cave of WoW Forever's (caves.find_caves): accepted, skipped or unavailable, and
why; it goes to app/azerothgps/data/interior_maps.json and docs/interior-maps.md.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

from . import dungeonmaps as DM
from .extract.spike import ClientData
from .paths import REPO

INVENTORY = Path(__file__).parent / "data" / "interior_maps.json"
DOC = REPO / "docs" / "interior-maps.md"
CONTINENTS = (0, 1)  # (Zephras Isle, 2991, is WoW Forever's own: the source has nothing of it)
MAP_TYPES = (4, 5, 6)  # UiMap types: a dungeon's floor, a micro map, an orphan, assigned to a continent's models
INDOOR = 0x2000  # MOGI flags: an indoor group
ROOMS_PAD_YD = 5.0  # the box round an interior's rooms where every model must be placed alike
PLACE_YD = 1.0  # a model placed this near a map's placement is one of its (G.CAVE_ART_YD in the addon)
CAPITALS = ("Stormwind City", "Ironforge", "Darnassus", "Orgrimmar", "Thunder Bluff", "Undercity")


def candidates(src: ClientData, conts=CONTINENTS) -> dict:
    """Every uiMap of MAP_TYPES with art that the source assigns to one of `conts`: {ui: {name, type, maps}}."""
    maps = {m["ID"]: m for m in src.table("UiMap")}
    xart = {r["UiMapID"] for r in src.table("UiMapXMapArt")}
    on = defaultdict(set)
    for r in src.table("UiMapAssignment"):
        on[r["UiMapID"]].add(r["MapID"])
    out = {}
    for ui, mids in on.items():
        m = maps.get(ui)
        if m and m["Type"] in MAP_TYPES and ui in xart and mids & set(conts):
            out[ui] = {"name": m["Name_lang"], "type": m["Type"], "maps": sorted(mids)}
    return out


def interior_box(src: DM.Models, floor: dict):
    """The box round the floor's rooms (minX, minY, maxX, maxY; in its bounds, ROOMS_PAD_YD more) when it's a map of
    a model's indoor rooms (the source ties it to groups of its models, every one indoor), else None."""
    if not floor["gids"]:
        return None
    region = floor["bounds"]
    groups = DM.floor_groups(src, floor["gids"], region)
    if not groups:
        return None
    boxes = []
    for q, gi in groups:
        w = src.wmo(q.wmo)
        flags = w.get("flags")
        if not flags or not flags[gi] & INDOOR:
            return None
        boxes.append(DM.world_box(q, w["boxes"][gi]))
    return (max(region[0], min(b[0] for b in boxes)) - ROOMS_PAD_YD, max(region[1], min(b[1] for b in boxes)) - ROOMS_PAD_YD,
            min(region[2], max(b[2] for b in boxes)) + ROOMS_PAD_YD, min(region[3], max(b[3] for b in boxes)) + ROOMS_PAD_YD)


def verify_interior(fv: DM.Models, src: DM.Models, floor: dict, fv_ground=None, src_ground=None, art_ok=None) -> dict:
    """dungeonmaps.verify_floor for a continent's interior: its indoor rooms' map by the models round its rooms,
    the ground as evidence; any other map as a dungeon's with terrain. `evidence.checked` says which."""
    box = interior_box(src, floor)
    if box is None:
        res = DM.verify_floor(fv, src, floor, fv_ground, src_ground, art_ok)
        res["evidence"] = {"checked": "the whole map", **res["evidence"]}
    else:
        res = DM.verify_floor(fv, src, floor, fv_ground, src_ground, art_ok, models_region=box, ground=False)
        res["evidence"] = {"checked": "indoor rooms", **res["evidence"]}
    return res


def inventory(fv: ClientData, src: ClientData, log=print, debug_dir: Path | None = None) -> dict:
    """Every interior map the source has on WoW Forever's continents (each floor accepted or skipped and why), the
    capitals, and WoW Forever's caves (accepted, skipped or unavailable: which map covers them)."""
    from .caves import Ground, find_caves

    cands = candidates(src)
    floors_by_map = DM.source_floors(src, MAP_TYPES)
    floors = {f["ui"]: (mid, f) for mid, fl in floors_by_map.items() for f in fl if mid in CONTINENTS}

    def art_ok(fid):
        return fv.casc.has(fid) and fv.casc.root.get(fid) == src.casc.root.get(fid)

    # (the source's maps, one entry per map group: Fargodeep Mine's two floors one interior)
    entries, by_key = [], {}
    for ui in sorted(cands):
        c = cands[ui]
        mid, f = floors.get(ui, (None, None))
        key = ("group", f["group"]) if f and f["group"] else ("ui", ui)
        e = by_key.get(key)
        if e is None:
            e = {"name": f["map_name"] if f else c["name"], "cont": mid if mid is not None else c["maps"][0],
                 "uis": [], "floors": []}
            by_key[key] = e
            entries.append(e)
        e["uis"].append(ui)
        if f is None:
            e["floors"].append({"ui": ui, "name": c["name"], "index": 0, "status": "skipped", "evidence": {},
                                "why": "its assignments don't give it one map's bounds (on maps "
                                       + ", ".join(str(m) for m in c["maps"]) + ")"})
            continue
        e["floors"].append({"ui": ui, "name": f["name"], "index": f["index"], "_floor": f})
    for cont in CONTINENTS:
        mine = [e for e in entries if e["cont"] == cont and any("_floor" in f for f in e["floors"])]
        if not mine:
            continue
        t = time.time()
        fm, sm = DM.Models(fv, cont), DM.Models(src, cont)
        fg, sg = Ground(fv, cont), Ground(src, cont)
        log(f"  continent {cont}: {len(fm.placements)} placements here, {len(sm.placements)} in the source "
            f"({time.time() - t:.1f}s)")
        for e in mine:
            for fe in e["floors"]:
                f = fe.pop("_floor", None)
                if f is None:
                    continue
                res = verify_interior(fm, sm, f, fg, sg, art_ok)
                fe.update(status="accepted" if res["ok"] else "skipped", why=res["why"], evidence=res["evidence"])
                fe["bounds"] = [round(v, 2) for v in f["bounds"]]
                if res["ok"]:
                    fe["data"] = {"bounds": fe["bounds"], "z": res.get("z"), "rooms": res["rooms"],
                                  "places": res["places"], "art": f["art"]}
                if debug_dir is not None:
                    own = all(fv.casc.has(t[0]) for t in f["art"]["tiles"])  # (else the source's art, to look at)
                    DM.render_debug(fv if own else src, f, res.get("footprint"),
                                    Path(debug_dir) / f"{cont}_{f['ui']}_{fe['status']}.png")
                log(f"  {e['name']} floor {f['ui']} {f['name']!r}: {fe['status']} {res['why']}")
    for e in entries:
        e["floors"].sort(key=lambda f: (f["index"], f["ui"]))
        n = sum(f["status"] == "accepted" for f in e["floors"])
        if n:
            e.update(status="accepted", why=f"{n} of {len(e['floors'])} floors match")
        else:
            e.update(status="skipped", why="no floor matches: " + "; ".join(sorted({f["why"] for f in e["floors"]})))
    entries.sort(key=lambda e: (e["cont"], e["name"], e["uis"][0]))

    # (the capitals: WoW Forever has their maps; the addon draws those, and its models' minimap art inside)
    own = defaultdict(list)
    fv_maps = {m["ID"]: m for m in fv.table("UiMap")}
    for r in fv.table("UiMapAssignment"):
        m = fv_maps.get(r["UiMapID"])
        if m and m["Name_lang"] in CAPITALS and r["MapID"] in CONTINENTS and r["UiMapID"] not in own[m["Name_lang"]]:
            own[m["Name_lang"]].append(r["UiMapID"])
    cities = []
    for name in CAPITALS:
        inside = [e["name"] for e in entries if e["name"] == name]
        cities.append({"name": name, "status": "skipped" if own.get(name) else "unavailable", "fv_maps": own.get(name, []),
                       "why": (f"WoW Forever's client has its own map of it (uiMap {', '.join(map(str, own[name]))}): "
                               "nothing to fill in" if own.get(name) else "no map of it in either client")
                       + (f"; the source's maps inside it: see {', '.join(sorted(set(inside)))} above" if inside else "")})

    # (WoW Forever's caves, mines and dens: which map covers each)
    caves = []
    for cont in CONTINENTS:
        named = {}
        for p, _path, name in find_caves(fv, cont):
            label = name or f"(unnamed, at {p.x:.0f}, {p.y:.0f})"
            named.setdefault((label, name == ""), []).append(p)
        for (label, _unnamed), pl in sorted(named.items()):
            # (an accepted floor's by its models, as the addon finds it, G.InteriorMapFor; any by the models' bounds
            # over its map)
            ok, failed, beside = set(), set(), set()
            for e in entries:
                for f in e["floors"]:
                    b = f.get("bounds")
                    if e["cont"] != cont or not b:
                        continue
                    places = f.get("data", {}).get("places", [])
                    if any(abs(x - p.x) <= PLACE_YD and abs(y - p.y) <= PLACE_YD for x, y in places for p in pl):
                        ok.add(e["name"])
                    elif any(DM._overlaps(p.bounds, b) for p in pl):
                        (beside if f["status"] == "accepted" else failed).add(e["name"])
            if ok:
                st, why = "accepted", "its map: " + ", ".join(sorted(ok))
            elif failed:
                st, why = "skipped", "the source's map over it doesn't match: " + ", ".join(sorted(failed))
            elif beside:
                st, why = "unavailable", ("not one of the models of the source's map beside it (" + ", ".join(sorted(beside))
                                          + "): no map of its own")
            else:
                st, why = "unavailable", "the source has no map of it (its models' minimap art stays its map)"
            caves.append({"name": label, "cont": cont, "models": len(pl), "status": st, "why": why})
    return {"source": {"name": DM.SOURCE_NAME, "product": DM.SOURCE_PRODUCT, "build": src.casc.version,
                       "url": DM.SOURCE_URL.format(build=src.casc.version)},
            "client": {"product": fv.casc.product, "build": fv.casc.version},
            "time": time.strftime("%Y-%m-%d"), "interiors": entries, "cities": cities, "caves": caves}


def interior_maps_lua(inv: dict) -> str:
    """Data/InteriorMaps.lua: each accepted interior's floors' maps (numbers and names only)."""
    src = inv["source"]
    lua = DM._lua_str
    out = [f"-- GENERATED by `agps interior-maps --write` from client {inv['client']['build']} and the interior maps of",
           f"-- {src['name']} {src['build']} where their layout is WoW Forever's (app/azerothgps/interiormaps.py;",
           "-- the inventory: docs/interior-maps.md). Do not edit by hand.",
           "local _, ns = ...",
           "",
           "-- [continent] = { { ui, name (the floor's), map (the interior's), index, bounds = { minX, minY, maxX, maxY }",
           "--   (world yards), z = { lo, hi } or nil (its rooms' heights), rooms = { minX, minY, maxX, maxY } (the box round",
           "--   its rooms), places = { x, y, ... } (its models' placements: ns.Interiors rows' spots), artW, artH,",
           "--   tiles = { {fileID, x, y, w, h, texW, texH} } (art pixels, as Maps.lua's) } }",
           "ns.InteriorMaps = {"]
    for cont in CONTINENTS:
        rows = [(e, f) for e in inv["interiors"] if e["cont"] == cont for f in e["floors"] if f["status"] == "accepted"]
        if not rows:
            continue
        out.append(f"  [{cont}] = {{")
        for e, f in rows:
            d = f["data"]
            b, r = d["bounds"], d["rooms"]
            z = f"{{ {d['z'][0]:.1f}, {d['z'][1]:.1f} }}" if d["z"] else "nil"
            places = ", ".join(f"{x:.2f}, {y:.2f}" for x, y in d["places"])
            tiles = ", ".join("{%d,%d,%d,%d,%d,%d,%d}" % tuple(t) for t in d["art"]["tiles"])
            out.append(f"    {{ ui = {f['ui']}, name = {lua(f['name'])}, map = {lua(e['name'])}, index = {f['index']}, "
                       f"bounds = {{ {b[0]:.2f}, {b[1]:.2f}, {b[2]:.2f}, {b[3]:.2f} }}, z = {z}, "
                       f"rooms = {{ {r[0]:.1f}, {r[1]:.1f}, {r[2]:.1f}, {r[3]:.1f} }}, places = {{ {places} }}, "
                       f"artW = {d['art']['w']}, artH = {d['art']['h']},")
            out.append(f"      tiles = {{ {tiles} }} }},")
        out.append("  },")
    out.append("}")
    return "\n".join(out) + "\n"


def inventory_md(inv: dict) -> str:
    src = inv["source"]
    lines = ["# Interior maps: coverage", "",
             "Generated by `agps interior-maps --write` (app/azerothgps/interiormaps.py) on " + inv["time"] + ".", "",
             f"- Source: {src['name']} {src['build']}, its UiMap tables ({src['url']}), read from the local client:",
             "  every micro map (and dungeon or orphan map) it assigns to Eastern Kingdoms or Kalimdor.",
             f"- Checked against WoW Forever {inv['client']['build']}.",
             "- A map of a model's indoor rooms (`checked` \"indoor rooms\") is accepted only when every model round its",
             "  rooms is placed alike, its rooms cover the same ground seen from above (`footprint_matched`), they are",
             "  inside its bounds (`inside_bounds`) and its art tiles are in WoW Forever's own client with the same content.",
             "  Its art draws those rooms only, so the land over them (`ground_matched`) is evidence, not a check. Any",
             "  other map (`checked` \"the whole map\") is checked as a dungeon's with terrain (docs/dungeon-maps.md):",
             "  every model over its bounds placed alike and its ground the same. See the module's docstring.",
             "- A skipped or unavailable interior keeps the map it had (its models' minimap art).",
             "- Pictures of each floor with WoW Forever's rooms outlined over it: `data/debug/interiormaps/` (not in git).",
             ""]
    for status in ("accepted", "skipped"):
        rows = [e for e in inv["interiors"] if e["status"] == status]
        lines += [f"## {status.capitalize()} ({len(rows)})", ""]
        for e in rows:
            lines.append(f"- **{e['name']}** (continent {e['cont']}): {e['why']}")
            for f in e["floors"]:
                evid = ", ".join(f"{k} {v}" for k, v in f["evidence"].items())
                lines.append(f"  - floor {f['ui']} \"{f['name']}\": {f['status']}"
                             + (f" ({f['why']})" if f["why"] else "") + (f"; {evid}" if evid else ""))
        lines.append("")
    lines += [f"## Capitals ({len(inv['cities'])})", ""]
    for c in inv["cities"]:
        lines.append(f"- **{c['name']}**: {c['status']} ({c['why']})")
    lines.append("")
    for status in ("accepted", "skipped", "unavailable"):
        rows = [c for c in inv["caves"] if c["status"] == status]
        lines += [f"## WoW Forever's caves: {status} ({len(rows)})", ""]
        for c in rows:
            lines.append(f"- {c['name']} (continent {c['cont']}, {c['models']} model{'s' if c['models'] > 1 else ''}): "
                         f"{c['why']}")
        lines.append("")
    return "\n".join(lines)


def write(inv: dict, addon_dir: Path) -> list:
    INVENTORY.write_text(json.dumps(inv, indent=1) + "\n", encoding="utf-8", newline="\n")
    DOC.write_text(inventory_md(inv), encoding="utf-8", newline="\n")
    p = addon_dir / "Data" / "InteriorMaps.lua"
    p.write_text(interior_maps_lua(inv), encoding="utf-8", newline="\n")
    return [INVENTORY, DOC, p]
