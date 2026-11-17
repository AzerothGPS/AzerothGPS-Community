# The seamless map's art: behaviour specification

Issue #61. This is what the stitched world map under AzerothGPS's map must draw and when. A new engine is to be
written from it, with its own structure, names and algorithms. It describes behaviour only: what is drawn, where, at
which zoom, in which colour, and what the rest of AzerothGPS needs from it. It is not a description of any existing
code. Nothing here is a code listing. The engine is free to organise frames, caches, queues and culling as it likes,
as long as the picture and the costs are the same.

Words used throughout:

- **the engine**: the new code that builds and draws the art (it replaces `Atlas/Stitch/`).
- **the glue**: `Atlas/Atlas.lua`, AzerothGPS's own file that loads the engine, places it under the map and converts
  coordinates. It stays. Its calls into the engine change to whatever the new engine offers.
- **the map**: AzerothGPS's own map window (GPSFrame.lua). Its seamless zoom code (`G.SeamBlend`, `G.ArtBlend`,
  `G.SeamArt`, `G.SeamZoneAt`, `G.SeamRebase`, `G.SeamOverview`, `G.UpdateZoneHover`) stays as it is.
- **smoothstep(a, b, x)**: 0 for x at or below a, 1 at or above b, else t²(3 − 2t) with t = (x − a) / (b − a). Every
  fade below uses this unless it says otherwise. A range written "a → b" is such a fade. Where b < a, it runs the
  other way: 0 at a, 1 at b.
- **floor20(x)**: x rounded down to a multiple of 0.05. **round50(x)**: x rounded to the nearest 0.02.
  **round100(x)**: x rounded to the nearest 0.01.

---------------------------------------------------------------------------------------------------------------------

## 1. Overview

The seamless map is one picture of the whole world, made from every zone's map art placed where the game puts it on
Azeroth's world map (uiMap 947). The continents' and the world's own art lie under it. AzerothGPS draws it under its
terrain tiles. As the mouse wheel zooms out past the terrain's furthest zoom (2,500 yd from the middle to the edge at
the 450 px reference size), the art fades in under the tiles, the tiles fade out, and the wheel goes on out to the
whole world (GPSFrame's blend, section 7.1).

From the whole world inwards, the art goes through these stages:

1. **World.** The world map's own art, with the continents' and seas' names lettered live.
2. **Continents.** Each continent's own art comes in over the world's. The world's land art goes. The open sea
   becomes a sea texture tiled at the continents' scale. Coasts get wave hatching.
3. **Zones.** Every zone's own art comes in over the continent art. This is the finest painted detail. Each zone is
   cut to its own territory, colour-matched at its borders, and drawn over the neighbours' halos. Capitals come in
   from their own maps as they grow on screen. The continent art fades to a muted hint. Land with no zone map is
   drawn as blank map paper.
4. **Close-up** (only reached in very wide, short map windows in AzerothGPS; see 7.3). Past the painted art's pixels
   the zones soften with a small blur and paper grain. The game's minimap tiles mix in, and caves can "surface".

The engine never moves the camera, reads input or draws icons in AzerothGPS. The route, stops, player arrow, points
of interest, zone hover label, search and Find Me are all AzerothGPS's own map layers, drawn on top. The engine draws
art only.

### 1.1 Hard constraints

- Lua 5.1 (interface 16001). A file's main chunk may have at most 200 locals, and a function at most 60 upvalues.
  `test_every_addon_file_compiles_under_the_games_lua_5_1` checks this.
- Every texture with a filter is drawn with `"LINEAR"`. `"TRILINEAR"` crashes this client (an assertion on the
  filter; the stand-in UI `wowmock.lua` fails the same way).
- Blizzard's `WorldMapFrame` is never touched (a test greps for it).
- Nothing global and no saved variables of its own. All of its state hangs off `ns.Atlas`. Off, nothing is loaded or
  kept (section 12.1).
- The engine's code names no other project. The style is called OpenMap and its creator is credited (
  2026-10-17, issue #91) only in the player-facing places `test_atlas.py`'s `test_openmap_is_credited_only_where_meant`
  allows: Options > Help improve's Thanks, the style's label and tooltip, the README, the changelog and the docs.
- The art is display only. A click or drag on the map is AzerothGPS's.

---------------------------------------------------------------------------------------------------------------------

## 2. Coordinate spaces

### 2.1 World units and (u, v)

- **World units**: the pixels of Azeroth's map art (uiMap 947). `W × H` is the size of its first art layer from
  `C_Map.GetMapArtLayers(947)[1]` (`layerWidth`, `layerHeight`): **1002 × 668** in this client. Origin top-left,
  x right (east), y down (south).
- **(u, v)**: world units over `W` and `H`, 0..1 across Azeroth's map art. Everything the glue exchanges with the
  engine is in (u, v). Outside 0..1 is valid (sea past the art's edge).
- **A map's rectangle on the world**: `C_Map.GetMapRectOnMap(map, 947)` returns left, right, top, bottom in (u, v).
  The engine needs this for every map it places. It counts as valid only when right > left and bottom > top, and
  it is cached per map, failures included (call it under `pcall`). For 947 itself the rectangle is 0, 1, 0, 1.
- **A map's art pixels → world units**: a map's art layer is `layerWidth × layerHeight` px. Every zone, continent and
  world map here is 1002 × 668, in tiles of `tileWidth × tileHeight` = 256 × 256. Pixel (px, py) of map M with
  rectangle (l, r, t, b) is at world units x = l·W + px·sx, y = t·H + py·sy, where sx = (r − l)·W / layerWidth and
  sy = (b − t)·H / layerHeight.
- Yards per world unit come out at about 44.6 (Eastern Kingdoms) and 44.8 (Kalimdor), both ways. You can check this
  from Data/Maps.lua's `worldFrames`.

### 2.2 AzerothGPS yards ↔ (u, v): the projection

AzerothGPS's yards are the game's world coordinates on continent 0 (Eastern Kingdoms) or 1 (Kalimdor): x north,
y west. The engine provides:

- **yards → (u, v)** for continent c (0 or 1). The continent's map is 1415 for c = 0 and 1414 for c = 1. Take its
  corners from `C_Map.GetWorldPosFromMapPos(map, CreateVector2D(0, 0))` and `(1, 1)`. The second return is a vector;
  read it with `GetXY()` or `.x/.y`, under `pcall`. The vector's x is the world X (north) and its y the world Y
  (west). The corner at map (0, 0) is the north-west one (largest X, largest Y). Then:
  - the map's fraction across = (Y₀ − y) / (Y₀ − Y₁) and down = (X₀ − x) / (X₀ − X₁), where (X₀, Y₀) is the (0, 0)
    corner and (X₁, Y₁) the (1, 1) corner;
  - u = l + across·(r − l), v = t + down·(b − t), with (l, r, t, b) the continent map's rectangle on 947.
  - Robustness (optional but current behaviour): the axis order is checked once with a known spot. Stormwind's flight
    master (−8840.6, 489.7) on continent 0 must land inside the rectangle of uiMap 1429 (Elwynn Forest) or 1453
    (Stormwind City). If only the swapped reading (across from X, down from Y) puts it there, use that one.
  - nil when the corners or the rectangle can't be had. The glue then falls back to Data/Maps.lua's `worldFrames`
    (it already does this; same formula).
- **(u, v) → yards** for a given continent: the exact inverse of the above. The mapping is affine, so it can be
  solved from three probes, or the formula inverted directly. nil when the forward one is nil.

The glue checks once whether the engine's projection works (it asks for continent 0's (0, 0) and treats a non-nil u
as yes). Data/Maps.lua's `worldFrames` (`{minX, minY, maxX, maxY, u0, v0, u1, v1}` per continent) are the same game
assignment, and QA reads both as 0 px apart (section 14).

### 2.3 Minimap tile grid (close zoom and caves)

The game's minimap tiles are the 64 × 64 ADT grid per continent. Each tile is `1600/3` = 533.33 yd square (the ADT
size). Tile (tx, ty), with tx east and ty south, 0..63, covers:

- world Y (west) from (32 − tx)·T down to (31 − tx)·T, and
- world X (north) from (32 − ty)·T down to (31 − ty)·T, with T = 533.33.

A yard spot (X, Y) is in tile tx = floor(32 − Y/T), ty = floor(32 − X/T). Place a tile on the art by projecting
its two opposite corners to (u, v) with 2.2 and taking the box between them (min/max per axis).

### 2.4 The view

The glue gives the engine a view as:

- **centre** (u, v);
- **half extents** (hu, hv), the normalized half-width and half-height of the visible box. For a box of w × h px
  drawn at s px per world unit: hu = w / (2·W·s), hv = h / (2·H·s);
- **plain zoom** Zp: 1 when the whole world just fits the box. The scale is s = fit·Zp with
  fit = min(w/W, h/H) px per world unit;
- **detail zoom** Zd = Zp·K, with K = min(w/W, h/H) / sqrt(w·h / (W·H)). K is 1 for a box of the world's own
  aspect and under 1 for any other. It makes the layers fade by the area of world in view, so a tall or very wide
  box doesn't bring in zones while it still shows a continent's worth. This is the glue's `A.DetailK`; keep it.

Every fade in section 7 is in **Zd** unless it says **Zp** (only the minimap mix uses Zp) or names a size ratio
(caves, the baked handover).

The glue places the engine's root canvas itself. The canvas frame is scaled by s and anchored so that (u, v) falls
at the box's middle. The engine lays its art out in world units inside that canvas: one world unit is one canvas
unit, and the root is laid out for map 947. The art is never rotated.

---------------------------------------------------------------------------------------------------------------------

## 3. Data formats (Atlas/Data/*.lua, kept)

Each file is generated and assigns one or more tables in the engine's namespace. Their current names are in
Appendix A. Each file is currently wrapped so that it only runs when the seamless map is on (section 12.1). Keep that
property, whatever the wrapping looks like.

### 3.1 Reveal data (Reveal.lua)

The zones' explorable pieces, all of them, explored or not. Keyed by **UiMapArtID** (`C_Map.GetMapArtID(map)`, not
the uiMap ID). There are 84 art IDs, two generations of art, and only those the client returns for a zone are used.
Each value maps a piece key to its files:

- key: the string `"w:h:x:y"`: the piece's texture width and height in art px, then its offset x, y in the zone's
  art px (decimal integers, `:`-separated). This is the same identity the game's explored-map data has (3.1.1).
- value: a string of file IDs separated by `", "`. The piece's 256 × 256 tiles, row-major,
  ceil(w/256) per row.

In all, 1,073 pieces and 1,739 tile files over the 84 art IDs.

#### 3.1.1 The game's explored pieces

`C_MapExplorationInfo.GetExploredMapTextures(map)` gives a list with `textureWidth`, `textureHeight`, `offsetX`,
`offsetY`, `fileDataIDs` (row-major, as above) and `isShownByMouseOver`. A piece's identity is the same `"w:h:x:y"`
key built from those four numbers.

- Pieces in this list are **explored**. Those with `isShownByMouseOver` true are left out entirely, never drawn.
- Pieces in the Reveal data but not in this list are **unexplored**. They are drawn from the Reveal data's file IDs.

### 3.2 Grade data (Grade.lua)

`[uiMapID] = { r, g, b }`: colour multipliers, each 0..1 (most 0.6–1.0). Each one takes the zone's border band
toward one shared palette. Present for the 44 zones that have overlays: the 40 original ones plus 2482 (Hyjal), 2521
(Zephras Isle), 2548 (Riverglades) and 2652 (Shen'dralas). A zone with a Grade entry is "graded". Only graded zones
have the per-zone masks (Band, Territory, Core, Edge).

### 3.3 Minimap data (Minimap.lua)

`[continent 0|1][tx·64 + ty] = fileID`: the game's own minimap tile files on the 2.3 grid (305 lines). A missing
key means no tile there.

### 3.4 Minimap LOD data (MinimapLOD.lua)

`[continent 0|1] = { { n, { col·64 + row, ... } }, { n, {...} } }`: smaller copies of the minimap, **finest
first**. Today that is n = 4 (each piece covers 4 × 4 native tiles) and n = 16 (16 × 16). Piece (col, row) covers
native tiles tx = col·n … col·n + n − 1 and ty = row·n … row·n + n − 1. Its file is
`MapMiniLOD/<continent>_<n>_<col>_<row>`. The list says which pieces exist.

### 3.5 Caves data (Caves.lua)

`[uiMapID] = { name, continent (0|1), minX, minY, maxX, maxY, uiMinX, uiMinY, uiMaxX, uiMaxY, { 12 file IDs } }`.
These are the game's micro maps of caves and dungeon entrance areas (44 maps). The yards box is world X (north) and
Y (west). The art covers the whole box: the four ui values are 0, 0, 1, 1 everywhere and aren't used. The 12 files
are a 1002 × 668 picture in 256 px tiles, 4 per row, 3 rows, row-major. Several maps can share a name (floors of
one place).

### 3.6 Gaps data (Gaps.lua)

Land no zone map covers, per continent map:

- `tile = 64`: a gap tile's side in **world units**.
- `paper = 21.62`: world units per repeat of the blank paper texture.
- `[1414]`, `[1415]`: flat lists of triples `col, row, over`. These are gap tiles counted from the continent map's
  top-left corner (its rectangle's l·W, t·H) in steps of `tile`. `over` is 0 everywhere (nothing laid over the
  paper). The tile's land mask is `MapGapLand/<continentMap>_<col>_<row>`.
- `minimap[1414|1415]`: minimap tile keys (tx·64 + ty) touching a gap. They are used only by the "minimap in the
  gaps" layer, which is **off** in AzerothGPS (10.4).
- `art`: a list of `{ name, continentMap, { l, r, t, b } (normalized on the world), { 12 file IDs, 0 = skip } }`.
  These are finer maps the client has of land no zone covers (19 entries: parts of Azshara, Durotar, Stonetalon,
  Silithus, Feralas, Thousand Needles, Ashenvale, Felwood, Tanaris, Un'Goro, the Barrens, Mulgore, Gilneas, Dun
  Morogh, Hillsbrad, Loch Modan, Arathi, the Badlands, Searing Gorge). Each is a 1002 × 668 picture in 256 px tiles,
  4 × 3, placed over its rectangle and masked by `MapCoastArt/<name>`.

### 3.7 Tones data (Tones.lua)

`[uiMapID] = { r, g, b }` (0..1): each zone's overall painted colour, the median of its land. There is no entry for
2521. Used to tint minimap tiles.

### 3.8 Art edits data (ArtEdits.lua)

`[uiMapID] = { tile indices }`: tiles of a map's base art drawn from `MapArt/<uiMapID>_<index>` instead of the
client's file. The index is row-major from 1. Today it covers all 12 tiles of 947, 1414 and 1415 (their hand-cleaned
art: no sea lettering, no baked continent or sea names). So the world and continent backdrops come entirely from
shipped files.

### 3.9 Labels data (Labels.lua)

A list of names lettered live (6.15). Each entry:

- `map`: the map whose art px the lines are measured on (947 for the continents' names, 1414/1415 for the seas').
- `name`: `{ map = uiMapID, text = fallback }` or `{ area = areaID, text = fallback }`. The client's own name
  (`C_Map.GetMapInfo(map).name` or `C_Map.GetAreaInfo(area)`) wins when it isn't empty.
- `fade`: `"land"` or `"sea"`.
- `ink`, `glow`: `{ r, g, b }` 0..255. `glowA`: halo strength.
- `lines`: one per word as the art set it: `{ left, right, baseline, capHeight [, true] }` in the map's art px. A
  fifth value `true` marks a line set all in small capitals.

The current entries: Kalimdor (947; 1 line), Eastern Kingdoms (947; 2 lines), The Veiled Sea (1414; area 457),
The Great Sea (1415; area 214), The Forbidding Sea (1415; area 308). Land: ink (78, 44, 12), glow (243, 189, 81),
glowA 0.7. Sea: ink (66, 60, 44), glow (168, 172, 152), glowA 0.35.

### 3.10 Banners data (Banners.lua): four tables

- City banners: `[cityMap] = { zoneMap, x, y, width, height }`. This is the zone art's name banner for that city, at
  (x, y) in the zone's art px, `width × height` art px. Its texture is `MapBanner/<cityMap>`. Present for 1454
  Orgrimmar (on 1411 Durotar), 1458 Undercity (on 1420 Tirisfal), 1456 Thunder Bluff (on 1412 Mulgore) and 1457
  Darnassus (on 1438 Teldrassil).
- Banner holes: `[zoneMap] = true` for 1411, 1420, 1412, 1438. That zone's overlay art is drawn through
  `MapBannerHole/<zoneMap>`, which cuts its own copy of the banner out (the engine's banner copy shows instead).
- City cuts: `[cityMap] = true` for 1454, 1458, 1456. The city's own map is masked by `MapCityMask/<cityMap>` (cut to
  the city plan) instead of the round feather.
- City titles: `[cityMap] = true` for 1454, 1458, 1456. The city's own (cut) map keeps its own title, so the zone's
  banner for it fades out as the city comes in (6.12).

### 3.11 Zone art data (ZoneArt.lua): the baked tiles

- `px = 16`: baked px per world unit.
- `size = 512`: a tile's px. `step = 510`: the px of it that are its own. The 1 px rim each side overlaps the
  neighbours.
- `desaturate = 0.1`, `colorMatch = 1`: the grade settings the tiles were baked at.
- `tiles`: a list of keys i·256 + j (column i, row j). This is 205 tiles; the file is `MapZones/<i>_<j>` (BLP).

A tile covers world units [i·step/px, (i+1)·step/px) × [j·step/px, (j+1)·step/px), i.e. 31.875 world units square.
Draw it with texture coordinates inset by (size − step) / 2 / size = 1/512 on every side.

---------------------------------------------------------------------------------------------------------------------

## 4. Assets (Atlas/Media/Textures/, about 200 MB, kept)

All are TGA type 2 (uncompressed) unless noted. "Mask" means the file is used as a mask texture, stretched over the
named rectangle, with clamp-to-black-additive wrap on both axes (nothing outside the rectangle). Masks are 32-bit
with alpha. "Colour" files are drawn as textures.

| Folder / file | Count, size | Naming | Used as |
|---|---|---|---|
| `MapArt/` | 36, 256², 24-bit | `<map>_<n>`, n = 1..12 row-major | colour: replacement base art tiles for 947, 1414, 1415 (3.8). The last column's and row's art fills only the left 234 / top 156 px |
| `MapBackLand/` | 3, 256² | `<947\|1414\|1415>` | mask over the map's art rect: its land plus the coastal band (shallows, hatching) |
| `MapSeaMask/` | 3, 256² | `<947\|1414\|1415>` | mask: the continent map's open sea (only 1414/1415 are used) |
| `MapSeaOpen/947` | 1, 256² | | mask over 947's rect: the world art's open sea, away from the coasts |
| `MapSeaCoast/947` | 1, 256² | | mask over 947's rect: the world art's sea just off the coasts |
| `MapSeaOut/` | 2, 256² | `<1414\|1415>` | mask over the continent's rect: its sea past the world art's edges |
| `MapSeaField/` | 3, 256², 24-bit | `<947\|1414\|1415>` | colour: the smooth sea colour field of that map, stretched over its rect |
| `MapSeaFieldOut.tga` | 512², 24-bit | | colour: the sea colour carried out past the world, stretched over the outer-sea rectangle |
| `MapSeaDark.tga`, `MapSeaLight.tga` | 512² | | colour with alpha, repeat-wrapped: dark and light sea mottling |
| `MapHatch.tga` | 128 × 256 | | colour with alpha, repeat-wrapped: coastal wave strokes |
| `MapCoast/` | 2, 256² | `<1414\|1415>` | mask over the continent's rect: its coastal band |
| `MapLand/` | 3, 256² | `<947\|1414\|1415>` | colour (the continent's land as a smooth field, alpha = land) and also a mask of the land, over the continent's rect |
| `MapGrain.tga`, `MapTooth.tga` | 256² | | colour with alpha, repeat-wrapped: parchment grain and paper tooth |
| `MapPaper.tga` | 256², 24-bit | | colour, repeat-wrapped: blank map paper |
| `MapGapLand/` | 61, 256² | `<contMap>_<col>_<row>` | mask over one gap tile (64 world units square) |
| `MapGapMask/` | 2, 768 × 512 | `<1414\|1415>` | mask over the continent's rect: the gaps (only for the gap minimap, off) |
| `MapCoastArt/` | 19, 256² | `<Name>` (3.6 `art`) | mask over a gap-art rectangle |
| `MapFeather.tga` | 256² | | mask: a map's whole art rect, edges feathered (zone base art) |
| `MapFeatherThin.tga` | 256² | | mask: thin feather (overlays of an ungraded zone) |
| `MapFeatherWide.tga` | 256² | | mask: wide feather (world and continent art, sea fields, land) |
| `MapFeatherRound.tga` | 256² | | mask: round/oval feather (cities without a cut) |
| `MapBand/` | 44, 128² | `<zone>` | mask over the zone's art rect: its border band (strong at the outline, fading inward and a little outward) |
| `MapTerritory/` | 44, 256² (one 128²) | `<zone>` | mask over the zone's art rect: its territory (its land, just past it, any land in its rect, never sea) |
| `MapCore/` | 44, 128² | `<zone>` | mask over the zone's art rect: the zone's interior, from just inside its outline |
| `MapEdge/` | 43, 128² | `<zone>` (no 2521) | mask over the zone's art rect: the zone's own measured frame |
| `MapBannerHole/` | 4, 256² | `<zone>` | mask over the zone's art rect: everything but the city banner |
| `MapBanner/` | 4 (512×128, 256×64, 512×64 ×2) | `<city>` | colour: the banner art |
| `MapCityMask/` | 3, 256² | `<city>` | mask over the city map's art rect: its plan |
| `MapCave/` | 44, 128² | `<caveMap>` | mask over the cave's art box |
| `MapMiniLOD/` | 205, 256² | `<cont>_<n>_<col>_<row>` | colour: minimap LOD pieces (3.4). Cont 0: 98 at n=4, 9 at n=16. Cont 1: 86 and 12 |
| `MapZones/` | 205, 512², BLP2 (DXT, 8-bit alpha, mips) | `<i>_<j>` | colour: the baked zone tiles (3.11) |
| `MapZoneBorder/`, `MapZoneLand/` | 43 each | `<zone>` | only for the "dim" unexplored style, which AzerothGPS never uses (section 9.4). Keep or drop |

Texture coordinate conventions:

- **Base art tiles** (world, continents, zones, cities, gap art, caves): every file is a full 256² tile. The tile in
  column k (from 1) of an art w px wide is pw = 256 px wide, except the last, pw = w − 256·(cols − 1). It is drawn
  pw·sx world units wide, with texture coordinates 0 … pw/256 (and the same vertically). Its world position is the
  art px offset (k − 1)·256 converted by 2.1.
- **Overlay piece tiles**: the same, except that a piece's last column or row file is the next power of two of the
  leftover size (at least 16). So the last-column texture coordinate is pw / pow2(pw), not pw / 256.
- **Repeat-wrapped patterns** (sea mottling, hatching, grain, tooth, paper): the texture coordinates are world
  coordinates over the pattern's period in world units, plus a per-pattern offset (given with each layer). So the
  pattern is fixed to the world and a pan moves it with the map.

---------------------------------------------------------------------------------------------------------------------

## 5. Structure and draw order

All art lies in one host frame the glue owns. The host clips its children to the map's canvas box, and its alpha is
the seamless blend. The engine gets a base frame level **L** (the host's level + 1) and **80 levels** above it
(`A.ART_RANGE`; the map reserves `ART_RANGE + 4` = 84 levels under its own canvas, `G.ArtSpan`). It also gets one
level for icons, L + 81, which the engine leaves empty in AzerothGPS.

Bottom to top (frame-level offset from L; within a level, draw layer and sublevel):

| # | Offset | Layer / sublevel | What (section) |
|---|---|---|---|
| 1 | +0 | BACKGROUND −8 | Outer sea colour field (6.1) |
| 2 | +0 | BACKGROUND −7 | Outer sea mottling, dark and light (6.1) |
| 3 | +0 | BACKGROUND −6 | World sea colour field (6.2) |
| 4 | +0 | BACKGROUND −5 | Continents' sea colour fields (6.2) |
| 5 | +0 | BACKGROUND −4…−1 | Sea mottling octaves (6.3) |
| 6 | +0 | BACKGROUND 0 | World art (land part, open-sea part, coast part) and the continents' outer sea (6.4) |
| 7 | +1 | ARTWORK 0 | Continent art, land part and open-sea part (6.5) |
| 8 | +1 | ARTWORK 1 | Coastal hatching (6.5) |
| 9 | +1 | ARTWORK 2 | Land fill colour field (6.5) |
| 10 | +1 | ARTWORK 3, 4 | Gap paper, two layers (6.5) |
| 11 | +1 | ARTWORK 6 | Land grain, two octaves (6.5) |
| 12 | +2 | ARTWORK | Gap art (6.7) |
| 13 | +3 … +63 | ARTWORK 0 / 2 | Zone base art, one level per zone, largest zone lowest (6.6) |
| 14 | +64 | ARTWORK 0–3 | Zone overlays, every zone (6.8) |
| 15 | +65 | ARTWORK 0–1 | Zone interiors (6.9) |
| 15b | +65 | ARTWORK | Baked zone tiles, in place of 13–15 (6.10) |
| 16 | +67 … +70 | ARTWORK | Blur copies, four taps (6.11) |
| 17 | +71 | ARTWORK | Capitals on the surface (6.12) |
| 18 | +72 | ARTWORK −2 … 0 | Minimap detail: coarse LOD, fine LOD, native tiles (10) |
| 19 | +75 | ARTWORK | Underground capitals: Undercity 1458, Ironforge 1455 (6.12) |
| 20 | +76 | BACKGROUND | Underground dim (11) |
| 21 | +77 | ARTWORK | Cave maps (11); city banners (6.12) |
| 22 | about +78/+79 | ARTWORK (halo), OVERLAY (ink) | Continent and sea names (6.15) |
| 23 | +79 | OVERLAY 1–4 | Grain and tooth over everything (10.5) |

Notes:

- Rows 1–6 are all in the base level. Their order inside it is by draw layer and sublevel only. Within row 6 the four
  parts are masked to areas that don't overlap, so their mutual order doesn't matter.
- Where two items share a frame level and draw layer (row 14 across zones, row 21's caves and banners), their order is
  not set by anything. The masks keep the overlap small or the alphas keep it invisible. The new engine may pick any
  order there.
- The names are the top art except the grain. They must be above the cities, banners and caves.
- A frame's alpha multiplies its regions' alphas. Layers are not composited first: at a host alpha under 1 the layers
  show through one another. That is the current look during the blend, and it must stay.
- Each "texture with a mask" applies up to three masks. Nothing here needs more than three on one texture.

---------------------------------------------------------------------------------------------------------------------

## 6. The layers

The placement in each subsection is in world units (2.1). Where a layer depends on a game call that fails or returns
nothing for a map (no art layer, no rectangle on 947), that map's part is skipped.

### 6.1 Outer sea

The sea runs well past the world art, so a wide or tall view shows more ocean and never the paper's edge.

- One `MapSeaFieldOut` texture stretched over the rectangle from (−1.5·W, −1.5·H) to (2.5·W, 2.5·H), i.e. the world
  plus 1.5 world widths/heights on every side (SEA_REACH = 1.5; visual tuning).
- Over it, `MapSeaDark` and `MapSeaLight` over the same rectangle, repeat-wrapped, alpha 1. Their period is the sea
  paper's first octave P₀ = 128 · kEK world units in both axes, where kEK = the Eastern Kingdoms map's world units
  per art px = (r − l)·W / 1002 for uiMap 1415. That is about 0.346, so P₀ ≈ 44.3. If 1415 has no rectangle, use
  128 · 0.4. There's no offset. The texture coordinates for the rectangle are x/P₀ and y/P₀ at its corners.
- Past this rectangle nothing is drawn (the map window's own dark backdrop).

### 6.2 Sea colour fields

For each of 947, 1414 and 1415 (whichever has art and a rectangle): `MapSeaField/<map>` stretched over that map's
whole art rectangle, through the wide feather (`MapFeatherWide` over the same rectangle). The world's is at
BACKGROUND −6 and the continents' at −5, so the continents' fields fade into the world's at their feathered edges.
Alpha 1 at every zoom.

### 6.3 Sea mottling octaves

Four repeat-wrapped textures: dark, light, dark, light (sublevels −4, −3, −2, −1). They are laid over a box round the
view, not the world. That box is the view's centre ± 1.8 × (hu, hv). The pattern is fixed to the world, so the box is
only laid again when one of these happens:

- the detail zoom changed;
- the sea strength `m_s` changed;
- the view's ± 1.2 × half extents no longer fit inside the last box.

Strength: m_s = max(0, ws, wc), with ws and wc from 7.2 (it rises as the world art's sea and coast go).

Octaves: o = max(0, log₂(Zd / 4)). Let n = floor(o), f = o − n, div = 2ⁿ. With size = P₀ (6.1):

- textures 1 and 2 (dark, light): period size/div, alpha m_s·(1 − f), offset shift(n);
- textures 3 and 4 (dark, light): period size/div/2, alpha m_s·f, offset shift(n + 1);
- shift(k) = (0.37·k) mod 1, added to the u texture coordinate. Add 1.6 × that to the v coordinate.

The texture coordinates for a box (u0..u1, v0..v1) are u·W/period + shift and v·H/period + 1.6·shift. Each octave
keeps its own offset, so when the finer copy takes over at a doubling it is the same pattern in the same place. A
texture whose alpha is ≤ 0.01, or whose box is empty, is hidden.

### 6.4 World art (the world backdrop)

Azeroth's base art (947: its 12 tiles, all from `MapArt/947_<n>`) is drawn three times, each through the wide
feather over 947's rectangle plus one more mask:

- **land part**: masked by `MapBackLand/947` (land and coastal band);
- **open-sea part**: masked by `MapSeaOpen/947`;
- **coast part**: masked by `MapSeaCoast/947`.

Each continent's own base art (1414, 1415: `MapArt/<map>_<n>`) is also drawn here, at the world level, masked only
by `MapSeaOut/<continent>` (its sea past the world art's edges: compass roses, ship, serpent). It counts as part of
the world's sea.

Colour and alpha (m, wo, ws, wc from 7.2):

- the land part: desaturation 0.8·m, vertex colour (c, 0.97c, 0.92c) with c = 1 − 0.45·m,
  alpha (1 − 0.92·m)·(1 − wo);
- the open-sea part and the continents' outer sea: untinted (1, 1, 1), desaturation 0, alpha 1 − ws;
- the coast part: untinted, alpha 1 − wc.

A part at alpha ≤ 0.003 is hidden.

### 6.5 Continent layer

The whole layer's alpha is smoothstep(1.3 → 1.7) of Zd (hidden at ≤ 0.003). For each continent map that is a child
of 947 (`C_Map.GetMapChildrenInfo(947, Continent, true)`), placed over its rectangle on the world:

1. **Continent art** (ARTWORK 0), twice through the wide feather:
   - land part, masked by `MapBackLand/<map>`: desaturation 0.8·m, colour (c, 0.97c, 0.92c), alpha 1 − 0.92·m;
   - open-sea part, masked by `MapSeaMask/<map>`: the same tint, alpha (1 − 0.92·m)·(1 − sm).
2. **Coastal hatching** (ARTWORK 1): two `MapHatch` textures masked by `MapCoast/<map>`. They are laid with the sea
   (6.3), over the intersection of the sea box with the continent's rectangle. Let k = the continent's world units
   per art px. The periods are 34·k/div by 84·k/div (first texture) and half that (second), with
   div, f = the octave split of log₂(Zd / 7) (as in 6.3, but from 7). Alphas are 0.6·m_s·sqrt(1 − f) and
   0.6·m_s·sqrt(f), with no offset. Hidden when the box is empty or the alpha is ≤ 0.01.
3. **Land fill** (ARTWORK 2): `MapLand/<map>` stretched over the continent's rectangle, through the wide feather,
   vertex colour (0.96, 0.92, 0.84), desaturation 0.25. This is a smooth colour field of the continent's land with
   no ink strokes or names. Unmapped regions (Quel'Thalas, Gilneas …) stay land as the backdrop mutes.
4. **Land grain** (ARTWORK 6): `MapGrain`, repeat-wrapped, over the continent's rectangle, through the wide feather
   and the `MapLand/<map>` mask. It is drawn twice:
   - period 14 world units, offset 0, vertex alpha 0.55;
   - period 14 × 2.618 = 36.65, offset 0.37, vertex alpha 0.5.

   The texture coordinates run from offset to offset + width/period horizontally, and from 1.7·offset to
   1.7·offset + height/period vertically.
5. Alpha of the land fill and both grain textures: max(m, U), where U is how far a cave has surfaced (section 11; 0
   in normal use).
6. **Gap paper** (ARTWORK 3, 4): for each gap tile (col, row) of this continent (3.6), the tile's rectangle is
   x = l·W + col·64, y = t·H + row·64, 64 × 64 world units. Two `MapPaper` textures over it, repeat-wrapped,
   masked by `MapGapLand/<map>_<col>_<row>` and the continent's wide feather:
   - period 21.62, offset 0, vertex alpha 1 (sublevel 3);
   - period 21.62 × 2.618, offset 0.41, vertex alpha 0.5 (sublevel 4).

   Texture coordinates: x/period + offset … (x + 64)/period + offset, and y/period + 1.7·offset …. They use absolute
   world x, y, so the paper is continuous across tiles. The texture alpha is the zone detail d (7.4). The zone art
   fades into this paper at its frame.

### 6.6 Zone base art (live layers)

Zones are the maps returned by `C_Map.GetMapChildrenInfo(947, Zone, true)`, sorted by their rectangle's area,
largest first. Zones with no rectangle (area 0) are skipped. A zone that has overlay pieces (explored or in the
Reveal data) is a **zone**. One with none is a **city** (6.12). In this client the capitals are the cities.

Each zone's base art (its 12 tiles from `C_Map.GetMapArtLayerTextures(map, 1)`, or art edits if any) gets a frame
level of its own. The first zone (largest) is at L + 3, and each next one is one level higher, capped at L + 63. So
smaller zones lie over larger ones. Each tile:

- masked by `MapFeather` over the zone's rectangle, and (graded zones) by `MapTerritory/<zone>`. In this client a
  zone's base art is mostly blank parchment. It shows on the zone's territory: its land, just past it, and any land
  in its rectangle, never sea. It fills the seams between zones.
- graded zones also get a **colour-match copy** (sublevel 2; the plain copy is sublevel 0). The copy is the same
  tile, masked by `MapFeather` and `MapBand/<zone>`, with colour from 8.1.
- These textures are shown only while the live layers are (7.5) and near the view (12.3). They get their file lazily
  and fade in (12.2).

### 6.7 Gap art

For each entry of the Gaps data's `art` list: its 12 tiles over its rectangle (as a 1002 × 668 art with 256 px tiles,
sx = (r − l)·W/1002, sy = (b − t)·H/668). Tiles whose file is 0 are not drawn. All are masked by
`MapCoastArt/<name>` over the rectangle. It is drawn at L + 2 with the live layers: it shows only while they do, at
alpha d, and it's in the baked tiles otherwise. Files are set at build time.

### 6.8 Zone overlays (live layers)

All zones' overlay pieces are in one level, L + 64, drawn whole, with their parchment halos. Each piece is drawn tile
by tile at the piece's art px offset, through:

- the zone's frame mask: `MapEdge/<zone>` for a graded zone that has one, else `MapFeatherThin`, both over the zone's
  rectangle;
- `MapBannerHole/<zone>` for the four banner-hole zones (3.10);
- for graded zones, a colour-match copy with `MapBand/<zone>` (instead of a second mask).

Sublevels: explored pieces at 1 and unexplored ones at 0, so explored art lies over unexplored where they overlap.
Each colour-match copy is 2 above its piece (2 or 3). Alpha is the live layer alpha (7.5). Hidden pieces: 9.2.

### 6.9 Zone interiors (live layers)

Graded zones only. The overlays are drawn again at L + 65, through the zone's frame mask (as 6.8), the banner hole
where there is one, and `MapCore/<zone>`. There's no colour-match copy, and the same sublevels by explored/unexplored.
Every zone's own land so lies over its neighbours' parchment halos. Layer alpha: when the live layers show,
max(0, (d − 0.3) / 0.7), where d is the detail alpha (7.4). Otherwise 0. It is hidden at ≤ 0.003.

### 6.10 Baked zone tiles

The zones' layers 6.6–6.9 (and the gap art) pre-rendered at grade strength 1, desaturation 0.1, with every area
shown, as 205 world tiles (3.11). They are drawn at L + 65 **in place of** the live layers when they can be:

- **Used** only while the grade is exactly strength 1 and desaturation 0.1 (within 0.001), the unexplored style is not
  "hide", and the Zone Art data is present. In AzerothGPS that means: always, unless "Show Only Explored Areas" is on.
- Layer alpha: round100((1 − (1 − d)²) · (1 − g)). Here d is the detail alpha, and g is the live share (7.5), or 0
  while holding. The square is because the live layers stack two copies (base art and overlays), each at d, which
  cover 1 − (1 − d)² of what's under them. The baked tiles are both in one, so they're drawn that strong.
- Each tile is created the first time it's near the view (12.3) while this layer shows, and its file is set at once
  (no fade-in). After that it's shown or hidden by nearness.

### 6.11 Blur copies (close zoom)

Only when the soft amount σ (7.2) is over 0.01: every graded zone whose rectangle meets the view box gets four
shifted copies of its interior (its overlay pieces through its frame mask and `MapCore`, as 6.9). The copies are
offset diagonally by ±0.6 art px (×sx, ×sy): (−,−), (+,−), (−,+), (+,+), where + is right/down. The copy frames are at
L + 67 … L + 70 with frame alphas 1/2, 1/3, 1/4, 1/5. Over the interior, that makes an even five-tap average.

The copies are built the first time a zone needs them, and a zone's copies are hidden when it leaves the view box or
σ drops to 0.01. Their parent layer's alpha is d·σ. Their textures follow the zone textures' rules (grade, explored,
lazy files, fade-in), and they show whatever the live/baked state.

### 6.12 Cities

Every city (a zone-type map with no overlay pieces) gets its base art drawn over its rectangle. Its mask is
`MapCityMask/<city>` for the cut cities (3.10), else `MapFeatherRound`. There is no colour-match copy. Cities are
at L + 71, except the underground ones, Undercity (1458) and Ironforge (1455), at L + 75 (over the minimap detail,
which shows the surface there).

- **Alpha**: Zc = 1 / (r − l), the zoom at which the city's rectangle fills the view's width (roughly). The alpha is
  smoothstep(a·Zc → b·Zc) of Zd, with (a, b) = (0.08, 0.25) for Orgrimmar 1454 and Thunder Bluff 1456, else
  (0.2, 0.4). Worked from Data/Maps.lua's bounds (expect small differences in game):

  | City | Zc | Fade Zd |
  |---|---|---|
  | Stormwind | ≈ 25.7 | 5.1 → 10.3 |
  | Orgrimmar | ≈ 32 | 2.6 → 8.0 |
  | Thunder Bluff | ≈ 43 | 3.4 → 10.8 |
  | Ironforge | ≈ 56.5 | 11.3 → 22.6 |
  | Darnassus | ≈ 42.4 | 8.5 → 17 |
  | Undercity | ≈ 46.6 | 9.3 → 18.6 |

- Its textures load lazily and fade in, starting once the zone detail starts (d > 0.001) and the city is near.
- **Found**: a city has no pieces of its own. It counts as found when no zone's piece covers its rectangle's centre,
  or when at least one piece covering it is explored. A piece covers it when the centre, in that zone's art px, is
  inside the piece's x … x + w, y … y + h. Every zone with pieces is checked. All of a city's textures share one
  "unexplored" state for 9.2.
- **Banners** (the four cities in 3.10): one texture, `MapBanner/<city>`, placed over its zone's art at (x, y),
  w × h art px (via 2.1 with the zone's rectangle), at L + 77. Alpha round50(d·(1 − out)), where
  out = smoothstep(0.25·Zc → 0.4·Zc) of Zd for the cities with a title, else 0. Alpha 0 when unexplored areas are
  hidden and the city is unfound.

### 6.13 Minimap detail

Section 10.

### 6.14 Caves

Section 11.

### 6.15 Continent and sea names

For each label (3.9), lettered live in the client's standard font (`STANDARD_TEXT_FONT`), placed on the world through
the label's map (2.1). The lettering is built the first time its alpha goes over 0.01.

- **Fade** (round100): land labels 1 − smoothstep(3 → 4) of Zd; sea labels 1 − smoothstep(3.5 → 5). Hidden at
  ≤ 0.003 and when off the view (12.3).
- **Text and lines**: the client's name (3.9). If its word count equals the label's line count, each word goes on its
  own line, in order. Otherwise the whole name goes on the widest line.
- **Units**: a line's left, right and baseline (art px of the label's map) go to world units by 2.1. Its cap height C
  is capHeight·sy world units. The lettering is laid out in a frame scaled to 1/4, so font sizes are given in quarter
  world units. It scales with the map like everything else.
- **Letters**: one font string per character (UTF-8 aware). Single-byte characters are upper-cased.
  - Font size: (C / 0.69) for the first letter of each word, and for every letter of a small-caps line. Every other
    letter is (C / 0.69)·0.78. 0.69 is the font's capital height in font sizes; 0.78 is the small capitals' size,
    measured on the art.
  - A space is a gap 0.4·C wide and starts a new word.
  - Ink colour ink/255 with alpha 0.9, no shadow.
- **Spacing**: g gaps between glyphs (spaces count as glyphs). The tracking is max(0.1·C, (lineWidth − sum of glyph
  widths) / g), so the name is set wide across the art's line and centred on it. The glyphs are laid left to right
  from centre − (total + tracking·g)/2. Each glyph's vertical middle is 0.36·size above the baseline.
- **Halo**: behind each glyph, two rings of copies in the glow colour (text and shadow both glow colour). Ring 1 has
  radius 0.07·C and strength 1. Ring 2 has radius 0.15·C and strength 0.45. Each ring has 8 taps round the circle. A
  copy's shadow is offset to the opposite tap, so each ring takes 4 font strings, at angles 0°, 45°, 90°, 135°.
  Per-copy alpha: min(1, strength·glowA/8·2). The halo is drawn under the ink.
- **Rest while moving**: when the view changes on three frames in a row (each change within 0.1 s of the last), the
  halos are hidden. They come back once the view has been still for 0.15 s. The ink always shows.
- **Culling box** for a label: the union of its lines' boxes (baseline up by C), widened by half its width on each
  side and by its full height above and below.

### 6.16 Not drawn in AzerothGPS

These are not drawn and are not part of the spec:

- the engine's own icons (dungeon entrances, docks, pins, lines, paint marks, its own player arrow);
- the "dim" unexplored style (9.4);
- the minimap in the gaps (10.4).

AzerothGPS draws its own icons, route and player above the art.

---------------------------------------------------------------------------------------------------------------------

## 7. Zoom: the stages and fades

### 7.1 AzerothGPS's blend (GPSFrame, unchanged)

Let Zy be the map's zoom: yards from the middle to the long side's edge. Zr = Zy / ZoomScale, where
ZoomScale = max(1, long side px / 450). As shipped (issue #90, the knobs as tuned in testing): ZOOM_STEP = 1.16 per wheel
notch, SEAM_TERRAIN_ZOOM = 1000, SEAM_SHARP_NOTCHES = -8, SEAM_ART_NOTCHES = SEAM_TILES_NOTCHES = 1,
SEAM_WORLD_NOTCHES = 0.

| Zr (yd) | Art alpha | Tiles alpha |
|---|---|---|
| ≤ 305 | 0 (host hidden) | 1 |
| 305 → 354 | smoothstep | 1 |
| 354 → 410 | 1 | 1 − smoothstep |
| ≥ 410 | 1 (the art alone: no tiles, no roads or walls unless the tools are on) | 0 |
| > 410 | 1, and only a continent map's icons (`view.seamFar`) | 0 |

The host alpha is art alpha × the map's fade-while-moving. The view is north-up while the art alpha > 0. The furthest
zoom is the whole world with a margin of 0.85 (`G.WorldZoom`, ≈ 19,070 yd: its far edges just off the map). The art is
not drawn on dungeon levels, cave maps, inside maps, the map styles, while browsing, or while a game holds the map.

The engine is told the detail zoom Zd no greater than the `closeUpFrom` knob (8) and Zp scaled with it
(Atlas.lua `A.TellZoom`): on AzerothGPS's map the art past the tiles is the zones' map, sharp, never the close-up of
7.2's `soft` and 10's minimap. The canvas is still placed by the real zoom.

### 7.2 The engine's fades (all in Zd unless noted)

| Name | Range | Quantised | Drives |
|---|---|---|---|
| continent layer | 1.3 → 1.7 | no | whole continent layer alpha (6.5) |
| sm (continent sea out) | 1.2 → 1.9 | floor20 | continents' open-sea part (6.5) |
| wo (world land out) | 1.7 → 2.2 | floor20 | world land part (6.4) |
| detail hint | 1.8 → 3 | weight 0.3 | d (7.4) |
| detail | 3 → 4.5 | weight 0.7 | d (7.4) |
| wc (world coast out) | 3 → 5 | floor20 | world coast part; sea strength |
| land names out | 3 → 4 | round100 | land labels |
| sea names out | 3.5 → 5 | round100 | sea labels |
| m (mute) | 4 → 7 | floor20 | backdrop tint and alpha, land fill, sea strength |
| ws (world sea out) | 4 → 7 | floor20 | world open sea; sea strength |
| sea octaves | from 4, doubling | — | 6.3 |
| hatch octaves | from 7, doubling | — | 6.5 |
| σ soft | 8 → 18 | no | blur copies, grain (10.5) |
| cities | a·Zc → b·Zc | no | 6.12 |
| banners out | 0.25·Zc → 0.4·Zc | round50 (with d) | 6.12 |
| minimap mix | Zp 20 → 34, then 30 → 48 | no | 10 |

All of these are visual tuning. Their values are as written here, and QA's stage readings (SM1) depend on them.

The player's stages (AzerothGPS's Options > Map, OpenMap; `E.STAGES`, set by Atlas.lua's `A.SetStages`) move two groups of these: "world" (continent layer, sm, wo) and "zone" (both parts of d, wc, m, ws, the land and sea names). Each group's ends are taken as k·c·(x/c)^w, c its middle (`E.STAGE_MID`: zone 3, world 1.5), k the move on Zd and w the width (0: a sharp switch at c); an end past 0.95 × closeUpFrom is kept there. Unset (the default), every value is exactly as in the table.

The quantised values (floor20) only change in steps of 0.05. The backdrop parts are recoloured only when one of m,
sm, wo, ws or wc changes. That is a performance rule, and it is also why the backdrop steps rather than glides; keep
the quantisation.

### 7.3 What AzerothGPS reaches

For a square 450 px map: K ≈ 0.816 and Zp ≈ 22,400 / Zy.

| Zr (yd) | Zp | Zd | What shows |
|---|---|---|---|
| 305 (art starts) | ≈ 73 → 9.8 told | ≈ 60 → 8 told | zones fully in, backdrop fully muted; σ = 0 (the cap) |
| 410 (tiles gone) | ≈ 55 → 9.8 told | ≈ 45 → 8 told | the zones' map alone, sharp (no softening, no minimap) |
| ≈ 2,290 | ≈ 9.8 | ≈ 8 | the cap's end: zoomed out further the real zoom is told |
| 4,000 | ≈ 5.6 | ≈ 4.6 | zones at full detail (d = 1 from 4.5) |
| 6,000 | ≈ 3.7 | ≈ 3.0 | detail down to its hint (d = 0.3), names coming in |
| ≈ 19,070 (world) | ≈ 1.2 | ≈ 0.96 | the world art alone, names at full |

In general Zp = (long side px / (2·Zy)) · (yards per world unit) / min(w/W, h/H), where yards per world unit is about
44.7 and Zy is in this map's yards. A map up to 450 px on its long side keeps the square's numbers. A bigger map
reaches lower zooms: at 1054 × 450, the art starts at Zd ≈ 3.0, so the zones are never at full detail there. A wide,
short map reaches higher ones: at 450 × 120, Zp ≈ 22 and Zd ≈ 14 at the art's start, so the blur, grain and first
minimap mix show. So the whole close-zoom behaviour (10, 11) must be implemented, even though the default map never
shows it.

### 7.4 The detail alpha d

d₀ = 0.3·smoothstep(1.8 → 3) + 0.7·smoothstep(3 → 4.5), both of Zd. Then d = d₀·(1 − 0.75·U), where U is the cave
focus (section 11). d is the alpha of the zone base art and overlays (live), the gap paper and the gap art, and the
input to the interiors, the baked tiles, the blur and the banners.

### 7.5 Live layers vs baked tiles

When the baked tiles are used (6.10), whether the live layers come in is measured in **screen pixels per baked
pixel**:

ρ = (the root's effective scale) × (physical screen height / 768) / 16

That is the physical px per world unit over the baked tiles' 16 px per world unit (use `GetPhysicalScreenSize`).

- **Live share** λ = round50(smoothstep(1.2 → 1.6) of ρ).
- **Warm**: ρ ≥ 1.02 (0.85 × 1.2). From then the live layers are on at full under the baked tiles, so their files
  load before they're needed.
- **On** (the live layers show at all): d > 0.001 and (λ > 0 or warm). When baked tiles are not used, λ = 1 (on
  whenever d > 0.001).
- The live layers' alpha is d while on, else hidden. The baked layer's alpha is
  round100((1 − (1 − d)²)·(1 − λ)) (6.10).
- **Holding**: when the live layers first switch on while baked tiles are used and files are still loading, the baked
  layer stays as if λ = 0. Otherwise the zones' bare parchment (the first files to arrive) would flash between the
  two. Holding ends when the load queue is empty (12.2).

In AzerothGPS with the default UI scale, ρ stays well under 1 (≈ 0.36 at the art's start on a 450 px map at
1080p). So with every area shown, the zones are the baked tiles, and the live layers appear only with "Show Only
Explored Areas".

---------------------------------------------------------------------------------------------------------------------

## 8. Colour

### 8.1 The grade

The glue sets the grade as (strength = 1, desaturation = 0.1, unexplored = "show" | "hide") when the art is first
attached and whenever the setting changes. The engine applies it to:

- every zone and city texture (base art, overlays, interiors, blur copies, cities): vertex colour (1, 1, 1, 1),
  desaturation 0.1;
- every colour-match copy, for zone Z with Grade (gr, gg, gb): vertex colour (1 + (gr − 1)·strength, …) = (gr, gg,
  gb) at strength 1, desaturation 0.1. Copies are shown only while strength > 0. The copy is masked by the zone's
  border band, so the zone's colours shift toward the shared palette fully at its outline and fade inward;
- the texture's own alpha stays its load fade-in (12.2).

The baked tiles already carry this grade (3.11). That is why they're used only at exactly these settings.

### 8.2 Backdrop mute

Sections 6.4 and 6.5: as the zones come in, the world and continent art goes to desaturation 0.8, colour (0.55,
0.53, 0.51) and alpha 0.08 at m = 1, so only a hint of it is left. The land fill takes over the land.

### 8.3 Land fill

Colour (0.96, 0.92, 0.84), desaturation 0.25, toward the zone art's parchment (6.5).

### 8.4 Minimap tint

Section 10.3.

---------------------------------------------------------------------------------------------------------------------

## 9. Explored and unexplored

### 9.1 The source

Section 3.1: the game's explored pieces per zone (`C_MapExplorationInfo.GetExploredMapTextures`) against the Reveal
data's full list (by `C_Map.GetMapArtID`). These are read when the art is built. The engine reads them again on
`MAP_EXPLORATION_UPDATED` (the glue registers the event and forwards it). After that, each piece's state is updated
by its key, the cities' found state (6.12) is worked out again, and if anything changed the grade is applied again.
A newly explored piece keeps the textures it has. Its art is the same and only its state changes; its sublevel
doesn't move.

### 9.2 "show" (the default)

Every piece, explored or not, is drawn. Explored and unexplored pieces differ only in sublevel (6.8).

### 9.3 "hide" (Options > Map: Show Only Explored Areas, `gps.seamExploredOnly`)

- The baked tiles aren't used (6.10). The live layers draw instead.
- Every unexplored piece is not drawn, in the overlays, interiors, blur copies and their colour-match copies. Where a
  zone has no explored piece, its **base art** (blank parchment on its territory) shows, as on the game's own world
  map. The gap paper, land fill and backdrop are unchanged.
- An unfound city (6.12) is not drawn, and neither is its banner.
- The continent and world art are not affected. They still show the whole continent at the zooms where they lead
  (Zd < 4, muting until 7).
- AzerothGPS's terrain tiles never change.

### 9.4 "dim"

A third style (unexplored land shaded dark) exists in the old engine. AzerothGPS never sets it, so it is out of scope.

---------------------------------------------------------------------------------------------------------------------

## 10. Close zoom: the minimap detail

Everything in this section and the next is worked out on every view change: centre (u, v), half extents (hu, hv),
Zd, Zp.

### 10.1 The mix

These are the settings AzerothGPS runs with (fixed, no options): minimap on, strength 0.45, deepest 0.85, "from"
zoom 20, soften on, caves on, gap minimap off.

1. mix = 0.45 · smoothstep(20 → 34) of **Zp**.
2. mix = mix + (0.85 − mix) · smoothstep(30 → 48) of **Zp**.
3. Over an underground capital (1458, 1455): mix = mix · (1 − cover). Here cover is how much of the point is inside
   the city's own rectangle, eased off toward its edges: for the city containing (u, v), the smaller of its distances
   to the rectangle's sides as a share of the half-width (and half-height), e. Cover = city alpha × min(1, 2.5·e),
   and the most covering city wins.
4. Over a surface capital: if mix > cap, mix = mix + (cap − mix)·cover, with cap = 0.15 for Orgrimmar and Thunder
   Bluff, else 0.5, and cover as in step 3 for the non-underground cities.

### 10.2 Which tiles

For each continent whose map rectangle overlaps the view box (both can be in view):

1. Convert the view box's corners to that continent's yards (2.2). Find the tile range tx0..tx1, ty0..ty1 covering
   it (2.3). count = (tx1 − tx0 + 1)·(ty1 − ty0 + 1) and across = the larger of the two spans.
2. Shares: native share wn = smoothstep(64 → 36) of count when count ≤ 64 (else 0); when there's no LOD data it is 1
   at count ≤ 64. Fine share φ = smoothstep(40 → 24) of across.
3. Alphas, which stack coarse under fine under native and add up to the mix:
   - native a₃ = mix·wn;
   - fine LOD a₂ = mix·(1 − wn)·φ / (1 − a₃) (0 when a₃ ≥ 1);
   - coarse LOD a₁ = mix·(1 − wn)·(1 − φ) / max(0.001, (1 − a₂)(1 − a₃)).
4. **LOD pieces** (first list entry = fine, alpha a₂, sublevel −1; second = coarse, a₁, sublevel −2), each drawn when
   its alpha > 0.005: every listed piece whose col and row are within floor(tx0/n)..floor(tx1/n),
   floor(ty0/n)..floor(ty1/n). Each is placed over its yards box (3.4, 2.3) projected to (u, v), with desaturation
   0.35, **no tint** (white), alpha min(1, a), masked by `MapLand/<continentMap>` over the continent's rectangle.
5. **Native tiles** (sublevel 0) when count ≤ 64 and a₃ > 0.005: every tile in range with a file in the Minimap data,
   placed over its yards box. Desaturation 0.35, tint per 10.3, alpha a₃, the same land mask.
6. Tiles and pieces not wanted any more are hidden and released.

### 10.3 Native tile tint

Find the tone of the deepest map at the tile's centre: the zone chain (11.4) → the Tones data for its last map →
default (0.56, 0.45, 0.17). Normalise the tone by its largest component (at least 0.001). The tint is
paper + (normalised − paper)·0.25 per channel, with paper = (1, 0.93, 0.80). This is set when the tile is created.

### 10.4 Minimap in the gaps

Off in AzerothGPS (its alpha is 0, nothing drawn). Not needed.

### 10.5 Grain and tooth

Four repeat-wrapped textures over everything (L + 79, OVERLAY 1–4): grain octave 1, grain octave 2, tooth octave 1,
tooth octave 2. The strength is amount = max(σ, min(1.4, 1.4·U)). When amount ≤ 0.01, all four are hidden.
Otherwise they are laid over the view's centre ± 1.8·(hu, hv). That is only redone when hu or the amount changed, or
the view's ± 1.2 box left the last one.

- want = log₂(hu · 2 · W · 0.35), so a mottle tile is about a third of the view. Let n = floor(want), f = want − n.
- Grain period 2^(n + octave − 1) world units. Tooth period the same divided by 6.
- Alpha: (octave 1: 1 − f; octave 2: f) × amount × (grain 0.7, tooth 0.9). The client clamps at 1.
- The texture coordinates are world x, y over the period, with no offset.

---------------------------------------------------------------------------------------------------------------------

## 11. Caves (underground)

- The continent at the view's centre comes from the zone chain (11.4) at (u, v): the first map in it that is 1415 (0)
  or 1414 (1). It can be cached until the centre moves 0.002 in u or v.
- **Which caves**: maps from the Caves data on that continent, except 34 and 35 (Blackrock Mountain's deeper floors).
  For each name only the lowest map ID counts (one floor per place). Each cave's box is its yards box projected to
  (u, v): the (maxX, maxY) corner and the (minX, minY) corner, min/max per axis. A cave counts when its box overlaps
  the view box.
- **Surfacing**: fill = (2·hu) / (cave box width in u), i.e. view width over cave width. t = 1 − smoothstep(1.05 →
  start) of fill, with start = 4 for map 33 (Blackrock Mountain, seen from further out) and 1.5 for all others. A cave
  with t > 0.01 is shown at frame alpha t. Its art is 12 tiles laid as a 1002 × 668 picture over the box: column c
  and row r (from 0) at box left + c·(box width/(1002/256)), with width scaled by pw/256 and texture coordinates
  0..pw/256 (likewise vertically). It is masked by `MapCave/<id>` over the box, and files are set when built. Caves no
  longer qualifying are hidden.
- **Focus** U = the largest t·(1 − smoothstep(0.35 → 0.8) of off) over the shown caves. Here off = max(|cave centre
  u − u| / hu, |cave centre v − v| / hv). Only the cave you're centred on darkens the world.
- **Dim**: a flat colour (0.05, 0.035, 0.02) over the view's centre ± 1.5·(hu, hv), at L + 76 BACKGROUND (under the
  cave art), alpha 0.45·U. Hidden when U ≤ 0.01.
- U also scales the detail alpha (7.4: × (1 − 0.75U)), raises the land fill (6.5: max(m, U)) and feeds the grain
  (10.5).

In AzerothGPS the caves essentially never surface: the view is at least about 5,000 yd across where the art shows,
and the largest cave is under 900 yd. Only a narrow, tall map over Blackrock Mountain could just start to (t ≈ 0.02).
Implement the rule anyway, to keep the picture identical.

### 11.4 The zone chain at a point

Used for tints, caves' continent and QA's spot check. Start with [947] at (u, v). Repeat up to 4 times:

1. Ask `C_Map.GetMapInfoAtPosition(current, x, y)`.
2. Stop if it gives nothing, or the same map, or a map whose type is neither Continent nor Zone, or whose rectangle on
   the current map (`C_Map.GetMapRectOnMap(child, current)`) isn't valid.
3. Otherwise, rescale (x, y) into the child's rectangle and append the child.

The result is the list from the world down, e.g. { 947, 1415, 1420 }. Its last element is "the deepest map".

---------------------------------------------------------------------------------------------------------------------

## 12. Loading, memory and performance

### 12.1 On and off

- The seamless map is the default map style (`gps.style = "seamless"`, issue #75). Its data and code are loaded at
  PLAYER_LOGIN only when that style is picked. Off, they are dropped at login, and the memory left must equal the glue alone. Today's test allows under 16 KB
  difference (`test_off_the_memory_left_is_none_of_the_stitched_maps`). The current method is that every data and
  engine file only registers a function, and the functions run or are let go at login. Any method that meets the test
  will do.
- Turned on mid-session, it waits for a /reload. The glue's prompt and its secure Reload UI button stay as they are.
- The art is **built** once, the first time the map zooms out to it (the glue's attach), on the host frame. If
  Azeroth's art layer can't be read, the build fails. The glue then marks it failed, hides the host and prints once,
  and the map works as if it were off.
- Nothing is saved. There are no saved variables of the engine's own.

### 12.2 Lazy files and fade-in

- **Lazy** (file set only when wanted): every zone and city texture (base art, overlays, interiors, colour-match
  copies, blur copies, cities). A texture is wanted when its zone is in the cull box, the texture's own rectangle is
  in the cull box, its layer can show (the live layers on, or for the others always), and the zone detail has
  started (d > 0.001).
- **Queue**: wanted textures are queued and given their files at most **40 per frame**. Each one, as it gets its
  file, goes to alpha 0 and fades to 1 over **0.3 s** (smoothstep in time). Done in a frame that runs only while there
  is work. When the queue and the fades are done, holding ends (7.5).
- **Set at build**: the sea, world and continent backdrops, land, grain, gap paper and gap art. Set when first near:
  baked tiles, cave art and minimap/LOD tiles (no fade). The labels are lettered when first visible.

### 12.3 Culling (nothing far off is shown)

- **Cull box**: the view box plus 35% of its size on every side. It's kept while the view stays inside it with 10% of
  the view's size to spare and hasn't zoomed in more than 1.6× since. Otherwise it's made again.
- Shown only when their rectangle meets the cull box: each zone's textures (tile by tile), each city, each gap paper
  tile, each gap art block, each baked tile, each label.
- A hidden texture should also stop being laid out by the client (the old engine un-anchored hidden zone textures and
  their masks, because a pan or zoom lays out everything anchored to a scaled frame, hidden or not). Thousands of
  hidden anchored textures cost as much as visible ones. The new engine must keep a pan or zoom from touching textures
  far off, however it does it.

### 12.4 Sizes and budget

- Regions at build: about 4,000 textures and a few hundred masks. This is an estimate: 44 zones × 24 base tiles, about
  540 pieces × about 1.6 tiles × 3 copies, about 100 backdrop tiles, gaps, cities. Only those near the view have files
  or are shown.
- The glue applies a view only when centre, zoom or box size changed. Every engine step per view change is O(things
  near the view), plus cheap loops over zones and cities (about 50).
- The backdrop recolouring runs only on a quantised step (7.2).
- The redraw's cost is measured as "redraw: seamless art" (`/agps debug perf`, `agps perf`; QA SM7: a small part of
  "redraw"). No ms figure is recorded in the repo. Measure the old engine before switching, and the new one must not
  be worse (issue #61's acceptance), nor its memory once built.
- Load at most 40 files per frame (12.2). Never build all of a zone's textures' files in one frame.

---------------------------------------------------------------------------------------------------------------------

## 13. Edge cases

- **The other continent**: the projection (2.2) handles both continents in one (u, v) space. The view's yards are in
  one continent's coordinates even when over the other. The glue's `A.ViewOfYards` and `G.SeamRebase` handle that.
  The engine draws both continents' art whatever the centre is, and the minimap detail checks both (10.2).
- **The sea**: there is art out to ±1.5 world sizes (6.1). `A.FromAtlas` returns nil more than 0.03 (u or v) outside
  every continent's frame. The zone hover uses AzerothGPS's own `Router.ZoneAt` (0 = sea → no label), not the engine.
- **Teldrassil and Rut'theran**: they're in Kalimdor's frame on the world map. Teldrassil (1438) is a graded zone
  with a banner hole for Darnassus. Darnassus (1457) is a city with the round feather and a banner that stays (no
  title), alpha d. QA SM2: Dolanaar and Rut'theran map into Teldrassil.
- **Zephras Isle** (uiMap 2991, zone 2521): on a map of its own. If the game gives 2521 a rectangle on 947, the
  engine places it like any zone. Otherwise there is no art there, only sea. Note that `MapEdge/2521` doesn't exist:
  if it's placed, its overlays should use the thin feather (as for a zone with no Edge mask). The glue gives the isle
  a frame by its rectangle, or `G.WORLD_INSETS`, for the projection only.
- **Underground cities** (Undercity, Ironforge): above the minimap detail, and the minimap mix is reduced over them
  (10.1). An AzerothGPS view on Undercity's level (10001) is projected through continent 0 (the glue).
- **Dungeon levels** (20000+): not on the art (`A.ToAtlas` → nil), and the map hides it.
- **Wide or tall boxes**: the fit is by the shorter way (2.4). The detail zoom uses K. The minimap uses Zp. The cull
  box, sea box and grain box use the box's own half extents.
- **Tiny map** (120 px): the same zooms as 450 px (ZoomScale ≥ 1). **Huge map**: lower zooms (7.3).
- **Map resized or moved to another box**: the host is re-anchored and the view applied again. The art isn't rebuilt.
- **Held by a game** (StreetView): the map never asks for the art (`G.Seamless` is false). The host stays hidden.

---------------------------------------------------------------------------------------------------------------------

## 14. Interface the glue needs

What `Atlas/Atlas.lua` and GPSFrame use the engine for. The names are the new engine's to choose. The glue changes
its calls to match.

| Need | Inputs → outputs | Used by |
|---|---|---|
| Build the art | host canvas frame, base level L, 80 levels, icon level → nothing. Afterwards a "built" check is true, or false if the world art layer couldn't be read | glue's attach |
| Lay out for the world | once after build: the art in world units on the canvas (canvas units = world units) | glue's attach |
| Show / hide | shown flag → nothing (the art and its empty icon layer) | glue's attach |
| World size | → W, H (world units: 947's art layer size, 1002 × 668) | glue: view maths, CheckMapping, CheckSeamless |
| Set the grade | strength, desaturation, unexplored style ("show"/"hide") → applies section 8.1/9 | glue's grade (after build, on the setting) |
| Explored again | → re-reads the explored pieces (9.1) | glue's MAP_EXPLORATION_UPDATED handler |
| Set zoom | detail zoom Zd (and the canvas scale, unused) → applies every zoom fade (7) | glue's apply-view |
| Set view | u, v, hu, hv, Zd, Zp → sea, culling, blur, minimap, caves, grain; also "the view moved" for the names' rest | glue's apply-view, after set zoom |
| Yards → (u, v) | continent 0/1, x, y → u, v or nil (2.2) | `A.ToAtlas`, `A.Projection`, `A.ViewOfYards` |
| (u, v) → yards | continent 0/1, u, v → x, y or nil | `A.FromAtlas` |
| Map rectangle | uiMap → l, r, t, b on 947 or nil (cached) | glue's isle frames |
| Zone chain | u, v → list of uiMaps from 947 down (11.4) | `A.CheckMapping` (QA's spot check) |

The glue's own view maths (`A.FitPx`, `A.DetailK`, `A.Place`, `A.ViewOfYards`, `A.FromFrame`/`A.ToFrame`,
`A.Frames`), its placement of the canvas (scale s, anchored so (u, v) is mid-box), the host's alpha, and
`A.CheckSeamless`/`A.CheckMapping` stay AzerothGPS's.

`app/tests/test_atlas.py` touches a few engine internals that will be renamed. It reads the engine's source for
texture names, checks the wrapping and licence headers, and calls a "close-up parts that failed" table, the build
check, and the namespace slot the engine registers in. Update those tests with the new engine, and keep what they
check: every named texture shipped, no part failed, nothing loaded when off.

Each per-view part (sea, culling, blur, minimap, caves, grain) must be independent: one failing (a client difference)
must not stop the others, and is reported once through the error handler. The test checks that none failed with the
stand-in API.

---------------------------------------------------------------------------------------------------------------------

## 15. Acceptance checks

These must still pass, or be updated only where they name old internals (section 14).

- `cd app && python -m pytest -q` (the full suite), in particular `test_atlas.py`:
  - files in the toc after everything else, and present;
  - the release zip takes the folder;
  - every texture the engine names is shipped;
  - no Blizzard art outside `Atlas/`;
  - off, nothing kept, memory within 16 KB of the glue alone;
  - on, the art builds and applies "show" and then "hide"/"show" for Show Only Explored Areas, and the exploration
    event is registered;
  - the view maths;
  - yards ↔ (u, v) and back for Stormwind, Brill, Ironforge, Orgrimmar, Thunder Bluff and Darnassus, with and without
    the engine's projection (agreement with `worldFrames` to 1e-9, the way back to 1e-6 yd);
  - `/agps seamless spots` with every spot under 0.01 px off and 0.01 yd back;
  - the blend per notch;
  - the art under the map's own projection within 1 px at 3000, 3600, 8000 and 20000 yd;
  - wheel out to the world (Zp < 1.2 there) and back to the tiles;
  - right-click overview;
  - heading-up turning north-up;
  - the other continent's yards;
  - Teldrassil, Rut'theran and Zephras from three starting views;
  - the zone hover;
  - held styles identical;
  - off as before.
- `test_lua_lint.py` (the new engine is linted like any addon file: no exemption for its folder),
  `test_every_addon_file_compiles_under_the_games_lua_5_1`, `test_map_redraw.py`.
- No file under `addon/`, `app/`, `docs/` or CLAUDE.md contains the upstream project's or its author's name (the grep
  in issue #61). `Atlas/LICENSE.txt` is gone.
- In game, from docs/ingame-tests.md:
  - **SM1**: the blend readings per notch, as before (art 0 / tiles 1 to 2,500 yd, gone by about 3,900, then the
    zones' art, the continents', the world's);
  - **SM2**: `/agps seamless spots`: each spot in its zone, 0 px off the frames, 0 yd back;
  - **SM3**: Teldrassil and Zephras terrain comes back;
  - **SM4**: hover;
  - **SM5**: Show Only Explored Areas;
  - **SM6**: StreetView Normal/Heroic/Mythic;
  - **SM7**: "redraw: seamless art" no worse.
- **Side-by-side pictures**: screenshots at the same spot and zoom in the old and new engine. Take them at the art's
  start (2,500 yd), at full art (3,125), with the tiles gone (3,906), at the world stage (6,104), at the whole world,
  and with Show Only Explored Areas on. Spots: Brill/Tirisfal (Undercity's banner), Durotar (Orgrimmar's cut and
  banner), Mulgore (Thunder Bluff), Teldrassil, the Barrens/Stonetalon gap paper and gap art, the Great Sea (names),
  and one wide 450 × 120 map over Elwynn (blur, grain, minimap mix). Screenshots stay out of git.

---------------------------------------------------------------------------------------------------------------------

## 16. Uncertain or worth checking

- **Same-level order**: within one frame level and draw layer the client's order isn't specified (zone overlays
  between zones; banners vs caves at L + 77; the names' exact level vs the grain). The old picture relied on whatever
  the client did. Compare the side-by-side pictures at zone borders.
- **Zephras Isle**: whether `C_Map.GetMapRectOnMap(2521, 947)` is non-nil in game is unknown here (the test stand-in
  says nil). If it is, its overlays name a `MapEdge/2521` mask that isn't shipped.
- **Font size limits**: the labels use very large font sizes in a quarter-scaled frame (Kalimdor's capitals are about
  116 font units). If the client clamps font sizes, the new engine must letter at the same sizes to match.
- **ρ (7.5)** uses the root frame's effective scale, which includes UIParent's scale and the map's own. In AzerothGPS
  it stays under the handover, so the handover is effectively never seen with the default UI. Very large UI scales
  could reach it.
- **Data file headers**: the data files and the texture set are kept, but each data file today carries the copy
  header naming the licence file and generator scripts that aren't in this repo. Re-wrap them without those headers
  when the old engine goes (they are data, not code).

---------------------------------------------------------------------------------------------------------------------

## Appendix A: current data table names

What each data file assigns today, in the engine's own namespace (the glue's `ns.Atlas.core`). The rewrite may rename
them.

| File | Table(s) |
|---|---|
| Reveal.lua | `MapReveal` |
| Grade.lua | `MapGrade` |
| Minimap.lua | `MapMinimap` |
| MinimapLOD.lua | `MapMinimapLOD` |
| Caves.lua | `MapCaves` |
| Gaps.lua | `MapGaps` (fields `tile`, `paper`, `[1414]`, `[1415]`, `minimap`, `art`) |
| Tones.lua | `MapTones` |
| ArtEdits.lua | `MapArtEdits` |
| Labels.lua | `MapLabels` |
| Banners.lua | `MapBanners`, `MapBannerHoles`, `MapCityCuts`, `MapCityTitles` |
| ZoneArt.lua | `MapZoneArt` (fields `px`, `size`, `step`, `desaturate`, `colorMatch`, `tiles`) |

## Appendix B: the new engine's names (issue #61, as written)

The data files were renamed and re-wrapped without any copy header; their contents are the same numbers. Each file
registers a chunk in `ns.AtlasChunks`, run by the glue at login with `D` (the data) and `E` (the engine).

| Was | Now (Atlas/Data) | Table(s) in `D` |
|---|---|---|
| Reveal.lua | Pieces.lua | `ArtPieces` |
| Grade.lua | BorderTints.lua | `BorderTints` |
| Minimap.lua | MiniTiles.lua | `MiniTiles` |
| MinimapLOD.lua | MiniMipmaps.lua | `MiniMipmaps` |
| Caves.lua | CaveMaps.lua | `CaveMaps` |
| Gaps.lua | Unmapped.lua | `Unmapped` |
| Tones.lua | ZoneTones.lua | `ZoneTones` |
| ArtEdits.lua | CleanArt.lua | `CleanArt` |
| Labels.lua | Lettering.lua | `Lettering` |
| Banners.lua | CityBanners.lua | `CityBanners`, `BannerCutouts`, `CityPlans`, `CityTitled` |
| ZoneArt.lua | BakedZones.lua | `BakedZones` |

The engine (Atlas/Engine), in load order: `Base.lua` (maths, map geometry, the projection `E.YardsToUV` /
`E.UVToYards`, `E.ChainAt`, sprites, the lazy-file queue), `Backdrop.lua` (6.1–6.7), `Zones.lua` (6.6–6.12, 8.1, 9),
`Detail.lua` (6.15, 10, 11), `Engine.lua` (the build `E.Build`, the fades `E.Fades`, `E.Handover`, the view
`E.SetView`, the cull box). The glue calls `E.Build`, `E.IsBuilt`, `E.SetShown`, `E.Size`, `E.Grade`, `E.Rescan`,
`E.SetView`, `E.YardsToUV`, `E.UVToYards`, `E.MapRect` and `E.ChainAt`. A per-view part that raises is kept in
`E.broken` (reported once).
