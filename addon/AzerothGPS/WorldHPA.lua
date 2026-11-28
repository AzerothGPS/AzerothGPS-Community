-- HPA* over the world grid (item 127, 1.4.2; Kooki3z's checklist d-hpa: "build HPA*", replacing #922). A long leg's
-- grid search flooded up to 290k nodes (the route-speed study, 2026-11-25: Camp Taurajo to Un'Goro, Darkshore to
-- Felwood), and a stop it couldn't reach flooded its whole budget before saying so (Woodpaw Den, test_cave_sweep). Now:
--
-- - The bake (app/azerothgps/worldhpa.py; the load-on-demand folder AzerothGPS_WGHPA, a file a continent, loaded at the
--   first long leg by HP.Load, so planning loads none of the grid's regions; c.hpa): each map
--   tile a cluster; its ways in and out (the moves from its surfaces onto another tile's, in runs at one height, one
--   surface pair a run's piece), and from each way in to each way out of the tile the least cost inside it by the grid
--   search's own moves, at the default Safe drop (`head.drop`), with the biggest drop on the way and the shares of the
--   cost on road ground and in water.
-- - In game (HP.Search, asked by WG.Walk before its own search): the start's tile flooded (the grid's search kept to
--   it), then A* from tile to tile over the ways, each priced by the trip's costs (Road tolerance, the swim weight, the
--   guards and zones too high at its ends, the drop limit); the stop's tile entered by the way whose walk on to the stop
--   (searched then, kept to the stop's tile) is cheapest. Then the way refined tile by tile: the grid's search inside
--   each tile on the way to the next way out (any surface of its run), and the steps put together as one search's.
-- - No way between the tiles at the bake's own drop limit: no way at once (Kooki3z, item 127: "No way there" from the
--   clusters' connectivity). Anything it can't tell (another drop limit, the player's own roads and erasers, a region
--   from another bake, a refine that fails more than REPLANS times): nil, and the grid's own search as before.
-- Ideas from Polestar's (map tiles as clusters, ways on tile borders, grid A* inside); our own code (Polestar is GPL-3).
local _, ns = ...
local WG = ns.WorldGrid
local HP = {}
ns.WorldHPA = HP

local floor, sqrt, abs, min, max, huge = math.floor, math.sqrt, math.abs, math.min, math.max, math.huge
local byte = string.byte

HP.MIN_YD = 800 -- (a leg shorter than this: tile to tile only after the grid's own search ran out, below)
-- A long leg (WorldGrid.LONG_LEG_YD) is searched tile to tile first; a shorter one by the grid's own search first, within
-- SHORT_FIRST nodes (most are found so, as 1.4.1 found them: the road down Red Cloud Mesa's west end, not a drop the
-- tiles' refine took), and tile to tile when that runs out (Darkshore to Felwood's 8.5k yd way round a ridge, 985 yd
-- straight; a cave's mouth on a ledge no way reaches: no way at once, not 400k nodes)
HP.SHORT_FIRST = 60000 -- (the landmark trips', test_world_grid_alt: Tanaris' warrior 41k, the Barrens 25k; as 1.4.1)
HP.LONG_FIRST = 20000 -- (a long leg's weighed search first, within this: Taurajo to Un'Goro 90k, then 33k tile to tile)
HP.MAX_POPS = 40000 -- ways an abstract search settles at most (then the grid's own search)
HP.GOAL_TRIES = 6 -- ways into the stop's tile whose walk on to the stop is searched, at most (each up to a tile's nodes)
HP.VERIFY_NODES = 15000 -- (... and more while those walks took fewer nodes than this: a cave's stop, its tile's rim ways each a pocket)
HP.REPLANS = 6 -- a tile's refine with no way: the way left out and the tiles searched again, so many times
HP.WINDOW = 3 -- (tiles a refine goes through at a time, the ways between them free: at 1, Darkshore to Felwood came out 6% over
-- the grid's own best way, at 3 2% under it, 33k nodes)
HP.HOME_RING = 0 -- (tiles round a window's tiles its refine may go through too: at 1, Un'Goro 120k nodes, not 40k)
HP.RUN_CELLS = 16 -- (cells either side of a way's surface its run's other surfaces are looked for at, the bake's 32 / 2)
HP.RUN_Z, HP.RUN_SLOPE = 4, 3 -- (and their heights within this, and this a cell more: worldhpa.GAP_Z, GAP_SLOPE)
HP.stats = { searches = 0, found = 0, noWay = 0, gaveUp = 0, pops = 0, nodes = 0, replans = 0, tries = 0 }

local ALPHA = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
local DEC = {}
for i = 1, #ALPHA do DEC[byte(ALPHA, i)] = i - 1 end
local NONE = byte("_")
local function Num(str, p, w)
  local v = 0
  for i = p, p + w - 1 do v = v * 64 + DEC[byte(str, i)] end
  return v
end
local function Dist(x1, y1, x2, y2) return sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2) end

-- The continent's ways (the folder AzerothGPS_WGHPA, once a session; the grid's own bake only): c.hpa, c.hpaHead.
HP.FOLDER = "AzerothGPS_WGHPA"
HP.store = {} -- [cont] = the folder's data (kept for the session: a grid made again takes it from here), or false
function HP.Load(c)
  if c.hpaTried then return c.hpaHead ~= nil end
  c.hpaTried = true
  local all = rawget(_G, "AzerothGPS_WorldGridHpa")
  if HP.store[c.cont] == nil and not (type(all) == "table" and all[c.cont]) and not HP.loaded then
    HP.loaded = true -- (once a session: missing or turned off, the grid's own searches, as before)
    local load = (C_AddOns and C_AddOns.LoadAddOn) or LoadAddOn
    if load then pcall(load, HP.FOLDER) end
    all = rawget(_G, "AzerothGPS_WorldGridHpa")
  end
  if HP.store[c.cont] == nil then
    HP.store[c.cont] = type(all) == "table" and all[c.cont] or false
    if type(all) == "table" then all[c.cont] = nil end
  end
  local e = HP.store[c.cont]
  if type(e) == "table" and e.bake == c.d.bake and type(e.t) == "table" then
    c.hpa = e.t
    c.hpaHead = { road = e.road, swim = e.swim, drop = e.drop, unit = e.unit or 2 }
  end
  return c.hpaHead ~= nil
end

-- A tile's ways: { E (ways in: surface ids), Eci, X (ways out: { s, ci, tkey,
-- t, tci, cost, fall }), Mc/Mr/Ms/Md (way in i to way out j: cost, road and water shares /7, the biggest drop; nil:
-- none), inAt [id] = i, outAt [id] = { j, ... } }, or false (no data: a tile with no ways, or another bake's).
function HP.TileData(c, key)
  c.hpaP = c.hpaP or {}
  local got = c.hpaP[key]
  if got ~= nil then return got end
  local str = c.hpa and c.hpa[key]
  if not str then
    c.hpaP[key] = false
    return false
  end
  -- (made for this tile's map data: else, a region baked again since, none. Its region not loaded yet: looked at once
  -- it is, HP.Fresh)
  if not HP.Fresh(c, key, str) then
    c.hpaP[key] = false
    return false
  end
  local unit = c.hpaHead and c.hpaHead.unit or 2
  local SHIFT = WG.SHIFT
  local base = key * SHIFT
  local nE, nX = Num(str, 7, 2), Num(str, 9, 2)
  local p = 11
  local d = { key = key, E = {}, Eci = {}, X = {}, Mc = {}, Mr = {}, Ms = {}, Md = {}, inAt = {}, outAt = {} }
  for i = 1, nE do
    d.E[i], d.Eci[i] = base + Num(str, p, 3), Num(str, p + 3, 2)
    d.inAt[d.E[i]] = i
    p = p + 5
  end
  for j = 1, nX do
    local tkey = Num(str, p + 5, 2)
    local o = { s = base + Num(str, p, 3), ci = Num(str, p + 3, 2), tkey = tkey, t = tkey * SHIFT + Num(str, p + 7, 3),
      tci = Num(str, p + 10, 2), cost = Num(str, p + 12, 2) * unit, fall = DEC[byte(str, p + 14)] }
    d.X[j] = o
    local l = d.outAt[o.s]
    if not l then l = {} d.outAt[o.s] = l end
    l[#l + 1] = j
    p = p + 15
  end
  for i = 1, nE do d.Mc[i], d.Mr[i], d.Ms[i], d.Md[i] = {}, {}, {}, {} end
  -- (one sequence of nE * nX, way in by way in: a run of none may go on into the next way in's)
  local k, total = 0, nE * nX
  local Rt = ns.Router
  local looked = 0
  while k < total do
    looked = looked + 1
    if Rt and Rt.Breathe and looked % 200 == 0 then Rt.Breathe(looked, 200) end
    if byte(str, p) == NONE then
      k = k + DEC[byte(str, p + 1)] + 1
      p = p + 2
    else
      local i, j = floor(k / nX) + 1, k % nX + 1
      local sh = DEC[byte(str, p + 2)]
      d.Mc[i][j], d.Mr[i][j], d.Ms[i][j], d.Md[i][j] = Num(str, p, 2) * unit, floor(sh / 8), sh % 8, DEC[byte(str, p + 3)]
      p = p + 4
      k = k + 1
    end
  end
  c.hpaP[key] = d
  return d
end

-- Whether a tile's ways are for its map data as shipped (its length and check sum), or its region isn't loaded yet
-- (nil raw: told when it is, and the refine checks again: Search's Stale).
function HP.Fresh(c, key, str)
  local raw = c.raw[key]
  if not raw then return true end
  str = str or (c.hpa and c.hpa[key])
  if not str then return false end
  if Num(str, 1, 4) ~= #raw or Num(str, 5, 2) ~= HP.Check(raw) then
    HP.stats.stale = (HP.stats.stale or 0) + 1
    return false
  end
  return true
end
-- A tile's map data's length and check sum (worldhpa.py's H.Check).
function HP.Check(raw)
  local n, sum = #raw, 0
  local step = max(1, floor(n / 64))
  for i = 1, n, step do sum = (sum * 31 + byte(raw, i)) % 4096 end
  return sum
end

-- A surface's cell's middle (its tile key, cell): a way's point, near enough for the estimates.
local function CellPt(c, key, ci)
  local gx0, gy0 = WG.Origin(c, key)
  return (gx0 + floor(ci / c.per) + 0.5) * c.cell, (gy0 + ci % c.per + 0.5) * c.cell
end
HP.CellPt = CellPt

-- Whether a leg may be searched tile to tile: the data, its length, nothing the bake doesn't know of.
function HP.Usable(c, sx, sy, tx, ty, x, anyLength)
  if WG.hpaOff or not c or not x then return false end
  if (not anyLength and Dist(sx, sy, tx, ty) < HP.MIN_YD) or not HP.Load(c) then return false end
  if x.home or x.flood then return false end
  if x.erased or x.own or x.roadCells or x.unroadCells then return false end
  -- (only at the bake's own drop limit: a bigger one (a fall spell, Expert jumper, a ghost, Safe drop over it) has
  -- drops the tiles' ways leave out, a smaller one may need ways round their drops; the grid's own search then)
  local drop = c.hpaHead.drop
  if (x.maxDrop or 0) ~= drop or (x.slopeDrop or x.maxDrop or 0) ~= drop then return false end
  -- (the straight line past guards or an elite area: the grid's own search, as 1.4.1; ChainNearGuards for the rest)
  if x.side and WG.GuardsOnLine(x, sx, sy, tx, ty) then return false end
  return true
end

-- (the guards' and zones' extra a yard at a spot, WorldGrid's Extra: cached by a spot's 25 yd square)
local function SpotExtra(x, px, py)
  if not x.any then return 0 end
  local id = -(4e12 + floor(px / 25 + 2000) * 1e6 + floor(py / 25 + 2000))
  return WG.Extra(x, id, px, py)
end
-- (and along a way's line, every LINE_STEP yards: the most of them, so a town the line passes isn't missed)
HP.LINE_STEP = 30
local function LineExtra(x, ax, ay, bx, by)
  if not x.any then return 0 end
  local n = max(1, math.ceil(Dist(ax, ay, bx, by) / HP.LINE_STEP))
  local sum = 0
  for i = 0, n do
    local f = i / n
    sum = sum + SpotExtra(x, ax + (bx - ax) * f, ay + (by - ay) * f)
  end
  return sum / (n + 1)
end

-- Whether a spot is within GUARD_NEAR_YD of the reach of guards or an elite area the costs `x` weigh (not the zones
-- too high): the spot and four round it.
HP.GUARD_NEAR_YD = 40
local RING = { { 0, 0 }, { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } }
function HP.NearGuards(c, x, px, py)
  local Rt = ns.Router
  if not (Rt and Rt.HostileAt and x.side) then return false end
  local r = HP.GUARD_NEAR_YD
  for _, o in ipairs(RING) do
    local qx, qy = px + o[1] * r, py + o[2] * r
    if Rt.HostileAt(c.cont, qx, qy, x.side, x.exempt) then return true end
    if x.light and not (Rt.NearLightEnd and Rt.NearLightEnd(qx, qy)) and Rt.HostileAt(c.cont, qx, qy, x.light) then
      return true
    end
  end
  return false
end
-- Whether a way's steps go near guards or an elite area (NearGuards, every other step).
function HP.PastGuards(c, x, steps)
  if not x.side then return false end
  local SHIFT = WG.SHIFT
  for i = 1, #steps, 2 do
    local st = steps[i]
    local t = WG.Tile(c, st.key)
    if t then
      local px, py = WG.Pt(c, t, st.id - st.key * SHIFT, st.ci)
      if HP.NearGuards(c, x, px, py) then return true end
    end
  end
  return false
end
-- Whether the tiles' way (its ways' points, the lines between) goes near guards or an elite area.
function HP.ChainNearGuards(c, x, chain, sx, sy, tx, ty)
  if not x.side then return false end
  local SHIFT = WG.SHIFT
  local px, py = sx, sy
  local function Line(ax, ay, bx, by)
    local n = max(1, math.ceil(Dist(ax, ay, bx, by) / HP.LINE_STEP))
    for i = 0, n do
      if HP.NearGuards(c, x, ax + (bx - ax) * i / n, ay + (by - ay) * i / n) then return true end
    end
    return false
  end
  for m = 1, #chain do
    local nk = chain[m]
    local id = nk % 2 == 0 and nk / 2 or (nk - 1) / 2
    local key = floor(id / SHIFT)
    local d = HP.TileData(c, key)
    local ci = d and (nk % 2 == 0 and d.inAt[id] and d.Eci[d.inAt[id]] or (d.outAt[id] and d.X[d.outAt[id][1]].ci))
    if ci then
      local qx, qy = CellPt(c, key, ci)
      if Line(px, py, qx, qy) then return true end
      px, py = qx, qy
    end
  end
  return Line(px, py, tx, ty)
end

-- The grid's way from `starts` to `goals` tile to tile (see the top): steps as WG.Search's, false (no way, for sure),
-- or nil (not worked out: the grid's own search).
-- `pre` (WorldGrid's Walk, before its own search): only the cheap looks: the tiles' data, a start in a pocket of its
-- tile (a flood of PREFLIGHT_NODES at most: no way out of the tile from it). "ok" when HPA* may be worth its nodes here,
-- else nil (the hpa-bench, 2026-11-27: Fargodeep Mine's legs gave up after a 10-node flood, each after the grid's own
-- search's first try, which then ran again whole).
HP.PREFLIGHT_NODES = 400
HP.gaveUp = {} -- [the stop's tiles and costs] = true (WG.Reset clears it)
function HP.Search(c, starts, goals, tx, ty, x, pre)
  local Rt = ns.Router
  local SHIFT = WG.SHIFT
  local head = c.hpaHead
  HP.stats.searches = HP.stats.searches + 1
  if not starts[1] then return nil end
  local startTiles, goalTiles = {}, {}
  for _, st in ipairs(starts) do startTiles[floor(st.id / SHIFT)] = true end
  local anyGoal = false
  for id in pairs(goals) do
    local k = floor(id / SHIFT)
    if startTiles[k] then return nil end -- (a stop in the start's own tile: the grid's search)
    goalTiles[k] = true
    anyGoal = true
  end
  if not anyGoal then return nil end
  -- (a stop the tiles' search gave up on, with these costs: not again this session, nor its preflight's nodes. The
  -- hpa-bench's Fargodeep Mine trip gave up ten times, each after the grid's own search's first try)
  local gk = {}
  for k in pairs(goalTiles) do gk[#gk + 1] = k end
  table.sort(gk)
  local goalSig = table.concat(gk, ",") .. "|" .. tostring(x.maxDrop) -- (round the guards or through: the same stop)
  if HP.gaveUp[goalSig] then return nil end
  for k in pairs(startTiles) do
    if not HP.TileData(c, k) then return nil end
  end
  local lim = min(x.maxDrop or 0, x.slopeDrop or x.maxDrop or 0)
  -- (no way, for sure, only at the bake's own drop limit: with a bigger one there are drops it left out)
  local exact = (x.maxDrop == head.drop) and ((x.slopeDrop or x.maxDrop) == head.drop)
  local kRoad = (x.road or head.road) / head.road
  local kSwim = (x.swim or head.swim) / head.swim
  local kmin = min(x.road or 1, 1) -- (a yard's least cost: the heuristic's)
  local nodes = 0
  local fres -- (the start's tile's flood, below)
  local parts = { flood = 0, seg = 0, verify = 0, segs = 0 } -- (where the nodes went: HP.lastParts, the tests)
  HP.lastParts = parts
  -- (the refine's costs: the leg's, kept to a tile at a time)
  local xs = {}
  for k, v in pairs(x) do xs[k] = v end
  xs.heur, xs.noAlt, xs.noLimit, xs.nodeCap, xs.flood = WG.HEUR, true, true, nil, nil
  local function Seg(from, fromCi, home, segGoals, gx, gy)
    xs.home = home
    local steps = WG.Search(c, { { id = from, ci = fromCi, cost = 0 } }, segGoals, gx, gy, nil, xs)
    nodes = nodes + (WG.lastNodes or 0)
    return steps, steps and WG.lastCost or nil
  end
  local blocked = {} -- [in-node key * 2^20-ish .. out key]: a tile's way left out after its refine found none
  local verified = {} -- [in-node key] = { steps, cost } or false: the walk on to the stop from a way into its tile
  local dead = {} -- [surface id] = true: reached by a walk on to the stop in vain (none from there either)
  local missing = false -- (a tile on the way with no data: no "no way" from it)
  local cut = false
  local tries = 0
  local skipped = false
  -- `dry`: before any grid search (the start's flood, the walks on to the stop), the ways from the start's tile and
  -- into the stop's priced by their lines at the least a yard costs: the tiles' way as it would likely come out, for a
  -- look at the guards along it (ChainNearGuards) before a node is spent
  local function Plan(dry)
    -- (nodes: way in id * 2, way out id * 2 + 1)
    local g, parent, closed = {}, {}, {}
    local hk, hv = {}, {}
    local function Hd(px, py) return Dist(px, py, tx, ty) * kmin end
    local near = {} -- (ways near guards or an elite area, x.side: never taken, the way round the tiles' own)
    local function Relax(nk, cost, from, px, py)
      if closed[nk] then return end
      if x.side then
        local v = near[nk]
        if v == nil then
          v = HP.NearGuards(c, x, px, py)
          near[nk] = v
        end
        if v then return end
      end
      if not g[nk] or cost < g[nk] then
        g[nk], parent[nk] = cost, from
        WG.HeapPush(hk, hv, cost + Hd(px, py), nk)
      end
    end
    local s0x, s0y = starts[1].x or tx, starts[1].y or ty
    for k in pairs(startTiles) do
      local d = HP.TileData(c, k)
      for _, o in ipairs(d and d.X or {}) do
        local gt
        if dry then
          local qx, qy = CellPt(c, k, o.ci)
          gt = Dist(s0x, s0y, qx, qy) * kmin + o.cost
        else
          gt = fres.g[o.t]
        end
        if gt and not startTiles[o.tkey] then
          local px, py = CellPt(c, o.tkey, o.tci)
          Relax(o.t * 2, gt, "S", px, py)
        end
      end
    end
    local best, bestNode = huge, nil
    local pops = 0
    while hk[1] do
      local f, nk = WG.HeapPop(hk, hv)
      if f >= best then break end
      if not closed[nk] then
        closed[nk] = true
        pops = pops + 1
        if Rt.Breathe then Rt.Breathe(pops, 100) end
        if pops > HP.MAX_POPS then cut = true break end
        local gs = g[nk]
        local isIn = nk % 2 == 0
        local id = isIn and nk / 2 or (nk - 1) / 2
        local key = floor(id / SHIFT)
        local d = HP.TileData(c, key)
        if not d then
          missing = true
        elseif isIn then
          -- (a way into the stop's tile: the walk on to the stop, kept to its tile, once; dry: its line on)
          if dry and goalTiles[key] then
            local px, py = CellPt(c, key, d.Eci[d.inAt[id]])
            if gs + Hd(px, py) < best then best, bestNode = gs + Hd(px, py), nk end
          elseif goalTiles[key] then
            local v = verified[nk]
            -- (reached by a walk on in vain from another way in: none from here either, no search)
            if v == nil and dead[id] then
              v = false
              verified[nk] = false
              if HP.debug then HP.debug[#HP.debug + 1] = string.format("dead %d g%.0f", id, gs) end
            end
            if v == nil and not (tries < HP.GOAL_TRIES or parts.verify < HP.VERIFY_NODES) then
              skipped = true -- (a way in not tried: no "no way" for sure)
            end
            if v == nil and (tries < HP.GOAL_TRIES or parts.verify < HP.VERIFY_NODES) then
              tries = tries + 1
              HP.stats.tries = HP.stats.tries + 1
              local i = d.inAt[id]
              local n0 = nodes
              xs.keep, xs.res = true, nil
              local steps, cost = Seg(id, d.Eci[i], goalTiles, goals, tx, ty)
              xs.keep = nil
              if not steps and xs.res then
                for rid in pairs(xs.res.g) do dead[rid] = true end
              end
              xs.res = nil
              parts.verify = parts.verify + nodes - n0
              v = steps and { steps = steps, cost = cost } or false
              verified[nk] = v
              if HP.debug then HP.debug[#HP.debug + 1] = string.format("verify %d g%.0f -> %s (%d nodes)", id, gs, tostring(steps and cost), nodes - n0) end
            end
            if v and gs + v.cost < best then best, bestNode = gs + v.cost, nk end
          end
          local i = d.inAt[id]
          if i then
            local ex, ey = CellPt(c, key, d.Eci[i])
            local mc, mr, ms, md = d.Mc[i], d.Mr[i], d.Ms[i], d.Md[i]
            for j, cost in pairs(mc) do
              local o = d.X[j]
              local ok = md[j] <= lim and not blocked[nk .. ">" .. (o.s * 2 + 1)]
              if ok then
                local w = cost * (1 + mr[j] / 7 * (kRoad - 1) + ms[j] / 7 * (kSwim - 1))
                local px, py = CellPt(c, key, o.ci)
                if x.any then w = w + cost * LineExtra(x, ex, ey, px, py) end
                Relax(o.s * 2 + 1, gs + w, nk, px, py)
              end
            end
          end
        else
          for _, j in ipairs(d.outAt[id] or {}) do
            local o = d.X[j]
            if o.fall <= lim then
              local td = HP.TileData(c, o.tkey)
              if not td then
                missing = true
              elseif td.inAt[o.t] then
                local px, py = CellPt(c, o.tkey, o.tci)
                local w = o.cost
                if x.any then
                  local qx, qy = CellPt(c, key, o.ci)
                  w = w + o.cost * LineExtra(x, qx, qy, px, py)
                end
                Relax(o.t * 2, gs + w, nk, px, py)
              end
            end
          end
        end
      end
    end
    HP.stats.pops = HP.stats.pops + pops
    if not bestNode then return nil end
    local chain, k = {}, bestNode
    while k ~= "S" do
      table.insert(chain, 1, k)
      k = parent[k]
    end
    return chain, best
  end
  -- (the surfaces of a way's run in its tile: the way's own, and those on the tile's edge near it at about its height,
  -- each its line on to the next way as its extra, weighed as the search's heuristic is (hwS): the tile's search heads
  -- for the next way, and the first of the run it settles is the one it crosses by)
  local hwS = (xs.road or c.road) * WG.HEUR
  local function RunGoals(tid, nx, ny)
    local key = floor(tid / SHIFT)
    local t = WG.Tile(c, key)
    local out = {}
    if not t then return out end
    local d = HP.TileData(c, key)
    local tci = d and d.inAt[tid] and d.Eci[d.inAt[tid]]
    if not tci then
      out[tid] = 0
      return out
    end
    local per = c.per
    local a0, b0 = floor(tci / per), tci % per
    local z0 = WG.Z(c, t, tid - key * SHIFT)
    local R = HP.RUN_CELLS
    for a = max(0, a0 - R), min(per - 1, a0 + R) do
      for b = max(0, b0 - R), min(per - 1, b0 + R) do
        if a == 0 or b == 0 or a == per - 1 or b == per - 1 or (a == a0 and b == b0) then
          local ci = a * per + b
          local n = WG.Count(t, ci)
          if n > 0 then
            local f0 = WG.First(t, ci)
            local cheb = max(abs(a - a0), abs(b - b0))
            for q = 0, n - 1 do
              local s = f0 + q
              if abs(WG.Z(c, t, s) - z0) <= HP.RUN_Z + HP.RUN_SLOPE * cheb then
                local px, py = WG.Pt(c, t, s, ci)
                out[key * SHIFT + s] = Dist(px, py, nx, ny) * hwS
              end
            end
          end
        end
      end
    end
    out[tid] = out[tid] or 0
    return out
  end
  -- (guards or an elite area near the tiles' likely way: the grid's own search, before a node is spent on this one)
  if pre then
    -- (a start in a pocket of its tile: a flood of PREFLIGHT_NODES at most reaches no other tile)
    local xp = {}
    for k, v in pairs(x) do xp[k] = v end
    xp.heur, xp.flood, xp.home, xp.noAlt, xp.noLimit, xp.nodeCap, xp.res = 0, true, startTiles, true, nil,
      HP.PREFLIGHT_NODES, nil
    WG.Search(c, starts, {}, tx, ty, nil, xp)
    local res = xp.res
    if res and not xp.limitHit then
      local out = false
      for id in pairs(res.g) do
        if not startTiles[floor(id / SHIFT)] then out = true break end
      end
      if not out then
        HP.stats.pocket = (HP.stats.pocket or 0) + 1
        return nil
      end
    end
    return "ok"
  end
  if x.side then
    local chain = Plan(true)
    if chain and x.side and HP.ChainNearGuards(c, x, chain, starts[1].x or tx, starts[1].y or ty, tx, ty) then
      HP.stats.guards = (HP.stats.guards or 0) + 1
      HP.stats.guardsEarly = (HP.stats.guardsEarly or 0) + 1
      WG.lastNodes, WG.lastCost = 0, nil
      return nil
    end
    missing, cut = false, false
  end
  -- (the start's tile flooded: the costs to its ways out, and the way to each)
  local xf = {}
  for k, v in pairs(x) do xf[k] = v end
  xf.heur, xf.flood, xf.home, xf.noAlt, xf.noLimit, xf.nodeCap, xf.res = 0, true, startTiles, true, true, nil, nil
  WG.Search(c, starts, {}, tx, ty, nil, xf)
  fres = xf.res
  xf.res = nil
  nodes = nodes + (fres and fres.nodes or 0)
  if not fres then return nil end
  parts.flood = nodes
  for _ = 0, HP.REPLANS do
    local chain, total = Plan()
    if not chain then
      if exact and not missing and not cut and not skipped then
        HP.stats.noWay = HP.stats.noWay + 1
        HP.stats.nodes = HP.stats.nodes + nodes
        WG.lastNodes, WG.lastCost = nodes, nil
        return false
      end
      HP.stats.gaveUp = HP.stats.gaveUp + 1
      HP.gaveUp[goalSig] = true
      return nil
    end
    -- (a way near guards or an elite area: the grid's own search, which goes round them or through them as 1.4.1 did
    -- (round within its cap, then the way through and "Take it?"); the tiles' ways are priced along their lines only)
    if x.side and HP.ChainNearGuards(c, x, chain, starts[1].x or tx, starts[1].y or ty, tx, ty) then
      HP.stats.guards = (HP.stats.guards or 0) + 1
      HP.stats.nodes = HP.stats.nodes + nodes
      return nil
    end
    -- (the start's flood's way to the first way in)
    local first = chain[1] / 2
    local steps = {}
    local cur = first
    while cur do
      table.insert(steps, 1, { id = cur, key = floor(cur / SHIFT), ci = fres.cellOf[cur], link = fres.via[cur],
        drop = fres.dropAt[cur] })
      cur = fres.prev[cur]
    end
    local cost = fres.g[first]
    local at, atCi = first, fres.cellOf[first]
    local failed = false
    -- (WINDOW tiles at a time: from where the last refine arrived to the run of the way into the tile after them, kept
    -- to those tiles (the ways between them free to move); the last ones' on to the stop. A refine with no way from where
    -- the one before arrived (another surface of the way's run than the way's own): the one before again, to the way's
    -- own surface, then on)
    local marks, repOnly, before = {}, {}, {}
    local q = 1
    while q <= #chain do
      marks[q] = { n = #steps, cost = cost, at = at, atCi = atCi }
      local seg, sc
      local qEnd = q + 2 * HP.WINDOW
      local home = {}
      -- (the last window takes the stop's tile in with the one before it at least: the way into the stop's tile free,
      -- not the way in's own surface the walk on to the stop was searched from; Darkshore to Felwood 7.6k against 7.2k)
      if qEnd >= #chain then qEnd = #chain + 2 end
      for m = q, math.min(qEnd - 2, #chain), 2 do
        local k = floor(chain[m] / 2 / SHIFT)
        -- (and the tiles round them, HOME_RING: a road down off Red Cloud Mesa wound through a tile off the way, and
        -- the refine kept to the way's tiles dropped off the rim instead)
        local tx0, ty0 = floor(k / 64), k % 64
        for i = -HP.HOME_RING, HP.HOME_RING do
          for j = -HP.HOME_RING, HP.HOME_RING do
            local a, b = tx0 + i, ty0 + j
            if a >= 0 and a < 64 and b >= 0 and b < 64 then home[a * 64 + b] = true end
          end
        end
      end
      if qEnd > #chain then
        local v = verified[chain[q]]
        if v and q == #chain and at == chain[q] / 2 then
          seg, sc = v.steps, v.cost
        else
          for k in pairs(goalTiles) do home[k] = true end
          local n0 = nodes
          seg, sc = Seg(at, atCi, home, goals, tx, ty)
          parts.seg, parts.segs = parts.seg + nodes - n0, parts.segs + 1
        end
        qEnd = #chain + 2
      else
        local tid = chain[qEnd] / 2
        local nx, ny = tx, ty
        if chain[qEnd + 1] then
          local oid = (chain[qEnd + 1] - 1) / 2
          local od = HP.TileData(c, floor(oid / SHIFT))
          local j = od and od.outAt[oid] and od.outAt[oid][1]
          if j then nx, ny = CellPt(c, floor(oid / SHIFT), od.X[j].ci) end
        end
        local tk = floor(tid / SHIFT)
        local td = HP.TileData(c, tk)
        local gx, gy = CellPt(c, tk, td.Eci[td.inAt[tid]])
        local rg = repOnly[q] and { [tid] = 0 } or RunGoals(tid, nx, ny)
        if repOnly[q] then nx, ny = gx, gy end
        local n0 = nodes
        seg, sc = Seg(at, atCi, home, rg, nx, ny)
        parts.seg, parts.segs = parts.seg + nodes - n0, parts.segs + 1
        if seg then sc = sc - (rg[seg[#seg].id] or 0) end -- (its goal's line on: not a cost of the way)
      end
      if seg then
        for m = 2, #seg do steps[#steps + 1] = seg[m] end
        cost = cost + sc
        at, atCi = seg[#seg].id, seg[#seg].ci
        before[qEnd] = q
        q = qEnd
      elseif before[q] and at ~= chain[q] / 2 and not repOnly[before[q]] then
        local p0 = before[q]
        parts.back = (parts.back or 0) + 1
        repOnly[p0] = true
        local b = marks[p0]
        for m = #steps, b.n + 1, -1 do steps[m] = nil end
        cost, at, atCi = b.cost, b.at, b.atCi
        q = p0
      else
        if q == #chain then verified[chain[q]] = false else blocked[chain[q] .. ">" .. chain[q + 1]] = true end
        parts.replans = (parts.replans or 0) + 1
        HP.stats.replans = HP.stats.replans + 1
        failed = true
        break
      end
    end
    -- (the tiles on the way, their regions loaded by the refine now: any whose ways weren't for its map data, the
    -- grid's own search)
    if not failed then
      for m = 1, #chain, 2 do
        local k = floor(chain[m] / 2 / SHIFT)
        if not HP.Fresh(c, k) then
          c.hpaP[k] = false
          HP.stats.gaveUp = HP.stats.gaveUp + 1
      HP.gaveUp[goalSig] = true
          return nil
        end
      end
    end
    -- (the other faction's guards, an elite area (Router.HostileAt's light ones): a way past them the tiles' ways can't
    -- tell from a way round, priced along their lines only. One that goes by them: the grid's own search, which goes
    -- round them or through them as 1.4.1 did (round within its cap, then the way through and "Take it?"))
    if not failed and x.side and HP.PastGuards(c, x, steps) then
      HP.stats.guards = (HP.stats.guards or 0) + 1
      HP.stats.nodes = HP.stats.nodes + nodes
      return nil
    end
    if not failed then
      HP.stats.found = HP.stats.found + 1
      HP.stats.nodes = HP.stats.nodes + nodes
      WG.lastNodes, WG.lastCost = nodes, cost
      HP.lastChain, HP.lastEstimate = chain, total
      return steps
    end
  end
  HP.stats.gaveUp = HP.stats.gaveUp + 1
      HP.gaveUp[goalSig] = true
  return nil
end
