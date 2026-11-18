# Public API for plugin addons

`Api.lua` publishes a global table `AzerothGPS` (version 21) so other addons, such as
AzerothGPS-StreetView, can read the map's geometry and draw on the map. It stays display
only, like the rest of AzerothGPS. Declare `## Dependencies: AzerothGPS` in your toc.

World coordinates are yards on a continent: **x points north, y points west**, in the order
`UnitPosition` returns them (see `coordinates.md`). Map offsets are UI units from the map's
center, +x right and +y up.

## Geometry

| Function | Returns |
|---|---|
| `PlayerWorld()` | x, y, continent, z; nil in instances or when the game hides it. Always where the game says the player is, even while AzerothGPS's developer tools show the map from a simulated spot |
| `Facing()` | radians, counter-clockwise from north (the game's, like `PlayerWorld`) |
| `PlayerLevel()` | the level the player is on (API 16): an underground city's own (Undercity: 10001) when the game reports its map, a dungeon's level inside one, else the continent. From where the game says the player is, like `PlayerWorld` |
| `ShownLevel()` | the underground city level whose art the map is showing (API 16), else nil |
| `BaseContinent(cont)` | the continent an underground city level is drawn on |
| `ToContinent(from, x, y, to)` | (x, y) on continent `from` in continent `to`'s coordinates, by where both sit on the world map (a spot on one continent drawn over the other's world map); nil when either has no world frame. A map shown as an inset on the world map (Zephras Isle, continent 2991) lands on its inset (version 7) |
| `LocateWorld(cont, x, y)` | uiMapID, zone name, u (east), v (south) of the smallest zone there |
| `MapToWorld(uiMapID, u, v)` | x, y, continent |
| `Roads(cont)` | the shipped road network, read only (`Data/Roads.lua` format) |
| `NearestRoad(cont, x, y)` | x, y, distance, edge index of the closest road point routing uses; nil while that continent's roads are still being built in the background (a moment after a /reload) |
| `RoadEdge(cont, edge)` | that edge's table, read only; its points start at index 5 |

## The map window

| Function | Returns |
|---|---|
| `MapFrame()` | `AzerothGPSFrame` |
| `MapCanvas()` | the clipped map area |
| `MapButtonParent()` | a frame above the map for your buttons (anchor inside it) |
| `MapShown()` | whether the map is visible |
| `MapButton(name)` | the map's `"recenter"` button (Back to your position; shown only while panned away) or `"import"` button (always shown), to place your buttons around them; or (version 13) `"toppanel"`, the directions panel at the map's top (shown while there's a route; the player may make it narrower or detach it into its own window, 1.3.9: then its parent is UIParent): hook its `OnShow`, `OnHide` and `OnSizeChanged` to keep a panel of yours under it; or (version 14) `"logo"`, the window frame's logo plate (hidden with the frame while it's off, `TopPanelInset()` 4; nil where the client has no window frame template), over every part of the frame. The frame's border is at frame level 500 (the client's template): a frame of yours over the border goes above that, under the plate's level to go behind the logo |
| `View()` | center x, y, continent, rotation, scale (UI units per yard), half width |
| `SaveView()` | the whole map view, to put back later (version 8): following the player, or the map browsed (a continent's, the world's, a zone's, a dungeon's and its floor) with its zoom and middle, or the terrain view looked around. An opaque table |
| `RestoreView(state)` | puts back a view from `SaveView` (right-click still goes back where it did); nil, following, or no longer valid: follows the player (version 8) |
| `CursorWorld()` | x, y, continent under the mouse pointer; nil unless it's over the map. On a dungeon's map: its level as the continent, and a 4th value, z: the height there on the floor shown |
| `Instance()` | the dungeon or raid whose map is in view: level (20000 + MapID: its coordinates' "continent"), MapID, name, the floor shown (0: all, else counted from the top), how many floors; nil when none is. The game hides the player's position inside, so pick spots here by browsing its map (its entrance's icon, or it's shown while the player is in it) with the `+` / `-` floor buttons |
| `InstanceFloors(level)` | its floors, lowest first: `{ { lowest z, highest z }, ... }` |
| `WorldToMap(x, y)` | the point's offset from the map's center as drawn now |

## Drawing on the map

- `SetOverlay(name, fn)`: `fn(ctx)` runs on every redraw inside a `pcall`. `ctx.cont` is the
  continent in view and `ctx.zoom` the yards from center to edge. Draw with
  `ctx.Line(x1, y1, x2, y2, {r, g, b}, width, alpha, dotted)` and
  `ctx.Dot(x, y, {r, g, b}, size, alpha)` in world yards; `ctx.ToScreen(x, y)` converts.
  `ctx.Icon(x, y, texture, size, alpha)` (version 10) puts an icon there: a file id, a path or
  `"atlas:<name>"`, `size` UI units across.
  `ctx.level` (version 21) is the level the map shows: an underground city's own on its map
  (Undercity: 10001, in the continent's coordinates), else `ctx.cont`.
  The lines join the map's own: clipped, rotated with the map, drawn above the route, never
  faded. Pass `nil` to remove the overlay. Errors are logged like the map's own.
- `ShowRoads(owner, on, {r, g, b})`: shows the road network in that color while any owner
  asks. The player's own road option wins.
- `HoldMap(owner, on, onDoubleClick)`: while any owner holds the map (a game on it), the
  route (still followed; the arrow window is unchanged), the stops' pins, the crosshair with
  Confirm Route and the top panel aren't shown, and a double-click on the map or one of its
  icons calls `onDoubleClick(x, y, continent)` instead of making a stop. `on = false` lets go.
- `HoldMap(owner, on, onDoubleClick, opts)` (version 9): `opts.style` draws the map in that style
  while it's held, at every zoom as for a player who picked it, whatever the player's own setting
  (which isn't changed, and is back on release): `"minimap"` (the terrain view), `"zone"` (the
  world map's art, every area shown), `"unrevealed"` (the world map's art with no area shown at
  all: the same for every character), or `"nospoiler"` (the areas this character explored).
  Holding again with another style updates it. Meanwhile the Map Style buttons and `/agps style`
  don't change it (they say the game on the map sets it). No `opts`, or no style: as before.
  An older AzerothGPS ignores the 4th argument: check `AzerothGPS.version >= 9`.
  The player's own styles (the `style` setting, since 1.1.9): `"seamless"` (OpenMap, as the player sees it named; the default: the terrain,
  and the wheel on out past the land onto a stitched world map), `"minimap"` (Terrain), `"zone"`
  (World Map) and `"nospoiler"` (No Spoiler Map); `"seamless"` isn't a held style.
  While any owner holds the map, the seamless map is set aside: the held style (or the player's) draws as it
  always did, with the zoom limits it always had, and the player's setting is back on release. Nothing changed in the API (still version 17).
- `LookAt(cont, x, y, zoom)`: centers the map on that spot, north up, `zoom` yards from the
  middle to the edge. "Back to your position" or `Follow()` returns to the player.
- `ShowWorld()`: the world map, as right-clicking out to the top level (from the terrain view, a
  click on a continent and then on a spot comes back to the terrain view there).
- `Follow()`: back to following the player.
- `Window(name, width, height, title, strata)` (version 11): a popup window in AzerothGPS's style, the
  map window's frame without the logo (the game's metal border, title bar and close button, a dark
  inside, the title centered), movable and closed by Escape; a plain dark box with a border where the
  client lacks the template. It starts hidden; put its content from `f.top` (negative) down, and
  change the title with `f:SetWindowTitle(text)`.
- `RegisterPopup(frame, strata)` (version 20): a window of your own making (not from `Window`) goes over the map
  while the player has it opened out of the minimap square, as `Window`'s do, and back to its own strata after
  (`strata`, default: its strata when registered).
- `OnIconShiftClick(owner, fn, hint)` (version 12): a Shift-click on a boss icon in a dungeon's map is offered to `fn(info)` first (`info`: `kind = "boss"`, `name`, `x`, `y`, `z`, `cont` = the dungeon's level); `fn` returns true when it used it. `hint` (a string, or `hint(info)`) says what it does: the boss's tooltip shows "Shift-click: <hint>" and, inside the dungeon, the map's top line "Shift-click a boss: <hint>". `fn = nil` removes it.
  Version 20 offers Shift-clicks on NPCs too, so check `info.kind`: an NPC in a building's or cave's inside map, an
  NPC's row in Search Places, and a pin made from one with its Pin button give `info` = `kind = "npc"`, `id` (the
  creature id, `Data/Npcs.lua`'s), `name`, `title`, `x`, `y`, `z` (its height), `cont` (the continent) and `floor` (the
  level when it isn't the continent: Undercity's 10001; else nil). A click `fn` doesn't use does what it did before (a
  search row: a stop; a pin: shared in chat). `hint(info)` returning nil for an NPC leaves its tooltip without a
  "Shift-click: ..." line (a search row then has no tooltip). Both maps alike: the window and the map in the world map.
- `ShowMap()`: shows the map window when the player has it hidden.
- `TopPanelInset()`: the left inset (pixels) the top panel starts at: past the window frame's
  portrait when the frame is on, else 4. Line up a panel of your own there with it.
- `OnLayout(owner, fn)`: `fn(inset)` is called when that inset changes (the window frame turned
  on or off); `fn = nil` stops.
- `Redraw()`: the map redraws on its next frame. The map skips redraws when nothing it knows
  about changed, so call this after changing what your overlay draws.

## Your options page and Save Now (version 13)

- `AddOptionsPage(owner, title, build)`: a page called `title` in AzerothGPS's options window. After AzerothGPS's own
  pages, each addon gets a section of its own in the list, headed with its name less "AzerothGPS" (`owner`
  "AzerothGPS_Example" or "AzerothGPS Example" -> **Example**), its pages under it in the order added ("General",
  "History"...); the page itself is headed "Example: General".
  `build(ui)` runs once when the window is built, or at once if it's built already; calling again with the same
  `owner` and `title` replaces that page. It runs in `pcall`: an error stays in your page (the window says so in chat). Returns true
  when added. `ui` has the helpers AzerothGPS's own pages use, each placing its control under the last:
  - `ui.header(text, note)`, `ui.note(text)`
  - `ui.check(label, tip, get, set)`
  - `ui.slider(label, min, max, step, fmt, get, set, enabled)`: `fmt` a format (`"%d"`) or a `function(v)` returning
    the text ("7 days", "Always")
  - `ui.button(label, width, onClick)`: returns the button
  - `ui.choice(label, options, get, set, enabled)`: radio buttons, `options = { { value =, text =, tip = }, ... }`
  - `ui.dropdown(label, options, get, set, enabled)` (version 15): the same arguments as `ui.choice`, as a box showing
    the one picked; a click opens the list under it (12 rows at most, the mouse wheel scrolls the rest, each option's
    `tip` on its row), a click on a row picks it, a click anywhere else closes it. Returns the box. For more than a
    few choices, where radio buttons take a row each.
  - `ui.text(getText)`: a line whose text is read again on every refresh
  - `ui.place(frame, height, indent)`: a frame of your own, placed like the rest; `ui.page`: the page's frame

  `get()`, `enabled()` and `getText()` are read again whenever the window refreshes (it opens, a setting changes,
  `RefreshOptions()`), each in `pcall`.
- `RefreshOptions()`: read them all again (your own state changed).
- `ShowOptions(title, owner)`: open the options window at the page `title`: `owner`'s when given (pass yours: "General"
  without an owner is AzerothGPS's own), else one of AzerothGPS's. False when there's no such page.
- `SetUnsaved(owner, count, text)`: the game saves addons' data only at logout, quitting and `/reload`; a crash loses
  what came since. Tell AzerothGPS how many of your things are waiting (`count`; 0 clears it) and your line for the
  tooltip (`text`, e.g. "Example: 3 notes"). Counted only since the map's Save and Dismiss buttons were removed
  (2026-11-17); kept so plugins calling it keep working.
- `SaveNow()`: a `/reload`, which saves every addon's data. Never in combat: false then.

## Looks and arrivals (version 14)

Only how the map looks, never what it does. Each `owner` sets its own look (`nil` takes it away); the look set last
shows, and AzerothGPS's own without any.

- `SetPlayerArrow(owner, look)`: the player's arrow on the map. `look.texture` (a path or file id) pointing up; it's
  turned with the facing as the game's arrow is. `width`, `height` (UI units; 32 by default), `coords = { left, right,
  top, bottom }` (texture coordinates: one frame of a sheet; call again with others to animate), `color = { r, g, b }`
  (a tint).
- `SetRouteLook(owner, look)`: the route. `color = { r, g, b }` (the roads and the legs off them; rides a darker
  shade; a trip of several stops keeps its stops' colors), `rainbow = true` (the rainbow's colors along it, every
  stop's legs), `width` (times the usual, 0.5 to 3), `glow = true` (a wide faint line under it), `dotted = true`
  (every leg dotted). The way back to your body stays red.
- `SetFrameLook(owner, look)`: the window frame (while it's on). `border = { r, g, b }` (a tint over its metal),
  `title = { r, g, b }` (the title bar's color), `text = { r, g, b }` (the title's).
  Version 17: `buttons = { r, g, b }` (the panel buttons') and `close = { r, g, b }` (the close buttons', the X;
  without it, `buttons`): on the map window, and on yours registered with `RegisterLookFrame` (below); not on
  AzerothGPS's options window or popups (since version 19: the player's window options are the map window's). Only panel buttons (UIPanelButtonTemplate: their Left, Middle or
  Center and Right pieces, and their normal, pushed and disabled textures) and close buttons (the frame's
  `CloseButton` or `closeButton`); never icon buttons, nor anything on the map's own layers. Highlights and text
  stay as they are. A color AzerothGPS gives a button by its state is multiplied by yours, not replaced.
  Your colors come out true: each button texture, and the border's pieces for `border`, is grayed first
  (`SetDesaturated(true)`) and then colored, so a green is green over the game's red button art; with no look, the
  game's own art again. A preview of yours matches when it grays the same way.
- `OnArrive(owner, fn)`: `fn(info)` when a stop is reached, in `pcall`: `info = { x, y, cont, name, last, kind }`,
  `last` true for the trip's last stop, `kind` "stop" or "boss" (a boss stop is reached when it dies). `fn = nil`
  stops.

## The title bar (version 15)

- `TitleBarSlot(owner, width)`: a place for a widget of yours on the map window frame's title bar, at its right, left
  of the close button. Returns the slot, a frame `width` UI units wide and 20 high (the title bar's middle is its
  middle), above every part of the frame (its border is at frame level 500), under the logo: parent your widget to it,
  at its level + 1 or more. Calling it again with the same `owner` resizes the same frame; `width = nil` lets it go (it's hidden)
  and returns nil. Several owners' slots go right to left in the order asked.
- The slot shows only while the window frame does and the title bar has room for it: hidden while the frame is off
  (Options > Map window > Window frame), on a map too narrow for it and 50 units of the title, and until the map is built
  (a slot asked for before is placed then), and wherever the client has no window frame. Hook its `OnShow` and `OnHide`
  to put your widget elsewhere meanwhile, and check `IsShown()` when you first place it.
- While a slot shows, the title (the place's name) sits left, right after the logo, and stops before the slots: one
  line, cut short with "..." on a narrow map, never under them. With none, it's centered as before.
- The slot doesn't take the mouse, so dragging the title bar still moves the map; a widget of yours that takes the
  mouse covers that part. It fades with the map's frame while the player moves (the window frame's opacity).
- Also in version 15: `ui.dropdown` for your options pages (above).

## Button colors on your windows (version 17)

- `RegisterLookFrame(frame)`: your own window takes the frame look's `buttons` and `close` colors (above) on its
  panel and close buttons: at once, again at every look change, and each time it's shown (buttons you make after
  registering it are covered then). Kept weakly: a window you let go isn't held. Returns true. Name its X
  `frame.CloseButton` (as PortraitFrameTemplate does) or `frame.closeButton` for the close color.
- `FrameLook()`: the frame look shown, `{ border, title, text, buttons, close }` (each `{ r, g, b }` or nil), a
  copy; nil when there's none.

## Options > Map window's looks and your charms (version 19)

- The player picks the map window's own looks in Options > Map window (the route's color: Options > Map): a celebration on reaching the trip's last stop
  (confetti, fireworks or none), the frame's tint and its buttons' and X's colors, the route in blue or a rainbow, and a
  charm hanging from the logo. A look you set (`SetFrameLook`, `SetRouteLook`) shows over theirs while it's set;
  `FrameLook()` gives the one shown, theirs too. Arrivals (`OnArrive`) still reach you as before.
- `AddCharm(owner, def)`: a charm of yours in that list, after AzerothGPS's own, for the player to pick there. `def =
  { key, name, tip, file, art }`: `file` is your textures' path without the `_<k>x` each ends in (`..._1x`, `_2x`,
  `_3x`: k screen pixels an art pixel, picked by the screen); `art = { w, h, frames, cols, ax, ay, tex }`: the picture's
  cell in art pixels, its frames (a half turn on its string, left to right then down, 1 art pixel apart; drawn mirrored
  for the other half), `cols` frames a row, the point it hangs by (`ax`, `ay` from the cell's top left), and `tex = {
  [1] = { width, height }, [2] = ..., [3] = ... }` your textures' sizes. Or `smooth = k`: one texture, `tex[k]` only,
  scaled to the screen. `scale`: its size, times its art pixels' (0.25 to 4; 1 unless given). Checked as data: false when it isn't well made or its key is one of AzerothGPS's. Called again
  with the same key, it's replaced.

## An import inbox (map data from a tool on the player's PC)

Not a function: a global any loaded file may define, for a tool on the player's PC that has map data for them:

```lua
AzerothGPS_ImportInbox = {
  { made = 1791234567, text = [==[
H 0 2100.0,400.0 name=Peacebloom
P add 0 1790000003 2250.5,230.0 icon=134400 name=Old Tree
]==] },
}
```

- `made`: a whole number of the entry's own (the time it was made works); `text`: AzerothGPS map data, the lines its
  Import and Share window reads (`MapText.lua`'s: roads, walls, pins, herbs, ore, NPCs). `/way` lines aren't taken
  from an inbox: it never changes the route.
- AzerothGPS reads it once every addon is loaded (at login, a `/reload` too), as data only: up to 50 entries, each
  text within the window's limits; anything else is passed over. The entries it hasn't handled are offered to the
  player once, with what they hold; Yes takes them in as the window's Import does (the player's own data, never
  AzerothGPS's), No declines them; unanswered, they're offered again next time.
- Each entry handled is acknowledged in AzerothGPS's saved data (`AzerothGPSDB.importInbox[made] = { at, added =
  { roads, walls, pins, herbs, ore, npcs }, had, rejected, declined }`), written at the next `/reload` or logout: read
  it there and drop those entries from your file.

## The seamless zoom's knobs (version 18, for developer tools)

`SeamKnobs()` returns a table to turn the seamless map's transition levels live (issue #72, for AzerothGPS's private
developer tools, which are never shipped). Nothing changes unless it's called; values aren't saved (a `/reload` is
back to the shipped ones), and the map redraws at once after each change.

- `List()`: `{ { name, value, default, min, max } }`. The names: `SEAM_TERRAIN_ZOOM` (yards: where the
  notches are counted from), `SEAM_SHARP_NOTCHES` (may be negative: the transition starts that many notches sooner),
  `SEAM_ART_NOTCHES`, `SEAM_TILES_NOTCHES`, `SEAM_WORLD_NOTCHES` (wheel notches, fractions too), `ZOOM_STEP` (the
  wheel's notch), `SEAM_WORLD_MARGIN`, `INTERIOR_FEATHER_YD` (yards: the soft edge round a dungeon's or cave's rooms
  over the world art, issue #85); and once the stitched map is loaded its close-up's `minimapFrom`,
  `minimapDeep`, `soften` (a boolean: its `min` is `"boolean"`) and `closeUpFrom` (the most detail zoom the art is
  told on the map: 8, the zones' map whole and sharp; raise it to let the close-up show, issue #90).
- `Get(name)`, `Set(name, value)`: true when set (kept in its range; `nil` sets the shipped value), false for an
  unknown name or the wrong kind of value. `Reset()`: every knob back to the shipped value.
- `Stages()`: `{ artIn = { from, to }, tilesOut = { from, to }, iconsFew, worldZoom }`, yards at the reference size.
- `Reading()`: the blend as last drawn (`zoom`, `ref`, `notch`, `art`, `tiles`, `artOnly`, `seamFar`, `cont`, `x`,
  `y`), or nil before a redraw.
- `Report()`: all of it (the knobs, the stages, the map's size, the reading, the place, the version and build) as one
  block of text to copy.
