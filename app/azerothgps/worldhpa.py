"""HPA* over the world grid (item 127, 1.4.2; the route-speed study's portal graph, item 108's design): each map tile a
cluster, its ways in and out (entrances: the moves from its surfaces onto another tile's, in runs along the border at
one height, each run cut into pieces of at most RUN_CELLS, one surface pair a piece), and between each way in and each
way out the least cost inside the tile by the grid search's own moves (WorldGrid.lua's WG.Search, a flood kept to the
tile, `x.home`), directed, at the default Safe drop (DROP), with the biggest drop on the way and the shares of the cost
on road ground and in water (so the game prices it by the trip's Road tolerance and swim weight). Written as one
load-on-demand folder, AzerothGPS_WGHPA (a file a continent, AzerothGPS_WorldGridHpa), loaded by WorldHPA.lua at the
first long leg (no region of the grid's loaded to plan): a long leg searched tile to tile over these, then refined
inside the tiles on the way.

Baked from the shipped region folders with the addon's own WorldGrid.lua in the game harness (as worldalt.py), so the
costs are the search's moves; rebaked after every grid bake (`agps world-grid hpa --write`).

Each tile's string (WorldGrid's 64-character alphabet, numbers big-endian):
  the tile's map data's length (4) and check sum (2: H.Check; the ways are for those surfaces only)
  nE (2) nX (2)
  nE ways in:  s (3: the surface's index in the tile) ci (2: its cell)
  nX ways out: s (3) ci (2) tkey (2: the tile it goes onto) ts (3) tci (2) cost (2: in COST_UNIT yd) fall (1: yd down)
  the costs from each way in to each way out, way in by way in (the ways sorted by their piece of the tile, so the
  ways with none between come in runs): cost (2) shares (1: road share * 8 + water share, each of 7) biggest drop on
  the way (1, yd); or "_" and a count less 1 (1): that many ways out with no way inside the tile."""

from __future__ import annotations

import time
from pathlib import Path

HPA_FILE = "Hpa.lua"
DROP = 39  # (the Safe drop's default, Nav.SafeDropSetting: the trips most players' searches make)
RUN_CELLS = 32  # (a way in or out's run cut into pieces this long at most: 267 yd)
COST_UNIT = 2  # (yards a cost's unit)
# (moves between two pieces no player reaches, worldbake's F_REACH: a rock's top, a roof, left out)
REACH_ONLY = True

_LUA = r"""
local WG = AGPS_NS.WorldGrid
local floor, abs, sqrt, min, max, huge = math.floor, math.abs, math.sqrt, math.min, math.max, math.huge
local SHIFT = WG.SHIFT
local ALPHA = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
local CH = {}
for i = 1, #ALPHA do CH[i - 1] = ALPHA:sub(i, i) end
local function E(v, w)
  local out = {}
  for i = w, 1, -1 do out[i] = CH[v % 64] v = floor(v / 64) end
  return table.concat(out)
end
AGPS_HPA = {}
local H = AGPS_HPA
function H.LoadAll(c)
  for rk in pairs(c.d.regions or {}) do
    local rx, ry = rk:match("^(%d+):(%d+)$")
    WG.LoadRegion(c, tonumber(rx), tonumber(ry))
  end
end
-- (the bake's costs: the grid's own with the default Road tolerance and swim weight, the Safe drop `drop`, nothing of a
-- player's: no guards, zones, walls, bans or own roads)
function H.Costs(c, drop)
  local x = WG.Costs(c, 0, 0, 1, 1, { maxDrop = drop, slopeDrop = drop, redFree = true })
  x.side, x.exempt, x.light, x.block, x.red, x.redExempt = nil, nil, nil, nil, nil, nil
  x.any, x.walls, x.bans, x.jumpBanned, x.lineWalls = false, false, false, nil, false
  x.erased, x.own, x.roadCells, x.unroadCells = nil, nil, nil, nil
  x.heur, x.noAlt, x.noLimit, x.flood = 0, true, true, true
  return x
end
local function Gxy(c, t, ci) return t.gx0 + floor(ci / c.per), t.gy0 + ci % c.per end
-- (one tile's moves onto other tiles: a flood from all its surfaces at no cost, kept to the tile)
function H.Discover(c, key, x, out)
  local t = WG.Tile(c, key)
  if not t then return 0 end
  local per = c.per
  local starts = {}
  for ci = 0, per * per - 1 do
    local n = WG.Count(t, ci)
    if n > 0 then
      local f0 = WG.First(t, ci)
      for q = 0, n - 1 do starts[#starts + 1] = { id = key * SHIFT + f0 + q, ci = ci, cost = 0 } end
    end
  end
  if not starts[1] then return 0 end
  x.home, x.res = { [key] = true }, nil
  WG.Search(c, starts, {}, 0, 0, nil, x)
  local res = x.res
  local n = 0
  for id2, g in pairs(res.g) do
    local k2 = floor(id2 / SHIFT)
    if k2 ~= key then
      local s = res.prev[id2]
      local t2 = WG.Tile(c, k2)
      local sci, tci = res.cellOf[s], res.cellOf[id2]
      local zs, zt = WG.Z(c, t, s - key * SHIFT), WG.Z(c, t2, id2 - k2 * SHIFT)
      local sgx, sgy = Gxy(c, t, sci)
      local tgx, tgy = Gxy(c, t2, tci)
      local kind = 0
      local via = res.via[id2]
      if via then kind = 3
      elseif max(abs(sgx - tgx), abs(sgy - tgy)) > 1 then kind = 2
      elseif res.dropAt[id2] then kind = 1 end
      local fall = (res.dropAt[id2] or (via and c.links[via] and c.links[via].kind == 4)) and max(0, zs - zt) or 0
      local fs, ft = WG.Flags(t, s - key * SHIFT), WG.Flags(t2, id2 - k2 * SHIFT)
      local reach = floor(fs / 4) % 2 == 1 or floor(ft / 4) % 2 == 1
      H.nonReach = (H.nonReach or 0) + (reach and 0 or 1)
      if reach or not H.reachOnly then out[#out + 1] = { s = s, t = id2, skey = key, tkey = k2, sci = sci, tci = tci, cost = g, zs = zs, zt = zt,
        sgx = sgx, sgy = sgy, tgx = tgx, tgy = tgy, kind = kind, fall = fall } end
      n = n + 1
    end
  end
  x.res = nil
  return n
end
-- (the crossings in runs: one way out of a tile onto one other tile, cell next to cell, their surfaces on either side
-- linked to each other (walked between), the same kind (a far drop's apart); road links alone; each run cut into
-- pieces of at most `R`, its middle crossing the way)
local DX = { 1, 0, -1, 0, 1, -1, -1, 1 }
local DY = { 0, 1, 0, -1, 1, 1, -1, -1 }
local function Linked(c, a, aci, b, bci)
  local ka, kb = floor(a / SHIFT), floor(b / SHIFT)
  if ka ~= kb then return false end
  local t = WG.Tile(c, ka)
  local per = c.per
  local dx, dy = floor(bci / per) - floor(aci / per), bci % per - aci % per
  local sa, sb = a - ka * SHIFT, b - ka * SHIFT
  for d = 1, 8 do
    if DX[d] == dx and DY[d] == dy then
      if WG.Link(t, sa, d) == sb - WG.First(t, bci) + 1 then return true end
      local e = d <= 4 and ((d + 1) % 4 + 1) or ({ 7, 8, 5, 6 })[d - 4]
      if WG.Link(t, sb, e) == sa - WG.First(t, aci) + 1 then return true end
      return false
    end
  end
  return false
end
H.Linked = Linked
-- (each surface's piece of its tile: the surfaces joined by links inside the tile, either way; H.comp[id])
H.comp = {}
function H.Pieces(c, key)
  local t = WG.Tile(c, key)
  if not t then return end
  local per = c.per
  local parent = {}
  local function Find(i)
    while parent[i] ~= i do parent[i] = parent[parent[i]] i = parent[i] end
    return i
  end
  for ci = 0, per * per - 1 do
    local n = WG.Count(t, ci)
    local f0 = n > 0 and WG.First(t, ci)
    for q = 0, n - 1 do parent[f0 + q] = f0 + q end
  end
  for ci = 0, per * per - 1 do
    local n = WG.Count(t, ci)
    if n > 0 then
      local f0 = WG.First(t, ci)
      local a, b = floor(ci / per), ci % per
      for q = 0, n - 1 do
        local s = f0 + q
        for d = 1, 8 do
          local kk = WG.Link(t, s, d)
          local na, nb = a + DX[d], b + DY[d]
          if kk > 0 and na >= 0 and na < per and nb >= 0 and nb < per then
            local s2 = WG.First(t, na * per + nb) + kk - 1
            local r1, r2 = Find(s), Find(s2)
            if r1 ~= r2 then parent[r1] = r2 end
          end
        end
      end
    end
  end
  for s in pairs(parent) do H.comp[key * SHIFT + s] = key * SHIFT + Find(s) end
end
H.GAP, H.GAP_Z, H.GAP_SLOPE = 3, 4, 3
function H.Group(c, cross, R)
  local parent = {}
  local function Find(i)
    while parent[i] ~= i do parent[i] = parent[parent[i]] i = parent[i] end
    return i
  end
  local comp = H.comp
  local idx = {}
  local function K(cr, gx, gy) return (cr.skey * 4096 + cr.tkey) .. ":" .. (cr.kind == 2 and 2 or 0) .. ":" .. (gx * 65536 + gy) end
  for i, cr in ipairs(cross) do
    parent[i] = i
    if cr.kind ~= 3 then
      local k = K(cr, cr.sgx, cr.sgy)
      local l = idx[k]
      if not l then l = {} idx[k] = l end
      l[#l + 1] = i
    end
  end
  local G = H.GAP
  for i, cr in ipairs(cross) do
    if cr.kind ~= 3 then
      for di = -G, G do
        for dj = -G, G do
          for _, j in ipairs(idx[K(cr, cr.sgx + di, cr.sgy + dj)] or {}) do
            local o = cross[j]
            local cheb = max(abs(di), abs(dj))
            if j > i and Find(i) ~= Find(j) and comp[o.s] == comp[cr.s] and comp[o.t] == comp[cr.t]
                and abs(o.zs - cr.zs) <= H.GAP_Z + H.GAP_SLOPE * cheb and abs(o.zt - cr.zt) <= H.GAP_Z + H.GAP_SLOPE * cheb then
              parent[Find(i)] = Find(j)
            end
          end
        end
      end
    end
  end
  local groups = {}
  for i in ipairs(cross) do
    local r = Find(i)
    groups[r] = groups[r] or {}
    table.insert(groups[r], cross[i])
  end
  local reps = {}
  H.sizes = {}
  for _, g in pairs(groups) do
    local x0, x1, y0, y1 = huge, -huge, huge, -huge
    for _, cr in ipairs(g) do
      x0, x1, y0, y1 = min(x0, cr.sgx), max(x1, cr.sgx), min(y0, cr.sgy), max(y1, cr.sgy)
    end
    local byX = x1 - x0 >= y1 - y0
    table.sort(g, function(a, b)
      local ka, kb = byX and a.sgx or a.sgy, byX and b.sgx or b.sgy
      if ka ~= kb then return ka < kb end
      if a.zs ~= b.zs then return a.zs < b.zs end
      return a.s < b.s
    end)
    local span = (byX and x1 - x0 or y1 - y0) + 1
    local pieces = math.max(1, math.ceil(span / R))
    H.sizes[#H.sizes + 1] = #g
    for p = 0, pieces - 1 do
      local i0, i1 = floor(p * #g / pieces) + 1, floor((p + 1) * #g / pieces)
      if i1 >= i0 then reps[#reps + 1] = g[floor((i0 + i1) / 2)] end
    end
  end
  return reps
end
function H.Kinds(cross)
  local n = { [0] = 0, 0, 0, 0 }
  for _, cr in ipairs(cross) do n[cr.kind] = n[cr.kind] + 1 end
  return n[0] .. " steps, " .. n[1] .. " drops, " .. n[2] .. " far drops, " .. n[3] .. " links"
end
-- (the path's biggest drop and its yards on road ground and in water, walked back from `id`)
local function PathStats(c, res, id)
  local md, road, swim = 0, 0, 0
  local cur = id
  while res.prev[cur] do
    local p = res.prev[cur]
    local kq, kp = floor(cur / SHIFT), floor(p / SHIFT)
    local tq, tp = WG.Tile(c, kq), WG.Tile(c, kp)
    local sq, sp = cur - kq * SHIFT, p - kp * SHIFT
    local zq, zp = WG.Z(c, tq, sq), WG.Z(c, tp, sp)
    local via = res.via[cur]
    if res.dropAt[cur] then md = max(md, zp - zq) end
    if via then
      local L = c.links[via]
      if L then
        if L.kind == 4 then md = max(md, zp - zq) else road = road + (L.yd or 0) end
      end
    else
      local qx, qy = WG.Pt(c, tq, sq, res.cellOf[cur])
      local px, py = WG.Pt(c, tp, sp, res.cellOf[p])
      local d = sqrt((qx - px) ^ 2 + (qy - py) ^ 2)
      local fq, fp = WG.Flags(tq, sq), WG.Flags(tp, sp)
      if fq % 2 == 1 or fp % 2 == 1 then swim = swim + d
      elseif floor(fq / 2) % 2 == 1 and floor(fp / 2) % 2 == 1 then road = road + d end
    end
    cur = p
  end
  return md, road, swim
end
-- (a tile's map data's length and check sum: the ways are for these surfaces only, WorldHPA.lua's TileData)
function H.Check(raw)
  local n, sum = #raw, 0
  local step = math.max(1, floor(n / 64))
  for i = 1, n, step do sum = (sum * 31 + raw:byte(i)) % 4096 end
  return n, sum
end
-- (a tile's string: its ways in and out, and the costs between, each way in's flood kept to the tile)
function H.Intra(c, key, ins, outs, x, unit, none)
  local t = WG.Tile(c, key)
  local rn, rs = H.Check(c.raw[key])
  local parts = { E(rn, 4), E(rs, 2), E(#ins, 2), E(#outs, 2) }
  for _, e in ipairs(ins) do parts[#parts + 1] = E(e.t - key * SHIFT, 3) .. E(e.tci, 2) end
  for _, o in ipairs(outs) do
    parts[#parts + 1] = E(o.s - key * SHIFT, 3) .. E(o.sci, 2) .. E(o.tkey, 2) .. E(o.t - o.tkey * SHIFT, 3) .. E(o.tci, 2)
      .. E(min(none - 1, math.ceil(o.cost / unit)), 2) .. E(min(63, floor(o.fall + 0.5)), 1)
  end
  local nodes = 0
  local road, swim = x.road, x.swim
  local run = 0 -- (ways with none between, in a row: "_" and their count)
  local function Flush()
    while run > 0 do
      local n = min(64, run)
      parts[#parts + 1] = "_" .. CH[n - 1]
      run = run - n
    end
  end
  for _, e in ipairs(ins) do
    x.home, x.res = { [key] = true }, nil
    WG.Search(c, { { id = e.t, ci = e.tci, cost = 0 } }, {}, 0, 0, nil, x)
    local res = x.res
    nodes = nodes + res.nodes
    for _, o in ipairs(outs) do
      local g = res.g[o.s]
      if not g then
        run = run + 1
      else
        Flush()
        local md, ry, sy = PathStats(c, res, o.s)
        local rs = g > 0 and min(7, floor(7 * ry * road / g + 0.5)) or 0
        local ss = g > 0 and min(7, floor(7 * sy * swim / g + 0.5)) or 0
        parts[#parts + 1] = E(min(none - 1, math.ceil(g / unit)), 2) .. CH[rs * 8 + ss] .. CH[min(62, math.ceil(md))]
      end
    end
    x.res = nil
  end
  Flush()
  return table.concat(parts), nodes
end
"""


def bake(cont: int, log=print, lua_ns=None, tiles_only=None, reach_only: bool = REACH_ONLY) -> dict:
    """The continent's HPA graph: {"bake", "road", "swim", "drop", "regions": {"rx:ry": {key: str}}, stats}."""
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
    H = lua.globals().AGPS_HPA
    H.reachOnly = reach_only
    c = WG.Cont(cont)
    if not c:
        raise SystemExit(f"no world grid for continent {cont}")
    WG.TILE_CACHE_MB = 1e9
    t0 = time.time()
    H.LoadAll(c)
    x = H.Costs(c, DROP)
    keys = sorted(int(k) for k in c.raw.keys())
    if tiles_only:
        keys = [k for k in keys if k in tiles_only]
    log(f"  cont {cont}: {len(keys)} tiles loaded in {time.time() - t0:.0f} s; road {x.road:.3f}, swim {x.swim:.2f}")
    cross = lua.table()
    t1 = time.time()
    for k in keys:
        H.Pieces(c, k)
    for k in keys:
        H.Discover(c, k, x, cross)
    log(f"  cont {cont}: {len(cross)} crossings in {time.time() - t1:.0f} s ({H.nonReach} between pieces no player reaches)")
    log(f"  kinds: {H.Kinds(cross)}")
    reps = H.Group(c, cross, RUN_CELLS)
    sz = sorted(int(v) for v in H.sizes.values())
    log(f"  groups {len(sz)}: sizes median {sz[len(sz)//2] if sz else 0}, singletons {sum(1 for v in sz if v == 1)}")
    ins, outs = {}, {}
    for i in range(1, len(reps) + 1):
        r = reps[i]
        outs.setdefault(int(r.skey), {}).setdefault(int(r.s), []).append(r)
        ins.setdefault(int(r.tkey), {})[int(r.t)] = r
    log(f"  cont {cont}: {len(reps)} ways between tiles")
    out, nodes, n_in, n_out = {}, 0, 0, 0
    t2 = time.time()
    none = 63 * 64  # (costs' first character under 63: "_" is no way)
    for k in keys:
        il = lua.table()
        comp = H.comp
        for i, r in enumerate(sorted(ins.get(k, {}).values(), key=lambda r: (int(comp[r.t] or 0), int(r.t)))):
            il[i + 1] = r
        ol = lua.table()
        j = 0
        for s in sorted(outs.get(k, {}), key=lambda s: (int(comp[s] or 0), s)):
            for r in sorted(outs[k][s], key=lambda r: (int(r.tkey), int(r.t))):
                j += 1
                ol[j] = r
        s, nn = H.Intra(c, k, il, ol, x, COST_UNIT, none)  # (a tile with no ways too: "0000", known to have none)
        nodes += int(nn)
        n_in, n_out = n_in + len(il), n_out + len(ol)
        out[k] = str(s)
    log(f"  cont {cont}: {n_in} ways in, {n_out} ways out, {nodes} nodes flooded in {time.time() - t2:.0f} s")
    regions = {}
    for k, s in out.items():
        tx, ty = k // 64, k % 64
        rk = f"{tx // int(c.rb)}:{ty // int(c.rb)}"
        regions.setdefault(rk, {})[k] = s
    return {"bake": str(c.d.bake), "road": float(x.road), "swim": float(x.swim), "drop": DROP, "unit": COST_UNIT,
            "regions": regions, "crossings": len(cross), "ways": len(reps), "ins": n_in, "outs": n_out, "nodes": nodes,
            "secs": round(time.time() - t0)}


def check(raw: str) -> tuple[int, int]:
    """A tile's map data's length and check sum, as the bake's H.Check (WorldHPA.lua's TileData)."""
    n, total = len(raw), 0
    step = max(1, n // 64)
    for i in range(0, n, step):
        total = (total * 31 + ord(raw[i])) % 4096
    return n, total


FOLDER = "AzerothGPS_WGHPA"  # (one load-on-demand folder for every continent: HPA*'s search reads no region to plan)


def hpa_text(cont: int, res: dict, tiles: dict) -> str:
    lines = ["-- GENERATED by `agps world-grid hpa --write` (app/azerothgps/worldhpa.py). Do not edit by hand.",
             "-- AzerothGPS's world grid: one continent's map tiles' ways in and out and the costs between them (HPA*,",
             "-- WorldHPA.lua's HP.Load).",
             "local all = AzerothGPS_WorldGridHpa or {}",
             "AzerothGPS_WorldGridHpa = all",
             f'all[{cont}] = {{ bake = "{res["bake"]}", road = {res["road"]:.4f}, swim = {res["swim"]:.4f}, '
             f'drop = {res["drop"]}, unit = {res["unit"]}, t = {{']
    for k in sorted(tiles):
        lines.append(f'  [{k}] = "{tiles[k]}",')
    lines.append("} }")
    return "\n".join(lines) + "\n"


def folder_toc(root: Path) -> str:
    from . import worldbake
    files = sorted(p.name for p in (root / FOLDER).glob("Hpa*.lua"))
    return "\n".join([f"## Interface: {worldbake.toc_interface()}",
                      f"## Title: |cff{worldbake.TITLE_COLOR}AzerothGPS map data: ways between map tiles|r",
                      f"## Notes: {worldbake.REGION_NOTES}",
                      "## Author: AzerothGPS",
                      "## Group: AzerothGPS",
                      f"## IconTexture: {worldbake.REGION_ICON}",
                      "## LoadOnDemand: 1",
                      "## Dependencies: AzerothGPS",
                      ""] + files + [""])


def write(cont: int, res: dict, root: Path, log=print) -> int:
    """The continent's Hpa<cont>.lua in the folder FOLDER (and its toc); returns the bytes written."""
    tiles = {}
    for t in res["regions"].values():
        tiles.update(t)
    d = root / FOLDER
    d.mkdir(parents=True, exist_ok=True)
    text = hpa_text(cont, res, tiles)
    (d / f"Hpa{cont}.lua").write_text(text, encoding="utf-8", newline="\n")
    (d / f"{FOLDER}.toc").write_text(folder_toc(root), encoding="utf-8", newline="\n")
    log(f"  cont {cont}: {len(tiles)} tiles, {len(text) / 1e6:.2f} MB of ways")
    return len(text)
