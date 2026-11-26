-- City routing on layered walk grids (1.4.0, being tested: Options > Routing "City routing: new (test)", off by
-- default, and /agps citygrid on|off; docs/city-rework-1.4.0.md). Asked 2026-11-21: inside the capitals the routes went
-- along roads traced from the floors' faces, which zig-zag, and the player's floor was a guess.
--
-- The grids (Data/CityGrid.lua, `agps city-grid --write`, citygrid.py): baked from our own navigation meshes of the
-- cities' collision, a square grid each (3 yd cells in Orgrimmar, Stormwind, Ironforge and Darnassus, 2 in Undercity and
-- Thunder Bluff), every cell with each
-- walkable surface there and its height (floors over floors: Undercity's rings, the Drag over the Cleft of Shadow), each
-- surface linked to the surface it walks onto in each of its 8 neighbor cells, and road links (stairs, ledges and decks
-- the mesh lacks, from the city's own roads; a drop one way; Thunder Bluff's lifts, their ride costing the wait and
-- the ride as the Router's own lift roads do).
--
-- Routing: a leg with both ends in one city's grid (its own cells: Router.CapitalAt; Undercity's level) is searched on
-- it (A*, in the background, a slice at a time under the frame budget) and drawn string-pulled (straight wherever the
-- grid walks the straight line on one floor), each point's height in the route (`zs` on a level, `fz` on a continent:
-- the directions' stairs, the map's floors). A leg with one end in the city: the Router's own route outside, cut where it
-- comes into the city's grid, the grid's from there. Anything the grid can't walk, and every leg elsewhere: the Router's
-- own, as before.
--
-- The player's floor (CG.TrackFloor, the game gives no height: UnitPosition's z is 0): the grid's surfaces under the
-- player, kept to those the grid walks to from the last ones (a floor stays a candidate while there's a way from it), and
-- the height band (CG.Band): the game checks ranges in 3D, so an NPC the player has named (target, mouseover, the soft
-- interact target, the NPC whose window is open) standing at a known spawn (Data/Npcs.lua) bounds the player's height:
-- in range R at d yards across, |z - zNPC| <= sqrt(R^2 - d^2); out of it, more. Read-only range checks
-- (CheckInteractDistance, C_Spell.IsSpellInRange, C_Item.IsItemInRange); nothing is targeted, cast or used.
local _, ns = ...
local CG = {}
ns.CityGrid = CG

local floor, sqrt, abs, huge, max, min = math.floor, math.sqrt, math.abs, math.huge, math.max, math.min
local byte = string.byte

CG.HURT_DROP_COST = 12 -- yards of walking each yard of a drop past the free one costs (the fall's hurt; CG.Search)
-- (Expert jumper with a fall spell ready (FallSpells.MaxDrop): no hurt, one cast's flat cost a drop past the free one;
-- #948)
CG.CAST_DROP_COST = 30
CG.CITY_STEP_DOWN = 4 -- yards: a drop link a city walk takes without Expert jumper (CG.Search)
CG.START_ROAD_YD = 8 -- yards: a start with no height takes the nearest road's this near (CG.Leg)
CG.SUNKEN_Z, CG.SUNKEN_ROAD_YD = 20, 32 -- (... a road that far over the terrain: a sunken place under it, the roads this near looked at)
-- The capitals' sunken places, by name: { x0, y0, x1, y1 } boxes (world yards). Only in them a stop with no height takes
-- the road nearest the terrain's (CG.Leg's RoadZ): in general the heights can't tell a sunken place under a road from a
-- tower's foot under its top (the capitals' sweep, 2026-11-24: the rule everywhere fixed 21 stops and put 11 on the
-- wrong floor, Tyrande's temple balcony and Doras's tower among them). The Cleft of Shadow, Orgrimmar: from its NPCs,
-- Kor'jus to Zevrost, with a margin.
CG.SUNKEN = {
  Orgrimmar = { { 1740, -4400, 1880, -4320 } }, -- (the Cleft of Shadow)
}
-- The places a drop never lands in, by city: { x0, y0, x1, y1 } boxes. A drop past a step down (CITY_STEP_DOWN) ending
-- in one isn't taken, Expert jumper or not. The Cleft of Shadow's ways in are its tunnel from the Valley of Strength
-- and the Drag's (Kooki3z 2026-11-24, item 55b/c): with Expert jumper on, the grid's drops off the rock by the Valley
-- (28 yd down to 6, then to the Cleft's floor, -8) were "Stairs down in 103 yd" through the wall.
CG.NO_DROP_IN = {
  -- (the Cleft of Shadow: CG.SUNKEN's box, and north to its ramp up to the Drag, whose foot a drop off the rock by the
  -- Valley of Strength reached next, 36 yd down to 7.6 at (1756, -4303))
  Orgrimmar = { { 1720, -4400, 1880, -4280 } },
}
function CG.NoDropAt(name, x, y)
  for _, b in ipairs(CG.NO_DROP_IN[name] or {}) do
    if x >= b[1] and x <= b[3] and y >= b[2] and y <= b[4] then return true end
  end
  return false
end
local function InSunken(name, x, y)
  for _, b in ipairs(CG.SUNKEN[name] or {}) do
    if x >= b[1] and x <= b[3] and y >= b[2] and y <= b[4] then return true end
  end
  return false
end
CG.FLOOR_Z = 4 -- yards: a spot's height takes the surfaces this near it (else the nearest, dearer)
CG.Z_COST = 6 -- (a yard between a spot's height and the surface taken, past FLOOR_Z, costs this many)
CG.NEAR_CELLS = 2 -- cells round a spot looked at when its own has no surface (a spot against a wall)
CG.SLICE = 150 -- nodes settled between pauses in the background
CG.MAX_NODES = 300000 -- (a search giving up: no way)
CG.CLIMB_COST = 0.5 -- each yard up or down costs this many more (the flatter way, when about as short)
CG.CACHE = 24 -- routes kept (a trip's legs, the ride check's)
CG.REUSE_YD = 25 -- a route to the same stop from this near: joined straight onto it, no search
CG.LINE_TOL = 0.75 -- a straight line keeps within this many cells of each crossed surface's own point ...
CG.LINE_TOL_EDGE = 0.4 -- ... this many where the point isn't the cell's middle (the floor covers only that side of the
-- cell: a corridor's edge, a walkway's; at 0.75 a line along Ironforge's Tinker Town hall ran 15 yd past the floor's edge)
CG.LINE_RISE = 2.5 -- yards: a straight line's ground this far off the climb between its ends isn't one line (CG.Line)
CG.Z_BEND = 1.5 -- yards: a straight stretch's ground bending this far from a straight climb gets a point there
CG.SPLICE_STEP = 2 -- yards: the Router's own route walked this often to find where it comes into the city

CG.stats = { grid = 0, spliced = 0, own = 0, pending = 0, searches = 0, nodes = 0, ms = 0 }

-- (the data's characters, ALPHA in citygrid.py, and the 8 directions in its order)
local ALPHA = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
local DEC = {}
for i = 1, #ALPHA do DEC[byte(ALPHA, i)] = i - 1 end
CG.DEC = DEC
local DX = { 1, 0, -1, 0, 1, -1, -1, 1 }
local DY = { 0, 1, 0, -1, 1, 1, -1, -1 }
local SURF = 7

function CG.On()
  local s = ns.settings and ns.settings.gps
  -- (the world grid's option takes the capitals' grids with it: inside them only the city grid routes)
  return s ~= nil and (s.cityGrid == true or s.worldGrid == true)
end

local function R() return ns.Router end
local function Dist(x1, y1, x2, y2) return sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2) end

---------------------------------------------------------------------------------------------------- the data
CG.cities = {}
-- The city's grid, read once: its strings kept as they are (looked up character by character), the block starts and
-- the road links unpacked.
function CG.City(name)
  local c = CG.cities[name]
  local d = ns.CityGridData and ns.CityGridData[name]
  if c and c.d == d then return c end
  if not d then return nil end
  c = { name = name, d = d, cont = d.cont, level = d.level, lv = d.level or d.cont, cell = d.cell, x0 = d.x0, y0 = d.y0,
    w = d.w, h = d.h, zmin = d.zmin, zq = d.zq, offs = d.offs, block = d.block, n = d.n, cells = d.cells, s = d.s,
    base = {}, links = {}, out = {}, first = {}, firstN = 0 }
  for v in d.base:gmatch("%d+") do c.base[#c.base + 1] = tonumber(v) end
  for item in d.links:gmatch("[^;]+") do
    local nums = {}
    for v in item:gmatch("[^,]+") do nums[#nums + 1] = tonumber(v) end
    local L = { a = nums[1] - 1, b = nums[2] - 1, cost = nums[3], kind = nums[4], pts = {} }
    for k = 5, #nums - 2, 3 do L.pts[#L.pts + 1] = { nums[k], nums[k + 1], nums[k + 2] } end
    local last = L.pts[#L.pts]
    L.bci = last and CG.CellAt(c, last[1], last[2])
    -- (a drop's fall: its first point's height less its last's; taken only within the player's safe drop, CG.Search)
    if L.kind == 4 and last then L.drop = L.pts[1][3] - last[3] end
    c.links[#c.links + 1] = L
    local o = c.out[L.a]
    if not o then o = {} c.out[L.a] = o end
    o[#o + 1] = #c.links
  end
  -- (the walled cells: a wall at body height through them, a tent's canvas over Thunder Bluff's polys; navfeatures:
  -- each its index, then its wall's way through it, its ends' shares of the cell (0-63 each), or all 0: walled whole;
  -- then the surface it stands over (its index in the cell): the cell's other floors walk on under or over it)
  if d.walls then
    c.walls = {}
    for p = 1, #d.walls - 8, 9 do
      local v = 0
      for q = p, p + 3 do v = v * 64 + DEC[byte(d.walls, q)] end
      local a, b, e, f = DEC[byte(d.walls, p + 4)], DEC[byte(d.walls, p + 5)], DEC[byte(d.walls, p + 6)],
        DEC[byte(d.walls, p + 7)]
      if a + b + e + f == 0 then
        c.walls[v] = true
      else
        local i, j = floor(v / d.h), v % d.h
        local ox, oy, k = d.x0 + i * d.cell, d.y0 + j * d.cell, d.cell / 63
        local list = c.walls[v]
        if list ~= true then
          list = list or {}
          list[#list + 1] = { ox + a * k, oy + b * k, ox + e * k, oy + f * k, DEC[byte(d.walls, p + 8)] }
          c.walls[v] = list
        end
      end
    end
  end
  c.xmax, c.ymax = c.x0 + c.w * c.cell, c.y0 + c.h * c.cell
  c.nBaked = #c.links
  CG.cities[name] = c
  return c
end

-- The stairs and bridges found in the city's mesh (navfeatures.py; `feat`: "kind,half width,x,y,z,...;..." kind 1
-- stairs, bottom to top, 2 a bridge's deck), read at the first look and kept by FEAT_CELL buckets: what Turns says
-- ("Take the stairs up", "Cross the bridge") and the map's stairs icon along the grid's walks (CG.StairAt, CG.BridgeAt).
CG.FEAT_CELL = 16
CG.FEAT_Z = 4 -- yards: a route's point is on a feature this near its height (when the point has one)
function CG.Features(c)
  if c.feat then return c.feat end
  local f = { cells = {} }
  local C = CG.FEAT_CELL
  for item in (c.d.feat or ""):gmatch("[^;]+") do
    local nums = {}
    for v in item:gmatch("[^,]+") do nums[#nums + 1] = tonumber(v) end
    local F = { kind = nums[1], w = nums[2], pts = {} }
    for k = 3, #nums - 2, 3 do F.pts[#F.pts + 1] = { nums[k], nums[k + 1], nums[k + 2] } end
    local seen = {}
    for _, p in ipairs(F.pts) do
      for dx = -1, 1 do
        for dy = -1, 1 do
          local key = (floor(p[1] / C) + dx) * 65536 + floor(p[2] / C) + dy
          if not seen[key] then
            seen[key] = true
            local b = f.cells[key] or {}
            f.cells[key] = b
            b[#b + 1] = F
          end
        end
      end
    end
  end
  c.feat = f
  return f
end

-- The feature of `kind` (1 stairs, 2 a bridge) under (x, y) (and z, when known) in the city there: the feature, and how
-- far along its line (0 its first point, 1 its last); nil where none.
function CG.FeatureAt(cont, kind, x, y, z)
  if not CG.On() then return nil end
  local name = CG.GridCityAt and CG.GridCityAt(cont, x, y)
  local c = name and CG.City(name)
  if not (c and c.d.feat) then return nil end
  local f = CG.Features(c)
  local C = CG.FEAT_CELL
  for _, F in ipairs(f.cells[floor(x / C) * 65536 + floor(y / C)] or {}) do
    if F.kind == kind then
      local total, best, bestT = 0, nil, nil
      local lens = {}
      for k = 1, #F.pts - 1 do
        lens[k] = Dist(F.pts[k][1], F.pts[k][2], F.pts[k + 1][1], F.pts[k + 1][2])
        total = total + lens[k]
      end
      local along = 0
      for k = 1, math.max(1, #F.pts - 1) do
        local a, b = F.pts[k], F.pts[k + 1] or F.pts[k]
        local vx, vy = b[1] - a[1], b[2] - a[2]
        local L2 = vx * vx + vy * vy
        local t = L2 > 0 and math.max(0, math.min(1, ((x - a[1]) * vx + (y - a[2]) * vy) / L2)) or 0
        local d = Dist(x, y, a[1] + vx * t, a[2] + vy * t)
        local fz = a[3] + (b[3] - a[3]) * t
        if d <= F.w and (not z or math.abs(z - fz) <= CG.FEAT_Z) and (not best or d < best) then
          best, bestT = d, total > 0 and (along + (lens[k] or 0) * t) / total or 0
        end
        along = along + (lens[k] or 0)
      end
      if best then return F, bestT end
    end
  end
  return nil
end

-- Whether the walk (x1, y1)-(x2, y2) goes up (1) or down (-1) stairs the city's mesh has (its middle on them, the way by
-- the stairs' own, bottom to top), else nil. As Router.StairAt for its stairs roads.
function CG.StairAt(cont, x1, y1, x2, y2, z)
  local mx, my = (x1 + x2) / 2, (y1 + y2) / 2
  local F = CG.FeatureAt(cont, 1, mx, my, z)
  if not F then return nil end
  local _, t1 = CG.FeatureAt(cont, 1, x1, y1)
  local _, t2 = CG.FeatureAt(cont, 1, x2, y2)
  if t1 and t2 and math.abs(t2 - t1) > 0.001 then return t2 > t1 and 1 or -1 end
  -- (along its line: the way of the walk against its first and last points)
  local a, b = F.pts[1], F.pts[#F.pts]
  return ((x2 - x1) * (b[1] - a[1]) + (y2 - y1) * (b[2] - a[2]) >= 0) and 1 or -1
end

-- Whether (x, y) is on a bridge or walkway deck the city's mesh has.
function CG.BridgeAt(cont, x, y, z)
  return CG.FeatureAt(cont, 2, x, y, z) ~= nil
end

-- The cell at (x, y) (0-based, i * h + j), or nil off the grid.
function CG.CellAt(c, x, y)
  local i, j = floor((x - c.x0) / c.cell), floor((y - c.y0) / c.cell)
  if i < 0 or j < 0 or i >= c.w or j >= c.h then return nil end
  return i * c.h + j
end
local function Count(c, ci) return DEC[byte(c.cells, ci + 1)] end
-- The cell's first surface (0-based). (each cell's kept once looked up: a search looks at the same cells again and again)
local function First(c, ci)
  local f = c.first[ci]
  if f then return f end
  local b = floor(ci / c.block)
  f = c.base[b + 1]
  local cells = c.cells
  for k = b * c.block + 1, ci do f = f + DEC[byte(cells, k)] end
  if c.firstN > 200000 then c.first, c.firstN = {}, 0 end
  c.first[ci], c.firstN = f, c.firstN + 1
  return f
end
CG.First, CG.Count = First, Count
local function Z(c, s)
  local p = s * SURF
  local str = c.s
  return (DEC[byte(str, p + 1)] * 64 + DEC[byte(str, p + 2)]) * c.zq + c.zmin
end
CG.Z = Z
-- The surface's point (its spot in its cell).
local function Pt(c, s, ci)
  local v = DEC[byte(c.s, s * SURF + 3)]
  local i, j = floor(ci / c.h), ci % c.h
  local o = c.offs
  return c.x0 + (i + (floor(v / o) + 0.5) / o) * c.cell, c.y0 + (j + (v % o + 0.5) / o) * c.cell
end
CG.Pt = Pt
-- The surface it walks onto in direction d (1-8): 1-7 in that cell, 0 none.
local function Link(c, s, d)
  local v = DEC[byte(c.s, s * SURF + 3 + floor((d + 1) / 2))]
  if d % 2 == 1 then return floor(v / 8) end
  return v % 8
end
CG.Link = Link

-- The surfaces at (x, y) (its cell's; none there: the nearest cell's within NEAR_CELLS that has some), each
-- { s, ci, z, x, y } (the surface's point), nearest the spot's height first when `z` is given.
function CG.SurfacesAt(c, x, y, z)
  local ci = CG.CellAt(c, x, y)
  local out = {}
  local function Add(cell)
    for k = 0, Count(c, cell) - 1 do
      local s = First(c, cell) + k
      local px, py = Pt(c, s, cell)
      out[#out + 1] = { s = s, ci = cell, z = Z(c, s), x = px, y = py }
    end
  end
  if ci and Count(c, ci) > 0 then
    Add(ci)
  else
    local i, j = floor((x - c.x0) / c.cell), floor((y - c.y0) / c.cell)
    for r = 1, CG.NEAR_CELLS do
      local best, bd
      for di = -r, r do
        for dj = -r, r do
          if max(abs(di), abs(dj)) == r then
            local ii, jj = i + di, j + dj
            if ii >= 0 and jj >= 0 and ii < c.w and jj < c.h and Count(c, ii * c.h + jj) > 0 then
              local d2 = di * di + dj * dj
              if not bd or d2 < bd then best, bd = ii * c.h + jj, d2 end
            end
          end
        end
      end
      if best then Add(best) break end
    end
  end
  if z then table.sort(out, function(a, b) return abs(a.z - z) < abs(b.z - z) or (abs(a.z - z) == abs(b.z - z) and a.s < b.s) end) end
  return out
end

-- The city whose grid (x, y) on level `cont` is in: a capital's own cells (Router.CapitalAt), Undercity's level, and
-- in a city whose grid is all its own (`whole`: Darnassus, on Teldrassil's crown) any spot over a floor of its grid:
-- the capital's cells there are its ground's top floor reached from the gates, and the Cenarion Enclave's treetops
-- aren't among them (the Arch Druid's routes were the Router's own up to his tree and a straight line from its foot).
function CG.CityFor(cont, x, y)
  if not (cont and x and y and ns.CityGridData) then return nil end
  for name, d in pairs(ns.CityGridData) do
    if (d.level or d.cont) == cont and x >= d.x0 and y >= d.y0 and x < d.x0 + d.w * d.cell and y < d.y0 + d.h * d.cell then
      if d.level or (R().CapitalAt and R().CapitalAt(cont, x, y)) then return name end
      if d.whole then
        local c = CG.City(name)
        local ci = c and CG.CellAt(c, x, y)
        if ci and Count(c, ci) > 0 then return name end
      end
    end
  end
  return nil
end

-- Whether (x, y) on `cont` (a level's id for an underground city) is over a floor of a city's grid: CityFor's, or any
-- surface of a grid round it (a gate's ground, the margin round a capital's own cells). Turns: a walk there is the
-- grid's, its stairs only those found with risers.
function CG.InGrid(cont, x, y)
  return CG.GridCityAt(cont, x, y) ~= nil
end
-- The city whose grid has a floor at (x, y): CityFor's, else any grid with a surface in that cell.
function CG.GridCityAt(cont, x, y)
  local name = CG.CityFor(cont, x, y)
  if name then return name end
  if not (cont and x and y and ns.CityGridData) then return nil end
  for nm, d in pairs(ns.CityGridData) do
    if (d.level or d.cont) == cont and x >= d.x0 and y >= d.y0 and x < d.x0 + d.w * d.cell and y < d.y0 + d.h * d.cell then
      local c = CG.City(nm)
      local ci = c and CG.CellAt(c, x, y)
      if ci and Count(c, ci) > 0 then return nm end
    end
  end
  return nil
end

---------------------------------------------------------------------------------------------------- the search
-- (a binary heap of node ids by cost)
local function Push(hk, hv, k, v)
  local i = #hk + 1
  hk[i], hv[i] = k, v
  while i > 1 do
    local p = floor(i / 2)
    if hk[p] <= hk[i] then break end
    hk[p], hk[i], hv[p], hv[i] = hk[i], hk[p], hv[i], hv[p]
    i = p
  end
end
local function Pop(hk, hv)
  local n = #hk
  local k0, v0 = hk[1], hv[1]
  hk[1], hv[1] = hk[n], hv[n]
  hk[n], hv[n] = nil, nil
  n = n - 1
  local i = 1
  while true do
    local l, r, s = 2 * i, 2 * i + 1, i
    if l <= n and hk[l] < hk[s] then s = l end
    if r <= n and hk[r] < hk[s] then s = r end
    if s == i then break end
    hk[s], hk[i], hv[s], hv[i] = hk[i], hk[s], hv[i], hv[s]
    i = s
  end
  return k0, v0
end

-- The player's own roads and recorded walks (ns.db.tracks, Router.ExpandTracks; not yet in the data) as the grid's links
-- along their whole length (asked 2026-11-22: "use my fixed routing ... on city grid routing"; drawn and recorded roads
-- are truth): each TRACK_CHUNK yards of one between two points on the grid's floors (at the road's own heights where
-- it has them, else the floor nearest the one before) is a link costing TRACK_FACTOR a yard, cheaper than the grid's
-- own ground, so routes keep to them where they go the same way; down a drop steeper than a walk, one way. Kept in
-- c.links after the baked ones, worked out again when the tracks change (c.trackKey).
CG.TRACK_STEP, CG.TRACK_CHUNK, CG.TRACK_FACTOR, CG.TRACK_ON_Z, CG.TRACK_DROP_DZ = 2, 6, 0.7, 2.5, 1.5
local function TrackKey()
  local tracks = ns.db and ns.db.tracks
  local st = ns.settings and ns.settings.gps
  return (tracks and #tracks or 0) .. ":" .. tostring(st and st.roadTolerance or 0)
end
function CG.TrackLinks(c)
  local key = TrackKey()
  if c.trackKey == key then return end
  c.trackKey = key
  for i = #c.links, (c.nBaked or #c.links) + 1, -1 do c.links[i] = nil end
  c.tout, c.trackF = {}, nil
  local tracks = ns.db and ns.db.tracks
  if not (tracks and tracks[1]) then return end
  local Rt = R()
  local list = Rt.ExpandTracks and Rt.ExpandTracks(tracks) or tracks
  local shipped = ns.RoadTracksIn or {}
  for _, t in ipairs(list) do
    local pts = t.pts
    if (t.continent == c.lv) and pts and #pts >= 4 and t.op ~= "wall" and t.op ~= "remove" and t.op ~= "unwall"
        and not (t.time and shipped[t.time] and not t.shipped) then
      local zs = type(t.zs) == "table" and #t.zs == #pts / 2 and t.zs or nil
      -- (its points every TRACK_STEP with a height and the grid's surface there)
      local smp, prevZ = {}, nil
      for i = 1, #pts - 3, 2 do
        local ax, ay, bx, by = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
        local m = max(1, floor(Dist(ax, ay, bx, by) / CG.TRACK_STEP))
        for k = 0, (i + 3 >= #pts) and m or m - 1 do
          local f = k / m
          local x, y = ax + (bx - ax) * f, ay + (by - ay) * f
          local z = zs and (zs[(i + 1) / 2] + (zs[(i + 3) / 2] - zs[(i + 1) / 2]) * f) or nil
          local fs = CG.SurfacesAt(c, x, y, z or prevZ)
          local best
          for _, sf in ipairs(fs) do
            local dz = abs(sf.z - (z or prevZ or sf.z))
            if dz <= CG.TRACK_ON_Z and (not best or dz < abs(best.z - (z or prevZ or best.z))) then best = sf end
          end
          if best then prevZ = z or best.z end
          smp[#smp + 1] = { x, y, z or (best and best.z) or prevZ, best }
        end
      end
      -- (links between on-grid points about TRACK_CHUNK apart along it)
      local a, along = nil, 0
      for q = 1, #smp do
        if q > 1 then along = along + Dist(smp[q - 1][1], smp[q - 1][2], smp[q][1], smp[q][2]) end
        local p = smp[q]
        if p[4] then
          if a and (along >= CG.TRACK_CHUNK or q == #smp) and smp[a][4].s ~= p[4].s then
            local lp = {}
            for k = a, q do lp[#lp + 1] = { smp[k][1], smp[k][2], smp[k][3] or p[4].z } end
            -- (scaled by Options > Routing's Road tolerance, as the Router's road preference is)
            local f = Rt.RoadFactor and 1 / Rt.RoadFactor(1 / CG.TRACK_FACTOR) or CG.TRACK_FACTOR
            local cost = max(1, along) * f
            c.trackF = f
            local dz = (lp[#lp][3] or 0) - (lp[1][3] or 0)
            local down = dz < 0 and -dz > CG.TRACK_DROP_DZ + along -- (a drop off a ledge: one way down)
            local function Add(sa, sb, pp, ci)
              local L = { a = sa, b = sb, cost = cost, kind = 0, pts = pp, bci = ci, track = true }
              c.links[#c.links + 1] = L
              local o = c.tout[sa]
              if not o then o = {} c.tout[sa] = o end
              o[#o + 1] = #c.links
            end
            Add(smp[a][4].s, p[4].s, lp, p[4].ci)
            if not down then
              local rp = {}
              for k = #lp, 1, -1 do rp[#rp + 1] = lp[k] end
              Add(p[4].s, smp[a][4].s, rp, smp[a][4].ci)
            end
          end
          if not a or along >= CG.TRACK_CHUNK then a, along = q, 0 end
        end
      end
    end
  end
end

-- A* over the grid from `starts` ({ s, ci, cost }) to any of `goals` ({ [s] = extra cost }), toward (tx, ty). The way as
-- a list of steps { s, ci, link (the road link taken onto it, or nil) }, or nil. Pauses in the background (Breathe).
-- The city's streets (the Router's own roads in it: Data/Capitals.lua's, the player's) as its cells: { [ci] = true },
-- worked out once a city (in the background's slices). A step between two of them costs the costs' `road` (the world
-- grid's: Road tolerance; asked 2026-11-22 in Orgrimmar's Valley of Honor, the route went over the raised ground beside
-- the street instead of along it).
CG.STREET_HALF_YD = 2.5
function CG.Streets(c)
  if c.streets then return c.streets end
  local Rt = R()
  if c.level or not (Rt.NearestEdges and Rt.DebugGraph) then return nil end
  Rt.NearestEdges(c.cont, c.x0 + c.w * c.cell / 2, c.y0 + c.h * c.cell / 2)
  local g = Rt.DebugGraph(c.cont)
  if not (g and g.e) then return nil end
  local set, k = {}, 0
  local pad = CG.STREET_HALF_YD
  for _, e in ipairs(g.e) do
    k = k + 1
    if Rt.Breathe and k % 200 == 0 then Rt.Breathe(k, 200) end
    for i = 5, #e - 3, 2 do
      local ax, ay, bx, by = e[i], e[i + 1], e[i + 2], e[i + 3]
      if ax and bx and max(ax, bx) >= c.x0 and min(ax, bx) <= c.xmax and max(ay, by) >= c.y0 and min(ay, by) <= c.ymax then
        local m = max(1, math.ceil(Dist(ax, ay, bx, by) / (c.cell / 2)))
        for q = 0, m do
          local x, y = ax + (bx - ax) * q / m, ay + (by - ay) * q / m
          for _, o in ipairs({ { 0, 0 }, { pad, 0 }, { -pad, 0 }, { 0, pad }, { 0, -pad } }) do
            local ci = CG.CellAt(c, x + o[1], y + o[2])
            if ci then set[ci] = true end
          end
        end
      end
    end
  end
  c.streets = set
  return set
end

-- The costs of a search in city `c` (WorldGrid.lua's WG.Costs: the other faction's guards and lighter NPCs, zones too
-- high, the Road tolerance; one cost function for both grids), its streets, or nil on a level (Undercity) or with the
-- world grid's code missing.
function CG.Costs(c, sx, sy, tx, ty, opts)
  local WG = ns.WorldGrid
  if c.level or not (WG and WG.Costs) then return nil end
  local x = WG.Costs({ cont = c.cont, cell = c.cell, road = CG.ROAD_PREF, swim = 1.5 }, sx, sy, tx, ty, opts or {})
  x.streets = CG.Streets(c)
  x.maxDrop = CG.MaxDrop()
  return x
end
CG.ROAD_PREF = 0.85 -- a yard along a street costs this many (the capitals' streets; the open world's is worldgrid.ROAD_PREF), the Road tolerance's scaling on it

function CG.Search(c, starts, goals, tx, ty, x)
  local Rt = R()
  local maxDrop = x and x.maxDrop or CG.MaxDrop()
  -- (the jumps avoided on this trip, Nav.AvoidJump: no drop or jump link from within reach of one's top)
  local N = ns.Nav
  local jumpBanned = N and N.jumpBans and N.jumpBans[1] and N.JumpBanned or nil
  local FREE_FALL = (ns.Nav and ns.Nav.FALL_FREE) or 14
  -- (a step down's walked off on the walk's first try, as the open world's are, but only a curb's: a city's ledges are
  -- its structures' levels, walked (Orgrimmar's by the bank, 5.9 yd off a walk already 2 down, a 10 yd ledge))
  local stepDown = CG.CITY_STEP_DOWN
  local noDropIn = CG.NO_DROP_IN[c.name] ~= nil
  local FS = ns.FallSpells
  local castDrop = Rt.ExpertJumper and Rt.ExpertJumper() and FS and FS.MaxDrop and FS.MaxDrop() > FREE_FALL
    and FS.MaxDrop() or nil
  CG.TrackLinks(c)
  local t0 = debugprofilestop and debugprofilestop()
  local g, prev, via, cellOf, closed = {}, {}, {}, {}, {}
  local hk, hv = {}, {}
  local cell = c.cell
  local diag = cell * sqrt(2)
  local h = c.h
  local WG = ns.WorldGrid
  local Extra = x and x.any and WG and WG.Extra
  local streets = x and x.streets
  local road = x and x.road or 1
  local hw = streets and min(1, road) or 1
  -- (no more than the player's walks cost a yard either (c.trackF): weighed at the streets' or the ground's, the search
  -- cut across past a walk's corner, its cheaper way never looked at; Ironforge's by the bank, a quarter of it off)
  if c.trackF then hw = min(hw, c.trackF) end
  for _, st in ipairs(starts) do
    if not g[st.s] or st.cost < g[st.s] then
      g[st.s], cellOf[st.s] = st.cost, st.ci
      local px, py = Pt(c, st.s, st.ci)
      Push(hk, hv, st.cost + hw * Dist(px, py, tx, ty), st.s)
    end
  end
  local found, k = nil, 0
  local bestEnd
  while hk[1] do
    local f, s = Pop(hk, hv)
    if not closed[s] then
      closed[s] = true
      k = k + 1
      if Rt.Breathe then Rt.Breathe(k, CG.SLICE) end
      if k > CG.MAX_NODES then break end
      local extra = goals[s]
      if extra then
        -- (a goal settled: the best end, its own last stretch counted)
        local tot = g[s] + extra
        if not bestEnd or tot < bestEnd then bestEnd, found = tot, s end
      end
      if found and f >= bestEnd then break end
      local ci, gs = cellOf[s], g[s]
      local zs = Z(c, s)
      local i, j = floor(ci / h), ci % h
      local ea = 0
      if Extra then
        local sx_, sy_ = Pt(c, s, ci)
        ea = Extra(x, s, sx_, sy_)
      end
      local onStreet = streets and streets[ci]
      for d = 1, 8 do
        local kk = Link(c, s, d)
        if kk > 0 then
          local ni, nj = i + DX[d], j + DY[d]
          local nci = ni * h + nj
          local ns2 = First(c, nci) + kk - 1
          if not closed[ns2] then
            local dz = Z(c, ns2) - zs
            local step = (d > 4 and diag or cell)
            local sc = sqrt(step * step + dz * dz) + abs(dz) * CG.CLIMB_COST
            if onStreet and streets[nci] then sc = sc * road end
            if Extra then
              local px2, py2 = Pt(c, ns2, nci)
              sc = sc + step * (ea + Extra(x, ns2, px2, py2)) / 2
            end
            local cost = gs + sc
            if not g[ns2] or cost < g[ns2] then
              g[ns2], prev[ns2], via[ns2], cellOf[ns2] = cost, s, nil, nci
              local px, py = c.x0 + (ni + 0.5) * cell, c.y0 + (nj + 0.5) * cell
              Push(hk, hv, cost + hw * Dist(px, py, tx, ty), ns2)
            end
          end
        end
      end
      local out = c.out[s]
      local tout = c.tout and c.tout[s]
      if tout then
        for _, li in ipairs(tout) do
          local L = c.links[li]
          if not closed[L.b] and L.bci then
            local cost = gs + L.cost
            if not g[L.b] or cost < g[L.b] then
              g[L.b], prev[L.b], via[L.b], cellOf[L.b] = cost, s, li, L.bci
              local p = L.pts[#L.pts]
              Push(hk, hv, cost + hw * Dist(p[1], p[2], tx, ty), L.b)
            end
          end
        end
      end
      if out then
        for _, li in ipairs(out) do
          local L = c.links[li]
          -- (a drop only within the player's safe drop: the costs' maxDrop, CG.Walk's; FallSpells; none past a step down
          -- on the walk's first try without Expert jumper, CG.Walk)
          -- (and a step down right after another, a ledge in two: walked round as the open world's chains are)
          -- (and none from within reach of a jump avoided on this trip, Nav.AvoidJump)
          local chain = L.drop and x and x.noDrops and via[s] and c.links[via[s]].drop
          if not closed[L.b] and L.bci and not chain
              and not (L.drop and (L.drop > maxDrop or (x and x.noDrops and L.drop > stepDown)))
              and not (L.drop and L.drop > stepDown and noDropIn and CG.NoDropAt(c.name, L.pts[#L.pts][1], L.pts[#L.pts][2]))
              and not (jumpBanned and (L.drop or L.kind == 9) and jumpBanned(c.lv, L.pts[1][1], L.pts[1][2])) then
            local cost = gs + L.cost
            -- (a drop past the free one dearer by the yard: the hurt fall taken only where it saves a long way round.
            -- Orgrimmar's 26 yd ledge saves about 90 yd; Darnassus's 34 yd fall into the Enclave's hollow saved 64 yd on
            -- its spiral stairs, and landed 11 yd under the Rogue Trainer's floor)
            if L.drop and L.drop > FREE_FALL then
              if castDrop and L.drop <= castDrop then cost = cost + CG.CAST_DROP_COST
              else cost = cost + (L.drop - FREE_FALL) * CG.HURT_DROP_COST end
            end
            if not g[L.b] or cost < g[L.b] then
              g[L.b], prev[L.b], via[L.b], cellOf[L.b] = cost, s, li, L.bci
              local p = L.pts[#L.pts]
              Push(hk, hv, cost + hw * Dist(p[1], p[2], tx, ty), L.b)
            end
          end
        end
      end
    end
  end
  CG.stats.searches, CG.stats.nodes = CG.stats.searches + 1, CG.stats.nodes + k
  if t0 then CG.stats.ms = CG.stats.ms + (debugprofilestop() - t0) end
  CG.lastNodes = k
  if not found then return nil end
  local steps, s = {}, found
  while s do
    table.insert(steps, 1, { s = s, ci = cellOf[s], link = via[s] })
    s = prev[s]
  end
  return steps
end

-- Whether the grid walks the straight line from surface s0 (in cell c0) at (x0, y0) to (x1, y1), arriving on surface
-- `s1` (or any, nil): cell to cell along it, one axis at a time (never a corner's cut), always by a link. The surfaces
-- crossed { s, ci } when it does.
-- Whether the segment (ax, ay)-(bx, by) crosses a cell's wall (cx, cy)-(dx, dy) or passes within WALL_NEAR of it
-- (the wall's way is a straight line between its crossings of the cell: a tent's corner bends off it).
CG.WALL_NEAR = 0.45
CG.WALL_FLOOR_Z = 3 -- (a cell's wall stands over its floors this near the one it was found over)
local function PtSeg2(px, py, ax, ay, bx, by)
  local vx, vy = bx - ax, by - ay
  local L2 = vx * vx + vy * vy
  local t = L2 > 0 and max(0, min(1, ((px - ax) * vx + (py - ay) * vy) / L2)) or 0
  local qx, qy = ax + vx * t - px, ay + vy * t - py
  return qx * qx + qy * qy
end
function CG.Crosses(ax, ay, bx, by, cx, cy, dx, dy)
  local function Side(px, py, qx, qy, rx, ry) return (qx - px) * (ry - py) - (qy - py) * (rx - px) end
  local d1, d2 = Side(cx, cy, dx, dy, ax, ay), Side(cx, cy, dx, dy, bx, by)
  local d3, d4 = Side(ax, ay, bx, by, cx, cy), Side(ax, ay, bx, by, dx, dy)
  if ((d1 > 0) ~= (d2 > 0)) and ((d3 > 0) ~= (d4 > 0)) then return true end
  local n2 = CG.WALL_NEAR * CG.WALL_NEAR
  return PtSeg2(cx, cy, ax, ay, bx, by) < n2 or PtSeg2(dx, dy, ax, ay, bx, by) < n2
    or PtSeg2(ax, ay, cx, cy, dx, dy) < n2 or PtSeg2(bx, by, cx, cy, dx, dy) < n2
end
-- Whether the line (x0, y0)-(x1, y1) on surface s of cell ci crosses one of the cell's walls `list` on about its floor.
function CG.WallCut(c, list, ci, s, x0, y0, x1, y1)
  local z, f = Z(c, s), First(c, ci)
  for _, w in ipairs(list) do
    if abs(Z(c, f + w[5]) - z) <= CG.WALL_FLOOR_Z and CG.Crosses(x0, y0, x1, y1, w[1], w[2], w[3], w[4]) then return true end
  end
  return false
end
function CG.Line(c, s0, c0, x0, y0, x1, y1, s1)
  local cell, h = c.cell, c.h
  local i, j = floor(c0 / h), c0 % h
  local i1, j1 = floor((x1 - c.x0) / cell), floor((y1 - c.y0) / cell)
  local dx, dy = x1 - x0, y1 - y0
  local si, sj = dx > 0 and 1 or -1, dy > 0 and 1 or -1
  local tdx = dx ~= 0 and abs(cell / dx) or huge
  local tdy = dy ~= 0 and abs(cell / dy) or huge
  local fx = (x0 - c.x0) / cell - i
  local fy = (y0 - c.y0) / cell - j
  local tmx = dx ~= 0 and (si > 0 and (1 - fx) or fx) * tdx or huge
  local tmy = dy ~= 0 and (sj > 0 and (1 - fy) or fy) * tdy or huge
  local s = s0
  local crossed = { { s = s0, ci = c0 } }
  local w0 = c.walls and c.walls[c0] -- (and across its own cell's wall)
  if type(w0) == "table" and CG.WallCut(c, w0, c0, s0, x0, y0, x1, y1) then return nil end
  local tol2 = (CG.LINE_TOL * cell) ^ 2
  local tolEdge2 = (CG.LINE_TOL_EDGE * cell) ^ 2
  local mid = floor(c.offs / 2) * (c.offs + 1) -- (the middle's point code: its x step * offs + its y step)
  local guard = 0
  while i ~= i1 or j ~= j1 do
    guard = guard + 1
    if guard > 4000 then return nil end
    local d
    local dxs, dys = si > 0 and 1 or 3, sj > 0 and 2 or 4
    local xFirst = tmx < tmy
    -- (the line about through a cell's corner (the other axis's crossing before this one's next): the other way round
    -- the corner when this one has no link; still within LINE_TOL of the surfaces)
    if xFirst and Link(c, s, dxs) == 0 and tmy < tmx + tdx and Link(c, s, dys) > 0 then xFirst = false
    elseif not xFirst and Link(c, s, dys) == 0 and tmx < tmy + tdy and Link(c, s, dxs) > 0 then xFirst = true end
    if xFirst then
      i, tmx, d = i + si, tmx + tdx, dxs
    else
      j, tmy, d = j + sj, tmy + tdy, dys
    end
    if i < 0 or j < 0 or i >= c.w or j >= c.h then return nil end
    local kk = Link(c, s, d)
    if kk == 0 then return nil end
    local ci = i * h + j
    -- (never straight across a wall through a cell on the way: a corner cut by a tent's door would clip its canvas;
    -- a cell walled whole not at all but at the line's end)
    local wl = c.walls and c.walls[ci]
    if wl then
      if wl == true then
        if i ~= i1 or j ~= j1 then return nil end
      elseif CG.WallCut(c, wl, ci, First(c, ci) + kk - 1, x0, y0, x1, y1) then
        return nil
      end
    end
    s = First(c, ci) + kk - 1
    -- (and near the surface's own point: a cell's surface may cover only a corner of it, a walkway's edge or a ledge,
    -- and the line through the rest of the cell is over nothing)
    if i ~= i1 or j ~= j1 then
      local px, py = Pt(c, s, ci)
      local L2 = dx * dx + dy * dy
      local t = L2 > 0 and max(0, min(1, ((px - x0) * dx + (py - y0) * dy) / L2)) or 0
      local qx, qy = x0 + dx * t - px, y0 + dy * t - py
      local tl2 = DEC[byte(c.s, s * SURF + 3)] == mid and tol2 or tolEdge2
      if qx * qx + qy * qy > tl2 then return nil end
    end
    crossed[#crossed + 1] = { s = s, ci = ci }
  end
  if s1 and s ~= s1 then return nil end
  -- (no straight line over a rise or a dip off the climb between its ends: a rock or a ledge beside the street is a
  -- floor's edge, never cut across; Orgrimmar's Valley of Honor, 2026-11-22)
  local n = #crossed
  if n > 2 then
    local z0, z1 = Z(c, crossed[1].s), Z(c, crossed[n].s)
    for m = 2, n - 1 do
      if abs(Z(c, crossed[m].s) - (z0 + (z1 - z0) * (m - 1) / (n - 1))) > CG.LINE_RISE then return nil end
    end
  end
  return crossed
end

-- The steps (CG.Search's) as a route: string-pulled along each run between road links, from (sx, sy) to (tx, ty).
-- { pts, kinds, length, road, zs or fz, cityGrid }.
function CG.Pull(c, steps, sx, sy, tx, ty)
  local Rt = R()
  local WALK = Rt.KIND_OFFROAD or 1
  local pts, kinds, hs, onLink, bends = {}, {}, {}, {}, {}
  local function Put(x, y, z, kind)
    local n = #pts
    if n >= 2 and abs(pts[n - 1] - x) < 0.05 and abs(pts[n] - y) < 0.05 then return end
    if n >= 2 then kinds[#kinds + 1] = kind end
    pts[n + 1], pts[n + 2] = x, y
    hs[#hs + 1] = z
  end
  -- (the steps' points: the first and last the leg's own ends)
  local P = {}
  for idx, st in ipairs(steps) do
    local x, y = Pt(c, st.s, st.ci)
    P[idx] = { s = st.s, ci = st.ci, x = x, y = y, z = Z(c, st.s), link = st.link }
  end
  P[1].x, P[1].y = sx, sy
  P[#P].x, P[#P].y = tx, ty
  -- (runs: between road links)
  local a = 1
  Put(P[1].x, P[1].y, P[1].z, WALK)
  local k = 0
  while a < #P do
    -- the farthest step b in this run the grid walks straight to from a (a few past the first that fails: a corner)
    local b, misses = a + 1, 0
    local best = a + 1
    while b <= #P and not P[b].link do
      k = k + 1
      if Rt.Breathe and k % 20 == 0 then Rt.Breathe(k, 20) end
      local line = CG.Line(c, P[a].s, P[a].ci, P[a].x, P[a].y, P[b].x, P[b].y, P[b].s)
      if line then
        best, misses = b, 0
      else
        misses = misses + 1
        if misses > 6 then break end
      end
      b = b + 1
    end
    if P[a + 1].link then best = a + 1 end
    local nb = P[best]
    if nb.link then
      -- (a road link: its points, as the road went)
      local L = c.links[nb.link]
      local kind = WALK
      if L.kind == 4 then kind = Rt.KIND_DROP or 4
      elseif L.kind == 9 then kind = Rt.KIND_JUMP or 8 -- (a running jump across a gap: navfeatures)
      elseif L.kind == 5 then kind = (L.pts[#L.pts][3] > L.pts[1][3]) and (Rt.KIND_LIFT_UP or 6) or (Rt.KIND_LIFT_DOWN or 5) end
      -- (a drop's fall noted by its top, the point its first piece starts at: FallSpells' steps)
      if L.drop and Rt.NoteDrop and #pts >= 2 then Rt.NoteDrop(pts[#pts - 1], pts[#pts], L.drop) end
      local k0 = #kinds
      for _, p in ipairs(L.pts) do Put(p[1], p[2], p[3], kind) end
      -- (on to the cell's own point, unless another link goes on from it: a recorded walk's links one after another,
      -- each out to its cell's point and back made a spur every few yards down Darnassus's spiral)
      local nx = P[best + 1]
      if not (nx and nx.link and best + 1 < #P) then Put(nb.x, nb.y, nb.z, kind) end
      for m = k0 + 1, #kinds do onLink[m] = true end -- (its pieces, and the step onto it in the cell it leaves)
    else
      -- (a straight stretch: the ground's heights along it kept where they bend from a straight climb by more than
      -- Z_BEND: stairs, a ramp's foot, a rise and fall; the directions say stairs by them, the map its floors)
      local line = CG.Line(c, P[a].s, P[a].ci, P[a].x, P[a].y, nb.x, nb.y, nb.s)
      if line and #line > 2 then
        local ax, ay, vx, vy = P[a].x, P[a].y, nb.x - P[a].x, nb.y - P[a].y
        local L2 = vx * vx + vy * vy
        local ts, zs = {}, {}
        for m = 1, #line do
          local px, py = Pt(c, line[m].s, line[m].ci)
          ts[m] = L2 > 0 and max(0, min(1, ((px - ax) * vx + (py - ay) * vy) / L2)) or 0
          zs[m] = Z(c, line[m].s)
        end
        ts[1], zs[1], ts[#line], zs[#line] = 0, P[a].z, 1, nb.z
        local keep = {}
        local function Split(i0, i1)
          local worst, wi = CG.Z_BEND, nil
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
          Put(ax + vx * ts[m], ay + vy * ts[m], zs[m], WALK)
          bends[#pts / 2] = true -- (a point on a straight line: its heights, not a corner)
        end
      end
      Put(nb.x, nb.y, nb.z, WALK)
    end
    a = best
  end
  if #pts < 4 then Put(tx + 0.01, ty, P[#P].z, WALK) end
  local length = 0
  for m = 1, #kinds do length = length + Dist(pts[2 * m - 1], pts[2 * m], pts[2 * m + 1], pts[2 * m + 2]) end
  local r = { pts = pts, kinds = kinds, length = length, road = length, cityGrid = c.name, onLink = onLink, bends = bends }
  if c.level then r.zs = hs else r.fz = hs end
  return r
end

---------------------------------------------------------------------------------------------------- legs
-- The surfaces a leg's end may start or end on, by its height when known: { s, ci, cost }.
local function Ends(c, x, y, z)
  local out = {}
  for _, f in ipairs(CG.SurfacesAt(c, x, y, z)) do
    local dz = z and abs(f.z - z) or 0
    if not z or dz <= CG.FLOOR_Z or not out[1] then
      out[#out + 1] = { s = f.s, ci = f.ci, z = f.z, cost = Dist(x, y, f.x, f.y) + max(0, dz - CG.FLOOR_Z) * CG.Z_COST }
    end
  end
  return out
end
CG.Ends = Ends

CG.routes, CG.order = {}, {}
local function Remember(key, r)
  if not CG.routes[key] then CG.order[#CG.order + 1] = key end
  CG.routes[key] = r
  while #CG.order > CG.CACHE do CG.routes[table.remove(CG.order, 1)] = nil end
end
local function ZKey(z) return z and string.format("%.0f", z) or "-" end

-- A route found to the same stop from near (sx, sy): from here straight onto it (the grid walks that line), then along
-- it. (The player moves on: each reroute would search again.)
function CG.Reuse(c, sx, sy, sz, tkey)
  local starts = Ends(c, sx, sy, sz)
  if not starts[1] then return nil end
  for key, r in pairs(CG.routes) do
    if r.tkey == tkey and r.c == c and r.route then
      local pts, hs = r.route.pts, r.route.zs or r.route.fz
      local best, bi, bx, by
      for i = 1, #pts / 2 - 1 do
        local ax, ay, qx, qy = pts[2 * i - 1], pts[2 * i], pts[2 * i + 1], pts[2 * i + 2]
        local vx, vy = qx - ax, qy - ay
        local L2 = vx * vx + vy * vy
        local t = L2 > 0 and max(0, min(1, ((sx - ax) * vx + (sy - ay) * vy) / L2)) or 0
        local px, py = ax + vx * t, ay + vy * t
        local d = Dist(sx, sy, px, py)
        if d <= CG.REUSE_YD and (not best or d < best) and r.route.kinds[i] == (R().KIND_OFFROAD or 1) then
          local z = hs and hs[i] and hs[i + 1] and hs[i] + (hs[i + 1] - hs[i]) * t
          local tgt = CG.SurfacesAt(c, px, py, z)[1]
          if tgt and (not z or abs(tgt.z - z) <= CG.FLOOR_Z) then
            for _, st in ipairs(starts) do
              if CG.Line(c, st.s, st.ci, sx, sy, px, py, tgt.s) then
                best, bi, bx, by = d, i, px, py
                break
              end
            end
          end
        end
      end
      if bi then
        local out, kinds, zs, onLink, bends = { sx, sy }, {}, { starts[1].z }, {}, {}
        local rl, rb = r.route.onLink or {}, r.route.bends or {}
        local WALK = R().KIND_OFFROAD or 1
        local function Put(x, y, z, kind, link, bend)
          if abs(out[#out - 1] - x) < 0.05 and abs(out[#out] - y) < 0.05 then return end
          out[#out + 1], out[#out + 2] = x, y
          kinds[#kinds + 1] = kind
          zs[#zs + 1] = z
          if link then onLink[#kinds] = true end -- (its road links' pieces and bends kept: the old walk's own)
          if bend then bends[#zs] = true end
        end
        local z1 = hs and hs[bi] or nil
        Put(bx, by, z1, WALK)
        for i = bi + 1, #pts / 2 do Put(pts[2 * i - 1], pts[2 * i], hs and hs[i], r.route.kinds[i - 1], rl[i - 1], rb[i]) end
        if #out < 4 then return nil end
        local length = 0
        for m = 1, #kinds do length = length + Dist(out[2 * m - 1], out[2 * m], out[2 * m + 1], out[2 * m + 2]) end
        local nr = { pts = out, kinds = kinds, length = length, road = length, cityGrid = c.name, reused = true,
          onLink = onLink, bends = bends }
        if c.level then nr.zs = zs else nr.fz = zs end
        return nr
      end
    end
  end
  return nil
end

-- The grid's walk for a leg in city `c`: a route, false (no way on the grid: the Router's own), or "pending" (being
-- searched in the background; the route is worked out again when it's found).
CG.jobs = {}
-- The biggest drop a grid walk takes (its drop links' heights): the player's safe drop (Nav.SafeDrop: Options' Safe
-- drop, 39 yd by default, in combat too; a fall spell's while one is ready);
-- the bake keeps drops up to navfeatures.BIG_DROP, each checked for a clear take-off and landing.
function CG.MaxDrop()
  local N = ns.Nav
  if N and N.SafeDrop then return N.SafeDrop() end -- (the player's safe drop, a fall spell's when one is ready)
  return N and N.FALL_FREE or 14
end

-- A level lift's way off at its foot (navfeatures.lift_exits; `exits`: "x,y,z,...;..." from the lift's end over the mesh to
-- the grid's first floor, through the landing's arch): the one whose lift end is within LIFT_EXIT_R of (x, y), or nil.
-- A walk from (or to) a lift's end goes by it, not by a straight line to the nearest floor across the landing's wall
-- (Kooki3z 2026-11-22, Undercity's east lift: "Slight left now" into the wall).
CG.LIFT_EXIT_R = 4
function CG.LiftExit(c, x, y)
  if not c.d.exits then return nil end
  if not c.exits then
    c.exits = {}
    for item in c.d.exits:gmatch("[^;]+") do
      local nums, e = {}, {}
      for v in item:gmatch("[^,]+") do nums[#nums + 1] = tonumber(v) end
      for k = 1, #nums - 2, 3 do e[#e + 1] = { nums[k], nums[k + 1], nums[k + 2] } end
      if #e >= 2 then c.exits[#c.exits + 1] = e end
    end
  end
  for _, e in ipairs(c.exits) do
    if Dist(x, y, e[1][1], e[1][2]) <= CG.LIFT_EXIT_R then return e end
  end
  return nil
end

-- Route r with `pre` (points from the walk's own start) before it and `post` after it (to its own end).
local function Splice(r, pre, post)
  local WALK = R().KIND_OFFROAD or 1
  local pts, kinds, hs, onLink, bends = {}, {}, {}, {}, {}
  local rh, rl, rb = r.zs or r.fz or {}, r.onLink or {}, r.bends or {}
  local function Put(x, y, z, kind, link, bend)
    local n = #pts
    if n >= 2 and abs(pts[n - 1] - x) < 0.05 and abs(pts[n] - y) < 0.05 then return end
    if n >= 2 then
      kinds[#kinds + 1] = kind
      if link then onLink[#kinds] = true end -- (the walk's road links' pieces kept marked as theirs)
    end
    pts[n + 1], pts[n + 2] = x, y
    hs[#hs + 1] = z or false
    if bend then bends[#hs] = true end
  end
  for _, p in ipairs(pre or {}) do Put(p[1], p[2], p[3], WALK) end
  for k = 1, #r.pts / 2 do Put(r.pts[2 * k - 1], r.pts[2 * k], rh[k], r.kinds[k - 1] or WALK, rl[k - 1], rb[k]) end
  for _, p in ipairs(post or {}) do Put(p[1], p[2], p[3], WALK) end
  local length = 0
  for m = 1, #kinds do length = length + Dist(pts[2 * m - 1], pts[2 * m], pts[2 * m + 1], pts[2 * m + 2]) end
  local out = { pts = pts, kinds = kinds, length = length, road = length, cityGrid = r.cityGrid, bends = bends,
    onLink = onLink }
  if r.zs then out.zs = hs else out.fz = hs end
  return out
end

function CG.Walk(c, sx, sy, sz, tx, ty, tz, maxDrop)
  local WG = ns.WorldGrid
  -- (the drops taken: within the player's safe drop, Nav.SafeDrop; another limit, another walk)
  maxDrop = maxDrop or CG.MaxDrop()
  local tkey = string.format("%s:%.0f:%.0f:%s:%s|%s%s", c.name, tx, ty, ZKey(tz),
    maxDrop and string.format("%.0f", math.min(maxDrop, 9999)) or "-", WG and WG.CostKey and WG.CostKey() or "",
    (R().ExpertJumper and R().ExpertJumper()) and "|x" or "")
  local key = string.format("%.0f:%.0f:%s>%s|%s", sx, sy, ZKey(sz), tkey, TrackKey())
  local got = CG.routes[key]
  if got then return got.route or false end
  local reused = CG.Reuse(c, sx, sy, sz, tkey)
  if reused then return reused end
  local function Work()
    -- (from or to a lift's end: by its way off, from where it reaches the grid)
    local ex, gx = CG.LiftExit(c, sx, sy), CG.LiftExit(c, tx, ty)
    local ax, ay, az, bx, by, bz = sx, sy, sz, tx, ty, tz
    if ex then ax, ay, az = ex[#ex][1], ex[#ex][2], ex[#ex][3] end
    if gx then bx, by, bz = gx[#gx][1], gx[#gx][2], gx[#gx][3] end
    local starts = Ends(c, ax, ay, az)
    local goals = {}
    for _, e in ipairs(Ends(c, bx, by, bz)) do goals[e.s] = e.cost end
    local route = false
    if starts[1] and next(goals) then
      local x = CG.Costs(c, ax, ay, bx, by) or {}
      if maxDrop then x.maxDrop = maxDrop end
      -- (Kooki3z 2026-11-23: in a city, no hops from one level of a structure to another, Darnassus's spiral, Thunder
      -- Bluff's mesa paths, Undercity's ramps, a tower's stairs: the walkway walked, a drop only where there's no
      -- walkable way at all; an Expert jumper (option expertJumper) hops, within the safe drop)
      local Rt = R()
      local expert = Rt.ExpertJumper and Rt.ExpertJumper()
      local steps
      if not expert then
        x.noDrops = true
        steps = CG.Search(c, starts, goals, bx, by, x)
        x.noDrops = nil
      end
      if not steps then steps = CG.Search(c, starts, goals, bx, by, x) end
      if steps then route = CG.Pull(c, steps, ax, ay, bx, by) end
    end
    if route and (ex or gx) then
      local pre, post = nil, nil
      if ex then
        pre = { { sx, sy, ex[1][3] } }
        for k = 2, #ex - 1 do pre[#pre + 1] = ex[k] end
      end
      if gx then
        post = {}
        for k = #gx - 1, 2, -1 do post[#post + 1] = gx[k] end
        post[#post + 1] = { tx, ty, gx[1][3] }
      end
      route = Splice(route, pre, post)
    end
    Remember(key, { c = c, tkey = tkey, route = route })
    return route
  end
  local Rt = R()
  local co, main = coroutine.running()
  if Rt.SYNC_WALKS or (co and not main) then return Work() end
  if not CG.jobs[key] then
    CG.jobs[key] = true
    CG.stats.pending = CG.stats.pending + 1
    Rt.Background("citygrid:" .. key, Work, function()
      CG.jobs[key] = nil
      local N = ns.Nav
      if N and N.Invalidate and CG.On() then N.Invalidate(true) end -- (the route again, with the grid's walk)
    end, nil, nil, function()
      CG.jobs[key] = nil -- (dropped unfinished, R.Reset: searched again when asked)
      local N = ns.Nav
      if N and N.Invalidate and CG.On() then N.Invalidate(true) end
    end)
  end
  return "pending"
end

-- Routes `a` then `b` as one (b from where a ends); heights as `fz` (a continent) or `zs` (a level), false where unknown.
local function Concat(a, b, useZs)
  local pts, kinds, hs, onLink, bends = {}, {}, {}, {}, {}
  local gpts = {} -- (each point's height a grid's own: the world grid's or a city grid's walk, not the Router's road)
  local function Add(r)
    local p, rh = r.pts, r.zs or r.fz
    local whole = r.gpts == nil and (r.worldGrid or r.cityGrid) and true or false
    for k = 1, #p / 2 do
      local n = #pts
      local x, y = p[2 * k - 1], p[2 * k]
      if not (n >= 2 and abs(pts[n - 1] - x) < 0.05 and abs(pts[n] - y) < 0.05) then
        if n >= 2 then
          kinds[#kinds + 1] = r.kinds[k - 1] or (R().KIND_OFFROAD or 1)
          if r.onLink and r.onLink[k - 1] then onLink[#kinds] = true end
        end
        pts[n + 1], pts[n + 2] = x, y
        hs[#hs + 1] = (rh and rh[k]) or false
        gpts[#hs] = whole or (r.gpts and r.gpts[k]) or false
        if r.bends and r.bends[k] then bends[#hs] = true end
      end
    end
  end
  Add(a)
  Add(b)
  local length, road = 0, 0
  for m = 1, #kinds do
    local d = Dist(pts[2 * m - 1], pts[2 * m], pts[2 * m + 1], pts[2 * m + 2])
    length = length + d
    if kinds[m] == R().KIND_ROAD then road = road + d end
  end
  local r = { pts = pts, kinds = kinds, length = length, road = road, cityGrid = a.cityGrid or b.cityGrid,
    blocked = a.blocked or b.blocked, pending = a.pending or b.pending, onLink = onLink, bends = bends, gpts = gpts }
  if useZs then r.zs = hs else r.fz = hs end
  return r
end

-- The first (or, `last`, the last) spot along route r inside city `name`'s grid with a surface: x, y, the route's
-- height there, and the index of the route's point before it.
local function Crossing(r, cont, name, c, last)
  local pts, hs = r.pts, r.zs or r.fz
  local n = #pts / 2
  local a, b, step = 1, n - 1, 1
  if last then a, b, step = n - 1, 1, -1 end
  for i = a, b, step do
    local ax, ay, bx, by = pts[2 * i - 1], pts[2 * i], pts[2 * i + 1], pts[2 * i + 2]
    local L = Dist(ax, ay, bx, by)
    local m = max(1, floor(L / CG.SPLICE_STEP))
    for q = 0, m do
      local t = last and (1 - q / m) or q / m
      local x, y = ax + (bx - ax) * t, ay + (by - ay) * t
      if CG.CityFor(cont, x, y) == name then
        local za, zb = hs and hs[i], hs and hs[i + 1]
        if not (za and zb and za > -9000 and zb > -9000) then za, zb = nil, nil end -- (-10000: a road with no height)
        local z = za and (za + (zb - za) * t) or nil
        local f = CG.SurfacesAt(c, x, y, z)[1]
        if f and (not z or abs(f.z - z) <= CG.FLOOR_Z) then return x, y, z, i end
      end
    end
  end
  return nil
end

-- The leg (Router.Route's): the grid's walk where it applies (see the top), else nil for the Router's own. "pending"
-- while the grid's walk is searched (the Router's own meanwhile, marked pending).
CG.OFF_GRID_Z = 5 -- yards: a stop (or a start) this far from every floor of the grid round it is off the grid (CG.Leg):
-- Ironforge's First Aid trainer, 6 yd over the landing under him on a floor the mesh lacks; Stormwind's Cooking Trainer
local function OffGrid(c, x, y, z)
  for _, f in ipairs(CG.SurfacesAt(c, x, y, z)) do
    if abs(f.z - z) <= CG.OFF_GRID_Z then return false end
  end
  return true
end
CG.OffGrid = OffGrid

function CG.Leg(cont, sx, sy, tx, ty, opts)
  if not CG.On() then return nil end
  local a, b = CG.CityFor(cont, sx, sy), CG.CityFor(cont, tx, ty)
  if not (a or b) or (a and b and a ~= b) then return nil end
  local name = a or b
  local c = CG.City(name)
  if not c then return nil end
  -- (a stop at a height the city's grid has no floor near, under it: Ironforge's Hall of Thanes' portal at 399, the halls
  -- at 500: the Router's own, which follows the player's walks down there; Kooki3z 2026-11-22, "still wrong")
  if opts.tz and tx >= c.x0 and ty >= c.y0 and tx < c.xmax and ty < c.ymax and OffGrid(c, tx, ty, opts.tz) then
    return nil
  end
  local sz = opts.z
  if a and CG.PlayerStart(cont, sx, sy) then sz = CG.PlayerFloorZ(cont, sx, sy) or sz
  elseif a and sz and OffGrid(c, sx, sy, sz) then return nil end -- (from such a floor the same: the Router's own)
  -- (no height for the start, not the player's: the nearest road's there, as the Router's own takes it, else the
  -- ground's, where the grid has a floor at it; not every floor at once, the lowest winning: from Orgrimmar's Hall of
  -- Legends the walk began on the Valley's floor under its ledge)
  local function RoadZ(x, y)
    if c.level then return nil end
    local Rt = R()
    local near = Rt.HeightsNear and Rt.HeightsNear(cont, x, y, CG.START_ROAD_YD)
    local ground = Rt.GroundZ and Rt.GroundZ(cont, x, y)
    -- (roads on two levels near it, a sunken place's and the one over it: the one nearest the terrain's height with a
    -- floor of the grid at it, the floor reached through the place's entrance. The coordinator 2026-11-24, Orgrimmar's
    -- Cleft of Shadow: the Drag's road over it, 46, was taken first and the trainer's stop put on the rock top, the
    -- Cleft's road at -12, its floor -14, the terrain -25. One road level: as before (Darnassus's Enclave road, not the
    -- hollow under it, which has none))
    -- (the road near it SUNKEN_Z or more over the terrain: a sunken place under it, the roads further round looked at
    -- too, SUNKEN_ROAD_YD: the Cleft's own are 10-40 yd from its trainers, the Drag's 46 within 8)
    local sunken = ground and near and near[1] and near[1].z > ground + CG.SUNKEN_Z and InSunken(name, x, y)
    if sunken then near = Rt.HeightsNear(cont, x, y, CG.SUNKEN_ROAD_YD) or near end
    local cands = {}
    if sunken then
      for _, h in ipairs(near) do cands[#cands + 1] = h.z end
      table.sort(cands, function(p, q) return abs(p - ground) < abs(q - ground) end)
    else
      -- (elsewhere the nearest road's, else the terrain's, as before: the terrain's nearest everywhere put Darnassus's
      -- stops on the hollows under its roads, the capitals' sweep: 48 off their floor before, 58)
      cands[1] = (near and near[1] and near[1].z) or ground
    end
    for _, gz in ipairs(cands) do
      for _, f in ipairs(CG.SurfacesAt(c, x, y, gz)) do
        if abs(f.z - gz) <= CG.FLOOR_Z then return gz end
      end
    end
    return nil
  end
  if a and sz == nil then sz = RoadZ(sx, sy) end
  -- (and a stop with none the same: back up from the Rogue Trainer to Darnassus's Enclave road, not the hollow's floor
  -- under it)
  local tz = opts.tz
  if b and tz == nil then tz = RoadZ(tx, ty) end
  local md = opts.maxDrop or (ns.Nav and ns.Nav.SafeDrop and ns.Nav.SafeDrop()) or nil
  if a and b then
    local r = CG.Walk(c, sx, sy, sz, tx, ty, tz, md)
    if r == "pending" then return "pending" end
    if not r then
      CG.stats.own = CG.stats.own + 1
      return nil
    end
    CG.stats.grid = CG.stats.grid + 1
    return r
  end
  -- (one end in the city: the Router's own route, cut where it comes into the city's grid)
  local own = R().RouteOwn(cont, sx, sy, tx, ty, opts)
  if not (own and own.pts and #own.pts >= 4) or own.pending or own.noWay or own.unconnected then return own end
  if a then
    local x, y, z, i = Crossing(own, cont, name, c, true)
    if not x then return own end
    local inside = CG.Walk(c, sx, sy, sz, x, y, z, md)
    if inside == "pending" then
      own.pending = true
      return own
    end
    if not inside then return own end
    -- (the join's height the grid's floor there, not the Router's road's: Concat keeps the first of the two points,
    -- and a road's height a few yards off the floor made a step in the route's heights)
    local ih = inside.zs or inside.fz
    z = (ih and ih[#ih]) or z
    local rest = { pts = { x, y }, kinds = {}, zs = { z or false }, fz = { z or false } }
    for k = i + 1, #own.pts / 2 do
      rest.pts[#rest.pts + 1], rest.pts[#rest.pts + 2] = own.pts[2 * k - 1], own.pts[2 * k]
      rest.kinds[#rest.kinds + 1] = own.kinds[k - 1]
      local hh = own.zs or own.fz
      rest.zs[#rest.zs + 1] = hh and hh[k] or false
    end
    rest.fz = rest.zs
    CG.stats.spliced = CG.stats.spliced + 1
    return Concat(inside, rest, c.level ~= nil)
  end
  local x, y, z, i = Crossing(own, cont, name, c, false)
  if not x then return own end
  local inside = CG.Walk(c, x, y, z, tx, ty, tz, md)
  if inside == "pending" then
    own.pending = true
    return own
  end
  if not inside then return own end
  local head = { pts = {}, kinds = {}, zs = {} }
  local hh = own.zs or own.fz
  for k = 1, i do
    head.pts[#head.pts + 1], head.pts[#head.pts + 2] = own.pts[2 * k - 1], own.pts[2 * k]
    if k > 1 then head.kinds[#head.kinds + 1] = own.kinds[k - 1] end
    head.zs[#head.zs + 1] = hh and hh[k] or false
  end
  head.pts[#head.pts + 1], head.pts[#head.pts + 2] = x, y
  head.kinds[#head.kinds + 1] = own.kinds[i]
  local ih = inside.zs or inside.fz
  head.zs[#head.zs + 1] = (ih and ih[1]) or z or false
  head.fz = head.zs
  CG.stats.spliced = CG.stats.spliced + 1
  local r = Concat(head, inside, c.level ~= nil)
  r.blocked = own.blocked
  return r
end

-- Whether a leg's start is where the player stands (their floor, CG.TrackFloor's, is its height).
CG.PLAYER_YD = 3
function CG.PlayerStart(cont, x, y)
  local t = CG.track
  return t ~= nil and t.level == cont and Dist(t.x, t.y, x, y) <= CG.PLAYER_YD
end

---------------------------------------------------------------------------------------------------- the player's floor
-- The height band (see the top): readings of range checks against NPCs the player names, each { x, y, z (the NPC's
-- spawn), r (yards), inside (true: in range), at, px, py (where the player stood) }.
CG.BAND_UNITS = { "target", "mouseover", "softinteract", "softfriend", "npc" }
CG.INTERACT_YD = { [2] = 11.11, [3] = 9.9, [4] = 28 } -- CheckInteractDistance's (trade, duel, follow)
CG.RANGE_SLACK = 3 -- yards: in range means within the range and at most this more (the bodies' reach)
CG.WANDER_YD = 2 -- yards an NPC may stand off its spawn
CG.SPAWN_YD = 60 -- an NPC's spawn this near the player is the one it stands at ...
CG.SPAWN_ALONE_YD = 40 -- ... when no other spawn of it is this near that one
CG.BAND_KEEP_SECONDS = 8 -- a reading counts this long ...
CG.BAND_KEEP_YD = 3 -- ... while the player is this near where it was taken
CG.BAND_EVERY = 0.25 -- seconds between looks
-- Spells that may be cast on a friendly NPC (a class's own; one not known is no check: IsSpellInRange says nil).
CG.BAND_SPELLS = { 2050, 17, 1243, 635, 19740, 5185, 774, 1126, 331, 1459, 5697 }

CG.readings = {}
-- The spawn of creature `id` the unit stands at, near (px, py) on `level`: x, y, z, or nil (none near, or two near
-- each other: can't tell which).
function CG.SpawnOf(id, level, px, py)
  local L = ns.Layers
  if not (L and L.ShippedNpcs) then return nil end
  local _, byId = L.ShippedNpcs()
  local n = byId and byId[id]
  local sp = n and n.spawns
  if not sp then return nil end
  local best, bd, second
  for i = 1, #sp - 3, 4 do
    if sp[i] == level then
      local d = Dist(sp[i + 1], sp[i + 2], px, py)
      if d <= CG.SPAWN_YD then
        if not bd or d < bd then
          second = best
          best, bd = i, d
        elseif not second then second = i end
      end
    end
  end
  if not best then return nil end
  if second and Dist(sp[best + 1], sp[best + 2], sp[second + 1], sp[second + 2]) < CG.SPAWN_ALONE_YD then return nil end
  return sp[best + 1], sp[best + 2], sp[best + 3], n.name
end

-- A unit's checks now: { r, inside } each, the game's own range checks (nil ones left out).
function CG.Checks(unit)
  local out = {}
  if CheckInteractDistance then
    for idx, yd in pairs(CG.INTERACT_YD) do
      local ok, v = pcall(CheckInteractDistance, unit, idx)
      if ok and v ~= nil and not ns.IsSecret(v) then out[#out + 1] = { r = yd, inside = v and true or false, src = "interact" .. idx } end
    end
  end
  local S = C_Spell
  if S and S.IsSpellInRange and S.GetSpellInfo then
    for _, id in ipairs(CG.BAND_SPELLS) do
      local ok, v = pcall(S.IsSpellInRange, id, unit)
      if ok and v ~= nil and not ns.IsSecret(v) then
        local ok2, info = pcall(S.GetSpellInfo, id)
        local r = ok2 and type(info) == "table" and info.maxRange
        if type(r) == "number" and r > 0 and not ns.IsSecret(r) then
          out[#out + 1] = { r = r, inside = v and true or false, src = "spell" .. id }
        end
      end
    end
  end
  local I = C_Item
  if I and I.IsItemInRange then
    for _, it in ipairs(CG.RangeItems()) do
      local ok, v = pcall(I.IsItemInRange, it.id, unit)
      if ok and v ~= nil and not ns.IsSecret(v) then out[#out + 1] = { r = it.r, inside = v and true or false, src = "item" .. it.id } end
    end
  end
  return out
end

-- The items in the bags whose use has a range (its spell's): { id, r }. Looked at again every RANGE_ITEMS_SECONDS.
CG.RANGE_ITEMS_SECONDS = 30
function CG.RangeItems()
  local now = GetTime()
  if CG.items and now - CG.itemsAt < CG.RANGE_ITEMS_SECONDS then return CG.items end
  local out, seen = {}, {}
  local Cn, I, S = C_Container, C_Item, C_Spell
  if Cn and Cn.GetContainerNumSlots and Cn.GetContainerItemID and I and I.GetItemSpell and S and S.GetSpellInfo then
    for bag = 0, 4 do
      local ok, n = pcall(Cn.GetContainerNumSlots, bag)
      for slot = 1, ok and n or 0 do
        local ok2, id = pcall(Cn.GetContainerItemID, bag, slot)
        if ok2 and id and not seen[id] then
          seen[id] = true
          local ok3, _, spell = pcall(I.GetItemSpell, id)
          if ok3 and spell then
            local ok4, info = pcall(S.GetSpellInfo, spell)
            local r = ok4 and type(info) == "table" and info.maxRange
            if type(r) == "number" and r > 0 and r < 60 then out[#out + 1] = { id = id, r = r } end
          end
        end
      end
    end
  end
  CG.items, CG.itemsAt = out, now
  return out
end

-- New readings from the units the player names, at (px, py) on `level`.
function CG.Look(level, px, py)
  local now = GetTime()
  local seen = {}
  for _, unit in ipairs(CG.BAND_UNITS) do
    local ok, exists = pcall(UnitExists or function() return false end, unit)
    if ok and exists and not ns.IsSecret(exists) and not (UnitIsPlayer and UnitIsPlayer(unit)) then
      local guid = UnitGUID and UnitGUID(unit)
      local id = guid and not ns.IsSecret(guid) and ns.Nav and ns.Nav.NpcOf and ns.Nav.NpcOf(guid)
      if id and not seen[guid] then
        seen[guid] = true
        local x, y, z, name = CG.SpawnOf(id, level, px, py)
        if x then
          for _, ck in ipairs(CG.Checks(unit)) do
            CG.readings[#CG.readings + 1] = { x = x, y = y, z = z, r = ck.r, inside = ck.inside, src = ck.src,
              at = now, px = px, py = py, npc = name, unit = unit, level = level }
          end
        end
      end
    end
  end
  -- (the old ones dropped: too old, or the player moved off)
  local kept = {}
  for _, rd in ipairs(CG.readings) do
    if rd.level == level and now - rd.at <= CG.BAND_KEEP_SECONDS and Dist(rd.px, rd.py, px, py) <= CG.BAND_KEEP_YD then
      kept[#kept + 1] = rd
    end
  end
  -- (one per NPC and check: the newest)
  local by, out = {}, {}
  for i = #kept, 1, -1 do
    local rd = kept[i]
    local k = string.format("%.1f:%.1f:%s", rd.x, rd.y, rd.src)
    if not by[k] then by[k] = true out[#out + 1] = rd end
  end
  CG.readings = out
  return out
end

-- The band of heights the readings allow at (px, py): a list of { lo, hi } (nil: no reading, every height).
function CG.Band(readings, px, py)
  if not (readings and readings[1]) then return nil end
  local band = { { -huge, huge } }
  local function Cut(lo, hi) -- (keep only [lo, hi])
    local out = {}
    for _, iv in ipairs(band) do
      local a, b = max(iv[1], lo), min(iv[2], hi)
      if a <= b then out[#out + 1] = { a, b } end
    end
    band = out
  end
  local function Hole(lo, hi) -- (take out (lo, hi))
    local out = {}
    for _, iv in ipairs(band) do
      if iv[2] <= lo or iv[1] >= hi then
        out[#out + 1] = iv
      else
        if iv[1] < lo then out[#out + 1] = { iv[1], lo } end
        if iv[2] > hi then out[#out + 1] = { hi, iv[2] } end
      end
    end
    band = out
  end
  for _, rd in ipairs(readings) do
    local d = Dist(rd.x, rd.y, px, py)
    if rd.inside then
      local R2 = rd.r + CG.RANGE_SLACK + CG.WANDER_YD
      local dd = max(0, d - CG.WANDER_YD)
      if dd < R2 then
        local hz = sqrt(R2 * R2 - dd * dd)
        Cut(rd.z - hz, rd.z + hz)
      end
    else
      local dd = d + CG.WANDER_YD
      if dd < rd.r then
        local hz = sqrt(rd.r * rd.r - dd * dd)
        Hole(rd.z - hz, rd.z + hz)
      end
    end
  end
  return band
end
local function InBand(band, z, slack)
  if not band then return true end
  for _, iv in ipairs(band) do
    if z >= iv[1] - slack and z <= iv[2] + slack then return true end
  end
  return false
end
CG.InBand = InBand

-- The player's floor at (px, py) on `level`: the grid's surfaces there, those the grid walks to from the last ones
-- (CG.track.set) within the yards moved, then those in the band; one left: its height. `navZ`: the floor Nav followed
-- along the roads (the pick among several when one is near it). Nil when it can't tell.
CG.TRACK_EVERY = 0.2 -- seconds
CG.TRACK_JUMP_YD = 40 -- moved this far: from scratch
CG.TRACK_REACH = 1.5 -- the grid's way from the last surfaces may be this many times the yards moved (and two cells)
-- The floor followed is held (item 18, the coordinator 2026-11-24: Ironforge's Forge to the Hall of Thanes flipped
-- between a 100 yd and a 640 yd way as the start's floor was guessed again and again): the city's grid followed where
-- it has floors even outside the capital's outline (the Great Forge's edge: the track was dropped there, every route a
-- new guess); with the walk from the last floors finding none here, the floors near the one followed (FLOOR_Z) before
-- all of them; and of several, the one followed before.
function CG.TrackFloor(level, px, py, navZ)
  local name = CG.GridCityAt(level, px, py)
  local t = CG.track
  if not name and ns.CityGridData then
    -- (a city's grid box with its floors round the spot, SurfacesAt's as the following below: the Great Forge's edge,
    -- its own 3 yd cell bare, the hall's floor a cell off)
    for nm, d in pairs(ns.CityGridData) do
      if (d.level or d.cont) == level and px >= d.x0 and py >= d.y0 and px < d.x0 + d.w * d.cell
          and py < d.y0 + d.h * d.cell then
        local c0 = CG.City(nm)
        if c0 and (CG.SurfacesAt(c0, px, py)[1] or (t and t.name == nm and t.level == level)) then name = nm break end
      end
    end
  end
  if not name then
    CG.track = nil
    return nil
  end
  local now = GetTime()
  if t and t.name == name and t.x == px and t.y == py and now - t.at < CG.TRACK_EVERY then return t.z end
  local c = CG.City(name)
  local here = CG.SurfacesAt(c, px, py)
  if not here[1] then
    -- (no floor of the grid here, a bare stretch (round the Great Forge's pit): the floor followed held, its surfaces
    -- kept to walk on from when there are floors again)
    if t and t.name == name and (t.z or t.pick) then return t.z or t.pick end
    CG.track = { name = name, level = level, x = px, y = py, at = now, set = {}, n = 0 }
    return nil
  end
  local set = {}
  local moved = t and t.name == name and Dist(t.x, t.y, px, py)
  if moved and moved <= CG.TRACK_JUMP_YD and t.set and next(t.set) then
    -- (the grid's way from the last surfaces, within the yards moved)
    local want = {}
    for _, f in ipairs(here) do want[f.s] = f end
    local reach = moved * CG.TRACK_REACH + 2 * c.cell + 1
    local dist, open = {}, {}
    for s, ci in pairs(t.set) do dist[s] = 0 open[#open + 1] = { s, ci } end
    local qi = 1
    while open[qi] do
      local s, ci = open[qi][1], open[qi][2]
      qi = qi + 1
      if want[s] then set[s] = ci end
      local i, j = floor(ci / c.h), ci % c.h
      for d = 1, 8 do
        local kk = Link(c, s, d)
        if kk > 0 then
          local nci = (i + DX[d]) * c.h + j + DY[d]
          local s2 = First(c, nci) + kk - 1
          local nd = dist[s] + (d > 4 and c.cell * 1.4142 or c.cell)
          if nd <= reach and (not dist[s2] or nd < dist[s2]) then
            dist[s2] = nd
            open[#open + 1] = { s2, nci }
          end
        end
      end
      for _, li in ipairs(c.out[s] or {}) do
        local L = c.links[li]
        local nd = dist[s] + L.cost
        if L.bci and nd <= reach and (not dist[L.b] or nd < dist[L.b]) then
          dist[L.b] = nd
          open[#open + 1] = { L.b, L.bci }
        end
      end
      if qi > 5000 then break end
    end
  end
  local held = t and t.name == name and (t.z or t.pick) or nil
  if not next(set) and held then
    for _, f in ipairs(here) do
      if abs(Z(c, f.s) - held) <= CG.FLOOR_Z then set[f.s] = f.ci end
    end
  end
  if not next(set) then for _, f in ipairs(here) do set[f.s] = f.ci end end
  -- (the band, when there's a reading)
  local band = CG.Band(CG.Look(level, px, py), px, py)
  local inBand = {}
  for s, ci in pairs(set) do
    if InBand(band, Z(c, s), 1) then inBand[s] = ci end
  end
  if next(inBand) then set = inBand end
  local n, only = 0, nil
  for s in pairs(set) do n, only = n + 1, s end
  local z = n == 1 and Z(c, only) or nil
  local pick = z
  if not pick and held then
    local best
    for s2 in pairs(set) do
      local dz = abs(Z(c, s2) - held)
      if dz <= CG.FLOOR_Z and (not best or dz < best) then best, pick = dz, Z(c, s2) end
    end
  end
  if not pick and navZ then
    local best
    for s in pairs(set) do
      local dz = abs(Z(c, s) - navZ)
      if dz <= CG.FLOOR_Z and (not best or dz < best) then best, pick = dz, Z(c, s) end
    end
  end
  CG.track = { name = name, level = level, x = px, y = py, at = now, set = set, n = n, z = z, pick = pick, band = band,
    readings = #CG.readings }
  return z
end

-- The player's floor for a leg starting where they stand: CG.TrackFloor's, else its pick by Nav's floor.
function CG.PlayerFloorZ(level, x, y)
  local t = CG.track
  if not (t and t.level == level and Dist(t.x, t.y, x, y) <= CG.PLAYER_YD) then return nil end
  return t.z or t.pick
end

-- Nav's floor following, with the grid's: N.TrackCityZ's answer, or the grid's floor when it knows it (and Nav's
-- followed floor set to it).
function CG.HookNav()
  local N = ns.Nav
  if not N or CG.hooked or not N.TrackCityZ then return end
  CG.hooked = true
  local own = N.TrackCityZ
  N.TrackCityZ = function(level, px, py)
    local z = own(level, px, py)
    if not CG.On() or not px then return z end
    -- (on a flight: nothing followed, the Router's own rule; the grid's floor under the wind rider was the streets',
    -- kept on landing up on Orgrimmar's tower)
    if UnitOnTaxi and UnitOnTaxi("player") then return z end
    -- (a floor told (Nav.AnchorFloor: an NPC's window, the player's own) kept near where it was told)
    if N.TrackAnchored and N.TrackAnchored(level) then return z end
    local ok, gz = pcall(CG.TrackFloor, level, px, py, z)
    if ok and gz then
      if not z or abs(gz - z) > 1 then N.SetTrackForTests(level, px, py, gz) end
      CG.UpdateDebug()
      return gz
    end
    CG.UpdateDebug()
    return z
  end
end

---------------------------------------------------------------------------------------------------- testing aids
-- What the floor estimate says now: lines for /agps floor.
function CG.FloorReport()
  local x, y, cont = ns.Geo.PlayerWorld()
  local N = ns.Nav
  local level = cont and N.PlayerLevel and N.PlayerLevel(cont) or cont
  local lines = {}
  local name = CG.CityFor(level, x, y)
  if not name then
    lines[1] = "city grid: not in a city with a grid here (the six capitals)"
    return lines
  end
  local navZ = N.FollowedZ and N.FollowedZ(level)
  CG.track = nil -- (from scratch: the band and the surfaces here only)
  local readings = CG.Look(level, x, y)
  local band = CG.Band(readings, x, y)
  local c = CG.City(name)
  local here = CG.SurfacesAt(c, x, y)
  lines[#lines + 1] = string.format("city grid: %s, at %.1f, %.1f; floors here: %d", name, x, y, #here)
  for _, f in ipairs(here) do
    lines[#lines + 1] = string.format("  floor %.1f%s", f.z, InBand(band, f.z, 1) and (band and "  (in the band)" or "") or "  (out of the band)")
  end
  for _, rd in ipairs(readings) do
    lines[#lines + 1] = string.format("  %s (%s): %s %s %.1f yd, %.1f yd across, at %.1f", tostring(rd.npc), rd.unit,
      rd.src, rd.inside and "in" or "out of", rd.r, Dist(rd.x, rd.y, x, y), rd.z)
  end
  if band then
    local parts = {}
    for _, iv in ipairs(band) do parts[#parts + 1] = string.format("%.1f to %.1f", iv[1], iv[2]) end
    lines[#lines + 1] = "  band: " .. (parts[1] and table.concat(parts, ", ") or "none (the readings disagree)")
  else
    lines[#lines + 1] = "  band: no reading (target, mouse over or face an NPC that stands still nearby)"
  end
  local z = CG.TrackFloor(level, x, y, navZ)
  lines[#lines + 1] = string.format("  floor picked: %s (followed along the roads: %s)", z and string.format("%.1f", z) or "can't tell",
    navZ and string.format("%.1f", navZ) or "none")
  return lines
end

-- The small line on the map while the option is on: the floor estimate.
function CG.UpdateDebug()
  local f = _G.AzerothGPSFrame
  if not (f and f.CreateFontString) then return end
  local fs = CG.debugText
  if not fs then
    fs = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    fs:SetPoint("BOTTOMLEFT", f, "BOTTOMLEFT", 6, 6)
    CG.debugText = fs
  end
  local t = CG.track
  if not (CG.On() and t) then
    fs:SetText("")
    return
  end
  local z = t.z or t.pick
  fs:SetText(string.format("grid: %s floors %d%s, band %s", z and string.format("%.0f", z) or "?", t.n or 0,
    t.z and "" or " (guess)", t.band and (t.band[1] and string.format("%.0f-%.0f", t.band[1][1], t.band[#t.band][2]) or "x") or "-"))
end

function CG.Set(on)
  ns.settings.gps.cityGrid = on and true or false
  CG.routes, CG.order, CG.track = {}, {}, nil
  CG.stats = { grid = 0, spliced = 0, own = 0, pending = 0, searches = 0, nodes = 0, ms = 0 }
  local N = ns.Nav
  if N and N.Invalidate then N.Invalidate(true, true) end
  CG.UpdateDebug()
end

function CG.Slash(a, b)
  if a == "floor" then
    for _, line in ipairs(CG.FloorReport()) do ns.Print(line) end
    return
  end
  do -- (debug: its stats; no switch for players since item 74)
    local s = CG.stats
    ns.Print(string.format("city grid %s: legs on the grid %d, cut in at a gate %d, the Router's own %d, searched %d (%d nodes, %.0f ms), waited %d",
      CG.On() and "on" or "off", s.grid, s.spliced, s.own, s.searches, s.nodes, s.ms, s.pending))
  end
end

-- (for the world grid, WorldGrid.lua: a leg with one end in a capital)
CG.Crossing, CG.Concat = Crossing, Concat

CG.HookNav()
