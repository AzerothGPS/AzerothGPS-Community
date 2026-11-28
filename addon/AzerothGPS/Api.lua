-- Public API for companion addons (AzerothGPS-StreetView and others): read the map's
-- geometry and draw on the map. Display only, like the rest of AzerothGPS. See docs/api.md.
-- World coordinates are yards on a continent: x points north, y points west (UnitPosition's
-- order). Everything here is safe to call before the map exists; it returns nil then.
local _, ns = ...

local API = { version = 23 }
_G.AzerothGPS = API

local function GPS() return ns.GPS end

-- The player: x, y, continent, z (nil in instances or when the game hides it).
-- (always the game's own: the dev tools' simulated player, Geo.override, isn't passed on, so a companion that records
-- where the player goes never counts a simulated drive)
function API.PlayerWorld() return ns.Geo.RealPlayerWorld() end
-- Facing in radians, counter-clockwise from north (0 when unavailable).
function API.Facing() return ns.Geo.RealFacing() end -- (the game's own, as PlayerWorld)

-- The level the player is on (API 16, for AzerothGPS-StreetView's Undercity views): an underground
-- city's own level (Undercity: 10001) when the game reports its map, a dungeon's inside one, else the
-- continent. From where the game says the player is, like PlayerWorld.
function API.PlayerLevel()
  local _, _, cont = ns.Geo.RealPlayerWorld()
  if not cont then return nil end
  return ns.Nav and ns.Nav.PlayerLevel and ns.Nav.PlayerLevel(cont) or cont
end

-- The underground city level whose art the map is showing (API 16), or nil: the player seeing
-- Undercity's map gets 10001 here while CursorWorld still speaks in its world coordinates.
function API.ShownLevel()
  local g = GPS()
  local lvl = g and g.shownLevel
  local l = lvl and ns.CityLevels and ns.CityLevels[lvl]
  if l and not l.instance then return lvl end
  return nil
end
-- The continent an underground city level (a pseudo-continent) is drawn on; others unchanged.
function API.BaseContinent(cont) return ns.Geo.Base(cont) end
-- (x, y) on continent `from` in continent `to`'s coordinates, by where both sit on the world map
-- (to draw a spot on one continent over the other's on the world map); nil when either has none.
-- (Version 7: a map shown as an inset on the world map, Zephras Isle, lands on its inset.)
function API.ToContinent(from, x, y, to) return ns.Geo.ToContinent(from, x, y, to) end
-- (Version 8) The whole map view, to put back later (a game on the map ending): following the
-- player, or the map browsed (a continent's, the world's, a zone's, a dungeon's and its floor)
-- with its zoom and middle, or the terrain view looked around. An opaque table.
function API.SaveView()
  local G = GPS()
  if not G then return nil end
  return G.SaveView() or { follow = true }
end
-- Put back a view from SaveView; nil, following, or one no longer valid: following the player.
function API.RestoreView(state)
  local G = GPS()
  if not G then return end
  if type(state) ~= "table" or state.follow or not state.x then return G.Follow() end
  G.ApplyView(state)
end
-- The smallest zone on continent `cont` containing (x, y): uiMapID, name, u (east), v (south).
-- (not `GPS() and GPS().f()`: `and` keeps only a call's first value)
function API.LocateWorld(cont, x, y)
  if GPS() then return GPS().LocateWorld(cont, x, y) end
end
-- uiMap point (u east, v south, 0-1) -> world x, y and the map's continent.
function API.MapToWorld(mapID, u, v)
  local m = ns.Maps and ns.Maps[mapID]
  local b = m and m.bounds
  if not b then return nil end
  return b[3] - v * (b[3] - b[1]), b[4] - u * (b[4] - b[2]), m.continent
end

-- The shipped road network of `cont` (read only!): { n = { x1, y1, ... }, e = { { a, b, len,
-- source, x, y, x, y, ... }, ... } }. Data/Roads.lua has the details.
function API.Roads(cont) return ns.Roads and ns.Roads[cont] end
-- The nearest point on the road network routing uses: x, y, distance (yards), edge index.
function API.NearestRoad(cont, x, y)
  local R = ns.Router
  -- (the continent's roads not built yet, after a /reload: built in the background, nil meanwhile,
  -- rather than all at once in this frame)
  if R and R.WARM and not R.SYNC_WALKS and R.GraphReady and (not R.GraphReady(cont) or (R.Warming and R.Warming())) then
    R.WarmUp(cont, x, y)
    return nil
  end
  local n = R and R.Nearest and R.Nearest(cont, x, y)
  if not n then return nil end
  return n.px, n.py, n.dist, n.edge
end
-- That edge's points (read only!), as in API.Roads: e[5], e[6] is its first point.
function API.RoadEdge(cont, edge)
  local R = ns.Router
  local edges = R and R.Edges and R.Edges(cont)
  return edges and edges[edge]
end

-- The map window (AzerothGPSFrame), its clipped map area, and a frame above the map for
-- buttons (anchor to it; it isn't clipped).
function API.MapFrame() return _G.AzerothGPSFrame end
function API.MapCanvas() return GPS() and GPS().Canvas() end
function API.MapButtonParent() return GPS() and GPS().TopLayer() end
-- One of the map's own buttons, to place yours around it: "recenter" (Back to your
-- position: shown only while the map is panned away from you) or "import" (always shown); or (API 13) "toppanel",
-- the directions panel at the map's top (shown while there's a route): hook its OnShow, OnHide and OnSizeChanged to
-- put a panel of yours under it; or (API 14) "logo", the window frame's logo plate (hidden with the frame when it's off; nil where the client has no window
-- frame template), over every
-- part of the frame: the frame's border is at frame level 500, the plate above it.
function API.MapButton(name)
  local b = GPS() and GPS().mapButtons
  return b and b[name] or nil
end
-- (1.4.2) A button of yours in the map menu, on its row going right after Import and Share (or at the end of its
-- column with the player's option, Options > Keys and buttons): made on API.MapButtonParent(), any size near 28; the map
-- places it, shows it with the menu's buttons and lets the controller press it. `label`, `tip`: its name and line for
-- the controller's tooltip (its own OnEnter shows as ever). Returns true once it's in.
function API.MapMenuButton(button, label, tip)
  local g = GPS()
  if not (g and g.AddCompanionButton and button) then return false end
  return g.AddCompanionButton(button, label, tip) ~= nil
end
-- (1.4.2) Your map menu button shown with the menu's buttons (`shown` true, as it starts) or not at all: the map shows and
-- hides the buttons it places, so hide yours through this, not with :Hide().
function API.MapMenuButtonShown(button, shown)
  local g = GPS()
  return (g and g.SetCompanionShown and g.SetCompanionShown(button, shown)) or false
end
function API.MapShown() return GPS() and GPS().IsVisible() or false end
-- The last drawn view: center x, y, continent, rotation (radians), scale (UI units per
-- yard), half the map's width (UI units).
function API.View()
  if not GPS() then return nil end
  return GPS().ViewState()
end
-- The world point under the mouse pointer: x, y, continent (on a dungeon's map: its level,
-- and z, the height there on the floor shown); nil unless it's over the map.
function API.CursorWorld()
  if GPS() then return GPS().CursorWorld() end
end

-- The dungeon or raid whose map is in view (browsed from its entrance's icon, or the one the
-- player is in: the game hides their position there): level (20000 + its MapID, the
-- "continent" its coordinates are in), MapID, name, the floor shown (0: all of them, else
-- counted from the top; the map's "+" / "-" buttons), how many floors. nil when none is.
function API.Instance()
  local G = GPS()
  if not (G and G.ViewInstance) then return nil end
  local lvl, floor = G.ViewInstance()
  local info = lvl and ns.Instances and ns.Instances[lvl]
  if not info then return nil end
  return lvl, info.map, info.name, floor or 0, #G.InstanceFloors(lvl)
end
-- A dungeon's floors, lowest first: { { lowest height, highest }, ... } (world z).
function API.InstanceFloors(level)
  local G = GPS()
  return G and G.InstanceFloors and G.InstanceFloors(level) or {}
end
-- A world point's offset from the map's center in UI units (+x right, +y up), as drawn now.
function API.WorldToMap(x, y)
  if not GPS() then return nil end
  local cx, cy, _, rot, s = GPS().ViewState()
  local dx, dy = ns.Geo.ScreenOffset(cx, cy, x, y)
  return ns.Geo.Rotate(dx * s, dy * s, rot)
end

-- Draw on the map: fn(ctx) runs on every redraw (in a pcall). ctx.cont is the continent in
-- view; ctx.Line(x1, y1, x2, y2, { r, g, b }, width, alpha, dotted) and
-- ctx.Dot(x, y, { r, g, b }, size, alpha) take world yards; ctx.ToScreen(x, y) gives UI units
-- from the center; ctx.zoom is yards from center to edge. fn = nil removes it.
-- (Version 10) ctx.Icon(x, y, texture, size, alpha): an icon there (a file id, a path, or
-- "atlas:<name>"), `size` UI units across.
-- (Version 21) ctx.level: the level the map shows, an underground city's own (Undercity: 10001)
-- on its map, else ctx.cont.
function API.SetOverlay(name, fn)
  if not GPS() then return end
  GPS().overlays[name] = fn
  GPS().Redraw()
end
-- Show the road network (in color { r, g, b }) while `owner` wants it; on = false stops.
function API.ShowRoads(owner, on, color)
  if not GPS() then return end
  GPS().roadOwners[owner] = on and (color or { 0.25, 0.6, 1 }) or nil
  GPS().Redraw()
end
-- Hold the map for a while (a game on it): while any owner holds it, the route (still followed,
-- and the arrow window unchanged), the stops' pins, the crosshair with Confirm Route and the top
-- panel aren't shown, and a double-click on the map (or on one of its icons) calls
-- onDoubleClick(x, y, continent) instead of making a stop. on = false lets go.
-- (Version 9) `opts.style`: the map drawn in that style while held, whatever the player's own setting
-- (not changed; back on release): "minimap" (the terrain view), "zone" (the world map's art, every area
-- shown), "unrevealed" (the world map's art with no area shown: the same for every character), or
-- "nospoiler". The style buttons and /agps style don't change it meanwhile. Holding again updates it. Never
-- "seamless" (the player's default style, issue #75): held, the map draws as it always did, no seamless zoom.
function API.HoldMap(owner, on, onDoubleClick, opts)
  local G = GPS()
  if not G then return end
  local style = type(opts) == "table" and G.HOLD_STYLES[opts.style] and opts.style or nil
  G.SetHolder(owner, on and { click = onDoubleClick, style = style } or nil)
end
-- Look at a spot: the map centered on (x, y) of `cont`, north up, `zoom` yards from the middle
-- to the edge. "Back to your position" (or API.Follow) returns to the player.
function API.LookAt(cont, x, y, zoom)
  if GPS() then GPS().LookAt(cont, x, y, zoom) end
end
-- The world map (both continents), as right-clicking out to the top level.
function API.ShowWorld()
  if GPS() then GPS().ShowWorld() end
end
-- (Version 11) A popup window in AzerothGPS's style: the map window's frame without the logo (the
-- game's metal border, title bar and close button, a dark inside, the title centered), movable, closed
-- by Escape. Hidden; its content goes from f.top (negative) down; f:SetWindowTitle(text).
function API.Window(name, width, height, title, strata)
  return ns.Window(name, width, height, title, strata, { noLogo = true }) -- (another addon's window: no AzerothGPS logo)
end
-- (Version 20) A window of another addon's own making (not API.Window), lifted over the map opened out of the minimap
-- square while it shows, as AzerothGPS's own popups are (asked 2026-11-15: "Streetview windows should show on top of
-- AzerothGPS pop out window in minimap mode"); `strata` its own (default: its strata now).
function API.RegisterPopup(frame, strata)
  if frame then ns.RegisterPopup(frame, strata) end
end
-- (Version 12) Shift-click on a boss icon in a dungeon's map: fn(info) is offered it first, info =
-- { kind = "boss", name, x, y, z, cont } (cont: the dungeon's level, 20000 + its MapID); fn returns true when
-- it used the click. `hint` (a string, or hint(info) giving one or nil) says what the click does, e.g.
-- "its street view": the boss's tooltip shows "Shift-click: <hint>", and inside the dungeon the map's top
-- line "Shift-click a boss: <hint>" (info has no x, y there). fn = nil removes it.
-- (Version 20, issue #383) NPCs too: a Shift-click on an inside map's NPC, an NPC's row in Search Places or a pin made
-- from one is offered as info = { kind = "npc", id (Data/Npcs.lua's creature id), name, title, x, y, z, cont (the
-- continent), floor (the level when not the continent: Undercity's 10001) }. Check info.kind. Not used: AzerothGPS's own
-- Shift-click (a pin shared in chat). hint(info) nil for an NPC: no "Shift-click: ..." line in its tooltip.
function API.OnIconShiftClick(owner, fn, hint)
  local G = GPS()
  if not G then return end
  G.iconClicks[owner] = fn and { click = fn, hint = hint } or nil
  G.Redraw()
end
-- Back to following the player.
function API.Follow()
  if GPS() then GPS().Follow() end
end
-- Show the map window (when the player has it hidden).
function API.ShowMap()
  if not (ns.settings and ns.settings.gps) then return end
  ns.settings.gps.shown = true
  if ns.Options and ns.Options.Apply then ns.Options.Apply() elseif GPS() then GPS().ApplySettings() end
end

-- The left inset (pixels from the map's left edge) the top panel starts at now: past the window
-- frame's portrait when the frame is on, else 4. A panel of your own there can line up with it.
function API.TopPanelInset()
  local G = GPS()
  return G and G.topInset or 4
end
-- fn(inset) is called when that inset changes (the window frame turned on or off); fn = nil stops.
function API.OnLayout(owner, fn)
  local G = GPS()
  if G then G.layoutHooks[owner] = fn end
end

-- Redraw the map on its next frame (after changing what an overlay draws).
function API.Redraw()
  if GPS() then GPS().Redraw() end
end

-- (API 22's ShowRecorder, Recording and RecordedWalks went in 1.3.14, with the recorder: no longer in this table.)

-- (API 23, for a companion reviewing routes: the live route set to a place, and to a recorded walk being checked)
-- RouteTo(level, x, y, z, name): the route replaced by one stop there (`level` as PlayerLevel's, `z` its height, for its
-- floor, or nil), as a stop the player made on the map; the route is worked out from wherever the player is. True when
-- set; false (and true while a zone too high is asked about first) when not. Nothing moves the character.
function API.RouteTo(level, x, y, z, name)
  level, x, y = tonumber(level), tonumber(x), tonumber(y)
  if not (level and x and y and ns.Nav and ns.Nav.SetStops) then return false end
  local ok, asking = ns.Nav.SetStops({ { x = x, y = y, cont = level, z = tonumber(z), name = name, icon = 1 } })
  if ok and GPS() then GPS().Redraw() end
  return ok and true or false, asking and true or nil
end
-- PreviewWalk(times, done): routes take the player's recorded walks with those times (their `time`s in the saved roads) as the
-- way, far ahead of any other road, as they will once the walk replaces the route there in the data; the roads built
-- again and the route worked out again at once. PreviewWalk(nil) ends it. Never saved (a /reload ends it too). True
-- and how many walks (on the oldest one's level) are previewed; false, "none" when none of those times is a recorded
-- walk. done(share, along, total), when given: once the route from the walks' start to their end is worked out with
-- the preview on, `share` the part of it along them (0 to 1; nil: no way there), `along` and `total` its yards; never
-- called once the preview was changed or ended. Previewing() is whether one is on.
function API.PreviewWalk(times, done)
  local R = ns.Router
  if not (R and R.SetPreview) then return false, "none" end
  if times == nil then return R.SetPreview(nil) end
  local want = {}
  for _, t in ipairs(type(times) == "table" and times or { times }) do
    if tonumber(t) then want[tonumber(t)] = true end
  end
  local walks = {}
  for _, t in ipairs(ns.db and type(ns.db.tracks) == "table" and ns.db.tracks or {}) do
    if type(t) == "table" and t.recorded and (t.op == nil or t.op == "add") and want[tonumber(t.time) or false] then
      walks[#walks + 1] = t
    end
  end
  if not walks[1] then return false, "none" end
  return R.SetPreview(walks, type(done) == "function" and done or nil)
end
function API.Previewing()
  return (ns.Router and ns.Router.preview ~= nil) and true or false
end

-- (API 13, asked 2026-10-05 for a companion) A page of your own in AzerothGPS's options window, after the built-in
-- pages, under a section named after your addon (`owner` less "AzerothGPS": "AzerothGPS_Example" -> "Example"); add
-- several (titles "General", "History"...) and they're listed under it in that order. build(ui) runs once when the
-- window is built, or at once if it's built already; the same `owner` and `title` again replaces that page. In pcall: an error stays in your page. `ui`: header(text, note), note(text), check(label, tip, get,
-- set), slider(label, min, max, step, fmt, get, set, enabled) (fmt a format or a function(v) giving the text),
-- button(label, width, onClick), choice(label, { { value, text, tip }, ... }, get, set, enabled) (radio buttons),
-- text(getText) (re-read on every refresh), place(frame, height, indent), page (the page's frame). get() and enabled()
-- are read again whenever the window refreshes. True when added.
function API.AddOptionsPage(owner, title, build)
  return ns.Options and ns.Options.AddPage and ns.Options.AddPage(owner, title, build) or false
end
-- Read every page's get() and enabled() again (your own state changed).
function API.RefreshOptions()
  if ns.Options and ns.Options.Refresh then ns.Options.Refresh() end
end
-- Open the options window at the page titled `title`: `owner`'s page when given (yours: "General" is AzerothGPS's own
-- otherwise), or a built-in one. False when there's no such page.
function API.ShowOptions(title, owner)
  return ns.Options and ns.Options.ShowPage and ns.Options.ShowPage(title, owner) or false
end
-- Things of yours a crash would lose, waiting for the game to save: `count` (0 clears it) and `text`, your line for
-- the map's Save Now button's tooltip ("Example: 6.2 mi of paths"). The button shows while anyone has some.
function API.SetUnsaved(owner, count, text)
  ns.SetUnsavedOwner(owner, count, text)
end
-- Save now, as clicking Save Now: a /reload, never in combat. False when it can't (in combat).
function API.SaveNow() return ns.SaveNow() end

-- (API 14, asked 2026-10-05 for a companion) Looks for the map: each owner sets its own (nil takes it away);
-- the look set last shows, AzerothGPS's own without any. Only how things look, never what the map does.
-- The player's arrow: { texture (path or file id, pointing up), width, height (UI units), coords = { l, r, t, b },
-- color = { r, g, b } }.
function API.SetPlayerArrow(owner, look)
  if GPS() then GPS().SetArrowLook(owner, look) end
end
-- The route: { color = { r, g, b }, rainbow, width (times the usual, 0.5 to 3), glow, dotted }.
function API.SetRouteLook(owner, look)
  if GPS() then GPS().SetRouteLook(owner, look) end
end
-- The window frame: { border = { r, g, b } (a tint over its metal), title = { r, g, b } (the title bar), text = { r,
-- g, b } (the title) }.
function API.SetFrameLook(owner, look)
  if GPS() then GPS().SetFrameLook(owner, look) end
end
-- (API 17) Your own window: the frame look's button colors on its panel and close buttons, now and at every change
-- and each time it's shown. Kept weakly: a window you let go isn't held.
function API.RegisterLookFrame(frame)
  return GPS() and GPS().RegisterLookFrame(frame) or false
end
-- (API 17) The frame look shown: { border, title, text, buttons, close } (each { r, g, b } or nil), a copy; nil: none.
function API.FrameLook()
  return GPS() and GPS().FrameLook() or nil
end
-- (API 19, 2026-11-04) A charm of yours in Options > Window's list (the map window's own looks: Looks.lua), after
-- AzerothGPS's: def = { key, name, tip, file (your textures' path, without the "_<k>x" each ends in), art = { w, h
-- (art pixels), frames (a half turn on its string, left to right then down), cols (frames a row), ax, ay (the point
-- it hangs by, from the cell's top left), tex = { [k] = { width, height } } (k = 1 to 3 screen pixels an art pixel,
-- the frames 1 art pixel apart), or smooth = k (one texture, tex[k]: scaled) }, scale (its size, times its art
-- pixels': 0.25 to 4, 1 unless given) }. Checked as data; false when it isn't
-- well made or its key is one of AzerothGPS's. The player picks it there.
function API.AddCharm(owner, def)
  return ns.Looks and ns.Looks.AddCharm(owner, def) or false
end
-- fn(info) when a stop is reached: { x, y, cont, name, last (the trip's last stop), kind ("stop" or "boss") }, in
-- pcall; fn = nil stops.
function API.OnArrive(owner, fn)
  if owner ~= nil and ns.Nav then ns.Nav.arriveHooks[owner] = type(fn) == "function" and fn or nil end
end

-- (API 15, asked 2026-10-06 for a companion's meter) A slot on the window frame's title bar: `width` UI units at its
-- right, left of the close button, the title bar's height (20), over the frame's border. Returns the slot's frame
-- (`owner`'s: called again, resized; `width` nil lets it go and returns nil). It shows only while the window frame does
-- and the title bar has room for it (a narrow map: not); hook its OnShow / OnHide. While one shows, the title (the
-- place's name) sits left, after the logo, cut short before the slots.
function API.TitleBarSlot(owner, width)
  if not GPS() then return nil end
  return GPS().TitleBarSlot(owner, width)
end

-- (API 18, issue #72: for the developer tools, never shipped; nothing changes unless they call it) The seamless map's
-- transition levels, turned live: the map redraws at once, nothing saved (a /reload is back to the shipped values).
-- Returns a table:
--   List()           { { name, value, default, min, max } } (a boolean knob's min is "boolean"); the close-up's three
--                    only once the stitched map is loaded
--   Get(name)        the value now
--   Set(name, value) true when set (kept in its range; nil: the shipped value), false for an unknown name or a wrong
--                    kind of value
--   Reset()          every knob back to the shipped value
--   Stages()         { artIn = { from, to }, tilesOut = { from, to }, iconsFew, worldZoom } in yards at the reference size
--   Reading()        the blend as last drawn (zoom, ref, notch, art, tiles, artOnly, seamFar, cont, x, y), or nil
--   Report()         all of it as one block of text, to copy and send back
function API.SeamKnobs()
  local G, A = GPS(), ns.Atlas
  if not (G and G.SEAM_KNOBS) then return nil end
  local K = {}
  local function Close(name)
    for _, k in ipairs(A and A.CLOSE_KNOBS or {}) do
      if k[1] == name then return k end
    end
  end
  function K.List()
    local out = {}
    for _, k in ipairs(G.SEAM_KNOBS) do
      out[#out + 1] = { name = k[1], value = G[k[1]], default = G.SEAM_DEFAULTS[k[1]], min = k[2], max = k[3] }
    end
    if A and A.loaded then
      for _, k in ipairs(A.CLOSE_KNOBS) do
        out[#out + 1] = { name = k[1], value = A.CloseKnob(k[1]), default = A.CLOSE_DEFAULTS[k[1]], min = k[2], max = k[3] }
      end
    end
    return out
  end
  function K.Get(name)
    if G.SEAM_DEFAULTS[name] ~= nil then return G[name] end
    if A and Close(name) then return A.CloseKnob(name) end
  end
  function K.Set(name, value)
    if G.SEAM_DEFAULTS[name] ~= nil then return G.SetSeamKnob(name, value) end
    if not (A and Close(name) and A.SetCloseKnob(name, value)) then return false end
    G.Redraw()
    return true
  end
  function K.Reset()
    for _, k in ipairs(K.List()) do K.Set(k.name, nil) end
  end
  function K.Stages()
    return { artIn = { G.SEAM_ART_IN[1], G.SEAM_ART_IN[2] }, tilesOut = { G.SEAM_TILES_OUT[1], G.SEAM_TILES_OUT[2] },
      iconsFew = G.SEAM_ICONS_FEW, worldZoom = G.WorldZoom() / G.ZoomScale() }
  end
  function K.Reading() return G.SeamReading() end
  function K.Report()
    local lines = { "AzerothGPS seamless zoom knobs" }
    local meta = C_AddOns and C_AddOns.GetAddOnMetadata or GetAddOnMetadata
    local version = meta and meta("AzerothGPS", "Version")
    local bv, bb = nil, nil
    if GetBuildInfo then bv, bb = GetBuildInfo() end
    lines[#lines + 1] = "version: " .. tostring(version or "?") .. ", build " .. tostring(bv or "?") .. " " .. tostring(bb or "")
    for _, k in ipairs(K.List()) do
      local v = k.value
      lines[#lines + 1] = string.format("%s = %s%s", k.name, tostring(v), v == k.default and "" or
        " (shipped " .. tostring(k.default) .. ")")
    end
    local s = K.Stages()
    lines[#lines + 1] = string.format("stages (yd at the reference size): art in %.0f-%.0f, tiles out %.0f-%.0f, "
      .. "icons few %.0f, world %.0f", s.artIn[1], s.artIn[2], s.tilesOut[1], s.tilesOut[2], s.iconsFew, s.worldZoom)
    local w, h = G.MapSize()
    lines[#lines + 1] = string.format("map %d x %d (zoom scale %.2f)", math.floor(w + 0.5), math.floor(h + 0.5),
      G.ZoomScale())
    local r = G.SeamReading()
    if r then
      lines[#lines + 1] = string.format("now: %.0f yd (%.0f at the reference size), notch %+.2f, art %.2f, tiles %.2f%s%s",
        r.zoom, r.ref, r.notch, r.art, r.tiles, r.artOnly and ", art alone" or "", r.seamFar and ", world stage" or "")
      local _, zone = G.LocateWorld(r.cont, r.x, r.y)
      lines[#lines + 1] = string.format("at continent %s, %d, %d (%s)", tostring(r.cont), r.x, r.y, tostring(zone or "?"))
    else
      lines[#lines + 1] = "now: the map hasn't been drawn"
    end
    return table.concat(lines, "\n")
  end
  return K
end
