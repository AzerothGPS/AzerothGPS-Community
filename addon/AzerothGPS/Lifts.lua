-- Lift timing (item 118, 1.4.1; the idea from Shortest Path Forever, GPL-3, which times lifts by the player's height:
-- our own code, by floors, as this client gives no height).
--
-- Each lift car loops on a fixed timetable: the client's own TransportAnimation, Data/LiftTimes.lua (`agps lifts
-- --times`): its loop's length and when in it the car stands at the bottom and at the top. Where in the loop it is now
-- is the server's and isn't told to addons, so it's learned from the rides the player is seen taking: on a car's shaft
-- (CAR_YD) having come from one floor (the floor followed by it, NEAR_YD: Nav's, the city grid's, the world grid's;
-- Undercity's by its level), then off it onto the other floor (within EXIT_WAIT) is a ride, the car having stopped there
-- shortly before they stepped off (STEP_OFF; never sooner than the ride's own time after they got on). That gives the
-- car's phase, kept per realm and car in the addon's own saved data (ns.db.lifts) against the server's time (sub-second
-- by GetTime against GetServerTime's tick, LT.Now), and the next car's arrival at either floor follows ("lift arrives
-- in 12 s" on the directions' line, Turns.NowText; "Board the lift", Nav's panel). No phase known (or older than
-- KEEP_HOURS: the server may have restarted since): nothing said, the route's fixed lift time as before.
--
-- The cars: Thunder Bluff's two lifts (two cars each, side by side), the Great Lift's and Freewind Post's (two each),
-- Undercity's three (one car each). Their cars' loops differ by 33 ms in places (30.000 s and 30.033 s): each car is
-- phased on its own. What it saw: ns.db.liftLog (the last LOG_MAX).
local _, ns = ...
local LT = {}
ns.Lifts = LT
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end })

LT.CAR_YD = 5 -- on a car: this near its shaft
LT.OFF_YD = 7 -- off it: this far (between the two: as it was)
LT.NEAR_YD = 30 -- the floor followed this near a lift's car is the one boarded from ...
LT.NEAR_FRESH = 30 -- ... seen within this many seconds before getting on
LT.EXIT_WAIT = 20 -- seconds after stepping off: the other floor seen by then, a ride
LT.STEP_OFF = 1 -- seconds: stepped off about this soon after the car stopped
LT.SAME_TOL = 2 -- seconds: a ride this near the phase kept sharpens it (averaged); else it replaces it
LT.KEEP_HOURS = 24 -- a phase older than this isn't used (kept: a newer ride replaces it)
LT.STATION_YD = 120 -- a lift maneuver's or a ride's spot this near a car is that car's lift (the Great Lift's road starts
-- 78 yd from its shafts)
LT.NOTE_YD = 100 -- the wait is said on the directions' line this near the lift
LT.LOG_MAX = 20

local function Dist2(x1, y1, x2, y2) return (x1 - x2) ^ 2 + (y1 - y2) ^ 2 end

---------------------------------------------------------------------------
-- The clock: the server's time to a fraction of a second. GetServerTime counts whole seconds; each look bounds
-- GetServerTime() - GetTime() (at or above `lo`, below `hi`), the bounds narrowing as the second ticks over.
---------------------------------------------------------------------------
local clockLo, clockHi
function LT.NoteClock(now, server)
  if not (now and server) then return end
  local lo, hi = server - now, server + 1 - now
  if clockLo and (lo > clockHi + 0.05 or hi < clockLo - 0.05) then clockLo, clockHi = nil, nil end -- (the clock jumped)
  clockLo = clockLo and math.max(clockLo, lo) or lo
  clockHi = clockHi and math.min(clockHi, hi) or hi
  if clockLo > clockHi then clockLo, clockHi = lo, hi end
end
-- The server's time now (seconds, fractional), from GetTime `now` (and GetServerTime `server`, noted).
function LT.Now(now, server)
  now = now or GetTime()
  server = server or (GetServerTime and GetServerTime()) or (time and time()) or 0
  LT.NoteClock(now, server)
  return now + (clockLo + clockHi) / 2
end
function LT.ResetClock() clockLo, clockHi = nil, nil end -- (the tests)

---------------------------------------------------------------------------
-- The cars and the phases learned
---------------------------------------------------------------------------
function LT.CarKey(c) return string.format("%d@%d,%d", c.entry, math.floor(c.x + 0.5), math.floor(c.y + 0.5)) end

-- Whether car `c` is on `level` (Undercity's: its city level too, drawn in its continent's coordinates).
local function OnLevel(c, level) return level == c.cont or (c.city ~= nil and level == c.city) end

-- The car whose shaft is within `r` of (x, y) on `level`, nearest, or nil.
function LT.CarAt(level, x, y, r)
  local best, bd
  for _, c in ipairs(ns.LiftCars or {}) do
    if OnLevel(c, level) then
      local d = Dist2(c.x, c.y, x, y)
      if d <= r * r and (not bd or d < bd) then best, bd = c, d end
    end
  end
  return best
end

local function Realm() return (ns.RealmName and ns.RealmName()) or "?" end
-- The phases learned: { [car key] = { phase (s: the server time the loop last began, mod its period), at (the ride's
-- server time), n (rides it's from) } }, this realm's.
function LT.Sightings()
  if not ns.db then return {} end
  ns.db.lifts = ns.db.lifts or {}
  local r = Realm()
  ns.db.lifts[r] = ns.db.lifts[r] or {}
  return ns.db.lifts[r]
end

function LT.Log(text)
  if not ns.db then return end
  ns.db.liftLog = ns.db.liftLog or {}
  local log = ns.db.liftLog
  log[#log + 1] = (date and date("%m-%d %H:%M:%S ") or "") .. text
  while #log > LT.LOG_MAX do table.remove(log, 1) end
end

-- The floor ("bottom" / "top") of car `c` the player stands on at (px, py) on `level`, or nil when not known:
-- Undercity's by the level (down in the city: the bottom); else the floor followed (LT.PlayerFloorZ) nearer one end.
function LT.PlayerFloorZ(level, px, py)
  local N, CG = ns.Nav, ns.CityGrid
  return (N and N.PlayerZ and N.PlayerZ()) or (CG and CG.PlayerFloorZ and CG.PlayerFloorZ(level, px, py))
    or (N and N.FollowedZ and N.FollowedZ(level)) or (N and N.GridTrackZ and N.GridTrackZ(level)) or nil
end
function LT.FloorAt(c, level, px, py)
  if c.city then
    if level == c.city then return "bottom" end
    if level == c.cont then return "top" end
    return nil
  end
  if level ~= c.cont then return nil end
  local z = LT.PlayerFloorZ(level, px, py)
  if type(z) ~= "number" then return nil end
  local span = c.hi - c.lo
  if math.abs(z - c.lo) <= span * 0.25 then return "bottom" end
  if math.abs(z - c.hi) <= span * 0.25 then return "top" end
  return nil
end

local function Mod(a, p) return a - math.floor(a / p) * p end

-- A ride seen on car `c` to floor `to`: on it from `tb`, last on it at `ta` (server times). The car stopped there
-- STEP_OFF before `ta`, never sooner than the ride's own time after `tb` nor before it could have left again; a ride
-- that couldn't be (quicker than the car: a fall down the shaft) isn't one. Returns the phase, or nil.
function LT.Rode(c, to, tb, ta)
  local P = c.period
  local from = to == "top" and "bottom" or "top"
  local wa, wb = c[from], c[to]
  if not (P and wa and wb) then return nil end
  local travel = Mod(wb[1] - wa[2], P) -- (leaves one end, stops at the other)
  local dwell = wb[2] - wb[1]
  local lo = math.max(tb + travel, ta - dwell)
  if lo > ta + 0.5 then
    LT.Log(string.format("%s %s: %.1f s on it, quicker than its %.1f s ride: not a ride", c.place, LT.CarKey(c),
      ta - tb, travel))
    return nil
  end
  local stopped = math.min(ta, math.max(lo, ta - LT.STEP_OFF))
  local phase = Mod(stopped - wb[1], P)
  local seen = LT.Sightings()
  local key = LT.CarKey(c)
  local old = seen[key]
  local fresh = old and old.phase and old.at and ta - old.at <= LT.KEEP_HOURS * 3600
  if fresh then
    local d = Mod(phase - old.phase + P / 2, P) - P / 2
    if math.abs(d) <= LT.SAME_TOL then
      local n = math.min(old.n or 1, 4)
      phase = Mod(old.phase + d / (n + 1), P)
      seen[key] = { phase = phase, at = ta, n = (old.n or 1) + 1 }
      LT.Log(string.format("%s %s to the %s: %.1f s off, now %.2f (%d rides)", c.place, key, to, d, phase,
        seen[key].n))
      return phase
    end
  end
  seen[key] = { phase = phase, at = ta, n = 1 }
  LT.Log(string.format("%s %s to the %s at %.1f: phase %.2f%s", c.place, key, to, ta, phase,
    old and old.phase and string.format(" (was %.2f)", old.phase) or ""))
  return phase
end

-- Car `c`'s next stop at floor `floor` from server time `t`: (wait, leaves): 0 and the seconds till it leaves while it
-- stands there; else the seconds till it stops there and how long it stands. Nil when its phase isn't known.
function LT.CarWait(c, floor, t)
  local s = LT.Sightings()[LT.CarKey(c)]
  local w = c[floor]
  if not (s and s.phase and s.at and w and c.period) or t - s.at > LT.KEEP_HOURS * 3600 then return nil end
  local P = c.period
  local a = Mod(t - s.phase, P) -- (where in its loop it is now)
  local into = Mod(a - w[1], P)
  local dwell = w[2] - w[1]
  if into < dwell then return 0, dwell - into end
  return Mod(w[1] - a, P), dwell
end

-- The next car at `floor` of the lift (its cars: LT.CarAt's station) by (x, y) on `level`, from server time `t`: wait,
-- leaves (as CarWait: the soonest of its cars known), or nil.
function LT.LiftWait(level, x, y, floor, t)
  local near = LT.CarAt(level, x, y, LT.STATION_YD)
  if not near then return nil end
  local bw, bl
  for _, c in ipairs(ns.LiftCars or {}) do
    if c.station == near.station then
      local w, l = LT.CarWait(c, floor, t)
      if w and (not bw or w < bw or (w == bw and l > bl)) then bw, bl = w, l end
    end
  end
  return bw, bl
end

-- The words for the wait: "lift arrives in 12s" / "lift here, leaves in 4s", or nil (no phase known).
function LT.WaitWords(level, x, y, floor, t)
  local w, l = LT.LiftWait(level, x, y, floor, t or LT.Now())
  if not w then return nil end
  local N = ns.Nav
  local fmt = N and N.FormatTime or function(s) return string.format("%ds", math.floor(s + 0.5)) end
  if w <= 0 then return string.format(L["lift here, leaves in %s"], fmt(math.max(l, 0))) end
  return string.format(L["lift arrives in %s"], fmt(w))
end

-- The words for maneuver `m`'s lift (Turns: `m.lift` = { level, x, y, floor }), within NOTE_YD of it, or nil.
function LT.ManeuverWords(m)
  local f = m and m.lift
  if not f or (m.dist or 0) > LT.NOTE_YD then return nil end
  return LT.WaitWords(f.level, f.x, f.y, f.floor)
end
---------------------------------------------------------------------------
-- The wait in the route's costs (item 135a, 1.4.2; an idea from Polestar, GPL-3: our own code). The data prices each
-- lift at a fixed wait and ride (AVG_SECONDS: capitals.py's, lifts.py's and cities.py's LIFT_SECONDS, as yards walked
-- at YD_PER_SECOND). With a car's phase known, the lift costs the wait for the next car at the time the player gets
-- there (ETA: from where they stand now, at ETA_SPEED) and its ride instead. Worked out once per lift and floor and
-- kept for the trip (LT.ResetCosts, Nav's new stops): the route doesn't change as the cars come and go, only when a
-- phase is learned or changes (a ride seen, LT.Rode: one reroute then).
---------------------------------------------------------------------------
LT.AVG_SECONDS = { ["Undercity"] = 25, ["Thunder Bluff"] = 20, ["Thousand Needles"] = 30 }
LT.YD_PER_SECOND = 7
LT.ETA_SPEED = 7 -- yards a second to the lift (the run's)
local costs = {} -- [station .. floor] = { stamp, seconds }
function LT.ResetCosts() costs = {} end

-- The phases known for the cars of `station`, as one string ("" when none: nothing to price).
local function Stamp(station, t)
  local seen, parts = LT.Sightings(), {}
  for _, c in ipairs(ns.LiftCars or {}) do
    local s = c.station == station and seen[LT.CarKey(c)]
    if s and s.phase and s.at and t - s.at <= LT.KEEP_HOURS * 3600 then
      parts[#parts + 1] = string.format("%s=%.2f@%.0f", LT.CarKey(c), s.phase, s.at)
    end
  end
  return table.concat(parts, ";")
end

-- The player's yards to (x, y) on `level`, or nil.
local function YardsTo(level, x, y)
  local ok, px, py, _, cont = pcall(UnitPosition, "player")
  if not ok or not px or (ns.IsSecret and (ns.IsSecret(px) or ns.IsSecret(py) or ns.IsSecret(cont))) then return nil end
  local N = ns.Nav
  local lv = N and N.PlayerLevel and N.PlayerLevel(cont) or cont
  if lv ~= level and cont ~= level then return nil end
  return math.sqrt(Dist2(px, py, x, y))
end

-- The seconds car `c` takes from leaving `floor` to stopping at the other.
local function RideSeconds(c, floor)
  local other = floor == "bottom" and "top" or "bottom"
  local a, b = c[floor], c[other]
  if not (a and b and c.period) then return nil end
  return Mod(b[1] - a[2], c.period)
end

-- The lift's wait and ride boarded at `floor` ("bottom" / "top") by (x, y) on `level`, as seconds over the data's fixed
-- ones (less than 0: quicker), or 0 when no car's phase is known there. `eta`: the seconds till the player gets there
-- (nil: from where they stand, ETA_SPEED).
function LT.CostSeconds(level, x, y, floor, eta)
  local near = level and x and y and LT.CarAt(level, x, y, LT.STATION_YD)
  if not near then return 0 end
  local now = LT.Now()
  local stamp = Stamp(near.station, now)
  local key = near.station .. floor
  if stamp == "" then
    costs[key] = nil
    return 0
  end
  local m = costs[key]
  if m and m[1] == stamp then return m[2] end
  if not eta then
    local yd = YardsTo(level, x, y)
    eta = yd and yd / LT.ETA_SPEED or 0
  end
  -- (the soonest of its cars there then, and that car's ride)
  local w, ride
  for _, c in ipairs(ns.LiftCars or {}) do
    if c.station == near.station then
      local cw = LT.CarWait(c, floor, now + eta)
      if cw and (not w or cw < w) then w, ride = cw, RideSeconds(c, floor) end
    end
  end
  local avg = LT.AVG_SECONDS[near.place]
  local d = (w and ride and avg) and (w + ride - avg) or 0
  costs[key] = { stamp, d }
  return d
end

-- The same as yards walked (Router's, the grids' lift roads and links), never under -`floorYd` (their own length).
function LT.CostYards(level, x, y, floor, floorYd)
  local d = LT.CostSeconds(level, x, y, floor) * LT.YD_PER_SECOND
  if floorYd and d < -floorYd then d = -floorYd end
  return d
end

-- A phase learned or changed (LT.Rode): the lifts' costs worked out again, the route once.
local Rode = LT.Rode
function LT.Rode(c, to, tb, ta)
  local was = Stamp(c.station, ta)
  local phase = Rode(c, to, tb, ta)
  if phase and Stamp(c.station, ta) ~= was then
    costs[c.station .. "bottom"], costs[c.station .. "top"] = nil, nil
    -- (the grids' walks kept with the old costs: searched again)
    local WG, CG = ns.WorldGrid, ns.CityGrid
    if WG and WG.routes then WG.routes, WG.order = {}, {} end
    if CG and CG.routes then CG.routes, CG.order = {}, {} end
    local N = ns.Nav
    if N and N.Invalidate and N.stops and N.stops[1] then N.Invalidate(true) end
  end
  return phase
end

local on -- (below: on a car's shaft now)
-- Not while riding: on a car of that lift that isn't standing at the floor boarded from (it's left: the next car's
-- wait there is no use now).
local WaitWords = LT.WaitWords
function LT.WaitWords(level, x, y, floor, t)
  t = t or LT.Now()
  if on and on.car then
    local near = LT.CarAt(level, x, y, LT.STATION_YD)
    if near and near.station == on.car.station then
      local w = LT.CarWait(on.car, floor, t)
      if w and w > 0 then return nil end
    end
  end
  return WaitWords(level, x, y, floor, t)
end

-- The floor a ride on transport row `t` (a lift: Undercity's) boards at from its side `from`: { level, x, y, floor }.
function LT.RideLift(t, from)
  if not (t and t[8] == "lift") then return nil end
  local e = from == 2 and 2 or 1
  local level, x, y = t[e * 3 - 2], t[e * 3 - 1], t[e * 3]
  local c = x and LT.CarAt(level, x, y, LT.STATION_YD)
  if not c then return nil end
  -- (the end down in the city, or the lower of the two: the bottom)
  local floor
  if c.city then
    floor = level == c.city and "bottom" or "top"
  else
    local z1, z2 = t.z1, t.z2
    floor = (z1 and z2) and (((e == 1) == (z1 < z2)) and "bottom" or "top") or (e == 1 and "bottom" or "top")
  end
  return { level = level, x = x, y = y, floor = floor }
end

---------------------------------------------------------------------------
-- The rides, seen every half second
---------------------------------------------------------------------------
local approach -- { car, floor, at }: the floor last seen by a lift
-- (`on`, above: { car, floor, enteredAt, lastIn }: on a car's shaft now)
local off -- { car, floor, enteredAt, lastIn, since }: stepped off it, the floor not seen yet
function LT.Reset() approach, on, off = nil, nil, nil end -- (the tests)
function LT.State() return { approach = approach, on = on, off = off } end -- (the tests)

function LT.Tick(now, server, level, px, py)
  if not (level and px and py) then return end
  local t = LT.Now(now, server)
  local inCar = LT.CarAt(level, px, py, LT.CAR_YD)
  if on and not inCar then
    -- (in the band between CAR_YD and OFF_YD: still on it)
    local c = on.car
    if OnLevel(c, level) and Dist2(c.x, c.y, px, py) <= LT.OFF_YD ^ 2 then inCar = c end
  end
  if inCar then
    if on and on.car == inCar then
      on.lastIn = t
    else
      local fl = approach and approach.car.station == inCar.station and t - approach.at <= LT.NEAR_FRESH
        and approach.floor or nil
      -- (Undercity's: its level says the floor even on the car; the others' floor followed opens up at the lift)
      if not fl and inCar.city then fl = LT.FloorAt(inCar, level, px, py) end
      on, off = { car = inCar, floor = fl, enteredAt = t, lastIn = t }, nil
    end
    return
  end
  if on then
    off = on.floor and { car = on.car, floor = on.floor, enteredAt = on.enteredAt, lastIn = on.lastIn, since = t } or nil
    on = nil
  end
  local near = LT.CarAt(level, px, py, LT.NEAR_YD)
  local fl = near and LT.FloorAt(near, level, px, py)
  if off then
    local c = off.car
    local f = (near and near.station == c.station) and fl or LT.FloorAt(c, level, px, py)
    if f and f ~= off.floor then
      LT.Rode(c, f, off.enteredAt - 0.25, off.lastIn + 0.25)
      off = nil
    elseif t - off.since > LT.EXIT_WAIT then
      off = nil
    end
  end
  if near and fl then approach = { car = near, floor = fl, at = t } end
end

do
  local function tick()
    local ok, px, py, _, cont = pcall(UnitPosition, "player")
    if not ok or not px or (ns.IsSecret and (ns.IsSecret(px) or ns.IsSecret(py) or ns.IsSecret(cont))) then return end
    if ns.Geo and ns.Geo.override then return end -- (the dev tools' simulated player: not a ride)
    local N = ns.Nav
    local level = N and N.PlayerLevel and N.PlayerLevel(cont) or cont
    pcall(LT.Tick, GetTime(), GetServerTime and GetServerTime() or time(), level, px, py)
  end
  if C_Timer and C_Timer.NewTicker then C_Timer.NewTicker(0.5, tick) end
end
