-- Taxi: records known flight masters and learned flight durations into
-- SavedVariables. Read-only observation; never selects or takes a flight.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)
local Format = ns.Format or string.format

local T = {}
ns.Taxi = T

local pending -- { from, to, fromNode, toNode } set when a flight is chosen
local flightStart
local loadedAt = GetTime and GetTime() or 0 -- (and again at login: T.RESTORE_GRACE)

local function KnownState(state)
  -- Enum.FlightPathState: 0 Current, 1 Reachable, 2 Unreachable
  return state == 0 or state == 1
end

-- The flights known among `nodes` as one text (node ids in order): two lists with the same one route the same.
function T.KnownKey(nodes)
  local ids = {}
  for _, n in ipairs(nodes or {}) do
    if n.known and n.nodeID then ids[#ids + 1] = n.nodeID end
  end
  table.sort(ids)
  return table.concat(ids, ",")
end

-- The names among `nodes` as one text (node ids in order, each with its name).
function T.NamesKey(nodes)
  local parts = {}
  for _, n in ipairs(nodes or {}) do
    if n.nodeID then parts[#parts + 1] = n.nodeID .. "=" .. tostring(n.name) end
  end
  table.sort(parts)
  return table.concat(parts, ";")
end

local function StoreNodes(mapID, nodes, source)
  if not nodes then return 0 end
  local cdb = ns.CharDB()
  -- (a node read with no state, the continents' maps away from a flight master: the game doesn't say whether it's
  -- known, so what was saved for it stays. The login read wrote every flight master unknown, and one marked known at
  -- "New flight path discovered!" was lost at the next login, reported 2026-11-13)
  local before = {}
  for _, n in ipairs(cdb.taxiNodes[mapID] and cdb.taxiNodes[mapID].nodes or {}) do
    if n.nodeID and n.known then before[n.nodeID] = true end
  end
  local out = {}
  for _, n in ipairs(nodes) do
    local known = KnownState(n.state)
    if n.state == nil and n.nodeID and before[n.nodeID] then known = true end
    out[#out + 1] = {
      nodeID = n.nodeID,
      name = n.name,
      x = n.position and n.position.x,
      y = n.position and n.position.y,
      state = n.state,
      known = known,
      slotIndex = n.slotIndex,
    }
  end
  -- (only when the flights known changed: every talk to a flight master threw the route away and worked it out
  -- again, the map refreshing each time, a player's report 2026-11-10)
  local changed = T.KnownKey(cdb.taxiNodes[mapID] and cdb.taxiNodes[mapID].nodes) ~= T.KnownKey(out)
  local renamed = T.NamesKey(cdb.taxiNodes[mapID] and cdb.taxiNodes[mapID].nodes) ~= T.NamesKey(out)
  cdb.taxiNodes[mapID] = { time = time(), source = source, nodes = out }
  -- (the game's names for the flight masters, shown in its language: ns.TaxiName; the flights' names made again)
  if renamed and ns.TaxiNamesChanged then ns.TaxiNamesChanged() end
  if changed and ns.Nav and ns.Nav.FlightsChanged then ns.Nav.FlightsChanged() end -- routes may fly now
  return #out
end
T.StoreNodes = StoreNodes

local function CurrentNode()
  for i = 1, NumTaxiNodes() do
    if TaxiNodeGetType(i) == "CURRENT" then return i end
  end
end

local function OnTaxiMapOpened()
  local mapID = GetTaxiMapID and GetTaxiMapID()
  if not mapID then return end
  local n = StoreNodes(mapID, C_TaxiMap.GetAllTaxiNodes(mapID), "taximap")
  ns.Print(Format(L["recorded %d flight nodes for map %d"], n, mapID))
end

-- The flights known read again from the game, away from a flight master (the continents' maps): at login, and when
-- a flight path is discovered. True when the flights known changed.
T.MAPS = { 1414, 1415 }
function T.Refresh(source)
  local cdb = ns.CharDB()
  local changed = false
  for _, mapID in ipairs(T.MAPS) do
    pcall(function()
      local before = T.KnownKey(cdb.taxiNodes[mapID] and cdb.taxiNodes[mapID].nodes)
      StoreNodes(mapID, C_TaxiMap.GetTaxiNodesForMap(mapID), source)
      if T.KnownKey(cdb.taxiNodes[mapID] and cdb.taxiNodes[mapID].nodes) ~= before then changed = true end
    end)
  end
  return changed
end

function T.OnLogin()
  loadedAt = GetTime()
  -- If the API exposes known nodes without visiting a flight master, keep
  -- a fresh copy from login. Phase 0 probe reports whether this works.
  T.Refresh("login")
end

-- "New flight path discovered!" (asked 2026-11-10: a right-click on the flight master is enough, the flight map
-- never opened): the flights known read again, so the routes may fly from there at once. Where the game's list
-- doesn't have it yet, the flight master the player stands at (the node nearest on the continent's map, within
-- T.DISCOVER_NEAR of it) is marked known; the next read (a login, the flight map) puts the game's own in its place.
T.DISCOVER_AFTER = 0.5 -- s after the message: the game's list has it by then
T.DISCOVER_NEAR = 0.004 -- of the continent's map (some 150 yd)
function T.MarkNearest()
  local cdb = ns.CharDB()
  for _, mapID in ipairs(T.MAPS) do
    local ok, pos = pcall(function() return C_Map.GetPlayerMapPosition(mapID, "player") end)
    local entry = cdb.taxiNodes[mapID]
    if ok and pos and entry then
      local px, py = pos.x, pos.y
      if pos.GetXY then px, py = pos:GetXY() end
      local best, bd
      for _, n in ipairs(entry.nodes) do
        if n.x and n.y and px and py then
          local d = math.sqrt((n.x - px) ^ 2 + (n.y - py) ^ 2)
          if d <= T.DISCOVER_NEAR and (not bd or d < bd) then best, bd = n, d end
        end
      end
      if best and not best.known then
        best.known = true
        entry.source = "discovered"
        if ns.Nav and ns.Nav.FlightsChanged then ns.Nav.FlightsChanged() end
        return best
      end
    end
  end
end

function T.OnDiscovered()
  if not T.Refresh("discovered") then T.MarkNearest() end
end

-- The flight being flown, kept in the character's saved data (cdb.flying) so a /reload in the air (or a relog the
-- game keeps them flying through) still knows where it lands and when it took off ("/reload on a flight breaks the
-- routing pause and timer", 2026-11-17: both were only in this file's locals, the route worked out again from the
-- moving player and "lands in" the whole flight again). { from, to (names, as the flight map's), fromNode, toNode
-- (node ids, as Data/Pois.lua's, when the game gave them), at (server time it took off), start (GetTime then) }.
T.FLIGHT_STALE = 1800 -- s: a flight saved longer ago than this isn't the one being flown
T.RESTORE_GRACE = 10 -- s after the files load: not on a taxi yet isn't taken as landed (the game puts them back on)
local function ServerNow() return (GetServerTime and GetServerTime()) or time() end
local function Saved()
  local ok, cdb = pcall(ns.CharDB)
  return ok and cdb or nil
end

-- The flight master's node id for slot `slot` of the flight map open (and the one there: `here`), when the game says.
local function SlotNodes(slot)
  local mapID = GetTaxiMapID and GetTaxiMapID()
  local nodes = mapID and C_TaxiMap and C_TaxiMap.GetAllTaxiNodes and C_TaxiMap.GetAllTaxiNodes(mapID) or {}
  local here, to
  for _, n in ipairs(nodes) do
    if n.state == 0 then here = n.nodeID end -- (Enum.FlightPathState.Current)
    if n.slotIndex == slot then to = n.nodeID end
  end
  return here, to
end

-- The flight master picked on the flight map (slot `slot`): the flight that follows is to it.
function T.Took(slot)
  local from = CurrentNode()
  pending = { from = from and TaxiNodeName(from), to = TaxiNodeName(slot) }
  local ok, fromNode, toNode = pcall(SlotNodes, slot)
  if ok then pending.fromNode, pending.toNode = fromNode, toNode end
  local cdb = Saved()
  if cdb then
    cdb.flying = { from = pending.from, to = pending.to, fromNode = pending.fromNode, toNode = pending.toNode }
  end
end

-- Remember which node the player picked (hook only observes the call).
if TakeTaxiNode then
  hooksecurefunc("TakeTaxiNode", function(slot) pcall(T.Took, slot) end)
end

-- In the air with no take-off seen this session: the saved flight, when it's the one being flown (it took off, not
-- long ago), else it took off now. Its take-off kept in the saved data either way.
local function Airborne()
  local now, snow = GetTime(), ServerNow()
  local cdb = Saved()
  local s = cdb and cdb.flying
  if s and s.at and not pending and snow - s.at >= 0 and snow - s.at <= T.FLIGHT_STALE then
    -- (after a /reload GetTime runs on; after a relog or a restart it doesn't: then by the server's clock)
    local start = s.start
    if not (start and start <= now and math.abs((now - start) - (snow - s.at)) <= 3) then start = now - (snow - s.at) end
    pending = { from = s.from, to = s.to, fromNode = s.fromNode, toNode = s.toNode }
    flightStart = start
    s.start = start
    return
  end
  flightStart = now
  if cdb then
    local p = pending or {}
    cdb.flying = { from = p.from, to = p.to, fromNode = p.fromNode, toNode = p.toNode, at = snow, start = now }
  end
end

-- The flight the player is on: { from, to (flight master names, as the flight map shows
-- them), fromNode, toNode (node ids, when known), start (GetTime) }, or nil when not flying. `to` is unknown when
-- the flight was picked another way than the flight map (a quest's flight) or saved before this version.
local OnTaxiChanged
function T.Current()
  local on = UnitOnTaxi and UnitOnTaxi("player")
  if not on then
    if flightStart and OnTaxiChanged then pcall(OnTaxiChanged) end -- (landed: its time recorded)
    -- (a saved flight not flown any more: landed while away, or logged in on the ground)
    local cdb = not flightStart and GetTime() - loadedAt > T.RESTORE_GRACE and Saved()
    if cdb and cdb.flying and cdb.flying.at then cdb.flying = nil end
    return nil
  end
  -- (taken off: the clock starts now if the control events didn't start it. This client doesn't fire
  -- them for flights, so the start was "now" at every redraw and the countdown sat at the whole flight's
  -- time, reported 2026-10-01; and no flight's time was ever learned)
  if not flightStart then Airborne() end
  return { from = pending and pending.from, to = pending and pending.to, fromNode = pending and pending.fromNode,
    toNode = pending and pending.toNode, start = flightStart }
end

OnTaxiChanged = function()
  local onTaxi = UnitOnTaxi("player")
  if onTaxi and not flightStart then
    Airborne()
  elseif not onTaxi and flightStart then
    local secs = GetTime() - flightStart
    flightStart = nil
    if pending and pending.from and pending.to and secs > 5 then
      local flights = ns.CharDB().flights
      local key = pending.from .. " > " .. pending.to
      local f = flights[key] or { from = pending.from, to = pending.to, seconds = 0, samples = 0 }
      f.seconds = (f.seconds * f.samples + secs) / (f.samples + 1)
      f.samples = f.samples + 1
      flights[key] = f
      ns.Print(string.format(L["flight %s took %.0fs"], key, secs))
    end
    pending = nil
    local cdb = Saved()
    if cdb then cdb.flying = nil end
  end
end

---------------------------------------------------------------------------
-- The route's flight on the flight map (a player's request, 2026-11-17: "put a ring round X, so I can click the right
-- one straight away"): with the flight master the route boards at open, a pulsing ring round the flight master it
-- flies to (the game's own TaxiButton, or the flight map's pin), the next flight of the route only. Display only:
-- the ring takes no clicks, and nothing is picked for the player. Option `flightMapRing` (Options > Routing, on).
---------------------------------------------------------------------------
T.RING_PX = 32 -- the ring's size (Media\IconRing32, drawn at its own size): round the game's 16 px button
T.RING_PULSE = 1.2 -- s, one pulse
T.RING_COLOR = { 1, 0.82, 0 } -- gold, as the game's own highlights

-- The route's next flight: the flight master it boards at, the one it lands at (node ids, as Data/Pois.lua's and the
-- game's) and that one's name, else nil. Only the first flight of the route (and none while flying).
function T.RouteFlight()
  local N = ns.Nav
  local r = N and N.route
  if not r then return nil end
  local function first(legs)
    for _, leg in ipairs(legs or {}) do
      local t = leg.ride
      if t and t[8] == "flight" and not t.flying and t.to then return t end
    end
  end
  local t = first(r.legs)
  local stretches = r.stretches
  for i = 2, (not t and stretches and N.PlannedStops) and N.PlannedStops() or 0 do
    t = t or (stretches[i] and first(stretches[i].legs))
  end
  if not t then return nil end
  return t.from, t.to, t[10]
end

-- The flight map's slot of node `to`, when the flight master open is node `from` (the route boards here): else nil.
function T.RingSlot(from, to, toName)
  local mapID = GetTaxiMapID and GetTaxiMapID()
  local nodes = mapID and C_TaxiMap and C_TaxiMap.GetAllTaxiNodes and C_TaxiMap.GetAllTaxiNodes(mapID) or {}
  local here, slot
  for _, n in ipairs(nodes) do
    if n.state == 0 then here = n.nodeID end -- (Enum.FlightPathState.Current)
    if n.nodeID == to then slot = n.slotIndex end
  end
  if here ~= nil and from ~= nil and here ~= from then return nil end -- (another flight master than the route's)
  if not slot and toName and NumTaxiNodes then -- (no ids from the game: by its name)
    for i = 1, NumTaxiNodes() do
      if TaxiNodeName(i) == toName then slot = i end
    end
  end
  if slot and TaxiNodeGetType and TaxiNodeGetType(slot) == "CURRENT" then return nil end
  return slot
end

local ring
local function Ring()
  if ring then return ring end
  ring = CreateFrame("Frame", nil, UIParent)
  ring:SetSize(T.RING_PX, T.RING_PX)
  if ring.EnableMouse then ring:EnableMouse(false) end -- (display only: clicks go to the game's button)
  local tex = ring:CreateTexture(nil, "OVERLAY")
  tex:SetAllPoints()
  tex:SetTexture("Interface\\AddOns\\AzerothGPS\\Media\\IconRing" .. T.RING_PX)
  tex:SetVertexColor(T.RING_COLOR[1], T.RING_COLOR[2], T.RING_COLOR[3])
  ring.tex = tex
  ring:SetScript("OnUpdate", function(self)
    local p = (GetTime() % T.RING_PULSE) / T.RING_PULSE
    self.tex:SetAlpha(0.45 + 0.55 * math.abs(math.cos(p * math.pi)))
  end)
  ring:Hide()
  T.ring = ring
  return ring
end

-- The button (or pin) of slot `slot` on the flight map shown: the classic flight map's TaxiButton<slot>, else the
-- flight map's pin for it.
function T.RingButton(slot, to)
  local tf = rawget(_G, "TaxiFrame")
  if tf and tf.IsShown and tf:IsShown() then
    local b = rawget(_G, "TaxiButton" .. slot)
    if b then return b end
  end
  local fm = rawget(_G, "FlightMapFrame")
  if fm and fm.IsShown and fm:IsShown() and fm.EnumeratePinsByTemplate then
    for pin in fm:EnumeratePinsByTemplate("FlightMap_FlightPointPinTemplate") do
      local d = pin.taxiNodeData
      if d and (d.nodeID == to or d.slotIndex == slot) then return pin end
    end
  end
end

-- The ring put round the route's next flight master on the flight map open (or hidden: none, or the option off).
-- True when shown.
function T.MarkTaxiMap()
  local r = Ring()
  r:Hide()
  if ns.settings and ns.settings.gps and ns.settings.gps.flightMapRing == false then return false end
  local from, to, toName = T.RouteFlight()
  local slot = to and T.RingSlot(from, to, toName)
  local b = slot and T.RingButton(slot, to)
  if not b then return false end
  r:SetParent(b)
  r:ClearAllPoints()
  r:SetPoint("CENTER", b, "CENTER")
  r:SetFrameStrata(b.GetFrameStrata and b:GetFrameStrata() or "HIGH")
  r:SetFrameLevel((b.GetFrameLevel and b:GetFrameLevel() or 1) + 2)
  r:Show()
  r.slot = slot
  return true
end

-- The ring a moment after the flight map opens (the game sets its buttons as it shows, after TAXIMAP_OPENED), and
-- again while it stays open with none yet: a flight master's flights read for the first time put the route aside
-- until it's worked out again (Nav.FlightsChanged), and the ring waits for it.
T.RING_TRIES = { 0, 0.2, 0.5, 1, 2, 3 } -- s after the flight map opens
function T.MarkSoon()
  for _, d in ipairs(T.RING_TRIES) do
    C_Timer.After(d, function()
      if T.taxiOpen and not (ring and ring:IsShown()) then pcall(T.MarkTaxiMap) end
    end)
  end
end

function T.UnmarkTaxiMap()
  if not ring then return end
  ring:Hide()
  ring:SetParent(UIParent)
end

local ev = CreateFrame("Frame")
ev:RegisterEvent("TAXIMAP_OPENED")
pcall(ev.RegisterEvent, ev, "TAXIMAP_CLOSED")
ev:RegisterEvent("PLAYER_CONTROL_LOST")
ev:RegisterEvent("PLAYER_CONTROL_GAINED")
pcall(ev.RegisterEvent, ev, "UI_INFO_MESSAGE") -- ("New flight path discovered!")
ev:SetScript("OnEvent", function(_, event, _, message)
  if event == "TAXIMAP_OPENED" then
    pcall(OnTaxiMapOpened)
    T.taxiOpen = true
    T.MarkSoon()
  elseif event == "TAXIMAP_CLOSED" then
    T.taxiOpen = false
    pcall(T.UnmarkTaxiMap)
  elseif event == "UI_INFO_MESSAGE" then
    if ERR_NEWTAXIPATH and message == ERR_NEWTAXIPATH then
      C_Timer.After(T.DISCOVER_AFTER, function() pcall(T.OnDiscovered) end)
    end
  else
    -- Taxi state flips around control lost/gained; check shortly after.
    C_Timer.After(0.5, function() pcall(OnTaxiChanged) end)
  end
end)
if ns.TimeScript then ns.TimeScript(ev, "OnEvent", "events (flights, boats)") end

---------------------------------------------------------------------------
-- Zeppelins and boats: their timetables (Data/Transports.lua: cycle, ride1 / ride2, wait1 /
-- wait2) and when one was seen leaving a dock (the player aboard it: standing still, carried
-- away from the dock), for the next arrivals and departures at both its docks. The game
-- doesn't tell addons where a transport is; the server keeps its own time, so it's learned
-- per realm, and an old sighting (a server restart since) may be off.
---------------------------------------------------------------------------
T.DOCK_YD = 45 -- this close to a dock: waiting there (or aboard, docked)
T.RIDE_YD = 60 -- carried this far from it without walking: it left
T.CARRY_YD = 1.5 -- moved this far between checks without walking: carried
T.CYCLE_SHARPEN = 0.02 -- a second departure sharpens the cycle only this close to the data's (a server restart
-- between the two shifted the timetable, and up to 10% let it bend the cycle: the timer drifted off, 2026-10-02)
T.RIDE_LOG_MAX = 20
T.ARRIVE_YD = 120 -- a ride's end this close to the dock it was heading for: arrived (it may berth off the dock's spot)
T.RIDE_LEARN = 0.4 -- a ride time seen counts only this close to the data's (a share either way)

-- What the ride detector saw (ns.db.rideLog, the last RIDE_LOG_MAX): each departure learned, and each time the
-- player left a dock's reach without one ("rode it and the timer didn't fix itself", 2026-10-02).
function T.LogRide(text)
  if not ns.db then return end
  ns.db.rideLog = ns.db.rideLog or {}
  local log = ns.db.rideLog
  log[#log + 1] = (date and date("%m-%d %H:%M:%S ") or "") .. text
  while #log > T.RIDE_LOG_MAX do table.remove(log, 1) end
end

local function Realm() return (GetRealmName and GetRealmName()) or "?" end
local function RowKey(t) return (t[9] or "?") .. " | " .. (t[10] or "?") end

-- The sightings: { [realm] = { [row key] = { side, at (server time, seconds), cycle? } } }.
function T.Sightings()
  if not ns.db then return {} end
  ns.db.transports = ns.db.transports or {}
  local r = Realm()
  ns.db.transports[r] = ns.db.transports[r] or {}
  return ns.db.transports[r]
end

-- The dock (transport index, side 1 or 2) within DOCK_YD of (x, y) on `cont`, nearest.
function T.DockAt(cont, x, y)
  local best, bi, bs
  for i, t in ipairs(ns.Transports or {}) do
    for side = 1, 2 do
      local c, dx, dy = t[side == 1 and 1 or 4], t[side == 1 and 2 or 5], t[side == 1 and 3 or 6]
      if c == cont then
        local d = math.sqrt((dx - x) ^ 2 + (dy - y) ^ 2)
        if d <= T.DOCK_YD and (not best or d < best) then best, bi, bs = d, i, side end
      end
    end
  end
  return bi, bs
end

-- A departure seen: transport i left dock `side` at server time `at`. A second one from the
-- same dock sharpens the cycle (the server's may run a little off the data's).
function T.Departed(i, side, at)
  local t = ns.Transports and ns.Transports[i]
  if not t then return end
  local seen = T.Sightings()
  local key = RowKey(t)
  local old = seen[key]
  local cycle = old and old.cycle
  if old and old.side == side and t.cycle then
    local n = math.floor((at - old.at) / t.cycle + 0.5)
    if n >= 1 and n <= 40 then
      local c = (at - old.at) / n
      if math.abs(c - t.cycle) < t.cycle * T.CYCLE_SHARPEN then cycle = c end
    end
  end
  seen[key] = { side = side, at = at, cycle = cycle, ride1 = old and old.ride1, ride2 = old and old.ride2 }
  T.LogRide(string.format("departed %s side %d at %.0f (was %s; cycle %s)", key, side, at,
    old and tostring(old.at) or "unknown", cycle and string.format("%.1f", cycle) or "data's"))
end

-- How long transport i takes from dock `side` to its other: the ride seen (T.Arrived), else the data's.
function T.RideTime(i, side)
  local t = ns.Transports and ns.Transports[i]
  if not t then return nil end
  local s = T.Sightings()[RowKey(t)]
  local key = side == 1 and "ride1" or "ride2"
  return s and s[key] or t[key]
end

-- A ride seen arriving: transport i, left dock `from` at server time `left`, berthed at its other dock at `at`. Its
-- time is learned (averaged with the last seen), when within RIDE_LEARN of the data's; the timetable stays on the
-- departure seen, the arrival there worked out from it with the ride's own time.
function T.Arrived(i, from, left, at)
  local t = ns.Transports and ns.Transports[i]
  local key = from == 1 and "ride1" or "ride2"
  if not (t and t[key]) then return end
  local secs = at - left
  local s = T.Sightings()[RowKey(t)]
  local used = s and math.abs(secs - t[key]) <= t[key] * T.RIDE_LEARN
  if used then s[key] = s[key] and (s[key] + secs) / 2 or secs end
  T.LogRide(string.format("arrived %s side %d after %.0f s (data's %.0f s%s)", RowKey(t), 3 - from, secs, t[key],
    used and string.format(", now %.0f s", s[key]) or ", not used"))
end

-- Called every half second: near a dock, then carried away from it (not walking): it left.
local near -- { i, side, x, y, since }
local last -- { x, y, cont }
local carried -- (server time the carrying began)
local streak, streakAt = 0, nil -- (checks in a row carried: one alone may be the last step walked)
-- Riding a boat, a zeppelin or the tram right now, anywhere on the way (not only by a dock): not
-- walking, and carried CARRY_YD and more between checks, two in a row (T.Riding). The route isn't
-- worked out again meanwhile (Nav.Route), as on a flight: at a ride's speed every check was off it.
local rideStreak = 0
function T.Riding() return rideStreak >= 2 end

-- The zeppelin or boat the player is on, its departure seen (asked 2026-10-02: an "arrives in" as a flight's
-- "lands in"): { i, side (the dock it left), at (server time), carriedAt (the last check it was carrying them) }.
-- Through a loading screen on the way too; done within ARRIVE_YD of its other dock once no longer carried there
-- (ARRIVED_CHECKS in a row: T.Arrived, the ride's time from it), or RIDE_GRACE seconds past its timetable's ride.
-- Meanwhile the dock it's heading for is never taken as one it left: coming in, it passed that dock's spot still
-- moving, and that was logged as its departure there, 80-91 s into the ride (2026-10-02 and 03): every ride moved
-- the timetable on by the wait there.
T.RIDE_GRACE = 90
T.ARRIVED_CHECKS = 2
local ride, stillAtDock = nil, 0

function T.StartRide(i, side, at)
  local t = ns.Transports and ns.Transports[i]
  if not (t and (t[8] == "zeppelin" or t[8] == "boat") and t.ride1 and t.ride2) then return end
  ride, stillAtDock = { i = i, side = side, at = at, carriedAt = at }, 0
end

-- The ride now: { kind, from, to (dock names), dock = { cont, x, y } (where it lands), left (seconds) }, or nil.
function T.CurrentRide(serverNow)
  if not ride then return nil end
  local t = ns.Transports and ns.Transports[ride.i]
  serverNow = serverNow or (GetServerTime and GetServerTime()) or time()
  local secs = t and T.RideTime(ride.i, ride.side)
  if not secs or serverNow - ride.at > secs + T.RIDE_GRACE then
    ride = nil
    return nil
  end
  local to = 3 - ride.side
  return { kind = t[8], from = ride.side == 1 and t[9] or t[10], to = to == 1 and t[9] or t[10],
    dock = to == 1 and { t[1], t[2], t[3] } or { t[4], t[5], t[6] }, left = ride.at + secs - serverNow }
end
function T.TransportTick(now, serverNow, px, py, cont, speed)
  if not px then
    last = nil
    rideStreak = 0
    return
  end
  local walking = speed == nil or speed > 0.1
  local carriedNow = not walking and last and last.cont == cont
    and math.sqrt((px - last.x) ^ 2 + (py - last.y) ^ 2) >= T.CARRY_YD
  rideStreak = carriedNow and rideStreak + 1 or 0
  local i, side = T.DockAt(cont, px, py)
  -- (out of a zeppelin's or boat's reach with no departure seen: what the detector saw, for the log)
  if near and not i and not near.left and not carried and near.cont == cont then -- (carried: it departs below)
    local t = ns.Transports[near.i]
    local d = near.x and math.sqrt((px - near.x) ^ 2 + (py - near.y) ^ 2) or 0
    if d >= T.RIDE_YD and t and (t[8] == "zeppelin" or t[8] == "boat") then
      near.left = true
      T.LogRide(string.format("left %s side %d, no departure seen (speed %s, carried %s, streak %d)", RowKey(t),
        near.side, tostring(speed), tostring(carried), streak))
    end
  end
  -- (the dock the ride is heading for: not one to leave until it has arrived; and a dock is one waited at, not one
  -- carried into: coming in aboard with the departure missed, its spot passed still moving was a "departure" too)
  local heading = ride and i == ride.i and side == 3 - ride.side
  if heading and near and near.i == i and near.side == side then near, carried = nil, nil end
  local sameDock = near and near.i == i and near.side == side
  if i and not heading and (sameDock or not carriedNow) then
    near = { i = i, side = side, since = near and near.i == i and near.side == side and near.since or now, cont = cont }
    local t = ns.Transports[i]
    near.x, near.y = t[side == 1 and 2 or 5], t[side == 1 and 3 or 6]
  end
  local moved = last and last.cont == cont and math.sqrt((px - last.x) ^ 2 + (py - last.y) ^ 2) or 0
  if near and not walking and moved >= T.CARRY_YD then
    streak = streak + 1
    if streak == 1 then streakAt = serverNow end
    if streak >= 2 then carried = carried or streakAt end
  else
    streak = 0
    if walking then carried = nil end
  end
  if near and near.cont == cont and carried then
    local d = math.sqrt((px - near.x) ^ 2 + (py - near.y) ^ 2)
    if d >= T.RIDE_YD then
      T.Departed(near.i, near.side, carried)
      T.StartRide(near.i, near.side, carried)
      near, carried = nil, nil
    end
  end
  if near and not i and now - near.since > 600 then near = nil end
  -- (by the ride's other dock and no longer carried: it arrived when it last carried them)
  if ride and carriedNow then ride.carriedAt = serverNow end
  local t = ride and ns.Transports[ride.i]
  local to = ride and 3 - ride.side
  local dx, dy = t and t[to == 1 and 2 or 5], t and t[to == 1 and 3 or 6]
  local berthed = t and t[to == 1 and 1 or 4] == cont and math.sqrt((px - dx) ^ 2 + (py - dy) ^ 2) <= T.ARRIVE_YD
  if berthed and not carriedNow then
    stillAtDock = stillAtDock + 1
    if stillAtDock >= T.ARRIVED_CHECKS then
      T.Arrived(ride.i, ride.side, ride.at, ride.carriedAt)
      ride = nil
    end
  else
    stillAtDock = 0
  end
  last = { x = px, y = py, cont = cont }
end

-- The next arrival at and departure from dock `side` of transport i: seconds from `serverNow`
-- (arrival, departure), and how long ago it was learned; nil when never seen.
function T.TransportTimes(i, side, serverNow)
  local t = ns.Transports and ns.Transports[i]
  local s = t and T.Sightings()[RowKey(t)]
  if not (s and t.cycle and t.ride1) then return nil end
  local P = s.cycle or t.cycle
  local ride = T.RideTime(i, s.side)
  local waitOther = s.side == 1 and t.wait2 or t.wait1
  local waitHere = side == 1 and t.wait1 or t.wait2
  local dep0 = side == s.side and s.at or s.at + ride + waitOther
  local arr0 = dep0 - waitHere
  local function nextAfter(t0) return t0 + math.ceil((serverNow - t0) / P) * P - serverNow end
  return nextAfter(arr0), nextAfter(dep0), serverNow - s.at
end

---------------------------------------------------------------------------
-- Dungeon and raid entrances, learned: where the player stood (outside) just before the
-- loading screen into one. Kept account-wide (ns.db.entrances[map id] = { { cont, x, y, n } }),
-- shared with "Copy map data" (Feedback.RoadsText) for the data (WoW Forever's own dungeons
-- have none in the client or the server data).
---------------------------------------------------------------------------
T.ENTRANCE_FRESH = 120 -- seconds: the last spot outside this recent counts
T.ENTRANCE_SAME_YD = 40 -- one within this of a known one is the same way in
local outside -- { cont, x, y, at }

function T.NoteOutside(now, px, py, cont)
  if px and cont and not (ns.CityLevels and ns.CityLevels[cont]) and cont < 20000 then
    local inInstance = ns.Nav and ns.Nav.CurrentInstance and ns.Nav.CurrentInstance()
    if not inInstance then outside = { cont, px, py, at = now } end
  end
end

-- Just into a dungeon or raid (its map id): its way in is where the player last stood outside.
function T.NoteEntrance(mapID, now)
  if not (mapID and outside and ns.db) or now - outside.at > T.ENTRANCE_FRESH then return false end
  ns.db.entrances = ns.db.entrances or {}
  local list = ns.db.entrances[mapID] or {}
  ns.db.entrances[mapID] = list
  for _, e in ipairs(list) do
    if e[1] == outside[1] and math.sqrt((e[2] - outside[2]) ^ 2 + (e[3] - outside[3]) ^ 2) <= T.ENTRANCE_SAME_YD then
      e.n = (e.n or 1) + 1
      return true
    end
  end
  list[#list + 1] = { outside[1], outside[2], outside[3], n = 1 }
  if ns.MarkUnsaved then ns.MarkUnsaved("entrance:" .. mapID .. ":" .. #list, "add") end
  return true
end

-- A dungeon with wings (Data/Instances.lua's `wings`: the Scarlet Monastery's, Dire Maul's): the wing the
-- player went in by, the way in nearest where they last stood outside (noted on entering, as T.NoteEntrance;
-- kept per character, over a /reload in there). Its map, boss route and usual way are that wing's.
function T.NoteWing(mapID, now)
  if not (mapID and outside) or now - outside.at > T.ENTRANCE_FRESH then return nil end
  local lvl = ns.Nav and ns.Nav.InstanceLevel and ns.Nav.InstanceLevel(mapID)
  local info = lvl and ns.Instances and ns.Instances[lvl]
  if not (info and info.wings) then return nil end
  local best, bd
  for _, e in ipairs(info.entrances or {}) do
    if e[7] and ns.Geo.Base(e[1]) == ns.Geo.Base(outside[1]) then
      local d = (e[2] - outside[2]) ^ 2 + (e[3] - outside[3]) ^ 2
      if not bd or d < bd then best, bd = e[7], d end
    end
  end
  local cdb = ns.CharDB and ns.CharDB()
  if cdb then cdb.enteredWing = best and { level = lvl, wing = best } or nil end
  return best
end

-- The wing of dungeon level `lvl` the player went in by (T.NoteWing), or nil.
function T.EnteredWing(lvl)
  local cdb = ns.CharDB and ns.CharDB()
  local w = cdb and cdb.enteredWing
  return w and w.level == lvl and w.wing or nil
end

do
  local function tick()
    -- (a flight's take-off and landing looked at here too: only a route's redraw called T.Current, and with no
    -- route set no flight's time was ever recorded, found in QA 2026-11-15)
    pcall(T.Current)
    local ok, px, py, _, cont = pcall(UnitPosition, "player")
    if not ok or (ns.IsSecret and (ns.IsSecret(px) or ns.IsSecret(py))) then return end
    local sok, speed = pcall(GetUnitSpeed, "player")
    if not sok or (ns.IsSecret and ns.IsSecret(speed)) then speed = nil end
    pcall(T.TransportTick, GetTime(), GetServerTime and GetServerTime() or time(), px, py, cont, speed)
    pcall(T.NoteOutside, GetTime(), px, py, cont)
  end
  if C_Timer and C_Timer.NewTicker then C_Timer.NewTicker(0.5, tick) end
end
