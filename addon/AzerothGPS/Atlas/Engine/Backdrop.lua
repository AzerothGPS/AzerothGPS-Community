-- The seamless map's engine, part 2 of 5: the backdrop under the zones (docs/atlas-spec.md, 6.1 to 6.7): the sea
-- past the world, the seas' colour fields and their mottling, the world's and the continents' own art (muted as the
-- zones come in), the coasts' hatching, the land's colour and grain, and the land no zone map covers (blank paper and
-- the client's finer maps of it).
local _, ns = ...
ns.AtlasChunks = ns.AtlasChunks or {}
ns.AtlasChunks[#ns.AtlasChunks + 1] = { "engine/Backdrop", function(D, E)

E.SEA_REACH = 1.5            -- the sea goes on this many world sizes past the art
E.SEA_BOX = 1.8              -- the mottling and hatching laid over this many half views round the middle,
E.SEA_KEEP = 1.2             -- and laid again once this many no longer fit in it
E.GRAIN_PERIOD = 14          -- the land's grain: world units a repeat (the second octave GOLDEN times that)
E.GOLDEN = 2.618
E.LAND_TINT = { 0.96, 0.92, 0.84 }

local Smooth, Tex, NewMask = E.Smooth, E.Tex, E.NewMask

-- a sprite (Base.lua) made at the build: its file set then, anchored when first wanted
local function Static(frame, layer, sub, file, x, y, w, h, masks, extra)
  local sp = { frame = frame, layer = layer, sub = sub, file = file, x = x, y = y, w = w, h = h, masks = masks,
    tc = { 0, 1, 0, 1 } }
  for k, v in pairs(extra or {}) do sp[k] = v end
  E.MakeTexture(sp)
  return sp
end
E.Static = Static

-- a map's art tiles as sprites over its rectangle (each through `masks`); files 0 or missing skipped
function E.ArtSprites(frame, layer, sub, map, files, masks, spot, list)
  local s = spot or E.Spot(map)
  list = list or {}
  if not s then return list end
  for i, tl in ipairs(E.Tiles(s[5], s[6], E.TILE)) do
    local f = files[i]
    if f and f ~= 0 then
      local sp = { frame = frame, layer = layer, sub = sub, file = f, masks = masks,
        x = s[1] + tl[3] * s[3], y = s[2] + tl[4] * s[4], w = tl[5] * s[3], h = tl[6] * s[4],
        tc = { 0, tl[7], 0, tl[8] } }
      list[#list + 1] = sp
    end
  end
  return list
end

-- a mask over a map's whole rectangle
function E.MapMask(frame, file, map)
  local s = E.Spot(map)
  if not s then return nil end
  return NewMask(frame, file, s[1], s[2], s[5] * s[3], s[6] * s[4])
end

local function ShowAll(list)
  for _, sp in ipairs(list) do
    if not sp.tex then E.MakeTexture(sp) end
    E.Want(sp)
  end
end

-- the continents on Azeroth's map with art of their own (their masks are shipped for these)
function E.Continents()
  local out = {}
  local T = Enum and Enum.UIMapType
  if C_Map and C_Map.GetMapChildrenInfo and T then
    local ok, kids = pcall(C_Map.GetMapChildrenInfo, E.WORLD, T.Continent, true)
    for _, k in ipairs(ok and type(kids) == "table" and kids or {}) do
      if E.MAP_CONT[k.mapID] and E.Spot(k.mapID) then out[#out + 1] = k.mapID end
    end
  end
  return out
end

--------------------------------------------------------------------------------
-- The build
--------------------------------------------------------------------------------

function E.BuildBackdrop()
  local W, H, R = E.W, E.H, E.SEA_REACH
  local f0, f1 = E.layer[0], E.layer[1]
  local bd = { world = {}, worldSea = {}, coast = {}, contLand = {}, contSea = {}, hatch = {}, fill = {}, grain = {},
    paper = {}, octaves = {} }
  E.bd = bd
  -- the sea past the world: its colour, and the mottling at the sea's first octave
  local ek = E.Spot(1415)
  E.P0 = 128 * (ek and ek[3] or 0.4)
  local x0, y0, x1, y1 = -R * W, -R * H, (1 + R) * W, (1 + R) * H
  ShowAll({ Static(f0, "BACKGROUND", -8, Tex("MapSeaFieldOut"), x0, y0, x1 - x0, y1 - y0) })
  for _, name in ipairs({ "MapSeaDark", "MapSeaLight" }) do
    local sp = Static(f0, "BACKGROUND", -7, Tex(name), x0, y0, x1 - x0, y1 - y0, nil, { wrap = true })
    sp.tex:SetTexCoord(x0 / E.P0, x1 / E.P0, y0 / E.P0, y1 / E.P0)
    ShowAll({ sp })
  end
  local conts = E.Continents()
  E.conts = conts
  -- the seas' colour fields, each through the wide feather
  for _, map in ipairs({ E.WORLD, conts[1], conts[2] }) do
    local s = E.Spot(map)
    if s then
      local mk = E.MapMask(f0, Tex("MapFeatherWide"), map)
      ShowAll({ Static(f0, "BACKGROUND", map == E.WORLD and -6 or -5, Tex("MapSeaField", map), s[1], s[2],
        s[5] * s[3], s[6] * s[4], { mk }) })
    end
  end
  -- the mottling's octaves round the view (E.LaySea)
  for i, name in ipairs({ "MapSeaDark", "MapSeaLight", "MapSeaDark", "MapSeaLight" }) do
    bd.octaves[i] = Static(f0, "BACKGROUND", i - 5, Tex(name), 0, 0, 1, 1, nil, { wrap = true })
  end
  -- the world's art in three parts: its land and coastal band, its open sea, the sea just off its coasts
  local feather = E.MapMask(f0, Tex("MapFeatherWide"), E.WORLD)
  local files = E.ArtFiles(E.WORLD)
  E.ArtSprites(f0, "BACKGROUND", 0, E.WORLD, files, { feather, E.MapMask(f0, Tex("MapBackLand", E.WORLD), E.WORLD) },
    nil, bd.world)
  E.ArtSprites(f0, "BACKGROUND", 0, E.WORLD, files, { feather, E.MapMask(f0, Tex("MapSeaOpen", E.WORLD), E.WORLD) },
    nil, bd.worldSea)
  E.ArtSprites(f0, "BACKGROUND", 0, E.WORLD, files, { feather, E.MapMask(f0, Tex("MapSeaCoast", E.WORLD), E.WORLD) },
    nil, bd.coast)
  -- each continent: its sea past the world art's edges (with the world's sea), its own art, hatching, land, grain
  for _, map in ipairs(conts) do
    local s = E.Spot(map)
    local art = E.ArtFiles(map)
    E.ArtSprites(f0, "BACKGROUND", 0, map, art, { E.MapMask(f0, Tex("MapSeaOut", map), map) }, s, bd.worldSea)
    local wide = E.MapMask(f1, Tex("MapFeatherWide"), map)
    E.ArtSprites(f1, "ARTWORK", 0, map, art, { wide, E.MapMask(f1, Tex("MapBackLand", map), map) }, s, bd.contLand)
    E.ArtSprites(f1, "ARTWORK", 0, map, art, { wide, E.MapMask(f1, Tex("MapSeaMask", map), map) }, s, bd.contSea)
    local coast = E.MapMask(f1, Tex("MapCoast", map), map)
    for k = 1, 2 do
      bd.hatch[#bd.hatch + 1] = Static(f1, "ARTWORK", 1, Tex("MapHatch"), 0, 0, 1, 1, { coast },
        { wrap = true, map = map, k = s[3], half = k == 2 })
    end
    local cw, ch = s[5] * s[3], s[6] * s[4]
    bd.fill[#bd.fill + 1] = Static(f1, "ARTWORK", 2, Tex("MapLand", map), s[1], s[2], cw, ch, { wide },
      { vc = E.LAND_TINT, desat = 0.25 })
    local land = E.MapMask(f1, Tex("MapLand", map), map)
    for k = 1, 2 do
      local period = E.GRAIN_PERIOD * (k == 2 and E.GOLDEN or 1)
      local off = k == 2 and 0.37 or 0
      local sp = Static(f1, "ARTWORK", 6, Tex("MapGrain"), s[1], s[2], cw, ch, { wide, land },
        { wrap = true, va = k == 2 and 0.5 or 0.55 })
      sp.tex:SetTexCoord(off, off + cw / period, 1.7 * off, 1.7 * off + ch / period)
      bd.grain[#bd.grain + 1] = sp
    end
    E.BuildPaper(map, s, wide)
  end
  for _, list in ipairs({ bd.world, bd.worldSea, bd.coast, bd.contLand, bd.contSea, bd.fill, bd.grain }) do
    ShowAll(list)
  end
  E.BuildGapArt()
  bd.mute = nil
end

-- the blank paper over a continent's land no zone map covers: two repeats of it a square (D.Unmapped)
function E.BuildPaper(map, s, wide)
  local u = D.Unmapped
  local list = u and u[map]
  if not list then return end
  local tile, period = u.tile or 64, u.paper or 21.62
  for i = 1, #list - 2, 3 do
    local col, row = list[i], list[i + 1]
    local x, y = s[1] + col * tile, s[2] + row * tile
    local mk = NewMask(E.layer[1], Tex("MapGapLand", map .. "_" .. col .. "_" .. row), x, y, tile, tile)
    for k = 1, 2 do
      local p = period * (k == 2 and E.GOLDEN or 1)
      local off = k == 2 and 0.41 or 0
      local sp = Static(E.layer[1], "ARTWORK", 2 + k, Tex("MapPaper"), x, y, tile, tile, { mk, wide },
        { wrap = true, va = k == 2 and 0.5 or 1 })
      sp.tex:SetTexCoord(x / p + off, (x + tile) / p + off, y / p + 1.7 * off, (y + tile) / p + 1.7 * off)
      E.bd.paper[#E.bd.paper + 1] = sp
    end
  end
end

-- the client's finer maps of land no zone covers, each through its own mask (D.Unmapped.art)
function E.BuildGapArt()
  E.gapArt = {}
  local f = E.layer[2]
  for _, a in ipairs(D.Unmapped and D.Unmapped.art or {}) do
    local rc = a[3]
    local x, y = rc[1] * E.W, rc[3] * E.H
    local w, h = (rc[2] - rc[1]) * E.W, (rc[4] - rc[3]) * E.H
    local spot = { x, y, w / 1002, h / 668, 1002, 668 }
    local mk = NewMask(f, Tex("MapCoastArt", a[1]), x, y, w, h)
    local block = { x0 = x, y0 = y, x1 = x + w, y1 = y + h, sprites = E.ArtSprites(f, "ARTWORK", 0, nil, a[4], { mk },
      spot) }
    for _, sp in ipairs(block.sprites) do E.MakeTexture(sp) end
    E.gapArt[#E.gapArt + 1] = block
  end
end

--------------------------------------------------------------------------------
-- Colour by zoom
--------------------------------------------------------------------------------

-- a list's alpha (not again unchanged): hidden and unanchored at none
local function SetAlpha(list, a)
  if list.alpha == a then return end
  list.alpha = a
  for _, sp in ipairs(list) do
    if a <= 0.003 then
      E.Drop(sp)
    else
      E.Want(sp)
      sp.tex:SetAlpha(a)
    end
  end
end

-- the world's and continents' art muted as the zones come in: m the mute, sm the continents' open sea going, wo the
-- world's land going, ws its open sea, wc its coasts (each in steps of a twentieth: recoloured only on a step)
function E.TintBackdrop(m, sm, wo, ws, wc)
  local bd = E.bd
  if bd.mute ~= m then
    bd.mute = m
    local c = 1 - 0.45 * m
    local tint, desat = { c, 0.97 * c, 0.92 * c }, 0.8 * m
    for _, list in ipairs({ bd.world, bd.contLand, bd.contSea }) do
      for _, sp in ipairs(list) do
        sp.vc, sp.desat = tint, desat
        E.Paint(sp)
      end
    end
  end
  SetAlpha(bd.world, (1 - 0.92 * m) * (1 - wo))
  SetAlpha(bd.worldSea, 1 - ws)
  SetAlpha(bd.coast, 1 - wc)
  SetAlpha(bd.contLand, 1 - 0.92 * m)
  SetAlpha(bd.contSea, (1 - 0.92 * m) * (1 - sm))
end

-- the land's colour and grain: up with the mute (and a cave surfacing); the paper at the zones' detail
function E.LandAlpha(a, d)
  local bd = E.bd
  if bd.landA ~= a then
    bd.landA = a
    SetAlpha(bd.fill, a)
    SetAlpha(bd.grain, a)
  end
  if bd.paperD ~= d then
    bd.paperD = d
    for _, sp in ipairs(bd.paper) do sp.tex:SetAlpha(d) end
  end
end

--------------------------------------------------------------------------------
-- By the view: the mottling's octaves and the coasts' hatching round it
--------------------------------------------------------------------------------

-- a repeat over a box: anchored there, its pattern fixed to the world
local function Lay(sp, x0, y0, x1, y1, px, py, su, sv, a)
  if a <= 0.01 or x1 <= x0 or y1 <= y0 then
    E.Drop(sp)
    return
  end
  sp.x, sp.y, sp.w, sp.h = x0, y0, x1 - x0, y1 - y0
  E.Anchor(sp)
  sp.tex:SetTexCoord(x0 / px + su, x1 / px + su, y0 / py + sv, y1 / py + sv)
  sp.tex:SetAlpha(a)
  if not sp.on then
    sp.tex:Show()
    sp.on = true
  end
end

-- the sea's strength ms (as the world's own sea goes), its box round the view (u, v, hu, hv) and zoom zd
function E.LaySea(u, v, hu, hv, zd, ms)
  local bd, W, H = E.bd, E.W, E.H
  local box = bd.seaBox
  local k = E.SEA_KEEP
  if box and box.zd == zd and box.ms == ms and u - k * hu >= box.u0 and u + k * hu <= box.u1
    and v - k * hv >= box.v0 and v + k * hv <= box.v1 then
    return
  end
  local b = E.SEA_BOX
  box = { zd = zd, ms = ms, u0 = u - b * hu, u1 = u + b * hu, v0 = v - b * hv, v1 = v + b * hv }
  bd.seaBox = box
  local x0, y0, x1, y1 = box.u0 * W, box.v0 * H, box.u1 * W, box.v1 * H
  local n, f, div = E.Octave(zd, 4)
  local size = E.P0 / div
  for i, sp in ipairs(bd.octaves) do
    local fine = i > 2
    local period = fine and size / 2 or size
    local shift = (0.37 * (fine and n + 1 or n)) % 1
    Lay(sp, x0, y0, x1, y1, period, period, shift, 1.6 * shift, ms * (fine and f or 1 - f))
  end
  local hn, hf, hdiv = E.Octave(zd, 7)
  for _, sp in ipairs(bd.hatch) do
    local s = E.Spot(sp.map)
    local cx0, cy0 = math.max(x0, s[1]), math.max(y0, s[2])
    local cx1, cy1 = math.min(x1, s[1] + s[5] * s[3]), math.min(y1, s[2] + s[6] * s[4])
    local px, py = 34 * sp.k / hdiv, 84 * sp.k / hdiv
    local a = 0.6 * ms * math.sqrt(1 - hf)
    if sp.half then px, py, a = px / 2, py / 2, 0.6 * ms * math.sqrt(hf) end
    Lay(sp, cx0, cy0, cx1, cy1, px, py, 0, 0, a)
  end
  return hn
end

end }
