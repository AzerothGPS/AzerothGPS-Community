-- The GPS frame: a square, clipped map around the player drawn from the game's
-- own textures (by FileDataID), heading-up or north-up, adjustable opacity.
--
-- The whole of it is one function (BuildMap, to the end of the file), run once for the map and, when it's needed, once
-- more for a second one of its own: the map on the minimap square while the first is in the game's world map window
-- (asked 2026-11-10: "need to just be 2 duplicate instances of AzerothGPS drawings when opened"; the bottom of the
-- file). The second has everything of its own (its window, layers, view and pools are this function's locals) and
-- only shows: `G.clone`.
local function BuildMap(...)
local _, ns = ...
local L = ns.L or setmetatable({}, { __index = function(_, k) return k end }) -- (the game's language: Locales.lua)
local Format = ns.Format or string.format -- (translations may put the values in another order)
local Geo = ns.Geo

local G = {}
ns.GPS = G
G.clone = ns.isMapClone == true -- (the second map: nothing of the game's own touched, no mouse, no names)

local TILE = Geo.TILE
local MIN_ZOOM, MAX_ZOOM = 60, 2500
local BORDER = 3
local CHROME_TITLE = 22 -- title bar height of the game-style window frame (while unlocked)
local MAP_BUTTON = 32 -- the round map menu button (bottom-left)
local MENU_IDLE = 20 -- seconds: the map menu (and its toggles column) closes by itself
local SEARCH_IDLE = 20 -- ... and the search panel
local LASSO_COLOR = { 1, 0.82, 0 } -- a farming area being drawn
local DRAW_COLOR, ERASE_COLOR = { 0.3, 1, 0.3 }, { 1, 0.2, 0.2 } -- a road being drawn / erased
local WALL_COLOR, UNWALL_COLOR = { 0.55, 0.02, 0.02 }, { 0.6, 0.6, 0.6 } -- a wall being drawn (blood red) / erased
local CHROME_PORTRAIT_INSET = 46 -- the frame's portrait covers this much of the map's top-left

-- Texture:SetRotation turns the image counter-clockwise for positive angles.
-- If the in-game test shows tiles turning the wrong way, flip with /agps debug rotsign.
G.rotSign = 1

---------------------------------------------------------------------------
-- Layout (pure; unit-tested outside the game)
---------------------------------------------------------------------------

-- A north-aligned world rectangle [minX, maxX] x [minY, maxY] showing texture coords
-- [u0, u1] x [v0, v1] (u runs east, v runs south), cropped to the view box around
-- (cx, cy) with half-size R yards. Returns the quad for it, or nil when out of view.
-- Cropping keeps every drawn region small: the game stops drawing very large regions,
-- which blanked the map when zoomed right in.
function G.CropQuad(fid, minX, maxX, minY, maxY, u0, u1, v0, v1, cx, cy, R, rot, s, sublayer)
  local X0, X1 = math.max(minX, cx - R), math.min(maxX, cx + R)
  local Y0, Y1 = math.max(minY, cy - R), math.min(maxY, cy + R)
  if X0 >= X1 or Y0 >= Y1 then return nil end
  local du, dv = (u1 - u0) / (maxY - minY), (v1 - v0) / (maxX - minX)
  local cu0, cu1 = u0 + (maxY - Y1) * du, u0 + (maxY - Y0) * du
  local cv0, cv1 = v0 + (maxX - X1) * dv, v0 + (maxX - X0) * dv
  local dx, dy = Geo.ScreenOffset(cx, cy, (X0 + X1) / 2, (Y0 + Y1) / 2)
  dx, dy = Geo.Rotate(dx * s, dy * s, rot)
  return { fid, dx, dy, (Y1 - Y0) * s + 1, (X1 - X0) * s + 1, rot, cu0, cu1, cv0, cv1, sublayer }
end

-- Returns a list of quads { fid, x, y, w, h, rot, l, r, t, b, sublayer } in UI units,
-- relative to the frame center (+y up), for the view centered on world (px, py).
-- `rot` is the map rotation (radians, CCW); l/r/t/b are texture coords.
-- Whether `cont` has terrain (a minimap tile) at world (x, y): not the open sea, which the
-- terrain view would show black.
function G.HasTerrain(cont, x, y)
  local tiles = ns.MinimapTiles and ns.MinimapTiles[cont]
  if not tiles then return false end
  local tx, ty = Geo.WorldToTile(x, y)
  return tiles[math.floor(tx) * 64 + math.floor(ty)] ~= nil
end

-- `edge` (the seamless map's edge blend, issue #62; north up only): each tile gets an opaque mask under it (a tile
-- still loading never shows the art through it), and each known-empty cell beside a tile a feather (G.EdgeFeathers).
-- Along the coast (issue #73, G.CoastAt): a tile all sea is left out like an empty cell, and a coastal tile and the
-- mask under it are drawn through its coastline mask (`q.mask`: the file and its whole tile's rectangle on the map)
function G.LayoutMinimap(px, py, cont, rot, zoom, half, edge)
  local tiles = ns.MinimapTiles and ns.MinimapTiles[cont]
  local quads = {}
  if not tiles then return quads end
  local s = half / zoom -- UI units per yard
  local R = zoom * 1.42 -- covers the view's corners at any rotation
  local ptx, pty = Geo.WorldToTile(px, py)
  local span = R / TILE + 1
  for tx = math.floor(ptx - span), math.floor(ptx + span) do
    for ty = math.floor(pty - span), math.floor(pty + span) do
      local fid = tiles[tx * 64 + ty]
      local maxX, maxY = (32 - ty) * TILE, (32 - tx) * TILE -- north-west corner
      local coast = edge and fid and G.CoastAt(cont, tx, ty)
      if fid and coast ~= 0 then
        local q = G.CropQuad(fid, maxX - TILE, maxX, maxY - TILE, maxY, 0, 1, 0, 1, px, py, R, rot, s, 0)
        if q then
          quads[#quads + 1] = q
          if edge then
            local m = G.CropQuad(0, maxX - TILE, maxX, maxY - TILE, maxY, 0, 1, 0, 1, px, py, R, rot, s, G.EDGE_MASK_SUBLAYER)
            m.color = G.EDGE_MASK_COLOR
            quads[#quads + 1] = m
            if coast then
              local dx, dy = Geo.ScreenOffset(px, py, maxX - TILE / 2, maxY - TILE / 2)
              q.mask = { coast, dx * s, dy * s, TILE * s + 1, TILE * s + 1 }
              m.mask = q.mask
            end
          end
        end
      elseif edge then
        G.EdgeFeathers(quads, tiles, tx, ty, maxX, maxY, px, py, R, s, cont)
      end
    end
  end
  return quads
end

-- The edge blend (issue #62): in the terrain view, where there's no terrain tile at all (the open sea, past the
-- baked terrain's edge) the seamless map's art shows instead of black. Only known-empty cells (no tile in
-- ns.MinimapTiles): the art is drawn whole under the map, and every laid tile has an opaque mask under it, so a tile
-- still loading shows the dark ground as it always did, never the art. The terrain is never faded: the soft edge is
-- in the empty cell, a feather of the tile's own last pixels stretched over EDGE_FEATHER_YD and fading out over the
-- art. In world yards, so it looks the same at every zoom. North up only (the art can't turn: a heading-up view keeps
-- the black), and only with the seamless map on (G.Seamless: off, or a held game's style, as before).
G.EDGE_FEATHER_YD = 60 -- yards from a tile's edge into the empty cell over which its edge fades out over the art
G.EDGE_SMEAR = 2 / 256 -- the share of the tile at its edge stretched over the feather (its last 2 px, about 4 yd)
G.EDGE_MASK_COLOR = { 0.05, 0.05, 0.05 } -- the masks under the tiles: the map's own dark ground (its backdrop)
G.EDGE_MASK_SUBLAYER = -1 -- (under the tiles, 0)

-- The coastline (issue #73): the edge blend followed the tiles' squares, and a coastal tile's own sea stayed dark.
-- Data/Coast.lua (app/azerothgps/coast.py, from the shipped terrain grid's water) lists each continent's tiles by the
-- sea: 0 all sea (left out, the art there), else coastal (drawn through its mask, Media\Coast\<cont>_<tx>_<ty>:
-- white, its alpha 1 on land fading over ns.CoastFeatherYd out into the sea, the same yards as EDGE_FEATHER_YD; the
-- number the box of its pixels not all land, G.CoastBox); tiles all land aren't listed. Masks are our own (no game
-- art: made from the grid's numbers).
G.COAST_MEDIA = "Interface\\AddOns\\AzerothGPS\\Media\\Coast\\"
G.COAST_PX = 64 -- a mask's side
-- tile (tx, ty) of `cont` by the sea: 0 all sea, its mask's file when coastal, nil all land (or no coast data)
function G.CoastAt(cont, tx, ty)
  local c = ns.Coast and ns.Coast[cont]
  local v = c and c[tx * 64 + ty]
  if v and v > 0 then return G.COAST_MEDIA .. cont .. "_" .. tx .. "_" .. ty end
  return v
end

-- a coastal tile's (Data/Coast.lua's number `v`) pixels not all land, in tile units from its north-west corner:
-- u0, v0, u1, v1 (u east, v south; coast.py's code())
function G.CoastBox(v)
  local n, P = v - 1, G.COAST_PX
  local x0 = n % P
  n = (n - x0) / P
  local y0 = n % P
  n = (n - y0) / P
  local x1 = n % P
  local y1 = (n - x1) / P
  return x0 / P, y0 / P, (x1 + 1) / P, (y1 + 1) / P
end

-- Whether the view (north up, `zoom` yards to its long side's edge round px, py) has a cell with no terrain tile
-- in it, or a tile's sea (G.CoastAt; a coastal tile by its box, G.CoastBox): the edge blend's one test, a few
-- hundred lookups at the terrain view's furthest zoom
function G.EdgeInView(cont, px, py, zoom)
  local tiles = ns.MinimapTiles and ns.MinimapTiles[cont]
  if not tiles then return false end
  local coast = ns.Coast and ns.Coast[cont]
  local x0, y0 = Geo.WorldToTile(px + zoom, py + zoom) -- (north-west: x is north, y is west)
  local x1, y1 = Geo.WorldToTile(px - zoom, py - zoom)
  local u0, u1, v0, v1 = math.min(x0, x1), math.max(x0, x1), math.min(y0, y1), math.max(y0, y1)
  for tx = math.floor(u0), math.floor(u1) do
    for ty = math.floor(v0), math.floor(v1) do
      local k = tx * 64 + ty
      local c = coast and coast[k]
      if not tiles[k] or c == 0 then return true end
      if c then
        local a0, b0, a1, b1 = G.CoastBox(c)
        if tx + a0 < u1 and tx + a1 > u0 and ty + b0 < v1 and ty + b1 > v0 then return true end
      end
    end
  end
  return false
end

-- The feathers into empty cell (tx, ty) (its north-west corner maxX, maxY) from each tile beside it, added to
-- `quads`: the tile's band at that edge stretched over EDGE_FEATHER_YD, `grad` its alpha (1 at the tile, 0 inward)
-- along the screen's axis as cropped (north up: Texture:SetGradient's axes are the screen's). Only from a tile all
-- land (G.CoastAt nil): a coastal one already fades out into its sea before its edge (its mask), and its edge's own
-- dark sea pixels smeared out would be the square edge again.
function G.EdgeFeathers(quads, tiles, tx, ty, maxX, maxY, px, py, R, s, cont)
  local F, e = G.EDGE_FEATHER_YD, G.EDGE_SMEAR
  local minX, minY = maxX - TILE, maxY - TILE
  local cx0, cx1, cy0, cy1 = px - R, px + R, py - R, py + R
  local function Add(fid, x0, x1, y0, y1, u0, u1, v0, v1, side)
    local q = G.CropQuad(fid, x0, x1, y0, y1, u0, u1, v0, v1, px, py, R, 0, s, 0)
    if not q then return end
    local X0, X1 = math.max(x0, cx0), math.min(x1, cx1)
    local Y0, Y1 = math.max(y0, cy0), math.min(y1, cy1)
    if side == "W" then -- (the tile west of it: +y; the screen's left is west, Y1)
      q.grad = { "HORIZONTAL", (Y1 - y0) / F, (Y0 - y0) / F }
    elseif side == "E" then
      q.grad = { "HORIZONTAL", (y1 - Y1) / F, (y1 - Y0) / F }
    elseif side == "N" then -- (VERTICAL: the bottom's alpha, then the top's)
      q.grad = { "VERTICAL", (X0 - x0) / F, (X1 - x0) / F }
    else
      q.grad = { "VERTICAL", (x1 - X0) / F, (x1 - X1) / F }
    end
    quads[#quads + 1] = q
  end
  local coast = ns.Coast and ns.Coast[cont]
  local function Land(k)
    if not (coast and coast[k]) then return tiles[k] end
  end
  local w = Land((tx - 1) * 64 + ty)
  if w then Add(w, minX, maxX, maxY - F, maxY, 1 - e, 1, 0, 1, "W") end
  local east = Land((tx + 1) * 64 + ty)
  if east then Add(east, minX, maxX, minY, minY + F, 0, e, 0, 1, "E") end
  local n = Land(tx * 64 + ty - 1)
  if n then Add(n, maxX - F, maxX, minY, maxY, 0, 1, 1 - e, 1, "N") end
  local south = Land(tx * 64 + ty + 1)
  if south then Add(south, minX, minX + F, minY, maxY, 0, 1, 0, e, "S") end
end

-- a feather's alpha along the screen (`grad`: orientation, the left's or bottom's alpha, the right's or top's)
function G.SetAlphaGradient(t, grad)
  local a0, a1 = math.max(0, math.min(1, grad[2])), math.max(0, math.min(1, grad[3]))
  if CreateColor and t.SetGradient then
    t:SetGradient(grad[1], CreateColor(1, 1, 1, a0), CreateColor(1, 1, 1, a1))
  elseif t.SetGradientAlpha then
    t:SetGradientAlpha(grad[1], 1, 1, 1, a0, 1, 1, 1, a1)
  end
end

-- Zone map art (fully explored) for uiMap `mapID`, placed in world space.
-- Explored parts of uiMap `id`'s art, as overlay tiles like Maps.lua's ({ fileID, x, y, w,
-- h, texW, texH }), from what the game says the player has explored
-- (C_MapExplorationInfo, as the world map uses). Cached; refreshed every few seconds.
local explored = {} -- [id] = { t, tiles }
G.EXPLORED_TTL = 10
-- the cached list dropped (the player explored somewhere)
function G.ForgetExplored(id) explored[id] = nil end
function G.ExploredOverlays(id)
  local c = explored[id]
  local now = GetTime()
  if c and now - c.t < G.EXPLORED_TTL then return c.tiles end
  local tiles = {}
  local api = C_MapExplorationInfo and C_MapExplorationInfo.GetExploredMapTextures
  for _, e in ipairs(api and api(id) or {}) do
    if not e.isShownByMouseOver and e.fileDataIDs then
      local wide = math.ceil(e.textureWidth / 256)
      local tall = math.ceil(e.textureHeight / 256)
      for j = 1, tall do
        for k = 1, wide do
          local fid = e.fileDataIDs[(j - 1) * wide + k]
          if fid then
            -- the last column/row is narrower; its file is the next power of two
            local w = k < wide and 256 or (e.textureWidth - 256 * (wide - 1))
            local h = j < tall and 256 or (e.textureHeight - 256 * (tall - 1))
            local texW, texH = 16, 16
            while texW < w do texW = texW * 2 end
            while texH < h do texH = texH * 2 end
            tiles[#tiles + 1] = { fid, e.offsetX + 256 * (k - 1), e.offsetY + 256 * (j - 1), w, h, texW, texH }
          end
        end
      end
    end
  end
  -- (reported 2026-11-17, "When the spoiler-free map is enabled, display errors occur. It flickers, pops out": the
  -- game's list asked again every G.EXPLORED_TTL could come back in another order, or empty for a moment, and the
  -- map's textures were handed other files, or the explored parts dropped for 10 s. In one order, the list kept
  -- while it's the same, and an empty answer never wipes what was explored: exploring is never undone)
  table.sort(tiles, function(a, b)
    if a[3] ~= b[3] then return a[3] < b[3] end
    if a[2] ~= b[2] then return a[2] < b[2] end
    return a[1] < b[1]
  end)
  if c and (#tiles == 0 or G.SameTiles(c.tiles, tiles)) then
    c.t = now
    return c.tiles
  end
  explored[id] = { t = now, tiles = tiles }
  return tiles
end
function G.SameTiles(a, b)
  if #a ~= #b then return false end
  for i = 1, #a do
    for k = 1, 7 do
      if a[i][k] ~= b[i][k] then return false end
    end
  end
  return true
end

-- The map styles (issue #75; the Map Style buttons, /agps style, the `style` setting): "seamless" (the default: the
-- terrain, and the wheel on out to the whole world on the stitched art, G.Seamless), "minimap" (Terrain: the terrain
-- alone, as before the seamless map), "zone" and "nospoiler" (below). "unrevealed" is a held style only (API.HoldMap).
G.STYLES = { seamless = true, minimap = true, zone = true, nospoiler = true }
-- Map styles that draw world map art: "zone" (fully explored) and "nospoiler" (only what
-- the character has explored).
function G.IsMapStyle(style) return style == "zone" or style == "nospoiler" or style == "unrevealed" end
-- The style the map draws: one a holder of the map set (a game on it: API.HoldMap's opts.style), else the
-- player's own (the setting is never changed by a holder).
G.HOLD_STYLES = { minimap = true, zone = true, nospoiler = true, unrevealed = true }
function G.HeldStyle()
  for _, h in pairs(G.holders or {}) do
    if h.style then return h.style end
  end
  return nil
end
-- The minimap square is always the seamless map, whatever the style picked for the map (asked 2026-11-10: "changing
-- the map mode ... shouldn't change the minimap if enabled, should always be using seamless view"): the style
-- picked is the opened map's. Only with the stitched map's art loaded (Atlas.Wanted loads it for the square too).
function G.SquareStyle()
  local A = ns.Atlas
  if G.mmState and G.MinimapMode and G.MinimapMode() and G.ArtSpan() > 0 and A and A.loaded == true and not A.artFailed then
    return "seamless"
  end
  return nil
end
function G.Style() return G.HeldStyle() or G.SquareStyle() or (ns.settings and ns.settings.gps.style) end
-- LayoutZone's overlays for a style: "zone" every area, "nospoiler" the ones this character explored
-- (true), "unrevealed" none (the base art only, the same for every character).
function G.SpoilerMode(style)
  if style == "unrevealed" then return "none" end
  return style == "nospoiler"
end

-- `noSpoiler`: only the explored overlays (what this character has discovered); "none": no overlays at
-- all (G.SpoilerMode). `layer`: drawn this many sublayers up (an inset over another map's art).
function G.LayoutZone(px, py, mapID, rot, zoom, half, bounds, noSpoiler, layer)
  local quads = {}
  local m = ns.Maps and ns.Maps[mapID]
  while m and not m.tiles do
    mapID = m.parent
    m = ns.Maps[mapID]
  end
  local b = bounds or (m and m.bounds) -- the world map has no bounds of its own: passed in
  if not m or not b then return quads end
  layer = layer or 0
  G.LayoutArtTiles(quads, m.tiles, b, m.artW, m.artH, px, py, rot, zoom, half, layer)
  if noSpoiler == "none" then
    -- (the base art only)
  elseif noSpoiler then
    G.LayoutArtTiles(quads, G.ExploredOverlays(mapID), b, m.artW, m.artH, px, py, rot, zoom, half, layer + 1)
  else
    G.LayoutArtTiles(quads, m.overlays, b, m.artW, m.artH, px, py, rot, zoom, half, layer + 1) -- (explored areas over it)
  end
  return quads
end

-- A world map's art tiles ({ fileID, x, y, w, h, texW, texH } in art pixels, Maps.lua's) over world bounds `b`
-- ({ minX, minY, maxX, maxY }; the art artW x artH pixels across them), as quads added to `quads` for the view
-- centered on (px, py): a zone's map, and a dungeon's (G.LayoutDungeonMap).
function G.LayoutArtTiles(quads, list, b, artW, artH, px, py, rot, zoom, half, sublayer)
  if not list then return quads end
  local s = half / zoom
  local R = zoom * 1.42
  local maxX, maxY = b[3], b[4]
  local ydx = (maxX - b[1]) / artH -- world X yards per art pixel (north-south)
  local ydy = (maxY - b[2]) / artW -- world Y yards per art pixel (east-west)
  for _, q in ipairs(list) do
    local fid, ax, ay, w, h, texW, texH = q[1], q[2], q[3], q[4], q[5], q[6], q[7]
    local qMaxX, qMaxY = maxX - ay * ydx, maxY - ax * ydy
    local c = G.CropQuad(fid, qMaxX - h * ydx, qMaxX, qMaxY - w * ydy, qMaxY, 0, w / texW, 0, h / texH,
      px, py, R, rot, s, sublayer)
    if c then quads[#quads + 1] = c end
  end
  return quads
end

-- A dungeon's world map (Data/DungeonMaps.lua, issue #4): another WoW version's map of it where its layout is
-- WoW Forever's, floor by floor (dungeonmaps.py checks each; the textures are in this client: drawn by file id).
-- The terrain view draws the dungeon's own art (its models' minimap art, or its terrain's) over it, the world
-- map's styles it alone; a dungeon without one is drawn as before.
G.DUNGEON_MAP_SUBLAYER = -7 -- (under the models' art, 1 and up, and the terrain's tiles, 0; over the floors' fill, -8)
-- The floor of dungeon level `inst`'s world map for a view centered on (cx, cy), or nil (none for it). `band`: the
-- floor shown ({ lo, hi } world height, G.InstanceFloors): the map whose rooms' heights overlap it most. Then by
-- where the view is: a map whose rooms are round its middle (the smallest: a wing's own, the Scarlet Monastery's),
-- else the nearest; then the first.
function G.DungeonMapFloor(inst, band, cx, cy)
  local dm = ns.DungeonMaps and ns.DungeonMaps[inst]
  return G.PickMapFloor(dm and dm.floors, band, cx, cy)
end
-- Of world map floors `floors` (DungeonMaps' or InteriorMaps' rows), the one for floor band `band` and the view's
-- middle (cx, cy), as G.DungeonMapFloor says; nil when none has its art.
function G.PickMapFloor(floors, band, cx, cy)
  if not floors or #floors == 0 then return nil end
  local best, bz, bd, ba
  for _, f in ipairs(floors) do
    if f.tiles and #f.tiles > 0 and f.bounds then -- (a floor without its art: none, its dungeon's own art drawn)
      local r = f.rooms or f.bounds
      local z = 0
      if band and f.z then z = math.max(0, math.min(band[2], f.z[2]) - math.max(band[1], f.z[1])) end
      local dx = math.max(r[1] - cx, 0, cx - r[3])
      local dy = math.max(r[2] - cy, 0, cy - r[4])
      local d, a = dx * dx + dy * dy, (r[3] - r[1]) * (r[4] - r[2])
      if not best or z > bz or (z == bz and (d < bd or (d == bd and a < ba))) then
        best, bz, bd, ba = f, z, d, a
      end
    end
  end
  return best
end

-- Quads for a dungeon's world map floor `f` (G.DungeonMapFloor) in the view centered on (cx, cy).
function G.LayoutDungeonMap(cx, cy, f, rot, zoom, half, quads)
  return G.LayoutArtTiles(quads or {}, f.tiles, f.bounds, f.artW, f.artH, cx, cy, rot, zoom, half, G.DUNGEON_MAP_SUBLAYER)
end

-- A dungeon's map, its layers bottom to top: its world map's floor `dmap` (or nil), then, in the terrain view
-- (not `mapStyle`) or with no world map, its own art: its models' minimap art (one floor, `band`, or all), over
-- (WoW Forever's own dungeons on their terrain, `terrain`) its terrain's minimap tiles. Quads (none: no art, its floors' outline instead).
-- `ground` (the interiors' edge blend, issue #85): the dark ground under its rooms (G.InteriorGround), its terrain's
-- tiles with the terrain's edge blend (G.LayoutMinimap's `edge`).
-- `terrain` ({ cont, dx, dy }, G.InstanceTerrainSpot): over the continent's terrain round its way in, as a cave's map
-- (asked 2026-11-15): no world map's parchment under it, its art's thin black outline, the terrain's tiles laid where
-- it lies on the continent (the view's middle moved by dx, dy).
function G.LayoutDungeon(cx, cy, inst, rot, zoom, half, band, dmap, mapStyle, ground, terrain)
  if terrain then
    local art = G.LayoutInstanceArt(cx, cy, inst, rot, zoom, half, band)
    if #art > 0 then G.InteriorOutline(art) end
    return G.LayoutInteriorTerrain(art, cx + terrain[2], cy + terrain[3], terrain[1], rot, zoom, half)
  end
  local quads = dmap and G.LayoutDungeonMap(cx, cy, dmap, rot, zoom, half) or {}
  if mapStyle and #quads > 0 then return quads end -- (none in view: its own art, as without one)
  local art = G.LayoutInstanceArt(cx, cy, inst, rot, zoom, half, band)
  local lvl = ns.CityLevels and ns.CityLevels[inst]
  if lvl and lvl.terrain then -- (its terrain's minimap tiles: its map only, or under its models' art, the Ruins of
    -- Lordaeron's streets round its few buildings with interior maps)
    for _, q in ipairs(G.LayoutMinimap(cx, cy, lvl.base, rot, zoom, half, ground)) do quads[#quads + 1] = q end
  elseif ground and #art > 0 then
    G.InteriorGround(art, cx, cy, G.ArtList(inst), band, rot, zoom, half)
  end
  for _, q in ipairs(art) do quads[#quads + 1] = q end
  return quads
end

-- An interior's world map (Data/InteriorMaps.lua, issue #41): a cave's, mine's or manor's map from another WoW version
-- where its rooms are laid out as WoW Forever's (interiormaps.py checks each floor; the textures are in this client:
-- drawn by file id), as a dungeon's: under its models' minimap art in the terrain view, alone in the world map's
-- styles. An interior without one is drawn as before.
-- The floors of continent `cont`'s interior maps one of whose models is a row of `list` (ns.Interiors rows: placed
-- within G.CAVE_ART_YD of one of a floor's `places`), looked up once per row.
G.interiorMapsOf = {} -- [ns.Interiors row] = { floor, ... } (on G: the main chunk is at Lua 5.1's 200 locals)
function G.InteriorMapFloors(cont, list)
  local out, seen = {}, {}
  for _, p in ipairs(list or {}) do
    local got = G.interiorMapsOf[p]
    if not got then
      got = {}
      local r = G.CAVE_ART_YD
      for _, f in ipairs(ns.InteriorMaps and ns.InteriorMaps[cont] or {}) do
        local pl = f.places or {}
        for i = 1, #pl - 1, 2 do
          if math.abs(pl[i] - p[2]) <= r and math.abs(pl[i + 1] - p[3]) <= r then
            got[#got + 1] = f
            break
          end
        end
      end
      G.interiorMapsOf[p] = got
    end
    for _, f in ipairs(got) do
      if not seen[f] then
        seen[f] = true
        out[#out + 1] = f
      end
    end
  end
  return out
end
-- The interior map floor for models `list` on `cont` (G.InteriorMapFloors), floor band `band` ({ lo, hi } world height,
-- or nil) and the view's middle (cx, cy), as G.DungeonMapFloor picks; nil when none.
function G.InteriorMapFor(cont, list, band, cx, cy)
  return G.PickMapFloor(G.InteriorMapFloors(cont, list), band, cx, cy)
end
-- A world map floor `f` (or nil) with art over it, `layoutArt()`'s quads: the map alone when `only` (a map style) and
-- some of it is in view, as G.LayoutDungeon.
function G.LayoutUnderMap(f, only, cx, cy, rot, zoom, half, layoutArt)
  local quads = f and G.LayoutDungeonMap(cx, cy, f, rot, zoom, half) or {}
  if only and #quads > 0 then return quads end
  for _, q in ipairs(layoutArt()) do quads[#quads + 1] = q end
  return quads
end

-- Maps not on the world map's art (Zephras Isle, an island in the sky) shown on it as an inset:
-- their own map in a rectangle of the world map (fractions of it, left to right and top to
-- bottom), framed and named; a click opens it.
G.WORLD_INSETS = { { map = 2521, u0 = 0.415, v0 = 0.05, u1 = 0.545, v1 = 0.18 } }
-- An inset's rectangle in world yards { minX, minY, maxX, maxY }, on a world map drawn over `b`.
function G.InsetBounds(it, b)
  local W, H = b[4] - b[2], b[3] - b[1]
  return { b[3] - it.v1 * H, b[4] - it.u1 * W, b[3] - it.v0 * H, b[4] - it.u0 * W }
end
-- The inset at world map fractions (u, v), or nil.
function G.InsetAt(u, v)
  for _, it in ipairs(G.WORLD_INSETS) do
    if ns.Maps and ns.Maps[it.map] and u >= it.u0 and u <= it.u1 and v >= it.v0 and v <= it.v1 then return it end
  end
end

-- Per-continent edge bounding boxes for culling: { minX, maxX, minY, maxY, edge }.
local roadIndex = {}

-- The roads as routing sees them (shipped plus recorded; rebuilt when recordings change).
local function RoadIndex(cont)
  local edges, g
  if ns.Router then
    edges, g = ns.Router.Edges(cont)
  else
    local roads = ns.Roads and ns.Roads[cont]
    edges, g = roads and roads.e, roads
  end
  local c = roadIndex[cont]
  if c and c.g == g then return c.idx end
  local idx = {}
  local breathe = ns.Router and ns.Router.Breathe
  if edges then
    for ei, e in ipairs(edges) do
      if breathe then breathe(ei, 300) end -- (in the background work: a slice per frame)
      local minX, maxX, minY, maxY = math.huge, -math.huge, math.huge, -math.huge
      for i = 5, #e, 2 do
        local x, y = e[i], e[i + 1]
        if x < minX then minX = x end
        if x > maxX then maxX = x end
        if y < minY then minY = y end
        if y > maxY then maxY = y end
      end
      idx[#idx + 1] = { minX, maxX, minY, maxY, e, ei }
    end
  end
  roadIndex[cont] = { g = g, idx = idx }
  return idx
end

-- Built ahead in the background (Router.WarmUp), not in the first frame that shows the roads.
function G.WarmRoadIndex(cont) RoadIndex(cont) end

G.MAX_SEGMENTS = 1500

-- The terrain's impassable edges near a view (mountains, cliffs: Passability.At == 2), as
-- world segments { x1, y1, x2, y2, ... } (flat): the borders between blocked and open
-- samples on a grid of `step` yards (the terrain's cell, coarser zoomed out). Worked out
-- for a block around the view and kept while the view stays in it.
G.EDGE_SAMPLES = 48 -- samples across the view's half width, at least
G.EDGE_SAMPLES_INSTANCE = 128 -- ... in a dungeon's map (its outline is the map: its halls are narrow)
G.EDGE_MS = 2 -- ms of a frame spent working a new outline out (the old one stays meanwhile)
local edgeCache, edgeJob = {}, nil
function G.ClearEdges() edgeCache, edgeJob = {}, nil end -- (walls or wall erasers changed)
local function EdgeWork(cont, g, P, step, x0, x1, y0, y1)
  local nx, ny = math.floor((x1 - x0) / step), math.floor((y1 - y0) / step)
  local blocked = {}
  for i = 0, nx - 1 do
    local row = {}
    local x = x0 + (i + 0.5) * step
    for j = 0, ny - 1 do row[j] = P.At(cont, x, y0 + (j + 0.5) * step) == 2 end
    blocked[i] = row
    coroutine.yield()
  end
  local segs = {}
  local function line(ax, ay, bx, by)
    segs[#segs + 1], segs[#segs + 2], segs[#segs + 3], segs[#segs + 4] = ax, ay, bx, by
  end
  -- the open ground as runs along each sample row: { x, y from, y to, ... } (flat), and the
  -- rows' width (a dungeon's map fills its floors with them)
  local fill = {}
  for i = 0, nx - 1 do
    local row, x, run = blocked[i], x0 + (i + 0.5) * step, nil
    for j = 0, ny do
      local open = j < ny and not row[j]
      if open and not run then run = j
      elseif not open and run then
        fill[#fill + 1], fill[#fill + 2], fill[#fill + 3] = x, y0 + run * step, y0 + j * step
        run = nil
      end
    end
  end
  segs.fill, segs.step = fill, step
  -- borders across x (between rows i and i + 1), merged along y; then across y
  for i = 0, nx - 2 do
    local a, b = blocked[i], blocked[i + 1]
    local x = x0 + (i + 1) * step
    local run
    for j = 0, ny do
      local edge = j < ny and a[j] ~= b[j]
      if edge and not run then run = j
      elseif not edge and run then
        line(x, y0 + run * step, x, y0 + j * step)
        run = nil
      end
    end
  end
  for j = 0, ny - 2 do
    local y = y0 + (j + 1) * step
    local run
    for i = 0, nx do
      local edge = i < nx and blocked[i][j] ~= blocked[i][j + 1]
      if edge and not run then run = i
      elseif not edge and run then
        line(x0 + run * step, y, x0 + i * step, y)
        run = nil
      end
    end
  end
  return segs
end

function G.BlockEdges(cont, cx, cy, zoom)
  local P = ns.Passability
  local g = ns.Terrain and ns.Terrain[cont]
  if not (P and P.At and g) then return {} end
  local step = g.cell
  local lvl = ns.CityLevels and ns.CityLevels[cont]
  local samples = lvl and lvl.instance and G.EDGE_SAMPLES_INSTANCE or G.EDGE_SAMPLES
  while step < zoom / samples do step = step * 2 end
  local chunk = step * 32
  local reach = zoom * 1.4
  local x0, x1 = math.floor((cx - reach) / chunk) * chunk, math.ceil((cx + reach) / chunk) * chunk
  local y0, y1 = math.floor((cy - reach) / chunk) * chunk, math.ceil((cy + reach) / chunk) * chunk
  local key = string.format("%s:%g:%g:%g:%g:%g", tostring(cont), step, x0, x1, y0, y1)
  if edgeCache.key == key then return edgeCache.segs end
  -- (a new block: worked out a little each frame by G.PumpEdges, the last one shown meanwhile)
  if not edgeJob or edgeJob.key ~= key then
    edgeJob = { key = key, cont = cont, co = coroutine.create(EdgeWork) }
    edgeJob.args = { cont, g, P, step, x0, x1, y0, y1 }
  end
  if not debugprofilestop then G.PumpEdges() end -- (no frames to spread it over: all now)
  if edgeCache.key == key then return edgeCache.segs end
  if edgeCache.cont == cont then return edgeCache.segs or {} end
  return {}
end

-- An error in the map's work: kept (ns.db.errors, the last 20, read with `agps probes`-style
-- tools after a /reload) and said once per kind in chat.
local errorSaid = {}
function G.LogError(what, err)
  G.lastError = tostring(err)
  if ns.db then
    ns.db.errors = ns.db.errors or {}
    local list = ns.db.errors
    list[#list + 1] = { what = what, err = G.lastError, time = time and time() or 0,
      stack = debugstack and debugstack(2, 8, 0) or nil }
    while #list > 20 do table.remove(list, 1) end
  end
  if ns.Debug then ns.Debug.Log("error", { what = what, err = G.lastError }) end
  if not errorSaid[what] then
    errorSaid[what] = true
    ns.Print(Format(L["GPS error (%s): %s"], what, G.lastError))
  end
end

-- Every frame: a little more of the outline being worked out (EDGE_MS); the map redrawn
-- once it's done.
function G.PumpEdges()
  if not edgeJob then return end
  local clock = debugprofilestop
  local t0 = clock and clock()
  repeat
    local ok, res = coroutine.resume(edgeJob.co, (unpack or table.unpack)(edgeJob.args))
    if not ok then
      edgeJob = nil
      return
    end
    if coroutine.status(edgeJob.co) == "dead" then
      edgeCache.key, edgeCache.segs, edgeCache.cont = edgeJob.key, res, edgeJob.cont
      edgeJob = nil
      if G.Redraw then G.Redraw() end
      return
    end
  until clock and clock() - t0 >= G.EDGE_MS
end

-- Walls near the view (Passability.WallLines, and with `edges` the terrain's impassable
-- borders: G.BlockEdges): { x1, y1, x2, y2 } in UI units.
function G.LayoutWalls(px, py, cont, rot, zoom, half, edges)
  local segs = {}
  local P = ns.Passability
  if not (P and P.WallLines) then return segs end
  local s = half / zoom
  local reach = zoom * 1.5
  -- the walls first (drawn and shipped: never the ones left out), then the terrain's edges up to
  -- MAX_SEGMENTS in all (the tools on: another floor's walls faint)
  local tf = G.ToolFloor(cont)
  for _, w in ipairs(P.WallLines(cont)) do
    local lx, ly
    local faint = tf and w.fl and P.SameWallFloor and not P.SameWallFloor(cont, w[1], w[2], w.fl, tf) or nil
    for i = 1, #w - 1, 2 do
      local wx, wy = w[i], w[i + 1]
      local dx, dy = Geo.ScreenOffset(px, py, wx, wy)
      dx, dy = Geo.Rotate(dx * s, dy * s, rot)
      if lx and (math.abs(wx - px) <= reach and math.abs(wy - py) <= reach or math.abs(dx) <= half * 2) then
        segs[#segs + 1] = { lx, ly, dx, dy, faint = faint, own = w.own }
      end
      lx, ly = dx, dy
    end
  end
  if edges then
    local e = G.BlockEdges(cont, px, py, zoom)
    for i = 1, #e - 3, 4 do
      if #segs >= G.MAX_SEGMENTS then break end
      local ax, ay, bx, by = e[i], e[i + 1], e[i + 2], e[i + 3]
      if math.abs(ax - px) <= reach or math.abs(bx - px) <= reach then
        if math.abs(ay - py) <= reach or math.abs(by - py) <= reach then
          local dx1, dy1 = Geo.ScreenOffset(px, py, ax, ay)
          dx1, dy1 = Geo.Rotate(dx1 * s, dy1 * s, rot)
          local dx2, dy2 = Geo.ScreenOffset(px, py, bx, by)
          dx2, dy2 = Geo.Rotate(dx2 * s, dy2 * s, rot)
          segs[#segs + 1] = { dx1, dy1, dx2, dy2, edge = true }
        end
      end
    end
  end
  return segs
end

-- Road segments near the player: list of { x1, y1, x2, y2, source } in UI units
-- relative to the frame center. source: 0 road (the player's drawn ones too), 1 bridged
-- gap, 3 a drop off a ledge. At most MAX_SEGMENTS: the player's drawn roads first, only the
-- parts on screen, laid on a grid of ROAD_STEP_UI cells (a line within one cell is too small
-- to see; one between two cells is drawn once, whichever road it's from: zoomed out, a road of
-- many short pieces still draws whole; a road all within one cell, one short line there, once
-- a cell, so none goes missing). When a view still has more (zoomed out over a dense
-- network, a capital's streets), the grid is made coarser (twice, and again) rather than whole
-- roads left out. The grid is kept for the frames after (scaled with the zoom).
local RECORDED = 9 -- (Router.SOURCE_RECORDED)
G.ROAD_STEP_UI = 2
-- The player's drawn roads not in the data yet, straight from their strokes, as index entries
-- like RoadIndex's (drawn while the road graph is rebuilt after an edit).
function G.DrawnTrackIndex(cont)
  local out, shipped = {}, ns.RoadTracksIn or {}
  for _, t in ipairs(ns.db and ns.db.tracks or {}) do
    local pts = t.pts
    if t.continent == cont and (t.op == nil or t.op == "add") and pts and #pts >= 4 and not shipped[t.time or -1] then
      local e = { 0, 0, 0, RECORDED, time = t.time }
      local x0, x1, y0, y1 = math.huge, -math.huge, math.huge, -math.huge
      for i = 1, #pts - 1, 2 do
        e[#e + 1], e[#e + 2] = pts[i], pts[i + 1]
        x0, x1, y0, y1 = math.min(x0, pts[i]), math.max(x1, pts[i]), math.min(y0, pts[i + 1]), math.max(y1, pts[i + 1])
      end
      out[#out + 1] = { x0, x1, y0, y1, e }
    end
  end
  return out
end
-- The player's erasures not in the data yet: { { pts, area, reach, x0, x1, y0, y1, time }, ... }
-- (while the road graph is rebuilt after one, the roads under it go at once, not after).
function G.PendingErases(cont)
  local out, shipped = {}, ns.RoadTracksIn or {}
  local reach = ns.Router and ns.Router.TRACK_REMOVE_YD or 8
  for _, t in ipairs(ns.db and ns.db.tracks or {}) do
    local pts = t.pts
    if t.continent == cont and t.op == "remove" and pts and #pts >= 4 and not shipped[t.time or -1] then
      local r = t.area and 0 or reach
      local x0, x1, y0, y1 = math.huge, -math.huge, math.huge, -math.huge
      for i = 1, #pts - 1, 2 do
        x0, x1, y0, y1 = math.min(x0, pts[i]), math.max(x1, pts[i]), math.min(y0, pts[i + 1]), math.max(y1, pts[i + 1])
      end
      out[#out + 1] = { pts = pts, area = t.area, reach = r, x0 = x0 - r, x1 = x1 + r, y0 = y0 - r, y1 = y1 + r, time = t.time,
        floor = (t.z or t.down ~= nil) and { z = t.z, down = t.down } or nil }
    end
  end
  return out
end
-- Whether (x, y) is under one of those erasures (made after `since`, when given; `applies(er)`: the
-- erasure is on the road's floor).
function G.UnderErase(list, x, y, since, applies)
  for _, er in ipairs(list) do
    if (not since or (er.time or 0) > since) and x >= er.x0 and x <= er.x1 and y >= er.y0 and y <= er.y1
        and (not applies or applies(er)) then
      local pts = er.pts
      if er.area then
        if ns.Router and ns.Router.InPolygon and ns.Router.InPolygon(pts, x, y) then return true end
      else
        local r2 = er.reach * er.reach
        for k = 1, #pts - 3, 2 do
          local ax, ay, bx, by = pts[k], pts[k + 1], pts[k + 2], pts[k + 3]
          local vx, vy = bx - ax, by - ay
          local L2 = vx * vx + vy * vy
          local t = L2 > 0 and math.max(0, math.min(1, ((x - ax) * vx + (y - ay) * vy) / L2)) or 0
          if (ax + vx * t - x) ^ 2 + (ay + vy * t - y) ^ 2 <= r2 then return true end
        end
      end
    end
  end
  return false
end
local roadCoarse = {} -- [cont] = { zoom, k }: the spacing that fitted last
function G.LayoutRoads(px, py, cont, rot, zoom, half)
  local segs = {}
  -- (the road graph not built yet, after a /reload or a road or wall edit: built in the
  -- background; meanwhile the roads as they were, and the player's drawn ones as drawn)
  local R = ns.Router
  local stale
  if R and R.GraphReady and R.WARM and not R.SYNC_WALKS and GetTime then -- (no game clock, the tests: at once)
    local ready = R.GraphReady(cont)
    if not ready then R.WarmUp(cont, px, py) end
    if not ready or (R.Warming and R.Warming()) then -- (or its index for drawing still being built)
      stale = roadIndex[cont]
      if not stale then return segs end
    end
  end
  -- (the road or wall tools on, with edits made: the network is rebuilt when they're turned off;
  -- the roads as they were meanwhile, the edits drawn over them)
  if not stale and ns.Record and ns.Record.pending then stale = roadIndex[cont] end
  local s = half / zoom
  local reach = zoom * 1.5
  local edge = half * 1.45 -- (the view's corners, turned heading-up)
  local idx = stale and stale.idx or RoadIndex(cont)
  local lists = { idx }
  local erases
  if stale then
    lists[2] = G.DrawnTrackIndex(cont)
    erases = G.PendingErases(cont)
    if #erases == 0 then erases = nil end
  end
  -- (the tools on where floors lie over each other: the other floors' roads faint; an erasure not
  -- drawn into the network yet takes out its own floor's roads only)
  local fg = (stale or roadIndex[cont] or {}).g
  local tf = fg and G.ToolFloor(cont)
  local ei -- (the road being laid: its number in fg)
  local function applies(er)
    return not (er.floor and ei and G.OtherFloor(fg, ei, cont, er.floor))
  end
  local function Lay(k)
    local out, seen = {}, {}
    local cell = G.ROAD_STEP_UI * k
    for round = 1, 2 do -- the player's drawn roads first, then the rest
      for _, list in ipairs(lists) do for _, b in ipairs(list) do
        if b[2] > px - reach and b[1] < px + reach and b[4] > py - reach and b[3] < py + reach then
          local e = b[5]
          -- (drawn roads are truth: roads like any, before they're in the data too)
          local drawn = e[4] == 2 or e[4] == RECORDED
          if (round == 1) == drawn then
            -- (the player's own, not in the data yet: green)
            local src = e[4] == RECORDED and G.OWN_ROAD_COLOR or drawn and 0 or e[4]
            ei = list == idx and b[6] or nil
            local alpha = tf and ei and G.OtherFloor(fg, ei, cont, tf) and G.OTHER_FLOOR_ALPHA or nil
            local lx, ly, lc -- last point kept (screen) and its grid cell
            local fx, fy, any -- the first point, and whether any line was kept
            for i = 5, #e, 2 do
              if erases and G.UnderErase(erases, e[i], e[i + 1], e.time, fg and applies or nil) then
                lx, ly, lc = nil, nil, nil -- (erased just now: gone at once, not after the rebuild)
              else
              local dx, dy = Geo.ScreenOffset(px, py, e[i], e[i + 1])
              dx, dy = Geo.Rotate(dx * s, dy * s, rot)
              local c = (math.floor(dx / cell) + 2048) * 4096 + math.floor(dy / cell) + 2048
              if c ~= lc then
                -- (not a piece wholly off one side of the view, nor one drawn already)
                if lx and not ((lx < -edge and dx < -edge) or (lx > edge and dx > edge)
                    or (ly < -edge and dy < -edge) or (ly > edge and dy > edge)) then
                  local key = lc < c and lc * 16777216 + c or c * 16777216 + lc
                  any = true
                  if not seen[key] then
                    seen[key] = true
                    out[#out + 1] = { lx, ly, dx, dy, src, alpha }
                    if #out >= G.MAX_SEGMENTS then return out, true end
                  end
                end
                if not lx then fx, fy = dx, dy end
                lx, ly, lc = dx, dy, c
              end
              if i >= #e - 1 and not any and lx and math.abs(lx) <= edge and math.abs(ly) <= edge then
                -- (all of it within one cell: one short line in that cell, once)
                local key = lc * 16777216 + lc
                if not seen[key] then
                  seen[key] = true
                  out[#out + 1] = { fx, fy, dx, dy, src, alpha }
                  if #out >= G.MAX_SEGMENTS then return out, true end
                end
              end
              end
            end
          end
        end
      end end
    end
    return out, false
  end
  -- (the grid that fitted last, scaled with the zoom: coarser zoomed out, finer zoomed back in)
  local c = roadCoarse[cont]
  local k = 1
  if c then
    local want = c.k * zoom / c.zoom
    while k * 2 <= want do k = k * 2 end
  end
  local full
  segs, full = Lay(k)
  while full and k < 16 do
    k = k * 2
    segs, full = Lay(k)
  end
  roadCoarse[cont] = { zoom = zoom, k = k }
  return segs
end

-- Interiors (WMO minimaps; see app/azerothgps/interiors.py for the conventions)

local Z_SLACK = 3 -- yards above/below a group's height range still counted as "in" it
-- City models whose art is never the inside map: Stormwind's (every piece of it, streets and squares
-- too, has art and a district's name, so on its streets its art took over zoomed in; and indoors it
-- looks worse than the terrain). There the terrain view stays the terrain.
G.NO_INSIDE_MAP = {} -- (Stormwind's was here till 2026-11-14: an open city since, G.OPEN_CITY_MODELS)
-- Cities in the open built as one model: their inside map only where the game says indoors (the Cleft of Shadow, a
-- building in it); out in their streets the terrain (asked 2026-11-14 with a screenshot of Orgrimmar's model art and
-- its black gaps: "for cities that are outside don't do this, doesn't look as good"). Named, not worked out: Darnassus's
-- model is flagged indoors throughout, as Ironforge's is. Ironforge and Undercity keep their map everywhere; Thunder
-- Bluff is many small models (its tents keep theirs).
G.OPEN_CITY_MODELS = { [7964229] = true, [113359] = true, [7962574] = true } -- (Orgrimmar's, Darnassus's, Stormwind's:
-- Data/Interiors.lua. Stormwind's since 2026-11-14, asked: "I can't view inside buildings for stormwind")
-- Indoors there, the building alone, as any building's (Tarren Mill's inn): the smallest room round the player (not the
-- one the zone text names: the valley's), and only the rooms within OPEN_CITY_ROOM_YD of it, not every room at its
-- height (nearly all of Orgrimmar's are flagged indoors: the whole city came over the terrain, asked 2026-11-14).
G.OPEN_CITY_ROOM_YD = 8
function G.RoomGroupShown(place, room, g)
  if g == room or not (place and G.OPEN_CITY_MODELS[place[1]]) then return true end
  local m = G.OPEN_CITY_ROOM_YD
  return g[1] >= room[1] - m and g[4] <= room[4] + m and g[2] >= room[2] - m and g[5] <= room[5] + m
end
G.INTERIOR_MAX_ZOOM = 500 -- zoomed out further than this, show the outside view instead (not while indoors)
-- In a city whose inside map shows (Ironforge's, Undercity's), the city's map at any zoom, and the wheel
-- zooms out no further than this (zoomed out further on the way in: zoomed in to it); right-click for
-- the land around (asked, 2026-09-30: zooming out in Ironforge turned to the terrain around it).
G.CITY_MAX_ZOOM = G.INTERIOR_MAX_ZOOM
G.CITY_MAX_ZOOM_BASE = G.CITY_MAX_ZOOM
-- In Ironforge (the game's map for the player), twice as far out before its map gives way to the land (asked
-- 2026-11-16: "when in ironforge, make the zoom out distance required to not show ironforge map twice the distance").
-- G.CITY_MAX_ZOOM is set from this at each G.Update.
G.CITY_MAX_ZOOM_TIMES = { [1455] = 2 }
function G.CityMaxZoomFor(mapID)
  return G.CITY_MAX_ZOOM_BASE * (G.CITY_MAX_ZOOM_TIMES[mapID or 0] or 1)
end

-- Height range of the rooms in `w` named `name` (cached): the floor the minimap names.
local function NamedBand(w, name)
  w.bands = w.bands or {}
  local b = w.bands[name]
  if b == nil then
    b = false
    for _, g in ipairs(w.groups) do
      if g.n == name then
        if not b then b = { g[3], g[6] } else b[1], b[2] = math.min(b[1], g[3]), math.max(b[2], g[6]) end
      end
    end
    w.bands[name] = b
  end
  return b or nil
end

-- The heights (world: the game's) the rooms named `zoneText` of model `wmo` near world (px, py) on `cont` span: lo, hi;
-- nil when none is (Nav.TrackCityZ's first guess at the player's floor down in a city: the minimap's zone text).
function G.ZoneTextBand(cont, px, py, zoneText, wmo)
  if not (zoneText and zoneText ~= "" and wmo) then return nil end
  for _, p in ipairs(ns.Interiors and ns.Interiors[cont] or {}) do
    if p[1] == wmo and px >= p[6] - 5 and px <= p[8] + 5 and py >= p[7] - 5 and py <= p[9] + 5 then
      local b = ns.WMOs[wmo] and NamedBand(ns.WMOs[wmo], zoneText)
      if b then return b[1] + p[4], b[2] + p[4] end
    end
  end
  return nil
end

-- Squared distance from (x, y) to a room's rectangle (0 inside).
local function RectDist2(g, x, y)
  local dx = math.max(g[1] - x, 0, x - g[4])
  local dy = math.max(g[2] - y, 0, y - g[5])
  return dx * dx + dy * dy
end

-- The building the player at world (px, py) is inside, if any: returns place, wmo and
-- the room ("group") that sets the floor to draw.
-- The client reports height as 0 and Forever says "outdoors" all through Undercity, so
-- without height the floor comes from the minimap zone text: the rooms named like it
-- (e.g. every "Trade Quarter" room) give a height band, and any indoor room containing
-- the player within that band counts, named or not (corridors are often unnamed). With
-- no containing room, the nearest named room is used. Most ordinary buildings' rooms
-- have no name, so standing outside next to one does not trigger this.
-- `cityZ`, `cityWmo`: down in an underground city, the floor's height under the player (its
-- model's own) for that model: its room found by height, like with a known z.
function G.FindInterior(px, py, pz, cont, zoneText, indoors, cityZ, cityWmo, mapWmo)
  local list = ns.Interiors and ns.Interiors[cont]
  if not list then return nil end
  local haveZ = pz and pz ~= 0
  local hasName = zoneText and zoneText ~= ""
  local best, bestWmo, bestGroup, bestScore
  for _, p in ipairs(list) do
    if px >= p[6] - 5 and px <= p[8] + 5 and py >= p[7] - 5 and py <= p[9] + 5 and not G.NO_INSIDE_MAP[p[1]]
        and (indoors or cityWmo == p[1] or not G.OPEN_CITY_MODELS[p[1]]) then -- (an open city's streets: the terrain)
      local w = ns.WMOs[p[1]]
      local dx, dy = px - p[2], py - p[3]
      local c, s = math.cos(p[5]), math.sin(p[5])
      local lx, ly, lz = dx * c + dy * s, -dx * s + dy * c, (pz or 0) - p[4]
      local haveZ = haveZ
      if cityZ and p[1] == cityWmo then haveZ, lz = true, cityZ + 1 end
      local band = hasName and NamedBand(w, zoneText)
      local nearest, nearestD
      for _, g in ipairs(w.groups) do
        local named = hasName and g.n == zoneText
        local inside = lx >= g[1] and lx <= g[4] and ly >= g[2] and ly <= g[5]
        local ok
        if haveZ then
          -- (a model's outdoor pieces, a city's streets and squares (Stormwind's), are the outside:
          -- only its indoor rooms, or where the game says indoors; down in an underground city,
          -- any of its rooms)
          ok = inside and lz >= g[3] - Z_SLACK and lz <= g[6] + Z_SLACK
            and (g["in"] or indoors or (cityZ ~= nil and p[1] == cityWmo))
        else
          local onFloor = band and g[6] >= band[1] - Z_SLACK and g[3] <= band[2] + Z_SLACK
          -- (`mapWmo`: the model of the city the game's map says the player is in, Ironforge's: any of its indoor
          -- rooms. The rooms' names are the client's English ones and the zone text is the player's language, so on
          -- a German client none was named and Forever says outdoors there: the mountain's terrain was drawn, #426)
          ok = inside and g["in"] and (named or indoors or onFloor or mapWmo == p[1])
        end
        if ok then
          local score = (g[4] - g[1]) * (g[5] - g[2]) * math.max(1, g[6] - g[3])
          if named and not G.OPEN_CITY_MODELS[p[1]] then score = score * 1e-6 end -- prefer the named room, then the smallest
          -- (in an open city, the biggest building-sized room round the spot: its shell, whose box takes in the rest of
          -- the building (G.RoomGroupShown); the smallest was now and then its roof's frame or a beam, and that alone
          -- was drawn, a video 2026-11-14 in the Drag. Rooms bigger than a building, the Cleft's, last)
          if G.OPEN_CITY_MODELS[p[1]] then
            local side = math.max(g[4] - g[1], g[5] - g[2])
            score = side <= G.ZOOM_ROOM_MAX_YD and -side or 1e12 + score
          end
          if not bestScore or score < bestScore then best, bestWmo, bestGroup, bestScore = p, w, g, score end
        elseif named and not haveZ then
          local d = RectDist2(g, lx, ly)
          if not nearestD or d < nearestD then nearest, nearestD = g, d end
        end
      end
      if not best and nearest and nearestD < 60 * 60 then
        best, bestWmo, bestGroup, bestScore = p, w, nearest, math.huge
      end
    end
  end
  return best, bestWmo, bestGroup
end

-- Zoomed in over a building or a cave (asked 2026-11-14: "a slider ... how far zooming in on a building or cave it
-- transitions to the interior view of that building"): at the zoom Options > Map's slider sets (`interiorZoomYd`,
-- yards from the map's middle to its edge; 0: off, only when the player is inside), the building or cave under the
-- view's middle shows its inside map as it would with the player in it (the terrain round it in OpenMap). Not a city:
-- Stormwind's model, an underground city's; in a city
-- in the open (Orgrimmar, Darnassus) a room of at most ZOOM_ROOM_MAX_YD (a building in it, not a valley).
G.INTERIOR_ZOOM_YD = 150 -- the default (Core.lua's DEFAULTS too; "150yd is fine up to 500yd", 2026-11-14)
G.INTERIOR_ZOOM_RANGE = { 0, 500 }
-- A left click over the building shown holds its inside map that long (`interiorHoldSec`, Options > Map; asked
-- 2026-11-14: "allow left click to hold the interior map view overlay for 30s (adjustable setting)"), the mouse
-- anywhere meanwhile; right-click lets it go.
G.INTERIOR_HOLD_SEC = 30
G.INTERIOR_HOLD_RANGE = { 0, 120 }
function G.InteriorHoldSec()
  local v = tonumber(ns.settings and ns.settings.gps and ns.settings.gps.interiorHoldSec)
  if v == nil then v = G.INTERIOR_HOLD_SEC end
  return math.max(0, v)
end
-- the left click's hold (G.heldInside: the hovered building then, till when); false when nothing is hovered
-- A held inside map let go before its seconds are up once the view's middle is LEAVE_INSIDE_PAN_YD from it, or it's
-- zoomed out past the inside maps' distance, as an opened cave's or city's map (asked 2026-11-15: "same rule should
-- apply like viewing cave, if player pans too far away or zooms out this gets closed before the 30s")
function G.DropHeldIfAway(cx, cy, zoom, cont)
  local h = G.heldInside
  if not h then return end
  -- (from where the view was at the click, h.cx, h.cy: a building held far off the view's middle stays till then)
  local away = h.hit.cont ~= cont or not G.InteriorZoomOK(zoom)
    or (h.cx and (cx - h.cx) ^ 2 + (cy - h.cy) ^ 2 > G.LEAVE_INSIDE_PAN_YD ^ 2)
  if away then G.heldInside = nil end
end
function G.HoldInside()
  local secs = G.InteriorHoldSec()
  if not (G.hoverInside and secs > 0) then return false end
  local vx, vy = G.ViewState()
  G.heldInside = { hit = G.hoverInside, key = G.hoverInsideKey, untilT = GetTime() + secs, cx = vx, cy = vy }
  G.hoverDismissKey = nil
  G.Redraw()
  return true
end
G.ZOOM_ROOM_MAX_YD = 60
-- A city inside a mountain, one model (Ironforge's): its NPCs never dotted (the whole city's map). Hovered like any
-- model since 2026-11-15 ("allow ironforge to show from zoom in"). By model, not by size: models CITY_WMO_YD and bigger
-- were never hovered, and with them the big caves and caverns (Blackrock Mountain's, 1,053 yd; Feralas's, Tanaris's).
G.MOUNTAIN_CITY_MODELS = { [7801267] = true }
function G.InteriorZoomYd()
  local v = tonumber(ns.settings and ns.settings.gps and ns.settings.gps.interiorZoomYd)
  if v == nil then v = G.INTERIOR_ZOOM_YD end
  return math.max(0, v)
end
-- whether zoom `zoom` (yards to the map's edge) is in close enough for the hovered inside maps: the setting's yards at
-- the reference size, as the OpenMap stages' (G.ZoomScale: a bigger map shows more at a zoom, and its least zoom grows
-- with it; the game's world map window, a big one, never came in to 150 yd: asked 2026-11-14, "mouse over viewing for
-- both gps map and in game map ... whatever changes are done on 1 map the same features should be available on either")
function G.InteriorZoomOK(zoom)
  local scale = G.ZoomScale and G.ZoomScale() or 1
  return zoom ~= nil and zoom / math.max(scale, 1e-6) <= G.InteriorZoomYd()
end
-- the building or cave under (x, y) on `cont` (the mouse's spot on the map, G.BuildingHover): place, wmo, room (its
-- lowest floor's smallest room there: the player's height isn't known), or nil
-- the models the zoom may open: { [model] = true } of those it may not (an underground city's)
function G.ZoomSkips()
  local skip = {}
  for _, l in pairs(ns.CityLevels or {}) do
    if l.wmo then skip[l.wmo] = true end
  end
  return skip
end
function G.ZoomedInterior(x, y, cont) return G.InteriorUnder(x, y, cont) end
-- The player standing in a building of a city in the open (Stormwind's, Orgrimmar's, Darnassus's: one model with the
-- streets, G.OPEN_CITY_MODELS): its inside map as the mouse over it shows it (G.InteriorUnder). WoW Forever says
-- outdoors in those buildings' halls, as in Ironforge's, and G.FindInterior takes an open city's rooms only indoors
-- (its streets are the terrain): inside Stormwind's Trade District buildings the terrain showed, the hover their map
-- (reported 2026-11-15).
function G.OpenCityBuildingAt(x, y, cont)
  local p, w, g = G.InteriorUnder(x, y, cont)
  if p and G.OPEN_CITY_MODELS[p[1]] then return p, w, g end
  return nil
end
function G.InteriorUnder(x, y, cont)
  local list = ns.Interiors and ns.Interiors[cont]
  if not list then return nil end
  local cityWmo = G.ZoomSkips()
  local best, bestW, bestG, bestZ, bestA
  for _, p in ipairs(list) do
    if x >= p[6] and x <= p[8] and y >= p[7] and y <= p[9] and not G.NO_INSIDE_MAP[p[1]] and not cityWmo[p[1]] then
      local w = ns.WMOs and ns.WMOs[p[1]]
      local open = G.OPEN_CITY_MODELS[p[1]]
      if w then
        local dx, dy = x - p[2], y - p[3]
        local c, sn = math.cos(p[5]), math.sin(p[5])
        local lx, ly = dx * c + dy * sn, -dx * sn + dy * c
        for _, g in ipairs(w.groups) do
          if g["in"] and g.blocks and #g.blocks > 0 and lx >= g[1] and lx <= g[4] and ly >= g[2] and ly <= g[5]
              and (not open or math.max(g[4] - g[1], g[5] - g[2]) <= G.ZOOM_ROOM_MAX_YD) then
            -- (an open city's: the biggest building-sized room there, its shell, as G.FindInterior)
            local a = (g[4] - g[1]) * (g[5] - g[2])
            if open then a = -a end
            if not best or g[3] < bestZ - Z_SLACK or (math.abs(g[3] - bestZ) <= Z_SLACK and a < bestA) then
              best, bestW, bestG, bestZ, bestA = p, w, g, g[3], a
            end
          end
        end
      end
    end
  end
  return best, bestW, bestG
end

-- The NPCs in a building's or cave's inside map (asked 2026-11-14: "for every npc in the building I want a small dot to
-- show where that NPC is, hover for the name. If that npc is a profession trainer, vendor, repair, etc show a small icon
-- next to the NPC dot"; "only special NPCs, no common name mob enemies"): the shipped ones (Data/Npcs.lua: friendly or
-- neutral and interactive) offering something past gossip (NPC_DOT_SERVICES), the player's side's or neutral, whose
-- spawn is in one of the rooms the map draws (G.LayoutInterior's: in its box, about its heights). Each { x, y, z, name,
-- title, icon (Pins.NpcIcon's; nil for one with none of its own) }. Worked out once a building and room.
G.NPC_DOT_SERVICES = "qvftbhipdmasr" -- (npcs.py's letters but "g", gossip alone)
G.npcDotCache = {}
function G.InteriorNpcs(place, wmo, room, cont)
  local key = table.concat({ place[1], place[2], place[3], tostring(room), cont or 0 }, ":")
  local hit = G.npcDotCache[key]
  if hit then return hit end
  local out = {}
  local Lay = ns.Layers
  if Lay and Lay.ShippedNpcs and wmo and room then
    local groups = {}
    local zlo, zhi = room[3] - Z_SLACK, room[6] + Z_SLACK
    for _, g in ipairs(wmo.groups) do
      if g == room or (g["in"] and g[6] >= zlo and g[3] <= zhi and G.RoomGroupShown(place, room, g)) then
        groups[#groups + 1] = g
      end
    end
    local base = Geo.Base(cont)
    local c, sn = math.cos(place[5]), math.sin(place[5])
    local pattern = "[" .. G.NPC_DOT_SERVICES .. "]"
    -- (every side's: zoomed into the other faction's buildings, their NPCs show too; asked 2026-11-14, "they should
    -- still be able to zoom into alliance buildings to see the NPCs there")
    for _, n in ipairs((Lay.ShippedNpcs())) do
      local special = n.svc and n.svc:find(pattern) ~= nil
      if special then
        local sp = n.spawns
        for i = 1, #sp - 3, 4 do
          local x, y, z = sp[i + 1], sp[i + 2], sp[i + 3]
          if x >= place[6] and x <= place[8] and y >= place[7] and y <= place[9] and Geo.Base(sp[i]) == base then
            local dx, dy = x - place[2], y - place[3]
            local lx, ly, lz = dx * c + dy * sn, -dx * sn + dy * c, z - place[4]
            for _, g in ipairs(groups) do
              if lx >= g[1] and lx <= g[4] and ly >= g[2] and ly <= g[5] and lz >= g[3] - Z_SLACK and lz <= g[6] + Z_SLACK then
                local icon = ns.Pins and ns.Pins.NpcIcon and ns.Pins.NpcIcon({ shipped = n }) or nil
                local I = ns.Pins and ns.Pins.NPC_ICONS
                -- (no icon of its own, or a quest giver's: a dot; asked 2026-11-14, "don't use quest indicators")
                if I and (icon == I.npc or icon == I.quest) then icon = nil end
                out[#out + 1] = { x = x, y = y, z = z, name = ns.NpcName(n.id, n.name), title = ns.NpcTitle(n.id, n.title),
                  icon = icon, id = n.id, level = sp[i] }
                break
              end
            end
          end
        end
      end
    end
  end
  G.npcDotCache[key] = out
  return out
end
-- the NPC dots of the inside map shown (POI kind 16) added to `pois`; none on a whole city's map, Undercity's or
-- Ironforge's (asked 2026-11-14, "too cluttered": only on a building's own inside map, as hovering one shows)
function G.WholeCityPlace(place, cont)
  if ns.CityLevels and ns.CityLevels[cont] then return true end
  if not place or G.OPEN_CITY_MODELS[place[1]] then return false end
  if G.ZoomSkips()[place[1]] then return true end
  return G.MOUNTAIN_CITY_MODELS[place[1]] == true
end
function G.AddInteriorNpcs(pois, place, wmo, room, cont, cx, cy, rot, s, half)
  if G.WholeCityPlace(place, cont) then return end
  for _, n in ipairs(G.InteriorNpcs(place, wmo, room, cont)) do
    local dx, dy = Geo.ScreenOffset(cx, cy, n.x, n.y)
    dx, dy = Geo.Rotate(dx * s, dy * s, rot)
    if math.abs(dx) <= half and math.abs(dy) <= half then
      pois[#pois + 1] = { 16, dx, dy, n.name, n.x, n.y, z = n.z, level = cont, npcIcon = n.icon, note = n.title,
        npc = G.NpcClickInfo(n.id, n.name, n.title, n.level or cont, n.x, n.y, n.z) } -- (another addon's Shift-click)
    end
  end
end

-- Step-by-step report of the interior lookup, for /agps debug interior.
function G.DebugInterior()
  local px, py, cont, pz = Geo.PlayerWorld()
  local zt = GetMinimapZoneText and GetMinimapZoneText() or "?"
  local out = { string.format("pos %.1f, %.1f z=%s cont=%s indoors=%s zoneText=%q setting=%s",
    px or 0, py or 0, tostring(pz), tostring(cont), tostring(IsIndoors()), zt, tostring(ns.settings.gps.interiors)) }
  local list = ns.Interiors and ns.Interiors[cont]
  local function try(f, ...) local ok, v = pcall(f, ...); return ok and tostring(v) or "n/a" end
  local mapID = C_Map.GetBestMapForUnit("player")
  out[#out + 1] = string.format("outdoors=%s mounted=%s zone=%q subzone=%q real=%q map=%s(%s)",
    try(IsOutdoors), try(IsMounted), try(GetZoneText), try(GetSubZoneText), try(GetRealZoneText),
    tostring(mapID), mapID and try(function() return C_Map.GetMapInfo(mapID).name end) or "?")
  out[#out + 1] = "interior data: " .. (list and (#list .. " buildings on this continent") or "none")
  for _, p in ipairs(list or {}) do
    if px >= p[6] - 5 and px <= p[8] + 5 and py >= p[7] - 5 and py <= p[9] + 5 then
      local dx, dy = px - p[2], py - p[3]
      local c, sn = math.cos(p[5]), math.sin(p[5])
      local lx, ly = dx * c + dy * sn, -dx * sn + dy * c
      local w = ns.WMOs[p[1]]
      local inXY, named = 0, 0
      for _, g in ipairs(w.groups) do
        if lx >= g[1] and lx <= g[4] and ly >= g[2] and ly <= g[5] then
          inXY = inXY + 1
          if g.n == zt then named = named + 1 end
        end
      end
      out[#out + 1] = string.format("  wmo %d: local %.1f, %.1f; %d rooms contain it, %d named %q",
        p[1], lx, ly, inXY, named, zt)
    end
  end
  local place, _, room = G.FindInterior(px, py, pz, cont, zt, IsIndoors(), nil, nil, G.PlayerCityWmo())
  out[#out + 1] = "result: " .. (place and (room.n .. " in wmo " .. place[1]) or "nil")
  return out
end

-- Quads for the floor of room `room` (all indoor rooms overlapping its height range),
-- centered on world (cx, cy).
-- District names inside a building (its rooms' area names, what the zone text shows:
-- "Trade Quarter", "Magic Quarter"), on the level of the room you're in: { { x, y, name } }
-- in world coordinates. Rooms of a name are grouped by nearness; each group gets a label
-- in its middle (by area) when it's big enough, and each name is shown once, on its
-- biggest group (Undercity's canals are many bits). Cached per building and level.
G.LABEL_GROUP_YD = 70 -- rooms of one name closer than this: one label
G.LABEL_MIN_AREA = 1500 -- square yards a label's rooms must cover
local interiorLabels = {}
-- The capitals' districts' names (Data/Capitals.lua's ns.CityLabels: Trade District, The Drag, Hunter
-- Rise) as place labels when zoomed in on the city, as Undercity's come with its inside map.
G.CITY_LABEL_ZOOM = 700 -- yards from the middle to the edge, at most
function G.CityLabelPois(pois, viewCont, cx, cy, rot, s, half, zoom)
  local list = zoom <= G.CITY_LABEL_ZOOM and ns.CityLabels and ns.CityLabels[Geo.Base(viewCont)]
  for _, l in ipairs(list or {}) do
    local dx, dy = Geo.ScreenOffset(cx, cy, l[1], l[2])
    dx, dy = Geo.Rotate(dx * s, dy * s, rot)
    if math.abs(dx) <= half and math.abs(dy) <= half then
      pois[#pois + 1] = { 3, dx, dy, ns.PlaceName(l[3]), l[1], l[2] }
    end
  end
  return pois
end

function G.InteriorLabels(place, wmo, room)
  local key = tostring(place) .. ":" .. tostring(room and room[3] or 0)
  if interiorLabels[key] then return interiorLabels[key] end
  local zlo, zhi = room[3] - Z_SLACK, room[6] + Z_SLACK
  local clusters = {}
  for _, g in ipairs(wmo.groups) do
    if g.n and g.n ~= "" and (g == room or (g["in"] and g[6] >= zlo and g[3] <= zhi)) then
      local x, y = (g[1] + g[4]) / 2, (g[2] + g[5]) / 2
      local area = (g[4] - g[1]) * (g[5] - g[2])
      local into
      for _, c in ipairs(clusters) do
        if c.name == g.n and (c.x / c.area - x) ^ 2 + (c.y / c.area - y) ^ 2 <= G.LABEL_GROUP_YD ^ 2 then into = c break end
      end
      if into then
        into.x, into.y, into.area = into.x + x * area, into.y + y * area, into.area + area
      else
        clusters[#clusters + 1] = { name = g.n, x = x * area, y = y * area, area = area }
      end
    end
  end
  -- one label per name: on its biggest group of rooms
  local biggest = {}
  for _, cl in ipairs(clusters) do
    if cl.area >= G.LABEL_MIN_AREA and (not biggest[cl.name] or cl.area > biggest[cl.name].area) then biggest[cl.name] = cl end
  end
  local c, sn = math.cos(place[5]), math.sin(place[5])
  local out = {}
  for name, cl in pairs(biggest) do
    local lx, ly = cl.x / cl.area, cl.y / cl.area
    out[#out + 1] = { place[2] + lx * c - ly * sn, place[3] + lx * sn + ly * c, name }
  end
  table.sort(out, function(a, b) return a[3] < b[3] end)
  interiorLabels[key] = out
  return out
end

G.BLOCK_PAST_PX = 4 -- (G.LayoutInterior: a block may start this far past its room's box, in its 2 px a yard)
function G.LayoutInterior(cx, cy, place, wmo, room, rot, zoom, half, anyGroup, quads)
  quads = quads or {}
  local s = half / zoom
  local theta = place[5]
  local c, sn = math.cos(theta), math.sin(theta)
  local texRot = theta + math.pi / 2 + rot -- image "right" is the building's local +x
  local reach = zoom * 1.5 + 128
  local groups = {}
  local zlo, zhi = room[3] - Z_SLACK, room[6] + Z_SLACK
  for _, g in ipairs(wmo.groups) do
    if g == room or ((anyGroup or g["in"]) and g[6] >= zlo and g[3] <= zhi and G.RoomGroupShown(place, room, g)) then
      groups[#groups + 1] = g
    end
  end
  table.sort(groups, function(a, b) return a[6] < b[6] end) -- higher floors drawn last
  for layer, g in ipairs(groups) do
    -- (a block starting past its room's own box isn't its art: Orgrimmar's bank, a 39 yd room, listed five more
    -- blocks out to 250 yd, the Valley of Strength's art drawn over the land askew; asked 2026-11-14)
    local gw, gh = (g[4] - g[1]) * 2 + G.BLOCK_PAST_PX, (g[5] - g[2]) * 2 + G.BLOCK_PAST_PX
    for _, b in ipairs(g.blocks) do
      local fid, bx, by, w, h = b[1], b[2], b[3], b[4], b[5]
      local lx = g[1] + bx * 128 + w / 4 -- block center, local yards (2 px per yard)
      local ly = g[2] + by * 128 + h / 4
      local wx = place[2] + lx * c - ly * sn
      local wy = place[3] + lx * sn + ly * c
      local dx, dy = Geo.ScreenOffset(cx, cy, wx, wy)
      if math.abs(dx) < reach and math.abs(dy) < reach and bx * 128 < gw and by * 128 < gh then
        dx, dy = Geo.Rotate(dx * s, dy * s, rot)
        quads[#quads + 1] = { fid, dx, dy, w / 2 * s + 0.5, h / 2 * s + 0.5, texRot, 0, 1, 0, 1, math.min(layer, 7) }
      end
    end
  end
  return quads
end

-- A dungeon's map from the game's own minimap art of its models (Data/Instances.lua:
-- ns.Interiors[its map id]): the player's floor while they're in it and the view is on them
-- (`band`: one floor, { lo, hi } world height, G.InstanceFloors), else every floor, the higher
-- ones over the lower. Quads (none: no art for it, the floors' outline instead).
local ALL_FLOORS = { 0, 0, -1e9, 0, 0, 1e9 }
G.ALL_FLOORS = ALL_FLOORS
-- A city whose map is one model (Ironforge's in its mountain, an underground city's: Undercity's) with the view's middle
-- over it, the player not in it: that model, every floor (asked 2026-11-15: "should the whole city map also come up for
-- a city you're not in as soon as you zoom in over it, without hovering? yes"). Zoomed in to CITY_MAX_ZOOM (at the
-- reference size), as the player's own city's map shows.
function G.CityUnderView(x, y, cont, zoom)
  if not (x and zoom and ns.Interiors and ns.Interiors[cont]) then return nil end
  if zoom / math.max(G.ZoomScale and G.ZoomScale() or 1, 1e-6) > G.CITY_MAX_ZOOM then return nil end
  local skips = G.ZoomSkips()
  for _, p in ipairs(ns.Interiors[cont]) do
    if (G.MOUNTAIN_CITY_MODELS[p[1]] or skips[p[1]]) and x >= p[6] and x <= p[8] and y >= p[7] and y <= p[9] then
      local w = ns.WMOs and ns.WMOs[p[1]]
      if w then
        -- (over its rooms, not its box's empty corners)
        local dx, dy = x - p[2], y - p[3]
        local c, sn = math.cos(p[5]), math.sin(p[5])
        local lx, ly = dx * c + dy * sn, -dx * sn + dy * c
        for _, g in ipairs(w.groups) do
          if g["in"] and lx >= g[1] and lx <= g[4] and ly >= g[2] and ly <= g[5] then return p, w, ALL_FLOORS end
        end
      end
    end
  end
  return nil
end
function G.LayoutInstanceArt(cx, cy, inst, rot, zoom, half, band)
  local list = G.ArtList(inst) -- (a cave's map too: G.CaveArt's)
  if not list then return {} end
  local quads = {}
  for _, p in ipairs(list) do
    local w = ns.WMOs[p[1]]
    -- (the band in the model's own height; LayoutInterior widens a room's by Z_SLACK)
    local room = band and { 0, 0, band[1] - p[4] + Z_SLACK, 0, 0, band[2] - p[4] - Z_SLACK } or ALL_FLOORS
    if w then G.LayoutInterior(cx, cy, p, w, room, rot, zoom, half, true, quads) end
  end
  return quads
end

-- The interiors' edge blend (issue #85; the seamless map, north up, not while a game holds the map): a dungeon's or a
-- cave's map had a dark ground over the whole map, black past its rooms. With the blend the stitched world art is drawn
-- under it (a dungeon's laid at its way in, G.InteriorArtSpot) and the dark ground is each room's own: under every
-- model group drawn (G.LayoutInstanceArt's), its box in the model's yards, opaque, with a feather round it fading out
-- over INTERIOR_FEATHER_YD onto the art (Media\Feather, our own: a soft square cut in nine, its corners round, its
-- sides stretched; coast.py's feather()). The art's own pixels past its rooms are clear, so the ground is what
-- follows the dungeon's outline; overlapping feathers make one soft edge round the whole layout.
G.INTERIOR_FEATHER_YD = 60 -- yards from a room's box out over which its dark ground fades out over the art (a knob)
G.INTERIOR_FEATHER = "Interface\\AddOns\\AzerothGPS\\Media\\Feather"
G.INTERIOR_FEATHER_CUT = 0.25 -- the texture's share at each side that's its feather (the rest opaque)
G.INTERIOR_GROUND = { 0.05, 0.045, 0.04, 0.95 } -- the ground's color and alpha (the dark ground it replaces)
G.INTERIOR_GROUND_LAYER = "BORDER" -- (under the art, ARTWORK, and the floors' fill; over the dark ground, BACKGROUND)
-- The dark ground under models `list` (ns.Interiors rows) in the view centered on (cx, cy): the groups of floor band
-- `band` (nil: all) with art, as G.LayoutInstanceArt draws them; with `room` (an inside map: G.LayoutInterior's room
-- of the one model in `list`), that room and the indoor rooms about its height, as G.LayoutInterior draws them. Quads
-- added to `quads`. `feather`: its yards (nil: INTERIOR_FEATHER_YD; a building's over the terrain: G.InteriorTerrain).
function G.InteriorGround(quads, cx, cy, list, band, rot, zoom, half, room, feather)
  local s = half / zoom
  local F, cut = math.max(0, feather or G.INTERIOR_FEATHER_YD), G.INTERIOR_FEATHER_CUT
  local reach = zoom * 1.5 + F
  local tint, layer, fid = G.INTERIOR_GROUND, G.INTERIOR_GROUND_LAYER, G.INTERIOR_FEATHER
  -- (each slice across: from, to (the model's yards), the texture's u0, u1)
  local xs, ys = {}, {}
  for _, p in ipairs(list or {}) do
    local w = ns.WMOs and ns.WMOs[p[1]]
    local r0 = room or band and { 0, 0, band[1] - p[4] + Z_SLACK, 0, 0, band[2] - p[4] - Z_SLACK } or ALL_FLOORS
    local zlo, zhi = r0[3] - Z_SLACK, r0[6] + Z_SLACK
    local c, sn = math.cos(p[5]), math.sin(p[5])
    local texRot = p[5] + math.pi / 2 + rot
    for _, g in ipairs(w and w.groups or {}) do
      if g.blocks and #g.blocks > 0 and (g == room or (not room or g["in"]) and g[6] >= zlo and g[3] <= zhi
          and (not room or G.RoomGroupShown(p, room, g))) then
        local mx, my = (g[1] + g[4]) / 2, (g[2] + g[5]) / 2
        local r = math.max(g[4] - g[1], g[5] - g[2]) / 2 + F
        local dx, dy = Geo.ScreenOffset(cx, cy, p[2] + mx * c - my * sn, p[3] + mx * sn + my * c)
        if math.abs(dx) < reach + r and math.abs(dy) < reach + r then
          local nx, ny = 0, 0
          if F > 0 then
            nx, ny = 1, 1
            -- (v: the top row is the model's highest y, as its art's)
            xs[1], ys[1] = { g[1] - F, g[1], 0, cut }, { g[2] - F, g[2], 1 - cut, 1 }
          end
          nx, ny = nx + 1, ny + 1
          xs[nx], ys[ny] = { g[1], g[4], cut, 1 - cut }, { g[2], g[5], cut, 1 - cut }
          if F > 0 then
            nx, ny = nx + 1, ny + 1
            xs[nx], ys[ny] = { g[4], g[4] + F, 1 - cut, 1 }, { g[5], g[5] + F, 0, cut }
          end
          for i = 1, nx do
            local a = xs[i]
            for j = 1, ny do
              local b = ys[j]
              local lx, ly = (a[1] + a[2]) / 2, (b[1] + b[2]) / 2
              local qx, qy = Geo.ScreenOffset(cx, cy, p[2] + lx * c - ly * sn, p[3] + lx * sn + ly * c)
              qx, qy = Geo.Rotate(qx * s, qy * s, rot)
              quads[#quads + 1] = { fid, qx, qy, (a[2] - a[1]) * s + 0.5, (b[2] - b[1]) * s + 0.5, texRot,
                a[3], a[4], b[3], b[4], 0, tint = tint, layer = layer }
            end
          end
        end
      end
    end
  end
  return quads
end

-- A building's inside map in the seamless style: the terrain round it, a little darker (asked 2026-11-14, two
-- screenshots, Tarren Mill's inn and the minimap square: "When in a building and using seamless we show the world map
-- around the building map. Can we close in the black area outline to much smaller and show the terrain map in the
-- surrounding area instead slightly darker though by like 20% so the player still knows they are in the building but
-- can still see the terrain around them ... the same behaviour on all 3 maps, world map if enabled, gps map, and the
-- minimap"). The edge blend (issue #85) laid the stitched art under its rooms and a dark ground INTERIOR_FEATHER_YD
-- round them: zoomed in that far the art is a few blurry pixels of the zone map's lettering, and on the minimap
-- square's small radius the feathers covered nearly all of it (the second screenshot). Now: the terrain view's own
-- tiles (G.LayoutMinimap, in the same laid set as the rooms: nothing drawn twice, no stitched art), shaded by
-- INTERIOR_TERRAIN_SHADE (vertex color) in the BACKGROUND layer under the rooms' ground, and the ground's feather only
-- INTERIOR_TERRAIN_FEATHER_YD. The tiles turn, so heading-up and a turning minimap get it too (the art couldn't).
-- One view (G.Update) draws the map's window, the map in the game's world map and the minimap square alike.
-- Buildings, a city in a mountain (Ironforge), an underground city's level (Undercity, drawn in its base continent's
-- yards: the land up top round it; asked 2026-11-14 with a screenshot of the minimap square in the War Quarter, still
-- the blurry art and the black: "doesn't seem to apply everywhere") and a cave's map on its continent (view.cave,
-- G.LayoutCaveMap); not a dungeon's map (in its own yards: the art at its way in, as issue #85 has it).
-- A building's outline over the terrain (asked 2026-11-14: "can we tighten up the black outline to the shape of the
-- interior instead of black squares?", then "make the black outline a bit thicker and fade to the other surrounding
-- map"): no dark ground boxes; its art drawn again black under itself, nudged every way (OUTLINE_OFFSETS) at each of
-- OUTLINE_RINGS' distances (UI units) with its alpha, darkest close in, so the edge follows the rooms' own outline (the
-- art is clear past its rooms) and fades out onto the terrain.
-- (a bit wider, 2026-11-15: "increase the black fading outline for buildings/caves just a bit more"; was
-- { 1.5, 0.9 } ... { 12.5, 0.05 })
G.OUTLINE_RINGS = { { 2, 0.9 }, { 4, 0.7 }, { 6, 0.5 }, { 8.5, 0.35 }, { 11, 0.22 }, { 14, 0.12 }, { 17, 0.06 } }
G.OUTLINE_OFFSETS = { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 }, { 0.7, 0.7 }, { -0.7, 0.7 }, { 0.7, -0.7 }, { -0.7, -0.7 } }
G.OUTLINE_AXES = { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } }
G.OUTLINE_DIAGONALS = { { 0.7, 0.7 }, { -0.7, 0.7 }, { 0.7, -0.7 }, { -0.7, -0.7 } }
-- The most copies an outline may add (each a texture placed on every layout). Art of many blocks gets a lighter
-- outline, OUTLINE_LIGHTER's first that fits: Undercity's whole-city map, 172 blocks, had 9,632 copies (1.3.0's
-- stutter walking there, reported 2026-11-15); a building's few blocks keep the full one.
G.OUTLINE_MAX_COPIES = 1600
G.OUTLINE_LIGHTER = { -- (rings { distance, alpha, offsets (nil: OUTLINE_OFFSETS) }; 32, 16, 8 and 4 copies a block)
  { { 3, 0.85 }, { 8, 0.5 }, { 13, 0.25 }, { 17, 0.08 } },
  { { 3, 0.85 }, { 10, 0.4, G.OUTLINE_AXES }, { 16, 0.12, G.OUTLINE_DIAGONALS } },
  { { 3, 0.8, G.OUTLINE_AXES }, { 9, 0.35, G.OUTLINE_DIAGONALS } },
  { { 3, 0.8, G.OUTLINE_AXES } },
}
-- The rings for an outline round `n` blocks: OUTLINE_RINGS, or a lighter set within OUTLINE_MAX_COPIES.
function G.OutlineRings(n)
  local function copies(rings)
    local c = 0
    for _, r in ipairs(rings) do c = c + #(r[3] or G.OUTLINE_OFFSETS) end
    return c * n
  end
  if copies(G.OUTLINE_RINGS) <= G.OUTLINE_MAX_COPIES then return G.OUTLINE_RINGS end
  for _, rings in ipairs(G.OUTLINE_LIGHTER) do
    if copies(rings) <= G.OUTLINE_MAX_COPIES then return rings end
  end
  return G.OUTLINE_LIGHTER[#G.OUTLINE_LIGHTER]
end
G.outlineTints = {}
function G.InteriorOutline(quads)
  local n = #quads
  for _, ring in ipairs(G.OutlineRings(n)) do
    local d = ring[1]
    local tint = G.outlineTints[ring[2]]
    if not tint then
      tint = { 0, 0, 0, ring[2] }
      G.outlineTints[ring[2]] = tint
    end
    for i = 1, n do
      local a = quads[i]
      for _, o in ipairs(ring[3] or G.OUTLINE_OFFSETS) do
        quads[#quads + 1] = { a[1], a[2] + o[1] * d, a[3] + o[2] * d, a[4], a[5], a[6], a[7], a[8], a[9], a[10],
          math.max(-8, (a[11] or 0) - 1), tint = tint, layer = G.INTERIOR_GROUND_LAYER, outline = true }
      end
    end
  end
  return quads
end
-- Whether tiles laid for `laidFor` (TilesKept's key) are kept while the view moves (the layer they're on slid instead):
-- the land's and the zones' (laid out to 1.42 x the zoom round their center), and an inside map's or a cave's over the
-- terrain (its art laid out to 1.5 x the zoom and more, G.LayoutInterior, the terrain's tiles with it).
function G.LaidKeptMoving(laidFor)
  return laidFor:sub(1, 5) == "tiles" or laidFor:sub(1, 4) == "zone"
    or ((laidFor:sub(1, 3) == "in:" or laidFor:sub(1, 5) == "cave:" or laidFor:sub(1, 5) == "inst:")
      and laidFor:sub(-8) == ":terrain")
end
G.INTERIOR_TERRAIN_SHADE = 1 -- the terrain round a building: its color times this (0.8, 20% darker, till 2026-11-15:
-- "lets remove the darken the rest of the map effect when viewing a building's interior")
G.INTERIOR_TERRAIN_FEATHER_YD = 6 -- yards over which a building's dark ground fades out onto the terrain (a knob)
G.INTERIOR_TERRAIN_LAYER = "BACKGROUND" -- (under the rooms' ground, BORDER, and their art, ARTWORK)
-- whether inside map `place` (an ns.Interiors row) or cave map `cave` (G.CaveArt's) gets the terrain round it, in a
-- view where `artA` is the seamless blend's art alpha (nil: not the seamless style, or browsing)
function G.InteriorTerrain(place, artA, cave)
  return artA ~= nil and (place ~= nil or cave ~= nil) or false
end
-- The terrain tiles round a building on `cont` (an underground city's level: its base continent's), as the terrain
-- view lays them, shaded, added to `quads`.
function G.LayoutInteriorTerrain(quads, cx, cy, cont, rot, zoom, half)
  local k = G.INTERIOR_TERRAIN_SHADE
  local tint = { k, k, k, 1 }
  for _, q in ipairs(G.LayoutMinimap(cx, cy, Geo.Base(cont), rot, zoom, half)) do
    q.tint, q.layer, q.terrain = tint, G.INTERIOR_TERRAIN_LAYER, true
    quads[#quads + 1] = q
  end
  return quads
end

-- Where the stitched world art lies under an interior's map (issue #85): { cont, dx, dy }, the view's middle moved
-- by (dx, dy) to that continent's yards, or nil (no art under it). A cave's or an inside map is on its continent
-- (no move; an underground city's in its base's yards); dungeon `inst`'s is in yards of its own, laid with its way in
-- (the spot inside it the way in puts you) on its way in on the continent (G.InstanceWayOut, where zooming out of it
-- goes); the game's marker alone, its middle there.
function G.InteriorArtSpot(inst, viewCont)
  if not inst then return { Geo.Base(viewCont), 0, 0 } end
  local e = G.InstanceWayOut(inst)
  if not e then return nil end
  local ix, iy = e[4], e[5]
  if not (ix and iy) then
    local x0, x1, y0, y1 = G.InstanceBounds(inst)
    if not x0 then return nil end
    ix, iy = (x0 + x1) / 2, (y0 + y1) / 2
  end
  return { e[1], e[2] - ix, e[3] - iy }
end

-- A dungeon's or raid's map over the terrain round it (asked 2026-11-15: "change dungeon/raid maps to use surrounding
-- terrain too when applicable, just like viewing a cave"): where it lies on its continent (G.InteriorArtSpot: its way
-- in), in a view with the seamless blend's art (`artA`), not browsing; not WoW Forever's own dungeons on their own
-- terrain (their map is their terrain). nil: as before (no way in known, another style).
function G.InstanceTerrainSpot(inst, viewCont, artA)
  if not (inst and artA ~= nil) then return nil end
  local lvl = ns.CityLevels and ns.CityLevels[inst]
  if lvl and lvl.terrain then return nil end
  local sp = G.InteriorArtSpot(inst, viewCont)
  if not (sp and ns.MinimapTiles and ns.MinimapTiles[sp[1]]) then return nil end
  return sp
end

-- Points of interest in view: list of { kind, sx, sy, name, x, y, extra, faction }.
-- show = { [1] = flight masters, [2] = map POIs, [3] = place labels } (booleans),
-- faction = "A"/"H"/nil; flight masters of the other faction are skipped.
G.MAX_POIS = 150
function G.LayoutPois(cx, cy, cont, rot, zoom, half, show, faction)
  local out = {}
  local list = ns.Pois and ns.Pois[cont]
  if not list then return out end
  local s = half / zoom
  local reach = zoom * 1.45
  for _, p in ipairs(list) do
    local kind = p[1]
    if show[kind] and (kind ~= 1 or not faction or string.find(p[6], faction, 1, true)) then
      local dx, dy = Geo.ScreenOffset(cx, cy, p[2], p[3])
      if math.abs(dx) < reach and math.abs(dy) < reach then
        dx, dy = Geo.Rotate(dx * s, dy * s, rot)
        if math.abs(dx) <= half and math.abs(dy) <= half then
          out[#out + 1] = { kind, dx, dy, ns.PoiName(p), p[2], p[3], p[5], p[6], level = kind == 1 and p[7] or nil }
          if #out >= G.MAX_POIS then break end
        end
      end
    end
  end
  return out
end

-- World point under a screen offset (dxUI, dyUI) from the center of a view centered on
-- world (cx, cy) with rotation rot and scale s.
function G.ScreenToWorld(cx, cy, dxUI, dyUI, rot, s)
  local east, north = Geo.Rotate(dxUI / s, dyUI / s, -rot)
  return cx + north, cy - east
end

-- Yards from center to edge that fit a whole uiMap (for world-map browsing).
function G.MapFitZoom(m)
  local b = m.bounds
  return math.max(b[3] - b[1], b[4] - b[2]) / 2 * 1.02
end

-- The zone (child of parentID) containing world (x, y), smallest first.
function G.ZoneAt(x, y, parentID)
  local best, bestArea
  for id, m in pairs(ns.Maps or {}) do
    if m.parent == parentID and m.tiles then
      local b = m.bounds
      if x >= b[1] and x <= b[3] and y >= b[2] and y <= b[4] then
        local area = (b[3] - b[1]) * (b[4] - b[2])
        if not bestArea or area < bestArea then best, bestArea = id, area end
      end
    end
  end
  return best
end

-- The smallest zone/city map on continent `cont` containing world (x, y), with the
-- point's map coordinates (0-1): returns uiMapID, name, mx, my.
local cityMaps -- (the city maps: those with a zone around them, `zoneParent`)
-- The city map (uiMapID) at world (x, y) of `cont`: on a capital's own cells, or down in an underground
-- city; nil elsewhere. (The ground's zone there is the land's: Ironforge's is Dun Morogh's.)
function G.CityMapAt(cont, x, y)
  local lvl = G.DownInCityAt and G.DownInCityAt(cont, x, y)
  local l = lvl and ns.CityLevels and ns.CityLevels[lvl]
  if l and l.map and ns.Maps and ns.Maps[l.map] then return l.map end
  local R = ns.Router
  if not (ns.Maps and R and R.CapitalAt and R.CapitalAt(cont, x, y)) then return nil end
  if not cityMaps then
    cityMaps = {}
    for id, m in pairs(ns.Maps) do
      if m.zoneParent and m.bounds then cityMaps[#cityMaps + 1] = id end
    end
    table.sort(cityMaps)
  end
  for _, id in ipairs(cityMaps) do
    local m = ns.Maps[id]
    local b = m.bounds
    if m.continent == cont and x >= b[1] and x <= b[3] and y >= b[2] and y <= b[4] then return id end
  end
  return nil
end

function G.LocateWorld(cont, x, y)
  -- (a city: its own map)
  local city = G.CityMapAt(cont, x, y)
  if city then
    local m = ns.Maps[city]
    local b = m.bounds
    return city, m.name, (b[4] - y) / (b[4] - b[2]), (b[3] - x) / (b[3] - b[1])
  end
  -- (the zone the ground there is in, Data/Zones.lua, when it has it: the zones' outlines
  -- overlap, and a third of Tirisfal's ground is inside Western Plaguelands' by them)
  local R = ns.Router
  local z = R and R.ZoneAt and R.ZoneAt(cont, x, y)
  local zm = z and z ~= 0 and ns.Maps and ns.Maps[z]
  local zb = zm and zm.bounds
  if zb and x >= zb[1] and x <= zb[3] and y >= zb[2] and y <= zb[4] then
    return z, zm.name, (zb[4] - y) / (zb[4] - zb[2]), (zb[3] - x) / (zb[3] - zb[1])
  end
  local best, bestArea
  for id, m in pairs(ns.Maps or {}) do
    local b = m.bounds
    if m.type == 3 and m.continent == cont and b and x >= b[1] and x <= b[3] and y >= b[2] and y <= b[4] then
      local area = (b[3] - b[1]) * (b[4] - b[2])
      if not bestArea or area < bestArea then best, bestArea = id, area end
    end
  end
  if not best then return nil end
  local m = ns.Maps[best]
  local b = m.bounds
  return best, m.name, (b[4] - y) / (b[4] - b[2]), (b[3] - x) / (b[3] - b[1])
end

G.MINIMAP_MAX_ZOOM = 3000 -- wider than this, the terrain view shows map art instead of tiles
-- The zoom limits (yards from the middle to the edge) at the window's size: past ZOOM_REF_SIZE, a bigger
-- window zooms out further at the same scale, more of the map rather than the map bigger (asked
-- 2026-10-01: at the most zoomed out, a bigger window only made the map bigger).
G.ZOOM_REF_SIZE = 450
-- The map window's shape (asked 2026-10-04: big maps up to a 4K screen, then "just support free sizing ... make square
-- default and have a check box ... to freely size the map however"): square (`size` its side), or with "Any shape"
-- (`freeSize`) the corner sets the width (`width`) and the height (`size`) apart. Up to the screen either way.
function G.FreeSize()
  local st = ns.settings and ns.settings.gps
  return st and st.freeSize and st.width ~= nil
end
-- Width to height (of the window as shown): 1 square.
function G.Ratio()
  if not G.FreeSize() then return 1 end
  local w, h = G.MapSize()
  return w / math.max(1, h)
end
-- The window's width and height at `size` (its height; default the setting's: the width as set). The setting's own
-- (no `size`) as the window shows it: kept between what the quick buttons need and the screen (G.FitSize), whatever
-- was saved (a narrow "Any shape" window grew to the screen's height and its title bar went off the top, 2026-10-06).
function G.MapSize(size, own)
  local st = ns.settings and ns.settings.gps
  if not size then
    if not own and G.WorldMapHosted and G.WorldMapHosted() then return G.WorldMapSize() end -- (in the world map)
    local mmSide = not own and G.MinimapSide and G.MinimapSide() -- (the map as the minimap: its square; `own`: the window's)
    if mmSide then return mmSide, mmSide end
    if G.FreeSize() then return G.FitSize(st.width, st.size) end
    local v = (st and st.size) or G.ZOOM_REF_SIZE
    return G.FitSize(v, v)
  end
  return math.floor(size * G.Ratio() + 0.5), size
end
-- The screen in UI units (a 4K one at its UI scale too); 800 x 800 before it's laid out.
G.SIZE_MIN = 120
function G.Screen()
  local w, h = UIParent and UIParent:GetWidth(), UIParent and UIParent:GetHeight()
  if not (w and h) or h < 300 then return 800, 800 end
  return w, h
end
function G.ScreenKnown()
  local h = UIParent and UIParent:GetHeight()
  return h and h >= 300 or false
end
-- What the window has over the map's top edge: the window frame's title bar and the logo half over it (Core.lua
-- FitCorner: CORNER_LOGO_UNITS across, centered TITLE_MID under the frame's top), and its border under the bottom. The
-- map is never taller than the screen less these, and they're kept on the screen with it (ApplySettings: the clamp's
-- insets), so the title bar can always be grabbed (asked 2026-10-06).
G.BOTTOM_ROOM = 2
G.MOVE_TAB_ROOM = 17 -- (the Move tab without the window frame: 18 high, 1 over the map's edge)
function G.TopRoom()
  return CHROME_TITLE + math.ceil(math.max(0, (ns.CORNER_LOGO_UNITS or 62) / 2 - (ns.TITLE_MID or 11))) + 2
end
-- The biggest height (the side, square) that fits the screen with the title bar and logo over it, in steps of 10.
function G.SizeMax()
  local w, h = G.Screen()
  h = h - G.TopRoom() - G.BOTTOM_ROOM
  return math.max(G.SIZE_MIN, math.floor((G.FreeSize() and h or math.min(w, h)) / 10) * 10)
end
-- The widest an "Any shape" map can be: the screen's width.
function G.WidthMax()
  local w = G.Screen()
  return math.max(G.SIZE_MIN, math.floor(w))
end
-- (w, h) as the window may show them: each up to the screen (only once it's laid out: G.ScreenKnown) and not under
-- what the quick buttons need, any shape the width and the height apart (G.QuickMinSides: the buttons along the bottom
-- set the width's, the column going up the height's), square the side both.
function G.FitSize(w, h)
  local minH, minW = G.SIZE_MIN, G.SIZE_MIN
  if G.QuickMinSides then minH, minW = G.QuickMinSides() end
  local maxH, maxW = math.huge, math.huge
  if G.ScreenKnown() then maxH, maxW = G.SizeMax(), G.WidthMax() end
  if not G.FreeSize() then
    local v = math.min(maxH, math.max(w, minH, minW))
    return v, v
  end
  return math.min(maxW, math.max(w, minW)), math.min(maxH, math.max(h, minH))
end
function G.ZoomScale()
  local w, h = G.MapSize()
  return math.max(1, math.max(w, h) / G.ZOOM_REF_SIZE)
end
function G.MaxZoom()
  if G.Seamless() then return math.max(MAX_ZOOM * G.ZoomScale(), G.WorldZoom()) end
  return MAX_ZOOM * G.ZoomScale()
end

-- The seamless zoom (issues #57, #60; the Seamless map style, the default, issue #75): the wheel goes on from the terrain's tiles
-- out to the whole world, on the stitched map's art (Atlas/Atlas.lua: A.ShowOnMap) drawn under the tiles, one zoom with
-- no switch of view. Its stages are counted in the wheel's notches (G.ZOOM_STEP each) from SEAM_TERRAIN_ZOOM (yards
-- from the middle to the edge at the reference size, times G.ZoomScale(), as MINIMAP_MAX_ZOOM):
-- * terrain only, sharp and opaque, from the closest zoom out to SEAM_SHARP_NOTCHES from SEAM_TERRAIN_ZOOM (305 yd as
--   shipped, issue #90; before, 2,500: the terrain view's own furthest, MAX_ZOOM, so every zoom the map had before
--   showed no art. Now the default zoom, 524, a city's own map's 500 and the land view's 2,000 are past the tiles);
-- * SEAM_ART_NOTCHES: the art comes in under the tiles while they still cover it (it shows only where they have none,
--   the open sea), so no hole opens as they go;
-- * SEAM_TILES_NOTCHES: the tiles fade out over the art;
-- * past them, only the art (and the route, stops, icons, player), out to the whole world (G.WorldZoom): first its
--   zones' own art, then the world stage, SEAM_WORLD_NOTCHES on (a continent's worth): the icons a continent map's,
--   no points of interest, marks or caves, and the art's zones giving way to its continents and the world by itself.
-- (Issue #60, read in game, 2026-10-16: the art shows its zones' detail only from about 4,000 yd in (its
-- own zoom 4.5, the engine's detail fade: E.Fades) and continents' art from about 6,000 out, so the tiles must be gone by
-- 4,000 for the zones' stage to show at all: kept 4 notches longer (to 4,900) the terrain went straight to the
-- continents' art. Closer in the engine draws its blurred close-up (its minimap and "soft" stages); the map never
-- tells it a zoom that close (Atlas.lua A.TellZoom, issue #90), so past the tiles it's always the zones' map.
-- Before, the art came in from 2,000 and the tiles began going at 2,200.)
-- G.SEAM_ART_IN, G.SEAM_TILES_OUT (yards: start, end) and G.SEAM_ICONS_FEW are worked out from these (G.SeamStages).
-- Shipped as tuned in testing with the dev tools' knobs (issue #90, 2026-10-17; before: a notch of 1.25, from 2,500
-- yd, 0 sharp notches, 2 world notches, a margin of 1.05): the art in at 305-354 yd, the tiles out by 410, the world
-- stage's icons from there, the whole world 19,073 yd. Past the tiles the art shows the zones' map, never its close-up
-- (Atlas.lua A.TellZoom), so zooming in goes the world's art, the zones' (revealed) map, then the terrain.
G.ZOOM_STEP = 1.16 -- the wheel's notch (the map's OnMouseWheel: out by this, in by 1 / ...)
G.SEAM_TERRAIN_ZOOM = 1000 -- where the notches below are counted from (yards at the reference size)
G.SEAM_SHARP_NOTCHES = -8 -- terrain alone this many notches out past it (negative: in from it; 305 yd)
-- (3 each since 2026-11-14: "for terrain transition, make what 300% is the new 100% default setting"; 1 each before)
G.SEAM_ART_NOTCHES = 3 -- the art in under the tiles
G.SEAM_TILES_NOTCHES = 3 -- the tiles out over the art
G.SEAM_WORLD_NOTCHES = 0 -- the art's zones alone this many notches before the world stage's icons
G.SEAM_WORLD_MARGIN = 0.85 -- the whole world in view with this room round it (under 1: its far edges just off the map)
G.NO_QUADS = {} -- (the art alone: no tiles laid, the same empty list each redraw)

-- the stages' yards (at the reference size) from the notches above
function G.SeamStages()
  local step = G.ZOOM_STEP
  local a0 = G.SEAM_TERRAIN_ZOOM * step ^ G.SEAM_SHARP_NOTCHES
  local a1 = a0 * step ^ G.SEAM_ART_NOTCHES
  local t1 = a1 * step ^ G.SEAM_TILES_NOTCHES
  G.SEAM_ART_IN = { a0, a1 }
  G.SEAM_TILES_OUT = { a1, t1 }
  G.SEAM_ICONS_FEW = t1 * step ^ G.SEAM_WORLD_NOTCHES
end
G.SeamStages()

-- The knobs above, turned live by the developer tools (issue #72: AzerothGPS.SeamKnobs, Api.lua; never by AzerothGPS
-- itself): each one's least and most, and the shipped value (G.SEAM_DEFAULTS). Every reader takes G's value at use.
G.SEAM_KNOBS = {
  { "SEAM_TERRAIN_ZOOM", 100, 20000 }, { "SEAM_SHARP_NOTCHES", -20, 20 }, { "SEAM_ART_NOTCHES", 0, 20 },
  { "SEAM_TILES_NOTCHES", 0, 20 }, { "SEAM_WORLD_NOTCHES", -20, 20 }, { "ZOOM_STEP", 1.01, 4 },
  { "SEAM_WORLD_MARGIN", 0.5, 4 }, { "INTERIOR_FEATHER_YD", 0, 300 }, -- (issue #85: the interiors' feather)
  { "INTERIOR_TERRAIN_FEATHER_YD", 0, 60 }, -- (2026-11-14: a building's, over the terrain)
}
G.SEAM_DEFAULTS = {}
for _, k in ipairs(G.SEAM_KNOBS) do G.SEAM_DEFAULTS[k[1]] = G[k[1]] end
-- a knob set (a number, kept in its range; nil: the shipped value), the stages worked out again and the map redrawn;
-- false for a name that isn't one
function G.SetSeamKnob(name, value)
  for _, k in ipairs(G.SEAM_KNOBS) do
    if k[1] == name then
      if value == nil then value = G.SEAM_DEFAULTS[name] end
      if type(value) ~= "number" or value ~= value then return false end
      G[name] = math.min(k[3], math.max(k[2], value))
      G.SeamStages()
      G.worldZoom = nil -- (its margin)
      if G.Redraw then G.Redraw() end
      return true
    end
  end
  return false
end

-- The player's own stages (Options > Map, the OpenMap style only; asked 2026-11-14: "sliders for adjusting the
-- distance the map transitions from terrain to zone to world map like we did in the dev addon", then the same day:
-- "zone map to world map doesn't change the distance the map fades between these 2. Also should be a third one for
-- the fade to world view ... Also want a transition setting for each level"). Three stages, each where it happens and
-- how long its blend is:
-- * the terrain giving way to the zones' map: `seamTerrainYd` (yards at the reference size, nil the shipped 305:
--   SEAM_SHARP_NOTCHES from SEAM_TERRAIN_ZOOM) and `seamTerrainBlend` (SEAM_ART_NOTCHES and SEAM_TILES_NOTCHES times
--   it), through the dev tools' knobs (G.SetSeamKnob);
-- * the zones' map giving way to the continents' (`seamContinentAt`, `seamContinentBlend`) and the continents' to the
--   whole world's (`seamWorldAt`, `seamWorldBlend`): those are the art engine's own fades on its detail zoom (E.Fades:
--   its "zone" fades, the zones' detail from 1.8 to 4.5, and its "world" ones, the continent layer's 1.3 to 1.7), never
--   the knobs above (the first "zone map to world map" slider moved SEAM_WORLD_NOTCHES, only the icons' world stage at
--   410 yd, so the zones' map faded where it always had, about 6,000 yd out). Set through Atlas.lua's A.SetStages on
--   the engine's E.STAGES: each group moved by ZOOM_STEP ^ -At on its detail zoom (`At` in the wheel's notches from where
--   it's shipped, out positive) and its width times the blend.
-- Blends 1 and notches 0 (the defaults) are the shipped stages, number for number. The order holds: the zones' fade
-- never in past the tiles' end, the world's never in past the zones' (G.SeamContinentLeast, G.SeamWorldLeast).
-- (the terrain's least -20 notches, 51 yd: "Terrain to zone map needs to be able to go down to 50yd", 2026-11-14;
-- -14, 125 yd, before)
G.SEAM_PLAYER_RANGE = { terrain = { -20, 4 }, continent = { -4, 6 }, world = { -6, 3 }, blend = { 0, 3 } }
-- The engine's detail zoom times the yards at the reference size (read on the 450 px map in the harness: 18,245; so
-- the zones' fade's middle, its detail zoom 3, is 6,082 yd and the world's, 1.5, 12,163 yd).
G.SEAM_DETAIL_YD = 18245
G.SEAM_STAGE_MID = { zone = 3, world = 1.5 } -- (the engine's E.STAGE_MID: each group's middle on its detail zoom)
-- yards at the reference size <-> the wheel's notches from SEAM_TERRAIN_ZOOM
function G.SeamNotch(yd) return math.log(yd / G.SEAM_TERRAIN_ZOOM) / math.log(G.ZOOM_STEP) end
function G.SeamNotchYards(n) return G.SEAM_TERRAIN_ZOOM * G.ZOOM_STEP ^ n end
-- an art fade's middle ("zone": the zones' map to the continents', "world": the continents' to the world) in yards at
-- the reference size, `n` notches out from where it's shipped
function G.SeamFadeYards(group, n) return G.SEAM_DETAIL_YD / G.SEAM_STAGE_MID[group] * G.ZOOM_STEP ^ (n or 0) end
-- the least notches the zones' fade can be at: its middle no closer in than the tiles' end
function G.SeamContinentLeast()
  local r = G.SEAM_PLAYER_RANGE.continent
  local n = math.log(G.SEAM_TILES_OUT[2] / G.SeamFadeYards("zone")) / math.log(G.ZOOM_STEP)
  return math.min(r[2], math.max(r[1], n))
end
-- ... and the world's, with the zones' at `nc`: its middle no closer in than theirs
function G.SeamWorldLeast(nc)
  local r = G.SEAM_PLAYER_RANGE.world
  local n = nc + math.log(G.SeamFadeYards("zone") / G.SeamFadeYards("world")) / math.log(G.ZOOM_STEP)
  return math.min(r[2], math.max(r[1], n))
end
G.seamStage = { continent = 0, world = 0 } -- (the art's fades' notches as last applied)
-- the stages now: the terrain giving way (notches from SEAM_TERRAIN_ZOOM), the zones' and the world's fades (notches
-- from shipped), and the least those two can be now
function G.SeamPlayerStages()
  local nc = G.seamStage.continent
  return G.SeamNotch(G.SEAM_ART_IN[1]), nc, G.seamStage.world, G.SeamContinentLeast(), G.SeamWorldLeast(nc)
end
function G.SeamNum(v, lo, hi, default) -- (a number kept in its range, else the default)
  v = tonumber(v)
  if not v or v ~= v then return default end
  return math.min(hi, math.max(lo, v))
end
-- The settings applied (from G.ApplySettings: the options changed, a profile picked, login), only when they changed
-- since last applied, so a dev knob turned meanwhile isn't undone by every redraw of the settings; at login with all
-- of them at their defaults nothing is touched. True when the stages were set.
function G.ApplySeamPlayer()
  local st = ns.settings and ns.settings.gps or {}
  local t = tonumber(st.seamTerrainYd)
  if t and not (t > 0) then t = nil end
  local r = G.SEAM_PLAYER_RANGE
  local tb = G.SeamNum(st.seamTerrainBlend, r.blend[1], r.blend[2], 1)
  local cb = G.SeamNum(st.seamContinentBlend, r.blend[1], r.blend[2], 1)
  local wb = G.SeamNum(st.seamWorldBlend, r.blend[1], r.blend[2], 1)
  local nc = G.SeamNum(st.seamContinentAt, r.continent[1], r.continent[2], 0)
  local nw = G.SeamNum(st.seamWorldAt, r.world[1], r.world[2], 0)
  local key = table.concat({ tostring(t), tb, cb, wb, nc, nw }, "|")
  local before = G.seamPlayerApplied
  if key == before then return false end
  G.seamPlayerApplied = key
  if before == nil and not t and tb == 1 and cb == 1 and wb == 1 and nc == 0 and nw == 0 then return false end
  -- the terrain: where (nil: the shipped value) and its blend (the art in and the tiles out, each its notches times it)
  local sharp = nil
  if t then sharp = math.min(r.terrain[2], math.max(r.terrain[1], G.SeamNotch(t))) end
  G.SetSeamKnob("SEAM_SHARP_NOTCHES", sharp)
  local D = G.SEAM_DEFAULTS
  G.SetSeamKnob("SEAM_ART_NOTCHES", tb ~= 1 and D.SEAM_ART_NOTCHES * tb or nil)
  G.SetSeamKnob("SEAM_TILES_NOTCHES", tb ~= 1 and D.SEAM_TILES_NOTCHES * tb or nil)
  -- the art's own fades, in order after the terrain's
  nc = math.max(nc, G.SeamContinentLeast())
  nw = math.max(nw, G.SeamWorldLeast(nc))
  G.seamStage = { continent = nc, world = nw }
  local step = G.ZOOM_STEP
  local stages = {
    zone = (nc ~= 0 or cb ~= 1) and { step ^ -nc, cb } or nil,
    world = (nw ~= 0 or wb ~= 1) and { step ^ -nw, wb } or nil,
  }
  if ns.Atlas and ns.Atlas.SetStages then ns.Atlas.SetStages(stages) end
  if G.Redraw then G.Redraw() end
  return true
end

-- the share 0-1 of the way from a to b, eased (0 before a, 1 past b)
function G.Smooth(a, b, x)
  if x <= a then return 0 end
  if x >= b then return 1 end
  local t = (x - a) / (b - a)
  return t * t * (3 - 2 * t)
end

-- the art's and the tiles' alpha at `zoom` yards (at the reference size: zoom / G.ZoomScale())
function G.ArtBlend(zoom)
  return G.Smooth(G.SEAM_ART_IN[1], G.SEAM_ART_IN[2], zoom), 1 - G.Smooth(G.SEAM_TILES_OUT[1], G.SEAM_TILES_OUT[2], zoom)
end

-- The seamless blend as last drawn (/agps seamless check, issue #60's readings): the zoom (yards, and at the reference
-- size), its notches from SEAM_TERRAIN_ZOOM, the art's and the tiles' alpha, whether the art shows alone; nil before a
-- redraw
function G.SeamReading()
  local v = G.shownView
  if not (v and v.s and v.s > 0) then return nil end
  local w, h = G.MapSize()
  local zoom = math.max(w, h) / 2 / v.s
  local ref = zoom / G.ZoomScale()
  return { zoom = zoom, ref = ref, notch = math.log(ref / G.SEAM_TERRAIN_ZOOM) / math.log(G.ZOOM_STEP),
    art = G.seamArt or 0, tiles = G.quadAlpha or 1, artOnly = v.artOnly and true or false, seamFar = v.seamFar and true or false,
    edge = v.edge and true or false, -- (the edge blend: the art whole under the tiles, shown only where they have none)
    interior = v.interiorEdge and true or false, -- (the interiors' edge blend: the art round a dungeon's or cave's rooms)
    cont = v.cont, x = math.floor(v.x + 0.5), y = math.floor(v.y + 0.5), seamless = G.Seamless() }
end

-- the tiles' furthest zoom (yards, this map's size): the terrain view's own (MINIMAP_MAX_ZOOM), or with the seamless
-- zoom's blend on, as far as the tiles fade out to
function G.TilesMaxZoom(seam)
  if seam then return G.SEAM_TILES_OUT[2] * G.ZoomScale() * G.SeamShare() end
  return G.MinimapMaxZoom()
end

-- the frame levels the map keeps under its canvas for the art (made at G.Init: on then, and the stitched map wanted)
function G.ArtSpan() return G.artSpan or 0 end

-- whether the seamless zoom is on and can draw: the Seamless style (issue #75), the stitched map loaded and room made
-- for it at login. Not while a game holds the map (API.HoldMap, StreetView's mini game, issue #60): the held style's own rendering then,
-- with the zoom limits it always had, and nothing of the player's settings changed
function G.Seamless()
  local A = ns.Atlas
  -- (the second map, the square while the first is in the game's world map: its engine was loaded only once its art
  -- was first laid, which the square's small radius never asks for, so it drew as the Terrain style: a building's
  -- rooms on black, 2026-11-14's second screenshot. Loaded when first asked, from the first map's chunks)
  if G.clone and A and A.loaded == nil and A.Load and G.ArtSpan() > 0 and G.Style() == "seamless" then pcall(A.Load) end
  return G.Style() == "seamless" and G.ArtSpan() > 0 and A and A.loaded == true and not A.artFailed
    and not (G.Held and G.Held()) or false
end

-- the zoom with the whole world in view: half the world map's width in yards (its continents' frames on it, the
-- widest), and a margin
function G.WorldZoom()
  if G.worldZoom then return G.worldZoom end
  local best = 0
  for _, m in pairs(ns.Maps or {}) do
    for _, wf in pairs(m.worldFrames or {}) do
      if wf[7] > wf[5] then best = math.max(best, (wf[4] - wf[2]) / (wf[7] - wf[5]) / 2) end
    end
  end
  G.worldZoom = best > 0 and best * G.SEAM_WORLD_MARGIN or MAX_ZOOM
  return G.worldZoom
end

function G.MinimapMaxZoom() return G.MINIMAP_MAX_ZOOM * G.ZoomScale() end

-- The smallest map with art on continent `cont` that contains (cx, cy) and is at least
-- about as big as a view of `zoom` yards: a zone, else the continent, else the whole
-- world map (drawn in this continent's coordinates). Returns uiMapID, bounds.
function G.CoveringMap(cont, cx, cy, zoom)
  local best, bestArea, bestBounds
  for id, m in pairs(ns.Maps or {}) do
    local b = m.bounds
    if b and m.tiles and m.continent == cont and cx >= b[1] and cx <= b[3] and cy >= b[2] and cy <= b[4]
        and math.max(b[3] - b[1], b[4] - b[2]) / 2 >= zoom * 0.9 then
      local area = (b[3] - b[1]) * (b[4] - b[2])
      if not bestArea or area < bestArea then best, bestArea, bestBounds = id, area, b end
    end
  end
  if best then return best, bestBounds end
  local w = Geo.WorldMap()
  return w, w and Geo.WorldArtBounds(cont)
end

-- The nearest map with art, starting from uiMap `id` and walking up its parents.
function G.DisplayMap(id)
  local m = id and ns.Maps and ns.Maps[id]
  while m and not m.tiles do
    id = m.parent
    m = ns.Maps[id]
  end
  return m and id or nil
end

-- Free view: dragging the map by (dxUI, dyUI) UI units (+y up) from a view
-- centered on world (x0, y0) with rotation rot and scale s (UI units per yard).
-- The map follows the cursor, so the center moves the other way.
function G.PanCenter(x0, y0, dxUI, dyUI, rot, s)
  local east, north = Geo.Rotate(-dxUI / s, -dyUI / s, -rot)
  return x0 + north, y0 - east
end

---------------------------------------------------------------------------
-- Frame
---------------------------------------------------------------------------

local frame, canvas, lineLayer, arrow, northLabel, infoText, noMapText, recenter
-- a dungeon's map: which floor is shown (text), and "+" / "-" for another (up, down), on a bar
-- (one table: G.Init is near Lua 5.1's 60 outside variables a function may use)
local fl = {}
local free -- nil while following the player; else the frozen view { x, y, rot }
local approachZoom, approachFor, approachSkip -- near a stop: the zoom now (animated); for which stop; skipped for (G.UpdateApproach)
local view = { x = 0, y = 0, rot = 0, s = 1 } -- last drawn view
G.shownView = view -- (the tests)
local drag -- { cx, cy, x, y, rot, s, moved } while the left button is held on the map
local browse, browseZoom -- world-map browsing: displayed uiMap and its zoom (nil = follow the player's zone)
local browseCont, browseBounds -- continent whose coordinates the browsed map is drawn in; its bounds there
local tour -- Route Here tour: { phase, t0, from = {x, y, zoom}, to = {x, y, zoom} }
local navClosedAt -- Nav.Version() when the route panel was closed with its X
local crossH, crossV, routeBtn, navPanel, navText, stepsText
local pending = {} -- stops double-clicked in free view, not yet confirmed: { x, y, cont, icon }
-- (the tutorial, Tutorial.lua: the stops waiting for Confirm Route, read, or put back as they were with `list`)
function G.PendingStops(list)
  if list then
    pending = list
    if G.Redraw then G.Redraw() end
  end
  return pending
end

-- the art's and tiles' alpha for the view now: nil when the seamless zoom doesn't apply (off, a map style, browsing)
-- Heading-up (asked 2026-11-07: "Turn the map with me" stopped working on OpenMap): the art can't turn, and since the
-- stages were tuned (issue #90) it comes in from about 305 yd, so at the usual zooms (400 or so) the map stayed north
-- up. With the map turning, every stage is this many times further out: the art in from SEAM_HEADING_UP_YD (yards at
-- the reference size, where it came in before issue #90), the tiles turning with the player until then.
G.SEAM_HEADING_UP_YD = 2000
function G.SeamShare()
  local st = ns.settings and ns.settings.gps
  local turns = st and (st.rotate or (G.MinimapMode and G.MinimapMode() and G.MinimapRotates()))
  if not turns then return 1 end
  return math.max(1, G.SEAM_HEADING_UP_YD / G.SEAM_ART_IN[1])
end

function G.SeamBlend(zoom)
  if not G.Seamless() or browse or G.IsMapStyle(G.Style()) then return nil end
  return G.ArtBlend(zoom / G.ZoomScale() / G.SeamShare())
end

-- zoomed out past a continent's worth: a continent map's icons only
function G.SeamFar(zoom)
  return G.Seamless() and not browse and zoom / G.ZoomScale() / G.SeamShare() > G.SEAM_ICONS_FEW
end
-- The quests' objectives and turn-ins stay on the world stage out to SEAM_QUESTS_YD (yards at the reference size; asked
-- 2026-11-05: zoomed out on Tirisfal's art the quests had gone with the points of interest, from SEAM_ICONS_FEW's 410
-- yd). Past it the art shows the continents (about 6,000 yd, issue #60's readings) and the zone's quests would be a
-- pile over the player. Their areas are drawn at every zoom (thin outlines, nothing hidden under them).
G.SEAM_QUESTS_YD = 6000
-- The roads and walls shown (Show Roads and Walls, or their options) stay on the art past the tiles out to SEAM_DATA_YD
-- (yards at the reference size; asked 2026-11-14: "when zooming out on seamless with show road/wall data it disappears
-- after terrain data, need to still show it a bit further out"; before, they went with the tiles, at about 410 yd).
-- Past it none, the road and wall tools on too (asked the same day, from a screenshot at about 1,100 yd: "you can stop
-- showing road/wall data past this point of zooming out to save on performance").
G.SEAM_DATA_YD = 1000
function G.SeamDataNear(zoom)
  return zoom / G.ZoomScale() / G.SeamShare() <= G.SEAM_DATA_YD
end
function G.SeamQuests(zoom)
  return zoom / G.ZoomScale() <= G.SEAM_QUESTS_YD
end
-- How far out each kind of icon still shows (asked 2026-11-14: "sliders for Map icons for how far out their icons are
-- rendered"): Options > Map icons, a setting a kind (ICON_YD_KEYS, Core.lua's DEFAULTS), yards to the map's edge at the
-- reference size (zoom / G.ZoomScale(), as G.InteriorZoomOK: the same in the game's world map). ICON_YD_ALWAYS (the
-- top notch): every zoom. "stage", the shipped default of the kinds that went with OpenMap's world stage (G.SeamFar):
-- gone past it there, every zoom in the other styles; its slider shows the stage's yards.
G.ICON_YD_RANGE = { 100, 6100, 100 } -- least, most (always), step
G.ICON_YD_ALWAYS = 6100
G.ICON_YD_KEYS = { taxi = "iconYdTaxi", poi = "iconYdPoi", quests = "iconYdQuests", city = "iconYdCity",
  instances = "iconYdInstances", caves = "iconYdCaves", herbs = "iconYdHerbs", ore = "iconYdOre", pins = "iconYdPins" }
function G.IconYdSetting(kind)
  local key = G.ICON_YD_KEYS[kind]
  local v = ns.settings and ns.settings.gps and ns.settings.gps[key]
  if v == nil then v = ns.DEFAULTS and ns.DEFAULTS.gps[key] end
  return v
end
-- the slider's yards for `kind` ("stage": the world stage's on OpenMap, else always)
function G.IconYd(kind)
  local v = G.IconYdSetting(kind)
  if v == "stage" then
    if G.Style() ~= "seamless" then return G.ICON_YD_ALWAYS end
    return math.min(G.ICON_YD_ALWAYS, G.SEAM_ICONS_FEW * G.SeamShare())
  end
  return math.max(G.ICON_YD_RANGE[1], math.min(G.ICON_YD_ALWAYS, tonumber(v) or G.ICON_YD_ALWAYS))
end
-- whether `kind`'s icons show at `zoom` (`far`: the view's seamFar)
function G.IconShown(kind, zoom, far)
  local v = G.IconYdSetting(kind)
  if v == "stage" then return not far end
  v = tonumber(v)
  if not v or v >= G.ICON_YD_ALWAYS then return true end
  return zoom ~= nil and zoom / math.max(G.ZoomScale(), 1e-6) <= v
end
function G.IconKinds(zoom, far)
  local out = {}
  for kind in pairs(G.ICON_YD_KEYS) do out[kind] = G.IconShown(kind, zoom, far) end
  return out
end

-- the view turns with the player (heading-up) except while the art shows: it can't turn
function G.ViewRot(st, facing, zoom)
  if not st.rotate then return 0 end
  local art = G.SeamBlend(zoom)
  if art and art > 0 then return 0 end
  return -(facing or 0)
end

-- A view looked at elsewhere (dragged, zoomed out) is in its continent's yards, and goes on past its edge: over the
-- other continent (or an isle on a map of its own) on the art it takes that one's (its tiles, roads and icons as it's
-- zoomed in there). Not mid-drag (the drag's start is in the old one's), nor on a dungeon's level or a cave's map. A
-- view on an underground city's level (the player down in Undercity) or still carrying a city's inside map opened
-- before (`interior`, `city`: kept through later drags) goes over too, those left behind (issue #60: Teldrassil,
-- looked at from such a view, never came back to its terrain).
function G.SeamRebase(cont)
  if not free or browse or drag or not G.Seamless() then return end
  if free.instance or (free.cave and view.cave) then return end -- (a cave's map zoomed out past: the land, issue #62)
  local fc = free.cont or cont
  if not fc then return end
  local A = ns.Atlas
  local u, v = A.ToAtlas(fc, free.x, free.y) -- (a city level: by its continent's)
  if not u then return end
  local c, x, y = A.FromAtlas(u, v)
  if c and c ~= Geo.Base(fc) then
    free.cont, free.x, free.y = c, x, y
    free.interior, free.city, free.cave = nil, nil, nil
  end
end
local lastActivity = 0 -- GetTime() of the last click, drag or zoom on the map
local lastClick -- { t, x, y } of the last plain left click, for double-click detection
local stopPins = {}
local AUTO_CONFIRM = 5 -- seconds without map activity before pending stops start the route
local DOUBLE_CLICK = 0.4 -- seconds
local poiLayer, poiButtons, poiLabels = nil, {}, {}
G.poiButtons, G.stopPins = poiButtons, stopPins -- (the minimap hover's tests)

-- Whether the still map shows nothing that moves by the second: no dock's countdown, no party dots, the mouse off it,
-- and the layers as last drawn. The idle redraw then waits for REDRAW_IDLE_QUIET instead of a second (the 2026-10-07
-- idle profile). With a route or stop: false, and true second (`routeOnly`) when the route is as last drawn
-- (G.RouteIdleSig): only the directions panel's text ticks (ETAs, countdowns), refreshed alone (issue #191: a full
-- redraw a second, 5 ms, its tiles laid again, with a route set and the player standing still).
function G.QuietIdle()
  local N = ns.Nav
  local routed = N and (N.route or N.dest or (N.stops and #N.stops > 0)) and true or false
  if #pending > 0 then return false end
  if frame and frame:IsMouseOver() then return false end
  local ok, m = pcall(G.party.io.members)
  if ok and m and m[1] then return false end
  for _, b in ipairs(poiButtons) do
    if b.dock and b:IsShown() and b.timer and b.timer:IsShown() then return false end
  end
  if ns.OtherPins and ns.OtherPins.Pending() then return false end -- (another addon's map icons changed)
  local lv = ns.Layers and ns.Layers.version
  if lv ~= G.quietLayers then
    G.quietLayers = lv -- (on G: the 200-locals limit)
    return false
  end
  if routed then return false, G.RouteIdleSig() == G.routeIdleSig end
  return true
end
-- What the route's drawing goes by besides its table (ViewChanged has that): the stops' version, the faded look while
-- it's checked (Nav.Checking), "keep this route?" (not drawn meanwhile), a quest stop's wait, a forced redraw.
-- G.routeIdleSig: as at the last full redraw.
function G.RouteIdleSig()
  local N = ns.Nav
  return table.concat({ tostring(N.route), tostring(N.dest), tostring(N.Version()),
    tostring(N.Checking and N.Checking() or false), tostring(N.RedAsking and N.RedAsking() or false),
    tostring(N.QuestPaused and N.QuestPaused() or false), tostring(G.drawVersion) }, "|")
end
-- Fading while moving (options): the map's tiles, points of interest, road and quest-area
-- lines, buttons, frame and crosshair fade; the route, the stop markers and the player arrow don't.
local tileLayer, keepLayer, topLayer -- map tiles; stop markers; buttons and text above the map
local fade = 1 -- current share of the map's opacity for the fading parts
local lastMoved = -math.huge -- GetTime() the player was last seen moving
local FADE_SECONDS = 0.4 -- time to fade out or back in
local FADE_HOLD = 1 -- seconds standing still before the map fades back in
local TAXI_ICON = {
  known = "Interface\\TaxiFrame\\UI-Taxi-Icon-Green",
  unlearned = "Interface\\TaxiFrame\\UI-Taxi-Icon-Gray",
  unknown = "Interface\\TaxiFrame\\UI-Taxi-Icon-Yellow",
}
local LABEL_MAX_ZOOM = 1200 -- place names only when zoomed in this far
local ROUTE_COLOR = 3
G.CHECKING_ALPHA = 0.45 -- (a new route still being checked for a shorter way: drawn this faint, Nav.Checking)
local pool, poolUsed = {}, 0
local lines, linesUsed = {}, 0
local dashes, dashesUsed = {}, 0 -- textured dotted lines (DASH_TEXTURE)
local ROAD_COLORS = { [0] = { 1, 0.35, 0.1 }, [1] = { 0.1, 0.9, 1 }, [2] = { 0.3, 1, 0.3 }, [3] = { 0.05, 0.28, 0.85 },
  [4] = { 0.25, 0.85, 1 }, [5] = { 0.65, 0.65, 0.7 }, [6] = { 0.45, 0.6, 1 }, [7] = { 0.55, 0.02, 0.02 },
  [8] = { 0.85, 0.78, 0.6 }, [9] = { 1, 0.85, 0.1 } } -- 6: quest areas, 7: walls, 8: a dungeon's walls (its map)
-- 2: the player's own drawn and recorded roads, green; 9: their own walls, yellow (asked 2026-11-11: "make them green
-- for roads and yellow for walls so the player can see what they have drawn"). Not in the map data yet; once they
-- are, they're roads and walls like any.
G.OWN_ROAD_COLOR, G.OWN_WALL_COLOR = 2, 9
-- Route segment kinds -> { color, width, dotted }: road, off-road, transport ride, far-side walk.
local ROUTE_STYLE = { [0] = { 3, 5, false }, [1] = { 3, 4, true }, [2] = { 4, 4, true }, [3] = { 5, 3, true } }
ROUTE_STYLE[5], ROUTE_STYLE[6] = ROUTE_STYLE[2], ROUTE_STYLE[2] -- (a lift down or up, Router.KIND_LIFT_*: as a ride)
G.RIDE_KINDS = { [2] = true, [5] = true, [6] = true } -- (rides keep their color with several stops)
local DASH, GAP = 7, 5 -- off-road route legs are dotted (UI units)
G.HEADING_UP_LOW = 0.6 -- heading-up, following: the player this share of the half below the middle
G.DETOUR_COLOR = { 0.62, 0.40, 0.18 } -- brown: the detour to a flight master not learned yet (Nav.LearnOnRoute)
-- Dotted legs as one line each, with Media\Dash repeated along it (DASH on, GAP off per
-- 32 pixels of the texture) instead of a line per dash. `/agps debug dashes` switches back
-- to a line per dash (G.dashTexture = false).
local DASH_TEXTURE = "Interface\\AddOns\\AzerothGPS\\Media\\Dash"
G.dashTexture = true
local elapsed = 0
-- Floors over floors, while the road or wall tools are on (Router.WithTracks: an edit changes one
-- floor's roads): the game gives addons no player height, so the player picks the floor they edit
-- (Shift + mouse wheel: G.StepEditFloor), from those where the map is centered; "all floors" until
-- then (and after the tools are off). The other floors' roads and walls draw faint, and the hint says
-- which floor is picked.
G.OTHER_FLOOR_ALPHA = 0.22
G.FLOOR_PICK_YD = 30 -- the floors around the map's middle this far are the ones to pick from
G.editFloor = nil -- the floor picked: { z = height } (a level with heights), { down = bool } (over a cave's floor)
-- The floors to pick from at (x, y) of `level`: on a level with heights, the roads' heights within
-- FLOOR_PICK_YD apart by more than Router.LAYER_Z, bottom up, as { z = middle height }; over a cave's or
-- a capital's floor under walkable ground, { down = true } and { down = false }; else none.
G.FLOOR_GAP_YD = 2.5 -- (a building's flat roads this far apart in height: two floors)
function G.EditFloors(level, x, y)
  local R, P = ns.Router, ns.Passability
  local g = R and R.DebugGraph and level and R.DebugGraph(level)
  local out = {}
  -- (on a continent: its buildings' and capitals' floors, the heights of their flat roads near (`nz`, the same at both
  -- ends; not stairs, whose heights between would join the floors up), where two or more lie near, FLOOR_GAP_YD apart;
  -- asked 2026-10-06, the road tools' heights: the stroke on that floor, at that height)
  if g and not g.floorsAt and g.nz and R.NearestEdges then
    local hs = {}
    for _, c in ipairs(R.NearestEdges(level, x, y)) do
      if c.dist > G.FLOOR_PICK_YD then break end
      local e = g.e[c.edge]
      local za, zb = e and g.nz[e[1]], e and g.nz[e[2]]
      if za and zb and e[4] ~= R.SOURCE_STAIR and math.abs(za - zb) < 1 then hs[#hs + 1] = (za + zb) / 2 end
    end
    table.sort(hs)
    local groups = {}
    for _, h in ipairs(hs) do
      local f = groups[#groups]
      if f and h - f.hi < G.FLOOR_GAP_YD then f.hi = h else groups[#groups + 1] = { lo = h, hi = h } end
    end
    if #groups >= 2 then
      for _, f in ipairs(groups) do out[#out + 1] = { z = math.floor((f.lo + f.hi) * 5 + 0.5) / 10 } end
      return out
    end
  end
  if g and g.floorsAt then
    local hs = g.floorsAt(x, y, G.FLOOR_PICK_YD)
    table.sort(hs)
    local groups = {}
    for _, h in ipairs(hs) do
      local f = groups[#groups]
      if f and h - f.hi <= R.LAYER_Z then f.hi = h else groups[#groups + 1] = { lo = h, hi = h } end
    end
    if #groups >= 2 then
      for _, f in ipairs(groups) do out[#out + 1] = { z = math.floor((f.lo + f.hi) * 5 + 0.5) / 10 } end
    end
    return out
  end
  if level and P and P.OverlayRaw then
    local v, o = P.OverlayRaw(level, x, y)
    if v == 3 and o and o.cave then out = { { down = true }, { down = false } } end
  end
  return out
end
local function SameFloor(a, b)
  if not (a and b) then return a == b end
  if a.z and b.z then return math.abs(a.z - b.z) <= (ns.Router and ns.Router.LAYER_Z or 5) end
  return a.down == b.down
end
-- Shift + mouse wheel with the tools on: the next floor up (delta > 0) or down, "all floors" past the
-- ends, from the floors where the map is centered. Returns whether there were floors to pick from.
function G.StepEditFloor(delta)
  local floors = G.EditFloors(G.shownLevel, view.x, view.y)
  if #floors == 0 then return false end
  local i = 0 -- (0: all floors)
  for k, f in ipairs(floors) do
    if SameFloor(f, G.editFloor) then i = k end
  end
  -- (over a cave's floor: up = up top, the second; a level's floors are bottom up)
  i = i + (delta > 0 and 1 or -1)
  if i > #floors then i = 0 elseif i < 0 then i = #floors end
  G.editFloor = floors[i]
  G.floorLine = nil
  if G.RoadHint and (G.roadMode or G.wallMode) then G.RoadHint() end
  elapsed = 1
  return true
end
-- The floor of an edit on `level` (the stroke's points `pts`): the one picked, as the stroke's `z` (a
-- level with heights), or `indoors` and `down` (over a cave's floor); nil when none is picked (all
-- floors). With no pick over a cave's or capital's grid, `down` (third) is the game's word for its
-- middle (IsIndoors), for the data's build (roads/graph.py).
function G.EditFloor(level, pts)
  local f = G.editFloor
  if f then
    if f.z then return f.z, nil, nil end
    return nil, f.down, f.down
  end
  local N, P, R = ns.Nav, ns.Passability, ns.Router
  local roads = ns.Roads and ns.Roads[level]
  if (roads and roads.z) or not pts or not (ns.CityHalls and ns.CityHalls[level]) then return nil end
  if not (N and N.Indoors and P and P.OverlayRaw and R and R.CaveDown) then return nil end
  local x, _, inst = Geo.PlayerWorld()
  if not x or N.PlayerLevel(inst) ~= level then return nil end
  local k = math.floor(#pts / 4) * 2 + 1
  local v, o = P.OverlayRaw(level, pts[k], pts[k + 1])
  if v == nil then return nil end
  local indoors = N.Indoors()
  return nil, indoors, (o and o.cave and R.CaveDown(level, pts[k], pts[k + 1], indoors, nil)) or nil
end
-- The picked floor while the tools are on (else nil): { z } or { down }.
function G.ToolFloor(level)
  if not (G.roadMode or G.wallMode) then return nil end
  return G.editFloor
end

-- Pins (Pins.lua) and floors: the floors a pin at (x, y) of `level` can be on, bottom up, as
-- { label, z, down }, and the one to start on (0: every floor). A dungeon's floors (its art's, as the
-- map steps them; the height a road has there on it), the one the map shows first; elsewhere the
-- floors the road and wall tools pick from (G.EditFloors), the one picked first.
local pinRoadIndex = setmetatable({}, { __mode = "k" }) -- [a dungeon's graph] = its roads' heights by place
local function RoadHeightsNear(level, x, y)
  local R = ns.Router
  local g = R and R.DebugGraph and R.DebugGraph(level)
  if not (g and g.z and g.e and R.FloorIndex) then return {} end
  local idx = pinRoadIndex[g]
  if not idx then
    idx = R.FloorIndex(g.e, g.z)
    pinRoadIndex[g] = idx
  end
  return idx(x, y, G.FLOOR_PICK_YD) or {}
end
function G.PinFloors(level, x, y)
  local out, pick = {}, 0
  local lvl = ns.CityLevels and ns.CityLevels[level]
  if lvl and lvl.instance then
    local bands = G.InstanceFloors(level)
    if #bands < 2 then return out, 0 end
    local hs = RoadHeightsNear(level, x, y)
    for k, band in ipairs(bands) do
      local z -- (the road's height there nearest the floor's bottom; else its bottom)
      for _, h in ipairs(hs) do
        if h >= band[1] - 2 and h <= band[2] and (not z or h < z) then z = h end
      end
      out[k] = { z = z or band[1] + 1, label = Format(L["floor %d of %d, counting up"], k, #bands) }
    end
    if (view.floor or 0) > 0 then pick = #bands - view.floor + 1 end
    return out, pick
  end
  local floors = G.EditFloors(level, x, y)
  for k, f in ipairs(floors) do
    out[k] = { z = f.z, down = f.down,
      label = f.z and Format(L["floor %d of %d here, counting up"], k, #floors) or (f.down and L["down under"] or L["up top"]) }
    if G.editFloor and SameFloor(f, G.editFloor) then pick = k end
  end
  return out, pick
end
-- Whether pin `p` is on another floor than the one shown (`band`: a dungeon's, { low, high }) or picked
-- with the road and wall tools: drawn faint.
function G.PinOffFloor(p, band)
  if band then
    return p.z ~= nil and (p.z < band[1] - G.FLOOR_HEAD or p.z > band[2] + G.FLOOR_HEAD)
  end
  local f = G.ToolFloor(p.level)
  if not f then return false end
  if f.z and p.z then return math.abs(f.z - p.z) > (ns.Router and ns.Router.LAYER_Z or 5) end
  if f.down ~= nil and p.down ~= nil then return f.down ~= p.down end
  return false
end
-- A pin's floor in words, for its tooltip ("floor 2 of 3, counting up"; nil: on every floor, or none there).
local pinLabels = setmetatable({}, { __mode = "k" }) -- [pin] = its floor's label, or false (worked out once)
function G.PinFloorLabel(p)
  if p.z == nil and p.down == nil then return nil end
  local known = pinLabels[p]
  if known ~= nil then return known or nil end
  local label = G.PinFloorLabelNow(p)
  pinLabels[p] = label or false
  return label
end
function G.PinFloorLabelNow(p)
  local ok, floors = pcall(G.PinFloors, p.level, p.x, p.y)
  local best, bestD
  for _, f in ipairs(ok and floors or {}) do
    if f.down ~= nil and f.down == p.down then return f.label end
    local d = f.z and p.z and math.abs(f.z - p.z) -- (the nearest: a dungeon's floors can lie close)
    if d and d <= (ns.Router and ns.Router.LAYER_Z or 5) and (not bestD or d < bestD) then best, bestD = f, d end
  end
  return best and best.label or nil
end
-- The level a pin at (x, y) (the map's world point) goes on: the one the map shows, an underground
-- city's when its map is shown over it (as a drawn road's, G.FinishRoad).
function G.PinLevel(x, y)
  local _, _, cont = Geo.PlayerWorld()
  local level = browse and browseCont or (free and free.cont) or cont -- (as ViewCont, below)
  local shown = G.shownLevel
  if level and shown and shown ~= level and G.shownCont == level and Geo.Base(shown) == level
      and not (ns.Passability and ns.Passability.InGrid and not ns.Passability.InGrid(shown, x, y)) then
    level = shown
  end
  return level
end
-- Whether road `ei` of graph `g` (on `cont`) is on another floor than the floor `f` (picked: { z } or
-- { down }) there, at the road's middle (the graph's `otherFloors` on a level with heights; where a
-- cave's or a capital's floor lies under walkable ground, by its being the cave's road).
local caveMids = setmetatable({}, { __mode = "k" }) -- [graph] = { [ei] = { x, y } over such a floor, or false }
function G.OtherFloor(g, ei, cont, f)
  local R = ns.Router
  if not (g and f and R and R.NearestHeight) then return false end
  if g.otherFloors then
    local m = g.otherFloors[ei]
    if not (m and f.z) then return false end
    local h = R.NearestHeight(m.hs, f.z)
    return h ~= nil and math.abs(m.h - h) > R.LAYER_Z
  end
  local P = ns.Passability
  if f.down == nil or not (g.cave and g.e and P and P.OverlayRaw) then return false end
  local c = caveMids[g]
  if not c then
    c = {}
    caveMids[g] = c
  end
  local m = c[ei]
  if m == nil then
    m = false
    local e = g.e[ei]
    if e then
      local x, y = R.EdgeMiddle(e)
      local v, o = P.OverlayRaw(cont, x, y)
      if v == 3 and o and o.cave then m = { x, y } end
    end
    c[ei] = m
  end
  if not m then return false end
  return not R.CaveFloorOK(cont, m[1], m[2], g.cave[ei], nil, nil, f.down)
end
-- The hint's floor line while the tools are on: the floor picked, or nil where floors don't lie over
-- each other at the map's middle.
function G.FloorText()
  local floors = G.EditFloors(G.shownLevel, view.x, view.y)
  local f = G.editFloor
  if #floors == 0 and not f then return nil end
  local what
  if not f then
    what = L["all floors"]
  elseif f.z then
    local i = 0
    for k, o in ipairs(floors) do
      if SameFloor(o, f) then i = k end
    end
    what = i > 0 and Format(L["floor %d of %d here, counting up"], i, #floors) or L["the floor picked (none here)"]
  else
    what = f.down and L["down under"] or L["up top"]
  end
  return Format(L["|cffffd100Editing: %s|r  |cff9d9d9d(Shift + mouse wheel picks a floor; other floors faint)|r"], what)
end

local function S() return ns.settings.gps end

-- A dungeon's floors (from its art's rooms): { { lo, hi }, ... } in world height, lowest
-- first. Rooms are grouped by height (a new floor past FLOOR_GAP yards between rooms' bottoms);
-- neighbors that aren't over each other (less than FLOOR_STACK of the smaller overlaps: a
-- cave going down, not a floor over another) are one floor; tiny ones join the one below.
G.FLOOR_GAP, G.FLOOR_STACK, G.FLOOR_MIN_SHARE, G.FLOOR_HEAD = 4, 0.15, 0.03, 6
local floorCache = {}
function G.InstanceFloors(inst)
  local cached = floorCache[inst]
  if cached then return cached end
  local list = G.ArtList(inst) -- (a cave's map too: G.CaveArt's)
  local rooms, total = {}, 0
  for _, p in ipairs(list or {}) do
    local w = ns.WMOs[p[1]]
    local c, sn = math.cos(p[5]), math.sin(p[5])
    for _, g in ipairs(w and w.groups or {}) do
      local x0, y0, x1, y1 = math.huge, math.huge, -math.huge, -math.huge
      for _, lx in ipairs({ g[1], g[4] }) do
        for _, ly in ipairs({ g[2], g[5] }) do
          local x, y = p[2] + lx * c - ly * sn, p[3] + lx * sn + ly * c
          x0, y0, x1, y1 = math.min(x0, x), math.min(y0, y), math.max(x1, x), math.max(y1, y)
        end
      end
      local area = (g[4] - g[1]) * (g[5] - g[2])
      rooms[#rooms + 1] = { p[4] + g[3], area, { x0, y0, x1, y1 } }
      total = total + area
    end
  end
  table.sort(rooms, function(a, b) return a[1] < b[1] end)
  local floors = {}
  for _, r in ipairs(rooms) do
    local f = floors[#floors]
    if f and r[1] - f.last <= G.FLOOR_GAP then
      f.last, f.area = r[1], f.area + r[2]
      f.boxes[#f.boxes + 1] = r[3]
    else
      floors[#floors + 1] = { lo = r[1], last = r[1], area = r[2], boxes = { r[3] } }
    end
  end
  local function overlap(a, b)
    local t = 0
    for _, p in ipairs(a.boxes) do
      for _, q in ipairs(b.boxes) do
        local w, h = math.min(p[3], q[3]) - math.max(p[1], q[1]), math.min(p[4], q[4]) - math.max(p[2], q[2])
        if w > 0 and h > 0 then t = t + w * h end
      end
    end
    return t
  end
  local function join(i)
    local a, b = floors[i], floors[i + 1]
    a.last, a.area = b.last, a.area + b.area
    for _, bx in ipairs(b.boxes) do a.boxes[#a.boxes + 1] = bx end
    table.remove(floors, i + 1)
  end
  local changed = true
  while changed and #floors > 1 do
    changed = false
    for i = 1, #floors - 1 do
      if overlap(floors[i], floors[i + 1]) < G.FLOOR_STACK * math.min(floors[i].area, floors[i + 1].area) then
        join(i)
        changed = true
        break
      end
    end
  end
  for i = #floors, 2, -1 do
    if floors[i].area < total * G.FLOOR_MIN_SHARE then join(i - 1) end
  end
  local out = {}
  for i, f in ipairs(floors) do out[i] = { f.lo, f.last + G.FLOOR_HEAD } end
  floorCache[inst] = out
  return out
end

-- Wings (Data/Instances.lua's `wings`: ways in into parts of their own, the Scarlet Monastery's four,
-- Dire Maul's; each way in's 7th value its wing, each boss's `wing`; asked 2026-10-01): the wing shown
-- of level `lvl`: its map opened from that wing's icon, else the one the player went in by
-- (Taxi.EnteredWing); nil for all of it (no wings, or not known).
function G.InstanceWing(lvl)
  local info = lvl and ns.Instances and ns.Instances[lvl]
  if not (info and info.wings) then return nil end
  if free and free.instance == lvl and free.wing then return free.wing end
  return ns.Taxi and ns.Taxi.EnteredWing and ns.Taxi.EnteredWing(lvl) or nil
end
-- Whether boss row `b` is in wing `wing` (nil: any; a boss with no wing is in each; `wings`: in several,
-- Maraudon's inner bosses).
function G.InWing(b, wing)
  if not wing or not (b.wing or b.wings) then return true end
  if b.wing then return b.wing == wing end
  for _, w in ipairs(b.wings) do
    if w == wing then return true end
  end
  return false
end
-- Wing `wing`'s (first) way in of level `lvl`, else its first.
function G.WingEntrance(lvl, wing)
  local info = ns.Instances and ns.Instances[lvl]
  local list = info and info.entrances or {}
  for _, e in ipairs(list) do
    if wing and e[7] == wing then return e end
  end
  return list[1]
end
-- A wing's extent: its ways in and bosses, WING_MARGIN round them (x0, x1, y0, y1), or nil (none of the
-- bosses its own: a door into the whole dungeon, Uldaman's back way in).
G.WING_MARGIN = 80
function G.WingBounds(lvl, wing)
  local info = ns.Instances and ns.Instances[lvl]
  if not (info and wing) then return nil end
  local x0, x1, y0, y1 = math.huge, -math.huge, math.huge, -math.huge
  local function add(x, y)
    x0, x1, y0, y1 = math.min(x0, x), math.max(x1, x), math.min(y0, y), math.max(y1, y)
  end
  local own = false
  for _, b in ipairs(info.bosses or {}) do
    if b[3] and (b.wing or b.wings) and G.InWing(b, wing) then
      add(b[3], b[4])
      own = true
    end
  end
  if not own then return nil end
  for _, e in ipairs(info.entrances or {}) do
    if e[7] == wing and e[4] then add(e[4], e[5]) end
  end
  local m = G.WING_MARGIN
  return x0 - m, x1 + m, y0 - m, y1 + m
end

-- A dungeon's bosses in the usual order (optional ones left out; those without an order after,
-- as listed): { boss row, ... }. Of wing `wing` (nil: the wing shown, G.InstanceWing; false: all).
function G.BossOrder(lvl, wing)
  if wing == nil then wing = G.InstanceWing(lvl) end
  local info = ns.Instances and ns.Instances[lvl]
  local list = {}
  for i, b in ipairs(info and info.bosses or {}) do
    if not b.optional and G.InWing(b, wing or nil) then list[#list + 1] = { b = b, key = (b.order or 1000) * 1000 + i } end
  end
  table.sort(list, function(a, c) return a.key < c.key end)
  local out = {}
  for i, e in ipairs(list) do out[i] = e.b end
  return out
end

-- The usual way through a dungeon, drawn on its map: from its (first) way in, boss by boss in
-- the usual order, along its roads. World points { x, y, ... }; worked out when first shown
-- (again every 2 s while a terrain search it needs runs), then kept.
local suggested = {}
function G.SuggestedPath(inst)
  local wing = G.InstanceWing(inst) -- (a wing's: from its way in, its bosses)
  local key = wing and (inst .. ":" .. wing) or inst
  local c = suggested[key]
  local now = GetTime and GetTime() or 0
  if c and (c.done or now - c.at < 2) then return c.pts, c.zs, c.legs end
  local info = ns.Instances and ns.Instances[inst]
  local R = ns.Router
  local e = info and G.WingEntrance(inst, wing)
  if not (e and R and R.Route) then return {} end
  local pts, zs, pending = {}, {}, false
  local legs = {} -- { { first point, last point, boss row }, ... }: the way to each boss in turn
  local x, y, z = e[4], e[5], e[6]
  for _, b in ipairs(G.BossOrder(inst, wing or false)) do
    local first = #pts / 2 + 1
    -- (from floor to floor: the heights say which, the stairs between them in the route; no
    -- spot, no stretch)
    local ok, r = false, nil
    if b[3] then ok, r = pcall(R.Route, inst, x, y, b[3], b[4], { offroad = false, z = z, tz = b[5] }) end
    if ok and r and r.pts then
      pending = pending or r.pending
      for i = 1, #r.pts - 1, 2 do
        pts[#pts + 1], pts[#pts + 2] = r.pts[i], r.pts[i + 1]
        zs[#zs + 1] = r.zs and r.zs[(i + 1) / 2] or false
      end
    end
    legs[#legs + 1] = { first, #pts / 2, b }
    if b[3] then x, y, z = b[3], b[4], b[5] end
  end
  suggested[key] = { pts = pts, zs = zs, legs = legs, at = now, done = not pending }
  return pts, zs, legs
end

-- The run so far in a dungeon: the first boss in the usual order still up (its index in
-- G.BossOrder, and its row), or nil when all are down. (Kills: Nav.BossKilled.)
function G.NextBoss(inst)
  for i, b in ipairs(G.BossOrder(inst)) do
    if not ns.Nav.BossDead({ cont = inst, boss = ns.Nav.BossKey(b) }) then return i, b end
  end
  return nil
end

-- Where a route in a dungeon goes up or down to another floor: the foot (or top) of each
-- stair or ramp (a run of legs climbing more than STAIR_SLOPE, joined across flat bits
-- shorter than STAIR_JOIN yards) rising or falling STAIR_RISE yards or more. { { x, y, up,
-- yards along } }, the first `max` of them.
G.STAIR_RISE, G.STAIR_SLOPE, G.STAIR_JOIN = 4, 0.2, 4
function G.FloorChanges(pts, zs, max)
  local out = {}
  if not (pts and zs) then return out end
  local n = #pts / 2
  local run, along = nil, 0
  local function close()
    if run and math.abs(run.dz) >= G.STAIR_RISE then
      out[#out + 1] = { run.x, run.y, run.dz > 0, run.along }
    end
    run = nil
  end
  for i = 1, n - 1 do
    local x1, y1, x2, y2 = pts[2 * i - 1], pts[2 * i], pts[2 * i + 1], pts[2 * i + 2]
    local z1, z2 = zs[i], zs[i + 1]
    local len = math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)
    if z1 and z2 and len > 0 then
      local dz = z2 - z1
      if math.abs(dz) / len >= G.STAIR_SLOPE then
        if run and (dz > 0) == (run.dz >= 0) and along - run.last <= G.STAIR_JOIN then
          run.dz, run.last = run.dz + dz, along + len
        else
          close()
          run = { x = x1, y = y1, dz = dz, along = along, last = along + len }
        end
      elseif run and along + len - run.last > G.STAIR_JOIN then
        close()
      end
    end
    along = along + len
    if max and #out >= max then break end
  end
  close()
  if max then
    while #out > max do table.remove(out) end
  end
  return out
end

-- The floor shown in a dungeon's map: 0 all of them, else counted from the top. Picked with the
-- "+" and "-" buttons (G.FloorStep); until then the player's (at height pz, in it), else all.
local floorSel, floorInst, floorBaseZoom
function G.ShownFloor(inst, pz)
  local floors = G.InstanceFloors(inst)
  if #floors < 2 then return 0 end
  if floorInst ~= inst then floorInst, floorSel, floorBaseZoom = inst, nil, S().zoom end
  if floorSel then return floorSel end
  if pz and pz ~= 0 then
    -- (the highest floor whose bottom is under the player's feet: the one they stand on)
    local best = 1
    for i, f in ipairs(floors) do
      if f[1] - 2 <= pz then best = i end
    end
    return #floors - best + 1
  end
  return 0
end

-- A dungeon's map with floors: the "+" button goes up a floor (all of them past the top one),
-- "-" down one. True when it did.
function G.FloorStep(up)
  local inst = view.instance or (free and free.instance) or view.cave -- (a cave's map: G.CaveArt's)
  local floors = inst and G.InstanceFloors(inst)
  local n = floors and #floors or 0
  if n < 2 then return false end
  local _, _, _, pz = Geo.PlayerWorld()
  local k = G.ShownFloor(inst, view.mine and pz or nil)
  if up then
    if k <= 0 then return false end
    floorSel = k - 1
  else
    if k >= n then return false end
    floorSel = k + 1
  end
  elapsed = 1
  return true
end

-- The continent the view shows: the browsed map's, a free view's (it may be on another
-- continent, e.g. picked from the world map), else the player's.
local function ViewCont(cont)
  return browse and browseCont or (free and free.cont) or cont
end
-- The underground city level (Undercity: 10001) whose art the map shows: its model's inside
-- map (`wmo`, a WMO id) or its zone map (`mapID`); nil for any other. Its roads and walls are
-- the ones drawn over it, and the road tools edit that level there (G.shownLevel); the
-- continent's map around it (the Ruins of Lordaeron, Tirisfal) shows the continent's.
function G.CityArtLevel(wmo, mapID)
  for id, l in pairs(ns.CityLevels or {}) do
    if (wmo and l.wmo == wmo) or (mapID and l.map == mapID) then return id end
  end
  return nil
end
G.shownLevel = nil -- (the last redraw's, with its continent: G.shownCont)
-- The underground city level the player is down in, when (x, y) is over it (its grid); else nil.
function G.DownInCityAt(cont, x, y)
  local lvl = ns.Nav and ns.Nav.PlayerLevel and ns.Nav.PlayerLevel(cont)
  if not (lvl and lvl ~= cont and ns.CityLevels and ns.CityLevels[lvl]) then return nil end
  local P = ns.Passability
  if P and P.InGrid and not P.InGrid(lvl, x, y) then return nil end
  return lvl
end
-- Whether the view's middle (cx, cy) is over the capital the player is in (px, py): anywhere in its grid's
-- rectangle (the rock between Ironforge's halls too: over it the map flipped to the outside, a video
-- 2026-10-01), the player within CITY_VIEW_YD.
G.CITY_VIEW_YD = 900
function G.OverCity(cont, px, py, cx, cy)
  local R, P = ns.Router, ns.Passability
  if not (R and R.CapitalAt and P and P.CapitalGridAt) then return false end
  if (cx - px) ^ 2 + (cy - py) ^ 2 > G.CITY_VIEW_YD ^ 2 then return false end
  if not R.CapitalAt(cont, px, py) then return false end
  local g = P.CapitalGridAt(cont, px, py)
  return g ~= nil and g == P.CapitalGridAt(cont, cx, cy)
end
local fromTerrain -- world-map browsing started by right-clicking the terrain view
local openedFrom -- the view a city's or dungeon's map was opened from (right-click goes back to it)
local LeaveOpened -- (below: right-click out of such a map)

-- The tiles sit on a layer of their own (G.quadLayer, made with tileLayer): panning with the turn, scale
-- and size unchanged moves the layer once instead of placing every tile again (the layouts lay tiles out
-- to 1.42 x the zoom, so a small pan is already covered; the user's 1.1.3 timings: placing the same tiles
-- again was 3.5 ms a redraw on a 1054-wide map).
local function Acquire(i)
  local t = pool[i]
  if not t then
    t = (G.quadLayer or tileLayer):CreateTexture(nil, "ARTWORK")
    if t.SetSnapToPixelGrid then t:SetSnapToPixelGrid(false) end
    if t.SetTexelSnappingBias then t:SetTexelSnappingBias(0) end
    pool[i] = t
  end
  return t
end

-- A dungeon's map (`on`): a dark background (the frame has none of its own: map art always
-- covers it), and with `edges` its floors filled in (the open runs G.BlockEdges works out, as
-- thick lines under the game's minimap art of it and the roads). `bare`: no dark background (the interiors' edge
-- blend, issue #85: the stitched art under it, the rooms' own ground, G.InteriorGround).
local floorBg, floorLines = nil, {}
local FLOOR_BG, FLOOR = G.INTERIOR_GROUND, { 0.36, 0.31, 0.24 }
function G.DrawFloors(on, edges, cx, cy, rot, s, bare)
  local n = 0
  if on and not floorBg then
    floorBg = tileLayer:CreateTexture(nil, "BACKGROUND")
    floorBg:SetAllPoints(tileLayer)
    floorBg:SetColorTexture(FLOOR_BG[1], FLOOR_BG[2], FLOOR_BG[3], FLOOR_BG[4])
  end
  if floorBg then floorBg:SetShown(on and not bare and true or false) end
  if on and edges then
    local fill, w = edges.fill, (edges.step or 2) * s + 1
    for i = 1, fill and #fill - 2 or 0, 3 do
      local x = fill[i]
      local ax, ay = Geo.ScreenOffset(cx, cy, x, fill[i + 1])
      ax, ay = Geo.Rotate(ax * s, ay * s, rot)
      local bx, by = Geo.ScreenOffset(cx, cy, x, fill[i + 2])
      bx, by = Geo.Rotate(bx * s, by * s, rot)
      n = n + 1
      local l = floorLines[n]
      if not l then
        l = tileLayer:CreateLine(nil, "ARTWORK", nil, -8) -- (under the art)
        l:SetColorTexture(FLOOR[1], FLOOR[2], FLOOR[3], 1)
        floorLines[n] = l
      end
      l:SetThickness(w)
      l:SetStartPoint("CENTER", tileLayer, ax, ay)
      l:SetEndPoint("CENTER", tileLayer, bx, by)
      l:Show()
    end
  end
  for i = n + 1, #floorLines do floorLines[i]:Hide() end
end

-- A tile texture's coastline mask (issue #73, G.LayoutMinimap's `q.mask`: file, its whole tile's middle and size on
-- the map; nil: none). Each pooled texture keeps one mask of its own, added while it has one: placed over the whole
-- tile, so the tile's crop to the view needs nothing of it (as the stitched map's masks are); zoomed in so far that
-- the whole tile is over COAST_MASK_MAX_PX (the game stops drawing very large regions), over the crop with the
-- crop's texture coordinates (`q`).
G.COAST_MASK_MAX_PX = 2048
function G.SetQuadMask(t, mask, parent, q)
  if not mask then
    if t.agpsMaskOn then
      t:RemoveMaskTexture(t.agpsMask)
      t.agpsMaskOn = nil
    end
    return
  end
  local m = t.agpsMask
  if not m then
    local host = t.GetParent and t:GetParent() or parent -- (a mask works on its own frame's textures)
    if not (host and host.CreateMaskTexture) then return end
    m = host:CreateMaskTexture()
    t.agpsMask = m
  end
  if m.file ~= mask[1] then
    m:SetTexture(mask[1], "CLAMP", "CLAMP")
    m.file = mask[1]
  end
  m:ClearAllPoints()
  if q and mask[4] > G.COAST_MASK_MAX_PX and m.SetTexCoord then
    m:SetPoint("CENTER", parent, "CENTER", q[2], q[3])
    m:SetSize(q[4], q[5])
    m:SetTexCoord(q[7], q[8], q[9], q[10])
  else
    m:SetPoint("CENTER", parent, "CENTER", mask[2], mask[3])
    m:SetSize(mask[4], mask[5])
    if m.SetTexCoord then m:SetTexCoord(0, 1, 0, 1) end
  end
  if not t.agpsMaskOn then
    t:AddMaskTexture(m)
    t.agpsMaskOn = true
  end
end

local function DrawQuads(quads)
  local parent = G.quadLayer or canvas
  for i, q in ipairs(quads) do
    local t = Acquire(i)
    if q.color then -- (the edge blend's masks under the tiles: G.LayoutMinimap)
      if t.fid ~= "color" then
        t:SetColorTexture(q.color[1], q.color[2], q.color[3], 1)
        t.fid = "color"
      end
    elseif t.fid ~= q[1] then
      t:SetTexture(q[1])
      t.fid = q[1]
    end
    if q.grad then -- (its feathers: G.EdgeFeathers)
      G.SetAlphaGradient(t, q.grad)
      t.grad = true
    elseif q.tint then -- (an interior's dark ground: G.InteriorGround)
      t:SetVertexColor(q.tint[1], q.tint[2], q.tint[3], q.tint[4])
      t.grad = true
    elseif t.grad then
      t:SetVertexColor(1, 1, 1, 1)
      t.grad = nil
    end
    t:ClearAllPoints()
    t:SetPoint("CENTER", parent, "CENTER", q[2], q[3])
    t:SetSize(q[4], q[5])
    t:SetTexCoord(q[7], q[8], q[9], q[10])
    t:SetRotation(q[6] * G.rotSign)
    t:SetDrawLayer(q.layer or "ARTWORK", q[11])
    G.SetQuadMask(t, q.mask, parent, q)
    t:Show()
  end
  for i = #quads + 1, poolUsed do pool[i]:Hide() end
  poolUsed = #quads
end

-- Line records for the current redraw, reused from frame to frame (no garbage):
-- segPool[1..segN] = { x1, y1, x2, y2, color (index or { r, g, b }), thickness, alpha, keep }
-- (keep: part of the route, which doesn't fade while moving).
local segPool, segN = {}, 0
local function AddSeg(ax, ay, bx, by, c, w, a, keep, dotted)
  segN = segN + 1
  local sg = segPool[segN]
  if not sg then
    sg = {}
    segPool[segN] = sg
  end
  sg[1], sg[2], sg[3], sg[4], sg[5], sg[6], sg[7], sg[8], sg[9] = ax, ay, bx, by, c, w, a, keep or false, dotted or false
end

-- Drawing by other addons (the public API, Api.lua). G.overlays[name] = fn(ctx) runs on every
-- redraw; ctx draws in world yards of the continent in view (ctx.cont) and its lines join the
-- map's own (clipped, rotated, no fading). G.roadOwners[owner] = { r, g, b }: the road network
-- is shown, in that color, while anyone asks (the player's own road option wins).
G.overlays, G.roadOwners = {}, {}
if G.clone then G.overlays, G.roadOwners = ns.realGPS.overlays, ns.realGPS.roadOwners end
-- Other addons' Shift-clicks on a dungeon map's boss icons and on NPCs (API.OnIconShiftClick): owner -> { click, hint }.
-- (one table for both maps: the world map's clone takes the window's, as the overlays)
G.iconClicks = G.clone and ns.realGPS.iconClicks or {}

-- Looks other addons give the map (API 14, asked 2026-10-05 for a companion): the player's arrow
-- (G.arrowLooks), the route (G.routeLooks) and the window frame (G.frameLooks), each owner -> its look; the look set
-- last shows, AzerothGPS's own without any (Options > Window's, Looks.lua: G.ownFrameLook, G.ownRouteLook; nil for the
-- game's). Only how things look: nothing here changes what the map does.
G.arrowLooks, G.routeLooks, G.frameLooks, G.lookSeq = {}, {}, {}, 0
if G.clone then G.arrowLooks, G.routeLooks, G.frameLooks = ns.realGPS.arrowLooks, ns.realGPS.routeLooks, ns.realGPS.frameLooks end
function G.ShownFrameLook() return G.LatestLook(G.frameLooks) or G.ownFrameLook end
function G.LatestLook(looks)
  local best
  for _, l in pairs(looks) do
    if not best or l.seq > best.seq then best = l end
  end
  return best
end
function G.LookColor(c, fallback) -- (an { r, g, b } of numbers, or `fallback`)
  if type(c) == "table" and tonumber(c[1]) and tonumber(c[2]) and tonumber(c[3]) then
    return { tonumber(c[1]), tonumber(c[2]), tonumber(c[3]) }
  end
  return fallback
end
-- `owner`'s new look (a fresh record, set last), or nil: no look (removed).
function G.KeepLook(looks, owner, look)
  if owner == nil then return nil end
  if type(look) ~= "table" then
    looks[owner] = nil
    return nil
  end
  G.lookSeq = G.lookSeq + 1
  local l = { seq = G.lookSeq }
  looks[owner] = l
  return l
end

-- The player's arrow: `look.texture` (a path or file id) pointing up (it's turned with the facing as the game's
-- arrow is), `width` and `height` (UI units, 32 by default), `coords` ({ left, right, top, bottom } of the texture),
-- `color` ({ r, g, b }: a tint).
G.ARROW_DEFAULT = { texture = "Interface\\Minimap\\MinimapArrow", width = 32, height = 32 }
function G.SetArrowLook(owner, look)
  local l = G.KeepLook(G.arrowLooks, owner, look)
  if l then
    l.texture = (type(look.texture) == "string" or type(look.texture) == "number") and look.texture or G.ARROW_DEFAULT.texture
    l.width = math.max(4, math.min(256, tonumber(look.width) or 32))
    l.height = math.max(4, math.min(256, tonumber(look.height) or l.width))
    local c = type(look.coords) == "table" and look.coords
    l.coords = c and tonumber(c[1]) and tonumber(c[2]) and tonumber(c[3]) and tonumber(c[4])
      and { tonumber(c[1]), tonumber(c[2]), tonumber(c[3]), tonumber(c[4]) } or nil
    l.color = G.LookColor(look.color)
  end
  G.ApplyArrowLook()
end
function G.ApplyArrowLook()
  if not arrow then return end
  local l = G.LatestLook(G.arrowLooks) or G.ARROW_DEFAULT
  if arrow.agpsLook == l then return end
  arrow.agpsLook = l
  if arrow.agpsTex ~= l.texture then
    arrow:SetTexture(l.texture)
    arrow.agpsTex = l.texture
  end
  local c = l.coords
  arrow:SetTexCoord(c and c[1] or 0, c and c[2] or 1, c and c[3] or 0, c and c[4] or 1)
  arrow:SetSize(l.width, l.height)
  local col = l.color
  arrow:SetVertexColor(col and col[1] or 1, col and col[2] or 1, col and col[3] or 1)
  arrow:SetRotation(arrow.agpsRot or 0) -- (turned after its texture coordinates, as the redraw does)
end

-- The route: `color` ({ r, g, b }: the roads and the legs off them; rides a darker shade; a trip of several stops
-- keeps its stops' colors), `rainbow` (the colors of the rainbow along it, one turn every G.RAINBOW_YD yards,
-- several stops or one), `width` (times the usual, 0.5 to 3), `glow` (a wide faint line under it), `dotted` (every
-- leg dotted). The way back to your body stays red.
G.RAINBOW_YD, G.RAINBOW_STEPS = 600, 36
G.RAINBOW = {} -- [step] = { r, g, b }; [-step]: a ride's darker shade
for i = 1, G.RAINBOW_STEPS do
  local h = (i - 1) / G.RAINBOW_STEPS * 6 -- (red, yellow, green, cyan, blue, magenta, and back to red)
  local f = h - math.floor(h)
  local c = ({ { 1, f, 0 }, { 1 - f, 1, 0 }, { 0, 1, f }, { 0, 1 - f, 1 }, { f, 0, 1 }, { 1, 0, 1 - f } })[math.floor(h) + 1]
  G.RAINBOW[i] = c
  G.RAINBOW[-i] = { c[1] * 0.7, c[2] * 0.7, c[3] * 0.7 }
end
function G.SetRouteLook(owner, look)
  local l = G.KeepLook(G.routeLooks, owner, look)
  if l then
    l.color = G.LookColor(look.color)
    l.shade = l.color and { l.color[1] * 0.7, l.color[2] * 0.7, l.color[3] * 0.7 }
    l.rainbow = look.rainbow == true
    l.width = math.max(0.5, math.min(3, tonumber(look.width) or 1))
    l.glow = look.glow == true
    l.dotted = look.dotted == true
  end
  G.Redraw()
end
-- A route leg's color, width and dotting with the route's look `l` (nil: as AzerothGPS draws it): `col` its color
-- as worked out (its stop's, a ride's), `kind` (Router's: 0 road, 1 off the road, 2 a ride, 3 the far side of a
-- ride, 5 and 6 a lift), `along` the yards along the route to its middle, `own` false for the way back to your body.
function G.RouteLegLook(l, col, width, dotted, kind, along, multi, own)
  if not l then return col, width, dotted end
  if own and kind ~= 3 then
    local ride = kind ~= 0 and kind ~= 1
    if l.rainbow then
      local i = math.floor(along / G.RAINBOW_YD * G.RAINBOW_STEPS) % G.RAINBOW_STEPS + 1
      col = G.RAINBOW[ride and -i or i]
    elseif l.color and not multi then
      col = ride and l.shade or l.color
    end
  end
  return col, math.max(1, width * l.width), dotted or l.dotted
end

-- The window frame: `border` ({ r, g, b }: a tint over its metal), `title` (the title bar's color), `text` (the
-- title's color); API 17 (asked 2026-10-07 for a plugin addon: button colors, the X included, on every window):
-- `buttons` (the panel buttons') and `close` (the close buttons'; else `buttons`).
G.TITLE_STRIP = { 0.06, 0.06, 0.07 }
function G.SetFrameLook(owner, look)
  local l = G.KeepLook(G.frameLooks, owner, look)
  if l then
    l.border = G.LookColor(look.border)
    l.title = G.LookColor(look.title)
    l.text = G.LookColor(look.text)
    l.buttons = G.LookColor(look.buttons)
    l.close = G.LookColor(look.close)
  end
  G.ApplyFrameLook()
  G.ApplyButtonLooks()
end
-- The look's button colors on the map window (G.lookMap: Options > Window's or another addon's look) and on any window
-- another addon registers (G.RegisterLookFrame: weak, a window let go isn't kept; another addon's look only): at once,
-- again at each look change and each time the window is shown (its buttons are often made after it). Never the options
-- window or AzerothGPS's popups (asked 2026-11-04: the window options are the map window's alone). Only panel buttons (their Left, Middle or Center, Right
-- pieces) and close buttons: their normal, pushed and disabled textures and the pieces; never an icon button (the
-- map's layers of icons, tiles and lines are skipped: `agpsNoLook`). A texture's own state color (G.ButtonStateColor)
-- is multiplied by the look's, not replaced. A look's color goes on the texture grayed first (SetDesaturated), so it
-- comes out true: over the game's red button art a Fel green was brown (asked 2026-10-08, "True colors"; a
-- plugin's preview grays the same way, docs/api.md). No look: the game's own art again, white.
G.lookFrames = setmetatable({}, { __mode = "k" })
G.WHITE = { 1, 1, 1 }
G.LOOK_TEXTURES = { "GetNormalTexture", "GetPushedTexture", "GetDisabledTexture" }
G.LOOK_PIECES = { "Left", "Middle", "Center", "Right" }
G.LOOK_DEPTH = 8
function G.TintLookTexture(tex, col)
  if type(tex) ~= "table" or not tex.SetVertexColor then return end
  tex.agpsLook = col
  if tex.SetDesaturated then tex:SetDesaturated(col ~= G.WHITE) end
  local s = tex.agpsState
  tex:SetVertexColor(col[1] * (s and s[1] or 1), col[2] * (s and s[2] or 1), col[3] * (s and s[3] or 1))
end
function G.ButtonStateColor(tex, r, g, b) -- (core's own color for a button's texture by its state; the look multiplies it)
  if type(tex) ~= "table" or not tex.SetVertexColor then return end
  tex.agpsState = r and { r, g, b } or nil
  G.TintLookTexture(tex, tex.agpsLook or G.WHITE)
end
function G.IsCloseButton(parent, b)
  return b.agpsClose == true or b == parent.CloseButton or b == parent.closeButton
end
function G.TintButtons(f, l, depth)
  for _, c in ipairs({ f:GetChildren() }) do
    if type(c) == "table" and not c.agpsNoLook then
      if c.IsObjectType and c:IsObjectType("Button") then
        local close = G.IsCloseButton(f, c)
        local panel = c.Left and c.Right and (c.Middle or c.Center) and true or false
        if close or panel then
          local col = close and (l.close or l.buttons) or l.buttons or G.WHITE
          for _, get in ipairs(G.LOOK_TEXTURES) do
            if c[get] then G.TintLookTexture(c[get](c), col) end
          end
          if panel then
            for _, k in ipairs(G.LOOK_PIECES) do G.TintLookTexture(c[k], col) end
          end
        end
      end
      if depth < G.LOOK_DEPTH and c.GetChildren then G.TintButtons(c, l, depth + 1) end
    end
  end
end
function G.ApplyButtonLook(f)
  if type(f) ~= "table" or not f.GetChildren then return end
  G.TintButtons(f, (f == G.lookMap and G.ShownFrameLook() or G.LatestLook(G.frameLooks)) or {}, 0)
end
function G.ApplyButtonLooks()
  for f in pairs(G.lookFrames) do G.ApplyButtonLook(f) end
end
function G.RegisterLookFrame(f)
  if type(f) ~= "table" or not f.GetChildren then return false end
  if not G.lookFrames[f] then
    G.lookFrames[f] = true
    if f.HookScript then f:HookScript("OnShow", function(self) G.ApplyButtonLook(self) end) end
  end
  G.ApplyButtonLook(f)
  return true
end
-- The look shown (a copy: changing it changes nothing), or nil.
function G.FrameLook()
  local l = G.ShownFrameLook()
  if not l then return nil end
  local function copy(c) return c and { c[1], c[2], c[3] } or nil end
  return { border = copy(l.border), title = copy(l.title), text = copy(l.text), buttons = copy(l.buttons),
    close = copy(l.close) }
end
function G.ApplyFrameLook()
  local chrome = G.chrome
  if not chrome then return end
  local l = G.ShownFrameLook() or {}
  local b = l.border or { 1, 1, 1 }
  local nine = chrome.NineSlice
  if nine and nine.GetRegions then
    for _, r in ipairs({ nine:GetRegions() }) do
      -- (a look's border grayed first, as the buttons: its color true; none: the game's own art)
      if r.SetDesaturated then r:SetDesaturated(l.border ~= nil) end
      if r.SetVertexColor then r:SetVertexColor(b[1], b[2], b[3]) end
    end
  end
  local t = l.title or G.TITLE_STRIP
  if G.chromeStrip then G.chromeStrip:SetColorTexture(t[1], t[2], t[3], 1) end
  local text = chrome.TitleContainer and chrome.TitleContainer.TitleText
  if text and text.SetTextColor and text.GetTextColor then
    if not G.titleTextColor then G.titleTextColor = { text:GetTextColor() } end
    local c = l.text or G.titleTextColor
    text:SetTextColor(c[1], c[2], c[3])
  end
end
function G.IconShiftClick(info)
  for _, h in pairs(G.iconClicks) do
    local ok, used = pcall(h.click, info)
    if ok and used then return true end
  end
  return false
end
-- What a Shift-click on that icon does (info.x nil: on any of the dungeon's bosses), or nil.
function G.IconHint(info)
  for _, h in pairs(G.iconClicks) do
    local text = h.hint
    if type(text) == "function" then
      local ok, t = pcall(text, info)
      text = ok and t or nil
    end
    if type(text) == "string" and text ~= "" then return text end
  end
end
-- What another addon is offered for a Shift-click on an NPC (API 20, issue #383: StreetView's NPC views): its creature
-- id (Data/Npcs.lua's), name, title, x, y on continent `cont` (the base one: Undercity's spots are in its yards), its
-- height, and `floor` the level it's on when that isn't the continent (Undercity's 10001). Nil without an id.
function G.NpcClickInfo(id, name, title, level, x, y, z)
  id = tonumber(id)
  if not (id and x and y and level) then return nil end
  local cont = Geo.Base(level)
  return { kind = "npc", id = id, name = name, title = title, x = x, y = y, z = z, cont = cont,
    floor = level ~= cont and level or nil }
end
-- A search entry's (an NPC's, shipped or talked to) G.NpcClickInfo, or nil.
function G.SearchNpcInfo(e)
  if not (e and e.npc) then return nil end
  return G.NpcClickInfo(e.id, e.name, e.title, e.cont, e.x, e.y, e.z)
end
-- A Shift-click on search row `e`: offered to another addon when it's an NPC's (G.IconShiftClick); true when used.
function G.SearchShiftClick(e)
  local info = G.SearchNpcInfo(e)
  return info ~= nil and G.IconShiftClick(info)
end
-- What a Shift-click on search row `e` does (another addon's hint for an NPC's), or nil.
function G.SearchHint(e)
  local info = G.SearchNpcInfo(e)
  return info and G.IconHint(info) or nil
end
-- A pin made from an NPC's search row (its `npc`: the creature id) as G.NpcClickInfo, or nil.
function G.PinNpcInfo(pin)
  if not (pin and pin.npc) then return nil end
  return G.NpcClickInfo(pin.npc, pin.npcName or pin.name, nil, pin.level, pin.x, pin.y, pin.z)
end
-- A boss icon's name without its place in the usual order ("2. Taragaman" -> "Taragaman").
local function BossName(name) return (tostring(name or ""):gsub("^%d+%. ", "")) end
-- The map held by another addon (a game on it, AzerothGPS-StreetView's): G.holders[owner] =
-- { click = fn(x, y, cont) }. While held, the route (still followed: Nav, the arrow window), the
-- stops' pins, the crosshair with Confirm Route and the top panel aren't shown, and a
-- double-click goes to the holder instead of making a stop.
G.holders = {}
G.HELD_STYLE_TEXT = L["The map style is set by the game on the map while it's on."]
-- Hold or let go of the map for `owner` (API.HoldMap): `h` = { click, style } or nil. A style held, or
-- let go, changes what the map draws as the player's own change would (a map browsed goes back to the
-- terrain view for the terrain style).
function G.SetHolder(owner, h)
  local before = G.Style()
  G.holders[owner] = h
  local now = G.Style()
  if now ~= before then
    if not G.IsMapStyle(now) and browse and G.BrowseToTerrain then G.BrowseToTerrain() end
    if G.RefreshQuick then G.RefreshQuick() end
  end
  if h and G.StopTools then G.StopTools() end -- (no road, wall or farming tools during it)
  if G.Redraw then G.Redraw() end
end
-- Called with the top panel's left inset when it changes (the window frame on or off):
-- G.layoutHooks[owner] = fn(inset). G.topInset: the inset now.
G.layoutHooks, G.topInset = {}, 4
function G.Held() return next(G.holders) ~= nil end
-- The map's own markers that stand in a holder's way (a game on the map): the zeppelins' and
-- boats' docks and the dungeons' entrances, hidden while it's held.
function G.ShowsTravelMarkers() return not G.Held() end
local function HeldClick(x, y, cont)
  for _, h in pairs(G.holders) do
    if h.click then pcall(h.click, x, y, cont) end
    return true
  end
  return false
end
G.HeldClick = HeldClick
function G.ForcedRoadColor()
  for _, c in pairs(G.roadOwners) do return c end
end
local ctx = {}
function ctx.ToScreen(x, y)
  local dx, dy = Geo.ScreenOffset(ctx.x, ctx.y, x, y)
  return Geo.Rotate(dx * ctx.scale, dy * ctx.scale, ctx.rot)
end
local function Outside(ax, ay, bx, by)
  local r = ctx.reach
  return (ax > r and bx > r) or (ax < -r and bx < -r) or (ay > r and by > r) or (ay < -r and by < -r)
end
function ctx.Line(x1, y1, x2, y2, color, width, alpha, dotted)
  local ax, ay = ctx.ToScreen(x1, y1)
  local bx, by = ctx.ToScreen(x2, y2)
  if Outside(ax, ay, bx, by) then return end
  AddSeg(ax, ay, bx, by, color, width or 3, alpha or 1, true, dotted)
end
function ctx.Dot(x, y, color, size, alpha) -- a square dot `size` UI units across
  local sx, sy = ctx.ToScreen(x, y)
  if Outside(sx, sy, sx, sy) then return end
  size = size or 6
  AddSeg(sx - size / 2, sy, sx + size / 2, sy, color, size, alpha or 1, true)
end
-- (API 10) An icon at (x, y): a texture (file id, path or "atlas:<name>"), `size` UI units across.
local overlayIcons, overlayIconsUsed = {}, 0
function ctx.Icon(x, y, texture, size, alpha)
  local sx, sy = ctx.ToScreen(x, y)
  if Outside(sx, sy, sx, sy) or not poiLayer or not G.markLayer then return end
  overlayIconsUsed = overlayIconsUsed + 1
  local t = overlayIcons[overlayIconsUsed]
  if not t then
    t = poiLayer:CreateTexture(nil, "OVERLAY")
    overlayIcons[overlayIconsUsed] = t
  end
  ns.SetIcon(t, texture, "Interface\\Icons\\INV_Misc_QuestionMark")
  t:SetSize(size or 16, size or 16)
  t:SetAlpha(alpha or 1)
  t:ClearAllPoints()
  t:SetPoint("CENTER", G.markLayer, "CENTER", sx, sy) -- (placed each redraw round the view: the marks' anchor)
  t:Show()
end
local function RunOverlays(cx, cy, viewCont, rot, s, half, zoom)
  overlayIconsUsed = 0
  if next(G.overlays) then
    ctx.x, ctx.y, ctx.cont, ctx.rot, ctx.scale, ctx.half, ctx.zoom, ctx.reach = cx, cy, viewCont, rot, s, half, zoom, half * 1.5
    -- (API 21) the level the map shows: an underground city's own (Undercity: 10001) on its map, else ctx.cont; this
    -- map's, the window's or the world map's (G.shownLevel, set earlier in the same redraw)
    ctx.level = G.shownLevel or viewCont
    for name, fn in pairs(G.overlays) do
      local ok, err = pcall(fn, ctx)
      if not ok then G.LogError("overlay " .. tostring(name), err) end
    end
  end
  for i = overlayIconsUsed + 1, #overlayIcons do overlayIcons[i]:Hide() end
end

-- Color, thickness and alpha only when they changed (most lines keep theirs frame to frame).
local function Style(l, c, a, w, textured)
  if l.agpsC ~= c or l.agpsA ~= a then
    if textured then l:SetVertexColor(c[1], c[2], c[3], a) else l:SetColorTexture(c[1], c[2], c[3], a) end
    l.agpsC, l.agpsA = c, a
  end
  if l.agpsW ~= w then
    l:SetThickness(w)
    l.agpsW = w
  end
end

-- A segment clipped to the square [-b, b] (Liang-Barsky): its ends and the share of it cut off its start, or nil when
-- it's all outside. (Asked 2026-10-06 with the errors in the saved data: a dotted leg zoomed in on, long past the map's
-- edges, repeated its dash past the client's limit, "Line:SetTexCoord(): TexCoord out of range", and the redraw stopped.)
local function ClipEdge(p, q, t0, t1)
  if p == 0 then
    if q < 0 then return nil end
    return t0, t1
  end
  local r = q / p
  if p < 0 then
    if r > t1 then return nil end
    if r > t0 then t0 = r end
  else
    if r < t0 then return nil end
    if r < t1 then t1 = r end
  end
  return t0, t1
end
function G.ClipSeg(x1, y1, x2, y2, b)
  local dx, dy = x2 - x1, y2 - y1
  local t0, t1 = ClipEdge(-dx, x1 + b, 0, 1)
  if t0 then t0, t1 = ClipEdge(dx, b - x1, t0, t1) end
  if t0 then t0, t1 = ClipEdge(-dy, y1 + b, t0, t1) end
  if t0 then t0, t1 = ClipEdge(dy, b - y1, t0, t1) end
  if not t0 then return nil end
  return x1 + dx * t0, y1 + dy * t0, x1 + dx * t1, y1 + dy * t1, t0
end
G.CLIP_PAD = 40 -- past the map's edge, lines are clipped this far out
G.MAX_DASH_REPEAT = 1000
-- Only the route near what's shown (asked 2026-10-06: zoomed in on a long route cost as much as zoomed out): each of
-- the route's parts is cut once into chunks of ROUTE_CHUNK segments, its points in the view's continent coordinates,
-- each chunk with its bounds and the yards along the route to it (G.RouteChunks, kept per part: a trim makes a new
-- first part, the rest are kept); a redraw (and the minimap's) goes through only the chunks within `radius` yards of
-- (x, y): fn(x1, y1, x2, y2, kind, stop, partCont, along, z1, z2, part, i) (`part` and `i`: the route part and its
-- piece, Nav.HostileSpans'). G.segsSeen counts the segments it gave (the tests).
G.ROUTE_CHUNK = 16
G.chunkCache = setmetatable({}, { __mode = "k" })
G.segsSeen = 0
function G.RouteChunks(part, view)
  local byView = G.chunkCache[part]
  if not byView then
    byView = {}
    G.chunkCache[part] = byView
  end
  local ch = byView[view]
  if ch then return ch end
  local xs, ys, list = {}, {}, {}
  local pts, n = part.pts, 0
  for i = 1, #pts - 1, 2 do
    local x, y = Geo.ToContinent(part.cont, pts[i], pts[i + 1], view)
    if not x then break end -- (as Nav.EachSegment: not on this continent's map from here on)
    n = n + 1
    xs[n], ys[n] = x, y
  end
  local along, i0 = 0, 1
  while i0 < n do
    local i1 = math.min(n, i0 + G.ROUTE_CHUNK)
    local minx, maxx, miny, maxy, len = xs[i0], xs[i0], ys[i0], ys[i0], 0
    for i = i0 + 1, i1 do
      local x, y = xs[i], ys[i]
      if x < minx then minx = x elseif x > maxx then maxx = x end
      if y < miny then miny = y elseif y > maxy then maxy = y end
      len = len + math.sqrt((x - xs[i - 1]) ^ 2 + (y - ys[i - 1]) ^ 2)
    end
    list[#list + 1] = { i0, i1, minx, maxx, miny, maxy, along }
    along, i0 = along + len, i1
  end
  ch = { xs = xs, ys = ys, list = list, total = along }
  byView[view] = ch
  return ch
end
function G.EachSegmentNear(route, view, x, y, radius, fn)
  local before = 0 -- (the yards of the parts before this one)
  for _, part in ipairs(route.parts or {}) do
    local ch = G.RouteChunks(part, view)
    local xs, ys, kinds, fz = ch.xs, ch.ys, part.kinds, part.fz -- (fz: each point's floor, a building's or a capital's)
    for _, c in ipairs(ch.list) do
      if c[4] >= x - radius and c[3] <= x + radius and c[6] >= y - radius and c[5] <= y + radius then
        local along = before + c[7]
        for i = c[1], c[2] - 1 do
          local x1, y1, x2, y2 = xs[i], ys[i], xs[i + 1], ys[i + 1]
          G.segsSeen = G.segsSeen + 1
          fn(x1, y1, x2, y2, kinds[i], part.stop, part.cont, along, fz and fz[i] or nil, fz and fz[i + 1] or nil, part, i)
          along = along + math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)
        end
      end
    end
    before = before + ch.total
  end
end
-- (asked 2026-10-06: a route that doesn't change isn't drawn again) a line whose ends moved less than this (UI units)
-- since it was placed is left where it is: the game calls that place lines are most of a redraw's line work, and a
-- still map's lines are the same every redraw. G.lineMoves counts the lines placed (the tests).
G.LINE_EPS = 0.1
G.lineMoves = 0
local function PlaceLine(l, x1, y1, x2, y2)
  local e = G.LINE_EPS
  if not l.agpsX1 or math.abs(l.agpsX1 - x1) > e or math.abs(l.agpsY1 - y1) > e or math.abs(l.agpsX2 - x2) > e
      or math.abs(l.agpsY2 - y2) > e then
    l:SetStartPoint("CENTER", G.markLayer, x1, y1)
    l:SetEndPoint("CENTER", G.markLayer, x2, y2)
    l.agpsX1, l.agpsY1, l.agpsX2, l.agpsY2 = x1, y1, x2, y2
    G.lineMoves = G.lineMoves + 1
  end
  if not l.agpsShown then
    l:Show()
    l.agpsShown = true
  end
end
local function HideLine(l)
  if l.agpsShown ~= false then
    l:Hide()
    l.agpsShown = false
  end
end

-- Draw segPool[1..n], each clipped to the map (a little past its edges).
local function DrawLines(n, thickness, colors, alpha)
  local nl, nd = 0, 0
  local b = (canvas and canvas:GetWidth() or 800) / 2 + G.CLIP_PAD
  for i = 1, n do
    local sg = segPool[i]
    local c = type(sg[5]) == "table" and sg[5] or colors[sg[5]] or colors[0] -- index or { r, g, b }
    local a = (sg[7] or alpha) * (sg[8] and 1 or fade)
    local x1, y1, x2, y2, cut = G.ClipSeg(sg[1], sg[2], sg[3], sg[4], b)
    local l
    if not x1 then
      -- (nowhere on the map)
    elseif sg[9] then
      nd = nd + 1
      l = dashes[nd]
      if not l then
        l = lineLayer:CreateLine(nil, "OVERLAY")
        l:SetTexture(DASH_TEXTURE, "REPEAT", "REPEAT")
        dashes[nd] = l
      end
      Style(l, c, a, sg[6] or thickness, true)
      -- (the dashes where they'd be on the whole line: they don't slide along it as the view moves)
      local full = math.sqrt((sg[3] - sg[1]) ^ 2 + (sg[4] - sg[2]) ^ 2)
      local s0 = (full * cut / (DASH + GAP)) % 1
      local reps = math.min(math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2) / (DASH + GAP), G.MAX_DASH_REPEAT)
      if not l.agpsS0 or math.abs(l.agpsS0 - s0) > 0.01 or math.abs(l.agpsReps - reps) > 0.01 then
        l:SetTexCoord(s0, s0 + reps, 0, 1)
        l.agpsS0, l.agpsReps = s0, reps
      end
    else
      nl = nl + 1
      l = lines[nl]
      if not l then
        l = lineLayer:CreateLine(nil, "OVERLAY")
        lines[nl] = l
      end
      Style(l, c, a, sg[6] or thickness, false)
    end
    if l then PlaceLine(l, x1, y1, x2, y2) end
  end
  for i = nl + 1, linesUsed do HideLine(lines[i]) end
  for i = nd + 1, dashesUsed do HideLine(dashes[i]) end
  linesUsed, dashesUsed = nl, nd
end

-- The lines made ahead, hidden, a slice a frame (in Router.WarmUp's background work after a
-- /reload): the first showing of the road network (MAX_SEGMENTS lines, and a companion addon's
-- overlay on top) would otherwise make them all in one frame.
G.WARM_LINES, G.WARM_DASHES = G.MAX_SEGMENTS + 500, 200
function G.WarmLines()
  if not lineLayer then return end
  local breathe = ns.Router and ns.Router.Breathe
  for i = #lines + 1, G.WARM_LINES do
    local l = lineLayer:CreateLine(nil, "OVERLAY")
    l:Hide()
    lines[i] = l
    if breathe then breathe(i, 100) end
  end
  for i = #dashes + 1, G.WARM_DASHES do
    local l = lineLayer:CreateLine(nil, "OVERLAY")
    l:SetTexture(DASH_TEXTURE, "REPEAT", "REPEAT")
    l:Hide()
    dashes[i] = l
    if breathe then breathe(i, 100) end
  end
end

-- Quest area outlines: drawn once on their own layer around an anchor point (the view's
-- centre then), which just slides as the view moves: one SetPoint a frame instead of every
-- outline segment. Redrawn when the zoom, rotation, continent or outlines change, every
-- AREA_REFRESH seconds (new quests get traced), or when the view drifts far from the anchor.
local areaLayer, areaLines, areaUsed, areaState = nil, {}, 0, nil
local AREA_REFRESH = 2
local AREA_COLOR = { 0.45, 0.6, 1 } -- the minimap's quest-area blue (as ROAD_COLORS[6])
-- The inside of each area tinted faintly in the same blue (asked 2026-10-08: being inside a big area showed nothing,
-- zoomed in, its outline out of view): Layers.FillRects' rectangles on the outlines' layer, under them, placed with
-- them (only when they're drawn again, not every frame).
G.AREA_FILL_ALPHA = 0.14
G.areaFills, G.areaFillUsed = {}, 0

local function DrawAreas(on, viewCont, cx, cy, zoom, rot, s, half, maps)
  if not on then
    for i = 1, areaUsed do areaLines[i]:Hide() end
    for i = 1, G.areaFillUsed do G.areaFills[i]:Hide() end
    areaUsed, areaState, G.areaFillUsed = 0, nil, 0
    return
  end
  local st = areaState
  local mapsKey = tostring(maps[1]) .. ":" .. tostring(maps[2])
  local now = GetTime()
  local stale = not st or st.cont ~= viewCont or st.zoom ~= zoom or math.abs(st.rot - rot) > 0.0005
    or st.version ~= ns.Layers.version or st.maps ~= mapsKey or now - st.t > AREA_REFRESH
    or math.max(math.abs(cx - st.ax), math.abs(cy - st.ay)) * s > half * 0.75
  if stale then
    local t0 = ns.PerfStart and ns.PerfStart()
    st = { cont = viewCont, zoom = zoom, rot = rot, version = ns.Layers.version, maps = mapsKey, t = now, ax = cx, ay = cy }
    areaState = st
    local n, nf = 0, 0
    local function fill(x1, y1, x2, y2) -- (a rectangle of an area's inside, as a tile is placed: G.CropQuad)
      local dx, dy = Geo.ScreenOffset(cx, cy, (x1 + x2) / 2, (y1 + y2) / 2)
      local ax, ay = Geo.Rotate(dx * s, dy * s, rot)
      nf = nf + 1
      local t = G.areaFills[nf]
      if not t then
        t = areaLayer:CreateTexture(nil, "BACKGROUND") -- (under the outlines, as they are under the routes)
        t:SetColorTexture(AREA_COLOR[1], AREA_COLOR[2], AREA_COLOR[3], G.AREA_FILL_ALPHA)
        G.areaFills[nf] = t
      end
      t:ClearAllPoints()
      t:SetPoint("CENTER", areaLayer, "CENTER", ax, ay)
      t:SetSize((y2 - y1) * s, (x2 - x1) * s)
      t:SetRotation(rot * G.rotSign)
      t:Show()
    end
    ns.Layers.EachArea(viewCont, cx, cy, zoom * 2.5, maps, function(x1, y1, x2, y2)
      local dx1, dy1 = Geo.ScreenOffset(cx, cy, x1, y1)
      local dx2, dy2 = Geo.ScreenOffset(cx, cy, x2, y2)
      local ax, ay = Geo.Rotate(dx1 * s, dy1 * s, rot)
      local bx, by = Geo.Rotate(dx2 * s, dy2 * s, rot)
      n = n + 1
      local l = areaLines[n]
      if not l then
        l = areaLayer:CreateLine(nil, "OVERLAY")
        l:SetColorTexture(AREA_COLOR[1], AREA_COLOR[2], AREA_COLOR[3], 0.9)
        l:SetThickness(3)
        areaLines[n] = l
      end
      l:SetStartPoint("CENTER", areaLayer, ax, ay)
      l:SetEndPoint("CENTER", areaLayer, bx, by)
      l:Show()
    end, fill)
    for i = n + 1, areaUsed do areaLines[i]:Hide() end
    for i = nf + 1, G.areaFillUsed do G.areaFills[i]:Hide() end
    areaUsed, G.areaFillUsed = n, nf
    if t0 then ns.PerfEnd("quest areas", t0) end
  end
  -- slide the layer: where the anchor is now, relative to the view's centre
  local dx, dy = Geo.ScreenOffset(cx, cy, st.ax, st.ay)
  local ox, oy = Geo.Rotate(dx * s, dy * s, rot)
  areaLayer:ClearAllPoints()
  areaLayer:SetPoint("CENTER", canvas, "CENTER", ox, oy)
end

-- Flight master knowledge for this character: set of known node IDs, and whether any
-- flight map has been seen (otherwise we can't tell known from unlearned).
local function TaxiKnowledge()
  local known, seen = {}, false
  for node in pairs(ns.Nav and ns.Nav.StartingFlightNodes and ns.Nav.StartingFlightNodes() or {}) do known[node] = true end
  local cdb = ns.CharDB()
  for _, entry in pairs(cdb.taxiNodes or {}) do
    for _, n in ipairs(entry.nodes or {}) do
      if n.state ~= nil then seen = true end
      if n.known then known[n.nodeID] = true end
    end
  end
  return known, seen
end

local function PoiButton(i)
  local b = poiButtons[i]
  if b then return b end
  b = CreateFrame("Button", nil, poiLayer)
  b:SetSize(16, 16)
  if G.clickThrough then b.agpsMouse, b.agpsWheel = true, false; b:EnableMouse(false) end
  b.icon = b:CreateTexture(nil, "ARTWORK")
  b.icon:SetAllPoints()
  b:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText(self.name, 1, 1, 1)
    if self.questID and ns.Layers then
      GameTooltip:ClearLines()
      ns.Layers.AddQuestToTooltip(GameTooltip, self.questID)
    end
    if self.note then GameTooltip:AddLine(self.note, 0.7, 0.7, 0.7) end
    -- (the controller in use: its button, and no mouse-only lines; asked 2026-11-16, "the tool tip controls should be
    -- the controller's not mouse instructions")
    if G.PadTipLine(GameTooltip, "select") then GameTooltip:Show() return end
    GameTooltip:AddLine(L["Double-click: add as a stop"], 0.4, 0.8, 1)
    if self.dock and ns.Nav.RideAllowed(ns.Transports[self.dock[1]]) then
      GameTooltip:AddLine(L["Right-click: don't use it in routes"], 0.4, 0.8, 1)
    end
    if self.dock and G.DockShareText(self.dock[1], self.dock[2]) then
      GameTooltip:AddLine(L["Shift-click: paste its times in chat"], 0.4, 0.8, 1)
    end
    if self.pin then
      GameTooltip:AddLine(L["Right-click: remove this pin"], 0.4, 0.8, 1)
      local shift = self.npc and G.IconHint(self.npc) -- (another addon's, which takes the Shift-click first)
      GameTooltip:AddLine(shift and Format(L["Shift-click: %s"], shift) or L["Shift-click: share it in chat"], 0.4, 0.8, 1)
    end
    GameTooltip:Show()
  end)
  b:SetScript("OnLeave", GameTooltip_Hide)
  b:SetScript("OnUpdate", function(self, dt)
    -- (a dock's timer: the tooltip counts down with it)
    if not self.dock or GameTooltip:GetOwner() ~= self then return end
    self.agpsTick = (self.agpsTick or 0) + dt
    if self.agpsTick < 1 then return end
    self.agpsTick = 0
    local _, lines = G.DockTimes(self.dock[1], self.dock[2])
    self.note = lines and table.concat(lines, "\n") or nil
    local onEnter = self:GetScript("OnEnter")
    if onEnter then onEnter(self) end
  end)
  if ns.TimeScript then ns.TimeScript(b, "OnUpdate", "map buttons") end
  b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  b:SetScript("OnClick", function(self, button)
    if self.mapPin and button == "LeftButton" then -- (the map pin: Ctrl-click takes it away, Shift-click links it)
      if IsControlKeyDown and IsControlKeyDown() then
        ns.Import.ClearMapPin()
      elseif IsShiftKeyDown and IsShiftKeyDown() then
        ns.Import.LinkMapPin()
      end
      return
    end
    if button == "LeftButton" and self.dock and IsShiftKeyDown and IsShiftKeyDown() then -- (its times pasted in chat)
      G.ShareDock(self.dock)
      return
    end
    if button == "LeftButton" and self.npc and IsShiftKeyDown and IsShiftKeyDown() and G.IconShiftClick(self.npc) then
      return -- (an NPC's dot or pin: another addon's, API.OnIconShiftClick; else as before)
    end
    if button == "LeftButton" and self.pin and IsShiftKeyDown and IsShiftKeyDown() then -- (asked 2026-10-06)
      G.SharePin(self.pin)
      return
    end
    if button == "LeftButton" and self.bossKey and IsShiftKeyDown and IsShiftKeyDown() -- (another addon's: API.OnIconShiftClick)
      and G.IconShiftClick({ kind = "boss", name = BossName(self.name), x = self.wx, y = self.wy, z = self.z,
        cont = self.level or view.cont }) then
      return
    end
    if button == "RightButton" then -- (a pin: "Remove?"; a boss: defeated or not, by hand; a dock: in routes or not)
      if self.pin then G.AskRemove(self) end
      if self.dock then G.AskRideOff(self.dock) end
      if self.bossKey and self.level then
        ns.Nav.SetBossDead(self.level, self.bossKey, not self.dead)
        G.Redraw()
      end
      return
    end
    if self.cityMap then G.ShowCity(self.cityMap) end -- (a capital on a continent's map)
    if self.instance then G.ShowInstance(self.instance, self.wing) end -- (a dungeon's entrance: its map, a wing's)
    if self.cave then G.ShowCave(self.caveCont, self.cave) end -- (a cave's way in: its map, G.CaveArt's)
    if self.exit then G.ShowEntrance(self.exit) end -- (in a dungeon's map: back out at its entrance)
  end)
  b:SetScript("OnDoubleClick", function(self)
    if self.cityMap or self.exit then return end
    -- (a controller's Select on it, the game's controller UI clicking it too: one click, no stop; asked 2026-11-16,
    -- "Select button still sets a route stop instead of clicking to open a dungeon view")
    if G.PadClickedJustNow() then return end
    if G.Held() then return HeldClick(self.wx, self.wy, self.level or view.cont) end -- (the holder's)
    -- (like a double-click on the map, with its name and icon; a pin's, on its own level; a quest's, its quest)
    G.AddStopAt(self.wx, self.wy, self.name, self.level, self.stopTex, self.z, self.pin ~= nil, self.questID)
  end)
  poiButtons[i] = b
  return b
end

local INSTANCE_ICON = "Interface\\Icons\\INV_Misc_Bone_HumanSkull_01"
local CAVE_ICON = "Interface\\Icons\\INV_Pick_02"
-- A dungeon's usual way through, on its map (dotted): its color picked on the map (issue #16, G.MakePathColorPicker;
-- setting `dungeonPathColor`): Gold, as it always was, or one of the route's colors (Nav.MARKER_COLORS). Each has a
-- brighter one for the stretch to the next boss still up.
G.DUNGEON_PATH_COLORS = { { key = "gold", name = L["Gold"], color = { 1, 0.78, 0.15 }, next = { 1, 0.95, 0.45 } } }
for i, c in ipairs(ns.Nav and ns.Nav.MARKER_COLORS or {}) do -- (Nav.lua loads first; some tests load this alone)
  local name = ns.Nav.MARKER_COLOR_NAMES[i]
  G.DUNGEON_PATH_COLORS[#G.DUNGEON_PATH_COLORS + 1] = { key = ns.Nav.MARKER_COLOR_KEYS[i], name = name, color = c,
    next = { c[1] + (1 - c[1]) * 0.45, c[2] + (1 - c[2]) * 0.45, c[3] + (1 - c[3]) * 0.45 } }
end
-- The picked one's entry (an unknown key: Gold).
function G.DungeonPathColor(key)
  for _, e in ipairs(G.DUNGEON_PATH_COLORS) do
    if e.key == key then return e end
  end
  return G.DUNGEON_PATH_COLORS[1]
end
-- The dungeon map's note on it, named and colored as picked ("Gold: the usual way through" in gold).
function G.PathColorNote(e)
  local c = e.color
  return Format(L["  |cff%02x%02x%02x%s: the usual way through|r"], math.floor(c[1] * 255 + 0.5),
    math.floor(c[2] * 255 + 0.5), math.floor(c[3] * 255 + 0.5), e.name)
end
local DOCK_ICON = { zeppelin = "Interface\\AddOns\\AzerothGPS\\Media\\Zeppelin",
  boat = "Interface\\AddOns\\AzerothGPS\\Media\\Ship", -- (our own art, Media/)
  tram = "Interface\\Icons\\INV_Misc_Gear_01" } -- (the Deeprun Tram's ends: no timetable)
local DOCK_NAME = { zeppelin = L["Zeppelin to %s"], boat = L["Boat to %s"], tram = L["Deeprun Tram to %s"] }

-- A zeppelin's or boat's dock: its timer ("in 2:10" to its next arrival, "leaves 0:45" while
-- it's docked) and the tooltip's lines, from Taxi's learned timetable.
local function Clock(sec)
  sec = math.max(0, math.floor(sec + 0.5))
  return string.format("%d:%02d", math.floor(sec / 60), sec % 60)
end
function G.DockTimes(i, side)
  local T, t = ns.Taxi, ns.Transports and ns.Transports[i]
  if not (T and T.TransportTimes and t and t.cycle) then return nil end -- (the tram: no timetable)
  local now = GetServerTime and GetServerTime() or (time and time()) or 0
  local arr, dep, age = T.TransportTimes(i, side, now)
  if not arr then return nil, { L["Timetable: ride it once and the addon learns it"] } end
  local wait = side == 1 and t.wait1 or t.wait2
  local docked = dep <= wait
  local short = docked and Format(L["leaves %s"], Clock(dep)) or Clock(arr)
  local lines = { docked and Format(L["At the dock: leaves in %s"], Clock(dep))
    or Format(L["Arrives in %s, leaves in %s"], Clock(arr), Clock(dep)) }
  if age > 6 * 3600 then
    lines[#lines + 1] = Format(L["(learned %d h ago: a server restart since would put it off)"], math.floor(age / 3600))
  end
  return short, lines, docked
end

-- A dock's times as a chat line (asked 2026-10-02: Shift-click a zeppelin with known timing to paste it, never
-- sent by itself): "Zeppelin from Brill to Grom'gol Base Camp: arrives in 2:10, leaves in 3:10"; nil while
-- its timetable isn't known yet.
function G.DockShareText(i, side)
  local t = ns.Transports and ns.Transports[i]
  local T = ns.Taxi
  if not (t and T and T.TransportTimes) then return nil end
  local now = GetServerTime and GetServerTime() or (time and time()) or 0
  local arr, dep = T.TransportTimes(i, side, now)
  if not arr then return nil end
  local function Town(name) return (((name or "?"):match("^[^,]+") or "?"):gsub("|", "")) end
  local here, there = Town(ns.RideEndName(t, side)), Town(ns.RideEndName(t, 3 - side))
  local boat = t[8] == "boat"
  local wait = side == 1 and t.wait1 or t.wait2
  if dep <= wait then
    return Format(boat and L["Boat from %s to %s: at the dock, leaves in %s"]
      or L["Zeppelin from %s to %s: at the dock, leaves in %s"], here, there, Clock(dep))
  end
  return Format(boat and L["Boat from %s to %s: arrives in %s, leaves in %s"]
    or L["Zeppelin from %s to %s: arrives in %s, leaves in %s"], here, there, Clock(arr), Clock(dep))
end

-- Right-click on a dock (asked 2026-10-03): don't use that zeppelin, boat or tram in routes from now on, or use it
-- again (Nav.SetRideAllowed; Options → Routing lists them all).
function G.AskRideOff(dock)
  local t = dock and ns.Transports and ns.Transports[dock[1]]
  if not (t and ns.Nav.RIDE_KINDS[t[8]]) then return end
  local on = ns.Nav.RideAllowed(t)
  local a, b = (ns.RideEndName(t, 1) or "?"):match("^[^,]+"), (ns.RideEndName(t, 2) or "?"):match("^[^,]+")
  local text
  if t[8] == "tram" then
    text = on and Format(L["Don't use the Deeprun Tram between %s and %s in routes?\n\nOptions -> Routing turns it back on."], a, b)
      or Format(L["Use the Deeprun Tram between %s and %s in routes again?"], a, b)
  elseif t[8] == "boat" then
    text = on and Format(L["Don't use the boat between %s and %s in routes?\n\nOptions -> Routing turns it back on."], a, b)
      or Format(L["Use the boat between %s and %s in routes again?"], a, b)
  else
    text = on and Format(L["Don't use the zeppelin between %s and %s in routes?\n\nOptions -> Routing turns it back on."], a, b)
      or Format(L["Use the zeppelin between %s and %s in routes again?"], a, b)
  end
  G.Ask("AzerothGPSRideOff", text, on and L["Don't Use"] or L["Use It"], L["Cancel"], function()
    ns.Nav.SetRideAllowed(t, not on)
    G.Redraw()
  end, nil, { timeout = 30 })
end

-- Shift-click on a dock (its map icon, or the route's ride icon there): its times pasted in chat.
-- A pin into the chat box being typed in (else a new one), for the player to send: AzerothGPS users get it as a link
-- that adds it to their map (Import.PinTag). Nothing is sent here.
function G.SharePin(pin)
  if not (pin and pin.x and ns.Import and ns.Import.PinTag) then return false end
  return ns.Import.PasteInChat(ns.Import.PinTag(pin, ns.Pins and ns.Pins.PlaceName(pin)))
end
function G.ShareDock(dock)
  local text = dock and G.DockShareText(dock[1], dock[2])
  local t = dock and ns.Transports and ns.Transports[dock[1]]
  if not text and t and not t.cycle then return false end -- (the tram: no timetable to share)
  if not text then
    ns.Print(L["No timetable for this one yet: ride it once and AzerothGPS learns it."])
    return false
  end
  return ns.Import.PasteInChat(text)
end
local BOSS_ICON ="Interface\\TargetingFrame\\UI-TargetingFrame-Skull"
local EXIT_ICON = "Interface\\Icons\\Spell_Arcane_PortalOrgrimmar"

-- A map label on whole screen pixels (the user, 2026-10-01: place names and city labels looked soft). The
-- map scrolls smoothly, so a label's spot mostly falls between pixels, and the game smears text drawn
-- there; its 1-unit shadow lands between pixels too. `fs`'s top-left goes on the pixel nearest to where
-- `point` ("CENTER" or "BOTTOM") at (x, y) from `parent`'s middle would put it, its shadow one pixel off.
function G.PinText(fs, parent, point, x, y)
  local ppu = ns.PixelsPerUnit(parent:GetEffectiveScale())
  local w, h = fs:GetStringWidth() or 0, fs:GetStringHeight() or 0
  local left, top = G.SnapPoint(parent, x - w / 2, point == "BOTTOM" and y + h or y + h / 2)
  fs:ClearAllPoints()
  fs:SetPoint("TOPLEFT", parent, "CENTER", left, top)
  fs:SetShadowOffset(1 / ppu, -1 / ppu)
end

-- An offset from `parent`'s middle moved onto the nearest whole screen pixel.
function G.SnapPoint(parent, x, y)
  local ppu = ns.PixelsPerUnit(parent:GetEffectiveScale())
  local pcx, pcy = parent:GetCenter()
  if not (pcx and pcy) then return x, y end
  return math.floor((pcx + x) * ppu + 0.5) / ppu - pcx, math.floor((pcy + y) * ppu + 0.5) / ppu - pcy
end

-- Game icons (64-pixel art) drawn at an exact quarter of their pixels, ICON_PX on the screen, on whole pixels
-- (the user, 2026-10-01: city places, pins, stops made from them, party members' class icons looked grainy;
-- half, 32, was too large). The client shrinks with the plain filter only (a finer one, "TRILINEAR", crashed
-- it); at a whole fraction every screen pixel takes the same share of the art, not grainy.
G.ICON_PX = 16
-- The map's icons' size (asked 2026-11-14: "increase the size of icons outside of buildings by 25%", then "render
-- them in multiple sizes, current is small, make a medium, and large. put this under the map icon options";
-- `iconSize`, Options > Map icons): each icon's size times this (G.PoiSize in DrawPois), not an inside map's NPCs.
G.ICON_SIZES = { small = 1, medium = 1.25, large = 1.5 }
function G.PoiScale()
  local st = ns.settings and ns.settings.gps
  return G.ICON_SIZES[st and st.iconSize or "medium"] or G.ICON_SIZES.medium
end
G.poiScaleNow = 1
function G.PoiSize(b, w, h)
  local k = G.poiScaleNow or 1
  b:SetSize(w * k, h * k)
end
-- an inside map's NPC (POI kind 16): a dot NPC_DOT_PX across, or its service's game icon NPC_ICON_PX across instead
-- (asked 2026-11-14: "make the npc dots a little bigger, if the npc can have a icon, use the icon instead")
G.NPC_DOT_PX = 10
G.NPC_ICON_PX = 14
G.NPC_DOT_TEXTURE = "Interface\\Common\\Indicator-Gray"
G.NPC_DOT_COLOR = { 1, 0.85, 0.3 }
function G.IsGameIcon(tex)
  if type(tex) == "number" then return true end
  return type(tex) == "string" and tex:lower():find("^interface[\\/]icons[\\/]") ~= nil
end
-- `px` screen pixels in `frame`'s UI units.
function G.PxUnits(frame, px)
  return px / ns.PixelsPerUnit(frame:GetEffectiveScale())
end

local function DrawPois(pois, zoom)
  local known, seen = TaxiKnowledge()
  local nb, nl = 0, 0
  for _, p in ipairs(pois) do
    if p[1] == 3 then
      if zoom <= LABEL_MAX_ZOOM then
        nl = nl + 1
        local fs = poiLabels[nl]
        if not fs then
          fs = poiLayer:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
          fs:SetTextColor(1, 0.95, 0.8)
          poiLabels[nl] = fs
        end
        fs:SetText(p[4])
        G.PinText(fs, poiLayer, "CENTER", p[2], p[3])
        fs:Show()
      end
    else
      nb = nb + 1
      local b = PoiButton(nb)
      G.poiScaleNow = p[1] == 16 and 1 or G.PoiScale()
      b.name, b.wx, b.wy = p[4], p[5], p[6]
      b.level = p.level -- (a flight master down in a city: its stop is on the city's level)
      b.kind, b.city = p[1], p.city -- (named on hover as the minimap square: G.MinimapTipText)
      b.z = p.z -- (a city place's height: its floor, where floors lie over each other)
      b.preview, b.cityMap, b.instance, b.exit, b.wing, b.cave, b.caveCont = nil, nil, nil, nil, nil, nil, nil
      b.dock, b.pin, b.bossKey, b.dead, b.mapPin, b.npc = nil, nil, nil, nil, nil, nil
      if b.timer then b.timer:Hide() end
      if p[1] == 10 then -- a zeppelin's or boat's dock: its next arrival under it
        ns.SetIcon(b.icon, DOCK_ICON[p.kind])
        b.stopTex, b.questID = DOCK_ICON[p.kind], nil
        b.dock = p.dock
        local short, lines, docked = G.DockTimes(p.dock[1], p.dock[2])
        lines = lines or {}
        if p.rideOff then table.insert(lines, 1, L["|cffff6060Not used in routes|r (right-click: use it again)"]) end
        b.note = #lines > 0 and table.concat(lines, "\n") or nil
        if short then
          if not b.timer then
            b.timer = b:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
            b.timer:SetPoint("TOP", b, "BOTTOM", 0, -1)
            b.timer:SetShadowOffset(1, -1)
          end
          b.timer:SetText(short)
          b.timer:SetTextColor(docked and 0.4 or 1, docked and 1 or 0.9, docked and 0.4 or 0.6)
          b.timer:Show()
        end
        G.PoiSize(b, 18, 18)
      elseif p[1] == 6 then -- a dungeon's or raid's entrance: click for its map
        ns.SetIcon(b.icon, p.raid and "atlas:Raid" or "atlas:Dungeon", INSTANCE_ICON)
        b.stopTex, b.questID = nil, nil
        b.note = p.raid and L["Raid. Click: show its map"] or L["Dungeon. Click: show its map"]
        b.instance, b.wing = p.instance, p.wing
        G.PoiSize(b, 20, 20)
      elseif p[1] == 11 then -- a cave's or mine's way in (click: its map, when it has one: G.ShowCave)
        ns.SetIcon(b.icon, "atlas:CaveUnderground-Down", CAVE_ICON)
        b.stopTex, b.questID = CAVE_ICON, nil
        local map = p.cave and G.CaveArt(p.caveCont, p.cave)
        b.cave, b.caveCont = map and p.cave or nil, map and p.caveCont or nil
        b.note = map and L["Cave entrance. Click: show its map. Double-click: a stop there"]
          or L["Cave entrance. Double-click: a stop there"]
        G.PoiSize(b, 16, 16)
      elseif p[1] == 7 then -- a boss, in a dungeon's map
        ns.SetIcon(b.icon, BOSS_ICON)
        b.stopTex, b.questID = BOSS_ICON, nil
        b.note = (p.dead and L["|cff40ff40Defeated|r"] or p.next and L["|cffffd100Next|r"] or p.optional and L["Optional"] or "")
          .. "\n" .. (p.dead and L["Right-click: not defeated after all"] or L["Right-click: mark defeated"])
        b.bossKey, b.dead = p.bossKey, p.dead -- (right-click: its kill marked by hand, Nav.SetBossDead)
        local shift = G.IconHint({ kind = "boss", name = BossName(b.name), x = b.wx, y = b.wy, cont = b.level })
        if shift then b.note = b.note .. "\n" .. Format(L["Shift-click: %s"], shift) end
        G.PoiSize(b, p.next and 22 or 18, p.next and 22 or 18)
      elseif p[1] == 9 then -- stairs to another floor (a dungeon's), up or down
        ns.SetIcon(b.icon, p.up and "atlas:poi-door-up" or "atlas:poi-door-down",
          p.up and "Interface\\Buttons\\Arrow-Up-Up" or "Interface\\Buttons\\Arrow-Down-Up")
        b.stopTex, b.questID = nil, nil
        b.note = p.note
        -- (smaller, asked 2026-11-15: "stairs icons are too large"; 22 and 16 before Icon size's scale)
        G.PoiSize(b, p.next and 16 or 13, p.next and 16 or 13)
      elseif p[1] == 8 then -- a dungeon's way out, in its map
        ns.SetIcon(b.icon, "atlas:poi-door", EXIT_ICON)
        b.stopTex, b.questID = nil, nil
        b.note = L["Click: back out on the map"]
        b.exit = p.exit
        G.PoiSize(b, 18, 18)
      elseif p[1] == 5 then -- a capital on a continent's map: click for the city
        ns.SetIcon(b.icon, "atlas:poi-majorcity", "Interface\\Icons\\INV_Misc_Map02")
        b.icon:SetVertexColor(1, 1, 1)
        b.stopTex, b.questID = nil, nil
        b.note = L["Click: show the city"]
        b.cityMap = p.cityMap
        G.PoiSize(b, 20, 20)
      elseif p[1] == 1 then
        local state = not seen and "unknown" or (known[p[7]] and "known" or "unlearned")
        ns.SetIcon(b.icon, TAXI_ICON[state])
        b.stopTex = TAXI_ICON[state]
        b.note = state == "known" and L["Flight master (known)"] or state == "unlearned" and L["Flight master (not learned)"]
          or L["Flight master (open a flight map once to see which you know)"]
        G.PoiSize(b, 16, 16)
      elseif p[1] == 12 then -- a pin (Pins.lua): its icon; double-click for a stop, right-click to remove it
        local tex = ns.Pins.IconTexture(p.icon)
        ns.SetIcon(b.icon, tex)
        b.stopTex, b.questID = tex, nil
        b.pin = p.pin
        b.npc = G.PinNpcInfo(p.pin) -- (a pin from an NPC's search row: Shift-click offered to another addon first)
        b.note = p.floor and Format(p.pin.shipped and L["Shared pin, %s"] or L["Your pin, %s"], p.floor)
          or (p.pin.shipped and L["Shared pin"] or L["Your pin"])
        G.PoiSize(b, 18, 18)
      elseif p[1] == 16 then -- an NPC in the inside map shown (G.InteriorNpcs): its service's icon, else a small dot
        if p.npcIcon then
          ns.SetIcon(b.icon, p.npcIcon)
          b.icon:SetVertexColor(1, 1, 1)
        else
          ns.SetIcon(b.icon, G.NPC_DOT_TEXTURE)
          b.icon:SetVertexColor(G.NPC_DOT_COLOR[1], G.NPC_DOT_COLOR[2], G.NPC_DOT_COLOR[3])
        end
        b.stopTex, b.questID = p.npcIcon, nil
        b.npc = p.npc -- (Shift-click: another addon's, API.OnIconShiftClick)
        local shift = p.npc and G.IconHint(p.npc)
        b.note = shift and ((p.note and (p.note .. "\n") or "") .. Format(L["Shift-click: %s"], shift)) or p.note
        local u = G.PxUnits(poiLayer, p.npcIcon and G.NPC_ICON_PX or G.NPC_DOT_PX)
        G.PoiSize(b, u, u)
      elseif p[1] == 13 then -- the map pin (Import.MapPin): the game's waypoint diamond
        ns.SetIcon(b.icon, "atlas:Waypoint-MapPin-Untracked", "Interface\\TargetingFrame\\UI-RaidTargetingIcon_3")
        b.stopTex, b.questID = nil, nil
        b.mapPin = true
        b.note = L["Shift-click: link it in chat\nCtrl-click: remove it"]
        G.PoiSize(b, 20, 20)
      elseif p[1] == 4 then -- map layer mark (Layers.lua)
        ns.SetIcon(b.icon, p.icon, ns.Layers and ns.Layers.ICON.objectiveFallback)
        b.icon:SetVertexColor(p.r or 1, p.g or 1, p.b or 1)
        -- its icon for a stop made from it (a file; atlas art can't show in text)
        b.stopTex = (type(p.icon) == "number" or (type(p.icon) == "string" and not p.icon:find("^atlas:"))) and p.icon or nil
        b.note = p.note
        b.questID = p.questID
        b.preview = p.preview
        G.PoiSize(b, p.size or 14, p.size or 14)
      else
        ns.SetIcon(b.icon, "Interface\\Common\\Indicator-Yellow")
        b.stopTex = nil
        b.note = nil
        G.PoiSize(b, 12, 12)
      end
      if p[1] ~= 4 and p[1] ~= 16 then
        b.icon:SetVertexColor(1, 1, 1)
        b.questID = nil
      end
      b:SetAlpha(p.dim and 0.35 or 1)
      b.icon:SetShown(not p.under) -- (a dock under a stop: the stop's marker over it, its timer still under)
      b:ClearAllPoints()
      -- (a pin's, a city place's or a node's item's game icon: G.ICON_PX, on whole pixels)
      local exact = (p[1] == 12 and G.IsGameIcon(ns.Pins.IconTexture(p.icon)))
        or (p[1] == 4 and (p.city or p.exact) and G.IsGameIcon(p.icon))
      if exact then
        local u = G.PxUnits(poiLayer, G.ICON_PX)
        G.PoiSize(b, u, u)
        b:SetPoint("CENTER", poiLayer, "CENTER", G.SnapPoint(poiLayer, p[2], p[3]))
      else
        b:SetPoint("CENTER", poiLayer, "CENTER", p[2], p[3])
      end
      G.RoundIcon(b, b.icon, G.PoiGameIcon(p))
      b:Show()
    end
  end
  for i = nb + 1, #poiButtons do poiButtons[i]:Hide() end
  for i = nl + 1, #poiLabels do poiLabels[i]:Hide() end
end

-- The docks' countdowns set again on the buttons already placed: an icon refresh with nothing else changed
-- gathers and places the same icons, and the countdowns are the only live content (the 2026-10-07 draw
-- profile), so the gather is skipped and only they are reset (G.Update's icons, within ICON_FULL_REFRESH).
function G.RefreshDockTimers()
  for _, b in ipairs(poiButtons) do
    if b.dock and b:IsShown() then
      local short, _, docked = G.DockTimes(b.dock[1], b.dock[2])
      if short then
        if not b.timer then
          b.timer = b:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
          b.timer:SetPoint("TOP", b, "BOTTOM", 0, -1)
          b.timer:SetShadowOffset(1, -1)
        end
        b.timer:SetText(short)
        b.timer:SetTextColor(docked and 0.4 or 1, docked and 1 or 0.9, docked and 0.4 or 0.6)
        b.timer:Show()
      elseif b.timer then
        b.timer:Hide()
      end
    end
  end
end

-- The route's stairs in an underground city (asked 2026-10-06: a multi-floor plan for Undercity with stair indicators):
-- an icon, up or down, where the route changes floors (G.FloorChanges over its heights, as on a dungeon's map), the
-- next G.ROUTE_STAIRS of them. Added to `pois` (the map's icons) in view.
G.ROUTE_STAIRS = 3
function G.AddRouteStairs(pois, route, viewCont, cx, cy, rot, s, half)
  local n = 0
  for _, part in ipairs(route and route.parts or {}) do
    local l = part.zs and ns.CityLevels and ns.CityLevels[part.cont]
    if l and not l.instance then
      for _, c in ipairs(G.FloorChanges(part.pts, part.zs, G.ROUTE_STAIRS - n)) do
        local x, y = Geo.ToContinent(part.cont, c[1], c[2], viewCont)
        if x and y then
          local dx, dy = Geo.ScreenOffset(cx, cy, x, y)
          dx, dy = Geo.Rotate(dx * s, dy * s, rot)
          if math.abs(dx) <= half and math.abs(dy) <= half then
            pois[#pois + 1] = { 9, dx, dy, c[3] and L["Stairs up"] or L["Stairs down"], x, y, up = c[3], next = n == 0,
              note = c[3] and L["The route goes up to the floor above here"] or L["The route goes down to the floor below here"] }
          end
        end
        n = n + 1
      end
    end
    if n >= G.ROUTE_STAIRS then break end
  end
  -- (a building's or a capital's stairs, asked 2026-10-06: the icon on the stairs, Brill's inn, not by the stop:
  -- where the route takes a stairs road (Router.StairAt, source 6), each flight once, only near the view)
  local R = ns.Router
  if R and R.StairAt and route then
    local last, flight
    -- (the flight up or down as the route's floors go across it (fz), where it has them; else as its first piece reads)
    local function Way(fl)
      local p, up = fl.p, nil
      if fl.f1 and fl.f2 and math.abs(fl.f2 - fl.f1) >= 1 then up = fl.f2 > fl.f1 else up = fl.dir > 0 end
      p[4], p.up = up and L["Stairs up"] or L["Stairs down"], up
      p.note = up and L["The route goes up to the floor above here"] or L["The route goes down to the floor below here"]
    end
    G.EachSegmentNear(route, viewCont, cx, cy, half * 1.5 / s, function(x1, y1, x2, y2, kind, _stop, partCont, _along, f1, f2)
      local l = ns.CityLevels and ns.CityLevels[partCont]
      local st = not l and (kind == 0 or kind == nil) and R.StairAt(partCont, x1, y1, x2, y2)
      -- (one flight however its pieces read: stairs over stairs, an inn's cellar under its stairs up, can read the
      -- other way on a piece; the flight goes the way the route's floors go across it, coming down Brill's inn's read
      -- "up" by its first piece, 2026-10-06)
      local joined = st and last and last.st and last.x == x1 and last.y == y1
      -- (and across a landing to more stairs the same way, Turns.STAIRS_GAP: one flight, one icon, as the directions
      -- say it; Brill's inn's stairs, 2026-10-06)
      local landing = st and flight and flight.dir == st and flight.gap <= (ns.Turns and ns.Turns.STAIRS_GAP or 6)
      last = { x = x2, y = y2, st = st }
      if st then
        if joined or landing then
          flight.gap, flight.f2 = 0, f2 or flight.f2
          if flight.p then Way(flight) end
        else
          flight = { dir = st, gap = 0, f1 = f1, f2 = f2 }
        end
      elseif flight then
        flight.gap = flight.gap + math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2)
      end
      if not st or joined or landing then return end
      local dx, dy = Geo.ScreenOffset(cx, cy, x1, y1)
      dx, dy = Geo.Rotate(dx * s, dy * s, rot)
      if math.abs(dx) <= half and math.abs(dy) <= half then
        flight.p = { 9, dx, dy, nil, x1, y1, next = n == 0 }
        pois[#pois + 1] = flight.p
        Way(flight)
        n = n + 1
      end
    end)
  end
  return n
end

-- A stairs icon, up or down (a dungeon's stairs; a stop upstairs or in a cellar).
function G.SetStairsIcon(tex, up)
  ns.SetIcon(tex, up and "atlas:poi-door-up" or "atlas:poi-door-down",
    up and "Interface\\Buttons\\Arrow-Up-Up" or "Interface\\Buttons\\Arrow-Down-Up")
end
-- (asked 2026-10-06) a stop upstairs or in a cellar (Nav.StopFloor): its last yards dotted in this color, and its
-- marker with a stairs badge
G.STAIRS_COLOR = { 0.75, 0.55, 1 }
G.FLOOR_LEG_YD = 25

-- A walk being recorded (the road tools' Record, Record.lua's R.rec), on the level in view: its line so far as a drawn
-- road, its stairs (marked, and one still open up to the player) in the stairs' color. Only what's in view, and points
-- under ROAD_STEP_UI pixels apart as one (a walk is up to REC_MAX_POINTS: a line a point, zoomed out, cost a redraw
-- what another addon's 2500 lines did). How many lines.
function G.DrawRecording(cx, cy, rot, s, viewCont, half)
  local r = ns.Record and ns.Record.rec
  local pts = r and r.pts
  if not (pts and r.level == viewCont and #pts >= 4) then return 0 end
  local st, k = r.stairs, 1
  local open = r.stairOpen
  local edge = (half or 1e9) * 1.45 -- (the view's corners, turned heading-up)
  local step2 = G.ROAD_STEP_UI * G.ROAD_STEP_UI
  local lx, ly, lp
  local n = 0
  local last = #pts - 1
  for i = 1, last, 2 do
    local p = (i + 1) / 2
    local dx, dy = Geo.ScreenOffset(cx, cy, pts[i], pts[i + 1])
    local ax, ay = Geo.Rotate(dx * s, dy * s, rot)
    -- (the piece from the last point drawn to point p: on stairs when a mark's stretch holds it)
    while st[k + 1] and st[k + 1] < p do k = k + 2 end
    local stairs = (st[k] and st[k] <= p - 1 and p <= st[k + 1]) or (open and p - 1 >= open) or false
    if not lx then
      lx, ly, lp = ax, ay, stairs
    elseif i == last or stairs ~= lp or (ax - lx) ^ 2 + (ay - ly) ^ 2 >= step2 then
      if not ((lx < -edge and ax < -edge) or (lx > edge and ax > edge) or (ly < -edge and ay < -edge)
          or (ly > edge and ay > edge)) then
        AddSeg(lx, ly, ax, ay, stairs and G.STAIRS_COLOR or ROAD_COLORS[0], 3, 1, true)
        n = n + 1
      end
      lx, ly, lp = ax, ay, stairs
    end
  end
  return n
end

-- Marker buttons for the route's stops and the pending (not yet confirmed) ones.
local function StopPin(i)
  local b = stopPins[i]
  if b then return b end
  b = CreateFrame("Button", nil, keepLayer)
  b:SetSize(18, 18)
  b:SetFrameLevel(keepLayer:GetFrameLevel() + 2)
  b.icon = b:CreateTexture(nil, "OVERLAY")
  b.icon:SetAllPoints()
  b.floorBadge = b:CreateTexture(nil, "OVERLAY", nil, 2) -- (upstairs / downstairs)
  b.floorBadge:SetSize(12, 12)
  b.floorBadge:SetPoint("CENTER", b, "TOPRIGHT", -1, -1)
  b.floorBadge:Hide()
  b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  b:SetScript("OnClick", function(self, button)
    if button == "LeftButton" then -- (a dock's: Shift-click pastes its times in chat)
      if self.dock and IsShiftKeyDown and IsShiftKeyDown() then G.ShareDock(self.dock)
      elseif IsShiftKeyDown and IsShiftKeyDown() then G.ShareStopPin(self) end -- (a stop: a pin link in chat)
      if IsControlKeyDown and IsControlKeyDown() then G.CopyStopWay(self) end -- (a stop: its /way line to copy)
      return
    end
    G.AskRemove(self)
  end)
  b:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText(self.title, 1, 1, 1)
    if self.floor then
      GameTooltip:AddLine(self.floor > 0 and L["Upstairs: take the stairs inside"] or L["Downstairs: the stairs down inside"],
        G.STAIRS_COLOR[1], G.STAIRS_COLOR[2], G.STAIRS_COLOR[3])
    end
    if self.dock then -- (a zeppelin's or boat's dock: its timetable, as its own icon's)
      local _, lines = G.DockTimes(self.dock[1], self.dock[2])
      for _, l in ipairs(lines or {}) do GameTooltip:AddLine(l, 1, 0.82, 0) end
    end
    if (self.stopIndex or self.pendingIndex) and G.PadTipLine(GameTooltip, "remove") then GameTooltip:Show() return end
    if G.PadTipLine(GameTooltip) then GameTooltip:Show() return end -- (a ride's or detour's: the mouse's own)
    GameTooltip:AddLine(G.PinHint(self), 0.7, 0.7, 0.7)
    if G.PinStop(self) then
      GameTooltip:AddLine(L["Shift-click: link it in chat as a map pin"], 0.7, 0.7, 0.7)
      GameTooltip:AddLine(L["Ctrl + left-click: copy as a /way line"], 0.7, 0.7, 0.7)
    end
    if self.dock and G.DockShareText(self.dock[1], self.dock[2]) then
      GameTooltip:AddLine(L["Shift-click: paste its times in chat"], 0.7, 0.7, 0.7)
    end
    GameTooltip:Show()
  end)
  b:SetScript("OnLeave", GameTooltip_Hide)
  stopPins[i] = b
  return b
end

-- A route pin's stop (one of the route's or a pending one), not a ride's or a detour's: nil for those.
function G.PinStop(b)
  if b.learnNode or b.ride then return nil end
  if b.stopIndex then return ns.Nav.stops[b.stopIndex] end
  if b.pendingIndex then return pending[b.pendingIndex] end
  return nil
end

-- Shift + left-click on a stop (asked 2026-11-15 for 1.3.3: "share a destination's location as a map pin"): the pin
-- link a pin's Shift-click pastes (Import.PinTag: its level, spot, height and floor, its name and place), in the chat
-- box; whoever clicks it is offered it as a pin of their own (Import.OnPinLink). Not a stop's icon: a raid marker's
-- index, not an icon's (the pin's own default).
function G.StopPin(d)
  if not (d and d.x and d.y) then return nil end
  return { level = d.cont, x = d.x, y = d.y, z = d.z, down = d.down, name = d.name or L["Destination"] }
end
-- (asked 2026-11-16: "should share as a normal map pin location, not a azerothGPS share": the game's own map pin link,
-- "[Map Pin Location]", that anyone can click, AzerothGPS or not)
function G.ShareStopPin(b)
  local d = G.PinStop(b)
  local I = ns.Import
  if not (d and d.x and d.y and I and I.PointLink) then return false end
  return I.InsertLink(I.PointLink(d.cont, d.x, d.y))
end
-- Ctrl + left-click on a stop (asked 2026-11-09): its TomTom /way line, in a box to copy (Import.ShowCopyLine).
function G.CopyStopWay(b)
  local d = G.PinStop(b)
  if not d then return end
  local line = ns.Import.WayLine(d)
  if not line then
    ns.Print(L["no zone map covers that stop, so it has no /way line"])
    return
  end
  ns.Import.ShowCopyLine(line)
end

-- A route pin's right-click hint.
-- The controller in use (Pad.used): `action`'s line on `tip` ("A: add as a stop"), none for nil; true then, and the
-- tooltip's mouse lines are left out. False with the mouse in use.
function G.PadTipLine(tip, action)
  local P = ns.Pad
  if not (P and P.used) then return false end
  local key = action and P.Key(action)
  if key then
    local line = action == "remove" and L["%s: remove this stop"] or L["%s: add as a stop"]
    tip:AddLine(Format(line, P.ActionLabel(action)), 0.4, 0.8, 1)
  end
  return true
end
function G.PinHint(b)
  if b.learnNode then return L["Right-click: remove this detour (for this route)"] end
  if b.ride then
    return b.hop and L["Right-click: don't fly this connection (for this route)"] or L["Right-click: don't take this ride (for this route)"]
  end
  return L["Right-click: remove this stop"]
end
-- A ride's pin icon (Nav.RidePins' kinds; a teleport's, its item's or spell's).
local RIDE_ICON = { flight = TAXI_ICON.known, tram = "Interface\\Icons\\INV_Misc_Gear_01", lift = "Interface\\Icons\\INV_Misc_Gear_01" }
function G.RideIcon(p)
  if p.kind == "teleport" then
    local t = p.ride
    local tex = t.item and GetItemIcon and GetItemIcon(t.item)
    if not tex and t.spell and ns.SpellIcon then tex = ns.SpellIcon(t.spell) end
    return tex or "Interface\\Icons\\INV_Misc_Rune_01"
  end
  return RIDE_ICON[p.kind] or DOCK_ICON[p.kind] or TAXI_ICON.known
end

-- Draw the pins: route stops (solid) and pending stops (lighter, removable).
local function DrawStopPins(toScreen, viewCont)
  if G.Held() then -- (held by another addon: no pins)
    for _, b in ipairs(stopPins) do b:Hide() end
    return
  end
  local n = 0
  local half = canvas and canvas:GetWidth() / 2 or math.huge
  local function pin(d, title, pendingIndex, stopIndex)
    local x, y = Geo.ToContinent(d.cont, d.x, d.y, viewCont)
    if not x then return end
    local sx, sy = toScreen(x, y)
    if math.abs(sx) > half + 20 or math.abs(sy) > half + 20 then return end -- (off the map: not placed)
    n = n + 1
    local b = StopPin(n)
    b.icon:SetTexCoord(0, 1, 0, 1) -- (a reused pin: no round icon's crop left on it; an atlas sets its own after)
    if d.learnNode then -- (a flight master's detour: the map's own icon for it, as a stop made from a map icon)
      b.icon:SetTexture(TAXI_ICON.unlearned)
    elseif d.ride then -- (a ride the route takes: its icon where it's boarded)
      ns.SetIcon(b.icon, G.RideIcon(d))
    else
      b.icon:SetTexture(ns.Nav.StopIcon(d))
    end
    b.icon:SetAlpha(pendingIndex and 0.75 or 1)
    local fl = not (d.learnNode or d.ride) and ns.Nav.StopFloor(d) -- (upstairs or in a cellar: a stairs badge)
    if fl then G.SetStairsIcon(b.floorBadge, fl > 0) end
    b.floorBadge:SetShown(fl and true or false)
    b.floor = fl or nil
    b.title, b.pendingIndex, b.stopIndex, b.learnNode = title, pendingIndex, stopIndex, d.learnNode
    b.ride, b.hop, b.dock = d.ride, d.hop, d.dock
    if G.clickThrough then
      b.agpsMouse = true -- restored when click-through ends
      b:EnableMouse(false)
    else
      b:EnableMouse(true)
    end
    b:ClearAllPoints()
    if d.learnNode or d.ride then -- (where the map's icon is, its size: that icon, right-clickable)
      b:SetSize(16, 16)
      b:SetPoint("CENTER", G.markLayer, "CENTER", sx, sy)
    elseif G.IsGameIcon(ns.Nav.StopIcon(d)) then -- (a city place's or pin's icon: G.ICON_PX)
      local u = G.PxUnits(G.markLayer, G.ICON_PX)
      b:SetSize(u, u)
      b:SetPoint("BOTTOM", G.markLayer, "CENTER", G.SnapPoint(G.markLayer, sx, sy - 4))
    else
      b:SetSize(18, 18)
      b:SetPoint("BOTTOM", G.markLayer, "CENTER", sx, sy - 4)
    end
    -- (round with its ring as the icon it was made from, with Round icons on: asked 2026-11-16, "with double clicking
    -- and routing to a rounded icon, it 'selects' and shows a square icon instead"; a ride's or detour's art as it is)
    G.RoundIcon(b, b.icon, not (d.learnNode or d.ride) and ns.Nav.StopIcon(d) or nil)
    b:Show()
  end
  -- every stop's marker (the route is worked out and drawn only to the ones ahead, PlannedStops:
  -- the option; a marker costs next to nothing)
  local stops = ns.Nav.stops
  for i = 1, #stops do
    local d = stops[i]
    pin(d, d.name or (#stops > 1 and Format(L["Stop %d"], i) or L["Destination"]), nil, i)
  end
  for i, d in ipairs(pending) do
    pin(d, Format(L["New stop %d (not confirmed yet)"], i), i)
  end
  -- the detour to a flight master not learned yet (Nav.LearnOnRoute): its pin, removable
  local learn = ns.Nav.route and not ns.Nav.QuestPaused() and ns.Nav.LearnOnRoute(ns.Nav.route)
  for _, h in ipairs(learn or {}) do
    pin({ cont = h.cont, x = h.x, y = h.y, learnNode = h.node }, Format(L["Detour: learn the flight path at %s"], h.name))
  end
  -- the rides it takes (flights, boats, zeppelins, the tram, teleports): each removable from this route
  for _, p in ipairs(ns.Nav.route and ns.Nav.RidePins and ns.Nav.RidePins(ns.Nav.route) or {}) do
    pin(p, p.title)
  end
  for i = n + 1, #stopPins do stopPins[i]:Hide() end
end

-- Party and raid members on the map (option showParty): a dot each in their class's color, their
-- name when pointed at, only those in the map's view placed. Where they are comes through
-- G.party.io.members(): { { name, cont, x, y, class, raid }, ... } (the game's positions by default;
-- a private dev addon swaps in fake members to test this). Members offline are
-- left out: the game goes on giving where they logged out (probed 2026-10-03, a raid member gone
-- offline: UnitPosition still there, UnitIsConnected false), and their icon stayed there.
G.party = { io = {} }
G.PARTY_COLOR = { 0.4, 0.8, 1 }
function G.party.io.members()
  local out = {}
  local raid = IsInRaid and IsInRaid()
  for i = 1, raid and 40 or 4 do
    local u = (raid and "raid" or "party") .. i
    if UnitExists and UnitExists(u) and not (UnitIsUnit and UnitIsUnit(u, "player"))
        and not (UnitIsConnected and UnitIsConnected(u) == false) then
      local ok, x, y, _, inst = pcall(UnitPosition, u)
      if ok and x and y and not ns.IsSecret(x) and not ns.IsSecret(y) then
        local class
        if UnitClass then class = select(2, UnitClass(u)) end -- (its file name: MAGE; not `a and f()`, one value)
        out[#out + 1] = { name = UnitName and UnitName(u) or u, cont = inst, x = x, y = y, class = class, raid = raid,
          unit = u } -- (one of the game's group: the game's Minimap has its blip, G.DrawParty)
      end
    end
  end
  return out
end
local partyPins = {}
-- A class's icon on `tex`: the game's own (the atlas classicon-<class>), else the class sheet cut to
-- it (CLASS_ICON_TCOORDS); false when neither is there (old art missing here: a dot instead).
G.CLASS_SHEET = "Interface\\GLUES\\CHARACTERCREATE\\UI-CHARACTERCREATE-CLASSES"
function G.ClassIcon(tex, class)
  if not class then return false end
  local atlas = "classicon-" .. class:lower()
  tex.agpsSrc, tex.scaledFile = nil, nil
  if tex.SetAtlas and C_Texture and C_Texture.GetAtlasInfo and C_Texture.GetAtlasInfo(atlas) then
    tex:SetAtlas(atlas)
    tex.agpsSrc = "atlas:" .. atlas -- (drawn at its size once placed: G.ScaledIcon)
    return true
  end
  local tc = CLASS_ICON_TCOORDS and CLASS_ICON_TCOORDS[class]
  if tc and tex:SetTexture(G.CLASS_SHEET) ~= false then
    tex:SetTexCoord(tc[1], tc[2], tc[3], tc[4])
    return true
  end
  return false
end
-- `tex` cut to a circle (the game's portrait mask, as the map's round buttons); left square where
-- masks aren't there
G.ROUND_MASK = "Interface\\CharacterFrame\\TempPortraitAlphaMask"
function G.MakeRound(owner, tex)
  if not (owner.CreateMaskTexture and tex.AddMaskTexture) then return false end
  local mask = owner:CreateMaskTexture()
  mask:SetAllPoints(tex)
  mask:SetTexture(G.ROUND_MASK, "CLAMPTOBLACKADDITIVE", "CLAMPTOBLACKADDITIVE")
  tex:AddMaskTexture(mask)
  return true
end
-- Round icons (asked 2026-11-14: "all icons on the map from AzerothGPS are square, can we add an option in general to
-- use round icons instead? ... color appropriate rings for class trainers and gold rings as the default. Make this a
-- default setting"; `roundIcons`, Options > General, on by default): a game icon (G.IsGameIcon: Interface\Icons, a file
-- id) on the map or the minimap cut to a circle (G.ROUND_MASK) inside a ring of our own (Media\IconRing, coast.ring():
-- white, tinted), its border cropped (ROUND_CROP). The ring is the class's color for a class's icon (a class trainer's,
-- G.IconClass), else ROUND_RING_GOLD. Atlas art (docks, dungeons, the game's own round markers) is left as it is.
G.ICON_RING = "Interface\\AddOns\\AzerothGPS\\Media\\IconRing"
-- the ring drawn at each size, pixel for pixel (coast.py's RING_SIZES; one 64 px ring shrunk to 16 px broke up, a
-- screenshot 2026-11-14): the nearest to the icon's size on the screen
G.RING_SIZES = { 10, 12, 14, 16, 18, 20, 22, 24, 28, 32, 40, 48, 64 }
-- a party member's ring (asked 2026-11-14: "do the scaling change for the party icons as well"): the round icons'
-- ring drawn at its size (G.RingTexture), tinted the class's color; texture `t` on frame `owner`, sized already
function G.PartyRing(t, owner, r, g, b)
  local ring = G.RingTexture(t, owner)
  if t.ringTex ~= ring then
    t:SetTexture(ring)
    t.ringTex = ring
  end
  t:SetVertexColor(r, g, b, 1)
  t:SetAlpha(G.TextureLoaded(t) and 1 or 0)
end
-- The map's game icons drawn at each size they're shown at (asked 2026-11-16: "for all map icons and borders ...
-- render the icons to scale like we did for icon rings to look better"): Media\Icons\, made by iconscale.py from the
-- game's own art (Data/IconSizes.lua: the textures, each's largest size; bigger than that, the game's file is it). An
-- icon's texture as ns.SetIcon (or G.ClassIcon) set it (`agpsSrc`) swapped for the file nearest its size on the screen,
-- round (its border cropped as ROUND_CROP) when it's drawn round. A file the client doesn't know (added since the last
-- login: GetTextureFileID nil) is left out till then, the game's file instead.
function G.ScaledIconKey(src)
  local I = ns.IconSizes
  if not I or src == nil then return nil end
  if type(src) == "number" then return I.ids[src] end
  if type(src) ~= "string" then return nil end
  local k = src:lower():gsub("\\", "/")
  k = k:gsub("%.blp$", ""):gsub("^interface/", "")
  return I.files[k] and k or nil
end
function G.ScaledIconFile(src, px, round)
  local key = G.ScaledIconKey(src)
  if not key or not px then return nil end
  local I = ns.IconSizes
  local kind = I.files[key]
  local jpg, largest = kind:sub(1, 1) == "j", tonumber(kind:sub(2)) or 0
  local best, bd = nil, math.huge
  for _, n in ipairs(I.sizes) do
    local d = math.abs(n - px)
    if d < bd then best, bd = n, d end
  end
  if not best or best > largest then return nil end
  local r = round and jpg or false
  local base = key:gsub("^atlas:", "atlas_")
  base = base:gsub("[^%w_]", "_")
  return I.path .. base .. "_" .. best .. (r and "r" or "") .. (jpg and ".jpg" or ""), r
end
G.scaledMissing = {}
function G.ScaledIcon(owner, t, round)
  local src = t.agpsSrc
  local w = src ~= nil and t.GetWidth and t:GetWidth() or 0
  local file, r
  if w and w > 0 then
    file, r = G.ScaledIconFile(src, w * ns.PixelsPerUnit(owner.GetEffectiveScale and owner:GetEffectiveScale() or 1), round)
  end
  if file and G.scaledMissing[file] then file = nil end
  if not file then
    if t.scaledFile then ns.SetIcon(t, src) end -- (back to the game's own: bigger than the largest drawn)
    t.scaledRound = nil
    return false
  end
  if t.scaledFile ~= file then
    t:SetTexCoord(0, 1, 0, 1)
    t:SetTexture(file)
    if not G.TextureLoaded(t) then
      G.scaledMissing[file] = true
      ns.SetIcon(t, src)
      t.scaledRound = nil
      return false
    end
    t.scaledFile = file
  end
  t.scaledRound = r
  return true
end
function G.RingTexture(t, owner)
  local w = t.GetWidth and t:GetWidth() or 16
  local px = w * ns.PixelsPerUnit(owner.GetEffectiveScale and owner:GetEffectiveScale() or 1)
  local best, bd = 64, math.huge
  for _, n in ipairs(G.RING_SIZES) do
    local d = math.abs(n - px)
    if d < bd then best, bd = n, d end
  end
  return G.ICON_RING .. best
end
G.ROUND_RING_GOLD = { 1, 0.8, 0.3 }
G.ROUND_CROP = 0.07
G.CLASS_RING = { -- (RAID_CLASS_COLORS where the game has it)
  WARRIOR = { 0.78, 0.61, 0.43 }, PALADIN = { 0.96, 0.55, 0.73 }, HUNTER = { 0.67, 0.83, 0.45 },
  ROGUE = { 1, 0.96, 0.41 }, PRIEST = { 1, 1, 1 }, SHAMAN = { 0, 0.44, 0.87 }, MAGE = { 0.25, 0.78, 0.92 },
  WARLOCK = { 0.53, 0.53, 0.93 }, DRUID = { 1, 0.49, 0.04 },
}
-- the class whose icon `tex` is (Layers.CITY_ICONS' class words: the city places', Pins.NpcIcon's trainers'), or nil
function G.IconClass(tex)
  if type(tex) ~= "string" then return nil end
  local Lay = ns.Layers
  if not G.iconClasses and Lay and Lay.CITY_ICONS then
    G.iconClasses = {}
    for _, e in ipairs(Lay.CITY_ICONS) do
      local class = e[1]:upper()
      if G.CLASS_RING[class] then G.iconClasses[e[2]:lower()] = class end
    end
  end
  return G.iconClasses and G.iconClasses[tex:lower()] or nil
end
function G.RingColor(tex)
  local class = G.IconClass(tex)
  if class then
    local c = RAID_CLASS_COLORS and RAID_CLASS_COLORS[class]
    if c and c.r then return c.r, c.g, c.b end
    local k = G.CLASS_RING[class]
    return k[1], k[2], k[3]
  end
  local g = G.ROUND_RING_GOLD
  return g[1], g[2], g[3]
end
function G.RoundIconsOn()
  local st = ns.settings and ns.settings.gps
  return not st or st.roundIcons ~= false
end
-- texture `t` (on frame `owner`, showing `icon`) round with its ring, or square as before; true when round
function G.RoundIcon(owner, t, icon)
  local on = G.RoundIconsOn() and G.IsGameIcon(icon) and owner.CreateMaskTexture and t.AddMaskTexture
  G.ScaledIcon(owner, t, on) -- (drawn at its size: G.ScaledIcon)
  if not on then
    if t.roundOn then t:RemoveMaskTexture(t.roundMask) t.roundOn = nil end
    if t.ring then t.ring:Hide() end
    return false
  end
  if not t.roundMask then
    t.roundMask = owner:CreateMaskTexture()
    t.roundMask:SetTexture(G.ROUND_MASK, "CLAMPTOBLACKADDITIVE", "CLAMPTOBLACKADDITIVE")
    t.ring = owner:CreateTexture(nil, "OVERLAY")
  end
  local ring = G.RingTexture(t, owner)
  if t.ringTex ~= ring then
    t.ring:SetTexture(ring)
    t.ringTex = ring
  end
  t.roundMask:ClearAllPoints()
  t.roundMask:SetAllPoints(t)
  if not t.roundOn then t:AddMaskTexture(t.roundMask) t.roundOn = true end
  local k = t.scaledRound and 0 or G.ROUND_CROP -- (a round file's border is cropped already)
  t:SetTexCoord(k, 1 - k, k, 1 - k)
  t.ring:ClearAllPoints()
  t.ring:SetAllPoints(t)
  t.ring:SetVertexColor(G.RingColor(icon))
  -- (a ring file the client doesn't know yet, added since the last login: drawn as the game's green square; hidden
  -- instead, the icon round without it; GetTextureFileID is nil for a missing file, 2026-11-14)
  t.ring:SetShown(G.TextureLoaded(t.ring))
  return true
end
function G.TextureLoaded(t)
  if not t.GetTextureFileID then return true end
  local ok, id = pcall(t.GetTextureFileID, t)
  return not ok or id ~= nil
end
-- a minimap icon `t` hidden with its ring (a texture on the minimap's frame, not a child of `t`: hidden alone, the
-- empty rings stayed where the icons were as the player walked, a video 2026-11-14)
function G.HideIcon(t)
  t:Hide()
  if t.ring then t.ring:Hide() end
end
-- the game icon POI `p` shows (a pin's, a layer mark's, an NPC's), or nil
function G.PoiGameIcon(p)
  local tex
  if p[1] == 12 then tex = ns.Pins and ns.Pins.IconTexture(p.icon)
  elseif p[1] == 4 then tex = p.icon
  elseif p[1] == 16 then tex = p.npcIcon end
  return G.IsGameIcon(tex) and tex or nil
end
function G.DrawParty(cx, cy, rot, s, viewCont)
  local n = 0
  if S().showParty ~= false and not G.Held() and canvas then
    local half = canvas:GetWidth() / 2
    local ok, list = pcall(G.party.io.members)
    -- (as the minimap square, asked 2026-11-17: "party member icons don't show on our square minimap": none were drawn
    -- there, left to the game's Minimap over it, which has no blip for members not in the game's group, the dev addon's
    -- fake ones. Now ours, but not for a member read from a unit while the ground is hidden ("ground"): its own blip is
    -- over the map there, ours under it a double. Under the all-clear mask ("mask") the blips may be clipped: ours.)
    local square = G.MinimapMode() and G.MinimapHideMode() == "ground"
    for _, m in ipairs(ok and list or {}) do
      local x, y
      if not (square and m.unit) then x, y = Geo.ToContinent(m.cont, m.x, m.y, viewCont) end
      local sx, sy
      if x and y then
        local dx, dy = Geo.ScreenOffset(cx, cy, x, y)
        sx, sy = Geo.Rotate(dx * s, dy * s, rot)
      end
      if sx and math.abs(sx) <= half and math.abs(sy) <= half then
        n = n + 1
        local b = partyPins[n]
        if not b then
          b = CreateFrame("Button", nil, keepLayer)
          b:SetSize(16, 16)
          b:SetFrameLevel(keepLayer:GetFrameLevel() + 1)
          b.dot = b:CreateTexture(nil, "ARTWORK") -- (the class's icon, or its color, cut round)
          b.dot:SetAllPoints()
          b.edge = b:CreateTexture(nil, "OVERLAY") -- (the ring in the class's color over it: G.PartyRing)
          b.edge:SetAllPoints()
          G.MakeRound(b, b.dot)
          b:SetScript("OnEnter", function(self)
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:SetText(self.name or "?", 1, 1, 1)
            GameTooltip:AddLine(self.raid and L["Raid member"] or L["Party member"], 0.7, 0.7, 0.7)
            GameTooltip:AddLine(L["Right-click: ask for their route"], 0.8, 0.8, 0.8)
            GameTooltip:Show()
          end)
          -- (asked 2026-10-06: request a route in a party) right-click: ask them for theirs, after a yes here
          b:RegisterForClicks("RightButtonUp")
          b:SetScript("OnClick", function(self, button)
            if button == "RightButton" and self.name then G.AskMemberForRoute(self.name) end
          end)
          b:SetScript("OnLeave", GameTooltip_Hide)
          partyPins[n] = b
        end
        local c = RAID_CLASS_COLORS and m.class and RAID_CLASS_COLORS[m.class]
        local r, g, bl = c and c.r or G.PARTY_COLOR[1], c and c.g or G.PARTY_COLOR[2], c and c.b or G.PARTY_COLOR[3]
        local icon = G.ClassIcon(b.dot, m.class)
        if not icon then b.dot:SetColorTexture(r, g, bl, 1) end
        b.name, b.raid = m.name, m.raid
        b:ClearAllPoints()
        -- (the class icon at G.ICON_PX and the ring round it, on whole pixels; times the map icons' size, Icon size,
        -- as the other icons: asked 2026-11-14, "party and raid icon scaling still looks off")
        local u = G.PxUnits(G.markLayer, math.floor((G.ICON_PX + 4) * G.PoiScale() + 0.5))
        b:SetSize(u, u)
        G.PartyRing(b.edge, b, r, g, bl)
        G.ScaledIcon(b, b.dot, false)
        b:SetPoint("CENTER", G.markLayer, "CENTER", G.SnapPoint(G.markLayer, sx, sy)) -- (each redraw: the marks' anchor)
        b:Show()
      end
    end
  end
  for i = n + 1, #partyPins do partyPins[i]:Hide() end
  return n
end
---------------------------------------------------------------------------
-- The route on the game's minimap (asked 2026-10-06: "overlay route stuff in game minimap too"): the route's lines
-- around the player and the next stop's marker, clipped to the minimap (round, or square where the UI makes it so),
-- the marker on its edge while the stop is further. Drawn again only when something it shows changed (asked
-- 2026-10-06: the route unchanged, not redrawn): the player moved half a minimap pixel, the minimap turned or zoomed,
-- or the route did (`mm.draws` counts the times). Option `minimapRoute`. Only the way to the next stop, on the level the
-- player is on (asked 2026-11-05, down in Undercity: the next stops' ways out of the city and their paths on the land
-- over it were drawn over that one in the same color; the map draws them in their stops' colors or faint), and none
-- while the route waits in the stop's quest area (Nav.QuestPaused, as the map). While the route is dropped to be worked
-- out again (Nav.Invalidate: a background search finished), the last one drawn for the same stop stays (asked
-- 2026-11-07, a recording in Ban'ethil Hollow: the line and the stop's marker flickered off between the map's or the
-- arrow window's calls of Nav.Route, the map closed).
---------------------------------------------------------------------------
G.MINIMAP_ROUTE_HZ = 20
G.MINIMAP_ROUTE_COLOR = { 0.3, 0.8, 1 }
G.MINIMAP_ROUTE_WIDTH = 3
local mm = { lines = {}, used = 0, draws = 0 }
G.minimapRoute = mm
-- World (x, y) on the minimap, from its middle (the player at px, py), in its units: `yards` across `width`, turned
-- by `facing` when the minimap turns (Layers.MinimapOffset the other way round).
function G.MinimapPoint(px, py, x, y, yards, width, facing)
  local dX, dY, f, k = x - px, y - py, facing or 0, width / yards
  return (dX * math.sin(f) - dY * math.cos(f)) * k, (dX * math.cos(f) + dY * math.sin(f)) * k
end
-- A segment clipped to the circle of radius `r` around (0, 0): its ends, or nil when it's all outside.
function G.ClipCircle(x1, y1, x2, y2, r)
  local dx, dy = x2 - x1, y2 - y1
  local a = dx * dx + dy * dy
  local c = x1 * x1 + y1 * y1 - r * r
  if a == 0 then
    if c <= 0 then return x1, y1, x2, y2 end
    return nil
  end
  local b = 2 * (x1 * dx + y1 * dy)
  local disc = b * b - 4 * a * c
  if disc < 0 then return nil end
  local sq = math.sqrt(disc)
  local t0, t1 = math.max(0, (-b - sq) / (2 * a)), math.min(1, (-b + sq) / (2 * a))
  if t0 >= t1 then return nil end
  return x1 + dx * t0, y1 + dy * t0, x1 + dx * t1, y1 + dy * t1
end
local function MinimapHide(from)
  for i = from, #mm.lines do mm.lines[i]:Hide() end
end
-- The game's minimap square (a bug report, 2026-10-30: under EllesmereUI's square minimap the route stopped at a circle
-- inside it): the option `minimapShape` ("round", "square"), else what the minimap addon says (GetMinimapShape, the
-- convention LibDBIcon reads), else the mask last put on the minimap (G.minimapMask, watched from login,
-- G.InitMinimapRoute): anything but the game's round one is square (EllesmereUI masks it square and defines no
-- GetMinimapShape).
G.ROUND_MINIMAP_MASKS = { [186178] = true, ["textures\\minimapmask"] = true }
function G.OnMinimapMask(tex)
  G.minimapMask = tex
  mm.route, mm.placed = nil, nil
end
function G.MinimapSquare()
  if G.mmState and G.mmState.applied then return true end -- (the GPS map as the minimap: a square)
  local o = S().minimapShape
  if o == "square" then return true end
  if o == "round" then return false end
  if GetMinimapShape then return GetMinimapShape() == "SQUARE" end
  local m = G.minimapMask
  if m == nil then return false end
  return not G.ROUND_MINIMAP_MASKS[type(m) == "string" and m:lower() or m]
end
function G.UpdateMinimapRoute(force)
  local f = mm.frame
  if not f then return 0 end
  local N = ns.Nav
  local r = N.route
  if r then
    mm.last, mm.lastDest = r, N.dest
  elseif N.dest and mm.lastDest == N.dest and not N.paused then
    r = mm.last -- (being worked out again: the last one drawn meanwhile; paused: none)
  end
  local px, py, cont = Geo.PlayerWorld()
  -- (not for the dev tools' simulated player: the game's minimap is round the real one)
  if (S().minimapRoute == false and not G.mmState.standIn) or not (r and px and N.dest) or N.RedAsking() or Geo.override or G.MinimapTaken() then
    MinimapHide(1)
    mm.stop:Hide()
    mm.route, mm.used = nil, 0
    if not N.dest then mm.last, mm.lastDest = nil, nil end
    return 0
  end
  local width = Minimap:GetWidth() or 140
  local yards = ns.Layers and ns.Layers.MinimapYards and ns.Layers.MinimapYards() or 400
  local facing = (GetCVar and GetCVar("rotateMinimap") == "1") and Geo.Facing() or 0
  local step = yards / width * 0.5 -- (half a minimap pixel, in yards)
  local square = G.MinimapSquare()
  local level, paused = N.PlayerLevel(cont), N.QuestPaused()
  if not force and mm.route == r and mm.pts == r.pts and mm.dest == N.dest and mm.yards == yards and mm.width == width
      and math.abs(mm.px - px) < step and math.abs(mm.py - py) < step and math.abs(mm.facing - facing) < 0.005
      and mm.square == square and mm.level == level and mm.paused == paused then
    return mm.used -- (nothing it shows changed)
  end
  local t0 = ns.PerfStart and ns.PerfStart()
  mm.route, mm.pts, mm.dest, mm.yards, mm.width, mm.px, mm.py, mm.facing = r, r.pts, N.dest, yards, width, px, py, facing
  mm.square, mm.level, mm.paused = square, level, paused
  mm.draws = mm.draws + 1
  local rad = width / 2 - 1
  local n = 0
  local col = G.MINIMAP_ROUTE_COLOR
  local function Piece(x1, y1, x2, y2, kind, c)
    local ax, ay = G.MinimapPoint(px, py, x1, y1, yards, width, facing)
    local bx, by = G.MinimapPoint(px, py, x2, y2, yards, width, facing)
    local cx1, cy1, cx2, cy2
    if square then
      cx1, cy1, cx2, cy2 = G.ClipSeg(ax, ay, bx, by, rad)
    else
      cx1, cy1, cx2, cy2 = G.ClipCircle(ax, ay, bx, by, rad)
    end
    if not cx1 then return end
    n = n + 1
    local l = mm.lines[n]
    if not l then
      l = f:CreateLine(nil, "OVERLAY")
      l:SetThickness(G.MINIMAP_ROUTE_WIDTH)
      mm.lines[n] = l
    end
    l:SetColorTexture(c[1], c[2], c[3], kind == 0 and 0.95 or 0.6) -- (off the roads: fainter)
    l:SetStartPoint("CENTER", f, cx1, cy1)
    l:SetEndPoint("CENTER", f, cx2, cy2)
    l:Show()
  end
  -- (only the route's chunks within the minimap's reach: G.EachSegmentNear)
  G.EachSegmentNear(r, cont, px, py, yards, function(x1, y1, x2, y2, kind, stop, partCont, _, _, _, part, i)
    if paused or (stop or 1) ~= 1 or partCont ~= level then return end -- (the way to the next stop, on this level)
    -- (the other faction's territory: red, Nav.HostileSpans; asked 2026-11-14, on the minimap square too)
    local spans = N.HostileSpans and N.HostileSpans(part, i)
    if spans then
      N.EachHostilePiece(spans, function(t1, t2, hostile)
        Piece(x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1, x1 + (x2 - x1) * t2, y1 + (y2 - y1) * t2, kind,
          hostile and N.HOSTILE_COLOR or col)
      end)
    else
      Piece(x1, y1, x2, y2, kind, col)
    end
  end)
  MinimapHide(n + 1)
  mm.used = n
  -- the next stop's marker: where it is, or on the edge toward it
  local d = N.dest
  local x, y = Geo.ToContinent(d.cont, d.x, d.y, cont)
  if x then
    local sx, sy = G.MinimapPoint(px, py, x, y, yards, width, facing)
    local edge = rad - 6
    local dist = math.sqrt(sx * sx + sy * sy)
    if square then dist = math.max(math.abs(sx), math.abs(sy)) end
    if dist > edge then sx, sy = sx * edge / dist, sy * edge / dist end
    mm.stop:SetTexture(N.StopIcon(d))
    mm.stop:ClearAllPoints()
    mm.stop:SetPoint("CENTER", f, "CENTER", sx, sy)
    mm.stop:Show()
    mm.stop.tipX, mm.stop.tipY, mm.stop.tipName = sx, sy, d.name or L["Destination"]
  else
    mm.stop:Hide()
  end
  if t0 then ns.PerfEnd("minimap route", t0) end
  return n
end
---------------------------------------------------------------------------
-- The map's icons on the game's minimap too (issue #10: "all icons that are set to show"): the map layers' marks
-- (quests, herbs and ore known, city places), the player's pins, docks, dungeon and cave entrances and party members,
-- each under its own show setting, on the minimap frame as the route is (G.MinimapPoint, turned with rotateMinimap),
-- only those wholly inside its circle (or square). Never the game's own blips (they can't be read) and never NPCs.
-- Gathered (in world yards, a box `yards` round the player: twice the minimap) when what they show changed
-- (Layers.version, G.drawVersion, the show settings), the player left half of that box, or every ICON_FULL_REFRESH;
-- placed again only when the gathered set changed, the player moved half a minimap pixel, the minimap turned or
-- zoomed, or a party member moved (`mm.iconDraws` counts the times). Option `minimapIcons` (off by default).
---------------------------------------------------------------------------
mm.icons, mm.partyIcons, mm.iconDraws, mm.iconsUsed = {}, {}, 0, 0
G.MINIMAP_ICON_SIZE = 12 -- (a mark's own size is the map's, scaled by this over 16)
-- What the map would show near (px, py) on `cont` within `reach` yards, by its show settings: { { x, y, icon,
-- fallback, size, r, g, b, a, name = (its hover name, G.MinimapTipText), city = (a city place) }, ... } in `cont`
-- coordinates (party members apart: G.MinimapParty).
function G.MinimapIconList(px, py, cont, reach)
  local st = S()
  local out = {}
  local function near(x, y) return x and math.abs(x - px) <= reach and math.abs(y - py) <= reach end
  local function add(x, y, icon, fallback, size, r, g, b, a, name, city)
    if near(x, y) then
      out[#out + 1] = { x, y, icon, fallback, size, r or 1, g or 1, b or 1, a or 1, name = name, city = city }
    end
  end
  local yours, shared = L["Your pin"], L["Shared pin"] -- (L: the layers' below)
  local L, N = ns.Layers, ns.Nav
  if L and L.Marks then
    local level = N.PlayerLevel and N.PlayerLevel(cont) or nil
    for _, m in ipairs(L.Marks(cont, px, py, reach, { Geo.PlayerMap() }, level)) do
      add(m[1], m[2], m[3], L.ICON and L.ICON.objectiveFallback, (m[6] or 14) * G.MINIMAP_ICON_SIZE / 16, m[7], m[8], m[9],
        nil, m[4], m[14])
    end
  end
  if st.showCustomPins ~= false and ns.Pins and ns.db then
    for _, pin in ipairs(ns.Pins.All()) do
      if pin.level and pin.x and pin.y then
        local x, y = Geo.ToContinent(pin.level, pin.x, pin.y, cont)
        add(x, y, ns.Pins.IconTexture(pin.icon), nil, G.MINIMAP_ICON_SIZE + 2, nil, nil, nil, nil,
          pin.name or (pin.shipped and shared or yours))
      end
    end
  end
  local base = Geo.Base(cont)
  if st.poiPoi ~= false then
    for _, t in ipairs(ns.Transports or {}) do
      if DOCK_ICON[t[8]] and N.TransportUsable(t) then
        local dim = not N.RideAllowed(t) and 0.35 or nil
        for side = 1, 2 do
          local o = side == 1 and 0 or 3
          if t[1 + o] == base then
            local to = ns.RideEndName(t, side == 1 and 2 or 1) -- (as the map names it)
            add(t[2 + o], t[3 + o], DOCK_ICON[t[8]], nil, G.MINIMAP_ICON_SIZE + 2, nil, nil, nil, dim,
              DOCK_NAME[t[8]] and Format(DOCK_NAME[t[8]], to or "?") or to)
          end
        end
      end
    end
  end
  if st.layerInstances ~= false then
    for _, e in ipairs(G.InstanceEntrances(base)) do
      add(e.x, e.y, e.raid and "atlas:Raid" or "atlas:Dungeon", INSTANCE_ICON, G.MINIMAP_ICON_SIZE + 4, nil, nil, nil, nil, e.name)
    end
  end
  if st.layerCaves ~= false then
    for _, e in ipairs(G.CaveEntrances(base)) do
      add(e.x, e.y, "atlas:CaveUnderground-Down", CAVE_ICON, G.MINIMAP_ICON_SIZE, nil, nil, nil, nil, e.name)
    end
  end
  return out
end
-- Party and raid members on `cont` (option showParty), as the map's: { { x, y, class, name }, ... }.
function G.MinimapParty(cont)
  local out = {}
  if S().showParty == false then return out end
  local ok, list = pcall(G.party.io.members)
  for _, m in ipairs(ok and list or {}) do
    local x, y = Geo.ToContinent(m.cont, m.x, m.y, cont)
    if x and y then out[#out + 1] = { x, y, m.class, m.name } end
  end
  return out
end
-- Whether a spot `size` across at (sx, sy) from the minimap's middle is wholly on it (radius `rad`).
function G.OnMinimap(sx, sy, size, rad, square)
  local r = rad - size / 2
  if square then return math.abs(sx) <= r and math.abs(sy) <= r end
  return sx * sx + sy * sy <= r * r
end
function G.HideMinimapIcons()
  for _, t in ipairs(mm.icons) do G.HideIcon(t) end
  for _, p in ipairs(mm.partyIcons) do p.edge:Hide() p.dot:Hide() end
  mm.iconsUsed, mm.iconList, mm.partyList, mm.gather, mm.placed = 0, nil, nil, nil, nil
end
function G.UpdateMinimapIcons(force)
  local f = mm.frame
  if not f then return 0 end
  local N = ns.Nav
  local px, py, cont = Geo.PlayerWorld()
  local st = S()
  -- (standing in for the map on the square, the map being in the world map: its icons there whatever the option)
  if (st.minimapIcons ~= true and not G.mmState.standIn) or not px or Geo.override or G.MinimapTaken() then
    G.HideMinimapIcons()
    return 0
  end
  local width = Minimap:GetWidth() or 140
  local yards = ns.Layers and ns.Layers.MinimapYards and ns.Layers.MinimapYards() or 400
  local facing = (GetCVar and GetCVar("rotateMinimap") == "1") and Geo.Facing() or 0
  local step = yards / width * 0.5 -- (half a minimap pixel, in yards)
  local now = GetTime()
  -- gathered again: what they show changed, the player left the box's middle half, or the full refresh is due
  local shows = table.concat({ tostring(cont), tostring(ns.Layers and ns.Layers.version), tostring(G.drawVersion),
    tostring(st.layerQuests), tostring(st.layerCity), tostring(st.layerHerbs), tostring(st.layerOre),
    tostring(st.showCustomPins), tostring(st.poiPoi), tostring(st.layerInstances), tostring(st.layerCaves),
    tostring(N and N.PlayerLevel and N.PlayerLevel(cont)), tostring(Geo.PlayerMap()) }, ":")
  local g = mm.gather
  local changed = force
  if force or not g or g.shows ~= shows or g.yards ~= yards or math.abs(g.x - px) > yards / 2 or math.abs(g.y - py) > yards / 2
      or now - g.at >= G.ICON_FULL_REFRESH then
    local list = G.MinimapIconList(px, py, cont, yards)
    local keys = {}
    for i, e in ipairs(list) do keys[i] = string.format("%.1f,%.1f,%s,%.2f", e[1], e[2], tostring(e[3]), e[9]) end
    local key = table.concat(keys, ";")
    if not g or g.key ~= key then changed = true end
    mm.gather = { shows = shows, yards = yards, x = px, y = py, at = now, key = key }
    mm.iconList = list
  end
  -- party members: where they are now, placed again when one moved half a minimap pixel
  local party = G.MinimapParty(cont)
  local was = mm.partyList
  if not was or #was ~= #party then
    changed = true
  else
    for i, m in ipairs(party) do
      local o = was[i]
      if o[3] ~= m[3] or math.abs(o[1] - m[1]) >= step or math.abs(o[2] - m[2]) >= step then changed = true break end
    end
  end
  local p = mm.placed
  local square = G.MinimapSquare()
  if not changed and p and p.yards == yards and p.width == width and math.abs(p.px - px) < step
      and math.abs(p.py - py) < step and math.abs(p.facing - facing) < 0.005 and p.square == square then
    return mm.iconsUsed -- (nothing it shows changed)
  end
  local t0 = ns.PerfStart and ns.PerfStart()
  mm.placed = { yards = yards, width = width, px = px, py = py, facing = facing, square = square }
  mm.partyList = party
  mm.iconDraws = mm.iconDraws + 1
  local rad = width / 2 - 1
  local n = 0
  for _, e in ipairs(mm.iconList or {}) do
    local sx, sy = G.MinimapPoint(px, py, e[1], e[2], yards, width, facing)
    if G.OnMinimap(sx, sy, e[5], rad, square) then
      n = n + 1
      local t = mm.icons[n]
      if not t then
        t = f:CreateTexture(nil, "ARTWORK")
        mm.icons[n] = t
      end
      ns.SetIcon(t, e[3], e[4])
      t:SetVertexColor(e[6], e[7], e[8])
      t:SetAlpha(e[9])
      t:SetSize(e[5], e[5])
      t:ClearAllPoints()
      t:SetPoint("CENTER", f, "CENTER", sx, sy)
      t:Show()
      t.tipX, t.tipY, t.tipE = sx, sy, e -- (named on hover: G.MinimapTipAt)
      if G.RoundIcon(f, t, e[3]) then t.ring:SetAlpha(e[9]) end
    end
  end
  for i = n + 1, #mm.icons do G.HideIcon(mm.icons[i]) end
  local np = 0
  local size = G.MINIMAP_ICON_SIZE + 2
  for _, m in ipairs(party) do
    local sx, sy = G.MinimapPoint(px, py, m[1], m[2], yards, width, facing)
    if G.OnMinimap(sx, sy, size, rad, square) then
      np = np + 1
      local b = mm.partyIcons[np]
      if not b then -- (as the map's: the class's icon in a ring of its color, cut round)
        b = { edge = f:CreateTexture(nil, "OVERLAY"), dot = f:CreateTexture(nil, "ARTWORK") }
        b.edge:SetSize(size, size)
        b.dot:SetAllPoints(b.edge)
        G.MakeRound(f, b.dot)
        mm.partyIcons[np] = b
      end
      local c = RAID_CLASS_COLORS and m[3] and RAID_CLASS_COLORS[m[3]]
      local r, gr, bl = c and c.r or G.PARTY_COLOR[1], c and c.g or G.PARTY_COLOR[2], c and c.b or G.PARTY_COLOR[3]
      if not G.ClassIcon(b.dot, m[3]) then b.dot:SetColorTexture(r, gr, bl, 1) end
      G.PartyRing(b.edge, f, r, gr, bl)
      G.ScaledIcon(f, b.dot, false)
      b.edge:ClearAllPoints()
      b.edge:SetPoint("CENTER", f, "CENTER", sx, sy)
      b.edge:Show()
      b.dot:Show()
      b.tipX, b.tipY, b.tipName = sx, sy, m[4]
    end
  end
  for i = np + 1, #mm.partyIcons do mm.partyIcons[i].edge:Hide() mm.partyIcons[i].dot:Hide() end
  mm.iconsUsed = n + np
  if t0 then ns.PerfEnd("minimap icons", t0) end
  return n + np
end
function G.InitMinimapRoute()
  if mm.frame or not Minimap then return end
  local f = CreateFrame("Frame", nil, Minimap)
  f:SetAllPoints(Minimap)
  f:SetFrameLevel((Minimap:GetFrameLevel() or 1) + 4)
  mm.frame = f
  -- (the mask a minimap addon puts on it from now: G.MinimapSquare; drawn again at once)
  if hooksecurefunc and Minimap.SetMaskTexture and not G.clone then
    hooksecurefunc(Minimap, "SetMaskTexture", function(_, tex) G.OnMinimapMask(tex) end)
  end
  mm.stop = f:CreateTexture(nil, "OVERLAY")
  mm.stop:SetSize(14, 14)
  mm.stop:Hide()
  local since = 0
  f:SetScript("OnUpdate", function(_, dt)
    since = since + dt
    if since < 1 / G.MINIMAP_ROUTE_HZ then return end
    since = 0
    local ok, err = pcall(G.UpdateMinimapRoute)
    if not ok then G.LogError("minimap route", err) end
    ok, err = pcall(G.UpdateMinimapIcons)
    if not ok then G.LogError("minimap icons", err) end
  end)
  G.InitMinimapTips()
end
---------------------------------------------------------------------------
-- Our icons on the minimap named on hover (asked 2026-11-14: "on the minimap support mouse over for our icons to just
-- show the NPC name. For example "Koma (banker)" in org when mousing over the bank but also do this for all icons we
-- put on the map, just no "Double-click: add as a stop" line"): the name alone, an NPC's "Name (Title)", a city
-- place's NPC there (G.PlaceNpc). The game's Minimap takes the mouse (pings, its blips' tooltips) and lies over the
-- map's buttons as the minimap square, so nothing of ours takes it: while the cursor is over the Minimap (its OnEnter
-- and OnLeave, hooked) a hidden frame hit-tests the cursor MINIMAP_TIP_HZ times a second against the icons placed (the
-- map's buttons as the square, else our textures on the game's minimap) and shows our own tooltip by it; nothing runs
-- otherwise. The game's own tooltip over the minimap (a blip's) wins.
---------------------------------------------------------------------------
G.MINIMAP_TIP_HZ = 20
-- An NPC as the minimap names it: "Koma (Banker)", the game's title as it is; the name alone with none.
function G.NpcLabel(name, title)
  if title and title ~= "" then return string.format("%s (%s)", name, title) end
  return name
end
-- The NPC at a city place (`name`, "Orgrimmar Bank", "Bank": a shipped one or a guard's) at (x, y) on `cont`: the
-- nearest shipped NPC within PLACE_NPC_YD offering what it's named for (a banker at a bank: PLACE_NPC_SVC's services,
-- else a title the name holds, "Mining Trainer", before a trainer of what it holds: a mage trainer's, not the portal
-- trainer by him), or nil. Worked out once a place.
G.PLACE_NPC_YD = 30
G.PLACE_NPC_SVC = { { " bank ", "b" }, { " auction", "a" }, { " inn ", "i" }, { " stable", "s" }, { " guild master", "p" },
  { " battlemaster", "m" }, { " wind rider", "f" }, { " gryphon", "f" }, { " bat handler", "f" }, { " hippogryph", "f" },
  { " flight", "f" } }
G.placeNpcCache = {}
function G.PlaceNpc(name, cont, x, y)
  local Lay = ns.Layers
  if not (name and cont and x and y and Lay and Lay.ShippedNpcs) then return nil end
  local key = string.format("%s:%d:%d:%d", name, cont, math.floor(x), math.floor(y))
  local hit = G.placeNpcCache[key]
  if hit ~= nil then return hit or nil end
  local want = " " .. name:lower() .. " "
  local trainer = want:find(" trainer ", 1, true) ~= nil
  local svc
  if not trainer then -- (a trainer's by its trade: "skinning" holds "inn")
    for _, w in ipairs(G.PLACE_NPC_SVC) do
      if want:find(w[1], 1, true) then svc = w[2] break end
    end
  end
  local base = Geo.Base(cont)
  local best, bd, bt = false, G.PLACE_NPC_YD ^ 2, 0
  for _, n in ipairs((Lay.ShippedNpcs())) do
    local tier = 0
    if svc then
      if n.svc and n.svc:find(svc, 1, true) then tier = 1 end
    else
      local t = n.title and n.title:lower()
      if t and want:find(" " .. t .. " ", 1, true) then
        tier = 2
      elseif trainer and n.trainer and want:find(" " .. n.trainer:lower() .. " ", 1, true) then
        tier = 1
      end
    end
    if tier > 0 and tier >= bt then
      local sp = n.spawns
      for i = 1, #sp - 3, 4 do
        if Geo.Base(sp[i]) == base then
          local d = (sp[i + 1] - x) ^ 2 + (sp[i + 2] - y) ^ 2
          if tier > bt and d <= G.PLACE_NPC_YD ^ 2 then best, bd, bt = n, d, tier
          elseif tier == bt and d <= bd then best, bd = n, d end
        end
      end
    end
  end
  G.placeNpcCache[key] = best
  return best or nil
end
-- What an icon's hover says: `name`, an NPC's with its `title`, a city place's NPC's (`city`: at x, y on `cont`).
function G.MinimapTipText(name, title, city, cont, x, y)
  if city then
    local n = G.PlaceNpc(name, cont, x, y)
    if n then return G.NpcLabel(ns.NpcName(n.id, n.name), ns.NpcTitle(n.id, n.title)) end
  end
  if not name or name == "" then return nil end
  return G.NpcLabel(name, title)
end
-- The hover text of our icon under the cursor on the minimap, or nil.
function G.MinimapTipAt()
  local _, _, cont = Geo.PlayerWorld()
  if G.MinimapMode() then
    -- the map's buttons under the game's Minimap: the one on top first (the stops' over the icons)
    for i = #stopPins, 1, -1 do
      local b = stopPins[i]
      if b:IsVisible() and b:IsMouseOver() then return b.title end
    end
    for i = #partyPins, 1, -1 do
      local b = partyPins[i]
      if b:IsVisible() and b:IsMouseOver() then return b.name end
    end
    for i = #poiButtons, 1, -1 do
      local b = poiButtons[i]
      if b:IsVisible() and b:IsMouseOver() then
        return G.MinimapTipText(b.name, b.kind == 16 and b.note or nil, b.city, b.level or cont, b.wx, b.wy)
      end
    end
    return nil
  end
  local f = mm.frame
  if not (f and f:IsVisible()) then return nil end
  local cx, cy = GetCursorPosition()
  local fx, fy = f:GetCenter()
  if not (cx and cy and fx and fy) then return nil end
  local k = f:GetEffectiveScale() or 1
  cx, cy = cx / k - fx, cy / k - fy -- (the cursor from the minimap's middle, in its units)
  local function over(t, size)
    return t.tipX and math.abs(cx - t.tipX) <= size / 2 and math.abs(cy - t.tipY) <= size / 2
  end
  if mm.stop and mm.stop:IsShown() and over(mm.stop, 14) then return mm.stop.tipName end
  for i = #mm.partyIcons, 1, -1 do
    local b = mm.partyIcons[i]
    if b.edge:IsShown() and over(b, G.MINIMAP_ICON_SIZE + 2) then return b.tipName end
  end
  for i = #mm.icons, 1, -1 do
    local t = mm.icons[i]
    local e = t.tipE
    if e and t:IsShown() and over(t, e[5]) then return G.MinimapTipText(e.name, nil, e.city, cont, e[1], e[2]) end
  end
  return nil
end
function G.HideMinimapTip()
  local tip = G.minimapTip
  if tip and tip:IsShown() then tip:Hide() end
  G.minimapTipText = nil
end
-- Hit-test now: our tooltip by the cursor with the icon's name, or hidden. The text shown, or nil.
function G.MinimapHover()
  local text = G.MinimapTipAt()
  local gt = GameTooltip
  if not text or (gt and gt:IsShown() and gt:GetOwner() == Minimap) then -- (off our icons, or a blip's own tooltip)
    G.HideMinimapTip()
    return nil
  end
  local tip = G.minimapTip
  if not tip then
    tip = CreateFrame("GameTooltip", "AzerothGPSMinimapTip", UIParent, "GameTooltipTemplate")
    G.minimapTip = tip
  end
  if G.minimapTipText ~= text or not tip:IsShown() then
    tip:SetOwner(Minimap, "ANCHOR_CURSOR")
    tip:SetText(text, 1, 1, 1)
    tip:Show()
    G.minimapTipText = text
  end
  return text
end
-- The Minimap's OnEnter and OnLeave hooked (HookScript: its own scripts stay as they are), the hit-test running only
-- while the cursor is over it.
function G.InitMinimapTips()
  if G.clone or G.minimapTipWatch or not (Minimap and Minimap.HookScript) then return end
  local w = CreateFrame("Frame", nil, UIParent)
  w:Hide()
  G.minimapTipWatch = w
  local since = 0
  w:SetScript("OnUpdate", function(_, dt)
    since = since + dt
    if since < 1 / G.MINIMAP_TIP_HZ then return end
    since = 0
    local ok, err = pcall(G.MinimapHover)
    if not ok then G.LogError("minimap hover", err) end
  end)
  pcall(Minimap.HookScript, Minimap, "OnEnter", function()
    since = 1 -- (at once)
    w:Show()
  end)
  pcall(Minimap.HookScript, Minimap, "OnLeave", function()
    w:Hide()
    G.HideMinimapTip()
  end)
end
---------------------------------------------------------------------------
-- The GPS map as the game's minimap (1.2.0, asked 2026-11-08: "an option to replace the in game minimap with the gps
-- map ... show everything the minimap does now like herbs/mines ... mailboxes ... locked in the corner with just a
-- square border and no logo ... size options"). Addons can't read where the minimap's blips are, so the game's own
-- Minimap is kept, placed exactly over the map's canvas with its ground hidden, and the map draws the ground under it:
-- the same center (the player), the same radius (G.MinimapRadius) and the same turn (the rotateMinimap CVar). The
-- map window loses its frame, buttons and logo (a square border), sits in the minimap's corner by the minimap's own
-- container (Edit Mode moves both) and isn't moved or sized by hand. Its ground hidden one of two ways
-- (`replaceMinimapHide`): "ground" (C_Minimap.SetDrawGroundTextures(false) under a square mask) or "mask" (a fully
-- transparent mask, Media\MinimapClear). Nothing of the Minimap is touched in combat (queued for
-- PLAYER_REGEN_ENABLED), and off (or a /reload with it off) it goes back exactly as it was (G.mmState.was).
-- The Minimap hangs on an anchor of its own in the square's place (G.mmAnchor), never on the window: the square's
-- button grows the window out of the corner into the usual map window over everything (G.SetMinimapExpanded) to set
-- a route, and it goes back after MINIMAP_IDLE s of quiet, its back button or Escape; our frame only, in combat too.
-- The minimap buttons (LibDBIcon's, ours) go round the square: GetMinimapShape is "SQUARE" meanwhile.
-- (three since 2026-11-09, asked: "remove the small size": the old medium, large and extra large; saved ones moved by
-- size once, Core's InitDB `minimapSizes3`)
G.MINIMAP_SIDES = { small = 200, medium = 260, large = 320 }
G.MINIMAP_CLEAR = "Interface\\AddOns\\AzerothGPS\\Media\\MinimapClear" -- (every pixel transparent)
G.MINIMAP_SQUARE = "Interface\\Buttons\\WHITE8X8" -- (every pixel shown: a square minimap)
-- The game's round mask (textures/minimapmask.blp), put back when no other mask was seen: by its FileDataID, never its
-- path. This client's files have no name for it (checked in its CASC root, 2026-11-09): by path it was a missing mask
-- and the minimap given back drew nothing, its ground and blips gone (the user's test of the expanded window).
G.MINIMAP_ROUND = 186178
-- The minimap's own art round it, hidden while it's the GPS map (whichever this client has).
G.MINIMAP_ART = { "MinimapBorder", "MinimapBorderTop", "MinimapCompassTexture", "MinimapNorthTag" }
-- The square's border: the window's metal border without its title band (ns.Window's for a window with no title).
G.MINIMAP_BORDER = ns.WINDOW_PLAIN_BORDER or "SimplePanelTemplate"
-- (its place round the square: left, top, right, bottom from the frame's corners, G.ApplyMinimapChrome)
G.MINIMAP_BORDER_FIT = { 1.5, 3.5, 1.5, -0.5 }
G.MINIMAP_MASK_AGAIN = { 0.1, 0.5 } -- s after the minimap is given back: its own mask set once more
G.MINIMAP_TWEEN = 0.25 -- s: the square grows into the window, and back
G.MINIMAP_IDLE = 5 -- s with nothing done on the expanded map before it goes back to the square (the default)
-- The player's own wait (Options > Map, `replaceMinimapIdle`; asked 2026-11-11: "add option to change the timer for
-- map auto closing without activity", or to turn it off): 0 is never, the map stays out until it's sent back.
-- The tutorial keeps the default: its steps say 5 seconds and count them down.
function G.MinimapIdleSeconds()
  if ns.Tutorial and ns.Tutorial.run then return G.MINIMAP_IDLE end
  local v = ns.settings and tonumber(ns.settings.gps.replaceMinimapIdle)
  if not v then return G.MINIMAP_IDLE end
  return math.max(0, v)
end
-- (over the world map and its quest log, HIGH; bags and the game's panels, MEDIUM; and our popups' own DIALOG; under the
-- popups lifted over it, Core's POPUP_OVER_STRATA, asked 2026-11-09)
G.MINIMAP_EXPANDED_STRATA = "FULLSCREEN"
-- The minimap's quest, task and archaeology areas (its "blobs": a big see-through circle with a dotted ring over the
-- square, the user 2026-11-09), unseen while it's the square: the map's own quest areas instead. No getters, and the
-- game's own UI never sets them (checked in the client's Blizzard_* code): given back at the engine's default, 1.
G.MINIMAP_BLOBS = { "SetQuestBlobInsideAlpha", "SetQuestBlobOutsideAlpha", "SetQuestBlobRingAlpha",
  "SetTaskBlobInsideAlpha", "SetTaskBlobOutsideAlpha", "SetTaskBlobRingAlpha",
  "SetArchBlobInsideAlpha", "SetArchBlobOutsideAlpha", "SetArchBlobRingAlpha",
  -- (their rings' size too, 0 and back to 1, the engine's default; in this client's API docs, MinimapFrameAPI)
  "SetQuestBlobRingScalar", "SetTaskBlobRingScalar", "SetArchBlobRingScalar" }
G.MINIMAP_BLOB_DEFAULT = 1
function G.SetMinimapBlobs(alpha)
  for _, method in ipairs(G.MINIMAP_BLOBS) do G.MinimapCall(Minimap, method, alpha) end
end
-- While it's the square: the game's own quest areas hidden only while ours are drawn (the Quest Areas layer); with
-- ours off, the game's (asked 2026-11-15: "if player disables Quest Areas then show original quest areas and not
-- ours"), as in the world map (G.WorldMapArtPins).
function G.MinimapBlobAlpha()
  local st = S()
  return (st.layerQuests and st.layerQuestAreasMinimap ~= false) and 0 or G.MINIMAP_BLOB_DEFAULT
end
-- Our quest areas drawn: on the map by Quest areas on the map (`layerQuestAreas`), on the square by Quest areas on the
-- minimap (`layerQuestAreasMinimap`; asked 2026-11-15, "expand the option to 2 choices, one for the map and one for
-- the minimap").
function G.QuestAreasOn()
  local st = S()
  if not st.layerQuests then return false end
  if G.MinimapMode() then return st.layerQuestAreasMinimap ~= false end
  return st.layerQuestAreas and true or false
end
-- The square's button: the window's corner logo on its plate, as big as the window's (asked 2026-11-09, "overlay like
-- we do for the top left corner just make it bottom left"), pixel for pixel.
G.MINIMAP_LOGO_UNITS = ns.CORNER_LOGO_UNITS or 62
-- (asked 2026-11-09: 80% of that on the large square, and shrinking with the square's side; a bit further left)
G.MINIMAP_LOGO_SHARE = 0.8
G.MINIMAP_LOGO_IN = 0.3 -- its middle this share of its width in from the square's left edge (the window's: 0.42)
function G.MinimapLogoUnits()
  return G.MINIMAP_LOGO_UNITS * G.MINIMAP_LOGO_SHARE * G.MinimapSquareSide() / G.MINIMAP_SIDES.large
end
G.mmState = { on = false }

-- The map is the minimap square now (taken, not only asked for: combat may hold it back; not while expanded into the
-- window to set a route).
function G.MinimapMode()
  local m = G.mmState
  return m.on == true and not m.expanded and not G.WorldMapHosted()
end
-- The route's line left off the square (asked 2026-11-17, option `replaceMinimapRoute` off): only there, the map opened
-- out of it and in the world map keep it, and the stops' markers stay.
function G.SquareHidesRoute()
  return S().replaceMinimapRoute == false and G.MinimapMode()
end

-- The GPS map in the game's own world map window (the option `useWorldMap`, asked 2026-11-10: "an option that uses the
-- in game map instead of the GPS map, adding the buttons to that map instead, including the seamless map. So instead
-- of the minimap logo popping out the GPS map it'd instead pop out the main map"). The map window itself is laid over
-- the world map's map area while that window is open (never made its child: the game's frame is left as it is), so
-- the route, the stops, the buttons and the map styles are all there; closed, the map is the minimap square (with
-- that option) or not shown. Its own title bar, logo, Move tab and size corner are off meanwhile.
-- Where the map sits in the world map: in that window's own strata, over its map art and under its icons (asked
-- 2026-11-10: "this shouldn't by default just overlay, should fall between the map and all its original icons on
-- top"). The game's map icons (its pins, and other addons' on it: Questie's) are at frame levels from about 2000 up;
-- the map and everything on it go from WORLD_MAP_LEVEL, every frame of it moved by the same amount (set one by one:
-- raising the window's own frame alone left its map and its mouse under the game's map, seen in game 2026-11-10).
-- The level itself is read off the game's map each time: one over its art's (the art is at its canvas's own level,
-- and the window, a top-level one, is raised as it's used, so no fixed number stays between the two: at 50 the map
-- was under the game's art and its mouse, seen in a recording 2026-11-10).
G.WORLD_MAP_LEVEL = 50 -- (without a canvas to read)
-- The game's map canvas (the scroll frame's child: its art and every icon on it), else the window.
function G.WorldMapCanvas()
  local box = G.WorldMapBox()
  local child = box and rawget(box, "Child")
  if type(child) == "table" and child.GetFrameLevel then return child end
  return rawget(_G, "WorldMapFrame")
end
-- The map as big as ever in the game's canvas, whatever that's scaled to (its zoom): the opposite scale. True when
-- it changed.
function G.WorldMapKeepScale()
  local box = G.WorldMapBox()
  local child = box and rawget(box, "Child")
  if not (frame and type(child) == "table" and child.GetEffectiveScale and frame:GetParent() == child) then return false end
  local ces, bes = child:GetEffectiveScale(), box:GetEffectiveScale()
  if not (ces and bes and ces > 0 and bes > 0) then return false end
  local k = bes / ces
  if G.wmState.scale and math.abs(G.wmState.scale - k) < 1e-6 then return false end
  G.wmState.scale = k
  frame:SetScale(k)
  return true
end
function G.WorldMapLevel()
  local box = G.WorldMapBox()
  local child = box and rawget(box, "Child")
  local l = child and child.GetFrameLevel and child:GetFrameLevel()
  if type(l) ~= "number" then l = box and box.GetFrameLevel and box:GetFrameLevel() end
  return type(l) == "number" and l + 1 or G.WORLD_MAP_LEVEL
end
function G.WorldMapStrata()
  local wm = rawget(_G, "WorldMapFrame")
  return wm and wm.GetFrameStrata and wm:GetFrameStrata() or "MEDIUM"
end
-- Every frame in the window with how far over the window's own level it is (parents first).
function G.LevelOffsets()
  local base, strata, list = frame:GetFrameLevel() or 0, frame:GetFrameStrata(), {}
  local function Gather(f, buttons)
    buttons = buttons or (topLayer ~= nil and f == topLayer)
    for _, kid in ipairs({ f:GetChildren() }) do
      if kid.GetFrameLevel and kid.SetFrameLevel then
        local l = kid:GetFrameLevel() or 0
        -- (`over`: a frame with a strata of its own, to be over everything: a dropdown's list, the search's panel;
        -- `buttons`: the map's buttons and panels, everything on the layer over the map)
        local ks = kid.GetFrameStrata and kid:GetFrameStrata()
        list[#list + 1] = { kid, l - base, over = ks and ks ~= strata and l or nil,
          buttons = buttons or nil }
      end
      Gather(kid, buttons)
    end
  end
  Gather(frame)
  return list
end
-- In the game's map canvas a strata means nothing (the scroll frame draws all in it as one layer, by level alone):
-- the map's frames that are over everything by a strata of their own are put WORLD_MAP_OVER levels up there instead,
-- over the game's icons too (`boost`), and back at their own levels after. (The dungeon map's Path Color list was
-- under the map there, seen in game 2026-11-10.)
G.WORLD_MAP_OVER = 5000
-- The map's buttons and panels (Clear Route, Search Places, the quick buttons, the directions) are over the game's
-- icons there too, other addons' with them: WORLD_MAP_BUTTONS levels up, the map itself still under the icons
-- (seen in game 2026-11-11, gathering icons drawn across Clear Route: "our buttons should always be on top of
-- those"). The game's icons are at about 2000 to 2900.
G.WORLD_MAP_BUTTONS = 4000
G.wmOwnLevel = setmetatable({}, { __mode = "k" })
G.wmSetLevel = setmetatable({}, { __mode = "k" }) -- (the level SetLevelTree set each frame to last)
-- The window and every frame in it moved to `level` (the window's; the others keep their places over it, as `offsets`
-- has them: read before the window was given another parent, which sets levels of its own).
-- Whether frame `f` is the route panel or in it.
function G.InNavPanel(f)
  local p, n = f, 0
  while type(p) == "table" and n < 6 do
    if p == G.navPanel then return true end
    p = p.GetParent and p:GetParent() or nil
    n = n + 1
  end
  return false
end
function G.SetLevelTree(level, offsets, boost)
  offsets = offsets or G.LevelOffsets()
  if G.navDetached then -- (the route panel in its own window: not the map's any more, left at its own level)
    local kept = {}
    for _, e in ipairs(offsets) do
      if not G.InNavPanel(e[1]) then kept[#kept + 1] = e end
    end
    offsets = kept
  end
  local top = level
  if frame:GetFrameLevel() ~= level then frame:SetFrameLevel(level) end
  for _, e in ipairs(offsets) do
    local kid, l = e[1], nil
    local own = G.wmOwnLevel[kid] or e.over
    if own and boost then
      G.wmOwnLevel[kid] = own
      l = math.min(9500, level + G.WORLD_MAP_OVER + math.min(own, 500))
    elseif own then
      G.wmOwnLevel[kid] = nil
      l = own
    elseif e.buttons and boost then
      l = math.min(9000, level + G.WORLD_MAP_BUTTONS + math.max(0, e[2]))
    else
      l = math.max(0, level + e[2])
      if l > top then top = l end
    end
    -- (only a frame not at its level already: the world map's tick goes over the whole tree each second, and setting a
    -- level the game passes down to every child; at its level = the one set last, and still reporting it)
    if G.wmSetLevel[kid] ~= l or kid:GetFrameLevel() ~= l then
      pcall(kid.SetFrameLevel, kid, l)
      G.wmSetLevel[kid] = l
    end
  end
  return top
end
-- The world map's own buttons over its map (tracking, floors, its coordinates): kept over ours.
function G.RaiseWorldMapOverlays(top)
  local wm = rawget(_G, "WorldMapFrame")
  local list = wm and rawget(wm, "overlayFrames")
  if type(list) ~= "table" then return end
  for i, f in ipairs(list) do
    if type(f) == "table" and f.GetFrameLevel and f.SetFrameLevel and (f:GetFrameLevel() or 0) <= top then
      pcall(f.SetFrameLevel, f, top + 5 + i)
    end
  end
end
-- The game's own explored-area art is a map icon too (over ours, it would cover the map's art): unseen meanwhile.
G.WORLD_MAP_ART_PINS = { "MapExplorationPinTemplate", "FogOfWarPinTemplate" }
-- The game's own quest areas (its filled blue blobs) are map icons over ours too: with our quest areas drawn, they
-- doubled them up, too dark (reported 2026-11-14: "on world map view the quest outlined areas are too dark now").
-- Unseen while ours are drawn; seen again with ours off, or the world map back to the game's.
G.WORLD_MAP_AREA_PINS = { "QuestBlobPinTemplate" }
function G.WorldMapArtPins(shown)
  local wm = rawget(_G, "WorldMapFrame")
  if not (wm and wm.EnumeratePinsByTemplate) then return end
  local st = S()
  local ours = st and st.layerQuests and st.layerQuestAreas
  local function set(list, a)
    for _, tmpl in ipairs(list) do
      pcall(function()
        for pin in wm:EnumeratePinsByTemplate(tmpl) do
          if pin:GetAlpha() ~= a then pin:SetAlpha(a) end
        end
      end)
    end
  end
  set(G.WORLD_MAP_ART_PINS, shown and 1 or 0)
  set(G.WORLD_MAP_AREA_PINS, (shown or not ours) and 1 or 0)
end

-- The game's map kept on the same ground as ours, so its icons are where ours would put them: the map we drive (pan,
-- zoom, following the player), the game's follows. Its map is the zone under the view's middle, or the continent's
-- once more than WORLD_MAP_ZONE_OVER of a zone's width shows; its scale and scroll are set from our view (the scroll
-- as the widget takes it, not through the game's own clamp: our view goes past a zone's edge). A map picked in the
-- game's own bar (its zone list) is looked at on ours.
G.WORLD_MAP_ZONE_OVER = 1.6
-- The world map's own map pin button is pressed (the next click on the map places the game's map pin).
function G.WorldMapPinning()
  if not G.wmState.on then return false end
  local b = rawget(WorldMapFrame, "WorldMapTrackingPinButton")
  return type(b) == "table" and rawget(b, "isActive") == true
end
G.WORLD_MAP_INSET = 44 -- (UI units from the map's left edge: past the round buttons there)
-- The import button in the map's bottom right corner: in the world map, left of that window's own button there
-- (asked 2026-11-10: "bottom right needs the import button shifted left for game map mode").
G.WORLD_MAP_CORNER = 36
function G.PlaceCornerButtons(host)
  local b = G.mapButtons and G.mapButtons.import
  if not b then return end
  b:ClearAllPoints()
  b:SetPoint("BOTTOMRIGHT", host and -6 - G.WORLD_MAP_CORNER or -6, 6)
end

-- A double-click on any icon of the game's map makes a stop there, as one on the map itself does (asked 2026-11-10:
-- "support double clicking default map quest icons, questie icons, any icon for routing"). The icons are the game's
-- and other addons' frames over the map, so the clicks never reach it: every left click in the game is heard
-- instead (GLOBAL_MOUSE_DOWN), and one on a frame in the game's map canvas that isn't ours counts. Nothing of theirs
-- is hooked or changed; their own click does what it always does.
G.WORLD_MAP_ICON_MAX = 64 -- (UI units: a frame bigger than this is an area, the stop goes where the pointer is)
-- The spot of that frame on our map (UI units from its middle), or nil when it isn't an icon of the game's map.
function G.WorldMapIconSpot(f)
  if not (G.wmState.on and canvas and frame and type(f) == "table" and f.GetParent) then return nil end
  local child = G.WorldMapCanvas()
  if f == child or f == frame then return nil end
  local p, n, inside = f, 0, false
  while type(p) == "table" and n < 40 do
    if p == frame then return nil end -- (ours: the map's own click)
    if p == child then
      inside = true
      break
    end
    p = p.GetParent and p:GetParent() or nil
    n = n + 1
  end
  if not inside then return nil end
  local sc = canvas:GetEffectiveScale()
  local ccx, ccy = canvas:GetCenter()
  if not (sc and sc > 0 and ccx and ccy) then return nil end
  local x, y = GetCursorPosition()
  local fx, fy = f:GetCenter()
  local fs = f:GetEffectiveScale()
  if fx and fy and fs and fs > 0 and math.max(f:GetWidth() or 0, f:GetHeight() or 0) * fs <= G.WORLD_MAP_ICON_MAX * sc then
    x, y = fx * fs, fy * fs -- (the icon's own middle, wherever on it the pointer is)
  end
  return x / sc - ccx, y / sc - ccy
end
-- A mouse button went down somewhere: true when it was the second click of a double-click on such an icon.
function G.WorldMapIconDown(button)
  local st = G.wmState
  if button ~= "LeftButton" or not st.on then return false end
  local f
  local foci = rawget(_G, "GetMouseFoci")
  if foci then
    local ok, list = pcall(foci)
    f = ok and type(list) == "table" and list[1] or nil
  elseif rawget(_G, "GetMouseFocus") then
    f = GetMouseFocus()
  end
  local dx, dy = G.WorldMapIconSpot(f)
  if not dx then
    st.iconClick = nil
    return false
  end
  local now, c = GetTime(), st.iconClick
  if c and c.f == f and now - c.t <= G.DOUBLE_CLICK then
    st.iconClick = nil
    G.MapClickHook(dx, dy, true)
    G.AddPending(dx, dy)
    return true
  end
  st.iconClick = { f = f, t = now }
  return false
end
-- A land with no continent map of its own (Zephras Isle, an island in the sky: zones only): the game's map of it
-- there, whatever the zoom. The one the game shows already when it's one of that land's, else the zone at (x, y),
-- else any of its maps there. (Until 1.2.3 the game's map wasn't kept under ours there at all: its own art, player
-- arrow and quest icons sat over the GPS map in a small picture of their own, seen in game 2026-11-11: "on Zephras
-- Isle using in game map it has this permanent static image that follows the player's position on map pan".)
function G.LandMap(base, x, y, cur)
  local um = cur and ns.Maps[cur]
  if um and um.continent == base and um.bounds and um.type ~= 1 and um.type ~= 2 then return cur end
  local ok, id = pcall(G.LocateWorld, base, x, y)
  if ok and id and ns.Maps[id] and ns.Maps[id].bounds then return id end
  local best, bestKey
  for mid, o in pairs(ns.Maps) do
    local b = o.bounds
    if o.continent == base and b and o.type ~= 1 and x >= b[1] and x <= b[3] and y >= b[2] and y <= b[4] then
      local key = ((o.parent or 0) ~= 0 and 1 or 0)
      if not bestKey or key > bestKey or (key == bestKey and mid < best) then best, bestKey = mid, key end
    end
  end
  return best
end
-- The city's map under (x, y), one level below zone `zoneID` (ns.Maps' zoneParent: Ironforge's under Dun Morogh's), when
-- the view (`viewW` yards across) is no wider than it; nil for none.
function G.CityMapUnder(zoneID, x, y, viewW)
  if not (zoneID and ns.Maps) then return nil end
  for mid, o in pairs(ns.Maps) do
    local b = o.bounds
    if o.zoneParent == zoneID and b and x >= b[1] and x <= b[3] and y >= b[2] and y <= b[4]
        and viewW <= (b[4] - b[2]) * G.WORLD_MAP_ZONE_OVER then
      return mid
    end
  end
  return nil
end
function G.WorldMapSync()
  local st = G.wmState
  if not (st.on and canvas) then return false end
  local wm, box = WorldMapFrame, G.WorldMapBox()
  local child = box and rawget(box, "Child")
  if not (child and box.InstantPanAndZoom and wm.SetMapID and wm.GetMapID and ns.Maps) then return false end
  local x, y, cont, _, s = G.ViewState()
  if not (x and y and cont and s and s > 0) or G.ViewInstance() then return false end
  local contMap = G.ContinentMap(Geo.Base(cont))
  local land = not contMap and G.LandMap(Geo.Base(cont), x, y, wm:GetMapID()) -- (Zephras Isle: zones only)
  if not (contMap or land) then return false end
  local viewW = canvas:GetWidth() / s
  -- (the zone there as the game has it; by the zones' rectangles alone a spot in the Barrens was Durotar's, whose
  -- rectangle reaches over it: the game's map showed Durotar's icons under a view of the Barrens, so its quest icons
  -- and other addons' objectives were missing, seen in game 2026-11-10)
  local id = land or nil
  local cb = contMap and ns.Maps[contMap] and ns.Maps[contMap].bounds
  if cb and C_Map and C_Map.GetMapInfoAtPosition then
    local ok, info = pcall(C_Map.GetMapInfoAtPosition, contMap, (cb[4] - y) / (cb[4] - cb[2]), (cb[3] - x) / (cb[3] - cb[1]))
    if ok and type(info) == "table" and info.mapType == 3 and ns.Maps[info.mapID] then id = info.mapID end
  end
  if not id and G.LocateWorld then
    local ok, v = pcall(G.LocateWorld, Geo.Base(cont), x, y)
    if ok and v and ns.Maps[v] and ns.Maps[v].type == 3 then id = v end
  end
  id = id or G.ZoneAt(x, y, contMap)
  -- (a city's own map one level below its zone, Ironforge's under Dun Morogh's, when the view's middle is on it and the
  -- view no wider than it: the game asked about the continent's spot names the zone, and the game itself then went to
  -- the player's own map, the city, taken for a map picked in its bar; a player's screenshot 2026-11-16)
  id = G.CityMapUnder(id, x, y, viewW) or id
  local m = id and ns.Maps[id]
  if contMap and (not (m and m.bounds) or viewW > (m.bounds[4] - m.bounds[2]) * G.WORLD_MAP_ZONE_OVER) then
    id, m = contMap, ns.Maps[contMap]
  end
  if not (m and m.bounds) then return false end
  local cur = wm:GetMapID()
  if st.mapID and cur ~= st.mapID and cur ~= id then -- (picked in the game's own bar: ours looks at it)
    local um = ns.Maps[cur]
    st.mapID, st.sig = nil, nil
    -- (the player's own map while ours follows them: the game going to it by itself, a subzone changed, isn't a pick;
    -- ours stays on the player, the city's inside map with it)
    local px, py, pc = Geo.PlayerWorld()
    local onPlayer = not free and um and um.bounds and px and um.continent == Geo.Base(pc)
      and px >= um.bounds[1] and px <= um.bounds[3] and py >= um.bounds[2] and py <= um.bounds[4]
    if onPlayer then
      st.mapID = cur
      return false
    end
    if um and um.bounds and um.continent and um.type ~= 1 then
      local b = um.bounds
      local zoom = G.MapFitZoom(um)
      -- (a city with an inside map, Ironforge, Undercity: no further out than its map shows, G.CityUnderView)
      if G.CityInterior(cur) then zoom = math.min(zoom, G.CITY_MAX_ZOOM * (G.ZoomScale and G.ZoomScale() or 1)) end
      G.LookAt(um.continent, (b[1] + b[3]) / 2, (b[2] + b[4]) / 2, zoom)
      st.mapID = cur
      return true
    end
  end
  local changed = cur ~= id
  if changed then pcall(wm.SetMapID, wm, id) end
  st.mapID = id
  local bes = box:GetEffectiveScale() or 1
  local es = bes -- (ours is kept the scroll frame's: G.WorldMapKeepScale; read off ourselves it lags a zoom)
  local cw, ch = child:GetWidth(), child:GetHeight()
  -- (our middle from the scroll frame's top left, in its units: the window sits on it, its map BORDER in)
  local bl, bt = box:GetLeft(), box:GetTop()
  local ccx, ccy = bl and (bl + box:GetWidth() / 2), bt and (bt - box:GetHeight() / 2)
  if not (cw and ch and cw > 0 and ch > 0 and ccx and ccy and bl and bt and bes > 0) then return false end
  local b = m.bounds
  local mapW, mapH = b[4] - b[2], b[3] - b[1]
  if mapW <= 0 or mapH <= 0 then return false end
  local sc = s * (es / bes) * mapW / cw -- (the game's canvas scale that shows a yard as big as ours does)
  local u, v = (b[4] - y) / mapW, (b[3] - x) / mapH -- (the view's middle on the game's map: east, south)
  local dx, dy = (ccx * es - bl * bes) / bes, (bt * bes - ccy * es) / bes -- (our middle from the box's top left)
  local h, vv = u * cw - dx / sc, v * ch - dy / sc
  local key = string.format("%d:%.5f:%.2f:%.2f", id, sc, h, vv)
  -- (both ways: the game's scroll frame pulls its scroll back inside its own limits, the vertical one too near a
  -- zone's edge, and other addons' icons over it sat off their places until the view moved again: "when zooming the
  -- icons jump out of place then back in after a second or so", 2026-11-12)
  -- Once a view, though: where the game holds its scroll at its own limit (our view off a zone's edge), setting it
  -- again every frame fought the game's every frame, the game's canvas moved twice a frame (1.2.5's stutters, reported
  -- 2026-11-13). The scroll the game pulled it back to, the same again for the same view, is left as it is.
  local hNow = box.GetHorizontalScroll and box:GetHorizontalScroll()
  local vNow = box.GetVerticalScroll and box:GetVerticalScroll()
  local function Near(a, b) return not a or not b or math.abs(a - b) < 0.01 end
  if key == st.sig and not changed then
    if Near(hNow, h) and Near(vNow, vv) then return false end
    if st.pulled == key and Near(hNow, st.pulledH) and Near(vNow, st.pulledV) then return false end
    st.pulled, st.pulledH, st.pulledV = key, hNow, vNow
  end
  st.sig = key
  if changed or sc ~= st.sc then
    st.sc = sc
    pcall(box.InstantPanAndZoom, box, sc, u, v, true) -- (its icons sized for this scale)
    G.WorldMapArtPins(false)
    G.WorldMapKeepScale()
  end
  pcall(box.SetHorizontalScroll, box, h)
  pcall(box.SetVerticalScroll, box, vv)
  return true
end

-- The world map window's own size, dragged by a corner on the map while it's in it (asked 2026-11-10: "Can we make
-- the in game map window sizable when in this mode?"): the windowed map only, its shape kept, the size remembered
-- (`worldMapSize`, in the window's own units).
G.WORLD_MAP_MIN_W = 500
function G.WorldMapWindowed()
  local wm = rawget(_G, "WorldMapFrame")
  if not wm then return false end
  if wm.IsMaximized then
    local ok, v = pcall(wm.IsMaximized, wm)
    if ok and v then return false end
  end
  return true
end
function G.SetWorldMapSize(w, h)
  local wm = rawget(_G, "WorldMapFrame")
  if not (wm and w and h and G.WorldMapWindowed()) then return false end
  local sw = (UIParent:GetWidth() or 1600) * (UIParent:GetEffectiveScale() or 1) / (wm:GetEffectiveScale() or 1)
  local k = h / w
  w = math.max(G.WORLD_MAP_MIN_W, math.min(sw, w))
  wm:SetSize(w, w * k)
  if wm.OnFrameSizeChanged then pcall(wm.OnFrameSizeChanged, wm) end
  return true
end
function G.ApplyWorldMapSize()
  local size = S().worldMapSize
  if type(size) == "table" and tonumber(size[1]) and tonumber(size[2]) then G.SetWorldMapSize(size[1], size[2]) end
end
function G.WorldMapGrip()
  if G.wmGrip or not frame then return G.wmGrip end
  local b = CreateFrame("Button", nil, frame)
  b:SetSize(18, 18)
  b:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -1, 1)
  b:SetFrameLevel(frame:GetFrameLevel() + 40 + G.ArtSpan())
  b:SetNormalTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Up")
  b:SetHighlightTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Highlight")
  b:SetPushedTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Down")
  b:SetScript("OnMouseDown", function(self)
    local wm = WorldMapFrame
    local es = wm:GetEffectiveScale() or 1
    local cx = GetCursorPosition()
    self.drag = { x = cx / es, w = wm:GetWidth(), h = wm:GetHeight() }
  end)
  b:SetScript("OnMouseUp", function(self)
    if not self.drag then return end
    self.drag = nil
    local wm = WorldMapFrame
    S().worldMapSize = { math.floor(wm:GetWidth() + 0.5), math.floor(wm:GetHeight() + 0.5) }
  end)
  b:SetScript("OnUpdate", function(self)
    local d = self.drag
    if not d then return end
    local wm = WorldMapFrame
    local cx = GetCursorPosition()
    local w = d.w + (cx / (wm:GetEffectiveScale() or 1) - d.x)
    G.SetWorldMapSize(w, w * d.h / d.w)
  end)
  b:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    GameTooltip:SetText(L["Drag to resize the world map"], 1, 1, 1)
    GameTooltip:Show()
  end)
  b:SetScript("OnLeave", GameTooltip_Hide)
  b:Hide()
  G.wmGrip = b
  return b
end
-- Not with the game's controller UI on (seen in game 2026-11-11, "worked for the first couple map opens then got the
-- same error"): to keep the game's map on the GPS map's ground, the map is set to a zone and panned and zoomed from
-- here, and what an addon sets on the game's map taints the game's own code that reads it. With that UI on, that
-- code goes on to a function of the game's own only each time the map is opened or closed, and the game forbids it
-- (G.PanelsHeld). So there the GPS map opens in its own window, the option kept for when that UI is off; said once a
-- session, in chat.
function G.WorldMapWanted()
  local st = ns.settings and ns.settings.gps -- (asked before the settings are loaded too: G.MapSize)
  if not (st ~= nil and st.useWorldMap == true and rawget(_G, "WorldMapFrame") ~= nil) then return false end
  if G.ControllerUI and G.ControllerUI() then
    if not G.panelsHeldSaid then
      G.panelsHeldSaid = true
      ns.Print(L["With the game's controller UI on, the GPS map can't show in the game's world map: it opens in its own window instead."])
    end
    return false
  end
  return true
end
-- The part of the world map the map covers: its scrolling map area, else the whole window.
function G.WorldMapBox()
  local wm = rawget(_G, "WorldMapFrame")
  if not wm then return nil end
  local function Frame(v) return type(v) == "table" and v.GetWidth and v or nil end
  local box = Frame(wm.ScrollContainer)
  if not box and wm.GetCanvasContainer then
    local ok, v = pcall(wm.GetCanvasContainer, wm)
    box = ok and Frame(v) or nil
  end
  return box or wm
end
function G.WorldMapHosted()
  if not G.WorldMapWanted() then return false end
  local wm = WorldMapFrame
  return wm.IsShown and wm:IsShown() and true or false
end
-- The box's size in the map window's own units (the world map has a scale of its own).
function G.WorldMapSize()
  local box = G.WorldMapBox()
  local w, h = box and box:GetWidth() or 0, box and box:GetHeight() or 0
  local k = ((box and box:GetEffectiveScale()) or 1) / ((frame and frame:GetEffectiveScale()) or 1)
  if k <= 0 then k = 1 end
  return math.max(G.SIZE_MIN, math.floor(w * k + 0.5)), math.max(G.SIZE_MIN, math.floor(h * k + 0.5))
end
-- The game's controller UI is on (its Gamepad options' "Enable Gamepad UI").
function G.ControllerUI()
  local C = rawget(_G, "C_InputInterfaceStyle")
  local T = Enum and Enum.InputDeviceInterfaceType
  if not (type(C) == "table" and C.GetCurrentStyle and type(T) == "table" and T.Gamepad ~= nil) then return false end
  local ok, v = pcall(C.GetCurrentStyle)
  return ok and v == T.Gamepad
end
-- With it on, the game runs a function of its own only (SetPreferredGamepadInteractTarget) each time one of its
-- panels is shown or hidden: a panel shown or hidden by an addon is an action the game forbids, with its "blocked
-- from an action" error each time (seen in game 2026-11-11, 32 of them: the world map opened and closed by the
-- square's logo and the show/hide key). So AzerothGPS never opens or closes a game panel then.
function G.PanelsHeld()
  return G.ControllerUI()
end
-- Opens or closes the game's world map (the logo on the square, the show/hide key). Opened by these, it's ours to
-- close again (`G.wmState.byUs`: the options that send the map back as the player moves or a fight starts).
function G.ToggleWorldMap()
  local wm = rawget(_G, "WorldMapFrame")
  if not wm then return false end
  if G.PanelsHeld() or G.WorldMapLocked() then return false end
  G.wmState.byUs = not wm:IsShown() or nil
  local toggle = rawget(_G, "ToggleWorldMap")
  if toggle then
    local ok = pcall(toggle)
    if ok then return true end
  end
  wm:SetShown(not wm:IsShown())
  return true
end
-- In a fight the game doesn't let an addon open or close its world map: clicking the logo or the minimap button, or
-- the key, with the world map option said "Interface action failed because of an AddOn" and nothing opened (seen in
-- game 2026-11-12).
function G.WorldMapLocked()
  return InCombatLockdown and InCombatLockdown() and true or false
end
-- The logo, the minimap button and the show/hide key with the world map option: that window opened or closed; in a
-- fight, while it can't be, the GPS map in its own window instead: grown out of the minimap square (and back), or,
-- without the square, shown (`G.wmState.own`) till the next click or the world map opening. The world map already
-- open (the player's own key, M) is left to its own button and key then. True when something was done.
function G.ToggleMapView()
  if not G.WorldMapLocked() then return G.ToggleWorldMap() end
  local wm = rawget(_G, "WorldMapFrame")
  if wm and wm:IsShown() then return false end
  local m = G.mmState
  if m.on then
    G.SetMinimapExpanded(not m.expanded, true)
    return true
  end
  G.wmState.own = not G.wmState.own or nil
  G.ApplySettings()
  return true
end
-- The world map opened, closed or resized: the map into it, or back.
-- (Its own record of what it last saw, `st.seen`: G.ApplySettings sets `st.on` too, as it sees the world map open. Each
-- call is in the debug log, kept from login; an error in setting it up is logged, not lost in the game's OnShow.)
function G.WorldMapChanged()
  if not frame then return end
  local on = G.WorldMapHosted()
  local w, h = 0, 0
  if on then w, h = G.WorldMapSize() end
  local st = G.wmState
  local same = st.seen == on and st.w == w and st.h == h
  if ns.Debug and not G.clone then -- (the debug log, kept from login: Debug.Keep)
    pcall(G.DebugWorldMap, "world map " .. (on and "open" or "closed") .. (same and ", nothing new" or ""),
      { flagOn = st.on and true or false })
    if not same then G.wmLogLeft = on and 10 or nil end
  end
  if same then return end
  st.seen = on
  local ok, err = pcall(G.SetUpWorldMap, on, w, h)
  if not ok then G.LogError("world map", err) end
end
function G.SetUpWorldMap(on, w, h)
  local st = G.wmState
  st.on, st.w, st.h = on, w, h
  local m = G.mmState
  if on then m.tween, m.expanded = nil, nil end -- (grown out of the square meanwhile: the world map's instead)
  if on then st.own = nil end -- (its own window for a fight: the world map's now, G.ToggleMapView)
  pcall(G.ApplySettings) -- (an error in placing it: raised by the one below, the state set first)
  st.scale = nil
  if not on then
    st.byUs, st.alpha = nil, nil
    G.WorldMapArtPins(true)
  else
    G.ApplyWorldMapSize()
    w, h = G.WorldMapSize()
    st.w, st.h = w, h
  end
  st.mapID, st.sig, st.sc = nil, nil, nil
  st.wasMoving = G.PlayerMoving() -- (moving already as it opens: not a start)
  if G.wmTicker then G.wmTicker:SetShown(on) end
  G.ApplySettings()
  if ns.Looks and ns.Looks.ApplyCharm then pcall(ns.Looks.ApplyCharm) end -- (the charm: on the square, or back)
end
function G.DebugWorldMap(what, extra)
  local f = {}
  local function size(tag, fr)
    if fr and fr.GetWidth then
      f[tag] = string.format("%.0fx%.0f", fr:GetWidth() or -1, fr.GetHeight and fr:GetHeight() or -1)
      if fr.GetEffectiveScale then f[tag .. "Scale"] = string.format("%.3f", fr:GetEffectiveScale() or -1) end
      if fr.IsVisible then f[tag .. "Vis"] = fr:IsVisible() and true or false end
    end
  end
  size("box", G.WorldMapBox())
  size("frame", frame)
  size("canvas", canvas)
  local w, h = G.WorldMapSize()
  f.wmSize = string.format("%sx%s", tostring(w), tostring(h))
  f.hosted = G.WorldMapHosted() and true or false
  f.square = G.MinimapMode() and true or false
  f.style = G.Style()
  f.zoom = S().zoom
  f.artSpan = G.ArtSpan()
  f.route = ns.Nav.route and true or false
  f.vs = view.s or false
  f.tiles = G.laidTiles and G.laidTiles.laidSig or false
  for k, v in pairs(extra or {}) do f[k] = v end
  ns.Debug.Keep(what, f)
end
-- Each frame while the map is in the world map: faded as that window is (the game fades its map while the player
-- moves, the mapFade setting: "when moving the game fades the map window, when using this mode it should do the same
-- to match", asked 2026-11-10), and closed as the player starts moving with "Back to the minimap when you move" on,
-- when it was opened by the logo or the key (asked 2026-11-10).
function G.WorldMapTick()
  local st = G.wmState
  if not st.on then return end
  local now = GetTime()
  -- (once a second: frames made since, a list opened for the first time, into their places too)
  if st.level and (not st.levelAt or now - st.levelAt >= 1) then
    st.levelAt = now
    G.SetLevelTree(st.level, nil, true)
  end
  if not st.artPinsAt or now - st.artPinsAt >= 1 then -- (the game's icons made again since: a quest area redrawn)
    st.artPinsAt = now
    G.WorldMapArtPins(false)
  end
  if st.level and G.WorldMapLevel() ~= st.level then G.ApplySettings() end -- (the game's window raised: over its art again)
  G.WorldMapSync()
  G.WorldMapKeepScale() -- (the game's canvas zoomed since, by us or by the game)
  local moving = G.PlayerMoving()
  local started = moving and not st.wasMoving
  st.wasMoving = moving
  if started and st.byUs and S().replaceMinimapCollapseOnMove then -- (its search open too: asked 2026-11-15)
    G.CloseMapMenus()
    G.CloseWorldMap()
  end
end
-- The map menu and the search closed with the map as the player starts moving (asked 2026-11-15: "if player starts
-- moving after quick search and the window closes the map menu should close as well").
function G.CloseMapMenus()
  if G.mapMenu then G.mapMenu:Hide() end
  if G.searchPanel then G.searchPanel:Hide() end
end
-- The world map closed by us (never one the player opened themselves with its own key).
function G.CloseWorldMap()
  local wm = rawget(_G, "WorldMapFrame")
  if not (wm and wm:IsShown()) then return false end
  if G.PanelsHeld(true) then return false end -- (the game's controller UI: the player's own to close)
  local hide = rawget(_G, "HideUIPanel")
  if not (hide and pcall(hide, wm)) or wm:IsShown() then wm:Hide() end
  return true
end
G.wmState = { on = false }
-- (The game loads its world map when first needed: after a /reload WorldMapFrame wasn't there yet, the hooks were never
-- made, and no open was set up (no size, no tick keeping the map's scale against the game's canvas zoom): drawn zoomed
-- in, the art alone, no route, 2026-11-13. Tried again as addons load, as Route Here's are.)
function G.InitWorldMapHost()
  if G.clone or G.HookWorldMap() or G.wmEvents or not CreateFrame then return end
  local f = CreateFrame("Frame")
  G.wmEvents = f
  f:RegisterEvent("ADDON_LOADED")
  f:SetScript("OnEvent", function(self)
    if G.HookWorldMap() then
      self:UnregisterAllEvents()
      local wm = rawget(_G, "WorldMapFrame")
      if wm and wm.IsShown and wm:IsShown() then G.WorldMapChanged() end -- (open already: set up now)
    end
  end)
end
function G.HookWorldMap()
  if G.wmHooked then return true end
  local wm = rawget(_G, "WorldMapFrame")
  if G.clone or not (wm and wm.HookScript) then return false end
  G.wmHooked = true
  if ns.db then ns.db.wmDiag = nil end -- (a record a test build kept there: let go)
  pcall(wm.HookScript, wm, "OnShow", function() G.WorldMapChanged() end)
  pcall(wm.HookScript, wm, "OnHide", function()
    -- (the map in it closed with stops placed: the route starts, as when the map's window closes)
    if G.wmState and G.wmState.on and G.ConfirmPendingOnClose then pcall(G.ConfirmPendingOnClose) end
    G.WorldMapChanged()
  end)
  local box = G.WorldMapBox()
  if box and box.HookScript then pcall(box.HookScript, box, "OnSizeChanged", function() G.WorldMapChanged() end) end
  local tick = CreateFrame("Frame", nil, UIParent)
  tick:SetScript("OnUpdate", function() G.WorldMapTick() end)
  if ns.TimeScript then ns.TimeScript(tick, "OnUpdate", "world map tick") end
  tick:Hide()
  G.wmTicker = tick
  -- (the clicks on the game's icons: G.WorldMapIconDown)
  local ok = pcall(tick.RegisterEvent, tick, "GLOBAL_MOUSE_DOWN")
  if ok then
    tick:SetScript("OnEvent", function(_, _, button)
      local ok2, err = pcall(G.WorldMapIconDown, button)
      if not ok2 then G.LogError("world map icon click", err) end
    end)
  end
  return true
end
-- The square's side (UI units) from the setting.
function G.MinimapSquareSide()
  return G.MINIMAP_SIDES[S().replaceMinimapSize or "small"] or G.MINIMAP_SIDES.small
end
-- The square's side while the map is the minimap square, else nil.
function G.MinimapSide()
  if not G.MinimapMode() then return nil end
  local m = G.mmState
  if m.side and InCombatLockdown and InCombatLockdown() then return m.side end -- (the Minimap's, till the fight ends)
  return G.MinimapSquareSide()
end
-- The game's minimap's radius in yards: the client's own (C_Minimap.GetViewRadius), else the zoom's measured size.
function G.MinimapRadius()
  local C = C_Minimap
  if C and C.GetViewRadius then
    local ok, r = pcall(C.GetViewRadius)
    if ok and not ns.IsSecret(r) and type(r) == "number" and r > 0 then return r end
  end
  local yd = ns.Layers and ns.Layers.MinimapYards and ns.Layers.MinimapYards()
  return yd and yd / 2 or nil
end
function G.MinimapRotates()
  return (GetCVar and GetCVar("rotateMinimap") == "1") and true or false
end
-- The view while it's the minimap: zoom (yards to the edge: the minimap's radius) and turn, else nil.
function G.MinimapView(facing)
  if not G.MinimapMode() then return nil end
  local r = G.MinimapRadius()
  if not r then return nil end
  return r, G.MinimapRotates() and -(facing or 0) or 0
end
function G.MinimapHideMode()
  return S().replaceMinimapHide == "mask" and "mask" or "ground"
end

-- (pcall'd: a client without one of these just skips it)
function G.MinimapCall(obj, method, ...)
  if G.clone then return false end -- (the second map: the game's Minimap is the first one's)
  local fn = obj and obj[method]
  if not fn then return false end
  return pcall(fn, obj, ...)
end

-- In an instance (a dungeon, a raid, a battleground, an arena) the game hides where the player is from addons, so
-- the square can't follow them: it showed the place they came in from, Orgrimmar from a battleground ("In
-- battlegrounds and this is my map, this is a problem", seen in game 2026-11-10). The square stays, and the game's
-- own minimap fills it while they're in there (it follows them there): square, at the square's size, its ground
-- drawn, the map's own picture under it not shown (asked 2026-11-11: "is it possible to keep the shape and still
-- use the game's map in instances so movement is still tracked?"). G.PlaceMinimapItself does it.
function G.Canvas() return canvas end -- (the map's picture: for the tests)
-- (and wherever the map can't follow the player, whatever the game says of instances: no position given, or the
-- player on a dungeon's own map. After a /reload with a route to a dungeon, at its entrance and after leaving it, the
-- game said "not in an instance" while it gave no position, and the square showed the dungeon's map: seen in game
-- 2026-11-11, 1.2.1. The square is the map only where the map knows where the player is.)
function G.MinimapAway()
  if G.clone then return false end
  local f = rawget(_G, "IsInInstance")
  if f then
    local ok, inside = pcall(f)
    if ok and inside then return true end
  end
  local okP, px, _, cont = pcall(Geo.PlayerWorld)
  if okP and not px then return true end
  local N = ns.Nav
  if okP and cont and N and N.InstanceLevel and N.InstanceLevel(cont) then return true end
  return false
end
-- Into an instance and out of one is seen from the game's events, and looked at again a few times a second besides:
-- the events alone left the square on the dungeon's map on the way in, and on it still on the way out ("when I enter
-- a dungeon the minimap is initially loaded with the GPS dungeon map ... when leaving the dungeon the minimap is back
-- on the dungeon map", seen in game 2026-11-11, 1.2.0). The square as it should be for where the player is now: the
-- game's minimap in it in an instance, the map following them out of one. Never in combat, nor while it's opened out.
G.MINIMAP_AWAY_CHECK = 0.25 -- s between looks
G.MINIMAP_AWAY_AGAIN = { 0.5, 1.5, 3 } -- s after the game's minimap is put in the square: made to draw once more
function G.MinimapAwayCheck(dt)
  local m = G.mmState
  if G.clone or not m.on then return false end
  m.awayWait = (m.awayWait or 0) + (dt or 0)
  if m.awayWait < G.MINIMAP_AWAY_CHECK then return false end
  m.awayWait = 0
  -- (the minimap's quest circles hidden again each look while it's the square: hidden once when it was placed, the big
  -- hatched circle was back over a quest's area, 2026-11-15, "this circle is still here from original wow minimap")
  if G.MinimapTaken() and not m.expanded then G.SetMinimapBlobs(G.MinimapBlobAlpha()) end
  if not m.applied or m.expanded or m.tween then return false end
  if InCombatLockdown and InCombatLockdown() then return false end
  local away = G.MinimapAway()
  if away == (m.awayIn or false) then return false end
  m.away, m.awayOpen = away or nil, nil
  G.ApplySettings()
  -- (out of it: the square on the player, not the dungeon's map)
  if not away and (browse or (free and free.instance)) then
    local waiting = pending
    G.Follow()
    pending = waiting
  end
  if ns.Arrow and ns.Arrow.Apply then pcall(ns.Arrow.Apply) end
  elapsed = 1
  return true
end
-- ... and whether the map has no window for it: the minimap replaced, in an instance, its key not pressed there.
function G.MinimapAwayHidden()
  return S().replaceMinimap == true and G.MinimapAway() and not G.mmState.awayOpen
end
-- A battleground or an arena: no routes, arrow or directions in there (asked 2026-11-10: "in battlegrounds, pause
-- routing and don't show arrow and directions while in there").
function ns.InBattleground()
  local f = rawget(_G, "IsInInstance")
  if not f then return false end
  local ok, inside, kind = pcall(f)
  return ok and inside and (kind == "pvp" or kind == "arena") or false
end

-- Asked for, or back: done now out of combat, else at PLAYER_REGEN_ENABLED (G.ApplySettings calls it first).
function G.ApplyMinimapReplace()
  local m = G.mmState
  if G.clone then -- (the second map: always the square, combat or not; nothing of the game's is taken for it)
    if not m.on then G.TakeMinimap() end
    m.queued = nil
    return
  end
  local want = S().replaceMinimap == true and Minimap ~= nil and frame ~= nil
  if not want and not m.on then
    m.queued = nil
    return
  end
  if InCombatLockdown and InCombatLockdown() then
    m.queued = true
    return
  end
  m.queued = nil
  if want then G.TakeMinimap() else G.ReleaseMinimap() end
end

-- The map as the minimap (the window's side of it): the square, its corner (`m.home`: the minimap's container and
-- size as first seen, kept while it's on). The game's Minimap itself is taken and given back by G.SyncMinimap.
function G.TakeMinimap()
  local m = G.mmState
  if m.on then return end
  if G.clone then -- (the second map: where the first one's square is)
    m.home = ns.realGPS.mmState.home
    m.on, m.expanded = true, nil
    if G.Follow then G.Follow() end
    G.drawVersion = G.drawVersion + 1
    return
  end
  m.home = { parent = Minimap:GetParent(), w = Minimap:GetWidth(), h = Minimap:GetHeight(),
    es = Minimap:GetEffectiveScale() }
  -- (where the minimap is in its container, when it isn't in its middle: a minimap addon that parents it to the
  -- whole screen and anchors it to a corner, EllesmereUI's; the square went to the wrong place, seen 2026-11-10)
  do
    local home, ues = m.home.parent or UIParent, UIParent:GetEffectiveScale() or 1
    local mx, my = Minimap:GetCenter()
    local hx, hy = home:GetCenter()
    if mx and my and hx and hy then
      local hes = home:GetEffectiveScale() or 1
      m.home.dx = (mx * m.home.es - hx * hes) / ues
      m.home.dy = (my * m.home.es - hy * hes) / ues
    end
  end
  m.on, m.expanded = true, nil
  if G.Follow then G.Follow() end -- (the minimap is always on the player)
  G.drawVersion = G.drawVersion + 1
end

-- Another addon moving the minimap after the square took its place (EllesmereUI's mover, issue #324): the square
-- stayed where the minimap first was, and the minimap went off it. Hooked on the Minimap's SetPoint and SetParent
-- (G.InitMinimapReplace; ours are G.minimapPlacing): its new place is read from its point, not its middle (while taken
-- it's the square's size, not its own), into `m.home` as G.TakeMinimap has it, its points kept to give back
-- (G.RestoreMinimap), and the square and the minimap placed again. Looked at once the frame's moves are done.
G.MINIMAP_MOVED_PX = 0.5 -- (a move under this: the same place)
G.MINIMAP_MOVED_MAX = 5 -- (placed again at most this often in MINIMAP_MOVED_SPAN s: another addon putting it back
G.MINIMAP_MOVED_SPAN = 2 -- each time we do isn't fought forever)
function G.AnchorFraction(point)
  point = type(point) == "string" and point:upper() or "CENTER"
  local fx = point:find("LEFT") and 0 or (point:find("RIGHT") and 1 or 0.5)
  local fy = point:find("BOTTOM") and 0 or (point:find("TOP") and 1 or 0.5)
  return fx, fy
end
-- The Minimap's points other than ours.
function G.MinimapOwnPoints()
  local pts = {}
  for i = 1, (Minimap:GetNumPoints() or 0) do
    local p = { Minimap:GetPoint(i) }
    if p[1] and (p[2] == nil or p[2] ~= G.mmAnchor) then pts[#pts + 1] = p end
  end
  return pts
end
-- Where the minimap's middle is by its first point, at its own size (`m.home.w`, `h`): its container, the middle's
-- offset from the container's (UIParent's units) and its effective scale; nil when it can't be told.
function G.MinimapHomeFromPoint()
  local home = G.mmState.home
  if G.clone or not home or type(Minimap) ~= "table" then return nil end
  local p = G.MinimapOwnPoints()[1]
  if not p then return nil end
  local parent = Minimap:GetParent() or UIParent
  local point, rel, relPoint, x, y = p[1], p[2], p[3], tonumber(p[4]) or 0, tonumber(p[5]) or 0
  if type(rel) == "string" then rel = _G[rel] end
  rel = rel or parent
  if type(rel) ~= "table" or not rel.GetLeft then return nil end
  local rl, rb, rw, rh = rel:GetLeft(), rel:GetBottom(), rel:GetWidth(), rel:GetHeight()
  local hx, hy = parent:GetCenter()
  if not (rl and rb and rw and rh and hx and hy) then return nil end
  local res, mes = rel:GetEffectiveScale() or 1, Minimap:GetEffectiveScale() or 1
  local hes, ues = parent:GetEffectiveScale() or 1, UIParent:GetEffectiveScale() or 1
  local rfx, rfy = G.AnchorFraction(relPoint or point)
  local fx, fy = G.AnchorFraction(point)
  local w = home.w or 0
  local h = home.h or w
  local cx = (rl + rfx * rw) * res + x * mes + (0.5 - fx) * w * mes
  local cy = (rb + rfy * rh) * res + y * mes + (0.5 - fy) * h * mes
  return parent, (cx - hx * hes) / ues, (cy - hy * hes) / ues, mes
end
function G.OnMinimapMoved()
  local m = G.mmState
  if G.clone or G.minimapPlacing or not m.on or not m.home then return false end
  local parent, dx, dy, es = G.MinimapHomeFromPoint()
  if not parent then return false end
  if m.was then m.was.points, m.was.parent = G.MinimapOwnPoints(), parent end -- (theirs, given back)
  local home = m.home
  local moved = home.parent ~= parent or math.abs((home.dx or 0) - dx) > G.MINIMAP_MOVED_PX
    or math.abs((home.dy or 0) - dy) > G.MINIMAP_MOVED_PX
  -- (taken, it's off the square's anchor now even where it's the same place)
  if not moved and not m.applied then return false end
  local now = GetTime and GetTime() or 0
  local mv = m.moves
  if not mv or now - mv.since > G.MINIMAP_MOVED_SPAN then
    mv = { since = now, n = 0 }
    m.moves = mv
  end
  if mv.n >= G.MINIMAP_MOVED_MAX then return false end
  mv.n = mv.n + 1
  home.parent, home.dx, home.dy, home.es = parent, dx, dy, es
  m.placedKey = nil -- (G.PlaceMinimapItself: the Minimap set on the anchor again)
  G.ApplySettings() -- (in combat: the window now, the Minimap after, m.queued)
  return true
end
-- (from the hooks: once the mover's ClearAllPoints and SetPoints are all done)
function G.MinimapMovedSoon()
  if G.minimapPlacing or G.minimapMovedWait or not G.mmState.on then return end
  if C_Timer and C_Timer.After then
    G.minimapMovedWait = true
    C_Timer.After(0, function()
      G.minimapMovedWait = nil
      local ok, err = pcall(G.OnMinimapMoved)
      if not ok then G.LogError("minimap moved", err) end
    end)
  else
    G.OnMinimapMoved()
  end
end

-- The window its own again; the Minimap given back by G.SyncMinimap.
function G.ReleaseMinimap()
  local m = G.mmState
  m.on, m.expanded, m.tween, m.keepOut = false, nil, nil, nil
  if G.mmTicker then G.mmTicker:Hide() end
  if G.mmEscape then m.closing = true G.mmEscape:Hide() m.closing = nil end
  G.drawVersion = G.drawVersion + 1
end

-- The game's Minimap taken while the map is the square, given back as it was otherwise (the option off, or the map
-- grown into the window: asked 2026-11-09, "restore the minimap to original state while the map is expanded out";
-- since 2026-11-15 only with `replaceMinimapKeepSquare` off, G.SquareKeptOut).
-- Never in combat: queued, and done as the map is then. True while it's taken.
function G.SyncMinimap()
  local m = G.mmState
  if G.clone then
    if not m.applied then G.CaptureMinimap() end
    return true
  end
  local want = m.on and (not m.expanded or G.SquareKeptOut()) and true or false
  if want ~= (m.applied or false) then
    if InCombatLockdown and InCombatLockdown() then
      m.queued = true
    elseif want then
      G.CaptureMinimap()
    else
      G.RestoreMinimap()
    end
  end
  return m.applied or false
end
function G.MinimapTaken()
  local m = G.mmState
  return (m.applied and not m.standIn) or false -- (standing in: the game's own, with our route on it as ever)
end
-- The square kept as it is while the map is grown out of it (`replaceMinimapKeepSquare`, on by default; asked
-- 2026-11-15: "keep our square minimap as is and still animate show the GPS map and collapsing it without ever
-- changing the current minimap. Show both"): the window grows out of the square and back as ever, and meanwhile the
-- second map (G.SetCloneActive) is the square, the game's Minimap left taken on it, the logo and the charm there too.
-- Nothing of the game's moves, in a fight or not. Off: the Minimap given back while the map is out (G.SyncMinimap).
function G.MinimapKeepsSquare()
  return not G.clone and S().replaceMinimapKeepSquare ~= false
end
-- (from its growing out till it's back in the square: `m.keepOut` as it opens, `m.goingBack` as it's sent back)
function G.SquareKeptOut()
  local m = G.mmState
  return (not G.clone and m.on and m.keepOut and (m.expanded or m.tween or m.goingBack)) and true or false
end

-- The second map on the square while the first is in the world map (the first one's side: made the first time it's
-- needed, shown and hidden), and the second one's own (`G.SetActive`: where the first one's square is, its looks).
function G.SetCloneActive(on)
  if G.clone then return end
  local c = ns.mapClone
  if on and not c and ns.MakeMapClone then
    local ok, made = pcall(ns.MakeMapClone)
    if ok and made then
      local ok2, err = pcall(made.Init)
      if ok2 then
        c = made
        ns.mapClone = c
      else
        G.LogError("second map", err)
        ns.MakeMapClone = nil -- (not tried again each frame)
      end
    elseif not ok then
      G.LogError("second map", made)
      ns.MakeMapClone = nil
    end
  end
  if c then
    local ok, err = pcall(c.SetActive, on and true or false)
    if not ok then G.LogError("second map", err) end
  end
end
function G.SetActive(on)
  if not G.clone or not frame then return end
  local real = ns.realGPS
  G.cloneActive = on
  if on then
    G.mmState.home = real.mmState.home
    G.ownFrameLook, G.ownRouteLook = real.ownFrameLook, real.ownRouteLook
  end
  G.ApplySettings()
  if on then
    G.ApplyMinimapChrome(true, true) -- (its border the square's, whatever the windows' looks set since)
    elapsed = 1
  end
end

-- The minimap as it is now (put back by G.RestoreMinimap): its points, size, mask, ground, alpha, art and the
-- GetMinimapShape global.
function G.CaptureMinimap()
  local m = G.mmState
  if G.clone then
    m.was, m.applied = { points = {}, art = {} }, true
    return
  end
  local was = { points = {}, mask = G.minimapMask, art = {}, shape = rawget(_G, "GetMinimapShape") }
  -- (never one of our own masks as "its own": taken again before the last one was put back, the square mask was
  -- remembered and the round minimap came back with square ground, seen in game 2026-11-10)
  if was.mask == G.MINIMAP_CLEAR or was.mask == G.MINIMAP_SQUARE then was.mask = G.mmOwnMask end
  G.mmOwnMask = was.mask
  for i = 1, (Minimap:GetNumPoints() or 0) do was.points[i] = { Minimap:GetPoint(i) } end
  was.w, was.h = Minimap:GetWidth(), Minimap:GetHeight()
  was.parent = Minimap:GetParent()
  was.es = Minimap:GetEffectiveScale()
  was.alpha = Minimap.GetAlpha and Minimap:GetAlpha() or 1
  local C = C_Minimap
  if C and C.GetDrawGroundTextures then
    local ok, d = pcall(C.GetDrawGroundTextures)
    if ok and type(d) == "boolean" then was.ground = d end
  end
  for _, name in ipairs(G.MINIMAP_ART) do
    local t = _G[name]
    if t and t.IsShown then was.art[name] = t:IsShown() and true or false end
  end
  m.was, m.applied = was, true
  m.hidden, m.side, m.shaped, m.placedKey, m.alpha, m.combatOut = nil, nil, nil, nil, nil, nil
  mm.route, mm.placed = nil, nil
end

-- Back as it was: points, size (its OnSizeChanged: other addons place their buttons again), mask, ground, alpha, art,
-- GetMinimapShape, the minimap buttons round it again, our route on it again.
function G.RestoreMinimap()
  local m = G.mmState
  local was = m.was
  m.was, m.applied, m.hidden, m.side, m.shaped, m.placedKey, m.alpha = nil, false, nil, nil, nil, nil, nil
  m.combatOut = nil
  m.standIn = nil
  if m.awayIn then
    m.awayIn = nil
    if canvas then canvas:SetShown(true) end
  end
  G.PlaceQueueEye(false)
  G.PlaceZoomButtons(false)
  G.PlaceDayNight(false)
  if not was or G.clone then return end
  G.minimapPlacing = true
  pcall(function()
    Minimap:ClearAllPoints()
    for _, p in ipairs(was.points) do Minimap:SetPoint(unpack(p)) end
  end)
  G.minimapPlacing = nil
  if was.w and was.h then Minimap:SetSize(was.w, was.h) end
  if was.strata then G.MinimapCall(Minimap, "SetFrameStrata", was.strata) end
  local mask = was.mask or G.MINIMAP_ROUND
  if not G.MinimapCall(Minimap, "SetMaskTexture", mask) then
    mask = G.MINIMAP_ROUND
    G.MinimapCall(Minimap, "SetMaskTexture", mask)
  end
  G.OnMinimapMask(mask) -- (as the hook does in the game: the next take remembers this one)
  -- (and once more a moment later: set in the frame the minimap changes size, it sometimes didn't take)
  if C_Timer and C_Timer.After then
    for _, s in ipairs(G.MINIMAP_MASK_AGAIN) do
      C_Timer.After(s, function() G.MinimapMaskAgain(mask) end)
    end
  end
  if C_Minimap and C_Minimap.SetDrawGroundTextures then pcall(C_Minimap.SetDrawGroundTextures, was.ground ~= false) end
  G.MinimapCall(Minimap, "SetAlpha", was.alpha or 1)
  G.SetMinimapBlobs(G.MINIMAP_BLOB_DEFAULT)
  for name, shown in pairs(was.art) do
    local t = _G[name]
    if t and t.SetShown then t:SetShown(shown) end
  end
  _G.GetMinimapShape = was.shape
  G.MinimapRedraw() -- (drawn now as given back, standing still too)
  G.drawVersion = G.drawVersion + 1
  mm.route, mm.placed = nil, nil -- (the route on it drawn again)
  G.RefreshMinimapButtons()
end

-- The minimap's own mask set again while it's still given back (not taken since, not in combat).
function G.MinimapMaskAgain(mask)
  local m = G.mmState
  if m.applied or (InCombatLockdown and InCombatLockdown()) then return false end
  if G.minimapMask ~= mask then return false end -- (something else has set another since: theirs stays)
  local ok = G.MinimapCall(Minimap, "SetMaskTexture", mask) and true or false
  G.MinimapRedraw()
  return ok
end
-- The game draws its minimap again only as the player moves: given back while they stand still, it kept the square's
-- picture, the ground square past its round border ("still see this bug when standing still, opening the GPS map
-- from minimap mode, if I'm moving and I open it looks normal", seen in game 2026-11-11). Its zoom set to another
-- level and back makes it draw now: the same zoom after as before.
function G.MinimapRedraw()
  if G.clone or type(Minimap) ~= "table" or not (Minimap.GetZoom and Minimap.SetZoom) then return false end
  local okZ, z = pcall(Minimap.GetZoom, Minimap)
  if not okZ or type(z) ~= "number" then return false end
  local levels = 6
  if Minimap.GetZoomLevels then
    local okL, n = pcall(Minimap.GetZoomLevels, Minimap)
    if okL and type(n) == "number" then levels = n end
  end
  if levels < 2 then return false end
  local other = z + 1 < levels and z + 1 or z - 1
  if other < 0 then return false end
  G.minimapRedrawing = true
  local ok = pcall(Minimap.SetZoom, Minimap, other)
  pcall(Minimap.SetZoom, Minimap, z)
  G.minimapRedrawing = nil
  return ok
end

-- The square's corner: the one nearest the screen's, where the old minimap's square had it (anchored to the
-- minimap's own container: Edit Mode moving it moves the square). corner, home, x, y.
function G.MinimapCorner(side)
  local was = G.mmState.home or {}
  local home = was.parent or UIParent
  local ues = UIParent:GetEffectiveScale() or 1
  local hx, hy = home:GetCenter()
  local hes = home:GetEffectiveScale() or 1
  if not (hx and hy) then return "TOPRIGHT", home, 0, 0 end
  local sw, sh = G.Screen()
  local dx, dy = was.dx or 0, was.dy or 0 -- (the old minimap's middle from its container's)
  local cx, cy = hx * hes / ues + dx, hy * hes / ues + dy
  local right, top = cx > sw / 2, cy > sh / 2
  -- (the old minimap's half side, in the map's units)
  local half = (was.w or side) / 2 * (was.es or ues) / ues
  return (top and "TOP" or "BOTTOM") .. (right and "RIGHT" or "LEFT"), home, dx + (right and half or -half),
    dy + (top and half or -half), right, top
end

-- The window as the square, in the minimap's corner (our frame: in combat too).
function G.PlaceMinimapFrame(side)
  local corner, home, ox, oy = G.MinimapCorner(side)
  frame:ClearAllPoints()
  frame:SetPoint(corner, home, "CENTER", ox, oy)
end

-- The Minimap on the square: on an anchor of its own in the square's place (not on the window, which grows into the
-- window and back, in combat too), the same size as the map's canvas, its ground hidden, its art hidden, square to
-- the minimap buttons. Out of combat only.
-- The game's group finder eye (QueueStatusButton): the game hangs it on the round minimap's edge by an offset from
-- the minimap's middle, which on the bigger square is in the middle of the map ("looking for group eyeball is
-- center of minimap", seen in game 2026-11-10). While the square is on it sits outside the square's top left; where
-- the player moved it themselves (Edit Mode), it's left alone. Its own place comes back with the minimap.
G.QUEUE_EYE_AT = { "TOPRIGHT", "TOPLEFT", -2, -34 }
function G.PlaceQueueEye(on)
  if G.clone then return end
  -- (never with the game's controller UI on: the eye is the group finder's, and with it on the game runs its own
  -- protected code as the queue and its dungeon-ready popup show; an eye an addon moved made that ADDON_ACTION_FORBIDDEN
  -- on joining a dungeon, a player's report 2026-11-16: "crashed when joining dungeons with gamepad UI ... crashes all
  -- addons". Put back if it was moved: the controller UI turned on later)
  if on and G.ControllerUI and G.ControllerUI() then on = false end
  local b = rawget(_G, "QueueStatusButton")
  if type(b) ~= "table" or not (b.SetPoint and b.ClearAllPoints) then return end
  local m = G.mmState
  if on then
    local a = G.mmAnchor
    if not a then return end
    if not m.eye then
      if b.IsInDefaultPosition then
        local ok, default = pcall(b.IsInDefaultPosition, b)
        if ok and default == false then return end -- (theirs: put somewhere by hand)
      end
      local pts = {}
      for i = 1, (b.GetNumPoints and b:GetNumPoints() or 0) do pts[i] = { b:GetPoint(i) } end
      m.eye = pts
    end
    local at = G.QUEUE_EYE_AT
    G.eyeMoving = true
    pcall(function()
      b:ClearAllPoints()
      b:SetPoint(at[1], a, at[2], at[3], at[4])
    end)
    G.eyeMoving = nil
    -- (the game puts it back by the minimap whenever its layout is gone over: ours again after)
    if not G.eyeHooked and hooksecurefunc and b.UpdateDefaultAnchor then
      G.eyeHooked = true
      pcall(hooksecurefunc, b, "UpdateDefaultAnchor", function()
        if G.mmState.eye and not G.eyeMoving then G.PlaceQueueEye(true) end
      end)
    end
  elseif m.eye then
    local pts = m.eye
    m.eye = nil
    G.eyeMoving = true
    pcall(function()
      if #pts > 0 then
        b:ClearAllPoints()
        for _, p in ipairs(pts) do b:SetPoint(unpack(p)) end
      end
    end)
    G.eyeMoving = nil
  end
end

-- The game's minimap zoom buttons (+ and -, shown while the pointer is over the minimap) and the area that keeps them
-- up: the game puts them by fixed offsets from the round minimap's middle, which on the bigger square is inside the
-- map ("can these be moved?", seen in game 2026-11-11). On the square they're in its bottom right corner, + over -;
-- their own places come back with the minimap.
G.ZOOM_BUTTONS_AT = { ZoomIn = { -12, 30 }, ZoomOut = { -12, 13 }, ZoomHitArea = { -14, 20 } }
function G.PlaceZoomButtons(on)
  if G.clone or type(Minimap) ~= "table" then return end
  local m = G.mmState
  if on then
    if m.zoomWas then return end
    m.zoomWas = {}
    for key, at in pairs(G.ZOOM_BUTTONS_AT) do
      local b = Minimap[key]
      if type(b) == "table" and b.SetPoint and b.ClearAllPoints then
        local pts = {}
        for i = 1, (b.GetNumPoints and b:GetNumPoints() or 0) do pts[i] = { b:GetPoint(i) } end
        m.zoomWas[key] = pts
        pcall(function()
          b:ClearAllPoints()
          b:SetPoint("CENTER", Minimap, "BOTTOMRIGHT", at[1], at[2])
        end)
      end
    end
  elseif m.zoomWas then
    local was = m.zoomWas
    m.zoomWas = nil
    for key, pts in pairs(was) do
      local b = Minimap[key]
      if type(b) == "table" and #pts > 0 then
        pcall(function()
          b:ClearAllPoints()
          for _, p in ipairs(pts) do b:SetPoint(unpack(p)) end
        end)
      end
    end
  end
end

-- The game's day and night button (MinimapCluster.DielFrame, the sun or the moon): the game puts it by a fixed offset
-- from the minimap container's middle, on the round minimap's rim, which on the square is in its top edge ("what about
-- this one? maybe top right corner", seen in game 2026-11-11). On the square it's on its top right corner; the game
-- places it again whenever the minimap's Edit Mode scale is set, so ours again after; its own place comes back with
-- the minimap.
G.DAY_NIGHT_AT = { "CENTER", "TOPRIGHT", -4, -4 }
function G.PlaceDayNight(on)
  if G.clone then return end
  local cluster = rawget(_G, "MinimapCluster")
  local b = type(cluster) == "table" and cluster.DielFrame or nil
  if type(b) ~= "table" or not (b.SetPoint and b.ClearAllPoints) then return end
  local m = G.mmState
  if on then
    local a = G.mmAnchor
    if not a then return end
    if not m.dayNight then
      local pts = {}
      for i = 1, (b.GetNumPoints and b:GetNumPoints() or 0) do pts[i] = { b:GetPoint(i) } end
      m.dayNight = pts
    end
    local at = G.DAY_NIGHT_AT
    pcall(function()
      b:ClearAllPoints()
      b:SetPoint(at[1], a, at[2], at[3], at[4])
    end)
    if not G.dayNightHooked and hooksecurefunc and cluster.SetEditModeScale then
      G.dayNightHooked = true
      pcall(hooksecurefunc, cluster, "SetEditModeScale", function()
        if G.mmState.dayNight then G.PlaceDayNight(true) end
      end)
    end
  elseif m.dayNight then
    local pts = m.dayNight
    m.dayNight = nil
    pcall(function()
      if #pts > 0 then
        b:ClearAllPoints()
        for _, p in ipairs(pts) do b:SetPoint(unpack(p)) end
      end
    end)
  end
end

function G.PlaceMinimapItself(side)
  if G.clone then return end
  local m = G.mmState
  local was = m.was
  if not (was and frame and canvas) then return end
  local a = G.mmAnchor
  if not a then
    a = CreateFrame("Frame", nil, UIParent)
    a:EnableMouse(false)
    G.mmAnchor = a
  end
  local corner, home, ox, oy = G.MinimapCorner(side)
  a:ClearAllPoints()
  a:SetPoint(corner, home, "CENTER", ox, oy)
  a:SetSize(side, side)
  -- (the game's Minimap touched only when something changed: the size, the scale, the way its ground is hidden, or
  -- its mask or ground set by something else since; every settings change re-set them all, and opening the options
  -- brought a round white disc over the square, the user 2026-11-09)
  local inner = side - 2 * BORDER
  local k = (frame:GetEffectiveScale() or 1) / (Minimap:GetEffectiveScale() or 1)
  -- (the map in the game's world map window meanwhile: the game's Minimap stands in for it on the square, in the
  -- same place at the same size, square, with its own ground, its border and our route on it)
  local how = G.MinimapHideMode()
  -- (in an instance: the game's minimap itself in the square, G.MinimapAway)
  local away = G.MinimapAway()
  if away then how = "away" end
  if (m.awayIn or false) ~= away then
    m.awayIn = away or nil
    canvas:SetShown(not away)
  end
  local key = string.format("%s:%d:%.5f", how, side, k)
  local fresh = m.placedKey ~= key
  m.placedKey = key
  if fresh then
    G.minimapPlacing = true -- (ours: G.OnMinimapMoved leaves it)
    local okP, errP = pcall(function()
      Minimap:ClearAllPoints()
      Minimap:SetPoint("CENTER", a, "CENTER", 0, 0)
    end)
    G.minimapPlacing = nil
    if not okP then error(errP, 0) end
    Minimap:SetSize(inner * k, inner * k)
    G.SetMinimapBlobs(G.MinimapBlobAlpha()) -- (its quest areas: the map's own instead, while they're drawn)
    G.PlaceQueueEye(true)
    G.PlaceZoomButtons(true)
    G.PlaceDayNight(true)
    -- (the game's own dots, the herbs and ore it tracks, over the map's icons: they show a node is really there now,
    -- ours only where one was found before. Asked 2026-11-10. The map is in the lowest strata, so the Minimap is
    -- over it wherever it isn't in that one too; then it's lifted one, and put back with the rest.)
    if Minimap.GetFrameStrata and Minimap:GetFrameStrata() == "BACKGROUND" then
      was.strata = "BACKGROUND"
      G.MinimapCall(Minimap, "SetFrameStrata", "LOW")
    end
  end
  local mask = how == "mask" and G.MINIMAP_CLEAR or G.MINIMAP_SQUARE
  local ground = how == "away" or (how == "mask" and was.ground ~= false)
  -- (the game's minimap just put in the square: the game draws it again only as the player moves, and it was a black
  -- square on the way into a dungeon until they did, seen in game 2026-11-11. Made to draw now, and again a moment
  -- later: the place is still loading at first.)
  local drawNow = fresh and how == "away"
  if fresh or G.minimapMask ~= mask then
    if G.MinimapCall(Minimap, "SetMaskTexture", mask) then
      G.OnMinimapMask(mask) -- (as the hook does in the game)
    elseif how == "mask" then
      G.MinimapCall(Minimap, "SetMaskTexture", was.mask or G.MINIMAP_ROUND) -- (failed: its own back, never blank)
    end
  end
  local C = C_Minimap
  if C and C.SetDrawGroundTextures then
    local now
    if C.GetDrawGroundTextures then
      local ok, d = pcall(C.GetDrawGroundTextures)
      if ok then now = d end
    end
    if fresh or now ~= ground then pcall(C.SetDrawGroundTextures, ground) end
  end
  for name in pairs(was.art) do
    local t = _G[name]
    if t and t.IsShown and t:IsShown() then t:Hide() end
  end
  if drawNow then
    G.MinimapRedraw()
    if C_Timer and C_Timer.After then
      for _, s in ipairs(G.MINIMAP_AWAY_AGAIN) do
        C_Timer.After(s, function()
          if G.mmState.awayIn and G.mmState.applied and not (InCombatLockdown and InCombatLockdown()) then G.MinimapRedraw() end
        end)
      end
    end
  end
  -- (the minimap buttons, LibDBIcon's and ours, on the square's edge, not round the old circle)
  if not m.shaped then
    _G.GetMinimapShape = G.SquareMinimapShape
    m.shaped = true
  end
  local moved = m.hidden ~= how or m.side ~= side
  m.hidden, m.side = how, side
  if moved then G.RefreshMinimapButtons() end
end
function G.SquareMinimapShape() return "SQUARE" end

-- The map grown out of the square in a fight: the game's Minimap can't be given back till the fight ends (it can't be
-- moved), so it shows where it is, in the square's place, as the game's own minimap: square, its ground drawn. Unseen,
-- the player had no minimap for the fight ("when expanding the map in combat the game's minimap isn't drawn back
-- yet", seen in game 2026-11-12). Back into the square in the same fight: its ground and mask hidden again as the
-- square has them. Only the mask, the ground and the alpha: all allowed in combat.
function G.MinimapCombatStandIn(on)
  local m = G.mmState
  on = on and true or nil
  if G.clone or not m.applied or m.combatOut == on then return end
  m.combatOut = on
  local how = m.hidden or G.MinimapHideMode()
  local mask = on and G.MINIMAP_SQUARE or (how == "mask" and G.MINIMAP_CLEAR or G.MINIMAP_SQUARE)
  local ground = on or how == "away" or (how == "mask" and m.was ~= nil and m.was.ground ~= false)
  if G.minimapMask ~= mask and G.MinimapCall(Minimap, "SetMaskTexture", mask) then G.OnMinimapMask(mask) end
  local C = C_Minimap
  if C and C.SetDrawGroundTextures then pcall(C.SetDrawGroundTextures, ground and true or false) end
end

-- The minimap buttons placed again: LibDBIcon's (every addon's that uses it) by its own position update, ours.
function G.RefreshMinimapButtons()
  local LS = rawget(_G, "LibStub")
  local ok, lib = false, nil
  if LS then ok, lib = pcall(LS, "LibDBIcon-1.0", true) end
  if ok and type(lib) == "table" then
    if lib.SetButtonRadius and type(lib.radius) == "number" then
      pcall(lib.SetButtonRadius, lib, lib.radius) -- (every button's position again; nothing else touched)
    elseif lib.GetButtonList and lib.Refresh then
      local okL, names = pcall(lib.GetButtonList, lib)
      for _, n in ipairs(okL and names or {}) do pcall(lib.Refresh, lib, n) end
    end
  end
  local O = ns.Options
  if O and O.button and O.UpdateButton then pcall(O.UpdateButton) end
end

-- The square's chrome: the window's border without its title band, no title, logo or buttons (everything on it but
-- its border hidden, and shown again as it was); the window's own when it isn't the square.
function G.ApplyMinimapChrome(compact, force)
  local c = G.chrome
  if not c then return end
  c:ClearAllPoints()
  if compact then
    -- (the plain metal border's pieces sit unevenly round their frame: the game's layout puts the left ones 5 out,
    -- the right ones 2, the bottom ones 3 down, and the metal line is 5 in from a piece's outer edge. Square on our
    -- frame, the line ran 5 from the map on the left and 2 on the right, on the map's top edge and 3 under its
    -- bottom: "the map and its border is off by a bit", seen in game 2026-11-10. These put the line on the middle
    -- of the frame's own edge all round.)
    local o = G.MINIMAP_BORDER_FIT
    c:SetPoint("TOPLEFT", frame, "TOPLEFT", o[1], o[2])
    c:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", o[3], o[4])
  else
    c:SetPoint("TOPLEFT", frame, "TOPLEFT", -2, CHROME_TITLE)
    c:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", 2, -2)
  end
  local changed = (G.mmChromeCompact or false) ~= compact
  G.mmChromeCompact = compact
  if changed or force then
    if c.SetBorder then pcall(c.SetBorder, c, compact and G.MINIMAP_BORDER or "ButtonFrameTemplateNoPortrait") end
  end
  if compact then
    -- (everything on it but its border, each time: the logo's look, the title's slots show theirs again)
    G.mmChromeHid = G.mmChromeHid or {}
    for _, kid in ipairs({ c:GetChildren() }) do
      if kid ~= c.NineSlice and kid:IsShown() then
        kid:Hide()
        G.mmChromeHid[kid] = true
      end
    end
  elseif changed then
    for kid in pairs(G.mmChromeHid or {}) do kid:Show() end
    G.mmChromeHid = nil
  end
  if G.chromeStrip then G.chromeStrip:SetShown(not compact) end
  if changed or force then G.ApplyFrameLook() end
end
-- The square's look again after the windows' logo look was applied (ns.ApplyLogoLook: the options window opening the
-- first time, a logo setting, the UI's scale): it gives every window its titled border and its logo back.
function G.KeepMinimapChrome()
  if G.mmChromeCompact then G.ApplyMinimapChrome(true, true) end
  -- (the second map's: every window got its titled border back, so the square had a title bar over it, seen in game
  -- 2026-11-10)
  if not G.clone and ns.mapClone and ns.mapClone.KeepMinimapChrome then pcall(ns.mapClone.KeepMinimapChrome) end
end

-- The square grown into the usual window to set a route (`on`), or back to the square: animated, the window drawn over
-- every other one while it's out. The game's Minimap stays on the square, unseen meanwhile.
function G.SetMinimapExpanded(on, own)
  local m = G.mmState
  on = on and true or nil
  -- (the option: the game's world map opens instead, the map in it; `own`: in a fight, where it can't, G.ToggleMapView)
  if on and not own and G.WorldMapWanted() then
    if not G.WorldMapHosted() then G.ToggleWorldMap() end
    return
  end
  if not m.on or m.expanded == on or not frame then return end
  -- (sent back to the square: stops placed meanwhile start the route, as when the map's window closes)
  if not on and not G.clone and G.ConfirmPendingOnClose then G.ConfirmPendingOnClose() end
  -- (back to the square mid-fight: not till it ends. The square needs the game's Minimap, which can't be moved in
  -- combat; shrunk anyway, the map was left at the window's size and place with the square's look, no buttons and no
  -- player arrow, the game's minimap back in its corner, seen in game 2026-11-12. The fight's start, before the
  -- lockdown, goes back at once: G.MinimapCombatStarts.)
  -- (grown in this fight, the Minimap still on the square, unseen: back at once, nothing of the game's moves)
  if not on and not G.clone and not m.applied and InCombatLockdown and InCombatLockdown() then
    m.backAfterCombat = true
    return
  end
  m.backAfterCombat = nil
  local l0, b0, w0, h0 = frame:GetRect()
  if on then m.keepOut = G.MinimapKeepsSquare() or nil end -- (the square kept meanwhile: G.SquareKeptOut)
  m.expanded = on
  -- (back into the square: the square is never a dungeon's map or any map looked at, it's on the player; a dungeon's
  -- map opened from its entrance, or the one the player is in, shows on the opened map only. 1.2.1, asked 2026-11-11:
  -- "Collapsing the map with dungeon map up never replaces the minimap with the dungeon map")
  -- (only those: a spot panned to, a route's tour and stops waiting to start are left as they are)
  if not on and (browse or (free and free.instance)) and G.Follow then
    local waiting = pending
    G.Follow()
    pending = waiting
  end
  m.activeAt = GetTime()
  m.wasMoving = G.PlayerMoving() -- (moving already as it opens: not a start)
  m.goingBack = not on or nil -- (the square kept till the window's back in it)
  G.ApplySettings() -- (its place and size as it ends: the window's own, or the square)
  m.goingBack = nil
  local l1, b1, w1, h1 = frame:GetRect()
  if l0 and l1 and G.MINIMAP_TWEEN > 0 then
    m.tween = { t = 0, from = { l0, b0, w0, h0 }, to = { l1, b1, w1, h1 } }
    G.MinimapTween(0)
  end
  if not on and not m.tween and m.keepOut then -- (back with no animation: the square the map's own again now)
    m.keepOut = nil
    G.ApplySettings()
  end
  if G.mmEscape then
    m.closing = true
    G.mmEscape:SetShown(on and true or false)
    m.closing = nil
  end
  if G.mmTicker then G.mmTicker:SetShown(on or m.tween ~= nil) end
end
-- One step of the animation: the window's rect between where it was and where it ends (eased out); at the end its
-- own anchors again.
function G.MinimapTween(dt)
  local m = G.mmState
  local tw = m.tween
  if not tw then return end
  tw.t = tw.t + (dt or 0)
  local k = math.min(1, tw.t / G.MINIMAP_TWEEN)
  local e = 1 - (1 - k) * (1 - k)
  local a, b = tw.from, tw.to
  local function At(i) return a[i] + (b[i] - a[i]) * e end
  frame:ClearAllPoints()
  frame:SetPoint("BOTTOMLEFT", UIParent, "BOTTOMLEFT", At(1), At(2))
  frame:SetSize(At(3), At(4))
  if k >= 1 then
    m.tween = nil
    if not m.expanded then m.keepOut = nil end -- (back in the square: the second map put away)
    G.ApplySettings()
  end
end
-- The expanded window's quiet clock: the mouse over it, a drag, its search or menu open, stops waiting to start a
-- route, the road tools on: busy; any click, drag or zoom on it (lastActivity) too. Quiet MINIMAP_IDLE s: back.
function G.MinimapIdle(now)
  local m = G.mmState
  if not (m.expanded and not m.tween) then return end
  if frame:IsMouseOver() or drag or G.lasso or G.drawMode or G.roadMode or G.wallMode or #pending > 0
      or (G.searchPanel and G.searchPanel:IsShown()) or (G.mapMenu and G.mapMenu:IsShown())
      or (ns.PopupOverShown and ns.PopupOverShown()) -- (a popup over it, the options: in use)
      or G.mmHold then -- (held out: the tutorial's steps on the whole map, Tutorial.lua)
    m.activeAt = now
  end
  if lastActivity > (m.activeAt or 0) then m.activeAt = lastActivity end
  local idle = G.MinimapIdleSeconds()
  if idle > 0 and now - (m.activeAt or now) >= idle then G.SetMinimapExpanded(false) return end
  -- (the option: back as the player starts moving; walking already when it opened isn't a start, turning in place
  -- isn't moving. Its search open too (asked 2026-11-15: "it doesn't close the map unless player actually picks
  -- something from the search but it should anyway"): keys typed in its box don't move the player)
  local moving = G.PlayerMoving()
  local started = moving and not m.wasMoving
  m.wasMoving = moving
  if started and S().replaceMinimapCollapseOnMove then
    G.CloseMapMenus()
    G.SetMinimapExpanded(false)
  end
end
-- The option: back as a fight starts (the window only; the Minimap taken again when it's allowed).
function G.MinimapCombatStarts()
  local m = G.mmState
  if m.expanded and S().replaceMinimapCollapseOnCombat then
    G.SetMinimapExpanded(false)
    -- (at once, no animation: the square and the Minimap placed while that's still allowed, before the lockdown)
    if m.tween and not m.expanded then
      m.tween.t = G.MINIMAP_TWEEN
      G.MinimapTween(0)
    end
  end
  -- (the world map opened by the logo or the key: closed the same way)
  if G.wmState.on and G.wmState.byUs and S().replaceMinimapCollapseOnCombat then G.CloseWorldMap() end
end
function G.MinimapTick(dt)
  local m = G.mmState
  if m.tween then G.MinimapTween(dt) end
  if m.expanded and ns.LiftShownPopups then ns.LiftShownPopups() end -- (a popup opened over it)
  G.MinimapIdle(GetTime())
  if G.mmTicker and not (m.expanded or m.tween) then G.mmTicker:Hide() end
end

-- The square's button: the window's corner logo hanging over the square's bottom-left corner as the window's hangs over
-- its top-left (its middle `size * 0.42` in and TITLE_MID up from the corner, Core's FitCorner mirrored), out to the
-- window; on the window, an arrow back into the corner beside its bottom-left corner (the map menu's button is in it).
function G.PlaceMinimapButton()
  local b = G.mmButton
  if not b then return end
  local m = G.mmState
  -- (the window's own arrow while the logo stays on the kept square, G.mmBack: beside the window's bottom-left corner,
  -- pointing into the minimap's corner as the one on the window did)
  local back = G.mmBack
  if back then
    local keptOut = m.on and m.expanded and G.SquareKeptOut() and not G.WorldMapHosted()
    back:SetShown(keptOut and true or false)
    if keptOut then
      local _, _, _, _, r, t = G.MinimapCorner(G.MinimapSquareSide())
      back.icon:SetRotation((math.atan2 or math.atan)(-(r == false and -1 or 1), t == false and -1 or 1))
      back:ClearAllPoints()
      if (frame:GetLeft() or 100) < 30 then
        back:SetPoint("BOTTOMLEFT", frame, "BOTTOMRIGHT", 6, 0)
      else
        back:SetPoint("BOTTOMRIGHT", frame, "BOTTOMLEFT", -6, 0)
      end
    end
  end
  -- (the map in the world map meanwhile: the logo stays on the square's corner, on the minimap standing in there)
  local host = G.WorldMapHosted()
  local kept = G.SquareKeptOut() -- (the square kept while the map's out: the logo stays on it too)
  local sq = host or kept
  local on = sq and G.mmAnchor or frame
  local shown = m.on and (not sq or G.mmAnchor ~= nil)
  local parent = sq and UIParent or frame -- (the world map's picture ends at its own edge)
  if b:GetParent() ~= parent then
    b:SetParent(parent)
    b:SetFrameLevel((parent:GetFrameLevel() or 1) + 30 + G.ArtSpan())
  end
  b:SetShown(shown and true or false)
  if not shown then return end
  local _, _, _, _, right, top = G.MinimapCorner(G.MinimapSquareSide())
  local x, y = right == false and -1 or 1, top == false and -1 or 1 -- (toward the screen's corner)
  b.icon:SetRotation((math.atan2 or math.atan)(-x, y))
  -- (on the square: the window's corner logo, small, pixel for pixel; on the window: the arrow back into the corner)
  local logo = not m.expanded or kept
  b.icon:SetShown(not logo)
  b.bg:SetShown(not logo)
  b.hl:SetShown(not logo)
  b.logo:SetShown(logo)
  b.logoHl:SetShown(logo)
  if logo then
    local size = ns.ShowCornerLogo(b.logo, G.MinimapLogoUnits(), frame:GetEffectiveScale())
    ns.ShowCornerLogo(b.logoHl, G.MinimapLogoUnits(), frame:GetEffectiveScale())
    b:SetSize(size, size)
    b.logoSize = size
  else
    b:SetSize(20, 20)
  end
  b:SetFrameStrata(not logo and G.MINIMAP_EXPANDED_STRATA or "MEDIUM") -- (over the game's Minimap on the square)
  b:ClearAllPoints()
  if logo then
    -- (hanging below the bottom by the share the window's hangs over its top, for its size)
    local size = b.logoSize or 0
    b:SetPoint("CENTER", on, "BOTTOMLEFT", size * G.MINIMAP_LOGO_IN,
      ((ns.TITLE_MID or 11) - 2) * size / (ns.CORNER_LOGO_UNITS or 62))
  elseif (frame:GetLeft() or 100) < 30 then
    b:SetPoint("BOTTOMLEFT", frame, "BOTTOMRIGHT", 6, 0)
  else
    b:SetPoint("BOTTOMRIGHT", frame, "BOTTOMLEFT", -6, 0)
  end
end

-- What it's doing, for /agps replace status: the radius both ways, the turn, the hiding.
function G.MinimapReplaceStatus()
  local m = G.mmState
  local r
  if C_Minimap and C_Minimap.GetViewRadius then
    local ok, v = pcall(C_Minimap.GetViewRadius)
    r = ok and not ns.IsSecret(v) and v or nil
  end
  local yd = ns.Layers and ns.Layers.MinimapYards and ns.Layers.MinimapYards()
  return string.format(L["minimap replaced: %s%s%s, minimap taken %s, size %s, ground hidden by %s; radius %s yd (game), %s yd (zoom table); zoom %s, rotates %s"], tostring(m.on), m.expanded and L[" (expanded)"] or "", m.queued and L[" (after combat)"] or "",
    tostring(m.applied or false),
    tostring(S().replaceMinimapSize), G.MinimapHideMode(), r and string.format("%.1f", r) or "?",
    yd and string.format("%.1f", yd / 2) or "?", tostring(Minimap and Minimap.GetZoom and Minimap:GetZoom()),
    tostring(G.MinimapRotates()))
end

-- The game's controller UI turned on or off (its Gamepad options; asked 2026-11-11: "addon should work with and
-- without this mode"). The game changes its Edit Mode layout with it, so its minimap is somewhere else, at another
-- size: the square is given back to the game first (what was kept of the minimap's old place is of the old layout),
-- then taken again once the new layout is in place. In combat, it waits for the fight's end as any change does.
G.INPUT_CHANGE_WAIT = 0.5 -- s for the game's new layout to be in place
function G.MinimapInputChanged()
  local m = G.mmState
  if not (m.on or m.queued) or S().replaceMinimap ~= true then return false end
  if not (InCombatLockdown and InCombatLockdown()) then
    S().replaceMinimap = false
    local ok = pcall(G.ApplySettings)
    S().replaceMinimap = true
    if not ok then return false end
  end
  local function Again()
    if S().replaceMinimap == true then G.ApplySettings() end
  end
  if C_Timer and C_Timer.After then C_Timer.After(G.INPUT_CHANGE_WAIT, Again) else Again() end
  return true
end

-- Its events: combat's end (a change held back), the minimap's zoom and turn (drawn again at once), Edit Mode and the
-- UI's scale (placed again: the minimap's size is in its own scale). Its button, the expanded window's clock and
-- Escape (a stand-in in UISpecialFrames, shown while it's out: Escape takes it back to the square).
function G.InitMinimapReplace()
  if G.mmEvents then return end
  if G.clone then -- (the second map: its zoom's events only; the button, Escape and combat are the first one's)
    local zoomEv = CreateFrame("Frame")
    for _, e in ipairs({ "MINIMAP_UPDATE_ZOOM", "CVAR_UPDATE" }) do pcall(zoomEv.RegisterEvent, zoomEv, e) end
    zoomEv:SetScript("OnEvent", function() elapsed = 1 end)
    G.mmEvents = zoomEv
    return
  end
  local ev = CreateFrame("Frame")
  for _, e in ipairs({ "PLAYER_REGEN_ENABLED", "PLAYER_REGEN_DISABLED", "MINIMAP_UPDATE_ZOOM", "CVAR_UPDATE", "EDIT_MODE_LAYOUTS_UPDATED",
      "UI_SCALE_CHANGED", "DISPLAY_SIZE_CHANGED", "PLAYER_ENTERING_WORLD", "ZONE_CHANGED_NEW_AREA",
      "INPUT_DEVICE_INTERFACE_TRANSITION" }) do
    pcall(ev.RegisterEvent, ev, e) -- (one this client lacks is skipped)
  end
  ev:SetScript("OnEvent", function(_, e)
    local m = G.mmState
    if e == "PLAYER_REGEN_ENABLED" then
      if m.queued then G.ApplySettings() end
      if m.backAfterCombat then -- (asked for mid-fight: G.SetMinimapExpanded)
        m.backAfterCombat = nil
        if m.expanded then G.SetMinimapExpanded(false) end
      end
    elseif e == "PLAYER_REGEN_DISABLED" then
      G.MinimapCombatStarts()
    elseif e == "MINIMAP_UPDATE_ZOOM" or e == "CVAR_UPDATE" then
      if m.on then elapsed = 1 end
    elseif e == "PLAYER_ENTERING_WORLD" or e == "ZONE_CHANGED_NEW_AREA" then
      -- (into an instance or out of one: the game's minimap back, or the square again, G.MinimapAway; the arrow
      -- and the directions, off in a battleground)
      local away = G.MinimapAway()
      if away ~= (m.away or false) then m.away, m.awayOpen = away or nil, nil end
      if m.on or m.queued or S().replaceMinimap == true then G.ApplySettings() end
      if ns.Arrow and ns.Arrow.Apply then pcall(ns.Arrow.Apply) end
      elapsed = 1
    elseif e == "INPUT_DEVICE_INTERFACE_TRANSITION" then
      -- (the map in the game's world map or not, G.WorldMapWanted, changes with it too)
      if not G.MinimapInputChanged() then G.ApplySettings() end
    elseif m.on or m.queued then
      G.ApplySettings()
    end
  end)
  G.mmEvents = ev
  -- (another addon moving the minimap: the square follows it, G.OnMinimapMoved)
  if hooksecurefunc and type(Minimap) == "table" then
    for _, method in ipairs({ "SetPoint", "SetParent" }) do
      if Minimap[method] then pcall(hooksecurefunc, Minimap, method, function() G.MinimapMovedSoon() end) end
    end
  end
  local tick = CreateFrame("Frame", nil, UIParent)
  tick:SetScript("OnUpdate", function(_, dt) G.MinimapTick(dt) end)
  tick:Hide()
  G.mmTicker = tick
  local esc = CreateFrame("Frame", not G.clone and "AzerothGPSMinimapBack" or nil, frame)
  esc:SetSize(1, 1)
  esc:Hide()
  esc:SetScript("OnHide", function()
    if not G.mmState.closing and G.mmState.expanded then G.SetMinimapExpanded(false) end
  end)
  if UISpecialFrames and not G.clone then table.insert(UISpecialFrames, "AzerothGPSMinimapBack") end
  G.mmEscape = esc
  local b = CreateFrame("Button", nil, frame)
  b:SetSize(20, 20)
  b:SetFrameLevel(frame:GetFrameLevel() + 30 + G.ArtSpan())
  local bg = b:CreateTexture(nil, "BACKGROUND")
  bg:SetAllPoints()
  bg:SetColorTexture(0.05, 0.05, 0.06, 0.85)
  local hl = b:CreateTexture(nil, "HIGHLIGHT")
  hl:SetAllPoints()
  hl:SetColorTexture(1, 1, 1, 0.15)
  b.bg, b.hl = bg, hl
  b.logo = b:CreateTexture(nil, "ARTWORK") -- (the corner logo: G.PlaceMinimapButton)
  b.logo:SetAllPoints()
  b.logoHl = b:CreateTexture(nil, "HIGHLIGHT") -- (the logo again, added over it while pointed at)
  b.logoHl:SetAllPoints()
  b.logoHl:SetBlendMode("ADD")
  b.logoHl:SetAlpha(0.35)
  b.icon = b:CreateTexture(nil, "ARTWORK")
  b.icon:SetTexture("Interface\\Minimap\\MinimapArrow")
  b.icon:SetSize(18, 18)
  b.icon:SetPoint("CENTER")
  -- (right-click: the options, as the minimap button's; asked 2026-11-09, "always make right click on the logo ... open
  -- options")
  b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  b:SetScript("OnClick", function(_, mouse)
    if mouse == "RightButton" then
      if ns.Options and ns.Options.Toggle then ns.Options.Toggle() end
      return
    end
    if G.WorldMapWanted() then G.ToggleMapView() return end
    G.SetMinimapExpanded(not G.mmState.expanded)
  end)
  b:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_LEFT")
    if G.mmState.expanded then
      GameTooltip:SetText(L["Back to the Minimap"], 1, 1, 1)
      local idle = G.MinimapIdleSeconds()
      GameTooltip:AddLine(idle > 0 and Format(L["Also after %d seconds without using the map, or Escape."], idle)
        or L["Also with Escape."], 0.8, 0.8, 0.8, true)
    else
      GameTooltip:SetText(L["Open the GPS Map"], 1, 1, 1)
      GameTooltip:AddLine(G.WorldMapWanted() and L["Left-click: the game's world map, with the GPS map in it."]
        or L["Left-click: the whole map window, to set a route."], 0.8, 0.8, 0.8, true)
    end
    GameTooltip:AddLine(L["Right-click: options"], 0.8, 0.8, 0.8, true)
    GameTooltip:Show()
  end)
  b:SetScript("OnLeave", GameTooltip_Hide)
  b:Hide()
  G.mmButton = b
  -- (and on the opened window while the square is kept, the logo staying on the square: the arrow back as before 1.3.0,
  -- asked 2026-11-16 for 1.3.5, "the little arrow in the pop out map in the bottom left is gone ... lets add that back")
  local back = CreateFrame("Button", nil, frame)
  back:SetSize(20, 20)
  back:SetFrameLevel(frame:GetFrameLevel() + 30 + G.ArtSpan())
  local bbg = back:CreateTexture(nil, "BACKGROUND")
  bbg:SetAllPoints()
  bbg:SetColorTexture(0.05, 0.05, 0.06, 0.85)
  local bhl = back:CreateTexture(nil, "HIGHLIGHT")
  bhl:SetAllPoints()
  bhl:SetColorTexture(1, 1, 1, 0.15)
  back.icon = back:CreateTexture(nil, "ARTWORK")
  back.icon:SetTexture("Interface\\Minimap\\MinimapArrow")
  back.icon:SetSize(18, 18)
  back.icon:SetPoint("CENTER")
  back:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  back:SetScript("OnClick", function(self, mouse) b:GetScript("OnClick")(b, mouse) end)
  back:SetScript("OnEnter", function(self) b:GetScript("OnEnter")(self) end)
  back:SetScript("OnLeave", GameTooltip_Hide)
  back:Hide()
  G.mmBack = back
end

-- Ask a group member for their route (a right-click on their icon): "Ask <name> for their route?" first.
function G.AskMemberForRoute(name)
  local who = Ambiguate and Ambiguate(name, "none") or name
  return G.Confirm(Format(L["Ask |cffffd100%s|r for their route?"], who), function()
    local ok, why = ns.Import.AskForRoute(name)
    if not ok and why then ns.Print(why) end
  end)
end
-- The route linked in party (or raid) chat, for the player to send (the directions panel's Share button, shown in a
-- group; asked 2026-10-06). Returns the stops it carries, or nil.
function G.ShareRouteWithGroup()
  local channel = (IsInRaid and IsInRaid()) and "RAID" or ((IsInGroup and IsInGroup()) and "PARTY" or nil)
  if not channel then
    ns.Print(L["You're not in a group."])
    return nil
  end
  local n, err = ns.Import.Send(channel)
  if not n then ns.Print(err) return nil end
  local raid = channel == "RAID"
  ns.Print(n == 1 and (raid and L["A link to your route (1 stop) is in the chat box: press Enter to send it to your raid."]
      or L["A link to your route (1 stop) is in the chat box: press Enter to send it to your party."])
    or Format(raid and L["A link to your route (%d stops) is in the chat box: press Enter to send it to your raid."]
      or L["A link to your route (%d stops) is in the chat box: press Enter to send it to your party."], n))
  return n
end
-- "You are here" in a dungeon (asked 2026-10-01): the game hides the player's position there, so a
-- double-click on its map, inside it, puts their class icon where they say they are (instead of a stop).
-- Kept for the character (cdb.youHere: { level, x, y }) over a /reload, gone when they leave the dungeon;
-- a right-click on it takes it away.
function G.YouHere()
  local cdb = ns.db and ns.CharDB and ns.CharDB()
  return cdb and cdb.youHere or nil
end
function G.MarkYouHere(level, x, y)
  ns.CharDB().youHere = level and { level = level, x = x, y = y } or nil
  G.Redraw()
end
local youPin
function G.DrawYouHere(cx, cy, rot, s, viewCont)
  local me = G.YouHere()
  local show = me and me.level == viewCont and canvas and not G.Held()
  local sx, sy
  if show then
    local dx, dy = Geo.ScreenOffset(cx, cy, me.x, me.y)
    sx, sy = Geo.Rotate(dx * s, dy * s, rot)
    local half = canvas:GetWidth() / 2
    show = math.abs(sx) <= half and math.abs(sy) <= half
  end
  if not show then
    if youPin then youPin:Hide() end
    return
  end
  if not youPin then
    youPin = CreateFrame("Button", nil, keepLayer)
    youPin:SetFrameLevel(keepLayer:GetFrameLevel() + 2)
    youPin.edge = youPin:CreateTexture(nil, "ARTWORK")
    youPin.edge:SetAllPoints()
    youPin.dot = youPin:CreateTexture(nil, "OVERLAY")
    G.MakeRound(youPin, youPin.edge)
    G.MakeRound(youPin, youPin.dot)
    youPin:RegisterForClicks("RightButtonUp")
    youPin:SetScript("OnClick", function() G.MarkYouHere(nil) end)
    youPin:SetScript("OnEnter", function(self)
      GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
      GameTooltip:SetText(L["You (where you marked)"], 1, 1, 1)
      GameTooltip:AddLine(L["Double-click the map: you're there now"], 0.4, 0.8, 1)
      GameTooltip:AddLine(L["Right-click: clear"], 0.4, 0.8, 1)
      GameTooltip:Show()
    end)
    youPin:SetScript("OnLeave", GameTooltip_Hide)
  end
  local class
  if UnitClass then class = select(2, UnitClass("player")) end
  local c = RAID_CLASS_COLORS and class and RAID_CLASS_COLORS[class]
  local r, g, b = c and c.r or 1, c and c.g or 1, c and c.b or 1
  youPin.edge:SetColorTexture(r, g, b, 1)
  local icon = G.ClassIcon(youPin.dot, class)
  if not icon then youPin.dot:SetColorTexture(r, g, b, 1) end
  local ring = icon and G.PxUnits(G.markLayer, 2) or 1.5
  local u = icon and G.PxUnits(G.markLayer, G.ICON_PX) + 2 * ring or 16
  youPin:SetSize(u, u)
  youPin.dot:ClearAllPoints()
  youPin.dot:SetPoint("TOPLEFT", ring, -ring)
  youPin.dot:SetPoint("BOTTOMRIGHT", -ring, ring)
  if icon then G.ScaledIcon(youPin, youPin.dot, false) end
  youPin:ClearAllPoints()
  youPin:SetPoint("CENTER", G.markLayer, "CENTER", G.SnapPoint(G.markLayer, sx, sy))
  youPin:Show()
end

local hiddenShown -- the dungeon whose map was put up because the game hides the player's position in it
-- Redraws a second: the option (`hz`), at most BIG_MAP_HZ on a map over BIG_MAP across (asked 2026-10-04: a big map
-- costs about its area a redraw, and needs no 20 a second). The tiles and icons only move when the view does
-- (STILL_PX, STILL_ROT), refreshed every TILE_REFRESH and ICON_REFRESH seconds anyway; G.drawVersion: a forced redraw.
G.BIG_MAP, G.BIG_MAP_HZ = 800, 10
G.STILL_PX, G.STILL_ROT = 0.5, 0.002
G.TILE_REFRESH, G.ICON_REFRESH = 2, 0.5
G.TILE_REFRESH_STILL = 30 -- (the tiles laid for the view as it still is: kept this long; a forced redraw lays them again)
G.ICON_FULL_REFRESH = 5 -- (an icon refresh with the signature unchanged only resets the docks' countdowns: the
-- same icons would be gathered and placed again; gathered for real this often, in case the signature missed a thing)
G.ICON_PAN_PX = 24 -- panned this far on the screen at most before the icons are placed again
G.drawVersion = 0
G.UPKEEP_EVERY = 0.25 -- the route's upkeep with the map and the arrow both hidden (the pump frame), as the arrow's text
-- Between redraws the map still slides with the player: the laid tiles' and icons' layers, the quest areas', and
-- the marks' (G.markLayer: the route's lines, the stops' and rides' pins, party dots, plugin icons — placed
-- each redraw round its view's center) move every frame (a few SetPoints), so panning is as smooth as the
-- game's frame rate and the redraws at RedrawHz only refresh what they show. Only while following on the
-- land's or a zone's tiles with the turn, scale and size they were laid for (a free view, browsing, an
-- interior or a dungeon's map hold still between redraws, everything together). (Reported 2026-10-07: boats,
-- flight-path icons and the stops' markers hopped while the tiles slid; the marks were anchored to the
-- panned icon layer and moved twice, ahead of the map, until each re-gather put them back.)
function G.GlidePan()
  G.glided = false
  if free or browse or hiddenShown or not canvas or not G.markLayer then return end
  local px, py = Geo.PlayerWorld()
  if not px then return end
  local st2 = S()
  local half = math.max(canvas:GetWidth(), canvas:GetHeight()) / 2
  local halfH = canvas:GetHeight() / 2
  local facing = Geo.Facing()
  local mmZoom, mmRot = G.MinimapView(facing) -- (the map as the minimap: its radius and turn)
  local zoom = mmZoom or approachZoom or st2.zoom
  if not zoom or zoom == 0 then return end
  local rot = mmRot or G.ViewRot(st2, facing, zoom)
  local s = half / zoom
  local cx, cy = px, py
  if st2.rotate and not mmZoom then cx, cy = G.ScreenToWorld(px, py, 0, G.HEADING_UP_LOW * halfH, rot, s) end
  local function Off(x, y)
    local dx, dy = Geo.ScreenOffset(cx, cy, x, y)
    return Geo.Rotate(dx * s, dy * s, rot)
  end
  local function Same(l) return l and l.s == s and l.half == half and math.abs(l.rot - rot) < G.STILL_ROT end
  local lt = G.laidTiles
  -- (a building's or an underground city's inside map, "in:", glides too: down in Undercity the minimap square only
  -- moved at each redraw, a video 2026-11-16 "minimap stutters a lot in UC")
  local kind = lt and lt.laidSig
  -- (not with the art blended at its edge, view.interiorEdge: that one isn't on the layer that slides)
  local inside = kind and kind:sub(1, 3) == "in:" and not view.interiorEdge
  if not (Same(lt) and (kind:sub(1, 5) == "tiles" or kind:sub(1, 4) == "zone" or inside)) then return end
  G.quadLayer:ClearAllPoints()
  G.quadLayer:SetPoint("CENTER", canvas, "CENTER", Off(lt.x, lt.y))
  if Same(G.laidIcons) then
    poiLayer:ClearAllPoints()
    poiLayer:SetPoint("CENTER", canvas, "CENTER", Off(G.laidIcons.x, G.laidIcons.y))
  end
  if Same(G.markView) then
    G.markLayer:ClearAllPoints()
    G.markLayer:SetPoint("CENTER", canvas, "CENTER", Off(G.markView.x, G.markView.y))
    -- (all of it slid: the player's turn alone is the arrow's, turned here every frame, and a redraw for the move
    -- alone can wait for G.GLIDE_HZ; issue #316)
    G.glided = true
    local r = (facing or 0) + rot
    if arrow and arrow.agpsRot ~= r then
      arrow.agpsRot = r
      arrow:SetRotation(r)
    end
  end
  local as = areaState
  if as and as.zoom == zoom and math.abs(as.rot - rot) < 0.0005 then
    areaLayer:ClearAllPoints()
    areaLayer:SetPoint("CENTER", canvas, "CENTER", Off(as.ax, as.ay))
  end
end
function G.Timed(name, fn) return ns.Timed and ns.Timed(name, fn) or fn end -- (ns.Timed: Core.lua)
function G.RedrawHz()
  local hz = S().hz or 20
  local w, h = G.MapSize()
  if math.max(w, h) > G.BIG_MAP then hz = math.min(hz, G.BIG_MAP_HZ) end
  return hz
end

-- A walk with no other legs (asked 2026-11-15: "why is the directions just the current directions at the top of the
-- map and not the list of steps/whole distance?"): its turns numbered, each with how far after the one before, down to
-- the arrival, as a trip's legs are listed (Nav.StepsText): the first WALK_TURNS_SHOWN (Turns.Ahead's, HORIZON_YD
-- ahead), or with the list's "+" (`all`, stepsAll) the whole walk's: Turns.Maneuvers once a route, the turns passed
-- since left off by how much shorter the route is now. Worked out twice a second, not every redraw. The text, and the
-- turns' count (99: more past the horizon than counted).
G.WALK_TURNS_SHOWN = 3
function G.WalkTurnsText(route, label, all)
  local T = ns.Turns
  local now = GetTime()
  if route ~= G.turnRoute or now - (G.turnAt or 0) > 0.5 then
    G.turnRoute, G.turnAt = route, now
    local ok, path, ms = pcall(T.Ahead, route, label)
    G.turnMs, G.turnPath = ok and ms or nil, ok and path or nil
  end
  local ms, path = G.turnMs, G.turnPath
  local m1 = ms and ms[1]
  if not m1 then return "", nil end
  local fmt = ns.Nav.FormatDistance
  local count = ms[#ms].kind == "arrive" and #ms or nil
  local rest = {}
  for i = 2, #ms do rest[#rest + 1] = ms[i] end
  if all and path and path.total then
    local w = G.walkTurnsAll
    if not (w and w.route == route and w.label == label) then
      local ok, full = pcall(T.Maneuvers, path, label, math.huge)
      w = { route = route, label = label, ms = ok and full or {}, total = path.total }
      G.walkTurnsAll = w
    end
    local gone = w.total - path.total
    if w.ms[#w.ms] and w.ms[#w.ms].kind == "arrive" then
      rest = {}
      for _, m in ipairs(w.ms) do
        if m.dist - gone > m1.dist + 1 then
          local c = {}
          for k, v in pairs(m) do c[k] = v end
          c.dist = m.dist - gone
          rest[#rest + 1] = c
        end
      end
      count = #rest + 1
    end
  end
  local shown = all and math.huge or G.WALK_TURNS_SHOWN
  local lines = { "|cffffffff" .. Format(L["%d. %s"], 1, T.NowText(m1, fmt)) .. "|r" }
  local prev = m1.dist
  for i, m in ipairs(rest) do
    if i + 1 > shown then break end
    lines[#lines + 1] = "|cffb0b0b0" .. Format(L["%d. %s in %s"], i + 1, m.text, fmt(m.dist - prev)) .. "|r"
    prev = m.dist
  end
  if count and count > #lines then
    lines[#lines + 1] = Format(count - #lines > 1 and L["|cff808080... %d more steps|r"] or L["|cff808080... %d more step|r"],
      count - #lines)
  elseif not count then
    lines[#lines + 1] = L["|cff808080... more turns further on|r"]
  end
  return table.concat(lines, "\n"), count or 99
end

-- The route panel's width, side and detaching (1.3.9, asked 2026-11-18: "make this section's width resizable and its
-- position like left, right, or middle ... add an option to 'detach this' as a separate window similar to the
-- direction's text box and this stays open even when map in collapsed"). On the map (its own window and in the world
-- map alike): `navPanelWidth`, a share of the room right of the inset (100, the whole of it: as before), placed by
-- `navPanelAlign` left, center or right; its free edge dragged sets the width too. Detached (`navPanelDetached`): the
-- same panel, a child of UIParent, a panel like the directions' (their dark box, no frame), dragged anywhere
-- (`navPanelPoint`), as wide as `navPanelDetachedWidth`; shown while there's a route whether the map shows or not
-- (kept up to date by the pump frame while the map's hidden, G.RefreshDetachedNav). Attach (its button, or the
-- option off) puts it back on the map.
G.NAV_EDGE_W = 6 -- (UI units: the edge dragged for the width, just outside the panel)
G.NAV_MIN_PCT, G.NAV_MAX_PCT = 30, 100
G.NAV_MIN_W = 160 -- (UI units: room for the times line and the panel's buttons)
G.NAV_DETACHED_W, G.NAV_DETACHED_MAX_W = 320, 900
G.NAV_DETACHED_Y = 140 -- (from the screen's top, the first time)
G.NAV_DETACHED_STRATA = "MEDIUM" -- (the directions' own)
G.NAV_DETACHED_EVERY = 0.25 -- (seconds: its text while the map's hidden, as the arrow's)
G.NAV_ALIGNS = { left = true, center = true, right = true }
function G.NavAlign()
  local a = S().navPanelAlign
  return G.NAV_ALIGNS[a] and a or "left"
end
function G.NavWidthPct()
  local v = tonumber(S().navPanelWidth) or G.NAV_MAX_PCT
  return math.max(G.NAV_MIN_PCT, math.min(G.NAV_MAX_PCT, v))
end
function G.NavDetachedWidth()
  local v = tonumber(S().navPanelDetachedWidth) or G.NAV_DETACHED_W
  return math.max(G.NAV_MIN_W, math.min(G.NAV_DETACHED_MAX_W, v))
end
-- The room it has on the map: right of the inset (the frame's portrait, the world map's corner buttons) to the edge.
function G.NavRoom()
  local home = G.navHome
  local w = home and home.GetWidth and home:GetWidth() or 0
  return math.max(0, w - (G.topInset or 4) - 4)
end
-- The panel showing on the map (what goes under it: the floor buttons, the path color, the tools' hint).
function G.NavOnMap()
  return navPanel ~= nil and not G.navDetached and navPanel:IsShown()
end
function G.PlaceNavPanel()
  if not navPanel then return end
  local edge, align = G.navEdge, G.NavAlign()
  if G.navDetached then
    navPanel:SetWidth(G.NavDetachedWidth())
    local h = G.NavDetachedHeight()
    if h then navPanel:SetHeight(h) end -- (sized by its corner: else as tall as its text)
    align = "left" -- (its right edge)
  else
    local inset, pct = G.topInset or 4, G.NavWidthPct()
    navPanel:ClearAllPoints()
    if pct >= G.NAV_MAX_PCT then
      navPanel:SetPoint("TOPLEFT", inset, -4)
      navPanel:SetPoint("TOPRIGHT", -4, -4)
    else
      local room = G.NavRoom()
      navPanel:SetWidth(math.min(room, math.max(G.NAV_MIN_W, room * pct / 100)))
      if align == "right" then
        navPanel:SetPoint("TOPRIGHT", -4, -4)
      elseif align == "center" then
        navPanel:SetPoint("TOP", (inset - 4) / 2, -4) -- (the middle of its room)
      else
        navPanel:SetPoint("TOPLEFT", inset, -4)
      end
    end
  end
  if edge then
    edge:ClearAllPoints()
    if align == "right" then
      edge:SetPoint("TOPRIGHT", navPanel, "TOPLEFT", 1, 0)
      edge:SetPoint("BOTTOMRIGHT", navPanel, "BOTTOMLEFT", 1, 0)
    else
      edge:SetPoint("TOPLEFT", navPanel, "TOPRIGHT", -1, 0)
      edge:SetPoint("BOTTOMLEFT", navPanel, "BOTTOMRIGHT", -1, 0)
    end
  end
end
-- The edge dragged `dx` from where it was when the panel was `w0` wide: the width it takes now.
function G.DragNavEdge(w0, dx)
  local st = S()
  if G.navDetached then
    st.navPanelDetachedWidth = math.floor(math.max(G.NAV_MIN_W, math.min(G.NAV_DETACHED_MAX_W, w0 + dx)) + 0.5)
  else
    local align = G.NavAlign()
    local grow = align == "right" and -dx or (align == "center" and 2 * dx or dx) -- (in the middle: both sides)
    local room = G.NavRoom()
    if room <= 0 then return end
    st.navPanelWidth = math.floor(math.max(G.NAV_MIN_PCT, math.min(G.NAV_MAX_PCT, (w0 + grow) / room * 100)) + 0.5)
  end
  G.PlaceNavPanel()
end
function G.SaveNavPoint()
  local l, t = navPanel:GetLeft(), navPanel:GetTop()
  if l and t then S().navPanelPoint = { "TOPLEFT", "UIParent", "BOTTOMLEFT", math.floor(l + 0.5), math.floor(t + 0.5) } end
end
-- Detached or on the map, as the setting says (ApplySettings; the second map never: it has the first's panel).
function G.ApplyNavDetach()
  if not navPanel then return end
  local st = S()
  local want = st.navPanelDetached == true and not G.clone
  if want ~= (G.navDetached == true) then
    G.navDetached = want or nil
    if want then
      navPanel:SetParent(UIParent)
      navPanel:SetScale(1)
      navPanel:SetFrameStrata(G.NAV_DETACHED_STRATA)
      navPanel:SetFrameLevel(10)
      navPanel:EnableMouse(true)
    else
      local home = G.navHome
      navPanel:SetParent(home)
      navPanel:SetFrameStrata(home:GetFrameStrata())
      navPanel:SetFrameLevel((home:GetFrameLevel() or 0) + 1)
      navPanel:EnableMouse(false)
    end
    G.navPanelSig = nil -- (laid out again)
    -- (the use button: set again with the panel's strata, out of combat)
    -- (hidden till then: with nothing to use next, a nil key left the old one showing)
    if G.useBtn and not (InCombatLockdown and InCombatLockdown()) then
      G.useBtn:Hide()
      G.useBtn.key = nil
    end
  end
  if want and not G.navMoving then -- (not while it's being dragged: a settings change meanwhile)
    local p = st.navPanelPoint
    navPanel:ClearAllPoints()
    if type(p) == "table" and p[1] then
      navPanel:SetPoint(p[1], _G[p[2] or "UIParent"] or UIParent, p[3] or p[1], tonumber(p[4]) or 0, tonumber(p[5]) or 0)
    else
      navPanel:SetPoint("TOP", UIParent, "TOP", 0, -G.NAV_DETACHED_Y)
    end
  end
  G.PlaceNavPanel()
  G.ApplyNavLook()
  if fl.bar and fl.bar:IsShown() then G.PlaceFloorBar() end
  if G.pathColorBox and G.pathColorBox:IsShown() then G.PlacePathColorPicker() end
  if want and not G.IsVisible() then G.RefreshDetachedNav() end -- (shown now, the map closed)
  -- (and fitted again once the client has laid it out: at login and after a /reload the first fit comes before that)
  if want and G.NavFixed() then
    G.navRefits = 0
    G.NavRefitSoon()
  end
end
-- Detached, two looks of its own (1.3.9, asked 2026-11-18: "for the detached route panel, add options to hide all
-- buttons in it and set the opacity of the background"). `navPanelHideButtons`: only its text, every button in it
-- hidden (the X, Attach, the steps' -/+, Share, the use button, the quest rows' Leave Out / Put Back); it still drags
-- anywhere, a right-click on it puts it back on the map (as Attach does), and its edge still sizes it. `navPanelAlpha`:
-- its dark box's opacity in percent (70, as before; 0 leaves the text alone, which keeps its own). It has no border to
-- keep. On the map neither: all its buttons, the usual box.
G.NAV_ALPHA_DEFAULT = 70
function G.NavBare()
  return G.navDetached == true and S().navPanelHideButtons == true
end
function G.NavAlphaPct()
  local v = tonumber(S().navPanelAlpha) or G.NAV_ALPHA_DEFAULT
  return math.max(0, math.min(100, v))
end
function G.ApplyNavLook()
  if not navPanel then return end
  navPanel:SetBackdropColor(0, 0, 0, (G.navDetached and G.NavAlphaPct() or G.NAV_ALPHA_DEFAULT) / 100)
  local bare = G.NavBare()
  local textR, stepsR = G.NavTextInsets()
  local key = textR .. ":" .. stepsR
  if key ~= G.navInsetWas then
    G.navInsetWas = key
    -- (its text out to the right edge without the buttons there; clear of the lock button with it)
    navText:SetPoint("TOPRIGHT", -textR, -6)
    stepsText:SetPoint("RIGHT", -stepsR, 0)
    G.navPanelSig = nil -- (laid out again: the buttons)
  end
  -- (word wrap stays on: in the client a string of several lines with it off shows its first line alone, cut short;
  -- seen in game 2026-11-18. A sized panel cuts its too-long lines itself, G.FitLineWidth.)
  local locked = G.NavLocked()
  if G.navGrip then
    G.navGrip:SetShown(G.navDetached == true and not locked)
    G.navGrip:SetAlpha((bare and not G.navHover) and 0 or 1) -- (buttons hidden: the grip only under the mouse)
  end
  -- (detached, its corner grip sizes it: the width edge only on the map; asked 2026-11-18, "remove the 'drag to change
  -- panel's width' on the popout directions window")
  if G.navEdge then G.navEdge:SetShown(not G.navDetached) end
  if G.navLock then
    G.navLock:SetShown(G.navDetached == true and not bare)
    G.SetLockGlyph(G.navLock, locked)
  end
end
-- The detached panel locked (1.3.9, asked 2026-11-18, "be able to lock the detached route panel"): `navPanelLocked`,
-- no dragging, no sizing (its grip and edge hidden), no right-click back to the map; its buttons still work, its lock
-- button (shown with them) or the option unlocks it. Only while detached: on the map it never moves anyway.
function G.NavLocked()
  return G.navDetached == true and S().navPanelLocked == true
end
function G.SetNavLocked(on)
  S().navPanelLocked = on and true or false
  G.ApplyNavLook()
  if ns.Options and ns.Options.Refresh then ns.Options.Refresh() end
end
-- How far in from the panel's right edge its text ends: the status line (clear of the X, Attach, the lock and a steps
-- box) and the steps (clear of the use button); with its buttons hidden, the edge.
G.NAV_LOCK_W = 18 -- (the lock button and its gap)
function G.NavTextInsets()
  if G.NavBare() then return 6, 6 end
  return 58 + (G.navDetached and G.NAV_LOCK_W or 0), 32
end
-- A drawn padlock (no game art that may be missing): its body, and its shackle closed or open.
function G.SetLockGlyph(b, locked)
  local g = b.glyph
  if not g then return end
  g.shackleR:ClearAllPoints()
  if locked then
    g.shackleR:SetPoint("BOTTOMRIGHT", g.body, "TOPRIGHT", -1, 0)
  else
    g.shackleR:SetPoint("BOTTOMRIGHT", g.body, "TOPRIGHT", -1, 3) -- (lifted: open)
  end
  g.shackleR:SetSize(1, 3)
  b.locked = locked
end
function G.NavHover(on)
  G.navHover = on or nil
  if G.navGrip then G.navGrip:SetAlpha((G.NavBare() and not G.navHover) and 0 or 1) end
end

-- Detached, sized by its bottom-right corner (1.3.9, asked 2026-11-18: "add a corner resizer for the window so text
-- would only stay within that, steps that would go past it show as '... X more steps'"): `navPanelDetachedWidth` and
-- `navPanelDetachedHeight` (nil until it's sized: as tall as its text, as before). Sized, its text stays inside: the
-- status lines first, then the quest rows, then as many whole steps as fit, the last line saying how many more there
-- are (G.FitSteps); a line too long for its width cut short.
G.NAV_DETACHED_MIN_H, G.NAV_DETACHED_MAX_H = 36, 600
G.NAV_PAD_H = 12 -- (UI units: above and below its text)
G.NAV_STEPS_GAP, G.NAV_STEPS_SPACING = 4, 2 -- (the steps under the status, and between their lines: as laid out)
function G.NavDetachedHeight()
  local v = tonumber(S().navPanelDetachedHeight)
  if not v then return nil end
  return math.max(G.NAV_DETACHED_MIN_H, math.min(G.NAV_DETACHED_MAX_H, v))
end
function G.NavFixed()
  return G.navDetached == true and G.NavDetachedHeight() ~= nil
end
-- Its corner dragged to `w` x `h` (clamped, kept).
function G.SizeNavDetached(w, h)
  local st = S()
  st.navPanelDetachedWidth = math.floor(math.max(G.NAV_MIN_W, math.min(G.NAV_DETACHED_MAX_W, w)) + 0.5)
  st.navPanelDetachedHeight = math.floor(math.max(G.NAV_DETACHED_MIN_H, math.min(G.NAV_DETACHED_MAX_H, h)) + 0.5)
  G.PlaceNavPanel()
  G.ApplyNavLook()
  G.navPanelSig = nil -- (its text fitted again, on the next update)
  if G.navDetached and not G.IsVisible() then G.RefreshDetachedNav() end
end
function G.NavLineH(fs)
  local ok, h = pcall(function() return fs:GetLineHeight() end)
  if ok and type(h) == "number" and h > 0 then return h end
  local _, size = fs:GetFont()
  return tonumber(size) or 12
end
function G.SplitLines(text)
  local t = {}
  if text == nil or text == "" then return t end
  for l in (text .. "\n"):gmatch("(.-)\n") do t[#t + 1] = l end
  return t
end
-- A numbered step's line ("2. Take the boat ...", any language: "%d. %s"), its colors aside.
function G.IsStepLine(l)
  return (l:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")):match("^%d+%. ") ~= nil
end
function G.MoreStepsLine(n)
  return Format(n > 1 and L["|cff808080... %d more steps|r"] or L["|cff808080... %d more step|r"], n)
end
-- The steps' lines (`text`) that fit in `fit` lines: all of them, or the first ones and, last, "... N more steps"
-- (`total`, the steps in all; false: not known, "... more turns further on"). Gives the text and how many were left out.
-- `cost` (optional): how many lines each takes (wrapped: G.NavWrap), else one; a step is kept whole or not at all.
function G.FitSteps(text, fit, total, cost)
  local lines = G.SplitLines(text)
  local costs, sum = {}, 0
  for i, l in ipairs(lines) do
    costs[i] = cost and math.max(1, cost(l)) or 1
    sum = sum + costs[i]
  end
  if sum <= fit then return text, 0 end
  local numbered = 0
  for _, l in ipairs(lines) do
    if G.IsStepLine(l) then numbered = numbered + 1 end
  end
  if fit <= 0 then return "", total or numbered end
  local out, kept, used = {}, 0, 0
  for i = 1, #lines do
    if used + costs[i] > fit - 1 then break end -- (a line kept for the rest's count)
    out[i] = lines[i]
    used = used + costs[i]
    if G.IsStepLine(lines[i]) then kept = kept + 1 end
  end
  local more = (total or numbered) - kept
  if total == false then
    out[#out + 1] = L["|cff808080... more turns further on|r"]
  elseif more > 0 then
    out[#out + 1] = G.MoreStepsLine(more)
  else -- (only lines after the steps left over: the one more that fits)
    local nx = lines[#out + 1]
    if nx and used + costs[#out + 1] <= fit then out[#out + 1] = nx end
  end
  return table.concat(out, "\n"), math.max(0, more)
end
-- Detached, wrapping its lines (`navPanelWrap`, asked 2026-11-18: "Wrap the text"): a line too long for the panel goes
-- on to the next instead of being cut short; the fit counts each step's lines, kept whole or not at all.
function G.NavWrap()
  return G.navDetached == true and S().navPanelWrap == true
end
-- How many lines `line` takes wrapped at `w` wide (the client's way: at the spaces; a word wider than a line broken).
-- One while the font measures nothing (not settled yet: fitted again after).
function G.WrapCount(line, w)
  if line == "" or w <= 0 then return 1 end
  local full = G.TextWidth(line)
  if full <= w then return 1 end
  local n, cur = 1, ""
  for word in line:gmatch("%S+") do
    local try = cur == "" and word or (cur .. " " .. word)
    if cur ~= "" and G.TextWidth(try) > w then
      n = n + 1
      cur = word
    else
      cur = try
    end
    local cw = G.TextWidth(cur)
    if cw > w then -- (one word past the width: broken over lines of its own)
      n = n + math.ceil(cw / w) - 1
      cur = ""
    end
  end
  return n
end
-- Sized: its text fitted inside it (from G.UpdateNavPanel, the full text set). `steps` the steps' text, `total` their
-- count, `rowsH` the quest rows' height. G.navMore: how many steps were left out (the tests).
function G.FitNavPanel(steps, total, rowsH)
  local h = G.NavDetachedHeight()
  local w = G.NavDetachedWidth()
  local textR, stepsR = G.NavTextInsets()
  local room = h - G.NAV_PAD_H
  local lh = G.NavLineH(navText)
  local status = G.SplitLines(navText:GetText() or "")
  local fitS = math.max(1, math.floor(room / lh))
  local wrap, tw = G.NavWrap(), w - 6 - textR
  local statusLines = 0
  if wrap then -- (whole lines while they fit; the first always, cut short if it alone is past the room)
    local keep = {}
    for i, l in ipairs(status) do
      local c = G.WrapCount(l, tw)
      if statusLines + c > fitS then
        if i == 1 then keep[1], statusLines = G.FitLineWidth(l, tw), 1 end
        break
      end
      keep[i], statusLines = l, statusLines + c
    end
    status = keep
  else
    for i = #status, fitS + 1, -1 do status[i] = nil end
    for i, l in ipairs(status) do status[i] = G.FitLineWidth(l, tw) end
    statusLines = #status
  end
  navText:SetText(table.concat(status, "\n"))
  -- (the client's own measures only once they're settled, G.NavLayoutSettled: right after a /reload the text strings
  -- have no width yet, every word a line of its own, and the panel came up with step 1 alone; Kooki3z's test of
  -- #617, 2026-11-18. Unsettled: by the font's line height, and fitted again shortly, G.NavRefitSoon)
  local settled = G.NavLayoutSettled()
  local used = statusLines * lh
  local measured = tonumber(navText:GetStringHeight()) or 0
  if settled and measured > used and measured <= used * G.NAV_MEASURE_TRUST then used = measured end
  room = room - used
  if rowsH > 0 and rowsH > room then -- (no room for the quest rows)
    G.LayoutGroupRows(navPanel, navText, false)
    rowsH = 0
  end
  G.navMore = 0
  if steps ~= "" then
    local sl = G.NavLineH(stepsText)
    local stepRoom = room - rowsH - G.NAV_STEPS_GAP
    local fit = math.floor((stepRoom + G.NAV_STEPS_SPACING) / (sl + G.NAV_STEPS_SPACING))
    local ww = w - 6 - stepsR
    local out
    local cost = wrap and function(l) return G.WrapCount(l, ww) end or nil
    repeat
      out, G.navMore = G.FitSteps(steps, fit, total, cost)
      local lines = G.SplitLines(out)
      local count = #lines
      if wrap then
        count = 0
        for _, l in ipairs(lines) do count = count + cost(l) end
      else
        for i, l in ipairs(lines) do lines[i] = G.FitLineWidth(l, ww) end
      end
      out = table.concat(lines, "\n")
      stepsText:SetText(out)
      fit = fit - 1
      -- (laid out taller than the room by the client's own measure: one line fewer. Not on a measure that isn't
      -- settled, nor one far past what its lines can be: a string with no width yet, each word a line, isn't "too
      -- tall"; nor zero or none)
      local mh = tonumber(stepsText:GetStringHeight()) or 0
      local expect = count * (sl + G.NAV_STEPS_SPACING)
      local over = settled and mh > stepRoom + 1 and mh <= expect * G.NAV_MEASURE_TRUST
    until fit < 0 or out == "" or not over
    stepsText:SetShown(out ~= "")
    if out == "" and rowsH > 0 then G.LayoutGroupRows(navPanel, navText, true) end
  end
  navPanel:SetHeight(h)
  if settled then G.navRefits = 0 else G.NavRefitSoon() end
end
G.NAV_MEASURE_TRUST = 2 -- (a measured height up to twice what its lines make is the client's; past that, not settled)
G.NAV_REFIT_WAIT, G.NAV_REFIT_MAX = 0.25, 20 -- (seconds; tries while it isn't settled)
-- The panel's text laid out by the client yet: its strings have a width, and the font measures text.
function G.NavLayoutSettled()
  local tw = tonumber(navText:GetWidth()) or 0
  local sw = tonumber(stepsText:GetWidth()) or 0
  local pw = tonumber(navPanel:GetWidth()) or 0
  return tw > 1 and sw > 1 and pw > 1 and G.TextWidth("0") > 0
end
-- Fitted again shortly (its text laid out once more: G.navPanelSig cleared), while the client's layout settles; at
-- most NAV_REFIT_MAX tries in a row.
function G.NavRefitSoon()
  if (G.navRefits or 0) >= G.NAV_REFIT_MAX or not (C_Timer and C_Timer.After) then return end
  local now = GetTime()
  if G.navRefitPending and now - G.navRefitPending < 1 then return end -- (one on its way)
  G.navRefits = (G.navRefits or 0) + 1
  G.navRefitPending = now
  C_Timer.After(G.NAV_REFIT_WAIT, G.NavRefit)
end
function G.NavRefit()
  G.navRefitPending = nil
  if not G.NavFixed() then return end
  G.navPanelSig = nil
  if not G.IsVisible() then G.RefreshDetachedNav() end -- (the map shown: its next update lays it out)
end
-- The pieces of a line of text: each escape sequence whole (a color, its end, an icon, a link, "||") and each
-- character (UTF-8), so a line is cut between them, never inside one.
function G.TextTokens(s)
  local t, i, n = {}, 1, #s
  while i <= n do
    local c, j = s:sub(i, i), i
    if c == "|" then
      local nx = s:sub(i + 1, i + 1)
      if nx == "c" then j = i + 9
      elseif nx == "r" or nx == "|" then j = i + 1
      elseif nx == "T" then j = (s:find("|t", i + 2, true) or n) + 1
      elseif nx == "A" then j = (s:find("|a", i + 2, true) or n) + 1
      elseif nx == "H" then -- (|Hdata|htext|h: the whole link)
        local a = s:find("|h", i + 2, true)
        j = a and ((s:find("|h", a + 2, true) or n) + 1) or n
      end
    else
      local b = c:byte()
      j = i + (b >= 0xF0 and 3 or b >= 0xE0 and 2 or b >= 0xC0 and 1 or 0)
    end
    t[#t + 1] = s:sub(i, j)
    i = j + 1
  end
  return t
end
-- How wide `text` is in the panel's font, on one line (a hidden font string of its own: G.navMeasure).
function G.TextWidth(text)
  local m = G.navMeasure
  if not m then return 0 end
  m:SetText(text)
  local w = m.GetUnboundedStringWidth and m:GetUnboundedStringWidth() or m:GetStringWidth()
  return tonumber(w) or 0
end
G.NAV_ELLIPSIS = "..."
-- `line` cut to `w` wide: as it is when it fits, else as much as fits and "..." (in its color, then ended).
function G.FitLineWidth(line, w)
  if line == "" or w <= 0 or G.TextWidth(line) <= w then return line end
  local tok = G.TextTokens(line)
  local function cut(k) return table.concat(tok, "", 1, k) .. G.NAV_ELLIPSIS .. "|r" end
  local lo, hi = 0, #tok - 1 -- (the most pieces that fit with the dots)
  while lo < hi do
    local mid = math.floor((lo + hi + 1) / 2)
    if G.TextWidth(cut(mid)) <= w then lo = mid else hi = mid - 1 end
  end
  return cut(lo)
end
function G.SetNavDetached(on)
  S().navPanelDetached = on and true or false
  local main = ns.GPS or G -- (the second map's button: the first map's panel)
  main.ApplySettings()
  if ns.Options and ns.Options.Refresh then ns.Options.Refresh() end
end
-- Detached, with the map hidden (closed, minimized, the world map closed): its text from the pump frame.
function G.RefreshDetachedNav()
  if not (G.navDetached and navPanel) then return false end
  local px, py, pc = Geo.PlayerWorld()
  if not px then
    navPanel:Hide() -- (no position: a dungeon's boss list is the map's)
    G.navPanelSig = nil
    return false
  end
  ns.Nav.Tick()
  local r = ns.Nav.Route(px, py, pc)
  if r and ns.Nav.RedAsking and ns.Nav.RedAsking() then r = nil end
  G.UpdateNavPanel(px, py, pc, nil, r, ns.Nav.dest)
  return true
end

-- The directions panel over the map: the status (distances, ETAs, the stops), the steps, and their buttons; laid
-- out again only when its text or states changed. From each redraw, and on its own while the still map with a route
-- waits for its idle redraw (issue #191: the ETAs and countdowns tick, nothing else on the map moves).
function G.UpdateNavPanel(px, py, cont, hidden, route, dest)
  local st = S()
  local status
  if hidden then -- (no directions without the player's position: the next boss, when on its route)
    local i, b = G.NextBoss(hidden)
    local n = #G.BossOrder(hidden)
    status = (b and Format(L["Next: |cffffd100%s|r  (%d of %d)"], b[1], i, n) or L["|cff40ff40All the bosses are down|r"])
      .. "\n" .. L["|cff9d9d9dDouble-click: mark where you are   Right-click a boss: defeated|r"]
    local shift = G.IconHint({ kind = "boss", cont = hidden }) -- (another addon's, e.g. StreetView's)
    if shift then status = status .. "\n" .. Format(L["|cff9d9d9dShift-click a boss: %s|r"], shift) end
  else
    status = ns.Nav.Status(px, py, cont)
  end
  local steps = status and not hidden and ns.Nav.StepsText(st.stepsAll and 99 or 3) or ""
  -- a walk with no other legs: its turns, numbered, as the list of a trip's legs (G.WalkTurnsText)
  G.walkTurns = nil
  if status and steps == "" and route and not route.flying and ns.Turns and not ns.Nav.questing then
    steps, G.walkTurns = G.WalkTurnsText(route, dest and dest.name or L["the stop"], st.stepsAll)
  end
  -- collapsed (the -/+ button, with steps to list): only the "All stops" / times line
  local collapsed = steps ~= "" and st.stepsCollapsed
  -- ... and the hearthstone or a teleport kept for a later stop, under the times (or a quest area's
  -- objectives: no steps there). (On G: the 200-locals limit.)
  G.tpAhead = status and not hidden and (collapsed or steps == "") and ns.Nav.TeleportAheadText(0) or nil
  -- (and the other faction's territory the route can't go round, Nav.HostileNote: asked 2026-11-14)
  G.hostileNote = status and not hidden and ns.Nav.HostileNote and ns.Nav.HostileNote() or nil
  local grouped = (IsInGroup and IsInGroup()) or (IsInRaid and IsInRaid())
  local manySteps = #ns.Nav.Steps() > 3 or (G.walkTurns or 0) > G.WALK_TURNS_SHOWN
  -- (the same text and states as the last redraw: the panel isn't touched again — a heading-up
  -- redraw changes only the view; G.drawVersion is in the signature, so any forced redraw still
  -- lays it out; the 2026-10-07 draw profile. On G: the 200-locals limit.)
  local psig = table.concat({ status or "", steps, collapsed and "c" or "-", hidden and "h" or "-",
    grouped and "g" or "-", manySteps and "m" or "-", st.stepsAll and "a" or "-",
    #ns.Nav.stops > 0 and "s" or "-", tostring(ns.Nav.Version()), tostring(navClosedAt),
    G.Held() and "H" or "-", tostring(G.drawVersion), G.tpAhead or "", G.hostileNote or "",
    G.NavBare() and "b" or "-", G.NavFixed() and tostring(G.NavDetachedHeight()) or "-",
    G.NavWrap() and "w" or "-" }, "|")
  if psig ~= G.navPanelSig then
  G.navPanelSig = psig
  navText:SetText((collapsed and G.CollapsedStatus(status) or status or "") .. (G.tpAhead and "\n" .. G.tpAhead or "")
    .. (G.hostileNote and "\n" .. G.hostileNote or ""))
  if collapsed then steps = "" end
  stepsText:SetText(steps)
  stepsText:SetShown(steps ~= "")
  -- (detached with its buttons hidden: none of them, G.NavBare)
  local bare = G.NavBare()
  G.navCancel:SetShown(not bare)
  G.navDetach:SetShown(not bare)
  G.navLock:SetShown(not bare and G.navDetached == true) -- (detached only: on the map it doesn't move)
  local right = G.navLock:IsShown() and G.navLock or G.navDetach -- (the boxes left of these)
  G.stepsToggle:ClearAllPoints()
  G.stepsToggle:SetPoint("RIGHT", right, "LEFT", -2, 0)
  G.stepsToggle:SetShown(not bare and status ~= nil and (steps ~= "" or collapsed))
  G.stepsToggle.label:SetText(collapsed and "+" or "-")
  -- "+" for all of them: when there are more than the few shown
  G.stepsMore:SetShown(not bare and status ~= nil and not collapsed and not st.stepsAll and manySteps)
  -- Share (in a group, with a route): left of the boxes shown
  G.shareButton:SetShown(not bare and status ~= nil and #ns.Nav.stops > 0 and grouped and true or false)
  if G.shareButton:IsShown() then
    local left = G.stepsMore:IsShown() and G.stepsMore or (G.stepsToggle:IsShown() and G.stepsToggle) or nil
    G.shareButton:ClearAllPoints()
    if left then
      G.shareButton:SetPoint("RIGHT", left, "LEFT", -2, 0)
    else
      G.shareButton:SetPoint("RIGHT", right, "LEFT", -2, 0)
    end
  end
  local rowsH = G.LayoutGroupRows(navPanel, steps ~= "" and stepsText or navText, status ~= nil and not collapsed and not hidden)
  if G.NavFixed() then -- (detached and sized by its corner: its text kept inside it)
    G.FitNavPanel(steps, G.walkTurns and (G.walkTurns < 99 and G.walkTurns or false) or #ns.Nav.Steps(), rowsH)
  else
    G.navMore = 0
    navPanel:SetHeight(navText:GetStringHeight() + 12 + (steps ~= "" and stepsText:GetStringHeight() + 4 or 0) + rowsH)
  end
  -- closed with its X: hidden until the route changes (unless the X clears the route)
  navPanel:SetShown(status ~= nil and navClosedAt ~= ns.Nav.Version() and not G.Held() and not ns.InBattleground())
  elseif collapsed then
    steps = "" -- (as the laid-out path leaves it: what follows reads it)
  end
  -- (not while the steps are collapsed: asked, 2026-10-01; the arrow window has its own)
  G.UpdateUseButton(navPanel:IsShown() and not hidden and not collapsed and not G.NavBare() and ns.Nav.UseNow() or nil)
  -- (a dungeon's floor and route note: under the panel while it shows, not under its text)
  if fl.bar and fl.bar:IsShown() then G.PlaceFloorBar() end
  if G.pathColorBox and G.pathColorBox:IsShown() then G.PlacePathColorPicker() end
end

function G.Update()
  local st = S()
  do -- (the player's city: its own zoom-out limit, G.CITY_MAX_ZOOM_TIMES)
    local ok, id = pcall(function() return C_Map and C_Map.GetBestMapForUnit and C_Map.GetBestMapForUnit("player") end)
    G.CITY_MAX_ZOOM = G.CityMaxZoomFor(ok and id or nil)
  end
  if G.WatchQuickOn then G.WatchQuickOn() end
  local px, py, cont, pz = Geo.PlayerWorld()
  -- In a dungeon the game hides the player's position: its map still (the art, the usual way
  -- through, the bosses), without them on it and without a route from where they stand.
  local hidden
  if not px then
    local lvl = ns.Nav.CurrentInstance and ns.Nav.CurrentInstance()
    local inst = lvl and G.InstanceOf(lvl)
    if inst then
      hidden = inst
      if not free or hiddenShown ~= inst then
        local x0, x1, y0, y1 = G.InstanceBounds(inst)
        browse, browseZoom, browseCont, browseBounds, fromTerrain, openedFrom = nil, nil, nil, nil, nil, nil
        free = { x = (x0 + x1) / 2, y = (y0 + y1) / 2, rot = 0, cont = inst, instance = inst, hidden = true }
        st.zoom = math.max(MIN_ZOOM, math.min(G.MaxZoom(), math.max(x1 - x0, y1 - y0) / 2 * 1.05))
        hiddenShown = inst
      end
      px, py, cont, pz = free.x, free.y, free.cont, nil
    end
  else
    hiddenShown = nil
    if G.YouHere() then ns.CharDB().youHere = nil end -- (out of the dungeon: the mark goes)
    if (free or browse) and G.MinimapMode() then G.Follow() end -- (the minimap is always on the player)
  end
  if not px then
    DrawQuads({})
    DrawLines(0, 1, ROAD_COLORS, 1)
    DrawPois({}, 0) -- (no names left over from the last map)
    G.DrawFloors(false)
    noMapText:SetText(L["No map here"])
    noMapText:Show()
    arrow:Hide()
    northLabel:Hide()
    infoText:SetText("")
    return
  end
  noMapText:Hide()
  arrow:Show()
  local pt = ns.PerfStart() -- the parts' timings (/agps debug perf)
  local facing = Geo.Facing()
  -- (half the long side: drawn as a square that size, the window clipping it to its shape; halfH, the height's)
  local half = math.max(canvas:GetWidth(), canvas:GetHeight()) / 2
  local halfH = canvas:GetHeight() / 2
  -- Following: centered on the player, turning with them in heading-up mode.
  -- Free view: wherever the user dragged, rotation frozen at the start of the drag.
  G.SeamRebase(cont)
  -- (zoomed out on the seamless map's art, then a game held the map: no further out than its limits, issue #60; the
  -- setting itself kept for after)
  -- (the map as the minimap, following: the minimap's radius and turn, the player in the middle, so its blips land
  -- on the map's places: G.MinimapView)
  local mmZoom, mmRot
  if not free and not browse then mmZoom, mmRot = G.MinimapView(facing) end
  local zoom = mmZoom or browseZoom or approachZoom or math.min(st.zoom, G.MaxZoom())
  local cx, cy, rot = px, py, mmRot or G.ViewRot(st, facing, zoom)
  -- (the art showing: north up, it can't turn)
  if free then cx, cy, rot = free.x, free.y, (G.SeamBlend(zoom) or 0) > 0 and 0 or free.rot end
  if free and not browse then G.LeaveInsideIfAway(zoom) end -- (an inside map opened, panned well away from: left)
  if G.wmState.on then rot = 0 end -- (in the game's world map: north up, as its icons are)
  local s = half / zoom
  -- (heading-up, following: the player low on the map, more of the way ahead shown; the center
  -- is the spot HEADING_UP_LOW of the half ahead of them)
  if st.rotate and not free and not browse and not mmZoom then
    cx, cy = G.ScreenToWorld(px, py, 0, G.HEADING_UP_LOW * halfH, rot, s)
  end
  view.x, view.y, view.rot, view.s = cx, cy, rot, s
  G.markView = { x = cx, y = cy, rot = rot, s = s, half = half } -- (the marks are placed round this: G.GlidePan)
  G.markLayer:ClearAllPoints()
  G.markLayer:SetPoint("CENTER", canvas, "CENTER", 0, 0)
  -- (the view hardly moved since the last redraw: under G.STILL_PX on the screen, the same turn, scale and size;
  -- the tiles and the icons then stay as drawn, refreshed every TILE_REFRESH / ICON_REFRESH seconds anyway.
  -- Asked 2026-10-04: a 1054-wide map zoomed out spent 10 ms a redraw, 691 of them over a frame, mostly
  -- placing the same tiles and icons again)
  local now = GetTime()
  local dn = G.drawn
  local still = dn and dn.s == s and dn.half == half and dn.version == G.drawVersion
    and math.abs(dn.rot - rot) < G.STILL_ROT and math.abs((cx - dn.x) * s) < G.STILL_PX
    and math.abs((cy - dn.y) * s) < G.STILL_PX
  if not still then
    dn = { x = cx, y = cy, rot = rot, s = s, half = half, version = G.drawVersion }
    G.drawn = dn
  end
  -- the tiles shown last, to draw again unchanged (`laidFor`: what they were laid out for), or nil.
  -- Panned with the turn, scale and size unchanged, they're kept too while they still cover the view
  -- (the land's and the zones' layouts lay tiles out to 1.42 x the zoom round their center): the layer
  -- they sit on (G.quadLayer) is moved once instead of every tile placed again.
  local lt = G.laidTiles
  local wantSig
  local function TilesKept(laidFor)
    wantSig = laidFor
    -- (laid for this very view, still: kept TILE_REFRESH_STILL; issue #191, laying them again was most of an idle redraw)
    local laidHere = still and lt and math.abs((cx - lt.x) * s) < G.STILL_PX and math.abs((cy - lt.y) * s) < G.STILL_PX
    local fine = lt and lt.laidSig == laidFor and lt.quads
      and now - lt.at < (laidHere and G.TILE_REFRESH_STILL or G.TILE_REFRESH)
      and lt.s == s and lt.half == half and lt.version == G.drawVersion and math.abs(lt.rot - rot) < G.STILL_ROT
    if not fine then return nil end
    if not still then
      -- (only the land and the zones overdraw; a heading square to the view has the least room over it. An inside map
      -- or a cave's over the terrain too: laid with the terrain's tiles round it, its art out past them. Laid again on
      -- every move, they were 1.3.0's stutter, reported 2026-11-15: Undercity walked, its outline thousands of copies;
      -- a flight with the mouse on a building, every redraw. G.LAID_KEPT_MOVING)
      if not G.LaidKeptMoving(laidFor) then return nil end
      local zoomYd, hh = half / s, halfH / s
      local wx = hh * math.abs(math.cos(rot)) + zoomYd * math.abs(math.sin(rot)) -- (the view's reach, world yards)
      local wy = zoomYd * math.abs(math.cos(rot)) + hh * math.abs(math.sin(rot))
      local R = zoomYd * 1.42 - 2
      if math.abs(cx - lt.x) + wx > R or math.abs(cy - lt.y) + wy > R then return nil end
    end
    return lt.quads
  end
  -- The continent whose coordinates this view uses (browsing may show the other one).
  local viewCont = ViewCont(cont)
  local here = viewCont == cont and not hidden
  -- a dungeon or raid: the player in one (the game reports its map), or one opened from its
  -- entrance's icon. Its map: its models' art (or its floors' outline), over its world map where it has one.
  local inst = G.InstanceOf(ns.Nav.InstanceLevel and ns.Nav.InstanceLevel(viewCont) or viewCont)
  view.instance, view.floor = inst, nil
  view.dungeonMap, view.dungeonMapOnly = nil, nil
  view.interiorMap, view.interiorMapOnly = nil, nil
  -- (a cave's map opened from it, G.ShowCave: its models' art on the continent, as a dungeon's)
  -- (the seamless map, issue #62: zoomed out past it, the land round it: G.CaveSeamZoom)
  G.DropHeldIfAway(cx, cy, zoom, viewCont)
  view.cave = not inst and not browse and free and free.cave and G.CaveArt(viewCont, free.cave) or nil
  do -- (a cave hovered, or held: its map, as a building's; G.BuildingHover)
    local h, hk = G.hoverInside, G.hoverInsideKey
    if not (h and h.cave) and G.heldInside and GetTime() <= G.heldInside.untilT then h, hk = G.heldInside.hit, G.heldInside.key end
    if h and h.cave and hk ~= G.hoverDismissKey and not view.cave and not inst and not browse
        and S().interiors ~= false and h.cont == viewCont and not G.IsMapStyle(G.Style()) and G.InteriorZoomOK(zoom) then
      view.cave = G.CaveArt(viewCont, h.cave)
      G.hoveredCave = view.cave and h.cave or nil
    else
      G.hoveredCave = nil
    end
  end
  if view.cave and G.Seamless() and zoom > G.CaveSeamZoom(view.cave) then view.cave = nil end
  local quads
  -- Indoors inside a known building: show its interior map, like the game minimap.
  local place, wmo, room
  local artLevel -- (an underground city's map shown: its level, G.CityArtLevel)
  -- Interiors belong to the terrain view (like the game minimap), and only while zoomed in:
  -- the world map style shows the city's world map, and zooming out shows the outside.
  -- (the player's own inside map only while the view is on them: not a city opened from its
  -- icon, nor looking somewhere else)
  local onMe = not free or (not free.interior and (free.x - px) ^ 2 + (free.y - py) ^ 2 <= (zoom * 1.5) ^ 2)
  -- (down in an underground city: its map anywhere over the city, not only round the player:
  -- zooming in on the cursor moved the view off them, and the outside map flipped in)
  local downCity = here and not onMe and G.DownInCityAt(cont, cx, cy)
  -- (indoors, the inside map at any zoom, as the game's minimap: which map shows is up to indoors or
  -- outdoors, not the zoom)
  -- (Nav.Indoors: the game's, or the dev tools' simulated player's underground switch)
  local indoors = ns.Nav.Indoors and ns.Nav.Indoors() or false
  -- (in a city: down in an underground one, or in a capital's own cells)
  local inCity = here and (ns.Nav.PlayerLevel(cont) ~= cont
    or (ns.Router and ns.Router.CapitalAt and ns.Router.CapitalAt(cont, px, py)) or false)
  -- (in a capital with an inside map, Ironforge: its map while looking over the city, not only round the
  -- player: panning there flipped to the outside, a video 2026-10-01; and wherever the player drags the
  -- view: dragged off the city it flipped to the land, then zoomed out into the black, a third video.
  -- Right-click for the land, as on the player)
  local overCity = here and not onMe and inCity
    and (free.pan and not free.interior or G.OverCity(cont, px, py, cx, cy))
  -- (the route's tour zoomed out past the city's map, a route out of the city: the land around, then the
  -- city's map again as it comes back to the player; it zoomed out over the city's map into the black,
  -- asked 2026-10-01)
  local touringOut = tour and zoom > G.CITY_MAX_ZOOM
  -- (right-clicked out of the city's map, G.LandView: the land, dragged and zoomed anywhere, until
  -- following the player again; a video 2026-10-02: down in Undercity, the land around was black)
  local landView = free and free.land
  -- (the seamless map, issue #62: wheeled out of the inside map, the land round it until back in, G.SeamPastInterior)
  if G.seamOut and (zoom <= G.CITY_MAX_ZOOM or not (indoors or inCity or free and free.interior)) then G.seamOut = nil end
  if st.interiors and not inst and not view.cave and not G.IsMapStyle(G.Style()) and not browse and here and (onMe or downCity or overCity)
      and (zoom <= G.INTERIOR_MAX_ZOOM or (indoors or inCity) and not G.SeamPastInterior(zoom))
      and not touringOut and not landView then
    local lvl = ns.Nav.PlayerLevel(cont)
    local city = ns.CityLevels and ns.CityLevels[lvl]
    local cityZ = city and ns.Nav.CityHeight(lvl, px, py)
    place, wmo, room = G.FindInterior(px, py, pz, cont, GetMinimapZoneText and GetMinimapZoneText(), indoors,
      cityZ, city and city.wmo, G.PlayerCityWmo())
    if not place and not city and onMe then place, wmo, room = G.OpenCityBuildingAt(px, py, cont) end
    -- an underground city's model while up top (the Ruins of Lordaeron): its art there is
    -- mostly black, so the outside map until down in the city
    if place and not city then
      for _, l in pairs(ns.CityLevels or {}) do
        if l.wmo == place[1] then place, wmo, room = nil, nil, nil break end
      end
    end
    -- right-clicked out of a building's inside map: the outside view while in that building
    -- (G.outsideOf, until the player leaves it)
    local building = place and not city and place[1] or nil
    G.outsideOf = G.KeepOutside(G.outsideOf, building)
    if building and G.outsideOf == building then place, wmo, room = nil, nil, nil end
    G.shownInside = place and not city and place[1] or nil
  else
    G.shownInside = nil
  end
  -- (zoomed in, the mouse over a building or a cave anywhere on the map: its inside map, G.BuildingHover; asked
  -- 2026-11-14: "I want this to work for any building I'm hovering anywhere on the map")
  G.zoomedInside = nil
  G.viewZoom = zoom
  local held = G.heldInside
  if held and GetTime() > held.untilT then held, G.heldInside = nil, nil end
  -- (the building under the mouse first, then the one held: another hovered while one is held shows, and a click
  -- there holds that one instead; asked 2026-11-14)
  local hov, hovKey = G.hoverInside, G.hoverInsideKey
  if not hov and held then hov, hovKey = held.hit, held.key end
  if hov and hov.cave then hov = nil end -- (a cave's: its map, view.cave above)
  -- (right-clicked while shown: not again till the mouse leaves it, G.hoverDismissKey; never G.outsideOf, which is by
  -- model: Orgrimmar is one, and one right-click shut every building in it till the map followed again, a video
  -- 2026-11-14)
  if hov and hovKey and hovKey == G.hoverDismissKey then hov = nil end
  -- (over the player's own inside map too: the building under the mouse shows instead; standing in one, hovering
  -- the others did nothing, "when I pan away from my current position I can no longer mouse over buildings")
  local overOwn = place and not (ns.CityLevels and ns.CityLevels[ns.Nav.PlayerLevel(cont)])
  -- (no building hovered, the view's middle over a city you're not in: its whole map, G.CityUnderView)
  if not hov and not place and not inCity and st.interiors and not inst and not view.cave and not G.IsMapStyle(G.Style())
      and not browse and not touringOut and not landView and not (free and free.interior) and G.Seamless() then
    local cp, cw, cr = G.CityUnderView(cx, cy, viewCont, zoom)
    -- (an underground city's map, Undercity, only once down in it: following the player up top at the Ruins of
    -- Lordaeron the view sat over its rooms and the minimap square showed them; asked 2026-11-16 "don't show
    -- undercity on minimap until player is actually in UC after taking the lift down". Down = Nav.PlayerLevel, the
    -- game's best map less the city's upper subzones, as the player's own place uses; a view dragged or opened
    -- from the city's icon still shows it. The minimap square only: on the map, zoomed in over it, its map as ever;
    -- reported 2026-11-16 "zoom in from the map on UC stopped working")
    if cp and not free and G.MinimapMode() then
      for id, l in pairs(ns.CityLevels or {}) do
        if l.wmo == cp[1] and not l.instance and ns.Nav.PlayerLevel(cont) ~= id then cp = nil break end
      end
    end
    if cp then hov = { cp, cw, cr, cont = viewCont, city = true } end
  end
  if hov and (not place or (overOwn and (hov[1] ~= place or hov[3] ~= room))) and st.interiors and not inst and not view.cave
      and not G.IsMapStyle(G.Style()) and not browse
      and not touringOut and not (free and free.interior) and (hov.city or G.InteriorZoomOK(zoom))
      and hov.cont == viewCont then
    place, wmo, room = hov[1], hov[2], hov[3]
    G.zoomedInside, G.shownInside = place[1], place[1]
  end
  -- (the one held stays shown with another hovered, both: asked 2026-11-14, "left click hold interior view works until
  -- I mouse over another building's interior then it goes away")
  G.alsoInside = nil
  if G.zoomedInside and held and not held.hit.cave and hovKey ~= held.key and held.key ~= G.hoverDismissKey
      and held.hit.cont == viewCont then
    G.alsoInside = held.hit
    G.alsoInsideKey = held.key
  end
  -- (the city's map on the player, or dragged off them: zoomed out no further than CITY_MAX_ZOOM, G.WheelZoom)
  G.cityMap = place and inCity and not G.zoomedInside and (not free or free.pan) or false
  -- (its map shown, the capital's grid and its map: the title names the city anywhere in it, the rock
  -- between its halls too, G.InfoParts)
  G.cityGrid, G.cityGridMap = nil, nil
  if place and inCity and ns.Passability and ns.Passability.CapitalGridAt then
    G.cityGrid = ns.Passability.CapitalGridAt(cont, px, py)
    G.cityGridMap = G.cityGrid and G.CityMapAt(cont, px, py) or nil
  end
  if G.cityMap and S().zoom > G.CITY_MAX_ZOOM then
    S().zoom = G.CITY_MAX_ZOOM
    elapsed = 1
  end
  -- a city inside a mountain (Ironforge) opened from its icon: its interior map while looking there
  if not place and free and free.interior and not browse and not G.IsMapStyle(G.Style()) and zoom <= G.INTERIOR_MAX_ZOOM then
    place, wmo, room = free.interior[1], free.interior[2], free.interior[3]
  end
  G.inside = place and ((room.n ~= "" and room.n or "?") .. " / " .. place[1]) or nil
  local instArt, instBand, instFloor = false, nil, 0
  view.mine = here and onMe
  -- (the seamless zoom, issue #57: the stitched map's art under the tiles on the terrain view, and the tiles' share;
  -- not drawn, the tiles as they always were)
  local artA, tileA = G.SeamBlend(zoom)
  -- (in a building, zoomed out past the terrain's tiles on OpenMap: the land's art as anywhere, not the building's
  -- inside map over terrain laid out that far. Opened at 9,135 yd in Tarren Mill's barn it was a continent of tiles on
  -- black until a wheel turn, 2026-11-15. Not a city's: its own zoom rules, G.CITY_MAX_ZOOM)
  if place and artA ~= nil and not inCity and zoom > G.TilesMaxZoom(true) then
    place, wmo, room = nil, nil, nil
    G.shownInside, G.zoomedInside = nil, nil
  end
  -- (the edge blend, issue #62: the land's tiles north up with a cell of no terrain in view, the art whole under
  -- them; G.LayoutMinimap's masks and feathers)
  -- (a dungeon the game hides the position in: only the land at its way in, zoomed out of its map, G.SeamOutOfInstance)
  local edge = artA ~= nil and tileA > 0 and rot == 0 and not inst and not view.cave and not place
    and zoom <= G.TilesMaxZoom(true) and G.EdgeInView(viewCont, cx, cy, zoom) or false
  local artShown = (edge or artA and artA > 0) and not inst and not view.cave and not place
    and G.SeamArt(viewCont, cx, cy, s, edge and 1 or artA) or false
  -- (a building's inside map, an underground city's or a cave's, 2026-11-14: the terrain round it, a little darker, at
  -- any turn; G.InteriorTerrain)
  view.interiorTerrain = not inst and G.InteriorTerrain(not view.cave and place or nil, artA, view.cave) or nil
  view.instTerrain = inst and not browse and G.InstanceTerrainSpot(inst, viewCont, artA) or nil
  -- (the interiors' edge blend, issue #85: a dungeon's, a cave's or an inside map north up, the art whole under its
  -- rooms' dark ground, where it lies on the continent: G.InteriorArtSpot; shown once its art is laid, below)
  view.interiorSpot = artA ~= nil and rot == 0 and not browse and (inst or view.cave or place)
    and not view.interiorTerrain and not view.instTerrain and G.InteriorArtSpot(inst, viewCont) or nil
  view.interiorEdge = nil
  if not artShown then
    if not view.interiorSpot then G.SeamArt(nil) end
    tileA = 1
  end
  view.edge = artShown and edge or nil
  view.artOnly = artShown and tileA <= 0 or nil
  view.seamFar = artShown and G.SeamFar(zoom) or nil
  if inst and not browse then
    -- the game's minimap art of its models, one floor or all; none: its floors' outline (G.DrawFloors, below)
    local floors = G.InstanceFloors(inst)
    instFloor = G.ShownFloor(inst, view.mine and pz or nil)
    view.floor = instFloor
    instBand = instFloor > 0 and floors[#floors - instFloor + 1] or nil
    -- (its world map, another WoW version's where it's laid out alike: under its own art in the terrain view,
    -- alone in the world map's styles; Data/DungeonMaps.lua)
    -- (over the terrain: no world map's parchment under it, as a cave's; G.InstanceTerrainSpot)
    view.dungeonMap = not view.instTerrain and G.DungeonMapFloor(inst, instBand, cx, cy) or nil
    view.dungeonMapOnly = view.dungeonMap and G.IsMapStyle(G.Style()) or nil
    quads = TilesKept("inst:" .. inst .. ":" .. tostring(instBand and instBand[1]) .. ":" .. tostring(instBand and instBand[2])
        .. ":" .. tostring(view.dungeonMap and view.dungeonMap.ui) .. ":" .. tostring(view.dungeonMapOnly)
        .. (view.instTerrain and ":terrain" or view.interiorSpot and ":ground" or ""))
      or G.LayoutDungeon(cx, cy, inst, rot, zoom, half, instBand, view.dungeonMap, view.dungeonMapOnly,
        view.interiorSpot ~= nil, view.instTerrain)
    instArt = #quads > 0
    local n = #floors
    if fl.text then
      -- (the note at the bottom: which floor, and what the dotted line is, in the color picked: issue #18)
      local route = G.DungeonPathsOn(st) and G.PathColorNote(G.DungeonPathColor(st.dungeonPathColor)) or ""
      -- (another addon's Shift-click on the bosses, e.g. StreetView's street views: API.OnIconShiftClick)
      local shift = G.IconHint({ kind = "boss", cont = inst })
      fl.text:SetText((n < 2 and ns.InstanceName(inst) or instFloor == 0 and Format(L["All %d floors"], n)
        or Format(L["Floor %d of %d, from the top"], instFloor, n)) .. route
        .. (view.dungeonMap and #ns.DungeonMaps[inst].floors > 1 and ("\n" .. Format(L["|cff9d9d9dMap: %s|r"], ns.ZoneName(view.dungeonMap.ui, view.dungeonMap.name))) or "")
        .. (shift and ("\n" .. Format(L["|cff9d9d9dShift-click a boss: %s|r"], shift)) or ""))
      fl.count:SetText(n < 2 and "" or instFloor == 0 and L["All"] or (instFloor .. "/" .. n))
      fl.up:SetShown(n >= 2)
      fl.down:SetShown(n >= 2)
      fl.up:SetEnabled(instFloor > 0)
      fl.down:SetEnabled(instFloor < n)
    end
  elseif view.cave then -- (a cave's map opened from it: its art, a floor or all, as a dungeon's)
    quads, instBand, instFloor = G.LayoutCaveMap(cx, cy, rot, zoom, half, TilesKept, view.interiorSpot ~= nil,
      view.interiorTerrain and viewCont or nil)
    instArt = #quads > 0
  elseif place and not browse then
    -- (its world map under it where it has one, the floor of the room's heights: Data/InteriorMaps.lua)
    local terrain = view.interiorTerrain -- (a building's: the terrain round it, 2026-11-14)
    -- (over the terrain, no world map's parchment under it either, as a cave's: 2026-11-15)
    view.interiorMap = not terrain and G.InteriorMapFor(cont, { place }, room and { place[4] + room[3], place[4] + room[6] }, cx, cy) or nil
    local ground = view.interiorSpot ~= nil or terrain -- (the interiors' edge blend, issue #85)
    quads = TilesKept("in:" .. tostring(place[1]) .. ":" .. tostring(room) .. ":" .. tostring(view.interiorMap and view.interiorMap.ui)
        .. (G.alsoInside and (":also:" .. tostring(G.alsoInsideKey)) or "")
        .. (terrain and ":terrain" or ground and ":ground" or ""))
    if not quads then
      quads = G.LayoutUnderMap(view.interiorMap, false, cx, cy, rot, zoom, half, function()
        local q = G.LayoutInterior(cx, cy, place, wmo, room, rot, zoom, half)
        local also = G.alsoInside
        if also and (also[1] ~= place or also[3] ~= room) then
          G.LayoutInterior(cx, cy, also[1], also[2], also[3], rot, zoom, half, false, q)
        end
        if ground and #q > 0 then
          if terrain then -- (a building over the terrain, a whole city's map too, Undercity's, Ironforge's: asked 2026-11-14)
            G.InteriorOutline(q) -- (a building over the terrain: a thin black edge round its art's own shape)
          else
            G.InteriorGround(q, cx, cy, { place }, nil, rot, zoom, half, room, terrain and G.INTERIOR_TERRAIN_FEATHER_YD or nil)
          end
        end
        return q
      end)
      if terrain then G.LayoutInteriorTerrain(quads, cx, cy, viewCont, rot, zoom, half) end
    end
    instArt = #quads > 0
    artLevel = G.CityArtLevel(place[1])
  elseif browse then
    local kept = TilesKept("browse:" .. browse .. ":" .. tostring(G.Style()))
    quads = kept or G.LayoutZone(cx, cy, browse, rot, zoom, half, browseBounds, G.SpoilerMode(G.Style()))
    artLevel = G.CityArtLevel(nil, browse)
    local bm = ns.Maps[browse]
    if bm and bm.worldFrames and browseBounds and not kept then -- (the insets: maps not on the world map's art)
      for _, it in ipairs(G.WORLD_INSETS) do
        if ns.Maps[it.map] then
          -- (the No Spoiler Map's as the map under them: only what was explored, not every area)
          for _, q in ipairs(G.LayoutZone(cx, cy, it.map, rot, zoom, half, G.InsetBounds(it, browseBounds),
              G.SpoilerMode(G.Style()), 3)) do
            quads[#quads + 1] = q
          end
        end
      end
    end
  elseif view.artOnly then -- (the art alone: no tiles)
    quads = TilesKept("art:" .. tostring(viewCont)) or G.NO_QUADS
  elseif G.IsMapStyle(G.Style()) or zoom > G.TilesMaxZoom(artA ~= nil) then
    -- The player's zone map, or a bigger map (continent, world) when zoomed out past it.
    -- (the view moved off somewhere else: the zone there, not the player's)
    local id = free and G.LocateWorld(Geo.Base(viewCont), cx, cy)
    if not id then id = here and G.DisplayMap(Geo.PlayerMap()) or nil end
    local m = id and ns.Maps[id]
    local bounds = m and m.bounds
    if not bounds or math.max(bounds[3] - bounds[1], bounds[4] - bounds[2]) / 2 < zoom * 0.9 then
      id, bounds = G.CoveringMap(viewCont, cx, cy, zoom)
    end
    quads = TilesKept("zone:" .. tostring(id) .. ":" .. tostring(G.Style()))
      or G.LayoutZone(cx, cy, id, rot, zoom, half, bounds, G.SpoilerMode(G.Style()))
    artLevel = G.CityArtLevel(nil, id)
  else
    quads = TilesKept("tiles:" .. tostring(viewCont) .. (view.edge and ":edge" or ""))
      or G.LayoutMinimap(cx, cy, viewCont, rot, zoom, half, view.edge)
  end
  if view.interiorSpot then -- (the interiors' edge blend: the art under its ground; none without its art, as before)
    local sp = view.interiorSpot
    view.interiorEdge = instArt and G.SeamArt(sp[1], cx + sp[2], cy + sp[3], s, 1) or nil
    if not view.interiorEdge then G.SeamArt(nil) end
  end
  if quads ~= (lt and lt.quads) then -- (laid out afresh: drawn, round this center)
    DrawQuads(quads)
    G.laidTiles = { quads = quads, laidSig = wantSig, at = now, x = cx, y = cy, rot = rot, s = s, half = half,
      version = G.drawVersion }
    if G.quadLayer then
      G.quadLayer:ClearAllPoints()
      G.quadLayer:SetPoint("CENTER", canvas, "CENTER", 0, 0)
    end
  elseif G.quadLayer and lt then -- (kept: the layer where the tiles' center now is)
    local ldx, ldy = Geo.ScreenOffset(cx, cy, lt.x, lt.y)
    ldx, ldy = Geo.Rotate(ldx * s, ldy * s, rot)
    G.quadLayer:ClearAllPoints()
    G.quadLayer:SetPoint("CENTER", canvas, "CENTER", ldx, ldy)
  end
  if G.quadLayer and G.quadAlpha ~= tileA then -- (fading out over the art)
    G.quadLayer:SetAlpha(tileA)
    G.quadAlpha = tileA
  end
  if G.pathColorBox then
    G.pathColorBox:SetShown(G.ShowsPathColorPicker(inst, browse, st))
    if not G.pathColorBox:IsShown() and G.pathColorList then G.pathColorList:Hide() end
  end
  if fl.bar then
    fl.bar:SetShown((inst or view.cave) ~= nil and not browse and #G.InstanceFloors(inst or view.cave) >= 2)
    fl.text:SetShown((inst or view.cave) ~= nil and not browse)
    -- (Confirm Route above the dungeon's note, not over it)
    routeBtn:ClearAllPoints()
    if fl.text:IsShown() then routeBtn:SetPoint("BOTTOM", fl.text, "TOP", 0, 3) else routeBtn:SetPoint("BOTTOM", 0, 22) end
  end
  -- (its floors filled under the art: the parts with none, a courtyard or a raid out in the open,
  -- still show where you can walk)
  -- (not over a world map of it: the map draws its floors)
  -- (the interiors' edge blend, issue #85: no dark ground over the whole map, the art round the rooms' own)
  G.DrawFloors((inst or view.cave) and not browse,
    inst and not browse and not instBand and not view.dungeonMap and G.BlockEdges(inst, cx, cy, zoom) or nil,
    cx, cy, rot, s, view.interiorEdge or view.interiorTerrain or view.instTerrain) -- (the terrain round a cave's or
    -- a dungeon's map: none over it)
  ns.PerfEnd("redraw: tiles", pt)
  pt = ns.PerfStart()
  segN = 0
  G.DrawInsetFrames(cx, cy, rot, s)
  G.RefreshFloorHint() -- (the tools on: which floor the player is on, as they move)
  -- (the roads of the continent in view, the player's or another)
  local forced = not st.showRoads and G.ForcedRoadColor() or nil -- (asked for by another addon: Api.lua)
  -- (an underground city's map: its level's roads; not over another inside map, a building's)
  G.shownLevel, G.shownCont = artLevel or viewCont, viewCont
  -- (the road network: the option, the Show Roads and Walls button, or the road tools on)
  -- (not over a building's inside map, an inn's; but a capital's inside, Ironforge's, is its streets:
  -- its roads, and the road tools' edits, show there)
  local capitalInside = place and not artLevel and ns.Router and ns.Router.CapitalAt and ns.Router.CapitalAt(viewCont, cx, cy)
  if (st.showRoads or G.roadMode or forced) and (not place or artLevel or capitalInside)
      and not (view.artOnly and not G.SeamDataNear(zoom)) then -- (the art alone, far out: its own roads)
    for _, sg in ipairs(G.LayoutRoads(cx, cy, inst or artLevel or viewCont, rot, zoom, half)) do
      AddSeg(sg[1], sg[2], sg[3], sg[4], forced or sg[5], forced and 4 or nil, forced and 0.9 or sg[6])
    end
  end
  -- walls (blood red): with the roads shown, or the road tools on
  if inst then -- a dungeon's map: its floors' outline where there's no art (and walls drawn in it)
    for _, sg in ipairs(G.LayoutWalls(cx, cy, inst, rot, zoom, half, not instArt)) do
      AddSeg(sg[1], sg[2], sg[3], sg[4], sg.own and G.OWN_WALL_COLOR or sg.edge and 8 or 7, sg.edge and 2 or 3)
    end
    -- the usual way through, boss by boss (dotted, in the color picked; a route set in here goes over it)
    if not browse and G.DungeonPathsOn(st) then
      -- (the stretches to bosses already down faded, the one to the next boss bright)
      local path, _, legs = G.SuggestedPath(inst)
      local reach = half * 1.5
      local nextIdx = G.NextBoss(inst) or math.huge
      local pc = G.DungeonPathColor(st.dungeonPathColor)
      local lx, ly
      local leg = 1
      for i = 1, #path - 1, 2 do
        local k = (i + 1) / 2 -- (this point's number)
        while legs and legs[leg] and k > legs[leg][2] do leg = leg + 1 end
        local dx, dy = Geo.ScreenOffset(cx, cy, path[i], path[i + 1])
        dx, dy = Geo.Rotate(dx * s, dy * s, rot)
        if lx and k > (legs and legs[leg] and legs[leg][1] or 0) and not ((lx > reach and dx > reach)
            or (lx < -reach and dx < -reach) or (ly > reach and dy > reach) or (ly < -reach and dy < -reach)) then
          if leg < nextIdx then
            AddSeg(lx, ly, dx, dy, pc.color, 2, 0.25, true, true) -- (done)
          elseif leg == nextIdx then
            AddSeg(lx, ly, dx, dy, pc.next, 5, 1, true, true) -- (the way to the next boss)
          else
            AddSeg(lx, ly, dx, dy, pc.color, 3, 0.7, true, true)
          end
        end
        lx, ly = dx, dy
      end
    end
  elseif G.ShowsWalls() and not (view.artOnly and not G.SeamDataNear(zoom)) then -- (inside maps too: a city's own floors and walls)
    local wc = artLevel or viewCont -- (the level shown: an underground city's on its map)
    -- (the terrain's impassable borders thinner, drawn walls thicker)
    for _, sg in ipairs(G.LayoutWalls(cx, cy, wc, rot, zoom, half, true)) do
      AddSeg(sg[1], sg[2], sg[3], sg[4], sg.own and G.OWN_WALL_COLOR or 7, sg.edge and 2 or 3,
        sg.faint and G.OTHER_FLOOR_ALPHA or nil)
    end
  end
  -- Quest objective areas (Layers.lua), outlined in the minimap's blue, on their own layer.
  local layerMaps = { Geo.PlayerMap(), browse }
  DrawAreas(ns.Layers and G.QuestAreasOn() and not place and not inst, viewCont, cx, cy, zoom, rot, s, half, layerMaps)
  ns.PerfEnd("redraw: roads and quest areas", pt)
  pt = ns.PerfStart()
  -- Route: solid along roads, dotted for the legs to and from the road; destination pin.
  ns.Nav.Tick()
  local dest = ns.Nav.dest
  local route = not hidden and ns.Nav.Route(px, py, cont) or nil
  if route and ns.Nav.RedAsking and ns.Nav.RedAsking() then route = nil end -- (asked "keep this route?": not drawn yet)
  -- (held by another addon: the route goes on, not drawn; the square with its route off, G.SquareHidesRoute: same)
  if route and not G.Held() and not G.SquareHidesRoute() then
    -- Every part of the route, converted into this view's continent coordinates.
    local reach = half * 1.5
    local function toScreen(x, y)
      local dx, dy = Geo.ScreenOffset(cx, cy, x, y)
      return Geo.Rotate(dx * s, dy * s, rot)
    end
    -- Several stops: each leg in the color of its stop's marker (off-road and rides a
    -- darker shade of it); a single destination keeps the usual blues.
    local stops = ns.Nav.stops
    local multi = #stops > 1
    local shades = {}
    local function color(stop, kind, base)
      local d = stops[stop]
      if d and d.corpse then -- the way back to your body: red
        local c, k = ns.Nav.CORPSE_COLOR, kind == 0 and 1 or 0.75
        shades.corpse = shades.corpse or {}
        shades.corpse[k] = shades.corpse[k] or { c[1] * k, c[2] * k, c[3] * k }
        return shades.corpse[k]
      end
      if not multi then return base end
      -- (a ride, a flight, zeppelin, boat or lift: always its own light blue, asked 2026-11-14: "once a route uses a
      -- flight path / zeppelin / boat and another stop is added the ... dotted line color changes, keep this the same")
      if G.RIDE_KINDS[kind] then return base end
      local c = d and ns.Nav.MARKER_COLORS[d.icon or 1]
      if not c then return base end
      local k = kind == 0 and 1 or 0.7
      local key = (d.icon or 1) * 10 + (kind == 0 and 0 or 1)
      shades[key] = shades[key] or { c[1] * k, c[2] * k, c[3] * k }
      return shades[key]
    end
    local questing = ns.Nav.QuestPaused()
    -- (the level shown: the player's, or a city's opened from its icon; the route's stretches
    -- on another level (down in a city while up top, or back up) are drawn faint and dotted,
    -- not as if across what's shown)
    local shown = inst or (here and ns.Nav.PlayerLevel(cont) or viewCont)
    if free and free.interior then
      for lc, l in pairs(ns.CityLevels or {}) do
        if l.wmo == free.interior[1][1] then shown = lc end
      end
    end
    -- (another addon's look for the route, API 14: its color, width, glow, dots; `along`: the yards along the
    -- route so far, for a rainbow)
    local look = G.LatestLook(G.routeLooks) or G.ownRouteLook -- (or the Rainbow of Options > Window)
    local floorOf = {} -- (each stop's floor once a redraw, Nav.StopFloor: not per segment)
    -- (a new route still being checked for a shorter way: faded until it has settled, Nav.Checking; asked 2026-10-08)
    G.routeFade = ns.Nav.Checking and ns.Nav.Checking() and G.CHECKING_ALPHA or 1
    -- One stretch of the route on the screen, in its look: faint and dotted on another level, else solid or dotted.
    local function DrawLeg(ax, ay, bx, by, col, width, dotted, partCont)
      local under = partCont and partCont ~= shown and ns.CityLevels and ns.CityLevels[partCont]
      if under and not under.instance and not ns.CityLevels[shown] then
        -- (down in an underground city while the player is up top: not drawn over the land above)
      elseif partCont and partCont ~= shown and (ns.CityLevels and (ns.CityLevels[partCont] or ns.CityLevels[shown])) then
        AddSeg(ax, ay, bx, by, col, math.max(2, width - 2), 0.45 * G.routeFade, true, true) -- (another level)
      else
        if look and look.glow then AddSeg(ax, ay, bx, by, col, width * 2.6 + 2, 0.3 * G.routeFade, true) end -- (under it)
        if not dotted then
          AddSeg(ax, ay, bx, by, col, width, G.routeFade, true)
        elseif G.dashTexture then
          AddSeg(ax, ay, bx, by, col, width, G.routeFade, true, true)
        else
          local vx, vy = bx - ax, by - ay
          local len = math.sqrt(vx * vx + vy * vy)
          local t, n = 0, 0
          while t < len and n < 400 do
            local t2 = math.min(t + DASH, len)
            AddSeg(ax + vx * t / len, ay + vy * t / len, ax + vx * t2 / len, ay + vy * t2 / len, col, width, G.routeFade, true)
            t, n = t2 + GAP, n + 1
          end
        end
      end
    end
    -- (only the chunks of the route near the view, however turned: G.EachSegmentNear)
    G.EachSegmentNear(route, viewCont, cx, cy, reach * 1.5 / s, function(x1, y1, x2, y2, kind, stop, partCont, along, _, _, part, i)
      if questing and stop == 1 then return end -- in the stop's quest area, spot reached: no way there
      local mid = along
      if look then mid = along + math.sqrt((x2 - x1) ^ 2 + (y2 - y1) ^ 2) / 2 end
      local ax, ay = toScreen(x1, y1)
      local bx, by = toScreen(x2, y2)
      -- nowhere near the view: skip (no dashes, no line objects, no garbage)
      if (ax > reach and bx > reach) or (ax < -reach and bx < -reach) or (ay > reach and by > reach)
          or (ay < -reach and by < -reach) then return end
      local style = ROUTE_STYLE[kind] or ROUTE_STYLE[1]
      local col, width, dotted = G.RouteLegLook(look, color(stop, kind, style[1]), style[2], style[3], kind, mid,
        multi, not (stops[stop] and stops[stop].corpse))
      -- (asked 2026-10-06) the last yards to a stop upstairs or in a cellar (G.FLOOR_LEG_YD round it): dotted in the
      -- stairs color, into the building and up (or down)
      local sd = stops[stop]
      local tx, ty, cx1, cy1, cx2, cy2
      local fl_ = sd and floorOf[sd]
      if sd and fl_ == nil then
        fl_ = ns.Nav.StopFloor(sd) or false
        floorOf[sd] = fl_
      end
      if fl_ then tx, ty = Geo.ToContinent(sd.cont, sd.x, sd.y, viewCont) end
      if tx and ty then cx1, cy1, cx2, cy2 = G.ClipCircle(x1 - tx, y1 - ty, x2 - tx, y2 - ty, G.FLOOR_LEG_YD) end
      if cx1 then
        local ex, ey = toScreen(cx1 + tx, cy1 + ty) -- (where it comes into the circle)
        local fx, fy = toScreen(cx2 + tx, cy2 + ty) -- (where it leaves it, or its end)
        if (ex - ax) ^ 2 + (ey - ay) ^ 2 > 0.25 then DrawLeg(ax, ay, ex, ey, col, width, dotted, partCont) end
        DrawLeg(ex, ey, fx, fy, G.STAIRS_COLOR, width, true, partCont)
        if (bx - fx) ^ 2 + (by - fy) ^ 2 > 0.25 then DrawLeg(fx, fy, bx, by, col, width, dotted, partCont) end
      else
        -- (asked 2026-11-14: "that part of the route should be red ... if they have that setting turned off for avoiding
        -- it should still show red for that area": the stretches in the other faction's guards' reach, Nav.HostileSpans,
        -- red over any look, dotted off the roads as the rest)
        local spans = ns.Nav.HostileSpans and ns.Nav.HostileSpans(part, i)
        if spans then
          ns.Nav.EachHostilePiece(spans, function(t1, t2, hostile)
            DrawLeg(ax + (bx - ax) * t1, ay + (by - ay) * t1, ax + (bx - ax) * t2, ay + (by - ay) * t2,
              hostile and ns.Nav.HOSTILE_COLOR or col, width, dotted, partCont)
          end)
        else
          DrawLeg(ax, ay, bx, by, col, width, dotted, partCont)
        end
      end
    end)
    -- a flight master not learned yet by the route (Nav.LearnOnRoute): a brown line to it from the
    -- route, a detour (listed in the steps)
    -- (not `x, y = learn and ToContinent(...)`: `and` keeps only a call's first value, y was nil and
    -- the redraw failed there, the route and the panel not drawn at all)
    -- (along the roads, as walked: Nav.DetourPath; straight while that's worked out, or with no way found)
    for _, h in ipairs(not questing and ns.Nav.LearnOnRoute(route) or {}) do
      local path = ns.Nav.DetourPath and ns.Nav.DetourPath(h) or { h.rx, h.ry, h.x, h.y }
      local px, py
      for i = 1, #path - 1, 2 do
        local lx, ly = Geo.ToContinent(h.cont, path[i], path[i + 1], viewCont)
        if not (lx and ly) then px = nil break end
        local ax, ay = toScreen(lx, ly)
        if px then AddSeg(px, py, ax, ay, G.DETOUR_COLOR, 3, 1, true, G.dashTexture and true or nil) end
        px, py = ax, ay
      end
    end
  end
  DrawStopPins(function(x, y)
    local dx, dy = Geo.ScreenOffset(cx, cy, x, y)
    return Geo.Rotate(dx * s, dy * s, rot)
  end, viewCont)
  G.DrawParty(cx, cy, rot, s, viewCont) -- (party members: G, not a local of this file's, the 60 limit)
  G.DrawYouHere(cx, cy, rot, s, viewCont) -- (in a dungeon: where the player marked themselves)
  -- a farming area being drawn: its outline so far
  local lasso = G.lasso
  if lasso and lasso.cont == viewCont then
    local pts, lx, ly = lasso.pts, nil, nil
    for i = 1, #pts - 1, 2 do
      local dx, dy = Geo.ScreenOffset(cx, cy, pts[i], pts[i + 1])
      local ax, ay = Geo.Rotate(dx * s, dy * s, rot)
      -- (the magic eraser's stroke: as wide as its circle, filled, the ground it goes over; asked 2026-11-14)
      if lx and lasso.eraser then
        AddSeg(lx, ly, ax, ay, lasso.color, math.min(2 * lasso.r * s, G.ERASER_BAND_MAX_PX), G.ERASER_FILL_ALPHA, true)
      elseif lx then
        AddSeg(lx, ly, ax, ay, lasso.color or LASSO_COLOR, lasso.color and 3 or 2, 1, true)
      end
      lx, ly = ax, ay
    end
    -- (the controller's corners: on to the crosshair, the map's middle, and a dotted line back to the first)
    if lasso.pad and lx then
      AddSeg(lx, ly, 0, 0, LASSO_COLOR, 2, 0.8, true, true)
      if #pts >= 4 and (G.drawKind or "farm") == "farm" then
        local dx, dy = Geo.ScreenOffset(cx, cy, pts[1], pts[2])
        local fx, fy = Geo.Rotate(dx * s, dy * s, rot)
        AddSeg(0, 0, fx, fy, LASSO_COLOR, 2, 0.5, true, true)
      end
    end
  end
  G.DrawEraser(s) -- (the magic eraser's circle at the pointer)
  G.DrawRecording(cx, cy, rot, s, viewCont, half) -- (a walk being recorded: the road tools' Record)
  -- (other addons' lines, through the API's SetOverlay: timed apart from AzerothGPS's own, `/agps debug perf`; their
  -- count in G.overlaySegs)
  local ot = ns.PerfStart()
  G.overlaySegs = segN
  RunOverlays(cx, cy, viewCont, rot, s, half, zoom)
  G.overlaySegs = segN - G.overlaySegs
  ns.PerfEnd("redraw: other addons' lines", ot)
  ot = ns.PerfStart()
  DrawLines(segN, 3, ROAD_COLORS, 0.85)
  ns.PerfEnd("redraw: placing lines", ot)
  ns.PerfEnd("redraw: route (incl. calculation)", pt)
  if G.wmLogLeft and ns.Debug then
    G.wmLogLeft = G.wmLogLeft > 1 and G.wmLogLeft - 1 or nil
    pcall(G.DebugWorldMap, "redraw in the world map", { zoomNow = zoom, s = s, half = half, artA = artA or false,
      tileA = tileA or false, artShown = artShown and true or false, routeNow = route and true or false,
      free = free and true or false, browse = browse or false })
  end
  pt = ns.PerfStart()
  -- (the icons: placed again when the view moved, what they show changed (the route, the stops, the layers), or
  -- ICON_REFRESH on: party members, quests and docks' countdowns stay current)
  local iconSig = table.concat({ tostring(inst), tostring(browse), tostring(place and place[1]), tostring(viewCont),
    tostring(zoom), tostring(ns.Nav.Version()), tostring(ns.Nav.route), tostring(ns.Layers and ns.Layers.version),
    #pending, tostring(instBand and instBand[1]), ns.OtherPins and ns.OtherPins.Stamp() or 0 }, ":")
  -- (kept while they show the same and the view only panned a little: they're culled at the view's edge, so
  -- the layer moves at most ICON_PAN_PX before they're gathered and placed again; a bare strip at the leading
  -- edge lasts at most that far or ICON_REFRESH)
  local li = G.laidIcons
  local iconsLive = li and li.laidSig == iconSig and li.s == s and li.half == half
    and li.version == G.drawVersion and math.abs(li.rot - rot) < G.STILL_ROT
  local idx, idy = 0, 0
  if iconsLive then
    idx, idy = Geo.ScreenOffset(cx, cy, li.x, li.y)
    idx, idy = Geo.Rotate(idx * s, idy * s, rot)
    if math.abs(idx) > G.ICON_PAN_PX or math.abs(idy) > G.ICON_PAN_PX then iconsLive = false end
  end
  local iconsKept = iconsLive and now - li.at < G.ICON_REFRESH
  -- (an ICON_REFRESH with the signature still the same would gather and place the same icons again: only
  -- the docks' countdowns are live, so they're set again on the placed buttons instead, and the gather
  -- runs for real every ICON_FULL_REFRESH; the 2026-10-07 draw profile, ~2 full gathers a second moving)
  if iconsLive and not iconsKept and now - (li.gathered or li.at) < G.ICON_FULL_REFRESH then
    G.RefreshDockTimers()
    li.at = now
    iconsKept = true
  end
  poiLayer:ClearAllPoints()
  if iconsKept then
    poiLayer:SetPoint("CENTER", canvas, "CENTER", idx, idy)
  else
    poiLayer:SetPoint("CENTER", canvas, "CENTER", 0, 0)
    G.laidIcons = { laidSig = iconSig, at = now, gathered = now, x = cx, y = cy, rot = rot, s = s, half = half,
      version = G.drawVersion }
  end
  if not iconsKept then
  local worldView = browse and ns.Maps[browse] and ns.Maps[browse].type <= 1
  -- (each kind's icons out to its own zoom, Options > Map icons: G.IconKinds, asked 2026-11-14)
  view.icons = G.IconKinds(zoom, view.seamFar)
  -- Map layers: quests, gathering nodes, city locations (Layers.lua), outside and inside
  -- (`questsOnly`: the quests' alone; the kinds past their zoom left out, view.icons)
  local function AddMarks(pois, questsOnly)
    if not ns.Layers then return end
    -- (a city's own places show on its level: the player's, or the city opened from its icon)
    local level = here and ns.Nav.PlayerLevel(cont) or nil
    if free and free.interior then
      for lc, l in pairs(ns.CityLevels or {}) do
        if l.wmo == free.interior[1][1] then level = lc end
      end
    end
    local marks = ns.Layers.Marks(viewCont, cx, cy, zoom * 1.45, layerMaps, level, questsOnly, view.icons)
    local w = ns.Layers.drawWatch
    if w and not G.clone then
      local found, inView, sdx, sdy = false, false, false, false
      for _, m in ipairs(marks) do
        if m[4] == w.name and (m[1] - w.x) ^ 2 + (m[2] - w.y) ^ 2 <= 400 then
          found = true
          local dx, dy = Geo.ScreenOffset(cx, cy, m[1], m[2])
          dx, dy = Geo.Rotate(dx * s, dy * s, rot)
          sdx, sdy = math.floor(dx), math.floor(dy)
          inView = math.abs(dx) <= half and math.abs(dy) <= half
          w.icon = tostring(m[3])
        end
      end
      pcall(ns.Layers.NoteDraw, { draw = w.name, marks = #marks, found = found, inView = inView, dx = sdx, dy = sdy,
        half = math.floor(half), zoom = math.floor(zoom), icon = w.icon or false, square = G.MinimapMode() and true or false,
        questsOnly = questsOnly and true or false, poiShown = poiLayer:IsVisible() and true or false,
        viewCont = viewCont or false, cont = cont or false, cx = cx and math.floor(cx) or false, cy = cy and math.floor(cy) or false,
        nodesHere = (ns.db and ns.db.nodes and ns.db.nodes[viewCont]) and #ns.db.nodes[viewCont] or false,
        layerOre = tostring(ns.settings and ns.settings.gps and ns.settings.gps.layerOre),
        sameSt = (ns.settings and ns.settings.gps == st) and true or false,
        filter = tostring(ns.settings and ns.settings.gps and ns.settings.gps.nodeFilter and next(ns.settings.gps.nodeFilter)),
        reach = math.floor(zoom * 1.45), level = level or false })
    end
    for _, m in ipairs(marks) do
      local dx, dy = Geo.ScreenOffset(cx, cy, m[1], m[2])
      dx, dy = Geo.Rotate(dx * s, dy * s, rot)
      if math.abs(dx) <= half and math.abs(dy) <= half then
        pois[#pois + 1] = { 4, dx, dy, m[4], m[1], m[2], nil, nil, icon = m[3], note = m[5], size = m[6], questID = m[10],
          r = m[7], g = m[8], b = m[9], preview = m[11], level = m[12], z = m[13], city = m[14], exact = m[15] }
      end
    end
  end
  -- the pins (Pins.lua, option showCustomPins): those on the level shown (`level`: a dungeon's map, its
  -- own; else the continent in view and the levels drawn in it), faint on another floor than the one
  -- shown or picked
  local function AddPins(pois, level)
    -- the map pin (Import.MapPin: the game's waypoint, Ctrl + left-click), on a continent's or zone's map
    local mp = not level and ns.Import and ns.Import.MapPin and ns.Import.MapPin()
    local mx_, my_
    if mp then mx_, my_ = Geo.ToContinent(mp.cont, mp.x, mp.y, viewCont) end
    if mx_ then
      local dx, dy = Geo.ScreenOffset(cx, cy, mx_, my_)
      dx, dy = Geo.Rotate(dx * s, dy * s, rot)
      if math.abs(dx) <= half and math.abs(dy) <= half then
        pois[#pois + 1] = { 13, dx, dy, L["Map Pin Location"], mp.x, mp.y, level = mp.cont }
      end
    end
    if st.showCustomPins == false or not (ns.Pins and ns.db) or not view.icons.pins then return end
    for _, pin in ipairs(ns.Pins.All()) do
      local x, y
      if level then
        if pin.level == level then x, y = pin.x, pin.y end
      elseif pin.level and pin.x and pin.y then
        x, y = Geo.ToContinent(pin.level, pin.x, pin.y, viewCont)
      end
      if x then
        local dx, dy = Geo.ScreenOffset(cx, cy, x, y)
        dx, dy = Geo.Rotate(dx * s, dy * s, rot)
        if math.abs(dx) <= half and math.abs(dy) <= half then
          pois[#pois + 1] = { 12, dx, dy, pin.name, pin.x, pin.y, level = pin.level, z = pin.z, icon = pin.icon, pin = pin,
            dim = G.PinOffFloor(pin, level and instBand), floor = G.PinFloorLabel(pin) }
        end
      end
    end
  end
  -- a stop made from a map icon (a trainer, a flight master) shows that icon: the map's
  -- own one under it isn't drawn as well
  local function DropUnderStops(pois)
    local under = {}
    for _, list in ipairs({ ns.Nav.stops, pending }) do
      for _, d in ipairs(list) do
        if d.tex then
          local x, y = Geo.ToContinent(d.cont, d.x, d.y, viewCont)
          if x then under[#under + 1] = { x, y } end
        end
      end
    end
    -- (and a flight master's detour: its pin is that flight master's icon, right-clickable)
    for _, h in ipairs(ns.Nav.route and ns.Nav.LearnOnRoute(ns.Nav.route) or {}) do
      local x, y = Geo.ToContinent(h.cont, h.x, h.y, viewCont)
      if x then under[#under + 1] = { x, y } end
    end
    -- (and the rides the route takes: their pins are the flight master's or dock's icon, right-clickable)
    for _, h in ipairs(ns.Nav.route and ns.Nav.RidePins(ns.Nav.route) or {}) do
      local x, y = Geo.ToContinent(h.cont, h.x, h.y, viewCont)
      if x then under[#under + 1] = { x, y } end
    end
    local out = {}
    for _, p in ipairs(pois) do
      local drop = false
      if p[1] ~= 3 and p[5] then
        for _, u in ipairs(under) do
          if (u[1] - p[5]) ^ 2 + (u[2] - p[6]) ^ 2 <= 9 then drop = true break end
        end
      end
      -- (a dock under a stop keeps its countdown under the stop's marker: its icon only goes)
      if p[1] == 10 then p.under = drop or nil end
      if not drop or p[1] == 10 then out[#out + 1] = p end
    end
    return out
  end
  if inst and not browse then
    -- a dungeon's map: its bosses (in the usual order) and its ways out
    local pois = {}
    local function add(p)
      local dx, dy = Geo.ScreenOffset(cx, cy, p[5], p[6])
      dx, dy = Geo.Rotate(dx * s, dy * s, rot)
      if math.abs(dx) <= half and math.abs(dy) <= half then
        p[2], p[3] = dx, dy
        pois[#pois + 1] = p
      end
    end
    local info = ns.Instances[inst]
    for _, e in ipairs(info.entrances or {}) do
      if e[4] then add({ 8, 0, 0, Format(L["Way out: %s"], ns.InstanceName(inst)), e[4], e[5], exit = e }) end
    end
    -- stairs to another floor: along the usual way through, and the route's next one
    local function stairs(list, next_)
      for _, c in ipairs(list) do
        add({ 9, 0, 0, c[3] and L["Stairs up"] or L["Stairs down"], c[1], c[2], up = c[3],
          note = next_ and (c[3] and L["The route goes up to the floor above here"] or L["The route goes down to the floor below here"])
            or (c[3] and L["The usual way goes up a floor here"] or L["The usual way goes down a floor here"]), next = next_ })
      end
    end
    local mine = route and route.parts and route.parts[1]
    if mine and mine.cont == inst and mine.zs then
      stairs(G.FloorChanges(mine.pts, mine.zs, 1), true)
    end
    if G.DungeonPathsOn(st) then
      local sp, sz = G.SuggestedPath(inst)
      stairs(G.FloorChanges(sp, sz), false)
    end
    local _, nextBoss = G.NextBoss(inst)
    local wing = G.InstanceWing(inst)
    for _, b in ipairs(info.bosses or {}) do
      if b[3] and G.InWing(b, wing) then
      -- (on another floor than the one shown: faint; down already: faint, and said so)
      local off = instBand and b[5] and (b[5] < instBand[1] - G.FLOOR_HEAD or b[5] > instBand[2] + G.FLOOR_HEAD)
      local dead = ns.Nav.BossDead({ cont = inst, boss = ns.Nav.BossKey(b) })
      add({ 7, 0, 0, (b.order and (b.order .. ". ") or "") .. b[1], b[3], b[4], level = inst, optional = b.optional,
        dim = off or dead, dead = dead, next = nextBoss == b, bossKey = ns.Nav.BossKey(b) })
      end
    end
    AddPins(pois, inst)
    DrawPois(DropUnderStops(pois), zoom)
  elseif (not place or browse) and not worldView then
    local fac = ns.CharDB().faction
    fac = fac == "Horde" and "H" or fac == "Alliance" and "A" or nil
    -- (a continent's map: none of the points of interest, only once in a zone)
    local bm = browse and ns.Maps[browse]
    local pois = {}
    -- (zoomed out on the art past a continent's worth, view.seamFar: no place names; the other kinds out to their own
    -- zoom, view.icons: by default its flight masters and the quests only)
    if not (bm and bm.type == 2) or view.seamFar then
      local k = view.icons
      pois = G.LayoutPois(cx, cy, viewCont, rot, zoom, half,
        { st.poiTaxi and k.taxi, st.poiPoi and k.poi, not view.seamFar and st.poiLabels }, fac)
      AddMarks(pois)
      if st.poiLabels ~= false and not view.seamFar then G.CityLabelPois(pois, viewCont, cx, cy, rot, s, half, zoom) end
    end
    -- a continent's map: its capitals, to click for the city
    if bm and bm.type == 2 then
      for id, m in pairs(ns.Maps) do
        if m.zoneParent and m.continent == bm.continent and m.bounds then
          local x, y = (m.bounds[1] + m.bounds[3]) / 2, (m.bounds[2] + m.bounds[4]) / 2
          local dx, dy = Geo.ScreenOffset(cx, cy, x, y)
          dx, dy = Geo.Rotate(dx * s, dy * s, rot)
          if math.abs(dx) <= half and math.abs(dy) <= half then
            pois[#pois + 1] = { 5, dx, dy, ns.ZoneName(id, m.name), x, y, cityMap = id }
          end
        end
      end
    end
    -- zeppelins' and boats' docks (with points of interest, every map style but the world map):
    -- their next arrival, double-click for a stop there
    if st.poiPoi ~= false and G.ShowsTravelMarkers() then
      local base = Geo.Base(viewCont)
      for i, t in ipairs(ns.Transports or {}) do
        if DOCK_ICON[t[8]] and ns.Nav.TransportUsable(t) then -- (only the player's faction's)
          for side = 1, 2 do
            local c, x, y = t[side == 1 and 1 or 4], t[side == 1 and 2 or 5], t[side == 1 and 3 or 6]
            if c == base then
              local dx, dy = Geo.ScreenOffset(cx, cy, x, y)
              dx, dy = Geo.Rotate(dx * s, dy * s, rot)
              if math.abs(dx) <= half and math.abs(dy) <= half then
                local to = ns.RideEndName(t, side == 1 and 2 or 1)
                local off = not ns.Nav.RideAllowed(t) -- (turned off: still shown, faded; right-click turns it back on)
                pois[#pois + 1] = { 10, dx, dy, DOCK_NAME[t[8]] and Format(DOCK_NAME[t[8]], to or "?") or (to or "?"), x, y,
                  dock = { i, side }, kind = t[8], level = c, dim = off or nil, rideOff = off }
              end
            end
          end
        end
      end
    end
    -- dungeon and raid entrances (every map style but the world map): click for its map
    if st.layerInstances ~= false and G.ShowsTravelMarkers() and view.icons.instances then
      local zoomedOut = (bm and bm.type == 2) or view.seamFar
      for _, e in ipairs(G.InstanceEntrances(Geo.Base(viewCont))) do
        local dx, dy = Geo.ScreenOffset(cx, cy, e.x, e.y)
        dx, dy = Geo.Rotate(dx * s, dy * s, rot)
        if math.abs(dx) <= half and math.abs(dy) <= half and not (zoomedOut and e.shared) then
          -- (a continent's map: one icon where several are, the dungeon's, the whole of it)
          pois[#pois + 1] = { 6, dx, dy, zoomedOut and e.base or e.name, e.x, e.y, instance = e.level, raid = e.raid,
            level = e.cont, wing = not zoomedOut and e.wing or nil }
        end
      end
    end
    -- cave and mine entrances (not on a continent's map: too many there): double-click for a stop
    if st.layerCaves ~= false and not (bm and bm.type == 2) and view.icons.caves then
      for _, e in ipairs(G.CaveEntrances(Geo.Base(viewCont))) do
        local dx, dy = Geo.ScreenOffset(cx, cy, e.x, e.y)
        dx, dy = Geo.Rotate(dx * s, dy * s, rot)
        if math.abs(dx) <= half and math.abs(dy) <= half then
          pois[#pois + 1] = { 11, dx, dy, e.name, e.x, e.y, cave = e.key, caveCont = Geo.Base(viewCont) }
        end
      end
    end
    -- the terrain view: the cities with an inside map of their own (Undercity, Ironforge),
    -- to click for it
    if not browse and not G.IsMapStyle(G.Style()) then
      for _, c in ipairs(G.InteriorCities(viewCont)) do
        local dx, dy = Geo.ScreenOffset(cx, cy, c.x, c.y)
        dx, dy = Geo.Rotate(dx * s, dy * s, rot)
        if math.abs(dx) <= half and math.abs(dy) <= half then
          pois[#pois + 1] = { 5, dx, dy, ns.ZoneName(c.id, c.name), c.x, c.y, cityMap = c.id }
        end
      end
    end
    AddPins(pois) -- (on a continent's map too: a few, not hundreds like the caves)
    DrawPois(DropUnderStops(pois), zoom)
  elseif place and not browse then
    -- inside a building's map (a city like Undercity): its districts' names, like the
    -- world map's, and the quests and city locations
    local pois = {}
    if st.poiLabels ~= false then
      for _, l in ipairs(G.InteriorLabels(place, wmo, room)) do
        local dx, dy = Geo.ScreenOffset(cx, cy, l[1], l[2])
        dx, dy = Geo.Rotate(dx * s, dy * s, rot)
        if math.abs(dx) <= half and math.abs(dy) <= half then
          pois[#pois + 1] = { 3, dx, dy, ns.PlaceName(l[3]), l[1], l[2] }
        end
      end
    end
    AddMarks(pois)
    -- dungeon and raid entrances in it too (asked 2026-10-01: the Deadmines' door, down in the Defias
    -- Hideout's map): click for the dungeon's map
    if st.layerInstances ~= false and G.ShowsTravelMarkers() then
      for _, e in ipairs(G.InstanceEntrances(Geo.Base(viewCont))) do
        local dx, dy = Geo.ScreenOffset(cx, cy, e.x, e.y)
        dx, dy = Geo.Rotate(dx * s, dy * s, rot)
        if math.abs(dx) <= half and math.abs(dy) <= half then
          pois[#pois + 1] = { 6, dx, dy, e.name, e.x, e.y, instance = e.level, raid = e.raid, level = e.cont, wing = e.wing }
        end
      end
    end
    AddPins(pois)
    G.AddInteriorNpcs(pois, place, wmo, room, viewCont, cx, cy, rot, s, half)
    local also = G.alsoInside
    if also and (also[1] ~= place or also[3] ~= room) then
      G.AddInteriorNpcs(pois, also[1], also[2], also[3], viewCont, cx, cy, rot, s, half)
    end
    G.AddRouteStairs(pois, route, viewCont, cx, cy, rot, s, half) -- (down in Undercity: where the route changes floors)
    DrawPois(DropUnderStops(pois), zoom)
  else
    DrawPois({}, zoom)
  end
  -- other addons' world map icons (OtherPins.lua, option otherAddonPins): not in a dungeon's map or on the world map
  if ns.OtherPins and not G.clone then -- (its copies have one place: the first map's)
    local ot = ns.PerfStart()
    local far = view.seamFar or (browse and ns.Maps[browse] and ns.Maps[browse].type == 2)
    ns.OtherPins.Draw(poiLayer, cx, cy, viewCont, rot, s, half, zoom,
      ((inst and not browse) or worldView) and "none" or (far and "far" or "near"))
    ns.PerfEnd("redraw: other addons' icons", ot)
  end
  end -- (not iconsKept)
  ns.PerfEnd("redraw: icons", pt)
  pt = ns.PerfStart()
  G.UpdateNavPanel(px, py, cont, hidden, route, dest)
  ns.PerfEnd("redraw: text", pt)
  -- Once the player starts moving after choosing a destination, follow them again --
  -- but not during the Route Here tour: only dragging or zooming cancels that, and it
  -- ends by zooming in on the player anyway.
  if dest and free and not browse and dest.watchX and not tour and not hidden then
    local mx, my = px - dest.watchX, py - dest.watchY
    if mx * mx + my * my > 4 then
      dest.watchX = nil
      G.Follow()
    end
  end
  -- Free look: crosshair and "Route Here" at the view center.
  local showCross = free ~= nil and free.cross and not (browse and ns.Maps[browse] and ns.Maps[browse].type <= 2)
  if G.Held() then showCross = false end
  crossH:SetShown(showCross)
  crossV:SetShown(showCross)
  G.crossShown = showCross and true or false
  -- (the controller's reticle: only where the map's own crosshair isn't, never two)
  local pad = ns.Pad
  if pad and pad.reticle then
    pad.reticle:SetShown(pad.marksOn and not showCross and not (pad.MenuOpen and pad.MenuOpen()) and true or false)
  end
  routeBtn:SetShown((showCross or #pending > 0) and not G.Held())
  -- with a route set: Clear Route (double-clicks add stops to it directly)
  routeBtn:SetText(#ns.Nav.stops > 0 and L["Clear Route"]
    or (#pending > 0 and Format(L["Confirm Route (%d)"], #pending) or L["Confirm Route"]))
  routeBtn:SetWidth(math.max(128, (routeBtn:GetTextWidth() or 0) + 24))
  if G.mapMenu and G.mapMenu:IsShown() then G.RefreshMapMenu() end

  -- Arrow at the player's real position; it points where they face on this map
  -- (always up while following in heading-up mode).
  local ax, ay = Geo.ScreenOffset(cx, cy, px, py)
  ax, ay = Geo.Rotate(ax * s, ay * s, rot)
  arrow:SetShown(here and not G.MinimapMode()) -- (as the minimap: the game's own arrow over it)
  arrow:ClearAllPoints()
  arrow:SetPoint("CENTER", lineLayer, "CENTER", ax, ay)
  arrow.agpsRot = facing + rot
  arrow:SetRotation(arrow.agpsRot)
  -- North marker orbits the edge in heading-up mode.
  local nx, ny = Geo.Rotate(0, math.min(halfH, canvas:GetWidth() / 2) - 12, rot)
  northLabel:ClearAllPoints()
  northLabel:SetPoint("CENTER", canvas, "CENTER", nx, ny)
  northLabel:Show()

  view.cont = viewCont
  G.UpdateInfo()
end

-- The coordinates line, split (asked, 2026-09-30): with the window frame shown, the place's name is its
-- title ("AzerothGPS" when there's none) and the line at the map's bottom has the coordinates; without
-- it, the whole line at the bottom. (G.infoMark, G.infoName, G.infoXY: from G.UpdateInfo.)
function G.PlaceInfo()
  if not infoText then return end
  local mark, name, xy = G.infoMark or "", G.infoName, G.infoXY
  if ns.settings and ns.settings.gps.showCoords == false then xy = nil end -- (Options > General: hidden)
  local c = G.chrome
  local title = c and c:IsShown() and (c.TitleContainer and c.TitleContainer.TitleText or c.TitleText)
  if title then
    title:SetText(name and name ~= "" and name or "AzerothGPS")
    infoText:SetText(xy and mark .. xy or "")
  else
    infoText:SetText(mark .. (name or "") .. (xy and ((name and "  " or "") .. xy) or ""))
  end
  infoText:Show()
end

-- The coordinates line: the spot under the mouse pointer while it's over the map, else the crosshair
-- while panning, else the player. Runs ~10 times a second on its own (the map redraw is skipped when
-- nothing moves, the pointer may still).
local InfoParts
function G.UpdateInfo()
  if not infoText then return end
  G.infoMark, G.infoName, G.infoXY = InfoParts()
  G.PlaceInfo()
end
-- Its parts: the mark (what it's of: the pointer, the crosshair, or none for the player), the place's
-- name and the coordinates; each nil when there's none.
InfoParts = function()
  local over = canvas:IsMouseOver() and not drag
  local x, y, mark
  if over then
    local mx, my = GetCursorPosition()
    local sc = canvas:GetEffectiveScale()
    local ccx, ccy = canvas:GetCenter()
    x, y = G.ScreenToWorld(view.x, view.y, mx / sc - ccx, my / sc - ccy, view.rot, view.s)
    mark = "|cff80c0ff>|r "
  elseif free and free.cross then
    x, y, mark = view.x, view.y, "|cffffd100+|r "
  end
  if x and view.instance and ns.Instances[view.instance] then -- (a dungeon's map)
    local wing = G.InstanceWing(view.instance)
    return mark, ns.InstanceName(view.instance, wing), string.format("%.0f, %.0f", x, y)
  end
  if x and view.cave and view.cont then -- (a cave's map: its name, the spot on the zone's map)
    local _, _, u, v = G.LocateWorld(view.cont, x, y)
    return mark, view.cave.name, u and string.format("%.1f, %.1f", u * 100, v * 100) or nil
  end
  local cm = G.cityGridMap and ns.Maps and ns.Maps[G.cityGridMap]
  if x and cm and cm.bounds and ns.Passability.InGridRect(G.cityGrid, x, y) then -- (the city's map shown: its name)
    local b = cm.bounds
    return mark, ns.ZoneName(G.cityGridMap, cm.name), string.format("%.1f, %.1f", (b[4] - y) / (b[4] - b[2]) * 100, (b[3] - x) / (b[3] - b[1]) * 100)
  end
  if x and view.cont then
    local zid, name, u, v = G.LocateWorld(view.cont, x, y)
    if name then return mark, ns.ZoneName(zid, name), string.format("%.1f, %.1f", u * 100, v * 100) end
    return mark, nil, nil
  end
  -- (in a dungeon or a map passed through, the Deeprun Tram: its name, and the spot in its own yards)
  local own = view.mine and view.instance and ns.Instances[view.instance]
  if own then
    local wx, wy = Geo.PlayerWorld()
    return nil, ns.InstanceName(view.instance), wx and string.format("%.0f, %.0f", wx, wy) or nil
  end
  if Geo.override then -- (the dev tools' simulated player: its zone and spot, as the game gives the player's)
    local o = Geo.override
    local zid, name, u, v = G.LocateWorld(o.cont, o.x, o.y)
    return nil, ns.ZoneName(zid, name), u and string.format("%.1f, %.1f", u * 100, v * 100) or nil
  end
  local mapID = C_Map.GetBestMapForUnit("player")
  local info = mapID and C_Map.GetMapInfo(mapID)
  local pos = mapID and C_Map.GetPlayerMapPosition(mapID, "player")
  if info and pos then
    local px, py = pos:GetXY()
    return nil, info.name, string.format("%.1f, %.1f", px * 100, py * 100)
  end
  return nil, info and info.name or nil, nil
end

function G.Describe()
  if not frame then return "not created" end
  local st = S()
  return string.format("shown=%s style=%s rotate=%s zoom=%d size=%d alpha=%.2f roads=%s interior=%s quads=%d lines=%d",
    tostring(frame:IsShown()), tostring(G.Style()) .. (G.HeldStyle() and " (held)" or ""), tostring(st.rotate), st.zoom, st.size, st.alpha,
    tostring(st.showRoads), tostring(G.inside), poolUsed, linesUsed) .. (G.lastError and ("\nlast error: " .. G.lastError) or "")
end

local function SavePosition()
  local p, rel, rp, x, y = frame:GetPoint(1)
  S().point = { p, rel and rel:GetName() or "UIParent", rp, x, y }
end

-- The map's size by its bottom-right corner (asked 2026-10-02): with "Resize from the corner" on (`lockSize` off, the
-- default), a grip there; a left-drag sizes the window (square, or any shape with "Any shape": G.FreeSize), its
-- top-left staying put, up to the screen less the title bar (G.SizeMax, G.WidthMax) and room for the quick buttons
-- (G.ClampSize; any shape the width its own, G.ClampWidth).
-- Whether the corner resizes the map (asked 2026-10-03): the option on (`lockSize` off, the default) and the map's
-- position not locked. Locking the position doesn't change the option: unlocking brings the corner back.
function G.Resizable()
  local st = S()
  return st.lockSize == false and not st.locked
end
function G.SizeFromCursor()
  local sc = frame:GetEffectiveScale()
  local cx, cy = GetCursorPosition()
  local l, t = frame:GetLeft(), frame:GetTop()
  if not (l and t) then return nil end
  local dx, dy = cx / sc - l, t - cy / sc
  if G.FreeSize() then -- (any shape: the width and the height apart, each up to the screen, each its own minimum)
    local w = math.floor(math.max(G.SIZE_MIN, math.min(G.WidthMax(), dx)) + 0.5)
    local h = math.floor(math.max(G.SIZE_MIN, math.min(G.SizeMax(), dy)) + 0.5)
    if G.ClampWidth then w = G.ClampWidth(w, true) end
    return G.ClampSize and G.ClampSize(h, true) or h, l, t, w
  end
  local v = math.floor(math.max(G.SIZE_MIN, math.min(G.SizeMax(), math.max(dx, dy))) + 0.5) -- (square)
  return G.ClampSize and G.ClampSize(v, true) or v, l, t
end
function G.MakeSizeGrip()
  local grip = CreateFrame("Button", nil, frame)
  grip:SetSize(16, 16)
  grip:SetPoint("BOTTOMRIGHT", -2, 2)
  grip:SetFrameLevel(frame:GetFrameLevel() + 20 + G.ArtSpan())
  local gbg = grip:CreateTexture(nil, "BACKGROUND") -- (visible even if the old art is missing here)
  gbg:SetPoint("BOTTOMRIGHT")
  gbg:SetSize(8, 8)
  gbg:SetColorTexture(0.6, 0.5, 0.25, 0.6)
  grip:SetNormalTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Up")
  grip:SetHighlightTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Highlight")
  grip:SetScript("OnMouseDown", function(self, button)
    if button == "LeftButton" then self.sizing = true end
  end)
  grip:SetScript("OnMouseUp", function(self)
    if not self.sizing then return end
    self.sizing = false
    SavePosition()
  end)
  grip:SetScript("OnUpdate", function(self)
    if not self.sizing then return end
    local v, l, t, w = G.SizeFromCursor()
    if not v or (v == S().size and (not w or w == S().width)) then return end
    S().size = v
    if w then S().width = w end
    S().point = { "TOPLEFT", "UIParent", "BOTTOMLEFT", l, t } -- (the top-left stays put)
    G.ApplySettings()
  end)
  grip:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText(L["Drag to resize the map"], 1, 1, 1)
    GameTooltip:AddLine(L["Turn off \"Resize from the corner\" (Options, Map window), or lock the map's position, to hide this."], 0.8, 0.8, 0.8, true)
    GameTooltip:Show()
  end)
  grip:SetScript("OnLeave", GameTooltip_Hide)
  G.sizeGrip = grip
  return grip
end

-- The floor buttons' column: right under the window frame's portrait (it hangs over the map's
-- top-left), else under the top panel while it shows, else in the corner.
function G.PlaceFloorBar()
  local bar = fl.bar
  if not bar then return end
  bar:ClearAllPoints()
  if G.wmState.on then -- (in the world map: right of that window's own buttons in the corner, seen in game 2026-11-10)
    if G.NavOnMap() then
      bar:SetPoint("TOPLEFT", navPanel, "BOTTOMLEFT", 2, -4)
    else
      bar:SetPoint("TOPLEFT", bar:GetParent(), "TOPLEFT", G.WORLD_MAP_INSET, -6)
    end
  elseif G.chrome and G.chrome:IsShown() then
    bar:SetPoint("TOPLEFT", bar:GetParent(), "TOPLEFT", 6, -(CHROME_PORTRAIT_INSET + 4))
  elseif G.NavOnMap() then
    bar:SetPoint("TOPLEFT", navPanel, "BOTTOMLEFT", 2, -4)
  else
    bar:SetPoint("TOPLEFT", bar:GetParent(), "TOPLEFT", 6, -6)
  end
end

-- The dungeon map's path color picker (issue #16): at the map's top right while a dungeon's map with its dotted usual
-- way shows (inside one too: the map the game hides the position in), not a map browsed to, nor held by another addon.
-- "Path Color" with a swatch of the one picked; a click lists G.DUNGEON_PATH_COLORS, a click on one saves it
-- (`dungeonPathColor`) and redraws; a click anywhere else closes the list.
function G.ShowsPathColorPicker(inst, browse, st)
  return inst ~= nil and not browse and G.DungeonPathsOn(st) and not G.Held()
end
-- A dungeon's dotted way through shown: Dungeons on, and Show Routes (`showDungeonPaths`, the map menu's toggle)
function G.DungeonPathsOn(st)
  st = st or S()
  return st.layerInstances ~= false and st.showDungeonPaths ~= false
end
function G.PickPathColor(key)
  S().dungeonPathColor = G.DungeonPathColor(key).key
  if G.pathColorList then G.pathColorList:Hide() end
  G.RefreshPathColorPicker()
  G.Redraw()
end
function G.RefreshPathColorPicker()
  local box = G.pathColorBox
  if not box then return end
  local e = G.DungeonPathColor(S().dungeonPathColor)
  box.swatch:SetColorTexture(e.color[1], e.color[2], e.color[3], 1)
  for _, row in ipairs(G.pathColorList and G.pathColorList.rows or {}) do
    row.mark:SetShown(row.key == e.key)
  end
end
-- (under the top panel while it shows, else in the map's top-right corner)
function G.PlacePathColorPicker()
  local box = G.pathColorBox
  if not box then return end
  G.RefreshPathColorPicker() -- (the setting changed elsewhere: Restore Defaults, a profile)
  box:ClearAllPoints()
  if G.NavOnMap() then
    box:SetPoint("TOPRIGHT", navPanel, "BOTTOMRIGHT", -2, -4)
  else
    box:SetPoint("TOPRIGHT", box:GetParent(), "TOPRIGHT", -6, -6)
  end
end
function G.MakePathColorPicker(parent)
  local ROW, W = 18, 104
  local function Edge(f)
    local e = f:CreateTexture(nil, "BACKGROUND", nil, -1)
    e:SetPoint("TOPLEFT", -1, 1)
    e:SetPoint("BOTTOMRIGHT", 1, -1)
    e:SetColorTexture(0.45, 0.45, 0.45, 0.9)
    local bg = f:CreateTexture(nil, "BACKGROUND")
    bg:SetAllPoints()
    bg:SetColorTexture(0.04, 0.04, 0.04, 0.9)
  end
  local function Swatch(f, size, x)
    local s = f:CreateTexture(nil, "ARTWORK")
    s:SetSize(size, size)
    s:SetPoint("LEFT", x, 0)
    return s
  end
  local box = CreateFrame("Button", nil, parent)
  box:SetSize(W, 20)
  box:SetFrameLevel(parent:GetFrameLevel() + 5)
  Edge(box)
  local hl = box:CreateTexture(nil, "HIGHLIGHT")
  hl:SetAllPoints()
  hl:SetColorTexture(1, 1, 1, 0.08)
  box.swatch = Swatch(box, 10, 6)
  local text = box:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
  text:SetPoint("LEFT", 22, 0)
  text:SetText(L["Path Color"])
  box:Hide()
  local list = CreateFrame("Frame", nil, box)
  list:SetFrameStrata("FULLSCREEN_DIALOG")
  list:SetFrameLevel(10)
  list:SetSize(W, #G.DUNGEON_PATH_COLORS * ROW + 2)
  list:SetPoint("TOPRIGHT", box, "BOTTOMRIGHT", 0, -2)
  list:EnableMouse(true)
  Edge(list)
  -- (a click anywhere else: closed; under the list, over everything else)
  local catch = CreateFrame("Button", nil, box)
  catch:SetFrameStrata("FULLSCREEN_DIALOG")
  catch:SetFrameLevel(1)
  catch:SetAllPoints(UIParent)
  catch:SetScript("OnClick", function() list:Hide() end)
  catch:Hide()
  list:SetScript("OnShow", function() catch:Show() end)
  list:SetScript("OnHide", function() catch:Hide() end)
  list.rows = {}
  for i, e in ipairs(G.DUNGEON_PATH_COLORS) do
    local row = CreateFrame("Button", nil, list)
    row:SetSize(W - 2, ROW)
    row:SetPoint("TOPLEFT", 1, -1 - (i - 1) * ROW)
    row.key = e.key
    local rh = row:CreateTexture(nil, "HIGHLIGHT")
    rh:SetAllPoints()
    rh:SetColorTexture(1, 1, 1, 0.1)
    row.mark = Swatch(row, 4, 4)
    row.mark:SetColorTexture(1, 0.82, 0, 1)
    Swatch(row, 10, 12):SetColorTexture(e.color[1], e.color[2], e.color[3], 1)
    local rt = row:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    rt:SetPoint("LEFT", 28, 0)
    rt:SetText(e.name)
    row:SetScript("OnClick", function(self) G.PickPathColor(self.key) end)
    list.rows[i] = row
  end
  list:Hide()
  box:SetScript("OnClick", function()
    if list:IsShown() then list:Hide() else list:Show() end
  end)
  box:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_LEFT")
    GameTooltip:SetText(L["Path Color"], 1, 1, 1)
    GameTooltip:AddLine(L["The color of the dotted usual way through dungeons."], nil, nil, nil, true)
    GameTooltip:Show()
  end)
  box:SetScript("OnLeave", GameTooltip_Hide)
  G.pathColorBox, G.pathColorList = box, list
  G.RefreshPathColorPicker()
  return box
end

-- Minimized (asked 2026-11-09: "a minimize button ... double clicking the icon contract/expand the map ... they hide
-- the map and only leaves the logo icon on screen"; the button gone, the same day: "just use the logo"): a double-click on the window's
-- logo hides the map and leaves the logo alone where it was (G.miniIcon, a button of its own on the screen); a
-- double-click on that brings the map back. Kept over a /reload (`gps.minimized`); the logo dragged moves the map with
-- it (where the map comes back). /agps show, the key binding and the minimap button bring it back too.
G.DOUBLE_CLICK = 0.4 -- s between two clicks on the window's logo (a Frame: no OnDoubleClick of its own)
G.MINI_ICON = "Interface\\AddOns\\AzerothGPS\\Media\\Device" -- (no plate logo drawn yet: the addon's icon)
function G.MiniIcon()
  if G.miniIcon then return G.miniIcon end
  local b = CreateFrame("Button", not G.clone and "AzerothGPSMiniIcon" or nil, UIParent)
  b:SetSize(44, 44)
  b:SetFrameStrata("MEDIUM")
  b:SetClampedToScreen(true)
  b:SetMovable(true)
  b:EnableMouse(true)
  b:RegisterForDrag("LeftButton")
  b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  b.tex = b:CreateTexture(nil, "ARTWORK")
  b.tex:SetAllPoints()
  b:SetScript("OnDoubleClick", function(_, button) if button ~= "RightButton" then G.SetMinimized(false) end end)
  b:SetScript("OnClick", function(_, button) if button == "RightButton" then G.OpenOptions() end end)
  b:SetScript("OnDragStart", function(self)
    self.dragFrom = { self:GetCenter() }
    self:StartMoving()
  end)
  b:SetScript("OnDragStop", function(self)
    self:StopMovingOrSizing()
    local x0, y0 = unpack(self.dragFrom or { self:GetCenter() })
    local x1, y1 = self:GetCenter()
    G.MoveMapBy(x1 - x0, y1 - y0) -- (the map comes back where the logo is now)
    S().miniAt = { x1, y1 }
    G.PlaceMiniIcon()
  end)
  b:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText("AzerothGPS", 1, 1, 1)
    GameTooltip:AddLine(L["Double-click: show the map"], 0.8, 0.8, 0.8)
    GameTooltip:AddLine(L["Right-click: options"], 0.8, 0.8, 0.8)
    GameTooltip:AddLine(L["Drag: move it"], 0.8, 0.8, 0.8)
    GameTooltip:Show()
  end)
  b:SetScript("OnLeave", GameTooltip_Hide)
  b:Hide()
  G.miniIcon = b
  return b
end

-- A right-click on the logo, wherever it shows (the window's corner, minimized, the minimap square's), opens the
-- options (the user, 2026-11-09: "always make right click on the logo ... open options").
function G.OpenOptions()
  local O = ns.Options
  if O and O.Show then O.Show() elseif O and O.Toggle then O.Toggle() end
end

-- The minimized logo on the map window's logo (its picture, size and place on the screen; the addon's icon where the
-- window has no plate logo).
function G.PlaceMiniIcon()
  local b = G.MiniIcon()
  local plate = G.logo and G.logo.plate
  local scale = frame:GetEffectiveScale() / UIParent:GetEffectiveScale()
  if plate and plate.tex and plate.tex:GetTexture() then
    b.tex:SetTexture(plate.tex:GetTexture())
    b.tex:SetTexCoord(plate.tex:GetTexCoord())
    b:SetSize(plate:GetWidth() * scale, plate:GetHeight() * scale)
  else
    b.tex:SetTexture(G.MINI_ICON)
    b.tex:SetTexCoord(0, 1, 0, 1)
    b:SetSize(44, 44)
  end
  -- (where the logo is: the window's top-left corner, over the title bar, frame hidden or not)
  local px = plate and plate:GetCenter() and plate:IsVisible() and { plate:GetCenter() }
  local fs = frame:GetEffectiveScale() / UIParent:GetEffectiveScale()
  local x, y
  if px then
    x, y = px[1] * fs, px[2] * fs
    S().miniAt = { x, y } -- (kept: after a /reload minimized the map's hidden, its logo not placed)
  elseif S().miniAt then
    x, y = S().miniAt[1], S().miniAt[2]
  else
    local left, top = frame:GetLeft(), frame:GetTop()
    if not (left and top) then return end
    x, y = (left + 18) * fs, (top + 10) * fs
  end
  b:ClearAllPoints()
  b:SetPoint("CENTER", UIParent, "BOTTOMLEFT", x, y)
end

-- The map's saved place moved by (dx, dy) screen units (the minimized logo dragged).
function G.MoveMapBy(dx, dy)
  local p = S().point
  if not p then return end
  local fs = frame:GetEffectiveScale() / UIParent:GetEffectiveScale()
  S().point = { p[1], p[2], p[3], (p[4] or 0) + dx / fs, (p[5] or 0) + dy / fs }
  frame:ClearAllPoints()
  frame:SetPoint(p[1], _G[p[2]] or UIParent, p[3], S().point[4], S().point[5])
end

function G.SetMinimized(on)
  local st = S()
  if G.mmState and G.mmState.on then -- (the map as the minimap: minimizing the window takes it back to the square)
    if on then G.SetMinimapExpanded(false) end
    return
  end
  if on then G.PlaceMiniIcon() end -- (before the map's hidden: the logo's place is read off it)
  st.minimized = on and true or nil
  G.ApplySettings()
end

function G.ApplySettings()
  G.ApplySeamPlayer() -- (the OpenMap stages the player set, Options > Map)
  if not frame then return end
  local st = S()
  G.ApplyMinimapReplace() -- (the map as the game's minimap, or back: out of combat only)
  local m = G.mmState
  local mmOn = m.on -- (the map is the minimap: the square, or grown out of it into the window for a while)
  local mmSide = G.MinimapSide() -- (the square: that size, its border, no title, logo, buttons or panels)
  local host = G.WorldMapHosted() -- (laid over the game's world map: its size and place, no frame of its own)
  local wmWanted = G.WorldMapWanted() -- (... and no window of its own while that one is closed)
  G.wmState.on = host
  -- (in the world map: that window's child meanwhile. The game draws its world map as one picture, a frame buffer,
  -- so a frame from outside is under all of it or over all of it whatever its level: outside, at one level over the
  -- game's art, the map was under the whole window, read from the game 2026-11-10. As its child it is in that
  -- picture, between the art and the icons by its level, and fades and hides with the window.)
  -- (And of that window's map canvas itself, the scroll frame's child the game's icons are on: a scroll frame draws
  -- all that's in it as one layer at its own level, so beside it, a child of the window, the map covered every icon
  -- whatever their levels: no quest icons, no other addons' icons, read from the game 2026-11-10. In the canvas it
  -- is one level over the art and far under the icons. The canvas is scaled and scrolled; the map keeps its own
  -- size by the opposite scale (G.WorldMapKeepScale) and its place by its anchor to the scroll frame.)
  do
    local parent = host and G.WorldMapCanvas() or UIParent
    if frame:GetParent() ~= parent then
      if host then G.frameLevelOwn = G.frameLevelOwn or frame:GetFrameLevel() or 0 end
      G.wmOffsets = G.LevelOffsets()
      frame:SetParent(parent)
      if not host then frame:SetScale(1) end
      G.frameStrata, G.wmState.level = "?", nil -- (its strata and level: set again below)
    end
    if host then G.WorldMapKeepScale() end
  end
  G.PlaceCornerButtons(host)
  local held = (mmOn or m.applied) and InCombatLockdown and InCombatLockdown() -- (the game's Minimap: never moved in combat)
  G.drawVersion = G.drawVersion + 1 -- (settings drive what's drawn: the kept tiles and icons are placed again)
  -- the window frame (option, locked or not); without it, an unlocked map has the Move tab
  local framed = G.chrome ~= nil and (st.windowFrame ~= false or mmSide ~= nil) and not host
  local inset = (framed and not mmSide) and CHROME_PORTRAIT_INSET or 4
  -- (in the world map: right of that window's own buttons in the map's top left corner, the map pin's and other
  -- addons' (Questie's): the directions were under them, seen in game 2026-11-10)
  if host then inset = G.WORLD_MAP_INSET end
  if G.chrome then
    G.chrome:SetShown(framed)
    G.ApplyFrameLook() -- (another addon's look for it, kept over the frame's own changes)
    G.PlaceInfo() -- (the coordinates in its title bar, or at the bottom without it)
  end
  if inset ~= G.topInset then
    G.topInset = inset
    for _, fn in pairs(G.layoutHooks) do pcall(fn, inset) end
  end
  -- (the portrait hangs over the map's top-left corner: the top panel starts right of it; its width and side, or
  -- detached: G.PlaceNavPanel)
  G.ApplyNavDetach()
  if G.moveTab then G.moveTab:SetShown(not st.locked and not framed and not mmSide and not host) end
  -- (kept on the screen with what's over its top: the title bar and the logo, or the Move tab; G.SizeMax leaves room)
  local over = (framed and not mmSide) and G.TopRoom() or (not st.locked and not mmSide and not host and G.moveTab and G.MOVE_TAB_ROOM) or 0
  if frame.SetClampRectInsets then frame:SetClampRectInsets(0, 0, over, 0) end
  -- (a bigger or smaller window: the same scale, more or less of the map shown, not the map bigger)
  -- (zoom: yards to the long side's edge, so kept by that side; not as the minimap: its zoom is the minimap's)
  local mw, mh = G.MapSize()
  if not mmSide and not host then -- (the world map's size isn't the player's: their zoom is left alone)
    local long = math.max(mw, mh)
    -- (only when the player sized it: the Size sliders or the corner, `size`/`width`. A size the screen or the quick
    -- buttons' minimum gave it (G.FitSize, G.ClampSize) changing by itself is no resize: at a /reload it came out
    -- different before and after the buttons were laid out, and the zoom was multiplied by that each time, up to the
    -- whole continent's, 16,442 yd; "opening the map after reload ignores zoom level", 2026-11-15)
    local sized = tostring(st.size) .. ":" .. tostring(st.width) .. ":" .. tostring(G.FreeSize())
    if G.sizeShown and G.sizeShown ~= long and st.zoom and G.sizeSetBy and G.sizeSetBy ~= sized then
      st.zoom = math.max(MIN_ZOOM, math.min(G.MaxZoom(), st.zoom * long / G.sizeShown))
    end
    G.sizeShown, G.sizeSetBy = long, sized
  end
  if not m.tween then frame:SetSize(mw, mh) end -- (growing or shrinking: G.MinimapTween sizes it)
  G.LayoutTitle() -- (companions' slots on the title bar: as wide as it is now, shown with it)
  if G.sizeGrip then G.sizeGrip:SetShown(G.Resizable() and not G.clickThrough and not mmSide and not host) end
  local hidden = ns.inCombat and st.combatHideMap and not mmOn and not host
  -- (in the world map: that window's own fade, as its child; the square solid, but grown out of it into the window
  -- the map's opacity again: asked 2026-11-14, "map opacity setting doesn't work when gps minimap is on for the pop out")
  frame:SetAlpha((mmSide or host) and 1 or (ns.inCombat and (st.combatAlpha or st.alpha) or st.alpha))
  if G.RefreshHearthButton then G.RefreshHearthButton() end -- the option may have changed
  -- (grown out of the square: over every other window, the quest log, the world map, bags; else under them all)
  local strata = (mmOn and m.expanded) and G.MINIMAP_EXPANDED_STRATA or "BACKGROUND"
  if host then strata = G.WorldMapStrata() end
  if host then
    G.frameLevelOwn = G.frameLevelOwn or frame:GetFrameLevel() or 0
    local level = G.WorldMapLevel()
    if G.wmState.level ~= level then -- (as it opens, and again whenever the game's window was raised)
      G.wmState.level = level
      G.RaiseWorldMapOverlays(G.SetLevelTree(level, G.wmOffsets, true))
      G.wmOffsets = nil
    end
  elseif G.frameLevelOwn then
    G.wmState.level = nil
    G.SetLevelTree(G.frameLevelOwn, G.wmOffsets, false)
    G.frameLevelOwn, G.wmOffsets = nil, nil
  end
  if host or G.wmGrip then G.WorldMapGrip():SetShown(host and G.WorldMapWindowed()) end
  if (G.frameStrata or "BACKGROUND") ~= strata then
    G.frameStrata = strata
    frame:SetFrameStrata(strata)
    if ns.ApplyLogoLook then pcall(ns.ApplyLogoLook) end -- (the logo's plate keeps its own strata: set again)
    -- (the search's panel has a strata of its own: over the map out too)
    if G.searchPanel then G.searchPanel:SetFrameStrata(strata == "BACKGROUND" and "DIALOG" or ns.POPUP_OVER_STRATA) end
    if ns.SetPopupsOver then ns.SetPopupsOver(strata ~= "BACKGROUND") end -- (our popups over the map out)
  end
  G.ApplyMinimapChrome(mmSide ~= nil)
  if host then
    frame:ClearAllPoints()
    frame:SetPoint("TOPLEFT", G.WorldMapBox(), "TOPLEFT", 0, 0)
  elseif mmSide then
    if not m.tween then G.PlaceMinimapFrame(mmSide) end -- (in the minimap's corner)
  elseif not m.tween then
    frame:ClearAllPoints()
    local p = st.point
    frame:SetPoint(p[1], _G[p[2]] or UIParent, p[3], p[4], p[5])
  end
  -- (the game's Minimap: taken on the square, given back while the map's grown into the window or off; in combat
  -- queued, done as the map is when it ends)
  if held then m.queued = true end
  if G.SyncMinimap() and not held then G.PlaceMinimapItself(G.MinimapSquareSide()) end
  -- (the map in the world map meanwhile, or grown out of the square kept as it is, G.SquareKeptOut: the square keeps a
  -- map of its own, the second map; in combat too. Not where the square is the game's own minimap, G.MinimapAway: the
  -- map shown in the window or the world map all the same)
  local kept = G.SquareKeptOut()
  do
    local stand = not G.clone and (host or (kept and not m.awayIn)) and m.on and m.applied and G.mmAnchor ~= nil
    if (m.second or false) ~= (stand or false) or (m.keptOut or false) ~= kept then
      m.second, m.keptOut = stand or nil, kept or nil
      if ns.Looks and ns.Looks.ApplyCharm then pcall(ns.Looks.ApplyCharm) end
    end
    G.SetCloneActive(stand)
    -- (in the world map too: there it's the map, not the square; the world map black in a dungeon, 1.3.4)
    local shown = (kept or host) and true or false
    if m.awayIn and canvas and (canvas:IsShown() and true or false) ~= shown then canvas:SetShown(shown) end
  end
  if m.applied then -- (grown in combat: the game's own minimap where the square was, G.MinimapCombatStandIn)
    local standIn = m.expanded and held and not kept and true or false -- (kept: it's as it was, nothing to stand in)
    G.MinimapCombatStandIn(standIn)
    local alpha = (m.expanded and not standIn and not kept) and 0 or 1
    if m.alpha ~= alpha then
      m.alpha = alpha
      G.MinimapCall(Minimap, "SetAlpha", alpha)
    end
  end
  G.PlaceMinimapButton()
  frame:SetMovable(not st.locked and not mmSide and not host)
  if topLayer then topLayer:SetShown(not mmSide) end -- (its buttons, panels and text: none on the square)
  -- (as the minimap: always, as the minimap is; else minimized: only the logo, G.SetMinimized. With the world map
  -- option: in that window while it's open, and no window of its own)
  local ownWin = not wmWanted or G.wmState.own -- (with the world map option: its own window only for a fight)
  frame:SetShown(host or (st.shown and not hidden and not st.minimized and ownWin and not G.MinimapAwayHidden()) or mmOn)
  if G.clone then frame:SetShown(G.cloneActive == true) end -- (the second map: only while the first is away)
  local mini = not mmOn and ownWin and st.shown and not hidden and st.minimized
  if mini then G.PlaceMiniIcon() end
  if G.miniIcon or mini then G.MiniIcon():SetShown(mini and true or false) end
  elapsed = 1 -- redraw now
end

-- Whether the map's own fading while moving applies: its own window only, not the minimap square nor in the game's
-- world map (it fades with that window there, the game's mapFade; asked 2026-11-12, Options > Opacity and combat).
function G.MapFades()
  return not (G.MinimapMode() or G.wmState.on)
end
-- Fading while moving: the share of the map's opacity the fading parts should have now.
function G.FadeTarget(st, moving, mouseOver, baseAlpha)
  if not st.fadeMoving or mouseOver or not moving then return 1 end
  if not baseAlpha or baseAlpha <= 0 then return 1 end
  return math.min(1, (st.movingAlpha or 0.4) / baseAlpha)
end

-- The stitched map's art under the map (the seamless zoom, issue #57: Atlas.lua's A.ShowOnMap), at `alpha` (and the
-- fade while moving); `cont` nil: off the map. True when it's drawn.
function G.SeamArt(cont, cx, cy, s, alpha)
  local A = ns.Atlas
  if not cont then
    if A and A.HideOnMap then A.HideOnMap(canvas) end
    G.seamArt = nil
    return false
  end
  local ok = A.ShowOnMap(frame, canvas, frame:GetFrameLevel() + 1, cont, cx, cy, s, alpha * fade)
  G.seamArt = ok and alpha or nil
  return ok
end

local function ApplyFade()
  if not frame then return end
  local A = ns.Atlas
  if G.seamArt and A and A.artHost and A.artBox == canvas then A.artHost:SetAlpha(G.seamArt * fade) end
  tileLayer:SetAlpha(fade)
  areaLayer:SetAlpha(fade)
  poiLayer:SetAlpha(fade)
  topLayer:SetAlpha(fade)
  frame:SetBackdropColor(0.05, 0.05, 0.05, fade)
  frame:SetBackdropBorderColor(0.15, 0.15, 0.15, fade)
  if G.chrome then G.chrome:SetAlpha(fade) end
  -- the crosshair (shown while looking around, not following the player) fades too
  crossH:SetAlpha(fade)
  crossV:SetAlpha(fade)
end

local function PlayerMoving()
  local o = Geo.override -- (the dev tools' simulated player: driven or not)
  if o then return o.moving and true or false end
  if IsPlayerMoving then
    local ok, m = pcall(IsPlayerMoving)
    if ok and not ns.IsSecret(m) then return m and true or false end
  end
  local ok, speed = pcall(GetUnitSpeed, "player")
  return ok and not ns.IsSecret(speed) and speed and speed > 0 or false
end

-- Every frame: fade out while the player moves, back in a moment after they stop (or
-- right away while the mouse is over the map, to use it).
G.PlayerMoving = PlayerMoving

-- Click-through (options, Opacity page): while moving and/or in combat the map ignores the
-- mouse, so clicks go to the game world (targeting, turning the camera) instead.
G.clickThrough = false
local CLICK_HOLD = 0.3 -- seconds after stopping before the map takes clicks again

function G.ClickThroughWanted(st, moving, inCombat)
  if G.clone then return true end -- (the second map only shows)
  if G.wmState.on then return false end -- (in the game's world map: that window's, always clicked; the arrow's own)
  return (st.clickThroughMoving and moving) or (st.clickThroughCombat and inCombat) and true or false
end

-- Every frame of the map (and the frames in it): stop taking the mouse, or go back to how
-- it was (remembered per frame).
local function SetMouse(f, takeMouse)
  if takeMouse then
    if f.agpsMouse ~= nil then f:EnableMouse(f.agpsMouse) end
    if f.agpsWheel ~= nil and f.EnableMouseWheel then f:EnableMouseWheel(f.agpsWheel) end
    f.agpsMouse, f.agpsWheel = nil, nil
  else
    if f.agpsMouse == nil and f.IsMouseEnabled then f.agpsMouse = f:IsMouseEnabled() end
    if f.agpsWheel == nil and f.IsMouseWheelEnabled then f.agpsWheel = f:IsMouseWheelEnabled() end
    if f.EnableMouse then f:EnableMouse(false) end
    if f.EnableMouseWheel then f:EnableMouseWheel(false) end
  end
  for _, c in ipairs({ f:GetChildren() }) do SetMouse(c, takeMouse) end
end

-- The map's frame checks (the fade, its click-through, the quest areas' and roads' hover tooltips) while not fading:
-- this often (seconds), less with Options > Performance's gentle background work (the low-end settings).
G.SETTLED_EVERY, G.SETTLED_EVERY_GENTLE = 0.1, 0.2
function G.SettledEvery() return S().gentleBackground and G.SETTLED_EVERY_GENTLE or G.SETTLED_EVERY end
function G.UpdateFade(dt)
  local now = GetTime()
  if PlayerMoving() then lastMoved = now end
  local through = G.ClickThroughWanted(S(), now - lastMoved < CLICK_HOLD, ns.inCombat)
  if through ~= G.clickThrough then
    G.clickThrough = through
    if through and drag then
      drag = nil
      frame:StopMovingOrSizing()
    end
    SetMouse(frame, not through)
  end
  local target = G.MapFades() and G.FadeTarget(S(), now - lastMoved < FADE_HOLD, canvas:IsMouseOver(), frame:GetAlpha()) or 1
  G.fading = fade ~= target
  if not G.fading then return end
  local step = dt / FADE_SECONDS
  if fade < target then fade = math.min(target, fade + step) else fade = math.max(target, fade - step) end
  G.fading = fade ~= target
  ApplyFade()
  elapsed = 1 -- redraw the lines at the new opacity
end

-- The nav panel's text when the steps are collapsed: just its last line (the whole trip's
-- walking and mounted times, "All stops: ..." or "Next 8 stops: ..."; "Arrived" and the
-- like stay as they are).
function G.CollapsedStatus(status)
  if not status then return "" end
  return status:match("\n([^\n]*)$") or status
end

-- Leave free view and follow the player again (and the inside map again, in a building or a city whose
-- outside was right-clicked to: routing out of Ironforge from inside left its outside shown, 2026-10-01).
function G.Follow()
  G.outsideOf = nil
  G.appended = false
  fromTerrain, openedFrom = nil, nil
  tour = nil
  free = nil
  pending = {}
  browse, browseZoom, browseCont, browseBounds = nil, nil, nil, nil
  if recenter then recenter:Hide() end
  elapsed = 1
end

-- Another addon's view: centered on (x, y) of `cont`, north up, `zoom` yards from the middle to
-- the edge (at least MIN_ZOOM; more than MAX_ZOOM too, as the Route Here tour's). "Back to your
-- position" returns as usual.
function G.LookAt(cont, x, y, zoom)
  browse, browseCont, browseBounds, fromTerrain, openedFrom = nil, nil, nil, nil, nil
  browseZoom = math.max(MIN_ZOOM, zoom or S().zoom)
  free = { x = x, y = y, rot = 0, cont = cont }
  tour = nil
  if recenter then recenter:Show() end
  elapsed = 1
end
-- The controller's pan (Pad.lua): the view moved `dxUI`, `dyUI` UI units (right and up), as a drag the other way does.
-- A controller's press or pan on the map: activity, as a click or drag (the opened-out map's quiet clock, G.MinimapIdle:
-- asked 2026-11-16, "the map is closing now while I'm using the controller to pan, this should count as activity")
function G.MarkActivity()
  lastActivity = GetTime()
end
-- A controller's Select just now (Pad.ClickAt): a double-click then is that and the game's own click, not a stop.
function G.PadClickedJustNow()
  return G.padClickAt ~= nil and GetTime() - G.padClickAt <= 0.6
end
function G.PadPan(dxUI, dyUI)
  if not view.cont or (dxUI == 0 and dyUI == 0) then return end
  lastActivity = GetTime()
  local x, y = G.PanCenter(view.x, view.y, -dxUI, -dyUI, view.rot, view.s)
  tour = nil
  free = { x = x, y = y, rot = view.rot, cross = true, cont = view.cont, interior = free and free.interior, pan = true,
    land = (free and free.land) or (free ~= nil and not free.city and not free.instance and not free.cave and not G.cityMap)
      or nil, cave = free and free.cave }
  if recenter then recenter:Show() end
  elapsed = 1
end
-- The map's Clear Route (its button, the controller's control, /agps clear): the route and its stops gone, the map back
-- on the player. False with no route.
-- `keepView`: the view left where it is (a controller's Clear Route: asked 2026-11-16, "clearing route with controller
-- jumps back to the player position again, shouldn't do that")
function G.ClearRoute(keepView)
  if #ns.Nav.stops == 0 then return false end
  ns.Nav.Clear()
  if not keepView then G.Follow() end -- (the route gone: back to the player, the city's inside map in a city)
  elapsed = 1
  return true
end
-- The view as last drawn (Pad.lua's reticle: the middle): x, y, its level, UI units a yard, the turn.
function G.PadView() return view.x, view.y, view.cont, view.s, view.rot end
-- A stop placed and not confirmed yet (Pad.lua: the one under the reticle).
function G.PendingStop(i) return pending[i] end

-- The mouse wheel: zoom by `f`. A map being browsed zooms freely; the terrain view looked at
-- from elsewhere (LookAt: no map browsed) never out past its tiles (MINIMAP_MAX_ZOOM, where it
-- would turn into map art): only right-click leaves it. Returns the zoom.
function G.WheelZoom(f)
  if not browseZoom then
    local z = math.min(S().zoom, G.MaxZoom()) * f
    if f > 1 then G.LeaveInsideIfAway(z, true) end -- (an inside map opened, zoomed well out of: left in place)
    if G.Seamless() then -- (issue #62: out of a dungeon's map to the land at its way in, and back in to it)
      local back = free and free.seamBack
      if back and f < 1 and z <= back.zoom * 1.001 then return G.SeamBackIn(z) end
      -- (zoomed well out past a dungeon's map: left for good, as a cave's; G.LeaveInstanceIfAway)
      -- (only one opened from its icon: the player's own, the game hiding them in it, comes back)
      if back and f > 1 and back.free and back.free.instance and not back.free.hidden
        and z > back.zoom * G.LEAVE_INSIDE_ZOOM_TIMES then
        free.seamBack = nil
      end
      if f > 1 and G.SeamOutOfInstance(z) then return S().zoom end
    end
    -- (on a city's map: no further out than it; right-click for the land around. The seamless map: on out, the
    -- land past CITY_MAX_ZOOM, G.SeamPastInterior)
    if G.Seamless() and f > 1 and G.inside and z > G.CITY_MAX_ZOOM then G.seamOut = true end
    if G.cityMap and f > 1 and not G.Seamless() then z = math.min(z, math.max(S().zoom, G.CITY_MAX_ZOOM)) end
    G.SetZoom(z)
    return S().zoom
  end
  local z = math.max(MIN_ZOOM, browseZoom * f)
  if not browse and f > 1 then
    z = math.min(z, math.max(G.MaxZoom(), math.min(browseZoom, G.MinimapMaxZoom() - 1)))
  end
  browseZoom = z
  elapsed = 1
  return z
end

-- From browsing a map (a world map style) to the terrain view: over the same spot, about
-- as zoomed, not back on the player.
function G.BrowseToTerrain()
  if not browse then return end
  local x, y, c, z = view.x, view.y, browseCont, browseZoom
  browse, browseZoom, browseCont, browseBounds, fromTerrain = nil, nil, nil, nil, nil
  free = { x = x, y = y, rot = 0, cross = true, cont = c }
  if z then S().zoom = math.max(MIN_ZOOM, math.min(G.MaxZoom(), z)) end
  if recenter then recenter:Show() end
  elapsed = 1
end

-- World-map browsing (zone style): show uiMap `id` whole, north-up, in free view.
-- `cont` picks the continent whose coordinates the world map is drawn in.
function G.Browse(id, cont)
  local m = ns.Maps[id]
  if not m then return end
  local b, c = m.bounds, m.continent
  if not b and m.worldFrames then
    local _, _, pc = Geo.PlayerWorld()
    c = cont or browseCont or pc or 0
    b = Geo.WorldArtBounds(c)
    if not b then -- (a continent with no place on the world map's art: drawn for one that has)
      c = m.worldFrames[0] and 0 or next(m.worldFrames)
      b = c and Geo.WorldArtBounds(c)
    end
  end
  if not b then return end
  browse, browseCont, browseBounds = id, c, b
  browseZoom = math.max(b[3] - b[1], b[4] - b[2]) / 2 * 1.02
  free = { x = (b[1] + b[3]) / 2, y = (b[2] + b[4]) / 2, rot = 0, cross = true }
  if recenter then recenter:Show() end
  elapsed = 1
end

-- One level up from uiMap `id`: a capital city goes to the zone around it (zoneParent,
-- e.g. Undercity -> Tirisfal Glades), a zone to its continent, a continent to the world.
function G.UpMap(id)
  local m = ns.Maps[id]
  if not m then return nil end
  if m.zoneParent and ns.Maps[m.zoneParent] then return m.zoneParent end
  local parent = ns.Maps[m.parent]
  return parent and parent.tiles and m.parent or nil
end

-- Right-click in world-map style: up one level.
function G.ZoomOut()
  if not browse and LeaveOpened() then return end
  local current = browse or G.DisplayMap(Geo.PlayerMap())
  if not current or not ns.Maps[current] then return end
  if not browse then
    G.Browse(current) -- first right-click: the whole zone
  else
    local up = G.UpMap(current)
    if up then G.Browse(up, browseCont) end
  end
end

-- Left-click (no drag) on the map: open the zone (on a continent) or the continent (on
-- the world map) under the cursor.
-- A click on a world map inset: from the terrain view, the terrain there (the whole island in
-- view); in a map style, its map.
function G.OpenInset(it)
  local im = ns.Maps[it.map]
  if not (fromTerrain and im and im.bounds) then
    G.Browse(it.map)
    return
  end
  local ib = im.bounds
  browse, browseZoom, browseCont, browseBounds, fromTerrain, openedFrom = nil, nil, nil, nil, nil, nil
  free = { x = (ib[1] + ib[3]) / 2, y = (ib[2] + ib[4]) / 2, rot = 0, cont = im.continent }
  S().zoom = math.max(MIN_ZOOM, math.min(G.MaxZoom(), G.MapFitZoom(im)))
  if recenter then recenter:Show() end
  elapsed = 1
end

local function OnMapClick(dxUI, dyUI)
  local m = browse and ns.Maps[browse]
  if not m or (m.type > 2 and not fromTerrain) then return end -- (a zone from the terrain view: a spot on it)
  local x, y = G.ScreenToWorld(view.x, view.y, dxUI, dyUI, view.rot, view.s)
  if m.worldFrames then
    local b = browseBounds
    local u, v = (b[4] - y) / (b[4] - b[2]), (b[3] - x) / (b[3] - b[1])
    local it = G.InsetAt(u, v)
    if it then
      G.OpenInset(it)
      return
    end
    for c, wf in pairs(m.worldFrames) do
      if u >= wf[5] and u <= wf[7] and v >= wf[6] and v <= wf[8] then
        for id, o in pairs(ns.Maps) do
          if o.type == 2 and o.continent == c and o.parent == browse then
            G.Browse(id) -- the continent (from the terrain view: then a spot on it)
            return
          end
        end
      end
    end
    return
  end
  if fromTerrain then
    -- picked a spot: back to the terrain view, centered there (free view, crosshair); not in
    -- the open sea (no terrain there, nothing but black)
    local c = browseCont
    if not G.HasTerrain(Geo.Base(c), x, y) then return end
    browse, browseZoom, browseCont, browseBounds, fromTerrain = nil, nil, nil, nil, nil
    free = { x = x, y = y, rot = 0, cross = true, cont = c }
    recenter:Show()
    elapsed = 1
    return
  end
  local zone = G.ZoneAt(x, y, browse)
  if zone then G.Browse(zone) end
end

-- Right-click in the terrain view: the world map (Azeroth) to pick a continent, then a spot
-- on it to come back to the terrain view there. Right-click again goes back up / home.
-- (The continent first, then the world map with both; left-clicks come back down: the
-- world map to a continent, a spot on the continent to the terrain view there.)
local function WorldMapID()
  for id, o in pairs(ns.Maps or {}) do
    if o.worldFrames then return id end
  end
end
-- A continent's map: the world map's child (with the zones), not the small overview some
-- continents also have (no parent, one 512 texture).
function G.ContinentMap(c)
  local best, bestKey
  for id, o in pairs(ns.Maps or {}) do
    if o.type == 2 and o.continent == c and o.bounds then
      local key = ((o.parent or 0) ~= 0 and 1e6 or 0) + (o.artW or 0)
      if not bestKey or key > bestKey or (key == bestKey and id < best) then best, bestKey = id, key end
    end
  end
  return best
end

-- The world map (another addon's view): as right-clicking up to the top. From the terrain view,
-- a continent and then a spot on it lead back to the terrain view there.
function G.ShowWorld()
  local w = WorldMapID()
  if not w then return end
  local _, _, cont = Geo.PlayerWorld()
  openedFrom = nil
  fromTerrain = not G.IsMapStyle(G.Style()) or nil
  G.Browse(w, ViewCont(cont))
end

-- Still outside the building `outside` (right-clicked out of its inside map), with the player in
-- building `building` now (nil: outdoors): that building, or nil once they've left it.
function G.KeepOutside(outside, building)
  if outside and outside ~= building then return nil end
  return outside
end

-- Out of a city's map (Undercity down below, Ironforge's halls, a capital's), right-click: the land's
-- terrain around it, zoomed out (asked 2026-10-02, a video: it went to the continent's map art, and the
-- land past the city stayed black). Dragged or zoomed, still the land (`free.land`), until following again.
function G.LandView()
  local c = Geo.Base(view.cont or select(3, Geo.PlayerWorld()))
  free = { x = view.x, y = view.y, rot = 0, cross = true, cont = c, land = true }
  G.shownInside = nil
  S().zoom = math.max(MIN_ZOOM, math.min(G.MaxZoom(), G.LAND_ZOOM * G.ZoomScale()))
  if recenter then recenter:Show() end
  elapsed = 1
end
G.LAND_ZOOM = 2000 -- yards from the middle to the edge (at the default map size)

function G.TerrainZoomOut()
  -- a building's inside map shown by the mouse or held: that one let go till the mouse leaves it
  if not browse and G.zoomedInside then
    G.hoverDismissKey = G.heldInside and G.heldInside.key or G.hoverInsideKey
    G.heldInside = nil
    G.Redraw()
    return
  end
  -- a city's map shown: the land around it (the continent's map next)
  if not browse and G.cityMap and not (free and (free.instance or free.city)) then
    G.LandView()
    return
  end
  -- in a building, its inside map shown: first the outside view there (the continent's map next)
  if not browse and G.shownInside then
    G.outsideOf, G.shownInside = G.shownInside, nil
    elapsed = 1
    return
  end
  if not browse and LeaveOpened() then return end
  if not browse and G.Seamless() then -- (the seamless zoom: the world on the art, not the world map's browsing)
    G.SeamRightClick()
    return
  end
  local m = browse and ns.Maps[browse]
  local _, _, cont = Geo.PlayerWorld()
  if not browse then
    fromTerrain = true
    local c = Geo.Base(ViewCont(cont))
    local id = G.ContinentMap(c)
    if id then
      G.Browse(id, c) -- this continent's map
      return
    end
    local w = WorldMapID()
    if w then G.Browse(w, ViewCont(cont)) end
  elseif m and m.worldFrames then
    G.Follow() -- from the world map: back to following the player
  elseif fromTerrain then
    local w = WorldMapID()
    if w then G.Browse(w, browseCont) else G.Follow() end
  else
    local up = G.UpMap(browse)
    if up then G.Browse(up, browseCont) else G.Follow() end
  end
end

-- Right-click in the terrain view with the seamless zoom on (issue #74): a shortcut for the wheel, out
-- SEAM_RIGHTCLICK_NOTCHES notches in place (the same middle, nothing recentered), up to the whole world, where it
-- stays (a city's or building's inside map first goes to the land around, as always). Returns the zoom.
G.SEAM_RIGHTCLICK_NOTCHES = 4
function G.SeamRightClickZoom(zoom)
  return math.min(G.MaxZoom(), zoom * G.ZOOM_STEP ^ G.SEAM_RIGHTCLICK_NOTCHES)
end
function G.SeamRightClick()
  local z = math.min(browseZoom or S().zoom, G.MaxZoom()) -- (browseZoom: a view looked at, G.LookAt)
  if z >= G.MaxZoom() * 0.999 then return z end -- (the whole world already: nothing new)
  return G.WheelZoom(G.SeamRightClickZoom(z) / z)
end

-- The interiors on the seamless map (issue #62): the wheel goes on out of an inside map as it does outdoors, the
-- inside map -> the land round it -> its zone -> the continent -> the world, the same stages (G.SeamStages), and
-- back in to the inside map. A city's or a building's inside map, a cave's map: they're on the continent, so past
-- G.CITY_MAX_ZOOM the land shows instead (G.SeamPastInterior) and back in the inside map again, nothing to
-- remember. A dungeon's map is in yards of its own, on no world map: past its own extent (G.InstanceSeamZoom) the
-- view goes to the land at its way in (G.SeamOutOfInstance: the entrance the dungeon's icon is at; the game's
-- marker for it in WoW Forever's own dungeons), and back in past that zoom to the dungeon's map as it was
-- (G.SeamBackIn); a drag or "Back to your position" lets it go. A dungeon with no known way in stops at its own
-- extent, as before, and says so. Never while a game holds the map (G.Seamless): the old rules then.
G.seamNoted = {} -- (the dungeons whose way out was said in the chat this session)

-- whether a city's or a building's inside map gives way to the land at zoom `zoom` (yards): wheeled out past
-- G.CITY_MAX_ZOOM (G.seamOut, from G.WheelZoom; let go back in, or out of the city or the building). A city come
-- into zoomed out is still zoomed in to its map, as always
function G.SeamPastInterior(zoom)
  return G.Seamless() and G.seamOut and zoom > G.CITY_MAX_ZOOM or false
end

-- the furthest a cave's map (G.CaveArt's) zooms out before the land round it takes over: its extent, at least
-- G.CITY_MAX_ZOOM
function G.CaveSeamZoom(art)
  return math.max(G.CITY_MAX_ZOOM, math.max(art.x1 - art.x0, art.y1 - art.y0) / 2 * 1.05)
end

-- the furthest dungeon `inst`'s map zooms out before the land at its way in takes over: its whole extent, at least
-- G.CITY_MAX_ZOOM
function G.InstanceSeamZoom(inst)
  local x0, x1, y0, y1 = G.InstanceBounds(inst)
  local fit = x0 and math.max(x1 - x0, y1 - y0) / 2 * 1.05 or 0
  return math.max(G.CITY_MAX_ZOOM, fit)
end

-- the way out of dungeon `inst` on the continent for the zoom out ({ cont, x, y }) and which data it is, or nil
function G.InstanceWayOut(inst)
  local info = ns.Instances and ns.Instances[inst]
  if not info then return nil end
  local e = G.WingEntrance(inst, G.InstanceWing(inst))
  if e and e[1] and e[2] and e[3] then
    return e, e.guess and "guess" or "entrance"
  end
  local g = info.ghost
  if g and g[1] and g[2] and g[3] then return g, "ghost" end
  return nil
end

-- The wheel out to zoom `z` on a dungeon's map (the last drawn): past its extent, the land at its way in, at that
-- zoom (true); with none known, no further than its extent (true); else false (not a dungeon's map, or still in it)
function G.SeamOutOfInstance(z)
  local inst = not browse and view.instance
  if not inst then return false end
  local limit = G.InstanceSeamZoom(inst)
  if z <= limit then return false end
  local info = ns.Instances[inst]
  local e, how = G.InstanceWayOut(inst)
  if not e then
    if S().zoom < limit then G.SetZoom(limit) end
    if not G.seamNoted[inst] then
      G.seamNoted[inst] = true
      ns.Print(info.name and Format(L["%s isn't on the world map and has no known way in: its map zooms out no further."], ns.InstanceName(inst))
        or L["This dungeon isn't on the world map and has no known way in: its map zooms out no further."])
    end
    return true
  end
  local back = { free = free, openedFrom = openedFrom, zoom = limit, inst = inst }
  openedFrom = nil
  free = { x = e[2], y = e[3], rot = 0, cross = true, cont = e[1], land = true, seamBack = back }
  if not G.seamNoted[inst] then
    G.seamNoted[inst] = true
    ns.Print(Format(how == "guess" and L["Zoomed out of %s to the land at its way in (a guess); zoom back in for its map."]
      or how == "ghost" and L["Zoomed out of %s to the land at the game's marker for its way in; zoom back in for its map."]
      or L["Zoomed out of %s to the land at its way in; zoom back in for its map."], ns.InstanceName(inst) or L["the dungeon"]))
  end
  G.SetZoom(z)
  if recenter then recenter:Show() end
  return true
end

-- The wheel in to zoom `z` past the zoom a dungeon's map was left at (free.seamBack): that map again, as it was
-- (the player's own, followed; one opened from its icon, with the view it was opened from). The zoom it shows.
function G.SeamBackIn(z)
  local back = free.seamBack
  free, openedFrom = back.free, back.openedFrom
  if recenter then recenter:SetShown(free ~= nil) end
  G.SetZoom(math.min(z, back.zoom))
  return S().zoom
end

G.CITY_WMO_YD = 300 -- a building this big at the city is the city (Ironforge, inside its mountain)
G.CITY_INDOOR_SHARE = 0.97 -- ... when about all of its rooms (by area) are indoors

-- A capital that's one huge building (a city inside a mountain): { place, wmo, room } of
-- its main hall, for its interior map; nil for a city in the open.
function G.CityInterior(id)
  local m = ns.Maps and ns.Maps[id]
  if not (m and m.bounds and m.name) then return nil end
  local b = m.bounds
  local cx, cy = (b[1] + b[3]) / 2, (b[2] + b[4]) / 2
  local place, wmo, room = G.FindInterior(cx, cy, nil, m.continent, m.name, true)
  if place and math.max(place[8] - place[6], place[9] - place[7]) >= G.CITY_WMO_YD then
    -- (mostly indoors, like Ironforge: not a city in the open built as one model, like Orgrimmar)
    local indoor, all = 0, 0
    for _, g in ipairs(wmo.groups) do
      local area = (g[4] - g[1]) * (g[5] - g[2])
      all = all + area
      if g["in"] then indoor = indoor + area end
    end
    if all > 0 and indoor >= all * G.CITY_INDOOR_SHARE then return { place, wmo, room } end
  end
end

-- The model of the city with an inside map of its own (G.CityInterior: Ironforge's) the game's map says the player is
-- in, or nil. By map ID: the same in every language, unlike the zone text (#426). Cached per map.
G.cityWmos = {} -- (on G: the main chunk's locals are at Lua's 200)
function G.PlayerCityWmo()
  local ok, id = pcall(function() return C_Map and C_Map.GetBestMapForUnit and C_Map.GetBestMapForUnit("player") end)
  if not (ok and id) then return nil end
  local w = G.cityWmos[id]
  if w == nil then
    local ci = G.CityInterior(id)
    w = ci and ci[1] and ci[1][1] or false
    G.cityWmos[id] = w
  end
  return w or nil
end

-- The capitals on `cont` with an inside map of their own (G.CityInterior): { { id, name, x, y } }.
local interiorCities = {}
function G.InteriorCities(cont)
  local list = interiorCities[cont]
  if list then return list end
  list = {}
  for id, m in pairs(ns.Maps or {}) do
    if m.zoneParent and m.continent == cont and m.bounds and G.CityInterior(id) then
      list[#list + 1] = { id = id, name = m.name, x = (m.bounds[1] + m.bounds[3]) / 2, y = (m.bounds[2] + m.bounds[4]) / 2 }
    end
  end
  interiorCities[cont] = list
  return list
end

-- Before opening a city's or a dungeon's map from its icon: the view now, for right-click
-- to come back to (a zone's or continent's map, or the terrain view). From one opened map to
-- another, still the first.
local function RememberView()
  if view.instance or (free and (free.city or free.instance or free.cave)) then return end
  openedFrom = { browse = browse, browseZoom = browseZoom, browseCont = browseCont, browseBounds = browseBounds,
    fromTerrain = fromTerrain, free = free, zoom = S().zoom }
end

-- A capital picked on a continent's map: the terrain view over the city.
function G.ShowCity(id)
  local m = ns.Maps[id]
  if not (m and m.bounds) then return end
  local b = m.bounds
  RememberView()
  browse, browseZoom, browseCont, browseBounds, fromTerrain = nil, nil, nil, nil, nil
  local cx, cy = (b[1] + b[3]) / 2, (b[2] + b[4]) / 2
  local interior = G.CityInterior(id)
  free = { x = cx, y = cy, rot = 0, cross = true, cont = m.continent, interior = interior, city = id }
  if recenter then recenter:Show() end
  elapsed = 1
end

-- Caves and mines (Data/Caves.lua) ----------------------------------------------------------

-- The caves' and mines' ways in on continent `cont`: { { x, y, name } }. Their mouths are in the
-- caves' road data (caves.py): the nodes on the ground outside each opening, written into
-- `bridge` along with the joins onto the land's roads, so bridge less joins. A cave's mouth
-- nodes within CAVE_MOUTH_MERGE yd of each other (through others too) are one way in (at the
-- node nearest their middle), named
-- after the cave whose grid it opens from (the nearest; "Cave" when it has no name). Worked out
-- once per continent, by buckets (no frame spent on it).
G.CAVE_MOUTH_MERGE = 60
G.CAVE_SAME_YD = 40 -- ... and ways in of the same name closer than this (neighboring models of one cave): one
local caveEntrances = {}
-- (neighboring models of one cave, same name, ways in side by side: one)
local function SameNameMerge(list)
  local near2, out = G.CAVE_SAME_YD ^ 2, {}
  for _, m in ipairs(list) do
    local dup = false
    for _, o in ipairs(out) do
      if o.name == m.name and (o.x - m.x) ^ 2 + (o.y - m.y) ^ 2 < near2 then dup = true break end
    end
    if not dup then out[#out + 1] = m end
  end
  return out
end
function G.CaveEntrances(cont)
  local list = caveEntrances[cont]
  if list then return list end
  list = {}
  caveEntrances[cont] = list
  local P, caves = ns.Passability, ns.Caves and ns.Caves[cont]
  -- (the ways in as the cave builder wrote them, one an opening: each row's fifth field)
  if caves and caves[1] and type(caves[1][5]) == "table" then
    for _, c in ipairs(caves) do
      local name, w = c[1] ~= "" and c[1] or L["Cave"], c[5]
      for k = 1, #w - 1, 2 do list[#list + 1] = { x = w[k], y = w[k + 1], name = name, key = c[2] } end
    end
    list = SameNameMerge(list)
    caveEntrances[cont] = list
    return list
  end
  -- (older data: worked out from the caves' roads)
  -- (the caves' roads: the first entry marked cave, from Data/Caves.lua; the capitals' floors
  -- under others are marked so too, and come after it: Data/Capitals.lua loads later)
  local entry
  for _, o in ipairs(ns.RoadOverlays and ns.RoadOverlays[cont] or {}) do
    if o.cave then
      entry = o
      break
    end
  end
  if not (P and P.GridBounds and caves and entry and entry.n and entry.bridge) then return list end
  -- the caves' grid rectangles, by 256-yd bucket
  local B, buckets, boxes = 256, {}, {}
  for i, c in ipairs(caves) do
    local x0, x1, y0, y1 = P.GridBounds(c[2])
    if x0 then
      boxes[i] = { x0, x1, y0, y1 }
      for bx = math.floor(x0 / B) - 1, math.floor(x1 / B) + 1 do
        for by = math.floor(y0 / B) - 1, math.floor(y1 / B) + 1 do
          local k = bx * 65536 + by
          buckets[k] = buckets[k] or {}
          table.insert(buckets[k], i)
        end
      end
    end
  end
  local joins = {}
  for _, j in ipairs(entry.joins or {}) do joins[j] = true end
  local n, byCave = entry.n, {}
  for _, j in ipairs(entry.bridge) do
    if not joins[j] then
      local x, y = n[2 * j - 1], n[2 * j]
      local best, bd
      for _, i in ipairs(buckets[math.floor(x / B) * 65536 + math.floor(y / B)] or {}) do
        local b = boxes[i]
        local d = math.max(b[1] - x, 0, x - b[2]) ^ 2 + math.max(b[3] - y, 0, y - b[4]) ^ 2
        if not bd or d < bd then best, bd = i, d end
      end
      if best then
        byCave[best] = byCave[best] or {}
        table.insert(byCave[best], { x, y })
      end
    end
  end
  -- a cave's mouth nodes in groups: any two within CAVE_MOUTH_MERGE yd in one (through others
  -- too), each group one way in at its node nearest the group's middle
  local merge2 = G.CAVE_MOUTH_MERGE ^ 2
  local order = {}
  for i in pairs(byCave) do order[#order + 1] = i end
  table.sort(order)
  for _, i in ipairs(order) do
    local pts = byCave[i]
    local root = {}
    for k = 1, #pts do root[k] = k end
    local function find(k)
      while root[k] ~= k do
        root[k] = root[root[k]]
        k = root[k]
      end
      return k
    end
    for k1 = 1, #pts do
      for k2 = k1 + 1, #pts do
        if (pts[k1][1] - pts[k2][1]) ^ 2 + (pts[k1][2] - pts[k2][2]) ^ 2 < merge2 then root[find(k1)] = find(k2) end
      end
    end
    local groups, gorder = {}, {}
    for k = 1, #pts do
      local r = find(k)
      if not groups[r] then
        groups[r] = {}
        gorder[#gorder + 1] = r
      end
      table.insert(groups[r], pts[k])
    end
    local name = caves[i][1] ~= "" and caves[i][1] or L["Cave"]
    for _, r in ipairs(gorder) do
      local gr = groups[r]
      local mx, my = 0, 0
      for _, p in ipairs(gr) do mx, my = mx + p[1] / #gr, my + p[2] / #gr end
      local pick, pd
      for _, p in ipairs(gr) do
        local d = (p[1] - mx) ^ 2 + (p[2] - my) ^ 2
        if not pd or d < pd then pick, pd = p, d end
      end
      list[#list + 1] = { x = pick[1], y = pick[2], name = name, key = caves[i][2] }
    end
  end
  list = SameNameMerge(list)
  caveEntrances[cont] = list
  return list
end

-- Caves' maps (asked 2026-10-06: "if a cave map exists I want to be able to left click and see it like how instances
-- work, right click to exit back to previous map"). This client has no maps of their own for caves (no uiMaps, as for
-- dungeons): a cave's map is the game's own minimap art of its models (ns.Interiors, the WMOs'), shown as a dungeon's
-- (G.LayoutInstanceArt, its floors stepped, a dark ground under it) but on the continent: the route, pins and the
-- player's arrow are where they are. A cave: its row in Data/Caves.lua (`key`, "cave<placement>") matched to its
-- model's art by the placement's spot (CAVE_ART_YD), with the rows of its name whose art touches it (CAVE_GROUP_GAP_YD:
-- one cave of several models, Dreadmaul Rock's three; dens of one name 112 yd apart, Chill Breeze Valley's, are maps of
-- their own). None (an animal's den has no art): nothing to open, as before.
G.CAVE_GROUP_GAP_YD = 20
G.CAVE_ART_YD = 1
G.caveArt = {} -- [cont][key] = the cave's map (G.CaveArt's), or false (on G: the main chunk is at Lua 5.1's 200 locals)
-- Cave `key`'s map on continent `cont`: { list (ns.Interiors rows), x0, y0, x1, y1, name, cont, key }, or nil.
function G.CaveArt(cont, key)
  if not (cont and key) then return nil end
  local byCont = G.caveArt[cont]
  if not byCont then
    byCont = {}
    G.caveArt[cont] = byCont
  end
  local got = byCont[key]
  if got ~= nil then return got or nil end
  byCont[key] = false
  local caves, ints = ns.Caves and ns.Caves[cont], ns.Interiors and ns.Interiors[cont]
  local row
  for _, c in ipairs(caves or {}) do
    if c[2] == key then row = c break end
  end
  local p0 = row and ints and G.InteriorAt(cont, row[3], row[4])
  if not p0 then return nil end
  local art = { list = { p0 }, x0 = p0[6], y0 = p0[7], x1 = p0[8], y1 = p0[9], cont = cont, key = key,
    name = row[1] ~= "" and row[1] or L["Cave"] }
  -- (its other models: of its name, their art within CAVE_GROUP_GAP_YD of one already in, through others too)
  local group, used, grew = { row }, { [row] = true }, row[1] ~= ""
  while grew do
    grew = false
    for _, c in ipairs(caves) do
      local p = not used[c] and c[1] == row[1] and G.InteriorAt(cont, c[3], c[4])
      if p then
        for _, q in ipairs(art.list) do
          local gx, gy = math.max(p[6] - q[8], q[6] - p[8], 0), math.max(p[7] - q[9], q[7] - p[9], 0)
          if gx * gx + gy * gy <= G.CAVE_GROUP_GAP_YD ^ 2 then
            used[c], grew = true, true
            group[#group + 1] = c
            art.list[#art.list + 1] = p
            art.x0, art.y0 = math.min(art.x0, p[6]), math.min(art.y0, p[7])
            art.x1, art.y1 = math.max(art.x1, p[8]), math.max(art.y1, p[9])
            break
          end
        end
      end
    end
  end
  for _, c in ipairs(group) do byCont[c[2]] = art end -- (the same map from any of its models)
  return art
end
-- The ns.Interiors row of the model placed at (x, y) on continent `cont` (within CAVE_ART_YD, with its art), or nil;
-- looked up by 4-yd cells, indexed once per continent (a redraw with many caves' icons in view looks up each).
G.interiorIdx = {}
function G.InteriorAt(cont, x, y)
  local idx = G.interiorIdx[cont]
  if not idx then
    idx = {}
    for _, p in ipairs(ns.Interiors and ns.Interiors[cont] or {}) do
      local k = math.floor(p[2] / 4) * 65536 + math.floor(p[3] / 4)
      local l = idx[k]
      if not l then
        l = {}
        idx[k] = l
      end
      l[#l + 1] = p
    end
    G.interiorIdx[cont] = idx
  end
  local r = G.CAVE_ART_YD
  for gx = math.floor((x - r) / 4), math.floor((x + r) / 4) do
    for gy = math.floor((y - r) / 4), math.floor((y + r) / 4) do
      for _, p in ipairs(idx[gx * 65536 + gy] or {}) do
        if math.abs(p[2] - x) <= r and math.abs(p[3] - y) <= r and ns.WMOs and ns.WMOs[p[1]] then return p end
      end
    end
  end
  return nil
end
-- The models whose minimap art a map is made of (ns.Interiors rows): a dungeon's (its level) or a cave's (G.CaveArt's).
function G.ArtList(key)
  if type(key) == "table" then return key.list end
  local lvl = ns.CityLevels and ns.CityLevels[key]
  return lvl and ns.Interiors and ns.Interiors[lvl.base] or nil
end
-- The cave whose own cells (x, y) on continent `cont` is in (its grid's, not the continent's round it): its key, or nil.
G.caveGrids = {} -- [cont] = { [its grid] = key }
function G.CaveAt(cont, x, y)
  local P = ns.Passability
  if not (P and P.OverlayRaw) then return nil end
  local v, grid = P.OverlayRaw(cont, x, y)
  if v == nil or v == 1 or not (grid and grid.cave) then return nil end
  local map = G.caveGrids[cont]
  if not map then
    map = {}
    for _, c in ipairs(ns.Caves and ns.Caves[cont] or {}) do
      local g = ns.Terrain and ns.Terrain[c[2]]
      if g then map[g] = c[2] end
    end
    G.caveGrids[cont] = map
  end
  return map[grid]
end
-- A cave's map opened (its icon clicked, or the cave itself on the map): fitted in the view, as a dungeon's
-- (G.ShowInstance); right-click goes back (LeaveOpened). False when it has none.
function G.ShowCave(cont, key)
  local art = cont and key and G.CaveArt(cont, key)
  if not art then return false end
  RememberView()
  browse, browseZoom, browseCont, browseBounds, fromTerrain = nil, nil, nil, nil, nil
  free = { x = (art.x0 + art.x1) / 2, y = (art.y0 + art.y1) / 2, rot = 0, cross = true, cont = cont, cave = key }
  S().zoom = math.max(MIN_ZOOM, math.min(G.MaxZoom(), math.max(art.x1 - art.x0, art.y1 - art.y0) / 2 * 1.05))
  if recenter then recenter:Show() end
  elapsed = 1
  return true
end
-- A plain left click on the map at (dxUI, dyUI) from its middle: over a cave with a map, that map, once the click
-- is clear of being a double-click's first (a double-click makes a stop there, as always). True when it will.
function G.CaveClick(dxUI, dyUI)
  if browse or view.instance or (G.Held and G.Held()) then return false end
  local x, y = G.ScreenToWorld(view.x, view.y, dxUI, dyUI, view.rot, view.s)
  local cont = Geo.Base(view.cont or 0)
  local key = G.CaveAt(cont, x, y)
  local art = key and G.CaveArt(cont, key)
  if not art or view.cave == art then return false end
  local mine = lastClick
  C_Timer.After(DOUBLE_CLICK + 0.05, function()
    if lastClick == mine then G.ShowCave(cont, key) end
  end)
  return true
end
-- A cave's map in the redraw (view.cave): its models' art, one floor or all (G.InstanceFloors, stepped with the floor
-- bar; the player's height is never given), and the note under it (its name, the floor shown), as a dungeon's.
-- `kept`: the redraw's TilesKept. Returns the quads, the floor band shown (nil: all) and the floor's number.
-- `ground`: the interiors' edge blend (issue #85), the dark ground under its rooms (G.InteriorGround). `terrain`: the
-- continent of the terrain round it (G.InteriorTerrain, 2026-11-14: the rooms' ground feathered a little over it).
function G.LayoutCaveMap(cx, cy, rot, zoom, half, kept, ground, terrain)
  local art = view.cave
  local floors = G.InstanceFloors(art)
  local k = G.ShownFloor(art, nil)
  view.floor = k
  local band = k > 0 and floors[#floors - k + 1] or nil
  -- (its world map, another WoW version's where its rooms are laid out alike: Data/InteriorMaps.lua)
  -- (over the terrain, none: the art alone with its black outline, not on its world map's parchment; asked 2026-11-15,
  -- Gol'Bolar Quarry Mine: "any cave doing this should be changed to do the black outline trick")
  local f = not terrain and G.InteriorMapFor(art.cont, art.list, band, cx, cy) or nil
  view.interiorMap, view.interiorMapOnly = f, f and G.IsMapStyle(G.Style()) or nil
  local quads = kept("cave:" .. art.key .. ":" .. tostring(band and band[1]) .. ":" .. tostring(f and f.ui)
      .. ":" .. tostring(view.interiorMapOnly) .. (terrain and ":terrain" or ground and ":ground" or ""))
  if not quads then
    quads = G.LayoutUnderMap(f, view.interiorMapOnly, cx, cy, rot, zoom, half, function()
      local q = G.LayoutInstanceArt(cx, cy, art, rot, zoom, half, band)
      if terrain and #q > 0 then
        G.InteriorOutline(q) -- (as a building's: the thin black edge round its art, not dark squares; asked 2026-11-14)
      elseif ground and #q > 0 then
        G.InteriorGround(q, cx, cy, art.list, band, rot, zoom, half, nil, nil)
      end
      return q
    end)
    if terrain then G.LayoutInteriorTerrain(quads, cx, cy, terrain, rot, zoom, half) end
  end
  local n = #floors
  if fl.text then
    fl.text:SetText((n < 2 and art.name or k == 0 and Format(L["%s: all %d floors"], art.name, n)
      or Format(L["%s: floor %d of %d, from the top"], art.name, k, n))
      .. (f and #G.InteriorMapFloors(art.cont, art.list) > 1 and ("\n" .. Format(L["|cff9d9d9dMap: %s|r"], f.name)) or ""))
    fl.count:SetText(n < 2 and "" or k == 0 and L["All"] or (k .. "/" .. n))
    fl.up:SetShown(n >= 2)
    fl.down:SetShown(n >= 2)
    fl.up:SetEnabled(k > 0)
    fl.down:SetEnabled(k < n)
  end
  return quads, band, k
end

-- Dungeons and raids (Data/Instances.lua) --------------------------------------------------

-- Level `lvl` if it's a dungeon's or raid's, else nil.
function G.InstanceOf(lvl)
  local l = lvl and ns.CityLevels and ns.CityLevels[lvl]
  return l and l.instance and ns.Instances and ns.Instances[lvl] and lvl or nil
end

-- The dungeon and raid entrances on continent `cont`: { { level, name, raid, cont, x, y,
-- shared } } (shared: another's within 60 yd, e.g. the Scarlet Monastery's wings, Blackrock
-- Mountain's; only the first of those shows on a continent's map).
local entrances = {}
function G.InstanceEntrances(cont)
  local list = entrances[cont]
  if list then return list end
  list = {}
  local levels = {}
  for lvl in pairs(ns.Instances or {}) do levels[#levels + 1] = lvl end
  table.sort(levels)
  for _, lvl in ipairs(levels) do
    local info = ns.Instances[lvl]
    -- (in through another dungeon, Blackwing Lair: its icon where the ghost's way in is)
    local list_ = info.ghost and { { info.ghost[1], info.ghost[2], info.ghost[3] } } or info.entrances or {}
    for _, e in ipairs(list_) do
      if e[1] == cont then
        local shared = false
        for _, o in ipairs(list) do
          if (o.x - e[2]) ^ 2 + (o.y - e[3]) ^ 2 <= 60 * 60 then shared = true break end
        end
        -- (a wing's: its icon of its own, named, "Scarlet Monastery: Library"; a second door into the
        -- same wing at the same spot left out)
        local wing = not info.ghost and e[7] or nil
        local same = e.guess and not info.ghost or false -- (a wing guessed, its spot too: no icon, Data/Instances.lua)
        for _, o in ipairs(list) do
          if o.level == lvl and o.wing == wing and (o.x - e[2]) ^ 2 + (o.y - e[3]) ^ 2 <= 10 * 10 then same = true break end
        end
        if not same then
          local name = ns.InstanceName(lvl, wing, e.door) -- (in the game's language)
          list[#list + 1] = { level = lvl, name = name, raid = info.raid, cont = e[1], x = e[2], y = e[3], shared = shared,
            wing = wing, base = ns.InstanceName(lvl) }
        end
      end
    end
  end
  entrances[cont] = list
  return list
end

-- The way in a stop picked in dungeon `lvl`'s map at (x, y) goes to instead: its entrance on the continent,
-- the icon there ({ cont, x, y, name }), or nil when it has none. Of several, the one whose way in is
-- nearest (x, y) (a wing's: the Scarlet Monastery's); with no inside end (WoW Forever's own dungeons),
-- the one nearest the player (`pcont`, px, py: on their continent first).
function G.InstanceStopEntrance(lvl, x, y, pcont, px, py)
  local info = ns.Instances and ns.Instances[lvl]
  if not info then return nil end
  local list = info.ghost and { info.ghost } or info.entrances or {}
  local wing = G.InstanceWing(lvl) -- (a wing's map: that wing's way in)
  local best, bd
  for _, e in ipairs(list) do
    local d
    if wing and e[7] and e[7] ~= wing then
      d = nil -- (another wing's)
    elseif e[4] and e[5] then
      d = (e[4] - x) ^ 2 + (e[5] - y) ^ 2
    elseif pcont and px and Geo.Base(pcont) == e[1] then
      d = (e[2] - px) ^ 2 + (e[3] - py) ^ 2
    else
      d = math.huge
    end
    if d and (not bd or d < bd) then best, bd = e, d end
  end
  return best and { cont = best[1], x = best[2], y = best[3], name = ns.InstanceName(lvl, best[7]) } or nil
end

-- Dungeons reached through a cave of their own on the continent (asked 2026-10-01: the Deadmines, through the
-- Defias Hideout): a stop at the dungeon's way in, made from outside that cave, is the cave's way in instead
-- (Data/Caves.lua's key; its opening nearest the player), and the cave's map takes it from there. From down
-- in the cave, the dungeon's door.
G.ENTRANCE_VIA = { [20036] = "cave35530" }
G.ENTRANCE_NEAR_YD = 15 -- a stop this near a dungeon's way in is one at it
function G.ApproachEntrance(stopCont, x, y, pcont, px, py)
  local base = Geo.Base(stopCont or 0)
  for lvl, key in pairs(G.ENTRANCE_VIA) do
    local info = ns.Instances and ns.Instances[lvl]
    for _, e in ipairs(info and info.entrances or {}) do
      if e[1] == base and (e[2] - x) ^ 2 + (e[3] - y) ^ 2 <= G.ENTRANCE_NEAR_YD ^ 2 then
        -- (the player down in that cave already: the door)
        local P = ns.Passability
        if px and pcont and Geo.Base(pcont) == base and P and P.OverlayRaw then
          local v, o = P.OverlayRaw(base, px, py)
          if o and o == (ns.Terrain and ns.Terrain[key]) and (v == 0 or (v == 3 and ns.Nav.Indoors and ns.Nav.Indoors())) then
            return nil
          end
        end
        for _, c in ipairs(ns.Caves and ns.Caves[base] or {}) do
          if c[2] == key and type(c[5]) == "table" and c[5][1] then
            local w, best, bd = c[5], nil, nil
            for k = 1, #w - 1, 2 do
              local d = px and Geo.Base(pcont or base) == base and ((w[k] - px) ^ 2 + (w[k + 1] - py) ^ 2) or k
              if not bd or d < bd then best, bd = k, d end
            end
            return { cont = base, x = w[best], y = w[best + 1], name = Format(L["%s (way to %s)"], c[1], ns.InstanceName(lvl)) }
          end
        end
      end
    end
  end
  return nil
end

-- A dungeon's extent: x0, x1, y0, y1 (its floor grid, else its map's minimap tiles: WoW
-- Forever's own dungeons, their map only), or nil.
function G.InstanceBounds(lvl)
  local P = ns.Passability
  if P and P.GridBounds then
    local x0, x1, y0, y1 = P.GridBounds(lvl)
    if x0 then return x0, x1, y0, y1 end
  end
  local l = ns.CityLevels and ns.CityLevels[lvl]
  local tiles = l and ns.MinimapTiles and ns.MinimapTiles[l.base]
  if not tiles then return nil end
  local x0, x1, y0, y1 = math.huge, -math.huge, math.huge, -math.huge
  for k in pairs(tiles) do
    local tx, ty = math.floor(k / 64), k % 64
    local mx, my = (32 - ty) * TILE, (32 - tx) * TILE -- (the tile's north-west corner)
    x0, x1, y0, y1 = math.min(x0, mx - TILE), math.max(x1, mx), math.min(y0, my - TILE), math.max(y1, my)
  end
  if x0 == math.huge then return nil end
  return x0, x1, y0, y1
end

-- A dungeon's map: its floors, bosses and ways out, fitted in the view. Of wing `wing` (its icon's):
-- that wing fitted, its bosses and usual way.
function G.ShowInstance(lvl, wing)
  local x0, x1, y0, y1 = G.InstanceBounds(lvl)
  if not x0 then return end
  local wx0, wx1, wy0, wy1 = G.WingBounds(lvl, wing)
  if wx0 then
    wx0, wx1, wy0, wy1 = math.max(x0, wx0), math.min(x1, wx1), math.max(y0, wy0), math.min(y1, wy1)
    if wx0 < wx1 and wy0 < wy1 then x0, x1, y0, y1 = wx0, wx1, wy0, wy1 end
  end
  RememberView()
  browse, browseZoom, browseCont, browseBounds, fromTerrain = nil, nil, nil, nil, nil
  free = { x = (x0 + x1) / 2, y = (y0 + y1) / 2, rot = 0, cross = true, cont = lvl, instance = lvl, wing = wing }
  S().zoom = math.max(MIN_ZOOM, math.min(G.MaxZoom(), math.max(x1 - x0, y1 - y0) / 2 * 1.05))
  if recenter then recenter:Show() end
  elapsed = 1
end

-- Back out of a dungeon's map: the terrain view at entrance `e` ({ cont, x, y, ... }).
function G.ShowEntrance(e)
  openedFrom = nil
  browse, browseZoom, browseCont, browseBounds, fromTerrain = nil, nil, nil, nil, nil
  free = { x = e[2], y = e[3], rot = 0, cross = true, cont = e[1] }
  S().zoom = math.max(MIN_ZOOM, math.min(G.MaxZoom(), 400))
  if recenter then recenter:Show() end
  elapsed = 1
end

-- Right-click in a city's or dungeon's map opened from its icon: back to the view it was
-- opened from (a zone's map, the terrain view); in a dungeon's the player is in, out at its
-- (first) entrance.
LeaveOpened = function()
  local inst = view.instance or (free and free.instance)
  if not (inst or (free and (free.city or free.cave))) then return false end
  local from = openedFrom
  if from then
    openedFrom = nil
    browse, browseZoom, browseCont, browseBounds = nil, nil, nil, nil
    if from.browse and ns.Maps and ns.Maps[from.browse] then
      G.Browse(from.browse, from.browseCont) -- (its bounds; saved over a /reload without them)
      browseZoom = from.browseZoom or browseZoom
    end
    fromTerrain, free = from.fromTerrain, from.free
    if free and free.city and not free.interior then free.interior = G.CityInterior(free.city) end
    if from.zoom then S().zoom = from.zoom end
    if recenter then recenter:SetShown(free ~= nil) end
    elapsed = 1
    return true
  end
  if free and free.cave then -- (a cave's map with nothing to go back to: the land round it, where it is)
    free.cave = nil
    elapsed = 1
    return true
  end
  if not inst then -- (a city opened before a /reload: the continent's map, as usual)
    free.city = nil
    return false
  end
  local e = G.WingEntrance(inst, G.InstanceWing(inst)) -- (a wing's: its way in)
  if not e then return false end
  G.ShowEntrance(e)
  return true
end
-- A controller's Back in a dungeon's, cave's or city's map opened: as the right-click there, back out of it (asked
-- 2026-11-16: "the Back button does the same as a right click in that view so it goes back to the map first. another
-- Back press would close the map"). False when there's none to leave.
function G.LeaveOpenedView()
  if browse then return false end
  return LeaveOpened() and true or false
end

-- An inside map the player opened while browsing (a cave's, G.ShowCave; a city's or building's, Undercity's level,
-- G.ShowCity) ends by itself, in place, once they've looked well away from it (asked 2026-11-14: "if the user pans
-- far enough away OR zooms out enough the cave/city/building view should be exited automatically"): the view's
-- middle panned past its box by more than LEAVE_INSIDE_PAN_YD and the view's own reach (the map out of sight), or the
-- wheel out past LEAVE_INSIDE_ZOOM_TIMES the zoom its map gives way to the land at (G.CaveSeamZoom, CITY_MAX_ZOOM:
-- just past that the seamless map's land round it, issue #62, and back in its map again). Its name, floor bar and
-- floor line go with it, and zooming back in there is the land; right-click inside goes back as before
-- (LeaveOpened). Not the player's own inside map (never `free.interior`), nor a dungeon's map (its own yards).
G.LEAVE_INSIDE_PAN_YD = 200
G.LEAVE_INSIDE_ZOOM_TIMES = 2

-- the opened inside map: its box (x0, y0, x1, y1, continent yards) and the zoom it gives way to the land at, or nil
function G.OpenedInside()
  if not free or browse or free.instance then return nil end
  local x0, y0, x1, y1, limit
  local art = free.cave and G.CaveArt(free.cont, free.cave)
  local p = free.interior and free.interior[1]
  local m = free.city and ns.Maps and ns.Maps[free.city]
  if art then
    x0, y0, x1, y1, limit = art.x0, art.y0, art.x1, art.y1, G.CaveSeamZoom(art)
  elseif p then
    x0, y0, x1, y1, limit = p[6], p[7], p[8], p[9], G.CITY_MAX_ZOOM
  elseif m and m.bounds then
    local b = m.bounds
    x0, y0, x1, y1, limit = math.min(b[1], b[3]), math.min(b[2], b[4]), math.max(b[1], b[3]), math.max(b[2], b[4]),
      G.CITY_MAX_ZOOM
  else
    return nil
  end
  return x0, y0, x1, y1, limit
end

-- whether the view's middle (x, y) at zoom `zoom` is far enough from box (x0, y0, x1, y1) to leave it
function G.InsidePannedAway(x, y, zoom, x0, y0, x1, y1)
  local dx, dy = math.max(x0 - x, 0, x - x1), math.max(y0 - y, 0, y - y1)
  return dx * dx + dy * dy > math.max(G.LEAVE_INSIDE_PAN_YD, zoom) ^ 2
end

-- the opened inside map left where the view is: free's middle, turn and zoom kept, its map and name gone, nothing to
-- go back to (openedFrom). True when there was one
function G.LeaveInsideInPlace()
  if not (free and (free.cave or free.city or free.interior)) then return false end
  free.cave, free.city, free.interior = nil, nil, nil
  openedFrom = nil
  elapsed = 1
  return true
end

-- the redraw's check (`zoom` its zoom): panned away from the opened inside map, it's left. With `wheeled` (G.WheelZoom
-- going out to `zoom`): zoomed out past it, too
function G.LeaveInsideIfAway(zoom, wheeled)
  if free and free.instance and not browse then return G.LeaveInstanceIfAway(zoom) end
  local x0, y0, x1, y1, limit = G.OpenedInside()
  if not x0 then return false end
  if (wheeled and zoom > limit * G.LEAVE_INSIDE_ZOOM_TIMES) or G.InsidePannedAway(free.x, free.y, zoom, x0, y0, x1, y1) then
    return G.LeaveInsideInPlace()
  end
  return false
end

-- A dungeon's map opened from its icon ends by itself too (asked 2026-11-15: "just like viewing a cave, panning too far
-- or zooming out closes the view"): its view's middle panned past its box (its wing's) by LEAVE_INSIDE_PAN_YD and the
-- view's reach, the land there in its continent's yards (G.InteriorArtSpot: dungeon yards moved by its way in's), zoom
-- and turn kept, nothing to go back to. No way in known: it stays (nowhere on the land to leave it). Zoomed out past its
-- extent, G.SeamOutOfInstance's land at its way in as before; past LEAVE_INSIDE_ZOOM_TIMES that, no way back in to it
-- (G.WheelZoom drops free.seamBack).
function G.LeaveInstanceIfAway(zoom)
  local inst = free and free.instance
  if not inst or browse or free.hidden then return false end -- (not the player's own, put up hidden)
  local x0, x1, y0, y1 = G.InstanceBounds(inst)
  local wx0, wx1, wy0, wy1 = G.WingBounds(inst, free.wing)
  if wx0 and x0 then
    wx0, wx1, wy0, wy1 = math.max(x0, wx0), math.min(x1, wx1), math.max(y0, wy0), math.min(y1, wy1)
    if wx0 < wx1 and wy0 < wy1 then x0, x1, y0, y1 = wx0, wx1, wy0, wy1 end
  end
  if not (x0 and G.InsidePannedAway(free.x, free.y, zoom, x0, y0, x1, y1)) then return false end
  local sp = G.InteriorArtSpot(inst, inst)
  if not sp then return false end
  free = { x = free.x + sp[2], y = free.y + sp[3], rot = free.rot or 0, cross = true, cont = sp[1], land = true }
  openedFrom = nil
  elapsed = 1
  return true
end

-- "Route Here": destination at the crosshair, then a short tour: hold 3 s, ease out to
-- show the whole route, hold 4 s, ease back in on the player and follow. Dragging the
-- map, the mouse wheel or recentering cancel it; the player moving does not.
local ROUTE_TOUR = { hold = 3, out = 1.5, show = 4, back = 1.5 }

local function Ease(t) return t < 0.5 and 2 * t * t or 1 - (-2 * t + 2) ^ 2 / 2 end

function G.CancelTour() tour = nil end

-- The view that fits the player and the destination (with the route between them).
local function Overview(px, py, cont)
  local r = ns.Nav.Route(px, py, cont) -- make sure the route exists before framing it
  local minX, maxX, minY, maxY = px, px, py, py
  if r then
    ns.Nav.EachSegment(r, cont, function(x1, y1, x2, y2)
      minX, maxX = math.min(minX, x1, x2), math.max(maxX, x1, x2)
      minY, maxY = math.min(minY, y1, y2), math.max(maxY, y1, y2)
    end)
  end
  -- every stop routed too: the legs between stops are worked out over the next frames,
  -- so right after a route is made only the first ones are drawn yet
  for i = 1, ns.Nav.PlannedStops() do
    local d = ns.Nav.stops[i]
    local x, y
    if d then x, y = Geo.ToContinent(d.cont, d.x, d.y, cont) end -- (not `d and ...`: keeps one value)
    if x and y then
      minX, maxX = math.min(minX, x), math.max(maxX, x)
      minY, maxY = math.min(minY, y), math.max(maxY, y)
    end
  end
  local half = math.max(maxX - minX, maxY - minY) / 2
  return (minX + maxX) / 2, (minY + maxY) / 2, math.max(MIN_ZOOM, half * 1.35) -- margin for rotation
end

-- Whether the route goes to another continent than the player's (a boat or a zeppelin over),
-- its stops or its way (a stop on this continent reached through the other one: from Tirisfal to
-- Riverglades by the zeppelins through Durotar): its overview is the world map's, not the
-- continent's (whose art stops at its coasts).
function G.TourAcrossContinents(cont)
  local here = Geo.Base(cont)
  local function other(c)
    return c and Geo.Base(c) ~= here and not (ns.CityLevels and ns.CityLevels[c] and ns.CityLevels[c].instance)
  end
  for i = 1, #ns.Nav.stops do
    local d = ns.Nav.stops[i]
    if d and other(d.cont) then return true end
  end
  local r = ns.Nav.route
  for _, part in ipairs(r and r.parts or {}) do
    if other(part.cont) then return true end
  end
  return false
end

-- How far the route tour zooms out for an overview `z` yards wide: on the terrain view no further
-- than its tiles go (MINIMAP_MAX_ZOOM; past that the zone maps' art showed instead, the map
-- switching halfway through the zoom); a map browsed or the map style, all of it.
-- The seamless map (asked 2026-11-09: a route to another continent left it) zooms on its own art out to the whole
-- world: all of the route, up to G.MaxZoom.
function G.TourZoom(z)
  if not browse and G.Seamless() then return math.min(z, G.MaxZoom()) end
  if not browse and not G.IsMapStyle(G.Style()) then return math.min(z, G.MinimapMaxZoom() - 1) end
  return z
end

-- Whether the tour shows the world map for a route to another continent: not on the seamless map, whose own
-- zoom has both ends on its art (Overview frames the other continent's stops in this one's yards).
function G.TourWorldMap(cont)
  return not G.Seamless() and G.TourAcrossContinents(cont) and WorldMapID() ~= nil
end

-- The tour's view middle in continent `cont`'s yards: the seamless map's view, gone over to the other continent
-- (G.SeamRebase), is in that one's.
function G.TourCenter(cont)
  if free.cont and Geo.Base(free.cont) ~= Geo.Base(cont) then
    local x, y = Geo.ToContinent(free.cont, free.x, free.y, cont)
    if x and y then return x, y end
  end
  return free.x, free.y
end

local function TourStep(now)
  if not tour then return end
  local px, py, cont = Geo.PlayerWorld()
  if not px or not ns.Nav.dest then tour = nil return end
  local dt = now - tour.t0
  if tour.phase == "world" then -- (the world map shown: then back to the player, in their view)
    if dt >= ROUTE_TOUR.show then G.Follow() end
    return
  end
  if tour.phase == "hold" and dt >= ROUTE_TOUR.hold and G.TourWorldMap(cont) then
    -- to another continent: the world map, both ends on it (G.Follow returns to the terrain
    -- view or the zone's map, whichever the player had)
    G.Browse(WorldMapID(), ViewCont(cont))
    tour = { phase = "world", t0 = now }
    elapsed = 1
    return
  end
  if tour.phase == "hold" and dt >= ROUTE_TOUR.hold then
    local x, y, z = Overview(px, py, cont)
    z = G.TourZoom(z)
    local fx, fy = G.TourCenter(cont)
    tour = { phase = "out", t0 = now, from = { fx, fy, browseZoom or S().zoom }, to = { x, y, z } }
  elseif tour.phase == "out" or tour.phase == "back" then
    local dur = ROUTE_TOUR[tour.phase]
    local k = Ease(math.min(1, dt / dur))
    local to = tour.to
    if tour.phase == "back" then to = { px, py, S().zoom } end -- the player may be moving
    local f = tour.from
    free.x = f[1] + (to[1] - f[1]) * k
    free.y = f[2] + (to[2] - f[2]) * k
    free.cont = nil -- (the player's continent's yards: the seamless map goes over to the other one itself, G.SeamRebase)
    browseZoom = math.exp(math.log(f[3]) + (math.log(to[3]) - math.log(f[3])) * k) -- even zoom speed
    elapsed = 1
    if dt >= dur then
      if tour.phase == "out" then
        tour = { phase = "show", t0 = now }
      else
        tour = nil
        G.Follow()
      end
    end
  elseif tour.phase == "show" and dt >= ROUTE_TOUR.show then
    local fx, fy = G.TourCenter(cont)
    tour = { phase = "back", t0 = now, from = { fx, fy, browseZoom or S().zoom } }
  end
end

-- After setting the route: the tour. `skipHold` starts zooming out right away.
local function StartTour(px, py, cont, viewCont, skipHold)
  local dest = ns.Nav.dest
  if not dest then return end
  dest.watchX, dest.watchY = px, py -- moving ends the tour and follows the player
  browse, browseCont, browseBounds = nil, nil, nil
  pending = {}
  if viewCont == cont then
    free = { x = free.x, y = free.y, rot = free.rot } -- no crosshair once routed
  else
    -- The view is in the other continent's coordinates: go straight to the overview.
    free = { x = px, y = py, rot = 0 }
    skipHold = true
  end
  tour = { phase = "hold", t0 = GetTime() - (skipHold and ROUTE_TOUR.hold or 0) }
  elapsed = 1
end

-- Route to the crosshair (single stop).
function G.RouteHere()
  local px, py, cont = Geo.PlayerWorld()
  if not px or not free then return end
  if ns.Nav.DungeonLocked() then ns.Nav.SayLocked() return end
  local viewCont = ViewCont(cont)
  if ns.Nav.SetDestination(free.x, free.y, viewCont) == false then return end -- (asked first: a zone too high)
  StartTour(px, py, cont, viewCont, false)
end

-- "Confirm Route": the double-clicked stops (in the fastest order if that option is on),
-- or the crosshair when none were placed.
function G.ConfirmRoute()
  if #pending == 0 then return G.RouteHere() end
  local px, py, cont = Geo.PlayerWorld()
  if not px or not free then return end
  local viewCont = ViewCont(cont)
  -- new stops go after the route's existing ones (clear the route first to start over)
  local stops = {}
  for _, d in ipairs(ns.Nav.stops) do stops[#stops + 1] = d end
  for _, d in ipairs(pending) do stops[#stops + 1] = d end
  -- (a route kept in its listed order, an import's: the new stops after it, Nav.keepOrder)
  local keep = ns.Nav.keepOrder and #ns.Nav.stops > 0
  local _, asked = ns.Nav.SetStops(stops, S().fastestOrder and not keep, nil, keep)
  if asked then -- (a zone too high: "route there anyway?" has them now)
    pending = {}
    elapsed = 1
    return
  end
  StartTour(px, py, cont, viewCont, true)
end

-- A stop at world (x, y) in the viewed continent, named `name` in the directions (a point
-- of interest's): appended to the route when one is set, else placed for Confirm Route
-- (or the 5 s auto-confirm). Stops following the player while placing. False at the limit.
---------------------------------------------------------------------------
-- Search (the magnifier button above the map button)
---------------------------------------------------------------------------

-- Places to search: flight masters, points of interest, place names, zones and docks from
-- the addon's data. NPCs: every friendly one shipped (Data/Npcs.lua), and those talked to (Layers.KnownNpcs).
local searchIndex
local function SearchIndex()
  -- (built for the character's faction: the other's docks left out; made again once it's known)
  local fac = ns.Nav.Faction and ns.Nav.Faction() or false
  local namesVer = ns.names and ns.names.taxiVer or 0 -- (and again when the game named the flight masters)
  if searchIndex and G.searchFaction == fac and G.searchNamesVer == namesVer then return searchIndex end
  G.searchFaction, G.searchNamesVer = fac, namesVer
  local list, seen = {}, {}
  -- (`name` in the game's language, `en` the data's English: found by either, ns.PoiName and the like)
  local function add(name, sub, cont, x, y, generic, en)
    if not name or name == "" or not cont then return end
    local key = name:lower() .. ":" .. cont .. ":" .. math.floor(x / 200) .. ":" .. math.floor(y / 200)
    if seen[key] then return end
    seen[key] = true
    -- (what it is, for the search's generic words: "flight master", "boat dock"; not a place's or a zone's)
    local kind = generic and sub:lower() or nil
    list[#list + 1] = { name = name, lower = G.SearchLower(name), sub = sub, cont = cont, x = x, y = y, kind = kind,
      en = en and en ~= name and G.SearchLower(en) or nil }
  end
  for cont, pois in pairs(ns.Pois or {}) do
    for _, p in ipairs(pois) do
      add(ns.PoiName(p), p[1] == 1 and L["Flight master"] or p[1] == 2 and L["Point of interest"] or L["Place"], cont,
        p[2], p[3], p[1] == 1, p[4])
    end
  end
  for id, m in pairs(ns.Maps or {}) do
    if m.type == 3 and m.bounds and m.continent and m.continent >= 0 then
      local b = m.bounds
      add(ns.ZoneName(id, m.name), L["Zone (its middle)"], m.continent, (b[1] + b[3]) / 2, (b[2] + b[4]) / 2, nil, m.name)
    end
  end
  for _, t in ipairs(ns.Transports or {}) do
    if t[8] == "portal" then -- (a dungeon's or raid's way in, Data/Instances.lua: its end on the continent)
      add(ns.RideEndName(t, 2), L["Instance entrance"], t[1], t[2], t[3], true, t[10])
    elseif ns.Nav.TransportUsable and not ns.Nav.TransportUsable(t) then
      -- (the other faction's: not offered, as on the map, in the routes and the options; asked 2026-10-08, "why does
      -- zeppelins show for alliance players?")
    else
      local what = t[8] == "teleporter" and L["Teleporter"] or t[8] == "boat" and L["boat dock"] -- (Darnassus's portal: no dock)
        or t[8] == "zeppelin" and L["zeppelin dock"] or t[8] == "tram" and L["tram dock"] or (t[8] .. " dock")
      add(ns.RideEndName(t, 1), what, t[1], t[2], t[3], true, t[9])
      add(ns.RideEndName(t, 2), what, t[4], t[5], t[6], true, t[10])
    end
  end
  searchIndex = list
  return list
end

-- Whether every word of `words` starts a word of `hay` (lower case): "inn ir" in "inn ironforge".
local function AllWordsStart(words, hay)
  for _, w in ipairs(words) do
    local found = false
    for h in hay:gmatch("[^%s%-%(%)',]+") do
      if h:sub(1, #w) == w then found = true break end
    end
    if not found then return false end
  end
  return true
end

-- What a city's or town's place is, for the search's generic words (asked 2026-10-30, the game's own list of a town's
-- trainers and services: "Class Trainer" without asking a guard first): "class trainer" (the player's class's, `class`
-- as UnitClass names it), "profession trainer", "flight master", "weapon trainer" (a capital's Weapon Master: "can't
-- seem to route to weapons trainer in Orgrimmar", 2026-11-05, nothing was found); nil for the rest (the name says it:
-- "Bank", "Rogue Trainer").
G.PROFESSIONS = { "Alchemy", "Blacksmithing", "Cooking", "Enchanting", "Engineering", "First Aid", "Fishing", "Herbalism",
  "Leatherworking", "Mining", "Skinning", "Tailoring" }
G.FLIGHT_MASTERS = { "Wind Rider Master", "Gryphon Master", "Hippogryph Master", "Bat Handler" }
function G.PlaceKind(name, class)
  local n = (name or ""):lower()
  local function ends(s)
    s = s:lower()
    return #n >= #s and n:sub(-#s) == s
  end
  if ends("weapon master") then return "weapon trainer" end
  if class and ends(class .. " trainer") then return "class trainer" end
  for _, p in ipairs(G.PROFESSIONS) do
    if ends(p .. " trainer") then return "profession trainer" end
  end
  for _, f in ipairs(G.FLIGHT_MASTERS) do
    if ends(f) then return "flight master" end
  end
  return nil
end

-- The search's lowercase: A-Z, and accented capitals (Latin-1's, "Ü") and
-- Cyrillic ones ("Наставник") are lowered here too (asked 2026-11-12: the search in the addon's language).
do
  local char = string.char
  local C3, D0, D1 = char(195), char(208), char(209)
  local LATIN = C3 .. "([" .. char(128) .. "-" .. char(158) .. "])" -- (À-Þ: UTF-8 C3 80-9E)
  local CYRILLIC = D0 .. "([" .. char(128) .. "-" .. char(175) .. "])" -- (Ѐ-Я: D0 80-AF)
  local function latin(c)
    local b = c:byte()
    if b == 151 then return nil end -- (the multiplication sign)
    return C3 .. char(b + 32)
  end
  local function cyrillic(c)
    local b = c:byte()
    if b < 144 then return D1 .. char(b + 16) end -- (Ѐ-Џ, Ё among them: D1 90-9F)
    if b < 160 then return D0 .. char(b + 32) end -- (А-П: D0 B0-BF)
    return D1 .. char(b - 32) -- (Р-Я: D1 80-8F)
  end
  -- (A-Z by a table, never string.lower: in a C library set to a code page it lowers bytes over 127 too, which
  -- breaks UTF-8: Python's lupa on Windows turned "Ü" into two bytes that aren't a letter)
  local ASCII = {}
  for i = 65, 90 do ASCII[char(i)] = char(i + 32) end
  function G.SearchLower(s)
    s = (s or ""):gsub("[A-Z]", ASCII)
    s = s:gsub(LATIN, latin)
    s = s:gsub(CYRILLIC, cyrillic)
    return s
  end
end

-- The capitals' and towns' places' names in the addon's language (asked 2026-11-12: "I've set the add-on's language to
-- German, so I should be able to search for "Bergbau," but I'm still only able to search for "Mining.""): the shipped
-- names are English (Data/CityPlaces.lua), each ending in what the place is. G.PlaceName(name): the name in the
-- addon's language and what came before that ending ("Sen'jin Village"), or the name as it is.
function G.PlaceNames()
  if not G.placeNames then
    G.placeNames = {
      { "Alchemy Trainer", L["Alchemy Trainer"] }, { "Blacksmithing Trainer", L["Blacksmithing Trainer"] },
      { "Cooking Trainer", L["Cooking Trainer"] }, { "Enchanting Trainer", L["Enchanting Trainer"] },
      { "Engineering Trainer", L["Engineering Trainer"] }, { "First Aid Trainer", L["First Aid Trainer"] },
      { "Fishing Trainer", L["Fishing Trainer"] }, { "Herbalism Trainer", L["Herbalism Trainer"] },
      { "Leatherworking Trainer", L["Leatherworking Trainer"] }, { "Mining Trainer", L["Mining Trainer"] },
      { "Skinning Trainer", L["Skinning Trainer"] }, { "Tailoring Trainer", L["Tailoring Trainer"] },
      { "Druid Trainer", L["Druid Trainer"] }, { "Hunter Trainer", L["Hunter Trainer"] },
      { "Mage Trainer", L["Mage Trainer"] }, { "Paladin Trainer", L["Paladin Trainer"] },
      { "Priest Trainer", L["Priest Trainer"] }, { "Rogue Trainer", L["Rogue Trainer"] },
      { "Shaman Trainer", L["Shaman Trainer"] }, { "Warlock Trainer", L["Warlock Trainer"] },
      { "Warrior Trainer", L["Warrior Trainer"] }, { "Bank", L["Bank"] }, { "Inn", L["Inn"] },
      { "Stable Master", L["Stable Master"] }, { "Guild Master", L["Guild Master"] },
      { "Weapon Master", L["Weapon Master"] }, { "Gryphon Master", L["Gryphon Master"] },
      { "Wind Rider Master", L["Wind Rider Master"] }, { "Bat Handler", L["Bat Handler"] },
      { "Transmogrifier", L["Transmogrifier"] },
    }
  end
  return G.placeNames
end
function G.PlaceName(name)
  if not name then return name end
  for _, p in ipairs(G.PlaceNames()) do
    local en, shown = p[1], p[2]
    if #name >= #en and name:sub(-#en) == en and (#name == #en or name:sub(-#en - 1, -#en - 1) == " ") then
      if shown == en then return name end
      local before = name:sub(1, #name - #en):gsub("%s+$", "")
      return shown, before ~= "" and before or nil
    end
  end
  return name
end

-- The generic words in the game's language ("Klassenlehrer"), typed as well as the English.
function G.KindWord(kind)
  local words = G.kindWords
  if not words then
    words = { ["class trainer"] = L["class trainer"], ["profession trainer"] = L["profession trainer"],
      ["weapon trainer"] = L["weapon trainer"], ["flight master"] = L["flight master"], ["repair"] = L["repair"],
      ["repair vendor"] = L["repair vendor"], ["armorer"] = L["armorer"], ["vendor"] = L["vendor"],
      ["merchant"] = L["merchant"], ["innkeeper"] = L["innkeeper"], ["banker"] = L["banker"], ["bank"] = L["bank"],
      ["auctioneer"] = L["auctioneer"], ["auction house"] = L["auction house"],
      ["stable master"] = L["stable master"], ["quest giver"] = L["quest giver"], ["ammo"] = L["ammo"],
      ["ammunition"] = L["ammunition"], ["arrows"] = L["arrows"], ["bullets"] = L["bullets"] }
    G.kindWords = words
  end
  local w = words[kind]
  return w and G.SearchLower(w)
end

-- The generic words (asked 2026-11-14: "repair" and "vendor" too, the NPCs talked to of that kind): a city place's
-- (G.PlaceKind) or a learned NPC's, its title's ("Mining Trainer": G.PlaceKind's too) or its window's ("vendor", and
-- "repair" when it repairs: Layers.NoteMerchant). Typed, the common NPCs (met in several places) are found by it too.
-- Each one's other words: "repairs", "armorer", "merchant" (G.Singular takes the plurals).
-- The shipped NPCs (Data/Npcs.lua, 2026-11-14) by their services too: "innkeeper", "banker" ("bank"), "auctioneer"
-- ("auction house"), "stable master", "quest giver".
G.GENERIC_KINDS = { "class trainer", "profession trainer", "weapon trainer", "flight master", "repair", "vendor",
  "innkeeper", "banker", "auctioneer", "stable master", "quest giver", "ammo", "arrows", "bullets" }
G.KIND_OTHER_WORDS = { repair = { "repair vendor", "armorer" }, vendor = { "merchant" }, banker = { "bank" },
  auctioneer = { "auction house" }, ammo = { "ammunition" } }
-- Ammo vendors (asked 2026-11-14, Quick Find's Ammo): the data has no flag for what a vendor sells, so by its title's
-- words ("Bowyer", "Gun Merchant", "Fletcher", "Ammunition Vendor"): "arrows" a bow/arrow/fletch word's, "bullets" a
-- gun word's, "ammo"/"ammunition" both; "ammo" any of them. Each a word's start: "Gunsmith", "Bowyer".
-- ("ammo"/"ammunition" both only when the title names no weapon: Kaja, "Guns and Ammo Merchant", sells bullets
-- alone, asked 2026-11-15: "selecting arrows as a hunter on quick find sent me to Kaja, which only sells gun ammo")
G.AMMO_TITLE_WORDS = { { "bow", "arrows" }, { "arrow", "arrows" }, { "fletch", "arrows" }, { "gun", "bullets" } }
G.AMMO_ANY_WORDS = { "ammo", "ammun" }
-- The ammo kinds title `title` gives ({ "ammo", "arrows" }), or nil.
function G.AmmoKinds(title)
  if not title then return nil end
  local got, out, any = {}, nil, false
  for w in title:lower():gmatch("%a+") do
    for _, p in ipairs(G.AMMO_TITLE_WORDS) do
      if w:sub(1, #p[1]) == p[1] and not got[p[2]] then
        got[p[2]] = true
        out = out or { "ammo" }
        out[#out + 1] = p[2]
      end
    end
    for _, a in ipairs(G.AMMO_ANY_WORDS) do
      if w:sub(1, #a) == a then any = true end
    end
  end
  if any and not out then out = { "ammo", "arrows", "bullets" } end
  return out
end
-- What the vendors sell, for the search (asked 2026-11-15: "need to search for all vendors items for sell to do this
-- correctly ... "arrows" or "sharp arrow" should send me to the closest vendor that sells them"): made once, again when
-- the lists change (Layers.VendorItems, the shipped; a stock learned, Layers.NoteMerchantItems, which wins for its NPC).
-- Each seller by a key: a shipped NPC's id, else "r<id>" (one talked to the data doesn't have). { stock = { [key] =
-- { item ids } }, ammo = { [key] = { "ammo", "arrows" }, or false }, items = { { id, name, lowers } ... } shorter
-- names first, sellers = { [item id] = { keys } } }.
G.ITEM_NAMES_AGAIN, G.ITEM_NAMES_TRIES = 10, 6 -- (s between tries; tries in all: an item the game never names stays English)
function G.VendorIndex()
  local Lay = ns.Layers
  if not (Lay and Lay.VendorItems) then return nil end
  local items, sells = Lay.VendorItems()
  local db = ns.db and ns.db.npcs
  local c = G.vendorIndex
  -- (items' names in the game's language once it has them cached, ns.ItemName: made again, at most every
  -- ITEM_NAMES_AGAIN s, while some are still missing)
  local now = GetTime and GetTime() or 0
  local fresh = not (c and c.missing and c.missing > 0 and (c.tries or 0) < G.ITEM_NAMES_TRIES and now - c.at >= G.ITEM_NAMES_AGAIN)
  if c and c.from == items and c.db == db and c.ver == Lay.sellsVersion and fresh then return c end
  local stock, names, kinds = {}, {}, {}
  local missing = 0
  for npc, list in pairs(sells) do stock[npc] = list end
  for id, it in pairs(items) do
    local shown = ns.ItemName(id, it.name)
    if shown ~= it.name then
      names[id] = { shown, it.name } -- (found by either, shown in the game's language)
    else
      names[id] = { it.name }
      if ns.GameLocalized() then missing = missing + 1 end
    end
    kinds[id] = it.kind
  end
  for id, n in pairs(db or {}) do
    if type(n) == "table" and type(n.sells) == "table" and next(n.sells) and not n.imported then
      local s = Lay.ShippedFor and Lay.ShippedFor(id, n)
      local list = {}
      for item, it in pairs(n.sells) do
        list[#list + 1] = item
        names[item] = names[item] or {}
        local nm = type(it) == "table" and it.name
        if nm then table.insert(names[item], 1, nm) end -- (the client's own name first: shown)
        if type(it) == "table" and it.kind then kinds[item] = it.kind end
      end
      stock[s and s.id or ("r" .. id)] = list
    end
  end
  local sellers, ammo = {}, {}
  for key, list in pairs(stock) do
    local a, b = false, false
    for _, item in ipairs(list) do
      sellers[item] = sellers[item] or {}
      local l = sellers[item]
      l[#l + 1] = key
      if kinds[item] == "a" then a = true elseif kinds[item] == "b" then b = true end
    end
    ammo[key] = a and b and { "ammo", "arrows", "bullets" } or a and { "ammo", "arrows" } or b and { "ammo", "bullets" }
      or false
  end
  local list = {}
  for id, nm in pairs(names) do
    if sellers[id] and nm[1] then
      local lowers, seen = {}, {}
      for _, x in ipairs(nm) do
        local l = G.SearchLower(x)
        if not seen[l] then seen[l], lowers[#lowers + 1] = true, l end
      end
      list[#list + 1] = { id = id, name = nm[1], lowers = lowers }
    end
  end
  table.sort(list, function(a, b)
    if #a.name ~= #b.name then return #a.name < #b.name end
    return a.id < b.id
  end)
  c = { from = items, db = db, ver = Lay.sellsVersion, stock = stock, ammo = ammo, items = list, sellers = sellers,
    missing = missing, at = now, tries = c and c.from == items and (c.tries or 0) + 1 or 0 }
  G.vendorIndex = c
  return c
end
-- Seller `key`'s ammo kinds (G.VendorIndex's key): by what it sells when that's known, else by its title's words
-- (G.AmmoKinds; `vendor`: it sells at all). Nil when none.
function G.StockAmmoKinds(key, title, vendor)
  local idx = G.VendorIndex()
  local a = idx and key and idx.ammo[key]
  if a ~= nil then return a or nil end
  return vendor and G.AmmoKinds(title) or nil
end
-- The sellers of the item typed (`q` the whole text, lower case; `words` its words): an item's name starting with it,
-- or every word starting a word of it ("sharp ar", "ice cold milk"), ITEM_MIN letters or more. { [key] = the item's
-- name shown (the shortest of those matched) }, or nil when none.
G.ITEM_MIN = 3
function G.VendorItemsTyped(q, words)
  if #q < G.ITEM_MIN then return nil end
  local idx = G.VendorIndex()
  if not idx then return nil end
  local out
  for _, it in ipairs(idx.items) do
    local hit = false
    for _, l in ipairs(it.lowers) do
      if l:sub(1, #q) == q or (l:find(words[1], 1, true) and AllWordsStart(words, l)) then hit = true break end
    end
    if hit then
      out = out or {}
      for _, key in ipairs(idx.sellers[it.id]) do
        if not out[key] then out[key] = it.name end
      end
    end
  end
  return out
end
-- A shipped NPC's grey text, or one selling what was typed: "Sells Sharp Arrow, Orgrimmar", "Armorer, Brill".
function G.SearchSub(e)
  local place = e.shipped and G.NpcPlaceName(e.cont, e.x, e.y) or e.where
  local what = e.sells and Format(L["Sells %s"], e.sells) or e.title
  return (what and place) and (what .. ", " .. place) or what or place or L["NPC"]
end

-- The shipped NPCs as search entries (Layers.ShippedNpcs; asked 2026-11-14, "Ship all NPCs": every friendly NPC found
-- before talking to anyone), the player's faction's and the neutral ones only (an enemy-faction NPC never), each once
-- (its spawn nearest the player is picked when it's found: G.PlaceShippedNpc). Found by name, by title ("Armorer"),
-- and by the generic words: its services (npcflag), "class trainer" the player's class's, "profession trainer" and
-- "<profession> trainer" ("Journeyman Blacksmith": a blacksmithing trainer), "weapon trainer". Made once per faction
-- and class.
G.SERVICE_KINDS = { { "v", "vendor" }, { "r", "repair" }, { "f", "flight master" }, { "i", "innkeeper" },
  { "b", "banker" }, { "a", "auctioneer" }, { "s", "stable master" }, { "q", "quest giver" } }
function G.ShippedNpcEntries(class)
  local Lay = ns.Layers
  if not (Lay and Lay.ShippedNpcs) then return {} end
  local list = Lay.ShippedNpcs()
  local fac = ns.Nav.Faction and ns.Nav.Faction() or false
  local c = G.shippedSearch
  local vi = G.VendorIndex() -- (what they sell: their ammo kinds, made again when it changes)
  if c and c.list == list and c.fac == fac and c.class == class and c.vi == vi and c.names == ns.npcNamesVer then
    return c.entries
  end
  local profs = {}
  for _, p in ipairs(G.PROFESSIONS) do profs[p] = true end
  local out = {}
  for _, n in ipairs(list) do
    if n.side == "B" or not fac or n.side == fac then
      local kinds = {}
      local function add(k) if k then kinds[#kinds + 1] = k end end
      add(n.title and G.PlaceKind(n.title, class))
      local t = n.trainer
      if t and class and t == class then
        add("class trainer")
      elseif t and profs[t] then
        add("profession trainer")
        add(G.SearchLower(t .. " trainer"))
        local shown = G.PlaceName(t .. " Trainer") -- (in the addon's language: "Bergbaulehrer")
        if shown and shown ~= t .. " Trainer" then add(G.SearchLower(shown)) end
      elseif t == "Weapon" then
        add("weapon trainer")
      end
      for _, s in ipairs(G.SERVICE_KINDS) do
        if Lay.NpcOffers(n, s[1]) then add(s[2]) end
      end
      -- (ammo by what it sells, asked 2026-11-15: Trak'gen, General Goods, sells Sharp Arrow; by its title only where
      -- nothing is known of its stock)
      for _, k in ipairs(G.StockAmmoKinds(n.id, n.title, Lay.NpcOffers(n, "v")) or {}) do add(k) end
      -- (its name as the game showed it, in its language, ns.NpcName; found by the English too, `en`)
      -- (and the shipped one in the client's language for one never met, Data/NpcNames; its title so too: shown, and
      -- found by it as by the English)
      local shown = ns.NpcName(n.id, n.name)
      local title = ns.NpcTitle(n.id, n.title)
      if title and title ~= n.title then add(G.SearchLower(title)) end
      local e = { name = shown, lower = G.SearchLower(shown), en = shown ~= n.name and G.SearchLower(n.name) or nil,
        title = n.title, sub = title or L["NPC"], npc = true,
        shipped = n, id = n.id, kind = n.title and G.SearchLower(n.title) or nil, kinds = kinds }
      e.tex = ns.Pins and ns.Pins.NpcIcon and ns.Pins.NpcIcon(e) or nil -- (by the English title)
      e.title = title
      out[#out + 1] = e
    end
  end
  G.shippedSearch = { list = list, fac = fac, class = class, entries = out, vi = vi, names = ns.npcNamesVer }
  return out
end
-- Search entry `e` of a shipped NPC, found: at its spawn nearest the player (px, py on level `pc`), its floor the one
-- learned there (`learned`: its record in ns.db.npcs, talked to; Layers.LearnedZ), else the spawn's height.
function G.PlaceShippedNpc(e, px, py, pc, learned)
  local Lay = ns.Layers
  local lv, x, y, z = Lay.NearestSpawn(e.shipped, px, py, pc)
  e.cont, e.x, e.y = lv, x, y
  e.z = Lay.LearnedZ(learned, lv, x, y) or z
end
-- The search list's Pin button (asked 2026-11-14): search entry `e` (an NPC or a city place) pinned for good
-- (Pins.AddFromSearch), on its floor: where floors there are told by under or over a cave's ground (G.PinFloors'
-- `down`), by its height (Router.CaveDown). Says so when it's pinned there already. Returns the pin made, or nil.
function G.PinSearchEntry(e)
  local P = ns.Pins
  if not (P and e and e.x and e.cont) then return nil end
  local down
  local ok, floors = pcall(G.PinFloors, e.cont, e.x, e.y)
  for _, f in ipairs(ok and floors or {}) do
    if f.down ~= nil and e.z and ns.Router and ns.Router.CaveDown then
      down = ns.Router.CaveDown(e.cont, e.x, e.y, nil, e.z) and true or false
      break
    end
  end
  local p, have = P.AddFromSearch(e, down)
  if p then
    ns.Print(Format(L["pinned %s (double-click it for a stop, right-click to remove it)"], p.name))
  elseif have then
    ns.Print(Format(L["already pinned here: %s"], have.name or L["Pin"]))
  end
  return p, have
end
-- Whether `words` (typed, lower case) name `kind`: its English, its word in the game's language, or one of its others.
function G.KindTyped(words, kind)
  if not kind then return false end
  if G.KindMatch(words, kind) or G.KindMatch(words, G.KindWord(kind)) then return true end
  for _, o in ipairs(G.KIND_OTHER_WORDS[kind] or {}) do
    if G.KindMatch(words, o) or G.KindMatch(words, G.KindWord(o)) then return true end
  end
  return false
end
-- Whether a search entry is of the kind typed (`e.kind`, or any of `e.kinds`). `memo`: a table kept for one search's
-- `words` ({ [kind] = whether typed }): thousands of shipped NPCs share a few hundred kinds.
function G.MemoKindTyped(words, k, memo)
  if not k then return false end
  if not memo then return G.KindTyped(words, k) end
  local v = memo[k]
  if v == nil then
    v = G.KindTyped(words, k)
    memo[k] = v
  end
  return v
end
function G.EntryKindTyped(words, e, memo)
  if G.MemoKindTyped(words, e.kind, memo) then return true end
  local ks = e.kinds
  if ks then
    for j = 1, #ks do
      if G.MemoKindTyped(words, ks[j], memo) then return true end
    end
  end
  return false
end

-- A generic word typed: every word typed starts one of `kind`'s, the first a whole one ("class tr", "flight master";
-- "fl" isn't one, or two letters would list every flight master before the names with them). Singular or plural, as
-- typed: "weapons trainer", "flight masters" (G.Singular on both sides).
-- (and the first word begun, KIND_PREFIX_MIN letters or more: "rep", "vend", "inn"; asked 2026-11-14, "shouldn't need
-- the full word")
G.KIND_PREFIX_MIN = 3
function G.Singular(w) return (w:gsub("s$", "")) end
function G.KindMatch(words, kind)
  if not kind then return false end
  local first, ks, whole = G.Singular(words[1]), {}, false
  local begun = #words[1] >= G.KIND_PREFIX_MIN
  for k in kind:gmatch("%S+") do
    ks[#ks + 1] = G.Singular(k)
    if ks[#ks] == first or (begun and k:sub(1, #words[1]) == words[1]) then whole = true end
  end
  if not whole then return false end
  for _, w in ipairs(words) do
    local sw, found = G.Singular(w), false
    for _, k in ipairs(ks) do
      if k:sub(1, #sw) == sw then found = true break end
    end
    if not found then return false end
  end
  return true
end

-- Places matching `text` (any case, 2+ letters): names starting with it first, then what is of the kind typed
-- ("Class Trainer", "Flight master": G.KindMatch) nearest first, then names containing it, shorter first; the same
-- name nearer first ("Rogue Trainer": every city's), each with its yards from the player on their continent (`yd`).
-- Several words (asked 2026-10-03: "Inn Ir" for Ironforge's inn): every word starts a word of the name or its place,
-- those whose name starts with the first word first. At most `max` (default 8).
-- What and where typed together (asked 2026-11-14: "tailor tarren mill" found nothing; "consider any search like
-- this"): a place's name at the end or the start of what's typed ("repair undercity", "brill innkeeper") narrows the
-- rest's results to those there, by their place's or zone's name (a shipped NPC at its spawn there); those first,
-- then what the whole text finds. The place names: the map's town and place labels, its zones and cities.
G.SEARCH_PLACE_MIN = 3 -- letters: a place word typed shorter than this isn't taken as one
function G.SearchPlaceNames()
  local set = G.searchPlaceSet
  if set then return set end
  set = {}
  -- (each name in the game's language and the data's English, each the other's twin: [lower] = twin or true; a
  -- place typed in either finds what's named in either)
  local function both(shown, en)
    if not en then return end
    local a, b = G.SearchLower(shown or en), G.SearchLower(en)
    if a ~= b then
      set[a], set[b] = b, a
    elseif set[a] == nil then
      set[a] = true
    end
  end
  for _, list in pairs(ns.Pois or {}) do
    for _, p in ipairs(list) do
      if p[1] ~= 1 and p[4] then both(ns.PoiName(p), p[4]) end
    end
  end
  for id, m in pairs(ns.Maps or {}) do
    if m.name and (m.type == 3 or m.type == 4) then both(ns.ZoneName(id, m.name), m.name) end
  end
  for _, l in pairs(ns.CityLevels or {}) do
    if l.name then both(ns.ZoneName(l.map, l.name), l.name) end
  end
  G.searchPlaceSet = set
  return set
end
-- The place names `typed` stands for (each one a name starting with it), or nil.
function G.SearchPlacesTyped(typed)
  if #typed < G.SEARCH_PLACE_MIN then return nil end
  local out
  for name, twin in pairs(G.SearchPlaceNames()) do
    if name:sub(1, #typed) == typed then
      out = out or {}
      out[name] = true
      if twin ~= true then out[twin] = true end -- (its name in the other language too)
    end
  end
  return out
end
-- Whether search entry `e` is at one of `places` (a set of lower-case names): its place's name or its zone's; a
-- shipped NPC at any of its spawns, moved to that one.
function G.SearchEntryAt(e, places)
  local function named(level, x, y)
    local a = G.NpcPlaceName(level, x, y)
    if a and places[G.SearchLower(a)] then return true end
    local _, zone = G.LocateWorld(Geo.Base(level), x, y)
    return zone and places[G.SearchLower(zone)] or false
  end
  if e.shipped then
    local sp = e.shipped.spawns
    for i = 1, #sp - 3, 4 do
      if named(sp[i], sp[i + 1], sp[i + 2]) then
        e.cont, e.x, e.y, e.z = sp[i], sp[i + 1], sp[i + 2], sp[i + 3]
        return true
      end
    end
    return false
  end
  if not (e.cont and e.x) then return false end
  if e.sub then
    for name in pairs(places) do
      if G.SearchLower(e.sub):find(name, 1, true) then return true end
    end
  end
  return named(e.cont, e.x, e.y)
end
function G.SearchPlaces(text, max)
  max = max or 8
  local q = G.SearchLower(text):gsub("^%s+", ""):gsub("%s+$", ""):gsub("%s+", " ")
  local words = {}
  for w in q:gmatch("%S+") do words[#words + 1] = w end
  local out, seen = {}, {}
  -- (the whole text's own results first worked out, kept for after: each search sets the shared entries' spot and
  -- grey text, and the place's search after it sets them for its own)
  local plain = {}
  for _, e in ipairs(G.SearchPlacesPlain(text, max)) do plain[#plain + 1] = { e, e.cont, e.x, e.y, e.z, e.sub } end
  if #words > 1 then
    for k = #words - 1, 1, -1 do -- (the longest place first: "tarren mill", then "mill")
      for _, atEnd in ipairs({ true, false }) do
        local rest, where = {}, {}
        for j, w in ipairs(words) do
          local inPlace = atEnd and j > #words - k or (not atEnd and j <= k)
          if inPlace then where[#where + 1] = w else rest[#rest + 1] = w end
        end
        local places = #rest > 0 and G.SearchPlacesTyped(table.concat(where, " "))
        if places and #out == 0 then
          for _, e in ipairs(G.SearchPlacesPlain(table.concat(rest, " "), 400)) do
            if #out < max and G.SearchEntryAt(e, places) then
              out[#out + 1], seen[e] = e, true
              if e.shipped or e.sells then e.sub = G.SearchSub(e) end
            end
          end
        end
      end
    end
  end
  for _, p in ipairs(plain) do
    local e = p[1]
    if #out < max and not seen[e] then
      out[#out + 1] = e
      e.cont, e.x, e.y, e.z, e.sub = p[2], p[3], p[4], p[5], p[6]
    end
  end
  return out
end
function G.SearchPlacesPlain(text, max)
  local q = G.SearchLower(text):gsub("^%s+", ""):gsub("%s+$", ""):gsub("%s+", " ")
  if #q < 2 then return {} end
  local words = {}
  for w in q:gmatch("%S+") do words[#words + 1] = w end
  local starts, kinds, contains = {}, {}, {}
  local all = {}
  for _, e in ipairs(SearchIndex()) do all[#all + 1] = e end
  -- (the class's file name, "MAGE": the places' names are English; UnitClass's first value is in the client's language)
  local class
  if UnitClass then class = select(2, UnitClass("player")) end
  -- (the city places of their faction's capitals and towns, a guard talked to or not (asked 2026-10-30): "Inn" in white,
  -- "Ironforge" in grey, its icon; picked, a stop at it as a double-click on it)
  if ns.Layers and ns.Layers.KnownPlaces and ns.db then
    for _, p in ipairs(ns.Layers.KnownPlaces(true)) do
      -- (shown in the addon's language, found by the English too: `en`)
      local shown, before = G.PlaceName(p.name)
      local city = p.city or L["City location"]
      all[#all + 1] = { name = shown, lower = G.SearchLower(shown), sub = before and (before .. ", " .. city) or city,
        en = shown ~= p.name and G.SearchLower(p.name) or nil, cont = p.cont,
        x = p.x, y = p.y, z = p.z, tex = p.icon, place = p.full, kind = G.PlaceKind(p.name, class) }
    end
  end
  -- (the pins too, asked 2026-10-03: "Auction House" in white, "Stormwind City" in grey, the pin's icon; picked,
  -- a stop on the pin's level and floor, as double-clicking it. Each search: pins come and go)
  if ns.Pins and ns.db then
    for _, pin in ipairs(ns.Pins.All()) do
      if pin.name and pin.x and pin.level then
        all[#all + 1] = { name = pin.name, lower = G.SearchLower(pin.name), sub = ns.Pins.PlaceName(pin) or L["Pin"],
          cont = pin.level, x = pin.x, y = pin.y, z = pin.z, tex = ns.Pins.IconTexture(pin.icon), pin = true }
      end
    end
  end
  -- (NPCs the player has talked to, or imported, asked 2026-10-05: "Innkeeper Farley" in white, "Innkeeper, Goldshire"
  -- in grey; picked, a stop where the player stood talking to them. Never drawn on the map)
  -- A generic word typed ("repair", "class trainer"): the common ones too, found only by it (asked 2026-11-14; else
  -- only with the option searchCommonNpcs, as before).
  local generic = false
  for _, k in ipairs(G.GENERIC_KINDS) do
    if G.KindTyped(words, k) then generic = true break end
  end
  local commonToo = ns.settings and ns.settings.gps and ns.settings.gps.searchCommonNpcs
  -- (the shipped NPCs, every friendly one: Data/Npcs.lua, 2026-11-14. One talked to is the same NPC, listed once: the
  -- shipped entry, at the floor learned there, G.PlaceShippedNpc)
  local learnedFor = {} -- ([shipped id] = the record talked to of that NPC)
  if ns.Layers and ns.Layers.KnownNpcsWithIds and ns.db then
    local Lay = ns.Layers
    local known, ids = Lay.KnownNpcsWithIds(generic)
    for k, n in ipairs(known) do
      local s = Lay.ShippedFor and Lay.ShippedFor(ids[k], n)
      if s then
        learnedFor[s.id] = (ns.db.npcs and ids[k] and ns.db.npcs[ids[k]]) or n
      else
        local place = n.place
        if not place and G.LocateWorld then
          local _, z = G.LocateWorld(Geo.Base(n.cont), n.x, n.y)
          place = z
        end
        local sub = (n.title and place) and (n.title .. ", " .. place) or n.title or place or L["NPC"]
        if n.imported then sub = Format(L["%s (imported)"], sub) end
        -- (a common one with the option off: found only by a generic word)
        local only = n.common and not commonToo or nil
        local nk = { n.title and G.PlaceKind(n.title, class) or nil } -- ("Warrior Trainer": a class trainer)
        if Lay.NpcIsVendor and Lay.NpcIsVendor(n) then nk[#nk + 1] = "vendor" end
        if n.repair then nk[#nk + 1] = "repair" end
        for _, a in ipairs(G.StockAmmoKinds(ids[k] and ("r" .. ids[k]), n.title, true) or {}) do
          nk[#nk + 1] = a -- (by what it sells, else its title: a "Bowyer", "arrows")
        end
        local e = { name = n.name, lower = G.SearchLower(n.name), title = n.title, sub = sub, cont = n.cont, x = n.x,
          y = n.y, npc = true, id = tonumber(ids[k]), z = (ns.Nav.SpawnZ and ns.Nav.SpawnZ(n.cont, n.x, n.y)) or n.z, -- (its floor: its spot's
          -- shipped one, else learned where the player talked to it: the stop goes there)
          kind = not only and n.title and G.SearchLower(n.title) or nil, -- ("innkeeper": the nearest ones talked to)
          kinds = nk, kindOnly = only, vendor = Lay.NpcIsVendor and Lay.NpcIsVendor(n) or nil, repair = n.repair,
          seller = ids[k] and ("r" .. ids[k]), where = place }
        e.tex = ns.Pins and ns.Pins.NpcIcon and ns.Pins.NpcIcon(e) or nil
        all[#all + 1] = e
      end
    end
  end
  for _, e in ipairs(G.ShippedNpcEntries(class)) do all[#all + 1] = e end
  local px, py, pc = Geo.PlayerWorld()
  local base = pc and Geo.Base(pc)
  local memo = {} -- (the kinds typed, worked out once each: G.EntryKindTyped)
  -- (the vendors selling an item typed, asked 2026-11-15: "sharp arrow", nearest first, "Sells Sharp Arrow" in grey)
  local sold = not generic and G.VendorItemsTyped(q, words) or nil
  for _, e in ipairs(all) do
    local i = e.lower:find(q, 1, true)
    if not i and e.en then i = e.en:find(q, 1, true) end
    if e.shipped then e.sub = e.title or L["NPC"] end -- (its place, once shown: below)
    local sells = sold and sold[e.shipped and e.id or e.seller or false]
    e.sells = nil
    local into
    if e.kindOnly then
      if G.EntryKindTyped(words, e, memo) then
        into = kinds
      elseif sells then
        into, e.sells = kinds, sells
      end
    elseif e.npc and generic and G.EntryKindTyped(words, e, memo) then
      into = kinds -- (an NPC of the kind typed is listed by it, nearest first, even named so: "Innkeeper Renee")
    elseif i == 1 then
      into = starts
    elseif G.EntryKindTyped(words, e, memo) then
      into = kinds
    elseif sells then
      into, e.sells = kinds, sells
    elseif i then
      into = contains
    elseif #words > 1 and AllWordsStart(words, e.lower .. " " .. (e.en or "") .. " " .. G.SearchLower(e.sub)) then
      local first = e.lower:sub(1, #words[1]) == words[1] or (e.en and e.en:sub(1, #words[1]) == words[1])
      into = first and starts or contains
    end
    if into then
      into[#into + 1] = e
      -- (a shipped NPC found: at its spawn nearest the player, only now)
      if e.shipped then G.PlaceShippedNpc(e, px, py, pc, learnedFor[e.id] or (ns.db and ns.db.npcs and ns.db.npcs[e.id])) end
    end
    -- (the yards there in a straight line, on the player's continent; the index's entries are kept: set each time)
    e.yd = (into and px and e.cont and Geo.Base(e.cont) == base) and math.sqrt((e.x - px) ^ 2 + (e.y - py) ^ 2) or nil
  end
  local FAR = math.huge
  local function order(a, b)
    if #a.name ~= #b.name then return #a.name < #b.name end
    if a.name ~= b.name then return a.name < b.name end
    return (a.yd or FAR) < (b.yd or FAR)
  end
  local function nearest(a, b)
    if (a.yd or FAR) ~= (b.yd or FAR) then return (a.yd or FAR) < (b.yd or FAR) end
    return order(a, b)
  end
  table.sort(starts, order)
  table.sort(kinds, nearest)
  table.sort(contains, order)
  local out = {}
  for _, l in ipairs({ starts, kinds, contains }) do
    for _, e in ipairs(l) do
      if #out < (max or 8) then out[#out + 1] = e end
    end
  end
  -- (a shipped NPC shown: its title and where it is, "Armorer, Brill", as one talked to; "Sells Sharp Arrow, Orgrimmar")
  for _, e in ipairs(out) do
    if e.shipped or e.sells then e.sub = G.SearchSub(e) end
  end
  return out
end

-- Where a shipped NPC is, for the search's grey text: its city ("Undercity", down there; "Orgrimmar"), else the town
-- or place named nearest it on the map within NPC_PLACE_YD ("Brill"), else its zone. The game's names, untranslated.
G.NPC_PLACE_YD = 250
function G.NpcPlaceName(level, x, y)
  local lv = ns.CityLevels and ns.CityLevels[level]
  if lv and lv.name then
    if lv.instance then return ns.InstanceName(level) end -- (a dungeon's: by its map id)
    return ns.ZoneName(lv.map, lv.name)
  end
  local cont = Geo.Base(level)
  local city = G.CityMapAt and G.CityMapAt(cont, x, y)
  if city and ns.Maps and ns.Maps[city] then return ns.ZoneName(city, ns.Maps[city].name) end
  local best, bd = nil, G.NPC_PLACE_YD ^ 2
  for _, p in ipairs(ns.Pois and ns.Pois[cont] or {}) do
    if p[1] ~= 1 then -- (not a flight master's: "Undercity, Tirisfal")
      local d = (p[2] - x) ^ 2 + (p[3] - y) ^ 2
      if d < bd then best, bd = p, d end
    end
  end
  if best then return ns.PoiName(best) end
  if G.LocateWorld then
    local zid, z = G.LocateWorld(cont, x, y)
    return z and ns.ZoneName(zid, z)
  end
  return nil
end

---------------------------------------------------------------------------
-- Drawing a farming area (map menu): circle known herb/ore nodes, route a loop
---------------------------------------------------------------------------

local drawHint

-- `kind`: "farm" (a loop round nodes, the default) or "road" (a road to suggest).
-- While another addon holds the map (a game on it: API.HoldMap), no drawing tools: turning one on
-- says so and does nothing (false).
function G.ToolsRefused()
  if not G.Held() then return false end
  ns.Print(L["not during a game on the map"])
  return true
end

-- The walls drawn on the map (the option, or the wall tools on): not while another addon holds it
-- (its game's map stays clear; the option itself is left as it is).
function G.ShowsWalls()
  return (S().showWalls or G.wallMode) and not G.Held() and true or false
end

-- The Show Roads and Walls button: the road network and the walls on the map, or neither (either on:
-- both off).
function G.ToggleMapData()
  local on = not (S().showRoads or S().showWalls)
  S().showRoads, S().showWalls = on, on
  if G.RefreshQuick then G.RefreshQuick() end
  if ns.Options and ns.Options.Refresh then ns.Options.Refresh() end
  G.Redraw()
  return on
end

-- A hold starting: every drawing tool off (they come back only when turned on again).
function G.StopTools()
  if G.roadMode then G.SetRoadMode(false) end
  if G.wallMode then G.SetWallMode(false) end
  if G.drawMode or G.lasso then G.StopDrawing() end
end

function G.StartDrawing(kind)
  if G.ToolsRefused() then return false end
  if (kind or "farm") == "farm" and ns.Nav.DungeonLocked() then ns.Nav.SayLocked() return end
  G.drawMode, G.lasso, G.drawKind = true, nil, kind or "farm"
  if drawHint then
    drawHint:SetText(G.DrawHintText())
    drawHint:Show()
  end
  G.PadMarksRefresh()
  elapsed = 1
end

function G.StopDrawing()
  G.drawMode, G.lasso = false, nil
  if drawHint then
    if G.roadMode or G.wallMode then G.RoadHint() else drawHint:Hide() end
  end
  G.PadMarksRefresh()
  elapsed = 1
end

-- Drawing with a controller (asked 2026-11-16: "add controller support for drawing areas too like for drawing farming
-- area, when controller input is detected switch wording to those controls instead"): the area's corners marked one at
-- a time at the crosshair (the map's middle, which the pad pans and zooms), by Pad.lua's buttons: the stop's (A) marks
-- one (on the first corner again, with enough: done), Remove's (X) takes the last one off, the map menu's (Y) finishes,
-- Back (B) cancels. A lasso of `pad` corners: the pointer adds nothing to it. The hint names the pad's buttons while the
-- pad is in use (Pad.used), the mouse's otherwise.
G.PAD_CLOSE_UI = 14 -- the crosshair this near the first corner (UI units): A there closes the area
-- the corners an area needs: a farming loop 3, a road 2
function G.PadDrawMin() return (G.drawKind or "farm") == "farm" and 3 or 2 end
function G.DrawHintText()
  local P = ns.Pad
  if P and P.used and P.ActionLabel then
    local K = P.ActionLabel
    return Format((G.drawKind or "farm") == "farm"
      and L["Mark corners around the nodes to farm: %s adds one at the crosshair  ·  %s: undo  ·  %s: finish  |cff9d9d9d(%s cancels)|r"]
      or L["Mark points at the crosshair with %s  ·  %s: undo  ·  %s: finish  |cff9d9d9d(%s cancels)|r"],
      K("select"), K("remove"), K("menu"), K("back"))
  end
  return G.drawKind == "road" and L["Drag along the road  |cff9d9d9d(right-click cancels)|r"]
    or G.drawKind == "erase" and L["Drag over the road to take out  |cff9d9d9d(right-click cancels)|r"]
    or L["Drag around the nodes to farm  |cff9d9d9d(right-click cancels)|r"]
end
-- The hint as the input in use now (Pad.SawInput: the pad or the mouse).
function G.RefreshDrawHint()
  if drawHint and G.drawMode then
    drawHint:SetText(G.DrawHintText())
    drawHint:Show()
  end
end
-- The controller's legend and box (Pad.lua) as the drawing starts or ends: its drawing controls, or the map's.
function G.PadMarksRefresh()
  local P = ns.Pad
  if P and P.bound and P.ShowMarks then P.ShowMarks(true) end
end
-- A: a corner at the crosshair (the lasso begun with the first); on the first corner again with enough, the area done.
function G.PadDrawCorner()
  if not (G.drawMode and view.cont and view.x) then return false end
  local l = G.lasso
  if l and (not l.pad or l.cont ~= view.cont) then
    if l.pad then return false end -- (another map's in view: its corners stay where they were)
    l = nil -- (a mouse stroke left half done: the pad's own from here)
  end
  if not l then
    l = { pts = {}, cont = view.cont, road = G.drawKind == "road", pad = true }
    G.lasso = l
  end
  local x, y, pts = view.x, view.y, l.pts
  local n = #pts / 2
  if n >= G.PadDrawMin() and (G.drawKind or "farm") == "farm"
      and math.sqrt((x - pts[1]) ^ 2 + (y - pts[2]) ^ 2) * (view.s or 0) <= G.PAD_CLOSE_UI then
    return G.PadDrawFinish()
  end
  if n > 0 and pts[#pts - 1] == x and pts[#pts] == y then return true end -- (the same spot again: once)
  pts[#pts + 1], pts[#pts + 2] = x, y
  elapsed = 1
  return true
end
-- X: the last corner off (none left: the lasso gone, still drawing).
function G.PadDrawUndo()
  local l = G.lasso
  if not (G.drawMode and l and l.pad and #l.pts >= 2) then return false end
  l.pts[#l.pts] = nil
  l.pts[#l.pts] = nil
  if #l.pts == 0 then G.lasso = nil end
  elapsed = 1
  return true
end
-- Y (or A on the first corner): the area done, as the mouse let go; too few corners yet: said, still drawing.
function G.PadDrawFinish()
  local l = G.lasso
  if not (G.drawMode and l and l.pad and #l.pts / 2 >= G.PadDrawMin()) then
    ns.Print(L["Mark more corners first."])
    return false
  end
  G.FinishDrawing()
  return true
end

-- The road tools: on until toggled off. On the map, left-drag draws a road, right-drag
-- erases one (in red), middle-drag pans.
function G.RoadHint()
  local text
  if G.eraserMode then
    text = Format(L["|cffe080ffMagic eraser (%d yd): drag over your changes to put the map's own back|r  ·  |cff9d9d9dCtrl + wheel: size  ·  Middle-drag: pan|r"], G.EraserYd())
  elseif G.wallMode then
    text = L["|cffd02020Left-drag: draw a wall|r  ·  |cffb0b0b0Right-drag: erase walls (circle an area to erase them all)|r  ·  |cff9d9d9dMiddle-drag: pan|r"]
  elseif G.stairMode then
    text = G.stairMode.x and L["|cffffd100Stairs: now click their top|r  ·  |cff9d9d9dMiddle-drag: pan|r"]
      or L["|cffffd100Stairs: click their foot on the map|r  ·  |cff9d9d9dthe Stairs button again: done|r"]
  else
    text = L["Left-drag: draw a road  ·  |cffff4040Right-drag: erase (circle an area to erase it all)|r  ·  |cff9d9d9dMiddle-drag: pan|r"]
  end
  if S().toolShiftClick then text = text .. "\n" .. L["|cff9d9d9dShift-click drawing: hold Shift to draw or erase; a plain drag pans the map|r"] end
  -- (where floors lie over each other: which one the player is on, the one their edits change)
  G.floorLine = G.FloorText()
  drawHint:SetText(G.floorLine and text .. "\n" .. G.floorLine or text)
  drawHint:Show()
end
-- The hint's floor line kept up to date as the player moves (a redraw, every FLOOR_HINT_SECONDS).
G.FLOOR_HINT_SECONDS = 0.5
local floorHintAt = 0
function G.RefreshFloorHint()
  if not (drawHint and (G.roadMode or G.wallMode) and not G.drawMode) then return end
  local now = GetTime and GetTime() or 0
  if now - floorHintAt < G.FLOOR_HINT_SECONDS then return end
  floorHintAt = now
  G.PlaceDrawHint()
  if G.FloorText() ~= G.floorLine then G.RoadHint() end
end
-- The hint under the top panel (the directions, a quest area's objectives): at DRAW_HINT_Y, or lower when that panel
-- reaches further down (reported 2026-11-14: a quest's four lines hid the tools' hint).
G.DRAW_HINT_Y = -46
G.DRAW_HINT_GAP = 6
function G.PlaceDrawHint()
  if not drawHint then return end
  local top = drawHint:GetParent()
  local y = G.DRAW_HINT_Y
  if G.NavOnMap() and top then
    local tt, nb = top:GetTop(), navPanel:GetBottom()
    if type(tt) == "number" and type(nb) == "number" then y = math.min(y, math.floor(nb - tt - G.DRAW_HINT_GAP)) end
  end
  if y == G.drawHintY then return end
  G.drawHintY = y
  drawHint:ClearAllPoints()
  drawHint:SetPoint("TOPLEFT", top, "TOPLEFT", 14, y)
  drawHint:SetPoint("TOPRIGHT", top, "TOPRIGHT", -14, y)
end

-- The tools off: the edits made with them into the road network now (Record.Apply), once.
local function ToolsOff()
  if not G.roadMode and not G.wallMode and ns.Record and ns.Record.pending then ns.Record.Apply() end
  if not G.roadMode and not G.wallMode then G.editFloor, G.eraserMode = nil, nil end -- (the floor picked: all again next time)
end

function G.SetRoadMode(on)
  if on and G.ToolsRefused() then return false end
  if on then G.MapEditAuto(true) end
  G.roadMode = on and true or false
  if not G.roadMode then G.stairMode = nil end -- (the stairs tool goes with them)
  ToolsOff()
  if G.roadMode then G.wallMode = false end -- (one set of tools at a time)
  G.lasso, drag = nil, nil
  if G.drawMode then G.drawMode = false end
  if drawHint then
    if G.roadMode or G.wallMode then G.RoadHint() else drawHint:Hide() end
  end
  if G.RefreshQuick then G.RefreshQuick() end
  if not on then G.MapEditAuto(false) end
  elapsed = 1
end

-- The wall tools: like the road tools, for walls (what routes can't walk through): on the
-- map, left-drag draws one, right-drag erases them, middle-drag pans. On until toggled off.
function G.SetWallMode(on)
  if on and G.ToolsRefused() then return false end
  if on then G.MapEditAuto(true) end
  G.wallMode = on and true or false
  ToolsOff()
  if G.wallMode then G.roadMode, G.stairMode = false, nil end
  G.lasso, drag = nil, nil
  if G.drawMode then G.drawMode = false end
  if drawHint then
    if G.roadMode or G.wallMode then G.RoadHint() else drawHint:Hide() end
  end
  if G.RefreshQuick then G.RefreshQuick() end
  if not on then G.MapEditAuto(false) end
  elapsed = 1
end

-- A tool turned on another way than from the menu (a slash command, Options, the tutorial) opens Map Editing with it, and
-- closes it again when the tools are all off; a menu the player opened stays open (G.SetMapEditOpen).
function G.MapEditAuto(on)
  if not G.SetMapEditOpen then return end
  if on and not G.mapEditOpen then
    G.SetMapEditOpen(true)
    G.mapEditAuto = true
  elseif not on and G.mapEditAuto and not G.roadMode and not G.wallMode then
    G.SetMapEditOpen(false)
  end
end
-- The road and wall tools, and the roads and walls shown, off by themselves after TOOLS_IDLE seconds with the map on
-- screen and not used (no click, drag, pan, zoom or stroke on it; a Record walk counts as use), said in chat: drawing
-- the road network or the walls costs every redraw (asked 2026-11-13, for performance). Turning one on starts the
-- count over; time with the map hidden doesn't count (nothing's drawn then).
G.TOOLS_IDLE = 120
G.toolsIdle = 0
-- (asked 2026-11-14: "This map editing menu will stay open for 2 minutes (adjustable setting) without map activity before
-- it collapses back and turns off show road/walls": `mapEditIdle`, minutes, Options > Tools)
G.MAP_EDIT_IDLE_MIN, G.MAP_EDIT_IDLE_MAX = 1, 30
function G.ToolsIdleSeconds()
  local m = tonumber(S().mapEditIdle)
  if not m then return G.TOOLS_IDLE end
  return math.max(G.MAP_EDIT_IDLE_MIN, math.min(G.MAP_EDIT_IDLE_MAX, m)) * 60
end
function G.ToolsOn()
  local st = S()
  local on = {}
  if G.roadMode then on[#on + 1] = L["road tools"] end
  if G.wallMode then on[#on + 1] = L["wall tools"] end
  if st.showRoads then on[#on + 1] = L["roads shown"] end
  if st.showWalls then on[#on + 1] = L["walls shown"] end
  if G.mapEditOpen and #on == 0 then on[1] = L["Map Editing"] end
  return on
end
function G.NoteMapUse() G.toolsIdle = 0 end
-- Each frame the map is up: `busy` a drag or a stroke under way. True when it turned them off.
function G.ToolsIdleTick(dt, busy)
  if G.clone then return false end
  local on = G.ToolsOn()
  local onSig = table.concat(on, ",")
  if #on == 0 or busy or onSig ~= G.toolsSig or (ns.Record and ns.Record.rec) then
    G.toolsSig, G.toolsIdle = onSig, 0
    return false
  end
  G.toolsIdle = G.toolsIdle + (dt or 0)
  local limit = G.ToolsIdleSeconds()
  if G.toolsIdle < limit then return false end
  G.toolsIdle, G.toolsSig = 0, nil
  local st = S()
  if G.mapEditOpen and G.SetMapEditOpen then G.SetMapEditOpen(false) end -- (Map Editing closed: all of it below too)
  st.showRoads, st.showWalls = false, false
  if G.roadMode then G.SetRoadMode(false) end
  if G.wallMode then G.SetWallMode(false) end
  if G.RefreshQuick then G.RefreshQuick() end
  if ns.Options and ns.Options.Refresh then pcall(ns.Options.Refresh) end
  G.Redraw()
  ns.Print(Format(L["Turned off after %d min without use, to save performance: %s."], math.floor(limit / 60 + 0.5),
    table.concat(on, ", ")))
  return true
end

function G.ToggleWallMode()
  if G.SetWallMode(not G.wallMode) == false then return end
  ns.Print(G.wallMode and L["wall tools on: left-drag draws a wall, right-drag erases walls, middle-drag pans (toggle off when done)"]
    or L["wall tools off"])
end

function G.ToggleRoadMode()
  if G.SetRoadMode(not G.roadMode) == false then return end
  ns.Print(G.roadMode and L["road tools on: left-drag draws a road, right-drag erases one, middle-drag pans (toggle off when done)"]
    or L["road tools off"])
end

-- The magic eraser (asked 2026-11-14: "a 'magic eraser' that has a resizable circle area ... that can be used to
-- restore original road and wall data"): with the road or wall tools on, a circle at the pointer; dragged over the map,
-- the player's own changes of the tools on (roads or walls) under it are taken out (Record.Restore: a stroke running on
-- past it is cut at its edge), so the map's own data is back there. Ctrl + wheel sizes it, ERASER_MIN_YD to
-- ERASER_MAX_YD: large enough to sweep away a stroke drawn across zones by mistake. Undo puts back what it took.
G.ERASER_MIN_YD, G.ERASER_MAX_YD, G.ERASER_YD = 5, 4000, 40
G.ERASER_STEP = 1.25 -- (a wheel notch: this much larger or smaller)
G.ERASER_COLOR = { 0.88, 0.5, 1 }
function G.EraserYd()
  local r = tonumber(S().eraserYd) or G.ERASER_YD
  return math.max(G.ERASER_MIN_YD, math.min(G.ERASER_MAX_YD, r))
end
function G.SizeEraser(delta)
  local r = G.EraserYd() * (delta > 0 and G.ERASER_STEP or 1 / G.ERASER_STEP)
  S().eraserYd = math.floor(math.max(G.ERASER_MIN_YD, math.min(G.ERASER_MAX_YD, r)) + 0.5)
  if drawHint and (G.roadMode or G.wallMode) then G.RoadHint() end
  elapsed = 1
  return S().eraserYd
end
-- The tools on: "road", "wall", or nil (neither: said in chat unless `quiet`).
function G.ToolKind(quiet)
  if G.wallMode then return "wall" end
  if G.roadMode then return "road" end
  if not quiet then ns.Print(L["turn on the road tools or the wall tools first"]) end
  return nil
end
function G.SetEraserMode(on)
  if on and not G.ToolKind() then return false end
  G.eraserMode = on and true or nil
  if on then G.stairMode = nil end
  G.lasso = nil
  if drawHint and (G.roadMode or G.wallMode) then G.RoadHint() end
  if G.RefreshQuick then G.RefreshQuick() end
  elapsed = 1
end
function G.ToggleEraser()
  if G.SetEraserMode(not G.eraserMode) == false then return end
  ns.Print(G.eraserMode and Format(L["magic eraser on: drag over your changes to put the map's own roads or walls back there. Ctrl + wheel sizes it (%d yd)."], G.EraserYd())
    or L["magic eraser off"])
end
-- Whether (x, y) is within `r` yards of the stroke `pts` ({ x, y, ... }): a function of (x, y).
function G.NearStroke(pts, r)
  local r2, n = r * r, #pts / 2
  return function(x, y)
    for i = 1, n do
      local ax, ay = pts[2 * i - 1], pts[2 * i]
      local vx, vy = 0, 0
      if i < n then vx, vy = pts[2 * i + 1] - ax, pts[2 * i + 2] - ay end
      local l2 = vx * vx + vy * vy
      local t = l2 > 0 and math.max(0, math.min(1, ((x - ax) * vx + (y - ay) * vy) / l2)) or 0
      if (x - ax - vx * t) ^ 2 + (y - ay - vy * t) ^ 2 <= r2 then return true end
    end
    return false
  end
end
-- What a restore did, in chat.
function G.SayRestored(whole, cut)
  if ns.Record.practice then return end
  if whole + cut == 0 then
    ns.Print(L["nothing of yours to restore there"])
  else
    ns.Print(Format(L["restored the map's own data there: %d of your changes taken out, %d cut short. Undo puts them back."], whole, cut))
  end
end
-- An eraser stroke done (`l`: its lasso, the points the pointer went over).
function G.FinishEraser(l)
  local kind = G.ToolKind(true)
  if not (l and kind and #l.pts >= 2) then return end
  local r = l.r or G.EraserYd()
  local x1, y1, x2, y2 = math.huge, math.huge, -math.huge, -math.huge
  for i = 1, #l.pts - 1, 2 do
    x1, x2 = math.min(x1, l.pts[i]), math.max(x2, l.pts[i])
    y1, y2 = math.min(y1, l.pts[i + 1]), math.max(y2, l.pts[i + 1])
  end
  local whole, cut = ns.Record.Restore(kind, l.cont, G.NearStroke(l.pts, r), { x1 - r, y1 - r, x2 + r, y2 + r },
    math.max(1, r / 2))
  G.SayRestored(whole, cut)
  elapsed = 1
end
-- The eraser's circle at the pointer (the map's scale `s`: pixels a yard), while it's over the map.
G.ERASER_SIDES = 48
-- Filled (asked 2026-11-14: "magic eraser circle should cover the entirety of the circle not just drawing a line with
-- a circle cursor"): a round see-through disc under its ring, and its stroke as wide as it.
G.ERASER_FILL_ALPHA = 0.3
G.ERASER_BAND_MAX_PX = 4000
G.ERASER_DISC_TEX = G.ROUND_MASK -- (a white disc, see-through round it)
function G.DrawEraser(s)
  local disc = G.eraserDisc
  if not (G.eraserMode and (G.roadMode or G.wallMode) and canvas and canvas:IsMouseOver()) then
    if disc then disc:Hide() end
    return
  end
  local mx, my = GetCursorPosition()
  local sc = canvas:GetEffectiveScale()
  local ccx, ccy = canvas:GetCenter()
  local dx, dy = mx / sc - ccx, my / sc - ccy
  local rp = G.EraserYd() * s
  if not disc and lineLayer then
    disc = lineLayer:CreateTexture(nil, "ARTWORK")
    disc:SetTexture(G.ERASER_DISC_TEX)
    G.eraserDisc = disc
  end
  if disc then
    local c = G.ERASER_COLOR
    disc:SetVertexColor(c[1], c[2], c[3], G.ERASER_FILL_ALPHA)
    disc:ClearAllPoints()
    disc:SetPoint("CENTER", canvas, "CENTER", dx, dy)
    disc:SetSize(math.max(1, 2 * rp), math.max(1, 2 * rp))
    disc:Show()
  end
  local lx, ly
  for k = 0, G.ERASER_SIDES do
    local a = k / G.ERASER_SIDES * 2 * math.pi
    local px, py = dx + rp * math.cos(a), dy + rp * math.sin(a)
    if lx then AddSeg(lx, ly, px, py, G.ERASER_COLOR, 2, 0.9, true) end
    lx, ly = px, py
  end
end
-- Each frame with the eraser on: the map drawn again when the pointer moved over it (the circle follows it).
function G.EraserTick()
  if not (G.eraserMode and (G.roadMode or G.wallMode) and canvas) then return end
  local over = canvas:IsMouseOver()
  local mx, my = GetCursorPosition()
  local e = G.eraserAt
  if over ~= (e and e.over) or (over and e and (mx - e.x) ^ 2 + (my - e.y) ^ 2 >= 4) then
    G.eraserAt = { over = over, x = mx, y = my }
    elapsed = 1
  end
end

-- The name of continent `cont` (its own map's), for the questions below.
function G.ContinentName(cont)
  local base = Geo.Base(cont)
  for _, m in pairs(ns.Maps or {}) do
    if m.type == 2 and m.continent == base and m.name then return m.name end
  end
  return tostring(base)
end
-- Restore Zone (asked 2026-11-14: "restore a zone the crosshair is currently in based on the tool being used"): the
-- zone at the map's middle (the crosshair, or the player when following), asked first.
function G.RestoreZone()
  local kind = G.ToolKind()
  if not kind then return end
  local cont, x, y = view.cont, view.x, view.y
  local base = Geo.Base(cont)
  local zone = ns.Router.ZoneAt(base, x, y)
  local m = zone and zone ~= 0 and ns.Maps and ns.Maps[zone]
  if not m then
    ns.Print(L["no zone under the crosshair"])
    return
  end
  local n = ns.Record.CountEdits(kind, cont, zone)
  if n == 0 then
    ns.Print(L["nothing of yours to restore there"])
    return
  end
  local name = m.name or "?"
  G.Ask("AzerothGPSRestoreZone", Format(kind == "wall"
      and L["Put %s's walls back as the map has them? Your %d wall changes there are taken out (one running on past it is cut at its edge). Undo puts them back."]
      or L["Put %s's roads back as the map has them? Your %d road changes there are taken out (one running on past it is cut at its edge). Undo puts them back."], name, n),
    L["Restore"], L["Cancel"], function()
      local whole, cut = ns.Record.Restore(kind, cont, function(px, py) return ns.Router.ZoneAt(base, px, py) == zone end,
        nil, 8)
      G.SayRestored(whole, cut)
    end)
end
-- Restore Continent: all of the tools' changes on the continent in view, asked twice.
function G.RestoreContinent()
  local kind = G.ToolKind()
  if not kind then return end
  local cont = view.cont
  local n = ns.Record.CountEdits(kind, cont)
  if n == 0 then
    ns.Print(L["nothing of yours to restore there"])
    return
  end
  local name = G.ContinentName(cont)
  G.Ask("AzerothGPSRestoreContinent", Format(kind == "wall"
      and L["Put all of %s's walls back as the map has them? All %d of your wall changes there are taken out. Undo puts them back."]
      or L["Put all of %s's roads back as the map has them? All %d of your road changes there are taken out. Undo puts them back."], name, n),
    L["Restore"], L["Cancel"], function()
      G.Ask("AzerothGPSRestoreContinent2", Format(L["Are you sure? Every one of your %d changes on %s goes."], n, name),
        L["Restore All"], L["Cancel"], function()
          local whole, cut = ns.Record.Restore(kind, cont, function() return true end)
          G.SayRestored(whole, cut)
        end)
    end)
end

-- Shift-click drawing (asked 2026-11-14): with it on, the tools draw and erase only with Shift held (Shift + left-drag,
-- Shift + right-drag); a plain click or drag is the map's own (left-drag pans, as with the tools off). Whether a click
-- with `button` goes to the map, not the tools.
function G.ToolsPassClick(button)
  return S().toolShiftClick and button ~= "MiddleButton" and not (IsShiftKeyDown and IsShiftKeyDown()) or false
end
function G.ToggleShiftClick()
  S().toolShiftClick = not S().toolShiftClick -- (off kept as false: on is the default)
  if drawHint and (G.roadMode or G.wallMode) then G.RoadHint() end
  if G.RefreshQuick then G.RefreshQuick() end
  if ns.Options and ns.Options.Refresh then pcall(ns.Options.Refresh) end
  ns.Print(S().toolShiftClick and L["shift-click drawing on: Shift + left-drag draws, Shift + right-drag erases, a plain drag pans the map"]
    or L["shift-click drawing off"])
end

-- The area is drawn: a loop through the known nodes inside it (of this character's
-- gathering professions; all kinds if it has none).
function G.FinishDrawing()
  local lasso = G.lasso
  local kind = G.drawKind
  G.StopDrawing()
  if kind == "road" or kind == "erase" then return G.FinishRoad(lasso, kind == "erase") end
  if not lasso or #lasso.pts < 6 then return end
  -- the kinds shown on the map (map menu: Herbs, Ore): one, the other, or both
  local kinds = ns.Layers.VisibleKinds()
  if not kinds.herb and not kinds.ore then
    ns.Print(L["turn on Herbs or Ore in the map menu first: the farming area uses the nodes shown"])
    return
  end
  local nodes = ns.Layers.NodesInPolygon(lasso.cont, lasso.pts, kinds, ns.Layers.NodeFilter()) -- (those picked, if any)
  local px, py = Geo.PlayerWorld()
  if #nodes == 0 then
    ns.Print(kinds.herb and kinds.ore and L["no known herb or ore nodes in that area. Nodes show up once gathered, hovered on the minimap, right-clicked, or imported (+ button)."]
      or kinds.herb and L["no known herbs in that area. Nodes show up once gathered, hovered on the minimap, right-clicked, or imported (+ button)."]
      or L["no known ore nodes in that area. Nodes show up once gathered, hovered on the minimap, right-clicked, or imported (+ button)."])
    return
  elseif #nodes == 1 then
    ns.Nav.SetStops({ nodes[1] })
  else
    ns.Nav.SetLoop(nodes, px, py)
  end
  local n = #ns.Nav.stops
  if n == 1 then
    ns.Print(L["farming route: 1 node. Clear Route (or /agps clear) ends it."]) -- (one node: the only one there)
  else
    ns.Print(#nodes > n and Format(L["farming route: %d nodes, round and round. Clear Route (or /agps clear) ends it. (the nearest %d of %d)"], n, n, #nodes)
      or Format(L["farming route: %d nodes, round and round. Clear Route (or /agps clear) ends it."], n))
  end
  -- start it like Confirm Route: the tour over the route, then follow the player
  local _, _, cont = Geo.PlayerWorld()
  if px then
    if not free then free = { x = view.x, y = view.y, rot = view.rot, cont = view.cont } end
    StartTour(px, py, cont, ViewCont(cont), true)
  else
    G.Follow()
  end
end

-- A road drawn on the map: saved with the player's road fixes (Record.lua), so routes use
-- it at once (the stretches along an existing road are that road: Router.WithTracks); on
-- the city's own level when that's where the player is. `agps roads` takes it into the
-- road data. `erase`: a road that shouldn't be there, drawn over (a "remove" track).
-- Whether a stroke (flat points, `len` yards long) is a loop: long enough, and ending back
-- near where it started.
G.LOOP_CLOSE = 0.25 -- its ends at most this share of its length apart
function G.IsLoop(pts, len)
  local n = #pts
  if n < 8 or len < 30 then return false end
  local gap = math.sqrt((pts[n - 1] - pts[1]) ^ 2 + (pts[n] - pts[2]) ^ 2)
  return gap <= math.max(15, len * G.LOOP_CLOSE) and gap < len * 0.5
end

-- `wall`: a wall (what can't be walked through), not a road; with `erase`, walls taken out.
-- A stroke's heights, a point each (`raw`: the floor picked at each, false where none was), for `n` points: the gaps
-- filled from the nearest point before, else after; nil when no point had one.
function G.StrokeHeights(raw, n)
  if type(raw) ~= "table" then return nil end
  local out, last, any = {}, nil, false
  for i = 1, n do
    if raw[i] then last, any = raw[i], true end
    out[i] = last or false
  end
  if not any then return nil end
  for i = n, 1, -1 do
    if out[i] then last = out[i] else out[i] = last end
  end
  return out
end
-- Drawing a road by hand: Record suggested instead (asked 2026-10-09: "prompt user that wants to draw a road to
-- potentially use record instead"; the game gives no height, z is always 0: a walk recorded keeps the way walked,
-- indoors or not, the rooms' names and the stairs marked, from which the import tells each point's floor; a drawn road
-- is a line). Asked at a road stroke's start until answered: Record Instead opens Record's window; Draw Anyway, not again
-- until a real login (ns.db.recordHintSnoozed); "Don't ask again", never (the `recordHint` option, Options > Tools).
G.RECORD_HINT_TEXT = L["Record this road instead? Walk it with Record and AzerothGPS saves the exact way you went, when you're indoors, the rooms you pass and your stairs, so it lands on the right floors when it's imported. A drawn road is only a line."]
function G.RecordHintDue()
  if S().recordHint == false or (ns.db and ns.db.recordHintSnoozed) then return false end
  if not (ns.Record and ns.Record.ShowWindow) then return false end
  if ns.Record.practice then return false end -- (the tutorial's practice strokes)
  return not ns.Record.rec -- (recording already: no)
end
function G.AskRecordHint()
  return G.Ask("AzerothGPSRecordHint", G.RECORD_HINT_TEXT, L["Record Instead"], L["Draw Anyway"], function(checked)
    if checked then S().recordHint = false end
    if ns.Record and ns.Record.ShowWindow then ns.Record.ShowWindow() end
  end, function(clicked, checked)
    if checked then S().recordHint = false end
    if clicked and ns.db then ns.db.recordHintSnoozed = true end
  end, { check = L["Don't ask again"] })
end

function G.FinishRoad(line, erase, wall)
  if not line or #line.pts < 4 then return end
  local pts, len = {}, 0
  for i = 1, #line.pts - 1, 2 do
    local x, y = line.pts[i], line.pts[i + 1]
    local n = #pts
    if n >= 2 then len = len + math.sqrt((x - pts[n - 1]) ^ 2 + (y - pts[n]) ^ 2) end
    pts[n + 1], pts[n + 2] = math.floor(x * 10 + 0.5) / 10, math.floor(y * 10 + 0.5) / 10
  end
  if len < 8 then
    ns.Print(wall and L["that wall is too short (drag along it)"] or L["that road is too short (drag along it)"])
    return
  end
  -- (down in a city: on its level only when drawn over the city, not somewhere else looked at)
  -- (the level the map shows: an underground city's over its own map, only over the city)
  local level, shown = line.cont, G.shownLevel
  if shown and shown ~= line.cont and G.shownCont == line.cont and Geo.Base(shown) == line.cont
      and not (ns.Passability and ns.Passability.InGrid and not ns.Passability.InGrid(shown, pts[1], pts[2])) then
    level = shown
  end
  local mapID = C_Map.GetBestMapForUnit("player")
  local info = mapID and C_Map.GetMapInfo(mapID)
  -- an erase drawn as a loop (ending back near its start): the roads inside it go
  local area = erase and G.IsLoop(pts, len) or nil
  local op = wall and (erase and "unwall" or "wall") or (erase and "remove" or "add")
  -- (the floor it's on, where floors lie over each other: the player's height and indoors or not,
  -- when they're on that level; Router.WithTracks changes only that floor's roads)
  local z, indoors, down = G.EditFloor(level, pts)
  -- (a height per point where a floor was picked while drawing: G.StrokeHeights)
  local zs = not wall and G.StrokeHeights(line.zs, #pts / 2) or nil
  if zs then z = zs[1] end
  local i = ns.Record.Save({ op = op, drawn = true, continent = level,
    zone = info and info.name or "?", time = time(), pts = pts, area = area, z = z, indoors = indoors, down = down,
    zs = zs })
  if ns.Record.practice then -- (the tutorial's practice: Record.Save kept it in memory only)
    ns.Print(L["Practice: nothing was saved."])
    elapsed = 1
    return
  end
  if wall then
    if erase then
      ns.Print(Format(area and L["erased the walls inside that circle (#%d). /agps draw undo puts them back."]
        or L["erased the walls along that stroke (#%d). /agps draw undo puts them back."], i))
    else
      ns.Print(Format(L["saved your wall (#%d, %s): routes won't cross it now, roads included (leave a gap for a gate). /agps draw undo takes it back."],
        i, ns.Nav.FormatDistance(len)))
    end
    elapsed = 1
    return
  end
  if area then
    ns.Print(Format(L["erased the roads inside that circle (#%d): routes leave them out now. /agps draw undo puts them back."], i))
    elapsed = 1
    return
  end
  ns.Print(Format(erase and L["erased that road (#%d, %s): routes leave it out now. /agps draw undo puts it back."]
    or L["saved your road (#%d, %s): routes use it now (joined to the roads it meets). /agps draw undo takes it back."],
    i, ns.Nav.FormatDistance(len)))
  elapsed = 1
end

-- The stairs tool (asked 2026-10-06: "the ability to set stair locations and their start and end height"): with the
-- road tools on, a click on the map for the stairs' foot, another for their top, then their heights, picked from the
-- floors near each end (G.StairHeights) or typed (G.AskStairHeights). Saved as a drawn road that's stairs (`stair`,
-- a height each end, `zs`): Router.WithTracks makes it a stairs road (source 6) on those floors, as the data's own.
-- The button again, or the road tools off, ends it.
function G.SetStairMode(on)
  if on and not G.roadMode then G.SetRoadMode(true) end
  G.stairMode = (on and G.roadMode) and {} or nil -- ({ level, x, y }: the foot, once clicked)
  if G.stairMode then G.eraserMode = nil end
  if G.roadMode and G.RoadHint then G.RoadHint() end
  if G.RefreshQuick then G.RefreshQuick() end
end
-- A click on the map with the stairs tool, at (x, y) of `level`: the foot, then the top (and their heights asked).
-- Whether it was taken.
function G.StairClick(level, x, y)
  local sm = G.stairMode
  if not (sm and level and x) then return false end
  if not sm.x or sm.level ~= level then
    sm.level, sm.x, sm.y = level, x, y
    if G.RoadHint then G.RoadHint() end
    return true
  end
  G.stairMode = {} -- (ready for the next stairs)
  if G.RoadHint then G.RoadHint() end
  G.AskStairHeights(level, sm.x, sm.y, x, y)
  return true
end
-- The heights to pick from at (x, y) of `level`: the floors there the tools pick from (G.EditFloors), bottom up, or
-- the one road's height near when there's only one floor (none: nothing to offer, a height is typed).
function G.StairHeights(level, x, y)
  local hs = {}
  for _, f in ipairs(G.EditFloors(level, x, y)) do
    if f.z then hs[#hs + 1] = f.z end
  end
  if #hs == 0 then
    local R = ns.Router
    local near = R and R.HeightsNear and R.HeightsNear(level, x, y, G.FLOOR_PICK_YD)
    if near and near[1] then hs[1] = math.floor(near[1].z * 10 + 0.5) / 10 end
  end
  return hs
end
-- The stairs from (x1, y1) at height z1 to (x2, y2) at z2 on `level`, saved with the drawn roads: their number, or nil.
function G.SaveStairs(level, x1, y1, z1, x2, y2, z2)
  if not (level and x1 and y1 and x2 and y2 and tonumber(z1) and tonumber(z2)) then return nil end
  if (x2 - x1) ^ 2 + (y2 - y1) ^ 2 < 1 then
    ns.Print(L["those stairs are too short: click their foot, then their top"])
    return nil
  end
  local function r(v) return math.floor(tonumber(v) * 10 + 0.5) / 10 end
  local mapID = C_Map and C_Map.GetBestMapForUnit and C_Map.GetBestMapForUnit("player")
  local info = mapID and C_Map.GetMapInfo(mapID)
  local i = ns.Record.Save({ op = "add", stair = true, drawn = true, continent = level, zone = info and info.name or "?",
    time = time(), pts = { r(x1), r(y1), r(x2), r(y2) }, zs = { r(z1), r(z2) }, z = r(z1) })
  ns.Print(Format(L["saved your stairs (#%d, %.1f to %.1f): routes take them now. /agps draw undo takes them back."],
    i, r(z1), r(z2)))
  elapsed = 1
  return i
end
-- The heights asked: a row for the foot and one for the top, each the heights near that end as buttons and a box to
-- type one; Save Stairs saves them (G.SaveStairs).
function G.AskStairHeights(level, x1, y1, x2, y2)
  local f = G.stairWindow
  if not f then
    f = ns.Window("AzerothGPSStairs", 360, 190, L["Stairs"])
    local function Row(label, y)
      local t = f:CreateFontString(nil, "ARTWORK", "GameFontNormal")
      t:SetPoint("TOPLEFT", 14, f.top - y)
      t:SetText(label)
      local box = CreateFrame("EditBox", nil, f, "InputBoxTemplate")
      box:SetSize(60, 20)
      box:SetPoint("TOPLEFT", 60, f.top - y + 3)
      box:SetAutoFocus(false)
      box:SetMaxLetters(8)
      box:SetScript("OnEscapePressed", function() f:Hide() end)
      local row = { box = box, buttons = {} }
      for k = 1, 5 do
        local b = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
        b:SetSize(50, 20)
        b:SetPoint("TOPLEFT", 130 + (k - 1) * 44, f.top - y + 3)
        b:SetScript("OnClick", function(self) box:SetText(string.format("%.1f", self.height)) end)
        row.buttons[k] = b
      end
      return row
    end
    f.foot, f.topRow = Row(L["Foot"], 10), Row(L["Top"], 44)
    local note = f:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    note:SetPoint("TOPLEFT", 14, f.top - 78)
    note:SetPoint("RIGHT", -14, 0)
    note:SetJustifyH("LEFT")
    note:SetText(L["Pick each end's height (the floors near it), or type one."])
    f.note = note
    local save = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
    save:SetSize(110, 22)
    save:SetPoint("BOTTOMRIGHT", -12, 10)
    save:SetText(L["Save Stairs"])
    save:SetWidth(math.max(110, (save:GetTextWidth() or 0) + 24)) -- (a longer text in another language)
    save:SetScript("OnClick", function()
      local a, b = tonumber(f.foot.box:GetText()), tonumber(f.topRow.box:GetText())
      local s = f.stairs
      if not (a and b and s) then
        f.note:SetText(L["|cffff6060Give both ends a height.|r"])
        return
      end
      if G.SaveStairs(s.level, s.x1, s.y1, a, s.x2, s.y2, b) then f:Hide() end
    end)
    f.save = save
    local cancel = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
    cancel:SetSize(90, 22)
    cancel:SetPoint("RIGHT", save, "LEFT", -6, 0)
    cancel:SetText(L["Cancel"])
    cancel:SetScript("OnClick", function() f:Hide() end)
    G.stairWindow = f
  end
  f.stairs = { level = level, x1 = x1, y1 = y1, x2 = x2, y2 = y2 }
  local function fill(row, hs, pick)
    for k, b in ipairs(row.buttons) do
      local h = hs[k]
      b.height = h
      b:SetText(h and string.format("%.1f", h) or "")
      b:SetShown(h ~= nil)
    end
    row.box:SetText(pick and string.format("%.1f", pick) or "")
  end
  -- (picked first: the foot on the lowest floor near it, the top on the highest near it)
  local hf, ht = G.StairHeights(level, x1, y1), G.StairHeights(level, x2, y2)
  fill(f.foot, hf, hf[1])
  fill(f.topRow, ht, ht[#ht])
  f.note:SetText(L["Pick each end's height (the floors near it), or type one."])
  f:Show()
  return f
end

function G.AddStopAt(x, y, name, stopCont, tex, z, exact, questID)
  local px, py, cont = Geo.PlayerWorld()
  if not px then return false end
  if ns.Nav.DungeonLocked() then ns.Nav.SayLocked() return false end
  local max = ns.Nav.loop and ns.Nav.MAX_LOOP_STOPS or ns.Nav.MAX_STOPS
  if #ns.Nav.stops + #pending >= max then
    ns.Print(Format(L["at most %d stops per route"], max))
    return false
  end
  if not free then
    free = { x = view.x, y = view.y, rot = view.rot, cross = true, cont = view.cont }
    if recenter then recenter:Show() end
  end
  tour = nil
  local sc = stopCont or ViewCont(cont)
  -- (`exact`: on `stopCont` as given, a pin's level)
  if ns.Nav.StopLevel and not exact then sc = ns.Nav.StopLevel(sc, x, y) end -- down in a city: on its level
  -- a place picked on the map (its icon: a guard's city location...) on a city's floors is
  -- down there, wherever the player is
  if tex and not exact and ns.Layers and ns.Layers.CityLevelAt then sc = ns.Layers.CityLevelAt(Geo.Base(sc), x, y) or sc end
  -- (in a dungeon's or raid's map, a spot, a boss or a pin there: not a stop inside it (a route there kept
  -- "Working out the route..." going), its entrance's icon on the continent instead; asked 2026-10-01)
  local inst = G.InstanceOf(sc)
  if inst then
    local e = G.InstanceStopEntrance(inst, x, y, cont, px, py)
    if not e then
      ns.Print(Format(L["%s: no way in known to route to"], ns.InstanceName(inst) or L["that dungeon"]))
      return false
    end
    x, y, name, tex, z = e.x, e.y, e.name, INSTANCE_ICON, nil
    sc = ns.Nav.StopLevel and ns.Nav.StopLevel(e.cont, x, y) or e.cont
  end
  -- (a dungeon reached through a cave of its own, from outside it: the cave's way in, G.ENTRANCE_VIA)
  local via = G.ApproachEntrance(sc, x, y, cont, px, py)
  if via then
    x, y, name, z = via.x, via.y, via.name, nil
    sc = ns.Nav.StopLevel and ns.Nav.StopLevel(via.cont, x, y) or via.cont
  end
  -- (`z`: its height, the game's, when known: a city place's, its floor where floors lie over each other)
  local stop = { x = x, y = y, cont = sc, name = name, icon = ns.Nav.NextMarker(ns.Nav.stops, pending), tex = tex, z = z }
  -- (a quest's icon: the stop carries its quest, done by it and not by getting there; Nav.QuestStop)
  if questID and ns.Nav.QuestStop then ns.Nav.QuestStop(stop, questID) end
  if #ns.Nav.stops > 0 then
    ns.Nav.AddStop(stop, S().fastestOrder) -- a route is set: straight onto it
    G.appended = true -- after AUTO_CONFIRM seconds of quiet: the tour, then follow again
  else
    pending[#pending + 1] = stop
  end
  lastActivity = GetTime()
  elapsed = 1
  return true
end

-- Double-click on the map: a stop at that spot (up to Nav.MAX_STOPS, one marker each).
function G.AddPending(dxUI, dyUI)
  if G.Held() then -- (held by another addon: its double-click)
    local x, y = G.ScreenToWorld(view.x, view.y, dxUI, dyUI, view.rot, view.s)
    return HeldClick(x, y, view.cont)
  end
  -- (in a dungeon that hides the player's position, its own map: they mark where they are, G.MarkYouHere)
  if hiddenShown and view.instance == hiddenShown then
    local x, y = G.ScreenToWorld(view.x, view.y, dxUI, dyUI, view.rot, view.s)
    return G.MarkYouHere(hiddenShown, x, y)
  end
  G.AddStopAt(G.ScreenToWorld(view.x, view.y, dxUI, dyUI, view.rot, view.s))
end

-- Right-click on a stop's marker: a small "Remove?" button next to it.
local removeAsk
function G.AskRemove(pin)
  if not removeAsk then
    removeAsk = CreateFrame("Button", nil, keepLayer, "UIPanelButtonTemplate")
    G.removeAsk = removeAsk -- (Pad.lua: A presses it, B lets it go)
    removeAsk:SetSize(76, 20)
    removeAsk:SetText(L["Remove?"])
    removeAsk:SetWidth(math.max(76, (removeAsk:GetTextWidth() or 0) + 20)) -- (a longer word in another language)
    removeAsk:SetFrameLevel(keepLayer:GetFrameLevel() + 6)
    removeAsk:SetScript("OnClick", function(self)
      self:Hide()
      if self.learnNode then -- (a detour: skipped for this route)
        ns.Nav.SkipLearn(self.learnNode)
        G.Redraw() -- (the flight master's own map icon comes back: the kept icons placed again)
      elseif self.ride then -- (a ride, or a flight's connection: not taken on this route)
        ns.Nav.SkipRide(self.ride, self.hop, self.rideName)
        G.Redraw()
      elseif self.customPin then -- (a pin: gone)
        ns.Pins.Remove(self.customPin)
        G.Redraw()
      elseif self.pendingIndex then
        G.RemovePending(self.pendingIndex)
      elseif self.stopIndex then
        ns.Nav.RemoveStop(self.stopIndex)
        G.Redraw()
      end
    end)
    removeAsk:SetScript("OnUpdate", function(self)
      if GetTime() - self.shownAt > 5 then self:Hide() end -- not taken up: go away
    end)
  end
  removeAsk.pendingIndex, removeAsk.stopIndex, removeAsk.learnNode = pin.pendingIndex, pin.stopIndex, pin.learnNode
  removeAsk.ride, removeAsk.hop, removeAsk.customPin = pin.ride, pin.hop, pin.pin
  removeAsk.rideName = pin.ride and pin.title or nil
  removeAsk.shownAt = GetTime()
  removeAsk:ClearAllPoints()
  removeAsk:SetPoint("BOTTOM", pin, "TOP", 0, 2)
  removeAsk:Show()
  GameTooltip_Hide()
end

-- Shift + left-click on the map (pinning on: Options > Tools): "Create Pin" there, a small button like
-- "Remove?", then the pin's dialog (Pins.lua). A drag (moving the window) isn't one; not on the world
-- map, nor while another addon holds the map.
G.PIN_CLICK_PX = 6 -- cursor pixels: moved further, a drag
local createAsk
function G.PinClickDown()
  G.pinClick = nil
  if createAsk then createAsk:Hide() end
  if S().pinning == false or G.Held() or not (IsShiftKeyDown and IsShiftKeyDown()) then return false end
  local m = browse and ns.Maps[browse]
  if m and m.type <= 2 then return false end
  local mx, my = GetCursorPosition()
  G.pinClick = { mx, my }
  return true
end
function G.PinClickUp()
  local c = G.pinClick
  G.pinClick = nil
  if not c then return false end
  local mx, my = GetCursorPosition()
  if (mx - c[1]) ^ 2 + (my - c[2]) ^ 2 > G.PIN_CLICK_PX ^ 2 then return false end
  local sc = canvas:GetEffectiveScale()
  local ccx, ccy = canvas:GetCenter()
  return G.AskCreatePin(mx / sc - ccx, my / sc - ccy)
end
function G.AskCreatePin(dxUI, dyUI)
  local x, y = G.ScreenToWorld(view.x, view.y, dxUI, dyUI, view.rot, view.s)
  local level = x and G.PinLevel(x, y)
  if not level then return false end
  if removeAsk then removeAsk:Hide() end
  if not createAsk then
    createAsk = CreateFrame("Button", nil, keepLayer, "UIPanelButtonTemplate")
    createAsk:SetSize(90, 20)
    createAsk:SetText(L["Create Pin"])
    createAsk:SetWidth(math.max(90, (createAsk:GetTextWidth() or 0) + 20))
    createAsk:SetFrameLevel(keepLayer:GetFrameLevel() + 6)
    createAsk:SetScript("OnClick", function(self)
      self:Hide()
      local ok, floors, pick = pcall(G.PinFloors, self.level, self.wx, self.wy)
      if not ok then floors, pick = {}, 0 end
      ns.Pins.OpenEditor({ level = self.level, x = self.wx, y = self.wy, floors = floors, pick = pick })
    end)
    createAsk:SetScript("OnUpdate", function(self)
      if GetTime() - self.shownAt > 5 then self:Hide() end -- not taken up: go away
    end)
  end
  createAsk.level, createAsk.wx, createAsk.wy = level, x, y
  createAsk.shownAt = GetTime()
  createAsk:ClearAllPoints()
  createAsk:SetPoint("BOTTOM", canvas, "CENTER", dxUI, dyUI + 4) -- (the cursor's spot on the screen: not the panned icon layer)
  createAsk:Show()
  GameTooltip_Hide()
  return true
end

function G.RemovePending(i)
  table.remove(pending, i)
  local kept = {}
  for _, d in ipairs(pending) do
    d.icon = ns.Nav.NextMarker(ns.Nav.stops, kept)
    kept[#kept + 1] = d
  end
  lastActivity = GetTime()
  elapsed = 1
  -- (the last one gone: the map stays where it is, not back to the player; asked 2026-11-16 for 1.3.5, "when right click
  -- removing a stop and its the only stop, don't snap back to the player's position")
end

-- Hovering a quest area on the map shows the quest and its objectives, like the minimap.
local hoverWait, hoverKey = 0, nil
local infoWait = 0
function G.AreaTooltip(dt)
  hoverWait = hoverWait - dt
  if hoverWait > 0 then return end
  hoverWait = 0.1
  local st = S()
  -- (the controller in use: the crosshair, the map's middle, as the mouse; asked 2026-11-16, "possible when using a
  -- controller to pan map to show tooltips based on crosshair like this?")
  local P = ns.Pad
  local pad = P and P.used and P.marksOn and canvas and not canvas:IsMouseOver() and not (P.MenuOpen and P.MenuOpen())
  local over = canvas and (canvas:IsMouseOver() or pad) and not drag and ns.Layers and G.QuestAreasOn()
    and not (G.roadMode or G.wallMode) -- (the road tools: the roads' heights instead, G.RoadHover)
  local owned = GameTooltip:IsShown() and GameTooltip:GetOwner() == frame
  if over and GameTooltip:IsShown() and not owned then return end -- another tooltip (an icon) has it
  local quests = {}
  if over then
    local x, y = view.x, view.y
    if not pad then
      local mx, my = GetCursorPosition()
      local sc = canvas:GetEffectiveScale()
      local ccx, ccy = canvas:GetCenter()
      x, y = G.ScreenToWorld(view.x, view.y, mx / sc - ccx, my / sc - ccy, view.rot, view.s)
    end
    local _, _, pc = Geo.PlayerWorld()
    quests = ns.Layers.QuestsAt(browse and browseCont or pc, x, y)
  end
  if #quests == 0 then
    if owned and hoverKey then GameTooltip:Hide() end -- (only its own: the zone hover's stays)
    hoverKey = nil
    G.areaTip = false
    return
  end
  table.sort(quests)
  local key = table.concat(quests, ",")
  if owned and key == hoverKey then return end
  hoverKey = key
  G.areaTip = true
  if pad then -- (over the crosshair, as the mouse's is over the pointer)
    GameTooltip:SetOwner(frame, "ANCHOR_NONE")
    GameTooltip:ClearAllPoints()
    GameTooltip:SetPoint("BOTTOM", canvas, "CENTER", 0, 16)
  else
    GameTooltip:SetOwner(frame, "ANCHOR_CURSOR")
  end
  for i, q in ipairs(quests) do
    if i > 1 then GameTooltip:AddLine(" ") end
    ns.Layers.AddQuestToTooltip(GameTooltip, q)
  end
  GameTooltip:Show()
end

-- The road tools' hover (asked 2026-10-06: "mouse over on existing road to show current Z height"): with the road or
-- wall tools on, the road under the pointer (within ROAD_HOVER_PX on the screen) and its height there, in a tooltip:
-- a level's with heights (Undercity's, a dungeon's roads: their own), a building's or a capital's floor (their roads'
-- `nz`), a stairs road's height there with its foot and top. The land's roads have none in the game's data: "on the
-- ground". Heights are the game's (world z).
G.ROAD_HOVER_PX = 8
-- What the road nearest (x, y) on `level` within `reach` yards is (on the floor near `z` where the level has heights):
-- { title, lines }, or nil (none near, or the roads not built yet: never built in a frame for this).
function G.RoadHoverInfo(level, x, y, reach, z)
  local R = ns.Router
  if not (R and R.GraphReady and R.GraphReady(level)) then return nil end
  local c = R.NearestEdges(level, x, y, z)[1]
  if not c or c.dist > reach then return nil end
  local g = R.DebugGraph(level)
  local e = g and g.e[c.edge]
  if not e then return nil end
  local heights = g.z or g.nz
  local za, zb = heights and heights[e[1]], heights and heights[e[2]]
  local here
  if g.z then here = R.EdgeZ(g, c.edge, c.along) else here = R.RoadFloor(g, c) end
  local src = e[4]
  local title = src == R.SOURCE_LIFT and L["Lift"] or src == R.SOURCE_RECORDED and L["Drawn road"] or L["Road"]
  local lines = {}
  if not here then
    lines[1] = L["On the ground (the game's data has no height for it)"]
  elseif za and zb and math.abs(za - zb) >= R.STAIR_MIN_Z then
    if src ~= R.SOURCE_LIFT then title = L["Stairs"] end
    lines[1] = Format(L["Height here: %.1f"], here)
    lines[2] = Format(L["Foot %.1f, top %.1f"], math.min(za, zb), math.max(za, zb))
  else
    lines[1] = Format(L["Height: %.1f"], here)
  end
  return { title = title, lines = lines }
end
function G.RoadHover(dt)
  G.roadHoverWait = (G.roadHoverWait or 0) - dt
  if G.roadHoverWait > 0 then return end
  G.roadHoverWait = 0.1
  local on = (G.roadMode or G.wallMode) and canvas and canvas:IsMouseOver() and not drag and not G.lasso
  local owned = GameTooltip:IsShown() and GameTooltip:GetOwner() == frame
  if on and GameTooltip:IsShown() and not owned then return end -- (another tooltip, an icon's, has it)
  local info
  if on then
    local mx, my = GetCursorPosition()
    local sc = canvas:GetEffectiveScale()
    local ccx, ccy = canvas:GetCenter()
    local x, y = G.ScreenToWorld(view.x, view.y, mx / sc - ccx, my / sc - ccy, view.rot, view.s)
    local level = G.PinLevel(x, y)
    info = level and G.RoadHoverInfo(level, x, y, G.ROAD_HOVER_PX / view.s, G.editFloor and G.editFloor.z)
  end
  if not info then
    if owned and G.roadTip then GameTooltip:Hide() end
    G.roadTip = nil
    return
  end
  local key = info.title .. "\n" .. table.concat(info.lines, "\n")
  if owned and G.roadTip == key then return end
  G.roadTip = key
  GameTooltip:SetOwner(frame, "ANCHOR_CURSOR")
  GameTooltip:SetText(info.title, 1, 1, 1)
  for _, l in ipairs(info.lines) do GameTooltip:AddLine(l, nil, nil, nil, true) end
  GameTooltip:Show()
end

function G.IsFree() return free ~= nil end

-- (every caller is something changing what's drawn, often outside the icons' signature — a pin made, a ride
-- toggled off, a boss marked dead — so the kept tiles and icons are placed again too, not only sooner)
function G.Redraw() G.drawVersion = G.drawVersion + 1 elapsed = 1 end

-- The player picks a map style (issue #75: the Map Style buttons, /agps style, Options > Map): not while a game holds
-- the map (API.HoldMap: said so, false). Live, no reload, but the Seamless style picked when the stitched map wasn't
-- loaded at login (another style then): the prompt to reload (Atlas.AskReload), Terrain until then. Off the seamless
-- map, zoomed out past what the style reaches: back to its furthest.
function G.SetStyle(style)
  if not G.STYLES[style] then return false end
  if G.HeldStyle() then -- (a game on the map set it: API.HoldMap)
    ns.Print(G.HELD_STYLE_TEXT)
    return false
  end
  local was = S().style
  S().style = style
  if style == "seamless" and was ~= style and ns.Atlas and ns.Atlas.ReloadIfNeeded then ns.Atlas.ReloadIfNeeded() end
  if not G.IsMapStyle(style) and browse then G.BrowseToTerrain() end
  if not G.Seamless() then
    G.seamOut = nil
    if free then free.seamBack = nil end
    if not browse and S().zoom > G.MaxZoom() then S().zoom = G.MaxZoom() end
  end
  if frame and G.RefreshQuick then G.RefreshQuick() end
  if ns.Options and ns.Options.Refresh then ns.Options.Refresh() end
  G.Redraw()
  return true
end

-- The use button: when the route starts with a teleport (your Hearthstone, a mage's teleport, an
-- engineer's teleporter), a button with its icon at the directions panel's corner; clicked, it
-- uses it (the player's own click: the addon never uses anything by itself). A secure button,
-- the game's rule for using items and spells: it can't be changed in combat, so it's hidden as
-- combat starts and set again after; and it's the UI's own child, not the map's (the map may
-- hide in combat, which a secure child would block), placed on the panel out of combat.
-- (Another: the arrow window's, where its arrow is, Arrow.lua: G.NewUseButton, G.SetUseButton.)
function G.NewUseButton(name, panel, size)
  if not CreateFrame or G.clone then return nil end
  local ok, b = pcall(CreateFrame, "Button", name, UIParent, "SecureActionButtonTemplate")
  if not ok or not b then return nil end
  b:SetSize(size or 24, size or 24)
  b:RegisterForClicks("AnyUp", "AnyDown") -- (either setting of "cast on key down")
  b.icon = b:CreateTexture(nil, "ARTWORK")
  b.icon:SetAllPoints()
  b:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Square", "ADD")
  -- (on its cooldown: the time left over the icon, G.UseWait)
  b.cd = b:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmallOutline")
  b.cd:SetPoint("CENTER")
  b.panel = panel
  b:Hide()
  b:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_LEFT")
    GameTooltip:SetText(self.what and Format(L["Use %s"], self.what) or L["Use it"], 1, 1, 1)
    if self.to then GameTooltip:AddLine(Format(L["To %s: the route's next step."], self.to), nil, nil, nil, true) end
    if self.wait then GameTooltip:AddLine(Format(L["On its cooldown: ready in %s."], G.UseWaitText(self)), 1, 0.3, 0.3, true) end
    GameTooltip:Show()
  end)
  b:SetScript("PostClick", function(self) G.UseWaitClick(self) end)
  b:SetScript("OnLeave", GameTooltip_Hide)
  local ev = CreateFrame("Frame")
  ev:RegisterEvent("PLAYER_REGEN_DISABLED") -- (fired before combat's lockdown: still allowed)
  ev:RegisterEvent("PLAYER_REGEN_ENABLED")
  ev:SetScript("OnEvent", function(_, e)
    if e == "PLAYER_REGEN_DISABLED" then
      -- (off its window too, not only hidden: a protected button anchored to the directions panel makes the panel and
      -- the whole map window protected in combat, so it couldn't be sized or moved mid-fight: out from the minimap
      -- square it stayed the square's size, back into it the window's, seen in game 2026-11-12. Placed again after.)
      b:Hide()
      b:ClearAllPoints()
      b.key = nil
    else
      elapsed = 1 -- (set again on the next redraw)
    end
  end)
  if ns.TimeScript then ns.TimeScript(ev, "OnEvent", "events (map)") end
  panel:HookScript("OnHide", function()
    if not (InCombatLockdown and InCombatLockdown()) then
      b:Hide()
      b.key = nil
    end
  end)
  return b
end
function G.MakeUseButton(panel)
  if G.useBtn then return end
  G.useBtn = G.NewUseButton("AzerothGPSUseButton", panel, 24)
end

-- A teleport row's icon: its item's or spell's (the question mark when the game hasn't it yet).
function G.UseTexture(t)
  local tex
  if t and t.item then
    tex = (C_Item and C_Item.GetItemIconByID and C_Item.GetItemIconByID(t.item)) or (GetItemIcon and GetItemIcon(t.item))
  elseif t and t.spell then
    tex = (C_Spell and C_Spell.GetSpellTexture and C_Spell.GetSpellTexture(t.spell)) or (GetSpellTexture and GetSpellTexture(t.spell))
  end
  return tex or 134400
end
-- What the use button uses: `t`, a teleport row with item or spell (Nav.UseNow), or nil (hidden).
-- The key it's set for: "item:6948", "spell:556", or nil.
function G.UseKey(t)
  if not t then return nil end
  if t.item then return "item:" .. t.item end
  if t.spell then return "spell:" .. t.spell end
  return nil
end

-- Button `b` set for teleport row `t` (nil: hidden), put in its place by `place(b)` (cleared first).
-- Not in combat (a secure button: hidden as combat starts, set again after).
function G.SetUseButton(b, t, place)
  if not b or (InCombatLockdown and InCombatLockdown()) then return end
  local key = G.UseKey(t)
  if key ~= b.key then
    b.key = key
    if not key then
      b:Hide()
      return
    end
    b.wait, b.waitAt = nil, nil -- (its attributes: G.UseWait, below)
    b.icon:SetTexture(G.UseTexture(t))
    b.what, b.to = t[8], t[10]
    b:ClearAllPoints()
    place(b)
    b:SetFrameStrata(b.panel:GetFrameStrata())
    b:SetFrameLevel(b.panel:GetFrameLevel() + 20)
    b:Show()
  end
  if key then G.UseWait(b, t) end
end

-- The use button's teleport on its cooldown (it went on one after the route was planned: used, or another
-- sharing it): the time left over its icon, grayed, and nothing to use (no "type": the game's use isn't
-- called), a click saying when it's ready (G.UseWaitClick); ready again, it uses it. Looked at every
-- USE_WAIT_EVERY s (from the redraw and the arrow window), out of combat only (SetUseButton's rule).
G.USE_WAIT_EVERY = 0.1
function G.UseWait(b, t)
  local now = GetTime()
  if b.wait ~= nil and b.waitAt and now - b.waitAt < G.USE_WAIT_EVERY then return end
  b.waitAt = now
  local T = ns.Teleports
  local left = T and T.CooldownLeft and T.CooldownLeft(t) or 0
  local wait = left > 0
  b.left = left
  if b.cd then b.cd:SetText(wait and T.FormatCooldown(left) or "") end
  if wait == b.wait then return end
  b.wait = wait
  if wait then
    b:SetAttribute("type", nil)
  elseif t.item then
    b:SetAttribute("type", "item")
    b:SetAttribute("item", G.UseKey(t))
    b:SetAttribute("spell", nil)
  else
    b:SetAttribute("type", "spell")
    b:SetAttribute("spell", ns.SpellName and ns.SpellName(t.spell) or t.spell)
    b:SetAttribute("item", nil)
  end
  if b.icon.SetDesaturated then b.icon:SetDesaturated(wait) end
end
function G.UseWaitText(b)
  local T = ns.Teleports
  return T and T.FormatCooldown and T.FormatCooldown(b.left or 0) or ""
end
-- A click while it waits: when it's ready, in the chat (once for a key's down and up).
function G.UseWaitClick(b)
  if not b.wait then return end
  local now = GetTime()
  if b.saidAt and now - b.saidAt < 1 then return end
  b.saidAt = now
  if not ns.Print then return end
  if not b.what then
    ns.Print(Format(L["It is on its cooldown: ready in %s."], G.UseWaitText(b)))
    return
  end
  local what = b.what:gsub("^%l", string.upper)
  ns.Print(Format(L["%s is on its cooldown: ready in %s."], what, G.UseWaitText(b)))
end
-- The directions panel's: at its corner.
-- (detached: left of its corner grip)
local function PlaceUse(b) b:SetPoint("BOTTOMRIGHT", b.panel, "BOTTOMRIGHT", G.navDetached and -20 or -5, 5) end
-- (not on the minimap square: the directions it belongs to aren't shown there. Asked 2026-11-10: "when route is
-- suggesting hearthstone its on the minimap as well, don't show that". The arrow window's own stays.)
function G.UpdateUseButton(t)
  if G.MinimapMode() then t = nil end
  G.SetUseButton(G.useBtn, t, PlaceUse)
end

-- Near the next stop (option): the map zooms in smoothly for the last yards, and back out
-- once you're there (or move away, or zoom yourself). Only while following the player.
G.APPROACH_YD = 50 -- zoom in this close to the stop
G.APPROACH_LEAVE_YD = 70 -- ... and back out beyond this
G.APPROACH_ZOOM = 70 -- yards from the middle to the edge, zoomed in
G.APPROACH_SPEED = 2.5 -- how fast it eases (per second)

function G.ApproachTarget(px, py, cont)
  local st = S()
  local N = ns.Nav
  local d = N.dest
  if not st.approachZoom or not d or not px or free or browse or tour or N.arrivedAt then return nil end
  -- (on its level: not with the stop straight above or below, down a lift)
  if N.PlayerLevel(cont) ~= d.cont or d.spotReached or N.QuestPaused() or approachSkip == d then return nil end
  local dd = math.sqrt((d.x - px) ^ 2 + (d.y - py) ^ 2)
  if dd > (approachFor == d and G.APPROACH_LEAVE_YD or G.APPROACH_YD) then return nil end
  approachFor = d
  return math.min(st.zoom, G.APPROACH_ZOOM)
end

function G.UpdateApproach(dt)
  local st = S()
  local px, py, cont = Geo.PlayerWorld()
  local target = G.ApproachTarget(px, py, cont)
  if not target then approachFor = nil end
  if not target and not approachZoom then return end
  local goal = target or st.zoom
  local cur = approachZoom or st.zoom
  local nz = math.exp(math.log(cur) + (math.log(goal) - math.log(cur)) * math.min(1, dt * G.APPROACH_SPEED))
  if not target and math.abs(nz - st.zoom) < st.zoom * 0.01 then
    approachZoom = nil -- back to the zoom it had
  else
    approachZoom = nz
  end
  if math.abs(nz - cur) > 0.01 then elapsed = 1 end
end

-- A route made or changed from outside the map (quest route, a shared map pin): the
-- route tour when the map is open (closing it ends the tour and follows the player);
-- closed, just follow the player, no tour when it's opened.
function G.RouteChanged()
  local px, py, cont = Geo.PlayerWorld()
  G.Follow()
  if frame and frame:IsVisible() and px and ns.Nav.dest then
    free = { x = view.x, y = view.y, rot = view.rot, cont = view.cont }
    StartTour(px, py, cont, ViewCont(cont), true)
    elapsed = 1
  end
end

-- The quest route button: stops for the quest log's objectives and turn-ins, in the
-- fastest order, as the route.
function G.QuestRoute()
  if ns.Nav.DungeonLocked() then ns.Nav.SayLocked() return end
  if InCombatLockdown and InCombatLockdown() then
    ns.Print(L["Quest Route: not in combat (the game hides quest locations then)."])
    return
  end
  if not (ns.Layers and ns.Layers.QuestStops) then return end
  local onlyZone = S().questZoneOnly
  local stops, c = ns.Layers.QuestStops(onlyZone)
  if #stops == 0 then
    ns.Print(onlyZone and c.elsewhere > 0
      and Format(L["Quest Route: none of your quests are in this zone (%d elsewhere; Options > Routing: only this zone)."], c.elsewhere)
      or L["Quest Route: no quest locations found in your quest log."])
    return
  end
  -- (asked 2026-10-06) a group quest (elite, or more than one player suggested): asked whether to keep it, each
  -- once a session (G.groupChoice), then the route. Its choice is shown in the directions with a button to change it
  -- (G.LayoutGroupRows; asked 2026-10-07: "show my choice and let me change it"). Every quest found left out: asked
  -- again, or the route would have nothing to show the choices on, and no way back
  G.groupQuests = G.GroupQuestsOf(stops)
  local any = false
  for _, d in ipairs(stops) do
    if not (d.quest and not d.turnin and G.groupChoice[d.quest] == "leave") then any = true break end
  end
  if not any then
    for _, q in ipairs(G.groupQuests) do G.groupChoice[q.id] = nil end
  end
  local ask = G.GroupQuestsToAsk(stops)
  local function Next(i)
    local q = ask[i]
    if not q then return G.SetQuestRoute(stops, c) end
    G.Ask("AzerothGPSGroupQuest", G.GroupQuestText(q), L["Keep"], L["Leave Out"],
      function() G.groupChoice[q.id] = "keep" Next(i + 1) end,
      function() G.groupChoice[q.id] = "leave" Next(i + 1) end)
  end
  Next(1)
end

-- Group quests asked about this session: questID -> "keep" or "leave" (Leave Out, or the question closed).
G.groupChoice = {}

-- The directions' pulsing Sprint icon clicked (a quest picked up or finished since the quest route was made): the
-- quest route made again. The first click ever (asked 2026-11-12: "first click ask if the player would like for
-- rerouting to happen automatically. This will only be ever asked once. Tell them where the option is") asks whether
-- it should happen by itself from now on (`questAutoReroute`; asked once for the account, `questAutoAsked`), says
-- where the option is either way, then remakes the route.
function G.QuestRerouteClick()
  local db = ns.db
  if db and not db.questAutoAsked then
    db.questAutoAsked = true
    local function Answer(on)
      S().questAutoReroute = on
      ns.Print(on and L["Quest Route: it's made again by itself now when you pick up or finish a quest. To turn this off: Options > Routing > \"Quest route: reroute by itself\"."]
        or L["Quest Route: click the pulsing Sprint icon to make it again. To have it done by itself: Options > Routing > \"Quest route: reroute by itself\"."])
      if ns.Options and ns.Options.Refresh then ns.Options.Refresh() end
      G.QuestRoute()
    end
    G.Ask("AzerothGPSQuestAuto", L["Make your quest route again automatically by itself whenever you pick up or finish a quest?\n(Asked once; you can change it in Options > Routing.)"],
      L["Yes"], L["No"], function() Answer(true) end, function() Answer(false) end)
    return
  end
  G.QuestRoute()
end
-- The quest route made again by itself (the option on): a moment after the quest change (the quest log's areas
-- come in after QUEST_ACCEPTED), and not in combat or while a question is up (tried again until then).
G.AUTO_QUEST_DELAY = 1.5
function G.AutoQuestRoute()
  if G.autoQuestPending then return end
  G.autoQuestPending = true
  local after = C_Timer and C_Timer.After
  if after then after(G.AUTO_QUEST_DELAY, G.AutoQuestTick) else G.AutoQuestTick() end
end
function G.AutoQuestTick()
  G.autoQuestPending = nil
  local N = ns.Nav
  if not (N.questRouteStale and N.QuestAutoReroute() and N.OnQuestRoute()) then return end
  local asking = G.askBox and G.askBox.IsShown and G.askBox:IsShown()
  if (InCombatLockdown and InCombatLockdown()) or asking then return G.AutoQuestRoute() end
  G.QuestRoute()
end

-- The route to the quest picked (asked 2026-11-13, a player: "when I select a quest and activate it, I'd like the
-- route guidance to start as well"; option `questPickRoute`, Options > Routing, off by default): the quest the player
-- focuses in the quest log or the objective tracker (the game's super-tracking: C_SuperTrack, SUPER_TRACKING_CHANGED)
-- becomes the route, its objectives and turn-in from the quest route's stops (Layers.QuestStops, every zone), a moment
-- after the change (it comes in bursts). The same quest again leaves the route as it is; in combat or a dungeon it
-- waits for the next pick.
G.PICK_DELAY = 0.3
function G.OnQuestPicked()
  if not S().questPickRoute or G.pickPending then return end
  G.pickPending = true
  local after = C_Timer and C_Timer.After
  if after then after(G.PICK_DELAY, G.PickedQuestRoute) else G.PickedQuestRoute() end
end
function G.PickedQuestRoute()
  G.pickPending = nil
  if not S().questPickRoute then return end
  local ST = rawget(_G, "C_SuperTrack")
  local ok, qid = pcall(function() return ST and ST.GetSuperTrackedQuestID and ST.GetSuperTrackedQuestID() end)
  if not ok or (ns.IsSecret and ns.IsSecret(qid)) or not tonumber(qid) or tonumber(qid) <= 0 then return end
  qid = tonumber(qid)
  if qid == G.pickedQuest then return end
  if ns.Nav.DungeonLocked() or (InCombatLockdown and InCombatLockdown()) then return end
  if not (ns.Layers and ns.Layers.QuestStops) then return end
  G.pickedQuest = qid
  G.RouteToQuest(qid)
end

-- One quest as the route: its objectives and turn-in from the quest route's stops (Layers.QuestStops, every zone).
-- For the option above and Route Here (the quest details' button and the quest menus, asked 2026-11-13). True when
-- routed; else said why (a dungeon's route, combat: the game hides quest locations then, no location known).
-- quest `qid`'s stops (its objectives and turn-in), or nil having said why there are none
function G.QuestStopsFor(qid)
  qid = tonumber(qid)
  if not qid or qid <= 0 then return nil end
  if ns.Nav.DungeonLocked() then
    ns.Nav.SayLocked()
    return nil
  end
  if InCombatLockdown and InCombatLockdown() then
    ns.Print(L["Quest Route: not in combat (the game hides quest locations then)."])
    return nil
  end
  if not (ns.Layers and ns.Layers.QuestStops) then return nil end
  local mine = {}
  for _, d in ipairs(ns.Layers.QuestStops(false) or {}) do
    if d.quest == qid then mine[#mine + 1] = d end
  end
  if #mine == 0 then
    ns.Print(L["Quest Route: no location found for the quest you picked."])
    return nil
  end
  return mine
end
function G.RouteToQuest(qid)
  local mine = G.QuestStopsFor(qid)
  if not mine then return false end
  G.SetQuestRoute(mine, { missing = {}, elsewhere = 0 })
  return true
end

-- A quest double-clicked in the game's quest log, its objective tracker or Questie's tracker (asked 2026-11-14: "can we
-- support double click to route to a quest on the quest itself? ... (this should add a stop if route in progress)"):
-- with no route, the route to it (G.RouteToQuest); with one, its stops added to it, those already in it left out.
-- Two left clicks on the same quest within QUEST_DOUBLE_CLICK seconds (G.QuestClicked, from post-hooks: whatever the
-- click does there still happens).
G.QUEST_DOUBLE_CLICK = 0.4
function G.QuestClicked(qid, button)
  qid = tonumber(qid)
  if not qid or (button and button ~= "LeftButton") then return false end
  local now = GetTime()
  local last = G.lastQuestClick
  if last and last.id == qid and now - last.t <= G.QUEST_DOUBLE_CLICK then
    G.lastQuestClick = nil
    G.RouteOrAddQuest(qid)
    return true
  end
  G.lastQuestClick = { id = qid, t = now }
  return false
end
function G.RouteOrAddQuest(qid)
  local stops = ns.Nav.stops or {}
  if #stops == 0 then return G.RouteToQuest(qid) end
  local mine = G.QuestStopsFor(qid)
  if not mine then return false end
  local had = {}
  for _, d in ipairs(stops) do
    if d.quest then had[d.quest .. ":" .. tostring(d.turnin and true or false) .. ":" .. tostring(d.name)] = true end
  end
  local added = 0
  for _, d in ipairs(mine) do
    if not had[d.quest .. ":" .. tostring(d.turnin and true or false) .. ":" .. tostring(d.name)] then
      local ok, asking = ns.Nav.AddStop(d)
      if asking then return true end -- (a zone too high: asked, added on yes)
      if not ok then break end
      added = added + 1
    end
  end
  if added > 0 then G.RouteChanged() end
  local title = mine[1].questTitle or mine[1].name or tostring(qid)
  ns.Print(added == 1 and Format(L["Quest Route: %s added to the route (1 stop)."], title)
    or added > 1 and Format(L["Quest Route: %s added to the route (%d stops)."], title, added)
    or Format(L["Quest Route: %s is in the route already."], title))
  return added > 0
end
-- Questie's tracker lines (its frames "linePool1".., each with its quest as .Quest.Id): their clicks post-hooked once
-- each; true when any is. Questie's own clicks (open the quest log, its menu) go on as ever.
function G.HookQuestieLines()
  local n = 0
  for i = 1, 500 do
    local line = rawget(_G, "linePool" .. i)
    if type(line) ~= "table" then break end
    if not line.agpsQuestDouble and line.HookScript then
      line.agpsQuestDouble = true
      pcall(line.HookScript, line, "OnClick", function(self, button)
        local q = type(self.Quest) == "table" and self.Quest.Id
        if q then G.QuestClicked(q, button) end
      end)
    end
    n = n + 1
  end
  return n > 0
end
-- The game's quest log's titles (QuestMapLogTitleButton_OnClick, the button's questID) and the objective tracker's
-- headers (OnBlockHeaderClick: the block's id): post-hooked once.
function G.HookQuestDoubleClicks()
  if not G.questLogDouble and hooksecurefunc and type(rawget(_G, "QuestMapLogTitleButton_OnClick")) == "function" then
    G.questLogDouble = true
    hooksecurefunc("QuestMapLogTitleButton_OnClick", function(self, button)
      if type(self) == "table" then G.QuestClicked(self.questID, button) end
    end)
  end
  if not G.trackerDouble and hooksecurefunc then
    for _, name in ipairs(G.QUEST_TRACKERS) do
      local t = rawget(_G, name)
      if type(t) == "table" and type(t.OnBlockHeaderClick) == "function" then
        G.trackerDouble = true
        hooksecurefunc(t, "OnBlockHeaderClick", function(_, block, button)
          if type(block) == "table" then G.QuestClicked(block.id, button) end
        end)
      end
    end
  end
  G.HookQuestieLines()
end

-- Route Here (asked 2026-11-13, a screenshot of the world map's quest details: "Put a Route Here button here, also
-- can we support right clicking a quest and adding Route Here option as well?"): a button beside the quest details'
-- Back (QuestMapFrame.DetailsFrame.BackFrame.BackButton; the quest shown is DetailsFrame.questID), and an entry in
-- the quest log's and the objective tracker's right-click menus (the game's own menus by tag, Menu.ModifyMenu, the
-- documented way for addons: MENU_QUEST_MAP_LOG_TITLE, whose owner is the quest's title button with its questID, and
-- MENU_QUEST_OBJECTIVE_TRACKER, whose owner is the tracker: the quest right-clicked comes from a post-hook on its
-- OnBlockHeaderClick, which runs after the menu is made and before an entry is clicked). Never with the controller UI
-- on (G.ControllerUI: an addon's frame in a game panel there makes forbidden actions).
function G.MakeRouteHere()
  if G.routeHereBtn then return G.routeHereBtn end
  if G.ControllerUI() then return nil end
  local qmf = rawget(_G, "QuestMapFrame")
  local df = type(qmf) == "table" and qmf.DetailsFrame
  local bf = type(df) == "table" and df.BackFrame
  local back = type(bf) == "table" and bf.BackButton
  if not back then return nil end
  local ok, b = pcall(CreateFrame, "Button", "AzerothGPSRouteHereButton", bf, "UIPanelButtonTemplate")
  if not ok or not b then return nil end
  b:SetText(L["Route Here"])
  local fs = b.GetFontString and b:GetFontString()
  b:SetSize(math.max(90, ((fs and fs:GetStringWidth()) or 70) + 24), (back.GetHeight and back:GetHeight()) or 22)
  b:SetPoint("LEFT", back, "RIGHT", 4, 0)
  b:SetScript("OnClick", function() G.RouteToQuest(df.questID) end)
  b:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText(L["Route Here"], 1, 1, 1)
    GameTooltip:AddLine(L["The route goes to this quest's objectives and turn-in."], nil, nil, nil, true)
    GameTooltip:Show()
  end)
  b:SetScript("OnLeave", GameTooltip_Hide)
  G.routeHereBtn = b
  return b
end
function G.HookQuestMenus()
  if G.questMenus then return true end
  local M = rawget(_G, "Menu")
  if not (type(M) == "table" and type(M.ModifyMenu) == "function") then return false end
  G.questMenus = true
  local function Add(root, quest)
    pcall(function()
      root:CreateDivider()
      root:CreateButton(L["Route Here"], function() G.RouteToQuest(quest()) end)
    end)
  end
  pcall(M.ModifyMenu, "MENU_QUEST_MAP_LOG_TITLE", function(owner, root)
    local q = type(owner) == "table" and tonumber(owner.questID)
    if q then Add(root, function() return q end) end
  end)
  local hooked = 0
  for _, name in ipairs(G.QUEST_TRACKERS) do
    local t = rawget(_G, name)
    if type(t) == "table" and type(t.OnBlockHeaderClick) == "function" and hooksecurefunc then
      hooksecurefunc(t, "OnBlockHeaderClick", function(_, block, button)
        if button == "RightButton" and type(block) == "table" then G.trackerMenuQuest = block.id end
      end)
      hooked = hooked + 1
    end
  end
  if hooked > 0 then
    pcall(M.ModifyMenu, "MENU_QUEST_OBJECTIVE_TRACKER", function(_, root)
      Add(root, function() return G.trackerMenuQuest end)
    end)
  end
  return true
end
G.QUEST_TRACKERS = { "QuestObjectiveTracker", "CampaignQuestObjectiveTracker" }
function G.InitRouteHere()
  if G.clone then return end -- (the second map, the square beside the world map's: the first one's are the ones)
  local function Try()
    G.MakeRouteHere()
    G.HookQuestMenus()
    G.HookQuestDoubleClicks()
    return G.questMenus and (G.routeHereBtn or G.ControllerUI())
  end
  if Try() or G.routeHereEvents or not CreateFrame then return end
  local f = CreateFrame("Frame") -- (the quest map or the menus loaded later: tried again as addons load)
  G.routeHereEvents = f
  f:RegisterEvent("ADDON_LOADED")
  f:SetScript("OnEvent", function(self)
    if Try() then self:UnregisterAllEvents() end
  end)
  -- (Questie makes its tracker's lines as it fills them: their double-clicks hooked a while after login too)
  if C_Timer and C_Timer.NewTicker then
    local tries = 0
    C_Timer.NewTicker(5, function(t)
      tries = tries + 1
      G.HookQuestDoubleClicks()
      if tries >= 24 then t:Cancel() end
    end)
  end
  if ns.TimeScript then ns.TimeScript(f, "OnEvent", "events (route here)") end
end
function G.InitPickRoute()
  if G.pickEvents or not CreateFrame then return end
  local f = CreateFrame("Frame")
  G.pickEvents = f
  pcall(f.RegisterEvent, f, "SUPER_TRACKING_CHANGED") -- (a client without it: no picks to follow)
  f:SetScript("OnEvent", function() G.OnQuestPicked() end)
  if ns.TimeScript then ns.TimeScript(f, "OnEvent", "events (quest picked)") end
end
-- The quest route's group quests: { { id, title, group = Layers.QuestGroup's }, ... }. A turn-in isn't one to ask
-- about (the quest's done).
function G.GroupQuestsOf(stops)
  local out, seen = {}, {}
  for _, d in ipairs(stops) do
    local id = d.quest
    if id and not d.turnin and not seen[id] and ns.Layers.QuestGroup then
      seen[id] = true
      local g = ns.Layers.QuestGroup(id)
      local red = ns.Layers.QuestRed and ns.Layers.QuestRed(id) -- (a red quest: asked about the same way)
      if g or red then out[#out + 1] = { id = id, title = d.name, group = g, red = red } end
    end
  end
  return out
end
-- Those not asked about yet this session.
function G.GroupQuestsToAsk(stops)
  local out = {}
  for _, q in ipairs(G.GroupQuestsOf(stops)) do
    if not G.groupChoice[q.id] then out[#out + 1] = q end
  end
  return out
end
-- The quest route's group quests (G.QuestRoute's last), for the directions' rows.
G.groupQuests = {}
-- A row's button: a group quest left out put back, or a kept one left out, and the quest route made again (not asked
-- again: the choice is the player's).
function G.ToggleGroupQuest(id)
  G.groupChoice[id] = G.groupChoice[id] == "leave" and "keep" or "leave"
  G.QuestRoute()
end
-- The directions' rows for the quest route's group quests, under `below` in `panel`: each one kept or left out, with
-- Leave Out or Put Back (the route's only quest isn't offered to leave out: nothing would be left). Their height.
G.GROUP_ROW_H = 16
function G.LayoutGroupRows(panel, below, show)
  G.groupRows = G.groupRows or {}
  local quests, n = {}, 0 -- (the quests on the route now)
  for _, d in ipairs(ns.Nav.stops) do
    if d.questRoute and d.quest and not quests[d.quest] then quests[d.quest], n = true, n + 1 end
  end
  local shown = 0
  for _, q in ipairs(show and ns.Nav.OnQuestRoute() and G.groupQuests or {}) do
    local choice = G.groupChoice[q.id]
    if choice then
      shown = shown + 1
      local row = G.groupRows[shown] or G.MakeGroupRow(panel)
      G.groupRows[shown] = row
      row.qid = q.id
      local left = choice == "leave"
      row.text:SetText(Format(left and L["|cff9d9d9dLeft out:|r %s"]
        or (q.group and L["|cffb0b0b0Group quest:|r %s"] or L["|cffff4040Red quest:|r %s"]), q.title or "?"))
      row.button.label:SetText(left and L["Put Back"] or L["Leave Out"])
      row.button:SetWidth(row.button.label:GetStringWidth() + 12)
      row.button:SetShown((left or n > 1) and not G.NavBare())
      row:ClearAllPoints()
      row:SetPoint("TOPLEFT", below, "BOTTOMLEFT", 0, -4 - (shown - 1) * G.GROUP_ROW_H)
      row:SetPoint("RIGHT", panel, "RIGHT", -32, 0)
      row:Show()
    end
  end
  for i = shown + 1, #G.groupRows do G.groupRows[i]:Hide() end
  return shown > 0 and shown * G.GROUP_ROW_H + 4 or 0
end
function G.MakeGroupRow(panel)
  local row = CreateFrame("Frame", nil, panel)
  row:SetHeight(G.GROUP_ROW_H)
  -- (a small gold-edged box, as the panel's -/+ buttons)
  local b = CreateFrame("Button", nil, row)
  b:SetHeight(14)
  b:SetPoint("RIGHT", row, "RIGHT", 0, 0)
  local edge = b:CreateTexture(nil, "BACKGROUND")
  edge:SetAllPoints()
  edge:SetColorTexture(1, 0.82, 0, 0.6)
  local fill = b:CreateTexture(nil, "BORDER")
  fill:SetPoint("TOPLEFT", 1, -1)
  fill:SetPoint("BOTTOMRIGHT", -1, 1)
  fill:SetColorTexture(0.12, 0.07, 0.03, 1)
  local hover = b:CreateTexture(nil, "HIGHLIGHT")
  hover:SetAllPoints(fill)
  hover:SetColorTexture(1, 1, 1, 0.15)
  b.label = b:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  b.label:SetPoint("CENTER", 0, 0)
  b:SetScript("OnClick", function() if row.qid then G.ToggleGroupQuest(row.qid) end end)
  b:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    local left = G.groupChoice[row.qid] == "leave"
    GameTooltip:SetText(left and L["Put Back"] or L["Leave Out"], 1, 1, 1)
    GameTooltip:AddLine(left and L["Puts this quest back in your Quest Route."] or
      L["Leaves this quest out of your Quest Route. Put Back brings it back."], nil, nil, nil, true)
    GameTooltip:Show()
  end)
  b:SetScript("OnLeave", GameTooltip_Hide)
  row.button = b
  row.text = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  row.text:SetPoint("LEFT", row, "LEFT", 0, 0)
  row.text:SetPoint("RIGHT", b, "LEFT", -4, 0)
  row.text:SetJustifyH("LEFT")
  row.text:SetWordWrap(false)
  return row
end
function G.GroupQuestText(q)
  if not q.group then
    return Format(L["|cffffd100%s|r is a red quest (level %d).\nKeep it in your route?"], q.title or L["This quest"],
      q.red or 0)
  end
  local why = {}
  if q.red then why[#why + 1] = Format(L["red, level %d"], q.red) end
  if q.group.elite then why[#why + 1] = L["elite"] end
  if (q.group.size or 0) > 1 then why[#why + 1] = Format(L["%d players suggested"], q.group.size) end
  if #why == 0 and q.group.tag then why[1] = q.group.tag:lower() end
  return Format(L["|cffffd100%s|r is a group quest (%s).\nKeep it in your route?"], q.title or L["This quest"],
    table.concat(why, L[", "]))
end
-- The quest route set: `stops` less the group quests left out and the stops the player removed on this quest route run
-- (Nav.QuestDropped); `c` the counts from Layers.QuestStops.
function G.SetQuestRoute(stops, c)
  local kept, left = {}, {}
  for _, d in ipairs(stops) do
    if (d.quest and not d.turnin and G.groupChoice[d.quest] == "leave") or ns.Nav.QuestDropped(d) then
      left[#left + 1] = d.name
    else
      kept[#kept + 1] = d
    end
  end
  if #kept == 0 then
    ns.Print(L["Quest Route: every quest found is one you left out."])
    return
  end
  if ns.Nav.SetStops(kept, true) == false then return end -- (asked first: a zone too high)
  ns.Nav.questRouteStale = nil
  -- (the quests finished now are in it, or have no turn-in to show: only those finished from here on pulse the icon)
  if ns.Nav.CheckQuestsDone and ns.Layers.LogQuests then ns.Nav.CheckQuestsDone(ns.Layers.LogQuests(), true) end
  G.RouteChanged()
  local todo, turnin = 0, 0
  for _, d in ipairs(kept) do
    if d.turnin then turnin = turnin + 1 else todo = todo + 1 end
  end
  local msg = #ns.Nav.stops == 1 and Format(L["Quest Route: 1 stop (%d to do, %d to turn in)."], todo, turnin)
    or Format(L["Quest Route: %d stops (%d to do, %d to turn in)."], #ns.Nav.stops, todo, turnin)
  if #left > 0 then msg = msg .. " " .. Format(L["Left out: %s."], table.concat(left, L[", "])) end
  if (c.elsewhere or 0) > 0 then msg = msg .. " " .. Format(L["%d in other zones left out."], c.elsewhere) end
  if #c.missing > 0 then msg = msg .. " " .. Format(L["No location for: %s."], table.concat(c.missing, L[", "])) end
  ns.Print(msg)
end

-- The boss route's stops for instance level `lvl`: its bosses in the usual order (those
-- without one after, by the order they're listed), not the optional ones nor the dead.
function G.BossStops(lvl)
  local stops, dead = {}, 0
  for _, b in ipairs(G.BossOrder(lvl)) do
    if ns.Nav.BossDead({ cont = lvl, boss = ns.Nav.BossKey(b) }) then
      dead = dead + 1
    elseif b[3] then -- (a boss with no spot, WoW Forever's own dungeons: not a stop)
      stops[#stops + 1] = { x = b[3], y = b[4], z = b[5], cont = lvl, name = b[1], tex = BOSS_ICON, boss = b[2], enc = b.enc }
    end
  end
  return stops, dead
end

-- The boss route: the dungeon whose map is shown, else the one the player is in.
function G.BossRoute(quiet)
  local lvl = view.instance or ns.Nav.CurrentInstance()
  local info = lvl and ns.Instances and ns.Instances[lvl]
  if not info then
    ns.Print(L["Boss Route: open a dungeon's map (click its entrance on the map) or go inside one."])
    return
  end
  local stops, dead = G.BossStops(lvl)
  if #stops == 0 then
    if G.NextBoss(lvl) then -- (bosses up, but none with a spot: WoW Forever's own dungeons, their map only)
      ns.Print(Format(L["Boss Route: %s's bosses have no spots on its map yet; the map still shows which is next."], ns.InstanceName(lvl)))
    else
      ns.Print(Format(L["Boss Route: %s's bosses are all down."], ns.InstanceName(lvl)))
    end
    return
  end
  ns.Nav.SetStops(stops, false, true) -- (the usual order: kept)
  G.RouteChanged()
  local wing = G.InstanceWing(lvl)
  local what, place = quiet and L["Dungeon route"] or L["Boss Route"], ns.InstanceName(lvl, wing)
  if #stops == 1 then
    ns.Print(dead > 0 and Format(L["%s: %s, 1 boss in the usual order (%d already down). Each is done when it dies; remove one to skip it."], what, place, dead)
      or Format(L["%s: %s, 1 boss in the usual order. Each is done when it dies; remove one to skip it."], what, place))
  else
    ns.Print(dead > 0 and Format(L["%s: %s, %d bosses in the usual order (%d already down). Each is done when it dies; remove one to skip it."], what, place, #stops, dead)
      or Format(L["%s: %s, %d bosses in the usual order. Each is done when it dies; remove one to skip it."], what, place, #stops))
  end
end

-- A route to a zone too high for the player (Nav.RedStops): "route there anyway?" `zones`:
-- { { name, lo, hi }, ... }; `stops` the route's; `again` sets them (confirmed). True when asked
-- (no popup here: false, and the route is set without asking).
-- "Yes / No" on the map (over its middle; the game's popup mid-screen while the map is hidden).
-- onYes / onNo run on the answer. False when neither can be shown.
function G.Confirm(text, onYes, onNo)
  if not ns.Ask then return false end
  G.confirmBox = G.Ask("AzerothGPSConfirm", text, YES or "Yes", NO or "No", onYes, onNo)
  return true
end

-- Every question AzerothGPS asks (asked 2026-10-04, a screenshot: "Don't use the zeppelin ...?" mid-screen): over the
-- map's middle while the map shows, with it (AzerothGPS's popup without a title bar, ns.Ask); mid-screen only while
-- it's hidden. `name`: the question's (the mid-screen window's; on the map its own window). `opts`: ns.Ask's (timeout).
-- The map only the minimap square, or not open at all, with the directions up: next to the directions instead, on the
-- side with more room (asked 2026-11-12 for 1.2.4: "when clicking reroute for quest route on directions and there is
-- a elite quest question, it doesn't pop up when using just the mini map and the map isn't open and blocks the
-- reroute. This should pop up next to the directions in this condition"; it was in the middle of the square).
G.ASK_DIR_GAP = 8
function G.AskByDirections()
  local dir = ns.Arrow and ns.Arrow.dir
  if not (dir and dir:IsShown()) then return nil end
  if frame and frame:IsShown() and not (G.MinimapMode and G.MinimapMode()) then return nil end
  return dir
end
function G.PlaceByDirections(f, dir)
  local x = dir:GetCenter()
  local w = UIParent:GetWidth() or 0
  if x and w > 0 and x > w / 2 then
    f:SetPoint("TOPRIGHT", dir, "TOPLEFT", -G.ASK_DIR_GAP, 0)
  else
    f:SetPoint("TOPLEFT", dir, "TOPRIGHT", G.ASK_DIR_GAP, 0)
  end
end
function G.Ask(name, text, yes, no, onYes, onNo, opts)
  opts = opts or {}
  local dir = G.AskByDirections()
  if dir then
    local o = {}
    for k, v in pairs(opts) do o[k] = v end
    o.strata = o.strata or "DIALOG"
    o.place = function(f) G.PlaceByDirections(f, dir) end
    G.askBox = ns.Ask(name, text, yes, no, onYes, onNo, o)
    if G.askBox then G.askBox.onMap, G.askBox.byDirections = nil, true end
    return G.askBox
  end
  -- (in the game's world map window: over everything, not on the map, which is under the world map's own icons and its
  -- canvas there: the question showed and its buttons took no clicks, 2026-11-15)
  if frame and frame:IsShown() and G.WorldMapHosted and G.WorldMapHosted() then
    local o = {}
    for k, v in pairs(opts) do o[k] = v end
    o.strata = ns.POPUP_OVER_STRATA
    o.key = name .. "@worldmap"
    o.place = function(f) f:SetPoint("CENTER", canvas, "CENTER", 0, 20) end
    G.askBox = ns.Ask(name, text, yes, no, onYes, onNo, o)
    if G.askBox then G.askBox.onMap, G.askBox.byDirections = nil, nil end
    return G.askBox
  end
  if frame and frame:IsShown() and topLayer then
    local o = { parent = topLayer, strata = topLayer:GetFrameStrata(), level = topLayer:GetFrameLevel() + 20,
      timeout = opts.timeout, check = opts.check, key = name .. "@map",
      place = function(f) f:SetPoint("CENTER", canvas, "CENTER", 0, 20) end }
    G.askBox = ns.Ask(name, text, yes, no, onYes, onNo, o)
    if G.askBox then G.askBox.onMap = true end
    return G.askBox
  end
  G.askBox = ns.Ask(name, text, yes, no, onYes, onNo, opts)
  if G.askBox then G.askBox.onMap, G.askBox.byDirections = nil, nil end
  return G.askBox
end

local function ZonesText(zones)
  local parts = {}
  for _, z in ipairs(zones) do
    parts[#parts + 1] = z[2] and Format(L["%s (level %d-%d)"], z[1], z[2], z[3] or z[2]) or z[1]
  end
  local ok, lvl = pcall(UnitLevel or error, "player")
  return table.concat(parts, L[", "]), ok and type(lvl) == "number" and lvl or nil
end

function G.ConfirmRedZone(zones, stops, again)
  local names, lvl = ZonesText(zones)
  local text
  if #stops == 1 then
    local stop = stops[1].name and stops[1].name ~= "" and stops[1].name or L["That stop"]
    text = lvl and Format(L["%s is in %s: too high for your level %d.\n\nRoute there anyway?"], stop, names, lvl)
      or Format(L["%s is in %s: too high for your level.\n\nRoute there anyway?"], stop, names)
  else
    text = lvl and Format(L["Some of the stops are in %s: too high for your level %d.\n\nRoute there anyway?"], names, lvl)
      or Format(L["Some of the stops are in %s: too high for your level.\n\nRoute there anyway?"], names)
  end
  return G.Confirm(text, function()
    again()
    G.RouteChanged()
  end, function()
    if #ns.Nav.stops == 0 then G.Follow() end -- (no: no route, back to the player)
  end)
end

-- The route walks through a zone too high for the player, with no way round it for them.
function G.ConfirmRedRoute(zones, onYes, onNo)
  local names, lvl = ZonesText(zones)
  local text = lvl and Format(L["The only way there walks through %s: too high for your level %d.\n\nKeep this route?"], names, lvl)
    or Format(L["The only way there walks through %s: too high for your level.\n\nKeep this route?"], names)
  return G.Confirm(text, onYes, function()
    onNo()
    G.RouteChanged()
  end)
end

-- The way past the other faction's guards much quicker than the safe way round (Nav's ride check, N.HostileBetter's
-- HOSTILE_SLOWER): risk it? One popup, with the zones too high on either way (asked 2026-11-14: "If a safe route
-- would 30% longer or more, ask the player if they want to risk going through enemy territory to save time"; "when
-- routing through multiple higher level zones, just ask in 1 popup"). Yes: the way past them; no: the safe way.
function G.ConfirmRisk(q, onYes, onNo)
  local names = {}
  for k, t in ipairs(q.towns or {}) do
    if k <= 3 then names[k] = t[1] end
  end
  local text = Format(L["Going past the other faction's guards at %s saves %s over the safe way round."],
    #names > 0 and table.concat(names, ", ") or "?", ns.Nav.FormatTime(q.saved or 0))
  if q.safeRed then
    local zn, lvl = ZonesText(q.safeRed)
    text = text .. "\n\n" .. Format(L["The safe way walks through %s: too high for your level %s."], zn, tostring(lvl or "?"))
  end
  -- (the way past them through zones the safe way doesn't go through too)
  local more = false
  for _, z in ipairs(q.riskyRed or {}) do
    local also = false
    for _, w in ipairs(q.safeRed or {}) do also = also or w.z == z.z end
    more = more or not also
  end
  if more then
    local zn, lvl = ZonesText(q.riskyRed)
    text = text .. "\n\n" .. Format(L["The way past the guards walks through %s: too high for your level %s."], zn, tostring(lvl or "?"))
  end
  text = text .. "\n\n" .. L["Risk enemy territory to save the time?"]
  return G.Confirm(text, function()
    onYes()
    G.RouteChanged()
  end, function()
    onNo()
    G.RouteChanged()
  end)
end

-- Whether the route is a boss route in instance level `lvl` (any, with nil).
local function OnBossRoute(lvl)
  for _, d in ipairs(ns.Nav.stops) do
    if d.boss and (not lvl or d.cont == lvl) then return true end
  end
  return false
end

-- Into a dungeon or raid (PLAYER_ENTERING_WORLD, Core.lua): with the dungeon route on, its
-- boss route (unless it's already set: a /reload in there), when the game gives the player's
-- position in there. Out of one: its boss route goes (it would lead back in).
local lastInstance -- (the dungeon the player was last in: leaving it ends its boss route)
function G.DungeonEntered()
  local lvl = ns.Nav.CurrentInstance()
  local left = lastInstance
  lastInstance = lvl
  if not lvl then
    -- (a boss route planned from outside, looking at a dungeon's map, stays)
    if left and OnBossRoute(left) then
      local keep = {}
      for _, d in ipairs(ns.Nav.stops) do
        if not (d.boss and d.cont == left) then keep[#keep + 1] = d end
      end
      if #keep > 0 then ns.Nav.SetStops(keep, false, true) else ns.Nav.Clear() end
      G.RouteChanged()
    end
    return
  end
  if S().dungeonRoute == false or OnBossRoute(lvl) then return end
  if not Geo.PlayerWorld() then
    ns.Print(L["Dungeon route: the game doesn't give your position in here, so it isn't started (/agps bosses starts it anyway)."])
    return
  end
  G.BossRoute(true)
end

-- The dungeon route on or off (the option, the map menu's toggle): on in a dungeon starts its
-- boss route; off ends it (other routes can be set again).
function G.SetDungeonRoute(on)
  S().dungeonRoute = on and true or false
  local lvl = ns.Nav.CurrentInstance()
  if on then
    ns.Print(L["Dungeon route on: entering a dungeon or raid starts its boss route."])
    if lvl and not OnBossRoute(lvl) then G.BossRoute(true) end
  else
    if lvl and OnBossRoute(lvl) then
      ns.Nav.Clear()
      G.RouteChanged()
    end
    ns.Print(L["Dungeon route off: routes are yours again (the Boss Route button still makes one)."])
  end
  if G.LayoutQuick then G.LayoutQuick() end
  elapsed = 1
end

-- Background terrain searches and road data (Router.Pump), ~1 ms a frame (WARM_MS while a
-- road network is being built). Run by the map window, or by the arrow window while the map
-- is hidden (e.g. in combat). True when one finished (the route was invalidated to use it).
G.WARM_MS = 5
G.WARM_SHARE = 0.25 -- ... and at most this share of the last frame's time (a fast frame rate isn't eaten up)
local lastPump
-- Options > Performance, "Gentle background work": smaller slices (smoother frames on a slow PC; routes
-- and the road data after a /reload take longer to work out)
G.GENTLE_MS, G.GENTLE_WARM_MS, G.GENTLE_WARM_SHARE = 0.5, 2, 0.1
-- (keeping a route up, at most this share of the last frame's time: 1 ms a 16 ms frame, less on faster ones, so a high
-- frame rate doesn't make it more ms a second; issue #316)
G.KEEP_SHARE = 1 / 16
function G.PumpBudget(frameMs, warming)
  local gentle = S().gentleBackground
  local base = gentle and G.GENTLE_MS or 1
  if not warming then return math.min(base, math.max(base / 4, frameMs * G.KEEP_SHARE)) end
  local cap, share = gentle and G.GENTLE_WARM_MS or G.WARM_MS, gentle and G.GENTLE_WARM_SHARE or G.WARM_SHARE
  return math.max(base, math.min(cap, frameMs * share)) -- (ms of this frame)
end
function G.PumpSearches()
  if not ns.Router.HasWork() then
    lastPump = nil
    return false
  end
  local t0 = ns.PerfStart()
  local now = debugprofilestop()
  local frameMs = lastPump and now - lastPump or 16
  lastPump = now
  -- (the warm-up's bigger slices for the road data after login and for a route just asked for: Nav.Fresh)
  local budget = G.PumpBudget(frameMs, (ns.Router.Warming and ns.Router.Warming()) or (ns.Nav.Fresh and ns.Nav.Fresh()))
  local done, fixed = ns.Router.Pump(debugprofilestop() + budget, debugprofilestop)
  if done then ns.Nav.SearchDone(fixed) end
  ns.PerfEnd("terrain search", t0)
  return done
end

function G.IsVisible() return frame ~= nil and frame:IsVisible() end

-- For the public API (Api.lua): the frame layers other addons may anchor to, the last drawn
-- view, and the world point under the mouse pointer (nil unless it's over the map).
function G.Canvas() return canvas end
function G.TopLayer() return topLayer end
function G.BrowseState() return browse, free end -- (for the tests)
function G.FloorBar() return fl end -- (for the tests: the floor bar and the floor line under a dungeon's or cave's map)
function G.MapArrow() return arrow end -- (for the tests: the player's arrow on the map)
function G.LookZoom() return browseZoom end -- (for the tests: a view looked at, G.LookAt, zooms by its own)
-- The dungeon's world map floor drawn last (Data/DungeonMaps.lua), or nil; and whether it was drawn alone (a map style).
function G.DungeonMapShown() return view.dungeonMap, view.dungeonMapOnly end
-- The interior's world map floor drawn last (Data/InteriorMaps.lua: a cave's map, or the inside map's), or nil; and
-- whether it was drawn alone (a map style).
function G.InteriorMapShown() return view.interiorMap, view.interiorMapOnly end
function G.ViewState()
  return view.x, view.y, view.cont, view.rot, view.s, canvas and canvas:GetWidth() / 2 or 0
end
-- The world spot under the pointer for a click on the map (the map's level; a dungeon's map: its level).
function G.ClickWorld()
  if not (canvas and view.cont) then return nil end
  local ox, oy = canvas:GetCenter()
  if not ox then return nil end
  local mx, my = GetCursorPosition()
  local sc = canvas:GetEffectiveScale()
  local x, y = G.ScreenToWorld(view.x, view.y, mx / sc - ox, my / sc - oy, view.rot, view.s)
  return x, y, view.instance or view.cont
end

-- The dev tools' map clicks (asked 2026-10-06 for a dev addon's simulated player; never set by AzerothGPS): a plain
-- left click on the map (not the world's or a continent's map, which open a zone) goes to `G.mapClickHook(x, y, level,
-- double)` first, in world yards and the level shown there, through the map's own projection at any zoom and size;
-- true when it took it. A double-click's second click comes with `double` and goes on to make a stop as always.
function G.MapClickHook(dxUI, dyUI, double)
  local hook = G.mapClickHook
  if not hook or G.Held() or not view.cont then return false end
  local x, y = G.ScreenToWorld(view.x, view.y, dxUI, dyUI, view.rot, view.s)
  local ok, used = pcall(hook, x, y, view.instance or G.PinLevel(x, y), double)
  return ok and used and not double or false
end

function G.CursorWorld()
  if not canvas or not view.cont or not canvas:IsVisible() or not canvas:IsMouseOver() then return nil end
  local ox, oy = canvas:GetCenter()
  if not ox then return nil end
  local mx, my = GetCursorPosition()
  local sc = canvas:GetEffectiveScale()
  local x, y = G.ScreenToWorld(view.x, view.y, mx / sc - ox, my / sc - oy, view.rot, view.s)
  local inst = view.instance
  if not inst then return x, y, view.cont end
  -- a dungeon's map: its level, and the height there on the floor shown (all of them: the top
  -- floor's; one: its height there when that's on it, else the floor's bottom)
  local z = ns.Nav.CityHeight and ns.Nav.CityHeight(inst, x, y)
  local floors = view.floor and view.floor > 0 and G.InstanceFloors(inst)
  local band = floors and floors[#floors - view.floor + 1]
  if band and not (z and z >= band[1] - 1 and z <= band[2] + 1) then z = band[1] end
  return x, y, inst, z
end

-- The dungeon whose map is in view (its level: 20000 + its MapID) and the floor shown (0 all,
-- else counted from the top), or nil.
function G.ViewInstance() return view.instance, view.floor end

-- What the picture depends on, compared with the last redraw (no garbage: values are
-- kept in `sig`). Returns true when any of it changed.
local sig = {}
local REDRAW_IDLE = 1
G.REDRAW_IDLE_QUIET = 5 -- (nothing by-the-second on the map: this instead, G.QuietIdle; on G: the 200-locals limit)
local lastFull = 0
local function SigChanged(...)
  local changed = false
  for i = 1, select("#", ...) do
    local v = select(i, ...)
    if sig[i] ~= v then
      sig[i] = v
      changed = true
    end
  end
  return changed
end

-- The player's moves count from half a pixel at the zoom drawn (G.MoveStep), never under a tenth of a yard: zoomed
-- out (the world map's, 4-5 yd a pixel) a tenth of a yard moved redrew the whole map and its route while walking,
-- the square's beside it too (reported 2026-11-13, 30% CPU spikes).
function G.MoveStep(s)
  if type(s) ~= "number" or s <= 0 then return 0.1 end
  return math.max(0.1, 0.5 / s)
end
-- Walking (or turning) while the map follows: G.GlidePan slides the tiles, the icons and the route's marks with the
-- player every frame and turns their arrow, so a redraw for the player's move alone shows little new (the route is
-- trimmed every Nav.TRIM_MOVED_YD walked, the panel's yards count down): it comes at G.GLIDE_HZ instead of the redraw
-- rate. Anything else changed (the route, the stops, the zoom, the view, the layers, a forced redraw) redraws at the
-- rate as before. (Issue #316: zoomed in on a long off-road leg the map redrew 20 times a second while walking, 120-130
-- ms a second of work in the game against a limit of 50.)
G.GLIDE_HZ = 5
G.glideSig, G.glideNow = {}, {}
function G.GlideFill(t)
  local st = S()
  local _, _, cont = Geo.PlayerWorld()
  t[1], t[2], t[3], t[4] = cont or false, browseZoom or approachZoom or st.zoom, free or false, browse or false
  t[5], t[6], t[7] = ns.Nav.route or false, #ns.Nav.stops, #pending
  t[8], t[9], t[10] = ns.Layers and ns.Layers.version or 0, G.Style(), canvas:GetWidth()
  t[11], t[12] = G.drawVersion, ns.Nav.Version and ns.Nav.Version() or 0
  local ok, m = pcall(G.party.io.members)
  t[13] = ok and m and m[1] and true or false -- (party members move on their own: drawn at the rate)
  t[14] = ns.Nav.Checking and ns.Nav.Checking() or false -- (the route's faded look while it's checked)
  return t
end
-- True while a redraw can wait: the layers glided this frame, nothing but the player's spot and facing changed since
-- the last redraw, and that was under 1 / G.GLIDE_HZ ago.
G.GLIDE_MAX_SHARE = 0.1 -- (nor once the player is this share of the zoom from where it was drawn: a flight's speed)
function G.GlideHolds(now, last)
  if not G.glided or now - last >= 1 / G.GLIDE_HZ then return false end
  local px, py = Geo.PlayerWorld()
  local mv = G.markView
  if not (px and G.glideX and mv and mv.s > 0) then return false end
  local far = G.GLIDE_MAX_SHARE * mv.half / mv.s
  if (px - G.glideX) ^ 2 + (py - G.glideY) ^ 2 > far * far then return false end
  local a, b = G.GlideFill(G.glideNow), G.glideSig
  if a[13] then return false end
  for i = 1, #a do
    if a[i] ~= b[i] then return false end
  end
  return true
end
local function ViewChanged()
  local px, py, cont = Geo.PlayerWorld()
  local st = S()
  local step = G.MoveStep(view.s)
  return SigChanged(px and math.floor(px / step) or false, py and math.floor(py / step) or false, cont or false,
    math.floor((Geo.Facing() or 0) * 500), browseZoom or approachZoom or st.zoom, free and free.x or false, free and free.y or false,
    free and free.rot or false, browse or false, ns.Nav.route or false, #ns.Nav.stops, #pending,
    ns.Layers and ns.Layers.version or 0, G.Style(), canvas:GetWidth())
end

function G.SetZoom(z)
  -- zooming yourself near a stop: that zoom stays (no zooming back out for this stop)
  if approachZoom then approachSkip, approachZoom = ns.Nav.dest, nil end
  S().zoom = math.max(MIN_ZOOM, math.min(G.MaxZoom(), z))
  elapsed = 1
end

-- The window frame's title centered on the window: the client's PortraitFrameTemplate centers it
-- between the portrait and the close button (its TitleContainer 58 in from the left, 24 from the
-- right), a little right of the middle. The same margin both sides, the same height and top.
G.TITLE_MARGIN = 24
function G.CenterTitle(chrome)
  local tc = chrome and chrome.TitleContainer
  if not (tc and tc.ClearAllPoints and tc.GetPoint) then return false end
  local _, _, _, _, y = tc:GetPoint(1)
  tc:ClearAllPoints()
  tc:SetPoint("TOPLEFT", chrome, "TOPLEFT", G.TITLE_MARGIN, y or -1)
  tc:SetPoint("TOPRIGHT", chrome, "TOPRIGHT", -G.TITLE_MARGIN, y or -1)
  return true
end

-- Companions' widgets on the title bar (API 15, asked 2026-10-06 for a companion's meter): G.TitleBarSlot(owner,
-- width) keeps `width` UI units at the title bar's right, left of the close button, the title bar's height
-- (TITLE_SLOT_H), over the frame's border; owner-keyed (again: resized; width nil lets it go), placed right to left in
-- the order asked. A slot shows while the window frame does and the title bar has room for it and TITLE_TEXT_MIN of
-- the title; else it's hidden (a companion hooks its OnShow / OnHide to put its widget elsewhere). While one shows,
-- the title (the place's name) sits in the middle between the logo and the slots, cut short before them, never under
-- them (left against the logo it looked lost, the 1.1.5 test pass).
G.titleSlots = {} -- owner -> { frame, width, order }
G.TITLE_SLOT_H = 20 -- (the title bar's middle: TitleContainer's, 1 down and 20 high)
G.TITLE_SLOT_GAP = 4
G.TITLE_CLOSE_ROOM = 26 -- the close button at the title bar's right
G.TITLE_TEXT_MIN = 50 -- the title's room a slot leaves at least
G.TITLE_LOGO_GAP = 4
G.titleSlotCount = 0 -- (the order asked; no file-level locals here: the file's main chunk is at Lua 5.1's 200)
function G.TitleBarSlot(owner, width)
  if owner == nil then return nil end
  local s = G.titleSlots[owner]
  width = tonumber(width)
  if not width or width <= 0 then
    if s then
      s.frame:Hide()
      G.titleSlots[owner] = nil
      G.LayoutTitle()
    end
    return nil
  end
  if not s then
    G.titleSlotCount = G.titleSlotCount + 1
    local f = CreateFrame("Frame", nil, G.chrome or UIParent) -- (the map not built yet: the window frame's once it is)
    f.agpsSlot = true
    f:EnableMouse(false) -- (the title bar under it still moves the map)
    f:Hide()
    s = { frame = f, order = G.titleSlotCount }
    G.titleSlots[owner] = s
  end
  s.width = math.floor(width + 0.5)
  s.frame:SetSize(s.width, G.TITLE_SLOT_H)
  G.LayoutTitle()
  return s.frame
end
-- Where the title starts while a slot shows: after the logo (Core.lua's plate: CORNER_LOGO_UNITS across, its middle
-- 0.42 of that in from the left).
function G.TitleLeft()
  return math.ceil((ns.CORNER_LOGO_UNITS or 62) * 0.92) + G.TITLE_LOGO_GAP
end
-- The highest frame level in the window frame (its border is at 500, its title at 510), the slots and the logo
-- (which goes over everything) left out.
function G.ChromeLevel(f, best)
  best = math.max(best or 0, f:GetFrameLevel())
  for _, c in ipairs({ f:GetChildren() }) do
    if not c.agpsSlot and c ~= (G.logo and G.logo.plate) then best = G.ChromeLevel(c, best) end
  end
  return best
end
function G.LayoutTitle()
  local chrome = G.chrome
  local list = {}
  for _, s in pairs(G.titleSlots) do list[#list + 1] = s end
  table.sort(list, function(a, b) return a.order < b.order end)
  if not chrome then
    for _, s in ipairs(list) do s.frame:Hide() end
    return
  end
  local framed = S().windowFrame ~= false
  local barW = (G.MapSize()) + 4 -- (the frame 2 past the map each side)
  local left, right = G.TitleLeft(), G.TITLE_CLOSE_ROOM
  local level = math.min(9000, G.ChromeLevel(chrome) + 2)
  local room, shown = framed, 0
  for _, s in ipairs(list) do
    local f = s.frame
    if f:GetParent() ~= chrome then f:SetParent(chrome) end
    room = room and barW - right - s.width >= left + G.TITLE_TEXT_MIN -- (in order: once one doesn't fit, nor do the rest)
    if room then
      f:ClearAllPoints()
      f:SetPoint("TOPRIGHT", chrome, "TOPRIGHT", -right, -1)
      f:SetFrameLevel(level)
      right = right + s.width + G.TITLE_SLOT_GAP
      shown = shown + 1
    end
    f:SetShown(room)
  end
  -- the title: between the logo and the slots, in the middle of that, cut short before the slots; centered on the
  -- window as before without any
  local tc = chrome.TitleContainer
  local text = tc and tc.TitleText or chrome.TitleText
  if shown > 0 and tc and tc.GetPoint then
    local _, _, _, _, y = tc:GetPoint(1)
    tc:ClearAllPoints()
    tc:SetPoint("TOPLEFT", chrome, "TOPLEFT", left, y or -1)
    tc:SetPoint("TOPRIGHT", chrome, "TOPRIGHT", -right, y or -1)
    if text and text.SetJustifyH then text:SetJustifyH("CENTER") end
    if text and text.SetWordWrap then text:SetWordWrap(false) end -- (one line: cut short with "...")
    G.titleLeft = true
  elseif G.titleLeft then -- (none shows any more: back to the middle)
    G.CenterTitle(chrome)
    if text and text.SetJustifyH then text:SetJustifyH("CENTER") end
    G.titleLeft = nil
  end
  G.titleSlotsShown = shown
end

function G.Init()
  if frame then return end
  G.ApplySeamPlayer() -- (the OpenMap stages the player set in Options > Map, read at login)
  -- (the seamless zoom, issue #57: frame levels kept under the canvas for the stitched map's art, which can't go
  -- under its parent's level; only when it's on and the stitched map's files are there to load: off, the levels are
  -- as they always were)
  G.artSpan = ns.Atlas and ns.Atlas.Wanted()
    and (ns.AtlasChunks ~= nil or (G.clone and ns.realAtlas and ns.realAtlas.loaded and true)) -- (the second: the first's)
    and ns.Atlas.ART_RANGE + 4 or 0
  frame = CreateFrame("Frame", not G.clone and "AzerothGPSFrame" or nil, UIParent, "BackdropTemplate")
  frame:SetFrameStrata("BACKGROUND") -- (under every other window: the game's and other addons')
  frame:SetClampedToScreen(true)
  frame:EnableMouse(true)
  -- Left-drag pans the map (free view); Shift+left-drag moves the frame.
  frame:SetScript("OnMouseDown", function(f, button)
    G.NoteMapUse() -- (the tools and roads shown: in use, G.ToolsIdleTick)
    if removeAsk then removeAsk:Hide() end
    -- a click on the map closes the map menu and the search panel
    if G.mapMenu then G.mapMenu:Hide() end
    if G.searchPanel then G.searchPanel:Hide() end
    -- (Shift-click drawing on: a click or drag without Shift goes on to the map's own, below)
    if (G.roadMode or G.wallMode) and not G.drawMode and not G.Held() and not G.ToolsPassClick(button) then
      if button == "LeftButton" and not S().toolShiftClick and G.PinClickDown() then return end -- (Shift: a pin, on the floor picked)
      if G.eraserMode and (button == "LeftButton" or button == "RightButton") then -- (the magic eraser)
        local mx, my = GetCursorPosition()
        local sc = canvas:GetEffectiveScale()
        local ccx, ccy = canvas:GetCenter()
        local x, y = G.ScreenToWorld(view.x, view.y, mx / sc - ccx, my / sc - ccy, view.rot, view.s)
        G.lasso = { pts = { x, y }, cont = view.cont, eraser = true, r = G.EraserYd(), button = button, color = G.ERASER_COLOR }
        return
      end
      if button == "LeftButton" and G.stairMode then -- (the stairs tool: their foot, then their top)
        local mx, my = GetCursorPosition()
        local sc = canvas:GetEffectiveScale()
        local ccx, ccy = canvas:GetCenter()
        local x, y = G.ScreenToWorld(view.x, view.y, mx / sc - ccx, my / sc - ccy, view.rot, view.s)
        G.StairClick(G.PinLevel(x, y), x, y)
        return
      end
      -- (a road drawn by hand: Record suggested first, G.AskRecordHint; the stroke isn't started)
      if button == "LeftButton" and not G.wallMode and G.RecordHintDue() then
        G.AskRecordHint()
        return
      end
      if button == "LeftButton" or button == "RightButton" then
        local erase = button == "RightButton"
        local wall = G.wallMode
        G.lasso = { pts = {}, cont = view.cont, road = true, erase = erase, wall = wall, button = button,
          color = wall and (erase and UNWALL_COLOR or WALL_COLOR) or (erase and ERASE_COLOR or DRAW_COLOR) }
      elseif button == "MiddleButton" then
        local mx, my = GetCursorPosition()
        tour = nil
        lastActivity = GetTime()
        drag = { cx = mx, cy = my, x = view.x, y = view.y, rot = view.rot, s = view.s, moved = false, pan = true,
          land = (free ~= nil and not free.city and not free.instance and not free.cave and not G.cityMap) or nil }
      end
      return
    end
    if G.drawMode then
      if button == "RightButton" then
        G.StopDrawing()
      elseif button == "LeftButton" then
        G.lasso = { pts = {}, cont = view.cont, road = G.drawKind == "road" }
      end
      return
    end
    if button == "RightButton" then
      if G.IsMapStyle(G.Style()) then
        G.ZoomOut()
      elseif S().terrainZoomOut ~= false then
        G.TerrainZoomOut()
      end
      return
    end
    if button ~= "LeftButton" then return end
    if IsShiftKeyDown() then
      G.PinClickDown() -- (Shift + click, not dragged: "Create Pin")
      if not S().locked and not G.MinimapMode() then
        f:StartMoving()
        f.moving = true
      end
      return
    end
    local mx, my = GetCursorPosition()
    tour = nil
    lastActivity = GetTime()
    drag = { cx = mx, cy = my, x = view.x, y = view.y, rot = view.rot, s = view.s, moved = false,
      land = (free ~= nil and not free.city and not free.instance and not free.cave and not G.cityMap) or nil } -- (looking at the land: dragged, still the land)
  end)
  frame:SetScript("OnMouseUp", function(f, button)
    if button == "LeftButton" and G.pinClick then -- (Shift + left-click: "Create Pin", unless it was a drag)
      if f.moving then
        f:StopMovingOrSizing()
        f.moving = false
        SavePosition()
      end
      G.PinClickUp()
      return
    end
    if (G.roadMode or G.wallMode) and not G.drawMode then
      local l = G.lasso
      if l and button == l.button then
        G.lasso = nil
        local okF, errF
        if l.eraser then okF, errF = pcall(G.FinishEraser, l) else okF, errF = pcall(G.FinishRoad, l, l.erase, l.wall) end
        if not okF then G.LogError(l.eraser and "restoring under the eraser" or "saving a drawn road or wall", errF) end
        return
      elseif button == "MiddleButton" then
        drag = nil
        return
      end
      if not S().toolShiftClick then return end -- (Shift-click drawing: the map's own click or drag, below)
    end
    if G.drawMode then
      if button == "LeftButton" and G.lasso then G.FinishDrawing() end
      return
    end
    if f.moving then
      f:StopMovingOrSizing()
      f.moving = false
      SavePosition()
    end
    if button == "LeftButton" and drag and not drag.moved then
      local mx, my = GetCursorPosition()
      local sc = canvas:GetEffectiveScale()
      local ccx, ccy = canvas:GetCenter()
      local dx, dy = mx / sc - ccx, my / sc - ccy
      local now = GetTime()
      local m = browse and ns.Maps[browse]
      local worldMap = m and m.type <= 2 -- a click there opens a zone instead
      -- Ctrl + left-click: the map pin there (Import.SetMapPin), as on the game's world map
      local px_, py_, pc_
      -- (in the game's world map with its own map pin button pressed: a click places it, as on the game's map)
      if ((IsControlKeyDown and IsControlKeyDown()) or G.WorldMapPinning()) and not G.Held() then px_, py_, pc_ = G.ClickWorld() end
      if px_ and ns.Import and ns.Import.SetMapPin(pc_, px_, py_) then
        lastClick = nil
      elseif not worldMap and lastClick and now - lastClick.t <= DOUBLE_CLICK
          and (dx - lastClick.x) ^ 2 + (dy - lastClick.y) ^ 2 <= 100
          and not G.PadClickedJustNow() then -- (a controller's Select with the game's own click: no stop)
        lastClick = nil
        G.MapClickHook(dx, dy, true) -- (a double-click: a stop, as always)
        G.AddPending(dx, dy)
      else
        lastClick = { t = now, x = dx, y = dy }
        if worldMap or not G.MapClickHook(dx, dy, false) then
          OnMapClick(dx, dy)
          if not worldMap then
            G.CaveClick(dx, dy) -- (over a cave with a map: its map, unless a double-click)
            G.HoldInside() -- (over a building whose inside map shows: held a while)
          end
        end
      end
    end
    drag = nil
  end)
  frame:EnableMouseWheel(true)
  frame:SetScript("OnMouseWheel", function(_, delta)
    G.NoteMapUse()
    -- (the road or wall tools on, Shift held: the floor edited, where floors lie over each other)
    if (G.roadMode or G.wallMode) and IsShiftKeyDown and IsShiftKeyDown() and G.StepEditFloor(delta) then return end
    -- (the magic eraser on, Ctrl held: its size)
    if G.eraserMode and (G.roadMode or G.wallMode) and IsControlKeyDown and IsControlKeyDown() then
      G.SizeEraser(delta)
      return
    end
    tour = nil
    lastActivity = GetTime()
    G.WheelZoom(delta > 0 and 1 / G.ZOOM_STEP or G.ZOOM_STEP)
  end)
  frame:SetBackdrop({
    bgFile = "Interface\\Buttons\\WHITE8X8",
    edgeFile = "Interface\\Buttons\\WHITE8X8",
    edgeSize = BORDER,
  })
  frame:SetBackdropColor(0.05, 0.05, 0.05, 1)
  frame:SetBackdropBorderColor(0.15, 0.15, 0.15, 1)

  -- "Move" tab above the top edge while unlocked: drag it to move the frame.
  local tab = CreateFrame("Button", nil, frame, "BackdropTemplate")
  tab:SetSize(84, 18)
  tab:SetPoint("BOTTOM", frame, "TOP", 0, -1)
  tab:SetBackdrop({ bgFile = "Interface\\Buttons\\WHITE8X8", edgeFile = "Interface\\Buttons\\WHITE8X8", edgeSize = 1 })
  tab:SetBackdropColor(0.12, 0.12, 0.14, 0.95)
  tab:SetBackdropBorderColor(0.3, 0.3, 0.3, 1)
  local tabText = tab:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  tabText:SetPoint("CENTER")
  tabText:SetText(L["Move"])
  tab:RegisterForDrag("LeftButton")
  tab:SetScript("OnDragStart", function() frame:StartMoving() end)
  tab:SetScript("OnDragStop", function() frame:StopMovingOrSizing(); SavePosition() end)
  tab:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    GameTooltip:SetText(L["Drag to move the GPS"], 1, 1, 1)
    GameTooltip:AddLine(L["Lock it in the options (or /agps lock) to hide this tab."], 0.8, 0.8, 0.8, true)
    GameTooltip:Show()
  end)
  tab:SetScript("OnLeave", GameTooltip_Hide)
  G.moveTab = tab
  G.MakeSizeGrip() -- (the corner grip: G.Resizable)

  -- While unlocked: the game's own window frame (metal border, title bar, portrait, close
  -- button) around the map, from the client's PortraitFrameTemplate. A child of the map, so
  -- it takes the map's opacity. Only its border and title bar draw over the map; the map
  -- stays clickable (only the title bar and the close button take the mouse). If the
  -- template isn't there, the plain Move tab is used instead.
  local ok, chrome = pcall(CreateFrame, "Frame", nil, frame, "PortraitFrameTemplate")
  if ok and chrome and chrome.NineSlice then
    chrome:SetPoint("TOPLEFT", frame, "TOPLEFT", -2, CHROME_TITLE)
    chrome:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", 2, -2)
    chrome:SetFrameLevel(frame:GetFrameLevel() + 12 + G.ArtSpan())
    chrome:EnableMouse(false)
    if chrome.Bg then chrome.Bg:Hide() end -- the map is the window's content
    if chrome.TopTileStreaks then chrome.TopTileStreaks:Hide() end
    local strip = chrome:CreateTexture(nil, "BACKGROUND") -- behind the title only
    strip:SetPoint("TOPLEFT", 2, -2)
    strip:SetPoint("BOTTOMRIGHT", chrome, "TOPRIGHT", -2, -CHROME_TITLE)
    strip:SetColorTexture(G.TITLE_STRIP[1], G.TITLE_STRIP[2], G.TITLE_STRIP[3], 1)
    G.chromeStrip = strip -- (another addon's look may color it: G.ApplyFrameLook)
    if chrome.SetTitle then chrome:SetTitle("AzerothGPS")
    elseif chrome.TitleContainer and chrome.TitleContainer.TitleText then chrome.TitleContainer.TitleText:SetText("AzerothGPS") end
    G.CenterTitle(chrome)
    -- the AzerothGPS logo top left, on its plate or in the round portrait (ns.ApplyLogoLook); the map's
    -- top panel moves right of it while unlocked (ApplySettings); dragging the plate moves the map, as
    -- the title bar does (G.logo: its record, the plate for API.MapButton("logo"))
    G.logo = ns.SetLogoPortrait(chrome, nil, function(starting)
      if starting then
        if not S().locked then frame:StartMoving() end
      else
        frame:StopMovingOrSizing()
        SavePosition()
      end
    end)
    if chrome.CloseButton then
      chrome.CloseButton:SetScript("OnClick", function()
        if G.mmState and G.mmState.on then G.SetMinimapExpanded(false) return end -- (back to the minimap square)
        S().shown = false
        G.ApplySettings()
        ns.Print(L["map hidden: /agps show or the minimap button brings it back"])
      end)
    end
    -- a double-click on the logo minimizes the map (the user, 2026-11-09: the logo only, no title-bar button; the plate
    -- is a Frame: two clicks close together, not a drag)
    local plate = G.logo and G.logo.plate
    if plate and plate.HookScript then
      local last
      plate:HookScript("OnMouseUp", function(_, button)
        if button == "RightButton" then
          last = nil
          G.OpenOptions()
          return
        end
        if button ~= "LeftButton" then return end
        local now = GetTime()
        if last and now - last <= G.DOUBLE_CLICK then
          last = nil
          G.SetMinimized(true)
        else
          last = now
        end
      end)
      plate:HookScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_TOP")
        GameTooltip:SetText("AzerothGPS", 1, 1, 1)
        GameTooltip:AddLine(L["Double-click: minimize the map to this logo (double-click it again to bring the map back)"], 0.8, 0.8, 0.8, true)
        GameTooltip:AddLine(L["Right-click: options"], 0.8, 0.8, 0.8)
        GameTooltip:Show()
      end)
      plate:HookScript("OnLeave", GameTooltip_Hide)
    end
    -- the title bar moves the map
    local grab = CreateFrame("Frame", nil, chrome)
    grab:SetPoint("TOPLEFT", 56, 0)
    grab:SetPoint("TOPRIGHT", -26, 0)
    grab:SetHeight(CHROME_TITLE)
    grab:EnableMouse(true)
    grab:RegisterForDrag("LeftButton")
    grab:SetScript("OnDragStart", function() if not S().locked then frame:StartMoving() end end)
    grab:SetScript("OnDragStop", function() frame:StopMovingOrSizing(); SavePosition() end)
    grab:SetScript("OnEnter", function(self)
      GameTooltip:SetOwner(self, "ANCHOR_TOP")
      if S().locked then
        GameTooltip:SetText("AzerothGPS", 1, 1, 1)
        GameTooltip:AddLine(L["Locked. Unlock the map in the options (or /agps unlock map) to move it."], 0.8, 0.8, 0.8, true)
      else
        GameTooltip:SetText(L["Drag to move the GPS"], 1, 1, 1)
        GameTooltip:AddLine(L["Lock it in the options (or /agps lock map) to keep it in place."], 0.8, 0.8, 0.8, true)
      end
      GameTooltip:Show()
    end)
    grab:SetScript("OnLeave", GameTooltip_Hide)
    G.chrome = chrome
    G.ApplyFrameLook() -- (a look set before the map was made)
  end

  -- (the game's controller UI steps through the buttons of its own panels with the d-pad. No mark of ours is put on
  -- the window to keep it out of that: a value an addon sets, read by the game's own code, taints what that code
  -- does next.)
  canvas = CreateFrame("Frame", nil, frame)
  canvas:SetPoint("TOPLEFT", BORDER, -BORDER)
  canvas:SetPoint("BOTTOMRIGHT", -BORDER, BORDER)
  canvas:SetClipsChildren(true)
  if G.ArtSpan() > 0 then canvas:SetFrameLevel(frame:GetFrameLevel() + 1 + G.ArtSpan()) end

  tileLayer = CreateFrame("Frame", nil, canvas) -- the map tiles (fade while moving)
  tileLayer.agpsNoLook = true -- (no buttons to tint on the map's own layers: G.TintButtons)
  tileLayer:SetAllPoints(canvas)
  tileLayer:SetFrameLevel(canvas:GetFrameLevel() + 1)
  -- (the tiles' own layer: a pan moves it once; everything else on tileLayer stays put)
  G.quadLayer = CreateFrame("Frame", nil, tileLayer)
  G.quadLayer:SetSize(1, 1)
  G.quadLayer:SetPoint("CENTER", canvas, "CENTER", 0, 0)
  G.quadLayer:SetFrameLevel(tileLayer:GetFrameLevel())

  areaLayer = CreateFrame("Frame", nil, canvas) -- quest area outlines (DrawAreas), clipped
  areaLayer.agpsNoLook = true
  areaLayer:SetSize(1, 1)
  areaLayer:SetFrameLevel(canvas:GetFrameLevel() + 2)

  lineLayer = CreateFrame("Frame", nil, canvas) -- roads and routes, above the tiles, still clipped
  lineLayer.agpsNoLook = true
  lineLayer:SetAllPoints(canvas)
  lineLayer:SetFrameLevel(canvas:GetFrameLevel() + 2)

  poiLayer = CreateFrame("Frame", nil, canvas) -- clickable points of interest, clipped (by canvas)
  poiLayer.agpsNoLook = true
  -- (an anchor, not a box: everything on it hangs off its center, and a small pan moves it whole)
  poiLayer:SetSize(1, 1)
  poiLayer:SetPoint("CENTER", canvas, "CENTER", 0, 0)
  poiLayer:SetFrameLevel(canvas:GetFrameLevel() + 3)
  G.poiLayer = poiLayer -- (the tests check its pan)
  -- (the marks' anchor: everything placed each redraw round the view's center hangs off it — the route's
  -- lines, the stops' and rides' pins, party dots, plugin icons. At the canvas's middle at each redraw,
  -- slid between redraws by G.GlidePan. Not the icons' layer: that one carries its own pan.)
  G.markLayer = CreateFrame("Frame", nil, canvas)
  G.markLayer.agpsNoLook = true
  G.markLayer:SetSize(1, 1)
  G.markLayer:SetPoint("CENTER", canvas, "CENTER", 0, 0)

  keepLayer = CreateFrame("Frame", nil, canvas) -- stop markers (don't fade), clipped
  keepLayer:SetAllPoints(canvas)
  keepLayer:SetFrameLevel(canvas:GetFrameLevel() + 4)

  local top = CreateFrame("Frame", nil, frame) -- above the map tiles
  top:SetAllPoints(canvas)
  top:SetFrameLevel(canvas:GetFrameLevel() + 5)
  topLayer = top

  arrow = lineLayer:CreateTexture(nil, "OVERLAY", nil, 7) -- clipped: may leave the view in free mode
  arrow:SetTexture(G.ARROW_DEFAULT.texture)
  arrow.agpsTex = G.ARROW_DEFAULT.texture
  arrow:SetSize(32, 32)
  arrow:SetPoint("CENTER")
  G.ApplyArrowLook() -- (another addon's arrow, set before the map was made)

  recenter = CreateFrame("Button", nil, top)
  recenter:SetSize(28, 28)
  recenter:SetPoint("BOTTOMRIGHT", -6, 38)
  local rbg = recenter:CreateTexture(nil, "BACKGROUND")
  rbg:SetAllPoints()
  rbg:SetTexture("Interface\\Minimap\\UI-Minimap-Background")
  local ricon = recenter:CreateTexture(nil, "ARTWORK")
  ricon:SetTexture("Interface\\Minimap\\MinimapArrow")
  ricon:SetSize(24, 24)
  ricon:SetPoint("CENTER")
  recenter:SetHighlightTexture("Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight")
  recenter:SetScript("OnClick", function() G.Follow() end)
  recenter:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_LEFT")
    GameTooltip:SetText(L["Back to Your Position"], 1, 1, 1)
    GameTooltip:Show()
  end)
  recenter:SetScript("OnLeave", GameTooltip_Hide)
  recenter:Hide()

  -- Import waypoints (TomTom /way lines): bottom-right, below the recenter button.
  local import = CreateFrame("Button", nil, top)
  import:SetSize(28, 28)
  import:SetPoint("BOTTOMRIGHT", -6, 6)
  local ibg = import:CreateTexture(nil, "BACKGROUND")
  ibg:SetAllPoints()
  ibg:SetTexture("Interface\\Minimap\\UI-Minimap-Background")
  local iicon = import:CreateTexture(nil, "ARTWORK")
  iicon:SetTexture("Interface\\Buttons\\UI-PlusButton-Up")
  iicon:SetSize(18, 18)
  iicon:SetPoint("CENTER")
  import:SetHighlightTexture("Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight")
  import:SetScript("OnClick", function() ns.Import.Toggle() end)
  import:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_LEFT")
    GameTooltip:SetText(L["Import and Share"], 1, 1, 1)
    GameTooltip:AddLine(L["Paste TomTom /way lines to make them the route's stops, or copy or send your route to someone else. Copy your map data (herbs, ore, NPCs, pins, roads, walls) for other players, and import theirs."], nil, nil, nil, true)
    GameTooltip:Show()
  end)
  import:SetScript("OnLeave", GameTooltip_Hide)
  -- (for companion addons placing their own buttons: Api.lua MapButton; "logo": the window frame's logo plate, over
  -- every part of the frame (its border is at frame level 500 in the client's template), API 14)
  G.mapButtons = { recenter = recenter, import = import, logo = G.logo and G.logo.plate or nil }

  -- Map menu (bottom-left): a round button that opens the map type and the map layers.
  local STYLES = {
    { "seamless", "Interface\\Icons\\INV_Misc_Map_01", "OpenMap", L["The ground seen from above, and the mouse wheel zooms on out past the land, through zones and continents to the whole world on a stitched world map, and back in to the roads. Right-click zooms out a few steps on the same spot, up to the whole world."] },
    { "minimap", "Interface\\Icons\\INV_Misc_Map02", L["Terrain"], L["The ground seen from above, like the minimap, zoomed out only as far as the land. Right-click opens the world map to pick a place."] },
    { "zone", "Interface\\Icons\\INV_Misc_Map05", L["World Map"], L["The world map, fully explored. Right-click to zoom out to the continent; click a zone to open it."] },
    { "nospoiler", "Interface\\Icons\\INV_Misc_Map03", L["No Spoiler Map"], L["The world map as your character has explored it: undiscovered parts stay hidden. Routes still use every road."] },
  }
  local mapButton = CreateFrame("Button", nil, top)
  mapButton:SetSize(MAP_BUTTON, MAP_BUTTON)
  mapButton:SetPoint("BOTTOMLEFT", 3, 3)
  local mbIcon = mapButton:CreateTexture(nil, "ARTWORK")
  mbIcon:SetAllPoints()
  mbIcon:SetTexture("Interface\\AddOns\\AzerothGPS\\Media\\MapMenu")
  local mbGlow = mapButton:CreateTexture(nil, "HIGHLIGHT")
  mbGlow:SetAllPoints()
  mbGlow:SetTexture("Interface\\AddOns\\AzerothGPS\\Media\\MapMenu")
  mbGlow:SetBlendMode("ADD")
  mbGlow:SetAlpha(0.35)

  -- The drawer's open/closed state: an invisible frame shown while it's open (its OnUpdate
  -- closes it after MENU_IDLE seconds untouched; a click on the map closes it too). What's
  -- in it are the quick buttons put "in the menu" (G.LayoutQuick).
  local menu = CreateFrame("Frame", nil, mapButton)
  menu:SetSize(1, 1)
  menu:SetPoint("CENTER")
  menu:Hide()
  if ns.Layers then ns.Layers.Init() end
  function G.RefreshMapMenu()
    if G.RefreshQuick then G.RefreshQuick() end
  end
  menu:SetScript("OnShow", function(self) self.idle = 0 end)
  menu:SetScript("OnUpdate", function(self, dt)
    -- (kept open while the search typed in shows: Quick Search opens it with the mouse anywhere)
    if mapButton:IsMouseOver() or (G.QuickMouseOver and G.QuickMouseOver())
        or (G.searchPanel and G.searchPanel:IsShown()) then
      self.idle = 0
    else
      self.idle = (self.idle or 0) + dt
      if self.idle >= MENU_IDLE then self:Hide() end
    end
  end)
  if ns.TimeScript then ns.TimeScript(menu, "OnUpdate", "map buttons") end

  mapButton:SetScript("OnClick", function() menu:SetShown(not menu:IsShown()) end)
  mapButton:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText(L["Map Menu"], 1, 1, 1) -- (asked 2026-11-11: "Map" said nothing of what it opens)
    GameTooltip:AddLine(L["Opens the quick buttons you keep in the menu: map styles, layers, drawing a farming area and more (Options: Quick buttons). Closes after 20 seconds untouched."], nil, nil, nil, true)
    GameTooltip:Show()
  end)
  mapButton:SetScript("OnLeave", GameTooltip_Hide)
  G.mapButton, G.mapMenu = mapButton, menu

  -- (the zone under the mouse on a continent's map, beside the cursor)
  G.zoneLabel = top:CreateFontString(nil, "OVERLAY", "GameFontHighlightLarge")
  G.zoneLabel:SetJustifyH("LEFT")
  G.zoneLabel:SetShadowColor(0, 0, 0, 1)
  G.zoneLabel:SetShadowOffset(1, -1)
  G.zoneLabel:Hide()
  drawHint = top:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  G.drawHint = drawHint -- (the drawing's hint: Pad.lua's tests read it)
  -- (as wide as the map, less a margin: longer lines wrap instead of running past its edges)
  drawHint:SetPoint("TOPLEFT", top, "TOPLEFT", 14, -46)
  drawHint:SetPoint("TOPRIGHT", top, "TOPRIGHT", -14, -46)
  drawHint:SetWordWrap(true)
  drawHint:SetJustifyH("CENTER")
  drawHint:SetText(L["Drag around the nodes to farm  |cff9d9d9d(right-click cancels)|r"])
  -- (on a black band, a quarter opaque, so it reads over any map; shown and hidden with it)
  local hintBg = top:CreateTexture(nil, "ARTWORK")
  hintBg:SetColorTexture(0, 0, 0, 0.25)
  hintBg:SetPoint("TOPLEFT", drawHint, "TOPLEFT", -8, 4)
  hintBg:SetPoint("BOTTOMRIGHT", drawHint, "BOTTOMRIGHT", 8, -4)
  local show, hide = drawHint.Show, drawHint.Hide
  drawHint.Show = function(self) G.PlaceDrawHint() show(self); hintBg:Show() end
  drawHint.Hide = function(self) hide(self); hintBg:Hide() end
  drawHint:Hide()

  -- Search: a small round magnifier button above the map button
  local search = CreateFrame("Button", nil, top)
  search:SetSize(26, 26)
  search:SetPoint("BOTTOM", mapButton, "TOP", 0, 4)
  local sbg = search:CreateTexture(nil, "BACKGROUND")
  sbg:SetAllPoints()
  sbg:SetTexture("Interface\\AddOns\\AzerothGPS\\Media\\MapMenu") -- the same round frame
  sbg:SetVertexColor(0.35, 0.35, 0.35)
  local sicon = search:CreateTexture(nil, "ARTWORK")
  sicon:SetPoint("TOPLEFT", 6, -6)
  sicon:SetPoint("BOTTOMRIGHT", -6, 6)
  ns.SetIcon(sicon, "atlas:common-search-magnifyingglass", "Interface\\Icons\\INV_Misc_Spyglass_03")
  local shl = search:CreateTexture(nil, "HIGHLIGHT")
  shl:SetAllPoints()
  shl:SetTexture("Interface\\AddOns\\AzerothGPS\\Media\\MapMenu")
  shl:SetBlendMode("ADD")
  shl:SetAlpha(0.3)

  local panel = CreateFrame("Frame", nil, search, "BackdropTemplate")
  panel:SetFrameStrata("DIALOG")
  panel:SetSize(310, 36) -- (wider since the rows have a Pin button)
  panel:SetPoint("BOTTOMLEFT", search, "BOTTOMRIGHT", 6, 0)
  panel:SetBackdrop({ bgFile = "Interface\\Buttons\\WHITE8X8", edgeFile = "Interface\\Buttons\\WHITE8X8", edgeSize = 1 })
  panel:SetBackdropColor(0.05, 0.05, 0.06, 0.95)
  panel:SetBackdropBorderColor(0.3, 0.3, 0.3, 1)
  panel:EnableMouse(true)
  panel:Hide()
  local box = CreateFrame("EditBox", nil, panel, "InputBoxTemplate")
  box:SetSize(248, 20)
  box:SetPoint("TOPLEFT", 14, -8)
  box:SetAutoFocus(false)
  box:SetMaxLetters(40)
  local rows, results = {}, {}
  local function Pick(e)
    if not e then return end
    panel:Hide()
    local _, _, cont = Geo.PlayerWorld()
    local vc = ViewCont(cont)
    local mine = e.pin or e.place or e.npc -- (a pin, a city place or an NPC: maybe on a city's or dungeon's level)
    if e.cont == vc or (mine and e.cont < 20000 and vc and Geo.Base(e.cont) == Geo.Base(vc)) then -- show it there
      free = { x = e.x, y = e.y, rot = view.rot, cross = true, cont = mine and Geo.Base(e.cont) or e.cont }
      recenter:Show()
    end
    if e.pin or e.npc then -- (on the pin's level, at its height: as a double-click on it; an NPC's where it was talked to)
      G.AddStopAt(e.x, e.y, e.name, e.cont, e.tex, e.z, true)
    elseif e.place then -- (a city place: its full name, icon and floor, as a double-click on it)
      G.AddStopAt(e.x, e.y, e.place, e.cont, e.tex, e.z)
    else
      G.AddStopAt(e.x, e.y, e.name, e.cont)
    end
    ns.Print(Format(L["stop: %s (%s)"], e.name, e.sub))
  end
  G.PickSearchEntry = Pick -- (Quick Find's click: as picking a search result)
  local function Refresh()
    results = G.SearchPlaces(box:GetText(), 8)
    for i, e in ipairs(results) do
      local r = rows[i]
      if not r then
        r = CreateFrame("Button", nil, panel)
        r:SetSize(288, 18)
        r:SetPoint("TOPLEFT", 12, -32 - (i - 1) * 18)
        local hl = r:CreateTexture(nil, "HIGHLIGHT")
        hl:SetAllPoints()
        hl:SetColorTexture(1, 1, 1, 0.1)
        r.text = r:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
        r.text:SetPoint("LEFT", 4, 0)
        r.text:SetPoint("RIGHT", -4, 0)
        r.text:SetJustifyH("LEFT")
        r.text:SetWordWrap(false)
        r:SetScript("OnClick", function(self)
          -- (an NPC's row Shift-clicked: another addon's first, API.OnIconShiftClick; else a stop, as before)
          if IsShiftKeyDown and IsShiftKeyDown() and G.SearchShiftClick(self.entry) then
            panel.idle = 0
            return
          end
          Pick(self.entry)
        end)
        r:SetScript("OnEnter", function(self)
          panel.idle = 0
          local shift = G.SearchHint(self.entry)
          if not shift then return end -- (no tooltip, as before, unless another addon says what a Shift-click does)
          GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
          GameTooltip:SetText(self.entry.name, 1, 1, 1)
          GameTooltip:AddLine(Format(L["Shift-click: %s"], shift), 0.4, 0.8, 1)
          GameTooltip:Show()
        end)
        r:SetScript("OnLeave", GameTooltip_Hide)
        -- (beside an NPC or a city place: Pin, a pin there for good; asked 2026-11-14)
        local pin = CreateFrame("Button", nil, r, "UIPanelButtonTemplate")
        pin:SetHeight(16)
        pin:SetText(L["Pin"])
        pin:SetWidth(math.max(32, (pin:GetTextWidth() or 0) + 12))
        pin:SetPoint("RIGHT", r, "RIGHT", 0, 0)
        pin:SetScript("OnClick", function(self)
          panel.idle = 0
          G.PinSearchEntry(self:GetParent().entry)
        end)
        pin:SetScript("OnEnter", function(self)
          panel.idle = 0
          GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
          GameTooltip:SetText(L["Add a pin here"], 1, 1, 1)
          GameTooltip:Show()
        end)
        pin:SetScript("OnLeave", GameTooltip_Hide)
        r.pin = pin
        rows[i] = r
      end
      r.entry = e
      local pinnable = (e.npc or e.place) and not e.pin and true or false
      r.pin:SetShown(pinnable)
      r.text:SetPoint("RIGHT", pinnable and r.pin or r, pinnable and "LEFT" or "RIGHT", -4, 0)
      r.text:SetText(string.format("%s%s  |cff9d9d9d%s|r%s", e.tex and ("|T" .. e.tex .. ":14:14|t ") or "", e.name, e.sub,
        e.yd and ("  " .. ns.Nav.FormatDistance(e.yd)) or ""))
      r:Show()
    end
    for i = #results + 1, #rows do rows[i]:Hide() end
    local extra = (#results == 0 and #(box:GetText() or "") >= 2) and 18 or 0
    panel:SetHeight(36 + #results * 18 + extra)
    panel.none:SetShown(extra > 0)
  end
  panel.none = panel:CreateFontString(nil, "ARTWORK", "GameFontDisableSmall")
  panel.none:SetPoint("TOPLEFT", 16, -34)
  panel.none:SetText(L["No places by that name"]) -- (NPCs: the search button's tooltip says when they're found)
  panel.none:Hide()
  box:SetScript("OnTextChanged", function()
    panel.idle = 0 -- typing keeps it open
    Refresh()
  end)
  -- closes by itself after SEARCH_IDLE seconds without typing or the mouse over it
  panel:SetScript("OnShow", function(self) self.idle = 0 end)
  panel:SetScript("OnUpdate", function(self, dt)
    if self:IsMouseOver() or search:IsMouseOver() then
      self.idle = 0
    else
      self.idle = (self.idle or 0) + dt
      if self.idle >= SEARCH_IDLE then
        box:ClearFocus()
        self:Hide()
      end
    end
  end)
  if ns.TimeScript then ns.TimeScript(panel, "OnUpdate", "map buttons") end
  box:SetScript("OnEnterPressed", function() Pick(results[1]) end)
  box:SetScript("OnEscapePressed", function() panel:Hide() end)
  search:SetScript("OnClick", function()
    panel:SetShown(not panel:IsShown())
    if panel:IsShown() then
      box:SetText("")
      Refresh()
      box:SetFocus()
    end
  end)
  search:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText(L["Search Places"], 1, 1, 1)
    GameTooltip:AddLine(L["Type 2+ letters, then pick a place to add it as a stop (Enter takes the first)."], nil, nil, nil, true)
    -- (what it finds and the Pin button: Options > General > Search, asked 2026-11-14: "too much text for a button
    -- hover")
    GameTooltip:Show()
  end)
  search:SetScript("OnLeave", GameTooltip_Hide)
  G.searchButton, G.searchPanel = search, panel
  panel.box = box -- (the tutorial reads what's typed)
  -- (Quick Search's key, G.QuickSearch: the panel open, empty, the box taking the keys)
  G.FocusSearch = function()
    if not panel:IsShown() then
      local click = search:GetScript("OnClick")
      if click then click(search) end
    else
      box:SetText("")
      Refresh()
      box:SetFocus()
    end
    panel.idle = 0
  end
  -- (Quick Find's right-click: the panel open with `text` typed, its list shown; the game's SetText lists it already)
  G.FillSearch = function(text)
    G.FocusSearch()
    local was = results
    box:SetText(text)
    if results == was then Refresh() end
    panel.idle = 0
  end

  -- A small round button like the map button: an icon in the same frame. Returns it and
  -- its icon texture.
  local function RoundButton(size, iconPath)
    local b = CreateFrame("Button", nil, top)
    b:SetSize(size, size)
    local bg = b:CreateTexture(nil, "BACKGROUND")
    bg:SetAllPoints()
    bg:SetTexture("Interface\\AddOns\\AzerothGPS\\Media\\MapMenu") -- the same round frame
    bg:SetVertexColor(0.35, 0.35, 0.35)
    local icon = b:CreateTexture(nil, "ARTWORK")
    icon:SetPoint("TOPLEFT", 5, -5)
    icon:SetPoint("BOTTOMRIGHT", -5, 5)
    ns.SetIcon(icon, iconPath, "Interface\\Icons\\INV_Misc_QuestionMark")
    local mask = b:CreateMaskTexture()
    mask:SetAllPoints(icon)
    mask:SetTexture("Interface\\CharacterFrame\\TempPortraitAlphaMask", "CLAMPTOBLACKADDITIVE", "CLAMPTOBLACKADDITIVE")
    icon:AddMaskTexture(mask)
    local hl = b:CreateTexture(nil, "HIGHLIGHT")
    hl:SetAllPoints()
    hl:SetTexture("Interface\\AddOns\\AzerothGPS\\Media\\MapMenu")
    hl:SetBlendMode("ADD")
    hl:SetAlpha(0.3)
    b:SetScript("OnLeave", GameTooltip_Hide)
    return b, icon
  end

  -- Quest route: stops for the quest log, fastest order.
  local qr = RoundButton(26, "Interface\\Icons\\Ability_Rogue_Sprint")
  qr:SetScript("OnClick", function() G.QuestRoute() end)
  qr:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText(L["Quest Route"], 1, 1, 1)
    GameTooltip:AddLine(L["A route through your quest log: where each quest's objectives are, and where finished quests are turned in, in the fastest order. Replaces the current route."], nil, nil, nil, true)
    GameTooltip:Show()
  end)

  -- The quick buttons. Each goes on the bar (always shown, along the bottom from the map
  -- button), in the menu (a column going up from the map button, shown with its menu) or
  -- nowhere: gps.quick[id] = G.QUICK_PLACES (Options: Quick buttons). What
  -- doesn't fit on the bar at the map's size goes in the menu.
  local QUICK = {
    { id = "search", button = search, label = L["Search Places"] },
    -- (asked 2026-11-14: "a quick button above the search button that expands out for quick searches for closest
    -- common things": G.QUICK_FIND)
    { id = "quickFind", icon = G.QUICK_FIND_ICON, label = L["Quick Find"],
      tip = L["Click for the common places: repair, vendor, innkeeper and more. Pick one for a stop at the nearest."],
      action = function() G.ToggleQuickFind() end },
    { id = "questRoute", button = qr, label = L["Quest Route"] },
    { id = "rxpRoute", icon = "Interface\\Icons\\INV_Misc_Book_09", label = L["RestedXP Route"],
      tip = L["Routes to each step of your RestedXP guide in turn: the step RestedXP points at is your next stop, done when RestedXP checks it off (not by getting there), then on to the next. Click again to stop. Replaces the current route. (Shown with RestedXP Guides installed)"],
      when = function() return ns.RestedXP and ns.RestedXP.Available() end,
      isOn = function() return ns.RestedXP and ns.RestedXP.On() end,
      action = function()
        if G.mapMenu then G.mapMenu:Hide() end
        ns.RestedXP.Toggle()
      end },
    { id = "zygorRoute", icon = "Interface\\Icons\\INV_Misc_Book_11", label = L["Zygor Route"],
      tip = L["Routes to each step of your Zygor guide in turn: the place Zygor's arrow is taking you is your next stop, done when Zygor checks it off (not by getting there), then on to the next. Click again to stop. Replaces the current route. (Shown with Zygor Guides installed)"],
      when = function() return ns.Zygor and ns.Zygor.Available() end,
      isOn = function() return ns.Zygor and ns.Zygor.On() end,
      action = function()
        if G.mapMenu then G.mapMenu:Hide() end
        ns.Zygor.Toggle()
      end },
    { id = "polestarRoute", icon = "Interface\\Icons\\Spell_Arcane_StarFire", label = L["Polestar Route"],
      tip = L["Routes to each step of your Polestar guide in turn: the place Polestar's arrow is taking you is your next stop, done when Polestar checks it off (not by getting there), then on to the next. Click again to stop. Replaces the current route. (Shown with Polestar installed)"],
      when = function() return ns.Polestar and ns.Polestar.Available() end,
      isOn = function() return ns.Polestar and ns.Polestar.On() end,
      action = function()
        if G.mapMenu then G.mapMenu:Hide() end
        ns.Polestar.Toggle()
      end },
    { id = "questifyRoute", icon = "Interface\\Icons\\INV_Misc_Book_13", label = L["Questify Route"],
      tip = L["Routes to each step of your Questify guide in turn: the place Questify's arrow is taking you is your next stop, done when Questify checks it off (not by getting there), then on to the next. Click again to stop. Replaces the current route. (Shown with Questify installed)"],
      when = function() return ns.Questify and ns.Questify.Available() end,
      isOn = function() return ns.Questify and ns.Questify.On() end,
      action = function()
        if G.mapMenu then G.mapMenu:Hide() end
        ns.Questify.Toggle()
      end },
    { id = "aprRoute", icon = "Interface\\Icons\\INV_Misc_Spyglass_03", label = L["Azeroth Pilot Route"],
      tip = L["Routes to each step of your Azeroth Pilot Reloaded guide in turn: the place Azeroth Pilot's arrow points at is your next stop, done when Azeroth Pilot checks it off (not by getting there), then on to the next. Click again to stop. Replaces the current route. (Shown with Azeroth Pilot Reloaded installed)"],
      when = function() return ns.AzerothPilot and ns.AzerothPilot.Available() end,
      isOn = function() return ns.AzerothPilot and ns.AzerothPilot.On() end,
      action = function()
        if G.mapMenu then G.mapMenu:Hide() end
        ns.AzerothPilot.Toggle()
      end },
    { id = "hearth", key = "useHearthstone", icon = "Interface\\Icons\\INV_Misc_Rune_01", label = L["Use Hearthstone"],
      tip = L["A route may start with your Hearthstone when it's ready and faster."], route = true, defaultOn = true },
    { id = "quests", key = "layerQuests", icon = ns.Layers and ns.Layers.ICON and ns.Layers.ICON.objective, label = L["Quests"],
      tip = L["Your quests' objectives and turn-ins on the map."] },
    { id = "questAreas", key = "layerQuestAreas", icon = ns.Layers and ns.Layers.ICON and ns.Layers.ICON.objective,
      label = L["Quest Areas"], tip = L["The quests' areas outlined on the map, like on the minimap."], needs = "layerQuests",
      tint = { 0.45, 0.6, 1 } },
    { id = "herbs", key = "layerHerbs", icon = "Interface\\Icons\\INV_Misc_Herb_07", label = L["Herbs"], tip = L["Herb nodes you know."] },
    { id = "ore", key = "layerOre", icon = "Interface\\Icons\\INV_Ore_Copper_01", label = L["Ore"], tip = L["Ore nodes you know."] },
    { id = "nodeFind", icon = "Interface\\Icons\\INV_Misc_Spyglass_03", label = L["Find Herbs and Ore"],
      tip = L["Search your herbs and ore veins by name (Peacebloom, Copper Vein) and pick which to show on the map: the others are hidden until Show All. A farming area uses only those picked too."],
      isOn = function()
        local L = ns.Layers
        return (L.NodeFilter() ~= nil or (L.finder and L.finder:IsShown())) and true or false
      end,
      action = function()
        if G.mapMenu then G.mapMenu:Hide() end
        ns.Layers.ToggleNodeFinder()
      end,
      -- (asked 2026-11-16: with a filter on it glows like the map editing tools, its group's button too, and says so)
      glowWhen = function() return ns.Layers.NodeFilter() ~= nil end,
      warn = function()
        return ns.Layers.NodeFilter() ~= nil and L["A filter is on: only the herbs and ore you picked show on the map."] or nil
      end },
    { id = "city", key = "layerCity", icon = "Interface\\Icons\\INV_Helmet_03", label = L["City Locations"],
      tip = L["Places guards pointed out to you (trainers, bank, ...), for all your characters."], defaultOn = true },
    -- (asked 2026-11-16: "remove the boss route button ... replace it with Show Routes": on, as before, a dungeon's
    -- dotted way through; off, none of its dotted lines. A boss route is still /agps bosses)
    { id = "dungeonPaths", key = "showDungeonPaths", icon = "Interface\\Icons\\Ability_DualWield", label = L["Show Routes"],
      defaultOn = true,
      tip = L["In dungeons and raids: the dotted way through, boss by boss, and where it takes the stairs. Off: no dotted lines in there."] },
    -- (the dungeon route toggle ("dungeonRoute": G.SetDungeonRoute) is left off the map menu: this
    -- client hides the player's position in dungeons, so the route it starts never can)
    { id = "caves", key = "layerCaves", icon = CAVE_ICON, label = L["Caves"], defaultOn = true,
      tip = L["Cave and mine entrances on the map (not on a continent's map). Double-click one for a stop there."] },
    { id = "instances", key = "layerInstances", icon = INSTANCE_ICON, label = L["Dungeons and Raids"], defaultOn = true,
      tip = L["Their entrances on the map (every map style). Click one for its map, with its bosses in the usual order; right-click goes back out."] },
    { id = "roadTools", icon = "Interface\\Icons\\INV_Misc_Note_02", label = L["Road Tools"], dev = true,
      tip = L["Click to turn on, click again when done. On the map: left-drag along a road the routes miss to add it (joined to the roads it meets; where it runs along one, that road stays), right-drag over a road that isn't there to erase it (red), middle-drag to pan. Routes use your changes at once. (Shown with the road tools option, or /agps dev)"],
      isOn = function() return G.roadMode end,
      action = function()
        if G.mapMenu then G.mapMenu:Hide() end
        G.ToggleRoadMode()
      end },
    { id = "wallTools", icon = "Interface\\Icons\\Ability_Warrior_ShieldWall", label = L["Wall Tools"], wallDev = true,
      tip = L["Click to turn on, click again when done. On the map: left-drag along a wall, fence or cliff edge the routes try to walk through (blood red): routes go around it like a mountain, and roads it crosses are cut there (leave a gap for a gate; flight paths still cross it). Right-drag over walls to erase them (circle an area for all in it), middle-drag to pan. (Shown with the wall tools option)"],
      isOn = function() return G.wallMode end,
      action = function()
        if G.mapMenu then G.mapMenu:Hide() end
        G.ToggleWallMode()
      end },
    { id = "roadUndo", icon = "Interface\\Icons\\INV_Misc_PocketWatch_01", label = L["Undo"], dev = true, wallDev = true,
      tip = L["Takes back your last drawn or erased road or wall (until it's in the data). (Shown with the road or wall tools)"],
      action = function()
        if G.mapMenu then G.mapMenu:Hide() end
        ns.Record.Undo()
      end },
    -- (asked 2026-11-14: the magic eraser, Restore Zone, Restore Continent and Shift-click drawing, for either tools)
    { id = "magicEraser", icon = "Interface\\Icons\\Spell_Holy_DispelMagic", label = L["Magic Eraser"], dev = true, wallDev = true,
      tip = L["Drag a circle over your own roads or walls (the tools on) to put the map's own back there: a stroke running on past it is cut at its edge. Ctrl + mouse wheel sizes the circle, up to a few zones across. Undo puts back what it took. Click again when done. (Shown with the road or wall tools)"],
      isOn = function() return G.eraserMode and true or false end,
      action = function()
        if G.mapMenu then G.mapMenu:Hide() end
        G.ToggleEraser()
      end },
    { id = "restoreZone", icon = "Interface\\Icons\\INV_Misc_Map_01", label = L["Restore Zone"], dev = true, wallDev = true,
      tip = L["Puts the zone under the crosshair (or where you are) back as the map has it: all your changes there of the tools on, roads or walls, taken out, after asking. Undo puts them back. (Shown with the road or wall tools)"],
      action = function()
        if G.mapMenu then G.mapMenu:Hide() end
        G.RestoreZone()
      end },
    { id = "restoreContinent", icon = "Interface\\Icons\\INV_Misc_Map02", label = L["Restore Continent"], dev = true, wallDev = true,
      tip = L["Puts the whole continent in view back as the map has it: all your changes on it of the tools on, roads or walls, taken out, after asking twice. Undo puts them back. (Shown with the road or wall tools)"],
      action = function()
        if G.mapMenu then G.mapMenu:Hide() end
        G.RestoreContinent()
      end },
    { id = "shiftClick", icon = "Interface\\Icons\\INV_Misc_Gear_01", label = L["Shift-Click Drawing"], dev = true, wallDev = true,
      tip = L["On: the tools draw and erase only with Shift held (Shift + left-drag, Shift + right-drag), and a plain click or drag is the map's own: left-drag pans it, as with the tools off. (Shown with the road or wall tools)"],
      isOn = function() return S().toolShiftClick and true or false end,
      action = function()
        if G.mapMenu then G.mapMenu:Hide() end
        G.ToggleShiftClick()
      end },
    { id = "roadStairs", icon = "Interface\\Icons\\Ability_Hunter_Pathfinding", label = L["Stairs"], dev = true,
      tip = L["Draw stairs between two floors: click this, then click the stairs' foot on the map, then their top, and pick each end's height (the floors near it, or type one). Routes take them as stairs at once, and Undo takes them back. Click it again when done. (Shown with the road tools)"],
      isOn = function() return G.stairMode ~= nil end,
      action = function()
        if G.mapMenu then G.mapMenu:Hide() end
        G.SetStairMode(not G.stairMode)
      end },
    { id = "roadRecord", icon = "Interface\\Icons\\Ability_Rogue_Sprint", label = L["Record"], dev = true,
      tip = L["Record a road by walking it: opens the Record window (Record, Pause, Stop, and Stairs Start and Stairs End at a staircase's foot and top, or their key). Each walk is saved as a drawn road with where you were indoors and the rooms' names, so its floors can be worked out. Undo takes the last walk back. (Shown with the road tools)"],
      isOn = function() return ns.Record and ns.Record.rec ~= nil end,
      action = function()
        if G.mapMenu then G.mapMenu:Hide() end
        if ns.Record and ns.Record.ToggleWindow then ns.Record.ToggleWindow() end
      end },
    -- (asked 2026-11-16: routing paused, by hand: Nav.SetPaused. Shown with a route; in the menu's row going right,
    -- last, by default; while paused also on the bar at the map's bottom, without opening the menu)
    { id = "pauseRoute", icon = "Interface\\Icons\\Spell_Nature_TimeStop", label = L["Pause Routing"],
      tip = L["Stop working out and drawing the route, the stops kept: less work while you aren't following it. Again to resume, worked out from where you are. Also /agps pause."],
      when = function() return ns.Nav.dest ~= nil end,
      labelNow = function() return ns.Nav.paused and L["Resume Routing"] or L["Pause Routing"] end,
      pinWhen = function() return ns.Nav.paused ~= nil end,
      action = function()
        if G.mapMenu then G.mapMenu:Hide() end
        ns.Nav.TogglePaused()
      end },
    { id = "farm", icon = "Interface\\Icons\\INV_Misc_Shovel_01", label = L["Draw a Farming Area"],
      tip = L["Drag a loop around nodes on the map: the route visits every known node inside that's shown (herbs, ore or both), round and round (the nearest 60 at most). Right-click cancels."],
      padTip = function()
        local K = ns.Pad.ActionLabel
        return Format(L["Move the map and press %s to mark each corner of a loop around nodes, %s to undo one, and %s (or %s on the first corner) to finish: the route visits every known node inside that's shown (herbs, ore or both), round and round (the nearest 60 at most). %s cancels."],
          K("select"), K("remove"), K("menu"), K("select"), K("back"))
      end,
      action = function()
        G.mapMenu:Hide()
        G.StartDrawing()
      end },
  }
  -- the map styles: one at a time
  for i, sd in ipairs(STYLES) do
    table.insert(QUICK, 3 + i, { id = "style_" .. sd[1], style = sd[1], icon = sd[2], label = sd[3], tip = sd[4] })
  end
  G.QUICK = QUICK
  -- Where each goes: always shown or in the menu, going up or right from the map button,
  -- or hidden. (The defaults, asked 2026-10-01: the menu up and right, the tools always shown.)
  G.QUICK_PLACES = { "barUp", "barRight", "menuUp", "menuRight", "hidden" }
  -- (the questing addons' routes, shown only with their addon loaded: on the bar to the right, always shown; asked
  -- 2026-11-16 for 1.3.5, "if using RestedXP or any of the supported questing addons, these buttons are always shown by
  -- default to the right")
  G.QUICK_DEFAULT = { search = "menuUp", quickFind = "menuUp", questRoute = "menuRight", rxpRoute = "barRight", zygorRoute = "barRight", polestarRoute = "barRight", questifyRoute = "barRight", aprRoute = "barRight", hearth = "menuRight", pauseRoute = "menuRight",
    city = "hidden", dungeonsG = "menuUp", styles = "hidden", gather = "menuUp", questsG = "menuUp", mapEdit = "barUp" }
  -- Groups: one button in the bar or menu; clicked, its buttons slide out beside it (to the
  -- right from a column going up, upward from a row going right).
  G.QUICK_GROUPS = {
    { id = "styles", label = L["Map Style"], members = { "style_seamless", "style_minimap", "style_zone", "style_nospoiler" },
      tip = L["The map's look: click to choose."] },
    { id = "questsG", label = L["Quests"], members = { "quests", "questAreas" }, tip = L["Quests and quest areas on the map."] },
    { id = "dungeonsG", label = L["Caves/Dungeons/Raids"], icon = INSTANCE_ICON, members = { "caves", "instances", "dungeonPaths" },
      tip = L["Cave, dungeon and raid entrances on the map, and a route through a dungeon's bosses."] },
    { id = "gather", label = L["Herbs, Ore and Farming"], members = { "herbs", "ore", "nodeFind", "farm" },
      tip = L["Herb and ore nodes on the map, finding particular ones, and drawing a farming area."] },
    -- (asked 2026-11-14: the road and wall tools as one button, "map editing tools"; opened, the roads and walls show,
    -- closed, they're hidden; it stays open until the map goes unused for the time set: G.SetMapEditOpen)
    { id = "mapEdit", label = L["Map Editing"], icon = "Interface\\Icons\\INV_Misc_Note_02", edit = true, keep = true,
      members = { "roadTools", "wallTools", "roadUndo", "magicEraser", "restoreZone", "restoreContinent", "shiftClick",
        "roadStairs", "roadRecord" },
      tip = L["The map editing tools: roads, walls, the magic eraser and restoring, Undo, Stairs and Record. While it's open the roads and walls show on the map; it closes by itself after the map goes unused a while (Options > Tools), hiding them and turning the tools off."] },
  }
  G.GROUP_IDLE = 8 -- seconds an opened group stays open with the mouse away
  G.DRAWER_SECONDS = 0.22 -- the menu column slides open and shut like a drawer
  G.QUICK_STEP_BAR, G.QUICK_STEP_MENU = 30, 28

  function G.QuickPlace(id)
    -- (a custom search's: where its row says, the whole account's; in Quick Find, not a map menu button)
    local Sx = ns.Searches
    local row = Sx and Sx.FromQuickId(id)
    if row then
      local p = Sx.Place(row)
      return p == "quickFind" and "hidden" or p
    end
    local q = S().quick
    local v = q and q[id]
    if not v and G.groupOf then -- a group: where its first member was put before groups
      local grp = G.groupOf[id]
      if grp then v = q and q[grp.members[1].id] end
    end
    v = v or G.QUICK_DEFAULT[id] or "menuUp"
    -- (an earlier version's "bar" / "menu", with the menu opening one way)
    local right = S().drawerDir == "right"
    if v == "bar" then v = right and "barUp" or "barRight" end
    if v == "menu" then v = right and "menuRight" or "menuUp" end
    return v
  end
  function G.QuickOn(t)
    if t.isOn then return t.isOn() and true or false end
    if t.style then return G.Style() == t.style end
    if t.action then return true end
    local v = S()[t.key]
    if t.defaultOn then return v ~= false end
    return v and true or false
  end
  -- How many fit: on the bar (up to the middle, clear of Clear Route and the coordinates)
  -- and in the menu column (up to the route panel).
  -- How many fit going up (to below the route panel) and going right (to short of the
  -- bottom middle: Clear Route and the coordinates) at `size` (default: the map as it is).
  function G.QuickCapacity(size)
    local w, h = top:GetWidth(), top:GetHeight()
    if size then w, h = G.MapSize(size) end
    if not w or w < 50 then w, h = G.MapSize() end -- (not laid out yet)
    return G.QuickCapacityAt(w, h)
  end
  -- (the column going up by the height `h`, the row going right by the width `w`)
  function G.QuickCapacityAt(w, h)
    local up = math.max(0, math.floor((h - (MAP_BUTTON + 7) - 100) / G.QUICK_STEP_MENU))
    local right = math.max(0, math.floor((w / 2 - 80 - (MAP_BUTTON + 7)) / G.QUICK_STEP_BAR))
    return up, right
  end
  -- How many go up and right, always shown and in the menu together (`change`: { id,
  -- place } to try one).
  function G.QuickCounts(change)
    local up, right = 0, 0
    for _, t in ipairs(G.QuickSlots()) do
      local where = (change and change[1] == t.id) and change[2] or G.QuickPlace(t.id)
      if where == "barUp" or where == "menuUp" then up = up + 1 end
      if where == "barRight" or where == "menuRight" then right = right + 1 end
    end
    return up, right
  end
  function G.QuickFits(change, size)
    local up, right = G.QuickCounts(change)
    local cu, cr = G.QuickCapacity(size)
    return up <= cu and right <= cr
  end
  -- The smallest height and width that hold them all (in steps of 10, up to the screen's): the column going up needs
  -- the height, the row going right (along the bottom) the width. They're apart: an "Any shape" map narrower than its
  -- row grew taller for it, up to the whole screen (2026-10-06).
  function G.QuickMinSides(change)
    local up, right = G.QuickCounts(change)
    local maxH, maxW = G.SizeMax(), G.WidthMax()
    local h, w = G.SIZE_MIN, G.SIZE_MIN
    while h < maxH and (G.QuickCapacityAt(maxW, h)) < up do h = h + 10 end
    while w < maxW do
      local _, fit = G.QuickCapacityAt(w, maxH)
      if fit >= right then break end
      w = w + 10
    end
    return math.min(h, maxH), math.min(w, maxW)
  end
  -- The smallest map size (height; square: the side, both) that holds them all.
  function G.QuickMinSize(change)
    local h, w = G.QuickMinSides(change)
    if G.FreeSize() then return h end -- (any shape: the width its own, G.QuickMinWidth)
    return math.min(G.SizeMax(), math.max(h, w))
  end
  function G.QuickMinWidth(change)
    local _, w = G.QuickMinSides(change)
    return w
  end
  -- What the map would need for `change` (the Options' warning): "460", any shape "400 wide" or "460 tall".
  function G.QuickNeedText(change)
    if not G.FreeSize() then return tostring(G.QuickMinSize(change)) end
    local h, w = G.QuickMinSides(change)
    local mw, mh = G.MapSize()
    if w > mw and h > mh then return Format(L["%d wide and %d tall"], w, h) end
    if w > mw then return Format(L["%d wide"], w) end
    return Format(L["%d tall"], h)
  end
  -- A map size to use for `v`: not smaller than the quick buttons need (and say why).
  local toldAt = -100
  function G.ClampSize(v, quiet)
    local min = G.QuickMinSize()
    if v < min then
      if not quiet and GetTime() - toldAt > 3 then
        toldAt = GetTime()
        ns.Print(Format(L["The map can't be smaller than %d with your quick buttons. Move some to the menu or hide them (Options: Quick buttons) to make it smaller."], min))
      end
      return min
    end
    return v
  end
  -- An "Any shape" width to use for `w`: not narrower than the quick buttons going right need (and say why).
  function G.ClampWidth(w, quiet)
    local min = G.QuickMinWidth()
    if w < min then
      if not quiet and GetTime() - toldAt > 3 then
        toldAt = GetTime()
        ns.Print(Format(L["The map can't be narrower than %d with your quick buttons going right. Put some going up or hide them (Options: Quick buttons) to make it narrower."], min))
      end
      return min
    end
    return w
  end

  -- (a quick button's round button and its scripts; G: the custom searches' made later too, G.SyncCustomQuick)
  function G.MakeQuickButton(t)
    if t.key or t.style or t.action then
      local b, icon = RoundButton(26, t.icon)
      t.button, t.iconTex = b, icon
      b:SetScript("OnClick", function(self)
        if t.action then
          t.action()
          if t.isOn then G.RefreshQuick() end -- (its look: lit while on, gray while off)
          if t.isOn and (GameTooltip:GetOwner() == self) then self:GetScript("OnEnter")(self) end
          return
        end
        if t.style then
          if G.SetStyle(t.style) and G.mapMenu then G.mapMenu.idle = 0 end
          return
        end
        if t.needs and not S()[t.needs] then return end
        S()[t.key] = not G.QuickOn(t)
        if t.route then ns.Nav.OptionsChanged() end
        G.RefreshQuick()
        if G.mapMenu then G.mapMenu.idle = 0 end -- (a click keeps the menu open)
        if ns.Options and ns.Options.Refresh then ns.Options.Refresh() end
        elapsed = 1
        if (GameTooltip:GetOwner() == self) then self:GetScript("OnEnter")(self) end
      end)
      b:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        local on = G.QuickOn(t)
        if t.labelNow then
          GameTooltip:SetText(t.labelNow(), 1, 1, 1)
        elseif t.isOn or not (t.action or t.style) then
          GameTooltip:SetText(Format(on and L["%s: |cff40ff40on|r"] or L["%s: |cff9d9d9doff|r"], t.label), 1, 1, 1)
        elseif t.action then
          GameTooltip:SetText(t.label, 1, 1, 1)
        else
          GameTooltip:SetText(on and Format(L["%s: |cff40ff40showing|r"], t.label) or t.label, 1, 1, 1)
        end
        local tip = t.tip
        if t.padTip and ns.Pad and ns.Pad.used then tip = t.padTip() end -- (the controller in use: its buttons)
        GameTooltip:AddLine(tip, nil, nil, nil, true)
        local warn = t.warn and t.warn()
        if warn then GameTooltip:AddLine(warn, 1, 0.55, 0.2, true) end
        if t.needs and not S()[t.needs] then GameTooltip:AddLine(L["Turn Quests on first."], 1, 0.5, 0.5) end
        GameTooltip:Show()
      end)
    end
  end
  for _, t in ipairs(QUICK) do G.MakeQuickButton(t) end

  -- The slots: a button on its own, or a group's one button. G.QuickSlots() in the order
  -- set in the options (gps.quickOrder: slot ids), the rest after in the built-in order.
  local byId, SLOTS, openGroup, groupIdle = {}, {}, nil, 0
  for _, t in ipairs(QUICK) do byId[t.id] = t end
  G.groupOf = {}
  local memberOf = {}
  for _, grp in ipairs(G.QUICK_GROUPS) do
    local slot = { id = grp.id, label = grp.label, tip = grp.tip, members = {}, group = true, icon = grp.icon,
      edit = grp.edit, keep = grp.keep }
    for _, mid in ipairs(grp.members) do
      local m = byId[mid]
      if m then
        slot.members[#slot.members + 1] = m
        memberOf[mid] = slot
      end
    end
    slot.icon = slot.icon or (slot.members[1] and slot.members[1].icon)
    local b, icon = RoundButton(26, slot.icon)
    slot.button, slot.iconTex = b, icon
    b:SetScript("OnClick", function() G.ToggleGroup(slot) end)
    b:SetScript("OnEnter", function(self)
      GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
      GameTooltip:SetText(slot.label, 1, 1, 1)
      GameTooltip:AddLine(slot.tip, nil, nil, nil, true)
      local names = {}
      for _, m in ipairs(slot.members) do names[#names + 1] = m.label end
      GameTooltip:AddLine(Format(L["Click for: %s"], table.concat(names, L[", "])), 0.8, 0.8, 0.8, true)
      for _, m in ipairs(slot.members) do
        local warn = m.warn and m.warn()
        if warn then GameTooltip:AddLine(warn, 1, 0.55, 0.2, true) end
      end
      GameTooltip:Show()
    end)
    G.groupOf[grp.id] = slot
  end
  for _, t in ipairs(QUICK) do
    local grp = memberOf[t.id]
    if not grp then
      SLOTS[#SLOTS + 1] = t
    elseif not grp.added then
      grp.added = true
      SLOTS[#SLOTS + 1] = grp
    end
  end
  function G.QuickSlots()
    local rank, base = {}, {}
    for i, id in ipairs(S().quickOrder or {}) do rank[id] = i end
    -- (an order saved before Quick Find: it goes just above Search Places, asked 2026-11-14)
    if rank.search and not rank.quickFind then rank.quickFind = rank.search + 0.5 end
    local out = {}
    for i, t in ipairs(SLOTS) do
      -- (the map editing tools: their option, /agps dev)
      local shown = not (t.dev or t.wallDev or t.edit) or S().devTools
      if shown and (not t.when or t.when()) then out[#out + 1] = t end
      base[t.id] = i
    end
    local function key(t) return rank[t.id] or 1000 + base[t.id] end
    table.sort(out, function(a, b) return key(a) < key(b) end)
    return out
  end
  -- The custom searches put in the map menu (ns.Searches, Options > Quick buttons): a quick button each, made the
  -- first time it's wanted, its icon, name and tooltip as its row's now; one moved to Quick Find or removed is taken
  -- out of the buttons and the slots. Clicked: its search's top result the destination (Searches.Run).
  G.customQuickMade = {}
  function G.SyncCustomQuick()
    local Sx = ns.Searches
    local want, order = {}, {}
    for _, r in ipairs(Sx and Sx.List() or {}) do
      if Sx.Place(r) ~= "quickFind" and Sx.Shown(r) then
        local id = Sx.QuickId(r)
        want[id] = r
        order[#order + 1] = id
      end
    end
    for i = #QUICK, 1, -1 do
      local t = QUICK[i]
      if t.custom and not want[t.id] then
        if t.button then t.button:Hide() end
        table.remove(QUICK, i)
        byId[t.id] = nil
        for j = #SLOTS, 1, -1 do
          if SLOTS[j] == t then table.remove(SLOTS, j) end
        end
      end
    end
    for _, id in ipairs(order) do
      local r = want[id]
      local t = byId[id]
      if not t then
        t = G.customQuickMade[id]
        if not t then
          t = { id = id, custom = true, icon = Sx.Icon(r), label = Sx.Name(r), tip = Sx.Desc(r),
            action = function()
              if G.mapMenu then G.mapMenu:Hide() end
              local row = Sx.FromQuickId(id)
              if row then Sx.Run(row) end
            end }
          G.MakeQuickButton(t)
          G.customQuickMade[id] = t
        end
        QUICK[#QUICK + 1], SLOTS[#SLOTS + 1], byId[id] = t, t, t
      end
      t.label, t.tip, t.icon = Sx.Name(r), Sx.Desc(r), Sx.Icon(r)
      ns.SetIcon(t.iconTex, t.icon, "Interface\\Icons\\INV_Misc_QuestionMark")
    end
    if G.LayoutQuick then G.LayoutQuick() end
    if G.RefreshQuick then G.RefreshQuick() end
  end
  -- Move a slot `delta` places in the order (the options' ^ / v).
  function G.MoveSlot(id, delta)
    local ids = {}
    for i, t in ipairs(G.QuickSlots()) do ids[i] = t.id end
    for i, sid in ipairs(ids) do
      if sid == id then
        local j = i + delta
        if j >= 1 and j <= #ids then ids[i], ids[j] = ids[j], ids[i] end
        break
      end
    end
    S().quickOrder = ids
    G.LayoutQuick()
  end

  -- A group's buttons out beside its button (or back in).
  local function PlaceGroup()
    if openGroup and not openGroup.button:IsShown() then openGroup = nil end
    for _, grp in pairs(G.groupOf) do
      local open = grp == openGroup or (grp.keep and G.mapEditOpen and true or false)
      local up = grp.where == "barUp" or grp.where == "menuUp"
      for j, m in ipairs(grp.members) do
        m.button:ClearAllPoints()
        if open then
          if up then
            m.button:SetPoint("LEFT", grp.button, "RIGHT", 4 + (j - 1) * G.QUICK_STEP_BAR, 0)
          else
            m.button:SetPoint("BOTTOM", grp.button, "TOP", 0, 4 + (j - 1) * G.QUICK_STEP_MENU)
          end
          m.button:SetAlpha(1)
          m.button:SetFrameLevel(grp.button:GetFrameLevel() + 2)
          m.button:Show()
        else
          m.button:Hide()
        end
      end
    end
    if G.PlaceQuickFind then G.PlaceQuickFind() end
  end
  -- A group's flyout open (not Map Editing's): shut. True when one was (Pad.lua: B backs out of it first).
  function G.OpenGroupSlot() return openGroup end -- (Pad.lua: the menu's focus in an open group)
  function G.CloseOpenGroup()
    if not openGroup then return false end
    openGroup = nil
    PlaceGroup()
    return true
  end
  function G.ToggleGroup(slot)
    if slot.keep then return G.SetMapEditOpen(not G.mapEditOpen) end -- (Map Editing: open on its own, G.SetMapEditOpen)
    openGroup = openGroup ~= slot and slot or nil
    groupIdle = 0
    if G.mapMenu then G.mapMenu.idle = 0 end
    PlaceGroup()
  end
  -- Map Editing open or closed: open, the roads and walls shown; closed, hidden and the tools off. It stays open until
  -- the map goes unused for the time set (G.ToolsIdleTick), whatever other group opens meanwhile.
  function G.SetMapEditOpen(on)
    on = on and true or false
    G.mapEditAuto = nil -- (opened or shut by the player, or after use: theirs from now)
    local was = G.mapEditOpen and true or false
    G.mapEditOpen = on
    G.NoteMapUse()
    if on ~= was then
      local st = S()
      st.showRoads, st.showWalls = on, on
      if not on then
        if G.roadMode then G.SetRoadMode(false) end
        if G.wallMode then G.SetWallMode(false) end
      end
      if ns.Options and ns.Options.Refresh then pcall(ns.Options.Refresh) end
      G.Redraw()
    end
    PlaceGroup()
    if G.RefreshQuick then G.RefreshQuick() end
    return on
  end
  local groupDriver = CreateFrame("Frame", nil, top)
  groupDriver:SetScript("OnUpdate", function(_, dt)
    if not openGroup then return end
    local over = openGroup.button:IsMouseOver()
    for _, m in ipairs(openGroup.members) do over = over or (m.button:IsShown() and m.button:IsMouseOver()) end
    groupIdle = over and 0 or groupIdle + dt
    if over and G.mapMenu then G.mapMenu.idle = 0 end
    if groupIdle >= G.GROUP_IDLE or not openGroup.button:IsShown() then
      openGroup = nil
      PlaceGroup()
    end
  end)
  if ns.TimeScript then ns.TimeScript(groupDriver, "OnUpdate", "map buttons") end

  -- Quick Find's flyout (asked 2026-11-14): a round button for each of G.QuickFindEntries() out beside it, as a
  -- group's (right of a column going up, up from a row going right); Ammo's own (Arrows, Bullets; asked 2026-11-14:
  -- "that button should pop out again") out from Ammo the other way. Shut after GROUP_IDLE untouched, or with it.
  G.quickFindButtons = {}
  do
    -- (an entry's button, by its kind (a custom search's "cs:" id): made the first time it's shown, its icon and what
    -- it does the entry's as last placed, `view`, as the player may have changed it since)
    local function Make(e)
      local b, icon = RoundButton(26, G.QuickFindIcon(e))
      b.qfIcon, b.view = icon, e
      b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
      b:SetScript("OnClick", function(self, mouse)
        if mouse == "RightButton" then G.QuickFindSearch(self.view) else G.QuickFindClick(self.view) end
      end)
      b:SetScript("OnEnter", function(self)
        local v = self.view
        G.quickFindIdle = 0
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetText(v.label, 1, 1, 1)
        GameTooltip:AddLine(v.desc or (v.sub and L["Click for arrows or bullets. Right-click: the search, nearest first."]
          or L["Click: a stop at the nearest. Right-click: the search, nearest first."]), nil, nil, nil, true)
        GameTooltip:Show()
      end)
      b:Hide()
      G.quickFindButtons[e.kind] = b
      for _, s in ipairs(e.sub or {}) do Make(s) end
      return b
    end
    function G.QuickFindButton(e)
      local b = G.quickFindButtons[e.kind] or Make(e)
      b.view = e
      ns.SetIcon(b.qfIcon, G.QuickFindIcon(e), "Interface\\Icons\\INV_Misc_QuestionMark")
      return b
    end
    for _, e in ipairs(G.QUICK_FIND) do Make(e) end
    local d = CreateFrame("Frame", nil, top)
    d:SetScript("OnUpdate", function(_, dt)
      if not G.quickFindOpen then return end
      local b = byId.quickFind.button
      local over = b:IsMouseOver() or G.QuickFindMouseOver()
      G.quickFindIdle = over and 0 or (G.quickFindIdle or 0) + dt
      if over and G.mapMenu then G.mapMenu.idle = 0 end
      if G.quickFindIdle >= G.GROUP_IDLE or not b:IsShown() then G.SetQuickFindOpen(false) end
    end)
    if ns.TimeScript then ns.TimeScript(d, "OnUpdate", "map buttons") end
    G.quickFindDriver = d
  end
  function G.QuickFindMouseOver()
    for _, b in pairs(G.quickFindButtons) do
      if b:IsShown() and b:IsMouseOver() then return true end
    end
    return false
  end
  function G.PlaceQuickFind()
    local t = byId.quickFind
    if not (G.quickFindOpen and t.button:IsShown()) then G.quickFindOpen, G.quickFindSub = false, nil end
    for _, b in pairs(G.quickFindButtons) do b:Hide() end
    if not G.quickFindOpen then return end
    local function lay(list, from, sideways)
      for j, e in ipairs(list) do
        local b = G.QuickFindButton(e)
        b:ClearAllPoints()
        if sideways then
          b:SetPoint("LEFT", from, "RIGHT", 4 + (j - 1) * G.QUICK_STEP_BAR, 0)
        else
          b:SetPoint("BOTTOM", from, "TOP", 0, 4 + (j - 1) * G.QUICK_STEP_MENU)
        end
        b:SetAlpha(1)
        b:SetFrameLevel(t.button:GetFrameLevel() + 2)
        b:Show()
      end
    end
    local up = t.where == "barUp" or t.where == "menuUp"
    lay(G.QuickFindEntries(), t.button, up)
    local s = G.quickFindSub
    if s then lay(s.sub, G.quickFindButtons[s.kind], not up) end
  end

  -- on/off look of the toggles (a group's: its active map style, or lit when any is on)
  -- The buttons whose on or off is another addon's or another place's (RestedXP's, Zygor's, Polestar's and Questify's
  -- routes, a guide turned off there or by /agps): looked at twice a second, their look refreshed when one changed
  -- (asked 2026-11-16 for 1.3.5: "restedxp icon use to fade to grey when off, doesn't now")
  G.QUICK_WATCH_SECONDS = 0.5
  function G.WatchQuickOn()
    local now = GetTime()
    if G.quickWatchAt and now - G.quickWatchAt < G.QUICK_WATCH_SECONDS then return end
    G.quickWatchAt = now
    local sig, shown = {}, {}
    for _, t in ipairs(QUICK) do
      if t.isOn then sig[#sig + 1] = G.QuickOn(t) and "1" or "0" end
      -- (and a button shown only with a route, or pinned while paused: laid out again when that changes)
      if t.pinWhen then shown[#shown + 1] = ((not t.when or t.when()) and "1" or "0") .. (t.pinWhen() and "1" or "0") end
    end
    sig = table.concat(sig)
    shown = table.concat(shown)
    if shown ~= G.quickShownSig then
      G.quickShownSig = shown
      if G.LayoutQuick then G.LayoutQuick() end
    end
    if sig ~= G.quickWatchSig then
      G.quickWatchSig = sig
      G.RefreshQuick()
    end
  end
  function G.RefreshQuick()
    for _, t in ipairs(QUICK) do
      if t.iconTex then
        local on = G.QuickOn(t) and (not t.needs or S()[t.needs])
        t.iconTex:SetDesaturated(not on)
        t.iconTex:SetAlpha(on and 1 or 0.45)
        if t.tint and on then t.iconTex:SetVertexColor(t.tint[1], t.tint[2], t.tint[3]) else t.iconTex:SetVertexColor(1, 1, 1) end
      end
    end
    for _, grp in pairs(G.groupOf or {}) do
      local any, icon = false, grp.icon
      for _, m in ipairs(grp.members) do
        if m.style then
          if G.QuickOn(m) then icon, any = m.icon, true end
        elseif m.key and G.QuickOn(m) and (not m.needs or S()[m.needs]) then
          any = true
        end
      end
      ns.SetIcon(grp.iconTex, icon, "Interface\\Icons\\INV_Misc_QuestionMark")
      grp.iconTex:SetDesaturated(not any)
      grp.iconTex:SetAlpha(any and 1 or 0.6)
    end
    G.RefreshEditGlow()
  end
  -- Road Tools and Wall Tools glow while Map Editing is open with neither on (asked 2026-11-14: "make road and wall
  -- tools glow when neither is enabled and map editor is expanded"): a gold ring round each, pulsing.
  G.EDIT_GLOW = { "roadTools", "wallTools" }
  G.EDIT_GLOW_COLOR = { 1, 0.82, 0.1 }
  G.EDIT_GLOW_HZ = 1.2 -- pulses a second
  function G.EditGlowWanted()
    return (G.mapEditOpen and not G.roadMode and not G.wallMode) and true or false
  end
  local glowDriver
  -- (and any button whose glowWhen says so: Find Herbs and Ore with a filter on; a group's button glows for its members)
  function G.GlowingIds()
    local out, edit = {}, G.EditGlowWanted()
    if edit then for _, id in ipairs(G.EDIT_GLOW) do out[id] = true end end
    for _, t in ipairs(QUICK) do
      if t.glowWhen and t.glowWhen() then out[t.id] = true end
    end
    for gid, grp in pairs(G.groupOf or {}) do
      for _, m in ipairs(grp.members) do
        if m.glowWhen and out[m.id] then out[gid] = true end
      end
    end
    return out
  end
  function G.RefreshEditGlow()
    local want = G.GlowingIds()
    local glowing = {}
    for _, t in ipairs(QUICK) do glowing[#glowing + 1] = t end
    for _, grp in pairs(G.groupOf or {}) do glowing[#glowing + 1] = grp end
    local any = next(want) ~= nil
    for _, t in ipairs(glowing) do
      local on = want[t.id] or false
      if t.button then
        if on and not t.glow then
          local g = t.button:CreateTexture(nil, "OVERLAY")
          g:SetPoint("CENTER")
          g:SetSize(t.button:GetWidth() * 1.45, t.button:GetHeight() * 1.45)
          g:SetTexture("Interface\\AddOns\\AzerothGPS\\Media\\MapMenu")
          g:SetBlendMode("ADD")
          local c = G.EDIT_GLOW_COLOR
          g:SetVertexColor(c[1], c[2], c[3])
          t.glow = g
        end
        if t.glow then t.glow:SetShown(on) end
      end
    end
    if any and not glowDriver then
      glowDriver = CreateFrame("Frame", nil, top)
      glowDriver:SetScript("OnUpdate", function()
        local a = 0.55 + 0.4 * math.sin((GetTime() or 0) * G.EDIT_GLOW_HZ * 2 * math.pi)
        for _, t in ipairs(glowing) do
          if t.glow and t.glow:IsShown() then t.glow:SetAlpha(a) end
        end
      end)
    end
    if glowDriver then glowDriver:SetShown(any) end
  end

  -- The menu column opens like a drawer: the buttons slide up out of the map button (and
  -- fade in), and back into it when it closes. drawer: 0 shut .. 1 open.
  local drawer, drawerTarget, colList = 0, 0, {}
  local menuUp, menuRight, pinnedUp, pinnedRight = {}, {}, 0, 0
  local function PlaceColumn()
    local e = drawer * drawer * (3 - 2 * drawer) -- eased
    local function place(list, pinned, up)
      for j, b in ipairs(list) do
        if drawer <= 0 then
          b:Hide()
        else
          local k = pinned + (j - 1) * e -- slides out from just past the always-shown ones
          b:ClearAllPoints()
          if up then
            b:SetPoint("BOTTOM", mapButton, "TOP", 0, 4 + k * G.QUICK_STEP_MENU)
          else
            b:SetPoint("LEFT", mapButton, "RIGHT", 4 + k * G.QUICK_STEP_BAR, 0)
          end
          b:SetAlpha(math.min(1, e * 1.5))
          b:Show()
        end
      end
    end
    place(menuUp, pinnedUp, true)
    place(menuRight, pinnedRight, false)
  end
  local driver = CreateFrame("Frame", nil, top)
  driver:SetScript("OnUpdate", function(_, dt)
    if drawer == drawerTarget then return end
    local step = dt / G.DRAWER_SECONDS
    if drawerTarget > drawer then drawer = math.min(drawerTarget, drawer + step) else drawer = math.max(drawerTarget, drawer - step) end
    PlaceColumn()
  end)
  if ns.TimeScript then ns.TimeScript(driver, "OnUpdate", "map buttons") end

  -- Place the buttons: the bar, and the column (the drawer) while the menu is open.
  function G.LayoutQuick()
    local capUp, capRight = G.QuickCapacity()
    local lists = { barUp = {}, barRight = {}, menuUp = {}, menuRight = {} }
    for _, t in ipairs(QUICK) do t.button:Hide() end
    for _, grp in pairs(G.groupOf) do grp.button:Hide() end -- (a group not shown any more: Map Editing's option off)
    for _, t in ipairs(G.QuickSlots()) do
      local where = G.QuickPlace(t.id)
      if t.pinWhen and t.pinWhen() then where = "barRight" end -- (Pause Routing while paused: on the bar)
      t.where = where
      if lists[where] then lists[where][#lists[where] + 1] = t end
      t.button:Hide()
    end
    -- always shown first (next to the map button); what doesn't fit isn't shown
    local function pin(list, up, cap)
      local n = 0
      for i, t in ipairs(list) do
        if i <= cap then
          t.button:ClearAllPoints()
          if up then
            t.button:SetPoint("BOTTOM", mapButton, "TOP", 0, 4 + (i - 1) * G.QUICK_STEP_MENU)
          else
            t.button:SetPoint("LEFT", mapButton, "RIGHT", 4 + (i - 1) * G.QUICK_STEP_BAR, 0)
          end
          t.button:SetAlpha(1)
          t.button:Show()
          n = i
        end
      end
      return n
    end
    pinnedUp = pin(lists.barUp, true, capUp)
    pinnedRight = pin(lists.barRight, false, capRight)
    menuUp, menuRight, colList = {}, {}, {}
    for i, t in ipairs(lists.menuUp) do
      if pinnedUp + i <= capUp then menuUp[#menuUp + 1] = t.button colList[#colList + 1] = t.button end
    end
    for i, t in ipairs(lists.menuRight) do
      if pinnedRight + i <= capRight then menuRight[#menuRight + 1] = t.button colList[#colList + 1] = t.button end
    end
    drawerTarget = menu:IsShown() and 1 or 0
    PlaceColumn()
    PlaceGroup()
    -- the search box: upward from the bar, to the right from the column
    panel:ClearAllPoints()
    local across = QUICK[1].where == "barRight" or QUICK[1].where == "menuRight" -- going right: open above
    if across then
      panel:SetPoint("BOTTOMLEFT", search, "TOPLEFT", 0, 4)
    else
      panel:SetPoint("BOTTOMLEFT", search, "BOTTOMRIGHT", 6, 0)
    end
    if not search:IsShown() then panel:Hide() end
    G.RefreshQuick()
  end
  function G.QuickMouseOver()
    if drawer <= 0 then return false end
    for _, b in ipairs(colList) do
      if b:IsShown() and b:IsMouseOver() then return true end
    end
    for _, m in ipairs(openGroup and openGroup.members or {}) do
      if m.button:IsShown() and m.button:IsMouseOver() then return true end
    end
    return G.QuickFindMouseOver()
  end
  -- The room on the map's left for the controller's buttons (Pad.UpdateBox; asked 2026-11-16, a box drawn below the
  -- directions and above the bottom-left map menu buttons): under the top panel, over the map menu button and the
  -- quick buttons always shown going up from it, along the left edge. Returns the frame it's in, its x and y (from that
  -- frame's top left), its width and the height there is; nil without a layout yet.
  G.PAD_BOX_GAP = 6
  function G.PadBoxRoom()
    local tt, tb = top:GetTop(), top:GetBottom()
    if type(tt) ~= "number" or type(tb) ~= "number" then return nil end
    local y = -G.PAD_BOX_GAP - 2
    if G.NavOnMap() then
      local nb = navPanel:GetBottom()
      if type(nb) == "number" then y = math.min(y, math.floor(nb - tt - G.PAD_BOX_GAP)) end
    end
    -- (under the window's corner logo too, where it hangs over the map: asked 2026-11-16, "need to move this down just
    -- a bit")
    local plate = G.logo and G.logo.plate
    if plate and plate.IsShown and plate:IsShown() then
      local lb = plate:GetBottom()
      if type(lb) == "number" and lb < tt then y = math.min(y, math.floor(lb - tt - G.PAD_BOX_GAP)) end
    end
    local column = 3 + MAP_BUTTON + 4 + pinnedUp * G.QUICK_STEP_MENU -- (up from the map's bottom)
    local h = math.floor((tt - tb) + y - column - G.PAD_BOX_GAP)
    local w = math.max(110, math.min(170, math.floor((top:GetWidth() or 0) * 0.12)))
    return top, G.PAD_BOX_GAP, y, w, h
  end
  menu:HookScript("OnShow", G.LayoutQuick)
  menu:HookScript("OnHide", G.LayoutQuick)
  top:HookScript("OnSizeChanged", G.LayoutQuick)
  G.RefreshHearthButton = G.LayoutQuick -- (ApplySettings calls this)
  G.RefreshTray = G.RefreshQuick
  G.LayoutQuick()
  G.SyncCustomQuick() -- (the custom searches in the map menu, ns.Searches)

  -- Free look: crosshair and Route Here.
  crossH = lineLayer:CreateTexture(nil, "OVERLAY", nil, 6)
  crossH:SetColorTexture(1, 1, 1, 0.85)
  crossH:SetSize(18, 2)
  crossH:SetPoint("CENTER")
  crossV = lineLayer:CreateTexture(nil, "OVERLAY", nil, 6)
  crossV:SetColorTexture(1, 1, 1, 0.85)
  crossV:SetSize(2, 18)
  crossV:SetPoint("CENTER")
  routeBtn = CreateFrame("Button", nil, top, "UIPanelButtonTemplate")
  G.confirmRouteBtn = routeBtn -- (a controller's Select presses it while it shows: Pad.ClickAt)
  routeBtn:SetSize(128, 22)
  routeBtn:SetPoint("BOTTOM", 0, 22)
  routeBtn:SetText(L["Confirm Route"])
  routeBtn:SetScript("OnClick", function()
    if not G.ClearRoute() then
      G.ConfirmRoute()
    end
  end)
  routeBtn:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    if #ns.Nav.stops > 0 then
      GameTooltip:SetText(L["Clear Route"], 1, 1, 1)
      GameTooltip:AddLine(L["Removes the route and all its stops. To add a stop instead, double-click the map; right-click a stop's marker to remove just that one."], nil, nil, nil, true)
    else
      GameTooltip:SetText(L["Confirm Route"], 1, 1, 1)
      GameTooltip:AddLine(L["Routes to the crosshair, or through the stops you double-clicked (each gets its own marker). With stops placed, the route also starts by itself after 5 seconds without touching the map."], nil, nil, nil, true)
    end
    GameTooltip:Show()
  end)
  routeBtn:SetScript("OnLeave", GameTooltip_Hide)
  G.routeButton = routeBtn -- (the tutorial points at it)

  -- Navigation panel (top): distance and ETAs; click the X to cancel the route.
  navPanel = CreateFrame("Frame", nil, top, "BackdropTemplate")
  if G.mapButtons then G.mapButtons.toppanel = navPanel end -- (API.MapButton("toppanel"): a companion's panel goes under it)
  navPanel:SetPoint("TOPLEFT", 4, -4)
  navPanel:SetPoint("TOPRIGHT", -4, -4)
  navPanel:SetHeight(36)
  navPanel:SetBackdrop({ bgFile = "Interface\\Buttons\\WHITE8X8" })
  navPanel:SetBackdropColor(0, 0, 0, 0.7)
  G.navPanel, G.navHome = navPanel, top -- (its width, side and detaching: G.PlaceNavPanel, G.ApplyNavDetach)
  -- (detached, its own window: dragged anywhere; on the map it takes no mouse, so the map under it still drags)
  navPanel:SetMovable(true)
  navPanel:SetClampedToScreen(true)
  navPanel:RegisterForDrag("LeftButton")
  navPanel:SetScript("OnDragStart", function(self)
    if G.navDetached and not G.NavLocked() then
      G.navMoving = true
      self:StartMoving()
    end
  end)
  navPanel:SetScript("OnDragStop", function(self)
    self:StopMovingOrSizing()
    G.navMoving = nil
    if G.navDetached then G.SaveNavPoint() end
  end)
  -- (detached: a right-click puts it back on the map, the way back with its buttons hidden; said on the mouse over then)
  navPanel:SetScript("OnMouseUp", function(_, button)
    if button == "RightButton" and G.navDetached and not G.NavLocked() then
      GameTooltip_Hide()
      G.SetNavDetached(false)
    end
  end)
  navPanel:SetScript("OnEnter", function(self)
    G.NavHover(true)
    if not G.NavBare() then return end
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    GameTooltip:SetText(L["Route panel"], 1, 1, 1)
    if G.NavLocked() then
      GameTooltip:AddLine(L["Locked. To unlock it: Options > Map window > Lock the panel."], nil, nil, nil, true)
    else
      GameTooltip:AddLine(L["Drag to move it. Right-click to put it back on the map."], nil, nil, nil, true)
    end
    GameTooltip:Show()
  end)
  navPanel:SetScript("OnLeave", function()
    G.NavHover(false)
    GameTooltip_Hide()
  end)
  navPanel:EnableMouse(false)
  navText = navPanel:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  navText:SetPoint("TOPLEFT", 6, -6)
  navText:SetPoint("TOPRIGHT", -58, -6) -- (clear of the X and the Detach button, and a steps box beside them)
  navText:SetJustifyH("LEFT")
  G.navText = navText -- (the tests)
  -- (a line's width in the panel's font, to cut a sized panel's long lines: G.TextWidth; never shown)
  G.navMeasure = navPanel:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  G.navMeasure:Hide()
  -- The route's steps (several stops, zeppelins, boats): the first three, then "... more".
  stepsText = navPanel:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  stepsText:SetPoint("TOPLEFT", navText, "BOTTOMLEFT", 0, -4)
  stepsText:SetPoint("RIGHT", -32, 0) -- (clear of the use button)
  G.MakeUseButton(navPanel)
  stepsText:SetJustifyH("LEFT")
  stepsText:SetSpacing(G.NAV_STEPS_SPACING)
  G.stepsText = stepsText -- (the tests)
  local cancel = CreateFrame("Button", nil, navPanel, "UIPanelCloseButton")
  cancel.agpsClose = true -- (an X: the look's close color, G.TintButtons)
  G.navCancel = cancel -- (the tutorial points at it)
  cancel:SetSize(22, 22)
  cancel:SetPoint("TOPRIGHT", 0, -1)
  -- X: closes this panel, the route goes on (option: clears the route instead)
  cancel:SetScript("OnClick", function()
    if S().navCloseClears then
      ns.Nav.Clear()
    else
      navClosedAt = ns.Nav.Version()
    end
    elapsed = 1
  end)
  cancel:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    if S().navCloseClears then
      GameTooltip:SetText(L["Cancel the Route"], 1, 1, 1)
    else
      GameTooltip:SetText(L["Close"], 1, 1, 1)
      GameTooltip:AddLine(L["Hides this panel; the route goes on. It comes back when the route changes. To cancel the route: Clear Route, or /agps clear."], nil, nil, nil, true)
    end
    GameTooltip:Show()
  end)
  cancel:SetScript("OnLeave", GameTooltip_Hide)
  -- collapse / expand the steps: "-" hides them (then "+" brings them back), and "+" beside
  -- it shows all of them, not just the next few
  -- (drawn here: small gold-edged boxes, not game art that may be missing)
  local function SmallBox(anchor, text)
    local b = CreateFrame("Button", nil, navPanel)
    b:SetSize(16, 16)
    b:SetPoint("RIGHT", anchor, "LEFT", -2, 0)
    local edge = b:CreateTexture(nil, "BACKGROUND")
    edge:SetAllPoints()
    edge:SetColorTexture(1, 0.82, 0, 0.6)
    local fill = b:CreateTexture(nil, "BORDER")
    fill:SetPoint("TOPLEFT", 1, -1)
    fill:SetPoint("BOTTOMRIGHT", -1, 1)
    fill:SetColorTexture(0.12, 0.07, 0.03, 1)
    local hover = b:CreateTexture(nil, "HIGHLIGHT")
    hover:SetAllPoints(fill)
    hover:SetColorTexture(1, 1, 1, 0.15)
    b.label = b:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    b.label:SetPoint("CENTER", 0, 1)
    b.label:SetText(text)
    b:SetScript("OnLeave", GameTooltip_Hide)
    b:Hide()
    return b
  end
  -- (asked 2026-11-18) Detach: the panel in its own window, kept open with the map closed; on it, Attach puts it back.
  -- Drawn: a small window with a corner arrow out of it (no game art that may be missing).
  local detach = SmallBox(cancel, "")
  do
    local box = detach:CreateTexture(nil, "ARTWORK")
    box:SetSize(8, 7)
    box:SetPoint("BOTTOMLEFT", 3, 3)
    box:SetColorTexture(1, 0.82, 0, 0.9)
    local hole = detach:CreateTexture(nil, "ARTWORK", nil, 1)
    hole:SetPoint("TOPLEFT", box, "TOPLEFT", 1, -2)
    hole:SetPoint("BOTTOMRIGHT", box, "BOTTOMRIGHT", -1, 1)
    hole:SetColorTexture(0.12, 0.07, 0.03, 1)
    local out = detach:CreateTexture(nil, "ARTWORK", nil, 2)
    out:SetSize(5, 5)
    out:SetPoint("TOPRIGHT", -3, -3)
    out:SetColorTexture(1, 0.82, 0, 0.9)
    detach.glyph = { box, hole, out }
  end
  detach:SetScript("OnClick", function() G.SetNavDetached(not G.navDetached) end)
  detach:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    if G.navDetached then
      GameTooltip:SetText(L["Attach to Map"], 1, 1, 1)
      GameTooltip:AddLine(L["Puts this panel back at the top of the map."], nil, nil, nil, true)
    else
      GameTooltip:SetText(L["Detach Panel"], 1, 1, 1)
      GameTooltip:AddLine(L["Shows this panel in its own window you can drag anywhere. It stays open while the map is closed or minimized, as long as you have a route."], nil, nil, nil, true)
    end
    GameTooltip:Show()
  end)
  detach:Show()
  G.navDetach = detach
  -- (asked 2026-11-18) Lock: detached, kept where it is (no dragging or sizing); a drawn padlock, open or closed.
  local lock = SmallBox(detach, "")
  do
    local body = lock:CreateTexture(nil, "ARTWORK")
    body:SetSize(8, 6)
    body:SetPoint("BOTTOM", 0, 3)
    body:SetColorTexture(1, 0.82, 0, 0.9)
    local top = lock:CreateTexture(nil, "ARTWORK")
    top:SetSize(6, 1)
    top:SetPoint("BOTTOM", body, "TOP", 0, 3)
    top:SetColorTexture(1, 0.82, 0, 0.9)
    local left = lock:CreateTexture(nil, "ARTWORK")
    left:SetSize(1, 3)
    left:SetPoint("BOTTOMLEFT", body, "TOPLEFT", 1, 0)
    left:SetColorTexture(1, 0.82, 0, 0.9)
    local right = lock:CreateTexture(nil, "ARTWORK")
    right:SetColorTexture(1, 0.82, 0, 0.9)
    lock.glyph = { body = body, top = top, shackleL = left, shackleR = right }
    G.SetLockGlyph(lock, false)
  end
  lock:SetScript("OnClick", function() G.SetNavLocked(not G.NavLocked()) end)
  lock:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    if G.NavLocked() then
      GameTooltip:SetText(L["Unlock Panel"], 1, 1, 1)
      GameTooltip:AddLine(L["Lets you drag and resize this panel again."], nil, nil, nil, true)
    else
      GameTooltip:SetText(L["Lock Panel"], 1, 1, 1)
      GameTooltip:AddLine(L["Keeps this panel where it is: no dragging or resizing."], nil, nil, nil, true)
    end
    GameTooltip:Show()
  end)
  G.navLock = lock
  -- (the panel's width, dragged by its free edge: the right one, the left one while it's on the right)
  local edge = CreateFrame("Button", nil, navPanel)
  edge:SetWidth(G.NAV_EDGE_W)
  edge:SetFrameLevel(navPanel:GetFrameLevel() + 6)
  local edgeHi = edge:CreateTexture(nil, "HIGHLIGHT")
  edgeHi:SetAllPoints()
  edgeHi:SetColorTexture(1, 0.82, 0, 0.35)
  edge:SetScript("OnMouseDown", function(self, button)
    if button ~= "LeftButton" or G.navDetached then return end
    local x = GetCursorPosition()
    self.drag = { x = x / (navPanel:GetEffectiveScale() or 1), w = navPanel:GetWidth() or 0 }
  end)
  edge:SetScript("OnMouseUp", function(self)
    if self.drag then
      self.drag = nil
      if ns.Options and ns.Options.Refresh then ns.Options.Refresh() end
    end
  end)
  edge:SetScript("OnUpdate", function(self)
    local d = self.drag
    if not d then return end
    local x = GetCursorPosition() / (navPanel:GetEffectiveScale() or 1)
    G.DragNavEdge(d.w, x - d.x)
  end)
  edge:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    GameTooltip:SetText(L["Drag to change the panel's width"], 1, 1, 1)
    GameTooltip:Show()
  end)
  edge:SetScript("OnLeave", GameTooltip_Hide)
  G.navEdge = edge
  -- (detached: its bottom-right corner sizes it, the directions' grip; with its buttons hidden, seen under the mouse)
  local grip = CreateFrame("Button", nil, navPanel)
  grip:SetSize(14, 14)
  grip:SetPoint("BOTTOMRIGHT", -1, 1)
  grip:SetFrameLevel(navPanel:GetFrameLevel() + 8)
  grip:SetNormalTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Up")
  grip:SetHighlightTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Highlight")
  grip:SetPushedTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Down")
  grip:SetScript("OnMouseDown", function(self, button)
    if button ~= "LeftButton" or not G.navDetached or G.NavLocked() then return end
    -- (kept by its top-left corner while it's sized: the corner dragged follows the mouse)
    G.SaveNavPoint()
    local l, t = navPanel:GetLeft(), navPanel:GetTop()
    if l and t then
      navPanel:ClearAllPoints()
      navPanel:SetPoint("TOPLEFT", UIParent, "BOTTOMLEFT", l, t)
    end
    local es = navPanel:GetEffectiveScale() or 1
    local x, y = GetCursorPosition()
    self.drag = { x = x / es, y = (y or 0) / es, w = navPanel:GetWidth() or 0, h = navPanel:GetHeight() or 0 }
  end)
  grip:SetScript("OnMouseUp", function(self)
    self.drag = nil
  end)
  grip:SetScript("OnUpdate", function(self)
    local d = self.drag
    if not d then return end
    local es = navPanel:GetEffectiveScale() or 1
    local x, y = GetCursorPosition()
    G.SizeNavDetached(d.w + (x / es - d.x), d.h - ((y or 0) / es - d.y))
  end)
  grip:SetScript("OnEnter", function(self)
    G.NavHover(true)
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    GameTooltip:SetText(L["Drag to resize the panel"], 1, 1, 1)
    GameTooltip:Show()
  end)
  grip:SetScript("OnLeave", function()
    G.NavHover(false)
    GameTooltip_Hide()
  end)
  grip:Hide()
  G.navGrip = grip
  top:HookScript("OnSizeChanged", function() G.PlaceNavPanel() end) -- (a share of the map's width: kept as it's sized)
  -- (sized by its corner, its size settling, as after a /reload: its text fitted again)
  navPanel:HookScript("OnSizeChanged", function()
    if G.NavFixed() then G.NavRefitSoon() end
  end)
  local toggle = SmallBox(detach, "-") -- (left of the lock while it shows: G.UpdateNavPanel)
  toggle:SetScript("OnClick", function()
    local st = S()
    if st.stepsCollapsed then st.stepsCollapsed = false -- "+": back to the next few
    elseif st.stepsAll then st.stepsAll = false -- all of them: back to the next few
    else st.stepsCollapsed = true end
    elapsed = 1
  end)
  toggle:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    local st = S()
    GameTooltip:SetText(st.stepsCollapsed and L["Show the steps"] or st.stepsAll and L["Show fewer steps"] or L["Hide the steps"], 1, 1, 1)
    GameTooltip:Show()
  end)
  G.stepsToggle = toggle
  local more = SmallBox(toggle, "+")
  more:SetScript("OnClick", function()
    S().stepsAll, S().stepsCollapsed = true, false
    elapsed = 1
  end)
  more:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    GameTooltip:SetText(L["Show All the Steps"], 1, 1, 1)
    GameTooltip:Show()
  end)
  G.stepsMore = more
  -- (asked 2026-10-06) in a group: Share, the route linked in party chat for you to send
  local share = SmallBox(more, "")
  share:SetWidth(44)
  share.label:SetFontObject("GameFontNormalSmall")
  share.label:SetText(L["Share"])
  share:SetWidth(math.max(44, (share.label:GetStringWidth() or 0) + 10)) -- (a longer word in another language)
  share:SetScript("OnClick", function() G.ShareRouteWithGroup() end)
  share:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    GameTooltip:SetText(ns.Nav.OnQuestRoute() and L["Share Quest Route"] or L["Share Route"], 1, 1, 1)
    GameTooltip:AddLine(L["Puts a link to your route in party chat (raid chat in a raid); press Enter to send it. Group members with AzerothGPS click it to get your route, and they're asked before it replaces theirs. Right-click a group member's icon on the map to ask for theirs."], nil, nil, nil, true)
    GameTooltip:Show()
  end)
  G.shareButton = share
  navPanel:Hide()

  northLabel = top:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  northLabel:SetText(L["N"]) -- (north)
  northLabel:SetTextColor(1, 0.3, 0.3)

  infoText = top:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  infoText:SetPoint("BOTTOM", 0, 4)
  infoText:SetShadowOffset(1, -1)

  noMapText = top:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  noMapText:SetPoint("CENTER")
  -- a dungeon's map: a column under the frame's portrait (G.PlaceFloorBar): "+" up a floor (all
  -- of them past the top), which is shown, "-" down one; its note (the gold line) at the bottom
  fl.bar = CreateFrame("Frame", nil, top)
  fl.bar:SetSize(30, 74)
  fl.bar:SetPoint("TOPLEFT", 8, -8)
  fl.bar:Hide()
  local function FloorButton(text, tip, up)
    local ok, b = pcall(CreateFrame, "Button", nil, fl.bar, "UIPanelButtonTemplate")
    if not ok then b = CreateFrame("Button", nil, fl.bar) end
    b:SetSize(28, 24)
    b:SetText(text)
    b:SetScript("OnClick", function() G.FloorStep(up) end)
    b:SetScript("OnEnter", function(self)
      GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
      GameTooltip:SetText(tip, 1, 1, 1)
      GameTooltip:Show()
    end)
    b:SetScript("OnLeave", GameTooltip_Hide)
    return b
  end
  fl.up = FloorButton("+", L["Up a floor (all of them past the top one)"], true)
  fl.up:SetPoint("TOP", fl.bar, "TOP", 0, 0)
  fl.count = fl.bar:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  fl.count:SetPoint("TOP", fl.up, "BOTTOM", 0, -3)
  fl.count:SetShadowOffset(1, -1)
  fl.down = FloorButton("-", L["Down a floor"], false)
  fl.down:SetPoint("TOP", fl.count, "BOTTOM", 0, -3)
  fl.text = top:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  fl.text:SetPoint("BOTTOM", infoText, "TOP", 0, 2)
  fl.text:SetShadowOffset(1, -1)
  fl.text:Hide()
  G.MakePathColorPicker(top)

  -- Hidden (closed, a key, combat) with stops placed but not confirmed yet: they become the
  -- route now (the 5 s auto-confirm runs only while the map shows), so the direction arrow
  -- leads there in the background. Placing ends; the map follows the player again.
  -- (and closed without being hidden: the map as the minimap sent back to its square, the game's world map with the
  -- map in it closed; asked 2026-11-14: "how come I'm having to confirm route? If I set a destination and close the
  -- map routing should just start")
  function G.ConfirmPendingOnClose()
    local had = #pending > 0
    if had then
      local stops = {}
      for _, d in ipairs(ns.Nav.stops) do stops[#stops + 1] = d end
      for _, d in ipairs(pending) do stops[#stops + 1] = d end
      local keep = ns.Nav.keepOrder and #ns.Nav.stops > 0 -- (an import's listed order: the new stops after it)
      ns.Nav.SetStops(stops, S().fastestOrder and not keep, nil, keep)
    end
    -- (option) with a route, a map looked around in reopens following the player too
    local reopenFollow = S().reopenFollow and ns.Nav.dest and (free or browse)
    if had or G.appended or tour or reopenFollow then G.Follow() end
    return had
  end
  frame:HookScript("OnHide", function() G.ConfirmPendingOnClose() end)

  -- (the map's OnUpdate pumps the searches while the map shows, and the arrow's used to while it was hidden:
  -- with the arrow off too, nothing pumped — the first route never finished and the minimap's route froze
  -- (the 2026-10-07 idle profile). A bare frame, always shown, pumps whenever the map isn't; the arrow no
  -- longer does. HasWork false is a few millionths of a second a frame.)
  local pump = CreateFrame("Frame", nil, UIParent)
  pump:SetSize(1, 1)
  pump:SetPoint("TOPLEFT")
  -- (timed: ns.Timed, the work besides the searches; the map's OnUpdate too, besides its redraw, searches and fade)
  pump:SetScript("OnUpdate", G.Timed("pump frame (map hidden)", function(_, dt)
    if not G.IsVisible() then
      G.PumpSearches()
      ns.Nav.Tick() -- (the map's redraw does this while it shows: clears an arrived trip)
      -- (and the route's upkeep: following the player, trimming what's walked, recalculating, the stops advanced on
      -- arrival: Nav.Status, which the arrow's text does 4 times a second while the arrow shows. With the map hidden
      -- AND the arrow off nothing did it, and the minimap's route stood still: the user's 1.1.6 test pass, 2026-10-07)
      local arrow = _G.AzerothGPSArrow
      -- (the route panel detached: kept up to date, the route's upkeep with it)
      local navShown = false
      if G.navDetached then
        G.navT = (G.navT or 0) + (dt or 0)
        if G.navT >= G.NAV_DETACHED_EVERY then
          G.navT = 0
          local okN, errN = pcall(G.RefreshDetachedNav)
          if not okN then G.LogError("route panel", errN) end
        end
        navShown = ns.Nav.dest ~= nil
      end
      if ns.Nav.dest and not navShown and not (arrow and arrow:IsVisible()) then
        G.upkeepT = (G.upkeepT or 0) + (dt or 0)
        if G.upkeepT >= G.UPKEEP_EVERY then
          G.upkeepT = 0
          local px, py, cont = Geo.PlayerWorld()
          if px then pcall(ns.Nav.Status, px, py, cont) end
        end
      end
    end
  end))
  G.pumpFrame = pump

  frame:SetScript("OnUpdate", G.Timed("map frame, other work", function(_, dt)
    if tour then
      -- (an error in the tour ends it, rather than failing every frame)
      local ok, err = pcall(TourStep, GetTime())
      if not ok then
        tour = nil
        G.lastError = tostring(err)
        G.Follow()
      end
    end
    -- background terrain searches for the route: ~1 ms a frame. A search done isn't a redraw of its own: the route it
    -- changes (Nav.SearchDone) is a new route, which the next redraw at G.RedrawHz sees (ViewChanged). Forced at once,
    -- walking off a long off-road leg redrew the map every frame, a search done in each (the 1.1.5 test pass: 20% of a
    -- core zoomed in on a long dotted leg)
    G.PumpSearches()
    G.UpdateApproach(dt)
    G.GlidePan() -- (the laid layers slide with the player every frame; redraws refresh their content)
    -- (every frame only while fading; settled, every G.SettledEvery(): issue #191, most of an idle map's frames)
    G.settleDt = (G.settleDt or 0) + dt
    if G.fading or G.settleDt >= G.SettledEvery() then
      local fdt = G.settleDt
      G.settleDt = 0
      local ft = ns.PerfStart()
      G.AreaTooltip(fdt)
      G.RoadHover(fdt)
      G.BuildingHover()
      G.UpdateFade(fdt)
      ns.PerfEnd("every frame: fade, tooltip", ft)
    end
    infoWait = infoWait - dt
    if infoWait <= 0 then
      infoWait = 0.1
      G.UpdateInfo()
    end
    local okH, errH = pcall(G.UpdateZoneHover)
    if not okH then G.LogError("zone hover", errH) end
    local okE, errE = pcall(G.PumpEdges) -- (the walls' outline, worked out in the background)
    if not okE then G.LogError("wall outline", errE) end
    if #pending > 0 or G.appended then
      local mx, my = GetCursorPosition()
      if (mx ~= G.lastMouseX or my ~= G.lastMouseY) and frame:IsMouseOver() then lastActivity = GetTime() end
      G.lastMouseX, G.lastMouseY = mx, my
      if not drag and GetTime() - lastActivity >= AUTO_CONFIRM then
        if #pending > 0 then
          G.ConfirmRoute()
        else
          -- stops added to the route: show the whole route, then follow the player again
          G.appended = false
          local px, py, cont = Geo.PlayerWorld()
          if px and ns.Nav.dest and free then StartTour(px, py, cont, ViewCont(cont), true) else G.Follow() end
        end
      end
    end
    G.EraserTick()
    if G.lasso and not G.lasso.pad then -- drawing a farming area: add the cursor's spot as it moves (not the pad's)
      local mx, my = GetCursorPosition()
      local sc = canvas:GetEffectiveScale()
      local ccx, ccy = canvas:GetCenter()
      local dx, dy = mx / sc - ccx, my / sc - ccy
      local l = G.lasso
      if not l.sx or (dx - l.sx) ^ 2 + (dy - l.sy) ^ 2 >= 36 then
        local x, y = G.ScreenToWorld(view.x, view.y, dx, dy, view.rot, view.s)
        l.pts[#l.pts + 1], l.pts[#l.pts + 2] = x, y
        -- (a road's: the floor picked at each point, Shift + wheel while drawing changes it: asked 2026-10-06)
        if l.road and not l.wall then
          l.zs = l.zs or {}
          l.zs[#l.pts / 2] = G.editFloor and G.editFloor.z or false
        end
        l.sx, l.sy = dx, dy
        elapsed = 1
      end
    end
    if drag then
      local mx, my = GetCursorPosition()
      local sc = frame:GetEffectiveScale()
      local dx, dy = (mx - drag.cx) / sc, (my - drag.cy) / sc
      if drag.moved or dx * dx + dy * dy > 9 then -- ignore clicks and tiny jitters
        drag.moved = true
        local x, y = G.PanCenter(drag.x, drag.y, dx, dy, drag.rot, drag.s)
        -- (a drag from the land keeps showing the land, G.LandView: only one from the city's map keeps the city's)
        free = { x = x, y = y, rot = drag.rot, cross = true, cont = view.cont, interior = free and free.interior, pan = true,
          land = (free and free.land) or drag.land or nil, cave = free and free.cave } -- (a cave's map stays one)
        recenter:Show()
        elapsed = 1 -- redraw this frame
      end
    end
    if G.mmState.on then
      local okA, errA = pcall(G.MinimapAwayCheck, dt)
      if not okA then G.LogError("minimap in an instance", errA) end
    end
    local okT, errT = pcall(G.ToolsIdleTick, dt, drag ~= nil or G.lasso ~= nil)
    if not okT then G.LogError("tools idle", errT) end
    local forced = elapsed >= 1 -- G.Redraw / settings / dragging / tour set elapsed = 1
    elapsed = elapsed + dt
    if elapsed < 1 / G.RedrawHz() then return end
    local now = GetTime()
    if not forced and G.GlideHolds(now, lastFull) then return end -- (only the player moved: the layers glide)
    elapsed = 0
    if forced then G.drawVersion = G.drawVersion + 1 end -- (asked for: everything placed again, G.Update's `still`)
    -- Nothing changed (standing still, same view, same route): skip, but still redraw at
    -- least every REDRAW_IDLE seconds (ETAs, timers, refreshed layers).
    if not ViewChanged() and not forced then
      local idle = now - lastFull
      if idle < REDRAW_IDLE then return end
      -- (no route or stop, no dock countdown, no party dots, the mouse off the map, the layers
      -- unchanged: nothing a redraw would move, so it waits for REDRAW_IDLE_QUIET; the 2026-10-07
      -- idle profile - a full redraw a second with nothing to show for it)
      if idle < G.REDRAW_IDLE_QUIET then
        local quiet, routeOnly = G.QuietIdle()
        if quiet then return end
        -- (a route as last drawn: its upkeep and the panel's text every REDRAW_IDLE, the map as it is; issue #191)
        local ipx, ipy, ipc = Geo.PlayerWorld()
        if routeOnly and ipx then
          if now - (G.idlePanelAt or 0) < REDRAW_IDLE then return end
          G.idlePanelAt = now
          local t1 = ns.PerfStart()
          local okP, errP = pcall(function()
            ns.Nav.Tick()
            local r = ns.Nav.Route(ipx, ipy, ipc)
            if r and ns.Nav.RedAsking and ns.Nav.RedAsking() then r = nil end
            G.UpdateNavPanel(ipx, ipy, ipc, nil, r, ns.Nav.dest)
          end)
          ns.PerfEnd("map text", t1)
          if not okP then G.LogError("map text", errP) end
          return
        end
      end
    end
    lastFull = now
    G.idlePanelAt = now
    local t0 = ns.PerfStart()
    local ok, err = pcall(G.Update)
    ns.PerfEnd("redraw", t0)
    if not ok then G.LogError("redraw", err) end
    -- (the game's map to the view just drawn, in this same frame: from its own ticker alone it could be a frame
    -- behind, its icons sliding on the map while it was panned, seen in a recording 2026-11-10)
    if G.wmState.on then pcall(G.WorldMapSync) end
    G.routeIdleSig = G.RouteIdleSig()
    G.GlideFill(G.glideSig) -- (what this redraw showed besides the player's spot: G.GlideHolds)
    G.glideX, G.glideY = Geo.PlayerWorld()
  end))
  G.InitMinimapReplace() -- (the map as the minimap: its events)
  G.InitWorldMapHost() -- (the map in the game's world map window: its opening and closing)
  G.InitPickRoute() -- (the quest picked in the quest log: its route, the option on)
  G.InitRouteHere() -- (Route Here: the quest details' button, the quest menus)
  G.ApplySettings()
  -- a /reload keeps the view where it was panned to (saved as the UI goes)
  local saver = CreateFrame("Frame")
  saver:RegisterEvent("PLAYER_LOGOUT")
  saver:SetScript("OnEvent", function() if not G.clone then ns.db.mapView = G.SaveView() end end)
  G.RestoreView(ns.db.mapView)
  ns.db.mapView = nil
  G.lookMap = frame -- (the window the button colors are for: Options > Window's and another addon's)
  G.RegisterLookFrame(frame) -- (its buttons all made by now)
end

G.VIEW_KEEP = 600 -- seconds: a saved view older than this (a later login) isn't restored

-- Zone level ranges (the classic zones) when the game doesn't say (C_Map.GetMapLevels).
G.ZONE_LEVELS = {
  ["Elwynn Forest"] = { 1, 10 }, ["Dun Morogh"] = { 1, 10 }, ["Tirisfal Glades"] = { 1, 10 },
  ["Durotar"] = { 1, 10 }, ["Mulgore"] = { 1, 10 }, ["Teldrassil"] = { 1, 10 },
  ["Westfall"] = { 10, 20 }, ["Loch Modan"] = { 10, 20 }, ["Silverpine Forest"] = { 10, 20 },
  ["Darkshore"] = { 10, 20 }, ["The Barrens"] = { 10, 25 }, ["Redridge Mountains"] = { 15, 25 },
  ["Stonetalon Mountains"] = { 15, 27 }, ["Ashenvale"] = { 18, 30 }, ["Duskwood"] = { 18, 30 },
  ["Wetlands"] = { 20, 30 }, ["Hillsbrad Foothills"] = { 20, 30 }, ["Thousand Needles"] = { 25, 35 },
  ["Alterac Mountains"] = { 30, 40 }, ["Arathi Highlands"] = { 30, 40 }, ["Desolace"] = { 30, 40 },
  ["Stranglethorn Vale"] = { 30, 45 }, ["Dustwallow Marsh"] = { 35, 45 }, ["Badlands"] = { 35, 45 },
  ["Swamp of Sorrows"] = { 35, 45 }, ["Feralas"] = { 40, 50 }, ["The Hinterlands"] = { 40, 50 },
  ["Tanaris"] = { 40, 50 }, ["Searing Gorge"] = { 43, 50 }, ["Azshara"] = { 45, 55 },
  ["Blasted Lands"] = { 45, 55 }, ["Un'Goro Crater"] = { 48, 55 }, ["Felwood"] = { 48, 55 },
  ["Burning Steppes"] = { 50, 58 }, ["Western Plaguelands"] = { 51, 58 }, ["Eastern Plaguelands"] = { 53, 60 },
  ["Winterspring"] = { 55, 60 }, ["Deadwind Pass"] = { 55, 60 }, ["Moonglade"] = { 55, 60 },
  ["Silithus"] = { 55, 60 },
}

-- A zone's levels: min, max (nil if unknown).
function G.ZoneLevels(id, name)
  if C_Map and C_Map.GetMapLevels then
    local ok, lo, hi = pcall(C_Map.GetMapLevels, id)
    if ok and lo and hi and lo > 0 and hi > 0 then return lo, hi end
  end
  local l = name and G.ZONE_LEVELS[name]
  if l then return l[1], l[2] end
end

-- The zone's name and levels for the hover: name, "Level 10-20" (or nil), color (by the
-- player's level: red far below it, orange below, yellow in it, green above, gray far above).
function G.ZoneHoverText(id, name, playerLevel)
  local lo, hi = G.ZoneLevels(id, name)
  local shown = ns.ZoneName(id, name) -- (the game's language; the levels by the English)
  if not lo then return shown end
  local pl = playerLevel or 1
  local r, g, b
  if pl < lo - 4 then r, g, b = 1, 0.1, 0.1
  elseif pl < lo then r, g, b = 1, 0.5, 0.25
  elseif pl <= hi then r, g, b = 1, 1, 0
  elseif pl <= hi + 5 then r, g, b = 0.25, 0.75, 0.25
  else r, g, b = 0.6, 0.6, 0.6 end
  return shown, lo == hi and Format(L["Level %d"], lo) or Format(L["Level %d-%d"], lo, hi), r, g, b
end

-- The insets' frames (gold under the mouse) and names, on the world map.
function G.DrawInsetFrames(cx, cy, rot, s)
  local bm = browse and ns.Maps[browse]
  local on = bm and bm.worldFrames and browseBounds and true
  G.insetLabels = G.insetLabels or {}
  for i, it in ipairs(G.WORLD_INSETS) do
    local label = G.insetLabels[i]
    if on and ns.Maps[it.map] then
      local ib = G.InsetBounds(it, browseBounds)
      local pts = {}
      for _, c in ipairs({ { ib[3], ib[4] }, { ib[3], ib[2] }, { ib[1], ib[2] }, { ib[1], ib[4] } }) do
        local dx, dy = Geo.ScreenOffset(cx, cy, c[1], c[2])
        dx, dy = Geo.Rotate(dx * s, dy * s, rot)
        pts[#pts + 1] = { dx, dy }
      end
      local hot = G.hoverInset == it
      for k = 1, 4 do
        local a, b = pts[k], pts[k % 4 + 1]
        AddSeg(a[1], a[2], b[1], b[2], hot and { 1, 0.82, 0 } or { 0.3, 0.22, 0.12 }, hot and 3 or 2, 1, true)
      end
      if not label then
        label = lineLayer:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
        G.insetLabels[i] = label
      end
      label:SetText(ns.ZoneName(it.map, ns.Maps[it.map].name))
      G.PinText(label, canvas, "BOTTOM", (pts[1][1] + pts[2][1]) / 2, (pts[1][2] + pts[2][2]) / 2 + 2)
      label:Show()
    elseif label then
      label:Hide()
    end
  end
end

-- The zone under the mouse lit up, as on the game's own map: C_Map.GetMapHighlightInfoAtPosition
-- gives the zone's highlight art and where it goes, in fractions of the map ({ u0, v0, u1, v1 }).
local highlight
local function PlaceHighlight()
  local t = G.zoneHighlight
  if not t then return end
  local b = browseBounds
  if not (highlight and b and view.rot == 0) then
    t:Hide()
    return
  end
  local function At(u, v)
    local dx, dy = Geo.ScreenOffset(view.x, view.y, b[3] - v * (b[3] - b[1]), b[4] - u * (b[4] - b[2]))
    return dx * view.s, dy * view.s
  end
  local x0, y0 = At(highlight[1], highlight[2])
  local x1, y1 = At(highlight[3], highlight[4])
  t:ClearAllPoints()
  t:SetPoint("TOPLEFT", canvas, "CENTER", x0, y0)
  t:SetPoint("BOTTOMRIGHT", canvas, "CENTER", x1, y1)
  t:Show()
end
local function FindHighlight(mapID, u, v)
  highlight = nil
  if not (C_Map and C_Map.GetMapHighlightInfoAtPosition and tileLayer) then return end
  local ok, fid, _, tu, tv, w, h, sx, sy = pcall(C_Map.GetMapHighlightInfoAtPosition, mapID, u, v)
  if not (ok and fid and fid ~= 0 and w and w > 0 and h and h > 0) then return end
  if not G.zoneHighlight then
    G.zoneHighlight = tileLayer:CreateTexture(nil, "ARTWORK", nil, 7)
    G.zoneHighlight:SetBlendMode("ADD")
  end
  G.zoneHighlight:SetTexture(fid)
  G.zoneHighlight:SetTexCoord(0, tu, 0, tv)
  highlight = { sx, sy, sx + w, sy + h }
end

-- The zone under (dx, dy) px from the map's middle on the seamless map's art (issue #60): its uiMap and name, or nil
-- over the sea. The view's yards go past its continent's edge over the other one on the art: that one's zone there.
function G.SeamZoneAt(dx, dy)
  local x, y = G.ScreenToWorld(view.x, view.y, dx, dy, view.rot, view.s)
  local c = view.cont
  local A = ns.Atlas
  if A and A.ToAtlas and A.FromAtlas then
    local u, v = A.ToAtlas(c, x, y)
    local c2, x2, y2 = nil, nil, nil
    if u then c2, x2, y2 = A.FromAtlas(u, v) end
    if c2 then c, x, y = c2, x2, y2 end
  end
  local R = ns.Router
  if not (R and R.ZoneAt) or R.ZoneAt(c, x, y) == 0 then return nil end -- (no ground there: the sea)
  return G.LocateWorld(c, x, y)
end

-- On a continent's map: the zone under the mouse, lit up, and its levels as text beside the
-- cursor. On the world map: an inset under the mouse (its frame gold, its name and levels).
-- On the seamless map's art alone (continent and world zoom, issue #60): the zone's name and levels.
-- Quick Search (the AZEROTHGPS_SEARCH key, Bindings.xml; asked 2026-11-14): the map shown (opened out, as the map as
-- the minimap; un-minimized), then its search box focused on the next frame, so the key itself isn't typed into it and
-- the player types the place at once.
G.SEARCH_FOCUS_EVERY, G.SEARCH_FOCUS_TRIES = 0.05, 12

-- Quick Find (asked 2026-11-14: "add a quick button above the search button that expands out for quick searches for
-- closest common things like repair, vendor, ammo (if the player class is hunter)"): its flyout's entries, each a
-- generic word (G.GENERIC_KINDS) and its icon (Pins.NPC_ICONS' key). Click: a stop at the nearest of that kind, as
-- picking the search's first; right-click: the search with that word typed. Ammo a hunter's only, and it opens its
-- own: Arrows, Bullets (asked 2026-11-14: "pop out again to select gun ammo or arrows").
G.QUICK_FIND_ICON = "Interface\\Icons\\Ability_Tracking"
G.QUICK_FIND = {
  { kind = "repair", label = L["Repair"], icon = "repair" },
  { kind = "vendor", label = L["Vendor"], icon = "vendor" },
  { kind = "innkeeper", label = L["Innkeeper"], icon = "inn" },
  { kind = "flight master", label = L["Flight Master"], icon = "flight" },
  -- (Banker, Auctioneer and Class Trainer taken off, asked 2026-11-15: Search Places still finds them)
  { kind = "stable master", label = L["Stable Master"], icon = "stable", class = "HUNTER" }, -- (hunters only, asked
  -- 2026-11-15)
  { kind = "ammo", label = L["Ammo"], icon = "ammo", class = "HUNTER", sub = {
    { kind = "arrows", label = L["Arrows"], icon = "arrows" },
    { kind = "bullets", label = L["Bullets"], icon = "bullets" } } },
}
G.QUICK_FIND_MAX = 100 -- (the search's list looked through for the nearest of the kind)
function G.QuickFindIcon(e)
  if e.tex then return e.tex end -- (a custom search's, or one the player changed: Searches)
  local I = ns.Pins and ns.Pins.NPC_ICONS
  return I and I[e.icon] or "Interface\\Icons\\INV_Misc_QuestionMark"
end
-- The entries for the player's class (UnitClass's file name: "HUNTER"): the account's searches put in Quick Find
-- (ns.Searches, 1.3.5: its own seeded there, changed, removed or added to by the player), each a view of its row
-- { kind (the built-in's, else "cs:" and its id), label, desc, tex, icon, search, sub, row }.
function G.QuickFindEntries()
  local Sx = ns.Searches
  local class = UnitClass and select(2, UnitClass("player"))
  local out = {}
  if not (Sx and ns.db) then
    for _, e in ipairs(G.QUICK_FIND) do
      if not e.class or e.class == class then out[#out + 1] = e end
    end
    return out
  end
  for _, r in ipairs(Sx.List()) do
    if Sx.Place(r) == "quickFind" and Sx.Shown(r) then
      local b = Sx.Builtin(r)
      out[#out + 1] = { kind = b and b.kind or Sx.QuickId(r), label = Sx.Name(r), desc = r.desc, tex = r.icon,
        icon = b and b.icon, search = Sx.Text(r), sub = b and b.sub, row = r, class = b and b.class }
    end
  end
  return out
end
-- The nearest search entry of generic `kind` (an NPC, or a city place of it): on the player's continent nearest
-- first, else the first found. Nil when there's none.
function G.QuickFindNearest(kind)
  local words = {}
  for w in kind:gmatch("%S+") do words[#words + 1] = w end
  local best, memo, FAR = nil, {}, math.huge
  for _, e in ipairs(G.SearchPlacesPlain(kind, G.QUICK_FIND_MAX)) do
    if e.x and e.cont and G.EntryKindTyped(words, e, memo) and (not best or (e.yd or FAR) < (best.yd or FAR)) then
      best = e
    end
  end
  return best
end
function G.ToggleQuickFind() return G.SetQuickFindOpen(not G.quickFindOpen) end
-- Open or shut; `sub`: the entry whose own flyout is out too (Ammo). Not while another addon holds the map.
function G.SetQuickFindOpen(on, sub)
  if on and G.Held() then return false end
  G.quickFindOpen = on and true or false
  G.quickFindSub = on and sub or nil
  G.quickFindIdle = 0
  if on and G.mapMenu then G.mapMenu.idle = 0 end
  if on and G.searchPanel then G.searchPanel:Hide() end -- (it opens over the flyout, just above Search Places)
  if G.PlaceQuickFind then G.PlaceQuickFind() end
  return G.quickFindOpen
end
-- An entry clicked: a stop at the nearest (the flyout shut), or said in chat there's none; Ammo opens or shuts its own.
function G.QuickFindClick(e)
  if G.Held() then return nil end
  if e.sub then
    G.SetQuickFindOpen(true, not (G.quickFindSub and G.quickFindSub.kind == e.kind) and e or nil) -- (by kind: the views are new
    return nil
  end
  -- (a row of the account's searches: its own words, the search's top result, ns.Searches)
  if e.row and ns.Searches then
    G.SetQuickFindOpen(false)
    return ns.Searches.Run(e.row)
  end
  local found = G.QuickFindNearest(e.kind)
  G.SetQuickFindOpen(false)
  if not found then
    ns.Print(Format(L["Quick Find: nothing found for %s."], e.label))
    return nil
  end
  if G.PickSearchEntry then G.PickSearchEntry(found) end
  return found
end
-- An entry right-clicked: the search open with its word typed (in the addon's language), all of them nearest first.
function G.QuickFindSearch(e)
  if G.Held() then return false end
  local where = G.QuickPlace and G.QuickPlace("search")
  if not where or where == "hidden" or not G.FillSearch then
    ns.Print(L["Quick Search: the Search Places button is turned off (Options > Quick buttons)."])
    return false
  end
  G.SetQuickFindOpen(false)
  if where:find("^menu") and G.mapMenu and not G.mapMenu:IsShown() then G.mapMenu:Show() end
  G.FillSearch((e.row and e.row.text) or G.KindWord(e.kind) or e.search or e.kind)
  return true
end

function G.QuickSearch()
  local gps = ns.settings and ns.settings.gps
  if not gps then return end
  -- (its quick button hidden: said so, nothing opened; asked 2026-11-14: "show error if player doesn't have this quick
  -- button enabled")
  local where = G.QuickPlace and G.QuickPlace("search")
  if where == "hidden" then
    ns.Print(L["Quick Search: the Search Places button is turned off (Options > Quick buttons)."])
    return false
  end
  -- (as the show/hide key: "Key doesn't show the map in combat", on by default, asked 2026-11-14)
  if gps.keyBlockedInCombat ~= false and (ns.inCombat or (InCombatLockdown and InCombatLockdown()))
      and (not gps.shown or gps.minimized or (G.mmState and G.mmState.on and not G.mmState.expanded)) then
    return false
  end
  if gps.shown and G.mmState and G.mmState.on and not G.mmState.expanded and G.SetMinimapExpanded then
    G.SetMinimapExpanded(true)
  elseif not gps.shown or gps.minimized then
    gps.shown, gps.minimized = true, nil
    if ns.Options and ns.Options.Apply then ns.Options.Apply() end
  end
  local function focus()
    -- (in the map menu: the menu opened first, the button in it; asked 2026-11-14: "quick search didn't expand the map
    -- menu")
    if where and where:find("^menu") and G.mapMenu and not G.mapMenu:IsShown() then G.mapMenu:Show() end
    if G.FocusSearch then G.FocusSearch() end
  end
  -- (the box takes the keys only once it's shown on the screen: the map just opened isn't yet on the next frame, so
  -- tried again each SEARCH_FOCUS_EVERY till it has them, up to SEARCH_FOCUS_TRIES; "can the text window ... be
  -- focused to immediately start typing?", 2026-11-14)
  local tries = 0
  local function try()
    tries = tries + 1
    local box = G.searchPanel and G.searchPanel.box
    if box and box.HasFocus and box:HasFocus() and G.searchPanel:IsVisible() then return end
    if tries == 1 then focus() elseif box then
      if not G.searchPanel:IsShown() then focus() end
      box:SetFocus()
    end
    if tries < G.SEARCH_FOCUS_TRIES and C_Timer and C_Timer.After then C_Timer.After(G.SEARCH_FOCUS_EVERY, try) end
  end
  if C_Timer and C_Timer.After then C_Timer.After(0, try) else focus() end
end

-- The building or cave under the mouse (G.InteriorUnder at G.CursorWorld), looked at every BUILDING_HOVER_EVERY while
-- the map is zoomed in to the "Inside maps when zoomed in" slider's distance (G.viewZoom, the last redraw's): a change
-- redraws with its inside map (G.Update's place), none under the mouse the map as it was. Not while dragging.
G.BUILDING_HOVER_EVERY = 0.1
function G.BuildingHover()
  local now = GetTime()
  if now - (G.buildingHoverAt or 0) < G.BUILDING_HOVER_EVERY then return end
  G.buildingHoverAt = now
  local st = ns.settings and ns.settings.gps
  local hit, key
  -- (a mouse button down, a drag or a click's: left as it is; cleared then, the map flashed and the click's hold had
  -- nothing to hold, asked 2026-11-14: "left click just flashes the map and doesn't hold it open")
  if drag then return end
  -- (OpenMap only, asked 2026-11-15: "for the building mouse over, this should only work in OpenMap mode")
  -- (on a flight, the mouse still: the map moving under it isn't a hover; it hovered building after building, each
  -- one's map laid, reported 2026-11-15 as stutter on flight paths)
  local mx, my = GetCursorPosition()
  local still = mx == G.hoverMouseX and my == G.hoverMouseY
  G.hoverMouseX, G.hoverMouseY = mx, my
  local flying = still and UnitOnTaxi and UnitOnTaxi("player")
  if st and st.interiors ~= false and G.Seamless() and not view.instance and G.InteriorZoomOK(G.viewZoom) and not flying then
    local x, y, c = G.CursorWorld()
    -- (the controller in use: the crosshair is the mouse, asked 2026-11-16 "In controller mode, when panning the map
    -- consider the crosshair as a mouse over for viewing inside buildings/caves/etc"; Pad.marksOn, its marks shown)
    if ns.Pad and ns.Pad.marksOn and view.cont and not view.instance then x, y, c = view.x, view.y, view.cont end
    local place, wmo, room
    -- (a cave under the mouse first: its whole map, as opened from its icon; asked 2026-11-14, "all caves should show
    -- with mouse over too just like buildings": a building's room under the mouse came up in only part of a cave, or
    -- none. G.CaveAt, the caves with art, G.CaveArt)
    local cave = x and not (view.cave and not G.hoveredCave) and c == Geo.Base(c) and G.CaveAt(c, x, y) -- (shown by
    -- this hover: looked for still, or it went and came every check, a video 2026-11-14)
    if cave and G.CaveArt(c, cave) then
      hit = { cave = cave, cont = c }
      key = "cave:" .. c .. ":" .. tostring(cave)
    else
      if x then place, wmo, room = G.InteriorUnder(x, y, c) end
      if place then
        hit = { place, wmo, room, cont = c }
        key = table.concat({ place[1], place[2], place[3], tostring(room), c }, ":")
      end
    end
  end
  local held = G.heldInside
  if held and now > held.untilT then
    G.heldInside = nil
    G.Redraw()
  end
  if key ~= G.hoverInsideKey then
    G.hoverInsideKey, G.hoverInside = key, hit
    if key ~= G.hoverDismissKey then G.hoverDismissKey = nil end
    if not G.heldInside then G.Redraw() end
  end
end

local hoverZone, hoverAt = nil, 0
function G.UpdateZoneHover()
  local label = G.zoneLabel
  if not label then return end
  local m = browse and ns.Maps and ns.Maps[browse]
  local seam = not browse and view.artOnly and not G.Held()
  local over = (seam or m and (m.type == 2 or m.worldFrames)) and frame:IsMouseOver() and not drag and not G.lasso
  if not over then
    if hoverZone then label:Hide() end
    hoverZone, highlight = nil, nil
    PlaceHighlight()
    if G.hoverInset then
      G.hoverInset = nil
      G.Redraw()
    end
    return
  end
  PlaceHighlight()
  local mx, my = GetCursorPosition()
  local sc = canvas:GetEffectiveScale()
  local ccx, ccy = canvas:GetCenter()
  local dx, dy = mx / sc - ccx, my / sc - ccy
  label:ClearAllPoints()
  label:SetPoint("BOTTOMLEFT", canvas, "CENTER", dx + 16, dy + 2)
  local now = GetTime()
  if now - hoverAt < 0.1 then return end
  hoverAt = now
  local id, name
  if seam then
    id, name = G.SeamZoneAt(dx, dy)
    if id == hoverZone then return end
    hoverZone = id
    if not id then
      label:Hide()
      return
    end
    local zn, lv, r, g, bl = G.ZoneHoverText(id, name, UnitLevel and UnitLevel("player"))
    label:SetText(lv and string.format("%s\n|cff%02x%02x%02x%s|r", zn, math.floor(r * 255), math.floor(g * 255), math.floor(bl * 255), lv) or zn)
    label:Show()
    return
  end
  local x, y = G.ScreenToWorld(view.x, view.y, dx, dy, view.rot, view.s)
  local b = browseBounds
  local u, v = b and (b[4] - y) / (b[4] - b[2]), b and (b[3] - x) / (b[3] - b[1])
  if b then FindHighlight(browse, u, v) end
  if m.worldFrames then -- (the world map: its insets only)
    local it = b and G.InsetAt(u, v)
    if it ~= G.hoverInset then
      G.hoverInset = it
      G.Redraw()
    end
    if it then highlight = nil end -- (the inset's own frame lights up instead)
    id = it and it.map
    name = it and ns.Maps[it.map].name
    if id == hoverZone then return end
    hoverZone = id
    if not id then
      label:Hide()
      return
    end
    local zn, lv, r, g, bl = G.ZoneHoverText(id, name, UnitLevel and UnitLevel("player"))
    label:SetText(lv and string.format("%s\n|cff%02x%02x%02x%s|r", zn, math.floor(r * 255), math.floor(g * 255), math.floor(bl * 255), lv) or zn)
    label:Show()
    return
  end
  if b and C_Map and C_Map.GetMapInfoAtPosition then
    local ok, info = pcall(C_Map.GetMapInfoAtPosition, browse, (b[4] - y) / (b[4] - b[2]), (b[3] - x) / (b[3] - b[1]))
    if ok and info and info.mapType == 3 then id, name = info.mapID, info.name end
  end
  if not id then id, name = G.LocateWorld(browseCont or m.continent, x, y) end
  if id == hoverZone then return end
  hoverZone = id
  if not id then
    label:Hide()
    return
  end
  local zn, lv, r, g, bl = G.ZoneHoverText(id, name, UnitLevel and UnitLevel("player"))
  label:SetText(lv and string.format("%s\n|cff%02x%02x%02x%s|r", zn, math.floor(r * 255), math.floor(g * 255), math.floor(bl * 255), lv) or zn)
  label:Show()
end

-- The panned view (nil while following the player), to come back to after a /reload.
-- (a view's free look, plain: no interior map tables)
local function PlainFree(f)
  return f and { x = f.x, y = f.y, rot = f.rot, cross = f.cross, cont = f.cont, city = f.city, instance = f.instance } or nil
end

function G.SaveView()
  if not free then return nil end
  local from = openedFrom
  local caveMap = free.cave and G.CaveArt(free.cont, free.cave)
  return { x = free.x, y = free.y, rot = free.rot, cross = free.cross, cont = free.cont, city = free.city, land = free.land,
    instance = free.instance, wing = free.wing, zoom = ns.settings and S().zoom or nil, -- (a dungeon's map, a wing's, and its floor stepped to)
    cave = free.cave, -- (a cave's map, G.ShowCave)
    floor = (free.instance and floorInst == free.instance or caveMap and floorInst == caveMap) and floorSel or nil,
    browse = browse, browseZoom = browseZoom, browseCont = browseCont, fromTerrain = fromTerrain,
    -- (the view a city's or dungeon's map was opened from: right-click still goes back there)
    from = from and { browse = from.browse, browseZoom = from.browseZoom, browseCont = from.browseCont,
      fromTerrain = from.fromTerrain, zoom = from.zoom, free = PlainFree(from.free) } or nil,
    who = UnitGUID and UnitGUID("player"), t = time() }
end

function G.RestoreView(v)
  if not (v and v.x and v.y) then return end
  if v.who ~= (UnitGUID and UnitGUID("player")) or not v.t or math.abs(time() - v.t) > G.VIEW_KEEP then return end
  G.ApplyView(v)
end

-- A view saved by G.SaveView put back as it was: a map browsed (a continent's, the world's, a
-- zone's) with its zoom and middle, a dungeon's map and floor, the terrain view looked around, and
-- where right-click goes back to. (Api.lua's RestoreView: another addon's game ending.)
function G.ApplyView(v)
  if not (v and v.x and v.y) then return end
  if v.instance and not (ns.CityLevels and ns.CityLevels[v.instance]) then return G.Follow() end
  if v.browse and ns.Maps and ns.Maps[v.browse] then
    G.Browse(v.browse, v.browseCont)
    browseZoom = v.browseZoom or browseZoom
    fromTerrain = v.fromTerrain
  else
    browse, browseZoom, browseCont, browseBounds = nil, nil, nil, nil
  end
  local caveMap = v.cave and v.cont and G.CaveArt(v.cont, v.cave) or nil -- (a cave's map: still one)
  free = { x = v.x, y = v.y, rot = v.rot or 0, cross = v.cross, cont = v.cont, city = v.city, land = v.land,
    interior = v.city and G.CityInterior(v.city) or nil, instance = v.instance, wing = v.instance and v.wing or nil,
    cave = caveMap and v.cave or nil }
  if v.zoom and ns.settings then S().zoom = v.zoom end
  if v.instance then floorInst, floorSel = v.instance, v.floor end
  if caveMap then floorInst, floorSel = caveMap, v.floor end
  openedFrom = v.from
  if recenter then recenter:Show() end
  elapsed = 1
end

return G
end -- (BuildMap)

local addonName, addon = ...
BuildMap(addonName, addon)

-- The second map (G.clone): the same code over a stand-in for the addon's table. Everything is read through to the
-- real one; what it writes stays with it (the map's settings and saved data: never the player's), and its settings
-- always say "the minimap square, shown, not in the world map".
function addon.MakeMapClone()
  local real, NIL = addon, {}
  local over = { replaceMinimap = true, useWorldMap = false, shown = true, minimized = NIL, locked = true,
    style = "seamless", -- (the square: always the seamless map, G.SquareStyle)
    replaceMinimapCollapseOnMove = false, replaceMinimapCollapseOnCombat = false }
  local own = {}
  local gps = setmetatable({}, {
    __index = function(_, k)
      local v = own[k]
      if v == nil then v = over[k] end
      if v ~= nil then
        if v == NIL then return nil end
        return v
      end
      local st = real.settings and real.settings.gps
      return st and st[k]
    end,
    __newindex = function(_, k, v) own[k] = v == nil and NIL or v end,
  })
  local settings = setmetatable({}, { __index = function(_, k)
    if k == "gps" then return gps end
    return real.settings and real.settings[k]
  end })
  local dbOwn = {}
  local db = setmetatable({}, {
    __index = function(_, k)
      local v = dbOwn[k]
      if v ~= nil then return v end
      return real.db and real.db[k]
    end,
    __newindex = function(_, k, v) dbOwn[k] = v end,
  })
  local proxy = setmetatable({ isMapClone = true, settings = settings, db = db, realGPS = real.GPS,
    realAtlas = real.Atlas }, { __index = real })
  -- (the stitched map's art has one place on one map: the second map gets an engine and art of its own, Atlas.lua)
  if real.Atlas and real.MakeAtlasClone then
    local ok, made = pcall(real.MakeAtlasClone, proxy)
    if not (ok and made) then proxy.Atlas = false end -- (none: the second map without the art, as the Terrain style)
  end
  return BuildMap(addonName, proxy)
end
