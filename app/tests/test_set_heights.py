"""Set Heights in Edit Road (1.3.10, issue #685, phase 2): a stretch of a drawn road gets a start and an end height
(filled in from the road's own or the map's ground, typed over), the points between spread evenly by the yards along,
made Stairs or a Ramp at once; the rest of the road keeps its heights; walking it says how far up or down it goes; the
import ships the stretch as its own piece with its kind and heights."""

import json

import pytest

from test_addon_lua import env, nav_env  # noqa: F401 (fixtures)

pytest.importorskip("lupa")


def vals(t):
    return [t[k] for k in range(1, len(t) + 1)]


def test_a_ramp_stretch_goes_on_as_a_ramp_piece_walked_as_a_road(nav_env):
    lua, ns = nav_env
    R = ns.Router
    assert "ramp" in vals(R.TRACK_KINDS)
    t = lua.table(op="add", continent=777, time=5, kind="ground", pts=lua.table(0, 0, 10, 0, 20, 0, 30, 0),
                  zs=lua.table(1, 1, 11, 11), stairs=lua.table(2, 3), skind="ramp")
    pieces = vals(R.TrackPieces(t))
    assert [p.kind for p in pieces] == ["ground", "ramp", "ground"]
    assert [bool(p.stair) for p in pieces] == [False, False, False]
    assert vals(pieces[1].zs) == [1, 11]
    t.skind = None
    assert [p.kind for p in vals(R.TrackPieces(t))] == ["ground", "stairs", "ground"]


def test_walking_a_climb_says_how_far_up_or_down_it_goes(nav_env):
    lua, ns = nav_env
    N = ns.Nav
    part = lua.table(pts=lua.table(0, 0, 5, 0, 10, 0, 20, 0, 30, 0), fz=lua.table(10, 12, 14, 18, 18))
    assert tuple(N.SlopeHint(part)) == ("up", 8)
    part.fz = lua.table(18, 14, 10, 10, 2)
    assert tuple(N.SlopeHint(part)) == ("down", 8)  # (levels off at 10: the climb ends there)
    part.fz = lua.table(10, 10, 14, 18, 18)
    assert N.SlopeHint(part) is None  # (not on it yet)
    part.fz = lua.table(10, 10.5, 11, 11, 11)
    assert N.SlopeHint(part) is None  # (less than SLOPE_MIN_YD)
    assert N.SlopeHint(lua.table(pts=lua.table(0, 0, 5, 0))) is None  # (no heights: the land)
    N.route = lua.table(parts=lua.table(lua.table(pts=lua.table(0, 0, 5, 0, 10, 0), fz=lua.table(0, 5, 12))))
    assert "12 yd up" in N.SlopeText()
    N.route = None


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    return lua, ns


def click(b):
    b.GetScript(b, "OnClick")(b)


def test_the_import_ships_a_ramp_stretch_as_its_own_piece(tmp_path):
    from azerothgps.roads.tracks import import_tracks, load_overrides

    wtf = tmp_path / "WTF" / "ACC" / "SavedVariables"
    wtf.mkdir(parents=True)
    (wtf / "AzerothGPS.lua").write_text(
        'AzerothGPSDB = { tracks = { { op = "add", drawn = true, edit = true, continent = 1, zone = "Durotar", '
        'time = 1700000100, kind = "ground", replaces = 1700000000, stairs = { 2, 3 }, skind = "ramp", '
        'pk = "1300 -4450 1280 -4450 1260 -4450 1240 -4450", zk = "15 20 32 14" } } }\n', encoding="utf-8")
    ov = tmp_path / "overrides"
    assert import_tracks(tmp_path / "WTF", ov) == 1
    feats = [f["properties"] for f in load_overrides(ov / "roads_1.geojson")["features"]]
    assert [f.get("kind") for f in feats] == ["ground", "ramp", "ground"]
    assert [bool(f.get("stair")) for f in feats] == [False, False, False]
    assert feats[1]["zs"] == [20, 32]
    json.dumps(feats)
