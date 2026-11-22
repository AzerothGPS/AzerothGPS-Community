-- Slash commands: /agps (alias /gps)
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)

local HELP = {
  L["/agps                    (options window; also right-click the minimap button)"],
  L["/agps show | hide | toggle"],
  L["/agps opacity <0-100>"],
  L["/agps size <px>          (the map's height, default 450)"],
  L["/agps zoom <yards>       (center to edge; or mouse wheel over the frame)"],
  L["/agps rotate on|off      (heading-up / north-up)"],
  L["/agps lookat <continent> <x> <y> [zoom]  (the map's view on a spot) | follow  (back on you)"],
  L["/agps style openmap|minimap|zone|nospoiler|none (OpenMap / terrain / world map / explored parts only / no map, in the world map)"],
  L["/agps language auto|enUS|deDE|esES|esMX|frFR|itIT|koKR|ptBR|ruRU|zhCN|zhTW  (AzerothGPS's text; then /reload)"],
  L["/agps clear              (cancel the route)"],
  L["/agps pause              (pause or resume routing, the stops kept)"],
  L["/agps questroute         (the quest route: your quest log's objectives and turn-ins)"],
  L["/agps questroute <way> [off]  (turn a way on, or off, then route: fastest, low, gray, turnins, objectives, tracked, zone)"],
  L["/agps arrow on|off       (turn-by-turn direction arrow window)"],
  L["/agps import             (paste TomTom /way lines as stops; copy or send your route)"],
  L["/way [zone] x y [text]   (add a stop; several pasted lines = several stops; with TomTom too)"],
  L["/agps seamless [on|off|check|spots|explored on|off]  (on: the OpenMap map style, off: Terrain; check: the art's offsets and blend; spots: well-known places on its art; explored: only the explored areas)"],
  L["/agps poi taxi|poi|labels on|off (points of interest on the map)"],
  L["/agps quests on|off      (your quests' objectives and turn-ins)"],
  L["/agps bosses             (in a dungeon or with its map open: a route through its bosses)"],
  L["/agps instances on|off   (dungeon and raid entrances on the map)"],
  L["/agps caves on|off       (cave and mine entrances on the map)"],
  L["/agps herbs on|off | ore on|off | nodes on|off  (herbs, ore, or both on the map)"],
  L["/agps lock | unlock [map|arrow|directions]  (all, or just one; unlocked they can be moved)"],
  L["/agps reset              (restore default position and settings)"],
  L["/agps roads on|off       (show the extracted road network)"],
  L["/agps walls on|off        (show the walls routes go around)"],
  L["/agps minimap on|off     (minimap button)"],
  L["/agps replace on|off|small|medium|large|ground|mask|status  (the GPS map as the minimap)"],
  L["/agps tutorial [section|exit]  (the tutorial, or one of its sections: Options > Help lists them)"],
  L["/agps setup               (the first-time setup: minimap, map, directions, icons)"],
  L["/agps pad                (a controller: open and close the map with its Back button)"],
  L["/agps pad select|yes|remove|back|recenter | menu | zoom in|out | pan up|down|left|right  (the controller's controls, for macros)"],
  "/agps debug              (API probe; see `agps probes`)",
  "/agps debug route        (save your position and the route for a bug report; then /reload)",
  "/agps debug combat [on|off]  (an API probe a second into each fight)",
}

-- Words other addons add to /agps (the dev addon's map editor: `dev`, `draw`): ns.COMMANDS[word] = fn(b, msg), its
-- help lines in ns.COMMAND_HELP.
ns.COMMANDS, ns.COMMAND_HELP = {}, {}

local function OnOff(v, cur)
  if v == "on" then return true elseif v == "off" then return false end
  return not cur
end

local function Status()
  ns.Print(ns.GPS.Describe())
end

SLASH_AZEROTHGPS1 = "/agps"
SLASH_AZEROTHGPS2 = "/gps"
local Command
-- (a command's answers print with Options > General's quiet chat on too: ns.inSlash while it runs)
SlashCmdList.AZEROTHGPS = function(msg)
  local was = ns.inSlash
  ns.inSlash = true
  local ok, err = pcall(Command, msg)
  ns.inSlash = was
  if not ok then error(err, 0) end
end
Command = function(msg)
  local gps = ns.settings.gps
  local a, b = strsplit(" ", strtrim((msg or ""):lower()))
  local n = tonumber(b)
  if a ~= "" and ns.COMMANDS[a] then return ns.COMMANDS[a](b, msg) end
  if a == "" or a == "options" or a == "config" then
    ns.Options.Toggle()
    return
  elseif a == "show" or a == "hide" or a == "toggle" then
    -- (as the show/hide key: the map in the game's world map opens and closes that; the map as the minimap opens
    -- out and goes back to the square, never hidden there. Before 1.3.1 these only flipped the window's setting)
    local G = ns.GPS
    if ns.LogToggleStart then ns.LogToggleStart("/agps " .. a) end -- (kept for a bug report: ns.db.toggleLog)
    if G and G.WorldMapWanted and G.WorldMapWanted() then
      local open = G.WorldMapHosted()
      if a == "toggle" or (a == "show") ~= open then G.ToggleMapView() end
      return
    end
    if gps.shown and G and G.mmState and G.mmState.on and G.SetMinimapExpanded then
      G.SetMinimapExpanded(a == "show" or (a == "toggle" and not G.mmState.expanded))
      return
    end
    local wasMini = gps.minimized -- (minimized: show or toggle brings the map back)
    if a ~= "hide" then gps.minimized = nil end
    gps.shown = (a == "show") or (a == "toggle" and (not gps.shown or wasMini and true or false))
  elseif a == "opacity" and n then
    gps.alpha = math.max(0.05, math.min(1, n / 100))
  elseif a == "size" and n then
    gps.size = math.max(120, math.min(ns.GPS.SizeMax and ns.GPS.SizeMax() or 800, math.floor(n)))
    if ns.GPS.ClampSize then gps.size = ns.GPS.ClampSize(gps.size) end -- room for the quick buttons
  elseif a == "zoom" and n then
    ns.GPS.SetZoom(n)
  elseif (a == "zoom" and (b == "in" or b == "out")) or a == "menu"
      or (a == "pan" and (b == "up" or b == "down" or b == "left" or b == "right")) then
    -- (the controller's controls as macros, Pad.MACROS: a zoom or pan step, the map menu)
    local id = a == "menu" and "menu" or a == "zoom" and (b == "in" and "zoomIn" or "zoomOut")
      or ("pan" .. b:sub(1, 1):upper() .. b:sub(2))
    if ns.Pad then ns.Pad.MacroRun(id) end
    return
  elseif a == "follow" then -- (the map back on the player, as its recenter button)
    ns.GPS.Follow()
  elseif a == "lookat" then -- (QA: the map's view on a spot, as the public API's LookAt; display only)
    local _, c, x, y, z = strsplit(" ", strtrim(msg or ""))
    c, x, y, z = tonumber(c), tonumber(x), tonumber(y), tonumber(z)
    if c and x and y then
      ns.GPS.LookAt(c, x, y, z)
    else
      ns.Print("/agps lookat <continent> <x> <y> [zoom]")
    end
  elseif a == "rotate" then
    gps.rotate = OnOff(b, gps.rotate)
  elseif a == "style" then -- (issue #75: seamless, minimap = Terrain, zone = World Map, nospoiler = No Spoiler Map;
    -- issue #91: openmap = seamless, the OpenMap style, its saved value still "seamless"; none = No Map, Kooki3z
    -- 2026-11-20, only with the map in the game's world map: SetStyle says so)
    local style = ({ terrain = "minimap", world = "zone", openmap = "seamless", nomap = "none" })[b] or b
    if ns.GPS.STYLES[style] then
      ns.GPS.SetStyle(style) -- (not while a game on the map set it: API.HoldMap; it says so)
    else
      ns.Print(string.format(L["map style: %s. /agps style openmap|minimap|zone|nospoiler|none"], tostring(gps.style)))
    end
  elseif a == "language" then -- (AzerothGPS's own text in another language than the game's: Locales.lua)
    local want
    for code in pairs(ns.LOCALES) do
      if code:lower() == (b or ""):lower() then want = code end
    end
    if want or b == "auto" then
      ns.db.language = want
      ns.Print(string.format(L["AzerothGPS's language: %s. Type /reload to apply it."], want or L["the game's"]))
    else
      ns.Print(string.format(L["AzerothGPS's language: %s. /agps language auto|enUS|deDE|esES|esMX|frFR|itIT|koKR|ptBR|ruRU|zhCN|zhTW"],
        ns.db.language or L["the game's"]))
    end
    return
  elseif a == "lock" or a == "unlock" then
    -- all three, or just "map" / "arrow" / "directions" (the directions text: its own lock since 1.3.9)
    local lock = a == "lock"
    local all = b ~= "map" and b ~= "arrow" and b ~= "directions" and b ~= "text"
    if all or b == "map" then gps.locked = lock end
    if all or b == "arrow" then gps.arrowLocked = lock end
    if all or b == "directions" or b == "text" then gps.dirLocked = lock end
  elseif a == "minimap" then
    ns.settings.minimap.hide = not OnOff(b, not ns.settings.minimap.hide)
  elseif a == "setup" then -- (the first-run setup again, Setup.lua)
    if ns.Setup then ns.Setup.Open() end
    return
  elseif a == "tutorial" then -- (the tutorial: all of it, one section by its id, or out of it)
    if ns.Tutorial then ns.Tutorial.Slash(b) end
    return
  elseif a == "replace" then -- (the GPS map as the minimap: on, off, its size, how its ground is hidden)
    if b == "status" then
      ns.Print(ns.GPS.MinimapReplaceStatus())
      return
    elseif ns.GPS.MINIMAP_SIDES[b or ""] or b == "xlarge" then -- (the old extra large: large now)
      gps.replaceMinimapSize = b == "xlarge" and "large" or b
    elseif b == "ground" or b == "mask" then
      gps.replaceMinimapHide = b
    else
      gps.replaceMinimap = OnOff(b, gps.replaceMinimap)
    end
    ns.Options.Apply()
    ns.Print(ns.GPS.MinimapReplaceStatus())
    return
  elseif a == "import" then
    ns.Import.Toggle()
    return
  elseif a == "seamless" or a == "openmap" or a == "atlas" then -- (the seamless map's setting, as Options > Map's; check: its alignment.
    -- "atlas": the Atlas window's old command, issue #60: the seamless map is the one view now)
    if a == "atlas" then
      if b == "check" then
        ns.Atlas.CheckMapping()
      else
        ns.Print(L["the Atlas window is now the map itself: zoom the map out with the mouse wheel (/agps seamless)."])
      end
    elseif b == "on" or b == "off" then
      if ns.Atlas.SetSeamless(b == "on") then ns.Print(b == "on" and L["the map style: OpenMap"] or L["the map style: Terrain"]) end
    elseif b == "check" then
      ns.Atlas.CheckSeamless()
    elseif b == "spots" then
      ns.Atlas.CheckMapping()
    elseif b == "explored" then
      local v = select(3, strsplit(" ", strtrim((msg or ""):lower())))
      ns.Atlas.SetExploredOnly(OnOff(v, gps.seamExploredOnly))
      ns.Print(gps.seamExploredOnly and L["the seamless map shows only the areas you've explored"] or L["the seamless map shows every area"])
    else
      ns.Print(gps.style == "seamless" and L["the seamless map is on: /agps seamless on|off|check|spots|explored"]
        or L["the seamless map is off: /agps seamless on|off|check|spots|explored"])
    end
    return
  elseif a == "arrow" then
    gps.arrow = OnOff(b, gps.arrow)
  elseif a == "poi" then
    local key = ({ taxi = "poiTaxi", poi = "poiPoi", labels = "poiLabels" })[b]
    if key then gps[key] = OnOff(select(3, strsplit(" ", msg:lower())), gps[key]) end
  elseif a == "clear" then
    if not (ns.GPS.ClearRoute and ns.GPS.ClearRoute()) then ns.Nav.Clear() end -- (as the map's Clear Route)
  elseif a == "questroute" then -- (the map menu's Quest Route: a controller's macro, asked 2026-11-16)
    -- (/agps questroute <way> [off]: one of its right-click menu's toggles, GPS.QUEST_WAYS, turned on (or off) as the
    -- menu does, others of its group off, saved; then the quest route by the saved options. Set, not flipped: a macro
    -- does the same each press)
    local way = b and b ~= "" and ns.GPS.QuestWayByWord and ns.GPS.QuestWayByWord(b)
    if b and b ~= "" and not way then
      ns.Print(L["Quest Route ways: fastest, low, gray, turnins, objectives, tracked, zone."])
    elseif way and ns.GPS.QuestToggle then
      ns.GPS.QuestToggle(way, select(3, strsplit(" ", msg:lower())) ~= "off", true)
    elseif ns.GPS.QuestRoute then
      ns.GPS.QuestRoute()
    end
  elseif a == "pause" then -- (routing paused or resumed, the stops kept: Nav.SetPaused)
    if not ns.Nav.dest then
      ns.Print(L["No route to pause."])
    else
      ns.Nav.TogglePaused()
      ns.Print(ns.Nav.paused and L["Routing paused: /agps pause again to resume."] or L["Routing resumed."])
    end
  elseif a == "quests" then
    gps.layerQuests = OnOff(b, gps.layerQuests)
  elseif a == "nodes" then
    local on = OnOff(b, gps.layerHerbs or gps.layerOre)
    gps.layerHerbs, gps.layerOre = on, on
  elseif a == "herbs" then
    gps.layerHerbs = OnOff(b, gps.layerHerbs)
  elseif a == "ore" then
    gps.layerOre = OnOff(b, gps.layerOre)
  elseif a == "bosses" then
    ns.GPS.BossRoute()
    return
  elseif a == "dungeonroute" then
    ns.GPS.SetDungeonRoute(b == "on" or (b ~= "off" and gps.dungeonRoute == false))
    return
  elseif a == "instances" then
    gps.layerInstances = OnOff(b, gps.layerInstances ~= false)
  elseif a == "caves" then
    gps.layerCaves = OnOff(b, gps.layerCaves ~= false)
  elseif a == "roads" then
    gps.showRoads = OnOff(b, gps.showRoads)
  elseif a == "walls" then
    gps.showWalls = OnOff(b, gps.showWalls)
  elseif a == "pad" then
    -- (a controller: "Show/Hide AzerothGPS" on its Back button, asked; Pad.lua, offered once by itself. With a control's
    -- name: that control, once, as its button: the controller's controls as macros, Pad.MACROS)
    if not ns.Pad then return end
    if b and b ~= "" then
      local id = ns.Pad.MacroId(b)
      if id then ns.Pad.MacroRun(id) else ns.Print(L["/agps pad select|yes|remove|back|recenter | menu | zoom in|out | pan up|down|left|right  (the controller's controls, for macros)"]) end
      return
    end
    ns.Pad.Offer()
    return
  elseif a == "reset" then
    ns.settings.gps = CopyTable(ns.DEFAULTS.gps)
  elseif a == "debug" and b == "toggle" then
    -- (what the show/hide key would do now, and the map after it: asked 2026-11-16, the /agps toggle macro doing
    -- nothing at all with the game's controller UI on)
    -- (the key's toggle, kept in ns.db.toggleLog too: ns.LogToggle)
    ns.inToggleLog = true
    local e = ns.LogToggle("debug", AzerothGPS_ToggleMap)
    ns.inToggleLog = nil
    ns.Print("before: " .. e.before)
    if e.err then ns.Print("error: " .. e.err) end
    ns.Print("after: " .. e.after)
  elseif a == "debug" then
    if b == "route" then
      -- (for a bug report: where the player is and the route as it stands, saved for `agps probes`
      -- style reading after a /reload: ns.db.routeDebug)
      local N = ns.Nav
      local x, y, c = ns.Geo.PlayerWorld()
      local lvl = c and N.PlayerLevel and N.PlayerLevel(c) or c
      local r = N.route
      local pts = {}
      for i = 1, math.min(#(r and r.pts or {}), 200) do pts[i] = r.pts[i] end
      local stops = {}
      for i, d in ipairs(N.stops) do stops[i] = { x = d.x, y = d.y, cont = d.cont, name = d.name } end
      ns.db.routeDebug = { time = time(), x = x, y = y, cont = c, level = lvl,
        z = N.PlayerZ and N.PlayerZ() or nil, indoors = N.Indoors and N.Indoors() or nil,
        stops = stops, pts = pts, kinds = r and r.kinds or nil,
        pending = r and r.pending or nil, length = r and r.length or nil,
        pendingEdits = ns.Record and ns.Record.pending or nil, roadMode = ns.GPS.roadMode, wallMode = ns.GPS.wallMode }
      -- (and the plan as it stands: each leg, its ride, the ride check's verdict, the risk question and the answers, the
      -- player's level and side; asked 2026-11-16: a "No" to "Risk enemy territory?" left the walk past Dun Algaz, and
      -- the first leg alone said nothing of why)
      local legs = {}
      for i, lg in ipairs(r and r.legs or {}) do
        legs[i] = { cont = lg.cont, x1 = lg.x1, y1 = lg.y1, x2 = lg.x2, y2 = lg.y2, walk = lg.walk and true or nil,
          ride = lg.ride and tostring(lg.ride[8] or "?") .. ":" .. tostring(lg.ride[10] or lg.ride[9] or "?") or nil }
      end
      local risk = {}
      for k, v in pairs(N.riskOk or {}) do risk[#risk + 1] = tostring(k) .. "=" .. tostring(v) end
      local q = N.riskQuestion or N.riskAsking
      local db = ns.db.routeDebug
      db.legs, db.rideCheck, db.riskOk = legs, N.lastRideCheck, risk
      db.riskQuestion = q and { key = q.key, saved = q.saved, asking = N.riskAsking and true or nil } or nil
      db.hostileNote = N.HostileNote and N.HostileNote() or nil
      db.playerLevel = UnitLevel and UnitLevel("player") or nil
      db.faction = N.Faction and N.Faction() or nil
      db.avoidHostile, db.avoidHighZones = ns.settings.gps.avoidHostile, ns.settings.gps.avoidHighZones
      db.rides = N.RideDebug and N.RideDebug() or nil
      ns.Print(string.format("route saved for the bug report (%s stops, %d points): /reload to write it out",
        #stops, #pts / 2))
      return
    elseif b == "combat" then
      -- (a probe a second into each fight, by itself: what combat hides from addons, the group's positions too)
      ns.settings.combatProbe = OnOff(select(3, strsplit(" ", strtrim((msg or ""):lower()))), ns.settings.combatProbe)
      ns.Print("probe on entering combat: " .. (ns.settings.combatProbe and "on" or "off"))
      return
    elseif b == "interior" then
      for _, l in ipairs(ns.GPS.DebugInterior()) do ns.Print(l) end
    elseif b == "perf" then
      for _, l in ipairs(ns.PerfReport()) do ns.Print(l) end
    elseif b == "dashes" then
      ns.GPS.dashTexture = not ns.GPS.dashTexture
      ns.Print("dotted route lines: " .. (ns.GPS.dashTexture and "textured (one line per leg)" or "a line per dash"))
      ns.GPS.Redraw()
    elseif b == "layers" then
      ns.Print(ns.Layers.Describe())
    elseif b == "rotsign" then
      ns.GPS.rotSign = -ns.GPS.rotSign
      ns.Print("tile rotation sign now " .. ns.GPS.rotSign)
    else
      ns.RunProbe("manual")
    end
    return
  elseif a == "status" then
    Status()
    return
  else
    for _, l in ipairs(HELP) do ns.Print(l) end
    for _, l in ipairs(ns.COMMAND_HELP) do ns.Print(l) end
    return
  end
  ns.Options.Apply()
  Status()
end
