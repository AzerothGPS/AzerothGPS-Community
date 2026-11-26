# Underground destinations sweep (2026-11-23)

Kooki3z's ask: "Test known underground destinations like NPCs and make sure it doesn't say jump here to its destination
through a floor that they can't go through. This should route them to the correct entrance."

`agps underground-sweep` (app/azerothgps/undergroundsweep.py) routes, through the whole addon with city and world
routing on (gameharness), to:

- every shipped NPC on the continents standing on a floor of the world grid with another floor 8 yd or more over its
  head (caves, mines, cellars, Blackrock Mountain, the capitals' lower halls), one per 60 yd square, and Undercity's;
- every dungeon's and raid's way in (Data/Instances.lua's portals; the stop just inside, so the walk ends at the portal).

From the nearest flight master of the stop's side, the nearest named place out in the open (one floor, not a cave),
and, for an NPC, a spot on the floor over its head (the player's height given). 646 destinations, 1,830 trips,
about 7 minutes with 4 jobs.

A trip fails with: `noway`; `portal` (a portal into another dungeon); `through` (a drop whose foot is under another of
the grid's floors, or a piece climbing or falling more than one of the grids' links can, 17.8 yd); `bigdrop`;
`overhead` (the walk ends on a floor over the stop's, or 40+ yd under it); `straight` (a straight walking piece near the
stop the world grid can't walk on any floor: through rock or a floor). Notes, not failures: `own` (the last walk is the
Router's own, no floors), `below` (the walk ends at the foot of the stop's building, its floor up stairs the grid lacks),
`steeplink` (one grid link's own climb drawn over a yard).

## Results

| | Before | After |
|---|---|---|
| Failed trips | 129 of 1,830 | 73 |
| Failed destinations | 99 of 646 | 60 |
| noway | 10 | 9 |
| portal | 0 | 0 |
| through | 45 | 25 |
| bigdrop | 0 | 0 |
| overhead | 25 | 19 |
| straight | 65 | 32 |

56 trips fixed, none newly failing ("before": e68edc85 + #928 with this branch's sweep and the old WorldGrid.lua).

## What was wrong (fixed here, WorldGrid.lua)

1. **Joined onto another floor.** A route remembered for the same stop from a start within 60 yd was joined onto with a
   straight line checked on the grid from the start's floor, but never that it arrived on the route's floor: from the
   floor over a cave (or the mountain over Ironforge) the join fell straight through to the route below. Now the join
   arrives within `WG.JOIN_FLOOR_Z` of the route's height, or isn't made.
2. **Spliced onto another floor.** A leg with one end in a capital is the world grid's walk outside spliced onto the
   city grid's inside at the crossing; when the world grid arrived on another floor there (the mountain's top, 714, over
   Ironforge's halls, 504) the splice was a 210 yd fall. `WG.SpliceMeets` now treats that as no walk outside.
3. **No stairs to the stop's floor.** A stop up a tower or inn floor the grid has no stairs to (Kargath's tower, Lakeshire's
   inn) was "no way", and the planner then came at it from farther off, where the Router's straight line was taken:
   72 yd from Kargath's flight master became a 10k yd walk round the Badlands. The reached floors under the stop
   (`WG.UNDER_STOP_YD`, never over it) are now dearer ends: the walk ends at the building's foot and Nav says the stop
   is above (`N.StopOffGround`).
4. **A start shut in on a speck.** A start whose own surface is a sliver the links leave shut in (every search over in
   a few nodes) now searches again from the reached floors round it (`WG.NearStarts`).

## Blackrock Mountain (Kooki3z's live case)

The stop was inside Blackrock Spire (his saved stop: level 20229, (4.85, -410.1)), so the portal was the right ride; the
walk to it was wrong. The world grid has the mountain's lower floor (Blackrock Depths' door, the Masonary, the Molten
Span) as an island: no link up to the upper ring and Blackrock Spire's door (287), and none out to Searing Gorge or the
Burning Steppes. So every leg between the two fell back to the Router's own route, straight lines through the rock
("651 yd to the portal"); in the tests' synchronous runs it is "no way" (cliff). Molten Span to Blackrock Depths with no
heights did walk the grid, but arrived on the mountain's top (276.5) over the door.

His recorded walks (#927: the Molten Span to Blackrock Depths' door; #929: from Blackrock Spire's door down the ramp to
the Molten Span) are the ground truth in test_underground_routes.py (three cases, xfail until the bake takes them in).

## What needs the bake (world grid bake6)

- **Blackrock Mountain:** take #927 and #929's recorded walks as links (feat/world-grid-recorded's rule) so the lower
  floor joins the upper ring; it still needs a walk from either outside entrance (Searing Gorge's tunnel, the Burning
  Steppes' road) to the upper ring, and the Molten Span's bridges (the grid has only the ring at 265 over
  (-7494.7, -1073.4), where Kooki3z stood on the bridge at about 180).
- **Floors the bake never reached on foot** (the stop's floor in the grid but cut off): Uldaman's front entrance
  (209.8, its cave in Loch Modan's south) and Hammertoe Grez in it, Gnomeregan's front entrance (257.2) and train depot,
  Namdo Bizzfizzle, the Sunken Temple's way in (-112.2), Archmage Xylem's tower (Azshara), Nijel's Point's upper floor
  (Brother Anton, Janet Hommers, Talendria).
- **Thunder Bluff's flight master's tower:** 15 failing trips start there; the city grid's walk falls 32 yd in one 2 yd
  step at (-1194, 24) (177 to 144), not a drop. And the Router's own walk up the east lift, (-1026, -30), climbs 80 yd
  in a walking piece (not a lift kind).
- 163 one-link climbs of 8 to 14 yd drawn over a yard (`steeplink` notes): the tower ramps at Aerie Peak (250, -2050),
  Everlook (6750, -4750), Lakeshire (-9200, -2300); real steep links or the bake's heights, worth a look.

## Worst failing destinations after the fixes

| # | Destination | Start | Should enter by | Record this |
|---|---|---|---|---|
| 1 | Blackrock Spire's door (-7524.7, -1228.4, z 287) and Bodley | Thorium Point, inside the mountain | Searing Gorge's tunnel, the upper ring | From Thorium Point through the Searing Gorge tunnel round the upper ring to Blackrock Spire's door |
| 2 | Blackrock Depths' door (-7179.5, -922.7, z 166) | Thorium Point | the ring, down to the Molten Span, the Masonary | From the Searing Gorge tunnel's end down the chains or ramps to the Molten Span |
| 3 | Thunder Bluff NPCs (Una, Sunn Ragetotem, Hamuul Runetotem and 12 more) | Thunder Bluff's flight master | the tower's own way down | From the flight master (Tal) down to the central mesa |
| 4 | Pand Stonebinder, Clarice Foster (Thunder Bluff) | Skywatcher Plateau | the east lift | A ride up the lift from Mulgore with Record on |
| 5 | Sunken Temple (-10176.6, -3995.3, z -112) | Nethergarde Keep, Sorrowmurk | the pit's stairs down to the temple's door | From the Swamp of Sorrows road down into the pit to the portal |
| 6 | Uldaman front (-6066.2, -2954.6, z 210), Hammertoe Grez | Thelsamar | the cave in Loch Modan's south | From Thelsamar's road into the Hall of the Crafters to the portal |
| 7 | Gnomeregan front (-5162.6, 927.8, z 257), Namdo Bizzfizzle | Ironforge | the ramp down from the gnomes' camp | From the camp outside Gnomeregan down to the portal |
| 8 | Brine (-3617.5, -1776.8, z 136) | Brackenwall Village | the path up to her hut | From Brackenwall's road up to Brine |
| 9 | Archmage Xylem (3982.1, -4760.2, z 305) | Talrendis Point, Valormok | the tower's ramp | From the coast road up Xylem's tower |
| 10 | Spirit Healer under Tanaris (-8146.1, -4609.0, z -125) | Gadgetzan | the Caverns of Time's tunnel | From the road down into the Caverns of Time to the spirit healer |
| 11 | Brother Anton, Janet Hommers, Talendria (Nijel's Point) | Nijel's Point's flight master | the inn's stairs | From the flight master up to them |
| 12 | Misha Tor'kren (742.4, -4241.6, z 19) | Orgrimmar | her camp's path | From Orgrimmar's gate to her |
| 13 | Quartermaster Hudson, Veldan Lightfoot (-9650, 660, z 39) | Stormwind | the garrison's door | From the road into the building to them |
| 14 | Captain Gerogg Hammertoe, Malgin Barleybrew (Bael Modan) | Thalanaar | the dig site's paths | From the road into the excavation to them |
| 15 | Razorfen Kraul, Razorfen Downs | Thalanaar | the thorn paths | From the Barrens road into each to its portal |

The full lists: data/debug/underground-sweep/report.json and report.md after a run.
