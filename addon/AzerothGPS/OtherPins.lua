-- Other addons' map icons on the GPS map (asked 2026-11-09: "can we add a default option that any map overlay from
-- other addons automatically show on the GPS map?"; option `otherAddonPins`, on by default, Options > Show on the map).
--
-- Where they come from (read only: nothing of another addon is changed, and everything that touches one is pcall'd):
-- - HereBeDragons-Pins, the library most map addons put their world map icons through, in every copy LibStub has
--   (`OP.Discover`: any library named HereBeDragons...Pins..., e.g. "HereBeDragons-Pins-2.0" and the renamed copies some
--   addons carry). Its `worldmapPinRegistry` (ref -> { icon frame = true }) and `worldmapPins` (icon frame -> { x, y,
--   instanceID, uiMapID, worldMapShowFlag }), x and y its world yards: x = west (UnitPosition's second value), y = north
--   (its first), so AzerothGPS's world x, y (north, west) are its y, x. Its Add/Remove functions are post-hooked
--   (hooksecurefunc: they run as before) to bump `OP.version`, and the pins are indexed by world cells again at most every
--   `REINDEX_MIN` while that changes (`OP.Reindex`): nothing walks the whole registry per redraw.
-- - Zygor's waypoints (ZygorGuidesViewer.Pointer.waypoints: its own world map frames, `frame_worldmap`, not through the
--   library), those it shows on the world map (`overworld`), by their map and 0-1 position (`OP.CheckZygor`).
-- - Every other addon's pins on the game's own world map canvas (asked 2026-11-14: "it should be for all addon map
--   overlays to show on the gps map too just like the world map"; `OP.CheckCanvas`): WorldMapFrame's `pinPools` (template
--   -> pool), the pins an addon's data provider put there with `AcquirePin` (DungeonQuestAtlas' markers and entrances,
--   ShortestPathForever's, any addon's own pin template), by their 0-1 `GetPosition()` on the map the world map last
--   showed (`WorldMapFrame:GetMapID()`) through `ns.Maps` bounds. Never Blizzard's own pins (`OP.BLIZZARD_PINS` and
--   `BLIZZARD_PREFIXES` by template; and any pin the game itself placed: `issecurevariable` says its `pinTemplate` was set
--   by secure code), which AzerothGPS draws its own way; never a pin bigger than `CANVAS_ICON_MAX` (an overlay over the
--   whole map: a route's lines, Zygor's fog), nor one anchored by more than one point. HereBeDragons' own canvas pins
--   (template ^HereBeDragons) only when their icon isn't in a library found above (a copy outside LibStub and Questie:
--   its icon is copied, once). Pins exist only for the map the world map last showed, so these are that map's (a
--   continent's also zoomed out); read again when the canvas's `AcquirePin`/`RemovePin`/`RemoveAllPinsByTemplate`/
--   `OnMapChanged` ran (post-hooks bumping `OP.canvasVersion`), at most every `REINDEX_MIN`, and every `CANVAS_EVERY`
--   while the world map is open (a provider showing or hiding its pins), at most `CANVAS_MAX` of them.
-- Only world map icons: never the libraries' minimap ones. While the map is the minimap square (1.2.0's
-- `G.MinimapMode`) an addon's icons that it also puts on the game's minimap (shown there over the square) are left out.
--
-- Each copy is a button on the map's icon layer (under AzerothGPS's own icons) with the icon's own look (its main
-- texture: file or atlas, texture coordinates, color, rotation; else its text), sized by its own size and the zoom
-- (`OP.Size`), placed again only with the map's own icons (G.Update's gather, `OP.Stamp` in its signature), nearest
-- the view's middle first, at most `MAX_DRAWN`. Hovering one runs the original's OnEnter (its tooltip), a click its
-- OnClick (a right-click it lets through goes to the map), a double-click makes a stop there.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)
local Geo = ns.Geo

local OP = {}
ns.OtherPins = OP

OP.CELL = 400 -- yards per side of an index cell
OP.MAX_DRAWN = 200 -- copies on the map at most
OP.SCAN_MAX = 6000 -- pins looked at in a gather at most (a far view over a huge registry)
OP.REINDEX_MIN = 1 -- s between two indexings while a registry keeps changing (Questie adds its icons in bursts)
OP.ZYGOR_EVERY = 0.5 -- s between looks at Zygor's waypoints
OP.REF_ZOOM = 524 -- the map's default zoom: icons at their own size there
OP.SIZE_MIN, OP.SIZE_MAX = 8, 32 -- UI units
OP.SHOW_CONTINENT, OP.SHOW_WORLD = 2, 3 -- HereBeDragons' show flags (HBD_PINS_WORLDMAP_SHOW_*)
OP.HOOKS = { "AddWorldMapIconWorld", "AddWorldMapIconMap", "RemoveWorldMapIcon", "RemoveAllWorldMapIcons" }
OP.TEX_FIELDS = { "texture", "icon", "Icon", "Texture", "tex", "Center" } -- (where addons keep an icon's main texture)
OP.TEXT_FIELDS = { "text", "Text", "label", "Label" }

OP.version = 0 -- bumped whenever a library's world map icons change (the hooks), or one is found
OP.stamp = 0 -- bumped whenever what the copies are drawn from changed (an indexing, Zygor's waypoints)
OP.libs = {} -- { lib, name, questie, hooked = { [function name] = the hooked function } }
OP.byLib = {}
OP.index = nil
OP.zygor, OP.zygorSig = {}, 0
OP.copies, OP.used = {}, 0
OP.mainOf = setmetatable({}, { __mode = "k" }) -- icon frame -> its main texture (or false: none)
OP.drawn = 0 -- (the last gather's: copies drawn, pins looked at; the tests read them)
OP.scanned = 0

local function S() return ns.settings and ns.settings.gps end
function OP.On()
  local st = S()
  -- (in the game's world map the addons' own icons are there, over the map: no copies, asked 2026-11-10)
  if ns.GPS and ns.GPS.WorldMapHosted and ns.GPS.WorldMapHosted() then return false end
  return st ~= nil and st.otherAddonPins ~= false
end

local function Secret(v) return ns.IsSecret and ns.IsSecret(v) end

function OP.Bump() OP.version = OP.version + 1 end

-- Every HereBeDragons Pins library LibStub has, its Add/Remove functions hooked (again after a newer copy replaced
-- them). Run at every addon loaded and at login: a library comes or upgrades only as an addon's files load.
-- (Questie 12.9.0, 2026-11-13, keeps its copy as a module of its own instead, QuestieLoader._modules.HBDPins: not in
-- LibStub, and its icons went missing from the GPS map; reported 2026-11-14. Read from there too, never created.)
local function Take(lib, name, questie)
  if type(lib) ~= "table" or type(rawget(lib, "worldmapPins")) ~= "table"
    or type(rawget(lib, "worldmapPinRegistry")) ~= "table" then return end
  local rec = OP.byLib[lib]
  if not rec then
    rec = { lib = lib, name = name, questie = questie, hooked = {} }
    OP.byLib[lib] = rec
    OP.libs[#OP.libs + 1] = rec
    OP.Bump()
  end
  for _, fn in ipairs(OP.HOOKS) do
    local f = rawget(lib, fn)
    if type(f) == "function" and rec.hooked[fn] ~= f and hooksecurefunc then
      pcall(hooksecurefunc, lib, fn, OP.Bump)
      rec.hooked[fn] = rawget(lib, fn)
      OP.Bump()
    end
  end
end
function OP.Discover()
  local LS = rawget(_G, "LibStub")
  local libs = type(LS) == "table" and rawget(LS, "libs")
  if type(libs) == "table" then
    for name, lib in pairs(libs) do
      if type(name) == "string" and name:find("^HereBeDragons") and name:find("Pins") then
        Take(lib, name, name:find("Questie") ~= nil)
      end
    end
  end
  local QL = rawget(_G, "QuestieLoader")
  local mods = type(QL) == "table" and rawget(QL, "_modules")
  if type(mods) == "table" then Take(rawget(mods, "HBDPins"), "Questie HBDPins", true) end
  OP.HookCanvas()
end

-- An owner that is AzerothGPS or a companion of it: its icons aren't copied.
function OP.OwnRef(ref, icon)
  if ref == ns or ref == rawget(_G, "AzerothGPS") then return true end
  local name = type(ref) == "string" and ref or (type(ref) == "table" and rawget(ref, "name")) or nil
  if type(name) == "string" and name:find("^AzerothGPS") then return true end
  if icon and icon.GetName then
    local ok, n = pcall(icon.GetName, icon)
    if ok and type(n) == "string" and n:find("^AzerothGPS") then return true end
  end
  return false
end

function OP.Key(x, y)
  return (math.floor(x / OP.CELL) + 1000) * 4096 + (math.floor(y / OP.CELL) + 1000)
end

-- The libraries' world map icons by instance and cell (icons only: their data is read live at the gather, the
-- libraries recycle those tables).
local function Index(now)
  local cells, libOf, refOf, n = {}, {}, {}, 0
  for _, rec in ipairs(OP.libs) do
    local pins, reg = rawget(rec.lib, "worldmapPins"), rawget(rec.lib, "worldmapPinRegistry")
    if type(pins) == "table" and type(reg) == "table" then
      for ref, set in pairs(reg) do
        if type(set) == "table" and not OP.OwnRef(ref) then
          for icon in pairs(set) do
            local d = pins[icon]
            if type(d) == "table" and type(d.x) == "number" and type(d.y) == "number" and type(d.instanceID) == "number" then
              local c = cells[d.instanceID]
              if not c then
                c = { n = 0 }
                cells[d.instanceID] = c
              end
              local k = OP.Key(d.y, d.x) -- (AzerothGPS's x, y: the library's y, x)
              local l = c[k]
              if not l then
                l = {}
                c[k] = l
                c.n = c.n + 1
              end
              l[#l + 1] = icon
              libOf[icon], refOf[icon] = rec, ref
              n = n + 1
            end
          end
        end
      end
    end
  end
  OP.index = { version = OP.version, at = now, cells = cells, libOf = libOf, refOf = refOf, count = n }
  OP.stamp = OP.stamp + 1
end
function OP.Reindex(now)
  local v = OP.version
  local ok, err = pcall(Index, now)
  if not ok then
    OP.index = { version = v, at = now, cells = {}, libOf = {}, refOf = {}, count = 0 }
    OP.stamp = OP.stamp + 1
    if ns.GPS and ns.GPS.LogError then ns.GPS.LogError("other addons' map icons", err) end
  end
end

-- Zygor's waypoints shown on the world map: { frame, cont, x, y, zoneOnly, title }, made again only when they changed.
local function ZygorList()
  local z = rawget(_G, "ZygorGuidesViewer")
  local P = type(z) == "table" and rawget(z, "Pointer")
  local list = type(P) == "table" and rawget(P, "waypoints")
  if type(list) ~= "table" then return nil end
  local icons = rawget(P, "Icons")
  return list, type(icons) == "table" and rawget(icons, "none") or nil
end
local function ZygorWay(w, none)
  if type(w) ~= "table" or not rawget(w, "overworld") or rawget(w, "icon") == none then return nil end
  local m, u, v = rawget(w, "m"), rawget(w, "x"), rawget(w, "y")
  local f = rawget(w, "frame_worldmap")
  local b = type(m) == "number" and ns.Maps and ns.Maps[m] and ns.Maps[m].bounds
  if not (b and type(f) == "table" and type(u) == "number" and type(v) == "number") then return nil end
  return f, b[3] - v * (b[3] - b[1]), b[4] - u * (b[4] - b[2]), m
end
local function CheckZygor()
  local list, none = ZygorList()
  local sig, n = 0, 0
  for i, w in ipairs(list or {}) do
    local f, x, y = ZygorWay(w, none)
    if f then
      n = n + 1
      sig = sig + i * 7 + x * 0.37 + y * 1.13
    end
  end
  if sig == OP.zygorSig and n == #OP.zygor then return end
  OP.zygorSig = sig
  local out = {}
  for _, w in ipairs(list or {}) do
    local f, x, y, m = ZygorWay(w, none)
    if f then
      local ic = rawget(w, "icon")
      local where = type(ic) == "table" and rawget(ic, "onworldmap") or nil
      local title = rawget(w, "title")
      out[#out + 1] = { f, Geo.MapCont(m), x, y, zoneOnly = where ~= nil and where ~= true,
        title = type(title) == "string" and not Secret(title) and title or nil }
    end
  end
  OP.zygor = out
  OP.stamp = OP.stamp + 1
end
function OP.CheckZygor(now)
  if OP.zygorAt and now - OP.zygorAt < OP.ZYGOR_EVERY then return end
  OP.zygorAt = now
  local ok, err = pcall(CheckZygor)
  if not ok and ns.GPS and ns.GPS.LogError then ns.GPS.LogError("Zygor's map icons", err) end
end

-- The game's world map canvas: other addons' pins on the map it last showed (see the top). Read only: the canvas's
-- pools and each pin's own getters; its functions are only post-hooked (hooksecurefunc) to bump `canvasVersion`.
OP.CANVAS_EVERY = 2 -- s between looks while the world map is open
OP.CANVAS_MAX = 400 -- canvas pins copied at most
OP.CANVAS_ICON_MAX = 80 -- UI units: a bigger pin is an overlay laid over the map, not an icon
OP.CANVAS_HOOKS = { "AcquirePin", "RemovePin", "RemoveAllPinsByTemplate", "OnMapChanged" }
-- The game's own pin templates (Blizzard_MapCanvas, Blizzard_SharedMapDataProviders, Blizzard_WorldMap and the modern
-- client's map providers): its quests, POIs, flight points, dungeon entrances, the player and the group, the explored
-- overlays and fog, quest areas, the map's own highlights and links. AzerothGPS draws its own of those.
OP.BLIZZARD_PINS = {}
for _, t in ipairs({ "MapExplorationPinTemplate", "MapHighlightPinTemplate", "MapLinkPinTemplate",
  "GroupMembersPinTemplate", "FlightPointPinTemplate", "DungeonEntrancePinTemplate", "AreaPOIPinTemplate",
  "AreaPOIEventPinTemplate", "AreaPOIBannerPinTemplate", "VignettePinTemplate", "QuestPinTemplate",
  "QuestOfferPinTemplate", "QuestBlobPinTemplate", "QuestHubPinTemplate", "QuestPOIPinTemplate",
  "SuperTrackedQuestPinTemplate", "WorldQuestPinTemplate", "WorldMap_WorldQuestPinTemplate", "BonusObjectivePinTemplate",
  "ThreatObjectivePinTemplate", "StorylineQuestPinTemplate", "WorldMapInvasionOverlayPinTemplate", "InvasionPinTemplate",
  "ScenarioPinTemplate", "ScenarioBlobPinTemplate", "MapIndicatorQuestPinTemplate", "DigSitePinTemplate",
  "PetTamerPinTemplate", "FogOfWarPinTemplate", "EncounterJournalPinTemplate", "ContributionCollectorPinTemplate",
  "CorpsePinTemplate", "DeathReleasePinTemplate", "BattlefieldFlagPinTemplate", "BattlefieldVehiclePinTemplate",
  "BattlefieldPOIPinTemplate", "WaypointLocationPinTemplate", "GossipPinTemplate", "AreaLabelPinTemplate",
  "BaseHighlightableMapPoiPinTemplate", "LegendHighlightablePoiPinTemplate", "SuperTrackableMapPinTemplate",
  "MapPinPingTemplate", "WorldMapPingPinTemplate", "WorldMapThreatEnginePinTemplate", "DelveEntrancePinTemplate",
  "DragonridingRacePinTemplate", "GarrisonPlotPinTemplate", "QuestSessionPinTemplate", "WorldMapTrackingPinTemplate",
  "PlayerPinTemplate", "UnitPositionPinTemplate" }) do OP.BLIZZARD_PINS[t] = true end
OP.BLIZZARD_PREFIXES = { "^FlightMap_", "^AdventureMap_", "^WorldMap_", "^Garrison" }
OP.canvasVersion = 0 -- bumped by the canvas's hooks
OP.canvas = {} -- { { frame, cont, x, y, wide = a continent's map }, ... }
OP.canvasHooked = setmetatable({}, { __mode = "k" }) -- WorldMapFrame -> { [function name] = the hooked function }

function OP.CanvasBump() OP.canvasVersion = OP.canvasVersion + 1 end

-- The canvas's AcquirePin/RemovePin/RemoveAllPinsByTemplate/OnMapChanged post-hooked (again after one was replaced). Run
-- with OP.Discover: the game's world map loads as an addon (ADDON_LOADED), at the latest when first opened.
function OP.HookCanvas()
  local wm = rawget(_G, "WorldMapFrame")
  if type(wm) ~= "table" or type(rawget(wm, "pinPools")) ~= "table" or type(hooksecurefunc) ~= "function" then return end
  local done = OP.canvasHooked[wm]
  if not done then
    done = {}
    OP.canvasHooked[wm] = done
  end
  for _, fn in ipairs(OP.CANVAS_HOOKS) do
    local f = rawget(wm, fn)
    if type(f) == "function" and done[fn] ~= f then
      pcall(hooksecurefunc, wm, fn, OP.CanvasBump)
      done[fn] = rawget(wm, fn)
      OP.CanvasBump()
    end
  end
end

local function Blizzards(tmpl, pin)
  if OP.BLIZZARD_PINS[tmpl] then return true end
  for _, p in ipairs(OP.BLIZZARD_PREFIXES) do
    if tmpl:find(p) then return true end
  end
  -- (placed by the game's own code: an addon's provider runs insecurely, so its pins' fields are never secure)
  local isv = rawget(_G, "issecurevariable")
  if type(isv) == "function" then
    local ok, secure = pcall(isv, pin, "pinTemplate")
    if ok and secure == true then return true end
  end
  return false
end

-- The icon frame is in a HereBeDragons library found by OP.Discover (copied from there already).
local function InLibrary(icon)
  for _, rec in ipairs(OP.libs) do
    local pins = rawget(rec.lib, "worldmapPins")
    if type(pins) == "table" and pins[icon] ~= nil then return true end
  end
  return false
end

local function Num(v) return type(v) == "number" and not Secret(v) end

-- One canvas pin into `out`: the frame to copy (the pin, or HereBeDragons' icon in it) at its world spot.
local function CanvasPin(pin, tmpl, hbd, b, cont, wide, out)
  if type(pin) ~= "table" or not pin.IsShown or pin:IsShown() ~= true then return end
  local frame = pin
  if hbd then
    frame = rawget(pin, "icon")
    if type(frame) ~= "table" or InLibrary(frame) or not frame.IsShown or frame:IsShown() ~= true then return end
  else
    if Blizzards(tmpl, pin) then return end
    if pin.GetNumPoints and (tonumber(pin:GetNumPoints()) or 0) > 1 then return end -- (laid over the map)
    local w, h = pin:GetSize()
    if not (Num(w) and Num(h)) or w > OP.CANVAS_ICON_MAX or h > OP.CANVAS_ICON_MAX then return end
  end
  if OP.OwnRef(nil, frame) then return end
  if type(pin.GetPosition) ~= "function" then return end
  local u, v = pin:GetPosition()
  if not (Num(u) and Num(v)) or u < -0.02 or u > 1.02 or v < -0.02 or v > 1.02 then return end
  out[#out + 1] = { frame, cont, b[3] - v * (b[3] - b[1]), b[4] - u * (b[4] - b[2]), wide = wide }
end

local function CanvasRead()
  local out = {}
  local wm = rawget(_G, "WorldMapFrame")
  local pools = type(wm) == "table" and rawget(wm, "pinPools")
  if type(pools) ~= "table" or type(wm.GetMapID) ~= "function" then return out end
  local m = wm:GetMapID()
  local info = type(m) == "number" and ns.Maps and ns.Maps[m]
  local b = info and info.bounds
  local cont = b and Geo.MapCont(m)
  if not cont then return out end -- (a map with no bounds: the whole world's, a dungeon's)
  local wide = (tonumber(info.type) or 3) <= 2
  for tmpl, pool in pairs(pools) do
    if type(tmpl) == "string" and type(pool) == "table" and type(pool.EnumerateActive) == "function"
      and not tmpl:find("^AzerothGPS") then
      local hbd = tmpl:find("^HereBeDragons") ~= nil
      for pin in pool:EnumerateActive() do
        if #out >= OP.CANVAS_MAX then return out end
        pcall(CanvasPin, pin, tmpl, hbd, b, cont, wide, out) -- (a pin that can't be read is left out alone)
      end
    end
  end
  return out
end

local function SameCanvas(a, b)
  if #a ~= #b then return false end
  for i = 1, #a do
    local p, q = a[i], b[i]
    if p[1] ~= q[1] or p[2] ~= q[2] or p[3] ~= q[3] or p[4] ~= q[4] or p.wide ~= q.wide then return false end
  end
  return true
end

local function WorldMapOpen()
  local wm = rawget(_G, "WorldMapFrame")
  if type(wm) ~= "table" or not wm.IsShown then return false end
  local ok, on = pcall(wm.IsShown, wm)
  return ok and on == true
end

function OP.CheckCanvas(now)
  local due = OP.canvasRead ~= OP.canvasVersion
    or (WorldMapOpen() and now - (OP.canvasAt or -math.huge) >= OP.CANVAS_EVERY)
  if not due or (OP.canvasAt and now - OP.canvasAt < OP.REINDEX_MIN) then return end
  OP.canvasAt, OP.canvasRead = now, OP.canvasVersion
  local ok, res = pcall(CanvasRead)
  if not ok then
    if ns.GPS and ns.GPS.LogError then ns.GPS.LogError("other addons' world map pins", res) end
    res = {}
  end
  if not SameCanvas(res, OP.canvas) then
    OP.canvas = res
    OP.stamp = OP.stamp + 1
  end
end

-- What the copies are drawn from, as a number for the map's icon signature: the icons are gathered again when it
-- changes. Indexes again here (at most every REINDEX_MIN) when a library's icons changed.
function OP.Stamp()
  if not OP.On() then return 0 end
  local now = GetTime()
  OP.CheckZygor(now)
  OP.CheckCanvas(now)
  local ix = OP.index
  if not ix or (ix.version ~= OP.version and now - ix.at >= OP.REINDEX_MIN) then OP.Reindex(now) end
  return OP.stamp
end

-- Something new to draw (the quiet idle map redraws sooner: G.QuietIdle).
function OP.Pending()
  if not OP.On() then return false end
  local ix = OP.index
  if ix and ix.version ~= OP.version then return true end
  if OP.canvasRead ~= OP.canvasVersion then return true end
  local s = OP.stamp
  local now = GetTime()
  OP.CheckZygor(now)
  OP.CheckCanvas(now)
  return OP.stamp ~= s
end

local function IsTexture(t)
  if type(t) ~= "table" or not t.GetObjectType then return false end
  local ok, k = pcall(t.GetObjectType, t)
  return ok and k == "Texture"
end
local function IsFontString(t)
  if type(t) ~= "table" or not t.GetObjectType then return false end
  local ok, k = pcall(t.GetObjectType, t)
  return ok and k == "FontString"
end

-- The icon frame's main texture: a texture kept in one of TEX_FIELDS, else its biggest shown texture with art.
local function FindMain(icon)
  for _, k in ipairs(OP.TEX_FIELDS) do
    local t = rawget(icon, k)
    if IsTexture(t) then return t end
  end
  local best, area
  for _, r in ipairs({ icon:GetRegions() }) do
    -- (never a HIGHLIGHT one: a hover's, as big as the icon on a world map pin's template)
    if IsTexture(r) and r:IsShown() and (r:GetTexture() or (r.GetAtlas and r:GetAtlas()))
      and select(2, pcall(r.GetDrawLayer, r)) ~= "HIGHLIGHT" then
      local w, h = r:GetSize()
      local a = (tonumber(w) or 0) * (tonumber(h) or 0)
      if not best or a > area then best, area = r, a end
    end
  end
  return best
end
function OP.MainTexture(icon)
  local t = OP.mainOf[icon]
  if t == nil then
    local ok, found = pcall(FindMain, icon)
    t = ok and found or false
    OP.mainOf[icon] = t
  end
  return t or nil
end

-- The icon's look, read into `lk` (reused): false when there's nothing to copy (no art, no text, or see-through).
OP.MAX_EXTRAS = 4 -- the icon's other textures copied at most (a glow, a ring, a badge)
OP.LAYERS = { BACKGROUND = true, BORDER = true, ARTWORK = true, OVERLAY = true } -- (never HIGHLIGHT: a hover's)
OP.regionsOf = setmetatable({}, { __mode = "k" }) -- icon frame -> { { texture, child frame or false }, ... }

-- The icon's textures other than its main one, its own and its child frames' (found once per frame).
local function FindRegions(icon, main)
  local out = {}
  local function take(f, child)
    for _, r in ipairs({ f:GetRegions() }) do
      if r ~= main and IsTexture(r) then out[#out + 1] = { r, child or false } end
    end
  end
  take(icon)
  for _, c in ipairs({ icon:GetChildren() }) do
    if type(c) == "table" and c.GetRegions then take(c, c) end
  end
  return out
end
function OP.Regions(icon, main)
  local list = OP.regionsOf[icon]
  if list == nil then
    local ok, found = pcall(FindRegions, icon, main)
    list = ok and found or false
    OP.regionsOf[icon] = list
  end
  return list or nil
end

-- A texture's draw layer and sublevel as the copy can take them (nil layer: HIGHLIGHT, a hover's, never copied).
local function DrawLayer(t)
  local ok, layer, sub = pcall(t.GetDrawLayer, t)
  if ok and layer == "HIGHLIGHT" then return nil, 0 end
  if not ok or type(layer) ~= "string" or not OP.LAYERS[layer] then layer = "ARTWORK" end
  sub = ok and type(sub) == "number" and not Secret(sub) and math.max(-8, math.min(7, sub)) or 0
  return layer, sub
end

-- The texture's place on its frame: its size (0 when anchored by two corners or unsized: the frame's) and its offset
-- from the frame's middle, in the frame's units.
local function Placement(t)
  local w, h = t:GetSize()
  w, h = tonumber(w) or 0, tonumber(h) or 0
  if Secret(w) or Secret(h) then w, h = 0, 0 end
  local ox, oy = 0, 0
  local n = t.GetNumPoints and t:GetNumPoints() or 0
  if n == 1 then
    local p, _, rp, x, y = t:GetPoint(1)
    if p == "CENTER" and rp == "CENTER" and type(x) == "number" and type(y) == "number" and not (Secret(x) or Secret(y)) then
      ox, oy = x, y
    end
  elseif n > 1 then
    w, h = 0, 0
  end
  return w, h, ox, oy
end

-- Questie draws an objective's glow, colored by its quest, only while the world map shows the icon (its OnShow; its
-- OnHide hides it): with the world map closed, the glow it would show there (_QuestieFrame.BaseOnShow's rule).
local function QuestieGlow(icon, glow)
  if rawget(icon, "glowTexture") ~= glow or rawget(icon, "miniMapIcon") then return nil end
  local Q = rawget(_G, "Questie")
  local ok, on = pcall(function() return Q.db.profile.alwaysGlowMap end)
  local data = rawget(icon, "data")
  local od = type(data) == "table" and rawget(data, "ObjectiveData")
  local c = type(od) == "table" and rawget(od, "Color")
  local kind = type(data) == "table" and rawget(data, "Type")
  if not (ok and on == true and type(c) == "table" and type(kind) == "string" and kind ~= "available"
    and kind ~= "complete") then return nil end
  return tonumber(c[1]) or 1, tonumber(c[2]) or 1, tonumber(c[3]) or 1
end

-- The icon's other textures shown (or Questie's glow it would show) into lk.extras (pooled tables), lk.nx of them.
local function ReadExtras(icon, main, lk, iw, ih)
  lk.nx = 0
  local list = OP.Regions(icon, main)
  if not list then return end
  for _, e in ipairs(list) do
    if lk.nx >= OP.MAX_EXTRAS then break end
    local t, child = e[1], e[2]
    local shown = t:IsShown() and (not child or child:IsShown())
    local gr, gg, gb
    if not shown and not child then gr, gg, gb = QuestieGlow(icon, t) end
    local layer, sub = DrawLayer(t)
    if (shown or gr) and layer then
      local atlas = t.GetAtlas and t:GetAtlas()
      atlas = type(atlas) == "string" and atlas ~= "" and not Secret(atlas) and atlas or nil
      local file = not atlas and t:GetTexture() or nil
      if (type(file) ~= "number" and type(file) ~= "string") or Secret(file) then file = nil end
      if atlas or file then
        lk.nx = lk.nx + 1
        local x = lk.extras[lk.nx]
        if not x then
          x = { coords = {} }
          lk.extras[lk.nx] = x
        end
        x.atlas, x.tex, x.coords.ok = atlas, file, false
        if file then
          local c = x.coords
          c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[8] = t:GetTexCoord()
          c.ok = true
          for i = 1, 8 do
            if Secret(c[i]) or type(c[i]) ~= "number" then c.ok = false end
          end
        end
        x.layer, x.sub = layer, sub
        local r, g, b, a = t:GetVertexColor()
        if Secret(r) or Secret(g) or Secret(b) or Secret(a) then r, g, b, a = 1, 1, 1, 1 end
        x.r, x.g, x.b, x.a = tonumber(r) or 1, tonumber(g) or 1, tonumber(b) or 1, tonumber(a) or 1
        local ta = t.GetAlpha and t:GetAlpha()
        if type(ta) == "number" and not Secret(ta) then x.a = x.a * ta end
        local bl = t.GetBlendMode and t:GetBlendMode()
        x.blend = bl == "ADD" and "ADD" or "BLEND"
        local w, h, ox, oy = Placement(t)
        if child then
          local cw, ch, cox, coy = Placement(child)
          ox, oy = ox + cox, oy + coy
          if w <= 0 or h <= 0 then w, h = cw, ch end
        end
        if gr then -- (Questie's glow as its OnShow sets it: 1.13 times the icon, the quest's color, the icon's alpha)
          w, h, ox, oy = iw * 1.13, ih * 1.13, 0, 0
          x.r, x.g, x.b, x.a = gr, gg, gb, lk.a
        end
        if w <= 0 or h <= 0 then w, h = iw, ih end
        x.w, x.h, x.ox, x.oy = w, h, ox, oy
        if x.a <= 0 then lk.nx = lk.nx - 1 end
      end
    end
  end
end

local function ReadLook(icon, lk)
  lk.tex, lk.atlas, lk.text = nil, nil, nil
  lk.extras = lk.extras or {}
  lk.nx, lk.layer, lk.sub = 0, "ARTWORK", 0
  lk.r, lk.g, lk.b, lk.a = 1, 1, 1, 1
  lk.desat, lk.rot, lk.blend, lk.coords = false, 0, "BLEND", nil
  if rawget(icon, "hidden") == true then return false end -- (Questie's FakeHide)
  local alpha = icon:GetAlpha()
  if Secret(alpha) or (tonumber(alpha) or 1) <= 0 then return false end
  lk.alpha = tonumber(alpha) or 1
  local t = OP.MainTexture(icon)
  if t then lk.layer, lk.sub = DrawLayer(t) end
  lk.layer = lk.layer or "ARTWORK"
  if t and t:IsShown() then
    local atlas = t.GetAtlas and t:GetAtlas()
    if type(atlas) == "string" and atlas ~= "" and not Secret(atlas) then
      lk.atlas = atlas
    else
      local file = t:GetTexture()
      if (type(file) == "number" or type(file) == "string") and not Secret(file) then lk.tex = file end
      local c = lk.buf
      c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[8] = t:GetTexCoord()
      local okc = true
      for i = 1, 8 do
        if Secret(c[i]) or type(c[i]) ~= "number" then okc = false end
      end
      if okc then lk.coords = c end
    end
    local r, g, b, a = t:GetVertexColor()
    if not (Secret(r) or Secret(g) or Secret(b) or Secret(a)) then
      lk.r, lk.g, lk.b, lk.a = tonumber(r) or 1, tonumber(g) or 1, tonumber(b) or 1, tonumber(a) or 1
    end
    local ta = t.GetAlpha and t:GetAlpha()
    if type(ta) == "number" and not Secret(ta) then lk.a = lk.a * ta end
    if lk.a <= 0 then return false end -- (faded out: Questie's FadeOut, an icon its filters hide)
    local d = t.IsDesaturated and t:IsDesaturated()
    lk.desat = d == true
    local rot = t.GetRotation and t:GetRotation()
    if type(rot) == "number" and not Secret(rot) then lk.rot = rot end
    local bl = t.GetBlendMode and t:GetBlendMode()
    if type(bl) == "string" then lk.blend = bl end
  end
  for _, k in ipairs(OP.TEXT_FIELDS) do
    local fs = rawget(icon, k)
    if IsFontString(fs) and fs:IsShown() then
      local s = fs:GetText()
      if type(s) == "string" and s ~= "" and not Secret(s) then
        lk.text = s
        local r, g, b = fs:GetTextColor()
        if Secret(r) or Secret(g) or Secret(b) then r, g, b = 1, 0.82, 0 end
        lk.tr, lk.tg, lk.tb = tonumber(r) or 1, tonumber(g) or 0.82, tonumber(b) or 0
        break
      end
    end
  end
  if not lk.tex and not lk.atlas and not lk.text then return false end
  local w, h = icon:GetSize()
  local sc = icon:GetScale()
  w, h, sc = tonumber(w) or 0, tonumber(h) or 0, tonumber(sc) or 1
  if Secret(w) or Secret(h) or w <= 0 or h <= 0 then w, h = 16, 16 end
  if Secret(sc) or sc <= 0 then sc = 1 end
  lk.w, lk.h = w * sc, h * sc
  ReadExtras(icon, t, lk, w, h)
  for i = 1, lk.nx do -- (in the copy's units: the icon's scale in them)
    local x = lk.extras[i]
    x.w, x.h, x.ox, x.oy = x.w * sc, x.h * sc, x.ox * sc, x.oy * sc
  end
  return true
end
OP.ReadLook = function(icon, lk)
  local ok, res = pcall(ReadLook, icon, lk)
  return ok and res
end

-- The copy's size (UI units, the long side): the icon's own, a little smaller zoomed out and bigger zoomed in.
function OP.Size(own, zoom)
  local k = (OP.REF_ZOOM / math.max(zoom or OP.REF_ZOOM, 1)) ^ 0.3
  k = math.max(0.6, math.min(1.25, k))
  return math.max(OP.SIZE_MIN, math.min(OP.SIZE_MAX, own * k))
end

-- The original frame may be talked to: not protected, not forbidden.
local function Usable(o)
  if type(o) ~= "table" then return false end
  local ok, p = pcall(o.IsProtected, o)
  if not ok or p == true or Secret(p) then return false end
  if o.IsForbidden then
    local okf, f = pcall(o.IsForbidden, o)
    if not okf or f == true or Secret(f) then return false end
  end
  return true
end
local function Script(o, name)
  local ok, fn = pcall(o.GetScript, o, name)
  return ok and type(fn) == "function" and fn or nil
end

-- A right-click the original doesn't take goes to the map (Questie lets it through, RestedXP's take no clicks).
function OP.PassesRight(o)
  if not Usable(o) then return true end
  if o.IsMouseClickEnabled then
    local ok, on = pcall(o.IsMouseClickEnabled, o)
    if ok and on == false then return true end
  end
  if o.ShouldButtonPassThrough then
    local ok, pass = pcall(o.ShouldButtonPassThrough, o, "RightButton")
    if ok and (pass == true or Secret(pass)) then return true end
  end
  if o.ShouldMouseButtonBePassthrough then -- (a world map canvas pin's own say: MapCanvasPinMixin)
    local ok, pass = pcall(o.ShouldMouseButtonBePassthrough, o, "RightButton")
    if ok and (pass == true or Secret(pass)) then return true end
  end
  return not (Script(o, "OnClick") or Script(o, "OnMouseUp"))
end

-- The tooltips an original may show its text in (TomTom has one of its own).
OP.TOOLTIPS = { "GameTooltip", "WorldMapTooltip", "TomTomTooltip" }
local function Shown(tip)
  local ok, on = pcall(tip.IsShown, tip)
  return ok and on == true
end
-- Each tooltip in OP.TOOLTIPS shown and owned by `a` or `b`: fn(tip, owner).
local function EachOwned(a, b, fn)
  for _, name in ipairs(OP.TOOLTIPS) do
    local tip = rawget(_G, name)
    if type(tip) == "table" and tip.GetOwner and Shown(tip) then
      local ok, owner = pcall(tip.GetOwner, tip)
      if ok and owner ~= nil and (owner == a or owner == b) then fn(tip, owner) end
    end
  end
end

-- While an original's OnEnter runs from its copy (`OP.entering`), a tooltip it gives a hidden owner (the original
-- itself, or the world map: both hidden while the world map is closed) is given the copy instead. The game doesn't
-- show a tooltip whose owner is hidden, so Questie's (owned by its icon, anchored on the cursor) showed nothing and
-- our "Another addon's map icon" came up in its place (reported 2026-11-12). A post-hook (hooksecurefunc) on each
-- tooltip's SetOwner, made once per tooltip at the first hover: the addon's own call runs as before, and its lines
-- then go into the tooltip owned by the copy, with the anchor it asked for.
OP.hooked = {}
local function ReOwn(tip, owner, anchor, x, y)
  local e = OP.entering
  if not e or OP.reowning or owner == nil or owner == e.b then return end
  if owner ~= e.orig then
    local ok, vis = pcall(owner.IsVisible, owner)
    if not ok or vis ~= false then return end
  end
  OP.reowning = true
  pcall(tip.SetOwner, tip, e.b, type(anchor) == "string" and anchor or "ANCHOR_RIGHT", x, y)
  OP.reowning = false
end
local function HookOwners()
  if type(hooksecurefunc) ~= "function" then return end
  for _, name in ipairs(OP.TOOLTIPS) do
    local tip = rawget(_G, name)
    if type(tip) == "table" and not OP.hooked[tip] and type(tip.SetOwner) == "function" then
      OP.hooked[tip] = true
      pcall(hooksecurefunc, tip, "SetOwner", ReOwn)
    end
  end
end

-- Questie's tooltip lists the icons on the game's world map round the hovered one, those its map has as pins: with
-- that map closed, or on another zone, none, the tooltip came up empty and the game didn't show it (on the GPS map
-- only; in the world map its own icons are there, reported 2026-11-12). Questie's own call for a hovered minimap path
-- (MapIconTooltip.ShowOnTooltip with an owner and icons) lists the icons given wherever they are: the hovered one and
-- Questie's others drawn at its spot (its NPC's quests), owned by the copy. False when that isn't there.
OP.QUESTIE_NEAR_PX = 10
function OP.QuestieTooltip(b)
  local o = b.orig
  local ix = OP.index
  local rec = ix and ix.libOf and ix.libOf[o]
  if not (rec and rec.questie) then return false end
  local QL = rawget(_G, "QuestieLoader")
  local tip = rawget(_G, "GameTooltip")
  if type(QL) ~= "table" or type(QL.ImportModule) ~= "function" or type(tip) ~= "table" then return false end
  local okM, M = pcall(QL.ImportModule, QL, "MapIconTooltip")
  if not okM or type(M) ~= "table" or type(M.ShowOnTooltip) ~= "function" then return false end
  local list, listed = { o }, { [o] = true }
  for i = 1, OP.used do
    local c = OP.copies[i]
    local co = c and c.orig
    if co and not listed[co] and ix.libOf[co] == rec and c.dx and b.dx
      and math.abs(c.dx - b.dx) <= OP.QUESTIE_NEAR_PX and math.abs(c.dy - b.dy) <= OP.QUESTIE_NEAR_PX then
      listed[co] = true
      list[#list + 1] = co
    end
  end
  local ok, err = pcall(M.ShowOnTooltip, o, tip, b, list)
  if not ok then
    OP.lastError = tostring(err)
    return false
  end
  local okO, owner = pcall(tip.GetOwner, tip)
  return okO and owner == b and Shown(tip)
end

function OP.OnEnter(b)
  local o = b.orig
  local G = ns.GPS
  local function Hint(tip) -- (the controller's button while it's in use, Pad.used)
    if G and G.PadTipLine and G.PadTipLine(tip, "select") then
      -- (by the icon, the crosshair's spot, as ours are: an addon's cursor anchor would follow the unused mouse;
      -- asked 2026-11-17, "Questie icons for example seem to be random, can all tooltips go to crosshair")
      pcall(tip.SetAnchorType, tip, "ANCHOR_NONE")
      pcall(tip.ClearAllPoints, tip)
      pcall(tip.SetPoint, tip, "BOTTOMLEFT", b, "TOPRIGHT", 0, 0)
      return
    end
    pcall(tip.AddLine, tip, L["Double-click: add as a stop"], 0.4, 0.8, 1)
  end
  if Usable(o) and OP.QuestieTooltip(b) then
    Hint(GameTooltip)
    pcall(GameTooltip.Show, GameTooltip)
    if not b.stopName then
      local line = rawget(_G, "GameTooltipTextLeft1")
      local first = line and line.GetText and line:GetText()
      if type(first) == "string" and first ~= "" and not Secret(first) then b.stopName = first end
    end
    return
  end
  if Usable(o) then
    local fn = Script(o, "OnEnter")
    if fn then
      HookOwners()
      OP.entering = { orig = o, b = b }
      local ok, err = pcall(fn, o, false)
      OP.entering = nil
      if not ok then OP.lastError = tostring(err) end
    end
  end
  local any = false
  EachOwned(o, b, function(tip, owner)
    any = true
    Hint(tip)
    pcall(tip.Show, tip)
    -- (anchored on the original, hidden with the world map: on the copy instead; a cursor anchor stays)
    if owner == o and not (o.IsVisible and o:IsVisible()) and not (ns.Pad and ns.Pad.used) then
      local okA, anchor = pcall(tip.GetAnchorType, tip)
      if not (okA and type(anchor) == "string" and anchor:find("CURSOR")) then
        pcall(tip.ClearAllPoints, tip)
        pcall(tip.SetPoint, tip, "BOTTOMLEFT", b, "TOPRIGHT", 0, 0)
      end
    end
    if not b.stopName then
      local line = rawget(_G, (tip.GetName and tip:GetName() or "") .. "TextLeft1")
      local first = line and line.GetText and line:GetText()
      if type(first) == "string" and first ~= "" and not Secret(first) then b.stopName = first end
    end
  end)
  if any then return end
  local tip = rawget(_G, "GameTooltip")
  if not tip then return end
  tip:SetOwner(b, "ANCHOR_RIGHT")
  tip:SetText(b.title or L["Another addon's map icon"], 1, 1, 1)
  local ref = OP.index and OP.index.refOf and OP.index.refOf[o] -- (the addon's name, when it registered by one)
  if type(ref) == "string" and ref ~= "" and not Secret(ref) and ref ~= b.title then tip:AddLine(ref, 0.6, 0.6, 0.6) end
  tip:AddLine(L["Double-click: add as a stop"], 0.4, 0.8, 1)
  tip:Show()
end

function OP.OnLeave(b)
  local o = b.orig
  if Usable(o) then
    local fn = Script(o, "OnLeave")
    if fn then pcall(fn, o) end
  end
  EachOwned(o, b, function(tip) pcall(tip.Hide, tip) end)
end

function OP.OnClick(b, button)
  local o = b.orig
  if button == "RightButton" and OP.PassesRight(o) then
    local mf = rawget(_G, "AzerothGPSFrame")
    local down = mf and Script(mf, "OnMouseDown")
    if down then pcall(down, mf, "RightButton") end
    return
  end
  if not Usable(o) then return end
  if o.IsMouseClickEnabled then
    local ok, on = pcall(o.IsMouseClickEnabled, o)
    if ok and on == false then return end
  end
  local fn = Script(o, "OnClick")
  if fn then
    pcall(fn, o, button, false)
    return
  end
  fn = Script(o, "OnMouseUp")
  if fn then pcall(fn, o, button, true) end
end

function OP.OnDoubleClick(b)
  local G = ns.GPS
  if not (G and G.AddStopAt) or (G.Held and G.Held()) then return end
  G.AddStopAt(b.wx, b.wy, b.stopName or b.title, b.cont)
end

local function Copy(i, layer)
  local b = OP.copies[i]
  if b then return b end
  b = CreateFrame("Button", nil, layer)
  b.agpsOtherPin = true
  b.agpsNoLook = true
  local G = ns.GPS
  if G and G.clickThrough then b.agpsMouse, b.agpsWheel = true, false; b:EnableMouse(false) end
  b.tex = b:CreateTexture(nil, "ARTWORK")
  b.tex:SetAllPoints()
  b.label = b:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  b.label:SetPoint("CENTER", b, "CENTER", 0, 0)
  b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  b:SetScript("OnEnter", OP.OnEnter)
  b:SetScript("OnLeave", OP.OnLeave)
  b:SetScript("OnClick", OP.OnClick)
  b:SetScript("OnDoubleClick", OP.OnDoubleClick)
  OP.copies[i] = b
  return b
end

local look = { buf = {} }
-- One copy placed: the icon `icon` (its look read now) at (dx, dy) on the layer; false when it has nothing to show.
local function Place(layer, icon, dx, dy, zoom, wx, wy, cont, title, dup)
  if not OP.ReadLook(icon, look) then return false end
  local key = string.format("%d:%d:%s", math.floor(wx), math.floor(wy), tostring(look.atlas or look.tex or look.text))
  if dup[key] then return false end -- (the same icon twice at one spot: RestedXP's for a zone and its subzone)
  dup[key] = true
  OP.used = OP.used + 1
  local b = Copy(OP.used, layer)
  b.orig, b.wx, b.wy, b.cont, b.title = icon, wx, wy, cont, title
  b.stopName = nil -- (the original's tooltip's first line, read when hovered)
  local t = b.tex
  if look.atlas then
    t:SetAtlas(look.atlas)
    t:Show()
  elseif look.tex then
    t:SetTexture(look.tex)
    if look.coords then
      local c = look.coords
      t:SetTexCoord(c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[8])
    else
      t:SetTexCoord(0, 1, 0, 1)
    end
    t:Show()
  else
    t:Hide()
  end
  t:SetVertexColor(look.r, look.g, look.b, look.a)
  t:SetDesaturated(look.desat)
  if t.SetRotation then t:SetRotation(look.rot) end
  t:SetBlendMode(look.blend == "ADD" and "ADD" or "BLEND")
  t:SetDrawLayer(look.layer, look.sub)
  local long = math.max(look.w, look.h)
  local size = OP.Size(long, zoom)
  local f = size / long -- (the copy's units per the original's)
  b:SetSize(look.w * f, look.h * f)
  -- the icon's other textures (Questie's glow under it, a ring, a badge): pooled per copy, in their own layers
  b.extras = b.extras or {}
  for i = 1, look.nx do
    local x = look.extras[i]
    local e = b.extras[i]
    if not e then
      e = b:CreateTexture(nil, "ARTWORK")
      b.extras[i] = e
    end
    if x.atlas then
      e:SetAtlas(x.atlas)
    else
      e:SetTexture(x.tex)
      local c = x.coords
      if c.ok then e:SetTexCoord(c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[8]) else e:SetTexCoord(0, 1, 0, 1) end
    end
    e:SetDrawLayer(x.layer, x.sub)
    e:SetVertexColor(x.r, x.g, x.b, x.a)
    e:SetBlendMode(x.blend)
    e:ClearAllPoints()
    e:SetPoint("CENTER", b, "CENTER", x.ox * f, x.oy * f)
    e:SetSize(x.w * f, x.h * f)
    e:Show()
  end
  for i = look.nx + 1, #b.extras do b.extras[i]:Hide() end
  if look.text then
    b.label:SetText(look.text)
    b.label:SetTextColor(look.tr, look.tg, look.tb)
    b.label:Show()
  else
    b.label:Hide()
  end
  b:SetAlpha(look.alpha)
  b:ClearAllPoints()
  b:SetPoint("CENTER", layer, "CENTER", dx, dy)
  b.dx, b.dy = dx, dy -- (OP.QuestieTooltip: the copies at its spot)
  b:SetFrameLevel(layer:GetFrameLevel()) -- (under AzerothGPS's own icons, the layer's children)
  b:Show()
  return true
end

-- The square minimap's game minimap shows this owner's minimap icons: its world map ones would double them.
local function OnMinimap(rec, ref, memo)
  local v = memo[ref]
  if v == nil then
    local reg = rawget(rec.lib, "minimapPinRegistry")
    local set = type(reg) == "table" and reg[ref]
    v = type(set) == "table" and next(set) ~= nil or false
    memo[ref] = v
  end
  return v
end

local cand, seen, mmMemo = {}, {}, {}
local function Gather(layer, cx, cy, viewCont, rot, s, half, zoom, far)
  local ix = OP.index
  local base = Geo.Base(viewCont)
  local G = ns.GPS
  local square = G and G.MinimapMode and G.MinimapMode() or false
  local hideQuestie = false -- (Questie's own "hide icons on continents", for its icons zoomed out)
  if far then
    local Q = rawget(_G, "Questie")
    local okQ, h = pcall(function() return Q.db.profile.hideIconsOnContinents end)
    hideQuestie = okQ and h == true
  end
  wipe(seen)
  wipe(mmMemo)
  local scanned = 0
  local function Try(icon, ax, ay, wx, wy, cont, title)
    scanned = scanned + 1
    local dx, dy = Geo.ScreenOffset(cx, cy, wx, wy)
    dx, dy = Geo.Rotate(dx * s, dy * s, rot)
    if math.abs(dx) > half or math.abs(dy) > half then return end
    Place(layer, icon, dx, dy, zoom, ax, ay, cont, title, seen)
  end
  local function Wanted(icon, d, rec)
    if far and ((d.worldMapShowFlag or 0) < OP.SHOW_CONTINENT or (rec.questie and hideQuestie)) then return false end
    if square and OnMinimap(rec, ix.refOf[icon], mmMemo) then return false end
    return true
  end
  -- the continent in view: its cells round the view's middle, nearest first
  local c = ix and ix.cells[base]
  if c then
    local reach = half / s * 1.42 + OP.CELL
    local ix0, iy0 = math.floor(cx / OP.CELL), math.floor(cy / OP.CELL)
    local r = math.ceil(reach / OP.CELL)
    wipe(cand)
    if (2 * r + 1) ^ 2 > c.n then
      for k in pairs(c) do
        if k ~= "n" then
          local kx, ky = math.floor(k / 4096) - 1000, k % 4096 - 1000
          if math.abs(kx - ix0) <= r and math.abs(ky - iy0) <= r then cand[#cand + 1] = k end
        end
      end
    else
      for kx = ix0 - r, ix0 + r do
        for ky = iy0 - r, iy0 + r do
          local k = (kx + 1000) * 4096 + (ky + 1000)
          if c[k] then cand[#cand + 1] = k end
        end
      end
    end
    table.sort(cand, function(a, b)
      local ax, ay = math.floor(a / 4096) - 1000 - ix0, a % 4096 - 1000 - iy0
      local bx, by = math.floor(b / 4096) - 1000 - ix0, b % 4096 - 1000 - iy0
      return ax * ax + ay * ay < bx * bx + by * by
    end)
    for _, k in ipairs(cand) do
      for _, icon in ipairs(c[k]) do
        if OP.used >= OP.MAX_DRAWN or scanned >= OP.SCAN_MAX then break end
        local rec = ix.libOf[icon]
        local pins = rec and rawget(rec.lib, "worldmapPins")
        local d = pins and pins[icon]
        if d and d.instanceID == base and Wanted(icon, d, rec) then
          Try(icon, d.y, d.x, d.y, d.x, base)
        end
      end
      if OP.used >= OP.MAX_DRAWN or scanned >= OP.SCAN_MAX then break end
    end
  end
  -- zoomed out: the other continents' icons shown on the world map too
  if far and ix then
    for inst, ci in pairs(ix.cells) do
      if inst ~= base then
        for k, list in pairs(ci) do
          if k ~= "n" then
            for _, icon in ipairs(list) do
              if OP.used >= OP.MAX_DRAWN or scanned >= OP.SCAN_MAX then break end
              local rec = ix.libOf[icon]
              local pins = rec and rawget(rec.lib, "worldmapPins")
              local d = pins and pins[icon]
              if d and d.instanceID == inst and (d.worldMapShowFlag or 0) >= OP.SHOW_WORLD and Wanted(icon, d, rec) then
                local wx, wy = Geo.ToContinent(inst, d.y, d.x, viewCont)
                if wx then Try(icon, d.y, d.x, wx, wy, inst) end
              end
            end
          end
        end
      end
    end
  end
  -- other addons' pins on the game's world map canvas (the map it last showed; zoomed out, a continent's map's only)
  for _, p in ipairs(OP.canvas) do
    if OP.used >= OP.MAX_DRAWN or scanned >= OP.SCAN_MAX then break end
    if not (far and not p.wide) then
      local wx, wy
      if Geo.Base(p[2]) == base then
        wx, wy = p[3], p[4]
      elseif far then
        wx, wy = Geo.ToContinent(p[2], p[3], p[4], viewCont)
      end
      if wx then Try(p[1], p[3], p[4], wx, wy, p[2]) end
    end
  end
  -- Zygor's waypoints (a few; in the square, Zygor's own minimap ones show on the game's minimap over it)
  if not square then
    for _, z in ipairs(OP.zygor) do
      if OP.used >= OP.MAX_DRAWN then break end
      if not (far and z.zoneOnly) and z[2] then
        local wx, wy
        if Geo.Base(z[2]) == base then
          wx, wy = z[3], z[4]
        elseif far then
          wx, wy = Geo.ToContinent(z[2], z[3], z[4], viewCont)
        end
        if wx then Try(z[1], z[3], z[4], wx, wy, z[2], z.title) end
      end
    end
  end
  OP.scanned = scanned
end

-- The copies for the view (G.Update's icon gather, on the icon layer): `mode` "near" (a zone's worth: every icon),
-- "far" (a continent's or the world's: those the libraries show on a continent's or the world map) or "none".
function OP.Draw(layer, cx, cy, viewCont, rot, s, half, zoom, mode)
  OP.used = 0
  local G = ns.GPS
  if layer and mode ~= "none" and OP.On() and not (G and G.Held and G.Held()) and viewCont and s and s > 0 then
    if not OP.index then OP.Reindex(GetTime()) end
    local ok, err = pcall(Gather, layer, cx, cy, viewCont, rot, s, half, zoom, mode == "far")
    if not ok and G and G.LogError then G.LogError("other addons' map icons", err) end
  end
  OP.drawn = OP.used
  for i = OP.used + 1, #OP.copies do
    local b = OP.copies[i]
    b:Hide()
    b.orig = nil
  end
end

local ev = CreateFrame("Frame")
ev:RegisterEvent("ADDON_LOADED")
ev:RegisterEvent("PLAYER_LOGIN")
ev:SetScript("OnEvent", function() OP.Discover() end)
