-- Routing over the road network (Data/Roads.lua). Pure Lua, unit-tested with lupa.
--
-- Road mode (default): walk to a nearby road, follow roads, leave the road at the
-- point closest to the destination. Straight only when that is shorter than just
-- getting on and off the road.
-- Offroad mode ("riskier but faster"): straight across open ground when the terrain
-- allows (Passability.lua); where it doesn't, straight legs to/from the roads that get
-- through (passes, bridges) and roads in between.
local _, ns = ...

local R = {}
ns.Router = R
-- (read only, never written: `ipairs(t[k] or EMPTY)` in the long loops of the background work, not a new table each
-- time; issue #657: that garbage, a table a bucket a segment, made the collector's 15+ ms steps)
local EMPTY = {}

R.OFFROAD_PENALTY = 1.25 -- road mode: off-road yards cost this much more than road yards
-- Options > Routing's Road tolerance (asked 2026-11-04: `roadTolerance`, ROAD_TOLERANCE_MIN to MAX, 0 the default): a
-- road-keeping factor (OFFROAD_PENALTY, LEAVE_ROAD_FACTOR, ROAD_DIRECT_PENALTY) with its extra over 1 scaled: below 0
-- up to 5 times as much (the roads kept more), above 0 less, none at the top (a yard off the roads costs one on them:
-- the straight way over open ground wins whenever it's shorter). At 0, exactly the factor (routes as before).
R.ROAD_TOLERANCE_MIN, R.ROAD_TOLERANCE_MAX = -10, 10
function R.RoadFactor(f)
  local st = ns.settings and ns.settings.gps
  local t = st and tonumber(st.roadTolerance) or 0
  if t == 0 then return f end
  t = math.max(R.ROAD_TOLERANCE_MIN, math.min(R.ROAD_TOLERANCE_MAX, t))
  local s = t > 0 and 1 - t / R.ROAD_TOLERANCE_MAX or 1 + 4 * t / R.ROAD_TOLERANCE_MIN
  return 1 + (f - 1) * s
end
R.KIND_ROAD, R.KIND_OFFROAD = 0, 1
R.KIND_DROP = 4 -- off a ledge onto the floor below (Nav's own kinds are 2 and 3)
-- a lift (Thunder Bluff's: a road from its top to its foot, Data/Capitals.lua's source 5, its length
-- the wait and the ride), down it or up it: "Take the lift up" (Turns), as Undercity's lifts are rides
R.SOURCE_LIFT, R.KIND_LIFT_DOWN, R.KIND_LIFT_UP = 5, 5, 6
-- Up or down a lift road `ei` of graph `g`, taken along it (`forward`: from its first node to its second) or back: by its
-- ends' heights when both are known and apart (a lift drawn and edited: its Foot and Top, Edit Road's Flip Lift swaps
-- them); else as the data's lifts are laid, from the top to the foot (forward: down). (Kooki3z 2026-11-20: a lift drawn
-- from its foot up said "Take the lift down": the edit's heights rise along it, the old rule took its start for the top.)
R.LIFT_APART_Z = 2
function R.LiftKind(g, ei, forward)
  local e = g.e[ei]
  local hz = g.z or g.nz
  local za, zb = hz and hz[e[1]], hz and hz[e[2]]
  if za and zb and math.abs(za - zb) >= R.LIFT_APART_Z then
    local up = (zb > za) == forward
    return up and R.KIND_LIFT_UP or R.KIND_LIFT_DOWN
  end
  -- (the player's own lift with no heights, drawn or recorded: from the end it starts at, its foot, as Edit Road's Foot
  -- is its first point; Flip Lift turns it round. The data's lifts are laid from the top.)
  if g.kind and g.kind[ei] == "lift" then return forward and R.KIND_LIFT_UP or R.KIND_LIFT_DOWN end
  return forward and R.KIND_LIFT_DOWN or R.KIND_LIFT_UP
end
R.DROP_COST = 30 -- yards a drop counts extra: taken only when it saves real distance
R.OFFROAD_LINKS = 24 -- offroad mode: straight links tried from start/destination to road nodes
R.OFFROAD_LINK_MAX = 3000 -- yards
R.OFFROAD_TIE = 1.02 -- offroad mode: open ground costs a hair more, so roads win ties
R.BLOCKED_PENALTY = 12 -- a leg the terrain data calls blocked, when nothing better exists
R.WALLS_CUT_ROADS = false -- (BuildGraph: walls pass roads through since 2026-11-15)
R.WALL_PENALTY = 200 -- ... through a wall drawn with the road tools (only when there's no other way at all)
-- ... up or down a cliff by the map's ground (Passability.CliffAlong), the same: a fall no one survives isn't a shortcut
-- (Kooki3z 2026-11-20, Freewind Post: "not a safe path down")
R.CLIFF_PENALTY = 200
R.CLIFF_STOP_YD = 100 -- (a stop only reached up or down a cliff this near it: no way, RouteOne's `cliff`)
-- A hop: a leg onto or off the roads, or a link between road pieces, straight over ground the terrain or a wall blocks
-- with no walk round it found (searched, none). Asked 2026-11-14 (Loch Modan, a route to Stonesplinter Valley hopped
-- the cliffs from the Maker's Terrace's road): "If there is a road that would continue the path and its reachable
-- based on open ground and no wall blocks it then make the dotted line connection but no wall hopping allowed." A route
-- with one is worked out again (`hopRedo`, up to HOP_REDOS deep): each hop costing HOP_COST yards more, so any way
-- without one wins however long, every candidate leg walked, and from an end whose every candidate is a hop (or on
-- roads a hop's link cut off), more and further roads tried: of NearestEdgesAll's HOP_WIDE_KEEP nearest, up to
-- HOP_WIDE_TRIES more HOP_WIDE_SPACING apart. Taken with fewer hops; with none fewer the route stays as it was (the
-- route still exists).
R.HOP_COST = 100000
R.HOP_REDOS = 3
R.HOP_WIDE_TRIES, R.HOP_WIDE_KEEP, R.HOP_WIDE_SPACING = 16, 96, 100
R.HOSTILE_FACTOR = 20 -- a yard within reach of the other faction's guards (Data/Hostile.lua) costs this many
R.HOSTILE_STEP = 5 -- yards between the points checked along a leg
-- (asked 2026-11-16: enemy areas are the NPCs that would flag a player for PvP; the guards among them as above, the
-- rest, quest givers, vendors, flight masters, a dig site's workers, light: Data/Hostile.lua's `a`/`h`, a small reach
-- at this many a yard: a route bends round them when that's cheap, never swims or goes far round one. Not towns, not
-- in the warnings or drawn red)
R.HOSTILE_LIGHT_FACTOR = 3
R.HOSTILE_LIGHT = { A = "a", H = "h" }
-- (nor the light ones this near a walk's start or end: a stop is often one of them, a trainer up in a town hall, and
-- the walk to him kept off the road short of him; the towns a route starts or ends in aren't paid for either)
R.LIGHT_END_YD = 40
local lightEnds = setmetatable({}, { __mode = "k" }) -- [coroutine or false] = { sx, sy, tx, ty }: the search's ends
function R.SetLightEnds(sx, sy, tx, ty)
  lightEnds[coroutine.running() or false] = sx and { sx, sy, tx, ty } or nil
end
local function NearLightEnd(x, y)
  local e = lightEnds[coroutine.running() or false]
  if not e then return false end
  local d2 = R.LIGHT_END_YD * R.LIGHT_END_YD
  return (x - e[1]) ^ 2 + (y - e[2]) ^ 2 <= d2 or (x - e[3]) ^ 2 + (y - e[4]) ^ 2 <= d2
end
R.NearLightEnd = NearLightEnd
R.CITY_BLOCKED_PENALTY = 200 -- the same in a city (its grid's walls are real walls)
R.ENTRY_CANDIDATES = 8 -- road edges tried for getting on and off the road network
R.ENTRY_SLACK = 400 -- yards: candidates up to this much farther than the nearest road
R.ENTRY_QUARTERS = true -- ... and the nearest in each quarter round the spot none of those is in (RouteOne)
-- (asked 2026-11-14) A route ENTRY_SIDES_DETOUR times the straight line or longer: worked out again with, at the stop,
-- the nearest road within ENTRY_SLACK in each quarter round it too (R.EntrySidesAgain), and taken when shorter
R.ENTRY_SIDES = true
R.ENTRY_SIDES_DETOUR = 1.5
R.ENTRY_SIDES_YD = 100 -- ... when the nearest road is this far or more (off in the wilds: in a city, the roads near do)
R.ENTRY_SIDES_OPEN = true -- ... only one whose straight leg to the stop is open ground (not walked round: blocked, it
-- was priced as a jump, BLOCKED_PENALTY, and beat Orgrimmar's way out to Lake Mennar, a city leg at its own price)
R.ON_ROAD_YD = 8 -- a straight leg this close to a road is drawn (and counted) as road
R.ON_ROAD_MIN = 25 -- yards: shorter stretches along a road stay off-road
-- On a road already (within ON_ROAD_YD): a leg off it across country onto another road costs this per
-- yard, so a shortcut is taken only when it saves a fair bit (riding Mulgore's road, a shortcut over the
-- fields and the road swapped every few seconds: a video, 2026-09-30)
R.LEAVE_ROAD_FACTOR = 1.4
R.NODE_LINKS = 8 -- offroad mode: straight shortcuts from each road node, one per direction
R.NODE_LINK_MAX = 1500 -- yards
R.LAYER_Z = 5 -- a dungeon's floors (roads with heights): a road this far above or below is another floor
R.LAYER_LEG_FREE, R.LAYER_LEG_FACTOR = 3, 2 -- ...: a leg onto or off the roads, past this many yards, costs this per yard
-- (and in a building with its inside (Data/Indoors.lua), to or from a spot with a height: its roads reach its places,
-- spurs; a leg across its rooms went through their walls, 2026-10-06)
R.INSIDE_LEG_FREE, R.INSIDE_LEG_FACTOR = 3, 4
R.LAYER_VOID_YD = 2 -- ...: a leg over more than this with no floor at any height (a canal) isn't one

-- Yards of the line (x1, y1, z1)-(x2, y2, z2) (the game's heights, at its ends) through walls or
-- over gaps on its own floor in an underground city, by its floor heights (the top floor per
-- cell): about the line's height there, a closed cell of its grid is a wall on it; well under it
-- (the top floor there is lower), there's no floor at its height at all, a gap to fall down;
-- well above it, a walkway over it, the grid tells nothing about the line's floor (0 there).
R.WALL_Z = 4
function R.WallYards(cont, x1, y1, z1, x2, y2, z2)
  local H = ns.Nav and ns.Nav.CityHeight
  local l = ns.CityLevels and ns.CityLevels[cont]
  local P = ns.Passability
  if not (H and l and l.zoff and z1 and z2 and P and P.IsOpen) then return 0 end
  local d = math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)
  local n = math.max(1, math.ceil(d))
  local wall = 0
  for i = 1, n - 1 do
    local t = i / n
    local x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
    local h, z = H(cont, x, y), z1 + (z2 - z1) * t - l.zoff
    if not h or h < z - R.WALL_Z or (math.abs(h - z) <= R.WALL_Z and not P.IsOpen(cont, x, y)) then wall = wall + d / n end
  end
  return wall
end

-- Yards of the line (x1, y1)-(x2, y2) over no floor at any height: an underground city's levels,
-- where its floor heights (the top floor per cell) have none (a canal's water, a pit).
function R.VoidYards(cont, x1, y1, x2, y2)
  local H = ns.Nav and ns.Nav.CityHeight
  if not (H and ns.CityHeights and ns.CityHeights[cont]) then return 0 end
  local d = math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)
  local n = math.max(1, math.ceil(d))
  local void = 0
  for i = 1, n - 1 do
    local t = i / n
    if not H(cont, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t) then void = void + d / n end
  end
  return void
end
R.NODE_LINK_TRIES = 3 -- ... the nearest this many nodes tried in each direction (past rock, give that one up)
R.NODE_LINK_MS = 12 -- ... worked out for this long per route calculation, the rest in the background (a long
-- route's search reaches thousands of nodes: done at once, the game froze)
R.OFFROAD_WALK_AROUND = 3000 -- yards: offroad trips up to this long may walk around obstacles
-- (and up to DETOUR_WALK_MAX when the roads go DETOUR_WALK_FACTOR times as far as the line: from Beggar's Haunt's door
-- to Turner's Logging Camp, 3,016 yd apart, the roads went 12.4k yd and the walk over the land 4.2k; 75 yd nearer it
-- was walked; the overnight trip sweep, 2026-10-07)
R.DETOUR_WALK_MAX, R.DETOUR_WALK_FACTOR = 8000, 2.5
R.OFFROAD_ALONG_STEP = 50 -- offroad mode: points this far apart along nearby roads, to join or leave them
R.OFFROAD_ALONG_MAX = 700 -- ... within this many yards of the start or the destination
R.JOIN_ALONG_MAX = 200 -- road mode: the same, onto (or off) the roads within this many yards, over open ground
R.DIRECT_SHORT = 400 -- road mode: a straight walk there up to this long weighs like a walk onto the roads
R.JOIN_WALK_TRIES = 3 -- ... and the few best of them blocked in a straight line: walked around what's in the way
R.WALK_AROUND_CANDIDATES = 3 -- only the nearest few get-on/get-off legs search the terrain grid
-- Road mode: walking straight there (around obstacles) instead, off the roads the whole way,
-- counts this much per yard; so the roads are kept unless they're about twice as long, or
-- only reached across blocked ground. Trips up to OFFROAD_WALK_AROUND yards.
R.ROAD_DIRECT_PENALTY = 2
local NODE_BUCKET = 500

local graphs = {}

R.TRACK_SNAP = 25 -- yards: a drawn road's end joins an existing road this close
R.TRACK_SNAP_CITY = 8 -- ... in a city down below (levels over each other)
-- ... and a bridge's, a floor's or a lift's (an edited road's kind: R.RAISED_KINDS, "lift") only this close, either way:
-- its own ends, and another road's end onto it (Kooki3z 2026-11-20, Freewind Post's two rope bridges: their ends 16 yd
-- apart were joined, and a bridge's end at a lift's tower to the other tower's road across the gap, "why are the ends of
-- the bridges being connected? I didn't do this")
R.TRACK_SNAP_RAISED = 4
R.TRACK_REMOVE_YD = 12 -- an erased ("false road") track removes road this close to it
-- A drawn road is truth: where it runs along an existing road (this close, about parallel,
-- for a while) it replaces that stretch, and the road's cut ends join it. Where it crosses
-- or touches a road it's joined there (a junction); its ends join a road within TRACK_SNAP.
R.TRACK_OVERLAP = 12 -- yards
R.TRACK_OVERLAP_CITY = 4
R.TRACK_ALONG_COS = 0.866 -- about parallel: within 30 degrees
R.TRACK_ALONG_MIN = 15 -- yards: shorter stretches along a road (not at its ends) don't replace it
R.TRACK_ALONG_MIN_CITY = 4
R.TRACK_CROSS = 3 -- yards: a drawn road this close to a road it isn't along crosses it
R.TRACK_CROSS_CITY = 1.5
R.TRACK_STUB = 15 -- yards: a cut road's dead-end stub shorter than this goes
R.TRACK_REACH = 50 -- yards: the furthest from a drawn road that merging it touches (TRACK_SNAP and more)
-- yards: on a continent, a track drawn or recorded with its heights is on the floor of a building's or capital's road
-- this near its height (not LAYER_Z: issue #65, Ironforge's First Aid landing 3.6 yd over the ground floor was taken
-- for it, and replaced its road)
R.TRACK_FLOOR_Z = 3
-- yards: a drawn or recorded road with no heights (none picked while it was drawn or walked) on a continent takes them
-- from the roads with floors (a capital's, a building's) its ends join within this: rising evenly from one end's to the
-- other's, flat at the one end's height with only one (R.RampHeights; asked 2026-11-17, "can the difference be assumed
-- to gradually increase over that drawn distance rather than flat", with Stormwind's bank: a walk recorded to it with
-- no floor picked was on no floor, and the route took the city road at the counter's height and a 45 yd line instead)
R.RAMP_END_YD = 12
-- yards: a piece's end this near another piece's end of the same walk (one time: a recorded walk's pieces) joins only
-- that walk there, never another road within TRACK_SNAP (issue #65: each piece's end snapped onto the piece before's
-- far end, and the stairs between them were lost). Only where they meet (a recorded walk's pieces share their point):
-- Darnassus's spiral's stairs start 0.5 yd off the piece before's end, and joined there the route from partway down
-- climbed back to its top first
R.TRACK_WALK_JOIN = 0.1
-- A drawn or recorded road's kind, set afterwards with the road tools' Edit Road (asked 2026-11-18 for 1.3.10: "pick the
-- floor level that would be on", a bridge in Thunder Bluff and a road under it): saved as the track's `kind`, with its
-- heights (`zs`) and a stairs stretch on part of it (`stairs` = { first point, last point }). An edit is a new track that
-- `replaces` the one edited (its time, `rpart` a recorded walk's piece): routes leave the old one out at once, and the
-- road watcher takes the new one in its place.
-- (and a ramp: a slope with its heights, set with Edit Road's Set Heights, 1.3.10 issue #685; walked as a road)
R.TRACK_KINDS = { "ground", "floor", "bridge", "stairs", "lift", "ramp" }
-- (a bridge's or a floor's roads over the land: never joined to the roads under them but at their own ends, and no gap
-- link onto them from below)
R.RAISED_KINDS = { bridge = true, floor = true }
-- Jumping down off a raised road onto a road under it with a known height (a road on a floor, or one edited with its
-- height; never the land's, whose height the addon doesn't know): a one-way drop (as a cave's ledges, `drops`) where
-- the fall is more than LAYER_Z and at most TRACK_DROP_MAX (Nav.FALL_FREE: no fall damage), within TRACK_DROP_REACH
-- yards of the road over it, one per road under it, looked for every TRACK_DROP_STEP yards along. At route time the
-- player's health still decides (RouteOne's maxDrop).
R.TRACK_DROP_MAX = 14
R.TRACK_DROP_REACH = 6
R.TRACK_DROP_STEP = 4

-- A track's pieces: its stairs stretch (`stairs` = { i, j }, its points) a stairs piece of its own (a ramp's, `skind` =
-- "ramp": a ramp piece, walked as a road), the rest as the track is; each a copy with `part` (0, 1, ..) when split. A
-- track with no stairs stretch: itself.
function R.TrackPieces(t)
  local st = type(t.stairs) == "table" and not t.recorded and t.stairs
  local n = t.pts and #t.pts / 2 or 0
  local i, j = st and tonumber(st[1]), st and tonumber(st[2])
  if not (i and j and i >= 1 and j <= n and j > i and type(t.zs) == "table" and #t.zs == n) then return { t } end
  local out = {}
  local function piece(a, b, stair)
    if b <= a then return end
    local p = {}
    for k, v in pairs(t) do p[k] = v end
    p.pts, p.zs, p.stairs = {}, {}, nil
    for k = a, b do
      p.pts[#p.pts + 1], p.pts[#p.pts + 2] = t.pts[2 * k - 1], t.pts[2 * k]
      p.zs[#p.zs + 1] = t.zs[k]
    end
    local ramp = stair and t.skind == "ramp"
    p.stair = (stair and not ramp) or nil
    if stair then p.kind = ramp and "ramp" or "stairs" end
    p.skind = nil
    p.z = p.zs[1]
    p.part = #out
    out[#out + 1] = p
  end
  piece(1, i, false)
  piece(i, j, true)
  piece(j, n, false)
  return out
end

-- Whether track `t` (a piece: its `part`, nil the whole) is one an edit in `gone` replaced: gone[time] = true (all of
-- it) or { [part] = true }.
function R.Replaced(gone, t)
  local g = t.time and gone[t.time]
  if g == true then return true end
  return g ~= nil and g[t.part or 0] == true
end
-- The tracks an edit replaced, from all of them: [time] = true (the whole track: `rpart` nil) or { [part] = true }.
function R.ReplacedSet(tracks)
  local gone = {}
  for _, t in ipairs(tracks or {}) do
    local r = tonumber(t.replaces)
    if r then
      if t.rpart == nil then gone[r] = true
      elseif gone[r] ~= true then
        gone[r] = gone[r] or {}
        gone[r][tonumber(t.rpart) or 0] = true
      end
    end
  end
  return gone
end
-- The tracks to put on (Router.WithTracks): those an edit replaced left out (`replaces`: the time of the one edited;
-- `rpart`: one piece of it, a recorded walk's or a split edit's, by its `part`; none: all of it), each edit with a
-- stairs stretch as its pieces.
-- A lift as one straight ride, its first point to its last (and their heights): a recorded one kept every point walked,
-- 2 yd apart, with heights ramped between, so it went on as a chain of short steep roads whose top ones went as a
-- dead-end stub, and its top never met the bridge at the tower (Kooki3z 2026-11-20, Freewind Post: the route rode
-- the lift up and hopped through the air to the other tower).
function R.LiftOnePiece(t)
  local p = t.pts
  if t.kind ~= "lift" or type(p) ~= "table" or #p <= 4 then return t end
  local c = {}
  for k, v in pairs(t) do c[k] = v end
  local n = #p
  c.pts = { p[1], p[2], p[n - 1], p[n] }
  if type(t.zs) == "table" then c.zs = { t.zs[1], t.zs[#t.zs] } end
  if type(t.gz) == "table" then c.gz = { t.gz[1], t.gz[#t.gz] } end
  c.stairs, c.rec = nil, nil
  return c
end
function R.ExpandTracks(tracks)
  local gone = R.ReplacedSet(tracks)
  local any = next(gone) ~= nil
  local out = {}
  for _, t in ipairs(tracks or {}) do
    t = R.LiftOnePiece(t)
    if not (any and R.Replaced(gone, t)) then
      if t.stairs and not t.recorded then
        for _, p in ipairs(R.TrackPieces(t)) do out[#out + 1] = p end
      else
        out[#out + 1] = t
      end
    end
  end
  return out
end

local function PolyLength(pts)
  local len = 0
  for i = 1, #pts - 3, 2 do
    len = len + math.sqrt((pts[i + 2] - pts[i]) ^ 2 + (pts[i + 3] - pts[i + 1]) ^ 2)
  end
  return len
end

-- Split an edge's polyline at `along` yards: the points before (ending at the split point)
-- and after (starting at it).
local function SplitPolyline(e, along)
  local a, b = {}, {}
  local acc, done = 0, false
  for i = 5, #e - 3, 2 do
    local ax, ay, bx, by = e[i], e[i + 1], e[i + 2], e[i + 3]
    local seg = math.sqrt((bx - ax) ^ 2 + (by - ay) ^ 2)
    if not done then
      a[#a + 1], a[#a + 2] = ax, ay
      if acc + seg >= along then
        local t = seg > 0 and (along - acc) / seg or 0
        local qx, qy = ax + (bx - ax) * t, ay + (by - ay) * t
        a[#a + 1], a[#a + 2] = qx, qy
        b[#b + 1], b[#b + 2] = qx, qy
        done = true
      end
    else
      b[#b + 1], b[#b + 2] = ax, ay
    end
    acc = acc + seg
  end
  b[#b + 1], b[#b + 2] = e[#e - 1], e[#e]
  return a, b
end

R.SOURCE_RECORDED = 9 -- edge source flag (e[4]) of the player's drawn roads (not yet in the data)
-- A capital's water (Data/Capitals.lua's `<city>_water` grid and its roads, source 7; asked 2026-10-08: "a way out
-- when you fall into a capital's canal"): swum only from in it (Router.CaveDown, the game's IsSwimming), each yard
-- SWIM_FACTOR dearer, so a route never takes the water by choice, and from in it goes to the nearest way out
R.SOURCE_SWIM = 7
R.SWIM_FACTOR = 50

local function MakeEdge(na, nb, pts, source)
  local e = { na, nb, PolyLength(pts), source or 0 }
  for i = 1, #pts do e[4 + i] = pts[i] end
  return e
end

-- Whether (x, y) is inside the loop `poly` (flat points; closed back to its first).
function R.InPolygon(poly, x, y)
  local inside, n = false, #poly / 2
  local jx, jy = poly[2 * n - 1], poly[2 * n]
  for i = 1, n do
    local ix, iy = poly[2 * i - 1], poly[2 * i]
    if (iy > y) ~= (jy > y) and x < (jx - ix) * (y - iy) / (jy - iy) + ix then inside = not inside end
    jx, jy = ix, iy
  end
  return inside
end

-- A cave's ways out (Data/Caves.lua: its roads out of the mouth end on the continent's
-- nearest road) joined onto that road: the road there is split at the point nearest each
-- one's end (within JOIN_SNAP) and the two tied together. `nodes`, `edges`: the network
-- being merged (changed in place); the continent's roads are edges[1..nRoads]; `joins`:
-- the cave roads' node numbers (after `base`).
R.JOIN_SNAP = 12 -- yards
local JOIN_BUCKET = 64
function R.JoinOnto(nodes, edges, nRoads, base, joins)
  local want = {}
  for ji, j in ipairs(joins) do
    local x, y = nodes[(base + j) * 2 - 1], nodes[(base + j) * 2]
    local k = math.floor(x / JOIN_BUCKET) * 65536 + math.floor(y / JOIN_BUCKET)
    want[k] = want[k] or {}
    table.insert(want[k], ji)
  end
  local snap2 = R.JOIN_SNAP * R.JOIN_SNAP
  local best = {} -- [ji] = { d2, edge }
  local function near(x, y, ax, ay, bx, by)
    local vx, vy = bx - ax, by - ay
    local L2 = vx * vx + vy * vy
    local t = L2 > 0 and math.max(0, math.min(1, ((x - ax) * vx + (y - ay) * vy) / L2)) or 0
    local dx, dy = ax + vx * t - x, ay + vy * t - y
    return dx * dx + dy * dy, ax + vx * t, ay + vy * t
  end
  for ei = 1, nRoads do
    -- (and past the end of R.Pump's slice, R.SliceOver: a road's many points against crowded buckets)
    if ei % 200 == 0 or (ei % 8 == 0 and R.SliceOver and R.SliceOver()) then
      local co, main = coroutine.running()
      if co and not main then coroutine.yield() end
    end
    local e = edges[ei]
    for i = 5, e[4] == 3 and 0 or #e - 3, 2 do -- (not onto a drop off a ledge: source 3)
      local ax, ay, bx, by = e[i], e[i + 1], e[i + 2], e[i + 3]
      for kx = math.floor((math.min(ax, bx) - R.JOIN_SNAP) / JOIN_BUCKET), math.floor((math.max(ax, bx) + R.JOIN_SNAP) / JOIN_BUCKET) do
        for ky = math.floor((math.min(ay, by) - R.JOIN_SNAP) / JOIN_BUCKET), math.floor((math.max(ay, by) + R.JOIN_SNAP) / JOIN_BUCKET) do
          for _, ji in ipairs(want[kx * 65536 + ky] or EMPTY) do
            local j = base + joins[ji]
            local d2 = near(nodes[j * 2 - 1], nodes[j * 2], ax, ay, bx, by)
            if d2 <= snap2 and (not best[ji] or d2 < best[ji][1]) then best[ji] = { d2, e } end
          end
        end
      end
    end
  end
  -- (one at a time: a road split for one join may be split again for the next, in its part)
  -- (in a background job: pauses here too; with the rest of the build up to JoinDrawnEnds' it was a 15 ms slice,
  -- a CI timing issue)
  local function pause(i, every)
    if i % every == 0 then
      local co, main = coroutine.running()
      if co and not main then coroutine.yield() end
    elseif every <= 50 and R.SliceOver and R.SliceOver() then -- (each join splits a road: by the clock too)
      coroutine.yield()
    end
  end
  local index = {}
  for ei = 1, nRoads do
    pause(ei, 2000)
    index[edges[ei]] = ei
  end
  local parts = {} -- [original edge] = { its parts (edges), ... }
  local done = 0
  for ji, b in pairs(best) do
    done = done + 1
    pause(done, 50)
    local j = base + joins[ji]
    local jx, jy = nodes[j * 2 - 1], nodes[j * 2]
    local pick, pi, bd, qx, qy = nil, nil, math.huge, nil, nil
    for _, e in ipairs(parts[b[2]] or { b[2] }) do
      for i = 5, #e - 3, 2 do
        local d2, px, py = near(jx, jy, e[i], e[i + 1], e[i + 2], e[i + 3])
        if d2 < bd then pick, pi, bd, qx, qy = e, i, d2, px, py end
      end
    end
    local ei = index[pick]
    local first, second = {}, { qx, qy }
    for i = 5, pi + 1 do first[#first + 1] = pick[i] end
    first[#first + 1], first[#first + 2] = qx, qy
    for i = pi + 2, #pick do second[#second + 1] = pick[i] end
    nodes[#nodes + 1], nodes[#nodes + 2] = qx, qy
    local q = #nodes / 2
    local ea, eb = MakeEdge(pick[1], q, first, pick[4]), MakeEdge(q, pick[2], second, pick[4])
    edges[ei] = ea
    edges[#edges + 1] = eb
    index[ea], index[eb], index[pick] = ei, #edges, nil
    local list = parts[b[2]] or { b[2] }
    for k, e in ipairs(list) do
      if e == pick then table.remove(list, k) break end
    end
    list[#list + 1], list[#list + 2] = ea, eb
    parts[b[2]] = list
    edges[#edges + 1] = MakeEdge(q, j, { qx, qy, jx, jy })
  end
end

-- Floors over floors, for the road and wall tools: an edit changes one floor's roads, the floor
-- nearest the player's height where it's made (a stroke records the height and IsIndoors: Record's
-- `z`, `indoors`). On a level with heights (Undercity's): of the roads within FLOOR_STACK_YD of a
-- spot, those about at the height (LAYER_Z) of the one nearest the player's. On a continent's level,
-- where a cave's or a capital's floor lies under walkable ground (their grids' 3): its roads when the
-- player is down there (CaveDown), else the others. Anywhere else, any road. The map draws the
-- other floors' roads faint while the tools are on (GPSFrame). roads/graph.py's `floors` does the
-- same offline.
R.FLOOR_STACK_YD = 8
-- yards: a track drawn with heights joins the land's road at its end only at about the floor of the road with one
-- nearest the land road's spot within this (WithTracks' LandHeightOK: the land's height there)
R.LAND_FLOOR_YD = 8
-- (and none that near: not at an end higher than another end of its own walk by more than LAYER_Z and this much a yard
-- between them, steeper than the ground is walked (the terrain grid closes past 50 degrees). Issue #676: Grom'gol's
-- zeppelin tower, a recorded walk's top 30 yd up joined the walk's own way to its foot 14 yd off, on the ground)
R.LAND_CLIMB = 1.2
-- Of `heights` (the roads' at a spot), the one nearest `z`; nil when none.
function R.NearestHeight(heights, z)
  local best, bd
  for _, h in ipairs(heights) do
    local d = math.abs(h - z)
    if not bd or d < bd then best, bd = h, d end
  end
  return best
end
-- Whether a road at (x, y) on a continent's level, a cave's or a floor under a capital's (`cave`) or
-- not, is on the floor of someone at height z (indoors or not) there; true where no floor lies over
-- another.
function R.CaveFloorOK(cont, x, y, cave, z, indoors, down)
  local P = ns.Passability
  if not (P and P.OverlayRaw) then return true end
  local v, o = P.OverlayRaw(cont, x, y)
  if v ~= 3 or not (o and o.cave) then return true end
  -- (`down`: the floor picked, down under or up top)
  if down ~= nil then return (cave and true or false) == down end
  return (cave and true or false) == R.CaveDown(cont, x, y, indoors, z)
end
-- The point of road `ed` nearest (x, y): distance squared, yards along it, the point, and its
-- segment's direction; nil for a road of one point.
local function Closest(ed, x, y)
  local best, bAlong, bx, by, bvx, bvy
  local along = 0
  for i = 5, #ed - 3, 2 do
    local ax, ay, cx, cy = ed[i], ed[i + 1], ed[i + 2], ed[i + 3]
    local vx, vy = cx - ax, cy - ay
    local L2 = vx * vx + vy * vy
    local t = 0
    if L2 > 0 then t = math.max(0, math.min(1, ((x - ax) * vx + (y - ay) * vy) / L2)) end
    local qx, qy = ax + vx * t, ay + vy * t
    local d2 = (qx - x) ^ 2 + (qy - y) ^ 2
    local L = math.sqrt(L2)
    if not best or d2 < best then best, bAlong, bx, by, bvx, bvy = d2, along + L * t, qx, qy, vx, vy end
    along = along + L
  end
  return best, bAlong, bx, by, bvx, bvy
end
-- Road `ed`'s height `along` yards along it, from its ends' (`zs`: each node's): nil when unknown.
local function HeightOn(zs, ed, along)
  local za, zb = zs[ed[1]], zs[ed[2]]
  if not za or not zb then return za or zb end
  return za + (zb - za) * math.max(0, math.min(1, along / math.max(ed[3], 1)))
end
R.HeightOn = HeightOn
-- Road `ed`'s middle: x, y and yards along it.
function R.EdgeMiddle(ed)
  local half, along = ed[3] / 2, 0
  for i = 5, #ed - 3, 2 do
    local ax, ay, cx, cy = ed[i], ed[i + 1], ed[i + 2], ed[i + 3]
    local L = math.sqrt((cx - ax) ^ 2 + (cy - ay) ^ 2)
    if along + L >= half then
      local t = L > 0 and (half - along) / L or 0
      return ax + (cx - ax) * t, ay + (cy - ay) * t, half
    end
    along = along + L
  end
  return ed[5], ed[6], 0
end
-- The roads' heights near a spot, on a level with heights: a function (x, y, r) -> { height, ... } of
-- the roads in `edges` (their nodes' heights `zs`) within r (FLOOR_STACK_YD by default) there.
function R.FloorIndex(edges, zs)
  local B = R.FLOOR_STACK_YD
  local b = {}
  for ei, ed in ipairs(edges) do
    if R.Breathe then R.Breathe(ei, 300) end
    local along = 0
    for i = 5, #ed - 3, 2 do
      local ax, ay, cx, cy = ed[i], ed[i + 1], ed[i + 2], ed[i + 3]
      local L = math.sqrt((cx - ax) ^ 2 + (cy - ay) ^ 2)
      local s = { ax, ay, cx, cy, ed, along, L }
      for kx = math.floor(math.min(ax, cx) / B), math.floor(math.max(ax, cx) / B) do
        for ky = math.floor(math.min(ay, cy) / B), math.floor(math.max(ay, cy) / B) do
          local k = kx * 65536 + ky
          local l = b[k]
          if not l then
            l = {}
            b[k] = l
          end
          l[#l + 1] = s
        end
      end
      along = along + L
    end
  end
  return function(x, y, r)
    r = r or B
    local hs, seen = {}, {}
    for kx = math.floor((x - r) / B), math.floor((x + r) / B) do
      for ky = math.floor((y - r) / B), math.floor((y + r) / B) do
        for _, s in ipairs(b[kx * 65536 + ky] or EMPTY) do
          if not seen[s] then
            seen[s] = true
            local ax, ay, vx, vy = s[1], s[2], s[3] - s[1], s[4] - s[2]
            local L2 = vx * vx + vy * vy
            local t = L2 > 0 and math.max(0, math.min(1, ((x - ax) * vx + (y - ay) * vy) / L2)) or 0
            if (ax + vx * t - x) ^ 2 + (ay + vy * t - y) ^ 2 <= r * r then
              local h = HeightOn(zs, s[5], s[6] + s[7] * t)
              if h then hs[#hs + 1] = h end
            end
          end
        end
      end
    end
    return hs
  end
end

-- The road data plus the player's drawn roads (Record.lua), in their order: "add" tracks
-- become roads (replacing the stretches of road they run along; see TRACK_OVERLAP),
-- "remove" tracks cut out the road under them. Tracks the data already has
-- (ns.RoadTracksIn, by time) are skipped. Returns node coordinates and edges (copies; the
-- shipped data isn't changed), and on a level with heights each node's (`roads.z`, the new nodes'
-- too). A track with a floor (`z`, `indoors`) changes only that floor's roads (FLOOR_STACK_YD).
-- `roads.cave`, `roads.drop` ([edge] = ...: a continent's caves' roads, drops) go on to the
-- pieces a road is split or cut into; a road drawn down in a cave is one of its roads.
-- app/azerothgps/roads/graph.py does the same offline.
-- A road's bounding box { x0, x1, y0, y1 } (its points from index 5), kept: the roads' own don't
-- change, and merging the drawn roads asks for them over and over.
local edgeBoxes = setmetatable({}, { __mode = "k" })
-- (asked for only while a graph is built; the graph's own edges stay referenced, so the boxes never
-- fell out of the weak table — 1.8 MB held for nothing (the 2026-10-07 memory census). Cleared at the
-- build's end and remade by the next build.)
local function ClearEdgeBoxes() edgeBoxes = setmetatable({}, { __mode = "k" }) end
local function EdgeBox(ed)
  local b = edgeBoxes[ed]
  if not b then
    local x0, x1, y0, y1 = math.huge, -math.huge, math.huge, -math.huge
    for k = 5, #ed - 1, 2 do
      local x, y = ed[k], ed[k + 1]
      if x < x0 then x0 = x end
      if x > x1 then x1 = x end
      if y < y0 then y0 = y end
      if y > y1 then y1 = y end
    end
    b = { x0, x1, y0, y1 }
    edgeBoxes[ed] = b
  end
  return b
end

-- Heights for a road's points `pts` (flat x, y list) from its ends' floors `z1` and `z2`: rising evenly by the yards
-- along it from one to the other; one alone, flat at it; neither, nil (R.RAMP_END_YD).
function R.RampHeights(pts, z1, z2)
  if not z1 and not z2 then return nil end
  z1, z2 = z1 or z2, z2 or z1
  local n = #pts / 2
  local along, total = { 0 }, 0
  for k = 2, n do
    total = total + math.sqrt((pts[2 * k - 1] - pts[2 * k - 3]) ^ 2 + (pts[2 * k] - pts[2 * k - 2]) ^ 2)
    along[k] = total
  end
  local out = {}
  for k = 1, n do out[k] = total > 0 and z1 + (z2 - z1) * along[k] / total or z1 end
  return out
end

function R.WithTracks(roads, tracks, cont)
  -- (long loops: in the background build, a pause every so often, not one long frame;
  -- R.Breathe, defined further down, does nothing outside it)
  local ticks = 0
  local function tick(every)
    ticks = ticks + 1
    if R.Breathe then R.Breathe(ticks, every or 200) end
  end
  local n, e = {}, {}
  -- (the copies too: with the next thousand roads indexed, a 14 ms slice on Kalimdor; 2026-11-21)
  for i = 1, #roads.n do
    tick(R.KEEP_BREATHE)
    n[i] = roads.n[i]
  end
  for i = 1, #roads.e do
    tick(R.KEEP_BREATHE)
    e[i] = roads.e[i]
  end
  -- (the edits: the tracks they replaced left out, a stairs stretch its own piece)
  tracks = R.ExpandTracks(tracks)
  -- (each road's kind, edited (R.TRACK_KINDS): the map draws it; a raised one's (R.RAISED_KINDS) roads, the nodes
  -- along it (not its two ends: those are where it meets the land), and the tracks for their drops)
  local kindOf, raised, raisedNode, raisedEnd, raisedTracks = {}, {}, {}, {}, {}
  -- (the roads of tracks drawn or recorded with their heights: RouteOne's walks round go to the roads on the ground)
  local floored = {}
  local curAdd = false -- (a road being drawn on, not an erasure)
  local zs -- (a level with heights: each node's, copied below when there's anything to do)
  -- (on a continent, its buildings' and capitals' roads' floors, `roads.nz`: copied the same way, a drawn road's new
  -- nodes with the heights it was drawn at: asked 2026-10-06, the road tools' heights)
  local nzs
  -- (the roads drawn with their heights on a building's floor (Data/Indoors.lua's), as its inside: never cut by the walls
  -- drawn round it, BuildGraph's `indoorOf`)
  local inside = {}
  local function newNode(x, y, z, f)
    n[#n + 1], n[#n + 2] = x, y
    if zs then zs[#n / 2] = z end
    if nzs and f then nzs[#n / 2] = f end
    return #n / 2
  end
  local caveOf, dropOf = roads.cave, roads.drop
  -- (the roads each walk made, by its time: a recorded walk's pieces never replace, cut or split each other; issue #33,
  -- Darnassus's spiral stairs, whose last turn the next piece, beside it at about its height, replaced)
  local walkOf, curWalk = {}, nil
  local function sameWalk(ed) return curWalk ~= nil and walkOf[ed] == curWalk end
  local function inherit(from, to)
    if caveOf and caveOf[from] then caveOf[to] = true end
    if dropOf and dropOf[from] then dropOf[to] = dropOf[from] end
    walkOf[to] = walkOf[from]
    floored[to] = floored[from]
    kindOf[to], raised[to] = kindOf[from], raised[from]
  end
  local city = ns.CityLevels and ns.CityLevels[cont]
  local snap = city and R.TRACK_SNAP_CITY or R.TRACK_SNAP
  local function bounds(pts, i0)
    local x0, x1, y0, y1 = math.huge, -math.huge, math.huge, -math.huge
    for k = i0 or 1, #pts - 1, 2 do
      x0, x1 = math.min(x0, pts[k]), math.max(x1, pts[k])
      y0, y1 = math.min(y0, pts[k + 1]), math.max(y1, pts[k + 1])
    end
    return x0, x1, y0, y1
  end
  -- The roads by grid square (their boxes'), and each one's place in `e`: a drawn road only
  -- looks at the roads near it, not every road on the continent, and in `e`'s order (so the
  -- result is the same as looking at all of them). Only the roads near the drawn ones are in it
  -- (nothing further than TRACK_REACH from one is ever touched).
  local BK = 128
  local grid, where = {}, {}
  local mine0 -- (the tracks' area, TRACK_REACH around them: the roads that can be touched)
  local shipped = ns.RoadTracksIn or {}
  local function wanted(t)
    -- (a shipped one with its heights, ns.FloorTracks: put on as it was drawn, though the data has its time)
    return t.continent == cont and t.pts and #t.pts >= 4 and (t.shipped or not shipped[t.time or -1])
      and t.op ~= "wall" and t.op ~= "unwall"
  end
  -- (each walk's pieces' ends, by its time: a piece's end where another of its pieces ends is inside the walk; and
  -- each end's height, with one a point: LandHeightOK)
  local walkEnds = {}
  for _, t in ipairs(tracks or {}) do
    if wanted(t) and t.op ~= "remove" and t.time and type(t.zs) == "table" then
      local l = walkEnds[t.time] or {}
      walkEnds[t.time] = l
      local tz = #t.zs == #t.pts / 2 and t.zs or {}
      l[#l + 1] = { t, t.pts[1], t.pts[2], tz[1] }
      l[#l + 1] = { t, t.pts[#t.pts - 1], t.pts[#t.pts], tz[#tz] }
    end
  end
  local function innerEnd(t, x, y)
    local r2 = R.TRACK_WALK_JOIN * R.TRACK_WALK_JOIN
    for _, w in ipairs(t.time and walkEnds[t.time] or {}) do
      if w[1] ~= t and (w[2] - x) ^ 2 + (w[3] - y) ^ 2 <= r2 then return true end
    end
    return false
  end
  for _, t in ipairs(tracks or {}) do
    if wanted(t) then
      local x0, x1, y0, y1 = bounds(t.pts)
      if not mine0 then mine0 = { x0, x1, y0, y1 }
      else mine0 = { math.min(mine0[1], x0), math.max(mine0[2], x1), math.min(mine0[3], y0), math.max(mine0[4], y1) } end
    end
  end
  if not mine0 then return n, e, roads.z, roads.nz end
  if roads.z then
    zs = {}
    for k, z in pairs(roads.z) do
      tick(R.KEEP_BREATHE)
      zs[k] = z
    end
  elseif roads.nz then
    nzs = {}
    for k, z in pairs(roads.nz) do
      tick(R.KEEP_BREATHE)
      nzs[k] = z
    end
  end
  local reach0 = R.TRACK_REACH
  local function keys(ed, fn)
    local bb = EdgeBox(ed)
    for kx = math.floor(bb[1] / BK), math.floor(bb[2] / BK) do
      for ky = math.floor(bb[3] / BK), math.floor(bb[4] / BK) do fn(kx * 65536 + ky) end
    end
  end
  local function put(ed, i)
    where[ed] = i
    local bb = EdgeBox(ed)
    if bb[2] < mine0[1] - reach0 or bb[1] > mine0[2] + reach0 or bb[4] < mine0[3] - reach0 or bb[3] > mine0[4] + reach0 then
      return -- (far from every drawn road)
    end
    keys(ed, function(k)
      local sq = grid[k]
      if not sq then
        sq = {}
        grid[k] = sq
      end
      sq[ed] = true
    end)
  end
  local function drop(ed)
    where[ed] = nil
    keys(ed, function(k)
      local sq = grid[k]
      if sq then sq[ed] = nil end
    end)
  end
  for i, ed in ipairs(e) do
    tick(1000)
    put(ed, i)
  end
  -- The roads whose boxes overlap x0..x1, y0..y1, in `e`'s order.
  local function near(x0, x1, y0, y1)
    local seen, out = {}, {}
    for kx = math.floor(x0 / BK), math.floor(x1 / BK) do
      for ky = math.floor(y0 / BK), math.floor(y1 / BK) do
        for ed in pairs(grid[kx * 65536 + ky] or EMPTY) do
          if not seen[ed] then
            seen[ed] = true
            local bb = EdgeBox(ed)
            if bb[2] >= x0 and bb[1] <= x1 and bb[4] >= y0 and bb[3] <= y1 then out[#out + 1] = ed end
          end
        end
      end
    end
    table.sort(out, function(a, b) return where[a] < where[b] end)
    return out
  end
  -- The floor of the track being applied ({ z, indoors }, or nil: any road), and whether road `ed`
  -- (`along` yards along it) is on it under the track's spot (x, y): on a level with heights, about at
  -- the height of the road nearest the track's within FLOOR_STACK_YD of that spot (where one floor
  -- alone is under the track, that one).
  -- (the floors are those of the roads as they were before the track: one it has cut away already
  -- doesn't make the floor over it the only one there; `heights`, R.FloorIndex of them, made per track)
  local fl, heights
  local LandHeightOK -- (below)
  local FS = R.FLOOR_STACK_YD
  -- (the track's height at (x, y): its point's nearest there when it has one per point, `zs` (asked 2026-10-06: a
  -- road drawn up the floors, a stair's foot and top), else the one for the whole stroke; `fl.at` while a point of the
  -- line is judged, its own height: a spiral stair passes over one spot on each turn, issue #33)
  local function trackZ(x, y)
    if not fl then return nil end
    if fl.at then return fl.at end
    local tz = fl.zs
    if not tz then return fl.z end
    local best, bz = math.huge, fl.z
    for k = 1, #fl.pts - 1, 2 do
      local h = tz[(k + 1) / 2]
      local d = (fl.pts[k] - x) ^ 2 + (fl.pts[k + 1] - y) ^ 2
      if h and d < best then best, bz = d, h end
    end
    return bz
  end
  local function floorHere(x, y, r, z)
    return R.NearestHeight(heights(x, y, math.max(r or 0, FS)), z or fl.z)
  end
  -- (`r`: the edit's reach there, when more than FLOOR_STACK_YD: every road it can touch counts)
  local function onFloor(ed, x, y, along, r)
    -- (a road with no floor drawn on: a raised one (a bridge, a floor over the land) only at its own ends, never where
    -- it passes over on the map)
    if not fl and curAdd and raised[ed] then
      return (along < 3 and raisedEnd[ed[1]] == true) or (along > ed[3] - 3 and raisedEnd[ed[2]] == true)
    end
    if not fl then return true end
    if zs then
      local fz = trackZ(x, y)
      if not fz then return true end
      local h = HeightOn(zs, ed, along)
      local f = h and floorHere(x, y, r, fz)
      return not f or math.abs(h - f) <= R.LAYER_Z
    end
    -- (a building's or a capital's road on a continent, with its floor: only one at about the track's height there,
    -- for a track drawn with its heights (`zs`); one with only a `z`, older, says above or below a floor under the
    -- capital's: CaveFloorOK)
    local fz = nzs and fl.zs and trackZ(x, y)
    local h = fz and HeightOn(nzs, ed, along)
    if h then return math.abs(h - fz) <= R.TRACK_FLOOR_Z end
    -- (the land's road, no floor of its own, for a track drawn with its heights: joined only at the track's ends, where
    -- it comes out of a building onto the road (`fl.landOK`); never crossed or replaced on the way, under an upstairs road)
    -- (and only an end at about the land's height there: issue #33, Darnassus's Rogue Trainer, a floor 23 yd under the
    -- Cenarion Enclave's road; the spiral's foot and the trainer's floor were joined up onto that road overhead)
    if fz then return fl.landOK == true and LandHeightOK(ed, x, y, fz) end
    if caveOf then return R.CaveFloorOK(cont, x, y, caveOf[ed], fl.z, fl.indoors, fl.down) end
    return true
  end
  -- (whether a track's end at height `fz` by (x, y) may join the land's road `ed`: the addon has no ground heights, so
  -- the land's there is the floor of the road with one (a capital's or a building's) nearest the land road's spot,
  -- within LAND_FLOOR_YD; none that near: it may, as before)
  LandHeightOK = function(ed, x, y, fz)
    local d2, _, qx, qy = Closest(ed, x, y)
    if not d2 then return true end
    local r = R.LAND_FLOOR_YD
    local best, bh = r * r, nil
    for _, o in ipairs(near(qx - r, qx + r, qy - r, qy + r)) do
      local od2, oal = Closest(o, qx, qy)
      local h = od2 and od2 <= best and HeightOn(nzs, o, oal)
      if h then best, bh = od2, h end
    end
    if bh then return math.abs(bh - fz) <= R.LAYER_Z end
    for _, w in ipairs(curWalk and walkEnds[curWalk] or {}) do
      if w[4] and fz - w[4] > R.LAYER_Z + math.sqrt((x - w[2]) ^ 2 + (y - w[3]) ^ 2) * R.LAND_CLIMB then return false end
    end
    return true
  end
  -- (a new node's height, on a level with heights: the track's floor there)
  local function heightAt(x, y)
    local fz = zs and trackZ(x, y)
    if not fz then return nil end
    return floorHere(x, y, nil, fz) or fz
  end
  -- (and on a continent, its floor: the height the track was drawn at there, when it has one)
  local function floorAt(x, y)
    return nzs and fl and fl.zs and trackZ(x, y) or nil
  end
  -- (a road drawn on a continent down in a cave, or on a floor under a capital's: one of its roads)
  local caveSplit = {} -- (a piece marked so off its grid: the split height it was under)
  local function markCave(ed, pts)
    if not (caveOf and fl) then return end
    local k = math.floor(#pts / 4) * 2 + 1
    local x, y = pts[k], pts[k + 1]
    local P = ns.Passability
    if not (P and P.OverlayRaw) then return end
    local v, o = P.OverlayRaw(cont, x, y)
    local down = fl.down
    if down == nil then down = R.CaveDown(cont, x, y, fl.indoors, fl.z) end
    if v ~= nil and o and o.cave and down then caveOf[ed] = true end
    -- (a piece drawn with its heights over none of its grid, going on from one of its roads below its split: one of them
    -- too. Issue #65: Ironforge's First Aid trainer's landing and floor, a room its grid doesn't cover, were the land's
    -- roads up on the mountain, and a stop down in the city never took them)
    if v == nil and fl.zs and not caveOf[ed] then
      local top = -math.huge
      for _, h in ipairs(fl.zs) do top = math.max(top, h) end
      for _, nd in ipairs({ ed[1], ed[2] }) do
        local nx, ny = n[nd * 2 - 1], n[nd * 2]
        for _, o2 in ipairs(near(nx - 0.5, nx + 0.5, ny - 0.5, ny + 0.5)) do
          if o2 ~= ed and caveOf[o2] and (o2[1] == nd or o2[2] == nd) then
            local split = caveSplit[o2]
            for k = 5, split and 0 or #o2 - 1, 2 do
              local ov, oo = P.OverlayRaw(cont, o2[k], o2[k + 1])
              split = ov ~= nil and oo and oo.cave and (oo.split or oo.zsplit) or nil
              if split then break end
            end
            if split then
              if top < split then caveOf[ed], caveSplit[ed] = true, split end
              return
            end
          end
        end
      end
    end
  end
  -- the node at (x, y) on the network (within `reach`; of the edges in `only` if given; on the
  -- track's floor), splitting an edge if needed; nil if none is close
  local function attach(x, y, reach, only)
    local best, bi, bAlong, bx, by
    reach = reach or snap
    for _, ed in ipairs(near(x - reach, x + reach, y - reach, y + reach)) do
      tick()
      -- (a walk with its heights: never onto its own roads but where its pieces meet, `only`: a short piece's end snapped
      -- back onto the piece before it, and was lost; issue #65)
      if (only and only[ed]) or (not only and not (fl and fl.zs and sameWalk(ed))) then
        local d2, along, qx, qy = Closest(ed, x, y)
        local tight = raised[ed] or kindOf[ed] == "lift" -- (a bridge, a floor, a lift: only R.TRACK_SNAP_RAISED)
        if d2 and (not best or d2 < best) and not (tight and d2 > R.TRACK_SNAP_RAISED ^ 2)
            and onFloor(ed, x, y, along, reach) then
          best, bi, bAlong, bx, by = d2, where[ed], along, qx, qy
        end
      end
    end
    if not best or best > reach * reach then return nil end
    local ed = e[bi]
    if bAlong < 3 then return ed[1], ed[5], ed[6] end
    if bAlong > ed[3] - 3 then return ed[2], ed[#ed - 1], ed[#ed] end
    local mid = newNode(bx, by, zs and HeightOn(zs, ed, bAlong), nzs and HeightOn(nzs, ed, bAlong))
    local p1, p2 = SplitPolyline(ed, bAlong)
    drop(ed)
    e[bi] = MakeEdge(ed[1], mid, p1, ed[4])
    inherit(ed, e[bi])
    put(e[bi], bi)
    e[#e + 1] = MakeEdge(mid, ed[2], p2, ed[4])
    inherit(ed, e[#e])
    put(e[#e], #e)
    if only then only[e[bi]], only[e[#e]] = true, true end
    return mid, bx, by
  end
  -- The stretches of road within `reach` of any of `lines` (flat point lists) cut out of
  -- the roads they're on (`parallel`: only where they run about parallel to it); the rest
  -- of each road stays, split where it was cut. Returns the new road ends: { { node, x, y } }.
  local cutNodes = {} -- (the road ends cuts made)
  -- (`area`: the lines are loops, and the road inside them goes)
  local function cut(lines, reach, parallel, area)
    local r2 = reach * reach
    local boxes = {}
    for li, l in ipairs(lines) do boxes[li] = { bounds(l) } end
    -- (and where on the lines: the floor there is the one an edit changes; in a loop, the spot itself)
    local function under(x, y, rvx, rvy)
      if area then
        for li, l in ipairs(lines) do
          local b = boxes[li]
          if x >= b[1] and x <= b[2] and y >= b[3] and y <= b[4] and R.InPolygon(l, x, y) then return true, x, y end
        end
        return false
      end
      for li, l in ipairs(lines) do
        local b = boxes[li]
        if not (x < b[1] - reach or x > b[2] + reach or y < b[3] - reach or y > b[4] + reach) then
          for k = 1, #l - 3, 2 do
            local ax, ay, cx, cy = l[k], l[k + 1], l[k + 2], l[k + 3]
            local vx, vy = cx - ax, cy - ay
            local L2 = vx * vx + vy * vy
            local tt = 0
            if L2 > 0 then tt = math.max(0, math.min(1, ((x - ax) * vx + (y - ay) * vy) / L2)) end
            if (ax + vx * tt - x) ^ 2 + (ay + vy * tt - y) ^ 2 <= r2 then
              if not parallel then return true, ax + vx * tt, ay + vy * tt end
              local nv, nr = math.sqrt(L2), math.sqrt(rvx * rvx + rvy * rvy)
              if nv > 0 and nr > 0 and math.abs(vx * rvx + vy * rvy) / (nv * nr) >= R.TRACK_ALONG_COS then
                return true, ax + vx * tt, ay + vy * tt
              end
            end
          end
        end
      end
      return false
    end
    -- (only the roads near the lines can be cut: the rest stay as they are)
    local cand = {}
    for _, b in ipairs(boxes) do
      for _, ed in ipairs(near(b[1] - reach, b[2] + reach, b[3] - reach, b[4] + reach)) do
        if not sameWalk(ed) then cand[ed] = true end
      end
    end
    local ends, kept, fresh = {}, {}, {}
    for _, ed in ipairs(e) do
      tick(2000)
      if not cand[ed] then
        kept[#kept + 1] = ed
      else
        -- its points every 2 yards or so, each under the lines (on the track's floor) or not
        local dense, flag, anyUnder = {}, {}, false
        local dal, along = {}, 0 -- (each point's yards along the road)
        for i = 5, #ed - 3, 2 do
          local ax, ay, bx, by = ed[i], ed[i + 1], ed[i + 2], ed[i + 3]
          local L = math.sqrt((bx - ax) ^ 2 + (by - ay) ^ 2)
          local m = math.max(1, math.ceil(L / 2))
          for k = (i == 5) and 0 or 1, m do
            local x, y = ax + (bx - ax) * k / m, ay + (by - ay) * k / m
            dense[#dense + 1], dense[#dense + 2] = x, y
            dal[#dal + 1] = along + L * k / m
            local u, sx, sy = under(x, y, bx - ax, by - ay)
            local f = u and onFloor(ed, sx, sy, along + L * k / m, reach)
            flag[#flag + 1] = f
            anyUnder = anyUnder or f
          end
          along = along + L
        end
        if not anyUnder then
          kept[#kept + 1] = ed
        else
          drop(ed)
          -- (a junction the cut took away from under another road: that road's end now)
          if flag[1] then ends[#ends + 1] = { ed[1], dense[1], dense[2] } end
          if flag[#flag] then ends[#ends + 1] = { ed[2], dense[#dense - 1], dense[#dense] } end
          -- the stretches not under them, as roads of their own
          local run = {}
          local function flush(last)
            if #run >= 4 then
              local na = run.startsAtA and ed[1]
              if not na then
                na = newNode(run[1], run[2], zs and HeightOn(zs, ed, run.a0), nzs and HeightOn(nzs, ed, run.a0))
                ends[#ends + 1] = { na, run[1], run[2] }
                cutNodes[na] = true
              end
              local nb = last and ed[2]
              if not nb then
                nb = newNode(run[#run - 1], run[#run], zs and HeightOn(zs, ed, run.a1), nzs and HeightOn(nzs, ed, run.a1))
                ends[#ends + 1] = { nb, run[#run - 1], run[#run] }
                cutNodes[nb] = true
              end
              local piece = MakeEdge(na, nb, run, ed[4])
              inherit(ed, piece)
              kept[#kept + 1] = piece
              fresh[piece] = true
            end
            run = {}
          end
          for j, f in ipairs(flag) do
            if f then
              if #run > 0 then flush(false) end
            else
              if #run == 0 then run.startsAtA, run.a0 = (j == 1), dal[j] end
              run[#run + 1], run[#run + 2] = dense[2 * j - 1], dense[2 * j]
              run.a1 = dal[j]
            end
          end
          if #run > 0 then flush(true) end
        end
      end
    end
    e = kept
    for i, ed in ipairs(e) do
      tick(2000)
      if fresh[ed] then put(ed, i) else where[ed] = i end
    end
    return ends
  end
  -- How many roads (not in `skip`) end at node `nd` (at x, y).
  local function degree(nd, x, y, skip)
    local d = 0
    for _, ed in ipairs(near(x - 0.5, x + 0.5, y - 0.5, y + 0.5)) do
      if not skip[ed] then
        if ed[1] == nd then d = d + 1 end
        if ed[2] == nd then d = d + 1 end
      end
    end
    return d
  end
  -- (the roads of the walk being applied near (x, y): attach's `only`)
  local function ownWalk(x, y)
    local r, set = R.TRACK_WALK_JOIN, {}
    for _, ed in ipairs(near(x - r, x + r, y - r, y + r)) do
      if sameWalk(ed) then set[ed] = true end
    end
    return set
  end
  -- (a road with no heights on a continent with floors: the heights of the floored roads at its ends, R.RAMP_END_YD)
  local function endFloor(x, y)
    local r = R.RAMP_END_YD
    local best, bh = r * r, nil
    for _, ed in ipairs(near(x - r, x + r, y - r, y + r)) do
      local d2, al = Closest(ed, x, y)
      local h = d2 and d2 <= best and HeightOn(nzs, ed, al)
      if h then best, bh = d2, h end
    end
    return bh
  end
  for _, t in ipairs(tracks or {}) do
    local pts = t.pts
    -- (walls aren't roads: Passability has them)
    if wanted(t) then
      curWalk = t.op ~= "remove" and t.time or nil
      curAdd = t.op ~= "remove"
      local tzs = type(t.zs) == "table" and #t.zs == #pts / 2 and t.zs or nil -- (its heights per point: checked)
      if not tzs and t.z == nil and nzs and t.op ~= "remove" and not t.stair then
        -- (only one in a capital or a building with its inside, by its middle: out on the land a road with no heights
        -- stays the land's, joined and crossed as before)
        local mk = math.floor(#pts / 4) * 2 + 1
        local mx, my = pts[mk], pts[mk + 1]
        if R.CapitalAt(cont, mx, my) or (ns.Nav and ns.Nav.InBuilding and ns.Nav.InBuilding(cont, mx, my, "joined")) then
          tzs = R.RampHeights(pts, endFloor(pts[1], pts[2]), endFloor(pts[#pts - 1], pts[#pts]))
        end
      end
      fl = (t.z or tzs or t.indoors ~= nil or t.down ~= nil)
        and { z = t.z or (tzs and tzs[1]), zs = tzs, pts = pts, indoors = t.indoors, down = t.down } or nil
      heights = zs and fl and fl.z and R.FloorIndex(e, zs) or nil
      if t.op == "remove" then
        if t.area then cut({ pts }, 0, false, true) else cut({ pts }, R.TRACK_REMOVE_YD) end
      else
        local over = city and R.TRACK_OVERLAP_CITY or R.TRACK_OVERLAP
        local crossYd = city and R.TRACK_CROSS_CITY or R.TRACK_CROSS
        local alongMin = city and R.TRACK_ALONG_MIN_CITY or R.TRACK_ALONG_MIN
        -- the roads' segments near the drawn line (on its floor): the nearest one's distance and
        -- direction (only those within `over`: a road further off is never along it nor crossed)
        local function nearest(x, y, z)
          local best, bvx, bvy = math.huge, 0, 0
          if fl then fl.at = z end
          for _, ed in ipairs(near(x - over, x + over, y - over, y + over)) do
            local bb = EdgeBox(ed)
            -- (never along a lift or crossing it: a ride up or down, not a road a stairs or a walk at its foot replaces;
            -- Freewind Post's stairs ran on in line with the lift at its foot and cut it out, 2026-11-20)
            if not sameWalk(ed) and not (kindOf[ed] == "lift" or ed[4] == R.SOURCE_LIFT) and math.max(bb[1] - x, 0, x - bb[2]) ^ 2 + math.max(bb[3] - y, 0, y - bb[4]) ^ 2 < best then
              local d2, along, _, _, vx, vy = Closest(ed, x, y)
              if d2 and d2 < best and onFloor(ed, x, y, along, over) then best, bvx, bvy = d2, vx, vy end
            end
          end
          if fl then fl.at = nil end
          return math.sqrt(best), bvx, bvy
        end
        -- the drawn line every 2 yards or so (its own points marked)
        local dx, dy, own = { pts[1] }, { pts[2] }, { true }
        local dz = { tzs and tzs[1] } -- (and each one's height, with heights per point)
        for k = 1, #pts - 3, 2 do
          local ax, ay, bx, by = pts[k], pts[k + 1], pts[k + 2], pts[k + 3]
          local m = math.max(1, math.ceil(math.sqrt((bx - ax) ^ 2 + (by - ay) ^ 2) / 2))
          local za, zb = tzs and tzs[(k + 1) / 2], tzs and tzs[(k + 3) / 2]
          for q = 1, m do
            dx[#dx + 1], dy[#dy + 1], own[#own + 1] = ax + (bx - ax) * q / m, ay + (by - ay) * q / m, q == m
            dz[#dx] = za and zb and za + (zb - za) * q / m or nil
          end
        end
        local M = #dx
        -- along a road: close and about parallel, for a while (or at the drawn road's ends)
        local along = {}
        for j = 1, M do
          tick(20)
          local d, vx, vy = nearest(dx[j], dy[j], dz[j])
          local j0, j1 = math.max(j - 1, 1), math.min(j + 1, M)
          local wx, wy = dx[j1] - dx[j0], dy[j1] - dy[j0]
          local nv, nw = math.sqrt(vx * vx + vy * vy), math.sqrt(wx * wx + wy * wy)
          along[j] = d <= over and nv > 0 and nw > 0 and math.abs(vx * wx + vy * wy) / (nv * nw) >= R.TRACK_ALONG_COS
        end
        local alongLines = {}
        local j = 1
        while j <= M do
          if along[j] then
            local k = j
            while k < M and along[k + 1] do k = k + 1 end
            if j == 1 or k == M or (k - j) * 2 >= alongMin then
              local l = {}
              for q = j, k do l[#l + 1], l[#l + 2] = dx[q], dy[q] end
              if #l == 2 then l[3], l[4] = l[1], l[2] end
              alongLines[#alongLines + 1] = l
            end
            j = k + 1
          else
            j = j + 1
          end
        end
        -- the road there goes: the drawn one replaces it
        local cutEnds = #alongLines > 0 and cut(alongLines, over, true) or {}
        -- where it crosses a road left: split there (a junction)
        local splits, cd = {}, {}
        for q = 1, M do
          tick(20)
          cd[q] = nearest(dx[q], dy[q], dz[q])
        end
        local q = 2
        -- (a bridge with no height known: over whatever it crosses, never joined to it there; only at its ends)
        if t.kind == "bridge" and not tzs then q = M end
        while q < M do
          if cd[q] <= crossYd then
            local c1, bestQ = q, q
            while c1 < M - 1 and cd[c1 + 1] <= crossYd do
              c1 = c1 + 1
              if cd[c1] < cd[bestQ] then bestQ = c1 end
            end
            splits[#splits + 1] = bestQ
            q = c1 + 1
          else
            q = q + 1
          end
        end
        -- (an edited road with its heights (`kind`): a node at each of its own points too, so the heights between its
        -- ends are kept (a bridge rising from the land and level over a road under it: one road end to end was at the
        -- land's height all the way, its ends', and joined that road)
        local ownSplit -- (those: the next piece goes on from the node the one before ended at)
        if t.kind and tzs then
          local set = {}
          ownSplit = {}
          for _, sq in ipairs(splits) do set[sq] = true end
          for qq = 2, M - 1 do
            if own[qq] and not set[qq] then set[qq], ownSplit[qq] = true, true end
          end
          splits = {}
          for sq in pairs(set) do splits[#splits + 1] = sq end
          table.sort(splits)
        end
        splits[#splits + 1] = M
        -- the pieces between them, each joined at both ends
        local mine = {} -- (this track's roads)
        -- (a bridge with no height known is raised too: kept off the roads under it, no drops off it; Kooki3z
        -- 2026-11-20, Thousand Needles' rope bridges between the mesas, no floors near them to take a height from)
        local isRaised = R.RAISED_KINDS[t.kind or ""] and ((fl and fl.zs) or t.kind == "bridge") and true or false
        if isRaised then raisedTracks[#raisedTracks + 1] = { t = t, mine = mine } end
        local endSnap = (isRaised or t.kind == "lift") and math.min(snap, R.TRACK_SNAP_RAISED) or snap
        local joined = {}
        local s0 = 1
        local lastNb, lastX, lastY -- (the node the piece before ended at)
        for _, s1 in ipairs(splits) do
          if s1 > s0 then
            local line = { dx[s0], dy[s0] }
            for qq = s0 + 1, s1 - 1 do
              if own[qq] and (dx[qq] - dx[s0]) ^ 2 + (dy[qq] - dy[s0]) ^ 2 >= 4
                  and (dx[qq] - dx[s1]) ^ 2 + (dy[qq] - dy[s1]) ^ 2 >= 4 then
                line[#line + 1], line[#line + 2] = dx[qq], dy[qq]
              end
            end
            line[#line + 1], line[#line + 2] = dx[s1], dy[s1]
            if fl then fl.landOK, fl.at = s0 == 1, dz[s0] end
            local na, ax, ay
            if ownSplit and ownSplit[s0] and lastNb then
              na, ax, ay = lastNb, lastX, lastY
            elseif s0 == 1 and innerEnd(t, line[1], line[2]) then
              na, ax, ay = attach(line[1], line[2], R.TRACK_WALK_JOIN, ownWalk(line[1], line[2]))
            else
              na, ax, ay = attach(line[1], line[2], s0 == 1 and endSnap or crossYd + 1)
            end
            if na then line[1], line[2] = ax, ay
            else na = newNode(line[1], line[2], heightAt(line[1], line[2]), floorAt(line[1], line[2])) end
            if fl then fl.landOK, fl.at = s1 == M, dz[s1] end
            local nb, bx, by
            if s1 == M and innerEnd(t, line[#line - 1], line[#line]) then
              nb, bx, by = attach(line[#line - 1], line[#line], R.TRACK_WALK_JOIN, ownWalk(line[#line - 1], line[#line]))
            else
              nb, bx, by = attach(line[#line - 1], line[#line], s1 == M and endSnap or crossYd + 1)
            end
            if nb then line[#line - 1], line[#line] = bx, by
            else nb = newNode(line[#line - 1], line[#line], heightAt(line[#line - 1], line[#line]),
              floorAt(line[#line - 1], line[#line])) end
            if fl then fl.landOK, fl.at = nil, nil end
            lastNb, lastX, lastY = nb, line[#line - 1], line[#line]
            if na ~= nb then
              -- (a stair drawn with the stairs tool: a stairs road, source 6, as the data's: "Take the stairs up", their icon)
              -- (a shipped one: as the data's drawn roads, source 2)
              -- (a lift edited so: a lift road, source 5, its length the ride: "Take the lift up", as Thunder Bluff's)
              local ed = MakeEdge(na, nb, line, t.stair and R.SOURCE_STAIR or t.kind == "lift" and R.SOURCE_LIFT
                or t.shipped and 2 or R.SOURCE_RECORDED)
              markCave(ed, line)
              if t.kind then kindOf[ed] = t.kind end
              if tzs then floored[ed] = true end
              if isRaised then
                raised[ed] = t
                if s0 == 1 then raisedEnd[na] = true else raisedNode[na] = true end
                if s1 == M then raisedEnd[nb] = true else raisedNode[nb] = true end
              end
              local mk = math.floor(#line / 4) * 2 + 1
              if nzs and fl and fl.zs and ns.Nav and ns.Nav.InBuilding and ns.Nav.InBuilding(cont, line[mk], line[mk + 1], "joined") then
                inside[ed] = true
              end
              e[#e + 1] = ed
              put(ed, #e)
              mine[ed] = true
              walkOf[ed] = curWalk
              joined[na], joined[nb] = true, true
            end
          end
          s0 = s1
        end
        -- the replaced road's cut ends (and roads that met it there) join the drawn one
        -- (only those left a dead end: a road still going through a node needs nothing)
        for _, ce in ipairs(cutEnds) do
          if not joined[ce[1]] and degree(ce[1], ce[2], ce[3], mine) == 1 then
            joined[ce[1]] = true
            -- (onto the drawn road at the cut end's own height: Stormwind's Wizard's Sanctum, 2026-11-17, a street's
            -- end cut at the spiral's foot was joined up onto the turn over it, 22 yd up, and the route skipped the
            -- spiral the player walked)
            local cz = (zs and zs[ce[1]]) or (nzs and nzs[ce[1]])
            if fl and cz then fl.at = cz end
            local nm, mx, my = attach(ce[2], ce[3], over + 4, mine)
            if fl then fl.at = nil end
            if nm and nm ~= ce[1] then
              -- (a shipped one's: shipped too, source 2, as its own pieces)
              local ed = MakeEdge(ce[1], nm, { ce[2], ce[3], mx, my }, t.shipped and 2 or R.SOURCE_RECORDED)
              markCave(ed, { ce[2], ce[3], mx, my })
              e[#e + 1] = ed
              put(ed, #e)
              mine[ed] = true
            end
          end
        end
      end
    end
  end
  -- safe jumps off the raised roads (R.TRACK_DROP_MAX): one way down onto a road under one with a known height
  if #raisedTracks > 0 and dropOf and (nzs or zs) then
    curAdd, fl = false, nil
    local hz = nzs or zs
    local reach = R.TRACK_DROP_REACH
    local pick = {} -- [track] = { [lower road] = best spot }
    local tops, lows = {}, {}
    for _, ed in ipairs(e) do
      local t = raised[ed]
      if t then
        tops[ed] = true
        local m = math.max(2, math.floor(ed[3] / R.TRACK_DROP_STEP))
        for k = 1, m - 1 do
          local al = ed[3] * k / m
          -- (the spot `al` yards along)
          local x, y, acc = ed[5], ed[6], 0
          for i = 5, #ed - 3, 2 do
            local L = math.sqrt((ed[i + 2] - ed[i]) ^ 2 + (ed[i + 3] - ed[i + 1]) ^ 2)
            if acc + L >= al then
              local f = L > 0 and (al - acc) / L or 0
              x, y = ed[i] + (ed[i + 2] - ed[i]) * f, ed[i + 1] + (ed[i + 3] - ed[i + 1]) * f
              break
            end
            acc = acc + L
          end
          local top = HeightOn(hz, ed, al)
          for _, o in ipairs(top and near(x - reach, x + reach, y - reach, y + reach) or {}) do
            if o ~= ed and raised[o] ~= t and o[4] ~= 3 and o[4] ~= R.SOURCE_SWIM and hz[o[1]] and hz[o[2]]
                and o[1] ~= ed[1] and o[1] ~= ed[2] and o[2] ~= ed[1] and o[2] ~= ed[2] then
              local d2, oal, qx, qy = Closest(o, x, y)
              local low = d2 and d2 <= reach * reach and HeightOn(hz, o, oal)
              local dz = low and top - low
              if dz and dz > R.LAYER_Z and dz <= R.TRACK_DROP_MAX then
                pick[t] = pick[t] or {}
                local b = pick[t][o]
                if not b or d2 < b.d2 then pick[t][o] = { d2 = d2, x = x, y = y, qx = qx, qy = qy, dz = dz } end
              end
            end
          end
        end
      end
    end
    for _, rt in ipairs(raisedTracks) do
      local list = {}
      for o, b in pairs(pick[rt.t] or {}) do
        lows[o] = true
        list[#list + 1] = b
      end
      table.sort(list, function(a, b) return a.d2 < b.d2 or (a.d2 == b.d2 and (a.x < b.x or (a.x == b.x and a.y < b.y))) end)
      for _, b in ipairs(list) do
        tick(20)
        local na, ax, ay = attach(b.x, b.y, 0.5, tops)
        local nb, bx, by = attach(b.qx, b.qy, 0.5, lows)
        if na and nb and na ~= nb then
          raisedNode[na] = raisedEnd[na] == nil or nil
          local ed = MakeEdge(na, nb, { ax, ay, bx, by }, 3)
          dropOf[ed] = b.dz
          e[#e + 1] = ed
          put(ed, #e)
        end
      end
    end
  end
  -- dead-end stubs the cuts left (a road cut short beside a drawn one) go
  -- (only the cut nodes' degrees, and a new list only when a stub goes: a table over every node of the continent, made
  -- three times, was most of a 12 ms stretch of the background build with the collector's work, issue #657)
  if next(cutNodes) then
    for _ = 1, 3 do
      local deg = {}
      for _, ed in ipairs(e) do
        tick(2000)
        local a, b = ed[1], ed[2]
        if cutNodes[a] then deg[a] = (deg[a] or 0) + 1 end
        if cutNodes[b] then deg[b] = (deg[b] or 0) + 1 end
      end
      local function isStub(ed)
        return ed[3] < R.TRACK_STUB and ((cutNodes[ed[1]] and deg[ed[1]] == 1) or (cutNodes[ed[2]] and deg[ed[2]] == 1))
      end
      local first
      for k, ed in ipairs(e) do
        tick(2000)
        if isStub(ed) then first = k break end
      end
      if not first then break end
      local kept = {}
      for k = 1, first - 1 do kept[k] = e[k] end
      for k = first, #e do
        tick(2000)
        local ed = e[k]
        if not isStub(ed) then kept[#kept + 1] = ed end
      end
      e = kept
    end
  end
  local info
  if next(kindOf) or next(raisedNode) or next(floored) then
    info = { kind = kindOf, raised = {}, raisedNode = raisedNode, raisedEnd = raisedEnd, floored = floored }
    for ed in pairs(raised) do info.raised[ed] = true end
  end
  return n, e, zs or roads.z, nzs or roads.nz, inside, info
end

-- The extracted road network comes in pieces (roads the extraction lost, gates, towns).
-- Inside a background job (a coroutine run by R.Pump): hand control back every `every`
-- steps, so building the road data for a continent doesn't stall a frame.
local function CanYield()
  local co, main = coroutine.running()
  return co ~= nil and not main
end
-- (and by the clock, issue #841: R.Pump's slice's end, `slice`; a loop's steps can cost far more than its `every`
-- guessed (Bridges' 40 nodes in a city's crowded buckets were 13 ms here, 88 ms live, and the stutter watch paused
-- routing): the clock is looked at every `every` / BREATHE_CLOCK_SHARE steps, and past the slice's end it pauses then)
R.BREATHE_CLOCK_SHARE = 40
R.CLOCK_PAUSES = true -- (off: by the counts alone, as before; tests that count the work by its pauses, or by clock calls)
local slice = {} -- { stop = ms, now = fn } while R.Pump runs a job
local function SliceOver()
  local stop = slice.stop
  return stop ~= nil and slice.now() >= stop
end
local function Breathe(i, every)
  if i % every == 0 then
    if CanYield() then coroutine.yield() end
    return
  end
  if slice.stop then
    local step = every > R.BREATHE_CLOCK_SHARE and math.floor(every / R.BREATHE_CLOCK_SHARE) or 1
    if i % step == 0 and SliceOver() and CanYield() then coroutine.yield() end
  end
end
-- By the clock alone, every `step` calls: no pause unless the slice has run out (loops whose pauses by a count would
-- change how often a job is resumed, which some tests count).
local function BreatheIfOver(i, step)
  if slice.stop and i % step == 0 and SliceOver() and CanYield() then coroutine.yield() end
end
-- Whether a slice of the background work (R.Pump's) has run past its end: loops elsewhere that yield by a count of
-- their own (Passability's searches) pause at once then too.
function R.SliceOver() return SliceOver() and CanYield() end
R.KEEP_BREATHE = 1000 -- (the road network's copies: values copied between pauses)

-- table.sort(t, function(x, y) return x[1] < y[1] end), pausing by the clock (BreatheIfOver) in a background job: a
-- sort can't pause, and Bridges' 3,600 pairs were 1.8 ms here in one go, the slow-client test's worst slice on the CI
-- runner (issue #841). Lua 5.1's own sort (ltablib.c's auxsort) step for step, so the order, ties too, is the
-- game's table.sort's and routes don't change.
R.SORT_BREATHE = 64 -- (comparisons between looks at the clock)
function R.SortByFirst(t)
  local n = 0
  local function lt(a, b)
    n = n + 1
    BreatheIfOver(n, R.SORT_BREATHE)
    return a[1] < b[1]
  end
  local function aux(l, u)
    while l < u do
      if lt(t[u], t[l]) then t[l], t[u] = t[u], t[l] end
      if u - l == 1 then break end
      local i = math.floor((l + u) / 2)
      if lt(t[i], t[l]) then
        t[i], t[l] = t[l], t[i]
      elseif lt(t[u], t[i]) then
        t[i], t[u] = t[u], t[i]
      end
      if u - l == 2 then break end
      local p = t[i]
      t[i], t[u - 1] = t[u - 1], p
      local j
      i, j = l, u - 1
      while true do
        i = i + 1
        while lt(t[i], p) do i = i + 1 end
        j = j - 1
        while lt(p, t[j]) do j = j - 1 end
        if j < i then break end
        t[i], t[j] = t[j], t[i]
      end
      t[u - 1], t[i] = t[i], t[u - 1]
      if i - l < u - i then
        j, i, l = l, i - 1, i + 1
      else
        j, i, u = i + 1, u, i - 1
      end
      aux(j, i)
    end
  end
  aux(1, #t)
  return t
end

-- Links between pieces, so a route can go on along roads instead of giving up: the
-- closest node pair between pieces, Kruskal style until every piece is joined, plus every
-- pair of nodes on different pieces closer than BRIDGE_SHORT. { [node] = { { m, yards } } }
R.BRIDGE_SHORT = 200
R.BRIDGE_SHORT_CITY = 40 -- ... up to this inside a city's ruins up top (walls: links through them are no use)
R.BRIDGE_MAX_PER_NODE = 6 -- the short links kept per node (the nearest)
R.BRIDGE_BUCKET = 250 -- yards: gap links are looked for in the buckets around a node
R.JUMP_YD = 400 -- a link between road pieces longer than this with no walk around it: a jump, routed round
R.JUMP_RUN_YD = 200 -- ... and with this much blocked ground in one go on its line (the trip sweep's WALLCUT_YD)
R.BRIDGE_FAR_EXTRA = 3 -- far links kept per group of pieces besides the one that joins it (its nearest)
R.BRIDGE_FAR_EXTRA_YD = 3000 -- ... no longer than this
R.BRIDGE_FAR_ALTS = 4 -- ... and between two groups, from this many places of the smaller one
R.BRIDGE_SAMPLE = 60 -- nodes per group of pieces tried when joining groups far apart
R.BRIDGE_SAMPLE_YD = 250 -- ... about that many, a node per square these yards wide or a multiple (by place)
-- (between two nodes with floors on a continent, `nz`: a capital's, a building's, a drawn road's with its heights, only
-- when about as near in height as a walk that long can climb: LAYER_Z and this a yard. Stormwind's Wizard's Sanctum,
-- 2026-11-17: the trainers' room under the city, 76 yd down, was linked to the tower's stairs and the street over it)
R.BRIDGE_FLOOR_SLOPE = 1
local function FloorsNear(nz, a, b, d2)
  local za, zb = nz and nz[a], nz and nz[b]
  return not (za and zb) or math.abs(za - zb) <= R.LAYER_Z + math.sqrt(d2) * R.BRIDGE_FLOOR_SLOPE
end
-- `short`: the short links' reach (0 for none: a city's own level, joined by its stairs);
-- `nearOverlay(x, y)`: whether a spot is inside a city's ruins (short links shorter there);
-- `skip[n]`: nodes left out (true: inside a cave, joined to the rest by its way out), or
-- only in short links ("short": a cave's mouth, not a way to join pieces of road up).
local function Bridges(nodes, adj, short, nearOverlay, skip, zs, nz)
  -- (roads with heights, a dungeon's floors: only between roads on about the same floor)
  local function zok(a, b)
    return not zs or not zs[a] or not zs[b] or math.abs(zs[a] - zs[b]) <= R.LAYER_Z
  end
  local parent = {}
  local function find(a)
    local r = a
    while parent[r] ~= r do r = parent[r] end
    while parent[a] ~= r do parent[a], a = r, parent[a] end
    return r
  end
  -- (in a background job: pauses while the pieces are worked out too; all of Kalimdor's nodes in one go were a
  -- 40 ms slice on the CI runner)
  local list = {}
  for n in pairs(adj) do
    parent[n] = n
    list[#list + 1] = n
    Breathe(#list, 2000)
  end
  table.sort(list)
  local seen = 0
  for n, links in pairs(adj) do
    seen = seen + 1
    Breathe(seen, 1000)
    for _, l in ipairs(links) do
      local a, b = find(n), find(l[1])
      if a ~= b then parent[a] = b end
    end
  end
  local piece = {}
  for i, n in ipairs(list) do
    Breathe(i, 2000)
    piece[n] = find(n)
  end
  if skip and next(skip) then
    local kept = {}
    for _, n in ipairs(list) do
      if skip[n] ~= true then kept[#kept + 1] = n end
    end
    list = kept
  end
  local shortOnly = skip or {}
  -- closest pair per two pieces, and the short pairs: each node against the nodes in the
  -- buckets around it (a bucket at least a short link wide, so none is missed)
  local best, links = {}, {} -- best[pa][pb] (pa < pb) = { d2, a, b }
  short = short or R.BRIDGE_SHORT
  local short2 = short * short
  local city2 = R.BRIDGE_SHORT_CITY * R.BRIDGE_SHORT_CITY
  local B = math.max(short, R.BRIDGE_BUCKET)
  local buckets = {}
  for i, n in ipairs(list) do
    Breathe(i, 2000)
    local k = math.floor(nodes[n * 2 - 1] / B) * 65536 + math.floor(nodes[n * 2] / B)
    local bk = buckets[k]
    if not bk then
      bk = {}
      buckets[k] = bk
    end
    bk[#bk + 1] = n
  end
  local function consider(a, b, ax, ay, pa)
    local pb = piece[b]
    if pa == pb or not zok(a, b) then return end
    local dx, dy = nodes[b * 2 - 1] - ax, nodes[b * 2] - ay
    local d2 = dx * dx + dy * dy
    if not FloorsNear(nz, a, b, d2) then return end
    local lo, hi = pa, pb
    if lo > hi then lo, hi = hi, lo end
    local row = best[lo]
    if not row then
      row = {}
      best[lo] = row
    end
    local cur = row[hi]
    if shortOnly[a] or shortOnly[b] then -- (a cave's mouth: no joining link)
    elseif not cur then
      row[hi] = { d2, a, b }
    elseif d2 < cur[1] then
      cur[1], cur[2], cur[3] = d2, a, b
    end
    if d2 <= short2 and (d2 <= city2 or not nearOverlay
        or not (nearOverlay(ax, ay) or nearOverlay(nodes[b * 2 - 1], nodes[b * 2]))) then
      links[#links + 1] = { math.sqrt(d2), a, b }
    end
  end
  for i = 1, #list do
    Breathe(i, 40)
    local a = list[i]
    local ax, ay, pa = nodes[a * 2 - 1], nodes[a * 2], piece[a]
    local bx, by = math.floor(ax / B), math.floor(ay / B)
    for kx = bx - 1, bx + 1 do
      for ky = by - 1, by + 1 do
        for _, b in ipairs(buckets[kx * 65536 + ky] or EMPTY) do
          if b > a then consider(a, b, ax, ay, pa) end
        end
      end
    end
  end
  local pairsByDist = {}
  local tick = 0 -- (the loops below, a pause now and then: Breathe by the clock)
  for lo, row in pairs(best) do
    tick = tick + 1
    Breathe(tick, 2000)
    for hi, p in pairs(row) do pairsByDist[#pairsByDist + 1] = { math.sqrt(p[1]), p[2], p[3], lo, hi } end
  end
  R.SortByFirst(pairsByDist)
  local joined = {}
  local function jfind(a)
    while joined[a] and joined[a] ~= a do a = joined[a] end
    return a
  end
  -- (every joining link kept, a short one too: as one of the nearest few per node it was dropped
  -- where a node had BRIDGE_MAX_PER_NODE shorter ones, a cave mouth's, and the pieces it alone
  -- joined were cut off: the Wetlands from Dun Algaz once a road drawn there was shipped, 2026-10-01)
  local kept = {}
  local function join(p)
    local a, b = jfind(p[4]), jfind(p[5])
    if a ~= b then
      joined[a] = b
      links[#links + 1] = { p[1], p[2], p[3], keep = true }
      kept[math.min(p[2], p[3]) * 1048576 + math.max(p[2], p[3])] = true
    end
  end
  for i, p in ipairs(pairsByDist) do
    Breathe(i, 2000)
    join(p)
  end
  -- groups of pieces still apart (farther than the buckets reach): joined by their closest
  -- pair among up to BRIDGE_SAMPLE of each group's nodes
  local groups, order = {}, {}
  for i, n in ipairs(list) do
    Breathe(i, 2000)
    if not shortOnly[n] then
      local gr = jfind(piece[n])
      if not groups[gr] then
        groups[gr] = {}
        order[#order + 1] = gr
      end
      local g = groups[gr]
      g[#g + 1] = n
    end
  end
  if #order > 1 then
    -- (a group's sample by place, not by node number: a node per square, the one nearest its middle,
    -- the squares sized from the group's extent in whole BRIDGE_SAMPLE_YD steps; so roads edited in one
    -- city don't renumber another's sample, and its far links, across the continent)
    local samples = {}
    for gi, gr in ipairs(order) do
      BreatheIfOver(gi, 1)
      local g = groups[gr]
      local x0, x1, y0, y1 = math.huge, -math.huge, math.huge, -math.huge
      for _, n in ipairs(g) do
        local x, y = nodes[n * 2 - 1], nodes[n * 2]
        x0, x1, y0, y1 = math.min(x0, x), math.max(x1, x), math.min(y0, y), math.max(y1, y)
      end
      local span = math.max(x1 - x0, y1 - y0) / math.sqrt(R.BRIDGE_SAMPLE)
      local cell = math.max(1, math.ceil(span / R.BRIDGE_SAMPLE_YD)) * R.BRIDGE_SAMPLE_YD
      local rep = {}
      for _, n in ipairs(g) do
        local x, y = nodes[n * 2 - 1], nodes[n * 2]
        local cx, cy = math.floor(x / cell), math.floor(y / cell)
        local mx, my = (cx + 0.5) * cell, (cy + 0.5) * cell
        local d = (x - mx) ^ 2 + (y - my) ^ 2
        local k = cx * 65536 + cy
        local r = rep[k]
        if not r or d < r[2] then rep[k] = { n, d } end
      end
      local sm = {}
      for _, r in pairs(rep) do sm[#sm + 1] = r[1] end
      table.sort(sm)
      samples[gi] = sm
    end
    local far = {}
    for gi = 1, #order do
      Breathe(gi, 2)
      for gj = gi + 1, #order do
        local bd, ba, bb
        -- (and from each sampled node of the group with fewer of them, its own nearest: `alts`, the few shortest,
        -- for the extra links below: a short road's two ends, one of them maybe the open side)
        local sa, sb = samples[gi], samples[gj]
        if #sb < #sa then sa, sb = sb, sa end
        local alts = {}
        for _, a in ipairs(sa) do
          local ax, ay = nodes[a * 2 - 1], nodes[a * 2]
          local ad, ab
          for _, b in ipairs(sb) do
            local dx, dy = nodes[b * 2 - 1] - ax, nodes[b * 2] - ay
            local d2 = dx * dx + dy * dy
            if (not ad or d2 < ad) and zok(a, b) then ad, ab = d2, b end
          end
          if ad then
            if not bd or ad < bd then bd, ba, bb = ad, a, ab end
            if ad <= R.BRIDGE_FAR_EXTRA_YD * R.BRIDGE_FAR_EXTRA_YD then alts[#alts + 1] = { ad, a, ab } end
          end
        end
        if bd then
          table.sort(alts, function(x, y) return x[1] < y[1] or (x[1] == y[1] and x[2] < y[2]) end)
          far[#far + 1] = { math.sqrt(bd), ba, bb, order[gi], order[gj], alts = alts }
        end
      end
    end
    R.SortByFirst(far)
    for _, p in ipairs(far) do join(p) end
    -- (and each group's nearest few such links whether they join anything or not: with the one joining link alone,
    -- a group whose nearest neighbor lies over a cliff had only that way in. Un'Goro's roads were joined to
    -- Thousand Needles' over the crater's wall, 1,192 yd no walk goes, and routes from Tanaris went back north to
    -- jump it, the pass from Tanaris never tried: seen in game 2026-11-10. The route takes one only over ground a
    -- walk crosses, `extra`, and only when it's worked out again round a jump: RouteOne's `withExtras`.)
    local extra, extraKept = {}, {}
    for _, p in ipairs(far) do
      local ga, gb = p[4], p[5]
      if p[1] <= R.BRIDGE_FAR_EXTRA_YD and ((extra[ga] or 0) < R.BRIDGE_FAR_EXTRA or (extra[gb] or 0) < R.BRIDGE_FAR_EXTRA) then
        extra[ga], extra[gb] = (extra[ga] or 0) + 1, (extra[gb] or 0) + 1
        for i = 1, math.min(#p.alts, R.BRIDGE_FAR_ALTS) do
          local alt = p.alts[i]
          local k = math.min(alt[2], alt[3]) * 1048576 + math.max(alt[2], alt[3])
          -- (a set of their own: `kept` drops a pair's short link for its joining copy, and an extra one is no
          -- link at all in most routes)
          if not kept[k] and not extraKept[k] then
            extraKept[k] = true
            links[#links + 1] = { math.sqrt(alt[1]), alt[2], alt[3], keep = true, extra = true }
          end
        end
      end
    end
  end
  -- the nearest few short links per node (and every joining one)
  R.SortByFirst(links)
  local out, count = {}, {}
  for i, l in ipairs(links) do
    Breathe(i, 2000)
    local d, a, b = l[1], l[2], l[3]
    if l.keep or (not kept[math.min(a, b) * 1048576 + math.max(a, b)] -- (that pair's kept copy instead)
        and (count[a] or 0) < R.BRIDGE_MAX_PER_NODE and (count[b] or 0) < R.BRIDGE_MAX_PER_NODE) then
      -- (an extra far link takes no node's place among its nearest few: the links every route has, as they were)
      if not l.extra then count[a], count[b] = (count[a] or 0) + 1, (count[b] or 0) + 1 end
      out[a] = out[a] or {}
      out[b] = out[b] or {}
      -- (`extra`: one of a group's other far links, a way only over ground a walk crosses; never a jump)
      out[a][#out[a] + 1] = { b, d, extra = l.extra }
      out[b][#out[b] + 1] = { a, d, extra = l.extra }
    end
  end
  return out
end

-- A road's loose end linked to the roads near it that are far along the roads (issue #411: Thunder Bluff to Camp
-- Gev'rek's zeppelin, 2026-11-15. The road up the gap north of the Wildmane Water Well to Gev'rek ends in the gap,
-- 600 yd over the plains from Thunder Bluff's roads, but it's on the same network by the Barrens: no gap link, those
-- join pieces only, and a walk 9.4k yd round). Each node with one road from it, a drawn road's (DEAD_END_SOURCES), the
-- nearest DEAD_END_LINKS nodes within DEAD_END_LINK_YD whose way along the roads is over DEAD_END_ROAD_FACTOR times the
-- straight line (or none): links added to `bridges` (`deadEnd`), priced by the ground or, blocked straight, by its walk
-- round (none: shut). Taken only in a route worked out again for a long way round, R.DeadEndsAgain: on every link
-- in every route, 22 of route-quality's 200 sample trips weighed worse.
R.DEAD_END_LINK_YD = 700
R.DEAD_END_LINKS = 2
R.DEAD_END_ROAD_FACTOR = 2.5
R.DEAD_END_SOURCES = { [2] = true, [9] = true } -- (the shipped drawn roads, and the player's own: R.SOURCE_RECORDED)
-- (and the nearest not up or down a cliff first, `cliff(n, m)` (Passability.CliffAlong), of the nearest
-- DEAD_END_CLIFF_TRIES; those over one only when too few aren't. The gap road's end by the Wildmane Water Well had its
-- two links up the ridges over it, a walk none; its way from Thunder Bluff was the jump off the mesa's east side, 100
-- yd down (Kooki3z 2026-11-20, Freewind Post: "not a safe path down"). Mulgore's roads 530 yd off are walked to)
R.DEAD_END_CLIFF_TRIES = 16
function R.DeadEndLinks(nodes, adj, bridges, skip, nearOverlay, zs, edges, nz, cliff)
  local B = R.DEAD_END_LINK_YD
  local function zok(a, b)
    return not zs or not zs[a] or not zs[b] or math.abs(zs[a] - zs[b]) <= R.LAYER_Z
  end
  local buckets, i = {}, 0
  for n in pairs(adj) do
    i = i + 1
    Breathe(i, 2000)
    if not (skip and skip[n]) then
      local k = math.floor(nodes[n * 2 - 1] / B) * 65536 + math.floor(nodes[n * 2] / B)
      local bk = buckets[k]
      if not bk then
        bk = {}
        buckets[k] = bk
      end
      bk[#bk + 1] = n
    end
  end
  local ends = {}
  i = 0
  for n, links in pairs(adj) do
    i = i + 1
    Breathe(i, 2000)
    local e = #links == 1 and edges and edges[links[1][3]]
    if e and R.DEAD_END_SOURCES[e[4]] and not (skip and skip[n])
        and not (nearOverlay and nearOverlay(nodes[n * 2 - 1], nodes[n * 2])) then
      ends[#ends + 1] = n
    end
  end
  table.sort(ends)
  local B2 = B * B
  for k, n in ipairs(ends) do
    Breathe(k, 20)
    local x, y = nodes[n * 2 - 1], nodes[n * 2]
    -- the roads' yards from it, out to the farthest that could count (a small Dijkstra)
    local limit = B * R.DEAD_END_ROAD_FACTOR
    local dist, done, open, pops = { [n] = 0 }, {}, { n }, 0
    while #open > 0 do
      pops = pops + 1
      Breathe(pops, 100)
      local bi = 1
      for j = 2, #open do if dist[open[j]] < dist[open[bi]] then bi = j end end
      local a = table.remove(open, bi)
      if not done[a] then
        done[a] = true
        for _, l in ipairs(adj[a] or EMPTY) do
          local b, d = l[1], dist[a] + l[2]
          if d <= limit and (dist[b] == nil or d < dist[b]) then
            dist[b] = d
            open[#open + 1] = b
          end
        end
      end
    end
    local near = {}
    local bx, by = math.floor(x / B), math.floor(y / B)
    for kx = bx - 1, bx + 1 do
      for ky = by - 1, by + 1 do
        for _, m in ipairs(buckets[kx * 65536 + ky] or EMPTY) do
          local dx, dy = nodes[m * 2 - 1] - x, nodes[m * 2] - y
          local d2 = dx * dx + dy * dy
          if m ~= n and d2 <= B2 and zok(n, m) and FloorsNear(nz, n, m, d2) then
            local d = math.sqrt(d2)
            if not dist[m] or dist[m] > d * R.DEAD_END_ROAD_FACTOR then near[#near + 1] = { d, m } end
          end
        end
      end
    end
    table.sort(near, function(a, b) return a[1] < b[1] end)
    if cliff and #near > R.DEAD_END_LINKS then
      local ok, over = {}, {}
      for j, c in ipairs(near) do
        if j > R.DEAD_END_CLIFF_TRIES or not (cliff(n, c[2]) or cliff(c[2], n)) then ok[#ok + 1] = c else over[#over + 1] = c end
        if #ok >= R.DEAD_END_LINKS then break end
      end
      for _, c in ipairs(over) do ok[#ok + 1] = c end
      near = ok
    end
    for j = 1, math.min(#near, R.DEAD_END_LINKS) do
      local d, m = near[j][1], near[j][2]
      local have = false
      for _, l in ipairs(bridges[n] or EMPTY) do if l[1] == m then have = true end end
      if not have then
        bridges[n] = bridges[n] or {}
        bridges[m] = bridges[m] or {}
        bridges[n][#bridges[n] + 1] = { m, d, deadEnd = true }
        bridges[m][#bridges[m] + 1] = { n, d, deadEnd = true }
      end
    end
  end
  return bridges
end

-- A cave's roads in pieces, joined (asked 2026-11-16: Kharanos to the Wetlands went round by the South Gate Pass, 3,400
-- yd, and the player drew a road through the North Gate Pass instead: its tunnel's roads in Data/Caves.lua are two
-- pieces, one from each mouth, 17 yd apart behind a sliver of rock its grid closes in the passage, and a cave's nodes
-- get no gap links, Bridges' `skip`). A dead end of a cave's road is linked to the nearest dead end of another piece of
-- the caves' roads (neither with a height, `nz`) within CAVE_JOIN_YD, the roads between them CAVE_JOIN_ROAD_FACTOR times
-- longer or more, along a walk over the grids up to CAVE_JOIN_WALK_FACTOR times as long and CAVE_JOIN_WALK_EXTRA yards
-- more (round the sliver: the North Gate's is 19 yd for 18; through a wall there's none). The caves' nodes are `base` + 1 on, `e` every road (the land's, theirs, their ways
-- out). The links made (indices into `e`), cave roads too.
R.CAVE_JOIN_YD = 25
R.CAVE_JOIN_WALK_FACTOR, R.CAVE_JOIN_WALK_EXTRA = 2, 10 -- ... and a walk over the grids between them this short
R.CAVE_JOIN_CORNER_YD = 6 -- ... on the cave's own cells all the way, at most this many of them closed (a corner cut)
R.CAVE_JOIN_ROAD_FACTOR = 4 -- ... and only where the roads between them are longer than this many times the link
R.CAVE_JOIN_REACH_PAD = 10 -- yards: the roads round the ends looked at that far past where those could reach
local CAVE_CELL = 128
function R.JoinCavePieces(cont, n, e, base, nz)
  local P = ns.Passability
  if not (P and P.FindPath and P.OverlayRaw) then return {} end
  -- (a walk on a cave's own floor all the way, its open cells or its floor under walkable ground: not out over the
  -- land at a mouth, nor up over the hill a mine is under, the continent's grid there; Durotar's cave by Razor Hill,
  -- whose route went out of it and in again by a link like that)
  -- (its walk smoothed into lines may cut a corner of the cave's closed cells: CAVE_JOIN_CORNER_YD of them at most)
  local function onFloor(x, y, pts)
    local px, py, shut = x, y, 0
    for i = 1, #pts - 1, 2 do
      local qx, qy = pts[i], pts[i + 1]
      local d = math.sqrt((qx - px) ^ 2 + (qy - py) ^ 2)
      local steps = math.max(1, math.ceil(d))
      for k = 0, steps do
        local v, o = P.OverlayRaw(cont, px + (qx - px) * k / steps, py + (qy - py) * k / steps)
        if not (o and o.cave and (v == 0 or v == 2 or v == 3)) then return false end
        if v == 2 and k > 0 then shut = shut + d / steps end
      end
      px, py = qx, qy
    end
    return shut <= R.CAVE_JOIN_CORNER_YD
  end
  -- (the caves' nodes' roads counted only: the ends looked for are theirs)
  local deg = {}
  for k = 1, #e do
    Breathe(k, 2000)
    local a, b = e[k][1], e[k][2]
    if a > base then deg[a] = (deg[a] or 0) + 1 end
    if b > base then deg[b] = (deg[b] or 0) + 1 end
  end
  -- (dead ends of the caves' roads, with no height: floors over floors keep their own roads, layers.py's)
  local function loose(nd)
    return nd > base and deg[nd] == 1 and not (nz and nz[nd - base] and nz[nd - base] ~= 0)
  end
  local B = R.CAVE_JOIN_YD
  local buckets, ends = {}, {}
  for nd = base + 1, #n / 2 do
    if loose(nd) then
      ends[#ends + 1] = nd
      local key = math.floor(n[nd * 2 - 1] / B) * 65536 + math.floor(n[nd * 2] / B)
      buckets[key] = buckets[key] or {}
      buckets[key][#buckets[key] + 1] = nd
    end
  end
  -- The roads by their ends (flat: { node, yards, node, yards, ... } a node), only round the ends: `near` goes no
  -- further along them than CAVE_JOIN_ROAD_FACTOR times a link under CAVE_JOIN_YD, and a road is never shorter than
  -- the line between its ends. (Every road of the continent, two tables each, were most of the garbage of the
  -- background build and its collector's 10 ms steps, issue #657.)
  local reach = B * R.CAVE_JOIN_ROAD_FACTOR + 1 + R.CAVE_JOIN_REACH_PAD
  local cells = {}
  for _, nd in ipairs(ends) do
    local x, y = n[nd * 2 - 1], n[nd * 2]
    for kx = math.floor((x - reach) / CAVE_CELL), math.floor((x + reach) / CAVE_CELL) do
      for ky = math.floor((y - reach) / CAVE_CELL), math.floor((y + reach) / CAVE_CELL) do
        cells[kx * 65536 + ky] = true
      end
    end
  end
  local function inCells(nd)
    return cells[math.floor(n[nd * 2 - 1] / CAVE_CELL) * 65536 + math.floor(n[nd * 2] / CAVE_CELL)]
  end
  local adj = {}
  local function link(a, b, len)
    local l = adj[a]
    if not l then
      l = {}
      adj[a] = l
    end
    l[#l + 1], l[#l + 2] = b, len
  end
  if #ends > 0 then
    for k = 1, #e do
      Breathe(k, 2000)
      local a, b = e[k][1], e[k][2]
      if inCells(a) or inCells(b) then
        local len = e[k][3] or 0
        link(a, b, len)
        link(b, a, len)
      end
    end
  end
  -- (the roads' yards from `a`, up to `limit`: a small Dijkstra; whether `b` is reached)
  local function near(a, b, limit)
    local dist, done, open = { [a] = 0 }, {}, { a }
    while #open > 0 do
      local bi = 1
      for j = 2, #open do if dist[open[j]] < dist[open[bi]] then bi = j end end
      local x = table.remove(open, bi)
      if x == b then return true end
      if not done[x] then
        done[x] = true
        local l = adj[x] or EMPTY
        for i = 1, #l - 1, 2 do
          local y, d = l[i], dist[x] + l[i + 1]
          if d <= limit and (dist[y] == nil or d < dist[y]) then
            dist[y] = d
            open[#open + 1] = y
          end
        end
      end
    end
    return false
  end
  local made, linked = {}, {}
  -- (pauses at every other end, and after each walk tried: 20 ends between pauses, each with its walks over the grids,
  -- were 13 ms slices of the warm-up after a login; with G-Sync and V-Sync off a frame that long tears, issue #548)
  for k, nd in ipairs(ends) do
    Breathe(k, 2)
    local x, y = n[nd * 2 - 1], n[nd * 2]
    local best, bd, bpts = nil, B, nil
    local bx, by = math.floor(x / B), math.floor(y / B)
    for kx = bx - 1, bx + 1 do
      for ky = by - 1, by + 1 do
        for _, m in ipairs(buckets[kx * 65536 + ky] or EMPTY) do
          if m ~= nd and not linked[m] then
            local d = math.sqrt((n[m * 2 - 1] - x) ^ 2 + (n[m * 2] - y) ^ 2)
            if d < bd and not near(nd, m, d * R.CAVE_JOIN_ROAD_FACTOR + 1) then
              -- (a walk over the grids, round the sliver: not through a wall)
              local total, pts = P.FindPath(cont, x, y, n[m * 2 - 1], n[m * 2], true, true)
              Breathe(1, 1)
              if total and pts and total <= d * R.CAVE_JOIN_WALK_FACTOR + R.CAVE_JOIN_WALK_EXTRA and onFloor(x, y, pts) then
                best, bd, bpts = m, d, pts
              end
            end
          end
        end
      end
    end
    if best and not linked[nd] then
      local ed = { nd, best, 0, 0, x, y }
      for i = 3, #bpts - 2 do ed[#ed + 1] = bpts[i] end -- (its walk's corners; the nodes at its ends)
      ed[#ed + 1], ed[#ed + 2] = n[best * 2 - 1], n[best * 2]
      for i = 5, #ed - 3, 2 do ed[3] = ed[3] + math.sqrt((ed[i + 2] - ed[i]) ^ 2 + (ed[i + 3] - ed[i + 1]) ^ 2) end
      e[#e + 1] = ed
      made[#made + 1] = #e
      linked[nd], linked[best] = true, true
      link(nd, best, ed[3])
      link(best, nd, ed[3])
    end
  end
  return made
end

-- The characters of packed road points (Data/Caves.lua): each one's value, 0 to 63.
local PACK = {}
do
  local chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
  for i = 1, #chars do PACK[chars:byte(i)] = i - 1 end
end

-- A road with packed points (e[5] a string: from node a, each point the last one moved by
-- whole yards, two characters each way; see caves.pack_points) as a plain one; `n` its nodes,
-- `base` added to its node numbers.
local function Unpacked(e, n, base)
  base = base or 0
  local c = { e[1] + base, e[2] + base }
  if type(e[5]) ~= "string" then
    for j = 3, #e do c[j] = e[j] end
    return c
  end
  c[3], c[4] = e[3], e[4]
  local x, y = n[e[1] * 2 - 1], n[e[1] * 2]
  c[5], c[6] = x, y
  local s = e[5]
  for i = 1, #s - 3, 4 do
    local b1, b2, b3, b4 = s:byte(i, i + 3)
    x = x + PACK[b1] * 64 + PACK[b2] - 2048
    y = y + PACK[b3] * 64 + PACK[b4] - 2048
    c[#c + 1], c[#c + 2] = x, y
  end
  return c
end

-- Roads drawn in game and shipped (source 2, Data/Roads.lua): a loose end (no other road there) joins the
-- nearest road within TRACK_SNAP, split there, as it did in game before it was in the data (WithTracks);
-- a cave's roads only at a mouth (`mouth[n]`, its "short" nodes: not the cave's roads under the hill),
-- never a drop or a lift. The data's build joins drawn roads to the land's roads only, not to the caves'
-- and capitals' merged in here (Dun Algaz's, drawn between two cave mouths' roads, was a piece of its
-- own, 2026-10-01). `nodes`, `edges` are changed in place; `caveOf`, `dropOf` by edge. Returns the joins.
function R.JoinDrawnEnds(nodes, edges, caveOf, dropOf, mouth, attachedOf)
  local deg, own = {}, {}
  for ei, e in ipairs(edges) do
    Breathe(ei, 2000)
    deg[e[1]] = (deg[e[1]] or 0) + 1
    deg[e[2]] = (deg[e[2]] or 0) + 1
  end
  local B, snap = 64, R.TRACK_SNAP
  local want, ends = {}, {}
  for ei, e in ipairs(edges) do
    Breathe(ei, 2000)
    if e[4] == 2 then
      for k = 1, 2 do
        local j = e[k]
        if deg[j] == 1 and not own[j] then
          own[j] = e
          ends[#ends + 1] = j
          local key = math.floor(nodes[j * 2 - 1] / B) * 65536 + math.floor(nodes[j * 2] / B)
          want[key] = want[key] or {}
          table.insert(want[key], j)
        end
      end
    end
  end
  if #ends == 0 then return 0 end
  local function each(x0, x1, y0, y1, fn)
    for kx = math.floor((x0 - snap) / B), math.floor((x1 + snap) / B) do
      for ky = math.floor((y0 - snap) / B), math.floor((y1 + snap) / B) do
        for _, j in ipairs(want[kx * 65536 + ky] or EMPTY) do fn(j) end
      end
    end
  end
  local best = {} -- [end] = { d2, node } or { d2, edge }
  local mi = 0
  for m, v in pairs(mouth or {}) do
    mi = mi + 1
    Breathe(mi, 500) -- (every cave's and building's node is in `mouth`: a pause now and then)
    if v == "short" then
      local mx, my = nodes[m * 2 - 1], nodes[m * 2]
      each(mx, mx, my, my, function(j)
        local d2 = (nodes[j * 2 - 1] - mx) ^ 2 + (nodes[j * 2] - my) ^ 2
        if d2 <= snap * snap and (not best[j] or d2 < best[j][1]) then best[j] = { d2, m } end
      end)
    end
  end
  for ei, ed in ipairs(edges) do
    Breathe(ei, 50)
    -- (nor onto an attached building's roads, `attachedOf`: a drawn road's end by Splintertree Post's flight master went onto
    -- its hut's, not the road it ends at, and the road east of it was lost, 2026-11-21)
    if not (caveOf and caveOf[ed]) and not (dropOf and dropOf[ed]) and not (attachedOf and attachedOf[ed]) and ed[4] ~= 3 and ed[4] ~= 5 then
      local bb = EdgeBox(ed)
      each(bb[1], bb[2], bb[3], bb[4], function(j)
        if own[j] ~= ed and ed[1] ~= j and ed[2] ~= j then
          local d2 = Closest(ed, nodes[j * 2 - 1], nodes[j * 2])
          if d2 and d2 <= snap * snap and (not best[j] or d2 < best[j][1]) then best[j] = { d2, ed } end
        end
      end)
    end
  end
  -- (one at a time, in node order: a road split for one end may be split again for the next, in its part)
  local index, parts, done = {}, {}, 0
  for i, ed in ipairs(edges) do index[ed] = i end
  table.sort(ends)
  for _, j in ipairs(ends) do
    local b = best[j]
    if b then
      local jx, jy = nodes[j * 2 - 1], nodes[j * 2]
      local to = b[2]
      if type(to) == "table" then
        local pick, bd, bAlong
        for _, p in ipairs(parts[to] or { to }) do
          local d2, along = Closest(p, jx, jy)
          if d2 and (not bd or d2 < bd) then pick, bd, bAlong = p, d2, along end
        end
        if bAlong < 3 then to = pick[1]
        elseif bAlong > pick[3] - 3 then to = pick[2]
        else
          local p1, p2 = SplitPolyline(pick, bAlong)
          nodes[#nodes + 1], nodes[#nodes + 2] = p1[#p1 - 1], p1[#p1]
          local q = #nodes / 2
          local ea, eb = MakeEdge(pick[1], q, p1, pick[4]), MakeEdge(q, pick[2], p2, pick[4])
          local pi = index[pick]
          edges[pi], index[ea], index[pick] = ea, pi, nil
          edges[#edges + 1] = eb
          index[eb] = #edges
          local list = parts[to] or { to }
          for k, p in ipairs(list) do
            if p == pick then table.remove(list, k) break end
          end
          list[#list + 1], list[#list + 2] = ea, eb
          parts[to] = list
          to = q
        end
      end
      edges[#edges + 1] = MakeEdge(j, to, { jx, jy, nodes[to * 2 - 1], nodes[to * 2] }, 2)
      done = done + 1
    end
  end
  return done
end

local BuildGraph
local HostileSide
local mergedRoads = {} -- [cont] = the roads with the overlays merged in (BuildGraph: kept between rebuilds)
-- (the background jobs building a road network now: R.Pump's slices of it are the data built once, as the warm-up's,
-- not routing the player could stop by pausing it; issue #841, R.PumpBuilt)
local building = setmetatable({}, { __mode = "k" })
local function Graph(cont)
  -- (built for the player's faction: its guards' towns cost more; rebuilt if that changes)
  if graphs[cont] and graphs[cont].side ~= HostileSide() then graphs[cont] = nil end
  if graphs[cont] ~= nil then return graphs[cont] or nil end
  local t0 = ns.PerfStart and ns.PerfStart()
  local co, main = coroutine.running()
  if main then co = nil end
  local was = co and building[co]
  if co then building[co] = true end
  local g = BuildGraph(cont)
  if co then building[co] = was end
  if ns.PerfEnd then ns.PerfEnd("router: build roads", t0) end
  return g
end
-- A road query in the frame (not a background job: the floor followed, the roads near, a junction or stairs for the
-- turns) never builds a continent's roads there: it starts the background warm-up (R.WarmUp) and gets none for now,
-- which each copes with. Built at once, right after login with a route restored the arrow's first update (the floor
-- followed: HeightsNear) built Eastern Kingdoms' roads in the frame, a 1.1 s hitch (QA, 2026-10-07).
-- Past the warm-up's wait (R.WARM_WAIT), or with nothing to warm up, built as before.
local function GraphQuery(cont, x, y)
  local g = graphs[cont]
  if (g == nil or (g and g.side ~= HostileSide())) and R.WARM and not R.SYNC_WALKS and not CanYield()
      and R.WarmUp(cont, x, y) then
    return nil
  end
  return Graph(cont)
end
function BuildGraph(cont)
  local roads = ns.Roads and ns.Roads[cont]
  if not roads then
    graphs[cont] = false
    return nil
  end
  if roads.e[1] and type(roads.e[1][5]) == "string" then
    -- (an instance's roads, Data/Instances.lua: packed; unpacked once, in place)
    for i, e in ipairs(roads.e) do roads.e[i] = Unpacked(e, roads.n) end
  end
  local nodes, edges = roads.n, roads.e
  local P0, P1 = ns.PerfStart or function() end, ns.PerfEnd or function() end
  local pt = P0()
  -- drops off ledges (a city's, a cave's): one way, a to b, and no part of the network's
  -- joining up. By road (the edge itself), as the numbers change below.
  local dropOf, caveOf = {}, {}
  -- (a building's inside, Data/Indoors.lua: from its own model, out only by its doors; the walls drawn round a
  -- building, to keep the land's routes out of it, don't cut it: Brill's inn's came apart in 13 pieces, 2026-10-06)
  local indoorOf = {}
  -- (and those of its buildings `attach`ed, not joined (indoors.py's phase 7): their joins don't split the land's road;
  -- a trip to or from one goes in by them, R.AttachTrip; every other route is on the land's roads as without them)
  local attachOf, attachJoin = {}, {}
  local nodeZ = {} -- (a capital's road nodes' floor heights, its data's `nz`: a stop with a height on its floor)
  local noBridge = {} -- (a cave's nodes inside it: joined to the rest only by its roads out)
  -- (the continent's roads with its overlays merged in don't depend on the player's drawn roads
  -- or walls: worked out once and kept, so an edit rebuilds only what they change; copies of the
  -- lists, which the walls below add to)
  local merged = mergedRoads[cont]
  -- (an attached building's roads after all the rest, the drawn roads and the player's too: every other road and node
  -- numbered as without them, so every search goes the same way; R.AttachTrip)
  local joined, attached = {}, {}
  for _, extra in ipairs(ns.RoadOverlays and ns.RoadOverlays[cont] or {}) do
    if extra.attach then attached[#attached + 1] = extra else joined[#joined + 1] = extra end
  end
  local overlays = ns.RoadOverlays and ns.RoadOverlays[cont]
  if merged and merged.roads == roads and merged.overlays == overlays and merged.nOverlays == (overlays and #overlays or 0) then
    nodes, edges = {}, {}
    for i = 1, #merged.nodes do nodes[i] = merged.nodes[i] end
    for i = 1, #merged.edges do edges[i] = merged.edges[i] end
    for k, v in pairs(merged.dropOf) do dropOf[k] = v end
    for k, v in pairs(merged.caveOf) do caveOf[k] = v end
    for k, v in pairs(merged.indoorOf or {}) do indoorOf[k] = v end
    noBridge = merged.noBridge
    nodeZ = merged.nodeZ
  else
  for ei, h in pairs(ns.RoadDrops and ns.RoadDrops[cont] or {}) do
    if edges[ei] then dropOf[edges[ei]] = h end
  end
  -- roads of a city's ruins up top (Data/Cities.lua), added to the continent's; its own
  -- roads that run through the ruins' walls there are left out. And the caves' roads
  -- (Data/Caves.lua), their ways out joined onto the continent's nearest road.
  local Pass = ns.Passability
  local samples = 0
  local function throughWalls(e)
    if not (Pass and Pass.Overlay) then return false end
    for i = 5, #e - 3, 2 do
      local x1, y1, x2, y2 = e[i], e[i + 1], e[i + 2], e[i + 3]
      if not Pass.OverlayNear or Pass.OverlayNear(cont, x1, y1, x2, y2) then -- (no grid there: nothing to cross)
        local n = math.max(1, math.floor(math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)))
        for k = 0, n do
          samples = samples + 1
          BreatheIfOver(samples, 64) -- (a sample a yard: one long road was 1.8 ms here, issue #841)
          -- (a city's walls: not a cave's rock, which is under the land)
          local v, o = Pass.OverlayRaw(cont, x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n, true)
          if v == 2 and not o.cave then return true end
        end
      end
    end
    return false
  end
  -- (an attached building's roads after all the rest, the drawn roads' ends joined too: every other road and node
  -- numbered as without them, so the search goes the same way)
  for _, extra in ipairs(joined) do
    local base = #nodes / 2
    local n2, e2 = {}, {}
    for i = 1, #nodes do
      Breathe(i, 20000)
      n2[i] = nodes[i]
    end
    for i = 1, #extra.n do
      BreatheIfOver(i, 500) -- (an overlay's nodes, the indoors' tens of thousands: issue #841)
      n2[#nodes + i] = extra.n[i]
    end
    local ox0, ox1, oy0, oy1 = math.huge, -math.huge, math.huge, -math.huge
    for i = 1, #extra.n, 2 do
      BreatheIfOver(i + 1, 500)
      ox0, ox1 = math.min(ox0, extra.n[i]), math.max(ox1, extra.n[i])
      oy0, oy1 = math.min(oy0, extra.n[i + 1]), math.max(oy1, extra.n[i + 1])
    end
    for i = 1, #edges do
      Breathe(i, 16) -- (throughWalls per road near the overlay: 100 between pauses was a long slice
      -- when a graph built inside a background job, the seed-31 sweep, 2026-10-07; so below)
      local e = edges[i]
      local a, b = e[1], e[2]
      local near = false -- (only roads near the ruins are checked; a cave's rock is under the land; a building's
      -- inside, Data/Indoors.lua, has no grid of its own: no land road is cut for it)
      for _, nd in ipairs((extra.cave or extra.indoor) and {} or { a, b }) do
        local x, y = nodes[nd * 2 - 1], nodes[nd * 2]
        if x > ox0 - 400 and x < ox1 + 400 and y > oy0 - 400 and y < oy1 + 400 then near = true end
      end
      -- (a road drawn in game (source 2) is truth: kept through them, as before it was in the data:
      -- Stormwind's gate road, drawn through its gate's closed cells, went once shipped, 2026-09-30)
      if e[4] == 2 or not (near and throughWalls(e)) then e2[#e2 + 1] = e end
    end
    local roadsEnd = #e2
    for k, e in ipairs(extra.e) do
      Breathe(k, 50)
      local c = Unpacked(e, extra.n, base)
      e2[#e2 + 1] = c
      if extra.drops and extra.drops[k] then dropOf[c] = extra.drops[k] end
      if extra.cave then caveOf[c] = true end
      if extra.indoor then indoorOf[c] = true end
    end
    for i, h in ipairs(extra.nz or {}) do
      Breathe(i, 2000)
      if h ~= 0 then nodeZ[base + i] = h end
    end
    -- (a cave's inside, or a building's: joined to the rest only by its ways out, its mouths or doors)
    if extra.cave or extra.indoor then
      for i = 1, #extra.n / 2 do
        Breathe(i, 2000)
        noBridge[base + i] = true
      end
      for _, j in ipairs(extra.bridge or {}) do noBridge[base + j] = "short" end
    end
    if extra.joins then R.JoinOnto(n2, e2, roadsEnd, base, extra.joins) end
    if extra.cave then
      for _, k in ipairs(R.JoinCavePieces(cont, n2, e2, base, extra.nz)) do caveOf[e2[k]] = true end
    end
    nodes, edges = n2, e2
  end
  if nodes == roads.n then -- (no overlays: copies, as the data's own lists aren't changed)
    local n2, e2 = {}, {}
    for i = 1, #nodes do
      Breathe(i, R.KEEP_BREATHE)
      n2[i] = nodes[i]
    end
    for i = 1, #edges do
      Breathe(i, R.KEEP_BREATHE)
      e2[i] = edges[i]
    end
    nodes, edges = n2, e2
  end
  if not roads.z then R.JoinDrawnEnds(nodes, edges, caveOf, dropOf, noBridge, attachOf) end -- (not a level with heights: by floor there)
  local keep ={ roads = roads, overlays = overlays, nOverlays = overlays and #overlays or 0,
    nodes = {}, edges = {}, dropOf = {}, caveOf = {}, noBridge = noBridge, nodeZ = nodeZ, indoorOf = indoorOf }
  -- (a pause every KEEP_BREATHE: a copy's growing table is moved and the garbage collector's share comes with it,
  -- 8-11 ms a 5,000 on Kalimdor, release 1.3.12's CI timing)
  for i = 1, #nodes do
    Breathe(i, R.KEEP_BREATHE)
    keep.nodes[i] = nodes[i]
  end
  for i = 1, #edges do
    Breathe(i, R.KEEP_BREATHE)
    keep.edges[i] = edges[i]
  end
  local copied = 0
  for k, v in pairs(dropOf) do
    copied = copied + 1
    Breathe(copied, R.KEEP_BREATHE)
    keep.dropOf[k] = v
  end
  for k, v in pairs(caveOf) do
    copied = copied + 1
    Breathe(copied, R.KEEP_BREATHE)
    keep.caveOf[k] = v
  end
  mergedRoads[cont] = keep
  end
  P1("router: build roads: overlays and caves", pt)
  pt = P0()
  local tracks = ns.db and ns.db.tracks
  local trackInfo -- (the edited roads' kinds and the raised ones: R.WithTracks)
  -- (and the roads the data has with their heights, drawn in game and shipped as they were (ns.FloorTracks, 1.1.6's
  -- road tools): put on first, as the player's own are, on their floors)
  local floorTracks = ns.FloorTracks and ns.FloorTracks[cont]
  if floorTracks and #floorTracks > 0 then
    local all = {}
    for _, t in ipairs(floorTracks) do
      t.shipped, t.continent = true, cont
      all[#all + 1] = t
    end
    for _, t in ipairs(tracks or {}) do all[#all + 1] = t end
    tracks = all
  end
  local zs = roads.z -- (a level with heights: each node's)
  if tracks and #tracks > 0 then
    -- (the player's recorded and drawn roads, on the roads as merged)
    local nz2, inside
    nodes, edges, zs, nz2, inside, trackInfo = R.WithTracks({ n = nodes, e = edges, z = roads.z,
      nz = not roads.z and nodeZ or nil, cave = caveOf, drop = dropOf }, tracks, cont)
    if nz2 then nodeZ = nz2 end -- (a copy with the drawn roads' floors: the merged one is kept as it was)
    for ed in pairs(inside or {}) do indoorOf[ed] = true end
  end
  -- Walls (drawn or shipped: Passability.WallLines) block walking over the land, not the roads: a road through one is
  -- a pass, as over the terrain's too-steep edges (asked 2026-11-15: "roads should be allowed through drawn walls just
  -- like normal walls"; a wall drawn along a cliff by Dun Garok cut Hillsbrad's road south and no way was left from
  -- Tarren Mill to Kharanos). The road eraser takes a road out. R.WALLS_CUT_ROADS: the old rule, walls cutting the
  -- roads they cross (a gate a gap in them).
  local P = ns.Passability
  if R.WALLS_CUT_ROADS and P and P.HasWalls and P.HasWalls(cont) then
    if nodes == roads.n then
      local copy = {}
      for i = 1, #nodes do copy[i] = nodes[i] end
      nodes = copy
    end
    -- (a wall drawn with a floor, `fl`: it cuts only that floor's roads, by the road at the crossing)
    local floorsAt = zs and P.WallFloors and P.WallFloors(cont) and R.FloorIndex(edges, zs)
    local cur -- (the road being checked)
    local function onWallFloor(s, x, y)
      local wf = s.fl
      if not wf then return true end
      if zs then
        if not (wf.z and floorsAt) then return true end
        local _, along = Closest(cur, x, y)
        local h = along and HeightOn(zs, cur, along)
        local f = h and R.NearestHeight(floorsAt(x, y), wf.z)
        return not f or math.abs(h - f) <= R.LAYER_Z
      end
      return R.CaveFloorOK(cont, x, y, caveOf[cur], wf.z, wf.indoors, wf.down)
    end
    local kept = {}
    local wchecks = 0 -- (walls are checked along every segment, and one road can be hundreds of points:
    -- the pause goes by checks, not roads — one road's own checks were a 20 ms stretch, 2026-10-07)
    for k, ed in ipairs(edges) do
      Breathe(k, 25) -- (CrossesWall along each road)
      cur = ed
      local crossed = false
      for i = 5, indoorOf[ed] and 0 or #ed - 3, 2 do -- (a building's inside: never cut, indoorOf)
        wchecks = wchecks + 1
        Breathe(wchecks, 150)
        if P.CrossesWall(cont, ed[i], ed[i + 1], ed[i + 2], ed[i + 3], onWallFloor) then crossed = true break end
      end
      if not crossed then
        kept[#kept + 1] = ed
      else
        -- the stretches between the crossings, each a road of its own, cut a yard short of
        -- the wall either side (ends: new nodes)
        local run, a = { ed[5], ed[6] }, ed[1]
        local function flush(b)
          if #run >= 4 then
            local e2 = MakeEdge(a, b, run, ed[4])
            if dropOf[ed] then dropOf[e2] = dropOf[ed] end
            if caveOf[ed] then caveOf[e2] = true end
            kept[#kept + 1] = e2
          end
        end
        local skip = 0 -- (yards of the gap still to leave out, past a crossing at a segment's end)
        for i = 5, #ed - 3, 2 do
          local x1, y1, x2, y2 = ed[i], ed[i + 1], ed[i + 2], ed[i + 3]
          local len = math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)
          if skip > 0 then
            if len <= skip then
              skip = skip - len
              x1, y1 = x2, y2
            else
              local f = skip / len
              x1, y1 = x1 + (x2 - x1) * f, y1 + (y2 - y1) * f
              skip = 0
            end
            nodes[#nodes] , nodes[#nodes - 1] = y1, x1 -- (the new piece's start node, moved on)
            run = { x1, y1 }
          end
          local guard = 0
          while skip == 0 do
            wchecks = wchecks + 1
            Breathe(wchecks, 150)
            local t = P.WallHit(cont, x1, y1, x2, y2, onWallFloor)
            guard = guard + 1
            if not t or guard > 20 then break end
            local L = math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)
            local g = L > 0 and 1 / L or 0 -- (a yard, as a share of the leg)
            local ax, ay = x1 + (x2 - x1) * math.max(0, t - g), y1 + (y2 - y1) * math.max(0, t - g)
            run[#run + 1], run[#run + 2] = ax, ay
            nodes[#nodes + 1], nodes[#nodes + 2] = ax, ay
            flush(#nodes / 2)
            if t + g >= 1 then
              -- (the gap runs on into the next segment)
              skip = (t + g - 1) * L
              nodes[#nodes + 1], nodes[#nodes + 2] = x2, y2
              run, a = { x2, y2 }, #nodes / 2
              x1, y1 = x2, y2
              if skip <= 0 then skip = 1e-6 end
              break
            end
            local bx, by = x1 + (x2 - x1) * (t + g), y1 + (y2 - y1) * (t + g)
            nodes[#nodes + 1], nodes[#nodes + 2] = bx, by
            run, a = { bx, by }, #nodes / 2
            x1, y1 = bx, by
          end
          if skip == 0 or x1 ~= x2 or y1 ~= y2 then
            if not (run[#run - 1] == x2 and run[#run] == y2) then run[#run + 1], run[#run + 2] = x2, y2 end
          end
        end
        flush(ed[2])
      end
    end
    edges = kept
  end
  if attached[1] then
    if nodes == roads.n then -- (the data's own lists aren't changed)
      local n2, e2 = {}, {}
      for i = 1, #nodes do n2[i] = nodes[i] end
      for i = 1, #edges do e2[i] = edges[i] end
      nodes, edges = n2, e2
    end
    local nz2 = {} -- (a copy: the merged one is kept as it was)
    for k, v in pairs(nodeZ) do nz2[k] = v end
    nodeZ = nz2
    local nb = {}
    for k, v in pairs(noBridge) do nb[k] = v end
    noBridge = nb
    for _, extra in ipairs(attached) do
      local base = #nodes / 2
      for i = 1, #extra.n do
        BreatheIfOver(i, 500)
        nodes[#nodes + 1] = extra.n[i]
      end
      for k, e in ipairs(extra.e) do
        Breathe(k, 50)
        local c = Unpacked(e, extra.n, base)
        edges[#edges + 1] = c
        indoorOf[c], attachOf[c] = true, true
      end
      for i, h in ipairs(extra.nz or {}) do
        if h ~= 0 then nodeZ[base + i] = h end
      end
      for i = 1, #extra.n / 2 do noBridge[base + i] = true end
      for _, j in ipairs(extra.joins or {}) do attachJoin[base + j] = true end
    end
  end
  local drops, caveEdges, indoorEdges = {}, {}, {}
  local attachedEdges = {} -- (an attached building's roads, its doors' ways to its joins too)
  local kinds, raisedEdges = {}, {} -- (the edited roads' kinds, R.TRACK_KINDS, and the raised ones: by edge number)
  local flooredEdges = {} -- (and those of tracks with their heights)
  local tk, tr, tf = trackInfo and trackInfo.kind, trackInfo and trackInfo.raised, trackInfo and trackInfo.floored
  for ei, ed in ipairs(edges) do
    Breathe(ei, 500)
    drops[ei] = dropOf[ed]
    caveEdges[ei] = caveOf[ed]
    if tk and tk[ed] then kinds[ei] = tk[ed] end
    if tr and tr[ed] then raisedEdges[ei] = true end
    if tf and tf[ed] then flooredEdges[ei] = true end
    -- (a building's own roads, both ends on its floors: not a door's join onto the land's road)
    if indoorOf[ed] and nodeZ[ed[1]] and nodeZ[ed[2]] then indoorEdges[ei] = true end
    if attachOf[ed] then attachedEdges[ei] = true end
  end
  P1("router: build roads: drawn roads", pt)
  pt = P0()
  local adj = {}
  local ratio = {} -- [edge] = its cost per yard, where more than 1 (past guards)
  local edgeTowns = {} -- [edge] = { [town] = yards past its guards }, where it has any
  local edgeLight = {} -- [edge] = its extra cost past the light ones (R.HOSTILE_LIGHT), where it has any
  -- (the zone a road is in and its yards there, two flat lists: a table per edge holding mostly one
  -- pair was ~2 MB of the two graphs, the 2026-10-07 memory census; the few edges crossing several
  -- zones keep a table in zonesOver. 0: no zone counted.)
  local zoneId, zoneYd, zonesOver = {}, {}, {}
  local hasZones = ns.Zones and ns.Zones[cont] ~= nil
  local side = HostileSide()
  for ei, e in ipairs(edges) do
    Breathe(ei, 4) -- (each road: the guards and zones along it, sampled its whole length — 20 between
    -- pauses was the seed-31 sweep's 40-50 ms slice when a graph built inside the ride check, 2026-10-07)
    local a, b, len = e[1], e[2], e[3]
    adj[a] = adj[a] or {}
    adj[b] = adj[b] or {}
    if not drops[ei] then
      -- (cost: its length, and more where it passes the other faction's guards)
      local cost, towns = len, nil
      if side then
        towns = {}
        for i = 5, #e - 3, 2 do
          cost = cost + R.HostileYards(cont, e[i], e[i + 1], e[i + 2], e[i + 3], side, nil, towns) * (R.HOSTILE_FACTOR - 1)
        end
        local light = 0
        for i = 5, #e - 3, 2 do
          light = light + R.HostileLightYards(cont, e[i], e[i + 1], e[i + 2], e[i + 3], side) * (R.HOSTILE_LIGHT_FACTOR - 1)
        end
        if light > 0 then cost, edgeLight[ei] = cost + light, light end
      end
      if e[4] == R.SOURCE_SWIM then cost = cost * R.SWIM_FACTOR end -- (swum: never by choice)
      adj[a][#adj[a] + 1] = { b, len, ei, true, cost }
      adj[b][#adj[b] + 1] = { a, len, ei, false, cost }
      if cost > len then
        ratio[ei] = cost / math.max(len, 1)
        edgeTowns[ei] = towns -- (the yards past each town's guards: a route to or from a town doesn't pay for it)
      end
      -- (yards in each zone: for keeping out of zones too high for the player)
      if hasZones then
        local zy = {}
        for i = 5, #e - 3, 2 do R.ZoneYards(cont, e[i], e[i + 1], e[i + 2], e[i + 3], zy) end
        local z1, n = nil, 0
        for z in pairs(zy) do z1, n = z, n + 1 end
        if n == 1 then
          zoneId[ei], zoneYd[ei] = z1, zy[z1]
        elseif n > 1 then
          zonesOver[ei] = zy
        end
      end
    end
    if zoneId[ei] == nil then zoneId[ei], zoneYd[ei] = 0, 0 end
  end
  local grid = ns.Terrain and ns.Terrain[cont]
  local P = ns.Passability
  -- (a city's ruins up top: not a cave's, whose own nodes don't take part)
  local nearOverlay = ns.CityHalls and ns.CityHalls[cont] and P and P.OverlayRaw
    and function(x, y)
      local v, o = P.OverlayRaw(cont, x, y)
      return v ~= nil and not o.cave
    end or nil
  P1("router: build roads: costs", pt)
  pt = P0()
  local nzB = not zs and next(nodeZ) and nodeZ or nil
  -- (a raised road's nodes along it, a bridge's: no gap link onto them from the roads under them, only its ends)
  local skipB = noBridge
  if trackInfo and next(trackInfo.raisedNode) then
    skipB = {}
    for k, v in pairs(noBridge) do skipB[k] = v end
    for nd in pairs(trackInfo.raisedNode) do skipB[nd] = skipB[nd] or true end
  end
  local bridges = Bridges(nodes, adj, grid and grid.slack and 0 or nil, nearOverlay, skipB, zs, nzB)
  local cliff = not zs and P and P.CliffAlong and function(a, b)
    return P.CliffAlong(cont, nodes[a * 2 - 1], nodes[a * 2], nodes[b * 2 - 1], nodes[b * 2])
  end or nil
  if not (grid and grid.slack) then R.DeadEndLinks(nodes, adj, bridges, skipB, nearOverlay, zs, edges, nzB, cliff) end -- (#411)
  for ei in pairs(drops) do
    local e = edges[ei]
    if e then adj[e[1]][#adj[e[1]] + 1] = { e[2], e[3], ei, true } end
  end
  P1("router: build roads: gap links", pt)
  pt = P0()
  -- The adjacency packed flat (a table per node and one per directed edge were 7.6 MB of the two graphs,
  -- 2026-10-07): node n's entries sit at adjIdx[n] .. adjIdx[n + 1] - 1 in four lists: the far node, the
  -- length, the edge signed (+ forward, - back, as the A* keeps its steps), and the cost past guards
  -- (0: the length). Bridges and the drops above still build the per-node tables; only the flat lists ship.
  local adjIdx, adjTo, adjLen, adjE, adjCost = {}, {}, {}, {}, {}
  local ak = 1
  for an = 1, #nodes / 2 do
    Breathe(an, 2000)
    adjIdx[an] = ak
    for _, a in ipairs(adj[an] or EMPTY) do
      adjTo[ak], adjLen[ak], adjE[ak], adjCost[ak] = a[1], a[2], a[4] and a[3] or -a[3], a[5] or 0
      ak = ak + 1
    end
  end
  adjIdx[#nodes / 2 + 1] = ak
  adj = nil
  P1("router: build roads: packing", pt)
  local g = { adjIdx = adjIdx, adjTo = adjTo, adjLen = adjLen, adjE = adjE, adjCost = adjCost,
    n = nodes, e = edges, count = #nodes / 2, bridges = bridges, drops = drops, side = side,
    ratio = ratio, towns = edgeTowns, light = edgeLight, cave = caveEdges, caveNode = noBridge, z = zs, nz = next(nodeZ) and nodeZ or nil,
    zoneId = hasZones and zoneId or nil, zoneYd = hasZones and zoneYd or nil,
    zonesOver = next(zonesOver) and zonesOver or nil,
    indoor = next(indoorEdges) and indoorEdges or nil,
    attached = next(attachedEdges) and attachedEdges or nil, attachJoin = next(attachedEdges) and attachJoin or nil,
    kind = next(kinds) and kinds or nil, raised = next(raisedEdges) and raisedEdges or nil,
    floored = next(flooredEdges) and flooredEdges or nil,
    raisedEnd = next(raisedEdges) and trackInfo and trackInfo.raisedEnd or nil }
  -- (an underground city's floors over floors: the roads' heights near a spot, for the road and wall
  -- tools' floor (GPSFrame.OtherFloor, FloorText); not a dungeon's, where they can't be used)
  local lvl = ns.CityLevels and ns.CityLevels[cont]
  if zs and lvl and not lvl.instance then
    pt = P0()
    g.floorsAt = R.FloorIndex(edges, zs)
    -- (each road with roads on other floors at its middle: its height there and theirs)
    local others = {}
    for ei, ed in ipairs(edges) do
      Breathe(ei, 100)
      local x, y, along = R.EdgeMiddle(ed)
      local h = HeightOn(zs, ed, along)
      if h then
        local hs = g.floorsAt(x, y)
        for _, o in ipairs(hs) do
          if math.abs(o - h) > R.LAYER_Z then
            others[ei] = { h = h, hs = hs }
            break
          end
        end
      end
    end
    g.otherFloors = others
    P1("router: build roads: floors", pt)
  end
  ClearEdgeBoxes() -- (build-time only: see its note)
  -- (built in the background by WarmUp, a route may have built it meanwhile: keep that one)
  if graphs[cont] == nil then graphs[cont] = g end
  return graphs[cont] or nil
end

-- Terrain walks (Passability.FindPath) by end points: the legs to the destination are
-- the same on every reroute.
local walks, walkCount = {}, 0
local failed = {} -- rough spots where walks failed: "cont:x:y:x2:y2" at WALK_FAIL_YD
local walkJobs, walkQueued = {}, {} -- background searches (coroutines), queued by key
R.WALK_FAIL_YD = 25 -- a walk that failed isn't retried from within this distance
-- Tests: search right away instead of in the background.
R.SYNC_WALKS = false
R.MAX_WALK_JOBS = 8
R.STALE_START_YD = 15 -- queued searches from where the player was, further than this: dropped
R.WALK_REUSE_YD = 30 -- a walk found from where the player was, this close: joined straight from here
R.PENDING_BLOCKED_YD = 40 -- while a walk around is searched: blocked for no more than this in a straight
R.PENDING_BLOCKED_COST = 2 -- line, it's taken to be about straight (each blocked yard costing this many)

-- The road edges routing uses on `cont` (shipped roads plus recorded ones), and the graph
-- they belong to (a new one after Reset, e.g. when a recording is saved).
function R.Edges(cont)
  local g = Graph(cont)
  return g and g.e, g
end

local warmed, warming = {}, {} -- WarmUp: continents done, and started (GetTime) but not done

-- The other faction's guards (Data/Hostile.lua): the side whose circles are dangerous to
-- the player ("A" for an Alliance character: the Horde's guards), nil when unknown or the
-- option is off.
-- (read once per background job: every GraphQuery and Graph asks, and Smooth asks for each point it weighs; the
-- faction through ns.CharDB is the game's UnitName and GetRealmName and strings built, a third of a ride check's time,
-- issue #348. The faction can't change in a session, nor the option in the middle of a job)
local sideOf = setmetatable({}, { __mode = "k" }) -- [coroutine] = { side }
function HostileSide()
  local co = CanYield() and coroutine.running()
  local seen = co and sideOf[co]
  if seen then return seen[1] end
  local st = ns.settings and ns.settings.gps
  local side
  if not (st and st.avoidHostile == false) then side = ns.Nav and ns.Nav.Faction and ns.Nav.Faction() or nil end
  if co then sideOf[co] = { side } end
  return side
end
R.HostileSide = HostileSide
local HB = 100 -- bucket size (yards)
local hostileIdx = {}
local function HostileBuckets(cont, side)
  local key = cont .. side
  local idx = hostileIdx[key]
  if idx then return idx end
  idx = {}
  local list = ns.Hostile and ns.Hostile[cont] and ns.Hostile[cont][side] or {}
  local bn = 0 -- (i steps by 3: i % 300 never hits 0, so the pause counts guards itself)
  for i = 1, #list - 2, 3 do
    bn = bn + 1
    Breathe(bn, 100) -- (in a background job: a pause every 100 guards; built whole, the first guard
    -- check of a graph's build was a ~19 ms stretch, the seed-31 sweep, 2026-10-07)
    local x, y, r = list[i], list[i + 1], list[i + 2]
    for kx = math.floor((x - r) / HB), math.floor((x + r) / HB) do
      for ky = math.floor((y - r) / HB), math.floor((y + r) / HB) do
        local k = kx * 65536 + ky
        idx[k] = idx[k] or {}
        idx[k][#idx[k] + 1] = i
      end
    end
  end
  hostileIdx[key] = idx
  return idx
end
-- The guards' towns: circles this near each other (their reaches less TOWN_GAP apart) are one town. A route
-- that starts or ends in a town doesn't pay for that town's guards (asked 2026-10-02: a stop at Dun Garok, the
-- Alliance's, from Tarren Mill came back as a straight walk over the hills, the road into it being "past their
-- guards"), as the zones a route starts and ends in don't count as too high (LEVEL_FACTOR).
R.TOWN_GAP = 60 -- yards
R.TOWN_NEAR = 20 -- yards: a start or stop this near a town's guards is in it (60 till 2026-11-14: a stop 45 yd past
-- Southshore's guards, west of it, counted as in the town, and the walk there from the south went through it, asked)
local hostileTowns = {}
-- The guards changed (ns.Hostile): their buckets and towns built again, and the graphs (their roads' costs).
function R.HostileChanged()
  hostileIdx, hostileTowns = {}, {}
  if R.Reset then R.Reset() end
end
function R.HostileTowns(cont, side)
  local key = cont .. side
  local town = hostileTowns[key]
  if town then return town end
  town = {}
  local list = ns.Hostile and ns.Hostile[cont] and ns.Hostile[cont][side] or {}
  local idx = HostileBuckets(cont, side)
  local parent = {}
  -- (path halving: without it the chains grew as long as a continent's guards, and the first call was 180-220 ms in one
  -- piece, a hitch on the first route on a continent; the overnight profile, 2026-10-07)
  local function find(i)
    while parent[i] ~= i do
      parent[i] = parent[parent[i]]
      i = parent[i]
    end
    return i
  end
  for i = 1, #list - 2, 3 do parent[i] = i end
  local gap = R.TOWN_GAP
  local tn = 0 -- (i steps by 3: i % 300 never hit 0, and this never paused; 2026-10-07)
  for i = 1, #list - 2, 3 do
    tn = tn + 1
    Breathe(tn, 100) -- (in a background job: a pause every 100 guards)
    local x, y, r = list[i], list[i + 1], list[i + 2]
    for kx = math.floor((x - r - gap) / HB), math.floor((x + r + gap) / HB) do
      for ky = math.floor((y - r - gap) / HB), math.floor((y + r + gap) / HB) do
        for _, j in ipairs(idx[kx * 65536 + ky] or EMPTY) do
          if j > i and (list[j] - x) ^ 2 + (list[j + 1] - y) ^ 2 <= (r + list[j + 2] + gap) ^ 2 then -- (each pair once)
            local a, b = find(i), find(j)
            if a ~= b then parent[a] = b end
          end
        end
      end
    end
  end
  for i = 1, #list - 2, 3 do town[i] = find(i) end
  hostileTowns[key] = town
  return town
end
-- The towns (a set) whose guards stand within TOWN_NEAR of their reach of any of the points (x, y, ...).
function R.HostileTownsNear(cont, side, ...)
  local list = side and ns.Hostile and ns.Hostile[cont] and ns.Hostile[cont][side]
  if not list then return nil end
  local town, out, pts = R.HostileTowns(cont, side), nil, { ... }
  local near = R.TOWN_NEAR
  for p = 1, #pts - 1, 2 do
    local x, y = pts[p], pts[p + 1]
    for i = 1, #list - 2, 3 do
      if (list[i] - x) ^ 2 + (list[i + 1] - y) ^ 2 <= (list[i + 2] + near) ^ 2 then
        out = out or {}
        out[town[i]] = true
      end
    end
  end
  return out
end
-- Whether (x, y) is within reach of guards hostile to the player (`side`: HostileSide()), not counting the
-- towns in `exempt` (a set, R.HostileTownsNear); with `acc`, the town whose guard it is.
function R.HostileAt(cont, x, y, side, exempt)
  side = side or HostileSide()
  if not side then return false end
  local list = ns.Hostile and ns.Hostile[cont] and ns.Hostile[cont][side]
  if not list then return false end
  local b = HostileBuckets(cont, side)[math.floor(x / HB) * 65536 + math.floor(y / HB)]
  local town = exempt and R.HostileTowns(cont, side)
  for _, i in ipairs(b or {}) do
    if (list[i] - x) ^ 2 + (list[i + 1] - y) ^ 2 <= list[i + 2] ^ 2 and not (town and exempt[town[i]]) then
      return true, i
    end
  end
  return false
end
-- Yards of the leg (x1, y1)-(x2, y2) within their reach (`exempt` towns not counted). With `acc`, the yards
-- also added up per town into it ({ [town] = yards }).
function R.HostileYards(cont, x1, y1, x2, y2, side, exempt, acc)
  side = side or HostileSide()
  if not (side and ns.Hostile and ns.Hostile[cont] and ns.Hostile[cont][side]) then return 0 end
  -- (a short leg, a road's piece, whose box's buckets hold no circle: none of it in reach, without sampling it; the
  -- light ones made every road weighed twice at a graph's build, the Brill frame budget's ride check 1,200 slices of
  -- 1,000. A long one's box is many buckets: sampled as ever)
  local bx1, bx2 = math.floor(math.min(x1, x2) / HB), math.floor(math.max(x1, x2) / HB)
  local by1, by2 = math.floor(math.min(y1, y2) / HB), math.floor(math.max(y1, y2) / HB)
  if bx2 - bx1 <= 1 and by2 - by1 <= 1 then -- (at most 2 by 2: its corners are all its buckets)
    local idx = HostileBuckets(cont, side)
    if not (idx[bx1 * 65536 + by1] or idx[bx1 * 65536 + by2] or idx[bx2 * 65536 + by1] or idx[bx2 * 65536 + by2]) then
      return 0
    end
  end
  local d = math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)
  local n = math.max(1, math.ceil(d / R.HOSTILE_STEP))
  local inside = 0
  local town = acc and R.HostileTowns(cont, side)
  for k = 0, n - 1 do
    local t = (k + 0.5) / n
    local hit, i = R.HostileAt(cont, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, side, exempt)
    if hit then
      inside = inside + 1
      if acc then acc[town[i]] = (acc[town[i]] or 0) + d / n end
    end
  end
  return d * inside / n
end
-- Yards of the leg within reach of the light ones (R.HOSTILE_LIGHT) hostile to `side`.
function R.HostileLightYards(cont, x1, y1, x2, y2, side, ends)
  side = side or HostileSide()
  local light = side and R.HOSTILE_LIGHT[side]
  if not (light and ns.Hostile and ns.Hostile[cont] and ns.Hostile[cont][light]) then return 0 end
  if ends and (NearLightEnd(x1, y1) or NearLightEnd(x2, y2)) then return 0 end
  return R.HostileYards(cont, x1, y1, x2, y2, light)
end
local function HostileExtra(cont, x1, y1, x2, y2, exempt)
  return R.HostileYards(cont, x1, y1, x2, y2, nil, exempt) * (R.HOSTILE_FACTOR - 1)
    + R.HostileLightYards(cont, x1, y1, x2, y2, nil, true) * (R.HOSTILE_LIGHT_FACTOR - 1)
end

-- Zones too high for the player (option avoidHighZones, on by default): their lowest level
-- more than LEVEL_RED above the player's (red on the map's zone hover). A yard in one costs
-- LEVEL_FACTOR, like the other faction's guards' reach but milder: the way round is taken
-- when it's up to that much longer. The zones a route starts and ends in don't count.
R.LEVEL_RED = 4
R.LEVEL_FACTOR = 4
-- (asked 2026-11-14: level 20, Tarren Mill to the Wetlands swam 1.6k yd down the coast round the Arathi Highlands;
-- "take the road through Arathi with a warning") with zones too high about, a walk swimming SWIM_DETOUR_YD or more
-- pays LEVEL_FACTOR a yard of water, as a yard in one: the way round them isn't a long swim. The road through is
-- taken and asked about once (Nav.RedOnRoute). A river crossed on the way stays as it was
R.SWIM_DETOUR_YD = 300
R.SWIM_DETOUR_THROUGH = 0.5 -- (a walk through this share of the straight line's yards in them isn't a way round)
R.ZONE_STEP = 16 -- yards between the points checked along a road or leg

-- The zone (its uiMap) at world (x, y) on `cont`, from Data/Zones.lua; 0 for none.
local ZONE_TILE = 1600 / 3
function R.ZoneAt(cont, x, y)
  local z = ns.Zones and ns.Zones[cont]
  if not z then return 0 end
  local runs = z.rows[math.floor((32 - x / ZONE_TILE) * 16)]
  local col = math.floor((32 - y / ZONE_TILE) * 16)
  if not runs or col < 0 then return 0 end
  local c = 0
  for i = 1, #runs - 1, 2 do
    c = c + runs[i + 1]
    if col < c then return runs[i] end
  end
  return 0
end

-- Yards of the line (x1, y1)-(x2, y2) in each zone, added to `out` ({ [uiMap] = yards }).
function R.ZoneYards(cont, x1, y1, x2, y2, out)
  out = out or {}
  if not (ns.Zones and ns.Zones[cont]) then return out end
  local d = math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)
  local n = math.max(1, math.ceil(d / R.ZONE_STEP))
  for k = 0, n - 1 do
    local t = (k + 0.5) / n
    local z = R.ZoneAt(cont, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
    if z ~= 0 then out[z] = (out[z] or 0) + d / n end
  end
  return out
end

-- A zone's levels: the game's (C_Map.GetMapLevels), else the map's table (GPSFrame's).
function R.ZoneLevels(id)
  if C_Map and C_Map.GetMapLevels then
    local ok, lo, hi = pcall(C_Map.GetMapLevels, id)
    if ok and lo and hi and lo > 0 then return lo, hi end
  end
  local m = ns.Maps and ns.Maps[id]
  local l = m and ns.GPS and ns.GPS.ZONE_LEVELS and ns.GPS.ZONE_LEVELS[m.name]
  if l then return l[1], l[2] end
end

-- The zones too high for the player now: { [uiMap] = true }, or nil (none, the option off,
-- the level unknown).
local redZones = {}
function R.RedZones()
  local st = ns.settings and ns.settings.gps
  if st and st.avoidHighZones == false then return nil end
  local ok, lvl = pcall(UnitLevel or error, "player")
  if not ok or type(lvl) ~= "number" or lvl <= 0 then return nil end
  local set = redZones[lvl]
  if set == nil then
    set = false
    for id, m in pairs(ns.Maps or {}) do
      if m.type == 3 then
        local lo = R.ZoneLevels(id)
        if lo and lvl < lo - R.LEVEL_RED then
          set = set or {}
          set[id] = true
        end
      end
    end
    redZones[lvl] = set
  end
  return set or nil
end

function R.Reset()
  graphs, walks, walkCount, failed, walkJobs, walkQueued = {}, {}, 0, {}, {}, {}
  warmed, warming = {}, {}
  R.ClearSegMemo()
end

-- Straight-line terrain checks for off-road legs, remembered: recalculating a route from
-- the player's new position repeats every check on the destination's side (the same
-- points), and terrain doesn't change. Up to SEG_MEMO_MAX, then started over.
local SEG_MEMO_MAX = 20000
local segMemo, segMemoCount = {}, 0
function R.ClearSegMemo() segMemo, segMemoCount = {}, 0 end
-- Yards of a terrain walk (`path`, flat points; nil: the straight line) over the grid's water (P.WaterSpans).
function R.WalkSwimYards(cont, path, x1, y1, x2, y2)
  local P = ns.Passability
  if not (P and P.WaterSpans) then return 0 end
  local wet = 0
  local function add(a, b, c, d)
    local s = P.WaterSpans(cont, a, b, c, d)
    if s then
      local len = math.sqrt((c - a) ^ 2 + (d - b) ^ 2)
      for i = 1, #s - 1, 2 do wet = wet + (s[i + 1] - s[i]) * len end
    end
  end
  if path then
    for i = 1, #path - 2, 2 do add(path[i], path[i + 1], path[i + 2], path[i + 3]) end
  else
    add(x1, y1, x2, y2)
  end
  return wet
end

local function SegCost(cont, x1, y1, x2, y2)
  local key = string.format("%d:%.1f:%.1f:%.1f:%.1f", cont, x1, y1, x2, y2)
  local c = segMemo[key]
  if c == nil then
    c = ns.Passability.SegmentCost(cont, x1, y1, x2, y2) or false
    if segMemoCount >= SEG_MEMO_MAX then segMemo, segMemoCount = {}, 0 end
    segMemo[key], segMemoCount = c, segMemoCount + 1
  end
  return c or nil
end

local byTarget = {} -- walks found, by where they go: [cont:x:y] = { [walk key] = true }

-- Walls drawn or erased with the tools still on (asked 2026-11-07: "need to update this to work instantly"): the walks
-- off the roads and their straight checks start over, so the next route goes round them at once; the road network
-- (the roads the walls cut, the links between them) waits for the tools to be turned off (Record.Apply, R.Reset).
function R.WallsChanged()
  walks, walkCount, failed, walkJobs, walkQueued, byTarget = {}, 0, {}, {}, {}, {}
  -- (the road nodes' straight links off the roads too: priced by SegmentCost, the walls and the swim cost in them;
  -- their background job just dropped with the others, so none is waited on)
  for _, g in pairs(graphs) do
    if g then
      g.links, g.linkQueued, g.linkJob = nil, nil, nil
      -- (and the links across gaps between road pieces: priced once by SegmentCost too, so at the swim cost then)
      for _, list in pairs(g.bridges or {}) do
        for _, b in ipairs(list) do b.raw, b.open, b.shut, b.prov = nil, nil, nil, nil end
      end
    end
  end
  R.ClearSegMemo()
end
local function Remember(key, rough, c, path, tkey)
  if walkCount > 256 then walks, walkCount, failed, byTarget = {}, 0, {}, {} end
  walks[key], walkCount = c and { c, path } or false, walkCount + 1
  if not c then failed[rough] = true end
  if c and path and tkey then
    byTarget[tkey] = byTarget[tkey] or {}
    byTarget[tkey][key] = true
  end
end

-- Run background terrain searches until `deadline` (now() in ms). Returns true when one
-- finished (the route should then be recomputed to use it), and whether any of those was
-- a leg between fixed points (then the legs between stops need recomputing too).
local pumpBuilt = false
function R.Pump(deadline, now)
  local finished, fixed = false, false
  pumpBuilt = false
  while walkJobs[1] and now() < deadline do
    -- (a route worked out again for a hop searches its walks `low`: after the others, 2026-11-14. First in line, a
    -- dozen searches that find nothing held up the walks the route itself waited on, and off Teldrassil the plan
    -- settled on walking down the tree's side before the teleporter's walks came in)
    local ji = 1
    if walkJobs[1].low then
      for i = 2, #walkJobs do
        if not walkJobs[i].low then ji = i break end
      end
    end
    local j = walkJobs[ji]
    if R.CLOCK_PAUSES then slice.stop, slice.now = deadline, now end
    local wasBuilding = building[j.co]
    local ok, c, path = coroutine.resume(j.co)
    slice.stop, slice.now = nil, nil
    if wasBuilding or building[j.co] then pumpBuilt = true end
    if not ok or coroutine.status(j.co) == "dead" then
      table.remove(walkJobs, ji)
      walkQueued[j.key] = nil
      if j.bg then
        if ok and j.done then j.done(c) end
      elseif j.warm then
        warming[j.cont] = nil
      elseif j.links then -- (offroad links a route wanted: recalculate)
        finished, fixed = true, true
      else
        Remember(j.key, j.rough, ok and c or nil, ok and path or nil, j.tkey)
        finished = true
        if not j.transient then fixed = true end
      end
    end
  end
  return finished, fixed
end

function R.HasWork() return walkJobs[1] ~= nil end
-- Whether the last R.Pump built a road network in any of its jobs (the warm-up's or one a route's job needed): not
-- counted by the stutter watch, Nav.RouteWork (issue #841: built for a search after a .go, it paused routing).
function R.PumpBuilt() return pumpBuilt end
-- Whether a job is building a road network now (paused in the middle of it): its slices get the warm-up's size.
function R.Building()
  for co, on in pairs(building) do
    if on and coroutine.status(co) ~= "dead" then return true end
  end
  return false
end

-- Other work in the background, pumped with the searches: fn() (it may route: a route's search
-- pauses every ROUTE_BREATHE nodes when run here), then done(result) with what it returned. One
-- job per key at a time. (Tests, SYNC_WALKS: at once.) False when that key's job is queued already.
-- `first`: ahead of the searches and the other jobs (after a road network being built), and that key's job already
-- queued moved there: a reroute off the route, the player waiting on it (it ran in the frame, a hitch every time).
R.ROUTE_BREATHE = 10
local function FrontAt()
  local at = 1
  while walkJobs[at] and walkJobs[at].warm do at = at + 1 end
  return at
end
function R.Background(key, fn, done, first)
  if walkQueued[key] then
    for i, j in ipairs(first and walkJobs or {}) do
      if j.key == key then
        local job = table.remove(walkJobs, i)
        table.insert(walkJobs, FrontAt(), job)
        break
      end
    end
    return false
  end
  if R.SYNC_WALKS then
    local result = fn()
    if done then done(result) end
    return true
  end
  walkQueued[key] = true
  local job = { key = key, bg = true, done = done, co = coroutine.create(fn) }
  if first then table.insert(walkJobs, FrontAt(), job) else walkJobs[#walkJobs + 1] = job end
  return true
end
-- Building a road network in the background: it gets more of each frame than searches do.
function R.Warming() return walkJobs[1] ~= nil and walkJobs[1].warm or false end

-- Returns yards, path; or nil (no way found), or nil, nil, true while still searching.
-- transient: a walk from the player's current position (soon stale as they move on);
-- only those are dropped when the queue is full; walks between fixed points always finish.
-- A walk found from near (x1, y1) to the same place (`tkey`): from here straight onto its
-- path (over open ground, within WALK_REUSE_YD), then along the rest of it. Yards, path; or nil.
-- (The player moves on while a walk from where they were is searched: without this every step
-- started a new search, and the route stayed on its stopgap meanwhile.)
local function Reuse(cont, x1, y1, tkey)
  local bestC, bestI, bestPath, bestX, bestY
  local P = ns.Passability
  for key in pairs(byTarget[tkey] or {}) do
    local w = walks[key]
    local path = w and w[2]
    if path and #path >= 4 then
      -- (its cost from each corner on, and each piece's, as the search priced them (P.SegmentCost: water dearer, more
      -- so with swimming left out): by yards alone a walk over a lake, found and lost to the roads, came back cheap on
      -- the next reroute from beside where it was searched; a removed swim was swum again, 2026-11-19)
      local remain, piece = w.remain, w.piece
      if not remain then
        remain, piece = { [#path - 1] = 0 }, {}
        for i = #path - 3, 1, -2 do
          local dx, dy = path[i + 2] - path[i], path[i + 3] - path[i + 1]
          local len = math.sqrt(dx * dx + dy * dy)
          piece[i] = math.max(len, P.SegmentCost(cont, path[i], path[i + 1], path[i + 2], path[i + 3]) or len)
          remain[i] = remain[i + 2] + piece[i]
        end
        w.remain, w.piece = remain, piece
      end
      -- (anywhere along it, not only at its corners, asked 2026-10-06: a walk's corners are far apart, and the only
      -- one near was where its search started, behind the player: the route stepped back there, or, once past it,
      -- went the long way by the roads while the next search ran, again on every reroute; Shadowvale, Tirisfal)
      for i = 1, #path - 3, 2 do
        local ax, ay, bx, by = path[i], path[i + 1], path[i + 2], path[i + 3]
        local vx, vy = bx - ax, by - ay
        local L2 = vx * vx + vy * vy
        local t = 0
        if L2 > 0 then t = math.max(0, math.min(1, ((x1 - ax) * vx + (y1 - ay) * vy) / L2)) end
        local qx, qy = ax + vx * t, ay + vy * t
        local d = math.sqrt((qx - x1) ^ 2 + (qy - y1) ^ 2)
        if d <= R.WALK_REUSE_YD then
          local join = P.SegmentCost(cont, x1, y1, qx, qy)
          local c = join and join + (1 - t) * piece[i] + remain[i + 2]
          if c and (not bestC or c < bestC) then
            bestC, bestI, bestPath, bestX, bestY = c, i, path, qx, qy
          end
        end
      end
    end
  end
  if not bestI then return nil end
  local out = { x1, y1 }
  local function Add(x, y) -- (no point twice in a row: the walk's corner itself when joined there)
    if (out[#out - 1] - x) ^ 2 + (out[#out] - y) ^ 2 > 0.01 then out[#out + 1], out[#out + 2] = x, y end
  end
  Add(bestX, bestY)
  for i = bestI + 2, #bestPath - 1, 2 do Add(bestPath[i], bestPath[i + 1]) end
  return bestC, out
end

local function Walk(cont, x1, y1, x2, y2, transient, road1, road2, low, fresh)
  local key = string.format("%d:%.0f:%.0f:%.0f:%.0f%s%s", cont, x1, y1, x2, y2, road1 and "r" or "", road2 and "R" or "")
  local tkey = string.format("%d:%.0f:%.0f", cont, x2, y2)
  local w = walks[key]
  if w == nil and transient and not fresh then -- (`fresh`: its own search, SwimWalk's: a reused walk can swim more)
    local c, path = Reuse(cont, x1, y1, tkey)
    if c then return c, path end
  end
  if w == nil then
    local g = R.WALK_FAIL_YD
    local rough = string.format("%d:%d:%d:%d:%d", cont, math.floor(x1 / g), math.floor(y1 / g),
      math.floor(x2 / g), math.floor(y2 / g))
    if failed[rough] then return nil end
    if R.SYNC_WALKS then
      local c, path = ns.Passability.FindPath(cont, x1, y1, x2, y2, road1, road2)
      Remember(key, rough, c, path, tkey)
      w = walks[key]
    else
      -- search in the background (Pump); meanwhile the caller falls back to a straight leg
      if not walkQueued[key] then
        -- searches from spots the player has already moved on from go stale: drop the
        -- queued ones from elsewhere (not the one running), and keep few
        local nTransient, oldest = 0, nil
        local far2 = R.STALE_START_YD * R.STALE_START_YD
        for i = #walkJobs, 2, -1 do
          local j = walkJobs[i]
          if j.transient and transient and ((j.x1 - x1) ^ 2 + (j.y1 - y1) ^ 2 > far2 or j.cont ~= cont) then
            walkQueued[j.key] = nil
            table.remove(walkJobs, i)
          end
        end
        for i = 2, #walkJobs do
          if walkJobs[i].transient then
            nTransient = nTransient + 1
            oldest = oldest or i
          end
        end
        if transient and nTransient >= R.MAX_WALK_JOBS and oldest then
          walkQueued[table.remove(walkJobs, oldest).key] = nil
        end
        walkQueued[key] = true
        walkJobs[#walkJobs + 1] = { key = key, rough = rough, tkey = tkey, transient = transient, cont = cont, x1 = x1, y1 = y1,
          low = low or nil, co =coroutine.create(function() return ns.Passability.FindPath(cont, x1, y1, x2, y2, road1, road2) end) }
      end
      return nil, nil, true -- still searching
    end
  end
  if w then return w[1], w[2] end
end

-- Whether a walk from (x1, y1) to (x2, y2) was searched and none found, without searching: as Walk keys it, with or
-- without its road ends, or failed near there (WALK_FAIL_YD). A leg not walked in this route (past
-- WALK_AROUND_CANDIDATES) that an earlier route's walk found none for is a hop already known (HOP_COST).
local function WalkFailed(cont, x1, y1, x2, y2)
  local key = string.format("%d:%.0f:%.0f:%.0f:%.0f", cont, x1, y1, x2, y2)
  if walks[key] == false or walks[key .. "r"] == false or walks[key .. "R"] == false or walks[key .. "rR"] == false then
    return true
  end
  local gy = R.WALK_FAIL_YD
  return failed[string.format("%d:%d:%d:%d:%d", cont, math.floor(x1 / gy), math.floor(y1 / gy),
    math.floor(x2 / gy), math.floor(y2 / gy))] and true or false
end

local function Dist(x1, y1, x2, y2)
  local dx, dy = x2 - x1, y2 - y1
  return math.sqrt(dx * dx + dy * dy)
end

-- A straight piece off the roads across water (SWIM_WALK_MIN_YD or more of it): its walk over the grid instead, when
-- that's cheaper at the swim cost, else nil. A straight leg was only ever walked round when the ground blocked it, and
-- water is open: every link, join and shortcut swam straight across a pond its walk goes round on land, 1.3x the
-- yards, south of Tarren Mill (2026-11-19). Searched in the background in game: straight meanwhile, the route worked
-- out again once it's in (Nav.SearchDone).
R.SWIM_WALK_MIN_YD = 10
local function SwimWalk(cont, x1, y1, x2, y2, transient)
  local P = ns.Passability
  if not (P and P.FindPath and P.SwimCost) then return nil end
  local swimCost = P.SwimCost()
  if swimCost <= 1 then return nil end
  local sc = SegCost(cont, x1, y1, x2, y2)
  if not sc then return nil end
  if (sc - Dist(x1, y1, x2, y2)) / (swimCost - 1) < R.SWIM_WALK_MIN_YD then return nil end
  local c, path = Walk(cont, x1, y1, x2, y2, transient, nil, nil, nil, true)
  if c and path and c < sc - 1 then return path end
  return nil
end

-- Yards of blocked ground on the straight line (x1, y1)-(x2, y2) (sampled every 4 yd).
local function BlockedYards(cont, x1, y1, x2, y2)
  local P = ns.Passability
  local d = Dist(x1, y1, x2, y2)
  local n = math.max(1, math.floor(d / 4))
  local blocked = 0
  for i = 0, n do
    BreatheIfOver(i + 1, 16) -- (a long line decodes the grid's rows as it goes)
    local t = i / n
    if P.At(cont, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t) == 2 then blocked = blocked + d / (n + 1) end
  end
  return blocked
end

-- The most blocked ground (yards) the straight line crosses in one go.
local function BlockedRun(cont, x1, y1, x2, y2)
  local P = ns.Passability
  local d = Dist(x1, y1, x2, y2)
  local n = math.max(1, math.floor(d / 4))
  local run, most = 0, 0
  for i = 0, n do
    BreatheIfOver(i + 1, 16)
    local t = i / n
    if P.At(cont, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t) == 2 then
      run = run + d / n
      if run > most then most = run end
    else
      run = 0
    end
  end
  return most
end

-- While the walk around is searched: its cost taken as about straight when only a little of
-- the line is blocked (a rock, a steep patch), not the long way by the roads meanwhile (which
-- showed as a U-turn away from the stop until the search was done). Else nil.
local function PendingCost(cont, x1, y1, x2, y2)
  local b = BlockedYards(cont, x1, y1, x2, y2)
  if b > R.PENDING_BLOCKED_YD then return nil end
  return Dist(x1, y1, x2, y2) + b * R.PENDING_BLOCKED_COST
end

-- Squared distance from (x, y) to segment a-b, and the parameter of the closest point.
local function SegDist2(x, y, ax, ay, bx, by)
  local vx, vy = bx - ax, by - ay
  local L2 = vx * vx + vy * vy
  local t = 0
  if L2 > 0 then t = math.max(0, math.min(1, ((x - ax) * vx + (y - ay) * vy) / L2)) end
  local dx, dy = ax + vx * t - x, ay + vy * t - y
  return dx * dx + dy * dy, t
end

local function Key(bx, by) return bx * 65536 + by end

-- Offroad mode: straight links from road node n to up to NODE_LINKS nearby road nodes over
-- passable ground, { { m, cost }, ... }. Terrain doesn't change, so they are cached.
-- Road nodes by NODE_BUCKET cell: { [Key(kx, ky)] = { n, ... } }.
local function NodeBuckets(g)
  if not g.nodeBuckets then
    local b = {}
    for m = 1, g.count do
      Breathe(m, 1000)
      local k = Key(math.floor(g.n[m * 2 - 1] / NODE_BUCKET), math.floor(g.n[m * 2] / NODE_BUCKET))
      b[k] = b[k] or {}
      b[k][#b[k] + 1] = m
    end
    g.nodeBuckets = g.nodeBuckets or b
  end
  return g.nodeBuckets
end

-- Road nodes within `maxd` yards of (x, y): { { n, yards }, ... }, nearest first.
local function NodesNear(g, x, y, maxd)
  local buckets = NodeBuckets(g)
  local bx, by, reach = math.floor(x / NODE_BUCKET), math.floor(y / NODE_BUCKET), math.ceil(maxd / NODE_BUCKET)
  local list = {}
  for kx = bx - reach, bx + reach do
    for ky = by - reach, by + reach do
      for _, m in ipairs(buckets[Key(kx, ky)] or EMPTY) do
        local d = Dist(x, y, g.n[m * 2 - 1], g.n[m * 2])
        if d <= maxd then list[#list + 1] = { m, d } end
      end
    end
  end
  table.sort(list, function(a, b) return a[2] < b[2] end)
  return list
end

local function NodeLinks(g, cont, n)
  g.links = g.links or {}
  local cached = g.links[n]
  if cached then return cached end
  -- (not from or to a cave's or a city's own nodes: those are reached by their ways in)
  local inside = g.caveNode
  if inside and inside[n] then
    g.links[n] = {}
    return g.links[n]
  end
  NodeBuckets(g)
  local x, y = g.n[n * 2 - 1], g.n[n * 2]
  local bx, by, reach = math.floor(x / NODE_BUCKET), math.floor(y / NODE_BUCKET), math.ceil(R.NODE_LINK_MAX / NODE_BUCKET)
  -- the nearest NODE_LINK_TRIES nodes in each of NODE_LINKS directions (kept sorted, no full sort)
  local sectors, count, tries, maxd = {}, R.NODE_LINKS, R.NODE_LINK_TRIES, R.NODE_LINK_MAX
  local atan2, tau = math.atan2 or math.atan, 2 * math.pi
  for kx = bx - reach, bx + reach do
    for ky = by - reach, by + reach do
      local bucket = g.nodeBuckets[Key(kx, ky)]
      if bucket then
        for _, m in ipairs(bucket) do
          local mx, my = g.n[m * 2 - 1], g.n[m * 2]
          local dx, dy = mx - x, my - y
          local d = math.sqrt(dx * dx + dy * dy)
          if m ~= n and d <= maxd and not (inside and inside[m]) then
            local sector = math.floor(atan2(dy, dx) / tau * count) % count
            local list = sectors[sector]
            if not list then
              list = {}
              sectors[sector] = list
            end
            local k = #list
            if k < tries or d < list[k][2] then
              if k == tries then list[k] = nil k = k - 1 end
              while k > 0 and list[k][2] > d do
                list[k + 1] = list[k]
                k = k - 1
              end
              list[k + 1] = { m, d }
            end
          end
        end
      end
    end
  end
  -- the nearest reachable one in each direction (past rock, the next nearest)
  local links = {}
  for sector = 0, count - 1 do
    for _, nd in ipairs(sectors[sector] or EMPTY) do
      local m = nd[1]
      local mx, my = g.n[m * 2 - 1], g.n[m * 2]
      local c = ns.Passability.SegmentCost(cont, x, y, mx, my)
      if c then
        links[#links + 1] = { m, (c + HostileExtra(cont, x, y, mx, my)) * R.OFFROAD_TIE }
        break
      end
    end
  end
  g.links[n] = links
  return links
end

local function Clock() return debugprofilestop and debugprofilestop() or os.clock() * 1000 end
local linkDeadline -- (Clock() ms: the route being calculated works out node links until then)

-- Node n's links, or nil when they aren't worked out yet and this route's time for them is
-- used up: then they're worked out in the background, and the route recalculated after.
local function LinksNow(g, cont, n)
  local l = g.links and g.links[n]
  if l then return l end
  if R.SYNC_WALKS or not linkDeadline or Clock() < linkDeadline then return NodeLinks(g, cont, n) end
  g.linkQueued = g.linkQueued or {}
  if g.linkQueued[n] then return nil end
  g.linkQueued[n] = true
  local key = "links:" .. cont
  local job = walkQueued[key] and g.linkJob
  if job and job.cont == cont then
    job.want[#job.want + 1] = n
    return nil
  end
  job = { key = key, links = true, cont = cont, want = { n } }
  job.co = coroutine.create(function()
    local i = 1
    while job.want[i] do
      local m = job.want[i]
      NodeLinks(g, cont, m)
      g.linkQueued[m] = nil
      i = i + 1
      Breathe(i, 4)
    end
  end)
  g.linkJob = job
  walkQueued[key] = true
  walkJobs[#walkJobs + 1] = job
  return nil
end

-- Road segments bucketed on a SEG_BUCKET grid, with how far along its edge each starts, each bucket a flat list of
-- three numbers a segment: [key] = { edge, i (index of the segment's first point in e), along, edge, i, along, ... }.
-- (A table a segment was 13 MB of the two continents' 41 under the game's Lua 5.1, 2026-10-06; flat, about half.)
local SEG_BUCKET = 50
local function SegIndex(g)
  if g.segIndex then return g.segIndex end
  local idx = {}
  for ei, e in ipairs(g.e) do
    Breathe(ei, 200)
    if g.drops and g.drops[ei] then e = { 0, 0, 0, 0 } end -- (not a road to get on or off at)
    local along = 0
    for i = 5, #e - 3, 2 do
      local ax, ay, bx, by = e[i], e[i + 1], e[i + 2], e[i + 3]
      for kx = math.floor(math.min(ax, bx) / SEG_BUCKET), math.floor(math.max(ax, bx) / SEG_BUCKET) do
        for ky = math.floor(math.min(ay, by) / SEG_BUCKET), math.floor(math.max(ay, by) / SEG_BUCKET) do
          local k = Key(kx, ky)
          local b = idx[k]
          if not b then
            b = {}
            idx[k] = b
          end
          local n = #b
          b[n + 1], b[n + 2], b[n + 3] = ei, i, along
        end
      end
      along = along + Dist(ax, ay, bx, by)
    end
  end
  g.segIndex = g.segIndex or idx
  return g.segIndex
end

-- Whether (x, y) is within ON_ROAD_YD of a road (not a cave's: under the land a leg crosses), by the segment index's
-- buckets round it. (An index of its own, a table a segment, padded, was 13 MB of the continents' graphs, 2026-10-06.)
local function OnRoad(g, x, y)
  local idx = SegIndex(g)
  local r2 = R.ON_ROAD_YD * R.ON_ROAD_YD
  local bx, by = math.floor(x / SEG_BUCKET), math.floor(y / SEG_BUCKET)
  local reach = math.ceil(R.ON_ROAD_YD / SEG_BUCKET)
  for kx = bx - reach, bx + reach do
    for ky = by - reach, by + reach do
      local b = idx[Key(kx, ky)]
      if b then
        for j = 1, #b - 2, 3 do
          local ei, i = b[j], b[j + 1]
          if not (g.cave and g.cave[ei]) and not (g.attached and g.attached[ei]) then -- (nor an attached building's)
            local e = g.e[ei]
            if SegDist2(x, y, e[i], e[i + 1], e[i + 2], e[i + 3]) <= r2 then return true end
          end
        end
      end
    end
  end
  return false
end

R.NEAREST_MAX_RINGS = 240 -- SEG_BUCKET rings searched (12 km) before scanning everything
R.NEAREST_ENOUGH = 32 -- ... or once this many edges are found and the next ring is past the farthest of them
-- (the routes try ENTRY_CANDIDATES of them; a dense city, Stormwind, has thousands within ENTRY_SLACK,
-- and gathering and sorting them all made a reroute there a frame's time)

-- The closest point of the road edges near (x, y) to it, nearest first: every edge within
-- ENTRY_SLACK of the nearest one (enough for getting on/off the road).
-- { { edge, px, py, dist, along = yards from the edge's first node }, ... }
-- A road's height `along` yards from its first node (a dungeon's roads: from its ends'), or nil.
function R.EdgeZ(g, ei, along)
  local e = g and g.z and g.e[ei]
  if not e then return nil end
  local za, zb = g.z[e[1]], g.z[e[2]]
  if not za or not zb then return za or zb end
  return za + (zb - za) * math.max(0, math.min(1, along / math.max(e[3], 1)))
end

-- The heights of the roads within `r` of (x, y) on a level whose roads have them (Undercity's, a dungeon's):
-- { { z =, d = }, ... }, nearest first; nil on a level without (Nav.TrackCityZ follows the player's floor by them).
-- (and on a continent, its buildings' and capitals' roads by their nodes' floor heights, g.nz: Data/Indoors.lua,
-- asked 2026-10-06; the land's roads have none)
-- Each stretch of road near gives its height, not each road its nearest point: a spiral stair is one road whose turns
-- lie over each other, and its nearest point was always the lowest turn's. Up Orgrimmar's Wind Rider tower the floor
-- followed fell back to it, the arrow pointed back down the stairs and the master was never reached (a test walk,
-- 2026-10-08).
-- `flat`: the road's ends within FLAT_Z of each other (a floor's road, a door's way out), else it climbs (stairs, a ramp).
R.FLAT_Z = 0.5
function R.HeightsNear(cont, x, y, r)
  local g = GraphQuery(cont, x, y)
  if not (g and (g.z or g.nz)) then return nil end
  -- (its index not built yet, asked in the frame: none yet, the index built in the background's slices. Built here it
  -- was a 37 ms frame walking in Brill after a login; with G-Sync and V-Sync off a frame that long tears the screen,
  -- website issue #548)
  if not g.segIndex and R.WARM and not R.SYNC_WALKS and not CanYield() then
    R.Background("segIndex:" .. tostring(cont), function() SegIndex(g) end)
    return nil
  end
  local idx = SegIndex(g)
  local out, seen, r2 = {}, {}, r * r
  local bx, by, reach = math.floor(x / SEG_BUCKET), math.floor(y / SEG_BUCKET), math.ceil(r / SEG_BUCKET)
  for kx = bx - reach, bx + reach do
    for ky = by - reach, by + reach do
      local b = idx[Key(kx, ky)]
      for j = 1, b and #b - 2 or 0, 3 do
        local ei, i, along = b[j], b[j + 1], b[j + 2]
        local sk = ei * 100000 + i
        if not seen[sk] then -- (a stretch over two buckets is in both)
          seen[sk] = true
          local e = g.e[ei]
          local ax, ay, cx, cy = e[i], e[i + 1], e[i + 2], e[i + 3]
          local d2, t = SegDist2(x, y, ax, ay, cx, cy)
          if d2 <= r2 then
            local at = along + Dist(ax, ay, cx, cy) * t
            local z
            if g.z then z = R.EdgeZ(g, ei, at) else z = R.RoadFloor(g, { edge = ei, along = at }) end
            if z then
              local hz = g.z or g.nz
              local za, zb = hz[e[1]], hz[e[2]]
              -- (`stair`: a stairs road, source 6: Nav.TrackCityZ lets the floor go when lost on one)
              out[#out + 1] = { z = z, d = math.sqrt(d2), flat = not (za and zb) or math.abs(za - zb) <= R.FLAT_Z,
                stair = e[4] == R.SOURCE_STAIR, edge = ei }
            end
          end
        end
      end
    end
  end
  table.sort(out, function(a, c) return a.d < c.d end)
  return out
end

-- The roads joined to road `ei` of `cont`'s graph within `reach` yards along the roads from its ends: { [edge] = true },
-- `ei` too. Nav.TrackCityZ follows the player's floor onto these first (a walkway overhead isn't one of them).
function R.EdgesJoined(cont, ei, reach)
  local g = graphs[cont]
  local e = g and g.e and g.e[ei]
  if not (e and g.adjIdx) then return nil end
  local set, best, open = { [ei] = true }, { [e[1]] = 0, [e[2]] = 0 }, { e[1], e[2] }
  while #open > 0 do
    local n = table.remove(open)
    local d = best[n]
    for ai = g.adjIdx[n] or 0, (g.adjIdx[n + 1] or 0) - 1 do
      local se = g.adjE[ai]
      set[se >= 0 and se or -se] = true
      local m, nd = g.adjTo[ai], d + (g.adjLen[ai] or 0)
      if nd <= reach and (not best[m] or nd < best[m]) then
        best[m] = nd
        open[#open + 1] = m
      end
    end
  end
  return set
end

-- The nearer road first; the same yards off (the roads at one junction), by edge. The lists are gathered by pairs(),
-- whose order moves with the road ids, so which of two roads at a junction came first, and past ENTRY_CANDIDATES
-- which was tried at all, changed with a building's roads rebuilt far away: Brill inn's 3 fewer nodes (#846) sent a
-- walk from Tarren Mill's flight master round by the road, 34 s longer.
function R.NearerEdge(a, b) return a.dist < b.dist or (a.dist == b.dist and a.edge < b.edge) end

-- `z`: with roads with heights (a dungeon's floors), only those about at that height.
local function NearestEdgesRaw(cont, x, y, z)
  local g = GraphQuery(cont, x, y)
  if not g then return {} end
  if not g.z then z = nil end
  local idx = SegIndex(g)
  local bx, by = math.floor(x / SEG_BUCKET), math.floor(y / SEG_BUCKET)
  local best, bestD = {}, nil
  local seen = {}
  -- (counted apart: over a mine up top, the nearest may all be its tunnels, which CaveLevel then leaves
  -- out; enough of each before stopping early)
  local count, land, caved = 0, 0, 0
  for ring = 0, R.NEAREST_MAX_RINGS do
    Breathe(ring + 1, 2)
    -- cells beyond this ring are at least (ring) buckets away
    if bestD and (ring - 1) * SEG_BUCKET > bestD + R.ENTRY_SLACK then break end
    if count >= R.NEAREST_ENOUGH and ring >= 2 and land >= R.ENTRY_CANDIDATES
        and (caved == 0 or caved >= R.ENTRY_CANDIDATES) then
      local ds = {}
      for _, b in pairs(best) do ds[#ds + 1] = b.d2 end
      table.sort(ds)
      if ((ring - 1) * SEG_BUCKET) ^ 2 > ds[R.NEAREST_ENOUGH] then break end
    end
    for kx = bx - ring, bx + ring do
      for ky = by - ring, by + ring do
        if math.max(math.abs(kx - bx), math.abs(ky - by)) == ring then
          local bucket = idx[Key(kx, ky)] or {}
          for j = 1, #bucket - 2, 3 do
            local ei, i, along = bucket[j], bucket[j + 1], bucket[j + 2]
            local sk = ei * 100000 + i
            -- (an attached building's roads never: the land's nearest, and their order, as without it; R.NearAttached)
            if not seen[sk] and not (g.attached and g.attached[ei]) then
              seen[sk] = true
              local e = g.e[ei]
              local ax, ay, cx, cy = e[i], e[i + 1], e[i + 2], e[i + 3]
              local d2, t = SegDist2(x, y, ax, ay, cx, cy)
              local at = along + Dist(ax, ay, cx, cy) * t
              local ez = z and R.EdgeZ(g, ei, at)
              if not (ez and math.abs(ez - z) > R.LAYER_Z) then
                local b = best[ei]
                if not b then
                  count = count + 1
                  if g.cave[ei] then caved = caved + 1 else land = land + 1 end
                end
                if not b or d2 < b.d2 then
                  best[ei] = { edge = ei, px = ax + (cx - ax) * t, py = ay + (cy - ay) * t, d2 = d2, along = at }
                end
                if not bestD or d2 < bestD * bestD then bestD = math.sqrt(d2) end
              end
            end
          end
        end
      end
    end
  end
  if not bestD then
    if z then return R.NearestEdges(cont, x, y) end -- (none on that floor: any)
    return R.NearestEdgesAll(cont, x, y)
  end
  local list = {}
  for _, b in pairs(best) do
    b.dist = math.sqrt(b.d2)
    list[#list + 1] = b
  end
  table.sort(list, R.NearerEdge)
  return list
end

-- The nearest roads to a spot are asked for again every recalculation — the stop's exact spot every
-- time, 5 ms and more a call out in sparse country (the 2026-10-07 router profile) — so each graph's
-- answers are remembered, the exact spot and floor the key, and handed out as fresh copies: RouteOne's
-- cave branch appends to and sorts the list, and entries are written into further on. A rebuilt graph
-- is a new table, so its remembered answers go with it.
R.NEAREST_MEMO_MAX = 500
local neCache = {} -- [cont] = { g, n, map = { [key] = list } }
function R.NearestEdges(cont, x, y, z)
  local g = GraphQuery(cont, x, y)
  if not g then return {} end
  local c = neCache[cont]
  if not c or c.g ~= g then
    c = { g = g, n = 0, map = {} }
    neCache[cont] = c
  end
  local key = x .. ":" .. y .. ":" .. (z or "n")
  local hit = c.map[key]
  if not hit then
    hit = NearestEdgesRaw(cont, x, y, z)
    if c.n >= R.NEAREST_MEMO_MAX then c.map, c.n = {}, 0 end
    c.map[key], c.n = hit, c.n + 1
  end
  local out = {}
  for i, b in ipairs(hit) do
    out[i] = { edge = b.edge, px = b.px, py = b.py, d2 = b.d2, along = b.along, dist = b.dist }
  end
  return out
end

-- Whether (x, y) is down in a cave (Data/Caves.lua): over one's own cells; over its floor
-- under walkable ground, when the player's spot, only when `indoors` (IsIndoors) says so
-- (a stop there is taken to be down in it). A capital's floor under another (Data/Capitals.lua,
-- `split`: a height between the two) goes by the player's height `z` instead, when known.
R.CAVE_GAP_YD = 12 -- yards: a spot in a gap of a cave's or city's grid with its cells this near on both sides
R.CAVE_GAP_STEP = 2 -- (looked for this often out to CAVE_GAP_YD)
R.CAVE_NEAR_YD = 24 -- yards: a stop with a height in a closed hole of a floored city's grid, its cells this near (CaveNearDown)
R.CAVE_NEAR_LAND_YD = 40 -- (and taken down only with no land road this near it, its last step open)
R.CAVE_NEAR_DIRS = { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 }, { 0.7071, 0.7071 }, { 0.7071, -0.7071 }, { -0.7071, 0.7071 }, { -0.7071, -0.7071 } }
-- Whether (x, y) is over a cave's own grid (Data/Caves.lua's; not a capital's floors laid like one).
function R.InCaveGrid(cont, x, y)
  local v, o = ns.Passability.OverlayRaw(cont, x, y)
  return v ~= nil and o and o.cave and not o.capital and true or false
end
function R.CaveDown(cont, x, y, indoors, z, swimming)
  local P = ns.Passability
  local v, o = P.OverlayRaw(cont, x, y)
  if v == nil then
    -- (in a narrow gap of its grid, its cells on both sides: down as they are. The tram's way in under
    -- Ironforge, a strip with none: taken as up on the mountain, the walk there from the city went out by
    -- its gate and round through Loch Modan and the Wetlands, 10 km; reported 2026-10-01. The nearest cell each
    -- way within CAVE_GAP_YD, not only the one that far: by the Mining Trainer's door the city's cells were 1 yd
    -- off but none 12 yd out, and a route from there went over the mountain, 1284 yd for 296, a test walk 2026-10-08)
    local d = R.CAVE_GAP_YD
    if P.OverlayNear and not P.OverlayNear(cont, x - d, y - d, x + d, y + d) then return false end
    for _, s in ipairs({ { 1, 0 }, { 0, 1 } }) do
      local hit = {} -- (each way: nil not found yet, false a cell not a cave's, else the yards to a cave's)
      for k = R.CAVE_GAP_STEP, d, R.CAVE_GAP_STEP do
        for side = 1, 2 do
          if hit[side] == nil then
            local sg = side == 1 and 1 or -1
            local vk, ok = P.OverlayRaw(cont, x + sg * s[1] * k, y + sg * s[2] * k)
            if vk ~= nil then hit[side] = (ok and ok.cave) and k or false end
          end
        end
        if hit[1] ~= nil and hit[2] ~= nil then break end
      end
      if hit[1] and hit[2] then return R.CaveDown(cont, x + s[1] * hit[1], y + s[2] * hit[1], indoors, z, swimming) end
    end
    return false
  end
  if not (o and o.cave) then return false end
  -- (a capital's water: in it only while the game says the player is swimming; a stop over it, never: a trainer
  -- by a pool's edge, Orgrimmar's First Aid, was reached by a swim; a boat over it, not)
  if o.water then return swimming == true end
  -- (a floor under another's: `split`; a city under a mountain's own grid, Ironforge's: `zsplit`, its
  -- floor or the ground over it, not skipped as the floors under others are by Passability's `floors`)
  -- (a cave's floor under walkable ground parted from that ground by height, `under` (Data/Caves.lua, 2026-11-14): a
  -- spot with a height over it is up on the ground, a stop at an NPC's spot on the hill over Fargodeep Mine; with none,
  -- as before)
  if v == 3 and z and o.under and not o.capital then return z < o.under end
  local split = o.split or o.zsplit
  if v == 3 and split then
    if z then return z < split end
    return true
  end
  if v == 3 and indoors ~= nil then return indoors end
  return true
end

-- A stop with a height in a closed hole of a floored city's grid (a house left out of its cells, CaveDown's gap rule
-- finding none within CAVE_GAP_YD both ways): down as the nearest of the city's cells any way within CAVE_NEAR_YD
-- would be at that height. Gerrig Bonegrip's house in Ironforge's Forlorn Cavern, the cells 16 and 20 yd off either
-- way: taken as up, the route came to the land roads 280 yd off and ended in a straight line through the rock,
-- reported 2026-11-16. Only cells with a floor split (Ironforge's zsplit, a floor's split): the mountain over the
-- city is over it, still up. RouteBody takes it only with no land road near (CAVE_NEAR_LAND_YD, its last step open).
function R.CaveNearDown(cont, x, y, z)
  local P = ns.Passability
  if not (z and P.OverlayRaw) or P.OverlayRaw(cont, x, y) ~= nil then return false end
  local r = R.CAVE_NEAR_YD
  if P.OverlayNear and not P.OverlayNear(cont, x - r, y - r, x + r, y + r) then return false end
  for k = R.CAVE_GAP_STEP, r, R.CAVE_GAP_STEP do
    for _, s in ipairs(R.CAVE_NEAR_DIRS) do
      local cx, cy = x + s[1] * k, y + s[2] * k
      local v, o = P.OverlayRaw(cont, cx, cy)
      if v ~= nil and o and o.cave and o.capital and not o.water and (o.split or o.zsplit) then
        return R.CaveDown(cont, cx, cy, nil, z)
      end
    end
  end
  return false
end

-- The road network's pieces (joined by roads), worked out once a graph: g.piece[node] = its piece, g.shutPiece[piece]
-- = true for one of a cave's with no way out, no land road in it and no gap link from it (a chamber whose floors the
-- cave's build didn't join to its mouth: 82 on the two continents, Mulgore's Venture Co. Mine's among them; down in
-- one, every route out was "No way there found", the overnight trip sweep, 2026-10-07).
function R.Pieces(g)
  if g.piece then return g.piece, g.shutPiece end
  local piece, shut, id = {}, {}, 0
  for n = 1, g.count do
    if not piece[n] and g.adjIdx[n + 1] > g.adjIdx[n] then
      id = id + 1
      piece[n] = id
      local queue, i, open = { n }, 1, false
      while queue[i] do
        local m = queue[i]
        i = i + 1
        Breathe(i, 500)
        if g.bridges and g.bridges[m] and g.bridges[m][1] then open = true end
        for ai = g.adjIdx[m], g.adjIdx[m + 1] - 1 do -- (a node only a drop leads to may have none)
          local se = g.adjE[ai]
          if not g.cave[se >= 0 and se or -se] then open = true end
          local to = g.adjTo[ai]
          if not piece[to] then
            piece[to] = id
            queue[#queue + 1] = to
          end
        end
      end
      if not open then shut[id] = true end
    end
  end
  g.piece, g.shutPiece = piece, shut
  return piece, shut
end
-- The nodes on piece `id` of R.Pieces (counted once a graph)
function R.PieceSize(g, id)
  if not g.pieceSize then
    local piece = R.Pieces(g)
    local size = {}
    for n = 1, g.count do
      Breathe(n, 2000)
      local p = piece[n]
      if p then size[p] = (size[p] or 0) + 1 end
    end
    g.pieceSize = g.pieceSize or size
  end
  return g.pieceSize[id] or 0
end
-- (a road `ei` on a piece with no way out, R.Pieces)
function R.OnShutPiece(g, ei)
  local piece, shut = R.Pieces(g)
  local e = g.e[ei]
  return e and shut[piece[e[1]] or 0] or false
end

-- The roads to get on or off at (NearestEdges' list) by the caves: down in one, only a cave's
-- roads; outside, none of them, but for their ways out when the other end of the trip is
-- down in a cave (`wayIn`). When that leaves none nearby, from every road (x, y: the spot);
-- unchanged when none at all. `open`: only roads on a piece with a way out (R.Pieces), when one is within
-- SHUT_REACH_YD (the same cave's other chambers; past it another cave's, a line through the mountain: as before).
R.SHUT_REACH_YD = 300
R.SHUT_TOGETHER_YD = 30 -- (both ends on a chamber's roads: one of it this near each)
function R.CaveLevel(g, cont, list, down, wayIn, x, y, open)
  local P = ns.Passability
  local function Level(skipShut)
    local function keep(from)
      local out = {}
      for _, c in ipairs(from) do
        local cave = g.cave[c.edge]
        if skipShut and cave and R.OnShutPiece(g, c.edge) then -- (a chamber with no way out: not to get on or off at)
        elseif down then
          if cave then out[#out + 1] = c end
        elseif not cave then
          out[#out + 1] = c
        elseif wayIn then
          local v, o = P.OverlayRaw(cont, c.px, c.py)
          if not (v ~= nil and o and o.cave) then out[#out + 1] = c end
        end
      end
      return out[1] and out
    end
    -- (every road's nearest, of those the rule can keep: g.cave's down there, else the land's, or a cave's way in)
    return keep(list) or (x and keep(R.NearestEdgesAll(cont, x, y, function(ei)
      if skipShut and g.cave[ei] and R.OnShutPiece(g, ei) then return false end
      if down then return g.cave[ei] end
      return not g.cave[ei] or wayIn
    end)))
  end
  if open and x then
    -- (and a way there from the spot: straight over open ground, or a walk round it found or being searched; not a line
    -- through the rock to another cave's roads, never drawn for a way there isn't: Woodpaw Den's was 294 yd)
    local out = Level(true)
    local c = out and out[1]
    if c and (c.dist or 0) <= R.SHUT_REACH_YD then
      local ok = not (P and P.SegmentCost) or P.SegmentCost(cont, x, y, c.px, c.py) ~= nil
      if not ok and P.FindPath then
        local w, _, searching = Walk(cont, x, y, c.px, c.py, false)
        ok = w ~= nil or searching or false
      end
      if ok then return out end
    end
  end
  return Level(false) or list
end

-- Of `list` (NearestEdges'), the roads on the floor of height z: a capital's (its nodes' floor heights,
-- g.nz) within STOP_FLOOR_Z of it (not one with none known, the land's), within STOP_FLOOR_REACH more than the
-- nearest road (a stop with no road on its floor near: as the nearest, not a far one: Ironforge's
-- Paladin trainer on a balcony with no road went 481 yd straight); `list` when none is.
-- Of those, the floor nearest z (FLOOR_PICK_Z of the best): a building's floors are 6 or 7 yd apart, within
-- STOP_FLOOR_Z of each other (Brill's inn, 2026-10-06: the ground floor's road taken for a trainer upstairs).
R.STOP_FLOOR_Z, R.STOP_FLOOR_REACH, R.FLOOR_PICK_Z = 8, 40, 2
R.SAME_FLOOR_Z = 3 -- (two roads' floors this near in height: the same floor; a building's are 6 or 7 yd apart)
-- `x, y`: the spot `list` is of. A road that climbs is taken at its stretch on the floor of height z, not its nearest
-- point: a spiral stair is one road whose turns lie over each other, and its nearest point was the turn under the
-- player's, so from partway down Darnassus's spiral to the Rogue Trainer the route left the stairs for the land's road
-- and climbed back up to the top first (issue #40).
function R.OnFloor(g, list, z, x, y)
  local out, near, best = {}, math.huge, math.huge
  local moved = false
  if x and y then
    for _, c in ipairs(list) do moved = R.AtFloor(g, c, x, y, z) or moved end
  end
  for _, c in ipairs(list) do near = math.min(near, c.dist or math.huge) end
  for _, c in ipairs(list) do
    -- (only a capital's roads, with their heights: not the land's over it, Dun Morogh's over Ironforge; the height at
    -- the road's point nearest the stop, not its best end: a road climbing between floors, Goldshire's inn's, counted
    -- as upstairs by its top, and the route came to its foot and walked straight up through the ceiling, 2026-10-06)
    local h = R.RoadFloor(g, c)
    local fd = h and math.abs(h - z) or math.huge
    if fd <= R.STOP_FLOOR_Z and (c.dist or math.huge) <= near + R.STOP_FLOOR_REACH then
      out[#out + 1] = c
      c.floorOff = fd
      best = math.min(best, fd)
    end
  end
  local kept = {}
  for _, c in ipairs(out) do
    if c.floorOff <= best + R.FLOOR_PICK_Z then kept[#kept + 1] = c end
  end
  if moved then
    table.sort(kept, R.NearerEdge)
    table.sort(list, R.NearerEdge)
  end
  return kept[1] and kept or list
end

-- A road candidate `c` (NearestEdges') of the spot (x, y) whose road climbs (its ends' g.nz more than FLAT_Z apart)
-- and whose point is off the floor of height z by more than SAME_FLOOR_Z: moved to the nearest point of the road
-- within SAME_FLOOR_Z of z, if there's one. True when moved.
function R.AtFloor(g, c, x, y, z)
  local e = c and g and g.nz and g.e[c.edge]
  if not e then return false end
  local za, zb = g.nz[e[1]], g.nz[e[2]]
  if not (za and zb) or math.abs(za - zb) <= R.FLAT_Z then return false end
  local h = R.RoadFloor(g, c)
  if h and math.abs(h - z) <= R.SAME_FLOOR_Z then return false end
  local along, bestD2, bx, by, bat = 0, nil, nil, nil, nil
  for i = 5, #e - 3, 2 do
    local ax, ay, cx, cy = e[i], e[i + 1], e[i + 2], e[i + 3]
    local L = Dist(ax, ay, cx, cy)
    local d2, t = SegDist2(x, y, ax, ay, cx, cy)
    local at = along + L * t
    local hz = R.RoadFloor(g, { edge = c.edge, along = at })
    if (not bestD2 or d2 < bestD2) and hz and math.abs(hz - z) <= R.SAME_FLOOR_Z then
      bestD2, bx, by, bat = d2, ax + (cx - ax) * t, ay + (cy - ay) * t, at
    end
    along = along + L
  end
  if not bestD2 then return false end
  c.px, c.py, c.along, c.d2, c.dist = bx, by, bat, bestD2, math.sqrt(bestD2)
  c.atFloor = z -- (RouteOne's alongPoints: none of this road's points off that floor)
  return true
end

-- The floor height of a road candidate `c` (NearestEdges'): its ends' heights (g.nz: a capital's or a building's
-- road), at its point along it; nil for the land's.
function R.RoadFloor(g, c)
  local e = c and g and g.nz and g.e[c.edge]
  if not e then return nil end
  local za, zb = g.nz[e[1]], g.nz[e[2]]
  if za and zb then return za + (zb - za) * math.max(0, math.min(1, (c.along or 0) / math.max(e[3], 1))) end
  return za or zb
end

-- Whether (x, y) is on a capital's own cells (Data/Capitals.lua: its grid over the continent's).
-- Whether (x, y) is in a cave with floors over floors (Data/Caves.lua's `layered`: roads on every floor, their
-- heights; asked 2026-11-14), where a spot with a height is on its floor as in a building with its inside.
function R.InLayeredCave(cont, x, y)
  local P = ns.Passability
  if not (P and P.OverlayRaw and x) then return false end
  local v, o = P.OverlayRaw(cont, x, y)
  return v ~= nil and o ~= nil and o.layered == true and not o.capital
end
-- A spot with its floors by height: in a building with its inside, or down in a cave with floors over floors (with
-- a height `z`, by it: on the ground over the cave, not).
-- The start's road candidates (NearestEdges') without those on a raised road (g.raised: a bridge's, a floor's over the
-- land), when a road not raised is within RAISED_UNDER_YD more than the nearest: the player on the ground, no floor
-- followed (Nav.TrackRaisedZ follows one onto a bridge from its end). Else the list as it was. `nearer`: only when the
-- road not raised is as near as the raised one (a stop with no height: on a bridge when nearest it).
R.RAISED_UNDER_YD = 40
-- ... unless the map's ground where the spot is lies about at a raised road's height there (RAISED_GROUND_Z): up there
-- with it, a mesa's top and the bridge off it (Kooki3z 2026-11-20, Freewind Post: from the mesa's top the bridge was
-- left out for the canyon road 130 yd below, and the route walked off the cliff).
R.RAISED_GROUND_Z = 8
-- The map's ground height at (x, y) of `cont` (Ground.lua: the terrain's heights, the road tools open or not), or nil.
function R.GroundZ(cont, x, y)
  local GD = ns.Ground
  if not (GD and GD.At and cont and x and y) then return nil end
  local was = GD.force
  GD.force = true
  local ok, h = pcall(GD.At, ns.Geo and ns.Geo.Base and ns.Geo.Base(cont) or cont, x, y)
  GD.force = was
  return ok and type(h) == "number" and h or nil
end
function R.OffRaised(g, list, nearer, cont, x, y)
  if not (g and g.raised and list and list[1]) then return list end
  local gz = R.GroundZ(cont, x, y)
  if gz then
    for _, c in ipairs(list) do
      local h = g.raised[c.edge] and R.RoadFloor(g, c)
      if h and math.abs(h - gz) <= R.RAISED_GROUND_Z then return list end -- (on the ground up there with it)
    end
  end
  local near, out = math.huge, {}
  for _, c in ipairs(list) do near = math.min(near, c.dist or math.huge) end
  if nearer then
    local ground = math.huge
    for _, c in ipairs(list) do
      if not g.raised[c.edge] then ground = math.min(ground, c.dist or math.huge) end
    end
    if ground > near then return list end
  end
  local any = false
  for _, c in ipairs(list) do
    if g.raised[c.edge] then any = true
    elseif (c.dist or math.huge) <= near + R.RAISED_UNDER_YD then out[#out + 1] = c end
  end
  return (any and out[1]) and out or list
end

-- Whether (x, y) at height z is on a raised road of graph `g` (within RAISED_ON_YD, its floor within SAME_FLOOR_Z).
R.RAISED_ON_YD = 8
function R.OnRaised(g, cont, x, y, z)
  if not (g and g.raised and z) then return false end
  for _, h in ipairs(R.RaisedNear(cont, x, y, R.RAISED_ON_YD) or {}) do
    if h.z and math.abs(h.z - z) <= R.SAME_FLOOR_Z then return true end
  end
  return false
end

-- The raised roads (g.raised) near (x, y) of `cont`, within `r`: { { edge, z (its floor there), d (yards off it), endD
-- (yards from the nearer of its ends that meet the land, g.raisedEnd; math.huge with none) }, ... }, nearest first; nil
-- with none on the graph.
function R.RaisedNear(cont, x, y, r)
  -- (the graph as built: never built for this, nor warmed up; asked every status tick by Nav.TrackRaisedZ)
  local g = graphs[cont]
  if not (g and g.raised and g.nz) then return nil end
  local out = {}
  for ei in pairs(g.raised) do
    local e = g.e[ei]
    local d2, along = Closest(e, x, y)
    if d2 and d2 <= r * r then
      local endD = math.huge
      for k, nd in ipairs({ e[1], e[2] }) do
        if g.raisedEnd and g.raisedEnd[nd] then
          local nx, ny = e[k == 1 and 5 or #e - 1], e[k == 1 and 6 or #e]
          endD = math.min(endD, math.sqrt((nx - x) ^ 2 + (ny - y) ^ 2))
        end
      end
      out[#out + 1] = { edge = ei, z = HeightOn(g.nz, e, along), d = math.sqrt(d2), endD = endD }
    end
  end
  table.sort(out, function(a, b) return a.d < b.d or (a.d == b.d and a.edge < b.edge) end)
  return out
end

function R.OnFloors(cont, x, y, z)
  if ns.Nav and ns.Nav.InBuilding and ns.Nav.InBuilding(cont, x, y, "joined") then return true end
  return R.InLayeredCave(cont, x, y) and (z == nil or R.CaveDown(cont, x, y, nil, z)) or false
end

function R.CapitalAt(cont, x, y)
  local P = ns.Passability
  if not (P and P.OverlayRaw) then return false end
  local v, o = P.OverlayRaw(cont, x, y)
  return v ~= nil and o ~= nil and o.capital == true
end

-- What a route's road is in at (x, y) (asked 2026-11-12 for 1.2.4: "consider say when to enter a cave or cross a
-- bridge or go into a building", Turns' T.Places): "cave" on a cave's own roads down in it (not a capital's floor
-- under another: Data/Capitals.lua's are laid like a cave's), "building" on a building's inside roads (Data/Indoors.lua),
-- false on any other road. nil with no road within PLACE_ROAD_YD of the spot (a route's piece off the roads: can't tell).
R.PLACE_ROAD_YD = 1.5
-- (each spot's answer kept with its graph, by its exact coordinates: the directions ask again for every stretch of the
-- route each time it's trimmed as the player goes on, every 2 yd, and a nearest-road search a stretch was 20-30 ms
-- in Orgrimmar, the map's panel and the arrow each: heavy stuttering running through it, 2026-11-13)
R.PLACE_MEMO_MAX = 20000
local function PlaceLookup(g, cont, x, y)
  local c = R.NearestEdges(cont, x, y)[1]
  if not c or c.dist > R.PLACE_ROAD_YD then return nil end
  local ei = c.edge
  if g.indoor and g.indoor[ei] then return "building" end
  if g.cave and g.cave[ei] then
    local P = ns.Passability
    local v, o = P.OverlayRaw(cont, x, y)
    if v ~= nil and v ~= 1 and o and o.cave and not o.capital and not o.water
        and not (P.CapitalGridAt and P.CapitalGridAt(cont, x, y)) then
      return "cave"
    end
  end
  return false
end
function R.PlaceAt(cont, x, y)
  local g = graphs[cont]
  if not g then return nil end
  local memo = g.placeMemo
  if not memo or memo.n > R.PLACE_MEMO_MAX then
    memo = { n = 0, at = {} }
    g.placeMemo = memo
  end
  local row = memo.at[x]
  local v = row and row[y]
  if v == nil then
    v = PlaceLookup(g, cont, x, y)
    if v == nil then v = 0 end -- (no road near: kept as 0)
    if not row then row = {}; memo.at[x] = row end
    row[y] = v
    memo.n = memo.n + 1
  end
  if v == 0 then return nil end
  return v
end
-- Whether (x, y), going (dx, dy) (a unit heading), is on a bridge: on the land, inside one of the game's bridge models'
-- outlines (Data/Bridges.lua: water under a road can't tell one, the marshes' roads are that too); in a capital, a
-- walkway of its open floor with none of the city's open floor BRIDGE_SIDE_YD to either side (Thunder Bluff's rope
-- bridges between the mesas, part of its city models: about 4 yd wide, the ground far below).
R.BRIDGE_SIDE_YD = { 5, 8 }
R.BRIDGE_MODEL_BUCKET = 64
R.bridgeIndex = {} -- [cont] = { list = ns.Bridges[cont], cells = { [key] = { outline, ... } } }
function R.InOutline(o, x, y)
  local inside, n = false, #o / 2
  local jx, jy = o[2 * n - 1], o[2 * n]
  for i = 1, n do
    local ix, iy = o[2 * i - 1], o[2 * i]
    if (iy > y) ~= (jy > y) and x < (jx - ix) * (y - iy) / (jy - iy) + ix then inside = not inside end
    jx, jy = ix, iy
  end
  return inside
end
function R.OnBridgeModel(cont, x, y)
  local list = ns.Bridges and ns.Bridges[cont]
  if not list then return false end
  local B = R.BRIDGE_MODEL_BUCKET
  local ix = R.bridgeIndex[cont]
  if not ix or ix.list ~= list then
    ix = { list = list, cells = {} }
    for _, o in ipairs(list) do
      local x0, x1, y0, y1 = math.huge, -math.huge, math.huge, -math.huge
      for i = 1, #o, 2 do
        x0, x1 = math.min(x0, o[i]), math.max(x1, o[i])
        y0, y1 = math.min(y0, o[i + 1]), math.max(y1, o[i + 1])
      end
      for cx = math.floor(x0 / B), math.floor(x1 / B) do
        for cy = math.floor(y0 / B), math.floor(y1 / B) do
          local k = cx * 65536 + cy
          local c = ix.cells[k] or {}
          ix.cells[k] = c
          c[#c + 1] = o
        end
      end
    end
    R.bridgeIndex[cont] = ix
  end
  for _, o in ipairs(ix.cells[math.floor(x / B) * 65536 + math.floor(y / B)] or EMPTY) do
    if R.InOutline(o, x, y) then return true end
  end
  return false
end
-- Whether the line (x1, y1)-(x2, y2) crosses a bridge model (Data/Bridges.lua) at its middle: a link over a bridge the
-- terrain grid doesn't know (Thandol Span's gorge) is no hop. 2026-11-14: with Thandol Span a hop at HOP_COST, a Horde
-- route from Tarren Mill to the Wetlands (and anyone's) became a 1.6k yd swim down the coast, drawn as one straight line.
function R.OverBridge(cont, x1, y1, x2, y2)
  if not (ns.Bridges and ns.Bridges[cont]) then return false end
  for _, t in ipairs({ 0.5, 0.35, 0.65 }) do
    if R.OnBridgeModel(cont, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t) then return true end
  end
  return false
end
function R.BridgeAt(cont, x, y, dx, dy)
  if R.OnBridgeModel(cont, x, y) then return true end
  local P = ns.Passability
  if not (P and P.OverlayRaw) then return false end
  local px, py = -dy, dx
  local v0, o0 = P.OverlayRaw(cont, x, y)
  if not (v0 == 0 and o0 and o0.capital and not o0.cave) then return false end
  for _, d in ipairs(R.BRIDGE_SIDE_YD) do
    for s = -1, 1, 2 do
      local v, o = P.OverlayRaw(cont, x + px * d * s, y + py * d * s)
      if v == 0 and o and o.capital then return false end
    end
  end
  return true
end

-- The ways out of the cave a spot is down in (its roads outside it: out of its mouths and on
-- to the land's roads), from `list` (NearestEdges' of that spot), each as its closest point
-- to (x, y) (NearestEdges' format).
function R.CaveWaysOut(g, cont, list, x, y)
  local P = ns.Passability
  local out, seen = {}, {}
  for _, c in ipairs(list) do
    local ei = c.edge
    local v, o = P.OverlayRaw(cont, c.px, c.py)
    if g.cave[ei] and not seen[ei] and not (v ~= nil and o and o.cave) then
      seen[ei] = true
      local e = g.e[ei]
      local best, along = nil, 0
      for i = 5, #e - 3, 2 do
        local ax, ay, bx, by = e[i], e[i + 1], e[i + 2], e[i + 3]
        local d2, t = SegDist2(x, y, ax, ay, bx, by)
        local seg = Dist(ax, ay, bx, by)
        if not best or d2 < best.d2 then
          best = { edge = ei, px = ax + (bx - ax) * t, py = ay + (by - ay) * t, d2 = d2, along = along + seg * t }
        end
        along = along + seg
      end
      if best then
        best.dist = math.sqrt(best.d2)
        out[#out + 1] = best
      end
    end
  end
  return out
end

-- Every edge's closest point: far from any road, or none of the roads near will do. The NEAREST_ALL_KEEP nearest,
-- nearest first; `ok(ei)`: only the edges it takes. By the segment index, ring by ring of its buckets out from (x, y),
-- till a ring can hold none nearer than the K-th found; not found within NEAREST_ALL_RING_YD, every road looked at
-- (`NearestAllScan`, the same answer). `keep`: that many instead. (Every road on the continent, 13,000 on Kalimdor, was 7 to 12 ms a call, and a
-- plan's walks checked again called it many times in the frame: 250 ms; the overnight trip sweep, 2026-10-07)
R.NEAREST_ALL_KEEP, R.NEAREST_ALL_RING_YD = 32, 1500
local function NearestAllScan(g, x, y, ok, keep)
  local list, K = {}, keep or R.NEAREST_ALL_KEEP
  for ei, e in ipairs(g.e) do
    Breathe(ei, 300)
    if not (g.drops and g.drops[ei]) and not (g.attached and g.attached[ei]) and (not ok or ok(ei)) then -- (a drop: not a road to get on or off at; nor an attached building's)
      local along, bd2, bi, bt, bAlong = 0, nil, nil, nil, nil
      for i = 5, #e - 3, 2 do
        local ax, ay, bx, by = e[i], e[i + 1], e[i + 2], e[i + 3]
        local d2, t = SegDist2(x, y, ax, ay, bx, by)
        local segLen = Dist(ax, ay, bx, by)
        if not bd2 or d2 < bd2 then bd2, bi, bt, bAlong = d2, i, t, along + segLen * t end
        along = along + segLen
      end
      if bd2 and (#list < K or bd2 < list[#list].d2) then
        local ax, ay, bx, by = e[bi], e[bi + 1], e[bi + 2], e[bi + 3]
        local c = { edge = ei, px = ax + (bx - ax) * bt, py = ay + (by - ay) * bt, d2 = bd2, along = bAlong,
          dist = math.sqrt(bd2) }
        local pos = #list + 1
        while pos > 1 and list[pos - 1].d2 > bd2 do
          list[pos] = list[pos - 1]
          pos = pos - 1
        end
        list[pos] = c
        if #list > K then list[#list] = nil end
      end
    end
  end
  return list
end
function R.NearestEdgesAll(cont, x, y, ok, keep)
  local g = GraphQuery(cont, x, y)
  if not g then return {} end
  local K, idx = keep or R.NEAREST_ALL_KEEP, SegIndex(g)
  local cx, cy = math.floor(x / SEG_BUCKET), math.floor(y / SEG_BUCKET)
  local best, found, kth, sure = {}, {}, math.huge, false -- [edge] = { d2, i, t, along }; the edges found; the K-th d2
  local buckets = 0 -- (a far ring is hundreds of buckets: in a background job, a pause by buckets, not rings)
  for ring = 0, math.ceil(R.NEAREST_ALL_RING_YD / SEG_BUCKET) do
    local near = (ring - 1) * SEG_BUCKET -- (the nearest a bucket of this ring can be to (x, y))
    if #found >= K and near > 0 and near * near > kth then
      sure = true
      break
    end
    for kx = cx - ring, cx + ring do
      local col = ring == 0 or kx == cx - ring or kx == cx + ring
      local ky = cy - ring
      while ky <= cy + ring do
        buckets = buckets + 1
        Breathe(buckets, 200)
        local bk = idx[Key(kx, ky)]
        if bk then
          for j = 1, #bk - 2, 3 do
            local ei = bk[j]
            if (not ok or ok(ei)) and not (g.attached and g.attached[ei]) then -- (nor an attached building's)
              local i, e = bk[j + 1], g.e[ei]
              local d2, t = SegDist2(x, y, e[i], e[i + 1], e[i + 2], e[i + 3])
              local c = best[ei]
              if not c then
                found[#found + 1] = ei
                best[ei] = { d2, i, t, bk[j + 2] }
              elseif d2 < c[1] then
                c[1], c[2], c[3], c[4] = d2, i, t, bk[j + 2]
              end
            end
          end
        end
        ky = ky + ((col or ky == cy + ring) and 1 or 2 * ring)
      end
    end
    if #found >= K then -- (the K-th best so far: a ring further can stop the search)
      local ds = {}
      for n, ei in ipairs(found) do ds[n] = best[ei][1] end
      table.sort(ds)
      kth = ds[K]
    end
  end
  if not sure then return NearestAllScan(g, x, y, ok, keep) end
  local list = {}
  for _, ei in ipairs(found) do
    local c, e = best[ei], g.e[ei]
    local i, t = c[2], c[3]
    local ax, ay, bx, by = e[i], e[i + 1], e[i + 2], e[i + 3]
    list[#list + 1] = { edge = ei, px = ax + (bx - ax) * t, py = ay + (by - ay) * t, d2 = c[1],
      along = c[4] + Dist(ax, ay, bx, by) * t, dist = math.sqrt(c[1]) }
  end
  table.sort(list, R.NearerEdge)
  for n = #list, K + 1, -1 do list[n] = nil end
  return list
end

-- Whether (x, y) is a road junction (a node where three or more roads meet).
function R.JunctionAt(cont, x, y)
  local g = GraphQuery(cont, x, y)
  if not g then return false end
  if not g.junctions then
    local j = {}
    for n = 1, g.count do
      if g.adjIdx[n + 1] - g.adjIdx[n] >= 3 then j[Key(math.floor(g.n[n * 2 - 1] + 0.5), math.floor(g.n[n * 2] + 0.5))] = true end
    end
    g.junctions = j
  end
  return g.junctions[Key(math.floor(x + 0.5), math.floor(y + 0.5))] or false
end

-- Whether the route's stretch (x1, y1)-(x2, y2) on `cont` goes up (1) or down (-1) stairs (a capital's
-- stairs or ramp between levels: SOURCE_STAIR, capitals.py), else nil: its middle on such a road, the
-- way along it by its ends' heights (g.nz), at least STAIR_MIN_Z apart. Turns says "Stairs up".
R.SOURCE_STAIR = 6
R.STAIR_MIN_Z = 3
R.STAIR_CELL = 8 -- yards: the cells the stairs' pieces are looked up by
R.STAIR_REACH = 2 -- yards: a stretch's middle this close to a stair road is on it
function R.StairAt(cont, x1, y1, x2, y2)
  local g = GraphQuery(cont, x1, y1)
  if not (g and g.nz) then return nil end
  local C = R.STAIR_CELL
  if not g.stairs then
    local idx = {}
    for _, e in ipairs(g.e) do
      local za, zb
      if e[4] == R.SOURCE_STAIR then za, zb = g.nz[e[1]], g.nz[e[2]] end
      if za and zb and math.abs(zb - za) >= R.STAIR_MIN_Z then
        for i = 5, #e - 3, 2 do
          local s = { e[i], e[i + 1], e[i + 2], e[i + 3], zb > za } -- (5th: along its points is up)
          local n = math.max(1, math.ceil(Dist(e[i], e[i + 1], e[i + 2], e[i + 3]) / (C / 2)))
          local seen = {}
          for k = 0, n do -- (in the cells around it too: a lookup is one cell's)
            local px, py = e[i] + (e[i + 2] - e[i]) * k / n, e[i + 1] + (e[i + 3] - e[i + 1]) * k / n
            for dx = -1, 1 do
              for dy = -1, 1 do
                local key = Key(math.floor(px / C) + dx, math.floor(py / C) + dy)
                if not seen[key] then
                  seen[key] = true
                  idx[key] = idx[key] or {}
                  table.insert(idx[key], s)
                end
              end
            end
          end
        end
      end
    end
    g.stairs = idx
  end
  local mx, my = (x1 + x2) / 2, (y1 + y2) / 2
  local list = g.stairs[Key(math.floor(mx / C), math.floor(my / C))]
  if not list then return nil end
  local best, bestD = nil, R.STAIR_REACH * R.STAIR_REACH
  for _, s in ipairs(list) do
    local d = SegDist2(mx, my, s[1], s[2], s[3], s[4])
    if d <= bestD then best, bestD = s, d end
  end
  if not best then return nil end
  local along = (x2 - x1) * (best[3] - best[1]) + (y2 - y1) * (best[4] - best[2]) >= 0
  return along == best[5] and 1 or -1
end

-- Nearest point on the road network to (x, y) (see NearestEdges).
function R.Nearest(cont, x, y)
  return R.NearestEdges(cont, x, y)[1]
end

-- Points of edge e between `from` and `to` yards along it (either direction), with the
-- end points interpolated.
local function EdgePoints(e, from, to)
  local pts, cum = {}, { 0 }
  for i = 5, #e, 2 do pts[#pts + 1] = { e[i], e[i + 1] } end
  for i = 2, #pts do cum[i] = cum[i - 1] + Dist(pts[i - 1][1], pts[i - 1][2], pts[i][1], pts[i][2]) end
  local total = cum[#cum]
  local function At(a)
    a = math.max(0, math.min(total, a))
    for i = 2, #pts do
      if cum[i] >= a then
        local seg = cum[i] - cum[i - 1]
        local t = seg > 0 and (a - cum[i - 1]) / seg or 0
        return { pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * t, pts[i - 1][2] + (pts[i][2] - pts[i - 1][2]) * t, a }
      end
    end
    return { pts[#pts][1], pts[#pts][2], total }
  end
  -- (each point's yards from the road's first node: out[k][3])
  local out = { At(from) }
  if from <= to then
    for i = 1, #pts do if cum[i] > from and cum[i] < to then out[#out + 1] = { pts[i][1], pts[i][2], cum[i] } end end
  else
    for i = #pts, 1, -1 do if cum[i] < from and cum[i] > to then out[#out + 1] = { pts[i][1], pts[i][2], cum[i] } end end
  end
  out[#out + 1] = At(to)
  return out
end

-- Binary heap keyed on f.
-- A heap of nodes by f, as two lists ({ n = nodes, f = their f }): a table an entry was a few MB of garbage a long route
-- (the overnight trip sweep, 2026-10-07: frames past 150 ms with a collection in them).
local function Push(h, node, f)
  local hn, hf = h.n, h.f
  local i = #hn + 1
  while i > 1 do
    local p = math.floor(i / 2)
    if hf[p] <= f then break end
    hn[i], hf[i] = hn[p], hf[p]
    i = p
  end
  hn[i], hf[i] = node, f
end

local function Pop(h)
  local hn, hf = h.n, h.f
  local n = #hn
  local top, lastN, lastF = hn[1], hn[n], hf[n]
  hn[n], hf[n] = nil, nil
  n = n - 1
  if n > 0 then
    local i = 1
    while true do
      local l = i * 2
      if l > n then break end
      local m = l
      if l + 1 <= n and hf[l + 1] < hf[l] then m = l + 1 end
      if hf[m] >= lastF then break end
      hn[i], hf[i] = hn[m], hf[m]
      i = m
    end
    hn[i], hf[i] = lastN, lastF
  end
  return top
end

-- Turn a list of pieces into the route result. A piece is
-- { kind, x1, y1, x2, y2 } (straight) or { kind = ROAD, edge = e, from = a1, to = a2 }.
-- Straight legs that run along a road are split, and those stretches count as road.
local function Build(g, pieces)
  local flat, kinds, length, road = {}, {}, 0, 0
  -- (a dungeon's roads with heights: each point's height, `zs`, for the stairs between floors)
  local zs = g and g.z and {} or nil
  -- (on a continent, a building's or a capital's roads' floors, g.nz: each point's, `fz` (not `zs`: not a level with
  -- heights), so following the route knows its floors: Nav's Follow, 2026-10-06, Brill's inn)
  local fz = g and not g.z and g.nz and {} or nil
  local raisedPts = {} -- (the points on a raised road, a bridge: R.Smooth cuts no corner onto or off one)
  local function add(x, y, kind, z, f)
    local n = #flat
    if n >= 2 and math.abs(flat[n - 1] - x) < 0.01 and math.abs(flat[n] - y) < 0.01 then
      if zs and z and not zs[n / 2] then zs[n / 2] = z end
      if fz and f and not fz[n / 2] then fz[n / 2] = f end
      return
    end
    if zs then zs[n / 2 + 1] = z or false end
    if fz then fz[n / 2 + 1] = f or false end
    if n >= 2 then
      local d = Dist(flat[n - 1], flat[n], x, y)
      length = length + d
      if kind == R.KIND_ROAD then road = road + d end
      kinds[#kinds + 1] = kind
    end
    flat[n + 1], flat[n + 2] = x, y
  end
  local function straight(x1, y1, x2, y2)
    local len = Dist(x1, y1, x2, y2)
    local n = math.max(1, math.ceil(len / 4))
    -- runs along the leg: { t_end, onRoad, t_start }
    local runs = {}
    for i = 0, n do
      local t = i / n
      local on = g and OnRoad(g, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t) or false
      local last = runs[#runs]
      if last and last[2] == on then last[1] = t else runs[#runs + 1] = { t, on, last and last[1] or 0 } end
    end
    -- short stretches along a road stay off-road
    local merged = {}
    for _, r in ipairs(runs) do
      local on = r[2] and (r[1] - r[3]) * len >= R.ON_ROAD_MIN
      local last = merged[#merged]
      if last and last[2] == on then last[1] = r[1] else merged[#merged + 1] = { r[1], on } end
    end
    add(x1, y1, R.KIND_OFFROAD)
    for _, r in ipairs(merged) do
      if r[1] > 0 then add(x1 + (x2 - x1) * r[1], y1 + (y2 - y1) * r[1], r[2] and R.KIND_ROAD or R.KIND_OFFROAD) end
    end
  end
  local blocked = 0 -- (yards straight over ground the terrain blocks: a leg no walk around was found for)
  local swum = 0 -- (yards on roads in a capital's water: R.SOURCE_SWIM)
  for pi, p in ipairs(pieces) do
    Breathe(pi, 12) -- (in a background job: a pause now and then)
    if p.edge then
      local kind = g.drops and g.drops[p.edge] and R.KIND_DROP or R.KIND_ROAD
      if g.e[p.edge][4] == R.SOURCE_LIFT then kind = R.LiftKind(g, p.edge, p.from <= p.to) end
      if g.e[p.edge][4] == R.SOURCE_SWIM then swum = swum + math.abs(p.to - p.from) end
      for _, q in ipairs(EdgePoints(g.e[p.edge], p.from, p.to)) do
        add(q[1], q[2], kind, zs and R.EdgeZ(g, p.edge, q[3]), fz and R.EdgeFloor(g, p.edge, q[3]))
        if g.raised and g.raised[p.edge] then raisedPts[#flat / 2] = true end
      end
    else
      if p.gap then blocked = blocked + Dist(p[2], p[3], p[4], p[5]) end
      straight(p[2], p[3], p[4], p[5])
    end
  end
  for _, hs in ipairs({ zs or false, fz or false }) do
    if hs then -- (points off the roads: the height of the nearest one on a road before, else after)
      local n, last = #flat / 2, nil
      for i = 1, n do
        if hs[i] then last = hs[i] elseif last then hs[i] = last end
      end
      for i = n, 1, -1 do
        if hs[i] then last = hs[i] elseif last then hs[i] = last end
      end
    end
  end
  if fz and not fz[1] then fz = nil end -- (none of its roads has a floor: the land's)
  return { pts = flat, kinds = kinds, length = length, road = road, zs = zs, fz = fz,
    blocked = blocked > 0 and blocked or nil, swum = swum > 0 and swum or nil, raisedPts = next(raisedPts) and raisedPts or nil }
end
-- The floor at `along` yards on road `ei` (its ends' g.nz, as R.RoadFloor), or nil.
function R.EdgeFloor(g, ei, along)
  local e = g and g.nz and g.e[ei]
  if not e then return nil end
  local za, zb = g.nz[e[1]], g.nz[e[2]]
  if za and zb then return za + (zb - za) * math.max(0, math.min(1, (along or 0) / math.max(e[3], 1))) end
  return za or zb
end

local function Straight(g, sx, sy, tx, ty)
  return Build(g, { { R.KIND_OFFROAD, sx, sy, tx, ty } })
end

-- A stop inside a city's blocked cells (a banker's booth, a counter): open floor around it,
-- the nearest one in each direction up to CITY_SNAP_YD, at most CITY_SNAP_TRIES of them.
R.CITY_SNAP_YD = 12
R.CITY_SNAP_TRIES = 2 -- (the ones nearest where the route comes from)
R.CITY_SNAP_KEEP = 25 -- yards the start may move before the spot is chosen again
R.CITY_SNAP_LEVEL = 4 -- yards: an open spot about this near the floor's height is on the same floor
local snapChosen = {}
-- (On about the same floor as there, when the city's heights say: not up or down a ledge.)
function R.OpenAround(cont, x, y, fromX, fromY)
  local Pass = ns.Passability
  local H = ns.Nav and ns.Nav.CityHeight
  -- a start: the same floor as there (not up or down a ledge); a stop (`fromX`): any floor,
  -- the spot nearest it being where one stands to reach it
  local h0 = not fromX and H and H(cont, x, y)
  local found = {}
  for pass = 1, 2 do -- (the same floor first; any open floor when there's none)
    for k = 0, 7 do
      local a = k * math.pi / 4
      for d = 1, R.CITY_SNAP_YD do
        local ox, oy = x + math.cos(a) * d, y + math.sin(a) * d
        if Pass.IsOpen(cont, ox, oy) then
          local h = h0 and H(cont, ox, oy)
          if pass == 2 or not h or math.abs(h - h0) < R.CITY_SNAP_LEVEL then found[#found + 1] = { ox, oy, d } end
          break
        end
      end
    end
    if found[1] then break end
  end
  table.sort(found, function(p, q) return p[3] < q[3] end)
  local out = {}
  local function add(p)
    if not p then return end
    for _, q in ipairs(out) do
      if Dist(p[1], p[2], q[1], q[2]) < 4 then return end
    end
    if #out < R.CITY_SNAP_TRIES then out[#out + 1] = p end
  end
  add(found[1]) -- the nearest the spot
  if fromX then -- and the nearest the way in
    local best
    for _, p in ipairs(found) do
      if not best or Dist(p[1], p[2], fromX, fromY) < Dist(best[1], best[2], fromX, fromY) then best = p end
    end
    add(best)
  end
  for _, p in ipairs(found) do add(p) end
  return out
end

local RouteOne
local entrySidesLeft = false -- (RouteOne's last search left a road out that `entrySides` would try: R.EntrySidesAgain)

-- Route from (sx, sy) to (tx, ty) on continent `cont`. opts.offroad selects offroad mode.
-- Returns { pts = { x1, y1, ... }, kinds = { kind per segment }, length, road,
-- pending (true while a terrain search it depends on is still running) }.
-- Smoothing the finished route (the map's line and the directions both follow it): a
-- short jog out and back, or a zigzag, becomes the straight line past it where that's
-- walkable (and no nearer the other faction's guards). Not a road junction's point, not
-- across a change of kind (onto a road, a ride, a drop), not down in a city, and not on
-- hilly ground (Passability.Hilly: winding there may be the way up), bar tiny wobbles.
R.SMOOTH_SPAN = 80 -- yards of route a jog may span
R.SMOOTH_RATIO = 1.2 -- route this much longer than the straight line past it: a jog
R.SMOOTH_TOL = 2.5 -- yards: points this close to the straight line past them go anyway
-- yards: a stretch whose floors (a building's or a capital's roads, the route's `fz`) differ more than this isn't
-- smoothed (the stairs keep their shape: a chord across them went through the floor; Brill's inn, 2026-10-06)
R.SMOOTH_FLOOR_Z = 1.5
local function SegDev(x, y, ax, ay, bx, by)
  local vx, vy = bx - ax, by - ay
  local L2 = vx * vx + vy * vy
  local t = L2 > 0 and math.max(0, math.min(1, ((x - ax) * vx + (y - ay) * vy) / L2)) or 0
  return math.sqrt((ax + vx * t - x) ^ 2 + (ay + vy * t - y) ^ 2)
end
function R.Smooth(cont, r)
  if not r or not r.pts or #r.pts < 6 or (ns.CityLevels and ns.CityLevels[cont]) then return r end
  local pts, kinds, fz = r.pts, r.kinds, r.fz
  local n = #pts / 2
  local function P(i) return pts[2 * i - 1], pts[2 * i] end
  local smoothable = { [R.KIND_ROAD] = true, [R.KIND_OFFROAD] = true }
  local out, ok = { pts[1], pts[2] }, {}
  local outF = fz and { fz[1] } or nil -- (the floors of the points kept)
  local i, steps = 1, 0
  while i < n do
    steps = steps + 1
    Breathe(steps, 10) -- (in a background job: a pause now and then; each step checks the ground)
    local best
    local k = kinds[i]
    if smoothable[k] then
      local along, j = 0, i
      local flo, fhi = fz and fz[i], fz and fz[i]
      while j < n and kinds[j] == k do
        local ax, ay = P(j)
        local bx, by = P(j + 1)
        along = along + Dist(ax, ay, bx, by)
        if along > R.SMOOTH_SPAN then break end
        local f = fz and fz[j + 1]
        -- (onto or off a raised road, a bridge: by its end, no corner cut up to it from the ground)
        if r.raisedPts and (r.raisedPts[j + 1] or false) ~= (r.raisedPts[i] or false) then break end
        if f and flo then
          flo, fhi = math.min(flo, f), math.max(fhi, f)
          if fhi - flo > R.SMOOTH_FLOOR_Z then break end
        end
        j = j + 1
        if j >= i + 2 then
          local x1, y1 = P(i)
          local x2, y2 = P(j)
          local chord = Dist(x1, y1, x2, y2)
          local dev, junction = 0, false
          for m = i + 1, j - 1 do
            local mx, my = P(m)
            dev = math.max(dev, SegDev(mx, my, x1, y1, x2, y2))
            if k == R.KIND_ROAD and R.JunctionAt and R.JunctionAt(cont, mx, my) then junction = true end
          end
          local jog = along >= chord * R.SMOOTH_RATIO and dev > R.SMOOTH_TOL
          if jog and ns.Passability and ns.Passability.HillyAlong and ns.Passability.HillyAlong(cont, pts, i, j) then
            jog = false -- (a climb: the winding is the way up)
          end
          if chord >= 1 and not junction and (jog or dev <= R.SMOOTH_TOL) then
            -- (strictly: no leeway at its ends, which are mid-route)
            local walk = not ns.Passability or ns.Passability.SegmentCost(cont, x1, y1, x2, y2, 0)
            -- (nor across water the route went round: a walk round a pond south of Tarren Mill was cut straight
            -- across it, open ground being all it asked, 2026-11-19. Its cost at the swim cost, not its yards)
            if type(walk) == "number" and walk > chord + 0.5 then
              local cost = 0
              for m = i, j - 1 do
                local ax, ay = P(m)
                local bx, by = P(m + 1)
                cost = cost + (ns.Passability.SegmentCost(cont, ax, ay, bx, by, 0) or Dist(ax, ay, bx, by))
              end
              if walk > cost + 0.5 then walk = nil end
            end
            if walk then
              local hs = 0
              for m = i, j - 1 do
                local ax, ay = P(m)
                local bx, by = P(m + 1)
                hs = hs + R.HostileYards(cont, ax, ay, bx, by)
              end
              if R.HostileYards(cont, x1, y1, x2, y2) <= hs + 1 then best = j end
            end
          end
        end
      end
    end
    local j = best or i + 1
    local x, y = P(j)
    out[#out + 1], out[#out + 2] = x, y
    ok[#ok + 1] = kinds[i]
    if outF then outF[#outF + 1] = fz[j] end
    i = j
  end
  if #out == #pts then return r end
  r.pts, r.kinds = out, ok
  if outF then r.fz = outF end
  local length, road = 0, 0
  for m = 1, #ok do
    local d = Dist(out[2 * m - 1], out[2 * m], out[2 * m + 1], out[2 * m + 2])
    length = length + d
    if ok[m] == R.KIND_ROAD then road = road + d end
  end
  r.length, r.road = length, road
  return r
end

-- From a floor in a building with its inside (opts.z: the player's followed floor) or to one (opts.tz: a stop upstairs),
-- RouteOne takes no straight line or walk over the terrain (`offFloor`: they went through the walls and floors), so the
-- whole trip went by the roads. The route's way out of the start's building to its first point outside it, and its way
-- into the stop's from its last point outside, kept; between them, routed again as between any two spots outside, when
-- that's OUT_GAIN_YD shorter. (From Lakeshire's town hall to Darkshire: 7.6k yd by the roads round by Westfall, 1.7k
-- over the pass; the overnight trip sweep, 2026-10-07)
R.OUT_GAIN_YD = 100
-- The route `r` worked out again with more roads tried at the stop (RouteOne's `entrySides`), when it's
-- ENTRY_SIDES_DETOUR times the straight line or longer and its search left one out: that one when it's shorter (its blocked yards at
-- BLOCKED_PENALTY), with no more hops, and settled; else nil. Not every route: in road mode a road found that way
-- beat a straight walk 220 yd shorter, Darkshire's flight master to the Brackwell Pumpkin Patch (route quality)
function R.EntrySidesAgain(cont, r, sx, sy, tx, ty, opts)
  if not R.ENTRY_SIDES or not entrySidesLeft or (opts and opts.entrySides) or not (r and r.length and r.pts) or r.pending
      or r.unconnected or r.noWay or r.length < Dist(sx, sy, tx, ty) * R.ENTRY_SIDES_DETOUR then return nil end
  local again = RouteOne(cont, sx, sy, tx, ty, setmetatable({ entrySides = true }, { __index = opts }))
  if not (again and again.length) or again.pending or again.unconnected or again.noWay
      or (again.hops or 0) > (r.hops or 0) then return nil end
  local function W(x) return x.length + (x.blocked or 0) * (R.BLOCKED_PENALTY - 1) end
  if W(again) >= W(r) then return nil end
  return again
end

-- The route `r` worked out again with the links from loose road ends (R.DeadEndLinks, `deadEnds`), when it's
-- DEAD_END_DETOUR times the straight line or longer; taken when it weighs less with no more hops. Its walks still
-- searched: `r`, provisional (asked again once they're in).
R.DEAD_END_DETOUR = 2
R.DEAD_END_PENDING_FACTOR = 1.25 -- (a loose end's link while its walk is searched: its straight yards times this)
function R.DeadEndsAgain(cont, r, sx, sy, tx, ty, opts)
  if (opts and opts.deadEnds) or not (r and r.length and r.pts) or r.pending or r.unconnected or r.noWay
      or r.length < Dist(sx, sy, tx, ty) * R.DEAD_END_DETOUR then return nil end
  local again = RouteOne(cont, sx, sy, tx, ty, setmetatable({ deadEnds = true }, { __index = opts }))
  if not (again and again.length) or again.unconnected or again.noWay then return nil end
  -- (its links' walks still searched: `r` provisional, asked again once they're in. Checked before comparing: a link
  -- waiting for its walk isn't in `again`, which is then `r`'s long way again. In game the walks run in the background,
  -- so the long way was kept as final: Orgrimmar to Zephras Isle 6.6k yd round the Barrens, AzerothGPS#420)
  local function W(x) return x.length + (x.blocked or 0) * (R.BLOCKED_PENALTY - 1) end
  local better = (again.hops or 0) <= (r.hops or 0) and W(again) < W(r)
  if again.pending then -- (the better of the two shown meanwhile, both provisional)
    if better then return again end
    r.pending = true
    return r
  end
  if not better then return nil end
  return again
end

function R.ThroughDoors(cont, r, sx, sy, tx, ty, opts)
  local Nav = ns.Nav
  if not (opts and (opts.z or opts.tz) and r and r.pts and r.kinds and #r.pts >= 6 and not r.zs and not r.noWay
      and not r.unconnected and Nav and Nav.InBuilding) then return nil end
  local bs = opts.z and Nav.InBuilding(cont, sx, sy, "joined") or nil
  local bt = opts.tz and Nav.InBuilding(cont, tx, ty, "joined") or nil
  if (not bs and not bt) or bs == bt then return nil end -- (within one building: its own roads)
  local pts, n = r.pts, #r.pts / 2
  local i, j = 1, n -- (the route's first point out of the start's building, and its last one before the stop's)
  if bs then
    i = nil
    for k = 2, n do
      if Nav.InBuilding(cont, pts[2 * k - 1], pts[2 * k], "joined") ~= bs then
        i = k
        break
      end
    end
  end
  if bt then
    j = nil
    for k = n - 1, 1, -1 do
      if Nav.InBuilding(cont, pts[2 * k - 1], pts[2 * k], "joined") ~= bt then
        j = k
        break
      end
    end
  end
  if not i or not j or i >= j then return nil end
  local o = {}
  for k, v in pairs(opts) do o[k] = v end
  if bs then o.z, o.transient, o.indoors, o.swimming = nil, nil, nil, nil end -- (from outside the building: not the player's spot)
  if bt then o.tz = nil end
  return R.Respliced(cont, r, i, j, o)
end

-- The route `r` with its points i..j routed again as between two spots outside (RouteOne, options `o`), when that's
-- OUT_GAIN_YD shorter; its way to i and from j kept (ThroughDoors', OutOfCapital's). Nil when no shorter.
function R.Respliced(cont, r, i, j, o)
  local pts, n = r.pts, #r.pts / 2
  local function Along(a, b)
    local d = 0
    for k = a, b - 1 do d = d + Dist(pts[2 * k - 1], pts[2 * k], pts[2 * k + 1], pts[2 * k + 2]) end
    return d
  end
  local head, tail = Along(1, i), Along(j, n)
  local ex, ey, nx, ny = pts[2 * i - 1], pts[2 * i], pts[2 * j - 1], pts[2 * j]
  if head + Dist(ex, ey, nx, ny) + tail >= r.length - R.OUT_GAIN_YD then return nil end -- (no shorter way possible)
  local mid = RouteOne(cont, ex, ey, nx, ny, o)
  if not (mid and mid.pts and mid.kinds) or mid.noWay or mid.unconnected
      or head + mid.length + tail >= r.length - R.OUT_GAIN_YD then return nil end
  local out, kinds, fz = {}, {}, r.fz and {} or nil
  local function Put(x, y, f)
    out[#out + 1], out[#out + 2] = x, y
    if fz then fz[#fz + 1] = f or false end
  end
  for k = 1, i do
    Put(pts[2 * k - 1], pts[2 * k], r.fz and r.fz[k])
    if k < i then kinds[#kinds + 1] = r.kinds[k] end
  end
  local mp, lastF = mid.pts, r.fz and r.fz[i] or false
  for k = 2, #mp / 2 do
    kinds[#kinds + 1] = mid.kinds[k - 1]
    Put(mp[2 * k - 1], mp[2 * k], (mid.fz and mid.fz[k]) or lastF)
  end
  for k = j + 1, n do
    kinds[#kinds + 1] = r.kinds[k - 1]
    Put(pts[2 * k - 1], pts[2 * k], r.fz and r.fz[k])
  end
  local length, road = 0, 0
  for m = 1, #kinds do
    local d = Dist(out[2 * m - 1], out[2 * m], out[2 * m + 1], out[2 * m + 2])
    length = length + d
    if kinds[m] == R.KIND_ROAD then road = road + d end
  end
  return { pts = out, kinds = kinds, length = length, road = road, fz = fz, blocked = mid.blocked,
    pending = r.pending or mid.pending }
end

local RouteBody
-- Another addon's walk for a leg (2026-11-17: a navigation mesh's walk inside a capital): R.SetLegProvider(fn),
-- fn(cont, sx, sy, tx, ty, opts) called first for every leg routed. It returns a route as R.Route's own ({ pts, kinds
-- (a kind per piece), length, road, and fz on a continent or zs on a level: each point's height }), taken as it is; nil
-- for the Router's own; or "pending" for the Router's own marked `pending` (its walk is still worked out: the route is
-- provisional, worked out again, never remembered as final). Called with pcall, so it must never yield: an error is the
-- Router's own. None set (as AzerothGPS itself never does): routes are exactly as before.
local legProvider
function R.SetLegProvider(fn) legProvider = fn end
function R.LegProvider() return legProvider end
function R.Route(cont, sx, sy, tx, ty, opts)
  if legProvider then
    local ok, got = pcall(legProvider, cont, sx, sy, tx, ty, opts or {})
    if ok and type(got) == "table" and type(got.pts) == "table" and #got.pts >= 4 and type(got.kinds) == "table" then
      return got
    end
    if ok and got == "pending" then
      local r = R.RouteOwn(cont, sx, sy, tx, ty, opts)
      if r then r.pending = true end
      return r
    end
  end
  return R.RouteOwn(cont, sx, sy, tx, ty, opts)
end
-- A trip to or from inside an attached building (Data/Indoors.lua's `attach` entries: indoors.py's phase 7, asked
-- 2026-11-21: "if routing to an NPC in the building you just get a dotted line to it through walls"): its joins aren't
-- tied into the land's roads (a split road changed which road other trips left from, which node a straight link went
-- to, and 12 sample trips by Splintertree Post, Southshore and the like came out worse), so the trip is worked out in
-- parts: on the land's roads to each of its joins (RouteBody, as to any spot on a road), and from there in along the
-- building's own roads (InsideWay), the best one in all; and the same out of the start's. A spot is
-- in one when it's in its bounds (Nav.InBuilding) with one of its own roads within ATTACH_REACH: on the spot's floor,
-- or (no height) nearer than any of the land's with the spot on a cell the buildings close. Nil when neither end is.
R.ATTACH_REACH = 12 -- yards (indoors.py's CHECK_NPC_LAST_YD)
-- The attached buildings' roads within `reach` of (x, y), nearest first: { edge, px, py, d2, along, dist } as
-- NearestEdges' (which leaves them out).
function R.NearAttached(cont, x, y, reach)
  local g = GraphQuery(cont, x, y)
  if not (g and g.attached) then return {} end
  local idx = SegIndex(g)
  local best, r2 = {}, reach * reach
  local bx, by, k = math.floor(x / SEG_BUCKET), math.floor(y / SEG_BUCKET), math.ceil(reach / SEG_BUCKET)
  for kx = bx - k, bx + k do
    for ky = by - k, by + k do
      local bk = idx[Key(kx, ky)]
      for j = 1, bk and #bk - 2 or 0, 3 do
        local ei, i, along = bk[j], bk[j + 1], bk[j + 2]
        if g.attached[ei] then
          local e = g.e[ei]
          local ax, ay, cx, cy = e[i], e[i + 1], e[i + 2], e[i + 3]
          local d2, t = SegDist2(x, y, ax, ay, cx, cy)
          if d2 <= r2 and (not best[ei] or d2 < best[ei].d2) then
            best[ei] = { edge = ei, px = ax + (cx - ax) * t, py = ay + (cy - ay) * t, d2 = d2,
              along = along + Dist(ax, ay, cx, cy) * t, dist = math.sqrt(d2) }
          end
        end
      end
    end
  end
  local list = {}
  for _, c in pairs(best) do list[#list + 1] = c end
  table.sort(list, function(a, c) return a.dist < c.dist or (a.dist == c.dist and a.edge < c.edge) end)
  return list
end
R.ATTACH_JOINS = 3 -- the nearest this many of a building's joins tried
local function AttachJoins(g, cont, x, y, z)
  local Nav, Pass = ns.Nav, ns.Passability
  if not (g and g.attached and g.attachJoin and Nav and Nav.InBuilding) then return nil end
  if not Nav.InBuilding(cont, x, y, "attach") then return nil end
  -- (with a height, one of its own roads on that floor (STOP_FLOOR_Z) within ATTACH_REACH; without, the spot on a
  -- cell the buildings close and one of its own roads nearer than any of the land's: a flight master by Splintertree
  -- Post's inn stood in its bounds on a closed cell, 15 yd from the land's road, 16 from the inn's)
  if not z and not (Pass and Pass.At and Pass.At(cont, x, y) == 2) then return nil end
  local land = R.NearestEdges(cont, x, y)[1]
  land = land and land.dist or math.huge
  local seen, queue = {}, {}
  for _, c in ipairs(R.NearAttached(cont, x, y, R.ATTACH_REACH)) do
    if g.indoor and g.indoor[c.edge] and (z or c.dist < land) then
      local h = z and R.RoadFloor(g, c)
      if not z or (h and math.abs(h - z) <= R.STOP_FLOOR_Z) then
        local e = g.e[c.edge]
        for k = 1, 2 do
          if not seen[e[k]] then seen[e[k]], queue[#queue + 1] = true, e[k] end
        end
      end
    end
  end
  if not queue[1] then return nil end
  local joins, qi = {}, 1
  while queue[qi] do
    local n = queue[qi]
    qi = qi + 1
    if g.attachJoin[n] then joins[#joins + 1] = n end
    for ai = g.adjIdx[n] or 0, (g.adjIdx[n + 1] or 0) - 1 do
      local se = g.adjE[ai]
      local m = g.adjTo[ai]
      if g.attached[se >= 0 and se or -se] and not seen[m] then seen[m], queue[#queue + 1] = true, m end
    end
  end
  if not joins[1] then return nil end
  table.sort(joins, function(a, c)
    return Dist(g.n[2 * a - 1], g.n[2 * a], x, y) < Dist(g.n[2 * c - 1], g.n[2 * c], x, y)
  end)
  for k = #joins, R.ATTACH_JOINS + 1, -1 do joins[k] = nil end
  return joins, seen
end
-- Routes `a` then `b` (b starting where a ends) as one.
local function Joined(a, b)
  local out, kinds, fz = {}, {}, (a.fz or b.fz) and {} or nil
  local function Put(x, y, f)
    local n = #out
    if n >= 2 and math.abs(out[n - 1] - x) < 0.01 and math.abs(out[n] - y) < 0.01 then return false end
    out[n + 1], out[n + 2] = x, y
    if fz then fz[#fz + 1] = f or false end
    return true
  end
  for _, r in ipairs({ a, b }) do
    local p = r.pts
    for k = 1, #p / 2 do
      if Put(p[2 * k - 1], p[2 * k], r.fz and r.fz[k]) and #out > 2 then kinds[#kinds + 1] = r.kinds[k - 1] or R.KIND_OFFROAD end
    end
  end
  if fz then -- (the land's points: the nearest floor along, as Build's)
    local last
    for i = 1, #fz do if fz[i] then last = fz[i] elseif last then fz[i] = last end end
    for i = #fz, 1, -1 do if fz[i] then last = fz[i] elseif last then fz[i] = last end end
    if not fz[1] then fz = nil end
  end
  local length, road = 0, 0
  for m = 1, #kinds do
    local d = Dist(out[2 * m - 1], out[2 * m], out[2 * m + 1], out[2 * m + 2])
    length = length + d
    if kinds[m] == R.KIND_ROAD then road = road + d end
  end
  return { pts = out, kinds = kinds, length = length, road = road, fz = fz,
    blocked = ((a.blocked or 0) + (b.blocked or 0)) > 0 and (a.blocked or 0) + (b.blocked or 0) or nil,
    pending = a.pending or b.pending or nil }
end
-- The way from join `j` along the building's own roads (`only`: its nodes) to the spot (x, y), height z: onto the
-- nearest of its rooms' roads (both ends on its floors) within ATTACH_REACH on that floor (STOP_FLOOR_Z), the least of
-- the way there and the straight last stretch (dearer past INSIDE_LEG_FREE, INSIDE_LEG_FACTOR, as RouteOne's). A route
-- (Build's), or nil.
local function InsideWay(g, cont, j, x, y, z, only)
  local cands = {}
  for _, c in ipairs(R.NearAttached(cont, x, y, R.ATTACH_REACH)) do
    local e = g.e[c.edge]
    if g.indoor and g.indoor[c.edge] and only[e[1]] then
      local h = z and R.RoadFloor(g, c)
      if not z or (h and math.abs(h - z) <= R.STOP_FLOOR_Z) then cands[#cands + 1] = c end
    end
  end
  if not cands[1] then return nil end
  -- (its roads from the join: a small search, the building's few dozen nodes)
  local dist, prev, open, done = { [j] = 0 }, {}, { j }, {}
  while #open > 0 do
    local bi = 1
    for k = 2, #open do if dist[open[k]] < dist[open[bi]] then bi = k end end
    local n = table.remove(open, bi)
    if not done[n] then
      done[n] = true
      for ai = g.adjIdx[n] or 0, (g.adjIdx[n + 1] or 0) - 1 do
        local se = g.adjE[ai]
        local ei, m = se >= 0 and se or -se, g.adjTo[ai]
        if g.attached[ei] and only[m] then
          local d = dist[n] + (g.adjLen[ai] or g.e[ei][3])
          if not dist[m] or d < dist[m] then
            dist[m], prev[m] = d, { n, ei }
            open[#open + 1] = m
          end
        end
      end
    end
  end
  local best, bestCost
  for _, c in ipairs(cands) do
    local e = g.e[c.edge]
    local last = c.dist + math.max(0, c.dist - R.INSIDE_LEG_FREE) * (R.INSIDE_LEG_FACTOR - 1)
    for k = 1, 2 do
      local n = e[k]
      if dist[n] then
        local cost = dist[n] + (k == 1 and c.along or math.max(0, e[3] - c.along)) + last
        if cost < (bestCost or math.huge) then best, bestCost = { c, n, k }, cost end
      end
    end
  end
  if not best then return nil end
  local c, n, k = best[1], best[2], best[3]
  local chain, cur = {}, n
  while prev[cur] do
    local p, ei = prev[cur][1], prev[cur][2]
    local e = g.e[ei]
    table.insert(chain, 1, { kind = R.KIND_ROAD, edge = ei, from = e[1] == p and 0 or e[3], to = e[1] == p and e[3] or 0 })
    cur = p
  end
  local e = g.e[c.edge]
  chain[#chain + 1] = { kind = R.KIND_ROAD, edge = c.edge, from = k == 1 and 0 or e[3], to = c.along }
  chain[#chain + 1] = { R.KIND_OFFROAD, c.px, c.py, x, y }
  return Build(g, chain)
end
-- Route `r` the other way round.
local function Reversed(r)
  local p, n = r.pts, #r.pts / 2
  local pts, kinds, fz = {}, {}, r.fz and {} or nil
  for k = n, 1, -1 do
    pts[#pts + 1], pts[#pts + 2] = p[2 * k - 1], p[2 * k]
    if fz then fz[#fz + 1] = r.fz[k] end
    if k > 1 then kinds[#kinds + 1] = r.kinds[k - 1] end
  end
  return { pts = pts, kinds = kinds, length = r.length, road = r.road, fz = fz }
end
function R.AttachTrip(cont, sx, sy, tx, ty, opts)
  local g = Graph(cont)
  if not (g and g.attached) then return nil end
  opts = opts or {}
  local js, ns_ = AttachJoins(g, cont, sx, sy, opts.z)
  local jt, nt = AttachJoins(g, cont, tx, ty, opts.tz)
  if not js and not jt then return nil end
  if js and jt and ns_[jt[1]] then return nil end -- (within one building: RouteOne's, as before)
  local outs, ins = { false }, { false }
  if js then
    outs = {}
    for _, j in ipairs(js) do
      local r = InsideWay(g, cont, j, sx, sy, opts.z, ns_)
      if r then outs[#outs + 1] = { j, Reversed(r) } end
    end
  end
  if jt then
    ins = {}
    for _, j in ipairs(jt) do
      local r = InsideWay(g, cont, j, tx, ty, opts.tz, nt)
      if r then ins[#ins + 1] = { j, r } end
    end
  end
  if #outs == 0 or #ins == 0 then return nil end -- (`false`: that end not in one)
  local best, bestLen
  for _, a in ipairs(outs) do
    for _, c in ipairs(ins) do
      local fx, fy = sx, sy
      if a then fx, fy = g.n[2 * a[1] - 1], g.n[2 * a[1]] end
      local ex, ey = tx, ty
      if c then ex, ey = g.n[2 * c[1] - 1], g.n[2 * c[1]] end
      local o = {}
      for k, v in pairs(opts) do o[k] = v end
      if a then o.z, o.indoors, o.transient, o.swimming = nil, nil, nil, nil end
      if c then o.tz = nil end
      local mid = RouteBody(cont, fx, fy, ex, ey, o)
      if mid and mid.pts and #mid.pts >= 2 and not mid.noWay and not mid.unconnected then
        local len = mid.length + (a and a[2].length or 0) + (c and c[2].length or 0)
        if len < (bestLen or math.huge) then best, bestLen = { a, mid, c }, len end
      end
    end
  end
  if not best then return nil end
  local r = best[2]
  if best[1] then r = Joined(best[1][2], r) end
  if best[3] then r = Joined(r, best[3][2]) end
  return r
end
function R.RouteOwn(cont, sx, sy, tx, ty, opts)
  local r = R.AttachTrip(cont, sx, sy, tx, ty, opts) or RouteBody(cont, sx, sy, tx, ty, opts)
  if r.unconnected and not r.pending then r = R.ToCaveWayIn(cont, sx, sy, tx, ty, opts) or r end
  r = R.BendRoundGuards(cont, R.Smooth(cont, r), sx, sy, tx, ty)
  return R.GuardsOverHighZones(cont, r, sx, sy, tx, ty, opts)
end

-- The other faction's guards before zones too high (asked 2026-11-14: "if there is any other route with avoid enemy
-- territory turned on we should use that instead even if higher level area walks are needed to get there"; the ride
-- check did, a walk didn't: 2026-11-16, a level 14 Horde walk from Grom'gol went through Darkshire and Lakeshire, 271 yd
-- past their guards, as the way round them crossed zones too high at LEVEL_FACTOR a yard). A walk HOSTILE_OVER_RED_YD
-- or more past guards, zones too high priced, is searched again with them free (opts.redFree); that way, as many
-- yards fewer past guards, is taken (its zones too high asked about as ever, Nav.RedOnRoute).
R.HOSTILE_OVER_RED_YD = 100
function R.WalkGuardYards(cont, r, sx, sy, tx, ty)
  local side = HostileSide()
  if not (side and r and r.pts and #r.pts >= 4) then return 0 end
  local exempt = R.HostileTownsNear(cont, side, sx, sy, tx, ty)
  local yd, pts = 0, r.pts
  for i = 1, #pts - 3, 2 do yd = yd + R.HostileYards(cont, pts[i], pts[i + 1], pts[i + 2], pts[i + 3], side, exempt) end
  return yd
end
function R.GuardsOverHighZones(cont, r, sx, sy, tx, ty, opts)
  if (opts and opts.redFree) or not r or r.pending or r.noWay or r.unconnected or not HostileSide() or not R.RedZones() then
    return r
  end
  local guard = R.WalkGuardYards(cont, r, sx, sy, tx, ty)
  if guard < R.HOSTILE_OVER_RED_YD then return r end
  local o = {}
  for k, v in pairs(opts or {}) do o[k] = v end
  o.redFree = true
  local r2 = R.Route(cont, sx, sy, tx, ty, o)
  if r2 and not r2.pending and not r2.noWay and not r2.unconnected
      and R.WalkGuardYards(cont, r2, sx, sy, tx, ty) + R.HOSTILE_OVER_RED_YD <= guard then
    r2.redOverGuards = true
    return r2
  end
  if r2 and r2.pending then r.pending = true end -- (still searched: this one meanwhile, not remembered as final)
  return r
end

-- Round a guard post, where the ground allows (asked 2026-11-14: "need to track where enemy faction guard NPCs and
-- avoid their aggro with detour suggestions to get there"; "a road that passes a guard post at a distance is fine and
-- the route bends round them"). Data/Hostile.lua has each guard's spot and patrol points, its reach the yards it
-- notices a player from (hostile.py's GUARD_YD) and how far it wanders. A stretch of the route within their reach, up to
-- BEND_MAX_YD across, goes round them instead: on the side whose way round is shorter, BEND_MARGIN yards clear of
-- their reach, over open ground (Passability) and through no other guards' reach; else it stays (red on the map,
-- Nav.HostileSpans). Not round the towns the route starts or ends in, not with the option off (Router.HostileSide),
-- not on floors over floors or in an underground city, nor on a line with no way found.
R.BEND_MAX_YD, R.BEND_OUT_YD, R.BEND_MARGIN = 400, 150, 8
function R.BendRoundGuards(cont, r, sx, sy, tx, ty)
  local side = HostileSide()
  if not (side and r and r.pts and r.kinds and #r.pts >= 4) or r.zs or r.fz or r.unconnected then return r end
  local out, outK = R.BendPts(cont, r.pts, r.kinds, side, R.HostileTownsNear(cont, side, sx, sy, tx, ty))
  if not out then return r end
  local length, road = 0, 0
  for k = 1, #out / 2 - 1 do
    local d = math.sqrt((out[2 * k + 1] - out[2 * k - 1]) ^ 2 + (out[2 * k + 2] - out[2 * k]) ^ 2)
    length = length + d
    if outK[k] == R.KIND_ROAD then road = road + d end
  end
  r.pts, r.kinds, r.length, r.road, r.bent = out, outK, length, road, true
  return r
end
-- The bends for the points `pts` ({ x, y, ... }, `kinds` a piece): new points and kinds, or nil when none.
function R.BendPts(cont, pts, kinds, side, exempt)
  local list = side and ns.Hostile and ns.Hostile[cont] and ns.Hostile[cont][side]
  local P = ns.Passability
  if not (list and pts and kinds and #pts >= 4 and P and P.SegmentCost) or (ns.CityLevels and ns.CityLevels[cont]) then
    return nil
  end
  local n = #pts / 2
  -- the route sampled every HOSTILE_STEP yards: each sample's segment, spot and the guard whose reach it's in (false:
  -- none; flat lists, no table a sample). Nothing to do when no sample is.
  local sSeg, sX, sY, sG, ns_, any = {}, {}, {}, {}, 0, false
  local step = R.HOSTILE_STEP
  for k = 1, n - 1 do
    Breathe(k, 50)
    local x1, y1, x2, y2 = pts[2 * k - 1], pts[2 * k], pts[2 * k + 1], pts[2 * k + 2]
    local d = math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)
    local m = math.max(1, math.ceil(d / step))
    local walked = kinds[k] == R.KIND_ROAD or kinds[k] == R.KIND_OFFROAD
    for j = 0, m - 1 do
      local t = j / m
      local x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
      local hit, gi = false, nil
      if walked then hit, gi = R.HostileAt(cont, x, y, side, exempt) end
      ns_ = ns_ + 1
      sSeg[ns_], sX[ns_], sY[ns_], sG[ns_] = k, x, y, hit and gi or false
      any = any or hit
    end
  end
  if not any then return nil end
  ns_ = ns_ + 1
  sSeg[ns_], sX[ns_], sY[ns_], sG[ns_] = n, pts[2 * n - 1], pts[2 * n], false
  local function Open(x1, y1, x2, y2)
    if not P.SegmentCost(cont, x1, y1, x2, y2) then return false end
    -- (no blocked cell at all on it, its ends either: SegmentCost lets a few yards at the ends by, and a bend in Dun
    -- Morogh went 36 yd over a rock there, route-check)
    local d = math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)
    local m = math.max(1, math.ceil(d / 3))
    for k = 0, m do
      if P.At(cont, x1 + (x2 - x1) * k / m, y1 + (y2 - y1) * k / m) == 2 then return false end
    end
    if P.CrossesWall and P.CrossesWall(cont, x1, y1, x2, y2) then return false end
    return R.HostileYards(cont, x1, y1, x2, y2, side, exempt) == 0
  end
  local out, outK, i, changed = {}, {}, 1, false
  local function Add(x, y, kind)
    local m = #out
    if m >= 2 and math.abs(out[m - 1] - x) < 0.05 and math.abs(out[m] - y) < 0.05 then return end
    out[m + 1], out[m + 2] = x, y
    if kind then outK[#outK + 1] = kind end
  end
  local lastSeg = 1
  Add(pts[1], pts[2])
  local function CopyTo(seg, x, y) -- (the route's own points up to segment `seg`, then (x, y) on it)
    for k = lastSeg + 1, seg do Add(pts[2 * k - 1], pts[2 * k], kinds[k - 1]) end
    Add(x, y, kinds[seg])
    lastSeg = seg
  end
  while i <= ns_ do
    if sG[i] and i > 1 then
      -- a stretch within their reach: from the sample before it to the one after
      local j = i
      while j < ns_ and sG[j] do j = j + 1 end
      local a, b = i - 1, j
      local ex, ey, xx, xy = sX[a], sY[a], sX[b], sY[b]
      local len = math.sqrt((xx - ex) ^ 2 + (xy - ey) ^ 2)
      local done = false
      if len > 1 and len <= R.BEND_MAX_YD then
        local ux, uy = (xx - ex) / len, (xy - ey) / len
        local nx, ny = -uy, ux
        -- the guards it passes (and every guard within their reach of those: a post's guards together)
        local hit, seen = {}, {}
        for q = i, j - 1 do
          local gi = sG[q]
          if gi and not seen[gi] then seen[gi], hit[#hit + 1] = true, gi end
        end
        local best, bestLen
        for _, sgn in ipairs({ 1, -1 }) do
          local off, t0, t1 = 0, math.huge, -math.huge
          for _, gi in ipairs(hit) do
            local cx, cy, rr = list[gi] - ex, list[gi + 1] - ey, list[gi + 2]
            local t, h = cx * ux + cy * uy, (cx * nx + cy * ny) * sgn
            off = math.max(off, h + rr + R.BEND_MARGIN)
            t0, t1 = math.min(t0, t - rr), math.max(t1, t + rr)
          end
          t0, t1 = math.max(0, t0), math.min(len, t1)
          if off <= R.BEND_OUT_YD then
            local p1x, p1y = ex + ux * t0 + nx * sgn * off, ey + uy * t0 + ny * sgn * off
            local p2x, p2y = ex + ux * t1 + nx * sgn * off, ey + uy * t1 + ny * sgn * off
            local way = { ex, ey, p1x, p1y, p2x, p2y, xx, xy }
            local ok, wl = true, 0
            for w = 1, 5, 2 do
              if ok and not Open(way[w], way[w + 1], way[w + 2], way[w + 3]) then ok = false end
              wl = wl + math.sqrt((way[w + 2] - way[w]) ^ 2 + (way[w + 3] - way[w + 1]) ^ 2)
            end
            if ok and (not bestLen or wl < bestLen) then best, bestLen = way, wl end
          end
        end
        if best then
          CopyTo(sSeg[a], ex, ey)
          Add(best[3], best[4], R.KIND_OFFROAD)
          Add(best[5], best[6], R.KIND_OFFROAD)
          Add(xx, xy, R.KIND_OFFROAD)
          lastSeg = sSeg[b]
          changed, done = true, true
        end
      end
      i = done and j + 1 or j
    else
      i = i + 1
    end
  end
  if not changed then return nil end
  for k = lastSeg + 1, n do Add(pts[2 * k - 1], pts[2 * k], kinds[k - 1]) end
  return out, outK
end
-- A road's price when every stretch of it past the guards can be bent round (BendPts): its yards bent, the bends at
-- the off-road price; else nil. Worked out once a road (the graph's side, no towns left out), when a search first
-- reaches it. So the search knows a road past a guard post it can go round costs only the way round: priced at
-- HOSTILE_FACTOR, a road through the Arathi Highlands past one guard lost to a 1.6k yd swim down the coast from
-- Hillsbrad to the Wetlands, drawn as one straight line (2026-11-14).
function R.BentRoadCost(g, cont, ei)
  g.bentCost = g.bentCost or {}
  local v = g.bentCost[ei]
  if v ~= nil then return v or nil end
  v = false
  local e, side = g.e[ei], g.side
  if e and side and not g.z and not (g.nz and (g.nz[e[1]] or g.nz[e[2]])) then -- (not a building's or a city's floors)
    local pts, kinds = {}, {}
    for i = 5, #e, 2 do pts[#pts + 1], pts[#pts + 2] = e[i], e[i + 1] end
    for k = 1, #pts / 2 - 1 do kinds[k] = R.KIND_ROAD end
    local out, outK = R.BendPts(cont, pts, kinds, side, nil)
    if out then
      local left, c = 0, 0
      for k = 1, #out / 2 - 1 do
        local x1, y1, x2, y2 = out[2 * k - 1], out[2 * k], out[2 * k + 1], out[2 * k + 2]
        local d = math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)
        c = c + (outK[k] == R.KIND_ROAD and d or d * R.RoadFactor(R.OFFROAD_PENALTY))
        left = left + R.HostileYards(cont, x1, y1, x2, y2, side)
      end
      if left == 0 then v = c end
    end
  end
  g.bentCost[ei] = v
  return v or nil
end

function RouteBody(cont, sx, sy, tx, ty, opts)
  local grid = ns.Terrain and ns.Terrain[cont]
  local Pass = ns.Passability
  -- (floors over floors, roads with heights, Undercity's: its grid is the top floor in each cell,
  -- no guide to where a stop on another floor stands; its roads reach the places)
  local g0 = Graph(cont)
  if g0 and g0.z then grid = nil end
  -- a city's stop inside blocked cells: to the best open spot around it, then the last step
  if grid and grid.slack and Pass and not Pass.IsOpen(cont, tx, ty) then
    local t0 = ns.PerfStart and ns.PerfStart()
    local best, bestLen, pending
    -- (the spot chosen last time, while the start is near where it was chosen from)
    local key = string.format("%d:%.0f:%.0f", cont, tx, ty)
    local c = snapChosen[key]
    local fresh = R.OpenAround(cont, tx, ty, sx, sy)
    local tries = fresh
    if c and Dist(c[1], c[2], sx, sy) <= R.CITY_SNAP_KEEP then
      -- (the spot kept, and the best one from here now: walked past the booth, the kept
      -- one can be round the far side)
      tries = { c[3] }
      local f = fresh[1]
      if f and (f[1] ~= c[3][1] or f[2] ~= c[3][2]) then tries[2] = f end
    end
    local chosen
    for _, p in ipairs(tries) do
      local r = RouteOne(cont, sx, sy, p[1], p[2], opts)
      pending = pending or r.pending
      if r.length + p[3] < (bestLen or math.huge) then
        best, bestLen, chosen = r, r.length + p[3], p
      end
    end
    if chosen and not pending and not (c and chosen == c[3]) then snapChosen[key] = { sx, sy, chosen } end
    if ns.PerfEnd then ns.PerfEnd("router: stop in a booth", t0) end
    if best then
      local n = #best.pts
      best.pts[n + 1], best.pts[n + 2] = tx, ty
      best.kinds[#best.kinds + 1] = R.KIND_OFFROAD
      best.length = bestLen
      best.pending = pending
      return best
    end
  end
  -- a start on a closed cell (a ledge's foot, beside a wall): from the nearest open floor on
  -- the same level, not across whatever closes it
  if grid and grid.slack and Pass and not Pass.IsOpen(cont, sx, sy) then
    local p = R.OpenAround(cont, sx, sy)[1]
    if p then
      local r = RouteBody(cont, p[1], p[2], tx, ty, opts)
      table.insert(r.pts, 1, sy)
      table.insert(r.pts, 1, sx)
      table.insert(r.kinds, 1, R.KIND_OFFROAD)
      r.length = r.length + p[3]
      return r
    end
  end
  entrySidesLeft = false
  local r = RouteOne(cont, sx, sy, tx, ty, opts)
  r = R.EntrySidesAgain(cont, r, sx, sy, tx, ty, opts) or r
  r = R.DeadEndsAgain(cont, r, sx, sy, tx, ty, opts) or r
  r = R.ThroughDoors(cont, r, sx, sy, tx, ty, opts) or r
  return R.OutOfCapital(cont, r, sx, sy, tx, ty, opts) or r
end

-- From a capital to a spot outside it (or back in): RouteOne takes no walk over the terrain to or from a spot on an
-- overlay's grid (its streets are the way), so past the city's gate the trip kept to the roads it reached the gate by.
-- The route's way out of the capital to its first point off every overlay's grid, and its way in from its last one,
-- kept; between them, routed again as between any two spots outside (R.Respliced). (From Orgrimmar to a stop on the
-- Southfury River's west bank, 1.1k yd from the gate: 3.9k yd by the roads round by Razor Hill and Far Watch's bridge,
-- and the flight to the Crossroads won; seen in game 2026-11-14)
function R.OutOfCapital(cont, r, sx, sy, tx, ty, opts)
  local Pass = ns.Passability
  if not (Pass and Pass.Overlay and r and r.pts and r.kinds and #r.pts >= 6 and not r.zs and not r.noWay
      and not r.unconnected) then return nil end
  local cs, ct = R.CapitalAt(cont, sx, sy), R.CapitalAt(cont, tx, ty)
  if not cs and not ct then return nil end
  local pts, n = r.pts, #r.pts / 2
  local function Outside(k) return Pass.Overlay(cont, pts[2 * k - 1], pts[2 * k]) == nil end
  -- (past the gate for good: the first point after the route's last one on a grid, and the last before its first one
  -- on the stop's side. A point in the city where its grid gives way to the continent's (Ironforge's, under the land)
  -- isn't out of it: rerouted from there, the First Aid trainer's stairs were lost)
  local i, j = 1, n
  if cs then
    i = nil
    for k = n - 1, 2, -1 do
      if not Outside(k) then break end
      i = k
    end
  end
  if ct then
    j = nil
    for k = 2, n - 1 do
      if not Outside(k) then break end
      j = k
    end
  end
  if not i or not j or i >= j then return nil end
  local o = {}
  for k, v in pairs(opts or {}) do o[k] = v end
  if cs then o.z, o.transient, o.indoors, o.swimming = nil, nil, nil, nil end -- (from outside the city: not the player's spot)
  if ct then o.tz = nil end
  return R.Respliced(cont, r, i, j, o)
end

-- A stop down in a cave with no way there found on its roads (the cave's own, as built: a floor over another's in it,
-- its ramp lost under the lower one, joined only by a drop too far to fall): to its way in nearest the stop on the
-- roads, then on to the stop. (2026-11-06, Teldrassil: from outside Ban'ethil Barrow Den, The Relics of Wakening's
-- stop in it was a line 423 yd straight over the hill; there's one way in.) Nil when the start is in that cave, or no
-- way in is reached either.
function R.ToCaveWayIn(cont, sx, sy, tx, ty, opts)
  local Pass = ns.Passability
  if not (Pass and Pass.OverlayRaw and ns.Caves and ns.Caves[cont]) then return nil end
  local v, o = Pass.OverlayRaw(cont, tx, ty)
  if v == nil or not (o and o.cave) then return nil end
  local sv, so = Pass.OverlayRaw(cont, sx, sy)
  if sv ~= nil and so == o then return nil end
  local best, bestLen
  for _, c in ipairs(ns.Caves[cont]) do
    if ns.Terrain and ns.Terrain[c[2]] == o then
      local ways = c[5] or {}
      for i = 1, #ways - 1, 2 do
        local wx, wy = ways[i], ways[i + 1]
        local r = RouteOne(cont, sx, sy, wx, wy, opts)
        local len = r.length + Dist(wx, wy, tx, ty)
        if not r.unconnected and not r.noWay and len < (bestLen or math.huge) then best, bestLen = r, len end
      end
    end
  end
  if not best then return nil end
  local n = #best.pts
  best.pts[n + 1], best.pts[n + 2] = tx, ty
  best.kinds[#best.kinds + 1] = R.KIND_OFFROAD
  best.length = bestLen
  return best
end

local redoWalks = {} -- (the walks searched for a route worked out again round a jump, the searches done at once)
-- A route worked out again (round a jump, or a hop): with the searches done at once, the tools and tests, its walks kept
-- apart from every other route's (`redoWalks`; not again inside one already apart). Its searches fill the walks'
-- memory and mark failures by rough place, so with them shared a later route came out another way than without them,
-- a sample trip weighing worse for it. In the game they're searched in the background and remembered as ever.
-- (Called in pcall only where it can't pause: the game's Lua 5.1 can't yield across a pcall, and in a background job
-- (Breathe) the pcall'd route failed at its first pause, "attempt to yield across metamethod/C-call boundary", and the
-- route round a jump worked out there was never taken; found 2026-11-14)
local apart = false
local function Apart(g, fn, ...)
  local safe = not CanYield()
  local own = R.SYNC_WALKS and not apart and redoWalks or nil
  if own then
    if own.g ~= g then own.g, own.walks, own.count, own.failed, own.byTarget = g, {}, 0, {}, {} end
    walks, own.walks = own.walks, walks
    walkCount, own.count = own.count, walkCount
    failed, own.failed = own.failed, failed
    byTarget, own.byTarget = own.byTarget, byTarget
    apart = true
  end
  local ok, r
  if safe then ok, r = pcall(fn, ...) else ok, r = true, fn(...) end
  if own then
    apart = false
    walks, own.walks = own.walks, walks
    walkCount, own.count = own.count, walkCount
    failed, own.failed = own.failed, failed
    byTarget, own.byTarget = own.byTarget, byTarget
  end
  return ok, r
end
function RouteOne(cont, sx, sy, tx, ty, opts)
  local withExtras = opts and opts.withExtras -- (worked out again round a jump: the extra far links too)
  local offroad = opts and opts.offroad
  -- yards the player may drop off a ledge (Nav: what their health survives)
  local maxDrop = opts and opts.maxDrop or (ns.Nav and ns.Nav.SafeDrop and ns.Nav.SafeDrop()) or 0
  -- (and the cliffs' ways down the same: the cliff walls', the map's ground's; Passability.SetDropMax)
  if ns.Passability and ns.Passability.SetDropMax then ns.Passability.SetDropMax(math.max(maxDrop, R.TRACK_DROP_MAX)) end
  local grid = ns.Terrain and ns.Terrain[cont]
  local cityPenalty = grid and grid.slack and R.CITY_BLOCKED_PENALTY
  -- (a blocked leg or link: a city's walls are real, and so are its ruins' up top)
  local function blockedPenalty(x1, y1, x2, y2)
    if Pass and Pass.CrossesWall and Pass.CrossesWall(cont, x1, y1, x2, y2) then return R.WALL_PENALTY end
    if cityPenalty then return cityPenalty end
    local P = ns.Passability
    if P and P.Overlay and x1 then
      for k = 0, 4 do
        if P.Overlay(cont, x1 + (x2 - x1) * k / 4, y1 + (y2 - y1) * k / 4) then return R.CITY_BLOCKED_PENALTY end
      end
    end
    if P and P.CliffAlong and x1 and P.CliffAlong(cont, x1, y1, x2, y2) then return R.CLIFF_PENALTY end
    return R.BLOCKED_PENALTY
  end
  local Pass = ns.Passability
  local g = Graph(cont)
  -- zones too high for the player: more per yard (not the ones the route starts and ends in; none with opts.redFree,
  -- R.GuardsOverHighZones' second search)
  local red = not (opts and opts.redFree) and R.RedZones() or nil
  local exempt = red and { [R.ZoneAt(cont, sx, sy)] = true, [R.ZoneAt(cont, tx, ty)] = true }
  local function Danger(zy)
    if not (red and zy) then return 0 end
    local d = 0
    for z, yd in pairs(zy) do
      if red[z] and not exempt[z] then d = d + yd end
    end
    return d * (R.LEVEL_FACTOR - 1)
  end
  local function DangerLine(x1, y1, x2, y2)
    if not red then return 0 end
    return Danger(R.ZoneYards(cont, x1, y1, x2, y2))
  end
  -- (a walk's long swim, with zones too high about: R.SWIM_DETOUR_YD) `path` its points, else the straight line
  local function SwimDetour(path, x1, y1, x2, y2)
    local swimCost = Pass and Pass.SwimCost and Pass.SwimCost() or (Pass and Pass.SWIM_COST)
    if not (red and swimCost and swimCost > 1) then return 0 end
    -- (only a swim round one: the walk's ends straight through a zone too high. An isle's swim, the Echo Isles',
    -- Theramore's, crosses none and is priced as before)
    local straight = DangerLine(x1, y1, x2, y2)
    if straight == 0 then return 0 end
    -- (and the walk itself keeps out of them: from an isle in Lordamere Lake to Light's Hope the walk swims the lake and
    -- goes on through the Plaguelands, no way round anything; the Hillsbrad coast's swim walks none of Arathi)
    if path then
      -- (its dry yards only: with the open sea closed, 1.3.10, the swim round Arathi keeps to Arathi's own coast, in it)
      local through = 0
      for i = 1, #path - 2, 2 do
        local a, b, c, d = path[i], path[i + 1], path[i + 2], path[i + 3]
        local z = DangerLine(a, b, c, d)
        if z > 0 then
          local sc, len = SegCost(cont, a, b, c, d), Dist(a, b, c, d)
          if sc and len > 0 then z = z * math.max(0, 1 - (sc - len) / (Pass.SWIM_COST - 1) / len) end
        end
        through = through + z
      end
      if through > straight * R.SWIM_DETOUR_THROUGH then return 0 end
    end
    local wet = 0
    local function add(a, b, c, d)
      local sc = SegCost(cont, a, b, c, d)
      if sc then wet = wet + math.max(0, sc - Dist(a, b, c, d)) / (swimCost - 1) end
    end
    if path then
      for i = 1, #path - 2, 2 do add(path[i], path[i + 1], path[i + 2], path[i + 3]) end
    else
      add(x1, y1, x2, y2)
    end
    if wet < R.SWIM_DETOUR_YD then return 0 end
    return wet * math.max(0, R.LEVEL_FACTOR - swimCost) -- (swimming left out: dearer than a zone too high already)
  end
  -- (the guards' towns the route starts or ends in: not paid for, R.HostileTownsNear; a stop at Dun Garok)
  local exempt = R.HostileTownsNear(cont, HostileSide(), sx, sy, tx, ty)
  R.SetLightEnds(sx, sy, tx, ty)
  local lightNear = {} -- [edge] = a point of it near the walk's ends (memo): its light ones not paid for
  local function LightNear(ei)
    local v = lightNear[ei]
    if v == nil then
      v = false
      local e = g.e[ei]
      for i = 5, #e - 1, 2 do
        if NearLightEnd(e[i], e[i + 1]) then v = true break end
      end
      lightNear[ei] = v
    end
    return v
  end
  local roadRatio = {} -- [edge] = its cost per yard past guards, the exempt towns left out (memo)
  local function RoadRatio(ei)
    local r = g and g.ratio and g.ratio[ei]
    local near = r and g.light and g.light[ei] and LightNear(ei)
    if not (r and (exempt or near)) then return r or 1 end
    local v = roadRatio[ei]
    if v == nil then
      local extra = 0
      for t, yd in pairs(g.towns and g.towns[ei] or EMPTY) do
        if not (exempt and exempt[t]) then extra = extra + yd end
      end
      v = 1 + (extra * (R.HOSTILE_FACTOR - 1) + (not near and g.light and g.light[ei] or 0)) / math.max(g.e[ei][3], 1)
      roadRatio[ei] = v
    end
    return v
  end
  local edgeDanger = {} -- [edge] = extra cost per yard (memo)
  local function EdgeDanger(ei)
    if not red then return 0 end
    local v = edgeDanger[ei]
    if v == nil then
      local e = g and g.e[ei]
      if not e then
        v = 0
      else
        -- (through Danger both ways: it holds the zones' own exempt table — the towns' shadows it here)
        local over = g.zonesOver and g.zonesOver[ei]
        if over then
          v = Danger(over) / math.max(e[3], 1)
        else
          local z = g.zoneId and g.zoneId[ei]
          v = (z and z ~= 0) and Danger({ [z] = g.zoneYd[ei] }) / math.max(e[3], 1) or 0
        end
      end
      edgeDanger[ei] = v
    end
    return v
  end
  local direct = not Pass or Pass.SegmentCost(cont, sx, sy, tx, ty)
  Breathe(1, 1)
  -- a dungeon's floors over floors (roads with heights): the start and the stop on theirs
  -- (opts.z / opts.tz), no shortcuts off the roads (the terrain grid is only the top floor),
  -- and straight only on one floor
  local layered = g and g.z and true or false
  local sz, tz = opts and opts.z, opts and opts.tz
  if layered then
    offroad = false
    if not (sz and tz and math.abs(sz - tz) <= R.LAYER_Z) then direct = nil end
  end
  -- (a stop with a height in a building with its inside (Data/Indoors.lua), or the start in one: straight only on one
  -- floor, as on a level with heights; the terrain grid is the ground's, and offroad mode went straight through the
  -- walls to a trainer upstairs in Goldshire's inn, 2026-10-06; from upstairs in Brill's inn, straight down through
  -- the floor to its First Aid trainer, the 1.1.5 test pass)
  local offFloor = false
  if not layered and g and g.nz then -- (and a cave's floors over floors: its ramps, not a line through the rock)
    -- (and on a raised road, a bridge over the land: no straight walk up onto it, or down off it but by its drops)
    local inT = tz and (R.OnFloors(cont, tx, ty, tz) or R.OnRaised(g, cont, tx, ty, tz))
    local inS = sz and (R.OnFloors(cont, sx, sy, sz) or R.OnRaised(g, cont, sx, sy, sz))
    offFloor = (inT or inS) and not (sz and tz and math.abs(sz - tz) <= R.SAME_FLOOR_Z) and true or false
    if offFloor then direct = nil end
  end
  -- (straight past the other faction's guards isn't a way to go if there's another)
  if direct and R.HostileYards(cont, sx, sy, tx, ty, nil, exempt) > 0 then direct = nil end
  Breathe(1, 1)
  -- (straight at once when it's open, unless through a zone too high for the player: then it's
  -- weighed against the ways round, below)
  local directSafe = direct and DangerLine(sx, sy, tx, ty) == 0
  -- (straight there, or its walk round on land where the line swims and that's cheaper: SwimWalk)
  local function StraightThere()
    local path = g and not layered and not R.CapitalAt(cont, sx, sy) and not R.CapitalAt(cont, tx, ty)
      and SwimWalk(cont, sx, sy, tx, ty, opts and opts.transient)
    if not path then return Straight(g, sx, sy, tx, ty) end
    local pieces = {}
    for i = 1, #path - 2, 2 do pieces[#pieces + 1] = { R.KIND_OFFROAD, path[i], path[i + 1], path[i + 2], path[i + 3] } end
    return Build(g, pieces)
  end
  if not g then return Straight(g, sx, sy, tx, ty) end
  if offroad and directSafe then return StraightThere() end
  local ss = R.NearestEdges(cont, sx, sy, layered and sz or nil)
  Breathe(1, 1) -- (in a background job: a pause between the parts; in the frame: nothing)
  local ts = R.NearestEdges(cont, tx, ty, layered and tz or nil)
  Breathe(1, 1)
  -- the caves (Data/Caves.lua): in one, on by its roads; outside, not onto them, but for a
  -- way in to a cave at the other end. Over a mine under walkable ground the player may be
  -- up top: opts.indoors, from IsIndoors, tells (under a capital's floor, opts.z: their height).
  -- (an end down in a cave over its own grid: its legs straight only, R.InCaveGrid)
  local caveEnd = {}
  if g.cave and next(g.cave) and Pass and Pass.OverlayRaw then
    local sDown = R.CaveDown(cont, sx, sy, opts and opts.indoors, opts and opts.z, opts and opts.swimming)
    local tDown = R.CaveDown(cont, tx, ty, nil, opts and opts.tz)
    caveEnd.s = sDown and R.InCaveGrid(cont, sx, sy)
    caveEnd.t = tDown and R.InCaveGrid(cont, tx, ty)
    -- (a stop in a closed hole of a city under a mountain, R.CaveNearDown: down when no land road is near with an
    -- open last step, and a cave road on the stop's floor is)
    if not tDown and opts and opts.tz and R.CaveNearDown(cont, tx, ty, opts.tz) then
      local function nearOpen(down)
        for _, c in ipairs(ts) do
          local h = down and g.nz and R.RoadFloor(g, c)
          if (g.cave[c.edge] ~= nil) == down and (c.dist or 0) <= R.CAVE_NEAR_LAND_YD
            and (not down or (h and math.abs(h - opts.tz) <= R.STOP_FLOOR_Z))
            and (not Pass.SegmentCost or Pass.SegmentCost(cont, tx, ty, c.px, c.py) ~= nil) then
            return true
          end
        end
        return false
      end
      if not nearOpen(false) and nearOpen(true) then tDown = true end
    end
    -- (the ways out of the cave at the other end, however far: a cave with no land road
    -- near its mouth is reached across the land to it)
    local sWays = tDown and not sDown and R.CaveWaysOut(g, cont, ts, sx, sy)
    local tWays = sDown and not tDown and R.CaveWaysOut(g, cont, ss, tx, ty)
    -- (a chamber's roads with no way out, R.Pieces: left out at both ends, unless both ends are on that piece: a road
    -- of it within SHUT_TOGETHER_YD of each. Not any of the start's nearest: 378 yd off, a ledge by the stop one
    -- only drops off counted as the start's too, and the stop was left on it, with no way there; Teldrassil's
    -- Ban'ethil Barrow Den, 2026-11-06)
    local piece, shut = R.Pieces(g)
    local together = false
    for _, a in ipairs(ss) do
      local pa = piece[g.e[a.edge][1]]
      if shut[pa or 0] and (a.dist or 0) <= R.SHUT_TOGETHER_YD then
        for _, b in ipairs(ts) do
          together = together or (piece[g.e[b.edge][1]] == pa and (b.dist or 0) <= R.SHUT_TOGETHER_YD)
        end
      end
    end
    ss = R.CaveLevel(g, cont, ss, sDown, tDown, sx, sy, not together)
    ts = R.CaveLevel(g, cont, ts, tDown, sDown, tx, ty, not together)
    for _, pair in ipairs({ { ss, sWays }, { ts, tWays } }) do
      local list, ways = pair[1], pair[2]
      for _, w in ipairs(ways or {}) do
        local seen = false
        for _, c in ipairs(list) do seen = seen or c.edge == w.edge end
        if not seen then list[#list + 1] = w end
      end
      table.sort(list, R.NearerEdge)
    end
  end
  -- a capital's stop with a height (a city place's: its NPC's): onto the roads on its floor, not the
  -- nearest, on a balcony or a walk over it (Ironforge's Priest trainer under the Hall of Mysteries'
  -- balcony: up its stairs and down, 2026-10-01)
  if not layered and g.nz and opts and opts.tz then ts = R.OnFloor(g, ts, opts.tz, tx, ty) end
  -- (and the player's own floor in a building, followed along its roads: Nav.TrackCityZ; asked 2026-10-06, Brill's
  -- inn: from upstairs the route started on the ground floor's road under them)
  if not layered and g.nz and opts and opts.z then ss = R.OnFloor(g, ss, opts.z, sx, sy) end
  -- (and no floor followed, on the ground, under a raised road (a bridge, a floor over the land, edited so): onto the
  -- roads under it, not up onto it overhead; it's reached by its ends, the route going round to one. Asked 2026-11-18
  -- for 1.3.10: "pathing would know if an area is accessible based on player position")
  if not layered and g.raised and not (opts and opts.z) then ss = R.OffRaised(g, ss, nil, cont, sx, sy) end
  -- (and a stop with no height by a road under one, nearer it than the raised road: not off the side of the bridge)
  if not layered and g.raised and not (opts and opts.tz) then ts = R.OffRaised(g, ts, true, cont, tx, ty) end
  -- a city: roads on the same floor as the start or the stop (the nearest may be on a
  -- walk right above or below)
  local H = not layered and grid and grid.slack and ns.Nav and ns.Nav.CityHeight
  if H then
    -- (the heights given, the game's: the player's own floor, not the top one over them, a
    -- walkway overhead; and the stop's, a trainer under one. The level's are the model's: less zoff.)
    local zoff = ns.CityLevels and ns.CityLevels[cont] and ns.CityLevels[cont].zoff
    local function sameFloor(list, x, y, around, z)
      local h0 = (z and zoff) and z - zoff or around and ns.Nav.CityFloor(cont, x, y) or H(cont, x, y)
      if not h0 then return list end
      local out = {}
      for _, c in ipairs(list) do
        local h = H(cont, c.px, c.py)
        if not h or math.abs(h - h0) < R.CITY_SNAP_LEVEL then out[#out + 1] = c end
      end
      return out[1] and out or list
    end
    ss, ts = sameFloor(ss, sx, sy, false, sz), sameFloor(ts, tx, ty, true, tz)
  end
  -- (a spot outside every building with its inside (Nav.InBuilding: its bounds and TRACK_YD) isn't on or off one's
  -- own roads straight through its walls: in by its doors' joins, from the land's roads. Sentinel Hill's tower's top
  -- floor was taken 79 yd straight from the road outside, its stairs being the longer way, 2026-10-06)
  if not layered and g.indoor and ns.Nav and ns.Nav.InBuilding then
    local function outside(list, x, y)
      if ns.Nav.InBuilding(cont, x, y, "joined") then return list end
      local out = {}
      for _, c in ipairs(list) do
        if not g.indoor[c.edge] then out[#out + 1] = c end
      end
      return out[1] and out or list
    end
    ss, ts = outside(ss, sx, sy), outside(ts, tx, ty)
  end
  local s, t = ss[1], ts[1]
  if not s or not t then return Straight(g, sx, sy, tx, ty) end
  -- (no closer to a road than to each other: straight; not in a capital, whose grid doesn't show its
  -- walls where its floor is under the land (Ironforge's: straight across the Great Forge, 2026-09-30);
  -- nor to a road on a floor of a building's (or a capital's) but from that floor: from the ground floor or
  -- outside, a trainer upstairs is up the stairs, not through the ceiling (Brill's inn, 2026-10-06))
  local tf, sf = R.RoadFloor(g, t), R.RoadFloor(g, s)
  -- (`opts.roads`, a flight master's detour, asked 2026-11-08: along the roads where they go there, not this nor the
  -- short walk straight there below; over the land only where the roads go ROAD_DIRECT_PENALTY times as far)
  local roadsFirst = opts and opts.roads
  if not offroad and not roadsFirst and directSafe and Dist(sx, sy, tx, ty) <= s.dist + t.dist
      and not R.CapitalAt(cont, sx, sy) and not R.CapitalAt(cont, tx, ty)
      and (not tf or (sf and math.abs(sf - tf) <= R.SAME_FLOOR_Z)) then
    return StraightThere()
  end

  local OFF, ROAD = R.KIND_OFFROAD, R.KIND_ROAD
  -- a terrain search this route needs is still running: it's provisional (see Nav's Route)
  local pending = false
  linkDeadline = Clock() + R.NODE_LINK_MS
  -- Off-road leg: cost and pieces. Straight where the ground allows. Getting on/off the
  -- road (`must`) otherwise walks around obstacles over the terrain grid, and as a last
  -- resort goes straight at a heavy penalty; offroad mode's extra links are just dropped.
  -- (worked out again for a hop, `hopRedo`, below: the hops priced, HOP_COST, every candidate walked, ends widened)
  local walkAll = opts and opts.hopRedo and true or false
  local function Leg(x1, y1, x2, y2, must, walk, z1, z2)
    local d = Dist(x1, y1, x2, y2)
    local c, path = d, nil
    if Pass and not layered then c = SegCost(cont, x1, y1, x2, y2) end
    -- (to or from a spot with a height in a building with its inside: dearer past INSIDE_LEG_FREE, by any way: straight,
    -- walked round or blocked. Only when straight, a walk round the building's cells from its road on the floor's far
    -- side beat the road up to the NPC's room: 36 yd to Wildhammer Keep's Harggan, 2026-10-06)
    local extra = 0
    if not layered and g and g.nz
        and ((tz and x2 == tx and y2 == ty and R.OnFloors(cont, tx, ty, tz))
          or (sz and x1 == sx and y1 == sy and R.OnFloors(cont, sx, sy, sz))) then
      extra = math.max(0, d - R.INSIDE_LEG_FREE) * (R.INSIDE_LEG_FACTOR - 1)
    end
    if layered then
      walk = false
      -- (floors over floors: the grid can't tell what's between, a wall or a gap down to the
      -- floor below; the roads can, so onto the nearest one: past a few yards, dearer; and not
      -- over a gap with no floor at any height, a canal's water, R.VoidYards)
      c = d + math.max(0, d - R.LAYER_LEG_FREE) * (R.LAYER_LEG_FACTOR - 1)
      if R.VoidYards(cont, x1, y1, x2, y2) > R.LAYER_VOID_YD
          or R.WallYards(cont, x1, y1, z1, x2, y2, z2) > R.LAYER_VOID_YD then c = nil end
    end
    -- (in a capital no walk around: the terrain grid's cells are coarser than its streets,
    -- and blind to its floors over each other; a leg there is straight, its walls real)
    local capital = not c and (R.CapitalAt(cont, x1, y1) or R.CapitalAt(cont, x2, y2))
    if capital then walk = false end
    -- (nor to or from a spot down in a cave: the terrain search doesn't see the cave's rock, and within STOP_SLACK of
    -- the stop it crossed it; Whelgar in his dig site's cave was walked to 40 yd through the rock from a road by the
    -- mouth, not along the cave's road in. Its roads lead through it; straight over its floor from them)
    if (caveEnd.t and x2 == tx and y2 == ty) or (caveEnd.s and x1 == sx and y1 == sy) then walk = false end
    local stopgap, walked = false, false
    if not c and walk and Pass and Pass.FindPath then
      local searching
      -- (an end that isn't the start or the stop is a road's point: Passability.FindPath's road1/road2)
      c, path, searching = Walk(cont, x1, y1, x2, y2, opts and opts.transient and x1 == sx and y1 == sy,
        not (x1 == sx and y1 == sy), not (x2 == tx and y2 == ty), walkAll)
      if searching then
        pending = true
        c = PendingCost(cont, x1, y1, x2, y2)
        stopgap = c ~= nil
      else
        walked = true
      end
    end
    -- (a hop: blocked straight and its walk round searched and none found, here or by an earlier route; asked
    -- 2026-11-14, "no wall hopping allowed". Not while searched: a stopgap meanwhile. Priced as one, HOP_COST, only
    -- in a route worked out again for one: the first is as before, at BLOCKED_PENALTY)
    local hop = not c and not stopgap and not cityPenalty and not capital and not layered and Pass and Pass.FindPath
      and (walked or WalkFailed(cont, x1, y1, x2, y2)) and not R.OverBridge(cont, x1, y1, x2, y2) and true or false
    local hopCost = hop and walkAll and R.HOP_COST or 0
    -- (blocked in a straight line: walked around it once searched, if the route takes it)
    local pieces = { { OFF, x1, y1, x2, y2, gap = (stopgap or not c) and not cityPenalty and not capital or nil,
      hop = hop or nil } }
    if path then
      pieces = {}
      for i = 1, #path - 2, 2 do pieces[#pieces + 1] = { OFF, path[i], path[i + 1], path[i + 2], path[i + 3] } end
    end
    local h = 0 -- (past the other faction's guards, and through zones too high for the player)
    if path then
      for i = 1, #path - 2, 2 do
        h = h + HostileExtra(cont, path[i], path[i + 1], path[i + 2], path[i + 3], exempt) + DangerLine(path[i], path[i + 1], path[i + 2], path[i + 3])
      end
    else
      h = HostileExtra(cont, x1, y1, x2, y2, exempt) + DangerLine(x1, y1, x2, y2)
    end
    if c or must then h = h + SwimDetour(path, x1, y1, x2, y2) end
    h = h + extra
    if offroad then
      if c then return (c + h) * R.OFFROAD_TIE, pieces end
      if must then return (d * blockedPenalty(x1, y1, x2, y2) + h) * R.RoadFactor(R.OFFROAD_PENALTY) + hopCost, pieces end
      return nil
    end
    return ((c or d * blockedPenalty(x1, y1, x2, y2)) + h) * R.RoadFactor(R.OFFROAD_PENALTY) + hopCost, pieces
  end
  -- (a leg that's a hop, HOP_COST: blocked straight and no walk round it)
  local function IsHop(leg) return leg and #leg == 1 and leg[1].hop and true or false end
  -- pieces a .. b .. c as one list
  local function Join(...)
    local out = {}
    for _, list in ipairs({ ... }) do
      for _, p in ipairs(list) do out[#out + 1] = p end
    end
    return out
  end

  -- (yards along part of an edge, as cost: more past the other faction's guards)
  local function part(ei, yd) return yd * (RoadRatio(ei) + EdgeDanger(ei)) end
  local START, GOAL = -1, -2
  -- (how each node was reached: from which, and by what: a list of pieces, or a road as its edge, + along it, - back)
  local gscore, cameFrom, cameBy, open, closed = { [START] = 0 }, {}, {}, { n = {}, f = {} }, {}
  local function h(n)
    if n < 0 then return 0 end
    return Dist(g.n[n * 2 - 1], g.n[n * 2], tx, ty)
  end
  local function relax(from, to, cost, by)
    if not cost then return end
    local ng = gscore[from] + cost
    if gscore[to] == nil or ng < gscore[to] - 1e-9 then
      gscore[to] = ng
      cameFrom[to], cameBy[to] = from, by
      Push(open, to, ng + h(to))
    end
  end
  -- Nearby edges to get on/off the road network: not just the nearest one, since the
  -- nearest road can lead the wrong way.
  -- (and, worked out again for a long way round (`entrySides`, R.EntrySidesAgain), at the stop the nearest within
  -- ENTRY_SLACK in each quarter round it that none of those is in, over open ground straight to it: asked 2026-11-14,
  -- a stop by the river between Duskwood and Elwynn, Elwynn's road pieces were all eight, so Duskwood's road 200 yd
  -- further never got tried and the route went round by Westfall, twice as far)
  -- (and past the ENTRY_CANDIDATES, at either end, the nearest road in each quarter round the spot that none of them is
  -- in, within ENTRY_SLACK and over open ground straight to it (`qx`, `qy`). Issue #682: a road drawn to Tarren Mill's
  -- flight master along the old one split the roads by it; the eight were all those roads, to the town's side, and the
  -- south road 204 yd off, the way south-east, wasn't one: 732 yd north through the town and back down for 388 yd)
  local function candidates(list, x, y, qx, qy)
    local out, side = {}, {}
    local function sideOf(c, ax, ay)
      ax, ay = ax or x, ay or y
      if not (ax and c.px) then return nil end
      return (c.px >= ax and 0 or 1) + (c.py >= ay and 0 or 2) -- (its quarter round the spot)
    end
    local last = #list -- (the last one looked at)
    for i, c in ipairs(list) do
      if i > R.ENTRY_CANDIDATES or c.dist > list[1].dist + R.ENTRY_SLACK then last = i - 1 break end
      out[#out + 1] = c
      local k = sideOf(c)
      if k then side[k] = true end
    end
    -- (not where ENTRY_SIDES below looks at the stop's quarters: a route worked out again for them)
    local sides = R.ENTRY_SIDES and x and list[1] and list[1].dist >= R.ENTRY_SIDES_YD
    -- (on the open land only: not in a capital, a city's or a building's floors, whose roads near are its own floors')
    if R.ENTRY_QUARTERS and qx and not sides and last < #list and last >= R.ENTRY_CANDIDATES and not layered
        and not cityPenalty and not R.CapitalAt(cont, qx, qy) and not (ns.Nav and ns.Nav.InBuilding
        and ns.Nav.InBuilding(cont, qx, qy, "joined")) then
      local quarter = {}
      for _, c in ipairs(out) do quarter[sideOf(c, qx, qy)] = true end
      for i = last + 1, #list do
        local c = list[i]
        if c.dist > list[1].dist + R.ENTRY_SLACK then break end
        local k = sideOf(c, qx, qy)
        if not quarter[k] and not (g.cave and g.cave[c.edge]) and not (g.indoor and g.indoor[c.edge]) then
          quarter[k] = true -- (the nearest only: blocked, none from that quarter)
          if not Pass or SegCost(cont, c.px, c.py, qx, qy) then out[#out + 1] = c end
        end
      end
    end
    if x then entrySidesLeft = false end
    if sides and #list > last then
      local again = opts and opts.entrySides
      for i = last + 1, #list do
        local c = list[i]
        if c.dist > list[1].dist + R.ENTRY_SLACK then break end
        local k = sideOf(c)
        if k and not side[k] then
          -- (not worked out again: only whether there's one, the ground to it judged then)
          if not again then
            entrySidesLeft = true
            break
          end
          if not (R.ENTRY_SIDES_OPEN and Pass) or SegCost(cont, c.px, c.py, x, y) then
            side[k] = true
            out[#out + 1] = c
          end
        end
      end
    end
    return out
  end

  local goalFrom = {}
  local function goalVia(n, cost, pieces)
    if cost and (not goalFrom[n] or cost < goalFrom[n][1]) then goalFrom[n] = { cost, pieces } end
  end
  -- (worked out again for a hop, `hopRedo`: every candidate's leg walked round what's in the way, not only the
  -- nearest WALK_AROUND_CANDIDATES; and an end whose every candidate is a hop tries more and further roads, the
  -- nearest HOP_WIDE_TRIES others of NearestEdgesAll's, walked too. Asked 2026-11-14: a road reachable over open
  -- ground, however far, before a hop over a wall)
  -- (and an end on roads cut off by a hop's link, `g.hopPieces`, every candidate on them: the roads off them tried too.
  -- The nearest HOP_WIDE_KEEP roads, HOP_WIDE_SPACING apart: not all of them the next few on one road beside)
  local function wider(cands, x, y, legs)
    if not walkAll or layered or cityPenalty or not cands[1] or R.CapitalAt(cont, x, y) then return {} end
    local hp = g.hopPieces
    local piece = hp and R.Pieces(g)
    local function onHop(ei) return hp and hp[piece[g.e[ei][1]] or 0] or false end
    for i, leg in ipairs(legs) do
      if not IsHop(leg) and not onHop(cands[i].edge) then return {} end
    end
    local have, out = {}, {}
    for _, c in ipairs(cands) do have[c.edge] = true end
    local all = R.NearestEdgesAll(cont, x, y, nil, R.HOP_WIDE_KEEP)
    local space2 = R.HOP_WIDE_SPACING * R.HOP_WIDE_SPACING
    for _, c in ipairs(all) do
      if #out >= R.HOP_WIDE_TRIES then break end
      if not have[c.edge] and not onHop(c.edge) and not (g.cave and g.cave[c.edge])
          and not (g.indoor and g.indoor[c.edge]) then
        local near = false
        for _, o in ipairs(out) do
          near = near or (o.px - c.px) ^ 2 + (o.py - c.py) ^ 2 < space2
        end
        if not near then out[#out + 1] = c end
      end
    end
    return out
  end
  -- Goal: from either end of a nearby edge to its closest point, then off the road.
  local goals = {}
  local function addGoal(c, walk)
    local e = g.e[c.edge]
    local cost, leg = Leg(c.px, c.py, tx, ty, true, walk, layered and R.EdgeZ(g, c.edge, c.along), tz)
    goals[#goals + 1] = { c = c, cost = cost, leg = leg }
    goalVia(e[1], part(c.edge, c.along) + cost, Join({ { kind = ROAD, edge = c.edge, from = 0, to = c.along } }, leg))
    goalVia(e[2], part(c.edge, math.max(0, e[3] - c.along)) + cost, Join({ { kind = ROAD, edge = c.edge, from = e[3], to = c.along } }, leg))
  end
  -- (the nearest WALK_AROUND_CANDIDATES roads on the ground: a track's with its heights (a floor, stairs) takes none, the
  -- terrain walk being the ground's. Issue #676: by Grom'gol's flight master a recorded walk up the zeppelin tower, its
  -- pieces 35 to 70 yd off, took them all, and the road 430 yd off whose walk round the hill is the way got none: 13
  -- points by the roads, 540 yd, for a 431 yd walk)
  local function walkSlots()
    local used = 0
    return function(c)
      if walkAll then return true end
      if used >= R.WALK_AROUND_CANDIDATES then return false end
      if not (g.floored and g.floored[c.edge]) then used = used + 1 end
      return true
    end
  end
  local tc = candidates(ts, tx, ty, tx, ty)
  local goalSlot = walkSlots()
  for _, c in ipairs(tc) do addGoal(c, goalSlot(c)) end
  if walkAll then
    local legs = {}
    for _, gl in ipairs(goals) do legs[#legs + 1] = gl.leg end
    for _, c in ipairs(wider(tc, tx, ty, legs)) do addGoal(c, true) end
  end
  -- Start: onto a nearby edge's closest point, then either way along it.
  local starts = {} -- (onto the roads: { edge, along, cost, leg }, for a way off the same edge further on)
  local onRoad = false -- (the player on a road: another road across country only when it saves a fair bit)
  if not layered and not offroad then
    for _, c in ipairs(ss) do
      if c.dist and c.dist <= R.ON_ROAD_YD then onRoad = true break end
    end
  end
  local function addStart(c, walk)
    local e = g.e[c.edge]
    local cost, leg = Leg(sx, sy, c.px, c.py, true, walk, sz, layered and R.EdgeZ(g, c.edge, c.along))
    if onRoad and c.dist and c.dist > R.ON_ROAD_YD then
      local hc = walkAll and IsHop(leg) and R.HOP_COST or 0 -- (a hop's HOP_COST as it is)
      cost = (cost - hc) * R.RoadFactor(R.LEAVE_ROAD_FACTOR) + hc
    end
    starts[#starts + 1] = { edge = c.edge, along = c.along, cost = cost, leg = leg }
    relax(START, e[1], cost + part(c.edge, c.along), Join(leg, { { kind = ROAD, edge = c.edge, from = c.along, to = 0 } }))
    relax(START, e[2], cost + part(c.edge, math.max(0, e[3] - c.along)), Join(leg, { { kind = ROAD, edge = c.edge, from = c.along, to = e[3] } }))
    for _, gl in ipairs(goals) do
      if gl.c.edge == c.edge then
        relax(START, GOAL, cost + part(c.edge, math.abs(gl.c.along - c.along)) + gl.cost,
          Join(leg, { { kind = ROAD, edge = c.edge, from = c.along, to = gl.c.along } }, gl.leg))
      end
    end
  end
  local sc = candidates(ss, nil, nil, sx, sy)
  local startSlot = walkSlots()
  for _, c in ipairs(sc) do addStart(c, startSlot(c)) end
  if walkAll then
    local legs = {}
    for _, st in ipairs(starts) do legs[#legs + 1] = st.leg end
    for _, c in ipairs(wider(sc, sx, sy, legs)) do addStart(c, true) end
  end
  -- Joining (and leaving) a road partway along it, not only where it's closest or at a
  -- junction: points every OFFROAD_ALONG_STEP yards on the nearby roads, straight over
  -- open ground. So the route cuts across to where the road is heading.
  -- (`fromNearest`: the points counted from the edge's nearest point, not its start: the same
  -- wherever the road data splits the edge, a cave's way in or a drawn road joining it)
  local function alongPoints(list, x, y, reach, fromNearest)
    local out = {}
    local r2 = reach * reach
    for i, c in ipairs(list) do
      if i > R.ENTRY_CANDIDATES then break end
      local e = g.e[c.edge]
      local acc = 0
      local step = R.OFFROAD_ALONG_STEP
      local shift = fromNearest and c.along % step or 0
      for k = 5, #e - 3, 2 do
        local ax, ay, bx, by = e[k], e[k + 1], e[k + 2], e[k + 3]
        local seg = Dist(ax, ay, bx, by)
        local t = math.ceil((acc - shift) / step) * step + shift
        while t <= acc + seg do
          local f = seg > 0 and (t - acc) / seg or 0
          local px, py = ax + (bx - ax) * f, ay + (by - ay) * f
          -- (a climbing road taken at its stretch on the floor, R.AtFloor: not got on or off at its other heights;
          -- Wildhammer Keep's barracks' ramp was left at its foot, 10 yd under the floor of the NPC upstairs)
          local hz = c.atFloor and R.RoadFloor(g, { edge = c.edge, along = t })
          if (px - x) ^ 2 + (py - y) ^ 2 <= r2 and not (hz and math.abs(hz - c.atFloor) > R.SAME_FLOOR_Z) then
            out[#out + 1] = { c.edge, t, px, py }
          end
          t = t + R.OFFROAD_ALONG_STEP
        end
        acc = acc + seg
      end
    end
    return out
  end
  -- (road mode: onto the road where it's heading, not back to its nearest point and round:
  -- within JOIN_ALONG_MAX, straight over open ground, or walked around what's in the way (a
  -- town's fences) for the few that look best, on the way to the stop; not on floors over floors)
  if not offroad and not layered and Pass then
    local function joins(list, x, y, use)
      local blocked = {}
      -- (not in a capital or a city: its streets are the way, its grid coarser than they are;
      -- nor in a cave or a city's ruins, whose grids can't tell a tunnel's walls)
      if cityPenalty or R.CapitalAt(cont, x, y) or (Pass.Overlay and Pass.Overlay(cont, x, y)) then return blocked end
      for k, p in ipairs(alongPoints(list, x, y, R.JOIN_ALONG_MAX, true)) do
        Breathe(k, 6)
        if SegCost(cont, x, y, p[3], p[4]) then
          p.walk = false
          use(p)
        else
          p.est = Dist(sx, sy, p[3], p[4]) + Dist(p[3], p[4], tx, ty)
          blocked[#blocked + 1] = p
        end
      end
      return blocked
    end
    -- (onto and off the same edge: along it between, not round by its end and back)
    local ons, offs = {}, {}
    local function onto(p)
      local cost, leg = Leg(sx, sy, p[3], p[4], false, p.walk)
      local e = g.e[p[1]]
      ons[#ons + 1] = { edge = p[1], along = p[2], cost = cost, leg = leg }
      relax(START, e[1], cost + part(p[1], p[2]), Join(leg, { { kind = ROAD, edge = p[1], from = p[2], to = 0 } }))
      relax(START, e[2], cost + part(p[1], math.max(0, e[3] - p[2])), Join(leg, { { kind = ROAD, edge = p[1], from = p[2], to = e[3] } }))
    end
    local function off(p)
      local cost, leg = Leg(p[3], p[4], tx, ty, false, p.walk)
      local e = g.e[p[1]]
      offs[#offs + 1] = { edge = p[1], along = p[2], cost = cost, leg = leg }
      goalVia(e[1], part(p[1], p[2]) + cost, Join({ { kind = ROAD, edge = p[1], from = 0, to = p[2] } }, leg))
      goalVia(e[2], part(p[1], math.max(0, e[3] - p[2])) + cost, Join({ { kind = ROAD, edge = p[1], from = e[3], to = p[2] } }, leg))
    end
    for _, pair in ipairs({ { ss, sx, sy, onto }, { ts, tx, ty, off } }) do
      local use = pair[4]
      local blocked = joins(pair[1], pair[2], pair[3], use)
      table.sort(blocked, function(a, b) return a.est < b.est end)
      for i = 1, math.min(#blocked, R.JOIN_WALK_TRIES) do
        blocked[i].walk = true
        use(blocked[i])
      end
    end
    -- (a short walk straight there over open ground: weighed like the walks onto and off the
    -- roads, not at ROAD_DIRECT_PENALTY: a road only a little of the way doesn't beat it)
    if direct and directSafe and not roadsFirst and not cityPenalty and not R.CapitalAt(cont, sx, sy) and not R.CapitalAt(cont, tx, ty)
        and not (Pass.Overlay and (Pass.Overlay(cont, sx, sy) or Pass.Overlay(cont, tx, ty)))
        and Dist(sx, sy, tx, ty) <= R.DIRECT_SHORT then
      relax(START, GOAL, Leg(sx, sy, tx, ty, false, false))
    end
    for _, gl in ipairs(goals) do offs[#offs + 1] = { edge = gl.c.edge, along = gl.c.along, cost = gl.cost, leg = gl.leg } end
    for _, pair in ipairs({ { ons, offs }, { starts, offs } }) do
      for _, a in ipairs(pair[1]) do
        for _, b in ipairs(pair[2]) do
          if a.edge == b.edge and a.cost and b.cost then
            relax(START, GOAL, a.cost + part(a.edge, math.abs(b.along - a.along)) + b.cost,
              Join(a.leg, { { kind = ROAD, edge = a.edge, from = a.along, to = b.along } }, b.leg))
          end
        end
      end
    end
  end
  -- Offroad mode: straight links from the start to nearby road nodes, and from nearby
  -- road nodes to the destination, where the ground allows. (A walk around whatever is in
  -- the way, for a short trip: after the search, as in road mode.)
  if offroad then
    local function nearestNodes(x, y) return NodesNear(g, x, y, R.OFFROAD_LINK_MAX) end
    for i, nd in ipairs(nearestNodes(sx, sy)) do
      if i > R.OFFROAD_LINKS then break end
      local n = nd[1]
      local nx, ny = g.n[n * 2 - 1], g.n[n * 2]
      relax(START, n, Leg(sx, sy, nx, ny))
    end
    for i, nd in ipairs(nearestNodes(tx, ty)) do
      if i > R.OFFROAD_LINKS then break end
      local n = nd[1]
      local nx, ny = g.n[n * 2 - 1], g.n[n * 2]
      goalVia(n, Leg(nx, ny, tx, ty))
    end
    for _, p in ipairs(alongPoints(ss, sx, sy, R.OFFROAD_ALONG_MAX)) do
      local cost, leg = Leg(sx, sy, p[3], p[4])
      if cost then
        local e = g.e[p[1]]
        relax(START, e[1], cost + part(p[1], p[2]), Join(leg, { { kind = ROAD, edge = p[1], from = p[2], to = 0 } }))
        relax(START, e[2], cost + part(p[1], math.max(0, e[3] - p[2])), Join(leg, { { kind = ROAD, edge = p[1], from = p[2], to = e[3] } }))
      end
    end
    for _, p in ipairs(alongPoints(ts, tx, ty, R.OFFROAD_ALONG_MAX)) do
      local cost, leg = Leg(p[3], p[4], tx, ty)
      if cost then
        local e = g.e[p[1]]
        goalVia(e[1], part(p[1], p[2]) + cost, Join({ { kind = ROAD, edge = p[1], from = 0, to = p[2] } }, leg))
        goalVia(e[2], part(p[1], math.max(0, e[3] - p[2])) + cost, Join({ { kind = ROAD, edge = p[1], from = e[3], to = p[2] } }, leg))
      end
    end
  end

  local expanded = 0
  while #open.n > 0 do
    local n = Pop(open)
    if n == GOAL then break end
    expanded = expanded + 1
    Breathe(expanded, R.ROUTE_BREATHE) -- (in a background job: pauses; in the frame: nothing)
    if not closed[n] then
      closed[n] = true
      local gf = goalFrom[n]
      if gf then relax(n, GOAL, gf[1], gf[2]) end
      for ai = g.adjIdx[n], g.adjIdx[n + 1] - 1 do
        local se = g.adjE[ai]
        local aei = se >= 0 and se or -se
        local drop = g.drops and g.drops[aei]
        if not drop or drop <= maxDrop then -- (a drop only when the fall is safe, and worth it)
          local alen = g.adjLen[ai]
          local acost = g.adjCost[ai]
          local ec = (exempt or (g.light and g.light[aei])) and alen * RoadRatio(aei) or (acost ~= 0 and acost) or alen
          -- (past the guards: the way round them, where every stretch can be bent round, BentRoadCost)
          if ec > alen and g.ratio and g.ratio[aei] then
            local bc = R.BentRoadCost(g, cont, aei)
            if bc and bc < ec then ec = bc end
          end
          relax(n, g.adjTo[ai], ec + alen * EdgeDanger(aei) + (drop and R.DROP_COST or 0), se)
        end
      end
      -- across a gap to another piece of the road network (walked around obstacles below)
      local x, y = g.n[n * 2 - 1], g.n[n * 2]
      for _, b in ipairs(g.bridges[n] or EMPTY) do
        local m = b[1]
        local mx, my = g.n[m * 2 - 1], g.n[m * 2]
        if b.raw == nil and (not b.deadEnd or (opts and opts.deadEnds)) then
          local c = Pass and Pass.SegmentCost(cont, x, y, mx, my)
          b.open = c ~= nil
          -- (to or from a cave's roads only over open ground: not through the mountain; nor in a
          -- capital, where what's closed between two roads is a wall or a level up or down)
          if not b.open and g.caveNode and (g.caveNode[n] or g.caveNode[m]) then b.shut = true end
          if not b.open and (R.CapitalAt(cont, x, y) or R.CapitalAt(cont, mx, my)) then b.shut = true end
          if not b.open and Pass and Pass.CrossesWall and Pass.CrossesWall(cont, x, y, mx, my) then b.shut = true end
          -- (kept without the road factor: Road tolerance may change it)
          -- (an extra far link only: on every link it made six of 200 sample trips weigh worse, 2026-11-10)
          -- (blocked for a few yards only, a rock or a hut on the line: about straight, as a leg waiting for its walk
          -- around is, and walked around when the route takes it. Priced as blocked all its length, the open desert
          -- from Gadgetzan to the pass into Un'Goro, 27 yd of 2,223 behind a building, lost to a jump over the
          -- crater's wall: seen in game 2026-11-10)
          local few = Pass and b.extra and not c and not b.shut and PendingCost(cont, x, y, mx, my) or nil
          if b.extra and not (c or few) then b.shut = true end -- (an extra far link the ground blocks: no way at all)
          -- (a loose road end's link, R.DeadEndLinks, blocked straight: its walk round's yards, once searched, whatever
          -- the line crosses (a wall, a city's edge: the walk keeps to its ways); none, shut)
          local walked
          if b.deadEnd and not c and Pass and Pass.FindPath and not layered then
            local wc, _, searching = Walk(cont, x, y, mx, my)
            if searching then
              pending = true
              walked = false
              -- (meanwhile about straight, a little more, as a leg waiting for its walk round is: the route provisional
              -- up the gap, not round the Barrens for the seconds the search takes in game, AzerothGPS#420)
              b.prov = b[2] * R.DEAD_END_PENDING_FACTOR + HostileExtra(cont, x, y, mx, my)
            elseif wc then
              walked, few, b.shut, b.prov = wc, nil, nil, nil
            else
              b.shut, b.prov = true, nil
            end
          end
          if walked ~= false then
            b.raw = (c or few or walked or b[2] * blockedPenalty(x, y, mx, my)) + HostileExtra(cont, x, y, mx, my)
          end
          if walked then -- (the same walk back: its twin too, whose own search from the other end may find none)
            for _, t in ipairs(g.bridges[m] or EMPTY) do
              if t[1] == n and t.deadEnd then t.raw, t.shut, t.open = b.raw, nil, b.open end
            end
          end
          Breathe(1, 1) -- (a link costed the first time: the ground along it, the guards: a pause after, in a background job)
        end
        -- (an extra far link: only in a route worked out again round a jump, below. In every route they made a
        -- sample trip weigh worse, a link of theirs priced under links that cost less once walked: 2026-11-10)
        local braw = b.raw or (b.raw == nil and b.prov) or nil -- (a loose end's link waiting for its walk: provisional)
        if braw and not (b.shut and b.raw) and (not b.extra or withExtras) and not (withExtras and b.jump)
            and (not b.deadEnd or (opts and opts.deadEnds)) then
          if red and b.zy == nil then b.zy = R.ZoneYards(cont, x, y, mx, my) end
          -- (`hop`: blocked and walked round by no walk, found when a route took it: HOP_COST, 2026-11-14)
          relax(n, m, braw * R.RoadFactor(R.OFFROAD_PENALTY) + Danger(b.zy) + (b.hop and walkAll and R.HOP_COST or 0),
            { { OFF, x, y, mx, my, gap = not b.open, hop = b.hop, bridge = b, bn = n, bm = m } })
        end
      end
      if offroad and Pass then
        local x, y = g.n[n * 2 - 1], g.n[n * 2]
        local links = LinksNow(g, cont, n)
        if not links then pending = true end
        for _, l in ipairs(links or {}) do
          local m = l[1]
          if red and l.zy == nil then l.zy = R.ZoneYards(cont, x, y, g.n[m * 2 - 1], g.n[m * 2]) end
          relax(n, m, l[2] + Danger(l.zy), { { OFF, x, y, g.n[m * 2 - 1], g.n[m * 2] } })
        end
      end
    end
  end
  -- Roads that go a long way round, or that are only reached across blocked ground, lose to
  -- walking straight there around the obstacles (road mode: see ROAD_DIRECT_PENALTY; offroad
  -- mode, whose straight line is blocked: like any leg off the roads).
  -- (Searched only when it could win: the walk is at least the straight distance. Not in a
  -- city or its ruins up top, whose grids are floors and walls, not terrain.)
  local directFactor = offroad and R.OFFROAD_TIE or R.RoadFactor(R.ROAD_DIRECT_PENALTY)
  -- (nor to or from a spot with a height in a building with its inside, off its floor (`offFloor` above): the terrain
  -- walk is flat, and went through the walls to a trainer upstairs in Goldshire's inn; its doors and stairs instead,
  -- 2026-10-06. Not by the nearest road's height: a capital's roads have heights too, and trips by Ironforge's and
  -- Thunder Bluff's lost their walks, route-check)
  if Pass and not cityPenalty and not layered and not offFloor
      and not (Pass.Overlay and (Pass.Overlay(cont, sx, sy) or Pass.Overlay(cont, tx, ty))) then
    local d = Dist(sx, sy, tx, ty)
    local best = gscore[GOAL] or math.huge
    local reach = d <= R.OFFROAD_WALK_AROUND or (d <= R.DETOUR_WALK_MAX and best > d * R.DETOUR_WALK_FACTOR)
    if reach and best > d * directFactor then
      local c, path = direct, nil
      if not c and Pass.FindPath then
        local searching
        c, path, searching = Walk(cont, sx, sy, tx, ty, opts and opts.transient)
        if searching then
          pending = true
          c = PendingCost(cont, sx, sy, tx, ty) -- (meanwhile: about straight, when only a little is blocked)
        end
      end
      if c then -- (past the other faction's guards, through zones too high for the player: more)
        if path then
          for i = 1, #path - 2, 2 do
            c = c + HostileExtra(cont, path[i], path[i + 1], path[i + 2], path[i + 3], exempt) + DangerLine(path[i], path[i + 1], path[i + 2], path[i + 3])
          end
        else
          c = c + HostileExtra(cont, sx, sy, tx, ty, exempt) + DangerLine(sx, sy, tx, ty)
        end
        c = c + SwimDetour(path, sx, sy, tx, ty)
      end
      -- (the roads' preference is for the walk's dry yards only: a swim's yards already pay the swim's own price,
      -- P.SwimCost, and no road goes over the water. Times the factor too, a yard swum weighed three on the roads:
      -- from the Wetlands' western marsh to a stop in the bay below Stromgarde the roads round by Thandol Span,
      -- 5.4k yd, beat the 2.1k yd swim straight there, 2026-11-19)
      -- (measured only when the walk would lose without it, after a pause: the frame budget)
      local wins = c and c * directFactor < best
      if c and not wins and directFactor > 1 and c < best then
        Breathe(1, 1)
        wins = c * directFactor - (directFactor - 1) * R.WalkSwimYards(cont, path, sx, sy, tx, ty) * Pass.SwimCost() < best
      end
      if wins then
        local pieces = { { OFF, sx, sy, tx, ty } }
        if not path then path = SwimWalk(cont, sx, sy, tx, ty, opts and opts.transient) end
        if path then
          pieces = {}
          for i = 1, #path - 2, 2 do pieces[#pieces + 1] = { OFF, path[i], path[i + 1], path[i + 2], path[i + 3] } end
        end
        local res = Build(g, pieces)
        res.pending = pending
        return res
      end
    end
  end
  Breathe(1, 1) -- (the search done: in a background job, a pause before the rest)
  if not gscore[GOAL] then -- not connected
    local res = Straight(g, sx, sy, tx, ty)
    res.pending, res.unconnected = pending, true -- (no way there on foot found: a line across)
    -- (and that line through a wall or over ground the terrain blocks: no way at all, `noWay`, which
    -- Nav doesn't draw; asked 2026-10-01, a broken road network drew one over the mountains from
    -- Ironforge. Over open ground or water, a swim to an island, it's still the way. Not while a
    -- search is running: provisional)
    if not pending and Pass and not (direct or Pass.SegmentCost(cont, sx, sy, tx, ty)) then
      res.noWay = true
      -- (and a cliff on it: said so, Nav's "a cliff in the way")
      res.cliff = Pass.CliffAlong and Pass.CliffAlong(cont, sx, sy, tx, ty) or nil
    end
    return res
  end

  local redo = false -- (a jump found in the route, below: worked out again)
  local hops, freshHop = 0, false -- (hops in the route, below; one of them not priced as one)
  local chain, cur = {}, GOAL
  while cur ~= START do
    local by = cameBy[cur]
    if type(by) == "number" then -- (a road: along its edge, or back)
      local ei = math.abs(by)
      local len = g.e[ei][3]
      by = { { kind = ROAD, edge = ei, from = by > 0 and 0 or len, to = by > 0 and len or 0 } }
    end
    table.insert(chain, 1, by)
    cur = cameFrom[cur]
  end
  local pieces = {}
  for _, list in ipairs(chain) do
    for _, p in ipairs(list) do
      -- a gap the terrain blocks in a straight line: walked around it once searched (from
      -- the player's position: a search that goes stale as they move on)
      local path, searching
      if p.gap and Pass and Pass.FindPath and not layered then
        path, searching = select(2, Walk(cont, p[2], p[3], p[4], p[5], opts and opts.transient and p[2] == sx and p[3] == sy or false))
        -- (a long link between road pieces with no walk around it, searched and none found: a jump no one walks,
        -- over a crater's wall or a mountain. The route is worked out again without it, with the extra far links
        -- to go round it by (`withExtras`), and that one taken if it's better. At BLOCKED_PENALTY the 1,192 yd over Un'Goro's wall still beat the 6,000 yd round by Tanaris from
        -- Camp Taurajo: "still doing the hop", seen in game 2026-11-10. A link with a walk around it stays as it
        -- was: Redridge's 313 yd over a ridge.)
        local b = p.bridge
        if b and searching then pending = true end -- (worked out again once the search is done: a jump, or walked)
        -- (searched and none found: a hop, 2026-11-14. One not priced as one, HOP_COST, a route worked out
        -- again knows: a link's own `hop`, both ways; a leg's walk remembered, WalkFailed)
        if not path and not searching and not R.OverBridge(cont, p[2], p[3], p[4], p[5]) then
          hops = hops + 1
          if not (p.hop and walkAll) then freshHop = true end
          if b and not b.hop then
            b.hop = true
            for _, t in ipairs(g.bridges[p.bm] or EMPTY) do
              if t[1] == p.bn then t.hop = true end
            end
          end
          -- (and the smaller of the road pieces it joins, the one cut off: an end on it tries roads off it too,
          -- `wider`. Loch Modan, 2026-11-14: the Maker's Terrace's roads are joined to the rest only by a link over
          -- the cliffs to Stonesplinter Valley's; a stop there is walked to from Thelsamar's)
          if b then
            local piece = R.Pieces(g)
            local a, c = piece[p.bn] or 0, piece[p.bm] or 0
            local cut = R.PieceSize(g, a) <= R.PieceSize(g, c) and a or c
            g.hopPieces = g.hopPieces or {} -- (R.Pieces' ids, kept with the graph as its links' `hop`)
            if not g.hopPieces[cut] then
              g.hopPieces[cut] = true
              freshHop = true -- (worked out again: an end on it tries the roads off it)
            end
          end
        end
        -- (and only over a wide stretch of blocked ground, JUMP_RUN_YD in one go: a thin ridge whose walk around
        -- the search didn't reach isn't one; a sample trip over one in the Hinterlands weighed worse going round)
        if b and b.wide == nil and not path and not searching and b[2] > R.JUMP_YD then
          b.wide = BlockedRun(cont, p[2], p[3], p[4], p[5]) >= R.JUMP_RUN_YD
        end
        if b and b.wide and not path and not searching and b[2] > R.JUMP_YD then
          if not b.jump then -- (its price is left alone: every other route as it was)
            b.jump = true
            for _, t in ipairs(g.bridges[p.bm] or EMPTY) do
              if t[1] == p.bn then t.jump = true end
            end
          end
          redo = true
        end
      end
      -- (open but across water: its walk round on land when that's cheaper, SwimWalk)
      if not path and not searching and not p.gap and p.kind == nil and p[1] == OFF and Pass and not layered then
        path = SwimWalk(cont, p[2], p[3], p[4], p[5], opts and opts.transient and p[2] == sx and p[3] == sy or false)
      end
      if path then
        for i = 1, #path - 2, 2 do pieces[#pieces + 1] = { OFF, path[i], path[i + 1], path[i + 2], path[i + 3] } end
      else
        pieces[#pieces + 1] = p
      end
    end
  end
  local res = Build(g, pieces)
  res.hops = hops
  -- (the last leg, into the stop, left straight, blocked, up or down a cliff (Passability.CliffAlong, at
  -- CLIFF_PENALTY): taken only when nothing else gets there, so nothing does on foot. No way, `noWay`, said as a cliff
  -- in the way, not a line drawn up it. Kooki3z 2026-11-20: "If I picked a spot that actually isn't reachable then
  -- should've said too high or route not possible". Not a cliff on the way from the start: the player got up there;
  -- and only one within CLIFF_STOP_YD of the stop, the stop up on it or under it: a long line over the mountains to
  -- a stop at sea, a hop as before, has a steep stretch somewhere on it whatever the stop)
  if not pending and not layered and Pass and Pass.CliffAlong then
    for _, p in ipairs(pieces) do
      local d = p[4] == tx and p[5] == ty and Dist(p[2], p[3], tx, ty)
      local k = d and d > R.CLIFF_STOP_YD and (d - R.CLIFF_STOP_YD) / d or 0
      if d and p.gap and p[1] == OFF
          and Pass.CliffAlong(cont, p[2] + (tx - p[2]) * k, p[3] + (ty - p[3]) * k, tx, ty) then
        res.noWay, res.cliff = true, true
        break
      end
    end
  end
  local againPending, hopPending = false, false
  -- (a hop in the route, 2026-11-14: once more, every hop priced as one (HOP_COST), every candidate's leg walked and,
  -- from an end with only hops or on roads cut off by one, more and further roads tried (`hopRedo`). Taken with fewer
  -- hops, however long: "no wall hopping allowed". Else this one, as before: with as many, priced as one the hops'
  -- yards don't count, and a shorter hop it found from the Great Lift's foot lost the lift, one down Teldrassil beat
  -- the Darnassus teleporter in the plan. Again inside one only for a hop found there not priced as one, or roads
  -- found cut off by one, HOP_REDOS deep)
  local function W(r) return (r.length or 0) + (r.blocked or 0) * (R.BLOCKED_PENALTY - 1) end
  local depth = opts and opts.hopRedo or 0
  if hops > 0 and depth < R.HOP_REDOS and (freshHop or depth == 0) then
    local ok, again = Apart(g, RouteOne, cont, sx, sy, tx, ty,
      setmetatable({ hopRedo = depth + 1 }, { __index = opts }))
    if ok and again and not again.unconnected then
      local ah = again.hops or 0
      -- (and settled: while its walks are searched, a leg waiting for one isn't a hop yet, so fewer means nothing)
      if ah < hops and not again.pending then
        again.pending = pending
        return again
      end
      -- (its walks still searched: worked out again once they're in, but this one isn't provisional for it: `pending`
      -- made Nav judge the walk by its line and leave it out, and the plan off Teldrassil walked down the tree's side
      -- without the teleporter; `hopPending` only keeps it out of Nav's walks kept, LegRoute)
      hopPending = again.pending and true or false
    end
  end
  -- (a jump in the route: once more, with the extra far links to go round it by. Taken when it's the better one as
  -- routes are weighed: fewer hops (2026-11-14), else its yards and its blocked yards at the router's cost for them;
  -- else the jump, as before: a way round that only jumps elsewhere, or is longer than the jump is dear, is no
  -- better. While its own walks are still searched, this one meanwhile and asked again: `pending`.)
  if redo and not withExtras then
    local ok, again = Apart(g, RouteOne, cont, sx, sy, tx, ty, setmetatable({ withExtras = true }, { __index = opts }))
    if ok and again and not again.unconnected then
      local ah = again.hops or 0
      if ah < hops or (ah == hops and W(again) < W(res)) then return again end
      againPending = againPending or (again.pending and true or false)
    end
  end
  -- off the roads more than walking straight there (open ground, nothing in the way): the roads
  -- only made it longer (to a road, a bit along it and off again), so straight
  -- (not on floors over floors, nor in a capital: grids too coarse for walls between)
  if direct and directSafe and not layered and not R.CapitalAt(cont, sx, sy) and not R.CapitalAt(cont, tx, ty)
      and res.length - res.road >= Dist(sx, sy, tx, ty) then
    res = StraightThere() -- (or round the water it swims, SwimWalk)
    res.hops = 0
  end
  res.pending = pending or againPending
  res.hopPending = hopPending or nil
  return res
end

-- Build a continent's road data (graph, indexes) and decode the terrain around (x, y) as a
-- background job, the first time a route is needed there: otherwise the first route pays
-- for all of it in one frame (a few hundred ms). Returns true while that's still running
-- (Nav waits for it, up to WARM_WAIT seconds, then works the route out anyway).
R.WARM = true -- tests: off
R.WARM_WAIT = 10
R.WARM_TERRAIN_YD = 800
-- Whether `cont`'s road graph is built (or it has no roads): drawing the road network waits for
-- it (built in the background by WarmUp) rather than building it all at once in a frame.
function R.GraphReady(cont) return graphs[cont] ~= nil end
function R.DebugGraph(cont) return graphs[cont] end -- (for tests and checks)
-- Whether (x, y) of `cont` is on a road of kind `kind` (an edited, drawn or recorded road's, g.kind), within `reach`
-- yards: the directions' "Cross the bridge" for the player's own bridges (Turns.Places; Kooki3z 2026-11-20, "doesn't say
-- cross the bridge on drawn bridges ... or recorded"). Each graph's roads of a kind kept with their boxes, once.
R.kindBoxes = setmetatable({}, { __mode = "k" })
function R.OnKindRoad(cont, x, y, kind, reach)
  local g = graphs[cont]
  if not (g and g.kind and x and y) then return false end
  local per = R.kindBoxes[g]
  if not per then
    per = {}
    R.kindBoxes[g] = per
  end
  local list = per[kind]
  if not list then
    list = {}
    for ei, k in pairs(g.kind) do
      local e = k == kind and g.e[ei]
      if e and #e >= 8 then
        local x0, x1, y0, y1 = math.huge, -math.huge, math.huge, -math.huge
        for i = 5, #e - 1, 2 do
          x0, x1, y0, y1 = math.min(x0, e[i]), math.max(x1, e[i]), math.min(y0, e[i + 1]), math.max(y1, e[i + 1])
        end
        list[#list + 1] = { e, x0, x1, y0, y1 }
      end
    end
    per[kind] = list
  end
  local r2 = reach * reach
  for _, b in ipairs(list) do
    if x >= b[2] - reach and x <= b[3] + reach and y >= b[4] - reach and y <= b[5] + reach then
      local e = b[1]
      for i = 5, #e - 3, 2 do
        local ax, ay, bx, by = e[i], e[i + 1], e[i + 2], e[i + 3]
        local vx, vy = bx - ax, by - ay
        local L2 = vx * vx + vy * vy
        local f = L2 > 0 and math.max(0, math.min(1, ((x - ax) * vx + (y - ay) * vy) / L2)) or 0
        if (ax + vx * f - x) ^ 2 + (ay + vy * f - y) ^ 2 <= r2 then return true end
      end
    end
  end
  return false
end
R.Breathe = Breathe -- (long loops elsewhere that may run inside the background work: GPSFrame's road index)

function R.WarmUp(cont, x, y)
  if not R.WARM or R.SYNC_WALKS then return false end
  local started = warming[cont]
  if started then return GetTime() - started < R.WARM_WAIT end
  if warmed[cont] then return false end
  if not (ns.Roads and ns.Roads[cont]) then
    warmed[cont] = true
    return false
  end
  warmed[cont], warming[cont] = true, GetTime()
  local key = "warm:" .. cont
  walkQueued[key] = true
  table.insert(walkJobs, 1, { key = key, warm = true, cont = cont, co = coroutine.create(function()
    local g = Graph(cont)
    if not g then return end
    SegIndex(g)
    NodeBuckets(g)
    if x and y and ns.Passability and ns.Passability.WarmRows then ns.Passability.WarmRows(cont, x, y, R.WARM_TERRAIN_YD) end
    -- (the map's index of the roads for drawing them, and the zones too high for the player)
    if ns.GPS and ns.GPS.WarmRoadIndex then ns.GPS.WarmRoadIndex(cont) end
    R.RedZones()
    if ns.GPS and ns.GPS.WarmLines then ns.GPS.WarmLines() end -- (and the map's lines for them)
  end) })
  return true
end
