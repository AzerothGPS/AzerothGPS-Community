"""A dungeon's or raid's map over the terrain round it, and left by itself like a cave's (asked 2026-11-15: "change
dungeon/raid maps to use surrounding terrain too when applicable, just like viewing a cave, panning too far or zooming
out closes the view"; Shadowfang Keep's map was on the seamless world art with a black feathered ground round it)."""

import pytest

SFK = 20033  # (Shadowfang Keep: map 33, its way in in Silverpine Forest)


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    lua.execute("AGPS_REAL_SEAMLESS = AGPS_NS.GPS.Seamless; AGPS_NS.GPS.Seamless = function() return true end")
    return lua, ns


def _tick(lua, ns, n=3):
    for _ in range(n):
        lua.execute("AGPS_T = (AGPS_T or 1000) + 0.5")
        ns.GPS.Update()


def test_a_dungeons_map_is_over_the_terrain_round_its_way_in(game):
    lua, ns = game
    G = ns.GPS
    G.ShowInstance(SFK)
    _tick(lua, ns)
    lt = G.laidTiles
    assert str(lt.laidSig).startswith(f"inst:{SFK}:") and str(lt.laidSig).endswith(":terrain")
    quads = list(lt.quads.values())
    assert any(q.terrain for q in quads), "no terrain round it"
    assert any(q.outline for q in quads), "no thin black outline round its art"
    assert not G.DungeonMapShown()[0]  # (no world map's parchment under it, as a cave's)
    assert G.LaidKeptMoving(str(lt.laidSig))  # (kept while the view moves)
    # (laid where it lies on the continent: its way in's spot, G.InteriorArtSpot)
    sp = G.InteriorArtSpot(SFK, SFK)
    assert sp[1] == 0
    G.Follow()


def test_panned_well_away_from_a_dungeons_map_its_the_land_there(game):
    lua, ns = game
    G = ns.GPS
    G.ShowInstance(SFK)
    _tick(lua, ns, 1)
    x0, x1, y0, y1 = G.InstanceBounds(SFK)
    sp = G.InteriorArtSpot(SFK, SFK)
    v = G.SaveView()
    v.x, v.y = x1 + 600.0, (y0 + y1) / 2  # (dragged 600 yd past it, in its own yards)
    G.ApplyView(v)
    assert G.SaveView().instance == SFK
    _tick(lua, ns, 1)
    w = G.SaveView()
    assert not w.instance, "the dungeon's map stayed open panned 600 yd past it"
    assert w.cont == 0 and abs(w.x - (v.x + sp[2])) < 1 and abs(w.y - (v.y + sp[3])) < 1  # (the land there)
    G.Follow()


def test_zoomed_well_out_of_a_dungeons_map_it_doesnt_come_back(game):
    lua, ns = game
    G = ns.GPS
    G.ShowInstance(SFK)
    _tick(lua, ns, 1)
    limit = G.InstanceSeamZoom(SFK)
    for _ in range(40):
        G.WheelZoom(1.16)
        _tick(lua, ns, 1)
        if ns.settings.gps.zoom > limit * G.LEAVE_INSIDE_ZOOM_TIMES * 1.2:
            break
    assert not G.SaveView().instance
    for _ in range(60):  # (back in all the way: the land, not the dungeon's map again)
        G.WheelZoom(1 / 1.16)
        _tick(lua, ns, 1)
    assert not G.SaveView().instance, "zoomed well out of the dungeon's map and back in, its map came back"
    G.Follow()
