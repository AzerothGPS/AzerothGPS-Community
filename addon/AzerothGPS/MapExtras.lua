-- Map extras from the walk grids (item 114, 1.4.1; Kooki3z 2026-11-26, the grid ideas: "do all except the L ones"):
--
-- (a) The height profile: a strip along the map's bottom edge showing the route to the next stop from the side, its
--     climbs (green), drops (orange) and jumps (the coil's orange-red, thicker), with the player as a dot moving along
--     it. Heights: the route's own (`zs` in a level of its own, `fz` from the city and world grids), else the world
--     grid's surface there nearest the last height (only where its tiles are loaded already: nothing loaded for the
--     strip), else the map's ground (Router.GroundZ). Worked out once per route part (the walk from the player kept
--     whole by Nav, `r.fullFirst`); each redraw only moves the dot. A flat route (no rise of PROFILE_MIN_RISE, no jump),
--     a short one, the minimap square: no strip. Option `heightProfile` (Options > Map).
-- (b) The jump landing preview: hovering a planned jump on the map (GPSFrame's G.JumpHover) rings where it lands and
--     says the drop in yards and whether it hurts at the Safe drop setting (MX.HurtLine). Yards only: the player's
--     health is secret in WoW Forever.
-- (c) The floor picker: at any spot where the grids' floors lie over each other (the city grid in a capital or down in
--     Undercity, else the world grid: inns, towers, caves under hills, bridges), a "+" / "-" column on the map like a
--     dungeon's, the floors counted from the grid (MX.FloorsAt), the floor the floor tracker reports (Nav.PlayerFloorZ)
--     shown first and marked yours. A floor picked: the route's floor fade (G.FloorFadeKey) goes by it, and a stop
--     double-clicked there goes on it (MX.ClickZ). Not over a dungeon's or a cave's own map (its art's floors have the
--     map's own column). Option `floorPicker` (Options > Map).
--
-- The map is built up to three times (GPSFrame's BuildMap: the window, the minimap square, the extra window): each map
-- has its own strip and floor picker (MX.New), the minimap square neither. Nothing here is drawn from a file: color
-- textures and lines only (no texture filter to mind).
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end })
local Format = ns.Format or string.format
local MX = {}
ns.MapExtras = MX

local floor, abs, max, min, sqrt = math.floor, math.abs, math.max, math.min, math.sqrt

local function S() return ns.settings and ns.settings.gps or {} end
-- A height or a drop in the player's units (Options > General: yards, meters or feet; Nav.FormatDistance, `short`);
-- `long`: a route's length (kilometers, miles past their start).
local function Dist(yd, long)
  local N = ns.Nav
  if N and N.FormatDistance then return N.FormatDistance(yd, not long) end
  return Format(L["%d yd"], floor(yd + 0.5))
end
MX.Dist = Dist
local function R() return ns.Router end

---------------------------------------------------------------------------------------------------- (a) the profile
MX.PROFILE_MIN_YD = 30 -- a route to the next stop shorter than this: no strip
MX.PROFILE_MIN_RISE = 6 -- yards between its lowest and highest: under this and no jump, it's flat (no strip)
MX.PROFILE_STEP_YD = 8 -- a stretch with no heights of its own: the ground looked at this often along it ...
MX.PROFILE_MAX_LOOKS = 160 -- ... at most this many looks a route (a longer one: further apart)
MX.PROFILE_COLS = 48 -- the strip's columns (its line's pieces)
MX.NOISE_YD = 1 -- climbs and drops added up past this (the ground's small bumps left out)
MX.SLOPE_FLAT = 0.08 -- a column climbing less than this (yards up a yard along): flat
MX.RIDE_KINDS = { [2] = true, [5] = true, [6] = true } -- (rides: Router.KIND_LIFT_*, Nav's ride; no ground)
MX.profileCache = setmetatable({}, { __mode = "k" }) -- [part] = its profile (or false: none)
MX.groundLooks = 0 -- (the tests: ground looked up)

local function JumpKind(k)
  local Rt = R()
  return Rt ~= nil and (k == Rt.KIND_DROP or k == Rt.KIND_JUMP)
end
MX.JumpKind = JumpKind

-- Whether the world grid's tile under (x, y) is loaded already (the strip and the floor picker never load one).
function MX.GridTileLoaded(c, x, y)
  local WG = ns.WorldGrid
  if not (c and WG and WG.CellKey) then return false end
  local key = WG.CellKey(c, floor(x / c.cell), floor(y / c.cell))
  return key ~= nil and (c.tiles[key] or c.raw[key]) ~= nil
end

-- The ground's height at (x, y) on `level` for the profile: the world grid's surface nearest `near` (the height before
-- along the route), else the map's ground; nil on a level of its own (Undercity's, a dungeon's: only the route's own).
function MX.GroundAt(level, x, y, near)
  local Geo = ns.Geo
  if not (level and Geo and Geo.Base and Geo.Base(level) == level) then return nil end
  MX.groundLooks = MX.groundLooks + 1
  local WG = ns.WorldGrid
  local c = WG and WG.On and WG.On() and WG.Cont and WG.Cont(level)
  if c and WG.SurfacesAt and MX.GridTileLoaded(c, x, y) then
    local ref = near or (R() and R().GroundZ and R().GroundZ(level, x, y))
    local ok, ss = pcall(WG.SurfacesAt, c, x, y, ref)
    if ok and ss and ss[1] then return ss[1].z end
  end
  return R() and R().GroundZ and R().GroundZ(level, x, y) or nil
end

-- A height `z` the route gives at (x, y) on a continent, on the world grid's surface nearest it there (its tile loaded):
-- the Router's own routes carry a building's last floor on over the land as their `fz` (GPSFrame's floor fade notes
-- it), which isn't the ground's; the grid's surface nearest is (a bridge's deck over a canyon stays the deck). Else `z`.
function MX.Snap(level, x, y, z)
  local Geo = ns.Geo
  if not (z and Geo and Geo.Base and Geo.Base(level) == level) then return z end
  local WG = ns.WorldGrid
  local c = WG and WG.On and WG.On() and WG.Cont and WG.Cont(level)
  if not (c and WG.SurfacesAt and MX.GridTileLoaded(c, x, y)) then return z end
  local ok, ss = pcall(WG.SurfacesAt, c, x, y, z)
  if ok and ss and ss[1] then return ss[1].z end
  return z
end
-- The route's own height at point i of `part` (its `zs`, else its `fz`), or nil.
local function OwnZ(part, i)
  local v = part.zs and part.zs[i]
  if type(v) == "number" then return v end
  v = part.fz and part.fz[i]
  if type(v) == "number" then return v end
  return nil
end

-- The profile of route part `part`: { len (yards), s = { d1, z1, d2, z2, ... } (heights along it), lo, hi, up, down
-- (yards climbed and dropped, past NOISE_YD), jumps = { { d0, d1, z0, z1, dz, kind }, ... }, cols = { z at each of
-- PROFILE_COLS + 1 even steps }, colKind = { "up" | "down" | "flat" | "jump" for each column } }, or nil (too short,
-- no heights, a ride). Kept per part.
function MX.Profile(part)
  if not (part and part.pts) then return nil end
  local hit = MX.profileCache[part]
  if hit ~= nil then return hit or nil end
  local p = MX.BuildProfile(part)
  MX.profileCache[part] = p or false
  return p
end
function MX.BuildProfile(part)
  local pts, kinds = part.pts, part.kinds or {}
  local n = #pts / 2
  if n < 2 then return nil end
  local cum, len = { 0 }, 0
  local rides = 0
  for i = 2, n do
    local d = sqrt((pts[2 * i - 1] - pts[2 * i - 3]) ^ 2 + (pts[2 * i] - pts[2 * i - 2]) ^ 2)
    len = len + d
    cum[i] = len
    if MX.RIDE_KINDS[kinds[i - 1]] then rides = rides + d end
  end
  if len < MX.PROFILE_MIN_YD or rides > len / 2 then return nil end
  -- (the ground's looks spread over the stretches with no heights of their own)
  local bare = 0
  for i = 1, n - 1 do
    if not (OwnZ(part, i) and OwnZ(part, i + 1)) then bare = bare + cum[i + 1] - cum[i] end
  end
  local step = max(MX.PROFILE_STEP_YD, bare / MX.PROFILE_MAX_LOOKS)
  local s, last = {}, nil
  local function Add(d, z)
    s[#s + 1], s[#s + 2] = d, z or false
    if z then last = z end
  end
  for i = 1, n - 1 do
    local za, zb = OwnZ(part, i), OwnZ(part, i + 1)
    local seg = cum[i + 1] - cum[i]
    if za and zb then
      Add(cum[i], MX.Snap(part.cont, pts[2 * i - 1], pts[2 * i], za))
    elseif MX.RIDE_KINDS[kinds[i]] then
      Add(cum[i], za or last)
    else
      local k = max(1, floor(seg / step + 0.5))
      for j = 0, k - 1 do
        local t = j / k
        local x = pts[2 * i - 1] + (pts[2 * i + 1] - pts[2 * i - 1]) * t
        local y = pts[2 * i] + (pts[2 * i + 2] - pts[2 * i]) * t
        local z = (j == 0 and za) or MX.GroundAt(part.cont, x, y, last)
        Add(cum[i] + seg * t, z)
      end
    end
  end
  local zn = OwnZ(part, n)
  Add(cum[n], zn and MX.Snap(part.cont, pts[2 * n - 1], pts[2 * n], zn)
    or MX.GroundAt(part.cont, pts[2 * n - 1], pts[2 * n], last))
  -- (holes filled between the heights known; none known at all: no profile)
  local m = #s / 2
  local known = {}
  for k = 1, m do
    if s[2 * k] then known[#known + 1] = k end
  end
  if #known == 0 then return nil end
  for k = 1, m do
    if not s[2 * k] then
      local a, b
      for _, q in ipairs(known) do
        if q < k then a = q elseif not b then b = q end
      end
      if a and b then
        local t = (s[2 * k - 1] - s[2 * a - 1]) / max(1e-6, s[2 * b - 1] - s[2 * a - 1])
        s[2 * k] = s[2 * a] + (s[2 * b] - s[2 * a]) * t
      else
        s[2 * k] = s[2 * (a or b)]
      end
    end
  end
  local lo, hi = math.huge, -math.huge
  local up, down, ref = 0, 0, s[2]
  for k = 1, m do
    local z = s[2 * k]
    lo, hi = min(lo, z), max(hi, z)
    if z > ref + MX.NOISE_YD then
      up, ref = up + z - ref, z
    elseif z < ref - MX.NOISE_YD then
      down, ref = down + ref - z, z
    end
  end
  -- (the jumps: each run of drop or running-jump pieces, its top and its foot)
  local jumps = {}
  local i = 1
  while i <= n - 1 do
    if JumpKind(kinds[i]) then
      local f = i
      while JumpKind(kinds[f + 1]) and f + 1 <= n - 1 do f = f + 1 end
      local z0, z1 = MX.ZAlong(s, cum[i]), MX.ZAlong(s, cum[f + 1])
      local dz = kinds[i] == R().KIND_DROP and R().DropFall and R().DropFall(pts, kinds, i) or nil
      jumps[#jumps + 1] = { cum[i], cum[f + 1], z0, z1, dz or max(0, z0 - z1),
        kind = kinds[i] == R().KIND_JUMP and "jump" or "drop" }
      i = f + 1
    else
      i = i + 1
    end
  end
  if hi - lo < MX.PROFILE_MIN_RISE and #jumps == 0 then return nil end
  local p = { len = len, s = s, lo = lo, hi = hi, up = up, down = down, jumps = jumps }
  MX.Columns(p)
  return p
end
-- The height `d` yards along a profile's samples `s` (linear between them).
function MX.ZAlong(s, d)
  local m = #s / 2
  if d <= s[1] then return s[2] end
  for k = 2, m do
    if s[2 * k - 1] >= d then
      local d0, d1 = s[2 * k - 3], s[2 * k - 1]
      local t = d1 > d0 and (d - d0) / (d1 - d0) or 1
      return s[2 * k - 2] + (s[2 * k] - s[2 * k - 2]) * t
    end
  end
  return s[2 * m]
end
-- The profile's columns: its heights at PROFILE_COLS + 1 even steps (the drops kept: each column's lowest end where a
-- sample falls between), and each column's kind.
function MX.Columns(p)
  local M, s = MX.PROFILE_COLS, p.s
  local cols, kinds = {}, {}
  for j = 0, M do
    local d = p.len * j / M
    cols[j] = MX.ZAlong(s, d)
  end
  for j = 1, M do
    local d0, d1 = p.len * (j - 1) / M, p.len * j / M
    local kind
    for _, jp in ipairs(p.jumps) do
      if jp[1] < d1 and jp[2] > d0 then kind = "jump" break end
      if jp[1] == jp[2] and jp[1] >= d0 and jp[1] <= d1 then kind = "jump" break end
    end
    if not kind then
      local slope = (cols[j] - cols[j - 1]) / max(1e-6, d1 - d0)
      kind = slope > MX.SLOPE_FLAT and "up" or slope < -MX.SLOPE_FLAT and "down" or "flat"
    end
    kinds[j] = kind
  end
  p.cols, p.colKind = cols, kinds
  return p
end

-- The route part the strip shows and the yards along it the player is: the walk from the player kept whole by Nav
-- (r.fullFirst, r.consumed), else the first part from where they are.
function MX.ProfilePart(r)
  if not (r and r.parts) then return nil, 0 end
  if r.fullFirst then return r.fullFirst, r.consumed or 0 end
  return r.parts[1], 0
end

-- Whether map `G` shows the strip now: the option on, not the minimap square, a route with a profile.
-- (the map sent back to the minimap square, G.MinimapMode: too small for it, as the square's own map)
function MX.StripWanted(G, r)
  if G.square or S().heightProfile == false or (G.MinimapMode and G.MinimapMode()) then return nil end
  local part, at = MX.ProfilePart(r)
  local p = part and MX.Profile(part)
  if not p then return nil end
  return p, at
end

---------------------------------------------------------------------------------------------------- (b) jumps
-- What a jump `dz` yards down does at the Safe drop setting (Options > Routing, Nav.SafeDropSetting), in yards only
-- (the player's health is secret): the line and its color, or nil (no drop known).
function MX.HurtLine(dz)
  local N = ns.Nav
  if not (dz and N) then return nil end
  if UnitIsGhost and UnitIsGhost("player") then return L["No fall damage as a ghost."], 0.5, 1, 0.5 end
  local free = N.FALL_FREE or 14
  if dz <= free then return L["No fall damage."], 0.5, 1, 0.5 end
  local safe = N.SafeDropSetting and N.SafeDropSetting() or 39
  if dz <= safe then return Format(L["Some fall damage: within your safe drop (%s)."], Dist(safe)), 1, 0.82, 0.2 end
  return Format(L["Past your safe drop (%s): it hurts badly without a fall spell."], Dist(safe)), 1, 0.35, 0.3
end

-- The run of jump pieces that piece `i` of `part` is in: its first piece, its last piece.
function MX.JumpRun(part, i)
  local kinds = part and part.kinds
  if not (kinds and i and JumpKind(kinds[i])) then return nil end
  local a, b = i, i
  while a > 1 and kinds[a - 1] == kinds[i] do a = a - 1 end
  while kinds[b + 1] == kinds[i] do b = b + 1 end
  return a, b
end
-- Where a jump lands: its run's foot (world x, y), and how far it falls when the route's own heights say (the foot's
-- under the top), else nil.
function MX.JumpLanding(part, i)
  local a, b = MX.JumpRun(part, i)
  if not a then return nil end
  local pts = part.pts
  local x, y = pts[2 * (b + 1) - 1], pts[2 * (b + 1)]
  if not (x and y) then return nil end
  local z0, z1 = OwnZ(part, a), OwnZ(part, b + 1)
  return x, y, (z0 and z1) and (z0 - z1) or nil, a, b
end

-- The landing ring for map `G` (on G.markLayer, its screen units round the layer's middle): a ring of RING_SIDES lines
-- RING_PX across round the jump's foot, and the drop in yards beside it. `sg`: the hovered jump's seg (G.jumpSegs'),
-- nil to hide it.
MX.RING_SIDES, MX.RING_PX = 10, 7
MX.RING_COLOR = { 1, 0.82, 0.1 }
function MX.ShowLanding(G, sg, info)
  local st = G.mx
  if not st then return end
  local ring = st.ring
  if not sg or not G.markLayer then
    if ring and ring.shown then
      for _, l in ipairs(ring.lines) do l:Hide() end
      ring.label:Hide()
      ring.shown = false
    end
    return
  end
  -- (the run's foot on the screen: the end of its last piece's seg drawn, else straight on from this one's)
  local a, b = MX.JumpRun(sg.part, sg.i)
  if not a then return MX.ShowLanding(G, nil) end
  local fx, fy
  for k = 1, G.jumpSegN or 0 do
    local o = G.jumpSegs[k]
    if o.part == sg.part and o.i == b then fx, fy = o[3], o[4] end
  end
  if not fx then fx, fy = sg[3], sg[4] end
  if not ring then
    ring = { lines = {} }
    for k = 1, MX.RING_SIDES do
      local l = G.markLayer:CreateLine(nil, "OVERLAY", nil, 7)
      l:SetThickness(2)
      l:SetColorTexture(MX.RING_COLOR[1], MX.RING_COLOR[2], MX.RING_COLOR[3], 1)
      ring.lines[k] = l
    end
    ring.label = G.markLayer:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    ring.label:SetShadowOffset(1, -1)
    st.ring = ring
  end
  local r = MX.RING_PX
  for k = 1, MX.RING_SIDES do
    local a1, a2 = 2 * math.pi * (k - 1) / MX.RING_SIDES, 2 * math.pi * k / MX.RING_SIDES
    local l = ring.lines[k]
    l:SetStartPoint("CENTER", G.markLayer, fx + r * math.cos(a1), fy + r * math.sin(a1))
    l:SetEndPoint("CENTER", G.markLayer, fx + r * math.cos(a2), fy + r * math.sin(a2))
    l:Show()
  end
  local dz = info and info.dz
  ring.label:ClearAllPoints()
  ring.label:SetPoint("LEFT", G.markLayer, "CENTER", fx + r + 3, fy)
  ring.label:SetText(dz and Format(L["%s down"], Dist(dz)) or L["Lands here"])
  ring.label:Show()
  ring.shown, ring.x, ring.y = true, fx, fy
end

---------------------------------------------------------------------------------------------------- (c) floors
MX.FLOOR_GAP = 5.5 -- yards: surfaces further apart in height than this are two floors (an inn's stories are 6 to 7 yd
-- apart; the world grid's steep hillside cells hold two surfaces 4 or 5 yd apart, no floors over floors: a sweep of
-- Tirisfal round Brill had them in 2% of its cells at 4 yd, half that at 5.5)
MX.FLOOR_NEAR_OF = 2 -- a floor counts at a spot when at least this many of the 4 cells beside it have it too (a
-- cliff's top and foot in one cell aren't floors over floors: the cells across the edge have only one of them)
MX.FLOOR_MAX_ZOOM = 600 -- zoomed out past this (the map's half width in yards): no floor picker
MX.FLOOR_MOVE_YD = 2 -- the floors under the map's middle looked at again when it moved this far ...
MX.FLOOR_MIN_EVERY = 0.1 -- ... at most this often (a drag across the map) ...
MX.FLOOR_EVERY = 2 -- ... and this often standing still (a grid tile loaded meanwhile)
MX.PICK_KEEP_YD = 40 -- a floor picked holds while the map's middle stays this near where it was picked
MX.SPOT_HOLD_YD = 12 -- the picker stays while the map's middle is this near the last stacked spot (no blinking between
-- a room's stacked cells and its single ones, its stairs, a gap in the floor)

-- The heights at (x, y) of the grid that has the spot: the city grid's in a capital (or down in Undercity), else the
-- world grid's (its tile loaded already; no water's surface). { z, ... } (unsorted), the grid's cell size, its kind.
function MX.GridHeights(level, x, y)
  local CG, WG = ns.CityGrid, ns.WorldGrid
  local out = {}
  local name = CG and CG.CityFor and CG.CityFor(level, x, y)
  local c = name and CG.City and CG.City(name)
  if c and CG.SurfacesAt then
    for _, e in ipairs(CG.SurfacesAt(c, x, y)) do out[#out + 1] = e.z end
    return out, c.cell, "city"
  end
  local Geo = ns.Geo
  if not (Geo and Geo.Base and Geo.Base(level) == level) then return out, nil, nil end
  local w = WG and WG.On and WG.On() and WG.Cont and WG.Cont(level)
  if w and WG.SurfacesAt and MX.GridTileLoaded(w, x, y) then
    local ok, ss = pcall(WG.SurfacesAt, w, x, y)
    for _, e in ipairs(ok and ss or {}) do
      if (e.f or 0) % 2 == 0 then out[#out + 1] = e.z end -- (WorldGrid's F_SWIM: the water's surface)
    end
    return out, w.cell, "world"
  end
  return out, nil, nil
end
-- Heights grouped into floors: { lo, hi } bottom up, a new one past FLOOR_GAP.
function MX.Group(hs)
  table.sort(hs)
  local out = {}
  for _, h in ipairs(hs) do
    local f = out[#out]
    if f and h - f[2] <= MX.FLOOR_GAP then f[2] = h else out[#out + 1] = { h, h } end
  end
  return out
end
-- The floors over each other at (x, y) on `level` by the grids: { z, ... } bottom up (each floor's middle height), and
-- the grid's kind ("city", "world"); fewer than two: none (a single floor, or a cliff's top and foot side by side).
MX.floorLooks = 0 -- (the tests: spots looked at)
function MX.FloorsAt(level, x, y)
  if not (level and x and y) then return {}, nil end
  MX.floorLooks = MX.floorLooks + 1
  local hs, cell, kind = MX.GridHeights(level, x, y)
  if not cell then return {}, nil end
  local groups = MX.Group(hs)
  if #groups < 2 then return {}, kind end
  local near = {}
  for k, o in ipairs({ { cell, 0 }, { -cell, 0 }, { 0, cell }, { 0, -cell } }) do
    near[k] = (MX.GridHeights(level, x + o[1], y + o[2]))
  end
  local out = {}
  for _, g in ipairs(groups) do
    local z = (g[1] + g[2]) / 2
    local seen = 0
    for _, hs2 in ipairs(near) do
      for _, h in ipairs(hs2) do
        if h >= g[1] - MX.FLOOR_GAP and h <= g[2] + MX.FLOOR_GAP then
          seen = seen + 1
          break
        end
      end
    end
    if seen >= MX.FLOOR_NEAR_OF then out[#out + 1] = floor(z * 10 + 0.5) / 10 end
  end
  if #out < 2 then return {}, kind end
  return out, kind
end
-- The floor in `floors` (bottom up) nearest height `z` within FLOOR_GAP: its index, else nil.
function MX.FloorIndexOf(floors, z)
  if not z then return nil end
  local best, bd
  for k, f in ipairs(floors) do
    local d = abs(f - z)
    if d <= MX.FLOOR_GAP and (not bd or d < bd) then best, bd = k, d end
  end
  return best
end

-- A map's own state (G.mx): its strip, landing ring and floor picker.
function MX.New(G)
  return { G = G, spot = nil }
end

-- The floors at the map's middle, looked at again when it moved FLOOR_MOVE_YD (at most every FLOOR_MIN_EVERY), else
-- every FLOOR_EVERY: st.spot = { level,
-- x, y, floors, kind, at }, or nil where there are none (or the picker's off, the minimap square, zoomed far out).
function MX.LookFloors(st, level, x, y, zoom, now)
  local G = st.G
  if G.square or S().floorPicker == false or not (level and x) or (zoom and zoom > MX.FLOOR_MAX_ZOOM)
      or (G.MinimapMode and G.MinimapMode()) then
    st.spot, st.pick = nil, nil
    return nil
  end
  local sp = st.spot
  local look = st.lookAt
  if look and look.level == level and now - look.at < MX.FLOOR_EVERY
      and (now - look.at < MX.FLOOR_MIN_EVERY or (x - look.x) ^ 2 + (y - look.y) ^ 2 < MX.FLOOR_MOVE_YD ^ 2) then
    return sp
  end
  st.lookAt = { level = level, x = x, y = y, at = now }
  local floors, kind = MX.FloorsAt(level, x, y)
  -- (a pick holds near where it was made, with the same floors there)
  local pk = st.pick
  if pk and (pk.level ~= level or (x - pk.x) ^ 2 + (y - pk.y) ^ 2 > MX.PICK_KEEP_YD ^ 2) then st.pick = nil end
  if #floors < 2 then
    -- (between the floors' cells (a room's middle on one floor, its stairs): the last spot kept while the pick holds,
    -- or while the map's middle stays near it)
    if sp and sp.level == level and (st.pick or (x - sp.x) ^ 2 + (y - sp.y) ^ 2 <= MX.SPOT_HOLD_YD ^ 2) then return sp end
    st.spot = nil
    return nil
  end
  st.spot = { level = level, x = x, y = y, floors = floors, kind = kind, at = now }
  -- (a floor picked and not among these floors: dropped)
  if st.pick and st.pick.z and not MX.PickIndex(st) then st.pick = nil end
  return st.spot
end
-- The floor the tracker reports here (Nav.PlayerFloorZ on the spot's level, the player within PICK_KEEP_YD of it): its
-- index in the spot's floors, else nil.
function MX.YourFloor(st)
  local sp = st.spot
  local N = ns.Nav
  if not (sp and N and N.PlayerFloorZ) then return nil end
  local Geo = ns.Geo
  if not (Geo and Geo.PlayerWorld) then return nil end
  local px, py = Geo.PlayerWorld()
  if not px or (px - sp.x) ^ 2 + (py - sp.y) ^ 2 > MX.PICK_KEEP_YD ^ 2 then return nil end
  return MX.FloorIndexOf(sp.floors, N.PlayerFloorZ(sp.level))
end
-- The floor picked among the spot's floors (bottom up): the one nearest its height within 2 FLOOR_GAP, else nil.
function MX.PickIndex(st)
  local pk, sp = st.pick, st.spot
  if not (pk and pk.z and sp) then return nil end
  local best, bd
  for k, f in ipairs(sp.floors) do
    local d = abs(f - pk.z)
    if d <= 2 * MX.FLOOR_GAP and (not bd or d < bd) then best, bd = k, d end
  end
  return best
end
-- The floor shown: counted from the top (1 the top floor), 0 all of them; picked, else yours, else 0.
function MX.ShownFloor(st)
  local sp = st.spot
  if not sp then return 0 end
  local n = #sp.floors
  if st.pick then
    if not st.pick.z then return 0 end
    local i = MX.PickIndex(st)
    if i then return n - i + 1 end
  end
  local you = MX.YourFloor(st)
  return you and n - you + 1 or 0
end
-- "+" (up a floor; past the top: all of them) and "-" (down one). True when it changed.
function MX.FloorStep(st, up)
  local sp = st.spot
  if not sp then return false end
  local n = #sp.floors
  local k = MX.ShownFloor(st)
  if up then
    if k <= 0 then return false end
    k = k - 1
  else
    if k >= n then return false end
    k = k + 1
  end
  st.pick = { z = k > 0 and sp.floors[n - k + 1] or false, level = sp.level, x = sp.x, y = sp.y }
  return true
end
-- The height of the floor picked on `level` (false: "all floors" picked), or nil (none picked there: the tracker's).
function MX.PickedZ(st, level)
  local pk, sp = st and st.pick, st and st.spot
  if not (pk and sp and pk.level == level) then return nil end
  if not pk.z then return false end
  local i = MX.PickIndex(st)
  return i and sp.floors[i] or nil
end
-- The height a double-click at (x, y) on `level` means with a floor picked near: the grid's surface there nearest the
-- floor picked (within 2 FLOOR_GAP), else the floor's own height; nil with none picked, or the click far from it.
function MX.ClickZ(st, level, x, y)
  local z = MX.PickedZ(st, level)
  local pk = st and st.pick
  if not z or (x - pk.x) ^ 2 + (y - pk.y) ^ 2 > MX.PICK_KEEP_YD ^ 2 then return nil end
  local hs = MX.GridHeights(level, x, y)
  local best, bd
  for _, h in ipairs(hs) do
    local d = abs(h - z)
    if d <= 2 * MX.FLOOR_GAP and (not bd or d < bd) then best, bd = h, d end
  end
  return best or z
end
-- The floor picker's tooltip lines: the floors top down, the one shown highlighted, yours marked.
function MX.FloorLines(st)
  local sp = st.spot
  local out = {}
  if not sp then return out end
  local n = #sp.floors
  local shown, you = MX.ShownFloor(st), MX.YourFloor(st)
  for k = n, 1, -1 do
    local name = k == n and Format(L["%d (top)"], k) or k == 1 and Format(L["%d (ground)"], k) or tostring(k)
    local line = Format(L["%s: %s"], name, Dist(sp.floors[k]))
    if k == you then line = Format(L["%s (you)"], line) end
    out[#out + 1] = { line, n - k + 1 == shown }
  end
  return out
end

---------------------------------------------------------------------------------------------------- the widgets
MX.STRIP_H = 36 -- UI units: the strip's height
MX.STRIP_PAD = 3
MX.STRIP_TEXT_H = 12 -- (its text's row over the line)
MX.STRIP_SIDE = 44 -- UI units off each side of the map (the round buttons in its corners)
MX.STRIP_MIN_W = 90 -- a map narrower than this leaves the strip out
MX.STRIP_BOTTOM = 18 -- over the map's info line
MX.COLORS = { up = { 0.45, 1, 0.45 }, down = { 1, 0.65, 0.25 }, flat = { 0.75, 0.85, 1 }, jump = { 1, 0.4, 0.15 } }

-- Map G's widgets, made once: the strip on `top` (the layer over the map), the floor picker beside the dungeon floor
-- column `fl`, anchored under the same rules (G.PlaceFloorBar). `below`: { the info line, the dungeon's note, the
-- Confirm Route button } the strip sits over.
function MX.Make(G, top, below)
  local st = G.mx
  if not st or st.strip or G.square then return end
  st.below = below or {}
  local f = CreateFrame("Frame", nil, top)
  f:SetHeight(MX.STRIP_H)
  f:Hide()
  f:EnableMouse(true)
  local bg = f:CreateTexture(nil, "BACKGROUND")
  bg:SetAllPoints()
  bg:SetColorTexture(0, 0, 0, 0.45)
  f.bg = bg
  f.fills, f.lines, f.jumps = {}, {}, {}
  local text = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  text:SetPoint("TOPLEFT", MX.STRIP_PAD + 1, -1)
  text:SetShadowOffset(1, -1)
  f.text = text
  local dotEdge = f:CreateTexture(nil, "OVERLAY", nil, 6)
  dotEdge:SetSize(8, 8)
  dotEdge:SetColorTexture(0, 0, 0, 1)
  local dot = f:CreateTexture(nil, "OVERLAY", nil, 7)
  dot:SetSize(6, 6)
  dot:SetColorTexture(1, 1, 1, 1)
  dot:SetPoint("CENTER", dotEdge, "CENTER")
  f.dot, f.dotEdge = dot, dotEdge
  f:SetScript("OnEnter", function(self) MX.StripTip(G, self) end)
  f:SetScript("OnLeave", GameTooltip_Hide)
  st.strip = f

  local bar = CreateFrame("Frame", nil, top)
  bar:SetSize(30, 74)
  bar:Hide()
  local function Btn(label, tip, up)
    local ok, b = pcall(CreateFrame, "Button", nil, bar, "UIPanelButtonTemplate")
    if not ok then b = CreateFrame("Button", nil, bar) end
    b:SetSize(28, 24)
    b:SetText(label)
    b:SetScript("OnClick", function()
      if MX.FloorStep(st, up) then
        MX.RefreshFloorBar(G)
        if G.Redraw then G.Redraw() end
      end
    end)
    b:SetScript("OnEnter", function(self) MX.FloorTip(G, self, tip) end)
    b:SetScript("OnLeave", GameTooltip_Hide)
    return b
  end
  bar.up = Btn("+", L["Up a floor (all of them past the top one)"], true)
  bar.up:SetPoint("TOP", bar, "TOP", 0, 0)
  bar.count = bar:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  bar.count:SetPoint("TOP", bar.up, "BOTTOM", 0, -3)
  bar.count:SetShadowOffset(1, -1)
  bar.down = Btn("-", L["Down a floor"], false)
  bar.down:SetPoint("TOP", bar.count, "BOTTOM", 0, -3)
  st.bar = bar
end

function MX.FloorTip(G, owner, tip)
  local st = G.mx
  GameTooltip:SetOwner(owner, "ANCHOR_RIGHT")
  GameTooltip:SetText(tip or L["Floors here"], 1, 1, 1)
  for _, e in ipairs(MX.FloorLines(st)) do
    if e[2] then GameTooltip:AddLine(e[1], 1, 0.82, 0) else GameTooltip:AddLine(e[1], 0.7, 0.7, 0.7) end
  end
  GameTooltip:AddLine(L["The route on the floor picked shows full, the others fainter indoors; a stop you double-click here goes on that floor."], 0.8, 0.8, 0.8, true)
  GameTooltip:Show()
end

function MX.StripTip(G, owner)
  local st = G.mx
  local p = st and st.profile
  if not p then return end
  GameTooltip:SetOwner(owner, "ANCHOR_TOP")
  GameTooltip:SetText(L["Height profile"], 1, 1, 1)
  GameTooltip:AddLine(Format(L["To your next stop: up %s, down %s over %s."], Dist(p.up), Dist(p.down),
    Dist(p.len, true)), nil, nil, nil, true)
  GameTooltip:AddLine(Format(L["Highest %s, lowest %s."], Dist(p.hi), Dist(p.lo)), 0.8, 0.8, 0.8, true)
  if #p.jumps > 0 then
    GameTooltip:AddLine(Format(L["Jumps: %d (hover one on the map for where it lands)."], #p.jumps), 1, 0.55, 0.3, true)
  end
  GameTooltip:AddLine(L["Green climbs, orange drops; the dot is you. Turn it off in Options > Map."], 0.6, 0.6, 0.6, true)
  GameTooltip:Show()
end

-- The floor picker: shown with floors under the map's middle (and not over a dungeon's or a cave's own map, whose
-- column `fl` is), placed where that column goes.
function MX.RefreshFloorBar(G)
  local st = G.mx
  local bar = st and st.bar
  if not bar then return end
  local sp = st.spot
  local fl = G.FloorBar and G.FloorBar()
  local other = fl and fl.bar and fl.bar:IsShown()
  local on = sp ~= nil and not other and not (G.roadMode or G.wallMode)
  if not on then
    if bar:IsShown() then bar:Hide() end
    return
  end
  if not bar:IsShown() then
    if G.PlaceFloorBar then G.PlaceFloorBar() end -- (the dungeon column's spot, then ours on it)
    bar:ClearAllPoints()
    if fl and fl.bar then bar:SetPoint("TOPLEFT", fl.bar, "TOPLEFT", 0, 0) else bar:SetPoint("TOPLEFT", 8, -8) end
    bar:Show()
  end
  local n = #sp.floors
  local k = MX.ShownFloor(st)
  local you = MX.YourFloor(st)
  if k == 0 then
    bar.count:SetText(Format(L["All %d"], n))
    bar.count:SetTextColor(0.8, 0.8, 0.8)
  else
    bar.count:SetText(Format("%d/%d", n - k + 1, n))
    if you and n - you + 1 == k then bar.count:SetTextColor(1, 0.82, 0) else bar.count:SetTextColor(1, 1, 1) end
  end
  bar.up:SetEnabled(k > 0)
  bar.down:SetEnabled(k < n)
end

-- Lays the strip out for profile `p` (its columns and jumps; again only when the profile or the strip's size changed)
-- and moves the dot to `at` yards along.
function MX.LayStrip(f, p, at)
  local w, h = f:GetWidth() or 0, f:GetHeight() or MX.STRIP_H
  local pad = MX.STRIP_PAD
  local x0, x1 = pad, w - pad
  local y0, y1 = pad, h - MX.STRIP_TEXT_H
  local span = max(MX.PROFILE_MIN_RISE, p.hi - p.lo)
  local function X(d) return x0 + (x1 - x0) * d / p.len end
  local function Y(z) return y0 + (y1 - y0) * (z - p.lo) / span end
  local units = S().distanceUnits or "yards" -- (its text in the player's units)
  if f.laid ~= p or f.laidW ~= w or f.laidUnits ~= units then
    f.laid, f.laidW, f.laidUnits = p, w, units
    local M = MX.PROFILE_COLS
    for j = 1, M do
      local xa, xb = X(p.len * (j - 1) / M), X(p.len * j / M)
      local za, zb = p.cols[j - 1], p.cols[j]
      local c = MX.COLORS[p.colKind[j]] or MX.COLORS.flat
      local fill = f.fills[j]
      if not fill then
        fill = f:CreateTexture(nil, "BORDER")
        f.fills[j] = fill
      end
      fill:SetColorTexture(c[1], c[2], c[3], 0.22)
      fill:ClearAllPoints()
      fill:SetPoint("BOTTOMLEFT", f, "BOTTOMLEFT", xa, y0)
      fill:SetSize(max(1, xb - xa), max(1, Y(min(za, zb)) - y0))
      fill:Show()
      local l = f.lines[j]
      if not l then
        l = f:CreateLine(nil, "ARTWORK")
        l:SetThickness(2)
        f.lines[j] = l
      end
      l:SetColorTexture(c[1], c[2], c[3], 1)
      l:SetStartPoint("BOTTOMLEFT", f, xa, Y(za))
      l:SetEndPoint("BOTTOMLEFT", f, xb, Y(zb))
      l:Show()
    end
    for j = M + 1, #f.lines do
      f.lines[j]:Hide()
      f.fills[j]:Hide()
    end
    -- (each jump over its columns: from its top straight down to its foot, thicker)
    local c = MX.COLORS.jump
    for k, jp in ipairs(p.jumps) do
      local l = f.jumps[k]
      if not l then
        l = f:CreateLine(nil, "OVERLAY")
        l:SetThickness(3)
        f.jumps[k] = l
      end
      l:SetColorTexture(c[1], c[2], c[3], 1)
      local xa, xb = X(jp[1]), X(jp[2])
      if xb - xa < 2 then xb = xa + 2 end
      l:SetStartPoint("BOTTOMLEFT", f, xa, Y(jp[3]))
      local foot = jp[5] and jp[5] > 0 and jp[3] - jp[5] or jp[4]
      l:SetEndPoint("BOTTOMLEFT", f, xb, Y(max(p.lo, min(jp[4], foot))))
      l:Show()
    end
    for k = #p.jumps + 1, #f.jumps do f.jumps[k]:Hide() end
    f.text:SetText(Format(L["Up %s, down %s"], Dist(p.up), Dist(p.down)))
  end
  local d = max(0, min(p.len, at or 0))
  f.dotEdge:ClearAllPoints()
  f.dotEdge:SetPoint("CENTER", f, "BOTTOMLEFT", X(d), Y(MX.ZAlong(p.s, d)))
  f.dotAt = d
end

-- At each redraw of map G (the end of G.Update): the strip for the route now, the floor picker for the map's middle.
-- `level`, (x, y): what the map shows (G.shownLevel or the view's continent) and its middle; `zoom` its half width.
function MX.OnRedraw(G, r, level, x, y, zoom)
  local st = G.mx
  if not st then return end
  local now = GetTime and GetTime() or 0
  local f = st.strip
  if f then
    local p, at = MX.StripWanted(G, r)
    local parent = f:GetParent()
    local w = parent and parent:GetWidth() or 0
    if p and w - 2 * MX.STRIP_SIDE < MX.STRIP_MIN_W then p = nil end
    st.profile = p
    if not p then
      if f:IsShown() then
        f:Hide()
        f.text:SetText("") -- (nothing stale left: laid again, in the units then, when it shows)
        f.laid = nil
      end
    else
      -- (over the info line, the dungeon's note when it shows, Confirm Route when it shows)
      local b = st.below
      local over = b[1]
      if b[2] and b[2]:IsShown() then over = b[2] end
      if b[3] and b[3]:IsShown() then over = b[3] end
      if f.over ~= over or f.overW ~= w then
        f:ClearAllPoints()
        -- (the info line, the note and the button are all centered on the map)
        if over then
          f:SetPoint("BOTTOM", over, "TOP", 0, 3)
        else
          f:SetPoint("BOTTOM", parent, "BOTTOM", 0, MX.STRIP_BOTTOM)
        end
        f:SetWidth(w - 2 * MX.STRIP_SIDE)
        f.over, f.overW = over, w
      end
      if not f:IsShown() then f:Show() end
      MX.LayStrip(f, p, at)
    end
  end
  MX.LookFloors(st, level, x, y, zoom, now)
  MX.RefreshFloorBar(G)
end
