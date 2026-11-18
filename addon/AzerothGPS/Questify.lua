-- Questify Route (asked 2026-11-13: "add Polestar and Questify support like RestedXP"): with Questify installed (WoW
-- Forever's open-source leveling guide), a quick button that routes to each step of its guide in turn, as RestedXP,
-- Zygor and Polestar Route. The place Questify guides to is the route's first stop, read from its own state
-- (`Questify.Nav:Status()`: { target = { mapId, x, y (0-100), title }, manual }; Questify's global is its addon table):
-- never a point the player picked by hand on its map (`manual`). For a kill step Questify's target follows the nearest
-- spawn point, so the stop moves with it, as its arrow does. When Questify moves on, that stop is done and the next
-- place is the stop; getting there doesn't finish it. Another route picked turns it off, and so do the other guide
-- routes (one guide at a time). Read only: nothing in Questify is changed, only Status is called.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)

local Q = {}
ns.Questify = Q

Q.TICK = 0.5 -- s between looks at Questify's target
Q.lastKey = nil -- the step place the route was last given (nil: none yet since turned on)

local function QNav()
  local q = rawget(_G, "Questify")
  local n = type(q) == "table" and q.Nav
  if type(n) ~= "table" or type(n.Status) ~= "function" then return nil end
  return n
end

-- Questify is loaded with the navigation state this reads.
function Q.Available()
  return QNav() ~= nil
end

local function CDB() return ns.CharDB and ns.db and ns.CharDB() end

-- Following Questify's steps (per character, kept over a /reload). On by itself where Questify is loaded, until it's
-- turned off, unless another guide route is on (one guide at a time: RestedXP's, Zygor's, Polestar's first).
function Q.On()
  local cdb = CDB()
  if not cdb then return false end
  if cdb.questifyFollow ~= nil then return cdb.questifyFollow == true end
  for _, k in ipairs({ "RestedXP", "Zygor", "Polestar" }) do
    local g = ns[k]
    if g and g.On and g.On() then return false end
  end
  return Q.Available() and cdb.aprFollow ~= true
end

-- The place Questify is guiding to, if it's its guide's: { mapId, x, y, title }, else nil (none, or picked by hand).
function Q.Waypoint()
  local n = QNav()
  if not n then return nil end
  local ok, st = pcall(n.Status, n)
  if not ok or type(st) ~= "table" or st.manual then return nil end
  local t = st.target
  if type(t) ~= "table" or not (tonumber(t.mapId) and tonumber(t.x) and tonumber(t.y)) then return nil end
  return t
end

-- The place in world yards: x, y, the level it's on (a city's own level where its map is one, Undercity's), or nil.
function Q.Place(w)
  local stop = ns.Import and ns.Import.ToStop({ mapID = tonumber(w.mapId), x = tonumber(w.x), y = tonumber(w.y) })
  if not stop then return nil end
  return stop.x, stop.y, stop.cont
end

-- A step place's key: its title and where (Questify gives no step number).
function Q.Key(w)
  return string.format("%s:%s,%.1f,%.1f", tostring(w.title or ""), tostring(w.mapId), tonumber(w.x), tonumber(w.y))
end

-- The stop's name: the title (its color codes taken out), else "Step".
function Q.Name(w)
  local t = w.title
  if type(t) == "string" then
    t = t:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("\n.*", ""):gsub("%s+", " ")
    t = t:match("^%s*(.-)%s*$")
  end
  if type(t) ~= "string" or t == "" then t = L["Step"] end
  return "Questify: " .. t
end

-- The route's Questify stop: index, stop (or nil).
function Q.Stop()
  for i, d in ipairs(ns.Nav and ns.Nav.stops or {}) do
    if d.questify then return i, d end
  end
end

-- One look at Questify's target (every Q.TICK while on).
function Q.Tick()
  if not Q.On() or not ns.Nav then return end
  local N = ns.Nav
  local w = Q.Waypoint()
  local x, y, cont
  if w then x, y, cont = Q.Place(w) end
  local key = x and Q.Key(w)
  local i, d = Q.Stop()
  if d and d.questify ~= key then
    -- (Questify moved past it: the goal or step is done, so is the stop)
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
    if Q.lastKey == key then
      -- (Questify still on the same place and its stop gone: another route was picked, or it was removed by hand)
      Q.SetOn(false)
      ns.Print(L["Questify Route: off (the route was changed). Click Questify Route to follow the guide again."])
      return
    end
    N.InsertStop({ x = x, y = y, z = H and H(cont, x, y), cont = cont, name = Q.Name(w), questify = key }, 1, true)
  end
  Q.lastKey = key
end

function Q.SetOn(on)
  local cdb = CDB()
  if not cdb then return end
  cdb.questifyFollow = on and true or false -- (off is kept too: the default is on)
  Q.lastKey = nil
end

-- The button: on replaces the route with Questify's current step (and each one after it); off leaves the route.
function Q.Toggle()
  if not Q.Available() then
    ns.Print(L["Questify Route: Questify isn't loaded."])
    return
  end
  if Q.On() then
    Q.SetOn(false)
    local i = Q.Stop()
    if i then ns.Nav.RemoveStop(i) end
    ns.Print(L["Questify Route: off."])
    return
  end
  for _, k in ipairs({ "RestedXP", "Zygor", "Polestar", "AzerothPilot" }) do -- (one guide at a time)
    local g = ns[k]
    if g and g.On and g.On() then g.Toggle() end
  end
  if ns.Nav.Clear then ns.Nav.Clear() end
  Q.SetOn(true)
  Q.Tick()
  ns.Print(Q.Stop() and L["Questify Route: on. Each Questify step is your next stop; it's done when Questify checks it off."]
    or L["Questify Route: on. Questify's step has no place to go right now; the route starts at the next one that has."])
end

if C_Timer and C_Timer.NewTicker then
  Q.ticker = C_Timer.NewTicker(Q.TICK, function()
    local ok, err = pcall(Q.Tick)
    if not ok and ns.GPS and ns.GPS.LogError then ns.GPS.LogError("Questify Route", err) end
  end)
end
