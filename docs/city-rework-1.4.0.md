# City routing rework (1.4.0): layered walk grids and the height band

Status: **being tested** on branch `feat/city-grid-1.4.0` (draft PR, not for merging before 1.4.0 is decided). Behind
Options > Routing "City routing: new (test)" (off by default) and `/agps citygrid on|off`. With it off nothing
changes: the grid is never asked (`test_with_the_option_off_the_grid_is_never_asked`, route-quality against main).

## Why

Inside the capitals AzerothGPS routes along roads traced from the city models' floor faces (`Data/Capitals.lua`,
`Data/Cities.lua`, `Data/Indoors.lua`). Over wide floors the traced skeleton is a web, so routes zig-zag (issue #829:
"Org and UC are full of zigzag road paths"), a stop off the roads gets a dotted line through walls, and the player's
floor (the game gives no height: `UnitPosition`'s z is always 0) is a guess made along those roads (`Nav.TrackCityZ`).

The idea (the general approach Shortest Path Forever also takes; **none of its code or data is used**, everything
here is our own): a per-city grid of every walkable surface with heights, searched with A* and drawn string-pulled,
and the player's floor narrowed down by range checks against NPCs at known spots.

## 1. The grid (`Data/CityGrid.lua`, `agps city-grid`, `app/azerothgps/citygrid.py`)

Baked offline from **our own** Recast meshes of each city (`recastmesh.py`, `agps navmesh build`; the meshes are
dev data in `data/navmesh/*.pkl` and never ship). Only numbers ship: heights, link bits, road-link points.

- **Cells:** a square grid. Every walkable mesh poly touching a cell gives it a *surface* at the poly's height there
  (the cell's middle, or the poly's point nearest it inside the cell). Floors over floors are separate surfaces of one
  cell (Undercity's rings, the Drag over the Cleft of Shadow, halls over streets). Surfaces within 2 yd of each other
  from joined polys are one. Each keeps its point's spot in the cell (8 x 8 steps), so lines through doors keep to them.
- **Links:** a surface links to one surface in each of its 8 neighbor cells where the mesh joins them (the same poly,
  or polys at most 2 links apart: Recast's polys never join across a wall) and the climb fits a 55 degree slope plus a
  1 yd step. Diagonals only where a square way round is linked too (no corner cut through a wall's end). Each link
  belongs to its surface, so one-way links are possible.
- **Road links (the hybrid):** the mesh comes in pieces where the city's own roads still go (stairs taller than
  Recast's 1 yd climb, bank counters, bridge decks, Undercity's canal walkways and the drops the roads have). Every city
  road of the Router's graph (drawn roads included) is walked every yard at its height; where it leaves the grid and
  comes back, and the grid has no way between those two surfaces within 1.3 x the road's yards + 6, the road's stretch
  becomes a link (its points kept every 4 yd, costing 1.5 x its yards so the grid's own walk comes first; a drop
  one way). Thunder Bluff's lifts (Data/Capitals.lua's source 5 roads) are links the same way: the stretch up the
  shaft (10 yd of climb or more, `LIFT_RISE`) is `KIND_LIFT` and costs the Router's own yards for it (the wait and the
  ride, `capitals.LIFT_SECONDS`), so routes ride them up and down and never walk off a mesa's edge (the mesh has no
  way down the cliffs). Undercity's lifts are rides between levels, handled by the planner as before; so are
  Ironforge's tram and Darnassus's teleporter (the grid walks from their ends).
- **Counters:** an NPC's floor the grid has no way onto (Darnassus's bankers behind their round counter; no road
  goes in) is joined to the city's floor round it, within 4 yd across and 2 yd in height, by a road link each way
  from each side (the nearest in each eighth round it, 10 yd dearer than its yards: never a way through).
- **What's kept:** a capital's own cells (`Passability.Overlay`) plus 30 yd round them (its gates' ground); only
  surfaces within 30 yd across and 8 yd in height of a city road or an NPC's spot (`Data/NpcFloors.lua`; Darnassus and Ironforge 16
  yd, `near_z`: their ramps and spiral stairs climb 20-30 yd between the roads' floors, the Temple of the Moon's
  balcony, the Cenarion Enclave's treetops, the Mystic Ward's balcony, and at 8 their middles were cut out; neither has
  land under the city, and Ironforge's mountain top is far over it). Recast also
  walks the land *under* a city's model where the model stands clear of it (Orgrimmar's east half had a flat floor at 9
  under streets at 20-70, joined to the land at the model's edges), and roofs, wall tops and the canyon's rims; none of
  that is ground a player reaches. Then only the grid's pieces the roads or NPCs touch (60 surfaces or more, or joined
  by a road link).
- **Format:** per city `{ cont, level, whole, cell, x0, y0, w, h, zmin, zq, offs, block, n, mesh, bake, cells, s, base,
  links }`: `cells` one character a cell (its count of surfaces), `s` 7 characters a surface (height in 0.25 yd steps,
  its point in the cell, 4 characters of links: two directions a character, 3 bits each), `base` the first surface of
  every 32 cells (so a cell's surfaces are found by a short count), `links` the road links as numbers. Read in place
  (character by character: `string.byte`), never unpacked into tables: the memory is the strings.
- **Staleness:** the file carries each mesh's hash and the bake parameters' hash; `test_city_grid.py` fails when the
  parameters change without a new bake, and (where the meshes are, not on CI) when a mesh was rebuilt since.

Size per city (cell size chosen per city; compared with `agps city-grid --cells 2,3,4`):

| city | cell | surfaces | cells with a surface | cells with floors over floors | road links | bytes in the file |
|---|---|---|---|---|---|---|
| Orgrimmar | 3 yd | 44,072 | 30,867 | 9,130 | 386 | 466 KB |
| Stormwind | 3 yd | 41,776 | 32,142 | 7,703 | 457 | 423 KB |
| Undercity | 2 yd | 59,920 | 37,017 | 16,455 | 862 | 582 KB |
| Ironforge | 3 yd | 20,909 | 16,054 | 3,785 | 128 | 197 KB |
| Thunder Bluff | 2 yd | 38,136 | 30,546 | 5,906 | 473 (10 of them lifts) | 416 KB |
| Darnassus | 3 yd | 54,896 | 36,834 | 12,184 | 1,151 | 535 KB |
| **all** | | | | | | **2.62 MB** (1.47 MB for the first three; Data/Cities.lua and Capitals.lua together are 0.87 MB) |

Cell size: at 2 yd Orgrimmar and Stormwind are 2-2.2 times the surfaces (and search time) for little gain on their
wide streets; Undercity's walkways and doors are narrow (3-4 yd), so it keeps 2 yd. 4 yd breaks narrow doors.
Ironforge's halls are wide (2 yd: 40,525 surfaces, 388 KB, for nothing the checks found). Thunder Bluff keeps 2 yd: at
3 (221 KB) its rope bridges and the Pools of Vision's tunnel came out narrower than a cell, the Mage Trainer's route
ended 25 yd off its floor and three gate trips came out longer. Darnassus at 2 yd is 1.02 MB (110,418 surfaces) for
the same checks to within 2% (its streets and terraces are wide; its spiral stairs are walked at 3 too).
See "Cell sizes" below for the full comparison.

## 2. The search (`CityGrid.lua`)

- **Where:** a leg with both ends in one city's grid (a capital's own cells, `Router.CapitalAt`; Undercity's level
  10001; Darnassus: any spot over a floor of its grid, `whole = true`, as the Cenarion Enclave's treetops are outside
  the capital's cells). A leg with one end in the city: the Router's own route outside, cut where it first comes into
  the city's grid (walked every 2 yd), the grid's walk from there (the gates' roads join as before; the join's height
  the grid floor's, not the road's). Legs elsewhere, legs between two
  cities, and anything the grid can't walk (Stormwind's Wizard's Sanctum up its portal): the Router's own, unchanged.
- **A\*:** over surfaces, 8 directions, costs the 3D step plus 0.5 per yard climbed (the flatter way when about as
  short), road links at their cost; heuristic the straight distance. Ends: the surfaces at the spot (within 2 cells when
  the spot is against a wall), those within 4 yd of the spot's height when it has one (the player's floor, a stop's
  NPC height), else the nearest, dearer by 6 a yard. Several start or goal surfaces are searched at once.
- **Frame budget:** the search runs in the Router's background work (`Router.Background`, a pause every 150 nodes and
  by the slice's clock), never in the frame: meanwhile the leg is the Router's own marked `pending`, and the route is
  worked out again when the search is done (`test_the_search_runs_in_short_slices_in_the_background`). Searches are
  kept (24), and a reroute from a few yards on joins the route found (25 yd, the grid walks the straight line onto it)
  without a new search.
- **String-pulling:** from each point, the farthest later step the grid walks straight to (cell to cell along the
  line, one axis at a time, always by a link, the line within 0.75 cell of each crossed surface's own point, 0.4 cell
  where that point isn't the cell's middle: the floor covers only that side of the cell, a corridor's edge; at 0.75
  a line along Ironforge's Tinker Town hall ran 15 yd past the floor's edge), a few
  past the first that fails (a corner). Road links keep their own points. Along each straight stretch the ground's
  heights are kept where they bend more than 1.5 yd from a straight climb (stairs, a ramp's foot), so the route's
  `zs` (Undercity) / `fz` (a capital) have every floor change: Turns says the stairs, the map draws the floors.
- **Kinds:** a grid walk is `KIND_OFFROAD` (Turns says its turns from 50 degrees, as on any walk; drawn dotted, as
  walks are), drops `KIND_DROP`, lifts `KIND_LIFT_*`.

## 3. The player's floor: walk connectivity and the height band

The game gives no height, so:

1. **The grid's surfaces under the player** (their cell, or the nearest within 2 cells). One: that's the floor.
2. **Walk connectivity:** a surface stays a candidate only while the grid has a way to it from the last candidates
   within 1.5 x the yards moved + 2 cells (`CG.TrackFloor`, every 0.2 s while moving). Walking from the Cleft of
   Shadow in under the Drag keeps the Cleft. A jump of 40 yd or more (a teleport) starts over.
3. **The height band:** the game checks ranges in 3D, so an NPC at a known single spawn bounds the player's height.
   In range R at d yards across: |z - zNPC| <= sqrt((R + 3 + 2)^2 - (d - 2)^2) (3 yd for the bodies' reach, 2 yd for the
   NPC standing off its spawn). Out of range: |z - zNPC| > sqrt(R^2 - (d + 2)^2) where d + 2 < R. Readings intersect
   into a band (a list of height intervals); the candidates outside it (1 yd slack) are dropped, unless that would
   drop them all (then the band is ignored: a wrong spawn).
4. **Nav's own following** (`Nav.TrackCityZ` along the roads) stays; when the grid knows the floor (one candidate) it
   sets Nav's followed floor to it, else Nav's floor picks among the candidates for a leg's start.

**Which units:** only units the player names themselves: `target`, `mouseover`, `softinteract`, `softfriend` and
`npc` (the NPC whose window is open). Nothing is targeted, clicked or cast by the addon. The NPC's identity: its
creature id from `UnitGUID` (checked with `ns.IsSecret`: secret, skipped), its spot the shipped spawn
(`Data/Npcs.lua`) within 60 yd of the player, only when no other spawn of it is within 40 yd of that one.

**Which checks** (this client's own API docs, Blizzard_APIDocumentationGenerated, read 2026-11-22):

| API | flags in the docs | used |
|---|---|---|
| `CheckInteractDistance(unit, i)` | `SecretArguments = "AllowedWhenUntainted"`; no secret returns, no `HasRestrictions` | yes: i = 2 (11.11 yd), 3 (9.9 yd), 4 (28 yd): every class has these; the docs give no yards, these are classic's |
| `C_Spell.IsSpellInRange(spell, unit)` | `SecretArguments = "AllowedWhenTainted"`, nilable result (nil: unknown spell or bad target) | yes, for a short list of class spells that can be cast on friendly NPCs (heals, buffs); range from `C_Spell.GetSpellInfo().maxRange`; nil skipped |
| `C_Item.IsItemInRange(item, unit)` | `SecretArguments = "AllowedWhenUntainted"`, nilable | yes, for bag items whose use spell has a range (`C_Item.GetItemSpell` + its spell's `maxRange`, looked at every 30 s) |
| `UnitInRange` | `SecretReturns = true` | no |
| `UnitDistanceSquared`, `C_Map.GetPlayerMapPosition` | group members only | no |
| `UnitGUID`, `UnitName`, `UnitCreatureID` | `SecretWhenUnitIdentityRestricted` | `UnitGUID` only, checked for secrecy (the NPC window code already reads it in cities) |

All are read-only queries the default UI makes for its own menus (`CheckInteractDistance` for the unit menu's trade and
duel buttons). The band is display only (the floor estimate, the route's start floor). **To confirm in game:** that the
checks are 3D (stand on a floor straight over or under an NPC: `/agps floor`), and the slack (3 + 2 yd).

## 4. Found floors, stairs, bridges, lifts and jumps (`navfeatures.py`)

Asked 2026-11-22 (Kooki3z: "detect stairs/bridges/floors automatically for route data ... When creating the city grid,
automatically determine bridges, stairs, lifts, etc."; and "consider marking jump spots too for directions, that would
show orange arrow and directions to jump"). `app/azerothgps/navfeatures.py` reads the grid and its mesh at the bake, with
the collision triangles and the models' liquids the mesh was built from (`agps navmesh tris`:
`data/navmesh/<city>_tris.npz`, dev data) to check every link it proposes at body height. Each thing it finds has a
confidence; only those at `USE_CONF` (0.75) or more change the data.

- **Floors:** the grid's surfaces joined by flat links (0.2 yd up a yard), pieces of 40 sq yd or more; a piece spanning
  over 4 yd in height is open ground. Stacked floors are separate pieces.
- **Stairs and ramps:** the non-floor surfaces between floors, climbing 3 yd or more at a stairs' slope, mostly one way;
  8 yd wide or less is stairs (a spiral where its ends are close for its length), wider a ramp. **Stairs only with
  risers** (2026-11-22, Kooki3z: "stairs up" on Orgrimmar's incline from Durotar): the collision's height up the flight,
  every 0.1 yd along it and 0.6 yd either side, must climb half its rise or more on faces steeper than a walk (risers),
  on two or more of them (`stepped`, `is_stairs`); a smooth slope is a ramp and is never said. The same test tags a road
  link as stairs. On a grid walk (`CG.InGrid`) Turns says only these stairs (`CG.StairAt`), never by the walk's slope
  (`T.STAIR_SLOPE` over `zs`: Undercity's grid walks had it).
- **Bridges and walkways:** decks 12 yd wide or less (an arched deck climbing up to 0.8 yd a yard is one deck), open on
  both sides at chest height (or a parapet with the drop right past it: Stormwind's canal bridges), with a drop, water or
  ground 3+ yd under their sides (a parapet lower than 3 yd; a passage's tall walls close it), nothing over them within
  15 yd at two of five probes round each cell (the models' ceilings too, `agps navmesh tris`: Stormwind's district gates'
  barrel vaults over the canals are no bridges), 8 yd long or more, joining two areas. On the grids' walks
  (city or world grid, a walk with heights) Turns says the bridge models and these decks, however short, from 8 yd
  before the deck found (its ramps: `T.FOUND_BRIDGE_LEAD`), and no longer the roads' walkway rule (`Router.BridgeAt`'s
  capital cells), which took Stormwind's covered gate passages for bridges and had no cells on the open canal bridges
  before them (Kooki3z 2026-11-22: "bridge detection was after the bridge not on it").
- **Lifts:** the known lifts (Thunder Bluff's lift roads, Undercity's three to the Ruins) found on the mesh: a floor at
  the foot and one at the top, no walk between. Their ride times stay the roads' and the transports'.
- **Jumps** (one way): down a ledge 3 to 14 yd (`SAFE_DROP`, Nav.FALL_FREE: never more), the polys within 2 yd across,
  nothing in the way at 0.5/1.2/1.8 yd over the floor, the fall clear, the landing not under a pool's or canal's liquid,
  and the grid's own way round more than 3 x its yards + 25 (else it's found, not a link). Each costs 10 yd over its
  own, so the walk down stays first where it's about as long. Across a gap of 1.5-3.5 yd at one height, open under it:
  found (0.7), not used yet.
- **Steps and seams the mesh lacks:** surfaces of neighbor cells with their polys 1 yd or less apart and nothing at body
  height between: a road link across one becomes straight (its points between dropped; its cost the road's).

In the bake (`citygrid.build`, `FEATURES`): the jumps become grid links (`KIND_DROP`); the city's road links are made
again over them (only where the grid still has no way), each tagged: a road one way and down 3 yd or more is a drop
(the roads' drops: "Jump down here", the arrow orange), a climb of 2 yd or more at a stairs' slope stairs (6), one
along a bridge found a bridge (8, `KIND_BRIDGE`; `KIND_JUMP` 9 for a jump across). The stairs and bridges found are the
city's `feat` lines ("kind,half width,x,y,z,..."): `CG.StairAt` and `CG.BridgeAt` (only with the option on) let Turns
say "Take the stairs up" and "Cross the bridge" on the grid's walks (kind 1, which never asked `Router.StairAt`), and
the map's stairs icon go on them. Debug output for Route Studio: `data/debug/navfeatures/<city>.json` (its "Found
floors, stairs, bridges, lifts, jumps" layer).

Found (2026-11-22; links at the confidence the bake uses):

| city | floors (ground) | stairs (spirals) / ramps | bridges | lifts | jumps found / links | road links (step found) | data |
|---|---|---|---|---|---|---|---|
| Orgrimmar | 257 (39) | 125 (2) / 34 | 9 of 11 | - | 496 / 170 | 386 -> 388 (21) | 465 -> 483 KB |
| Stormwind | 281 (11) | 102 (1) / 13 | 4 of 5 | - | 299 / 103 | 457 -> 463 (24) | 422 -> 435 KB |
| Undercity | 374 (17) | 97 / 19 | 33 | 3 of 3 (foot -41, top 56-63) | 869 / 437 | 862 -> 862 (46) | 581 -> 615 KB |
| Ironforge | 123 (5) | 80 (3) / 5 | 3 | - | 294 / 101 | 128 -> 128 (6) | 197 -> 209 KB |
| Thunder Bluff | 92 (9) | 32 / 9 | 15 of 16 | 2 of 2 (the lift roads) | 344 / 147 | 473 -> 471 (6) | 415 -> 429 KB |
| Darnassus | 289 (35) | 118 / 32 | 13 | - | 884 / 432 | 1151 -> 1159 (38) | 534 -> 572 KB |
| **all** | | | | | | | **2.62 -> 2.74 MB** (+5%: jump links 96 KB, `feat` 49 KB) |

The road links don't get fewer: most are doors and seams the triangles have something across at body height (door
frames, thresholds), which stay the roads'. Where the grid has a road link the roads' drops were plain one-way walks;
now 119 of them are drops ("Jump down here").

Checks (`agps city-grid --check`, against the bake before): all six 56 of 56 on the grid, none off the mesh past 3 yd,
none newly flagged; yards 148,120 -> 145,119 (Undercity 23,778 -> 22,491, Darnassus 24,576 -> 23,838); one trip 1.4 yd
longer (Orgrimmar, Sorek to Ur'kyo: no link of this change on it, the search's tie order). Gate trips: Undercity's 6,027
-> 4,214 yd (down the rings' ledges instead of round), two 1.7-2.4 yd longer (the same); Thunder Bluff's Mage Trainer
trip from Mulgore is now on the grid (it was the Router's own): 522 yd against 624, down two 6 yd ledges into the Pools
of Vision, ending 6.5 yd under the place's height (111, where the grid has no floor; flagged, as the doc's table says
for that place). `agps route-quality --against origin/feat/city-grid-1.4.0` with the option on (`AGPS_CITY_GRID=1`):
198 same, **2 better, 0 worse**, 0 lost.

Bridges against the old data: Thunder Bluff's long rope bridges (77-94 yd) are what `Router.BridgeAt` calls bridges too
(7 of its 15); the others are walkways at the lifts' feet. Stairs against the old stairs roads (source 6): Ironforge 7
of 8 have a flight found on them, Stormwind 5 of 12, Orgrimmar 4 of 15, Darnassus 2 of 19 (most of those are steps the
mesh lacks, which are the grid's stairs links and in `feat` too).

**Interiors trial** (`agps nav-features --interiors`: each building's own Recast mesh, 1 yd cells, against Data/Indoors.lua):

| building | floors found | Indoors.lua's floors (agree) | Indoors.lua's stairs roads on a flight found | flights found |
|---|---|---|---|---|
| Brill's inn | 27.9, 33.0, 37.8, 41.4, 50.7 | 27.5, 34.5, 41.5 (3 of 3) | 4 of 4 | 3 |
| Goldshire's inn | 50.4, 57.4, 60.3, 64.2, 73.4 | 49.5, 56.5, 60.5 (3 of 3) | 3 of 3 | 2 |
| Darkshire's town hall | 25.1, 28.3, 31.7 | 27.5 (1 of 1) | 0 of 2 | 0 |
| Sentinel Hill's tower | 56.4, 66.2, 68.9, 75.0, 85.0, 90.6, 96.3 | 56.5, 60.5, 66.5, 92.5 (3 of 4) | 5 of 7 | 6 |

The extra floors are roofs and landings (Brill's 50.7, Goldshire's 73.4: the roof; Sentinel Hill's tower its landings
between flights); Darkshire's town hall has two short steps (under 3 yd) the detector doesn't call stairs. Blackrock
Mountain wasn't tried (a cave of its own, not a building `buildings()` lists).

## Rollout

1. **1.4.0 test (this branch):** all six capitals behind the option, off by default (Ironforge, Thunder Bluff and
   Darnassus added 2026-11-22: Thunder Bluff's lifts as road links with their ride time, as the roads have them;
   Ironforge's tram and Darnassus's teleporter rides as before, the grid walking from their ends).
2. Kooki3z's tests (below), fixes; then the option on by default, the old road overlays kept as the fallback
   (anything the grid can't walk).
3. Buildings (`Data/Indoors.lua`) and caves later: the same bake over each model, a grid per building is small; the
   Router's attach code already splits a trip at a building's doors, which is where a grid would take over.
4. Once the grids carry the capitals, the capitals' traced roads can be thinned to the gate joins and the stairs the
   mesh lacks (less data, fewer zig-zags anywhere they're still drawn).

## Risks

- **The mesh is a second opinion.** It's built from the collision faces, but server-spawned doors, gates and lifts
  aren't in it, and doodads only where the ADTs place them. A door that's shut in game, a gate the mesh lacks: wrong.
  Drawn and recorded roads are the truth; they become road links where the grid lacks a way.
- **Thin walls and corners:** cells are 2-3 yd; a line can pass a little off the floor at a corner. The line check
  keeps within 0.75 cell of each surface's own point (0.4 at a floor's edge); `agps city-grid --check` walks every
  route over the mesh (see numbers): none of the 336 place-to-place trips has a run off it past 3 yd.
- **Ledges:** drops come from the roads' own drops and the jumps navfeatures.py finds (section 4: checked against the
  collision at body height, 14 yd at most); a wrong one would be a jump the game doesn't allow. To check in game.
- **The band** relies on the spawns being where the NPC stands (a wandering vendor) and on the 3D range check; a
  wrong band is ignored when it rules out every floor, and the walk connectivity still holds.
- **Memory:** 2.6 MB of strings for the six loaded with the addon (the data is read in place, no tables); a search's tables are
  dropped when it ends (up to 40,000 surfaces settled for the longest Undercity trips).
- **Line style:** grid walks are drawn dotted (a walk's kind) and Turns says "leave the road" at the gate where a
  route comes in from the land's roads. An open question below.

## Test plan

Automated (`app/tests/test_city_grid.py`, CI):
- the data's integrity and staleness stamps; the option off never asks the grid;
- Undercity from the Trade Quarter's ring (-43) to the Apothecarium (-85); Orgrimmar into the Cleft of Shadow under
  the Drag and back out; Grommash Hold (no road goes in); across Stormwind; a stop the grid can't reach (the Wizard's
  Sanctum) is the Router's own; a trip from Durotar into the Cleft cut in at the gate;
- Ironforge from the tram's end in Tinker Town to the inn on the halls' floor (never the mountain over them), and the
  whole trip from Stormwind by the tram; Thunder Bluff up a lift from Mulgore and down another from the Hunter Rise
  (no step off a mesa's edge, the lifts' cost the wait and the ride); Darnassus from the teleporter's end, the whole
  trip up from Rut'theran Village by it, up the Cenarion Enclave's spiral stairs to the Arch Druid and back, the
  bank's counter and the Temple of the Moon's balcony;
- every straight stretch of a route is one the grid walks; against the mesh (local only): no run off it past 3 yd;
- the band's math (in range, out of range, a shell, far across) and the floor picked by the band and by the walk under
  the Drag;
- the search in the background in slices under the frame budget (40 ms); a reroute a few yards on reuses the route.

Offline (`agps city-grid --check`, local: needs the meshes): 336 trips between 8 NPCs a city, each to each, grid
against the Router's own, each grid route walked over the mesh. `agps route-quality --against origin/main`: no trip
different with the option off; with it on (`AGPS_CITY_GRID=1`), the trips touching the cities listed separately.

## What Kooki3z should test in game

New files (`CityGrid.lua`, `Data/CityGrid.lua`): **relog** after installing, a /reload doesn't load new files.

1. `/agps citygrid on` (or Options > Routing > "City routing: new (test)"). `/agps citygrid stats` says how many legs
   went on the grid.
2. **Orgrimmar:** from the bank (Valley of Strength) to Zevrost in the Cleft of Shadow and back; to Thrall in
   Grommash Hold; up to Doras on the wind rider tower; the Valley of Spirits (Ur'kyo) to the Valley of Honor (Sorek).
   Look for: straight lines instead of zig-zags, no line through a wall or over a gap, "Take the stairs" where there
   are stairs, the arrow and the steps following while you walk (no snap back).
3. **Undercity:** the bat handler (Michael Garrett) to the Apothecarium (Faranell) at the bottom; the bank to the
   Magic Quarter's trainers; the Rogues' Quarter. Undercity's floors over floors are the hardest case.
4. **Stormwind:** the gryphon master to the cathedral, the Mage Quarter, Old Town (SI:7).
5. **Ironforge:** off the tram (from Stormwind) to the inn, the bank, the Mystic Ward and the Forlorn Cavern (Hulfdan
   Blackbeard). Look for: the route on the halls' floor, never over the mountain.
6. **Thunder Bluff:** from Mulgore up a lift to the inn; from the Hunter Rise over the rope bridges and down a lift
   ("Take the lift up/down"); to the Pools of Vision under the Spirit Rise (Archmage Shymm).
7. **Darnassus:** from Rut'theran Village by the teleporter to the inn; up the Cenarion Enclave's tree to Arch Druid
   Fandral Staghelm (the spiral stairs); to Tyrande on the Temple of the Moon's balcony; the bank's counter.
8. **Into a city from outside:** a stop in the Cleft of Shadow from the Durotar road: the route comes in by the
   gate on the roads and walks the grid from there.
9. **The floor:** stand on the Drag over the Cleft, under a walkway in Undercity, on a balcony: `/agps floor` prints
   the floors under you, the NPCs used and their range checks, the band and the floor picked. Target or mouse over an
   NPC that stands still near you (a vendor) to give it a reading. Also check: **are the range checks 3D?** Stand right
   over or under an NPC on another floor (straight above, 15+ yd up): "out of" interact range means 3D. The small line at
   the map's bottom left shows the grid's floor, how many floors are still possible, and the band.
10. **Jumps, stairs, bridges (found in the mesh):** with the option on, a route down a ledge says "Jump down here" (or
   "Continue straight, then jump down in 10 yd"), the arrow turns orange within 12 yd of it and aims at the path past
   the drop; at the top the step stays until you jump (or walk away from it): Orgrimmar from the ledge by the bank down to the Valley of Strength; Undercity from the Trade Quarter's
   ring down to the canals' walkways. Is each jump one the game lets you make, and survive? Stairs on a grid walk say
   "Take the stairs up/down" (Orgrimmar's spiral stairs by the Valley of Honor); Thunder Bluff's rope bridges say
   "Cross the bridge".
11. `/agps citygrid off`: everything as before.

## Numbers (2026-11-22, lupa; the game's Lua is about as fast)

`agps city-grid --check` (8 NPCs a city, each to each: 56 trips a city):

| city | on the grid | yards, grid | yards, Router's own | shorter | longer | runs off the mesh > 3 yd |
|---|---|---|---|---|---|---|
| Orgrimmar | 56 of 56 | 25,640 | 29,691 (-14%) | 49 | 7 | 0 |
| Stormwind | 56 of 56 | 31,315 | 38,596 (-19%) | 54 | 2 | 0 |
| Undercity | 56 of 56 | 23,778 | 28,414 (-16%) | 50 | 6 | 0 |
| Ironforge | 56 of 56 | 21,106 | 23,494 (-10%) | 45 | 10 | 0 |
| Thunder Bluff | 56 of 56 | 21,705 | 28,496 (-24%) | 54 | 2 | 0 |
| Darnassus | 56 of 56 | 24,576 | 28,873 (-15%) | 45 | 11 | 0 |

(2026-11-22, with the three new cities: the line's tighter tolerance at floor edges took Orgrimmar's one run off the
mesh, 3.1 yd, to none, for 1-2% more yards in the first three.) The check also walks the Router's own straight legs
over the mesh: the "longer" ones are where the Router's own goes through a wall or a floor. Orgrimmar: to Thrall by a
136 yd straight line through Grommash Hold's walls (79 yd of it off the mesh). Undercity: the Router's own crosses a
canal by a road the mesh has no floor under where the grid goes round, 7-32 yd more. Ironforge: the throne room to the
bank is 46 yd for the Router's own through the wall between them (19 yd off the mesh), 293 round by the Great Forge
and the Commons on the grid; the bank's and the inn's trips likewise (18-33 yd off the mesh); the Mystic Ward to the
Forlorn Cavern 24 yd more (a step the mesh has 5 yd high at Hulfdan Blackbeard's door, where the Router's own goes
straight, 2 yd off the mesh). Thunder Bluff: the Spirit Rise to the Pools of Vision under it, 78 yd for the Router's
own, which ends 24 yd over the Archmage on the rise's top; the grid goes down into the pools, 216. Darnassus: the
Router's own crosses between the Enclave's trees and terraces through their trunks (14-22 yd off the mesh) and up to
the Temple of the Moon's balcony by a 30 yd climb straight up; the grid walks the spiral stairs and ramps.

Search times (sync, lupa): median 30 ms, longest 250 ms (Darnassus, the inn to Tyrande on the temple's balcony,
42,189 surfaces settled); in game it runs in the background over a few frames.

`agps route-quality --against origin/main` (200 trips, seed 21):
- option off: **200 same**, 0 better, 0 worse, 0 lost, 0 errors.
- option on (`AGPS_CITY_GRID=1`, six cities): 185 same, **15 better, 0 worse**, 0 lost, 0 errors. They walk through a
  capital to a ride or out of one: 11 to 44 seconds faster each (e.g. A20 South Gate Pass to the Valley of Heroes by
  Ironforge's tram 624 s to 596 s; A5 Wildbend River to Darnassus by the teleporter 454 s to 431 s; H40 Tainted
  Foothills to Bloodhoof Village by Thunder Bluff's wind riders 7984 s to 7962 s; with the first three alone it was 10
  better).

## Cell sizes

`agps city-grid --cells 2,3,4` (before the gates' land roads were added as road links; those add a few hundred
surfaces):

| city | cell | surfaces | cells | stacked cells | road links | bytes |
|---|---|---|---|---|---|---|
| Orgrimmar | 2 yd | 86,993 | 66,746 | 15,412 | 292 | 930 KB |
| Orgrimmar | **3 yd** | 42,968 | 30,639 | 8,647 | 378 | 458 KB |
| Orgrimmar | 4 yd | 27,437 | 17,871 | 6,038 | 775 | 312 KB |
| Stormwind | 2 yd | 80,577 | 68,010 | 10,905 | 308 | 816 KB |
| Stormwind | **3 yd** | 41,637 | 32,040 | 7,672 | 411 | 418 KB |
| Stormwind | 4 yd | 27,461 | 18,957 | 6,261 | 949 | 303 KB |
| Undercity | **2 yd** | 59,920 | 37,017 | 16,455 | 862 | 582 KB |
| Undercity | 3 yd | 30,911 | 17,312 | 8,758 | 1,126 | 330 KB |
| Undercity | 4 yd | 20,152 | 10,151 | 5,912 | 1,832 | 269 KB |
| Ironforge | 2 yd | 40,525 | 34,285 | 5,432 | 130 | 388 KB |
| Ironforge | **3 yd** | 20,594 | 15,970 | 3,623 | 128 | 195 KB |
| Thunder Bluff | **2 yd** | 38,136 | 30,546 | 5,906 | 473 | 416 KB |
| Thunder Bluff | 3 yd | 19,415 | 14,154 | 3,771 | 538 | 221 KB |
| Darnassus | 2 yd | 110,418 | 80,600 | 22,392 | 1,055 | 1,018 KB |
| Darnassus | **3 yd** | 54,123 | 36,313 | 12,016 | 1,161 | 530 KB |

(the three new cities' rows: before their `near_z` and the counter's links, a few hundred surfaces fewer.)

The road links grow as the cells grow: at 4 yd (and Undercity at 3) the grid loses doors and walkways and the
roads have to carry them, which is the zig-zag this replaces.

`agps city-grid --check`'s gate trips (`capitals --check`'s: from outside the gate to every city place, Undercity
from its lifts' bottoms to the checked NPCs):

| city | on the grid | yards, grid | yards, Router's own | shorter | longer | flagged |
|---|---|---|---|---|---|---|
| Orgrimmar | 27 of 27 | 19,500 | 22,995 (-15%) | 27 | 0 | 1: the Transmogrifier, the route ends 13.8 yd off its floor |
| Stormwind | 26 of 28 | 19,311 | 22,500 (-14%) | 26 | 0 | 1: the Cooking Trainer, ends 7.2 yd off its floor |
| Undercity | 16 of 16 | 6,027 | 7,758 (-22%) | 16 | 0 | 0 |
| Ironforge | 27 of 27 | 16,222 | 17,572 (-8%) | 25 | 2 | 1: the First Aid Trainer, ends 6.2 yd off its floor |
| Thunder Bluff | 23 of 24 | 7,284 | 8,807 (-17%) | 20 | 2 | 0 |
| Darnassus | 23 of 23 | 15,002 | 20,772 (-28%) | 23 | 0 | 0 |

Stormwind's two not on the grid (the Router's own, as before): the Mage Trainer in the Wizard's Sanctum (up its portal) and the harbor's boat (outside the city's own cells). Thunder Bluff's one: the Mage Trainer in the Pools of Vision (the place's height, 111, has no floor of the grid at its spot; the nearest, a pool's floor at 104, is no way; the NPC trips there are on the grid). The flagged end on another floor than the place's height: the place's NPC stands where the grid has no floor at that height (to look at in game). Ironforge's two longer: the Mining Trainer 9 yd; the Paladin Trainer up on the Mystic Ward's balcony (525), 747 yd against the Router's own 652 (the balcony's stairs climb 22 yd between the roads' floors: Ironforge's `near_z` is 16 too; at 8 the balcony was no way on the grid and the trip was the Router's own). Thunder Bluff's: 1-2 yd. Each gate trip's own road into the city up to where the grid takes over is the Router's and is not judged against the mesh (Stormwind's gate road crosses the moat's bridge, which the mesh lacks); Thunder Bluff's start from Mulgore and ride a lift up.

## Open questions

- Draw grid walks solid (like roads) instead of dotted? Needs a kind or a flag the map and Turns both read.
- The band's slack (3 + 2 yd) and whether `CheckInteractDistance`'s yards are classic's here: to set from the in-game
  test.
- Ledges the roads have no drop for: found by navfeatures.py (section 4), up to the free 14 yd; to check in game.
- Default on for 1.4.0, or another test round first?
