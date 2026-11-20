AzerothGPS 1.3.11
=================

Car-GPS style navigation for World of Warcraft: a map window with routes along the roads,
turn-by-turn directions, multi-stop trips, zeppelins and boats, quest areas and more.
Display only: it never moves your character, clicks, or automates anything.

Install
-------
Copy the AzerothGPS folder into your game's Interface\AddOns folder, e.g.
  World of Warcraft\_forever_\Interface\AddOns\AzerothGPS
then start the game (or /reload).

Getting started
---------------
- /agps opens the options (or right-click the minimap button); /agps help lists commands.
- Set a key to show and hide the map: Options, General (or the game's Key Bindings, AddOns).
- Double-click the map to place stops; drag the map to look around, then "Confirm Route".
- Double-click a flight master, town or quest icon to add it as a named stop.
- The + button (bottom-right of the map) imports TomTom /way lines (/way works in chat too),
  copies your route as /way lines, or sends it to a player or your group in game.
- The direction arrow shows the next turn, the stop, distance and ETA.
- Unlock the map, the arrow or the directions text (options: Lock map position / Lock arrow position /
  Lock directions text position) to move them.
- The magnifier (bottom-left) searches places: pick one to add it as a stop.
- The round map button (bottom-left): map type, layers (quests, herbs, ore), and
  "Draw a farming area" to loop through the herb or ore nodes you circle.
- Routes can use flight paths (open a flight map once), including learning a new flight
  master on the way, and your Hearthstone or teleports. The Hearthstone button next to
  the round map button turns the hearthstone on or off.
- Questing (on by default): a stop in a quest's area is done when the quest is; the arrow
  shows a ! and the objective counters there.
- The Sprint button (next to the Hearthstone button): a route through your quest log's
  objectives and turn-ins, in the fastest order.
- Released as a ghost: a red route to your body (skull) comes first, then the rest.
- Dungeons and raids: click an entrance icon for its map (the + and - buttons change floor),
  with its bosses in the usual order; the Boss route button (map menu) routes through them,
  each stop done when its boss dies. The game hides your position inside, so the map shows
  the dungeon and your progress rather than you on it.
- Zeppelin and boat docks show on the map; after you ride one once, they count down to its
  next arrival. Double-click one to add it as a stop.
- Routes keep out of zones too high for your level when there's another way, and ask before
  taking you through or into one.
- Options, Opacity and combat: fade while moving, click-through while moving or in combat,
  and hiding or dimming the map and the arrow in combat.

Guide and bug reports
---------------------
The guide, downloads and news are at https://azerothgps.com
Found a bug, or want to share roads you've drawn? https://azerothgps.com/report
(in game: Options > Help > How to share), or the AzerothGPS Discord.

OpenMap
-------
Past the land, the map's mouse wheel zooms on out through zones and continents to the whole
world on a stitched world map, and back in to the roads. It's the OpenMap map style, the
default; the map button's Map Style group (or Options > Map) has the others: Terrain, World Map
and No Spoiler Map. Point at a zone there for its name and levels. Its map art is Blizzard Entertainment's
and is not covered by AzerothGPS's licence.
Thanks to jigrobbulus, creator of OpenMap, for making it open source so its stitched map could
be built into AzerothGPS: https://www.curseforge.com/wow/addons/openmap

Privacy
-------
Nothing is sent anywhere: addons can't use the network. The optional "Help improve
AzerothGPS" settings (off by default) only keep data in your saved variables on your PC.

Copyright (c) 2026 AzerothGPS. All rights reserved; see LICENSE.txt.
AzerothGPS is a fan-made addon and is not affiliated with or endorsed by Blizzard
Entertainment. World of Warcraft is a trademark of Blizzard Entertainment, Inc.
