-- The seamless map's engine, part 3 of 5: the zones (docs/atlas-spec.md, 6.6 to 6.12, 8.1, 9): every zone's base art
-- and explorable pieces, live, with their border colour match, interiors and close-up blur; the same pre-rendered as
-- world tiles (drawn instead whenever the settings are the ones they were rendered at); the capitals and their
-- banners; which pieces the character has explored.
--
-- Each zone is a group: its sprites (Base.lua) and masks, kept unanchored while the zone is away from the view. A
-- sprite's `kind` says when it's wanted: "live" (the live layers on), "blur" (its zone blurred). Pieces' sprites carry
-- their piece (hidden unexplored with "hide"), border copies `tinted` (shown while the colour match is).
local _, ns = ...
ns.AtlasChunks = ns.AtlasChunks or {}
ns.AtlasChunks[#ns.AtlasChunks + 1] = { "engine/Zones", function(D, E)

E.ZONE_LEVELS = { 3, 63 }     -- the zones' base art: the largest at +3, each smaller one a level higher, up to +63
E.LEVEL_OVERLAY, E.LEVEL_INNER, E.LEVEL_BAKED = 64, 65, 65
E.LEVEL_BLUR = 66             -- the blur's parent; its four copies over it
E.LEVEL_CITY, E.LEVEL_CITY_UNDER = 71, 75
E.LEVEL_BANNER = 77
E.UNDERGROUND = { [1458] = true, [1455] = true } -- (Undercity, Ironforge: over the minimap's detail)
E.NO_EDGE = { [2521] = true } -- (graded, but no frame mask of its own shipped: the thin feather)
E.CITY_FADE = { [1454] = { 0.08, 0.25 }, [1456] = { 0.08, 0.25 } } -- (else E.CITY_FADE_DEFAULT; times its zoom)
E.CITY_FADE_DEFAULT = { 0.2, 0.4 }
E.BLUR_TAP = 0.6              -- art px each blur copy is shifted, diagonally

local Tex, NewMask = E.Tex, E.NewMask

--------------------------------------------------------------------------------
-- Pieces and what's explored
--------------------------------------------------------------------------------

local function PieceKey(w, h, x, y)
  return string.format("%d:%d:%d:%d", w, h, x, y)
end
E.PieceKey = PieceKey

-- "w:h:x:y" back to its numbers
function E.ParseKey(key)
  local w, h, x, y = string.match(key, "^(%d+):(%d+):(%d+):(%d+)$")
  return tonumber(w), tonumber(h), tonumber(x), tonumber(y)
end

-- "file, file" as numbers
function E.ParseFiles(s)
  local out = {}
  for f in string.gmatch(s, "[^,%s]+") do out[#out + 1] = tonumber(f) or f end
  return out
end

-- the game's explored pieces of a map: { key = { files } }, and the keys only shown by a mouse over (never drawn)
function E.Explored(map)
  local seen, never = {}, {}
  local X = C_MapExplorationInfo
  if not (X and X.GetExploredMapTextures) then return seen, never end
  local ok, list = pcall(X.GetExploredMapTextures, map)
  for _, p in ipairs(ok and type(list) == "table" and list or {}) do
    if type(p) == "table" and p.textureWidth and p.offsetX then
      local key = PieceKey(p.textureWidth, p.textureHeight, p.offsetX, p.offsetY)
      if p.isShownByMouseOver then never[key] = true else seen[key] = p.fileDataIDs or {} end
    end
  end
  return seen, never
end

-- a zone's pieces: { key = { w, h, x, y, files, explored } }, the data's (D.ArtPieces, by its art id) and the game's
function E.ZonePieces(map)
  local out = {}
  local art = nil
  if C_Map and C_Map.GetMapArtID then
    local ok, id = pcall(C_Map.GetMapArtID, map)
    if ok then art = id end
  end
  local seen, never = E.Explored(map)
  for key, files in pairs(art and D.ArtPieces and D.ArtPieces[art] or {}) do
    if not never[key] then
      local w, h, x, y = E.ParseKey(key)
      if w then out[key] = { w, h, x, y, E.ParseFiles(files), explored = seen[key] ~= nil } end
    end
  end
  for key, files in pairs(seen) do
    if not out[key] then
      local w, h, x, y = E.ParseKey(key)
      if w and #files > 0 then out[key] = { w, h, x, y, files, explored = true } end
    end
  end
  return out
end

--------------------------------------------------------------------------------
-- Groups: zones and cities
--------------------------------------------------------------------------------

-- a mask over the group's map, on one of its frames (made once a frame and file)
local function GroupMask(g, frame, name, sub)
  local key = tostring(frame) .. name
  local mk = g.maskBy[key]
  if not mk then
    local s = g.spot
    mk = NewMask(frame, Tex(name, sub), s[1], s[2], s[5] * s[3], s[6] * s[4])
    g.maskBy[key] = mk
    g.masks[#g.masks + 1] = mk
  end
  return mk
end

-- sprites of a piece's tiles on `frame`, shifted dx, dy art px
local function PieceSprites(g, piece, frame, sub, masks, kind, dx, dy, extra)
  local s = g.spot
  local files = piece[5]
  for i, tl in ipairs(E.Tiles(piece[1], piece[2], E.TILE, true)) do
    local f = files[i]
    if f and f ~= 0 then
      local sp = { frame = frame, layer = "ARTWORK", sub = sub, file = f, masks = masks, kind = kind, piece = piece,
        lazy = true, x = s[1] + (piece[3] + tl[3] + dx) * s[3], y = s[2] + (piece[4] + tl[4] + dy) * s[4],
        w = tl[5] * s[3], h = tl[6] * s[4], tc = { 0, tl[7], 0, tl[8] } }
      for k, v in pairs(extra or {}) do sp[k] = v end
      g.sprites[#g.sprites + 1] = sp
    end
  end
end

-- the frame mask a zone's pieces are cut by: its own measured frame, else the thin feather
local function EdgeMask(z, frame)
  if z.tint and not E.NO_EDGE[z.map] then return GroupMask(z, frame, "MapEdge", z.map) end
  return GroupMask(z, frame, "MapFeatherThin")
end

-- a piece's overlay (and its border copy) and interior sprites
local function AddPiece(z, piece)
  local sub = piece.explored and 1 or 0
  local hole = D.BannerCutouts and D.BannerCutouts[z.map]
  local function Cut(frame, last)
    local m = { EdgeMask(z, frame) }
    if hole then m[#m + 1] = GroupMask(z, frame, "MapBannerHole", z.map) end
    if last then m[#m + 1] = GroupMask(z, frame, last, z.map) end
    return m
  end
  local over, inner = E.layer[E.LEVEL_OVERLAY], E.layer.inner
  PieceSprites(z, piece, over, sub, Cut(over), "live", 0, 0)
  if z.tint then
    PieceSprites(z, piece, over, sub + 2, Cut(over, "MapBand"), "live", 0, 0, { tinted = true })
    PieceSprites(z, piece, inner, sub, Cut(inner, "MapCore"), "live", 0, 0)
    if z.blurBuilt then E.AddBlur(z, piece) end
  end
end

-- a piece's four shifted copies of its interior (built the first time the zone is blurred)
function E.AddBlur(z, piece)
  local t = E.BLUR_TAP
  for i, f in ipairs(E.blurFrames) do
    local m = { EdgeMask(z, f) }
    if D.BannerCutouts and D.BannerCutouts[z.map] then m[#m + 1] = GroupMask(z, f, "MapBannerHole", z.map) end
    m[#m + 1] = GroupMask(z, f, "MapCore", z.map)
    PieceSprites(z, piece, f, piece.explored and 1 or 0, m, "blur", (i % 2 == 1) and -t or t, i <= 2 and -t or t)
  end
end

function E.BuildBlur(z)
  z.blurBuilt = true
  for _, piece in pairs(z.pieces) do E.AddBlur(z, piece) end
end

-- the zone's base art: through the feather (and, graded, its territory), with a border copy
local function AddBase(z)
  local f = z.frame
  local files = E.ArtFiles(z.map)
  local m = { GroupMask(z, f, "MapFeather") }
  if z.tint then m[2] = GroupMask(z, f, "MapTerritory", z.map) end
  local list = E.ArtSprites(f, "ARTWORK", 0, z.map, files, m, z.spot)
  if z.tint then
    E.ArtSprites(f, "ARTWORK", 2, z.map, files, { m[1], GroupMask(z, f, "MapBand", z.map) }, z.spot, list)
    for i = #list / 2 + 1, #list do list[i].tinted = true end
  end
  for _, sp in ipairs(list) do
    sp.lazy, sp.kind = true, "live"
    z.sprites[#z.sprites + 1] = sp
  end
end

local function NewGroup(map)
  local s = E.Spot(map)
  if not s then return nil end
  return { map = map, spot = s, x0 = s[1], y0 = s[2], x1 = s[1] + s[5] * s[3], y1 = s[2] + s[6] * s[4],
    sprites = {}, masks = {}, maskBy = {}, active = false }
end

-- the zones and cities on Azeroth's map, largest first; a zone has explorable pieces, a city (a capital) none
function E.BuildZones()
  E.zones, E.cities = {}, {}
  local T = Enum and Enum.UIMapType
  local kids = {}
  if C_Map and C_Map.GetMapChildrenInfo and T then
    local ok, list = pcall(C_Map.GetMapChildrenInfo, E.WORLD, T.Zone, true)
    if ok and type(list) == "table" then kids = list end
  end
  local groups = {}
  for _, k in ipairs(kids) do
    local g = type(k) == "table" and k.mapID and NewGroup(k.mapID)
    if g then
      g.area = (g.x1 - g.x0) * (g.y1 - g.y0)
      if g.area > 0 then groups[#groups + 1] = g end
    end
  end
  table.sort(groups, function(a, b) return a.area > b.area end)
  local lv = E.ZONE_LEVELS
  for _, g in ipairs(groups) do
    g.pieces = E.ZonePieces(g.map)
    if next(g.pieces) then
      local i = #E.zones
      g.tint = D.BorderTints and D.BorderTints[g.map]
      g.frame = E.NewLayer(math.min(lv[1] + i, lv[2]))
      AddBase(g)
      for _, piece in pairs(g.pieces) do AddPiece(g, piece) end
      E.zones[i + 1] = g
    else
      E.AddCity(g)
    end
  end
  E.FindCities()
end

-- a capital: its map cut to its plan (or the round feather), on a frame of its own; its zone's banner for it
function E.AddCity(c)
  local cut = D.CityPlans and D.CityPlans[c.map]
  c.frame = E.NewLayer(E.UNDERGROUND[c.map] and E.LEVEL_CITY_UNDER or E.LEVEL_CITY)
  local mk = cut and GroupMask(c, c.frame, "MapCityMask", c.map) or GroupMask(c, c.frame, "MapFeatherRound")
  for _, sp in ipairs(E.ArtSprites(c.frame, "ARTWORK", 0, c.map, E.ArtFiles(c.map), { mk }, c.spot)) do
    sp.lazy = true
    c.sprites[#c.sprites + 1] = sp
  end
  local l, r = E.MapRect(c.map)
  c.zc = 1 / (r - l)
  c.fade = E.CITY_FADE[c.map] or E.CITY_FADE_DEFAULT
  c.found = true
  local b = D.CityBanners and D.CityBanners[c.map]
  local zs = b and E.Spot(b[1])
  if zs then
    c.banner = { frame = E.layer[E.LEVEL_BANNER], layer = "ARTWORK", sub = 0, file = Tex("MapBanner", c.map),
      x = zs[1] + b[2] * zs[3], y = zs[2] + b[3] * zs[4], w = b[4] * zs[3], h = b[5] * zs[4], tc = { 0, 1, 0, 1 } }
  end
  E.cities[#E.cities + 1] = c
end

-- each city found: no zone's piece over its middle, or one of those explored
function E.FindCities()
  local changed = false
  for _, c in ipairs(E.cities) do
    local cx, cy = (c.x0 + c.x1) / 2, (c.y0 + c.y1) / 2
    local covered, seen = false, false
    for _, z in ipairs(E.zones) do
      local s = z.spot
      local px, py = (cx - s[1]) / s[3], (cy - s[2]) / s[4]
      for _, p in pairs(z.pieces) do
        if px >= p[3] and px <= p[3] + p[1] and py >= p[4] and py <= p[4] + p[2] then
          covered = true
          if p.explored then seen = true end
        end
      end
    end
    local found = not covered or seen
    if found ~= c.found then
      c.found = found
      changed = true
    end
  end
  return changed
end

-- MAP_EXPLORATION_UPDATED: each zone's pieces' state again (a piece explored keeps its textures and place)
function E.Rescan()
  if not E.built then return end
  local changed = false
  for _, z in ipairs(E.zones) do
    local seen, never = E.Explored(z.map)
    for key, p in pairs(z.pieces) do
      local now = seen[key] ~= nil
      if now ~= p.explored then
        p.explored = now
        changed = true
      end
    end
    for key, files in pairs(seen) do
      if not z.pieces[key] and not never[key] then
        local w, h, x, y = E.ParseKey(key)
        if w and #files > 0 then
          local p = { w, h, x, y, files, explored = true }
          z.pieces[key] = p
          AddPiece(z, p)
          changed = true
        end
      end
    end
  end
  if E.FindCities() then changed = true end
  if changed then E.Refresh(true) end
end

--------------------------------------------------------------------------------
-- The baked zones: world tiles made when first near
--------------------------------------------------------------------------------

function E.BuildBaked()
  E.baked = {}
  local b = D.BakedZones
  if not b then return end
  local side = b.step / b.px
  local inset = (b.size - b.step) / 2 / b.size
  for _, key in ipairs(b.tiles) do
    local i, j = math.floor(key / 256), key % 256
    E.baked[#E.baked + 1] = { frame = E.layer.baked, layer = "ARTWORK", sub = 0, file = Tex("MapZones", i .. "_" .. j),
      x = i * side, y = j * side, w = side, h = side, tc = { inset, 1 - inset, inset, 1 - inset } }
  end
end

-- whether the baked tiles can stand in for the live zones: the grade they were rendered at, every area shown
function E.BakedUsable()
  local b, g = D.BakedZones, E.grade
  return b ~= nil and g.style ~= "hide" and math.abs(g.strength - (b.colorMatch or 1)) <= 0.001
    and math.abs(g.desat - (b.desaturate or 0.1)) <= 0.001
end

--------------------------------------------------------------------------------
-- The grade: colour match and desaturation of every zone and city texture
--------------------------------------------------------------------------------

E.grade = { strength = 1, desat = 0.1, style = "show" }

local function GradeSprite(z, sp)
  sp.desat = E.grade.desat
  if sp.tinted and z.tint then
    local k, t = E.grade.strength, z.tint
    sp.vc = { 1 + (t[1] - 1) * k, 1 + (t[2] - 1) * k, 1 + (t[3] - 1) * k }
  end
  E.Paint(sp)
end

function E.GradeAll()
  for _, list in ipairs({ E.zones, E.cities }) do
    for _, g in ipairs(list) do
      for _, sp in ipairs(g.sprites) do
        if sp.tex then GradeSprite(g, sp) else sp.desat = E.grade.desat end
      end
    end
  end
end

-- the glue's grade: strength of the colour match, desaturation, unexplored areas "show" or "hide"
function E.Grade(strength, desat, style)
  local g = E.grade
  g.strength, g.desat, g.style = strength or 1, desat or 0, style == "hide" and "hide" or "show"
  if not E.built then return end
  E.GradeAll()
  E.Refresh(true)
end

--------------------------------------------------------------------------------
-- Which sprites are wanted (E.st: the zoom's state, Engine.lua; E.cull: the box round the view)
--------------------------------------------------------------------------------

local function Wanted(z, sp, st)
  if sp.kind == "blur" then
    if not z.blurOn then return false end
  elseif not st.liveOn then
    return false
  end
  local p = sp.piece
  if p and not p.explored and E.grade.style == "hide" then return false end
  if sp.tinted and E.grade.strength <= 0 then return false end
  return true
end

local function Park(g)
  for _, sp in ipairs(g.sprites) do E.Drop(sp) end
  for _, mk in ipairs(g.masks) do E.ParkMask(mk) end
  g.active = false
end

-- show what's near and wanted of one group, hide the rest (a city's sprites all alike)
local function SyncGroup(g, st, c, isCity)
  local near = st.detail and E.Meets(g.x0, g.y0, g.x1, g.y1, c[1], c[2], c[3], c[4])
  if isCity and E.grade.style == "hide" and not g.found then near = false end
  if not near then
    if g.active then Park(g) end
    return
  end
  g.active = true
  for _, sp in ipairs(g.sprites) do
    if (isCity or Wanted(g, sp, st)) and E.Meets(sp.x, sp.y, sp.x + sp.w, sp.y + sp.h, c[1], c[2], c[3], c[4]) then
      if not sp.tex then
        E.MakeTexture(sp)
        GradeSprite(g, sp)
      end
      E.Want(sp)
    else
      E.Drop(sp)
    end
  end
end
E.SyncGroup = SyncGroup

-- every zone, city, banner and baked tile against the cull box
function E.SyncZones()
  local st, c = E.st, E.cull
  if not c then return end
  for _, z in ipairs(E.zones) do SyncGroup(z, st, c, false) end
  for _, city in ipairs(E.cities) do
    SyncGroup(city, st, c, true)
    local b = city.banner
    if b then
      if st.detail and E.Meets(b.x, b.y, b.x + b.w, b.y + b.h, c[1], c[2], c[3], c[4]) then
        E.Want(b)
        b.tex:SetAlpha(b.alpha or 0)
      else
        E.Drop(b)
      end
    end
  end
  local show = st.bakedA > 0
  for _, sp in ipairs(E.baked) do
    if show and E.Meets(sp.x, sp.y, sp.x + sp.w, sp.y + sp.h, c[1], c[2], c[3], c[4]) then
      E.Want(sp)
    elseif sp.tex then
      E.Drop(sp)
    end
  end
  for _, block in ipairs(E.gapArt) do
    local on = st.liveOn and E.Meets(block.x0, block.y0, block.x1, block.y1, c[1], c[2], c[3], c[4])
    for _, sp in ipairs(block.sprites) do
      if on then E.Want(sp) else E.Drop(sp) end
    end
  end
  for _, sp in ipairs(E.bd.paper) do
    if E.Meets(sp.x, sp.y, sp.x + sp.w, sp.y + sp.h, c[1], c[2], c[3], c[4]) then E.Want(sp) else E.Drop(sp) end
  end
end

-- the close-up blur: graded zones meeting the view box (vx0, vy0, vx1, vy1), while soft; true when that set changed
function E.SyncBlur(vx0, vy0, vx1, vy1, soft)
  local changed = false
  for _, z in ipairs(E.zones) do
    local on = soft and z.tint ~= nil and E.Meets(z.x0, z.y0, z.x1, z.y1, vx0, vy0, vx1, vy1) or false
    if on and not z.blurBuilt then E.BuildBlur(z) end
    if on ~= (z.blurOn or false) then
      z.blurOn = on
      if E.cull then SyncGroup(z, E.st, E.cull, false) end
      changed = true
    end
  end
  return changed
end

-- the cities' and banners' alphas at detail zoom zd (d the zones' detail)
function E.CityAlphas(zd, d)
  local hide = E.grade.style == "hide"
  for _, c in ipairs(E.cities) do
    local a = E.Smooth(c.fade[1] * c.zc, c.fade[2] * c.zc, zd)
    c.alpha = a
    if a <= 0.003 then c.frame:Hide() else
      c.frame:Show()
      c.frame:SetAlpha(a)
    end
    local b = c.banner
    if b then
      local out = D.CityTitled and D.CityTitled[c.map] and E.Smooth(0.25 * c.zc, 0.4 * c.zc, zd) or 0
      local ba = E.Round50(d * (1 - out))
      if hide and not c.found then ba = 0 end
      b.alpha = ba
      if b.tex then b.tex:SetAlpha(ba) end
    end
  end
end

end }
