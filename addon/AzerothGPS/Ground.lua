-- The ground's height from the map's own data (1.3.10, issue #685). The game gives addons no height (UnitPosition's z
-- is always 0), so the road and wall tools take it from the terrain baked offline (Data/Heights.lua, `agps heights`):
-- per map tile a grid of whole yards every ns.Heights.cell yards, each tile one string (app/azerothgps/heights.py),
-- decoded here a tile at a time and only while the road or wall tools are open (GD.Active). Drawn roads start with it
-- (GD.RoadHeights), the tools show it at the pointer ("Ground: 123 yd"), and a cliff wall's sides are filled from it.
-- Terrain only: none over a hole (a cave's or a cellar's way down), none in a building or a cave for a drawn road.
local _, ns = ...
local GD = {}
ns.Ground = GD

local TILE = 1600 / 3
GD.CACHE_TILES = 24 -- tiles kept decoded (each about 4,000 numbers); the oldest goes first
-- (the characters, as heights.py's ALPHABET: '#' .. '~' but '\', each one's number its place)
local SMALL, NONE, NONE_RUN, ZERO_RUN, BIG = 40, 81, 82, 83, 84
local BASE = 91
local BIG_OFF = math.floor(BASE * BASE / 2)
local INDEX = {}
do
  local k = 0
  for c = 35, 126 do
    if c ~= 92 then
      INDEX[c] = k
      k = k + 1
    end
  end
end

-- The prediction for value k (0-based, row-major in rows of n) of grid `g` (false: none): as heights.py's _predict.
local function Predict(g, k, n, last)
  local i, j = math.floor(k / n), k % n
  local left = j > 0 and g[k] or false -- (g is 1-based: value k is g[k + 1], its left g[k])
  local up = i > 0 and g[k - n + 1] or false
  local ul = (i > 0 and j > 0) and g[k - n] or false
  if left and up and ul then return left + up - ul end
  if left then return left end
  if up then return up end
  return last or 0
end

-- A string from heights.py's encode as its grid: n * n values, row-major, 1-based (false: none); nil if malformed.
function GD.Decode(s, n)
  local g, k, last, pos, len = {}, 0, nil, 1, #s
  local byte = string.byte
  while pos <= len do
    local c = INDEX[byte(s, pos)]
    if not c then return nil end
    pos = pos + 1
    if c == NONE then
      k = k + 1
      g[k] = false
    elseif c == NONE_RUN or c == ZERO_RUN then
      local run = (INDEX[byte(s, pos) or 0] or 0) + 2
      pos = pos + 1
      for _ = 1, run do
        if c == NONE_RUN then
          g[k + 1] = false
        else
          local v = Predict(g, k, n, last)
          g[k + 1], last = v, v
        end
        k = k + 1
      end
    else
      local d
      if c == BIG then
        local a, b = INDEX[byte(s, pos) or 0], INDEX[byte(s, pos + 1) or 0]
        if not (a and b) then return nil end
        d = a * BASE + b - BIG_OFF
        pos = pos + 2
      else
        d = c - SMALL
      end
      local v = Predict(g, k, n, last) + d
      g[k + 1], last = v, v
      k = k + 1
    end
  end
  if k ~= n * n then return nil end
  return g
end

-- Whether the grid may be read now: the road or wall tools open (GD.force: the tests).
function GD.Active()
  if GD.force then return true end
  local G = ns.GPS
  return G and (G.roadMode or G.wallMode) and true or false
end

local cache, order = {}, {} -- [cont .. ":" .. key .. ":" .. water] = grid; the keys oldest first
function GD.Release()
  cache, order = {}, {}
end
GD.decoded = 0 -- (tiles decoded so far: the tests)
local function TileGrid(cont, key, water)
  local H = ns.Heights
  local list = H and (water and H.water and H.water[cont] or not water and H[cont])
  local s = list and list[key]
  if not s then return nil end
  local ck = cont .. ":" .. key .. (water and ":w" or "")
  local g = cache[ck]
  if g ~= nil then return g end
  g = GD.Decode(s, H.n + 1) or false
  GD.decoded = GD.decoded + 1
  cache[ck] = g
  order[#order + 1] = ck
  if #order > GD.CACHE_TILES then
    cache[table.remove(order, 1)] = nil
  end
  return g
end

-- The baked height at (x, y) of continent `cont`: bilinear between the grid's four values round it; nil off the map,
-- over a hole, with no data or the tools closed. `water`: the water's surface there instead (nil where there's none).
function GD.At(cont, x, y, water)
  local H = ns.Heights
  if not (H and H.n and x and y and GD.Active()) then return nil end
  local n = H.n
  local tx, ty = math.floor(32 - y / TILE), math.floor(32 - x / TILE)
  if tx < 0 or tx > 63 or ty < 0 or ty > 63 then return nil end
  local g = TileGrid(cont, tx * 64 + ty, water)
  if not g then return nil end
  local q = TILE / n
  local fi, fj = ((32 - ty) * TILE - x) / q, ((32 - tx) * TILE - y) / q
  local i, j = math.min(math.floor(fi), n - 1), math.min(math.floor(fj), n - 1)
  local u, v = fi - i, fj - j
  local w = n + 1
  local a, b, c, d = g[i * w + j + 1], g[(i + 1) * w + j + 1], g[i * w + j + 2], g[(i + 1) * w + j + 2]
  if not (a and b and c and d) then return nil end
  return a * (1 - u) * (1 - v) + b * u * (1 - v) + c * (1 - u) * v + d * u * v
end

-- The ground's height for a drawn road's point at (x, y) of `level`: the grid's, rounded to a tenth; in a building
-- being edited on its inside map, its floor's (G.BuildingFloorZ); false in another building or a cave (the import works
-- those out) or where the grid has none.
function GD.PointHeight(level, x, y)
  local N, G = ns.Nav, ns.GPS
  -- (in a building whose inside map is being edited, 1.3.10: its floor's height there, Data/InteriorFloors.lua)
  local fz = G and G.BuildingFloorZ and G.BuildingFloorZ(x, y)
  if fz then return math.floor(fz * 10 + 0.5) / 10 end
  if N and N.InBuilding and N.InBuilding(level, x, y) then return false end
  if G and G.CaveAt and G.CaveAt(level, x, y) then return false end
  local h = GD.At(level, x, y)
  return h and math.floor(h * 10 + 0.5) / 10 or false
end

-- A drawn road's ground heights, a point each (GD.PointHeight): nil when none has one.
function GD.RoadHeights(level, pts)
  if not (ns.Heights and ns.Heights[level]) then return nil end
  local out, any = {}, false
  for k = 1, #pts - 1, 2 do
    local h = GD.PointHeight(level, pts[k], pts[k + 1])
    out[#out + 1] = h
    any = any or h ~= false
  end
  return any and out or nil
end
