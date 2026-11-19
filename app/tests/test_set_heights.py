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


def test_a_stretchs_heights_are_spread_evenly_by_the_yards_along_and_the_rest_keeps_its_own(nav_env):
    lua, ns = nav_env
    from test_addon_lua import load
    load(lua, ns, "Record.lua")
    Rec = ns.Record
    # points 0, 10, 20, 50, 60 yd along; the stretch from point 2 to 4 (10 to 50 yd: 40 yd) from 5 up to 25
    pts = lua.table(0, 0, 10, 0, 20, 0, 50, 0, 60, 0)
    base = lua.table(1, 2, False, False, 9)
    hs = vals(Rec.EditHeights(pts, "ground", None, None, lua.table(2, 4, 5, 25), None, None, base))
    assert hs == pytest.approx([1, 5, 10, 25, 9])
    # with no heights of its own around it: the stretch's ends carried on
    hs = vals(Rec.EditHeights(pts, "ground", None, None, lua.table(2, 4, 5, 25), None, None))
    assert hs == pytest.approx([5, 5, 10, 25, 25])
    # down as well as up
    hs = vals(Rec.EditHeights(pts, "ground", None, None, lua.table(1, 5, 30, 0), None, None))
    assert hs == pytest.approx([30, 25, 20, 5, 0])
    # the base: the road's own heights, else the ground's it was drawn on
    t = lua.table(pts=pts, zs=lua.table(3, 3, 3, 3, 3))
    assert vals(Rec.StretchBase(t, 999)) == [3, 3, 3, 3, 3]
    t = lua.table(pts=pts, gz=lua.table(4, False, 6, 7, 8))
    assert vals(Rec.StretchBase(t, 999)) == [4, False, 6, 7, 8]


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


def test_set_heights_in_edit_road_makes_a_stretch_stairs_or_a_ramp_filled_from_the_ground(game):
    lua, ns = game
    G, R, Rec = ns.GPS, ns.Router, ns.Record
    saved = ns.db.tracks
    try:
        ns.db.tracks = lua.table()
        R.Reset()
        G.SetRoadMode(True)
        # Durotar, south of Orgrimmar: a road drawn there takes the ground's heights
        G.FinishRoad(lua.table(pts=lua.table(1300.0, -4450.0, 1280.0, -4450.0, 1260.0, -4450.0, 1240.0, -4450.0), cont=1),
                     False, False)
        first = ns.db.tracks[1]
        gz = vals(first.gz)
        assert all(isinstance(h, (int, float)) for h in gz)
        G.SetEditRoadMode(True)
        assert G.EditRoadClick(1, 1280.0, -4451.0)
        win = lua.globals().AzerothGPSRoadEdit
        click(win.pickFoot)
        assert G.EditRoadClick(1, 1281.0, -4450.0) and G.roadEdit.foot == 2
        click(win.pickTop)
        assert G.EditRoadClick(1, 1261.0, -4450.0) and G.roadEdit.top == 3
        click(win.setHeights)
        sh = lua.globals().AzerothGPSSetHeights
        assert sh._shown
        # filled in from the ground the road was drawn on
        assert float(sh.startBox.GetText(sh.startBox)) == pytest.approx(gz[1], abs=0.06)
        assert float(sh.endBox.GetText(sh.endBox)) == pytest.approx(gz[2], abs=0.06)
        # no height: not saved
        sh.endBox.SetText(sh.endBox, "")
        click(sh.save)
        assert len(ns.db.tracks) == 1 and sh._shown
        # typed over: a ramp from 20 to 32
        sh.startBox.SetText(sh.startBox, "20")
        sh.endBox.SetText(sh.endBox, "32")
        click([b for b in vals(sh.kinds) if b.kind == "ramp"][0])
        click(sh.save)
        assert not sh._shown and len(ns.db.tracks) == 2
        ed = ns.db.tracks[2]
        assert ed.replaces == first.time and vals(ed.stairs) == [2, 3] and ed.skind == "ramp"
        zs = vals(ed.zs)
        assert zs[1:3] == [20, 32] and zs[0] == pytest.approx(gz[0], abs=0.06) and zs[3] == pytest.approx(gz[3], abs=0.06)
        # its share line carries the heights
        assert " zs=" in ns.MapText.RoadLine(ed)
        # routes: the ramp a road of its own kind, with its heights
        Rec.Apply()
        R.NearestEdges(1, 1270.0, -4450.0)
        g = R.DebugGraph(1)
        ramp = [ei for ei in range(1, len(g.e) + 1) if g.kind and g.kind[ei] == "ramp"]
        assert ramp and all(g.e[ei][4] != R.SOURCE_STAIR for ei in ramp)
        assert {round(g.nz[g.e[ramp[0]][1]]), round(g.nz[g.e[ramp[0]][2]])} == {20, 32}
        # again, as stairs over the whole road (none picked), down
        Rec.Undo()
        assert G.EditRoadClick(1, 1280.0, -4451.0)
        click(win.setHeights)
        sh.startBox.SetText(sh.startBox, "30")
        sh.endBox.SetText(sh.endBox, "18")
        click([b for b in vals(sh.kinds) if b.kind == "stairs"][0])
        click(sh.save)
        st = ns.db.tracks[2]
        assert st.skind is None and vals(st.stairs) == [1, 4]
        assert vals(st.zs) == pytest.approx([30, 26, 22, 18])
        Rec.Apply()
        R.NearestEdges(1, 1270.0, -4450.0)
        g = R.DebugGraph(1)
        assert [ei for ei in range(1, len(g.e) + 1) if g.e[ei][4] == R.SOURCE_STAIR and abs(g.e[ei][6] + 4450) < 1]
    finally:
        ns.db.tracks = saved
        G.SetEditRoadMode(False)
        G.SetRoadMode(False)
        R.Reset()


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
