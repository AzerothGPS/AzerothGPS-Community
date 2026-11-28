-- AzerothGPS core: saved variables, settings, events, API probe.
local addonName, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)

ns.DEFAULTS = {
  gps = {
    -- map window
    shown = true,
    size = 450, -- the window's height in UI units (asked, 2026-10-01: 450 by default)
    freeSize = false, -- "Any shape": the corner sets the width (`width`) and the height apart (asked 2026-10-04); off: square
    lockSize = false, -- off (the default since 1.1.1): drag the map's bottom-right corner (GPS.MakeSizeGrip), unless
    -- the map's position is locked (`locked`); on: the size only by the slider
    searchCommonNpcs = false, -- the search finds NPCs met in several places too (Layers.KnownNpcs, asked 2026-10-06)
    searchEnemies = true, -- the search finds the enemy mobs too (Data/Mobs.lua, 1.4.0, GPSFrame's G.ShippedMobEntries)
    distanceUnits = "yards", -- distances shown in yards (the game's), "metric" or "imperial" (Nav.FormatDistance, asked 2026-10-07)
    minimapRoute = true, -- the route on the game's minimap too (asked 2026-10-06)
    minimapIcons = false, -- the map's icons shown on the game's minimap too (issue #10; off by default since 1.1.8, #31)
    minimapShape = "auto", -- the game's minimap: "auto" (GPS.MinimapSquare), "round", "square"
    replaceMinimap = false, -- the GPS map as the game's minimap (1.2.0, asked 2026-11-08; GPSFrame's G.MinimapMode)
    useWorldMap = false, -- the GPS map in the game's world map window, not one of its own (1.2.0, asked 2026-11-10)
    escClosesMap = true, -- Escape closes the world map with the GPS map in it, as the game's own does (off: asked 2026-11-20)
    -- an extra GPS map window, left open, Escape never closing it (Kooki3z 2026-11-20; GPSFrame's G.extra); its own
    -- place, size, zoom and minimized logo: extraWindowPoint, extraWindowSize, extraWindowWidth, extraWindowZoom,
    -- extraWindowMinimized, extraWindowMiniAt (none till it's moved: the first window's)
    extraWindow = false,
    -- companion addons' buttons (AzerothGPS_StreetView's figure and Street Guess's) at the end of the map menu's
    -- column, not on its row going right (1.4.2, Kooki3z 2026-11-27; GPSFrame's G.SyncCompanions)
    companionsInMenu = false,
    replaceMinimapKeepSquare = true, -- the square kept as it is while the map is grown out of it, both shown (asked
    -- 2026-11-15; off: the game's minimap given back meanwhile; GPSFrame's G.SquareKeptOut)
    replaceMinimapIdle = 5, -- s of quiet before the map grown out of the square goes back (0: never; asked 2026-11-11)
    replaceMinimapCollapseOnMove = false, -- the map grown out of the square goes back as the player starts moving
    replaceMinimapCollapseOnCombat = false, -- ... as combat starts (both asked 2026-11-09, off by default)
    replaceMinimapRoute = true, -- the route's line on the square (asked 2026-11-17; off: not drawn there, the opened map
    -- and the world map keep it; GPSFrame's G.SquareHidesRoute)
    replaceMinimapResume = true, -- a glowing Resume Routing button by the square's logo while routing is paused (1.3.9,
    -- asked 2026-11-18; GPSFrame's G.PlaceMinimapResume)
    replaceMinimapLogo = true, -- the AzerothGPS logo button on the square (Kooki3z 2026-11-27 for 1.4.2: "add option to
    -- hide minimap logo button"; off: hidden, its clicks reached by the Show/Hide GPS key, /agps show and /agps;
    -- GPSFrame's G.SquareLogoShown)
    replaceMinimapLogoKeep = true, -- the logo in its original spot over the square's corner (1.4.2, Kooki3z 2026-11-28;
    -- unticked by a drag; GPSFrame's G.LogoKept)
    replaceMinimapLogoUnlocked = false, -- the logo dragged round the square's edge (1.4.2; GPSFrame's G.LogoDragStart;
    -- its spot `replaceMinimapLogoAngle`, unset: its corner)
    replaceMinimapNoBorder = false, -- the square without its border, only the map (Kooki3z 2026-11-26 for 1.4.1;
    -- GPSFrame's G.SquareHidesBorder)
    replaceMinimapSize = "small", -- its square: "small" (200), "medium" (260), "large" (320) (G.MINIMAP_SIDES)
    replaceMinimapHide = "ground", -- how the minimap's ground is hidden: "ground" (C_Minimap.SetDrawGroundTextures) or
    -- "mask" (a fully transparent mask); /agps replace ground|mask
    seamExploredOnly = false, -- the seamless map's art: only the areas this character has explored (issue #60)
    -- The seamless map's stages (Options > Map, asked 2026-11-14; GPSFrame's G.ApplySeamPlayer): where the zones' map gives way
    -- to the continents' and the continents' to the world (the wheel's notches out from where they're shipped), and
    -- how long each stage's blend is (times the shipped). These are the shipped stages; `seamTerrainYd` (unset) too.
    seamContinentAt = 0, seamWorldAt = 0, seamTerrainBlend = 1, seamContinentBlend = 1, seamWorldBlend = 1,
    alpha = 1, -- whole-frame opacity
    stepsCollapsed = true, -- the map's top panel: only the whole trip's times (the -/+ button)
    stepsAll = false, -- the map's top panel: all the steps, not just the next few (its + button)
    fadeMoving = true, -- fade the map while moving (not the route, stops or player arrow)
    movingAlpha = 1, -- ... to this opacity
    locked = false, -- the map; unlocked: drag the window frame's title bar (or the Move tab) to move it
    windowFrame = true, -- the game-style window frame around the map (title bar, logo, close)
    -- the direction arrow and the directions; unlocked (the default since 1.2.2, asked 2026-11-11: a player found
    -- them "locked to the center screen" outside the tutorial): drag to move, corner to resize, right-click to lock
    arrowLocked = false,
    -- the directions text's own lock (1.3.9, asked 2026-11-18: "a separate lock option for the directions text than the
    -- arrow"); `arrowLocked` is the arrow's alone since. Saved before: the old shared lock's value (ns.SplitDirLock)
    dirLocked = false,
    point = { "BOTTOM", "UIParent", "BOTTOM", 495, 191 },
    hz = 20, -- redraws per second (at most; skipped when nothing changed; Options > Performance)
    -- performance (Options > Performance; its "Use Low-End Settings" sets these lighter)
    arrowHz = 0, -- the direction arrow turned this many times a second (0: every frame)
    arrowEase = true, -- its big turns eased, slow, fast, slow (Arrow.lua A.EaseStep; asked 2026-11-20)
    rerouteSeconds = 2, -- a route the player left is worked out again at most this often
    gentleBackground = false, -- background searches in smaller slices of each frame (GPS.PumpBudget)
    -- map
    style = "seamless", -- "seamless" (the terrain, the wheel on out to the whole world on the stitched art: Atlas/Atlas.lua,
    -- GPSFrame's G.Seamless; the default since issue #75), "minimap" (Terrain: the terrain tiles alone, as before the
    -- seamless map), "zone" (world map art) or "nospoiler" (explored parts only). Not "seamless", the stitched map's
    -- files are dropped at login
    rotate = false, -- heading-up; false = north-up
    zoom = 524.288, -- yards from center to edge
    interiors = true, -- switch to building interior maps indoors (cities, inns, caves)
    roundIcons = true, -- the map's game icons round with a ring (GPSFrame's G.RoundIcon)
    iconSize = "medium", -- the map's icons: small (as before 2026-11-14), medium (+25%), large (+50%), xlarge (x2, 1.3.9): G.ICON_SIZES
    interiorZoomYd = 150, -- zoomed in this close (yards to the map's edge) over a building or cave: its inside map
                          -- (GPSFrame's G.InteriorZoomYd, G.INTERIOR_ZOOM_YD; 0: only inside)
    interiorHoldSec = 30, -- a left click holds the hovered building's inside map this long (G.InteriorHoldSec)
    terrainZoomOut = true, -- terrain view: right-click opens the world map to pick a place
    showRoads = false, -- draw the road network the routes use (drawn roads too)
    -- show on the map
    poiTaxi = true, -- flight masters
    showParty = true, -- party and raid members on the map (GPS.DrawParty)
    poiPoi = true, -- the world map's points of interest
    poiLabels = true, -- place names (when zoomed in)
    layerQuests = true, -- your quests' objectives and turn-ins
    layerQuestAreas = true, -- ... and their objective areas, outlined (on the map)
    layerQuestAreasMinimap = true, -- ... and on the GPS map as the minimap (asked 2026-11-15: "2 choices")
    layerHerbs = true, -- herbs you've gathered, hovered on the minimap, right-clicked or imported
    layerOre = true, -- ... and ore
    nodeFilter = {}, -- the herbs and veins picked in Find Herbs and Ore, { [name] = true }: only those shown (none: all)
    nodeAvailable = false, -- Find Herbs and Ore's Available: only those the character's skill gathers shown
    layerCity = true, -- city locations guards pointed out (trainers, bank, ...)
    layerInstances = true, -- dungeon and raid entrances (click one for its map, with its bosses)
    showDungeonPaths = true, -- a dungeon's dotted way through on its map (the map menu's Show Routes; GPS.DungeonPathsOn)
    dungeonPathColor = "gold", -- a dungeon's dotted usual way: a key of GPS.DUNGEON_PATH_COLORS (the map's picker)
    layerCaves = true, -- cave and mine entrances (double-click one for a stop)
    -- (1.4.2, Kooki3z 2026-11-27: the map's elements shown or hidden one by one from the Map Layers button, GPSFrame's
    -- G.MAP_LAYERS; these four had no switch of their own before)
    layerRoute = true, -- the route's line on the map (off: still routed, the directions as ever; only not drawn)
    layerStops = true, -- the stops' and the destination's markers
    layerDocks = true, -- boats', zeppelins' and the tram's docks (with points of interest before 1.4.2: InitDB's docks142)
    layerNpcs = true, -- the NPCs drawn in a building's inside map (GPSFrame's G.AddInteriorNpcs)
    -- how far out each kind's icons show (yards to the map's edge at the reference size; 6100 the top notch: always;
    -- "stage": gone past the seamless map's world stage, as shipped): GPSFrame's G.IconShown, asked 2026-11-14
    iconYdTaxi = 6100, iconYdPoi = "stage", iconYdQuests = 6000, iconYdCity = "stage", iconYdInstances = 6100,
    iconYdCaves = "stage", iconYdHerbs = "stage", iconYdOre = "stage", iconYdPins = 6100,
    approachZoom = true, -- zoom in near the next stop, back out once there
    -- routing
    navCloseClears = true, -- the X on the map's route panel cancels the route (else just closes the panel)
    -- the map's route panel (1.3.9, GPSFrame's G.PlaceNavPanel): its width, a share of the map's (30-100; 100 the whole
    -- width, as before), its side when narrower ("left", "center", "right"), and detached in its own window
    -- (navPanelPoint, navPanelDetachedWidth: where it was dragged and how wide; nil until then)
    navPanelWidth = 100,
    navPanelAlign = "left",
    navPanelDetached = false,
    -- (detached only, 1.3.9: just its text, every button hidden; its dark box's opacity in percent, 70 as before)
    navPanelHideButtons = false,
    navPanelAlpha = 70,
    navPanelLocked = false, -- (detached: no dragging, sizing or right-click back to the map)
    navPanelWrap = false, -- (detached and sized: long lines wrap instead of being cut short)
    reopenFollow = false, -- hidden while looking around the map (a route set): reopens on the player
    followOnMove = false, -- the map panned away follows the player again once they start moving (asked 2026-11-20)
    questing = true, -- a stop in a quest area is done when the quest's objectives are
    questZoneOnly = false, -- the quest route: only the quests in the zone you're in
    questTrackedOnly = false, -- the quest route: only the quests you track (Questie's tracker's, else the game's; Layers.QuestTracked)
    -- (1.3.14, the Quest Route button's right-click toggles too: QuestWays.lua; at most one of these two and
    -- questTrackedOnly on, G.SetQuestToggle)
    questTurninsOnly = false, -- the quest route: only the finished quests' turn-ins
    questObjectivesOnly = false, -- the quest route: only the objectives, no turn-ins
    questLevelOrder = "off", -- the quest route by level: "off" (fastest), "low" (lowest first), "gray" (about to turn gray first); Nav.QuestBands
    questAutoReroute = false, -- the quest route made again by itself on a quest picked up or finished (Nav.MarkQuestRouteStale)
    questPickRoute = false, -- the route to the quest picked in the quest log or tracker (C_SuperTrack; G.PickedQuestRoute)
    avoidHighZones = true, -- routes keep out of zones too high for the character (red on the map), if there's a way round
    dungeonRoute = true, -- entering a dungeon or raid starts its boss route (other routes held off while on)
    useHearthstone = true, -- start a route with the hearthstone (or Astral Recall) when faster
    useTeleports = true, -- ... or a class teleport (mage teleports, Teleport: Moonglade)
    usePartyPortals = false, -- ... or a portal a mage in the group near you can open (Teleports.lua; asks another player)
    useWaterWalking = true, -- water walking, Levitate and the like make water as fast as land (Nav.WaterFast)
    useFlights = true, -- take flights between the flight masters this character knows
    flightMapRing = true, -- a ring round the route's next flight on the flight map (Taxi.MarkTaxiMap)
    fastestOrder = true, -- routes with several stops: visit them in the fastest order
    autoPauseRouting = false, -- routing paused when you're not following it (Nav.WatchFollowing; the low-end settings turn it on)
    autoPauseSeconds = 120, -- ... the time to the stop grown by this many seconds over its lowest
    stutterPause = true, -- routing cut back, then paused, when it makes the game stutter (Nav.RouteWork)
    stopsAhead = 3, -- stops routed and drawn on the map at a time (1 to Nav.PLAN_AHEAD); the next come in as they're reached
    avoidHostile = true, -- routes keep away from the other faction's guards (their towns)
    avoidElites = true, -- routes keep away from elite enemy areas (Data/Elites.lua; item 91, Router.EliteMin)
    eliteOffset = -10, -- ... those whose elites' top level is at least the player's plus this (Router.ELITE_OFFSET_MIN to MAX)
    showAvoided = true, -- the guard zones a route goes around, drawn red on the map (item 63c); the elite areas gold
    worldGrid = true, -- 1.4.0's world routing: routes on the open world's walk grid (WorldGrid.lua); always on (item 74)
    buildingGrid = true, -- 1.4.2's building routing (test): walks inside the open world's buildings on their own grids
    -- (BuildingGrid.lua, item 119), in BuildingGrid.TOWNS only for now
    cityGrid = true, -- 1.4.0's city routing: routes inside the capitals on their walk grids (CityGrid.lua); always on
    -- since 2026-11-23 (Kooki3z: "this will be the new default for pathing going forward")
    allowSwim = true, -- routes may swim (Passability.avoidSwim off: Nav.SyncSwim); off, they go round by land
    useClassSpells = true, -- big drops with Slow Fall, Levitate or a racial ready (FallSpells.lua)
    expertJumper = false, -- spell jumping, any height: cast just before landing (FallSpells.lua, under useClassSpells)
    -- (item 102: immunities an Expert jumper may land with, each its own; FallSpells.SPELLS' `option`; item 125b,
    -- Kooki3z: off by default, and nil is off (FallSpells.RowAllowed), a value saved stays)
    jumpDivineShield = false, jumpDivineProtection = false, jumpBlessingOfProtection = false, jumpIceBlock = false,
    safeDropYd = 39, -- the drop routes take out of combat without a fall spell (Nav.PlainSafeDrop, Options' Safe drop)
    cityKeepOrder = true, -- ... except stops down in a city: in the order placed
    importKeepOrder = true, -- stops imported (Import and Share, /way lists, shared routes) in the order listed (Nav.keepOrder)
    acceptWay = true, -- TomTom /way commands (typed or pasted in chat) add route stops
    acceptMapPins = true, -- a map pin link ("[Map Pin Location]") clicked in chat adds a stop there
    acceptShared = true, -- routes other players send (asked before use)
    -- directions
    arrow = true, -- turn-by-turn direction arrow window (TomTom style): either panel on, arrowShown or dirShown
    arrowShown = true, -- the arrow panel itself (Kooki3z 2026-11-24: the arrow and the directions text apart)
    arrowPoint = { "CENTER", "UIParent", "CENTER", 15, 267 },
    arrowSize = { 370, 97 }, -- taller: the later stops are listed too; wider (2026-10-04): "Continue straight, then
    -- slight right in 180 yd" on one line (253 units of text; the arrow's column and margins 82)
    -- the map window's looks (Options > Window, asked 2026-11-04; Looks.lua)
    arrivalEffect = "confetti", -- at the trip's last stop: "confetti", "fireworks" or "none"
    windowTint = "default", -- the window frame's tint: "default" (the game's own) or one of Looks.TINTS' keys
    windowButtons = "default", -- its buttons' color: "default", "frame" (the tint's) or a tint's key
    windowClose = "buttons", -- its X's: "buttons" (as the buttons), "default", "frame" or a tint's key
    routeColor = "blue", -- "blue" (AzerothGPS's own) or "rainbow"
    -- the route lighter uphill, darker downhill (Kooki3z 2026-11-20: "can we use shades of lighter or darker path colors
    -- to indicate elevation or de-elevation of a route?"; GPSFrame's G.SlopeColor)
    routeSlopeShade = true,
    -- (item 114, MapExtras.lua) the route's height profile strip on the map, and the floor picker where floors stack
    heightProfile = true,
    floorPicker = true,
    charm = "none", -- hanging from the logo: "none" or a charm's key (Looks.CHARMS, or one another addon added)
    charmSwing = true, -- it swings and twists as you go (off: hangs still)
    -- Options > Routing (Router.RoadFactor): below 0 the roads kept more, above 0 open ground. +3 since 1.4.0 (Kooki3z
    -- 2026-11-22, in game with the world grid: "a +3 on routing as default makes more sense, snaps to roads good enough
    -- and make the short cuts seem worthwhile"); a saved 0, the old default, moved to it once (InitDB, roadTolerance140)
    roadTolerance = 3,
    arrowBg = 0, -- background opacity of the arrow's panel (the directions': dirBg, unset: this one's)
    -- (two panels since 1.1.9, asked 2026-10-30: the arrow and the directions; dirPoint and dirSize made from arrowPoint
    -- and arrowSize the first time, Arrow.FromOld)
    arrowPx = 58, -- the arrow's size
    arrowSnap = true, -- the arrow against a side of the directions, the two moved as one (off: each on its own)
    arrowSide = "left", -- that side: "left", "right", "top", "bottom"; "hide": no arrow, the directions alone (asked
    -- 2026-11-17; only while the directions show: Arrow.lua's Hidden)
    dirShown = true, -- the directions panel (off: the arrow alone)
    dirStopsOnly = false, -- the directions list the stops only, no turns
    dirTextScale = 1, -- the directions' text size
    dirTextStyle = "ui", -- their font: a supported UI's text style ("ui", with DaylightUI or EllesmereUI) or ours ("agps"; 1.4.2, UIFont.lua)
    targetNpcButton = true, -- near the next stop's NPC, a Target button under the directions panel (1.3.14)
    targetNpcMarkSolo = true, -- ... its click also marks the NPC with the stop's route marker, solo
    targetNpcMarkGroup = false, -- ... and in a party or raid (a raid: with lead or assist only)
    waypointUI = true, -- the next stop as the Waypoint UI addon's waypoint, with that addon (1.4.2; WaypointUI.lua)
    waypointUIPins = true, -- ... and the player's own Ctrl-click pins there added as stops (1.4.2; WaypointUI.lua)
    -- click-through: the map and the arrow ignore the mouse (clicks go to the game world)
    clickThroughMoving = false, -- while moving
    clickThroughCombat = false, -- in combat (off by default: asked, 2026-10-01)
    -- in combat
    combatHideMap = false, -- hide the map (nothing to click by mistake; off by default, asked 2026-10-01)
    combatHideArrow = false, -- hide the direction arrow
    showCoords = true, -- the map's X, Y line at its bottom (asked 2026-11-17, "add option to general to hide X,Y display")
    keyBlockedInCombat = true, -- the show/hide and Quick Search keys don't show the map (it still hides it; issue #20;
    -- on by default since 2026-11-14, asked)
    -- a controller (Pad.lua; asked 2026-11-16, "full controller support", phase 1): the map's buttons on the pad while
    -- it's open, on by itself with a pad active; the right stick pans too (off: the D-pad only, the camera untouched)
    padControl = true,
    -- (the sticks' pan and zoom options taken out: asked 2026-11-16, "remove the L and R stick pan options they don't
    -- work")
    padLegend = true, -- (the controller's buttons listed in a box on the map's left, Pad.UpdateBox)
    combatAlpha = 1, -- map opacity in combat (unset: the map's usual opacity)
    arrowCombatAlpha = 1, -- arrow opacity in combat
    -- help improve AzerothGPS (opt-in: off unless the player turns them on)
    pinning = true, -- Shift + left-click on the map: "Create Pin" (Pins.lua)
    showCustomPins = true, -- the pins on the map (the player's and the shared ones)
    otherAddonPins = true, -- other addons' world map icons on the map too (OtherPins.lua; asked 2026-11-09)
    showWalls = false, -- draw the walls routes don't walk through (blood red)
    quietChat = false, -- none of AzerothGPS's messages in the chat window, but a /agps command's answers (ns.Print)
    -- what "Copy Map Data..." puts in the text (Feedback.KINDS)
    copyRoads = true, copyWalls = true, copyRoutes = true, copyPins = true,
  },
  minimap = { hide = false, angle = 128 }, -- minimap button (degrees around the minimap)
  combatProbe = false,
}

-- Quiet chat (asked 2026-11-12: "suppress all AzerothGPS chat information (unless they run /azerothgps commands of
-- course)", Options > General, `quietChat`): nothing is printed but while a /agps command runs (ns.inSlash, Config.lua).
function ns.ChatQuiet()
  local st = ns.settings and ns.settings.gps
  return st and st.quietChat and not ns.inSlash and true or false
end
local function Print(...)
  if ns.ChatQuiet() then return end
  if DEFAULT_CHAT_FRAME then
    DEFAULT_CHAT_FRAME:AddMessage("|cff33ccffAzerothGPS|r " .. strjoin(" ", tostringall(...)))
  end
end
ns.Print = Print

-- True if v is one of Midnight's "secret" values (unusable in math).
local function IsSecret(v)
  return issecretvalue ~= nil and v ~= nil and issecretvalue(v) or false
end
ns.IsSecret = IsSecret

-- Key binding (Bindings.xml): shows or hides the map. Names for the game's Key Bindings.
BINDING_HEADER_AZEROTHGPS = "AzerothGPS"
BINDING_NAME_AZEROTHGPS_TOGGLE = L["Show/Hide GPS"]
-- The game blocking an action of ours (its "blocked from an action only available to the Blizzard UI"), kept for a bug
-- report with the function it named and what was going on (asked 2026-11-16: the button window's dropdowns, "caused
-- UI error again"): ns.db.forbiddenLog, the last 20, read from the WTF file after a /reload.
do
  local watch = CreateFrame("Frame")
  watch:RegisterEvent("ADDON_ACTION_FORBIDDEN")
  watch:RegisterEvent("ADDON_ACTION_BLOCKED")
  watch:SetScript("OnEvent", function(_, event, who, func)
    if who ~= addonName or not ns.db then return end
    local log = ns.db.forbiddenLog or {}
    local P, O = ns.Pad, ns.Options
    log[#log + 1] = { t = time and time() or 0, event = event, func = tostring(func),
      controllerUI = ns.GPS and ns.GPS.ControllerUI and ns.GPS.ControllerUI() or false,
      padFocus = P and P.Opt and P.Opt.focus and (P.Opt.focus.GetName and P.Opt.focus:GetName() or tostring(P.Opt.focus)) or nil,
      padBound = P and P.Opt and P.Opt.bound or false, gameMenu = P and P.Opt and P.Opt.gameMenu ~= nil or false,
      buttonWindow = O and O.padButton and O.padButton:IsShown() and O.padButton.key or nil,
      stack = debugstack and debugstack(2, 12, 0) or nil }
    while #log > 20 do table.remove(log, 1) end
    ns.db.forbiddenLog = log
  end)
end
-- The show/hide path's state, for a bug report (asked 2026-11-16: the /agps toggle macro doing nothing with the game's
-- controller UI on, "have it write after reload for you to read"): each toggle's before and after, the last
-- ns.TOGGLE_LOG_KEEP, in the saved variables (ns.db.toggleLog), read from the WTF file after a /reload.
ns.TOGGLE_LOG_KEEP = 20
function ns.ToggleState()
  local gps = ns.settings and ns.settings.gps or {}
  local G = ns.GPS
  local f = rawget(_G, "AzerothGPSFrame")
  local m = G and G.mmState or {}
  local function yn(v) return v and "yes" or "no" end
  return string.format("shown=%s minimized=%s replaceMinimap=%s square=%s expanded=%s away=%s worldMap=%s controllerUI=%s combat=%s frame=%s visible=%s alpha=%.2f strata=%s",
    yn(gps.shown), yn(gps.minimized), yn(gps.replaceMinimap), yn(m.on), yn(m.expanded),
    yn(G and G.MinimapAway and G.MinimapAway()), yn(G and G.WorldMapWanted and G.WorldMapWanted()),
    yn(G and G.ControllerUI and G.ControllerUI()), yn(ns.inCombat or (InCombatLockdown and InCombatLockdown())),
    yn(f and f:IsShown()), yn(f and f:IsVisible()), f and f:GetEffectiveAlpha() or 0, f and f:GetFrameStrata() or "-")
end
-- a toggle from `src` starting now (the slash command's, whose work ends in several places): its before kept now, its
-- after a frame later and half a second later
function ns.LogToggleStart(src)
  local entry = { t = time and time() or 0, src = src, before = ns.ToggleState() }
  if ns.db then
    local log = ns.db.toggleLog or {}
    log[#log + 1] = entry
    while #log > ns.TOGGLE_LOG_KEEP do table.remove(log, 1) end
    ns.db.toggleLog = log
  end
  if C_Timer and C_Timer.After then
    C_Timer.After(0, function() entry.after = ns.ToggleState() end)
    C_Timer.After(0.5, function() entry.later = ns.ToggleState() end)
  end
  return entry
end
-- run `fn` (the toggle from `src`), its before and after kept; the after a moment later too (a frame shown then hidden)
function ns.LogToggle(src, fn)
  local entry = { t = time and time() or 0, src = src, before = ns.ToggleState() }
  local ok, err = pcall(fn)
  entry.after = ns.ToggleState()
  if not ok then entry.err = tostring(err) end
  if ns.db then
    local log = ns.db.toggleLog or {}
    log[#log + 1] = entry
    while #log > ns.TOGGLE_LOG_KEEP do table.remove(log, 1) end
    ns.db.toggleLog = log
  end
  if C_Timer and C_Timer.After then C_Timer.After(0.5, function() entry.later = ns.ToggleState() end) end
  return entry
end
function AzerothGPS_ToggleMap()
  if not ns.settings then return end
  if not ns.inToggleLog then
    ns.inToggleLog = true
    local ok = pcall(ns.LogToggle, "key", AzerothGPS_ToggleMap)
    ns.inToggleLog = nil
    return
  end
  local gps = ns.settings.gps
  -- (issue #20: with keyBlockedInCombat the key never shows the map in combat; hiding it still works)
  if not gps.shown and gps.keyBlockedInCombat ~= false and (ns.inCombat or (InCombatLockdown and InCombatLockdown())) then
    return
  end
  -- (the map as the minimap: the key opens it out and sends it back, asked 2026-11-10; it isn't hidden there)
  local G = ns.GPS
  -- (the map in the game's world map window: the key opens and closes that)
  if G and G.WorldMapWanted and G.WorldMapWanted() then
    G.ToggleMapView() -- (in a fight: the map's own window instead)
    return
  end
  -- (the minimap replaced, in an instance: the game's minimap is back there, and the key opens and closes the map's
  -- own window for the while; GPSFrame.lua's G.MinimapAway)
  if gps.replaceMinimap == true and G and G.MinimapAway and G.MinimapAway() and G.mmState and not G.mmState.on then
    G.mmState.awayOpen = not G.mmState.awayOpen or nil
    G.ApplySettings()
    return
  end
  if gps.shown and G and G.mmState and G.mmState.on and G.SetMinimapExpanded then
    G.SetMinimapExpanded(not G.mmState.expanded)
    return
  end
  if gps.shown and gps.minimized then gps.minimized = nil -- (minimized: the key brings the map back)
  else gps.shown = not gps.shown end
  if ns.Options and ns.Options.Apply then ns.Options.Apply() end
end
-- Quick Search (asked 2026-11-14: "a key binding to open the map and select the search function so player can
-- immediately start typing", "call it quick search"): GPSFrame's G.QuickSearch
BINDING_NAME_AZEROTHGPS_SEARCH = L["Quick Search"]
-- (the Target button's key, 1.3.14: Bindings.xml's CLICK binding, GPSFrame's G.MakeTargetButton)
_G["BINDING_NAME_CLICK AzerothGPSTargetButton:LeftButton"] = L["Target the NPC stop"]
function AzerothGPS_QuickSearch()
  if not ns.settings then return end
  if ns.GPS and ns.GPS.QuickSearch then return ns.GPS.QuickSearch() end
end

-- Timing of the addon's work (redraw and its parts, routing, layers), for /agps debug perf:
-- ns.perf[name] = { last, max, n, slow, total } in milliseconds, since ns.perfSince.
-- Names with ": " are parts of the one before (e.g. "redraw: tiles" is inside "redraw").
ns.perf = {}
ns.perfSince = GetTime and GetTime() or 0
function ns.PerfStart() return debugprofilestop and debugprofilestop() end
-- The timings that don't overlap (the others are parts of these): their sum is all the addon's work
-- (Options > Performance shows it as a share of the time).
ns.PERF_TOP = { "redraw", "arrow window", "every frame: fade, tooltip", "terrain search", "quest area tracing",
  "minimap route", "minimap icons", "map text" }
-- (the top timings' running sum, for a timing with others inside: ns.Timed counts only its own part)
ns.perfTopSum, ns.perfTopSet = 0, {}
for _, k in ipairs(ns.PERF_TOP) do ns.perfTopSet[k] = true end
-- A script handler (OnUpdate, OnEvent) timed under `name`, a top timing of its own (added to PERF_TOP): the event
-- handlers and the frames' other OnUpdates, so the Performance page counts what the client's addon CPU list does
-- (issue #191). A top timing run inside it (a redraw from an event) isn't counted twice.
function ns.Timed(name, fn)
  if not ns.perfTopSet[name] then
    ns.perfTopSet[name] = true
    ns.PERF_TOP[#ns.PERF_TOP + 1] = name
  end
  return function(...)
    local t0, inner = ns.PerfStart(), ns.perfTopSum
    fn(...)
    if t0 then ns.PerfAdd(name, math.max(0, debugprofilestop() - t0 - (ns.perfTopSum - inner))) end
  end
end
-- A frame's script as set, timed from now on (ns.Timed).
function ns.TimeScript(f, script, name)
  local fn = f and f.GetScript and f:GetScript(script)
  if fn then f:SetScript(script, ns.Timed(name, fn)) end
end
function ns.PerfTotal()
  local sum = 0
  for _, k in ipairs(ns.PERF_TOP) do
    local p = ns.perf[k]
    if p then sum = sum + p.total end
  end
  return sum
end
function ns.PerfEnd(name, t0)
  if not t0 then return end
  ns.PerfAdd(name, debugprofilestop() - t0)
end
-- One run of `name` that took `ms` (a run timed in pieces: their sum).
function ns.PerfAdd(name, ms)
  local p = ns.perf[name]
  if not p then
    p = { last = 0, max = 0, n = 0, slow = 0, total = 0 }
    ns.perf[name] = p
  end
  p.last, p.max, p.n, p.total = ms, math.max(p.max, ms), p.n + 1, p.total + ms
  if ms > 16 then p.slow = p.slow + 1 end -- longer than a 60 fps frame
  if ns.perfTopSet[name] then ns.perfTopSum = ns.perfTopSum + ms end
end
-- The report since the last one (then starts over): chat lines, and a snapshot saved in
-- AzerothGPSDB.perf (written to disk on /reload or logout; read with `agps perf`).
function ns.PerfReport()
  local now = GetTime()
  local span = math.max(0.001, now - (ns.perfSince or now))
  local names = {}
  for k in pairs(ns.perf) do names[#names + 1] = k end
  table.sort(names)
  local out, rows = {}, {}
  out[1] = string.format("over %.0f s (10 ms/s = 1%% of a CPU core):", span)
  for _, k in ipairs(names) do
    local p = ns.perf[k]
    out[#out + 1] = string.format("%s: %.2f ms/s, avg %.2f ms, max %.1f ms, %.1f runs/s, %d over 16 ms",
      k, p.total / span, p.total / p.n, p.max, p.n / span, p.slow)
    rows[#rows + 1] = { name = k, total = p.total, n = p.n, max = p.max, slow = p.slow }
  end
  if ns.db and #rows > 0 then
    ns.db.perf = ns.db.perf or {}
    local snaps = ns.db.perf
    local st = ns.settings and ns.settings.gps or {}
    snaps[#snaps + 1] = {
      time = time(), span = span, rows = rows, fps = GetFramerate and GetFramerate() or 0,
      version = C_AddOns and C_AddOns.GetAddOnMetadata and C_AddOns.GetAddOnMetadata(addonName, "Version") or nil,
      settings = { hz = st.hz, style = st.style, rotate = st.rotate, size = st.size,
        quests = st.layerQuests, questAreas = st.layerQuestAreas, herbs = st.layerHerbs, ore = st.layerOre,
        roads = st.showRoads, fade = st.fadeMoving, stops = ns.Nav and #ns.Nav.stops or 0 },
    }
    while #snaps > 10 do table.remove(snaps, 1) end
    out[#out + 1] = "saved: /reload, then run `agps perf` on your PC"
  end
  ns.perf, ns.perfSince = {}, now
  return #rows > 0 and out or { "nothing measured yet" }
end

-- (Never pass a filter mode above "LINEAR" to SetTexture or SetAtlas: client 1.60.1.70124 asserts
-- `flags.m_filter <= GxTex_Linear` and crashes; "TRILINEAR" did, 2026-10-01. wowmock.lua refuses it.)

-- Set a texture from a file path/ID, or from a UI atlas written "atlas:<name>" (falling back
-- to `fallback` if the client doesn't know the atlas).
function ns.SetIcon(tex, icon, fallback)
  local atlas = type(icon) == "string" and icon:match("^atlas:(.+)$")
  -- (what it shows, for GPSFrame's G.ScaledIcon: the same drawn at its size on the screen; asked 2026-11-16)
  tex.agpsSrc, tex.scaledFile = icon, nil
  if atlas then
    if tex.SetAtlas and C_Texture and C_Texture.GetAtlasInfo and C_Texture.GetAtlasInfo(atlas) then
      tex:SetAtlas(atlas)
      return
    end
    icon = fallback
    tex.agpsSrc = icon
  end
  tex:SetTexCoord(0, 1, 0, 1) -- undo a previous atlas's coordinates
  tex:SetTexture(icon)
end

-- The character's name, or nil while the game hasn't given it yet: right after logging in (a new
-- character's first login above all) UnitName says "Unknown", and everything was saved under
-- "<realm>-Unknown" (seen 2026-10-01 in testing: flight paths and faction filed there).
-- With a surname (WoW Forever's, UnitName's second value: "Ann", "Smith") the whole name: characters may share a
-- first name, and three characters of one first name shared one record, their stops, flight paths and hearthstone home (2026-11-05).
local function PlayerName()
  if not UnitName then return nil end
  local n, surname = UnitName("player")
  if not n or n == "" or n == "Unknown" or n == UNKNOWNOBJECT then return nil end
  if type(surname) == "string" and surname ~= "" then return n .. " " .. surname end
  return n
end
ns.PlayerName = PlayerName

-- A unit's whole name as whispers need it, or nil. On WoW Forever UnitName's second value is the surname, not a realm
-- (issue #854: a party member asked for their route was whispered by the first name alone, "No player named ... is
-- currently playing"): "First Surname" by the game's own separator (its UI's NameUtil does the same); else "Name-Realm".
-- Surnames where the game says so (RegionalUniqueNamesEnabled), or, without that call, where the player's own name has one.
function ns.UnitFullName(unit)
  if not UnitName then return nil end
  local n, second = UnitName(unit)
  if not n or ns.IsSecret(n) or n == "" then return nil end
  if ns.IsSecret(second) or type(second) ~= "string" or second == "" then return n end
  local surnames
  if RegionalUniqueNamesEnabled then
    surnames = RegionalUniqueNamesEnabled() and true or false
  else
    local _, own = UnitName("player")
    surnames = type(own) == "string" and own ~= ""
  end
  if surnames then
    local c = Constants and Constants.CharacterNameSeparatorConsts
    return n .. (c and c.CHARACTERNAME_SURNAME_SEPARATOR or " ") .. second
  end
  return n .. "-" .. second
end

-- The realm's name. The client sometimes gives an empty one (players' reports, 2026-11-21: "AzerothGPS forgot all my
-- flight paths since the update"; Kooki3z's own saved file had a second record "-<name>", no realm, its flights
-- unknown, beside "<realm>-<name>"). Then: the realm of this character's own record (by
-- the game's normalized realm name where several realms have one of that name), else the last realm the client named.
function ns.RealmName()
  local db = AzerothGPSDB
  local r = GetRealmName and GetRealmName()
  if type(r) == "string" and r ~= "" then
    if db then db.lastRealm = r end
    return r
  end
  local name = PlayerName()
  if db and type(db.chars) == "table" and name then
    local norm
    if GetNormalizedRealmName then
      local ok, v = pcall(GetNormalizedRealmName)
      if ok and type(v) == "string" and v ~= "" then norm = v end
    end
    if not norm and UnitFullName then
      local ok, _, v = pcall(UnitFullName, "player")
      if ok and type(v) == "string" and v ~= "" then norm = v end
    end
    local tail, found, many = "-" .. name, nil, false
    for k in pairs(db.chars) do
      if type(k) == "string" and #k > #tail and k:sub(-#tail) == tail then
        local realm = k:sub(1, #k - #tail)
        if realm ~= "?" then
          if norm and realm:gsub("[%s%-']", "") == norm:gsub("[%s%-']", "") then return realm end
          if found and found ~= realm then many = true end
          found = found or realm
        end
      end
    end
    if found and not many then return found end
  end
  return db and db.lastRealm or nil
end

function ns.CharKey()
  return (ns.RealmName() or "?") .. "-" .. (PlayerName() or "Unknown")
end

-- When a character's record was last used: its flight paths' latest read (each login reads them), 0 with none.
local function LastUsed(rec)
  local t = 0
  for _, entry in pairs(type(rec.taxiNodes) == "table" and rec.taxiNodes or {}) do
    if type(entry) == "table" and type(entry.time) == "number" and entry.time > t then t = entry.time end
  end
  return t
end

-- A record saved under no realm ("-<name>", the client's empty realm name before 1.3.13) taken into the character's
-- own (Kooki3z 2026-11-21: what was learned since the issue started comes back too). The one used last wins where
-- both have a value (a hearthstone set since, the route), the other fills in what it lacks, and every flight path
-- either knew stays known (one learned while saved under no realm too). The boats' and zeppelins' times learned
-- meanwhile (`transports[""]`) go to the realm's. The no-realm record goes once taken in.
function ns.TakeNoRealmRecord(db, key)
  local name = PlayerName()
  local stray = name and db.chars["-" .. name]
  if type(stray) ~= "table" or key == "-" .. name then return false end
  local own = db.chars[key]
  local knew = {}
  for _, rec in ipairs({ own or {}, stray }) do
    for _, entry in pairs(type(rec.taxiNodes) == "table" and rec.taxiNodes or {}) do
      for _, n in ipairs(type(entry) == "table" and entry.nodes or {}) do
        if type(n) == "table" and n.known and n.nodeID then knew[n.nodeID] = true end
      end
    end
  end
  local merged
  if type(own) ~= "table" then
    merged = stray
  elseif LastUsed(stray) > LastUsed(own) then
    merged = ns.MergeInto(stray, own)
  else
    merged = ns.MergeInto(own, stray)
  end
  for _, entry in pairs(type(merged.taxiNodes) == "table" and merged.taxiNodes or {}) do
    for _, n in ipairs(type(entry) == "table" and entry.nodes or {}) do
      if type(n) == "table" and n.nodeID and knew[n.nodeID] then n.known = true end
    end
  end
  db.chars[key] = merged
  db.chars["-" .. name] = nil
  if db.lastChar == "-" .. name then db.lastChar = key end
  local realm = key:sub(1, #key - #name - 1)
  if type(db.transports) == "table" and type(db.transports[""]) == "table" and realm ~= "" and realm ~= "?" then
    db.transports[realm] = ns.MergeInto(db.transports[realm] or {}, db.transports[""])
    db.transports[""] = nil
  end
  return true
end

-- A character with a surname and no record of its own yet: a copy of the record its first name had (until 1.1.11 a
-- character was saved by its first name alone, so every character of that name used it). That record stays as it was
-- (keep data forever) for the others of that name.
function ns.TakeFirstNameRecord(db, key)
  local first = UnitName("player")
  local old = PlayerName() ~= first and db.chars[(ns.RealmName() or "?") .. "-" .. first]
  if type(old) ~= "table" then return false end
  db.chars[key] = CopyTable(old)
  old.copiedTo = old.copiedTo or {}
  old.copiedTo[key] = time and time() or true
  db.chars[key].copiedTo = nil
  return true
end

-- This character's saved table. Until the name is known, a stand-in for this session ("<realm>-Unknown");
-- once it is, what was put there meanwhile moves into the character's own (anything it hasn't got yet).
local pendingKey
function ns.CharDB()
  local db = AzerothGPSDB
  local key = ns.CharKey()
  if PlayerName() then
    if ns.RealmName() then ns.TakeNoRealmRecord(db, key) end
    if db.chars[key] == nil then ns.TakeFirstNameRecord(db, key) end
    if pendingKey and pendingKey ~= key then
      local tmp = db.chars[pendingKey]
      db.chars[pendingKey] = nil
      local own = db.chars[key] or {}
      ns.MergeInto(own, tmp) -- (entry by entry: a flight time learned meanwhile isn't lost, keep data forever)
      db.chars[key] = own
      if db.lastChar == pendingKey then db.lastChar = key end
    end
    pendingKey = nil
  elseif not pendingKey then
    pendingKey = key
    db.chars[key] = nil -- (a stand-in left by an earlier session: whose it was can't be told)
  end
  db.chars[key] = db.chars[key] or { taxiNodes = {}, flights = {} }
  return db.chars[key]
end

-- What `from` has that `into` hasn't, entry by entry (into sub-tables both have); `into`'s own values stay.
function ns.MergeInto(into, from)
  for k, v in pairs(from or {}) do
    local mine = into[k]
    if mine == nil then
      into[k] = v
    elseif type(v) == "table" and type(mine) == "table" then
      ns.MergeInto(mine, v)
    end
  end
  return into
end

-- Saved packed (asked 2026-10-06, keep data forever): the points of a drawn road and of a faster trip's trace go into
-- the saved file as one string each (`pk`, and `zk` for a road's heights), not two values a point: WoW's Lua loads a
-- saved file of at most 262,143 distinct values, and every stroke is kept for good. Packed at logout and /reload
-- (PLAYER_LOGOUT), unpacked at load (InitDB): in the game they're lists as ever. A list may hold false (none).
function ns.PackNumbers(list)
  local out = {}
  for i, v in ipairs(list) do out[i] = v == false and "-" or tostring(v) end
  return table.concat(out, " ")
end
function ns.UnpackNumbers(s)
  local out = {}
  for w in tostring(s):gmatch("%S+") do
    if w == "-" then out[#out + 1] = false else out[#out + 1] = tonumber(w) or false end
  end
  return out
end
local function PackedLists(db)
  return { db.tracks, db.feedback and db.feedback.trips, db.feedback and db.feedback.roads }
end
function ns.PackSaved(db)
  for _, list in ipairs(PackedLists(db or {})) do
    for _, t in ipairs(list) do
      if type(t) == "table" then
        if type(t.pts) == "table" then t.pk, t.pts = ns.PackNumbers(t.pts), nil end
        if type(t.zs) == "table" then t.zk, t.zs = ns.PackNumbers(t.zs), nil end
        if type(t.gz) == "table" then t.gk, t.gz = ns.PackNumbers(t.gz), nil end -- (a drawn road's ground heights)
      end
    end
  end
end
function ns.UnpackSaved(db)
  for _, list in ipairs(PackedLists(db or {})) do
    for _, t in ipairs(list) do
      if type(t) == "table" then
        if type(t.pk) == "string" then t.pts, t.pk = ns.UnpackNumbers(t.pk), nil end
        if type(t.zk) == "string" then t.zs, t.zk = ns.UnpackNumbers(t.zk), nil end
        if type(t.gk) == "string" then t.gz, t.gk = ns.UnpackNumbers(t.gk), nil end
      end
    end
  end
end

-- The saved file's limit (asked 2026-10-06, keep data forever): WoW's Lua loads a saved file of at most 262,143
-- distinct values (strings and numbers, keys too), and all of AzerothGPS's saved variables are one file. Counted as
-- it will be saved (a road's or a trace's points one string, ns.PackSaved). Nothing is ever deleted for it: notices at
-- SAVED_NOTICES (ns.SavedNotice, at login), and an import past SAVED_IMPORT_SHARE is refused (Import.ImportText).
ns.SAVED_LIMIT = 262143
ns.SAVED_NOTICES = { 0.25, 0.5, 0.8 }
ns.SAVED_IMPORT_SHARE = 0.6
local PACKED_UNDER = { tracks = true, trips = true, roads = true, tracksShipped = true }
function ns.SavedValues(...)
  local seen, n, visited = {}, 0, {}
  local function add(v)
    local t = type(v)
    if (t == "string" or (t == "number" and v == v)) and not seen[v] then
      seen[v] = true
      n = n + 1
    end
  end
  local function walk(t, packed)
    if visited[t] then return end
    visited[t] = true
    for k, v in pairs(t) do
      add(k)
      if type(v) ~= "table" then
        add(v)
      elseif packed and (k == "pts" or k == "zs") then
        n = n + 1 -- (one string when saved)
      else
        walk(v, packed or PACKED_UNDER[k] == true)
      end
    end
  end
  for i = 1, select("#", ...) do
    local t = select(i, ...)
    if type(t) == "table" then walk(t, false) end
  end
  return n
end
-- At login: how full the saved file is, said from SAVED_NOTICES' first share up (never deleting anything). The share.
function ns.SavedNotice()
  local share = ns.SavedValues(AzerothGPSDB) / ns.SAVED_LIMIT
  ns.savedShare = share
  if share < ns.SAVED_NOTICES[1] then return share end
  local pct = math.floor(share * 100 + 0.5)
  local high = share >= ns.SAVED_NOTICES[#ns.SAVED_NOTICES]
  if high then
    ns.Print(string.format(L["|cffff6060your saved data is %d%% of what WoW can load in one file.|r Nothing is ever deleted for it; past 100%% WoW couldn't load it at all, so imports stop at %d%%."],
      pct, math.floor(ns.SAVED_IMPORT_SHARE * 100 + 0.5)))
  else
    ns.Print(string.format(L["|cffffd100your saved data is %d%% of what WoW can load in one file.|r Nothing is ever deleted for it; this is only to let you know."], pct))
  end
  return share
end

-- Copy missing defaults into t (recursing into sub-tables).
local function Merge(t, defaults)
  for k, v in pairs(defaults) do
    if t[k] == nil then
      t[k] = type(v) == "table" and CopyTable(v) or v
    elseif type(v) == "table" and type(t[k]) == "table" and k ~= "point" and k ~= "arrowPoint" and k ~= "arrowSize" then
      Merge(t[k], v)
    end
  end
end

-- (1.3.9: the arrow and the directions text one lock before, `arrowLocked`; the text's own, `dirLocked`, starts as it
-- was, once: for db.settings at load and each profile when it's used)
function ns.SplitDirLock(gps)
  if type(gps) == "table" and gps.dirLocked == nil then gps.dirLocked = gps.arrowLocked == true end
  -- (the arrow and the directions text each on or off on their own, Kooki3z 2026-11-24: "Show direction arrow" was both
  -- panels, the arrow alone hidden by Arrow side "Hide". Once, nobody's look changed: the window off, both off; "Hide",
  -- the arrow off and its side back to the left; `arrow` from then on either panel on)
  -- (item 28, Kooki3z 2026-11-24: "Allow big drops at full health" removed, the Safe drop slider the one limit)
  if type(gps) == "table" then gps.bigDropsFullHealth = nil end
  if type(gps) == "table" and not gps.arrowSplit then
    if gps.arrow == false then
      gps.arrowShown, gps.dirShown = false, false
    else
      gps.arrowShown = not (gps.arrowSide == "hide" and gps.dirShown ~= false)
    end
    if gps.arrowSide == "hide" then gps.arrowSide = "left" end
    gps.arrow = gps.arrowShown ~= false or gps.dirShown ~= false
    gps.arrowSplit = true
  end
end

-- A profile's gps settings: the Quests button's place (its group's, "questsG", else its first button's from before
-- groups) and its spot in the order (quickOrder) given to Map Layers ("mapLayers"), unless Map Layers has its own.
function ns.QuestsToLayers(gps)
  if type(gps) ~= "table" then return end
  local q = gps.quick
  if type(q) == "table" and q.mapLayers == nil then
    q.mapLayers = q.questsG or q.quests
  end
  local order = gps.quickOrder
  if type(order) == "table" then
    local has = false
    for _, id in ipairs(order) do has = has or id == "mapLayers" end
    for i, id in ipairs(order) do
      if id == "questsG" and not has then order[i] = "mapLayers" end
    end
  end
end

local function InitDB()
  local fresh = AzerothGPSDB == nil -- (no saved data before this session: a first install, for the setup and the tips)
  AzerothGPSDB = AzerothGPSDB or {}
  local db = AzerothGPSDB
  db.version = 2
  db.settings = db.settings or {}
  -- an early build's single "hide in combat" and fixed 100% combat map opacity
  local gps = db.settings.gps
  if gps and gps.combatHide ~= nil then
    gps.combatHideMap, gps.combatHideArrow, gps.combatHide = gps.combatHide, gps.combatHide, nil
    if gps.combatAlpha == 1 then gps.combatAlpha = nil end
  end
  ns.SplitDirLock(gps)
  -- (the grid system always on: item 74, Kooki3z 2026-11-25, its options removed. Anyone who turned Cities or World off
  -- gets them back on; the settings stay for tests and debug, switched by code only. AGPS_TEST_KEEP_GRIDS: the test
  -- harness's, which runs with world routing off unless a test turns it on, a reload included)
  if gps and not _G.AGPS_TEST_KEEP_GRIDS then
    gps.cityGrid, gps.worldGrid = true, true
    gps.cityGridDefaultOn, gps.worldGridDefaultOn = nil, nil
  end
  if gps and gps.frameAlways ~= nil then gps.frameAlways = nil end -- replaced by windowFrame
  if gps and gps.roundLogo ~= nil then gps.roundLogo = nil end -- (the round portrait option: removed, 2026-10-01)
  -- (Share drawn roads and walls, Share faster trips: removed, 2026-10-01; drawn roads are kept anyway,
  -- faster trips always, and Copy Map Data's checkboxes say what's shared)
  if gps then gps.shareRoads, gps.shareTrips = nil, nil end
  if gps then gps.layerAvailable, gps.layerLowLevel = nil, nil end -- quests to pick up: removed
  if gps and gps.hz == 30 then gps.hz = nil end -- the old default: now 20 (less CPU)
  if gps and gps.layerNodes ~= nil then -- split into Herbs and Ore
    gps.layerHerbs, gps.layerOre, gps.layerNodes = gps.layerNodes, gps.layerNodes, nil
  end
  -- (the offroad option, gone in 1.0.8: the roads are joined where they're heading instead)
  if gps then gps.offroad = nil end
  -- (the road and wall tools' two options: one, Map Editing, 2026-11-14)
  if gps and gps.wallTools ~= nil then
    if gps.wallTools then gps.devTools = true end
    gps.wallTools = nil
  end
  db.offroadOff108, db.offroadNote = nil, nil
  -- (1.1.1: resizing from the corner on by default, asked 2026-10-03. 1.1.0 saved "Lock map size" on for everyone,
  -- its default then: put back to the new default once)
  if gps and not db.resizeDefault111 then gps.lockSize = nil end
  db.resizeDefault111 = true
  -- (1.1.2: zeppelins' and boats' departures seen before were mostly a ride's arrival taken for its departure at the
  -- far dock (Taxi.TransportTick): no timer until the next ride rather than a wrong one, once)
  if not db.transports112 then db.transports = nil end
  db.transports112 = true
  -- (1.1.4: the direction window wider by default, asked 2026-10-04: a window still at the old default size gets the
  -- new one, once; a size the player chose stays)
  local as = gps and gps.arrowSize
  if not db.arrowWidth114 and type(as) == "table" and as[1] == 289 and as[2] == 97 then gps.arrowSize = { 370, 97 } end
  db.arrowWidth114 = true
  -- (1.1.8: the map's icons on the minimap off by default, issue #31. 1.1.7 saved them on for everyone, its default
  -- then: put back to the new default once; a choice made since stays)
  if gps and not db.minimapIconsDefault118 and gps.minimapIcons == true then gps.minimapIcons = nil end
  db.minimapIconsDefault118 = true
  db.hoverLog = nil -- (a 2026-11-13 test build's herb and ore log: the debug log's now, ns.Debug, never saved)
  -- (1.2.0's minimap square, three sizes since 2026-11-09: the small one gone, the others a step down in name. A saved
  -- one moved by its size once, so no square changes size: small (150) and medium (200) to small (200), large (260) to
  -- medium, extra large (320) to large)
  if gps and not db.minimapSizes3 and gps.replaceMinimapSize ~= nil then
    gps.replaceMinimapSize = ({ small = "small", medium = "small", large = "medium", xlarge = "large" })[gps.replaceMinimapSize]
      or "small"
  end
  db.minimapSizes3 = true
  -- (issue #60: the seamless map is the default for everyone. Earlier builds saved it off, their default then: put back
  -- to the new default once; the option stays the off switch. The Atlas window and its view switch are gone: their
  -- settings let go)
  if gps and not db.seamlessDefault60 and gps.seamlessZoom == false then gps.seamlessZoom = nil end
  db.seamlessDefault60 = true
  -- (Shift-click drawing always since 2026-11-19, its option gone: a stored value let go, never read)
  if gps then gps.toolShiftClick = nil end
  db.shiftClickDefault129 = nil
  -- (the keys kept from showing the map in combat, on by default, asked 2026-11-14: the old default's stored "off", once)
  if gps and not db.keyCombatDefault129 and gps.keyBlockedInCombat == false then gps.keyBlockedInCombat = nil end
  db.keyCombatDefault129 = true
  -- (issue #75: the seamless map is a map style of its own, the default, in place of its on/off option. The terrain
  -- style saved can't be told from the old default, so it's the seamless map now, but where the seamless map was turned
  -- off: Terrain stays; the World Map and No Spoiler Map stay)
  if gps and not db.mapStyles75 then
    local was = gps.style
    if gps.seamlessZoom == false and (was == nil or was == "minimap") then
      gps.style = "minimap"
    elseif was == "minimap" then
      gps.style = "seamless"
    end
  end
  if gps then gps.seamlessZoom = nil end
  db.mapStyles75 = true
  if gps then gps.atlas, gps.atlasView = nil, nil end
  if gps then gps.seamWorldYd = nil end -- (2026-11-14: the first world slider's, only the icons' stage; seamWorldAt)
  for _, c in pairs(db.chars or {}) do
    if type(c) == "table" and c.mapWindow == "atlas" then c.mapWindow = nil end
  end
  -- (importKeepOrder on by default, asked for 1.3.9 after a test build had it off: on once for every profile, then the
  -- player's own choice; `importOrderOn`)
  if not db.importOrderOn then
    db.importOrderOn = true
    if gps then gps.importKeepOrder = true end
    for _, t in pairs(type(db.profiles) == "table" and db.profiles or {}) do
      if type(t) == "table" and type(t.gps) == "table" then t.gps.importKeepOrder = true end
    end
  end
  -- (1.4.0: Road tolerance +3 by default, was 0: a saved 0, the old default, moved to the new one once, in every profile;
  -- another value the player chose stays)
  if not db.roadTolerance140 then
    db.roadTolerance140 = true
    if gps and (gps.roadTolerance == 0 or gps.roadTolerance == nil) then gps.roadTolerance = ns.DEFAULTS.gps.roadTolerance end
    for _, t in pairs(type(db.profiles) == "table" and db.profiles or {}) do
      if type(t) == "table" and type(t.gps) == "table" and (t.gps.roadTolerance == 0 or t.gps.roadTolerance == nil) then
        t.gps.roadTolerance = ns.DEFAULTS.gps.roadTolerance
      end
    end
  end
  -- (1.4.2: the docks were shown with Points of interest; their own setting since (Map Layers). Points of interest
  -- turned off kept them hidden: the docks off too, once, in every profile)
  if not db.docks142 then
    db.docks142 = true
    if gps and gps.poiPoi == false and gps.layerDocks == nil then gps.layerDocks = false end
    for _, t in pairs(type(db.profiles) == "table" and db.profiles or {}) do
      if type(t) == "table" and type(t.gps) == "table" and t.gps.poiPoi == false and t.gps.layerDocks == nil then
        t.gps.layerDocks = false
      end
    end
  end
  -- (1.4.2: the map menu's Quests button gone, Map Layers in its place, Kooki3z 2026-11-27: where a player put the
  -- Quests button (or hid it), and its place in their order, Map Layers takes once, in every profile; the quest layers'
  -- own settings as they were)
  if not db.questsToLayers142 then
    db.questsToLayers142 = true
    ns.QuestsToLayers(gps)
    for _, t in pairs(type(db.profiles) == "table" and db.profiles or {}) do
      if type(t) == "table" then ns.QuestsToLayers(t.gps) end
    end
  end
  Merge(db.settings, ns.DEFAULTS)
  db.chars = db.chars or {}
  -- (stand-ins saved before the character's name was known, by older versions: whose can't be told, so not anyone's;
  -- kept for good in `unclaimed`, keep data forever)
  for key, t in pairs(db.chars) do
    if type(key) == "string" and key:find("%-Unknown$") then
      db.unclaimed = db.unclaimed or {}
      db.unclaimed[#db.unclaimed + 1] = { key = key, data = t }
      db.chars[key] = nil
    end
  end
  db.probes = db.probes or {}
  -- (the tutorial's record, account-wide, 1.2.0: Tutorial.lua. `seen`: the sections played through, each with the
  -- version it was added in. The old offer's `ask`, `declined`, `offered`, `askedFor` and `fresh` may still be in
  -- saved data from before 1.4.0: nothing reads them, the tutorial is only on request since)
  if type(db.tutorial) ~= "table" then db.tutorial = {} end
  if type(db.tutorial.seen) ~= "table" then db.tutorial.seen = {} end
  -- (1.3.10, Setup.lua: the setup, a first install's only since 1.4.0 (`setup.fresh`, set as the table is made with no
  -- saved data at all; `setup.shown` under Setup's S.VERSION; `done` from a test build counts as shown), its live
  -- preview put back if the game was left with it open; the first route's tips a first install's only too: a player
  -- updating gets the tables without `fresh` and `due` and never sees either)
  if type(db.setup) ~= "table" then db.setup = { fresh = fresh or nil } end
  db.setup.due = nil
  if db.setup.done and not db.setup.shown then db.setup.shown = 1 end
  if ns.Setup and ns.Setup.RestoreSaved then pcall(ns.Setup.RestoreSaved, db) end
  if type(db.tips) ~= "table" then db.tips = { due = fresh or nil } end
  ns.UnpackSaved(db) -- (the points saved packed: lists again)
  ns.db = db
  ns.settings = db.settings
end

-- Profiles (1.2.2, asked 2026-11-11: "save/load profiles that are character specific and/or account wide ... for all
-- option settings"; picked: each character chooses its own). A profile is a whole set of options, everything in
-- `settings`. "Default" is db.settings itself: what every character used before, and uses until another is picked for
-- it. The others are kept for the account in db.profiles by name, and a character's pick in its own record
-- (`profile`). The options are always read through ns.settings, which is the picked profile's table, so a change is
-- saved into that profile as it's made.
-- (a setting renamed or moved by a later version: InitDB's fix-ups above are for db.settings; the same is owed to
-- each of db.profiles.)
-- The profile this character uses, by name; nil: Default.
function ns.ProfileName()
  local db = ns.db
  if not db then return nil end
  local name = ns.CharDB().profile
  if type(name) == "string" and type(db.profiles) == "table" and type(db.profiles[name]) == "table" then return name end
  return nil
end
-- The profiles made so far, by name (Default isn't one of them).
function ns.ProfileNames()
  local list = {}
  for name, t in pairs(ns.db and ns.db.profiles or {}) do
    if type(name) == "string" and type(t) == "table" then list[#list + 1] = name end
  end
  table.sort(list, function(a, b) return a:lower() < b:lower() end)
  return list
end
-- This character on the profile `name` (nil: Default) from now on. False when there's none of that name.
function ns.UseProfile(name)
  local db = ns.db
  local t = name and type(db.profiles) == "table" and db.profiles[name] or nil
  if name and type(t) ~= "table" then return false end
  if t and t.gps and t.gps.wallTools ~= nil then -- (the road and wall tools' two options: one, 2026-11-14)
    if t.gps.wallTools then t.gps.devTools = true end
    t.gps.wallTools = nil
  end
  if t and type(t.gps) == "table" then t.gps.seamWorldYd = nil end -- (the first world slider's: InitDB's)
  if t then ns.SplitDirLock(t.gps) end
  if t then Merge(t, ns.DEFAULTS) end -- (options added since it was last used)
  ns.settings = t or db.settings
  ns.CharDB().profile = t and name or nil
  return true
end
-- A new profile named `name`: a copy of the options as they are now, and this character on it. False when the name
-- is taken (or empty).
function ns.NewProfile(name)
  local db = ns.db
  if type(name) ~= "string" or name == "" then return false end
  db.profiles = type(db.profiles) == "table" and db.profiles or {}
  if db.profiles[name] ~= nil then return false end
  db.profiles[name] = CopyTable(ns.settings)
  return ns.UseProfile(name)
end
-- Every option of the profile `from` (nil: Default) copied into the one in use. False when that's the same one.
function ns.CopyProfile(from)
  local db = ns.db
  local src
  if from == nil then src = db.settings else src = type(db.profiles) == "table" and db.profiles[from] or nil end
  local cur = ns.settings
  if type(src) ~= "table" or src == cur then return false end
  for k in pairs(cur) do cur[k] = nil end
  for k, v in pairs(src) do cur[k] = type(v) == "table" and CopyTable(v) or v end
  ns.SplitDirLock(cur.gps)
  Merge(cur, ns.DEFAULTS)
  return true
end
-- The profile `name` gone (the player's own doing, asked first in the options). This character, on it, goes to
-- Default now; the others on it at their next login (ns.StartProfile).
function ns.DeleteProfile(name)
  local db = ns.db
  if not (name and type(db.profiles) == "table" and db.profiles[name]) then return false end
  if ns.settings == db.profiles[name] then ns.UseProfile(nil) end
  db.profiles[name] = nil
  return true
end
-- At login, before anything reads the options: the character's own pick (one deleted since: Default).
function ns.StartProfile()
  local c = ns.CharDB()
  local name = ns.ProfileName()
  if c.profile ~= nil and not name then c.profile = nil end
  if name then ns.UseProfile(name) end
end

-- Describe a value for the probe log, including secret-ness.
local function Describe(v)
  if IsSecret(v) then return "<secret>" end
  if v == nil then return "nil" end
  if type(v) == "number" then return string.format("%.6g", v) end
  return tostring(v)
end

-- API probe: prints to chat and appends to AzerothGPSDB.probes (read with `agps probes`).
-- A boss seen dead (`unit`: the target, focus, mouseover, a nameplate): its kill counted, in the dungeon the
-- player is in. The encounter events and the combat log can't be counted on: a server sent no
-- encounter events and the combat log's kill never came through (2026-10-01: Oggleflint dead at the
-- player's feet, targeted, and "Next: Oggleflint" stayed). By NPC entry, or name (Forever's own dungeons).
function ns.CheckDeadUnit(unit)
  local N = ns.Nav
  if not (N and N.CurrentInstance and UnitExists and UnitIsDead and UnitGUID) then return 0 end
  local lvl = N.CurrentInstance()
  if not lvl then return 0 end
  local okE, exists = pcall(UnitExists, unit)
  local okD, dead = pcall(UnitIsDead, unit)
  if not (okE and okD) or ns.IsSecret(exists) or ns.IsSecret(dead) or not (exists and dead) then return 0 end
  local okG, guid = pcall(UnitGUID, unit)
  local okN, name = pcall(UnitName, unit)
  local gs, nsec = not okG or ns.IsSecret(guid), not okN or ns.IsSecret(name)
  local npc = not gs and N.NpcOf(guid) or nil
  local n = (npc or not nsec) and N.BossKilled(lvl, npc, nil, not nsec and name or nil) or 0
  -- (what the game gave, the last 20, saved: /reload, then the saved file says why a kill didn't count)
  local log = ns.db and ns.db.killLog
  if ns.db and not log then log = {} ns.db.killLog = log end
  if log then
    local what = string.format("%s in %s: guid %s, name %s -> %d", unit, tostring(lvl),
      gs and "hidden" or tostring(npc), nsec and "hidden" or tostring(name), n)
    if what ~= ns.lastKillCheck then -- (not the same again: moving the mouse over a corpse)
      ns.lastKillCheck = what
      log[#log + 1] = (date and date("%H:%M:%S") or "?") .. " " .. what
      while #log > 20 do table.remove(log, 1) end
    end
  end
  if gs and nsec and not ns.killHint then -- (once a session: how to mark it by hand)
    ns.killHint = true
    if ns.Print then ns.Print(L["the game hides who died here, so a boss's kill may not count by itself: right-click it on the dungeon's map to mark it defeated."]) end
  end
  if n > 0 and ns.GPS and ns.GPS.Redraw then ns.GPS.Redraw() end
  return n
end

-- Boss kills, for 1.0.7's instance routes: which of these events this client fires, and
-- with what (ns.db.encounterLog, the last 20; shown by /agps debug).
do
  local f = CreateFrame and CreateFrame("Frame")
  if f then
    for _, ev in ipairs({ "ENCOUNTER_START", "ENCOUNTER_END", "BOSS_KILL", "PLAYER_ENTERING_WORLD" }) do
      pcall(f.RegisterEvent, f, ev)
    end
    -- (a dead boss looked at: targeted, moused over, looted, or still targeted when combat ends)
    local seen = CreateFrame("Frame")
    -- (and NPCs' names in the game's language, ns.LearnNpcName: targeted, under the mouse, a window opened)
    for _, ev in ipairs({ "PLAYER_TARGET_CHANGED", "UPDATE_MOUSEOVER_UNIT", "PLAYER_REGEN_ENABLED", "LOOT_OPENED",
      "GOSSIP_SHOW", "MERCHANT_SHOW", "TRAINER_SHOW", "QUEST_DETAIL", "QUEST_GREETING", "BANKFRAME_OPENED" }) do
      pcall(seen.RegisterEvent, seen, ev)
    end
    local window = { GOSSIP_SHOW = true, MERCHANT_SHOW = true, TRAINER_SHOW = true, QUEST_DETAIL = true,
      QUEST_GREETING = true, BANKFRAME_OPENED = true }
    seen:SetScript("OnEvent", function(_, ev)
      if not ns.db then return end
      if window[ev] then
        pcall(ns.LearnNpcName, "npc")
      elseif ev == "UPDATE_MOUSEOVER_UNIT" then
        pcall(ns.LearnNpcName, "mouseover")
        pcall(ns.CheckDeadUnit, "mouseover")
      else
        if ev == "PLAYER_TARGET_CHANGED" then pcall(ns.LearnNpcName, "target") end
        pcall(ns.CheckDeadUnit, "target")
        pcall(ns.CheckDeadUnit, "focus")
      end
    end)
    if ns.TimeScript then ns.TimeScript(seen, "OnEvent", "events (core)") end
    -- (never the combat log: COMBAT_LOG_EVENT_UNFILTERED is restricted in this client, HasRestrictions in its own API
    -- docs, and registering it raises ADDON_ACTION_FORBIDDEN, which pcall doesn't stop; a companion addon hit it,
    -- 2026-10-05. A boss's kill comes from ENCOUNTER_END / BOSS_KILL, a dead boss looked at, or a right-click)
    f:SetScript("OnEvent", function(_, ev, ...)
      if not ns.db then return end
      local N = ns.Nav
      if ev == "PLAYER_ENTERING_WORLD" then
        local inside = N and N.CurrentInstance and N.CurrentInstance() ~= nil
        -- (into a dungeon: its way in is where the player last stood outside, Taxi.NoteEntrance)
        if inside and ns.Taxi and ns.Taxi.NoteEntrance and GetInstanceInfo then
          local ok, _, _, _, _, _, _, _, mapID = pcall(GetInstanceInfo)
          if ok then
            pcall(ns.Taxi.NoteWing, mapID, GetTime()) -- (the wing gone in by: its map and boss route)
            pcall(ns.Taxi.NoteEntrance, mapID, GetTime())
          end
        end
        -- (after a /reload or logging in: the continent's roads and terrain prepared in the
        -- background now, not in the frame of the first route or the first showing of the roads)
        if C_Timer and C_Timer.After and ns.Router and ns.Router.WarmUp then
          C_Timer.After(2, function()
            local x, y, c = ns.Geo.PlayerWorld()
            if not x then return end
            pcall(ns.Router.WarmUp, c, x, y)
            local lvl = ns.Nav and ns.Nav.PlayerLevel and ns.Nav.PlayerLevel(c)
            if lvl and lvl ~= c then pcall(ns.Router.WarmUp, lvl, x, y) end
          end)
        end
        -- (in or out of a dungeon: its boss route started or ended, once the position settles)
        if ns.GPS and ns.GPS.DungeonEntered then
          if C_Timer and C_Timer.After then C_Timer.After(1.5, ns.GPS.DungeonEntered) else ns.GPS.DungeonEntered() end
        end
        return
      end
      if N and N.BossKilled and (ev == "BOSS_KILL" or (ev == "ENCOUNTER_END" and select(5, ...) == 1)) then
        local id, name = ...
        if not ns.IsSecret(id) and N.BossKilled(N.CurrentInstance(), nil, id, name) > 0 and ns.GPS and ns.GPS.Redraw then ns.GPS.Redraw() end
      end
      ns.db.encounterLog = ns.db.encounterLog or {}
      local args = {}
      for i = 1, select("#", ...) do args[#args + 1] = tostring((select(i, ...))) end
      local log = ns.db.encounterLog
      log[#log + 1] = date("%H:%M:%S") .. " " .. ev .. " " .. table.concat(args, ",")
      while #log > 20 do table.remove(log, 1) end
    end)
    if ns.TimeScript then ns.TimeScript(f, "OnEvent", "events (core)") end
  end
end

function ns.RunProbe(reason)
  local rec = { time = time(), reason = reason or "manual", results = {} }
  local lines = {}
  local function add(name, fn)
    local res = { pcall(fn) }
    local ok = table.remove(res, 1)
    local desc
    if not ok then
      desc = "ERROR: " .. tostring(res[1])
    else
      local parts = {}
      for i = 1, math.max(#res, 1) do parts[#parts + 1] = Describe(res[i]) end
      desc = table.concat(parts, ", ")
    end
    rec.results[#rec.results + 1] = { name = name, ok = ok, value = desc }
    lines[#lines + 1] = name .. " = " .. desc
  end

  add("GetBuildInfo", function() return GetBuildInfo() end)
  add("InCombatLockdown", function() return InCombatLockdown() end)
  local mapID
  add("C_Map.GetBestMapForUnit", function() mapID = C_Map.GetBestMapForUnit("player"); return mapID end)
  add("C_Map.GetPlayerMapPosition", function()
    local pos = C_Map.GetPlayerMapPosition(mapID, "player")
    if not pos then return nil end
    return pos:GetXY()
  end)
  add("GetPlayerFacing", function() return GetPlayerFacing() end)
  add("GetUnitSpeed", function() return GetUnitSpeed("player") end)
  add("UnitPosition", function() return UnitPosition("player") end)
  add("IsInInstance", function() return IsInInstance() end)
  -- (instances, for 1.0.7: what the game gives inside one)
  add("GetInstanceInfo", function() return GetInstanceInfo() end)
  add("map info", function()
    local i = mapID and C_Map.GetMapInfo(mapID)
    return i and i.name, i and i.mapType, i and i.parentMapID
  end)
  add("map floors", function()
    local g = mapID and C_Map.GetMapGroupID and C_Map.GetMapGroupID(mapID)
    local out = {}
    for _, m in ipairs(g and C_Map.GetMapGroupMembersInfo(g) or {}) do out[#out + 1] = m.mapID .. " " .. tostring(m.name) end
    return g, table.concat(out, "; ")
  end)
  add("map art", function() return mapID and C_Map.GetMapArtID and C_Map.GetMapArtID(mapID) end)
  add("boss events seen", function()
    local out = {}
    for _, e in ipairs(ns.db and ns.db.encounterLog or {}) do out[#out + 1] = e end
    return table.concat(out, " | ")
  end)
  add("GPS.state", function() return ns.GPS and ns.GPS.Describe() end)
  add("Layers.state", function() return ns.Layers and ns.Layers.Describe() end)
  add("Arrow.state", function() return ns.Arrow and ns.Arrow.Describe() end)
  add("Teleports.state", function() return ns.Teleports and ns.Teleports.Describe() end)
  add("Nav.plan", function() return ns.Nav and ns.Nav.DescribePlan() end)
  -- (party and raid members' positions: what the game gives an addon for them, for showing them on
  -- the map; by unit, not name: no other player's name in the saved probes)
  add("party positions", function()
    local units = {}
    if IsInRaid and IsInRaid() then
      for i = 1, 40 do units[#units + 1] = "raid" .. i end
    else
      for i = 1, 4 do units[#units + 1] = "party" .. i end
    end
    local function show(v, fmt)
      if v == nil then return "nil" end
      if ns.IsSecret and ns.IsSecret(v) then return "secret" end
      local ok, t = pcall(string.format, fmt, v)
      return ok and t or "?"
    end
    local out = {}
    -- (the group as the game tells it, and which member units exist: "none" while grouped would
    -- mean party1-4 aren't how this client names them)
    local exists = {}
    for _, u in ipairs({ "party1", "party2", "party3", "party4", "raid1", "raid2", "raid3" }) do
      local ok, e = pcall(UnitExists or error, u)
      if ok and e and not (ns.IsSecret and ns.IsSecret(e)) then exists[#exists + 1] = u end
    end
    local function call(f)
      local ok, v = pcall(f or error)
      return ok and tostring(v) or "error"
    end
    out[1] = string.format("group: IsInGroup=%s IsInRaid=%s members=%s units=%s", call(IsInGroup), call(IsInRaid),
      call(GetNumGroupMembers), #exists > 0 and table.concat(exists, ",") or "none")
    out[2] = string.format("class art: atlas classicon-mage=%s CLASS_ICON_TCOORDS=%s",
      tostring(C_Texture and C_Texture.GetAtlasInfo and C_Texture.GetAtlasInfo("classicon-mage") ~= nil or false),
      tostring(CLASS_ICON_TCOORDS ~= nil))
    for _, u in ipairs(units) do
      if UnitExists and UnitExists(u) and not (UnitIsUnit and UnitIsUnit(u, "player")) then
        local okp, x, y, _, inst = pcall(UnitPosition, u)
        local okm, map = pcall(C_Map.GetBestMapForUnit, u)
        local mx, my, mapErr
        if okm and map then
          local ok2, pos = pcall(C_Map.GetPlayerMapPosition, map, u)
          if ok2 and pos then mx, my = pos:GetXY() elseif not ok2 then mapErr = true end
        end
        out[#out + 1] = string.format("%s: UnitPosition=%s map=%s mapPos=%s connected=%s",
          u, okp and (show(x, "%.0f") .. "," .. show(y, "%.0f") .. " inst=" .. tostring(inst)) or "error",
          okm and show(map, "%d") or "error", mapErr and "error" or (show(mx, "%.3f") .. "," .. show(my, "%.3f")),
          tostring(UnitIsConnected and UnitIsConnected(u)))
      end
    end
    return table.concat(out, " | ")
  end)
  add("start errors", function() return table.concat(ns.initErrors or {}, " | ") end)
  add("C_Minimap", function()
    local names = {}
    for k in pairs(C_Minimap or {}) do names[#names + 1] = k end
    table.sort(names)
    return table.concat(names, " ")
  end)
  add("C_QuestLog", function()
    local names = {}
    for k in pairs(C_QuestLog or {}) do names[#names + 1] = k end
    table.sort(names)
    return table.concat(names, " ")
  end)
  -- The widget the world map draws quest objective areas with: does it exist, and can it
  -- tell which quest area a point is in (so the area's outline could be traced)?
  add("QuestPOIFrame", function()
    local ok, f = pcall(CreateFrame, "QuestPOIFrame", nil, UIParent)
    if not ok or not f then return "not available: " .. tostring(f) end
    f:Hide()
    local names = {}
    local idx = getmetatable(f) and getmetatable(f).__index
    for k in pairs(type(idx) == "table" and idx or {}) do
      if type(k) == "string" and (k:find("Quest") or k:find("Blob") or k:find("POI") or k:find("Mouse")
          or k:find("Draw") or k:find("Map") or k:find("Tooltip") or k:find("Alpha")) then
        names[#names + 1] = k
      end
    end
    table.sort(names)
    return table.concat(names, " ")
  end)
  add("C_MapExplorationInfo.GetExploredMapTextures(player map)", function()
    local list = C_MapExplorationInfo.GetExploredMapTextures(mapID) or {}
    local n = 0
    for _, e in ipairs(list) do n = n + #(e.fileDataIDs or {}) end
    return #list .. " explored areas, " .. n .. " textures"
  end)
  add("C_QuestLine", function()
    local names = {}
    for k in pairs(C_QuestLine or {}) do names[#names + 1] = k end
    table.sort(names)
    return table.concat(names, " ")
  end)
  add("GetQuestsOnMap(player map)", function()
    local out = {}
    for _, q in ipairs(C_QuestLog.GetQuestsOnMap(mapID) or {}) do
      out[#out + 1] = string.format("%s@%.3f,%.3f", tostring(q.questID), q.x or -1, q.y or -1)
    end
    return table.concat(out, " ")
  end)
  add("GetAvailableQuestLines(player map)", function()
    C_QuestLine.RequestQuestLinesForMap(mapID)
    local out = {}
    for _, q in ipairs(C_QuestLine.GetAvailableQuestLines(mapID) or {}) do
      out[#out + 1] = string.format("%s@%.3f,%.3f%s", tostring(q.questName), q.x or -1, q.y or -1, q.isHidden and "(hidden)" or "")
    end
    return table.concat(out, " ")
  end)

  local probes = ns.db.probes
  probes[#probes + 1] = rec
  while #probes > 50 do table.remove(probes, 1) end
  Print("probe (" .. rec.reason .. "):")
  for _, l in ipairs(lines) do Print("  " .. l) end
end

-- Developer hook: `AzerothGPS_Extend(fn)` runs fn(ns), the addon's own tables, for a private dev
-- addon (never shipped). It plugs in at
-- PLAYER_LOGIN, after every part has started. Nothing in AzerothGPS calls it.
-- `AzerothGPS_Extend(fn, "load")` runs fn(ns) at once, while the addons load (no saved data yet): for a file that
-- puts its functions on the addon's tables as it loads.
local extenders = {}
function AzerothGPS_Extend(fn, when)
  if type(fn) ~= "function" then return end
  if when == "load" then
    fn(ns)
    return
  end
  if ns.started then
    local ok, err = pcall(fn, ns)
    if not ok and ns.Print then ns.Print(string.format(L["an extension failed: %s"], tostring(err))) end
  else
    extenders[#extenders + 1] = fn
  end
end

local ev = CreateFrame("Frame")
ev:RegisterEvent("ADDON_LOADED")
ev:RegisterEvent("PLAYER_LOGIN")
ev:RegisterEvent("PLAYER_REGEN_DISABLED")
ev:RegisterEvent("PLAYER_REGEN_ENABLED")
ev:RegisterEvent("PLAYER_ENTERING_WORLD") -- (a real login: ns.OnEnteringWorld)
ev:RegisterEvent("PLAYER_LOGOUT") -- (a /reload or logout: the floor followed in a building kept, Nav.SaveTrack)
pcall(ev.RegisterEvent, ev, "UI_SCALE_CHANGED")
pcall(ev.RegisterEvent, ev, "DISPLAY_SIZE_CHANGED")

-- A spell's name and icon, whichever API this client has (C_Spell in newer clients,
-- GetSpellInfo / GetSpellTexture in older ones).
function ns.SpellName(id)
  if C_Spell and C_Spell.GetSpellName then
    local ok, name = pcall(C_Spell.GetSpellName, id)
    if ok and name then return name end
  end
  if GetSpellInfo then
    local ok, name = pcall(GetSpellInfo, id)
    if ok then return name end
  end
  return nil
end

function ns.SpellIcon(id)
  if C_Spell and C_Spell.GetSpellTexture then
    local ok, icon = pcall(C_Spell.GetSpellTexture, id)
    if ok and icon then return icon end
  end
  if GetSpellTexture then
    local ok, icon = pcall(GetSpellTexture, id)
    if ok then return icon end
  end
  return nil
end


-- The windows' corner logo (the map's and the options' PortraitFrameTemplate), pre-scaled
-- (`agps media`, app/azerothgps/media.py): the size nearest the pixels it covers on this screen, shown
-- 1:1 (one picture shrunk by the graphics card looked soft). Fitted again when the window shows and
-- when the UI's scale or the screen changes. Without the circle (the round portrait's option was
-- removed, 2026-10-01): the logo on a plate of the title bar's brown cut to its outline
-- (Media/CornerLogo<px>.tga), the window's border without the portrait's ring
-- ("ButtonFrameTemplateNoPortrait"), in the top-left corner half above the title bar, over every part
-- of the window's frame; dragging it moves the window as the title bar does.
ns.PORTRAIT_PX = { 48, 56, 64, 72, 80, 96, 112, 128, 144, 160, 176, 192, 208, 224, 256, 288 } -- (media.py's)
ns.SMALL_LOGO_PX = { 16, 20, 24, 28, 32, 36, 40, 44 } -- (smaller ones for the minimap square's logo: media.py's)
ns.CORNER_LOGO_UNITS = 62 -- (the portrait's size)
ns.POPUP_LOGO_UNITS = 44 -- (a popup's: no lower than its title bar, ns.Window)
ns.TITLE_MID = 11 -- the title bar's middle, under the window's top (its TitleContainer: 1 down, 20 high)
local MEDIA = "Interface\\AddOns\\AzerothGPS\\Media\\"
local windows = {} -- { chrome, portrait, move = fn(starting), plate }
-- Screen pixels per UI unit at effective scale `effScale` (a frame's GetEffectiveScale()).
function ns.PixelsPerUnit(effScale)
  local ppu = 1
  if GetPhysicalScreenSize then
    local ok, _, h = pcall(GetPhysicalScreenSize)
    if ok and h and h > 0 then ppu = h / 768 * (effScale or 1) end
  end
  return ppu
end
-- The pre-scaled size for `units` UI units at effective scale `effScale`, and the screen pixels per unit.
-- (`small`: the minimap square's smaller sizes too)
function ns.PortraitPx(units, effScale, small)
  local ppu = ns.PixelsPerUnit(effScale)
  local want, px = units * ppu, ns.PORTRAIT_PX[1]
  for _, list in ipairs(small and { ns.SMALL_LOGO_PX, ns.PORTRAIT_PX } or { ns.PORTRAIT_PX }) do
    for _, s in ipairs(list) do
      if math.abs(s - want) < math.abs(px - want) then px = s end
    end
  end
  return px, ppu
end
local function Show1to1(tex, file, px)
  local pot = 1
  while pot < px do pot = pot * 2 end
  tex:SetTexture(MEDIA .. file .. px)
  tex:SetTexCoord(0, px / pot, 0, px / pot)
  if tex.SetSnapToPixelGrid then tex:SetSnapToPixelGrid(true) end
end
-- The corner logo on texture `tex` at about `units` UI units (on a frame of effective scale `effScale`), pixel for pixel
-- as the window's (the nearest pre-scaled size): its size in units (the minimap square's button, asked 2026-11-09).
function ns.ShowCornerLogo(tex, units, effScale)
  local px, ppu = ns.PortraitPx(units, effScale, true)
  Show1to1(tex, "CornerLogo", px)
  return px / ppu
end
-- The plate logo's picture and place on window `w` (its size: exactly the picture's pixels).
local function FitCorner(w)
  local px, ppu = ns.PortraitPx(w.units or ns.CORNER_LOGO_UNITS, w.chrome:GetEffectiveScale(), w.units and true or nil)
  Show1to1(w.plate.tex, "CornerLogo", px)
  local size = px / ppu
  w.plate:SetSize(size, size)
  w.plate:ClearAllPoints()
  w.plate:SetPoint("CENTER", w.chrome, "TOPLEFT", size * 0.42, -ns.TITLE_MID)
  return px
end
-- The highest frame level among `f` and everything under it (the window's border, title bar and close
-- button are frames of their own), but `skip`.
local function TopLevel(f, skip, best)
  best = math.max(best or 0, f:GetFrameLevel())
  for _, c in ipairs({ f:GetChildren() }) do
    if c ~= skip then best = TopLevel(c, skip, best) end
  end
  return best
end
local function Fit(w)
  if w.plate then FitCorner(w) end
end
function ns.FitPortraits()
  for _, w in ipairs(windows) do Fit(w) end
end
-- Each window's logo: the plate without the circle, the border without the portrait's ring.
function ns.ApplyLogoLook()
  for _, w in ipairs(windows) do
    local c = w.chrome
    if c.SetBorder then pcall(c.SetBorder, c, "ButtonFrameTemplateNoPortrait") end
    w.portrait:SetShown(false)
    do
      if not w.plate then
        local plate = CreateFrame("Frame", nil, c)
        plate.tex = plate:CreateTexture(nil, "ARTWORK")
        plate.tex:SetAllPoints()
        plate:EnableMouse(true)
        plate:RegisterForDrag("LeftButton")
        plate:SetScript("OnDragStart", function() if w.move then w.move(true) end end)
        plate:SetScript("OnDragStop", function() if w.move then w.move(false) end end)
        w.plate = plate
      end
      w.plate:SetFrameStrata(c:GetFrameStrata()) -- (over the title bar: above every part of the frame)
      w.plate:SetFrameLevel(math.min(9000, TopLevel(c, w.plate) + 5))
      w.plate:Show()
    end
    Fit(w)
  end
  -- (the new border's pieces: another addon's tint for the map's frame again, API 14)
  if ns.GPS and ns.GPS.ApplyFrameLook then ns.GPS.ApplyFrameLook() end
  -- (the map as the minimap square: its own border back, no title band or logo)
  if ns.GPS and ns.GPS.KeepMinimapChrome then ns.GPS.KeepMinimapChrome() end
end
-- `f`'s logo (a PortraitFrameTemplate window); `move(starting)` moves the window (dragging the plate
-- logo). `file`: another picture in its round portrait, as it is. Returns its record ({ chrome,
-- portrait, move, plate }).
function ns.SetLogoPortrait(f, file, move, units)
  local p = f.GetPortrait and f:GetPortrait() or (f.PortraitContainer and f.PortraitContainer.portrait)
  if not p then return end
  if file then
    p:SetTexture(MEDIA .. file)
    return
  end
  local w = { chrome = f, portrait = p, move = move, units = units } -- (`units`: a smaller logo, a popup's)
  windows[#windows + 1] = w
  if f.HookScript then f:HookScript("OnShow", function() Fit(w) end) end
  ns.ApplyLogoLook()
  return w
end

-- Popup windows (asked, 2026-10-01: every popup in the map window's art style, without its logo): the
-- client's PortraitFrameTemplate (metal border, title bar, close button) with the border that has no
-- portrait, a dark inside like the map window's title strip, the title centered; a plain dark box with a
-- border and a close button if the template isn't there. Every popup AzerothGPS makes uses it (a test
-- checks: test_every_popup_window_is_made_with_ns_window), and its companions through API.Window.
-- Dragged anywhere to move, kept on the screen, closed by its button or Escape (a plain Hide: works in
-- combat). Returns the frame: its content goes from `f.top` (negative) down; f:SetWindowTitle(text).
-- `opts`: { parent (default the screen), noTitle (no title bar or close button: a question's, ns.Ask; the
-- border without the title band), fixed (not dragged) }.
ns.WINDOW_BG = { 0.06, 0.06, 0.07, 0.97 }
ns.WINDOW_TITLE_MARGIN = 24 -- (as the map window's: GPSFrame's TITLE_MARGIN)
ns.WINDOW_PLAIN_BORDER = "SimplePanelTemplate" -- (the client's metal border without a title band)
-- Popups over the map opened out of the minimap square (asked 2026-11-09: "any new popup like options or streetview
-- windows should go on top of that"): the map is at GPSFrame's MINIMAP_EXPANDED_STRATA (FULLSCREEN, over the world
-- map, quest log and bags) meanwhile, and every window made here (ns.Window, so API.Window's too, and the options) goes
-- to POPUP_OVER_STRATA while it shows then (lifted as it shows, or as the map opens out), back to its own after.
ns.POPUP_OVER_STRATA = "FULLSCREEN_DIALOG"
ns.STRATA_ORDER = { BACKGROUND = 1, LOW = 2, MEDIUM = 3, HIGH = 4, DIALOG = 5, FULLSCREEN = 6, FULLSCREEN_DIALOG = 7,
  TOOLTIP = 8 }
ns.popups = setmetatable({}, { __mode = "k" }) -- { [frame] = its own strata }
function ns.LiftPopup(f)
  if not (ns.popupsOver and f and f:IsShown()) or f.agpsLifted then return end
  local own = ns.popups[f]
  if own and (ns.STRATA_ORDER[own] or 0) < ns.STRATA_ORDER[ns.POPUP_OVER_STRATA] then
    f:SetFrameStrata(ns.POPUP_OVER_STRATA)
    f.agpsLifted = true
    if f.Raise then f:Raise() end
    if f.Layer then f.Layer() end -- (a question's buttons with it: ns.Ask)
  end
end
function ns.RegisterPopup(f, strata)
  ns.popups[f] = strata or (f.GetFrameStrata and f:GetFrameStrata()) or "DIALOG"
  if f.HookScript then
    f:HookScript("OnShow", function(self)
      self.agpsShownAt = GetTime and GetTime() or 0 -- (the one shown last: a controller's, PadOptions.lua)
      ns.LiftPopup(self)
    end)
  end
end
-- The map opened out (`on`): the popups showing lifted over it; back: every lifted one at its own strata again.
function ns.SetPopupsOver(on)
  ns.popupsOver = on and true or nil
  for f, own in pairs(ns.popups) do
    if on then
      ns.LiftPopup(f)
    elseif f.agpsLifted then
      f:SetFrameStrata(own)
      f.agpsLifted = nil
      if f.Layer then f.Layer() end
    end
  end
end
-- Every popup shown and not lifted yet, lifted (each frame while the map is out, GPSFrame's G.MinimapTick: a window
-- whose own OnShow script replaced the hook is lifted too).
function ns.LiftShownPopups()
  if not ns.popupsOver then return end
  for f in pairs(ns.popups) do
    if not f.agpsLifted and f:IsShown() then ns.LiftPopup(f) end
  end
end
-- A popup over the opened-out map in use (the map's quiet clock: it doesn't go back under it): the options showing
-- (`agpsBusy`), or one the mouse is over (a window left open for long, a companion's, doesn't hold it out for ever).
function ns.PopupOverShown()
  for f in pairs(ns.popups) do
    if f.agpsLifted and f:IsShown() and (f.agpsBusy or (f.IsMouseOver and f:IsMouseOver())) then return true end
  end
  return false
end
function ns.Window(name, w, h, title, strata, opts)
  opts = opts or {}
  local f = CreateFrame("Frame", name, opts.parent or UIParent, BackdropTemplateMixin and "BackdropTemplate" or nil)
  f:SetSize(w, h)
  f:SetPoint("CENTER")
  f:SetFrameStrata(strata or "DIALOG")
  ns.RegisterPopup(f, strata or "DIALOG")
  f:SetToplevel(true)
  f:SetClampedToScreen(true)
  f:EnableMouse(true)
  if not opts.fixed then
    f:SetMovable(true)
    f:RegisterForDrag("LeftButton")
    f:SetScript("OnDragStart", function(self) self:StartMoving() end)
    f:SetScript("OnDragStop", function(self) self:StopMovingOrSizing() end)
  end
  if name and UISpecialFrames then table.insert(UISpecialFrames, name) end -- (Escape closes it)
  local c = ns.WINDOW_BG
  local bg = f:CreateTexture(nil, "BACKGROUND")
  bg:SetPoint("TOPLEFT", 3, -3)
  bg:SetPoint("BOTTOMRIGHT", -3, 3)
  bg:SetColorTexture(c[1], c[2], c[3], c[4])
  f.bg = bg
  local ok, chrome = pcall(CreateFrame, "Frame", nil, f, "PortraitFrameTemplate")
  if ok and chrome and chrome.NineSlice then
    chrome:SetAllPoints()
    chrome:SetFrameLevel(f:GetFrameLevel()) -- (under the window's own controls)
    chrome:EnableMouse(false)
    if chrome.Bg then chrome.Bg:Hide() end
    if chrome.TopTileStreaks then chrome.TopTileStreaks:Hide() end
    local function Border(layout)
      if chrome.SetBorder then return (pcall(chrome.SetBorder, chrome, layout)) end
      if NineSliceUtil and NineSliceUtil.ApplyLayoutByName then
        return (pcall(NineSliceUtil.ApplyLayoutByName, chrome.NineSlice, layout))
      end
      return false
    end
    -- (no title bar: the plain metal border, else the usual one with its title band empty)
    if not (opts.noTitle and Border(ns.WINDOW_PLAIN_BORDER)) then Border("ButtonFrameTemplateNoPortrait") end
    if chrome.PortraitContainer then chrome.PortraitContainer:Hide() end
    if chrome.portrait then chrome.portrait:Hide() end
    local tc = chrome.TitleContainer
    if tc and tc.ClearAllPoints and tc.GetPoint then -- (centered on the window, as the map window's)
      local _, _, _, _, y = tc:GetPoint(1)
      tc:ClearAllPoints()
      tc:SetPoint("TOPLEFT", chrome, "TOPLEFT", ns.WINDOW_TITLE_MARGIN, y or -1)
      tc:SetPoint("TOPRIGHT", chrome, "TOPRIGHT", -ns.WINDOW_TITLE_MARGIN, y or -1)
    end
    if chrome.CloseButton then chrome.CloseButton:SetScript("OnClick", function() f:Hide() end) end
    if opts.noTitle then
      if tc then tc:Hide() end
      if chrome.CloseButton then chrome.CloseButton:Hide() end
    end
    function f.SetWindowTitle(_, text)
      if chrome.SetTitle then chrome:SetTitle(text)
      elseif tc and tc.TitleText then tc.TitleText:SetText(text) end
    end
    f.chrome, f.top = chrome, opts.noTitle and -14 or -30
    -- (the addon's logo on its corner, smaller than the map window's so it stays on the title bar: asked 2026-11-10,
    -- "nothing tells the player this is for AGPS ... should be on every popup"; not a question's box without a title
    -- bar, nor a window another addon asked for, `opts.noLogo`)
    if not opts.noTitle and not opts.noLogo then
      f.logo = ns.SetLogoPortrait(chrome, nil, function(starting)
        local fn = f:GetScript(starting and "OnDragStart" or "OnDragStop")
        if fn then fn(f) end
      end, ns.POPUP_LOGO_UNITS)
    end
  else
    if f.SetBackdrop then
      f:SetBackdrop({ bgFile = "Interface\\Buttons\\WHITE8X8", edgeFile = "Interface\\Buttons\\WHITE8X8", edgeSize = 1 })
      f:SetBackdropColor(c[1], c[2], c[3], c[4])
      f:SetBackdropBorderColor(0.3, 0.3, 0.3, 1)
    end
    local t = f:CreateFontString(nil, "ARTWORK", "GameFontNormal")
    t:SetPoint("TOP", 0, -8)
    function f.SetWindowTitle(_, text) t:SetText(text) end
    if not opts.noTitle then
      local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
      close:SetPoint("TOPRIGHT", 2, 2)
      close:SetScript("OnClick", function() f:Hide() end)
      f.closeButton = close
    end
    f.top = opts.noTitle and -12 or -28
  end
  f:SetWindowTitle(title or "")
  f:Hide()
  return f
end

-- A question with two answers, in AzerothGPS's popup: its title bar and corner logo like every other window's (asked
-- 2026-11-11: "needs azeroth standardizing for all windows, logo, color, etc just like tutorial pages"; until then a
-- question's box had no title bar). Its close button is no answer, like Escape. The text,
-- then `yes` and `no` buttons; onYes / onNo on the answer (onNo also when it times out, `opts.timeout`
-- seconds, or Escape hides it: onNo(true) when No was clicked, onNo() when unanswered). One window per `name` (made the first time), shown again for the next
-- question; `opts.parent` and `opts.place(f)` put it somewhere else than the screen's middle (`opts.key`: the window's
-- own key then, the same name kept for who watches it). `opts.check`: a checkbox's label under the text (unticked
-- each time); its state goes to onYes(checked) and onNo(clicked, checked). Returns it.
local asks = {}
-- Whether any of these questions is up now (one at a time: Nav's pause suggestion waits for it).
function ns.AskShown()
  for _, f in pairs(asks) do
    if f.IsShown and f:IsShown() then return true end
  end
  return false
end
function ns.Ask(name, text, yes, no, onYes, onNo, opts)
  opts = opts or {}
  local key = opts.key or name
  local f = asks[key]
  if not f then
    f = ns.Window(opts.parent and nil or name, 300, 120, "AzerothGPS", opts.strata, { parent = opts.parent,
      fixed = opts.parent ~= nil })
    f.text = f:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    f.text:SetPoint("TOPLEFT", 16, f.top - 4)
    f.text:SetPoint("TOPRIGHT", -16, f.top - 4)
    f.text:SetJustifyH("LEFT")
    local function Btn(x)
      local ok, b = pcall(CreateFrame, "Button", nil, f, "UIPanelButtonTemplate")
      if not ok then b = CreateFrame("Button", nil, f) end
      b:SetSize(110, 22)
      if x < 0 then b:SetPoint("BOTTOMRIGHT", f, "BOTTOM", -5, 14) else b:SetPoint("BOTTOMLEFT", f, "BOTTOM", 5, 14) end
      return b
    end
    f.yes, f.no = Btn(-60), Btn(60)
    -- (`opts.single`: something told, not asked: the one button, in the middle)
    function f.Buttons(single)
      f.yes:ClearAllPoints()
      if single then
        f.yes:SetPoint("BOTTOM", f, "BOTTOM", 0, 14)
      else
        f.yes:SetPoint("BOTTOMRIGHT", f, "BOTTOM", -5, 14)
      end
      f.no:SetShown(not single)
    end
    local function Checked() return f.check and f.check:IsShown() and f.check:GetChecked() and true or false end
    f.yes:SetScript("OnClick", function()
      f.answered = true
      local checked = Checked()
      f:Hide()
      if f.onYes then f.onYes(checked) end
    end)
    f.no:SetScript("OnClick", function()
      f.answered = true
      local checked = Checked()
      f:Hide()
      if f.onNo then f.onNo(true, checked) end -- (`true`: No clicked; unanswered, nil)
    end)
    -- (not answered: Escape, or the time out, counts as no. Hidden only with its parent, the map it's on closed (the
    -- game sends OnHide then too; still shown itself): still waiting, the "?" over the logo shows it. Kooki3z on
    -- 6195a75c: the map closed over "No way around the guards", the question was let go and no "?" came)
    f:SetScript("OnHide", function()
      if f.IsShown and f:IsShown() then return end
      if not f.answered and f.onNo then f.onNo() end
      f.answered = true
    end)
    f:SetScript("OnUpdate", function(self)
      if self.until_ and GetTime() > self.until_ then self:Hide() end
    end)
    -- (the keys, item 93: Enter answers yes, Escape no (the one button of something told: Escape takes it); every other
    -- key goes on to the game. Out of combat only: in it a keyboard-taking frame couldn't let the other keys through)
    f:SetScript("OnKeyDown", function(self, key) return ns.AskKey(self, key) end)
    -- (each part's level over the window's own, as each question is shown: item 93b, Kooki3z on e96d80ee, the question
    -- shown again later in a session had Yes and No as plain text under its frame's art, and took no clicks)
    function f.Layer()
      local l = f:GetFrameLevel() or 1
      local strata = f:GetFrameStrata()
      if f.chrome then f.chrome:SetFrameLevel(l) end
      for _, b in ipairs({ f.yes, f.no, f.check or false }) do
        if b then
          if strata and b.SetFrameStrata then b:SetFrameStrata(strata) end
          b:SetFrameLevel(l + ns.ASK_BUTTON_LEVELS)
          if b.EnableMouse then b:EnableMouse(true) end
          if b.Enable then b:Enable() end
        end
      end
    end
    asks[key] = f
  end
  -- (a parent given: the window on it, as it may be another than the last time's)
  if opts.parent and f.GetParent and f:GetParent() ~= opts.parent and f.SetParent then f:SetParent(opts.parent) end
  -- (its strata as asked each time, not only as first made: item 93b)
  if opts.strata then
    f:SetFrameStrata(opts.strata)
    if ns.popups[f] then ns.popups[f] = opts.strata end
    f.agpsLifted = nil
  end
  f.answered = true
  f:Hide() -- (the last question, unanswered: let go without its no)
  f.answered = false
  f.onYes, f.onNo = onYes, onNo
  f.Buttons(opts.single and true or false)
  f.yes:SetText(yes or YES or L["Yes"])
  f.no:SetText(no or NO or L["No"])
  -- (as wide as their labels, longer in some languages: side by side from the middle, the window wider to fit)
  local wy, wn = 110, 110
  if f.yes.GetTextWidth then wy = math.max(110, (f.yes:GetTextWidth() or 0) + 24) end
  if f.no.GetTextWidth then wn = math.max(110, (f.no:GetTextWidth() or 0) + 24) end
  f.yes:SetWidth(wy)
  f.no:SetWidth(wn)
  f:SetWidth(math.max(300, 2 * math.max(wy, wn) + 50))
  f.text:SetText(text)
  local checkRoom = 0
  if opts.check then
    if not f.check then
      local ok, c = pcall(CreateFrame, "CheckButton", nil, f, "UICheckButtonTemplate")
      if not ok then c = CreateFrame("CheckButton", nil, f) end
      c:SetSize(24, 24)
      c.label = c.Text or c:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
      if not c.Text then c.label:SetPoint("LEFT", c, "RIGHT", 2, 0) end
      f.check = c
    end
    f.check:ClearAllPoints()
    f.check:SetPoint("BOTTOMLEFT", f, "BOTTOMLEFT", 12, 40)
    f.check.label:SetText(opts.check)
    f.check:SetChecked(false)
    f.check:Show()
    checkRoom = 26
  elseif f.check then
    f.check:Hide()
  end
  f:SetHeight(f.text:GetStringHeight() + 22 - f.top + 34 + checkRoom)
  f.until_ = opts.timeout and GetTime() + opts.timeout or nil
  f:ClearAllPoints()
  if opts.place then opts.place(f) else f:SetPoint("CENTER", 0, 120) end
  if opts.level then f:SetFrameLevel(opts.level) end
  f:Show()
  f:Raise()
  f.Layer()
  ns.AskKeys(f)
  ns.lastAsk = f -- (the question up last: a controller's A and B answer it, Pad.lua)
  return f
end
ns.ASK_BUTTON_LEVELS = 5 -- (a question's buttons this many levels over its window: over its border's art)
-- A question's keys on (out of combat) or off (in it).
function ns.AskKeys(f)
  if not f.EnableKeyboard then return end
  local on = not (InCombatLockdown and InCombatLockdown())
  if on and f.SetPropagateKeyboardInput then on = pcall(f.SetPropagateKeyboardInput, f, true) end
  f:EnableKeyboard(on and true or false)
end
-- A key pressed with question `f` showing: Enter its Yes, Escape its No (or its one button); the rest to the game.
function ns.AskKey(f, key)
  local combat = InCombatLockdown and InCombatLockdown()
  local enter = key == "ENTER" or key == "NUMPADENTER"
  local eat = not combat and (enter or key == "ESCAPE") and true or false
  if f.SetPropagateKeyboardInput then pcall(f.SetPropagateKeyboardInput, f, not eat) end
  if not eat then return false end
  local b = (enter or not (f.no and f.no:IsShown())) and f.yes or f.no
  local click = b and b:GetScript("OnClick")
  if click then click(b, "LeftButton") end
  return true
end

-- In combat: the map and arrow switch to their combat opacity, or hide (options).
ns.inCombat = false
-- What the player made since login or the last /reload, not saved yet (asked 2026-10-04: the game writes AzerothGPSDB
-- only at logout, quitting and /reload; killed with taskkill, a pin made and a pin removed were both gone at the next
-- login): pins added or removed, roads and walls drawn or taken back, dungeon entrances learned. Not settings, the
-- map's view or the logs. Counted only (API.SetUnsaved, the tests); the map's Save and Dismiss buttons are gone (asked
-- 2026-11-17: "Don't show save/dismiss anymore and remove that setting").
-- Kept per thing (`key`: "pin:<time>", "track:<time>", ...), so taking back what was made since the last save leaves
-- nothing to save (asked 2026-10-04: a pin made and removed again still asked to be saved). `how`: "add" (made) or
-- "remove" (taken away); ns.unsaved: how many differ from what's saved.
ns.unsaved = 0
local changes = {}
function ns.MarkUnsaved(key, how)
  local cur = changes[key]
  if how == "remove" then
    changes[key] = cur ~= "add" and "remove" or nil -- (made since the save, then taken back: as saved)
  else
    changes[key] = cur ~= "remove" and "add" or nil
  end
  ns.CountUnsaved()
end
-- Companion addons' own unsaved counts (API.SetUnsaved: a companion's paths, say), each with its line for the
-- button's tooltip: { [owner] = { count, text } }.
ns.unsavedOwners = {}
function ns.SetUnsavedOwner(owner, count, text)
  count = tonumber(count) or 0
  ns.unsavedOwners[owner] = count > 0 and { count, text } or nil
  ns.CountUnsaved()
end
-- ns.unsaved: AzerothGPS's own changes and every companion's.
function ns.CountUnsaved()
  local n = 0
  for _ in pairs(changes) do n = n + 1 end
  ns.unsavedOwn = n
  for _, o in pairs(ns.unsavedOwners) do n = n + o[1] end
  ns.unsaved = n
  return n
end
-- PLAYER_ENTERING_WORLD: a real login (from the character list, or WoW started again) ends what lasts until logout
-- (Draw Anyway's hint); a /reload or a loading screen doesn't. Its payload, isInitialLogin and isReloadingUi, is in
-- this client's own API docs (Blizzard_APIDocumentationGenerated/SystemDocumentation.lua: both bools, never nil); a
-- client without them (both nil) counts as a login, so nothing stays snoozed for good.
function ns.OnEnteringWorld(isInitialLogin, isReloadingUi)
  if not ns.db then return end
  if isInitialLogin or (isInitialLogin == nil and isReloadingUi == nil) then
    ns.db.unsavedSnoozedLogin = nil -- (left by the old Dismiss button, removed 2026-11-17)
  end
end
function ns.ResetUnsaved() -- (as just saved: the tests)
  changes, ns.unsavedOwners = {}, {}
  ns.CountUnsaved()
end
-- A Reload UI button the player clicks: a secure button with the macro "/reload" (ReloadUI() from an addon's own
-- click is blocked in this client, ADDON_ACTION_BLOCKED "Reload()", seen in game 2026-10-16, issue #56), laid over the
-- plain button `over` (its size and text) in the window `win`. On UIParent (a secure child would make its window
-- protected), shown while `over` is (`b.Sync`, call it when its window shows or hides), set and shown only out of combat, hidden as combat
-- starts; in the strata over its window's (the window raised on show went over it, and the plain button under it
-- took the click, in game). Nil when it can't be made (in combat, no template).
ns.STRATA_ABOVE = { BACKGROUND = "LOW", LOW = "MEDIUM", MEDIUM = "HIGH", HIGH = "DIALOG", DIALOG = "FULLSCREEN",
  FULLSCREEN = "FULLSCREEN_DIALOG", FULLSCREEN_DIALOG = "TOOLTIP" }
function ns.SecureReloadButton(over, win, name)
  if not CreateFrame or (InCombatLockdown and InCombatLockdown()) then return nil end
  local ok, b = pcall(CreateFrame, "Button", name, UIParent, "UIPanelButtonTemplate, SecureActionButtonTemplate")
  -- (the secure template last: its OnClick is the one kept)
  if not ok or not b then return nil end
  b:RegisterForClicks("AnyUp", "AnyDown") -- (either setting of "cast on key down")
  b:SetAttribute("type", "macro")
  b:SetAttribute("macrotext", "/reload")
  b:Hide()
  function b.Sync()
    if InCombatLockdown and InCombatLockdown() then return end
    local shown = over:IsVisible() and (not win or win:IsVisible()) and true or false
    if shown then
      b:ClearAllPoints()
      b:SetAllPoints(over)
      b:SetFrameStrata(ns.STRATA_ABOVE[over:GetFrameStrata()] or "TOOLTIP")
      b:SetText(over:GetText())
    end
    b:SetShown(shown)
  end
  local ev = CreateFrame("Frame")
  ev:RegisterEvent("PLAYER_REGEN_DISABLED") -- (fired before combat's lockdown: still allowed)
  ev:SetScript("OnEvent", function() b:Hide() end)
  return b
end

-- Save now: a /reload (the game writes the saved variables), never in combat. False when it can't.
function ns.SaveNow()
  if ns.inCombat or (InCombatLockdown and InCombatLockdown()) or not ReloadUI then return false end
  ReloadUI()
  return true
end

local function CombatChanged(inCombat)
  ns.inCombat = inCombat
  if ns.GPS and ns.GPS.ApplySettings then pcall(ns.GPS.ApplySettings) end
  if ns.Arrow and ns.Arrow.Apply then pcall(ns.Arrow.Apply) end
end
ev:SetScript("OnEvent", function(_, event, arg1, arg2)
  if event == "ADDON_LOADED" and arg1 == addonName then
    InitDB()
  elseif event == "PLAYER_ENTERING_WORLD" then
    ns.OnEnteringWorld(arg1, arg2) -- (isInitialLogin, isReloadingUi)
    -- (a walk being recorded ends at a loading screen; after a /reload, recording goes on)
    if ns.started and ns.Record and ns.Record.OnEnteringWorld then pcall(ns.Record.OnEnteringWorld, arg1, arg2) end
    if ns.started and ns.Setup and ns.Setup.OnEnteringWorld then pcall(ns.Setup.OnEnteringWorld) end
    if ns.started and ns.WhatsNew and ns.WhatsNew.OnEnteringWorld then pcall(ns.WhatsNew.OnEnteringWorld) end
    -- (a supported UI picks its font at login: our HUD text takes it again, UIFont.lua)
    if ns.started and ns.UIFont and ns.UIFont.OnEnteringWorld then pcall(ns.UIFont.OnEnteringWorld) end
  elseif event == "PLAYER_LOGOUT" then
    if ns.Nav and ns.Nav.SaveTrack then pcall(ns.Nav.SaveTrack) end
    if ns.Record and ns.Record.OnLogout then pcall(ns.Record.OnLogout) end
    if ns.db then pcall(ns.PackSaved, ns.db) end -- (last: the points saved as strings, ns.PackSaved)
  elseif event == "PLAYER_LOGIN" then
    local meta = (C_AddOns and C_AddOns.GetAddOnMetadata) or GetAddOnMetadata
    ns.VERSION = meta and meta(addonName, "Version") or "?"
    ns.db.lastChar = ns.CharKey()
    ns.CharDB().faction = UnitFactionGroup("player") -- "Horde" / "Alliance"
    pcall(ns.StartProfile) -- (the character's own profile, before anything below reads the options)
    -- each part starts on its own: one failing doesn't stop the others (and says why)
    ns.initErrors = {}
    local function Start(name, fn)
      if not fn then return end
      local ok, err = pcall(fn)
      if not ok then
        ns.initErrors[#ns.initErrors + 1] = name .. ": " .. tostring(err)
        Print(string.format(L["|cffff6060%s failed to start:|r %s"], name, tostring(err)))
      end
    end
    -- (a tutorial cut short by a /reload or a crash: the player's own settings and route back before anything reads them)
    Start("tutorial restore", ns.Tutorial and ns.Tutorial.RestoreSaved)
    Start("flight paths", ns.Taxi and ns.Taxi.OnLogin)
    Start("route", ns.Nav and ns.Nav.Restore)
    Start("map", ns.GPS and ns.GPS.Init)
    Start("minimap route", ns.GPS and ns.GPS.InitMinimapRoute)
    Start("direction arrow", ns.Arrow and ns.Arrow.Init)
    Start("UI text style", ns.UIFont and ns.UIFont.Init) -- (after the map and the arrow made their texts)
    Start("window looks", ns.Looks and ns.Looks.Init)
    Start("waypoint import", ns.Import and ns.Import.Init)
    Start("teleports", ns.Teleports and ns.Teleports.Init)
    Start("feedback", ns.Feedback and ns.Feedback.Init)
    Start("drawn roads", ns.Record and ns.Record.Prune)
    Start("pins", ns.Pins and ns.Pins.Init)
    -- (GatherMate2 installed: its data checked once a startup, a few seconds in and in slices, for the map menu's
    -- Import From GatherMate2 glow; Layers' L.GM2OnLogin)
    Start("GatherMate2 check", ns.Layers and ns.Layers.GM2OnLogin)
    Start("options", ns.Options and ns.Options.Init)
    Start("seamless map", ns.Atlas and ns.Atlas.Init)
    Start("tutorial", ns.Tutorial and ns.Tutorial.Init)
    Start("setup", ns.Setup and ns.Setup.Init)
    Start("whatsnew", ns.WhatsNew and ns.WhatsNew.Init)
    -- (how full the saved file is, a few seconds in: the counting off the login's own frame)
    Start("saved data", function() C_Timer.After(5, function() pcall(ns.SavedNotice) end) end)
    -- (a player from before 1.2.2, the arrow locked: asked once whether to unlock it, Arrow's A.OfferUnlock)
    Start("arrow unlock offer", function()
      if ns.Arrow and ns.Arrow.OfferUnlock then
        C_Timer.After(ns.Arrow.UNLOCK_OFFER_WAIT, function() pcall(ns.Arrow.OfferUnlock) end)
      end
    end)
    if InCombatLockdown() then CombatChanged(true) end -- logged in (or reloaded) mid-fight
    ns.started = true
    for _, fn in ipairs(extenders) do Start("extension", function() fn(ns) end) end
    extenders = {}
    Print(L["loaded. /agps for options, /agps help for commands."])
  elseif event == "PLAYER_REGEN_DISABLED" then
    CombatChanged(true)
    if ns.settings and ns.settings.combatProbe then
      C_Timer.After(1, function()
        if InCombatLockdown() then ns.RunProbe("combat") end
      end)
    end
  elseif event == "PLAYER_REGEN_ENABLED" then
    CombatChanged(false)
  elseif event == "UI_SCALE_CHANGED" or event == "DISPLAY_SIZE_CHANGED" then
    ns.FitPortraits() -- (the portraits' pixels changed)
    if ns.GPS and ns.GPS.ApplySettings then ns.GPS.ApplySettings() end -- (the map's size fitted to the screen again)
  end
end)
if ns.TimeScript then ns.TimeScript(ev, "OnEvent", "events (core)") end
