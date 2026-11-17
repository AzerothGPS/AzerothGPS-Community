-- The seamless map's engine (issue #61), part 1 of 5: its maths, the game's map geometry, and the texture machinery
-- every layer shares. The engine draws the whole world's map art under AzerothGPS's map (docs/atlas-spec.md); the
-- glue, Atlas/Atlas.lua, runs these files at login only while the seamless map is on (ns.AtlasChunks), each with
-- `D` its data (Atlas/Data) and `E` the engine's own table (ns.Atlas.core). Nothing global, nothing saved.
--
-- Coordinates: "world units" are the px of Azeroth's map art (uiMap 947, E.W x E.H, origin top left, y down); the
-- canvas the glue scales and moves is laid out in them, a unit a canvas unit. (u, v) is a world unit over E.W, E.H.
--
-- Textures are "sprites": plain records (a frame, a draw layer, a world rectangle, a file, texture coordinates,
-- masks) whose texture is made the first time it's wanted, anchored only while wanted (a pan or zoom lays out every
-- anchored region of a scaled frame, shown or not), and, for the zones' art, given its file through a queue a few
-- dozen a frame, fading in.
local _, ns = ...
ns.AtlasChunks = ns.AtlasChunks or {}
ns.AtlasChunks[#ns.AtlasChunks + 1] = { "engine/Base", function(D, E)

E.WORLD = 947
E.W, E.H = 1002, 668        -- (947's art layer, read again at the build)
E.TILE = 256                -- every map's art tiles, px
E.CONT_MAP = { [0] = 1415, [1] = 1414 } -- AzerothGPS's continents' maps
E.MAP_CONT = { [1415] = 0, [1414] = 1 }
E.ADT_YD = 1600 / 3         -- a minimap tile's side, yards
E.FILES_PER_FRAME = 40      -- lazy files given out a frame at most
E.FADE_IN = 0.3             -- seconds a lazy texture takes to fade in
E.broken = {}               -- a per-view part that raised: its first error (reported once)

local floor, max, min = math.floor, math.max, math.min

--------------------------------------------------------------------------------
-- Maths (pure: app/tests/test_atlas.py)
--------------------------------------------------------------------------------

-- 0 at a, 1 at b (either way round), eased between
function E.Smooth(a, b, x)
  if a == b then return x >= b and 1 or 0 end
  local t = (x - a) / (b - a)
  if t <= 0 then return 0 end
  if t >= 1 then return 1 end
  return t * t * (3 - 2 * t)
end

-- quantised steps: down to a twentieth, to the nearest fiftieth, to the nearest hundredth
function E.Floor20(x) return floor(x * 20 + 1e-7) / 20 end
function E.Round50(x) return floor(x * 50 + 0.5) / 50 end
function E.Round100(x) return floor(x * 100 + 0.5) / 100 end

-- the smallest power of two at least n (and 16): a piece's last file is that wide
function E.Pow2(n)
  local p = 16
  while p < n do p = p * 2 end
  return p
end

-- an octave split: log2(x / from) (0 at least) as its whole steps, the share into the next, and 2^steps
function E.Octave(x, from)
  local o = x > 0 and math.log(x / from) / math.log(2) or 0
  if o < 0 then o = 0 end
  local n = floor(o)
  return n, o - n, 2 ^ n
end

-- an art of w x h px in tiles of `tile` px: { col, row (from 0), px, py, pw, ph, tu, tv } row by row, tu/tv the
-- share of its file the tile's art fills (the file `tile` px, or with `pow2`, its own size's next power of two)
function E.Tiles(w, h, tile, pow2)
  local out = {}
  local cols, rows = math.ceil(w / tile), math.ceil(h / tile)
  for row = 0, rows - 1 do
    for col = 0, cols - 1 do
      local pw, ph = min(tile, w - col * tile), min(tile, h - row * tile)
      local fw, fh = tile, tile
      if pow2 then fw, fh = E.Pow2(pw), E.Pow2(ph) end
      out[#out + 1] = { col, row, col * tile, row * tile, pw, ph, pw / fw, ph / fh }
    end
  end
  return out
end

-- whether two boxes (x0, y0, x1, y1) meet
function E.Meets(a0, b0, a1, b1, c0, d0, c1, d1)
  return a0 < c1 and c0 < a1 and b0 < d1 and d0 < b1
end

-- the minimap tile (tx east, ty south) a spot in yards (x north, y west) is in
function E.TileAt(x, y)
  local T = E.ADT_YD
  return floor(32 - y / T), floor(32 - x / T)
end

-- the yards a run of minimap tiles covers, tx0..tx1 by ty0..ty1: its north-west corner (x, y) and south-east one
function E.TileYards(tx0, ty0, tx1, ty1)
  local T = E.ADT_YD
  return (32 - ty0) * T, (32 - tx0) * T, (31 - ty1) * T, (31 - tx1) * T
end

--------------------------------------------------------------------------------
-- The game's map geometry
--------------------------------------------------------------------------------

local rectOf, layerOf, spotOf = {}, {}, {}

local function Num(...)
  for i = 1, select("#", ...) do
    if type((select(i, ...))) ~= "number" then return false end
  end
  return true
end

-- a map's rectangle on Azeroth's map: l, r, t, b in (u, v), or nil (asked once a map)
function E.MapRect(map)
  if map == E.WORLD then return 0, 1, 0, 1 end
  local r = rectOf[map]
  if r == nil then
    r = false
    if C_Map and C_Map.GetMapRectOnMap then
      local ok, l, rt, t, b = pcall(C_Map.GetMapRectOnMap, map, E.WORLD)
      if ok and Num(l, rt, t, b) and rt > l and b > t then r = { l, rt, t, b } end
    end
    rectOf[map] = r
  end
  if r then return r[1], r[2], r[3], r[4] end
  return nil
end

-- a map's first art layer: { w, h } px, or nil (asked once a map)
function E.ArtLayer(map)
  local a = layerOf[map]
  if a == nil then
    a = false
    if C_Map and C_Map.GetMapArtLayers then
      local ok, list = pcall(C_Map.GetMapArtLayers, map)
      local l1 = ok and type(list) == "table" and list[1]
      if type(l1) == "table" and Num(l1.layerWidth, l1.layerHeight) and l1.layerWidth > 0 and l1.layerHeight > 0 then
        a = { l1.layerWidth, l1.layerHeight }
      end
    end
    layerOf[map] = a
  end
  return a or nil
end

-- where a map's art px go in world units: x = x0 + px * sx, y = y0 + py * sy; nil off Azeroth's map
function E.Spot(map)
  local s = spotOf[map]
  if s == nil then
    s = false
    local l, r, t, b = E.MapRect(map)
    local a = E.ArtLayer(map)
    local aw, ah = a and a[1] or 1002, a and a[2] or 668
    if l then s = { l * E.W, t * E.H, (r - l) * E.W / aw, (b - t) * E.H / ah, aw, ah } end
    spotOf[map] = s
  end
  return s or nil
end

-- a map's base art files, row by row: its cleaned tiles (D.CleanArt) over the client's own
function E.ArtFiles(map)
  local out = {}
  if C_Map and C_Map.GetMapArtLayerTextures then
    local ok, list = pcall(C_Map.GetMapArtLayerTextures, map, 1)
    if ok and type(list) == "table" then
      for i, f in ipairs(list) do out[i] = f end
    end
  end
  for _, i in ipairs(D.CleanArt and D.CleanArt[map] or {}) do out[i] = E.Tex("MapArt", map .. "_" .. i) end
  return out
end

-- forget the cached geometry (a rebuild, the tests)
function E.ForgetMaps()
  rectOf, layerOf, spotOf = {}, {}, {}
  E.proj = {}
end

--------------------------------------------------------------------------------
-- Yards and (u, v): the projection
--------------------------------------------------------------------------------

E.proj = {}
E.SPOT_CHECK = { 0, -8840.6, 489.7, 1429, 1453 } -- Stormwind's flight master, in Elwynn or Stormwind City

-- a map position's world spot (X north, Y west), or nil
local function Corner(map, mx, my)
  if not (C_Map and C_Map.GetWorldPosFromMapPos and CreateVector2D) then return nil end
  local ok, _, vec = pcall(C_Map.GetWorldPosFromMapPos, map, CreateVector2D(mx, my))
  if not ok or type(vec) ~= "table" then return nil end
  local a, b
  if vec.GetXY then
    local ok2, x, y = pcall(vec.GetXY, vec)
    if ok2 then a, b = x, y end
  else
    a, b = vec.x, vec.y
  end
  if not Num(a, b) then return nil end
  return a, b
end

-- a continent's projection { X0, Y0, X1, Y1, l, r, t, b, swap }: its map's corners in world yards and its rectangle on
-- the world; false where the game won't say
local function Projection(cont)
  local p = E.proj[cont]
  if p ~= nil then return p end
  p = false
  local map = E.CONT_MAP[cont]
  if map then
    local X0, Y0 = Corner(map, 0, 0)
    local X1, Y1 = Corner(map, 1, 1)
    local l, r, t, b = E.MapRect(map)
    if X0 and X1 and l and X0 ~= X1 and Y0 ~= Y1 then p = { X0, Y0, X1, Y1, l, r, t, b, swap = false } end
  end
  E.proj[cont] = p
  -- the axes checked once with a known spot: only if the swapped reading alone puts it in its zone, that one
  local c = E.SPOT_CHECK
  if p and cont == c[1] then
    local function Inside(u, v)
      for i = 4, 5 do
        local l, r, t, b = E.MapRect(c[i])
        if l and u >= l and u <= r and v >= t and v <= b then return true end
      end
      return false
    end
    local plain = Inside(E.YardsToUV(cont, c[2], c[3]))
    p.swap = true
    local swapped = Inside(E.YardsToUV(cont, c[2], c[3]))
    p.swap = swapped and not plain
  end
  return p
end
E.Projection = Projection

-- AzerothGPS's yards (x north, y west) on continent 0 or 1 to (u, v); nil where the game won't say
function E.YardsToUV(cont, x, y)
  local p = Projection(cont)
  if not p then return nil end
  local across, down
  if p.swap then
    across, down = (p[1] - x) / (p[1] - p[3]), (p[2] - y) / (p[2] - p[4])
  else
    across, down = (p[2] - y) / (p[2] - p[4]), (p[1] - x) / (p[1] - p[3])
  end
  return p[5] + across * (p[6] - p[5]), p[7] + down * (p[8] - p[7])
end

-- and back
function E.UVToYards(cont, u, v)
  local p = Projection(cont)
  if not p then return nil end
  local across, down = (u - p[5]) / (p[6] - p[5]), (v - p[7]) / (p[8] - p[7])
  if p.swap then
    return p[1] - across * (p[1] - p[3]), p[2] - down * (p[2] - p[4])
  end
  return p[1] - down * (p[1] - p[3]), p[2] - across * (p[2] - p[4])
end

-- the maps at (u, v), from the world down: { 947, continent, zone }
function E.ChainAt(u, v)
  local chain = { E.WORLD }
  local cur, x, y = E.WORLD, u, v
  local T = Enum and Enum.UIMapType
  for _ = 1, 4 do
    if not (C_Map and C_Map.GetMapInfoAtPosition and C_Map.GetMapRectOnMap and T) then break end
    local ok, info = pcall(C_Map.GetMapInfoAtPosition, cur, x, y)
    local id = ok and type(info) == "table" and info.mapID
    if not id or id == cur or (info.mapType ~= T.Continent and info.mapType ~= T.Zone) then break end
    local ok2, l, r, t, b = pcall(C_Map.GetMapRectOnMap, id, cur)
    if not (ok2 and Num(l, r, t, b) and r > l and b > t) then break end
    x, y = (x - l) / (r - l), (y - t) / (b - t)
    chain[#chain + 1] = id
    cur = id
  end
  return chain
end

--------------------------------------------------------------------------------
-- Parts run apart: one failing (a client difference) never stops the others, and is reported once
--------------------------------------------------------------------------------

function E.Guard(name, fn, ...)
  local ok, err = pcall(fn, ...)
  if not ok and not E.broken[name] then
    E.broken[name] = tostring(err)
    local h = geterrorhandler and geterrorhandler()
    if h then pcall(h, "AzerothGPS seamless map (" .. name .. "): " .. tostring(err)) end
  end
  return ok
end

--------------------------------------------------------------------------------
-- Textures: files, masks, sprites
--------------------------------------------------------------------------------

-- a shipped texture's path: Tex("MapBand", 1411) is Media\Textures\MapBand\1411
function E.Tex(name, sub)
  if sub ~= nil then return E.TEX .. name .. "\\" .. sub end
  return E.TEX .. name
end

-- a frame of the art, `off` levels over the engine's base level (parent: the canvas, or another layer)
function E.NewLayer(off, parent)
  local f = CreateFrame("Frame", nil, parent or E.canvas)
  f:SetFrameLevel(E.L + off)
  f:SetSize(E.W, E.H)
  f:SetPoint("TOPLEFT", E.canvas, "TOPLEFT", 0, 0)
  E.frames[#E.frames + 1] = f
  return f
end

-- a mask: a file stretched over a world rectangle, for the textures of one frame. Made when first used.
function E.NewMask(frame, file, x, y, w, h)
  return { frame = frame, file = file, x = x, y = y, w = w, h = h }
end

local function MaskObject(mk)
  local m = mk.obj
  if not m then
    m = mk.frame:CreateMaskTexture()
    m:SetTexture(mk.file, "CLAMPTOBLACKADDITIVE", "CLAMPTOBLACKADDITIVE")
    mk.obj = m
  end
  if not mk.placed then
    m:SetPoint("TOPLEFT", mk.frame, "TOPLEFT", mk.x, -mk.y)
    m:SetSize(mk.w, mk.h)
    mk.placed = true
  end
  return m
end
E.MaskObject = MaskObject

-- a mask no texture near the view uses: unanchored, so pans don't lay it out
function E.ParkMask(mk)
  if mk.obj and mk.placed then
    mk.obj:ClearAllPoints()
    mk.placed = false
  end
end

-- A sprite: { frame, layer, sub, x, y, w, h, file, tc = { l, r, t, b }, masks, wrap, lazy, desat, vc = { r, g, b },
-- va (its vertex alpha) }. Its texture is made the first time it's wanted.
local function Paint(sp)
  local t = sp.tex
  if not t then return end
  local c = sp.vc
  if c then t:SetVertexColor(c[1], c[2], c[3], sp.va or 1) else t:SetVertexColor(1, 1, 1, sp.va or 1) end
  local d = sp.desat or 0
  if t.SetDesaturation then t:SetDesaturation(d) else t:SetDesaturated(d > 0) end
end
E.Paint = Paint

local function GiveFile(sp)
  local t = sp.tex
  if sp.wrap then
    t:SetTexture(sp.file, "REPEAT", "REPEAT", "LINEAR")
  else
    t:SetTexture(sp.file, nil, nil, "LINEAR")
  end
  sp.ready = true
end
E.GiveFile = GiveFile

local function Make(sp)
  local t = sp.frame:CreateTexture(nil, sp.layer or "ARTWORK", nil, sp.sub or 0)
  sp.tex = t
  for _, mk in ipairs(sp.masks or {}) do t:AddMaskTexture(MaskObject(mk)) end
  local c = sp.tc
  if c then t:SetTexCoord(c[1], c[2], c[3], c[4]) end
  Paint(sp)
  t:Hide()
  if not sp.lazy then GiveFile(sp) end
  return t
end
E.MakeTexture = Make

-- anchor a sprite's texture over its rectangle (again: it moved)
function E.Anchor(sp)
  local t = sp.tex or Make(sp)
  t:ClearAllPoints()
  t:SetPoint("TOPLEFT", sp.frame, "TOPLEFT", sp.x, -sp.y)
  t:SetSize(sp.w, sp.h)
  sp.placed = true
end

-- a sprite wanted on screen: made, anchored, shown once it has its file (a lazy one queued for it)
function E.Want(sp)
  if not sp.placed then
    for _, mk in ipairs(sp.masks or {}) do if not mk.placed and mk.obj then MaskObject(mk) end end
    E.Anchor(sp)
  end
  if sp.ready then
    if not sp.on then
      sp.tex:Show()
      sp.on = true
    end
  elseif not sp.queued then
    sp.queued = true
    local q = E.queue
    q[#q + 1] = sp
    E.Wake()
  end
end

-- a sprite not wanted: hidden and unanchored
function E.Drop(sp)
  if sp.placed then
    sp.tex:Hide()
    sp.tex:ClearAllPoints()
    sp.placed, sp.on = false, false
  end
end

--------------------------------------------------------------------------------
-- The loading queue and fades: a frame of its own, run only while there's work
--------------------------------------------------------------------------------

E.queue, E.fades = {}, {}
E.qHead = 1

function E.Wake()
  local d = E.driver
  if d and not d:IsShown() then d:Show() end
end

-- the queue's next files (at most FILES_PER_FRAME a frame), each fading in from 0; true while anything is left
function E.Pump(now)
  local q, given = E.queue, 0
  while E.qHead <= #q and given < E.FILES_PER_FRAME do
    local sp = q[E.qHead]
    q[E.qHead] = false
    E.qHead = E.qHead + 1
    sp.queued = false
    if sp.placed and not sp.ready then -- (still wanted)
      GiveFile(sp)
      sp.tex:SetAlpha(0)
      sp.tex:Show()
      sp.on = true
      E.fades[sp] = now
      given = given + 1
    end
  end
  if E.qHead > #q then
    E.queue, E.qHead = {}, 1
  end
  local busy = false
  for sp, t0 in pairs(E.fades) do
    local a = E.Smooth(0, E.FADE_IN, now - t0)
    sp.tex:SetAlpha(a)
    if a >= 1 then E.fades[sp] = nil else busy = true end
  end
  return busy or E.qHead <= #E.queue
end

-- whether files are still coming in or fading
function E.Loading()
  return E.qHead <= #E.queue or next(E.fades) ~= nil
end

end }
