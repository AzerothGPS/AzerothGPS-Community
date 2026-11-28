-- FlowUp Route (item 145, Kooki3z 2026-11-27: "add Flowup leveling addon support", then "We just need to support its
-- waypoints like RestedXP"): with FlowUp Forever installed, a quick button that routes to each step of its guide in
-- turn, as RestedXP Route. FlowUp keeps its guide in its own namespace and gives other addons no API (no TomTom of
-- ours, no HereBeDragons): its step's place is the pin it draws on the minimap, a frame of its own under Minimap whose
-- `sp` is the spot it shows ({ s = the step, m = uiMap, x, y in percent, wx, wy in world yards when it has them }).
-- FlowUp keeps that pin on the minimap (at its edge when far off) for the step it points at, on the player's
-- continent outside instances. With FlowUp's own map pin off (its Options), it sets the game's map pin instead and
-- keeps where in its saved FlowUpDB.gamePin: that's read then. When FlowUp moves on (the step checked off), that stop
-- is done and the next step's place is the stop; getting there doesn't finish it. Another route picked turns it off,
-- and so do the other guide routes (one guide at a time). Read only: no function of FlowUp's is called, nothing is
-- hooked or changed, and none of its route data is kept beyond the stop's place.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)

local F = {}
ns.FlowUp = F

F.TICK = 0.5 -- s between looks at FlowUp's pin
F.lastKey = nil -- the step place the route was last given (nil: none yet since turned on)
F.OTHERS = { "RestedXP", "Zygor", "Polestar", "Questify", "AzerothPilot", "OpenXP" } -- (one guide at a time)

-- FlowUp is loaded: its saved table or its guide window.
function F.Available()
  return type(rawget(_G, "FlowUpDB")) == "table" or type(rawget(_G, "FlowUpFrame")) == "table"
end

local function Num(v) return type(v) == "number" and v or nil end

-- Is `f` one of FlowUp's map pins (its frames have the spot shown, `sp`, a ring and a glyph), and shown?
local function Pin(f)
  if type(f) ~= "table" then return nil end
  local sp = rawget(f, "sp")
  if type(sp) ~= "table" or type(rawget(sp, "s")) ~= "table" then return nil end
  if rawget(f, "ring") == nil or rawget(f, "glyph") == nil then return nil end
  if type(f.IsShown) ~= "function" or not f:IsShown() then return nil end
  return sp
end

-- The spot FlowUp's minimap pins show: the step's own place first, else its first target's.
local function MinimapSpot()
  local mm = rawget(_G, "Minimap")
  if type(mm) ~= "table" or type(mm.GetChildren) ~= "function" then return nil end
  local first
  for _, f in ipairs({ mm:GetChildren() }) do
    local sp = Pin(f)
    if sp then
      if rawget(sp, "tg") == nil then return sp end
      first = first or sp
    end
  end
  return first
end

-- With FlowUp's map pin off: the game's map pin it set (FlowUpDB.gamePin), while the game's pin is still there.
local function GamePinSpot()
  local db = rawget(_G, "FlowUpDB")
  local o = type(db) == "table" and rawget(db, "opts")
  if type(o) ~= "table" or rawget(o, "mapPin") ~= false then return nil end
  local p = rawget(db, "gamePin")
  if type(p) ~= "table" or not (Num(p.m) and Num(p.x) and Num(p.y)) then return nil end
  if C_Map and C_Map.GetUserWaypoint then
    local ok, w = pcall(C_Map.GetUserWaypoint)
    local pos = ok and type(w) == "table" and w.position
    if type(pos) ~= "table" or w.uiMapID ~= p.m or math.abs(pos.x * 100 - p.x) > 0.05 or math.abs(pos.y * 100 - p.y) > 0.05 then
      return nil -- (the game's pin gone or moved: not FlowUp's any more)
    end
  end
  return { m = p.m, x = p.x, y = p.y }
end

-- The place FlowUp points at: { x, y (ours: world yards), cont, id, name }, else nil.
function F.Waypoint()
  if not F.Available() then return nil end
  local sp = MinimapSpot() or GamePinSpot()
  if not sp then return nil end
  local m, cont, x, y = Num(sp.m), nil, nil, nil
  local G = ns.Geo
  cont = m and G and G.MapCont and G.MapCont(m)
  if Num(sp.wx) and Num(sp.wy) then
    x, y = sp.wx, sp.wy -- (FlowUp's world yards: UnitPosition's first and second, as ours)
  elseif m and Num(sp.x) and Num(sp.y) and ns.Layers and ns.Layers.MapToWorld then
    local c
    x, y, c = ns.Layers.MapToWorld(m, sp.x / 100, sp.y / 100)
    cont = cont or c
  end
  if not (x and y and cont) then return nil end
  local s = rawget(sp, "s")
  local id = type(s) == "table" and rawget(s, "id")
  local name = type(s) == "table" and rawget(s, "plain")
  return { x = x, y = y, cont = cont, id = id, name = type(name) == "string" and name or nil }
end

-- A step place's key: FlowUp's step id and where.
function F.Key(w)
  return string.format("%s:%.1f,%.1f@%s", tostring(w.id or ""), w.x, w.y, tostring(w.cont))
end

-- The stop's name: the step's plain text (its color tags taken out), else "Step".
function F.Name(w)
  local t = w.name
  if t then
    t = t:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("|T.-|t", ""):gsub("%s+", " "):match("^%s*(.-)%s*$")
  end
  return "FlowUp: " .. ((t and t ~= "") and t or L["Step"])
end

-- The route's FlowUp stop: index, stop (or nil).
function F.Stop()
  for i, d in ipairs(ns.Nav and ns.Nav.stops or {}) do
    if d.flowup then return i, d end
  end
end

local function CDB() return ns.CharDB and ns.db and ns.CharDB() end

-- Following FlowUp's steps (per character, kept over a /reload). On by itself where FlowUp is loaded, until it's
-- turned off, unless another guide route is on (one guide at a time: the others first).
function F.On()
  local cdb = CDB()
  if not cdb then return false end
  if cdb.flowupFollow ~= nil then return cdb.flowupFollow == true end
  for _, k in ipairs(F.OTHERS) do
    local g = ns[k]
    if g and g.On and g.On() then return false end
  end
  return F.Available()
end

-- One look at FlowUp's pin (every F.TICK while on).
function F.Tick()
  if not F.On() or not ns.Nav then return end
  local N = ns.Nav
  local w = F.Waypoint()
  local key = w and F.Key(w)
  local i, d = F.Stop()
  if d and d.flowup ~= key then
    -- (FlowUp moved past it: the step is done, so is the stop)
    N.RemoveStop(i)
    d = nil
  end
  -- (where floors stack: as RestedXP Route's, X.HeightXY)
  local X = ns.RestedXP
  local H = X and X.HeightXY
  if d and d.z == nil and H then
    local hz = H(d.cont, d.x, d.y)
    if hz then
      d.z = hz
      if N.Invalidate then N.Invalidate() end
    end
  end
  if key and not d then
    if F.lastKey == key then
      -- (FlowUp still on the same place and its stop gone: another route was picked, or it was removed by hand)
      F.SetOn(false)
      ns.Print(L["FlowUp Route: off (the route was changed). Click FlowUp Route to follow the guide again."])
      return
    end
    N.InsertStop({ x = w.x, y = w.y, z = H and H(w.cont, w.x, w.y), cont = w.cont, name = F.Name(w), flowup = key }, 1, true)
  end
  F.lastKey = key
end

function F.SetOn(on)
  local cdb = CDB()
  if not cdb then return end
  cdb.flowupFollow = on and true or false -- (off is kept too: the default is on)
  F.lastKey = nil
end

-- The button: on replaces the route with FlowUp's current step (and each one after it); off leaves the route.
function F.Toggle()
  if not F.Available() then
    ns.Print(L["FlowUp Route: FlowUp isn't loaded."])
    return
  end
  if F.On() then
    F.SetOn(false)
    local i = F.Stop()
    if i then ns.Nav.RemoveStop(i) end
    ns.Print(L["FlowUp Route: off."])
    return
  end
  for _, k in ipairs(F.OTHERS) do -- (one guide at a time)
    local g = ns[k]
    if g and g.On and g.On() then g.Toggle() end
  end
  if ns.Nav.Clear then ns.Nav.Clear() end
  F.SetOn(true)
  F.Tick()
  ns.Print(F.Stop() and L["FlowUp Route: on. Each FlowUp step is your next stop; it's done when FlowUp checks it off."]
    or L["FlowUp Route: on. FlowUp's step has no place to go right now; the route starts at the next one that has."])
end

if C_Timer and C_Timer.NewTicker then
  F.ticker = C_Timer.NewTicker(F.TICK, function()
    local ok, err = pcall(F.Tick)
    if not ok and ns.GPS and ns.GPS.LogError then ns.GPS.LogError("FlowUp Route", err) end
  end)
end
