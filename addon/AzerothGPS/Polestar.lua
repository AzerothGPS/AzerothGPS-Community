-- Polestar Route (asked 2026-11-13: "add Polestar ... support like RestedXP"): with Polestar installed (WoW Forever's
-- open-source leveling guide), a quick button that routes to each step of its guide in turn, as RestedXP Route
-- (RestedXP.lua) and Zygor Route (Zygor.lua). The place Polestar's own arrow is guiding to is the route's first stop,
-- read through its documented API (its docs/ARCHITECTURE.md, "Nav"): `Polestar.Nav.GetTarget()` (the waypoint: map, x,
-- y in percent, label, stepIndex, goalIndex, kind) and `Polestar.Nav.GetTargetWorld()` (continent, world yards north
-- and west as AzerothGPS's own, and the NPC's or object's height when Polestar has one). Only a guide step's target:
-- never while Polestar's death helper holds its arrow (`IsHeld`) or on a point the player picked by hand there
-- (`IsOverride`). When Polestar moves on (the goal done, the step checked off or skipped), that stop is done and the
-- next place is the stop; getting there doesn't finish it (Polestar says when: N.CheckArrival). Another route picked
-- turns it off, and so do RestedXP Route and Zygor Route (one guide at a time). Read only: nothing in Polestar is
-- changed, and only those four functions are called.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)

local P = {}
ns.Polestar = P

P.TICK = 0.5 -- s between looks at Polestar's arrow
P.lastKey = nil -- the step place the route was last given (nil: none yet since turned on)

local function Nav()
  local p = rawget(_G, "Polestar")
  local n = type(p) == "table" and p.Nav
  if type(n) ~= "table" or type(n.GetTarget) ~= "function" or type(n.GetTargetWorld) ~= "function" then return nil end
  return n
end

-- Polestar is loaded with the navigation API this reads.
function P.Available()
  return Nav() ~= nil
end

local function CDB() return ns.CharDB and ns.db and ns.CharDB() end

-- Following Polestar's steps (per character, kept over a /reload). On by itself where Polestar is loaded, until it's
-- turned off, unless RestedXP Route or Zygor Route is on (one guide at a time: theirs first where several are loaded).
function P.On()
  local cdb = CDB()
  if not cdb then return false end
  if cdb.polestarFollow ~= nil then return cdb.polestarFollow == true end
  local X, Z = ns.RestedXP, ns.Zygor
  return P.Available() and not (X and X.On and X.On()) and not (Z and Z.On and Z.On()) and cdb.questifyFollow ~= true and cdb.aprFollow ~= true
end

local function Call(f, ...)
  local ok, a, b, c, d = pcall(f, ...)
  if ok then return a, b, c, d end
end

-- The waypoint Polestar is guiding to, if it's a guide step's place: the waypoint, else nil (its death helper's, a
-- point picked by hand in Polestar, a done step's none).
function P.Waypoint()
  local n = Nav()
  if not n then return nil end
  if type(n.IsHeld) == "function" and Call(n.IsHeld) then return nil end
  if type(n.IsOverride) == "function" and Call(n.IsOverride) then return nil end
  local w = Call(n.GetTarget)
  if type(w) ~= "table" or not (tonumber(w.map) and tonumber(w.x) and tonumber(w.y)) or not tonumber(w.stepIndex) then
    return nil
  end
  return w
end

-- The waypoint in world yards: x, y, the level it's on (a city's own level where its map is one, Undercity's), its
-- height (or nil), or nil. Polestar's own world point where it has one (its guides' coordinates may be on the older
-- maps' frames, `f`, which it places itself), else by its map and percent as Zygor's.
function P.Place(w)
  local stop = ns.Import and ns.Import.ToStop({ mapID = tonumber(w.map), x = tonumber(w.x), y = tonumber(w.y) })
  local n = Nav()
  local c, wx, wy, wz = Call(n.GetTargetWorld)
  wx, wy = tonumber(wx), tonumber(wy)
  if wx and wy and tonumber(c) then
    local cont = (stop and stop.cont) or tonumber(c)
    return wx, wy, cont, tonumber(wz)
  end
  if not stop then return nil end
  return stop.x, stop.y, stop.cont, tonumber(w.z)
end

-- A step place's key: the step and goal, where.
function P.Key(w)
  return string.format("%s.%s:%s,%.2f,%.2f", tostring(w.stepIndex), tostring(w.goalIndex or "?"), tostring(w.map),
    tonumber(w.x), tonumber(w.y))
end

-- The stop's name: the waypoint's label (its color codes taken out), else "Step n".
function P.Name(w)
  local t = w.label
  if type(t) == "string" then
    t = t:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("\n.*", ""):gsub("%s+", " ")
    t = t:match("^%s*(.-)%s*$")
  end
  if type(t) ~= "string" or t == "" then t = L["Step %s"]:format(tostring(w.stepIndex)) end
  return "Polestar: " .. t
end

-- The route's Polestar stop: index, stop (or nil).
function P.Stop()
  for i, d in ipairs(ns.Nav and ns.Nav.stops or {}) do
    if d.polestar then return i, d end
  end
end

-- One look at Polestar's arrow (every P.TICK while on).
function P.Tick()
  if not P.On() or not ns.Nav then return end
  local N = ns.Nav
  local w = P.Waypoint()
  local x, y, cont, z
  if w then x, y, cont, z = P.Place(w) end
  local key = x and P.Key(w)
  local i, d = P.Stop()
  if d and d.polestar ~= key then
    -- (Polestar moved past it: the goal or step is done, so is the stop)
    N.RemoveStop(i)
    d = nil
  end
  -- (where floors stack: Polestar's own height for the NPC or object, else as RestedXP Route's: the guides' shipped
  -- heights, an NPC's spot's, an NPC talked to there, the followed floor)
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
    if P.lastKey == key then
      -- (Polestar still on the same place and its stop gone: another route was picked, or it was removed by hand)
      P.SetOn(false)
      ns.Print(L["Polestar Route: off (the route was changed). Click Polestar Route to follow the guide again."])
      return
    end
    N.InsertStop({ x = x, y = y, z = z or (H and H(cont, x, y)), cont = cont, name = P.Name(w), polestar = key }, 1, true)
  end
  P.lastKey = key
end

function P.SetOn(on)
  local cdb = CDB()
  if not cdb then return end
  cdb.polestarFollow = on and true or false -- (off is kept too: the default is on)
  P.lastKey = nil
end

-- The button: on replaces the route with Polestar's current step (and each one after it); off leaves the route.
function P.Toggle()
  if not P.Available() then
    ns.Print(L["Polestar Route: Polestar isn't loaded."])
    return
  end
  if P.On() then
    P.SetOn(false)
    local i = P.Stop()
    if i then ns.Nav.RemoveStop(i) end
    ns.Print(L["Polestar Route: off."])
    return
  end
  for _, k in ipairs({ "RestedXP", "Zygor", "Questify", "AzerothPilot" }) do -- (one guide at a time)
    local g = ns[k]
    if g and g.On and g.On() then g.Toggle() end
  end
  if ns.Nav.Clear then ns.Nav.Clear() end
  P.SetOn(true)
  P.Tick()
  ns.Print(P.Stop() and L["Polestar Route: on. Each Polestar step is your next stop; it's done when Polestar checks it off."]
    or L["Polestar Route: on. Polestar's step has no place to go right now; the route starts at the next one that has."])
end

if C_Timer and C_Timer.NewTicker then
  P.ticker = C_Timer.NewTicker(P.TICK, function()
    local ok, err = pcall(P.Tick)
    if not ok and ns.GPS and ns.GPS.LogError then ns.GPS.LogError("Polestar Route", err) end
  end)
end
