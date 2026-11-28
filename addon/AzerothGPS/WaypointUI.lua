-- Waypoint UI (Kooki3z for 1.4.2: "do WaypointUI too"): with the Waypoint UI addon loaded, the route's next stop is its
-- waypoint, through its own API (WaypointUIAPI.Navigation, its API.lua): its map pin, its distance and arrival time,
-- and its marker in the world where the client draws one. It moves on to each next stop as the route does and goes when
-- the route ends or is cleared. Ours is marked by its flag (W.FLAG), so only ours is ever moved or cleared: a waypoint
-- the player set themselves (Waypoint UI's own, the game's map pin, a /way) is never replaced, nor a quest or anything
-- else the game is super-tracking (super-tracking ours would take that one's place). Our own map never takes ours for a
-- map pin of the player's (Import.lua's I.OnUserWaypoint). Option `waypointUI` (Options > Directions), on by default.
-- The stop, not the next turn: the arrow already points along the roads, and a waypoint moved at every turn would
-- churn its pins and sounds.
local _, ns = ...

local W = {}
ns.WaypointUI = W

W.FLAG = "AzerothGPS_Waypoint" -- (Waypoint UI's flags: whose waypoint it is)
W.TICK = 1 -- s between looks at the route
W.fed = nil -- the place ours was last set to ("<uiMapID>:<x>:<y>"), nil when none is ours
-- (the place we last set the game's waypoint to, in the world (W.GamePin's), kept while the game's waypoint may still be
-- there: Waypoint UI drops its record of ours (its flag) on its own, a quest super-tracked, ours cleared with pathfinding
-- on, and leaves the game's waypoint where we put it. Without this, that one was the player's: our map's pin, and a stop
-- again after the player removed it (Kooki3z 1.4.2: "I remove, add another and the old one is still there and a stop
-- gets added"). Forgotten once the game has no waypoint, or a pin of the player's is taken.)
W.last = nil

-- Waypoint UI's navigation API, or nil without the addon.
function W.API()
  local api = rawget(_G, "WaypointUIAPI")
  local nav = type(api) == "table" and rawget(api, "Navigation")
  if type(nav) ~= "table" or type(nav.NewUserNavigation) ~= "function" or type(nav.GetUserNavigation) ~= "function"
      or type(nav.ClearUserNavigation) ~= "function" then
    return nil
  end
  return nav
end
function W.Available() return W.API() ~= nil end

-- Sending stops to it (the option, and the addon there).
function W.On()
  local st = ns.settings and ns.settings.gps
  return (st and st.waypointUI ~= false and W.Available()) and true or false
end

-- Waypoint UI's waypoint now is ours.
function W.Ours()
  local nav = W.API()
  if not nav then return false end
  local ok, cur = pcall(nav.GetUserNavigation)
  return (ok and type(cur) == "table" and cur.flags == W.FLAG) and true or false
end

-- The game's waypoint is the one we just set or are clearing (Import.lua's map pin leaves it alone): while we're at it,
-- or the game's waypoint at the place ours was set to.
function W.Key(mapID, u, v) return string.format("%d:%.4f:%.4f", tonumber(mapID) or 0, u, v) end
function W.IsOursNow()
  if W.busy then return true end
  if not (C_Map and C_Map.GetUserWaypoint) then return false end
  local ok, wp = pcall(C_Map.GetUserWaypoint)
  local pos = ok and type(wp) == "table" and wp.position
  if type(pos) ~= "table" or not (wp.uiMapID and pos.x and pos.y) then return false end
  local here = W.Key(wp.uiMapID, pos.x, pos.y)
  if here == W.fed then return true end
  if W.last and W.Near(W.last, W.GamePin()) then return true end -- (ours, left there: W.last)
  -- (after a /reload Waypoint UI puts back the one it had, ours: by its own record of it)
  local nav = W.API()
  local okN, cur = false, nil
  if nav then okN, cur = pcall(nav.GetUserNavigation) end
  return (okN and type(cur) == "table" and cur.flags == W.FLAG and tonumber(cur.mapID) and tonumber(cur.x)
    and tonumber(cur.y) and W.Key(cur.mapID, cur.x, cur.y) == here) and true or false
end

-- The player has a waypoint of their own, or the game super-tracks something else (a quest): left as it is.
function W.PlayerHas()
  local nav = W.API()
  local ok, cur = pcall(nav.GetUserNavigation)
  if ok and type(cur) == "table" and cur.flags ~= W.FLAG then return true end
  if ns.Import and ns.Import.MapPin and ns.Import.MapPin() then return true end -- (our map's pin: theirs)
  if C_Map and C_Map.HasUserWaypoint then
    local okH, has = pcall(C_Map.HasUserWaypoint)
    if okH and has and not W.IsOursNow() then return true end -- (the game's pin, not ours: the player's)
  end
  local ST = rawget(_G, "C_SuperTrack")
  if ST and ST.IsSuperTrackingAnything then
    local okA, any = pcall(ST.IsSuperTrackingAnything)
    local okU, user = pcall(function() return ST.IsSuperTrackingUserWaypoint and ST.IsSuperTrackingUserWaypoint() end)
    if okA and any == true and not (okU and user == true) then return true end
  end
  return false
end

-- Where ours should be: the next stop, as the game's map point (uiMapID, x, y from 0 to 1) and its name; nil without a
-- route, or with a stop no zone map has (a dungeon's).
function W.Target()
  local N, I = ns.Nav, ns.Import
  local d = N and N.dest
  if not (d and d.x and d.y and d.cont and I and I.MapPoint) then return nil end
  local mapID, u, v = I.MapPoint(d.cont, d.x, d.y)
  if not (mapID and u and v) then return nil end
  return mapID, u, v, d.name
end

-- The game's waypoint taken away (Waypoint UI's own goes with it: its USER_WAYPOINT_UPDATED).
local function ClearGame()
  if not (C_Map and C_Map.HasUserWaypoint and C_Map.ClearUserWaypoint) then return false end
  local ok, has = pcall(C_Map.HasUserWaypoint)
  if not (ok and has) then return false end
  W.busy = true
  pcall(C_Map.ClearUserWaypoint)
  W.busy = nil
  return true
end

-- Ours taken away (the route over, the option off, a stop it can't show): Waypoint UI's, and the game's waypoint when
-- it's still ours (left there by Waypoint UI), never a waypoint of the player's.
function W.Clear()
  W.fed = nil
  local did = false
  if W.Ours() then
    W.busy = true
    pcall(W.API().ClearUserNavigation)
    W.busy = nil
    did = true
  end
  if W.last and not W.PlayersNav() and W.Near(W.last, W.GamePin()) then did = ClearGame() or did end
  W.last = nil
  return did
end

-- Waypoint UI has a waypoint of the player's (not ours).
function W.PlayersNav()
  local nav = W.API()
  if not nav then return false end
  local ok, cur = pcall(nav.GetUserNavigation)
  return (ok and type(cur) == "table" and cur.flags ~= W.FLAG) and true or false
end

-- One look: ours set to the next stop, moved on, or cleared. True when Waypoint UI was told something.
function W.Tick()
  if not W.Available() then
    W.fed = nil
    return false
  end
  W.DropRemovedPin()
  local mapID, u, v, name
  if W.On() then mapID, u, v, name = W.Target() end
  if not mapID then return W.Clear() end
  local ours = W.Ours()
  if not ours and W.PlayerHas() then -- (theirs: never replaced; ours again once theirs is gone)
    W.fed = nil
    return false
  end
  local key = W.Key(mapID, u, v)
  if ours and W.fed == key then return false end
  W.busy = true
  local ok, made = pcall(W.API().NewUserNavigation, {
    name = name, mapID = mapID, x = u * 100, y = v * 100, flags = W.FLAG, suppressAudio = true,
  })
  W.busy = nil
  if not (ok and made) then return W.Clear() end -- (a place it can't take: none of ours left on the last stop)
  W.fed = key
  W.last = W.PointPin(mapID, u, v)
  return true
end

---------------------------------------------------------------------------
-- The player's pins as stops (Kooki3z for 1.4.2: "when [Waypoint UI's] installed and user uses ctrl-click and sets a
-- pin, auto add that as a stop as well"). Waypoint UI 1.7.5's Ctrl-click pins (its world map and minimap ones, and the
-- game's own world map's) all end as the game's waypoint (C_Map.SetUserWaypoint, USER_WAYPOINT_UPDATED): each new one
-- the player sets is a stop, the route's last, or a route to it. Not one of them: ours (W.IsOursNow: the next stop sent
-- to it, by the place it was sent to and by its flag, not by when), a step of Waypoint UI's own pathfinding on the way to
-- a pin (its IsPathStepWaypointTracked), the one there at login (or put back then: Import's saved map pin), a pin seen
-- before, or one on a stop the route has. A pin cleared leaves its stop; its stop removed (or reached, or the route
-- cleared) takes the pin away, when it's still the game's waypoint (W.DropRemovedPin). Option `waypointUIPins`, on by
-- default.
---------------------------------------------------------------------------
W.NEAR = 5 -- yd: a pin this close to a stop, or to a pin seen before, is that one
W.MAX_SEEN = 50 -- the pins remembered (W.seen), the oldest forgotten first
W.seen = {} -- { cont, x, y }: the player's pins seen (taken as stops or there at login), never taken again
W.ready = false -- (W.Seed at login: until then the game's waypoint is the one it kept, not a new pin)
W.made = nil -- { cont, x, y }: the player's pin last made a stop, while it is the game's waypoint (W.DropRemovedPin)

function W.PinsOn()
  local st = ns.settings and ns.settings.gps
  return (st and st.waypointUIPins ~= false and W.Available()) and true or false
end

-- The game's waypoint as a spot in the world, { cont, x, y, name } (Import.ParseMapPin, as a map pin link from chat is
-- read), or nil without one or off any zone map.
function W.GamePin()
  if not (C_Map and C_Map.HasUserWaypoint and C_Map.GetUserWaypoint) then return nil end
  local okH, has = pcall(C_Map.HasUserWaypoint)
  if not (okH and has) then return nil end
  local ok, wp = pcall(C_Map.GetUserWaypoint)
  local pos = ok and type(wp) == "table" and wp.position
  local mapID, u, v = type(wp) == "table" and tonumber(wp.uiMapID), type(pos) == "table" and tonumber(pos.x),
    type(pos) == "table" and tonumber(pos.y)
  return W.PointPin(mapID, u, v)
end
-- A map point (uiMapID, x, y from 0 to 1) in the world, as W.GamePin reads the game's.
function W.PointPin(mapID, u, v)
  if not (mapID and u and v and ns.Import and ns.Import.ParseMapPin) then return nil end
  return ns.Import.ParseMapPin(string.format("worldmap:%d:%d:%d", mapID, math.floor(u * 10000 + 0.5),
    math.floor(v * 10000 + 0.5)))
end

function W.Near(a, b)
  local Geo = ns.Geo
  if not (a and b and a.x and b.x and a.cont and b.cont and Geo) then return false end
  return Geo.Base(a.cont) == Geo.Base(b.cont) and (a.x - b.x) ^ 2 + (a.y - b.y) ^ 2 <= W.NEAR * W.NEAR
end
local Near = W.Near

local function Seen(p)
  for _, s in ipairs(W.seen) do
    if Near(s, p) then return true end
  end
  return false
end
local function Remember(p)
  if not p or Seen(p) then return end
  table.insert(W.seen, { cont = p.cont, x = p.x, y = p.y })
  while #W.seen > W.MAX_SEEN do table.remove(W.seen, 1) end
end

-- At login: the game's waypoint then, and our map's saved pin (Import.RestoreMapPin puts it back as the game's), are
-- pins of before, not new ones.
function W.Seed()
  local I = ns.Import
  local p = I and I.MapPin and I.MapPin()
  if p then Remember(p) end
  Remember(W.GamePin())
  W.ready = true
end

-- A Waypoint UI pathfinding step: a waypoint of its own on the way to the player's pin, not a pin.
function W.PathStep()
  local nav = W.API()
  if not (nav and type(nav.IsPathStepWaypointTracked) == "function") then return false end
  local ok, step = pcall(nav.IsPathStepWaypointTracked)
  return (ok and step == true) and true or false
end

-- The stop a pin of the player's made is gone (removed, the route cleared, reached): that pin goes too, when it's still
-- the game's waypoint, so nothing takes it for a pin again (Waypoint UI's own record of it with it). True when it went.
function W.DropRemovedPin()
  local made = W.made
  if not made then return false end
  local pin = W.GamePin()
  if not Near(made, pin) then
    W.made = nil -- (the game's waypoint is another now, or none: that pin is gone already)
    return false
  end
  for _, d in ipairs(ns.Nav and ns.Nav.stops or {}) do
    if Near(d, made) then return false end -- (its stop still on the route)
  end
  W.made = nil
  local nav = W.API()
  if nav and W.PlayersNav() then
    W.busy = true
    pcall(nav.ClearUserNavigation)
    W.busy = nil
  end
  -- (the player's pin, not ours: our map's pin, which follows the game's waypoint, goes with it; Import.ClearMapPin)
  if ns.Import and ns.Import.ClearMapPin then pcall(ns.Import.ClearMapPin) else ClearGame() end
  return true
end

-- USER_WAYPOINT_UPDATED: the player's new pin made a stop. True when it was.
function W.OnUserWaypoint()
  if not (W.ready and W.Available()) then return false end
  local pin = W.GamePin()
  if not pin then
    W.last = nil -- (none: ours, if it was, is gone)
    return false
  end
  if W.IsOursNow() or W.PathStep() or Seen(pin) then return false end
  Remember(pin)
  W.last = nil -- (the player's pin over ours: ours gone)
  if not W.PinsOn() then return false end
  local N = ns.Nav
  if not N then return false end
  for _, d in ipairs(N.stops) do
    if Near(d, pin) then return false end -- (already a stop: a shared pin clicked in chat, Import.AddMapPin)
  end
  local stop = { cont = pin.cont, x = pin.x, y = pin.y, name = pin.name }
  local L = ns.L or setmetatable({}, { __index = function(_, k) return k end })
  if #N.stops > 0 then
    local ok, asked = N.AddStop(stop, false) -- (the last stop, as placed: not ordered in)
    if not ok then
      if not asked then ns.Print(string.format(L["Map pin: the route is full (%d stops at most)."], N.MAX_STOPS)) end
      return false -- (or a zone too high for the character: asked first)
    end
  elseif N.SetStops({ stop }) == false then
    return false
  end
  W.made = pin
  ns.Print(string.format(L["Waypoint UI pin added to your route: %s"], pin.name))
  if ns.GPS and ns.GPS.RouteChanged then ns.GPS.RouteChanged() end
  return true
end

if CreateFrame then
  W.events = CreateFrame("Frame")
  W.events:RegisterEvent("PLAYER_LOGIN")
  pcall(W.events.RegisterEvent, W.events, "USER_WAYPOINT_UPDATED")
  W.events:SetScript("OnEvent", function(_, event)
    local ok, err = pcall(event == "PLAYER_LOGIN" and W.Seed or W.OnUserWaypoint)
    if not ok and ns.GPS and ns.GPS.LogError then ns.GPS.LogError("waypoint ui pin", err) end
  end)
end

if C_Timer and C_Timer.NewTicker then
  W.ticker = C_Timer.NewTicker(W.TICK, function()
    local ok, err = pcall(W.Tick)
    if not ok and ns.GPS and ns.GPS.LogError then ns.GPS.LogError("waypoint ui", err) end
  end)
end
