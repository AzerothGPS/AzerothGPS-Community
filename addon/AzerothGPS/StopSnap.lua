-- Stops on walkable ground (item 116b, Kooki3z 2026-11-26's grid ideas): a stop made in rock, in a wall or on a roof
-- (a map click, a /way, a map pin, a quest's spot) is moved to the nearest walkable cell of the world grid
-- (WorldGrid.lua) on its most likely floor, everywhere in the open world. The caves' own (GPSFrame's G.ClickFloorZ,
-- d944e18c) picks the floor a click over a cave means; this then keeps the stop on that floor, and does the same for
-- every other stop:
-- - the floor: an NPC's stop its NPC's (its spawn's height; moved NPC_YD at most: the NPC stands where it
--   stands), a stop with a height of its own (a cave's floor clicked, a city place) that height, else the nearest
--   floor, but over a cave never its floor under the hill for a click on the land (item 82g);
-- - only ground that leads on (PIECE_MIN surfaces walked from it), never a pocket in the rock;
-- - a stop already on walkable ground (a surface the player reaches, or water, on its floor in its own cell) isn't
--   moved; a stop moved takes the floor's height as the route's (Nav's guessZ, zSource "snap");
-- - not: a corpse (where you died), a guide's step (theirs), a dungeon's way in (its portal), the capitals (their city
--   grids), a region of the grid the game didn't load, anywhere off the open world's continents.
-- Nav's Copy asks once a stop (`snapped` kept on it).
local _, ns = ...
local SS = {}
ns.StopSnap = SS

local floor, abs, sqrt, max = math.floor, math.abs, math.sqrt, math.max

SS.KEEP_Z = 8 -- yards: a walkable surface this near the stop's height in its cell: on walkable ground, kept
SS.UNDER_YD = 12 -- yards: a surface this far under the ground is under the hill (a cave's), not the ground's floor (the
-- shipped heights' 16.7 yd samples run 8 yd off the land: WorldGrid's INTO_GROUND_TOP_Z)
SS.MAX_CELLS = 12 -- cells (8.33 yd) round the stop looked at for walkable ground: about 100 yd
SS.NPC_YD = 10 -- an NPC's stop: moved this far at most (it stands where it stands; the grid lacks a few of their
-- spots, Cenarion Hold's flight master's platform 24 yd off it: left there, the route goes as near as it can)
SS.Z_WEIGHT = 2 -- a yard off the stop's floor costs this many yards across
SS.PIECE_MIN = 60 -- surfaces a spot's ground leads on to at least (walked from it): not a pocket in the rock. Route-quality
-- 2026-11-26: Timbermaw Hold's label went 8 yd onto a ledge of 4 surfaces in the mountain, its trip no way found

local F_SWIM, F_REACH = 1, 4
local function Bit(v, b) return floor(v / b) % 2 == 1 end
local function Walkable(f) return Bit(f, F_REACH) or Bit(f, F_SWIM) end

-- The ground's height at (x, y) (Data/Heights.lua), or nil.
local function Ground(cont, x, y)
  local GD = ns.Ground
  if not (GD and GD.Sample) then return nil end
  local ok, h = pcall(GD.Sample, cont, x, y)
  return ok and type(h) == "number" and h or nil
end

-- The surfaces of the grid's cell (gx, gy): { z, x, y, f } each; nil when its tile's region isn't loaded (unknown).
local function Cell(WG, c, gx, gy)
  local key, ci = WG.CellKey(c, gx, gy)
  if not key then return nil end
  local t = WG.Tile(c, key)
  if t == nil then return nil end
  local rx, ry = WG.RegionOf(c, key)
  if c.regions[rx .. ":" .. ry] ~= true then return nil end
  local out = {}
  if not t then return out end -- (a tile with no surfaces at all: the region has none there)
  local n = WG.Count(t, ci)
  if n == 0 then return out end
  local f0 = WG.First(t, ci)
  for k = 0, n - 1 do
    local s = f0 + k
    local px, py = WG.Pt(c, t, s, ci)
    out[#out + 1] = { z = WG.Z(c, t, s), x = px, y = py, f = WG.Flags(t, s), key = key, ci = ci, s = s }
  end
  return out
end

-- Whether surface `s` (a Cell's) leads on to PIECE_MIN surfaces by the grid's links walked both ways (a drop off a
-- ledge is one way: a mesa's top left only by drops leads nowhere a route comes from; route-quality 2026-11-26, Drygulch
-- Ravine's label onto its rim 9 yd off, no way found). `seen`: this look's answers.
local OPP = { 3, 4, 1, 2, 7, 8, 5, 6 }
local function LeadsOn(WG, c, s, seen)
  local id0 = s.key * 1048576 + s.s
  if seen[id0] ~= nil then return seen[id0] end
  local done, q, head, n = { [id0] = true }, { { s.key, s.ci, s.s } }, 1, 1
  while q[head] and n < SS.PIECE_MIN do
    local e = q[head]
    head = head + 1
    local t = WG.Tile(c, e[1])
    for d = 1, 8 do
      local kk = t and WG.Link(t, e[3], d) or 0
      if kk > 0 then
        local nk, nci = WG.Step(c, e[1], e[2], d)
        local nt = nk and WG.Tile(c, nk)
        if nt then
          local s2 = WG.First(nt, nci) + kk - 1
          local id = nk * 1048576 + s2
          local back = WG.Link(nt, s2, OPP[d])
          if not done[id] and back > 0 and WG.First(t, e[2]) + back - 1 == e[3] then
            done[id] = true
            n = n + 1
            q[#q + 1] = { nk, nci, s2 }
          end
        end
      end
    end
  end
  local ok = n >= SS.PIECE_MIN
  seen[id0] = ok
  return ok
end

-- How far surface `s` is off the stop's floor, in yards: `z` the stop's height, else over a cave the ground's there
-- (`gz`: under the ground, the cave's floor, is off it; over it isn't), else none (any floor: the nearest. The shipped
-- heights' coarse ground isn't a floor: Drygulch Ravine's bed 19 yd under it, route-quality 2026-11-26).
local function OffFloor(s, z, gz)
  if z then return max(0, abs(s.z - z) - SS.KEEP_Z) end
  if gz then return max(0, (gz - SS.UNDER_YD) - s.z) end
  return 0
end

-- Where stop `d` should be: x, y, z (z nil for a stop with no height of its own), moved; or nil, left where it is.
function SS.Spot(d)
  local WG, N, Geo = ns.WorldGrid, ns.Nav, ns.Geo
  if not (d and d.x and d.y and d.cont and WG and WG.On and WG.On() and WG.CellKey and Geo) then return nil end
  if d.corpse or d.rxp or d.zygor or d.polestar or d.questify or d.apr or d.openxp or d.flowup or d.boss or d.enc then return nil end
  if d.zSource == "portal" then return nil end
  local cont, x, y = d.cont, d.x, d.y
  if Geo.Base(cont) ~= cont then return nil end -- (a city's level, a dungeon: not the open world's grid)
  if N and N.InGridBox and N.InGridBox(cont, x, y) then return nil end -- (a capital: its city grid's)
  if WG.NotMeshed and WG.NotMeshed(cont, x, y) then return nil end
  if N and N.EntrancePortalAt and N.EntrancePortalAt(cont, x, y) then return nil end -- (a dungeon's way in)
  -- (a stop in a cave with a height of its own: the cave's floor, GPSFrame's G.ClickFloorZ, already picked. Moved, 71 of
  -- the sweep's 224 caves' stops went, some up onto the hill over them, 20 to 68 yd; test_cave_sweep, #1000)
  if d.z ~= nil and WG.CaveAt and WG.CaveAt(cont, x, y) ~= nil then return nil end
  local c = WG.Cont(cont)
  if not c then return nil end
  local npc = tonumber(d.npcId) ~= nil
  local z = d.z
  if z == nil and npc and N and N.SpawnZ then z = N.SpawnZ(cont, x, y) end
  local cell = c.cell
  local gx, gy = floor(x / cell), floor(y / cell)
  local own = Cell(WG, c, gx, gy)
  if not own then return nil end -- (unknown: its region not loaded)
  local overCave = not z and WG.CaveAt and WG.CaveAt(cont, x, y) ~= nil
  local gz = overCave and Ground(cont, x, y) or nil
  local seen = {}
  -- (on walkable ground on its floor: kept. An NPC's: its cell or one by it, the cells' points are a few yards apart)
  local keepR = npc and 1 or 0
  for di = -keepR, keepR do
    for dj = -keepR, keepR do
      for _, s in ipairs((di == 0 and dj == 0) and own or Cell(WG, c, gx + di, gy + dj) or {}) do
        if Walkable(s.f) and OffFloor(s, z, gz) == 0 and LeadsOn(WG, c, s, seen) then return nil end
      end
    end
  end
  -- (first the surfaces a route to it ends on, WorldGrid's Ends (its cell's, else the nearest cell's with any within
  -- NEAR_CELLS), the cheapest that leads on: the stop goes where its route went before. Route-quality 2026-11-26: the
  -- nearest walkable cell to Drygulch Ravine's label was its rim, 9 yd off, a corridor search from Ratchet found no
  -- way up to; its route ends on the ravine's bed, 15 yd off)
  local best, bc
  if WG.Ends and not npc then
    for _, f in ipairs(WG.Ends(c, x, y, z) or {}) do
      if Walkable(f.f or 0) and (not bc or (f.cost or 0) < bc) and Cell(WG, c, floor(f.x / cell), floor(f.y / cell)) then
        local sf = { z = f.z, x = f.x, y = f.y, f = f.f, key = f.key, ci = f.ci, s = f.s }
        if LeadsOn(WG, c, sf, seen) then best, bc = sf, f.cost or 0 end
      end
    end
    if best then return best.x, best.y, best.z end
  end
  -- (else the nearest walkable surface round it, nearer its floor first: ring by ring while a nearer one may be there)
  local rmax = npc and math.ceil(SS.NPC_YD / cell) or SS.MAX_CELLS
  local reach = npc and SS.NPC_YD or math.huge
  for r = 0, rmax do
    if bc and (r - 1) * cell > bc then break end
    for di = -r, r do
      for dj = -r, r do
        if max(abs(di), abs(dj)) == r then
          for _, s in ipairs(Cell(WG, c, gx + di, gy + dj) or {}) do
            if Walkable(s.f) then
              local cz = z
              local cg = overCave and Ground(cont, s.x, s.y) or nil
              local dd = sqrt((s.x - x) ^ 2 + (s.y - y) ^ 2)
              local cost = dd + SS.Z_WEIGHT * OffFloor(s, cz, cg)
              if dd <= reach and (not bc or cost < bc) and LeadsOn(WG, c, s, seen) then best, bc = s, cost end
            end
          end
        end
      end
    end
  end
  if not best then return nil end
  return best.x, best.y, best.z
end

-- Stop `d` on walkable ground: `d` itself when it's there already (or isn't for moving), else a copy moved there (its
-- height the floor's when it had one of its own, an NPC's kept). `snapped` set either way: asked once.
function SS.Stop(d)
  if not d or d.snapped then return d end
  local ok, x, y, z = pcall(SS.Spot, d)
  local c = {}
  for k, v in pairs(d) do c[k] = v end
  c.snapped = true
  if ok and x then
    c.x, c.y = x, y
    c.snapFrom = { d.x, d.y }
    -- (its height the floor's: its own's when it had one, else the route's guess, Nav's guessZ, not the shipped
    -- heights' coarse ground there)
    if d.z ~= nil and not tonumber(d.npcId) then
      c.z = z
    elseif d.z == nil then
      c.z, c.zSource = z, "snap"
    end
  end
  return c
end
