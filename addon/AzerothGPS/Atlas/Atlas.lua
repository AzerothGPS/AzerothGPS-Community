-- The seamless map's art (issues #49, #57, #60, #61): AzerothGPS's stitched world map, every zone's map art on one
-- canvas, drawn under AzerothGPS's own map as its wheel zooms out past the land, through the zones and continents to
-- the whole world (GPSFrame's G.Seamless, G.ArtBlend). The default map style ("seamless", issue #75; the Map Style
-- buttons). Its data (Atlas/Data) and engine (Atlas/Engine, docs/atlas-spec.md) are chunks, each a function in
-- ns.AtlasChunks, run at login (`A.Load`) with the data's table and the engine's; another style, they're dropped at
-- login (`A.Init`) and nothing of them is kept. Picked mid-session it loads after a /reload: a prompt with a Reload UI
-- button says so (`A.AskReload`, issue #56). Blizzard's map and other map addons are never touched.
-- The art's view: a world point (u, v), normalized on Azeroth's map (947), and a zoom (1: the whole world fits the
-- view); the canvas is scaled and moved, the art laid out once on it in world units.

--
-- The whole of it is one function (BuildAtlas, to the end of the file), run once for the map and once more for the
-- second map (GPSFrame.lua's G.clone: the minimap square while the first map is in the game's world map window): the
-- art has one place on one map, so the second map has an engine and art of its own, from the same chunks and data.
local function BuildAtlas(...)
local ADDON, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)

local A = {
  WORLD = 947,
  ART_RANGE = 80,           -- frame levels the art needs
  EDGE_UV = 0.03,           -- a spot this near a continent's rectangle on the world map is on it
}
ns.Atlas = A

-- The engine's own table (Atlas/Engine: its files' `E`) and its data (Atlas/Data: `D`)
local E = { TEX = "Interface\\AddOns\\" .. ADDON .. "\\Atlas\\Media\\Textures\\" }
A.core, A.data = E, {}

--------------------------------------------------------------------------------
-- The art's view maths (pure: tested in app/tests/test_atlas.py)
--------------------------------------------------------------------------------

-- view px per world unit with the whole world fitting a w x h view (world W x H units)
function A.FitPx(w, h, W, H) return math.min(w / W, h / H) end

-- the zoom the layers fade by: by the area of the world in view, so a tall or very wide view
-- doesn't bring the zones in while it still shows a continent's worth
function A.DetailK(w, h, W, H)
  if w <= 0 or h <= 0 then return 1 end
  return math.min(w / W, h / H) / math.sqrt(w * h / (W * H))
end

-- the canvas's scale (world unit -> view px) and its corner's offset from the view's top left (in its own units), so
-- that (u, v) is at the view's middle
function A.Place(u, v, zoom, w, h, W, H)
  local s = A.FitPx(w, h, W, H) * zoom
  return s, w / (2 * s) - u * W, -(h / (2 * s) - v * H)
end

-- AzerothGPS's world yards (x north, y west, on continent 0 / 1) on Azeroth's map, by a continent's rectangle there
-- (Data/Maps.lua's worldFrames: { minX, minY, maxX, maxY, u0, v0, u1, v1 }, the game's UiMapAssignment), and back.
-- In the game the engine's own projection comes first (E.YardsToUV: the continent's corners by
-- C_Map.GetWorldPosFromMapPos, on its rectangle by C_Map.GetMapRectOnMap(map, 947)); these are the fallback.
function A.FromFrame(wf, x, y)
  return wf[5] + (wf[4] - y) / (wf[4] - wf[2]) * (wf[7] - wf[5]), wf[6] + (wf[3] - x) / (wf[3] - wf[1]) * (wf[8] - wf[6])
end
function A.ToFrame(wf, u, v)
  return wf[3] - (v - wf[6]) / (wf[8] - wf[6]) * (wf[3] - wf[1]), wf[4] - (u - wf[5]) / (wf[7] - wf[5]) * (wf[4] - wf[2])
end

-- Each continent's frame on Azeroth's map: the world map's own (Data/Maps.lua's worldFrames), and an isle on a map of
-- its own (Zephras Isle, map 2991: not on the world map's art, issue #60) by its zone's rectangle where the game puts it
-- on Azeroth's map (E.MapRect), else where AzerothGPS's own map draws it (GPSFrame's WORLD_INSETS, as Geo.ToContinent
-- does): the art's view over it goes over to its yards (G.SeamRebase), so its terrain comes back zoomed in there.
local frames
local function Frames()
  if frames then return frames end
  local w = ns.Maps and ns.Maps[A.WORLD]
  local out = {}
  for c, wf in pairs(w and w.worldFrames or {}) do out[c] = wf end
  local G = ns.GPS
  for _, it in ipairs(G and G.WORLD_INSETS or {}) do
    local m = ns.Maps and ns.Maps[it.map]
    local b = m and m.bounds
    if b and m.continent and not out[m.continent] then
      local u0, v0, u1, v1 = it.u0, it.v0, it.u1, it.v1
      local l, r, t, bt = nil, nil, nil, nil
      if A.E and A.E.MapRect then l, r, t, bt = A.E.MapRect(it.map) end
      if l and r > l and bt > t then u0, v0, u1, v1 = l, t, r, bt end
      out[m.continent] = { b[1], b[2], b[3], b[4], u0, v0, u1, v1, isle = it.map }
    end
  end
  if A.loaded ~= nil then frames = out end -- (kept once the engine is loaded, or failed to)
  return out
end
A.Frames = Frames

-- whether the engine's projection works here (checked once: it needs the game's map calls; else the frames)
function A.Projection()
  local e = A.E
  if A.ownProjection == nil and e and e.YardsToUV then
    local ok, u = pcall(e.YardsToUV, 0, 0, 0)
    A.ownProjection = ok and u ~= nil
  end
  return A.ownProjection or false
end

-- a spot (level, x, y) on the art (u, v); nil off it (a dungeon's level)
function A.ToAtlas(cont, x, y)
  if not (cont and x and y) then return nil end
  local l = ns.CityLevels and ns.CityLevels[cont]
  if l and l.instance then return nil end
  local base = l and l.base or cont -- (an underground city: drawn in its continent's coordinates)
  local wf = Frames()[base]
  if A.Projection() and not (wf and wf.isle) then
    local u, v = A.E.YardsToUV(base, x, y)
    if u and v then return u, v end
  end
  if wf then return A.FromFrame(wf, x, y) end
  return nil
end

-- the continent under (u, v) on the world map, and the spot there in its yards: (cont, x, y), or nil in the sea
-- between them
function A.FromAtlas(u, v)
  local best, bestD
  for cont, wf in pairs(Frames()) do
    local du = math.max(wf[5] - u, 0, u - wf[7])
    local dv = math.max(wf[6] - v, 0, v - wf[8])
    local d = math.max(du, dv)
    if d <= A.EDGE_UV and (not bestD or d < bestD) then best, bestD = cont, d end
  end
  if not best then return nil end
  if A.Projection() and not Frames()[best].isle then
    local x, y = A.E.UVToYards(best, u, v)
    if x and y then return best, x, y end
  end
  local x, y = A.ToFrame(Frames()[best], u, v)
  return best, x, y
end

-- /agps seamless spots (QA's coordinate check): well-known spots on the art by the engine's projection, the zone
-- the game has there (the deepest under it, E.ChainAt: C_Map.GetMapInfoAtPosition down from Azeroth's map) against
-- the zone AzerothGPS's own data has at the spot, how far it is from the game's own frames (px of the world map's art),
-- and the way back (A.FromAtlas: the continent, and yards off). Kept for the QA's saved-file reading (ns.db.seamCheck,
-- a debug log: the last check only).
A.CHECK_SPOTS = { { "Stormwind", 0, -8840.6, 489.7 }, { "Goldshire", 0, -9465.0, 64.0 }, { "Brill", 0, 2254.0, 293.0 },
  { "Ironforge", 0, -4981.0, -880.0 }, { "Orgrimmar", 1, 1676.0, -4315.0 }, { "Thunder Bluff", 1, -1196.0, -40.0 },
  { "Darnassus", 1, 9947.0, 2482.0 }, { "Dolanaar", 1, 9850.0, 960.0 }, { "Rut'theran Village", 1, 8700.0, 970.0 },
  { "Moonglade", 1, 7800.0, -2500.0 } }

-- the zone's name the game has at (u, v) (issues #58, #205): the deepest Zone of E.ChainAt; where the chain stops above
-- one (the map under the spot a dungeon's, a micro map's or an orphan's: ChainAt stops there), that map's own parents
-- up to a Zone; else the chain's last map, as before
function A.GameZoneAt(u, v)
  if not (C_Map and C_Map.GetMapInfo) then return nil end
  local ok, chain = pcall(A.E.ChainAt, u, v)
  if not (ok and type(chain) == "table" and #chain > 0) then return nil end
  local T = Enum and Enum.UIMapType
  local zoneType = T and T.Zone or 3
  local function Info(id)
    local ok2, info = pcall(C_Map.GetMapInfo, id)
    return ok2 and type(info) == "table" and info or nil
  end
  local function Named(info) return info and type(info.name) == "string" and info.name or nil end
  for i = #chain, 1, -1 do
    local info = Info(chain[i])
    if info and info.mapType == zoneType then return Named(info) end
  end
  local deepest = chain[#chain]
  local x, y = u, v
  if deepest ~= A.E.WORLD and C_Map.GetMapRectOnMap then
    local ok3, l, r, t, b = pcall(C_Map.GetMapRectOnMap, deepest, A.E.WORLD)
    if ok3 and type(l) == "number" and type(r) == "number" and type(t) == "number" and type(b) == "number"
        and r > l and b > t then
      x, y = (u - l) / (r - l), (v - t) / (b - t)
    end
  end
  if C_Map.GetMapInfoAtPosition then
    local ok4, info = pcall(C_Map.GetMapInfoAtPosition, deepest, x, y)
    info = ok4 and type(info) == "table" and info or nil
    for _ = 1, 6 do
      if not info or info.mapID == deepest then break end
      if info.mapType == zoneType then return Named(info) end
      info = info.parentMapID and Info(info.parentMapID)
    end
  end
  return Named(Info(deepest))
end

function A.CheckMapping()
  if not A.Load() then
    ns.Print("the seamless map isn't loaded (the OpenMap map style, then /reload).")
    return {}
  end
  local w = ns.Maps and ns.Maps[A.WORLD]
  local W, H = w and w.artW or 1002, w and w.artH or 668
  local out = {}
  local G = ns.GPS
  ns.Print("Seamless map spots (" .. (A.Projection() and "the map's own projection" or "the game's frames only") .. "):")
  for _, p in ipairs(A.CHECK_SPOTS) do
    local u, v = A.ToAtlas(p[2], p[3], p[4])
    local wf = Frames()[p[2]]
    if u and wf then
      local fu, fv = A.FromFrame(wf, p[3], p[4])
      local off = math.sqrt(((u - fu) * W) ^ 2 + ((v - fv) * H) ^ 2)
      local zone = A.GameZoneAt(u, v) or "?"
      local _, mine = nil, nil
      if G and G.LocateWorld then _, mine = G.LocateWorld(p[2], p[3], p[4]) end
      local c2, x2, y2 = A.FromAtlas(u, v)
      local back = c2 and x2 and math.sqrt((x2 - p[3]) ^ 2 + (y2 - p[4]) ^ 2) or -1
      out[#out + 1] = { p[1], u, v, zone, off, mine or "?", c2 or -1, back }
      ns.Print(string.format("  %s: %.5f, %.5f in %s (ours: %s), %.1f px off the frames, back: continent %s, %.1f yd off",
        p[1], u, v, zone, mine or "?", off, tostring(c2), back))
    end
  end
  if ns.db then
    local c = ns.db.seamCheck or {}
    ns.db.seamCheck = c
    c.at, c.spots = time and time() or 0, out
  end
  return out
end

--------------------------------------------------------------------------------
-- Loading
--------------------------------------------------------------------------------

-- the data's and engine's chunks run, once: true when the engine is there
function A.Load()
  if A.loaded ~= nil then return A.loaded end
  local list = ns.AtlasChunks
  ns.AtlasChunks = nil
  local second = ns.isMapClone == true
  if second then -- (the second map's: the first one's chunks again for an engine of its own, its data as it is)
    local first = ns.realAtlas
    list = first and first.loaded and first.chunkList or nil
    A.data = first and first.data or A.data
  end
  if not list then return false end -- (dropped at login: turned on since, a /reload loads it)
  if not second then A.chunkList = list end -- (kept while it's on: the second map's engine is made from them)
  for _, chunk in ipairs(list) do
    local ok, err = true, nil
    if not (second and chunk[1]:find("^data/")) then ok, err = pcall(chunk[2], A.data, E) end
    if not ok then
      A.loadError = chunk[1] .. ": " .. tostring(err)
      A.loaded = false
      return false
    end
  end
  A.E = E.Build and E or nil
  A.loaded = A.E ~= nil
  if A.E then A.E.STAGES = A.STAGES end -- (the player's stages, set before it loaded: A.SetStages)
  A.CLOSE_DEFAULTS = {} -- (the close-up's knobs as shipped: issue #72's Reset)
  if A.E and E.KNOBS then
    for _, k in ipairs(A.CLOSE_KNOBS) do A.CLOSE_DEFAULTS[k[1]] = E.KNOBS[k[1]] end
  end
  return A.loaded
end

-- whether it's on but waits for a /reload (turned on this session: its files were let go at login, and loading them
-- without one would mean keeping them while it's off)
function A.NeedsReload()
  return A.Wanted() and not A.loaded and not ns.AtlasChunks and not A.loadError
end

-- whether the stitched map is wanted at login: the Seamless map style (issue #75; once the `seamlessZoom` option, issues
-- #57, #60). Never for a held style (API.HoldMap): those draw as they always did
function A.Wanted()
  -- (and for the map in the minimap's place: its square is always the seamless map, GPSFrame.lua's G.SquareStyle)
  -- (No Map picked: the style it stands in for out of the world map, GPSFrame.lua's G.NoMapFallback)
  local st = ns.settings.gps
  return st.style == "seamless" or st.replaceMinimap == true
    or (st.style == "none" and (st.styleBeforeNone == nil or st.styleBeforeNone == "seamless"))
end

-- On screen (issue #56: a chat line went unseen): the seamless map loads after a /reload, with a Reload UI button.
-- Mid-screen over the options window (it's turned on there). The Reload UI button is a secure "/reload" the player
-- clicks (ns.SecureReloadButton: ReloadUI() is blocked here), over the prompt's own; in combat only that one, which
-- says to /reload after (ns.SaveNow refuses in combat).
function A.AskReload(text)
  local f = ns.Ask("AzerothGPSAtlasReload", text or A.SEAMLESS_RELOAD_TEXT, L["Reload UI"], L["Later"], function()
    if not ns.SaveNow() then ns.Print(L["in combat: /reload once it's over to load it."]) end
  end, nil, { strata = "FULLSCREEN_DIALOG" })
  if f and not A.reloadBtn and ns.SecureReloadButton then
    A.reloadBtn = ns.SecureReloadButton(f.yes, f, "AzerothGPSAtlasReloadButton")
    if A.reloadBtn then f:HookScript("OnHide", A.reloadBtn.Sync) end
  end
  if A.reloadBtn then A.reloadBtn.Sync() end
  return f
end

-- PLAYER_LOGIN: off, the art's chunks are let go (nothing of them kept); on, they're run (the art is built
-- the first time the map zooms out to it)
function A.Init()
  if A.Wanted() then
    A.Load()
  else
    ns.AtlasChunks = nil
  end
end

A.SEAMLESS_RELOAD_TEXT = L["The OpenMap map style is on. It loads after the UI is reloaded: reload now?\n\nThen the map's mouse wheel zooms on out to the whole world."]

-- the Seamless style picked (GPSFrame's G.SetStyle, issue #75): it needs a /reload unless the engine was loaded at
-- login and the map made room for its art then (G.ArtSpan); another style draws as it always has at once
function A.ReloadIfNeeded()
  local G = ns.GPS
  if ns.settings.gps.style == "seamless" and (A.NeedsReload() or not (G and G.ArtSpan and G.ArtSpan() > 0)) then
    ns.Print(L["the seamless map loads after a /reload."])
    A.AskReload(A.SEAMLESS_RELOAD_TEXT)
  end
end

-- `/agps seamless on|off` (the old option's command): the Seamless style on, or off to Terrain
function A.SetSeamless(on)
  local G = ns.GPS
  if G and G.SetStyle then return G.SetStyle(on and "seamless" or "minimap") end
  ns.settings.gps.style = on and "seamless" or "minimap"
end

-- What the art shows of the zones the character hasn't explored (issue #60, `seamExploredOnly`): "hide" them (each
-- zone's blank parchment there, as on the game's own world map), else "show" every area. The engine does it
-- piece by piece from the game's explored-map data (E.Grade, E.Rescan): no seams between zones.
function A.Unexplored()
  return ns.settings.gps.seamExploredOnly == true and "hide" or "show"
end

-- the art's colour settings: the colour match in full, a little desaturation (as the baked zones), unexplored areas as
-- the setting says
function A.ApplyGrade()
  if A.E and A.artHost then A.E.Grade(1, 0.1, A.Unexplored()) end
  A.IsleOverlays()
end

-- "Show Only Explored Areas" changed (Options > Map)
function A.SetExploredOnly(on)
  ns.settings.gps.seamExploredOnly = on and true or false
  A.ApplyGrade()
  local G = ns.GPS
  if G and G.Redraw then G.Redraw() end
end

-- The detail zoom (and the plain zoom with it) the art is told on AzerothGPS's map: no closer than the closeUpFrom knob
-- (8: the zones' map whole and sharp, E.Fades' softening not begun, the minimap not mixed in). Closer in, the engine
-- draws its close-up: the zones blurred, grained and the minimap mixed over them. With the terrain's tiles going at about
-- 4,000 yd that never showed; at the tuned stages (issue #90: the tiles gone by 410 yd) it filled 410 to 1,500 yd, and
-- zooming in went from the world's art through that blur to the terrain without the zones' (revealed) map, and the
-- coasts faded into it. The canvas is still placed by the real zoom: only the fades stop at the zones' stage.
function A.TellZoom(zd, zp)
  local most = A.E.KNOBS and A.E.KNOBS.closeUpFrom
  if most and zd > most then return most, zp * most / zd end
  return zd, zp
end

-- a view (u, v, zoom) of a w x h box put on the canvas and told to the engine (not again unchanged)
function A.ApplyView(u, v, zoom, w, h, W, H)
  local was = A.applied
  if was and was[1] == u and was[2] == v and was[3] == zoom and was[4] == w and was[5] == h then return end
  A.applied = { u, v, zoom, w, h }
  local s, ox, oy = A.Place(u, v, zoom, w, h, W, H)
  local c = A.canvas
  c:SetScale(s)
  c:ClearAllPoints()
  c:SetPoint("TOPLEFT", A.artHost, "TOPLEFT", ox, oy)
  local zd, zp = A.TellZoom(zoom * A.DetailK(w, h, W, H), zoom)
  A.E.SetView(u, v, w / 2 / (W * s), h / 2 / (H * s), zd, zp)
end

--------------------------------------------------------------------------------
-- The art's own frame, and the seamless zoom on AzerothGPS's map (issue #57)
--------------------------------------------------------------------------------

-- The art is built once (thousands of textures, their files set only as they come into view), on a
-- frame of its own (A.artHost: it clips; A.canvas in it, scaled and moved) under AzerothGPS's map: `parent` its parent,
-- `box` the region it covers, `level` its frame level (the art's levels follow it: A.ART_RANGE + 2 over it). True when
-- the art is there.
function A.AttachArt(parent, box, level)
  if A.artFailed or not A.Load() then return false end
  local e, host = A.E, A.artHost
  if not host then
    host = CreateFrame("Frame", nil, parent)
    if host.SetClipsChildren then host:SetClipsChildren(true) end
    host:SetAllPoints(box)
    host:SetFrameLevel(level)
    local canvas = CreateFrame("Frame", nil, host)
    canvas:SetSize(1, 1)
    canvas:SetPoint("TOPLEFT")
    local l = level + 1
    e.Build(canvas, l, A.ART_RANGE, l + A.ART_RANGE + 1)
    if not e.IsBuilt() then
      A.artFailed = true
      host:Hide()
      ns.Print(L["the seamless map couldn't be built: the game gave no world map art."])
      return false
    end
    e.SetShown(true)
    A.artHost, A.canvas, A.artBox = host, canvas, box
    A.DrawIsles(canvas, l + 2)
    A.ApplyGrade()
    -- (the player explored somewhere: the art's pieces there aren't unexplored any more)
    local ev = CreateFrame("Frame")
    ev:RegisterEvent("MAP_EXPLORATION_UPDATED")
    ev:SetScript("OnEvent", function()
      e.Rescan()
      A.IsleOverlays(true)
    end)
    A.exploreEvents = ev
    return true
  end
  if A.artBox ~= box then -- (another box)
    host:SetParent(parent)
    host:ClearAllPoints()
    host:SetAllPoints(box)
    host:SetFrameLevel(level)
    A.artBox, A.applied = box, nil
  end
  if not host:IsShown() then host:Show() end
  return true
end

-- An isle on a map of its own (Zephras Isle, issue #72): the stitched map draws only the zones the game puts on
-- Azeroth's map, so the isle's frame there (Frames(), its inset) was open sea. Its own map's art (the game's tiles, by
-- file id: Data/Maps.lua) is laid over that frame through its land mask (Media/Textures/MapIsle/<map>, `agps
-- isle-mask`: the island alone, fading out into the sea; issues #87, #90: the whole page round it, parchment, clouds and
-- towers, was a light square with hard edges in the world's sea), under the stitched map's zones (one the game does
-- place there draws over it) and shown at every zoom the art is (it has no continent art to give way to). Its areas
-- revealed over the tiles as every other zone's are (A.IsleOverlays: its map's overlays, only those explored with
-- "Show Only Explored Areas"): the tiles alone are the map's unrevealed parchment.
-- `level` the frame level, under the engine's zones. Returns the isles drawn ({ map = n, textures, overlays }).
A.ISLE_MASK = "MapIsle"

-- a texture or mask stretched over a world box (u, v normalized on Azeroth's map) of the engine's canvas
local function PlaceUV(r, frame, u0, v0, u1, v1)
  local W, H = A.E.Size()
  r:ClearAllPoints()
  r:SetPoint("TOPLEFT", frame, "TOPLEFT", u0 * W, -v0 * H)
  r:SetSize((u1 - u0) * W, (v1 - v0) * H)
end

function A.DrawIsles(canvas, level)
  A.isles = {}
  if not (A.E and A.E.Size()) then return A.isles end
  for _, wf in pairs(Frames()) do
    local m = wf.isle and ns.Maps and ns.Maps[wf.isle]
    if m and m.tiles and m.artW and m.artH and m.artW > 0 and m.artH > 0 then
      local f = CreateFrame("Frame", nil, canvas)
      f:SetSize(1, 1)
      f:SetPoint("TOPLEFT")
      f:SetFrameLevel(level)
      local mask = f.CreateMaskTexture and f:CreateMaskTexture()
      if mask then
        mask:SetTexture(A.E.Tex(A.ISLE_MASK, wf.isle), "CLAMPTOBLACKADDITIVE", "CLAMPTOBLACKADDITIVE")
        PlaceUV(mask, f, wf[5], wf[6], wf[7], wf[8])
      end
      local isle = { map = wf.isle, frame = f, textures = {}, overlays = {}, pool = {}, mask = mask, wf = wf }
      for _, t in ipairs(m.tiles) do
        isle.textures[#isle.textures + 1] = A.IsleTexture(isle, t, 0)
      end
      A.isles[#A.isles + 1] = isle
    end
  end
  A.IsleOverlays()
  return A.isles
end

-- an art tile ({ file, x, y, w, h, texture w, texture h } in the isle's map's art pixels) on its frame, through its
-- mask, `sub` sublayers up (or `tex` again, a pooled one); nil when the tile is past the art's edge
function A.IsleTexture(isle, t, sub, tex)
  local m, wf = ns.Maps[isle.map], isle.wf
  local w, h = math.min(t[4], m.artW - t[2]), math.min(t[5], m.artH - t[3])
  if w <= 0 or h <= 0 then return nil end
  local du, dv = (wf[7] - wf[5]) / m.artW, (wf[8] - wf[6]) / m.artH
  if not tex then
    tex = isle.frame:CreateTexture(nil, "ARTWORK", nil, sub)
    if isle.mask then tex:AddMaskTexture(isle.mask) end
  end
  tex:SetTexture(t[1], nil, nil, "LINEAR")
  tex:SetTexCoord(0, w / t[6], 0, h / t[7])
  local u0, v0 = wf[5] + t[2] * du, wf[6] + t[3] * dv
  PlaceUV(tex, isle.frame, u0, v0, u0 + w * du, v0 + h * dv)
  tex:Show()
  return tex
end

-- The isles' revealed areas over their tiles: every overlay of their map, or with "Show Only Explored Areas" those this
-- character explored (GPSFrame's G.ExploredOverlays; `fresh` after MAP_EXPLORATION_UPDATED, not its cached list).
function A.IsleOverlays(fresh)
  for _, isle in ipairs(A.isles or {}) do
    local m = ns.Maps[isle.map]
    local list = m.overlays or {}
    local G = ns.GPS
    if A.Unexplored() == "hide" then
      if fresh and G and G.ForgetExplored then G.ForgetExplored(isle.map) end
      list = G and G.ExploredOverlays and G.ExploredOverlays(isle.map) or {}
    end
    for _, tex in ipairs(isle.overlays) do
      tex:Hide()
      isle.pool[#isle.pool + 1] = tex
    end
    isle.overlays = {}
    for _, t in ipairs(list) do
      local tex = A.IsleTexture(isle, t, 1, table.remove(isle.pool))
      if tex then isle.overlays[#isle.overlays + 1] = tex end
    end
  end
end

-- The close-up's knobs (the engine's E.KNOBS: minimapFrom, minimapDeep, soften, closeUpFrom; issue #72,
-- AzerothGPS.SeamKnobs): its name, least, most ("boolean": on or off); set through A.SetCloseKnob (the view told to the
-- art again at the next redraw). nil before the engine is loaded.
A.CLOSE_KNOBS = { { "minimapFrom", 1, 60 }, { "minimapDeep", 0, 1 }, { "soften", "boolean" }, { "closeUpFrom", 1, 100 } }
function A.CloseKnob(name)
  if A.loaded then return A.E.KNOBS[name] end
end
function A.SetCloseKnob(name, value)
  if not A.loaded then return false end
  for _, k in ipairs(A.CLOSE_KNOBS) do
    if k[1] == name then
      if value == nil then value = A.CLOSE_DEFAULTS[name] end
      if k[2] == "boolean" then
        if type(value) ~= "boolean" then return false end
      elseif type(value) ~= "number" or value ~= value then
        return false
      else
        value = math.min(k[3], math.max(k[2], value))
      end
      A.E.KNOBS[name] = value
      A.applied = nil
      return true
    end
  end
  return false
end

-- The player's stages (GPSFrame's G.ApplySeamPlayer, Options > Map): the engine's fades' groups moved and widened,
-- { zone = { k, w }, world = { k, w } } (E.StageRange; nil or a group left out: as shipped). Kept here for an engine
-- loaded later; the view told to the art again at the next redraw.
function A.SetStages(stages)
  A.STAGES = stages
  if A.E then A.E.STAGES = stages end
  A.applied = nil
end

A.YARD_PROBE = 1000 -- yards between the two spots a view's scale on the art is measured by (the projection is linear)

-- AzerothGPS's map's view (its middle cx, cy on level `cont`, `s` px a yard, a w x h box) on the art: the
-- world point (u, v) at its middle and the zoom (A.Place's) that draws a yard `s` px, and the art's yards across over
-- its yards down (1: the same both ways; the game's frames have it within 0.1%); nil off the art. The scale is the
-- mean of the two ways, so neither is off by more than half that.
function A.ViewOfYards(cont, cx, cy, s, w, h, W, H)
  local u, v = A.ToAtlas(cont, cx, cy)
  if not u then return nil end
  local D = A.YARD_PROBE
  local ue = A.ToAtlas(cont, cx, cy - D) -- (D yards east: y is west)
  local _, vs = A.ToAtlas(cont, cx - D, cy) -- (D yards south)
  if not (ue and vs) then return nil end
  local ku, kv = math.abs(ue - u) * W / D, math.abs(vs - v) * H / D -- (world units a yard, across and down)
  if ku <= 0 or kv <= 0 then return nil end
  return u, v, s / math.sqrt(ku * kv) / A.FitPx(w, h, W, H), ku / kv
end

-- The art under AzerothGPS's map (GPSFrame's G.Update, while the seamless zoom shows it): `box` the map's canvas,
-- `alpha` its share. False when it isn't drawn (off the art, no art).
function A.ShowOnMap(parent, box, level, cont, cx, cy, s, alpha)
  local t0 = ns.PerfStart and ns.PerfStart()
  if not A.AttachArt(parent, box, level) then return false end
  local W, H = A.E.Size()
  local w, h = box:GetWidth(), box:GetHeight()
  local u, v, zoom = nil, nil, nil
  if W and w > 0 and h > 0 then u, v, zoom = A.ViewOfYards(cont, cx, cy, s, w, h, W, H) end
  if not u then
    A.HideOnMap(box)
    return false
  end
  A.ApplyView(u, v, zoom, w, h, W, H)
  A.artHost:SetAlpha(alpha)
  A.onMap = { u = u, v = v, zoom = zoom }
  if t0 then ns.PerfEnd("redraw: seamless art", t0) end
  return true
end

-- /agps seamless check (QA's coordinate check, issue #57): where the well-known spots and the player are on the map by
-- its own projection (GPSFrame's view, Geo) and by the art's placement under it, and how far apart (px); { name, px }
function A.CheckSeamless()
  local G, Geo, m = ns.GPS, ns.Geo, A.onMap
  local view = G and G.shownView
  -- (the blend now, issue #60's readings per notch: kept in the saved file's debug log, ns.db.seamCheck.blend)
  local r = G and G.SeamReading and G.SeamReading()
  if r then
    ns.Print(string.format("Seamless blend: %.0f yd (%.0f at the reference size, notch %+.1f from the terrain's %d): "
      .. "art %.2f, tiles %.2f%s", r.zoom, r.ref, r.notch, G.SEAM_TERRAIN_ZOOM, r.art, r.tiles,
      r.artOnly and ", the art alone" or r.edge and ", the art where the terrain has no tiles"
      or r.interior and ", the art round the interior's rooms" or ""))
    if ns.db then
      local c = ns.db.seamCheck or {}
      ns.db.seamCheck = c
      c.blend = c.blend or {}
      table.insert(c.blend, r)
      while #c.blend > 60 do table.remove(c.blend, 1) end -- (a debug log: the last readings)
    end
  end
  if not (m and view and A.artHost and A.artHost:IsShown()) then
    ns.Print("the seamless map's art isn't showing here: zoom the map out past the land for its alignment.")
    return {}
  end
  local W, H = A.E.Size()
  local box = A.artBox
  local w, h = box:GetWidth(), box:GetHeight()
  local s, ox, oy = A.Place(m.u, m.v, m.zoom, w, h, W, H)
  local spots = { { "You", nil } }
  for _, p in ipairs(A.CHECK_SPOTS) do spots[#spots + 1] = p end
  local out = {}
  ns.Print(string.format("Seamless map alignment (%.0f yd, %s):", view.s > 0 and (math.max(w, h) / 2 / view.s) or 0,
    A.Projection() and "the map's own projection" or "the game's frames only"))
  for _, p in ipairs(spots) do
    local cont, x, y = p[2], p[3], p[4]
    if not cont then x, y, cont = Geo.PlayerWorld() end
    local mx, my = nil, nil
    if x then mx, my = Geo.ToContinent(cont, x, y, view.cont) end
    local u, v = A.ToAtlas(cont, x, y)
    if mx and my and u then
      local dx, dy = Geo.ScreenOffset(view.x, view.y, mx, my)
      local ax, ay = (u * W + ox) * s - w / 2, -(oy - v * H) * s - h / 2
      local off = math.sqrt((ax - dx * view.s) ^ 2 + (ay + dy * view.s) ^ 2)
      out[#out + 1] = { p[1], off }
      ns.Print(string.format("  %s: %.1f px apart", p[1], off))
    end
  end
  return out
end

-- the art off AzerothGPS's map
function A.HideOnMap(box)
  local host = A.artHost
  if host and A.artBox == box and host:IsShown() then host:Hide() end
  A.onMap = nil
end

return A
end -- (BuildAtlas)

local addonName, addon = ...
BuildAtlas(addonName, addon)
-- The second map's own (GPSFrame.lua's MakeMapClone): over its stand-in for the addon's table.
function addon.MakeAtlasClone(proxy) return BuildAtlas(addonName, proxy) end
