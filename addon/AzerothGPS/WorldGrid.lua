-- World routing on a layered walk grid (1.4.0, always on since item 74, no option;
-- /agps worldgrid shows its stats; docs/world-grid-1.4.0.md). Asked 2026-11-22: the city grid's way
-- (CityGrid.lua) over the whole open world, the land's roads a little preferred, the capitals on their city grids only.
--
-- The grids (`agps world-grid --write`, worldgrid.py and worldbake.py): baked from our own navigation meshes of every map
-- tile's collision (the terrain, every placed model, the solid doodads), a square grid of 8.33 yd cells (64 a map tile),
-- each cell's walkable surfaces (floors over floors: a bridge over a river, a tower's floors, a cave under a hill)
-- linked to the surface they walk onto in each of the 8 neighbor cells where the mesh is walked straight between them
-- (both ways; one way off a ledge down onto the floor under it: a drop), swims over the terrain grid's water (Recast
-- doesn't swim), road ground (the open world's roads: a yard there costs `road`, a little less) and road links (a road
-- over what the mesh can't walk: a bridge deck, a ledge).
--
-- The data loads only as a route needs it (asked 2026-11-22, "only load data that's needed for the route"): this
-- addon's Data/WorldGrid<cont>.lua holds a continent's numbers only; its map tiles are in load-on-demand folders, one a
-- region of REGION x REGION map tiles (AzerothGPS_WG<cont>_<rx>_<ry>), loaded (C_AddOns.LoadAddOn) the first time a
-- search reaches one of its tiles, in the background; a map tile is decoded the first time a search reaches it
-- (WG.Tile, in the background's slices) into the city grid's layout (a character a cell, SURF characters a surface, read
-- in place), the least recently used dropped past TILE_CACHE_MB. Nothing of it is loaded at login.
--
-- Routing (WG.Leg, asked first by Router.Route while the option is on): a leg on a continent with both ends outside
-- the capitals is searched on the grid (A* in the background, a slice at a time; short legs anywhere, long ones in a
-- corridor round the Router's own route) and drawn string-pulled with its heights (`fz`); a leg with one end in a
-- capital: the grid's walk to where the Router's own route comes into the city, the city's grid from there
-- (CityGrid.lua); both ends in one capital: the city grid's (CG.Leg). Rides, legs on other levels (Undercity, a
-- dungeon) and anything the grid can't walk: the Router's own, as before. The grid's costs are the Router's (WG.Costs):
-- the other faction's guards, zones too high, swimming, the player's own walls, erasers and roads, the safe drop.
local _, ns = ...
local WG = {}
ns.WorldGrid = WG

local floor, sqrt, abs, huge, max, min = math.floor, math.sqrt, math.abs, math.huge, math.max, math.min
local byte, sub = string.byte, string.sub

WG.SAME_FLOOR_Z = 1.5 -- yards: surfaces of a spot's cell this near the ground's height are all its floor (Ends)
WG.OTHER_FLOOR_YD = 150 -- yards: what one of its other reached floors costs more as a spot's end (no height: Ends)
WG.FLOOR_Z = 4 -- yards: a spot's height takes the surfaces this near it (else the nearest, dearer)
WG.Z_COST = 6
WG.NEAR_CELLS = 3 -- cells round a spot looked at when its own has no surface (25 yd: a stop on a rock's side)
WG.SLICE = 150 -- nodes settled between pauses in the background
WG.MAX_NODES = 200000 -- (a search giving up: the Router's own) ...
-- ... and a leg's own budget, NODES_BASE and NODES_PER_YD a yard of its straight line: a stop the grid can't reach
-- flooded 600,000 nodes (30 s of work and its tables, hundreds of MB in game) before giving up; the ways found on the
-- sample legs took at most 34,000 (a 1 km walk up Teldrassil's roots)
WG.NODES_BASE, WG.NODES_PER_YD = 60000, 50
WG.HEUR = 1.1 -- the heuristic's weight over the cheapest yard (road ground's): 10-35% fewer nodes, lengths within 1%
-- Whether the straight line from (sx, sy) to (tx, ty) passes the other faction's guards (search costs `x`'s side), looked
-- at every GUARD_LINE_STEP yards: a long way round that doesn't is the land's, not theirs (the Bluefen and warrior trips'
-- budgets, test_world_grid_alt).
WG.GUARD_LINE_STEP = 15
function WG.GuardsOnLine(x, sx, sy, tx, ty)
  local Rt = ns.Router
  if not (x and x.side and Rt and Rt.HostileAt) then return false end
  local n = math.max(1, math.floor(math.sqrt((tx - sx) ^ 2 + (ty - sy) ^ 2) / WG.GUARD_LINE_STEP))
  for i = 0, n do
    local t = i / n
    if Rt.HostileAt(x.cont, sx + (tx - sx) * t, sy + (ty - sy) * t, x.side, x.exempt) then return true end
  end
  return false
end
WG.DETOUR_FACTOR, WG.DETOUR_YD = 1.5, 1000 -- (a way round the guards kept within both over the way through: item 53c)
WG.HOSTILE_CAP = 80000
-- A side walk (the ride check's, Nav's CompareRide: to a dock or a flight master, not one of the trip's stops; the
-- route's own walks never): this many nodes a search at most. The route-speed study, 2026-11-25: from Thelsamar to Kharanos as a
-- Horde player the ride check's walks ran to 150,000 and 200,000 nodes one after another, 4-8 s of search each, none
-- finding a way, the queue held for minutes. A walk that needs more isn't one a plan with a ride is better for; cut
-- short it's remembered as searched in vain from round there (WG.Failed).
WG.SIDE_WALK_CAP = 60000
WG.REFUSED_FACTOR = 100 -- (a yard past the guards after a No: this many; Router.HOSTILE_FACTOR before it)
-- Whether this trip's "Take it?" was answered No (Nav.riskOk.trip): the grid's legs then never go through the guards.
function WG.GuardsRefused()
  local N = ns.Nav
  return N and N.riskOk and N.riskOk.trip == false or false
end
-- A leg whose search round the guards found nothing within its cap: said in the debug log (item 63b: what the way round
-- cost before the way through was taken).
function WG.LogThrough(sx, sy, tx, ty, nodes)
  local D = ns.Debug
  if D and D.Log then
    pcall(D.Log, "worldgrid through guards", { from = string.format("%.0f,%.0f", sx, sy),
      to = string.format("%.0f,%.0f", tx, ty), roundNodes = nodes })
  end
end
WG.HOSTILE_LONG_CAP = 150000 -- (a long leg's weighed search round the guards, at most: then the way through) -- (a search round the other faction's guards, at most: then the walk through them, item 51)
WG.LONG_LEG_YD, WG.HEUR_LONG = 3000, 3 -- (a leg this long, straight, or longer: weighed so, item 38)
WG.CLIMB_COST = 0.5 -- each yard up or down costs this many more
WG.FREE_YD = 1500 -- a leg this short (straight) is searched anywhere on the grid ...
WG.CORRIDOR_YD = 120 -- ... a longer one within this many yards of the Router's own route (its roads, its walks)
WG.CORRIDOR_BUCKET = 40 -- (the corridor's cells)
WG.CORRIDOR_WIDE_YD = 600 -- ... and, none found in it, within this many
-- A grid's way by road ground at most this many times the line, else at most this many times its walk with no road
-- preference (WG.Walk: no far road snap, open ground to open ground; the road preference alone would take 1 / road)
WG.ROAD_DETOUR_MAX = 1.2
WG.ROAD_PRICE_MIN = 1 / 1.5 -- (a road yard's price at the least, any Road tolerance: item 83)
WG.ROAD_PRICE_TOP = 0.95 -- (and at "Cut across", +10: a road within about 18 degrees of the way still taken. Item 57)
-- A route that goes past its stop and comes back: a point OVERSHOOT_YD further from the start than the stop is, and
-- OVERSHOOT_YD or more from the stop (item 83: a road's discount never makes the way overshoot, at any tolerance)
WG.OVERSHOOT_YD, WG.OVERSHOOT_ROUND = 80, 1.6
-- Only on the roads' pieces (kind 0): a way round a cliff off them goes past the stop's distance too, and searching it
-- again doubled the landmark trips' searches (warrior 41k -> 78k nodes)
function WG.Overshoots(route, sx, sy, tx, ty)
  local pts, kinds = route and route.pts, route and route.kinds
  if not pts then return false end
  local function D2(ax, ay, bx, by) return math.sqrt((ax - bx) ^ 2 + (ay - by) ^ 2) end
  local D = D2(sx, sy, tx, ty)
  for i = 1, #pts - 1, 2 do
    local p = (i + 1) / 2
    local onRoad = kinds and (kinds[p] == 0 or kinds[p - 1] == 0)
    local x, y = pts[i], pts[i + 1]
    if onRoad and D2(sx, sy, x, y) > D + WG.OVERSHOOT_YD and D2(x, y, tx, ty) > WG.OVERSHOOT_YD then return true end
  end
  return false
end
WG.ROAD_DETOUR_SLACK = 0.5 -- (the share of the bound kept for the weighted heuristic's slack: WG.Walk)
WG.CACHE = 12 -- routes kept (the least recently found dropped)
WG.TILE_CACHE_MB = 6 -- decoded map tiles kept up to about this many MB (the least recently used dropped first)
WG.LINE_TOL = 0.4 -- a straight line keeps within this many cells of each crossed surface's own point (the city
WG.LINE_TOL_EDGE = 0.25 -- grid's 0.75 and 0.4 of its 3 yd cells; these cells are 8.33: 0.75 cut corners by 6 yd)
WG.Z_BEND = 1.5
WG.LOOK_AHEAD = 48 -- steps a straight stretch is tried toward (WG.Pull), farthest first
WG.SPLICE_STEP = 2
WG.DROP_Z = 3 -- yards: a link down this far or more that the surface below doesn't link back is a drop off a ledge
-- (an erase stroke of the player's over a wall the bake cut: the links across it opened again, to the neighbor's surface
-- nearest in height within the grid's climb, citygrid.dz_max: a step's yards * tan(WALK_SLOPE) + CLIMB)
WG.ERASE_SLOPE, WG.ERASE_CLIMB = math.tan(math.rad(55)), 1
WG.ROAD_HALF_YD = 3 -- yards either side of the player's own drawn road its cells are road ground (worldgrid.ROAD_HALF_YD)

WG.stats = { grid = 0, spliced = 0, own = 0, open = 0, pending = 0, searches = 0, nodes = 0, ms = 0, tiles = 0,
  regions = 0, rawBytes = 0, tileBytes = 0 }

local ALPHA = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
local DEC = {}
for i = 1, #ALPHA do DEC[byte(ALPHA, i)] = i - 1 end
local CH = {} -- (ALPHA's i-th character, as sub(ALPHA, i, i): the tiles' decoding, 7 a surface)
for i = 1, #ALPHA do CH[i] = sub(ALPHA, i, i) end
local REP = byte(".")
local DX = { 1, 0, -1, 0, 1, -1, -1, 1 }
local DY = { 0, 1, 0, -1, 1, 1, -1, -1 }
local OPP = { 3, 4, 1, 2, 7, 8, 5, 6 }
local SURF = 9 -- flags, point, 4 links, height (3: (z - z0) / zq)
local F_SWIM, F_ROAD, F_REACH = 1, 2, 4
-- (a surface at a rim with a model's wall standing on it, worldgrid.RIM_WALL_CELLS: no fall off the rim starts there.
-- Item 43, Red Cloud Mesa's palisade: the route fell 32 yd off the mesa through it)
local F_RIM_WALL = 8
WG.F_RIM_WALL = F_RIM_WALL
local ZERO = byte("0") -- (a surface's links as the heights give them)
local ZESC = 62 -- (a height written whole: this, then 3 characters)
local SHIFT = 131072 -- a surface's id: its tile's key * SHIFT + its index in the tile
WG.SHIFT = SHIFT
local BASE = 8 -- (cells per entry of a tile's `base`: its first surface)
WG.REGION_ADDON = "AzerothGPS_WG%d_%d_%d"

function WG.On()
  local s = ns.settings and ns.settings.gps
  return s ~= nil and s.worldGrid == true
end

local function R() return ns.Router end
local function Dist(x1, y1, x2, y2) return sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2) end
local function Bit(v, b) return floor(v / b) % 2 == 1 end

---------------------------------------------------------------------------------------------------- the data
WG.conts = {}
WG.store = {} -- [cont] = the regions' data loaded: { raw, regions, links, out }
WG.tick = 0 -- (tiles' last use)
-- The continent's grid: its numbers (Data/WorldGrid<cont>.lua); its regions' tiles and road links as they're loaded.
function WG.Cont(cont)
  local d = ns.WorldGridData and ns.WorldGridData[cont]
  if not d then return nil end
  local c = WG.conts[cont]
  if c and c.d == d then return c end
  -- (the regions loaded, kept apart from the decoded tiles: a folder loads once a session, WG.LoadRegion)
  local st = WG.store[cont]
  if not (st and st.d == d) then
    st = { d = d, raw = {}, regions = {}, links = {}, out = {}, loading = {} }
    WG.store[cont] = st
  end
  c = { cont = cont, d = d, per = d.per, cell = d.cell, zq = d.zq, z0 = d.z0, road = d.road or 0.85,
    swim = d.swim or 1.5, implied = d.implied or 4, rb = d.rb or 8, raw = st.raw, regions = st.regions, none = {},
    tiles = {}, bytes = 0, links = st.links, out = st.out, loading = st.loading }
  WG.conts[cont] = c
  return c
end

-- A tile's region: "rx:ry" (its folder AzerothGPS_WG<cont>_<rx>_<ry>).
local function RegionOf(c, key)
  return floor(floor(key / 64) / c.rb), floor((key % 64) / c.rb)
end
WG.RegionOf = RegionOf

-- The road links of a region's data ("ka:ia,kb:ib,yards,kind,x,y,z,...;..."): a yard of one costs the data's `road`.
-- Parsed into `ld.links` from `ld.at` on, pausing in a background job (item 108: a region's 1,500 links were 27-34 ms in
-- one slice); put in place with the region's tiles in one go (WG.LoadRegion's Commit).
WG.LINKS_BREATHE = 100 -- (links parsed between looks at the slice)
local function ParseLinks(ld)
  local s = ld.e.links or ""
  local Rt = R()
  local n = 0
  while ld.at <= #s do
    local j = s:find(";", ld.at, true) or (#s + 1)
    local item = s:sub(ld.at, j - 1)
    ld.at = j + 1
    local ka, ia, kb, ib, rest = item:match("^(%d+):(%d+),(%d+):(%d+),(.*)$")
    if ka then
      local nums = {}
      for v in rest:gmatch("[^,]+") do nums[#nums + 1] = tonumber(v) end
      local L = { a = tonumber(ka) * SHIFT + tonumber(ia), b = tonumber(kb) * SHIFT + tonumber(ib), yd = nums[1],
        kind = nums[2], pts = {}, bkey = tonumber(kb) }
      for q = 3, #nums - 2, 3 do L.pts[#L.pts + 1] = { nums[q], nums[q + 1], nums[q + 2] } end
      ld.links[#ld.links + 1] = L
    end
    n = n + 1
    -- (a pause: another search reaching the region meanwhile carries the parse on from ld.at, WG.LoadRegion)
    if Rt.Breathe and n % WG.LINKS_BREATHE == 0 then Rt.Breathe(n, WG.LINKS_BREATHE) end
  end
end
local function AddLinks(c, list)
  for _, L in ipairs(list) do
    c.links[#c.links + 1] = L
    local o = c.out[L.a]
    if not o then o = {} c.out[L.a] = o end
    o[#o + 1] = #c.links
  end
end

-- A region's folder the game wouldn't load (turned off in the AddOn List, or missing): said once a session, with
-- the way back (the route there is the Router's own meanwhile). `reason` is the game's (DISABLED, MISSING, ...).
function WG.RegionMissing(name, reason)
  if WG.toldMissing then return end
  local isLoaded = (C_AddOns and C_AddOns.IsAddOnLoaded) or IsAddOnLoaded
  if isLoaded and isLoaded(name) then return end -- (loaded already: nothing's wrong)
  WG.toldMissing = true
  local L = ns.L
  local info = (C_AddOns and C_AddOns.GetAddOnInfo) or GetAddOnInfo
  local title
  if info then
    local ok, _, t = pcall(info, name)
    if ok and type(t) == "string" and t ~= "" then title = t end
  end
  title = title or name
  if reason == "DISABLED" then
    ns.Print(string.format(L["%s is turned off in the AddOn List, so routes there use the older routing. To turn it back on, tick the AzerothGPS map data rows under AzerothGPS in the AddOn List, then /reload."], title))
  else
    local why = reason and (rawget(_G, "ADDON_" .. tostring(reason)) or tostring(reason)) or "?"
    ns.Print(ns.Format(L["%1$s couldn't be loaded (%2$s), so routes there use the older routing. Installing AzerothGPS again puts it back."], title, why))
  end
end

-- Loads region (rx, ry)'s folder (once; a region the data hasn't, or whose folder isn't there or is from another bake,
-- stays empty: the Router's own routes there). In a background job its road links are parsed in slices (ParseLinks).
-- (Item 82h: a region marked loaded before its tiles were in, a pause between, was taken for none for good by a search
-- in the pause (WG.Tile's c.none), and a job dropped in it (a new trip's, Router.DropBackground; a reset) left it with
-- no tiles for the session: every walk there no way, remembered. So the region stays unmarked (nil) until everything
-- is in, put in place in one go (Commit), and its load's state (`c.loading`, kept with the regions) is carried on by
-- whichever search reaches the region next: the folder loaded once, never half taken.)
local function Commit(c, rk, ld)
  local e, ea = ld.e, ld.ea
  local n = 0
  for k, v in pairs(e.t) do
    c.raw[k] = v
    n = n + #v
  end
  AddLinks(c, ld.links)
  -- (the region's landmark fields, its Alt.lua: item 33; another bake's or a count unlike the continent's, none)
  if type(ea) == "table" and ea.bake == c.d.bake and type(ea.t) == "table" and type(ea.n) == "number"
      and (c.altN == nil or c.altN == ea.n) then
    c.alt, c.altN = c.alt or {}, ea.n
    for k, v in pairs(ea.t) do c.alt[k] = v end
    -- (the far set, every fall: item 47)
    if type(ea.t2) == "table" and type(ea.n2) == "number" then
      c.alt2, c.altN2 = c.alt2 or {}, ea.n2
      for k, v in pairs(ea.t2) do c.alt2[k] = v end
    end
    -- (and its blocks' ways out, the corridor's: item 38)
    if type(ea.e) == "table" then
      c.altE = c.altE or {}
      for k, v in pairs(ea.e) do c.altE[k] = v end
    end
    if type(ea.x) == "table" then
      c.altX = c.altX or {}
      for k, v in pairs(ea.x) do c.altX[k] = v end
    end
  end
  c.loading[rk] = nil
  c.regions[rk] = true
  WG.stats.regions = WG.stats.regions + 1
  WG.stats.rawBytes = WG.stats.rawBytes + n + #(e.links or "")
end
function WG.LoadRegion(c, rx, ry)
  local rk = rx .. ":" .. ry
  local got = c.regions[rk]
  if got ~= nil then return got end
  if not c.loading then c.loading = {} end
  local ld = c.loading[rk]
  if not ld then
    if not (c.d.regions and c.d.regions[rk]) then
      c.regions[rk] = false
      return false
    end
    local name = string.format(WG.REGION_ADDON, c.cont, rx, ry)
    local load = (C_AddOns and C_AddOns.LoadAddOn) or LoadAddOn
    if load then
      local ok, loaded, reason = pcall(load, name)
      if ok and not loaded then WG.RegionMissing(name, reason) end
    end
    local key = c.cont .. ":" .. rk
    local all = rawget(_G, "AzerothGPS_WorldGridTiles")
    local e = type(all) == "table" and all[key] or nil
    if type(all) == "table" then all[key] = nil end -- (held here only: dropped with the grid)
    local alts = rawget(_G, "AzerothGPS_WorldGridAlt")
    local ea = type(alts) == "table" and alts[key] or nil
    if type(alts) == "table" then alts[key] = nil end
    if type(e) ~= "table" or e.bake ~= c.d.bake or type(e.t) ~= "table" then
      c.regions[rk] = false
      return false
    end
    ld = { e = e, ea = ea, links = {}, at = 1 }
    c.loading[rk] = ld
  end
  ParseLinks(ld)
  -- (put in place by another search while this one paused: nothing more to do)
  if c.regions[rk] ~= nil then return c.regions[rk] end
  Commit(c, rk, ld)
  return true
end

-- A tile's box: its first cell (global gx, gy: floor(x / cell), floor(y / cell)).
local function Origin(c, key)
  local tx, ty = floor(key / 64), key % 64
  return (31 - ty) * c.per, (31 - tx) * c.per
end
WG.Origin = Origin
-- The tile and its cell (0-based, a * per + b) of global cell (gx, gy).
local function CellKey(c, gx, gy)
  local per = c.per
  local ty, tx = 31 - floor(gx / per), 31 - floor(gy / per)
  if tx < 0 or tx > 63 or ty < 0 or ty > 63 then return nil end
  local gx0, gy0 = (31 - ty) * per, (31 - tx) * per
  return tx * 64 + ty, (gx - gx0) * per + (gy - gy0)
end
WG.CellKey = CellKey

local TILE_CHECK, TILE_CHECK_SURF = 100, 25 -- (a tile's decoding: tokens or cells, and surfaces, between looks at the clock)
-- (a tile decoded: about its bytes in memory)
local function TileBytes(t) return #t.s + #t.cells + 16 * #t.base + 400 end

-- Decodes tile `key` of grid `c` (see worldbake.encode_tiles): { cells (a character a cell: its count), s (SURF
-- characters a surface: a record without its links has them as the heights give them, IMPLIED), base (the first
-- surface of every BASE cells) }, or false where the grid has nothing. Its region loaded first when it isn't.
function WG.Tile(c, key)
  local t = c.tiles[key]
  if t then
    WG.tick = WG.tick + 1
    t.used = WG.tick
    return t
  end
  if c.none[key] then return false end
  local raw = c.raw[key]
  if not raw then
    local rx, ry = RegionOf(c, key)
    if c.regions[rx .. ":" .. ry] == nil then
      WG.LoadRegion(c, rx, ry)
      raw = c.raw[key]
      t = c.tiles[key] -- (decoded meanwhile by another search)
      if t then return t end
    end
  end
  if not raw then
    c.none[key] = true
    return false
  end
  local Rt = R()
  -- (and a look at the slice's clock between those pauses: on the slow client (test_frame_budget's VM clock) 500
  -- surfaces' links were 8 ms, a tile's decoding ran 20 ms slices. Item 108)
  local SliceOver = Rt.SliceOver
  local function Over() if SliceOver and SliceOver() then coroutine.yield() end end
  local bar = raw:find("|", 1, true)
  local bar2 = raw:find("|", bar + 1, true)
  local bar3 = raw:find("|", bar2 + 1, true)
  local per = c.per
  local n = per * per
  -- (each part's tokens, REP repeating the one before)
  local function Tokens(i, j, width)
    local out, k, last = {}, 0, nil
    while i < j do
      local b = byte(raw, i)
      if b == REP then
        local r = DEC[byte(raw, i + 1)] + 2
        for _ = 1, r do k = k + 1 out[k] = last end
        i = i + 2
      else
        local w = width(b)
        last = w == 1 and DEC[b] or sub(raw, i, i + w - 1)
        k = k + 1
        out[k] = last
        i = i + w
      end
      if Rt.Breathe and k % 2000 == 0 then Rt.Breathe(k, 2000) elseif k % TILE_CHECK == 0 then Over() end
    end
    return out
  end
  local counts = Tokens(1, bar, function() return 1 end)
  local recs = Tokens(bar + 1, bar2, function() return 2 end)
  local hs = Tokens(bar2 + 1, bar3, function(b) return DEC[b] == ZESC and 4 or 1 end)
  local lks = Tokens(bar3 + 1, #raw + 1, function(b) return b == ZERO and 1 or 5 end)
  -- (the heights: each against its prediction, the same surface of the cell before in the column, else that cell's
  -- last, else the last; worldbake.encode_tiles)
  local vs, firsts = {}, {}
  local q, prevCell, last = 0, {}, nil
  for ci = 0, n - 1 do
    local cnt = counts[ci + 1] or 0
    firsts[ci] = q
    if ci % per == 0 then prevCell = {} end
    if cnt == 0 then
      prevCell = {}
    else
      local cur = {}
      for k = 1, cnt do
        q = q + 1
        local h = hs[q]
        local v
        if type(h) == "string" then
          v = (DEC[byte(h, 2)] * 64 + DEC[byte(h, 3)]) * 64 + DEC[byte(h, 4)]
        else
          local pred = prevCell[k] or prevCell[#prevCell] or last or 0
          v = pred + h - 31
        end
        last = v
        cur[k] = v
        vs[q] = v
      end
      prevCell = cur
    end
    if Rt.Breathe and ci % 1000 == 0 then Rt.Breathe(ci, 1000) elseif ci % TILE_CHECK == 0 then Over() end
  end
  -- (the links: those the heights give, worldbake.implied_rows: per direction the neighbor cell's surface nearest in
  -- height, the lower on a tie, within `implied` steps and in this tile; plus the written difference, mod 8)
  local imp = c.implied
  local out = {}
  local done = 0
  local L = {}
  for ci = 0, n - 1 do
    local cnt = counts[ci + 1] or 0
    if cnt > 0 then
      local a, b = floor(ci / per), ci % per
      for k = 1, cnt do
        local qq = firsts[ci] + k
        local v = vs[qq]
        for d = 1, 8 do
          local na, nb = a + DX[d], b + DY[d]
          local best = 0
          if na >= 0 and na < per and nb >= 0 and nb < per then
            local nci = na * per + nb
            local f0, bd = firsts[nci], nil
            for kk = 1, counts[nci + 1] or 0 do
              local dz = abs(vs[f0 + kk] - v)
              if not bd or dz < bd then bd, best = dz, kk end
            end
            if not bd or bd > imp then best = 0 end
          end
          L[d] = best
        end
        local df = lks[qq]
        if df ~= 0 then
          for m = 1, 4 do
            local w = DEC[byte(df, m + 1)]
            L[2 * m - 1] = (L[2 * m - 1] + floor(w / 8)) % 8
            L[2 * m] = (L[2 * m] + w % 8) % 8
          end
        end
        -- (each character a piece of one table, concatenated once: no string a surface, which churned the garbage
        -- collector, the memory climbing in game)
        local o = (qq - 1) * 8
        out[o + 1] = recs[qq]
        for m = 1, 4 do
          local w = L[2 * m - 1] * 8 + L[2 * m] + 1
          out[o + 1 + m] = CH[w]
        end
        local v1, v2, v3 = floor(v / 4096) % 64, floor(v / 64) % 64, v % 64
        out[o + 6], out[o + 7], out[o + 8] = CH[v1 + 1], CH[v2 + 1], CH[v3 + 1]
        done = done + 1
        if Rt.Breathe and done % 500 == 0 then Rt.Breathe(done, 500) elseif done % TILE_CHECK_SURF == 0 then Over() end
      end
    end
  end
  -- (the cells' counts as one string, and the first surface of every BASE cells)
  local parts, base, acc = {}, {}, 0
  for qi = 1, n do
    if (qi - 1) % BASE == 0 then base[#base + 1] = acc end
    local v = counts[qi] or 0
    parts[qi] = CH[v + 1]
    acc = acc + v
  end
  -- (a pause first if the slice is over: the joins and the collector's step below can't pause)
  if Rt.SliceOver and Rt.SliceOver() then coroutine.yield() end
  -- (another search may have decoded it meanwhile, in its own slices)
  if c.tiles[key] then return c.tiles[key] end
  local gx0, gy0 = Origin(c, key)
  t = { key = key, cells = table.concat(parts), s = table.concat(out), base = base, gx0 = gx0, gy0 = gy0, n = q }
  t.bytes = TileBytes(t)
  WG.tick = WG.tick + 1
  t.used = WG.tick
  c.tiles[key] = t
  c.bytes = c.bytes + t.bytes
  WG.stats.tiles = WG.stats.tiles + 1
  -- (the least recently used, of every continent's, dropped past TILE_CACHE_MB; never the one just decoded)
  while WG.TileBytesKept() > WG.TILE_CACHE_MB * 1048576 do
    local oc, old, ou
    for _, c2 in pairs(WG.conts) do
      for k2, t2 in pairs(c2.tiles) do
        if t2 ~= t and (not ou or t2.used < ou) then oc, old, ou = c2, k2, t2.used end
      end
    end
    if not old then break end
    oc.bytes = oc.bytes - oc.tiles[old].bytes
    oc.tiles[old] = nil
    WG.stats.evicted = (WG.stats.evicted or 0) + 1
  end
  WG.stats.tileBytes = WG.TileBytesKept()
  if Rt.SliceOver and Rt.SliceOver() then coroutine.yield() end
  WG.GcStep()
  return t
end

-- A step of the garbage collector after a tile decoded or a search done (their tables and strings let go): the game's
-- own steps lagged behind a long route's work and the addon's memory climbed (Kooki3z 2026-11-22, past 500 MB).
WG.GC_STEP = 256
-- (each step taken in pieces of GC_PIECE, with a pause when the slice is over between them: one step of 512 was a 13-16
-- ms slice, of 256 7-9 ms, past the slice's 1-5 ms. Item 108. The same work, the collector's own steps)
WG.GC_PIECE = 32
local function GcSteps(size)
  local Rt = R()
  local done = 0
  while done < size do
    local ok, finished = pcall(collectgarbage, "step", min(WG.GC_PIECE, size - done))
    done = done + WG.GC_PIECE
    if not ok then return true end -- (no collector steps here: as finished)
    if finished then return true end
    if done < size and Rt and Rt.SliceOver and Rt.SliceOver() then coroutine.yield() end
  end
  return false
end
WG.GcSteps = GcSteps
function WG.GcStep()
  if WG.GC_STEP and WG.GC_STEP > 0 then GcSteps(WG.GC_STEP) end
  -- (the heap grown GC_GROWTH_MB since the last cycle ended: a cycle run to its end in the background, item 59)
  local ok, kb = pcall(collectgarbage, "count")
  if ok and kb then
    WG.gcBase = WG.gcBase or kb
    if kb - WG.gcBase > WG.GC_GROWTH_MB * 1024 then WG.GcCycle() end
  end
end
-- The collector stepped (GC_CYCLE_STEP a slice, low in the background queue) until it finishes a cycle, so the searches'
-- tables are given back within a few frames, not when the game's own steps get round to it. Item 59, Kooki3z 2026-11-24
-- on the live client: "AddOn Memory 551 MB (374 MB AzerothGPS)"; in the harness six cross-zone trips held 130-190 MB
-- live, 90 of it kept. One cycle queued at a time; its end sets the base the growth is measured from.
WG.GC_GROWTH_MB, WG.GC_CYCLE_STEP = 32, 512
function WG.GcCycle()
  local Rt = R()
  if not (Rt and Rt.Background) or Rt.SYNC_WALKS then return false end
  return Rt.Background("worldgrid-gc", function()
    for _ = 1, 10000 do
      if GcSteps(WG.GC_CYCLE_STEP) then break end
      coroutine.yield()
    end
    local ok, kb = pcall(collectgarbage, "count")
    WG.gcBase = ok and kb or WG.gcBase
    WG.stats.gcCycles = (WG.stats.gcCycles or 0) + 1
    return true
  end, nil, nil, true)
end

-- Bytes of the decoded tiles kept, every continent's.
function WG.TileBytesKept()
  local n = 0
  for _, c in pairs(WG.conts) do n = n + (c.bytes or 0) end
  return n
end

-- (a surface's flags, 0-63, to whether it's road ground or water: the search's loop, without Bit's call)
local IS_ROAD, IS_SWIM = {}, {}
for v = 0, 63 do IS_ROAD[v], IS_SWIM[v] = Bit(v, F_ROAD), Bit(v, F_SWIM) end
local function Count(t, ci) return DEC[byte(t.cells, ci + 1)] end
local function First(t, ci)
  local b = floor(ci / BASE)
  local f = t.base[b + 1]
  local cells = t.cells
  for k = b * BASE + 1, ci do f = f + DEC[byte(cells, k)] end
  return f
end
local function Flags(t, s) return DEC[byte(t.s, s * SURF + 1)] end
local function Z(c, t, s)
  local p = s * SURF
  return ((DEC[byte(t.s, p + 7)] * 64 + DEC[byte(t.s, p + 8)]) * 64 + DEC[byte(t.s, p + 9)]) * c.zq + c.z0
end
local function Link(t, s, d)
  local v = DEC[byte(t.s, s * SURF + 2 + floor((d + 1) / 2))]
  if d % 2 == 1 then return floor(v / 8) end
  return v % 8
end
-- The surface's point (world x, y), its tile's cell ci.
local function Pt(c, t, s, ci)
  local v = DEC[byte(t.s, s * SURF + 2)]
  local a, b = floor(ci / c.per), ci % c.per
  return (t.gx0 + a + (floor(v / 8) + 0.5) / 8) * c.cell, (t.gy0 + b + (v % 8 + 0.5) / 8) * c.cell
end
WG.Count, WG.First, WG.Z, WG.Link, WG.Pt, WG.Flags = Count, First, Z, Link, Pt, Flags

-- The surfaces at (x, y): { id, key, ci, s (in its tile), z, x, y, f (flags) }; none in its cell: the nearest cell's
-- within NEAR_CELLS that has some. Nearest the spot's height first when `z` is given.
function WG.SurfacesAt(c, x, y, z)
  local gx, gy = floor(x / c.cell), floor(y / c.cell)
  local out = {}
  local function Add(cx, cy)
    local key, ci = CellKey(c, cx, cy)
    local t = key and WG.Tile(c, key)
    if not t then return false end
    local n = Count(t, ci)
    if n == 0 then return false end
    local f = First(t, ci)
    for k = 0, n - 1 do
      local s = f + k
      local px, py = Pt(c, t, s, ci)
      out[#out + 1] = { id = key * SHIFT + s, key = key, ci = ci, s = s, z = Z(c, t, s), x = px, y = py, f = Flags(t, s) }
    end
    return true
  end
  if not Add(gx, gy) then
    for r = 1, WG.NEAR_CELLS do
      local best, bd
      for di = -r, r do
        for dj = -r, r do
          if max(abs(di), abs(dj)) == r then
            local key, ci = CellKey(c, gx + di, gy + dj)
            local t = key and WG.Tile(c, key)
            if t and Count(t, ci) > 0 then
              local d2 = di * di + dj * dj
              if not bd or d2 < bd then best, bd = { gx + di, gy + dj }, d2 end
            end
          end
        end
      end
      if best then Add(best[1], best[2]) break end
    end
  end
  if z then table.sort(out, function(a, b) return abs(a.z - z) < abs(b.z - z) or (abs(a.z - z) == abs(b.z - z) and a.id < b.id) end) end
  return out
end

-- The surfaces a leg's end may start or end on: { id, key, ci, s, z, cost }. With a height: those within FLOOR_Z (else
-- the nearest, dearer); without one (the player: the game gives no height): the ground a player reaches (F_REACH), on
-- one nearest the shipped ground's height (Data/Heights.lua) where floors lie over each other. `swimming` (the start,
-- Nav.Swimming: the game says the player swims): the water's surfaces there first.
WG.CAVE_UNDER_Z = 6 -- yards: an indoors start (the game says so: opts.indoors) takes a floor this far under the ground
-- (item 106, 1.4.1, SPF parity: on a pier or a dock, not swimming, the dry floor over the water. Menethil's and Booty
-- Bay's docks: the deck 5-6 yd over the water's surface, the shipped ground the sea's bottom 11-30 yd under it, and the
-- floor nearest the ground was the water's: the walk began with a swim from under the pier)
WG.WADE_Z = 2 -- yards: a dry surface this far under the water's surface is its bottom, swum over (DrySplit)
-- (item 123, 1.4.1: Booty Bay's plank up out of the water, its cell's surface 2.5 yd under the water's top: Kooki3z
-- standing on its foot in the water, not swimming, was put on the deck 15 yd over him and routed along it, "Make a
-- U-turn onto the road", "Above you, 26 yd up". A surface under the water's top by up to WADE_STAND_Z that stands
-- WADE_OVER_GROUND or more over the shipped ground (the sea's bottom: so a model's, a plank's or a ramp's, not the
-- bottom) is one a player not swimming stands on in the water: dry, and its water a start as near (Ends))
WG.WADE_STAND_Z = 3.5
WG.WADE_OVER_GROUND = 3
-- The surfaces of `list` ({ z, f }) a player who isn't swimming stands on: those neither the water's (F_SWIM) nor under
-- it by more than WADE_Z (or by up to WADE_STAND_Z over `ground`, the shipped ground's height there, when given); the
-- rest second. With no water among them, or nothing dry, `list` itself. Third: the water's top.
function WG.DrySplit(list, ground)
  local top
  for _, f in ipairs(list) do
    if f.f and Bit(f.f, F_SWIM) and (not top or f.z > top) then top = f.z end
  end
  if not top then return list, nil end
  local dry, wet = {}, {}
  for _, f in ipairs(list) do
    local under = f.z < top - WG.WADE_Z
    if under and ground and f.z >= top - WG.WADE_STAND_Z and f.z >= ground + WG.WADE_OVER_GROUND then under = false end
    if (f.f and Bit(f.f, F_SWIM)) or under then wet[#wet + 1] = f else dry[#dry + 1] = f end
  end
  if not dry[1] then return list, nil end
  return dry, wet, top
end
-- Whether the cell at (x, y) has surfaces in a tile decoded already (Nav's status updates look only there: no load).
function WG.Decoded(c, x, y)
  local key, ci = CellKey(c, floor(x / c.cell), floor(y / c.cell))
  local t = key and c.tiles[key]
  return t and Count(t, ci) > 0 or false
end
-- The start's floor candidates in `opts` (opts.zs, Nav.GridCandidates) when (sx, sy) is the spot they were followed at
-- (zs.x, zs.y; within ZS_YD): a walk from elsewhere in the same leg (a building's door, a city's edge) not.
WG.ZS_YD = 3
function WG.StartZs(opts, sx, sy)
  local zs = opts and opts.zs
  if not (zs and zs[1] and zs.x and Dist(sx, sy, zs.x, zs.y) <= WG.ZS_YD) then return nil end
  return zs
end
-- `zs` (no height, Nav.GridCandidates: the floors the player may be on, followed and still more than one): the
-- surfaces on each of them, at their yards alone, so the search keeps the cheapest.
local function Ends(c, x, y, z, swimming, indoors, zs)
  local all = WG.SurfacesAt(c, x, y, z)
  local out = {}
  -- (swimming: the water's surfaces there, with a height too: the lower deck 4 yd over Booty Bay's water is within
  -- FLOOR_Z of its top, and a walk from under it began up on it, item 123)
  if swimming and (z or not (zs and zs[1])) then
    for _, f in ipairs(all) do
      if Bit(f.f, F_SWIM) then
        f.cost = Dist(x, y, f.x, f.y)
        out[#out + 1] = f
      end
    end
    if out[1] then return out end
  end
  if not z and zs and zs[1] then
    for _, f in ipairs(all) do
      for _, cz in ipairs(zs) do
        if abs(f.z - cz) <= WG.FLOOR_Z then
          f.cost = Dist(x, y, f.x, f.y)
          out[#out + 1] = f
          break
        end
      end
    end
    if out[1] then return out end
  end
  if z then
    -- (none of the cell's own on that floor: the neighbor cells' surfaces on it first (a tower's top whose cell's
    -- middle is its roof or the shaft: Freewind Post's east lift tower, whose top cell has only the foot and a roof, and
    -- the walk started down at the foot), then the cell's nearest, dearer)
    if not (all[1] and abs(all[1].z - z) <= WG.FLOOR_Z) then
      local gx, gy = floor(x / c.cell), floor(y / c.cell)
      for di = -1, 1 do
        for dj = -1, 1 do
          local key, ci = CellKey(c, gx + di, gy + dj)
          local t = (di ~= 0 or dj ~= 0) and key and WG.Tile(c, key)
          local n = t and Count(t, ci) or 0
          local f0 = n > 0 and First(t, ci)
          for k = 0, n - 1 do
            local s = f0 + k
            local sz = Z(c, t, s)
            if abs(sz - z) <= WG.FLOOR_Z then
              local px, py = Pt(c, t, s, ci)
              out[#out + 1] = { id = key * SHIFT + s, key = key, ci = ci, s = s, z = sz, x = px, y = py, f = Flags(t, s),
                                cost = Dist(x, y, px, py) + abs(sz - z) }
            end
          end
        end
      end
      if out[1] then return out end
    end
    for _, f in ipairs(all) do
      local dz = abs(f.z - z)
      if dz <= WG.FLOOR_Z or not out[1] then
        f.cost = Dist(x, y, f.x, f.y) + max(0, dz - WG.FLOOR_Z) * WG.Z_COST
        out[#out + 1] = f
      end
    end
    return out
  end
  local pick = {}
  if swimming then
    for _, f in ipairs(all) do if Bit(f.f, F_SWIM) then pick[#pick + 1] = f end end
    if pick[1] then
      for _, f in ipairs(pick) do f.cost = Dist(x, y, f.x, f.y) end
      return pick
    end
  end
  for _, f in ipairs(all) do if Bit(f.f, F_REACH) then pick[#pick + 1] = f end end
  if not pick[1] then pick = all end
  -- (not swimming, outdoors: the dry floors over the water first, a pier's deck; the water's after the ground's pick,
  -- dearer)
  local wet, top
  local GS = ns.Ground and ns.Ground.Sample
  if not swimming and not indoors then pick, wet, top = WG.DrySplit(pick, GS and GS(c.cont, x, y)) end
  -- (no height: the ground's, Data/Heights.lua's, picks among floors over floors; else every one, as the city grid)
  local gz = #pick > 1 and GS and GS(c.cont, x, y)
  local others
  if gz and indoors then
    -- (indoors with floors over floors: a cave under the hill, a building's floor under the ground's; as the Router's
    -- CaveDown takes IsIndoors: the floor under the ground nearest it)
    local under = {}
    for _, f in ipairs(pick) do if f.z < gz - WG.CAVE_UNDER_Z then under[#under + 1] = f end end
    if under[1] then
      table.sort(under, function(p, q) return p.z > q.z end)
      pick, gz = { under[1] }, nil
    end
  end
  if gz then
    -- (the nearest the ground's height, and any other as near: two pieces of one cell's floor a fence apart, the
    -- nearest alone a corner of six cells shut in, and the leg fell back to the Router's straight line through the
    -- keep's wall to Bernie Heisten; Nethergarde Keep 2026-11-22)
    table.sort(pick, function(p, q) return abs(p.z - gz) < abs(q.z - gz) end)
    local keep, d0 = {}, abs(pick[1].z - gz)
    others = {}
    for _, f in ipairs(pick) do
      if abs(f.z - gz) <= d0 + WG.SAME_FLOOR_Z then keep[#keep + 1] = f else others[#others + 1] = f end
    end
    pick = keep
    -- (the cell's other reached floors too, dearer by OTHER_FLOOR_YD: the ground's height is the top of an overhang
    -- where a road runs under it, and the top may have no way at all. North of Dun Algaz's tunnel the gorge's road is
    -- 70 yd under the mountain's top, and a stop on it ended up there: no way; 2026-11-22)
  end
  for _, f in ipairs(pick) do
    f.cost = Dist(x, y, f.x, f.y)
    out[#out + 1] = f
  end
  for _, f in ipairs(others or {}) do -- (after the ground's: out[1] stays the floor a spot is taken on)
    f.cost = Dist(x, y, f.x, f.y) + WG.OTHER_FLOOR_YD
    out[#out + 1] = f
  end
  -- (standing in the water on a plank's or a ramp's foot under its top, item 123: the water's as near as it, the way
  -- out from there is the swim's; the decks over it dearer)
  local wading = top and pick[1] and pick[1].z < top
  for _, f in ipairs(wet or {}) do
    f.cost = Dist(x, y, f.x, f.y) + ((wading and Bit(f.f, F_SWIM)) and 0 or WG.OTHER_FLOOR_YD)
    out[#out + 1] = f
  end
  return out
end
-- (never across a model wall: a spot by Red Cloud Mesa's palisade whose cell's surface has its point out past it on the
-- rim took that surface, and the route's first piece went through the palisade, item 78. The surfaces across one left
-- out; none left, the neighbor cells' on this side)
local EndsAll = Ends
Ends = function(c, x, y, z, swimming, indoors, zs)
  local out = EndsAll(c, x, y, z, swimming, indoors, zs)
  local P = ns.Passability
  if not (P and P.HasModelWalls and P.HasModelWalls(c.cont)) then return out end
  local keep = {}
  for _, f in ipairs(out) do
    if not P.CrossesModelWall(c.cont, x, y, f.x, f.y) then keep[#keep + 1] = f end
  end
  if keep[1] or not out[1] then return keep end
  local seen = {}
  for d = 1, 8 do
    local qx, qy = x + DX[d] * c.cell, y + DY[d] * c.cell
    if not P.CrossesModelWall(c.cont, x, y, qx, qy) then
      for _, f in ipairs(EndsAll(c, qx, qy, z, swimming, indoors, zs)) do
        if not seen[f.id] and not P.CrossesModelWall(c.cont, x, y, f.x, f.y) then
          seen[f.id] = true
          f.cost = (f.cost or 0) + Dist(x, y, qx, qy)
          keep[#keep + 1] = f
        end
      end
    end
  end
  return keep
end
WG.Ends = Ends

---------------------------------------------------------------------------------------------------- the costs
-- The Router's routing considerations for one search (asked 2026-11-22: "the opposing faction avoidance, swimming logic,
-- everything else we have in current routing considerations"), with its own constants and functions:
-- - the other faction's guards (Data/Hostile.lua; option avoidHostile, Router.HostileSide): a yard within their reach
--   costs HOSTILE_FACTOR (the towns the leg starts or ends in not, Router.HostileTownsNear), the light ones
--   HOSTILE_LIGHT_FACTOR (not within LIGHT_END_YD of the ends, Router.SetLightEnds);
-- - zones too high (option avoidHighZones, Router.RedZones): a yard in one costs LEVEL_FACTOR (not the start's and the
--   stop's zones), a step along road ground Router.RedFactor's (LEVEL_ROAD_FACTOR within LEVEL_ROAD_MAX levels: item
--   135b); with the straight line through one, a yard swum as much (RouteOne's SwimDetour: the way round them isn't a
--   long swim);
-- - swimming: Passability.SwimCost (Allow swimming off and a swim removed: AVOID_SWIM_COST; water walking: its own);
--   the water banned for the trip (Passability.SwimBanned) closed;
-- - the player's own walls (Passability.CrossesWall, while they have any: Passability.DrawnWalls) cut the links across
--   them; their erase strokes over walls (WALL_UNDER_YD) open the links the bake cut there;
-- - the player's own roads (not yet in the data; Router.ExpandTracks): road ground; their "remove" strokes take the
--   road ground off within Router.TRACK_REMOVE_YD;
-- - drops off ledges (one-way links down): none bigger than the player's safe drop (opts.maxDrop, else
--   Nav.SafeDrop), each DROP_COST yards more, as the Router's.
-- Each surface's extra a yard (guards, zones) worked out once a search and kept in `f`.
local SlopeDrop -- (below, by CostKey)
function WG.Costs(c, sx, sy, tx, ty, opts)
  local Rt, P, N = R(), ns.Passability, ns.Nav
  local cont = c.cont
  local x = { cont = cont, f = {} }
  x.side = Rt.HostileSide and Rt.HostileSide() or nil
  if x.side then
    x.exempt = Rt.EndsExempt and Rt.EndsExempt(cont, x.side, sx, sy, tx, ty) or nil -- (items 142, 130)
    x.light = Rt.HOSTILE_LIGHT and Rt.HOSTILE_LIGHT[x.side]
    -- (No to "Take it?": their ground far dearer, REFUSED_FACTOR, so the way round is taken wherever there's one, however
    -- long; shut, a start or stop by a camp had no way at all. Item 63b)
    x.block = WG.GuardsRefused() or nil
    if Rt.SetLightEnds then Rt.SetLightEnds(sx, sy, tx, ty) end
  end
  -- (the zones too high, weighed dearly so the way goes round them; not once the player said yes to them for this trip,
  -- Nav's AskRed (N.redOk.all): item 38, the Barrens to Un'Goro at level 25, Tanaris weighed at the level factor after
  -- his yes, the search flooded the Barrens and Thousand Needles first, hundreds of thousands of nodes)
  local N0 = ns.Nav
  local said = N0 and N0.redOk and N0.redOk.all
  x.red = not (opts and opts.redFree) and not said and Rt.RedZones and Rt.RedZones() or nil
  if x.red then x.redExempt = { [Rt.ZoneAt(cont, sx, sy)] = true, [Rt.ZoneAt(cont, tx, ty)] = true } end
  x.swim = WG.SwimWeight(c)
  -- (the stop's own swim avoided, Nav.AvoidLegSwim: this leg's water at the avoided swim's cost)
  if opts and opts.noSwim and P then x.swim = math.max(x.swim, P.AVOID_SWIM_COST or 10) end
  if x.red and x.swim > 1 then
    local through = false
    for z, yd in pairs(Rt.ZoneYards(cont, sx, sy, tx, ty)) do
      if yd > 0 and x.red[z] and not x.redExempt[z] then through = true break end
    end
    if through then x.swim = max(x.swim, Rt.LEVEL_FACTOR) end
  end
  x.bans = P and P.AnySwimBans and P.AnySwimBans(cont) or false
  -- (Options > Routing's Road tolerance, Router.RoadFactor: the roads' preference, 1 / road a yard off them, scaled as
  -- the Router's road-keeping factors are; at 0 the data's own)
  x.road = Rt.RoadFactor and 1 / Rt.RoadFactor(1 / c.road) or c.road
  -- (below 0, the roads kept as the Router's own walks keep them: its walk straight there off the roads,
  -- ROAD_DIRECT_PENALTY, scaled up to 5 times its extra at -10; a yard of road ground then about a sixth of one off it.
  -- Kooki3z 2026-11-22 at Nethergarde Keep, -10: the grid's way still hugged the keep's walls, not the canyon's road)
  local D = Rt.ROAD_DIRECT_PENALTY
  if Rt.RoadFactor and D and Rt.RoadFactor(D) > D then x.road = c.road / (1 + Rt.RoadFactor(D) - D) end
  -- (never cheaper than ROAD_PRICE_MIN of a yard off them, at -10 too: a road buys a detour of at most 1 / it over the
  -- open ground. Item 83, Kooki3z at -10 in the Barrens: the road's yard a sixth of one off it took the route north round
  -- the hills past the stop and back, twice the open way, and its search flooded, the heuristic's yard that cheap)
  x.road = max(x.road, WG.ROAD_PRICE_MIN)
  -- (never dearer than ROAD_PRICE_TOP: a small road bonus even at "Cut across" (+9 and +10; up to +8 as before), so a
  -- road that runs the trip's way is still taken there, joined late and shallow. Item 57, Kooki3z at +10 in the Barrens:
  -- the line ran across the open ground beside the road the whole way, joining it only at the stop)
  x.road = min(x.road, WG.ROAD_PRICE_TOP)
  x.maxDrop = opts and opts.maxDrop or (N and N.SafeDrop and N.SafeDrop()) or 0
  x.slopeDrop = SlopeDrop(opts, x.maxDrop)
  -- (the jumps avoided on this trip, Nav.AvoidJump: no drop from within reach of one's top)
  x.jumpBanned = N and N.jumpBans and N.jumpBans[1] and N.JumpBanned or nil
  x.walls = P and P.DrawnWalls and P.DrawnWalls(cont) or false
  -- (the lines drawn over the grid's way, its string pulling (WG.Pull, WG.Straighten), never across a wall, the shipped
  -- ones too: the bake cuts the links across them, but a line pulled past a gate's post cut its corner through the
  -- palisade; the coverage sweep, bake8: 71 stops, Splintertree Post's, Hammerfall's, Brill's)
  x.lineWalls = P and P.CrossesWall and true or false
  x.any = x.side ~= nil or x.red ~= nil
  -- (the player's own roads, erasers and remove strokes not yet in the data: by cell)
  local tracks = ns.db and ns.db.tracks
  if tracks and tracks[1] then
    local shipped = ns.RoadTracksIn or {}
    local list = Rt.ExpandTracks and Rt.ExpandTracks(tracks) or tracks
    local cell = c.cell
    local function Mark(set, pts, reach)
      local pad = math.ceil(reach / cell)
      for i = 1, #pts - 3, 2 do
        local ax, ay, bx, by = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
        local m = max(1, math.ceil(Dist(ax, ay, bx, by) / (cell / 3)))
        for q = 0, m do
          local px, py = ax + (bx - ax) * q / m, ay + (by - ay) * q / m
          local gx, gy = floor(px / cell), floor(py / cell)
          for di = -pad, pad do
            for dj = -pad, pad do
              local cx, cy = (gx + di + 0.5) * cell, (gy + dj + 0.5) * cell
              if pad == 0 or Dist(px, py, cx, cy) <= reach + cell * 0.71 then set[(gx + di) * 65536 + gy + dj] = true end
            end
          end
        end
      end
    end
    for _, t in ipairs(list) do
      if t.continent == cont and t.pts and #t.pts >= 4 and (t.shipped or not shipped[t.time or -1]) then
        if t.op == "unwall" then
          x.erased = x.erased or {}
          Mark(x.erased, t.pts, P and P.WALL_UNDER_YD or 12)
        elseif t.op == "remove" then
          x.unroadCells = x.unroadCells or {}
          Mark(x.unroadCells, t.pts, Rt.TRACK_REMOVE_YD or 12)
        elseif t.op ~= "wall" then
          x.roadCells = x.roadCells or {}
          Mark(x.roadCells, t.pts, WG.ROAD_HALF_YD)
          -- (the world grid's own: a city grid's costs, CityGrid's CG.Costs, come here with a stand-in { cont, cell,
          -- road, swim }, no tiles to put the links on; OwnLinks on it errored in the route's background job, the error
          -- swallowed and the job queued again every frame: "Working out the route..." for ever in Ironforge with a
          -- recorded road by the leg, 2026-11-22)
          if c.per and c.tiles and WG.NearLeg(t.pts, sx, sy, tx, ty) then
            x.own = x.own or {}
            for _, L in ipairs(WG.OwnLinks(c, t)) do
              local o = x.own[L.a]
              if not o then o = {} x.own[L.a] = o end
              o[#o + 1] = L
            end
          end
        end
      end
    end
  end
  return x
end

-- The player's own walks and roads not yet in the data as the bake's recorded links (worldbake.mark_recorded, Kooki3z
-- 2026-11-22: drawn and recorded roads are truth): each point on its cell's surface nearest its height (the road's own
-- heights, `zs`; none, as a recording has: the surface nearest the one before within REC_FOLLOW_Z, and a yard more for
-- each yard since one was, the heights between straight, the first on the ground's), and where the grid has no link between two surfaces one after
-- another along it, the road's stretch is a link at its own heights, its yards at the road's cost (a step of its own
-- heights falling REC_DROP_DZ more than its yards: one way down). Kept by the track's points (WG.own), only those near the
-- leg worked out (NearLeg: no far region loaded for them).
WG.REC_FOLLOW_Z, WG.REC_ON_Z, WG.REC_DROP_DZ, WG.REC_STEP, WG.REC_NEAR_YD = 3, 2.5, 1.5, 1, 400
WG.own = setmetatable({}, { __mode = "k" })
function WG.NearLeg(pts, sx, sy, tx, ty)
  local x0, x1 = min(sx, tx) - WG.REC_NEAR_YD, max(sx, tx) + WG.REC_NEAR_YD
  local y0, y1 = min(sy, ty) - WG.REC_NEAR_YD, max(sy, ty) + WG.REC_NEAR_YD
  for i = 1, #pts - 1, 2 do
    if pts[i] >= x0 and pts[i] <= x1 and pts[i + 1] >= y0 and pts[i + 1] <= y1 then return true end
  end
  return false
end
local function CellSurfaces(c, x, y)
  local key, ci = CellKey(c, floor(x / c.cell), floor(y / c.cell))
  local t = key and WG.Tile(c, key)
  if not t then return nil end
  return t, key, ci, Count(t, ci), First(t, ci)
end
function WG.OwnLinks(c, t)
  local per = WG.own[t]
  if per and per.cont == c.cont and per.n == #t.pts and per.d == c.d then return per.links end
  local Rt = R()
  local pts, zs = t.pts, type(t.zs) == "table" and #t.zs == #t.pts / 2 and t.zs or nil
  local samples = {}
  local prev, lost, gap = nil, 0, nil
  local GS = ns.Ground and ns.Ground.Sample
  for i = 1, #pts - 3, 2 do
    local ax, ay, bx, by = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
    local m = max(1, floor(Dist(ax, ay, bx, by) / WG.REC_STEP))
    local last = i + 3 >= #pts
    -- (the road's own step between two of its points: a drop down (-1) or up (1); the grid's guessed heights none)
    local jump = 0
    if zs then
      local dz = zs[(i + 3) / 2] - zs[(i + 1) / 2]
      if abs(dz) > WG.REC_DROP_DZ + Dist(ax, ay, bx, by) then jump = dz > 0 and 1 or -1 end
    end
    for k = 0, last and m or m - 1 do
      if Rt.Breathe then Rt.Breathe(#samples + 1, 100) end
      local f = k / m
      local x, y = ax + (bx - ax) * f, ay + (by - ay) * f
      local z
      if zs then
        z = zs[(i + 1) / 2] + (zs[(i + 3) / 2] - zs[(i + 1) / 2]) * f
        gap, lost = nil, 0
      else
        local tt, _, _, n, f0 = CellSurfaces(c, x, y)
        local best, bd
        if tt and n > 0 then
          for q = 0, n - 1 do
            local sz = Z(c, tt, f0 + q)
            local d = prev and abs(sz - prev) or (GS and abs(sz - (GS(c.cont, x, y) or sz)) or 0)
            if not bd or d < bd then best, bd = sz, d end
          end
        end
        if best and (not prev or bd <= WG.REC_FOLLOW_Z + lost) then
          -- (a surface near again after a run with none: the heights between straight from the last one's)
          if gap and gap > 1 then
            local z0, n = samples[gap - 1][3], #samples - gap + 2
            for j = gap, #samples do samples[j][3] = z0 + (best - z0) * (j - gap + 1) / n end
          end
          z, lost, gap = best, 0, nil
        else
          z, lost = prev or best or 0, lost + WG.REC_STEP
          gap = gap or #samples + 1
        end
      end
      prev = z
      samples[#samples + 1] = { x, y, z, jump }
    end
  end
  -- (each sample's surface: its cell's nearest its height within REC_ON_Z)
  local on = {}
  for q, p in ipairs(samples) do
    local tt, key, ci, n, f0 = CellSurfaces(c, p[1], p[2])
    if tt and n > 0 then
      local best, bd
      for k = 0, n - 1 do
        local d = abs(Z(c, tt, f0 + k) - p[3])
        if d <= WG.REC_ON_Z and (not bd or d < bd) then best, bd = k, d end
      end
      if best then on[q] = { id = key * SHIFT + f0 + best, key = key, ci = ci, t = tt, s = f0 + best } end
    end
  end
  local function Linked(a, b)
    for d = 1, 8 do
      local kk = Link(a.t, a.s, d)
      if kk > 0 then
        local nkey, nci = WG.Step(c, a.key, a.ci, d)
        local nt = nkey and WG.Tile(c, nkey)
        if nt and nkey * SHIFT + First(nt, nci) + kk - 1 == b.id then return true end
      end
    end
    for _, li in ipairs(c.out[a.id] or {}) do
      if c.links[li].b == b.id then return true end
    end
    return false
  end
  local links, last = {}, nil
  for q = 1, #samples do
    local b = on[q]
    if b then
      local a = last and on[last]
      if a and a.id ~= b.id then
        local fwd, back = not Linked(a, b), not Linked(b, a)
        if fwd or back then
          local yd, up, down, lp = 0, false, false, {}
          for r = last, q do
            local p = samples[r]
            if r > last then
              local o = samples[r - 1]
              local d, dz = Dist(o[1], o[2], p[1], p[2]), p[3] - o[3]
              yd = yd + sqrt(d * d + dz * dz)
              if o[4] < 0 then down = true elseif o[4] > 0 then up = true end
            end
            lp[#lp + 1] = { p[1], p[2], p[3] }
          end
          local rev = {}
          for r = #lp, 1, -1 do rev[#rev + 1] = lp[r] end
          local walk = (t.stairs or t.stair) and 6 or 0
          if fwd then links[#links + 1] = { a = a.id, b = b.id, bkey = b.key, yd = max(yd, 1), kind = down and 4 or walk, pts = lp, own = true } end
          if back and not down then links[#links + 1] = { a = b.id, b = a.id, bkey = a.key, yd = max(yd, 1), kind = up and 4 or walk, pts = rev, own = true } end
        end
      end
      last = q
    end
  end
  for n, L in ipairs(links) do L.n = n end
  WG.own[t] = { cont = c.cont, n = #t.pts, d = c.d, links = links }
  return links
end

-- A yard swum, in yards walked: the player's run speed over their swim speed (Nav.Speeds, Nav.SwimSpeed: items, Aquatic
-- Form), within SWIM_MIN to SWIM_MAX; water as fast as land (Nav.WaterFast: water walking): Passability's
-- WATER_FAST_COST; swimming left out (Allow swimming off, a removed swim): its AVOID_SWIM_COST. (Kooki3z 2026-11-22: "yes
-- use my current swim speed in the grid too"; the data's 1.5 was the base run over the base swim)
WG.SWIM_ENTER_YD = 20 -- (a swim's start: this many yards more, so a bridge or ford near it is walked instead)
WG.SWIM_MIN, WG.SWIM_MAX = 1.3, 3 -- (a yard swum never as cheap as one walked but with water walking: item 62)
function WG.SwimWeight(c)
  local P, N = ns.Passability, ns.Nav
  if P and P.avoidSwim then return P.AVOID_SWIM_COST or 10 end
  if P and P.waterFast then return P.WATER_FAST_COST or 1 end
  -- (run / swim from one reading on foot, Nav.SwimRatio; none yet: the data's)
  if N and N.Speeds then pcall(N.Speeds) end
  local ratio = N and N.SwimRatio and N.SwimRatio()
  if not ratio then return max(WG.SWIM_MIN, c and c.swim or 1.5) end
  return max(WG.SWIM_MIN, min(WG.SWIM_MAX, ratio))
end

-- (the cost context's key: a route searched with other costs is another route)
local CostKey
-- The drop limit on a steep slope's far drop (not a clean one, FAR_DROP_CLEAN_SLOPE): the Safe drop when the fall source
-- ready ends on landing (FallSpells.EndsOnLanding), else the drop limit as it is.
function SlopeDrop(opts, maxDrop)
  if opts and opts.slopeDrop then return opts.slopeDrop end
  local FS, N = ns.FallSpells, ns.Nav
  if not (FS and FS.EndsOnLanding and FS.EndsOnLanding() and N and N.PlainSafeDrop) then return maxDrop end
  return math.min(maxDrop, N.PlainSafeDrop())
end
function WG.CostKey(opts) return CostKey(opts) end
function CostKey(opts)
  local Rt, P, N = R(), ns.Passability, ns.Nav
  local side = Rt.HostileSide and Rt.HostileSide() or "-"
  if side ~= "-" and WG.GuardsRefused() then side = side .. "!" end -- (no way through them: item 63b)
  local lvl = "-"
  if Rt.RedZones and Rt.RedZones() and not (opts and opts.redFree) and not (N and N.redOk and N.redOk.all) then
    local ok, l = pcall(UnitLevel or error, "player")
    lvl = ok and tostring(l) or "?"
  end
  local swim = WG.SwimWeight()
  if opts and opts.noSwim then swim = math.max(swim, P and P.AVOID_SWIM_COST or 10) end
  local drop = opts and opts.maxDrop or (N and N.SafeDrop and N.SafeDrop()) or 0
  local slope = SlopeDrop(opts, drop)
  local tracks = ns.db and ns.db.tracks
  local st = ns.settings and ns.settings.gps
  -- (and the jumps avoided on this trip: Nav.jumpBanStamp, none 0)
  local bans = N and N.jumpBans and N.jumpBans[1] and N.jumpBanStamp or 0
  return string.format("%s|%s|%.2f|%d|%d|%s%s|%s|%d|%d", side, lvl, swim, drop == huge and 9999 or floor(drop),
    tracks and #tracks or 0, ((opts and opts.swimming) and "s" or "") .. ((Rt.ExpertJumper and Rt.ExpertJumper()) and "x" or ""),
    (opts and opts.indoors) and "i" or "",
    tostring(st and st.roadTolerance or 0), bans, slope == huge and 9999 or floor(slope))
end

-- The extra a yard at surface `id` (its point px, py): the guards' reach and zones too high (WG.Costs).
local function Extra(x, id, px, py)
  local v = x.f[id]
  if v then return v end
  v = 0
  local Rt = R()
  if x.side then
    if Rt.HostileAt(x.cont, px, py, x.side, x.exempt) then
      v = x.block and WG.REFUSED_FACTOR - 1 or Rt.HOSTILE_FACTOR - 1
    elseif x.light and not (Rt.NearLightEnd and Rt.NearLightEnd(px, py)) and Rt.HostileAt(x.cont, px, py, x.light) then
      v = Rt.HOSTILE_LIGHT_FACTOR - 1
    end
  end
  if x.red then
    local z = Rt.ZoneAt(x.cont, px, py)
    if x.red[z] and not x.redExempt[z] then
      v = v + Rt.LEVEL_FACTOR - 1
      -- (along road ground less, item 135b: RoadLess)
      local less = Rt.RedFactor and Rt.LEVEL_FACTOR - Rt.RedFactor(x.red, z, true) or 0
      if less > 0 then
        x.fr = x.fr or {}
        x.fr[id] = less
      end
    end
  end
  x.f[id] = v
  return v
end
WG.Extra = Extra
-- What a yard of surface `id` along road ground costs less than its Extra (a zone too high, within
-- Router.LEVEL_ROAD_MAX levels: Router.RedFactor's road price; item 135b). Its Extra worked out first. (WG.Search reads
-- x.fr itself: its upvalues are near Lua 5.1's 60.)
function WG.RoadLess(x, id) return x.fr and x.fr[id] or 0 end

-- Whether a step from surface s (tile t, cell ci) in direction d onto s2 (tile nt) is a drop off a ledge: down
-- DROP_Z or more and not linked back up.
local function Drop(t, s, ci, d, nt, s2, dz)
  if dz > -WG.DROP_Z then return false end
  local back = Link(nt, s2, OPP[d])
  return back ~= s - First(t, ci) + 1
end
WG.Drop = Drop

-- (a step's road ground: the data's, or the player's own road there, less their remove strokes)
local function RoadCell(x, c, t, ci)
  local gk = (t.gx0 + floor(ci / c.per)) * 65536 + t.gy0 + ci % c.per
  if x.unroadCells and x.unroadCells[gk] then return false, true end
  return x.roadCells and x.roadCells[gk] or false, false
end

---------------------------------------------------------------------------------------------------- the search
-- (a binary heap in two arrays, the least key first. The entry on its way up or down is held and written once where
-- it stops, the same comparisons and the same order out as swapping it level by level: study/route-perf, 2026-11-25)
local function Push(hk, hv, k, v)
  local i = #hk + 1
  while i > 1 do
    local p = (i - i % 2) / 2
    local pk = hk[p]
    if pk <= k then break end
    hk[i], hv[i] = pk, hv[p]
    i = p
  end
  hk[i], hv[i] = k, v
end
local function Pop(hk, hv)
  local n = #hk
  local k0, v0 = hk[1], hv[1]
  local mk, mv = hk[n], hv[n]
  hk[n], hv[n] = nil, nil
  n = n - 1
  if n == 0 then return k0, v0 end
  local i = 1
  while true do
    local l = 2 * i
    if l > n then break end
    local s, sk = i, mk
    local lk = hk[l]
    if lk < sk then s, sk = l, lk end
    if l < n then
      local rk = hk[l + 1]
      if rk < sk then s, sk = l + 1, rk end
    end
    if s == i then break end
    hk[i], hv[i] = sk, hv[s]
    i = s
  end
  hk[i], hv[i] = mk, mv
  return k0, v0
end
WG.HeapPush, WG.HeapPop = Push, Pop -- (tests: the order out)

-- The neighbor cell of (key, ci) in direction d: its key and ci (another tile's across a tile's side), or nil.
local function Step(c, key, ci, d)
  local per = c.per
  local a, b = floor(ci / per) + DX[d], ci % per + DY[d]
  if a >= 0 and a < per and b >= 0 and b < per then return key, a * per + b end
  local gx0, gy0 = Origin(c, key)
  return CellKey(c, gx0 + a, gy0 + b)
end
WG.Step = Step

-- (an erase stroke's link: the neighbor cell's surface nearest in height within the grid's climb, its index 1-7, or 0)
local function ErasedLink(c, x, t, s, ci, nt, nci, d, zs)
  local gk = (t.gx0 + floor(ci / c.per)) * 65536 + t.gy0 + ci % c.per
  if not x.erased[gk] then return 0 end
  local n = Count(nt, nci)
  if n == 0 then return 0 end
  local f = First(nt, nci)
  local step = d > 4 and c.cell * sqrt(2) or c.cell
  local lim = step * WG.ERASE_SLOPE + WG.ERASE_CLIMB
  local best, bd = 0, nil
  for k = 0, n - 1 do
    local dz = abs(Z(c, nt, f + k) - zs)
    if dz <= lim and (not bd or dz < bd) then best, bd = k + 1, dz end
  end
  return best
end

-- A drop off a sheer cliff over empty cells (Kooki3z 2026-11-23: Tanaris' west rim to Un'Goro, 188 yd down past ~45 yd
-- of cliff face no floor covers; Skywatcher Plateau's east edge, 130 yd past ~20 yd). The walked links join a cell's 8
-- neighbors only, so a fall past an empty cell was no link at all, whatever the drop limit: the search flooded Tanaris
-- for a way down (seconds of background, "Consulting the Tinker Town schematics..." for over a minute) and settled on
-- the far southern ramp. From a surface with no link in direction d, the cells on along d up to FAR_DROP_CELLS: the
-- first with a floor under the edge's height (FAR_DROP_CLEAR_Z over it) ends the look; a far drop when that floor is
-- FAR_DROP_MIN or more down and at least FAR_DROP_STEEP yards down a yard out, the terrain between falling all the way
-- (a face too steep to walk, slid or fallen down: Tanaris' drops 26 yd a cell; never a wall up or a ridge between), and
-- the landing not under the ground (a cave's: entered by its mouths). Kooki3z's rule (2026-11-23, the Barrens): "too
-- steep only blocks going UP"; down a too-steep slope is a slide or a fall, a drop of its height: a plain walk within
-- the Safe drop, deeper a spell jump (the player's x.maxDrop gates it as any drop's). One way, down only, and never
-- across a wall (Passability.CrossesWall: the shipped ones, the player's; a cliff's wall walked down). From
-- FAR_DROP_MIN (Kooki3z 2026-11-24, Stonetalon's Webwinder Path at Safe drop 60: "its not even that far down", a face
-- too steep to walk and under 40 yd got neither a walk nor a drop). Each surface's once (c.far, kept till WG.Reset):
-- { { id2, ci, x, y, z }, ... } or false.
WG.FAR_DROP_MIN = 8 -- (a cell out at FAR_DROP_STEEP)
WG.FAR_DROP_CELLS = 12 -- (100 yd)
WG.FAR_DROP_STEEP = 1 -- (45 degrees on the whole; the walked grid's own steepest is 55)
WG.FAR_DROP_CLEAR_Z = 2.5 -- (worldgrid.DROP_CLEAR_Z)
WG.FAR_DROP_WALL_Z = 3 -- yards the terrain between may rise over the edge, or over the cell before
WG.FAR_DROP_UNDER_Z = 6 -- (worldbake.UNDER_GROUND_Z)
-- A slope walked down, not a drop (Kooki3z 2026-11-23, a grassy hillside by Bluefen: "Use Walk on Air, then jump
-- down", 41 yd down, and he walked it): no step of the terrain between, cell to cell, steeper than FAR_DROP_WALK_SLOPE.
-- The mesh leaves a face steeper than its walk slope empty, but down it the player stays on the ground. Such an entry
-- is `walk`: one way down, a plain walk (no jump step, no spell, no drop limit). A drop only where the player leaves
-- the ground: a step past it (Tanaris' rim, 26 yd a cell).
WG.FAR_DROP_WALK_SLOPE = math.tan(math.rad(50))
-- ... judged by the terrain's own slope at each cell between (its steepest way down there, TerrainSlope), not the
-- way's: a diagonal across a steep face has gentle steps along it, but the face is too steep to stand on and the player
-- slides (Kooki3z 2026-11-24, Bluefen's ridge: "Straight, then arrive", no jump, down a face that's clearly one). And a
-- drop leaves the edge down the fall line: its direction within FAR_DROP_FALL_LINE of the terrain's way down (the
-- shortest fall, as a swim crosses water), not slantwise along the face.
WG.FAR_DROP_FALL_LINE = math.cos(math.rad(50))
WG.SLOPE_H = 4 -- yards either side the terrain's slope is sampled at
local function TerrainSlope(cont, x, y)
  local GS = ns.Ground and ns.Ground.Sample
  if not GS then return nil end
  local h = WG.SLOPE_H
  local a, b, c2, d = GS(cont, x + h, y), GS(cont, x - h, y), GS(cont, x, y + h), GS(cont, x, y - h)
  if not (a and b and c2 and d) then return nil end
  local gx, gy = (a - b) / (2 * h), (c2 - d) / (2 * h)
  return sqrt(gx * gx + gy * gy), gx, gy
end
WG.TerrainSlope = TerrainSlope
-- A clean drop, the face steeper than a glide's own way down (about 45 degrees: as many yards down a second as on) by a
-- margin: 55 degrees or more from the edge to the foot on the whole (Tanaris' rim 65, Skywatcher Plateau's 61, Northwatch
-- Hold's ridge 60; the Barrens' hillside 48, a slope). A glide that ends on landing counts only for these (FallSpells.
-- EndsOnLanding: x.slopeDrop, the Safe drop, on the others).
WG.FAR_DROP_CLEAN_SLOPE = math.tan(math.rad(55))
-- A fall from the ground into the ground: its top on the terrain (not UNDER_Z under it) and its landing UNDER_Z or more
-- under the terrain there, a cave's or a tunnel's floor through the rock over it. Caves are entered by their mouths,
-- walked (Kooki3z 2026-11-23: "all cave routes should only be accessible through an entrance"); the bake cuts such links
-- for the caves it knows (worldbake.cut_ceiling_drops, Data/Caves.lua), this at search time for any: the Wailing
-- Caverns' hills, a baked drop from 180 straight down to 26 in the caverns, the terrain 168 over it (2026-11-24). Only
-- falls of INTO_GROUND_MIN or more are looked at (a ledge's step isn't).
WG.INTO_GROUND_MIN = 20
WG.INTO_GROUND_TOP_Z = 12 -- (a top this near the terrain is on it: the coarse heights, 16.7 yd samples, run 8 yd over a
-- steep hill's floor; the Wailing Caverns' hill, 209 under 217)
local function IntoGround(cont, sx, sy, zs, px, py, z2)
  local GS = ns.Ground and ns.Ground.Sample
  if not GS or zs - z2 < WG.INTO_GROUND_MIN then return false end
  local gl = GS(cont, px, py)
  if not (gl and z2 < gl - WG.FAR_DROP_UNDER_Z) then return false end
  local gt = GS(cont, sx, sy)
  return not (gt and zs < gt - WG.INTO_GROUND_TOP_Z) -- (a fall inside the cave, its top under the ground too: fine)
end
WG.IntoGround = IntoGround
-- (its cache, c.far, in two generations of at most FAR_CACHE_MAX surfaces: past it the current one becomes the old one
-- and a new one starts, a surface found in the old one moved back. Item 59, Kooki3z 2026-11-24 on the live client,
-- "AddOn Memory 551 MB (374 MB AzerothGPS)": kept for the session, it held 307k surfaces, 24 MB, after six trips)
WG.FAR_CACHE_MAX = 40000
local function FarDrops(c, t, s, key, ci, zs, sx, sy)
  c.far = c.far or {}
  local id = key * SHIFT + s
  local got = c.far[id]
  if got ~= nil then return got end
  local old = c.farOld and c.farOld[id]
  if old ~= nil then
    c.far[id], c.farN = old, (c.farN or 0) + 1
    return old
  end
  local GS = ns.Ground and ns.Ground.Sample
  local out
  local walled = Bit(Flags(t, s), F_RIM_WALL)
  for d = 1, 8 do
    if not walled and Link(t, s, d) == 0 then
      local k2, c2 = key, ci
      local top = zs
      local prev, steep = zs, 0 -- (the terrain cell to cell: its steepest step down, and its own slope)
      local step = d > 4 and c.cell * sqrt(2) or c.cell
      local dl = d > 4 and sqrt(2) or 1
      for n = 1, WG.FAR_DROP_CELLS do
        k2, c2 = Step(c, k2, c2, d)
        local nt = k2 and WG.Tile(c, k2)
        if not nt then break end
        local cnt, f0 = Count(nt, c2), First(nt, c2)
        local best
        for q = cnt - 1, 0, -1 do
          if Z(c, nt, f0 + q) < zs + WG.FAR_DROP_CLEAR_Z then best = q break end
        end
        if best then
          local s2 = f0 + best
          local z2 = Z(c, nt, s2)
          local fall = zs - z2
          if n > 1 and fall >= WG.FAR_DROP_MIN then
            local px, py = Pt(c, nt, s2, c2)
            local gz = GS and GS(c.cont, px, py)
            if Dist(sx, sy, px, py) * WG.FAR_DROP_STEEP <= fall and not IntoGround(c.cont, sx, sy, zs, px, py, z2) then
              steep = max(steep, (prev - z2) / step)
              out = out or {}
              -- (a walk down only within the walk slope over its own length too, whatever the terrain's heights between
              -- say: item 40, Kooki3z 2026-11-24 west of Darkmist Cavern, "137 yd down" walked down a sheer rock face the
              -- heightmap reads gentler (the rock is the mesh's, not the terrain's). Steeper on the whole: a drop of
              -- its full height, a jump step, a spell or the way round past the Safe drop)
              local yd = Dist(sx, sy, px, py)
              local walk = steep <= WG.FAR_DROP_WALK_SLOPE and (WG.walkRuleOff or fall <= yd * WG.FAR_DROP_WALK_SLOPE)
              out[#out + 1] = { id2 = k2 * SHIFT + s2, ci = c2, x = px, y = py, z = z2,
                walk = walk or nil, steep = steep, over = fall / max(1, yd) }
            end
          end
          break
        end
        local cx, cy = sx + DX[d] * c.cell * n, sy + DY[d] * c.cell * n
        local gz = GS and GS(c.cont, cx, cy)
        -- (the ground rising past the edge: a wall, no drop this way; looked at before the slope's four samples, which
        -- change nothing then: study/route-perf, 2026-11-25)
        if gz and gz > top + WG.FAR_DROP_WALL_Z then break end
        local m, gx, gy = TerrainSlope(c.cont, cx, cy)
        if m then
          -- (the first cell out: down the fall line only, within FAR_DROP_FALL_LINE of the terrain's way down)
          if n == 1 and m > 0.3 and -(DX[d] * gx + DY[d] * gy) / (dl * m) < WG.FAR_DROP_FALL_LINE then break end
          steep = max(steep, m)
        end
        if gz then
          if gz > top + WG.FAR_DROP_WALL_Z then break end
          top = min(top, gz)
          steep = max(steep, (prev - gz) / step)
          prev = gz
        end
      end
    end
  end
  if (c.farN or 0) >= WG.FAR_CACHE_MAX then c.farOld, c.far, c.farN = c.far, {}, 0 end
  c.far[id], c.farN = out or false, (c.farN or 0) + 1
  return c.far[id]
end
WG.FarDrops = FarDrops

-- Whether link L (a road's, a baked drop's, a lift's: { pts = { {x, y, z}, ... } }) crosses a model wall
-- (Passability.CrossesModelWall); the answers kept on the grid c (c.walled, by the link table, weak).
function WG.WalledLinks(c)
  local P = ns.Passability
  local cache = c.walled
  if not cache then
    cache = setmetatable({}, { __mode = "k" })
    c.walled = cache
  end
  return function(L)
    local v = cache[L]
    if v == nil then
      v = P.PtsCrossModelWall(c.cont, L.pts, true)
      cache[L] = v
    end
    return v
  end
end

---------------------------------------------------------------------------------------- landmark distance fields
-- Item 33 (Kooki3z 2026-11-24, "yes, build the landmark (ALT) distance tables"): the search's heuristic was the straight
-- line, which a rim between badly underestimates (item 27: the no-spell way round Tanaris' rim flooded 62k nodes). Each
-- landmark's distance field, baked (app/azerothgps/worldalt.py, this file's WG.AltPrepare / WG.AltFlood on the shipped
-- tiles), shipped in the region folders (Alt.lua: AzerothGPS_WorldGridAlt, taken by WG.LoadRegion into c.alt[key]):
-- every surface's grid distance from the landmark over the moves a search can make, undirected (each link and road link
-- both ways, the far drops and slides reversed too, falls past ALT_FALL left out), each at its least cost as the search
-- weighs it (a link's walk and climb, the data's road where both ends are road ground, a road link's yards at the road's,
-- a fall's yards across); per ALT_BLOCK cells square, the least and the most of its surfaces'. A walk from s to t then
-- costs at least |d(L, t) - d(L, s)| whichever way it goes (triangle inequality; scaled down when Road tolerance makes
-- the road cheaper than the data's): the search's heuristic is the most of that over the landmarks and the straight
-- line's (WG.AltSearch), the bound not weighted by HEUR (a tight bound weighted lengthened routes). Only while the
-- search's falls stay within ALT_FALL (no spell's reach past it, no Expert jumper) and with no player's own roads or
-- erasers (links the fields don't know); otherwise the straight line as before.
WG.ALT_BLOCK, WG.ALT_FALL = 16, 60
WG.ALT_NONE = 262143 -- (a block no surface of reaches: no bound from it)
WG.ALT_REOPEN_YD, WG.ALT_REOPENS = 8, 5000 -- (a closed surface opened again only for a way this much cheaper, so many a search)
WG.ALT_SPAN_NONE = 262143 -- (a block's spread too wide to note: no bound from it)
local OPP = {}
for d = 1, 8 do
  for e = 1, 8 do
    if DX[e] == -DX[d] and DY[e] == -DY[d] then OPP[d] = e end
  end
end
-- (the bake's: every loaded tile's surfaces' cells, the far drops/slides both ways and the road links reversed)
function WG.AltPrepare(c, fallCap)
  fallCap = fallCap or WG.ALT_FALL
  local cellOf, rev, fwd = {}, {}, {}
  local function Add(list, a, w)
    list[#list + 1] = a
    list[#list + 1] = w
  end
  for _, L in ipairs(c.links) do
    local p0, p1 = L.pts[1], L.pts[#L.pts]
    local w = min(L.yd or huge, (p0 and p1) and Dist(p0[1], p0[2], p1[1], p1[2]) or 0) * c.road
    rev[L.b] = rev[L.b] or {}
    Add(rev[L.b], L.a, w)
  end
  local per = c.per
  for key in pairs(c.raw) do
    local t = WG.Tile(c, key)
    if t then
      for ci = 0, per * per - 1 do
        local cnt = Count(t, ci)
        if cnt > 0 then
          local f0 = First(t, ci)
          for q = 0, cnt - 1 do
            local s = f0 + q
            local id = key * SHIFT + s
            cellOf[id] = ci
            local zs = Z(c, t, s)
            local sx, sy = Pt(c, t, s, ci)
            local fd = FarDrops(c, t, s, key, ci, zs, sx, sy)
            if fd then
              for _, e in ipairs(fd) do
                if e.walk or zs - e.z <= fallCap then
                  local w = Dist(sx, sy, e.x, e.y)
                  fwd[id] = fwd[id] or {}
                  Add(fwd[id], e.id2, w)
                  rev[e.id2] = rev[e.id2] or {}
                  Add(rev[e.id2], id, w)
                end
              end
            end
          end
        end
      end
    end
  end
  c.far, c.farOld, c.farN = nil, nil, 0 -- (its cache: the far drops are in fwd now)
  return { cellOf = cellOf, rev = rev, fwd = fwd }
end
-- (the bake's: the distances from `srcs` (ids) into `dist`, by the prepared moves)
function WG.AltFlood(c, prep, srcs, dist)
  local cellOf, rev, fwd = prep.cellOf, prep.rev, prep.fwd
  local cell = c.cell
  local diag = cell * sqrt(2)
  local hk, hv = {}, {}
  for _, id in ipairs(srcs) do
    dist[id] = 0
    Push(hk, hv, 0, id)
  end
  local function Relax(id2, nd)
    local old = dist[id2]
    if not old or nd < old then
      dist[id2] = nd
      Push(hk, hv, nd, id2)
    end
  end
  while hk[1] do
    local f, id = Pop(hk, hv)
    if f <= dist[id] then
      local key = floor(id / SHIFT)
      local s = id - key * SHIFT
      local ci = cellOf[id]
      local t = ci and WG.Tile(c, key)
      if t then
        local kin = s - First(t, ci) + 1
        local zs, roadA = Z(c, t, s), Bit(Flags(t, s), F_ROAD)
        -- (a link's least cost as the search's, either way: its walk with the climb, the data's road where both ends
        -- are road ground, water at a yard's (swimming costs more))
        local function W(step, nt, s2)
          local dz = Z(c, nt, s2) - zs
          local w = sqrt(step * step + dz * dz) + abs(dz) * WG.CLIMB_COST
          if roadA and Bit(Flags(nt, s2), F_ROAD) then w = w * c.road end
          return w
        end
        for d = 1, 8 do
          local step = d > 4 and diag or cell
          local nkey, nci = Step(c, key, ci, d)
          local nt = nkey and WG.Tile(c, nkey)
          if nt then
            local kk = Link(t, s, d)
            local f2 = First(nt, nci)
            if kk > 0 then Relax(nkey * SHIFT + f2 + kk - 1, f + W(step, nt, f2 + kk - 1)) end
            for q = 0, Count(nt, nci) - 1 do -- (and the links into it from there)
              if Link(nt, f2 + q, OPP[d]) == kin then Relax(nkey * SHIFT + f2 + q, f + W(step, nt, f2 + q)) end
            end
          end
        end
        local out = c.out[id]
        if out then
          for _, li in ipairs(out) do
            local L = c.links[li]
            local p0, p1 = L.pts[1], L.pts[#L.pts]
            Relax(L.b, f + min(L.yd or huge, (p0 and p1) and Dist(p0[1], p0[2], p1[1], p1[2]) or 0) * c.road)
          end
        end
        for _, list in ipairs({ rev[id] or false, fwd[id] or false }) do
          if list then
            for k = 1, #list, 2 do Relax(list[k], f + list[k + 1]) end
          end
        end
      end
    end
  end
  return dist
end
-- (the bake's: the fields reduced to blocks and written as each tile's string, landmark by landmark: per block the
-- least and the spread to the most (3 characters each), ALT_NONE / ALT_SPAN_NONE when none)
function WG.AltEncode(c, prep, fields)
  local per, B = c.per, WG.ALT_BLOCK
  local nb = per / B
  local lo, hi = {}, {}
  for id, ci in pairs(prep.cellOf) do
    local key = floor(id / SHIFT)
    local bi = floor(floor(ci / per) / B) * nb + floor((ci % per) / B)
    for l, dist in ipairs(fields) do
      local v = dist[id]
      if v then
        local k = (key * 64 + bi) * 16 + l
        if not lo[k] or v < lo[k] then lo[k] = v end
        if not hi[k] or v > hi[k] then hi[k] = v end
      end
    end
  end
  local out = {}
  for key in pairs(c.raw) do
    local parts = {}
    for l = 1, #fields do
      for bi = 0, nb * nb - 1 do
        local k = (key * 64 + bi) * 16 + l
        local a, b = lo[k], hi[k]
        local v = a and min(WG.ALT_NONE - 1, floor(a)) or WG.ALT_NONE
        local span = (a and b) and math.ceil(b) - v or WG.ALT_SPAN_NONE
        if span >= WG.ALT_SPAN_NONE then span = WG.ALT_SPAN_NONE end
        parts[#parts + 1] = CH[floor(v / 4096) + 1] .. CH[floor(v / 64) % 64 + 1] .. CH[v % 64 + 1]
          .. CH[floor(span / 4096) + 1] .. CH[floor(span / 64) % 64 + 1] .. CH[span % 64 + 1]
      end
    end
    out[key] = table.concat(parts)
  end
  return out
end
-- One block's least and most distance from landmark l (nil, nil: none), from the tile's field string.
local function AltAt(c, key, ci, l, set)
  local a = (set or c.alt) and (set or c.alt)[key]
  if not a then return nil end
  local per, B = c.per, WG.ALT_BLOCK
  local nb = per / B
  local bi = floor(floor(ci / per) / B) * nb + floor((ci % per) / B)
  local p = ((l - 1) * nb * nb + bi) * 6
  if p + 6 > #a then return nil end
  local v = (DEC[byte(a, p + 1)] * 64 + DEC[byte(a, p + 2)]) * 64 + DEC[byte(a, p + 3)]
  local span = (DEC[byte(a, p + 4)] * 64 + DEC[byte(a, p + 5)]) * 64 + DEC[byte(a, p + 6)]
  if v >= WG.ALT_NONE or span >= WG.ALT_SPAN_NONE then return nil end
  return v, v + span
end
WG.AltAt = AltAt
-- A surface's cell in its tile (by the tile's `base`, then cell by cell).
local function CellOfSurface(t, s)
  local base = t.base
  local lo, hi = 1, #base
  while lo < hi do
    local mid = floor((lo + hi + 1) / 2)
    if base[mid] <= s then lo = mid else hi = mid - 1 end
  end
  local ci, f = (lo - 1) * BASE, base[lo]
  local cells = t.cells
  while ci < #cells do
    local n = DEC[byte(cells, ci + 1)]
    if s < f + n then return ci end
    f, ci = f + n, ci + 1
  end
  return nil
end
WG.CellOfSurface = CellOfSurface
-- For a search to `goals` (ids): a function (key, ci) -> the least cost from there to a goal the fields allow (0 when
-- none), or nil when the fields don't cover a goal. The goals' range: the least and most over their blocks.
function WG.AltSearch(c, goals, set, L)
  set = set or c.alt
  if not (set and next(set)) then return nil end
  L = L or c.altN or 0
  if L < 1 then return nil end
  local B = WG.ALT_BLOCK
  local tlo, thi = {}, {}
  local any = false
  for id in pairs(goals) do
    local key = floor(id / SHIFT)
    local t = WG.Tile(c, key)
    local ci = t and CellOfSurface(t, id - key * SHIFT)
    if not ci then return nil end
    for l = 1, L do
      local a, b = AltAt(c, key, ci, l, set)
      if not a then return nil end -- (a goal's block unknown: the straight line)
      tlo[l] = tlo[l] and min(tlo[l], a) or a
      thi[l] = thi[l] and max(thi[l], b) or b
    end
    any = true
  end
  if not any then return nil end
  local per, nb = c.per, c.per / B
  local cache = {}
  return function(key, ci)
    local bi = floor(floor(ci / per) / B) * nb + floor((ci % per) / B)
    local ck = key * 64 + bi
    local got = cache[ck]
    if got then return got end
    local best = 0
    for l = 1, L do
      local a, b = AltAt(c, key, ci, l, set)
      if a then
        local v = max(tlo[l] - b, a - thi[l])
        if v > best then best = v end
      end
    end
    cache[ck] = best
    return best
  end
end
-- Which fields a search with costs `x` may use: the near set (falls within ALT_FALL) while its falls stay within it,
-- else the far set (baked with every fall: a fall spell's, an Expert jumper's; item 47, Kooki3z: "is caching helping
-- or hurting it?", with Expert jumper on the fields were off and his long legs had the straight line only). Returns
-- the set and its landmark count, or nil (no player's own links, the fields don't know those).
function WG.AltAllowed(x, c)
  if not x or WG.altOff then return nil end
  if x.erased or x.own or x.roadCells then return nil end
  local fall = max(x.maxDrop or huge, x.slopeDrop or 0)
  if fall <= WG.ALT_FALL then
    if not c then return true end -- (asked without the continent: allowed)
    return c.alt, c.altN -- (nil while no region's fields are loaded yet)
  end
  if c and c.alt2 and next(c.alt2) then return c.alt2, c.altN2 end
  return nil
end

---------------------------------------------------------------------------------------------- the block corridor
-- Item 38 (Kooki3z 2026-11-24, a release blocker): from south of Camp Taurajo to Un'Goro at level 25 the route never
-- settled, the faded line for minutes: the one walk there is 10.4k yd round by Thousand Needles and Tanaris, and the
-- grid's search took 400k-700k nodes (the cap is 200k: "No way found yet" at last). A long leg's search is now kept to a
-- corridor first: the blocks (ALT_BLOCK cells square) a search over the blocks takes, and the blocks round them. The
-- blocks' ways out (`e`, baked with the landmark fields: every move a search can make from one block's surfaces to a
-- neighbor block's, each of the eight sides a bit; longer moves, a lift or a road link over two blocks, listed apart,
-- `xl`) make that search a few thousand blocks at most. The grid's search inside the corridor is the leg's walk; with
-- none found there, the whole grid's as before.
WG.BLOCK_CORRIDOR_YD = 1500 -- (a leg this long, straight, or longer: its corridor first)
WG.BLOCK_CORRIDOR_RING = 1 -- (blocks either side of the block path)
WG.BLOCK_CORRIDOR_MAX = 60000 -- (blocks a corridor search may look at)
local function BlockOf(c, t, ci)
  local B = WG.ALT_BLOCK
  return floor((t.gx0 + floor(ci / c.per)) / B), floor((t.gy0 + ci % c.per) / B)
end
local function BlockKey(bx, by) return (bx + 32768) * 65536 + by + 32768 end
WG.BlockKey = BlockKey
-- (the bake's: each block's ways out, by tile: { [key] = string of nb*nb blocks, 2 characters each (the 8 sides' bits) },
-- and the longer ones { [key] = "bi:bx:by,..." })
function WG.AltExits(c, prep)
  local cellOf, rev, fwd = prep.cellOf, prep.rev, prep.fwd
  local per, B = c.per, WG.ALT_BLOCK
  local nb = per / B
  local bits, longer = {}, {}
  local function Mark(key, ci, id2)
    local t = WG.Tile(c, key)
    local k2 = floor(id2 / SHIFT)
    local t2 = WG.Tile(c, k2)
    local ci2 = cellOf[id2]
    if not (t and t2 and ci2) then return end
    local ax, ay = BlockOf(c, t, ci)
    local bx, by = BlockOf(c, t2, ci2)
    if ax == bx and ay == by then return end
    local bi = floor(floor(ci / per) / B) * nb + floor((ci % per) / B)
    local dx, dy = bx - ax, by - ay
    if math.abs(dx) <= 1 and math.abs(dy) <= 1 then
      for d = 1, 8 do
        if DX[d] == dx and DY[d] == dy then
          local k = key * 64 + bi
          local v = bits[k] or 0
          if floor(v / 2 ^ (d - 1)) % 2 == 0 then bits[k] = v + 2 ^ (d - 1) end
          break
        end
      end
    else
      longer[key] = longer[key] or {}
      longer[key][bi .. ":" .. bx .. ":" .. by] = true
    end
  end
  for id, ci in pairs(cellOf) do
    local key = floor(id / SHIFT)
    local t = WG.Tile(c, key)
    if t then
      local s0 = id - key * SHIFT
      for d = 1, 8 do
        local kk = Link(t, s0, d)
        if kk > 0 then
          local nkey, nci = Step(c, key, ci, d)
          local nt = nkey and WG.Tile(c, nkey)
          if nt then Mark(key, ci, nkey * SHIFT + First(nt, nci) + kk - 1) end
        end
      end
      for _, li in ipairs(c.out[id] or {}) do Mark(key, ci, c.links[li].b) end
      local f = fwd[id]
      if f then
        for k = 1, #f, 2 do Mark(key, ci, f[k]) end
      end
    end
  end
  local e, x = {}, {}
  for key in pairs(c.raw) do
    local parts = {}
    for bi = 0, nb * nb - 1 do
      local v = bits[key * 64 + bi] or 0
      parts[#parts + 1] = CH[floor(v / 64) + 1] .. CH[v % 64 + 1]
    end
    e[key] = table.concat(parts)
    if longer[key] then
      local list = {}
      for item in pairs(longer[key]) do list[#list + 1] = item end
      table.sort(list)
      x[key] = table.concat(list, ",")
    end
  end
  return e, x
end
-- A block's ways out: the sides' bits (nil: the fields don't cover it) and its longer ways { { bx, by }, ... }.
local function BlockExits(c, bx, by)
  local B = WG.ALT_BLOCK
  local key, ci = CellKey(c, bx * B, by * B)
  if not key then return nil end
  -- (its region loaded as the block search reaches it, as the grid's search loads them: the exits come with it)
  if not (c.altE and c.altE[key]) then
    local tx, ty = floor(key / 64), key % 64
    local rk = floor(tx / c.rb) .. ":" .. floor(ty / c.rb)
    if c.regions[rk] == nil then WG.LoadRegion(c, floor(tx / c.rb), floor(ty / c.rb)) end
  end
  local e = c.altE and c.altE[key]
  if not e then return nil end
  local nb = c.per / B
  local bi = floor(floor(ci / c.per) / B) * nb + floor((ci % c.per) / B)
  local p = bi * 2
  if p + 2 > #e then return nil end
  local v = DEC[byte(e, p + 1)] * 64 + DEC[byte(e, p + 2)]
  local more
  local xl = c.altX and c.altX[key]
  if xl then
    for a, ox, oy in xl:gmatch("(%d+):(%-?%d+):(%-?%d+)") do
      if tonumber(a) == bi then
        more = more or {}
        more[#more + 1] = { tonumber(ox), tonumber(oy) }
      end
    end
  end
  return v, more
end

-- The blocks' distances to a goal (item 38): a search back from the goal's block over the blocks' ways out (each block's
-- ways in: its eight neighbors' bits toward it, the longer ways listed), in yards between the blocks' centers, the zones
-- too high weighed as the search weighs them. { [BlockKey] = yards }, nil when the goal's block has no fields. A long
-- leg's search takes it as its heuristic's guide (WG.Search's x.blockDist: the most of it less a block and a half, and
-- the straight line): it heads for the ways that lead to the goal, not the straight line into a rim.
WG.BLOCK_GUIDE_MAX = 60000 -- (blocks it may look at)
function WG.BlockDistances(c, tx, ty, x, sx, sy)
  local Rt = R()
  local B = WG.ALT_BLOCK
  local size = B * c.cell
  local cell = c.cell
  local tbx, tby = floor(floor(tx / cell) / B), floor(floor(ty / cell) / B)
  if not BlockExits(c, tbx, tby) then return nil end
  local dist, closed = {}, {}
  local hk, hv = {}, {}
  local g0 = BlockKey(tbx, tby)
  dist[g0] = 0
  Push(hk, hv, 0, g0)
  local function Factor(bx, by)
    if not (x and x.red and Rt.ZoneAt) then return 1 end
    local z = Rt.ZoneAt(c.cont, (bx + 0.5) * size, (by + 0.5) * size)
    if z and x.red[z] and not (x.redExempt and x.redExempt[z]) then
      -- (its roads, the least a yard there costs: item 135b)
      return Rt.RedFactor and Rt.RedFactor(x.red, z, true) or Rt.LEVEL_FACTOR or 1
    end
    return 1
  end
  -- (the longer ways in: every longer way out of a loaded block, by its far end)
  local longIn = {}
  local function LongIns()
    for key, xl in pairs(c.altX or {}) do
      if not longIn[key] then
        longIn[key] = true
        local t = WG.Tile(c, key)
        if t then
          local nb = c.per / B
          for a, ox, oy in xl:gmatch("(%d+):(%-?%d+):(%-?%d+)") do
            local bi = tonumber(a)
            local bx = floor((t.gx0 + floor(bi / nb) * B) / B)
            local by = floor((t.gy0 + (bi % nb) * B) / B)
            local k2 = BlockKey(tonumber(ox), tonumber(oy))
            longIn[k2] = longIn[k2] or {}
            if type(longIn[k2]) == "table" then longIn[k2][#longIn[k2] + 1] = { bx, by } end
          end
        end
      end
    end
  end
  local n = 0
  -- (far enough past the start's block: half as far again as it, and a few blocks; the blocks further aren't searched)
  local sk = sx and BlockKey(floor(floor(sx / cell) / B), floor(floor(sy / cell) / B))
  local stopAt
  while hk[1] do
    local f, k = Pop(hk, hv)
    if not closed[k] then
      closed[k] = true
      n = n + 1
      if Rt.Breathe then Rt.Breathe(n, 400) end
      if n > WG.BLOCK_GUIDE_MAX then break end
      if k == sk then stopAt = f * 1.5 + 4 * size end
      if stopAt and f > stopAt then break end
      local bx, by = floor(k / 65536) - 32768, k % 65536 - 32768
      local w = Factor(bx, by)
      -- (its ways in: a neighbor whose way out points here)
      for d = 1, 8 do
        local nx, ny = bx - DX[d], by - DY[d]
        local k2 = BlockKey(nx, ny)
        if not closed[k2] then
          local v = BlockExits(c, nx, ny)
          if v and floor(v / 2 ^ (d - 1)) % 2 == 1 then
            local cost = f + (d > 4 and 1.4142 or 1) * size * w
            if not dist[k2] or cost < dist[k2] then
              dist[k2] = cost
              Push(hk, hv, cost, k2)
            end
          end
        end
      end
      if n % 200 == 1 then LongIns() end
      local li = longIn[k]
      if type(li) == "table" then
        for _, o in ipairs(li) do
          local k2 = BlockKey(o[1], o[2])
          if not closed[k2] then
            local cost = f + Dist(o[1], o[2], bx, by) * size * w
            if not dist[k2] or cost < dist[k2] then
              dist[k2] = cost
              Push(hk, hv, cost, k2)
            end
          end
        end
      end
    end
  end
  WG.stats.blockGuides = (WG.stats.blockGuides or 0) + 1
  return dist
end
-- The block corridor for a walk from (sx, sy) to (tx, ty): inside(x, y) for WG.Search, or nil (no fields, no block path).
-- The block path the cheapest by the blocks' centers' yards, the zones too high (x.red, not the walk's own ends')
-- weighed as the search weighs them.
function WG.BlockCorridor(c, sx, sy, tx, ty, x)
  local Rt = R()
  local B = WG.ALT_BLOCK
  local size = B * c.cell
  local cell = c.cell
  local sbx, sby = floor(floor(sx / cell) / B), floor(floor(sy / cell) / B)
  local tbx, tby = floor(floor(tx / cell) / B), floor(floor(ty / cell) / B)
  local goal = BlockKey(tbx, tby)
  local g, prev, closed = {}, {}, {}
  local hk, hv = {}, {}
  local s0 = BlockKey(sbx, sby)
  g[s0] = 0
  Push(hk, hv, Dist(sbx, sby, tbx, tby) * size, s0)
  local n, found = 0, nil
  local function Factor(bx, by)
    if not (x and x.red and Rt.ZoneAt) then return 1 end
    local z = Rt.ZoneAt(c.cont, (bx + 0.5) * size, (by + 0.5) * size)
    if z and x.red[z] and not (x.redExempt and x.redExempt[z]) then
      -- (its roads, the least a yard there costs: item 135b)
      return Rt.RedFactor and Rt.RedFactor(x.red, z, true) or Rt.LEVEL_FACTOR or 1
    end
    return 1
  end
  while hk[1] do
    local f, k = Pop(hk, hv)
    if not closed[k] then
      closed[k] = true
      n = n + 1
      if Rt.Breathe then Rt.Breathe(n, 400) end
      if k == goal then found = k break end
      if n > WG.BLOCK_CORRIDOR_MAX then break end
      local bx, by = floor(k / 65536) - 32768, k % 65536 - 32768
      local v, more = BlockExits(c, bx, by)
      if v then
        local function Go(nx, ny, steps)
          local k2 = BlockKey(nx, ny)
          if closed[k2] then return end
          local cost = g[k] + steps * size * Factor(nx, ny)
          if not g[k2] or cost < g[k2] then
            g[k2], prev[k2] = cost, k
            Push(hk, hv, cost + Dist(nx, ny, tbx, tby) * size, k2)
          end
        end
        for d = 1, 8 do
          if floor(v / 2 ^ (d - 1)) % 2 == 1 then Go(bx + DX[d], by + DY[d], d > 4 and 1.4142 or 1) end
        end
        for _, o in ipairs(more or {}) do Go(o[1], o[2], Dist(bx, by, o[1], o[2])) end
      end
    end
  end
  if not found then return nil end
  local set = {}
  local ring = WG.BLOCK_CORRIDOR_RING
  local k = found
  while k do
    local bx, by = floor(k / 65536) - 32768, k % 65536 - 32768
    for i = -ring, ring do
      for j = -ring, ring do set[BlockKey(bx + i, by + j)] = true end
    end
    k = prev[k]
  end
  WG.stats.blockCorridors = (WG.stats.blockCorridors or 0) + 1
  -- (the block path itself, start to goal, for the tests and /agps worldgrid: { bx, by } each)
  local path = {}
  local kk = found
  while kk do
    table.insert(path, 1, { floor(kk / 65536) - 32768, kk % 65536 - 32768 })
    kk = prev[kk]
  end
  WG.lastBlockPath = path
  return function(px, py)
    return set[BlockKey(floor(floor(px / cell) / B), floor(floor(py / cell) / B))] == true
  end, n
end

-- A* over the grid from `starts` ({ id, key, ci, cost }) to any of `goals` ({ [id] = extra }), toward (tx, ty);
-- `inside(x, y)`: the corridor (nil: anywhere); `x`: the costs (WG.Costs; nil: the grid's own alone). The way as
-- { id, key, ci, link, drop } steps, or nil.
-- A lift link's yards over its own `cost`: its wait by the cars' phase when known (Lifts.CostYards, item 135a), else 0.
function WG.LiftYards(c, L, cost)
  local LT = ns.Lifts
  if not (LT and LT.CostYards) then return 0 end
  local a, b = L.pts[1], L.pts[#L.pts]
  return LT.CostYards(c.cont, a[1], a[2], ((b[3] or 0) > (a[3] or 0)) and "bottom" or "top", cost - 1)
end

function WG.Search(c, starts, goals, tx, ty, inside, x)
  local Rt = R()
  local P = ns.Passability
  local t0 = debugprofilestop and debugprofilestop()
  local g, prev, via, cellOf, closed, dropAt, lastDrop = {}, {}, {}, {}, {}, {}, {}
  local hk, hv = {}, {}
  local cell = c.cell
  local diag = cell * sqrt(2)
  local road = x and x.road or c.road
  local hw = road * (x and x.heur or WG.HEUR)
  local swim = x and x.swim or c.swim
  local any = x and x.any
  local dropCost = Rt.DROP_COST or 30
  -- (a spell jump with a lift near for the same climb: LIFT_FIRST_S more, Router.LiftFirstYards; nil, none to weigh)
  local liftFloor = x and Rt.LiftFirstFloor and Rt.LiftFirstFloor(c.cont, x.maxDrop) or nil
  -- (the thin tall walls from the models' collision, Passability.CrossesModelWall: a hard barrier for every far drop and
  -- link that crosses one in plan view, its heights whatever they are. Item 78, Red Cloud Mesa's palisade, then the whole
  -- map. The neighbor steps aren't checked: the bake drops every one across a wall, worldbake.shipped_walls, and a check
  -- a step cost 5-15% more frames on the common trips; test_model_walls_140.py checks the shipped data)
  local cont = c.cont
  local MW = P and P.HasModelWalls and P.HasModelWalls(cont) and P.CrossesModelWall or nil
  -- (the walls the search's links cross: worked out once a link, kept on the continent's grid)
  local walledLink = MW and WG.WalledLinks(c) or nil
  -- (the landmark fields' bound with the straight line, when allowed: item 33, WG.AltSearch)
  local altSet, altL = WG.AltAllowed(x, c)
  if x and x.noAlt then altSet = nil end -- (the bounded refine: the straight line alone, a consistent bound, WG.Refine)
  local AB = altSet and WG.AltSearch(c, goals, altSet, altL) or nil
  -- (its bounds by blocks aren't consistent from cell to cell: a surface closed is opened again when a cheaper way to it
  -- turns up, or the way found could be a few percent long)
  local reopen = AB ~= nil
  local reopens = 0
  local function Reopen(id2, old, new)
    if closed[id2] and old - new > WG.ALT_REOPEN_YD and reopens < WG.ALT_REOPENS then
      closed[id2] = nil
      reopens = reopens + 1
    end
  end
  -- (H is in yards at hw a yard: the bound, a cost, over hw; not weighted, and scaled when the road is cheaper than the
  -- data's, Road tolerance below 0)
  local altK = AB and min(1, road / c.road) / hw or 0
  local function H(px, py, hkey, hci)
    local dd = Dist(px, py, tx, ty)
    if AB and hci then
      local b = AB(hkey, hci) * altK
      if b > dd then dd = b end
    end
    return dd
  end
  for _, st in ipairs(starts) do
    if not g[st.id] or st.cost < g[st.id] then
      g[st.id], cellOf[st.id] = st.cost, st.ci
      Push(hk, hv, st.cost + hw * H(st.x or tx, st.y or ty, floor(st.id / SHIFT), st.ci), st.id)
    end
  end
  local found, k, bestEnd = nil, 0, nil
  local far = 0
  for _, st in ipairs(starts) do far = max(far, Dist(st.x or tx, st.y or ty, tx, ty)) end
  local limit = min(WG.MAX_NODES, WG.NODES_BASE + WG.NODES_PER_YD * far)
  if x and x.wholeBudget then limit = WG.MAX_NODES end -- (a short leg whose way is long round: WG.Walk, item 139)
  -- (the loop below reads a surface's record in one go and a neighbor in the node's own tile without a call: the same
  -- numbers as Link, Step, Pt, Flags, Z and H give, a third less time a node; study/route-perf, 2026-11-25. `LK`: the
  -- node's eight links, this search's own table, as a tile decoding for one search may pause for another)
  local per, zq, z0 = c.per, c.zq, c.z0
  local LK = {}
  local xf = x and x.f
  local ownCells = x and (x.roadCells or x.unroadCells) and true or false
  if x and x.nodeCap then limit = min(limit, x.nodeCap) end -- (a join's small search, JoinBySearch)
  if x and x.noLimit then limit = huge end -- (kept to a corridor, which bounds it: the refine, never cut short)
  if x then x.limitHit = nil end
  -- (HPA*, WorldHPA.lua: `x.home`, a set of tile keys, the search kept to them: a surface outside is reached (a goal, a
  -- way out of them) but never searched on from; `x.flood`, the bake's and a cluster's flood: every surface reached,
  -- no stop at a goal, its tables handed back in `x.res`)
  local home = x and x.home
  local flood = x and x.flood
  while hk[1] do
    local f, id = Pop(hk, hv)
    if not closed[id] then
      closed[id] = true
      k = k + 1
      if Rt.Breathe then Rt.Breathe(k, WG.SLICE) end
      if k > limit then
        if x then x.limitHit = true end -- (stopped by its budget, not out of ground: no proof there's no way, WG.Failed)
        break
      end
      local extra = goals[id]
      if extra then
        local tot = g[id] + extra
        if not bestEnd or tot < bestEnd then bestEnd, found = tot, id end
      end
      if found and f >= bestEnd and not flood then break end
      local key, ci, gs = floor(id / SHIFT), cellOf[id], g[id]
      local expand = not home or home[key] == true
      local t = WG.Tile(c, key)
      local s = id - key * SHIFT
      local ca, cb = floor(ci / per), ci % per
      local bF, bP, b1, b2, b3, b4, bz1, bz2, bz3 = byte(t.s, s * SURF + 1, s * SURF + 9)
      local zs = ((DEC[bz1] * 64 + DEC[bz2]) * 64 + DEC[bz3]) * zq + z0
      local fs = DEC[bF]
      local pv = DEC[bP]
      local sx, sy = (t.gx0 + ca + (floor(pv / 8) + 0.5) / 8) * cell, (t.gy0 + cb + (pv % 8 + 0.5) / 8) * cell
      local l1, l2, l3, l4 = DEC[b1], DEC[b2], DEC[b3], DEC[b4]
      LK[1], LK[2], LK[3], LK[4] = floor(l1 / 8), l1 % 8, floor(l2 / 8), l2 % 8
      LK[5], LK[6], LK[7], LK[8] = floor(l3 / 8), l3 % 8, floor(l4 / 8), l4 % 8
      local ea = any and Extra(x, id, sx, sy) or 0
      local roadA, unroadA = false, false
      if ownCells then roadA, unroadA = RoadCell(x, c, t, ci) end
      roadA = (roadA or IS_ROAD[fs]) and not unroadA
      local swimA = IS_SWIM[fs]
      for d = 1, expand and 8 or 0 do
        local kk = LK[d]
        local nkey, nci, nt
        if kk == 0 and x and x.erased then
          nkey, nci = Step(c, key, ci, d)
          nt = nkey and WG.Tile(c, nkey)
          if nt then kk = ErasedLink(c, x, t, s, ci, nt, nci, d, zs) end
        elseif kk > 0 then
          local na, nb = ca + DX[d], cb + DY[d]
          if na >= 0 and na < per and nb >= 0 and nb < per then
            nkey, nci, nt = key, na * per + nb, t
          else
            nkey, nci = Step(c, key, ci, d)
            nt = nkey and WG.Tile(c, nkey)
          end
        end
        if kk > 0 and nt then
          local s2 = First(nt, nci) + kk - 1
          local id2 = nkey * SHIFT + s2
          if not closed[id2] or reopen then
            local cF, cP, _, _, _, _, cz1, cz2, cz3 = byte(nt.s, s2 * SURF + 1, s2 * SURF + 9)
            local f2 = DEC[cF]
            local qv = DEC[cP]
            local px = (nt.gx0 + floor(nci / per) + (floor(qv / 8) + 0.5) / 8) * cell
            local py = (nt.gy0 + nci % per + (qv % 8 + 0.5) / 8) * cell
            local ok = not inside or inside(px, py)
            local dz = ((DEC[cz1] * 64 + DEC[cz2]) * 64 + DEC[cz3]) * zq + z0 - zs
            local isDrop = false
            if ok and dz <= -WG.DROP_Z then
              isDrop = Drop(t, s, ci, d, nt, s2, dz)
              if isDrop and x and -dz > x.maxDrop then ok = false end
              if isDrop and ok and IntoGround(c.cont, sx, sy, zs, px, py, zs + dz) then ok = false end
              if isDrop and x and x.jumpBanned and x.jumpBanned(c.cont, sx, sy, zs) then ok = false end
            end
            local swimB = IS_SWIM[f2]
            local wet = swimA or swimB
            if ok and wet and x and x.bans and swimB and P.SwimBanned(c.cont, px, py) then ok = false end
            if ok and x and x.walls and P.CrossesWall(c.cont, sx, sy, px, py) then ok = false end
            if ok then
              local step = d > 4 and diag or cell
              local cost = sqrt(step * step + dz * dz) + abs(dz) * WG.CLIMB_COST
              local onRoad = false
              if wet then
                cost = cost * swim
                -- (into the water from dry ground: SWIM_ENTER_YD more, once a swim: the bank, getting out. Item 60,
                -- Kooki3z 2026-11-24: "Swim 106 yd" across the Southfury right beside its bridge)
                if not swimA and swimB then cost = cost + WG.SWIM_ENTER_YD end
              else
                local roadB = IS_ROAD[f2]
                if ownCells then
                  local rb, ub = RoadCell(x, c, nt, nci)
                  roadB = (roadB or rb) and not ub
                end
                if roadA and roadB then cost = cost * road end
                onRoad = roadA and roadB
              end
              if any and cost then
                local ex2 = xf[id2]
                if ex2 == nil then ex2 = Extra(x, id2, px, py) end
                if ex2 >= huge or ea >= huge then
                  cost = nil
                else
                  local e2 = ea + ex2
                  -- (a zone too high's road ground, item 135b)
                  local fr = onRoad and x.fr
                  if fr then e2 = e2 - (fr[id] or 0) - (fr[id2] or 0) end
                  cost = cost + step * e2 / 2
                end
              end
              -- (a drop by the open world's rules, Router.DropExtra: a step down's walked off, a fall past it only where
              -- it saves the walk, never a chain of them down one slope)
              local land = lastDrop[id]
              if isDrop then
                local ld = lastDrop[id]
                local chained = ld and Rt.ChainDrop and Rt.ChainDrop(-dz) and Dist(sx, sy, ld[1], ld[2]) <= Rt.CHAIN_YD
                local extra = Rt.DropExtra and Rt.DropExtra(-dz, chained) or dropCost
                if extra and liftFloor and -dz > liftFloor then
                  extra = extra + Rt.LiftFirstYards(c.cont, sx, sy, -dz, zs, liftFloor)
                end
                if extra and cost then cost = cost + extra else cost = nil end
                if Rt.ChainDrop and Rt.ChainDrop(-dz) then land = { px, py } end
              end
              if cost then
                cost = gs + cost
                if not g[id2] or cost < g[id2] then
                  if reopen and g[id2] then Reopen(id2, g[id2], cost) end
                  g[id2], prev[id2], via[id2], cellOf[id2], dropAt[id2] = cost, id, nil, nci, isDrop or nil
                  lastDrop[id2] = land
                  local dd = sqrt((tx - px) ^ 2 + (ty - py) ^ 2) -- (H(px, py, nkey, nci))
                  if AB then
                    local bound = AB(nkey, nci) * altK
                    if bound > dd then dd = bound end
                  end
                  Push(hk, hv, cost + hw * dd, id2)
                end
              end
            end
          end
        end
      end
      -- (drops off a sheer cliff over empty cells: FarDrops)
      -- (and the slopes walked down over them, `walk`: anyone's, a plain walk; a drop only within the drop limit)
      local fd = expand and x and FarDrops(c, t, s, key, ci, zs, sx, sy)
      if fd then
        local banned = x.jumpBanned and x.jumpBanned(c.cont, sx, sy, zs)
        for _, e in ipairs(fd) do
          local fall = zs - e.z
          local lim = (e.over or 0) >= WG.FAR_DROP_CLEAN_SLOPE and x.maxDrop or (x.slopeDrop or x.maxDrop)
          if (not closed[e.id2] or reopen) and (e.walk or (not banned and fall <= lim)) and (not inside or inside(e.x, e.y))
            and not P.CrossesWall(c.cont, sx, sy, e.x, e.y) and not (MW and MW(cont, sx, sy, e.x, e.y)) then
            local yd = Dist(sx, sy, e.x, e.y)
            local cost
            local extra = 0
            if e.walk then
              cost = sqrt(yd * yd + fall * fall) + fall * WG.CLIMB_COST
            else
              cost = yd
              local ld = lastDrop[id]
              local chained = ld and Rt.ChainDrop and Rt.ChainDrop(fall) and Dist(sx, sy, ld[1], ld[2]) <= Rt.CHAIN_YD
              extra = Rt.DropExtra and Rt.DropExtra(fall, chained) or dropCost
              if extra and liftFloor and fall > liftFloor then
                extra = extra + Rt.LiftFirstYards(c.cont, sx, sy, fall, zs, liftFloor)
              end
            end
            if any then
              local ex2 = Extra(x, e.id2, e.x, e.y)
              if ex2 >= huge or ea >= huge then extra = nil else cost = cost + yd * (ea + ex2) / 2 end
            end
            if extra then
              cost = gs + cost + extra
              if not g[e.id2] or cost < g[e.id2] then
                if reopen and g[e.id2] then Reopen(e.id2, g[e.id2], cost) end
                g[e.id2], prev[e.id2], via[e.id2], cellOf[e.id2], dropAt[e.id2] = cost, id, nil, e.ci, (not e.walk) or nil
                lastDrop[e.id2] = (not e.walk and Rt.ChainDrop and Rt.ChainDrop(fall)) and { e.x, e.y } or lastDrop[id]
                Push(hk, hv, cost + hw * H(e.x, e.y, floor(e.id2 / SHIFT), e.ci), e.id2)
              end
            end
          end
        end
      end
      local out, own = c.out[id], x and x.own and x.own[id]
      if not expand then out, own = nil, nil end
      local nOut = out and #out or 0
      for oi = 1, nOut + (own and #own or 0) do
        local li = oi <= nOut and out[oi] or own[oi - nOut]
        local L = oi <= nOut and c.links[li] or li
        if not (walledLink and walledLink(L)) then
          if not closed[L.b] or reopen then
            local p = L.pts[#L.pts]
            local bkey, bci = CellKey(c, floor(p[1] / cell), floor(p[2] / cell))
            if bkey == L.bkey then
              local cost = L.yd * road
              -- (a lift: its wait by the cars' phase when known, Lifts.CostYards; item 135a)
              if L.kind == 5 then cost = cost + WG.LiftYards(c, L, cost) end
              if any then
                -- (the road link's own yards past guards and in zones too high, by its points)
                local q0 = L.pts[1]
                for q = 2, #L.pts do
                  local q1 = L.pts[q]
                  local seg = Dist(q0[1], q0[2], q1[1], q1[2])
                  local qid = L.own and -(1e9 + L.n * 1000 + q) or -(li * 1000 + q)
                  cost = cost + seg * Extra(x, qid, q1[1], q1[2])
                  if x.fr and x.fr[qid] then cost = cost - seg * x.fr[qid] end -- (road ground: item 135b)
                  q0 = q1
                end
                if cost >= huge then cost = nil end -- (through ground shut: item 63b)
              end
              local land = lastDrop[id]
              if L.kind == 4 and x then
                local fall = (L.pts[1][3] or 0) - (L.pts[#L.pts][3] or 0)
                if fall > x.maxDrop then cost = nil end
                if cost and x.jumpBanned and x.jumpBanned(c.cont, L.pts[1][1], L.pts[1][2]) then cost = nil end
                if cost and Rt.DropExtra then
                  local ld = lastDrop[id]
                  local q = L.pts[1]
                  local chained = ld and Rt.ChainDrop(fall) and Dist(q[1], q[2], ld[1], ld[2]) <= Rt.CHAIN_YD
                  local extra = Rt.DropExtra(fall, chained)
                  if extra and liftFloor and fall > liftFloor then
                    extra = extra + Rt.LiftFirstYards(c.cont, q[1], q[2], fall, q[3], liftFloor)
                  end
                  if extra then cost = cost + extra else cost = nil end
                  if Rt.ChainDrop(fall) then land = { p[1], p[2] } end
                end
              end
              if cost then
                cost = gs + cost
                if not g[L.b] or cost < g[L.b] then
                  if reopen and g[L.b] then Reopen(L.b, g[L.b], cost) end
                  g[L.b], prev[L.b], via[L.b], cellOf[L.b], dropAt[L.b] = cost, id, li, bci, nil
                  lastDrop[L.b] = land
                  Push(hk, hv, cost + hw * H(p[1], p[2], bkey, bci), L.b)
                end
              end
            end
          end
        end
      end
    end
  end
  WG.stats.searches, WG.stats.nodes = WG.stats.searches + 1, WG.stats.nodes + k
  if t0 then WG.stats.ms = WG.stats.ms + (debugprofilestop() - t0) end
  WG.lastNodes = k
  WG.lastCost = found and bestEnd or nil -- (the way's cost, for the tests: test_world_grid_alt's bound against it)
  if flood then x.res = { g = g, prev = prev, via = via, dropAt = dropAt, cellOf = cellOf, nodes = k } end
  if x and x.keep and not found then x.res = { g = g, nodes = k } end -- (HPA*'s: what a search in vain reached)
  g, closed = nil, nil
  WG.GcStep()
  if not found then return nil end
  -- (a road link's end cell: the cell of its last point, but its surface may be another cell's when that point is on
  -- the edge; the steps keep the ids' own cells)
  local steps, id = {}, found
  while id do
    table.insert(steps, 1, { id = id, key = floor(id / SHIFT), ci = cellOf[id], link = via[id], drop = dropAt[id] })
    id = prev[id]
  end
  return steps
end

-- Whether the grid walks the straight line from surface `id0` (tile key0, cell ci0) at (x0, y0) to (x1, y1), arriving
-- on `id1` (or any): cell to cell along it by links (none a drop: a ledge's edge is never a line's), within LINE_TOL of
-- each crossed surface's point. The surfaces crossed { id, key, ci } when it does.
function WG.Line(c, id0, key0, ci0, x0, y0, x1, y1, id1, probe)
  local cell = c.cell
  local gxs, gys = Origin(c, key0)
  local i, j = gxs + floor(ci0 / c.per), gys + ci0 % c.per
  local i1, j1 = floor(x1 / cell), floor(y1 / cell)
  local dx, dy = x1 - x0, y1 - y0
  local si, sj = dx > 0 and 1 or -1, dy > 0 and 1 or -1
  local tdx = dx ~= 0 and abs(cell / dx) or huge
  local tdy = dy ~= 0 and abs(cell / dy) or huge
  local fx, fy = x0 / cell - i, y0 / cell - j
  local tmx = dx ~= 0 and (si > 0 and (1 - fx) or fx) * tdx or huge
  local tmy = dy ~= 0 and (sj > 0 and (1 - fy) or fy) * tdy or huge
  local id, key, ci = id0, key0, ci0
  local t = WG.Tile(c, key)
  local s = id - key * SHIFT
  local crossed = not probe and { { id = id, key = key, ci = ci } } or nil
  local tol2 = (WG.LINE_TOL * cell) ^ 2
  local tolEdge2 = (WG.LINE_TOL_EDGE * cell) ^ 2
  local mid = 4 * 8 + 4
  local guard = 0
  while i ~= i1 or j ~= j1 do
    guard = guard + 1
    if guard > 4000 then return nil end
    local d
    local dxs, dys = si > 0 and 1 or 3, sj > 0 and 2 or 4
    local xFirst = tmx < tmy
    if xFirst and Link(t, s, dxs) == 0 and tmy < tmx + tdx and Link(t, s, dys) > 0 then xFirst = false
    elseif not xFirst and Link(t, s, dys) == 0 and tmx < tmy + tdy and Link(t, s, dxs) > 0 then xFirst = true end
    if xFirst then
      i, tmx, d = i + si, tmx + tdx, dxs
    else
      j, tmy, d = j + sj, tmy + tdy, dys
    end
    local kk = Link(t, s, d)
    if kk == 0 then return nil end
    local nkey, nci = Step(c, key, ci, d)
    local nt = nkey and WG.Tile(c, nkey)
    if not nt then return nil end
    local s2 = First(nt, nci) + kk - 1
    if Drop(t, s, ci, d, nt, s2, Z(c, nt, s2) - Z(c, t, s)) then return nil end
    key, ci, t, s = nkey, nci, nt, s2
    id = key * SHIFT + s
    if i ~= i1 or j ~= j1 then
      local px, py = Pt(c, t, s, ci)
      local L2 = dx * dx + dy * dy
      local tt = L2 > 0 and max(0, min(1, ((px - x0) * dx + (py - y0) * dy) / L2)) or 0
      local qx, qy = x0 + dx * tt - px, y0 + dy * tt - py
      local tl2 = DEC[byte(t.s, s * SURF + 2)] == mid and tol2 or tolEdge2
      if qx * qx + qy * qy > tl2 then return nil end
    end
    if crossed then crossed[#crossed + 1] = { id = id, key = key, ci = ci } end
  end
  if id1 and id ~= id1 then return nil end
  return crossed or true
end

-- A straight piece's extra past guards and elite areas and in zones too high (WG.Extra a yard, sampled every 4 yd), by
-- the search's costs `x`; 0 with none to weigh.
local function LineExtra(x, ax, ay, bx, by)
  if not (x and x.any) then return 0 end
  local Rt = R()
  local L = Dist(ax, ay, bx, by)
  local m = max(1, math.ceil(L / 4))
  local e = 0
  for q = 0, m - 1 do
    if q % 16 == 15 and Rt.SliceOver and Rt.SliceOver() then coroutine.yield() end -- (item 108, as WG.Clear's)
    local f = (q + 0.5) / m
    x.probe = (x.probe or 0) - 1
    e = e + Extra(x, x.probe - 1e9, ax + (bx - ax) * f, ay + (by - ay) * f) * L / m
  end
  return e
end
WG.LineExtra = LineExtra
-- Whether Pull's straight line from step a to step b is no dearer by the search's costs than the steps it replaces (+1
-- yard's worth): never across an elite area or the guards the search went round. Item 132, Kooki3z 2026-11-27 in Tanaris:
-- the refine's way hugged Sandsorrow Watch's elite areas, and the line pulled from step to step (up to LOOK_AHEAD, 400
-- yd) went straight through them, three red stretches the first route had gone round, and no "Take it?".
local function PullAllowed(x, P, a, b)
  if not (x and x.any) then return true end
  local before = 0
  for m = a, b - 1 do
    local p, q = P[m], P[m + 1]
    before = before + Extra(x, q.id, q.x, q.y) * Dist(p.x, p.y, q.x, q.y)
  end
  return LineExtra(x, P[a].x, P[a].y, P[b].x, P[b].y) <= before + 1
end
WG.PullAllowed = PullAllowed

-- The steps as a route: string-pulled between road links and drops, (sx, sy) to (tx, ty): { pts, kinds, length, road,
-- fz, worldGrid }. A straight stretch over road ground alone is a road's kind (drawn and said as one); a drop off a
-- ledge is the Router's KIND_DROP.
function WG.Pull(c, steps, sx, sy, tx, ty, x)
  local Rt = R()
  local WALK, ROAD = Rt.KIND_OFFROAD or 1, Rt.KIND_ROAD or 0
  local DROP = Rt.KIND_DROP or 4
  local pts, kinds, hs, onLink, bends = {}, {}, {}, {}, {}
  local function Put(x, y, z, kind)
    local n = #pts
    if n >= 2 and abs(pts[n - 1] - x) < 0.05 and abs(pts[n] - y) < 0.05 then return end
    if n >= 2 then kinds[#kinds + 1] = kind end
    pts[n + 1], pts[n + 2] = x, y
    hs[#hs + 1] = z
  end
  local P = {}
  local function LinkOf(l) return type(l) == "table" and l or c.links[l] end
  for idx, st in ipairs(steps) do
    local t = WG.Tile(c, st.key)
    local s = st.id - st.key * SHIFT
    local x, y = Pt(c, t, s, st.ci)
    P[idx] = { id = st.id, key = st.key, ci = st.ci, x = x, y = y, z = Z(c, t, s), link = st.link, drop = st.drop,
      f = Flags(t, s) }
  end
  P[1].x, P[1].y = sx, sy
  P[#P].x, P[#P].y = tx, ty
  local a = 1
  Put(P[1].x, P[1].y, P[1].z, WALK)
  local k = 0
  while a < #P do
    -- (the farthest step within LOOK_AHEAD the grid walks straight to, not the last before a few misses: along a wall
    -- the lines to every other step failed, and the line went cell to cell in a sawtooth; Nethergarde Keep 2026-11-22)
    local b, best = a + 1, a + 1
    while b <= #P and b - a <= WG.LOOK_AHEAD and not P[b].link and not P[b].drop do b = b + 1 end
    for bb = b - 1, a + 2, -1 do
      k = k + 1
      if Rt.Breathe and k % 4 == 0 then Rt.Breathe(k, 4) end
      if WG.Line(c, P[a].id, P[a].key, P[a].ci, P[a].x, P[a].y, P[bb].x, P[bb].y, P[bb].id, true)
        and not (x and x.lineWalls and ns.Passability.CrossesWall(c.cont, P[a].x, P[a].y, P[bb].x, P[bb].y))
        and WG.PullAllowed(x, P, a, bb) then
        best = bb
        break
      end
    end
    if P[a + 1].link or P[a + 1].drop then best = a + 1 end
    local nb = P[best]
    if nb.link then
      local L = LinkOf(nb.link)
      local kind = L.kind == 4 and DROP or ROAD
      if L.kind == 5 then -- (a lift: up or down by its ends' heights, as the Router's lift roads)
        local z1, z2 = L.pts[1][3] or 0, L.pts[#L.pts][3] or 0
        kind = z2 > z1 and (Rt.KIND_LIFT_UP or 6) or (Rt.KIND_LIFT_DOWN or 5)
      end
      local k0 = #kinds
      -- (a drop's fall noted by its top, the point its first piece starts at: FallSpells' steps)
      if L.kind == 4 and Rt.NoteDrop and #pts >= 2 then
        Rt.NoteDrop(pts[#pts - 1], pts[#pts], (L.pts[1][3] or 0) - (L.pts[#L.pts][3] or 0))
      end
      for _, p in ipairs(L.pts) do Put(p[1], p[2], p[3], kind) end
      -- (the way on from the link's own end, on the road: back to the cell's surface point first, a chain of a road's
      -- short links went link, point, link in a sawtooth; Nethergarde Keep 2026-11-22)
      local q = L.pts[#L.pts]
      if best < #P and q then nb.x, nb.y, nb.z = q[1], q[2], q[3] or nb.z else Put(nb.x, nb.y, nb.z, kind) end
      for m = k0 + 1, #kinds do onLink[m] = true end
    elseif nb.drop then
      if Rt.NoteDrop and #pts >= 2 and P[a].z and nb.z then Rt.NoteDrop(pts[#pts - 1], pts[#pts], P[a].z - nb.z) end
      Put(nb.x, nb.y, nb.z, DROP)
    else
      local line = WG.Line(c, P[a].id, P[a].key, P[a].ci, P[a].x, P[a].y, nb.x, nb.y, nb.id)
      local road = true
      if line then
        for m = 2, #line do
          local t = WG.Tile(c, line[m].key)
          if not Bit(Flags(t, line[m].id - line[m].key * SHIFT), F_ROAD) then road = false break end
        end
      else
        road = false
      end
      if line and #line > 2 then
        local ax, ay, vx, vy = P[a].x, P[a].y, nb.x - P[a].x, nb.y - P[a].y
        local L2 = vx * vx + vy * vy
        local ts, zs = {}, {}
        for m = 1, #line do
          local t = WG.Tile(c, line[m].key)
          local s = line[m].id - line[m].key * SHIFT
          local px, py = Pt(c, t, s, line[m].ci)
          ts[m] = L2 > 0 and max(0, min(1, ((px - ax) * vx + (py - ay) * vy) / L2)) or 0
          zs[m] = Z(c, t, s)
        end
        ts[1], zs[1], ts[#line], zs[#line] = 0, P[a].z, 1, nb.z
        local keep = {}
        local function Split(i0, i1)
          local worst, wi = WG.Z_BEND, nil
          for m = i0 + 1, i1 - 1 do
            local f = ts[i1] > ts[i0] and (ts[m] - ts[i0]) / (ts[i1] - ts[i0]) or 0
            local dev = abs(zs[m] - (zs[i0] + (zs[i1] - zs[i0]) * f))
            if dev > worst then worst, wi = dev, m end
          end
          if wi then
            Split(i0, wi)
            keep[#keep + 1] = wi
            Split(wi, i1)
          end
        end
        Split(1, #line)
        for _, m in ipairs(keep) do
          Put(ax + vx * ts[m], ay + vy * ts[m], zs[m], road and ROAD or WALK)
          bends[#pts / 2] = true
        end
      end
      Put(nb.x, nb.y, nb.z, road and ROAD or WALK)
    end
    a = best
  end
  if #pts < 4 then Put(tx + 0.01, ty, P[#P].z, WALK) end
  pts, kinds, hs, onLink, bends = WG.Straighten(c, pts, kinds, hs, onLink, bends, x)
  local length, roadYd = 0, 0
  for m = 1, #kinds do
    local d = Dist(pts[2 * m - 1], pts[2 * m], pts[2 * m + 1], pts[2 * m + 2])
    length = length + d
    if kinds[m] == ROAD then roadYd = roadYd + d end
  end
  return { pts = pts, kinds = kinds, length = length, road = roadYd, fz = hs, worldGrid = true, onLink = onLink,
    bends = bends }
end

---------------------------------------------------------------------------------------------------- straightening
-- (asked 2026-11-22, Kooki3z: "Straighten out lines when this happens": a line along a building's wall stepped cell by
-- cell, the 8.33 yd cells showing through)
WG.CLEAR_YD = 1 -- a straightened line keeps this far off a cell side the grid has no link across (a wall's, a drop's)
WG.CLEAR_STEP = 1 -- yards between the points it's checked at
-- (item 123, 1.4.1: over the water a straightened line keeps within this of the water's top, the bake's SHORE_Z, a
-- step up out of it: never cut from a swim up onto a deck or a ledge the water has no way up to. Booty Bay's piers: the
-- swim's line went from under the lower deck straight onto it 4.5 yd up, past the plank that is the only way out)
WG.SWIM_CLEAR_Z = 1.5
WG.CLEAR_LOOSE = 0.7 -- (cells: WG.Clear's `loose` edge surfaces, item 57)
WG.CLEAR_Z = 3 -- yards: its height within this of the floor it's over (never across a floor change or stairs)
WG.STRAIGHT_AHEAD = 64 -- points a straight piece is tried toward, farthest first ...
WG.STRAIGHT_TRIES = 3000 -- ... and lines tried a route at most
WG.COLLINEAR_DEG = 10 -- a turn smaller than this between two short pieces is dropped ...
WG.COLLINEAR_YD = 30 -- ... pieces up to this long

-- Whether the grid walks the straight line (x0, y0, z0) to (x1, y1, z1) on one floor: every CLEAR_STEP yards over a
-- surface of its cell within CLEAR_Z of the line's height, from cell to cell by links (none a drop), CLEAR_YD off every
-- side of a cell with no link across it (and off a corner with no diagonal link), a floor's edge surface (its point off
-- the cell's middle) kept near its point (0.45 of a cell); `loose`: within CLEAR_LOOSE of a cell (a merge's walk onto a
-- road over open ground, WG.SnapRun: a line along a cell's side failed on flat grass, its cells' points 5 yd off it; not
-- looser: with none, a merge's walk went into the Crossroads' inn through its wall, test_building_doors).
function WG.Clear(c, x0, y0, z0, x1, y1, z1, loose)
  local cell = c.cell
  local L = Dist(x0, y0, x1, y1)
  local n = max(1, math.ceil(L / WG.CLEAR_STEP))
  local key, ci, t, s, gx, gy
  local clr = WG.CLEAR_YD
  local edgeTol2 = ((loose and WG.CLEAR_LOOSE or 0.45) * cell) ^ 2
  local mid = 4 * 8 + 4
  local SliceOver = R().SliceOver
  for q = 0, n do
    -- (in a background job, a look at the slice's clock along a long line: a yard a step, hundreds of them; Straighten's
    -- and the road merges' tries ran 12-30 ms slices on the slow client. Item 108)
    if q % 64 == 63 and SliceOver and SliceOver() then coroutine.yield() end
    local f = q / n
    local x, y = x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
    local z = (z0 and z1) and z0 + (z1 - z0) * f or nil
    local cx, cy = floor(x / cell), floor(y / cell)
    if not key then
      local k2, c2 = CellKey(c, cx, cy)
      local t2 = k2 and WG.Tile(c, k2)
      if not t2 then return false end
      local cnt = Count(t2, c2)
      if cnt == 0 then return false end
      local f0, best, bd = First(t2, c2), nil, nil
      for kk = 0, cnt - 1 do
        local d = z and abs(Z(c, t2, f0 + kk) - z) or 0
        if not bd or d < bd then best, bd = f0 + kk, d end
      end
      if bd > WG.CLEAR_Z then return false end
      key, ci, t, s, gx, gy = k2, c2, t2, best, cx, cy
    elseif cx ~= gx or cy ~= gy then
      -- (into the next cell by the links: a diagonal step by its own link)
      while cx ~= gx or cy ~= gy do
        local ix, iy = cx - gx, cy - gy
        ix = ix > 0 and 1 or ix < 0 and -1 or 0
        iy = iy > 0 and 1 or iy < 0 and -1 or 0
        local d
        for dd = 1, 8 do if DX[dd] == ix and DY[dd] == iy then d = dd break end end
        local kk = Link(t, s, d)
        if kk == 0 then return false end
        local nkey, nci = Step(c, key, ci, d)
        local nt = nkey and WG.Tile(c, nkey)
        if not nt then return false end
        local s2 = First(nt, nci) + kk - 1
        if Drop(t, s, ci, d, nt, s2, Z(c, nt, s2) - Z(c, t, s)) then return false end
        key, ci, t, s = nkey, nci, nt, s2
        gx, gy = gx + ix, gy + iy
      end
      if z and abs(Z(c, t, s) - z) > WG.CLEAR_Z then return false end
    end
    -- (a body's width off the cell's closed sides and corners)
    local fx, fy = x - gx * cell, y - gy * cell
    local nearW, nearE, nearS, nearN = fx < clr, fx > cell - clr, fy < clr, fy > cell - clr
    if (nearE and Link(t, s, 1) == 0) or (nearW and Link(t, s, 3) == 0) or (nearN and Link(t, s, 2) == 0)
      or (nearS and Link(t, s, 4) == 0) then return false end
    if (nearE and nearN and Link(t, s, 5) == 0) or (nearW and nearN and Link(t, s, 6) == 0)
      or (nearW and nearS and Link(t, s, 7) == 0) or (nearE and nearS and Link(t, s, 8) == 0) then return false end
    if DEC[byte(t.s, s * SURF + 2)] ~= mid then
      local px, py = Pt(c, t, s, ci)
      if (px - x) ^ 2 + (py - y) ^ 2 > edgeTol2 then return false end
    end
    if z and Bit(Flags(t, s), F_SWIM) and abs(Z(c, t, s) - z) > WG.SWIM_CLEAR_Z then return false end
  end
  return true
end

-- The pulled route's points straightened (WG.Pull's last pass): from each point to the farthest later one within
-- STRAIGHT_AHEAD the grid walks straight to (WG.Clear), over walking pieces only (a road link's, a drop's, a lift's
-- stay; a road's too while the Road tolerance keeps to the roads, below 0); then near-collinear points dropped.
function WG.Straighten(c, pts, kinds, hs, onLink, bends, x)
  local Rt = R()
  local WALK, ROAD = Rt.KIND_OFFROAD or 1, Rt.KIND_ROAD or 0
  local st = ns.settings and ns.settings.gps
  local tol = st and tonumber(st.roadTolerance)
  local keepRoads = tol ~= nil and tol < 0
  local n = #pts / 2
  if n < 3 then return pts, kinds, hs, onLink, bends end
  local function Free(m) -- (piece m, between points m and m + 1, may be straightened over)
    if onLink[m] then return false end
    local k = kinds[m]
    return k == WALK or (k == ROAD and not keepRoads)
  end
  -- (the search's costs kept: a straight piece no dearer past guards or in zones too high than the pieces it replaces,
  -- and across none of the player's own walls)
  local Pa = ns.Passability
  local function Dear(ax, ay, bx, by) return LineExtra(x, ax, ay, bx, by) end
  local function Allowed(i, jj)
    local ax, ay, bx, by = pts[2 * i - 1], pts[2 * i], pts[2 * jj - 1], pts[2 * jj]
    if x and x.lineWalls and Pa and Pa.CrossesWall and Pa.CrossesWall(c.cont, ax, ay, bx, by) then return false end
    if x and x.any then
      local before = 0
      for m = i, jj - 1 do before = before + Dear(pts[2 * m - 1], pts[2 * m], pts[2 * m + 1], pts[2 * m + 2]) end
      if Dear(ax, ay, bx, by) > before + 1 then return false end
    end
    return true
  end
  local P, K, H, LK, B = { pts[1], pts[2] }, {}, { hs[1] }, {}, {}
  local tries, i = 0, 1
  while i < n do
    local j = i + 1
    if Free(i) then
      local far = i + 1
      while far < n and far - i < WG.STRAIGHT_AHEAD and Free(far) do far = far + 1 end
      for jj = far, i + 2, -1 do
        if tries >= WG.STRAIGHT_TRIES then break end
        tries = tries + 1
        if Rt.Breathe then Rt.Breathe(tries, 3) end -- (every 3 tries, and the clock between: item 108)
        local za, zb = hs[i], hs[jj]
        local level = true
        for m = i + 1, jj - 1 do
          local f = (m - i) / (jj - i)
          if za and zb and hs[m] and abs(hs[m] - (za + (zb - za) * f)) > WG.CLEAR_Z then level = false break end
        end
        if level and WG.Clear(c, pts[2 * i - 1], pts[2 * i], za, pts[2 * jj - 1], pts[2 * jj], zb) and Allowed(i, jj) then
          j = jj
          break
        end
      end
    end
    local kind = kinds[i]
    for m = i, j - 1 do if kinds[m] ~= kind then kind = WALK break end end
    P[#P + 1], P[#P + 2] = pts[2 * j - 1], pts[2 * j]
    K[#K + 1], H[#H + 1] = kind, hs[j]
    if onLink[i] and j == i + 1 then LK[#K] = true end
    if bends[j] then B[#H] = true end
    i = j
  end
  -- (a point between two short pieces of one kind turning less than COLLINEAR_DEG, on their height: dropped)
  local cos = math.cos(math.rad(WG.COLLINEAR_DEG))
  local P2, K2, H2, L2, B2 = { P[1], P[2] }, {}, { H[1] }, {}, {}
  local np = #P / 2
  local cx_ = x
  for m = 2, np do
    if m % 4 == 0 and Rt.SliceOver and Rt.SliceOver() then coroutine.yield() end -- (item 108: a long route's points)
    local x, y = P[2 * m - 1], P[2 * m]
    local np2 = #P2 / 2
    local drop = false
    if np2 >= 2 and m <= np and #K2 >= 1 and K2[#K2] == K[m - 1] and not L2[#K2] and not LK[m - 1]
      and (K[m - 1] == WALK or K[m - 1] == ROAD) then
      local ax, ay, bx, by = P2[2 * np2 - 3], P2[2 * np2 - 2], P2[2 * np2 - 1], P2[2 * np2]
      local u1, v1, u2, v2 = bx - ax, by - ay, x - bx, y - by
      local l1, l2 = sqrt(u1 * u1 + v1 * v1), sqrt(u2 * u2 + v2 * v2)
      local hz = H2[np2]
      local za, zc = H2[np2 - 1], H[m]
      local flat = not (hz and za and zc) or abs(hz - (za + zc) / 2) <= WG.Z_BEND
      if l1 > 0 and l2 > 0 and l1 <= WG.COLLINEAR_YD and l2 <= WG.COLLINEAR_YD and (u1 * u2 + v1 * v2) / (l1 * l2) > cos
        and flat and not B2[np2] and WG.Clear(c, ax, ay, za, x, y, zc)
        and not (cx_ and cx_.lineWalls and Pa and Pa.CrossesWall and Pa.CrossesWall(c.cont, ax, ay, x, y))
        and Dear(ax, ay, x, y) <= Dear(ax, ay, bx, by) + Dear(bx, by, x, y) + 1 then
        drop = true
      end
    end
    if drop then
      -- (the last kept point moved on to this one: its piece runs straight from the one before)
      P2[#P2 - 1], P2[#P2] = x, y
      H2[#H2] = H[m]
      if B[m] then B2[#H2] = true end
    else
      P2[#P2 + 1], P2[#P2 + 2] = x, y
      K2[#K2 + 1], H2[#H2 + 1] = K[m - 1], H[m]
      if LK[m - 1] then L2[#K2] = true end
      if B[m] then B2[#H2] = true end
    end
  end
  return P2, K2, H2, L2, B2
end

---------------------------------------------------------------------------------------------------- merges
-- (item 57, Kooki3z 2026-11-24, the Barrens at "Cut across": the road should be used wherever it goes the right way.
-- The grid's eight directions price a road that runs at a slant to them up to 8% dearer than its yards, more than the
-- road's bonus at the right of the slider, and its ties set where a merge falls, so the search walked the open ground
-- beside the road, or joined it anywhere. Each run of walking and road pieces of the pulled way is tried along the roads
-- near it, priced in straight lines: off the road a yard a yard, on it the search's road price p (Road tolerance). The
-- cheapest way from one of the run's points onto a road and off it again to a later one (joined where the walk meets
-- the road at the angle whose cosine is p, left where the road turns away from the way on by as much) replaces the run
-- between them when it costs less. So the slider shapes the merge: to the left early and steep, to the right later and
-- flatter, at +10 only a road within about 18 degrees of the way. Never a merge back against the way to the stop, a ride
-- along the road away from it, nor a leave back.)
WG.SNAP_MIN_YD = 40 -- a run this long or longer is tried along the roads near it ...
WG.SNAP_NEAR_YD = 120 -- ... those this near it (looked for every SNAP_SAMPLE_YD along it)
WG.SNAP_SAMPLE_YD = 40
WG.SNAP_STEP_YD = 5 -- (the spots along a road a merge or a leave is tried at)
WG.SNAP_RIDE_YD = 40 -- (a ride along the road this long at least: no "Join the road", "Leave the road" for a few yards)
WG.SNAP_GAIN_YD = 2 -- (taken when it costs this much less than the run at least)
WG.SNAP_TRIES = 8 -- (the best ways checked walkable, cheapest first, a run: one a road, way and point of the run)
WG.SNAP_NUDGE_STEP = 2 -- (samples a merge or a leave is moved by when its walk isn't straight, SnapRun's NUDGE)
WG.SNAP_LEAVE_YD = 5 -- (a walk this short onto or off the road: no direction to check)
WG.SNAP_CLEAR_YD = 12 -- (a new piece checked walkable in steps this long, on the floor followed, and dry when a walk)
-- The spots along edge `e` (its points flat from e[5]) every SNAP_STEP_YD or less and at its own points, within the box:
-- xs, ys, their yards along it, and for each the index of the edge's point it is at or after.
local function EdgeSamples(e, x0, y0, x1, y1)
  local xs, ys, as, vi = {}, {}, {}, {}
  local along = 0
  local n = (#e - 4) / 2
  local function Add(px, py, a, k)
    if px >= x0 and px <= x1 and py >= y0 and py <= y1 then
      local i = #xs + 1
      xs[i], ys[i], as[i], vi[i] = px, py, a, k
    end
  end
  for k = 1, n - 1 do
    local ax, ay, bx, by = e[3 + 2 * k], e[4 + 2 * k], e[5 + 2 * k], e[6 + 2 * k]
    local L = Dist(ax, ay, bx, by)
    local m = max(1, math.ceil(L / WG.SNAP_STEP_YD))
    for q = 0, m - 1 do
      local f = q / m
      Add(ax + (bx - ax) * f, ay + (by - ay) * f, along + L * f, k)
    end
    along = along + L
  end
  Add(e[3 + 2 * n], e[4 + 2 * n], along, n)
  return xs, ys, as, vi
end
-- A surface's height at (x, y), the nearest to z, and whether it's water.
local function SurfaceNear(c, x, y, z)
  local ss = WG.SurfacesAt(c, x, y, z)
  if not ss[1] then return z, false end
  return ss[1].z, IS_SWIM[ss[1].f] or false
end
-- Points k0..k1 of the pulled way (pts flat, kinds, hs; a run of walking and road pieces) along a road near them, when
-- cheaper: { i, j, pts = { { x, y, z, kind }, ... } }: the way leaves point i for the new points and comes back at
-- point j (each new point's kind the piece's up to it; point j's piece a walk). Else nil. (tx, ty): the leg's stop.
function WG.SnapRun(c, x, pts, kinds, hs, k0, k1, tx, ty)
  local Rt = R()
  local Pa = ns.Passability
  local price = x.road
  local ROAD, WALK = Rt.KIND_ROAD or 0, Rt.KIND_OFFROAD or 1
  -- (the run's cost to each point, C, and on from it, D)
  local C, VX, VY = {}, {}, {}
  C[k0] = 0
  local bx0, by0, bx1, by1 = huge, huge, -huge, -huge
  for k = k0, k1 do
    VX[k], VY[k] = pts[2 * k - 1], pts[2 * k]
    bx0, by0, bx1, by1 = min(bx0, VX[k]), min(by0, VY[k]), max(bx1, VX[k]), max(by1, VY[k])
    if k > k0 then
      C[k] = C[k - 1] + Dist(VX[k - 1], VY[k - 1], VX[k], VY[k]) * (kinds[k - 1] == ROAD and price or 1)
    end
  end
  local total = C[k1]
  -- (open land's: none in or by a capital's grid, the city grid's own ways; item 57 kept to the open world)
  local CG = ns.CityGrid
  if CG and CG.InGrid then
    for k = k0, k1 do if CG.InGrid(c.cont, VX[k], VY[k]) then return nil end end
  end
  local length = 0
  for k = k0 + 1, k1 do length = length + Dist(VX[k - 1], VY[k - 1], VX[k], VY[k]) end
  if length < WG.SNAP_MIN_YD or not Rt.RoadLinesNear then return nil end
  local pad = WG.SNAP_NEAR_YD
  bx0, by0, bx1, by1 = bx0 - pad, by0 - pad, bx1 + pad, by1 + pad
  -- (the roads near the run)
  local edges, seen = {}, {}
  -- (a background job paused by the clock alone, never by a count: SnapRun's loops change no job's resumes)
  local breathe = 0
  local function Pause()
    breathe = breathe + 1
    -- (every other step: a step is a sample's roads or a 12 yd piece checked clear, a yard at a time; 8 of them were
    -- 20-27 ms on the slow client. Item 108)
    if breathe % 2 == 0 and Rt.SliceOver and Rt.SliceOver() then coroutine.yield() end
  end
  for k = k0, k1 - 1 do
    local L = Dist(VX[k], VY[k], VX[k + 1], VY[k + 1])
    local n = max(1, math.ceil(L / WG.SNAP_SAMPLE_YD))
    for q = 0, (k == k1 - 1) and n or n - 1 do
      local qx, qy = VX[k] + (VX[k + 1] - VX[k]) * q / n, VY[k] + (VY[k + 1] - VY[k]) * q / n
      for _, r in ipairs(Rt.RoadLinesNear(c.cont, qx, qy, WG.SNAP_NEAR_YD)) do
        if not seen[r.ei] then
          seen[r.ei] = true
          edges[#edges + 1] = r
        end
      end
      Pause()
    end
  end
  if not edges[1] then return nil end
  local best = {}
  for _, r in ipairs(edges) do
    local xs, ys, as, vi = EdgeSamples(r.e, bx0, by0, bx1, by1)
    local m = #xs
    if m >= 2 then
      -- (each spot's best way off the road to a point of the run, LB, to LJ: never back against the way to the stop)
      local LB, LJ = {}, {}
      for a = 1, m do
        local px, py = xs[a], ys[a]
        local lb, lj = huge, nil
        for k = k0 + 1, k1 do
          local vx, vy = VX[k], VY[k]
          local d = Dist(vx, vy, px, py)
          if d + total - C[k] < lb and (d <= WG.SNAP_LEAVE_YD or (vx - px) * (tx - px) + (vy - py) * (ty - py) >= 0) then
            lb, lj = d + total - C[k], k
          end
        end
        LB[a], LJ[a] = lb, lj
        Pause()
      end
      -- (from each point i of the run: onto the road at a (never back), along it to b, off it to a later point)
      for i = k0, k1 - 1 do
        local vx, vy = VX[i], VY[i]
        for dir = 1, -1, -2 do
          local i0, i1, st = 1, m, 1
          if dir < 0 then i0, i1, st = m, 1, -1 end
          local pf, pa = nil, nil -- (the best merge so far: its cost less p yards along, and its spot)
          local top = nil
          for b = i0, i1, st do
            Pause()
            if pa and LJ[b] and LJ[b] > i then
              -- (a ride toward the stop)
              if (xs[b] - xs[pa]) * (tx - xs[pa]) + (ys[b] - ys[pa]) * (ty - ys[pa]) > 0
                  and dir * (as[b] - as[pa]) >= WG.SNAP_RIDE_YD then
                local tot = pf + LB[b] + dir * price * as[b]
                if not top or tot < top.tot then top = { tot = tot, a = pa, b = b, i = i, j = LJ[b] } end
              end
            end
            local px, py = xs[b], ys[b]
            local d = Dist(vx, vy, px, py)
            if d <= WG.SNAP_LEAVE_YD or (px - vx) * (tx - vx) + (py - vy) * (ty - vy) >= 0 then
              local f = C[i] + d - dir * price * as[b]
              if not pf or f < pf then pf, pa = f, b end
            end
          end
          if top and top.tot < total - WG.SNAP_GAIN_YD then
            top.e, top.dir, top.ei, top.xs, top.ys, top.vi = r.e, dir, r.ei, xs, ys, vi
            best[#best + 1] = top
          end
        end
        Pause()
      end
    end
  end
  if not best[1] then return nil end
  table.sort(best, function(p, q)
    if p.tot ~= q.tot then return p.tot < q.tot end
    if p.ei ~= q.ei then return p.ei < q.ei end
    return p.dir > q.dir
  end)
  local MW = Pa and Pa.HasModelWalls and Pa.HasModelWalls(c.cont) and Pa.CrossesModelWall or nil
  -- (a piece checked as the grid walks it: in short steps on the floor followed from z0, across no wall; a walk by the
  -- grid's links (WG.Clear) and swimming nowhere (priced as a walk), a road's own line as it is; arriving within CLEAR_Z
  -- of z1. Its points' heights, or nil)
  local function Walked(x0, y0, z0, x1, y1, z1, walk)
    local L = Dist(x0, y0, x1, y1)
    if L <= 0.05 then return {} end
    if Pa and Pa.CrossesWall and Pa.CrossesWall(c.cont, x0, y0, x1, y1) then return nil end
    if MW and MW(c.cont, x0, y0, x1, y1) then return nil end
    local n = max(1, math.ceil(L / WG.SNAP_CLEAR_YD))
    local subs = {}
    local px, py, pz = x0, y0, z0
    for q = 1, n do
      local f = q / n
      local qx, qy = x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
      Pause()
      local qz, wet = SurfaceNear(c, qx, qy, pz)
      if q == n then
        if abs(qz - z1) > WG.CLEAR_Z then return nil end
        qz = z1
      end
      if walk and wet then return nil end
      if walk and not WG.Clear(c, px, py, pz, qx, qy, qz, true) then return nil end
      subs[q] = { x = qx, y = qy, z = qz }
      px, py, pz = qx, qy, qz
    end
    return subs
  end
  -- (the heights a piece's points need, as WG.Pull's: those its height bends at by Z_BEND or more)
  local function Bends(x0, y0, z0, subs, kind, into)
    local all = { { x = x0, y = y0, z = z0 } }
    for _, s in ipairs(subs) do all[#all + 1] = s end
    local keep = {}
    local function Split(i0, i1)
      local worst, wi = WG.Z_BEND, nil
      local L = Dist(all[i0].x, all[i0].y, all[i1].x, all[i1].y)
      for m = i0 + 1, i1 - 1 do
        local f = L > 0 and Dist(all[i0].x, all[i0].y, all[m].x, all[m].y) / L or 0
        local dev = abs(all[m].z - (all[i0].z + (all[i1].z - all[i0].z) * f))
        if dev > worst then worst, wi = dev, m end
      end
      if wi then
        Split(i0, wi)
        keep[#keep + 1] = wi
        Split(wi, i1)
      end
    end
    Split(1, #all)
    for _, m in ipairs(keep) do into[#into + 1] = { x = all[m].x, y = all[m].y, z = all[m].z, kind = kind, bend = true } end
    local e = all[#all]
    into[#into + 1] = { x = e.x, y = e.y, z = e.z, kind = kind }
  end
  -- (a straight piece's extra past guards and in zones too high, WG.Extra a yard)
  local function Dear(x0, y0, x1, y1)
    local L = Dist(x0, y0, x1, y1)
    local n = max(1, math.ceil(L / 4))
    local e = 0
    for q = 0, n - 1 do
      local f = (q + 0.5) / n
      x.probe = (x.probe or 0) - 1
      e = e + Extra(x, x.probe - 1e9, x0 + (x1 - x0) * f, y0 + (y1 - y0) * f) * L / n
    end
    return e
  end
  -- (candidate cd's way with its merge at spot a and its leave at b: its new points, or nil and the part that failed)
  local function Way(cd, a, b)
    local xs, ys, e, vi = cd.xs, cd.ys, cd.e, cd.vi
    local i, j = cd.i, cd.j
    -- (the merge, the road's own points between, the leave, then back to point j)
    local way = { { x = xs[a], y = ys[a], kind = WALK, part = "merge" } }
    if cd.dir > 0 then
      for k = vi[a] + 1, vi[b] do way[#way + 1] = { x = e[3 + 2 * k], y = e[4 + 2 * k], kind = ROAD, part = "road" } end
    else
      for k = vi[a], vi[b] + 1, -1 do way[#way + 1] = { x = e[3 + 2 * k], y = e[4 + 2 * k], kind = ROAD, part = "road" } end
    end
    local last = way[#way]
    if Dist(last.x, last.y, xs[b], ys[b]) > 0.5 then way[#way + 1] = { x = xs[b], y = ys[b], kind = ROAD, part = "road" } end
    way[#way + 1] = { x = VX[j], y = VY[j], z = hs[j], kind = WALK, part = "leave" }
    local out = {}
    local px, py, pz = VX[i], VY[i], hs[i] or 0
    for k = 1, #way do
      local o = way[k]
      local zz = o.z
      if zz == nil then zz = SurfaceNear(c, o.x, o.y, pz) end
      local subs = Walked(px, py, pz, o.x, o.y, zz, o.kind == WALK)
      if not subs then return nil, o.part end
      if Dist(px, py, o.x, o.y) > 0.05 then Bends(px, py, pz, subs, o.kind, out) end
      px, py, pz = o.x, o.y, zz
    end
    return out
  end
  -- (a merge or a leave whose walk the grid doesn't take straight (a rock, a bush in the way): tried again a few spots
  -- along the road either side, SNAP_NUDGE at most)
  local NUDGE = { 0, 1, -1, 2, -2, 3, -3, 4, -4 }
  for t = 1, min(#best, WG.SNAP_TRIES) do
    local cd = best[t]
    local m = #cd.xs
    local a, b = cd.a, cd.b
    local out, part = Way(cd, a, b)
    local function Fits(sa, sb) -- (merge spot before the leave spot, both on the edge's samples)
      return sa >= 1 and sa <= m and sb >= 1 and sb <= m and (sb - sa) * cd.dir > 0
    end
    for _, nd in ipairs(NUDGE) do
      if out or not (part == "merge" or part == "leave") then break end
      if nd ~= 0 then
        local sa, sb = a, b
        if part == "merge" then sa = a + nd * WG.SNAP_NUDGE_STEP else sb = b + nd * WG.SNAP_NUDGE_STEP end
        if Fits(sa, sb) then
          local o2, p2 = Way(cd, sa, sb)
          if o2 then out, a, b = o2, sa, sb
          elseif p2 ~= part then -- (the merge now walks, the leave next)
            if p2 == "leave" then a, part = sa, p2 end
          end
        end
      end
    end
    -- (no dearer past the other faction's guards or in zones too high than the run it replaces, as WG.Straighten)
    if out and out[1] and x.any then
      local before, after = 0, 0
      for k = cd.i, cd.j - 1 do before = before + Dear(VX[k], VY[k], VX[k + 1], VY[k + 1]) end
      local px, py = VX[cd.i], VY[cd.i]
      for _, o in ipairs(out) do
        after = after + Dear(px, py, o.x, o.y)
        px, py = o.x, o.y
      end
      if after > before + 1 then out = nil end
    end
    if out and out[1] then
      -- (point j itself is the run's own: out's last is it, its piece's kind kept)
      local jk = out[#out].kind
      out[#out] = nil
      WG.stats.snaps = (WG.stats.snaps or 0) + 1
      return { i = cd.i, j = cd.j, pts = out, jkind = jk }
    end
  end
  return nil
end
-- The pulled way's runs of walking and road pieces along the roads near them (WG.SnapRun), at the search's road price
-- x.road.
function WG.SnapPieces(c, pts, kinds, hs, onLink, bends, x, tx, ty)
  local Rt = R()
  local WALK, ROAD = Rt.KIND_OFFROAD or 1, Rt.KIND_ROAD or 0
  local n = #pts / 2
  local P2, K2, H2, L2, B2 = { pts[1], pts[2] }, {}, { hs[1] }, {}, {}
  if bends[1] then B2[1] = true end
  local function Keep(k) -- (point k, as it was, with its piece from k - 1)
    P2[#P2 + 1], P2[#P2 + 2] = pts[2 * k - 1], pts[2 * k]
    H2[#H2 + 1] = hs[k]
    K2[#K2 + 1] = kinds[k - 1]
    if onLink[k - 1] then L2[#K2] = true end
    if bends[k] then B2[#H2] = true end
  end
  local function Free(m) return (kinds[m] == WALK or kinds[m] == ROAD) and not onLink[m] end
  local changed = false
  local m = 1
  while m <= n - 1 do
    if Free(m) then
      local m2 = m
      while m2 + 1 <= n - 1 and Free(m2 + 1) do m2 = m2 + 1 end
      local snap = WG.SnapRun(c, x, pts, kinds, hs, m, m2 + 1, tx, ty)
      if snap then
        changed = true
        for k = m + 1, snap.i do Keep(k) end
        for _, o in ipairs(snap.pts) do
          P2[#P2 + 1], P2[#P2 + 2] = o.x, o.y
          H2[#H2 + 1] = o.z
          K2[#K2 + 1] = o.kind
          if o.bend then B2[#H2] = true end
        end
        P2[#P2 + 1], P2[#P2 + 2] = pts[2 * snap.j - 1], pts[2 * snap.j]
        H2[#H2 + 1] = hs[snap.j]
        K2[#K2 + 1] = snap.jkind or WALK
        if bends[snap.j] then B2[#H2] = true end
        for k = snap.j + 1, m2 + 1 do Keep(k) end
      else
        for k = m + 1, m2 + 1 do Keep(k) end
      end
      m = m2 + 1
    else
      Keep(m + 1)
      m = m + 1
    end
  end
  if not changed then return pts, kinds, hs, onLink, bends end
  return P2, K2, H2, L2, B2
end

-- Leg route r (WG.Pull's) with its merges onto roads shaped (WG.SnapPieces) at the costs' road price x.road: a new
-- route, or r itself when none changed (none with no road preference).
function WG.SnapRoute(c, r, x, tx, ty)
  if not (r and r.pts and r.fz and x and x.road and x.road < 1) or r.throughGuards then return r end
  local pts, kinds, hs, onLink, bends = WG.SnapPieces(c, r.pts, r.kinds, r.fz, r.onLink or {}, r.bends or {}, x, tx, ty)
  if pts == r.pts then return r end
  local ROAD = R().KIND_ROAD or 0
  local length, roadYd = 0, 0
  for m = 1, #kinds do
    local d = Dist(pts[2 * m - 1], pts[2 * m], pts[2 * m + 1], pts[2 * m + 2])
    length = length + d
    if kinds[m] == ROAD then roadYd = roadYd + d end
  end
  local out = {}
  for k, v in pairs(r) do out[k] = v end
  out.pts, out.kinds, out.fz, out.onLink, out.bends, out.length, out.road = pts, kinds, hs, onLink, bends, length, roadYd
  out.snapped = true
  return out
end

---------------------------------------------------------------------------------------------------- legs
-- The corridor round route r: inside(x, y), CORRIDOR_YD round its points (buckets of CORRIDOR_BUCKET). In a background
-- job it pauses when the slice is over (Router.SliceOver): the wide one round a 3.5 km leg filled 170,000 buckets in one
-- go, a 15 ms slice (2026-11-23, the sand south of Gadgetzan to Uldum, its plan's leg from Steamwheedle Port).
WG.CORRIDOR_CLOCK_EVERY = 4 -- (points between looks at the slice's clock)
function WG.Corridor(r, yd)
  local B = WG.CORRIDOR_BUCKET
  local Rt = R()
  local n = 0
  local set = {}
  local pad = math.ceil((yd or WG.CORRIDOR_YD) / B)
  local pts = r.pts
  for i = 1, #pts / 2 - 1 do
    local ax, ay, bx, by = pts[2 * i - 1], pts[2 * i], pts[2 * i + 1], pts[2 * i + 2]
    local m = max(1, floor(Dist(ax, ay, bx, by) / (B / 2)))
    for q = 0, m do
      local x, y = ax + (bx - ax) * q / m, ay + (by - ay) * q / m
      local kx, ky = floor(x / B), floor(y / B)
      for dx = -pad, pad do
        for dy = -pad, pad do set[(kx + dx) * 65536 + ky + dy] = true end
      end
      n = n + 1
      if n % WG.CORRIDOR_CLOCK_EVERY == 0 and Rt.SliceOver and Rt.SliceOver() then coroutine.yield() end
    end
  end
  return function(x, y) return set[floor(x / B) * 65536 + floor(y / B)] == true end
end

WG.routes, WG.order = {}, {}
-- Long legs searched in vain, by target: a start within FAIL_REUSE_YD of one isn't searched again (no way: the trip's
-- other plans). Item 59, Kooki3z 2026-11-24 on the live client, long waits on trips across zones: Durotar to Un'Goro
-- searched the long leg to the crater 13 times from a few starts, 200k nodes each, the leg cache (CACHE) having let the
-- first answers go; 1.66M nodes before it settled by Gadgetzan. At most FAIL_KEEP targets (the oldest dropped).
WG.FAIL_REUSE_YD, WG.FAIL_KEEP = 1000, 64
WG.FAIL_SIDE_YD, WG.FAIL_NEARER = 3000, 1.25 -- (... or within FAIL_SIDE_YD, the failed start no more than this times as far)
WG.failed, WG.failOrder = {}, {}
-- Stops the grid didn't reach from a short leg's start within its whole budget (WG.Walk): [target key] = GetTime() then.
-- Any leg to one is no way at once for UNREACHED_SECONDS; WG.Reset forgets them.
WG.UNREACHED_SECONDS = 120
WG.UNREACHED_LEG_YD = 1000 -- (only a leg this short, straight, to one of the trip's stops marks it)
WG.unreached = {}
local function TargetKey(cont, tx, ty, tz)
  return string.format("%d>%.0f:%.0f:%s", cont, tx, ty, tz and string.format("%.0f", tz) or "-")
end
function WG.Unreached(cont, tx, ty, tz)
  WG.unreached[TargetKey(cont, tx, ty, tz)] = GetTime and GetTime() or 0
  WG.stats.unreached = (WG.stats.unreached or 0) + 1
end
-- Whether any floor at the stop (x, y) on `cont` is unreached (WG.IsUnreached, at whatever height).
function WG.StopUnreached(cont, x, y)
  if not (cont and x and y) or not next(WG.unreached) then return false end
  local pre = string.format("%d>%.0f:%.0f:", cont, x, y)
  local tNow = GetTime and GetTime() or 0
  for k, t in pairs(WG.unreached) do
    if k:sub(1, #pre) == pre and tNow - t <= WG.UNREACHED_SECONDS then return true end
  end
  return false
end
function WG.IsUnreached(cont, tx, ty, tz)
  local k = TargetKey(cont, tx, ty, tz)
  local t = WG.unreached[k]
  if not t then return false end
  if (GetTime and GetTime() or 0) - t > WG.UNREACHED_SECONDS then
    WG.unreached[k] = nil
    return false
  end
  return true
end
-- (`cut`: its search stopped by its node budget, not out of ground: skipped again like the others (the ride check's legs
-- to far flight masters, searched again and again otherwise), but never a leg to one of the trip's own stops (Nav.stops):
-- the way there is searched again, never written off. Items 80/81, Kooki3z by Astranaar: the walk to the stop cut short
-- and skipped for the rest of the session, the trip pending for minutes or round by Booty Bay's boat)
WG.STOP_NEAR_YD = 30
local function ToAStop(tx, ty)
  local N = ns.Nav
  for _, s in ipairs(N and N.stops or {}) do
    if s.x and Dist(s.x, s.y, tx, ty) <= WG.STOP_NEAR_YD then return true end
  end
  return false
end
function WG.Failed(tkey, sx, sy, tx, ty, cut)
  if Dist(sx, sy, tx, ty) < WG.LONG_LEG_YD then return end
  local list = WG.failed[tkey]
  if not list then
    list = {}
    WG.failed[tkey] = list
    WG.failOrder[#WG.failOrder + 1] = tkey
    while #WG.failOrder > WG.FAIL_KEEP do WG.failed[table.remove(WG.failOrder, 1)] = nil end
  end
  list[#list + 1] = { sx, sy, cut = cut or nil }
  WG.stats.failedLegs = (WG.stats.failedLegs or 0) + 1
end
function WG.FailedNear(tkey, sx, sy, tx, ty)
  local list = WG.failed[tkey]
  if not list or Dist(sx, sy, tx, ty) < WG.LONG_LEG_YD then return false end
  local d = Dist(sx, sy, tx, ty)
  local toStop = nil
  for _, p in ipairs(list) do
    if p.cut then
      if toStop == nil then toStop = ToAStop(tx, ty) end
    end
    local apart = not (p.cut and toStop) and Dist(p[1], p[2], sx, sy) or math.huge
    -- (or from further round, no nearer the target: Ratchet's and Orgrimmar's flight masters after Razor Hill's)
    if apart <= WG.FAIL_REUSE_YD or (apart <= WG.FAIL_SIDE_YD and Dist(p[1], p[2], tx, ty) <= d * WG.FAIL_NEARER) then
      WG.stats.failSkipped = (WG.stats.failSkipped or 0) + 1
      return true
    end
  end
  return false
end
-- A short leg to one of the trip's stops whose way is long round (item 139, Kooki3z 2026-11-27: Darkshore's west coast
-- road, 40.2, 64.2, to Felwood behind the ridge, 985 yd straight, the walk 8-10k yd south through Ashenvale): its
-- search floods the shut-in coast before it leaves it, 135k nodes, over the short leg's budget (NODES_PER_YD: 109k) and
-- the guards' cap (HOSTILE_CAP 80k) at every Road tolerance. Cut short, its stop was "unreached" for UNREACHED_SECONDS,
-- then searched again the same way: "Working out the route..." for good, 190k nodes every two minutes. Now such a
-- search, cut short, is searched once more with the long legs' whole budget (MAX_NODES, `wholeBudget`); cut short then
-- too, it's no way for good from round there (EXHAUSTED_YD; till WG.Reset): "No way found yet", not searched again.
WG.EXHAUSTED_YD = 300
WG.exhausted = {}
function WG.ExhaustedNear(tkey, sx, sy)
  for _, p in ipairs(WG.exhausted[tkey] or {}) do
    if Dist(p[1], p[2], sx, sy) <= WG.EXHAUSTED_YD then return true end
  end
  return false
end
function WG.Exhausted(tkey, sx, sy, tx, ty, nodes)
  local list = WG.exhausted[tkey] or {}
  WG.exhausted[tkey] = list
  list[#list + 1] = { sx, sy }
  WG.stats.exhausted = (WG.stats.exhausted or 0) + 1
  local D = ns.Debug
  if D and D.Log then
    pcall(D.Log, "worldgrid no way within the whole budget", { from = string.format("%.0f,%.0f", sx, sy),
      to = string.format("%.0f,%.0f", tx, ty), nodes = nodes })
  end
end
local function Remember(key, r)
  if not WG.routes[key] then WG.order[#WG.order + 1] = key end
  WG.routes[key] = r
  while #WG.order > WG.CACHE do WG.routes[table.remove(WG.order, 1)] = nil end
end
local function ZKey(z) return z and string.format("%.0f", z) or "-" end

-- A route found for the same stop from a start this near the new one: joined straight onto it (where the grid walks
-- that line) instead of searching again. The player moves on while a long leg is worked out: keyed on the exact yard,
-- every step started a new search, each finished one re-planned the trip and the next step's was never ready
-- (Kooki3z 2026-11-22 in game: the route stayed on "Working out the route..." and the addon's memory climbed past 500 MB)
WG.REUSE_YD = 60
WG.REUSE_SHARE, WG.REUSE_MAX_YD = 0.1, 200
WG.JOIN_FLOOR_Z = 6 -- yards: a join onto it arrives this near the route's height there (on its floor), or none
WG.MAX_JOBS = 2 -- grid searches queued or running at once (more asked for meanwhile: the Router's own, asked again)
WG.WAIT_MAX_SECONDS = 60 -- a leg waits on one grid search this long at most (item 56): then a fast one beside it
WG.HEUR_RUSH = 4 -- (that fast search's heuristic weight: found in few nodes, a little longer; the slow one swapped in later)
-- A search waited on too long (WAIT_MAX_SECONDS): put behind the queue, counted and said in the debug log.
-- Whether a search is waited on past WAIT_MAX_SECONDS with no fast one beside it yet (Nav works the route out again
-- then: the leg asked for anew gets its fast search, WG.Walk).
function WG.StaleWait()
  local tNow = GetTime and GetTime() or 0
  for _, j in pairs(WG.jobs) do
    if not j.rush and not j.rushed and not j.inJob and tNow - (j.since or tNow) > WG.WAIT_MAX_SECONDS then return true end
  end
  return false
end
function WG.WaitedTooLong(key, j, secs)
  WG.stats.waitedOut = (WG.stats.waitedOut or 0) + 1
  -- (put behind the rest of the queue: first in line, a search that never ends took every slice)
  j.rushed = true
  local Rt = ns.Router
  if Rt and Rt.Demote then Rt.Demote(j.qkey or ("worldgrid:" .. key)) end
  local D = ns.Debug
  if D and D.Log then
    pcall(D.Log, "worldgrid wait", { key = key, seconds = math.floor(secs), jobs = WG.jobCount,
      queue = ns.Router and ns.Router.JobList and #ns.Router.JobList() or nil })
  end
  return false
end
WG.jobs, WG.jobCount = {}, 0
WG.targets = {} -- [target key] = { [route key] = { sx, sy, route } }, the finished ones (as WG.routes holds them)

-- (route r from its point nearest (sx, sy) on, with (sx, sy) first: a copy)
local function JoinOnto(c, r, sx, sy, sz, opts)
  local pts, kinds, fz = r.pts, r.kinds, r.fz
  local best, bi, bt
  for i = 1, #pts / 2 - 1 do
    local ax, ay, bx, by = pts[2 * i - 1], pts[2 * i], pts[2 * i + 1], pts[2 * i + 2]
    local vx, vy = bx - ax, by - ay
    local L2 = vx * vx + vy * vy
    local t = L2 > 0 and max(0, min(1, ((sx - ax) * vx + (sy - ay) * vy) / L2)) or 0
    local d = Dist(sx, sy, ax + vx * t, ay + vy * t)
    if not best or d < best then best, bi, bt = d, i, t end
  end
  -- (a long route's, further: REUSE_SHARE of its length past the join, up to REUSE_MAX_YD; mounted, the player was past
  -- REUSE_YD before a long leg's search was done, every time, and the stand-in stayed; Tanaris 2026-11-23)
  if not best then return nil end
  if best > WG.REUSE_YD then
    local left = 0
    for i = bi, #pts / 2 - 1 do left = left + Dist(pts[2 * i - 1], pts[2 * i], pts[2 * i + 1], pts[2 * i + 2]) end
    if best > min(WG.REUSE_MAX_YD, WG.REUSE_SHARE * left) then return nil end
  end
  local jx, jy = pts[2 * bi - 1] + (pts[2 * bi + 1] - pts[2 * bi - 1]) * bt, pts[2 * bi] + (pts[2 * bi + 2] - pts[2 * bi]) * bt
  local jz = fz and fz[bi] and fz[bi + 1] and fz[bi] + (fz[bi + 1] - fz[bi]) * bt or (fz and fz[bi]) or nil
  -- (never a straight join across the guards or an elite area the route went round, the towns at the leg's ends left out
  -- as its search's (WG.Costs): a small search to it instead, by the costs, JoinBySearch. A route through them where it's
  -- joined is joined as before. Item 132)
  local Rt = R()
  local side = best > 1 and Rt.HostileSide and Rt.HostileSide() or nil
  if side then
    local n = #pts
    local hx = { cont = c.cont, side = side,
      exempt = Rt.EndsExempt and Rt.EndsExempt(c.cont, side, sx, sy, pts[n - 1], pts[n]) or nil }
    if WG.GuardsOnLine(hx, sx, sy, jx, jy) and not Rt.HostileAt(c.cont, jx, jy, side, hx.exempt) then return nil end
  end
  -- (the straight join walked on the grid, from the start's surface, arriving on the route's floor there: a route
  -- found from a start on another floor, under the start's (a cave under the hill, a city's halls under its mountain),
  -- was joined straight down onto through the floor; the underground sweep, 2026-11-23: from the mountain over
  -- Ironforge, 210 yd down to Hjoldir)
  if best > 1 then
    local st = Ends(c, sx, sy, sz, opts and opts.swimming, opts and opts.indoors, WG.StartZs(opts, sx, sy))[1]
    local crossed = st and WG.Line(c, st.id, st.key, st.ci, sx, sy, jx, jy)
    if not crossed then return nil end
    if jz then
      local e = crossed[#crossed]
      local et = WG.Tile(c, e.key)
      if not et or abs(Z(c, et, e.id - e.key * SHIFT) - jz) > WG.JOIN_FLOOR_Z then return nil end
    end
  elseif sz and jz and abs(sz - jz) > WG.JOIN_FLOOR_Z then
    return nil
  end
  local out = { pts = { sx, sy }, kinds = {}, fz = { (sz or jz) }, worldGrid = true, onLink = {}, bends = {} }
  local function Put(x, y, z, kind, link)
    local n = #out.pts
    if abs(out.pts[n - 1] - x) < 0.05 and abs(out.pts[n] - y) < 0.05 then return end
    out.pts[n + 1], out.pts[n + 2] = x, y
    out.kinds[#out.kinds + 1] = kind
    out.fz[#out.fz + 1] = z
    if link then out.onLink[#out.kinds] = true end
  end
  Put(jx, jy, jz, kinds[bi], r.onLink and r.onLink[bi])
  for i = bi + 1, #pts / 2 do Put(pts[2 * i - 1], pts[2 * i], fz and fz[i], kinds[i - 1], r.onLink and r.onLink[i - 1]) end
  local length, road = 0, 0
  for m = 1, #out.kinds do
    local d = Dist(out.pts[2 * m - 1], out.pts[2 * m], out.pts[2 * m + 1], out.pts[2 * m + 2])
    length = length + d
    if out.kinds[m] == (R().KIND_ROAD or 0) then road = road + d end
  end
  out.length, out.road = length, road
  return out
end

-- (JoinOnto's straight join blocked on the grid, a dune's edge or a rock between: the route reached by a small search
-- instead, to its points within JOIN_SEARCH_YD of the start, at most JOIN_SEARCH_NODES; the rest of it as it is. Item 27,
-- the coordinator 2026-11-24: the ride check's start, rounded 15 yd off the player's on Tanaris' sands, flooded the whole
-- 3.4k yd way round again, 100k nodes, as the straight 15 yd to the route was blocked)
WG.JOIN_SEARCH_YD, WG.JOIN_SEARCH_NODES = 120, 2500
local function JoinBySearch(c, r, sx, sy, sz, opts)
  local pts, kinds, fz = r.pts, r.kinds, r.fz
  local n = #pts / 2
  local goals, at = {}, {}
  local cell = c.cell
  local near, nx, ny
  for i = 1, n - 1 do
    local ax, ay, bx, by = pts[2 * i - 1], pts[2 * i], pts[2 * i + 1], pts[2 * i + 2]
    local L = Dist(ax, ay, bx, by)
    local m = max(1, math.ceil(L / cell))
    for q = 0, m - 1 do
      local t = q / m
      local px, py = ax + (bx - ax) * t, ay + (by - ay) * t
      local d = Dist(sx, sy, px, py)
      if d <= WG.JOIN_SEARCH_YD then
        local pz = fz and fz[i] and fz[i + 1] and fz[i] + (fz[i + 1] - fz[i]) * t or (fz and fz[i]) or nil
        for _, e in ipairs(Ends(c, px, py, pz)) do
          if not goals[e.id] then goals[e.id], at[e.id] = e.cost, { i, px, py, pz } end
        end
        if not near or d < near then near, nx, ny = d, px, py end
      end
    end
  end
  if not next(goals) then return nil end
  local starts = Ends(c, sx, sy, sz, opts and opts.swimming, opts and opts.indoors, WG.StartZs(opts, sx, sy))
  if not starts[1] then return nil end
  local x = WG.Costs(c, sx, sy, nx, ny, opts) or {}
  x.nodeCap = WG.JOIN_SEARCH_NODES
  local steps = WG.Search(c, starts, goals, nx, ny, nil, x)
  local hit = steps and at[steps[#steps].id]
  if not hit then return nil end
  local i, jx, jy, jz = hit[1], hit[2], hit[3], hit[4]
  local head = WG.Pull(c, steps, sx, sy, jx, jy, x)
  if not (head and head.pts) then return nil end
  local out = { pts = {}, kinds = {}, fz = {}, worldGrid = true, onLink = {}, bends = {} }
  for k = 1, #head.pts do out.pts[k] = head.pts[k] end
  for k = 1, #head.kinds do
    out.kinds[k] = head.kinds[k]
    if head.onLink and head.onLink[k] then out.onLink[k] = true end
  end
  for k = 1, #head.pts / 2 do out.fz[k] = head.fz and head.fz[k] or nil end
  local function Put(px, py, pz, kind, link)
    local m = #out.pts
    if abs(out.pts[m - 1] - px) < 0.05 and abs(out.pts[m] - py) < 0.05 then return end
    out.pts[m + 1], out.pts[m + 2] = px, py
    out.kinds[#out.kinds + 1] = kind
    out.fz[#out.kinds + 1] = pz
    if link then out.onLink[#out.kinds] = true end
  end
  out.fz[#out.pts / 2] = out.fz[#out.pts / 2] or jz
  for k = i + 1, n do Put(pts[2 * k - 1], pts[2 * k], fz and fz[k], kinds[k - 1], r.onLink and r.onLink[k - 1]) end
  local length, road = 0, 0
  for m = 1, #out.kinds do
    local d = Dist(out.pts[2 * m - 1], out.pts[2 * m], out.pts[2 * m + 1], out.pts[2 * m + 2])
    length = length + d
    if out.kinds[m] == (R().KIND_ROAD or 0) then road = road + d end
  end
  out.length, out.road = length, road
  WG.stats.joinSearched = (WG.stats.joinSearched or 0) + 1
  return out
end
WG.JoinBySearch = JoinBySearch -- (tests)

-- A long leg's best way, searched in the background after its weighed search's (item 38): at HEUR, low in the queue
-- (the trip's other walks first); kept for the leg when REFINE_GAIN cheaper (by the search's own costs: climbs, water,
-- the zones too high) than the one shown, and the trip worked out
-- again with it. A leg searched again meanwhile (another key) is left alone.
WG.REFINE_GAIN = 0.005 -- (one swap a leg, when its search is done: any real gain, the line never flips back)
-- The refine is bounded (the route-speed study, 2026-11-25): searched anywhere at HEUR with the landmark fields it took
-- 41k-396k nodes a leg, stopped at MAX_NODES with nothing on the longest (Camp Taurajo to Un'Goro, the Crossroads to
-- Gadgetzan: 60-94% of a long trip's search time), and ended 0.2-11% over the best way where it finished (the fields'
-- bounds by blocks aren't consistent). Now: within REFINE_CORRIDOR_YD of the weighed search's own way (WG.StepCorridor),
-- the straight line its only bound (`noAlt`), no node limit (`noLimit`: the corridor is its bound, never cut short):
-- 28k-100k nodes on the same legs, the way 0-2% over the best.
WG.REFINE_CORRIDOR_YD = 400
-- The blocks (ALT_BLOCK cells square) within `yd` of a search's `steps`: inside(x, y) for WG.Search, and how many blocks.
function WG.StepCorridor(c, steps, yd)
  local B = WG.ALT_BLOCK
  local cell = c.cell
  local ring = math.ceil(yd / (B * cell))
  local set, n, last = {}, 0, nil
  for _, st in ipairs(steps) do
    local t = WG.Tile(c, st.key)
    if t then
      local bx, by = floor((t.gx0 + floor(st.ci / c.per)) / B), floor((t.gy0 + st.ci % c.per) / B)
      local bk = BlockKey(bx, by)
      if bk ~= last then
        last = bk
        for i = -ring, ring do
          for j = -ring, ring do
            local k = BlockKey(bx + i, by + j)
            if not set[k] then set[k], n = true, n + 1 end
          end
        end
      end
    end
  end
  return function(px, py)
    return set[BlockKey(floor(floor(px / cell) / B), floor(floor(py / cell) / B))] == true
  end, n
end
-- (the refine's costs and corridor from the weighed search's: `x` copied, its weight and node cap off)
function WG.RefineCosts(c, x, steps)
  local x2 = {}
  for k, v in pairs(x) do x2[k] = v end
  x2.heur, x2.nodeCap, x2.noAlt, x2.noLimit = nil, nil, true, true
  return x2, (WG.StepCorridor(c, steps, WG.REFINE_CORRIDOR_YD))
end
function WG.Refine(c, key, rf, sx, sy, tx, ty)
  local Rt = R()
  if not Rt.Background then return false end
  return Rt.Background("worldgrid-refine:" .. key, function()
    local x2, inside = WG.RefineCosts(c, rf.x, rf.steps)
    local s2 = WG.Search(c, rf.starts, rf.goals, tx, ty, inside, x2)
    WG.stats.refineNodes = (WG.stats.refineNodes or 0) + (WG.lastNodes or 0)
    WG.stats.refineCut = (WG.stats.refineCut or 0) + (x2.limitHit and 1 or 0)
    local cost2 = s2 and WG.lastCost
    local r2 = s2 and WG.Pull(c, s2, sx, sy, tx, ty, x2)
    if r2 then r2 = WG.SnapRoute(c, r2, x2, tx, ty) end
    if r2 then r2.searchCost = cost2 end
    return r2 or false
  end, function(better)
    local kept = WG.routes[key]
    if not (better and kept and kept.route) then return end
    if (better.searchCost or math.huge) < (rf.cost or math.huge) * (1 - WG.REFINE_GAIN) then
      better.throughGuards = kept.route.throughGuards -- (the same costs' way: through the guards still, if it was)
      kept.route = better
      WG.stats.refined = (WG.stats.refined or 0) + 1
      local N = ns.Nav
      if N and N.Invalidate and WG.On() then N.Invalidate(true) end
    end
  end, nil, true)
end

-- The grid's walk from (sx, sy[, sz]) to (tx, ty[, tz]) on `cont`: a route, false (no way: the Router's own), nil (not
-- worked out yet, asked from inside another background job: the Router's own for now) or "pending" (searched in the
-- background; worked out again when found). A route for the same stop from within REUSE_YD is joined onto, one being
-- searched from within REUSE_YD is waited for; at most MAX_JOBS searches at once. `opts.swimming`: the start in the water.
-- With "pending" or false, a long leg's Router's own route when worked out here (the stand-in; over open ground, the leg).
function WG.Walk(c, sx, sy, sz, tx, ty, tz, opts)
  local ck = CostKey(opts)
  local tkey = string.format("%d>%.0f:%.0f:%s|%s", c.cont, tx, ty, ZKey(tz), ck)
  -- (the start's floor candidates, Nav.GridCandidates, when it has no height: another start)
  local zs = not sz and WG.StartZs(opts, sx, sy)
  local zsKey = zs and table.concat(zs, ",") or ""
  local key = string.format("%.0f:%.0f:%s%s>", sx, sy, ZKey(sz), zsKey ~= "" and ("~" .. zsKey) or "") .. tkey
  local got = WG.routes[key]
  if got then return got.route or false end
  if WG.FailedNear(tkey, sx, sy, tx, ty) then return false end
  if WG.exhausted[tkey] and WG.ExhaustedNear(tkey, sx, sy) then return false end
  if WG.IsUnreached(c.cont, tx, ty, tz) then return false end
  local Rt = R()
  -- (one found for the same stop from near here, still remembered: joined onto. Not from floor candidates, item 106:
  -- the join would start on the first of them, the search keeps the cheapest)
  local seen = not zs and WG.targets[tkey]
  if seen then
    for rk, e in pairs(seen) do
      local kept = WG.routes[rk]
      if not kept then
        seen[rk] = nil
      elseif kept.route then
        local j = JoinOnto(c, kept.route, sx, sy, sz, opts)
        if not j and Dist(sx, sy, e[1], e[2]) <= WG.REUSE_YD then j = JoinBySearch(c, kept.route, sx, sy, sz, opts) end
        if j then return j end -- (not remembered: the searched one stays in WG.routes, the joins are cheap)
      end
    end
  end
  local refine -- (a long leg's best way still to search: WG.Refine)
  local rushing -- (this search the fast one beside a slow one: set below)
  -- (the ride check's walk, Nav's CompareRide (`opts.side`), not to one of the trip's stops: SIDE_WALK_CAP. To a stop
  -- too once the walk all the way is known, `opts.sideStop`: a plan's last walk from a far dock)
  local sideWalk = opts and opts.side and (opts.sideStop or not ToAStop(tx, ty)) or nil
  local function Work()
    local route = false
    local starts, goals = Ends(c, sx, sy, sz, opts and opts.swimming, opts and opts.indoors, WG.StartZs(opts, sx, sy)), {}
    for _, e in ipairs(Ends(c, tx, ty, tz)) do goals[e.id] = e.cost end
    WG.UnderGoals(c, tx, ty, tz, goals)
    WG.NearGoals(c, tx, ty, tz, goals)
    if starts[1] and next(goals) then
      -- (Kooki3z 2026-11-23: "we have to get rid of the fallback option, its fighting routing too much": the grid's
      -- search on its own, no corridor round the Router's own way nor its walk over open ground taken instead; their
      -- walks were searched first and held a long leg's search back). Within its node budget (NODES_PER_YD): a stop it
      -- can't reach is no way (WG.NoWay), said and logged.
      local inside = nil
      do
        local x = WG.Costs(c, sx, sy, tx, ty, opts)
        local n0 = WG.stats.nodes
        -- (a leg tile to tile first, HPA* (item 127, WorldHPA.lua): its way, or no way for sure; else, or when it can't
        -- tell, the grid's own search)
        -- (a leg whose straight line passes the other faction's guards: its searches round them and through them as
        -- 1.4.1 made them, so the trip walks through and asks, not hearths (item 51); HPA* would only add to them)
        -- (nor a plan's side walk, the ride check's, where the guards are avoided: its cap and its way through as 1.4.1
        -- weighed them, never a far dock's walk past them found where 1.4.1's gave up, more plans for the background)
        local guardLine = x.side and WG.GuardsOnLine(x, sx, sy, tx, ty)
        local guardSide = sideWalk and x.side ~= nil
        local function Find(xx)
          local HP = ns.WorldHPA
          xx.hpa, xx.hpaNoWay = nil, nil -- (this search's own: not a copied search's, Widen's or Through's)
          if HP and not guardLine and not guardSide and HP.Usable(c, sx, sy, tx, ty, xx, true) then
            -- (the grid's own search first, as 1.4.1 made it, its own budget and caps; tile to tile only when that one is
            -- cut short, in place of the wider searches after it (the whole budget, the next cap). The hpa-bench,
            -- 2026-11-27: tile to tile first, or after a first try of its own, was slower to settle on 15-18 of 100
            -- trips: the weighed search with the landmark fields finds most long legs in fewer nodes)
            local got0 = WG.Search(c, starts, goals, tx, ty, inside, xx)
            if got0 or not xx.limitHit then return got0 end
            local pre = HP.Search(c, starts, goals, tx, ty, xx, true)
            if pre == false then
              xx.limitHit, xx.hpaNoWay = nil, true
              WG.stats.hpaNoWay = (WG.stats.hpaNoWay or 0) + 1
              return nil
            end
            if pre ~= "ok" then return nil end -- (cut short, as 1.4.1's: the wider searches after it as ever)
            xx.hpaPre = true
            local got = HP.Search(c, starts, goals, tx, ty, xx)
            xx.hpaPre = nil
            if got then
              xx.hpa, xx.limitHit = true, nil
              WG.stats.hpa = (WG.stats.hpa or 0) + 1
              return got
            end
            if got == false then
              xx.limitHit, xx.hpaNoWay = nil, true
              WG.stats.hpaNoWay = (WG.stats.hpaNoWay or 0) + 1
              return nil
            end
            xx.limitHit = true -- (cut short, as the grid's own was)
            return nil
          end
          return WG.Search(c, starts, goals, tx, ty, inside, xx)
        end
        -- (a long leg: inside its corridor first, the whole grid only when there's no way there: item 38)
        -- (a long leg: the heuristic weighed HEUR_LONG, item 38: south of Camp Taurajo to Un'Goro, the one walk 10.4k yd
        -- round, 386k nodes at HEUR, never settled in game; at 3, 88k and 3.5% longer. A route found in seconds beats the
        -- best one found in minutes; the blocks' corridor and guide (WG.BlockCorridor, WG.BlockDistances) didn't help, a
        -- block mixing a mesa's top and the canyon's floor)
        if Dist(sx, sy, tx, ty) >= WG.LONG_LEG_YD then x.heur = WG.HEUR_LONG end
        if rushing then x.heur = max(x.heur or 0, WG.HEUR_RUSH) end -- (waited on too long: item 56)
        -- (round the other faction's guards (x.side): within HOSTILE_CAP nodes, else the walk through them (item 51,
        -- Kooki3z 2026-11-24, a Horde 60 in Dun Morogh: the guard-free way, 11k yd round, took 476k nodes, the cap
        -- ran out after 165 s and the trip settled on a 24-minute hearth and zeppelin; the walk through is 4.6k yd and
        -- 51k nodes). Marked `throughGuards`: its guards' yards are the route's to weigh and say.)
        local guarded = x.side and true or false
        -- (the player said No to "Take it?" on this trip: round the guards however long, never through (53c's step 3;
        -- item 63b, Kooki3z 2026-11-24: "No" left the route through the enemy spot), no way round: no way)
        local refused = guarded and WG.GuardsRefused()
        -- (a long leg's weighed search: its own cap; the fast one beside a slow search (item 56) keeps this one)
        if refused then x.nodeCap = nil
        elseif guarded and (rushing or not x.heur) then x.nodeCap = WG.HOSTILE_CAP
        elseif guarded then x.nodeCap = WG.HOSTILE_LONG_CAP end -- (a long leg's: item 59, 423k nodes round in vain)
        -- (a plan's side walk: SIDE_WALK_CAP at most, its way through the guards too)
        if sideWalk and not refused then x.nodeCap = min(x.nodeCap or huge, WG.SIDE_WALK_CAP) end
        -- (a capital's other crossing tried, WG.Leg: within its own budget, CROSS_WALK_NODES)
        if opts and opts.crossCap then x.nodeCap = min(x.nodeCap or huge, opts.crossCap) end
        x.throughCut = nil
        -- (a short leg to one of the trip's stops: the whole budget, MAX_NODES, not its length's (NODES_PER_YD) nor the
        -- guards' cap when they're not on the straight line (their way through is then no shorter). Item 139: its way
        -- may be long round a ridge; only the trip's own legs, never a plan's side walk, whose cap keeps the ride check
        -- quick. A way found within the old budget is the same way: only a search it cut short goes on)
        -- (not to a stop inside a cave: its way in is the cave's own roads from its mouth, WG.CaveLeg; the grid's walk
        -- straight to its floor is only when there's no road in, a floor the grid seldom reaches. The whole budget there
        -- was 200k nodes more for every no way, and the stop's No way found yet a minute late: the Wailing Caverns stop
        -- with no cave road, Woodpaw Den, 1.4.2's CI)
        local wide = not sideWalk and Dist(sx, sy, tx, ty) < WG.LONG_LEG_YD and ToAStop(tx, ty)
          and not WG.InCave(c.cont, tx, ty, tz)
        local widened, wideCut, wideNodes = false, nil, 0
        local throughX -- (the way through's costs, once searched)
        local function Widen(xb)
          local x3 = {}
          for k, v in pairs(xb) do x3[k] = v end
          x3.nodeCap, x3.wholeBudget = nil, true
          local n1 = WG.stats.nodes
          local got = Find(x3)
          widened, wideCut, wideNodes = true, x3.limitHit and true or false, WG.stats.nodes - n1
          if x3.limitHit then WG.stats.wideCut = (WG.stats.wideCut or 0) + 1 end
          return got, x3
        end
        local steps
        if wide and not (guarded and not refused and WG.GuardsOnLine(x, sx, sy, tx, ty)) then
          local x3
          steps, x3 = Widen(x)
          x3.wholeBudget = nil -- (its later searches, the way through's, their own budgets)
          x = x3
        else
          steps = Find(x)
        end
        local through = false
        local function Through()
          local x2 = {}
          for k, v in pairs(x) do x2[k] = v end
          x2.side, x2.exempt, x2.light, x2.nodeCap = nil, nil, nil, sideWalk and WG.SIDE_WALK_CAP or nil
          if opts and opts.crossCap then x2.nodeCap = min(x2.nodeCap or huge, opts.crossCap) end
          x2.any = x2.red ~= nil
          local got = Find(x2)
          x.throughCut = x2.limitHit and true or false
          throughX = x2
          return got, x2
        end
        if not steps and guarded and not refused then
          WG.LogThrough(sx, sy, tx, ty, WG.stats.nodes - n0)
          local s2, x2 = Through()
          if s2 then steps, x, through = s2, x2, true end
        elseif steps and guarded and not refused and (not x.heur or x.hpa) then -- (not a long leg's: its length the land's,
          -- its search dear; but a long leg's found tile to tile, HPA*, item 127: its way through as quick to find)
          -- (a way round found: kept only within the usual detour over the way through, DETOUR_FACTOR times it or
          -- DETOUR_YD more (item 53c, Kooki3z's order: round the guards if reasonable, else ask "Take it?" with the way
          -- through (Nav.CheckHostileRoute), and only on a no the long way). Looked at only when the way round is
          -- longer than that over the straight line: the way through is never shorter than it)
          local round = WG.Pull(c, steps, sx, sy, tx, ty, x)
          local D = Dist(sx, sy, tx, ty)
          if round and round.length > math.max(D * WG.DETOUR_FACTOR, D + WG.DETOUR_YD)
              and WG.GuardsOnLine(x, sx, sy, tx, ty) then
            local s2, x2 = Through()
            local thru = s2 and WG.Pull(c, s2, sx, sy, tx, ty, x2)
            if thru and round.length > math.max(thru.length * WG.DETOUR_FACTOR, thru.length + WG.DETOUR_YD) then
              steps, x, through = s2, x2, true
              WG.stats.detourRefused = (WG.stats.detourRefused or 0) + 1
            end
          end
        end
        x.nodeCap = nil
        -- (the start's surface a speck the grid's links leave shut in, a rock's top or a mesh's sliver, every search
        -- over in a few nodes: from the reached floors round it instead, as a spot with no surface of its own is)
        -- (ring after ring, NEAR_CELLS at most, while each ring's floors are a speck too: a spot by Red Cloud Mesa's
        -- palisade has a pocket of a few surfaces between the wall's posts, its ring's floors past the wall left out,
        -- item 78)
        if not steps and WG.stats.nodes - n0 < WG.ISLAND_NODES then
          local tried = {}
          for _, st in ipairs(starts) do tried[#tried + 1] = st end
          for _ = 1, WG.NEAR_CELLS do
            local n1 = WG.stats.nodes
            local more = WG.NearStarts(c, sx, sy, sz, tried)
            if not more[1] then break end
            steps = WG.Search(c, more, goals, tx, ty, nil, x)
            if steps or WG.stats.nodes - n1 >= WG.ISLAND_NODES then break end
            for _, st in ipairs(more) do tried[#tried + 1] = st end
          end
        end
        -- (item 139: the short leg's search cut short by its budget, not out of ground: the whole budget once, with the
        -- costs of the way it last tried (through the guards, when that was searched))
        if not steps and wide and not widened then
          local wasCut
          if guarded and not refused then wasCut = x.throughCut ~= false else wasCut = x.limitHit end
          if wasCut then
            local s3, x3 = Widen(throughX or x)
            if s3 then
              steps, x = s3, x3
              if throughX then through = true end
            elseif not wideCut then
              x.limitHit, x.throughCut = nil, false -- (out of ground with the whole budget: no way, said so)
            end
          end
        end
        -- (and cut short with it too: no way for good from round here, never searched again the same way)
        if not steps and widened and wideCut then WG.Exhausted(tkey, sx, sy, tx, ty, wideNodes) end
        if steps then route = WG.Pull(c, steps, sx, sy, tx, ty, x) end
        -- (remembered as searched in vain only when its search ran out of ground: one stopped by its node budget, the
        -- guards' cap's way through included, proves nothing. Items 80/81, Kooki3z by Astranaar: a leg cut short was
        -- skipped for the rest of the session, the trip pending for minutes or round by Booty Bay's boat)
        local cut
        if guarded and not refused then cut = x.throughCut ~= false else cut = x.limitHit end
        if not steps and cut and sideWalk then WG.stats.sideCut = (WG.stats.sideCut or 0) + 1 end
        if not steps and cut then WG.stats.failCut = (WG.stats.failCut or 0) + 1 end
        if not steps then WG.Failed(tkey, sx, sy, tx, ty, cut) end
        -- (one of the trip's stops not reached within a short leg's whole budget (UNREACHED_LEG_YD): the stop's floor is
        -- what the grid can't reach (a cave's inner floor, item 84c), from anywhere. Every other leg to it said no way at
        -- once (WG.Unreached), never searched again from the flight masters the ride check weighs: Kooki3z's route into
        -- the Wailing Caverns hung. Only the trip's stops, and short legs: a flight master's walk cut short from 2-3k yd
        -- off says nothing of the others (test_a10_..._chillwind_camp: its plan lost the flight))
        -- (and so is one tile to tile says is no way for sure, HPA*'s after the grid's own search was cut short (item 127),
        -- round the guards and through them alike: its search ran out of tiles, not of budget, so `cut` is false. Not
        -- marked, the Wailing Caverns stop with no cave road was searched again from every flight master's plan and never
        -- settled, test_a_stop_the_grid_cant_reach_settles_as_no_way_found_yet, 1.4.2's CI)
        local sure = x.hpaNoWay and (not guarded or refused or (throughX and throughX.hpaNoWay)) and true or false
        if not steps and (cut or sure) and not refused and Dist(sx, sy, tx, ty) <= WG.UNREACHED_LEG_YD
            and ToAStop(tx, ty) then
          WG.Unreached(c.cont, tx, ty, tz)
        end
        if route and through then
          route.throughGuards = true
          WG.stats.throughGuards = (WG.stats.throughGuards or 0) + 1
        end
        -- (the long leg's weighed search found it fast; the best way searched again at HEUR: in the same go when the
        -- walks are worked out at once (the tests, the bake), else after, in the background (WG.Refine), the route
        -- shown meanwhile and swapped only for one REFINE_GAIN shorter, never flipping back and forth)
        -- (not a side walk's (`sideWalk`, the ride check's): only weighed against the walk, never walked as it is (the
        -- trip's own legs are searched apart); its best way searched 120-135k nodes more a dock on the Dun Morogh trip)
        -- (a long leg's found tile to tile too, HPA*: its refine round its way, as cheap as it was or cheaper, item 127's
        -- "the same quality"; 51-131k nodes in the background, after the trip's own walks)
        if x.heur and route and not sideWalk then
          local cost1 = WG.lastCost or math.huge
          if Rt.SYNC_WALKS then
            local x2, inside2 = WG.RefineCosts(c, x, steps)
            local s2 = WG.Search(c, starts, goals, tx, ty, inside2, x2)
            WG.stats.refineNodes = (WG.stats.refineNodes or 0) + (WG.lastNodes or 0)
            WG.stats.refineCut = (WG.stats.refineCut or 0) + (x2.limitHit and 1 or 0)
            local cost2 = s2 and WG.lastCost
            local better = s2 and WG.Pull(c, s2, sx, sy, tx, ty, x2)
            if better and cost2 and cost2 < cost1 * (1 - WG.REFINE_GAIN) then route = better end
          else
            refine = { starts = starts, goals = goals, x = x, cost = cost1, steps = steps }
          end
        end
        -- (open ground to open ground, no far road: a way by road ground longer than ROAD_DETOUR_MAX times the line
        -- is searched again with no road preference, and that walk is the leg's when the road's way is longer than
        -- ROAD_DETOUR_MAX times it. Kooki3z 2026-11-23: "open ground to open ground tends to want to snap to roads far
        -- away, this shouldn't be the case if it adds that much of a route")
        -- (not below Road tolerance 0: the player asked for the roads)
        local tol = ns.settings and ns.settings.gps and tonumber(ns.settings.gps.roadTolerance) or 0
        -- (and only when the road's share could make it so: the road's way is the cheapest by its costs, so a plain
        -- walk P has length(P) >= length - (1 - x.road) * road; it's taken when length > ROAD_DETOUR_MAX * length(P),
        -- which needs ROAD_DETOUR_MAX * (1 - x.road) * road > (ROAD_DETOUR_MAX - 1) * length. Half that, for the
        -- heuristic's weight. Item 27: Tanaris's way round, 215 of 3.4k yd road, searched twice, 40k nodes more)
        local M = WG.ROAD_DETOUR_MAX
        local roadCould = route and M * (1 - x.road) * (route.road or 0) > (M - 1) * route.length * WG.ROAD_DETOUR_SLACK
        -- (and at any tolerance, a way by road that goes past the stop and back: item 83)
        -- (not a long leg's, nor a way round (longer than OVERSHOOT_ROUND times the line: past the stop's distance to go
        -- round a cliff, not for a road): its second search doubled the landmark trips' nodes, warrior 41k -> 78k)
        local line = Dist(sx, sy, tx, ty)
        local over = route and (route.road or 0) > 0 and x.road < 1 and line < WG.LONG_LEG_YD
          and route.length <= WG.OVERSHOOT_ROUND * line and WG.Overshoots(route, sx, sy, tx, ty)
        if over or (route and roadCould and (route.road or 0) > 0 and x.road < 1 and tol >= 0
            and route.length > WG.ROAD_DETOUR_MAX * Dist(sx, sy, tx, ty)) then
          local x2 = {}
          for k, v in pairs(x) do x2[k] = v end
          x2.road = 1
          local s2 = Find(x2)
          local plain = s2 and WG.Pull(c, s2, sx, sy, tx, ty, x2)
          -- (and only to the same floor: the plain walk may end at another of the goals, a tower's foot for the
          -- archmage up it; bake9's sweep, Archmage Tervosh, Ian Strom, Jadenvis Seawatcher)
          local za, zb = route.fz and route.fz[#route.fz], plain and plain.fz and plain.fz[#plain.fz]
          if plain and (za == nil or zb == nil or abs(za - zb) <= WG.NEAR_FLOOR_Z)
              and (route.length > WG.ROAD_DETOUR_MAX * plain.length
                or over and plain.length < route.length and not WG.Overshoots(plain, sx, sy, tx, ty)) then
            if over then WG.stats.overshoots = (WG.stats.overshoots or 0) + 1 end
            refine = nil -- (its best way is the road's, searched again: never the overshoot back in)
            WG.stats.unroaded = (WG.stats.unroaded or 0) + 1
            route = plain
          end
        end
        -- (its merges onto roads shaped last, once its search and the searches again are decided, at this tolerance's
        -- road price, the plain walk's too: a road near it that runs its way taken as at any other. Item 57)
        if route then route = WG.SnapRoute(c, route, x, tx, ty) end
      end
    end
    Remember(key, { route = route })
    WG.targets[tkey] = WG.targets[tkey] or {}
    WG.targets[tkey][key] = { sx, sy }
    if refine then WG.Refine(c, key, refine, sx, sy, tx, ty) end
    return route
  end
  if Rt.SYNC_WALKS then return Work() end
  -- (one being searched for the same stop from within REUSE_YD: waited for, the line meanwhile. From further, its
  -- own search: a plan's other leg to the same stop, from Steamwheedle Port to Uldum's entrance, held up the walk there
  -- from the sand south of Gadgetzan for the 4 s it searched, 2026-11-23. A job the Router no longer has queued is
  -- gone (dropped without a word): out of the list, never waited on)
  -- (and never waited on past WAIT_MAX_SECONDS: a fast search beside it (WG.HEUR_RUSH, the long legs' kind of weighed
  -- search, found in a fraction of the nodes), the slow one put behind the queue and swapped in when it lands. Not the
  -- Router's own route: no fallback. Item 56, Kooki3z 2026-11-24: Orgrimmar to the Crossroads "Working out the
  -- route..." for 4+ minutes, not seen again; whatever held it, a route never waits on one search for good. Said in the
  -- debug log: `worldgrid wait`)
  local tNow = GetTime and GetTime() or 0
  local oldest, rush
  for jk, j in pairs(WG.jobs) do
    if Rt.Queued and not Rt.Queued(j.qkey or ("worldgrid:" .. jk)) then
      WG.jobs[jk] = nil
      WG.jobCount = max(0, WG.jobCount - 1)
    else
      if not j.rush and (not oldest or (j.since or tNow) < oldest) then oldest = j.since or tNow end
      if j.tkey == tkey and Dist(j.sx, j.sy, sx, sy) <= max(WG.REUSE_YD, min(WG.REUSE_MAX_YD, WG.REUSE_SHARE * Dist(sx, sy, tx, ty))) then
        if j.inJob then return "pending" end -- (queued by a plan's weighing: its leg is coming, not no way)
        if j.rush or j.rushed or tNow - (j.since or tNow) <= WG.WAIT_MAX_SECONDS then return "pending" end
        WG.WaitedTooLong(jk, j, tNow - j.since)
        rush = true
      end
    end
  end
  local co, main = coroutine.running()
  local inJob = co and not main -- (asked inside another job, a plan being weighed: never searched there in one go)
  if WG.jobCount >= WG.MAX_JOBS and not rush then
    if inJob then return "pending" end
    if not (oldest and tNow - oldest > WG.WAIT_MAX_SECONDS) then return "pending" end
    -- (the queue full of searches waited on too long: those put behind, this one searched fast)
    for jk, j in pairs(WG.jobs) do
      if not j.rush and not j.rushed and tNow - (j.since or tNow) > WG.WAIT_MAX_SECONDS then
        WG.WaitedTooLong(jk, j, tNow - j.since)
      end
    end
    rush = true
  end
  local jkey = rush and key .. "!rush" or key
  rushing = rush
  if WG.jobs[jkey] then return "pending" end
  WG.jobs[jkey] = { tkey = tkey, inJob = inJob, sx = sx, sy = sy, since = tNow, rush = rush or nil,
    qkey = "worldgrid:" .. jkey }
  WG.jobCount = WG.jobCount + 1
  WG.stats.pending = WG.stats.pending + 1
  Rt.Background("worldgrid:" .. jkey, Work, function(route)
    WG.jobs[jkey] = nil
    WG.jobCount = max(0, WG.jobCount - 1)
    -- (the trip worked out again once, with this leg's walk ready; with none too (given up, or the Router's own walk
    -- over open ground), the Router's own then: else the stand-in, still marked pending, stayed until something else
    -- worked the route out again, shown faded and "Working out the route..." meanwhile (Nav.StandIn); Kooki3z
    -- 2026-11-23 saw it about a minute)
    -- (found or not: a search that found nothing left the trip on its stand-in for good, nothing asking again. Item 82g,
    -- Kooki3z on b84cff45: a 550 yd trip in the Barrens, its stop on a hill's top the grid can't reach, "Working out
    -- the route..." for minutes. Its answer, none, is remembered (Remember): asked again, the leg is no way at once)
    local N = ns.Nav
    if N and N.Invalidate and WG.On() then N.Invalidate(true) end
  end, (not inJob and Rt.IsFocus and Rt.IsFocus(c.cont, tx, ty)) or nil, nil, function()
    -- (dropped unfinished, a Router reset or an error: out of the count, and the trip asked again, R.Reset)
    if WG.jobs[jkey] then
      WG.jobs[jkey] = nil
      WG.jobCount = max(0, WG.jobCount - 1)
    end
    local N = ns.Nav
    if N and N.Invalidate and WG.On() then N.Invalidate(true) end
  end)
  -- (`first`: the leg to the stop itself before the planner's walks, whatever its length (no Router's own walk to wait
  -- on any more); Mulgore 2026-11-23, Skywatcher Plateau to the plain: the stand-in by the Barrens' roads for 15 s)
  -- (inside a job too: "pending", never nil. Nil read as no walk, and a plan weighed in the background settled on its
  -- rides for good: a 550 yd trip in the Barrens by the Crossroads' flight master (item 82h), Orgrimmar to Astranaar's
  -- edge round by Booty Bay's boat (81). Pending, the plan is provisional and worked out again when the search lands)
  return "pending"
end

-- The reached surfaces in the cells round (x, y) (rings out to NEAR_CELLS; with a height, those within NEAR_FLOOR_Z of
-- it), other than `starts`': where a search from the spot's own surfaces ended in fewer than ISLAND_NODES nodes.
WG.ISLAND_NODES = 400
WG.NEAR_FLOOR_Z = 8
function WG.NearStarts(c, x, y, z, starts)
  local had, out = {}, {}
  local P = ns.Passability
  local MW = P and P.HasModelWalls and P.HasModelWalls(c.cont) and P.CrossesModelWall or nil
  for _, st in ipairs(starts) do had[st.id] = true end
  local gx, gy = floor(x / c.cell), floor(y / c.cell)
  for r = 1, WG.NEAR_CELLS do
    for di = -r, r do
      for dj = -r, r do
        if max(abs(di), abs(dj)) == r then
          local key, ci = CellKey(c, gx + di, gy + dj)
          local t = key and WG.Tile(c, key)
          local n = t and Count(t, ci) or 0
          local f = n > 0 and First(t, ci)
          for k = 0, n - 1 do
            local s = f + k
            local id = key * SHIFT + s
            local sz = Z(c, t, s)
            local px, py = Pt(c, t, s, ci)
            if not had[id] and Bit(Flags(t, s), F_REACH) and (not z or abs(sz - z) <= WG.NEAR_FLOOR_Z)
                and not (MW and MW(c.cont, x, y, px, py)) then -- (never across a model wall: item 78)
              out[#out + 1] = { id = id, key = key, ci = ci, s = s, z = sz, x = px, y = py, cost = Dist(x, y, px, py) }
              had[id] = true
            end
          end
        end
      end
    end
    if out[1] then break end
  end
  return out
end

-- A stop up a floor whose own floor the grid has no way to (a tower's or an inn's stairs the meshes lack: Kargath's
-- tower, 2026-11-23's underground sweep): the floors under it at its spot reached on foot are its ends too, each
-- UNDER_STOP_COST yards and Z_COST a yard under it dearer, so the walk ends at the foot of the building (Nav says the
-- stop is above, N.StopOffGround) rather than no way, which planned a 10k yd walk round to come at it from farther off
-- (where the Router's own straight line was taken). Never a floor over the stop's: that's the ground over a cave, and
-- the walk would end over its head.
WG.UNDER_STOP_YD = 40 -- yards: floors this far under the stop at most
WG.UNDER_STOP_COST = 150
function WG.UnderGoals(c, tx, ty, tz, goals)
  if not tz then return end
  for _, f in ipairs(WG.SurfacesAt(c, tx, ty)) do
    if not goals[f.id] and Bit(f.f, F_REACH) and f.z < tz - WG.FLOOR_Z and f.z >= tz - WG.UNDER_STOP_YD then
      goals[f.id] = Dist(tx, ty, f.x, f.y) + WG.UNDER_STOP_COST + (tz - f.z) * WG.Z_COST
    end
  end
end

-- A stop whose own surfaces the bake's walk doesn't reach (none F_REACH: a hillside too steep, a rock's top): the
-- reached surfaces nearest it as goals too, out to NEAR_GOAL_CELLS (the first ring with any and the next), the last
-- yards straight up to it. Else the search could never arrive, flooded the ground round and gave up, and the whole leg
-- was the Router's own: from north of Booty Bay to a stop on the slope east of Kurzen's Compound, 40 yd up from the
-- valley's reached ground, round by the Mosh'Ogg hills (4.5k yd for 2.9k straight up the valley; Kooki3z 2026-11-23).
-- And a stop with no height whose own cell's surfaces all stand HIGH_GOAL_Z or more over the terrain (Uldum's entrance:
-- its gate's top, 64 and 72, the sand 8): the floors round it at the terrain's height are its goals too. Its gate's
-- top is reached from elsewhere, not from the sands, and the search from Gadgetzan flooded Tanaris and gave up (the
-- Router's own straight walk stood in, Kooki3z 2026-11-23: "ok to just route across the open").
WG.NEAR_GOAL_CELLS = 8
WG.HIGH_GOAL_Z = 10
function WG.NearGoals(c, tx, ty, tz, goals)
  local gz = not tz and ns.Ground and ns.Ground.Sample and ns.Ground.Sample(c.cont, tx, ty) or nil
  local high = gz ~= nil and next(goals) ~= nil
  if high then
    for id in pairs(goals) do
      local t = WG.Tile(c, floor(id / SHIFT))
      if t and Z(c, t, id % SHIFT) < gz + WG.HIGH_GOAL_Z then high = false break end
    end
  end
  if not high then
    for id in pairs(goals) do
      local t = WG.Tile(c, floor(id / SHIFT))
      if t and Bit(Flags(t, id % SHIFT), F_REACH) then return 0 end
    end
  end
  local z = tz or gz or (ns.Ground and ns.Ground.Sample and ns.Ground.Sample(c.cont, tx, ty)) or nil
  local gx, gy = floor(tx / c.cell), floor(ty / c.cell)
  local P = ns.Passability
  local MW = P and P.HasModelWalls and P.HasModelWalls(c.cont) and P.CrossesModelWall or nil
  local n, upto = 0, WG.NEAR_GOAL_CELLS
  for r = 1, WG.NEAR_GOAL_CELLS do
    if r > upto then break end
    for di = -r, r do
      for dj = -r, r do
        if max(abs(di), abs(dj)) == r then
          local key, ci = CellKey(c, gx + di, gy + dj)
          local t = key and WG.Tile(c, key)
          local cnt = t and Count(t, ci) or 0
          local f0 = cnt > 0 and First(t, ci)
          for k = 0, cnt - 1 do
            local s = f0 + k
            local px, py = Pt(c, t, s, ci)
            if Bit(Flags(t, s), F_REACH) and not (MW and MW(c.cont, tx, ty, px, py)) then -- (never across a model wall)
              local id = key * SHIFT + s
              local cost = Dist(tx, ty, px, py) + (z and abs(Z(c, t, s) - z) or 0)
              if not goals[id] or cost < goals[id] then
                goals[id] = cost
                n = n + 1
              end
            end
          end
        end
      end
    end
    if n > 0 and upto == WG.NEAR_GOAL_CELLS then upto = r + 1 end
  end
  return n
end

-- Places the grid's meshes don't have (the Ruins of Lordaeron: Undercity's model, its own level, is left out of the
-- meshes, and the ruins up top are part of it: the grid walked the ground under them, round their outside): a leg with
-- an end there, or a grid route through one, is the Router's own (its ruins' grid, CityHalls, and Undercity's lifts).
-- Kooki3z 2026-11-22: from the ruins' gate to the Rogues' Quarter the route went round the ruins' east side.
WG.NOT_MESHED = { "ruins_of_lordaeron" }
function WG.NotMeshed(cont, x, y)
  local P = ns.Passability
  for _, key in ipairs(WG.NOT_MESHED) do
    local o = ns.Terrain and ns.Terrain[key]
    if o and P and P.InGridRect and ns.CityHalls and ns.CityHalls[cont] then
      for _, k in ipairs(ns.CityHalls[cont]) do
        if k == key and P.InGridRect(o, x, y) then return true end
      end
    end
  end
  return false
end
-- (the boxes of `cont`'s places NotMeshed can say yes in, a cell wider each way: a piece of the route clear of them all
-- isn't sampled. Item 108: a 9.5k yd route was 1,200 samples a call, 12-15 ms, on every leg handed back)
local function NotMeshedBoxes(cont)
  local P, out = ns.Passability, {}
  if not (P and P.InGridRect and ns.CityHalls and ns.CityHalls[cont]) then return out end
  for _, key in ipairs(WG.NOT_MESHED) do
    local o = ns.Terrain and ns.Terrain[key]
    if o and o.tx0 and o.ty0 and o.w and o.h and o.cell then
      for _, k in ipairs(ns.CityHalls[cont]) do
        if k == key then
          local x1, y1 = (32 - o.ty0) * (1600 / 3), (32 - o.tx0) * (1600 / 3)
          local pad = o.cell + 1
          out[#out + 1] = { x1 - o.h * o.cell - pad, x1 + pad, y1 - o.w * o.cell - pad, y1 + pad }
        end
      end
    elseif o then
      return nil -- (a grid without its box: every piece sampled, as before)
    end
  end
  return out
end
WG.NotMeshedBoxes = NotMeshedBoxes
function WG.ThroughNotMeshed(cont, r)
  local p = r.pts
  local boxes = NotMeshedBoxes(cont)
  if boxes and #boxes == 0 then return false end
  for i = 1, #p - 3, 2 do
    local near = not boxes
    if boxes then
      local ax, ay, bx, by = p[i], p[i + 1], p[i + 2], p[i + 3]
      for _, b in ipairs(boxes) do
        if max(ax, bx) >= b[1] and min(ax, bx) <= b[2] and max(ay, by) >= b[3] and min(ay, by) <= b[4] then
          near = true
          break
        end
      end
    end
    if near then
      local L = Dist(p[i], p[i + 1], p[i + 2], p[i + 3])
      local n = max(1, math.ceil(L / 8))
      for q = 0, n do
        if WG.NotMeshed(cont, p[i] + (p[i + 2] - p[i]) * q / n, p[i + 1] + (p[i + 3] - p[i + 1]) * q / n) then return true end
      end
    end
  end
  return false
end

-- Whether the grid's route r passes the other faction's guards GUARD_SLACK_YD or more beyond the Router's own route for
-- the leg (the towns at its ends not counted: Router.HostileTownsNear): then the Router's own is taken, so the grid never
-- walks a player through guards today's routing goes round, and Nav's notes and questions about enemy ground are as
-- today's (Kooki3z 2026-11-22, an Alliance player in Mulgore: the grid's way went through Bloodhoof Village and over
-- Thunder Bluff's mesas, and nothing was asked).
WG.GUARD_SLACK_YD = 10
function WG.GuardYards(cont, r, side, exempt)
  local Rt = R()
  local p, yd = r.pts, 0
  for i = 1, #p - 3, 2 do
    if Rt.Breathe and i % 40 == 1 then Rt.Breathe(1, 1) end
    yd = yd + Rt.HostileYards(cont, p[i], p[i + 1], p[i + 2], p[i + 3], side, exempt)
  end
  return yd
end
-- Whether the grid walks the straight piece (x0, y0)-(x1, y1) cell to cell by its links from any surface of its
-- first cell (no height: any floor; no clearance kept): false over a wall, a building's side, a cliff.
function WG.Open(c, x0, y0, x1, y1)
  local cell = c.cell
  local k0, c0 = CellKey(c, floor(x0 / cell), floor(y0 / cell))
  local t0 = k0 and WG.Tile(c, k0)
  if not t0 or Count(t0, c0) == 0 then return nil end -- (off the grid: can't tell)
  local k1, c1 = CellKey(c, floor(x1 / cell), floor(y1 / cell))
  local t1 = k1 and WG.Tile(c, k1)
  if not t1 or Count(t1, c1) == 0 then return nil end
  local L = Dist(x0, y0, x1, y1)
  local n = max(1, math.ceil(L / (cell / 3)))
  local f0 = First(t0, c0)
  for s0 = f0, f0 + Count(t0, c0) - 1 do
    local key, ci, t, s, gx, gy = k0, c0, t0, s0, floor(x0 / cell), floor(y0 / cell)
    local ok = true
    for q = 1, n do
      local x, y = x0 + (x1 - x0) * q / n, y0 + (y1 - y0) * q / n
      local cx, cy = floor(x / cell), floor(y / cell)
      while ok and (cx ~= gx or cy ~= gy) do
        local ix, iy = cx - gx, cy - gy
        ix = ix > 0 and 1 or ix < 0 and -1 or 0
        iy = iy > 0 and 1 or iy < 0 and -1 or 0
        local d
        for dd = 1, 8 do if DX[dd] == ix and DY[dd] == iy then d = dd break end end
        local kk = Link(t, s, d)
        local nkey, nci = Step(c, key, ci, d)
        local nt = nkey and WG.Tile(c, nkey)
        if kk == 0 or not nt then
          ok = false
        else
          key, ci, t, s = nkey, nci, nt, First(nt, nci) + kk - 1
          gx, gy = gx + ix, gy + iy
        end
      end
      if not ok then break end
    end
    if ok then return true end
  end
  return false
end

-- Buildings whose walls the meshes lack and Kooki3z found walked through (boxes { cont, x0, y0, x1, y1 }): the bake's
-- stop links keep out of them (worldbake.walled_boxes). (bake8: no longer a reason the Router's own straight walk stands
-- in game. Kooki3z 2026-11-23, "imo fall back can't be trusted and should identify where that would be needed and just
-- correct it": where the grid has no way, "No way there found" until the bake covers the place; `agps world-grid
-- coverage` lists them)
WG.WALLED = {
  { 0, -10985, -3395, -10925, -3340 }, -- (Nethergarde Keep's building, Bernie Heisten's: 2026-11-22, map 63.8, 18.0)
}

-- Whether a city grid's walk `inside` and the world grid's `outside` meet on one floor at the crossing (within
-- JOIN_FLOOR_Z): `fromCity` true when the leg starts in the city (inside, then outside), else outside, then inside.
-- Either without heights there: true (nothing to tell by).
function WG.SpliceMeets(inside, outside, fromCity)
  local fi, fo = inside.fz, outside.fz
  if not (fi and fo and fi[1] and fo[1]) then return true end
  local zi = fromCity and fi[#fi] or fi[1]
  local zo = fromCity and fo[1] or fo[#fo]
  if not (zi and zo) then return true end
  return abs(zi - zo) <= WG.JOIN_FLOOR_Z
end

-- The leg (Router.Route's, asked first while the option is on): the grid's walk, "pending", or no way (WG.NoWay); nil
-- only for the city grid's (both ends in one capital, a capital's unmeshed halls) and a continent with no grid.
-- A leg the world grid has no way for with both ends over one city grid's floors that the Router's capital outline
-- leaves out (CityGrid.CityFor: Ironforge's halls under the mountain, where the world grid has only scraps between the
-- capital's own cells, no way between them: bake6's 10,000-route test lost 8 trips there, Pithwick to Dolkin Craghelm
-- among them): the city's grid's walk, or "pending", or nil.
function WG.CityWalk(cont, sx, sy, tx, ty, opts)
  local CG = ns.CityGrid
  if not (CG and CG.On and CG.On() and CG.GridCityAt and CG.Walk) then return nil end
  local a, b = CG.GridCityAt(cont, sx, sy), CG.GridCityAt(cont, tx, ty)
  local name = a or b
  if not name then return nil end
  local cc = CG.City(name)
  if not cc then return nil end
  -- (an end the outline leaves out but the city's grid has floors under: one of its own; the Great Forge's edge, 3 yd
  -- off its pit, outside Ironforge's outline: with no fallback any more, "no way" from the heart of the city)
  if a ~= b then
    local ox, oy = sx, sy
    if a then ox, oy = tx, ty end
    if not (CG.SurfacesAt and CG.SurfacesAt(cc, ox, oy)[1]) then return nil end
  end
  local md = opts.maxDrop or (ns.Nav and ns.Nav.SafeDrop and ns.Nav.SafeDrop()) or nil
  local zs = not opts.z and CG.PlayerStart(cont, sx, sy) and CG.PlayerFloorZs and CG.PlayerFloorZs(cont, sx, sy) or nil
  local r = CG.Walk(cc, sx, sy, opts.z, tx, ty, opts.tz, md, zs)
  if r == "pending" then return "pending" end
  if not r then return nil end
  WG.stats.city = (WG.stats.city or 0) + 1
  return r
end

-- No way on the grid (WG.Leg): the line, marked `noWay` and `gridGap` (Nav: "No way found yet"), never the Router's own
-- route instead. Each kept once in WG.gaps (newest last, GAPS_MAX) and said to a listening hook (the Dev addon's TODO
-- list: Nav.gridGapHook), so the data gets fixed there.
WG.GAPS_MAX = 200
WG.gaps = {}
local gapSeen = {}
function WG.NoWay(cont, sx, sy, tx, ty, why)
  WG.stats.noWay = (WG.stats.noWay or 0) + 1
  local k = string.format("%d:%.0f:%.0f:%.0f:%.0f", cont, sx, sy, tx, ty)
  if not gapSeen[k] then
    gapSeen[k] = true
    local g = { cont = cont, x1 = sx, y1 = sy, x2 = tx, y2 = ty, why = why }
    WG.gaps[#WG.gaps + 1] = g
    if #WG.gaps > WG.GAPS_MAX then
      local old = table.remove(WG.gaps, 1)
      gapSeen[string.format("%d:%.0f:%.0f:%.0f:%.0f", old.cont, old.x1, old.y1, old.x2, old.y2)] = nil
    end
    local hook = ns.Nav and ns.Nav.gridGapHook
    if hook then pcall(hook, g) end
  end
  local Rt = R()
  return { pts = { sx, sy, tx, ty }, kinds = { Rt.KIND_OFFROAD or 1 }, length = Dist(sx, sy, tx, ty), road = 0,
    noWay = true, gridGap = true, worldGrid = true }
end

-- The open world's building (Data/Indoors.lua: an inn, a keep, a tower, with its inside's roads and doors) that (x, y)
-- is in, or nil: within its radius, and at a height `z` near one of its floors (BUILDING_FLOOR_Z); with no height,
-- only when `indoors` (the game's IsIndoors at the player's spot): a spot by a building isn't in it.
WG.BUILDING_FLOOR_Z = 6
function WG.BuildingAt(cont, x, y, z, indoors)
  if z == nil and not indoors then return nil end
  for _, b in ipairs(ns.Indoors and ns.Indoors[cont] or {}) do
    if b.x and b.r and (x - b.x) ^ 2 + (y - b.y) ^ 2 <= b.r * b.r then
      local onFloor = z == nil
      for _, f in ipairs(b.floors or {}) do
        if z and abs(z - f) <= WG.BUILDING_FLOOR_Z then onFloor = true end
      end
      if onFloor then return b end
    end
  end
  return nil
end
-- A leg with one end inside one of the open world's buildings and the other outside it: in through its door. The
-- grid's bake has its walls only where the building's model has them for a walker (the Crossroads' inn: none, the
-- straight line through the wall to the stop in its middle; Kooki3z 2026-11-24, item 70, "I thought routes to
-- locations inside of buildings are routed to go through the door now?"). The Router's own way, along the building's
-- inside roads (Data/Indoors.lua, its doors the only ways in), only to find the door: the grid walks up to it, the
-- inside roads from it. Returns the route, "pending", or nil (not such a leg, or no door found: the grid's own walk).
function WG.BuildingLeg(c, cont, sx, sy, tx, ty, opts)
  -- (into a building only: a walk out of one starts where the player stands, on its stairs or floor, the grid's own way
  -- out (the Router's started on the inside road, yards off: Darnassus's spiral down the tree))
  local bt = WG.BuildingAt(cont, tx, ty, opts.tz)
  local bs = WG.BuildingAt(cont, sx, sy, opts.z, opts.indoors)
  if not bt or bt == bs then return nil end
  local b, into = bt or bs, bt ~= nil
  if bt and bs then b, into = bt, true end -- (from one building to another: into the stop's)
  local own = R().RouteOwn(cont, sx, sy, tx, ty, opts)
  if type(own) == "table" and own.pending then return "pending" end
  if not (type(own) == "table" and own.pts and #own.pts >= 4) or own.noWay or own.unconnected then return nil end
  local pts, n = own.pts, #own.pts / 2
  local function In(i) return (pts[2 * i - 1] - b.x) ^ 2 + (pts[2 * i] - b.y) ^ 2 <= b.r * b.r end
  -- (the door: the last point outside before the inside, going in; the first one outside after it, coming out)
  local door
  if into then
    for i = 2, n do
      if In(i) and not In(i - 1) then door = i - 1 break end
    end
  else
    for i = n - 1, 1, -1 do
      if In(i) and not In(i + 1) then door = i + 1 break end
    end
  end
  if not door then return nil end
  local dx, dy = pts[2 * door - 1], pts[2 * door]
  -- (the inside's points with no height of their own: the building's floor nearest the end inside it)
  local endZ = into and opts.tz or opts.z
  local floorZ = false
  for _, f in ipairs(b.floors or {}) do
    if floorZ == false or (endZ and abs(f - endZ) < abs(floorZ - endZ)) then floorZ = f end
  end
  local out = { pts = {}, kinds = {}, fz = {}, length = 0, road = 0, worldGrid = true, onLink = {}, bends = {} }
  local function AddOwn(i0, i1)
    for i = i0, i1 do
      if i > i0 or #out.pts == 0 then
        out.pts[#out.pts + 1], out.pts[#out.pts + 2] = pts[2 * i - 1], pts[2 * i]
        out.fz[#out.pts / 2] = (into and i == n and opts.tz) or (not into and i == 1 and opts.z)
          or own.zs and own.zs[i] or own.fz and own.fz[i] or floorZ
      end
      if i < i1 then
        out.kinds[#out.kinds + 1] = own.kinds and own.kinds[i] or (R().KIND_ROAD or 0)
        out.length = out.length + Dist(pts[2 * i - 1], pts[2 * i], pts[2 * i + 1], pts[2 * i + 2])
      end
    end
  end
  local function AddGrid(r)
    if type(r) ~= "table" or not r.pts then return false end
    for k = 1, #r.pts / 2 do
      if k > 1 or #out.pts == 0 then
        out.pts[#out.pts + 1], out.pts[#out.pts + 2] = r.pts[2 * k - 1], r.pts[2 * k]
        out.fz[#out.pts / 2] = r.fz and r.fz[k] or false
      end
    end
    for k = 1, #(r.kinds or {}) do out.kinds[#out.kinds + 1] = r.kinds[k] end
    out.length, out.road = out.length + (r.length or 0), out.road + (r.road or 0)
    return true
  end
  local walk
  if into then
    walk = WG.Walk(c, sx, sy, opts.z, dx, dy, nil, opts)
    if walk == "pending" or walk == nil then return "pending" end
    if not walk then return nil end
    AddGrid(walk)
    AddOwn(door, n)
  else
    walk = WG.Walk(c, dx, dy, nil, tx, ty, opts.tz, opts)
    if walk == "pending" or walk == nil then return "pending" end
    if not walk then return nil end
    AddOwn(1, door)
    AddGrid(walk)
  end
  WG.stats.buildingDoors = (WG.stats.buildingDoors or 0) + 1
  out.building = b[1]
  return out
end

-- The cave or mine (Data/Caves.lua: its key, ns.Caves[cont][i][2]) whose grid is at (x, y) on continent `cont`, or nil.
local caveGrids = {}
function WG.CaveAt(cont, x, y)
  local P = ns.Passability
  if not (P and P.OverlayRaw and x and y) then return nil end
  local v, grid = P.OverlayRaw(cont, x, y)
  if v == nil or v == 1 or not (grid and grid.cave) then return nil end
  local map = caveGrids[cont]
  if not map then
    map = {}
    for _, cv in ipairs(ns.Caves and ns.Caves[cont] or {}) do
      local g = ns.Terrain and ns.Terrain[cv[2]]
      if g then map[g] = cv[2] end
    end
    caveGrids[cont] = map
  end
  return map[grid]
end
local function GroundZ(cont, x, y) -- (the ground over (x, y): the hill over a cave; WG.GroundZ)
  local N = ns.Nav
  local g = N and N.GroundAt and N.GroundAt(cont, x, y)
  if not g and ns.Ground and ns.Ground.Sample then
    local ok, h = pcall(ns.Ground.Sample, cont, x, y)
    g = ok and type(h) == "number" and h or nil
  end
  return g
end
WG.GroundZ = GroundZ
-- Whether (x, y) at height z is inside a cave: over its grid, `under` yd or more under the ground (the hill or the
-- mountain over it). The cave's key, or nil.
WG.CAVE_UNDER_YD = 8 -- (a stop this far under the ground over a cave is in it: GPSFrame's CAVE_UNDER_YD)
WG.CAVE_DOOR_Z = 3 -- (a route's point this near the ground, or over it, is outside: the cave's mouth is the last such)
function WG.InCave(cont, x, y, z, under)
  if not z then return nil end
  local cave = WG.CaveAt(cont, x, y)
  if not cave then return nil end
  local g = GroundZ(cont, x, y)
  if g and z <= g - (under or WG.CAVE_UNDER_YD) then return cave end
  return nil
end
-- A leg to a stop inside a cave or mine (item 84's floor shown: the Wailing Caverns' inside, Kooki3z 2026-11-25; any
-- cave in Data/Caves.lua). The grid's tunnels often don't join the mouth to the inner floors (section 11's known gap:
-- its falls into the cave refused, WG.IntoGround), and searching for a floor the grid can't reach took every node of
-- the leg's budget, then the ride check's legs to it from the flight masters the same (Kooki3z's route hung on its
-- faded line). So the cave's own roads inside, from its mouth: the Router's own route only to find the mouth (its last
-- point outside before the cave's inside, R.RouteOwn along Caves.lua's roads), the grid's walk up to it, the cave's road
-- from it to the stop. Returns the route, "pending", or nil (not such a leg, the start in the same cave, or no road
-- into it: the grid's own walk).
WG.CAVE_LINE_YD = 40 -- (a straight line to the stop from outside this long at most is a stop's step off a mouth's road)
WG.CAVE_WAY_YD = 12 -- (a spot this near one of a cave's ways in, Data/Caves.lua's, is at its mouth)
WG.CAVE_WAY_BACK_YD = 120 -- (the route's way in looked for this far back along it from the grid's edge)
local caveWays = {}
function WG.AtCaveWayIn(cont, key, x, y)
  local map = caveWays[cont]
  if not map then
    map = {}
    for _, cv in ipairs(ns.Caves and ns.Caves[cont] or {}) do map[cv[2]] = cv[5] end
    caveWays[cont] = map
  end
  local ways = map[key] or {}
  for k = 1, #ways - 1, 2 do
    if Dist(x, y, ways[k], ways[k + 1]) <= WG.CAVE_WAY_YD then return true end
  end
  return false
end
function WG.CaveLeg(c, cont, sx, sy, tx, ty, opts)
  local cave = WG.InCave(cont, tx, ty, opts.tz)
  if not cave then return nil end
  if WG.CaveAt(cont, sx, sy) == cave and (opts.z == nil or WG.InCave(cont, sx, sy, opts.z, WG.CAVE_DOOR_Z)) then
    return nil -- (in it already: the grid's walk on its floors)
  end
  local own = R().RouteOwn(cont, sx, sy, tx, ty, opts)
  if type(own) == "table" and own.pending then return "pending" end
  if not (type(own) == "table" and own.pts and #own.pts >= 4) or own.noWay or own.unconnected then return nil end
  local pts, n = own.pts, #own.pts / 2
  local hs = own.zs or own.fz
  local function Inside(i)
    local z = (i == n and opts.tz) or (hs and hs[i])
    if not z then return WG.CaveAt(cont, pts[2 * i - 1], pts[2 * i]) == cave end
    return WG.InCave(cont, pts[2 * i - 1], pts[2 * i], z, WG.CAVE_DOOR_Z) == cave
  end
  -- (another cave's or mine's grid there: Dreadmaul Rock's caves, joined under the hill)
  local function InOther(i)
    local z = hs and hs[i]
    local x, y = pts[2 * i - 1], pts[2 * i]
    local other
    if z then other = WG.InCave(cont, x, y, z, WG.CAVE_DOOR_Z) else other = WG.CaveAt(cont, x, y) end
    return other ~= nil and other ~= cave
  end
  -- (the mouth: the last point outside before the stretch inside that ends at the stop; a stretch through another
  -- cave's grid between two of this one's is inside (the cave sweep's Dreadmaul Rock: in by its own mouth, through
  -- the next cave's tunnel and back, the "mouth" was the tunnel's middle, 122 yd off its way in))
  local door
  local i = n - 1
  while i >= 1 do
    if Inside(i) then
      i = i - 1
    else
      local j = i
      while j >= 1 and not Inside(j) and InOther(j) do j = j - 1 end
      if j >= 1 and j < i and Inside(j) then
        i = j - 1
      else
        door = i
        break
      end
    end
  end
  if not door or door == 1 then return nil end -- (no way in by the roads: in from the start, or none)
  -- (none of the cave's own roads on the way in, only a straight line to the stop from a spot neither on the cave's
  -- grid nor at one of its ways in, longer than a stop's step: the Router's own found no road into it and went through
  -- the rock (the sweep's Mo'grosh Stronghold, 667 yd through the mountain to a stop on the ground over it; the
  -- Dawning Wood Catacombs, 143): not such a leg, the grid's own walk to the stop)
  local ex, ey = pts[2 * door - 1], pts[2 * door]
  if door == n - 1 and Dist(ex, ey, tx, ty) > WG.CAVE_LINE_YD and WG.CaveAt(cont, ex, ey) ~= cave
      and not WG.AtCaveWayIn(cont, cave, ex, ey) then
    return nil
  end
  -- (the way in the route came by, a few yards back off the cave's grid: the mouth, not a spot past it that only the
  -- grid's edge leaves outside. The sweep's Dun Algaz tunnel: its grid starts 75 yd in, and the walk was sent to that
  -- spot at the mountain's height over it, a ledge in the rock: No way found yet)
  if not (hs and hs[door]) and not WG.AtCaveWayIn(cont, cave, ex, ey) then
    local back = 0
    for j = door - 1, 2, -1 do
      back = back + Dist(pts[2 * j - 1], pts[2 * j], pts[2 * j + 1], pts[2 * j + 2])
      if back > WG.CAVE_WAY_BACK_YD then break end
      if WG.AtCaveWayIn(cont, cave, pts[2 * j - 1], pts[2 * j]) then
        door = j
        break
      end
    end
  end
  local dx, dy = pts[2 * door - 1], pts[2 * door]
  local dz = hs and hs[door] or GroundZ(cont, dx, dy)
  local walk = WG.Walk(c, sx, sy, opts.z, dx, dy, dz, opts)
  if walk == "pending" or walk == nil then return "pending" end
  if not walk then
    -- (no way to the mouth: no way in, never the stop searched for on the grid after it (its floor further still; the
    -- sweep's Loch Modan cave, 70k nodes to the mouth, then 80k more). From round here, the stop unreached: no plan by
    -- the flight masters searched for it either (WG.StopUnreached))
    if Dist(sx, sy, tx, ty) <= WG.UNREACHED_LEG_YD and ToAStop(tx, ty) then WG.Unreached(cont, tx, ty, opts.tz) end
    return WG.NoWay(cont, sx, sy, tx, ty, "no way to the mouth of " .. tostring(cave))
  end
  local out = { pts = {}, kinds = {}, fz = {}, length = 0, road = 0, worldGrid = true, onLink = {}, bends = {} }
  for k = 1, #walk.pts / 2 do
    out.pts[#out.pts + 1], out.pts[#out.pts + 2] = walk.pts[2 * k - 1], walk.pts[2 * k]
    out.fz[#out.pts / 2] = walk.fz and walk.fz[k] or false
  end
  for k = 1, #(walk.kinds or {}) do out.kinds[#out.kinds + 1] = walk.kinds[k] end
  out.length, out.road = walk.length or 0, walk.road or 0
  -- (the grid's walk ends at the mouth: from there the cave's road; a step between them when the grid's end isn't it)
  for i = door, n do
    local x, y = pts[2 * i - 1], pts[2 * i]
    local lx, ly = out.pts[#out.pts - 1], out.pts[#out.pts]
    local first = i == door
    if not (first and Dist(lx, ly, x, y) < 0.5) then
      out.kinds[#out.kinds + 1] = first and (R().KIND_OFFROAD or 1) or own.kinds and own.kinds[i - 1] or (R().KIND_ROAD or 0)
      out.length = out.length + Dist(lx, ly, x, y)
      out.pts[#out.pts + 1], out.pts[#out.pts + 2] = x, y
      out.fz[#out.pts / 2] = (i == n and opts.tz) or hs and hs[i] or false
    end
  end
  WG.stats.caveMouths = (WG.stats.caveMouths or 0) + 1
  out.cave, out.caveMouth = cave, { dx, dy, dz }
  return out
end

-- Other spots on capital `name`'s edge near its crossing (x, y, z) (CG.Crossing's, where the Router's own route crosses
-- in): { { x, y, z }, ... }, nearest first, at most CROSS_RETRY, CROSS_RETRY_YD round it, each on a floor of the city's
-- grid within CROSS_RETRY_Z of z (any, with none), with the land outside within CROSS_EDGE_YD. Item 141 (1.4.2):
-- Thunder Bluff's north lift's foot stands on a rise; the Router's own came at it straight from the east, up the slope,
-- and the grid had no way there though the road up the rise is 30 yd round.
WG.CROSS_RETRY = 12
WG.CROSS_RETRY_YD = 80
WG.CROSS_RETRY_Z = 20
WG.CROSS_EDGE_YD = 10
WG.CROSS_WALK_NODES = 20000 -- (the walk outside to one: within this many ...
WG.CROSS_RETRY_NODES = 100000 -- ... and all those tried for one leg within this many)
function WG.OtherCrossings(cont, name, cc, x, y, z)
  local CG = ns.CityGrid
  local out = {}
  local E = WG.CROSS_EDGE_YD
  for r = 10, WG.CROSS_RETRY_YD, 10 do
    for k = 0, 15 do
      local an = k * math.pi / 8
      local px, py = x + r * math.cos(an), y + r * math.sin(an)
      if CG.CityFor(cont, px, py) == name then
        local edge = false
        for j = 0, 7 do
          local bn = j * math.pi / 4
          if CG.CityFor(cont, px + E * math.cos(bn), py + E * math.sin(bn)) ~= name then edge = true break end
        end
        local f = edge and CG.SurfacesAt(cc, px, py, z)[1]
        if f and (not z or math.abs(f.z - z) <= WG.CROSS_RETRY_Z) then
          local apart = true
          for _, q in ipairs(out) do
            if (q[1] - px) ^ 2 + (q[2] - py) ^ 2 < 400 then apart = false break end
          end
          if apart then
            out[#out + 1] = { px, py, f.z }
            if #out >= WG.CROSS_RETRY then return out end
          end
        end
      end
    end
  end
  return out
end

-- Whether the grid gets out from (qx, qy, qz) toward (ox, oy, oz): a small search (CROSS_ESCAPE_NODES) from there,
-- its surfaces, else (a speck: the city's cells are the city grid's) the floors round it as WG.Walk starts, that finds
-- it or runs out of budget, not out of ground. No drops: the way out is walked in the other way too.
-- (WG.OtherCrossings' spots on Thunder Bluff's north lift's rise flooded the land for seconds each before failing.)
WG.CROSS_ESCAPE_NODES = 4000
function WG.CrossEscapes(c, qx, qy, qz, ox, oy, oz, opts)
  local goals = {}
  for _, e in ipairs(Ends(c, ox, oy, oz)) do goals[e.id] = e.cost end
  if not next(goals) then return true end
  local x = WG.Costs(c, qx, qy, ox, oy, opts) or {}
  x.nodeCap, x.maxDrop, x.slopeDrop = WG.CROSS_ESCAPE_NODES, 0, 0
  local starts, tried = Ends(c, qx, qy, qz), {}
  for _ = 0, WG.NEAR_CELLS do
    if starts[1] then
      local n1 = WG.stats.nodes
      if WG.Search(c, starts, goals, ox, oy, nil, x) or x.limitHit then return true end
      if WG.stats.nodes - n1 >= WG.ISLAND_NODES then return false end
      for _, st in ipairs(starts) do tried[#tried + 1] = st end
    end
    starts = WG.NearStarts(c, qx, qy, qz, tried)
    if not starts[1] then return false end
  end
  return false
end

function WG.Leg(cont, sx, sy, tx, ty, opts)
  if not WG.On() then return nil end
  local c = WG.Cont(cont)
  if not c then return nil end
  local CG = ns.CityGrid
  local a = CG and CG.CityFor and CG.CityFor(cont, sx, sy)
  local b = CG and CG.CityFor and CG.CityFor(cont, tx, ty)
  if a and b then return nil end -- (one city: its grid, CG.Leg; two: the Router's own between them)
  if WG.NotMeshed(cont, sx, sy) or WG.NotMeshed(cont, tx, ty) then return nil end
  if not (a or b) then
    -- (1.4.2, item 119: a building's own grid, through its doors, in the test's towns; BuildingGrid.lua)
    local BG = ns.BuildingGrid
    local bg = BG and BG.Leg and BG.Leg(c, cont, sx, sy, tx, ty, opts)
    if bg ~= nil then return bg end
    -- (a stop inside one of the open world's buildings, or a start, the other end outside it: through its door. Item 70)
    local door = WG.BuildingLeg(c, cont, sx, sy, tx, ty, opts)
    if door ~= nil then return door end
    -- (a stop inside a cave or mine: the grid to its mouth, its own roads inside. Item 84c)
    local mouth = WG.CaveLeg(c, cont, sx, sy, tx, ty, opts)
    if mouth ~= nil then return mouth end
    -- (never the Router's own route instead, Kooki3z 2026-11-23: "we have to get rid of the fallback option, its
    -- fighting routing too much". Being worked out (here, or in a plan's job: queued): "pending", the line meanwhile
    -- (Router.GridWaiting); none: no way, said so and logged as a gap in the grid's data (WG.NoWay))
    local r = WG.Walk(c, sx, sy, opts.z, tx, ty, opts.tz, opts)
    if r == "pending" or r == nil then return "pending" end
    if not r then
      local cw = WG.CityWalk(cont, sx, sy, tx, ty, opts)
      if cw then return cw end
      return WG.NoWay(cont, sx, sy, tx, ty, "no way on the grid")
    end
    if WG.ThroughNotMeshed(cont, r) then return nil end -- (a capital's halls the grid has no mesh for: the city's)
    WG.stats.grid = WG.stats.grid + 1
    return r
  end
  -- (one end in a capital: the Router's own route finds the way in; the grid walks outside up to it, the city's grid
  -- inside from it)
  local name = a or b
  local cc = CG.City(name)
  if not cc then return nil end
  -- (the Router's own way only to find where it crosses into the capital: never shown or followed)
  local own = R().RouteOwn(cont, sx, sy, tx, ty, opts)
  if type(own) == "table" and own.pending then return "pending" end
  if not (own and own.pts and #own.pts >= 4) or own.noWay or own.unconnected then
    return WG.NoWay(cont, sx, sy, tx, ty, "no way into " .. name)
  end
  local x, y, z, i = CG.Crossing(own, cont, name, cc, a ~= nil)
  if not x then return WG.NoWay(cont, sx, sy, tx, ty, "no crossing into " .. name) end
  -- (the city's grid from or to the crossing, the world grid's on from or up to it: inside, outside, or "pending")
  local function Splice(px, py, pz, retry)
    local inside, outside
    local wo = opts
    if retry then -- (another crossing: its walk outside within CROSS_WALK_NODES; one that isn't there flooded the land)
      wo = {}
      for kk, v in pairs(opts) do wo[kk] = v end
      wo.crossCap = WG.CROSS_WALK_NODES
    end
    if a then
      local sz = opts.z
      local zs
      if CG.PlayerStart(cont, sx, sy) then
        sz = CG.PlayerFloorZ(cont, sx, sy) or sz
        zs = not sz and CG.PlayerFloorZs and CG.PlayerFloorZs(cont, sx, sy) or nil
      end
      inside = CG.Walk(cc, sx, sy, sz, px, py, pz, nil, zs)
      local o2 = wo
      if opts.swimming then -- (the start's water is the city's: the grid's walk starts out of it)
        o2 = {}
        for kk, v in pairs(wo) do o2[kk] = v end
        o2.swimming = nil
      end
      outside = inside ~= "pending" and inside
        and WG.Walk(c, px, py, (inside.fz or {})[#(inside.fz or {})] or pz, tx, ty, opts.tz, o2)
    else
      inside = CG.Walk(cc, px, py, pz, tx, ty, opts.tz)
      outside = inside ~= "pending" and inside and WG.Walk(c, sx, sy, opts.z, px, py, (inside.fz or {})[1] or pz, wo)
    end
    if inside == "pending" or outside == "pending" then return "pending" end
    -- (the two grids' walks meeting on different floors at the crossing: the world grid's arrived on another floor than
    -- the city's starts on (its own floor there unreached: the mountain's top over Ironforge, 210 yd over the city's
    -- halls), so the splice is a fall through the rock: as with no walk outside. The underground sweep, 2026-11-23)
    if inside and outside and not WG.SpliceMeets(inside, outside, a ~= nil) then
      WG.stats.splitFloors = (WG.stats.splitFloors or 0) + 1
      outside = nil
    end
    return inside, outside
  end
  local inside, outside = Splice(x, y, z)
  if inside == "pending" then return "pending" end
  if not inside then return WG.NoWay(cont, sx, sy, tx, ty, "no way inside " .. name) end
  if not outside then
    -- (no way outside to where the Router's own crosses in: its straight leg off the roads came at the city up a slope
    -- the grid can't climb (item 141, Thunder Bluff's north lift's foot from the east); the nearest other spots on the
    -- city's edge then, WG.OtherCrossings, the first that both grids walk)
    -- (each tried only when the grid gets out from it at all, WG.CrossEscapes, and its walk outside within
    -- CROSS_WALK_NODES, all of them within CROSS_RETRY_NODES)
    local ox, oy, oz = a and tx or sx, a and ty or sy, a and opts.tz or opts.z
    local n0 = WG.stats.nodes
    for _, q in ipairs(WG.OtherCrossings(cont, name, cc, x, y, z)) do
      if WG.stats.nodes - n0 > WG.CROSS_RETRY_NODES then break end
      local i2, o2
      if WG.CrossEscapes(c, q[1], q[2], q[3], ox, oy, oz, opts) then i2, o2 = Splice(q[1], q[2], q[3], true) end
      if i2 == "pending" then return "pending" end
      if i2 and o2 then
        inside, outside = i2, o2
        WG.stats.recrossed = (WG.stats.recrossed or 0) + 1
        break
      end
    end
  end
  if not outside then
    -- (the grid has no way outside: the city grid's whole leg when both ends are on its floors (a spot by Ironforge's
    -- Forge just outside the capital's outline, WG.CityWalk); else no way, never the Router's own up to the city, nor
    -- CG.Leg's splice of it: the coordinator 2026-11-24, no fallback in the capitals either)
    local cw = WG.CityWalk(cont, sx, sy, tx, ty, opts)
    if cw then return cw end
    return WG.NoWay(cont, sx, sy, tx, ty, "no way outside " .. name)
  end
  local r = a and CG.Concat(inside, outside, false) or CG.Concat(outside, inside, false)
  r.worldGrid = true
  WG.stats.spliced = WG.stats.spliced + 1
  return r
end

---------------------------------------------------------------------------------------------------- the switch
-- (the routes and decoded tiles dropped; the regions loaded stay: the game can't load a folder twice)
function WG.Reset()
  if ns.WorldHPA then ns.WorldHPA.gaveUp = {} end
  WG.routes, WG.order = {}, {}
  WG.failed, WG.failOrder = {}, {}
  WG.unreached = {}
  WG.exhausted = {}
  for _, c in pairs(WG.conts) do
    c.tiles, c.bytes, c.none, c.far, c.farOld, c.farN = {}, 0, {}, nil, nil, 0
  end
  WG.stats.tileBytes = 0
  if ns.BuildingGrid and ns.BuildingGrid.Reset then ns.BuildingGrid.Reset() end
end

function WG.Set(on)
  ns.settings.gps.worldGrid = on and true or false
  WG.Reset()
  local s = WG.stats
  WG.stats = { grid = 0, spliced = 0, own = 0, open = 0, pending = 0, searches = 0, nodes = 0, ms = 0, tiles = 0,
    regions = s.regions or 0, rawBytes = s.rawBytes or 0, tileBytes = 0 }
  local CG = ns.CityGrid
  if CG then CG.routes, CG.order, CG.track = {}, {}, nil end -- (its option left as the player set it)
  local N = ns.Nav
  if N and N.Invalidate then N.Invalidate(true, true) end
end

function WG.Slash(b) -- (debug: its stats; no switch for players since item 74)
  do
    local s = WG.stats
    ns.Print(string.format("world grid %s: legs on the grid %d, with a city's %d, the Router's own %d, searched %d (%d nodes, %.0f ms), tiles read %d (%.1f MB kept), regions loaded %d (%.1f MB), waited %d",
      WG.On() and "on" or "off", s.grid, s.spliced, s.own, s.searches, s.nodes, s.ms, s.tiles, (s.tileBytes or 0) / 1048576,
      s.regions or 0, (s.rawBytes or 0) / 1048576, s.pending))
  end
end
