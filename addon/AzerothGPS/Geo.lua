-- World geometry. World coordinates are yards: X points north, Y points west
-- (the order UnitPosition returns). See docs/coordinates.md.
local _, ns = ...

local Geo = {}
ns.Geo = Geo

Geo.TILE = 1600 / 3 -- yards per terrain tile; 64x64 tiles per continent

-- A simulated player for route testing (asked 2026-10-06; set by private dev tools, and by AzerothGPS only for the
-- tutorial's spell-jump demo while its step shows (Tutorial.lua's T.JumpDemoStart); never saved: a /reload or logout
-- ends it). While set, `Geo.override` = { x, y, cont (as UnitPosition
-- gives it: an underground city's base continent, a dungeon's MapID), level (an underground city's level, or nil),
-- facing, moving, indoors } stands in for where the player is: the map, the arrow, routing, directions and arrivals
-- go by it. What learns from where the player really stands (herbs and ore, NPCs, the trips shared, pins' notes,
-- transports and dungeon entrances) reads the game's own (Geo.RealPlayerWorld) or waits, and companions (the public
-- API) are given the game's own.
Geo.override = nil
function Geo.SetOverride(o)
  Geo.override = o
  if ns.Nav and ns.Nav.ForgetLevel then ns.Nav.ForgetLevel() end
end
function Geo.Simulated() return Geo.override ~= nil end

-- Player position: world X, Y, continent (instance) ID and height Z; nil in instances.
function Geo.RealPlayerWorld()
  local ok, x, y, z, inst = pcall(UnitPosition, "player")
  if not ok or not x or ns.IsSecret(x) or ns.IsSecret(y) then return nil end
  return x, y, inst, z or 0
end
function Geo.PlayerWorld()
  local o = Geo.override
  if o then return o.x, o.y, o.cont, o.z or 0 end
  return Geo.RealPlayerWorld()
end

-- Facing in radians, counter-clockwise from north (0 when unavailable).
function Geo.RealFacing()
  local ok, f = pcall(GetPlayerFacing)
  if ok and f and not ns.IsSecret(f) then return f end
  return 0
end
function Geo.Facing()
  local o = Geo.override
  if o and o.facing then return o.facing end
  return Geo.RealFacing()
end

-- The player's map (uiMapID): the game's, or the zone or city where the simulated player is (GPS.LocateWorld).
function Geo.PlayerMap()
  local o = Geo.override
  if o then
    if o.mapX ~= o.x or o.mapY ~= o.y then
      o.mapX, o.mapY = o.x, o.y
      o.map = ns.GPS and ns.GPS.LocateWorld and (ns.GPS.LocateWorld(o.cont, o.x, o.y)) or nil
    end
    return o.map
  end
  return C_Map and C_Map.GetBestMapForUnit and C_Map.GetBestMapForUnit("player")
end

-- World (X, Y) -> fractional terrain tile (tx east, ty south).
function Geo.WorldToTile(x, y)
  return 32 - y / Geo.TILE, 32 - x / Geo.TILE
end

-- Offset of world point (x, y) from the player, in screen yards: +right = east, +up = north.
function Geo.ScreenOffset(px, py, x, y)
  return py - y, x - px
end

-- Rotate (dx, dy) counter-clockwise by angle a.
function Geo.Rotate(dx, dy, a)
  local c, s = math.cos(a), math.sin(a)
  return dx * c - dy * s, dx * s + dy * c
end

-- The world map (Azeroth) shows both continents on one image; each continent's region
-- maps to its own rectangle of it (Data/Maps.lua worldFrames).
function Geo.WorldMap()
  if Geo.worldMapID == nil then
    Geo.worldMapID = false
    for id, m in pairs(ns.Maps or {}) do
      if m.worldFrames then Geo.worldMapID = id end
    end
  end
  return Geo.worldMapID or nil
end

-- Bounds {minX, minY, maxX, maxY} of the whole world map image, expressed in continent
-- `cont`'s world coordinates (extrapolated beyond that continent).
function Geo.WorldArtBounds(cont)
  local id = Geo.WorldMap()
  local wf = id and ns.Maps[id].worldFrames[cont]
  if not wf then return nil end
  local ky = (wf[4] - wf[2]) / (wf[7] - wf[5]) -- yards of Y per unit of u (east-west)
  local kx = (wf[3] - wf[1]) / (wf[8] - wf[6]) -- yards of X per unit of v (north-south)
  local maxY = wf[4] + wf[5] * ky
  local maxX = wf[3] + wf[6] * kx
  return { maxX - kx, maxY - ky, maxX, maxY }
end

-- World position (x, y) on continent `from` -> the matching point in continent `to`'s
-- coordinates, via the world map (for drawing routes across the sea).
-- City levels (Data/Cities.lua): an underground city routes as its own level, a
-- pseudo-continent that is drawn in its base continent's coordinates.
function Geo.Base(cont)
  local l = ns.CityLevels and ns.CityLevels[cont]
  return l and l.base or cont
end

-- The continent (or city level) of uiMap `mapID`: an underground city's map gives its level.
function Geo.MapCont(mapID)
  for id, l in pairs(ns.CityLevels or {}) do
    if l.map == mapID then return id end
  end
  local m = ns.Maps and ns.Maps[mapID]
  return m and m.continent
end

-- A map not on the world map's art but shown as an inset on it (Zephras Isle: GPSFrame's
-- WORLD_INSETS): the spot's place in the inset's rectangle, as world map fractions (u east, v
-- south), or nil.
local function InsetFraction(cont, x, y)
  for _, it in ipairs(ns.GPS and ns.GPS.WORLD_INSETS or {}) do
    local m = ns.Maps and ns.Maps[it.map]
    local b = m and m.continent == cont and m.bounds
    if b then
      local u = (b[4] - y) / (b[4] - b[2])
      local v = (b[3] - x) / (b[3] - b[1])
      return it.u0 + u * (it.u1 - it.u0), it.v0 + v * (it.v1 - it.v0)
    end
  end
end

-- ... and back: world map fractions (u, v) to the isle's own coordinates (where they'd be if its inset's
-- scale went on past its frame: a spot on another continent, far off its edge that way), or nil.
local function FromInsetFraction(cont, u, v)
  for _, it in ipairs(ns.GPS and ns.GPS.WORLD_INSETS or {}) do
    local m = ns.Maps and ns.Maps[it.map]
    local b = m and m.continent == cont and m.bounds
    if b and it.u1 ~= it.u0 and it.v1 ~= it.v0 then
      local iu, iv = (u - it.u0) / (it.u1 - it.u0), (v - it.v0) / (it.v1 - it.v0)
      return b[3] - iv * (b[3] - b[1]), b[4] - iu * (b[4] - b[2])
    end
  end
end

-- Where world spot (x, y) on continent `cont` is on the world map's art, as fractions (u east, v south); an isle
-- shown as an inset there, where it's drawn. Nil when it's on neither. (The search orders what's on another
-- continent by it: GPSFrame's G.SearchPlacesPlain.)
function Geo.WorldFraction(cont, x, y)
  cont = Geo.Base(cont)
  local a = Geo.WorldArtBounds(cont)
  if a then return (a[4] - y) / (a[4] - a[2]), (a[3] - x) / (a[3] - a[1]) end
  return InsetFraction(cont, x, y) -- (an isle shown as an inset on the world map: where it's drawn there)
end

-- `into`: into an isle's coordinates too (by its inset; Geo.IntoAny), else nil there (the public API's
-- ToContinent: nil, as its callers expect).
local function ToContinent(from, x, y, to, into)
  from, to = Geo.Base(from), Geo.Base(to)
  if from == to then return x, y end
  local b = Geo.WorldArtBounds(to)
  if not b and not into then return nil end
  local u, v = Geo.WorldFraction(from, x, y)
  if not u then return nil end
  if not b then return FromInsetFraction(to, u, v) end
  return b[3] - v * (b[3] - b[1]), b[4] - u * (b[4] - b[2])
end
function Geo.ToContinent(from, x, y, to) return ToContinent(from, x, y, to) end
-- ... and into an isle shown as an inset too (a ride to it from another continent drawn: the zeppelin to
-- Zephras Isle had no line, 2026-10-01).
function Geo.IntoAny(from, x, y, to) return ToContinent(from, x, y, to, true) end
