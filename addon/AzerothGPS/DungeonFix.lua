-- Where the player may be inside a dungeon, from range checks to the mobs around them (item 105, 1.4.1; Kooki3z
-- 2026-11-26: "guess the player's spot inside dungeons from range checks ... better than nothing").
--
-- The game gives addons no position in instances (UnitPosition, GetPlayerFacing and C_Map.GetBestMapForUnit are nil
-- there), but its range checks are in 3D and still answer: in range of a spell or item at R yards, or of a
-- CheckInteractDistance index, the player is within R of that mob; out of range, farther. A mob that stands still at a
-- known spawn (the CMaNGOS dump's creature spawns in that instance) turns each answer into a shell round its spawn;
-- several mobs' shells meet where the player is. Which spawn a mob stands at isn't known (a camp has several of one
-- kind, and inside instances the game makes other units' GUIDs and names secret, so often not even which kind: then its
-- level and classification narrow the spawns it may be), so each sighting has candidate spawns and the spot kept is the
-- one most sightings agree on with some candidate each (the consistent set).
--
-- The spots tried are the instance's roads (ns.Roads[level]: its nodes, its packed points and every POINT_STEP yards
-- between, with heights from its `z`) and the spawns themselves (the player fights where the mobs stand). A prior (the
-- last estimate, or the way in after entering) keeps the search near where the player can have got to since.
--
-- Pure: nothing here asks the game anything; the caller (a developer's range probe now; the "You are here"
-- pin's automatic move later, item 105's step 2) gathers the sightings. Never errors on odd input (pcall'd by callers).
local _, ns = ...
local DF = {}
ns.DungeonFix = DF

local sqrt, max, min, floor, huge = math.sqrt, math.max, math.min, math.floor, math.huge

DF.SLACK = 3 -- yards: in range means within the range and at most this more (the bodies' reach; HB.RANGE_SLACK)
DF.WANDER = 2 -- yards a mob standing still may be off its spawn
DF.PATROL = 40 -- yards a mob on a patrol path (MovementType 2) may be off its spawn: weak evidence
DF.POINT_STEP = 4 -- yards between the spots tried along a road
DF.CELL = 16 -- yards: the spots' grid buckets
DF.RADIUS_PAD = 2 -- yards added to the estimate's radius
DF.TOLERANCE = 1.5 -- yards of violation a spot may have and still count as in the best set
DF.SPEED = 8 -- yards a second the player may have moved since the prior (a run with a sprint now and then)
DF.MAX_SPREAD = 60 -- yards: an estimate whose spots spread further than this is no estimate (too ambiguous)
DF.LINK_YD = 3 * DF.POINT_STEP -- yards: the best spots this near each other are one place
DF.PLACES_R = 25 -- yards: best spots in several places all within this of their middle still make an estimate
DF.MAX_SIGHTS = 12 -- sightings weighed at most (the ones with the fewest candidates near: the most telling)

-- UnitClassification's answers by creature_template Rank (0 normal, 1 elite, 2 rare elite, 3 boss, 4 rare).
DF.RANK_OF = { normal = 0, trivial = 0, minus = 0, elite = 1, rareelite = 2, worldboss = 3, rare = 4 }

local function D3(ax, ay, az, bx, by, bz)
  local dx, dy = ax - bx, ay - by
  if az and bz then
    local dz = az - bz
    return sqrt(dx * dx + dy * dy + dz * dz)
  end
  return sqrt(dx * dx + dy * dy)
end

---------------------------------------------------------------------------------------------------- the spawns
-- A level's spawns from its packed text: lines "id x y z move wander" (move: creature MovementType, 0 still, 1 random
-- within `wander` yards, 2 a path). Returns a list of { id, x, y, z, move, wander }.
function DF.ParseSpawns(text)
  local out = {}
  if type(text) ~= "string" then return out end
  for id, x, y, z, mv, wd in text:gmatch("(%d+) (%-?[%d.]+) (%-?[%d.]+) (%-?[%d.]+) (%d) ([%d.]+)") do
    out[#out + 1] = { id = tonumber(id), x = tonumber(x), y = tonumber(y), z = tonumber(z), move = tonumber(mv),
      wander = tonumber(wd) }
  end
  return out
end

-- How far a spawn's mob may stand off it.
function DF.Wander(sp)
  if sp.move == 2 then return DF.PATROL end
  if sp.move == 1 then return DF.WANDER + (sp.wander or 0) end
  return DF.WANDER
end

-- The spawns a sighting may be: by its creature id when the game said it, else by its level, classification and
-- whether it's an enemy (the mob's template's level range, rank and side; a level of -1, "??", says nothing).
-- `mobs[id]` = { name, lo, hi, rank, class, side ("A", "H", "B": an enemy; "N" neither) }.
function DF.Candidates(sight, spawns, mobs)
  local out = {}
  if not spawns then return out end
  local rank = sight.class and DF.RANK_OF[sight.class]
  for _, sp in ipairs(spawns) do
    local ok
    if sight.npc then
      ok = sp.id == sight.npc
    else
      local m = mobs and mobs[sp.id]
      ok = true
      if m then
        local lv = sight.level
        if type(lv) == "number" and lv > 0 and (lv < (m[2] or lv) or lv > (m[3] or lv)) then ok = false end
        if ok and rank and m[4] and m[4] ~= rank then ok = false end
        if ok and sight.enemy ~= nil and m[6] and (m[6] ~= "N") ~= sight.enemy then ok = false end
      elseif sight.level or sight.class then
        ok = false -- (no template: can't match a fingerprint)
      end
    end
    if ok then out[#out + 1] = sp end
  end
  return out
end

-- A sighting's shell from its checks ({ r, inside } each): the nearest the mob can be (the largest range it's out of)
-- and the farthest (the smallest it's in, plus SLACK). Either may be nil.
function DF.Shell(checks)
  local lo, hi
  for _, ck in ipairs(checks or {}) do
    if type(ck.r) == "number" then
      if ck.inside == true then
        local h = ck.r + DF.SLACK
        if not hi or h < hi then hi = h end
      elseif ck.inside == false then
        if not lo or ck.r > lo then lo = ck.r end
      end
    end
  end
  return lo, hi
end

-- Yards spot (x, y, z) is outside spawn `sp`'s shell [lo, hi] (0: it fits). No height at the spot: across only, and
-- only the farthest bound (the true 3D distance is at least that across).
local function Violation(x, y, z, sp, lo, hi)
  local w = DF.Wander(sp)
  local d = D3(x, y, z, sp.x, sp.y, sp.z)
  local v = 0
  if hi and d - w > hi then v = d - w - hi end
  if lo and z and d + w < lo then v = max(v, lo - d - w) end
  return v
end

---------------------------------------------------------------------------------------------------- the spots
local PACK = {}
do
  local chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
  for i = 1, #chars do PACK[chars:byte(i)] = i - 1 end
end

-- The spots tried on `level`: its roads' nodes and points every POINT_STEP yards along them (heights between the
-- nodes' `z` by the share of the way), plus `extra` ({ x, y, z } each: the spawns). Kept per level. Returns a list
-- of { x, y, z } and its grid { [key] = { i, ... } }.
local spotCache = {}
function DF.Spots(level, extra)
  local c = spotCache[level]
  if c then return c.list, c.grid end
  local list = {}
  local rd = ns.Roads and ns.Roads[level]
  local n, zs = rd and rd.n, rd and rd.z
  local function Add(x, y, z) list[#list + 1] = { x = x, y = y, z = z } end
  if type(n) == "table" then
    for i = 1, #n - 1, 2 do Add(n[i], n[i + 1], zs and zs[(i + 1) / 2]) end
    for _, e in ipairs(rd.e or {}) do
      local a, b = e[1], e[2]
      if type(a) == "number" and type(b) == "number" and n[a * 2] and n[b * 2] then
        local pts = { n[a * 2 - 1], n[a * 2] }
        if type(e[5]) == "string" then
          local x, y, s = pts[1], pts[2], e[5]
          for i = 1, #s - 3, 4 do
            local b1, b2, b3, b4 = s:byte(i, i + 3)
            x = x + (PACK[b1] or 0) * 64 + (PACK[b2] or 0) - 2048
            y = y + (PACK[b3] or 0) * 64 + (PACK[b4] or 0) - 2048
            pts[#pts + 1], pts[#pts + 2] = x, y
          end
        else
          for j = 5, #e - 1, 2 do
            if type(e[j]) == "number" and type(e[j + 1]) == "number" then
              pts[#pts + 1], pts[#pts + 2] = e[j], e[j + 1]
            end
          end
        end
        pts[#pts + 1], pts[#pts + 2] = n[b * 2 - 1], n[b * 2]
        local total = 0
        for j = 1, #pts - 3, 2 do total = total + D3(pts[j], pts[j + 1], nil, pts[j + 2], pts[j + 3]) end
        local za, zb = zs and zs[a], zs and zs[b]
        local walked = 0
        for j = 1, #pts - 3, 2 do
          local x0, y0, x1, y1 = pts[j], pts[j + 1], pts[j + 2], pts[j + 3]
          local len = D3(x0, y0, nil, x1, y1)
          local steps = floor(len / DF.POINT_STEP)
          for k = (j == 1) and 1 or 0, steps do
            local f = len > 0 and (k * DF.POINT_STEP) / len or 0
            if f < 1 then
              local at = walked + f * len
              local z = za and zb and total > 0 and za + (zb - za) * (at / total) or za or zb
              Add(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, z)
            end
          end
          walked = walked + len
        end
      end
    end
  end
  for _, p in ipairs(extra or {}) do Add(p.x, p.y, p.z) end
  local grid = {}
  for i, p in ipairs(list) do
    local key = floor(p.x / DF.CELL) * 100000 + floor(p.y / DF.CELL)
    local b = grid[key]
    if not b then b = {} grid[key] = b end
    b[#b + 1] = i
  end
  spotCache[level] = { list = list, grid = grid }
  return list, grid
end
function DF.ResetSpots() spotCache = {} end -- (the tests; new data)

-- The spots' indices within `r` across of (x, y) (nil r: all).
local function Near(list, grid, x, y, r, into)
  into = into or {}
  local c0, c1 = floor((x - r) / DF.CELL), floor((x + r) / DF.CELL)
  local d0, d1 = floor((y - r) / DF.CELL), floor((y + r) / DF.CELL)
  for cx = c0, c1 do
    for cy = d0, d1 do
      local b = grid[cx * 100000 + cy]
      if b then
        for _, i in ipairs(b) do
          local p = list[i]
          if D3(p.x, p.y, nil, x, y) <= r then into[i] = true end
        end
      end
    end
  end
  return into
end

-- How many places apart the spots `set` ({ i } rows into `list`) are in: spots within LINK_YD (3D) of each other
-- are one place.
function DF.Places(list, set)
  local L = DF.LINK_YD
  local cells = {}
  local function Key(p) return floor(p.x / L) * 100000 + floor(p.y / L) end
  for k, row in ipairs(set) do
    local key = Key(list[row.i])
    local b = cells[key]
    if not b then b = {} cells[key] = b end
    b[#b + 1] = k
  end
  local seen, places = {}, 0
  for k in ipairs(set) do
    if not seen[k] then
      places = places + 1
      seen[k] = true
      local stack = { k }
      while stack[1] do
        local j = table.remove(stack)
        local p = list[set[j].i]
        local cx, cy = floor(p.x / L), floor(p.y / L)
        for ax = cx - 1, cx + 1 do
          for ay = cy - 1, cy + 1 do
            for _, m in ipairs(cells[ax * 100000 + ay] or {}) do
              if not seen[m] then
                local q = list[set[m].i]
                if D3(p.x, p.y, p.z, q.x, q.y, q.z) <= L then
                  seen[m] = true
                  stack[#stack + 1] = m
                end
              end
            end
          end
        end
      end
    end
  end
  return places
end

---------------------------------------------------------------------------------------------------- the estimate
-- The player's spot from `sights` (each { checks = { { r, inside }, ... }, cands = { spawn, ... } }) over `spots`
-- (DF.Spots' list and grid). `prior` ({ x, y, z, r, at }, optional): only spots the player can have reached since
-- (DF.SPEED), unless none is. Returns { x, y, z, r, score, of, spots, places, picks = { [sight index] = spawn } } or
-- nil, why ("no checks in range", "no spot fits", "ambiguous": the best spots in places further apart than PLACES_R,
-- "too spread") and, for the last two, what was found ({ places, r } or { x, y, z, r }).
function DF.Estimate(sights, list, grid, prior, now)
  if not (list and list[1]) then return nil, "no spots" end
  -- (each sighting's shell; the ones with a farthest bound and candidates can place the player)
  local used = {}
  for i, s in ipairs(sights or {}) do
    local lo, hi = DF.Shell(s.checks)
    if (lo or hi) and s.cands and s.cands[1] then used[#used + 1] = { i = i, lo = lo, hi = hi, cands = s.cands } end
  end
  local anchor
  for _, u in ipairs(used) do
    if u.hi and (not anchor or #u.cands < #anchor.cands) then anchor = u end
  end
  if not anchor then return nil, "no checks in range" end
  -- (the spots near the anchor's candidates: within its farthest bound plus their wander)
  local pick = {}
  for _, sp in ipairs(anchor.cands) do Near(list, grid, sp.x, sp.y, anchor.hi + DF.Wander(sp), pick) end
  -- (the spots in `pick` scored: the best score and every spot's row)
  local function Score(pick)
    -- (each sighting's candidates that can matter for these spots: within its bound of their box; one only out of range
    -- with a candidate beyond that fits every spot and says nothing: left out, counted as fitting)
    local x0, y0, x1, y1 = huge, huge, -huge, -huge
    for i in pairs(pick) do
      local p = list[i]
      x0, y0, x1, y1 = min(x0, p.x), min(y0, p.y), max(x1, p.x), max(y1, p.y)
    end
    local free, kept = 0, {}
    for _, u in ipairs(used) do
      local reach = (u.hi or u.lo or 0)
      local near, far = {}, false
      for _, sp in ipairs(u.cands) do
        local w = reach + DF.Wander(sp)
        if sp.x >= x0 - w and sp.x <= x1 + w and sp.y >= y0 - w and sp.y <= y1 + w then
          near[#near + 1] = sp
        else
          far = true
        end
      end
      if not u.hi and far then
        free = free + 1
      elseif u.hi and not near[1] then
        -- (in range of a mob none of whose candidates is near any spot here: it can't fit; it lowers every score alike)
      else
        kept[#kept + 1] = { i = u.i, hi = u.hi, lo = u.lo, cands = near }
      end
    end
    table.sort(kept, function(a, b) return #a.cands < #b.cands end)
    while #kept > DF.MAX_SIGHTS do table.remove(kept) end
    -- (each sighting with a farthest bound: its candidates in grid buckets, to look only at the ones that can reach)
    for _, u in ipairs(kept) do
      if u.hi then
        local g, wmax = {}, 0
        for _, sp in ipairs(u.cands) do
          local key = floor(sp.x / DF.CELL) * 100000 + floor(sp.y / DF.CELL)
          local b = g[key]
          if not b then b = {} g[key] = b end
          b[#b + 1] = sp
          wmax = max(wmax, DF.Wander(sp))
        end
        u.grid, u.cells = g, floor((u.hi + wmax) / DF.CELL) + 1
      end
    end
    -- (each spot: how many sightings some candidate fits, and the yards they miss by; a spot that can't reach the best
    -- score any more is left)
    local best, rows, nk = -1, {}, #kept
    for i in pairs(pick) do
      local p = list[i]
      local score, miss, picks, gone = 0, 0, {}, false
      for k, u in ipairs(kept) do
        local bv, bsp = 20, nil
        if u.grid then
          local cx, cy = floor(p.x / DF.CELL), floor(p.y / DF.CELL)
          for ax = cx - u.cells, cx + u.cells do
            for ay = cy - u.cells, cy + u.cells do
              local b = u.grid[ax * 100000 + ay]
              if b then
                for _, sp in ipairs(b) do
                  local v = Violation(p.x, p.y, p.z, sp, u.lo, u.hi)
                  if v < bv then bv, bsp = v, sp end
                  if v == 0 then break end
                end
              end
              if bv == 0 then break end
            end
            if bv == 0 then break end
          end
        else
          for _, sp in ipairs(u.cands) do
            local v = Violation(p.x, p.y, p.z, sp, u.lo, u.hi)
            if v < bv then bv, bsp = v, sp end
            if v == 0 then break end
          end
        end
        if bv <= DF.TOLERANCE then score = score + 1 end
        miss = miss + bv
        picks[u.i] = bsp
        if score + free + (nk - k) < best then gone = true break end
      end
      if not gone then
        score = score + free
        rows[#rows + 1] = { i = i, score = score, miss = miss, picks = picks }
        if score > best then best = score end
      end
    end
    return best, rows
  end
  -- (with a prior, the spots the player can have reached since; where fewer sightings fit there than anywhere, the
  -- prior is wrong (a teleport, a /reload, a guess gone astray): left out)
  local best, rows = nil, nil
  if prior and prior.x and prior.y then
    local reach = (prior.r or 0) + DF.SPEED * max(0, (now or prior.at or 0) - (prior.at or now or 0))
    local near = {}
    for i in pairs(pick) do
      local p = list[i]
      if D3(p.x, p.y, p.z, prior.x, prior.y, prior.z) <= reach then near[i] = true end
    end
    if next(near) then
      best, rows = Score(near)
      if best < #used then
        local b2, r2 = Score(pick)
        if b2 > best then best, rows = b2, r2 end
      end
    end
  end
  if not best then best, rows = Score(pick) end
  if best <= 0 then return nil, "no spot fits" end
  local bestMiss = huge
  for _, r in ipairs(rows) do
    if r.score == best and r.miss < bestMiss then bestMiss = r.miss end
  end
  local sx, sy, sz, nz, n, set = 0, 0, 0, 0, 0, {}
  for _, r in ipairs(rows) do
    if r.score == best and r.miss <= bestMiss + DF.TOLERANCE then set[#set + 1] = r end
  end
  -- (the best spots in places apart: the checks fit at more than one place; near each other, one estimate round them
  -- all, else it can't tell which)
  local places = DF.Places(list, set)
  for _, row in ipairs(set) do
    local p = list[row.i]
    sx, sy, n = sx + p.x, sy + p.y, n + 1
    if p.z then sz, nz = sz + p.z, nz + 1 end
  end
  local x, y, z = sx / n, sy / n, nz > 0 and sz / nz or nil
  local r, near, nd = 0, nil, huge
  for _, row in ipairs(set) do
    local p = list[row.i]
    local d = D3(p.x, p.y, nil, x, y)
    if d > r then r = d end
    if d < nd then near, nd = row, d end
  end
  if places > 1 and r > DF.PLACES_R then
    return nil, "ambiguous", { places = places, score = best, of = #used, r = r }
  end
  if r > DF.MAX_SPREAD then return nil, "too spread", { x = x, y = y, z = z, r = r, score = best, of = #used } end
  return { x = x, y = y, z = z, r = r + DF.RADIUS_PAD, score = best, of = #used, spots = n, places = places,
    picks = near.picks }
end

-- Where the player stands just inside `level`'s way in (after entering: the first prior), or nil.
function DF.WayIn(level)
  local inst = ns.Instances and ns.Instances[level]
  local e = inst and inst.entrances and inst.entrances[1]
  if not (e and e[4] and e[5]) then return nil end
  return { x = e[4], y = e[5], z = e[6], r = 10 }
end
