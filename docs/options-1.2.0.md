# The options, reorganized for 1.2.0

Asked 2026-11-10: "look at all the options in every menu and do an overhaul on the organization of options to be as
intuitive as possible." This is the inventory (before), the new layout (after) and why. No setting was renamed and no
default changed: only where an option is, what it sits next to, and a few labels. Saved settings work untouched.

`app/tests/test_options.py` holds the same lists and fails if an option is lost, doubled, or put on another page.

> **Changed 2026-11-10** (asked: "4 different map pages... maybe reduce to 2"): the map's pages are three now. **Map** also has the Minimap page's "Replace the minimap" options and the world map option; **Map icons** (the page called "Show on the map" below, id `Layers`) also has what the Minimap page put on the game's own minimap (its button, the route, the icons, the shape); **Map window** is as below without the world map option. The id `Minimap` opens Map. General has an **Apply (Reload UI)** button under the language while the one picked isn't the one loaded. The rest of this file is the layout as first built.

## In short

- **12 pages instead of 10**, named for what a player is doing: General, Map, Show on the map, Minimap, Map window,
  Opacity and combat, Routing, Directions, Quick buttons, Performance, Tools, Help.
- **34 of the 89 options moved to another page**; the other 55 stayed on their page (some in a new order). Nothing was
  removed.
- **3 new pages**: Show on the map (the old Map page's layer list), Minimap (everything about the minimap, from three
  pages), Help (new; the old Help improve page is its lower half).
- **2 pages renamed**: Window is now Map window (it gained the position, size and frame options from General);
  Opacity is now Opacity and combat (its content always was both).
- **1 label fixed** to sentence case: "Show Only Explored Areas" is "Show only explored areas".
- **4 settings got a control** that had none on an options page: the language, city locations, show the roads, show
  the walls.
- **24 options gray out while the option they depend on is off** (9 did before), the closest ones indented under
  their parent.
- Every old page id still opens a page (`O.ShowPage("Help improve")` opens Help).

## Why this shape

The old pages grew feature by feature. General held the map window's size next to the save reminder; Map held the map
style, thirteen layers, three options for the game's minimap and the four for the minimap replacement, about two
screens long; the minimap button was on General, the route on the minimap on Map.

The new pages follow the questions a player has:

| A player wants to... | Page |
|---|---|
| show or hide the map, bind a key, pick units or language | General |
| change how the map looks and moves (style, heading-up, zoom) | Map |
| pick what's drawn on the map | Show on the map |
| do anything with the minimap | Minimap |
| move, size, frame or decorate the map window | Map window |
| make the map see-through, or get it out of the way in a fight | Opacity and combat |
| change how routes are worked out | Routing |
| set up the arrow and the directions | Directions |
| arrange the map's buttons | Quick buttons |
| lighten the load on a slow PC | Performance |
| fix roads and walls, make pins | Tools |
| find out what's new, replay the tutorial, get help, share map data | Help |

Choices made on the way, and why:

- **Show on the map is its own page**, not part of Map: thirteen checkboxes fill a screen, and "what's shown" is the
  most common reason to open the options after the first day.
- **Minimap is its own page**: the replacement and its three dependent options, the minimap button, the route and
  icons on the game's minimap and the minimap's shape were on three pages.
- **The map window's frame colors stay with the frame**, on Map window, below position and size. The charm (it hangs
  from the frame's logo) and the arrival celebration follow, last: decorations, fine below the fold.
- **Route color moved to Map**, next to the map style: it's how the map looks, not the window.
- **Opacity and combat keeps hiding in combat and click-through** with opacity. One page for "the map is in my way".
- **Stops routed and drawn ahead stays on Performance only** (asked earlier: not on Routing too).
- **Questing objective tracker stays on Directions** (moved there 2026-10-16), now under its own "Quests" header.
- **Routing's long list of zeppelins, boats and the tram is last** on its page; sharing options moved above it.
- **Tools is second to last**: road and wall tools are for the few who fix map data. Pins stay there with them.
- **Performance sits after the everyday pages**; it was second.
- A search box wasn't added.

### Pages that scroll

The window is 560 units tall at every UI scale (the game's UI is 768 units high at scale 1 and about 670 at the
largest scale), which leaves a page 480.
A longer page scrolls, with a scroll bar only then. Measured with the test stand-in's text sizes:

| Page | Height | Fits |
|---|---|---|
| General | 450 | yes |
| Map | 386 (about 450 in game: two notes wrap) | yes |
| Show on the map | 438 | yes |
| Minimap | 402 | yes |
| Map window | 726 | scrolls: the charm and the celebration are below the fold |
| Opacity and combat | 462 | yes |
| Routing | 814 with a Horde character's rides | scrolls: the rides list is below the fold |
| Directions | 698 | scrolls: only "How it works" and Quests are below the fold |
| Quick buttons | 370 | yes |
| Performance | 530 (more in game: notes wrap) | scrolls, as before |
| Tools | 564 (more in game) | scrolls, as before |
| Help | 668 without tutorial sections | scrolls: what's new and the tutorial are on top |

A language with longer words wraps more notes, so a page near 480 may scroll a little there.

## After: every page

`>` marks a dependent option (indented; gray while the option in brackets is off). Keys are in `ns.DEFAULTS.gps`
(Core.lua) unless noted.

### General (id `General`)

| Section | Option | Setting | What it does |
|---|---|---|---|
| Map | Show the map | `shown` | The GPS map window |
| Map | Show/hide key | the game's key binding `AZEROTHGPS_TOGGLE` | Click, press a key |
| Map | > Key doesn't show the map in combat | `keyBlockedInCombat` | A press mid-fight can't pop the map up |
| Distances | Show distances in | `distanceUnits` | Yards, metric or imperial |
| Language | Show AzerothGPS in (**new**) | `AzerothGPSDB.language` | The game's language or one of eleven; after a /reload |
| Saving | Remind me to save | `askToSave` | The map's Save and Dismiss buttons |
| Search | Find NPCs met in several places | `searchCommonNpcs` | Guards and suppliers in the search too |

### Map (id `Map`)

| Section | Option | Setting | What it does |
|---|---|---|---|
| (top) | Map style | `style` | OpenMap, Terrain, World Map, No Spoiler Map |
| (top) | > Show only explored areas [OpenMap style] | `seamExploredOnly` | Zone art only where the character has been |
| (top) | > Terrain to zone map [OpenMap style] | `seamTerrainYd` | How far out the terrain gives way to the zone map (yards at the reference size; unset: the shipped 305 yd) |
| (top) | > Terrain transition [OpenMap style] | `seamTerrainBlend` | How long the terrain's blend into the zone map is, times the shipped (0 to 3; 0: a sharp switch; default 1) |
| (top) | > Zone map to continent map [OpenMap style] | `seamContinentAt` | How far out the zone map fades into the continent map: the art's own fade, in notches from the shipped 6,082 yd (-4 to 6, never closer than the terrain's end; default 0) |
| (top) | > Zone map transition [OpenMap style] | `seamContinentBlend` | How long that fade is, times the shipped (0 to 3; default 1) |
| (top) | > Continent map to world map [OpenMap style] | `seamWorldAt` | How far out the continent map fades into the whole world, in notches from the shipped 12,163 yd (-6 to 3, never closer than the zone map's fade; default 0) |
| (top) | > Continent map transition [OpenMap style] | `seamWorldBlend` | How long that fade is, times the shipped (0 to 3; default 1) |
| (top) | > Reset to defaults [OpenMap style] | | All six back to the shipped stages |
| (top) | Route color | `routeColor` | Blue or rainbow |
| View | Turn the map with me | `rotate` | Heading-up or north-up |
| View | Zoom in near a stop | `approachZoom` | Zooms in within 50 yards of the next stop |
| View | Reopen following me | `reopenFollow` | Hidden while looking around: opens on you |
| View | Right-click opens the world map | `terrainZoomOut` | Right-click zooms out or shows Azeroth |
| View | Building interiors | `interiors` | A building's own map inside it |

### Show on the map (id `Layers`)

| Option | Setting |
|---|---|
| Quests | `layerQuests` |
| > Quest areas [Quests] | `layerQuestAreas` |
| Flight masters | `poiTaxi` |
| Points of interest | `poiPoi` |
| Place names | `poiLabels` |
| City locations (**new here**; only the Quick buttons page's "On" box before) | `layerCity` |
| Dungeons and raids | `layerInstances` |
| Cave entrances | `layerCaves` |
| Herbs | `layerHerbs` |
| Ore | `layerOre` |
| Pins | `showCustomPins` |
| Show other addons' map icons | `otherAddonPins` |
| Party members | `showParty` |

### Minimap (id `Minimap`)

| Section | Option | Setting | What it does |
|---|---|---|---|
| (top) | Replace the minimap with the GPS map | `replaceMinimap` | The GPS map as a square in the minimap's corner |
| (top) | > Minimap size [Replace] | `replaceMinimapSize` | Small, medium, large |
| (top) | > Back to the minimap when you move [Replace] | `replaceMinimapCollapseOnMove` | The opened map closes as you move |
| (top) | > Back to the minimap when combat starts [Replace] | `replaceMinimapCollapseOnCombat` | ... or as a fight starts |
| On the game's minimap | Minimap button | `minimap.hide` (beside `gps`) | The AzerothGPS button |
| On the game's minimap | Route on the minimap | `minimapRoute` | The route drawn on the game's minimap |
| On the game's minimap | Icons on the minimap | `minimapIcons` | The map's icons there too |
| On the game's minimap | Minimap shape | `minimapShape` | Automatic, round, square |

### Map window (id `Window`)

| Section | Option | Setting | What it does |
|---|---|---|---|
| (top) | Show the GPS map in the game's world map | `useWorldMap` | The map in the game's world map window (M), not a window of its own; the key and the square's logo open it |
| Position and size | Lock map position | `locked` | Can't be dragged |
| Position and size | Size (Height and Width with Any shape) | `size`, `width` | The window's size |
| Position and size | Resize from the corner [not locked] | `lockSize` | Drag the bottom-right corner |
| Position and size | > Any shape [Resize from the corner] | `freeSize` | Width and height apart |
| Frame and buttons | Window frame | `windowFrame` | Title bar, logo, close button |
| Frame and buttons | Frame color [Window frame] | `windowTint` | The frame's tint |
| Frame and buttons | Close button (X) [Window frame] | `windowClose` | The X's color |
| Frame and buttons | Buttons | `windowButtons` | The map's buttons' color |
| Charm | Charm [Window frame] | `charm` | A weapon hanging from the logo |
| Charm | > Swings while you move [a charm picked] | `charmSwing` | It swings or hangs still |
| Arriving | Celebration, Try It | `arrivalEffect` | Confetti, fireworks or none |

### Opacity and combat (id `Opacity`)

| Section | Option | Setting |
|---|---|---|
| Map | Map opacity | `alpha` |
| Map | Fade the map while moving | `fadeMoving` |
| Map | Map opacity while moving [Fade] | `movingAlpha` |
| In combat | Hide the map | `combatHideMap` |
| In combat | Map opacity in combat [not hidden] | `combatAlpha` |
| In combat | Hide the direction arrow | `combatHideArrow` |
| In combat | Arrow opacity in combat [not hidden] | `arrowCombatAlpha` |
| Click-through | Click-through while moving | `clickThroughMoving` |
| Click-through | Click-through in combat | `clickThroughCombat` |

### Routing (id `Routing`)

| Section | Option | Setting |
|---|---|---|
| Routes | Use flight paths | `useFlights` |
| Routes | Use hearthstone | `useHearthstone` |
| Routes | Use class teleports and teleport items | `useTeleports` |
| Routes | Avoid zones too high for your level | `avoidHighZones` |
| Routes | Avoid the other faction's towns | `avoidHostile` |
| Routes | Road tolerance | `roadTolerance` |
| Stops | Visit stops in the fastest order | `fastestOrder` |
| Stops | > Except in cities [fastest order] | `cityKeepOrder` |
| Stops | Quest route: only this zone | `questZoneOnly` |
| Stops | X on the route panel cancels the route | `navCloseClears` |
| Waypoints and sharing | Accept TomTom /way commands | `acceptWay` |
| Waypoints and sharing | Map pin links add stops | `acceptMapPins` |
| Waypoints and sharing | Accept routes shared by players | `acceptShared` |
| Waypoints and sharing | Import and Share... (button) | opens the window |
| Zeppelins, boats and the tram | a checkbox per ride of your faction | `ridesOff[id]` |

The RestedXP, Zygor, Questie and TomTom tie-ins have no settings of their own beyond "Accept TomTom /way commands":
RestedXP Route and Zygor Route are quick buttons.

### Directions (id `Directions`)

| Section | Option | Setting |
|---|---|---|
| Direction arrow | Show direction arrow | `arrow` |
| Direction arrow | > Lock arrow position [arrow] | `arrowLocked` |
| Direction arrow | Arrow size [arrow] | `arrowPx` |
| Direction arrow | Arrow background [arrow] | `arrowBg` |
| Directions panel | Show the directions [arrow] | `dirShown` |
| Directions panel | > Lock directions text position [directions] (1.3.9) | `dirLocked` |
| Directions panel | > List the stops only [directions] | `dirStopsOnly` |
| Directions panel | > Snap the arrow to the directions [directions] | `arrowSnap` |
| Directions panel | > > Arrow side [snapped] | `arrowSide` |
| Directions panel | Text size [directions] | `dirTextScale` |
| Directions panel | Directions background [directions] | `dirBg` |
| Quests | Questing objective tracker | `questing` |
| How it works | five notes | |

### Quick buttons (id `Quick buttons`), unchanged

The table of where each map button goes (always shown or in the menu, up or right, or hidden: `quick[id]`), its order
(`quickOrder`), and an "On" box for the two buttons that are a setting themselves (Use Hearthstone, City Locations):
those two also have their own checkbox on Routing and Show on the map.

### Performance (id `Performance`), unchanged

Use Low-End Settings, Restore Defaults; Map redraws per second (`hz`); Work out a route you've left at most every
(`rerouteSeconds`); Stops routed and drawn ahead (`stopsAhead`); Gentle background work (`gentleBackground`); Turn the
arrow every frame (`arrowHz`).

### Tools (id `Tools`)

| Section | Option | Setting |
|---|---|---|
| Roads | Road tools button on the map | `devTools` |
| Roads | Road Tools On/Off (button) | |
| Roads | Suggest Record when drawing roads | `recordHint` |
| Roads | Show the roads on the map (**new**; `/agps roads` before) | `showRoads` |
| Walls | Wall tools button on the map | `wallTools` |
| Walls | Wall Tools On/Off (button) | |
| Walls | Show the walls on the map (**new**; `/agps walls` before) | `showWalls` |
| Both tools | Shift-click drawing (1.3.0) | `toolShiftClick` |
| Pins | Pinning | `pinning` |
| Your changes | Take Back the Last, List Your Changes (buttons) | |

### Help (id `Help`; `Help improve` opens it too)

| Section | What's there |
|---|---|
| What's new in 1.2.0 | Five lines from the changelog (`O.WHATS_NEW`) |
| Tutorial | Shown once something registers a section (`O.RegisterHelpSection`): the tutorial's replay list goes here |
| Commands and links | Show Commands (prints `/agps help`); the website and Discord addresses to copy |
| Help improve AzerothGPS | What's waiting to be shared; How to share..., Copy Map Data... |
| What Copy Map Data... includes | Roads, Walls, Routes, Pins (`copyRoads`, `copyWalls`, `copyRoutes`, `copyPins`) |
| Thanks | The OpenMap credit and its address |

## Before: every page (1.1.17 plus 1.2.0's merged features)

| Page | Section | Options (setting) | Now on |
|---|---|---|---|
| General | Map window | Show the map (`shown`) | General |
| General | Map window | Lock map position (`locked`), Window frame (`windowFrame`), Size and Width (`size`, `width`), Resize from the corner (`lockSize`), Any shape (`freeSize`) | Map window |
| General | Map window | Reopen following me (`reopenFollow`), Zoom in near a stop (`approachZoom`), Turn the map with me (`rotate`) | Map |
| General | Map window | Show/hide key, Key doesn't show the map in combat (`keyBlockedInCombat`) | General |
| General | Distances | Show distances in (`distanceUnits`) | General |
| General | Minimap | Minimap button (`minimap.hide`) | Minimap |
| General | Saving | Remind me to save (`askToSave`) | General |
| General | Search | Find NPCs met in several places (`searchCommonNpcs`) | General |
| Performance | all | `hz`, `rerouteSeconds`, `stopsAhead`, `gentleBackground`, `arrowHz` | Performance |
| Opacity | Map | `alpha`, `fadeMoving`, `movingAlpha` | Opacity and combat |
| Opacity | Click-through | `clickThroughMoving`, `clickThroughCombat` | Opacity and combat |
| Opacity | In combat | `combatHideMap`, `combatAlpha`, `combatHideArrow`, `arrowCombatAlpha` | Opacity and combat |
| Routing | Routes | `avoidHighZones`, `useFlights`, `questZoneOnly`, `useHearthstone`, `useTeleports`, `avoidHostile`, `roadTolerance`, `fastestOrder`, `cityKeepOrder`, `navCloseClears` | Routing |
| Routing | Zeppelins, boats and the tram | a checkbox per ride | Routing |
| Routing | Waypoints and sharing | `acceptWay`, `acceptMapPins`, `acceptShared`, Import and Share... | Routing |
| Directions | Direction arrow | `arrow`, `arrowLocked`, `questing`, `arrowPx`, `arrowBg` | Directions |
| Directions | Directions panel | `dirShown`, `dirStopsOnly`, `dirTextScale`, `dirBg`, `arrowSnap`, `arrowSide` | Directions |
| Map | Map | Right-click opens the world map (`terrainZoomOut`), Building interiors (`interiors`), Map style (`style`), Show Only Explored Areas (`seamExploredOnly`) | Map |
| Map | Show on the map | `poiTaxi`, `poiPoi`, `poiLabels`, `layerQuests`, `showParty`, `layerQuestAreas`, `layerHerbs`, `layerOre`, `layerInstances`, `layerCaves`, `showCustomPins`, `otherAddonPins` | Show on the map |
| Map | Show on the map | Route on the minimap (`minimapRoute`), Icons on the minimap (`minimapIcons`), Minimap shape (`minimapShape`) | Minimap |
| Map | Minimap | `replaceMinimap`, `replaceMinimapCollapseOnMove`, `replaceMinimapCollapseOnCombat`, `replaceMinimapSize` | Minimap |
| Window | Window frame | `windowTint`, `windowButtons`, `windowClose` | Map window |
| Window | Route | Route color (`routeColor`) | Map |
| Window | Arriving, Charm | `arrivalEffect`, `charm`, `charmSwing` | Map window |
| Quick buttons | Where each one goes | `quick`, `quickOrder`, "On" for Use Hearthstone and City Locations | Quick buttons |
| Tools | Roads, Walls, Pins, Your changes | `devTools`, `recordHint`, `wallTools`, `pinning` | Tools |
| Help improve | all | How to share..., Copy Map Data..., `copyRoads`, `copyWalls`, `copyRoutes`, `copyPins`, Thanks | Help |

Two pieces of text went: the long note under the Show/hide key (its tooltip says the same), and the Window page's
header note that pointed at General.

## Settings with only a slash command

| Command | Setting | Now |
|---|---|---|
| `/agps language` | `AzerothGPSDB.language` | General > Language (**new control**) |
| `/agps roads on\|off` | `showRoads` | Tools > Roads (**new control**) |
| `/agps walls on\|off` | `showWalls` | Tools > Walls (**new control**) |
| (the City Locations quick button) | `layerCity` | Show on the map (**new control**) |
| `/agps replace ground\|mask` | `replaceMinimapHide` | Slash only: a workaround for how the minimap's ground is hidden, not a preference |
| `/agps dungeonroute on\|off` | `dungeonRoute` | Slash only: this client hides your position in dungeons, so the route it starts can't work |
| `/agps zoom`, `lookat`, `follow` | `zoom`, the view | Slash only: the mouse wheel and the recenter button do it |
| `/agps debug ...`, `/agps status`, `/agps seamless check\|spots` | `combatProbe`, none | Slash only: diagnostics |

The other commands (`show`, `hide`, `opacity`, `size`, `rotate`, `style`, `arrow`, `poi`, `quests`, `herbs`, `ore`,
`instances`, `caves`, `lock`, `minimap`, `replace on|off|small|medium|large`, `dev`, `walltools`, `draw`, `reset`)
set options that have a control.

## Controls outside the options window

Left as they are; listed so the whole picture is in one place.

| Where | Control | Setting or effect |
|---|---|---|
| Map window | Logo: double-click, right-click, drag | Minimize (`minimized`), open the options, move (`point`) |
| Map window | Close X, title bar drag, Move tab, Shift + drag | `shown`, `point` |
| Map window | Bottom-right corner drag | `size`, `width` |
| Map window | Mouse wheel, right-click, recenter button | `zoom`, the view |
| Map window | Map Menu button (bottom-left) | Opens the quick buttons' menu |
| Quick buttons | Search Places, Quest Route, RestedXP Route, Zygor Route, Boss Route, Draw a Farming Area | Actions |
| Quick buttons | Map Style group | `style` |
| Quick buttons | Quests, Quest Areas, Herbs, Ore, City Locations, Caves, Dungeons and Raids, Use Hearthstone | The same settings as their checkboxes |
| Quick buttons | Find Herbs and Ore | `nodeFilter` (which herbs and veins show) |
| Quick buttons | Road Tools, Wall Tools, Show Roads and Walls, Undo, Stairs, Record | The tools (shown with `devTools` / `wallTools`); `showRoads`, `showWalls` |
| Route panel | - / + and + | `stepsCollapsed`, `stepsAll` |
| Route panel | X | Cancels the route or closes the panel (`navCloseClears`) |
| Route panel | Clear Route / Confirm Route, Save, Dismiss, Share, Use (hearthstone, teleport) | Actions |
| On the map | Double-click: a stop. Shift + click: Create Pin (`pinning`). Ctrl + click: the map pin | |
| On the map | Right-click a dock: use it or not (`ridesOff`); a pin: remove; a boss: mark dead; a stop: remove | |
| Dungeon map | Path Color picker, floor + / - | `dungeonPathColor` |
| Minimap square | Logo button: open or close the map; right-click: options | |
| Arrow and directions | Drag, corner resize, drop the arrow on a side | `dirPoint`, `dirSize`, `arrowSnap`, `arrowSide` |
| Record window | Record, Pause, Stop, Stairs Start / End, Undo; the Record: Stairs key | Drawn roads |
| Import and Share window | Copy Route as /way, link to a player or the group, Copy My Map Data (what to include), Import (add to the route; /way as nodes or NPCs) | Nothing saved |
| Create Pin window | Name, icon, floor | The pin |
| Record hint popup | Don't ask again | `recordHint` |

Companion addons add their own pages after these through `AzerothGPS.AddOptionsPage`, each under a section named
after the addon. Those are untouched.

## For the code

- Pages: `Page(L["Shown name"], nil, "Id")` in Options.lua's `BuildWindow`. `O.pages[id]` is
  `{ index, scroll, child }`. `O.PAGE_ALIASES` maps an old id to the page it's on now.
- `Key("setting")` before a control lists it in `O.settingControls` (`{ key, page, control, mirror }`).
- `check(label, tip, get, set, enabled, indent)`, `slider(..., enabled, tip)`, `Choice(..., enabled, indent)`,
  `Dropdown(..., enabled)`: `enabled` is a function; the control is gray while it returns false (`control.agpsOn`).
  `INDENT` (20) puts a dependent option under its parent.
- **Help's tutorial hook**: `ns.Options.RegisterHelpSection(id, build)`. `build(ui)` gets the helpers a companion's
  page gets (`ui.header`, `note`, `check`, `slider`, `button`, `choice`, `dropdown`, `text`, `place`, and `ui.page`,
  the section's own frame). Call it when your file loads or any time later; the same `id` again builds the section
  again (a list that changed). Sections show under the "Tutorial" header, in the order first registered; the header
  is hidden while there's none. `ns.Options.HelpHost()` returns the host frame and the Help page's frame.
