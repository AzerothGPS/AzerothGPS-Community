"""The seamless map's art (issues #49, #56, #57, #60, #61): AzerothGPS's stitched world map under its own map
(addon/AzerothGPS/Atlas/: its data, its engine, docs/atlas-spec.md). Its files listed in the toc and shipped in the
release zip; Blizzard's map art only in its folder; OpenMap named and credited only where meant (issue #91); off, nothing of its code is kept;
on, the art lies under the map's own projection and the wheel goes out to the whole world, under the game's Lua 5.1
with the stand-in UI (wowmock.lua)."""

import math
import re
from pathlib import Path

import pytest

ADDON = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS"
ATLAS = ADDON / "Atlas"
REPO = ADDON.parents[1]
IMAGES = {".tga", ".blp", ".png", ".jpg", ".jpeg", ".bmp", ".dds", ".webp", ".gif"}
# AzerothGPS's own art (agps media and the hand-made icons): the only images outside the Atlas folder
OWN_MEDIA = {"Dash.tga", "Device.tga", "Feather.tga", "MapMenu.tga", "Ship.tga", "Zeppelin.tga",
              "MinimapClear.tga"}  # (an all-clear mask for the minimap: test_map_redraw.py checks it is)


def toc_files():
    lines = (ADDON / "AzerothGPS.toc").read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith("#")]


def lua_files():
    """The Atlas's files as the toc lists them: the data, the engine, Atlas.lua last."""
    return [f for f in toc_files() if f.startswith("Atlas\\")]


def test_the_atlas_files_are_in_the_toc_in_order_after_everything_else():
    files = toc_files()
    listed = lua_files()
    assert files[-len(listed):] == listed  # (last: the rest of the addon loads as before)
    assert listed[-1] == "Atlas\\Atlas.lua"
    for f in listed:
        assert (ADDON / f.replace("\\", "/")).is_file(), f
    # every data and engine file listed: the data before the engine, the engine's parts in order
    on_disk = sorted(f"Atlas\\{p.parent.name}\\{p.name}" for d in ("Data", "Engine") for p in (ATLAS / d).glob("*.lua"))
    assert sorted(listed[:-1]) == on_disk
    data = [f for f in listed if f.startswith("Atlas\\Data\\")]
    assert listed[:len(data)] == data
    assert [f.split("\\")[-1] for f in listed[len(data):-1]] == ["Base.lua", "Backdrop.lua", "Zones.lua", "Detail.lua",
                                                                 "Engine.lua"]


def test_the_release_zip_takes_the_whole_folder_with_the_atlas_textures():
    # release.yml zips addon/AzerothGPS whole, leaving out only dot files, then checks every toc file is in it
    release = REPO / ".github" / "workflows" / "release.yml"
    if not release.is_file():
        pytest.skip("no release workflow in this repo (the maintainers' copy has it)")
    yml = release.read_text(encoding="utf-8")
    assert "zip -r -q \"../dist/AzerothGPS-$VERSION.zip\" AzerothGPS -x '*/.*'" in yml
    textures = [p for p in (ATLAS / "Media" / "Textures").rglob("*") if p.is_file()]
    assert len(textures) > 800
    assert not [p for p in ATLAS.rglob("*") if any(part.startswith(".") for part in p.relative_to(ADDON).parts)]
    assert not (ATLAS / "LICENSE.txt").exists()  # (issue #61: the engine is AzerothGPS's own, nothing copied)


def test_every_texture_the_engine_names_is_there():
    # Tex("MapZones", ...), GroupMask(z, f, "MapBand", ...) and the like in the engine: each folder or file shipped (as .tga or .blp)
    tex = ATLAS / "Media" / "Textures"
    names = set()
    for f in (ATLAS / "Engine").glob("*.lua"):
        src = f.read_text(encoding="utf-8")
        names |= set(re.findall(r'"(Map[A-Z]\w+)"', src))  # (every "Map..." string there is a texture's name)
    assert len(names) > 30
    for n in sorted(names):
        assert (tex / n).is_dir() or (tex / f"{n}.tga").is_file() or (tex / f"{n}.blp").is_file(), n


def _scaled_icon_bases():
    text = (ADDON / "Data" / "IconSizes.lua").read_text(encoding="utf-8")
    keys = re.findall(r'\["([^"]+)"\] = "[jt]\d+"', text)
    return {re.sub(r"[^a-z0-9_]", "_", k.replace("atlas:", "atlas_")) for k in keys}


def test_no_blizzard_art_outside_the_atlas_folder():
    # (CLAUDE.md: the Atlas view's map art is the one exception, 2026-10-16)
    stray = []
    for p in ADDON.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in IMAGES or ATLAS in p.parents:
            continue
        rel = p.relative_to(ADDON)
        own = rel.parent == Path("Media") and (p.name in OWN_MEDIA or re.fullmatch(r"(CornerLogo|IconRing)\d+\.tga", p.name))
        # (the coastline masks, issue #73: made from the terrain grid's numbers, white with only an alpha;
        # test_coast.py checks every one is)
        own = own or rel.parent == Path("Media/Coast") and re.fullmatch(r"\d+_\d+_\d+\.tga", p.name)
        # (the charms, Options > Window: our own small 3D models of the legendary weapons drawn as pixel art, made by
        # the charm tools, 2026-11-04; never a render of a game model)
        own = own or rel.parent == Path("Media/Charms") and re.fullmatch(r"charm_[a-z]+_s_[123]x\.tga", p.name)
        # (the second exception, 2026-11-16, CLAUDE.md: the map's game icons drawn at each size, iconscale.py; only
        # those Data/IconSizes.lua lists, test_icons_to_scale.py checks)
        own = own or rel.parent == Path("Media/Icons") and p.name.rsplit("_", 1)[0] in _scaled_icon_bases()
        # (the controller's buttons and Options > Controller's diagram, 2026-11-16: drawn from numbers by padicons.py)
        own = own or rel.parent == Path("Media/Pad") and re.fullmatch(r"[A-Za-z0-9]+_\d+\.tga", p.name)
        # (the road and wall tools' legend icons, 1.3.10: the mouse's buttons, Shift and Ctrl, drawn from numbers by
        # toolicons.py; test_tool_legend.py checks they're what it makes)
        own = own or rel.parent == Path("Media/Tools") and re.fullmatch(r"[A-Za-z]+_\d+\.tga", p.name)
        # (the map's round buttons drawn at each size, 1.3.9: MapMenu.tga, our own, resized, and discs drawn from
        # numbers by coast.py; test_button_art.py checks they're what it makes)
        own = own or rel.parent == Path("Media/Buttons") and re.fullmatch(r"(Frame|Disc)\d+\.tga", p.name)
        if not own:
            stray.append(str(rel))
    assert not stray, stray
    assert not [p for p in REPO.rglob("*.blp") if ATLAS not in p.parents and "data" not in p.relative_to(REPO).parts
                and ".git" not in p.parts]


def test_the_data_and_engine_are_chunks_run_only_at_login():
    for f in lua_files()[:-1]:
        src = (ADDON / f.replace("\\", "/")).read_text(encoding="utf-8")
        # (each file only registers a function: run at login while it's on, else let go)
        assert "ns.AtlasChunks[#ns.AtlasChunks + 1] = { " in src, f
        assert src.rstrip().endswith("end }"), f
        assert "TRILINEAR" not in src, f  # (crashes this client: wowmock.lua)
        assert "LICENSE" not in src and "MIT" not in src, f  # (issue #61: nothing copied, no notice to keep)


# ---------------------------------------------------------------- in Lua 5.1, with the stand-in UI

def _start(on: bool):
    """Core.lua, the Atlas's files and the stand-in UI, started up as the game does (ADDON_LOADED, PLAYER_LOGIN)."""
    lua51 = pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import GLOBALS, MOCK

    lua = lua51.LuaRuntime()
    lua.execute(MOCK.read_text(encoding="utf-8"))
    lua.execute(GLOBALS)
    ns = lua.table()
    lua.globals().AGPS_NS = ns
    loader = lua.eval("function(src, name) return assert(loadstring(src, '@' .. name)) end")
    for name in ["Core.lua"] + [f.replace("\\", "/") for f in lua_files()]:
        loader((ADDON / name).read_text(encoding="utf-8"), name)("AzerothGPS", ns)
    lua.execute(f"AzerothGPSDB = {{ settings = {{ gps = {{ style = '{'seamless' if on else 'minimap'}' }} }}, "
                "seamlessDefault60 = true, mapStyles75 = true }")
    fire = lua.eval("AGPS_FIRE")
    fire("ADDON_LOADED", "AzerothGPS")
    fire("PLAYER_LOGIN")
    assert not list(ns.initErrors.values())
    return lua, ns


# The game's map API for the stitched map: Azeroth's art, two continents and a zone on it
WORLD_MAPS = """
local layer = { layerWidth = 1002, layerHeight = 668, tileWidth = 256, tileHeight = 256 }
C_Map.GetMapArtLayers = function() return { layer } end
C_Map.GetMapArtLayerTextures = function() local t = {} for i = 1, 12 do t[i] = 1000 + i end return t end
C_Map.GetMapRectOnMap = function(id)
  if id == 1414 then return 0.05, 0.45, 0.1, 0.9 end
  if id == 1415 then return 0.55, 0.95, 0.1, 0.9 end
  if id == 2521 then return nil end -- (Zephras Isle: on a map of its own, not on Azeroth's)
  return 0.6, 0.7, 0.2, 0.3
end
C_Map.GetMapChildrenInfo = function(_, kind)
  if kind == 2 then return { { mapID = 1414 }, { mapID = 1415 } } end
  return { { mapID = 1420 } }
end
Enum.UIMapType = { Continent = 2, Zone = 3, Dungeon = 4, Micro = 5 }
GetPhysicalScreenSize = function() return 1920, 1080 end
GetPlayerFacing = function() return 1 end
C_Map.GetAreaInfo = function() return "The Great Sea" end
"""


def test_off_nothing_of_the_stitched_maps_code_is_kept():
    lua, ns = _start(False)
    A = ns.Atlas
    assert ns.AtlasChunks is None and A.loaded is None and A.E is None and A.core.Build is None
    assert A.Wanted() is False


def test_off_the_memory_left_is_none_of_the_stitched_maps():
    # The Atlas's files loaded and let go (as at login with the seamless map off) against Atlas.lua alone: the same memory
    lua51 = pytest.importorskip("lupa.lua51")
    files = [f.replace("\\", "/") for f in lua_files()]

    def kb(names, drop):
        lua = lua51.LuaRuntime()
        run = lua.eval("""function(srcs, names, drop)
          collectgarbage("collect"); collectgarbage("collect")
          local ns = {}
          for i = 1, #srcs do
            assert(loadstring(srcs[i], '@' .. names[i]))("AzerothGPS", ns)
            srcs[i] = false -- (the file's text let go, as the game does once it's run)
          end
          if drop then ns.AtlasChunks = nil end
          collectgarbage("collect"); collectgarbage("collect")
          return collectgarbage("count"), ns
        end""")
        srcs = [(ADDON / n).read_text(encoding="utf-8") for n in names]
        return run(lua.table_from(srcs), lua.table_from(names), drop)[0]

    alone = kb(files[-1:], False)
    loaded = kb(files, False)
    dropped = kb(files, True)
    assert loaded - alone > 200  # (the stitched map's code and data held while waiting to run: hundreds of KB)
    # (its file names, interned, and Lua 5.1's string table: a power of two that shrinks only below a quarter
    # full, so left up to twice Atlas.lua's own strings' size; the stitched map's code kept would be hundreds of KB)
    assert abs(dropped - alone) < 16, (alone, loaded, dropped)


def test_on_the_art_builds_on_a_frame_of_its_own_and_shows_only_the_explored_areas_on_request():
    lua, ns = _start(True)
    lua.execute(WORLD_MAPS)
    A = ns.Atlas
    assert A.loaded is True and ns.AtlasChunks is None and A.E is not None
    lua.execute("AGPS_GRADES = {} local E = AGPS_NS.Atlas.E local g = E.Grade "
                "E.Grade = function(...) AGPS_GRADES[#AGPS_GRADES + 1] = select(3, ...) return g(...) end")
    box = lua.eval("CreateFrame('Frame', nil, UIParent)")
    box.SetSize(box, 450, 450)
    assert A.AttachArt(box, box, 5)
    assert A.E.IsBuilt() and not dict(A.E.broken)  # (the per-view parts run each in a pcall: none failed)
    assert list(lua.eval("AGPS_GRADES").values()) == ["show"]  # (every area shown, as before)
    # Show Only Explored Areas (issue #60): the stitched map's own "hide", piece by piece; off again: every area
    A.SetExploredOnly(True)
    assert ns.settings.gps.seamExploredOnly is True and list(lua.eval("AGPS_GRADES").values())[-1] == "hide"
    A.SetExploredOnly(False)
    assert list(lua.eval("AGPS_GRADES").values())[-1] == "show"
    # the player exploring somewhere: the art's pieces read again
    assert A.exploreEvents._events["MAP_EXPLORATION_UPDATED"]
    # Blizzard's world map: never touched
    for name in [f.replace("\\", "/") for f in lua_files()]:
        assert "WorldMapFrame" not in re.sub(r"--[^\n]*", "", (ADDON / name).read_text(encoding="utf-8")), name


def test_the_views_maths():
    lupa = pytest.importorskip("lupa")
    lua = lupa.LuaRuntime()
    ns = lua.table()
    lua.execute("issecretvalue = nil")
    src = (ATLAS / "Atlas.lua").read_text(encoding="utf-8")
    lua.eval("function(src, ns) return assert(load(src, '@Atlas.lua'))('AzerothGPS', ns) end")(src, ns)
    A = ns.Atlas
    W, H = 1002, 668
    # the whole world fits a 1002 x 668 view at zoom 1 (a px a unit), its middle in the view's
    s, ox, oy = A.Place(0.5, 0.5, 1, W, H, W, H)
    assert (s, ox, oy) == pytest.approx((1, 0, 0))
    # zoomed 4x on a point: that point at the view's middle
    s, ox, oy = A.Place(0.25, 0.75, 4, W, H, W, H)
    assert (ox + 0.25 * W) * s == pytest.approx(W / 2) and (oy - 0.75 * H) * s == pytest.approx(-H / 2)
    assert A.DetailK(W, H, W, H) == pytest.approx(1)
    assert A.DetailK(400, 800, W, H) < 1  # (a tall view shows more of the world than its fit says)


# ---------------------------------------------------------------- the whole addon

# The stitched map's projection as the game gives it: each continent's map corners in world yards and its rectangle on
# Azeroth's map, laid out as Data/Maps.lua's worldFrames (the game's own assignment)
STITCH_PROJECTION = """
CreateVector2D = function(x, y) return { x = x, y = y, GetXY = function(self) return self.x, self.y end } end
local frames = AGPS_NS.Maps[947].worldFrames
local MAPS = { [1415] = frames[0], [1414] = frames[1] }
C_Map.GetWorldPosFromMapPos = function(id, p)
  local wf = MAPS[id]
  if not wf then return nil end
  return 0, CreateVector2D(wf[3] - p.y * (wf[3] - wf[1]), wf[4] - p.x * (wf[4] - wf[2]))
end
local rect = C_Map.GetMapRectOnMap
C_Map.GetMapRectOnMap = function(id, on)
  local wf = MAPS[id]
  if wf then return wf[5], wf[7], wf[6], wf[8] end
  return rect(id, on)
end
"""

# (Stormwind, Brill, Ironforge; Orgrimmar, Thunder Bluff, Darnassus)
SPOTS = [(0, -8840.6, 489.7), (0, 2254.0, 293.0), (0, -4981.0, -880.0), (1, 1676.0, -4315.0), (1, -1196.0, -40.0),
         (1, 9947.0, 2482.0)]


def _seamless(on=True, projection=True, saved_extra=""):
    """The whole addon (gameharness) with the seamless map on (the default) or off, the stitched map's art (and its
    projection)."""
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    gps = f"style = '{'seamless' if on else 'minimap'}'"
    lua, ns = start(saved=f"AzerothGPSDB = {{ settings = {{ gps = {{ {gps} }} }}, seamlessDefault60 = true, mapStyles75 = true "
                          f"{saved_extra} }}")
    lua.execute(WORLD_MAPS)
    if projection:
        lua.execute(STITCH_PROJECTION)
    ns.Nav.FUN = False
    return lua, ns


@pytest.mark.parametrize("projection", [True, False])
def test_world_yards_go_to_the_stitched_map_and_back(projection):
    lua, ns = _seamless(projection=projection)
    A = ns.Atlas
    assert A.Load()
    assert bool(A.Projection()) == projection  # (no CreateVector2D in the stand-in: the frames)
    frames = ns.Maps[947].worldFrames
    for cont, x, y in SPOTS:
        u, v = A.ToAtlas(cont, x, y)
        wf = frames[cont]
        assert wf[5] <= u <= wf[7] and wf[6] <= v <= wf[8], (cont, x, y)
        # the stitched map's own projection and the game's frames agree (the same assignment)
        assert (u, v) == pytest.approx(A.FromFrame(wf, x, y), abs=1e-9)
        c2, x2, y2 = A.FromAtlas(u, v)
        assert c2 == cont and (x2, y2) == pytest.approx((x, y), abs=1e-6)
    # Stormwind south of Ironforge and Ironforge of Brill (v down), on the east; Orgrimmar west of them
    sw, br, ifo = (A.ToAtlas(c, x, y) for c, x, y in SPOTS[:3])
    assert br[1] < ifo[1] < sw[1] and A.ToAtlas(1, 1676.0, -4315.0)[0] < sw[0]
    # an underground city in its continent's coordinates; a dungeon's level and the sea: not on it
    assert A.ToAtlas(10001, 1600.0, 240.0) == pytest.approx(A.ToAtlas(0, 1600.0, 240.0))
    assert A.ToAtlas(20036, 0.0, 0.0) is None
    assert A.FromAtlas(0.48, 0.5) is None
    # an isle on a map of its own (Zephras Isle, map 2991, issue #60): where AzerothGPS's map draws it on the world
    # map (its inset, as Geo.ToContinent), and back to its own yards
    u, v = A.ToAtlas(2991, 3000.0, 1500.0)
    it = ns.GPS.WORLD_INSETS[1]
    assert it.u0 <= u <= it.u1 and it.v0 <= v <= it.v1
    mx, my = ns.Geo.IntoAny(2991, 3000.0, 1500.0, 0)
    assert A.ToAtlas(0, mx, my) == pytest.approx((u, v), abs=1e-3)  # (the same place as the map's own projection)
    assert A.FromAtlas(u, v) == pytest.approx((2991, 3000.0, 1500.0), abs=1e-6)
    # /agps seamless spots: every spot, none off the frames, each back on its own continent
    lua.globals().DEFAULT_CHAT_FRAME = lua.eval("{ AddMessage = function() end }")
    out = list(A.CheckMapping().values())
    assert len(out) == len(list(A.CHECK_SPOTS.values())) and all(r[5] < 0.01 for r in out)
    assert all(r[8] < 0.01 for r in out)  # (the way back: yards off)
    assert ns.db.seamCheck and len(list(ns.db.seamCheck.spots.values())) == len(out)  # (QA reads the saved file)


def test_the_spot_check_names_the_zone_not_the_continent():
    """Issues #58, #205: /agps seamless spots names each spot's zone. Where the game's chain of maps stops at the
    continent (the map under the spot there a micro map, a dungeon's or an orphan's, which E.ChainAt stops at), that
    map's parents are walked up to its zone; only with no zone found at all is the continent named."""
    lua, ns = _seamless()
    A = ns.Atlas
    assert A.Load()
    lua.execute("""
      Enum = { UIMapType = { Cosmic = 0, World = 1, Continent = 2, Zone = 3, Dungeon = 4, Micro = 5, Orphan = 6 } }
      local maps = {
        [947] = { 'Azeroth', 1 }, [1415] = { 'Eastern Kingdoms', 2, 947 }, [1414] = { 'Kalimdor', 2, 947 },
        [1453] = { 'Stormwind City', 3, 1415 }, [1454] = { 'Orgrimmar', 3, 1414 }, [9001] = { 'Cleft of Shadow', 5, 1454 },
      }
      C_Map.GetMapInfo = function(id)
        local m = maps[id]
        return m and { mapID = id, name = m[1], mapType = m[2], parentMapID = m[3] } or nil
      end
      C_Map.GetMapRectOnMap = function() return 0.1, 0.5, 0.2, 0.6 end
      AGPS_UNDER = nil
      C_Map.GetMapInfoAtPosition = function(id, x, y)
        AGPS_AT = { id, x, y }
        return AGPS_UNDER and C_Map.GetMapInfo(AGPS_UNDER) or nil
      end
      local E = AGPS_NS.Atlas.E
      E.ChainAt = function() return AGPS_CHAIN end
    """)
    g = lua.globals()
    g.AGPS_CHAIN = lua.table(947, 1415, 1453)
    assert A.GameZoneAt(0.3, 0.4) == "Stormwind City"
    # the chain stops at Kalimdor: the micro map under the spot there, up to its zone
    g.AGPS_CHAIN = lua.table(947, 1414)
    g.AGPS_UNDER = 9001
    assert A.GameZoneAt(0.3, 0.4) == "Orgrimmar"
    at = g.AGPS_AT
    assert at[1] == 1414 and (at[2], at[3]) == pytest.approx((0.5, 0.5))  # (the spot on the continent's own map)
    # nothing under it: the continent, as before
    g.AGPS_UNDER = None
    assert A.GameZoneAt(0.3, 0.4) == "Kalimdor"
    lua.globals().DEFAULT_CHAT_FRAME = lua.eval("{ AddMessage = function() end }")
    g.AGPS_CHAIN = lua.table(947, 1415, 1453)
    assert all(r[4] == "Stormwind City" for r in A.CheckMapping().values())


# The game's maps under a spot as the client gives them, one level at a time: on Azeroth's map the continent (its
# direct child, never the zone), on a continent's the zone the ground there is in (Router.ZoneAt), on a zone's a micro
# map; each continent's map laid out as its world frame (STITCH_PROJECTION's), each zone's rectangle on it by its bounds
MAP_CHAIN = """
local Maps = AGPS_NS.Maps
local frames = Maps[947].worldFrames
local CONT = { [1415] = frames[0], [1414] = frames[1] }
local function Rect(id, on)
  local wf, b = CONT[on], Maps[id] and Maps[id].bounds
  if not (wf and b and Maps[id].type == 3 and Maps[id].parent == on) then return nil end
  -- (a map's x runs west to east: Y down from maxY; its y north to south: X down from maxX)
  return (wf[4] - b[4]) / (wf[4] - wf[2]), (wf[4] - b[2]) / (wf[4] - wf[2]),
         (wf[3] - b[3]) / (wf[3] - wf[1]), (wf[3] - b[1]) / (wf[3] - wf[1])
end
local rectOnMap = C_Map.GetMapRectOnMap
C_Map.GetMapRectOnMap = function(id, on)
  local l, r, t, b = Rect(id, on)
  if l then return l, r, t, b end
  return rectOnMap(id, on)
end
C_Map.GetMapInfoAtPosition = function(on, x, y)
  if on == 947 then
    for id, wf in pairs(CONT) do
      if x >= wf[5] and x <= wf[7] and y >= wf[6] and y <= wf[8] then return C_Map.GetMapInfo(id) end
    end
    return nil
  end
  local wf = CONT[on]
  if wf then -- (the zone the ground there is in: the addon's own zone data)
    local zone = AGPS_NS.Router.ZoneAt(Maps[on].continent, wf[3] - y * (wf[3] - wf[1]), wf[4] - x * (wf[4] - wf[2]))
    return zone and zone ~= 0 and C_Map.GetMapInfo(zone) or nil
  end
  return { mapID = 99999, name = "A cellar", mapType = 5 } -- (a micro map: not a zone, the chain stops)
end
"""


def test_the_seamless_maps_spot_check_names_each_spots_zone_not_its_continent():
    """Issue #58: /agps seamless spots (once /agps atlas check) named each spot's continent, from one look on
    Azeroth's map; the game's maps are asked down to the zone."""
    lua, ns = _seamless()
    lua.execute(MAP_CHAIN)
    A = ns.Atlas
    assert A.Load()
    lua.globals().DEFAULT_CHAT_FRAME = lua.eval("{ AddMessage = function() end }")
    zones = {r[0]: r[3] for r in (list(row.values()) for row in A.CheckMapping().values())}
    assert zones["Stormwind"] == "Stormwind City" and zones["Brill"] == "Tirisfal Glades"
    assert zones["Orgrimmar"] == "Orgrimmar" and zones["Thunder Bluff"] == "Thunder Bluff"
    assert not {"Eastern Kingdoms", "Kalimdor", "Azeroth", "?"} & set(zones.values()), zones


def test_the_atlas_window_and_its_view_switch_are_gone():
    """Issue #60: the seamless map is the one view. The Atlas window, its "Atlas View" button and its settings are
    gone; /agps atlas says where it went; nothing else of the player's settings is lost."""
    saved = ("AzerothGPSDB = { settings = { gps = { atlas = true, atlasView = { u = 0.5, v = 0.5, zoom = 3 }, "
             "seamlessZoom = false, zoom = 700, rotate = true, style = 'minimap' } }, "
             "chars = { ['Me-Realm'] = { mapWindow = 'atlas', faction = 'Horde' } } }")
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start(saved=saved)
    A, G, gps = ns.Atlas, ns.GPS, ns.settings.gps
    for gone in ("Frame", "Toggle", "SwitchView", "Sync", "SetEnabled", "Draw", "ViewChosen"):
        assert A[gone] is None, gone
    assert not any(t.id == "atlasView" for t in G.QuickSlots().values())
    # (an existing profile, saved with the old default off: the seamless map on, once; the rest kept)
    assert gps.seamlessZoom is None and gps.atlas is None and gps.atlasView is None and ns.db.seamlessDefault60
    assert gps.zoom == 700 and gps.rotate is True and gps.style == "seamless"  # (issue #75: the old default's terrain)
    assert ns.db.chars["Me-Realm"].mapWindow is None and ns.db.chars["Me-Realm"].faction == "Horde"
    assert A.loaded is True and G.Seamless()  # (loaded at login, the map made room for its art)
    lua.globals().DEFAULT_CHAT_FRAME = lua.eval("{ AddMessage = function(_, m) AGPS_PRINTED = m end }")
    lua.eval("SlashCmdList.AZEROTHGPS")("atlas")
    assert "zoom the map out" in str(lua.eval("AGPS_PRINTED"))
    G.ApplySettings()
    assert G.IsVisible()
    # turned off since (the switch kept): off it stays, the Terrain style (issue #75)
    lua2, ns2 = start(saved="AzerothGPSDB = { settings = { gps = { seamlessZoom = false } }, seamlessDefault60 = true }")
    assert ns2.settings.gps.style == "minimap" and ns2.Atlas.loaded is None and not ns2.GPS.Seamless()


def test_a_fresh_profile_opens_on_the_seamless_map():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    assert ns.settings.gps.style == "seamless" and ns.settings.gps.seamExploredOnly is False
    assert ns.Atlas.loaded is True and ns.GPS.ArtSpan() > 0 and ns.GPS.Seamless()


# ---------------------------------------------------------------- OpenMap's credit (issue #91)

OPENMAP_URL = "https://www.curseforge.com/wow/addons/openmap"
AUTHOR = re.compile(rb"jigrobbulus", re.IGNORECASE)
OPENMAP = re.compile(rb"openmap", re.IGNORECASE)
OLD_REPO = re.compile(b"jifo" + b"rever", re.IGNORECASE)  # (the old repo's owner: still nowhere)
# where the author's name may be (2026-10-17: the credit in Help improve, the README, the changelog, the docs)
AUTHOR_FILES = {"addon/AzerothGPS/Options.lua", "addon/AzerothGPS/README.txt", "CHANGELOG.md", "CLAUDE.md",
                "app/tests/test_atlas.py"}
# (and the same player-facing text in every language: the Options credit translated)
AUTHOR_FILES |= {f"addon/AzerothGPS/Locales/{c}.lua" for c in ("deDE", "esES", "esMX", "frFR", "itIT", "koKR", "ptBR",
                                                                  "ruRU", "zhCN", "zhTW")}
# where the style's name may be: those, and the player-facing text of the map menu, the commands and the reload prompt
OPENMAP_FILES = AUTHOR_FILES | {"addon/AzerothGPS/GPSFrame.lua", "addon/AzerothGPS/Config.lua",
                                "addon/AzerothGPS/Atlas/Atlas.lua"}


def _repo_files():
    files = [p for p in ADDON.rglob("*") if p.is_file()]
    files += [p for p in (REPO / "CHANGELOG.md", REPO / "CLAUDE.md") if p.is_file()]
    for d in ("app", "docs"):
        files += [p for p in (REPO / d).rglob("*") if p.is_file() and "__pycache__" not in p.parts
                  and not any(part.startswith(".") for part in p.relative_to(REPO).parts)]  # (.pytest_cache)
    return files


def test_openmap_is_credited_only_where_meant():
    # The style is OpenMap and its creator credited (2026-10-17, issue #91, reversing 2026-10-16's "no mention in
    # any way"), in the player-facing places only: never in the engine's or the data's code, a path, or a comment
    # elsewhere; the old repo's owner nowhere.
    found = []
    for p in _repo_files():
        rel = str(p.relative_to(REPO)).replace("\\", "/")
        if OPENMAP.search(rel.encode()) or OLD_REPO.search(rel.encode()):
            found.append(("path", rel))
            continue
        if p.suffix.lower() in IMAGES:
            continue
        data = p.read_bytes()
        docs = rel.startswith("docs/")
        if OLD_REPO.search(data) and rel != "app/tests/test_atlas.py":
            found.append(("old repo", rel))
        if AUTHOR.search(data) and not (docs or rel in AUTHOR_FILES):
            found.append(("author", rel))
        if OPENMAP.search(data) and not (docs or rel in OPENMAP_FILES):
            found.append(("OpenMap", rel))
    assert not found, found
    # the Lua files that name it do so in the player's text, not in comments outside an issue note
    for rel in OPENMAP_FILES:
        if rel.endswith(".lua"):
            for line in (REPO / rel).read_text(encoding="utf-8").splitlines():
                code, _, comment = line.partition("--")
                assert not AUTHOR.search(comment.encode()) or rel.endswith("Options.lua"), (rel, line)
    for f in ("addon/AzerothGPS/Options.lua", "addon/AzerothGPS/README.txt", "CHANGELOG.md",
              "docs/curseforge-description.md"):
        text = (REPO / f).read_text(encoding="utf-8")
        assert "jigrobbulus" in text and OPENMAP_URL in text, f


def test_help_improve_thanks_openmaps_creator_and_the_style_is_named_openmap():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    O = ns.Options
    assert O.OPENMAP_URL == OPENMAP_URL
    assert "jigrobbulus" in str(O.CREDIT_TEXT) and "OpenMap" in str(O.CREDIT_TEXT)
    O.Show()
    texts = [str(w._text) for w in lua.eval("AGPS_WIDGETS").values() if w._text]
    assert "Thanks" in texts and O.CREDIT_TEXT in texts
    # the link to copy (the game can't open one): a box with the address, put back if typed over
    box = O.creditBox
    assert box and str(box._text) == OPENMAP_URL
    # the style's label, in Options > Map and the map menu, its saved value still "seamless"
    assert "Seamless" not in texts and ns.settings.gps.style == "seamless"
    assert '{ value = "seamless", text = "OpenMap" }' in (ADDON / "Options.lua").read_text(encoding="utf-8")
    src = (ADDON / "GPSFrame.lua").read_text(encoding="utf-8")
    assert r'{ "seamless", "Interface\\Icons\\INV_Misc_Map_01", "OpenMap", ' in src
    # /agps style openmap picks it, /agps style seamless too
    lua.globals().DEFAULT_CHAT_FRAME = lua.eval("{ AddMessage = function() end }")
    for word in ("minimap", "openmap", "minimap", "seamless"):
        lua.eval("SlashCmdList.AZEROTHGPS")("style " + word)
        assert ns.settings.gps.style == ("minimap" if word == "minimap" else "seamless"), word


def test_turned_on_mid_session_a_prompt_offers_a_reload():
    lua, ns = _seamless(on=False)
    A, G = ns.Atlas, ns.GPS
    lua.execute("AGPS_RELOADED = 0 ReloadUI = function() AGPS_RELOADED = AGPS_RELOADED + 1 end")
    lua.globals().DEFAULT_CHAT_FRAME = lua.eval("{ AddMessage = function() end }")
    assert not A.NeedsReload()
    A.SetSeamless(True)  # (/agps seamless on, as the Seamless style picked: its files were let go at login)
    assert A.NeedsReload() and ns.settings.gps.style == "seamless" and not G.Seamless()
    f = lua.globals().AzerothGPSAtlasReload
    assert f and f._shown and f.yes._text == "Reload UI" and "reload" in str(f.text._text).lower()
    assert "openmap map style" in str(f.text._text).lower()
    # (its Reload UI: a secure "/reload" the player clicks, over the prompt's own: ReloadUI() from an addon's click
    # is blocked in this client, ADDON_ACTION_BLOCKED, seen in game)
    sb = A.reloadBtn
    assert sb and sb._shown and sb._attr["type"] == "macro" and sb._attr["macrotext"] == "/reload"
    assert sb._text == "Reload UI" and lua.eval("rawequal")(sb.GetParent(sb), lua.globals().UIParent)
    # Reload UI: a /reload (never in combat)
    ns.inCombat = True
    f.yes._scripts["OnClick"](f.yes)
    assert lua.eval("AGPS_RELOADED") == 0
    ns.inCombat = False
    A.AskReload()
    f.yes._scripts["OnClick"](f.yes)
    assert lua.eval("AGPS_RELOADED") == 1


# ---------------------------------------------------------------- the seamless zoom on AzerothGPS's map (#57, #60)

def notch(G, k):
    """The zoom (yards at the reference size) k wheel notches out from SEAM_TERRAIN_ZOOM."""
    return G.SEAM_TERRAIN_ZOOM * G.ZOOM_STEP ** k


def terrain_zoom(G, share=0.85):
    """A zoom (yards, this map's size) with the terrain alone, sharp: inside the art's coming in."""
    return G.SEAM_ART_IN[1] * share * G.ZoomScale()


def test_the_zoom_to_blend_function_by_the_wheels_notches():
    lua, ns = _seamless()
    G = ns.GPS
    # (shipped as tuned in testing, issue #90: a notch of 1.16, counted from 1,000 yd, 8 notches in from it)
    assert (G.ZOOM_STEP, G.SEAM_TERRAIN_ZOOM, G.SEAM_SHARP_NOTCHES, G.SEAM_ART_NOTCHES, G.SEAM_TILES_NOTCHES,
            G.SEAM_WORLD_NOTCHES, G.SEAM_WORLD_MARGIN, G.INTERIOR_FEATHER_YD) == (1.16, 1000, -8, 3, 3, 0, 1, 60)
    # the terrain alone, sharp and opaque, from the closest zoom out to SEAM_SHARP_NOTCHES from SEAM_TERRAIN_ZOOM (no
    # art at all: issue #60)
    sharp = notch(G, G.SEAM_SHARP_NOTCHES)
    assert sharp == pytest.approx(305.0, abs=0.1)
    for z in (20, 60, 146, 250, sharp):
        assert G.ArtBlend(z) == (0, 1), z
    # then the art in under the tiles over SEAM_ART_NOTCHES, the tiles out over SEAM_TILES_NOTCHES, each a stage of
    # its own, counted in notches
    a0, a1 = G.SEAM_ART_IN[1], G.SEAM_ART_IN[2]
    t0, t1 = G.SEAM_TILES_OUT[1], G.SEAM_TILES_OUT[2]
    assert a0 == pytest.approx(sharp) and a1 == pytest.approx(notch(G, G.SEAM_SHARP_NOTCHES + G.SEAM_ART_NOTCHES))
    assert t0 == pytest.approx(a1)
    assert t1 == pytest.approx(notch(G, G.SEAM_SHARP_NOTCHES + G.SEAM_ART_NOTCHES + G.SEAM_TILES_NOTCHES))
    art, tiles = G.ArtBlend((a0 + a1) / 2)
    assert 0 < art < 1 and tiles == 1
    art, tiles = G.ArtBlend((t0 + t1) / 2)
    assert art == 1 and 0 < tiles < 1
    assert G.ArtBlend(t1) == (1, 0) and G.ArtBlend(40000) == (1, 0)
    # the tiles gone by the art's own zone detail (about 4,000 yd: the engine's detail fade, E.Fades), so the zones' art shows
    # before the continents' and the world's: the world stage after it, SEAM_WORLD_NOTCHES on
    assert t1 <= 4100
    # (the stages read in testing, issue #90; the transition three times as long since 2026-11-14, "make what 300% is the
    # new 100%")
    assert (a0, a1, t1) == pytest.approx((305.0, 476.1, 743.2), abs=0.1)
    assert G.SEAM_ICONS_FEW == pytest.approx(t1 * G.ZOOM_STEP ** G.SEAM_WORLD_NOTCHES) == pytest.approx(t1)
    # the wheel's limits: the tiles laid out to their fade's end, Azeroth's whole map fitting the (square) map the
    # furthest (2026-11-18; before, 0.85 of the widest continent's yards across: its far edges off the map)
    assert G.TilesMaxZoom(True) == pytest.approx(t1 * G.ZoomScale())
    b = G.WorldBounds(0)
    assert G.WorldZoom(0) == pytest.approx((b[4] - b[2]) / 2) == pytest.approx(22344.3, abs=1)
    assert G.MaxZoom() == pytest.approx(G.WorldZoom())
    last = (0, 1)
    for z in range(100, 6000, 5):
        a, t = G.ArtBlend(z)
        assert a >= last[0] and t <= last[1] and a >= 1 - t  # (one way each; the art never under a gap in the tiles)
        last = (a, t)


def test_the_blend_per_notch_as_the_wheel_goes_and_as_qa_reads_it():
    """The blend at each notch of the wheel, from the map's default zoom out to the whole world (the readings
    /agps seamless check keeps for QA)."""
    lua, ns = _seamless()
    G = ns.GPS
    lua.globals().DEFAULT_CHAT_FRAME = lua.eval("{ AddMessage = function() end }")
    # (inland, 2,900 yd from the sea every way, in the Barrens: Brill is 730 yd from Tirisfal's coast, and the edge
    # blend brings the art in under the tiles along it, issue #73)
    lua.execute("AGPS_POS = { -4.0, -788.0, 1 }")
    ns.settings.gps.zoom = 60
    G.Update()
    readings = []
    for _ in range(60):
        ns.Atlas.CheckSeamless()
        r = G.SeamReading()
        readings.append((r.ref, r.art, r.tiles, r.artOnly))
        if ns.settings.gps.zoom >= G.MaxZoom():
            break
        G.WheelZoom(G.ZOOM_STEP)
        G.Update()
    first_art = next(ref for ref, a, t, alone in readings if a > 0)
    assert first_art > G.SEAM_ART_IN[1]  # (no art at all up to there)
    assert all(t == 1 and a == 0 for ref, a, t, alone in readings if ref <= G.SEAM_ART_IN[1])
    assert any(0 < t < 1 for ref, a, t, alone in readings)  # (the tiles' fade: a notch of its own)
    assert readings[-1][3] and readings[-1][1] == 1  # (the whole world: the art alone)
    kept = list(ns.db.seamCheck.blend.values())
    assert len(kept) == len(readings) and kept[0].tiles == 1 and kept[0].art == 0


def _art_pos(A, u, v):
    """Where (u, v) is on the map's canvas by the art's own placement: px right and down of its middle."""
    W, H = A.E.Size()
    host = A.artHost
    w, h = host.GetWidth(host), host.GetHeight(host)
    s, ox, oy = A.Place(A.onMap.u, A.onMap.v, A.onMap.zoom, w, h, W, H)
    c = A.canvas
    assert c._scale == pytest.approx(s)
    p = c._pts["TOPLEFT"]
    assert (p[4], p[5]) == pytest.approx((ox, oy))  # (the canvas placed as A.Place says)
    return (u * W + ox) * s - w / 2, -(oy - v * H) * s - h / 2


@pytest.mark.parametrize("zoom", [380, 3000, 8000, 18000])
def test_the_art_lies_under_the_maps_own_projection(zoom):
    lua, ns = _seamless()
    A, G, Geo = ns.Atlas, ns.GPS, ns.Geo
    assert G.Seamless() and G.ArtSpan() > 0 and A.loaded
    ns.settings.gps.zoom = zoom
    G.Update()
    assert G.MaxZoom() >= 18000
    view = G.shownView
    assert ns.settings.gps.zoom == zoom and A.onMap and A.artHost.IsShown(A.artHost)
    assert A.artBox is not None and view.rot == 0
    # the player (the view's middle), Stormwind, Orgrimmar (the other continent, in this one's yards), each where
    # the map puts it, within a px
    for cont, x, y in [(0, 2254.0, 293.0), SPOTS[0], SPOTS[3], SPOTS[5]]:
        mx, my = Geo.ToContinent(cont, x, y, view.cont)
        dx, dy = Geo.ScreenOffset(view.x, view.y, mx, my)
        want = (dx * view.s, -dy * view.s)  # (Geo's offsets: y up)
        got = _art_pos(A, *A.ToAtlas(cont, x, y))
        assert got == pytest.approx(want, abs=1.0), (cont, x, y, got, want)
    # /agps seamless check: the same offsets, in game
    lua.globals().DEFAULT_CHAT_FRAME = lua.eval("{ AddMessage = function() end }")
    out = list(A.CheckSeamless().values())
    assert len(out) == 1 + len(list(A.CHECK_SPOTS.values())) and all(r[2] < 1.0 for r in out)
    # the art's alpha: as the blend says
    lua.execute("local h = AGPS_NS.Atlas.artHost h.SetAlpha = function(self, a) self._alpha = a end")
    G.Update()
    # (Brill is 730 yd from the coast: the edge blend's art, whole under the tiles, issue #73)
    want = 1 if G.shownView.edge else G.ArtBlend(zoom / G.ZoomScale())[0]
    assert A.artHost._alpha == pytest.approx(want)


def test_the_wheel_goes_out_to_the_world_and_back_to_the_roads():
    lua, ns = _seamless()
    A, G = ns.Atlas, ns.GPS
    ns.settings.gps.zoom = terrain_zoom(G)
    G.Update()
    assert not (A.artHost and A.artHost.IsShown(A.artHost))  # (close in: the map as it was, no art)
    n = 0
    while ns.settings.gps.zoom < G.MaxZoom() and n < 60:
        G.WheelZoom(G.ZOOM_STEP)
        G.Update()
        n += 1
    assert ns.settings.gps.zoom == pytest.approx(G.MaxZoom()) and n < 40
    assert G.MaxZoom() == pytest.approx(G.WorldZoom())
    view = G.shownView
    assert view.artOnly and view.seamFar and A.onMap
    assert A.onMap.zoom < 1.2  # (the whole world in view: zoom 1 on the art is the world fitting the view)
    lua.execute("AGPS_Q = AGPS_NS.GPS.laidTiles.quads == AGPS_NS.GPS.NO_QUADS")
    assert lua.eval("AGPS_Q")  # (no tiles laid under the art alone)
    while ns.settings.gps.zoom > terrain_zoom(G):
        G.WheelZoom(1 / G.ZOOM_STEP)
        G.Update()
    assert not view.artOnly and not A.artHost.IsShown(A.artHost)
    lua.execute("AGPS_Q = #AGPS_NS.GPS.laidTiles.quads > 0")
    assert lua.eval("AGPS_Q")  # (the terrain's tiles again)


def test_the_tiles_show_out_to_the_end_of_their_fade_never_the_zones_map_art():
    # (past MINIMAP_MAX_ZOOM the terrain view turned into a zone's map art; with the seamless map the tiles go on
    # until they've faded out over the stitched art)
    lua, ns = _seamless()
    G = ns.GPS
    ns.settings.gps.zoom = (G.SEAM_TILES_OUT[1] + G.SEAM_TILES_OUT[2]) / 2 * G.ZoomScale()
    G.Update()
    assert G.laidTiles.laidSig.startswith("tiles:") and G.quadAlpha < 1
    lua2, ns2 = _seamless(on=False)
    ns2.settings.gps.zoom = 2400
    G2 = ns2.GPS
    G2.Update()
    assert G2.laidTiles.laidSig.startswith("tiles:")  # (off: as it always was)


def test_right_click_zooms_out_a_few_notches_in_place_up_to_the_world():
    # (issue #74: it jumped to the whole world, and the next right-click back to the player: three views for one
    # button. Now the wheel's shortcut: SEAM_RIGHTCLICK_NOTCHES notches out on the same spot, the world its end)
    lua, ns = _seamless()
    G, st = ns.GPS, ns.settings.gps
    assert G.SEAM_RIGHTCLICK_NOTCHES == 4
    step = G.ZOOM_STEP ** G.SEAM_RIGHTCLICK_NOTCHES
    assert G.SeamRightClickZoom(400) == pytest.approx(400 * step)
    assert G.SeamRightClickZoom(G.MaxZoom() / 1.1) == pytest.approx(G.MaxZoom())
    st.zoom = 400
    G.Update()
    G.TerrainZoomOut()  # (following the player: still following, 4 notches out)
    G.Update()
    assert st.zoom == pytest.approx(400 * step) and G.BrowseState()[1] is None
    x, y = ns.Geo.ToContinent(0, -9000.0, 400.0, 0)  # (looked at somewhere off the player: kept there)
    G.LookAt(0, x, y)
    G.Update()
    spot = (G.shownView.x, G.shownView.y)

    def zoom():
        return G.LookZoom() or st.zoom  # (a view looked at zooms by its own)

    zooms, n = [zoom()], 0
    while zoom() < G.MaxZoom() * 0.999 and n < 20:
        G.TerrainZoomOut()
        G.Update()
        zooms.append(zoom())
        # (no recenter: the same spot, only kept off the far side of Azeroth's map's edge, G.ClampToWorld; 2026-11-18)
        v = G.shownView
        want = G.ClampToWorld(spot[0], spot[1], 0, v.s, 400, 400)
        if v.world:  # (the world view at last: Azeroth's map's middle)
            wb = G.WorldBounds(0)
            want = ((wb[1] + wb[3]) / 2, (wb[2] + wb[4]) / 2)
        assert (v.x, v.y) == pytest.approx(want, abs=1)
        assert G.BrowseState()[0] is None  # (no world map browsed)
        n += 1
    for a, b in zip(zooms, zooms[1:-1]):
        assert b == pytest.approx(a * step)
    assert zooms[-1] == pytest.approx(G.MaxZoom()) and n < 20
    G.TerrainZoomOut()  # (at the world: it stays, never back to the player)
    G.Update()
    assert zoom() == pytest.approx(G.MaxZoom())
    b = G.WorldBounds(0)  # (the world view: Azeroth's map's middle)
    assert G.shownView.world and (G.shownView.x, G.shownView.y) == pytest.approx(((b[1] + b[3]) / 2, (b[2] + b[4]) / 2))


def test_right_click_while_a_game_holds_the_map_keeps_the_old_rule():
    # (issue #74: not while a game holds the map: right-click browses the continent's map, as it always did)
    lua, ns = _seamless()
    G, st = ns.GPS, ns.settings.gps
    st.zoom = 400
    lua.globals().AzerothGPS.HoldMap("StreetGuess", True, None, lua.eval("{ style = 'minimap' }"))
    try:
        G.Update()
        G.TerrainZoomOut()
        assert G.BrowseState()[0] is not None and st.zoom == pytest.approx(400)
    finally:
        G.Follow()
        lua.globals().AzerothGPS.HoldMap("StreetGuess", False)


def test_heading_up_turns_north_up_while_the_art_shows():
    lua, ns = _seamless()
    G = ns.GPS
    lua.execute("GetPlayerFacing = function() return 1 end")
    ns.settings.gps.rotate = True
    ns.settings.gps.zoom = terrain_zoom(G, 0.5)
    G.Update()
    assert G.shownView.rot != 0
    ns.settings.gps.zoom = terrain_zoom(G, 0.99)  # (the terrain alone: still heading-up)
    G.Update()
    assert G.shownView.rot != 0
    ns.settings.gps.zoom = 5000
    G.Update()
    assert G.shownView.rot == 0


def test_heading_up_turns_at_the_usual_zooms():
    """(asked 2026-11-07: "Turn the map with me" stopped working on OpenMap: at zoom 402 on a 508 map the art had come
    in, issue #90's stages, and the art can't turn) heading-up keeps the turning tiles out to G.SEAM_HEADING_UP_YD;
    north-up the art comes in where it was tuned."""
    lua, ns = _seamless()
    G, st = ns.GPS, ns.settings.gps
    lua.execute("GetPlayerFacing = function() return 1 end")
    zoom = G.SEAM_ART_IN[2] * 1.2 * G.ZoomScale()  # (past the art's coming in, north-up)
    st.rotate = True
    st.zoom = zoom
    G.Update()
    assert G.shownView.rot != 0 and not G.shownView.artOnly
    assert G.SeamBlend(zoom)[0] == 0 and G.SeamBlend(zoom)[1] == 1  # (the tiles alone, sharp)
    st.zoom = G.SEAM_HEADING_UP_YD * 0.9 * G.ZoomScale()
    G.Update()
    assert G.shownView.rot != 0
    st.zoom = G.SEAM_ICONS_FEW * G.SeamShare() * 1.5 * G.ZoomScale()  # (past the tiles: the art, north up)
    G.Update()
    assert G.shownView.rot == 0
    st.rotate = False
    st.zoom = zoom
    G.Update()
    assert G.shownView.rot == 0 and G.SeamBlend(zoom)[0] > 0


def test_a_view_dragged_over_the_other_continent_takes_its_yards():
    lua, ns = _seamless()
    G = ns.GPS
    ns.settings.gps.zoom = 20000
    G.Update()
    # Orgrimmar in the Eastern Kingdoms' yards (past its edge), as a drag there leaves the view
    x, y = ns.Geo.ToContinent(1, 1676.0, -4315.0, 0)
    G.LookAt(0, x, y)
    G.Update()
    view = G.shownView
    # (its spot in Kalimdor's yards; drawn kept on Azeroth's map, this far out: G.ClampToWorld, 2026-11-18)
    free = G.BrowseState()[1]
    assert view.cont == 1 and (free.x, free.y) == pytest.approx((1676.0, -4315.0), abs=1)
    assert (view.x, view.y) == pytest.approx(G.ClampToWorld(1676.0, -4315.0, 1, view.s, 400, 400), abs=1)


# Teldrassil (Dolanaar), Rut'theran Village, Zephras Isle (an isle on a map of its own, 2991): each looked at from the
# whole world in the Eastern Kingdoms' yards, as a drag over it leaves the view
ISLES = [(1, 9850.0, 960.0), (1, 8700.0, 970.0), (2991, 3000.0, 1500.0)]


@pytest.mark.parametrize("cont,x,y", ISLES)
@pytest.mark.parametrize("from_view", ["ek", "undercity", "opened_city"])
def test_zoomed_in_on_an_island_its_terrain_comes_back(cont, x, y, from_view):
    """Issue #60: Teldrassil never turned back into the terrain map. A view on Undercity's level (the player down
    there) or one still carrying a city's inside map opened before (Ironforge's, from its icon: kept through every
    drag) never went over to Kalimdor's yards, so its tiles never came back; an isle on a map of its own (Zephras
    Isle) had no place on the art's projection at all."""
    lua, ns = _seamless()
    G, A = ns.GPS, ns.Atlas
    ns.settings.gps.zoom = 20000
    G.Update()
    from_cont = 0
    if from_view == "undercity":
        from_cont = 10001
    x0, y0 = ns.Geo.IntoAny(cont, x, y, 0)
    G.LookAt(from_cont, x0, y0, 20000)
    if from_view == "opened_city":
        lua.execute("local f = select(2, AGPS_NS.GPS.BrowseState()) f.interior = { 'Ironforge' } f.city = 1455")
    G.Update()
    for _ in range(20):
        G.WheelZoom(0.8)
        G.Update()
    view = G.shownView
    assert view.cont == cont and (view.x, view.y) == pytest.approx((x, y), abs=2)
    # (the art under the tiles only by the edge blend, on its coast: issue #73)
    assert not view.artOnly and (view.edge or not A.artHost.IsShown(A.artHost))
    lua.execute("AGPS_Q = #AGPS_NS.GPS.laidTiles.quads")
    assert lua.eval("AGPS_Q") > 0  # (its terrain's tiles)


def test_the_zone_under_the_mouse_on_the_art_with_its_levels():
    """Issue #60: pointing at a zone on the seamless map's art (continent and world zoom) names it with its levels,
    in the map's own zone label (as the world map style's hover); nothing over the sea."""
    lua, ns = _seamless()
    G = ns.GPS
    ns.settings.gps.zoom = 16000
    G.Update()
    view = G.shownView
    assert view.artOnly
    lua.execute("UnitLevel = function() return 12 end")

    def offset(cont, x, y):
        mx, my = ns.Geo.ToContinent(cont, x, y, view.cont)
        dx, dy = ns.Geo.ScreenOffset(view.x, view.y, mx, my)
        return dx * view.s, dy * view.s

    assert G.SeamZoneAt(*offset(0, 2254.0, 293.0))[1] == "Tirisfal Glades"
    assert G.SeamZoneAt(*offset(1, -400.0, -2600.0))[1] == "The Barrens"  # (the other continent, on the art)
    assert G.SeamZoneAt(*offset(1, 0.0, -8600.0)) is None  # (the open sea east of Durotar)
    # the label beside the cursor, as the world map style's: the name and the levels in the level's color
    lua.execute("AzerothGPSFrame.IsMouseOver = function() return true end")
    dx, dy = offset(1, -400.0, -2600.0)
    lua.execute(f"local c = AGPS_NS.GPS.Canvas and AGPS_NS.GPS.Canvas() GetCursorPosition = function() "
                f"local x, y = 0, 0 if c and c.GetCenter then x, y = c:GetCenter() end "
                f"local s = c and c.GetEffectiveScale and c:GetEffectiveScale() or 1 "
                f"return ((x or 0) + {dx}) * s, ((y or 0) + {dy}) * s end")
    G.UpdateZoneHover()
    label = G.zoneLabel
    assert label._shown and "The Barrens" in str(label._text) and "Level 10-25" in str(label._text)
    # zoomed back in on the terrain: no such label
    ns.settings.gps.zoom = 400
    G.Update()
    lua.execute("AGPS_T = (AGPS_T or 0) + 1")
    G.UpdateZoneHover()
    assert not label._shown


def test_zephras_isle_has_its_own_art_on_the_stitched_map_and_its_zone_under_the_mouse():
    """Issue #72: Zephras Isle (map 2521 on continent 2991, an island in the sky) isn't on Azeroth's map, so the
    stitched map drew nothing there: open sea at its frame. Its own map's tiles are laid over that frame, at every zoom
    the art shows, and pointing at it names it."""
    lua, ns = _seamless()
    G, A = ns.GPS, ns.Atlas
    ns.settings.gps.zoom = 16000
    G.Update()
    assert G.shownView.artOnly and A.artHost.IsShown(A.artHost)
    isles = list(A.isles.values())
    assert len(isles) == 1 and isles[0].map == 2521
    m = ns.Maps[2521]
    tex = list(isles[0].textures.values())
    assert [t._tex for t in tex] == [m.tiles[i][1] for i in range(1, len(m.tiles) + 1)]
    # (cropped at the art's edge, 1002 x 668 of 4 x 3 tiles of 256: the last column 234 wide, the last row 156 high)
    assert tuple(tex[-1]._coords.values()) == pytest.approx((0, 234 / 256, 0, 156 / 256))
    assert all(t._masks for t in tex)  # (its edges feathered)
    # where it is on the art: its frame there, as A.ToAtlas puts its yards
    wf = A.Frames()[2991]
    u, v = A.ToAtlas(2991, 3100.0, 1450.0)
    assert wf[5] < u < wf[7] and wf[6] < v < wf[8]
    # its zone under the mouse, from a view in the Eastern Kingdoms' yards
    view = G.shownView
    mx, my = ns.Geo.ToContinent(2991, 3100.0, 1450.0, view.cont)
    dx, dy = ns.Geo.ScreenOffset(view.x, view.y, mx, my)
    assert G.SeamZoneAt(dx * view.s, dy * view.s)[1] == "Zephras Isle"


def test_zephras_isle_on_the_stitched_map_is_its_revealed_map():
    """Zephras Isle's own map tiles alone are its unrevealed parchment: its areas were never drawn, where every other
    zone on the stitched map shows them. Its map's overlays go over the tiles, through the same land mask; with "Show
    Only Explored Areas" only those this character explored, again when they explore more."""
    lua, ns = _seamless()
    G, A = ns.GPS, ns.Atlas
    ns.settings.gps.zoom = 16000
    G.Update()
    isle = list(A.isles.values())[0]
    m = ns.Maps[2521]
    over = list(isle.overlays.values())
    assert len(over) == len(m.overlays) > 0
    assert [t._tex for t in over] == [m.overlays[i][1] for i in range(1, len(m.overlays) + 1)]
    assert all(t._shown and t._masks for t in over)  # (cut by the island's mask too)
    # only the explored ones: none explored yet, then one area
    lua.execute("""
      GetTime = function() return 0 end
      AGPS_EXPLORED = {}
      C_MapExplorationInfo = { GetExploredMapTextures = function(id)
        return id == 2521 and AGPS_EXPLORED or {} end }
    """)
    A.SetExploredOnly(True)
    assert len(list(isle.overlays.values())) == 0
    assert not any(t._shown for t in over)
    lua.execute("""AGPS_EXPLORED = { { textureWidth = 209, textureHeight = 191, offsetX = 600, offsetY = 357,
      isShownByMouseOver = false, fileDataIDs = { 8124653 } } }""")
    A.exploreEvents._scripts.OnEvent(A.exploreEvents, "MAP_EXPLORATION_UPDATED")
    shown = list(isle.overlays.values())
    assert [t._tex for t in shown] == [8124653] and shown[0]._shown and shown[0]._masks
    A.SetExploredOnly(False)
    assert len(list(isle.overlays.values())) == len(m.overlays)


def test_zephras_isle_is_the_island_alone_never_its_maps_page():
    """Issues #87, #90: the isle's own map is a whole parchment page (clouds, towers, the page's frame) round the
    island; drawn through a plain feather it was a light square with hard edges in the world's sea. Its tiles go
    through its land mask (Atlas/Media/Textures/MapIsle/2521.tga, `agps isle-mask`): white, the island opaque, the
    page clear, fading out between."""
    import numpy as np
    from PIL import Image
    lua, ns = _seamless()
    G, A = ns.GPS, ns.Atlas
    ns.settings.gps.zoom = 16000
    G.Update()
    isle = list(A.isles.values())[0]
    masks = [m._tex for t in isle.textures.values() for m in t._masks.values()]
    assert len(masks) == len(isle.textures) and set(masks) == {
        "Interface\\AddOns\\AzerothGPS\\Atlas\\Media\\Textures\\MapIsle\\2521"}  # (each tile through it)
    f = ADDON / "Atlas" / "Media" / "Textures" / "MapIsle" / "2521.tga"
    im = np.asarray(Image.open(f).convert("RGBA"))
    assert (im[..., :3] == 255).all()  # (white: only its alpha cuts)
    a = im[..., 3].astype(float) / 255
    n = a.shape[0]
    # the page round the island clear: its frame, corners, the clouds and towers at its sides
    assert a[0].max() == a[-1].max() == a[:, 0].max() == a[:, -1].max() == 0
    assert a[: n // 16].max() == 0 and a[:, : n // 5].max() == 0 and a[:, -n // 5:].max() == 0
    # the island opaque (its middle, Zephras Isle's lakes too), about a quarter of the page, a soft edge
    assert a[n // 2, n // 2] == 1 and 0.2 < (a > 0.5).mean() < 0.33
    assert 0 < ((a > 0) & (a < 1)).mean() < 0.05


def test_past_the_tiles_the_art_is_the_zones_map_never_its_close_up():
    """Issue #90: at the tuned stages the art showed alone from 410 yd, where the engine draws its close-up (the
    zones blurred and grained, the minimap mixed over them: E.Fades' softening from detail zoom 8). Zooming in went from
    the world's art through that blur to the terrain without the zones' (revealed) map, and the coasts faded into it.
    On the map the art is told no closer than the closeUpFrom knob (A.TellZoom): world, zones' map, terrain."""
    lua, ns = _seamless()
    G, A = ns.GPS, ns.Atlas
    E = A.E if A.E else None
    ns.settings.gps.zoom = G.MaxZoom()
    G.Update()
    E = A.E
    stages = []
    while ns.settings.gps.zoom > terrain_zoom(G, 0.5):
        r = G.SeamReading()
        if r.art > 0:
            zd, zp = E.view[5], E.view[6]
            f = E.Fades(zd, 0)
            assert zd <= 8 + 1e-9 and f.soft == 0 and zp < E.MINI["from"][1]  # (never the close-up)
            stages.append("world" if f.d < 0.5 else "zones" if r.artOnly else "blend")
        else:
            stages.append("terrain")
        G.WheelZoom(1 / G.ZOOM_STEP)
        G.Update()
    order = [s for i, s in enumerate(stages) if i == 0 or s != stages[i - 1]]
    assert order == ["world", "zones", "blend", "terrain"], stages
    assert stages.count("zones") >= 10  # (the zones' map over many notches: 410 yd to about 4,000)
    # the knob: the close-up again when it's let in (the dev tools)
    K = lua.globals().AzerothGPS.SeamKnobs()
    assert K.Get("closeUpFrom") == 8 and A.TellZoom(40, 50) == pytest.approx((8, 10)) and A.TellZoom(5, 6) == (5, 6)
    assert K.Set("closeUpFrom", 100)
    ns.settings.gps.zoom = 500
    G.Update()
    assert E.view[5] > 30 and E.Fades(E.view[5], 0).soft == 1
    K.Reset()
    assert K.Get("closeUpFrom") == 8


def test_the_seamless_knobs_turn_the_transition_live_and_reset():
    """Issue #72: the developer tools turn the transition levels live (AzerothGPS.SeamKnobs): the stages and the blend
    move at once, values kept in range, a report to send back, Reset to the shipped values; unturned, nothing changes."""
    lua, ns = _seamless()
    G, A = ns.GPS, ns.Atlas
    K = lua.globals().AzerothGPS.SeamKnobs()
    names = [k.name for k in K.List().values()]
    assert names == ["SEAM_TERRAIN_ZOOM", "SEAM_SHARP_NOTCHES", "SEAM_ART_NOTCHES", "SEAM_TILES_NOTCHES",
                     "SEAM_WORLD_NOTCHES", "ZOOM_STEP", "SEAM_WORLD_MARGIN", "INTERIOR_FEATHER_YD", "INTERIOR_TERRAIN_FEATHER_YD",
                     "minimapFrom", "minimapDeep", "soften",
                     "closeUpFrom"]
    assert all(k.value == k.default for k in K.List().values())
    # shipped as tuned in testing (issue #90): the report's values and stages
    assert {k.name: k.default for k in K.List().values()} == {
        "SEAM_TERRAIN_ZOOM": 1000, "SEAM_SHARP_NOTCHES": -8, "SEAM_ART_NOTCHES": 3, "SEAM_TILES_NOTCHES": 3,
        "SEAM_WORLD_NOTCHES": 0, "ZOOM_STEP": 1.16, "SEAM_WORLD_MARGIN": 1, "INTERIOR_FEATHER_YD": 60, "INTERIOR_TERRAIN_FEATHER_YD": 6,
        "minimapFrom": 40, "minimapDeep": 1, "soften": True, "closeUpFrom": 8}
    shipped = K.Stages()
    assert tuple(shipped.artIn.values()) == pytest.approx((305.0, 476.1), abs=0.1)
    assert tuple(shipped.tilesOut.values()) == pytest.approx((476.1, 743.2), abs=0.1)
    assert shipped.iconsFew == pytest.approx(743.2, abs=0.1) and shipped.worldZoom == pytest.approx(22344.3, abs=1)
    assert G.ArtBlend(300) == (0, 1) and G.ArtBlend(800) == (1, 0)
    # the transition pushed out four notches: the art in from 552 yd
    assert K.Set("SEAM_SHARP_NOTCHES", -4)
    assert K.Stages().artIn[1] == pytest.approx(1000 * 1.16 ** -4) and G.ArtBlend(500) == (0, 1)
    assert K.Set("SEAM_ART_NOTCHES", 0.25) and K.Get("SEAM_ART_NOTCHES") == 0.25
    assert K.Set("SEAM_TERRAIN_ZOOM", 1) and K.Get("SEAM_TERRAIN_ZOOM") == 100  # (kept in its range)
    assert not K.Set("NOT_A_KNOB", 1) and not K.Set("ZOOM_STEP", "fast") and K.Get("ZOOM_STEP") == 1.16
    world = K.Stages().worldZoom
    assert K.Set("SEAM_WORLD_MARGIN", 2.1) and K.Stages().worldZoom == pytest.approx(world * 2.1)
    # the close-up's knobs: the engine's own (E.KNOBS), read at its next view
    assert K.Set("minimapFrom", 99) and K.Get("minimapFrom") == 60
    assert K.Set("soften", False) and K.Get("soften") is False and not K.Set("soften", 1)
    assert A.applied is None  # (told to the art again)
    ns.settings.gps.zoom = 9000
    G.Update()
    text = K.Report()
    for part in ("SEAM_SHARP_NOTCHES = -4 (shipped -8)", "minimapFrom = 60 (shipped 40)", "stages", "map ", "notch",
                 "continent"):
        assert part in text, (part, text)
    K.Reset()
    assert all(k.value == k.default for k in K.List().values())
    assert tuple(K.Stages().artIn.values()) == pytest.approx((305.0, 476.1), abs=0.1)
    assert K.Stages().worldZoom == pytest.approx(world)


@pytest.mark.parametrize("style", ["minimap", "zone", "unrevealed"])
@pytest.mark.parametrize("zoom", [400, 2400, 9000])
def test_a_held_map_draws_its_style_as_before(style, zoom):
    """Issue #60: StreetView's game holds the map with a style (Normal "minimap", Heroic "zone", Mythic "unrevealed");
    while held, the map draws that style as it always did, with the seamless map on: the same tiles and art, the old
    zoom limits, no stitched art, and the player's own settings untouched."""
    def drawn(on):
        lua, ns = _seamless(on=on)
        G = ns.GPS
        ns.settings.gps.zoom = zoom
        lua.globals().AzerothGPS.HoldMap("StreetGuess", True, None, lua.eval(f"{{ style = '{style}' }}"))
        assert not G.Seamless()
        G.Update()
        quads = G.laidTiles.quads
        fids = sorted(int(quads[i][1]) for i in range(1, len(quads) + 1))
        art = ns.Atlas.artHost is not None and ns.Atlas.artHost.IsShown(ns.Atlas.artHost)
        out = (fids, round(G.shownView.s, 9), G.MaxZoom(), art, ns.settings.gps.style, ns.settings.gps.zoom)
        lua.globals().AzerothGPS.HoldMap("StreetGuess", False)
        return out, ns

    (on, ns_on), (off, _) = drawn(True), drawn(False)
    assert on[:4] + on[5:] == off[:4] + off[5:]
    assert (on[4], off[4]) == ("seamless", "minimap")  # (the player's own styles, untouched: issue #75)
    assert on[3] is False  # (no stitched art while held)
    assert ns_on.settings.gps.style == "seamless" and ns_on.GPS.Seamless()  # (let go: the seamless map again)


# ---------------------------------------------------------------- the four map styles (issue #75)

@pytest.mark.parametrize("saved, style", [
    ("", "seamless"),  # (a fresh profile)
    ("settings = { gps = { style = 'minimap' } }, seamlessDefault60 = true", "seamless"),  # (the old default's terrain)
    ("settings = { gps = { style = 'minimap', seamlessZoom = false } }", "seamless"),  # (off before #60: on since)
    ("settings = { gps = { style = 'minimap', seamlessZoom = false } }, seamlessDefault60 = true", "minimap"),
    ("settings = { gps = { seamlessZoom = false } }, seamlessDefault60 = true", "minimap"),  # (turned off: Terrain)
    ("settings = { gps = { style = 'zone' } }, seamlessDefault60 = true", "zone"),
    ("settings = { gps = { style = 'nospoiler', seamlessZoom = false } }, seamlessDefault60 = true", "nospoiler"),
    ("settings = { gps = { style = 'minimap' } }, seamlessDefault60 = true, mapStyles75 = true", "minimap"),  # (picked)
])
def test_saved_profiles_take_the_four_map_styles(saved, style):
    """Issue #75: the seamless map is a style of its own, the default. A saved Terrain style (the old default, can't be
    told from a choice) is Seamless now unless the seamless map was turned off; the world map styles stay; the old
    option is let go; a style picked since stays."""
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start(saved=f"AzerothGPSDB = {{ {saved} }}" if saved else None)
    gps = ns.settings.gps
    assert gps.style == style and gps.seamlessZoom is None and ns.db.mapStyles75
    assert (ns.Atlas.loaded is True) == (style == "seamless") and ns.GPS.Seamless() == (style == "seamless")
    if style != "seamless":
        assert ns.AtlasChunks is None  # (nothing of the stitched map kept)


def test_the_map_style_buttons_switch_between_the_four_live():
    """Issue #75: the Map Style buttons (and /agps style) switch between Seamless, Terrain, World Map and No Spoiler
    Map at once, no reload: the seamless zoom in Seamless only, the old limits in the others (zoomed out past them:
    back to their furthest), and Seamless again goes on out to the world with no prompt (loaded at login)."""
    lua, ns = _seamless(on=True)
    G, A, gps = ns.GPS, ns.Atlas, ns.settings.gps
    lua.globals().DEFAULT_CHAT_FRAME = lua.eval("{ AddMessage = function() end }")
    G.ApplySettings()
    buttons = {t.style: t for t in G.QUICK.values() if t.style}
    assert set(buttons) == {"seamless", "minimap", "zone", "nospoiler"}
    assert [buttons[k].label for k in ("seamless", "minimap", "zone", "nospoiler")] ==         ["OpenMap", "Terrain", "World Map", "No Spoiler Map"]
    group = next(g for g in G.QUICK_GROUPS.values() if g.id == "styles")
    assert list(group.members.values()) == ["style_seamless", "style_minimap", "style_zone", "style_nospoiler"]
    terrain_max = 2500 * G.ZoomScale()
    for i, style in enumerate(["seamless", "minimap", "zone", "nospoiler", "seamless", "minimap"]):
        if style == "minimap" and i == 1:
            G.SetZoom(G.WorldZoom())  # (out on the world, then Terrain: back to the land's furthest)
            G.Update()
        b = buttons[style]
        b.button._scripts.OnClick(b.button)
        assert gps.style == style and G.Style() == style and G.QuickOn(b)
        assert G.Seamless() == (style == "seamless")
        assert all(not G.QuickOn(t) for k, t in buttons.items() if k != style)
        if style == "seamless":
            assert G.MaxZoom() > terrain_max and not A.NeedsReload()
        else:
            assert gps.zoom <= G.MaxZoom() + 1e-6 and G.MaxZoom() <= terrain_max + 1e-6
        lua.execute(f"AGPS_T = {800 + i}")
        G.Update()
    assert lua.globals().AzerothGPSAtlasReload is None  # (never a reload prompt: loaded at login)
    slash = lua.globals().SlashCmdList.AZEROTHGPS
    for cmd, style in (("style nospoiler", "nospoiler"), ("style seamless", "seamless"), ("style zone", "zone"),
                       ("style terrain", "minimap"), ("style bogus", "minimap"), ("seamless on", "seamless"),
                       ("seamless off", "minimap"), ("style minimap", "minimap")):
        slash(cmd)
        assert gps.style == style, cmd


@pytest.mark.parametrize("held", ["minimap", "zone", "unrevealed"])
@pytest.mark.parametrize("mine", ["seamless", "minimap", "zone", "nospoiler"])
def test_a_held_style_over_each_of_the_four(mine, held):
    """Issue #75: StreetView's Normal (terrain), Heroic (world map) and Mythic (unrevealed) over each of the player's
    four styles: the held one draws, never the seamless zoom; the player's own is untouched and back on release."""
    lua, ns = _seamless(on=True)
    G, gps = ns.GPS, ns.settings.gps
    lua.globals().DEFAULT_CHAT_FRAME = lua.eval("{ AddMessage = function() end }")
    G.ApplySettings()
    assert G.SetStyle(mine)
    lua.globals().AzerothGPS.HoldMap("StreetGuess", True, None, lua.eval(f"{{ style = '{held}' }}"))
    assert G.Style() == held and not G.Seamless() and gps.style == mine
    assert G.SetStyle("zone") is False and gps.style == mine  # (the game on the map set it)
    G.Update()
    lua.globals().AzerothGPS.HoldMap("StreetGuess", False)
    assert G.Style() == mine and gps.style == mine and G.Seamless() == (mine == "seamless")
    G.Update()


def test_off_the_map_is_as_it_was():
    lua, ns = _seamless(on=False)
    A, G = ns.Atlas, ns.GPS
    assert not G.Seamless() and G.ArtSpan() == 0
    assert A.loaded is None and ns.AtlasChunks is None  # (nothing of the stitched map loaded or kept)
    assert G.MaxZoom() == pytest.approx(2500 * G.ZoomScale())
    ns.settings.gps.zoom = 99999
    G.SetZoom(99999)
    G.Update()
    assert ns.settings.gps.zoom == pytest.approx(G.MaxZoom()) and A.artHost is None
    # turned on mid-session: a reload first (the stitched map isn't loaded, the map made no room for it)
    lua.globals().DEFAULT_CHAT_FRAME = lua.eval("{ AddMessage = function(_, m) AGPS_PRINTED = m end }")
    A.SetSeamless(True)
    assert "reload" in str(lua.eval("AGPS_PRINTED")) and not G.Seamless()
    G.Update()
    assert A.artHost is None


def _engine():
    """The engine's maths alone: its Base and Engine chunks run in a plain Lua, no game calls."""
    lupa = pytest.importorskip("lupa")
    lua = lupa.LuaRuntime()
    ns = lua.table()
    for name in ("Base", "Engine"):
        src = (ATLAS / "Engine" / f"{name}.lua").read_text(encoding="utf-8")
        lua.eval("function(src, ns) return assert(load(src, '@x'))('AzerothGPS', ns) end")(src, ns)
    D, E = lua.table(), lua.table()
    for chunk in ns.AtlasChunks.values():
        chunk[2](D, E)
    _engine.lua = lua  # (its runtime: a test's Lua tables for it made there)
    return E


def test_the_engines_fades_by_zoom():
    # (docs/atlas-spec.md 7.2 to 7.5: the stages QA reads per notch depend on these)
    E = _engine()
    world = E.Fades(0.78)  # (the whole world: its art alone)
    assert world.cont == 0 and world.d == 0 and world.m == 0 and world.ws == 0
    stage = E.Fades(3.0)  # (the world stage: the zones' detail down to its hint)
    assert stage.d == pytest.approx(0.3) and stage.cont == 1 and stage.wo == 1 and stage.m == 0
    zones = E.Fades(4.7)  # (the tiles gone: the zones in full)
    assert zones.d == pytest.approx(1) and 0 < zones.m < 1 and zones.m == round(zones.m * 20) / 20  # (in steps)
    close = E.Fades(7.3)  # (the art's start on a square map: the backdrop muted, no blur yet)
    assert close.m == 1 and close.ws == 1 and close.soft == 0 and close.ms == 1
    assert E.Fades(13).soft == pytest.approx(0.5)
    assert E.Fades(4.7, 1).d == pytest.approx(0.25)  # (a cave surfaced: the zones dimmed)
    # the baked zones stand in for the live ones until a baked px is 1.2 screen px; the live ones load from 1.02
    share, warm, on, baked = E.Handover(True, 0.36, 1, False)
    assert (share, warm, on, baked) == (0, False, False, 1)
    share, warm, on, baked = E.Handover(True, 1.1, 0.5, False)
    assert share == 0 and warm and on and baked == pytest.approx(0.75)
    assert E.Handover(True, 1.1, 0.5, True)[3] == pytest.approx(0.75)
    assert E.Handover(True, 2, 1, False)[0] == 1 and E.Handover(True, 2, 1, False)[3] == 0
    share, warm, on, baked = E.Handover(False, 0.36, 0.5, False)  # (Show Only Explored Areas: the live zones only)
    assert share == 1 and on and baked == 0


def _old_fades(zd):
    """E.Fades as it was before the player's stages (2026-11-14): the numbers as written in docs/atlas-spec.md 7.2."""
    def smooth(a, b, x):
        if a == b:
            return 1 if x >= b else 0
        t = (x - a) / (b - a)
        if t <= 0:
            return 0
        if t >= 1:
            return 1
        return t * t * (3 - 2 * t)

    def floor20(x):
        return math.floor(x * 20 + 1e-7) / 20
    f = {"cont": smooth(1.3, 1.7, zd), "sm": floor20(smooth(1.2, 1.9, zd)), "wo": floor20(smooth(1.7, 2.2, zd)),
         "wc": floor20(smooth(3, 5, zd)), "m": floor20(smooth(4, 7, zd)), "ws": floor20(smooth(4, 7, zd)),
         "soft": smooth(8, 18, zd)}
    f["d"] = 0.3 * smooth(1.8, 3, zd) + 0.7 * smooth(3, 4.5, zd)
    return f


def test_the_engines_fades_are_as_shipped_at_the_default_stages():
    """The player's stages (Options > Map, 2026-11-14) at their defaults: every fade the very number it was."""
    E = _engine()
    zds = [0.5 + i * 0.0137 for i in range(1100)]
    for stages in (None, "{ zone = { 1, 1 }, world = { 1, 1 } }"):
        if stages:
            E.STAGES = _engine.lua.eval(stages)
        for zd in zds:
            f, old = E.Fades(zd), _old_fades(zd)
            for k, v in old.items():
                assert f[k] == v, (stages, zd, k)  # (exactly: not approx)
    assert tuple(E.StageRange("zone", 3, 4)) == (3, 4) and tuple(E.StageRange("zone", 3.5, 5)) == (3.5, 5)
    # moved, they do move (so the check above means something)
    E.STAGES = _engine.lua.eval("{ zone = { 2, 1 } }")
    assert E.Fades(3.0).d != _old_fades(3.0)["d"] and E.Fades(1.5).cont == _old_fades(1.5)["cont"]


def _seam_at(ns, zr):
    """The art engine's fades with the map at zr yards (at the reference size): its detail zoom, d, the continents'."""
    G, A = ns.GPS, ns.Atlas
    ns.settings.gps.zoom = zr * G.ZoomScale()
    G.Update()
    E = A.E
    return E.st.zd, E.st.d, E.Fades(E.st.zd).cont


def _set_stages(ns, **kw):
    st = ns.settings.gps
    for k, v in kw.items():
        st[k] = v
    ns.GPS.ApplySettings()


def _partial_notches(ns, zr0, zr1, read):
    """How many of the wheel's notches from zr0 out to zr1 show a fade part way (between 2% and 98%)."""
    G, n, zr = ns.GPS, 0, zr0
    while zr <= zr1:
        if 0.02 < read(_seam_at(ns, zr)) < 0.98:
            n += 1
        zr *= G.ZOOM_STEP
    return n


def test_the_zone_map_to_continent_map_slider_moves_the_engines_zone_fade():
    """Asked 2026-11-14: "zone map to world map doesn't change the distance the map fades between these 2": the first
    slider moved SEAM_WORLD_NOTCHES, the icons' world stage at 410 yd, while the zones' map gives way to the continents'
    by the art engine's own fade (E.Fades' d, about 6,000 yd out). seamContinentAt moves that fade."""
    lua, ns = _seamless()
    G, A = ns.GPS, ns.Atlas
    mid = G.SeamFadeYards("zone")
    # the reference size's yards to the engine's detail zoom, as G.SEAM_DETAIL_YD has it; and the middles alike
    for zr in (3000, 6000, 15000):
        assert _seam_at(ns, zr)[0] * zr == pytest.approx(G.SEAM_DETAIL_YD, rel=0.002)
    assert dict(A.E.STAGE_MID) == dict(G.SEAM_STAGE_MID)
    # as shipped: the zones' detail down to its hint (0.3) at its middle, whole at 4,000 yd, gone by 11,000
    assert _seam_at(ns, mid)[1] == pytest.approx(0.3, abs=0.01)
    assert _seam_at(ns, 4000)[1] == 1 and _seam_at(ns, 11000)[1] == 0
    try:
        # 4 notches further out: the zones' map whole where it was at its middle, its middle 4 notches out
        _set_stages(ns, seamContinentAt=4)
        assert _seam_at(ns, mid)[1] == 1
        assert _seam_at(ns, mid * 1.16 ** 4)[1] == pytest.approx(0.3, abs=0.01)
        # 4 notches in: gone at its old middle, at its hint 4 notches in
        _set_stages(ns, seamContinentAt=-4)
        assert _seam_at(ns, mid)[1] == 0
        assert _seam_at(ns, mid * 1.16 ** -4)[1] == pytest.approx(0.3, abs=0.01)
        # and still whole on the zones' stage closest in (the art's zoom told no closer than 8: A.TellZoom)
        assert _seam_at(ns, 600)[1] == 1
        # the continents' fade isn't the zones' slider's
        assert _seam_at(ns, G.SeamFadeYards("world"))[2] == pytest.approx(0.5, abs=0.02)
    finally:
        _set_stages(ns, seamContinentAt=0)
    assert _seam_at(ns, mid)[1] == pytest.approx(0.3, abs=0.01)


def test_the_continent_map_to_world_map_slider_moves_the_engines_world_fade():
    """Asked 2026-11-14: "a third one for the fade to world view": the continents' map giving way to the whole world's
    (E.Fades' continent layer, sea and world land: the engine's "world" fades), seamWorldAt."""
    lua, ns = _seamless()
    G = ns.GPS
    mid = G.SeamFadeYards("world")
    assert _seam_at(ns, mid)[2] == pytest.approx(0.5, abs=0.02)
    assert _seam_at(ns, 8000)[2] == 1 and _seam_at(ns, 19000)[2] == 0
    try:
        _set_stages(ns, seamWorldAt=3)
        assert _seam_at(ns, mid)[2] == 1
        assert _seam_at(ns, mid * 1.16 ** 3)[2] == pytest.approx(0.5, abs=0.02)
        _set_stages(ns, seamWorldAt=-3)
        assert _seam_at(ns, mid)[2] == 0
        assert _seam_at(ns, mid * 1.16 ** -3)[2] == pytest.approx(0.5, abs=0.02)
        # the zones' fade isn't the world slider's
        assert _seam_at(ns, G.SeamFadeYards("zone"))[1] == pytest.approx(0.3, abs=0.01)
    finally:
        _set_stages(ns, seamWorldAt=0)
    assert _seam_at(ns, mid)[2] == pytest.approx(0.5, abs=0.02)


def test_each_stages_transition_setting_widens_or_narrows_its_blend():
    """Asked 2026-11-14: "a transition setting for each level ... how much phasing or transitioning the map does fading
    from 1 to the next when zooming": none a sharp switch, more a longer blend, for each of the three."""
    lua, ns = _seamless()
    G = ns.GPS
    zone = lambda r: r[1]  # noqa: E731
    world = lambda r: r[2]  # noqa: E731
    widths = {}
    try:
        for blend in (0, 1, 2):
            _set_stages(ns, seamContinentBlend=blend, seamWorldBlend=blend, seamTerrainBlend=blend)
            terrain = 0
            zr = 150
            while zr < 3000:
                art, tiles = G.ArtBlend(zr)
                terrain += 1 if (0.02 < art < 0.98 or 0.02 < tiles < 0.98) else 0
                zr *= G.ZOOM_STEP
            widths[blend] = (terrain, _partial_notches(ns, 1500, 30000, zone), _partial_notches(ns, 4000, 40000, world))
    finally:
        _set_stages(ns, seamContinentBlend=1, seamWorldBlend=1, seamTerrainBlend=1)
    for i in range(3):
        assert widths[0][i] <= 1 < widths[1][i] < widths[2][i], widths
    # (as shipped: the terrain over 6 notches since 2026-11-14 (4 to 6 partly), the zones' map about 6, the continents'
    # about 3)
    assert 4 <= widths[1][0] <= 6 and 5 <= widths[1][1] <= 8 and 2 <= widths[1][2] <= 4, widths


def test_the_engine_draws_the_stages_as_the_wheel_goes_out():
    lua, ns = _seamless()
    A, G = ns.Atlas, ns.GPS
    ns.settings.gps.zoom = 3200  # (the art in full, the zones' baked tiles over Elwynn)
    G.Update()
    E = A.E
    assert E.IsBuilt() and not dict(E.broken)
    assert E.st.bakedA == 1 and not E.st.liveOn  # (every area shown: the baked zones, not the live ones)
    shown = [sp for sp in E.baked.values() if sp.on]
    assert shown and len(shown) < len(list(E.baked.values()))  # (only those near the view)
    assert E.bd.world.alpha < 0.1  # (the world art muted out)
    ns.settings.gps.zoom = 20000  # (the world stage: the world's art and the names, no zones)
    G.Update()
    assert E.st.bakedA < 1 and E.bd.world.alpha > 0.5 and not dict(E.broken)
    assert any(n.frame for n in E.names.values())  # (the continents' names lettered)
    # Show Only Explored Areas: the live zones instead of the baked ones
    ns.settings.gps.zoom = 3200
    A.SetExploredOnly(True)
    G.Update()
    assert E.st.bakedA == 0 and E.st.liveOn and not dict(E.broken)


# ---------------------------------------------------------------- the edge blend (issue #62)

# Off Westfall's coast and Durotar's shore: the last terrain tile's edge (no tile west of y 3725, east of y -6925),
# a spot with terrain and the empty sea in view with the terrain sharp (about 260 yd)
COASTS = [(0, -10400.0, 2000.0), (1, 388.0, -5012.0)]  # (the shore of Westfall, of Durotar: 100 yd inland)


def _laid(lua):
    """The quads laid last: (tiles, masks, feathers) as lists."""
    lua.execute("""AGPS_L = { t = {}, m = {}, f = {} }
      for _, q in ipairs(AGPS_NS.GPS.laidTiles.quads) do
        local k = q.color and 'm' or q.grad and 'f' or 't'
        AGPS_L[k][#AGPS_L[k] + 1] = q
      end""")
    got = lua.eval("AGPS_L")
    return [list(got[k].values()) for k in ("t", "m", "f")]


@pytest.mark.parametrize("cont,x,y", COASTS)
def test_the_art_shows_where_the_terrain_has_no_tiles_and_nowhere_else(cont, x, y):
    lua, ns = _seamless()
    G, A = ns.GPS, ns.Atlas
    lua.execute(f"AGPS_POS = {{ {x}, {y}, {cont} }}")
    ns.settings.gps.zoom = terrain_zoom(G)
    G.Update()
    view = G.shownView
    assert view.edge and not view.artOnly and view.rot == 0
    assert A.artHost.IsShown(A.artHost) and G.seamArt == 1  # (the art whole, under the tiles)
    assert G.laidTiles.laidSig == f"tiles:{cont}:edge" and G.quadAlpha == 1  # (the terrain sharp, unfaded)
    tiles, masks, feathers = _laid(lua)
    # every tile laid has its mask under it (a tile still loading never shows the art), the same box
    assert len(masks) == len(tiles) > 0
    for t, m in zip(tiles, masks):
        assert [m[i] for i in (2, 3, 4, 5)] == [t[i] for i in (2, 3, 4, 5)] and m[11] < t[11]
    # the coastal tiles, and the masks under them, through their coastline mask over the whole tile (issue #73)
    coastal = [t for t in tiles if t.mask]
    assert coastal
    for t, m in zip(tiles, masks):
        assert (m.mask is not None) == (t.mask is not None)
        if t.mask:
            assert m.mask[1] == t.mask[1] and t.mask[1].startswith(G.COAST_MEDIA)
            assert G.COAST_MEDIA == "Interface\\AddOns\\AzerothGPS\\Media\\Coast\\"
            assert t.mask[4] == pytest.approx(ns.Geo.TILE * view.s + 1)
    # feathers into the empty cells (no tile, or a tile all sea) only, at most EDGE_FEATHER_YD wide, their alpha 1
    # at the tile and 0 inward
    for f in feathers:
        o, a0, a1 = f.grad[1], f.grad[2], f.grad[3]
        wide = (f[4] if o == "HORIZONTAL" else f[5]) - 1
        assert wide <= G.EDGE_FEATHER_YD * view.s + 1e-6
        assert {round(a0, 6), round(a1, 6)} == {1, 0} or wide < G.EDGE_FEATHER_YD * view.s  # (cropped: a part of it)
        wx, wy = view.x + f[3] / view.s, view.y - f[2] / view.s  # (its middle, world: y west, x north)
        tx, ty = ns.Geo.WorldToTile(wx, wy)
        assert not G.HasTerrain(cont, wx, wy) or G.CoastAt(cont, int(tx // 1), int(ty // 1)) == 0, (wx, wy)
    # drawn: the masks' dark ground, the feathers' gradients on their textures
    lua.execute("""AGPS_D = { m = 0, g = 0 }
      for _, w in ipairs(AGPS_WIDGETS) do
        if w._shown and w._parent == AGPS_NS.GPS.quadLayer then
          if tostring(w._tex):find('^color:0.05') then AGPS_D.m = AGPS_D.m + 1 end
          if w._grad then AGPS_D.g = AGPS_D.g + 1 end
        end
      end""")
    d = lua.eval("AGPS_D")
    assert d.m == len(masks) and d.g == len(feathers)
    # the coastline masks on the textures drawn: one each, its file, over its whole tile
    lua.execute("""AGPS_D = { n = 0, files = {} }
      for _, w in ipairs(AGPS_WIDGETS) do
        if w._shown and w._parent == AGPS_NS.GPS.quadLayer and w.agpsMaskOn then
          AGPS_D.n = AGPS_D.n + 1
          AGPS_D.files[w.agpsMask.file] = true
          assert(#w._masks == 1 and w._masks[1] == w.agpsMask)
        end
      end""")
    d = lua.eval("AGPS_D")
    assert d.n == 2 * len(coastal) and set(d.files.keys()) == {t.mask[1] for t in coastal}
    # /agps seamless check says so
    lua.globals().DEFAULT_CHAT_FRAME = lua.eval("{ AddMessage = function() end }")
    A.CheckSeamless()
    assert G.SeamReading().edge is True
    # inland (Brill): no empty cell in view, nothing more than before: no art, no masks, no feathers
    lua.execute("AGPS_POS = { 2254.0, 293.0, 0 }")
    G.Update()
    assert not view.edge and not A.artHost.IsShown(A.artHost) and G.laidTiles.laidSig == "tiles:0"
    tiles, masks, feathers = _laid(lua)
    assert tiles and not masks and not feathers
    # (a texture reused for a tile after a feather: its gradient gone)
    lua.execute("""AGPS_D = 0
      for _, w in ipairs(AGPS_WIDGETS) do
        if w._shown and w._parent == AGPS_NS.GPS.quadLayer and w._grad then AGPS_D = AGPS_D + 1 end
      end""")
    assert lua.eval("AGPS_D") == 0


def test_the_feathers_alpha_as_cropped():
    lua, ns = _seamless()
    G = ns.GPS
    F, TILE = G.EDGE_FEATHER_YD, ns.Geo.TILE
    tiles = lua.eval("{ [10 * 64 + 10] = 111 }")  # (one tile; the cell east of it empty)
    # the empty cell (11, 10): its west neighbor the tile; the view's middle far off, nothing cropped
    maxX, maxY = (32 - 10) * TILE, (32 - 11) * TILE
    out = lua.eval("{}")
    G.EdgeFeathers(out, tiles, 11, 10, maxX, maxY, maxX - TILE / 2, maxY, 10000, 1)
    q = out[1]
    assert len(out) == 1 and q[1] == 111 and q.grad[1] == "HORIZONTAL"
    assert (q.grad[2], q.grad[3]) == pytest.approx((1, 0))  # (opaque on the left: the tile's side, west)
    assert (q[7], q[8]) == pytest.approx((1 - G.EDGE_SMEAR, 1))  # (the tile's eastern band)
    assert q[4] == pytest.approx(F + 1)  # (EDGE_FEATHER_YD wide at 1 px a yard)
    # cropped by the view's reach halfway along it (its half by the tile off the view): its left end half faded
    out = lua.eval("{}")
    G.EdgeFeathers(out, tiles, 11, 10, maxX, maxY, maxX - TILE / 2, maxY - F / 2 - 100, 100, 1)
    q = out[1]
    assert (q.grad[2], q.grad[3]) == pytest.approx((0.5, 0)) and q[4] == pytest.approx(F / 2 + 1)
    # each side: the tile north, south, east of an empty cell, opaque at that side
    for tx, ty, side in [(10, 11, ("VERTICAL", 0, 1)), (10, 9, ("VERTICAL", 1, 0)), (9, 10, ("HORIZONTAL", 0, 1))]:
        out = lua.eval("{}")
        mx, my = (32 - ty) * TILE, (32 - tx) * TILE
        G.EdgeFeathers(out, tiles, tx, ty, mx, my, mx - TILE / 2, my - TILE / 2, 10000, 1)
        q = out[1]
        assert (q.grad[1], q.grad[2], q.grad[3]) == pytest.approx(side), (tx, ty)


def test_no_edge_blend_heading_up_off_or_held():
    """The art can't turn: heading-up keeps the black. Off (and while a game holds the map) the map is as before."""
    cont, x, y = COASTS[0]
    lua, ns = _seamless()
    G, A = ns.GPS, ns.Atlas
    lua.execute(f"AGPS_POS = {{ {x}, {y}, {cont} }} GetPlayerFacing = function() return 1 end")
    ns.settings.gps.zoom = terrain_zoom(G)
    ns.settings.gps.rotate = True
    G.Update()
    assert G.shownView.rot != 0 and not G.shownView.edge and A.artHost is None  # (never even built)
    assert not any(_laid(lua)[1:])
    ns.settings.gps.rotate = False
    lua.globals().AzerothGPS.HoldMap("StreetGuess", True, None, lua.eval("{ style = 'minimap' }"))
    G.Update()
    assert not G.shownView.edge and A.artHost is None and not any(_laid(lua)[1:])
    lua.globals().AzerothGPS.HoldMap("StreetGuess", False)  # (let go: the blend)
    G.Update()
    assert G.shownView.edge and A.artHost.IsShown(A.artHost)
    lua2, ns2 = _seamless(on=False)
    lua2.execute(f"AGPS_POS = {{ {x}, {y}, {cont} }}")
    ns2.settings.gps.zoom = 400
    ns2.GPS.Update()
    assert not ns2.GPS.shownView.edge and ns2.GPS.laidTiles.laidSig == f"tiles:{cont}"
    assert not any(_laid(lua2)[1:])


# ---------------------------------------------------------------- the interiors zoom out to the world (issue #62)

CITIES = [  # (Ironforge's Great Forge: a capital in a mountain; down in Undercity: its own level)
    ("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = -4840.0, -1100.0, 0, 501.7 "
     "GetMinimapZoneText = function() return 'The Great Forge' end", 0),
    ("AGPS_MAP = 1458 AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = 1593.5, 157.3, 0, nil", 0),
]


def _land(lua, G, cont):
    """Whether the land round an interior shows as the seamless zoom's stage there says: the continent's tiles while
    they still show (out to SEAM_TILES_OUT), past them the art alone (issue #90's stages: the tiles gone by 410 yd,
    nearer than a city's own map's 500)."""
    view = G.shownView
    if view.cont != cont:
        return False
    if G.ArtBlend(ns_zoom(lua) / G.ZoomScale())[1] > 0:
        lua.execute("AGPS_Q = #AGPS_NS.GPS.laidTiles.quads")
        return G.laidTiles.laidSig.startswith(f"tiles:{cont}") and lua.eval("AGPS_Q") > 0
    return bool(view.artOnly) and G.laidTiles.laidSig.startswith(f"art:{cont}")


def ns_zoom(lua):
    return lua.eval("AGPS_NS.settings.gps.zoom")


def _wheel(lua, G, f, times=1):
    for _ in range(times):
        G.WheelZoom(f)
        lua.execute("AGPS_T = (AGPS_T or 0) + 1")
        G.Update()


@pytest.mark.parametrize("setup,cont", CITIES)
def test_out_of_a_citys_map_to_the_world_and_back_in(setup, cont):
    lua, ns = _seamless()
    G, A, st = ns.GPS, ns.Atlas, ns.settings.gps
    lua.execute(setup + " AGPS_T = (AGPS_T or 0) + 1000")
    st.zoom = 2000.0  # (come into the city zoomed out: zoomed in to its map, as always)
    G.Follow()
    G.Update()
    assert G.inside is not None and G.cityMap and st.zoom == G.CITY_MAX_ZOOM
    # the wheel on out: the land round the city (following the player still), then the art's stages to the world
    _wheel(lua, G, 1.25)
    assert st.zoom > G.CITY_MAX_ZOOM and G.inside is None and not G.cityMap and not G.IsFree()
    assert _land(lua, G, cont)  # (the continent's land)
    n = 0
    while st.zoom < G.MaxZoom() and n < 40:
        _wheel(lua, G, 1.25)
        n += 1
    assert st.zoom == pytest.approx(G.MaxZoom()) and G.shownView.artOnly and A.artHost.IsShown(A.artHost)
    # and back in: the land, then the city's map again at its own zoom
    while st.zoom > G.CITY_MAX_ZOOM * 1.2:
        _wheel(lua, G, 0.8)
        assert G.inside is None
    _wheel(lua, G, 0.8)
    assert st.zoom <= G.CITY_MAX_ZOOM and G.inside is not None and G.cityMap
    # (the terrain round it, a little darker, 2026-11-14: a city in a mountain and, since the War Quarter screenshot
    # the same day, an underground city's level too; no art blend under it)
    assert G.shownView.interiorTerrain and _terrain(lua) and _ground(lua)[1] and not G.shownView.interiorEdge
    assert G.shownView.interiorSpot is None
    # a held game's style (StreetView): its map stops at the city's, as before
    lua.globals().AzerothGPS.HoldMap("StreetGuess", True, None, lua.eval("{ style = 'minimap' }"))
    G.Update()
    _wheel(lua, G, 1.25, 3)
    assert st.zoom == G.CITY_MAX_ZOOM and G.inside is not None


DM = 20036  # (the Deadmines: its way in at Moonbrook)


def _way_in(G):
    e = G.WingEntrance(DM, None)
    assert e[1] == 0 and abs(e[2] + 11208.7) < 1  # (Data/Instances.lua's, the server's exit)
    return e[2], e[3]


def test_out_of_a_dungeons_map_to_the_land_at_its_way_in_and_back():
    lua, ns = _seamless()
    G, A, st = ns.GPS, ns.Atlas, ns.settings.gps
    lua.globals().DEFAULT_CHAT_FRAME = lua.eval("{ AddMessage = function(_, m) AGPS_PRINTED = m end }")
    G.Update()
    assert not G.IsFree()  # (following the player, in Brill)
    G.ShowInstance(DM)  # (opened from its icon)
    G.Update()
    assert G.shownView.instance == DM
    opened = st.zoom
    limit = G.InstanceSeamZoom(DM)
    assert limit >= G.CITY_MAX_ZOOM and limit >= opened  # (its whole extent first)
    n = 0
    while G.shownView.instance and n < 20:
        _wheel(lua, G, 1.25)
        n += 1
    # past its extent: the land at its way in, at the zoom the wheel went on to, then on out to the world
    view = G.shownView
    assert view.cont == 0 and (view.x, view.y) == pytest.approx(_way_in(G), abs=1e-6)
    assert limit < st.zoom <= limit * 1.25 + 1e-6 and G.IsFree()
    assert "Deadmines" in str(lua.eval("AGPS_PRINTED")) and "way in" in str(lua.eval("AGPS_PRINTED"))
    assert _land(lua, G, 0)
    while st.zoom < G.MaxZoom() and n < 60:
        _wheel(lua, G, 1.25)
        n += 1
    assert G.shownView.artOnly and A.artHost.IsShown(A.artHost)
    # zoomed well out (LEAVE_INSIDE_ZOOM_TIMES its extent): left for good, as a cave's (asked 2026-11-15: "panning too
    # far or zooming out closes the view"); back in is the land
    while st.zoom > 100:
        _wheel(lua, G, 0.8)
    assert G.shownView.instance is None and G.shownView.cont == 0
    # just past its extent and back in: its map again, as it was opened (right-click: back to where it was opened)
    G.Follow()
    G.ShowInstance(DM)
    G.Update()
    while G.shownView.instance and n < 80:
        _wheel(lua, G, 1.25)
        n += 1
    _wheel(lua, G, 0.8)
    assert G.shownView.instance == DM and st.zoom <= limit
    G.TerrainZoomOut()  # (right-click: the view it was opened from)
    G.Update()
    assert G.shownView.instance is None and not G.IsFree()  # (following the player again, as before it was opened)
    # a drag lets it go: zoomed out to the land, then panned, back in is the land
    G.ShowInstance(DM)
    G.Update()
    while G.shownView.instance and n < 80:
        _wheel(lua, G, 1.25)
        n += 1
    x, y, _ = G.ViewState()[0:3]
    G.LookAt(0, x + 300, y)
    _wheel(lua, G, 0.8, 6)
    assert G.shownView.instance is None and G.shownView.cont == 0


def test_a_dungeon_the_game_hides_the_player_in_zooms_out_to_its_way_in():
    lua, ns = _seamless()
    G, st = ns.GPS, ns.settings.gps
    lua.globals().DEFAULT_CHAT_FRAME = lua.eval("{ AddMessage = function() end }")
    lua.execute('AGPS_POS_REAL = AGPS_POS AGPS_POS = {} '
                'GetInstanceInfo = function() return "Deadmines", "party", 1, "Normal", 5, 0, false, 36 end')
    G.Update()
    assert G.shownView.instance == DM  # (its map put up: the position is hidden)
    for _ in range(20):
        _wheel(lua, G, 1.25)
        if not G.shownView.instance:
            break
    view = G.shownView
    assert view.instance is None and view.cont == 0 and (view.x, view.y) == pytest.approx(_way_in(G), abs=1e-6)
    _wheel(lua, G, 1.25, 12)
    assert G.shownView.artOnly  # (the art: nothing of the hidden dungeon holding it back)
    while G.shownView.instance is None and st.zoom > 100:
        _wheel(lua, G, 0.8)
    assert G.shownView.instance == DM


def test_a_dungeon_with_no_known_way_in_stops_at_its_own_extent_and_says_so():
    lua, ns = _seamless()
    G, st = ns.GPS, ns.settings.gps
    lua.globals().DEFAULT_CHAT_FRAME = lua.eval("{ AddMessage = function(_, m) AGPS_PRINTED = m end }")
    lua.execute(f"local i = AGPS_NS.Instances[{DM}] i.entrances = {{}} i.ghost = nil")
    G.ShowInstance(DM)
    G.Update()
    _wheel(lua, G, 1.25, 10)
    assert G.shownView.instance == DM and st.zoom == pytest.approx(G.InstanceSeamZoom(DM))
    assert "no known way in" in str(lua.eval("AGPS_PRINTED"))


def test_out_of_a_caves_map_to_the_land_and_back():
    lua, ns = _seamless()
    G, st = ns.GPS, ns.settings.gps
    lua.execute("""AGPS_C = nil
      for _, c in ipairs(AGPS_NS.Caves[0]) do
        if AGPS_NS.GPS.CaveArt(0, c[2]) then AGPS_C = c[2] break end
      end""")
    key = lua.eval("AGPS_C")
    assert key and G.ShowCave(0, key)
    G.Update()
    art = G.shownView.cave
    assert art and st.zoom <= G.CaveSeamZoom(art)
    while G.shownView.cave and st.zoom < 5000:
        _wheel(lua, G, 1.25)
    assert G.shownView.cave is None and st.zoom > G.CaveSeamZoom(art) and G.IsFree()
    assert _land(lua, G, 0)  # (the land round it)
    # just past it, back in: its map again
    while G.shownView.cave is None and st.zoom > 100:
        _wheel(lua, G, 0.8)
    assert G.shownView.cave and st.zoom <= G.CaveSeamZoom(art)
    # on out to the world: left for good (2026-11-14, G.LEAVE_INSIDE_ZOOM_TIMES), back in is the land
    _wheel(lua, G, 1.25, 12)
    assert G.shownView.artOnly and not G.BrowseState()[1].cave
    while st.zoom > 100:
        _wheel(lua, G, 0.8)
    assert G.shownView.cave is None and G.IsFree()


# ---------------------------------------------------------------- an opened inside map left by itself (2026-11-14)
# (asked with a screen recording: the Shadowvale Tomb's map opened, panned to Aerie Peak and zoomed out to the
# continent, its name, floor bar and "floor 2 of 2" line still there, and the right-click to leave jumped back to the
# tomb: "if the user pans far enough away OR zooms out enough the cave/city/building view should be exited
# automatically") G.LeaveInsideIfAway: in place, its name, floor bar and floor line gone, back over it the land

TOMB = "cave68463626"  # (the Shadowvale Tomb, Tirisfal: two floors)
TOMB_WAY = (1857.4, 2453.9)
AERIE_PEAK = (300.0, -2080.0)  # (the Hinterlands)


def _drag(lua, by):
    """A left-button drag on the map by `by` (x, y) pixels."""
    frame = lua.globals().AzerothGPSFrame
    lua.execute("AGPS_CUR_REAL = GetCursorPosition GetCursorPosition = function() return 300, 300 end")
    try:
        frame._scripts.OnMouseDown(frame, "LeftButton")
        lua.execute(f"GetCursorPosition = function() return {300 + by[0]}, {300 + by[1]} end")
        frame._scripts.OnUpdate(frame, 0.05)
        frame._scripts.OnMouseUp(frame, "LeftButton")
    finally:
        lua.execute("GetCursorPosition = AGPS_CUR_REAL")
    lua.execute("AGPS_T = (AGPS_T or 0) + 1")
    lua.globals().AGPS_NS.GPS.Update()


def _right_click(lua):
    frame = lua.globals().AzerothGPSFrame
    frame._scripts.OnMouseDown(frame, "RightButton")
    frame._scripts.OnMouseUp(frame, "RightButton")
    lua.execute("AGPS_T = (AGPS_T or 0) + 1")
    lua.globals().AGPS_NS.GPS.Update()


def _pan_to(lua, ns, spot, steps=40):
    """Dragged over to world `spot` (continent 0), a drag at a time."""
    G = ns.GPS
    for _ in range(steps):
        x, y, _c, rot, s = G.ViewState()[0:5]
        dx, dy = spot[0] - x, spot[1] - y
        if math.hypot(dx, dy) < 30:
            return
        k = min(1.0, 250 / (math.hypot(dx, dy) * s))  # (at most 250 px a drag)
        # (north up: world x is the screen's up, world y its left; the map follows the pointer)
        _drag(lua, (dy * s * k, -dx * s * k))
    raise AssertionError(G.ViewState()[0:2])


def _cave_shown(lua, ns):
    G = ns.GPS
    G.UpdateInfo()
    fl = G.FloorBar()
    return {"cave": G.shownView.cave is not None, "name": str(G.infoName), "bar": bool(fl.bar.IsShown(fl.bar)),
            "line": bool(fl.text.IsShown(fl.text)), "kept": G.BrowseState()[1] is not None and
            G.BrowseState()[1].cave is not None}


def _open_tomb(lua, ns):
    """The Shadowvale Tomb's map opened from its icon, as in the recording."""
    G = ns.GPS
    G.ApplyView(lua.eval(f"{{ x = {TOMB_WAY[0]}, y = {TOMB_WAY[1]}, cont = 0, rot = 0, cross = true, zoom = 250 }}"))
    lua.execute("AGPS_T = (AGPS_T or 0) + 1")
    G.Update()
    icons = [w for w in lua.eval("AGPS_WIDGETS").values() if w._shown and w.cave == TOMB]
    assert icons
    icons[0]._scripts.OnClick(icons[0], "LeftButton")
    lua.execute("AGPS_T = (AGPS_T or 0) + 1")
    G.Update()
    assert _cave_shown(lua, ns) == {"cave": True, "name": "Shadowvale Tomb", "bar": True, "line": True, "kept": True}


@pytest.mark.parametrize("on", [True, False])
def test_a_caves_map_panned_far_away_is_left_where_the_view_is(on):
    lua, ns = _seamless(on=on)
    G = ns.GPS
    _open_tomb(lua, ns)
    # a little way off it: still its map
    _drag(lua, (0, 120))
    assert _cave_shown(lua, ns)["kept"]
    # on to Aerie Peak: left, in place
    _pan_to(lua, ns, AERIE_PEAK)
    free = G.BrowseState()[1]
    shown = _cave_shown(lua, ns)
    assert shown == {"cave": False, "name": shown["name"], "bar": False, "line": False, "kept": False}
    assert shown["name"] != "Shadowvale Tomb"
    assert G.ViewState()[0:2] == pytest.approx((free.x, free.y)) and G.IsFree()
    assert math.hypot(free.x - AERIE_PEAK[0], free.y - AERIE_PEAK[1]) < 30  # (where it was panned to)
    # right-click: nothing to go back to (the seamless map: out in place; the Terrain style: the continent's map)
    _right_click(lua)
    browse, free2 = G.BrowseState()
    if on:
        assert G.ViewState()[0:2] == pytest.approx((free.x, free.y))
    assert not (free2 and math.hypot(free2.x - TOMB_WAY[0], free2.y - TOMB_WAY[1]) < 600)
    # back over the tomb, zoomed in: the land, its map left
    G.Follow()
    G.ApplyView(lua.eval(f"{{ x = {TOMB_WAY[0]}, y = {TOMB_WAY[1]}, cont = 0, rot = 0, cross = true, zoom = 250 }}"))
    _pan_to(lua, ns, AERIE_PEAK)
    _pan_to(lua, ns, (1900.0, 2550.0))
    assert not _cave_shown(lua, ns)["cave"]


@pytest.mark.parametrize("on", [True, False])
def test_a_caves_map_zoomed_far_out_is_left_where_the_view_is(on):
    lua, ns = _seamless(on=on)
    G, st = ns.GPS, ns.settings.gps
    _open_tomb(lua, ns)
    x, y = G.ViewState()[0:2]
    art = G.CaveArt(0, TOMB)
    while st.zoom <= G.CaveSeamZoom(art) * G.LEAVE_INSIDE_ZOOM_TIMES:
        assert _cave_shown(lua, ns)["kept"]
        _wheel(lua, G, 1.25)
    shown = _cave_shown(lua, ns)
    assert not shown["kept"] and not shown["cave"] and not shown["bar"] and not shown["line"]
    assert G.ViewState()[0:2] == pytest.approx((x, y)) and G.IsFree()  # (in place)
    _wheel(lua, G, 1.25, 4)
    assert not _cave_shown(lua, ns)["cave"]
    # back in over it: the land
    while st.zoom > 100:
        _wheel(lua, G, 0.8)
    shown = _cave_shown(lua, ns)
    assert not shown["cave"] and shown["name"] != "Shadowvale Tomb" and not shown["bar"]


@pytest.mark.parametrize("on", [True, False])
def test_right_click_in_a_caves_map_still_goes_back(on):
    lua, ns = _seamless(on=on)
    G = ns.GPS
    _open_tomb(lua, ns)
    _drag(lua, (0, 120))  # (looked about in it)
    _wheel(lua, G, 1.25, 2)
    assert _cave_shown(lua, ns)["kept"]
    _right_click(lua)
    free = G.BrowseState()[1]
    assert not free.cave and (free.x, free.y) == pytest.approx(TOMB_WAY)  # (the view it was opened from)
    assert ns.settings.gps.zoom == pytest.approx(250)


def _open_undercity(lua, ns):
    """Undercity's level opened from its icon (G.ShowCity; the player up top in Brill), wheeled in on it."""
    G = ns.GPS
    lua.execute("AGPS_T = (AGPS_T or 0) + 1000")
    G.Follow()
    G.ShowCity(1458)
    ns.settings.gps.zoom = 300.0
    G.Update()
    assert G.inside is not None


@pytest.mark.parametrize("on", [True, False])
def test_undercity_opened_from_its_icon_is_left_panned_far_away(on):
    lua, ns = _seamless(on=on)
    G = ns.GPS
    _open_undercity(lua, ns)
    _pan_to(lua, ns, AERIE_PEAK)
    free = G.BrowseState()[1]
    assert G.inside is None and not free.interior and not free.city
    _right_click(lua)  # (no jump back to where it was opened from: following the player in Brill)
    assert G.IsFree() or G.BrowseState()[0] is not None
    G.Follow()
    G.ShowCity(1458)
    ns.settings.gps.zoom = 300.0
    _pan_to(lua, ns, AERIE_PEAK)
    _pan_to(lua, ns, (1557.0, 393.0))  # (back over the city: the land, its map left)
    assert G.inside is None


@pytest.mark.parametrize("on", [True, False])
def test_undercity_opened_from_its_icon_is_left_zoomed_far_out(on):
    lua, ns = _seamless(on=on)
    G, st = ns.GPS, ns.settings.gps
    _open_undercity(lua, ns)
    x, y = G.ViewState()[0:2]
    while st.zoom <= G.CITY_MAX_ZOOM * G.LEAVE_INSIDE_ZOOM_TIMES:
        _wheel(lua, G, 1.25)
    free = G.BrowseState()[1]
    assert not free.interior and not free.city and G.ViewState()[0:2] == pytest.approx((x, y))
    st.zoom = 300.0
    G.Update()
    # (back in: no longer the map opened from its icon; on OpenMap the city's whole map as zoomed in over it, asked
    # 2026-11-15, G.CityUnderView; the other styles: the land)
    assert not G.BrowseState()[1].city
    if on:
        assert G.zoomedInside == 7675285
    else:
        assert G.inside is None
    # still in it, right-click goes back to the view it was opened from (following the player), as before
    _open_undercity(lua, ns)
    _wheel(lua, G, 1.25, 2)
    _right_click(lua)
    assert not G.IsFree()


@pytest.mark.parametrize("on", [True, False])
def test_the_player_down_in_undercity_keeps_its_map(on):
    """Not the player's own inside map: down in Undercity, dragged well away and back, wheeled far out and back in,
    its map again, as before."""
    lua, ns = _seamless(on=on)
    G, st = ns.GPS, ns.settings.gps
    _down_in_undercity(lua, ns)
    _pan_to(lua, ns, (1557.0, 1400.0))
    _pan_to(lua, ns, (1593.5, 157.3))
    assert G.inside is not None
    G.Follow()
    G.Update()
    n = 0
    while st.zoom <= G.CITY_MAX_ZOOM * G.LEAVE_INSIDE_ZOOM_TIMES * 1.5 and n < 30:
        _wheel(lua, G, 1.25)
        n += 1
    while st.zoom > 300:
        _wheel(lua, G, 0.8)
    assert G.inside is not None and G.shownLevel == 10001


def test_a_held_map_keeps_a_dungeons_map_as_before():
    lua, ns = _seamless()
    G, st = ns.GPS, ns.settings.gps
    G.ShowInstance(DM)
    lua.globals().AzerothGPS.HoldMap("StreetGuess", True, None, lua.eval("{ style = 'zone' }"))
    G.Update()
    _wheel(lua, G, 1.25, 10)
    assert G.shownView.instance == DM  # (no way out to the land while a game holds the map)


# ---------------------------------------------------------------- the interiors' edge blend (issue #85)

def _ground(lua):
    """The laid quads: (art, ground) as lists (the ground: G.InteriorGround's tinted pieces; not the terrain round a
    building, _terrain)."""
    lua.execute("""AGPS_L = { a = {}, g = {} }
      for _, q in ipairs(AGPS_NS.GPS.laidTiles.quads) do
        if not q.terrain then
          local k = q.tint and 'g' or 'a'
          AGPS_L[k][#AGPS_L[k] + 1] = q
        end
      end""")
    got = lua.eval("AGPS_L")
    return list(got.a.values()), list(got.g.values())


def _terrain(lua):
    """The laid quads of the terrain round a building (G.LayoutInteriorTerrain's), as a list."""
    lua.execute("""AGPS_L = {}
      for _, q in ipairs(AGPS_NS.GPS.laidTiles.quads) do
        if q.terrain then AGPS_L[#AGPS_L + 1] = q end
      end""")
    return list(lua.eval("AGPS_L").values())


def _dark_backdrop_shown(lua, G):
    """Whether the dungeon map's dark ground over the whole map (DrawFloors' floorBg) shows."""
    lua.globals().AGPS_TL = G.quadLayer._parent
    lua.execute("""AGPS_D = false
      for _, w in ipairs(AGPS_WIDGETS) do
        if w._parent == AGPS_TL and w._kind == 'Texture' and w._shown and tostring(w._tex):find('^color:0.05') then
          AGPS_D = true
        end
      end""")
    return lua.eval("AGPS_D")


def test_the_interior_ground_is_a_soft_box_round_each_room():
    """G.InteriorGround: each model group with art gets its box, opaque, and a feather INTERIOR_FEATHER_YD round it,
    nine pieces of Media/Feather that tile the box grown by the feather exactly, the texture's middle on the box."""
    lua, ns = _seamless()
    G = ns.GPS
    F, cut = G.INTERIOR_FEATHER_YD, G.INTERIOR_FEATHER_CUT
    assert F == 60 and cut == coast_cut()
    lua.execute("""AGPS_NS.WMOs[-85] = { groups = {
        { 10, 20, 0, 50, 80, 10, blocks = { { 1, 0, 0, 80, 120 } } },
        { 0, 0, 100, 5, 5, 110 },  -- (no art: no ground)
      } }""")
    p = lua.eval("{ -85, 1000, 2000, 0, 0 }")  # (placed at world 1000, 2000, not turned)
    out = G.InteriorGround(lua.eval("{}"), 1000, 2000, lua.eval("{ ... }", p), None, 0, 500, 500)  # (1 px a yard)
    q = list(out.values())
    assert len(q) == 9 and all(x[1] == G.INTERIOR_FEATHER and x.layer == "BORDER"
                               and list(x.tint.values()) == list(G.INTERIOR_GROUND.values()) for x in q)
    # (world: x north, y west; the model's x and y are the world's here: theta 0; on the screen x is east = -y)
    # (a quad's width is along the model's x, turned a quarter onto the screen's north: G.LayoutInterior's art)
    xs = sorted({(round(x[2] - x[5] / 2 + 0.25, 3), round(x[2] + x[5] / 2 - 0.25, 3)) for x in q})
    ys = sorted({(round(x[3] - x[4] / 2 + 0.25, 3), round(x[3] + x[4] / 2 - 0.25, 3)) for x in q})
    # the screen's rows (north, +y) are the model's x: 10..50 grown by F; its columns (east, -y) the model's -y
    assert ys == [(10 - F, 10), (10, 50), (50, 50 + F)]
    assert xs == [(-80 - F, -80), (-80, -20), (-20, -20 + F)]
    # the texture's middle half on the box, its sides on the feathers
    mid = [x for x in q if [x[i] for i in (7, 8, 9, 10)] == pytest.approx([cut, 1 - cut, cut, 1 - cut])]
    assert len(mid) == 1 and (mid[0][4], mid[0][5]) == pytest.approx((40.5, 60.5))
    assert (mid[0][2], mid[0][3]) == pytest.approx((-50, 30))  # (the box's middle: model x 30 north, y 50 west)
    for x in q:
        assert 0 <= min(x[7], x[8], x[9], x[10]) and max(x[7], x[8], x[9], x[10]) <= 1
        assert x[6] == pytest.approx(math.pi / 2)  # (the model's turn, as its art's: G.LayoutInterior)
    # no feather: the box alone
    G.INTERIOR_FEATHER_YD = 0
    out = G.InteriorGround(lua.eval("{}"), 1000, 2000, lua.eval("{ ... }", p), None, 0, 500, 500)
    assert len(out) == 1 and out[1][5] == pytest.approx(60.5)
    # out of view: nothing
    G.INTERIOR_FEATHER_YD = F
    assert len(G.InteriorGround(lua.eval("{}"), 9000, 9000, lua.eval("{ ... }", p), None, 0, 500, 500)) == 0
    # a floor band that misses the group: nothing
    assert len(G.InteriorGround(lua.eval("{}"), 1000, 2000, lua.eval("{ ... }", p), lua.eval("{ 50, 60 }"), 0, 500,
                                500)) == 0


def coast_cut():
    from azerothgps import coast
    return coast.FEATHER_CUT


def test_a_dungeons_map_lies_on_the_world_art_at_its_way_in_with_a_soft_edge():
    lua, ns = _seamless()
    G, A, st = ns.GPS, ns.Atlas, ns.settings.gps
    # (over the terrain round its way in since 2026-11-15, as a cave's: test_dungeon_terrain.py. Where there's none to
    # lay, G.InstanceTerrainSpot nil: the art under its rooms' feathered ground, as here)
    lua.execute("AGPS_REAL_ITS = AGPS_NS.GPS.InstanceTerrainSpot; AGPS_NS.GPS.InstanceTerrainSpot = function() return nil end")
    G.ShowInstance(DM)
    G.Update()
    view = G.shownView
    assert view.instance == DM and view.rot == 0
    # the art under it where the dungeon lies on the continent: its way in (the spot inside it the way in puts you)
    # on its way in at Moonbrook
    e = G.WingEntrance(DM, None)
    spot = list(view.interiorSpot.values())
    assert spot == pytest.approx([0, e[2] - e[4], e[3] - e[5]])
    assert view.interiorEdge and A.artHost.IsShown(A.artHost) and G.seamArt == 1 and G.quadAlpha == 1
    assert G.SeamReading().interior is True
    assert G.laidTiles.laidSig.endswith(":ground")
    art, ground = _ground(lua)
    assert art and ground and len(ground) % 9 == 0
    # no dark ground over the whole map: the rooms' own
    assert not _dark_backdrop_shown(lua, G)
    # drawn: Media\Feather tinted dark
    lua.execute("""AGPS_D = 0
      for _, w in ipairs(AGPS_WIDGETS) do
        if w._shown and w._parent == AGPS_NS.GPS.quadLayer and w._tex == AGPS_NS.GPS.INTERIOR_FEATHER then
          assert(w._vc == string.format("%.2f,%.2f,%.2f", unpack(AGPS_NS.GPS.INTERIOR_GROUND)))
          AGPS_D = AGPS_D + 1
        end
      end""")
    assert lua.eval("AGPS_D") == len(ground)
    # the knob (issue #72's, API 18): the feather's yards, live
    K = lua.globals().AzerothGPS.SeamKnobs()
    assert K.Get("INTERIOR_FEATHER_YD") == 60
    assert K.Set("INTERIOR_FEATHER_YD", 0)
    G.Update()
    assert len(_ground(lua)[1]) == len(ground) // 9
    assert K.Set("INTERIOR_FEATHER_YD", 999) and K.Get("INTERIOR_FEATHER_YD") == 300
    K.Reset()
    G.Update()
    assert len(_ground(lua)[1]) == len(ground)
    # a held map (StreetView): as before
    lua.globals().AzerothGPS.HoldMap("StreetGuess", True, None, lua.eval("{ style = 'minimap' }"))
    G.Update()
    assert G.shownView.instance == DM and not G.shownView.interiorEdge and not _ground(lua)[1]
    assert _dark_backdrop_shown(lua, G) and not (A.artHost and A.artHost.IsShown(A.artHost))
    lua.globals().AzerothGPS.HoldMap("StreetGuess", False)
    G.Update()
    assert G.shownView.interiorEdge
    lua.execute("AGPS_NS.GPS.InstanceTerrainSpot = AGPS_REAL_ITS")


def test_a_dungeon_with_no_known_way_in_keeps_its_dark_ground():
    lua, ns = _seamless()
    G = ns.GPS
    lua.execute(f"local i = AGPS_NS.Instances[{DM}] i.entrances = {{}} i.ghost = nil")
    G.ShowInstance(DM)
    G.Update()
    assert G.shownView.instance == DM and G.shownView.interiorSpot is None and not G.shownView.interiorEdge
    assert not _ground(lua)[1] and _dark_backdrop_shown(lua, G)


@pytest.mark.parametrize("on", [True, False])
def test_a_caves_map_has_the_terrain_round_it(on):
    """(2026-11-14, "doesn't seem to apply everywhere": issue #85 laid the stitched art under a cave's map, with its
    60 yd feathers, black heading-up) a cave's map on its continent has the terrain round it as a building's has, a
    little darker, the rooms' ground feathered a few yards; no dark ground over the whole map."""
    lua, ns = _seamless(on=on)
    G = ns.GPS
    lua.execute("""AGPS_C = nil
      for _, c in ipairs(AGPS_NS.Caves[0]) do
        if AGPS_NS.GPS.CaveArt(0, c[2]) then AGPS_C = c[2] break end
      end""")
    key = lua.eval("AGPS_C")
    assert key and G.ShowCave(0, key)
    G.Update()
    view = G.shownView
    assert view.cave
    art, ground = _ground(lua)
    assert art
    if not on:  # (the Terrain style: as before)
        assert not view.interiorEdge and not ground and not _terrain(lua) and _dark_backdrop_shown(lua, G)
        assert view.interiorTerrain is None
        return
    assert view.rot == 0
    _check_terrain_round_the_rooms(lua, ns)
    assert not _dark_backdrop_shown(lua, G) and not G.SeamReading().interior
    assert G.laidTiles.laidSig.startswith("cave:")


@pytest.mark.parametrize("setup,cont", CITIES)
def test_an_inside_map_turning_with_the_player_has_the_terrain_round_it(setup, cont):
    """The art can't turn, the terrain can: heading-up, a city's inside map (a city in a mountain's, an underground
    city's level) has the terrain round it, turning with it (2026-11-14), never the black or the art."""
    lua, ns = _seamless()
    G, A, st = ns.GPS, ns.Atlas, ns.settings.gps
    lua.execute(setup + " GetPlayerFacing = function() return 1 end")
    st.rotate = True
    st.zoom = 300.0
    G.Follow()
    G.Update()
    assert G.inside is not None and G.shownView.rot != 0
    assert not G.shownView.interiorEdge and not (A.artHost and A.artHost.IsShown(A.artHost))
    assert G.shownView.interiorTerrain and _terrain(lua) and _ground(lua)[1]
    st.rotate = False
    G.Update()
    assert G.inside is not None and G.shownView.interiorTerrain and not G.shownView.interiorEdge and _terrain(lua)


# ------------------------------------------------- the terrain round a building's inside map (asked 2026-11-14)

GOLDSHIRE_INN = ("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = -9466.0, 16.0, 0, 63.0 "
                 "IsIndoors = function() return true end")  # (the Lion's Pride Inn, downstairs)


def _in_the_inn(lua, ns, zoom=100.0):
    G = ns.GPS
    lua.execute(GOLDSHIRE_INN + " AGPS_T = (AGPS_T or 0) + 1000")
    ns.settings.gps.zoom = zoom
    G.Follow()
    G.Update()
    assert G.inside is not None and G.shownInside is not None  # (the inn's inside map)


def _check_terrain_round_the_rooms(lua, ns):
    """The inside map's rooms (an inn's, Undercity's, a cave's) with the terrain view's own tiles round them, 20% darker under the rooms' dark ground; no
    stitched art; the dark ground's feather a few yards, not INTERIOR_FEATHER_YD."""
    G, A = ns.GPS, ns.Atlas
    view = G.shownView
    assert view.interiorTerrain and view.interiorSpot is None and not view.interiorEdge
    assert not (A.artHost and A.artHost.IsShown(A.artHost)) and not G.seamArt  # (no stitched art laid)
    assert G.laidTiles.laidSig.endswith(":terrain")
    art, ground = _ground(lua)
    terrain = _terrain(lua)
    assert art and ground and terrain
    if any(q.outline for q in ground):
        # (a building's, 2026-11-14: "tighten up the black outline to the shape of the interior instead of black
        # squares": its art again in black under itself, nudged every way, G.InteriorOutline)
        # (a big map's lighter, 2026-11-15: G.OutlineRings, within OUTLINE_MAX_COPIES; Undercity's stuttered)
        blocks = [n for n in range(1, len(art) + 1) if len(ground) == n * sum(len(r[3] or G.OUTLINE_OFFSETS)
                                                                         for r in G.OutlineRings(n).values())]
        assert blocks, f"{len(ground)} outline copies: not a whole outline of the art's blocks"
        offsets = len(ground) // blocks[0]
        # (a cave's, an underground city's too since 2026-11-14: its world map's pieces under the art aren't outlined)
        assert all(q.outline for q in ground)
        assert {q[1] for q in ground} <= {q[1] for q in art} and len(ground) // offsets <= len(art)
        assert all(list(q.tint.values())[:3] == [0, 0, 0] and q.layer == "BORDER" for q in ground)
        x, y, cont, rot, s, half = G.ViewState()
        own = list(G.LayoutMinimap(x, y, ns.Geo.Base(cont), rot, half / s, half).values())
        assert [(q[1], round(q[2], 3), round(q[3], 3)) for q in terrain] == [(q[1], round(q[2], 3), round(q[3], 3))
                                                                              for q in own]
        return
    assert len(ground) % 9 == 0
    # the terrain view's own tiles there, the same textures in the same places (G.LayoutMinimap), shaded and under
    # the rooms' ground
    x, y, cont, rot, s, half = G.ViewState()
    own = list(G.LayoutMinimap(x, y, ns.Geo.Base(cont), rot, half / s, half).values())  # (Undercity: its base's)
    assert [(q[1], round(q[2], 3), round(q[3], 3)) for q in terrain] == [(q[1], round(q[2], 3), round(q[3], 3))
                                                                          for q in own]
    k = G.INTERIOR_TERRAIN_SHADE
    assert k == pytest.approx(0.8)
    for q in terrain:
        assert list(q.tint.values()) == pytest.approx([k, k, k, 1]) and q.layer == "BACKGROUND"
    assert all(q.layer == "BORDER" for q in ground) and all((q.layer or "ARTWORK") == "ARTWORK" for q in art)
    # the dark ground's edge: a small margin (its feather pieces INTERIOR_TERRAIN_FEATHER_YD thick, not 60 yd)
    F = G.INTERIOR_TERRAIN_FEATHER_YD
    assert 0 < F <= 10 < G.INTERIOR_FEATHER_YD
    # (a piece's width runs along its texture's u (q[7], q[8]), its height along v (q[9], q[10]): a feather side's
    # cut, 0..cut or 1-cut..1, is F thick; a room narrower than that, Undercity's, may be thinner than its feathers)
    cut = G.INTERIOR_FEATHER_CUT
    sides = [(0, cut), (1 - cut, 1)]
    fw = [q[4] for q in ground if (q[7], q[8]) in sides] + [q[5] for q in ground if (q[9], q[10]) in sides]
    assert fw and all(w == pytest.approx(F * s + 0.5, abs=0.01) for w in fw)
    assert all(min(q[4], q[5]) < G.INTERIOR_FEATHER_YD * s for q in ground if q[7] in (0, 1 - G.INTERIOR_FEATHER_CUT)
               and q[8] in (G.INTERIOR_FEATHER_CUT, 1))
    # drawn: the tiles darkened by their vertex color
    lua.execute("""AGPS_D = 0
      local G = AGPS_NS.GPS
      local want = string.format("%.2f,%.2f,%.2f", G.INTERIOR_TERRAIN_SHADE, G.INTERIOR_TERRAIN_SHADE, G.INTERIOR_TERRAIN_SHADE)
      for _, w in ipairs(AGPS_WIDGETS) do
        if w._shown and w._parent == G.quadLayer and w._vc == want then AGPS_D = AGPS_D + 1 end
      end""")
    assert lua.eval("AGPS_D") == len(terrain)


def test_a_buildings_inside_map_has_the_terrain_round_it_a_little_darker():
    """(asked 2026-11-14: "close in the black area outline to much smaller and show the terrain map in the surrounding
    area instead slightly darker though by like 20%") in the seamless style, the map's window."""
    lua, ns = _seamless()
    G, st = ns.GPS, ns.settings.gps
    _in_the_inn(lua, ns)
    assert G.shownView.rot == 0
    _check_terrain_round_the_rooms(lua, ns)
    # walked a few yards: laid again round the new spot, still the terrain
    lua.execute("AGPS_POS[1] = AGPS_POS[1] + 3 AGPS_T = AGPS_T + 5")
    G.Update()
    _check_terrain_round_the_rooms(lua, ns)
    # heading-up: the terrain turns with the rooms (the art couldn't)
    lua.execute("GetPlayerFacing = function() return 1 end AGPS_T = AGPS_T + 5")
    st.rotate = True
    G.Update()
    assert G.shownView.rot != 0
    _check_terrain_round_the_rooms(lua, ns)
    st.rotate = False
    # the knob (issue #72's, API 18): the feather's yards, live
    K = lua.globals().AzerothGPS.SeamKnobs()
    assert K.Get("INTERIOR_TERRAIN_FEATHER_YD") == 6
    assert K.Set("INTERIOR_TERRAIN_FEATHER_YD", 0)
    G.Update()
    n = len(_ground(lua)[1])
    K.Reset()
    G.Update()
    # (a building's edge is its outline since 2026-11-14, G.InteriorOutline: the feather's knob is the cities' and
    # caves' now, a building's ground the same either way)
    assert len(_ground(lua)[1]) == n and all(q.outline for q in _ground(lua)[1])


def test_a_buildings_inside_map_in_another_style_is_as_before():
    """The Terrain style: the rooms alone, no terrain round them, no ground of their own, as before."""
    lua, ns = _seamless(on=False)
    _in_the_inn(lua, ns)
    G = ns.GPS
    assert G.shownView.interiorTerrain is None and not _terrain(lua) and not _ground(lua)[1]
    assert _ground(lua)[0] and not G.laidTiles.laidSig.endswith(":terrain")


def test_the_minimap_square_has_the_terrain_round_a_building():
    """(the second screenshot, 2026-11-14: the square inside the inn, with the world map option on, nearly all black:
    the stitched art under the rooms and their 60 yd feathers over most of its small radius) the square is the
    seamless map too: the same terrain round the rooms, turning with the minimap as well."""
    from test_world_map_host import SETUP  # (the minimap's and a closed world map's)
    lua, ns = _seamless()
    G, st = ns.GPS, ns.settings.gps
    lua.execute(SETUP)
    st.shown, st.minimized = True, None
    st.useWorldMap = True  # (as in the screenshot: the world map closed, the square shows)
    st.replaceMinimap = True
    G.ApplySettings()
    assert G.MinimapMode()
    _in_the_inn(lua, ns)
    assert G.MinimapMode() and G.shownView.s == pytest.approx(G.ViewState()[5] / G.MinimapRadius())
    _check_terrain_round_the_rooms(lua, ns)
    lua.execute("AGPS_MM_CVAR = '1' GetPlayerFacing = function() return 2 end AGPS_T = AGPS_T + 5")  # (rotateMinimap)
    G.Update()
    assert G.shownView.rot != 0
    _check_terrain_round_the_rooms(lua, ns)


def test_the_map_in_the_world_map_has_the_terrain_round_a_building():
    """The GPS map hosted in the game's world map (useWorldMap): the same terrain round the rooms."""
    from test_world_map_host import SETUP
    lua, ns = _seamless()
    G, st = ns.GPS, ns.settings.gps
    lua.execute(SETUP)
    st.shown, st.minimized = True, None
    st.useWorldMap = True
    G.ApplySettings()
    lua.globals().AzerothGPS_ToggleMap()
    assert G.WorldMapHosted()
    _in_the_inn(lua, ns)
    assert G.WorldMapHosted() and G.shownView.rot == 0
    _check_terrain_round_the_rooms(lua, ns)
    # (with the square on too, it's a second map of the same code meanwhile: the same look there)
    st.replaceMinimap = True
    G.ApplySettings()
    c = ns.mapClone
    assert c is not None and c.MinimapMode()
    c.ApplySettings()
    c.Update()
    # (its engine loaded when first asked: before, never on that small radius, so it drew as the Terrain style)
    assert c.Seamless() and c.shownView.interiorTerrain and c.shownView.interiorSpot is None
    assert any(q.terrain for q in c.laidTiles.quads.values())


# ------------------------------------------- the terrain round Undercity's level (asked 2026-11-14, the War Quarter)

UNDERCITY = CITIES[1][0]  # (down in Undercity: its own level, 10001, drawn in its base continent 0's yards)


def _down_in_undercity(lua, ns):
    G = ns.GPS
    lua.execute(UNDERCITY + " AGPS_T = (AGPS_T or 0) + 1000")
    ns.settings.gps.zoom = 300.0
    G.Follow()
    G.Update()
    assert G.inside is not None and G.shownLevel == 10001  # (its level's map, its roads)


def test_undercity_has_the_terrain_round_its_rooms():
    """(asked 2026-11-14 with a screenshot of the minimap square in the War Quarter: "the change you did for always
    showing the terrain map and smaller black borders looks great but doesn't seem to apply everywhere. For example
    undercity here") down in Undercity the land up top round its rooms, shaded, as a building's; no stitched art blend
    under it (issue #85's interiorSpot), north up and heading-up alike."""
    lua, ns = _seamless()
    G, st = ns.GPS, ns.settings.gps
    _down_in_undercity(lua, ns)
    assert G.shownView.rot == 0
    _check_terrain_round_the_rooms(lua, ns)
    assert G.laidTiles.laidSig.startswith("in:") and not _dark_backdrop_shown(lua, G)
    lua.execute("GetPlayerFacing = function() return 1 end AGPS_T = AGPS_T + 5")
    st.rotate = True
    G.Update()
    assert G.shownView.rot != 0 and G.shownLevel == 10001
    _check_terrain_round_the_rooms(lua, ns)
    # the Terrain style: as before (the rooms on black, nothing round them)
    lua2, ns2 = _seamless(on=False)
    _down_in_undercity(lua2, ns2)
    assert ns2.GPS.shownView.interiorTerrain is None and not _terrain(lua2) and not _ground(lua2)[1]


def test_undercity_on_the_minimap_square_has_the_terrain_round_it():
    """The screenshot's own map: the minimap square down in Undercity, turning with the minimap too."""
    from test_world_map_host import SETUP
    lua, ns = _seamless()
    G, st = ns.GPS, ns.settings.gps
    lua.execute(SETUP)
    st.shown, st.minimized = True, None
    st.useWorldMap = True
    st.replaceMinimap = True
    G.ApplySettings()
    assert G.MinimapMode()
    _down_in_undercity(lua, ns)
    assert G.MinimapMode()
    _check_terrain_round_the_rooms(lua, ns)
    lua.execute("AGPS_MM_CVAR = '1' GetPlayerFacing = function() return 2 end AGPS_T = AGPS_T + 5")  # (rotateMinimap)
    G.Update()
    assert G.shownView.rot != 0
    _check_terrain_round_the_rooms(lua, ns)


# (up top at the Ruins of Lordaeron, over Undercity's rooms: the game's best map Undercity's own with the Ruins'
# subzone, or Tirisfal's)
UP_AT_THE_RUINS = [
    "AGPS_MAP = 1458 AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = 1643.8, 245.7, 0, nil "
    "GetSubZoneText = function() return 'Ruins of Lordaeron' end",
    "AGPS_MAP = 1420 AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = 1643.8, 245.7, 0, nil "
    "GetSubZoneText = function() return 'Ruins of Lordaeron' end",
]


def _up_at_the_ruins(lua, ns, which=0):
    lua.execute(UP_AT_THE_RUINS[which] + " AGPS_T = (AGPS_T or 0) + 1000")
    ns.settings.gps.zoom = 300.0
    ns.GPS.Follow()
    ns.GPS.Update()


@pytest.mark.parametrize("minimap", [False, True])
@pytest.mark.parametrize("which", [0, 1])
def test_undercity_shows_only_once_down_in_it(which, minimap):
    """(asked 2026-11-16 with a screenshot at the Ruins of Lordaeron: "Don't show undercity on minimap until player is
    actually in UC after taking the lift down") following the player up top, over its rooms: the land, not Undercity's
    map (G.CityUnderView); down the lift its map; back up the land again. The GPS window and the minimap square
    alike."""
    lua, ns = _seamless()
    G, st = ns.GPS, ns.settings.gps
    if minimap:
        from test_world_map_host import SETUP
        lua.execute(SETUP)
        st.shown, st.minimized = True, None
        st.useWorldMap = True
        st.replaceMinimap = True
        G.ApplySettings()
        assert G.MinimapMode()
    _up_at_the_ruins(lua, ns, which)
    assert ns.Nav.PlayerLevel(0) != 10001
    if minimap:
        assert G.inside is None and G.zoomedInside is None and G.shownLevel != 10001
    else:  # (the map, zoomed in over its rooms: its map, as ever; "zoom in from the map on UC stopped working")
        assert G.inside is not None
    lua.execute("GetSubZoneText = function() return 'Trade Quarter' end")  # (down the lift)
    _down_in_undercity(lua, ns)
    _up_at_the_ruins(lua, ns, which)
    lua.execute("AGPS_T = AGPS_T + 1000 GetSubZoneText = function() return 'Ruins of Lordaeron' end")
    G.Update()
    if minimap:
        assert G.inside is None and G.zoomedInside is None and G.shownLevel != 10001
        assert G.MinimapMode()
    else:
        assert G.inside is not None


def test_undercity_opened_from_its_icon_has_the_terrain_round_it():
    """Undercity's map opened from its icon (G.ShowCity, the player up top elsewhere): the same terrain round it."""
    lua, ns = _seamless()
    G = ns.GPS
    lua.execute("AGPS_T = (AGPS_T or 0) + 1000")
    G.ShowCity(1458)
    ns.settings.gps.zoom = 300.0  # (wheeled in on it: the city's map, G.INTERIOR_MAX_ZOOM)
    G.Update()
    assert G.inside is not None and G.shownView.rot == 0
    _check_terrain_round_the_rooms(lua, ns)


def test_the_quests_show_on_the_art_past_the_tiles_where_the_world_stages_icons_go():
    """(asked 2026-11-05: zoomed out on the art over Tirisfal, no quest icons or areas) the world stage past the tiles
    (G.SeamFar, as tuned in testing, issue #90) keeps a continent map's icons only, but the quests' objectives,
    turn-ins stay on the art out to G.SEAM_QUESTS_YD (their areas at any zoom); herbs and ore still go with the rest."""
    lua, ns = _seamless()
    G, L, st = ns.GPS, ns.Layers, ns.settings.gps
    lua.execute("""
      local L = AGPS_NS.Layers
      local x, y = L.MapToWorld(1420, 0.5, 0.5)
      AGPS_POS = { x, y, 0 }
      AGPS_QL = C_QuestLog
      C_QuestLog = setmetatable({
        GetQuestsOnMap = function(map)
          if map == 1420 then return { { questID = 601, x = 0.52, y = 0.5 }, { questID = 602, x = 0.48, y = 0.52 } } end
          return {}
        end,
        IsComplete = function(id) return id == 602 end,
        GetTitleForQuestID = function(id) return id == 601 and "The Cult of the Damned" or "Gordo's Task" end,
      }, { __index = AGPS_QL })
      L.AddNode(0, x + 40, y, "Peacebloom", "herb")
      AGPS_AREA_AT = { x - 60, y - 30, x + 60, y + 30 }
      AGPS_EACH_AREA = L.EachArea
      L.EachArea = function(cont, cx, cy, reach, maps, fn, fillFn)
        local a = AGPS_AREA_AT
        fn(a[1], a[2], a[3], a[2])
        if fillFn then fillFn(a[1], a[2], a[3], a[4]) end
      end
    """)
    st.layerQuests = st.layerQuestAreas = st.layerHerbs = True

    def shown(zoom):
        st.zoom = zoom * G.ZoomScale()
        G.Redraw()
        lua.execute("AGPS_T = AGPS_T + 3")
        G.Update()
        ws = [w for w in lua.eval("AGPS_WIDGETS").values() if w._shown and w._kind == "Button"]
        quests = sorted(int(w.questID) for w in ws if w.questID)
        herbs = [w for w in ws if w.name == "Peacebloom"]
        return G.shownView, quests, len(herbs), G.areaFillUsed

    try:
        view, quests, herbs, areas = shown(250)  # (the terrain alone)
        assert not view.artOnly and quests == [601, 602] and herbs == 1 and areas == 1
        # (the screenshot's zoom: Tirisfal on the art, past the tiles, so the world stage's icons)
        view, quests, herbs, areas = shown(1300)
        assert view.artOnly and view.seamFar
        assert quests == [601, 602] and areas == 1  # (was none: the quests went with the points of interest)
        assert herbs == 0  # (the rest of the marks as tuned)
        view, quests, herbs, areas = shown(G.SEAM_QUESTS_YD * 0.95)
        assert view.seamFar and quests == [601, 602] and areas == 1
        # (past it, the continents' art: the zone's quests would be a pile over the player; the areas' thin outlines stay)
        view, quests, herbs, areas = shown(G.SEAM_QUESTS_YD * 1.2)
        assert view.seamFar and quests == [] and areas == 1
    finally:
        lua.execute("C_QuestLog = AGPS_QL AGPS_NS.Layers.EachArea = AGPS_EACH_AREA")


def test_the_roads_and_walls_shown_stay_on_the_art_a_little_past_the_tiles():
    """Asked 2026-11-14: with Show Roads and Walls on, zoomed out on the seamless map they went with the terrain's tiles
    (about 410 yd); they stay on the art out to G.SEAM_DATA_YD, then go, the tools on too."""
    lua, ns = _seamless()
    G, st = ns.GPS, ns.settings.gps
    lua.execute("""
      AGPS_LR, AGPS_LW = 0, 0
      local G = AGPS_NS.GPS
      local lr, lw = G.LayoutRoads, G.LayoutWalls
      G.LayoutRoads = function(...) AGPS_LR = AGPS_LR + 1 return lr(...) end
      G.LayoutWalls = function(...) AGPS_LW = AGPS_LW + 1 return lw(...) end
    """)
    st.showRoads, st.showWalls = True, True

    def drawn(ref_yd):
        st.zoom = ref_yd * G.ZoomScale()
        lua.execute("AGPS_LR, AGPS_LW = 0, 0 AGPS_T = (AGPS_T or 0) + 1")
        G.Redraw()
        G.Update()
        return bool(G.shownView.artOnly), lua.eval("AGPS_LR") > 0, lua.eval("AGPS_LW") > 0

    assert drawn(G.SEAM_TILES_OUT[1] * 0.8)[1:] == (True, True)  # (on the terrain, as always)
    assert drawn(G.SEAM_DATA_YD * 0.9) == (True, True, True)  # (the art alone: still drawn)
    assert drawn(G.SEAM_DATA_YD * 1.5) == (True, False, False)  # (further out: gone)
    st.showRoads, st.showWalls = False, False
    assert drawn(G.SEAM_DATA_YD * 0.9) == (True, False, False)  # (not shown: none)
    # the road and wall tools on: past it none either (for performance)
    try:
        G.SetRoadMode(True)
        assert drawn(G.SEAM_DATA_YD * 0.9)[1] and not drawn(G.SEAM_DATA_YD * 1.5)[1]
        G.SetWallMode(True)
        assert drawn(G.SEAM_DATA_YD * 0.9)[2] and not drawn(G.SEAM_DATA_YD * 1.5)[2]
    finally:
        G.SetRoadMode(False)
        G.SetWallMode(False)


def test_hovering_a_building_shows_its_inside_map_a_click_holds_it_and_right_click_lets_it_go():
    """Asked 2026-11-14: "any building I'm hovering anywhere on the map"; "allow left click to hold the interior map
    view overlay for 30s"; and a video: after a right-click no building of Orgrimmar (one model) opened again until the
    map was closed and opened (G.outsideOf, by model): now that one building is let go only till the mouse leaves it."""
    lua, ns = _seamless()
    G = ns.GPS
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = -9400.0, 60.0, 0, 60.0 "
                "IsIndoors = function() return false end AGPS_T = (AGPS_T or 0) + 1000")
    ns.settings.gps.zoom = 80.0
    G.Follow()
    G.Update()
    assert G.inside is None
    def mouse(x, y):
        lua.execute(f"AGPS_NS.GPS.CursorWorld = function() return {x}, {y}, 0 end AGPS_T = AGPS_T + 1")
        G.BuildingHover()
        G.Update()
    mouse(-9466.0, 16.0)  # (over the Lion's Pride Inn)
    assert G.zoomedInside is not None and G.inside is not None
    mouse(-9400.0, 60.0)  # (off it)
    assert G.zoomedInside is None
    # a left click over it holds it, the mouse anywhere, till the setting's seconds are up
    mouse(-9466.0, 16.0)
    assert G.HoldInside()
    mouse(-9400.0, 60.0)
    assert G.zoomedInside is not None
    lua.execute(f"AGPS_T = AGPS_T + {G.InteriorHoldSec() + 1}")
    G.BuildingHover()
    G.Update()
    assert G.zoomedInside is None
    # right-click: let go, and not again till the mouse leaves it; back over it, it shows (no G.outsideOf kept)
    mouse(-9466.0, 16.0)
    assert G.zoomedInside is not None
    G.TerrainZoomOut()
    G.Update()
    assert G.zoomedInside is None and G.outsideOf is None
    mouse(-9466.0, 16.0)
    assert G.zoomedInside is None
    mouse(-9400.0, 60.0)
    mouse(-9466.0, 16.0)
    assert G.zoomedInside is not None
    # zoomed out past the slider's distance (at the reference size: G.ZoomScale): none
    ns.settings.gps.zoom = (G.InteriorZoomYd() + 50) * G.ZoomScale()
    G.Update()
    mouse(-9466.0, 16.0)
    assert G.zoomedInside is None



def test_a_whole_citys_map_has_no_npc_dots_a_buildings_has():
    """Asked 2026-11-14, Undercity's map covered in NPC icons: "for cities that whole city is inside, don't show inside
    vendors/NPCs ... too cluttered". Undercity's level and Ironforge's model: none; Brill's tavern and Orgrimmar's
    buildings (their maps alone): their NPCs."""
    lua, ns = _seamless()
    G = ns.GPS

    def dots(place, wmo, room, cont, x, y):
        pois = lua.eval("{}")
        G.AddInteriorNpcs(pois, place, wmo, room, cont, x, y, 0, 1.0, 1e6)
        return len(pois)

    x, y = 2269.5, 244.9  # (Innkeeper Renee, Brill's tavern)
    place, wmo, room = G.ZoomedInterior(x, y, 0)
    assert dots(place, wmo, room, 0, x, y) > 0 and not G.WholeCityPlace(place, 0)
    assert G.WholeCityPlace(None, 10001)  # (Undercity's level)
    ironforge = next(p for p in ns.Interiors[0].values() if p[1] == 7801267)
    assert G.WholeCityPlace(ironforge, 0)
    assert dots(ironforge, ns.WMOs[7801267], room, 0, ironforge[2], ironforge[3]) == 0
    org = next(p for p in ns.Interiors[1].values() if p[1] == 7964229)
    assert not G.WholeCityPlace(org, 1)


def test_orgrimmars_bank_draws_only_its_own_rooms_art():
    """Asked 2026-11-14, a screenshot: hovering Orgrimmar's bank drew a box of the Valley of Strength's art askew over
    the land. The bank's room (39 by 40 yd) lists six blocks, five starting 64 to 128 yd past its box: not its art."""
    import math
    lua, ns = _seamless()
    G = ns.GPS
    bank = (1624.7, -4376.3)
    place = next(p for p in ns.Interiors[1].values()
                 if p[1] == 7964229 and p[6] <= bank[0] <= p[8] and p[7] <= bank[1] <= p[9])
    w = ns.WMOs[place[1]]
    c, s = math.cos(place[5]), math.sin(place[5])
    dx, dy = bank[0] - place[2], bank[1] - place[3]
    lx, ly = dx * c + dy * s, -dx * s + dy * c
    room = next(g for g in w.groups.values() if g["in"] and g[1] <= lx <= g[4] and g[2] <= ly <= g[5]
                and max(g[4] - g[1], g[5] - g[2]) <= G.ZOOM_ROOM_MAX_YD)
    assert len(room.blocks) == 6
    q = G.LayoutInterior(bank[0], bank[1], place, w, room, 0, 100.0, 100.0)  # (1 px a yard)
    assert len(q) >= 1
    for i in range(1, len(q) + 1):
        assert abs(q[i][2]) < 100 and abs(q[i][3]) < 100, (q[i][1], q[i][2], q[i][3])


def test_hovering_a_building_works_after_dragging_the_map_again_and_again():
    """Asked 2026-11-14: "why is the building view still not working on buildings not near me?": the second drag of the
    map (from a view already dragged) kept the land view, `free.land`, a city map's way out, and no building hovered
    showed till the map followed again."""
    lua, ns = _seamless()
    G = ns.GPS
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = -9200.0, -100.0, 0, 82.0 "
                "IsIndoors = function() return false end AGPS_T = (AGPS_T or 0) + 1000")
    ns.settings.gps.zoom = 80.0
    G.Follow()
    G.Update()
    frame = lua.globals().AzerothGPSFrame

    def drag(dx, dy):
        lua.execute("AGPS_CX, AGPS_CY = 300, 300 AGPS_OLDC = GetCursorPosition "
                    "GetCursorPosition = function() return AGPS_CX, AGPS_CY end")
        try:
            frame._scripts.OnMouseDown(frame, "LeftButton")
            lua.execute(f"AGPS_CX, AGPS_CY = {300 + dx}, {300 + dy} AGPS_T = AGPS_T + 0.1")
            frame._scripts.OnUpdate(frame, 0.1)
            frame._scripts.OnMouseUp(frame, "LeftButton")
        finally:
            lua.execute("GetCursorPosition = AGPS_OLDC")
        G.Update()

    def mouse(x, y):
        lua.execute(f"AGPS_NS.GPS.CursorWorld = function() return {x}, {y}, 0 end AGPS_T = AGPS_T + 1")
        G.BuildingHover()
        G.Update()

    for _ in range(3):
        drag(-100, -50)
        mouse(-9466.0, 16.0)  # (over the Lion's Pride Inn, the player 400 yd off)
        assert G.zoomedInside is not None
        mouse(-9300.0, -100.0)
        assert G.zoomedInside is None


def test_hovering_a_building_is_openmap_only():
    """Asked 2026-11-15: "for the building mouse over, this should only work in OpenMap mode": the Terrain style, none."""
    lua, ns = _seamless(on=False)
    G = ns.GPS
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = -9400.0, 60.0, 0, 60.0 "
                "IsIndoors = function() return false end AGPS_T = (AGPS_T or 0) + 1000")
    ns.settings.gps.zoom = 80.0
    G.Follow()
    G.Update()
    lua.execute("AGPS_NS.GPS.CursorWorld = function() return -9466.0, 16.0, 0 end AGPS_T = AGPS_T + 1")
    G.BuildingHover()
    G.Update()
    assert G.hoverInside is None and G.zoomedInside is None


def test_hovering_a_building_works_on_a_big_map_as_on_a_small_one():
    """Asked 2026-11-14: "mouse over viewing for both gps map and in game map": the game's world map window is a big
    map, whose least zoom is past 150 yd; the slider's yards are at the reference size, as the OpenMap stages'."""
    lua, ns = _seamless()
    G = ns.GPS
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = -9400.0, 60.0, 0, 60.0 "
                "IsIndoors = function() return false end AGPS_T = (AGPS_T or 0) + 1000")
    lua.execute("AGPS_NS.GPS.ZoomScale = function() return 3 end")  # (a map three times the reference size)
    ns.settings.gps.zoom = 3 * 80.0
    G.Follow()
    G.Update()
    lua.execute("AGPS_NS.GPS.CursorWorld = function() return -9466.0, 16.0, 0 end AGPS_T = AGPS_T + 1")
    G.BuildingHover()
    G.Update()
    assert G.zoomedInside is not None


def test_stormwinds_buildings_have_their_inside_maps_its_streets_the_terrain():
    """Asked 2026-11-14: "I can't view inside buildings for stormwind": its one model was never an inside map
    (G.NO_INSIDE_MAP); an open city since, as Orgrimmar: a building hovered, its room; a street, nothing."""
    lua, ns = _seamless()
    G = ns.GPS
    place, _, room = G.InteriorUnder(-8867.0, 673.0, 0)  # (the Trade District, by the Gilded Rose)
    assert place is not None and place[1] == 7962574 and max(room[4] - room[1], room[5] - room[2]) <= G.ZOOM_ROOM_MAX_YD
    assert G.InteriorUnder(-8830.0, 625.0, 0)[0] is None  # (a street)
    # (standing in a street, not indoors: the terrain)
    assert G.FindInterior(-8830.0, 625.0, 95.0, 0, "Trade District", False)[0] is None


def test_a_caves_map_over_the_terrain_has_no_world_map_under_it():
    """Asked 2026-11-15, Gol'Bolar Quarry Mine on its world map's parchment: "any cave doing this should be changed to
    do the black outline trick": over the terrain, the art alone with its outline; the Terrain style keeps its map."""
    for on in (False, True):
        lua, ns = _seamless(on=on)
        G = ns.GPS
        lua.execute("""AGPS_C = nil
          for _, c in ipairs(AGPS_NS.Caves[0]) do
            local art = AGPS_NS.GPS.CaveArt(0, c[2])
            if art and AGPS_NS.GPS.InteriorMapFor(art.cont, art.list, nil, (art.x0 + art.x1) / 2, (art.y0 + art.y1) / 2) then
              AGPS_C = c[2] break
            end
          end""")
        key = lua.eval("AGPS_C")
        assert key
        assert G.ShowCave(0, key)
        G.Update()
        view = G.shownView
        assert view.cave
        if on:
            assert view.interiorMap is None and view.interiorTerrain
        else:
            assert view.interiorMap is not None


def test_a_cave_hovered_shows_its_map_as_a_building():
    """Asked 2026-11-14: "all caves should show with mouse over too just like buildings": a cave with art under the
    mouse, zoomed in, its map (G.CaveAt, G.CaveArt); off it, the land again; a click holds it."""
    lua, ns = _seamless()
    G = ns.GPS
    lua.execute("""AGPS_C = nil
      for _, c in ipairs(AGPS_NS.Caves[0]) do
        if AGPS_NS.GPS.CaveArt(0, c[2]) then AGPS_C = c break end
      end""")
    c = lua.eval("AGPS_C")
    key = c[2]
    art = G.CaveArt(0, key)
    spot = None
    for i in range(41):
        for j in range(41):
            x = art.x0 + (art.x1 - art.x0) * i / 40
            y = art.y0 + (art.y1 - art.y0) * j / 40
            if G.CaveAt(0, x, y) == key:
                spot = (x, y)
                break
        if spot:
            break
    assert spot
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = {art.x0 - 300}, {art.y0 - 300}, 0, 0 "
                "IsIndoors = function() return false end AGPS_T = (AGPS_T or 0) + 1000")
    ns.settings.gps.zoom = 80.0
    G.Follow()
    G.Update()

    def mouse(x, y):
        lua.execute(f"AGPS_NS.GPS.CursorWorld = function() return {x}, {y}, 0 end AGPS_T = AGPS_T + 1")
        G.BuildingHover()
        G.Update()

    mouse(*spot)
    assert G.shownView.cave is not None and G.hoveredCave == key
    for _ in range(4):  # (the mouse still: it stays, not gone every other check; a video 2026-11-14)
        mouse(*spot)
        assert G.shownView.cave is not None and G.hoveredCave == key
    mouse(art.x0 - 300, art.y0 - 300)
    assert G.shownView.cave is None
    mouse(*spot)
    assert G.HoldInside()
    mouse(art.x0 - 300, art.y0 - 300)
    assert G.shownView.cave is not None  # (held)


def test_a_held_inside_map_is_let_go_panned_or_zoomed_away():
    """Asked 2026-11-15: the 30 s hold closes early, as an opened cave's map, once the view is panned
    LEAVE_INSIDE_PAN_YD from it or zoomed out past the inside maps' distance."""
    lua, ns = _seamless()
    G = ns.GPS
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = -9400.0, 60.0, 0, 60.0 "
                "IsIndoors = function() return false end AGPS_T = (AGPS_T or 0) + 1000")
    st = ns.settings.gps
    st.zoom = 80.0
    G.Follow()
    G.Update()

    def hold():
        lua.execute("AGPS_NS.GPS.CursorWorld = function() return -9466.0, 16.0, 0 end AGPS_T = AGPS_T + 1")
        G.BuildingHover()
        G.Update()
        assert G.HoldInside()
        lua.execute("AGPS_NS.GPS.CursorWorld = function() return -9400.0, 300.0, 0 end AGPS_T = AGPS_T + 1")
        G.BuildingHover()
        G.Update()
        assert G.heldInside is not None and G.zoomedInside is not None

    hold()
    G.LookAt(0, -9400.0 + 150, 60.0, 80.0)  # (near where it was held: kept)
    G.Update()
    assert G.heldInside is not None
    G.LookAt(0, -9400.0 + G.LEAVE_INSIDE_PAN_YD + 50, 60.0, 80.0)  # (panned away: let go)
    G.Update()
    assert G.heldInside is None
    G.LookAt(0, -9440.0, 40.0, 80.0)
    G.Update()
    assert G.zoomedInside is None  # (back over it: not held again)
    G.Follow()
    G.Update()
    hold()
    st.zoom = (G.InteriorZoomYd() + 50) * G.ZoomScale()  # (zoomed out: let go)
    G.Update()
    st.zoom = 80.0
    G.Update()
    assert G.heldInside is None


def test_a_held_inside_map_stays_with_another_building_hovered():
    """Asked 2026-11-14: "left click hold interior view works until I mouse over another building's interior then it
    goes away until no longer viewing its interior": the held one stays drawn with the hovered one, both."""
    lua, ns = _seamless()
    G = ns.GPS
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = -9400.0, 60.0, 0, 60.0 "
                "IsIndoors = function() return false end AGPS_T = (AGPS_T or 0) + 1000")
    ns.settings.gps.zoom = 80.0
    G.Follow()
    G.Update()

    def mouse(x, y):
        lua.execute(f"AGPS_NS.GPS.CursorWorld = function() return {x}, {y}, 0 end AGPS_T = AGPS_T + 1")
        G.BuildingHover()
        G.Update()

    inn = (-9466.0, 16.0)  # (the Lion's Pride Inn)
    a = G.InteriorUnder(inn[0], inn[1], 0)[0]
    other = next((p[2], p[3]) for p in ns.Interiors[0].values()
                 if abs(p[2] - inn[0]) < 300 and abs(p[3] - inn[1]) < 300
                 and G.InteriorUnder(p[2], p[3], 0)[0] is not None and G.InteriorUnder(p[2], p[3], 0)[0][1] != a[1])
    mouse(*inn)
    assert G.HoldInside()
    mouse(*other)
    assert G.zoomedInside != a[1] and G.alsoInside is not None and G.alsoInside[1][1] == a[1]
    mouse(-9400.0, 300.0)  # (off both: the held one alone)
    assert G.zoomedInside == a[1] and G.alsoInside is None


def test_hovering_works_standing_in_a_building_a_click_holds_and_another_shows_over_the_held():
    """Asked 2026-11-14: "when I pan away from my current position I can no longer mouse over buildings" (standing in
    a building, its own inside map came first); "left click just flashes the map and doesn't hold it open" (the
    click's mouse-down cleared the hover); "even when its held open I still want to be able to mouse over other
    buildings and left click those"."""
    lua, ns = _seamless()
    G = ns.GPS
    lua.execute(GOLDSHIRE_INN + " AGPS_T = (AGPS_T or 0) + 1000")  # (standing in the inn)
    ns.settings.gps.zoom = 80.0
    G.Follow()
    G.Update()
    inn = G.shownInside
    assert inn is not None
    other = None
    for p in ns.Interiors[0].values():
        if p[1] != inn and abs(p[2] - -9466.0) < 400 and abs(p[3] - 16.0) < 400:
            place = G.InteriorUnder(p[2], p[3], 0)[0]
            if place is not None and place[1] != inn:
                other = (p[2], p[3])
                break
    assert other, "no other building near Goldshire's inn"
    def mouse(x, y):
        lua.execute(f"AGPS_NS.GPS.CursorWorld = function() return {x}, {y}, 0 end AGPS_T = AGPS_T + 1")
        G.BuildingHover()
        G.Update()
    mouse(*other)
    assert G.zoomedInside is not None and G.zoomedInside != inn  # (the hovered one over the player's own)
    # a click: the mouse-down is a drag till it's up; the hover stays, and the click holds it
    frame = lua.globals().AzerothGPSFrame
    lua.execute("GetCursorPosition = function() return 300, 300 end")
    frame._scripts.OnMouseDown(frame, "LeftButton")
    G.BuildingHover()
    assert G.hoverInside is not None
    frame._scripts.OnMouseUp(frame, "LeftButton")
    assert G.heldInside is not None
    held = G.zoomedInside
    # the mouse off every building: the held one; over another: that one shows
    mouse(-9400.0, 400.0)
    assert G.zoomedInside == held
    mouse(-9466.0, 16.0)  # (the player's own: its map, as standing in it)
    assert G.shownInside == inn


def test_in_a_building_zoomed_out_past_the_tiles_the_map_is_the_lands_art():
    # (2026-11-15, a video: opened in Tarren Mill's barn at 9,135 yd the map was the barn's inside map over terrain
    # tiles laid out that far, a continent of tiles on black, the art off, until a wheel turn; "it only happens inside a
    # building". Past the tiles' zoom the building's inside map gives way to the land's art; zoomed in, as before)
    lua, ns = _seamless(on=True)
    G, st = ns.GPS, ns.settings.gps
    lua.execute("AGPS_MAP = 1424; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = -8, -938, 0; IsIndoors = function() return true end")
    try:
        for z, inside in ((150.0, True), (9135.0, False)):
            st.zoom = z
            G.Follow()
            for _ in range(3):
                lua.execute("AGPS_T = (AGPS_T or 1000) + 0.5")
                G.Update()
            r = G.SeamReading()
            assert (G.shownInside is not None) == inside, z
            if not inside:
                assert r.art == 1 and r.tiles == 0, (r.art, r.tiles)
                assert not str(G.laidTiles.laidSig).startswith("in:")
    finally:
        lua.execute("IsIndoors = function() return false end")


def test_with_the_controller_the_crosshair_hovers_buildings():
    """Asked 2026-11-16: "In controller mode, when panning the map consider the crosshair as a mouse over for viewing
    inside buildings/caves/etc": the controller in use (its marks shown), the view's middle is the spot looked under,
    the mouse elsewhere; not in use, the mouse."""
    lua, ns = _seamless()
    G = ns.GPS
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = -9400.0, 60.0, 0, 60.0 "
                "IsIndoors = function() return false end AGPS_T = (AGPS_T or 0) + 1000 "
                "AGPS_NS.GPS.CursorWorld = function() return nil end")
    ns.settings.gps.zoom = 80.0
    G.Follow()
    G.Update()
    try:
        G.LookAt(0, -9466.0, 16.0, 80.0)  # (panned over the Lion's Pride Inn)
        G.Update()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.BuildingHover()
        G.Update()
        assert G.zoomedInside is None  # (no controller: the mouse, off the map)
        ns.Pad.marksOn = True
        lua.execute("AGPS_T = AGPS_T + 1")
        G.BuildingHover()
        G.Update()
        assert G.zoomedInside is not None
    finally:
        ns.Pad.marksOn = False


def test_walking_down_in_undercity_the_minimap_square_glides():
    """A video 2026-11-16, "minimap stutters a lot in UC": down in Undercity, mounted, the minimap square only moved at
    each redraw (its inside map, "in:", wasn't among the layers that slide with the player between redraws), 8-10
    times a second. Now it slides every frame and a redraw for the move alone waits for G.GLIDE_HZ, as on the land."""
    from test_world_map_host import SETUP
    lua, ns = _seamless()
    G, st = ns.GPS, ns.settings.gps
    lua.execute(SETUP)
    st.shown, st.minimized = True, None
    st.useWorldMap = True
    st.replaceMinimap = True
    G.ApplySettings()
    lua.execute("GetSubZoneText = function() return 'Trade Quarter' end")
    _down_in_undercity(lua, ns)
    st.hz = 20
    frame = lua.globals().AzerothGPSFrame
    fps, secs = 60, 3

    def redraws():
        p = ns.perf["redraw"]
        return p.n if p else 0
    n0, glided = redraws(), 0
    for _ in range(fps * secs):
        lua.execute(f"AGPS_POS[1] = AGPS_POS[1] + {14 / fps} AGPS_T = AGPS_T + {1 / fps}")
        frame._scripts.OnUpdate(frame, 1 / fps)
        glided += 1 if G.glided else 0
    assert G.inside is not None and str(G.laidTiles.laidSig).startswith("in:")
    assert glided >= fps * secs - 2, glided  # (slid every frame)
    assert (redraws() - n0) / secs <= G.GLIDE_HZ + 1, (redraws() - n0) / secs


def test_in_ironforge_its_map_holds_twice_as_far_out():
    """Asked 2026-11-16: "when in ironforge, make the zoom out distance required to not show ironforge map twice the
    distance". The game's map for the player Ironforge's: its map up to twice CITY_MAX_ZOOM's usual, the land past
    it; other cities as before."""
    lua, ns = _seamless()
    G, st = ns.GPS, ns.settings.gps
    lua.execute("AGPS_MAP = 1455 " + CITIES[0][0] + " AGPS_T = (AGPS_T or 0) + 1000")
    try:
        st.zoom = 4000.0
        G.Follow()
        G.Update()
        base = G.CITY_MAX_ZOOM_BASE
        assert G.CITY_MAX_ZOOM == 2 * base and G.inside is not None and st.zoom == 2 * base
        _wheel(lua, G, 0.5)  # (in)
        _wheel(lua, G, 1.5)  # (out past the usual limit: still the city's map)
        assert base < st.zoom <= 2 * base and G.inside is not None, st.zoom
        _wheel(lua, G, 1.25, 3)  # (out past twice: the land)
        assert st.zoom > 2 * base and G.inside is None
    finally:
        lua.execute("AGPS_MAP = nil")
        G.Update()
    assert G.CITY_MAX_ZOOM == G.CITY_MAX_ZOOM_BASE
