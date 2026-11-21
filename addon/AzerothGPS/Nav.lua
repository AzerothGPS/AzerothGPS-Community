-- Navigation state: stops, current route (via Router), distance and ETAs.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)
local Format = ns.Format or string.format
local Geo = ns.Geo
local unpack = unpack or table.unpack

local N = {}
ns.Nav = N

local DEFAULT_RUN = 7 -- yd/s, normal run speed
local ARRIVED_YD = 10
local REROUTE_SECONDS = 2 -- at most this often while moving (option rerouteSeconds, Performance)
local REROUTE_MOVED_YD = 15 -- ...and only after moving this far (scaled with it)
local REROUTE_STALE = 30 -- standing still: refresh this often anyway
local OFF_ROUTE_YD = 30 -- further than this from the route: recalculate it
-- A terrain search from the player's position finished: the route is recalculated to use
-- it, but at most this often: each recalculation starts searches from the new position,
-- and recalculating on each of those would loop (a recalculation a few times a second).
local SEARCH_RECALC_SECONDS = 3 -- (scaled with rerouteSeconds too)
-- How often a route off the player's way is recalculated (Options > Performance): seconds, and the
-- yards moved and seconds between recalculations for finished searches, scaled with it.
function N.RerouteTiming()
  local st = ns.settings and ns.settings.gps
  local secs = math.max(REROUTE_SECONDS, st and st.rerouteSeconds or REROUTE_SECONDS)
  local k = secs / REROUTE_SECONDS
  return secs, REROUTE_MOVED_YD * k, SEARCH_RECALC_SECONDS * k
end
local searchDirty, searchRecalcAt = false, -math.huge
local FOLLOW_MAX_AGE = 20 -- following the route: recalculate this often anyway
-- The walked part behind the player is trimmed off as they go (every TRIM_MOVED_YD), apart
-- from recalculations (at most every REROUTE_SECONDS and REROUTE_MOVED_YD): the route shrinks
-- behind them smoothly instead of in jumps. Only the next TRIM_AHEAD_YD of it is searched.
N.TRIM_MOVED_YD = 2
N.TRAM_MAP = 369 -- the Deeprun Tram's own map (Data/Transports.lua: its ride)
N.TRIM_AHEAD_YD = 120
-- A recalculation that comes out clearly longer while the player is still on the current
-- route (e.g. a terrain search near an obstacle hasn't finished yet) keeps the current
-- route: while the new one is provisional, or for up to KEEP_SECONDS if it's final.
local LONGER_SHARE, LONGER_YD = 1.1, 30 -- "clearly longer": more than 10% and 30 yd
local KEEP_SECONDS = 20

N.stops = {} -- { { x, y, cont, name, icon }, ... } in visiting order
N.dest = nil -- the next stop (N.stops[1])
N.route = nil -- Router result from the player's position at routeX/routeY
N.arrivedAt = nil
N.MAX_STOPS = 100 -- a trip's stops (imported lists, /way, placed)
N.PLAN_AHEAD = 8 -- stops routed and drawn ahead at most (option stopsAhead, default 3); the next comes in as each is reached
N.MAX_LOOP_STOPS = 60 -- a farming loop (nodes circled on the map)
N.LOOP_AHEAD = 4 -- a loop routes this many stops ahead (it goes round and round)
N.loop = false -- the stops are a loop: reaching one moves it to the end
-- The stops go in the order listed, never reordered (an import with "Route in the listed order", gps.importKeepOrder:
-- the fastest order, its reorders on the way and a quest area's stop brought forward all left out; a stop added later
-- goes at the end). Saved with the stops.
N.keepOrder = false
-- (each stop of such a trip carries it too, `listed`: saved with it, so the order holds whatever reaches the stops)
function N.ListedOrder()
  if N.keepOrder then return true end
  for _, d in ipairs(N.stops) do
    if d.listed then return true end
  end
  return false
end
N.ICON = "Interface\\TargetingFrame\\UI-RaidTargetingIcon_%d"
-- Marker for the k-th stop placed (raid icon numbers): square, star, triangle, diamond,
-- moon, circle. Cross and skull aren't used: after the six, the markers start over.
N.MARKER_ORDER = { 6, 1, 4, 3, 5, 2 }
function N.MarkerFor(k) return N.MARKER_ORDER[(k - 1) % #N.MARKER_ORDER + 1] end

-- The first marker (in MARKER_ORDER) that none of the given stop lists uses yet.
function N.NextMarker(...)
  local used = {}
  for _, list in ipairs({ ... }) do
    for _, d in ipairs(list) do if d.icon then used[d.icon] = true end end
  end
  local count = 0
  for _, list in ipairs({ ... }) do count = count + #list end
  if count < #N.MARKER_ORDER then
    for _, m in ipairs(N.MARKER_ORDER) do
      if not used[m] then return m end
    end
  end
  return N.MarkerFor(count + 1) -- all six in use: start over
end
-- Route color per marker (star, circle, diamond, triangle, moon, square, cross, skull),
-- for trips with several stops: each leg in the color of the stop it leads to.
N.MARKER_COLORS = {
  { 1, 0.85, 0.1 }, { 1, 0.5, 0.05 }, { 0.75, 0.3, 1 }, { 0.25, 0.85, 0.25 },
  { 0.65, 0.8, 1 }, { 0.15, 0.5, 1 }, { 1, 0.2, 0.15 }, { 0.92, 0.92, 0.92 },
}
-- (their names, as the dungeon map's color picker shows them: GPS.DUNGEON_PATH_COLORS)
N.MARKER_COLOR_NAMES = { L["Yellow"], L["Orange"], L["Purple"], L["Green"], L["Light Blue"], L["Blue"], L["Red"],
  L["White"] }
-- (and their ids, the saved `dungeonPathColor`: the same in every language)
N.MARKER_COLOR_KEYS = { "yellow", "orange", "purple", "green", "lightblue", "blue", "red", "white" }
local version = 0 -- bumped when the stops change (cache key for the stretches between stops)

local function Copy(d)
  -- (a stop with no height of its own at an NPC's spot: that NPC's, N.SpawnZ. Not a guide's: theirs is looked up their
  -- own way, the guides' shipped waypoint heights first, RestedXP.lua's X.HeightXY; nor a corpse's)
  local z = d.z
  if z == nil and not (d.corpse or d.rxp or d.zygor or d.polestar or d.questify or d.apr) and N.SpawnZ then
    z = N.SpawnZ(d.cont, d.x, d.y)
  end
  return { x = d.x, y = d.y, cont = d.cont, name = d.name, icon = d.icon, corpse = d.corpse, questRoute = d.questRoute,
    tex = d.tex, boss = d.boss, enc = d.enc, z = z, quest = d.quest, turnin = d.turnin,
    parts = d.parts, partAt = d.partAt, -- (a quest area in parts, Layers.QuestAreaSpots: the one chosen, OrderStops)
    rxp = d.rxp, -- (a RestedXP step's: its key, RestedXP.lua)
    zygor = d.zygor, -- (a Zygor step's: its key, Zygor.lua)
    polestar = d.polestar, -- (a Polestar step's: its key, Polestar.lua)
    questify = d.questify, -- (a Questify step's: its key, Questify.lua)
    apr = d.apr, -- (an Azeroth Pilot Reloaded step's: its key, AzerothPilot.lua)
    questie = d.questie, -- (Questie's "Set TomTom Target", Import.QuestieTarget)
    listed = d.listed } -- (a trip in its listed order's, N.keepOrder)
end

-- The stops are saved per character, so /reload and relogging keep the route.
local function Save()
  local cdb = ns.CharDB and ns.db and ns.CharDB()
  if not cdb then return end
  local list = {}
  for i, d in ipairs(N.stops) do list[i] = Copy(d) end
  cdb.stops = #list > 0 and list or nil
  cdb.loop = (N.loop and #list > 1) or nil
  cdb.keepOrder = (N.keepOrder and #list > 0) or nil
  cdb.paused = (#list > 0 and N.paused) or nil -- (routing paused: kept over a /reload, N.SetPaused)
  cdb.dest = nil -- older single-destination save
  -- (the zones too high the player said yes to for this route: not asked again after a /reload)
  local ok = {}
  for z in pairs(N.redOk or {}) do ok[#ok + 1] = z end
  cdb.redOk = (#list > 0 and #ok > 0) and ok or nil
  -- (and the "risk it?" answers for its stops: asked once for the route, a /reload too; asked 2026-11-16, "On a single
  -- route this should only be asked once and remembered while that route is active")
  local risk = {}
  for k, v in pairs(N.riskOk or {}) do risk[k] = v end
  cdb.riskOk = (#list > 0 and next(risk)) and risk or nil
  N.SaveQuestChoices(cdb) -- (the quests kept or left out: with or without a route, N.questDropped)
  local skip = {}
  for node in pairs(N.skipLearn or {}) do skip[#skip + 1] = node end
  cdb.skipLearn = (#list > 0 and #skip > 0) and skip or nil
  local rides = {}
  for key in pairs(N.skipRides or {}) do rides[#rides + 1] = key end
  cdb.skipRides = (#list > 0 and #rides > 0) and rides or nil
  cdb.noSwim = (#list > 0 and N.noSwim) or nil -- (a swim removed from this trip: N.SkipSwim)
  cdb.swimBans = (#list > 0 and N.noSwim and N.swimBans and #N.swimBans > 0) and N.swimBans or nil -- (its water)
  -- (the other faction's towns said in chat for this trip, N.CheckHostileRoute: not said again after a /reload)
  local towns = {}
  for name in pairs(N.hostileSaid or {}) do towns[#towns + 1] = name end
  cdb.hostileSaid = (#list > 0 and #towns > 0) and towns or nil
end
N.SaveStops = Save

local function Changed()
  N.dest = N.stops[1]
  N.route, N.arrivedAt = nil, nil
  version = version + 1
  N.freshAt = GetTime and GetTime() or nil
  N.ResetStutter() -- (another trip: routed in full again; its later stretches are new)
  Save()
end
-- A route just asked for (the stops changed FRESH_SECONDS ago or less): its background searches get the warm-up's
-- bigger slices (GPS.PumpBudget), not the 1 ms a frame of a route being kept up. At 1 ms, from Lakeshire's town hall
-- to Darkshire the walk across country (about 1.5 s of searching) took 13 s and more to land, and the long way by the
-- roads showed meanwhile (QA v116-ov-a, 2026-10-07: about 20 s in game).
-- Settled before that (N.Checking: shown with no work left for CHECK_QUIET), it's a route being kept up: the
-- recalculations as the player walks off it get the 1 ms again (issue #316: walking a long off-road leg just after
-- asking for it, the warm-up's slices ran on every frame).
N.FRESH_SECONDS = 20
local settledAt -- (the stops' version settled: N.Checking)
function N.Fresh()
  return N.freshAt ~= nil and N.dest ~= nil and settledAt ~= version and GetTime() - N.freshAt < N.FRESH_SECONDS
end

-- A route through `stops` ({ x, y, cont, name?, icon? } each) in the given order, or in
-- the fastest order from the player's position when `fastest` is set.
-- Stops down in a city stay in the order they were placed (option, on by default): the
-- way through a city from one to the next is what the player means.
-- Whether stop `d` keeps the place it was given (option cityKeepOrder): down in a city, placed
-- by hand (the quest route button's stops are always put in the fastest order, in cities too).
function N.CityKept(d)
  local gps = ns.settings and ns.settings.gps
  if not gps or gps.cityKeepOrder == false or not ns.CityLevels then return false end
  return d.cont and ns.CityLevels[d.cont] and not d.questRoute and true or false
end

-- The stops aren't reordered at all: every one down in a city, in the order placed. With some
-- outside the city, the fastest order, the city's still in their order among themselves
-- (N.OrderStops): how you go round a city is up to you, not where the rest of the trip goes.
function N.KeepCityOrder()
  if #N.stops == 0 then return false end
  for _, d in ipairs(N.stops) do
    if not N.CityKept(d) then return false end
  end
  return true
end

-- In a dungeon or raid with the dungeon route on (option `dungeonRoute`) and its boss route
-- set: other routes wait (the quest route, stops added on the map, shared routes) until it's
-- done or turned off. `force`: the boss route itself.
function N.DungeonLocked()
  local gps = ns.settings and ns.settings.gps
  if not gps or gps.dungeonRoute == false then return false end
  local lvl = N.CurrentInstance and N.CurrentInstance()
  if not lvl then return false end
  for _, d in ipairs(N.stops) do
    if d.boss and d.cont == lvl then return true end
  end
  return false
end

local lockSaidAt = -100
function N.SayLocked()
  local now = GetTime and GetTime() or 0
  if now - lockSaidAt < 5 then return end
  lockSaidAt = now
  ns.Print(L["In a dungeon the dungeon route is on: other routes wait until its bosses are down. Turn it off in the map menu (Dungeon route) or with /agps dungeonroute."])
end

local function Locked(force)
  if force or not N.DungeonLocked() then return false end
  N.SayLocked()
  return true
end

-- Stops in zones too high for the player (red on the map; option avoidHighZones): { { zone
-- name, lowest level, highest }, ... } (each zone once), or nil. Not the zone the player is in.
function N.RedStops(list)
  local R = ns.Router
  local red = R and R.RedZones and R.RedZones()
  if not red then return nil end
  local px, py, pc = Geo.PlayerWorld()
  local here = px and R.ZoneAt(Geo.Base(pc), px, py)
  local out, seen = {}, {}
  for _, d in ipairs(list) do
    local z = d.x and R.ZoneAt(Geo.Base(d.cont), d.x, d.y)
    if z and red[z] and z ~= here and not seen[z] then
      seen[z] = true
      local lo, hi = R.ZoneLevels(z)
      local m = ns.Maps and ns.Maps[z]
      out[#out + 1] = { m and m.name or "?", lo, hi, z = z }
    end
  end
  return out[1] and out or nil
end

-- A route to stops in a zone too high for the player: asked first (GPSFrame's popup), and
-- `again` (setting them, confirmed) run on yes. True while asking.
local function AskRed(list, again)
  -- (the trip's zones too high already said yes to, or all of them: not asked again, N.redOk)
  if N.redOk.all then return false end
  local zones = {}
  for _, z in ipairs(N.RedStops(list) or {}) do
    if not N.redOk[z.z] then zones[#zones + 1] = z end
  end
  if not zones[1] or not (ns.GPS and ns.GPS.ConfirmRedZone) then return false end
  return ns.GPS.ConfirmRedZone(zones, list, function()
    for _, z in ipairs(zones) do N.redOk[z.z] = true end -- (asked: not again for passing through)
    -- (nor about the other zones too high the route walks through on its way: one popup a trip, asked 2026-11-14:
    -- "when routing through multiple higher level zones, just ask in 1 popup")
    N.redOk.all = true
    again()
  end)
end

-- A route walking through a zone too high for the player (the way round there isn't, for
-- their faction): asked once per zone per route, like a stop in one. Rides (boats, flights)
-- over one don't count, nor the zones the route starts and ends in.
N.RED_ROUTE_YD = 60 -- walked this far in one: asked
-- Asked once a trip (asked 2026-11-18, a trip of many stops asking at each one: "they should only be asked once in a
-- multi stop route"): Yes to "Keep this route?" is `all`, every zone too high on the rest of the trip's legs, and No in
-- a trip of several stops is `no`, the trip kept (the planner goes round them wherever there's a way, as always) and
-- not asked again. Saved with the stops (a /reload); a new trip (N.SameTrip) starts with none.
N.redOk = {} -- zones the player said yes to, for this route (and `all`, `no`)
function N.RedOnRoute(r, px, py, cont)
  local R = ns.Router
  local red = R and R.RedZones and R.RedZones()
  if not (red and r and r.parts) or N.redOk.all or N.redOk.no then return nil end
  local exempt = { [R.ZoneAt(Geo.Base(cont), px, py)] = true }
  for _, d in ipairs(N.stops) do exempt[R.ZoneAt(Geo.Base(d.cont), d.x, d.y)] = true end
  local yards = {}
  for _, part in ipairs(r.parts) do
    local c, pts = Geo.Base(part.cont), part.pts
    for i = 1, #pts - 3, 2 do
      if part.kinds[(i + 1) / 2] ~= N.KIND_TRANSPORT then
        for z, yd in pairs(R.ZoneYards(c, pts[i], pts[i + 1], pts[i + 2], pts[i + 3])) do
          if red[z] and not exempt[z] and not N.redOk[z] then yards[z] = (yards[z] or 0) + yd end
        end
      end
    end
  end
  local out = {}
  for z, yd in pairs(yards) do
    if yd >= N.RED_ROUTE_YD then
      local lo, hi = R.ZoneLevels(z)
      local m = ns.Maps and ns.Maps[z]
      out[#out + 1] = { m and m.name or "?", lo, hi, z = z, yards = yd }
    end
  end
  table.sort(out, function(a, b) return a.yards > b.yards end)
  return out[1] and out or nil
end

-- The other faction's territory on the route: their guards' reach (Data/Hostile.lua, Router.HostileAt). Asked
-- 2026-11-14, a Horde player's route through Dun Algaz past the Alliance's guards: "If we have to force a player
-- through opposing faction area we should warn them and that part of the route should be red ... Also if they have
-- that setting turned off for avoiding it should still show red for that area." So by the player's own faction
-- (N.Faction), whether "Avoid the other faction's towns" is on or off (Router.HostileSide is nil when it's off), and
-- on the walks only (a flight or a boat over them isn't in their reach; kinds as Router's: road, off the road, a drop).
N.HOSTILE_COLOR = { 1, 0.15, 0.15 }
N.HOSTILE_WALK_KINDS = { [0] = true, [1] = true, [4] = true }
N.HOSTILE_WARN_YD = 20 -- walked this far past one town's guards: in the warning
N.HOSTILE_NAME_YD = 800 -- a town's name: the nearest town or place label this near its guards, else the zone's
local hostileSpans = setmetatable({}, { __mode = "k" }) -- [part] = { side = , [i] = spans or false }
-- The stretches of route part `part`'s piece i (its points i and i + 1) within their reach: { t1, t2, t1, t2, ... }
-- (0 to 1 along the piece), or false. Sampled every Router.HOSTILE_STEP yards, as the router weighs them; each piece
-- worked out once, when it's first drawn.
function N.HostileSpans(part, i)
  local side, R = N.Faction and N.Faction(), ns.Router
  if not (side and part and part.pts and R and R.HostileAt and ns.Hostile and ns.Hostile[part.cont]) then return false end
  local memo = hostileSpans[part]
  if not memo or memo.side ~= side then
    memo = { side = side }
    hostileSpans[part] = memo
  end
  local v = memo[i]
  if v ~= nil then return v end
  v = false
  local pts, k = part.pts, part.kinds and part.kinds[i]
  local x1, y1, x2, y2 = pts[2 * i - 1], pts[2 * i], pts[2 * i + 1], pts[2 * i + 2]
  if x2 and N.HOSTILE_WALK_KINDS[k or 0] then
    local n = math.max(1, math.ceil(math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2) / R.HOSTILE_STEP))
    for s = 0, n - 1 do
      local t = (s + 0.5) / n
      if R.HostileAt(part.cont, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, side) then
        v = v or {}
        local m = #v
        if m > 0 and v[m] == s / n then v[m] = (s + 1) / n else v[m + 1], v[m + 2] = s / n, (s + 1) / n end
      end
    end
  end
  memo[i] = v
  return v
end
-- Pieces of a route piece for drawing it: fn(t1, t2, hostile) for each stretch from 0 to 1, in order (`spans` as
-- N.HostileSpans').
function N.EachHostilePiece(spans, fn)
  local t = 0
  for j = 1, #spans - 1, 2 do
    if spans[j] > t then fn(t, spans[j], false) end
    fn(spans[j], spans[j + 1], true)
    t = spans[j + 1]
  end
  if t < 1 then fn(t, 1, false) end
end

-- Swims on the route (asked for 1.3.10): the walks' stretches off the roads over water to swim (Passability.WaterSpans,
-- the terrain grid's water; the deep sea far out is closed). Drawn as a wavy line on both maps and the minimap, timed
-- at the game's swim speed (N.TripSecs), and removable from the trip (right-click: N.SkipSwim). Shorter than
-- SWIM_MIN_YD on a piece: a stream waded, not counted.
N.SWIM_MIN_YD = 10
N.SWIM_SPEED = 4.72 -- yd/s, the game's base swim speed (GetUnitSpeed's fourth value once seen: N.SwimSpeed)
local swimSpans = setmetatable({}, { __mode = "k" }) -- [part] = { [i] = spans or false }
-- The stretches of route part `part`'s piece i that are swum: { t1, t2, ... } (0 to 1 along the piece), or false.
function N.SwimSpans(part, i)
  local P, R = ns.Passability, ns.Router
  if not (part and part.pts and P and P.WaterSpans and R) then return false end
  local memo = swimSpans[part]
  if not memo then
    memo = {}
    swimSpans[part] = memo
  end
  local v = memo[i]
  if v ~= nil then return v end
  v = false
  local pts, k = part.pts, part.kinds and part.kinds[i]
  local x1, y1, x2, y2 = pts[2 * i - 1], pts[2 * i], pts[2 * i + 1], pts[2 * i + 2]
  if x2 and k == R.KIND_OFFROAD then
    local wet = P.WaterSpans(part.cont, x1, y1, x2, y2)
    if wet then
      local len = math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)
      for j = 1, #wet - 1, 2 do
        if (wet[j + 1] - wet[j]) * len >= N.SWIM_MIN_YD then
          v = v or {}
          v[#v + 1], v[#v + 2] = wet[j], wet[j + 1]
        end
      end
    end
  end
  memo[i] = v
  return v
end
-- Pieces of a route piece for drawing it: fn(t1, t2, hostile, swim) for each stretch from 0 to 1, in order: the other
-- faction's guards' reach (N.HostileSpans) and the swims (N.SwimSpans) cut it alike.
local function InSpans(list, t)
  if not list then return false end
  for j = 1, #list - 1, 2 do
    if t >= list[j] and t <= list[j + 1] then return true end
  end
  return false
end
function N.EachRoutePiece(part, i, fn)
  local h = N.HostileSpans(part, i)
  local w = N.SwimSpans(part, i)
  if not h and not w then return fn(0, 1, false, false) end
  local cuts, seen = { 0, 1 }, { [0] = true, [1] = true }
  for _, list in ipairs({ h or {}, w or {} }) do
    for _, t in ipairs(list) do
      if not seen[t] then cuts[#cuts + 1], seen[t] = t, true end
    end
  end
  table.sort(cuts)
  for k = 1, #cuts - 1 do
    local a, b = cuts[k], cuts[k + 1]
    if b > a then
      local m = (a + b) / 2
      fn(a, b, InSpans(h, m), InSpans(w, m))
    end
  end
end
-- The yards swum along `part`: all of it, or before its piece i at t along it (from its start).
local swimAlong = setmetatable({}, { __mode = "k" }) -- [part] = { cumulative yards swum before each piece }
local function SwimCum(part)
  local cum = swimAlong[part]
  if cum then return cum end
  cum = { 0 }
  local pts = part.pts or {}
  local R = ns.Router
  for i = 1, #pts / 2 - 1 do
    if R and R.Breathe then R.Breathe(i, 50) end -- (in a background job: a pause along a long walk)
    local w, yd = N.SwimSpans(part, i), 0
    if w then
      local len = math.sqrt((pts[2 * i + 1] - pts[2 * i - 1]) ^ 2 + (pts[2 * i + 2] - pts[2 * i]) ^ 2)
      for j = 1, #w - 1, 2 do yd = yd + (w[j + 1] - w[j]) * len end
    end
    cum[i + 1] = cum[i] + yd
  end
  swimAlong[part] = cum
  return cum
end
function N.SwimYards(part, i, t)
  if not (part and part.pts) then return 0 end
  local cum = SwimCum(part)
  if not i then return cum[#cum] end
  local before = cum[i] or cum[#cum]
  local w = t and t > 0 and cum[i] and N.SwimSpans(part, i)
  if w then
    local pts = part.pts
    local len = math.sqrt((pts[2 * i + 1] - pts[2 * i - 1]) ^ 2 + (pts[2 * i + 2] - pts[2 * i]) ^ 2)
    for j = 1, #w - 1, 2 do
      if t > w[j] then before = before + (math.min(t, w[j + 1]) - w[j]) * len end
    end
  end
  return before
end
-- The yards swum on a stretch's walks (its parts; a ride's has no piece off the roads).
function N.StretchSwim(st)
  if not st then return 0 end
  if st.swimYd then return st.swimYd end
  local yd = 0
  for _, p in ipairs(st.parts or {}) do yd = yd + N.SwimYards(p) end
  st.swimYd = yd
  return yd
end
-- The route's swims: r.swimYards to the next stop, r.totalSwim to the last one planned (from its stretches).
local function SetSwim(r)
  local yd, total = 0, 0
  for i, st in pairs(r.stretches or {}) do
    if type(i) == "number" and st then
      local s = N.StretchSwim(st)
      if i == 1 then yd = s end
      total = total + s
    end
  end
  r.swimYards, r.totalSwim = yd, total
end
N.SetSwim = SetSwim

-- A walk's steps split by what's done along it (asked for 1.3.10: "Walk 2.6k yd" over a coast's swims read as one walk):
-- "Walk 800 yd", "Swim 1.2k yd", "Walk 600 yd", each timed at its own speed. A piece under SWIM_STEP_MIN_YD is folded
-- into its neighbors (a bit of land between two swims: one swim; a puddle on a walk: the walk), the smallest first, so
-- the list doesn't flicker into many steps.
N.SWIM_STEP_MIN_YD = 40
local swimRuns = setmetatable({}, { __mode = "k" }) -- [part] = { runs, length }
-- Route part `part`'s swims as yards along it: { s0, s1, ... } (swims across a corner joined), and its length.
function N.SwimRuns(part)
  local v = swimRuns[part]
  if v then return v[1], v[2] end
  local runs, acc, pts = {}, 0, part and part.pts or {}
  for i = 1, #pts / 2 - 1 do
    local len = math.sqrt((pts[2 * i + 1] - pts[2 * i - 1]) ^ 2 + (pts[2 * i + 2] - pts[2 * i]) ^ 2)
    local w = N.SwimSpans(part, i)
    for j = 1, w and #w - 1 or 0, 2 do
      local s0, s1 = acc + w[j] * len, acc + w[j + 1] * len
      if #runs > 0 and s0 - runs[#runs] < 0.01 then runs[#runs] = s1 else runs[#runs + 1], runs[#runs + 2] = s0, s1 end
    end
    acc = acc + len
  end
  swimRuns[part] = { runs, acc }
  return runs, acc
end
-- The stretch from `a` to `b` yards along a walk with swims `runs` (N.SwimRuns) as pieces, in order:
-- { s0, s1, swim = true or false, sw = yards swum in it }, folded (SWIM_STEP_MIN_YD).
function N.SwimPieces(runs, a, b)
  local pieces = {}
  local function add(s0, s1, swim)
    if s1 <= s0 then return end
    local last = pieces[#pieces]
    if last and last.swim == swim then
      last.s1, last.sw = s1, last.sw + (swim and s1 - s0 or 0)
    else
      pieces[#pieces + 1] = { s0 = s0, s1 = s1, swim = swim, sw = swim and s1 - s0 or 0 }
    end
  end
  local t = a
  for j = 1, #runs - 1, 2 do
    local s0, s1 = math.max(runs[j], t), math.min(runs[j + 1], b)
    if s1 > s0 then
      add(t, s0, false)
      add(s0, s1, true)
      t = s1
    end
  end
  add(t, b, false)
  while #pieces > 1 do
    local k, least
    for j, p in ipairs(pieces) do
      local yd = p.s1 - p.s0
      if yd < N.SWIM_STEP_MIN_YD and (not least or yd < least) then k, least = j, yd end
    end
    if not k then break end
    local p, prev, nxt = pieces[k], pieces[k - 1], pieces[k + 1]
    if prev and nxt then -- (between two of the other kind: the three one)
      prev.s1, prev.sw = nxt.s1, prev.sw + p.sw + nxt.sw
      table.remove(pieces, k + 1)
    elseif prev then
      prev.s1, prev.sw = p.s1, prev.sw + p.sw
    else
      nxt.s0, nxt.sw = p.s0, nxt.sw + p.sw
    end
    table.remove(pieces, k)
  end
  return pieces
end
-- Walk leg `leg` of stretch `st` (its part: the one with that leg), `done` yards of it walked, as pieces in yards from
-- where the player is (adding up to leg.yards - done), or nil when none of it is swum.
function N.LegPieces(st, leg, done)
  local part
  for _, p in ipairs(st and st.parts or {}) do
    if p.leg == leg then part = p break end
  end
  if not part then return nil end
  local runs, len = N.SwimRuns(part)
  if #runs == 0 or len <= 0 then return nil end
  done = math.min(done or 0, len)
  local yards = math.max(0, (leg.yards or len) - done)
  local pieces = N.SwimPieces(runs, done, len)
  local any = false
  for _, p in ipairs(pieces) do
    if p.swim then any = true end
  end
  if not any then return nil end
  local k = len - done > 0 and yards / (len - done) or 0 -- (the leg's yards as the router counted them)
  for _, p in ipairs(pieces) do
    p.s0, p.s1, p.sw = (p.s0 - done) * k, (p.s1 - done) * k, p.sw * k
    p.yd = p.s1 - p.s0
  end
  return pieces
end

-- What makes water as fast as land for this character (asked for 1.3.10): water walking or levitation on, castable or
-- in the bags, or Aquatic Form (a druid swims about as fast as running in it). What the addon can read: the auras
-- (N.AuraOn), the spells known (IsPlayerSpell / IsSpellKnown) and the bags (GetItemCount). A spell with a reagent counts
-- only with the reagent in the bags (asked 2026-11-19; the client's SpellReagents: Water Walking takes a Fish Oil,
-- Levitate a Light Feather, Aquatic Form none). Items: the client's on-use items whose spell walks on water (ItemEffect,
-- aura 104), the Elixir of Water Walking first; `aura`: walking on water while it's on (cast by another, a quest's).
-- { spell, item, reagent, count, name, icon, active } or nil; the auras checked at most every second, the spells and
-- bags every 10 s, and at once (at most every WATER_RECHECK s) when the bags or spells change (N.WaterChanged).
N.WATER_FAST = {
  { spell = 546, reagent = 17058, reagentName = "Fish Oil" }, -- Water Walking (shaman)
  { spell = 1706, reagent = 17056, reagentName = "Light Feather" }, -- Levitate (priest)
  { spell = 1066 },  -- Aquatic Form (druid)
  { spell = 11319, item = 8827 }, -- Elixir of Water Walking
  { spell = 1299351, item = 276274 }, -- (WoW Forever's own water walking items)
  { spell = 461120, item = 227923 },
  { spell = 1265304, item = 259890 },
  { spell = 10665, aura = true }, { spell = 27986, aura = true }, { spell = 461329, aura = true },
  { spell = 1221095, aura = true }, { spell = 1270422, aura = true }, { spell = 1310296, aura = true },
}
local function ItemNameOf(id)
  local ok, n = pcall(function()
    return (C_Item and C_Item.GetItemNameByID and C_Item.GetItemNameByID(id)) or (GetItemInfo and GetItemInfo(id))
  end)
  return ok and type(n) == "string" and n ~= "" and n or nil
end
local function ItemCountOf(id)
  local count = (C_Item and C_Item.GetItemCount) or GetItemCount
  if not count then return 0 end
  local ok, n = pcall(count, id)
  if not ok or type(n) ~= "number" or (ns.IsSecret and ns.IsSecret(n)) then return 0 end
  return n
end
local waterHave, waterHaveAt, waterNow, waterNowAt
function N.WaterFast()
  local now = GetTime()
  if waterNowAt and now - waterNowAt < 1 and now >= waterNowAt then return waterNow or nil end
  if not waterHaveAt or now - waterHaveAt >= 10 or now < waterHaveAt then
    waterHave, waterHaveAt = {}, now
    for _, w in ipairs(N.WATER_FAST) do
      local have = false
      w.count = nil
      if w.aura then
        have = false
      elseif w.item then
        local n = ItemCountOf(w.item)
        have, w.count = n > 0, n
      else
        have = N.KnownSpell(w.spell) and true or false
        if have and w.reagent then
          local n = ItemCountOf(w.reagent)
          have, w.count = n > 0, n
        end
      end
      if have then waterHave[#waterHave + 1] = w end
    end
  end
  local best, on
  for _, w in ipairs(N.WATER_FAST) do
    if N.AuraOn(w.spell) then best, on = w, true break end
  end
  best = best or waterHave[1]
  if best then
    best.active = on or false
    local name = (best.item and ItemNameOf(best.item)) or (ns.SpellName and ns.SpellName(best.spell)) or L["Water walking"]
    -- (a spell with its reagent: how many are left, "Water Walking (Fish Oil: 5)")
    if best.reagent and best.count and not on then
      name = string.format("%s (%s: %d)", name, ItemNameOf(best.reagent) or best.reagentName, math.floor(best.count))
    end
    best.name = name
    best.icon = (ns.SpellIcon and ns.SpellIcon(best.spell)) or best.icon
  end
  waterNow, waterNowAt = best or false, now
  return best
end
function N.ForgetWaterFast() waterHaveAt, waterNowAt = nil, nil end -- (the tests: checked again at once)
-- The bags or the spells known changed (BAG_UPDATE, SPELLS_CHANGED): looked at again, at most every WATER_RECHECK s,
-- and the routes worked out again when water's speed for them changed (N.SyncSwim): a Fish Oil used up or bought.
N.WATER_RECHECK = 2
local waterCheckedAt, waterDirty = -math.huge, false
function N.WaterChanged()
  local now = GetTime()
  if now - waterCheckedAt < N.WATER_RECHECK and now >= waterCheckedAt then
    if not waterDirty and C_Timer and C_Timer.After then
      C_Timer.After(N.WATER_RECHECK, function() if waterDirty then N.WaterChanged() end end)
    end
    waterDirty = true
    return false
  end
  waterCheckedAt, waterDirty = now, false
  N.ForgetWaterFast()
  return N.SyncSwim()
end
-- Seconds for `yards` on foot (`swim` of them swum) and `ride` seconds of rides at `speed` (walking, mounted, the
-- player's now): the swum yards at the swim speed (a mount is left at the water's edge), unless water's as fast
-- as land for them (N.WaterFast).
function N.TripSecs(yards, swim, ride, speed)
  yards = yards or 0
  speed = math.max(speed or DEFAULT_RUN, 0.1)
  swim = math.max(0, math.min(swim or 0, yards))
  local secs = (yards - swim) / speed + (ride or 0)
  if swim > 0 then secs = secs + swim / ((N.WaterFast() and speed) or math.min(speed, N.SwimSpeed())) end
  return secs
end

-- Swimming left out of routes: the option off (Options > Routing, "Allow swimming"), or a swim removed from this trip
-- (N.SkipSwim); Passability weighs water dearly then (P.avoidSwim). Checked at each route worked out.
function N.SwimAllowed()
  local st = ns.settings and ns.settings.gps
  return not (st and st.allowSwim == false) and not N.noSwim
end
function N.SyncSwim()
  local P = ns.Passability
  if not (P and P.SetAvoidSwim) then return false end
  local changed = P.SetAvoidSwim(not N.SwimAllowed())
  -- (water as fast as land, N.WaterFast: priced as land, a hair over; swimming left out still goes round)
  if waterDirty and GetTime() - waterCheckedAt >= N.WATER_RECHECK then
    waterCheckedAt, waterDirty = GetTime(), false
    N.ForgetWaterFast()
  end
  if P.SetWaterFast and P.SetWaterFast(N.WaterFast() ~= nil) then changed = true end
  if P.SetSwimBans and P.SetSwimBans(N.ActiveSwimBans()) then changed = true end
  if not changed then return false end
  if ns.Router and ns.Router.WallsChanged then ns.Router.WallsChanged() end -- (the walks worked out again)
  N.Invalidate(true, true)
  return true
end
-- A swim right-clicked on the map, "Remove?": this trip goes round by land wherever there's a way, rerouting and after
-- a /reload (saved with the stops); a new trip swims again. Its water (the bay, the lake: Passability.SwimSection) is
-- banned for the trip, as a wall is (asked 2026-11-19: "ignored for the remainder of the time that route is active",
-- not merely dearer: weighed 10 times a yard, a swim along the coast in the same water came back), N.swimBans; each
-- swim removed adds its own. Water costs AVOID_SWIM_COST a yard elsewhere too (N.noSwim, P.avoidSwim). `cont`, `pts`:
-- the swim's points (N.SwimStretch); none, every swim on the route.
N.noSwim = nil
N.swimBans = {}
function N.ActiveSwimBans()
  local out = {}
  for _, b in ipairs(N.noSwim and N.swimBans or {}) do
    if not b.lifted then out[#out + 1] = b end
  end
  return out
end
-- The removed swim's water (N.swimBans) that (x, y) on `cont` is in (`liftedOnly`: one swum after all), or nil.
function N.InSwimBan(cont, x, y, liftedOnly)
  local P = ns.Passability
  for _, b in ipairs(N.noSwim and N.swimBans or {}) do
    if (b.lifted or not liftedOnly) and P.InSwimSection(b, cont, x, y) then return b end
  end
  return nil
end
function N.SkipSwim(cont, pts)
  local P = ns.Passability
  local list = {}
  if cont and pts then
    list[1] = { cont, pts }
  else -- (every swim on the route)
    for _, part in pairs(N.route and N.route.parts or {}) do
      for i = 1, #(part.pts or {}) / 2 - 1 do
        local sp = N.SwimSpans(part, i)
        for j = 1, sp and #sp - 1 or 0, 2 do
          local c, swim = N.SwimStretch(part, i, sp[j], sp[j + 1])
          if c then list[#list + 1] = { c, swim } end
        end
      end
    end
  end
  N.noSwim = true
  for _, e in ipairs(list) do
    local c, swim = e[1], e[2]
    local mx, my = (swim[1] + swim[#swim - 1]) / 2, (swim[2] + swim[#swim]) / 2
    -- (a swim in water banned already, lifted or the same bay's: nothing more)
    if not N.InSwimBan(c, swim[1], swim[2]) and not N.InSwimBan(c, mx, my) then
      local sec = P and P.SwimSection and P.SwimSection(c, swim)
      if sec then N.swimBans[#N.swimBans + 1] = sec end
    end
  end
  N.SaveStops()
  N.SyncSwim()
end
-- The whole swim through route part `part`'s piece i from t1 to t2 (0 to 1 along it): on through the pieces before
-- and after while it's in the water. The part's continent and a flat point list, or nil.
function N.SwimStretch(part, i, t1, t2)
  local pts = part and part.pts
  if not (pts and pts[2 * i + 2]) then return nil end
  local function At(k, t)
    local x1, y1, x2, y2 = pts[2 * k - 1], pts[2 * k], pts[2 * k + 1], pts[2 * k + 2]
    return x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
  end
  local ax, ay = At(i, t1)
  local out = { ax, ay }
  local k, t = i, t1
  while t <= 1e-6 and k > 1 do -- (back while the piece before ends in the water)
    local sp = N.SwimSpans(part, k - 1)
    if not (sp and sp[#sp] >= 1 - 1e-6) then break end
    k, t = k - 1, sp[#sp - 1]
    local x, y = At(k, t)
    table.insert(out, 1, y)
    table.insert(out, 1, x)
  end
  local bx, by = At(i, t2)
  out[#out + 1], out[#out + 2] = bx, by
  k, t = i, t2
  while t >= 1 - 1e-6 and pts[2 * k + 4] do -- (on while the piece after starts in it)
    local sp = N.SwimSpans(part, k + 1)
    if not (sp and sp[1] <= 1e-6) then break end
    k, t = k + 1, sp[2]
    local x, y = At(k, t)
    out[#out + 1], out[#out + 2] = x, y
  end
  return part.cont, out
end
-- A walk with no way at all with that water banned (an isle in the bay, or a stop cut off by it): the bans near its
-- ends (within SWIM_LIFT_YD of their water's box), else every one on its continent, lifted for the trip: that water is
-- swum (at AVOID_SWIM_COST), and its swims say "No way round by land: this swim stays." (N.SwimStays). Whether any was.
N.SWIM_LIFT_YD = 300
function N.LiftSwimBans(cont, x1, y1, x2, y2)
  local P = ns.Passability
  local near, same = {}, {}
  for _, b in ipairs(N.ActiveSwimBans()) do
    if b.cont == cont then
      same[#same + 1] = b
      local bx0, bx1, by0, by1 = P.SwimSectionBox(b)
      local m = N.SWIM_LIFT_YD
      for _, e in ipairs({ { x1, y1 }, { x2, y2 } }) do
        if bx0 and e[1] and e[1] >= bx0 - m and e[1] <= bx1 + m and e[2] >= by0 - m and e[2] <= by1 + m then
          near[#near + 1] = b
          break
        end
      end
    end
  end
  local lift = #near > 0 and near or same
  if #lift == 0 then return false end
  for _, b in ipairs(lift) do b.lifted = true end
  N.SaveStops()
  N.SyncSwim()
  return true
end
-- Yards of route `r`'s pieces off the roads (on `cont`) straight over banned water (N.ActiveSwimBans): a hop over it
-- (Router's `blocked`), no walk round found.
function N.SwimBanYards(cont, r)
  local P, R = ns.Passability, ns.Router
  if not (r and r.pts and r.kinds and P and R and N.noSwim and #N.swimBans > 0) then return 0 end
  local yd, pts = 0, r.pts
  for i, k in ipairs(r.kinds) do
    local x1, y1, x2, y2 = pts[2 * i - 1], pts[2 * i], pts[2 * i + 1], pts[2 * i + 2]
    if x2 and k == R.KIND_OFFROAD then
      local len = math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)
      local n = math.max(1, math.ceil(len / 6))
      for j = 0, n - 1 do
        local t = (j + 0.5) / n
        local x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        if P.At(cont, x, y) == 2 and N.InSwimBan(cont, x, y) and not N.InSwimBan(cont, x, y, true) then
          yd = yd + len / n
        end
      end
    end
  end
  return yd
end
-- Whether the swim at (x, y) on `cont` is one kept because there's no way round by land (N.LiftSwimBans).
function N.SwimStays(cont, x, y)
  return N.InSwimBan(cont, x, y, true) ~= nil
end

-- A name for where a town's guard stands (continent `c`, x, y): the nearest town (Data/Pois.lua kind 2), else place
-- label (kind 3), within HOSTILE_NAME_YD; else its zone's name; else nil.
local function GuardPlace(c, x, y)
  for _, kind in ipairs({ 2, 3 }) do
    local best, bd = nil, N.HOSTILE_NAME_YD ^ 2
    for _, p in ipairs(ns.Pois and ns.Pois[c] or {}) do
      if p[1] == kind and p[4] then
        local d = (p[2] - x) ^ 2 + (p[3] - y) ^ 2
        if d < bd then best, bd = p, d end
      end
    end
    if best then return ns.PoiName(best) end
  end
  local R = ns.Router
  local z = R and R.ZoneAt and R.ZoneAt(c, x, y)
  local m = z and ns.Maps and ns.Maps[z]
  return m and ns.ZoneName(z, m.name) or nil
end
-- The other faction's towns the route walks through: { { name, yards }, ... } most first, or nil. Not the towns at a
-- walk's own ends (a stop in one, the player in one: R.HostileTownsNear, as the router leaves them out).
function N.HostileOnRoute(r)
  local side, R = N.Faction and N.Faction(), ns.Router
  if not (side and r and r.parts and R and R.HostileYards and R.HostileTownsNear and ns.Hostile) then return nil end
  local yards, at = {}, {}
  for _, part in ipairs(r.parts) do
    local c, pts, kinds = part.cont, part.pts, part.kinds
    local list = ns.Hostile[c] and ns.Hostile[c][side]
    local n = pts and #pts or 0
    if list and kinds and n >= 4 then
      local exempt = R.HostileTownsNear(c, side, pts[1], pts[2], pts[n - 1], pts[n])
      for i = 1, n - 3, 2 do
        if R.Breathe then R.Breathe((i + 1) / 2, 50) end -- (in a background job: a pause along a long route)
        if N.HOSTILE_WALK_KINDS[kinds[(i + 1) / 2] or 0] then
          local acc = {}
          if R.HostileYards(c, pts[i], pts[i + 1], pts[i + 2], pts[i + 3], side, exempt, acc) > 0 then
            for t, yd in pairs(acc) do
              local key = c .. ":" .. t
              yards[key] = (yards[key] or 0) + yd
              at[key] = at[key] or { c, list[t], list[t + 1] }
            end
          end
        end
      end
    end
  end
  local out, seen = {}, {}
  for key, yd in pairs(yards) do
    if yd >= N.HOSTILE_WARN_YD then
      local a = at[key]
      local name = GuardPlace(a[1], a[2], a[3]) or "?"
      if seen[name] then
        seen[name][2] = seen[name][2] + yd
      else
        seen[name] = { name, yd }
        out[#out + 1] = seen[name]
      end
    end
  end
  table.sort(out, function(a, b) return a[2] > b[2] end)
  return out[1] and out or nil
end
-- Looked for once a route (its stops, the option, the faction), when it's settled (not while its searches or the ride
-- check run: a walk through Dun Algaz shown first, the flight round it after): a line in the directions panel while the
-- route lasts (N.HostileNote), and a chat line once a trip for each town (N.hostileSaid, saved with the stops: issue
-- #652, said again at every stop reached, death, pause and resume, /reload, the same stops set again; Kooki3z saw it
-- over and over on a trip through Dun Algaz). Looked for in the background (Router.Background: the whole route sampled
-- every few yards, not in a frame).
N.hostileSaid = {} -- [town's name] = said in chat this trip
local hostileChecked, hostileNames
local hostileNoteRoute, hostileNoteHas -- (N.HostileNote: the route it was looked for on, and whether it passes guards)
function N.CheckHostileRoute()
  local r, d = N.route, N.dest
  if not (r and d) or d.corpse or r.pending or (N.Checking and N.Checking()) then return end
  local R = ns.Router
  -- (avoiding them, unless the player said to risk it: N.riskOk)
  local avoiding = R and R.HostileSide and R.HostileSide() ~= nil and not (d and N.RiskAnswer(d))
  local key = version .. ":" .. tostring(N.Faction and N.Faction()) .. ":" .. tostring(avoiding)
  if hostileChecked == key then return end
  hostileChecked, hostileNames = key, nil
  local function Said(towns)
    if hostileChecked ~= key or not towns then return end -- (the route changed meanwhile, or none)
    local names = {}
    for k, t in ipairs(towns) do
      if k <= 3 then names[k] = t[1] end
    end
    hostileNames = table.concat(names, ", ")
    local new = false
    for _, name in ipairs(names) do
      if not N.hostileSaid[name] then new, N.hostileSaid[name] = true, true end
    end
    if not new then return end -- (all said already this trip: the directions and the map still show it)
    Save()
    if ns.Print then
      ns.Print(Format(avoiding and L["|cffff4040Enemy territory:|r no way round it found, the route passes the other faction's guards at %s (red on the map)."]
        or L["|cffff4040Enemy territory:|r the route passes the other faction's guards at %s (red on the map)."], hostileNames))
    end
  end
  if R and R.Background then
    R.Background("hostile:" .. key, function() return N.HostileOnRoute(r) or false end, Said)
  else
    Said(N.HostileOnRoute(r))
  end
end
-- The directions panel's line for it, or nil.
function N.HostileNote()
  if not (hostileNames and N.route and N.dest) then return nil end
  local R = ns.Router
  local d = N.dest
  local key = version .. ":" .. tostring(N.Faction and N.Faction()) .. ":"
    .. tostring(R and R.HostileSide and R.HostileSide() ~= nil and not (d and N.RiskAnswer(d)))
  if hostileChecked ~= key then return nil end
  -- (the route said it of can have been worked out again since, the stops the same: a route after a /reload that
  -- went through Southshore, then the hearthstone's round it, still said "Through enemy territory: Southshore", asked
  -- 2026-11-14. Said only while the route shown passes the guards: N.HostileSpans, the map's red, per route)
  local r = N.route
  if hostileNoteRoute ~= r then
    hostileNoteRoute, hostileNoteHas = r, false
    for _, part in ipairs(r.parts or {}) do
      local n = part.pts and #part.pts or 0
      for i = 1, n / 2 - 1 do
        if N.HostileSpans(part, i) then hostileNoteHas = true break end
      end
      if hostileNoteHas then break end
    end
  end
  if not hostileNoteHas then return nil end
  return Format(L["|cffff4040Through enemy territory: %s|r"], hostileNames)
end

-- Whether `stops` set as the route go on with the trip on now (its answers kept: N.redOk, the trip's "risk it?"): the
-- same stops again (a quest route's update, a reorder), or several stops with one of the trip's among them (stops
-- added to it, an import added to it, the quest route made again). Not a new single stop, nor a list of others (a new
-- import), nor anything after the route was cleared.
function N.SameTrip(stops)
  if #N.stops == 0 or #(stops or {}) == 0 then return false end
  local same = #stops == #N.stops
  for i, d in ipairs(stops) do
    local o = N.stops[i]
    same = same and o and d.x and N.RiskKey(d) == N.RiskKey(o)
  end
  if same then return true end
  if #stops < 2 then return false end
  local have = {}
  for _, o in ipairs(N.stops) do have[N.RiskKey(o)] = true end
  for _, d in ipairs(stops) do
    if d.x and have[N.RiskKey(d)] then return true end
  end
  return false
end
-- Counts trips (a new one set, the route cleared): a question about one, answered after another was set, does nothing.
N.trip = 0

function N.SetStops(stops, fastest, force, keep)
  if Locked(force) then return false end
  if not N.SameTrip(stops) then -- (another trip: its towns said again, N.CheckHostileRoute; it swims again, N.SkipSwim)
    N.hostileSaid, N.noSwim, N.swimBans = {}, nil, {}
  end
  if force ~= "red" then
    -- (the "risk it?" answers kept for the stops still in it: the same route set again, a quest route's update, a
    -- reorder, isn't asked again; a new stop is)
    local keep = {}
    for _, d in ipairs(stops or {}) do
      local k = d and d.x and N.RiskKey(d)
      if k and N.riskOk and N.riskOk[k] ~= nil then keep[k] = N.riskOk[k] end
    end
    -- (the same trip: the zones too high said yes to stay as well, and its "risk it?" answer, asked once a trip)
    local same = N.SameTrip(stops)
    if same and N.riskOk then keep.trip = N.riskOk.trip end
    if not same then N.trip = N.trip + 1 end
    local red = same and N.redOk or {}
    N.redOk, N.skipLearn, N.noWalk, N.walkKept, N.riskOk, N.riskQuestion, N.riskAsking = red, {}, {}, {}, keep, nil, nil
    N.ClearSkippedRides()
  end -- (a new route: its zones asked about again, its detours and rides back)
  -- ("red": asked and confirmed; true: the dungeon route, its own)
  if not force and AskRed(stops, function() N.SetStops(stops, fastest, "red", keep) end) then return false, true end
  -- (a new route, "red" too (asked and confirmed): routed again, not paused; the same stops set again keep it)
  if N.paused then
    local same = #(stops or {}) == #N.stops
    for i, d in ipairs(stops or {}) do
      local o = N.stops[i]
      same = same and o and d.x and N.RiskKey(d) == N.RiskKey(o)
    end
    if not same then
      N.paused = nil
      N.PauseShown() -- (the Pause button's glow and the square's Resume button gone with it)
    end
  end
  N.pauseWatch = nil
  N.stops, N.loop, N.keepOrder = {}, false, keep and true or false
  for i, d in ipairs(stops) do
    if i > N.MAX_STOPS then break end
    local c = Copy(d)
    c.icon = c.icon or N.MarkerFor(i)
    c.listed = N.keepOrder or nil
    N.stops[#N.stops + 1] = c
  end
  Changed()
  if fastest and not N.keepOrder and #N.stops > 1 and not N.KeepCityOrder() then N.OrderStops() end
  return true
end

-- Add a stop at the end of the route (then reorder if `fastest`).
function N.AddStop(d, fastest, force)
  if Locked(force) then return false end
  if not force and AskRed({ d }, function() N.AddStop(d, fastest, "red") end) then return false, true end
  if #N.stops >= (N.loop and N.MAX_LOOP_STOPS or N.MAX_STOPS) then return false end
  if #N.stops == 0 then N.keepOrder = false end -- (a new route: the last one's listed order is over)
  local c = Copy(d)
  c.icon = c.icon or N.NextMarker(N.stops)
  c.listed = N.keepOrder or nil
  N.stops[#N.stops + 1] = c
  Changed()
  -- (a route kept in its listed order: the new stop stays at the end)
  if fastest and not N.loop and not N.keepOrder and #N.stops > 1 and not N.KeepCityOrder() then N.OrderStops() end
  return true
end

-- Put a stop in at place `at` (1: the next one; RestedXP.lua's step). Not asked about zones too high (a guide's step).
function N.InsertStop(d, at, force)
  if Locked(force) then return false end
  if #N.stops >= N.MAX_STOPS then return false end
  local c = Copy(d)
  c.icon = c.icon or N.NextMarker(N.stops)
  table.insert(N.stops, math.max(1, math.min(at or 1, #N.stops + 1)), c)
  Changed()
  return true
end

-- Order for a loop through points { x, y } starting nearest (px, py): nearest-next, then
-- 2-opt on the closed loop (straight distances: the points are close together, one area).
function N.LoopOrder(pts, px, py)
  local n = #pts
  if n < 2 then return { 1 } end
  local function d(a, b) return math.sqrt((a.x - b.x) ^ 2 + (a.y - b.y) ^ 2) end
  local used, order = {}, {}
  local cur = { x = px, y = py }
  for k = 1, n do
    local best, bd
    for i = 1, n do
      if not used[i] then
        local di = d(cur, pts[i])
        if not bd or di < bd then best, bd = i, di end
      end
    end
    used[best], order[k], cur = true, best, pts[best]
  end
  local function len(o)
    local t = 0
    for k = 1, n do t = t + d(pts[o[k]], pts[o[k % n + 1]]) end
    return t
  end
  local improved, bestLen, rounds = true, len(order), 0
  while improved and rounds < 50 do
    improved, rounds = false, rounds + 1
    for a = 1, n - 1 do
      for b = a + 1, n do
        local o = {}
        for k = 1, n do o[k] = order[k] end
        for k = 0, math.floor((b - a) / 2) do o[a + k], o[b - k] = o[b - k], o[a + k] end
        local l = len(o)
        if l < bestLen - 1e-6 then order, bestLen, improved = o, l, true end
      end
    end
  end
  -- (the shortening reverses stretches of the loop, its first stop with them: Kooki3z, 2026-11-19, a loop round
  -- Hillsbrad's Headland started ~1k yd away with nodes all round. The loop the same length from any of its stops: it
  -- starts again at the one nearest the player, going the way whose next stop is nearer)
  local k0, bd = 1, nil
  local here = { x = px, y = py }
  for k = 1, n do
    local dk = d(here, pts[order[k]])
    if not bd or dk < bd then k0, bd = k, dk end
  end
  local fwd = d(pts[order[k0]], pts[order[k0 % n + 1]]) <= d(pts[order[k0]], pts[order[(k0 - 2) % n + 1]])
  local out = {}
  for j = 0, n - 1 do
    out[j + 1] = order[fwd and ((k0 - 1 + j) % n + 1) or ((k0 - 1 - j) % n + 1)]
  end
  return out
end

-- A farming loop through `nodes` ({ x, y, cont, name }): visited round and round, each
-- reached one moving to the end. Starts at the node nearest the player. More than MAX_LOOP_STOPS: the nearest that
-- many, looped (the first MAX_LOOP_STOPS of a loop through all of them went anywhere in the area and jumped back).
function N.SetLoop(nodes, px, py)
  if Locked() then return false end
  px, py = px or nodes[1].x, py or nodes[1].y
  if #nodes > N.MAX_LOOP_STOPS then
    local near = {}
    for i = 1, #nodes do near[i] = nodes[i] end
    local function d2(a) return (a.x - px) ^ 2 + (a.y - py) ^ 2 end
    table.sort(near, function(a, b) return d2(a) < d2(b) end)
    nodes = {}
    for i = 1, N.MAX_LOOP_STOPS do nodes[i] = near[i] end
  end
  local order = N.LoopOrder(nodes, px, py)
  N.stops = {}
  for k, i in ipairs(order) do
    local c = Copy(nodes[i])
    c.icon = N.MarkerFor(k)
    N.stops[k] = c
  end
  N.loop, N.keepOrder = #N.stops > 1, false
  Changed()
end

-- How many stops the route is worked out through (and drawn): a few ahead. A long list
-- (an imported guide) is routed PLAN_AHEAD stops at a time; reaching one brings in the next.
function N.PlannedStops()
  if N.loop then return math.min(#N.stops, 1 + N.LOOP_AHEAD) end
  local st = ns.settings and ns.settings.gps
  local ahead = math.max(1, math.min(N.PLAN_AHEAD, math.floor(tonumber(st and st.stopsAhead) or 3)))
  return math.min(#N.stops, ahead)
end

-- A stop's icon: its own (a city location's, say), else its marker.
function N.StopIcon(d)
  return d.tex or N.ICON:format(d.icon or 1)
end

-- Whether the route is a quest route (the Sprint button): a stop made for a quest is left.
function N.OnQuestRoute()
  for _, d in ipairs(N.stops) do
    if d.questRoute then return true end
  end
  return false
end

-- The quest route's stops the player removed (asked 2026-11-12: "Remember the quest stops they've dropped from the
-- route"): { quest, turnin, name }, left out when the quest route is made again (GPS.SetQuestRoute, by N.QuestDropped).
-- Since 1.3.13 (players' request relayed by Kooki3z 2026-11-21: "when a quest is excluded via the popup, it comes up
-- again every time the route regenerates") they stay out of every later quest route, not just this run's: saved per
-- character with or without a route, kept over a /reload, a new route and the route cleared, until the player puts
-- the quest back (N.PutBackQuest: the directions' Put Back, Options > Routing > Quest Route's Put Back All) or the
-- quest leaves the log (N.ForgetQuest). A stop is matched by its quest and part (objectives or turn-in), not where it
-- is: a quest's spot moves on as its objectives are done (its next one), and a removed stop matched by place (40 yd,
-- till 1.3.12) came back there. The group quests left out on the popup are GPS.groupChoice's, saved the same way.
N.questDropped = {}
function N.QuestDropped(d)
  if not (d and d.quest) then return false end
  for _, e in ipairs(N.questDropped or {}) do
    if e.quest == d.quest and (e.turnin or false) == (d.turnin or false) then return true end
  end
  return false
end
-- The group quests' choices (GPS.groupChoice: questID -> "keep" or "leave") and the stops removed (N.questDropped)
-- saved per character (CharDB `groupChoice`, `questDropped`; the same keys as before 1.3.13, when they were kept with
-- the route only).
function N.SaveQuestChoices(cdb)
  cdb = cdb or (ns.CharDB and ns.db and ns.CharDB())
  if not cdb then return end
  local group = {}
  for id, v in pairs(ns.GPS and ns.GPS.groupChoice or {}) do
    if v == "keep" or v == "leave" then group[id] = v end
  end
  cdb.groupChoice = next(group) and group or nil
  local dropped = {}
  for _, e in ipairs(N.questDropped or {}) do
    dropped[#dropped + 1] = { quest = e.quest, turnin = e.turnin or nil, name = e.name }
  end
  cdb.questDropped = #dropped > 0 and dropped or nil
end
function N.RestoreQuestChoices(cdb)
  N.questDropped = {}
  for _, e in ipairs(type(cdb.questDropped) == "table" and cdb.questDropped or {}) do
    if type(e) == "table" and type(e.quest) == "number" then
      N.questDropped[#N.questDropped + 1] = { quest = e.quest, turnin = e.turnin == true or nil,
        name = type(e.name) == "string" and e.name or nil }
    end
  end
  local G = ns.GPS
  if G and G.groupChoice then
    for id, v in pairs(type(cdb.groupChoice) == "table" and cdb.groupChoice or {}) do
      if G.groupChoice[id] == nil and (v == "keep" or v == "leave") then G.groupChoice[id] = v end
    end
  end
end
-- Whether quest `id` is left out of quest routes: Leave Out on the popup, or a stop of it removed.
function N.QuestLeftOut(id)
  local G = ns.GPS
  if G and G.groupChoice and G.groupChoice[id] == "leave" then return true end
  for _, e in ipairs(N.questDropped or {}) do
    if e.quest == id then return true end
  end
  return false
end
-- The quests left out: { { id, name }, ... } by name (Options > Routing > Quest Route lists them).
function N.LeftOutQuests()
  local out, seen = {}, {}
  local function add(id, name)
    if seen[id] then
      if not out[seen[id]].name and name then out[seen[id]].name = name end
      return
    end
    out[#out + 1] = { id = id, name = name }
    seen[id] = #out
  end
  local G = ns.GPS
  for id, v in pairs(G and G.groupChoice or {}) do
    if v == "leave" then add(id, nil) end
  end
  for _, e in ipairs(N.questDropped or {}) do add(e.quest, not e.turnin and e.name or nil) end
  local T = ns.Layers and ns.Layers.QuestTitle
  for _, q in ipairs(out) do
    local ok, t = pcall(function() return T and T(q.id) end)
    if ok and type(t) == "string" and t ~= "" and not (ns.IsSecret and ns.IsSecret(t)) then q.name = t end
    q.name = q.name or Format(L["Quest %d"], q.id)
  end
  table.sort(out, function(a, b) return a.name < b.name end)
  return out
end
-- Quest `id` put back in quest routes (the player's choice: a group quest isn't asked about again, it's kept).
function N.PutBackQuest(id)
  local G = ns.GPS
  if G and G.groupChoice and G.groupChoice[id] == "leave" then G.groupChoice[id] = "keep" end
  for i = #(N.questDropped or {}), 1, -1 do
    if N.questDropped[i].quest == id then table.remove(N.questDropped, i) end
  end
  N.SaveQuestChoices()
end
function N.PutBackAllQuests()
  for _, q in ipairs(N.LeftOutQuests()) do N.PutBackQuest(q.id) end
end
-- Quest `id` gone from the log (turned in or abandoned): its choices let go. Not pruning the player's data (the
-- project's rule: player data is kept forever, never capped or pruned by itself): a choice about a quest no longer in
-- the log is moot, and one picked up again is asked about afresh.
function N.ForgetQuest(id)
  local G = ns.GPS
  local had = false
  if G and G.groupChoice and G.groupChoice[id] ~= nil then G.groupChoice[id], had = nil, true end
  for i = #(N.questDropped or {}), 1, -1 do
    if N.questDropped[i].quest == id then
      table.remove(N.questDropped, i)
      had = true
    end
  end
  if had then N.SaveQuestChoices() end
end
-- The same for every quest not in `ids` (the quest log's questIDs, Layers.LogQuests), for quests turned in or
-- abandoned while the addon wasn't watching. An empty log isn't taken as one: the game may not have sent it yet.
function N.ForgetGoneQuests(ids)
  if not ids or #ids == 0 then return end
  local inLog = {}
  for _, id in ipairs(ids) do inLog[id] = true end
  local G = ns.GPS
  local gone = {}
  for id in pairs(G and G.groupChoice or {}) do
    if not inLog[id] then gone[#gone + 1] = id end
  end
  for _, e in ipairs(N.questDropped or {}) do
    if not inLog[e.quest] then gone[#gone + 1] = e.quest end
  end
  for _, id in ipairs(gone) do N.ForgetQuest(id) end
end

-- Remove stop i from the route (the route is recomputed).
function N.RemoveStop(i)
  local d = N.stops[i]
  if not d then return end
  if d.questRoute and d.quest and not N.QuestDropped(d) then
    N.questDropped = N.questDropped or {}
    local list = N.questDropped
    list[#list + 1] = { quest = d.quest, turnin = d.turnin or nil, name = d.name }
    -- (said, with where to put it back: it stays out of quest routes from now on)
    if ns.Print then
      ns.Print(Format(L["Quest Route: %s stays out of your quest routes. To put it back: Options > Routing > Quest Route."], d.name or "?"))
    end
  end
  table.remove(N.stops, i)
  N.reorderDue = true -- (a quest route: the rest in order again, N.MaybeReorder)
  Changed()
end

function N.SetDestination(x, y, cont, name)
  return N.SetStops({ { x = x, y = y, cont = cont, name = name, icon = 1 } })
end

-- Changes whenever the stops do (a new route, a stop added, removed or reached).
function N.Version() return version end

function N.Clear()
  N.stops, N.loop, N.keepOrder = {}, false, false
  N.paused, N.pauseWatch = nil, nil
  N.redOk, N.skipLearn, N.noWalk, N.walkKept, N.riskOk, N.riskQuestion, N.riskAsking = {}, {}, {}, {}, {}, nil, nil
  N.hostileSaid, N.noSwim, N.swimBans = {}, nil, {}
  N.trip = N.trip + 1
  N.ClearSkippedRides()
  Changed()
  N.PauseShown() -- (no route: no Resume button, and the Pause button's glow gone; cleared while paused, it stayed lit
  -- on the next route's button, 2026-11-18)
end
-- The buttons that show routing paused, laid out again: the quick bar's Pause button (its place and glow) and the
-- minimap square's Resume button. (N.SetPaused does it on a change; a route cleared or replaced while paused too.)
function N.PauseShown()
  local G = ns.GPS
  if not G then return end
  if G.LayoutQuick then G.LayoutQuick() end
  if G.RefreshQuick then G.RefreshQuick() end
  if G.RefreshMinimapResume then G.RefreshMinimapResume() end
end

-- Called at login: bring back the saved stops.
function N.Restore()
  local cdb = ns.CharDB()
  local list = cdb.stops or (cdb.dest and { cdb.dest }) or {}
  N.stops = {}
  for _, d in ipairs(list) do
    if d.x and d.y and d.cont then N.stops[#N.stops + 1] = Copy(d) end
  end
  N.loop = cdb.loop and #N.stops > 1 or false
  N.keepOrder = cdb.keepOrder and #N.stops > 0 or false
  N.keepOrder = N.ListedOrder() -- (or its stops say so)
  N.paused = (#N.stops > 0 and (cdb.paused == "auto" or cdb.paused == "manual" or cdb.paused == "perf")) and cdb.paused or nil
  N.pauseWatch = nil
  N.redOk = {}
  for _, z in ipairs(#N.stops > 0 and cdb.redOk or {}) do N.redOk[z] = true end
  N.riskOk = {}
  for k, v in pairs(#N.stops > 0 and type(cdb.riskOk) == "table" and cdb.riskOk or {}) do N.riskOk[k] = v end
  N.hostileSaid = {}
  for _, name in ipairs(#N.stops > 0 and type(cdb.hostileSaid) == "table" and cdb.hostileSaid or {}) do
    if type(name) == "string" then N.hostileSaid[name] = true end
  end
  N.RestoreQuestChoices(cdb) -- (with or without a route since 1.3.13)
  N.skipLearn = {}
  for _, node in ipairs(#N.stops > 0 and cdb.skipLearn or {}) do N.skipLearn[node] = true end
  N.skipRides = {}
  for _, key in ipairs(#N.stops > 0 and cdb.skipRides or {}) do N.skipRides[key] = true end
  N.noSwim = (#N.stops > 0 and cdb.noSwim == true) or nil
  N.swimBans = {}
  for _, b in ipairs(N.noSwim and type(cdb.swimBans) == "table" and cdb.swimBans or {}) do
    local ok = type(b) == "table" and type(b.cont) == "number" and type(b.rows) == "table" and #b.rows % 3 == 0
    for _, v in ipairs(ok and b.rows or {}) do ok = ok and type(v) == "number" end
    if ok then N.swimBans[#N.swimBans + 1] = { cont = b.cont, rows = b.rows, n = b.n, lifted = b.lifted == true or nil } end
  end
  if next(N.skipRides) then N.FlightsChanged() end
  N.dest = N.stops[1]
  N.route, N.arrivedAt = nil, nil
  version = version + 1
end

---------------------------------------------------------------------------
-- Planning across transports (zeppelins, boats)
---------------------------------------------------------------------------

N.KIND_TRANSPORT, N.KIND_PLANNED = 2, 3 -- route segment kinds beyond Router's road/offroad
N.WALK_FACTOR = 1.35 -- straight-line yards -> expected route yards, for planning only
N.DOCK_YD = 40 -- "at the dock" radius

-- Planning a walk from (x1, y1) to (x2, y2) on `cont`: its straight yards, plus what the router
-- charges for the yards in zones too high for the player (Router.LEVEL_FACTOR each: the way round
-- them, or through at a cost), but in the zones in `exempt` (the trip's own ends: where the player
-- starts and the stop is; not a dock walked past, which would let the walk through the zone it's
-- in). Else a flight over them lost to a walk that looked short in a straight line.
-- (Sampled every PLAN_ZONE_STEP yards; the yards in each zone remembered for every pair, the exact
-- points the key — 97% of a recalculation's pairs repeat, and only the ones from the player's own spot
-- are new (the 2026-10-07 router profile; `keep` is unused now, kept for the callers). `exempt` is
-- applied after the memo, so it may differ between calls.)
N.PLAN_ZONE_STEP = 64
N.PLAN_YARDS_MAX = 20000 -- remembered pairs, then started over
local planYards = { red = nil, n = 0 } -- [key] = { [zone] = yards }, for the zones too high now (`red`)
function N.PlanYards(cont, x1, y1, x2, y2, keep, exempt)
  local d = math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)
  local R = ns.Router
  local red = R and R.RedZones and R.RedZones()
  if not red or not (ns.Zones and ns.Zones[Geo.Base(cont)]) then return d end
  if planYards.red ~= red then planYards = { red = red, n = 0 } end
  local key = cont .. ":" .. x1 .. ":" .. y1 .. ":" .. x2 .. ":" .. y2
  local zy = planYards[key]
  if not zy then
    zy = {}
    local c = Geo.Base(cont)
    local n = math.max(1, math.ceil(d / N.PLAN_ZONE_STEP))
    for k = 0, n - 1 do
      local t = (k + 0.5) / n
      local z = R.ZoneAt(c, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
      if red[z] then zy[z] = (zy[z] or 0) + d / n end
    end
    if planYards.n >= N.PLAN_YARDS_MAX then planYards = { red = red, n = 0 } end
    planYards[key], planYards.n = zy, planYards.n + 1
  end
  local extra = 0
  for z, yd in pairs(zy) do
    if not (exempt and exempt[z]) then extra = extra + yd end
  end
  return d + extra * (R.LEVEL_FACTOR - 1)
end

---------------------------------------------------------------------------
-- Flight paths (Data/Flights.lua) between the flight masters this character knows
---------------------------------------------------------------------------

N.FLIGHT_SPEED = 32 -- yd/s along the flight path
N.FLIGHT_OVERHEAD = 15 -- s: talking to the flight master, taking off and landing

local flightCache -- { key, masters = { [node] = { cont, x, y, name } }, trips = { [from] = { [to] = row } } }

-- Flight masters (Data/Pois.lua kind 1): { [nodeID] = { cont, x, y, name, faction, en = the data's English name } };
-- cont is the city level for one down in a city (Undercity's: p[7]). The name is the game's (ns.TaxiName: in its
-- language, as the flight map and Taxi.lua's recorded flights have it), else the data's.
local function Masters()
  local m = {}
  for cont, list in pairs(ns.Pois or {}) do
    for _, p in ipairs(list) do
      if p[1] == 1 then
        local lvl = p[7] and ns.CityLevels and ns.CityLevels[p[7]] and p[7] -- (with the city's data)
        m[p[5]] = { lvl or cont, p[2], p[3], ns.TaxiName and ns.TaxiName(p[5], p[4]) or p[4], p[6], en = p[4] }
      end
    end
  end
  return m
end

-- Flight masters a character knows from the start, before any flight map is opened, by race (UnitRace's file name or
-- name, lower case) and faction (2026-11-08: Horde Skyborne know Thunder Bluff's and Orgrimmar's, so the flight
-- between them is theirs from level 1, never a detour to learn it). Nodes as Data/Pois.lua's.
N.STARTING_FLIGHTS = { { race = "skyborne", faction = "Horde", nodes = { 22, 23 } } } -- Thunder Bluff, Orgrimmar
function N.StartingFlightNodes()
  local out = {}
  local okR, name, file = pcall(function() return UnitRace("player") end)
  local okF, faction = pcall(function() return UnitFactionGroup("player") end)
  if not (okR and okF and faction) then return out end
  local race = string.lower(tostring(file or name or ""))
  local named = string.lower(tostring(name or ""))
  for _, s in ipairs(N.STARTING_FLIGHTS) do
    if s.faction == faction and (race == s.race or string.find(named, s.race, 1, true)) then
      for _, node in ipairs(s.nodes) do out[node] = true end
    end
  end
  return out
end

-- The flight master nodes this character knows (seen on a flight map: Taxi.lua; and those it starts with).
function N.KnownFlightNodes()
  local known, n = {}, 0
  for node in pairs(N.StartingFlightNodes()) do
    known[node] = true
    n = n + 1
  end
  local cdb = ns.CharDB and ns.CharDB()
  for _, entry in pairs(cdb and cdb.taxiNodes or {}) do
    for _, node in ipairs(entry.nodes or {}) do
      if node.known and node.nodeID and not known[node.nodeID] then
        known[node.nodeID] = true
        n = n + 1
      end
    end
  end
  return known, n
end

-- Rides the player left out of this route (right-click "Remove?" on a ride's pin: GPSFrame): not taken
-- again on it, rerouting or after a /reload (saved with the stops); a new route clears it. A flight's is
-- one connection between two flight masters (either way: "h:a:b"), so every flight over it goes too; a
-- boat's, a zeppelin's, the tram's, its row's; a teleport's, its item or spell.
N.skipRides = {}
local function HopKey(a, b)
  a, b = tostring(a), tostring(b)
  if b < a then a, b = b, a end
  return "h:" .. a .. ":" .. b
end
-- The key ride row `t` is left out by (`hop`: a flight's k-th connection, from its k-th flight master).
function N.RideKey(t, hop)
  if hop and t.hops and t.hops[hop + 1] then return HopKey(t.hops[hop], t.hops[hop + 1]) end
  if t.use then return "u:" .. (t.item and ("i" .. t.item) or ("s" .. tostring(t.spell or t[8]))) end
  if t.from and t.to then return "f:" .. tostring(t.from) .. ">" .. tostring(t.to) end
  return string.format("t:%s:%.0f,%.0f>%.0f,%.0f", tostring(t[8]), t[2], t[3], t[5], t[6])
end
N.skipNames = {} -- [key] = the ride's name (its pin's: "Boat to Auberdine"), for "Route not possible without"
function N.SkipRide(t, hop, name)
  local key = N.RideKey(t, hop)
  N.skipRides[key] = true
  N.skipNames[key] = name
  N.FlightsChanged() -- (the flights over a connection left out: worked out again without it)
  N.SaveStops()
end
function N.ClearSkippedRides()
  if next(N.skipRides or {}) then N.FlightsChanged() end
  N.skipRides, N.skipNames = {}, {}
end

-- Recompute the flights on the next plan (a flight map was opened, the option changed).
function N.FlightsChanged()
  flightCache = nil
  N.Invalidate(true, true) -- (also forgets the stop-to-stop times)
end

-- A route option the player changed (flight paths, the hearthstone, class teleports, the zones
-- and towns avoided): the whole trip worked out again at once, not compared with the one shown
-- (a longer one isn't held back), the stops put in the fastest order again under it (the order
-- was chosen with the old one: a flight since turned off), and the map redrawn now.
function N.OptionsChanged()
  flightCache = nil
  N.SyncSwim() -- ("Allow swimming")
  if ns.Teleports and ns.Teleports.Changed then ns.Teleports.Changed() end
  N.Invalidate(true, true)
  local st = ns.settings and ns.settings.gps
  if st and st.fastestOrder and #N.stops > 1 and not N.loop and not N.keepOrder and not N.KeepCityOrder() then
    N.OrderStops()
  end
  if ns.GPS and ns.GPS.Redraw then ns.GPS.Redraw() end
end

-- The character's faction as in Data/Pois.lua ("A" / "H"), or nil when unknown.
local function Faction()
  local f = ns.CharDB and ns.CharDB().faction
  return f == "Alliance" and "A" or f == "Horde" and "H" or nil
end
N.Faction = Faction

-- Whether transport row t (a boat, a zeppelin, a lift, a dungeon's portal) is one the player's
-- faction can take: not with either end among the other faction's guards (Data/Hostile.lua:
-- within DOCK_GUARDS_YD of them; the ship waits off the quay). Worked out once per faction.
N.DOCK_GUARDS_YD = 100
-- Zeppelins, boats and the tram turned off (asked 2026-10-03: right-click a dock, or Options → Routing): never in a
-- route until turned on again, unlike a ride left out of one route (N.SkipRide). Account-wide (gps.ridesOff), by the
-- ride's kind and its two ends, so regenerated data keeps them.
N.RIDE_KINDS = { zeppelin = true, boat = true, tram = true }
function N.RideId(t)
  return string.format("%s:%s|%s", tostring(t[8]), tostring(t[9]), tostring(t[10]))
end
function N.RideAllowed(t)
  local off = ns.settings and ns.settings.gps and ns.settings.gps.ridesOff
  return not (off and N.RIDE_KINDS[t[8]] and off[N.RideId(t)])
end
function N.SetRideAllowed(t, on)
  local st = ns.settings and ns.settings.gps
  if not st then return end
  st.ridesOff = st.ridesOff or {}
  st.ridesOff[N.RideId(t)] = (not on) or nil
  N.OptionsChanged()
end

local usable = {}
function N.TransportUsable(t)
  local side = Faction()
  -- (a row's own `faction`, where the guards can't tell: Data/Transports.lua, addon_data.TRANSPORT_FACTIONS)
  if t.faction == "both" then return true end
  if (t.faction == "A" or t.faction == "H") and side then return t.faction == side end
  local R = ns.Router
  if not (side and R and R.HostileAt and ns.Hostile) then return true end
  usable[side] = usable[side] or {}
  local v = usable[side][t]
  if v == nil then
    local function guarded(c, x, y)
      for a = 0, 15 do
        for k = 0, 3 do
          local r = N.DOCK_GUARDS_YD * k / 3
          if R.HostileAt(c, x + math.cos(a * math.pi / 8) * r, y + math.sin(a * math.pi / 8) * r, side) then return true end
        end
      end
      return false
    end
    v = not (guarded(t[1], t[2], t[3]) or guarded(t[4], t[5], t[6]))
    usable[side][t] = v
  end
  return v
end

-- Every trip between two known flight masters, connecting through known ones like the
-- game does: rows in the transports' format { c, x1, y1, c, x2, y2, seconds, "flight",
-- fromName, toName, "flight master", pts = { x, y, ... } via the connecting stops }.
-- Seconds: learned ones (Taxi.lua records each flight taken) or the path length.
-- Also trips from flight masters of the character's faction not learned yet but with a
-- direct flight to a known one: talking to one learns it, and the flight leaves from there
-- (rows marked learn = true). Flights only ever land at known ones.
local function Flights()
  if ns.settings and ns.settings.gps.useFlights == false or not ns.Flights then return nil end
  if N.corpse then return nil end -- a ghost can't take a flight
  local known, count = N.KnownFlightNodes()
  if count < 1 then return nil end
  local fac = Faction()
  local key = count .. (fac or "") .. ":" .. (ns.names and ns.names.taxiVer or 0) -- (and the game's names for them)
  if flightCache and flightCache.key == key then return flightCache end
  local masters = Masters()
  local adj, fresh = {}, {}
  for _, f in ipairs(ns.Flights) do
    local a, b = f[1], f[2]
    local ma, mb = masters[a], masters[b]
    if ma and mb and known[b] then
      if known[a] then
        adj[a] = adj[a] or {}
        adj[a][#adj[a] + 1] = { b, f[3] }
      elseif fac and ma[5] and string.find(ma[5], fac, 1, true) then
        fresh[a] = fresh[a] or {}
        fresh[a][#fresh[a] + 1] = { b, f[3] }
      end
    end
  end
  local learned = ns.CharDB and ns.CharDB().flights or {}
  local trips = {}
  local starts = {}
  for from in pairs(adj) do starts[from] = adj[from] end
  for from, edges in pairs(fresh) do starts[from] = edges end
  -- (issue #372) A trip's cost is its seconds in the air plus one FLIGHT_OVERHEAD, the air found by the fastest way
  -- over the network: a connection its recorded seconds when flown, else yards / FLIGHT_SPEED, and every recorded
  -- trip a shortcut too. Recorded seconds are on the taxi only (Taxi.lua), so mixing them with estimates that carry
  -- the overhead made landing and boarding again (A > B, B > C) cost less than the one flight A > C.
  local byName, recorded = {}, {}
  for node, m in pairs(masters) do
    -- (recorded flights are keyed by the game's names, in its language; older ones the English too)
    if m.en and known[node] then byName[m.en] = node end
    if m[4] and known[node] then byName[m[4]] = node end
  end
  local hopsSkipped = false
  for k in pairs(N.skipRides) do
    if string.sub(k, 1, 2) == "h:" then hopsSkipped = true end
  end
  if not hopsSkipped then -- (a recorded trip's path isn't known: none while a connection is left out)
    for key, rec in pairs(learned) do
      local an, bn = string.match(key, "^(.-) > (.+)$")
      local a, b = an and byName[an], bn and byName[bn]
      if a and b and a ~= b and type(rec) == "table" and tonumber(rec.seconds) then
        recorded[a] = recorded[a] or {}
        recorded[a][#recorded[a] + 1] = { b, tonumber(rec.seconds) }
      end
    end
  end
  local function Hop(u, v, yards)
    local mu, mv = masters[u], masters[v]
    local took = mu and mv and mu[4] and mv[4] and learned[mu[4] .. " > " .. mv[4]]
    return took and tonumber(took.seconds) or yards / N.FLIGHT_SPEED
  end
  for from, first in pairs(starts) do
    -- shortest flight (yards) to every other known master
    local dist, prev, done = { [from] = 0 }, {}, {}
    while true do
      local u, best
      for v, dv in pairs(dist) do
        if not done[v] and (not best or dv < best) then u, best = v, dv end
      end
      if not u then break end
      done[u] = true
      for _, e in ipairs(u == from and first or adj[u] or {}) do
        local v, nd = e[1], best + e[2]
        if not N.skipRides[HopKey(u, v)] and (not dist[v] or nd < dist[v]) then dist[v], prev[v] = nd, u end
      end
    end
    -- seconds in the air to every other known master
    local air, airDone = { [from] = 0 }, {}
    while true do
      local u, best
      for v, dv in pairs(air) do
        if not airDone[v] and (not best or dv < best) then u, best = v, dv end
      end
      if not u then break end
      airDone[u] = true
      for _, e in ipairs(u == from and first or adj[u] or {}) do
        local v = e[1]
        if not N.skipRides[HopKey(u, v)] then
          local nd = best + Hop(u, v, e[2])
          if not air[v] or nd < air[v] then air[v] = nd end
        end
      end
      for _, e in ipairs(recorded[u] or {}) do
        local v, nd = e[1], best + e[2]
        if not air[v] or nd < air[v] then air[v] = nd end
      end
    end
    trips[from] = {}
    for to, yards in pairs(dist) do
      if to ~= from then
        local a, b = masters[from], masters[to]
        local pts, cur, stops = {}, to, {}
        while cur do
          table.insert(stops, 1, cur)
          cur = prev[cur]
        end
        for _, s in ipairs(stops) do
          pts[#pts + 1], pts[#pts + 2] = masters[s][2], masters[s][3]
        end
        local took = learned[a[4] .. " > " .. b[4]]
        local secs = (air[to] or took and tonumber(took.seconds) or yards / N.FLIGHT_SPEED) + N.FLIGHT_OVERHEAD
        trips[from][to] = { a[1], a[2], a[3], b[1], b[2], b[3], secs, "flight", a[4], b[4],
          fresh[from] and "new flight master" or "flight master", pts = pts, learn = fresh[from] and true or nil,
          from = from, to = to, hops = stops }
      end
    end
  end
  -- every landing is a place on the map too, with flights on from there or not
  local lands = {}
  for _, to in pairs(trips) do
    for node in pairs(to) do lands[node] = true end
  end
  for node in pairs(lands) do trips[node] = trips[node] or {} end
  flightCache = { key = key, masters = masters, trips = trips }
  return flightCache
end

-- The rides route `r` takes that the player can leave out of it (right-click on their pins: GPSFrame),
-- each once: { cont, x, y, title, kind, ride = row, hop = k, dock = { transport, side } } where it's
-- boarded: a flight's at each flight master it flies on from (a connection each), a teleport's where it
-- lands; none for the flight being flown or a dungeon's way in.
N.RIDE_NAMES = { zeppelin = "Zeppelin", boat = "Boat", tram = "Deeprun Tram", lift = "Lift", teleporter = "Teleporter" }
-- (a ride's pin's title by its kind, %s where it goes: "Zeppelin to Jaggedswine Farm, Durotar")
N.RIDE_TO = { zeppelin = L["Zeppelin to %s"], boat = L["Boat to %s"], tram = L["Deeprun Tram to %s"], lift = L["Lift to %s"],
  teleporter = L["Teleporter to %s"] }
local rowIndex = setmetatable({}, { __mode = "k" }) -- [transport row] = its index in ns.Transports
function N.RidePins(r)
  local out, seen = {}, {}
  if not r then return out end
  local masters = flightCache and flightCache.masters
  local function add(p)
    local key = N.RideKey(p.ride, p.hop)
    if seen[key] then return end
    seen[key] = true
    out[#out + 1] = p
  end
  local function legs(list)
    for _, leg in ipairs(list or {}) do
      local t = leg.ride
      if t and not t.flying and t[8] ~= "portal" then
        if t.hops then
          for k = 1, #t.hops - 1 do
            local a, b = masters and masters[t.hops[k]], masters and masters[t.hops[k + 1]]
            if a and b then
              -- (a flight from a flight master to learn first: its pin stays the not-learned icon, over the map's
              -- own; it was the known one, and Kargath looked known, issue #652)
              local learn = t.learn and k == 1 or nil
              add({ cont = a[1], x = a[2], y = a[3], kind = "flight", ride = t, hop = k, learn = learn,
                title = learn and Format(L["Learn the flight path, then take the flight to %s"], tostring(t[10]))
                  or Format(L["Flight: %s to %s"], tostring(a[4]), tostring(b[4])) })
            end
          end
        elseif t.use then
          add({ cont = t[4], x = t[5], y = t[6], kind = "teleport", ride = t,
            title = Format(L["%s to %s"], (tostring(t[8]):gsub("^%l", string.upper)), tostring(t[10] ~= "" and t[10] or "?")) })
        elseif t[8] ~= "flight" then
          local back = leg.from == 2
          if not next(rowIndex) then
            for i, row in ipairs(ns.Transports or {}) do rowIndex[row] = i end
          end
          local i = rowIndex[t]
          add({ cont = back and t[4] or t[1], x = back and t[5] or t[2], y = back and t[6] or t[3], kind = t[8], ride = t,
            title = Format(N.RIDE_TO[t[8]] or L["Ride to %s"], tostring(ns.RideEndName(t, back and 1 or 2))),
            dock = i and { i, back and 2 or 1 } or nil })
        end
      end
    end
  end
  local stretches = r.stretches
  legs(r.legs)
  for i = 2, stretches and N.PlannedStops() or 0 do
    if stretches[i] then legs(stretches[i].legs) end
  end
  return out
end

-- Fastest sequence of legs from (px, py) on `cont` to stop d (default: the next stop),
-- walking, taking transports (Data/Transports.lua) and flights between known flight
-- masters. Legs: { walk = true, cont, x1, y1, x2, y2 } or { ride = row, from = 1|2 }
-- (a transport row, or a flight row in the same format; from = which end we board at).
-- `teleports`: rows (Teleports.lua) usable right away from (px, py): hearthstone, etc.
-- `direct`: seconds the walk straight from (px, py) to the stop takes at least (routed: see Stretch).
-- Walks found not to be walks (Stretch's N.WithoutBlockedWalks: over ground the terrain blocks) are left out, by
-- both ends to NO_WALK_ROUND: [cont] = { [from cell] = { [to cell] = true } }; for this route (a new one, Clear) and
-- the roads as they are (Invalidate's `fresh`: an edit).
N.NO_WALK_ROUND = 200
N.noWalk = {}
function N.NoWalkCell(x, y) return math.floor(x / N.NO_WALK_ROUND) * 65536 + math.floor(y / N.NO_WALK_ROUND) end
function N.NoWalkBetween(cont, x1, y1, x2, y2)
  local c = N.noWalk[cont]
  local from = c and c[N.NoWalkCell(x1, y1)]
  return from and from[N.NoWalkCell(x2, y2)] or false
end
function N.Plan(cont, px, py, speed, d, teleports, direct, avoid)
  d = d or N.dest
  -- (`avoid`: walks left out for this plan only, as N.noWalk's: the ride check's long ways round, CompareRide)
  local function Barred(c, x1, y1, x2, y2)
    if N.NoWalkBetween(c, x1, y1, x2, y2) then return true end
    local t = avoid and avoid[c]
    local from = t and t[N.NoWalkCell(x1, y1)]
    return from and from[N.NoWalkCell(x2, y2)] or false
  end
  local nodes = { { cont, px, py }, { d.cont, d.x, d.y } }
  -- (a room reached only through a teleporter, N.StopRoom: a place there is walked to and from only from that room)
  local stopRoom = N.StopRoom(d)
  local function RoomOf(n, i)
    if i == 1 then return N.roomIn end
    if i == 2 then return stopRoom end
    local t = n.t and ns.Transports[n.t]
    return t and t.room == n.side and n.t or nil
  end
  for _, row in ipairs(teleports or {}) do
    nodes[#nodes + 1] = { row[4], row[5], row[6], tp = row }
  end
  -- (a dungeon's way in only for a trip from or to inside it, never through one as a shortcut;
  -- and the dungeon one is entered from, Blackrock Spire's for Blackwing Lair)
  local inside = { [cont] = true, [d.cont] = true }
  for _ = 1, 2 do
    for _, t in ipairs(ns.Transports or {}) do
      if t[8] == "portal" and inside[t[4]] and ns.CityLevels and ns.CityLevels[t[1]] then inside[t[1]] = true end
    end
  end
  for i, t in ipairs(ns.Transports or {}) do
    if (t[8] ~= "portal" or inside[t[4]]) and N.TransportUsable(t) and N.RideAllowed(t) then
      nodes[#nodes + 1] = { t[1], t[2], t[3], t = i, side = 1 }
      nodes[#nodes + 1] = { t[4], t[5], t[6], t = i, side = 2 }
    end
  end
  local fl = Flights()
  if fl then
    for node in pairs(fl.trips) do
      local m = fl.masters[node]
      nodes[#nodes + 1] = { m[1], m[2], m[3], fm = node }
    end
  end
  -- (the trip's own ends: zones too high there are where the player is and the stop is)
  local Rt = ns.Router
  local exempt = Rt and Rt.ZoneAt and { [Rt.ZoneAt(Geo.Base(cont), px, py)] = true, [Rt.ZoneAt(Geo.Base(d.cont), d.x, d.y)] = true }
  -- (each place reached two ways apart, key = place * 2 + 1 when walking on from it is allowed: the start, a ride's
  -- end, or always without `direct`; + 0 when walked to with `direct` set, the way with a ride wanted: no walk on from a
  -- place walked to, which would only be the walk there in two, a flight master walked past. One label a place: the
  -- Rut'theran end of Darnassus's portal walked to (down the tree, as the crow flies) shut out the portal's arrival
  -- there, and from Dolanaar the way with a ride went up the portal and down again, 2026-10-07. Never back to a place
  -- the plan was at, either: its other label by a ride there and back was the same walk in two, and it won)
  local dist, prev, rode, done = { [3] = 0 }, {}, {}, {}
  local breathe = ns.Router and ns.Router.Breathe
  local expanded = 0
  local goal
  while true do
    local k, best
    for i in pairs(dist) do
      if not done[i] and (not best or dist[i] < best) then k, best = i, dist[i] end
    end
    if not k then break end
    local u, on = math.floor(k / 2), k % 2 == 1
    if u == 2 then
      goal = k
      break
    end
    done[k] = true
    expanded = expanded + 1
    if breathe then breathe(expanded, 1) end -- (in a background job: a pause after each place: each weighs them all)
    local a = nodes[u]
    local function relax(v, cost, ride)
      local kv = v * 2 + ((ride or not direct) and 1 or 0)
      if not done[kv] and (not dist[kv] or dist[k] + cost < dist[kv]) then
        local p = k
        while p do
          if math.floor(p / 2) == v then return end
          p = prev[p]
        end
        dist[kv], prev[kv], rode[kv] = dist[k] + cost, k, ride
      end
    end
    for v, b in ipairs(nodes) do
      if v ~= u then
        if a[1] == b[1] and on and RoomOf(a, u) == RoomOf(b, v) and not Barred(a[1], a[2], a[3], b[2], b[3]) then -- (zones too high on the way: as the router weighs them)
          local cost = N.PlanYards(a[1], a[2], a[3], b[2], b[3], u ~= 1 and v ~= 2, exempt) * N.WALK_FACTOR / speed
          if u == 1 and v == 2 and direct then cost = math.max(cost, direct) end
          relax(v, cost, nil)
        end
        if a.t and b.t == a.t and a.side ~= b.side and not N.skipRides[N.RideKey(ns.Transports[a.t])] then
          relax(v, ns.Transports[a.t][7], { ns.Transports[a.t], a.side })
        end
        if u == 1 and b.tp and not N.skipRides[N.RideKey(b.tp)] then relax(v, b.tp[7], { b.tp, 1 }) end -- a teleport, from where we stand
        if a.fm and b.fm then
          local row = fl.trips[a.fm][b.fm]
          if row and not N.skipRides[N.RideKey(row)] then relax(v, row[7], { row, 1 }) end
        end
      end
    end
  end
  if not goal then return nil end
  local path, cur = {}, goal
  while cur do
    table.insert(path, 1, cur)
    cur = prev[cur]
  end
  local legs = {}
  for i = 2, #path do
    local a, b = nodes[math.floor(path[i - 1] / 2)], nodes[math.floor(path[i] / 2)]
    local r = rode[path[i]]
    local last = legs[#legs]
    if r then
      legs[#legs + 1] = { ride = r[1], from = r[2] }
    elseif last and last.walk and last.cont == a[1] and not Barred(a[1], last.x1, last.y1, b[2], b[3]) then
      -- (a dock or flight master only walked past: one walk, the router's own way; routed in
      -- two, each would be free in the zone of the point between, one too high for the player.
      -- Not a walk left out, N.noWalk: routed as one, it was the same walk again)
      last.x2, last.y2 = b[2], b[3]
    else
      legs[#legs + 1] = { walk = true, cont = a[1], x1 = a[2], y1 = a[3], x2 = b[2], y2 = b[3] }
    end
  end
  return legs, dist[goal]
end

-- For a bug report (/agps debug): how the trip to the next stop is planned from here, and why:
-- the character's level and the zones too high for it, the flight masters known, the plan and
-- its time, the planned walk straight there, and the route as it stands.
function N.DescribePlan()
  local d = N.stops[1]
  if not d then return "no stop" end
  local px, py, cont = Geo.PlayerWorld()
  if not px then return "no position" end
  cont = N.PlayerLevel(cont)
  local _, walk = N.Speeds()
  local R = ns.Router
  local red = R and R.RedZones and R.RedZones()
  local names = {}
  for z in pairs(red or {}) do names[#names + 1] = ns.Maps and ns.Maps[z] and ns.ZoneName(z, ns.Maps[z].name) or tostring(z) end
  table.sort(names)
  local _, known = N.KnownFlightNodes()
  local legs, secs = N.Plan(cont, px, py, walk, d)
  local steps = {}
  for _, l in ipairs(legs or {}) do
    steps[#steps + 1] = l.ride and ("ride " .. tostring(l.ride[10] or l.ride[8]) .. string.format(" %.0fs", l.ride[7] or 0))
      or string.format("walk %.0f yd", math.sqrt((l.x2 - l.x1) ^ 2 + (l.y2 - l.y1) ^ 2))
  end
  local direct
  if Geo.Base(d.cont) == Geo.Base(cont) and R and R.ZoneAt then
    local exempt = { [R.ZoneAt(Geo.Base(cont), px, py)] = true, [R.ZoneAt(Geo.Base(d.cont), d.x, d.y)] = true }
    direct = N.PlanYards(cont, px, py, d.x, d.y, false, exempt) * N.WALK_FACTOR / walk
  end
  local lvl = UnitLevel and UnitLevel("player")
  local st = ns.settings and ns.settings.gps or {}
  local r = N.route
  return string.format("from (%d, %.0f, %.0f) to (%s, %.0f, %.0f) level=%s walk=%.1f avoidHigh=%s useFlights=%s "
    .. "flight masters known=%s | too high: %s | plan %.0fs: %s | walk straight there %.0fs | route %s yd, rides %s s | %s",
    cont, px, py, tostring(d.cont), d.x, d.y, tostring(lvl), walk, tostring(st.avoidHighZones ~= false),
    tostring(st.useFlights ~= false), tostring(known), table.concat(names, ", "), secs or -1, table.concat(steps, " > "),
    direct or -1, r and string.format("%.0f", r.totalYards or 0) or "none", r and string.format("%.0f", r.totalRide or 0) or "-",
    N.lastRideCheck or "no ride check")
end

-- One stretch of the route, from (sx, sy) on `cont` to stop `d`: every walking leg routed
-- over its own continent's roads, transport rides as straight dotted lines.
-- { parts = { { cont, pts, kinds }, ... }, legs, first = yards before any ride,
--   walk = walking yards, ride = seconds on transports, road = yards on roads }
-- opts.transient: (sx, sy) is the player's position (see Router's Walk).
-- Whether the player is indoors (a building, a cave: IsIndoors), or nil when unknown: over a
-- cave under walkable ground, whether they're up top or down in it (Router.CaveLevel).
-- Whether the player is swimming (IsSwimming), or nil when unknown: in a capital's water, its roads to the ways out
-- (Router.CaveDown; asked 2026-10-08, a fall into Stormwind's canal routed straight up its wall).
function N.Swimming()
  local o = ns.Geo.override -- (the dev tools' simulated player: as it says, when it says)
  if o and o.swimming ~= nil then return o.swimming end
  if not IsSwimming then return nil end
  local ok, v = pcall(IsSwimming)
  if not ok or (ns.IsSecret and ns.IsSecret(v)) then return nil end
  return v and true or false
end

function N.Indoors()
  local o = ns.Geo.override -- (the dev tools' simulated player: as it says, when it says)
  if o and o.indoors ~= nil then return o.indoors end
  if not IsIndoors then return nil end
  local ok, v = pcall(IsIndoors)
  if not ok or (ns.IsSecret and ns.IsSecret(v)) then return nil end
  return v and true or false
end

-- The player's height (world z), or nil when unknown: under a capital's floor, whether they're
-- up on it or down under it (Router.CaveDown).
function N.PlayerZ()
  local x, _, _, z = Geo.PlayerWorld()
  if not x or not z or z == 0 then return nil end
  return z
end

-- The player's height down in a city with floors over floors (asked 2026-10-06: better ways to know the player's floor;
-- WoW Forever gives no height), followed along its roads: the floor changes only on stairs, a ramp or a lift, so each
-- look it's the height of the road near the player (TRACK_YD) closest to the last one, within a stair's step
-- (TRACK_STEP); with none that close, the last one kept. It starts at a lift's bottom (its `z1`) when the player is
-- there, else among the roads at the height of the rooms the minimap's zone text names (GPS.ZoneTextBand), else the
-- nearest road's. Routes start on that floor (Compute's `z`). Game heights (the roads' `z`); nil off such a level.
N.TRACK_YD = 8
N.TRACK_STEP = 4
N.TRACK_SAME_Z = 1.5 -- (in a building: a road this near the floor followed is that floor; another floor's, only
N.TRACK_ON_YD = 2 -- standing on it: N.TrackCityZ)
N.TRACK_EVERY = 0.25
N.TRACK_STILL_EVERY = 2 -- (motionless on the exact spot the roads give the same answer: searched this often instead)
N.TRACK_STALE = 5 -- (not followed for this long: the player left the level, or the map and arrow were closed)
N.TRACK_LIFT_YD = 15
N.TRACK_STAIR_OFF = 6 -- (in a building: off its stairs onto a floor stood on, this far up or down)
N.TRACK_OUT_YD = 4 -- (outdoors by a building: a road of the floor followed this near, else not on it: N.OutsideFloor)
N.TRACK_UNDER_YD = 16 -- (down in a city's level: no start on a floor with a lower floor's road this near; N.TrackCityZ)
N.TRACK_LEFT_YD = 16 -- (asked 2026-11-15: in a capital, no road of the floor followed this near: left; N.TrackCityZ)
-- (the road followed's own and those joined to it within this along the roads come first: Router.EdgesJoined. In
-- Undercity, walked down the stairs from the Cooking Trainer three yards off their middle, the walkway overhead was
-- nearer at about the height and the floor followed went up onto it: "Take the stairs down, 10 yd down" at the foot,
-- 2026-11-15, "this is a constant issue")
N.TRACK_JOINED_YD = 12
local track -- { level, z, at, look, x, y }
local raisedTrack -- (N.TrackRaisedZ's: { level, z, at, edge })
local trackLook = { at = -math.huge } -- (a building's: when it was last looked for, the player not in one)
-- (asked 2026-10-06, Brill's inn: the same in the buildings with insides, Data/Indoors.lua (ns.Indoors), on the
-- continent: entered by a door, on its ground floor, followed up its stairs. Looked for only near one of them, by a
-- grid of BUILDING_CELL yards made the first time per level: not every building on the continent each status update)
N.BUILDING_CELL = 64
local buildingGrid = {} -- level -> { list = ns.Indoors[level], cells = { [key] = { building, ... } } }
function N.InBuilding(level, px, py)
  local list = ns.Indoors and ns.Indoors[level]
  if not list then return nil end
  local C = N.BUILDING_CELL
  local grid = buildingGrid[level]
  if not grid or grid.list ~= list then
    grid = { list = list, cells = {} }
    for _, b in ipairs(list) do
      local r = b.r + N.TRACK_YD
      for cx = math.floor((b.x - r) / C), math.floor((b.x + r) / C) do
        for cy = math.floor((b.y - r) / C), math.floor((b.y + r) / C) do
          local k = cx * 4096 + cy -- (a continent's cells are within 2048 of 0 either way)
          local c = grid.cells[k] or {}
          grid.cells[k] = c
          c[#c + 1] = b
        end
      end
    end
    buildingGrid[level] = grid
  end
  for _, b in ipairs(grid.cells[math.floor(px / C) * 4096 + math.floor(py / C)] or {}) do
    local r = b.r + N.TRACK_YD
    if math.abs(b.x - px) <= r and math.abs(b.y - py) <= r then return b end
  end
  return nil
end
-- (a /reload or a logout upstairs: the floor followed then, kept per character (N.SaveTrack), taken up again when the
-- player is where they were, as that's where they log in; once)
N.RESUME_YD, N.RESUME_DAYS = 3, 7
local function Resumed(level, px, py)
  local cdb = ns.CharDB and ns.CharDB()
  local s = cdb and cdb.floorTrack
  if not s then return nil end
  cdb.floorTrack = nil
  if s.level ~= level or (s.x - px) ^ 2 + (s.y - py) ^ 2 > N.RESUME_YD ^ 2 then return nil end
  if time and s.time and time() - s.time > N.RESUME_DAYS * 86400 then return nil end
  return s.z
end
function N.SaveTrack()
  local cdb = ns.CharDB and ns.CharDB()
  if not cdb then return end
  local fresh = track and track.x and GetTime() - track.at < N.TRACK_STALE and not Geo.Simulated()
  cdb.floorTrack = fresh and { level = track.level, x = track.x, y = track.y, z = track.z, time = time and time() } or nil
end
-- The floor followed (N.TrackCityZ) a moment ago, on `level` when given, or nil.
function N.FollowedZ(level)
  local now = GetTime()
  if track and track.z and now >= track.at and now - track.at < N.TRACK_STALE and (not level or track.level == level) then
    return track.z
  end
  local rt = raisedTrack -- (on a bridge over the land: N.TrackRaisedZ)
  if rt and now >= rt.at and now - rt.at < N.TRACK_STALE and (not level or rt.level == level) then return rt.z end
  return nil
end
-- The height of the NPC's spot at (x, y) on `level` (asked 2026-11-14: every NPC in the capitals and the caves, "any
-- path leading to those mapped to the appropriate height"): the nearest of the shipped spawns (Data/NpcFloors.lua,
-- `agps npc-floors`: heights only) within SPAWN_YD, else nil. The one lookup for a stop with no height of its own:
-- Copy's (a plain stop, a /way, Questie's), a quest stop's and a searched NPC's (before the floor learned there),
-- the guide routes' (RestedXP.lua's X.HeightXY, after their shipped waypoint heights). SPAWN_YD: the guides'
-- waypoints at an NPC over stacked floors are within 1 yd of its spawn (167 of 175 checked, 2026-11-14); from 3 yd
-- a spawn on another floor was picked.
N.SPAWN_YD, N.SPAWN_CELL = 2, 8
local spawnIx = {} -- [level] = { src = its list, [cell] = { x, y, z, ... } }
function N.SpawnZ(level, x, y)
  local t = level and x and y and ns.NpcFloors and ns.NpcFloors[level]
  if not t then return nil end
  local C = N.SPAWN_CELL
  local ix = spawnIx[level]
  if not ix or ix.src ~= t then -- (by cells, the first time: thousands of spots)
    ix = { src = t }
    for i = 1, #t - 2, 3 do
      local k = math.floor(t[i] / C) * 65536 + math.floor(t[i + 1] / C)
      local b = ix[k]
      if not b then b = {} ix[k] = b end
      b[#b + 1], b[#b + 2], b[#b + 3] = t[i], t[i + 1], t[i + 2]
    end
    spawnIx[level] = ix
  end
  local best, bd = nil, N.SPAWN_YD ^ 2
  local cx, cy = math.floor(x / C), math.floor(y / C)
  for dx = -1, 1 do
    for dy = -1, 1 do
      local b = ix[(cx + dx) * 65536 + cy + dy]
      for i = 1, b and #b - 2 or 0, 3 do
        local d = (b[i] - x) ^ 2 + (b[i + 1] - y) ^ 2
        if d <= bd then best, bd = b[i + 2], d end
      end
    end
  end
  return best
end
-- The player followed on the stop's floor (N.StopFloor): the floor followed in a building or city, about the stop's
-- height (SAME_FLOOR_Z), near it (FLOOR_HINT_YD).
N.SAME_FLOOR_Z = 3
-- A stop's height: its own (a city place's, an NPC's), else that of the town place it's at (N.StopFloorOf's: a stop made
-- by a click on the map by Brill's Enchanting trainer, upstairs, had none, and was "arrived" under it on the ground floor
-- the player was followed on, the 1.1.5 test pass)
function N.StopHeight(d)
  if not d then return nil end
  if d.z then return d.z end
  N.StopFloorOf(d)
  return d.floorZ or nil
end
local function FloorNear(d)
  local now = GetTime()
  if not (d and N.StopHeight(d) and track and track.z and now >= track.at and now - track.at < N.TRACK_STALE) then return nil end
  if track.level ~= d.cont then return nil end
  local px, py = N.playerX, N.playerY
  if not px or (px - d.x) ^ 2 + (py - d.y) ^ 2 > (N.FLOOR_HINT_YD or 60) ^ 2 then return nil end
  return track.z
end
function N.OnStopFloor(d)
  local z = FloorNear(d)
  return z ~= nil and math.abs(z - N.StopHeight(d)) <= N.SAME_FLOOR_Z
end
-- The player followed on another floor than the stop's (a building's: its roads' heights), near it: not arrived yet.
-- (down in an underground city, by its roads' heights too: as far apart as its hint says "above you" or "below you",
-- N.HEIGHT_HINT_YD; Undercity's ring under a walkway, indoor phase 2, 2026-10-06)
function N.OffStopFloor(d)
  local z = FloorNear(d)
  if z == nil then return false end
  local l = ns.CityLevels and ns.CityLevels[d.cont]
  -- (in a capital, by its roads' floors too: phase 3)
  if (l and l.zoff) or N.InCapital(d.cont, d.x, d.y) then return math.abs(z - N.StopHeight(d)) >= N.HEIGHT_HINT_YD end
  return math.abs(z - N.StopHeight(d)) > N.SAME_FLOOR_Z and N.StopFloorOf(d) ~= nil
end
-- (in a capital's own cells too (indoor routes phase 3, 2026-10-06): its roads have their floors, `nz`)

-- Rooms reached only through a teleporter (a Transports row's `room`, its end: Stormwind's mage trainers' room under the
-- city, by the Wizard's Sanctum's portal at the top of its tower; asked 2026-11-17, "Path here says below but the trainer
-- is actually at the top of the tower through a portal", issue #565). A stop with its height within ROOM_Z of the room
-- end's, within ROOM_YD of it, is in the room: the plan reaches it only through the teleporter (N.Plan), it's never
-- arrived at from the street over it, and no "Below you" is said for it.
N.ROOM_YD, N.ROOM_Z = 60, 15
-- (the player in the room: put exactly on its landing (ROOM_LAND_YD), facing the way the portal turns you (ROOM_FACE
-- radians). The game gives no height and the tower's stairs pass the portal at street level, so nothing else tells
-- the room from the street over it; out again by the portal back up, or ROOM_YD from its end)
N.ROOM_LAND_YD, N.ROOM_FACE = 1.5, 0.01
N.roomIn = nil -- (the row the player is in the room of, or nil)
-- (or a hop there: moved ROOM_HOP_YD or more faster than ROOM_HOP_SPEED yd/s (an epic mount runs 14; the text looks every
-- 0.25 s), onto within ROOM_HOP_LAND_YD of its landing.
-- 2026-11-17, the player through the portal and still told to take it: put 1.4 yd off the server's spot, and running
-- on, the landing's exact spot and facing were never seen)
N.ROOM_HOP_YD, N.ROOM_HOP_SPEED, N.ROOM_HOP_LAND_YD = 5, 25, 6
local roomLast -- ({ x, y, cont, time }: the player's spot when RoomWatch last looked)
local function RoomEnd(t)
  local s = t.room
  if s == 1 then return t[1], t[2], t[3], t.z1, t.land1, t.land2 end
  return t[4], t[5], t[6], t.z2, t.land2, t.land1
end
function N.StopRoom(d)
  if not (d and d.z and d.x) then return nil end
  for i, t in ipairs(ns.Transports or {}) do
    if t.room then
      local c, x, y, z = RoomEnd(t)
      if z and c == d.cont and (x - d.x) ^ 2 + (y - d.y) ^ 2 <= N.ROOM_YD ^ 2 and math.abs(d.z - z) <= N.ROOM_Z then
        return i
      end
    end
  end
  return nil
end
function N.RoomWatch(px, py, cont)
  if not px then return end
  local face
  local now = GetTime and GetTime() or 0
  local last = roomLast
  roomLast = { px, py, cont, now }
  local hop = last and last[3] == cont and now > last[4] and (px - last[1]) ^ 2 + (py - last[2]) ^ 2 >= N.ROOM_HOP_YD ^ 2
    and math.sqrt((px - last[1]) ^ 2 + (py - last[2]) ^ 2) >= N.ROOM_HOP_SPEED * (now - last[4])
  local hop2 = N.ROOM_HOP_LAND_YD ^ 2
  for i, t in ipairs(ns.Transports or {}) do
    if t.room and t.face then
      local c, x, y, _, inLand, outLand = RoomEnd(t)
      if c == cont and inLand and outLand and (x - px) ^ 2 + (y - py) ^ 2 <= (N.ROOM_YD * 2) ^ 2 then
        face = face or (Geo.Facing and Geo.Facing()) or false
        local faced = face and math.abs(face - t.face) <= N.ROOM_FACE
        local dIn, dOut = (px - inLand[1]) ^ 2 + (py - inLand[2]) ^ 2, (px - outLand[1]) ^ 2 + (py - outLand[2]) ^ 2
        if (faced and dIn <= N.ROOM_LAND_YD ^ 2) or (hop and dIn <= hop2) then
          if N.roomIn ~= i then N.roomIn = i Changed() end
        elseif N.roomIn == i and ((faced and dOut <= N.ROOM_LAND_YD ^ 2) or (hop and dOut <= hop2)) then
          N.roomIn = nil
          Changed()
        end
      end
      if N.roomIn == i and (c ~= cont or (x - px) ^ 2 + (y - py) ^ 2 > N.ROOM_YD ^ 2) then N.roomIn = nil end
    end
  end
end

-- In a city (an underground city's level, a capital's own cells) with the next stop outside it (asked 2026-11-15: "pause
-- recalculating routes while inside the city only for destinations outside the city to save on compute"): the route is
-- kept while the player is on it, never worked out again by time, distance walked or a finished terrain search; off it,
-- worked out again as anywhere (a route kept from another way would point them back). Out of the city, as before.
function N.CityHold(px, py, level)
  local d = N.dest
  if not (d and px and d.cont) or d.corpse then return false end
  local l = ns.CityLevels and ns.CityLevels[level]
  if l then return not l.instance and d.cont ~= level end
  local P = ns.Passability
  if not (P and P.OverlayRaw) then return false end
  local _, o = P.OverlayRaw(level, px, py)
  if not (o and o.capital) then return false end
  if Geo.Base(d.cont) ~= level then return true end
  if d.cont ~= level then return true end -- (down a city's level from a capital: another place)
  local _, od = P.OverlayRaw(level, d.x, d.y)
  return od ~= o
end
function N.InCapital(level, px, py)
  local R = ns.Router
  return px and R and R.CapitalAt and R.CapitalAt(level, px, py) or false
end
-- (a hearthstone into an inn with its inside lands the player on the innkeeper's floor (the bind point): followed from
-- there. Its floor wasn't known in there till they walked out of a door, and a trainer upstairs was "arrived" under it,
-- the 1.1.5 test pass. Taken within HEARTH_TRACK_YD of where it landed, HEARTH_TRACK_SECONDS after; Teleports.lua)
N.HEARTH_TRACK_YD, N.HEARTH_TRACK_SECONDS = 6, 120
N.INN_PLACE_YD = 30 -- (the town's inn among its places, ns.TownPlaces: "Brill Inn", its innkeeper's height)
N.TRACK_JUMP_YD = 40 -- (moved this far since the last look: a teleport, a hearth; followed from scratch)
local hearthed -- { level, x, y, at }
function N.Hearthed(level, x, y)
  hearthed = level and x and y and { level = level, x = x, y = y, at = GetTime() } or nil
  trackLook.x = nil -- (a failed look's still-player backoff: the hearth changes its answer, look again)
end
-- The innkeeper's floor at (px, py): the height of the roads near (hs) nearest the town's inn place's, or nil.
local function InnFloor(level, px, py, hs)
  local base = Geo.Base(level)
  local inn
  for _, t in pairs(ns.TownPlaces or {}) do
    if t.cont == base then
      for _, p in ipairs(t) do
        if p.z and type(p[1]) == "string" and p[1]:find(" Inn$")
            and (p.x - px) ^ 2 + (p.y - py) ^ 2 <= N.INN_PLACE_YD ^ 2 then inn = p end
      end
    end
  end
  if not inn then return nil end
  local best
  for _, h in ipairs(hs) do
    if math.abs(h.z - inn.z) <= N.SAME_FLOOR_Z and (not best or math.abs(h.z - inn.z) < math.abs(best - inn.z)) then
      best = h.z
    end
  end
  return best
end
-- Outdoors by a building with its inside (the game says so: IsIndoors, which is true in its rooms) with no road of
-- floor `z` within TRACK_OUT_YD (`hs`: HeightsNear's): the player isn't on that floor, they're out on the land. The
-- floor followed is let go and taken again where it's clear (2026-11-05: outside Brill inn's door the floor followed
-- was still its upstairs, and the route went in, up and back down). Not in a capital (its streets are outdoors, on
-- floors over floors) or a city's level.
function N.OutsideFloor(level, px, py, hs, z)
  if (ns.CityLevels and ns.CityLevels[level]) or not (ns.Indoors and ns.Indoors[level] and N.InBuilding(level, px, py))
      or N.Indoors() ~= false or N.InCapital(level, px, py) then
    return false
  end
  for _, h in ipairs(hs or {}) do
    if h.d <= N.TRACK_OUT_YD and math.abs(h.z - z) <= N.TRACK_STEP then return false end
  end
  return true
end
function N.TrackCityZ(level, px, py)
  -- (on a flight: not walked, nothing followed; started again where it lands. Orgrimmar, 2026-11-15: flown in over the
  -- city, the floor followed was the streets' under the wind rider, kept on landing up on the tower (no road at that
  -- height up there): by Doras "Above you, 36 yd up", the route down and back up the tower)
  if UnitOnTaxi and UnitOnTaxi("player") then
    track = nil
    return nil
  end
  local l = ns.CityLevels and ns.CityLevels[level]
  local building = not l and px and ((ns.Indoors and ns.Indoors[level] and N.InBuilding(level, px, py))
    or N.InCapital(level, px, py) or (ns.Router and ns.Router.InLayeredCave and ns.Router.InLayeredCave(level, px, py)))
  if not ((l and not l.instance) or building) or not (px and ns.Router and ns.Router.HeightsNear) then return nil end
  local now = GetTime()
  -- (followed a moment ago on this level; not since TRACK_STALE, or the clock went back: started again)
  local same = track and track.level == level and now >= track.at and now - track.at < N.TRACK_STALE
    and (px - track.x) ^ 2 + (py - track.y) ^ 2 <= N.TRACK_JUMP_YD ^ 2
  if same and now - track.at < N.TRACK_EVERY then return track.z end
  -- (standing still, the same roads give the same height: the last one kept, searched again only every
  -- TRACK_STILL_EVERY, so a road rebuilt under a still player is picked up within it; the idle sweep's
  -- biggest cost, 2026-10-07)
  if same and px == track.x and py == track.y and now - (track.look or track.at) < N.TRACK_STILL_EVERY then
    track.at = now
    return track.z
  end
  if building and not same and now >= trackLook.at
      and now - trackLook.at < (px == trackLook.x and py == trackLook.y and N.TRACK_STILL_EVERY or N.TRACK_EVERY) then
    return nil
  end
  trackLook.at, trackLook.x, trackLook.y = now, px, py
  local hs = ns.Router.HeightsNear(level, px, py, N.TRACK_YD)
  if same and track.z and N.OutsideFloor(level, px, py, hs, track.z) then same, track = false, nil end
  if not (hs and hs[1]) then return same and track.z or nil end
  local z, flat, edge
  if same and track.z then
    -- (the nearest road at about the last height: the one walked on. Not the one closest in height: at a stair's foot
    -- that was the floor it leaves, and the height never went up.) In a building with its inside, another floor's road
    -- (stairs too: a building's are narrow, walked on their middle) is taken only standing on it (TRACK_ON_YD): beside
    -- Brill inn's cellar stairwell its upper flight's middle, 2.7 yd off, was nearer than the ground floor's road, 6.1
    -- yd off, and the floor followed went down it to the cellar (QA, 2026-10-07: routes then planned
    -- from the cellar). Not in a capital or Undercity: their stairs are wide, walked anywhere across.
    -- Off stairs onto a floor stood on, up to TRACK_STAIR_OFF (2026-11-05): Brill inn's stairs end 3 yd over its
    -- ground floor, a yard from it, and its passage runs beside them. Walked a yard off their middle the floor followed
    -- stayed at their foot, over TRACK_STEP from the passage, went back up them beside it, and outside the door the
    -- route went in, up and back down. Not onto stairs (under them, the passage jumped up onto their middle) and never
    -- from one floor to another (floors over floors): TRACK_STEP.
    local indoor = N.InBuilding(level, px, py)
    -- (first the roads joined to the one followed, N.TRACK_JOINED_YD)
    local joined = track.edge and track.graph == (ns.Router.DebugGraph and ns.Router.DebugGraph(level)) -- (the same build)
      and ns.Router.EdgesJoined and ns.Router.EdgesJoined(level, track.edge, N.TRACK_JOINED_YD)
    if joined and not indoor then
      for _, h in ipairs(hs) do
        if joined[h.edge] and math.abs(h.z - track.z) <= N.TRACK_STEP then
          z, flat, edge = h.z, h.flat, h.edge
          break
        end
      end
    end
    for _, h in ipairs(z and {} or hs) do
      local dz = math.abs(h.z - track.z)
      local step = indoor and h.d <= N.TRACK_ON_YD and h.flat and track.flat == false and N.TRACK_STAIR_OFF
        or N.TRACK_STEP
      if not z and dz <= step and (not indoor or dz <= N.TRACK_SAME_Z or h.d <= N.TRACK_ON_YD) then
        z, flat, edge = h.z, h.flat, h.edge
      end
    end
    -- (in a capital's streets, off the floor followed: no road of it within TRACK_LEFT_YD, the player on another's
    -- (TRACK_ON_YD) and the roads near all that one floor. Orgrimmar, 2026-11-15: down the slope from a road that ends
    -- at 24 by the inn's door (no road on to the inn's floor, 16) the floor followed stayed 24, and by Innkeeper
    -- Gryshka "Below you, 9 yd down", the route 116 yd out and round. Not in a building, a cave, Undercity: stacked)
    if not z and not indoor and not l and hs[1].d <= N.TRACK_ON_YD and N.InCapital(level, px, py)
        and not (ns.Router.InLayeredCave and ns.Router.InLayeredCave(level, px, py)) then
      local on, left = hs[1], true
      for _, h in ipairs(hs) do
        if math.abs(h.z - on.z) > N.TRACK_STEP then left = false end
      end
      for _, h in ipairs(left and ns.Router.HeightsNear(level, px, py, N.TRACK_LEFT_YD) or {}) do
        if math.abs(h.z - track.z) <= N.TRACK_STEP then left = false end
      end
      if left then z, flat, edge = on.z, on.flat, on.edge end
    end
    -- (down in a city's level, no road of the floor followed within TRACK_LEFT_YD: dropped off a ledge, or the floor
    -- followed was wrong. Taken again where the roads near are all one floor, else let go (unknown: the route starts on
    -- any floor). Undercity, 2026-11-15: dropped 17 yd into the Trade Quarter, "Below you, 17 yd down" stayed and the
    -- route said turn around, "never reconsidered after the player actually drops")
    if not z and l and not l.instance and not indoor then
      local onFloor = false
      for _, h in ipairs(ns.Router.HeightsNear(level, px, py, N.TRACK_LEFT_YD) or {}) do
        if math.abs(h.z - track.z) <= N.TRACK_STEP then onFloor = true break end
      end
      if not onFloor then
        local on, one = hs[1], true
        for _, h in ipairs(hs) do
          if math.abs(h.z - on.z) > N.TRACK_STEP then one = false end
        end
        if not one then
          track = nil
          return nil
        end
        z, flat, edge = on.z, on.flat, on.edge
      end
    end
    -- (lost by a stairs road out in the open: no road near at the floor followed, a stairs road's within
    -- TRACK_LEFT_YD. Let go: unknown, taken again where it's clear. Orgrimmar's Wind Rider tower, 2026-11-15: its stairs road coils
    -- tight, its turns stacked, and the ramp walked runs yards off it; a few yards off, the turn near was over
    -- TRACK_STEP from the last height and the floor followed stayed at its foot (24) the whole climb: by Doras "Above
    -- you, 36 yd up", never arrived)
    if not z and not indoor then
      for _, h in ipairs(ns.Router.HeightsNear(level, px, py, N.TRACK_LEFT_YD) or {}) do
        if h.stair then
          track = nil
          return nil
        end
      end
    end
    if not z then z, flat, edge = track.z, track.flat, track.edge end
  else
    -- (the start: a lift's bottom, the zone text's rooms, the nearest road; in a building, the floor followed when the
    -- game was last left here (a /reload upstairs), else where its roads near are all one floor: at its door)
    -- (the Deeprun Tram's ways in only on coming out of it: the keep's road runs 25 yd over Stormwind's)
    local outOfTram = N.tramAt and now >= N.tramAt and now - N.tramAt < N.TRAM_OUT_SECONDS
    for _, t in ipairs(ns.Transports or {}) do
      if t[8] ~= "tram" then
        if t[1] == level and t.z1 and (t[2] - px) ^ 2 + (t[3] - py) ^ 2 <= N.TRACK_LIFT_YD ^ 2 then z = t.z1 end
      elseif outOfTram then
        for e = 1, 2 do
          local c, x, y = t[e * 3 - 2], t[e * 3 - 1], t[e * 3]
          local ez = e == 1 and t.z1 or t.z2
          if c == level and ez and (x - px) ^ 2 + (y - py) ^ 2 <= N.TRACK_LIFT_YD ^ 2 then z = ez end
        end
      end
    end
    if not z and building then z = Resumed(level, px, py) end
    if not z and building and hearthed and hearthed.level == level and now - hearthed.at < N.HEARTH_TRACK_SECONDS
        and (px - hearthed.x) ^ 2 + (py - hearthed.y) ^ 2 <= N.HEARTH_TRACK_YD ^ 2 then
      z = InnFloor(level, px, py, hs)
      if z then hearthed = nil end -- (taken once)
    end
    -- (else only where it's clear: the roads near the player, of the zone text's rooms' heights, all on one floor.
    -- Under a walkway the nearest road is the walkway's: started up there, the route went the long way round; until
    -- the player reaches a clear spot, no height, and the route starts on any floor, as before)
    if not z then
      local zt = GetMinimapZoneText and GetMinimapZoneText()
      local lo, hi
      if l and ns.GPS and ns.GPS.ZoneTextBand then lo, hi = ns.GPS.ZoneTextBand(Geo.Base(level), px, py, zt, l.wmo) end
      local first, clear = nil, true
      for _, h in ipairs(hs) do
        if not lo or (h.z >= lo - 1 and h.z <= hi + 1) then
          if not first then first = h.z elseif math.abs(h.z - first) > N.TRACK_STEP then clear = false end
        end
      end
      if not (first and clear) then return nil end
      -- (down in a city's level, a floor with a lower one's road within TRACK_UNDER_YD: the player may be under it, on
      -- open floor below a walkway. Undercity, 2026-11-14: started on the walkways over the ring by the Rogues' Quarter,
      -- the player on the ring under them; "repair" went 559 yd round by the Trade Quarter, "14 yd down")
      if l then
        for _, h in ipairs(ns.Router.HeightsNear(level, px, py, N.TRACK_UNDER_YD) or {}) do
          if h.z < first - N.TRACK_STEP and (not lo or (h.z >= lo - 1 and h.z <= hi + 1)) then return nil end
        end
      end
      z = first
    end
  end
  -- (the road taken at the start: the nearest of its height)
  if not edge then
    for _, h in ipairs(hs) do
      if math.abs(h.z - z) <= 0.5 then edge = h.edge break end
    end
  end
  track = { level = level, z = z, at = now, look = now, x = px, y = py, flat = flat, edge = edge,
    graph = ns.Router.DebugGraph and ns.Router.DebugGraph(level) }
  return z
end
function N.ResetCityTrack() track, trackLook.at = nil, -math.huge end -- (the tests; a level left and come back to)
function N.SetTrackForTests(level, x, y, z) track = { level = level, z = z, at = GetTime(), look = GetTime(), x = x, y = y } end

-- The floor followed onto a raised road out on the land (a bridge or a floor over the land, edited so with the road
-- tools' Edit Road; asked 2026-11-18 for 1.3.10): the game gives no height, so it's taken only by walking onto the
-- road at one of its ends, where it meets the land (within RAISED_END_YD of an end, RAISED_ON_YD of the road), and
-- followed while the player stays on it (within RAISED_LEFT_YD of a raised road at about that height, TRACK_STEP);
-- off it, the ground again (nil). Under a bridge, never: the route starts on the roads under it (Router.OffRaised).
-- (In a capital, a building, a layered cave: N.TrackCityZ follows the floors there.)
N.RAISED_ON_YD, N.RAISED_END_YD, N.RAISED_LEFT_YD = 4, 8, 5
function N.TrackRaisedZ(level, px, py)
  local R = ns.Router
  if not (px and R and R.RaisedNear) or (UnitOnTaxi and UnitOnTaxi("player")) then
    raisedTrack = nil
    return nil
  end
  local now = GetTime()
  local near = R.RaisedNear(level, px, py, math.max(N.RAISED_ON_YD, N.RAISED_LEFT_YD))
  if not (near and near[1]) then
    raisedTrack = nil
    return nil
  end
  local rt = raisedTrack
  if rt and rt.level == level and now >= rt.at and now - rt.at < N.TRACK_STALE then
    for _, h in ipairs(near) do
      if h.z and h.d <= N.RAISED_LEFT_YD and math.abs(h.z - rt.z) <= N.TRACK_STEP then
        rt.z, rt.at, rt.edge = h.z, now, h.edge
        return rt.z
      end
    end
    raisedTrack = nil -- (off it: the ground again)
    return nil
  end
  raisedTrack = nil
  for _, h in ipairs(near) do
    if h.z and h.d <= N.RAISED_ON_YD and h.endD <= N.RAISED_END_YD then
      raisedTrack = { level = level, z = h.z, at = now, edge = h.edge }
      return h.z
    end
  end
  return nil
end
function N.ResetRaisedTrack() raisedTrack = nil end -- (the tests)
-- The player's floor known at (px, py) on `level`: the game height `z` of an NPC whose window just opened (they stand
-- by it; its shipped spawn's, Layers.OnNpcWindow). Down in a city's level or in a capital, followed from there: the
-- road near at about that height, else `z` itself. Whether it was taken.
function N.AnchorFloor(level, px, py, z)
  local l = ns.CityLevels and ns.CityLevels[level]
  if not (z and px and ((l and not l.instance) or N.InCapital(level, px, py)) and ns.Router and ns.Router.HeightsNear) then
    return false
  end
  local best, flat
  for _, h in ipairs(ns.Router.HeightsNear(level, px, py, N.TRACK_YD) or {}) do
    if not best and math.abs(h.z - z) <= N.TRACK_STEP then best, flat = h.z, h.flat end
  end
  local now = GetTime()
  track = { level = level, z = best or z, at = now, look = now, x = px, y = py, flat = flat }
  return true
end

-- A walking leg's options: `base` with the heights it starts and ends at, when known (a
-- dungeon's floors over floors: Router takes the roads on those floors).
local function LegOpts(base, z, tz)
  if not z and not tz then return base end
  local o = {}
  for k, v in pairs(base) do o[k] = v end
  o.z, o.tz = z or base.z, tz
  return o
end

-- `sz`: the height the stretch starts at, when known (a stop's).
-- A walk planned the whole way (from the straight line) against the best way with a ride (a
-- flight, a boat), both as routed: the straight line's yards say little round a lake or over
-- mountains, and through zones too high for the player they count many times over (for either:
-- a walk from a flight master too). The walks are routed and weighed as planning does (the zones
-- too high on them, but the trip's own ends), the rides at their times. (Reported: level 14 from
-- Brill into Arathi Highlands: planned on foot over Lordamere Lake and Alterac, the walk went round
-- by Silverpine, 7.6k yd, past the Sepulcher's flight master, the flight there from Undercity not
-- taken.) Worked out once per stop from about here (RIDE_CHECK_YD), remembered.
N.RIDE_CHECK_MIN_YD = 800 -- (shorter walks: not worth a second look)
-- (a stop near as the crow flies, walked to all the way: the ride check too when the walk's route is this long, a canyon
-- or a mountain between; from Blackrock Stronghold to Tanner Camp at level 5, 520 yd apart, the walk was 9k yd round
-- and the flight from Thorium Point half its time, the overnight trip sweep, 2026-10-07)
N.RIDE_CHECK_FAR_YD = 1600
N.RIDE_CHECK_YD = 200
local rideCheck = {} -- [key] = whether the way with a ride won
local ridePlan = {} -- [key] = the ride check's own plan, when the ride won: the one taken
local rideLast = {} -- [stop] = the last answer for it (from wherever: used while this square's is worked out)
local rideFinal = {} -- [stop] = rideLast's answer is a final one (a provisional one doesn't replace it)
local ridePlanLast = {} -- [stop] = the last final plan with a ride kept for it (used from a square not checked yet)
local ridePending = {} -- ["ride:" .. key] = a ride check queued and not done (N.CheckRedRoute waits for it)
-- [key] = the spot a square's check is made from: its first (issue #652: checked from wherever the player stood at each
-- recalculation, each check of a square still searched its walks from a new spot, came out provisional, and was made
-- again at the next; walking by Dun Algaz, up to five checks a square, each planning the trip six times over)
local rideSpot = {}
function N.RideChecking() return next(ridePending) ~= nil end
-- (for /agps debug route: what the ride checks remember, each answer and its plan's legs in short)
function N.RideDebug()
  local out = {}
  for k, v in pairs(rideCheck) do out[#out + 1] = "check " .. tostring(k) .. " = " .. tostring(v) end
  for k, v in pairs(rideLast) do out[#out + 1] = "last " .. tostring(k) .. " = " .. tostring(v) end
  for k, v in pairs(ridePlan) do
    local legs = {}
    for _, leg in ipairs(v and v.legs or {}) do
      legs[#legs + 1] = leg.ride and ("ride:" .. tostring(leg.ride[8]) .. (leg.ride.use and "(use)" or "")) or "walk"
    end
    out[#out + 1] = "plan " .. tostring(k) .. " = " .. table.concat(legs, ",")
  end
  for k in pairs(ridePending) do out[#out + 1] = "pending " .. tostring(k) end
  return out
end
-- The player's answer to "risk it?" (N.HostileRisk's popup): the route worked out again with it, the ride checks'
-- answers forgotten (they're remembered per square), and the zones too high on the way chosen not asked about again.
function N.AnswerRisk(q, yes)
  N.riskOk[q.key] = yes and true or false
  N.riskOk.trip = yes and true or false -- (and the rest of the trip's stops: asked once a trip)
  if N.SaveStops then N.SaveStops() end -- (kept over a /reload while the route is on)
  if N.riskQuestion == q then N.riskQuestion = nil end
  for _, z in ipairs((yes and q.riskyRed or q.safeRed) or {}) do N.redOk[z.z] = true end
  rideCheck, ridePlan, rideLast, rideFinal, ridePlanLast, rideSpot = {}, {}, {}, {}, {}, {}
  -- (the way answered meanwhile, while the check is worked out again: asked 2026-11-16, a "No" left the walk past Dun
  -- Algaz; the check, planning again past a long way round, ran for a while in the game and with nothing remembered
  -- the route was the walk all that time. No: the safe way; yes: the one past the guards)
  if q.stopKey then
    rideLast[q.stopKey] = (yes and not q.ridesSafe) or (not yes and q.ridesSafe) or false
    rideFinal[q.stopKey] = true -- (the player's answer: final till the check is)
    if rideLast[q.stopKey] and q.plan then ridePlanLast[q.stopKey] = q.plan end -- (the way with the ride itself)
  end
  N.Invalidate(false)
end
-- Seconds for a walk along `pts` as planning weighs it: the zones too high for the player (but
-- `exempt`) counted extra (PlanYards), and water at swimming's cost (Passability's: across the sea
-- to an island isn't a walk to take over the boat).
local function Weighed(cont, pts, walk, exempt, blocked)
  local P = ns.Passability
  -- (yards straight over ground the terrain blocks, `blocked`: at the router's own cost for them,
  -- not ruled out: a bridge the terrain doesn't know, Thandol Span, was one on both ways)
  local yards = (blocked or 0) * ((ns.Router and ns.Router.BLOCKED_PENALTY or 12) - 1)
  for i = 1, #pts - 3, 2 do
    if ns.Router.Breathe then ns.Router.Breathe((i + 1) / 2, 25) end -- (a long walk is thousands of pieces: in a
    local x1, y1, x2, y2 = pts[i], pts[i + 1], pts[i + 2], pts[i + 3] -- background job, a pause along the way)
    yards = yards + N.PlanYards(cont, x1, y1, x2, y2, false, exempt)
    local c = P and P.SegmentCost and P.SegmentCost(cont, x1, y1, x2, y2, 0)
    if c then yards = yards + math.max(0, c - math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)) end
  end
  return yards / walk
end
N.WeighedWalk = Weighed -- (the trip sweep's checks weigh as this does)

-- A routed walk that isn't one: no way there found on foot (a line across). (Yards over blocked
-- ground are weighed, Weighed's `blocked`: the sea to an island costs a lot, a bridge a little.)
local function Unwalkable(r)
  return r.unconnected
end
N.Unwalkable = Unwalkable
-- Walks between fixed points (a lift to a flight master, a landing to the stop: not from the
-- player) routed once and kept: rerouting as the player moves redoes only the walk from them
-- (a long walk after a flight, routed again on every recalculation, was a lag spike each time).
-- Forgotten with the route's other cached parts (Invalidate), and never a provisional one.
N.LEG_MEMO_MAX = 64
local legMemo, legMemoN = {}, 0
local function LegRoute(cont, x1, y1, x2, y2, o, fixed)
  if not fixed then return ns.Router.Route(cont, x1, y1, x2, y2, o) end
  local key = string.format("%d:%.1f:%.1f:%.1f:%.1f:%s:%s:%s:%s", cont, x1, y1, x2, y2, tostring(o.z), tostring(o.tz),
    tostring(o.offroad), tostring(o.roads))
  local r = legMemo[key]
  if r then return r end
  r = ns.Router.Route(cont, x1, y1, x2, y2, o)
  if not r.pending and not r.hopPending then -- (nor one with a hop whose way round is still searched, 2026-11-14)
    if legMemoN >= N.LEG_MEMO_MAX then legMemo, legMemoN = {}, 0 end
    legMemo[key], legMemoN = r, legMemoN + 1
  end
  return r
end

-- Each walking leg of `legs` routed (a list by leg index), with the heights they start and end
-- at (a ride's ends: into a dungeon, down a lift, the Deeprun Tram's ways in; the stop's).
local function EndZ(t, e) return e == 1 and t.z1 or e == 2 and (t.z2 or t.iz) or nil end
-- (`memo`: walks routed already, by their ends and heights: the plans of one N.WithoutBlockedWalks share the walk from
-- the player to the same place, routed again for each, 30 to 60 ms a time in the frame)
-- (a walk inside a room reached through a teleporter, N.StopRoom: from where it lands, or the player in it, to the stop
-- or back to it. Straight: the room is under the city's streets, which the roads over it are, and has none of its own)
local function RoomWalk(legs, li, d, sx, sy)
  local leg = legs[li]
  local function rowRoom(l, side)
    local t = l and l.ride
    if not (t and t.room) then return nil end
    for i, r in ipairs(ns.Transports or {}) do
      if r == t then return t.room == side and i or false end
    end
    return nil
  end
  local prev, nxt = legs[li - 1], legs[li + 1]
  local a = prev and prev.ride and rowRoom(prev, prev.from == 1 and 2 or 1)
  if a == nil and li == 1 and leg.x1 == sx and leg.y1 == sy then a = N.roomIn end
  local b = nxt and nxt.ride and rowRoom(nxt, nxt.from)
  if b == nil and leg.x2 == d.x and leg.y2 == d.y then b = N.StopRoom(d) end
  if not (a and a == b) then return nil end
  local R = ns.Router
  return { pts = { leg.x1, leg.y1, leg.x2, leg.y2 }, kinds = { R.KIND_OFFROAD }, -- (a kind per piece)
    length = math.sqrt((leg.x2 - leg.x1) ^ 2 + (leg.y2 - leg.y1) ^ 2), road = 0 }
end
local function WalkRoutes(legs, sx, sy, d, opts, sz, memo)
  local out, legZ = {}, sz
  for li, leg in ipairs(legs) do
    if ns.Router.Breathe then ns.Router.Breathe(1, 1) end -- (in a background job: a pause per leg routed)
    local inRoom = not leg.ride and RoomWalk(legs, li, d, sx, sy)
    if leg.ride then
      legZ = EndZ(leg.ride, leg.from == 1 and 2 or 1)
    elseif inRoom then
      out[li] = inRoom
      legZ = nil
    else
      local toStop = leg.x2 == d.x and leg.y2 == d.y
      local nxt = legs[li + 1]
      local endZ = toStop and N.StopZ(d) or (nxt and nxt.ride and EndZ(nxt.ride, nxt.from)) or nil
      local fromPlayer = opts.transient and leg.x1 == sx and leg.y1 == sy
      local key = memo and string.format("%d:%.1f:%.1f:%.1f:%.1f:%s:%s", leg.cont, leg.x1, leg.y1, leg.x2, leg.y2,
        tostring(legZ), tostring(endZ))
      out[li] = key and memo[key] or LegRoute(leg.cont, leg.x1, leg.y1, leg.x2, leg.y2,
        LegOpts(fromPlayer and opts or opts.fixed, legZ, endZ), not fromPlayer)
      if key then memo[key] = out[li] end
      legZ = toStop and endZ or nil
    end
  end
  return out
end

-- The walk the whole way against the best way with a ride, from about (sx, sy): { won, final },
-- with both walks routed from the spot rounded to RIDE_CHECK_ROUND (searches between fixed points,
-- remembered: a comparison from about here comes out the same, and final once they're done).
N.RIDE_CHECK_ROUND = 50
N.RIDE_CHECK_FAR_LOSS = 2
-- A walk the plan took that's a long way round, a mountain between (the plan's walks are straight lines): routed, it
-- weighs NO_WALK_DETOUR times the yards the plan put on it and NO_WALK_DETOUR_YD more (both as planning weighs them,
-- the zones too high counted extra). The overnight trip sweep, 2026-10-07: at level 5 from Lakeridge Highway to
-- Kurzen's Compound the way with a ride walked to Stonard's flight master, 1.1k yd straight and 10k round, and lost to
-- the walk; by Rog'mar's flight it took half the walk's time.
N.NO_WALK_DETOUR, N.NO_WALK_DETOUR_YD = 2, 1000
function N.WalkDetour(leg, r, exempt)
  if not (r and r.pts and #r.pts >= 4) or r.pending or Unwalkable(r) then return false end
  local planned = N.PlanYards(leg.cont, leg.x1, leg.y1, leg.x2, leg.y2, false, exempt) * N.WALK_FACTOR
  return Weighed(leg.cont, r.pts, 1, exempt, r.blocked) > planned * N.NO_WALK_DETOUR + N.NO_WALK_DETOUR_YD
end
-- The yards a walk the plan took came out longer than the plan put on it (as WalkDetour weighs them), 0 while searched.
-- One NO_WALK_LONGER_YD longer or more along the roads (NO_WALK_LONGER_ROAD of its yards on them: where the roads go,
-- which the plan's straight lines don't see), not a long way round, still gets the next plan looked at in the ride
-- check (the best kept). Issue #359: new Loch Modan roads made the walk from Ironforge's tram into southern Loch Modan
-- 13.8k yd -> 7.5k, no longer a long way round; the check stopped at the tram's plan and walked (1,318 s), never trying
-- Farholde Keep's flight (919 s). A walk round over the land is the walk search's and N.WithoutBlockedWalks': from Bough
-- Shadow to Lake Mennar the walk to Valormok's flight master, 773 yd straight and 2.2k round, half of it on roads, left
-- out flew there (649 s), and the way on foot by it (527 s) was lost. `offRoad`: off the roads too, for the plans after
-- the first (the check already looking past one: the best kept; #715, Thunder Bluff's rebuilt roads met the gap road's
-- loose end north of it, and from Desolace the plan past Camp Mojache's flight walked to Thunder Bluff's, 4.9k yd (2.4k
-- planned), a third of it off the roads: the check stopped there, at Camp Mojache's (1,187 s), never trying
-- Shadowprey's (1,023 s); the same past three zeppelins (2,318 s) to the Golden Plains, not Brackenwall's (1,985 s)).
N.NO_WALK_LONGER_YD, N.NO_WALK_LONGER_ROAD = 1000, 0.75
function N.WalkLonger(leg, r, exempt, offRoad)
  if not (r and r.pts and #r.pts >= 4) or r.pending or Unwalkable(r) then return 0 end
  if not (r.length and r.length > 0 and (offRoad or (r.road or 0) >= r.length * N.NO_WALK_LONGER_ROAD)) then return 0 end
  local planned = N.PlanYards(leg.cont, leg.x1, leg.y1, leg.x2, leg.y2, false, exempt) * N.WALK_FACTOR
  return math.max(0, Weighed(leg.cont, r.pts, 1, exempt, r.blocked) - planned)
end

-- The other faction's guards on the walks (asked 2026-11-14: a Horde player's walk from the Wetlands into Loch Modan
-- went through Dun Algaz, 1.3k yd past the Alliance's guards, and the flight round by Hammerfall and Kargath lost to it:
-- this check weighed the walks' time and the zones too high, never the guards the router keeps away from. "If there
-- is any other route with avoid enemy territory turned on we should use that instead even if higher level area walks
-- are needed to get there"). Yards of a walk along `pts` within their reach, the towns at its own ends left out as the
-- router leaves them (a stop in one); 0 with the option off (Router.HostileSide nil). A way HOSTILE_RIDE_YD or more
-- nearer them loses whatever its time (HostileBetter): the last resort. Closer than that, time decides, as before (and
-- as the route quality check weighs it: its `safer` is GUARD_YD, 100, fewer; at the router's HOSTILE_FACTOR a walk 89
-- yd nearer them lost to one 123 s slower).
N.HOSTILE_RIDE_YD = 100
N.HOSTILE_TRIES = 3
function N.HostileWalkYards(cont, pts)
  local R = ns.Router
  local side = R and R.HostileSide and R.HostileSide()
  local n = pts and #pts or 0
  if not (side and n >= 4 and ns.Hostile and ns.Hostile[cont] and R.HostileYards and R.HostileTownsNear) then return 0 end
  local exempt = R.HostileTownsNear(cont, side, pts[1], pts[2], pts[n - 1], pts[n])
  local yd = 0
  for i = 1, n - 3, 2 do
    if R.Breathe then R.Breathe((i + 1) / 2, 25) end -- (a long walk is thousands of pieces: a pause along the way)
    yd = yd + R.HostileYards(cont, pts[i], pts[i + 1], pts[i + 2], pts[i + 3], side, exempt)
  end
  return yd
end
-- Whether a way taking `s1` seconds (as weighed) past `g1` yards of the other faction's guards beats one of `s2`, `g2`.
-- (asked 2026-11-14, in place of the safer way always winning: "If a safe route would 30% longer or more, ask the
-- player if they want to risk going through enemy territory to save time." HOSTILE_SLOWER: that share; the safer way
-- wins up to it, past it time decides here and the ride check asks, N.HostileRisk)
N.HOSTILE_SLOWER = 0.3
function N.HostileBetter(s1, g1, s2, g2)
  if s1 < math.huge and g1 + N.HOSTILE_RIDE_YD <= g2 and s1 < s2 * (1 + N.HOSTILE_SLOWER) then return true end
  if s2 < math.huge and g2 + N.HOSTILE_RIDE_YD <= g1 and s2 < s1 * (1 + N.HOSTILE_SLOWER) then return false end
  return s1 < s2
end
-- The trip's answer to "risk it?" (N.riskOk[N.RiskKey(d)]: true the way past the guards, false the safe way), for the
-- stops as they are (SetStops' new route forgets them, as the zones too high said yes to).
N.riskOk = {}
function N.RiskKey(d)
  return string.format("%s:%.0f:%.0f", tostring(d.cont), d.x, d.y)
end
-- The answer for stop `d`: its own, else the trip's (`trip`: the first answer, for every later stop of the trip; asked
-- 2026-11-18, "they should only be asked once in a multi stop route"). nil: not asked yet.
function N.RiskAnswer(d)
  local a = d and N.riskOk[N.RiskKey(d)]
  if a == nil then a = N.riskOk.trip end
  return a
end
-- The walks of a plan as a route's parts (N.HostileOnRoute's, N.RedOnRoute's).
local function PlanParts(plan, routes)
  local parts = {}
  for li, leg in ipairs(plan) do
    local r = not leg.ride and routes[li]
    if r and r.pts and r.kinds then parts[#parts + 1] = { cont = leg.cont, pts = r.pts, kinds = r.kinds } end
  end
  return { parts = parts }
end

-- Whether a trip from `cont` to stop `d` starts down in a city (a city level, Undercity's) on the stop's continent.
-- (reported 2026-11-18, 1.3.9, Horde level 24 in Undercity to Loch Modan: "fly to The Sepulcher, walk 10.3k yd", away
-- from the stop, with the flight to Tarren Mill known. The plan's straight walk from The Sepulcher missed the Arathi
-- Highlands, too high, and from Tarren Mill crossed them; the road from either crosses them. The ride check, which
-- routes the plan's walks and plans again past a long way round, ran only from the stop's own continent, never down
-- in the city, so the plan's straight lines chose)
function N.CityStart(cont, d)
  return cont ~= d.cont and ns.CityLevels and ns.CityLevels[cont] ~= nil and Geo.Base(cont) == d.cont or false
end

local function CompareRide(cont, sx, sy, d, walk, tps, opts, sz)
  -- (the player's spot rounded; a stop's as it is: it doesn't move, and 25 yd off Cliffspring Falls' was out of the
  -- cave it's down in, so the ride compared wasn't the one taken, the overnight trip sweep, 2026-10-07)
  local q = N.RIDE_CHECK_ROUND
  local qx, qy = sx, sy
  if opts.transient then qx, qy = math.floor(sx / q + 0.5) * q, math.floor(sy / q + 0.5) * q end
  local legs = N.Plan(cont, qx, qy, walk, d, tps, math.huge)
  local fixed = { fixed = opts.fixed }
  -- (down in a city on the stop's continent, N.CityStart: no walk there in one, the way out is the city's lift or
  -- tunnel, a ride of the plan's. Only the ways with a ride weighed against each other, the walk out among them; the
  -- walk all the way never wins here, `lr` none)
  local city = N.CityStart(cont, d)
  local lr = not city and LegRoute(cont, qx, qy, d.x, d.y, LegOpts(opts.fixed, sz, N.StopZ(d)), true)
  if not legs then return { won = false, final = true } end
  if not city and not (lr and lr.pts and lr.length and lr.length >= N.RIDE_CHECK_MIN_YD) then return { won = false, final = true } end
  local Rt = ns.Router
  local exempt = Rt and Rt.ZoneAt and { [Rt.ZoneAt(Geo.Base(cont), sx, sy)] = true, [Rt.ZoneAt(Geo.Base(d.cont), d.x, d.y)] = true }
  local walkGuard = (city or Unwalkable(lr)) and 0 or N.HostileWalkYards(cont, lr.pts)
  local walkSecs = (city or Unwalkable(lr)) and math.huge or Weighed(cont, lr.pts, walk, exempt, lr.blocked)
  -- (issue #348: as an Alliance player walking by Brill, every check was provisional, the ride's walks to far flight
  -- masters and docks, 6k to 30k yd, still searched: each check routed them all, 2 s of background work, and was queued
  -- again at the next recalculation, without a break, though the walk took 211 s and the rides alone thousands.) The
  -- way with a ride at the least: its rides' times and its walks straight, never longer routed (Weighed). Not under the
  -- walk's time, the walk not past the guards (a ride can't win by them, HostileBetter): the walk, with none of the
  -- ride's walks routed; final once the walk is, and while it's still searched only when the rides lose by
  -- RIDE_CHECK_FAR_LOSS times (its line meanwhile may be short of the walk found)
  if walkSecs < math.huge and walkGuard < N.HOSTILE_RIDE_YD then
    local least = 0
    for _, leg in ipairs(legs) do
      least = least + (leg.ride and (leg.ride[7] or 0) or math.sqrt((leg.x2 - leg.x1) ^ 2 + (leg.y2 - leg.y1) ^ 2) / walk)
    end
    if least >= walkSecs * (lr.pending and N.RIDE_CHECK_FAR_LOSS or 1) then
      N.lastRideCheck = string.format("walk routed %.0fs (%.0f yd, %.0f past guards) vs with rides at least %.0fs: walk%s",
        walkSecs, lr.length, walkGuard, least, lr.pending and " (provisional, not remembered)" or "")
      return { won = false, final = not lr.pending, legs = legs, x = qx, y = qy }
    end
  end
  -- (its seconds, whether a walk on it is still being searched, and its yards past the other faction's guards)
  local function Time(plan, routes)
    local secs, pending, guard = 0, false, 0
    for li, leg in ipairs(plan) do
      if leg.ride then
        secs = secs + (leg.ride[7] or 0)
      elseif routes[li] then
        local g = Unwalkable(routes[li]) and 0 or N.HostileWalkYards(leg.cont, routes[li].pts)
        secs = secs + (Unwalkable(routes[li]) and math.huge
          or Weighed(leg.cont, routes[li].pts, walk, exempt, routes[li].blocked))
        guard = guard + g
        pending = pending or routes[li].pending
      end
    end
    return secs, pending, guard
  end
  local routes = WalkRoutes(legs, qx, qy, d, fixed, sz)
  local secs, pending, guard = Time(legs, routes)
  -- (a walk on it a long way round, N.WalkDetour, or past the other faction's guards (HOSTILE_RIDE_YD: the plan's walks
  -- are straight lines, and at level 20 the way with a ride walked through Dun Algaz to Thorium Point, 2026-11-14): left
  -- out of this plan, `avoid`, and the way with a ride planned again, up to NO_WALK_TRIES times and HOSTILE_TRIES more;
  -- the best kept. (With only NO_WALK_TRIES, the walks past guards used them up: at level 5 from Elwynn the plans past
  -- Dun Algaz and Stormwind were tried and the zeppelin from Grom'gol, 52 yd past them, never was; the route quality
  -- check, 2026-11-14)
  local avoid, try, tryRoutes, replanned = {}, legs, routes, false
  for _ = 1, N.NO_WALK_TRIES + N.HOSTILE_TRIES do
    local bad
    for li, leg in ipairs(try) do
      if not leg.ride and (N.WalkDetour(leg, tryRoutes[li], exempt) or (tryRoutes[li] and not Unwalkable(tryRoutes[li])
          and N.HostileWalkYards(leg.cont, tryRoutes[li].pts) >= N.HOSTILE_RIDE_YD)) then
        bad = leg
        break
      end
    end
    -- (none: the walk that came out longest past the plan's yards, NO_WALK_LONGER_YD or more, N.WalkLonger; off the
    -- roads too once past the first plan, `avoid` not empty)
    if not bad then
      local most = N.NO_WALK_LONGER_YD
      for li, leg in ipairs(try) do
        local extra = not leg.ride and N.WalkLonger(leg, tryRoutes[li], exempt, next(avoid) ~= nil) or 0
        if extra >= most then bad, most = leg, extra end
      end
    end
    if not bad then break end
    local c = avoid[bad.cont] or {}
    avoid[bad.cont] = c
    local from = N.NoWalkCell(bad.x1, bad.y1)
    c[from] = c[from] or {}
    c[from][N.NoWalkCell(bad.x2, bad.y2)] = true
    try = N.Plan(cont, qx, qy, walk, d, tps, math.huge, avoid)
    local rides = false
    for _, leg in ipairs(try or {}) do rides = rides or leg.ride ~= nil end
    if not rides then break end
    tryRoutes = WalkRoutes(try, qx, qy, d, fixed, sz)
    local s, p, g = Time(try, tryRoutes)
    pending = pending or p
    if N.HostileBetter(s, g, secs, guard) then legs, routes, secs, guard, replanned = try, tryRoutes, s, g, true end
  end
  pending = pending or (lr and lr.pending)
  local won = N.HostileBetter(secs, guard, walkSecs, walkGuard) or (secs == math.huge and walkSecs == math.huge) -- (neither: the plan's ride)
  -- (one way HOSTILE_RIDE_YD or more nearer the other faction's guards, and the safe one HOSTILE_SLOWER or more slower:
  -- the player's answer, N.riskOk; none yet, the safe way meanwhile and the question for the popup, `risk`)
  local risk
  local ridesSafe = secs < math.huge and guard + N.HOSTILE_RIDE_YD <= walkGuard
  local walkSafe = walkSecs < math.huge and walkGuard + N.HOSTILE_RIDE_YD <= guard
  if (ridesSafe or walkSafe) and won ~= ridesSafe then
    local ans = N.RiskAnswer(d)
    if ans == nil then
      won = ridesSafe
      local risky = ridesSafe and { parts = { { cont = cont, pts = lr.pts, kinds = lr.kinds } } } or PlanParts(legs, routes)
      local safe = ridesSafe and PlanParts(legs, routes) or { parts = { { cont = cont, pts = lr.pts, kinds = lr.kinds } } }
      risk = { key = N.RiskKey(d), towns = N.HostileOnRoute(risky), saved = math.abs(secs - walkSecs), ridesSafe = ridesSafe,
        safeRed = N.RedOnRoute(safe, sx, sy, cont), riskyRed = N.RedOnRoute(risky, sx, sy, cont) }
    else
      won = (ans and walkSafe) or (not ans and ridesSafe) or false
    end
  end
  N.lastRideCheck = string.format("walk routed %.0fs (%.0f yd, %.0f past guards) vs with rides %.0fs (%.0f past guards)%s: %s%s%s",
    walkSecs, lr and lr.length or 0, walkGuard, secs, guard, replanned and " (planned again past a long way round)" or "",
    won and "rides" or "walk", risk and " (the safe way, asking)" or "", pending and " (provisional, not remembered)" or "")
  return { won = won, final = not pending, legs = legs, x = qx, y = qy, replanned = replanned, risk = risk }
end

-- The ride check's own plan (CompareRide's, from its rounded spot) from (sx, sy): its first walk from there. Kept when
-- the ride won, never one with a teleport (a row of where the player stood then, and maybe not ready now).
local function Kept(res)
  if not res.won then return nil end
  for _, leg in ipairs(res.legs) do
    if leg.ride and leg.ride.use then return nil end
  end
  return res
end
-- (a plan's rides and where its walks go, to tell two plans apart)
local function PlanKey(legs)
  local out = {}
  for _, leg in ipairs(legs or {}) do
    out[#out + 1] = leg.ride and (tostring(leg.ride) .. ":" .. tostring(leg.from)) or tostring(N.NoWalkCell(leg.x2, leg.y2))
  end
  return table.concat(out, " ")
end
local function PlanFrom(res, sx, sy)
  local legs = {}
  for i, leg in ipairs(res.legs) do
    local c = {}
    for k, v in pairs(leg) do c[k] = v end
    if i == 1 and c.walk and c.x1 == res.x and c.y1 == res.y then c.x1, c.y1 = sx, sy end
    legs[i] = c
  end
  return legs
end

-- The walk planned the whole way, or the best way with a ride: its legs and their routes, or nil
-- (the walk). Compared in the background (Router.Background: a long walk and the ride's walks
-- routed in full were a tenth of a second and more in one frame, on every recalculation while the
-- searches were still running); meanwhile the plan's walk, and the route worked out again once the
-- comparison says ride. Remembered once final (not on provisional routes: a straight line while a
-- terrain search runs makes the walk look short).
local function RideInstead(cont, sx, sy, d, walk, tps, opts, sz)
  local legs = N.Plan(cont, sx, sy, walk, d, tps, math.huge)
  local rides = false
  for _, leg in ipairs(legs or {}) do rides = rides or leg.ride ~= nil end
  if not rides then return nil end
  local lvl = UnitLevel and UnitLevel("player")
  local key = string.format("%d:%d:%d:%s:%.0f:%.0f:%s", cont, math.floor(sx / N.RIDE_CHECK_YD), math.floor(sy / N.RIDE_CHECK_YD),
    tostring(d.cont), d.x, d.y, tostring(lvl))
  -- (meanwhile, crossing into another RIDE_CHECK_YD square: the last answer for this stop, not the
  -- plan's walk: that walked the whole way routed in the frame, then the ride again once compared)
  local stopKey = string.format("%s:%.0f:%.0f:%s", tostring(d.cont), d.x, d.y, tostring(lvl))
  local won = rideCheck[key]
  if won == nil then
    ridePending["ride:" .. key] = true
    local spot = rideSpot[key] or { sx, sy }
    rideSpot[key] = spot
    ns.Router.Background("ride:" .. key, function()
      return CompareRide(cont, spot[1], spot[2], d, walk, tps, opts, sz)
    end, function(res)
      ridePending["ride:" .. key] = nil
      if not res then return end
      -- (the safe way round the other faction's guards much slower: asked, N.CheckRedRoute)
      if res.risk and res.final and N.RiskAnswer(d) == nil then
        res.risk.stopKey = stopKey
        res.risk.plan = Kept({ won = true, legs = res.legs }) -- (the plan with the ride: kept for a "no" or a "yes")
        N.riskQuestion = res.risk
      end
      -- (the answer for now, provisional or not; remembered for this square only once final:
      -- else asked again on the next recalculation)
      local before = rideLast[stopKey] or false
      -- (a provisional answer, its walks still searched, never over a final one: asked 2026-11-16, the safe way shown
      -- with "Risk enemy territory?" up went to the walk past Dun Algaz a few seconds later, before any answer)
      if res.final or not rideFinal[stopKey] then rideLast[stopKey] = res.won end
      if res.final then rideFinal[stopKey] = true end
      if res.final then rideCheck[key], ridePlan[key] = res.won, Kept(res) end
      if res.final and res.won and ridePlan[key] then ridePlanLast[stopKey] = ridePlan[key] end
      -- (the other way, or the ride that won isn't the one the route has: the route worked out again)
      if res.won ~= before or (ridePlan[key] and PlanKey(ridePlan[key].legs) ~= PlanKey(legs)) then N.Invalidate(false) end
    end)
    won = rideCheck[key]
    if won == nil then won = rideLast[stopKey] end
  else
    -- (once: added on every recalculation, the 2026-11-18 capture's said it 60 times over)
    local said = N.lastRideCheck or ""
    if said:sub(-13) ~= " [remembered]" then N.lastRideCheck = said .. " [remembered]" end
  end
  if not won then return nil, nil, won end
  -- (the ride that won the check is the one taken: planned again past a long way round, or from the check's spot)
  -- (a square not checked yet: the stop's last plan with a ride, not the plan's own guess, which may be the walk;
  -- 2026-11-16, a step indoors at Tarren Mill and the route past Dun Algaz while the safe way was the answer)
  local plan = ridePlan[key] or ridePlanLast[stopKey]
  if plan then legs = PlanFrom(plan, sx, sy) end
  return legs, WalkRoutes(legs, sx, sy, d, opts, sz), true
end

-- A walk the plan took that isn't one (asked 2026-10-07: from Dolanaar the route to the boat at Rut'theran Village
-- walked straight down the side of Teldrassil, not by Darnassus's teleporter; the plan's walks are straight lines):
-- routed, its straight pieces off the roads (NO_WALK_PIECE_YD and longer) over ground the terrain blocks come to
-- NO_WALK_YD, or there's no way at all (`noWay`). Left out of the plan (N.noWalk) and the stretch planned again, up to
-- NO_WALK_TRIES times (left out, a walk past a dock to the same place was the next try's); the plan weighing least
-- kept, those yards at the router's cost.
N.NO_WALK_YD, N.NO_WALK_PIECE_YD, N.NO_WALK_TRIES = 600, 100, 3
-- Yards of a walk's drawn line, its straight pieces off the roads (NO_WALK_PIECE_YD and longer), the terrain blocks,
-- whether its searches are done or not (BlockedYards: only once they are).
function N.LineBlockedYards(cont, r)
  local P, R = ns.Passability, ns.Router
  if not (r and r.pts and r.kinds and P and P.SegmentCost and R) then return 0 end
  local yd, pts, looked = 0, r.pts, 0
  for i, k in ipairs(r.kinds) do
    if k == R.KIND_OFFROAD then
      local x1, y1, x2, y2 = pts[2 * i - 1], pts[2 * i], pts[2 * i + 1], pts[2 * i + 2]
      local dd = math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)
      if dd >= N.NO_WALK_PIECE_YD then
        looked = looked + 1
        if R.Breathe then R.Breathe(looked, 25) end -- (in a background job: long routes have hundreds of pieces)
        if not P.SegmentCost(cont, x1, y1, x2, y2) then yd = yd + dd end
      end
    end
  end
  return yd
end
function N.BlockedYards(cont, r)
  if not r then return 0 end
  if r.noWay then return math.huge end
  if r.pending then return 0 end
  return N.LineBlockedYards(cont, r)
end
-- A walk still being searched, judged by the line it's drawn as for now: NO_WALK_YD or more of it over blocked ground
-- is as good as blocked (else 0). Counted as nothing, it made every walk down the side of Teldrassil look clear while
-- its search ran: the planner left out the one already known blocked, planned the next walk down (to Rut'theran's
-- flight master, still searched), weighed the known one a second lighter, kept it for good, and the teleporter never
-- came up (the user, 2026-10-07: to Darkshore from Dolanaar, the route walked straight down the tree's side). Only
-- for the planning call it's made in (WithoutBlockedWalks): searched by the next, the walk is judged by what was found.
function N.ProvisionalBlockedYards(cont, r)
  if not (r and r.pending) then return 0 end
  local yd = N.LineBlockedYards(cont, r)
  return yd >= N.NO_WALK_YD and yd or 0
end
function N.PlanWeighed(legs, routes, walk, exempt)
  local secs = 0
  for li, leg in ipairs(legs) do
    if leg.ride then
      secs = secs + (leg.ride[7] or 0)
    elseif routes[li] then
      local b = math.max(N.BlockedYards(leg.cont, routes[li]), N.ProvisionalBlockedYards(leg.cont, routes[li]))
      if b == math.huge or Unwalkable(routes[li]) then return math.huge end
      secs = secs + Weighed(leg.cont, routes[li].pts, walk, exempt, math.max(b, routes[li].blocked or 0))
    end
  end
  return secs
end
-- (a walk left out with no better way found is put back and kept, N.walkKept: no plan again for it. Each recalculation
-- tried every way again, a route's work three times in the frame: 250 ms redraws in the overnight trip sweep,
-- 2026-10-07; and the walk stayed left out, so the plans after it settled for a worse one)
-- (and a walk to the stretch's stop kept so, every walk to that stop: ["*"][stop's cell]. The way to a stop out in the
-- sea off Azshara crosses 1,600 yd of water from any road; from each new flight master on the plan, it was planned
-- again three times at a recalculation, 250 ms in the frame. Left out entirely, a stop in Lake Mennar lost the better
-- way the plan without its last walk had, the overnight trip sweep, 2026-10-07)
N.walkKept = {}
function N.WalkKept(cont, x1, y1, x2, y2)
  local c = N.walkKept[cont]
  if not c then return false end
  local to = N.NoWalkCell(x2, y2)
  local from = c[N.NoWalkCell(x1, y1)]
  return (from and from[to]) or (c["*"] and c["*"][to]) or false
end
function N.WithoutBlockedWalks(cont, sx, sy, d, walk, tps, opts, sz, legs, routes, memo)
  local best, bestLegs, bestRoutes, bestAt, exempt
  local tried = {} -- { cont, from cell, to cell }: the walks left out here, in order
  memo = memo or {} -- (the walks routed for the plans here, the stretch's first plan's too: WalkRoutes')
  for _ = 1, N.NO_WALK_TRIES do
    local bad, provisional
    for li, leg in ipairs(legs) do
      if not leg.ride and not N.WalkKept(leg.cont, leg.x1, leg.y1, leg.x2, leg.y2) then
        if N.BlockedYards(leg.cont, routes[li]) >= N.NO_WALK_YD then
          bad = leg
          break
        elseif N.ProvisionalBlockedYards(leg.cont, routes[li]) > 0 then
          bad, provisional = leg, true
          break
        end
      end
    end
    if not bad then break end
    if not best then
      local Rt = ns.Router
      exempt = Rt and Rt.ZoneAt and { [Rt.ZoneAt(Geo.Base(cont), sx, sy)] = true,
        [Rt.ZoneAt(Geo.Base(d.cont), d.x, d.y)] = true } or nil
      best, bestLegs, bestRoutes, bestAt = N.PlanWeighed(legs, routes, walk, exempt), legs, routes, 0
    end
    local c = N.noWalk[bad.cont] or {}
    N.noWalk[bad.cont] = c
    local from, to = N.NoWalkCell(bad.x1, bad.y1), N.NoWalkCell(bad.x2, bad.y2)
    c[from] = c[from] or {}
    c[from][to] = true
    tried[#tried + 1] = { bad.cont, from, to, provisional = provisional }
    legs = N.Plan(cont, sx, sy, walk, d, tps)
    if not legs then break end
    routes = WalkRoutes(legs, sx, sy, d, opts, sz, memo)
    local w = N.PlanWeighed(legs, routes, walk, exempt)
    if w < best then best, bestLegs, bestRoutes, bestAt = w, legs, routes, #tried end
  end
  if not best then return legs, routes end
  -- (the walks left out after the best plan was found: put back, and kept)
  local function Keep(c, from, to)
    local k = N.walkKept[c] or {}
    N.walkKept[c] = k
    k[from] = k[from] or {}
    k[from][to] = true
  end
  for i = bestAt + 1, #tried do
    local t = tried[i]
    N.noWalk[t[1]][t[2]][t[3]] = nil
    if not t.provisional then Keep(t[1], t[2], t[3]) end -- (a walk judged while searched: never kept)
  end
  -- (and those left out for the best plan only while searched: put back, judged again once found, N.ProvisionalBlockedYards)
  for i = 1, bestAt do
    local t = tried[i]
    if t.provisional then N.noWalk[t[1]][t[2]][t[3]] = nil end
  end
  -- (the best plan still walking to the stop over blocked ground, no plan tried got round it, or its walk there still
  -- searched after one that was: every walk to the stop kept. Searched in the background, the walk there looked clear
  -- until found, and the trip was planned again a second time)
  local stopCell, sawStop = N.NoWalkCell(d.x, d.y), false
  -- (only walks known blocked: one left out while still searched says nothing yet, and counted it kept every walk to
  -- the stop, so the next call couldn't leave the walk straight there out and never reached Teldrassil's teleporter)
  for _, t in ipairs(tried) do sawStop = sawStop or (not t.provisional and t[1] == d.cont and t[3] == stopCell) end
  for li, leg in ipairs(bestLegs) do
    local r = bestRoutes[li]
    if not leg.ride and leg.cont == d.cont and leg.x2 == d.x and leg.y2 == d.y
        and (N.BlockedYards(leg.cont, r) >= N.NO_WALK_YD or (sawStop and r and r.pending)) then
      Keep(leg.cont, "*", stopCell)
    end
  end
  return bestLegs, bestRoutes
end

N.INTERIM_WALK_SHARE = 2
local function Stretch(cont, sx, sy, d, walk, opts, sz)
  -- from the player's position: the teleports ready now may start the trip
  local tps = opts.teleports -- the teleports this stretch may start with (AssignTeleports)
  local legs, planSecs = N.Plan(cont, sx, sy, walk, d, tps)
  if not legs then return nil end
  local routes
  -- (walk vs ride, both routed: when the plan walks all the way, and when it rides, not a teleport,
  -- on this continent: its straight lines can pick a ride that's slower, a walk round to a flight
  -- master far off; reported, Winterspring to Aldrassil at level 14)
  local rides = false
  for _, leg in ipairs(legs) do rides = rides or (leg.ride ~= nil and not leg.ride.use) end
  local check = math.sqrt((d.x - sx) ^ 2 + (d.y - sy) ^ 2) >= N.RIDE_CHECK_MIN_YD / N.WALK_FACTOR
  if not check and #legs == 1 and legs[1].walk and legs[1].cont == cont and d.cont == cont then
    routes = WalkRoutes(legs, sx, sy, d, opts, sz) -- (routed here, not later: RIDE_CHECK_FAR_YD)
    local r = routes[1]
    check = r and not r.pending and r.length >= N.RIDE_CHECK_FAR_YD or false
  end
  -- (and from down in a city on the stop's continent with a ride, N.CityStart: the rides weighed, not the walk)
  local city = rides and N.CityStart(cont, d)
  if ((#legs == 1 and legs[1].walk) or rides) and legs[1].cont == cont and (d.cont == cont or city) and check then
    local ride, rideRoutes, won = RideInstead(cont, sx, sy, d, walk, tps, opts, sz)
    if ride then
      legs, routes = ride, rideRoutes
    elseif won == false and rides and not city then -- (walking all the way wins)
      legs, routes = { { walk = true, cont = cont, x1 = sx, y1 = sy, x2 = d.x, y2 = d.y } }, nil
    elseif won == nil and rides and not city then
      -- (the ride check not done yet, and nothing it said for this stop: meanwhile the walk, routed, where there's a way
      -- on foot and it weighs (as the check weighs it) no more than INTERIM_WALK_SHARE times the plan's time; the ride
      -- once the check says so. Not the plan's ride, chosen by straight lines: reported 2026-11-14, level 20 from Tarren
      -- Mill to the Wetlands showed "fly to The Sepulcher, walk 13.1k yd" for half a minute, the straight walk there
      -- crossing the Arathi Highlands, too high, and the road there through them the way it took. A walk far longer
      -- than the plan's ride, Undercity to Hammerfall, keeps the ride meanwhile)
      local wl = { { walk = true, cont = cont, x1 = sx, y1 = sy, x2 = d.x, y2 = d.y } }
      local wr = WalkRoutes(wl, sx, sy, d, opts, sz)
      local Rt = ns.Router
      local exempt = Rt and Rt.ZoneAt and { [Rt.ZoneAt(Geo.Base(cont), sx, sy)] = true, [Rt.ZoneAt(Geo.Base(d.cont), d.x, d.y)] = true }
      if wr[1] and not Unwalkable(wr[1]) and not wr[1].noWay and wr[1].pts and planSecs
          and Weighed(cont, wr[1].pts, walk, exempt, wr[1].blocked) <= planSecs * N.INTERIM_WALK_SHARE then
        legs, routes = wl, wr
      end
    end
  end
  local memo = {}
  routes = routes or WalkRoutes(legs, sx, sy, d, opts, sz, memo)
  legs, routes = N.WithoutBlockedWalks(cont, sx, sy, d, walk, tps, opts, sz, legs, routes, memo)
  -- (a walk with no way there, the Router's `noWay`: a line through a wall or over blocked ground with
  -- no roads or walk round: none, "No way there found", rather than that line drawn; a broken road
  -- network drew one over the mountains from Ironforge, 2026-10-01)
  for li, leg in ipairs(legs) do
    local r = routes[li]
    -- (no way with a removed swim's water banned, or only a hop over it: that water swum after all, N.LiftSwimBans;
    -- planned again)
    if not leg.ride and r and not r.pending and not opts.lifted and (r.noWay or (r.blocked and N.SwimBanYards(leg.cont, r) > 0))
        and N.LiftSwimBans(leg.cont, leg.x1, leg.y1, leg.x2, leg.y2) then
      local o = {}
      for k, v in pairs(opts) do o[k] = v end
      o.lifted = true
      return Stretch(cont, sx, sy, d, walk, o, sz)
    end
    if not leg.ride and r and r.noWay then
      -- (none but up or down a cliff, the Router's `cliff`: said so, N.CLIFF_TEXT)
      if r.cliff then N.noWayCliff = true end
      return nil
    end
  end
  local st = { parts = {}, legs = legs, first = 0, walk = 0, ride = 0, road = 0 }
  local rode = false
  for li, leg in ipairs(legs) do
    if leg.ride then
      local t = leg.ride
      local c1, x1, y1, c2, x2, y2 = t[1], t[2], t[3], t[4], t[5], t[6]
      if leg.from == 2 then c1, x1, y1, c2, x2, y2 = t[4], t[5], t[6], t[1], t[2], t[3] end
      local bx, by = Geo.IntoAny(c2, x2, y2, c1) -- (onto an isle shown as an inset too: Zephras Isle's)
      if t.use then -- a teleport: nothing to draw
      elseif t.pts then -- a flight: through its connecting stops (one continent)
        local kinds = {}
        for k = 1, #t.pts / 2 - 1 do kinds[k] = N.KIND_TRANSPORT end
        -- (in the air over the continent: not on a city's level, from its flight master down in
        -- it, Undercity's; the map doesn't draw what's down in a city while the player is up top)
        st.parts[#st.parts + 1] = { cont = Geo.Base(c1), pts = t.pts, kinds = kinds }
      elseif bx then
        st.parts[#st.parts + 1] = { cont = Geo.Base(c1) == Geo.Base(c2) and c1 or Geo.Base(c1), pts = { x1, y1, bx, by },
          kinds = { N.KIND_TRANSPORT } }
      end
      st.ride = st.ride + t[7]
      rode = true
    else
      local lr = routes[li]
      st.parts[#st.parts + 1] = { cont = leg.cont, pts = lr.pts, kinds = lr.kinds, zs = lr.zs, fz = lr.fz, leg = leg,
        blocked = lr.blocked, unconnected = lr.unconnected }
      st.walk, st.road = st.walk + lr.length, st.road + lr.road
      if lr.pending then st.pending = true end
      leg.yards = lr.length
      if not rode then st.first = st.first + lr.length end
    end
  end
  return st
end

local later = {} -- the stretches between stops don't depend on the player: cached
local pairCosts, pairCount = {}, 0 -- OrderStops: planned seconds between two stops
N.ORDER_WALK_YD = 1200 -- OrderStops: stops closer than this are just walked (no plan needed)
local kept -- the last route, kept through Invalidate to compare a recalculation with

-- Following the route like a car GPS: while the player stays near the first part (the
-- walk from them), trim what's behind them and count the distances down, without
-- recalculating anything. False when they're off the route (then it's recalculated).
N.JOIN_REPICK_YD = 10 -- off the walk to the road by this much: it's worked out again
local function Follow(r, px, py, ahead)
  local full = r.fullFirst
  if not full then return false end
  local pts, kinds, cum = full.pts, full.kinds, r.cum
  local best, bi, bt
  local upTo = ahead and (r.consumed or 0) + ahead
  -- (in a building, the player's floor followed (N.TrackCityZ): not a stretch of the route on another floor, over or
  -- under them; Brill's inn, 2026-10-06: under a trainer upstairs, the route was trimmed to its last yards up there.
  -- Down in Undercity by the route's own heights, `zs`: a walkway over the ring)
  local fz = full.fz
  local floors = fz or full.zs
  local tz = floors and N.FollowedZ(full.cont)
  for i = r.followIdx, #pts / 2 - 1 do
    if upTo and cum[i] > upTo then break end -- (trimming only: the stretch just ahead)
    local ax, ay, bx, by = pts[2 * i - 1], pts[2 * i], pts[2 * i + 1], pts[2 * i + 2]
    local off = tz and floors[i] and floors[i + 1]
      and (tz < math.min(floors[i], floors[i + 1]) - N.SAME_FLOOR_Z or tz > math.max(floors[i], floors[i + 1]) + N.SAME_FLOOR_Z)
    if not off then
      local vx, vy = bx - ax, by - ay
      local L2 = vx * vx + vy * vy
      local t = 0
      if L2 > 0 then t = math.max(0, math.min(1, ((px - ax) * vx + (py - ay) * vy) / L2)) end
      local dx, dy = ax + vx * t - px, ay + vy * t - py
      local d2 = dx * dx + dy * dy
      if not best or d2 < best then best, bi, bt = d2, i, t end
    end
  end
  if not best or best > OFF_ROUTE_YD * OFF_ROUTE_YD then return false end
  -- still walking to the road and off that walk: worked out again from here, joining the road
  -- where it's heading from where the player is now (a nearer point on it may be better)
  if best > N.JOIN_REPICK_YD * N.JOIN_REPICK_YD then
    local R = ns.Router
    local toRoad, road = true, false
    for i = 1, #kinds do
      if i <= bi and kinds[i] ~= R.KIND_OFFROAD then toRoad = false break end
      if i > bi and kinds[i] == R.KIND_ROAD then road = true break end
    end
    if toRoad and road then return false end
  end
  local ax, ay, bx, by = pts[2 * bi - 1], pts[2 * bi], pts[2 * bi + 1], pts[2 * bi + 2]
  local qx, qy = ax + (bx - ax) * bt, ay + (by - ay) * bt
  local consumed = cum[bi] + (cum[bi + 1] - cum[bi]) * bt
  local np, nk = { qx, qy }, {}
  for i = bi, #pts / 2 - 1 do
    np[#np + 1], np[#np + 2] = pts[2 * i + 1], pts[2 * i + 2]
    nk[#nk + 1] = kinds[i]
  end
  local nz -- (a dungeon's floors: the points' heights, trimmed alike)
  local zs = full.zs
  if zs and zs[bi] and zs[bi + 1] then
    nz = { zs[bi] + (zs[bi + 1] - zs[bi]) * bt }
    for i = bi, #pts / 2 - 1 do nz[#nz + 1] = zs[i + 1] end
  end
  local nf -- (and a building's floors, alike)
  if fz and fz[bi] and fz[bi + 1] then
    nf = { fz[bi] + (fz[bi + 1] - fz[bi]) * bt }
    for i = bi, #pts / 2 - 1 do nf[#nf + 1] = fz[i + 1] end
  end
  local trimmed = { cont = full.cont, pts = np, kinds = nk, stop = full.stop, zs = nz, fz = nf, leg = full.leg }
  r.parts[1], r.pts, r.kinds = trimmed, np, nk
  r.followIdx, r.consumed = bi, consumed
  local b = r.base
  r.length = math.max(0, b.length - consumed)
  r.walkYards = math.max(0, b.walkYards - consumed)
  r.totalYards = math.max(0, b.totalYards - consumed)
  local swum = N.SwimYards(full, bi, bt) -- (the swims behind the player: N.TripSecs)
  r.swimYards = math.max(0, (b.swimYards or 0) - swum)
  r.totalSwim = math.max(0, (b.totalSwim or 0) - swum)
  return true
end

-- On a flight: the route is the flight to where it lands, then on from there. Nothing is
-- recalculated until landing; the flight's line shrinks from the player to the landing and
-- its time counts down. Taxi.lua knows where the flight lands (the flight master picked).
local flyingRest -- { key, st, at }: the route on from the landing, worked out once per flight (again while provisional)
-- (the walk on from the landing still searched, or none yet: worked out again every FLYING_REST_EVERY s; once it was
-- for the whole flight, a straight line's guess kept, "Walk 33m" for a 10m walk)
N.FLYING_REST_EVERY = 2

local function MasterNamed(name, node)
  -- (by its node id first, when the flight map gave it: Taxi.lua's toNode)
  local byNode = node and Masters()[node]
  if byNode then return byNode, node end
  if not name then return nil end
  -- (the flight being flown names them as the game does, in its language: Taxi.lua's TaxiNodeName)
  for node, m in pairs(Masters()) do
    if m[4] == name or m.en == name then return m, node end
  end
end

-- The flight's seconds from boarding to landing: learned, or the flight network's estimate.
local function FlightSeconds(from, to, fromNode, toNode)
  local cdb = ns.CharDB and ns.CharDB()
  local took = from and to and cdb and cdb.flights and cdb.flights[from .. " > " .. to]
  if took then return took.seconds end
  local _, a = MasterNamed(from, fromNode)
  local _, b = MasterNamed(to, toNode)
  local fl = a and b and Flights()
  local row = fl and fl.trips[a] and fl.trips[a][b]
  return row and row[7] - N.FLIGHT_OVERHEAD
end

-- On a flight from `from` to `to` (names), at (px, py), landing at L: the yards left along its path
-- (through the flight masters it stops over, Flights()' trip), and that path from the player on
-- ({ x, y, ... }). Without the trip: the straight line to the landing.
function N.FlightLeft(from, to, px, py, L, fromNode, toNode)
  local _, a = MasterNamed(from, fromNode)
  local _, b = MasterNamed(to, toNode)
  local fl = a and b and Flights()
  local trip = fl and fl.trips[a] and fl.trips[a][b]
  local p = trip and trip.pts
  if not (p and #p >= 4) then
    return math.sqrt((L[2] - px) ^ 2 + (L[3] - py) ^ 2), { px, py, L[2], L[3] }
  end
  -- (the leg the player is on: the one nearest them)
  local bi, bx, by, bd
  for i = 1, #p - 3, 2 do
    local ax, ay, vx, vy = p[i], p[i + 1], p[i + 2] - p[i], p[i + 3] - p[i + 1]
    local L2 = vx * vx + vy * vy
    local t = L2 > 0 and math.max(0, math.min(1, ((px - ax) * vx + (py - ay) * vy) / L2)) or 0
    local qx, qy = ax + vx * t, ay + vy * t
    local d = (qx - px) ^ 2 + (qy - py) ^ 2
    if not bd or d < bd then bi, bx, by, bd = i, qx, qy, d end
  end
  local left = math.sqrt((bx - px) ^ 2 + (by - py) ^ 2) + math.sqrt((p[bi + 2] - bx) ^ 2 + (p[bi + 3] - by) ^ 2)
  local path = { px, py }
  for i = bi + 2, #p - 1, 2 do
    path[#path + 1], path[#path + 2] = p[i], p[i + 1]
    if i + 3 <= #p then left = left + math.sqrt((p[i + 2] - p[i]) ^ 2 + (p[i + 3] - p[i + 1]) ^ 2) end
  end
  return left, path
end

-- The route while riding (a flight, a zeppelin, a boat): its leg from the player to where it lands L ({ cont, x, y }),
-- `secs` left, drawn along `path` (on `cont`), as `row`; then on from there to the stop and the stops after it, as
-- usual (worked out once per ride: `key`). `info`: the route's `flying` ({ to, seconds, verb, when }).
local function RideOn(px, py, cont, walk, offroad, L, key, path, secs, row, info, landZ)
  local d = N.dest
  local now = GetTime()
  if not flyingRest or flyingRest.key ~= key
      or ((not flyingRest.st or flyingRest.st.pending) and now - flyingRest.at >= N.FLYING_REST_EVERY) then
    local fixed = { offroad = offroad }
    -- (the landing's roads not built yet, Undercity's down in the city: built in the background meanwhile, the flight
    -- alone shown; worked out in the frame they took 0.8 s on boarding a flight there, 2026-11-15)
    local R = ns.Router
    local warming = R and R.WarmUp and R.GraphReady and ((not R.GraphReady(L[1]) and R.WarmUp(L[1], L[2], L[3]))
      or (d and d.cont and not R.GraphReady(d.cont) and R.WarmUp(d.cont, d.x, d.y)))
    local rest = not warming and Stretch(L[1], L[2], L[3], d, walk, { offroad = offroad, fixed = fixed }, landZ) or nil
    -- the stops after this one, as usual
    local laterSt = {}
    for i = 2, warming and 1 or N.PlannedStops() do
      local a = N.stops[i - 1]
      laterSt[i] = Stretch(a.cont, a.x, a.y, N.stops[i], walk, { offroad = offroad, fixed = fixed }, N.StopZ(a)) or false
    end
    flyingRest = { key = key, st = rest, later = laterSt, at = now }
  end
  -- (no way on from the landing worked out yet: the flight alone meanwhile, never the route as it was before boarding,
  -- its arrow pointing back along it)
  local rest = flyingRest.st or { parts = {}, legs = {}, walk = 0, ride = 0 }
  local flight = { cont = cont, pts = path, kinds = {}, stop = 1 }
  for k = 1, #path / 2 - 1 do flight.kinds[k] = N.KIND_TRANSPORT end
  local parts = { flight }
  for _, p in ipairs(rest.parts) do
    p.stop = 1
    parts[#parts + 1] = p
  end
  local legs = { { ride = row, from = 1 } }
  for _, leg in ipairs(rest.legs) do legs[#legs + 1] = leg end
  local first = { parts = parts, legs = legs, first = 0, walk = rest.walk, ride = secs + rest.ride, road = rest.road }
  local stretches = { first }
  local yards, ride = rest.walk, secs + rest.ride
  for i = 2, N.PlannedStops() do
    local st = flyingRest.later[i]
    stretches[i] = st
    if st then
      for _, p in ipairs(st.parts) do
        p.stop = i
        parts[#parts + 1] = p
      end
      yards, ride = yards + st.walk, ride + st.ride
    end
  end
  info.seconds = secs
  local r = {
    pts = flight.pts, kinds = flight.kinds, road = rest.road, length = 0,
    walkYards = rest.walk, rideSeconds = secs + rest.ride, extraSeconds = secs + rest.ride,
    totalYards = yards, totalRide = ride, parts = parts, legs = legs, stretches = stretches,
    flying = info, version = version, offroad = offroad, cont = cont,
  }
  SetSwim(r)
  return r
end

function N.FlyingRoute(px, py, cont, walk, offroad, f)
  local land = MasterNamed(f.to, f.toNode)
  -- (a city's level counts as its continent: the bat out of Undercity flies through the city and its
  -- sewers on Undercity's map, and the route went back to the flight master there, a video 2026-10-02)
  cont = Geo.Base(cont)
  -- (landing on a city's level, Undercity's flight master down in the city: flown over its continent; reported
  -- 2026-11-15, a flight to Undercity off the route's way kept the route, its arrow pointing back along it)
  if not land or Geo.Base(land[1]) ~= cont then return nil end
  -- time left in the air: the planned flight time counting down, at least the distance left
  -- along the flight's path at flight speed (N.FlightLeft: through its stops on the way; a
  -- straight line to the landing held a flight with stops up, reported 2026-10-01)
  local left, path = N.FlightLeft(f.from, f.to, px, py, land, f.fromNode, f.toNode)
  local secs = left / N.FLIGHT_SPEED
  local total = FlightSeconds(f.from, f.to, f.fromNode, f.toNode)
  if total then secs = math.max(secs, total - (GetTime() - f.start)) end
  local row = { cont, px, py, land[1], land[2], land[3], secs, "flight", f.from or "?", f.to, "flight master", flying = true }
  return RideOn(px, py, cont, walk, offroad, land, version .. ":" .. f.to .. ":" .. tostring(offroad), path, secs, row,
    { to = f.to, kind = "flight" })
end

-- What the player is riding, for the directions (`kind`: the route's `flying.kind`): "Flying to %s", and when it lands
N.RIDING_TO = { flight = L["Flying to %s"], boat = L["Riding the boat to %s"], zeppelin = L["Riding the zeppelin to %s"],
  tram = L["Riding the Deeprun Tram to %s"] }
N.RIDING_WHEN = { flight = L["lands in %s"], boat = L["arrives in %s"], zeppelin = L["arrives in %s"], tram = L["arrives in %s"] }
function N.RidingText(kind, to)
  return Format(N.RIDING_TO[kind] or N.RIDING_TO.flight, tostring(to))
end
function N.RidingWhen(kind, seconds)
  return Format(N.RIDING_WHEN[kind] or N.RIDING_WHEN.flight, N.FormatTime(seconds))
end

-- On a zeppelin or a boat (Taxi.CurrentRide, asked 2026-10-02: as on a flight): the ride to its other dock, the time
-- left by its timetable ("arrives in"), then on from the dock; the route isn't worked out again until off it. Across
-- continents (the zeppelin to Durotar) the line to the dock isn't drawn: the dock is on the other map.
function N.RidingRoute(px, py, cont, walk, offroad, ride)
  local dock = ride.dock
  if not (dock and dock[1]) then return nil end
  cont = Geo.Base(cont)
  local here = dock[1] == cont
  local path = here and { px, py, dock[2], dock[3] } or { dock[2], dock[3], dock[2], dock[3] }
  local secs = math.max(0, ride.left or 0)
  local row = { here and cont or dock[1], here and px or dock[2], here and py or dock[3], dock[1], dock[2], dock[3], secs,
    ride.kind, ride.from or "?", ride.to, ride.kind, flying = true }
  return RideOn(px, py, here and cont or dock[1], walk, offroad, dock,
    version .. ":ride:" .. tostring(ride.to) .. ":" .. tostring(offroad), path, secs, row,
    { to = ride.to, kind = ride.kind == "boat" and "boat" or "zeppelin" })
end

-- In the Deeprun Tram (asked 2026-11-15, a player's report: inside it the route was worked out again from the tram's
-- own map, where the only way out is a teleport: "Teleport: Ironforge, walk to the flight master, fly to Stormwind"):
-- followed as a flight is. Its map is a level of its own (Data/Transit.lua's 20369, base 369: N.PlayerLevel gives the
-- level, so the old `cont == N.TRAM_MAP` never matched). The ride to its other end (the end away from where the player
-- was last seen outside it, N.lastOutside; else the one nearer the stop), "arrives in" from Data/Transports.lua's time,
-- then on from there; nothing worked out again until out of it.
N.TRAM_ENTRY_SECONDS = 180 -- (seen outside this long before: the end walked in from)
N.TRAM_OUT_SECONDS = 30 -- (in it this long before: just come out at a way in, on its floor)
function N.InTram(level)
  local l = ns.CityLevels and ns.CityLevels[level]
  return level == N.TRAM_MAP or (l ~= nil and l.base == N.TRAM_MAP)
end
function N.TramRoute(px, py, offroad)
  local row
  for _, t in ipairs(ns.Transports or {}) do
    if t[8] == "tram" then row = t break end
  end
  local d = N.dest
  if not (row and d) then return nil end
  local now = GetTime()
  local ride = N.tramRide
  if not ride then
    local o, toEnd = N.lastOutside, nil
    if o and now - o.at < N.TRAM_ENTRY_SECONDS then
      local a = (o.x - row[2]) ^ 2 + (o.y - row[3]) ^ 2
      local b = (o.x - row[5]) ^ 2 + (o.y - row[6]) ^ 2
      toEnd = a < b and 2 or 1
    else -- (after a /reload in it: the end nearer the stop)
      local a = (d.x - row[2]) ^ 2 + (d.y - row[3]) ^ 2
      local b = (d.x - row[5]) ^ 2 + (d.y - row[6]) ^ 2
      toEnd = a <= b and 1 or 2
    end
    ride = { to = toEnd, at = now }
    N.tramRide = ride
  end
  local e = ride.to
  local dock = e == 1 and { row[1], row[2], row[3] } or { row[4], row[5], row[6] }
  local name, from = row[e == 1 and 9 or 10], row[e == 1 and 10 or 9]
  local secs = math.max(0, (row[7] or 0) - (now - ride.at))
  local _, walk = N.Speeds()
  local trip = { dock[1], dock[2], dock[3], dock[1], dock[2], dock[3], secs, "tram", from, name, "tram", flying = true }
  return RideOn(px, py, dock[1], walk, offroad, dock, version .. ":tram:" .. e .. ":" .. tostring(offroad),
    { dock[2], dock[3], dock[2], dock[3] }, secs, trip, { to = name, kind = "tram" }, EndZ(row, e))
end

-- The stretches between stops are worked out a few per call (N.LATER_PER_CALL), the rest on
-- the next frames: a new route with many stops doesn't stall one frame. Until then the
-- route shows the ones done (and after Invalidate, the previous ones: later.done is reset,
-- the stretches themselves stay until replaced).
N.LATER_PER_CALL = 1

local function LaterMissing()
  if not later.key then return false end
  for i = 2, N.PlannedStops() do
    if not later.done or not later.done[i] then return true end
  end
  return false
end

-- Teleports (hearthstone, Astral Recall, mage teleports) ready now, from (x, y), limited
-- to the names in `only` ({ [name] = true }).
local function TeleportsFrom(cont, x, y, only)
  local out = {}
  if not only or not ns.Teleports then return out end
  for _, row in ipairs(ns.Teleports.Available(cont, x, y)) do
    if only[row[8]] then out[#out + 1] = row end
  end
  return out
end

-- The teleport the fastest plan from (x, y) to stop d starts with, and the seconds it
-- saves over the plan without teleports; nil when none helps.
local function TeleportGain(cont, x, y, d, walk, tps)
  if not tps or not tps[1] then return nil end
  local legs, with = N.Plan(cont, x, y, walk, d, tps)
  for _, leg in ipairs(legs or {}) do
    if leg.ride and leg.ride.use then
      local _, without = N.Plan(cont, x, y, walk, d)
      return leg.ride[8], (without or math.huge) - with
    end
  end
end

-- Each teleport is used once per trip, on the stretch where it saves the most: from the
-- player to the next stop, or from one stop to the next (e.g. hearthing from the last
-- stop but one when the trip ends near home). The gains between stops are worked out once
-- per route (and when the teleports ready change); the player's stretch every
-- recalculation. Sets later.tp[i] (the teleport stretch i may use; the stretch is redone
-- when that changes) and returns the teleports for the player's stretch.
-- (only when it saves more than TELEPORT_MIN_YD of walking: a hearthstone's hour-long cooldown
-- isn't worth a few hundred yards)
N.TELEPORT_MIN_YD = 800
local function AssignTeleports(cont, px, py, d, walk)
  local T = ns.Teleports
  if not T or N.loop or N.corpse then return nil end
  local tps = T.Available(cont, px, py)
  local names = {}
  for _, row in ipairs(tps) do names[#names + 1] = row[8] end
  local sig = table.concat(names, "|")
  if later.tpSig ~= sig and not (N.degraded and later.gains) then -- (cut back to the first stop: kept)
    later.tpSig, later.gains = sig, {}
    for i = 2, sig ~= "" and N.PlannedStops() or 1 do
      local a = N.stops[i - 1]
      local name, gain = TeleportGain(a.cont, a.x, a.y, N.stops[i], walk, T.Available(a.cont, a.x, a.y))
      later.gains[i] = name and { name, gain } or false
    end
  end
  local best = {} -- [name] = { stretch, seconds saved }
  local n1, g1 = TeleportGain(cont, px, py, d, walk, tps)
  local minGain = N.TELEPORT_MIN_YD / walk
  if n1 and g1 > minGain then best[n1] = { 1, g1 } end
  for i = 2, N.PlannedStops() do
    local g = later.gains[i]
    if g and g[2] > minGain and (not best[g[1]] or g[2] > best[g[1]][2]) then best[g[1]] = { i, g[2] } end
  end
  later.tp = later.tp or {}
  for i = 2, N.PlannedStops() do
    local want
    for name, b in pairs(best) do
      if b[1] == i then want = name end
    end
    if later.tp[i] ~= want then
      later.tp[i] = want
      if later.done then later.done[i] = nil end
    end
  end
  local out = {}
  for _, row in ipairs(tps) do
    if best[row[8]] and best[row[8]][1] == 1 then out[#out + 1] = row end
  end
  return out
end

-- Work out up to `budget` stretches between stops still to do (in order).
local function FillLater(walk, offroad, budget)
  later.done = later.done or {}
  for i = 2, N.PlannedStops() do
    if budget <= 0 then break end
    if not later.done[i] then
      local a = N.stops[i - 1]
      local opts = { offroad = offroad }
      opts.fixed = { offroad = offroad }
      if later.tp and later.tp[i] then opts.teleports = TeleportsFrom(a.cont, a.x, a.y, { [later.tp[i]] = true }) end
      later[i] = Stretch(a.cont, a.x, a.y, N.stops[i], walk, opts, N.StopZ(a)) or false
      later.done[i] = true
      budget = budget - 1
    end
  end
end

-- The route from the player's stretch (`first`, worked out at (px, py)) and the stretches
-- between stops worked out so far.
local function Assemble(first, px, py, cont, walk, offroad)
  local parts, stretches = {}, { first }
  for i = 2, N.PlannedStops() do stretches[i] = later[i] end
  -- each part knows which stop it leads to (drawn in that stop's marker color)
  for _, p in ipairs(first.parts) do
    p.stop = 1
    parts[#parts + 1] = p
  end
  local yards, ride = first.walk, first.ride
  for i = 2, N.PlannedStops() do
    local st = later[i]
    if st then
      for _, p in ipairs(st.parts) do
        p.stop = i
        parts[#parts + 1] = p
      end
      yards, ride = yards + st.walk, ride + st.ride
    end
  end
  local p1 = first.parts[1]
  local r = {
    pts = p1 and p1.pts or { px, py }, kinds = p1 and p1.kinds or {}, road = first.road,
    length = first.first, walkYards = first.walk, rideSeconds = first.ride,
    extraSeconds = first.ride + (first.walk - first.first) / walk,
    totalYards = yards, totalRide = ride, parts = parts, legs = first.legs, stretches = stretches,
  }
  -- for following: the first part (the walk from the player) and its running lengths
  r.version, r.offroad, r.cont, r.pending, r.firstStretch = version, offroad, cont, first.pending, first
  SetSwim(r)
  r.base = { length = r.length, walkYards = r.walkYards, totalYards = r.totalYards, swimYards = r.swimYards,
    totalSwim = r.totalSwim }
  r.followIdx, r.consumed = 1, 0
  if p1 and first.legs[1] and first.legs[1].walk then
    r.fullFirst = p1
    local cum, pts = { 0 }, p1.pts
    for i = 2, #pts / 2 do
      cum[i] = cum[i - 1] + math.sqrt((pts[2 * i - 1] - pts[2 * i - 3]) ^ 2 + (pts[2 * i] - pts[2 * i - 2]) ^ 2)
    end
    r.cum = cum
  end
  return r
end

-- Current route from (px, py) through every stop, recomputed every few seconds or after
-- moving a bit. route.parts = { { cont, pts, kinds }, ... } in each part's own continent
-- coordinates (drawing converts them via the world map); route.pts/kinds are the first
-- part (from the player). To the next stop: route.length = yards before any transport,
-- route.walkYards, route.rideSeconds; to the last stop: route.totalYards, route.totalRide.
-- The level the player routes on: an underground city's (the game says we're on its map)
-- or the continent. Checked every half second.
local levelAt, levelCache = -math.huge, nil

-- The underground city the player is down in right now (its level id), or nil; false when
-- the game doesn't say where the player is (loading).
function N.CityHere()
  local o = ns.Geo.override -- (the dev tools' simulated player: the level it was put on)
  if o then
    local l = o.level and ns.CityLevels and ns.CityLevels[o.level]
    return (l and not l.instance) and o.level or nil
  end
  local map = C_Map and C_Map.GetBestMapForUnit and C_Map.GetBestMapForUnit("player")
  if not map then return false end
  for id, l in pairs(ns.CityLevels or {}) do
    if l.map == map then
      -- (the halls at the lifts' tops report the city's map too, but they're up top)
      local sub = GetSubZoneText and GetSubZoneText()
      local mini = GetMinimapZoneText and GetMinimapZoneText()
      -- (the zone text is the client's language, "Ruinen von Lordaeron": `upper`'s names are the English ones)
      local up = false
      for en in pairs(l.upper or {}) do
        if ns.IsPlaceNamed(en, sub) or ns.IsPlaceNamed(en, mini) then up = true break end
      end
      if not up then return id end
    end
  end
  return nil
end

-- Boss kills (a dungeon's boss route: a boss's stop is done when it dies, not when you get
-- there). Kept per character for the instance they're in: { level, at = time(), npcs = { [npc]
-- = true } }, started over in another instance or BOSS_KILL_HOURS after the last kill.
N.BOSS_KILL_HOURS = 3
N.BOSS_NEAR_YD = 40 -- this close to a boss's stop: "Defeat <boss>"

local function Kills()
  local cdb = ns.CharDB and ns.db and ns.CharDB()
  if not cdb then
    N.kills = N.kills or {}
    return N.kills
  end
  cdb.bossKills = cdb.bossKills or {}
  return cdb.bossKills
end

-- The instance level the player is in (GetInstanceInfo's map), or nil.
function N.CurrentInstance()
  if not GetInstanceInfo then return nil end
  local ok, _, kind, _, _, _, _, _, mapID = pcall(GetInstanceInfo)
  if not ok or (kind ~= "party" and kind ~= "raid") then return nil end
  return N.InstanceLevel(mapID)
end

-- A boss's key in the kills: its NPC entry, or its name (WoW Forever's own dungeons: no entry).
function N.BossKey(b) return (b[2] and b[2] ~= 0) and b[2] or b[1] end

-- The bosses of instance level `lvl` matching a kill: by NPC entry, DungeonEncounter id or
-- name. Returns how many were marked dead.
function N.BossKilled(lvl, npc, encounter, name)
  local info = lvl and ns.Instances and ns.Instances[lvl]
  if not info then return 0 end
  local k = Kills()
  local now = time and time() or 0
  if k.level ~= lvl or (k.at and now - k.at > N.BOSS_KILL_HOURS * 3600) then
    k.level, k.npcs = lvl, {}
  end
  k.at = now
  local n = 0
  for _, b in ipairs(info.bosses or {}) do
    local hit = (npc and b[2] == npc) or (name and b[1] == name)
    for _, e in ipairs(encounter and b.enc or {}) do
      if e == encounter then hit = true end
    end
    local key = N.BossKey(b)
    if hit and not k.npcs[key] then
      k.npcs[key] = true
      n = n + 1
    end
  end
  return n
end

-- A boss of instance level `lvl` (its key, N.BossKey) marked defeated or not by hand (right-click its icon on the
-- dungeon's map): the game may not tell addons who died (asked 2026-10-01: Rhahk'Zor dead, looted, still "Next").
function N.SetBossDead(lvl, key, dead)
  local k = Kills()
  local now = time and time() or 0
  if k.level ~= lvl or (k.at and now - k.at > N.BOSS_KILL_HOURS * 3600) then
    k.level, k.npcs = lvl, {}
  end
  k.at = now
  k.npcs[key] = dead and true or nil
end

-- Whether boss stop `d` ({ cont = its level, boss = its NPC entry }) is dead.
function N.BossDead(d)
  local k = Kills()
  if not (d.boss and k.level == d.cont and k.npcs) then return false end
  if k.at and (time and time() or 0) - k.at > N.BOSS_KILL_HOURS * 3600 then return false end
  return k.npcs[d.boss] == true
end

-- A creature's NPC entry from its GUID ("Creature-0-server-instance-zone-npc-spawn").
function N.NpcOf(guid)
  if type(guid) ~= "string" then return nil end
  local kind, npc = guid:match("^(%a+)%-%d+%-%d+%-%d+%-%d+%-(%d+)%-")
  if kind ~= "Creature" and kind ~= "Vehicle" then return nil end
  return tonumber(npc)
end

-- The level of an instance map (Data/Instances.lua: LEVEL_BASE + its MapID, base = the map),
-- or nil: in a dungeon, the game reports its map as the player's continent.
local instanceOf
function N.InstanceLevel(cont)
  if not instanceOf then
    instanceOf = {}
    for id, l in pairs(ns.CityLevels or {}) do
      if l.instance then instanceOf[l.base] = id end
    end
  end
  return cont and instanceOf[cont]
end

-- (the player put somewhere else: Geo.SetOverride; the level worked out again at once)
function N.ForgetLevel() levelAt = -math.huge end
function N.PlayerLevel(cont)
  if not ns.CityLevels or not cont then return cont end
  local inst = N.InstanceLevel(cont)
  if inst then return inst end
  local now = GetTime()
  if now - levelAt > 0.5 or now < levelAt then -- (or the clock went back: a cache from the future never expired)
    levelAt, levelCache = now, N.CityHere() or nil
  end
  if levelCache and (levelCache == cont or ns.CityLevels[levelCache].base == cont) then return levelCache end
  return cont
end

-- The level of a new stop at (x, y) on `cont`: the city's when the player is down in it and
-- the spot is on its floors, else the continent. (Its floors: a height there, not only open
-- cells: a trainer at a ledge's edge or in a booth is a yard from closed ones.)
function N.StopLevel(cont, x, y)
  local lvl = N.PlayerLevel(cont)
  if lvl == cont then return cont end
  local P = ns.Passability
  if (P and P.IsOpen and P.IsOpen(lvl, x, y)) or (N.CityHeight and N.CityHeight(lvl, x, y)) then return lvl end
  return cont
end

local Apply, Rejoin
-- The jobs of a reroute off the route (N.Route): while one is queued, the pump's bigger slices (GPS.PumpBudget), so the
-- route from where the player went lands in a few frames, not the 1 ms a frame of a route being kept up.
local hurried
function N.Rerouting()
  local R = ns.Router
  for _, key in ipairs(hurried or {}) do
    if R.Queued and R.Queued(key) then return true end
  end
  hurried = nil
  return false
end
-- The route from (px, py) worked out: the stretch to the next stop and those after it (a few more
-- each call), assembled; nil when there's no way.
local function Compute(px, py, cont, d, offroad)
  local _, walk = N.Speeds()
  local key = version .. ":" .. tostring(offroad)
  if later.key ~= key then later = { key = key, done = {} } end
  local tps = AssignTeleports(cont, px, py, d, walk)
  if ns.Router.Breathe then ns.Router.Breathe(1, 1) end -- (in a background job: a pause between the parts)
  local t1 = ns.PerfStart and ns.PerfStart()
  N.noWayCliff = nil -- (set again by the stretches: no way but a cliff)
  local first = Stretch(cont, px, py, d, walk, { offroad = offroad, transient = true, fixed = { offroad = offroad },
    teleports = tps, indoors = N.Indoors(), swimming = N.Swimming(),
    z = N.PlayerZ() or N.TrackCityZ(cont, px, py) or N.TrackRaisedZ(cont, px, py) })
  if t1 then ns.PerfEnd("route calculation: next stop", t1) end
  if not first then return nil end
  if ns.Router.Breathe then ns.Router.Breathe(1, 1) end
  -- (routing cut back to the first stop, N.degraded: the stretches after it kept as they are)
  if not N.degraded then
    local t2 = ns.PerfStart and ns.PerfStart()
    FillLater(walk, offroad, N.LATER_PER_CALL)
    if t2 then ns.PerfEnd("route calculation: later stops", t2) end
  end
  return Assemble(first, px, py, cont, walk, offroad)
end

-- `new` (worked out at (px, py)) as the route; but `old`, when the player is still on it and `new`
-- is clearly longer (KeepOld).
function Apply(new, old, px, py, cont, offroad, now, trim)
  local _, walk = N.Speeds()
  if old and new and old ~= new and N.KeepOld(old, new, walk, now) and Follow(old, px, py) then
    old.keptSince = old.keptSince or now
    new = old
  elseif new then
    new.keptSince = nil
    if trim then Follow(new, px, py) end -- (worked out a moment ago, in the background: from where the player is now)
  end
  N.route, kept = new, new
  N.warming = nil
  N.routeX, N.routeY, N.routeTime, N.routeOffroad, N.routeCont = px, py, now, offroad, cont
  N.trimX, N.trimY = px, py
  N.CheckRedRoute(px, py, cont, now)
  return new
end

-- Off a long walk from the player: back onto it a little ahead of the nearest point (REJOIN_AHEAD_YD),
-- a short way routed from the player, the rest of the walk and the route after it as they were.
-- nil when it doesn't fit (too far off, a city's floors, near the walk's end).
N.REJOIN_MIN_YD = 1500 -- a walk from the player this long left: rejoined, worked out again in the background
N.REJOIN_MAX_OFF_YD = 250
N.REJOIN_AHEAD_YD = 60
function Rejoin(old, px, py, cont, offroad)
  local full, f0 = old.fullFirst, old.firstStretch
  if not (full and f0 and old.cum) or full.zs or Geo.Base(full.cont) ~= Geo.Base(cont) then return nil end
  local pts, cum = full.pts, old.cum
  local best, bi, bt
  for i = old.followIdx or 1, #pts / 2 - 1 do
    local ax, ay, bx, by = pts[2 * i - 1], pts[2 * i], pts[2 * i + 1], pts[2 * i + 2]
    local vx, vy = bx - ax, by - ay
    local L2 = vx * vx + vy * vy
    local t = L2 > 0 and math.max(0, math.min(1, ((px - ax) * vx + (py - ay) * vy) / L2)) or 0
    local d2 = (ax + vx * t - px) ^ 2 + (ay + vy * t - py) ^ 2
    if not best or d2 < best then best, bi, bt = d2, i, t end
  end
  if not best or best > N.REJOIN_MAX_OFF_YD ^ 2 then return nil end
  local total = cum[#cum]
  local along = cum[bi] + (cum[bi + 1] - cum[bi]) * bt + N.REJOIN_AHEAD_YD
  if along >= total - N.REJOIN_AHEAD_YD then return nil end
  local j = bi
  while cum[j + 1] < along do j = j + 1 end
  local f = (along - cum[j]) / math.max(cum[j + 1] - cum[j], 1e-6)
  local tx, ty = pts[2 * j - 1] + (pts[2 * j + 1] - pts[2 * j - 1]) * f, pts[2 * j] + (pts[2 * j + 2] - pts[2 * j]) * f
  local lr = ns.Router.Route(full.cont, px, py, tx, ty, { offroad = offroad, transient = true })
  if not lr or Unwalkable(lr) then return nil end
  local np, nk = {}, {}
  for k = 1, #lr.pts do np[k] = lr.pts[k] end
  for k = 1, #lr.kinds do nk[k] = lr.kinds[k] end
  nk[#nk + 1] = full.kinds[j] -- (on from the way back on along the walk)
  -- (the floors, a building's or a capital's at the walk's end: the way back on's own, else the walk's next)
  local fz, nf = full.fz, nil
  if fz then
    nf = {}
    for k = 1, #lr.pts / 2 do nf[k] = lr.fz and lr.fz[k] or fz[j + 1] end
  end
  for k = j + 1, #pts / 2 do
    np[#np + 1], np[#np + 2] = pts[2 * k - 1], pts[2 * k]
    if nf then nf[#nf + 1] = fz[k] end
    if k < #pts / 2 then nk[#nk + 1] = full.kinds[k] end
  end
  local newLen = lr.length + (total - along)
  local legs, l1 = {}, {}
  for k, v in pairs(f0.legs[1]) do l1[k] = v end
  l1.yards = newLen
  for k, leg in ipairs(f0.legs) do legs[k] = k == 1 and l1 or leg end
  local part = { cont = full.cont, pts = np, kinds = nk, fz = nf, leg = l1, stop = full.stop }
  local parts = { part }
  for k = 2, #f0.parts do parts[k] = f0.parts[k] end
  local first = { parts = parts, legs = legs, first = f0.first - total + newLen, walk = f0.walk - total + newLen,
    ride = f0.ride, road = f0.road, pending = lr.pending or f0.pending }
  local _, walk = N.Speeds()
  return Assemble(first, px, py, cont, walk, offroad)
end

-- In a city, the floor under the player changing height at a stroke (jumped down, or
-- back up top): worked out again from there (a drop may be the way again).
N.FLOOR_JUMP = 5
N.FLOOR_JUMP_EVERY = 4 -- seconds, at most (walking along a ledge's foot flickers)
local lastFloor, floorJumpAt = nil, -math.huge
function N.Route(px, py, cont)
  -- (routing paused, N.SetPaused: nothing worked out, nothing drawn; the stops kept)
  if N.paused then
    N.route = nil
    return nil
  end
  N.SyncSwim() -- (swimming allowed or left out: the option, the trip's)
  cont = N.PlayerLevel(cont)
  N.playerX, N.playerY = px, py
  local d = N.dest
  if not d then return nil end
  if ns.CityLevels and ns.CityLevels[cont] and px and N.CityHeight then
    -- (the player's own height when the game gives it, else the floor followed along the roads (N.TrackCityZ): the
    -- floor's under them can be a walkway over their head, and they didn't jump up to it)
    local tz = N.TrackCityZ(cont, px, py)
    local zoff = ns.CityLevels[cont].zoff
    local h = N.PlayerCityZ(cont) or (tz and zoff and tz - zoff) or N.CityHeight(cont, px, py)
    if h and lastFloor and math.abs(h - lastFloor) >= N.FLOOR_JUMP and GetTime() - floorJumpAt >= N.FLOOR_JUMP_EVERY then
      floorJumpAt = GetTime()
      kept = nil
      N.Invalidate(false) -- (just the way to the next stop)
    end
    lastFloor = h or lastFloor
  else
    lastFloor = nil
  end
  if N.QuestPaused() then return N.route end -- in the stop's quest area, spot reached: waits
  local now = GetTime()
  local r = N.route
  -- (roads always: the route joins them where they're heading, from wherever the player is;
  -- Router's JOIN_ALONG. The offroad option is gone from 1.0.8.)
  local offroad = false
  -- on a flight: the flight, then on from where it lands; no rerouting until then
  local f = ns.Taxi and ns.Taxi.Current and ns.Taxi.Current()
  if f then
    if f.to then
      local _, walkSpeed = N.Speeds()
      local fr = N.FlyingRoute(px, py, cont, walkSpeed, offroad, f)
      if fr then
        N.route, kept = fr, fr
        N.routeX, N.routeY, N.routeTime, N.routeOffroad, N.routeCont = px, py, now, offroad, cont
        return fr
      end
    end
    if r then return r end -- flying somewhere we can't tell (e.g. after a reload): keep the route
  end
  -- in the Deeprun Tram (its own map): the ride to its other end, as a flight (N.TramRoute); nothing worked out again
  -- until out of it
  if N.InTram(cont) then
    N.tramAt = now
    local tr = N.TramRoute(px, py, offroad)
    if tr then
      N.route, kept = tr, tr
      N.routeX, N.routeY, N.routeTime, N.routeOffroad, N.routeCont = px, py, now, offroad, cont
      return tr
    end
    return r
  end
  N.tramRide = nil
  if px then N.lastOutside = { x = px, y = py, at = now } end
  -- on a boat or a zeppelin, its departure seen (Taxi.CurrentRide): the ride, then on from its other dock
  local ride = ns.Taxi and ns.Taxi.CurrentRide and ns.Taxi.CurrentRide()
  if ride then
    local _, walkSpeed = N.Speeds()
    local rr = N.RidingRoute(px, py, cont, walkSpeed, offroad, ride)
    if rr then
      N.route, kept = rr, rr
      N.routeX, N.routeY, N.routeTime, N.routeOffroad, N.routeCont = px, py, now, offroad, cont
      return rr
    end
  end
  -- (on one whose departure wasn't seen, Taxi.Riding: the route as it is, not worked out again until off it)
  if ns.Taxi and ns.Taxi.Riding and ns.Taxi.Riding() then return r or kept end
  if r and r.flying then r, kept = nil, nil end -- just landed: work the route out afresh
  -- the continent's road data is still being built in the background (a moment)
  -- (and the levels the stops are on: a city's, down a lift)
  if not r and ns.Router.WarmUp then
    local busy = ns.Router.WarmUp(cont, px, py)
    for _, s in ipairs(N.stops) do
      if s.cont and s.cont ~= cont then busy = ns.Router.WarmUp(s.cont, s.x, s.y) or busy end
    end
    -- (and the underground cities on this continent: a route through one's flight master or
    -- lift, Undercity's, built its roads in the frame, a third of a second and more)
    for lvl, l in pairs(ns.CityLevels or {}) do
      if not l.instance and lvl ~= cont and Geo.Base(lvl) == Geo.Base(cont) then
        busy = ns.Router.WarmUp(lvl, px, py) or busy
      end
    end
    if busy then
      N.warming = true
      return nil
    end
  end
  N.warming = nil
  local moved = r and ((px - N.routeX) ^ 2 + (py - N.routeY) ^ 2) or math.huge
  -- stretches between stops still to work out: one more, same route from the player. In the game, in the
  -- background (they don't depend on the player; a far pair of stops was 40 to 85 ms in the frame, the
  -- overnight sweeps' replay); in the tests, in the frame as before.
  if r and not r.flying and r.firstStretch and r.version == version and r.offroad == offroad and not N.degraded
      and later.key == version .. ":" .. tostring(offroad) and LaterMissing() then
    if ns.Router.WARM and not ns.Router.SYNC_WALKS then
      ns.Router.Background("later:" .. version .. ":" .. tostring(offroad), function()
        local _, walk = N.Speeds()
        FillLater(walk, offroad, N.LATER_PER_CALL)
        return version
      end, function(v)
        local rr = N.route
        if v ~= version or not (rr and rr.firstStretch and rr.version == version and rr.offroad == offroad) then return end
        local _, walk = N.Speeds()
        local nr = Assemble(rr.firstStretch, N.routeX, N.routeY, N.routeCont, walk, offroad)
        nr.keptSince = rr.keptSince
        Follow(nr, N.playerX or px, N.playerY or py)
        N.route, kept = nr, nr
      end)
    else
      local _, walk = N.Speeds()
      local t0 = ns.PerfStart and ns.PerfStart()
      FillLater(walk, offroad, N.LATER_PER_CALL)
      local nr = Assemble(r.firstStretch, N.routeX, N.routeY, cont, walk, offroad)
      nr.keptSince = r.keptSince
      Follow(nr, px, py)
      N.route, kept, r = nr, nr, nr
      if t0 then ns.PerfEnd("route calculation: stops", t0) end
    end
  end
  local rerouteSecs, rerouteYd, searchSecs = N.RerouteTiming()
  -- (in a city, the next stop outside it, on the route: kept as it is, N.CityHold)
  if r and N.routeOffroad == offroad and N.routeCont == cont and N.CityHold(px, py, cont)
      and (moved <= rerouteYd ^ 2 or Follow(r, px, py)) then
    if moved > rerouteYd ^ 2 then N.routeX, N.routeY, N.trimX, N.trimY = px, py, px, py end
    return r
  end
  if searchDirty and r and now - searchRecalcAt >= searchSecs then
    r, N.route = nil, nil
    moved = math.huge
    searchDirty, searchRecalcAt = false, now
  end
  local age = r and now - N.routeTime or math.huge
  local same = r and N.routeOffroad == offroad and N.routeCont == cont
  if same and age < REROUTE_STALE and (age < rerouteSecs or moved <= rerouteYd ^ 2) then
    -- (not recalculated yet: the walked part behind the player trimmed off meanwhile)
    local tx, ty = N.trimX or N.routeX, N.trimY or N.routeY
    if age < FOLLOW_MAX_AGE and (px - tx) ^ 2 + (py - ty) ^ 2 >= N.TRIM_MOVED_YD ^ 2
        and Follow(r, px, py, N.TRIM_AHEAD_YD) then
      N.trimX, N.trimY = px, py
    end
    return r
  end
  -- moving along the route: just follow it (no recalculation)
  if same and age < FOLLOW_MAX_AGE and Follow(r, px, py) then
    N.routeX, N.routeY, N.trimX, N.trimY = px, py, px, py
    return r
  end
  -- the route so far, to compare with (also after Invalidate)
  local old = r or kept
  if old and not (old.version == version and old.offroad == offroad and old.cont == cont) then old = nil end
  -- Worked out in the background (Router.Background: its searches pause, no frame waits on them):
  -- the first route (nothing to show yet: "Working out the route..."), a route whose walk from
  -- the player is long (off it: rejoined, a short way back onto it ahead), and any route the player
  -- is still on, `old` shown meanwhile (a finished search's recalculation routed the whole plan in
  -- the frame when the walk from the player was short: the 50 to 170 ms frames of the overnight trip
  -- sweeps, 2026-10-07). Off the route too (asked 2026-11-18, "long routes going off course is causing lag spikes for
  -- each route": off the route with a short walk from the player, the whole plan, a trip across continents and its
  -- rides, was worked out in the frame, 20 to 40 ms each time, again every REROUTE_SECONDS while off it; with a long
  -- walk, the way back on routed in the frame): first in the queue with the bigger slices (N.Rerouting), the route as
  -- it was shown for those few frames, then the one from where the player went.
  local long = old and old.fullFirst and old.cum and (old.cum[#old.cum] - (old.consumed or 0)) >= N.REJOIN_MIN_YD
  if ns.Router.WARM and not ns.Router.SYNC_WALKS then -- (as in game; tests: at once)
    local off = old and not Follow(old, px, py)
    -- (a provisional route's recalculation, a search it waited on done, first in the queue too: behind the ride check's
    -- walks, 80 of them from the Wetlands' western marsh, the swim to the bay below Stromgarde landed half a minute
    -- after its walk, the 5.4k yd road round by Thandol Span shown meanwhile, issue #742)
    local first = off or (old and old.pending) or false
    if old and N.route == nil then
      -- (still on it, the route dropped for a finished search's recalculation: shown meanwhile, not
      -- "Working out the route..." with no route every few seconds while riding past searched ground)
      N.route = old
    end
    local key = "route:" .. version .. ":" .. tostring(offroad)
    ns.Router.Background(key, function()
      return Compute(px, py, cont, d, offroad)
    end, function(res)
      -- (still this route's stops: in, unless the one shown is clearly shorter; from where the
      -- player is now)
      if not res or res.version ~= version then return end
      local cur = N.route or kept
      if cur and not (cur.version == version and cur.cont == res.cont) then cur = nil end
      Apply(res, cur, N.playerX or px, N.playerY or py, res.cont, offroad, GetTime(), true)
    end, first)
    if off then
      hurried = { key }
      if long then
        -- (a short way back onto the long walk, ahead of the route worked out again: queued after it, run before it)
        local v, rkey = version, "rejoin:" .. version .. ":" .. tostring(offroad)
        hurried[2] = rkey
        ns.Router.Background(rkey, function()
          return Rejoin(old, px, py, cont, offroad) or false
        end, function(rj)
          if rj and v == version and (N.route == old or N.route == nil) then
            Apply(rj, nil, N.playerX or px, N.playerY or py, cont, offroad, GetTime(), true)
          end
        end, true)
      end
    end
    -- (queued now, or already: what's shown meanwhile, never worked out in the frame as well)
    N.warming = N.route == nil or nil
    return N.route
  end
  local t0 = ns.PerfStart and ns.PerfStart()
  local new = Compute(px, py, cont, d, offroad)
  if t0 then ns.PerfEnd("route calculation", t0) end
  return Apply(new, old, px, py, cont, offroad, now)
end
-- (the routing work done in the frame, outside the background's jobs: the stutter watch's, N.RouteWork)
local RouteNow = N.Route
function N.Route(px, py, cont)
  if coroutine.running() or not debugprofilestop then return RouteNow(px, py, cont) end
  local t0 = debugprofilestop()
  local r = RouteNow(px, py, cont)
  N.RouteWork(debugprofilestop() - t0)
  return r
end

-- Once a route is worked out (settled, or 3 s on): walking through a zone too high for the
-- player asks first (GPSFrame's ConfirmRedRoute); no clears the route.
local redChecked, redSeenAt = nil, nil
local redAsking -- (RedKey() while asked)
local redYes, redTrip -- (the question's yes, while it's up; the trip it's about, N.trip)
-- The route the check is about: the stops, and the rides left out of it (a ride removed is a route of its
-- own, checked again: the tram removed, the walk round through Loch Modan asked nothing, 2026-10-01).
local function RedKey()
  local n = 0
  for _ in pairs(N.skipRides or {}) do n = n + 1 end
  return version .. ":" .. n
end
-- Whether "keep this route?" is being asked about it: it isn't drawn or followed until the answer is
-- yes (asked 2026-10-01: the route through the zones showed while the popup asked about it).
function N.RedAsking() return redAsking ~= nil and redAsking == RedKey() end
function N.CheckRedRoute(px, py, cont, now)
  local r = N.route
  local d = N.dest
  local key = RedKey()
  if not r or not d or d.corpse then return end
  -- the way past the other faction's guards much quicker than the safe way (N.HostileSlower): asked first, in one popup
  -- with the zones too high on either way (GPSFrame's ConfirmRisk), the answer kept for the trip (N.AnswerRisk). Asked
  -- 2026-11-14: "If a safe route would 30% longer or more, ask the player if they want to risk going through enemy
  -- territory to save time"; "when routing through multiple higher level zones, just ask in 1 popup"
  local q = N.riskQuestion
  if q and q.key ~= N.RiskKey(d) then q, N.riskQuestion = nil, nil end
  if N.riskAsking and N.riskAsking.key ~= N.RiskKey(d) then N.riskAsking = nil end -- (another trip's, never answered)
  if q and not N.riskAsking and ns.GPS and ns.GPS.ConfirmRisk then
    N.riskAsking = q
    local asked = ns.GPS.ConfirmRisk(q, function()
      N.riskAsking = nil
      N.AnswerRisk(q, true)
    end, function()
      N.riskAsking = nil
      N.AnswerRisk(q, false)
    end)
    if not asked then N.riskAsking = nil end
    return
  end
  if N.riskAsking or redChecked == key then return end
  -- (the question still up, unanswered, from before a stop was reached or the route worked out again: the same trip's
  -- question, left up and not asked again; asked 2026-11-18, it came up again at every stop of a trip)
  if redAsking and redTrip == N.trip and N.RedAskUp() then
    redAsking, redChecked = key, key
    return
  end
  -- (the ride check still running: it may change the route, asked about once it's done; N.Tick asks again)
  if N.RideChecking and N.RideChecking() then return end
  if redSeenAt == nil or redSeenAt[1] ~= key then redSeenAt = { key, now } end
  if r.pending and now - redSeenAt[2] < 3 then return end
  redChecked = key
  local zones = N.RedOnRoute(r, px, py, cont)
  if not (zones and ns.GPS and ns.GPS.ConfirmRedRoute) then return end
  redAsking = key
  local trip = N.trip
  redTrip = trip
  -- Yes: kept, and no zone too high is asked about again on this trip (`all`). No: the route cleared when it's the only
  -- stop; a trip of several is kept and not asked again (`no`; the planner still goes round those zones where it can)
  redYes = function()
    redAsking, redYes = nil, nil
    if trip ~= N.trip then return end -- (another trip set meanwhile: not its answer)
    for _, z in ipairs(zones) do N.redOk[z.z] = true end
    N.redOk.all = true
    N.SaveStops()
    if ns.GPS.Redraw then ns.GPS.Redraw() end
  end
  local asked = ns.GPS.ConfirmRedRoute(zones, redYes, function()
    redAsking, redYes = nil, nil
    if trip ~= N.trip then return end
    if #N.stops > 1 then
      N.redOk.no = true
      N.SaveStops()
      ns.Print(L["Trip kept: it goes round zones too high for you where it can, and won't ask again this trip."])
      if ns.GPS.Redraw then ns.GPS.Redraw() end
      return
    end
    N.Clear()
  end)
  if not asked then redAsking, redYes = nil, nil end
end
-- Whether the "Keep this route?" question is still up on screen, unanswered (GPS.confirmBox: the yes / no box).
function N.RedAskUp()
  local box = redYes and ns.GPS and ns.GPS.confirmBox
  return (box and box.IsShown and box:IsShown() and box.onYes == redYes) and true or false
end

-- No route, with rides the player removed from it (N.SkipRide): "Route not possible without" them, put
-- back? (asked 2026-10-01) Yes: back in, the route worked out again; no: the route cleared. Once per change.
N.RED_ASK_TEXT = L["Waiting: keep the route through zones too high for you?"]
local skipAsked
function N.AskSkipped()
  local n = 0
  for _ in pairs(N.skipRides or {}) do n = n + 1 end
  local key = version .. ":" .. n
  if n == 0 or skipAsked == key or not N.dest or not (ns.GPS and ns.GPS.Confirm) then return false end
  skipAsked = key
  local names = {}
  for k in pairs(N.skipRides) do
    if N.skipNames[k] then names[#names + 1] = N.skipNames[k] end
  end
  table.sort(names)
  local what = #names > 0 and table.concat(names, ", ") or L["the rides you removed"]
  return ns.GPS.Confirm(Format(n == 1 and L["Route not possible without %s.\n\nPut it back?"]
    or L["Route not possible without %s.\n\nPut them back?"], what),
    function()
      N.ClearSkippedRides()
      N.SaveStops()
      if ns.GPS.RouteChanged then ns.GPS.RouteChanged() end
    end, function()
      N.Clear()
      if ns.GPS.Follow then ns.GPS.Follow() end
    end)
end

-- Keep route `old` instead of the recalculated `new`? When `new` is clearly longer (the
-- whole trip, rides counted at walking speed) and either still provisional or `old` hasn't
-- been kept for KEEP_SECONDS yet. (The caller also checks the player is still on `old`.)
-- A provisional route (a terrain search still running: straight across meanwhile) never
-- stays over a worked-out one, nor replaces one: standing still, the refresh's search made
-- a straight line over the hills each time and kept it, shorter than the roads.
function N.KeepOld(old, new, walk, now)
  if old.pending and not new.pending then return false end
  if new.pending and not old.pending then return true end
  local function cost(r) return (r.totalYards or 0) + (r.totalRide or 0) * walk end
  if cost(new) <= cost(old) * LONGER_SHARE + LONGER_YD then return false end
  return new.pending or now - (old.keptSince or now) < KEEP_SECONDS
end

-- Background terrain searches finished (GPSFrame pumps them): `fixed` when one was for a
-- leg between fixed points (the stops), else they were from the player's position.
function N.SearchDone(fixed)
  if fixed and not N.degraded then -- (cut back to the first stop: the stretches after it not redone, N.degraded)
    N.Invalidate(true)
  else
    searchDirty = true -- see SEARCH_RECALC_SECONDS
  end
end

-- Recompute the route on the next request (e.g. a background terrain search finished);
-- `all`: the legs between stops too (otherwise only the way from the player).
-- `fresh`: something the player changed (an option): the new route applies right away,
-- without comparing it with the current one (see KeepOld).
function N.Invalidate(all, fresh)
  N.route = nil -- (kept stays, to compare the recalculation with)
  if all ~= false then later.done = {} end -- redone a few a frame; shown until replaced
  if fresh then pairCosts, pairCount = {}, 0 end
  if fresh then kept, rideCheck, ridePlan, rideLast, N.noWalk, N.walkKept, rideSpot = nil, {}, {}, {}, {}, {}, {} end
  if all ~= false then legMemo, legMemoN = {}, 0 end
end

-- Reorder the stops into the fastest order from (px, py) (default: the player's
-- position), by planned travel time (transports included): every order for up to 7
-- stops, nearest-first improved by 2-opt beyond that. `onlyIfFaster`: keep the current
-- order unless the best one is clearly faster (REORDER_GAIN). Returns whether it changed.
N.REORDER_GAIN_SECONDS, N.REORDER_GAIN_SHARE = 15, 0.10
N.PART_ROUNDS = 3 -- a quest's area in parts: rounds of choosing the parts, then the order again
N.PART_GAIN_SECONDS = 5 -- ... another part only when it saves at least this much
-- The quest route ordered by level (players' request relayed by Kooki3z 2026-11-21: "Be able to prioritize quests by
-- level (i.e. prefer lower level or quests that are about to turn grey)"; `questLevelOrder`, Options > Routing > Quest
-- Route): each quest route stop gets a band, and N.OrderStops visits the bands in turn, the stops of each in the fastest
-- order (from where the band before ended). Bands, not a strict sort by level: a strict sort zigzags across the map for
-- a level's difference, while within a band the route is as fast as ever. "low": bands of LEVEL_BAND levels from the
-- lowest quest's up. "gray": the quests that turn gray within GRAY_SOON_LEVELS more levels of the player's
-- (Layers.QuestGrayLevel, the game's gray rule) first, then the rest; a quest gray already has little left to lose.
-- A turn-in counts at its quest's level (its reward shrinks the same way). Stops with no level known (not a quest's,
-- or the log doesn't say) have no band and go wherever is fastest. Nil when the option is off or no stop has a band.
N.LEVEL_BAND = 3
N.GRAY_SOON_LEVELS = 2
function N.QuestLevelOrder()
  local st = ns.settings and ns.settings.gps
  local v = st and st.questLevelOrder
  return (v == "low" or v == "gray") and v or nil
end
function N.QuestBands(stops)
  local mode = N.QuestLevelOrder()
  local Lay = ns.Layers
  if not (mode and Lay and Lay.QuestLevel) then return nil end
  local levels, low = {}, nil
  for i, d in ipairs(stops) do
    local lvl = d.questRoute and d.quest and Lay.QuestLevel(d.quest)
    if lvl then
      levels[i] = lvl
      low = math.min(low or lvl, lvl)
    end
  end
  if not low then return nil end
  local gray = mode == "gray" and Lay.QuestGrayLevel and Lay.QuestGrayLevel()
  if mode == "gray" and not gray then return nil end
  local bands = {}
  for i, lvl in pairs(levels) do
    if mode == "low" then
      bands[i] = math.floor((lvl - low) / N.LEVEL_BAND)
    else
      local left = lvl - gray -- (levels the player can still gain before it's gray)
      bands[i] = (left >= 1 and left <= N.GRAY_SOON_LEVELS) and 0 or 1
    end
  end
  return bands
end

function N.OrderStops(px, py, cont, onlyIfFaster)
  local n = #N.stops
  if n < 2 then return false end
  if N.ListedOrder() then return false end -- (a trip in its listed order: never, whoever asks)
  if N.stops[1].corpse then return false end -- your body stays first (corpse run)
  if not px then px, py, cont = Geo.PlayerWorld() end
  cont = N.PlayerLevel(cont)
  if not px then return end
  local _, walk = N.Speeds()
  local pts = { { x = px, y = py, cont = cont } }
  for i, d in ipairs(N.stops) do pts[i + 1] = d end
  -- seconds from a to b (`fromPlayer`: a is the player, not remembered)
  local function Secs(a, b, fromPlayer)
    local d = a.cont == b.cont and math.sqrt((a.x - b.x) ^ 2 + (a.y - b.y) ^ 2)
    if d and d <= N.ORDER_WALK_YD then
      return d * N.WALK_FACTOR / walk -- close by: walked (what the plan would say)
    end
    -- between two stops the time doesn't change: remembered (not from the player)
    local key = not fromPlayer and string.format("%d:%.0f:%.0f>%d:%.0f:%.0f@%.2f", a.cont, a.x, a.y, b.cont, b.x, b.y, walk)
    local secs = key and pairCosts[key]
    if not secs then
      secs = select(2, N.Plan(a.cont, a.x, a.y, walk, b)) or math.huge
      if key then
        if pairCount > 20000 then pairCosts, pairCount = {}, 0 end
        pairCosts[key], pairCount = secs, pairCount + 1
      end
    end
    return secs
  end
  -- (a quest stop whose area is in parts, Layers.QuestAreaSpots: at the part it was last given; N.ChooseParts)
  for i = 2, n + 1 do
    local d = pts[i]
    if d.parts and d.partAt then
      local q = d.parts[d.partAt]
      if q then pts[i] = setmetatable({ x = q.x, y = q.y, cont = q.cont }, { __index = d }) end
    end
  end
  local cost = {}
  local function Fill()
    for i = 1, n + 1 do
      cost[i] = {}
      for j = 2, n + 1 do
        cost[i][j] = i ~= j and Secs(pts[i], pts[j], i == 1) or 0
      end
    end
  end
  Fill()
  local function total(order)
    local t, prev = 0, 1
    for _, j in ipairs(order) do t, prev = t + cost[prev][j], j end
    return t
  end
  -- (stops down in a city keep their order among themselves: N.KeepCityOrder)
  local kept, keptList = {}, {}
  for j = 2, n + 1 do
    if N.CityKept(pts[j]) then
      kept[j] = true
      keptList[#keptList + 1] = j
    end
  end
  local function inTurn(j, used) -- (a kept stop only after the kept ones placed before it)
    if not kept[j] then return true end
    for _, e in ipairs(keptList) do
      if e == j then return true end
      if not used[e] then return false end
    end
    return true
  end
  -- (a quest's turn-in after its objectives' stops; the level bands in turn, N.QuestBands)
  local band = {}
  for i, b in pairs(N.QuestBands(N.stops) or {}) do band[i + 1] = b end
  local needs = {} -- [j] = { k, ... }: stops that must come before j
  for j = 2, n + 1 do
    local d = N.stops[j - 1]
    for k = 2, n + 1 do
      local e = N.stops[k - 1]
      if k ~= j and ((d.turnin and d.quest and e.quest == d.quest and not e.turnin)
          or (band[j] and band[k] and band[k] < band[j])) then
        needs[j] = needs[j] or {}
        needs[j][#needs[j] + 1] = k
      end
    end
  end
  local function ready(j, used)
    for _, k in ipairs(needs[j] or {}) do
      if not used[k] then return false end
    end
    return true
  end
  -- (a run of the order that can be turned round: none of its stops must come before another of them)
  local function canFlip(order, a, b)
    for x = a, b do
      for _, k in ipairs(needs[order[x]] or {}) do
        for y = a, b do
          if order[y] == k then return false end
        end
      end
    end
    return true
  end
  local best, bestT
  local function Order()
    if n <= 7 then
      local order, used = {}, {}
      local function perm(k)
        if k > n then
          local t = total(order)
          if not bestT or t < bestT then best, bestT = { unpack(order) }, t end
          return
        end
        for j = 2, n + 1 do
          if not used[j] and inTurn(j, used) and ready(j, used) then
            used[j], order[k] = true, j
            perm(k + 1)
            used[j] = false
          end
        end
      end
      perm(1)
    else
      best = {}
      local used, prev = {}, 1
      for k = 1, n do
        local pick
        for j = 2, n + 1 do
          if not used[j] and ready(j, used) and (not pick or cost[prev][j] < cost[prev][pick]) then pick = j end
        end
        for j = 2, n + 1 do -- (never: the rules have no loop; any stop left, should one)
          if not pick and not used[j] then pick = j end
        end
        used[pick], best[k], prev = true, pick, pick
      end
      -- 2-opt: reverse a run of stops where that shortens the trip. Times one way and back
      -- are about the same, so each try costs just the two ends (averaged both ways).
      local function S(i, j)
        if not j then return 0 end -- after the last stop: nothing
        if i == 1 then return cost[1][j] end -- from the player
        return (cost[i][j] + cost[j][i]) / 2
      end
      local improved, passes = true, 0
      while improved and passes < 50 do
        improved, passes = false, passes + 1
        for a = 1, n - 1 do
          for b = a + 1, n do
            local before = a > 1 and best[a - 1] or 1
            local after = best[b + 1]
            local delta = S(before, best[b]) + S(best[a], after) - S(before, best[a]) - S(best[b], after)
            if delta < -1e-6 and canFlip(best, a, b) then
              for k = 0, math.floor((b - a) / 2) do best[a + k], best[b - k] = best[b - k], best[a + k] end
              improved = true
            end
          end
        end
      end
      -- (the stops down in a city back in their order, in the places they got)
      local k = 0
      for i, j in ipairs(best) do
        if kept[j] then
          k = k + 1
          best[i] = keptList[k]
        end
      end
      bestT = total(best)
    end
  end
  Order()
  -- A quest's area in parts (asked 2026-11-07: led to its north part while another part was by the next quest's stop):
  -- each such stop at the part costing least put in where it fits best in that order, then the order
  -- again, until nothing changes (a few rounds at most)
  local moved, partWas = false, {}
  for j = 2, n + 1 do partWas[j] = N.stops[j - 1].partAt end
  for _ = 1, N.PART_ROUNDS do
    local changed = false
    for k, j in ipairs(best) do
      local d = N.stops[j - 1]
      if d.parts then
        -- (each part where it fits best in the order without this stop: the cheapest place to put it in, asked
        -- 2026-11-08: Fruit of the Sea's south part was by WANTED: Murkdeep! at the route's far end, but weighed only
        -- between its neighbors up north the north part won)
        local rest = {}
        for k2, j2 in ipairs(best) do if k2 ~= k then rest[#rest + 1] = j2 end end
        local function fit(p)
          local t
          for at = 0, #rest do
            local prev, nxt = at > 0 and rest[at] or 1, rest[at + 1]
            local c = Secs(pts[prev], p, prev == 1) + (nxt and Secs(p, pts[nxt]) - cost[prev][nxt] or 0)
            if not t or c < t then t = c end
          end
          return t
        end
        local pick, pickT = nil, fit(pts[j]) - N.PART_GAIN_SECONDS
        for m, q in ipairs(d.parts) do
          local t = fit(q)
          if t < pickT then pick, pickT = m, t end
        end
        if pick and pick ~= d.partAt then
          local q = d.parts[pick]
          pts[j] = setmetatable({ x = q.x, y = q.y, cont = q.cont }, { __index = d })
          d.partAt = pick
          changed, moved = true, true
        end
      end
    end
    if not changed then break end
    Fill()
    Order()
  end
  local same = true
  for k, j in ipairs(best) do if j ~= k + 1 then same = false end end
  if same and not moved then return false end
  if onlyIfFaster then
    local current = {}
    for k = 1, n do current[k] = k + 1 end
    local now = total(current)
    if bestT > now - math.max(N.REORDER_GAIN_SECONDS, now * N.REORDER_GAIN_SHARE) then
      for j = 2, n + 1 do N.stops[j - 1].partAt = partWas[j] end -- (the parts as they were too)
      return false
    end
  end
  local ordered = {}
  for k, j in ipairs(best) do
    local d = N.stops[j - 1]
    if d.parts and d.partAt then -- (at the part chosen: the stop itself moved there, its floor no longer known)
      local q = d.parts[d.partAt]
      if d.x ~= q.x or d.y ~= q.y then d.x, d.y, d.cont, d.z = q.x, q.y, q.cont, nil end
    end
    ordered[k] = d
  end
  N.stops = ordered
  Changed()
  return true
end

-- While traveling with several stops (fastest order on): every REORDER_EVERY seconds, and
-- after moving a bit, visit the stops in a new order if that has become clearly faster
-- (e.g. heading for stop 2 first). Not while flying.
local REORDER_EVERY, REORDER_MOVED_YD = 8, 30
local reorderAt, reorderX, reorderY = 0, nil, nil
-- A quest route's stop gone (reached, done, removed; asked 2026-11-07: "the route should be recalculated with that quest
-- removed and the next one and so on"): the stops left put in the fastest order again from here, and their quest
-- areas' parts chosen again (OrderStops), whatever their number, until the next Quest Route (N.reorderDue).
function N.MaybeReorder(px, py, cont)
  local due = N.reorderDue
  N.reorderDue = nil
  if N.degraded then -- (cut back to the first stop: the order kept, looked at again once recovered)
    N.reorderDue = due
    return false
  end
  if N.loop or N.keepOrder or #N.stops < 2 or not (ns.settings and ns.settings.gps.fastestOrder) or N.KeepCityOrder() then
    return false
  end
  if ns.Taxi and ns.Taxi.Current and ns.Taxi.Current() then
    N.reorderDue = due -- (after the flight)
    return false
  end
  if due and N.OnQuestRoute() then
    reorderAt, reorderX, reorderY = GetTime(), px, py
    if ns.Router.WARM and not ns.Router.SYNC_WALKS then
      local v = version
      ns.Router.Background("reorder", function()
        if version ~= v then return false end
        return N.OrderStops(px, py, cont)
      end)
      return false
    end
    return N.OrderStops(px, py, cont)
  end
  -- a long list (an imported guide) was put in order once, from where it was imported:
  -- redoing that on the way would be a long pause for little gain
  if #N.stops > N.PLAN_AHEAD then return false end
  if ns.Taxi and ns.Taxi.Current and ns.Taxi.Current() then return false end
  local now = GetTime()
  if now - reorderAt < REORDER_EVERY then return false end
  if reorderX and (px - reorderX) ^ 2 + (py - reorderY) ^ 2 < REORDER_MOVED_YD ^ 2 then return false end
  reorderAt, reorderX, reorderY = now, px, py
  -- In the game, in the background: the plans from the player aren't remembered (they move with them), and
  -- planning them in the frame on every reorder look was the sweeps' last 50 to 100 ms frames (2026-10-07).
  -- OrderStops reads the stops as they are when the job runs, and does nothing if they changed since.
  if ns.Router.WARM and not ns.Router.SYNC_WALKS then
    local v = version
    ns.Router.Background("reorder", function()
      if version ~= v then return false end
      return N.OrderStops(px, py, cont, true)
    end)
    return false
  end
  return N.OrderStops(px, py, cont, true)
end

-- The route's points converted into continent `view`'s coordinates:
-- calls fn(x1, y1, x2, y2, kind, stop) per segment (stop: index of the stop that part of
-- the route leads to). Returns the last point (the destination).
function N.EachSegment(route, view, fn)
  local lx, ly
  for _, part in ipairs(route.parts or {}) do
    local px, py
    for i = 1, #part.pts, 2 do
      local x, y = Geo.ToContinent(part.cont, part.pts[i], part.pts[i + 1], view)
      if not x then break end
      if px then fn(px, py, x, y, part.kinds[(i - 1) / 2], part.stop, part.cont) end
      px, py = x, y
    end
    lx, ly = px or lx, py or ly
  end
  return lx, ly
end

-- The next transport on the route: row, boarding side, and whether the player is at its dock.
local function NextRide(route, px, py)
  if not route or not route.legs then return nil end
  for i, leg in ipairs(route.legs) do
    if leg.ride then
      local t, from = leg.ride, leg.from
      local bx, by = from == 1 and t[2] or t[5], from == 1 and t[3] or t[6]
      local atDock = i <= 2 and math.sqrt((px - bx) ^ 2 + (py - by) ^ 2) <= N.DOCK_YD
      return t, from, atDock
    end
  end
end

-- The teleport to use now: the route's first step (the hearthstone, a teleport, an engineer's
-- teleporter), from where the player stands; else nil. What GPSFrame's use button uses.
function N.UseNow()
  local r = N.route
  local leg = r and not r.flying and r.legs and r.legs[1]
  if leg and leg.ride and leg.ride.use and (leg.ride.item or leg.ride.spell) then return leg.ride end
end

---------------------------------------------------------------------------
-- Speeds
---------------------------------------------------------------------------

local lastRun = DEFAULT_RUN -- the plain run speed: on foot, no speed ability on (items and the Speed stat in it)
local plainSeen -- (lastRun was seen, not guessed)

-- Movement abilities (not items): the spell, the share of the run speed it adds, talents adding
-- more (their spells by rank, `per` rank), and whether it only works outdoors. A known one's
-- time is shown beside walking; while it's on, it's the walking speed. Its speed is learned
-- the first time it's seen on (the server's own numbers), else estimated from these.
N.MOVE_ABILITIES = {
  { spell = 783, add = 0.40, outdoors = true },   -- Travel Form (druid)
  { spell = 2645, add = 0.40, outdoors = true },  -- Ghost Wolf (shaman)
  { spell = 768, add = 0, talent = { 17002, 24866 }, per = 0.15, outdoors = true }, -- Cat Form, with Feline Swiftness
  { spell = 5118, add = 0.30, talent = { 19559, 19560 }, per = 0.03 },  -- Aspect of the Cheetah (Pathfinding)
  { spell = 13159, add = 0.30, talent = { 19559, 19560 }, per = 0.03 }, -- Aspect of the Pack (Pathfinding)
}

local function Known(spell)
  if IsPlayerSpell then
    local ok, v = pcall(IsPlayerSpell, spell)
    if ok and v then return true end
  end
  if IsSpellKnown then
    local ok, v = pcall(IsSpellKnown, spell)
    if ok and v then return true end
  end
  return false
end

-- A talent's rank: its rank spells known, else found by name in the talent tabs.
local function TalentRank(ids)
  for rank = #ids, 1, -1 do
    if Known(ids[rank]) then return rank end
  end
  local want = ns.SpellName and ns.SpellName(ids[1])
  if not (want and GetNumTalentTabs and GetNumTalents and GetTalentInfo) then return 0 end
  local ok, rank = pcall(function()
    for tab = 1, GetNumTalentTabs() do
      for i = 1, GetNumTalents(tab) do
        local name, _, _, _, r = GetTalentInfo(tab, i)
        if name == want then return r or 0 end
      end
    end
    return 0
  end)
  return ok and rank or 0
end

-- Whether a spell's aura (or shapeshift form) is on the player.
local function AuraOn(spell)
  local ok, on = pcall(function()
    if C_UnitAuras and C_UnitAuras.GetPlayerAuraBySpellID then
      local a = C_UnitAuras.GetPlayerAuraBySpellID(spell)
      if a then return true end
    end
    if GetNumShapeshiftForms and GetShapeshiftFormInfo then
      for i = 1, GetNumShapeshiftForms() do
        local _, active, _, id = GetShapeshiftFormInfo(i)
        if active and id == spell then return true end
      end
    end
    if UnitBuff then
      for i = 1, 40 do
        local name, _, _, _, _, _, _, _, _, id = UnitBuff("player", i)
        if not name then break end
        if id == spell then return true end
      end
    end
    return false
  end)
  return ok and on == true
end
N.KnownSpell, N.AuraOn = Known, AuraOn -- (N.WaterFast)

-- The movement ability to show: the one on, else the fastest known. { spell, name, icon,
-- speed, active } or nil. Checked at most every half second (the auras) and 10 s (the
-- spells and talents known).
local abilities, abilitiesAt, abilityNow, abilityAt
local function AbilitySpeed(a, cdb)
  local learned = cdb and cdb.moveSpeeds and cdb.moveSpeeds[a.spell]
  if learned then return learned end
  return lastRun * (1 + a.add + (a.rank or 0) * (a.per or 0))
end
function N.MoveAbility()
  local now = GetTime()
  if not abilities or now - abilitiesAt >= 10 then
    abilities, abilitiesAt = {}, now
    for _, a in ipairs(N.MOVE_ABILITIES) do
      if Known(a.spell) then
        local rank = a.talent and TalentRank(a.talent) or 0
        if a.add + rank * (a.per or 0) > 0 then
          abilities[#abilities + 1] = { spell = a.spell, add = a.add, per = a.per, rank = rank, outdoors = a.outdoors }
        end
      end
    end
    abilityAt = nil
  end
  if #abilities == 0 then return nil end
  if abilityNow and abilityAt and now - abilityAt < 0.5 then return abilityNow end
  local cdb = ns.CharDB and ns.CharDB()
  local best, on
  for _, a in ipairs(abilities) do
    a.speed = AbilitySpeed(a, cdb)
    if AuraOn(a.spell) then on = a end
    if not best or a.speed > best.speed then best = a end
  end
  local a = on or best
  if not a.name then
    local name = ns.SpellName and ns.SpellName(a.spell) or L["Ability"]
    a.name = name:gsub("^Aspect of the ", "")
    a.icon = ns.SpellIcon and ns.SpellIcon(a.spell)
  end
  a.active = on ~= nil
  abilityNow, abilityAt = a, now
  return a
end

-- "Ghost Wolf" with its icon, for the times line.
function N.AbilityLabel(a)
  return a.icon and string.format("|T%s:12|t %s", a.icon, a.name) or a.name
end

-- The times line: `yards` to go on foot plus `ride` seconds of rides. Mounted: just the mounted time. On foot:
-- walking (or the movement ability while it's on), then only the fastest other way the character has, a
-- movement ability or a mount (asked 2026-10-02: a shaman with Ghost Wolf and riding sees "Walk ... Mount ...",
-- not all three). The mount's speed is the riding skill's (60% at apprentice, 100% at journeyman) until it's
-- seen on a mount, then that (N.Speeds).
-- (`swim`: the yards of it swum, at the swim speed: N.TripSecs)
function N.TimesLine(yards, ride, walk, mount, mounted, ability, swim)
  local function T(speed) return N.FormatTime(N.TripSecs(yards, swim, ride, speed)) end
  if mount and mounted then return Format(L["Mount %s"], T(mount)) end
  local on = ability and ability.active
  local line = on and (N.AbilityLabel(ability) .. " " .. T(walk)) or Format(L["Walk %s"], T(walk))
  local other = ability and not on and ability.speed
  if mount and mount > (other or walk) then
    line = line .. "    " .. Format(L["Mount %s"], T(mount))
  elseif other and other > walk then
    line = line .. "    " .. N.AbilityLabel(ability) .. " " .. T(other)
  end
  return line
end

-- Riding skill rank (0 if not learned). Classic keeps riding as a skill line.
local riding, ridingAt -- cached: Speeds() runs every redraw
function N.RidingRank()
  local now = GetTime()
  if riding and now - ridingAt < 10 then return riding end
  local ok, rank = pcall(function()
    for i = 1, GetNumSkillLines() do
      local name, isHeader, _, skillRank = GetSkillLineInfo(i)
      if not isHeader and name == (RIDING or "Riding") then return skillRank end
    end
    return 0
  end)
  riding, ridingAt = ok and rank or 0, now
  return riding
end

-- current speed, walking (run) speed, mounted speed or nil if the player can't ride, mounted?,
-- and the movement ability (N.MoveAbility) or nil. The walking speed is the plain run speed
-- (the Speed stat and items in it), or the ability's while it's on.
-- GetUnitSpeed is secret in combat; the last values seen are used then.
local lastSwim = N.SWIM_SPEED -- the swim speed (GetUnitSpeed's fourth value: items and Aquatic Form in it)
function N.SwimSpeed() return lastSwim end
function N.Speeds()
  local cur, run
  local ok, a, b, _, sw = pcall(GetUnitSpeed, "player")
  if ok and a and not ns.IsSecret(a) then cur, run = a, b end
  if ok and type(sw) == "number" and not ns.IsSecret(sw) and sw > 0.5 then lastSwim = sw end
  -- a flight counts as mounted to the game: not here (and its speed isn't a mount's)
  local onTaxi = UnitOnTaxi and UnitOnTaxi("player") or false
  local mounted = not onTaxi and IsMounted and IsMounted() or false
  local cdb = ns.CharDB and ns.CharDB()
  local ability = N.MoveAbility()
  if run and run > 0 and not onTaxi and not mounted then
    if ability and ability.active then
      -- (its speed as the server has it, kept per character)
      if cdb and run > lastRun + 0.2 then
        cdb.moveSpeeds = cdb.moveSpeeds or {}
        cdb.moveSpeeds[ability.spell] = run
      end
    else
      lastRun, plainSeen = run, true
    end
  end
  if not plainSeen and GetSpeed then
    -- (not seen on foot yet: the base run speed and the Speed stat, a percentage)
    local sok, pct = pcall(GetSpeed)
    if sok and type(pct) == "number" and not ns.IsSecret(pct) and pct >= 0 and pct < 100 then
      lastRun = DEFAULT_RUN * (1 + pct / 100)
    end
  end
  if ability then ability.speed = AbilitySpeed(ability, cdb) end
  -- a mounted time only for characters that have learned to ride
  local rank = N.RidingRank()
  if mounted then rank = math.max(rank, 75) end -- on a mount (the skill list may be collapsed)
  local mount
  if rank >= 75 then
    if mounted and cur and cur > lastRun + 0.5 and cur <= lastRun * 3 then
      if cdb then cdb.mountSpeed = cur end -- includes riding skill, items and buffs
    end
    if mounted and cur and cur > 0 then
      mount = cur
    elseif cdb and cdb.mountSpeed and cdb.mountSpeed <= lastRun * 3 then
      mount = cdb.mountSpeed
    else
      mount = lastRun * (rank >= 150 and 2.0 or 1.6)
    end
  end
  local walk = (ability and ability.active and not mounted) and ability.speed or lastRun
  return cur, walk, mount, mounted and mount ~= nil, ability
end

---------------------------------------------------------------------------
-- Formatting and status
---------------------------------------------------------------------------

function N.FormatTime(seconds)
  if not seconds or seconds ~= seconds or seconds == math.huge then return "--" end
  seconds = math.floor(seconds + 0.5)
  local h, m, s = math.floor(seconds / 3600), math.floor(seconds % 3600 / 60), seconds % 60
  if h > 0 then return Format(L["%dh %02dm %02ds"], h, m, s) end
  if m > 0 then return Format(L["%dm %02ds"], m, s) end
  return Format(L["%ds"], s)
end

-- A distance as the player picked (Options > General, `distanceUnits`; asked 2026-10-07: European distances): yards, the
-- game's own ("1.2k yd" past 1,000), "metric" (meters, kilometers past 1,000 m) or "imperial" (feet, miles from a tenth
-- of one). `short`: never the long unit (a height: "12 yd above you").
N.YD_M, N.YD_FT, N.YD_MI = 0.9144, 3, 1760
function N.FormatDistance(yd, short)
  local units = ns.settings and ns.settings.gps and ns.settings.gps.distanceUnits
  if units == "metric" then
    local m = yd * N.YD_M
    if m >= 1000 and not short then return string.format(L["%.1f km"], m / 1000) end
    return string.format(L["%d m"], math.floor(m + 0.5))
  elseif units == "imperial" then
    if yd >= N.YD_MI / 10 and not short then return string.format(L["%.1f mi"], yd / N.YD_MI) end
    return string.format(L["%d ft"], math.floor(yd * N.YD_FT + 0.5))
  end
  if yd >= 1000 and not short then return string.format(L["%.1fk yd"], yd / 1000) end
  return string.format(L["%d yd"], math.floor(yd + 0.5))
end

N.STEP_MIN_YD = 15 -- shorter walks (e.g. already at the dock) aren't listed as steps

-- A stop's floor in its building (asked 2026-10-06: Brill's trainers upstairs in the inn, Goldshire's Warlock trainer in
-- the cellar): 1 upstairs, -1 the cellar, nil the ground floor or unknown. From the town place at its spot
-- (ns.TownPlaces' `fl`, worked out offline from its NPC's height: townplaces.floors), however the stop was made (a
-- guard, the search, a double-click on the place's icon). Kept on the stop (`d.floor`, false: none).
N.FLOOR_SPOT_YD = 1.5
-- (asked 2026-10-06, Brill: with the player up on that floor, followed along the building's roads (N.TrackCityZ),
-- nil: no "(upstairs)", no stairs badge or color, no "Upstairs:" hint any more)
function N.StopFloor(d)
  local fl = N.StopFloorOf(d)
  if fl and N.OnStopFloor(d) then return nil end
  return fl
end
function N.StopFloorOf(d)
  if not d then return nil end
  if d.floor ~= nil then return d.floor or nil end
  -- (places at about the same spot can be on different floors, an inn's innkeeper under its trainers: the one at the
  -- stop's height, else of its name; by the spot alone only when they all agree)
  local near = {}
  local base = Geo.Base(d.cont)
  for _, t in pairs(ns.TownPlaces or {}) do
    if t.cont == base then
      for _, p in ipairs(t) do
        if math.abs(p.x - d.x) <= N.FLOOR_SPOT_YD and math.abs(p.y - d.y) <= N.FLOOR_SPOT_YD then near[#near + 1] = p end
      end
    end
  end
  local pick
  for _, p in ipairs(near) do
    if d.z and p.z and math.abs(p.z - d.z) < 1 then pick = p end
  end
  if not pick and d.name then
    for _, p in ipairs(near) do
      -- (or its name as shown in the addon's language: a stop picked from the map or the search, Layers.PlaceLabel)
      if p[1] == d.name or (ns.Layers and ns.Layers.PlaceLabel and ns.Layers.PlaceLabel(p[1]) == d.name) then pick = p end
    end
  end
  if not pick and not d.z and near[1] then
    pick = near[1]
    for _, p in ipairs(near) do
      if (p.fl or 0) ~= (pick.fl or 0) then pick = nil break end
    end
  end
  local fl = pick and pick.fl or false
  d.floor = fl
  d.floorZ = pick and pick.z or nil -- (the place's height: N.StopHeight, for a stop with none of its own)
  return fl or nil
end
local FLOOR_NAMED = { [1] = L["%s (upstairs)"], [-1] = L["%s (downstairs)"] }

-- How a stop is named in the steps: its marker and name (and its floor: "(upstairs)").
local function StopLabel(i, d, count)
  local icon = string.format("|T%s:12|t ", N.StopIcon(d))
  local fl = N.StopFloor(d)
  if d.name and fl then return icon .. Format(FLOOR_NAMED[fl], d.name) end
  if d.name then return icon .. d.name end
  if count > 1 then return icon .. Format(L["stop %d"], i) end
  return icon .. L["your destination"]
end

-- Taking a ride, in the steps (by its kind; %s: where to), and walking to one (by what's there: a row's 11th value,
-- else its kind; the first %s the distance, the last the place)
N.TAKE = {
  flight = L["Take the flight to %s"], zeppelin = L["Take the zeppelin to %s"], boat = L["Take the boat to %s"],
  tram = L["Take the tram to %s"], lift = L["Take the lift to %s"], portal = L["Take the portal to %s"],
  teleporter = L["Take the teleporter to %s"],
}
N.WALK_TO = {
  ["flight master"] = L["Walk %s to the flight master (%s)"], ["new flight master"] = L["Walk %s to the new flight master (%s)"],
  zeppelin = L["Walk %s to the zeppelin (%s)"], boat = L["Walk %s to the boat (%s)"], tram = L["Walk %s to the tram (%s)"],
  lift = L["Walk %s to the lift (%s)"], portal = L["Walk %s to the portal (%s)"],
  teleporter = L["Walk %s to the teleporter (%s)"],
}
-- (in the panel's first line, after the distance: "  to the zeppelin (then to Durotar)")
N.TO_RIDE = {
  ["flight master"] = L["to the flight master (then to %s)"], ["new flight master"] = L["to the new flight master (then to %s)"],
  zeppelin = L["to the zeppelin (then to %s)"], boat = L["to the boat (then to %s)"], tram = L["to the tram (then to %s)"],
  lift = L["to the lift (then to %s)"], portal = L["to the portal (then to %s)"],
  teleporter = L["to the teleporter (then to %s)"],
}
-- (boarding it, there: "Board the zeppelin to Durotar", as Turns' last maneuver)
N.BOARD = {
  flight = L["Board the flight to %s"], zeppelin = L["Board the zeppelin to %s"], boat = L["Board the boat to %s"],
  tram = L["Board the tram to %s"], lift = L["Board the lift to %s"], portal = L["Board the portal to %s"],
  teleporter = L["Take the teleporter to %s"],
}

-- The route as a list of steps (strings), from where the player is: walks to docks and
-- stops, rides on zeppelins and boats. Uses the last computed route (N.Route).
function N.Steps()
  local r = N.route
  if not r or not r.stretches then return {} end
  local steps = {}
  local count = #N.stops
  -- time for each stretch (from the previous stop, or from the player for the first):
  -- walking at mount speed while mounted, else run speed, plus transport rides
  local _, walk, mount, mounted = N.Speeds()
  local speed = mounted and mount or walk
  local learn = N.LearnOnRoute(r) or {}
  -- (a walk passing flight masters to learn: split where it passes each, the detour between;
  -- `yards` the walk's still to go: returns what's left after the detours)
  -- (a detour where the walk ends, the stop or a dock: after the walk's step, `after`)
  local function Detour(h)
    if h.off < N.LEARN_BY_YD then -- (right by the way)
      steps[#steps + 1] = Format(L["|cffc08040Learn the flight path at %s (on the way)|r"], h.name)
    else
      steps[#steps + 1] = Format(L["|cffc08040Detour %s to learn the flight path at %s|r"], N.FormatDistance(h.off), h.name)
    end
  end
  -- (a walk with swims, N.LegPieces: its pieces from `a` to `b` yards, each its own step with its own time; the last
  -- left out with `keepLast`, returned for the caller to word. A bit under STEP_MIN_YD cut off by a detour: its neighbor's)
  local function SwimTime(p) return string.format("  |cffffd100%s|r", N.FormatTime(N.TripSecs(p.yd, p.sw, 0, speed))) end
  local function PieceSteps(pieces, a, b, keepLast)
    local list = {}
    for _, p in ipairs(pieces) do
      local s0, s1 = math.max(p.s0, a), math.min(p.s1, b)
      if s1 > s0 then list[#list + 1] = { swim = p.swim, yd = s1 - s0, sw = p.sw * (s1 - s0) / (p.s1 - p.s0) } end
    end
    for j = #list, 1, -1 do
      local q = list[j]
      local into = #list > 1 and q.yd < N.STEP_MIN_YD and (list[j + 1] or list[j - 1])
      if into then
        into.yd, into.sw = into.yd + q.yd, into.sw + q.sw
        table.remove(list, j)
      end
    end
    local last = keepLast and table.remove(list) or nil
    for _, q in ipairs(list) do
      steps[#steps + 1] = Format(q.swim and L["Swim %s"] or L["Walk %s"], N.FormatDistance(q.yd)) .. SwimTime(q)
    end
    return last
  end
  local function Detours(leg, yards, pieces)
    local walked, after = 0, {}
    for _, h in ipairs(learn) do
      if h.leg == leg and h.along >= walked then
        if h.along > yards - N.STEP_MIN_YD then
          after[#after + 1] = h
        else
          if h.along - walked >= N.STEP_MIN_YD then
            if pieces then
              PieceSteps(pieces, walked, h.along)
            else
              steps[#steps + 1] = Format(L["Walk %s"], N.FormatDistance(h.along - walked))
            end
          end
          Detour(h)
          walked = h.along
        end
      end
    end
    return yards - walked, after, walked
  end
  for i, st in ipairs(r.stretches) do
    local d = N.stops[i]
    if st and d then
      local legs = st.legs
      local done = i == 1 and (r.consumed or 0) or 0 -- already walked (following the route)
      -- (its swims at the swim speed: the first's still to go, r.swimYards)
      local swim = i == 1 and (r.swimYards or 0) or N.StretchSwim(st)
      local took = string.format("  |cffffd100%s|r", N.FormatTime(N.TripSecs(math.max(0, st.walk - done), swim, st.ride, speed)))
      for k, leg in ipairs(legs) do
        if leg.ride then
          local t, from = leg.ride, leg.from
          steps[#steps + 1] = t.flying and N.RidingText(r.flying and r.flying.kind, t[10])
            or t.use and Format(L["Use %s (to %s)"], t[8], t[10])
            or t.learn and Format(L["Learn the flight path, then take the flight to %s"], t[10])
            or N.TAKE[t[8]] and Format(N.TAKE[t[8]], ns.RideEndName(t, from == 1 and 2 or 1))
            or Format(L["Take the %s to %s"], t[8], ns.RideEndName(t, from == 1 and 2 or 1))
          -- (the hearthstone or a teleport kept for a later stop, AssignTeleports: N.TeleportAheadText)
          if t.use and i > 1 and not steps.teleportAt then
            steps.teleportAt = #steps
            steps.teleportText = Format(L["|cffffd100Use %s after %s|r (to %s)"], t[8], StopLabel(i - 1, N.stops[i - 1], count), t[10])
          end
        elseif (leg.yards or 0) - (k == 1 and done or 0) >= N.STEP_MIN_YD or k == #legs then
          local nxt = legs[k + 1]
          local yards = math.max(0, (leg.yards or 0) - (k == 1 and done or 0))
          -- (swum in places: a step for each piece walked and swum, N.LegPieces)
          local pieces = N.LegPieces(st, leg, k == 1 and done or 0)
          local left, after, walked = Detours(leg, yards, pieces)
          local last = pieces and PieceSteps(pieces, walked, yards, true)
          if last then left = last.yd end
          local dist = N.FormatDistance(left)
          local time = last and SwimTime(last) or (count > 1 and took or "")
          if nxt and nxt.ride then
            local t = nxt.ride
            local at = N.WALK_TO[t[11] or t[8]]
            local here = ns.RideEndName(t, nxt.from == 1 and 1 or 2)
            steps[#steps + 1] = last and last.swim and Format(L["Swim %s to %s"], dist, here) .. time
              or (at and Format(at, dist, here) or Format(L["Walk %s to the %s (%s)"], dist, t[11] or t[8], here))
                .. (last and time or "")
          else
            local to = StopLabel(i, d, count)
            steps[#steps + 1] = (last and last.swim and Format(L["Swim %s to %s"], dist, to)
              or Format(L["Walk %s to %s"], dist, to)) .. time
          end
          for _, h in ipairs(after) do Detour(h) end
        end
      end
    end
  end
  -- the stops after those routed (the option: stops routed and drawn ahead): listed too, not worked
  -- out yet (about: the straight line from the one before, as planning counts it)
  local planned = N.PlannedStops()
  local prev = N.stops[planned]
  for i = planned + 1, #N.stops do
    local d = N.stops[i]
    local far = prev and Geo.Base(prev.cont) == Geo.Base(d.cont)
      and math.sqrt((d.x - prev.x) ^ 2 + (d.y - prev.y) ^ 2) * N.WALK_FACTOR
    steps[#steps + 1] = far and Format(L["|cff9d9d9dAbout %s to %s (not routed yet)|r"], N.FormatDistance(far), StopLabel(i, d, count))
      or Format(L["|cff9d9d9dThen to %s (not routed yet)|r"], StopLabel(i, d, count))
    prev = d
  end
  return steps
end

-- Steps text for the nav panel: the first `shown` steps numbered, then "... N more".
-- Empty when the trip is a single walk.
function N.StepsText(shown)
  if N.questing then return "" end
  local steps = N.Steps()
  if #steps < 2 then return "" end
  shown = shown or 3
  local lines = {}
  for i = 1, math.min(shown, #steps) do
    lines[i] = string.format("%s%d. %s|r", i == 1 and "|cffffffff" or "|cffb0b0b0", i, steps[i])
  end
  if #steps > shown then
    lines[#lines + 1] = string.format(#steps - shown > 1 and L["|cff808080... %d more steps|r"] or L["|cff808080... %d more step|r"],
      #steps - shown)
    if steps.teleportAt and steps.teleportAt > shown then lines[#lines + 1] = steps.teleportText end
  end
  return table.concat(lines, "\n")
end

-- The hearthstone (or a teleport) kept for a later stop, when its step isn't among the first `shown`
-- listed: "Use your Hearthstone after <stop> (to Brill)", or nil. (Asked 2026-11-05: with the steps
-- collapsed only the trip's times showed, and a hearthstone kept for after stop 1 looked not planned.)
function N.TeleportAheadText(shown)
  local steps = N.Steps()
  if steps.teleportAt and steps.teleportAt > (shown or 0) then return steps.teleportText end
  return nil
end

---------------------------------------------------------------------------
-- Corpse run: released as a ghost, your body becomes stop 1 (the skull marker, a red
-- route), ahead of whatever stops there are, whether there was a route or not. It stays
-- first: no reordering moves it. Alive again, it's taken off and the route goes on.
---------------------------------------------------------------------------

N.CORPSE_CHECK = 1 -- seconds between checks
N.CORPSE_ICON = 8 -- the skull
N.CORPSE_COLOR = { 1, 0.12, 0.08 }
local corpseCheckAt = -math.huge

-- Where your body is: cont, x, y (world), or nil. Asked on the map you're on, then on the
-- continents (the body can be in the next zone from the graveyard).
local function CorpseSpot()
  local D = C_DeathInfo
  if not (D and D.GetCorpseMapPosition) then return nil end
  local maps = {}
  local here = C_Map and C_Map.GetBestMapForUnit and C_Map.GetBestMapForUnit("player")
  if here then maps[1] = here end
  for id, m in pairs(ns.Maps or {}) do
    if m.type == 2 then maps[#maps + 1] = id end
  end
  for _, id in ipairs(maps) do
    local m = ns.Maps and ns.Maps[id]
    local pos = m and m.bounds and D.GetCorpseMapPosition(id)
    if pos and not (ns.IsSecret and ns.IsSecret(pos)) then
      local u, v
      if pos.GetXY then u, v = pos:GetXY() else u, v = pos.x, pos.y end
      if u and v and (u > 0 or v > 0) and u <= 1 and v <= 1 then
        local b = m.bounds
        return Geo.MapCont(id), b[3] - v * (b[3] - b[1]), b[4] - u * (b[4] - b[2])
      end
    end
  end
end

function N.DeathCheck()
  local now = GetTime()
  if now - corpseCheckAt < N.CORPSE_CHECK then return end
  corpseCheckAt = now
  local ghost = UnitIsGhost and UnitIsGhost("player")
  if ns.IsSecret and ns.IsSecret(ghost) then return end
  local body
  if ghost then
    local cont, x, y = CorpseSpot()
    if cont then body = { x = x, y = y, cont = cont, name = L["Your body"], icon = N.CORPSE_ICON, corpse = true } end
  end
  local d = N.stops[1]
  if body and d and d.corpse and d.cont == body.cont and math.abs(d.x - body.x) < 1 and math.abs(d.y - body.y) < 1 then
    N.corpse = true
    return -- already first
  end
  -- take off any body stop (alive again, or it moved), then put it first
  local changed = false
  for i = #N.stops, 1, -1 do
    if N.stops[i].corpse then
      table.remove(N.stops, i)
      changed = true
    end
  end
  if body then
    table.insert(N.stops, 1, body)
    changed = true
  end
  N.corpse = body ~= nil or nil
  if changed then Changed() end
end

---------------------------------------------------------------------------
-- Questing (option, on by default): a stop inside the area of quests in the log (as the
-- map outlines them, overlapping ones too) is done when those quests' objectives are, not
-- when you get there. In one of those areas (N.questing = the quests there) the directions
-- show the objectives, and the arrow still leads to the stop's spot until you've been
-- there (d.spotReached); after that the route waits while you're in the area
-- (N.QuestPaused). Leave before they're done and the route leads back. Then on to the
-- next stop.
---------------------------------------------------------------------------

N.QUEST_CHECK = 0.5 -- seconds between checks
-- The stop's quests done while you're in their area (or after being at its spot): the stop
-- is done. Done outside the area: it's a plain stop again, reached by going there.
local questCheckAt, questCheckVersion = -math.huge, nil

local function QuestActive(id)
  local Q = C_QuestLog
  if not Q then return false end
  local secret = ns.IsSecret or function() return false end
  local complete = Q.IsComplete and Q.IsComplete(id)
  if complete and not secret(complete) then return false end
  local on = Q.IsOnQuest and Q.IsOnQuest(id)
  if Q.IsOnQuest and not secret(on) and not on then return false end -- abandoned or turned in
  return true -- (hidden in combat: still open, until known otherwise)
end

local function QuestingOn()
  return ns.settings and ns.settings.gps.questing ~= false and not N.loop and not N.corpse and ns.Layers
    and ns.Layers.QuestsAt
end

-- The quest route's stops (asked 2026-10-06): within this of a quest's spot (one with no area too), it's being done.
N.QUEST_SPOT_YD = 80
-- Quests turned in (QUEST_TURNED_IN) or dropped (QUEST_REMOVED) this session: their stops are done.
N.questsGone = {}
-- Whether quest `id` is in the log: true, false, or nil when the game hides it (in combat).
local function InLog(id)
  local Q = C_QuestLog
  if N.questsGone[id] then return false end
  if not (Q and Q.IsOnQuest) then return nil end
  local on = Q.IsOnQuest(id)
  if ns.IsSecret and ns.IsSecret(on) then return nil end
  return on and true or false
end
-- Whether a quest route stop's part is done: a turn-in's quest gone from the log (turned in), a quest's spot its
-- objectives done (or the quest gone). False for any other stop.
function N.QuestStopDone(d)
  local id = d and d.quest
  if not id then return false end
  local on = InLog(id)
  if on == false then return true end
  if d.turnin then return false end
  local Q = C_QuestLog
  local complete = Q and Q.IsComplete and Q.IsComplete(id)
  if ns.IsSecret and ns.IsSecret(complete) then return false end
  return complete and true or false
end
-- Quest `id` turned in or dropped (`title`, its name, for stops saved before they carried their quest): every stop
-- of the route for it is done (asked 2026-10-06: "that matching stop name is complete"). The next stop's is left to
-- CheckArrival (it moves on as on arriving); later ones are taken out. Returns how many were.
function N.OnQuestGone(id, title)
  if not id then return 0 end
  N.questsGone[id] = true
  N.ForgetQuest(id) -- (left out of quest routes: moot now)
  local removed = 0
  for i = #N.stops, 1, -1 do
    local d = N.stops[i]
    local match = d.quest == id
      or (not d.quest and d.questRoute and title and (d.name == title or d.name == N.TurnInName(title)
        or d.name == "Turn in: " .. title))
    if match then
      if i == 1 then
        d.quest, d.questDone = id, true
      else
        table.remove(N.stops, i)
        removed = removed + 1
      end
    end
  end
  if removed > 0 then
    N.reorderDue = true
    Changed()
  end
  return removed
end
-- Quests finished since the quest route was made, their turn-in not on it (asked 2026-11-11 for 1.2.3: "show the
-- quest route glow button when quests are completed too so turn ins are added to the route just like new quests
-- suggest a re route"): the Sprint icon pulses in the directions (N.questRouteStale), and chat says so once a quest.
-- N.questsDoneSeen: the log's quests found finished at the last look (questID -> true). The first look of a session,
-- and the quest route made (`seed`), only note them: a quest already finished then is no news.
N.questsDoneSeen = {}
function N.HasTurnIn(id)
  for _, d in ipairs(N.stops) do
    if d.quest == id and d.turnin then return true end
  end
  return false
end
-- `ids`: the quest log's questIDs (Layers.LogQuests). Returns the first quest found newly finished whose turn-in
-- the quest route lacks, or nil.
function N.CheckQuestsDone(ids, seed)
  local Q = C_QuestLog
  if not (Q and Q.IsComplete and ids) then return nil end
  local secret = ns.IsSecret
  if seed or not N.questsDoneSeeded then
    N.questsDoneSeen, N.questsDoneSeeded = {}, true
    seed = true
  end
  local onRoute = not seed and N.OnQuestRoute()
  local found
  for _, id in ipairs(ids) do
    local done = Q.IsComplete(id)
    if not (secret and secret(done)) then -- (hidden in combat: looked at again after it)
      if done and not N.questsDoneSeen[id] then
        N.questsDoneSeen[id] = true
        if onRoute and not N.HasTurnIn(id) and N.QuestRouteTakes(id) then
          found = found or id
          if not N.QuestAutoReroute() then
            ns.Print(L["Quest complete: click the quest route button (Sprint) again to add its turn-in to your route."])
          end
        end
      elseif not done then
        N.questsDoneSeen[id] = nil
      end
    end
  end
  if found then N.MarkQuestRouteStale() end
  return found
end
-- Whether the quest route would take finished quest `id`'s turn-in: not one the player left out, and with "only tracked
-- quests" on (`questTrackedOnly`) one tracked. (Else the Sprint icon pulsed, and the route was made again, for a turn-in
-- it never takes.)
function N.QuestRouteTakes(id)
  if N.QuestDropped({ quest = id, turnin = true }) then return false end
  local st = ns.settings and ns.settings.gps
  local Lay = ns.Layers
  if st and st.questTrackedOnly and Lay and Lay.QuestTracked and not Lay.QuestTracked(id) then return false end
  return true
end
-- The quest route lacks a quest picked up or finished: the Sprint icon pulses in the directions, or with the option on
-- (asked 2026-11-12, `questAutoReroute`, Options > Routing; offered once at the icon's first click,
-- GPS.QuestRerouteClick) the quest route is made again by itself (GPS.AutoQuestRoute: after a moment, not in combat).
function N.QuestAutoReroute()
  local st = ns.settings and ns.settings.gps
  return st and st.questAutoReroute and true or false
end
function N.MarkQuestRouteStale()
  N.questRouteStale = true
  if N.QuestAutoReroute() and ns.GPS and ns.GPS.AutoQuestRoute then ns.GPS.AutoQuestRoute() end
end
-- A quest's turn-in stop's name ("Turn in: <quest>"), and whether a name is one.
function N.TurnInName(title)
  return Format(L["Turn in: %s"], title)
end
function N.IsTurnInName(name)
  if type(name) ~= "string" then return false end
  if name:find("^Turn in: ") then return true end -- (a stop saved in English)
  local pre, post = L["Turn in: %s"]:match("^(.-)%%s(.*)$")
  return pre ~= nil and name:sub(1, #pre) == pre and (post == "" or name:sub(-#post) == post) and #name > #pre + #post
end
-- A quest's stop on the map (its objective's or turn-in's icon, double-clicked; asked 2026-10-08 in the live game: a
-- stop made so was a plain one, tied to its quest only through a traced area, and with the area not traced it showed
-- no objectives and wasn't done when the quest was): the stop carries its quest, as the Quest Route's do.
function N.QuestStop(stop, id)
  if not (stop and id) then return stop end
  stop.quest, stop.questRoute = id, true
  local Q = C_QuestLog
  local complete = Q and Q.IsComplete and Q.IsComplete(id)
  if complete and not (ns.IsSecret and ns.IsSecret(complete)) then
    stop.turnin = true
    if stop.name and not N.IsTurnInName(stop.name) then stop.name = N.TurnInName(stop.name) end
  end
  return stop
end
-- Later quest route stops whose part is done already (an objective finished on the way): taken out. (Nothing is
-- added for a quest done: the route goes on to the stops left, or ends; the user, 2026-10-08: "I'd rather it just stop
-- routing after quest is complete".)
function N.PruneQuestStops()
  local removed = 0
  for i = #N.stops, 2, -1 do
    if N.QuestStopDone(N.stops[i]) then
      table.remove(N.stops, i)
      removed = removed + 1
    end
  end
  if removed > 0 then
    N.reorderDue = true
    Changed()
  end
  return removed
end

-- The stop's quests still to do, sorted. Remembers every quest whose area holds the stop
-- (d.quests): a quest finished drops out of the areas, but still counts as the stop's.
local function StopQuests(d)
  for _, id in ipairs(ns.Layers.QuestsAt(d.cont, d.x, d.y)) do
    d.quests = d.quests or {}
    d.quests[id] = true
  end
  local open = {}
  for id in pairs(d.quests or {}) do
    if QuestActive(id) then open[#open + 1] = id end
  end
  table.sort(open)
  return open
end

-- Every QUEST_CHECK seconds (Status): the next stop's quests, and whether the player is in
-- one of their areas. Sets N.questing, and d.questDone once its quests are all done.
function N.QuestCheck(px, py, cont)
  local d = N.dest
  if not QuestingOn() then
    N.questing, N.areaQuests = nil, nil
    return
  end
  local now = GetTime()
  if now - questCheckAt < N.QUEST_CHECK and questCheckVersion == version then return end
  questCheckAt, questCheckVersion = now, version
  local L = ns.Layers
  -- keep the areas around the player traced, even with the quest areas layer off
  if L.EachArea and C_Map and C_Map.GetBestMapForUnit then
    L.EachArea(cont, px, py, 0, { C_Map.GetBestMapForUnit("player") }, function() end)
  end
  -- the open quests whose areas the player is in (on the way anywhere: N.areaQuests)
  local at = L.QuestsAt(cont, px, py)
  if d and N.PruneQuestStops() > 0 then d = N.dest end -- (later quest stops done on the way: out)
  if not d then -- no route: just the areas you're in (the arrow window shows them)
    N.questing, N.areaQuests = nil, at[1] and at or nil
    return
  end
  -- in the quest area of a later stop: that stop first (already here: faster to do it now)
  local destHere = false
  for _, id in ipairs(L.AreaContains and at or {}) do
    if L.AreaContains(id, d.cont, d.x, d.y) then destHere = true end
  end
  if at[1] and #N.stops > 1 and L.AreaContains and not destHere and not N.keepOrder then -- (not a listed order's)
    for i = 2, #N.stops do
      local s = N.stops[i]
      local hit = false
      for _, id in ipairs(at) do
        if L.AreaContains(id, s.cont, s.x, s.y) then
          s.quests = s.quests or {}
          s.quests[id] = true
          hit = true
        end
      end
      if hit and not s.questDone then
        table.insert(N.stops, 1, table.remove(N.stops, i))
        Changed()
        d = N.dest
        questCheckVersion = version
        break
      end
    end
  end
  if d.quest then
    -- A quest route stop (its `quest`; asked 2026-10-06): done by the quest, never by getting there. Its objectives
    -- done (or the quest gone from the log) for a quest's spot, the quest turned in for a turn-in. Near it
    -- (QUEST_SPOT_YD, a quest with no area too) or in its area, it's what to do now: its objectives, or turning it in;
    -- once its spot's been reached the route waits there (QuestPaused), and leaving leads back.
    if N.QuestStopDone(d) then
      d.questDone = true
      N.questing, N.questTurnIn = nil, nil
      N.areaQuests = at[1] and at or nil
      return
    end
    local near = d.cont == cont and (d.x - px) ^ 2 + (d.y - py) ^ 2 <= N.QUEST_SPOT_YD ^ 2
    local inArea = not d.turnin and L.AreaContains and L.AreaContains(d.quest, cont, px, py)
    local was = N.questing
    if near or inArea then
      N.questing, N.questTurnIn = { d.quest }, d.turnin and true or nil
    else
      N.questing, N.questTurnIn = nil, nil
    end
    if was and not N.questing then N.route = nil end -- left it: the route leads back
    local other = {}
    for _, id in ipairs(at) do
      if id ~= d.quest then other[#other + 1] = id end
    end
    N.areaQuests = other[1] and other or nil
    return
  end
  N.questTurnIn = nil
  local open = StopQuests(d)
  if d.quests and #open == 0 then
    -- all done: in the quest's area (or been at the spot), this stop is reached
    -- (CheckArrival moves on); outside it, it's reached by going there, like any stop
    local inArea = N.questing ~= nil -- in the area at the last check
    for id in pairs(d.quests) do
      if L.AreaContains and L.AreaContains(id, cont, px, py) then inArea = true end
    end
    if inArea or d.spotReached then d.questDone = true end
    N.questing = nil
    N.areaQuests = at[1] and at or nil
    return
  end
  local here, inside, stopQuest = {}, {}, {}
  for _, id in ipairs(at) do inside[id] = true end
  for _, id in ipairs(open) do
    stopQuest[id] = true
    if inside[id] then here[#here + 1] = id end
  end
  local was = N.questing
  N.questing = here[1] and here or nil
  if was and not N.questing then N.route = nil end -- left the area: the route leads back
  -- other quest areas the player is in (not the stop's): shown with the directions
  local other = {}
  for _, id in ipairs(at) do
    if not stopQuest[id] then other[#other + 1] = id end
  end
  N.areaQuests = other[1] and other or nil
end

-- In the stop's quest area, and its spot already reached: the route waits, no arrow.
function N.QuestPaused()
  return N.questing ~= nil and N.dest ~= nil and N.dest.spotReached == true
end

-- The quests being done here (default: the stop's, N.questing), for the directions:
-- { { text, r, g, b }, ... } (titles in gold, objectives white, finished ones gray).
function N.QuestLines(ids)
  local out = {}
  for _, id in ipairs(ids or N.questing or {}) do
    local title, objectives = ns.Layers.QuestObjectives(id)
    out[#out + 1] = { title or string.format(L["Quest %d"], id), 1, 0.82, 0 }
    for _, o in ipairs(objectives) do
      if o.finished then out[#out + 1] = { o.text, 0.55, 0.55, 0.55 } else out[#out + 1] = { o.text, 1, 1, 1 } end
    end
  end
  return out
end

-- Other addons told of each stop reached (API 14, OnArrive, asked 2026-10-05 for a companion's arrival
-- effects): owner -> fn(info), info = { x, y, cont, name, last (the trip's last stop), kind ("stop", "boss") }.
N.arriveHooks = {}
function N.TellArrived(d, last)
  if not next(N.arriveHooks) then return end
  local info = { x = d.x, y = d.y, cont = d.cont, name = d.name, last = last and true or false,
    kind = d.boss and "boss" or "stop" }
  for owner, fn in pairs(N.arriveHooks) do
    local ok, err = pcall(fn, info)
    if not ok and ns.GPS and ns.GPS.LogError then ns.GPS.LogError("arrival hook " .. tostring(owner), err) end
  end
end

-- Reaching a stop that isn't the last one moves on to the next stop; reaching the last
-- one marks the trip as arrived (cleared a few seconds later by Tick). A questing stop
-- (see above) is reached when its quests are done, not by getting there.
local function CheckArrival(px, py, cont)
  local d = N.dest
  while d do
    if d.corpse then return false end -- at your body: it stays until you're alive (DeathCheck)
    local at = cont == d.cont and math.sqrt((d.x - px) ^ 2 + (d.y - py) ^ 2) <= ARRIVED_YD
    -- (a stop on a floor of a building, the player's floor followed there and another: not there yet; Brill's inn,
    -- 2026-10-06: "arrived" on the ground floor under a trainer upstairs)
    if at and N.OffStopFloor(d) then at = false end
    -- (a stop in a room reached through a teleporter: only once the player came in by it, N.RoomWatch)
    if at then
      local room = N.StopRoom(d)
      if room and N.roomIn ~= room then at = false end
    end
    -- (and in it, the stop's room: there. Asked 2026-11-17: "once going through the portal technically the player has
    -- arrived", the trainers in sight from its landing)
    if not at and cont == d.cont and N.roomIn and N.StopRoom(d) == N.roomIn then at = true end
    if d.quest and QuestingOn() and not d.questDone then
      -- a quest route stop: done by its quest (QuestCheck), not by getting there; there, it waits
      if N.QuestStopDone(d) then
        d.questDone = true
      elseif at then
        d.spotReached = true
      end
      at = false
    end
    if not d.questDone and at and QuestingOn() and d.quests and StopQuests(d)[1] then
      d.spotReached = true -- at the spot, its quests still open: stay (see QuestCheck)
      at = false
    end
    if d.rxp or d.zygor or d.polestar or d.questify or d.apr then at = false end -- a guide's step: done when its guide checks it off, not by getting there
    if d.boss then -- a boss: done when it dies (wherever you are), not by getting there
      at = false
      if not d.bossDone and N.BossDead(d) then d.bossDone = true end
    end
    if not (d.questDone or d.served or d.bossDone or at) then break end
    if ns.Feedback and not N.arrivedAt then ns.Feedback.Arrived(d) end
    if not N.arrivedAt then N.TellArrived(d, #N.stops <= 1) end -- (a loop of several never ends)
    if N.loop and #N.stops > 1 then
      -- a loop: this stop goes to the end, on to the next one
      table.insert(N.stops, table.remove(N.stops, 1))
      Changed()
      return false
    end
    if #N.stops <= 1 then
      -- (the last one: the route goes at once; "Arrived" stays up a few seconds, N.Tick. Kept
      -- as the stop until then, running on out of its circle brought the route to it back.)
      N.Clear()
      N.arrivedAt = GetTime()
      return true
    end
    table.remove(N.stops, 1)
    N.reorderDue = true
    Changed()
    d = N.dest
  end
  return false
end

-- "Working out the route...", and now and then said another way (asked, 2026-10-01): in Murloc one time
-- in twenty, gnome engineers at it one in five, goblin engineers another one in five (N.WORKING_FLAVORS:
-- each its share of the times and its lines). Picked once each time a
-- route is being worked out (not every redraw: it would flicker), until there's a route. N.FUN = false:
-- always the plain one (the tests).
N.WORKING_TEXT = L["Working out the route..."]
N.WORKING_FLAVORS = {
  { share = 0.05, lines = { "Mrglglglgl... mrrgll mrgl...", "Aaaaaughibbrgubugbugrguburgle!",
    "Mmmrrglllm... rrrgle mrgl?", "Mrrrggk! Mglrmglmglmgl..." } }, -- (Murloc: the same in every language)
  { share = 0.2, lines = { L["Recalibrating the gyro-o-matic..."], L["Consulting the Tinker Town schematics..."],
    L["Spinning up the Route-o-Tron 3000..."], L["Oiling the cogs of the navigation engine..."] } },
  { share = 0.2, lines = { L["Time is money, friend! Routing..."], L["Charging extra for the shortcut..."] } },
}
N.Random = math.random
local working -- (the text picked while the route is being worked out)
function N.WorkingText()
  if not working then
    working = N.WORKING_TEXT
    if N.FUN ~= false then
      local roll, at = N.Random(), 0
      for _, f in ipairs(N.WORKING_FLAVORS) do
        at = at + f.share
        if roll < at then
          working = f.lines[N.Random(#f.lines)]
          break
        end
      end
    end
  end
  return working
end

-- "Show it, marked" (asked 2026-10-08): a new route still being checked for a shorter way (within FRESH_SECONDS of the
-- stops changing, the background work it started still going: its searches, the walks across country, the ride check;
-- or r.pending) shows at once, faded on the map (GPSFrame's G.CHECKING_ALPHA), with a line in the directions saying so,
-- until it has settled: no such work for CHECK_QUIET (between a finished search and the recalculation it brings there is
-- none for a moment). Then not again for these stops: the searches a reroute starts as the player walks don't fade it.
-- (From Lakeshire's town hall to Darkshire the long way by the roads, 7.6k yd, shows first and the walk over the pass,
-- 1.8k, lands a few seconds on: QA v116-ov-a.) One line a check, picked at random from N.CHECKING_LINES (asked: funny
-- ones, the user's pick), else N.CHECKING_TEXT (N.FUN = false: always it).
N.CHECKING_TEXT = L["Checking for a shorter way..."]
N.CHECKING_LINES = { -- (the user's pick, all 16, 2026-10-08)
  L["Greasing the goblins for a shortcut..."],
  L["Asking the flight master for directions..."],
  L["Bribing a gnome engineer to check the tunnel..."],
  L["Checking whether the zeppelin is late again..."],
  L["Politely asking the murlocs to move..."],
  L["Haggling with a goblin over the toll road..."],
  L["Asking Hogger if he knows a back way..."],
  L["Sending a scout ahead (he'll be fine)..."],
  L["Polishing the Gnomish Shortcut-o-Tron..."],
  L["Checking behind the waterfall..."],
  L["Convincing the kodo to take the other path..."],
  L["Consulting a suspiciously old map..."],
  L["Measuring the Deeprun Tram with a ruler..."],
  L["Waiting for the goblin cartographer to sober up..."],
  L["Checking the shortcut for Defias..."],
  L["Counting the stairs in Ironforge..."],
}
N.CHECK_QUIET = 0.5
settledAt = -1
local checking, workSeen -- ({ version, the line }; { version, at })
function N.Checking()
  local r = N.route
  if not (r and N.dest) or settledAt == version then return false end
  local now, R = GetTime(), ns.Router
  if r.pending or (R and R.HasWork and R.HasWork()) then workSeen = { version, now } end
  local seen = workSeen and workSeen[1] == version and workSeen[2]
  if not N.Fresh() or not seen or now - seen >= N.CHECK_QUIET then
    settledAt = version
    return false
  end
  return true
end
function N.CheckingText()
  if not (checking and checking[1] == version) then
    local list, text = N.CHECKING_LINES, nil
    if N.FUN ~= false and type(list) == "table" and #list > 0 then text = list[N.Random(#list)] end
    checking = { version, type(text) == "string" and text ~= "" and text or N.CHECKING_TEXT }
  end
  return checking[2]
end

-- Text for the nav panel, or nil when there is no destination.
-- Routing paused (asked 2026-11-16: "the ability for routing to be paused ... to save on compute when the player doesnt
-- plan to follow the route but they dont want to remove it just yet"): nothing worked out or drawn, the stops kept, the
-- arrow as on a flight, the directions only saying so. N.paused: "manual" (the Pause Routing button, /agps pause) or
-- "auto" (low performance, the route not followed: N.WatchFollowing). Resumed: worked out again from where you are.
function N.SetPaused(on, why)
  local was = N.paused
  if on and not N.dest then return false end
  N.paused = on and (why or "manual") or nil
  N.pauseWatch = nil
  N.ResetStutter()
  if was ~= N.paused then
    N.route, kept = nil, nil
    -- (resumed: worked out again from where you are, the ride checks' answers kept, remembered by place: forgotten,
    -- each resume worked the whole trip out afresh, its rides and ways round the other faction's guards with it)
    if not N.paused then N.Invalidate(true) end
    Save()
    version = version + 1
    if ns.GPS then
      if ns.GPS.LayoutQuick then ns.GPS.LayoutQuick() end
      if ns.GPS.RefreshQuick then ns.GPS.RefreshQuick() end
      if ns.GPS.Redraw then ns.GPS.Redraw() end
      if ns.GPS.RefreshMinimapResume then ns.GPS.RefreshMinimapResume() end -- (the square's Resume button)
    end
  end
  return true
end
function N.TogglePaused()
  return N.SetPaused(not N.paused, "manual")
end
-- why it's paused, one line (nil when it isn't): the directions' and the square's Resume button's tooltip
function N.PausedHead()
  if not N.paused then return nil end
  return N.paused == "auto" and L["|cffffd100Routing paused: you're not following the route|r"]
    or N.paused == "perf" and L["|cffffd100Routing paused: it was making your game stutter|r"]
    or L["|cffffd100Routing is paused|r"]
end
function N.PausedText()
  local head = N.PausedHead() or L["|cffffd100Routing is paused|r"]
  return head .. "\n" .. L["|cff9d9d9dResume Routing in the map menu, or /agps pause|r"]
end
-- Auto-pause (Options > Performance, its own option, off by default, usable with any settings; asked 2026-11-16: the
-- low-end settings turn it on, going back to the defaults leaves it as it is): the lowest time to the stop seen since
-- the route was set or resumed; past it by AUTO_PAUSE seconds (the option's slider, autoPauseSeconds) for AUTO_PAUSE_HOLD seconds on
-- end, the route isn't being followed: paused. Not in the air or on a boat, in a dungeon, or while its search is
-- still working out the way.
N.AUTO_PAUSE_HOLD = 5
function N.AutoPauseOn()
  local st = ns.settings and ns.settings.gps
  return st and st.autoPauseRouting == true or false
end
-- High compute: the addon's own measured work (ns.PerfTotal, what Options > Performance shows) sampled every
-- COMPUTE_EVERY seconds; over HIGH_COMPUTE_MS a second averaged over the last COMPUTE_WINDOW seconds (at least that
-- long measured) is a lot of work (15 ms a second: 1.5% of a CPU core, about three times a quiet route's).
N.HIGH_COMPUTE_MS, N.COMPUTE_WINDOW, N.COMPUTE_EVERY = 15, 60, 5
local computeSamples = {}
function N.ComputeHigh()
  local now = GetTime()
  local last = computeSamples[#computeSamples]
  if not last or now - last[1] >= N.COMPUTE_EVERY then
    computeSamples[#computeSamples + 1] = { now, ns.PerfTotal and ns.PerfTotal() or 0 }
    while #computeSamples > 2 and now - computeSamples[2][1] >= N.COMPUTE_WINDOW do table.remove(computeSamples, 1) end
  end
  local a, b = computeSamples[1], computeSamples[#computeSamples]
  if not (a and b) or b[1] - a[1] < N.COMPUTE_WINDOW then return false end
  return (b[2] - a[2]) / (b[1] - a[1]) >= N.HIGH_COMPUTE_MS
end
function N.ResetCompute() computeSamples = {} end
-- (asked 2026-11-16: "If high compute is detected for a user and pausing the route condition is detected, ask the
-- user if they would like this feature to be turned on (only outside of combat)") with auto-pause off, the route not
-- followed and the work high: asked once (a session; a No for good, autoPauseDeclined, till the settings are reset),
-- out of combat and with no other question up. Yes: the option on, and paused now (the performance settings as they
-- are).
function N.OfferAutoPause()
  local st = ns.settings and ns.settings.gps
  if not st or st.autoPauseDeclined or N.autoPauseOffered then return false end
  if (InCombatLockdown and InCombatLockdown()) or ns.inCombat then return false end
  if ns.AskShown and ns.AskShown() then return false end
  if not (ns.GPS and ns.GPS.Confirm and N.ComputeHigh()) then return false end
  N.autoPauseOffered = true
  ns.GPS.Confirm(L["AzerothGPS is doing a lot of route work for a route you don't seem to be following. Pause routing automatically when you're not following it?"],
    function()
      st.autoPauseRouting = true
      N.SetPaused(true, "auto")
      local O = ns.Options
      if O and O.Refresh then O.Refresh() end
    end, function(clicked)
      if clicked then st.autoPauseDeclined = true end
    end)
  return true
end
-- Stutter from routing (asked 2026-11-18, Kooki3z: lag spikes going off course on a long route, and nothing noticed
-- them; the auto-pause above is about a route not followed, off by default, and skips a route still searched, and
-- ComputeHigh averages a minute's work, never a frame's). The routing work in one frame, outside the background's jobs
-- (N.Route's, the pump's slice: N.RouteWork), over STUTTER_MS is a slow route frame. STUTTER_HITS of them within
-- STUTTER_WINDOW seconds: routing cut back to the first stop (N.degraded: the way there worked out as always, the
-- stretches after it kept as they are, no `later:` jobs, no reorder, a finished search between stops not redoing
-- them). STUTTER_HITS more within the window, past STUTTER_GRACE seconds of that (the jobs already queued finish):
-- routing paused ("perf"), said in chat and in the directions; resumed by the player. Cut back and no slow route frame
-- for STUTTER_RECOVER seconds: full routing again, quietly (longer than the window: no flapping).
N.STUTTER_MS, N.STUTTER_HITS, N.STUTTER_WINDOW, N.STUTTER_GRACE, N.STUTTER_RECOVER = 25, 3, 60, 5, 90
N.degraded = nil -- (GetTime() when routing was cut back to the first stop)
-- (started over, by a new trip, a pause or a resume, or full routing back: the first STUTTER_RESUME_GRACE seconds aren't
-- counted, the trip worked out again in them; asked 2026-11-18: resumed, a re-plan read as stutter paused it again)
N.STUTTER_RESUME_GRACE = 8
N.STUTTER_SAY_EVERY = 300 -- (the chat line at most this often; the directions say it all along)
local stutter = { hits = {} }
local stutterSaidAt = -math.huge
function N.ResetStutter()
  stutter = { hits = {}, quietUntil = GetTime and GetTime() + N.STUTTER_RESUME_GRACE or nil }
  N.degraded = nil
end
-- (watched as in the game, the route work in the background; the tests' and the route checks' work at once isn't,
-- but with STUTTER_WATCH set)
N.STUTTER_WATCH = false
-- Not while the game is in the background (asked 2026-11-18, Kooki3z: routing paused "due to stutter" with the game's
-- window not focused). What's counted is our own work, timed around it (N.Route's wrapper, the pump's slice), never the
-- time between frames; but that's the clock's time, and with the window in the background the client runs at its
-- background frame cap (maxFPSBk) at a lower priority, and the system can hold it in the middle of our work: a few
-- milliseconds of routing read as tens. There's no focus event in this client (SystemDocumentation, checked
-- 2026-11-18): the frame rate held at that cap (GetFramerate within BG_CAP_SHARE of it, the cap on, `useMaxFPSBk`)
-- is the background, and the first FOCUS_SETTLE seconds back from it don't count either (its average catching up).
-- (A client whose own frame rate sits at its background cap isn't watched there: no false pause, the safe side.)
N.FOCUS_SETTLE, N.BG_CAP_SHARE, N.BG_CAP_EVERY = 5, 0.8, 5
local bgFrames = { capAt = -math.huge }
function N.BackgroundCap()
  local now = GetTime()
  if now - bgFrames.capAt >= N.BG_CAP_EVERY or now < bgFrames.capAt then
    bgFrames.capAt = now
    local cap
    if GetCVar then
      local ok, use = pcall(GetCVar, "useMaxFPSBk")
      local ok2, v = pcall(GetCVar, "maxFPSBk")
      cap = ok2 and tonumber(v) or nil
      if (ok and use == "0") or not cap or cap <= 0 then cap = nil end
    end
    bgFrames.cap = cap
  end
  return bgFrames.cap
end
-- Whether the frames now tell nothing of routing's work: at the background cap, or just back from it.
function N.FramesInBackground(now)
  local cap = N.BackgroundCap()
  local fps = cap and GetFramerate and GetFramerate()
  if fps and fps <= cap + 1 and fps >= cap * N.BG_CAP_SHARE then
    bgFrames.until_ = now + N.FOCUS_SETTLE
    return true
  end
  return bgFrames.until_ ~= nil and now < bgFrames.until_
end
function N.RouteWork(ms)
  local R = ns.Router
  if N.paused or not ms or not ((R.WARM and not R.SYNC_WALKS) or N.STUTTER_WATCH) then return end
  local now = GetTime()
  -- (the option off, Options > Performance: never cut back or paused; cut back already, full again)
  local st = ns.settings and ns.settings.gps
  if st and st.stutterPause == false then
    if N.degraded then
      N.ResetStutter()
      N.Invalidate(true)
    end
    return
  end
  if N.FramesInBackground(now) then
    stutter.frame, stutter.ms, stutter.counted = now, 0, true -- (this frame not counted, whatever comes in it)
    return
  end
  local s = stutter
  if s.quietUntil and now < s.quietUntil then
    s.frame, s.ms, s.counted = now, 0, true
    return
  end
  if N.degraded and now - math.max(N.degraded, s.lastSlow or 0) >= N.STUTTER_RECOVER then
    N.ResetStutter()
    N.Invalidate(true) -- (the stretches after the first stop worked out again, in the background)
    s = stutter
  end
  if s.frame ~= now then s.frame, s.ms, s.counted = now, 0, false end
  s.ms = s.ms + ms
  if s.counted or s.ms < N.STUTTER_MS then return end
  s.counted = true
  if N.degraded and now - N.degraded < N.STUTTER_GRACE then return end
  s.lastSlow = now
  local hits = s.hits
  hits[#hits + 1] = now
  while hits[1] and now - hits[1] > N.STUTTER_WINDOW do table.remove(hits, 1) end
  if #hits < N.STUTTER_HITS then return end
  s.hits = {}
  if not N.degraded then
    N.degraded = now
    return
  end
  N.SetPaused(true, "perf")
  if ns.Print and now - stutterSaidAt >= N.STUTTER_SAY_EVERY then
    stutterSaidAt = now
    ns.Print(L["Routing paused: it was making your game stutter. Resume it with the Pause Routing button or /agps pause."])
  end
end

function N.WatchFollowing(r, cont)
  if N.paused then N.pauseWatch = nil return end
  local auto = N.AutoPauseOn()
  local st0 = ns.settings and ns.settings.gps
  if not auto and (not st0 or st0.autoPauseDeclined or N.autoPauseOffered) then N.pauseWatch = nil return end
  if not auto then N.ComputeHigh() end -- (sampled all along, to have its minute when the route stops being followed)
  if r.pending or r.flying or (UnitOnTaxi and UnitOnTaxi("player")) or (N.CurrentInstance and N.CurrentInstance()) then
    return
  end
  local _, walk, mount, mounted = N.Speeds()
  local speed = (mounted and mount or walk) or 7
  local secs = N.TripSecs(r.walkYards or r.length or 0, r.swimYards, r.rideSeconds, math.max(speed, 1))
  local w = N.pauseWatch
  if not w or w.dest ~= N.dest then
    w = { dest = N.dest, best = secs }
    N.pauseWatch = w
  end
  if secs < w.best then w.best = secs end
  local st = ns.settings.gps
  local over = secs - w.best > (tonumber(st.autoPauseSeconds) or 120)
  local now = GetTime()
  if not over then w.overAt = nil return end
  w.overAt = w.overAt or now
  if now - w.overAt < N.AUTO_PAUSE_HOLD then return end
  if auto then N.SetPaused(true, "auto") else N.OfferAutoPause() end
end

function N.Status(px, py, cont)
  cont = N.PlayerLevel(cont)
  N.TrackCityZ(cont, px, py) -- (down in a city with floors: the player's floor followed as they move)
  N.TrackRaisedZ(cont, px, py) -- (and onto a bridge drawn over the land, from its end)
  N.RoomWatch(px, py, cont) -- (a room reached through a teleporter: the player put there by it)
  N.DeathCheck()
  if not N.dest then
    N.QuestCheck(px, py, cont) -- (no route: the quest areas you're in, for the arrow window)
    if N.arrivedAt then return L["|cff40ff40Arrived|r"] end -- (the last stop just reached)
    return nil
  end
  N.QuestCheck(px, py, cont)
  if CheckArrival(px, py, cont) then return L["|cff40ff40Arrived|r"] end
  if N.paused then return N.PausedText() end
  if N.questing then
    -- in the stop's quest area: the objectives instead of directions (and the way to the
    -- spot, until it's reached)
    if not N.QuestPaused() then N.Route(px, py, cont) end
    local lines = { N.questTurnIn and L["|cffffd100Turn in the quest|r"] or L["|cffffd100In the quest area|r"] }
    local ql = N.QuestLines()
    for _, l in ipairs(N.areaQuests and N.QuestLines(N.areaQuests) or {}) do ql[#ql + 1] = l end
    for _, l in ipairs(ql) do
      lines[#lines + 1] = string.format("|cff%02x%02x%02x%s|r", math.floor(l[2] * 255), math.floor(l[3] * 255), math.floor(l[4] * 255), l[1])
    end
    return table.concat(lines, "\n")
  end
  N.MaybeReorder(px, py, cont)
  local d = N.dest
  local r = N.Route(px, py, cont)
  if r then N.WatchFollowing(r, cont) end -- (low performance: paused when not followed, N.AUTO_PAUSE_*)
  if N.paused then return N.PausedText() end
  if not r then
    if not N.warming then N.AskSkipped() end -- (rides removed: put back?)
    -- (no way but up or down a cliff: the spot can't be walked to, said so, never a line up it. Kooki3z
    -- 2026-11-20: "If I picked a spot that actually isn't reachable then should've said too high or route not
    -- possible")
    if not N.warming and N.noWayCliff then return L["That spot can't be reached on foot from here (a cliff in the way)."] end
    return N.warming and N.WorkingText() or L["No way there found"]
  end
  if N.RedAsking() then return N.RED_ASK_TEXT end -- (not shown until kept)
  working = nil -- (the next time: picked again)
  local cur, walk, mount, mounted, ability = N.Speeds()
  local head = N.FormatDistance(r.length)
  local multi = #N.stops > 1
  if multi then head = string.format("|T%s:14|t 1/%d  %s", N.StopIcon(d), #N.stops, head) end
  local t, from, atDock = NextRide(r, px, py)
  if r.flying then
    head = "|cffffd100" .. N.RidingText(r.flying.kind, r.flying.to) .. "|r  " .. N.RidingWhen(r.flying.kind, r.flying.seconds)
  elseif t then
    local to = ns.RideEndName(t, from == 1 and 2 or 1)
    if t.use then
      head = Format(L["|cffffd100Use %s|r (to %s)"], t[8], to)
    elseif atDock and t.learn then
      head = Format(L["|cffffd100Learn the flight path, then fly to %s|r"], to)
    elseif atDock then
      head = "|cffffd100" .. (N.BOARD[t[8]] and Format(N.BOARD[t[8]], to) or Format(L["Board the %s to %s"], t[8], to)) .. "|r"
    else
      local there = N.TO_RIDE[t[11] or t[8]]
      head = head .. "  " .. (there and Format(there, to) or Format(L["to the %s (then to %s)"], t[11] or t[8], to))
    end
  end
  if cur and cur > 0.5 and not r.flying then
    head = head .. "   " .. Format(L["|cffffffffETA %s|r"], N.FormatTime(N.TripSecs(r.walkYards, r.swimYards, r.rideSeconds, cur)))
  end
  -- walking and mounted times: to the stop, or for the whole trip with several stops
  local yards, ride, line, swim = r.walkYards, r.rideSeconds, "", r.swimYards
  if multi then
    yards, ride, swim = r.totalYards, r.totalRide, r.totalSwim
    local planned = N.PlannedStops()
    line = (planned < #N.stops and not N.loop) and planned or "all"
  end
  local times = N.TimesLine(yards, ride, walk, mount, mounted, ability, swim)
  if line == "all" then
    line = Format(L["All stops: %s"], times)
  elseif line ~= "" then
    line = Format(L["Next %d stops: %s"], line, times)
  else
    line = times
  end
  -- in another quest's area on the way: its objectives first (the times line stays last:
  -- the collapsed panel shows just that)
  if N.areaQuests then
    local q = { L["|cffffd100! In a quest area|r"] }
    for _, l in ipairs(N.QuestLines(N.areaQuests)) do
      q[#q + 1] = string.format("|cff%02x%02x%02x%s|r", math.floor(l[2] * 255), math.floor(l[3] * 255), math.floor(l[4] * 255), l[1])
    end
    head = table.concat(q, "\n") .. "\n" .. head
  end
  local hint = N.HeightText(px, py, cont) or N.FloorText(px, py, cont)
  if hint then head = head .. "\n" .. hint end
  if N.Checking() then head = head .. "\n|cff9d9d9d" .. N.CheckingText() .. "|r" end -- (the route shown faded meanwhile)
  if d.boss and cont == d.cont and math.sqrt((d.x - px) ^ 2 + (d.y - py) ^ 2) <= N.BOSS_NEAR_YD then
    head = "|cffffd100" .. (d.name and Format(L["Defeat %s"], d.name) or L["Defeat the boss"]) .. "|r\n" .. head
  end
  return head .. "\n" .. line
end

-- The flight masters of the player's faction they haven't learned, by the route's walks still ahead
-- (within LEARN_NEAR_YD), in the order the route passes them: a list of { name, off = yards from the
-- route, leg = the walk passing it, along = yards along that walk (its part) to where it passes,
-- cont, x, y = the flight master, rx, ry = the nearest point of the route }, or nil. Each a detour:
-- a brown line on the map from the route to it and its pin (GPSFrame), and a step where that walk
-- passes it (Steps: the walk split there); the route itself isn't changed. Learned on the way, the next trips may fly from it (Taxi.lua sees it on the flight map:
-- the route is worked out again). Only once a flight map has been seen (else what's known isn't),
-- and not with flights turned off.
N.LEARN_NEAR_YD = 450 -- (Tarren Mill from the walk into Arathi: 390 yd off it)
N.LEARN_BY_YD = 40 -- ... this close: "on the way", not a detour
local mastersList
-- Flight masters whose detour the player removed (right-click on its pin: GPSFrame): not suggested
-- again on this route, rerouting or after a /reload (saved with the stops); a new route clears it.
N.skipLearn = {}
function N.SkipLearn(node)
  N.skipLearn[node] = true
  if N.route then N.route.learnAt = nil end
  N.SaveStops()
end
function N.LearnOnRoute(r)
  local st = ns.settings and ns.settings.gps
  if not (r and r.parts) or r.flying or (st and st.useFlights == false) or N.corpse then return nil end
  local fac = Faction()
  -- (a character that knows no flight path yet gets them too: a new one, the user's Alliance character in
  -- Elwynn, 2026-10-01, walked past Lakeshire's with none suggested; one not seen yet, known already, goes when
  -- a flight map's opened, or with right-click, Remove?)
  local known = N.KnownFlightNodes()
  if not fac then return nil end
  local at = math.floor((r.consumed or 0) / 50)
  if r.learnAt == at then return r.learnHint or nil end
  local namesVer = ns.names and ns.names.taxiVer or 0
  if not mastersList or mastersList.ver ~= namesVer then -- (again when the game's names for them came)
    mastersList = { ver = namesVer }
    for node, m in pairs(Masters()) do mastersList[#mastersList + 1] = { node, m } end
  end
  local cands = {}
  for _, e in ipairs(mastersList) do
    local m = e[2]
    -- (not the game's obsolete ones: "zzOLD..." names in its data)
    if not known[e[1]] and not N.skipLearn[e[1]] and m[5] and string.find(m[5], fac, 1, true)
        and not (m[4] or ""):find("^zz") then cands[#cands + 1] = e end
  end
  -- (each flight master: the nearest point of the route's walks to it, if within reach)
  local best = {}
  local near2 = N.LEARN_NEAR_YD * N.LEARN_NEAR_YD
  for pi, part in ipairs(r.parts) do
    local c, pts, kinds = Geo.Base(part.cont), part.pts, part.kinds
    local acc = 0
    for i = 1, #pts - 3, 2 do
      local ax, ay, bx, by = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
      local vx, vy = bx - ax, by - ay
      local L2 = vx * vx + vy * vy
      if kinds[(i + 1) / 2] ~= N.KIND_TRANSPORT then
        for _, e in ipairs(cands) do
          local m = e[2]
          if Geo.Base(m[1]) == c then
            local t = L2 > 0 and math.max(0, math.min(1, ((m[2] - ax) * vx + (m[3] - ay) * vy) / L2)) or 0
            local d2 = (ax + vx * t - m[2]) ^ 2 + (ay + vy * t - m[3]) ^ 2
            local b = best[e[1]]
            if d2 <= near2 and (not b or d2 < b.d2) then
              best[e[1]] = { name = (m[4]:match("^([^,]+)") or m[4]), full = m[4], off = math.sqrt(d2), d2 = d2, node = e[1],
                leg = part.leg, cont = c, x = m[2], y = m[3], rx = ax + vx * t, ry = ay + vy * t,
                part = pi, along = acc + math.sqrt(L2) * t }
            end
          end
        end
      end
      acc = acc + math.sqrt(L2)
    end
  end
  -- (not one the route takes a flight from: learned there, "Learn the flight path, then...")
  local from = {}
  for _, leg in ipairs(r.legs or {}) do
    if leg.ride and leg.ride.pts then from[leg.ride[leg.from == 2 and 10 or 9] or ""] = true end
  end
  -- (in the order the route passes them)
  local list = {}
  for _, b in pairs(best) do
    if not from[b.full] then list[#list + 1] = b end
  end
  table.sort(list, function(a, b) return a.part < b.part or (a.part == b.part and a.along < b.along) end)
  r.learnAt, r.learnHint = at, list[1] and list or false
  return list[1] and list or nil
end

-- A flight master's detour (N.LearnOnRoute's `h`) as walked (asked 2026-11-08: "flight path detour suggestions don't
-- follow roads/paths, they should still do this if possible"): routed from where it leaves the route to the flight
-- master as any walk is, along the roads where they go there (kept with the route's fixed walks, LegRoute: its start
-- taken every DETOUR_SNAP_YD so it isn't routed again as the player moves). Flat { x1, y1, x2, y2, ... } on h.cont, or
-- nil while it's worked out, or with no way found (the straight line then).
-- In the game the walk is worked out in the background (Router.Background), the straight line drawn meanwhile: routed in
-- the redraw itself it was a whole walk search in one frame each time the route moved where the detour leaves it, about
-- 130 ms on a leveling character's routes, most of which pass a flight master not learned yet (reported for 1.2.5 and
-- 1.2.6: "spikes and stuttering of around 130 ms when a route is active").
N.DETOUR_SNAP_YD = 5
N.DETOUR_RETRY = 0.5 -- seconds: a detour still being worked out (or with no way) asked again no sooner (every redraw)
N.DETOUR_KEPT = 64 -- detours worked out kept (by where they leave the route; all let go past this many)
local detourTried = {} -- [key] = when it was last asked and came back with nothing to draw
local detourPaths, detourPathN = {}, 0 -- [key] = the walk's points, once worked out
function N.DetourPath(h)
  if not (h and h.rx and ns.Router and ns.Router.Route) then return nil end
  local k = N.DETOUR_SNAP_YD
  local rx, ry = math.floor(h.rx / k + 0.5) * k, math.floor(h.ry / k + 0.5) * k
  local key = string.format("%d:%d:%d:%s", h.cont, rx, ry, tostring(h.node))
  if detourPaths[key] then return detourPaths[key] end
  local now = GetTime()
  local t = detourTried[key]
  if t and now - t < N.DETOUR_RETRY then return nil end
  local function Keep(r)
    if not r or r.pending or Unwalkable(r) or not r.pts or #r.pts < 4 then
      detourTried[key] = GetTime()
      return nil
    end
    detourTried[key] = nil
    if detourPathN >= N.DETOUR_KEPT then detourPaths, detourPathN = {}, 0 end
    detourPaths[key], detourPathN = r.pts, detourPathN + 1
    return r.pts
  end
  local R = ns.Router
  if R.WARM and not R.SYNC_WALKS and R.Background then -- (as in the game; tests: at once)
    detourTried[key] = now -- (queued: not asked again until it's done or DETOUR_RETRY on)
    R.Background("detour:" .. key, function()
      return LegRoute(h.cont, rx, ry, h.x, h.y, { offroad = false, roads = true }, true)
    end, function(r)
      if Keep(r) and ns.GPS and ns.GPS.Redraw then ns.GPS.Redraw() end
    end)
    return nil
  end
  return Keep(LegRoute(h.cont, rx, ry, h.x, h.y, { offroad = false, roads = true }, true))
end

-- Called every redraw: "Arrived" goes a few seconds after reaching the last stop (the route
-- went at once).
N.ARRIVED_SHOWN = 5
function N.Tick()
  if N.arrivedAt and GetTime() - N.arrivedAt > N.ARRIVED_SHOWN then N.arrivedAt = nil end
  -- (the zones too high and the risk question, once a ride check that held them back is done)
  if N.route and N.routeX and (N.riskQuestion or not N.RideChecking()) then
    N.CheckRedRoute(N.routeX, N.routeY, N.routeCont, GetTime())
  end
  N.CheckHostileRoute() -- (the other faction's territory on a route settled since: said once)
end

-- Heights in an underground city: its floors' height at (x, y) on `level` (the model's
-- own, relative), or nil.
local HTILE = 1600 / 3
local RUN = {} -- (a run's length character: ALPHABET, 1 to 64)
do
  local chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
  for i = 1, #chars do RUN[chars:byte(i)] = i end
end
function N.CityHeight(level, x, y)
  local h, g = ns.CityHeights and ns.CityHeights[level], ns.Terrain and ns.Terrain[level]
  if not (h and g and x) then return nil end
  local k = HTILE / g.cell
  local col = math.floor(((32 - y / HTILE) - g.tx0) * k) + 1
  local row = math.floor(((32 - x / HTILE) - g.ty0) * k) + 1
  local s = h.rows[row]
  if s and h.runs then
    -- (an instance's rows, Data/Instances.lua: runs of a height character and its length;
    -- a row is spelled out the first time it's read)
    h.plain = h.plain or {}
    if not h.plain[row] then
      local out = {}
      for i = 1, #s - 1, 2 do out[#out + 1] = s:sub(i, i):rep(RUN[s:byte(i + 1)] or 1) end
      s = table.concat(out)
      h.rows[row], h.plain[row] = s, true
    end
  end
  local b = s and s:byte(col)
  if not b or b == 46 then return nil end -- (".": no floor)
  if b > 92 then b = b - 1 end -- (the backslash isn't used)
  return (b - 48) * h.step + h.z0
end

-- A stop's height, the game's: its own (a city place's, a boss's), else that of the town place it's at (N.StopHeight:
-- a map click by Brill's Enchanting trainer, upstairs, was routed to the floor under it, going down toward the cellar,
-- though not "arrived" there; the QA runner's dry run, 2026-10-07), or down in an underground city, the floor's under it
-- (the most common near it: N.CityFloor); nil when unknown.
function N.StopZ(d)
  if d.z then return d.z end
  local h = N.StopHeight(d)
  if h then return h end
  local l = ns.CityLevels and ns.CityLevels[d.cont]
  local h = l and l.zoff and N.CityFloor(d.cont, d.x, d.y)
  return h and h + l.zoff or nil
end

-- The player's height in an underground city's own terms (its heights are the model's: the
-- game's height less the level's zoff), or nil when unknown.
function N.PlayerCityZ(level)
  local l = ns.CityLevels and ns.CityLevels[level]
  -- (WoW Forever gives none: the floor followed along the roads, N.TrackCityZ)
  local z = l and l.zoff and (N.PlayerZ() or (N.playerX and N.TrackCityZ(level, N.playerX, N.playerY)))
  return z and z - l.zoff or nil
end

-- The floor a stop is on: the most common floor height within a few yards (a marker can
-- sit on a sliver of another floor, under or beside a counter).
N.FLOOR_AROUND_YD = 4
function N.CityFloor(level, x, y)
  local count, best, bestN = {}, nil, 0
  local r = N.FLOOR_AROUND_YD
  for dx = -r, r, 2 do
    for dy = -r, r, 2 do
      local h = N.CityHeight(level, x + dx, y + dy)
      if h then
        count[h] = (count[h] or 0) + 1
        if count[h] > bestN then best, bestN = h, count[h] end
      end
    end
  end
  return best
end

-- The player's floor unknown (not followed yet: N.TrackCityZ), the height the route starts at by them on `level`, in
-- its own terms (less zoff), or nil: the hint as the route goes. The top floor over them was a walkway: "Below you, 17 yd
-- down" by a merchant on the ring under it, the route 23 yd along the ring (Undercity, 2026-11-14).
N.ROUTE_START_YD = 8
function N.RouteStartCityZ(level, px, py)
  local l = ns.CityLevels and ns.CityLevels[level]
  local p = N.route and N.route.parts and N.route.parts[1]
  if not (l and l.zoff and p and p.cont == level and p.zs and p.zs[1] and p.pts and p.pts[2]) then return nil end
  if (p.pts[1] - px) ^ 2 + (p.pts[2] - py) ^ 2 > N.ROUTE_START_YD ^ 2 then return nil end
  return p.zs[1] - l.zoff
end

-- Where the stop is against the player, up or down: "down" / "up" and yards (nil when on
-- another level: down or up a lift), or nil when it's about level with them.
N.HEIGHT_HINT_YD = 6
function N.HeightHint(px, py, cont)
  local d = N.dest
  if not (d and px and ns.CityLevels) then return nil end
  if N.StopRoom(d) then return nil end -- (through a teleporter: the steps say so, not "Below you")
  -- (what's walked to now: the next stop, or where the next ride (a flight, a lift) is boarded)
  local tc, tx, ty = d.cont, d.x, d.y
  local legs = N.route and N.route.legs
  if legs and legs[1] and legs[1].walk and legs[2] and legs[2].ride then
    local t, from = legs[2].ride, legs[2].from
    tc, tx, ty = from == 1 and t[1] or t[4], from == 1 and t[2] or t[5], from == 1 and t[3] or t[6]
  end
  local lvl = N.PlayerLevel(cont)
  if Geo.Base(tc) ~= Geo.Base(lvl) then return nil end
  if tc ~= lvl then
    if ns.CityLevels[tc] then return "down" end
    if ns.CityLevels[lvl] then return "up" end
    return nil
  end
  -- (in a capital, near a stop with its height: the floor followed along its roads, phase 3; "23 yd below you" from
  -- the Drag for a trainer down in the Cleft)
  if not ns.CityLevels[lvl] then
    if not (tx == d.x and ty == d.y and d.z and N.InCapital(lvl, tx, ty) and N.InCapital(lvl, px, py)) then
      return N.LandHeightHint(lvl, px, py, tx, ty, d)
    end
    if (tx - px) ^ 2 + (ty - py) ^ 2 > N.FLOOR_HINT_YD ^ 2 then return nil end
    local zp = N.FollowedZ(lvl)
    if not zp or math.abs(d.z - zp) < N.HEIGHT_HINT_YD then return nil end
    return d.z < zp and "down" or "up", math.abs(d.z - zp)
  end
  if not ns.CityLevels[lvl] then return nil end
  -- (the player's own height, and the stop's when it has one: not the top floor over them)
  local zoff = ns.CityLevels[lvl].zoff
  local zs = (tx == d.x and ty == d.y and d.z and zoff) and d.z - zoff or N.CityFloor(lvl, tx, ty)
  local zp = N.PlayerCityZ(lvl) or N.RouteStartCityZ(lvl, px, py) or N.CityHeight(lvl, px, py)
  if not (zs and zp) or math.abs(zs - zp) < N.HEIGHT_HINT_YD then return nil end
  return zs < zp and "down" or "up", math.abs(zs - zp)
end

-- Out on the land, near the stop (LAND_HINT_YD): its height against the player's from the map's ground (Ground.lua: the
-- game gives no player height), "Above you, 20 yd up" (Kooki3z 2026-11-20: "since we know on routing height changes, why
-- can't we say when we get closer to the destination how much higher/lower it is?"). The player's: the floor followed
-- (a bridge, N.FollowedZ), else the ground under them; the stop's: its own height, else the ground there. Not in caves
-- or buildings (the ground's height there is the hill over them), nor under LAND_HINT_Z apart (the ground's bumps).
N.LAND_HINT_YD = 80
N.LAND_HINT_Z = 8
function N.GroundAt(level, x, y)
  local GD = ns.Ground
  if not (GD and GD.PointHeight and x and y) then return nil end
  local was = GD.force
  GD.force = true -- (the map's ground data, the road tools open or not)
  local ok, h = pcall(GD.PointHeight, level, x, y)
  GD.force = was
  return ok and type(h) == "number" and h or nil
end
function N.LandHeightHint(lvl, px, py, tx, ty, d)
  if not (tx == d.x and ty == d.y) then return nil end -- (the stop itself, not a ride's dock)
  if (tx - px) ^ 2 + (ty - py) ^ 2 > N.LAND_HINT_YD ^ 2 then return nil end
  local zs = d.z or N.GroundAt(lvl, tx, ty)
  local zp = N.FollowedZ(lvl) or N.GroundAt(lvl, px, py)
  if not (zs and zp) or math.abs(zs - zp) < N.LAND_HINT_Z then return nil end
  return zs < zp and "down" or "up", math.abs(zs - zp)
end

-- Near a stop upstairs or in a cellar (N.FLOOR_HINT_YD): "Upstairs: <it>" / "Downstairs: <it>", for the directions.
N.FLOOR_HINT_YD = 60
function N.FloorText(px, py, cont)
  local d = N.dest
  local fl = d and px and N.StopFloor(d)
  if not fl or Geo.Base(d.cont) ~= Geo.Base(cont) or (d.x - px) ^ 2 + (d.y - py) ^ 2 > N.FLOOR_HINT_YD ^ 2 then return nil end
  return (fl > 0 and "|cffffc080" or "|cff80c0ff")
    .. Format(fl > 0 and L["Upstairs: %s"] or L["Downstairs: %s"], d.name or L["the stop"]) .. "|r"
end

-- On a road with its heights going up or down (stairs or a ramp set with Edit Road's Set Heights, a building's stairs:
-- the route's own heights, never the player's, which the game doesn't give; 1.3.10, issue #685): how far up or down the
-- climb the player is on goes, "12 yd up", from where they are on the route to where it levels off or turns back (within
-- SLOPE_AHEAD_YD). Nil off one, or when it's less than SLOPE_MIN_YD.
N.SLOPE_MIN_YD, N.SLOPE_AHEAD_YD, N.SLOPE_FLAT_Z = 2, 200, 0.05
function N.SlopeHint(part)
  local hs = part and (part.fz or part.zs)
  local pts = part and part.pts
  if not (hs and pts and hs[1] and hs[2]) then return nil end
  local h0 = hs[1]
  local sign = hs[2] > h0 + N.SLOPE_FLAT_Z and 1 or hs[2] < h0 - N.SLOPE_FLAT_Z and -1 or nil
  if not sign then return nil end
  local last, along = h0, 0
  for k = 2, #pts / 2 do
    local h = hs[k]
    if not h or (h - last) * sign <= N.SLOPE_FLAT_Z then break end
    along = along + math.sqrt((pts[2 * k - 1] - pts[2 * k - 3]) ^ 2 + (pts[2 * k] - pts[2 * k - 2]) ^ 2)
    last = h
    if along > N.SLOPE_AHEAD_YD then break end
  end
  local dz = math.abs(last - h0)
  if dz < N.SLOPE_MIN_YD then return nil end
  return sign > 0 and "up" or "down", dz
end
function N.SlopeText()
  local r = N.route
  local way, dz = N.SlopeHint(r and r.parts and r.parts[1])
  if not way then return nil end
  return (way == "down" and "|cff80c0ff" or "|cffffc080")
    .. Format(way == "down" and L["%s down"] or L["%s up"], N.FormatDistance(dz, true)) .. "|r"
end

function N.HeightText(px, py, cont)
  local way, yd = N.HeightHint(px, py, cont)
  if not way then return N.SlopeText() end
  local color = way == "down" and "|cff80c0ff" or "|cffffc080"
  if not yd then return color .. (way == "down" and L["Below you (down a lift)"] or L["Above you (up a lift)"]) .. "|r" end
  return color .. Format(way == "down" and L["Below you, %s down"] or L["Above you, %s up"], N.FormatDistance(yd, true)) .. "|r"
end

-- A stop that's a service (a guard's "Bank", "Auction House", a trainer...) is reached when
-- its window opens near it: any of the bankers, not only the spot the guard marked.
-- (event -> words in the stop's name)
N.SERVICES = {
  BANKFRAME_OPENED = { "bank" },
  AUCTION_HOUSE_SHOW = { "auction" },
  MAIL_SHOW = { "mailbox" },
  TAXIMAP_OPENED = { "flight master", "bat handler", "wind rider", "gryphon", "hippogryph" },
  TRAINER_SHOW = { "trainer" },
  MERCHANT_SHOW = { "vendor", "merchant", "supplies", "goods" },
}
N.SERVICE_YD = 60
function N.OnService(event, px, py, cont)
  local words, d = N.SERVICES[event], N.dest
  if not (words and d and d.name and px) or d.corpse then return false end
  if Geo.Base(d.cont) ~= Geo.Base(cont) or (d.x - px) ^ 2 + (d.y - py) ^ 2 > N.SERVICE_YD ^ 2 then return false end
  local name = d.name:lower()
  for _, w in ipairs(words) do
    if name:find(w, 1, true) then
      d.served = true
      return true
    end
  end
  return false
end

-- The highest drop off a ledge the player survives with health to spare: falls up to
-- FALL_FREE yards cost nothing, then about FALL_PER_YD of their health each yard. A ghost
-- takes no fall damage; in combat (health hidden) only the free ones.
N.FALL_FREE = 14
N.FALL_PER_YD = 0.02
N.FALL_KEEP = 0.3 -- of their health left after the fall, at least
-- (this client hides the player's health from addons, out of combat too: out of combat it's taken as FALL_SECRET_HEALTH
-- of the most, health coming back out of combat, so the safe jumps down a capital's ledges are routed (Kooki3z
-- 2026-11-20 in Orgrimmar: "should be jumpable cliffside, you can safely jump down from areas in org"; 22 yd from
-- by the Hall of Legends to the Valley of Strength). In combat only the free ones.)
N.FALL_SECRET_HEALTH = 0.8
function N.SafeDrop()
  if UnitIsGhost and UnitIsGhost("player") then return math.huge end
  local h = UnitHealth and UnitHealth("player")
  local m = UnitHealthMax and UnitHealthMax("player")
  if h and ns.IsSecret and ns.IsSecret(h) then
    local fight = UnitAffectingCombat and UnitAffectingCombat("player")
    if fight == false then return N.FALL_FREE + math.max(0, N.FALL_SECRET_HEALTH - N.FALL_KEEP) / N.FALL_PER_YD end
    return N.FALL_FREE
  end
  if not h or not m or (ns.IsSecret and (ns.IsSecret(h) or ns.IsSecret(m))) or m <= 0 then return N.FALL_FREE end
  return N.FALL_FREE + math.max(0, h / m - N.FALL_KEEP) / N.FALL_PER_YD
end

do -- the bags or spells changed: water's speed looked at again (N.WaterChanged)
  local ok, f = pcall(CreateFrame, "Frame")
  if ok and f then
    for _, e in ipairs({ "BAG_UPDATE", "BAG_UPDATE_DELAYED", "SPELLS_CHANGED", "LEARNED_SPELL_IN_TAB" }) do
      pcall(f.RegisterEvent, f, e)
    end
    f:SetScript("OnEvent", function() N.WaterChanged() end)
  end
end

do -- a service's window opening (see N.SERVICES)
  local ok, f = pcall(CreateFrame, "Frame")
  if ok and f then
    for e in pairs(N.SERVICES) do pcall(f.RegisterEvent, f, e) end
    f:SetScript("OnEvent", function(_, e)
      local px, py, cont = Geo.PlayerWorld()
      if N.OnService(e, px, py, cont) and ns.GPS and ns.GPS.Redraw then ns.GPS.Redraw() end
    end)
    if ns.TimeScript then ns.TimeScript(f, "OnEvent", "events (routes)") end
  end
end
