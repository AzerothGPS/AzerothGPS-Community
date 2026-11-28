-- Azeroth Pilot Route (asked 2026-11-17: "can we add another leveling guide support like restedXP called Azeroth Pilot
-- Reloaded?"): with Azeroth Pilot Reloaded installed (APR, which has WoW Forever routes), a quick button that routes to
-- each step of its guide in turn, as RestedXP, Zygor, Polestar and Questify Route. The place APR's arrow points at is
-- the route's first stop, read from its own state (`APR.Arrow`: `Active`, and `x`, `y` in world yards the other way
-- round from ours, as UnitPosition's second and first: APR's Arrow.lua compares them with UnitPosition's swapped; on
-- the player's own continent, as APR shows its arrow only there). Its `x` set to 0 is a step reached (in its range),
-- and 0, 0 a step with no place (an action only). When APR's arrow moves on, that stop is done and the next place is
-- the stop; getting there doesn't finish it. Another route picked turns it off, and so do the other guide routes (one
-- guide at a time). Read only: nothing in APR is changed, only GetCurrentStep and GetStepString are called.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)

local A = {}
ns.AzerothPilot = A

A.TICK = 0.5 -- s between looks at APR's arrow
A.lastKey = nil -- the step place the route was last given (nil: none yet since turned on)
A.OTHERS = { "RestedXP", "Zygor", "Polestar", "Questify", "OpenXP", "FlowUp" } -- (the other guide routes: one guide at a time)

local function APR()
  local a = rawget(_G, "APR")
  if type(a) ~= "table" or type(a.Arrow) ~= "table" then return nil end
  return a
end

-- APR is loaded with the arrow this reads.
function A.Available()
  return APR() ~= nil
end

local function CDB() return ns.CharDB and ns.db and ns.CharDB() end

-- Following APR's steps (per character, kept over a /reload). On by itself where APR is loaded, until it's turned
-- off, unless another guide route is on (one guide at a time: RestedXP's, Zygor's, Polestar's, Questify's first).
function A.On()
  local cdb = CDB()
  if not cdb then return false end
  if cdb.aprFollow ~= nil then return cdb.aprFollow == true end
  for _, k in ipairs(A.OTHERS) do
    local g = ns[k]
    -- (OpenXP Route and FlowUp Route, added after, ask this one first: only their saved choices here, or each would ask the other)
    if k ~= "OpenXP" and k ~= "FlowUp" and g and g.On and g.On() then return false end
  end
  return A.Available() and cdb.openxpFollow ~= true and cdb.flowupFollow ~= true
end

-- The current step: the step table and its index (APR:GetCurrentStep()), or nil.
local function CurrentStep(a)
  if type(a.GetCurrentStep) ~= "function" then return nil end
  local ok, step, index = pcall(a.GetCurrentStep, a)
  if not ok or type(step) ~= "table" then return nil end
  return step, index
end

-- The place APR's arrow points at: { x, y (ours: world yards), cont, step, index }, else nil (no arrow, a step
-- reached, or one with no place).
function A.Waypoint()
  local a = APR()
  if not a then return nil end
  local ar = a.Arrow
  if not ar.Active then return nil end
  local ax, ay = tonumber(ar.x), tonumber(ar.y)
  if not ax or not ay or ax == 0 or ay == 0 then return nil end
  local G = ns.Geo
  if not (G and G.PlayerWorld) then return nil end
  local _, _, cont = G.PlayerWorld()
  if cont == nil then return nil end
  local step, index = CurrentStep(a)
  return { x = ay, y = ax, cont = cont, step = step, index = index }
end

-- A step place's key: APR's route and step number, and where (a step's arrow can move to the next spot).
function A.Key(w)
  local a = APR()
  return string.format("%s:%s:%.1f,%.1f", tostring(a and a.ActiveRoute or ""), tostring(w.index or ""), w.x, w.y)
end

-- The stop's name: the step's text (its color codes taken out), else "Step".
function A.Name(w)
  local step, t = w.step, nil
  local a = APR()
  if type(step) == "table" then
    if a and type(a.GetStepString) == "function" then
      local ok, s = pcall(a.GetStepString, a, step)
      if ok and type(s) == "string" and s ~= "" then t = s end
    end
    for _, k in ipairs({ "label", "instruction", "title" }) do
      if not t and type(step[k]) == "string" and step[k] ~= "" then t = step[k] end
    end
  end
  if type(t) == "string" then
    t = t:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("|T.-|t", ""):gsub("\n.*", ""):gsub("%s+", " ")
    t = t:match("^%s*(.-)%s*$")
  end
  if type(t) ~= "string" or t == "" then t = L["Step"] end
  return "Azeroth Pilot: " .. t
end

-- The route's APR stop: index, stop (or nil).
function A.Stop()
  for i, d in ipairs(ns.Nav and ns.Nav.stops or {}) do
    if d.apr then return i, d end
  end
end

-- One look at APR's arrow (every A.TICK while on).
function A.Tick()
  if not A.On() or not ns.Nav then return end
  local N = ns.Nav
  local w = A.Waypoint()
  local key = w and A.Key(w)
  local i, d = A.Stop()
  if d and d.apr ~= key then
    -- (APR moved past it: the step is done, so is the stop)
    N.RemoveStop(i)
    d = nil
  end
  -- (where floors stack: as RestedXP Route's: the guides' shipped heights, an NPC's spot's, an NPC talked to
  -- there, the followed floor)
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
    if A.lastKey == key then
      -- (APR still on the same place and its stop gone: another route was picked, or it was removed by hand)
      A.SetOn(false)
      ns.Print(L["Azeroth Pilot Route: off (the route was changed). Click Azeroth Pilot Route to follow the guide again."])
      return
    end
    N.InsertStop({ x = w.x, y = w.y, z = H and H(w.cont, w.x, w.y), cont = w.cont, name = A.Name(w), apr = key }, 1, true)
  end
  A.lastKey = key
end

function A.SetOn(on)
  local cdb = CDB()
  if not cdb then return end
  cdb.aprFollow = on and true or false -- (off is kept too: the default is on)
  A.lastKey = nil
end

-- The button: on replaces the route with APR's current step (and each one after it); off leaves the route.
function A.Toggle()
  if not A.Available() then
    ns.Print(L["Azeroth Pilot Route: Azeroth Pilot Reloaded isn't loaded."])
    return
  end
  if A.On() then
    A.SetOn(false)
    local i = A.Stop()
    if i then ns.Nav.RemoveStop(i) end
    ns.Print(L["Azeroth Pilot Route: off."])
    return
  end
  for _, k in ipairs(A.OTHERS) do -- (one guide at a time)
    local g = ns[k]
    if g and g.On and g.On() then g.Toggle() end
  end
  if ns.Nav.Clear then ns.Nav.Clear() end
  A.SetOn(true)
  A.Tick()
  ns.Print(A.Stop() and L["Azeroth Pilot Route: on. Each Azeroth Pilot step is your next stop; it's done when Azeroth Pilot checks it off."]
    or L["Azeroth Pilot Route: on. Azeroth Pilot's step has no place to go right now; the route starts at the next one that has."])
end

if C_Timer and C_Timer.NewTicker then
  A.ticker = C_Timer.NewTicker(A.TICK, function()
    local ok, err = pcall(A.Tick)
    if not ok and ns.GPS and ns.GPS.LogError then ns.GPS.LogError("Azeroth Pilot Route", err) end
  end)
end
