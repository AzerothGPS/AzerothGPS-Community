-- OpenXP Route (item 111, Kooki3z 2026-11-26): with OpenXP 2.0 installed (WoW Forever's free leveling guides; 1.x was
-- RestedXP-based and RestedXP Route followed it), a quick button that routes to each step of its guide in turn, as
-- RestedXP, Zygor, Polestar, Questify and Azeroth Pilot Route. OpenXP 2.0 keeps everything in its own namespace and
-- gives other addons no API, so this reads what it hands to the shared map-pin library every addon can see,
-- HereBeDragons-Pins-2.0 (through LibStub): the pin it puts on the step you're on (its "Step pins", Settings > Maps,
-- on by default; the current step's pin is the one that pulses), at world yards x, y (UnitPosition's second and first:
-- the other way round from ours) on its continent. OpenXP's pins are the ones it registered under a table whose icon
-- paths are in OpenXP's own folder. The step's number and guide come from its per-character saved table, OpenXPCharDB
-- (`currentGuide`, `guides[key].step`), read only. When OpenXP moves on (the step checked off or skipped), that stop is
-- done and the next step's place is the stop; getting there doesn't finish it. Another route picked turns it off, and
-- so do the other guide routes (one guide at a time). Read only: no function of OpenXP's or of the library is called,
-- nothing is hooked and nothing is changed. (The step pin is at the step's first place: a step with several places
-- along its way gets the first one; asked of OpenXP as a public hook, docs in the item 111 report.)
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)

local O = {}
ns.OpenXP = O

O.TICK = 0.5 -- s between looks at OpenXP's step pin
O.lastKey = nil -- the step place the route was last given (nil: none yet since turned on)
O.OTHERS = { "RestedXP", "Zygor", "Polestar", "Questify", "AzerothPilot" } -- (the other guide routes: one guide at a time)
O.ICON_PREFIX = "interface\\addons\\openxp\\" -- (OpenXP's own media folder, lower case: how its pins' table is known)

-- OpenXP 2.0 is loaded: its arrow frame (named "OpenXPArrow"; 1.x had none, it made RestedXP's).
function O.Available()
  local f = rawget(_G, "OpenXPArrow")
  return type(f) == "table"
end

local function Pins()
  local ls = rawget(_G, "LibStub")
  local libs = type(ls) == "table" and rawget(ls, "libs")
  local p = type(libs) == "table" and rawget(libs, "HereBeDragons-Pins-2.0")
  if type(p) ~= "table" then return nil end
  return p
end

-- Is `ref` (a table pins were registered under) OpenXP's? Its icon paths are in OpenXP's folder.
local function IsOpenXP(ref)
  if type(ref) ~= "table" then return false end
  local icons = rawget(ref, "ICON")
  local disc = type(icons) == "table" and rawget(icons, "disc")
  return type(disc) == "string" and disc:lower():sub(1, #O.ICON_PREFIX) == O.ICON_PREFIX
end

-- OpenXP's settings and per-character record (its saved variables), read only.
local function Saved(name)
  local t = rawget(_G, name)
  return type(t) == "table" and t or nil
end

-- OpenXP's map pins are off (Settings > Maps > Step pins): nothing to follow.
function O.PinsOff()
  local db = Saved("OpenXPDB")
  local s = db and rawget(db, "settings")
  return type(s) == "table" and rawget(s, "mapPins") == false
end

-- The guide and step OpenXP is on: guide key, step number (or nil).
function O.CurrentStep()
  local c = Saved("OpenXPCharDB")
  local key = c and rawget(c, "currentGuide")
  if type(key) ~= "string" then return nil end
  local gs = rawget(c, "guides")
  local g = type(gs) == "table" and rawget(gs, key)
  local n = type(g) == "table" and tonumber(rawget(g, "step"))
  return key, n
end

-- The current step's pin among those registered under `ref` in `registry` ({ [ref] = { [icon] = true } }), its
-- place from `data` ({ [icon] = { instanceID, x, y } }): best = { pos, x, y, inst, entry }, the lowest step first.
local function Look(registry, data, best)
  if type(registry) ~= "table" or type(data) ~= "table" then return best end
  for ref, icons in pairs(registry) do
    if type(icons) == "table" and IsOpenXP(ref) then
      for icon in pairs(icons) do
        local p = type(icon) == "table" and (rawget(icon, "owner") or icon)
        local t = rawget(data, icon)
        if type(p) == "table" and type(t) == "table" and rawget(p, "kind") == "step" and rawget(p, "glowOn") == true then
          local x, y, inst = tonumber(rawget(t, "x")), tonumber(rawget(t, "y")), tonumber(rawget(t, "instanceID"))
          local entry = rawget(p, "entry")
          local pos = type(entry) == "table" and tonumber(rawget(entry, "pos")) or math.huge
          if x and y and inst and (not best or pos < best.pos) then
            best = { pos = pos, x = x, y = y, inst = inst, entry = type(entry) == "table" and entry or nil }
          end
        end
      end
    end
  end
  return best
end

-- The place of the step OpenXP is on: { x, y (ours: world yards), cont, pos, guide, entry }, else nil (no guide,
-- pins off, a step with no place).
function O.Waypoint()
  if not O.Available() then return nil end
  local lib = Pins()
  if not lib then return nil end
  local best = Look(rawget(lib, "worldmapPinRegistry"), rawget(lib, "worldmapPins"), nil)
  best = Look(rawget(lib, "minimapPinRegistry"), rawget(lib, "minimapPins"), best)
  if not best then return nil end
  local guide, step = O.CurrentStep()
  local pos = best.pos ~= math.huge and best.pos or step
  return { x = best.y, y = best.x, cont = best.inst, pos = pos, guide = guide, entry = best.entry }
end

-- A step place's key: OpenXP's guide and step number, and where.
function O.Key(w)
  return string.format("%s:%s:%.1f,%.1f", tostring(w.guide or ""), tostring(w.pos or ""), w.x, w.y)
end

local function Clean(t)
  if type(t) ~= "string" then return nil end
  t = t:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("|T.-|t", ""):gsub("\n.*", ""):gsub("%s+", " ")
  t = t:match("^%s*(.-)%s*$")
  return t ~= "" and t or nil
end

-- The stop's name: the step's title from its pin (a numbered badge's tooltip's first line, or a quest giver's name),
-- else the text under OpenXP's arrow, else "Step".
function O.Name(w)
  local e, t = w.entry, nil
  if e then
    local lines = rawget(e, "lines")
    t = type(lines) == "table" and Clean(rawget(lines, 1)) or Clean(rawget(e, "giver"))
  end
  if not t then
    local f = rawget(_G, "OpenXPArrow")
    local label = type(f) == "table" and rawget(f, "label")
    if type(label) == "table" and type(label.GetText) == "function" then
      local ok, s = pcall(label.GetText, label)
      if ok then t = Clean(s) end
    end
  end
  return "OpenXP: " .. (t or L["Step"])
end

-- The route's OpenXP stop: index, stop (or nil).
function O.Stop()
  for i, d in ipairs(ns.Nav and ns.Nav.stops or {}) do
    if d.openxp then return i, d end
  end
end

local function CDB() return ns.CharDB and ns.db and ns.CharDB() end

-- Following OpenXP's steps (per character, kept over a /reload). On by itself where OpenXP 2.0 is loaded, until it's
-- turned off, unless another guide route is on (one guide at a time: the others first).
function O.On()
  local cdb = CDB()
  if not cdb then return false end
  if cdb.openxpFollow ~= nil then return cdb.openxpFollow == true end
  for _, k in ipairs(O.OTHERS) do
    local g = ns[k]
    if g and g.On and g.On() then return false end
  end
  return O.Available()
end

-- One look at OpenXP's step pin (every O.TICK while on).
function O.Tick()
  if not O.On() or not ns.Nav then return end
  local N = ns.Nav
  local w = O.Waypoint()
  local key = w and O.Key(w)
  local i, d = O.Stop()
  if d and d.openxp ~= key then
    -- (OpenXP moved past it: the step is done, so is the stop)
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
    if O.lastKey == key then
      -- (OpenXP still on the same place and its stop gone: another route was picked, or it was removed by hand)
      O.SetOn(false)
      ns.Print(L["OpenXP Route: off (the route was changed). Click OpenXP Route to follow the guide again."])
      return
    end
    N.InsertStop({ x = w.x, y = w.y, z = H and H(w.cont, w.x, w.y), cont = w.cont, name = O.Name(w), openxp = key }, 1, true)
  end
  O.lastKey = key
end

function O.SetOn(on)
  local cdb = CDB()
  if not cdb then return end
  cdb.openxpFollow = on and true or false -- (off is kept too: the default is on)
  O.lastKey = nil
end

-- The button: on replaces the route with OpenXP's current step (and each one after it); off leaves the route.
function O.Toggle()
  if not O.Available() then
    ns.Print(L["OpenXP Route: OpenXP 2.0 isn't loaded."])
    return
  end
  if O.On() then
    O.SetOn(false)
    local i = O.Stop()
    if i then ns.Nav.RemoveStop(i) end
    ns.Print(L["OpenXP Route: off."])
    return
  end
  for _, k in ipairs(O.OTHERS) do -- (one guide at a time)
    local g = ns[k]
    if g and g.On and g.On() then g.Toggle() end
  end
  if ns.Nav.Clear then ns.Nav.Clear() end
  O.SetOn(true)
  O.Tick()
  if O.Stop() then
    ns.Print(L["OpenXP Route: on. Each OpenXP step is your next stop; it's done when OpenXP checks it off."])
  elseif O.PinsOff() then
    ns.Print(L["OpenXP Route: on, but OpenXP's step pins are off. Turn on Step pins in OpenXP's settings (Maps) to follow its steps."])
  else
    ns.Print(L["OpenXP Route: on. OpenXP's step has no place to go right now; the route starts at the next one that has."])
  end
end

if C_Timer and C_Timer.NewTicker then
  O.ticker = C_Timer.NewTicker(O.TICK, function()
    local ok, err = pcall(O.Tick)
    if not ok and ns.GPS and ns.GPS.LogError then ns.GPS.LogError("OpenXP Route", err) end
  end)
end
