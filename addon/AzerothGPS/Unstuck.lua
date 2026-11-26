-- Unstuck (item 117a, 1.4.1, the grid ideas): running into a wall the grids know.
--
-- The player keeps moving forward (the game says so: IsPlayerMoving, a speed) but their spot doesn't change for
-- STUCK_SECONDS, and the grid they're on (the capital's city grid, else the world grid, else the terrain grid) has no
-- way on from their floor a few yards ahead (PROBE_YD): they're pushing into a wall. The nearest way round it that the
-- grid walks (ROUND_YD out, every ROUND_STEP degrees either side), the one nearest the route's way on when there's a
-- route, is offered on the directions' line ("Blocked ahead: go around to your left") until they've moved off the spot
-- (CLEAR_YD) or SHOW_SECONDS have passed. Nothing is offered where the grid sees no wall there: that's for the dev
-- tools only (Nav.StuckHook: every stuck spot, the grid's wall or not, is handed to it; the shipped addon keeps none).
--
-- Never while the game moves the player some other way or their spot can't say: on a flight (UnitOnTaxi), on a boat or
-- a zeppelin (Taxi.Riding, Taxi.CurrentRide) or at its dock (Taxi.DockAt), at a lift or a teleporter (Nav.AtLift), in a
-- vehicle, flying, falling, swimming, casting or channeling, standing still (no speed), or after a gap in the looks
-- (GAP_SECONDS: the map and arrow closed, a loading screen). The tram is an instance's map: no grid, nothing offered.
local _, ns = ...
local U = {}
ns.Unstuck = U
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end })

local sqrt, abs, cos, sin, atan2, pi = math.sqrt, math.abs, math.cos, math.sin, math.atan2 or math.atan, math.pi

U.STUCK_SECONDS = 2.5 -- pushing this long ...
U.MOVE_YD = 1.5 -- ... within this of one spot: stuck
U.GAP_SECONDS = 1 -- looks further apart than this start over
U.PROBE_YD = 4 -- yards ahead the grid is asked for a way on (a body's length or two: the wall in front)
U.ROUND_YD = 10 -- a way round: the grid walks this far that way from the player's floor
U.ROUND_STEP = 30 -- degrees between the ways tried, either side, out to straight back
U.AIM_YD = 25 -- the route's way on: its point this far ahead of the nearest
U.CLEAR_YD = 5 -- moved this far from the stuck spot: the offer's gone
U.SHOW_SECONDS = 20
U.SIDE_DEG = 135 -- a way round past this from the facing: "turn back"

U.state = nil -- the offer: { at, level, x, y, wall, side, deg }
U.last = nil -- the last stuck spot found (the dev tools' readout): as `state`, plus z and why
local anchor, lastAt

local function Ask(fn, ...)
  if not fn then return nil end
  local ok, v = pcall(fn, ...)
  if not ok or (ns.IsSecret and ns.IsSecret(v)) then return nil end
  return v
end

-- Whether the player is pushing on (a movement key held, a speed): the dev tools' simulated player as it says.
function U.Pushing()
  local o = ns.Geo.override
  if o then return o.moving and true or false end
  if IsPlayerMoving and Ask(IsPlayerMoving) ~= true then return false end
  local sp = Ask(GetUnitSpeed, "player")
  return type(sp) == "number" and sp > 0.1
end

-- Why a stuck look means nothing now (a ride, a lift, a cast...), or nil.
function U.NotNow(level, px, py)
  local N, T = ns.Nav, ns.Taxi
  if Ask(UnitOnTaxi, "player") then return "taxi" end
  if T and ((T.Riding and T.Riding()) or (T.CurrentRide and Ask(T.CurrentRide))) then return "ride" end
  if T and T.DockAt and Ask(T.DockAt, level, px, py) then return "dock" end
  if Ask(UnitInVehicle, "player") or Ask(UnitUsingVehicle, "player") then return "vehicle" end
  if Ask(IsFlying) then return "flying" end
  if N and N.Falling and N.Falling() then return "falling" end
  if N and N.Swimming and N.Swimming() then return "swimming" end
  if Ask(UnitCastingInfo, "player") or Ask(UnitChannelInfo, "player") then return "casting" end
  if N and N.AtLift and N.AtLift(level, px, py) then return "lift" end
  return nil
end

-- The player's floor as the trackers know it now (no surface looked up): z, else zs (the candidates), else nil.
function U.Floor(level, px, py)
  local N, CG = ns.Nav, ns.CityGrid
  local z = N.PlayerZ() or (CG and CG.PlayerFloorZ and CG.PlayerFloorZ(level, px, py)) or N.FollowedZ(level)
    or (N.GridTrackZ and N.GridTrackZ(level))
  if z then return z, nil end
  local zs = (N.GridCandidates and N.GridCandidates(level, px, py))
    or (CG and CG.PlayerFloorZs and CG.PlayerFloorZs(level, px, py))
  return nil, zs
end

-- A function telling whether the grid at (px, py) on `level` walks from the player's floor `z` (nil: any) the straight
-- line `yd` toward `dir` (radians, as the game's facing: counter-clockwise from north, +x), and which grid answers
-- ("city", "world", "terrain"); nil where none has the spot.
function U.Probe(level, px, py, z)
  local CG, WG, P = ns.CityGrid, ns.WorldGrid, ns.Passability
  local name = CG and CG.On and CG.On() and CG.GridCityAt and CG.GridCityAt(level, px, py)
  local c = name and CG.City(name)
  if c then
    local ss = CG.SurfacesAt(c, px, py, z)
    local s0 = ss[1]
    if not s0 or (z and abs(s0.z - z) > CG.FLOOR_Z) then return nil end
    local x0, y0 = px, py
    if CG.CellAt(c, px, py) ~= s0.ci then x0, y0 = s0.x, s0.y end -- (the player's own cell bare: from the floor's)
    return function(dir, yd)
      local ok, line = pcall(CG.Line, c, s0.s, s0.ci, x0, y0, px + cos(dir) * yd, py + sin(dir) * yd)
      return ok and line ~= nil
    end, "city"
  end
  local wc = WG and WG.On and WG.On() and WG.Cont and WG.Cont(level)
  if wc and WG.Decoded and WG.Decoded(wc, px, py) then
    return function(dir, yd)
      local ok, clear = pcall(WG.Clear, wc, px, py, z, px + cos(dir) * yd, py + sin(dir) * yd, z)
      return ok and clear == true
    end, "world"
  end
  if P and P.IsOpen and P.IsOpen(level, px, py) then
    return function(dir, yd)
      for k = 1, 3 do
        if not P.IsOpen(level, px + cos(dir) * yd * k / 3, py + sin(dir) * yd * k / 3) then return false end
      end
      return true
    end, "terrain"
  end
  return nil
end

-- The route's way on from (px, py): the direction (radians, as the facing) to its point AIM_YD past the nearest, or nil.
function U.RouteAim(level, px, py)
  local N = ns.Nav
  local r = N.route
  local full = r and r.fullFirst
  local pts = full and full.cont == level and full.pts
  if not (pts and #pts >= 4) then return nil end
  local bi, bt, bd
  for i = math.max(1, r.followIdx or 1), #pts / 2 - 1 do
    local ax, ay, bx, by = pts[2 * i - 1], pts[2 * i], pts[2 * i + 1], pts[2 * i + 2]
    local vx, vy = bx - ax, by - ay
    local L2 = vx * vx + vy * vy
    local t = L2 > 0 and math.max(0, math.min(1, ((px - ax) * vx + (py - ay) * vy) / L2)) or 0
    local d2 = (ax + vx * t - px) ^ 2 + (ay + vy * t - py) ^ 2
    if not bd or d2 < bd then bi, bt, bd = i, t, d2 end
  end
  if not bi then return nil end
  local left = U.AIM_YD
  local i, t = bi, bt
  local tx, ty
  while i <= #pts / 2 - 1 do
    local ax, ay, bx, by = pts[2 * i - 1], pts[2 * i], pts[2 * i + 1], pts[2 * i + 2]
    local seg = sqrt((bx - ax) ^ 2 + (by - ay) ^ 2)
    local rest = seg * (1 - t)
    if rest >= left then
      local f = t + left / math.max(seg, 1e-6)
      tx, ty = ax + (bx - ax) * f, ay + (by - ay) * f
      break
    end
    left, i, t = left - rest, i + 1, 0
    tx, ty = bx, by
  end
  if not tx or (tx - px) ^ 2 + (ty - py) ^ 2 < 1 then return nil end
  return atan2(ty - py, tx - px)
end

local function Wrap(a) -- (-pi, pi]
  a = a % (2 * pi)
  if a > pi then a = a - 2 * pi end
  return a
end

-- The stuck spot looked at: whether the grid has a wall ahead (`wall`: true, false, or nil with no grid there), and
-- the nearest way round it the grid walks (`deg`: degrees from the facing, + to the left; `side`: "left", "right" or
-- "back"), the one nearest the route's way on (`aim`, radians) when given, else the smallest turn.
function U.Look(level, px, py, facing, aim)
  local z, zs = U.Floor(level, px, py)
  local floors = z and { z } or zs or { false }
  local out = { level = level, x = px, y = py, z = z, zs = zs, facing = facing }
  for _, fz in ipairs(floors) do
    local open, grid = U.Probe(level, px, py, fz or nil)
    if open then
      out.grid = grid
      if open(facing, U.PROBE_YD) then
        out.wall = false
        return out -- (the way ahead open on one of the floors they may be on: no wall of the grid's)
      end
      out.wall = true
      local best, bestScore
      for k = 1, math.floor(180 / U.ROUND_STEP) do
        for _, sgn in ipairs({ 1, -1 }) do
          local deg = sgn * k * U.ROUND_STEP
          if k * U.ROUND_STEP < 180 or sgn == 1 then
            local dir = facing + math.rad(deg)
            if open(dir, U.ROUND_YD) then
              local score = abs(deg) / 1000 + (aim and abs(Wrap(dir - aim)) or 0)
              if not bestScore or score < bestScore - 1e-9 then best, bestScore = deg, score end
            end
          end
        end
      end
      if best then
        out.deg = best
        out.side = abs(best) > U.SIDE_DEG and "back" or (best > 0 and "left" or "right")
        return out
      end
    end
  end
  return out
end

-- Every status update (Nav.Status): the stuck watch. `level`: the player's (Nav.PlayerLevel).
function U.Watch(px, py, level)
  local now = GetTime()
  local st = U.state
  if st and (now - st.at > U.SHOW_SECONDS or not px or st.level ~= level
      or (st.x - px) ^ 2 + (st.y - py) ^ 2 > U.CLEAR_YD ^ 2) then
    U.state = nil
  end
  local gap = not lastAt or now - lastAt > U.GAP_SECONDS or now < lastAt
  lastAt = now
  if not px or gap or not U.Pushing() then
    anchor = nil
    return
  end
  if not anchor or anchor.level ~= level or (anchor.x - px) ^ 2 + (anchor.y - py) ^ 2 > U.MOVE_YD ^ 2 then
    anchor = { at = now, x = px, y = py, level = level }
    return
  end
  if anchor.done or now - anchor.at < U.STUCK_SECONDS then return end
  local why = U.NotNow(level, px, py)
  if why then
    anchor = nil
    return
  end
  anchor.done = true -- (once a spot: moved off it, watched again)
  local facing = ns.Geo.Facing()
  local ok, look = pcall(U.Look, level, px, py, facing, U.RouteAim(level, px, py))
  if not ok or not look then return end
  look.at = now
  U.last = look
  if look.wall and look.side then U.state = look end
  local N = ns.Nav
  if N.StuckHook then pcall(N.StuckHook, look) end -- (the dev tools: every stuck spot, flagged there)
end

-- The directions' line while the offer stands (only with a wall the grid knows and a way round it), or nil.
function U.Text(px, py, level)
  local st = U.state
  if not (st and st.side and px and st.level == level) then return nil end
  if GetTime() - st.at > U.SHOW_SECONDS or (st.x - px) ^ 2 + (st.y - py) ^ 2 > U.CLEAR_YD ^ 2 then return nil end
  if st.side == "left" then return L["Blocked ahead: go around to your left"] end
  if st.side == "right" then return L["Blocked ahead: go around to your right"] end
  return L["Blocked ahead: turn back and go around"]
end

function U.Reset() U.state, U.last, anchor, lastAt = nil, nil, nil, nil end -- (the tests)
