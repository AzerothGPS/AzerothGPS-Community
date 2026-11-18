-- Turn-by-turn: the maneuvers ahead on the route (turns, joining/leaving the road,
-- boarding a zeppelin or boat, arriving at a stop) and where the direction arrow points.
-- Pure Lua (no frames), unit-tested with lupa.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)
local Format = ns.Format or string.format

local T = {}
ns.Turns = T

T.WINDOW = 35 -- yards before/after a point to measure how much the route bends there
T.MIN_ANGLE = 50 -- degrees: off-road, a curve turning less than this is just "continue" (the arrow points the way)
T.JUNCTION_ANGLE = 40 -- degrees: at a road junction, from this much it's a turn (less: straight on)
T.ROAD_BEND_ANGLE = 75 -- degrees: along a road away from junctions, only bends this sharp
T.BEND_START = 8 -- degrees: points bending at least this much belong to a curve
T.END_QUIET = 25 -- yards: no instructions this close to the stop ("Arrive" covers it)
T.HOP_YD = 60 -- yards: briefer stretches on (or off) a road aren't announced
T.MIN_AHEAD = 5 -- yards: bends closer than this are already being taken
T.JOG_YD = 60 -- yards: turns this close together are one run (a jog, if it nets out)
T.JOG_OFFSET = 12 -- yards: ... and a jog when the route after it is this close to the line before it
T.LOOKAHEAD = 30 -- the arrow points at the route this far ahead (on floors: the corner rule, T.CornerTarget)
-- (outdoors, this far: a road's short jogs near the player didn't swing it 40 degrees off a run straight down the
-- road, the Barrens, 2026-11-05)
T.OPEN_LOOKAHEAD = 60
T.TOWARD_AHEAD = 350 -- "toward <place>": a named place near the route this far past the turn
T.TOWARD_RADIUS = 450
T.STAIRS_GAP = 6 -- yards: stairs this close after stairs the same way (a landing between) are one flight
-- (where the route has heights: a stretch this steep is stairs, a flight rising this much in all; as the map's
-- stairs icons, GPSFrame's STAIR_SLOPE and STAIR_RISE)
T.STAIR_SLOPE, T.STAIR_RISE = 0.2, 4
T.STAIRS_THEN_YD = 20 -- yards: a turn this soon after the stairs is said with them ("Stairs up, then turn left")
-- Going into a cave or a building and out again, and crossing a bridge (asked 2026-11-12 for 1.2.4: "consider say when
-- to enter a cave or cross a bridge or go into a building"; T.Places): a bridge said where one at least BRIDGE_MIN_YD long
-- starts (CITY_BRIDGE_MIN_YD in a capital: its narrow walkways), looked for every BRIDGE_STEP yards along the roads.
T.BRIDGE_MIN_YD = 8
T.CITY_BRIDGE_MIN_YD = 20
T.BRIDGE_STEP = 2

local atan2 = math.atan2 or math.atan

local function Dist(x1, y1, x2, y2)
  return math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)
end

-- The walk ahead, from the player to the next stop or dock: the route's first parts that
-- lead to stop 1 on the player's continent, up to a transport ride.
-- { pts = { x, y, ... }, kinds, cum, total, cont, ends = "stop" | "ride", ride, from, zs }
-- (zs: the points' heights where the route has them, a level with floors over floors; else false)
function T.Path(route)
  if not route or not route.parts or not route.parts[1] then return nil end
  local first = route.parts[1]
  -- (`fz`: each point's floor in a building or a capital, Router's: the stairs' way, up or down, T.Stairs)
  local path = { pts = {}, kinds = {}, cum = { 0 }, cont = first.cont, ends = "stop", zs = {}, fz = {} }
  local pts, kinds, cum, zs, fz = path.pts, path.kinds, path.cum, path.zs, path.fz
  for _, part in ipairs(route.parts) do
    if part.stop ~= first.stop then break end
    -- (a ride next ends the walk at it, whatever level it's drawn on: a flight from Undercity's flight master, down on
    -- the city's level, is drawn over the continent, and the arrow window said "Arrive at" the stop past the flight,
    -- not "Board the flight", 2026-10-06)
    if part.kinds[1] == (ns.Nav and ns.Nav.KIND_TRANSPORT or 2) then
      path.ends = "ride"
      break
    end
    if part.cont ~= first.cont then break end
    for i = 1, #part.pts, 2 do
      local x, y = part.pts[i], part.pts[i + 1]
      local n = #pts
      if n == 0 or math.abs(pts[n - 1] - x) > 0.01 or math.abs(pts[n] - y) > 0.01 then
        if n > 0 then
          cum[#cum + 1] = cum[#cum] + Dist(pts[n - 1], pts[n], x, y)
          kinds[#kinds + 1] = part.kinds[(i - 1) / 2] or part.kinds[1]
        end
        pts[n + 1], pts[n + 2] = x, y
        zs[#zs + 1] = part.zs and part.zs[(i + 1) / 2] or false
        fz[#fz + 1] = part.fz and part.fz[(i + 1) / 2] or false
      end
    end
  end
  if path.ends == "ride" then
    for _, leg in ipairs(route.legs or {}) do
      if leg.ride then
        path.ride, path.from = leg.ride, leg.from
        break
      end
    end
  end
  path.total = cum[#cum]
  return path
end

-- Point `s` yards along the path (clamped to its ends). By halving (cum only grows): a scan from the start each time
-- made the maneuvers of a long route take the square of its length, 22 ms for 670 points, worked out 6 times a
-- second for the arrow window and the map's panel (2026-10-06: 15% of a CPU core however zoomed in).
function T.PointAt(path, s)
  local pts, cum = path.pts, path.cum
  local n = #cum
  if s <= 0 or n < 2 then return pts[1], pts[2] end
  if cum[n] < s then return pts[#pts - 1], pts[#pts] end
  local lo, hi = 2, n -- (the first i >= 2 with cum[i] >= s)
  while lo < hi do
    local mid = math.floor((lo + hi) / 2)
    if cum[mid] >= s then hi = mid else lo = mid + 1 end
  end
  local i = lo
  local seg = cum[i] - cum[i - 1]
  local t = seg > 0 and (s - cum[i - 1]) / seg or 0
  return pts[2 * i - 3] + (pts[2 * i - 1] - pts[2 * i - 3]) * t, pts[2 * i - 2] + (pts[2 * i] - pts[2 * i - 2]) * t
end

-- Signed bend (degrees, + = left, as seen on a north-up map) at `s` along the path.
local function Bend(path, s)
  local ax, ay = T.PointAt(path, s - T.WINDOW)
  local bx, by = T.PointAt(path, s)
  local cx, cy = T.PointAt(path, s + T.WINDOW)
  local d1x, d1y, d2x, d2y = bx - ax, by - ay, cx - bx, cy - by
  if d1x * d1x + d1y * d1y < 1 or d2x * d2x + d2y * d2y < 1 then return 0 end
  -- X is north, Y is west: west of north is to the left
  local a1, a2 = atan2(d1y, d1x), atan2(d2y, d2x)
  local d = math.deg(a2 - a1)
  while d > 180 do d = d - 360 end
  while d < -180 do d = d + 360 end
  return d
end
T.Bend = Bend

-- A turn by its angle: "uturn", "sharp_left", "turn_right", "slight_left"... (T.WORDS has its sentences)
function T.TurnId(angle)
  local a, side = math.abs(angle), angle > 0 and "left" or "right"
  if a >= 160 then return "uturn" end
  if a >= 120 then return "sharp_" .. side end
  if a >= 60 then return "turn_" .. side end
  return "slight_" .. side
end

-- Every maneuver's sentences, whole (each language words them its own way): { as it is, said at it ("... now"), inside
-- "Continue straight, then ... in 30 yd" }. A turn's id, "+join" / "+leave" with the road joined or left at it.
T.WORDS = {
  uturn = { L["Make a U-turn"], L["Make a U-turn now"], L["make a U-turn"] },
  sharp_left = { L["Sharp left"], L["Sharp left now"], L["sharp left"] },
  sharp_right = { L["Sharp right"], L["Sharp right now"], L["sharp right"] },
  turn_left = { L["Turn left"], L["Turn left now"], L["turn left"] },
  turn_right = { L["Turn right"], L["Turn right now"], L["turn right"] },
  slight_left = { L["Slight left"], L["Slight left now"], L["slight left"] },
  slight_right = { L["Slight right"], L["Slight right now"], L["slight right"] },
  ["uturn+join"] = { L["Make a U-turn onto the road"], L["Make a U-turn onto the road now"], L["make a U-turn onto the road"] },
  ["sharp_left+join"] = { L["Sharp left onto the road"], L["Sharp left onto the road now"], L["sharp left onto the road"] },
  ["sharp_right+join"] = { L["Sharp right onto the road"], L["Sharp right onto the road now"], L["sharp right onto the road"] },
  ["turn_left+join"] = { L["Turn left onto the road"], L["Turn left onto the road now"], L["turn left onto the road"] },
  ["turn_right+join"] = { L["Turn right onto the road"], L["Turn right onto the road now"], L["turn right onto the road"] },
  ["slight_left+join"] = { L["Slight left onto the road"], L["Slight left onto the road now"], L["slight left onto the road"] },
  ["slight_right+join"] = { L["Slight right onto the road"], L["Slight right onto the road now"], L["slight right onto the road"] },
  ["uturn+leave"] = { L["Make a U-turn off the road"], L["Make a U-turn off the road now"], L["make a U-turn off the road"] },
  ["sharp_left+leave"] = { L["Sharp left off the road"], L["Sharp left off the road now"], L["sharp left off the road"] },
  ["sharp_right+leave"] = { L["Sharp right off the road"], L["Sharp right off the road now"], L["sharp right off the road"] },
  ["turn_left+leave"] = { L["Turn left off the road"], L["Turn left off the road now"], L["turn left off the road"] },
  ["turn_right+leave"] = { L["Turn right off the road"], L["Turn right off the road now"], L["turn right off the road"] },
  ["slight_left+leave"] = { L["Slight left off the road"], L["Slight left off the road now"], L["slight left off the road"] },
  ["slight_right+leave"] = { L["Slight right off the road"], L["Slight right off the road now"], L["slight right off the road"] },
  join = { L["Join the road"], L["Join the road now"], L["join the road"] },
  leave = { L["Leave the road"], L["Leave the road now"], L["leave the road"] },
  drop = { L["Jump down here"], L["Jump down here"], L["jump down"] },
  lift_up = { L["Take the lift up"], L["Take the lift up"], L["take the lift up"] },
  lift_down = { L["Take the lift down"], L["Take the lift down"], L["take the lift down"] },
  stairs_up = { L["Take the stairs up"], L["Take the stairs up"], L["take the stairs up"] },
  stairs_down = { L["Take the stairs down"], L["Take the stairs down"], L["take the stairs down"] },
  enter_cave = { L["Enter the cave"], L["Enter the cave"], L["enter the cave"] },
  leave_cave = { L["Leave the cave"], L["Leave the cave"], L["leave the cave"] },
  enter_building = { L["Go into the building"], L["Go into the building"], L["go into the building"] },
  leave_building = { L["Leave the building"], L["Leave the building"], L["leave the building"] },
  bridge = { L["Cross the bridge"], L["Cross the bridge"], L["cross the bridge"] },
}
-- (a maneuver's text, "now" text and mid-sentence text from its words' id)
local function Words(m, id)
  local w = T.WORDS[id]
  m.words, m.text, m.now, m.mid = id, w[1], w[2], w[3]
  return m
end
T.Words = Words

function T.TurnText(angle)
  return T.WORDS[T.TurnId(angle)][1]
end

-- Boarding a ride at the walk's end, by its kind: { as it is, inside "Continue straight, then ..." } (%s: where to)
T.BOARD = {
  flight = { L["Board the flight to %s"], L["board the flight to %s"] },
  zeppelin = { L["Board the zeppelin to %s"], L["board the zeppelin to %s"] },
  boat = { L["Board the boat to %s"], L["board the boat to %s"] },
  tram = { L["Board the tram to %s"], L["board the tram to %s"] },
  lift = { L["Board the lift to %s"], L["board the lift to %s"] },
  portal = { L["Board the portal to %s"], L["board the portal to %s"] },
  teleporter = { L["Take the teleporter to %s"], L["take the teleporter to %s"] },
}

-- The next maneuver as what to do now, then it: "Continue straight, then slight right in 13 yd"
-- ("Straight, then ..." with `short`); within NOW_YD of it, "Slight right now" (a turn, joining or
-- leaving the road), or as it is ("Arrive at ..."). `fmt(yards)` formats the distance (its color).
T.NOW_YD = 8
function T.NowText(m, fmt, short)
  local d = m.dist or 0
  if m.kind == "stairs" then -- ("Stairs up in 10 yd, then turn left"; on them, "Take the stairs up, then turn left")
    if d <= T.NOW_YD then
      if not m.after then return m.text end
      return Format(m.up and L["Take the stairs up, then %s"] or L["Take the stairs down, then %s"], m.after)
    end
    if not m.after then return Format(m.up and L["Stairs up in %s"] or L["Stairs down in %s"], fmt(d)) end
    return Format(m.up and L["Stairs up in %s, then %s"] or L["Stairs down in %s, then %s"], fmt(d), m.after)
  end
  if d <= T.NOW_YD then
    if m.kind == "turn" or m.kind == "join" or m.kind == "leave" then return m.now or (m.text .. " now") end
    return m.text
  end
  -- (a maneuver made here has its words in the middle of a sentence, `mid`; one made by hand, as the English)
  local what = m.mid or (m.kind == "drop" and "jump down" or (m.text:sub(1, 1):lower() .. m.text:sub(2)))
  if short then return Format(L["Straight, then %s in %s"], what, fmt(d)) end
  return Format(L["Continue straight, then %s in %s"], what, fmt(d))
end

local COMPASS = { "north", "north-west", "west", "south-west", "south", "south-east", "east", "north-east" }
-- Compass direction of a heading (X north, Y west).
function T.Compass(dx, dy)
  local a = math.deg(atan2(dy, dx)) -- 0 = north, 90 = west
  return COMPASS[math.floor(((a % 360) + 22.5) / 45) % 8 + 1]
end

-- A named place near the route past distance s (for "toward <place>").
local function Toward(path, s)
  local list = ns.Pois and ns.Pois[path.cont]
  if not list then return nil end
  local px, py = T.PointAt(path, s)
  local qx, qy = T.PointAt(path, math.min(path.total, s + T.TOWARD_AHEAD))
  if Dist(px, py, qx, qy) < 50 then return nil end
  local best, bestD
  for _, p in ipairs(list) do
    if p[1] == 2 or p[1] == 3 then
      local d = Dist(qx, qy, p[2], p[3])
      local ahead = (p[2] - px) * (qx - px) + (p[3] - py) * (qy - py) > 0
      if d <= T.TOWARD_RADIUS and ahead and (not bestD or d < bestD) then best, bestD = p, d end
    end
  end
  return best and ns.PoiName(best)
end

-- Stairs on the path, in order: { s0, s1, dir = 1 up | -1 down }, flights the same way with a landing
-- between them one. Where the route has heights (Undercity, a dungeon), by its slope; else a capital's
-- stairs and ramps between levels (Router.StairAt). `horizon`: only those starting within that many yards.
function T.Stairs(path, horizon)
  local R = ns.Router
  local out = {}
  if not (path and path.pts) then return out end
  local pts, cum, zs = path.pts, path.cum, path.zs or {}
  local stairAt = R and R.StairAt
  local last
  for j = 1, #cum - 1 do
    if horizon and cum[j] > horizon then break end
    local st, dz
    local z1, z2, len = zs[j], zs[j + 1], cum[j + 1] - cum[j]
    if z1 and z2 then
      dz = z2 - z1
      if len > 0 and math.abs(dz) / len >= T.STAIR_SLOPE then st = dz > 0 and 1 or -1 end
    elseif stairAt and path.kinds[j] == 0 then -- (a road's: stairs are roads)
      st = stairAt(path.cont, pts[2 * j - 1], pts[2 * j], pts[2 * j + 1], pts[2 * j + 2])
    end
    if st then
      -- (by heights, a landing between flights the same way; by the stairs roads (no heights), one flight however its
      -- pieces read: stairs over stairs can read the other way on a piece, Brill's inn's)
      if last and ((last.dir == st and cum[j] - last.s1 <= T.STAIRS_GAP) or (not z1 and cum[j] - last.s1 <= 0.01)) then
        last.s1, last.dz, last.j1 = cum[j + 1], last.dz and dz and last.dz + dz, j + 1
      else
        last = { s0 = cum[j], s1 = cum[j + 1], dir = st, dz = dz, j0 = j, j1 = j + 1 }
        out[#out + 1] = last
      end
    end
  end
  -- (a flight by the stairs roads: up or down as the route's floors go across it, where it has them (a building's, a
  -- capital's); its first piece's way on the map read "up" coming down Brill's inn's stairs over stairs, 2026-10-06)
  local fz = path.fz or {}
  for _, st in ipairs(out) do
    local f0, f1 = fz[st.j0], fz[st.j1]
    if not st.dz and f0 and f1 and math.abs(f1 - f0) >= 1 then st.dir = f1 > f0 and 1 or -1 end
    -- (and no flight where the floors across it are level: the way beside the stairs, at their top. 2026-11-17, the
    -- Wizard's Sanctum's portal: "Take the stairs up" in front of it, the walk to it 2 yd off the stairs' last turn)
    if not st.dz and f0 and f1 and math.abs(f1 - f0) < 1 then st.level = true end
  end
  -- (by heights: only a flight rising or falling STAIR_RISE in all, not a bump)
  local kept = {}
  for _, st in ipairs(out) do
    if not st.level and (not st.dz or math.abs(st.dz) >= T.STAIR_RISE) then kept[#kept + 1] = st end
  end
  return kept
end

-- Where the walk goes into a cave or a building and out again ("place": `enter`, `place` "cave" or "building"), and
-- where it starts across a bridge ("bridge", `stop` where it ends), in order: { dist, kind, words }. On the roads only
-- (Router.PlaceAt, Router.BridgeAt); `horizon` as T.Stairs'.
function T.Places(path, horizon)
  local R = ns.Router
  local out = {}
  if not (path and path.pts and R and R.PlaceAt) then return out end
  local pts, cum, kinds, cont = path.pts, path.cum, path.kinds, path.cont
  -- (each stretch of road by its middle: at a vertex a door's join and the inside's road meet; off the roads, as the
  -- road before. Where the walk starts is told by its first road, not said: a walk from down in a cave isn't "Enter")
  local was
  for j = 1, #cum - 1 do
    if horizon and cum[j] > horizon then break end
    local place = was
    if kinds[j] == 0 then
      local p = R.PlaceAt(cont, (pts[2 * j - 1] + pts[2 * j + 1]) / 2, (pts[2 * j] + pts[2 * j + 2]) / 2)
      if p ~= nil then place = p end
    end
    if was ~= nil and place ~= was then -- (straight from one into another: out of the one, into the other)
      if was then out[#out + 1] = Words({ dist = cum[j] - 0.01, kind = "place", place = was, enter = false }, "leave_" .. was) end
      if place then out[#out + 1] = Words({ dist = cum[j], kind = "place", place = place, enter = true }, "enter_" .. place) end
    end
    was = place
  end
  if R.BridgeAt then
    local run, runCity
    local function close(s1)
      if run and s1 - run >= (runCity and T.CITY_BRIDGE_MIN_YD or T.BRIDGE_MIN_YD) then
        out[#out + 1] = Words({ dist = run, stop = s1, kind = "bridge" }, "bridge")
      end
      run = nil
    end
    local total = horizon and math.min(path.total, horizon) or path.total
    local j = 1
    for s = 0, total, T.BRIDGE_STEP do
      while j < #cum - 1 and cum[j + 1] < s do j = j + 1 end
      local on = false
      if kinds[j] == 0 or kinds[j] == 1 then -- (on the roads, or walked: Thandol Span has no road over it)
        local ax, ay, bx, by = pts[2 * j - 1], pts[2 * j], pts[2 * j + 1], pts[2 * j + 2]
        local len = Dist(ax, ay, bx, by)
        if len > 0 then
          local x, y = T.PointAt(path, s)
          if kinds[j] == 0 then
            on = R.BridgeAt(cont, x, y, (bx - ax) / len, (by - ay) / len)
          else
            on = R.OnBridgeModel ~= nil and R.OnBridgeModel(cont, x, y)
          end
          if on and not run then -- (a capital's walkway, not a bridge model: a longer run wanted)
            run, runCity = s, not (R.OnBridgeModel and R.OnBridgeModel(cont, x, y))
          end
        end
      end
      if not on then close(s) end
    end
    close(total)
  end
  table.sort(out, function(a, b) return a.dist < b.dist end)
  return out
end

-- The maneuvers ahead, nearest first: { dist, kind, text, toward, angle }.
-- kind: "turn", "join" (onto the road), "leave" (off the road), "drop", "lift", "stairs" (up or down:
-- `short` "Stairs up", `after` the turn just after them), "place" (into a cave or a building, or out: T.Places),
-- "bridge", "board", "arrive".
-- stopLabel: how the next stop is named ("stop 1", a place name...). `horizon`: only the maneuvers within that many
-- yards (and the arrival or boarding at the end): what the arrow and the map's panel show is the next one or two.
function T.Maneuvers(path, stopLabel, horizon)
  local out = {}
  if not path or not path.total then return out end
  local pts, cum, kinds = path.pts, path.cum, path.kinds
  -- curves: runs of points bending the same way; a curve is one turn, by how much the
  -- direction changes from before it to after it, at its sharpest point
  local function heading(s1, s2)
    local ax, ay = T.PointAt(path, s1)
    local bx, by = T.PointAt(path, s2)
    return atan2(by - ay, bx - ax)
  end
  local R = ns.Router
  local group
  local function flush()
    if group then
      local W = T.WINDOW
      local a = math.deg(heading(group.last, group.last + W) - heading(group.first - W, group.first))
      while a > 180 do a = a - 360 end
      while a < -180 do a = a + 360 end
      -- like a car GPS: on roads, speak at junctions; road curves elsewhere only when sharp
      local onRoad, junction, js = false, false, nil
      for i = group.i0, group.i1 do
        if kinds[i - 1] == 0 or kinds[i] == 0 then onRoad = true end
        if not junction and R and R.JunctionAt and R.JunctionAt(path.cont, pts[2 * i - 1], pts[2 * i]) then
          junction, js = true, cum[i]
        end
      end
      local need = not onRoad and T.MIN_ANGLE or junction and T.JUNCTION_ANGLE or T.ROAD_BEND_ANGLE
      if math.abs(a) >= need then
        local s = js or group.s
        out[#out + 1] = Words({ dist = s, kind = "turn", angle = a, toward = Toward(path, s), turn = T.TurnId(a) },
          T.TurnId(a))
      end
      group = nil
    end
  end
  local DROP = R and R.KIND_DROP or 4
  local DOWN, UP = R and R.KIND_LIFT_DOWN or 5, R and R.KIND_LIFT_UP or 6
  local function roadish(k) return k == 0 or k == DROP or k == DOWN or k == UP end
  for i = 2, #cum - 1 do
    local s = cum[i]
    if horizon and s > horizon then break end
    -- a drop off a ledge starts here (said however near it is)
    if kinds[i] == DROP and kinds[i - 1] ~= DROP then
      out[#out + 1] = Words({ dist = s, kind = "drop" }, "drop")
    end
    -- a lift (Thunder Bluff's): taken here, up or down
    if (kinds[i] == UP or kinds[i] == DOWN) and kinds[i - 1] ~= kinds[i] then
      out[#out + 1] = Words({ dist = s, kind = "lift" }, kinds[i] == UP and "lift_up" or "lift_down")
    end
    if s >= T.MIN_AHEAD then
      local a = Bend(path, s)
      if math.abs(a) >= T.BEND_START then
        if group and s - group.last <= T.WINDOW and (a > 0) == (group.sign > 0) then
          if math.abs(a) > group.peak then group.peak, group.s = math.abs(a), s end
          group.last, group.i1 = s, i
        else
          flush()
          group = { s = s, first = s, last = s, peak = math.abs(a), sign = a, i0 = i, i1 = i }
        end
      end
      -- road transitions at this vertex
      local k1, k2 = kinds[i - 1], kinds[i]
      if roadish(k1) ~= roadish(k2) then
        out[#out + 1] = Words({ dist = s, kind = k2 == 0 and "join" or "leave" }, k2 == 0 and "join" or "leave")
      end
    end
  end
  flush()
  -- stairs: said where they start (however near), and the turns on them not (a spiral's)
  local stairs = T.Stairs(path, horizon)
  if #stairs > 0 then
    local kept = {}
    for _, m in ipairs(out) do
      local on = false
      for _, st in ipairs(stairs) do
        if m.kind == "turn" and m.dist >= st.s0 - 3 and m.dist < st.s1 - 1 then on = true break end
      end
      if not on then kept[#kept + 1] = m end
    end
    out = kept
    for _, st in ipairs(stairs) do
      local up = st.dir > 0
      out[#out + 1] = Words({ dist = st.s0, stop = st.s1, kind = "stairs", up = up }, up and "stairs_up" or "stairs_down")
    end
  end
  for _, m in ipairs(T.Places(path, horizon)) do out[#out + 1] = m end
  table.sort(out, function(a, b) return a.dist < b.dist end)
  -- a jog: turns close together that net out and bring the route back onto the line it
  -- was on (out and back) are no turn at all: straight on
  local skip = {}
  local i = 1
  while i <= #out do
    if out[i].kind == "turn" then
      local run, last = { i }, out[i].dist
      for j = i + 1, #out do
        if out[j].dist - last > T.JOG_YD then break end
        if out[j].kind == "turn" then
          run[#run + 1] = j
          last = out[j].dist
        end
      end
      do
        -- (the heading before the run and after it: a jog comes back to the same one, even when
        -- its gentler bends were too slight to be turns and one sharp one is left)
        local s0, s1 = out[run[1]].dist, out[run[#run]].dist
        local p1x, p1y = T.PointAt(path, math.max(0, s0 - 2 * T.WINDOW))
        local p2x, p2y = T.PointAt(path, math.max(0, s0 - T.WINDOW))
        local q1x, q1y = T.PointAt(path, math.min(path.total, s1 + T.WINDOW))
        local q2x, q2y = T.PointAt(path, math.min(path.total, s1 + 2 * T.WINDOW))
        local net = 180
        if (p2x - p1x) ^ 2 + (p2y - p1y) ^ 2 >= 1 and (q2x - q1x) ^ 2 + (q2y - q1y) ^ 2 >= 1 then
          net = math.deg(atan2(q2y - q1y, q2x - q1x) - atan2(p2y - p1y, p2x - p1x))
          while net > 180 do net = net - 360 end
          while net < -180 do net = net + 360 end
        end
        -- (how far after the run the route is from the line it was on before it)
        local len = Dist(p1x, p1y, p2x, p2y)
        local off = len > 0 and math.abs((p2x - p1x) * (q1y - p1y) - (p2y - p1y) * (q1x - p1x)) / len or math.huge
        -- (not on hilly ground: winding there may be the way up, and worth saying)
        local hilly = false
        local P = ns.Passability
        if P and P.Hilly then
          for s = math.max(0, s0 - T.WINDOW), math.min(path.total, s1 + T.WINDOW), 10 do
            local hx, hy = T.PointAt(path, s)
            if P.Hilly(path.cont, hx, hy) then hilly = true break end
          end
        end
        if math.abs(net) < T.MIN_ANGLE and off <= T.JOG_OFFSET and not hilly then
          for _, j in ipairs(run) do skip[j] = true end
        end
      end
      i = run[#run] + 1
    else
      i = i + 1
    end
  end
  local kept = {}
  for j, m in ipairs(out) do
    if not skip[j] then kept[#kept + 1] = m end
  end
  out = kept
  local merged = {}
  for _, m in ipairs(out) do
    local prev = merged[#merged]
    if m.dist > path.total - T.END_QUIET and m.kind ~= "stairs" and not (m.kind == "place" and m.enter) then
      -- arriving: nothing more to say (but stairs: a trainer upstairs is up them, Brill's inn, 2026-10-06; nor going
      -- into the building or the cave the stop is in)
    elseif prev and m.dist - prev.dist < T.HOP_YD and (m.kind == "join" or m.kind == "leave")
        and (prev.road == "join" or prev.road == "leave") and prev.road ~= m.kind then
      -- a short hop onto a road and off again (or off and back on): not worth an instruction
      if prev.kind == "turn" then
        Words(prev, prev.turn) -- keep the turn itself
        prev.road, prev.merged = nil, nil
      else
        merged[#merged] = nil
      end
    elseif prev and m.dist - prev.dist < 15 and not prev.merged and ((prev.kind == "turn") ~= (m.kind == "turn"))
        and (prev.road or m.kind == "join" or m.kind == "leave") then
      -- a turn right where the route joins/leaves a road reads as one instruction
      local turn, road = prev.kind == "turn" and prev or m, prev.kind == "turn" and m or prev
      local id = turn.turn .. "+" .. road.kind
      prev.road = road.kind
      prev.kind, prev.angle, prev.toward, prev.turn, prev.merged = "turn", turn.angle, turn.toward, turn.turn, true
      Words(prev, id)
    else
      if m.kind == "join" or m.kind == "leave" then m.road = m.kind end
      merged[#merged + 1] = m
    end
  end
  -- (a turn just after stairs: said with them)
  for k, m in ipairs(merged) do
    local nxt = merged[k + 1]
    if m.kind == "stairs" and nxt and nxt.kind == "turn" and nxt.dist - m.stop <= T.STAIRS_THEN_YD then
      m.after = nxt.mid or (nxt.text:sub(1, 1):lower() .. nxt.text:sub(2))
    end
  end
  if path.ends == "ride" and path.ride then
    local t = path.ride
    local to = ns.RideEndName(t, path.from == 1 and 2 or 1)
    local board = T.BOARD[t[8]]
    local m = { dist = path.total, kind = "board" }
    if t.use then
      m.text, m.mid = Format(L["Use %s (to %s)"], t[8], t[10]), Format(L["use %s (to %s)"], t[8], t[10])
    elseif board then
      m.text, m.mid = Format(board[1], to), Format(board[2], to)
    else -- (a kind of ride with no words of its own: its kind as it is)
      m.text, m.mid = Format(L["Board the %s to %s"], t[8], to), Format(L["board the %s to %s"], t[8], to)
    end
    merged[#merged + 1] = m
  elseif stopLabel then
    merged[#merged + 1] = { dist = path.total, kind = "arrive", text = Format(L["Arrive at %s"], stopLabel),
      mid = Format(L["arrive at %s"], stopLabel) }
  else
    merged[#merged + 1] = { dist = path.total, kind = "arrive", text = L["Arrive at your destination"],
      mid = L["arrive at your destination"] }
  end
  return merged
end

-- The walk ahead and its maneuvers as the arrow window and the map's panel show them (the next one or two): within
-- HORIZON_YD, worked out once for the route as it is now (a new route, or trimmed as the player goes on) and stop
-- label, both reading the same (asked 2026-10-06: the arrow window's 4 a second and the panel's 2, each over the whole
-- route, cost as much zoomed in as out).
T.HORIZON_YD = 1500
-- Worked out once for both: the arrow's and the panel's labels differ (a stop's number, its name), and only the
-- arrival's words take it (each label's list a copy with its own; heavy stuttering running through Orgrimmar,
-- 2026-11-13: worked out twice at every trim).
local aheadKept -- { route, its first part, path, maneuvers (by the first label asked), label, [label] = maneuvers }
function T.Ahead(route, stopLabel)
  if not route then return nil, {} end
  local key = stopLabel or ""
  local first = route.parts and route.parts[1]
  if not (aheadKept and aheadKept[1] == route and aheadKept[2] == first) then
    local path = T.Path(route)
    local ms = T.Maneuvers(path, stopLabel, T.HORIZON_YD)
    aheadKept = { route, first, path, ms, key, labels = { [key] = ms } }
    T.aheadRuns = (T.aheadRuns or 0) + 1 -- (the tests count them)
    return path, ms
  end
  local ms = aheadKept.labels[key]
  if not ms then
    local base = aheadKept[4]
    ms = {}
    for i, m in ipairs(base) do ms[i] = m end
    local last = ms[#ms]
    if last and last.kind == "arrive" then
      local m = {}
      for k, v in pairs(last) do m[k] = v end
      if stopLabel then
        m.text, m.mid = Format(L["Arrive at %s"], stopLabel), Format(L["arrive at %s"], stopLabel)
      else
        m.text, m.mid = L["Arrive at your destination"], L["arrive at your destination"]
      end
      ms[#ms] = m
    end
    aheadKept.labels[key] = ms
  end
  return aheadKept[3], ms
end

-- Where the direction arrow points: the route OPEN_LOOKAHEAD yards ahead (or its end). Indoors on a building's or a city's
-- floors (the route's points with their floor, `fz`, within LOOKAHEAD; T.Indoors), no further than the route can be seen from the player
-- (`px`, `py`): every corner on the way within CORNER_YD of the line to it, so it never points through a wall at a
-- corner. (A test walk, 2026-10-07: from Brill's square to the Mage trainer the arrow aimed 30 yd ahead, past
-- Gallows' End's doorway corner, 50 degrees off, through the inner wall, and the character walked into it.)
-- Seen from the route where the player is along it, not the player's own spot, with CORNER_SLACK of the way there
-- allowed too: a player a couple of yards beside the route saw no corner from there and the arrow aimed 4 yd ahead,
-- swinging 25 degrees to the route on a run the right way (Orgrimmar, 2026-11-05).
T.CORNER_YD = 1.5
T.CORNER_SLACK = 0.1
T.CORNER_MIN_YD = 4 -- (never nearer than this: the arrow steady over the route's small kinks)
T.CORNER_STEP = 1
function T.OnFloors(path)
  local fz, cum = path.fz, path.cum
  if not fz then return false end
  for i = 1, #cum do
    if cum[i] > T.LOOKAHEAD then break end
    if fz[i] then return true end
  end
  return false
end
-- (how far along the path the player at (px, py) is: the nearest point on its first LOOKAHEAD * 2 yards)
function T.AlongNear(path, px, py)
  local pts, cum = path.pts, path.cum
  local best, bestD = 0, math.huge
  for i = 1, #cum - 1 do
    if cum[i] > T.LOOKAHEAD * 2 then break end
    local ax, ay, bx, by = pts[2 * i - 1], pts[2 * i], pts[2 * i + 1], pts[2 * i + 2]
    local vx, vy = bx - ax, by - ay
    local L2 = vx * vx + vy * vy
    local t = L2 > 0 and math.max(0, math.min(1, ((px - ax) * vx + (py - ay) * vy) / L2)) or 0
    local d = (ax + vx * t - px) ^ 2 + (ay + vy * t - py) ^ 2
    if d < bestD then best, bestD = cum[i] + (cum[i + 1] - cum[i]) * t, d end
  end
  return best
end
function T.CornerTarget(path, px, py, cap)
  local pts, cum = path.pts, path.cum
  local s0 = T.AlongNear(path, px, py)
  local ox, oy = T.PointAt(path, s0)
  local limit = math.min(s0 + T.LOOKAHEAD, path.total, cap or math.huge)
  local first = math.min(s0 + T.CORNER_MIN_YD, path.total)
  local best = first
  local s = first
  while s <= limit do
    local tx, ty = T.PointAt(path, s)
    local vx, vy = tx - ox, ty - oy
    local L2 = vx * vx + vy * vy
    local within = math.max(T.CORNER_YD, T.CORNER_SLACK * math.sqrt(L2))
    local seen = true
    for i = 2, #cum do -- (the corners passed on the way there)
      if cum[i] >= s then break end
      if cum[i] > s0 then
        local qx, qy = pts[2 * i - 1], pts[2 * i]
        local t = L2 > 0 and math.max(0, math.min(1, ((qx - ox) * vx + (qy - oy) * vy) / L2)) or 0
        if (ox + vx * t - qx) ^ 2 + (oy + vy * t - qy) ^ 2 > within * within then
          seen = false
          break
        end
      end
    end
    if not seen then break end
    best = s
    if s >= limit then break end
    s = math.min(s + T.CORNER_STEP, limit)
  end
  return T.PointAt(path, best)
end
-- (only where the game says the player is indoors: since the land's roads went 3D every route has its floors, and out on
-- Mulgore by Thunder Bluff's lifts, or in Orgrimmar's open streets, the corner rule aimed at the road's small kinks a
-- few yards off — beside the road, at the join behind them, the arrow red, 2026-11-05; on 496 spots beside routes
-- there it was more than 45 degrees off at 292, the outdoor aim at 32)
function T.Indoors()
  local N = ns.Nav
  if N and N.Indoors then return N.Indoors() == true end
  if not IsIndoors then return false end
  local ok, v = pcall(IsIndoors)
  return ok and not (ns.IsSecret and ns.IsSecret(v)) and v == true
end
-- Stairs ahead (asked 2026-11-15: "if there are stairs to be taken the arrow doesn't look past that until reached"): the
-- arrow aims no further than the near end of the next flight (T.Stairs) until the player is within STAIR_REACHED_YD of
-- it, then no further than its far end, until past it. Nil: no stairs in the way. `sp`: the player along the path.
T.STAIR_REACHED_YD = 3
T.STAIR_CAP_HORIZON = 200 -- (the flights looked for this far along a path; worked out once a path)
function T.StairCap(path, sp)
  local fl = path.stairFlights
  if fl == nil then
    fl = T.Stairs(path, T.STAIR_CAP_HORIZON)
    path.stairFlights = fl
  end
  for _, f in ipairs(fl) do
    if f.s1 > sp + T.STAIR_REACHED_YD then
      if f.s0 > sp + T.STAIR_REACHED_YD then return f.s0 end
      return f.s1
    end
  end
  return nil
end
function T.Target(path, px, py)
  if not path or not path.total then return nil end
  local sp = px and py and T.AlongNear(path, px, py) or 0
  local cap = T.StairCap(path, sp)
  if px and py and T.OnFloors(path) and T.Indoors() then return T.CornerTarget(path, px, py, cap) end
  local ahead = T.OPEN_LOOKAHEAD
  if cap and (cap < ahead * 0.6 or (path.total <= ahead and cap < path.total)) then return T.PointAt(path, cap) end -- (the stairs' end, not past it)
  if path.total <= ahead then return T.PointAt(path, path.total) end
  -- (averaged over the stretch around it: a kink there doesn't swing the arrow)
  local sx, sy, n = 0, 0, 0
  for s = ahead * 0.6, math.min(ahead * 1.4, path.total, cap or math.huge), ahead * 0.2 do
    local x, y = T.PointAt(path, s)
    sx, sy, n = sx + x, sy + y, n + 1
  end
  return sx / n, sy / n
end

-- The arrow's rotation for a player at (px, py) facing `facing` looking at (tx, ty):
-- 0 = straight ahead, positive = to the left (as Texture:SetRotation turns).
function T.RelativeAngle(px, py, facing, tx, ty)
  local a = atan2(ty - py, tx - px) - (facing or 0)
  while a > math.pi do a = a - 2 * math.pi end
  while a < -math.pi do a = a + 2 * math.pi end
  return a
end
