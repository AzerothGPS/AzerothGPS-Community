"""Landmark (ALT) distance fields for the world grid's search (item 33, Kooki3z 2026-11-24: "yes, build the landmark
(ALT) distance tables"). WorldGrid.lua's search took the straight line as its heuristic, which a rim between badly
underestimates: the no-spell way round Tanaris' rim flooded tens of thousands of nodes (item 27). Each landmark's field
is every surface's least cost from it over the moves a search can make, undirected (WorldGrid.lua's WG.AltPrepare /
WG.AltFlood: links and road links both ways, far drops and slides reversed, falls past WG.ALT_FALL left out), reduced to
blocks of WG.ALT_BLOCK cells (least and most) and written as each region folder's Alt.lua (AzerothGPS_WorldGridAlt,
taken by WG.LoadRegion). The search's heuristic is then the most of |d(L, t) - d(L, s)| over the landmarks and the
straight line (WG.AltSearch).

Baked from the shipped region folders with the addon's own WorldGrid.lua in the game harness, so the fields are the
moves the search makes; rebaked after every grid bake (`agps world-grid alt --write`, after `agps world-grid --write`).
Landmarks: farthest-point, each the surface farthest (by cost) from those taken (the continent's ends and its rims'
far sides), from a seed in the continent's largest connected part."""

from __future__ import annotations

import re
import time
from pathlib import Path

LANDMARKS = 12
ALT_FILE = "Alt.lua"
# Landmarks first at these (Kooki3z: "the rims' ways down, ramps, passes"): basins and mesas a detour goes round, so
# their fields see the rims (farthest-point alone took the continents' far ends: the warrior's Tanaris rim -11% nodes,
# against -45% with Un'Goro's basin among them); the rest farthest-point.
SPOTS = {
    1: [(-7283.3, -450.0),    # Un'Goro's basin (Golakka Hot Springs)
        (-5483.3, -2416.7),   # Thousand Needles' mesas (Freewind Post)
        (-3083.3, -2850.0),   # Dustwallow Marsh (Brackenwall Village)
        (-1350.0, 1983.3),    # Desolace (Kodo Graveyard)
        (-6816.7, 783.3),     # Silithus (Cenarion Hold)
        (6783.3, -4683.3)],   # Winterspring (Everlook)
    0: [(-6516.7, -1116.7),   # Searing Gorge (Thorium Point)
        (-6650.0, -2216.7),   # the Badlands (Kargath)
        (-5383.3, -3016.7),   # Loch Modan (Thelsamar)
        (-3716.7, -783.3),    # the Wetlands (Menethil Harbor)
        (-50.0, -916.7),      # Hillsbrad and Alterac (Tarren Mill)
        (-10483.3, -3283.3)], # Swamp of Sorrows (Stonard)
}

_LUA = r"""
local WG = AGPS_NS.WorldGrid
local floor = math.floor
AGPS_ALT = {}
-- (every region of the continent loaded: the fields cover all of it)
function AGPS_ALT.LoadAll(c)
  for rk in pairs(c.d.regions or {}) do
    local rx, ry = rk:match("^(%d+):(%d+)$")
    WG.LoadRegion(c, tonumber(rx), tonumber(ry))
  end
end
-- (the flooded distances folded into `mind`, the least over the landmarks so far: the id with the most, reached)
function AGPS_ALT.Farthest(dist, mind)
  local best, bid = -1, nil
  for id, v in pairs(dist) do
    local m = mind[id]
    if not m or v < m then m = v mind[id] = v end
    if m > best then best, bid = m, id end
  end
  return bid, best
end
function AGPS_ALT.Count(t)
  local n = 0
  for _ in pairs(t) do n = n + 1 end
  return n
end
-- (a surface of the largest connected part: floods from surfaces not yet reached until one reaches half of them)
function AGPS_ALT.Seed(c, prep)
  local total = AGPS_ALT.Count(prep.cellOf)
  local seen = {}
  local bestId, bestN = nil, 0
  for id in pairs(prep.cellOf) do
    if not seen[id] then
      local d = WG.AltFlood(c, prep, { id }, {})
      local n = 0
      for k in pairs(d) do seen[k] = true n = n + 1 end
      if n > bestN then bestId, bestN = id, n end
      if n * 2 >= total then return id, n, total end
    end
  end
  return bestId, bestN, total
end
-- (one landmark's field, encoded per tile, appended to `acc` tile by tile)
function AGPS_ALT.Append(c, prep, dist, acc)
  local enc = WG.AltEncode(c, prep, { dist })
  for key, s in pairs(enc) do acc[key] = (acc[key] or "") .. s end
end
-- (the tiles' strings by region "rx:ry")
function AGPS_ALT.ByRegion(c, acc)
  local out = {}
  for key, s in pairs(acc) do
    local tx, ty = floor(key / 64), key % 64
    local rk = floor(tx / c.rb) .. ":" .. floor(ty / c.rb)
    out[rk] = out[rk] or {}
    out[rk][key] = s
  end
  return out
end
"""


def bake(cont: int, landmarks: int = LANDMARKS, log=print, lua_ns=None, far_set: bool = False) -> dict:
    """The continent's fields: {"bake": stamp, "n": landmarks, "regions": {"rx:ry": {key: str}}, "landmarks": [...]}."""
    if lua_ns is None:
        from .gameharness import start
        lua, ns = start()
    else:
        lua, ns = lua_ns
    st = ns.settings.gps
    st.worldGrid = True
    WG = ns.WorldGrid
    WG.Set(True)
    lua.execute(_LUA)
    A = lua.globals().AGPS_ALT
    c = WG.Cont(cont)
    if not c:
        raise SystemExit(f"no world grid for continent {cont}")
    WG.TILE_CACHE_MB = 1e9
    t0 = time.time()
    A.LoadAll(c)
    prep = WG.AltPrepare(c)
    log(f"  cont {cont}: prepared in {time.time() - t0:.0f} s")
    seed, n, total = A.Seed(c, prep)
    log(f"  seed {seed}: reaches {n} of {total} surfaces")
    mind = lua.table()
    acc = lua.table()
    seedField = WG.AltFlood(c, prep, lua.table(seed), lua.table())
    cur = seedField
    ids = []
    spots = []
    for x, y in SPOTS.get(cont, []):
        e = WG.Ends(c, x, y, None)
        sid = e[1].id if e[1] else None
        if sid is not None and seedField[sid] is not None:  # (on the continent's main part)
            spots.append(sid)
    for k in range(landmarks):
        if k < len(spots):
            lid, far = spots[k], 0.0
        else:
            lid, far = A.Farthest(cur, mind) if ids else A.Farthest(cur, lua.table())
        if lid is None:
            break
        t1 = time.time()
        cur = WG.AltFlood(c, prep, lua.table(lid), lua.table())
        A.Append(c, prep, cur, acc)
        key = int(lid) // 131072
        ids.append(int(lid))
        log(f"  landmark {k + 1}: id {lid} (tile {key // 64},{key % 64}), {far:.0f} from the rest, {time.time() - t1:.0f} s")
        A.Farthest(cur, mind)  # (the least over the landmarks so far)
    regions = {}
    by = A.ByRegion(c, acc)
    for rk, tiles in by.items():
        regions[str(rk)] = {int(k): str(v) for k, v in tiles.items()}
    # (the far set: the same landmarks over every fall, a fall spell's or an Expert jumper's: item 47)
    # (off by default: measured 2026-11-24 on three cross-zone trips with Expert jumper on, it saved nothing (45k ->
    # 51k nodes, the rest the same): over every fall, undirected, the bound is too loose to steer; 1.4 MB more)
    far = {}
    acc2 = lua.table()
    prep2 = WG.AltPrepare(c, 1e9) if far_set else None
    for lid in (ids if far_set else []):
        f2 = WG.AltFlood(c, prep2, lua.table(lid), lua.table())
        A.Append(c, prep2, f2, acc2)
    for rk, tiles in (A.ByRegion(c, acc2).items() if far_set else []):
        far[str(rk)] = {int(k): str(v) for k, v in tiles.items()}
    if far_set:
        log(f"  cont {cont}: the far set ({len(ids)} landmarks over every fall)")
    # (and the blocks' ways out, the long legs' corridors: item 38, WorldGrid.lua's WG.Corridor)
    e, xl = WG.AltExits(c, prep)
    exits, longer = {}, {}
    for rk, tiles in A.ByRegion(c, e).items():
        exits[str(rk)] = {int(k): str(v) for k, v in tiles.items()}
    for rk, tiles in A.ByRegion(c, xl).items():
        longer[str(rk)] = {int(k): str(v) for k, v in tiles.items()}
    log(f"  cont {cont}: block exits for {sum(len(v) for v in exits.values())} tiles")
    return {"bake": str(c.d.bake), "n": len(ids), "regions": regions, "landmarks": ids, "exits": exits,
            "longer": longer, "far": far}


def alt_text(cont: int, rk: str, bake_stamp: str, n: int, tiles: dict, exits: dict | None = None,
             longer: dict | None = None, far: dict | None = None) -> str:
    lines = ["-- GENERATED by `agps world-grid alt --write` (app/azerothgps/worldalt.py). Do not edit by hand.",
             "-- AzerothGPS's world grid: one region's landmark distance fields (the search's heuristic, WorldGrid.lua's",
             "-- WG.AltSearch), taken by WG.LoadRegion with the region's tiles.",
             "local all = AzerothGPS_WorldGridAlt or {}",
             "AzerothGPS_WorldGridAlt = all",
             f'all["{cont}:{rk}"] = {{ bake = "{bake_stamp}", n = {n}, t = {{']
    for k in sorted(tiles):
        lines.append(f'  [{k}] = "{tiles[k]}",')
    lines.append("},")
    lines.append("e = {")  # (the blocks' ways out, WG.Corridor)
    for k in sorted(exits or {}):
        lines.append(f'  [{k}] = "{exits[k]}",')
    lines.append("},")
    lines.append("x = {")
    for k in sorted(longer or {}):
        lines.append(f'  [{k}] = "{longer[k]}",')
    lines.append("},")
    if far:
        lines.append(f"n2 = {n}, t2 = {{")  # (the far set: every fall, WG.AltAllowed; `--far` only)
        for k in sorted(far):
            lines.append(f'  [{k}] = "{far[k]}",')
        lines.append("} }")
    else:
        lines[-1] = "} }"
    return "\n".join(lines) + "\n"


def add_to_toc(toc: Path) -> None:
    text = toc.read_text(encoding="utf-8")
    if re.search(r"^Alt\.lua\s*$", text, re.M):
        return
    if not text.endswith("\n"):
        text += "\n"
    toc.write_text(text + ALT_FILE + "\n", encoding="utf-8", newline="\n")


def write(cont: int, res: dict, root: Path, log=print) -> int:
    """Each region folder's Alt.lua (and its toc line); returns the bytes written."""
    total = 0
    for rk, tiles in sorted(res["regions"].items()):
        rx, ry = rk.split(":")
        folder = root / f"AzerothGPS_WG{cont}_{rx}_{ry}"
        if not folder.is_dir():
            log(f"  (no folder {folder.name}: skipped)")
            continue
        text = alt_text(cont, rk, res["bake"], res["n"], tiles, res.get("exits", {}).get(rk), res.get("longer", {}).get(rk),
                        res.get("far", {}).get(rk))
        (folder / ALT_FILE).write_text(text, encoding="utf-8", newline="\n")
        add_to_toc(folder / f"{folder.name}.toc")
        total += len(text)
    log(f"  cont {cont}: {len(res['regions'])} regions, {total / 1e6:.2f} MB of fields")
    return total
