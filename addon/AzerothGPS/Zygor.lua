-- Zygor Route (asked 2026-11-09: "support zygor in the same way we support restedxp"): with Zygor Guides Viewer
-- installed (ZygorGuidesViewerForever), a quick button that routes to each step of its guide in turn, as RestedXP Route
-- (RestedXP.lua). The place Zygor's own arrow is taking the player to (ZygorGuidesViewer.Pointer.DestinationWaypoint:
-- the guide goal's waypoint, its uiMap `m` and x, y from 0 to 1; with Zygor's travel on, its arrow points at the hops
-- on the way, the destination stays this one) is the route's first stop; when Zygor moves on (the goal done, the step
-- checked off or skipped), that stop is done and the next place is the stop. Getting there doesn't finish it (Zygor says
-- when: N.CheckArrival). A step with no place to go leaves no stop until one that has. Another route picked turns it
-- off, and so does RestedXP Route (one guide at a time). Read only: nothing in Zygor is changed or called.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)

local Z = {}
ns.Zygor = Z

Z.TICK = 0.5 -- s between looks at Zygor's arrow
Z.lastKey = nil -- the step place the route was last given (nil: none yet since turned on)

local function ZGV() return type(_G.ZygorGuidesViewer) == "table" and _G.ZygorGuidesViewer or nil end

-- Zygor's guide viewer is loaded (its arrow's pointer is there).
function Z.Available()
  local z = ZGV()
  return (z and type(z.Pointer) == "table") and true or false
end

local function CDB() return ns.CharDB and ns.db and ns.CharDB() end

-- Following Zygor's steps (per character, kept over a /reload).
-- On by itself where Zygor Guides is loaded, until it's turned off (asked 2026-11-10, as RestedXP Route: its
-- X.On), unless RestedXP Route is on (one guide at a time: RestedXP's first where both are loaded).
function Z.On()
  local cdb = CDB()
  if not cdb then return false end
  if cdb.zygorFollow ~= nil then return cdb.zygorFollow == true end
  local X = ns.RestedXP
  return Z.Available() and not (X and X.On and X.On()) and cdb.polestarFollow ~= true and cdb.questifyFollow ~= true and cdb.aprFollow ~= true and cdb.openxpFollow ~= true and cdb.flowupFollow ~= true
end

-- The waypoint Zygor is taking the player to, if it's a guide step's place: the waypoint, else nil (a corpse's, a
-- waypoint the player set by hand in Zygor, a goal done).
function Z.Waypoint()
  local z = ZGV()
  local w = z and type(z.Pointer) == "table" and z.Pointer.DestinationWaypoint
  if type(w) ~= "table" or not (tonumber(w.m) and tonumber(w.x) and tonumber(w.y)) then return nil end
  local g = w.goal
  if type(g) ~= "table" or type(g.parentStep) ~= "table" then return nil end
  if w.type == "corpse" or g.status == "complete" then return nil end
  return w
end

-- The waypoint in world yards: x, y, the level it's on (a city's own level where its map is one, Undercity's), or nil.
function Z.Place(w)
  local stop = ns.Import and ns.Import.ToStop({ mapID = tonumber(w.m), x = w.x * 100, y = w.y * 100 })
  if not stop then return nil end
  return stop.x, stop.y, stop.cont
end

-- A step place's key: the guide, step and goal, where.
function Z.Key(w)
  local g = w.goal
  local s = g.parentStep
  local guide = type(s.parentGuide) == "table" and s.parentGuide.title or "?"
  return string.format("%s#%s.%s:%s,%.4f,%.4f", tostring(guide), tostring(s.num or "?"), tostring(g.num or "?"),
    tostring(w.m), w.x, w.y)
end

-- The stop's name: the waypoint's title (its color codes and "(in zone)" line taken out), else "Step n".
function Z.Name(w)
  local t = w.title
  if type(t) == "string" then
    t = t:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("\n.*", ""):gsub("%s+", " ")
    t = t:match("^%s*(.-)%s*$")
  end
  local s = w.goal.parentStep
  if type(t) ~= "string" or t == "" then t = s.num and L["Step %s"]:format(tostring(s.num)) or L["Step"] end
  return "Zygor: " .. t
end

-- The route's Zygor stop: index, stop (or nil).
function Z.Stop()
  for i, d in ipairs(ns.Nav and ns.Nav.stops or {}) do
    if d.zygor then return i, d end
  end
end

-- One look at Zygor's arrow (every Z.TICK while on).
function Z.Tick()
  if not Z.On() or not ns.Nav then return end
  local N = ns.Nav
  local w = Z.Waypoint()
  local x, y, cont
  if w then x, y, cont = Z.Place(w) end
  local key = x and Z.Key(w)
  local i, d = Z.Stop()
  if d and d.zygor ~= key then
    -- (Zygor moved past it: the goal or step is done, so is the stop)
    N.RemoveStop(i)
    d = nil
  end
  local X = ns.RestedXP
  -- (where floors stack: the guides' shipped heights, Data/GuideFloors.lua, Zygor's waypoints in it too (the user,
  -- 2026-11-09: "use it for both"), else an NPC's spot's (Nav's N.SpawnZ), else an NPC talked to there, else the
  -- followed floor: as RestedXP Route's)
  local H = X and X.HeightXY
  if d and d.z == nil and H then
    local z = H(d.cont, d.x, d.y)
    if z then
      d.z = z
      if N.Invalidate then N.Invalidate() end
    end
  end
  if key and not d then
    if Z.lastKey == key then
      -- (Zygor still on the same place and its stop gone: another route was picked, or it was removed by hand)
      Z.SetOn(false)
      ns.Print(L["Zygor Route: off (the route was changed). Click Zygor Route to follow the guide again."])
      return
    end
    N.InsertStop({ x = x, y = y, z = H and H(cont, x, y), cont = cont, name = Z.Name(w), zygor = key }, 1, true)
  end
  Z.lastKey = key
end

function Z.SetOn(on)
  local cdb = CDB()
  if not cdb then return end
  cdb.zygorFollow = on and true or false -- (off is kept too: the default is on)
  Z.lastKey = nil
end

-- The button: on replaces the route with Zygor's current step (and each one after it); off leaves the route.
function Z.Toggle()
  if not Z.Available() then
    ns.Print(L["Zygor Route: Zygor Guides isn't loaded."])
    return
  end
  if Z.On() then
    Z.SetOn(false)
    local i = Z.Stop()
    if i then ns.Nav.RemoveStop(i) end
    ns.Print(L["Zygor Route: off."])
    return
  end
  for _, k in ipairs({ "RestedXP", "Polestar", "Questify", "AzerothPilot", "OpenXP", "FlowUp" }) do -- (one guide at a time)
    local g = ns[k]
    if g and g.On and g.On() then g.Toggle() end
  end
  if ns.Nav.Clear then ns.Nav.Clear() end
  Z.SetOn(true)
  Z.Tick()
  ns.Print(Z.Stop() and L["Zygor Route: on. Each Zygor step is your next stop; it's done when Zygor checks it off."]
    or L["Zygor Route: on. Zygor's step has no place to go right now; the route starts at the next one that has."])
end

if C_Timer and C_Timer.NewTicker then
  Z.ticker = C_Timer.NewTicker(Z.TICK, function()
    local ok, err = pcall(Z.Tick)
    if not ok and ns.GPS and ns.GPS.LogError then ns.GPS.LogError("Zygor Route", err) end
  end)
end
