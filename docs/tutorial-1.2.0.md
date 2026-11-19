# The tutorial (1.2.0)

Asked 2026-11-09: "introduce a short tutorial on first install/update of the addon (these can be disabled and viewed
again in a Help section in options) that asks the user if they'd like to take a short tutorial on the features."

This is what was built, the whole script (every step's English text), the choices made on the way, and what could not
be checked without the game. The code is `addon/AzerothGPS/Tutorial.lua`; the tests are `app/tests/test_tutorial.py`
(one of them fails when a step's text is missing from this file).

## In short

- **When it's offered.** At a first install ("Welcome to AzerothGPS") and once after an update that adds sections
  ("What's new in 1.2.0"; for 1.2.0 every section is new): "Take a short tutorial?" with **Start Tutorial**, **Not Now**
  and **Don't Ask Again**. It comes up 8 seconds after the world is entered, never in combat, in a dungeon, dead, on a
  flight, or during a companion's game on the map (then at the next loading screen or login instead).
  Not Now asks again at the next login, 3 times at most. Closing the window without an answer counts as Not Now.
- **Any time.** Options > Help has a Tutorial section: **Play All**, a **Play** button for every section (done ones are
  marked), and the checkbox "Offer the tutorial after big updates" (Don't Ask Again turns it off). `/agps tutorial`
  plays all of it, `/agps tutorial <section>` one section (`minimap`, `route`, `quests`, `arrow`, `gather`, `pins`,
  `search`, `dungeon`, `window`, `roads`), `/agps tutorial exit` leaves it.
- **The player does it.** Each step points at the control with a pulsing gold outline and waits for the player to do
  the thing; the addon notices and moves on ("Done!"). Every such step has **Skip Step**. Steps that can't be done on
  the spot (the route across the sea, the dungeon's map) are set up by the addon and have **Next**.
- **Always a way out.** The panel has **Back**, **Sections** (jump to any section), **Exit Tutorial** and its X. A step
  that can't be shown says "This step can't be done here right now. Skip it to go on." Escape does not close the
  panel (so a tutorial isn't left by mistake). A companion addon's game starting on the map ends the tutorial (as Exit
  Tutorial does).
- **Everything goes back.** The player's settings, route, waiting stops, map view, window size and shape, arrow
  places, layers and tools are put back exactly at the end, on exit, and between sections. The one thing kept: "Keep
  the GPS map as your minimap?" answered Yes.
- **Nothing of the player's is written.** The example herbs and ore, the practice road and wall and the practice
  recorded walk live in memory only.
- **In the game's language.** All of its text is in the ten locale files (134 new lines each).

## The panel

`Tutorial` window (AzerothGPS's own popup frame), over every other window, the map opened out of the minimap square
included. From top to bottom: "Set a route: step 3 of 6" (or "Done!" for a moment), the step's title, one or two
sentences, a row of the step's own buttons where it has a choice (Small / Medium / Large, Yes / No), then **Back**,
**Sections**, **Exit Tutorial** and **Skip Step** or **Next**. It places itself on the half of the screen away from
what it points at, and stays where the player drags it.

Combat hides the panel and the outline and nothing is set up or checked meanwhile; the step goes on when the fight
ends (what the player did during it counts).

The closing card: "That's the tour" / "Everything is back as you had it. Replay any part in Options > Help, or type
/agps tutorial." with **Close**.

## The script

"The player does it" steps wait for the action named after "Noticed by"; the others have Next.

### 1. The GPS map as your minimap (`minimap`, added in 1.2.0)

The option is really turned on for this section.

1. **Minimap replacement** (shown)
   The GPS map now sits where your minimap was. The game's own icons still show on it.
2. **Open the GPS map** (the player does it)
   Click the logo on the minimap's bottom left corner.
   Noticed by: the map is opened out (`G.mmState.expanded`).
3. **Auto close on inactivity** (waits for the map to go back: left alone 5 seconds, or its arrow)
   Left alone for 5 seconds, the map goes back to its corner. The arrow button on the bottom left, or double-click on the logo, sends it back now.
   A countdown shows on the map (5, 4, 3...), and "Active!" while the player is doing something on it.
   It is drawn large, by the map's own size: its digits a fifth of the map's smaller side tall.
4. **Close on movement** (the player does it; "Back to the minimap when you move" is turned on for the step)
   That option is on for this demo: take a step and the map goes back to the minimap position.
   Noticed by: the map is no longer opened out.
5. **Close on combat** (shown; only mentioned, nothing about combat is demonstrated)
   It can also go back when combat starts. Both options are in Options > Map. Check here to turn it on now.
   Two checkboxes: "Back to the minimap when you move" and "Back to the minimap when combat starts". What is ticked here is kept after the tutorial.
6. **Three size choices** (a choice: Small, Medium, Large, applied at once)
   Pick the size you like.
7. **Options on the logo** (waits for the options to open)
   Right-click the logo in the bottom left of the minimap to open the options panel.
8. **Keep the GPS map as your minimap?** (a choice: Yes, No; Next leaves it as the player had it)
   Yes keeps it on after the tutorial. Everything else goes back to how you had it.
   For a player who has the option on already there is no question: "You already use the GPS map as your minimap, so
   it stays on."

### 2. Set a route (`route`, added in 1.2.0)

1. **Place a stop** (the player does it)
   Double-click anywhere on the map to place a stop.
   Noticed by: a stop is waiting or on the route.
2. **Start the route** (the player does it; an example stop waits if the last step was skipped)
   Click Confirm Route. It also starts by itself after 5 seconds of no further map activity.
   Noticed by: the route has a stop.
3. **Add more stops** (the player does it)
   Double-click two more places on the map. Each is added to the route.
   Noticed by: two more stops than when the step started.
4. **The fastest order** (waits for a stop to be removed; example stops fill the route up to three)
   With several stops, the route visits them in the fastest order. Right-click a stop's marker to remove it.
5. **Across to another continent** (shown; the addon sets a stop on the other continent and the map shows the overview)
   This example goes to the other continent. The steps are listed at the top of the map window.
   The example: Horde, to Orgrimmar from the Eastern Kingdoms and to Brill from Kalimdor; Alliance, to Auberdine from
   the Eastern Kingdoms and to Stormwind from Kalimdor. Zones too high for the character aren't asked about, and the
   top panel's steps are opened for it.
6. **Clear a route** (waits for the route to end; the X on the directions is pointed at, and ends the route for the step)
   Click the X at the top right of the directions to end the route.

### 3. Quest Route (`quests`, added in 1.2.0)

1. **A route through your quests** (the player does it, with quests that have places; else shown, with three example
   stops "Example quest 1" to "Example quest 3")
   Click Quest Route in the map menu.
   Without quests: "You have no quests with known places right now, so these stops are examples."
   Noticed by: a new route with stops.
2. **What it does** (shown)
   It visits your quests' objectives in the fastest order, then the turn-ins. A stop is done when its quest is, not when you get there.
3. **With your other addons** (shown; only when RestedXP Guides, Zygor Guides Viewer, Questie or TomTom is loaded,
   listing those that are)
   AzerothGPS also works with: RestedXP Route, Zygor Route, and Questie.

### 4. The direction arrow (`arrow`, added in 1.2.0)

The arrow and the directions panel are turned on and unlocked, with an example stop if there's no route.

1. **The arrow and the directions** (shown)
   The arrow points the way and the panel beside it lists the turns. Each can be dragged until you lock it.
2. **Move it** (the player does it)
   Drag the directions panel: the arrow comes with it.
   Noticed by: the panels' saved places changed.
3. **Pull them apart** (the player does it)
   Drag the arrow off the panel to place it on its own. Drop it on a side of the panel to snap it back.
   Noticed by: the arrow is no longer snapped to the panel.
4. **Size and lock** (shown)
   After the tutorial, right-click the arrow or the panel to lock that one in place: each has its own lock. The arrow's size, the text size and both locks are in Options > Directions.

### 5. Herbs and ore (`gather`, added in 1.2.0)

Six example nodes (Peacebloom, Silverleaf, Earthroot, Copper Vein twice, Tin Vein) within 80 yards of the player,
their tooltip "Example for the tutorial"; the Herbs and Ore layers are turned on and any Find Herbs and Ore pick is
set aside for the section.

1. **Example herbs and ore** (shown)
   These icons are examples for the tutorial. Yours appear as you gather, and you can import more.
2. **Show or hide them** (shown)
   The Herbs and Ore buttons in the map menu show or hide them. Find Herbs and Ore shows only the ones you pick.
3. **Draw a farming area** (the player does it)
   Click Draw a Farming Area in the map menu, under Herbs, Ore and Farming.
   Noticed by: the drawing is on (`G.drawMode`).
4. **Circle the icons** (the player does it; the drawing is turned on again after a loop that caught nothing)
   Drag a loop around the example icons.
   Noticed by: a new route with stops (the farming loop).
5. **A loop route** (shown; a loop through the examples is set if the last step was skipped)
   The route visits every one you circled until you reach them. To save work, only the paths to the next stops are drawn (3 at a time). Every stop is still in the route: reach one for the next path to appear. Options > Performance to adjust this number.

### 6. Custom pins (`pins`, added in 1.2.0)

Pinning and the pins' layer are turned on for the section. A pin made in it is practice: it is taken off again, as
if never made, when the tutorial moves on (its time is kept in the tutorial's saved part, so a /reload in between
loses nothing). The player's own pins are never touched.

1. **Create a pin** (the player does it)
   Hold Shift and click a spot on the map, then click Create Pin.
   Noticed by: the pin's window is open (or a pin was made).
2. **Name it** (the player does it; skipped to without a spot picked, the pin's window opens for a spot beside the player)
   Type a name, pick an icon, then click Create Pin.
   Noticed by: a pin was made since the section began.
3. **Route to your pin** (the player does it; a pin named "My pin" is made beside the player if the last steps were skipped)
   Double-click your pin: it becomes a stop and the route goes to it.
   Noticed by: a stop was added.
4. **Find it in the search** (the player does it; the search is opened, and reopened if it closes)
   Your pins are in Search Places too. Type its name in the search box: My pin
   (the name is the practice pin's own.) Noticed by: the name is in the search box, or a stop was added.
5. **Remove a pin** (shown)
   Right-click a pin to remove it. The pin made in this tutorial is practice: it is removed when you move on.

### 7. Search Places (`search`, added in 1.2.0)

1. **Open the search** (the player does it)
   Click the magnifier, Search Places, in the map menu.
   Noticed by: the search panel shows.
2. **Find your class trainer** (the player does it; the words are the game language's own, as the search takes them)
   Type this in the search box: class trainer
   Noticed by: the box holds those words in any case (or a result was picked already).
3. **Pick a result** (the player does it; the words are typed in if the last step was skipped)
   Click a result, or press Enter for the first one: it becomes a stop.
   Noticed by: one more stop. With no class trainer known for the character's faction the step says it can't be done.
4. **More to find** (shown)
   The search also finds flight masters, inns, towns and zones. Type what you need and get a route to it.

### 8. Dungeon maps (`dungeon`, added in 1.2.0)

The dungeon's map is opened from outside the way a click on its entrance icon opens it (`G.ShowInstance`).

1. **A dungeon's map** (shown)
   This is the map of Ragefire Chasm. Click a dungeon's entrance on the map to open its map like this.
2. **Bosses in order** (shown)
   The bosses are numbered in the usual order, with the usual path between them. You can mark off bosses and manually position yourself (when in a dungeon) with a double click.
3. **Back out** (shown; the map goes back to the player)
   Right-click the map to leave a dungeon's map. The tutorial has done it for you.

### 9. The map window (`window`, added in 1.2.0)

The window frame is turned on and the map and its size unlocked.

1. **Hide the map** (the player does it)
   Double-click the logo at the map's top left. The map hides and only the logo stays.
   Noticed by: the map is minimized.
2. **Bring it back** (the player does it)
   Double-click the logo again.
   Noticed by: the map is no longer minimized.
3. **Resize it** (the player does it)
   Drag the map's bottom-right corner.
   Noticed by: the size changed and the corner was let go.
4. **Any shape** (the player does it; "Any shape" is turned on)
   Any shape is on for this demo: drag the corner again to make the map wide or tall.
   One checkbox: "Any shape". Ticked, it is kept after the tutorial.
   Noticed by: the size or width changed and the corner was let go.
5. **In the game's world map** (shown; only told and offered: the tutorial stays on the map's own window)
   The GPS map can also show in the game's world map (M) instead of its own window. Check here to use it after the tutorial, or later in Options > Map.
   One checkbox: "Show the GPS map in the game's world map". Ticked, it is turned on as the tutorial ends.
6. **Returning to original** (shown)
   Size, shape and lock are in Options > Map window. Your own settings come back when the tutorial ends.

With the map as the minimap (kept in section 1, or the player's own setting), step 1 says instead: "With the GPS
map as your minimap, a double-click on the logo sends the map back to its corner instead." Step 2 is left out there
(asked 2026-11-11): the logo doesn't hide the map, and the resizing step opens the map by itself.

### 10. Fix roads and record (`roads`, added in 1.2.0, updated in 1.3.0)

The Map Editing button (the road and wall tools, one button since 1.3.0) is put on the map for the section. Everything
drawn, erased or recorded is practice.

1. **Practice only** (shown)
   Routes follow roads. Where one is missing or wrong, you can fix it. This is practice: nothing here is saved. The Map Editing button is on the map for this tutorial. Tick it here to keep it, or later in Options > Tools.
   One checkbox: "Map editing tools". What is ticked here is kept after the tutorial.
2. **Road Tools** (the player does it; the glow is on Map Editing while it's shut, then on Road Tools)
   Click Map Editing on the map, then Road Tools. Open, Map Editing shows the roads and walls.
   Noticed by: the road tools are on.
3. **Draw a road** (the player does it)
   Left-drag along where a road should be. Right-drag over a road erases it.
   Noticed by: a practice road stroke (drawn or erased) was made. The chat says "Practice: nothing was saved."
4. **Magic Eraser** (the player does it; a practice road is put across the player's spot if the last step was skipped)
   Click Magic Eraser, then drag its circle over the road you drew: the map's own roads are back there. Ctrl + mouse wheel sizes it.
   Noticed by: a practice road was taken out.
5. **Draw a wall** (the player does it)
   Wall Tools do the same for walls and cliffs that routes should go around. Click Wall Tools, then left-drag one.
   Noticed by: a practice wall stroke was made.
6. **Record a walk** (the player does it)
   Click Record on the map, then Record in its window, and walk a few steps.
   Noticed by: a recording is on and has gone 3 yards.
7. **Stop recording** (the player does it; a recording is started if the last step was skipped)
   Click Stop. A real walk is saved as a road, with its floors and rooms.
   Noticed by: no recording is on.
8. **Share your fixes** (shown; the practice strokes and walk are taken off the map)
   Real fixes work for you at once. Share them and they are added for everyone: Options > Help shows how. Your practice road, wall and walk are gone.

## Other text

- The sections' list (the panel's list and Options > Help): a section played through is "(done)"; one played before a
  later release changed it (its `updated`) is "(updated)"; one not played and added after the newest one played is
  "(new)". Only new sections bring the offer back; an updated one is only marked.

- The offer, first install: "Take a short tutorial? It shows the main features on your own map and puts everything
  back after. Options > Help plays it any time."
- The offer, after an update: "Take a short tutorial of the new features? It uses your own map and puts everything
  back after. Options > Help plays it any time."
- Starting: "Tutorial started. Everything goes back to how you had it when it ends."
- Leaving: "Tutorial closed: everything is back as you had it. Options > Help plays it again."
- After a /reload in the middle: "The tutorial was cut short, and everything is back as you had it. Carry on where you
  were?" (Yes / No)
- It can't start: "The tutorial can't start in combat, in a dungeon, on a flight, while dead or while recording a
  walk. Try again after." / "not during a game on the map" / "The tutorial is already running."
- Options > Help: "A short tour of the main features on your own map. Everything goes back to how you had it after."

## What's saved, and the snapshot

`AzerothGPSDB.tutorial` (account-wide): `seen` (section id = the version it was added in, for the sections played to
their end: the "(done)" marks), `ask` (the checkbox; Don't Ask Again sets it false), `declined` (Not Now so far),
`offered` (the newest section version the player was offered: the offer comes again only for sections newer than it),
`askedFor`, `fresh` (set at a first install, for the welcome title), and `run` while a tutorial runs.

Before the first step the tutorial takes a snapshot: every option of the map (`settings.gps`, whole), the character's
route (stops, loop, the zones and rides answered for it, RestedXP Route / Zygor Route on or off), the stops waiting for
Confirm Route, the map's view (browsed map, dungeon map, zoom), whether the road or wall tools were on and whether the
Record window was open. It's put back at the end of every section (so each section starts from the player's own
setup), at the end and on exit. While a tutorial runs the snapshot is in the saved variables (`tutorial.run`): after a
/reload, a logout or a crash the settings and the route are put back at the next login before the map starts, and the
tutorial is offered again from the section it was in.

Because the whole options table is put back, an option the player changes in the options window while a tutorial runs
is put back too.

## Choices made

- **Yes to "Keep the GPS map as your minimap?" keeps the size picked two steps earlier too** (the option on, at that
  size). Everything else goes back. No, or no answer, leaves the option as the player had it; a player who has it on
  already isn't asked.
- **The offer counts as taken once the player clicks Start Tutorial**, even if they exit early: it isn't offered again
  for those sections (Options > Help has them). Don't Ask Again also covers the sections on offer, so ticking the
  checkbox again brings the offer back only for a later update.
- **With the map as the minimap, sections 2 to 9 open it out and hold it out**: the 5 quiet seconds don't count
  (`G.mmHold`), "back when you move" and "back in combat" are off for the tutorial, and a map sent back by its arrow
  button is opened out again while a step needs it.
- **The practice is on for the whole tutorial**, not only section 9: a road, wall or recorded walk made at any point
  of a tutorial is practice and gone at the end. A tutorial can't be started while a real recording is on, and road or
  wall tools that were on are turned off first (so the player's own edits so far are applied as always) and on again
  after.
- **The quick buttons are in their default places while a tutorial runs** (Search Places, Quest Route and the
  farming group in the map menu, the road tools on the map), so the steps' "in the map menu" and "on the map" are
  true for everyone; a player's own arrangement comes back with everything else. With the menu closed the outline
  is on the menu's round button, then on the group's button, then on the button itself.
- **RestedXP Route and Zygor Route are paused for the tutorial** (they put their own stops into the route) and come
  back with the snapshot.
- **One generic line for a step that can't be done** rather than a reason each, to keep the text (and its ten
  translations) short. The window section's logo steps have their own line with the map as the minimap.
- **The Quest Route section has 2 or 3 steps**, the others 3 to 8.
- **The example across the sea** was picked to be a route the planner is known to make (Brill to Orgrimmar is the
  tests' own zeppelin trip); the Alliance one goes to Auberdine or Stormwind, not Darnassus.

## Not checked in the game

Everything runs in the test harness (a stand-in for the game's UI), which can't show how anything looks or how the
mouse behaves. To look at first, in this order:

1. **The offer and the panel**: a fresh character's first login (or delete `tutorial` from the saved variables): the
   window's size and its three buttons' widths in English and one long language (German or Russian); the panel's
   height following its text (it's sized again at each look, in case a text's height isn't known when it's first
   set); the panel over the map opened out of the minimap square.
2. **The outline**: that it sits on the right control at every step, most of all on the square's corner logo, the map
   window's logo, the minimized logo, the corner grip, and a quick button inside the opened map menu (with the menu
   closed it's on the menu's round button).
3. **The minimap section**: "Open the GPS map" noticed, "Close on movement" (take one step), the three sizes, and
   the Minimap given back properly when the section ends with No.
4. **Drags**: the arrow steps (dragging the directions panel, pulling the arrow off) and the window steps (the corner
   grip, also with "Any shape") are noticed only from the settings the addon saves when a drag ends; in the harness
   those are set directly.
5. **Double-clicks on the logo** (hide, bring back): the harness calls the minimize function; the two real clicks
   weren't simulated.
6. **The search step**: typing in the box with the panel under the tutorial panel's control (it's reopened if it
   closes while the step waits), in a non-English client too ("class trainer" in the game's language).
7. **The route across the sea** on an Alliance character and on Zephras Isle; and for a low-level character that no
   "route there anyway?" question comes up.
8. **Ragefire Chasm's map** opened from the open world, and back.
9. **The road section**: the road tools' buttons appearing on the map for a player who never turned them on, a
   practice stroke drawn (green; an erase red, a wall dark red), the Record window, a practice walk, and that Undo,
   the saved-changes count and Save Now stay untouched.
10. **Combat in the middle** of a step, and a `/reload` in the middle (everything back, then "Carry on where you
    were?").
11. **The ten translations** were written without a native reader; the terms follow each locale file's own.
