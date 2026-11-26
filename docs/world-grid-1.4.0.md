# World routing (1.4.0 test): the city grid's way over the whole open world

Status: **being tested** on branch `feat/world-grid` (draft PR #895 into `feat/city-grid-1.4.0`; bake6 and the fixes of 2026-11-22/23 in section 7). Behind Options >
Routing "World routing: new (test)" (off by default) and `/agps worldgrid on|off|stats`. The one switch takes the
capitals' city grids with it (CityGrid.lua's `CG.On()`); "City routing: new (test)" alone still turns on only the
capitals'. With both off nothing changes: `test_with_the_option_off_the_grid_is_never_asked`.

Asked 2026-11-22 (Kooki3z): "Using the same technique used for cities, lets plan to regenerate wall data for the whole
map to test", then "using current road data in the open world, give it a slightly higher weight for road preference
(only open world, cities are wiped using city grid routing only), do the same logic used for city grid for the entire
map and run routing tests there too. Test going from city to open world spots and vice versa. I want 10000 test routes
to various NPCs."

Everything is our own: our Recast build over the client's collision (as the cities'), none of Shortest Path Forever's
code or output, nor the test server's meshes.

## 1. The meshes (`agps world-grid mesh`, worldmesh.py; dev data, never shipped)

Every map tile of Eastern Kingdoms (736), Kalimdor (988) and Zephras Isle (72) built by navbuild.exe (recastmesh.py's
agent and cell sizes) from: the terrain (every 4.17 yd quad, not its holes; a quad under water deeper than 1 yd is
solid, Recast doesn't swim), every placed WMO's collision faces (walknet.model_faces, as the capitals'), every solid
doodad (the ADTs' and the WMOs' sets). A tile is built over its own box and 24 yd round it. Undercity's model is left
out (its own level). Seven processes: **1,796 tiles in 330 s**, 650 MB (`AGPS_WORLDMESH_DIR`, else data/navmesh/world).

## 2. The grid (`agps world-grid grid`, then `bake --write`; worldgrid.py, worldbake.py)

- **Cells** of 8.33 yd (64 a map tile: the terrain grid's own cells), each walkable poly's height at the cell's middle
  (or its point nearest it); samples within 2 yd of each other from polys at most 2 links apart are one surface (the
  city grid's rule joined only neighbors: a map tile's cell is crossed by many small polys, and it left two or three
  surfaces of one slope, joined to nothing). Floors over floors are surfaces of one cell (a bridge over a river, a
  tower's floors, a cave under a hill).
- **Links** to the 8 neighbors' surfaces where the mesh joins them and the climb fits (citygrid.build_links); across a
  map tile's side, each tile is built with a ring of its neighbors' cells and a link into it is matched to the
  neighbor tile's own surface at that height.
- **Water**: where the terrain grid has water (its 1s: its closed sea stays closed) and no mesh floor is near the
  water's top, a swim surface at the top, linked to the water round it and the shore's floors within 1.5 yd. A yard
  swum costs `SWIM_COST` (1.5, Passability's).
- **Roads** (the open world's only, not the capitals'): every land road of the Router's graph walked every yard; the
  surfaces it crosses are road ground, a yard between two of them costs **`ROAD_PREF` 0.70** (0.85 until bake6, section 7; worldgrid.py; the data's
  `road`); where a road crosses what the grid can't walk (no way between within 1.3 x + 6 yd: a bridge deck the mesh
  lacks, a ledge), the road's stretch is a road link (citygrid.road_links' rule, its yards at ROAD_PREF). The land's
  roads have no heights: each sample keeps to the surface the one before was on (`ROAD_FOLLOW_Z`), and **the floor is
  carried from road to road where they meet** (`worldbake.road_floors`, 2026-11-22): seeded at road ends with a height
  or a cell of one surface (roads through first, dead ends after, the longest first), a road starts on the floor the
  road joined at its end was found on; only roads no seed reaches start on the terrain's surface (Data/Heights.lua).
  Before, every road piece started on the terrain's: north of Dun Algaz's tunnel the gorge runs under an overhang, its
  pieces started on the mountain top 100 yd over the road, the gorge floor wasn't road ground and its 3 yd step under
  the gate (the mesh doesn't join it) got no road link: no way from Loch Modan into the Wetlands on the grid.
- **Shipped walls are truth**: every link across one is dropped (a cliff's only the way up; `worldbake.cut_walls`):
  1,167 wall pieces cut 4,664 links in Eastern Kingdoms, 332 cut 557 in Kalimdor.
- **Pruning**: pieces under 200 surfaces no road touches are left out (rocks' tops, roofs); a piece of 2,000 or more,
  or the biggest, or one a road touches, is ground a player reaches (`F_REACH`: a spot with no height starts there).
- **The capitals' own cells** are left out (Router.CapitalAt): the city grid routes there.

The format (`worldbake.encode_tiles`): per continent `ns.WorldGridData[cont] = { per, cell, zq, z0, road, swim, bake,
n, t = { [tx * 64 + ty] = "<counts>|<records>|<heights>" }, links }`: each map tile one string, its cells' counts, its
surfaces' records (flags, the point in the cell, 4 characters of links) and heights (each against its prediction:
the same surface of the cell before in its column), each part run-length coded. A tile is decoded in game the first
time a search reaches it (`WG.Tile`, in the background's slices) into the city grid's layout (a character a cell,
8 a surface), 40 tiles kept.

### Size

| continent | surfaces | cells | stacked cells | swim | road ground | road links | file |
|---|---|---|---|---|---|---|---|
| Eastern Kingdoms | 1,668,237 | 1,429,226 | 188,339 | 352,354 | 52,515 | 16,392 | 9.18 MB |
| Kalimdor | 2,168,744 | 1,857,041 | 240,283 | 453,176 | 52,614 | 19,213 | 11.35 MB |
| Zephras Isle | 48,441 | 38,375 | 7,038 | 0 | 1,461 | 308 | 0.30 MB |
| **all** | | | | | | | **20.8 MB** |

At 4.17 yd cells (`--per 128`) Kalimdor alone was 8.3 million surfaces and 52.8 MB in the first encoding (about 4
times the cells): not shippable. **20.8 MB is too much to load at login for everyone**: the proposal for a release is
a load-on-demand addon folder per continent (AzerothGPS_WorldGrid0/1, loaded with `C_AddOns.LoadAddOn` when the option
is on and the player is on that continent), and the records' links written only where they differ from the
neighbors' heights (73% of Kalimdor's surfaces have exactly the links the heights alone give: about a quarter off the
file, by the numbers below). The data loads in the game harness in under a second.

## 3. The search (WorldGrid.lua)

`Router.Route` asks `WG.Leg` first while the option is on (before the city grid's `CG.Leg`, as the city grid's hook):
- both ends outside the capitals: the grid's walk (`WG.Walk`): A* over the surfaces, 8 directions, the 3D step plus 0.5
  a yard climbed, road ground at `road`, swims at `swim`, road links at their cost; the heuristic the straight yards
  at `road`. A leg up to `FREE_YD` (1,500) straight is searched anywhere; a longer one within `CORRIDOR_YD` (120) of the
  Router's own route (its roads and walks: the grid's walk keeps to the ground the Router would take, and never floods
  a continent). String-pulled as the city grid's (`WG.Line`, within 0.4 of a cell of each crossed surface's point, 0.25
  at a floor's edge: the city grid's 0.75 cut 6 yd corners on these cells), heights kept where the ground bends
  (`fz`); a straight stretch over road ground alone is kind road (drawn and said as one).
- one end in a capital: the Router's own route finds where it comes into the city (`CG.Crossing`); the city's grid
  walks inside from there, the world grid outside up to it; joined (`CG.Concat`).
- both in one capital: `CG.Leg` (the city grid). Two capitals, another level (Undercity, a dungeon), rides: the
  Router's own and the planner's, as before.
- In the background (`Router.Background`, a pause every 150 nodes and by the slice's clock; the Router's own
  meanwhile, `pending`), 24 routes kept. `test_the_search_runs_in_short_slices_in_the_background`.

## 4. The sample zones (Loch Modan, Durotar; `agps world-grid zones`, data/debug/worldgrid/)

Each zone's map tiles built and gridded alone (no roads, no walls cut, no pruning: the mesh as Recast gives it), every
cell classed against Passability.At (the terrain grid with Buildings.lua's cells and the capitals'): renders
`data/debug/worldgrid/zones_loch_modan_<64|128>.png`, `zones_durotar_<64|128>.png` (green both open, red the terrain
open and the mesh closed, cyan the reverse, olive/brown a piece of the mesh apart from the zone's biggest, blue water,
white a grid link across a shipped wall), numbers in `zones_<64|128>.json`.

| zone, cell | both open | terrain open, mesh closed | terrain closed, mesh open | mesh: a piece apart (open / closed terrain) | links across shipped walls |
|---|---|---|---|---|---|
| Loch Modan, 4.17 yd | 128,895 | 3,290 (2.5%) | 24,528 | 68,387 / 66,351 | 25 |
| Loch Modan, 8.33 yd | 32,793 | 188 (0.6%) | 8,852 | 17,161 / 22,835 | 12 |
| Durotar, 4.17 yd | 227,281 | 2,465 (1.1%) | 32,623 | 4,856 / 52,582 | 0 |
| Durotar, 8.33 yd | 57,695 | 70 (0.1%) | 11,239 | 891 / 17,150 | 0 |

- **Recast is not stricter than the terrain grid on open ground**: where the terrain grid is open the mesh is closed on
  0.1-2.5% of the cells (doodads: trees' trunks, fences, rocks; buildings' walls), so AGENT_CLIMB (1 yd) and
  WALK_SLOPE (50 degrees, the terrain grid's own) were **not** tuned: nothing pointed at them.
- Where the terrain grid is closed the mesh walks 10-15% of the cells (the terrain grid closes a cell when half its
  quads are steep; Recast walks the gentle half) but most of those are pieces apart (ledges, mountain tops no way
  reaches), which the pruning and the "reached" flag keep routes off.
- "A piece apart" on open terrain in Loch Modan is mostly ground joined to the rest outside the sample's 25 tiles (Dun
  Morogh's and the Wetlands' sides) or only by a road (the bake's road links join them).
- **Shipped walls**: the mesh walked across 12-25 grid links over Loch Modan's drawn walls (the cliffs by the Maker's
  Terrace, among them). Drawn walls are truth, so the bake drops every link across one (section 2).
- The hop tests' trips on the grid alone: Loch Modan's road north of Stonesplinter Valley to the Maker's Terrace 956 yd
  (straight 570; the Router's own 1,184 by Thelsamar) with no step across a drawn wall; Durotar's 1,379 yd (straight
  1,006). The third ("from the south" at -5800, -3350) has no mesh floor within 16 yd (a rock): the Router's own.

## 5. The 10,000-route test (`agps world-grid check`, worldtest.py; its data and report kept outside the repos, `AGPS_WORLDTEST_OUT`)

10,000 trips between shipped NPC spawns (Data/Npcs.lua, with their heights; seed 10000; at most 5,000 yd apart
straight, the distance drawn evenly): 2,000 city to open world, 2,000 open world to city, 4,500 open world to open
world, 1,500 city to city (Undercity's level and the rides between continents left out: a single leg each, as
`Router.Route` gives it). Each routed with the option off (**main**: the Router as it is) and on (**grid**), in the game
harness with the background's searches run out, each route walked every 2 yd over our own meshes of the map (the
judge; never SPF, whose code and output stay out). Judged: *off the mesh* (no walkable poly within 1.5 yd, and not the
terrain grid's water); a *wall crossing* (a run off it past 3 yd); an *impossible climb* (the floor followed over the
mesh jumps up more than 4 yd between samples 2 yd apart, with no floor near the one it was on within 4 yd); the
*wrong floor* (the floor it ends on more than 5 yd from the NPC's); *clean* (found, none of those). Rides, drops and
road links over gaps aren't judged. 6,233 s on 7 processes.

| | main | grid |
|---|---|---|
| found | 98.7% | 98.9% |
| **clean** | 36.4% | **42.1%** |
| yards, median | 2,241 | **2,023** |
| wall crossings / 100 routes | 119.2 | **62.7** |
| yards off the mesh / 100 routes | 2,512 | **1,626** |
| impossible climbs / 100 routes | **137.4** | 163.9 |
| wrong-floor ends | 13.2% | **9.5%** |
| on the grid (some of the leg) | | 91.9% |
| ms, median / 95th percentile (lupa, searched at once) | 979 / 2,841 | 1,036 / 4,342 |

By kind (clean %, main / grid): city to open 42.4 / 45.2; open to city 21.6 / 23.3; open to open 34.9 / 39.5; city to
city 52.7 / 70.8. Wall crossings / 100 (main / grid): 92.6 / 64.7, 113.5 / 69.8, 170.6 / 77.9, 6.3 / 4.9. Wrong-floor
ends open to city 16.9% / 7.2%. Both found (9,866): the grid shorter by 5 yd or more on 7,545, main on 1,393 (median
ratio 0.935); clean on the grid alone 1,334, on main alone 770.

Where each loses:
- **Impossible climbs are the grid's one worse number** (163.9 against 137.4 / 100; open to city 312 against 216).
  Spot checks: the grid's string-pulled lines run along ledges' and slopes' edges within its 0.4-cell tolerance
  (3.3 yd) where the floor 1.5 yd off is another one; 8.33 yd links may join a ledge's top and foot whose polys meet
  within two links round its end (HOPS 1 tried on 1,000 of the trips: no better, 193.2 against 192.1, 7% more data);
  where the grid has no way, the leg is the Router's own (a straight walk over a mountain, Orgrimmar to Blimo
  Gadgetspring's). Not solved here (below).
- **The worst routes are mostly the same for both**: Winterspring's spirit healer to Captain Vanessa Beltis in
  Orgrimmar's harbor (14 km, the far end on a ship the mesh has no floor on), Ironforge to the Gnome Engineer and to
  Peria Lamenur by Gnomeregan (10 km round, by Dun Morogh's roads: the stop isn't reached through the city), Darkshore
  to Darnassus (720 yd off the mesh for both: the sea to Teldrassil is a boat's, and a single leg has no rides; the grid's
  6.0-6.4 km against main's 6.7-7.0).
- Searches: the grid's median is about main's (open to open faster: 844 ms against 972), its 95th percentile 1.5 times
  (long legs in their corridor). In game it runs over many frames (`test_the_world_grid_s_search_runs_in_short_slices`).
- "Share of yards on roads" isn't comparable (main 86.9%, grid 45.8%): the grid's straight stretches cut over road
  ground's edges and only a stretch wholly on it counts as road.

**The road preference** (the same first 1,000 trips, the grid alone):

| `road` | clean | yards, median | wall crossings / 100 | yards on road ground |
|---|---|---|---|---|
| 0.80 | 40.8% | 2,082 | 59.8 | 49.0% |
| **0.85** (baked) | 40.4% | 2,047 | 61.5 | 46.8% |
| 0.90 | 39.9% | 2,030 | 67.3 | 43.7% |
| 1.00 (none) | 38.4% | 2,024 | 78.9 | 34.8% |

The roads are cleaner ground (drawn and walked): preferring them takes routes off rough ground for 1-3% more
yards. 0.85 kept ("slightly higher weight"); 0.8 is a little cleaner still. (Since bake6 it is 0.70: the sweep was rerun at Road tolerance +3 with the terrain grid's water judged, section 7.)

**route-quality** (the whole addon, rides and the ride check; 200 trips, seed 21, against `feat/city-grid-1.4.0`):
option off **200 same**; on (`AGPS_WORLD_GRID=1`) 30 same, 121 better, 35 worse, 3 with a way where there was none, 0
lost, 0 errors. The worse ones are 10-60 s slower each but for a few planned differently (H5 Southfury River to the
Golden Plains 2,005 s to 2,348 s by a zeppelin; A20 the Dawning Isles to Light's Hope 1,862 s to 2,250 s): the grid
doesn't price the other faction's guards (`HOSTILE_FACTOR`) or the zones too high for the player (`LEVEL_FACTOR`),
which the Router's own walks do; several "slower past fewer guards / on the safe way" listed as not worse.
**route-check** (the Router alone, the option off): 0 flagged of 678 trips.

## 6. Recorded walks and lifts (Kooki3z 2026-11-22)

"I already recorded pathing for darkcloud pinnacle, use that": **drawn and recorded roads are truth** on the grid too.

- **Recorded links** (`worldbake.mark_recorded`, after the walls are cut): every piece of a recorded walk and every road
  drawn with heights (overrides/roads_<cont>.geojson: `recorded`, or `zs`, ns.FloorTracks) is walked every yard at its
  own heights; a piece the import put on the ground flat (no `zs`: a rope bridge the import's model faces miss among
  them) takes the grid's surface nearest the height before (`REC_FOLLOW_Z`, a yard more for each yard with none; the
  heights across such a gap straight between). The surfaces it crosses are road ground; where the grid has no link
  between two surfaces one after another on it (a bridge's deck or a ledge the 8.33 yd cells miss), the stretch is a
  link at its own heights, its yards at `ROAD_PREF`, never refused for its ends' heights, never cut by the shipped
  walls (walked). One of the walk's own steps falling `REC_DROP_DZ` more than its yards is a drop: that stretch one way
  down (a step up so is a drop the other way). Thousand Needles' region: 61 recorded links, 36 more surfaces of road
  ground. From the canyon's floor at the needles' foot (-5080, -1772) to Lakota Windsong on Darkcloud Pinnacle: **872 yd
  up the walk's bridges** (1,513 by the Great Lift before); the way down 882 (1,519).
- **In game** the player's own walks and roads not yet in the data are the same links (`WG.OwnLinks`, in the search's
  costs: those within `REC_NEAR_YD` of the leg's box, kept per track).
- **Every lift car its own shaft** ("for the great lift there are 2, ramp to them is in red"): the dump's two cars of
  each lift (`lifts.shafts`: the Great Lift's, Freewind Post's, Thunder Bluff's two lifts) each ride their own shaft,
  linked between its **platforms** at its two stops (`worldbake.platform_floors`, `citygrid.lift_platforms`: within
  `LIFT_PLATFORM_YD` of the shaft and `LIFT_PLATFORM_Z` of the stop, on the mesh's piece that goes on to the ground
  round it, `lifts.ground_piece`: up the ramp or stairs, never the ground under a raised platform nor the structure
  between two cars), drawn from the platform to the shaft, up it and off. Thunder Bluff's in the city grid replace the
  lift roads' rides (`citygrid.lift_shaft_links`). Turns says nothing more at a lift's ends than "Take the lift up/down"
  (no "Leave the road" or U-turn there).
- **Rebaked**: only Kalimdor's region 4:5 (`worldbake.bake_regions`: its tiles with a ring of two round them; 61 of its
  64 tiles encode as before, the three with the walk differ) and Thunder Bluff's block of Data/CityGrid.lua (the rest of
  it as baked before, byte for byte). The bake stamps are unchanged; the whole bake (both continents' other recorded
  walks and drawn roads) is still to run.

## 7. The preview's fixes and bake6 (Kooki3z in game, 2026-11-22 and 23)

**What changed.** Each item came from a route Kooki3z saw in game. The commits are on `feat/world-grid-bake6` (merged into `feat/world-grid`).
- **Costs as the Router's** (`WG.Costs`):
  - the other faction's guards (light ones too; the towns at the ends exempt);
  - zones too high for the player;
  - "Allow swimming", the banned swims, and the player's swim speed;
  - the player's own walls, erase strokes, roads and remove strokes;
  - the safe drop: a drop longer than the player's own `x.maxDrop` is never taken;
  - Road tolerance: below 0 a yard of road ground costs as the Router's direct walk is scaled.

  A grid leg that passes the other faction's guards 10 yd or more beyond the Router's own route gives way to the Router's route (`GUARD_SLACK_YD`).
- **Links walked on the mesh** (`worldgrid.mesh_walk`): a link is kept only where the mesh is walked straight between the two surfaces, or one way down a ledge within `DROP_MAX`. Links the heights already imply aren't written.
- **Data per region**: a small header per continent; the tiles live in load-on-demand folders `AzerothGPS_WG<cont>_<rx>_<ry>`, loaded the first time a search reaches them. The release zip and the install take them. In the game's AddOn List (which shows every folder: no toc field hides one) each sits under AzerothGPS's row (`## Group: AzerothGPS`) with AzerothGPS's icon, titled "AzerothGPS map data: <continent> <rx>-<ry>"; their tocs come from `worldbake.region_toc` (`agps world-grid tocs` writes them again without a bake). A folder the game won't load (turned off, missing) is said once a session in chat with the way back (WG.RegionMissing); routes there are the Router's own.
- **Searches**: one per leg, joined onto as the player walks (`REUSE_YD`), at most `MAX_JOBS` (2) at once. Node budget: 60,000 + 50 a yard, up to 200,000. A long leg with no way in its 120 yd corridor is searched again within 600 yd (`CORRIDOR_WIDE_YD`).
- **Lines**: no sawtooth along walls; straightened before they're drawn (`WG.Straighten`, `WG.Clear`). The city grid gets the same costs and its streets.
- **Roads keep to their own surface** (`ROAD_FOLLOW_Z`), and the floor is carried from road to road (`road_floors`, Dun Algaz).
- **Road-link climb** (`ROAD_LINK_DZ`, `ROAD_LINK_SLOPE`, `ROAD_LINK_SPAN_SLOPE` 0.5): a road link's climb is weighed over the road's yards, or half a yard a yard between the two surfaces' points.
  - This joins the tunnel north of Dun Algaz into the Wetlands' east (a ramp, 4 yd over 8) and never a mesa's edge.
  - The caves Kooki3z marked are now walked: the green one from by Dun Algaz north, then the drawn road round to the orange one's west mouth and through it. Nothing goes off the 115 yd ledge.
  - Eastern Kingdoms' two biggest pieces (743,786 and 632,940 surfaces) are now one (1,376,825).
- **A spot with no height**: every floor of its cell within 1.5 yd of the ground's is a start. The cell's other reached floors also count, 150 yd dearer (`OTHER_FLOOR_YD`), for a road under an overhang.
- **No straight line through walls**: a stop's last short stretch (`NOWAY_MAX_YD` 300) the grid can't walk is "no way", never the Router's straight line.
- **Left to the Router**: the Ruins of Lordaeron (Undercity's model isn't in the meshes).
- **Lifts**: the open world's are ridden (Freewind Post, the Great Lift). Each car is boarded from its platforms (#917).
- **Recorded walks as links** (#917): Darkcloud Pinnacle's.
- **Drops**: baked to 60 yd (`DROP_MAX`), so the drops a fall spell makes safe are in the data (#916). The game never takes one past the player's own safe drop.
- **Road preference 0.70** (`ROAD_PREF`; was 0.85), from the sweep below. The capitals' streets stay at 0.85.
- **Road tolerance +3 by default** (Kooki3z: "snaps to roads good enough and make the short cuts seem worthwhile"). A saved 0, the old default, is moved to +3 once (`roadTolerance140`). Two routes +3 made worse are fixed:
  - Near the Great Lift, a loose road end's walk dropped off a cliff at each end. A walk between two road points now gets no fall-free drop at its ends.
  - Pithwick's shop in Ironforge was cut 13.6 yd across. Road tolerance is the open world's: a leg in a capital costs as at 0.

**The bake** (bake6, stamp `41c0319a2bbb`, about 2.5 min; road links refused for height are in brackets):

| | road links, bake4 | road links, bake6 |
|---|---|---|
| Eastern Kingdoms | 9,658 (1,241) | 10,231 (368) |
| Kalimdor | 12,231 (1,467) | 12,548 (487) |
| Zephras Isle | 74 (33) | 90 (10) |

bake6 also has 88 lift links in Kalimdor, and 62 and 121 recorded links in Eastern Kingdoms and Kalimdor.

**The road preference** (the first 1,000 trips, the grid alone, Road tolerance +3, judged with the terrain grid's water):

| `road` | clean % | wall crossings / 100 | yards off the mesh / 100 | yards, median |
|---|---|---|---|---|
| **0.70** | **47.4** | **75.2** | **1,878** | 2,056 |
| 0.75 | 47.1 | 76.3 | 1,891 | 2,059 |
| 0.80 | 47.3 | 77.9 | 1,903 | 2,033 |
| 0.85 | 46.0 | 80.0 | 1,918 | 2,029 |
| 0.90 | 45.2 | 80.9 | 1,934 | 2,024 |
| 1.00 | 45.8 | 85.4 | 1,976 | 2,018 |

**The 10,000 routes again** (bake6; the report and its data are in `worldgrid-10000/report-2.md`, outside the repos):

| | main (tol 0) | main (tol +3) | grid, first run | grid, bake6 |
|---|---|---|---|---|
| found | 98.7% | 98.7% | 98.9% | 98.4% |
| **clean** | 36.9% | 36.2% | 42.1% | **50.9%** |
| yards, median | 2,241 | 2,226 | 2,023 | 2,047 |
| wall crossings / 100 | 119.2 | 123.6 | 62.7 | 65.3 |
| yards off the mesh / 100 | 2,512 | 2,604 | 1,626 | 1,746 |
| impossible climbs / 100 | 134.2 | 136.1 | 163.9 | **87.8** (63.5 at its own heights) |
| wrong-floor ends | 13.2% | 13.2% | 9.5% | 9.7% |

- Notable changes:
  - Impossible climbs are no longer the grid's worse number: 87.8 against main's 134.2.
  - Clean routes on the grid went from 42.1% to 50.9%.
- What got slightly worse:
  - Wall crossings are 65.3 against 62.7 in the first run. Open to city went from 69.8 to 83.4 and city to open from 64.7 to 74.6; open to open went down, 77.9 to 73.3.
  - **53 trips found a way in the first run and have none now** (1 the other way). The causes are the road-link climb check and the no-straight-line rule. main lost none.
- Both found on 9,828 trips: the grid is shorter on 7,859, main on 958. Clean on the grid alone 1,817, on main alone 433.
- The judge now takes the floor again after skipped pieces and counts climbs at the route's own heights too. main's climbs moved from 137.4 to 134.2 with it.

**route-quality and route-check** (b61c6d82, against origin/main 80fc6e54; 200 trips, seed 21)

- **Option off, Road tolerance pinned to 0 on both sides** (`AGPS_RQ_ROAD_TOL=0`): 197 same, 1 better, 0 worse, 0 errors.
  - Two more trips are listed but not counted as worse: one slower along roads the branch drew, one slower past fewer of the other faction's guards.
  - These differences come from the branch's other changes against main (#916, #917, the shipped roads), not from the grid: the grid is off in this run.
- **Option off, each side at its own default** (+3 here, 0 on main): 185 same, 12 better, 1 worse. The worse trip is H40 The Rolling Plains → Wildbend River, 1,407 s → 1,648 s: it now flies from Ratchet instead of the Crossroads.
- **Option on** (`AGPS_WORLD_GRID=1`): 36 same, 135 better, 24 worse, 2 with a way where there was none, 0 lost, 0 errors. The first run was 30 / 121 / 35 / 3.
  - The worse trips are 13-30 s slower each. Several more are listed as slower past fewer of the other faction's guards, which doesn't count as worse.
- **route-check** (the Router alone): 0 flagged of 678 trips in 51 zones.

## 8. bake7: the stops' floors, the recorded lift rides, Blackrock Mountain (2026-11-23)

The whole bake again (every continent: the stamp changed), with main's road imports up to #947 (Blackrock Mountain,
the Burning Steppes, Feralas, Tanaris, the Barrens to Razorfen Downs) and #945's underground sweep as a yardstick.

- **The stops' floors joined along the mesh** (`worldbake.stop_links`, after the recorded walks): every shipped NPC's
  spawn and every dungeon's door (`stop_spots`) whose floor the grid leaves apart from the ground players reach is
  joined to it along our own mesh's polys (`_mesh_way`, over the map tiles' rings), a link each way at the way's
  heights (thinned, `STOP_THIN_YD`). "Reached" is a strong piece of `REACH_PIECE` surfaces with no drop past
  `STOP_SAFE_DROP` (14 yd, a fall every player takes): Ironforge's halls were one piece only by 20-40 yd drops back. A
  floor joins the nearest bigger piece, then the next (`STOP_STEPS`), till the reached ground. Then each stop's floors
  round it (`STOP_NEAR_YD` of the mesh's way) that the grid walks to more than `STOP_DETOUR` times longer get the mesh's
  way too, up to `STOP_SHORTCUTS` a stop: Booty Bay's docks and its walkways, 1,310 yd from Auctioneer Kresky up to
  Grarnik Goodstitch 64 yd off, now 160. Never across a shipped wall, nor in a `WG.WALLED` building (Nethergarde Keep's:
  the mesh walks through its wall). Eastern Kingdoms: 84 stops' floors apart, 69 joined, 811 shorter ways (1,780 links);
  Kalimdor 93, 56, 858 (1,846); Zephras Isle 9, 8, 137 (290). Left apart: no way on the mesh (Gnomeregan's camp and
  front door, Namdo Bizzfizzle, Uldaman's front door and Hammertoe Grez, the Sunken Temple's door, Archmage Xylem's
  tower, a few mesa tops): they need recorded walks.
- **Recorded lift rides** (`mark_recorded`): a recorded step climbing or falling past a slope within `REC_RIDE_YD` of a
  lift car's shaft is that car's ride, a lift link both ways between where the walk got on and off. Kooki3z rode
  Freewind Post's east car with Record on: its 130 yd step was a walk link up (kind 0) and a 130 yd drop down, taken
  over the car with a zigzag over the foot's road ground. The east car is boarded from the ground 5 yd under its stop,
  out of `lift_links`' platforms. A recorded fall past `DROP_MAX` elsewhere is no link. Kalimdor: 2 rides.
- **In game** (WorldGrid.lua): a spot with a height and none of its cell's surfaces on that floor takes the neighbor
  cells' on it first (Freewind's east tower top: its cell has only the foot and a roof); a leg the world grid has no
  way for with both ends over one city grid's floors the Router's capital outline leaves out walks that grid
  (`WG.CityWalk`: Ironforge's halls, where the world grid has only scraps between the capital's cells).

| continent | road links (refused) bake6 | bake7 | recorded links | stops' links | all links | file |
|---|---|---|---|---|---|---|
| Eastern Kingdoms | 10,231 (368) | 10,287 (368) | 117 | 1,780 | 12,081 | 10.60 MB |
| Kalimdor | 12,548 (487) | 12,618 (493) | 169 + 2 rides | 1,846 | 14,620 | 13.70 MB |
| Zephras Isle | 90 (10) | 90 (10) | 0 | 290 | 380 | 0.45 MB |

(24.75 MB, bake6's 24.22.)

**The lost trips** (bake6's 10,000-route test: 53 trips it had a way for in the first run and none in bake6's): of the
38 short ones (420 yd or less straight; the towns), **34 get a grid's route** now (26 the world grid's, 8 Ironforge's
city grid), against 17 before (the 952 stopgap's Router walks aside). Left: Thunder Bluff's flight master to the spirit
healer under the mesa (the city grid's, and the start's floor: no player height), and three floors the mesh has no way
to (Archmage Xylem's tower, a Thousand Needles mesa top, a Desolace cliff). All 53: 42 on a grid, 9 no way.

**The underground sweep** (#945's `agps underground-sweep`, 4 jobs): before (bake6, this branch's code) 70 of 1,830
trips failed (58 of 646 destinations), after **57 of 1,836 (48 of 648)**: no way 1 to 0, overhead 13 to 10, straight
40 to 29, through 25 to 25 (Thunder Bluff's flight master's tower and Darnassus: the city grids'). Notes: stops ended
at a building's foot 57 to 12, the Router's own last walk 115 to 91; floors never reached 10 to 7. Blackrock Mountain:
his recorded walks (#927, #929, #934) join the lower floor to the ring and out; from the Molten Span to Blackrock
Depths and from Blackrock Spire's door down to it follow his walks (two of the three xfails pass; the reference is now
his whole walk down from the ring over the span). From his saved spot at Blackrock Depths' door the start has no height
and takes the mountain's top (288) over the door (166): still xfail (the open world has no floor followed).

**route-quality** (200 trips, seed 21):

| option | against | same | better | worse | a way where none | none where one | errors |
|---|---|---|---|---|---|---|---|
| on | #960 with main and #945 merged, no bake7 (5f576bf5) | 42 | 126 | 28 | 2 | 0 | 0 |
| on | #960 (b6124e2c) | 40 | 128 | 27 | 2 | 0 | 0 |
| on | main (546e4962) | 36 | 137 | 22 | 2 | 0 | 0 |
| off | #960 (b6124e2c) | 195 | 3 | 0 | 0 | 0 | 0 |
| off | 5f576bf5 | 200 | 0 | 0 | 0 | 0 | 0 |

With the option on, route-quality's older side takes the older ref's files under addon/AzerothGPS only (its
Data/WorldGrid*.lua headers) and this tree's region folders, which don't match those headers: the older side comes
out as without the grid (the same worse list as against main, which has none), so all three "on" rows are in effect
the grid against none (#960's own was 35 / 138 / 21 / 2 / 0 against main). The worse ones are the 10-60 s list of before (the grid's costs miss the guards and
the zones too high). Option off: 200 same against the same code without bake7; against #960 the 2 more listed (not
worse) are main's road data (the Scarab Wall, Zul'Farrak).

**route-check** (the Router alone): 0 flagged of 678 trips in 51 zones.

Not done here: Thunder Bluff's flight master's tower (a 32 yd step at (-1194, 24)) and the Router's walk up its east
lift are the city grid's (its meshes aren't on the bake's PC); the steep one-link climbs (51 notes) are as they were.

## 9. bake8: no fallback in towns, the coverage sweep, expert drops (2026-11-23)

Kooki3z: "imo fall back can't be trusted and should identify where that would be needed and just correct it".

- **The town stopgap is gone** (#952's `WG.RouterClosed`): a short leg the grid has no way for is "No way there found"
  wherever a straight piece of the Router's own walk is one the grid can't walk, whatever the Router's own ground says.
  `WG.WALLED` stays as the bake's (the stop links keep out of Nethergarde Keep's building). The long-leg rule (over
  `NOWAY_MAX_YD`, the Router's own) is unchanged.
- **The coverage sweep** (`agps world-grid coverage`, worldcoverage.py, about a minute with 8 jobs): every shipped stop
  (3,365: NPC spawns, the towns' places, the dungeons' doors, the flight masters, one per 3 yd) walked to on the grids
  alone (`WG.Walk`; over a city grid's cells, `CG.Walk`) from up to 3 starts 60-250 yd round it (road ground first, then
  any reached ground, never across a shipped wall from its cell's floor). A stop fails when no start's walk gets there
  on its floor (`noway`; `foot`: it ends under it; `overhead`; `nostart`); a walk that gets there across a shipped wall
  is counted apart (`crossing`). Each failure's cause from our meshes: `missing link` (the mesh walks there, the 8.33 yd
  cells miss the stairs or door), `cell too coarse`, `mesh apart` (no way on the mesh: a recorded walk's), `mesh hole`,
  `search`. `test_world_coverage.py`: the stops whose floor the data lacks and a sample of 120 others are reached, but
  for `EXCEPTIONS` (15, reviewed: out of reach on our mesh) and `KNOWN_GAPS` (59, the next bakes' work, with their
  causes); both lists may only shrink.

| | stops | can't reach | foot | no way | overhead | no start | crossing a wall |
|---|---|---|---|---|---|---|---|
| bake7's data, this code | 3,365 | 80 | 44 | 29 | 5 | 2 | 73 |
| bake8 | 3,365 | **74** | 38 | 29 | 5 | 2 | 73 |

  Fixed 9 (Bro'kin, Frezza, Gnomeregan's Train Depot, Jadenvis Seawatcher, Mountaineer Rharen, the Scarlet Monastery's
  Library, Snurk Bucksquick, Syurana, Tallonkai Swiftroot), 3 new (Blackfathom Deeps' door, Mountaineer Dokkin,
  Atal'ai Exile: their starts' pieces). The crossings are at road and stop links' ends: a link's end on a road inside a
  palisade and the next cell's point outside it (Hammerfall, Brill, Splintertree Post: 3-15 yd). The lines the grid
  pulls straight no longer cross a shipped wall (`x.lineWalls`, WG.Pull and WG.Straighten); the step after a link
  still can.
- **The mesh walk's arrival** (`worldgrid.mesh_walk`): a link's walk arrives on the neighbor surface's own polys, or one
  joined to them within `HOPS`; by the height alone, a surface's point on a corner two pieces of the mesh share was
  arrived at from the other piece. Gurubashi Arena's Battle Ring was walked into through its wall so.
- **Drops through the ground** (`worldbake.cut_ceiling_drops`): a one-way drop from a floor on the ground onto one
  `UNDER_GROUND_Z` under the terrain there, the terrain over the foot about as high as the top (a hole in the ground,
  not a cliff), `CEILING_DROP_MIN` or more, is dropped: Eastern Kingdoms 35,040 links, Kalimdor 50,612. Moonbrook's
  hill over the Deadmines' tunnel was walked over and fallen through, 20 yd, onto the portal's floor.
- **The stops' mesh ways** (`_Meshes.polys_at`): a poly is a stop's when the spot is in it (bake7 asked for its edge
  within 3 yd: a big floor's middle was never found), looked for by the polys' boxes, not their middles within 40 yd.
- **Expert jumper's drops** (`worldgrid.DROP_FAR`, 400 yd, FallSpells.lua's `DROP_CAP`): the walked links' one-way drops
  go to 400 yd (climbs, roads and recorded walks keep `DROP_MAX` 60); the game takes one only within the player's own
  safe drop (`x.maxDrop`). Trial, Kalimdor's region 3:4 (Mulgore and the Barrens' west, 122 tiles gridded): 16,567 more
  drop links past 60 yd (the deepest 307); the region's files 1,237,024 bytes with bake7, 1,195,773 with the arrival
  rule alone, 1,244,161 with both (+48 KB, 4%, for the drops); its stops' coverage the same.
- **The floor followed along the route** (`Nav.TrackRouteZ`, world routing on): the game gives no height, and a
  recalculation started on the floor nearest the shipped ground's height: in Blackrock Spire's entrance halls (floors
  246-286 under the mountain's top) that was a hall over the route, and the directions turned back. Within
  `ROUTE_Z_YD` of the route followed, its height there (the piece taken last first; switchbacks pass over themselves).
  Walking up from the ring 3 yd off the line, every step worked out again: 19-24 U-turns of 76 before, none after.
- **The underground sweep** reads the portal into a stop's dungeon from the stretch's `inside` (#964 leaves it out of
  the legs).
- **Tiles decode** with each character from a table (`CH`): about 5% less (17.6 to 17.0 ms a tile in the harness).

**The bake** (stamp changed: every tile gridded again, `world-grid grid --changed --workers 20`, 95 s; the bake 5 min):

| continent | road links (refused) bake7 | bake8 | recorded links | stops' floors apart / joined (links) | file |
|---|---|---|---|---|---|
| Eastern Kingdoms | 10,287 (368) | 10,460 (366) | 117 | 90 / 75 (1,818) | 10.36 MB |
| Kalimdor | 12,618 (493) | 12,785 (490) | 168 + 2 rides | 97 / 65 (1,948) | 13.73 MB |
| Zephras Isle | 90 (10) | 92 (10) | 0 | 14 / 13 (348) | 0.45 MB |

(24.54 MB, bake7's 24.75.)

**The cases**
- *Gurubashi Arena* (from the grass south of the east gatehouse to the Battle Ring): the route through the outer wall
  and stands was the stopgap's Router walk. Our mesh has the ring and the stands as one piece (a 483 yd way between
  them) apart from the ground outside: no gate tunnel joins them. Now "No way there found"; it needs a recorded walk
  through a gate (or a look at the tunnels' collision). Test: never a line into the ring at its floor's height.
- *The Deadmines*: from Sentinel Hill the walk goes in by the Defias hideout's building and its tunnel, no stretch on the
  hill over the portal.
- *Blackrock Spire's door*: the ring to the door follows his recorded walks (#929's and the halls' switchbacks); the
  flips were the start's floor (above). Tests: the walk, and walking it worked out again at every step.
- *Mulgore's plain*: on the grid (bake7's and bake8's) Skywatcher Plateau to the stop north of Elder Rise is 964 yd
  (straight 751): the road to the pass, then 600 yd down the plain; the whole addon 978 yd, no ride, both factions. The
  route in the screenshots (1,620 yd by Thunder Bluff) is the Router's own: the grid's walk wasn't the one shown there.
  The red dashes are the terrain grid's cliffs; north Mulgore has no shipped walls. Expert jumper: with any drop allowed
  (`maxDrop` 1000) the grid's way is the same: the ridge is steep slopes, not a ledge within a cell, so the walked links
  have no drop off it, and the cliff walls offer none there.
- *Durotar's ledge* (route-compare open:122): off the Den's raised ground the grid's way down is the mesh's drop (21
  yd); its walks keep their slopes.
- *Stormwind's climbs* (15 against 6 per 100 in route-compare): the city grid's (2-7 yd steps on its lines); not rebaked
  here (the city grids' meshes aren't on the bake's PC).
- *Routing time* (route-compare: 614 ms median against 140): 25 of its open-world trips in the harness, 27 s in all:
  the grid's searches 63% (decoding tiles 28% of all, 17 ms a tile), the Router's own route for the corridor 55%
  (they overlap). Cheap win taken: the decoding's characters. Not cheap: the corridor's Router route, the tiles.

**The yardsticks**
- bake6's 53 lost trips: 42 on a grid, 11 no way (bake7: 42, 9, and 2 the stopgap's Router walks).
- route-compare's 159 open-world fallbacks: before 117 still the Router's own, 31 the grid's, 11 no way; after 115, 32,
  12. Of a sample of 14 of the 115: 10 have no way on the grid even searched without a corridor or budget (an end on a
  piece apart, a spot off the meshes, a ghost's spirit healer), 2 only without the corridor and budget, 1 has a grid
  walk the guards rule (`WG.MoreGuards`) gave up. These are legs over `NOWAY_MAX_YD`, the Router's own by the long-leg
  rule: the next work, by the sweep's causes.
- The underground sweep (#945's, 6 jobs): before (bake7's data, this code) 49 of 1,836 trips failed (41 of 648
  destinations: no way 4, through 25, overhead 11, straight 17), after 52 of 1,847 (43 of 651: 4, 26, 13, 18). Fixed 3
  (two spirit healers' straight lines, Tepa's fall), new 6: starts on the floor over an NPC's head (`above`: Mirkfallon
  Keeper, Hammertoe Grez, Mountaineer Grugelm, a Slave Worker) and Thunder Bluff's Tal (the city grid's). Floors never
  reached on foot: 7 to 1.

**route-quality** (200 trips, seed 21):

| option | against | same | better | worse | a way where none | none where one | errors |
|---|---|---|---|---|---|---|---|
| on | bake7 (0dade147) | 43 | 125 | 29 | 2 | 0 | 0 |
| on | main (38a9275d) | 36 | 137 | 23 | 2 | 0 | 0 |
| off | bake7 (0dade147) | 200 | 0 | 0 | 0 | 0 | 0 |

As in bake7, the "on" rows' older side is in effect without the grid (its headers against this tree's region folders);
the worse ones are the 10-60 s list of before (the grid's costs and the ride check's plans: H5 Tarren Mill to
Northshire Valley 2,222 to 2,441 s, H5 Southfury River to the Golden Plains 2,005 to 2,113 s).

**route-check** (the Router alone): 0 flagged of 678 trips in 51 zones.

## 10. bake9: the stand-in replaced while riding, no far road, a sheer cliff's drop (2026-11-23)

**Tanaris, Mulgore and Dustwallow were the stand-in.** From the sands south of Gadgetzan to Uldum's entrance the route went north to
Gadgetzan's flight master, along the road to Steamwheedle Port and back south-west (5.9k yd for 1.8k straight); from
Skywatcher Plateau round by the Barrens (9.9k for 751); in Dustwallow (build 7cc84712), from the Barrens' ridge (203) to
the marsh 163 yd off and 170 yd below, 1.2k yd by North Point Tower's road junction (two straight lines: the Router's own
walks to the road still searched). Both were the Router's own route shown while its walks were
searched, the roads meanwhile, and on the build he played (2f7f12b3, bake8) never replaced while he rode on: in the
game harness with the game's background share (15 ms each half second, the player mounted, the route worked out again
when a search lands), 80 of 80 half seconds on the stand-in. The walk straight to the stop was queued behind the
planner's walks to docks and flight masters (one to Theramore ran for seconds), went stale as the player moved (15 yd)
and was queued again at the back. Not the flight-path detour: his character (an Alliance gnome mage) knows no flight
path on Kalimdor, so the planner has no flight there, and "Learn the flight path ... (on the way)" is a hint on the map,
never the route; not OpenGround/OpenLine either (the line over the dunes is blocked 104 yd in all, 76 in one go: the
grid was searched, round the stand-in's roads).

- `Router.SetFocus` (Nav.Compute): the walk from the player to the stop goes first; the other walks from the player
  before the walks between fixed points; a search begun is never dropped as stale; a `first` background job queues
  after those already started.
- `Router.Reuse`: a long walk found from where the player was is joined from further: `WALK_REUSE_SHARE` (0.1) of what's
  left of it, up to `WALK_REUSE_MAX_YD` (200). The world grid's `JoinOnto` and its wait for a search the same
  (`REUSE_SHARE`, `REUSE_MAX_YD`); a short leg to the stop itself is searched first.
- `Router.PendingCost`: while a walk is searched, a long leg blocked only here and there (`PENDING_BLOCKED_SHARE`, 6% of
  it) counts as about straight; `WG.OPEN_RUN_YD` 100 (a dune's side; 60 before).
- `Router.SaneStandIn`: the route shown while the world grid works a leg out is never one past `STANDIN_MAX` (2.5)
  times the line and `STANDIN_SLACK_YD` (200) more: the straight line meanwhile, marked pending ("Working out the
  route..."), the grid's way once it lands. With the grid's searches slow (the ridge to the marsh: no way down without
  a big drop, 1.7 s of search; Mulgore as an Alliance player, the guards priced, 300 ms and more) the far road's way
  round was what showed for a minute.
- Riding them (`test_stand_in.py`, the game's background share): Tanaris replaced in 2-3 s (the build before: never);
  no half second of the three trips shows a way round past 2.5 times the line (before: all 80, all 80, 30).

**Open ground to open ground, no far road** (Kooki3z: "open ground to open ground tends to want to snap to roads far
away, this shouldn't be the case if it adds that much of a route"). Where it happens: the grid's road preference
(`ROAD_PREF` 0.70: a way by road ground up to 1 / 0.70 = 1.43 times another wins) and the long legs' corridor round the
Router's own route (its roads). The rule (`WG.ROAD_DETOUR_MAX` 1.2): a grid way with road ground longer than 1.2 times
the line is searched again with no road preference, and the road's way is kept only when at most 1.2 times that walk;
the Router's own still searched or longer than 1.2 times the line, the line's own corridor is searched too. Not below
Road tolerance 0 (the player asked for the roads). Measured with world routing on (the game's leg, settled) against the
grid's walk with no road preference, open ground to open ground: past 1.3 times that walk, 8 of 1,357 of 1,500 sampled
10,000-route trips and 2 of 425 of route-compare's 600 before; 6 and 2 after (112 shorter, 24 longer, 1,911 the same).
The rest are Blackrock Mountain's floors (the Molten Core's way in to Bodley: the walk with no road preference falls
through a floor) and the Router's own on long legs with no grid way. Settled routes rarely snap to far roads; the stand-in
shown meanwhile did (above).

**Freewind Post's mesa** (Expert jumper, Slow Fall and feathers; the route went over the west bridge and down the next
mesa's road): the bake has the drop off the mesa's north-west edge (119 yd, bake8's `DROP_FAR`): with a drop that big
allowed the grid's way is that drop, 211-291 yd against 452-663 by the roads. On his build the route still took the
roads: the drop the grid's search may take is the player's own (`x.maxDrop`, Nav.SafeDrop), and picking the spell jump
and keeping it on settle is the jump work's (#948).

**A sheer cliff's drop**: off a mesh's edge with no floor under it, a drop is looked for on along the line up to
`DROP_SCAN_YD` (3) onto a floor `DROP_SCAN_MIN` (40) or more under the edge (a sheer cliff's foot starts the agent's
room off its face): only a fall a fall spell or Expert jumper makes (`test_bake_speed.py`, both walks). The compiled
walk (Numba, perf/gpu-bake merged) keeps bake8's arrival rule and `DROP_FAR` too.

**Skywatcher Plateau's east edge** (Slow Fall and feathers, Expert jumper): no spell jump is offered because the grid has
no drop there at all, whatever the drop limit: at x -470 the plateau's floor ends at 135 yd (y 116), two cells (16 yd)
have no floor (a 74 degree slope the mesh doesn't walk), and the plain's starts at 52 (y 95). The walked links join the
8 cells round a cell only, so a fall over empty cells is no link (with any `maxDrop` the grid's way is the same 964 yd).
It needs jump links over two or three cells (a link list as the road links', from an edge's floor down to the first
floor under the fall line); not done here. The baked drop limit wasn't it, and the cliff walls offer none there (north
Mulgore has no shipped walls; the red dashes are the terrain grid's cliffs, which the grid doesn't use).

**Into caves only by their mouths** (Kooki3z 2026-11-23, the Barrens' ridge to Dustwallow: a 176 yd "spell jump" from
the ridge, 208, straight down into Darkmist Cavern's tunnels, 34, and out its east mouth: "those should only be routes
available outside the cave once going through the entrance"). bake8's rule (a hole in the ground) missed it: the coarse
heights put the ground at the foot 8 yd lower than the ridge, a cliff's. Now a drop from a floor on the ground onto any
cell of a cave's grid (Data/Caves.lua: its floor, its floor under walkable ground, its rock) under the terrain is
dropped (Eastern Kingdoms 10,969 more, Kalimdor 13,999), and a drop of `DROP_CLEAR_MIN` (20) or more never lands with
another floor over it between its foot and its top (`worldgrid._clear_over`: the ground going on past the edge over a
tunnel; both walks). Caves are entered by their mouths, walked.

**The Deadmines from Moonbrook** (Kooki3z, build 3ae5a417: the way to the portal must go in by the Defias hideout's
house, never drop through the ground). The house sits over a hole in the terrain (no height there), so the rule above
missed it: the grid fell from the house's floor, 45, to the tunnel, 24, under the ramp's floor, 36 (and, once that was
cut, in two drops of 12 and 11 past it). Now a drop of `HOLE_DROP_MIN` (8) or more onto a cave's floor under a hole is
cut when a floor of its cell lies between the foot and just over the top (the roof far over doesn't count): the way
goes in by the house and down its ramp (`test_world_grid.py`). The Router's stand-in is never the straight line with
an end in a cave or a capital's split floors (`Router.SaneStandIn`). Which part holds the rule: the bake's links (here);
the Router's own routes and Passability's ground-cliff drops are unchanged (they follow the caves' roads); the spell-jump
planner's jumps are the jump work's (#948); the instance-portal stop's final approach is the grid's walk to the portal.
Not done: the Router's own ground-cliff checks
(Passability.CliffAlong) and the indoor WMO groups outside Caves.lua's caves (buildings' insides: their drops
off the roofs are few, and their doors are the city grid's and Indoors.lua's roads).

**The rebake** (Numba, `world-grid grid --changed --workers 16`: 1,796 tiles in about 90 s; the bake 4-5 min):

| continent | road links (refused) bake8 | bake9 | drops through the ground dropped | onto a cave's cells | file |
|---|---|---|---|---|---|
| Eastern Kingdoms | 10,460 (366) | 10,460 (365) | 36,452 | 14,071 | 10.33 MB |
| Kalimdor | 12,785 (490) | 12,785 (488) | 51,905 | 21,178 | 13.85 MB |
| Zephras Isle | 92 (10) | 92 (9) | 0 | 0 | 0.46 MB |

(24.63 MB, bake8's 24.54.) Coverage: 78 of 3,365 the grids can't reach (bake8 74): Innkeeper Karakul reached now, five
end at their buildings' feet or have no way that reached it in bake8 (Archmage Tervosh up Jaina's tower, Syurana, Ian
Strom, Jadenvis Seawatcher, Cenarion Scout Landion; the tiles' own links there didn't change, only 11 rows of Theramore's
tile, all drops added; to look at next). The underground sweep: 53 of 1,832 trips (bake8 52 of 1,847). bake6's 53 lost
trips: 42 on a grid, 11 no way (as bake8).

**Route-quality** (200 trips, seed 21, with the world grid on): against bake8 (d9227c6f) 41 same, 126 better, 29 worse, 2 with a way where there was none, none lost; against main (4ba3c4b4) 35 same, 138 better, 23 worse, 2 with a way, none lost. The worse are 4-10% slower (the biggest Tarren Mill to Northshire, 2,222 to 2,441 s); not traced one by one (the far-road rule, `ROAD_DETOUR_MAX`, takes slower open ground over road ground within 1.2 times; likely most of them). World grid off against bake8: 200 the same. route-check: 0 flagged of 678.

## 11. A cave's way in from a recorded walk (the Wailing Caverns, Gnomeregan; 2026-11-24)

With no fallback route (Kooki3z 2026-11-23), a stop the grid has no way to is "No way found yet" and logged
(WorldGrid.NoWay: WG.gaps, Nav.gridGapHook; the Dev addon's Recording TODO lists it under Grid gaps as a Record walk
from the gap's start to its end). The Wailing Caverns' portal (z 19, from the oasis's mouth) and Gnomeregan's are such:
the grid's tunnels don't join the mouth to the portal's floor, and its falls from the ground into a cave are refused at
search time (WorldGrid.IntoGround, the hills over the caverns). A recorded walk drops straight in:

1. Kooki3z walks it in the game with Record on (the Grid gaps item, or Recording TODO's own): from the cave's
   mouth (or Gnomeregan's front entrance, or the Train Depot) down to the portal, the way a player goes.
2. The road watcher imports it (the `recordings` branch): a piece of
   `overrides/roads_<cont>.geojson` with `recorded: true` and its heights (`zs`), read by `worldbake.recorded_walks`.
3. The region's bake on the bake machine (the tiles' grids there; `AGPS_WORLDGRID_DIR` at the latest grid run):
   - the Wailing Caverns: `agps world-grid bake --cont 1 --regions 4:4 --write` (the mouth and the portal, map tiles
     35/36, 33)
   - Gnomeregan: `agps world-grid bake --cont 0 --regions 3:5 --write` (both portals, the Front Entrance and the
     Train Depot, map tile 30, 41)
   `worldbake.mark_recorded` lays the walk in as links at its own heights where the grid has none.
4. Tests: `test_world_grid.py::test_a_recorded_walk_into_*` skip until a recorded walk reaches the place (in the
   overrides), then require the grid's way in by it, never over the ground; the coverage list (worldcoverage
   KNOWN_GAPS) loses the stop when it's reached.

## What's left

- ~~The grid's costs miss what the Router's have~~ (done, section 7: `WG.Costs`). Was: **the grid's costs miss what the Router's have**: the other faction's guards (`HOSTILE_FACTOR`, "Avoid the other
  faction's towns"), zones too high for the player (`LEVEL_FACTOR`), "Allow swimming" off and the swims removed by
  hand (the bans), walls the player draws in game (only the shipped ones are cut). Each is a per-cell cost the search
  can read (Hostile.lua's circles, Zones.lua's chunks, Passability's bans); route-quality's 35 worse need them first.
- **Impossible climbs** (bake6: 87.8 / 100 against main's 134.2; links walked on the mesh, done): a bake-time check of each 8.33 yd link by a walk over the mesh between its two
  surfaces' points (a Detour raycast of our own), and the line's tolerance tied to the floor's edge.
- ~~Size~~ (done: load-on-demand region folders, links implied by the heights not written). Was: **size**: 21 MB loaded at login for everyone is too much for a release. Load-on-demand folders per continent
  (loaded when the option is on and the player is there), links written only where the heights don't give them (73% of
  surfaces), and the swims' records (a fifth of the surfaces) as the terrain grid's water at run time.
- **Floors**: no player height in this client, so a start with no height takes the reached ground nearest
  Data/Heights.lua's; the city grid's floor estimate (`CG.TrackFloor`) isn't extended to the open world (a cave under a
  hill, a tower's floors). navfeatures.py's floors/stairs/lifts (the other branch) can feed it when it lands.
- **Caves, buildings and dungeon entrances** are walked on the grid where the mesh has them (their models are in it),
  but Caves.lua's and Indoors.lua's roads aren't road links yet, and the planner's portals into dungeons stay as they
  are.
- SPF wasn't run: its comparison scripts are another session's and the open world's 10,000 trips took 1.7 h for our
  two engines alone.
- **Open after bake6** (2026-11-23):
  - Freewind Post's east lift is climbed as a road link, not a ride, with a 25 yd zigzag at its foot and on its top.
  - Darkcloud Pinnacle's small north-west mesa needs Kooki3z's exact stop and start for its test.
  - Blackrock Mountain's lower floor is an island in the grid (#945's underground sweep).
  - The road-import walks (#927, #929, #933, #936, #937, #940) need a region rebake once they're on main.
  - The stand-in route and the search budget are in #952.
- In game: bake5 and bake6 are installed for testing (Kooki3z's tests above). New Lua files and region folders need a relog.

## 12. Thin walls: the models' collision (item 72, 2026-11-25)

The walk mesh's voxels lose a wall thinner than a voxel (a palisade, a fence, a barricade's planks), and the grid's
links ran through it. `agps world-grid models` saves each map tile's building and prop collision triangles from the
client (`<tile>.models.npy` beside its mesh); `world-grid grid` then (worldgrid.cut_wall_links):

- **cuts a link** whose line, at 0.5 and 1.2 yd over its floors, crosses a steep model face, but only where the walk mesh
  runs straight over that spot (walkable just before the wall, at it and just after): a wall the mesh knows (a
  building's inner wall: a gap in the mesh) keeps its link, which stands for the mesh's way round through a door. A
  level link or one linked back (a stair, a ramp) is judged along its line; a one-way drop along a level line at its
  top floor, since it's walked off the edge up there;
- **flags a rim** (F_RIM_WALL, bit 8 of a surface's flags) where a wide wall (three lines 1.5 yd apart) stands across an
  unlinked way out over falling ground within two cells: WorldGrid.FarDrops starts no fall there (Red Cloud Mesa's
  palisade, which the mesh knows: no link to cut, but the search fell 32 yd through it).

The first tries and what they taught (all in the 2026-11-25 bake): judging drops along their straight line cut 1.1
million links (median a 42 yd drop, through its own cliff face); cutting at every wall lost six upstairs innkeepers
(inner walls the mesh knows); a rim flag for any obstacle flagged a fifth of all surfaces (trunks on slopes). The bake
now: 27,199 links cut in 868 tiles (797 on Zephras Isle), about 0.01% of surfaces fewer; the coverage sweep 71 stops
unreached against 72 before, none lost. The bake also needs the full data/ (`need_bake_data`: the lifts' dump and the
terrain's water; a checkout's data/ without them baked no lifts and no seas, silently): AZEROTHGPS_DATA.

`test_world_grid_walls.py` (the rules), `test_world_grid_walls_shipped.py` (89 links the bake cut, from the client's
models: the shipped grid links none of them; the bake before 72 linked 61).

**Model walls, a hard barrier (item 78 the third time, 2026-11-25).** The cuts above judge a link at a few heights over
its floors, and Red Cloud Mesa's palisade leaked twice more: a far drop's top past the rim, a walk off the edge, and the
ends' fallback surfaces (WG.NearStarts) taken across the wall from a spot beside it. Its test's 84 "palisade" segments
were Camp Narache's posts. Now `agps world-grid model-walls --write` (modelwalls.py) rasterizes a region's steep model
triangles, keeps the long thin tall pieces (a palisade, a fence) and ships each one's outline in plan view
(Data/ModelWalls.lua). Passability.CrossesModelWall (and P.CrossesWall, which has their segments) refuses every piece
across one whatever its kind or heights: WorldGrid.Search's steps, far drops and road/drop links (WG.WalledLinks), the
ends' surfaces (Ends, NearStarts, NearGoals), the string pulling, and the Router's legs and spell jumps. The bake's
cut_walls takes them too (worldbake.shipped_walls). Only Red Cloud Mesa's box so far (modelwalls.REGIONS): one piece
from the west cliffs to the east rocks; the way off the mesa north is round its west end, by the road.
`test_palisade_140.py` (five spots inside, spells on and off; every shipped link round the mesa: 998 grid steps and
33 far drops across it, all refused until the next bake cuts them).

**Model walls, the whole map (item 78, 2026-11-25).** The CurseForge page promises fences, palisades and barricades
are walls: `model-walls` now runs over every map tile of the three continents (modelwalls.py's docstring has the
steps). The tests that keep it honest: a cell is a wall's where the steep model faces over it rise 2.5 yd; a piece is
a candidate when 15 yd across, at most 3 yd wide on average, and the ground round it not roofed (a building's walls,
which the mesh has and whose doors the grid's links stand for); then the cells the mesh walks under are left out (a
gate's arch, a lintel, a bridge's beam), and a part is kept when a third of its cells rise 1.5 yd or more out of a
walkable floor beside them (a deck's under-beams, the rocks over a cliff's drop not) and it isn't a closed ring (a
stone circle). Every Router road and recorded walk through a wall opens it 1.5 yd either side, and the capitals are
left to their city grids. The first tries: the zlo-against-neighbors lintel rule cut Red Cloud Mesa's palisade in
eight; a floor within 1.5 yd of the faces' foot lost Cragpool Lake's barricade (its posts are sunk 4 yd); a floor at a
cell's top as "a ledge" broke the palisade where rocks under it reach the rim.

Shipped: Eastern Kingdoms 1,958 outlines, Kalimdor 2,144, Zephras Isle 64 (80,099 points, 512 KB; each outline a string
in half yards, decoded by 512 yd square the first time a route piece comes over it, Passability.ModelWallOutlines for
the whole list). The bake: 47,700 links dropped across walls in Eastern Kingdoms, 45,745 in Kalimdor, 1,708 on Zephras
Isle (the shipped and model walls together); the ALT fields baked again. The Router's roads are cut by walls at load
without the model walls (none crosses one: test_model_walls_140.py), so they aren't decoded at login; the search's
neighbor steps aren't checked either (the bake dropped them), only its far drops and links. The Router's own terrain
ways leave them out too (Passability.SegmentCost, the road graph's joins, UnmarkedFall): the terrain grid doesn't know
them, and with them its walks were refused (route-quality: four Horde trips into the Hinterlands from the west lost);
the spell jumps' straight ways keep to them.

The coverage sweep: the first whole-map bake lost 10 stops (73 unreached before, 82 after): a stall's walls round its
vendor (Se'Jib, Wenna Silkbeard, Marshal Ryan's post, Race Master Kronkrider's stands) and ways through narrower than
the grid's 8.33 yd cells (Zul'Gurub's gate, the railings of the way up Stonetalon Peak to the Cenarion druids: four
druids and a dryad). A wall's part within 2 yd of a stop is now left out, and modelwalls.OPEN lists the reviewed
places (where the older grid's way to each crossed a new wall). After: 72 unreached, none lost, one found (Tiala
Whitemane, Winterspring). The common trips (test_common_trips_settle.py): the same yards, 0.6% fewer nodes, no more
frames.
