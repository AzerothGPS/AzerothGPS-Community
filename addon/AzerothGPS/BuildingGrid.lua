-- Walks inside the open world's buildings on their own walk grids (1.4.2, item 119; being tested: Options > Routing
-- "Building routing: new (test)", in BG.TOWNS only).
--
-- The grids (each world grid region folder's Buildings.lua, `agps building-grid`, buildinggrid.py): the capitals' city
-- grid recipe over each building model's own navigation mesh, in the model's own frame (2 yd cells), one grid shared by
-- the placements of a model that sit alike. Stored in the world grid's encoding (run-length coded, the links implied by
-- the heights); decoded once a building is first used into the city grid's surface layout (CityGrid.lua's: a character
-- a cell, 7 a surface), so CityGrid.lua's search, string-pulling and stairs work on it unchanged, read in place.
--
-- Routing (WorldGrid.lua's WG.Leg, the open world's legs): a leg ending inside a building (a stop on one of its floors)
-- walks the world grid to the building's door and its grid from there; one starting inside the same the other way; both
-- in one building: its grid only. The door is the grid's own choice: every door step of the building a start of one
-- search (its yards from the leg's other end added), the best one kept. Anything the building's grid can't do: nil, the
-- older indoor roads (WG.BuildingLeg, Data/Indoors.lua) as before.
local _, ns = ...
local BG = {}
ns.BuildingGrid = BG

local floor, sqrt, abs, max, min, rad, cos, sin = math.floor, math.sqrt, math.abs, math.max, math.min, math.rad,
  math.cos, math.sin
local byte, char, sub = string.byte, string.char, string.sub

BG.F_DOOR, BG.F_REACH = 1, 4 -- (a surface's flags: a door's step, the land's; a floor only an NPC's spot reaches)
BG.DOOR_FACTOR = 1 -- a yard from the leg's other end to a door costs this many in the door's choice
BG.TILE = 533.3333333
BG.CACHE = 16 -- walks kept
-- The towns the test option routes in (item 119's rollout, step 7): { name, x0, y0, x1, y1 } per continent, world yards.
BG.TOWNS = {
  [0] = {
    { "Brill", 2080, 120, 2400, 420 },
    { "Goldshire", -9560, -80, -9360, 160 },
    { "Kharanos", -5700, -620, -5500, -400 },
    { "Sentinel Hill", -10640, 920, -10380, 1180 },
    { "Booty Bay", -14560, 300, -14240, 640 },
    { "Lakeshire", -9360, -2300, -9100, -2000 },
    { "Darkshire", -10700, -1300, -10400, -1000 },
  },
  [1] = {
    { "Theramore", -3900, -4600, -3550, -4250 },
    { "The Crossroads", -560, -2780, -300, -2520 },
    { "Astranaar", 2640, -560, 2880, -300 },
  },
}

local function Dist(x1, y1, x2, y2) return sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2) end
local function R() return ns.Router end

function BG.On()
  local s = ns.settings and ns.settings.gps
  if not (s and s.buildingGrid ~= false) then return false end
  local WG = ns.WorldGrid
  return WG ~= nil and WG.On ~= nil and WG.On() and ns.CityGrid ~= nil
end

function BG.InTown(cont, x, y)
  for _, t in ipairs(BG.TOWNS[cont] or {}) do
    if x >= t[2] and x <= t[4] and y >= t[3] and y <= t[5] then return t[1] end
  end
  return nil
end

---------------------------------------------------------------------------------------------------- frames
-- A placement's frame: its origin, turned by its yaw + 180 degrees (walknet.Placed's, buildinggrid.frame_turn).
local function ToFrame(p, x, y)
  local dx, dy = x - p.x, y - p.y
  return dx * p.c + dy * p.s, -dx * p.s + dy * p.c
end
local function ToWorld(p, lx, ly)
  return p.x + lx * p.c - ly * p.s, p.y + lx * p.s + ly * p.c
end
BG.ToFrame, BG.ToWorld = ToFrame, ToWorld

---------------------------------------------------------------------------------------------------- the data
-- (the data's characters, citygrid.ALPHA; worldbake's repeat and escape)
local ALPHA = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
local DEC = {}
for i = 1, #ALPHA do DEC[byte(ALPHA, i)] = i - 1 end
local REP, ZESC = byte("."), 62
local DX = { 1, 0, -1, 0, 1, -1, -1, 1 }
local DY = { 0, 1, 0, -1, 1, 1, -1, -1 }
BG.BLOCK = 32

-- A part's tokens (worldbake._rle undone), each `width(part, i)` characters: a list of strings.
local function Tokens(part, width)
  local out, i, n = {}, 1, #part
  while i <= n do
    if byte(part, i) == REP then
      local last = out[#out]
      for _ = 1, DEC[byte(part, i + 1)] + 2 do out[#out + 1] = last end
      i = i + 2
    else
      local w = width(part, i)
      out[#out + 1] = sub(part, i, i + w - 1)
      i = i + w
    end
  end
  return out
end

-- A variant's grid (its string: "x0,y0,w,h|counts|recs|zs|links", buildinggrid.encode) in the city grid's layout:
-- { x0, y0, w, h, cell, zmin, zq, offs, block, n, cells, s, base, flags (a character a surface: its flags) }.
function BG.Decode(str, cell, zq, z0, implied)
  local head, counts, recs, zs, lks = str:match("^([^|]*)|([^|]*)|([^|]*)|([^|]*)|([^|]*)$")
  if not head then return nil end
  local x0, y0, w, h = head:match("^(-?%d+),(-?%d+),(%d+),(%d+)$")
  x0, y0, w, h = tonumber(x0), tonumber(y0), tonumber(w), tonumber(h)
  local cnt = Tokens(counts, function() return 1 end)
  if #cnt ~= w * h then return nil end
  local rec = Tokens(recs, function() return 2 end)
  local zt = Tokens(zs, function(p, i) return DEC[byte(p, i)] == ZESC and 4 or 1 end)
  local lt = Tokens(lks, function(p, i) return byte(p, i) == 49 and 5 or 1 end) -- ("1": 4 characters after)
  -- (the heights, cell by cell: each against its prediction)
  local zof, pos, last, vmin = {}, 1, nil, math.huge
  local cn = {}
  for a = 0, w - 1 do
    local prev = nil
    for b = 0, h - 1 do
      local ci = a * h + b
      local n = DEC[byte(cnt[ci + 1])]
      cn[ci] = n
      if n == 0 then
        prev = nil
      else
        local cz = {}
        for k = 1, n do
          local t = zt[pos + k - 1]
          local v
          if DEC[byte(t, 1)] == ZESC then
            v = DEC[byte(t, 2)] * 4096 + DEC[byte(t, 3)] * 64 + DEC[byte(t, 4)]
          else
            local pred = (prev and (prev[k] or prev[#prev])) or last
            v = pred + DEC[byte(t, 1)] - 31
          end
          last = v
          cz[k] = v
          if v < vmin then vmin = v end
        end
        zof[ci] = cz
        prev = cz
        pos = pos + n
      end
    end
  end
  -- (the surfaces in the city grid's layout: z (2), point (1), links (4: two directions a character))
  local s, fl, cells, base = {}, {}, {}, {}
  local q, nS = 0, 0
  for a = 0, w - 1 do
    for b = 0, h - 1 do
      local ci = a * h + b
      if ci % BG.BLOCK == 0 then base[#base + 1] = nS end
      local n = cn[ci]
      cells[#cells + 1] = sub(ALPHA, n + 1, n + 1)
      for k = 1, n do
        q = q + 1
        local r = rec[q]
        local v = zof[ci][k]
        -- (the links the heights imply, as the bake's: per direction the neighbor's surface nearest in height)
        local im = {}
        for d = 1, 8 do
          local na, nb = a + DX[d], b + DY[d]
          local nz = (na >= 0 and nb >= 0 and na < w and nb < h) and zof[na * h + nb] or nil
          local best, bk = nil, 0
          if nz then
            for kk = 1, #nz do
              local dz = abs(nz[kk] - v)
              if not best or dz < best then best, bk = dz, kk end
            end
          end
          im[d] = (best and best <= implied) and bk or 0
        end
        local L = lt[q]
        local links = im
        if L ~= "0" then
          links = {}
          for m = 1, 4 do
            local x = DEC[byte(L, m + 1)]
            local d1, d2 = 2 * m - 1, 2 * m
            links[d1] = (im[d1] + floor(x / 8)) % 8
            links[d2] = (im[d2] + x % 8) % 8
          end
        end
        local zv = v - vmin
        nS = nS + 1
        s[nS] = sub(ALPHA, floor(zv / 64) + 1, floor(zv / 64) + 1) .. sub(ALPHA, zv % 64 + 1, zv % 64 + 1)
          .. sub(r, 2, 2)
          .. sub(ALPHA, links[1] * 8 + links[2] + 1, links[1] * 8 + links[2] + 1)
          .. sub(ALPHA, links[3] * 8 + links[4] + 1, links[3] * 8 + links[4] + 1)
          .. sub(ALPHA, links[5] * 8 + links[6] + 1, links[5] * 8 + links[6] + 1)
          .. sub(ALPHA, links[7] * 8 + links[8] + 1, links[7] * 8 + links[8] + 1)
        fl[nS] = sub(r, 1, 1)
      end
    end
  end
  return { x0 = x0, y0 = y0, w = w, h = h, cell = cell, zmin = z0 + vmin * zq, zq = zq, offs = 8, block = BG.BLOCK,
    n = nS, cells = table.concat(cells), s = table.concat(s), base = base, flags = table.concat(fl) }
end

-- The region's buildings (its folder's Buildings.lua, loaded with it: WorldGrid.lua's WG.LoadRegion): { e (the data),
-- places = { { v, x, y, z, yaw, c, s, ... } } }, or false.
BG.regions = {}
function BG.Region(cont, rx, ry, noLoad)
  local key = cont .. ":" .. rx .. ":" .. ry
  local got = BG.regions[key]
  if got ~= nil then return got end
  local WG = ns.WorldGrid
  local wc = WG and WG.Cont and WG.Cont(cont)
  if wc and WG.LoadRegion and not noLoad then WG.LoadRegion(wc, rx, ry) end
  local all = rawget(_G, "AzerothGPS_BuildingGrids")
  local e = type(all) == "table" and all[key] or nil
  if type(e) ~= "table" or type(e.m) ~= "table" or type(e.p) ~= "string" then
    -- (not loaded yet, in a region the world grid hasn't: none for now; asked again next time)
    if e == nil then return false end
    BG.regions[key] = false
    return false
  end
  local reg = { e = e, places = {}, grids = {} }
  for item in e.p:gmatch("[^;]+") do
    local v, x, y, z, yaw = item:match("^(%d+),([^,]+),([^,]+),([^,]+),([^,]+)$")
    v = tonumber(v)
    local str = v and e.m[v]
    if str then
      local hx, hy, hw, hh = str:match("^(-?%d+),(-?%d+),(%d+),(%d+)|")
      local t = rad(tonumber(yaw) + 180)
      reg.places[#reg.places + 1] = { v = v, x = tonumber(x), y = tonumber(y), z = tonumber(z), yaw = tonumber(yaw),
        c = cos(t), s = sin(t), bx0 = tonumber(hx), by0 = tonumber(hy), bx1 = tonumber(hx) + tonumber(hw) * e.cell,
        by1 = tonumber(hy) + tonumber(hh) * e.cell, cont = cont, key = key, i = #reg.places + 1 }
    end
  end
  BG.regions[key] = reg
  return reg
end

local function RegionAt(cont, x, y)
  local WG = ns.WorldGrid
  local wc = WG and WG.Cont and WG.Cont(cont)
  local rb = wc and wc.rb or 8
  local tx, ty = floor(32 - y / BG.TILE), floor(32 - x / BG.TILE)
  return floor(tx / rb), floor(ty / rb)
end
BG.RegionAt = RegionAt

-- A placement's grid: the city grid's `c` (CityGrid.lua reads it as one of its cities'), in the placement's frame, its
-- heights the frame's (the placement's z less).
function BG.Grid(p)
  if p.grid then return p.grid end
  local reg = BG.regions[p.key]
  if not reg then return nil end
  local d = reg.grids[p.v]
  if d == nil then
    local e = reg.e
    d = BG.Decode(e.m[p.v], e.cell, e.zq, e.z0, e.implied or 8) or false
    reg.grids[p.v] = d
  end
  if not d then return nil end
  local c = { name = "bld:" .. p.key .. ":" .. p.i, d = {}, cont = p.cont, lv = -1, cell = d.cell, x0 = d.x0, y0 = d.y0,
    w = d.w, h = d.h, zmin = d.zmin, zq = d.zq, offs = d.offs, block = d.block, n = d.n, cells = d.cells, s = d.s,
    base = d.base, flags = d.flags, links = {}, out = {}, first = {}, firstN = 0, nBaked = 0, place = p, building = true }
  c.xmax, c.ymax = c.x0 + c.w * c.cell, c.y0 + c.h * c.cell
  p.grid = c
  return c
end

local function Flags(c, s) return DEC[byte(c.flags, s + 1)] end
BG.Flags = Flags

-- The building whose grid has a floor at (x, y) at height z (within CityGrid's FLOOR_Z; z nil: `indoors`, the game's
-- IsIndoors at the player's spot, and any floor there): the placement and its grid, or nil. Only in the test's towns.
function BG.At(cont, x, y, z, indoors)
  if not BG.On() or not BG.InTown(cont, x, y) then return nil end
  if z == nil and not indoors then return nil end
  local CG = ns.CityGrid
  local reg = BG.Region(cont, RegionAt(cont, x, y))
  if not reg then return nil end
  local best, bc, bd
  for _, p in ipairs(reg.places) do
    local lx, ly = ToFrame(p, x, y)
    if lx >= p.bx0 and ly >= p.by0 and lx < p.bx1 and ly < p.by1 then
      local c = BG.Grid(p)
      local ci = c and CG.CellAt(c, lx, ly)
      if ci then
        local f = CG.First(c, ci)
        for k = 0, CG.Count(c, ci) - 1 do
          local s = f + k
          if Flags(c, s) % 2 == 0 then -- (a floor of the building's, not a door's step)
            local dz = z and abs(CG.Z(c, s) + p.z - z) or 0
            if dz <= CG.FLOOR_Z and (not bd or dz < bd) then best, bc, bd = p, c, dz end
          end
        end
      end
    end
  end
  return best, bc
end

-- The placement whose grid has a cell with floors at (x, y), and its grid, its cell (frame), never loading a region
-- (the floor tracker's and the floor picker's: `noLoad`), else nil. `keep`: the placement followed, kept while its box
-- has the spot.
function BG.Under(cont, x, y, keep, noLoad)
  if not BG.On() or not BG.InTown(cont, x, y) then return nil end
  local CG = ns.CityGrid
  local function Try(p)
    local lx, ly = ToFrame(p, x, y)
    if not (lx >= p.bx0 and ly >= p.by0 and lx < p.bx1 and ly < p.by1) then return nil end
    local c = BG.Grid(p)
    local ci = c and CG.CellAt(c, lx, ly)
    if not ci or CG.Count(c, ci) == 0 then return nil end
    local f = CG.First(c, ci)
    for k = 0, CG.Count(c, ci) - 1 do
      if Flags(c, f + k) % 2 == 0 then return c, ci, lx, ly end
    end
    return nil
  end
  if keep then
    local c, ci, lx, ly = Try(keep)
    if c then return keep, c, ci, lx, ly end
  end
  local rx, ry = RegionAt(cont, x, y)
  local reg = BG.Region(cont, rx, ry, noLoad)
  if not reg then return nil end
  for _, p in ipairs(reg.places) do
    local c, ci, lx, ly = Try(p)
    if c then return p, c, ci, lx, ly end
  end
  return nil
end

-- The floors' heights (world) of the building under (x, y): the floor picker's (MapExtras.lua's MX.GridHeights), its
-- cell size; nil where none.
function BG.HeightsAt(cont, x, y)
  local p, c, ci = BG.Under(cont, x, y, nil, true)
  if not p then return nil end
  local CG = ns.CityGrid
  local out, f = {}, CG.First(c, ci)
  for k = 0, CG.Count(c, ci) - 1 do
    if Flags(c, f + k) % 2 == 0 then out[#out + 1] = CG.Z(c, f + k) + p.z end
  end
  return out, c.cell
end

-- An NPC's floor (its spawn at x, y, z) in the building grid under it: the floor's height (world) within NPC_Z of the
-- spawn's, else nil. Its NPCs are floor markers (HeightBand.lua's across rule, item 120b). Loads its region (in the
-- test's towns only: the player there, naming the NPC).
BG.NPC_Z = 2.5
function BG.NpcFloor(cont, x, y, z)
  if not z then return nil end
  local p, c, ci = BG.Under(cont, x, y)
  if not p then return nil end
  local CG = ns.CityGrid
  local best, bd
  local f = CG.First(c, ci)
  for k = 0, CG.Count(c, ci) - 1 do
    if Flags(c, f + k) % 2 == 0 then
      local fz = CG.Z(c, f + k) + p.z
      local d = abs(fz - z)
      if d <= BG.NPC_Z and (not bd or d < bd) then best, bd = fz, d end
    end
  end
  return best
end

---------------------------------------------------------------------------------------------------- walks
-- A frame route (CityGrid's walk on a placement's grid) in the world: its points turned, its heights the placement's z
-- more. A new table: the walk's own is kept for reuse.
function BG.InWorld(p, r)
  local pts, hs = {}, {}
  for k = 1, #r.pts / 2 do
    pts[2 * k - 1], pts[2 * k] = ToWorld(p, r.pts[2 * k - 1], r.pts[2 * k])
  end
  for k, z in ipairs(r.zs or r.fz or {}) do hs[k] = z and (z + p.z) or false end
  local kinds = {}
  for k, v in ipairs(r.kinds or {}) do kinds[k] = v end
  return { pts = pts, kinds = kinds, fz = hs, length = r.length, road = 0, onLink = r.onLink, bends = r.bends,
    worldGrid = true, buildingGrid = r.cityGrid }
end

BG.routes, BG.order, BG.jobs = {}, {}, {}
BG.stats = { walks = 0, doors = 0, inside = 0, noWay = 0, pending = 0 }
local function Remember(key, r)
  if not BG.routes[key] then BG.order[#BG.order + 1] = key end
  BG.routes[key] = r
  while #BG.order > BG.CACHE do BG.routes[table.remove(BG.order, 1)] = nil end
end

-- The building's walk between a door and (fx, fy, fz) in its frame (`out`: from that spot out to a door), every door a
-- candidate costing its yards from (ox, oy), world: { route (frame), door = { x, y, z (frame) } }, false, or "pending".
function BG.DoorWalk(c, fx, fy, fz, out, ox, oy)
  local p = c.place
  local key = string.format("%s:%.0f:%.0f:%.0f:%s:%.0f:%.0f", c.name, fx, fy, fz or -99999, out and "o" or "i", ox, oy)
  local got = BG.routes[key]
  if got ~= nil then return got end
  local CG = ns.CityGrid
  local function Work()
    local doors = {}
    for ci = 0, c.w * c.h - 1 do
      local n = CG.Count(c, ci)
      if n > 0 then
        local f = CG.First(c, ci)
        for k = 0, n - 1 do
          local s = f + k
          if Flags(c, s) % 2 == 1 then
            local px, py = CG.Pt(c, s, ci)
            local wx, wy = ToWorld(p, px, py)
            doors[#doors + 1] = { s = s, ci = ci, cost = Dist(ox, oy, wx, wy) * BG.DOOR_FACTOR, x = px, y = py }
          end
        end
      end
    end
    local result = false
    local ends = CG.Ends(c, fx, fy, fz)
    if doors[1] and ends[1] then
      local x = { maxDrop = CG.MaxDrop() }
      local steps
      if out then
        local goals = {}
        for _, d in ipairs(doors) do goals[d.s] = d.cost end
        local hx, hy = ToFrame(p, ox, oy) -- (toward the leg's other end: never more than a door's yards and its own)
        steps = CG.Search(c, ends, goals, hx, hy, x)
      else
        local goals = {}
        for _, e in ipairs(ends) do goals[e.s] = e.cost end
        steps = CG.Search(c, doors, goals, fx, fy, x)
      end
      if steps and steps[1] then
        local dstep = out and steps[#steps] or steps[1]
        local dx, dy = CG.Pt(c, dstep.s, dstep.ci)
        local route
        if out then route = CG.Pull(c, steps, fx, fy, dx, dy) else route = CG.Pull(c, steps, dx, dy, fx, fy) end
        result = { route = route, door = { x = dx, y = dy, z = CG.Z(c, dstep.s) } }
      end
    end
    Remember(key, result)
    return result
  end
  local Rt = R()
  local co, main = coroutine.running()
  if Rt.SYNC_WALKS or (co and not main) then return Work() end
  if not BG.jobs[key] then
    BG.jobs[key] = true
    BG.stats.pending = BG.stats.pending + 1
    Rt.Background("buildinggrid:" .. key, Work, function()
      BG.jobs[key] = nil
      local N = ns.Nav
      if N and N.Invalidate then N.Invalidate(true) end
    end, nil, nil, function()
      BG.jobs[key] = nil
      local N = ns.Nav
      if N and N.Invalidate then N.Invalidate(true) end
    end)
  end
  return "pending"
end

-- The leg (WorldGrid.lua's WG.Leg, the open world's, before the older indoor roads): with an end inside a building of
-- the test's towns, the world grid's walk to its door and the building's grid from it. A route, "pending", or nil (not
-- such a leg, or the building's grid has no way: the older indoor roads, as before).
function BG.Leg(wc, cont, sx, sy, tx, ty, opts)
  if not BG.On() then return nil end
  local CG, WG = ns.CityGrid, ns.WorldGrid
  local pt, ct = BG.At(cont, tx, ty, opts.tz)
  -- (from where the player stands: the floor followed in the building, CityGrid's TrackFloor, step 5)
  if opts.z == nil and CG.PlayerStart and CG.PlayerStart(cont, sx, sy) then
    local fz = CG.PlayerFloorZ(cont, sx, sy)
    if fz then
      local o2 = {}
      for k, v in pairs(opts) do o2[k] = v end
      o2.z = fz
      opts = o2
    end
  end
  local ps, cs = BG.At(cont, sx, sy, opts.z, opts.indoors)
  if not (pt or ps) then return nil end
  BG.stats.walks = BG.stats.walks + 1
  local md = opts.maxDrop or (ns.Nav and ns.Nav.SafeDrop and ns.Nav.SafeDrop()) or nil
  if pt and pt == ps then
    -- (both ends in one building: its grid alone)
    local fsx, fsy = ToFrame(pt, sx, sy)
    local ftx, fty = ToFrame(pt, tx, ty)
    local r = CG.Walk(ct, fsx, fsy, opts.z and (opts.z - pt.z), ftx, fty, opts.tz - pt.z, md)
    if r == "pending" then return "pending" end
    if not r then
      BG.stats.noWay = BG.stats.noWay + 1
      return nil
    end
    BG.stats.inside = BG.stats.inside + 1
    return BG.InWorld(pt, r)
  end
  -- (out of the start's building to its door, the rest from there)
  local head, fromX, fromY, fromZ = nil, sx, sy, opts.z
  if ps then
    local fsx, fsy = ToFrame(ps, sx, sy)
    local w = BG.DoorWalk(cs, fsx, fsy, opts.z and (opts.z - ps.z), true, tx, ty)
    if w == "pending" then return "pending" end
    if not w then
      BG.stats.noWay = BG.stats.noWay + 1
      return nil
    end
    head = BG.InWorld(ps, w.route)
    fromX, fromY = ToWorld(ps, w.door.x, w.door.y)
    fromZ = w.door.z + ps.z
  end
  local tail, toX, toY, toZ = nil, tx, ty, opts.tz
  if pt then
    local ftx, fty = ToFrame(pt, tx, ty)
    local w = BG.DoorWalk(ct, ftx, fty, opts.tz - pt.z, false, fromX, fromY)
    if w == "pending" then return "pending" end
    if not w then
      BG.stats.noWay = BG.stats.noWay + 1
      return nil
    end
    tail = BG.InWorld(pt, w.route)
    toX, toY = ToWorld(pt, w.door.x, w.door.y)
    toZ = w.door.z + pt.z
  end
  -- (the world grid's walk between them: from the start, or the start's door, to the stop, or the stop's door)
  local o2 = {}
  for k, v in pairs(opts) do o2[k] = v end
  o2.z, o2.tz, o2.indoors = fromZ, toZ, nil
  local mid = WG.Walk(wc, fromX, fromY, fromZ, toX, toY, toZ, o2)
  if mid == "pending" or mid == nil then return "pending" end
  if not mid then
    BG.stats.noWay = BG.stats.noWay + 1
    return nil
  end
  local r = mid
  if head then r = CG.Concat(head, r, false) end
  if tail then r = CG.Concat(r, tail, false) end
  r.worldGrid = true
  r.buildingGrid = (tail and tail.buildingGrid) or (head and head.buildingGrid)
  BG.stats.doors = BG.stats.doors + 1
  return r
end

function BG.Reset()
  BG.routes, BG.order = {}, {}
end
