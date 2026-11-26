-- RestedXP Route (asked 2026-11-08): with the RestedXP Guides addon (RXPGuides) installed, a quick button that routes
-- to each step of its guide in turn. The step RestedXP's own arrow points at (its global frame RXPG_ARROW, `.element`:
-- the step's waypoint in world yards, HereBeDragons' wx, wy, instance) is the route's first stop; when RestedXP moves on
-- (the step checked off there, its waypoint reached or skipped), that stop is done and the next step's place is the stop.
-- Getting to a RestedXP stop doesn't finish it (RestedXP says when its step is done: N.CheckArrival). A step with no
-- place to go (talk to someone right here) leaves no stop until one that has. Another route picked (Quest Route, a
-- search, a stop removed by hand) turns it off. Read only: nothing in RestedXP is changed or called.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)

local X = {}
ns.RestedXP = X

X.TICK = 0.5 -- s between looks at RestedXP's arrow
X.lastKey = nil -- the step place the route was last given (nil: none yet since turned on)

-- RestedXP is loaded (its arrow frame is there).
function X.Available()
  return type(_G.RXPG_ARROW) == "table" and true or false
end

local function CDB() return ns.CharDB and ns.db and ns.CharDB() end

-- Following RestedXP's steps (per character, kept over a /reload).
-- On by itself where RestedXP Guides is loaded, until it's turned off (asked 2026-11-10: "RestedXP and Zygor routing,
-- have these on by default"): nothing saved is the default, on with the guide addon there, unless Zygor Route was
-- turned on by hand (one guide at a time).
function X.On()
  local cdb = CDB()
  if not cdb then return false end
  if cdb.rxpFollow ~= nil then return cdb.rxpFollow == true end
  return X.Available() and cdb.zygorFollow ~= true and cdb.polestarFollow ~= true and cdb.questifyFollow ~= true and cdb.aprFollow ~= true and cdb.openxpFollow ~= true
end

-- The waypoint RestedXP's arrow points at, if it's a step's place to go: the element, else nil.
function X.Element()
  local af = _G.RXPG_ARROW
  local e = type(af) == "table" and af.element
  if type(e) ~= "table" or not (tonumber(e.wx) and tonumber(e.wy) and tonumber(e.instance)) then return nil end
  local s = e.step
  if type(s) ~= "table" then return nil end -- (its corpse or spirit healer arrow: no step)
  if s.completed or s.active == false or e.skip then return nil end
  return X.Lead(e)
end

-- A travel step's waypoint (`#completewith next`, "Travel to the Spirit Rise and enter the pools of vision": the way
-- in, on top of Spirit Rise), which RestedXP points at till the player comes within its few yards: with the player
-- already at the place the step leads to (the next step's waypoint, or its label's, within LEAD_YD), that place is the
-- stop instead. In the Pools of Vision beside Apothecary Zamah the route went back up and out to the way in (seen in
-- game 2026-11-12). RestedXP's own `RXP` (its addon table) for the guide's steps; read only.
X.LEAD_YD = 40
function X.Lead(e)
  local s = e.step
  local cw = s.completewith
  if not cw then return e end
  local rxp = rawget(_G, "RXP")
  local guide = type(rxp) == "table" and rxp.currentGuide
  if type(guide) ~= "table" or type(guide.steps) ~= "table" then return e end
  local idx = cw == "next" and tonumber(s.index) and s.index + 1 or (type(guide.labels) == "table" and guide.labels[cw])
  local t = idx and guide.steps[idx]
  if type(t) ~= "table" or t.completed or type(t.elements) ~= "table" then return e end
  local N = ns.Nav
  local px, py = N and N.playerX, N and N.playerY
  if not (px and py) then return e end
  for _, f in ipairs(t.elements) do
    local wx, wy = type(f) == "table" and tonumber(f.wx), type(f) == "table" and tonumber(f.wy)
    if wx and wy and tonumber(f.instance) == tonumber(e.instance) and not f.skip then
      -- (RestedXP's wx, wy: AzerothGPS's y, x)
      if (wy - px) ^ 2 + (wx - py) ^ 2 <= X.LEAD_YD ^ 2 then
        if f.step == nil then f.step = t end -- (its own step, as the arrow's element has)
        return f
      end
      return e
    end
  end
  return e
end

-- The level a step's place is on: its zone's (`e.zone`, a uiMap) when that's a city's own level (Undercity, down under
-- the ruins: 2026-11-08, "Enter the Royal Quarter" was put on the surface and the route went up the lift and out),
-- else the continent RestedXP gives.
function X.Cont(e)
  local c = tonumber(e.zone) and ns.Geo and ns.Geo.MapCont and ns.Geo.MapCont(tonumber(e.zone))
  if c and ns.CityLevels and ns.CityLevels[c] then return c end
  return tonumber(e.instance)
end

-- The height of a step's place, where floors lie over each other (RestedXP gives none; 2026-11-08, "Talk to Neeru
-- Fireblade" down in Orgrimmar's Cleft of Shadow went to the Drag's street over her, 600 yd round from 55 yd off): the
-- shipped height of its waypoint (Data/GuideFloors.lua, `agps rxp-floors`: its step's NPC's, within TABLE_YD), else
-- the shipped height of an NPC's spot there (Nav's N.SpawnZ: in the capitals and the caves;
-- 2026-11-14), else an NPC the player talked to there (Layers' NPCs, within NPC_YD: its floor), else, the roads near it being on floors
-- FLOOR_Z apart, the one nearest the floor the player is followed on, within FLOOR_NEAR_YD (wrong one time in four
-- along the guides, so last). Nil with one floor there, or nothing to tell. All the game's heights.
X.TABLE_YD, X.NPC_YD, X.FLOOR_NEAR_YD, X.FLOOR_ROAD_YD, X.FLOOR_Z = 2, 10, 200, 15, 8
function X.TableHeight(cont, x, y)
  local t = ns.GuideFloors and ns.GuideFloors[cont]
  local best, bd
  for i = 1, t and #t - 2 or 0, 3 do
    local d = (t[i] - x) ^ 2 + (t[i + 1] - y) ^ 2
    if d <= X.TABLE_YD ^ 2 and (not bd or d < bd) then best, bd = t[i + 2], d end
  end
  return best
end
function X.Height(e, cont)
  return X.HeightXY(cont, e.wy, e.wx)
end
-- (the same at (x, y): every guide route's, Zygor's, Polestar's, Questify's and Azeroth Pilot's too)
function X.HeightXY(cont, x, y)
  local N = ns.Nav
  return X.TableHeight(cont, x, y) or (N and N.SpawnZ and N.SpawnZ(cont, x, y)) or X.HeightAt(cont, x, y)
end
-- The same without the shipped table (an NPC talked to there, else the followed floor).
function X.HeightAt(cont, x, y)
  local best, bd
  for _, n in pairs(ns.db and ns.db.npcs or {}) do
    if type(n) == "table" and not n.imported then
      local spots = { n }
      for _, s in ipairs(n.spots or {}) do spots[#spots + 1] = s end
      for _, s in ipairs(spots) do
        if s.z and s.cont == cont and s.x then
          local d = (s.x - x) ^ 2 + (s.y - y) ^ 2
          if d <= X.NPC_YD ^ 2 and (not bd or d < bd) then best, bd = s.z, d end
        end
      end
    end
  end
  if best then return best end
  local N, R = ns.Nav, ns.Router
  local z = N and N.FollowedZ and N.FollowedZ(cont)
  local px, py = N and N.playerX, N and N.playerY
  if not (z and px and R and R.HeightsNear) or (px - x) ^ 2 + (py - y) ^ 2 > X.FLOOR_NEAR_YD ^ 2 then return nil end
  local hs = R.HeightsNear(cont, x, y, X.FLOOR_ROAD_YD)
  if not hs or #hs == 0 then return nil end
  local lo, hi, pick = math.huge, -math.huge, nil
  for _, h in ipairs(hs) do
    lo, hi = math.min(lo, h.z), math.max(hi, h.z)
    if not pick or math.abs(h.z - z) < math.abs(pick - z) then pick = h.z end
  end
  if hi - lo <= X.FLOOR_Z or math.abs(pick - z) > X.FLOOR_Z then return nil end
  return pick
end

-- A step place's key: the step, where and on what level (RestedXP's own hash is made again at each load).
function X.Key(e)
  return string.format("%s:%.1f,%.1f@%s", tostring(e.step.index or e.step.title or "?"), e.wx, e.wy, tostring(X.Cont(e)))
end

-- The stop's name: the waypoint's or the step's title (RestedXP's color tags taken out), else "Step n".
function X.Name(e)
  local s = e.step
  local t = e.title or s.arrowtext or s.title
  if type(t) == "string" then
    t = t:gsub("RXP_[A-Z]+_", ""):gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("%s+", " ")
    t = t:match("^%s*(.-)%s*$")
  end
  if type(t) ~= "string" or t == "" then t = s.index and L["Step %s"]:format(tostring(s.index)) or L["Step"] end
  return "RestedXP: " .. t
end

-- The route's RestedXP stop: index, stop (or nil).
function X.Stop()
  for i, d in ipairs(ns.Nav and ns.Nav.stops or {}) do
    if d.rxp then return i, d end
  end
end

-- One look at RestedXP's arrow (every X.TICK while on).
function X.Tick()
  if not X.On() or not ns.Nav then return end
  local N = ns.Nav
  local e = X.Element()
  local key = e and X.Key(e)
  local i, d = X.Stop()
  if d and d.rxp ~= key then
    -- (RestedXP moved past it: the step is done, so is the stop)
    N.RemoveStop(i)
    d = nil
  end
  if d and d.z == nil then
    -- (its floor told since: the player's followed floor taken up, an NPC there talked to)
    local z = X.Height(e, d.cont)
    if z then
      d.z = z
      if N.Invalidate then N.Invalidate() end
    end
  end
  if key and not d then
    if X.lastKey == key then
      -- (RestedXP still on the same step and its stop gone: another route was picked, or it was removed by hand)
      X.SetOn(false)
      ns.Print(L["RestedXP Route: off (the route was changed). Click RestedXP Route to follow the guide again."])
      return
    end
    local cont = X.Cont(e)
    N.InsertStop({ x = e.wy, y = e.wx, z = X.Height(e, cont), cont = cont, name = X.Name(e), rxp = key }, 1, true)
  end
  X.lastKey = key
end

function X.SetOn(on)
  local cdb = CDB()
  if not cdb then return end
  cdb.rxpFollow = on and true or false -- (off is kept too: the default is on)
  X.lastKey = nil
end

-- The button: on replaces the route with RestedXP's current step (and each one after it); off leaves the route.
function X.Toggle()
  if not X.Available() then
    ns.Print(L["RestedXP Route: RestedXP Guides isn't loaded."])
    return
  end
  if X.On() then
    X.SetOn(false)
    local i = X.Stop()
    if i then ns.Nav.RemoveStop(i) end
    ns.Print(L["RestedXP Route: off."])
    return
  end
  for _, k in ipairs({ "Zygor", "Polestar", "Questify", "AzerothPilot", "OpenXP" }) do -- (one guide at a time)
    local g = ns[k]
    if g and g.On and g.On() then g.Toggle() end
  end
  if ns.Nav.Clear then ns.Nav.Clear() end
  X.SetOn(true)
  X.Tick()
  ns.Print(X.Stop() and L["RestedXP Route: on. Each RestedXP step is your next stop; it's done when RestedXP checks it off."]
    or L["RestedXP Route: on. RestedXP's step has no place to go right now; the route starts at the next one that has."])
end

if C_Timer and C_Timer.NewTicker then
  X.ticker = C_Timer.NewTicker(X.TICK, function()
    local ok, err = pcall(X.Tick)
    if not ok and ns.GPS and ns.GPS.LogError then ns.GPS.LogError("RestedXP Route", err) end
  end)
end
