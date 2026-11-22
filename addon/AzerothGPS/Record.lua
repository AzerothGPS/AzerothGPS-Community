-- The player's own road fixes, as routes use them: roads drawn or recorded and stretches erased, and walls, kept in
-- ns.db.tracks (routes use them: Router.WithTracks, Passability.WallLines). Once the addon's road data has one
-- (ns.RoadTracksIn, by its time), it moves to an archive (R.Archive): kept for good, never used. Making and changing
-- them isn't part of AzerothGPS since 1.3.14; what a player made before stays theirs and keeps routing as it did.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)
local Format = ns.Format or string.format

local R = {}
ns.Record = R

local function Tracks()
  ns.db.tracks = ns.db.tracks or {}
  return ns.db.tracks
end
R.Tracks = Tracks

-- The fixes the road data has, kept for good (asked 2026-10-06, keep data forever): ns.db.tracksShipped, each as it
-- was with its points packed (`pk`, `zk`: ns.PackNumbers), never used by routes (the data's copy is) nor by Undo.
function R.Archive()
  ns.db.tracksShipped = ns.db.tracksShipped or {}
  return ns.db.tracksShipped
end
-- A copy of track `t` with its points packed, as the archive keeps it (Core.lua's ns.PackNumbers' format).
local function Pack(list)
  if ns.PackNumbers then return ns.PackNumbers(list) end
  local out = {}
  for i, v in ipairs(list) do out[i] = v == false and "-" or tostring(v) end
  return table.concat(out, " ")
end
function R.Packed(t)
  local c = {}
  for k, v in pairs(t) do c[k] = v end
  if type(c.pts) == "table" then c.pk, c.pts = Pack(c.pts), nil end
  if type(c.zs) == "table" then c.zk, c.zs = Pack(c.zs), nil end
  return c
end

-- At login: the fixes the road data now has go to the archive (R.Archive), out of the list routes and Undo go by.
-- (They were deleted before: a stroke set aside on purpose, or drawn in the same second as a shipped one, was lost.)
function R.Prune()
  local shipped = ns.RoadTracksIn
  if not shipped or not ns.db then return end
  local n = 0
  local archive = R.Archive()
  local have = {}
  for _, a in ipairs(archive) do have[tostring(a.time) .. ":" .. tostring(a.continent) .. ":" .. tostring(a.pk)] = true end
  local function prune(list, count)
    local moved = {}
    for i = #(list or {}), 1, -1 do
      if list[i].time and shipped[list[i].time] then
        table.insert(moved, 1, table.remove(list, i))
        if count then n = n + 1 end
      end
    end
    for _, t in ipairs(moved) do
      local c = R.Packed(t)
      local key = tostring(c.time) .. ":" .. tostring(c.continent) .. ":" .. tostring(c.pk)
      if not have[key] then -- (an older version's second copy of one: once)
        have[key] = true
        archive[#archive + 1] = c
      end
    end
  end
  prune(ns.db.tracks, true)
  -- (strokes saved on a city's level though drawn elsewhere, looking at another zone from down
  -- in the city: back on the continent)
  local P = ns.Passability
  for _, t in ipairs(ns.db.tracks or {}) do
    local lvl = ns.CityLevels and ns.CityLevels[t.continent]
    if lvl and P and P.InGrid and t.pts and t.pts[1] and not P.InGrid(t.continent, t.pts[1], t.pts[2]) then
      t.continent = lvl.base
    end
  end
  -- (and the copies kept for sharing: the data has them, nothing to share)
  prune(ns.db.feedback and ns.db.feedback.roads)
  if n > 0 then ns.Print(L["%d of your drawn roads and walls are in the map data now (kept in your saved data)"]:format(n)) end
end

-- Tracks changed: the walls at once, and the road network (it includes them) and the route rebuilt, after every
-- edit, the road and wall tools on or not (asked 2026-11-11: "make the route update immediately after a road or wall
-- is drawn, not after the tool is turned off"; until then the network waited for the tools to be turned off). The
-- network is rebuilt in the background; the map shows the edits over the roads as they were meanwhile (GPSFrame's
-- LayoutRoads).
function R.Changed()
  if ns.Passability and ns.Passability.RefreshWalls then ns.Passability.RefreshWalls() end
  if ns.GPS and ns.GPS.ClearEdges then ns.GPS.ClearEdges() end
  R.Apply()
end

-- The edits into the road network and the route.
function R.Apply()
  R.pending = nil
  if ns.Router and ns.Router.Reset then ns.Router.Reset() end
  if ns.Nav and ns.Nav.Invalidate then ns.Nav.Invalidate(true, true) end
  if ns.GPS and ns.GPS.Redraw then ns.GPS.Redraw() end
end
