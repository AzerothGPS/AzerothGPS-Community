-- The tutorial (1.2.0, asked 2026-11-09): a short tour of the main features on the player's own map. Only on request
-- (Kooki3z, 2026-11-25: "Let's make the tutorials only on request from the Help section"): Options > Help's buttons or
-- /agps tutorial start it; no popup ever offers it (not at a first install, not after an update, not after a /reload
-- cut one short). A first install gets the setup (Setup.lua), an update What's New (WhatsNew.lua).
--
-- A SECTION (T.SECTIONS, in order; its `id` is saved, never rename one; `version`: the release that added it, for the
-- (new) / (updated) marks in Help's list) is a list of STEPS. A step: `title`, `text` (a string, or a
-- function giving one), and
--   enter(run)   sets up everything the step needs, whatever came before (the player may have skipped, gone back or
--                jumped here): steps never rely on the one before. Run in a pcall: a failure shows "can't be done
--                here" with Skip Step.
--   target(run)  the control to point at (the glow follows it), or nil.
--   done(run)    the player did it (polled T.POLL apart): the step is one the player does, with Skip Step. None: the
--                step is shown, with Next.
--   blocked(run) true, or a text: it can't be done right now (said, with Next).
--   choices(run) buttons of its own in the panel ({ { label, onClick }, ... }).
--   poll(run)    run at each look while the step waits (a tool that turns itself off put on again).
--   when()       false leaves the step out (looked at as the section starts).
--   `minimized`  the step is done on the minimized map (it isn't brought back first).
-- run.mark is the step's own memory (emptied at each step), run.memo the section's.
-- `full` on a section: it needs the whole map window (the map as the minimap is opened out and held out, G.mmHold).
--
-- THE SNAPSHOT RULE: the tutorial only ever changes what T.Snapshot() takes first (the whole of settings.gps, the
-- character's route, the stops waiting, the map's view, the road and wall tools) and T.RestoreLive puts back, at the
-- end of every section and at the end or exit of the tutorial; it's saved (db.tutorial.run) while a tutorial runs, so
-- a /reload or a crash restores it at the next login (T.RestoreSaved, before anything reads the settings). Anything a
-- new step changes must be in the snapshot. The player's data is never written: example herbs and ore are
-- Layers.demoNodes (in memory only). The one
-- thing kept: "Keep the GPS map as your minimap?" answered Yes (the option on, at the size picked).
-- Display only: the tutorial drives AzerothGPS's own windows and settings, never the character or the game's own UI.
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)
local Format = ns.Format or string.format

local T = {}
ns.Tutorial = T

T.POLL = 0.1 -- seconds between looks at whether the player did the step
T.DONE_PAUSE = 0.8 -- seconds "Done!" shows before the next step
T.HOLD = "tutorial" -- G.mmHold's value: the map as the minimap held opened out
T.ORDER = { "minimap", "route", "quests", "arrow", "cities", "gather", "pins", "search", "dungeon", "window" }
T.RAGEFIRE = 389 -- Ragefire Chasm's map id (the dungeon map shown)
T.FILL_MAX = 160 -- the glow fills what it points at up to this wide (UI units); wider, the outline alone
-- the example across the sea, from each continent (world x, y, continent, the game's own name for the place's map)
T.FAR = {
  Horde = { [0] = { 1676, -4315, 1, 1454 }, [1] = { 2254, 293, 0, 1420 } },
  Alliance = { [0] = { 6439, 614, 1, 1439 }, [1] = { -8833, 628, 0, 1453 } },
}
-- the example herbs and ore: { yards north, yards west, name, kind } from the player
T.NODES = {
  { 70, 20, "Peacebloom", "herb" }, { 40, 75, "Copper Vein", "ore" }, { -30, 80, "Silverleaf", "herb" },
  { -75, 25, "Tin Vein", "ore" }, { -60, -50, "Earthroot", "herb" }, { 30, -70, "Copper Vein", "ore" },
}
-- what of the character's saved record the snapshot takes (the route, and the guide routes that put stops in it)
T.CHAR_KEYS = { "stops", "loop", "dest", "redOk", "skipLearn", "skipRides", "rxpFollow", "zygorFollow", "polestarFollow", "questifyFollow", "aprFollow", "openxpFollow" }

local function GPS() return ns.GPS end
local function S() return ns.settings.gps end
local function Tut() return ns.db and ns.db.tutorial end
local function Copy(v)
  if type(v) ~= "table" then return v end
  local o = {}
  for k, x in pairs(v) do o[k] = Copy(x) end
  return o
end
T.Copy = Copy

-- "1.2.0" as a number to compare.
function T.VersionNumber(v)
  local a, b, c = tostring(v or ""):match("^(%d+)%.?(%d*)%.?(%d*)")
  return (tonumber(a) or 0) * 1e6 + (tonumber(b) or 0) * 1e3 + (tonumber(c) or 0)
end

---------------------------------------------------------------------------
-- The snapshot: taken before the first step, put back at each section's end and at the end
---------------------------------------------------------------------------

function T.Snapshot()
  local g, cdb = GPS(), ns.CharDB()
  local R = ns.Record
  local snap = { char = ns.CharKey(), profile = ns.ProfileName and ns.ProfileName() or nil,
    gps = Copy(S()), cdb = {}, view = false, pending = Copy(g.PendingStops()),
    roadMode = g.roadMode or nil, wallMode = g.wallMode or nil, mapEditOpen = g.mapEditOpen or nil,
    recWindow = R and R.window and R.window:IsShown() and true or nil }
  for _, k in ipairs(T.CHAR_KEYS) do snap.cdb[k] = Copy(cdb[k]) end
  local ok, v = pcall(g.SaveView)
  snap.view = ok and v and Copy(v) or false
  return snap
end

-- The saved part put back: the settings (into the same table, whichever it is now) and the character's route.
function T.RestoreData(snap)
  -- (the profile they were taken from: at the next login the character may be another, on another profile)
  local set = ns.settings
  if snap.profile then
    local p = type(ns.db.profiles) == "table" and ns.db.profiles[snap.profile]
    if type(p) == "table" and type(p.gps) == "table" then set = p end
  elseif snap.char and snap.char ~= ns.CharKey() and type(ns.db.settings.gps) == "table" then
    set = ns.db.settings
  end
  local cur = set.gps
  for k in pairs(cur) do cur[k] = nil end
  for k, v in pairs(snap.gps) do cur[k] = Copy(v) end
  local cdb = ns.db.chars and ns.db.chars[snap.char]
  if cdb then
    for _, k in ipairs(T.CHAR_KEYS) do cdb[k] = Copy(snap.cdb[k]) end
  end
end

-- What the answer to "Keep the GPS map as your minimap?" keeps, over the settings just put back; and the two
-- "back to the minimap" options ticked in the tutorial itself (asked 2026-11-10: offered there, so kept).
T.BACK_KEYS = { "replaceMinimapCollapseOnMove", "replaceMinimapCollapseOnCombat" }
-- The world map option shown on its own step: on (the step entered), the game's map opened with the GPS map in it;
-- off (the step left), the game's map closed and the map in its own window again for the steps after.
function T.WorldMapPreview(on)
  local st, G = S(), ns.GPS
  if not (st and G and G.ToggleWorldMap) then return end
  local wm = rawget(_G, "WorldMapFrame")
  if not wm then return end
  if not on and st.useWorldMap ~= true then return end -- (never on here: the game's map as the player has it)
  st.useWorldMap = on and true or false
  G.ApplySettings()
  local shown = wm:IsShown() and true or false
  if on and not shown then G.ToggleWorldMap() elseif not on and shown then G.CloseWorldMap() end
  G.WorldMapChanged()
end
function T.ApplyKeep(run, final)
  if not run then return end
  local st = S()
  -- (the world map option, ticked in the map window's section: only as the tutorial ends, since it runs on the map's
  -- own window)
  if final and run.keepOpts and run.keepOpts.useWorldMap ~= nil then st.useWorldMap = run.keepOpts.useWorldMap end
  for _, keys in ipairs({ T.BACK_KEYS }) do
    for _, k in ipairs(keys) do
      if run.keepOpts and run.keepOpts[k] ~= nil then st[k] = run.keepOpts[k] end
    end
  end
  -- ("Any shape", ticked in the map window's section: as its checkbox in the options sets it, from the player's size)
  local free = run.keepOpts and run.keepOpts.freeSize
  if free ~= nil and free ~= (st.freeSize and true or false) then
    st.freeSize = free
    st.width = free and st.size or nil
  end
  if not run.keep then return end
  st.replaceMinimap = true
  if run.keepSize then st.replaceMinimapSize = run.keepSize end
end

-- One stage of putting things back, on its own: a failure in it is logged and the others still run.
function T.Try(what, fn, ...)
  local ok, err = pcall(fn, ...)
  if not ok then
    local g = GPS()
    if g and g.LogError then pcall(g.LogError, "tutorial: " .. what, err) end
  end
  return ok
end

-- The tutorial's own things off the map: the practice, the examples, the tools, the search and the hold.
function T.ClearDemo()
  local g, R, Lay = GPS(), ns.Record, ns.Layers
  if T.JumpDemoStop then T.JumpDemoStop("left") end -- (the spell-jump demo: the player's own route and spot back)
  -- (the Record window, unless the player had it open before)
  if R and R.window and R.window:IsShown() and not (T.run and T.run.snapshot.recWindow) then R.window:Hide() end
  if Lay and Lay.demoNodes then
    Lay.demoNodes = nil
    Lay.version = (Lay.version or 0) + 1
  end
  g.mmHold = nil
  T.DropPins()
  if g.searchPanel then g.searchPanel:Hide() end
  if g.mapMenu then g.mapMenu:Hide() end
  if g.drawMode or g.lasso then g.StopDrawing() end
  if g.roadMode then g.SetRoadMode(false) end
  if g.wallMode then g.SetWallMode(false) end
  if g.mapEditOpen and g.SetMapEditOpen then g.SetMapEditOpen(false) end
end

-- Everything back as the snapshot has it, live. `tweak(st)`: changes to the settings before they're applied (what a
-- running tutorial needs on top; at the end, only the minimap answer). `keepOut`: the map as the minimap, opened out,
-- stays out (the next section needs the whole map too: not into its corner and out again between the two).
function T.RestoreLive(snap, tweak, keepOut)
  local g, N = GPS(), ns.Nav
  T.Try("the demo off", T.ClearDemo)
  T.Try("the settings", function()
    T.RestoreData(snap)
    if tweak then tweak(S()) end
  end)
  T.Try("the route", N.Restore)
  T.Try("the view", function() T.ApplyView(snap.view) end)
  T.Try("the stops waiting", function() g.PendingStops(Copy(snap.pending or {})) end)
  T.Try("the map", function()
    -- (the map as the minimap, opened out: back in its corner, at once)
    local m = g.mmState
    local stay = keepOut and S().replaceMinimap and m.on and m.expanded
    if m.expanded and not stay then g.SetMinimapExpanded(false) end
    if m.tween then g.MinimapTween(g.MINIMAP_TWEEN or 1) end
    g.ApplySettings()
    if g.LayoutQuick then g.LayoutQuick() end -- (the quick buttons where the settings put back have them)
    -- (the window's size changing rescales the zoom, so a bigger window shows more: the player's own zoom, as it was)
    if S().zoom ~= snap.gps.zoom then
      S().zoom = snap.gps.zoom
      g.ApplySettings()
    end
  end)
  T.Try("the arrow", function()
    if ns.Arrow and ns.Arrow.Apply then ns.Arrow.Apply() end
  end)
  T.Try("the options", function()
    if ns.Options and ns.Options.Refresh then ns.Options.Refresh() end
  end)
  T.Try("the redraw", g.Redraw)
end

---------------------------------------------------------------------------
-- What the steps use
---------------------------------------------------------------------------

function T.MapFrame() return _G.AzerothGPSFrame end

-- A quick button to point at: the button itself while it shows, else its group's, else the map menu's round button.
function T.QuickButton(id)
  local g = GPS()
  local grp = g.groupOf and g.groupOf[id] -- (a group's own button: Map Editing)
  if grp and grp.button and grp.button:IsVisible() then return grp.button end
  for _, t in ipairs(g.QUICK or {}) do
    if t.id == id and t.button and t.button:IsVisible() then return t.button end
  end
  for _, grp in ipairs(g.QUICK_GROUPS or {}) do
    for _, mid in ipairs(grp.members) do
      local slot = mid == id and g.groupOf and g.groupOf[grp.id]
      if slot and slot.button and slot.button:IsVisible() then return slot.button end
    end
  end
  return g.mapButton
end
function T.Quick(id) return function() return T.QuickButton(id) end end

-- The player's spot: world x, y and the level stops there are on.
function T.Here()
  local x, y, cont = ns.Geo.PlayerWorld()
  if not x then error("no position here") end
  local level = ns.Nav.PlayerLevel and ns.Nav.PlayerLevel(cont) or cont
  return x, y, level
end

function T.StopCount() return #ns.Nav.stops + #GPS().PendingStops() end

function T.ClearRoute()
  local g = GPS()
  ns.Nav.Clear()
  g.PendingStops({})
  g.Follow()
end

-- Example stop `k`: a spot a few hundred yards from the player.
T.DEMO_SPOTS = { { 180, 60 }, { 60, -220 }, { -200, -40 }, { -90, 230 } }
function T.DemoStop(k)
  local x, y, level = T.Here()
  local d = T.DEMO_SPOTS[(k - 1) % #T.DEMO_SPOTS + 1]
  return { x = x + d[1], y = y + d[2], cont = level, name = L["Example stop"] }
end

-- At least `n` stops on the route: the route's own and those waiting, then examples.
function T.EnsureRoute(n)
  local g, N = GPS(), ns.Nav
  if #N.stops >= n then return end
  local list = {}
  for _, d in ipairs(N.stops) do list[#list + 1] = d end
  for _, d in ipairs(g.PendingStops()) do list[#list + 1] = d end
  for k = #list + 1, n do list[k] = T.DemoStop(k) end
  g.PendingStops({})
  N.SetStops(list, false, "red") -- ("red": not asked about a zone too high, the examples are near)
end

-- The map as the minimap, on: in its corner, or opened out (`hold`: kept out while the step is read).
function T.MinimapOn(expanded, hold)
  local g, st = GPS(), S()
  st.shown, st.minimized, st.replaceMinimap = true, nil, true
  g.ApplySettings()
  local m = g.mmState
  if not m.on then error("the minimap can't be replaced here") end
  g.mmHold = hold and T.HOLD or nil
  if (m.expanded and true or false) ~= (expanded and true or false) then g.SetMinimapExpanded(expanded) end
end

-- The whole map window on the screen: shown, not minimized; as the minimap, opened out and held out.
function T.EnsureFull(minimized)
  local g, st = GPS(), S()
  if not st.shown or (st.minimized and not minimized) then
    st.shown, st.minimized = true, nil
    g.ApplySettings()
  end
  local m = g.mmState
  if m.on then
    g.mmHold = T.HOLD
    if not m.expanded and not m.tween then g.SetMinimapExpanded(true) end
  else
    g.mmHold = nil
  end
end

-- The example across the sea: a stop on the other continent, set as Confirm Route does (its overview, then the player).
function T.FarRoute()
  local g, st = GPS(), S()
  local _, _, cont = ns.Geo.PlayerWorld()
  local base = ns.Geo.Base(cont)
  local side = T.FAR[UnitFactionGroup and UnitFactionGroup("player") or "Horde"] or T.FAR.Horde
  local d = side[base] or side[0]
  local name
  if C_Map and C_Map.GetMapInfo then
    local ok, info = pcall(C_Map.GetMapInfo, d[4])
    name = ok and info and info.name or nil
  end
  T.ClearRoute()
  st.avoidHighZones, st.stepsCollapsed = false, false -- (not asked about the zones on the way; the steps listed)
  g.AddStopAt(d[1], d[2], name or L["Example stop"], d[3])
  g.ConfirmRoute()
  if #ns.Nav.stops == 0 then error("no route across the sea") end
end

-- The example herbs and ore round the player (in memory: Layers.demoNodes), their layers on.
function T.DemoNodes()
  local g, st, Lay = GPS(), S(), ns.Layers
  st.layerHerbs, st.layerOre, st.nodeFilter = true, true, {}
  if Lay.demoNodes then return end
  local x, y, level = T.Here()
  local list = {}
  for i, n in ipairs(T.NODES) do list[i] = { x + n[1], y + n[2], n[3], n[4] } end
  Lay.demoNodes = { [level] = list }
  Lay.version = (Lay.version or 0) + 1
  T.ClearRoute()
  g.SetZoom(260)
  if g.RefreshQuick then g.RefreshQuick() end
  g.Redraw()
end
-- A loop through them, as a farming area drawn round them gives.
function T.DemoLoop()
  local x, y, level = T.Here()
  local Lay, nodes = ns.Layers, {}
  for _, n in ipairs(Lay.demoNodes and Lay.demoNodes[level] or {}) do
    nodes[#nodes + 1] = { x = n[1], y = n[2], cont = level, name = n[3], tex = Lay.NodeIcon(n[4], n[3]) }
  end
  if #nodes > 1 then ns.Nav.SetLoop(nodes, x, y) end
end

-- The pins section's practice pin (asked 2026-11-11: "After the Herbs and ore tutorial, add one for creating a custom
-- pin and how to route to it and how its searchable"). A pin made during that section is practice: its time is kept
-- in the tutorial's saved part (`pins`: a /reload in between loses nothing), and it's taken off again, as if never
-- made, when the tutorial moves on (T.ClearDemo). The player's own pins are never touched.
function T.PinDialog()
  local d = rawget(_G, "AzerothGPSPinDialog")
  return d and d:IsShown() and d or nil
end
function T.ClosePinDialog()
  local d = T.PinDialog()
  if d then d:Hide() end
end
-- The pins the player had as the section began (by their times), once a section.
function T.PinsBegin(run)
  if run.memo.pinsBefore then return end
  local tut = Tut()
  local practice, before = tut and tut.pins or {}, {}
  for _, p in ipairs(ns.Pins.Own()) do
    if p.time and not practice[p.time] then before[p.time] = true end
  end
  run.memo.pinsBefore = before
end
-- The pins made since: noted as practice; the newest of them.
function T.PracticePin(run)
  T.PinsBegin(run)
  local tut, newest = Tut(), nil
  for _, p in ipairs(ns.Pins.Own()) do
    if p.time and not run.memo.pinsBefore[p.time] then
      if tut then
        tut.pins = tut.pins or {}
        tut.pins[p.time] = true
      end
      newest = p
    end
  end
  return newest
end
-- ... or one made for them near where they stand, when they skipped making it.
function T.EnsurePin(run)
  local p = T.PracticePin(run)
  if p then return p end
  local x, y, level = T.Here()
  ns.Pins.Add({ level = level, x = x + 60, y = y + 40, name = L["My pin"] })
  return T.PracticePin(run)
end
function T.DropPins()
  local tut = Tut()
  local set = tut and tut.pins
  if not set then return end
  tut.pins = nil
  local own, any = ns.Pins.Own(), false
  for i = #own, 1, -1 do
    local t = own[i].time
    if t and set[t] then
      table.remove(own, i)
      if ns.MarkUnsaved then ns.MarkUnsaved("pin:" .. t, "remove") end -- (made and taken back: nothing to save)
      any = true
    end
  end
  T.ClosePinDialog()
  if any then ns.Pins.Changed() end
end

-- The search open; `text` put in its box as it opens (`force`: also when it was open already, over what's typed).
function T.OpenSearch(text, force)
  local g = GPS()
  local panel, button = g.searchPanel, g.searchButton
  local opened = not panel:IsShown()
  if opened then
    local click = button:GetScript("OnClick")
    if click then click(button, "LeftButton") end
  end
  local box = panel.box
  if text and (opened or force) and box and (box:GetText() or "") ~= text then
    box:SetText(text)
    local changed = box:GetScript("OnTextChanged")
    if changed then changed(box, false) end -- (set by code: the list made again either way)
  end
end
function T.CloseSearch()
  local panel = GPS().searchPanel
  if panel then panel:Hide() end
end
-- Whether the search box has `word` typed in it (any case, more round it or not).
function T.SearchHas(word)
  local panel = GPS().searchPanel
  local box = panel and panel:IsShown() and panel.box
  local text = box and box:GetText()
  if type(text) ~= "string" or text == "" then return false end
  return text:lower():find(tostring(word):lower(), 1, true) ~= nil
end

-- Ragefire Chasm's level, and its map shown.
function T.Dungeon()
  local lvl = 20000 + T.RAGEFIRE
  local inst = ns.Instances and ns.Instances[lvl]
  if type(inst) == "table" then return lvl, inst end
  for l, i in pairs(ns.Instances or {}) do
    if type(i) == "table" and i.map == T.RAGEFIRE then return l, i end
  end
end
function T.ShowDungeon()
  local g = GPS()
  local lvl = T.Dungeon()
  if not lvl then error("no dungeon map") end
  S().layerInstances = true
  local _, free = g.BrowseState()
  if not (free and free.instance == lvl) then g.ShowInstance(lvl) end
  _, free = g.BrowseState()
  if not (free and free.instance == lvl) then error("no dungeon map") end
end

-- Whether the quest log has quests with places (the Quest Route has something to make).
function T.HasQuests()
  local Lay = ns.Layers
  if not (Lay and Lay.QuestStops) then return false end
  local ok, stops = pcall(Lay.QuestStops, false)
  return ok and type(stops) == "table" and #stops > 0
end
function T.DemoQuests()
  local list = {}
  for k = 1, 3 do
    list[k] = T.DemoStop(k)
    list[k].name = Format(L["Example quest %d"], k)
  end
  GPS().PendingStops({})
  ns.Nav.SetStops(list, true, "red")
end
-- The other addons AzerothGPS works with that are loaded now, as a list to read, or nil.
function T.OtherAddons()
  local out = {}
  local function Loaded(name)
    local fn = (C_AddOns and C_AddOns.IsAddOnLoaded) or IsAddOnLoaded
    if not fn then return false end
    local ok, v = pcall(fn, name)
    return ok and v and true or false
  end
  if ns.RestedXP and ns.RestedXP.Available and ns.RestedXP.Available() then out[#out + 1] = L["RestedXP Route"] end
  if ns.Zygor and ns.Zygor.Available and ns.Zygor.Available() then out[#out + 1] = L["Zygor Route"] end
  if Loaded("Questie") then out[#out + 1] = "Questie" end
  if Loaded("TomTom") then out[#out + 1] = "TomTom /way" end
  -- (as a sentence lists them, asked 2026-11-10: "RestedXP Route, Zygor Route, and Questie")
  local n = #out
  if n == 0 then return nil end
  if n == 1 then return out[1] end
  if n == 2 then return Format(L["%s and %s"], out[1], out[2]) end
  return Format(L["%s, and %s"], table.concat(out, L[", "], 1, n - 1), out[n])
end

-- The arrow and the directions panel on, unlocked, with a route to show.
function T.ArrowOn()
  local st = S()
  st.arrow, st.arrowLocked, st.dirLocked, st.dirShown = true, false, false, true
  st.arrowShown = true -- (the arrow hidden: shown for its steps, put back after)
  T.EnsureRoute(1)
  if ns.Arrow and ns.Arrow.Apply then ns.Arrow.Apply() end
end
local function PointKey(p)
  if type(p) ~= "table" then return tostring(p) end
  local out = {}
  for i = 1, 5 do out[i] = tostring(p[i]) end
  return table.concat(out, ",")
end
-- Where the two panels are, as one text (a change: the player moved one).
function T.ArrowPlace()
  local st = S()
  return PointKey(st.dirPoint) .. "|" .. PointKey(st.arrowFreePoint) .. "|" .. tostring(st.arrowSnap) .. tostring(st.arrowSide)
end

-- The map window with its frame, its corner to drag, and minimized or not.
function T.WindowOn(minimized)
  local g, st = GPS(), S()
  st.shown, st.windowFrame, st.locked, st.lockSize = true, true, false, false
  if g.mmState.on then
    g.ApplySettings()
    T.EnsureFull()
    return
  end
  st.minimized = nil
  g.ApplySettings()
  if minimized then g.SetMinimized(true) end
end
function T.WindowSize()
  local st = S()
  return tostring(st.size) .. "x" .. tostring(st.freeSize and st.width or st.size)
end
function T.Sizing()
  local grip = GPS().sizeGrip
  return grip and grip.sizing and true or false
end

---------------------------------------------------------------------------
-- The spell-jump demo (Kooki3z 2026-11-25: "in the tutorial's spell-jumping step, show a live, simulated example")
---------------------------------------------------------------------------
-- On the "Class spells for big drops" step: the player's route (and the stops waiting) set aside, and an example trip
-- off Bluefen's ridge (test_world_grid's: from the Barrens' side of the ridge above Bluefen down into Dustwallow Marsh)
-- planned for a simulated player standing at its start (Geo.override, as the dev tools' is) who is a mage with Slow
-- Fall ready (FallSpells' FS.demo: the spell "known", Light Feathers "in the bags", nothing of the real character's
-- read or changed). The map draws the trip with its jump's coil and the directions say the real step, with the cast
-- button as it looks in play: an insecure look-alike in the secure button's place (GPSFrame's G.DemoUseButton, its
-- click T.JumpDemoCast; the mouse or the controller's A, Pad.Run), which casts nothing: it moves the simulated player
-- to the ledge, off it and gliding down (T.JumpDemoTick), and on to the stop, where the trip arrives as any does.
-- While it runs nothing of the route is saved (Nav's N.demoRoute: the saved route stays as it was).
-- All of it is undone at once (T.JumpDemoStop: the real position, the player's saved route and stops waiting, the
-- view) when the step is left or the tutorial ends, the player moves (the game's own position, Geo.RealPlayerWorld),
-- combat starts (PLAYER_REGEN_DISABLED), the map hides (or the game's world map closes, in world-map mode), or the
-- game is left or reloaded (PLAYER_LOGOUT; and it's all in memory: a /reload ends it anyway).
T.JUMP_DEMO = { cont = 1, start = { -2309.8, -3253.5 }, stop = { -2558.3, -3232.5 }, feathers = 5 }
T.DEMO_MOVED_YD = 0.5 -- the player's own position this far from where they stood: the demo ends
T.DEMO_LOOK = 0.1 -- seconds between looks at what ends it
-- (the walk to the ledge and the walk from the landing: at these yards a second, within these seconds; the glide down
-- in DEMO_GLIDE_SECS)
T.DEMO_RUN_YPS, T.DEMO_RUN_SECS = 14, { 0.4, 2 }
T.DEMO_GLIDE_SECS = 3
T.DEMO_LAND_YPS, T.DEMO_LAND_SECS = 25, { 0.4, 2.5 }

function T.JumpDemoOn() return T.jumpDemo ~= nil end

-- The demo's fall spell row (FS.SPELLS' Slow Fall).
function T.DemoSpellRow()
  local FS = ns.FallSpells
  for _, row in ipairs(FS.SPELLS) do
    if row.ids and row.ids[1] == FS.DEMO_SPELL then return row end
  end
  return nil
end

-- A view as G.SaveView gave it put back (the map following the player when there's none).
function T.ApplyView(v)
  local g = GPS()
  if not v then
    g.Follow()
  elseif v.browseZoom and not v.browse then -- (a spot looked at, G.LookAt: its own zoom, which ApplyView lets go)
    g.LookAt(v.cont, v.x, v.y, v.browseZoom)
  else
    g.ApplyView(Copy(v))
  end
end

-- The demo on (again from its start when it's on). False when it can't be (no position, combat).
function T.JumpDemoStart()
  if T.jumpDemo then T.JumpDemoStop("again") end
  local g, N, FS, Geo = GPS(), ns.Nav, ns.FallSpells, ns.Geo
  if ns.inCombat or (InCombatLockdown and InCombatLockdown()) then return false end
  local rx, ry, rc = Geo.RealPlayerWorld()
  local row = T.DemoSpellRow()
  if not (rx and row) then return false end
  local okView, view = pcall(g.SaveView)
  local demo = { real = { rx, ry, rc }, override = Geo.override, pending = Copy(g.PendingStops()),
    view = okView and view and Copy(view) or false }
  T.jumpDemo = demo
  N.demoRoute = true -- (before the trip's set: nothing of it saved)
  FS.held, FS.fall, FS.fallArm = nil, nil, nil
  FS.demo = { row = row, feathers = T.JUMP_DEMO.feathers }
  local D = T.JUMP_DEMO
  local sx, sy, tx, ty = D.start[1], D.start[2], D.stop[1], D.stop[2]
  Geo.SetOverride({ x = sx, y = sy, cont = D.cont, facing = math.atan2(ty - sy, tx - sx), moving = false,
    indoors = false, swimming = false })
  FS.Refresh()
  g.PendingStops({})
  N.SetStops({ { x = tx, y = ty, cont = D.cont, name = L["Example stop"] } }, false, "red")
  g.onDemoCast = T.JumpDemoCast
  g.Follow()
  g.Redraw()
  demo.lookAt = GetTime()
  T.DemoFrame():Show()
  return true
end

-- The demo's look-alike buttons hidden (each use button's twin, G.DemoUseButton).
function T.HideDemoButtons()
  local g = GPS()
  for _, b in ipairs({ g and g.useBtn or false, rawget(_G, "AzerothGPSArrowUseButton") or false }) do
    local d = b and b.twin
    if d then
      d:Hide()
      d.key = nil
    end
  end
end

-- Everything the demo changed put back at once. `why`: "left" (the step or the tutorial), "moved", "combat",
-- "hidden", "logout", "again".
function T.JumpDemoStop(why)
  local demo = T.jumpDemo
  if not demo then return false end
  T.jumpDemo = nil
  local g, N, FS = GPS(), ns.Nav, ns.FallSpells
  if T.demoFrame then T.demoFrame:Hide() end
  if g then g.onDemoCast = nil end
  T.Try("the demo's player", function() ns.Geo.SetOverride(demo.override) end)
  T.Try("the demo's spell", function()
    FS.demo, FS.held, FS.fall, FS.fallArm = nil, nil, nil, nil
  end)
  T.HideDemoButtons()
  T.Try("the demo's route", function()
    N.demoRoute = nil
    if ns.Router and ns.Router.DropBackground then ns.Router.DropBackground() end -- (the example trip's searches)
    N.Restore()
  end)
  T.Try("the demo's fall spells", FS.Refresh)
  T.Try("the demo's view", function() T.ApplyView(demo.view) end)
  -- (after the view: following the player again lets go of the stops waiting, G.Follow)
  T.Try("the demo's stops waiting", function() g.PendingStops(Copy(demo.pending or {})) end)
  T.Try("the demo's redraw", g.Redraw)
  -- (still on its step: it says the example stopped, Show Again plays it again)
  local run = T.run
  if why ~= "left" and why ~= "again" and run and run.step and run.step.jumpDemo and not run.card then
    run.mark.demoEnded = why or true
    if not run.paused then T.ShowStep() end
  end
  return true
end

-- The demo button clicked (G.DemoCastClick; the controller's A, Pad.Run): nothing cast; the simulated player walks to
-- the ledge, off it and glides down to the ground, then on to the stop.
function T.JumpDemoCast()
  local demo = T.jumpDemo
  if not demo or demo.anim then return false end
  local path = T.DemoPath()
  if not path then return false end
  ns.FallSpells.demo.castAt = GetTime()
  path.t0 = GetTime()
  demo.anim = path
  T.HideDemoButtons()
  return true
end

-- The simulated player's way from where they stand along the route: { pts = { x, y, ... }, at = { seconds at each
-- point }, total, drop = { first, last } point numbers of the fall }, or nil with no drop on the route.
function T.DemoPath()
  local N, R, Geo = ns.Nav, ns.Router, ns.Geo
  local r = N.route
  if not (r and r.parts) then return nil end
  local pts, kinds = {}, {}
  local o = Geo.override
  if o then pts[1], pts[2] = o.x, o.y end
  for _, part in ipairs(r.parts) do
    local p, k = part.pts, part.kinds
    if p and #p >= 4 and (part.stop == nil or part.stop == 1) then
      for i = 1, #p / 2 do
        local x, y = p[2 * i - 1], p[2 * i]
        local n = #pts / 2
        if n == 0 or (x - pts[2 * n - 1]) ^ 2 + (y - pts[2 * n]) ^ 2 > 0.01 then
          if n > 0 then kinds[n] = i > 1 and k and k[i - 1] or 1 end
          pts[#pts + 1], pts[#pts + 2] = x, y
        end
      end
    end
  end
  local n = #pts / 2
  local first, last
  for i = 1, n - 1 do
    if kinds[i] == R.KIND_DROP and (first == nil or last == i - 1) then
      first = first or i
      last = i
    end
  end
  if not first then return nil end
  local function Len(a, b)
    local yd = 0
    for i = a, b - 1 do
      yd = yd + math.sqrt((pts[2 * i + 1] - pts[2 * i - 1]) ^ 2 + (pts[2 * i + 2] - pts[2 * i]) ^ 2)
    end
    return yd
  end
  local function Clamp(v, lim) return math.max(lim[1], math.min(lim[2], v)) end
  -- (each phase's seconds shared out over its pieces by their yards)
  local phases = {
    { 1, first, Clamp(Len(1, first) / T.DEMO_RUN_YPS, T.DEMO_RUN_SECS) },
    { first, last + 1, T.DEMO_GLIDE_SECS },
    { last + 1, n, Clamp(Len(last + 1, n) / T.DEMO_LAND_YPS, T.DEMO_LAND_SECS) },
  }
  local at, t = { 0 }, 0
  for _, ph in ipairs(phases) do
    local a, b, secs = ph[1], ph[2], ph[3]
    local yd = Len(a, b)
    for i = a, b - 1 do
      t = t + (yd > 0 and secs * Len(i, i + 1) / yd or secs / math.max(1, b - a))
      at[i + 1] = t
    end
  end
  return { pts = pts, at = at, total = t, drop = { first, last + 1 } }
end

-- Where the simulated player is `t` seconds into path `a`: x, y, facing, and whether it's in the glide.
function T.DemoPathAt(a, t)
  local pts, at = a.pts, a.at
  local n = #pts / 2
  for i = 1, n - 1 do
    if t <= at[i + 1] or i == n - 1 then
      local span = at[i + 1] - at[i]
      local f = span > 0 and math.max(0, math.min(1, (t - at[i]) / span)) or 1
      local x1, y1, x2, y2 = pts[2 * i - 1], pts[2 * i], pts[2 * i + 1], pts[2 * i + 2]
      return x1 + (x2 - x1) * f, y1 + (y2 - y1) * f, math.atan2(y2 - y1, x2 - x1),
        i >= a.drop[1] and i < a.drop[2]
    end
  end
  return pts[1], pts[2], 0, false
end

-- Each frame while the demo runs: the glide moved on, and now and then a look at what ends it.
function T.JumpDemoTick()
  local demo = T.jumpDemo
  if not demo then return end
  local now = GetTime()
  local a = demo.anim
  local o = ns.Geo.override
  if a and o then
    local t = now - a.t0
    local x, y, facing, gliding = T.DemoPathAt(a, t)
    o.x, o.y, o.facing = x, y, facing
    demo.gliding = gliding or nil
    if t >= a.total then -- (down and walked on: at the stop, which the trip arrives at as any does)
      local d = ns.Nav.dest
      if d and d.x then o.x, o.y = d.x, d.y end
      demo.anim, demo.gliding, demo.landed = nil, nil, true
    end
  end
  if now - (demo.lookAt or 0) < T.DEMO_LOOK then return end
  demo.lookAt = now
  local why = T.JumpDemoEnds()
  if why then T.JumpDemoStop(why) end
end

-- What ends the demo now, or nil.
function T.JumpDemoEnds()
  local demo = T.jumpDemo
  if not demo then return nil end
  local run = T.run
  if not (run and not run.card and run.step and run.step.jumpDemo) then return "left" end
  if ns.inCombat or (InCombatLockdown and InCombatLockdown()) then return "combat" end
  local x, y, c = ns.Geo.RealPlayerWorld()
  local r = demo.real
  if not x or c ~= r[3] or (x - r[1]) ^ 2 + (y - r[2]) ^ 2 > T.DEMO_MOVED_YD ^ 2 then return "moved" end
  local g, st = GPS(), S()
  local f = T.MapFrame()
  if st.shown == false or st.minimized or not (f and f:IsVisible()) then return "hidden" end
  local wm = rawget(_G, "WorldMapFrame")
  if g.WorldMapWanted and g.WorldMapWanted() and not (wm and wm:IsShown()) then return "hidden" end
  return nil
end

function T.DemoFrame()
  if T.demoFrame then return T.demoFrame end
  local f = CreateFrame("Frame", nil, UIParent)
  f:SetScript("OnUpdate", function()
    local ok, err = pcall(T.JumpDemoTick)
    if not ok and GPS().LogError then pcall(GPS().LogError, "tutorial demo", err) end
  end)
  f:Hide()
  T.demoFrame = f
  return f
end

---------------------------------------------------------------------------
-- The sections
---------------------------------------------------------------------------

function T.BuildSections()
  local N = ns.Nav
  local function Button() return GPS().mmButton end
  local function InCorner() -- (the window section's logo steps, with the map as the minimap)
    if GPS().mmState.on then
      return L["With the GPS map as your minimap, a double-click on the logo sends the map back to its corner instead."]
    end
  end
  local function Size(size)
    return function()
      S().replaceMinimapSize = size
      GPS().ApplySettings()
      if ns.Options and ns.Options.Refresh then pcall(ns.Options.Refresh) end
    end
  end
  T.SECTIONS = {
    { id = "minimap", version = "1.2.0", title = L["The GPS map as your minimap"], steps = {
      { title = L["Minimap replacement"],
        text = L["The GPS map now sits where your minimap was. The game's own icons still show on it."],
        enter = function() T.MinimapOn(false) end, target = T.MapFrame },
      { title = L["Open the GPS map"], text = L["Click the logo on the minimap's bottom left corner."],
        enter = function() T.MinimapOn(false) end, target = Button,
        done = function() return GPS().mmState.expanded and true or false end },
      { title = L["Auto close on inactivity"],
        text = L["Left alone for 5 seconds, the map goes back to its corner. The arrow button on the bottom left, or double-click on the logo, sends it back now."],
        enter = function() T.MinimapOn(true) end, target = Button, countdown = true,
        done = function() return not GPS().mmState.expanded end },
      { title = L["Close on movement"],
        text = L["That option is on for this demo: take a step and the map goes back to the minimap position."],
        enter = function()
          S().replaceMinimapCollapseOnMove = true
          T.MinimapOn(true, true)
        end,
        target = T.MapFrame, done = function() return not GPS().mmState.expanded end },
      { title = L["Close on combat"],
        text = function()
          return L["It can also go back when combat starts. Both options are in Options > Map."]
            .. " " .. L["Check here to turn it on now."]
        end,
        enter = function(run)
          -- (the player's own, or what they ticked here: not the demo's)
          local keep = run.keepOpts or {}
          for _, k in ipairs(T.BACK_KEYS) do
            if keep[k] == nil then keep[k] = run.snapshot.gps[k] and true or false end
            S()[k] = keep[k]
          end
          run.keepOpts = keep
          T.MinimapOn(false)
        end,
        checks = function(run)
          local function Row(label, k)
            return { label, function() return run.keepOpts and run.keepOpts[k] end, function(v)
              run.keepOpts = run.keepOpts or {}
              run.keepOpts[k], S()[k] = v and true or false, v and true or false
              T.Persist()
            end }
          end
          return { Row(L["Back to the minimap when you move"], "replaceMinimapCollapseOnMove"),
            Row(L["Back to the minimap when combat starts"], "replaceMinimapCollapseOnCombat") }
        end },
      { title = L["Three size choices"], text = L["Pick the size you like."],
        enter = function() T.MinimapOn(false) end, target = T.MapFrame,
        choices = function()
          return { { L["Small"], Size("small") }, { L["Medium"], Size("medium") }, { L["Large"], Size("large") } }
        end },
      { title = L["Options on the logo"],
        text = L["Right-click the logo in the bottom left of the minimap to open the options panel."],
        enter = function()
          if _G.AzerothGPSOptions and _G.AzerothGPSOptions:IsShown() then _G.AzerothGPSOptions:Hide() end
          T.MinimapOn(false)
        end,
        target = Button,
        done = function() return _G.AzerothGPSOptions and _G.AzerothGPSOptions:IsShown() and true or false end },
      { title = L["Keep the GPS map as your minimap?"],
        text = function(run)
          if run.snapshot.gps.replaceMinimap then return L["You already use the GPS map as your minimap, so it stays on."] end
          return L["Yes keeps it on after the tutorial. Everything else goes back to how you had it."]
        end,
        enter = function() T.MinimapOn(false) end,
        choices = function(run)
          if run.snapshot.gps.replaceMinimap then return nil end
          return {
            { L["Yes"], function()
              run.keep, run.keepSize = true, S().replaceMinimapSize
              T.Advance()
            end },
            { L["No"], function()
              run.keep, run.keepSize = nil, nil
              T.Advance()
            end },
          }
        end },
    } },
    { id = "route", version = "1.2.0", title = L["Set a route"], full = true, steps = {
      { title = L["Place a stop"], text = L["Double-click anywhere on the map to place a stop."],
        enter = function() T.ClearRoute() end, target = T.MapFrame,
        done = function() return T.StopCount() > 0 end },
      { title = L["Start the route"], text = L["Click Confirm Route. It also starts by itself after 5 seconds of no further map activity."],
        enter = function()
          -- (the stop the player placed waits; none, or a route going already (come back to): an example waits)
          if #GPS().PendingStops() == 0 then
            T.ClearRoute()
            local d = T.DemoStop(1)
            GPS().AddStopAt(d.x, d.y, d.name, d.cont)
          end
        end,
        target = function() return GPS().routeButton end, done = function() return #N.stops > 0 end },
      { title = L["Add more stops"], text = L["Double-click two more places on the map. Each is added to the route."],
        enter = function(run)
          T.EnsureRoute(1)
          run.mark.n = T.StopCount()
        end,
        target = T.MapFrame, done = function(run) return T.StopCount() >= run.mark.n + 2 end },
      { title = L["The fastest order"],
        text = L["With several stops, the route visits them in the fastest order. Right-click a stop's marker to remove it."],
        -- (a stop removed: on, seen in game 2026-11-10)
        enter = function(run)
          T.EnsureRoute(3)
          run.mark.n = T.StopCount()
        end,
        target = T.MapFrame, done = function(run) return T.StopCount() < run.mark.n end },
      { title = L["Across to another continent"],
        text = L["This example goes to the other continent. The steps are listed at the top of the map window."],
        enter = function() T.FarRoute() end, target = T.MapFrame },
      { title = L["Clear a route"],
        text = L["Click the X at the top right of the directions to end the route."],
        -- (the directions' X: it ends the route with its option on, as it is by default; on for the step)
        enter = function()
          S().navCloseClears = true
          T.EnsureRoute(1)
          GPS().Update()
        end,
        target = function() return GPS().navCancel end, done = function() return T.StopCount() == 0 end },
    } },
    { id = "gather", version = "1.2.0", title = L["Herbs and ore"], full = true, steps = {
      { title = L["Example herbs and ore"],
        text = L["These icons are examples for the tutorial. Yours appear as you gather, and you can import more."],
        enter = function() T.DemoNodes() end, target = T.MapFrame },
      { title = L["Show or hide them"],
        text = L["The Herbs and Ore buttons in the map menu show or hide them. Find Herbs and Ore shows only the ones you pick."],
        enter = function() T.DemoNodes() end, target = T.Quick("herbs") },
      { title = L["Draw a farming area"],
        text = L["Click Draw a Farming Area in the map menu, under Herbs, Ore and Farming."],
        enter = function()
          T.DemoNodes()
          if GPS().drawMode then GPS().StopDrawing() end
        end,
        target = T.Quick("farm"), done = function() return GPS().drawMode and true or false end },
      { title = L["Circle the icons"],
        -- (the controller in use: its buttons, Pad.lua's drawing)
        text = function()
          local P = ns.Pad
          if P and P.used then
            return Format(L["Mark corners around the example icons with %s, then press %s to finish."],
              P.ActionLabel("select"), P.ActionLabel("menu"))
          end
          return L["Drag a loop around the example icons."]
        end,
        enter = function(run)
          T.DemoNodes()
          if not GPS().drawMode then GPS().StartDrawing() end
          run.mark.v = N.Version()
        end,
        target = T.MapFrame, done = function(run) return N.Version() ~= run.mark.v and #N.stops > 0 end,
        -- (a loop that caught nothing ends the drawing: on again for the next try)
        poll = function() if not GPS().drawMode and not GPS().lasso then GPS().StartDrawing() end end },
      { title = L["A loop route"],
        -- (why only some of the loop is drawn, asked 2026-11-10: the paths to the next few stops, Options >
        -- Performance's "Stops routed and drawn ahead")
        text = function() return L["The route visits every one you circled until you reach them."] .. " " .. Format(L["To save work, only the paths to the next stops are drawn (%d at a time). Every stop is still in the route: reach one for the next path to appear. Options > Performance to adjust this number."], S().stopsAhead or 3) end,
        enter = function()
          T.DemoNodes()
          if GPS().drawMode then GPS().StopDrawing() end
          if #N.stops == 0 then T.DemoLoop() end
        end,
        target = T.MapFrame },
    } },
    { id = "pins", version = "1.2.0", title = L["Custom pins"], full = true, steps = {
      { title = L["Create a pin"], text = L["Hold Shift and click a spot on the map, then click Create Pin."],
        enter = function(run)
          T.ClearRoute()
          T.CloseSearch()
          T.ClosePinDialog()
          S().pinning, S().showCustomPins = true, true
          T.PinsBegin(run)
          GPS().Redraw()
        end,
        target = T.MapFrame,
        done = function(run) return T.PinDialog() ~= nil or T.PracticePin(run) ~= nil end },
      { title = L["Name it"], text = L["Type a name, pick an icon, then click Create Pin."],
        enter = function(run)
          S().pinning, S().showCustomPins = true, true
          -- (skipped here without a spot picked: the pin's window for a spot beside the player)
          if not T.PracticePin(run) and not T.PinDialog() then
            local x, y, level = T.Here()
            ns.Pins.OpenEditor({ level = level, x = x + 60, y = y + 40, floors = {}, pick = 0 })
          end
        end,
        target = function() return T.PinDialog() or T.MapFrame() end,
        done = function(run) return T.PracticePin(run) ~= nil end,
        leave = function() T.ClosePinDialog() end },
      { title = L["Route to your pin"], text = L["Double-click your pin: it becomes a stop and the route goes to it."],
        enter = function(run)
          S().showCustomPins = true
          T.EnsurePin(run)
          T.ClearRoute()
          GPS().Redraw()
          run.mark.n = T.StopCount()
        end,
        target = T.MapFrame, done = function(run) return T.StopCount() > run.mark.n end },
      { title = L["Find it in the search"],
        text = function()
          local run = T.run
          return Format(L["Your pins are in Search Places too. Type its name in the search box: %s"], run and run.memo.pinName or L["My pin"])
        end,
        enter = function(run)
          run.memo.pinName = T.EnsurePin(run).name
          T.ClearRoute()
          T.OpenSearch("", true)
          run.mark.n = T.StopCount()
        end,
        target = function() return GPS().searchPanel end,
        done = function(run) return T.StopCount() > run.mark.n or T.SearchHas(run.memo.pinName or L["My pin"]) end,
        poll = function() T.OpenSearch() end },
      { title = L["Remove a pin"],
        text = L["Right-click a pin to remove it. The pin made in this tutorial is practice: it is removed when you move on."],
        enter = function(run)
          T.CloseSearch()
          T.EnsurePin(run)
        end,
        target = T.MapFrame },
    } },
    -- (1.4.0: the enemies in the search and the Target button added, updated = "1.4.0": marked in the lists)
    { id = "search", version = "1.2.0", updated = "1.4.0", title = L["Search Places"], full = true, steps = {
      { title = L["Open the search"], text = L["Click the magnifier, Search Places, in the map menu."],
        enter = function()
          T.ClearRoute()
          T.CloseSearch()
        end,
        target = T.Quick("search"), done = function() return GPS().searchPanel:IsShown() and true or false end },
      { title = L["Find your class trainer"],
        text = function() return Format(L["Type this in the search box: %s"], L["class trainer"]) end,
        enter = function(run)
          T.OpenSearch("", true)
          run.mark.n, run.memo.picked = T.StopCount(), nil
        end,
        target = function() return GPS().searchPanel end,
        -- (typed; or typed and picked in one go, which the next step then has)
        done = function(run)
          if T.StopCount() > run.mark.n then run.memo.picked = true end
          return run.memo.picked or T.SearchHas(L["class trainer"])
        end,
        poll = function() T.OpenSearch() end }, -- (it closes by itself after a while: open while this waits)
      { title = L["Pick a result"], text = L["Click a result, or press Enter for the first one: it becomes a stop."],
        blocked = function() return #GPS().SearchPlaces(L["class trainer"], 1) == 0 end,
        enter = function(run)
          -- (the words put in the box, unless the player typed them already or picked one in the last step)
          if not run.memo.picked and not T.SearchHas(L["class trainer"]) then T.OpenSearch(L["class trainer"], true) end
          run.mark.n = T.StopCount()
        end,
        target = function() return GPS().searchPanel end,
        done = function(run) return run.memo.picked or T.StopCount() > run.mark.n end,
        poll = function() T.OpenSearch(L["class trainer"]) end },
      { title = L["More to find"],
        text = L["The search also finds flight masters, inns, towns and zones. Type what you need and get a route to it."],
        enter = function() T.CloseSearch() end, target = T.Quick("search") },
      -- (1.4.0: Options > General's Include enemies, on by default)
      { title = L["Enemies too"],
        text = L["Enemy mobs are found by name too, at their camp nearest you. Ones orange or red to you show their levels first."],
        enter = function() T.CloseSearch() end, target = T.Quick("search") },
      -- (1.3.14's Target button, Options > Directions: it marks the NPC solo, not in a group, by default)
      { title = L["Target the NPC"],
        text = L["Near an NPC stop, click the pulsing Target button under the directions: it targets the NPC and, when you're solo, marks it."],
        enter = function() T.CloseSearch() end },
    } },
    { id = "dungeon", version = "1.2.0", title = L["Dungeon maps"], full = true, steps = {
      { title = L["A dungeon's map"],
        text = function()
          local lvl, inst = T.Dungeon()
          return Format(L["This is the map of %s. Click a dungeon's entrance on the map to open its map like this."],
            inst and ns.InstanceName(lvl) or "?")
        end,
        enter = function() T.ShowDungeon() end, target = T.MapFrame },
      { title = L["Bosses in order"],
        text = L["The bosses are numbered in the usual order, with the usual path between them. You can mark off bosses and manually position yourself (when in a dungeon) with a double click."],
        enter = function() T.ShowDungeon() end, target = T.MapFrame },
      { title = L["Back out"],
        text = L["Right-click the map to leave a dungeon's map. The tutorial has done it for you."],
        enter = function() GPS().Follow() end, target = T.MapFrame },
    } },
    { id = "quests", version = "1.2.0", title = L["Quest Route"], full = true, steps = {
      { title = L["A route through your quests"],
        text = function(run)
          if run.mark.has then return L["Click Quest Route in the map menu."] end
          return L["You have no quests with known places right now, so these stops are examples."]
        end,
        enter = function(run)
          T.ClearRoute()
          S().questZoneOnly = false -- (every quest with a place, wherever it is)
          run.mark.has = T.HasQuests()
          if not run.mark.has then T.DemoQuests() end
          run.mark.v = N.Version()
        end,
        target = function(run) return run.mark.has and T.QuickButton("questRoute") or T.MapFrame() end,
        shown = function(run) return not run.mark.has end,
        done = function(run) return N.Version() ~= run.mark.v and #N.stops > 0 end },
      { title = L["What it does"],
        text = L["It visits your quests' objectives in the fastest order, then the turn-ins. A stop is done when its quest is, not when you get there. Right-click the button to choose how it routes."],
        enter = function() if #N.stops == 0 then T.DemoQuests() end end, target = T.MapFrame },
      { when = function() return T.OtherAddons() ~= nil end, title = L["With your other addons"],
        text = function() return Format(L["AzerothGPS also works with: %s."], T.OtherAddons() or "") end },
    } },
    -- (not on the whole map: with the map as the minimap it stays in its corner, the arrow in plain view, asked
    -- 2026-11-10)
    { id = "arrow", version = "1.2.0", title = L["The direction arrow"], corner = true, steps = {
      { title = L["The arrow and the directions"],
        text = L["The arrow points the way and the panel beside it lists the turns. Each can be dragged until you lock it."],
        enter = function() T.ArrowOn() end, target = function() return ns.Arrow.frame end },
      { title = L["Move it"], text = L["Drag the directions panel: the arrow comes with it."],
        enter = function(run)
          S().arrowSnap = true
          T.ArrowOn()
          run.mark.at = T.ArrowPlace()
        end,
        target = function() return ns.Arrow.dir end, done = function(run) return T.ArrowPlace() ~= run.mark.at end },
      { title = L["Pull them apart"],
        text = L["Drag the arrow off the panel to place it on its own. Drop it on a side of the panel to snap it back."],
        enter = function()
          S().arrowSnap = true
          T.ArrowOn()
        end,
        target = function() return ns.Arrow.frame end, done = function() return S().arrowSnap == false end },
      { title = L["Size and lock"],
        text = L["After the tutorial, right-click the arrow or the panel to lock that one in place: each has its own lock. The arrow's size, the text size and both locks are in Options > Directions."],
        enter = function() T.ArrowOn() end },
    } },
    -- (1.4.0, asked 2026-11-23: "update tutorials for 1.4.0 too"; the city grid, jumps, the class fall spells and the
    -- other faction's ground. Told, not shown: no city or ledge is near every player, so the steps point at the arrow
    -- and the directions they're said in, as the arrow section does)
    { id = "cities", version = "1.4.0", title = L["Ground, stairs and jumps"], corner = true, steps = {
      { title = L["The map's own ground"],
        text = L["Routes walk the map's own ground, in the open world and the six capitals: every floor, stair, ramp and bridge. The directions say when to take the stairs, cross a bridge or board a lift."],
        enter = function() T.ArrowOn() end, target = function() return ns.Arrow.dir end },
      { title = L["Jumps"],
        text = L["A coiled line on the map and an orange arrow mean a jump is coming up. Right-click a coil to avoid jumps on the way to that stop."],
        enter = function() T.ArrowOn() end, target = function() return ns.Arrow.frame end },
      -- (a live example, Kooki3z 2026-11-25: a mage's trip off Bluefen's ridge on the map, the cast button as in play,
      -- an insecure look-alike that casts nothing; clicked, the glide down is shown. T.JumpDemoStart above)
      { title = L["Class spells for big drops"], jumpDemo = true,
        text = function(run)
          if run.mark.demoEnded then
            return L["The example stopped and your own route is back. Show Again plays it again."]
          end
          return L["With a spell that slows your fall ready, routes may take bigger drops. In this example as a mage, click the button beside the directions to watch the jump. Nothing is cast."]
        end,
        enter = function(run)
          local st = S()
          st.arrow, st.arrowLocked, st.dirLocked, st.dirShown, st.arrowShown = true, false, false, true, true
          -- (the player's own map: in the game's world map when that's theirs, T.WorldMapPreview, put back on leaving)
          if run.snapshot and run.snapshot.gps and run.snapshot.gps.useWorldMap == true then
            run.mark.worldMap = true
            T.WorldMapPreview(true)
          end
          if ns.Arrow and ns.Arrow.Apply then ns.Arrow.Apply() end
          if not T.JumpDemoStart() then error("the spell-jump demo can't start here") end
        end,
        leave = function(run)
          T.JumpDemoStop("left")
          if run.mark.worldMap then T.WorldMapPreview(false) end
        end,
        target = function() return GPS().DemoUseShown and GPS().DemoUseShown() or ns.Arrow.dir end,
        choices = function(run)
          return { { L["Show Again"], function()
            run.mark.demoEnded = nil
            T.JumpDemoStart()
            T.ShowStep()
          end } }
        end },
      { title = L["The other faction's ground"],
        text = L["Routes go around the other faction's guards (the red areas on the map). When the only way goes past them, the route asks you first: Take it?"],
        enter = function() T.ArrowOn() end, target = function() return ns.Arrow.dir end },
      { title = L["Your choice"],
        text = L["Use class spells, Expert jumper and Safe drop are in Options > Routing."],
        enter = function() T.ArrowOn() end },
    } },
    { id = "window", version = "1.2.0", title = L["The map window"], full = true, steps = {
      { title = L["Hide the map"],
        text = L["Double-click the logo at the map's top left. The map hides and only the logo stays."],
        -- (as the minimap: the double-click sends it to its corner, and it's left there for this step, asked
        -- 2026-11-10; the next step opens it again)
        blocked = InCorner, stay = true, enter = function() T.WindowOn(false) end,
        target = function() return GPS().logo and GPS().logo.plate end,
        done = function() return S().minimized and true or false end },
      -- (not with the map as the minimap, asked 2026-11-11: there the logo doesn't hide the map, the step had nothing
      -- to do, and the next one opens the map for its resizing by itself)
      { when = function() return not GPS().mmState.on end,
        title = L["Bring it back"], text = L["Double-click the logo again."], minimized = true,
        enter = function() T.WindowOn(true) end,
        target = function() return GPS().miniIcon end, done = function() return not S().minimized end },
      { title = L["Resize it"], text = L["Drag the map's bottom-right corner."],
        enter = function(run)
          T.WindowOn(false)
          run.mark.size = T.WindowSize()
        end,
        target = function() return GPS().sizeGrip end,
        done = function(run) return T.WindowSize() ~= run.mark.size and not T.Sizing() end },
      { title = L["Any shape"],
        text = L["Any shape is on for this demo: drag the corner again to make the map wide or tall."],
        -- (really on: the option alone left the map square, seen in game 2026-11-10; it needs a width of its own,
        -- as its checkbox in the options gives it, G.FreeSize)
        enter = function(run)
          local st = S()
          st.freeSize = true
          st.width = st.width or st.size
          if run.keepOpts == nil or run.keepOpts.freeSize == nil then
            run.keepOpts = run.keepOpts or {}
            run.keepOpts.freeSize = run.snapshot.gps.freeSize and true or false
          end
          T.WindowOn(false)
          run.mark.size = T.WindowSize()
        end,
        target = function() return GPS().sizeGrip end,
        done = function(run) return T.WindowSize() ~= run.mark.size and not T.Sizing() end,
        checks = function(run) -- (kept for after: it stays on while the step runs)
          return { { L["Any shape"], function() return run.keepOpts and run.keepOpts.freeSize end, function(v)
            run.keepOpts = run.keepOpts or {}
            run.keepOpts.freeSize = v and true or false
            T.Persist()
          end } }
        end },
      -- (the option to have the map in the game's world map window, offered here: asked 2026-11-10, "add this to the
      -- tutorials"; the tutorial itself stays on the map's own window. On this step it's shown: the game's map opens
      -- with the GPS map in it, by itself, and the step after puts it back; the checkbox is only whether to keep it
      -- after the tutorial. Asked 2026-11-10: "during this step it should be done automatically to demo the feature.
      -- If they don't check it then next step puts it back"; T.WorldMapPreview)
      { title = L["In the game's world map"],
        text = L["The GPS map can also show in the game's world map (M) instead of its own window. Check here to use it after the tutorial, or later in Options > Map."],
        enter = function(run)
          run.keepOpts = run.keepOpts or {}
          if run.keepOpts.useWorldMap == nil then run.keepOpts.useWorldMap = run.snapshot.gps.useWorldMap and true or false end
          T.WorldMapPreview(true)
        end,
        leave = function() T.WorldMapPreview(false) end,
        checks = function(run)
          return { { L["Show the GPS map in the game's world map"], function() return run.keepOpts and run.keepOpts.useWorldMap end, function(v)
            run.keepOpts = run.keepOpts or {}
            run.keepOpts.useWorldMap = v and true or false
            T.Persist()
          end } }
        end },
      { title = L["Returning to original"],
        text = L["Size, shape and lock are in Options > Map window. Your own settings come back when the tutorial ends."] },
    } },
  }
  T.byId = {}
  -- (the order they're gone through and listed in, asked 2026-11-11: the minimap, a route, the quest route, the
  -- arrow, herbs and ore, custom pins, "then the rest with current order"; one not named here keeps its place after)
  local at = {}
  for i, id in ipairs(T.ORDER) do at[id] = i end
  for i, sec in ipairs(T.SECTIONS) do sec.at = at[sec.id] or (#T.ORDER + i) end
  table.sort(T.SECTIONS, function(a, b) return a.at < b.at end)
  for _, sec in ipairs(T.SECTIONS) do T.byId[sec.id] = sec end
end

-- A section's name in the lists (asked 2026-11-14: "if the player has done the tutorial we mark it (done) but if we
-- update or add a new one we should show (new) or (updated)"): (done) played through as it is; (updated) played
-- through before its `updated` release changed it (`seen[id]`: the release it was played at); (new) not played, and
-- added after the newest one played; else its name alone.
function T.SectionLabel(sec, seen)
  seen = seen or {}
  local at = seen[sec.id]
  if at then
    if sec.updated and T.VersionNumber(sec.updated) > T.VersionNumber(at) then return Format(L["%s (updated)"], sec.title) end
    return Format(L["%s (done)"], sec.title)
  end
  local newest = 0
  for _, v in pairs(seen) do newest = math.max(newest, T.VersionNumber(v)) end
  if newest > 0 and T.VersionNumber(sec.version) > newest then return Format(L["%s (new)"], sec.title) end
  return sec.title
end

---------------------------------------------------------------------------
-- The panel, the glow and the section list
---------------------------------------------------------------------------

local function PanelButton(parent, label, onClick)
  local ok, b = pcall(CreateFrame, "Button", nil, parent, "UIPanelButtonTemplate")
  if not ok or not b then b = CreateFrame("Button", nil, parent) end
  b:SetHeight(22)
  b:SetScript("OnClick", onClick)
  function b.Label(self, text) -- (as wide as its text, longer in some languages)
    self:SetText(text)
    self:SetWidth(math.max(80, (self.GetTextWidth and self:GetTextWidth() or 0) + 24))
  end
  b:Label(label)
  return b
end

function T.Panel()
  if T.panel then return T.panel end
  -- (no name: Escape doesn't close it, a tutorial isn't left by mistake; the X and Exit Tutorial leave it)
  local f = ns.Window(nil, 430, 190, L["Tutorial"], "FULLSCREEN_DIALOG")
  _G.AzerothGPSTutorialPanel = f
  f:SetScript("OnDragStop", function(self)
    self:StopMovingOrSizing()
    T.panelMoved = true -- (where the player put it: left there)
  end)
  local close = (f.chrome and f.chrome.CloseButton) or f.closeButton
  if close then close:SetScript("OnClick", function() T.CloseClicked() end) end
  f.progress = f:CreateFontString(nil, "ARTWORK", "GameFontDisableSmall")
  f.progress:SetPoint("TOPLEFT", 16, f.top - 2)
  f.progress:SetPoint("TOPRIGHT", -16, f.top - 2)
  f.progress:SetJustifyH("LEFT")
  f.title = f:CreateFontString(nil, "ARTWORK", "GameFontNormalLarge")
  f.title:SetPoint("TOPLEFT", f.progress, "BOTTOMLEFT", 0, -6)
  f.title:SetPoint("TOPRIGHT", f.progress, "BOTTOMRIGHT", 0, -6)
  f.title:SetJustifyH("LEFT")
  f.body = f:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
  f.body:SetPoint("TOPLEFT", f.title, "BOTTOMLEFT", 0, -6)
  f.body:SetPoint("TOPRIGHT", f.title, "BOTTOMRIGHT", 0, -6)
  f.body:SetJustifyH("LEFT")
  f.body:SetWordWrap(true)
  f.back = PanelButton(f, L["Back"], function() T.Back() end)
  f.list = PanelButton(f, L["Sections"], function() T.ToggleList() end)
  f.exit = PanelButton(f, L["Exit Tutorial"], function() T.Exit() end)
  f.next = PanelButton(f, L["Next"], function() T.NextClicked() end)
  f.choices = {}
  T.panel = f
  return f
end

-- The panel's text and buttons for where the tutorial is.
function T.ShowStep()
  local run = T.run
  if not run then return end
  local f = T.Panel()
  local card, step = run.card, run.step
  local choices
  if card then
    f.progress:SetText("")
    f.title:SetText(card.title)
    f.body:SetText(card.text)
  else
    local sec = run.section
    f.progress:SetText(run.doneAt and ("|cff40ff40" .. L["Done!"] .. "|r")
      or Format(L["%s: step %d of %d"], sec.title, run.si, #run.steps))
    f.title:SetText(step.title)
    local text = run.blocked or step.text
    if type(text) == "function" then
      local ok, v = pcall(text, run)
      text = ok and v or T.CantText()
    end
    f.body:SetText(text)
    if not run.blocked and step.choices then
      local ok, list = pcall(step.choices, run)
      choices = ok and list or nil
    end
  end
  -- its own buttons, in a row over the others
  for i, c in ipairs(choices or {}) do
    local b = f.choices[i]
    if not b then
      b = PanelButton(f, "", function(self)
        if self.onPick then T.Try("a choice", self.onPick) end
      end)
      f.choices[i] = b
    end
    b:Label(c[1])
    b.onPick = c[2]
    b:ClearAllPoints()
    if i == 1 then b:SetPoint("BOTTOMLEFT", 14, 42) else b:SetPoint("LEFT", f.choices[i - 1], "RIGHT", 6, 0) end
    b:Show()
  end
  for i = #(choices or {}) + 1, #f.choices do f.choices[i]:Hide() end
  -- its checkboxes (options offered in the step itself), in a column over the buttons
  local checks
  if not card and not run.blocked and step.checks then
    local ok, list = pcall(step.checks, run)
    checks = ok and list or nil
  end
  f.checks = f.checks or {}
  for i, c in ipairs(checks or {}) do
    local cb = f.checks[i]
    if not cb then
      cb = CreateFrame("CheckButton", nil, f, "UICheckButtonTemplate")
      cb:SetSize(24, 24)
      cb.label = cb:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
      cb.label:SetPoint("LEFT", cb, "RIGHT", 2, 0)
      cb:SetScript("OnClick", function(self)
        if self.onSet then T.Try("a checkbox", self.onSet, self:GetChecked() and true or false) end
      end)
      f.checks[i] = cb
    end
    cb.label:SetText(c[1])
    cb.onSet = c[3]
    local ok, v = pcall(c[2])
    cb:SetChecked(ok and v and true or false)
    cb:ClearAllPoints()
    cb:SetPoint("BOTTOMLEFT", 12, 42 + (#checks - i) * 24)
    cb:Show()
  end
  for i = #(checks or {}) + 1, #f.checks do f.checks[i]:Hide() end
  -- Back and Sections from the left, Exit Tutorial and Next (or Skip Step, or Close) from the right
  f.back:SetShown(not card)
  f.list:SetShown(not card)
  f.exit:SetShown(not card)
  if not card then f.back:SetEnabled(run.si > 1) end
  f.next:Label(card and L["Close"] or (T.Waits(run) and L["Skip Step"] or L["Next"]))
  f.back:ClearAllPoints()
  f.back:SetPoint("BOTTOMLEFT", 14, 14)
  f.list:ClearAllPoints()
  f.list:SetPoint("LEFT", f.back, "RIGHT", 6, 0)
  f.next:ClearAllPoints()
  f.next:SetPoint("BOTTOMRIGHT", -14, 14)
  f.exit:ClearAllPoints()
  f.exit:SetPoint("RIGHT", f.next, "LEFT", -6, 0)
  local function W(b) return b:IsShown() and ((b.GetWidth and b:GetWidth() or 80) + 6) or 0 end
  local row = 0
  for i = 1, #(choices or {}) do row = row + W(f.choices[i]) end
  f:SetWidth(math.max(430, W(f.back) + W(f.list) + W(f.exit) + W(f.next) + 40, row + 34))
  f.choiceRoom = (choices and #choices > 0 and 28 or 0) + (checks and #checks * 24 + 4 or 0)
  for _, cb in ipairs(checks and f.checks or {}) do
    if cb:IsShown() then f:SetWidth(math.max(f:GetWidth(), (cb.label:GetStringWidth() or 0) + 60)) end
  end
  T.SizePanel()
  if not run.paused then
    f:Show()
    T.PlacePanel()
  end
  T.UpdateTarget()
end

-- The panel as tall as its text (again at each look: a text's height is only right once it's laid out).
function T.SizePanel()
  local f = T.panel
  if not f then return end
  local text = (f.progress:GetStringHeight() or 12) + (f.title:GetStringHeight() or 14) + (f.body:GetStringHeight() or 12)
  local h = -f.top + text + 14 + (f.choiceRoom or 0) + 52
  if math.abs((f.sizedTo or 0) - h) > 0.5 then
    f.sizedTo = h
    f:SetHeight(h)
  end
end

-- Whether the step waits for the player to do something (Skip Step), not just read (Next).
function T.Waits(run)
  local step = run.step
  if not step or run.blocked or run.doneAt or not step.done then return false end
  if step.shown then
    local ok, v = pcall(step.shown, run)
    if ok and v then return false end
  end
  return true
end

function T.CantText() return L["This step can't be done here right now. Skip it to go on."] end

-- The panel out of the way of what's pointed at: on the other half of the screen, low or high (left where the player
-- dragged it).
function T.PlacePanel()
  local f = T.panel
  if not f or T.panelMoved then return end
  local w, h = UIParent:GetWidth() or 1920, UIParent:GetHeight() or 1080
  local target = T.target or T.MapFrame()
  local tx, ty
  if target and target.GetCenter then
    local ok, x, y = pcall(target.GetCenter, target)
    if ok then tx, ty = x, y end
  end
  local scale = target and target.GetEffectiveScale and UIParent.GetEffectiveScale
    and (target:GetEffectiveScale() / UIParent:GetEffectiveScale()) or 1
  tx, ty = (tx or w / 2) * scale, (ty or h / 2) * scale
  local x = tx > w / 2 and w * 0.28 or w * 0.72
  local y = ty > h / 2 and h * 0.3 or h * 0.7
  f:ClearAllPoints()
  f:SetPoint("CENTER", UIParent, "BOTTOMLEFT", x, y)
end

-- The glow round the control pointed at: four gold edges and a faint fill, pulsing; the mouse goes through it.
function T.Glow()
  if T.glow then return T.glow end
  local f = CreateFrame("Frame", nil, UIParent)
  f:SetFrameStrata("FULLSCREEN_DIALOG")
  f:EnableMouse(false)
  local function Edge(p1, p2, w, h)
    local t = f:CreateTexture(nil, "OVERLAY")
    t:SetColorTexture(1, 0.82, 0.1, 1)
    t:SetPoint(p1)
    t:SetPoint(p2)
    if w then t:SetWidth(w) else t:SetHeight(h) end
  end
  Edge("TOPLEFT", "TOPRIGHT", nil, 3)
  Edge("BOTTOMLEFT", "BOTTOMRIGHT", nil, 3)
  Edge("TOPLEFT", "BOTTOMLEFT", 3)
  Edge("TOPRIGHT", "BOTTOMRIGHT", 3)
  local fill = f:CreateTexture(nil, "BACKGROUND")
  fill:SetAllPoints()
  fill:SetColorTexture(1, 0.82, 0.1, 0.12)
  f.fill = fill
  f:SetScript("OnUpdate", function(self)
    self:SetAlpha(0.45 + 0.55 * math.abs(math.sin(GetTime() * 3)))
  end)
  f:Hide()
  T.glow = f
  return f
end

-- The same glow on a control outside the tutorial (Import.lua's one-time notice: the "Route in the listed order" box),
-- round `target` to `to` (its label; `target` alone when nil). Not while the tutorial runs (its glow is its own).
function T.PointAt(target, to)
  if T.run or not target then return nil end
  local glow = T.Glow()
  glow:ClearAllPoints()
  glow:SetPoint("TOPLEFT", target, "TOPLEFT", -5, 5)
  glow:SetPoint("BOTTOMRIGHT", to or target, "BOTTOMRIGHT", 5, -5)
  glow.fill:SetShown(true)
  glow:Show()
  T.pointed = target
  return glow
end
-- That glow off (only `target`'s, when given).
function T.StopPointing(target)
  if not T.pointed or (target and T.pointed ~= target) then return end
  T.pointed = nil
  if not T.run then T.Glow():Hide() end
end

-- The glow on the step's target now (looked at again every poll: a menu opened shows the button itself).
function T.UpdateTarget()
  local run = T.run
  local glow = T.Glow()
  local target
  if run and not run.paused and not run.card and not run.blocked and run.step and run.step.target then
    local ok, v = pcall(run.step.target, run)
    target = ok and v or nil
    if target and target.IsVisible and not target:IsVisible() then target = nil end
  end
  if target ~= T.target then
    T.target = target
    glow:ClearAllPoints()
    if target then
      local ok = pcall(function()
        glow:SetPoint("TOPLEFT", target, "TOPLEFT", -5, 5)
        glow:SetPoint("BOTTOMRIGHT", target, "BOTTOMRIGHT", 5, -5)
      end)
      if not ok then T.target, target = nil, nil end
    end
    if target then
      -- (a faint fill on a button; the map itself is only outlined)
      local w = target.GetWidth and target:GetWidth() or 0
      glow.fill:SetShown(w <= T.FILL_MAX)
      if not T.panelMoved then T.PlacePanel() end
    end
  end
  glow:SetShown(target ~= nil)
end

-- The section list: every section, a click jumps to it.
function T.ToggleList()
  local f = T.list
  if f and f:IsShown() then
    f:Hide()
    return
  end
  if not f then
    f = ns.Window(nil, 300, 60 + #T.SECTIONS * 26, L["Sections"], "FULLSCREEN_DIALOG")
    f.rows = {}
    local width = 260
    for i, sec in ipairs(T.SECTIONS) do
      local b = PanelButton(f, sec.title, function()
        f:Hide()
        T.Jump(sec.id)
      end)
      b:SetPoint("TOPLEFT", 16, f.top - 6 - (i - 1) * 26)
      f.rows[i] = b
      width = math.max(width, b:GetWidth() or 0)
    end
    for _, b in ipairs(f.rows) do b:SetWidth(width) end
    f:SetWidth(width + 32)
    T.list = f
  end
  local seen = Tut().seen
  for i, sec in ipairs(T.SECTIONS) do
    f.rows[i]:SetText(T.SectionLabel(sec, seen))
  end
  f:ClearAllPoints()
  f:SetPoint("BOTTOM", T.panel, "TOP", 0, 6)
  f:Show()
end

---------------------------------------------------------------------------
-- The runner
---------------------------------------------------------------------------

-- Why the tutorial can't start now, or nil.
function T.Blocked()
  local g, N = GPS(), ns.Nav
  if T.run then return L["The tutorial is already running."] end
  if not (ns.started and g and g.mmState and T.MapFrame() and T.SECTIONS) then return L["The tutorial can't start right now. Try again in a moment."] end
  if g.Held and g.Held() then return L["not during a game on the map"] end
  local function Is(fn, ...)
    if not fn then return false end
    local ok, v = pcall(fn, ...)
    return ok and v and not (ns.IsSecret and ns.IsSecret(v)) and true or false
  end
  if ns.inCombat or Is(InCombatLockdown) or Is(UnitIsDeadOrGhost, "player") or Is(UnitOnTaxi, "player")
      or Is(N.DungeonLocked) or Is(N.CurrentInstance) or Is(IsInInstance) or (ns.Record and ns.Record.rec)
      or not ns.Geo.PlayerWorld() then
    return L["The tutorial can't start in combat, in a dungeon, on a flight or while dead. Try again after."]
  end
  return nil
end

function T.Persist()
  local run, tut = T.run, Tut()
  if not tut then return end
  if not run or run.card then
    tut.run = nil
    return
  end
  tut.run = { queue = Copy(run.queue), qi = run.qi, si = run.si, keep = run.keep, keepSize = run.keepSize,
    keepOpts = run.keepOpts and Copy(run.keepOpts) or nil, snapshot = run.snapshot }
end

-- Start the tutorial: the sections `ids` (every one without), from the `from`th. False and why when it can't.
function T.Start(ids, from)
  if T.run and T.run.card then T.CloseCard() end -- (the last tutorial's closing card still up)
  local why = T.Blocked()
  if why then
    ns.Print(why)
    return false, why
  end
  local queue = {}
  for _, id in ipairs(ids or {}) do
    if T.byId[id] then queue[#queue + 1] = id end
  end
  if #queue == 0 then
    for _, sec in ipairs(T.SECTIONS) do queue[#queue + 1] = sec.id end
  end
  local g, R = GPS(), ns.Record
  if _G.AzerothGPSOptions and _G.AzerothGPSOptions:IsShown() then _G.AzerothGPSOptions:Hide() end
  local snap = T.Snapshot()
  -- (the dev addon's map editor's tools on: off for the tutorial, back on at its end)
  if g.roadMode then g.SetRoadMode(false) end
  if g.wallMode then g.SetWallMode(false) end
  T.run = { queue = queue, qi = math.max(1, math.min(from or 1, #queue)), si = 1, snapshot = snap, mark = {},
    memo = {} }
  -- (the guide routes put their own stops back in: off while it runs, back on from the snapshot)
  local cdb = ns.CharDB()
  cdb.rxpFollow, cdb.zygorFollow = nil, nil
  T.Ticker():Show()
  T.Persist()
  ns.Print(L["Tutorial started. Everything goes back to how you had it when it ends."])
  T.EnterSection()
  return true
end

-- What a section needs on top of the player's own settings: the map on the screen, no going back by itself, the quick
-- buttons in their usual places, and the minimap answer so far.
function T.Baseline(st)
  st.shown, st.minimized = true, nil
  st.useWorldMap = false -- (the tutorial shows the map's own window; the snapshot puts the option back)
  st.replaceMinimapCollapseOnMove, st.replaceMinimapCollapseOnCombat = false, false
  -- (the quick buttons where they are by default, so "in the map menu" and "on the map" are true for everyone)
  st.quick, st.quickOrder, st.drawerDir = nil, nil, nil
  T.ApplyKeep(T.run)
end

function T.EnterSection()
  local run = T.run
  local sec = T.byId[run.queue[run.qi]]
  run.section, run.si, run.memo = sec, math.max(1, run.si or 1), {}
  T.RestoreLive(run.snapshot, T.Baseline, sec.full) -- (each section from the player's own state)
  local cdb = ns.CharDB()
  cdb.rxpFollow, cdb.zygorFollow = nil, nil
  run.steps = {}
  for _, step in ipairs(sec.steps) do
    local keep = true
    if step.when then
      local ok, v = pcall(step.when)
      keep = ok and v and true or false
    end
    if keep then run.steps[#run.steps + 1] = step end
  end
  run.si = math.min(run.si, #run.steps)
  T.EnterStep()
end

function T.EnterStep()
  local run = T.run
  local step = run.steps[run.si]
  run.step, run.mark, run.doneAt, run.blocked = step, {}, nil, nil
  T.target = nil
  if run.section.full then
    local ok = pcall(T.EnsureFull, step.minimized)
    if not ok then run.blocked = T.CantText() end
  elseif run.section.corner then -- (the map as the minimap: back in its corner, not held out)
    local g = GPS()
    g.mmHold = nil
    if g.mmState.on and g.mmState.expanded then g.SetMinimapExpanded(false) end
  end
  if not run.blocked and step.blocked then
    local ok, v = pcall(step.blocked, run)
    if ok and v then run.blocked = type(v) == "string" and v or T.CantText() end
  end
  if not run.blocked and step.enter then
    local ok, err = pcall(step.enter, run)
    if not ok then
      run.blocked, run.error = T.CantText(), tostring(err)
      if GPS().LogError then pcall(GPS().LogError, "tutorial step " .. run.section.id .. " " .. run.si, err) end
    end
  end
  T.Persist()
  T.ShowStep()
end

-- The seconds left before the opened-out map goes back by itself, on the map (asked 2026-11-10: a countdown in the
-- steps about it, "Active!" while the player is doing something on it; only in the tutorial). The map's own quiet
-- clock is read (G.mmState.activeAt, G.MINIMAP_IDLE): it sends the map back, not this.
T.ACTIVE_FOR = 0.35 -- s since the map's clock was set back: still "Active!"
function T.CountdownText(now)
  local run, g = T.run, GPS()
  local m = g.mmState
  if not (run and run.step and run.step.countdown and not run.doneAt and not run.paused) then return nil end
  if not (m.on and m.expanded and not m.tween) then return nil end
  local quiet = now - (m.activeAt or now)
  if quiet < T.ACTIVE_FOR then return "|cff40ff40" .. L["Active!"] .. "|r" end
  return tostring(math.max(1, math.ceil((g.MINIMAP_IDLE or 5) - quiet)))
end
-- How much bigger than the game's huge font (20 px) the countdown is drawn: its digits a fifth of the map's smaller
-- side tall, and "Active!" never wider than the map.
T.COUNTDOWN_PART, T.COUNTDOWN_MIN, T.COUNTDOWN_MAX = 0.2, 2, 12
function T.CountdownScale(w, h)
  local side = math.min(tonumber(w) or 0, tonumber(h) or 0)
  if side <= 0 then return T.COUNTDOWN_MIN end
  return math.max(T.COUNTDOWN_MIN, math.min(T.COUNTDOWN_MAX, side * T.COUNTDOWN_PART / 20))
end

function T.UpdateCountdown()
  local text = T.CountdownText(GetTime())
  local f = T.countdown
  if not text then
    if f then f:Hide() end
    return
  end
  if not f then
    local map = T.MapFrame()
    if not map then return end
    f = CreateFrame("Frame", nil, map)
    f:SetSize(200, 40)
    f:SetFrameLevel((map:GetFrameLevel() or 1) + 50)
    f.text = f:CreateFontString(nil, "OVERLAY", "GameFontNormalHuge")
    f.text:SetPoint("CENTER")
    T.countdown = f
  end
  -- (much larger, and by the map's own size: asked 2026-11-10. The frame is scaled, so a small map's isn't cut off
  -- and a big one's can be read across the room)
  local map = T.MapFrame()
  local scale = T.CountdownScale(map and map:GetWidth(), map and map:GetHeight())
  if f.scale ~= scale then
    f.scale = scale
    f:SetScale(scale)
    f:ClearAllPoints()
    f:SetPoint("TOP", map, "TOP", 0, -50 / scale)
  end
  f.text:SetText(text)
  f:Show()
end

function T.LeaveStep()
  if T.countdown then T.countdown:Hide() end
  local run = T.run
  local step = run and run.step
  if step and step.leave then pcall(step.leave, run) end
end

-- On to the next step; past a section's last, the section is done and the next starts.
function T.Advance()
  local run = T.run
  if not run or run.card then return end
  T.LeaveStep()
  if run.si < #run.steps then
    run.si = run.si + 1
    return T.EnterStep()
  end
  local tut = Tut()
  tut.seen[run.section.id] = run.section.updated or run.section.version
  T.RefreshHelp()
  if run.qi < #run.queue then
    run.qi, run.si = run.qi + 1, 1
    return T.EnterSection()
  end
  T.End(true)
end

function T.Back()
  local run = T.run
  if not run or run.card or run.si <= 1 then return end
  T.LeaveStep()
  run.si = run.si - 1
  T.EnterStep()
end

-- To section `id`: in the sections being played, on from there; else that one alone.
function T.Jump(id)
  local run = T.run
  if not run or run.card or not T.byId[id] then return end
  T.LeaveStep()
  local at
  for i, q in ipairs(run.queue) do
    if q == id then at = i end
  end
  if not at then
    run.queue, at = { id }, 1
  end
  run.qi, run.si = at, 1
  T.EnterSection()
end

function T.NextClicked()
  local run = T.run
  if not run then return end
  if run.card then return T.CloseCard() end
  T.Advance()
end
function T.CloseClicked()
  local run = T.run
  if run and run.card then return T.CloseCard() end
  T.Exit()
end

-- Out of the tutorial at any point: everything back.
function T.Exit()
  if not T.run then return end
  if T.run.card then return T.CloseCard() end
  T.End(false)
end

-- The end: everything back as the player had it, but the minimap answer. `completed`: the last card, else a line in
-- the chat.
function T.End(completed)
  local run = T.run
  if not run then return end
  T.LeaveStep()
  local g, R = GPS(), ns.Record
  T.RestoreLive(run.snapshot, function() T.ApplyKeep(run, true) end)
  T.Try("the tools", function()
    if run.snapshot.mapEditOpen and g.SetMapEditOpen then g.SetMapEditOpen(true) end
    if run.snapshot.roadMode then g.SetRoadMode(true) elseif run.snapshot.wallMode then g.SetWallMode(true) end
    g.Redraw()
  end)
  if T.list then T.list:Hide() end
  if T.countdown then T.countdown:Hide() end
  T.Ticker():Hide()
  T.Glow():Hide()
  T.target = nil
  local tut = Tut()
  tut.run = nil
  if completed then
    run.card = { title = L["That's the tour"],
      text = L["Everything is back as you had it. Replay any part in Options > Help, or type /agps tutorial."] }
    run.step, run.paused = nil, nil
    T.ShowStep()
  else
    T.run = nil
    if T.panel then T.panel:Hide() end
    ns.Print(L["Tutorial closed: everything is back as you had it. Options > Help plays it again."])
  end
  T.RefreshHelp()
end
function T.CloseCard()
  T.run = nil
  if T.panel then T.panel:Hide() end
end

-- Combat: the panel and the glow out of the way, nothing set up or looked at; the step goes on when it ends.
function T.Pause()
  local run = T.run
  if not run or run.card or run.paused then return end
  run.paused = true
  if T.panel then T.panel:Hide() end
  if T.list then T.list:Hide() end
  T.Glow():Hide()
  T.target = nil
end
function T.Resume()
  local run = T.run
  if not run or not run.paused then return end
  run.paused = nil
  T.ShowStep() -- (the step as it was: what the player did meanwhile is looked at now, not set up again)
end

-- One look (every T.POLL): the whole map kept out, the glow on its target, and whether the player did the step.
function T.Tick()
  local run = T.run
  if not run or run.paused or run.card or not run.step then return end
  local g = GPS()
  if g.Held and g.Held() then return T.Exit() end -- (a companion's game took the map: out of its way, everything back)
  if run.section.full and not run.step.stay and g.mmState.on and not g.mmState.expanded and not g.mmState.tween then
    pcall(T.EnsureFull)
  end
  T.UpdateTarget()
  T.SizePanel()
  T.UpdateCountdown()
  if run.doneAt then
    if GetTime() - run.doneAt >= T.DONE_PAUSE then T.Advance() end
    return
  end
  if T.Waits(run) then
    local step = run.step
    local ok, did = pcall(step.done, run)
    if ok and did then
      run.doneAt = GetTime()
      T.ShowStep()
      if T.DONE_PAUSE <= 0 then T.Advance() end
    elseif step.poll then
      pcall(step.poll, run)
    end
  end
end

function T.Ticker()
  if T.ticker then return T.ticker end
  local f = CreateFrame("Frame", nil, UIParent)
  local acc = 0
  f:SetScript("OnUpdate", function(_, dt)
    acc = acc + (dt or 0)
    if acc < T.POLL then return end
    acc = 0
    local ok, err = pcall(T.Tick)
    if not ok and GPS().LogError then pcall(GPS().LogError, "tutorial", err) end
  end)
  f:Hide()
  T.ticker = f
  return f
end

---------------------------------------------------------------------------
-- Options > Help and /agps tutorial (the only ways in: no popup offers it)
---------------------------------------------------------------------------

-- At login, before the map, the route and the arrow start: a tutorial that was running when the game was left
-- (a /reload, a crash) has its snapshot saved; the settings and the route go back as the player had them, with the
-- minimap answer already given. Nothing pops up after: Options > Help or /agps tutorial starts it again.
function T.RestoreSaved()
  local tut = Tut()
  local run = tut and tut.run
  if type(run) ~= "table" then return end
  tut.run = nil
  local snap = run.snapshot
  if type(snap) == "table" and type(snap.gps) == "table" and type(snap.cdb) == "table" then
    T.RestoreData(snap)
    T.ApplyKeep(run, true) -- (cut short by a /reload: what was ticked is kept, as at its end)
    ns.db.mapView = type(snap.view) == "table" and snap.view or nil -- (the view the map opens on: the player's own)
  end
end

-- Options > Help's section: Play All, and a Play button a section (done ones marked).
function T.BuildHelp(ui)
  local tut = Tut()
  ui.note(L["A short tour of the main features on your own map. Everything goes back to how you had it after."])
  ui.button(L["Play All"], 150, function() T.Start() end)
  T.helpRows = {}
  for _, sec in ipairs(T.SECTIONS) do
    local b = ui.button(L["Play"], 90, function() T.Start({ sec.id }) end)
    local fs = ui.page:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
    fs:SetPoint("LEFT", b, "RIGHT", 10, 0)
    fs:SetText(T.SectionLabel(sec, tut.seen))
    T.helpRows[#T.helpRows + 1] = { id = sec.id, button = b, label = fs }
  end
end
-- The Help section built again (a section done).
function T.RefreshHelp()
  local O = ns.Options
  if O and O.RegisterHelpSection then pcall(O.RegisterHelpSection, "tutorial", T.BuildHelp) end
end

-- /agps tutorial [section|exit]
function T.Slash(arg)
  arg = arg and arg ~= "" and arg or nil
  if arg == "exit" or arg == "stop" then
    if T.run then T.Exit() else ns.Print(L["The tutorial isn't running."]) end
    return
  end
  if arg and not T.byId[arg] then
    local ids = {}
    for _, sec in ipairs(T.SECTIONS) do ids[#ids + 1] = sec.id end
    ns.Print(Format(L["Tutorial sections: %s"], table.concat(ids, " ")))
    return
  end
  T.Start(arg and { arg } or nil)
end

function T.Init()
  if T.events then return end
  T.BuildSections()
  local ev = CreateFrame("Frame")
  ev:RegisterEvent("PLAYER_REGEN_DISABLED")
  ev:RegisterEvent("PLAYER_REGEN_ENABLED")
  ev:RegisterEvent("PLAYER_LOGOUT") -- (a /reload or logout: the spell-jump demo undone before the game saves)
  ev:SetScript("OnEvent", function(_, event)
    if event == "PLAYER_REGEN_DISABLED" then
      pcall(T.JumpDemoStop, "combat")
      pcall(T.Pause)
    elseif event == "PLAYER_LOGOUT" then
      pcall(T.JumpDemoStop, "logout")
    else
      pcall(T.Resume)
    end
  end)
  T.events = ev
  T.RefreshHelp()
end
