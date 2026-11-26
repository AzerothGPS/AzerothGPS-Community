"""Stand-in NPCs for WoW Forever's own content (Kooki3z, 2026-11-25: "fill what our data lacks from Wowhead's Forever
pages as stand-in data; I'll replace it with real in-game recordings later").

Riverglades, Mount Hyjal and Shen'dralas have no NPCs in the 1.12 dump, the client's files or the server snapshot
(data/zones_without_npcs.json). Until the NPC logger has them from the live game, Wowhead's WoW Forever pages stand in:
each zone page's NPC list (its Listview: id, name, tag, react) and each NPC page's map spots (its `g_mapperData`:
zone %), scraped in a browser by STANDIN_SCRAPE_JS (Wowhead's pages are script-rendered and ask a person to pass a
human check now and then: the scrape is run by hand, one zone at a time, with a pause between pages) into a JSON list,
taken in by `agps standin-npcs --import SCRAPE.json [--write]`.

Kept in FILE, every entry `"source": "wowhead-standin"` and `"verified": false`:

    {"npcs": {"<id>": {"name", "sub", "svc", "side", "zone", "uiMap", "source", "verified", "url",
                       "spawns": [{"level", "x", "y", "z", "pct": [x%, y%], "zFrom": "grid"|"terrain"|"none"}]}}}

`agps npcs --write` (npcs.build) and `agps standin-npcs --write` put them in Data/Npcs.lua after the dump, the server
snapshot and the logged NPCs: an NPC any of those has is theirs (real data wins), so a stand-in drops out as soon as
the NPC is logged in game. Their ids are listed in Data/Npcs.lua as `ns.NpcsStandIn` (Layers' `n.standin`), and
`--list FILE` writes them as a Markdown table to check in game.

Spots: zone % to world yards by Data/Maps.lua's bounds of the NPC's uiMap (X north, Y west: x% runs west to east,
y% north to south). Height: the world grid's surfaces in the cell (AGPS_WORLDGRID_DIR's tiles, `agps world-grid`),
the one nearest the terrain's height (an NPC stands on the ground floor unless the data says otherwise), else the
terrain's (Data/Heights.lua), else 0. Services and trainer kinds from the tag (TAG_SERVICES) and the NPC page's tabs
(sells, teaches, starts/ends: vendor, trainer, quests); the side from Wowhead's react (Alliance, Horde: 1 friendly,
0 neutral, -1 hostile, null unknown).
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from .paths import RESOURCES

FILE = RESOURCES / "overrides" / "standin_npcs.json"
SOURCE = "wowhead-standin"
TILE = 1600 / 3
SVC_ORDER = "gqvfthibpdmasr"  # (Data/Npcs.lua's letters, the dump's order)

# a tag (Wowhead's, the game's subname) -> the services it means (first match, case-insensitive)
TAG_SERVICES = (
    (r"innkeeper", "gvi"),
    (r"banker", "gb"),
    (r"stable ?master", "gs"),
    (r"(gryphon|wind rider|hippogryph|bat|flight|dragonhawk) (master|mistress|handler)", "gf"),
    (r"auctioneer", "ga"),
    (r"battlemaster", "gm"),
    (r"guild master", "gp"),
    (r"tabard", "gd"),
    (r"spirit healer", "gh"),
    (r"weapons? (trainer|master)", "gt"),
    (r"(warrior|paladin|hunter|rogue|priest|shaman|mage|warlock|druid) trainer", "gt"),
    (r"(apprentice|journeyman|expert|artisan|master)\b.*\b(alchemist|blacksmith|cook|enchanter|engineer|fisherman|"
     r"herbalist|leatherworker|miner|skinner|tailor|physician|surgeon|medic|goblin engineer|gnomish engineer)", "gt"),
    (r"(trainer|instructor)", "gt"),
    (r"^(alchemy|blacksmithing|enchanting|engineering|herbalism|leatherworking|mining|skinning|tailoring|cooking|"
     r"first aid|fishing)$", "gt"),  # (a profession's name alone: Shen'dralas' trainers)
    (r"(armorer|weaponsmith|armorcrafter|gunsmith|bowyer|blacksmithing supplies|repair)", "gvr"),
    (r"(goods|supplies|supplier|vendor|merchant|food|drink|bartender|butcher|baker|quartermaster|reagent|poison|"
     r"fruit|specialty|black market|fisherman|fishing|cook|tradesman|provisioner)", "gv"),
)


def services_of(tag: str, tabs=(), has_quests: bool = False) -> str:
    """Data/Npcs.lua's service letters for a Wowhead tag and page tabs."""
    have = set()
    low = (tag or "").lower()
    for pat, svc in TAG_SERVICES:
        if re.search(pat, low):
            have.update(svc)
            break
    tabs = set(tabs or ())
    if "sells" in tabs:
        have.add("v")
    if "teaches" in tabs or "trains" in tabs:
        have.add("t")
    if has_quests or tabs & {"starts", "ends"}:
        have.add("q")
    have.add("g")
    if "innkeeper" not in low:
        have.discard("i")
    return "".join(c for c in SVC_ORDER if c in have)


def side_of(react) -> str | None:
    """"A", "H" or "B" from Wowhead's react [alliance, horde]; None when hostile (or unknown) to both."""
    a, h = (list(react or []) + [None, None])[:2]
    ok_a, ok_h = a is not None and a >= 0, h is not None and h >= 0
    if ok_a and ok_h:
        return "B"
    if ok_a:
        return "A"
    if ok_h:
        return "H"
    return None


CLUSTER_PCT = 3.0  # (zone %: about 100 yd in Riverglades)


def clusters(coords) -> list[tuple[float, float]]:
    """Zone % spots, those chained within CLUSTER_PCT of each other one: each group's middle, in the list's order."""
    groups: list[list] = []
    for px, py in coords:
        p = (float(px), float(py))
        near = [g for g in groups if any(math.hypot(p[0] - q[0], p[1] - q[1]) <= CLUSTER_PCT for q in g)]
        merged = [p] + [q for g in near for q in g]
        groups = [g for g in groups if all(g is not n for n in near)] + [merged]
    out = []
    for g in groups:
        out.append((round(sum(q[0] for q in g) / len(g), 1), round(sum(q[1] for q in g) / len(g), 1)))
    return sorted(out)


def pct_to_world(bounds, px: float, py: float) -> tuple[float, float]:
    """Zone % (x west to east, y north to south) to world yards by Data/Maps.lua's bounds (minX, minY, maxX, maxY)."""
    x0, y0, x1, y1 = bounds
    return x1 - py / 100 * (x1 - x0), y1 - px / 100 * (y1 - y0)


class Heights:
    """A spot's height: the world grid's surface nearest the terrain, else the terrain's."""

    def __init__(self):
        self._terrain = {}
        self._tiles = {}

    def terrain(self, cont: int, x: float, y: float):
        h = self._terrain.get(cont)
        if h is None:
            try:
                from .worldbake import Heights as WBH
                h = self._terrain[cont] = WBH(cont)
            except Exception:
                h = self._terrain[cont] = False
        if h is False:
            return None
        import numpy as np
        v = h.sample(np.array([x], float), np.array([y], float))[0]
        return None if v != v else float(v)

    def surfaces(self, cont: int, x: float, y: float) -> list[float]:
        from . import worldgrid as W
        import numpy as np

        per = W.CELL_PER_TILE
        tx, ty = math.floor(32 - y / TILE), math.floor(32 - x / TILE)
        key = (cont, tx, ty)
        if key not in self._tiles:
            p = W.tile_grid_path(cont, tx, ty, per)
            g = None
            if p.exists():
                z = np.load(p)
                if "cell" in z.files:
                    g = (z["cell"], z["z"], z["kind"])
            self._tiles[key] = g
        g = self._tiles[key]
        if g is None:
            return []
        gx0, gy0 = W.tile_origin(tx, ty, per)
        c = W.cell_yd(per)
        a, b = math.floor(x / c) - gx0, math.floor(y / c) - gy0
        if not (0 <= a < per and 0 <= b < per):
            return []
        cells, zs, kinds = g
        m = (cells == a * per + b) & (kinds == W.KIND_GROUND)
        return sorted(float(v) for v in zs[m])

    def at(self, cont: int, x: float, y: float) -> tuple[float, str]:
        t = self.terrain(cont, x, y)
        ss = self.surfaces(cont, x, y)
        if ss:
            ref = t if t is not None else ss[0]
            return round(min(ss, key=lambda s: abs(s - ref)), 1), "grid"
        if t is not None:
            return round(t, 1), "terrain"
        return 0.0, "none"


def load(path: Path = FILE) -> dict:
    p = Path(path)
    if not p.exists():
        return {"npcs": {}}
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc.setdefault("npcs", {})
    return doc


def save(doc: dict, path: Path = FILE) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    out = {"_note": NOTE, "npcs": {k: doc["npcs"][k] for k in sorted(doc["npcs"], key=int)}}
    p.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


NOTE = ("Stand-in NPCs from Wowhead's WoW Forever pages (unverified; agps standin-npcs, app/azerothgps/standin.py). "
        "Real data (the dump, the server snapshot, NPCs logged in game) replaces each one by its id.")


def from_scrape(rows: list[dict], maps: dict, heights: Heights | None = None, log=print) -> dict:
    """The scrape's rows ({id, name, tag, react, hasQuests, tabs, zone, uiMap, map: g_mapperData}) as FILE's entries
    {id: entry}. `maps`: uiMap -> (continent, bounds) (cityplaces.map_bounds). Only the spots on the row's own zone
    map (`uiMap`, the zone page's; all of them when 0), those within CLUSTER_PCT of each other one spawn (their
    middle: Wowhead lists a wanderer's every spot). An NPC hostile to both sides, with nothing to offer (services
    past gossip: by its tag, quests or page tabs), or with no spot on a map we have, is left out (logged)."""
    heights = heights or Heights()
    out = {}
    for r in rows:
        nid = int(r["id"])
        side = side_of(r.get("react"))
        if side is None:
            log(f"  {nid} {r.get('name')}: hostile to both, left out")
            continue
        tag = r.get("tag") or ""
        tabs = r.get("tabs") or []
        if services_of(tag, tabs, bool(r.get("hasQuests"))) == "g":
            log(f"  {nid} {r.get('name')}: nothing to offer, left out")
            continue
        own = int(r.get("uiMap") or 0)
        spawns = []
        for zone_spots in (r.get("map") or {}).values():
            for spot in zone_spots or []:
                ui = int(spot.get("uiMapId") or 0)
                m = maps.get(ui)
                if not m or (own and ui != own):
                    continue
                cont, bounds = m
                for px, py in clusters(spot.get("coords") or []):
                    x, y = pct_to_world(bounds, px, py)
                    z, zf = heights.at(cont, x, y)
                    spawns.append({"level": cont, "x": round(x, 1), "y": round(y, 1), "z": z,
                                   "pct": [px, py], "zFrom": zf})
        if not spawns:
            log(f"  {nid} {r.get('name')}: no spot on a map we have, left out")
            continue
        from .npcs import server_trainer_kind
        svc = services_of(tag, tabs, bool(r.get("hasQuests")))
        out[nid] = {"name": r["name"], "sub": tag, "svc": svc,
                    "trainer": server_trainer_kind(0x10 if "t" in svc else 0, tag), "side": side,
                    "zone": r.get("zone") or "", "uiMap": int(r.get("uiMap") or 0), "source": SOURCE,
                    "verified": False, "url": f"https://www.wowhead.com/forever/npc={nid}", "spawns": spawns}
    return out


def snap_to_shipped_grid(doc: dict, log=print) -> int:
    """Each stand-in spawn whose height has no floor in the addon's own world grid within worldcoverage.FLOOR_Z (or
    only floors not reached on foot) takes that cell's floor nearest it, reached on foot first (the bake the heights
    came from may differ from the shipped one; a stop on no floor is one the grid can't walk to). The spawns moved."""
    from . import worldcoverage as WC

    lua, ns = WC._game()
    WG, CG = ns.WorldGrid, ns.CityGrid
    moved = 0
    for key, n in doc.get("npcs", {}).items():
        for s in n["spawns"]:
            lv, x, y, z = int(s["level"]), float(s["x"]), float(s["y"]), float(s.get("z", 0.0))
            if CG.CityFor(lv, x, y) or CG.GridCityAt(lv, x, y) or WG.NotMeshed(lv, x, y):
                continue
            c = WG.Cont(lv)
            if not c:
                continue
            fl = [f for f in WC._surfaces(ns, c, x, y) if not WC._swim(f)]
            near = [f for f in fl if abs(float(f.z) - z) <= WC.FLOOR_Z]
            if not fl or any(WC._reach(f) for f in near):
                continue
            pick = [f for f in fl if WC._reach(f)] or fl
            best = round(float(min(pick, key=lambda f: abs(float(f.z) - z)).z), 1)
            if log:
                log(f"  {key} {n['name']}: z {z} -> {best} (the shipped grid's floor)")
            s["z"], s["zFrom"] = best, "shipped grid"
            moved += 1
    ns.settings.gps.worldGrid = False
    ns.settings.gps.cityGrid = False
    return moved


def add_standin(npcs: dict, doc: dict, log=None) -> list[int]:
    """FILE's stand-ins into `npcs` (Data/Npcs.lua's {id: npc}) in place, each marked `"from": "standin"`; an id
    already there (real data: the dump, the snapshot, logged in game) is skipped. Their ids."""
    out = []
    for key, n in sorted(doc.get("npcs", {}).items(), key=lambda kv: int(kv[0])):
        nid = int(key)
        have = npcs.get(nid)
        if have is not None and have.get("from") != "standin":
            if log:
                log(f"stand-in npc {nid} ({n.get('name')}): real data has it, skipped")
            continue
        spawns = [(int(s["level"]), float(s["x"]), float(s["y"]), float(s.get("z", 0.0))) for s in n["spawns"]]
        if not spawns:
            continue
        npcs[nid] = {"name": n["name"], "sub": n.get("sub", ""), "svc": n.get("svc", ""),
                     "trainer": n.get("trainer", ""), "side": n.get("side", "B"), "spawns": spawns,
                     "from": "standin"}
        out.append(nid)
    return out


def list_md(doc: dict, shipped: set[int] | None = None) -> str:
    """The stand-ins as a Markdown list to check in game: zone, name, role, zone %, world x y z."""
    by_zone: dict[str, list] = {}
    for key, n in doc.get("npcs", {}).items():
        by_zone.setdefault(n.get("zone") or "?", []).append((int(key), n))
    lines = ["# WoW Forever stand-in NPCs (unverified)", "",
             "From Wowhead's WoW Forever pages, shipped in Data/Npcs.lua marked stand-in (`ns.NpcsStandIn`). Check "
             "each in game: the NPC logger's mark (or Mark NPC Here) replaces it with the real spot.", ""]
    for zone in sorted(by_zone):
        rows = sorted(by_zone[zone], key=lambda t: t[1]["name"])
        lines += [f"## {zone} ({len(rows)})", "", "| Name | Role | Side | Zone % | World x, y, z | Id |",
                  "|---|---|---|---|---|---|"]
        for nid, n in rows:
            s = n["spawns"][0]
            more = f" (+{len(n['spawns']) - 1})" if len(n["spawns"]) > 1 else ""
            skip = " (real data has it)" if shipped is not None and nid not in shipped else ""
            lines.append(f"| {n['name']}{skip} | {n.get('sub') or '-'} ({n.get('svc')}) | {n.get('side')} | "
                         f"{s['pct'][0]:.1f}, {s['pct'][1]:.1f}{more} | {s['x']:.1f}, {s['y']:.1f}, {s['z']:.1f} "
                         f"| [{nid}]({n.get('url')}) |")
        lines.append("")
    return "\n".join(lines)


# Run in a browser's console on a Wowhead WoW Forever zone page (www.wowhead.com/forever/zone=<id>) once its page
# shows (pass the human check by hand if asked): it reads the zone's NPC list, fetches each NPC page that might offer
# something (a tag or quests, not hostile to both) with a pause between, and copies the JSON list to the clipboard
# (also in window.__standin). Save it as a file and run `agps standin-npcs --import FILE`.
STANDIN_SCRAPE_JS = r"""
(async () => {
  const PAUSE_MS = 4000;
  const zone = document.title.split(' - ')[0];
  const zoneId = (location.href.match(/zone=(\d+)/) || [])[1];
  const ok = x => x.react && x.react.some(r => r !== null && r >= 0) && (x.tag || x.hasQuests);
  const sel = g_listviews.npcs.data.filter(ok);
  const out = window.__standin = window.__standin || [];
  const done = new Set(out.map(r => r.id));
  console.log(`stand-in scrape: ${sel.length} NPCs of ${g_listviews.npcs.data.length} in ${zone}`);
  for (const x of sel) {
    if (done.has(x.id)) continue;
    const t = await (await fetch('/forever/npc=' + x.id)).text();
    if (/confirm you are human/i.test(t)) { console.warn('human check: reload, pass it, run again'); break; }
    const mi = t.match(/g_mapperData = (\{.*?\});\n/);
    const tabs = [...new Set([...t.matchAll(/id: '([a-z-]+)'/g)].map(m => m[1]))]
      .filter(k => /^(sells|teaches|trains|starts|ends)$/.test(k));
    const map = mi ? JSON.parse(mi[1]) : null;
    const ui = map && (map[zoneId] || []).map(s => s.uiMapId).find(Boolean);
    out.push({id: x.id, name: x.name, tag: x.tag || '', react: x.react, hasQuests: !!x.hasQuests, tabs, map,
              zone, uiMap: ui || 0});
    console.log(`${out.length}/${sel.length} ${x.name}`);
    await new Promise(r => setTimeout(r, PAUSE_MS));
  }
  copy(JSON.stringify(out));
  console.log('copied ' + out.length + ' NPCs');
})();
"""
