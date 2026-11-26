-- Terrain passability for offroad routing (data: Data/Terrain.lua).
-- Cells are 0 open, 1 water (swimmable, slower), 2 blocked (too steep / off the map).
local _, ns = ...

local P = {}
ns.Passability = P

-- (in a background job: past the end of the Router's slice, Router.SliceOver; issue #841: a search's pauses by a count
-- of its own ran 88 ms live between them, and the stutter watch paused routing)
local function SliceOver()
  local R = ns.Router
  return R ~= nil and R.SliceOver ~= nil and R.SliceOver()
end

P.SWIM_COST = 1.5 -- swimming is about 2/3 of run speed (the game's base swim speed 4.72 yd/s, its run 7)
-- Swimming left out (Options > Routing "Allow swimming" off, or a swim removed from the trip on the map: Nav.SyncSwim):
-- water costs AVOID_SWIM_COST a yard instead, so a route goes round by land wherever there's a way, and still swims to
-- an isle with none. The prepared blocks (TerrainHPA.lua) keep SWIM_COST; their ways across water pay the rest
-- (ByBlocks). Never set by itself: P.SetAvoidSwim.
P.AVOID_SWIM_COST = 10
P.avoidSwim = false
-- (water as fast as land for the character, Nav.WaterFast: water walking with its reagent, an elixir, Aquatic Form:
-- WATER_FAST_COST a yard, a hair over land's so ties stay on land; swimming left out, avoidSwim, still wins)
P.WATER_FAST_COST = 1.02
P.KEEP_DRY_MIN_YD = 10 -- (FindPath: a walk swimming this much is straightened again keeping to the path's water)
P.waterFast = false
function P.SwimCost()
  if P.avoidSwim then return P.AVOID_SWIM_COST end
  return P.waterFast and P.WATER_FAST_COST or P.SWIM_COST
end
function P.SetWaterFast(on)
  on = on and true or false
  if P.waterFast == on then return false end
  P.waterFast = on
  if P.ClearSegMemo then P.ClearSegMemo() end
  return true
end
-- Whether it changed (then the remembered straight checks start over).
function P.SetAvoidSwim(on)
  on = on and true or false
  if P.avoidSwim == on then return false end
  P.avoidSwim = on
  if P.ClearSegMemo then P.ClearSegMemo() end
  return true
end
local TILE = 1600 / 3
local QUADS = 128 -- terrain quads per tile edge

local ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
local INDEX = {}
for i = 1, #ALPHABET do INDEX[ALPHABET:byte(i)] = i - 1 end
local SHORT = 21

local cache = {} -- [grid][row] = { end1, v1, end2, v2, ... }

-- Decode one run-length encoded row (see encode_row in app/azerothgps/roads/terrain.py;
-- `short`: the longest short run, SHORT unless the grid says (a cave's: 15); `long`: the
-- digits of a long run's length, 3 unless the grid says (a cave's: 2); `deep`: the grid's value for deep water far
-- out (fatigue: never swum), read as 2, blocked).
local function DecodeRow(text, short, long, deep)
  short = short or SHORT
  local runs, pos, i, n = {}, 0, 1, #text
  while i <= n do
    local b = text:byte(i)
    local v, len
    if b == 95 then -- "_": long run
      v = text:byte(i + 1) - 48
      if long == 2 then
        len = INDEX[text:byte(i + 2)] * 64 + INDEX[text:byte(i + 3)]
        i = i + 4
      else
        len = INDEX[text:byte(i + 2)] * 4096 + INDEX[text:byte(i + 3)] * 64 + INDEX[text:byte(i + 4)]
        i = i + 5
      end
    else
      local k = INDEX[b]
      v = math.floor(k / short)
      len = k % short + 1
      i = i + 1
    end
    if v == deep then v = 2 end
    pos = pos + len
    runs[#runs + 1] = pos
    runs[#runs + 1] = v
  end
  return runs
end
P.DecodeRow = DecodeRow

-- A grid's rows: a list, or one string of them split by "/" (a cave's), split the first time.
local function Rows(g)
  local rows = g.rows
  if type(rows) == "string" then
    local list = {}
    for r in rows:gmatch("[^/]+") do list[#list + 1] = r end
    g.rows = list
    rows = list
  end
  return rows
end
P.Rows = Rows

-- Walls drawn with the road tools (Shift+left-drag) or shipped (ns.Walls): what a player
-- can't walk through (a town's wall, a fence), like a mountain. Their cells on each grid are
-- closed (wallCells[grid][row * 65536 + col]) and legs crossing them blocked (P.CrossesWall).
-- Built again when the drawn ones change (P.RefreshWalls: Record.Changed).
local wallCells, wallSegs, wallsBuilt = {}, {}, false
-- (what the walls are built from changed: the drawn ones, P.RefreshWalls, or the safe drop, P.SetDropMax; a build begun
-- before that is dropped at its end)
local wallInputs = 0
-- Blocked ground a wall eraser went over (a mountain's edge the grid has wrong): open
-- (openCells[grid][row * 65536 + col]). Drawn walls still close their cells.
local openCells = {}
P.OPEN_YD = 6 -- an erase stroke opens the blocked ground this close to it
P.WALL_UNDER_YD = 12 -- an erase stroke takes out the walls this close to it
P.WALL_BUCKET = 64

-- The buildings on a continent (Data/Buildings.lua, app/azerothgps/buildings.py): cells of its grid
-- routes don't walk through, over the terrain's own. [g] = { [row * 65536 + col] = true }, made the
-- first time the grid is read (runs along its rows: row, first column, count).
local buildingCells = {}
local function Buildings(g)
  local set = buildingCells[g]
  if set then return set end
  set = {}
  for cont, grid in pairs(ns.Terrain or {}) do
    local runs = grid == g and ns.BuildingCells and ns.BuildingCells[cont]
    if runs then
      for i = 1, #runs - 2, 3 do
        local base, c0 = runs[i] * 65536, runs[i + 1]
        for c = c0, c0 + runs[i + 2] - 1 do set[base + c] = true end
      end
    end
  end
  buildingCells[g] = set
  return set
end
P.Buildings = Buildings

-- Cell value at (row, col) of grid g (2 outside the grid, on a wall, and in a building; a wall
-- eraser opens a building's cells too, as the terrain's).
local CellBase
-- Water banned from routes for the trip (a swim removed on the map: Nav.SkipSwim, P.SetSwimBans): closed like a wall.
-- [g][row] = { first col, last col, ... }.
local banRows = {}
local function Cell(g, row, col)
  if row < 1 or row > g.h or col < 1 or col > g.w then return 2 end
  local br = banRows[g]
  local bl = br and br[row]
  if bl then
    for i = 1, #bl - 1, 2 do
      if col >= bl[i] and col <= bl[i + 1] then return 2 end
    end
  end
  local wc = wallCells[g]
  if wc and wc[row * 65536 + col] then return 2 end
  return CellBase(g, row, col)
end
-- (a cell under a cliff walked down only, a cliff wall's: its way down, { x, y } toward the low side; else nil)
local function CliffCell(g, row, col)
  local wc = wallCells[g]
  local v = wc and wc[row * 65536 + col]
  return type(v) == "table" and v or nil
end
-- (the cell's value but the walls')
CellBase = function(g, row, col)
  local oc = openCells[g]
  if oc and oc[row * 65536 + col] then return 0 end
  if Buildings(g)[row * 65536 + col] then return 2 end
  local rc = cache[g]
  if not rc then
    rc = {}
    cache[g] = rc
  end
  local runs = rc[row]
  if not runs then
    runs = DecodeRow(Rows(g)[row], g.short, g.long, g.deep)
    rc[row] = runs
  end
  -- binary search for the run containing col
  local lo, hi = 1, #runs / 2
  while lo < hi do
    local mid = math.floor((lo + hi) / 2)
    if runs[mid * 2 - 1] < col then lo = mid + 1 else hi = mid end
  end
  return runs[lo * 2]
end

-- Grid cell (col, row) of world (x, y), and a cell's center back in world coordinates.
local function ToCell(g, x, y)
  local k = TILE / g.cell
  return math.floor(((32 - y / TILE) - g.tx0) * k) + 1, math.floor(((32 - x / TILE) - g.ty0) * k) + 1
end

local function CellCentre(g, col, row)
  local k = TILE / g.cell
  return (32 - g.ty0 - (row - 0.5) / k) * TILE, (32 - g.tx0 - (col - 0.5) / k) * TILE
end

local function InLoop(poly, x, y)
  local inside, n = false, #poly / 2
  local jx, jy = poly[2 * n - 1], poly[2 * n]
  for i = 1, n do
    local ix, iy = poly[2 * i - 1], poly[2 * i]
    if (iy > y) ~= (jy > y) and x < (jx - ix) * (y - iy) / (jy - iy) + ix then inside = not inside end
    jx, jy = ix, iy
  end
  return inside
end

local function NearLine(line, x, y, r)
  local r2 = r * r
  for k = 1, #line - 3, 2 do
    local ax, ay, bx, by = line[k], line[k + 1], line[k + 2], line[k + 3]
    local vx, vy = bx - ax, by - ay
    local L2 = vx * vx + vy * vy
    local t = L2 > 0 and math.max(0, math.min(1, ((x - ax) * vx + (y - ay) * vy) / L2)) or 0
    if (ax + vx * t - x) ^ 2 + (ay + vy * t - y) ^ 2 <= r2 then return true end
  end
  return false
end

P.InLoop, P.NearLine = InLoop, NearLine -- (the world grid's erase strokes, WorldGrid.lua)

-- A wall's floor (drawn where floors lie over each other: Record's `z`, `indoors`; a shipped one's
-- `z`, `indoors`): { z, indoors }, or nil.
local function WallFloor(w)
  if w.fl then return w.fl end
  if w.z or w.indoors ~= nil or w.down ~= nil then
    w.fl = { z = w.z, indoors = w.indoors, down = w.down }
    return w.fl
  end
  return nil
end
-- Whether a wall and a wall eraser (their floors, either nil: any) are on the same floor: drawn
-- within WALL_FLOOR_Z of each other's height (a floor over another is further). (roads/tracks.py's
-- walls does the same offline.)
P.WALL_FLOOR_Z = 8
function P.SameWallFloor(cont, x, y, a, b)
  if not (a and b) then return true end
  if a.down ~= nil and b.down ~= nil then return a.down == b.down end -- (over a cave's floor: picked)
  if not (a.z and b.z) then return true end
  return math.abs(a.z - b.z) <= P.WALL_FLOOR_Z
end
-- (a drawn wall's points with its floor and a cliff's sides, made once per stroke: its saved points stay as they are)
local floorLines = setmetatable({}, { __mode = "k" })
local function DrawnLine(t)
  local cliff = t.kind == "cliff" and type(t.cl) == "table" and type(t.cr) == "table"
  if t.z == nil and t.indoors == nil and t.down == nil and not cliff then return t.pts end
  local c = floorLines[t.pts]
  if not c then
    c = { fl = (t.z ~= nil or t.indoors ~= nil or t.down ~= nil) and { z = t.z, indoors = t.indoors, down = t.down } or nil }
    for i = 1, #t.pts do c[i] = t.pts[i] end
    if cliff then c.kind, c.cl, c.cr = "cliff", t.cl, t.cr end
    floorLines[t.pts] = c
  end
  return c
end

-- Cliff walls (1.3.10, issue #685): a wall's section (`kind` "cliff", with `cl` and `cr`: the ground's height on its
-- left and its right, as drawn from its first point to its last, a height or false per point; a section is a cliff
-- where both its points have both) is open where the two sides are within CLIFF_STEP; walked down from its high side
-- where the drop is at most CLIFF_DROP_MAX (Router.TRACK_DROP_MAX, the safe jumps': never up; walks over the grid go
-- round it either way); else a wall both ways. P.CliffSection(w, p): "open", "down" (and the way down: a unit vector
-- toward the low side, and the drop) or nil (a plain wall) for its section from point p to p + 1.
P.CLIFF_STEP = 2
P.CLIFF_DROP_MAX = 14
-- ... and the drop is the player's safe one, as the routes': RouteOne's maxDrop (Nav.SafeDrop: Options' Safe drop,
-- 39 yd by default, in combat too), set by P.SetDropMax; else the free one, Router.TRACK_DROP_MAX. Kooki3z 2026-11-20,
-- Stonetalon Mountains: a ledge dropped off one way but never climbed, and routes may drop as far as the safe drop.
-- The same limit for the map's ground's cliffs (CliffAlong) and the walks' first and last steps.
P.dropMax = nil
local cliffMemo, cliffMemoN -- (CliffAlong's, below: by the points, for this limit)
local cliffRuns = {} -- (and its runs down, P.CliffRuns)
local fallMemo, fallMemoN = {}, 0 -- (FallAlong's, below)
local function DropMax()
  return P.dropMax or ns.Router and ns.Router.TRACK_DROP_MAX or P.CLIFF_DROP_MAX
end
-- The safe drop for the routes from now on (whole yards); a new one works the cliff walls' ways down out again
-- (RefreshWalls, at their next use) and forgets the legs costed by the old one.
function P.SetDropMax(v)
  v = v and math.floor(v) or nil
  if v == P.dropMax then return end
  P.dropMax = v
  wallsBuilt, wallInputs = false, wallInputs + 1
  if P.ClearSegMemo then P.ClearSegMemo() end
  cliffMemo, cliffMemoN, cliffRuns = {}, 0, {}
  fallMemo, fallMemoN = {}, 0
end
-- Jumps avoided on the trip (Nav.AvoidJump: their tops): no cliff wall's way down within Nav.JUMP_BAN_YD of one, and no
-- leg down the ground's cliffs there (CliffAlong); set by Nav.SyncJumps, the cliff walls and the legs worked out again.
P.jumpBans = nil
P.JUMP_FALL_MIN = 4 -- yards: a run of the ground's steep samples falling this much near an avoided jump's top is one
function P.SetJumpBans(list)
  P.jumpBans = (list and list[1]) and list or nil
  wallsBuilt, wallInputs = false, wallInputs + 1
  if P.ClearSegMemo then P.ClearSegMemo() end
  cliffMemo, cliffMemoN = {}, 0
  fallMemo, fallMemoN = {}, 0
end
local function JumpBanned(cont, x, y)
  local N = P.jumpBans and ns.Nav
  return N and N.JumpBanned and N.JumpBanned(cont, x, y) or false
end
P.JumpBanned = JumpBanned
function P.CliffSides(w, p)
  local cl, cr = w.cl, w.cr
  if w.kind ~= "cliff" or type(cl) ~= "table" or type(cr) ~= "table" then return nil end
  local a, b, c, d = tonumber(cl[p]), tonumber(cl[p + 1]), tonumber(cr[p]), tonumber(cr[p + 1])
  if not (a and b and c and d) then return nil end
  return (a + b) / 2, (c + d) / 2
end
function P.CliffSection(w, p)
  local zl, zr = P.CliffSides(w, p)
  if not zl then return nil end
  local dz = zl - zr
  if math.abs(dz) <= P.CLIFF_STEP then return "open" end
  local max = DropMax()
  if math.abs(dz) > max then return nil end
  local ax, ay, bx, by = w[2 * p - 1], w[2 * p], w[2 * p + 1], w[2 * p + 2]
  -- (an avoided jump's top within reach of the section: a wall, both ways)
  if P.jumpBans and ns.Nav and ns.Nav.JumpBannedAlong and ns.Nav.JumpBannedAlong(w.cont, ax, ay, bx, by) then return nil end
  local ex, ey = bx - ax, by - ay
  local L = math.sqrt(ex * ex + ey * ey)
  if L <= 0 then return nil end
  local lx, ly = -ey / L, ex / L -- (its left)
  if dz > 0 then lx, ly = -lx, -ly end -- (toward the low side)
  return "down", lx, ly, math.abs(dz)
end

-- (each of the player's own lines in P.WallLines: its track; weak, as the lines are)
local lineTrack = setmetatable({}, { __mode = "k" })
-- The player's own track a line of P.WallLines(cont) was made from (nil for the map's own): what's drawn and routed is
-- what Edit Wall picks and Delete takes out (Record.EditableWalls; Kooki3z 2026-11-20, a wall deleted with an erase
-- was gone from the map and the routes but still picked, so a click on the wall shown over it picked that one again
-- and Delete never reached the one shown).
function P.WallTrack(w)
  return w and lineTrack[w]
end

-- The walls on `cont`: the shipped ones, then the player's drawn ones in order (an erase
-- stroke, "unwall", takes out the walls near it, or inside it when drawn as a loop; on its floor
-- only). Each a flat point list (`fl`: its floor, when it has one).
function P.WallLines(cont)
  local out = {}
  for _, w in ipairs(ns.Walls and ns.Walls[cont] or {}) do
    WallFloor(w)
    out[#out + 1] = w
  end
  local shipped = ns.RoadTracksIn or {}
  -- (a wall edited with Edit Wall: the new one `replaces` the old one's time, left out)
  local gone = {}
  for _, t in ipairs(ns.db and ns.db.tracks or {}) do
    if t.op == "wall" and t.replaces then gone[t.replaces] = true end
  end
  for _, t in ipairs(ns.db and ns.db.tracks or {}) do
    if t.continent == cont and t.pts and #t.pts >= 4 and not shipped[t.time or -1] and not (t.op == "wall" and gone[t.time or -1]) then
      if t.op == "wall" then
        local w = DrawnLine(t)
        lineTrack[w] = t
        w.own = true -- (the player's own, not in the data: drawn in its own color, GPSFrame's G.LayoutWalls)
        out[#out + 1] = w
      elseif t.op == "unwall" then
        local kept = {}
        local efl = (t.z or t.indoors ~= nil or t.down ~= nil) and { z = t.z, indoors = t.indoors, down = t.down } or nil
        for _, w in ipairs(out) do
          local under = false
          for i = 1, #w - 1, 2 do
            local x, y = w[i], w[i + 1]
            if ((t.area and InLoop(t.pts, x, y)) or (not t.area and NearLine(t.pts, x, y, P.WALL_UNDER_YD)))
                and P.SameWallFloor(cont, x, y, w.fl, efl) then
              under = true
              break
            end
          end
          if not under then kept[#kept + 1] = w end
        end
        out = kept
      end
    end
  end
  return out
end

-- The wall erasers on `cont` (they open blocked ground too): shipped (ns.WallOpens) and the
-- player's not yet in the data. { { pts, area }, ... }
function P.OpenAreas(cont)
  local out = {}
  for _, o in ipairs(ns.WallOpens and ns.WallOpens[cont] or {}) do out[#out + 1] = o end
  local shipped = ns.RoadTracksIn or {}
  for _, t in ipairs(ns.db and ns.db.tracks or {}) do
    if t.continent == cont and t.op == "unwall" and t.pts and #t.pts >= 4 and not shipped[t.time or -1] then
      out[#out + 1] = { pts = t.pts, area = t.area }
    end
  end
  return out
end

-- Every continent (and city level) with walls or wall erasers, shipped or drawn.
local function WallConts()
  local set = {}
  for c in pairs(ns.Walls or {}) do set[c] = true end
  for c in pairs(ns.WallOpens or {}) do set[c] = true end
  for _, t in ipairs(ns.db and ns.db.tracks or {}) do
    if t.op == "wall" or t.op == "unwall" then set[t.continent] = true end
  end
  return set
end

-- A continent's wall cells, segments and opened cells from these walls and wall erasers. (`pause()`: called now and
-- then, RefreshWalls' pause in a background job)
local function WallGrid(g, lines, opens, pause)
  local cells, segs, open = {}, {}, {}
  local B = P.WALL_BUCKET
  for _, w in ipairs(lines) do
    for k = 1, #w - 3, 2 do
      if pause then pause() end
      local ax, ay, bx, by = w[k], w[k + 1], w[k + 2], w[k + 3]
      -- (a cliff's section: none where its sides are level, one way where the drop is safe)
      local how, nx, ny, dz
      if w.kind == "cliff" then how, nx, ny, dz = P.CliffSection(w, (k + 1) / 2) end
      if how == "open" then
        -- (nothing: walked across either way)
      else
      -- its cells, every third of a cell along it (so none it crosses is skipped)
      if g then
        local len = math.sqrt((bx - ax) ^ 2 + (by - ay) ^ 2)
        local n = math.max(1, math.ceil(len / (g.cell / 3)))
        for i = 0, n do
          local c, r = ToCell(g, ax + (bx - ax) * i / n, ay + (by - ay) * i / n)
          local key = r * 65536 + c
          -- (a cliff's walked down only: its way down, for the straight legs, SegmentCost; walks go round)
          if how == "down" then
            if cells[key] ~= true then cells[key] = { nx, ny } end
          else
            cells[key] = true
          end
        end
      end
      local seg = { ax, ay, bx, by, fl = w.fl, down = how == "down" and { nx, ny } or nil, dz = dz }
      for kx = math.floor(math.min(ax, bx) / B), math.floor(math.max(ax, bx) / B) do
        for ky = math.floor(math.min(ay, by) / B), math.floor(math.max(ay, by) / B) do
          local key = kx * 65536 + ky
          segs[key] = segs[key] or {}
          local list = segs[key]
          list[#list + 1] = seg
        end
      end
      end
    end
  end
  -- the ground the erasers went over: open (inside a loop; along a stroke, OPEN_YD either side)
  if g then
    for _, o in ipairs(opens) do
      local pts = o.pts
      local x0, x1, y0, y1 = math.huge, -math.huge, math.huge, -math.huge
      for i = 1, #pts - 1, 2 do
        x0, x1 = math.min(x0, pts[i]), math.max(x1, pts[i])
        y0, y1 = math.min(y0, pts[i + 1]), math.max(y1, pts[i + 1])
      end
      local pad = o.area and 0 or P.OPEN_YD + g.cell
      local cA, rA = ToCell(g, x1 + pad, y1 + pad)
      local cB, rB = ToCell(g, x0 - pad, y0 - pad)
      for r = math.min(rA, rB), math.max(rA, rB) do
        if pause then pause() end
        for c = math.min(cA, cB), math.max(cA, cB) do
          local x, y = CellCentre(g, c, r)
          if (o.area and InLoop(pts, x, y)) or (not o.area and NearLine(pts, x, y, P.OPEN_YD + g.cell / 2)) then
            open[r * 65536 + c] = true
          end
        end
      end
    end
  end
  return cells, segs, open
end

-- Whether the player has walls or wall erasers on `cont` not in the data yet.
local function Drawn(cont)
  local shipped = ns.RoadTracksIn or {}
  for _, t in ipairs(ns.db and ns.db.tracks or {}) do
    if t.continent == cont and (t.op == "wall" or t.op == "unwall") and not shipped[t.time or -1] then return true end
  end
  return false
end

P.DrawnWalls = Drawn -- (the world grid: its shipped walls are cut at its bake, the player's own checked as it searches)

local hpaBlocks, hpaDirty = {}, {} -- (the search by blocks, below: blocks decoded, and those worked out here)
local wallDirty, banDirty = {}, {} -- (those of the player's walls, and of the banned water: hpaDirty is both)
local function MergeDirty()
  hpaBlocks, hpaDirty = {}, {}
  for _, src in ipairs({ wallDirty, banDirty }) do
    for cont, d in pairs(src) do
      local m = hpaDirty[cont] or {}
      for b in pairs(d) do m[b] = true end
      hpaDirty[cont] = m
    end
  end
end
-- (the block of cell (r, c) and its four neighbors, marked in d)
local function MarkBlock(H, d, r, c)
  local br, bc = math.floor((r - 1) / H.K), math.floor((c - 1) / H.K)
  for _, o in ipairs({ { 0, 0 }, { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } }) do
    local nr, nc = br + o[1], bc + o[2]
    if nr >= 0 and nr < H.ny and nc >= 0 and nc < H.nx then d[nr * H.nx + nc] = true end
  end
end

-- Build the walls' cells and segments again (after drawing or erasing one).
-- (In a background job it pauses as the Router's slice runs out (issue #841: a wall eraser's area tested cell by cell,
-- tens of ms in one go inside a route's job). Built into its own tables and put in place at the end, so nothing reads
-- half of it meanwhile; anything asking for the walls then builds them itself, and a build begun before what they're
-- built from changed is dropped at its end, `wallInputs`.)
local function BuildWalls()
  local gen = wallInputs
  local co, isMain = coroutine.running()
  local pause
  if co ~= nil and not isMain then
    pause = function() if SliceOver() then coroutine.yield() end end
  end
  local newCells, newSegs, newOpen, newDirty = {}, {}, {}, {}
  for cont in pairs(WallConts()) do
    local g = ns.Terrain and ns.Terrain[cont]
    local cells, segs, open = WallGrid(g, P.WallLines(cont), P.OpenAreas(cont), pause)
    if g then newCells[g] = cells end
    newSegs[cont] = segs
    if g and next(open) then newOpen[g] = open end
    -- (the player's own, not in the data yet: the blocks they change, and their neighbors,
    -- are worked out here; the prepared ones have the shipped walls)
    local H = g and ns.TerrainHPA and ns.TerrainHPA[cont]
    if H and Drawn(cont) then
      local sc, _, so = WallGrid(g, ns.Walls and ns.Walls[cont] or {}, ns.WallOpens and ns.WallOpens[cont] or {},
        pause)
      local d = {}
      local function mark(key) MarkBlock(H, d, math.floor(key / 65536), key % 65536) end
      for k in pairs(cells) do if not sc[k] then mark(k) end end
      for k in pairs(sc) do if not cells[k] then mark(k) end end
      for k in pairs(open) do if not so[k] then mark(k) end end
      for k in pairs(so) do if not open[k] then mark(k) end end
      if next(d) then newDirty[cont] = d end
    end
  end
  if gen ~= wallInputs then return end -- (changed meanwhile: built again from what they are now)
  wallCells, wallSegs, openCells, wallDirty = newCells, newSegs, newOpen, newDirty
  wallsBuilt = true
  if P.ClearSegMemo then P.ClearSegMemo() end -- (walls feed SegmentCost: its memo starts over)
  MergeDirty()
end
local function EnsureWalls()
  while not wallsBuilt do BuildWalls() end
end
function P.RefreshWalls()
  wallsBuilt, wallInputs = false, wallInputs + 1
  fallMemo, fallMemoN = {}, 0
  EnsureWalls()
end

local function Orient(ax, ay, bx, by, cx, cy)
  local v = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
  return v > 1e-9 and 1 or v < -1e-9 and -1 or 0
end

-- Where along the leg (x1, y1)-(x2, y2) it first meets a wall: 0..1, or nil. (`ok(seg, x, y)`: only
-- the walls it passes at the crossing (x, y): Router's floor check for a wall with a floor.)
function P.WallHit(cont, x1, y1, x2, y2, ok)
  EnsureWalls()
  local segs = wallSegs[cont]
  if not segs then return nil end
  local B = P.WALL_BUCKET
  local best
  local seen = {}
  local dx, dy = x2 - x1, y2 - y1
  for kx = math.floor(math.min(x1, x2) / B), math.floor(math.max(x1, x2) / B) do
    for ky = math.floor(math.min(y1, y2) / B), math.floor(math.max(y1, y2) / B) do
      for _, s in ipairs(segs[kx * 65536 + ky] or {}) do
        if not seen[s] and not (s.down and dx * s.down[1] + dy * s.down[2] > 0) then -- (a cliff walked down: no wall)
          seen[s] = true
          local ex, ey = s[3] - s[1], s[4] - s[2]
          local den = dx * ey - dy * ex
          if math.abs(den) > 1e-9 then
            local t = ((s[1] - x1) * ey - (s[2] - y1) * ex) / den
            local u = ((s[1] - x1) * dy - (s[2] - y1) * dx) / den
            if t > 1e-9 and t <= 1 and u >= 0 and u <= 1 and (not best or t < best)
                and (not ok or ok(s, x1 + dx * t, y1 + dy * t)) then best = t end -- (at its end too: a crossing right on a point)
          end
        end
      end
    end
  end
  return best
end

-- Whether world (x, y) is inside grid `key`'s rectangle (a city level's: over the city).
-- The world extent of grid `key` (a continent's, a city's or an instance's): x0, x1, y0, y1.
function P.GridBounds(key)
  local g = ns.Terrain and ns.Terrain[key]
  if not (g and g.w and g.h) then return nil end
  local x1, y1 = (32 - g.ty0) * TILE, (32 - g.tx0) * TILE -- (its north-west corner: rows run south, columns east)
  return x1 - g.h * g.cell, x1, y1 - g.w * g.cell, y1
end

function P.InGrid(key, x, y)
  local g = ns.Terrain and ns.Terrain[key]
  if not g then return false end
  local c, r = ToCell(g, x, y)
  return r >= 1 and r <= g.h and c >= 1 and c <= g.w
end

-- Whether `cont` has any walls.
function P.HasWalls(cont)
  EnsureWalls()
  return wallSegs[cont] ~= nil and next(wallSegs[cont]) ~= nil
end

-- Whether any of `cont`'s walls has a floor (drawn where floors lie over each other).
function P.WallFloors(cont)
  for _, w in ipairs(P.WallLines(cont)) do
    if w.fl then return true end
  end
  return false
end

-- Whether the leg (x1, y1)-(x2, y2) crosses a wall (`ok`: as WallHit's).
-- The model walls too (P.CrossesModelWall), unless `noModel`: the Router's roads cut by walls at load, which never cross
-- one (`agps world-grid model-walls` opens each road's way through), so the outlines aren't decoded for every road.
function P.CrossesWall(cont, x1, y1, x2, y2, ok, noModel)
  EnsureWalls()
  if not noModel and P.CrossesModelWall(cont, x1, y1, x2, y2) then return true end
  local segs = wallSegs[cont]
  if not segs then return false end
  local B = P.WALL_BUCKET
  local seen = {}
  for kx = math.floor(math.min(x1, x2) / B), math.floor(math.max(x1, x2) / B) do
    for ky = math.floor(math.min(y1, y2) / B), math.floor(math.max(y1, y2) / B) do
      for _, s in ipairs(segs[kx * 65536 + ky] or {}) do
        if not seen[s] and not (s.down and (x2 - x1) * s.down[1] + (y2 - y1) * s.down[2] > 0) then -- (a cliff walked down)
          seen[s] = true
          local o1, o2 = Orient(x1, y1, x2, y2, s[1], s[2]), Orient(x1, y1, x2, y2, s[3], s[4])
          local o3, o4 = Orient(s[1], s[2], s[3], s[4], x1, y1), Orient(s[1], s[2], s[3], s[4], x2, y2)
          if o1 ~= o2 and o3 ~= o4 and o1 ~= 0 and o2 ~= 0 then
            if not ok then return true end
            local dx, dy, ex, ey = x2 - x1, y2 - y1, s[3] - s[1], s[4] - s[2]
            local den = dx * ey - dy * ex
            local t = math.abs(den) > 1e-9 and ((s[1] - x1) * ey - (s[2] - y1) * ex) / den or 0
            if ok(s, x1 + dx * t, y1 + dy * t) then return true end
          end
        end
      end
    end
  end
  return false
end

-- The thin tall walls from the client's model collision (Data/ModelWalls.lua, app/azerothgps/modelwalls.py): palisades,
-- fences, barricades, railings, the whole map. Item 78 again (Kooki3z 2026-11-25, the 1.4.0 build): Red Cloud Mesa's
-- palisade was fixed twice by cutting the world grid's links at a few heights over their floors, and each time the route
-- jumped through the next stretch of it (a far drop's top past the rim, a baked drop link, a walk off the edge). Each
-- wall's outline in plan view is a hard barrier for every route piece crossing it, whatever its kind or heights: the
-- world grid's links and far drops (WorldGrid.Search; the bake dropped its steps across one) and P.CrossesWall's callers
-- but the Router's terrain ways (SegmentCost: its cells don't know them). A piece touching an outline counts as
-- crossing it (a line through a corner point exactly).
-- The data (a few thousand outlines) is kept as its strings until a route comes near (ns.ModelWalls[cont]: `w` the
-- outlines, each "x,y,dx,dy,..." in half yards, `r` [rx * 4096 + ry] = the outlines over that MODEL_REGION square):
-- a square's outlines are decoded the first time a piece is checked over it, into flat lists by MODEL_BUCKET yards
-- (`idx`, each bucket ax, ay, bx, by, ax, ...), kept for the session.
P.MODEL_BUCKET = 16
P.MODEL_REGION = 512
local modelState = {} -- [cont] = { idx = { [bucket] = { ax, ay, bx, by, ... } }, done = { [region] = true }, w = {} }
-- An outline's points from its string: { x, y, x, y, ... } (world yards).
local function DecodeOutline(s)
  local out, x, y, n = {}, nil, nil, 0
  for tok in string.gmatch(s, "[^,]+") do
    local v = tonumber(tok)
    n = n + 1
    if n == 1 then x = v elseif n == 2 then y = v else
      if n % 2 == 1 then x = x + v else y = y + v end
    end
    if n >= 2 and n % 2 == 0 then
      out[#out + 1] = x * 0.5
      out[#out + 1] = y * 0.5
    end
  end
  return out
end
P.DecodeModelOutline = DecodeOutline
local function ModelState(cont)
  local st = modelState[cont]
  if st == nil then
    local d = ns.ModelWalls and ns.ModelWalls[cont]
    st = d and { idx = {}, done = {}, w = {}, d = d } or false
    modelState[cont] = st
  end
  return st or nil
end
-- (outline k's segments into the buckets, once)
local function IndexOutline(st, k)
  if st.w[k] then return end
  st.w[k] = true
  local p = DecodeOutline(st.d.w[k])
  local B, idx = P.MODEL_BUCKET, st.idx
  local floor, min, max = math.floor, math.min, math.max
  for i = 1, #p - 3, 2 do
    local ax, ay, bx, by = p[i], p[i + 1], p[i + 2], p[i + 3]
    for kx = floor(min(ax, bx) / B), floor(max(ax, bx) / B) do
      for ky = floor(min(ay, by) / B), floor(max(ay, by) / B) do
        local key = kx * 65536 + ky
        local list = idx[key]
        if not list then
          list = {}
          idx[key] = list
        end
        local n = #list
        list[n + 1], list[n + 2], list[n + 3], list[n + 4] = ax, ay, bx, by
      end
    end
  end
end
-- (the outlines over the box decoded)
local function EnsureRegions(st, x0, y0, x1, y1)
  local R, floor = P.MODEL_REGION, math.floor
  for rx = floor(x0 / R), floor(x1 / R) do
    for ry = floor(y0 / R), floor(y1 / R) do
      local key = rx * 4096 + ry
      if not st.done[key] then
        st.done[key] = true
        local ks = st.d.r[key]
        if ks then
          for _, k in ipairs(ks) do IndexOutline(st, k) end
        end
      end
    end
  end
end
-- Whether `cont` has model walls.
function P.HasModelWalls(cont)
  return ModelState(cont) ~= nil
end
-- Every model wall outline on `cont`, decoded: { { x, y, x, y, ... }, ... } (the bake, the tests).
function P.ModelWallOutlines(cont)
  local d = ns.ModelWalls and ns.ModelWalls[cont]
  local out = {}
  for k, s in ipairs(d and d.w or {}) do out[k] = DecodeOutline(s) end
  return out
end
-- Whether the piece (x1, y1)-(x2, y2) crosses (or touches) a model wall's outline on `cont`.
function P.CrossesModelWall(cont, x1, y1, x2, y2)
  local st = ModelState(cont)
  if not st then return false end
  local floor, min, max = math.floor, math.min, math.max
  EnsureRegions(st, min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
  local B, idx = P.MODEL_BUCKET, st.idx
  local dx, dy = x2 - x1, y2 - y1
  for kx = floor(min(x1, x2) / B), floor(max(x1, x2) / B) do
    for ky = floor(min(y1, y2) / B), floor(max(y1, y2) / B) do
      local list = idx[kx * 65536 + ky]
      if list then
        for i = 1, #list, 4 do
          local ax, ay, bx, by = list[i], list[i + 1], list[i + 2], list[i + 3]
          local d1 = dx * (ay - y1) - dy * (ax - x1)
          local d2 = dx * (by - y1) - dy * (bx - x1)
          if (d1 <= 0 and d2 >= 0) or (d1 >= 0 and d2 <= 0) then
            local ex, ey = bx - ax, by - ay
            local d3 = ex * (y1 - ay) - ey * (x1 - ax)
            local d4 = ex * (y2 - ay) - ey * (x2 - ax)
            if ((d3 <= 0 and d4 >= 0) or (d3 >= 0 and d4 <= 0)) and not (d1 == 0 and d2 == 0) then return true end
          end
        end
      end
    end
  end
  return false
end
-- Whether any piece of the flat point list `pts` ({ {x, y, ...}, ... } when `nested`, else x, y, x, y, ...) crosses a
-- model wall.
function P.PtsCrossModelWall(cont, pts, nested)
  if not ModelState(cont) then return false end
  if nested then
    for i = 1, #pts - 1 do
      local a, b = pts[i], pts[i + 1]
      if P.CrossesModelWall(cont, a[1], a[2], b[1], b[2]) then return true end
    end
  else
    for i = 1, #pts - 3, 2 do
      if P.CrossesModelWall(cont, pts[i], pts[i + 1], pts[i + 2], pts[i + 3]) then return true end
    end
  end
  return false
end

-- Grids laid over a continent's (a city's ruins up top, the caves: ns.CityHalls[cont]), by
-- area: { keys = the list indexed, n = its length, b = { [bucket] = { grid, ... } } }. Built
-- again when the list changes.
local OV_BUCKET = 256
local ovIndex = {}
local function OverlayIndex(cont)
  local keys = ns.CityHalls and ns.CityHalls[cont]
  if not keys then return nil end
  local ix = ovIndex[cont]
  if ix and ix.keys == keys and ix.n == #keys then return ix end
  ix = { keys = keys, n = #keys, b = {} }
  for _, key in ipairs(keys) do
    local o = ns.Terrain and ns.Terrain[key]
    if o and o.overlay then
      local x1, y1 = (32 - o.ty0) * TILE, (32 - o.tx0) * TILE -- (its north-west corner: rows run south, columns east)
      local x0, y0 = x1 - o.h * o.cell, y1 - o.w * o.cell
      for bx = math.floor(x0 / OV_BUCKET), math.floor(x1 / OV_BUCKET) do
        for by = math.floor(y0 / OV_BUCKET), math.floor(y1 / OV_BUCKET) do
          local k = bx * 65536 + by
          local list = ix.b[k]
          if not list then
            list = {}
            ix.b[k] = list
          end
          list[#list + 1] = o
        end
      end
    end
  end
  ovIndex[cont] = ix
  return ix
end

-- A grid laid over a continent's (a city's ruins up top, a cave: ns.CityHalls[cont]): its
-- own value at (x, y) and the grid, or nil where none has one (1: the continent's grid).
-- A cave's (Data/Caves.lua) are 0 open, 2 closed, 3 its floor under walkable ground (open,
-- up top or down below; its rock there is the continent's grid, 1).
-- (`floors`: past a capital's floors under others (`split`), to the grid of the floor over them.)
local function OverlayRaw(cont, x, y, floors)
  local ix = OverlayIndex(cont)
  if not ix then return nil end
  local list = ix.b[math.floor(x / OV_BUCKET) * 65536 + math.floor(y / OV_BUCKET)]
  if not list then return nil end
  for _, o in ipairs(list) do
    local col, row = ToCell(o, x, y)
    if row >= 1 and row <= o.h and col >= 1 and col <= o.w then
      local v = Cell(o, row, col)
      if v ~= 1 and not (floors and o.split) then return v, o end
    end
  end
  return nil
end
P.OverlayRaw = OverlayRaw

-- Whether (x, y) is within grid `o`'s rectangle (any of its cells: the continent's too).
function P.InGridRect(o, x, y)
  local col, row = ToCell(o, x, y)
  return row >= 1 and row <= o.h and col >= 1 and col <= o.w
end
-- The capital's grid (Data/Capitals.lua) whose rectangle holds (x, y), the biggest there (the city's
-- own, not a floor under it), its own cells or not: the rock between Ironforge's halls too. Nil: none.
function P.CapitalGridAt(cont, x, y)
  local ix = OverlayIndex(cont)
  local list = ix and ix.b[math.floor(x / OV_BUCKET) * 65536 + math.floor(y / OV_BUCKET)]
  local best
  for _, o in ipairs(list or {}) do
    if o.capital and P.InGridRect(o, x, y) and (not best or o.w * o.h > best.w * best.h) then best = o end
  end
  return best
end

-- An overlay's value at (x, y) (0 open, 2 closed), or nil where the continent's grid holds.
-- (A capital's floor under another: the one over it, which a straight line there stays on.)
local function Overlay(cont, x, y)
  local v = OverlayRaw(cont, x, y, true)
  if v == 3 then return 0 end
  if v == 2 then -- (closed there, unless a wall eraser opened it)
    local g = ns.Terrain and ns.Terrain[cont]
    local oc = g and openCells[g]
    if oc then
      local c, r = ToCell(g, x, y)
      if oc[r * 65536 + c] then return 0 end
    end
  end
  return v
end
P.Overlay = Overlay

-- Whether any overlay grid lies near the leg (x1, y1)-(x2, y2) (its buckets): its cells are
-- finer than the continent's, so a leg there is checked every OVERLAY_STEP yards.
P.OVERLAY_STEP = 0.75
local function OverlayNear(cont, x1, y1, x2, y2)
  local ix = OverlayIndex(cont)
  if not ix then return false end
  for bx = math.floor(math.min(x1, x2) / OV_BUCKET), math.floor(math.max(x1, x2) / OV_BUCKET) do
    for by = math.floor(math.min(y1, y2) / OV_BUCKET), math.floor(math.max(y1, y2) / OV_BUCKET) do
      if ix.b[bx * 65536 + by] then return true end
    end
  end
  return false
end
P.OverlayNear = OverlayNear

-- Cell value at world (x, y) on continent `cont` (2 outside the grid).
function P.At(cont, x, y)
  EnsureWalls()
  local ov = Overlay(cont, x, y)
  if ov then return ov end
  local g = ns.Terrain and ns.Terrain[cont]
  if not g then return 0 end -- no data: treat as open
  local col, row = ToCell(g, x, y)
  return Cell(g, row, col)
end

-- Cost (yards, water weighted) of walking straight from (x1, y1) to (x2, y2), or nil when
-- the line crosses blocked terrain. Blocked cells within END_SLACK of either end are
-- ignored: the player (or the road) is evidently standing there.
P.END_SLACK = 12
-- A start inside "blocked" terrain (the player is standing there, so it's walkable: the
-- slope data is too strict on rocky ground) may cross this much of it to open ground; a
-- stop placed inside it, STOP_SLACK. Ends on open ground keep END_SLACK.
P.START_SLACK = 60
P.STOP_SLACK = 40
-- (A grid with its own `slack`, a city's: its blocked cells are walls and ledges, so only
-- that much, or up to CITY_INSIDE_SLACK from a start or stop inside them.)
P.CITY_INSIDE_SLACK = 0 -- (Router starts and stops from the nearest open floor instead)

P.SEG_YIELD_EVERY = 200 -- samples between pauses when checked in the background (a cross-continent
-- leg in one call was the ride check's 40-50 ms slice, the seed-31 sweep, 2026-10-07)

-- Cliffs from the map's ground heights (Ground.lua, Data/Heights.lua): ground the terrain grid calls open can still be
-- a cliff, and a walk off it isn't a way down (Kooki3z 2026-11-20, Freewind Post: "not a safe path down"; from the
-- mesa's top to the road below, every step off-road, 130 yd straight down its side). Ground steeper than CLIFF_SLOPE
-- (about 50 degrees: the steepest a character walks up, as the pipeline's floors, recastmesh.WALK_SLOPE) is a cliff: a
-- straight leg (CliffAlong, so SegmentCost) never climbs one more than CLIFF_CLIMB_MAX, and drops off one only as far
-- as the safe jumps do (Router.TRACK_DROP_MAX, the cliff walls' CLIFF_DROP_MAX: no fall damage), downhill; walks over
-- the grid (FindPath) go round it either way, as round the cliff walls. Only where the ground has a height: none (no
-- data, a city's or a cave's own grid, water) is as before.
P.CLIFF_SLOPE = 1.2
P.CLIFF_CLIMB_MAX = 4 -- (yards of steep rise: a jump clears about 1.5; the grid's 16.7 yd cells smooth steps out)
P.CLIFF_SAMPLE = 4 -- yards between a leg's heights (the grid's cells are 16.7 yd: four a cell)
P.CLIFF_CELL_Z_MAX = 60000 -- (the grid cells' ground heights remembered, then started over)
-- The ground's height at (x, y) for the cliff checks (the road tools open or not, as Router.GroundZ), or nil.
local function GroundZ(cont, x, y)
  local GD = ns.Ground
  if not (GD and GD.At) then return nil end
  local was = GD.force
  GD.force = true
  local h = GD.At(cont, x, y)
  GD.force = was
  return type(h) == "number" and h or nil
end
-- (... and nil where it isn't the ground walked: water (the grid's 1, or the map's water over the ground: its floor,
-- swum over; the deep sea far out the grid closes too), a city's or a cave's own grid (their floors, not the land's). Not a bridge's model: its outline over the gorge is its sides' too (Freewind
-- Post's bridge reaches over the mesa's edge), and the bridges are raised roads, reached by their ends)
P.GroundZ = GroundZ -- (Router.MarkDeckDrops: the ground under a bridge's side)
local function WalkedZ(cont, g, x, y, near)
  if g then
    local c, r = ToCell(g, x, y)
    if Cell(g, r, c) == 1 then return nil end
  end
  if near and OverlayRaw(cont, x, y) then return nil end
  local z = GroundZ(cont, x, y)
  if z then
    local GD = ns.Ground
    local was = GD.force
    GD.force = true
    local w = GD.At(cont, x, y, true)
    GD.force = was
    if type(w) == "number" and w > z then return nil end
  end
  return z
end

-- Whether the straight leg from (x1, y1) to (x2, y2), walked that way, goes up or down a cliff (above): its ground
-- every CLIFF_SAMPLE yards, a run of steep samples rising more than CLIFF_CLIMB_MAX or falling more than the safe drop.
-- Remembered by the points, as SegmentCost (the ground doesn't change; a recalculation asks the same legs again).
local CLIFF_MEMO_MAX = 20000
cliffMemo, cliffMemoN = {}, 0
-- (in the background: a pause every CLIFF_YIELD_EVERY heights read, counted across the calls, not per leg. The road
-- network's dead ends check up to 32 legs each, every one shorter than a pause's worth, so none paused: slices of the
-- route's work up to 25 ms here, 56 on CI, release 1.3.12's checks)
P.CLIFF_YIELD_EVERY = 100
P.cliffSamples = 0
function P.CliffAlong(cont, x1, y1, x2, y2)
  local key = cont .. ":" .. x1 .. ":" .. y1 .. ":" .. x2 .. ":" .. y2
  local memo = cliffMemo
  local v = memo[key]
  if v ~= nil then return v end
  v = false
  local g = ns.Terrain and ns.Terrain[cont]
  local dx, dy = x2 - x1, y2 - y1
  local len = math.sqrt(dx * dx + dy * dy)
  local runs
  if len > 0 and not (g and g.slack) and ns.Ground and ns.Ground.At then
    local n = math.max(1, math.ceil(len / P.CLIFF_SAMPLE))
    local rise = P.CLIFF_SLOPE * len / n
    local drop = DropMax()
    local near = OverlayNear(cont, x1, y1, x2, y2)
    local co, isMain = coroutine.running()
    local canYield = co ~= nil and not isMain
    local up, down, prev, from = 0, 0, nil, 0
    local bans = P.jumpBans ~= nil
    local topX, topY
    for i = 0, n do
      if canYield then
        local k = P.cliffSamples + 1
        if k >= P.CLIFF_YIELD_EVERY or (k % 8 == 0 and SliceOver()) then
          k = 0
          coroutine.yield()
        end
        P.cliffSamples = k
      end
      local z = WalkedZ(cont, g, x1 + dx * i / n, y1 + dy * i / n, near)
      local was = down
      if z and prev and z - prev > rise then
        up, down = up + z - prev, 0
      elseif z and prev and prev - z > rise then
        if down == 0 then
          from = (i - 1) / n
          topX, topY = x1 + dx * (i - 1) / n, y1 + dy * (i - 1) / n
        end
        up, down = 0, down + prev - z
      else
        up, down = 0, 0
      end
      -- (each run down kept: the open world's drop rules, P.DropsAlong)
      if was > 0 and down == 0 then
        runs = runs or {}
        runs[#runs + 1] = { from, was }
      end
      if up > P.CLIFF_CLIMB_MAX or down > drop
          or (bans and down >= P.JUMP_FALL_MIN and JumpBanned(cont, topX, topY)) then
        v = true
        break
      end
      prev = z
    end
    if down > 0 and not v then
      runs = runs or {}
      runs[#runs + 1] = { from, down }
    end
  end
  if memo ~= cliffMemo then return v end -- (the limit changed while it paused: not kept under the new one)
  if cliffMemoN >= CLIFF_MEMO_MAX then cliffMemo, cliffMemoN, cliffRuns = {}, 0, {} end
  cliffMemo[key], cliffMemoN = v, cliffMemoN + 1
  if runs then cliffRuns[key] = runs end
  return v
end
-- The runs down CliffAlong found along a leg (asked first): { { t, dz }, ... } or nil.
function P.CliffRuns(cont, x1, y1, x2, y2)
  return cliffRuns[cont .. ":" .. x1 .. ":" .. y1 .. ":" .. x2 .. ":" .. y2]
end

-- The biggest drop the straight leg from (x1, y1) to (x2, y2) goes down, walked that way: where it starts and ends
-- along it (0..1) and how far it falls, or nil: a cliff wall crossed down its way (its `dz`; a yard either side of it)
-- or a run of the ground's steep samples falling (CliffAlong's rule). For the routes' big drops (Router.MarkBigDrops,
-- FallSpells.lua). Remembered by the points, as CliffAlong.
function P.FallAlong(cont, x1, y1, x2, y2)
  local key = cont .. ":" .. x1 .. ":" .. y1 .. ":" .. x2 .. ":" .. y2
  local v = fallMemo[key]
  if v ~= nil then
    if not v then return nil end
    return v[1], v[2], v[3]
  end
  local dx, dy = x2 - x1, y2 - y1
  local len = math.sqrt(dx * dx + dy * dy)
  local best
  if len > 0 then
    -- (cliff walls crossed down)
    EnsureWalls()
    local segs = wallSegs[cont]
    if segs then
      local B, seen = P.WALL_BUCKET, {}
      for kx = math.floor(math.min(x1, x2) / B), math.floor(math.max(x1, x2) / B) do
        for ky = math.floor(math.min(y1, y2) / B), math.floor(math.max(y1, y2) / B) do
          for _, s in ipairs(segs[kx * 65536 + ky] or {}) do
            if not seen[s] and s.down and s.dz and dx * s.down[1] + dy * s.down[2] > 0 then
              seen[s] = true
              local ex, ey = s[3] - s[1], s[4] - s[2]
              local den = dx * ey - dy * ex
              if math.abs(den) > 1e-9 then
                local t = ((s[1] - x1) * ey - (s[2] - y1) * ex) / den
                local u = ((s[1] - x1) * dy - (s[2] - y1) * dx) / den
                local dz = math.abs(s.dz)
                if t >= 0 and t <= 1 and u >= 0 and u <= 1 and (not best or dz > best[3]) then
                  local e = 1 / len
                  best = { math.max(0, t - e), math.min(1, t + e), dz }
                end
              end
            end
          end
        end
      end
    end
    -- (the ground's steep runs down)
    local g = ns.Terrain and ns.Terrain[cont]
    if not (g and g.slack) and ns.Ground and ns.Ground.At then
      local n = math.max(1, math.ceil(len / P.CLIFF_SAMPLE))
      local rise = P.CLIFF_SLOPE * len / n
      local near = OverlayNear(cont, x1, y1, x2, y2)
      local down, start, prev = 0, nil, nil
      local co, isMain = coroutine.running()
      local canYield = co ~= nil and not isMain
      for i = 0, n do
        if canYield then -- (in the background: paused as CliffAlong's)
          local k = P.cliffSamples + 1
          if k >= P.CLIFF_YIELD_EVERY or (k % 8 == 0 and SliceOver()) then
            k = 0
            coroutine.yield()
          end
          P.cliffSamples = k
        end
        local z = WalkedZ(cont, g, x1 + dx * i / n, y1 + dy * i / n, near)
        if z and prev and prev - z > rise then
          if down == 0 then start = i - 1 end
          down = down + prev - z
          if not best or down > best[3] then best = { start / n, i / n, down } end
        else
          down = 0
        end
        prev = z
      end
    end
  end
  if fallMemoN >= CLIFF_MEMO_MAX then fallMemo, fallMemoN = {}, 0 end
  fallMemo[key], fallMemoN = best or false, fallMemoN + 1
  if not best then return nil end
  return best[1], best[2], best[3]
end

-- Every drop the straight leg from (x1, y1) to (x2, y2) goes down, walked that way, in order along it: { { t, dz }, ... }
-- (0..1 along it, how far): the cliff walls crossed down their way and the ground's runs of steep samples falling
-- (FallAlong's, each run its own). For the open world's drop rules (Router.DropExtra): a step down, a fall worth it, a
-- chain of them down a slope.
function P.DropsAlong(cont, x1, y1, x2, y2)
  local dx, dy = x2 - x1, y2 - y1
  local len = math.sqrt(dx * dx + dy * dy)
  local out = {}
  if len <= 0 then return out end
  EnsureWalls()
  local segs = wallSegs[cont]
  if segs then
    local B, seen = P.WALL_BUCKET, {}
    for kx = math.floor(math.min(x1, x2) / B), math.floor(math.max(x1, x2) / B) do
      for ky = math.floor(math.min(y1, y2) / B), math.floor(math.max(y1, y2) / B) do
        for _, s in ipairs(segs[kx * 65536 + ky] or {}) do
          if not seen[s] and s.down and s.dz and dx * s.down[1] + dy * s.down[2] > 0 then
            seen[s] = true
            local ex, ey = s[3] - s[1], s[4] - s[2]
            local den = dx * ey - dy * ex
            if math.abs(den) > 1e-9 then
              local t = ((s[1] - x1) * ey - (s[2] - y1) * ex) / den
              local u = ((s[1] - x1) * dy - (s[2] - y1) * dx) / den
              if t >= 0 and t <= 1 and u >= 0 and u <= 1 then out[#out + 1] = { t, math.abs(s.dz) } end
            end
          end
        end
      end
    end
  end
  -- (the ground's runs down: CliffAlong's, sampled once for both)
  if not P.CliffAlong(cont, x1, y1, x2, y2) then
    for _, r in ipairs(P.CliffRuns(cont, x1, y1, x2, y2) or {}) do out[#out + 1] = { r[1], r[2] } end
  end
  table.sort(out, function(a, b) return a[1] < b[1] end)
  -- (one drop seen twice, the wall's and the ground's at it (its heights the wall's): within DROP_SAME_YD, the bigger)
  local merged = {}
  for _, d in ipairs(out) do
    local last = merged[#merged]
    if last and (d[1] - last[1]) * len <= P.DROP_SAME_YD then
      if d[2] > last[2] then last[2] = d[2] end
    else
      merged[#merged + 1] = { d[1], d[2] }
    end
  end
  return merged
end
P.DROP_SAME_YD = 6

-- A straight leg's drops' extra cost by the open world's rules (Router.DropExtra): nil when one isn't taken (a chain).
local function DropsCost(cont, x1, y1, x2, y2)
  local Rt = ns.Router
  if not (Rt and Rt.DropExtra) then return 0 end
  local len = math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)
  local extra, lastT = 0, nil
  for _, d in ipairs(P.DropsAlong(cont, x1, y1, x2, y2)) do
    local chained = lastT ~= nil and Rt.ChainDrop(d[2]) and (d[1] - lastT) * len <= Rt.CHAIN_YD
    local e = Rt.DropExtra(d[2], chained, 0)
    if not e then return nil end
    extra = extra + e
    if Rt.ChainDrop(d[2]) then lastT = d[1] end
  end
  return extra
end

-- The ground's height at grid g's cell (c, r)'s middle for the walks' cliff check (WalkedZ), false where it has none;
-- remembered (cells don't change: a search asks each cell's neighbors again and again).
local cellZ, cellZN = {}, 0
-- (the ground's heights read again: the tests' own ground)
function P.ClearCliffMemo()
  cliffMemo, cliffMemoN, cellZ, cellZN, cliffRuns = {}, 0, {}, 0, {}
  fallMemo, fallMemoN = {}, 0
end
local function CellZ(cont, g, c, r)
  local t = cellZ[g]
  local row = t and t[r]
  local z = row and row[c]
  if z == nil then
    local x, y = CellCentre(g, c, r)
    z = WalkedZ(cont, g, x, y, true) or false
    if cellZN >= P.CLIFF_CELL_Z_MAX then cellZ, cellZN, t = {}, 0, nil end
    if not t then
      t = {}
      cellZ[g] = t
    end
    row = t[r]
    if not row then
      row = {}
      t[r] = row
    end
    row[c], cellZN = z, cellZN + 1
  end
  return z
end

-- Steep ground walked down (Kooki3z 2026-11-20, Stonetalon Mountains: on the road at the top of a ledge, the stop
-- below it to the north-east, routed ~640 yd down the road and back up the valley; "you should be able to go off the
-- cliff here"). The terrain grid closes a cell steeper than 50 degrees both ways (roads/terrain.py), and a cliff wall's
-- way down opened only its own cells to the ground's value underneath, still closed there, so no straight leg ever went
-- down the ledge's face. A character slides down such a face: a straight leg (SegmentCost) may cross a run of the
-- terrain's own steep cells (not a wall's, a building's, a banned swim's, a city's grid) where it goes down it, the
-- ground's height (Ground.lua) at the open ground past the run at least STEEP_FALL_MIN_YD (a ledge, ~33 yd across
-- the closed cells there; not a bump or a hillside the grid's cells smooth out: those stay closed, as before, and the
-- routes elsewhere as they were: at 15 yd, route-quality had 6 trips slower, a slide off a hill near Everlook making
-- a road way beat the walk at road mode's 2x, 2026-11-20) and STEEP_FALL a yard
-- of the run lower than before it, and the run at most STEEP_RUN_MAX_YD (a ledge's face, not a mountainside). Each run
-- costs STEEP_RUN_COST yards more (as Router.DROP_COST, twice: taken only when it saves real distance). How far it falls is CliffAlong's, after: the ground's cliffs only as far as the safe drop.
-- Never up a steep run; walks over the grid (FindPath, the blocks) still go round it either way.
P.STEEP_RUN_MAX_YD = 60
P.STEEP_FALL = 0.5
P.STEEP_FALL_MIN_YD = 25
P.STEEP_RUN_COST = 60
local function SteepCell(g, row, col, dx, dy)
  if row < 1 or row > g.h or col < 1 or col > g.w then return false end
  local bl = banRows[g] and banRows[g][row]
  if bl then
    for i = 1, #bl - 1, 2 do
      if col >= bl[i] and col <= bl[i + 1] then return false end
    end
  end
  local wc = wallCells[g]
  local w = wc and wc[row * 65536 + col]
  if w == true then return false end
  if type(w) == "table" and dx * w[1] + dy * w[2] <= 0 then return false end -- (a cliff wall's, crossed up)
  if Buildings(g)[row * 65536 + col] then return false end
  return CellBase(g, row, col) == 2
end
-- (the run of steep cells along the leg from t0 to t1, the open samples either side: walked down it?)
local function SteepRunDown(cont, g, x1, y1, dx, dy, len, t0, t1, near)
  local h = (t1 - t0) * len
  if h > P.STEEP_RUN_MAX_YD then return false end
  local z0 = WalkedZ(cont, g, x1 + dx * t0, y1 + dy * t0, near)
  local z1 = WalkedZ(cont, g, x1 + dx * t1, y1 + dy * t1, near)
  if not (z0 and z1) then return false end
  local fall = z0 - z1
  return fall >= P.STEEP_FALL_MIN_YD and fall >= P.STEEP_FALL * h
end

local function SegmentCostRaw(cont, x1, y1, x2, y2, endSlack)
  -- (a wall: never, not even near its ends. Not the model walls, P.CrossesModelWall: the terrain grid's cells and its
  -- prepared blocks don't know them, so its searches would go through and the pieces be refused: the road graph's joins
  -- and the Hinterlands' trips from the west were lost, item 78. The world grid and the spell jumps keep to them)
  if P.CrossesWall(cont, x1, y1, x2, y2, nil, true) then return nil end
  local g = ns.Terrain and ns.Terrain[cont]
  local dx, dy = x2 - x1, y2 - y1
  local len = math.sqrt(dx * dx + dy * dy)
  if not g then return len end
  local step = g.cell / 3 -- fine enough not to skip across the corner of a blocked cell
  local near = OverlayNear(cont, x1, y1, x2, y2)
  if near then step = math.min(step, P.OVERLAY_STEP) end -- (nor an overlay's)
  local n = math.max(1, math.ceil(len / step))
  local water = 0
  local co, isMain = coroutine.running()
  local canYield = co ~= nil and not isMain
  local yards = endSlack or P.END_SLACK
  if g.slack then yards = endSlack and math.min(endSlack, math.max(g.slack, P.CITY_INSIDE_SLACK)) or g.slack end
  local slack = len > 0 and yards / len or 1
  -- (no grid laid over the continent near the line: its own cells only; and a cell's value is
  -- looked up once, not for each of the samples in it)
  local k = TILE / g.cell
  local lastRow, lastCol, lastV, lastB, lastS
  local openT, runFrom = 0, nil -- (the last open sample's t; a steep run's start, the open sample before it)
  local steepRuns = 0
  -- (a building's cells: no end slack, unless that end is in a building itself: a stop at the innkeeper)
  local bset = Buildings(g)
  local c1, r1 = ToCell(g, x1, y1)
  local c2, r2 = ToCell(g, x2, y2)
  local inB1 = bset[r1 * 65536 + c1] and Cell(g, r1, c1) == 2
  local inB2 = bset[r2 * 65536 + c2] and Cell(g, r2, c2) == 2
  for i = 0, n do
    if canYield and i > 0 and (i % P.SEG_YIELD_EVERY == 0 or (i % 8 == 0 and SliceOver())) then coroutine.yield() end
    local t = i / n
    local x, y = x1 + dx * t, y1 + dy * t
    local ov = near and Overlay(cont, x, y) or nil
    if ov == 2 and t > 0 and t < 1 then return nil end -- (a city's ruins: its walls are real, no slack)
    local v, b, st = ov, false, false
    if not v then -- (the continent's own grid: the overlay was just asked)
      local col = math.floor(((32 - y / TILE) - g.tx0) * k) + 1
      local row = math.floor(((32 - x / TILE) - g.ty0) * k) + 1
      if row == lastRow and col == lastCol then
        v, b, st = lastV, lastB, lastS
      else
        v = Cell(g, row, col)
        -- (a cliff's cell crossed toward its low side: the ground's own value, the drop is safe)
        local cd = v == 2 and CliffCell(g, row, col)
        if cd and dx * cd[1] + dy * cd[2] > 0 then v = CellBase(g, row, col) end
        b = v == 2 and bset[row * 65536 + col] or false
        -- (the terrain's own steep cell: walked down, maybe; SteepRunDown above)
        st = v == 2 and not b and not g.slack and SteepCell(g, row, col, dx, dy) or false
        lastRow, lastCol, lastV, lastB, lastS = row, col, v, b, st
      end
    end
    if b then
      if not ((t <= slack and inB1) or (t >= 1 - slack and inB2)) then return nil end
    elseif v == 2 and t > slack and t < 1 - slack then
      if not st then return nil end
      runFrom = runFrom or openT
    elseif runFrom then
      if not SteepRunDown(cont, g, x1, y1, dx, dy, len, runFrom, t, near) then return nil end
      runFrom, steepRuns = nil, steepRuns + 1
    end
    if not (v == 2 and t > slack and t < 1 - slack) then openT = t end
    if v == 1 then water = water + 1 end
  end
  if P.CliffAlong(cont, x1, y1, x2, y2) then return nil end -- (open ground, but up or down a cliff: CliffAlong)
  local drops = DropsCost(cont, x1, y1, x2, y2) -- (its drops by the open world's rules: a chain is walked round)
  if not drops then return nil end
  return len + len * (water / (n + 1)) * (P.SwimCost() - 1) + steepRuns * P.STEEP_RUN_COST + drops
end

-- Every caller's checks remembered, the exact points and end slack the key (no rounding: routes stay the
-- same to the byte): about 70% of a recalculation's calls repeat exactly — Smooth's unchanged tail, the
-- bridges', a walk rejoined (the 2026-10-07 router profile, ~7 ms a recalculation on a long trip). The
-- terrain and buildings don't change; walls and drawn roads do through RefreshWalls, which starts it over.
local SEG_MEMO_MAX = 20000
local segMemo, segMemoN = {}, 0
function P.ClearSegMemo() segMemo, segMemoN = {}, 0 end
function P.SegmentCost(cont, x1, y1, x2, y2, endSlack)
  local key = cont .. ":" .. x1 .. ":" .. y1 .. ":" .. x2 .. ":" .. y2 .. ":" .. (endSlack or "d")
    .. (ns.Router and ns.Router.ExpertJumper and ns.Router.ExpertJumper() and ":x" or "")
  local c = segMemo[key]
  if c == nil then
    c = SegmentCostRaw(cont, x1, y1, x2, y2, endSlack) or false
    if segMemoN >= SEG_MEMO_MAX then segMemo, segMemoN = {}, 0 end
    segMemo[key], segMemoN = c, segMemoN + 1
  end
  return c or nil
end

-- The stretches of the straight line (x1, y1)-(x2, y2) in water to swim (the grid's 1; deep sea far out is closed,
-- never swum) as { t1, t2, ... } from 0 to 1 along it, in order; false when none. Sampled every half cell straight off
-- the continent's grid (no grid laid over it: a capital's water is a level of its own). Remembered by the points: a
-- route worked out again keeps most of its pieces (Nav.SwimSpans, the map's wavy swims and the honest swim time).
local WET_MEMO_MAX = 20000
local wetMemo, wetMemoN = {}, 0
function P.WaterSpans(cont, x1, y1, x2, y2)
  local key = cont .. ":" .. x1 .. ":" .. y1 .. ":" .. x2 .. ":" .. y2
  local v = wetMemo[key]
  if v ~= nil then return v end
  v = false
  local g = ns.Terrain and ns.Terrain[cont]
  local dx, dy = x2 - x1, y2 - y1
  local len = math.sqrt(dx * dx + dy * dy)
  if g and not g.slack and not g.overlay and len > 0 then
    local n = math.max(1, math.ceil(len / (g.cell / 2)))
    local k = TILE / g.cell
    local lastRow, lastCol, lastV
    local s
    for i = 0, n - 1 do
      local t = (i + 0.5) / n
      local col = math.floor(((32 - (y1 + dy * t) / TILE) - g.tx0) * k) + 1
      local row = math.floor(((32 - (x1 + dx * t) / TILE) - g.ty0) * k) + 1
      if row ~= lastRow or col ~= lastCol then
        lastRow, lastCol, lastV = row, col, Cell(g, row, col)
      end
      if lastV == 1 then
        if not s then s = i / n end
      elseif s then
        v = v or {}
        v[#v + 1], v[#v + 2] = s, i / n
        s = nil
      end
    end
    if s then
      v = v or {}
      v[#v + 1], v[#v + 2] = s, 1
    end
  end
  if wetMemoN >= WET_MEMO_MAX then wetMemo, wetMemoN = {}, 0 end
  wetMemo[key], wetMemoN = v, wetMemoN + 1
  return v
end

-- A swim removed from the trip (asked 2026-11-19: "a removed swim's water section must be ignored for the remainder of
-- the time that route is active"): the water it's in, banned (P.SetSwimBans). The grid's water cells joined to the
-- swim's (`pts`, a flat point list on `cont`), side by side, within SWIM_BAN_REACH_YD of the swim's box and at most
-- SWIM_BAN_MAX_CELLS of them, nearest first: a bay or a lake whole, a short swim at sea not the sea. Flooded by runs
-- of a row (the grid's own, decoded once), not cell by cell: a few milliseconds. { cont, rows = { row, first col,
-- count, ... }, n = cells }, or nil (no water under it).
P.SWIM_BAN_REACH_YD = 1500
P.SWIM_BAN_MAX_CELLS = 40000
local function RowRuns(g, row)
  local rc = cache[g]
  if not rc then
    rc = {}
    cache[g] = rc
  end
  local runs = rc[row]
  if not runs then
    runs = DecodeRow(Rows(g)[row], g.short, g.long, g.deep)
    rc[row] = runs
  end
  return runs
end
function P.SwimSection(cont, pts)
  local g = ns.Terrain and ns.Terrain[cont]
  if not (g and not g.slack and not g.overlay and pts and #pts >= 4) then return nil end
  local x0, x1, y0, y1 = math.huge, -math.huge, math.huge, -math.huge
  for i = 1, #pts - 1, 2 do
    x0, x1 = math.min(x0, pts[i]), math.max(x1, pts[i])
    y0, y1 = math.min(y0, pts[i + 1]), math.max(y1, pts[i + 1])
  end
  local pad = P.SWIM_BAN_REACH_YD
  local cA, rA = ToCell(g, x1 + pad, y1 + pad)
  local cB, rB = ToCell(g, x0 - pad, y0 - pad)
  local cmin, cmax = math.max(1, math.min(cA, cB)), math.min(g.w, math.max(cA, cB))
  local rmin, rmax = math.max(1, math.min(rA, rB)), math.min(g.h, math.max(rA, rB))
  -- (each water run of a row over [a, b], clipped to the box: fn(first, last))
  local function EachWater(r, a, b, fn)
    local runs = RowRuns(g, r)
    a, b = math.max(a, cmin), math.min(b, cmax)
    if a > b then return end
    local lo, hi = 1, #runs / 2
    while lo < hi do
      local mid = math.floor((lo + hi) / 2)
      if runs[mid * 2 - 1] < a then lo = mid + 1 else hi = mid end
    end
    for k = lo, #runs / 2 do
      local first = k > 1 and runs[k * 2 - 3] + 1 or 1
      if first > b then break end
      if runs[k * 2] == 1 then fn(math.max(first, cmin), math.min(runs[k * 2 - 1], cmax)) end
    end
  end
  local seen, queue, n, out = {}, {}, 0, {}
  local full = false
  local function Add(r, a, b)
    if full or seen[r * 65536 + a] then return end
    if n + (b - a + 1) > P.SWIM_BAN_MAX_CELLS then
      full = true
      return
    end
    seen[r * 65536 + a] = true
    n = n + (b - a + 1)
    queue[#queue + 1], queue[#queue + 2], queue[#queue + 3] = r, a, b
    out[#out + 1], out[#out + 2], out[#out + 3] = r, a, b - a + 1
  end
  -- (the swim's own water: every half cell along it)
  for i = 1, #pts - 3, 2 do
    local ax, ay, bx, by = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
    local m = math.max(1, math.ceil(math.sqrt((bx - ax) ^ 2 + (by - ay) ^ 2) / (g.cell / 2)))
    for k = 0, m do
      local c, r = ToCell(g, ax + (bx - ax) * k / m, ay + (by - ay) * k / m)
      if r >= rmin and r <= rmax then EachWater(r, c, c, function(a, b) Add(r, a, b) end) end
    end
  end
  -- (then outward, row by row: the water runs beside each one found, side by side)
  local q = 1
  while q <= #queue and not full do
    local r, a, b = queue[q], queue[q + 1], queue[q + 2]
    q = q + 3
    for _, nr in ipairs({ r - 1, r + 1 }) do
      if nr >= rmin and nr <= rmax then EachWater(nr, a, b, function(a2, b2) Add(nr, a2, b2) end) end
    end
  end
  if n == 0 then return nil end
  return { cont = cont, rows = out, n = n }
end

-- The water banned now (Nav.SyncSwim: the trip's removed swims, `bans` = { { cont, rows }, ... }, P.SwimSection's):
-- closed as a wall is, in the walks' searches, the blocks' (those it's in worked out here, and their neighbors) and the
-- straight checks. Whether it changed (the walks then start over: Router.WallsChanged).
local banKey = ""
function P.SetSwimBans(bans)
  local parts = {}
  for _, b in ipairs(bans or {}) do
    local rows = b.rows
    parts[#parts + 1] = b.cont .. ":" .. #rows .. ":" .. (rows[1] or 0) .. ":" .. (rows[2] or 0) .. ":" .. (rows[#rows] or 0)
  end
  local key = table.concat(parts, "/")
  if key == banKey then return false end
  banKey = key
  EnsureWalls()
  banRows, banDirty = {}, {}
  for _, b in ipairs(bans or {}) do
    local g = ns.Terrain and ns.Terrain[b.cont]
    if g then
      local br = banRows[g] or {}
      banRows[g] = br
      local H = ns.TerrainHPA and ns.TerrainHPA[b.cont]
      if H and not (H.w == g.w and H.h == g.h) then H = nil end
      local d = H and (banDirty[b.cont] or {})
      local rows = b.rows
      for i = 1, #rows - 2, 3 do
        local r, a, cnt = rows[i], rows[i + 1], rows[i + 2]
        local l = br[r] or {}
        br[r] = l
        l[#l + 1], l[#l + 2] = a, a + cnt - 1
        if d then
          for c = a, a + cnt - 1 + H.K, H.K do MarkBlock(H, d, r, math.min(c, a + cnt - 1)) end
        end
      end
      if d then banDirty[b.cont] = d end
    end
  end
  MergeDirty()
  wetMemo, wetMemoN = {}, 0
  if P.ClearSegMemo then P.ClearSegMemo() end
  return true
end
-- Whether world (x, y) on `cont` is in water banned now (P.SetSwimBans; the world grid's swims there are closed).
function P.SwimBanned(cont, x, y)
  local g = ns.Terrain and ns.Terrain[cont]
  local br = g and banRows[g]
  if not br then return false end
  local c, r = ToCell(g, x, y)
  local l = br[r]
  for i = 1, l and #l - 1 or 0, 2 do
    if c >= l[i] and c <= l[i + 1] then return true end
  end
  return false
end
function P.AnySwimBans(cont)
  local g = ns.Terrain and ns.Terrain[cont]
  return g ~= nil and banRows[g] ~= nil and next(banRows[g]) ~= nil
end
-- Whether world (x, y) on `cont` is in the water of `ban` (P.SwimSection's), banned or not. (By row, made once a ban:
-- not on the ban itself, which is saved.)
local banIndex = setmetatable({}, { __mode = "k" })
function P.InSwimSection(ban, cont, x, y)
  local g = ns.Terrain and ns.Terrain[cont]
  if not (g and ban and ban.cont == cont and ban.rows) then return false end
  local ix = banIndex[ban.rows]
  if not ix then
    ix = {}
    local rows = ban.rows
    for i = 1, #rows - 2, 3 do
      local l = ix[rows[i]] or {}
      ix[rows[i]] = l
      l[#l + 1], l[#l + 2] = rows[i + 1], rows[i + 1] + rows[i + 2] - 1
    end
    banIndex[ban.rows] = ix
  end
  local c, r = ToCell(g, x, y)
  local l = ix[r]
  for i = 1, l and #l - 1 or 0, 2 do
    if c >= l[i] and c <= l[i + 1] then return true end
  end
  return false
end
-- The world box of `ban`'s water: x0, x1, y0, y1 (nil when its continent has no grid).
function P.SwimSectionBox(ban)
  local g = ns.Terrain and ns.Terrain[ban.cont]
  if not g then return nil end
  local x0, x1, y0, y1 = math.huge, -math.huge, math.huge, -math.huge
  local rows = ban.rows
  for i = 1, #rows - 2, 3 do
    for _, c in ipairs({ rows[i + 1], rows[i + 1] + rows[i + 2] - 1 }) do
      local x, y = CellCentre(g, c, rows[i])
      x0, x1, y0, y1 = math.min(x0, x), math.max(x1, x), math.min(y0, y), math.max(y1, y)
    end
  end
  if x0 > x1 then return nil end
  return x0, x1, y0, y1
end

-- Binary heap keyed on f.
local function Push(h, node, f)
  h[#h + 1] = { node, f }
  local i = #h
  while i > 1 do
    local p = math.floor(i / 2)
    if h[p][2] <= h[i][2] then break end
    h[p], h[i] = h[i], h[p]
    i = p
  end
end

local function Pop(h)
  local top = h[1]
  local last = table.remove(h)
  if #h > 0 then
    h[1] = last
    local i = 1
    while true do
      local l, r, m = i * 2, i * 2 + 1, i
      if h[l] and h[l][2] < h[m][2] then m = l end
      if h[r] and h[r][2] < h[m][2] then m = r end
      if m == i then break end
      h[m], h[i] = h[i], h[m]
      i = m
    end
  end
  return top
end

P.PATH_PAD = 50 -- cells searched around the two points' bounding box
P.PATH_MAX_CELLS = 520 * 520
-- Cells expanded before giving up (the search runs in the background in slices, so this
-- only bounds how long a hopeless search, e.g. walled in by a town's terrain, keeps going).
P.PATH_MAX_EXPANSIONS = 80000
P.PATH_YIELD_EVERY = 50 -- cells expanded between pauses when run in the background

local SQ2 = math.sqrt(2)

-- The cost rule's value of a continent grid's cell: its own (walls and erased ground in), or,
-- under a capital's or the ruins' grid (not a cave's), that one's at the cell's middle.
local function BaseValue(g, cont, hasOverlay, c, r)
  local v = Cell(g, r, c)
  if hasOverlay then
    local cx, cy = CellCentre(g, c, r)
    local ov, o = OverlayRaw(cont, cx, cy, true)
    if ov and not o.cave then v = ov end
  end
  return v
end

-- A row of `cont`'s grid as those values, one digit a cell (for the offline prep, hpa.py).
function P.BaseRow(cont, r)
  local g = ns.Terrain[cont]
  local hasOverlay = ns.CityHalls and ns.CityHalls[cont] and true
  local t = {}
  for c = 1, g.w do t[c] = BaseValue(g, cont, hasOverlay, c, r) end
  return table.concat(t)
end

-- Cheapest walks over cells from (c0, r0): { [r * 65536 + c] = cost } and where each came
-- from. `step(c, r)`: the multiplier for stepping into a cell, nil where it can't go (a
-- diagonal step needs both cells beside it open). `back`: walks to (c0, r0) instead (each
-- entry's `came` is the next cell toward it).
local function Spread(step, c0, r0, back, pause)
  local start = r0 * 65536 + c0
  local dist, came, done, open = { [start] = 0 }, {}, {}, {}
  Push(open, start, 0)
  while #open > 0 do
    local n = Pop(open)[1]
    if not done[n] then
      done[n] = true
      if pause then pause() end
      local r, c = math.floor(n / 65536), n % 65536
      local here = back and (step(c, r) or 1) -- (walking back: stepping into this cell)
      for dr = -1, 1 do
        for dc = -1, 1 do
          if dr ~= 0 or dc ~= 0 then
            local m = step(c + dc, r + dr, c, r)
            if m and (dr == 0 or dc == 0 or (step(c + dc, r) and step(c, r + dr))) then
              local k = (r + dr) * 65536 + c + dc
              local d = dist[n] + (back and here or m) * ((dr ~= 0 and dc ~= 0) and SQ2 or 1)
              if not done[k] and (dist[k] == nil or d < dist[k]) then
                dist[k], came[k] = d, n
                Push(open, k, d)
              end
            end
          end
        end
      end
    end
  end
  return dist, came
end

-- A table per row of cells, made when first wanted: t[r][c]. (One table of every cell a search looked at grows twice
-- as big each time it's full, putting every cell in it again at once: 20 ms between two of a background search's
-- pauses. A row's table stays small.)
local function Row(t, r)
  local row = t[r]
  if not row then
    row = {}
    t[r] = row
  end
  return row
end

-- A* over cells from (c1, r1) to (c2, r2): the cells { {c, r}, ... }, or nil.
local function CellPath(step, c1, r1, c2, r2, pause, limit)
  local start, goal = r1 * 65536 + c1, r2 * 65536 + c2
  local gs, came, closed, open = {}, {}, {}, {} -- (by row: Row)
  Row(gs, r1)[c1] = 0
  Push(open, start, 0)
  local expanded = 0
  while #open > 0 do
    local n = Pop(open)[1]
    if n == goal then break end
    local r, c = math.floor(n / 65536), n % 65536
    local shut = Row(closed, r)
    if not shut[c] then
      shut[c] = true
      expanded = expanded + 1
      if limit and expanded > limit then return nil end
      if pause then pause() end
      local gn = gs[r][c]
      for dr = -1, 1 do
        for dc = -1, 1 do
          if dr ~= 0 or dc ~= 0 then
            local m = step(c + dc, r + dr, c, r)
            if m and (dr == 0 or dc == 0 or (step(c + dc, r) and step(c, r + dr))) then
              local k, gr, cc = (r + dr) * 65536 + c + dc, Row(gs, r + dr), c + dc
              local ng = gn + m * ((dr ~= 0 and dc ~= 0) and SQ2 or 1)
              if not Row(closed, r + dr)[cc] and (gr[cc] == nil or ng < gr[cc]) then
                gr[cc], Row(came, r + dr)[cc] = ng, n
                Push(open, k, ng + math.sqrt((c + dc - c2) ^ 2 + (r + dr - r2) ^ 2))
              end
            end
          end
        end
      end
    end
  end
  if not (gs[r2] and gs[r2][c2]) then return nil end
  local cells, cur = {}, goal
  while cur do
    local cr, cc = math.floor(cur / 65536), cur % 65536
    table.insert(cells, 1, { cc, cr })
    cur = came[cr] and came[cr][cc]
  end
  return cells
end

-- Whether CellPath from (c1, r1) can't reach (c2, r2) because the goal's open cells are shut in: the cells a step
-- may enter, joined to the goal (the same moves, both ways: a move into a cell needs only that cell and the two
-- beside a diagonal), counted up to `limit`; all found and none of them a step from the start, there's no way. Nil
-- when it can't tell (more than `limit` of them). (issue #322: walking by Brill's buildings, the player and the road
-- point a walk was searched to stood in the cells of the walls drawn round them, shut in; each search flooded its
-- whole box before giving up, 70 ms of background work, one after another while the player walked)
P.SHUT_IN_CELLS = 400
local function ShutIn(step, c1, r1, c2, r2, limit, pause)
  if c1 == c2 and r1 == r2 then return false end
  if not step(c2, r2) then return true end -- (never stepped into)
  local function moves(c, r, dc, dr) -- (a move from (c, r) to the cell beside it, as CellPath allows)
    return step(c + dc, r + dr, c, r) and (dr == 0 or dc == 0 or (step(c + dc, r) and step(c, r + dr))) and true or false
  end
  local seen, list, n = { [r2 * 65536 + c2] = true }, { c2, r2 }, 1
  local i = 1
  while i < #list do
    if pause then pause() end -- (each cell's steps: the cliffs' heights, a tile of ground decoded now and then)
    local c, r = list[i], list[i + 1]
    i = i + 2
    if math.abs(c - c1) <= 1 and math.abs(r - r1) <= 1 and moves(c1, r1, c - c1, r - r1) then return false end
    for dr = -1, 1 do
      for dc = -1, 1 do
        if (dr ~= 0 or dc ~= 0) and moves(c, r, dc, dr) then
          local k = (r + dr) * 65536 + c + dc
          if not seen[k] then
            n = n + 1
            if n > limit then return nil end
            seen[k] = true
            list[#list + 1], list[#list + 2] = c + dc, r + dr
          end
        end
      end
    end
  end
  return true
end

-- The cells on the line from (c1, r1) to (c2, r2) when every one of them is plain open ground
-- (a step of 1: no water, no guards' reach), with the walk's cost over cells (the 8-way
-- distance, what a search would find there); else nil. Open ground needs no search.
local function LineCells(step, c1, r1, c2, r2)
  local dc, dr = c2 - c1, r2 - r1
  local n = math.max(math.abs(dc), math.abs(dr))
  local cells = { { c1, r1 } }
  local pc, pr = c1, r1
  for i = 1, n do
    local c, r = c1 + math.floor(dc * i / n + 0.5), r1 + math.floor(dr * i / n + 0.5)
    if step(c, r, pc, pr) ~= 1 then return nil end
    if c ~= pc and r ~= pr and not (step(c, pr) == 1 and step(pc, r) == 1) then return nil end
    cells[#cells + 1] = { c, r }
    pc, pr = c, r
  end
  local a, b = math.abs(dc), math.abs(dr)
  return cells, math.max(a, b) + (SQ2 - 1) * math.min(a, b)
end

-- Searching by blocks (hierarchical A*, as Shortest Path Forever does): a continent's grid cut
-- into blocks of K x K cells (Data/TerrainHPA.lua, prepared offline by `agps terrain-hpa`,
-- app/azerothgps/hpa.py): each block's ways through to its neighbors (along each border, one
-- per opening, or one at each end of a wide one) and the walks between them inside it. A long
-- walk is searched over those (a few hundred nodes, not tens of thousands of cells), then only
-- the cells across the blocks it goes through; walled in, that's known at once. The blocks the
-- player's own walls or wall erasers change (and their neighbors) are worked out here instead.
P.HPA_MIN_CELLS = 40 -- start and stop at least this many cells apart (either way): by blocks
P.HPA_RUN_SPLIT = 8 -- (hpa.RUN_SPLIT) an opening this wide gets a way through at each end, else one in its middle

local function Two(s, i) return INDEX[s:byte(i)] * 64 + INDEX[s:byte(i + 1)] end

-- A block's ways through: { n, r = {}, c = {} (their cells), cost = {} (n x n: walking
-- between two inside the block, false: no way), at = { [cell in the block] = way } }.
local function DecodeBlock(H, b)
  local bl = { n = 0, r = {}, c = {}, cost = {}, at = {} }
  local s = H.c[b]
  if not s then return bl end
  local K = H.K
  local r0, c0 = math.floor(b / H.nx) * K, (b % H.nx) * K
  local n, p = Two(s, 1), 3
  for i = 1, n do
    local l = Two(s, p)
    p = p + 2
    bl.r[i], bl.c[i], bl.at[l] = r0 + math.floor(l / K) + 1, c0 + l % K + 1, i
  end
  for i = 1, n - 1 do
    for j = i + 1, n do
      local v = Two(s, p)
      p = p + 2
      local d = v < 4095 and v / 4 or false
      bl.cost[(i - 1) * n + j], bl.cost[(j - 1) * n + i] = d, d
    end
  end
  bl.n = n
  return bl
end

-- The same worked out from the grid as it is now (the player's walls in), as hpa.py does.
-- (`pause`: in a background search, a pause every so often: a removed swim's bay changes dozens of blocks, 150 ms
-- in one go)
local function BuildBlock(g, cont, H, b, pause)
  local K = H.K
  local br, bc = math.floor(b / H.nx), b % H.nx
  local r0, c0 = br * K, bc * K
  local hasOverlay = ns.CityHalls and ns.CityHalls[cont] and true
  local vals = {}
  local function V(c, r)
    if r < 1 or r > g.h or c < 1 or c > g.w then return 2 end
    local k = r * 65536 + c
    local v = vals[k]
    if not v then
      v = BaseValue(g, cont, hasOverlay, c, r)
      vals[k] = v
    end
    return v
  end
  local set = {}
  local function runs(ok, at)
    local s
    for k = 0, K do
      local o = k < K and ok(k)
      if o and not s then s = k end
      if not o and s then
        local e = k - 1
        if e - s + 1 >= P.HPA_RUN_SPLIT then
          set[at(s)], set[at(e)] = true, true
        else
          set[at(math.floor((s + e) / 2))] = true
        end
        s = nil
      end
    end
  end
  if bc > 0 then runs(function(k) return V(c0 + 1, r0 + k + 1) ~= 2 and V(c0, r0 + k + 1) ~= 2 end, function(k) return k * K end) end
  if bc < H.nx - 1 then
    runs(function(k) return V(c0 + K, r0 + k + 1) ~= 2 and V(c0 + K + 1, r0 + k + 1) ~= 2 end, function(k) return k * K + K - 1 end)
  end
  if br > 0 then runs(function(k) return V(c0 + k + 1, r0 + 1) ~= 2 and V(c0 + k + 1, r0) ~= 2 end, function(k) return k end) end
  if br < H.ny - 1 then
    runs(function(k) return V(c0 + k + 1, r0 + K) ~= 2 and V(c0 + k + 1, r0 + K + 1) ~= 2 end, function(k) return (K - 1) * K + k end)
  end
  local list = {}
  for l in pairs(set) do list[#list + 1] = l end
  table.sort(list)
  local bl = { n = #list, r = {}, c = {}, cost = {}, at = {} }
  for i, l in ipairs(list) do
    bl.r[i], bl.c[i], bl.at[l] = r0 + math.floor(l / K) + 1, c0 + l % K + 1, i
  end
  local function step(c, r)
    if c <= c0 or c > c0 + K or r <= r0 or r > r0 + K then return nil end
    local v = V(c, r)
    if v == 2 then return nil end
    return v == 1 and P.SWIM_COST or 1
  end
  for i = 1, bl.n do
    local dist = Spread(step, bl.c[i], bl.r[i], nil, pause)
    for j = 1, bl.n do
      if j ~= i then bl.cost[(i - 1) * bl.n + j] = dist[bl.r[j] * 65536 + bl.c[j]] or false end
    end
  end
  return bl
end

-- The walk's cells by blocks: { {c, r}, ... }; or nil and "none" (no way through the blocks
-- over the search box), or nil and "cells" (search it cell by cell after all).
local function ByBlocks(g, H, cont, c1, r1, c2, r2, step, box, danger, pause)
  local K, nx, ny = H.K, H.nx, H.ny
  local function BlockOf(c, r) return math.floor((r - 1) / K) * nx + math.floor((c - 1) / K) end
  local blocks = hpaBlocks[cont]
  if not blocks then
    blocks = {}
    hpaBlocks[cont] = blocks
  end
  local dirty = hpaDirty[cont]
  local function Block(b)
    local bl = blocks[b]
    if not bl then
      bl = (dirty and dirty[b]) and BuildBlock(g, cont, H, b, pause) or DecodeBlock(H, b)
      blocks[b] = bl
    end
    return bl
  end
  -- (only the blocks over the search box, as the cell search keeps to the box)
  local bc0, bc1 = math.max(0, math.floor((box[1] - 1) / K)), math.min(nx - 1, math.floor((box[2] - 1) / K))
  local br0, br1 = math.max(0, math.floor((box[3] - 1) / K)), math.min(ny - 1, math.floor((box[4] - 1) / K))
  local function Within(b) -- a block's cells only
    local r0, c0 = math.floor(b / nx) * K, (b % nx) * K
    return function(c, r, fc, fr)
      if c <= c0 or c > c0 + K or r <= r0 or r > r0 + K then return nil end
      return step(c, r, fc, fr)
    end
  end
  local bs, bg = BlockOf(c1, r1), BlockOf(c2, r2)
  if bs == bg then return nil, "cells" end
  -- the start's and the stop's walks to their blocks' ways through: straight over open ground,
  -- else searched over the block's cells
  local S, Gb = Block(bs), Block(bg)
  local function Reach(bl, b, c0, r0, back)
    local dist, lines = {}, {}
    for i = 1, bl.n do
      local cells, d = LineCells(Within(b), c0, r0, bl.c[i], bl.r[i])
      if not cells then return Spread(Within(b), c0, r0, back, pause) end
      local k = bl.r[i] * 65536 + bl.c[i]
      dist[k], lines[k] = d, cells
    end
    return dist, nil, lines
  end
  local sdist, scame, slines = Reach(S, bs, c1, r1, false)
  local gdist, gcame, glines = Reach(Gb, bg, c2, r2, true)
  local HF = danger and true or false -- (a step's cost factor about: the guards' reach, the zones too high)
  local WF = P.SwimCost() / P.SWIM_COST -- (swimming left out: the blocks' walks across water pay the rest)
  local function h(r, c) return math.sqrt((c - c2) ^ 2 + (r - r2) ^ 2) end
  local gs, came, closed, open = {}, {}, {}, {}
  for i = 1, S.n do
    local d = sdist[S.r[i] * 65536 + S.c[i]]
    if d then
      local k = bs * 4096 + i
      gs[k], came[k] = d, false
      Push(open, k, d + h(S.r[i], S.c[i]))
    end
  end
  if not next(gs) then return nil, "cells" end -- (walled in within its block: the cells decide)
  local reached = false
  for i = 1, Gb.n do
    if gdist[Gb.r[i] * 65536 + Gb.c[i]] then reached = true break end
  end
  if not reached then return nil, "cells" end
  local best, bestK
  local expanded = 0
  local DIRS = { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } }
  while #open > 0 do
    local top = Pop(open)
    local k = top[1]
    if best and top[2] >= best then break end
    if not closed[k] then
      closed[k] = true
      expanded = expanded + 1
      if expanded > P.PATH_MAX_EXPANSIONS then return nil, "none" end
      if pause then pause() end
      local b, i = math.floor(k / 4096), k % 4096
      local bl = Block(b)
      local r, c = bl.r[i], bl.c[i]
      local gk = gs[k]
      if b == bg then -- (the stop's block: on to the stop)
        local d = gdist[r * 65536 + c]
        if d and (not best or gk + d < best) then best, bestK = gk + d, k end
      end
      -- across the block to its other ways through (the other faction's guards: about)
      local n = bl.n
      for j = 1, n do
        local d = j ~= i and bl.cost[(i - 1) * n + j]
        if d then
          if HF then -- (five points along the way: their factors, the guards' reach and the zones too high)
            local cj, rj, extra = bl.c[j], bl.r[j], 0
            for q = 0, 4 do
              extra = extra + danger(math.floor(c + (cj - c) * q / 4 + 0.5), math.floor(r + (rj - r) * q / 4 + 0.5)) - 1
            end
            d = d * (1 + extra / 5)
          end
          if WF ~= 1 then -- (and the share of them in water, P.avoidSwim)
            local cj, rj, wet = bl.c[j], bl.r[j], 0
            for q = 0, 4 do
              if Cell(g, math.floor(r + (rj - r) * q / 4 + 0.5), math.floor(c + (cj - c) * q / 4 + 0.5)) == 1 then wet = wet + 1 end
            end
            d = d * (1 + wet / 5 * (WF - 1))
          end
          local kj = b * 4096 + j
          local ng = gk + d
          if not closed[kj] and (gs[kj] == nil or ng < gs[kj]) then
            gs[kj], came[kj] = ng, k
            Push(open, kj, ng + h(bl.r[j], bl.c[j]))
          end
        end
      end
      -- over the border to the neighbor's way through beside it
      for _, o in ipairs(DIRS) do
        local nc, nr = c + o[1], r + o[2]
        if nc >= 1 and nc <= g.w and nr >= 1 and nr <= g.h then
          local nb = BlockOf(nc, nr)
          local nbr, nbc = math.floor(nb / nx), nb % nx
          if nb ~= b and nbc >= bc0 and nbc <= bc1 and nbr >= br0 and nbr <= br1 then
            local m = step(nc, nr, c, r)
            local j = m and Block(nb).at[((nr - 1) % K) * K + (nc - 1) % K]
            if j then
              local kj = nb * 4096 + j
              local ng = gk + m
              if not closed[kj] and (gs[kj] == nil or ng < gs[kj]) then
                gs[kj], came[kj] = ng, k
                Push(open, kj, ng + h(nr, nc))
              end
            end
          end
        end
      end
    end
  end
  if not best then return nil, "none" end
  -- the ways through, in order, then their cells
  local chain, k = {}, bestK
  while k do
    table.insert(chain, 1, k)
    k = came[k]
  end
  local cells = {}
  local function At(key) local bl = Block(math.floor(key / 4096)) local i = key % 4096 return bl.c[i], bl.r[i] end
  local fc, fr = At(chain[1])
  if slines then
    for _, cell in ipairs(slines[fr * 65536 + fc]) do cells[#cells + 1] = cell end
  else
    local seq, cur = {}, fr * 65536 + fc
    while cur do
      table.insert(seq, 1, cur)
      cur = scame[cur]
    end
    for _, n in ipairs(seq) do cells[#cells + 1] = { n % 65536, math.floor(n / 65536) } end
  end
  for q = 2, #chain do
    local ac, ar = At(chain[q - 1])
    local bc, br = At(chain[q])
    if math.floor(chain[q - 1] / 4096) == math.floor(chain[q] / 4096) then
      local within = Within(math.floor(chain[q] / 4096))
      local path = LineCells(within, ac, ar, bc, br) or CellPath(within, ac, ar, bc, br, pause)
      if not path then return nil, "cells" end
      for m = 2, #path do cells[#cells + 1] = path[m] end
    else
      cells[#cells + 1] = { bc, br }
    end
  end
  local lc, lr = At(chain[#chain])
  if glines then
    local line = glines[lr * 65536 + lc] -- (from the stop: walked backward)
    for m = #line - 1, 1, -1 do cells[#cells + 1] = line[m] end
  else
    local cur = gcame[lr * 65536 + lc]
    while cur do
      cells[#cells + 1] = { cur % 65536, math.floor(cur / 65536) }
      cur = gcame[cur]
    end
  end
  return cells
end

-- Walkable path from (x1, y1) to (x2, y2) over the grid (8-connected A*, by blocks when far,
-- then straightened with line of sight): cost, { x1, y1, ..., x2, y2 }; nil when there is
-- none nearby. `road1`/`road2`: that end is a road's point (a walk onto or off the roads), which keeps END_SLACK
-- even in blocked ground: the road is walkable along its line, not the slope round it (Ironforge's gate road on its
-- mountain shelf, all blocked cells: STOP_SLACK took a walk up the cliff from Misty Pine Refuge, 2026-10-08).
local function Search(cont, x1, y1, x2, y2, road1, road2, priceRed)
  EnsureWalls()
  local g = ns.Terrain and ns.Terrain[cont]
  if not g then return nil end
  local c1, r1 = ToCell(g, x1, y1)
  local c2, r2 = ToCell(g, x2, y2)
  local pad = P.PATH_PAD
  local cmin, cmax = math.min(c1, c2) - pad, math.max(c1, c2) + pad
  local rmin, rmax = math.min(r1, r2) - pad, math.max(r1, r2) + pad
  if (cmax - cmin + 1) * (rmax - rmin + 1) > P.PATH_MAX_CELLS then return nil end
  local function slack(yd) -- (squared cells; a city's none means none: its walls are real)
    if g.slack and yd <= 0 then return -1 end
    return (yd / g.cell + 1) ^ 2
  end
  local function yards(inside, far)
    if g.slack then return inside and math.max(g.slack, P.CITY_INSIDE_SLACK) or g.slack end
    return inside and far or P.END_SLACK
  end
  local slack1 = slack(yards(Cell(g, r1, c1) == 2 and not road1, P.START_SLACK))
  local slack2 = slack(yards(Cell(g, r2, c2) == 2 and not road2, P.STOP_SLACK))
  local hasOverlay = ns.CityHalls and ns.CityHalls[cont] and true
  -- (the other faction's guards: their reach costs Router.HOSTILE_FACTOR a step)
  local Rt = ns.Router
  local side = Rt and Rt.HostileSide and Rt.HostileSide()
  local hostileCell = {} -- (by row: Row)
  local function hostile(c, r)
    if not side then return false end
    local row = Row(hostileCell, r)
    local h = row[c]
    if h == nil then
      local hx, hy = CellCentre(g, c, r)
      h = Rt.HostileAt(cont, hx, hy, side)
      row[c] = h
    end
    return h
  end
  -- (priceRed: the zones too high for the player, Router.RedZones, cost Router.LEVEL_FACTOR a step, as the Router
  -- prices a leg there; not the zones the walk starts and ends in. P.FindPath, below)
  local red = priceRed and Rt and Rt.RedZones and not g.slack and Rt.RedZones() or nil
  local redExempt = red and { [Rt.ZoneAt(cont, x1, y1)] = true, [Rt.ZoneAt(cont, x2, y2)] = true }
  local redCell = {} -- (by row: Row)
  local function inRed(c, r)
    if not red then return false end
    local row = Row(redCell, r)
    local v = row[c]
    if v == nil then
      local cx, cy = CellCentre(g, c, r)
      local z = Rt.ZoneAt(cont, cx, cy)
      v = (red[z] and not redExempt[z]) and true or false
      row[c] = v
    end
    return v
  end
  local LF = Rt and Rt.LEVEL_FACTOR or 1
  local function danger(c, r) -- (a step's cost factor there)
    if hostile(c, r) then return Rt.HOSTILE_FACTOR end
    if inRed(c, r) then return LF end
    return 1
  end
  local wc = wallCells[g]
  -- (a building's cells: crossed near an end only when that end is in a building itself, as SegmentCost)
  local bset = Buildings(g)
  local inB1 = bset[r1 * 65536 + c1] and Cell(g, r1, c1) == 2
  local inB2 = bset[r2 * 65536 + c2] and Cell(g, r2, c2) == 2
  local swimCost = P.SwimCost()
  local function cost0(c, r)
    if wc and wc[r * 65536 + c] then return nil end -- (a wall: not even near the ends)
    local v = Cell(g, r, c)
    if g.overlay and v == 1 then return nil end -- (an overlay grid: not its own there)
    if hasOverlay then -- (the continent's grid: a ruins' own grid over it where it has one)
      -- (not a cave's: its tunnels are narrower than these cells, and its roads lead through
      -- it; a cell's middle on its floor would open a hillside's blocked cell)
      local cx, cy = CellCentre(g, c, r)
      local ov, o = OverlayRaw(cont, cx, cy, true)
      if ov and not o.cave then
        if ov == 2 then return nil end -- (a city's ruins: its walls and banks are real, no end slack; as SegmentCost)
        v = ov
      end
    end
    if v == 2 then
      local b = bset[r * 65536 + c]
      local near1 = (c - c1) ^ 2 + (r - r1) ^ 2 <= slack1 and (not b or inB1)
      local near2 = (c - c2) ^ 2 + (r - r2) ^ 2 <= slack2 and (not b or inB2)
      if not near1 and not near2 then return nil end
      return 1
    end
    return v == 1 and swimCost or 1
  end
  -- (up or down a cliff (CliffAlong): no step between two cells whose ground differs more than CLIFF_SLOPE allows,
  -- either way, as round the cliff walls; but out of the start's cell or into the stop's by a fall-free drop: the
  -- player's there. Kooki3z 2026-11-20, Freewind Post: "not a safe path down")
  local cliffs = not g.slack and ns.Ground and ns.Ground.At and true
  local rise, drop = P.CLIFF_SLOPE * g.cell, DropMax()
  local function steep(c, r, fc, fr)
    local a = CellZ(cont, g, fc, fr)
    local b = a and CellZ(cont, g, c, r)
    if not b then return false end
    local dz = math.abs(b - a)
    if dz <= ((c ~= fc and r ~= fr) and rise * SQ2 or rise) then return false end
    -- (the fall-free drop out of the start's cell or into the stop's only where the player is: not at a road's end. A
    -- walk between two road pieces near Thousand Needles' Great Lift dropped 12 yd off a cliff at each end, and with
    -- Road tolerance +3 the route took it, 2026-11-23)
    return not (dz <= drop and ((fc == c1 and fr == r1 and not road1) or (c == c2 and r == r2 and not road2)))
  end
  local memo = {} -- (by row: Row)
  -- step multiplier into (c, r) (from (fc, fr), when it's a move: the cliffs), or nil where it can't go
  local function step(c, r, fc, fr)
    local row = Row(memo, r)
    local m = row[c]
    if m == nil then
      m = cost0(c, r) or false
      if m then -- (the guards' reach times its factor; a zone too high LEVEL_FACTOR - 1 more a yard, as the Router
        -- adds it to a leg's cost: water there at the swim cost and that, not their product)
        if hostile(c, r) then m = m * Rt.HOSTILE_FACTOR elseif inRed(c, r) then m = m + LF - 1 end
      end
      row[c] = m
    end
    if m and fc and cliffs and steep(c, r, fc, fr) then return nil end
    return m or nil
  end
  -- Run as a background job (a coroutine, see Router.Pump): hand control back every so
  -- often so no single frame pays for the whole search.
  local co, isMain = coroutine.running()
  local canYield = co ~= nil and not isMain
  local count = 0
  local pause = canYield and function()
    count = count + 1
    if count % P.PATH_YIELD_EVERY == 0 or SliceOver() then coroutine.yield() end
  end or nil
  local overPause = canYield and function() -- (by the clock alone: ShutIn's few hundred cells)
    if SliceOver() then coroutine.yield() end
  end or nil
  local cells, how
  local H = ns.TerrainHPA and ns.TerrainHPA[cont]
  if H and not g.slack and H.w == g.w and H.h == g.h
      and (math.abs(c1 - c2) >= P.HPA_MIN_CELLS or math.abs(r1 - r2) >= P.HPA_MIN_CELLS) then
    cells, how = ByBlocks(g, H, cont, c1, r1, c2, r2, step, { cmin, cmax, rmin, rmax }, (side or red) and danger or nil,
      pause)
    if how == "none" then return nil end
  end
  if not cells then
    local function inBox(c, r, fc, fr)
      if c < cmin or c > cmax or r < rmin or r > rmax then return nil end
      return step(c, r, fc, fr)
    end
    if ShutIn(inBox, c1, r1, c2, r2, P.SHUT_IN_CELLS, overPause) then return nil end
    cells = CellPath(inBox, c1, r1, c2, r2, pause, P.PATH_MAX_EXPANSIONS)
    if not cells then return nil end
  end
  local pts = {}
  for i, n in ipairs(cells) do
    local x, y = CellCentre(g, n[1], n[2])
    if i == 1 then x, y = x1, y1 elseif i == #cells then x, y = x2, y2 end
    pts[#pts + 1] = { x, y }
  end
  -- straighten: from each kept point, go as far along the path as is still in sight (and
  -- not back into the other faction's guards' reach where the path went round it)
  -- (the path's yards in their reach so far, from its start: a shortcut may not add any)
  local hostileSoFar = { 0 }
  -- (and the zones too high: a shortcut priced as the path was, its yards in them at LEVEL_FACTOR, no dearer than the
  -- path between; forbidding any yard more there kept walks hugging a zone's border the cells' middles judge it by)
  local redSoFar, lenSoFar = red and { 0 } or nil, red and { 0 } or nil
  -- (swimming left out, P.avoidSwim: nor across water the path went round. Else straightened both ways, the cheaper
  -- kept at the swim cost: checked only for being open, a shortcut swam straight across a pond the walk went round,
  -- 2026-11-19 south of Tarren Mill; kept from the water the path went round, a walk across a lake hugged the path's
  -- stairs over the water where the open line was cheaper)
  local wetSoFar = swimCost > 1 and { 0 } or nil
  for k = 2, #pts do
    local inside = hostile(cells[k][1], cells[k][2])
    local d = math.sqrt((pts[k][1] - pts[k - 1][1]) ^ 2 + (pts[k][2] - pts[k - 1][2]) ^ 2)
    hostileSoFar[k] = hostileSoFar[k - 1] + (inside and d or 0)
    if redSoFar then
      redSoFar[k] = redSoFar[k - 1] + (inRed(cells[k][1], cells[k][2]) and d or 0)
      lenSoFar[k] = lenSoFar[k - 1] + d
    end
    if wetSoFar then wetSoFar[k] = wetSoFar[k - 1] + (Cell(g, cells[k][2], cells[k][1]) == 1 and d or 0) end
  end
  local keepDry
  local function shortcut(i, j)
    local sc = P.SegmentCost(cont, pts[i][1], pts[i][2], pts[j][1], pts[j][2], 0)
    if not sc then return false end
    if keepDry then
      local len = math.sqrt((pts[j][1] - pts[i][1]) ^ 2 + (pts[j][2] - pts[i][2]) ^ 2)
      if (sc - len) / (swimCost - 1) > wetSoFar[j] - wetSoFar[i] + g.cell then return false end
    end
    if side then
      local h = Rt.HostileYards(cont, pts[i][1], pts[i][2], pts[j][1], pts[j][2], side)
      if h > hostileSoFar[j] - hostileSoFar[i] + g.cell then return false end
    end
    if redSoFar then
      local yd = 0
      for z, v in pairs(Rt.ZoneYards(cont, pts[i][1], pts[i][2], pts[j][1], pts[j][2])) do
        if red[z] and not redExempt[z] then yd = yd + v end
      end
      if yd > 0 and sc + yd * (LF - 1) > lenSoFar[j] - lenSoFar[i] + (redSoFar[j] - redSoFar[i]) * (LF - 1) + g.cell then
        return false
      end
    end
    return true
  end
  local checks = 0
  local function straighten()
    local out, total, i = { x1, y1 }, 0, 1
    local function sees(j)
      checks = checks + 1
      if canYield and (checks % 6 == 0 or SliceOver()) then coroutine.yield() end
      return shortcut(i, j)
    end
    while i < #pts do
      -- the farthest point still in sight: jumping ahead twice as far each time, then halving
      -- back between the last one seen and the first one not (a line check each, not one per point)
      local j, far, jump = i + 1, nil, 1
      while j < #pts do
        local k = math.min(#pts, j + jump)
        if sees(k) then
          j, jump = k, jump * 2
        else
          far = k
          break
        end
      end
      while far and far - j > 1 do
        local mid = math.floor((j + far) / 2)
        if sees(mid) then j = mid else far = mid end
      end
      local a, b = pts[i], pts[j]
      total = total + (P.SegmentCost(cont, a[1], a[2], b[1], b[2]) or math.sqrt((b[1] - a[1]) ^ 2 + (b[2] - a[2]) ^ 2))
      out[#out + 1], out[#out + 2] = b[1], b[2]
      i = j
    end
    return total, out
  end
  keepDry = P.avoidSwim and wetSoFar ~= nil
  local total, out = straighten()
  -- (the water the path went round kept to, when cutting it was dearer)
  local function Yards(o)
    local yd = 0
    for k = 1, #o - 3, 2 do yd = yd + math.sqrt((o[k + 2] - o[k]) ^ 2 + (o[k + 3] - o[k + 1]) ^ 2) end
    return yd
  end
  -- (only when the straightened walk swims, and kept to only when that swims KEEP_DRY_MIN_YD less: a few yards of a
  -- stream is no way round, and a walk reshaped for them reached Bloodhoof's Hunter trainer over the tent's roof)
  local wet = wetSoFar and not keepDry and (total - Yards(out)) / (swimCost - 1) or 0
  if wet >= P.KEEP_DRY_MIN_YD then
    keepDry = true
    local t2, o2 = straighten()
    if t2 < total and wet - (t2 - Yards(o2)) / (swimCost - 1) >= P.KEEP_DRY_MIN_YD then total, out = t2, o2 end
  end
  return total, out
end

-- A walk over the grid from (x1, y1) to (x2, y2): its cost (yards, water at the swim cost) and its points, or nil.
-- Searched by yards; when that walk goes P.RED_SEARCH_YD or more through zones too high for the player (not its ends'
-- zones), searched again with them priced (Router.LEVEL_FACTOR a yard, as the Router prices a leg there), and the
-- cheaper of the two by that pricing kept. The Router weighs the one walk it's given: 1.3.14's grid opened Silverpine's
-- hills into Alterac, and a level 20 walk to Light's Hope took 2k yd of it, 800 yd shorter and 556 s slower than the way
-- by Tirisfal. (Priced always, walks crossing a zone they can't avoid wandered along its border: the zones' 33 yd grid.)
P.RED_SEARCH_YD = 100
function P.FindPath(cont, x1, y1, x2, y2, road1, road2)
  local c, path = Search(cont, x1, y1, x2, y2, road1, road2, false)
  if c == nil then return nil end -- (one value, as before: callers count them)
  local Rt = ns.Router
  local g = ns.Terrain and ns.Terrain[cont]
  local red = c and path and g and not g.slack and Rt and Rt.RedZones and Rt.RedZones()
  if not red then return c, path end
  local exempt = { [Rt.ZoneAt(cont, x1, y1)] = true, [Rt.ZoneAt(cont, x2, y2)] = true }
  local function RedYards(pts)
    local yd = 0
    for i = 1, #pts - 3, 2 do
      for z, v in pairs(Rt.ZoneYards(cont, pts[i], pts[i + 1], pts[i + 2], pts[i + 3])) do
        if red[z] and not exempt[z] then yd = yd + v end
      end
    end
    return yd
  end
  local ry = RedYards(path)
  if ry < P.RED_SEARCH_YD then return c, path end
  local c2, path2 = Search(cont, x1, y1, x2, y2, road1, road2, true)
  if not (c2 and path2) then return c, path end
  local LF = Rt.LEVEL_FACTOR or 1
  if c2 + RedYards(path2) * (LF - 1) < c + ry * (LF - 1) then return c2, path2 end
  return c, path
end

function P.ClearCache()
  cache, ovIndex, hpaBlocks = {}, {}, {}
  wetMemo, wetMemoN = {}, 0
  P.ClearCliffMemo()
  if P.ClearSegMemo then P.ClearSegMemo() end
end

-- Whether (x, y) is hilly ground (Data/Terrain.lua's ns.Hills: open, but a climb): a route
-- winding there may be taking the slope the easy way.
function P.Hilly(cont, x, y)
  local g = ns.Hills and ns.Hills[cont]
  if not g then return false end
  local c, r = ToCell(g, x, y)
  if r < 1 or r > g.h or c < 1 or c > g.w then return false end
  return Cell(g, r, c) == 1
end

-- Whether the path (flat points, from index i to j) or the straight line between its ends
-- is on hilly ground anywhere (checked every `step` yards).
function P.HillyAlong(cont, pts, i, j, step)
  if not (ns.Hills and ns.Hills[cont]) then return false end
  step = step or 10
  local function line(x1, y1, x2, y2)
    local n = math.max(1, math.ceil(math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2) / step))
    for k = 0, n do
      if P.Hilly(cont, x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n) then return true end
    end
    return false
  end
  for m = i, j - 1 do
    if line(pts[2 * m - 1], pts[2 * m], pts[2 * m + 1], pts[2 * m + 2]) then return true end
  end
  return line(pts[2 * i - 1], pts[2 * i], pts[2 * j - 1], pts[2 * j])
end

-- Whether (x, y) is open ground on `cont`'s grid (false without a grid).
function P.IsOpen(cont, x, y)
  EnsureWalls()
  local ov = Overlay(cont, x, y)
  if ov then return ov == 0 end
  local g = ns.Terrain and ns.Terrain[cont]
  if not g then return false end
  local c, r = ToCell(g, x, y)
  local v = Cell(g, r, c)
  if g.overlay then return v == 0 end -- (an overlay's own: 1 is the continent's, not it)
  return v ~= 2
end

-- Decode the terrain rows within `yd` of (x, y) ahead of time (Router.WarmUp, run as a
-- background job: it pauses every few rows).
function P.WarmRows(cont, x, y, yd)
  local g = ns.Terrain and ns.Terrain[cont]
  if not g then return end
  local _, r1 = ToCell(g, x - yd, y - yd)
  local _, r2 = ToCell(g, x + yd, y + yd)
  local rc = cache[g]
  if not rc then
    rc = {}
    cache[g] = rc
  end
  local co, main = coroutine.running()
  local canYield = co ~= nil and not main
  local n = 0
  for row = math.max(1, math.min(r1, r2)), math.min(g.h, math.max(r1, r2)) do
    if not rc[row] and Rows(g)[row] then
      rc[row] = DecodeRow(Rows(g)[row], g.short, g.long, g.deep)
      n = n + 1
      if canYield and (n % 6 == 0 or SliceOver()) then coroutine.yield() end
    end
  end
end
