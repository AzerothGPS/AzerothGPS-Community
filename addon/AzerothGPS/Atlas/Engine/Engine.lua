-- The seamless map's engine, part 5 of 5: the build, the zoom's state and the view (docs/atlas-spec.md, 5, 7, 12, 14).
-- What the glue (Atlas/Atlas.lua) calls: E.Build, E.IsBuilt, E.SetShown, E.Size, E.Grade, E.Rescan, E.SetView,
-- E.YardsToUV / E.UVToYards, E.MapRect, E.ChainAt.
--
-- A view change: the caves first (their focus dims the rest), then every fade by the zoom (E.Fades: pure numbers),
-- then each part by where the view is, each run apart (E.Guard): the sea's mottling, the cull box and what's in it,
-- the blur, the minimap, the grain, the names.
local _, ns = ...
ns.AtlasChunks = ns.AtlasChunks or {}
ns.AtlasChunks[#ns.AtlasChunks + 1] = { "engine/Engine", function(D, E)

E.CULL_PAD = 0.35   -- the cull box: the view and this share of its size on every side,
E.CULL_SPARE = 0.10 -- kept while the view stays this share of its size inside it
E.CULL_ZOOM = 1.6   -- and hasn't zoomed in more than this since
E.HANDOVER = { 1.2, 1.6 } -- screen px a baked px: the live zones over the baked ones
E.WARM = 1.02       -- (from here the live zones load under the baked ones)

local Smooth, Floor20, Round50, Round100 = E.Smooth, E.Floor20, E.Round50, E.Round100
local max = math.max

--------------------------------------------------------------------------------
-- The zoom's fades (pure: app/tests/test_atlas.py)
--------------------------------------------------------------------------------

-- The player's stages (AzerothGPS's Options > Map, the seamless style; Atlas.lua's A.SetStages, GPSFrame's G.ApplySeamPlayer):
-- two groups of the fades below, "world" (the continents giving way to the world's art: cont, sm, wo) and "zone" (the
-- zones' map giving way to the continents': d, wc, m, ws and the names), each { k, w }: moved by k on the detail zoom
-- (the zoom k times as close for the same look) and w times as wide (each end's distance from the group's middle on a
-- log scale times w; 0: a sharp switch at the middle). nil (or { 1, 1 }): the numbers as written, exactly. An end is
-- kept short of the zoom the map tells at the most (A.TellZoom, the closeUpFrom knob), so the zones are whole there.
E.STAGE_MID = { zone = 3, world = 1.5 }
E.STAGES = nil
function E.StageRange(group, a, b)
  local s = E.STAGES and E.STAGES[group]
  if not s or (s[1] == 1 and s[2] == 1) then return a, b end
  local c, k, w = E.STAGE_MID[group], s[1], s[2]
  a, b = k * c * (a / c) ^ w, k * c * (b / c) ^ w
  local most = 0.95 * (E.KNOBS and E.KNOBS.closeUpFrom or 8)
  if b > most then b = most end
  if a > b then a = b end
  return a, b
end
local function Stage(group, a, b, zd)
  a, b = E.StageRange(group, a, b)
  return Smooth(a, b, zd)
end

-- every fade at detail zoom zd with a cave's focus U (7.2, 7.4)
function E.Fades(zd, U)
  U = U or 0
  local f = {
    cont = Stage("world", 1.3, 1.7, zd),
    sm = Floor20(Stage("world", 1.2, 1.9, zd)),
    wo = Floor20(Stage("world", 1.7, 2.2, zd)),
    wc = Floor20(Stage("zone", 3, 5, zd)),
    m = Floor20(Stage("zone", 4, 7, zd)),
    ws = Floor20(Stage("zone", 4, 7, zd)),
    soft = (not E.KNOBS or E.KNOBS.soften) and Smooth(8, 18, zd) or 0,
  }
  f.d = (0.3 * Stage("zone", 1.8, 3, zd) + 0.7 * Stage("zone", 3, 4.5, zd)) * (1 - 0.75 * U)
  f.ms = max(0, f.ws, f.wc)
  return f
end

-- the live zones against the baked ones at rho screen px a baked px: the live share, warm, on, the baked alpha
function E.Handover(usable, rho, d, holding)
  local share, warm = 1, false
  if usable then
    share = Round50(Smooth(E.HANDOVER[1], E.HANDOVER[2], rho))
    warm = rho >= E.WARM
  end
  local on = d > 0.001 and (share > 0 or warm or not usable)
  local baked = 0
  if usable then baked = Round100((1 - (1 - d) ^ 2) * (1 - (holding and 0 or share))) end
  return share, warm, on, baked
end

--------------------------------------------------------------------------------
-- The build
--------------------------------------------------------------------------------

E.built = false
E.st = { zd = 0, liveOn = false, detail = false, bakedA = 0, d = 0, soft = 0, U = 0 }

local function Alpha(f, a)
  if a <= 0.003 then f:Hide() else
    f:SetAlpha(a)
    f:Show()
  end
end

local function Driver()
  local d = CreateFrame("Frame")
  d:Hide()
  d:SetScript("OnUpdate", function(self)
    local now = GetTime and GetTime() or 0
    local busy = E.Pump(now)
    if not busy and E.st.holding then
      E.st.holding = false
      E.Refresh(false)
    end
    local resting = E.RestTick(now)
    if not busy and not resting then self:Hide() end
  end)
  return d
end

-- the art on `canvas` (laid out in world units), its frames from level L up `range` levels, an empty one for icons
-- at `iconLevel`; E.IsBuilt() false when the game gives no art for Azeroth's map
function E.Build(canvas, L, range, iconLevel)
  if E.built then return true end
  E.ForgetMaps()
  local art = E.ArtLayer(E.WORLD)
  if not art then return false end
  E.W, E.H = art[1], art[2]
  E.canvas, E.L, E.range, E.frames = canvas, L, range, {}
  canvas:SetSize(E.W, E.H)
  local lay = {}
  E.layer = lay
  for _, off in ipairs({ 0, 1, 2, E.LEVEL_OVERLAY }) do lay[off] = E.NewLayer(off) end
  lay.inner = E.NewLayer(E.LEVEL_INNER)
  lay.baked = E.NewLayer(E.LEVEL_BAKED)
  lay.blur = E.NewLayer(E.LEVEL_BLUR)
  E.blurFrames = {}
  for i = 1, 4 do
    local f = E.NewLayer(E.LEVEL_BLUR + i, lay.blur)
    f:SetAlpha(1 / (i + 1))
    E.blurFrames[i] = f
  end
  lay.mini = E.NewLayer(E.LEVEL_MINI)
  lay.dim = E.NewLayer(E.LEVEL_DIM)
  lay[E.LEVEL_BANNER] = E.NewLayer(E.LEVEL_BANNER)
  lay.names = E.NewLayer(E.LEVEL_NAMES)
  lay.grain = E.NewLayer(E.LEVEL_GRAIN)
  E.icons = CreateFrame("Frame", nil, canvas)
  E.icons:SetFrameLevel(iconLevel or (L + range + 1))
  E.mini = { made = {}, shown = {}, masks = {}, lodSets = {} }
  E.cave, E.caveList = {}, {}
  E.moves, E.resting = { run = 0 }, false
  E.queue, E.qHead, E.fades = {}, 1, {}
  E.BuildBackdrop()
  E.BuildZones()
  E.BuildBaked()
  E.BuildGrain()
  E.BuildNames()
  E.driver = Driver()
  E.built = true
  E.GradeAll()
  return true
end

function E.IsBuilt() return E.built end

-- Azeroth's map art's size: world units
function E.Size() return E.W, E.H end

function E.SetShown(on)
  if E.canvas then
    if on then E.canvas:Show() else E.canvas:Hide() end
  end
end

--------------------------------------------------------------------------------
-- The zoom's state applied
--------------------------------------------------------------------------------

-- screen px a baked px now (the canvas's effective scale on the physical screen)
local function Rho()
  local s = E.canvas.GetEffectiveScale and E.canvas:GetEffectiveScale() or 1
  local ph = 768
  if GetPhysicalScreenSize then
    local _, h = GetPhysicalScreenSize()
    if type(h) == "number" and h > 0 then ph = h end
  end
  local px = D.BakedZones and D.BakedZones.px or 16
  return s * (ph / 768) / px
end

-- every fade at detail zoom zd (with the caves' focus U): true when what the zones want changed
function E.ApplyZoom(zd, U)
  local st, lay = E.st, E.layer
  local f = E.Fades(zd, U)
  st.zd, st.U, st.d, st.soft, st.ms = zd, U, f.d, f.soft, f.ms
  E.TintBackdrop(f.m, f.sm, f.wo, f.ws, f.wc)
  Alpha(lay[1], f.cont)
  E.LandAlpha(max(f.m, U), f.d)
  local usable = E.BakedUsable()
  local rho = Rho()
  local share, warm, on = E.Handover(usable, rho, f.d, false)
  if on and not st.liveOn and usable and E.Loading() then st.holding = true end
  if not usable then st.holding = false end
  local _, _, _, baked = E.Handover(usable, rho, f.d, st.holding)
  local was = tostring(st.liveOn) .. st.bakedA .. tostring(st.detail)
  st.liveOn, st.bakedA, st.detail, st.share, st.warm = on, baked, f.d > 0.001, share, warm
  local live = on and f.d or 0
  for _, z in ipairs(E.zones) do Alpha(z.frame, live) end
  Alpha(lay[E.LEVEL_OVERLAY], live)
  Alpha(lay[2], live)
  Alpha(lay.inner, on and max(0, (f.d - 0.3) / 0.7) or 0)
  Alpha(lay.baked, baked)
  Alpha(lay.blur, f.d * f.soft)
  E.CityAlphas(zd, f.d)
  return was ~= tostring(st.liveOn) .. st.bakedA .. tostring(st.detail)
end

--------------------------------------------------------------------------------
-- The view
--------------------------------------------------------------------------------

-- the cull box round the view box (world units): kept while it still holds the view with room to spare
local function Cull(vx0, vy0, vx1, vy1)
  local w, h = vx1 - vx0, vy1 - vy0
  local c = E.cull
  if c then
    local sw, sh = E.CULL_SPARE * w, E.CULL_SPARE * h
    if vx0 - sw >= c[1] and vy0 - sh >= c[2] and vx1 + sw <= c[3] and vy1 + sh <= c[4] and w * E.CULL_ZOOM >= c.w then
      return false
    end
  end
  local pw, ph = E.CULL_PAD * w, E.CULL_PAD * h
  E.cull = { vx0 - pw, vy0 - ph, vx1 + pw, vy1 + ph, w = w }
  return true
end

-- the view: its middle (u, v), half its size (hu, hv) in (u, v), the detail zoom zd and the plain zoom zp
function E.SetView(u, v, hu, hv, zd, zp)
  if not E.built then return end
  E.view = { u, v, hu, hv, zd, zp }
  local W, H = E.W, E.H
  local vx0, vy0, vx1, vy1 = (u - hu) * W, (v - hv) * H, (u + hu) * W, (v + hv) * H
  local U = 0
  E.Guard("caves", function() U = E.SyncCaves(u, v, hu, hv) end)
  local changed = E.ApplyZoom(zd, U)
  local st = E.st
  E.Guard("sea", E.LaySea, u, v, hu, hv, zd, st.ms)
  E.Guard("cull", function()
    if Cull(vx0, vy0, vx1, vy1) or changed or E.dirty then
      E.dirty = false
      E.SyncZones()
    end
  end)
  E.Guard("blur", function()
    E.SyncBlur(vx0, vy0, vx1, vy1, st.soft > 0.01)
  end)
  E.Guard("minimap", E.SyncMinimap, u, v, vx0, vy0, vx1, vy1, zp)
  E.Guard("grain", E.SyncGrain, u, v, hu, hv, max(st.soft, math.min(1.4, 1.4 * U)))
  E.Guard("names", function()
    E.NoteMove(GetTime and GetTime() or 0)
    E.SyncNames(zd, E.cull)
  end)
end

-- the last view again (the grade or what's explored changed: `force` shows and hides every group again)
function E.Refresh(force)
  if force then E.dirty = true end
  local v = E.view
  if v then E.SetView(v[1], v[2], v[3], v[4], v[5], v[6]) end
end

end }
