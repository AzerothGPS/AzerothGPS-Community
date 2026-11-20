# Changelog

Each version's section is its release notes (GitHub and CurseForge).

## 1.3.11 (in progress)

## 1.3.10

### New

- Options: sections collapse and expand with the + or - at the right of their title; the search still finds what's collapsed.
- Options: a Minimap page for the GPS map as your minimap and the game's own minimap.
- Options: Keys and buttons has the map's keys with its quick buttons; Map window is now GPS Map, Opacity and combat is Opacity.
- Options: pictures show the map in its window or the world map, and the game's minimap or the GPS one; click a picture to pick it.
- Options: map redraws, rerouting and stops ahead are picked from a few choices.
- Options > Help: What's new lists the biggest changes of 1.3.
- A one-time setup after this update: pick your minimap (with a live preview and its size) and where the map opens, from big cards with in-game pictures. Works with a controller.
- Run it again any time: Options > Help > Run Setup Again, or /agps setup.
- On a new install, tips show where the route's directions go until your first route is done, instead of the tutorial popup.
- Edit Road: change a road you drew or recorded into ground, a floor, a bridge, stairs or a lift, with its height and stairs on part of it.
- With the road tools on, roads show their kind in color, with smooth corners and their connection points.
- With the road tools on, stairs show stair icons from foot to top pointing uphill, in a color of their own (ramps too).
- A road under a bridge stays apart from it: routes from under the bridge go round to its end.
- Routes can jump off a bridge onto a road below when the fall is safe.
- With the road or wall tools on, the pointer shows the ground's height from the map's data.
- New drawn roads start with the ground's height at each point.
- Edit Road: Set Heights gives a stretch of a road a start and an end height, as stairs or a ramp.
- Walking up or down a road with heights says how far it goes, "12 yd up".
- Edit Wall: make a wall you drew a cliff, with the ground's height on each side. Routes go round it from below and jump down when the drop is safe.
- Over a building's inside map, its roads and walls show for editing, the rest faded.
- With the road or wall tools on, the pointer shows a building's floor heights, and roads drawn there start at the floor's height.
- Roads: new roads and walls in Arathi Highlands, and new roads in Loch Modan.
- Roads: new road to Tarren Mill's flight master.
- Roads: more new roads in Stranglethorn Vale.
- Quest Route can take only the quests you track: the ones Questie's tracker shows, or the ones ticked in the quest log without Questie (Options > Routing). (thanks, DarkByteZero)
- Roads: the way up Grom'gol's zeppelin tower in Stranglethorn Vale.
- Walls: a wall moved in the Wetlands.
- Roads: new road in Desolace, by Shadowprey Village.
- NPCs: the search finds Captain Stoutfist where they stand in the Wetlands.
- Swims on a route show as a wavy line on the map and the minimap; hover one to see why, right-click it to go round by land for that trip.
- Trip times count swimming at swimming speed, or as land with water walking, levitation or Aquatic Form.
- New option, Routing > Allow swimming: off, routes go round by land wherever there's a way.
- The route's directions list swims as their own steps (Walk, Swim, Walk), each with its own time, and the arrow says when to swim.
- With GatherMate2 installed, Import From GatherMate2 in the map menu's herbs and ore group adds its herbs and mines to yours, and every one GatherMate2_Data lists when that's installed; it glows when there's new data to import.
- Options > Map icons: Remove Unconfirmed Herbs and Ore takes out imported ones you haven't gathered, after asking.
- Herbs and veins your skill is too low for say so in red when you point at them, "Requires Mining 125".
- Find Herbs and Ore: Available shows only the herbs and veins your skill can gather, on the map and in its list, and follows your skill as it goes up. Show All turns it off.
- Find Herbs and Ore: the list goes by the skill needed, lowest first; names your skill is too low for show that number in red, and its herb and ore buttons (top right) list only herbs or only ore.
- The road and wall tools' hints are now a list on the map's left, one action a row with a small picture of its mouse button or key; the pointer's tooltip keeps clear of it.
- With the road or wall tools on, click a road or wall to change its kind and heights; the map's own lines show their details.
- The road and wall tools always draw with Shift held (Shift + left-drag draws, Shift + right-drag erases); a plain drag pans the map. The Shift-click drawing option is gone.
- Edit Road and Edit Wall: Delete takes out the highlighted section, the map's own roads and walls too, after asking.
- Search Places: Up and Down pick a result, Enter takes it.
- Search Places: the Pin button is a map pin picture (log out and back in after updating to see it).
- Over a building with the road or wall tools on, its floors stay listed by the tools' hints; Shift + mouse wheel picks one and shows that floor's inside map, remembered for that building.

### Fixed

- In a quest's area, the arrow shows your Hearthstone to click when it's the route's next step, instead of pointing straight up.
- Ironforge: routes go round the Great Forge's lava pits on the walkway, not through the lava. (thanks, DarkByteZero)
- On a client in another language than English, places are found by the name the game gives them: Gnomeregan's Train Depot shows its inside map, not Dun Morogh's terrain; up top in the Ruins of Lordaeron counts as up top; the hearthstone's inn is found; rooms' labels on inside maps are in your language. (thanks, DarkByteZero)
- On a client in another language than English, the herbs and veins you gather are saved: their names are learned from the tooltip's profession line in your language ("Bergbau", "Kräuterkunde"). (thanks, DarkByteZero)
- A farming area's route starts at the node nearest you, and with more than 60 nodes it takes the 60 nearest.
- With Find Herbs and Ore open, the map opened from the minimap no longer closes by itself, and the window closes when that map goes back to the minimap. Its search box no longer sits on the text above it.
- Walks from Tarren Mill's flight master head south-east again, not round by the town.
- Routes no longer swim far out to sea where fatigue sets in, such as from the Wetlands across to Southshore; they keep near the shore.
- A swim you removed, or left out with Allow swimming off, no longer comes back along the shore when the route is worked out again.
- Removing a swim now keeps the route out of that whole bay or lake for the trip; an island with no way by land is still swum to.
- Routes walk round a pond or lake shore when that's quicker than swimming across; with Water Walking (and its Fish Oil), Levitate (and a Light Feather), an Elixir of Water Walking or Aquatic Form, they cross water as if it were land.
- A short swim straight to your stop is no longer passed over for a long way round by road, such as from the Wetlands' marsh to the bay below Stromgarde.
- With several stops, the way to your next stop is drawn over the rest of the route, not hidden under a later stop's way back over the same road. (thanks, DarkByteZero)
- /way lines take the zone in your game's language too ("/way Silberwald 63.4 64.3" on a German client), not only the English name. (thanks, DarkByteZero)
- Clear Route leaves the map where you were looking instead of jumping back to your position.
- The seamless map zoomed in: the sea along the coast shows the terrain, not the blurry world map art (such as off Menethil Harbor).

## 1.3.9

### New

- The route panel at the top of the map can be narrower and sit left, in the middle or right (Options > Map window, or drag its edge).
- Detach the route panel into its own window that stays open while the map is closed (its button on the panel, or Options > Map window).
- The detached route panel can hide its buttons and show only the route's text, and its background can be see-through (Options > Map window).
- Resize the detached route panel by its corner; steps that don't fit show as "... 3 more steps", and long lines are cut short or wrap (Options > Map window).
- Lock the detached route panel in place (its lock button, or Options > Map window).
- The directions text has its own lock, apart from the arrow (Options > Directions, or right-click it).
- Imported routes now visit their stops in the order listed, on by default; untick "Route in the listed order" in Import and Share (or Options > Routing) for the fastest order.
- Roads: new roads in Stonetalon Mountains.
- Roads: a new road in Stranglethorn Vale.
- Extra large map icons (Options > Map icons > Icon size); stops, your arrow and minimap icons grow with it too.
- While routing is paused, the Pause Routing button glows, and a glowing Resume button shows by the logo on the GPS minimap (Options > Map to turn it off). On a controller, Start pauses and resumes.
- The mouse wheel zooms toward the spot under the cursor, on the map window and in the world map.
- Zooming all the way out on the OpenMap style shows Kalimdor and the Eastern Kingdoms together, with both continents' flight masters and docks, and no panning needed.
- Map buttons are drawn sharp at every size, not blurry or jagged.

### Fixed

- Going off course on a long route no longer causes a hitch.
- Jumping off a boat or zeppelin picks the route up again from where you land.
- Messages with one button (like "Got It") no longer show a "No" button when they pop up over the map.
- If routing still makes your game stutter, it works out only the way to your next stop until things are smooth again, and pauses with a message if that isn't enough (resume with Pause Routing or /agps pause); turn this off in Options > Performance.
- Routing no longer pauses for stutter while the game is in the background, or again right after you resume it.
- A trip of several stops asks about zones too high for you, enemy territory and group quests once, not again at each stop, after rerouting or after a /reload.
- Road tools: a recorded walk or drawn road that isn't in the road data yet no longer says it's on the ground; it shows flat until it's added, which works out its heights and stairs.
- Routes from inside Undercity now pick the best flight (Tarren Mill toward Hillsbrad and Arathi, not The Sepulcher and a long walk back).
- The "Enemy territory" message shows once a trip, not again at each stop, pause or /reload, and walking near it off the road reroutes with less work.
- A flight path you haven't learned no longer looks learned on the map while you fly, and only a flight master marks one learned.

## 1.3.8

### New

- Azeroth Pilot Route: follow your Azeroth Pilot Reloaded guide, each step your next stop (shown with Azeroth Pilot Reloaded installed).
- The flight map rings the flight master your route flies to (Options > Routing to turn it off).
- Options > Directions: Arrow side Hide shows the directions text without the arrow.
- Options > Map: Route on the minimap square can leave the route line off the GPS map in the minimap corner.

### Changed

- Options > Directions: "Show the directions" is now "Show the directions text" (off: the arrow alone).
- For plugin addons (API 21): map overlays are told the level the map shows (Undercity's own down there). See docs/api.md.

### Fixed

- Fewer hitches in the first seconds after logging in, while the roads load (smoother on G-Sync and FreeSync screens).
- Routes to Excavation Leader Whelgar in the Wetlands come in from the north through the dig site to his cave, not round the hills.
- Flight masters, zones, cities, places, docks, items and NPCs you've met are shown in your game's language; the search finds them in English too.
- Roads: a new road in Stormwind City.
- Dungeon and raid names are shown in your game's language too, on the map, in the search and in directions.
- Search finds NPCs by their name in your game's language, also ones you haven't met yet.
- Party and raid members show on the GPS map when it replaces the minimap.
- Roads: new roads in the Wetlands.
- A /reload or relog on a flight keeps the route paused and "lands in" counting down; the flight's time is still learned.


## 1.3.7

### New

- Options > General: Show the coordinates (X, Y) turns off the X, Y line at the bottom of the map.

### Changed

- Undo in the road and wall tools takes back only what you changed since your last /reload or login.
- Roads: new and fixed roads in Stormwind City, and the way up the Wizard's Sanctum to the mage trainers.

### Fixed

- Stormwind's mage trainers: the route climbs the Wizard's Sanctum's stairs and goes through its portal, not "below you", and you've arrived once through it.
- Roads drawn or recorded in a city with no floor picked now take the height of the roads they join, rising evenly between them, so routes use them.
- Stormwind: routes from Cut-Throat Alley leave by its west door and cross the plaza to the bridge, not round the canals.
- The No Spoiler Map's explored areas no longer flicker or drop out, and the world map's inset maps no longer show unexplored areas.

## 1.3.6

### New

- Controller support: with a controller active, the open map works from the controller. A sets a stop at the crosshair, X removes one, B goes back, the triggers zoom, the D-pad pans, the left stick press recenters and Y opens the map menu.
- More controller controls: LB selects what's under the crosshair (a dungeon's or cave's map, Confirm Route), RB shows the controls over the map, and LB with X, Y or B clears the route, makes a quest route or pauses routing.
- Options > Controller draws the controller in gold: click a button to choose what it does on its own, held, or with LT, RT, LB or RB.
- The map lists your controller buttons on its left, and each button's icon pulses over what it acts on.
- The controller's marks show only while you use it; touching the mouse hides them.
- The map menu works with the D-pad: up and down the column, left and right along the row, into groups and Quick Find and back out with B.
- Options works with a controller: the D-pad moves, A selects, B goes back, LB and RB change the page, and up reaches the search box.
- With the controller, the crosshair shows the inside of a building or cave, the tooltips of icons (other addons' too) and quest areas, and draws farming areas; B leaves a dungeon's, cave's or city's map before it closes the map.
- Every controller control also works as a macro (/agps pad ...); Options shows each one's line.
- With the game's controller UI on, Show/Hide GPS can't go on a controller button: Options says so and offers the /agps toggle macro instead.
- Pause Routing: keep your stops without working out or drawing the route; the arrow points up as on a flight. It's in the map menu (bottom row, right), shows beside the map button while paused, and /agps pause.
- Options > Performance: "Pause routing when you're not following it" pauses the route on its own when the time to your stop keeps growing. The low-end settings turn it on.

### Changed

- The map's Save and Dismiss buttons and their setting are gone; your changes still save at logout, quitting and /reload.

### Fixed

- The Pause routing slider's title no longer runs into its value.
- Search buttons: the editor's labels are no longer cut off, icons are picked in their own window with a search box, and the rows in Options fit, with a dropdown for where each goes.
- With the map in the world map and Replace minimap on, a dungeon's map is no longer black.
- The minimap moves smoothly down in Undercity and over building maps, no more stutter.
- In Ironforge, the map zooms out twice as far before its city map gives way to the land.
- No more Lua error on every spell cast in combat.
- In the game's world map, inside Ironforge or Undercity the map shows the city's own map, not the land over it.
- In Ironforge, routes to NPCs inside houses (Gerrig Bonegrip in The Forlorn Cavern and others) follow the city's paths instead of ending in a straight line through the rock.
- Up top at the Ruins of Lordaeron, the minimap shows the land, not Undercity; its map shows once you're down the lift.
- Routes to the Deeprun Tram from Stormwind's Dwarven District take the short way inside the district, not round by Stormwind Keep.

## 1.3.5

### New
- Search buttons: make your own searches ("repair", a vendor, an NPC's name) with an icon, name and description; each sets the nearest match as your destination, from Quick Find or as a map menu button. Quick Find's own entries can be edited, removed and restored (Options > Quick buttons).

### Changed

- RestedXP, Zygor, Polestar and Questify Route buttons show on the bar to the right of the map button by default (when that addon is loaded).
- The opened map has its arrow back into the minimap's corner again, beside its bottom-left corner.
- In the game's addon list, AzerothGPS is under Map.

### Fixed

- A stop made from a round icon is round on the map too.
- Removing the only stop leaves the map where you were looking.
- The questing addons' route buttons go gray when off again.
- Saying No to "Risk enemy territory?" keeps the safe way, and it no longer switches to the way through enemy territory while the question is up. It's asked once a route, a /reload too.
- With the game's Gamepad UI on, joining a dungeon no longer gets AzerothGPS blocked (it leaves the group finder's eye where the game puts it).

## 1.3.4

### New

- A route that's one walk lists its turns in the directions, numbered with their distances down to the arrival (the first 3, or all with +).
- Find Herbs and Ore glows while a filter is on (its group's button too), and its tooltip says so.
- Shift-click a stop's marker on the map to link it in chat as a map pin anyone can click.

### Changed

- The map menu's Boss Route button is now Show Routes: off hides a dungeon's dotted way through (on by default). /agps bosses still starts a boss route.
- Map icons stay crisp at every size: the game's icons the map uses are drawn to scale, like the round icons' rings.
- Avoid enemy territory goes by the NPCs that would flag you for PvP: the other faction's guards as before, and their quest givers, vendors and flight masters lightly (a route bends round them when it's cheap). Posts that flag no one, like Hillsbrad Fields' Footmen, aren't enemy territory any more.
- Roads: new road in Dun Morogh, in the North Gate Pass.

### Fixed

- Options > Map: Reset to defaults resets the inside-map sliders too, and is no longer gray when only they were changed.
- Roads: new roads and walls in Hillsbrad Foothills, by Thoradin's Wall too.
- The North Gate Pass tunnel, Dun Morogh to Loch Modan, is a way through again: no detour by the South Gate Pass.
- With Avoid enemy territory on, a walk goes round the other faction's towns even through zones too high for you (they're asked about as before).

## 1.3.3

### Fixed

- The map in the game's world map: its questions (keep this route?) take clicks again.
- Walls you draw no longer cut roads: a road through one is still a way (a wall stops walking only).

## 1.3.2

### Changed

- Quest areas: on the map and on the minimap are two options (Options > Show on the map).
- The Map Style quick button is hidden by default (Options > Quick buttons puts it back; the style is in Options > Map too).
- Dungeon and raid maps sit on the terrain round their way in, as caves' do; panned or zoomed well away, the map closes.
- In a city with your next stop outside it, the route isn't worked out again while you're on it: less lag in cities.
- The arrow doesn't look past stairs until you reach them, then points along them to their other end.
- In a quest's area, the arrow's "!" is the small faded one at its top right, never a big one in its place.
- Options > Directions: the questing objective tracker is first.
- Roads: new road in Teldrassil, by Wellspring Lake (shared by a player).

### Fixed

- OpenMap in a building, zoomed far out: the map shows the land, not the building's map over a continent of terrain tiles.
- The map's zoom no longer drifts out at each /reload until it opens on the whole continent: it follows only your own resizing.
- Undercity: your floor is followed along the roads you walk, not onto a walkway overhead, and taken again after you drop down a floor: no more "Take the stairs down" or "17 yd down" where you already are.
- The GPS map as the minimap: the game's quest area circle no longer comes back over it; with Quest Areas off, the game's show instead.
- In the Deeprun Tram the route is followed like a flight ("Riding the Deeprun Tram to Stormwind City"), not worked out again from inside it.
- A flight to Undercity off the route's way is followed as a flight: where it lands, when, the arrow paused.
- "Close the map when I start moving" closes it with the search open too, and the map menu and search with it.
- Standing in a building in Stormwind, Orgrimmar or Darnassus shows its inside map, as hovering it does.
- The Deeprun Tram's map is drawn on its world map, not on black.
- Hovering a big cave or cavern shows its inside map (Blackrock Mountain, Feralas's and Tanaris's caverns), and Ironforge's.
- Zoomed in over Undercity or Ironforge from outside, the whole city's map shows.
- Routes from Thunder Bluff to the Camp Gev'rek zeppelin no longer go round the Barrens for the first few seconds.
- Ironforge's inside map on clients in other languages (the mountain's terrain showed instead).
- Flight times are learned on flights taken with no route set.
- OpenMap: Reset to defaults now puts the continent-to-world stage back to the shipped one.

## 1.3.1

### Fixed

- Stutter in Undercity and on flight paths with the map open.
- Routes no longer land and take a second flight mid-way when one flight goes straight there.
- /agps show, hide and toggle open and close the map in minimap mode and in the world map, as the key does.

### Changed

- Roads: new road in Mulgore, east of Thunder Bluff.
- Routes use a road's loose end across open ground when the roads go far round (Thunder Bluff to the Camp Gev'rek zeppelin).

## 1.3.0

### New

- OpenMap: zoomed in, hover any building or cave on the map to see its inside map; a slider in Options > Map sets how close.
- Stormwind's buildings have inside maps too, as Orgrimmar's; its streets show the terrain.
- Hover any cave, zoomed in, to see its whole map, as opened from its icon; its edge a thin black outline as buildings'.
- OpenMap: a cave's or building's inside map shows over the terrain with its black outline, never on its world map's parchment.
- Click a building's inside map to hold it for a while (Options > Map), shown with any other you hover; right-click to put it away until the mouse leaves.
- Inside maps show the NPCs who offer something there: trainers, vendors, repair and more by their icon, others as a dot; hover for the name.
- Round icons on the map and minimap, in a gold ring or a class trainer's class color (Options > Map icons, on by default).
- Icon size: small, medium or large map icons, party and raid members' too (Options > Map icons).
- Sliders in Options > Map icons for how far out each kind of icon still shows: herbs, ore, city locations, pins, caves and more.
- Opening the GPS map from the minimap square keeps the square as it is, both shown (Options > Map, on by default).
- A Quick Search key (Options > General) opens the map with the search box ready to type in.
- Search for an item a vendor sells ("sharp arrow", "ice cold milk") to find the nearest vendor that has it; opening a vendor's window learns its real stock.
- Quick Find: a quick button above Search Places for a stop at the nearest repair, vendor, innkeeper, flight master and more (hunters: arrows or bullets); right-click lists them all.
- Hover our icons on the minimap for their name: an NPC as "Karus (Banker)", a city place by its NPC, pins, herbs and more.
- Double-click a quest in the quest log, the objective tracker or Questie's tracker to route to it, or add it to your route.
- Closing the map with stops picked but not confirmed starts the route.
- Search: type what and where together, "tailor tarren mill", "repair undercity", "brill innkeeper".
- Search: the start of a kind is enough, "rep", "vend", "inn" (three letters or more).
- OpenMap: sliders in Options > Map for how far out the terrain gives way to the zone map, the zone map to the continent map, and the continent map to the world map, each with a transition slider for how long it blends.
- Road and wall tools: a Magic Eraser puts the map's own roads or walls back wherever you drag it (Ctrl + mouse wheel sizes it).
- Road and wall tools: Restore Zone and Restore Continent put a whole zone or continent back as the map has it, after asking.
- Road and wall tools: Shift-Click Drawing (on by default), so the tools draw only with Shift held and a plain drag pans the map.
- Routes through the other faction's territory are drawn red on the map and minimap, and you're told where in chat and the directions.
- OpenMap: inside a building the terrain shows round its rooms, on the map, the minimap and the world map.
- Search: "repair" and "vendor" list the vendors you've talked to, nearest first; "class trainer" finds trainers you've talked to as well.
- Search finds every NPC of your faction (and neutral ones) without talking to them first: by name, title, "repair", "innkeeper", "banker" and more, nearest first.
- Search: a Pin button beside each NPC and city place pins it on the map for good, with an icon for what it is.
- Other addons can now act on Shift-clicks on NPCs.

### Changed

- Search Places: its hover is just the how-to; what it finds and the Pin button are explained in Options > Help.
- Orgrimmar and Darnassus: out in their streets the map shows the terrain, not the city's model art; inside one of their buildings, that building's map alone with the terrain round it.
- A building's inside map over the terrain has a thin black edge round its own shape, not dark squares.
- The road and wall tools are one Map Editing button (Options > Tools: Map editing tools). Open, the roads and walls show; it closes by itself after 2 minutes unused (adjustable).
- Road Tools and Wall Tools glow in the open Map Editing menu until one is turned on.
- The Magic Eraser shows its whole circle filled, and its stroke as wide as the circle.
- The tutorial's list marks sections (new) or (updated) since you played them; the road section covers Map Editing and the Magic Eraser.
- A cave's or city's map you opened closes by itself, right where you are, once you pan far away or zoom well out.
- Inside maps show NPCs of both factions; the other faction's city guards are hidden.
- A whole city's inside map (Undercity, Ironforge) doesn't show its NPCs: only a building's own inside map does.
- "Key doesn't show the map in combat" is on by default, and covers the Quick Search key too.
- OpenMap: the terrain slider's transition is gentler and goes further in.
- Smaller stairs icons on the route.

### Fixed

- Orgrimmar: walked down into the inn, Innkeeper Gryshka is no longer shown "below you" with the route going out and round.
- A stop off the roads is reached from the nearest road on its other side too, not the long way round (Duskwood's river below Elwynn).
- Other addons' own windows (StreetView's viewer) can show over the map opened out of the minimap square.
- Inside maps in Orgrimmar, Stormwind and a few other places no longer draw a big box of the street's art askew round a building (its bank, the Hall of Legends).
- Orgrimmar: flown in or up the Wind Rider tower's ramp, the Wind Rider Master on top is no longer "above you", and you arrive.
- With the GPS map as your minimap, the map grown out into its window takes Map opacity again.
- Avoid the other faction's towns: a stop just outside one no longer counts as in it, so the route goes round it (Southshore as Horde).
- The directions' "Through enemy territory" line goes away once the route shown no longer passes the guards.
- Leaving a capital on foot, the walk goes straight across the land past its gate (Orgrimmar across the Southfury River), not round by the roads or a flight.
- OpenMap: Undercity and caves show the terrain round them too, like buildings.
- Flights, zeppelins and boats keep their light blue dotted line when the trip has several stops.
- Avoid zones too high: the road through one (with the usual warning) wins over a long swim round it.
- Avoid the other faction's towns: routes bend round single guard posts, and a safe way round is taken unless it's 30% slower; then you're asked whether to risk it.
- Zones too high for your level are asked about once per trip, in one popup.
- No more straight-line swims down the coast in place of the road (Tarren Mill to the Wetlands as Horde).
- While a new route is still being checked, it shows the walk instead of a far-off flight it may not take.
- Less CPU while walking with the map zoomed in on a route.
- Less CPU and fewer hitches while walking off the route among a town's buildings.
- Roads: new roads in Ashenvale.
- Roads: new roads in the Badlands, Loch Modan and the Swamp of Sorrows.
- Roads: stray roads removed by the Southfury River in Durotar.
- Questie's icons show on the GPS map again with Questie 12.9.0.
- Quest areas in the world map view are no longer drawn twice (too dark).
- Seamless map: roads and walls stay shown a little past the terrain, and are left out further out (also with the road and wall tools on) to save performance.
- Every addon's icons on the game's world map now show on the GPS map too, not just those of the common map libraries.
- A stop at an NPC in a capital city or a cave is routed to that NPC's floor (the Cleft of Shadow, Undercity's rings, upstairs shops), guide steps included.
- Routes in caves and mines with floors over floors (Fargodeep Mine, the Wailing Caverns' cave and more) take their ramps to the right floor, and a stop on the ground over a mine stays on the ground.
- Routes no longer hop over a cliff or wall to a road (the dotted line) when a road can be reached over open ground.
- Undercity: standing on the ring under a walkway, a nearby stop is no longer routed up and round the Trade Quarter or shown "below you"; talking to an NPC there sets your floor.

## 1.2.8

### Fixed

- Stuttering while running through a city with a route on.
- A flight path learned by talking to the flight master (without opening the flight map) is no longer forgotten after logging out.
- Roads: better roads at Splintertree Post in Ashenvale.
- Routes out of Undercity's Sewers follow the tunnels and stairs out into the city.

## 1.2.7

### New

- Option to route to the quest you pick in your quest log or objective tracker (Options > Routing).
- Route Here: a button in the world map's quest details, and in the quest log's and objective tracker's right-click menus.
- Debug log in Options > Help: tick it, do what goes wrong, then export it to send with your report.
- A herb or vein you gather that the map hides (its layer off, or not picked in Find Herbs and Ore) now says so in chat.

### Changed

- The road and wall tools, and the roads and walls shown, turn off after 2 minutes without using the map (it says so in chat).

### Fixed

- Less CPU use with the GPS map in the game's world map, and zoomed far out.
- Short stutters while a route is active, when it passes a flight master you haven't learned yet.
- Roads: new and better roads in The Barrens.
- Roads: new road in Ashenvale.
- Roads: new roads in Stonetalon Mountains.
- Herbs and ore you hover on the minimap are saved again, with the GPS map as your minimap too.
- The map in the game's world map is right on the first open after a /reload (it was zoomed in, with no route).

## 1.2.6

### New

- Polestar Route: follows your Polestar guide, each step your next stop; on by itself with Polestar installed, its quick button turns it off.
- Questify Route: the same for your Questify guide.

### Fixed

- Stutters with the map in the game's world map, when the view was near a zone's edge.
- RestedXP Route: already at the place a "travel to" step leads to (Apothecary Zamah in Thunder Bluff's Pools of Vision), the route goes there, not back to the way in.
- Walks off the roads can swim across the sea over a steep seabed (Alterac's coast to Silverpine), instead of going the long way round.

## 1.2.5

### Changed

- Options: "Show the GPS map in the game's world map" is at the top of the Map page.
- Options: the settings for the game's minimap, and the map window's opacity, fading and turning, say where they apply and are grayed out where they don't.

### Fixed

- In the game's world map, the map no longer fades or lets clicks through while you move; it fades with that window.
- With the map as your minimap, opening it from the square in a fight no longer leaves it the square's size, and sending it back no longer leaves it big without its buttons (asked for mid-fight, it goes back once the fight ends).
- With the map as your minimap, the game's minimap shows in its corner while you open the map during a fight.
- With the map in the game's world map, the logo, the minimap button and the key no longer fail in combat ("Interface action failed because of an AddOn"): during a fight the map opens in its own window instead.
- Fewer short stutters while a long route is being worked out.
- Questie's and other addons' icons on the map show their own tooltip when hovered, not "Another addon's map icon".
- Other addons' icons no longer jump out of place for a moment when zooming the map in the game's world map.

## 1.2.4

### New

- Directions say when to enter or leave a cave, go into or leave a building, and cross a bridge.
- The map's search finds the cities' and towns' trainers and services by their names in the addon's language ("Bergbau"), and the map shows those names.
- Option to remake the quest route by itself when you pick up or finish a quest (Options > Routing); the first click on the pulsing Sprint icon offers it.
- Quest stops you remove stay out of the quest route when it's remade.
- Option to keep AzerothGPS's messages out of the chat window (Options > General); /agps commands still answer.

### Changed

- Roads: better roads in Stonetalon Mountains.

### Fixed

- Thunder Bluff: the route to the lower bridge to Elder Rise goes through the tent at its end, not around it.
- Orgrimmar: routes from the Valley of Strength to the Valley of Spirits and the Cleft of Shadow go up the Wind Rider tower's spiral, not around by the Drag.
- With the map closed or as the minimap, questions like Keep / Leave Out for an elite quest pop up next to the directions.

## 1.2.3

### Changed

- On a quest route, finishing a quest makes the Sprint icon pulse too: click it to add the turn-in to your route.
- Roads: new roads in The Barrens.

### Fixed

- In the game's world map on Zephras Isle, the game's own map no longer shows as a small picture over the GPS map.

## 1.2.2

### New

- Profiles: save all your options under a name, and choose which profile each character uses (Options > Profiles).
- As the minimap, you choose how long the opened map waits before it goes back to its corner, or never (Options > Map).

### Changed

- Reset to defaults in the options asks first.
- The direction arrow and the directions are unlocked on a new install: drag them into place, then right-click either one to lock them.
- If yours were locked, they're unlocked once, with a popup that says so and offers to lock them again.
- Question popups have the AzerothGPS title bar and logo, like every other window.
- The map's bottom-left button is named Map Menu.
- Roads you draw or record show green and your walls yellow, so you can tell them from the map's own.
- The route updates as soon as you draw a road or a wall, not when the tools are turned off.
- As the minimap, a left-click on the AzerothGPS minimap button opens the map and sends it back, like the square's logo.
- The minimap square follows the game's controller UI when it is switched on or off.

### Fixed

- In the game's world map, the map's buttons are no longer covered by map icons, other addons' included.
- With the game's controller UI on, no more "blocked from an action" errors: the GPS map opens in its own window there, not in the game's world map.

## 1.2.1

### Fixed

- As the minimap, the square no longer shows a dungeon's map: not on the way in, not after leaving, not after a /reload, not when the opened map is sent back.
- As the minimap, the square is no longer black on the way into a dungeon until you move.

## 1.2.0

### New

- RestedXP Route: follows your RestedXP guide, each step your next stop; on by itself with RestedXP Guides installed, its quick button turns it off.
- Zygor Route: follows your Zygor guide the same way; on by itself with Zygor Guides installed.
- The GPS map can replace the minimap: a square in the minimap's corner in three sizes, opened to the whole map with a click or the show/hide key (Options > Map, or /agps replace).
- As the minimap, the opened map goes back to its corner after 5 quiet seconds; options send it back when you move or when combat starts.
- The GPS map can show in the game's own world map window instead of its own, with its route, buttons and map styles (Options > Map).
- Other addons' world map icons (quest helpers, guides, waypoints) show on the GPS map too; double-click one for a stop there.
- In the game's world map, double-click any icon (quests, other addons' icons) for a stop there.
- AzerothGPS shows its text in your game's language (all WoW languages); Options > General or /agps language picks another.
- A Help page in the options: what's new, the commands, the website and Discord, and sharing map data.
- A short tutorial shows the main features on your own map, offered at first install and after big updates; replay any part in Options > Help or with /agps tutorial.

### Changed

- Options reorganized: one page for the map (its style, the minimap, its window) and one for its icons; dependent options are indented and grayed out.
- Every AzerothGPS popup window has the AzerothGPS logo on its corner.
- Double-click the GPS map's logo to minimize the map to just the logo; double-click the logo again to bring the map back.
- Right-click the GPS map's logo to open the options.
- Less CPU while standing still, most of all with a route set.
- As the minimap, the square always shows the OpenMap map, whatever map style is picked.
- Options: a search box at the top filters the settings as you type.
- As the minimap, the square shows the game's own minimap inside dungeons, raids, battlegrounds and arenas, so it still follows you there.
- No direction arrow or directions in battlegrounds and arenas.
- As the minimap, the game's zoom buttons sit in the square's bottom right corner and its day and night button on the top right corner.
- Picking another language shows an Apply button that reloads the UI.

### Fixed

- Roads: new roads in The Barrens.
- Roads: new road in Stonetalon Mountains.
- Roads: new road in Searing Gorge.
- Routes between Ashenvale and Stonetalon Mountains go through the Talondeep Path instead of around by the Barrens.
- Routes between the Western and Eastern Plaguelands can go through the Terrorweb Tunnel.
- Talking to a flight master no longer works the route out again unless you learned a new flight path.
- A newly discovered flight path is used in routes right away, without opening the flight map.
- Routes into Un'Goro Crater go through the pass from Tanaris, not over the crater's wall.
- The route to Orgrimmar's transmogrifier goes down into the Cleft of Shadow.
- In Darnassus, a route from partway down the spiral stairs carries on down instead of climbing back up.
- The arrival confetti and fireworks now play, on arriving and on Try It.
- The map no longer stops redrawing when the game hides a teleport's cooldown.

## 1.1.16

### New

- Questie's "Set TomTom Target" (right-click a tracked quest) adds that spot to your route, with or without TomTom.
- Ctrl + left-click a stop on the map to copy it as a /way line.

### Changed

- Horde Skyborne start out knowing the Thunder Bluff and Orgrimmar flight masters, so routes fly between them.
- A route to another continent stays on the seamless map: it zooms out to show both ends instead of switching to the world map.

### Fixed

- Roads: a new wall in Darkshore.

## 1.1.15

### Fixed

- OpenMap shows Zephras Isle's revealed map, not its blank parchment.

## 1.1.14

### Changed

- Quest Route: a quest with its area in more than one place goes to the place that fits the route best.
- Quest Route: when a quest leaves the route (done or removed), the rest are put in the best order again.
- Quest Route: red quests (5 or more levels above you) are offered to leave out, as group quests are.
- The detour to a flight master you haven't learned follows the roads where it can.

### Fixed

- The Discord invite link works again.
- A wall drawn with the wall tools changes the route right away, not only after the tools are turned off.
- "Turn the map with me" turns the OpenMap map again at the usual zooms.

## 1.1.13

### New

- Find Herbs and Ore (map menu) shows only the herbs and veins you pick, and each node on the map shows the icon of what it gives.

### Fixed

- Routes to a stop deep in a cave, like Ban'ethil Barrow Den, go round to its way in instead of straight over the hill.
- The route on the game's minimap no longer flickers off and on while you walk.
- Roads: a new road and walls in Teldrassil.

## 1.1.12

### New

- The Ruins of Lordaeron and the Hall of Thanes show their bosses, the usual way through and the boss route on the dungeon map.

### Fixed

- Zoomed out on the OpenMap map, your quests' objectives and turn-ins stay on the map.
- The minimap shows only the way to your next stop, not later stops' paths or the one on the land over Undercity.
- The direction arrow no longer swings toward the route when you head the right way a little beside it, in cities or out on the roads.
- WoW Forever's own herbs and ore veins, like Stunted Silverleaf, are saved on the map when you gather them.

## 1.1.11

### Fixed

- Characters with the same first name no longer share their route, flight paths and hearthstone home.
- Search Places finds the weapon masters for "weapons trainer", and generic searches work in the plural ("flight masters").
- Coming down a building's stairs and walking out, routes no longer send you back in and up the stairs first.
- Routes that save your hearthstone for after a stop now say so, even with the steps collapsed.
- Only real herbs and ore veins are saved on the map: no more quest creatures or ground pickups as herbs.

## 1.1.10

### New

- Options > Window: confetti or fireworks when you reach your trip's last stop (or none).
- Options > Window: a color for the map window's frame, its buttons and its X.
- Options > Window: the route in blue or a rainbow.
- Options > Window: a legendary weapon charm hanging from the AzerothGPS logo, swinging as you go (off by default).
- Options > Routing: Road tolerance, to keep routes on the roads more or cut across open ground more.
- Every dropdown in the options is the game's own.

### Fixed

- The window frame's button colors change only the map window, not the options window or popups.

## 1.1.9

### New

- Search Places finds your faction's trainers and services in the capitals and starting towns without talking to a guard first ("Rogue Trainer", "Skinning Trainer", "Bank").
- Search Places understands "Class Trainer", "Profession Trainer" and "Flight master", and lists the nearest first with how far each is.
- Caves and mines such as Fargodeep Mine and the Burning Blade Coven show a full map of their own, inside them and when opened from the map.
- The teleport button shows the time left while the hearthstone or teleport is on cooldown, and says when it's ready if clicked.
- When your hearthstone or a teleport comes off cooldown, the route is worked out again to see if it's quicker with it.
- For the released WoW Forever: install into `World of Warcraft\_forever_\Interface\AddOns`.
- The map zooms seamlessly out to the whole world: past the land, the mouse wheel goes on through zones and continents on a stitched world map, and back in to the roads.
- Four map styles: OpenMap (the new default), Terrain, World Map and No Spoiler Map, in the Map Style buttons, Options > Map and /agps style.
- Maps on the old default Terrain style move to OpenMap; Terrain is one click away in Map Style.
- Past the coast and the edge of the land, the zoomed-in map shows the world map's sea and coast instead of black, fading in right along the shoreline.
- City, dungeon and cave maps zoom out to the world too, and back in to them.
- Dungeon, cave and building maps show the world map around their rooms instead of black, with a soft edge.
- Point at a zone on the zoomed-out map for its name and levels.
- Zephras Isle shows on the zoomed-out world map as an island in the sea, and zooms back in to its terrain.
- Zooming in, the zoomed-out map goes from the world to the zone maps, then to the terrain close in.
- New option (Map): Show Only Explored Areas, for the zoomed-out map.
- Right-click on the map zooms out a few steps on the same spot, up to the whole world.
- /agps follow puts the map back on you.
- The direction arrow and its directions are two windows: drag the arrow off to move it on its own, or drop it against any side of the directions to snap it there.
- New options (Directions): Arrow size, Text size, Directions background, Show the directions and List the stops only. Arrow background is the arrow's alone.
- Thanks to jigrobbulus, creator of [OpenMap](https://www.curseforge.com/wow/addons/openmap), for making it open source so its stitched map could be built into AzerothGPS (credited in Options > Help improve).

### Fixed

- Resizing the directions from their corner no longer sticks.
- On a square minimap from another addon (such as EllesmereUI), the route and icons reach its corners. Options > Map has a Minimap shape setting too.
- The minimap button stays in another addon's button drawer instead of jumping back over the minimap.

## 1.1.8

### New

- Pick the color of a dungeon's dotted path with the Path Color button at the top right of its map.
- New option (General): the show/hide key doesn't show the map in combat.

### Changed

- Icons on the minimap is off by default (Options → Map → Icons on the minimap to turn it on).
- Roads: new roads in Orgrimmar.
- Roads: a new road up the stairs in Ironforge.

### Fixed

- In Darnassus, the route to the Rogue Trainer goes down the spiral stairs to his floor and back up.

## 1.1.7

### New

- Quest areas are tinted inside, so you can tell you're in one at any zoom.
- Starting to draw a road by hand suggests Record instead, which keeps the floors and stairs (Options → Tools to turn it off).
- Fall into a capital's canal or lake and the route swims you to the nearest way out, not up the wall.
- The map's icons show on the game's minimap too: pins, herbs and ore, party members, city places, docks and entrances (Options → Map → Icons on the minimap).
- 16 dungeons have their world map: under the dungeon's own map in the terrain view, on its own in the world map styles.
- **For plugin addons (API 17):** button colors in the window frame look, on every AzerothGPS window and on their own, shown true. See docs/api.md.

### Fixed

- Right after logging in with a route, the arrow no longer hitches.
- Inside buildings the arrow points at the next corner, not through the wall.
- A new route's shortcut across country is found sooner.
- Beside a building's stairs, your floor is no longer taken for the one below.
- Routes no longer climb a cliff to reach a road on a mountain ledge (the way up to Ironforge's gate).
- On spiral stairs in cities, the arrow keeps following your floor to the top.
- In Stormwind, the street along the canal by the rowboats no longer leads you off the walkway into the water.
- In Ironforge, routes from the Mining Trainer's door no longer go out over the mountain.
- In Orgrimmar, the way to the Leatherworking Trainer goes in by the hut's door, not through its wall.
- A new route shows at once, faded, while a shorter way is still being looked for.
- In the capitals, routes no longer tell you to jump out of a window or over a railing.
- Search no longer offers the other faction's zeppelins.

## 1.1.6.1

### Fixed

- Quest areas no longer go missing after a fight.
- A stop made from a quest's map icon shows its objectives and counts as done when the quest is complete.

## 1.1.6

### New

- Distances in yards, meters or feet (Options → General → Show distances in).
- Cave maps: click a cave or its entrance icon to open its map; right-click to go back.
- Routes inside the buildings of six more towns: Goldshire, Kharanos, Dolanaar, Bloodhoof Village, Razor Hill and the Crossroads.
- Routes up or down the stairs to NPCs upstairs or in cellars, in about 80 more buildings across the world.
- NPCs you talk to are remembered on their floor; routes and quest stops for them go there.
- In capitals, AzerothGPS follows your floor and says when a stop is above or below you.
- Road tools: point at a road to see its height.
- Road tools: draw on a building's floors (Shift + mouse wheel) and draw stairs with the new Stairs button.
- Road tools: Record draws a road as you walk it.
- Nothing you've built up is dropped anymore: drawn roads, trips and the places you met NPCs are kept.
- Search can find NPCs met in several places (Options → General → Search).
- Quest Route: each group quest shows as kept or left out in the directions, with a button to change it.
- Herbs, ore and city places a guard showed you now count for Save Now.
- A notice when your saved data gets large; imports too large for it are turned down.
- Less memory used.

### Fixed

- Routes go into buildings by the door, not through the walls.
- Routes into or out of a building take a shorter way outside.
- Shorter walks across country where the roads go the long way around.
- Fewer flights that save time are passed over.
- Routes off Teldrassil take the Darnassus teleporter, never a walk down the tree's side.
- Routes out of more caves.
- Fewer stutters while following a long trip.
- Less CPU on long walks off the roads.
- Less CPU drawing a large map while moving.
- Less CPU standing still, with the map idle and from the direction arrow.
- Recalculations on long trips cost less CPU.
- Routes keep being worked out with the map hidden and the arrow off.
- Map icons slide smoothly with the map while moving, not in little hops.
- Undercity: standing under a stop on a walkway no longer counts as arriving.
- Search no longer offers NPCs of the other faction (met on another character).
- Retired flight masters no longer show on the map or in routes.

### Changed

- Reports go to azerothgps.com (Options → Help improve).

## 1.1.5

### New

- **Save Now.** The game only saves addon data when you log out, quit or /reload, so if WoW crashes, the pins you made or removed, the roads and walls you drew and the dungeon entrances learned since then are lost. While there's something unsaved, **Save** and **Dismiss** buttons show over Clear Route. Point at Save to see what's waiting; click it to save right away (it reloads the interface, only when you click it). Dismiss hides them until your next change, if you'd rather take the risk; right-click Dismiss and they stay hidden until you /reload or log out, or Shift-right-click it and they stay hidden until you log out, even after a /reload. To never see them, untick **Remind me to save** (Options > General > Saving). Both are hidden in combat. The pin window also says when a pin is saved.
- **Search finds NPCs you've talked to.** The game doesn't tell addons where NPCs are, but when you talk to one (to chat, buy, train, take or hand in a quest, fly, bank), you're standing by it, so AzerothGPS remembers it by its name and title ("Innkeeper Renee  Innkeeper, Brill"). Search for it later to make it a stop. Only one-of-a-kind NPCs: guards and anyone you've met in two far-apart places (a supplier in every town) are left out. NPCs aren't drawn on the map. You can import a list of them too: tick **Import as NPCs** in the waypoint window and paste `/way` lines with their names; talking to one confirms where it is.
- **Quest route: group quests ask first.** An elite quest, or one that suggests more than one player, asks whether to keep it in the route (Keep or Leave Out), once per quest until you /reload or log out.
- **Quest route stops are done by the quest.** Reaching a quest's spot no longer finishes it. Within 80 yards its objectives show and the route waits until they're done, quests with no area too, and a turn-in is done when you turn the quest in, not when you walk up. A quest turned in, finished or dropped on the way comes off the route.
- **Sharing in a group.** In a party or raid, the directions panel has a **Share** button that puts your route's link (the quest route too) in party or raid chat for you to send. Right-click a group member's icon on the map to ask them for their route: they're asked whether to send it, and you're asked before it replaces yours.
- **Share a pin in chat.** Shift-click a pin and a line for it goes in your chat box for you to send. Players with AzerothGPS click it to add the pin to their map, icon and floor included (they're asked first).
- **Your route on the game's minimap.** The way around you and the next stop's marker show on the minimap too (on its edge while the stop is further away), turning with it if yours rotates. Options → Map: **Route on the minimap**.
- **Less redrawing.** The minimap's route is drawn again only when something on it changed, and on the map, lines that haven't moved since the last redraw are left where they are.
- **Upstairs and downstairs.** Brill's and Goldshire's trainers upstairs in the inns, and Goldshire's Warlock trainer down in the cellar, say so: "(upstairs)" in the steps, "Upstairs: ..." once you're close, a stairs badge on the stop's marker, and the route's last yards into the building dotted in purple.
- **Share your map data with other players.** The **+** window is now **Import and Share**, and it has **Copy My Map Data**: the herbs and ore you've gathered, the NPCs you've talked to, your pins, and the roads and walls you've drawn, as lines to paste anywhere (tick what to include). Players with AzerothGPS paste them into the same window and press **Import** to add them to their own map: herbs, ore and NPCs show as unconfirmed until they find them themselves, and roads and walls work for routes right away. The window says what was added, what they had already, and which lines it couldn't read and why. Pins shared in chat can be pasted in too, many at once. Everything pasted is only read as data, never run, and it only ever goes into your own map. The boxes for /way lines are now **/way as herb/ore nodes** and **/way as NPCs**.
- **An import inbox.** A tool on your PC can leave map data for AzerothGPS (herbs, ore, NPCs, pins, roads and walls, the same lines as the Import and Share window). At login AzerothGPS says what's waiting and asks before adding it to your map; say no and it's not asked again. It's only ever read as data, and it never changes your route.
- **Routes inside buildings, starting with Brill.** Brill's inn, town hall, blacksmith and farmhouse have their insides mapped, floors and stairs included. A route to a trainer upstairs in the inn goes in by the door, along the ground floor and up the stairs ("Take the stairs up"), and the stairs icon sits on the stairs, not by the trainer. WoW Forever doesn't tell addons your height, so AzerothGPS follows your floor along the building's roads as you walk: once you're upstairs, "(upstairs)", the purple stairs color and the hint go away for every stop up there, and standing under a trainer on the ground floor no longer counts as arriving. If you /reload or log out upstairs, it remembers you're up there.
- **Stairs in Undercity.** Down in Undercity, where the route goes up or down a floor, a stairs icon marks the spot on the map, as in dungeons.
- **Undercity knows which floor you're on.** WoW Forever doesn't tell addons your height, so AzerothGPS follows your floor along Undercity's roads from the lift you came down (it only changes on stairs, a ramp or a lift). Routes start on your floor, not on a walkway over your head, and "12 yd above you" works down there.
- **Darnassus's teleporter to Rut'theran Village.** The portal in Darnassus's Temple Gardens down to Rut'theran Village, and the one there back up, are part of routes now, like a lift. A route from Darnassus or Dolanaar to Rut'theran Village, or on to the boat to Auberdine there, walks to the portal and says "Take the teleporter to Rut'theran Village". Before, routes had no way down and went straight down the side of the tree.
- **Your finds stay yours.** Pins, the NPCs you've talked to, and the herbs and ore you've found are never put into AzerothGPS's own data: they're yours to share with other players.
- **No combat log in dungeons.** Entering a dungeon or raid, AzerothGPS listened to the combat log for boss deaths; this client keeps the combat log from addons, and asking for it can bring up a "tried to call a protected function" error. It's gone: a boss's kill still counts from the game's encounter events, from a dead boss you target or point at, and from right-clicking it on the dungeon's map.
- **For companion addons (API 13):** a page of their own in AzerothGPS's options window, the same Save Now button for what they keep, and a place under the map's directions panel. See docs/api.md.
- **For companion addons (API 14):** looks for the map: the player's arrow, the route's color, width, glow or a rainbow, and a tint for the window frame; and a call when a stop is reached. Only how the map looks, never what it does. See docs/api.md.
- **For companion addons (API 15):** a dropdown for their options pages, and a place on the map window's title bar, left of the close button. While one is used, the place's name sits between the logo and it, shortened on a narrow map instead of running under it. See docs/api.md.

### Fixed

- **Upstairs in Brill's inn.** A route from upstairs down to a trainer on the ground floor went straight down through the floor; now it takes the stairs down, and the directions and the map's stairs icon say "down" (they said "up"). A stop you set with a click on the map by a trainer upstairs no longer counts as reached when you stand under it on the ground floor. And after a hearthstone into the inn, AzerothGPS knows you're on the innkeeper's floor (until you walked in by a door, it couldn't tell).
- **Pasting your own map data back in.** Your herbs, ore and NPCs on Zephras Isle came back as "unknown level '2991'"; they're taken in now, like the rest.
- **The Import window's boxes tick by their words too.** Clicking "/way as herb/ore nodes" or "/way as NPCs" now ticks the box (only the box itself did, and the /way lines became stops).
- **The place name with a companion's meter in the title bar** sits in the middle between the logo and the meter, not up against the logo.
- **Flights from Undercity: the arrow window says to board.** At Undercity's flight master, the direction arrow window skipped the flight and showed the walk after it ("Arrive at" the next stop), while the map said to board the flight. It now says "Board the flight to …" too, then the walk from where it lands.
- **A /way line with no name is no longer a herb or ore node.** With **/way as herb/ore nodes** ticked, a line with only a zone and coordinates was named after its zone, and a zone with "ore" or "thorn" in its name (Elwynn Forest, Darkshore, Stranglethorn Vale) made it an ore or herb node. Such a line now says it needs a name.
- **Long routes no longer cost CPU when zoomed in.** On a long route the next turns were worked out over the whole route six times a second (for the direction arrow and the map's directions), and every redraw went over every bit of the route, near or not, so a long route cost about as much zoomed all the way in as zoomed out, around 10 to 15% of a CPU core while moving. Now the next turns are worked out once each time the route changes, only for the next stretch ahead. Each redraw, the map and the minimap only look at the parts of the route near what they show. About a tenth of the work. **Options > Performance** shows AzerothGPS's own share as you play; `/agps debug perf` lists its parts in chat, with what other addons draw on the map (such as a companion's paths) as its own line.
- **A narrow map no longer fills the screen's height.** With **Any shape**, dragging the map narrower than its quick buttons along the bottom need made it taller instead, up to the whole screen, with its title bar off the top where it couldn't be grabbed. Now the width and the height each have their own smallest size: the map stops getting narrower there and its height stays as you set it. The map is also never taller than the screen less its title bar, and the title bar and logo stay on the screen, so it can always be moved. A map already stuck that way fixes itself.
- **The Shadowvale Tomb has roads and an entrance marker.** WoW Forever's new tomb under Shadowvale, in Tirisfal's Whispering Forest, is mapped like a cave: routes go in by its way in and along its halls, and its entrance shows on the map.
- **A walk that can't be walked is planned again.** AzerothGPS plans a trip's walks to a boat or a flight master as straight lines first. When the walk it then works out still crosses a long way of ground the map data marks as blocked (straight down a cliff), the trip is planned again without that walk, and the better way is kept.
- **Off the roads, the route no longer runs back to the road and down again.** Walking across open ground toward a stop (Shadowvale in Tirisfal), the route kept going back up to the road first while the way from where you were was still being worked out, again on every reroute. A way already found from a few steps back is now picked up ahead of you, instead of only at the spot where its search started.
- **Undercity's quests are down in Undercity.** A quest route made up in Tirisfal (from Brill, say) put the stops for Undercity's quest givers on the surface above them, and the route led there, outside the city. The city's own map is now checked first.
- **More buildings are walked around, not through.** Buildings with wide doorways or open sides (most of Brill's) only had their walls traced, and routes off the roads cut straight through them. Wider openings are now closed when working out a building's ground, so they're mapped like the rest: about a quarter more ground in towns is kept clear of, and a stop inside a building (an innkeeper) is still reached.
- **Long dotted route lines no longer stop the map from drawing.** Zoomed in on a long off-road leg, its dashes ran past what the game allows ("TexCoord out of range"), and the rest of the map wasn't drawn. Lines are now cut to the map's edges first.

## 1.1.4

### New

- **Any size and shape, up to your whole screen.** The map is still square by default, and its **Size** now goes up to your screen (a 4K one too), not 800. Options, General: tick **Any shape** and the Size slider splits into **Height** and **Width**, set separately, and dragging the map's corner sets them too, to any shape (a wide map on a wide screen, say).

### Fixed

- **Zeppelin timers, timed again.** 1.1.3 added a few seconds to every zeppelin's and boat's trip, which was right for Brill and Grom'gol but put others off (Orgrimmar and Brill's ran 4 seconds late each trip). Now each keeps its own trip time, Grom'gol and Brill's as timed in game, and every one waits at the dock the 62-63 seconds they really do.

### Changed

- **Lighter on big maps.** A big map zoomed out was placing every tile and icon again on every redraw, the same ones, even when it had hardly moved. Now they stay as drawn until the view really moves (and are refreshed a couple of times a second anyway), and a map over 800 across redraws at most 10 times a second. Routes and directions are unaffected.
- **A wider direction window** by default, so "Continue straight, then slight right in 180 yd" fits on one line. If you never resized it, it gets the new width; a size you chose stays.

## 1.1.3

### New

- **Starting towns' guards give you the whole town.** Talk to a guard in Goldshire, Kharanos, Dolanaar, Brill, Bloodhoof Village or Razor Hill and every trainer, the inn and the stable master they know show on the map, as a capital's places do once you've talked to its guard. That includes the trainers they send you to outside town, named where they really are ("Sen'jin Village Mage Trainer"). Search finds them, for your faction's towns.

### Fixed

- **Questions show over the map.** "Don't use this zeppelin in routes?" and a route someone shares with you popped up in the middle of the screen; every AzerothGPS question now shows over the map while it's open (mid-screen only when the map is hidden).
- **Zeppelin and boat timers no longer fall behind.** The live server keeps each one at the dock about 2 seconds longer than the timetable had it, so a timer lost a few seconds every trip and was a minute or more off within the hour. Timed in game from Brill's tower; every zeppelin's and boat's timetable is corrected.
- **Roads on Zephras Isle:** 16 roads drawn in game, so routes there follow them.

## 1.1.2

### Fixed

- **Zeppelin and boat timers stay right.** Coming in to the far dock, a ride was taken for that dock's departure, so every ride moved its timer on by the wait there, and it kept needing to be put right. Now the ride's arrival is just that, and the time each ride really takes is learned from your rides and used in place of the estimate (the "arrives in" on board too). Timers saved by earlier versions are cleared once: a dock shows its times again after your next ride on it.
- **Group members who log out leave the map.** A party or raid member who went offline stayed on the map where they logged out; now their icon goes. In a raid, pointing at an icon says "Raid member".

## 1.1.1

For WoW Forever client 1.60.1 (interface 16001), build 70205: the map data (caves, dungeons and raids, building interiors, points of interest, terrain) is updated for it.

### New

- **Search finds your pins and city places.** Your pins show up with where they are ("Auction House  Stormwind City"), and so do the city places you know from the guards, for your faction's capitals ("Inn  Ironforge"). Pick one and it's a stop there, on the right floor. Older pins work too: where they are is worked out the first time you search. A pin made where you're standing also remembers whether you were indoors and the subzone, for telling floors apart later.
- **Search by several words:** "Inn Ir" finds Ironforge's inn, "auction iron" your Ironforge auction house pin. Each word just has to start a word of the place's name or where it is.
- **Turn off a zeppelin, boat or the tram for good.** Right-click its dock on the map, **Don't Use**, and routes never take it until you turn it back on (right-click again, **Use It**). It stays on the map, faded. Options → Routing has a **Zeppelins, boats and the tram** section listing each one your faction can take, by kind, all on by default. The Deeprun Tram's two ends have dock icons now too.

### Changed

- **Resize the map from its corner, on by default.** Drag the map window's bottom-right corner to make it bigger or smaller. The option is now **Resize from the corner** (Options → General, under the Size slider), on for everyone, including if you had 1.1.0's "Lock map size" on. While **Lock map position** is on, the corner doesn't resize either; unlock the map and it does again.

### Fixed

- A road drawn in game on the Eastern Kingdoms.
- **Route links in a raid or dungeon:** when several people clicked your route link at once inside an instance, the game's limit on addon messages could cut the end off their routes. AzerothGPS now paces what it sends to stay under that limit and resends anything the game refuses, so everyone gets the whole route.

## 1.1.0

For WoW Forever client 1.60.1 (interface 16001). This one brings new data files, so restart the game fully after updating instead of just doing a /reload.

### New

**Getting there**

- **Joining the road where it's heading.** Off the road, a route now joins it where you're going (across open ground, around fences and buildings), not back at the closest bit and round. Wander off the line and it's worked out again from where you are, so the join point moves with you. A short hop over open ground just goes straight. This replaces the old experimental off-road shortcuts, and their option is gone.
- **Buildings are in the way now.** Routes go around buildings (Goldshire's inn, farmhouses, towers) instead of through them. A stop inside one, like an innkeeper, is still reached.
- **Lifts.** Routes ride the Great Lift between the Barrens and Thousand Needles, Freewind Post's lift and Gnomeregan's, and the directions say "Take the lift down" (or up), like Thunder Bluff's and Undercity's.
- **Stairs in the directions.** In the capitals, Undercity and dungeons, the directions call out the stairs and ramps between levels, with the turn after them: "Stairs up in 10 yd, then turn left". The bends of a spiral stair don't count as turns.
- **Flight paths to pick up on the way.** When your walk passes a flight master of your faction you haven't learned, a brown line shows the little detour and the steps mention it ("Detour 388 yd to learn the flight path at Tarren Mill"). Right-click the flight master's icon, **Remove?**, to skip it.
- **Leave a ride out.** Every flight, boat, zeppelin, tram and teleport a route takes has its icon where you board it. Right-click it, **Remove?**, and the route is worked out without it, and stays that way for this route (rerouting and /reload too). For a flight, each flight master it passes over has its own icon, so you can drop just one hop. If leaving rides out means there's no way there at all, you'll see **Route not possible without** that ride, with the option to put it back.
- **Hearth or teleport from the directions.** When a route starts with your hearthstone or a teleport, a button with its icon sits in the directions panel and glows in the arrow window, right where the arrow usually is. Your click uses it; nothing ever gets used without one, and it hides in combat. New teleports: the engineers' **Dimensional Ripper - Everlook** and **Ultrasafe Transporter: Gadgetzan**. One is only suggested when it saves more than 800 yd.
- **The Deeprun Tram** between Stormwind and Ironforge, for Alliance characters.
- **Movement abilities in travel times.** Ghost Wolf, Travel Form, Cat Form with Feline Swiftness, and Aspect of the Cheetah or the Pack count in travel times, and become the walking time while they're on. The panel shows your walking time and your fastest other way to travel: a movement ability, or your mount once you can ride (faster with journeyman riding).
- **Undercity, floor by floor.** Routes follow every floor (walkways over the bank's level, the canal walks under the bridges, the Magic Quarter's rooms), picked by your height and the stop's. Trips across town are shorter and no longer cut through floors, over the canals' rims or out over the Ruins' walls.
- **A route to another continent** is shown on the world map first, then the map follows you again.
- **City places** a guard showed you can be double-clicked into stops, and a stop down in a city takes the lift.
- **More roads** on Eastern Kingdoms, drawn in game.
- While a route is being worked out, now and then a Murloc does the thinking (Mrglglglgl), or the gnome engineers ("Spinning up the Route-o-Tron 3000...") or a goblin ("Time is money, friend! Routing...").

**Dungeons and raids**

- **Wings get their own icons.** Scarlet Monastery's Graveyard, Library, Armory and Cathedral, Dire Maul's East, West and North, Stratholme's Main Gate and Service Entrance, and Maraudon's Orange and Purple each have an icon, named so you know which door is which. A wing's map shows just its bosses, its usual way through from its own door, and its own boss route; inside, the map goes with the wing you walked in through. Maraudon's inner bosses belong to both sides. Uldaman's back way in and Gnomeregan's Train Depot get named icons too, and show the whole dungeon.
- **Mark where you are in a dungeon.** The game hides your position inside, so double-click the dungeon's map where you are and your class icon goes there (right-click it to clear). The panel at the top shows the controls, with right-click a boss to mark it defeated.
- **A stop picked in a dungeon's map** (a spot, a boss or a pin) goes on the dungeon's entrance out in the world, since that's where you're actually heading.
- **Blackwing Lair** (through Upper Blackrock Spire) and **WoW Forever's own dungeons and raids**: their maps, bosses and entrances. Entrances we don't know yet are learned when you go in; share them with **Copy Map Data...**.
- **Cave and mine entrances on the map** (double-click one for a stop), in the map menu's new **Caves/Dungeons/Raids** group.
- **The Defias Hideout** under Moonbrook has its roads, down the spiral stairs and the ramps to the Deadmines' door, and the dungeon's entrance shows on its map. A route to the Deadmines from outside takes you to the Hideout's way in, and its map shows the way down from there.

**The map**

- **Pins.** Shift + left-click the map, **Create Pin**, give it a name and any icon in the game (the same list a macro uses). Where floors stack up (a dungeon, Undercity, a cave), pick its floor too. Double-click a pin for a stop, right-click to remove it. Pins are kept for all your characters and can go out with your map data. Options → Tools: **Pinning**; Options → Map: **Pins**.
- **A bigger map shows more.** Resizing the window keeps the scale, so you see more of the world instead of the same bit bigger, and past 450 wide you can zoom out further too.
- **Resize from the corner.** Turn off **Lock map size** (Options → General, under the Size slider) and drag the map window's bottom-right corner to make it bigger or smaller.
- **On a zeppelin or boat, like on a flight:** once AzerothGPS sees it leave the dock, the panel and the arrow say "Riding the zeppelin to Brill, arrives in 1m 15s", counting down by its timetable, with the walk on from the other dock after it (it used to keep showing the way to the zeppelin you were already on).
- **Share a zeppelin's or boat's times.** Shift + left-click its dock (or the route's ride icon there) once AzerothGPS knows its timetable, and a line like "Zeppelin from Brill to Grom'gol Base Camp: arrives in 2:10, leaves in 3:10" goes in your chat box for you to send.
- **Map pins, as on the game's world map.** Ctrl + left-click the map to drop the map pin (a diamond, the game's own waypoint), Shift + left-click it to link it in chat, Ctrl + left-click it again to remove it. It stays through reloads and logouts and isn't shared with your map data. Click a map pin someone posted in chat ("[Map Pin Location]") and it's a stop (Options → Routing: **Map pin links add stops**).
- **Your group on the map,** as round class icons in their class color (Options → Map, Party members). They don't need AzerothGPS themselves.
- **Heading-up:** with "Turn the map with me" on, your arrow sits low on the map, so more of the road ahead shows.
- **Right-click inside a building** shows the outside first; the next right-click, the continent's map.
- **Right-click in Undercity or Ironforge** shows the terrain around the city, zoomed out, and you can drag and zoom it anywhere (it used to jump to the continent's map, and the land past the city stayed black). Recenter for the city's map again.
- **The capitals' districts** are named on the map when zoomed in, like Undercity's: Stormwind's Trade District and Old Town, Orgrimmar's Valleys and The Drag, Ironforge's Wards, Thunder Bluff's Rises, Darnassus's Terraces.
- **Zephras Isle on the world map,** as a framed picture at the top; click it to open the island. On a continent's map, the zone under your pointer lights up.

**Settings and sharing**

- **Performance options** (Options → Performance) for older PCs, with a live readout of how much time AzerothGPS is taking:
  - **Map redraws per second** (5 to 30, default 20), the biggest saving: at 10 the map needs about half the work.
  - **Work out a route you've left at most every** 2 to 10 seconds.
  - **Stops routed and drawn ahead** (1 to 8, default 3). Every stop keeps its marker and its place in the fastest order; the ones further on show an estimated distance until they're routed.
  - **Gentle background work:** fewer stutters, routes take a moment longer to appear.
  - **Turn the arrow every frame,** or 20 times a second.
  - **Use Low-End Settings** turns them all down at once; **Restore Defaults** puts them back.
- **Pick what Copy Map Data... includes:** Roads, Walls, Routes and Pins, each with how many you've got, all ticked unless you untick one. **Routes** are the ways you went when you beat the estimate, kept as you play (on your PC). Dungeon entrances you found always go along. The old **Share drawn roads and walls** and **Share faster trips** options are gone; these checkboxes decide now.
- **New defaults:** the map is 450 wide, Quest Route and Use Hearthstone live in the map button's menu, and in combat the map stays shown, fully opaque and clickable (Options → Opacity). Your own settings stay as they are; Reset to defaults takes these.
- **Road and wall tools:** the road tools show the road network while they're on, "Show extracted roads" and "Show extracted walls" are one button now (**Show Roads and Walls**, under Undo), and Undo takes back your last road or wall change, whichever came last.
- **Fixing floors over floors** (Undercity, under Orgrimmar's Drag and Stormwind's bridges, caves and mines): with the road or wall tools on, **Shift + mouse wheel** picks the floor you're editing. The hint under the map says which one ("Editing: floor 2 of 3 here"), and what you draw or erase changes only that floor.
- **For other addons:** API versions 3 to 12 (HoldMap with a map style held while it's on, icons in overlays, popup windows in AzerothGPS's style, Shift-click on a dungeon boss handed to another addon (OnIconShiftClick), LookAt, Follow, ShowMap, ShowWorld, ToContinent, SaveView and RestoreView, TopPanelInset). See docs/api.md.

### Changed

- **Sharing a route in game is a link now.** "Link To" a player or your group (Import and share waypoints) puts a short line in the chat box, "[AzerothGPS Route: 3 stops]", for you to send like a map pin. Players without AzerothGPS only see that line. AzerothGPS users click it to get your route, and are still asked before it replaces theirs. Nothing arrives unless you click a link, so no more surprise popups in the middle of a run.
- **Zones way above your level:** "Keep this route?" now comes before the route is drawn or followed, and it's asked again if you leave a ride out and the new way runs through one. A quicker safe way, like the tram, always comes first.
- **No more straight lines over mountains.** When there's genuinely no way to walk somewhere (no roads join up and a wall or a mountain's in the way), you get "No way there found" instead of a line over the top. Across open ground or water, a straight line still counts.
- **Flights at a low level** are weighed against the walk as it's really routed, so you'll fly when walking would go the long way round zones too high for you (like Brill into Arathi Highlands at level 14).
- **The directions** say what to do now and then the next turn: "Continue straight, then slight right in 13 yd" ("Slight right now" at the turn).
- **In Ironforge and Undercity** the city's own map stays up while you're in town, wherever you pan or drag, and zooming out stops at the city. Right-click for the outside. Coming into town zoomed way out, the map zooms in to it.
- With the window frame on, the place you're in ("Undercity") is in the title bar instead of "AzerothGPS"; the coordinates stay at the bottom.
- Every popup (Create Pin, Your Map Data, the waypoint windows) has the map window's frame now, and the yes/no questions have it without a title bar.
- Changing a route option (flight paths, the hearthstone, teleports, the zones or towns avoided) works the trip out again right away.
- A shaman with Astral Recall ready gets that instead of the hearthstone (same trip home), so the hearthstone stays ready for later.
- "Route there anyway?" is remembered for the route, even after a /reload.
- The last stop clears as soon as you reach it.
- With a stop down in Undercity, only the city's stops keep the order you placed them; the rest go in the fastest order.
- The map window sits under other windows.

### Fixed

- **Zeppelin and boat timers after a server restart:** riding one again resets its timer, and the restart's shift no longer bends the timetable for the rides after.
- **Brill to Grom'gol takes the direct zeppelin** again, not two zeppelins by way of Durotar. Zeppelin and boat times now come from the server's timetable.
- **The bat out of Undercity:** while it flies you through the city and its sewers, the route is the flight ("Flying to The Sepulcher, lands in..."), not a walk back to the flight master that kept getting longer.
- **Lag:** the first route after a /reload and very long walks are worked out in the background (no more freeze); recalculating a route with a flight in it; riding a zeppelin or boat no longer reworks the whole route; the first road display after a /reload, and each road or wall edit.
- **The capitals' roads are their streets now.** Stormwind's (and Ironforge's, Orgrimmar's, Thunder Bluff's and Darnassus's) roads were a jumble over every floor, some running out over the water. They now follow the streets the guards walk, with ways to every trainer, bank, inn and flight master.
- In the capitals, routes no longer climb onto a ledge or balcony and jump back down to a trainer underneath (Ironforge's Mystic Ward and Hall of Mysteries).
- Talking to a guard in Stormwind, Ironforge or Darnassus only showed the place you asked for; now all of that city's places show, like in the Horde capitals.
- In Ironforge, routes cut straight across the Great Forge and the Forlorn Cavern's pool instead of following the halls.
- **Thunder Bluff's lifts:** routes into and out of the city take them now, and two ways out that ran straight down the mesa's cliff are gone.
- Routes out of Stormwind went straight through the city wall: a road drawn in through its gate went missing once it was in the data. Drawn roads always stay now.
- **Dungeon routes** jump between floors much less: 16 of the boss routes that used to are fixed.
- **On a road, routes keep to it** unless a cross-country way onto another road saves a fair bit (on Mulgore's road the route kept flipping between the road and a shortcut).
- While riding or walking past ground the addon was still checking, the route vanished every few seconds behind "Working out the route...". It stays up now while it's reworked.
- When a route started with your hearthstone, the direction arrow gave the turns of the walk after it. It now says "Use your Hearthstone" like the route's first step, with the button.
- Stormwind's map flipped between the city's own map and the terrain as you zoomed; Stormwind keeps the terrain map now.
- A route out of Ironforge zoomed its overview out over the city's map into the black; it shows the land around now.
- The map stayed on Ironforge's outside after making or canceling a route out of the city.
- The map's title says the city you're in (Ironforge, not Dun Morogh), and it's centered.
- The corner logo stands on its own without the circle, and it's sharp.
- City places, pins, stops made from them and party members' class icons looked grainy; they're drawn at a size the game shrinks cleanly now, and sharp. Place names and city labels on the map are crisp too (they sat between screen pixels and looked smeared).
- The Deeprun Tram's map was blank.
- A zeppelin to Zephras Isle had no line on the map.
- A dock that was a stop lost its countdown.
- A straight line over the hills could replace the roads after standing still for a while.
- A flight could stop being suggested after adding a stop elsewhere and taking it back.
- Roads vanished from the map when zoomed out (road and wall tools).
- Ironforge's roads, and road tool edits there, didn't show on the city's map.
- Clicking the open sea on a continent's map opened a black terrain view.
- The "lands in" countdown on a flight stayed stuck at the flight's full time, and flight times were never learned. It counts down now, along the flight's path through any stops, which the map draws too.
- A character that knew no flight paths yet got no detour to learn one it walked past.
- A stop in the other faction's town (Dun Garok, from Tarren Mill) was reached by a straight walk over the hills instead of the road in: the guards of the town you're heading to (or leaving) no longer push the route off the road. Passing other towns still bends the route around them.
- A boss's kill sometimes didn't count, so the boss route kept sending you back to it (no kill reported by the server). A boss you see dead, targeted, moused over or looted, counts now, and where the game hides who died, right-click a boss on the dungeon's map to mark it defeated (or not).
- Right after logging in (a new character above all), your flight paths and faction could be saved under "Unknown" instead of your character.

### Known limits

- Party members show only where the game gives their position, so not inside dungeons.
- In some dungeons with floors stacked on floors (Blackrock Spire and Depths, Temple of Ahn'Qiraj, Scholomance) the gold line can still jump between floors in places.
- Zeppelin and boat countdowns start once you've ridden that one, since the game doesn't tell addons where they are.

## 1.0.7

For WoW Forever client 1.60.1 (interface 16001). New data and image files are included, so fully restart the game after updating, rather than just /reload.

### New

- **Dungeons and raids:** 25 of them (from Ragefire Chasm to Naxxramas) have entrance icons on every map style (the map menu's "Dungeons and raids" group turns them on and off). Click one for its map:
  - the game's own map of it, floor by floor with the **+** and **-** buttons at the top left (the mouse wheel still zooms);
  - its bosses, numbered in the usual kill order (optional ones marked);
  - a gold line for the usual way through, boss by boss, with stairs icons where it goes up or down a floor.

  Right-click goes back to the map you came from.
- **Boss route** (map menu): a route through a dungeon's bosses in the usual order. Each stop is done when its boss dies, not when you get there, and a boss already down is left out.
- **Inside a dungeon** the game hides your position from addons, so the map shows the dungeon itself: the bosses you've killed fade, the stretch of the gold line to the next boss lights up, and the panel says which boss is next ("Next: Sneed (2 of 6)").
- **Zones too high for your level** (Options → Routing, on by default): routes go around zones whose levels are red for you, when there's another way. Routing to a stop in one, or along the only way there through one, asks first, on the map.
- **Zeppelin and boat docks** show on the map with points of interest (double-click one for a stop). After you've ridden one once, its icon counts down to its next arrival, from its timetable and when you saw it leave.
- **Boats, zeppelins, lifts and dungeon portals** are only used when your faction can take them.
- **City icons on the terrain view:** Undercity's and Ironforge's open their inside maps.
- **For other addons:** a public `AzerothGPS` API (map geometry, the point under the mouse, drawing on the map; dungeons' maps too). See docs/api.md.

### Fixed

- Long routes without flight paths froze the game for seconds (off-road shortcuts are now worked out in the background).
- A route could turn back to a road the other way (a U-turn) while the way around a rock or a steep patch was still being searched, and kept doing it as you walked.
- Right-clicking out of a city's or dungeon's map went to the wrong place.
- An error inside dungeons (a tooltip the game hides from addons).

### Known limits

- Blackwing Lair and WoW Forever's new dungeons and raids aren't in yet.
- In some dungeons with floors over floors (Blackrock Spire and Depths, Temple of Ahn'Qiraj) the gold line can still jump between floors in places.
- Zeppelin and boat countdowns start once you've ridden that one (the game doesn't tell addons where they are).

## 1.0.6

For WoW Forever client 1.60.1 (interface 16001). New data files are included, so fully restart the game after updating, rather than just /reload.

### New

- **Undercity:** routes follow the city's own floors, stairs and lifts, with "above you" and "below you" hints, and use a safe jump down a ledge when it saves time (only when your health allows it). Off-road shortcuts turn themselves off in cities and the Ruins of Lordaeron, and back on after. Its flight master, trainers and quest givers are reached down in the city, not up top.

  ![Undercity's map with its districts and places](https://i.imgur.com/AZzfqTs.png)

- **The capitals:** Orgrimmar, Ironforge, Stormwind, Thunder Bluff and Darnassus have their own streets now: routes go in through the gates and follow them to the banks, trainers, flight masters and docks. That includes the Cleft of Shadow under Orgrimmar, the halls under Ironforge's mountain, Stormwind's canal bridges, and Thunder Bluff's bridges and elevators. Off-road shortcuts turn themselves off inside.
- **Caves and mines:** 351 of them on both continents are mapped: routes go in at the mouth and follow the tunnels.
- **More roads:** many roads the map was missing (Dun Morogh, Desolace, Badlands, Winterspring and more) are part of the network now.
- **The other faction's towns:** routes keep away from their guards and go around their towns when there's a way (Options → Routing).
- **Continent map:** right-click from the terrain view goes to the continent's map, then the world map. Hover a zone for its name and level range; click a capital's icon to open the city (Ironforge and Undercity show their inside).

  ![A continent's map: hovering a zone shows its name and level range](https://i.imgur.com/HHVpQsL.png)

- **City locations:** after talking to a guard in a capital, its banks, trainers and other places show on the map. Asking a guard again routes there again, and any banker, auctioneer or trainer of the kind finishes that stop.
- **Quick buttons** are grouped (map styles; quests; herbs, ore and farming) and slide out beside their button, in the order you set in Options.

  ![Quick button groups sliding out](https://i.imgur.com/DG6utoK.gif)

- **Road tools** (Options → Road tools): draw a road the routes miss, or erase a false one (or circle an area).

  ![Road tools: circling a false road to erase it, then drawing the real one](https://i.imgur.com/WjwnjW1.gif)

- **Wall tools** (Options → Wall tools): draw walls routes can't walk through (roads crossing them are cut; leave a gap for a gate), or erase a mountain edge the map has wrong. **Show extracted walls** draws everything routes won't cross.

  ![Stormwind's roads](https://i.imgur.com/woSLg9m.png)
  ![The walls routes won't cross, over the roads](https://i.imgur.com/oH1dYxZ.png)

- **Share your fixes:** Options → Help improve → **Copy map data...**, then paste it in a [Road data issue](https://github.com/AzerothGPS/AzerothGPS/issues/new?template=road-data.yml) on GitHub.
- **Quest route:** an option to use only the quests in the zone you're in; a quest route always goes in the fastest order, in cities too.
- **Smoother directions:** short jogs in a route are straightened (not on hilly ground, where winding is the way up), and a turn that just jogs back onto the same line reads as straight on. Parts of a route on another floor are drawn faint and dotted.
- The map keeps where you panned it across a /reload, and switching map style keeps the spot you're looking at.

### Fixed

- Routes through walls, off ledges and into water in Undercity and the Ruins of Lordaeron.
- A freeze when the first route after logging in was worked out, and the road network builds several times faster.
- "Turn around" when the way on was a lift down or up.

## 1.0.5

For WoW Forever client 1.60.1 (interface 16001). A new key binding file is included, so fully restart the game after updating, rather than just /reload.

### New

- **Questing** (on by default, Options → Routing). A stop inside a quest's area is done when that quest's objectives are, not when you get there:
  - **In the stop's quest area,** the arrow window shows the objective counters. A smaller arrow still points to the stop's spot, with "In quest area" and the distance under it, and the stop after this one listed below.
  - **At the spot,** a big **!** replaces the arrow and the route waits while you quest. Leave the area early and the route leads you back.
  - **Objectives done** anywhere in the area: on to the next stop.
  - **Other quest areas** you walk through (even with no route) show their objectives in the arrow window, with a **!**.
  - **In the area of a stop further down your list?** That stop moves to the front.
- **Quest route.** The new **Sprint button** next to the Hearthstone button makes a route through your quest log: every quest's objectives and every finished quest's turn-in, in the fastest order.
  - Pick up a new quest while on a quest route and a Sprint icon pulses in the arrow window's corner. Click it to make the route again with the new quest.
- **Corpse runs.** Released as a ghost, your body (the skull marker) becomes stop 1 with a red route, ahead of any stops you had. Once you're alive, it's taken off and your route carries on.
- **Long lists.** Import up to 100 stops (a quest guide, say). With fastest order on, the whole list is ordered from where you are; the route shows the next 8 stops and brings in the next one as you arrive.
- **Show/hide key.** Set a key for the map in Options → General, or in the game's Key Bindings under AddOns ("Show/Hide AzerothGPS").
- **Reopen following me** (Options → General, off by default): with a route set, a map you hid while looking around reopens centered on you.

### Improved

- **Quest areas** are found more reliably:
  - Small areas (a few dozen yards) are found by looking closely around you.
  - Quests with no map icon on your current map are traced too.
  - Tracing waits until combat is over (the game hides the answers in combat), so areas no longer come out empty.
  - All of it works with the map closed.
- **Hidden map:** routing and the arrow keep going with the map closed. Stops placed but not confirmed are confirmed when you close it.
- **The direction arrow** is click-through while locked.
- **The route animation** frames every stop, not just the first few.

### Fixed

- The route animation could stop the map from updating after making a quest route.

## 1.0.4

For WoW Forever client 1.60.1 (interface 16001). A new texture is included, so fully restart the game after updating, rather than just /reload.

### Improved

- **Much lower CPU use.** In testing with a 5-stop off-road route and quest areas shown, AzerothGPS uses about 40% less CPU than 1.0.3, with far fewer frame hitches:
  - **Routing** no longer recalculates several times a second while you're off-road. Background terrain searches refresh the route at most every 3 seconds.
  - **Recalculations are cheaper.** Terrain checks and stop-to-stop times are remembered instead of worked out again.
  - **Multi-stop routes** work out the legs between stops one per frame, so adding stops no longer stalls the game.
  - **The map** redraws at most 20 times a second, and dotted route lines are drawn as one line per leg.
  - **The first route** after logging in builds its road data in the background (the route panel briefly says "Working out the route...") instead of freezing the game for a moment.
- **Hearthstone and teleports on any leg.** On a multi-stop trip, your Hearthstone (or Astral Recall, or a mage teleport) is now used on the leg where it saves the most time, not only from where you stand. A trip that ends near home hearths from the last stop instead of running back. Each is used once per trip.

### Fixed

- **Routes stay up to date while the map is hidden** (for example in combat). The direction arrow keeps the route's background work going.

## 1.0.3

For WoW Forever client 1.60.1 (interface 16001). New files are included, so fully restart the game after updating, rather than just /reload.

### New

- **Search.** The magnifier at the bottom-left of the map finds towns, zones, landmarks, flight masters and boat and zeppelin docks. Pick one and it becomes a stop. NPCs can't be searched: the game doesn't tell addons where they are.
- **Farming routes.** Open the round map button, choose **Draw a farming area**, and drag around the herbs or ore you want. The route loops through every known node inside, round and round.
- **Herbs and ore:**
  - **Separate layers:** Herbs and Ore are now separate map layers, and a farming area uses the ones you show.
  - **Right-click to save:** right-click a herb or ore node without the profession ("Requires Herbalism/Mining") and it's saved for your characters who have it.
  - **Import node lists:** in the waypoint window (+), choose "Import as herb/ore nodes". They show faded until you gather there.
- **Hearthstone and teleports.** When it's faster, a route can start with your Hearthstone, Astral Recall, a mage's teleport or Teleport: Moonglade. The directions say "Use your Hearthstone (to …)"; the addon never uses anything for you.
  - **Two options** under Routing: "Use hearthstone" and "Use class teleports" (both on by default).
  - **Hearthstone button** next to the round map button: one click turns the hearthstone on or off for routes (grayed when off).
  - **Knows your inn:** the hearthstone lands at your inn's building, and the exact spot is learned when you're inside it.
- **New flight masters on the way.** If a flight master of your faction you haven't learned yet has a flight to one you know, and going there is faster, the route says "Learn the flight path, then take the flight to …".
- **Zephras Isle.** WoW Forever's island has its terrain map, roads and place names, and routes take the zeppelins there from Alterac Mountains and Mulgore.
- **Click-through.** Options → Opacity: while moving and/or in combat, clicks pass through the map and the arrow to the game world (combat on by default).

### Improved

- **Off-road routes:**
  - They walk around ridges on longer trips (up to 3,000 yards) instead of making long road detours.
  - They walk off rocks you're standing on.
  - They no longer cut through cliffs from walled-in spots.
  - Checked with a new all-zones route test: 0 bad routes in 711 random trips.
- **Route options apply right away.** Turning flights, the hearthstone or teleports on or off changes the route at once, instead of keeping the old one for a while.
- **Quest areas:**
  - Much lower CPU use while moving with quest areas shown.
  - They no longer disappear for a while when an outline is updated or you cross into another zone.
- **Gathering** is recognized at every rank of Mining and Herb Gathering, so gathered nodes show up.
- **Adding a stop to a route** shows the whole route again after 5 seconds, then follows you. Drawing a farming area plays the route animation.
- **The map menu** closes after 6 idle seconds or a click on the map, and the search panel after 20 seconds.
- **Stop markers** skip the cross and skull, and start over after six.
- **Buttons:** the import + button and the back-to-you button swapped places.
- **The direction arrow** has no tooltip anymore. How it works is explained under Options → Directions.
- **Close buttons** on AzerothGPS windows work in combat.
- **The addon list** shows the AzerothGPS icon instead of a "?".

### Fixed

- **Hearthstone** wasn't suggested in routes.
- **Flights** with only one known flight master at the far end couldn't be used.

### Removed

- **Quests to pick up.** This client only shows them on its own minimap, where addons can't read them.

## 1.0.2

For WoW Forever client 1.60.1 (interface 16001). Extract the `AzerothGPS` folder into `World of Warcraft\_classic_beta_\Interface\AddOns`. New image files are included, so fully restart the game after updating (not just /reload).

### New
- **Flight paths:** routes take flights between the flight masters your character knows, including connecting flights (option "Use flight paths", on by default). Open the flight map at any flight master once so the addon learns which ones you know.
- **Flying:** while on a flight, the route stays put and nothing is recalculated. The flight's line shrinks as you fly, and the time left counts into your ETA.
- **Stop order on the way:** with "Visit stops in the fastest order", stops are reordered as you travel when another order becomes clearly faster.
- **Fade while moving:** the map can fade while you move, leaving the route, the stop markers and your arrow visible (Options → Opacity).
- **Window frame:** the map has a game-style frame with a title bar, logo and close button, and it's its own option. The map and the direction arrow have separate lock options.
- **Options:** the options window has pages like the game's settings (General, Map, Routing, Directions, Opacity, Road tools, Help improve).
- **Map menu:** one round button at the bottom-left opens the map type and the map layers.
- **Route panel:** a -/+ button collapses the steps to the trip's times. The ✕ now closes the panel without canceling the route; an option restores the old behavior.

### Improved
- **Off-road:** routes join and leave roads partway along, so they cut straight across to where the road is heading.
- **Rerouting:** routes no longer jump to a longer path for a moment near obstacles while you're still on the route.
- **Times line:** only the mount time shows while mounted, and a mount time only appears once the character has learned Riding. Flights no longer count as mounted.

### License
All rights reserved (see LICENSE.txt).

## 1.0.1

For WoW Forever client 1.60.1 (interface 16001). Extract the `AzerothGPS` folder into `World of Warcraft\_classic_beta_\Interface\AddOns`.

### New
- **Share routes.** The + button's window can copy your route as TomTom `/way` lines (paste them anywhere), or send it in game to a player or your group. Receivers need AzerothGPS and are asked before it's used. Shift+click a name in chat to fill in "Send to". Option: "Accept routes shared by players".
- **Points of interest as stops.** Double-click a flight master, town or quest icon to add it as a stop; its name is used in the directions.
- **In combat options.** Hide the map and/or the direction arrow during fights, or give each its own combat opacity (the map's follows its usual opacity by default). The arrow no longer catches clicks in combat.

### Fixed
- Clicking a point of interest replaced the whole route; it now adds a stop like a double-click, and Confirm Route starts it.
- Routes on the other side of a boat or zeppelin (and anywhere the road data had gaps) could fall back to a straight line; the pieces of the road network are now joined, so routes follow the roads.
- "Show extracted roads" is off by default for new installs.

## 1.0.0

First release of **AzerothGPS**, car-GPS style navigation for World of Warcraft (Classic / WoW Forever client, interface 16001). Display only: it never moves your character, clicks, or automates anything.

**Install:** unzip `AzerothGPS-1.0.0.zip` into `World of Warcraft\_classic_beta_\Interface\AddOns\` (so you get `AddOns\AzerothGPS\AzerothGPS.toc`), then start the game or `/reload`. `/agps` opens the options.

### Features
- **Map window:** terrain view, world map, and a No Spoiler map (only explored parts); building interiors; zoom, pan, right-click to browse Azeroth and continents; coordinates under the mouse.
- **Routing:** along the extracted road network, optional off-road shortcuts that respect mountains and cliffs, zeppelins and boats between continents; follows the route like a car GPS and reroutes when you leave it.
- **Multi-stop trips:** double-click to place stops (raid markers), fastest order option, per-stop times, add/remove stops on a live route, color per leg.
- **Turn-by-turn:** a TomTom-style arrow with the next turn, "toward <place>", the stop's distance and ETA, and later stops when made taller.
- **TomTom compatible:** import `/way` lines (the + button), `/way` in chat, pasted lists of `/way` lines.
- **Layers:** quest objectives and turn-ins, quest areas with hover tooltips, quests to pick up, flight masters, points of interest, place names, herbs and ore you've gathered or hovered.
- **Road fixes:** record missing or false roads in game; they're used right away.

### Privacy
Nothing is sent anywhere; addons can't use the network. The optional "Help improve AzerothGPS" settings (off by default) only keep data in your saved variables on your PC.

AzerothGPS is a fan-made addon and is not affiliated with or endorsed by Blizzard Entertainment.
