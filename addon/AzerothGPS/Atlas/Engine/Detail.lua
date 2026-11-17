-- The seamless map's engine, part 4 of 5: what depends on where the view is, not only its zoom (docs/atlas-spec.md,
-- 6.15, 10, 11): the game's minimap tiles mixed in close up, caves surfacing, the paper's grain over everything, and
-- the continents' and seas' names lettered live in the client's font.
local _, ns = ...
ns.AtlasChunks = ns.AtlasChunks or {}
ns.AtlasChunks[#ns.AtlasChunks + 1] = { "engine/Detail", function(D, E)

E.LEVEL_MINI, E.LEVEL_DIM, E.LEVEL_CAVE, E.LEVEL_NAMES, E.LEVEL_GRAIN = 72, 76, 77, 78, 79
E.MINI = { strength = 0.45, deepest = 0.85, from = { 20, 34 }, to = { 30, 48 }, desat = 0.35 }
-- the close-up's knobs (issue #72, turned live by the dev tools through Atlas.lua's A.SetCloseKnob): the zoom the
-- minimap starts to mix in from (its fades move with it; 1: from the whole world), the most it ever shows, and the
-- softening and grain close up. Shipped as tuned in testing (issue #90: the minimap later, and whole at its deepest).
-- closeUpFrom is the glue's (Atlas.lua A.ApplyView): on AzerothGPS's map the art is told no closer a detail zoom than
-- this, so the close-up (softening, grain, minimap) never shows there; past the terrain's tiles it's the zones' map.
E.KNOBS = { minimapFrom = 40, minimapDeep = 1, soften = true, closeUpFrom = 8 }
E.MINI_CAP ={ [1454] = 0.15, [1456] = 0.15 } -- (a surface capital keeps its own map: the mix at most this; else 0.5)
E.MINI_PAPER = { 1, 0.93, 0.80 }
E.MINI_TONE = { 0.56, 0.45, 0.17 }
E.CAVE_SKIP = { [34] = true, [35] = true } -- (Blackrock Mountain's deeper floors)
E.CAVE_FAR = { [33] = 4 }                  -- (Blackrock Mountain surfaces from further out; else 1.5)
E.DIM = { 0.05, 0.035, 0.02 }

local Smooth, Tex = E.Smooth, E.Tex
local floor, max, min, abs = math.floor, math.max, math.min, math.abs

-- the uv box of a yards box (two opposite corners) on continent `cont`, as world units x0, y0, x1, y1
local function YardsBox(cont, xa, ya, xb, yb)
  local u1, v1 = E.YardsToUV(cont, xa, ya)
  local u2, v2 = E.YardsToUV(cont, xb, yb)
  if not (u1 and u2) then return nil end
  return min(u1, u2) * E.W, min(v1, v2) * E.H, max(u1, u2) * E.W, max(v1, v2) * E.H
end
E.YardsBox = YardsBox

-- a sprite over a world box (its texture made now), hidden
local function BoxSprite(frame, sub, file, x0, y0, x1, y1, masks, extra)
  local sp = { frame = frame, layer = "ARTWORK", sub = sub, file = file, masks = masks, tc = { 0, 1, 0, 1 },
    x = x0, y = y0, w = x1 - x0, h = y1 - y0 }
  for k, v in pairs(extra or {}) do sp[k] = v end
  E.MakeTexture(sp)
  return sp
end

--------------------------------------------------------------------------------
-- The minimap mixed in close up (10)
--------------------------------------------------------------------------------

-- how much of (u, v) a city covers: its alpha, eased off toward its rectangle's sides
local function CityCover(c, u, v)
  local l, r = c.x0 / E.W, c.x1 / E.W
  local t, b = c.y0 / E.H, c.y1 / E.H
  if u < l or u > r or v < t or v > b then return 0 end
  local e = min(min(u - l, r - u) / ((r - l) / 2), min(v - t, b - v) / ((b - t) / 2))
  return (c.alpha or 0) * min(1, 2.5 * e)
end

-- the minimap's share at plain zoom zp over (u, v)
function E.MiniMix(u, v, zp)
  local m, kn = E.MINI, E.KNOBS
  local k, most = kn.minimapFrom / m.from[1], kn.minimapDeep -- (the take-over moves later with it, never sooner)
  local mix = min(m.strength, most) * (kn.minimapFrom <= 1 and 1 or Smooth(m.from[1] * k, m.from[2] * k, zp))
  mix = mix + (most - mix) * Smooth(m.to[1] * max(1, k), m.to[2] * max(1, k), zp)
  local under, over, cap = 0, 0, 0.5
  for _, c in ipairs(E.cities or {}) do
    local k = CityCover(c, u, v)
    if E.UNDERGROUND[c.map] then
      if k > under then under = k end
    elseif k > over then
      over, cap = k, E.MINI_CAP[c.map] or 0.5
    end
  end
  mix = mix * (1 - under)
  if mix > cap then mix = mix + (cap - mix) * over end
  return mix
end

-- the tint of a minimap tile: its deepest map's painted colour, taken a quarter of the way from the paper
function E.MiniTint(cont, tx, ty)
  local xa, ya, xb, yb = E.TileYards(tx, ty, tx, ty)
  local u, v = E.YardsToUV(cont, (xa + xb) / 2, (ya + yb) / 2)
  local tone = E.MINI_TONE
  if u then
    local chain = E.ChainAt(u, v)
    tone = D.ZoneTones and D.ZoneTones[chain[#chain]] or tone
  end
  local top = max(tone[1], tone[2], tone[3], 0.001)
  local p = E.MINI_PAPER
  return { p[1] + (tone[1] / top - p[1]) * 0.25, p[2] + (tone[2] / top - p[2]) * 0.25,
    p[3] + (tone[3] / top - p[3]) * 0.25 }
end

-- the land mask of continent `cont`'s map on the minimap frame (one each)
local function MiniMask(cont)
  local mk = E.mini.masks[cont]
  if mk == nil then
    local map = E.CONT_MAP[cont]
    mk = E.Spot(map) and E.MapMask(E.layer.mini, Tex("MapLand", map), map) or false
    E.mini.masks[cont] = mk
  end
  return mk or nil
end

-- a minimap sprite by key: made when first wanted, kept
local function MiniSprite(key, make)
  local sp = E.mini.made[key]
  if sp == nil then
    sp = make() or false
    E.mini.made[key] = sp
  end
  return sp or nil
end

-- one continent's tiles and pieces over the view box (world units) at mix `mix`; the keys shown go in `keep`
local function MiniContinent(cont, vx0, vy0, vx1, vy1, mix, keep)
  local xa, ya = E.UVToYards(cont, vx0 / E.W, vy0 / E.H)
  local xb, yb = E.UVToYards(cont, vx1 / E.W, vy1 / E.H)
  if not (xa and xb) then return end
  local t1x, t1y = E.TileAt(xa, ya)
  local t2x, t2y = E.TileAt(xb, yb)
  local tx0, tx1 = max(0, min(t1x, t2x)), min(63, max(t1x, t2x))
  local ty0, ty1 = max(0, min(t1y, t2y)), min(63, max(t1y, t2y))
  if tx1 < tx0 or ty1 < ty0 then return end
  local count = (tx1 - tx0 + 1) * (ty1 - ty0 + 1)
  local across = max(tx1 - tx0 + 1, ty1 - ty0 + 1)
  local lods = D.MiniMipmaps and D.MiniMipmaps[cont]
  local wn = 0
  if count <= 64 then wn = lods and Smooth(64, 36, count) or 1 end
  local fine = Smooth(40, 24, across)
  local a3 = mix * wn
  local a2 = a3 < 1 and mix * (1 - wn) * fine / (1 - a3) or 0
  local a1 = mix * (1 - wn) * (1 - fine) / max(0.001, (1 - a2) * (1 - a3))
  local mk = MiniMask(cont)
  local f = E.layer.mini
  for i, lod in ipairs(lods or {}) do
    local a = i == 1 and a2 or a1
    if i <= 2 and a > 0.005 then
      local n, have = lod[1], E.mini.lodSets[cont .. ":" .. i]
      if not have then
        have = {}
        for _, k in ipairs(lod[2]) do have[k] = true end
        E.mini.lodSets[cont .. ":" .. i] = have
      end
      for col = floor(tx0 / n), floor(tx1 / n) do
        for row = floor(ty0 / n), floor(ty1 / n) do
          if have[col * 64 + row] then
            local key = "l" .. cont .. ":" .. n .. ":" .. col .. ":" .. row
            local sp = MiniSprite(key, function()
              local x0, y0, x1, y1 = YardsBox(cont, E.TileYards(col * n, row * n, col * n + n - 1, row * n + n - 1))
              if not x0 then return nil end
              return BoxSprite(f, i == 1 and -1 or -2, Tex("MapMiniLOD", cont .. "_" .. n .. "_" .. col .. "_" .. row),
                x0, y0, x1, y1, mk and { mk } or nil, { desat = E.MINI.desat })
            end)
            if sp then
              keep[key] = true
              E.Want(sp)
              sp.tex:SetAlpha(min(1, a))
            end
          end
        end
      end
    end
  end
  local tiles = D.MiniTiles and D.MiniTiles[cont]
  if count <= 64 and a3 > 0.005 and tiles then
    for tx = tx0, tx1 do
      for ty = ty0, ty1 do
        local file = tiles[tx * 64 + ty]
        if file then
          local key = "t" .. cont .. ":" .. tx .. ":" .. ty
          local sp = MiniSprite(key, function()
            local x0, y0, x1, y1 = YardsBox(cont, E.TileYards(tx, ty, tx, ty))
            if not x0 then return nil end
            return BoxSprite(f, 0, file, x0, y0, x1, y1, mk and { mk } or nil,
              { desat = E.MINI.desat, vc = E.MiniTint(cont, tx, ty) })
          end)
          if sp then
            keep[key] = true
            E.Want(sp)
            sp.tex:SetAlpha(a3)
          end
        end
      end
    end
  end
end

-- the minimap over the view box (world units) at plain zoom zp
function E.SyncMinimap(u, v, vx0, vy0, vx1, vy1, zp)
  local mm = E.mini
  local mix = zp >= E.MINI.from[1] and E.MiniMix(u, v, zp) or 0
  local keep = {}
  if mix > 0.005 then
    for cont, map in pairs(E.CONT_MAP) do
      local s = E.Spot(map)
      if s and E.Meets(s[1], s[2], s[1] + s[5] * s[3], s[2] + s[6] * s[4], vx0, vy0, vx1, vy1) then
        MiniContinent(cont, vx0, vy0, vx1, vy1, mix, keep)
      end
    end
  end
  for key in pairs(mm.shown) do
    if not keep[key] then
      local sp = mm.made[key]
      if sp then E.Drop(sp) end
    end
  end
  mm.shown = keep
end

--------------------------------------------------------------------------------
-- Caves surfacing (11)
--------------------------------------------------------------------------------

-- the caves of a continent: one floor a place (its lowest map), with its uv box in world units
local function CavesOf(cont)
  local list = E.caveList[cont]
  if list then return list end
  local byName = {}
  for map, c in pairs(D.CaveMaps or {}) do
    if c[2] == cont and not E.CAVE_SKIP[map] and (not byName[c[1]] or map < byName[c[1]]) then byName[c[1]] = map end
  end
  list = {}
  for _, map in pairs(byName) do
    local c = D.CaveMaps[map]
    local x0, y0, x1, y1 = YardsBox(cont, c[5], c[6], c[3], c[4])
    if x0 then list[#list + 1] = { map = map, files = c[11], x0 = x0, y0 = y0, x1 = x1, y1 = y1 } end
  end
  E.caveList[cont] = list
  return list
end

local function BuildCave(cv)
  local f = E.NewLayer(E.LEVEL_CAVE)
  local w, h = cv.x1 - cv.x0, cv.y1 - cv.y0
  local mk = E.NewMask(f, Tex("MapCave", cv.map), cv.x0, cv.y0, w, h)
  local spot = { cv.x0, cv.y0, w / 1002, h / 668, 1002, 668 }
  cv.frame, cv.sprites = f, E.ArtSprites(f, "ARTWORK", 0, nil, cv.files or {}, { mk }, spot)
  for _, sp in ipairs(cv.sprites) do E.MakeTexture(sp) end
end

-- the caves under the view: each surfacing as the view closes in on it; returns the focus U (how dark the world goes)
function E.SyncCaves(u, v, hu, hv)
  local cv = E.cave
  if not cv.at or abs(cv.at[1] - u) > 0.002 or abs(cv.at[2] - v) > 0.002 then
    cv.at = { u, v }
    cv.cont = nil
    for _, map in ipairs(E.ChainAt(u, v)) do
      if E.MAP_CONT[map] then cv.cont = E.MAP_CONT[map] break end
    end
  end
  local vx0, vy0, vx1, vy1 = (u - hu) * E.W, (v - hv) * E.H, (u + hu) * E.W, (v + hv) * E.H
  local focus, shown = 0, {}
  for _, c in ipairs(cv.cont and CavesOf(cv.cont) or {}) do
    if E.Meets(c.x0, c.y0, c.x1, c.y1, vx0, vy0, vx1, vy1) then
      local fill = (2 * hu * E.W) / (c.x1 - c.x0)
      local t = 1 - Smooth(1.05, E.CAVE_FAR[c.map] or 1.5, fill)
      if t > 0.01 then
        if not c.frame then BuildCave(c) end
        shown[c] = true
        c.frame:SetAlpha(t)
        c.frame:Show()
        for _, sp in ipairs(c.sprites) do E.Want(sp) end
        local cu, cvv = (c.x0 + c.x1) / 2 / E.W, (c.y0 + c.y1) / 2 / E.H
        local off = max(abs(cu - u) / hu, abs(cvv - v) / hv)
        focus = max(focus, t * (1 - Smooth(0.35, 0.8, off)))
      end
    end
  end
  for c in pairs(cv.shown or {}) do
    if not shown[c] then
      for _, sp in ipairs(c.sprites) do E.Drop(sp) end
      c.frame:Hide()
    end
  end
  cv.shown = shown
  local dim = cv.dim
  if focus > 0.01 then
    if not dim then
      dim = { frame = E.layer.dim, layer = "BACKGROUND", sub = 0, file = false, x = 0, y = 0, w = 1, h = 1 }
      dim.tex = dim.frame:CreateTexture(nil, "BACKGROUND")
      dim.tex:SetColorTexture(E.DIM[1], E.DIM[2], E.DIM[3], 1)
      dim.ready = true
      cv.dim = dim
    end
    dim.x, dim.y, dim.w, dim.h = (u - 1.5 * hu) * E.W, (v - 1.5 * hv) * E.H, 3 * hu * E.W, 3 * hv * E.H
    E.Anchor(dim)
    dim.tex:SetAlpha(0.45 * focus)
    dim.tex:Show()
    dim.on = true
  elseif dim then
    E.Drop(dim)
  end
  return focus
end

--------------------------------------------------------------------------------
-- Grain and tooth over everything (10.5)
--------------------------------------------------------------------------------

function E.BuildGrain()
  E.grain = { sprites = {} }
  local f = E.layer.grain
  for i, name in ipairs({ "MapGrain", "MapGrain", "MapTooth", "MapTooth" }) do
    local sp = { frame = f, layer = "OVERLAY", sub = i, file = Tex(name), wrap = true, x = 0, y = 0, w = 1, h = 1,
      octave = (i - 1) % 2 + 1, tooth = i > 2 }
    E.MakeTexture(sp)
    E.grain.sprites[i] = sp
  end
end

function E.SyncGrain(u, v, hu, hv, amount)
  local g = E.grain
  if amount <= 0.01 then
    if g.box then
      for _, sp in ipairs(g.sprites) do E.Drop(sp) end
      g.box = nil
    end
    return
  end
  local b, k = g.box, E.SEA_KEEP
  if b and b.hu == hu and b.amount == amount and u - k * hu >= b.u0 and u + k * hu <= b.u1
    and v - k * hv >= b.v0 and v + k * hv <= b.v1 then
    return
  end
  local r = E.SEA_BOX
  b = { hu = hu, amount = amount, u0 = u - r * hu, u1 = u + r * hu, v0 = v - r * hv, v1 = v + r * hv }
  g.box = b
  local x0, y0, x1, y1 = b.u0 * E.W, b.v0 * E.H, b.u1 * E.W, b.v1 * E.H
  local want = math.log(max(hu * 2 * E.W * 0.35, 1e-6)) / math.log(2)
  local n = floor(want)
  local f = want - n
  for _, sp in ipairs(g.sprites) do
    local period = 2 ^ (n + sp.octave - 1)
    if sp.tooth then period = period / 6 end
    local a = (sp.octave == 1 and 1 - f or f) * amount * (sp.tooth and 0.9 or 0.7)
    sp.x, sp.y, sp.w, sp.h = x0, y0, x1 - x0, y1 - y0
    E.Anchor(sp)
    sp.tex:SetTexCoord(x0 / period, x1 / period, y0 / period, y1 / period)
    sp.tex:SetAlpha(min(1, a))
    sp.tex:Show()
    sp.on = true
  end
end

--------------------------------------------------------------------------------
-- The continents' and seas' names (6.15)
--------------------------------------------------------------------------------

E.NAME_CAP = 0.69      -- the font's capital height, in font sizes
E.NAME_SMALL = 0.78    -- small capitals' size against a capital's
E.NAME_SCALE = 4       -- the lettering's frame is a quarter scale: its units a quarter world unit
E.HALO = { { 0.07, 1 }, { 0.15, 0.45 } } -- each ring's radius (cap heights) and strength
E.REST_GAP, E.REST_AFTER = 0.1, 0.15     -- the halos rest while the view moves on three frames this close

-- a label's name: the client's, else the data's
local function LabelText(lb)
  local n, text = lb.name or {}, nil
  if n.map and C_Map and C_Map.GetMapInfo then
    local ok, info = pcall(C_Map.GetMapInfo, n.map)
    text = ok and type(info) == "table" and info.name or nil
  elseif n.area and C_Map and C_Map.GetAreaInfo then
    local ok, name = pcall(C_Map.GetAreaInfo, n.area)
    text = ok and name or nil
  end
  if type(text) ~= "string" or text == "" then text = n.text or "" end
  return text
end

-- a string's characters (UTF-8), single bytes upper-cased
local function Letters(s)
  local out = {}
  for ch in string.gmatch(s, "[%z\1-\127\194-\244][\128-\191]*") do
    out[#out + 1] = #ch == 1 and string.upper(ch) or ch
  end
  return out
end

-- the text each line of a label takes: a word a line when they match, else the whole name on the widest
function E.LabelLines(text, lines)
  local words = {}
  for w in string.gmatch(text, "%S+") do words[#words + 1] = w end
  local out = {}
  if #words == #lines then
    for i, w in ipairs(words) do out[i] = w end
    return out
  end
  local best, bw = 1, -1
  for i, ln in ipairs(lines) do
    if ln[2] - ln[1] > bw then best, bw = i, ln[2] - ln[1] end
  end
  out[best] = text
  return out
end

local function Glyph(f, size, ch, layer)
  local fs = f:CreateFontString(nil, layer)
  fs:SetFont(STANDARD_TEXT_FONT or "Fonts\\FRIZQT__.TTF", max(1, size), "")
  fs:SetText(ch)
  return fs
end

-- a label's letters, on the names' frame (its units E.NAME_SCALE a world unit)
local function Letter(lb)
  local f = CreateFrame("Frame", nil, E.layer.names)
  f:SetScale(1 / E.NAME_SCALE)
  f:SetSize(E.W * E.NAME_SCALE, E.H * E.NAME_SCALE)
  f:SetPoint("TOPLEFT", E.layer.names, "TOPLEFT", 0, 0)
  lb.frame, lb.halo = f, {}
  local s = E.Spot(lb.map)
  local Q = E.NAME_SCALE
  local ink, glow = lb.ink or { 0, 0, 0 }, lb.glow or { 255, 255, 255 }
  local texts = E.LabelLines(LabelText(lb), lb.lines or {})
  for i, ln in ipairs(lb.lines or {}) do
    local text = texts[i]
    if s and text then
      local left, right, base = s[1] + ln[1] * s[3], s[1] + ln[2] * s[3], s[2] + ln[3] * s[4]
      local C = ln[4] * s[4]
      local big = C / E.NAME_CAP
      local glyphs, sum, newWord = {}, 0, true
      for _, ch in ipairs(Letters(text)) do
        if ch == " " then
          glyphs[#glyphs + 1] = { w = 0.4 * C }
          newWord = true
        else
          local size = (newWord or ln[5]) and big or big * E.NAME_SMALL
          local fs = Glyph(f, size * Q, ch, "OVERLAY")
          fs:SetTextColor(ink[1] / 255, ink[2] / 255, ink[3] / 255, 0.9)
          fs:SetShadowOffset(0, 0)
          glyphs[#glyphs + 1] = { w = fs:GetStringWidth() / Q, fs = fs, ch = ch, size = size }
          newWord = false
        end
        sum = sum + glyphs[#glyphs].w
      end
      local gaps = max(1, #glyphs - 1)
      local track = max(0.1 * C, ((right - left) - sum) / gaps)
      local x = (left + right) / 2 - (sum + track * (#glyphs - 1)) / 2
      for _, g in ipairs(glyphs) do
        if g.fs then
          local gy = base - 0.36 * g.size
          g.fs:SetPoint("LEFT", f, "TOPLEFT", x * Q, -gy * Q)
          -- the halo: two rings of copies in the glow colour, each copy's shadow on the opposite side
          for _, ring in ipairs(E.HALO) do
            local rad = ring[1] * C * Q
            local a = min(1, ring[2] * (lb.glowA or 0.5) / 8 * 2)
            for k = 0, 3 do
              local ang = k * math.pi / 4
              local dx, dy = rad * math.cos(ang), rad * math.sin(ang)
              local h = Glyph(f, g.size * Q, g.ch, "ARTWORK")
              h:SetTextColor(glow[1] / 255, glow[2] / 255, glow[3] / 255, a)
              h:SetShadowColor(glow[1] / 255, glow[2] / 255, glow[3] / 255, a)
              h:SetShadowOffset(-2 * dx, -2 * dy)
              h:SetPoint("LEFT", f, "TOPLEFT", x * Q + dx, -gy * Q + dy)
              lb.halo[#lb.halo + 1] = h
            end
          end
        end
        x = x + g.w + track
      end
    end
  end
end

-- each label's box (world units), for culling
function E.BuildNames()
  E.names = {}
  for _, lb in ipairs(D.Lettering or {}) do
    local s = E.Spot(lb.map)
    if s then
      local x0, y0, x1, y1 = math.huge, math.huge, -math.huge, -math.huge
      for _, ln in ipairs(lb.lines or {}) do
        local C = ln[4] * s[4]
        x0, x1 = min(x0, s[1] + ln[1] * s[3]), max(x1, s[1] + ln[2] * s[3])
        y0, y1 = min(y0, s[2] + ln[3] * s[4] - C), max(y1, s[2] + ln[3] * s[4])
      end
      if x1 > x0 then
        local w, h = x1 - x0, y1 - y0
        E.names[#E.names + 1] = { data = lb, x0 = x0 - w / 2, x1 = x1 + w / 2, y0 = y0 - h, y1 = y1 + h }
      end
    end
  end
end

-- the names' alphas at detail zoom zd, against the cull box
function E.SyncNames(zd, c)
  -- (the zones' fade's group: the player's stages move them with it, E.StageRange)
  local la, lb = E.StageRange("zone", 3, 4)
  local sa, sb = E.StageRange("zone", 3.5, 5)
  local land = E.Round100(1 - Smooth(la, lb, zd))
  local sea = E.Round100(1 - Smooth(sa, sb, zd))
  local rest = E.resting
  for _, n in ipairs(E.names) do
    local a = n.data.fade == "sea" and sea or land
    local near = c and E.Meets(n.x0, n.y0, n.x1, n.y1, c[1], c[2], c[3], c[4])
    if a > 0.01 and near and not n.frame then
      local lb = setmetatable({}, { __index = n.data })
      Letter(lb)
      n.frame, n.halo = lb.frame, lb.halo
    end
    if n.frame then
      if a <= 0.003 or not near then
        n.frame:Hide()
      else
        n.frame:SetAlpha(a)
        n.frame:Show()
        if n.rest ~= rest then
          n.rest = rest
          for _, h in ipairs(n.halo) do
            if rest then h:Hide() else h:Show() end
          end
        end
      end
    end
  end
end

-- the view moved at `now`: the halos rest on the third move in a row
function E.NoteMove(now)
  local m = E.moves
  if m.last and now - m.last <= E.REST_GAP then m.run = m.run + 1 else m.run = 1 end
  m.last = now
  if m.run >= 3 and not E.resting then
    E.resting = true
    E.SyncNames(E.st.zd, E.cull)
  end
  if E.resting then E.Wake() end
end

-- the halos back once the view has been still a moment; true while still waiting
function E.RestTick(now)
  if not E.resting then return false end
  if now - (E.moves.last or 0) >= E.REST_AFTER then
    E.resting = false
    E.SyncNames(E.st.zd, E.cull)
    return false
  end
  return true
end

end }
