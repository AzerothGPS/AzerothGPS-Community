"""Edit Wall's cliff sides and the walls it picks (Kooki3z 2026-11-20, his video of cliff walls in Stonetalon).

1. The sides filled in: the map's ground grid is ~16.7 yd a cell and bilinear, so right by a ledge both sides read
   nearly the same (Left 70.0, Right 69.7 at a ledge whose top is ~70-75 and its foot ~22-25): a level, open cliff
   that blocked nothing. Record.WallSides reads the ground out along the perpendicular on each side and takes the high
   side's top and the low side's foot.
2. A wall deleted with an erase was gone from the map and the routes but still picked by a click (Record.WallAt), so
   the wall shown next to it could never be picked and deleted. What Edit Wall picks is what the map draws
   (Passability.WallLines), and Delete takes out the one clicked.
"""

import pytest

from test_addon_lua import env, load  # noqa: F401 (fixtures)

pytest.importorskip("lupa")


# ---- 1. the sides filled in ------------------------------------------------------------------------------------------

def stub_ground(lua, ns, top, foot, x0, x1):
    """Ground that is `top` west of x0, `foot` east of x1 and a straight slope between (a ledge smoothed over the
    grid's cells), a bump on the way down as the real ground has."""
    ns.Ground = lua.eval("""function(top, foot, x0, x1)
      return { At = function(cont, x, y)
        if x <= x0 then return top end
        if x >= x1 then return foot end
        local h = top + (foot - top) * (x - x0) / (x1 - x0)
        if math.abs(x - (x0 + x1) / 2) < 3 then h = h + 3 end -- (a bump, less than CLIFF_SIDE_TURN)
        return h
      end }
    end""")(top, foot, x0, x1)


@pytest.fixture
def record(env):
    lua, ns = env
    load(lua, ns, "Record.lua")
    yield lua, ns


def test_the_sides_are_the_ledges_top_and_its_foot_not_its_smoothed_edge(record):
    lua, ns = record
    Rec = ns.Record
    # a ledge from 74 (x <= 800) down to 22 (x >= 860): a wall drawn along its edge at x = 820, north to south (its
    # left is east, the foot; its right west, the top)
    stub_ground(lua, ns, 74, 22, 800, 860)
    wall = lua.eval("{ pts = { 820, 450, 820, 400, 820, 350 } }")
    zl, zr = Rec.WallSides(1, wall, 1, 3)
    assert zr == pytest.approx(74, abs=0.5) and zl == pytest.approx(22, abs=1.5), (zl, zr)
    # the old fill, the ground 5 yd off each side: nearly level (an open cliff)
    near = [ns.Ground.At(1, 825, 400), ns.Ground.At(1, 815, 400)]
    assert abs(near[0] - near[1]) < 10
    # drawn the other way round: the sides swap
    back = lua.eval("{ pts = { 820, 350, 820, 400, 820, 450 } }")
    assert Rec.WallSides(1, back, 1, 3) == (zr, zl)


def test_the_sides_stop_at_the_next_valley_and_level_ground_stays_level(record):
    lua, ns = record
    Rec = ns.Record
    # a narrow ridge: the top 60 at the wall's west, the ground down to 30 by x = 790 and up again to 80 past 770
    ns.Ground = lua.eval("""{ At = function(cont, x, y)
      if x >= 820 then return 20 end
      if x >= 810 then return 60 end
      if x >= 790 then return 60 - (810 - x) * 1.5 end
      if x >= 775 then return 30 end
      return 80
    end }""")
    wall = lua.eval("{ pts = { 815, 450, 815, 350 } }")  # (north to south: left east, right west)
    zl, zr = Rec.WallSides(1, wall, 1, 2)
    assert zl == 20 and zr == 60, (zl, zr)  # (the ridge's top, not the mountain past the valley)
    ns.Ground = lua.eval("{ At = function(cont, x, y) return 50 + (x % 7) * 0.1 end }")
    zl, zr = Rec.WallSides(1, wall, 1, 2)
    assert abs(zl - zr) <= 1  # (level: an open cliff, as before)
    ns.Ground = lua.eval("{ At = function() return nil end }")
    assert Rec.WallSides(1, wall, 1, 2) == (None, None)


def test_the_stonetalon_ledge_fills_its_top_and_foot_from_the_shipped_ground(record):
    """The ledge in Kooki3z's video, near (825, 390) on Kalimdor: the top ~73 on the road's (west) side, the foot
    ~22-26 down to the east; the old fill read ~70 both sides."""
    lua, ns = record
    from pathlib import Path
    addon = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS"
    lua.eval("function(src, ns) assert(load(src, '@Ground.lua'))('AzerothGPS', ns) end")(
        (addon / "Ground.lua").read_text(encoding="utf-8"), ns)
    lua.eval("function(src, ns) assert(load(src, '@Heights.lua'))('AzerothGPS', ns) end")(
        (addon / "Data" / "Heights.lua").read_text(encoding="utf-8"), ns)
    ns.Ground.force = True
    GD = ns.Ground
    if GD.At(1, 810.5, 404.7) is None:
        pytest.skip("no ground data there")
    assert GD.At(1, 810.5, 404.7) > 70 and GD.At(1, 870.4, 348.1) < 30
    # the edge runs south-west to north-east there: drawn that way, its left is the top (north-west), its right the foot
    wall = lua.eval("{ pts = { 811, 375, 825, 390, 839, 405 } }")
    zl, zr = ns.Record.WallSides(1, wall, 1, 3)
    assert zl >= 70 and 20 <= zr <= 30, (zl, zr)
    # the old fill there: both sides alike (within a few yards)
    old = ns.Record.CLIFF_SIDE_YD
    a, b = GD.At(1, 825 - 0.73 * old, 390 + 0.69 * old), GD.At(1, 825 + 0.73 * old, 390 - 0.69 * old)
    assert abs(a - b) < 15


# ---- 2. the walls picked and deleted ---------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    lua.execute("AGPS_T = AGPS_T + 1")
    ns.GPS.Update()
    return lua, ns


@pytest.fixture()
def walls(game):
    lua, ns = game
    G = ns.GPS
    saved, shipped = ns.db.tracks, ns.RoadTracksIn
    ns.db.tracks = lua.table()
    ns.Router.Reset()
    ns.Passability.RefreshWalls()
    lua.execute("AGPS_TIME_REAL = time; AGPS_NOW = 1795230000; time = function() AGPS_NOW = AGPS_NOW + 7 "
                "return AGPS_NOW end")
    try:
        G.SetWallMode(True)
        yield lua, ns
    finally:
        f = lua.globals()["AzerothGPSWallEdit"]
        if f:
            f.Hide(f)
        if G.askBox:
            G.askBox.Hide(G.askBox)
        G.SetEditWallMode(False)
        G.SetWallMode(False)
        lua.execute("time = AGPS_TIME_REAL")
        ns.db.tracks, ns.RoadTracksIn = saved, shipped
        ns.Router.Reset()
        ns.Passability.RefreshWalls()


def draw(lua, ns, pts):
    ns.GPS.FinishRoad(lua.table(pts=lua.table(*pts), cont=0), False, True)
    return ns.db.tracks[len(ns.db.tracks)]


def own_lines(ns):
    return [(w[1], w[2]) for w in ns.Passability.WallLines(0).values() if w.own]


def ops(ns):
    return [t.op for t in ns.db.tracks.values()]


def test_an_erased_wall_is_never_picked_and_the_one_shown_is_deleted(walls):
    """His pattern: two cliff walls along the same ledge, one (B) taken out with an erase near its far end, the other
    (A, an open cliff: its sides filled in level) shown faint right by it. A click there picked B, the erased one,
    every time, so A could never be deleted."""
    lua, ns = walls
    G, P, Rec = ns.GPS, ns.Passability, ns.Record
    a = draw(lua, ns, [2600.0, 760.0, 2615.0, 760.0, 2630.0, 760.0, 2645.0, 760.0, 2660.0, 760.0])
    assert Rec.EditWall(Rec.WallAt(0, 2630.0, 759.0), lua.table(kind="cliff", i=1, j=5, zl=70, zr=69.7))
    b = draw(lua, ns, [2590.0 + 10 * k if i == 0 else 765.0 for k in range(12) for i in (0, 1)])
    assert Rec.EditWall(Rec.WallAt(0, 2690.0, 765.0), lua.table(kind="cliff", i=1, j=12, zl=75, zr=24))
    b_edit = ns.db.tracks[len(ns.db.tracks)]
    # B erased (Shift + right-drag) at its far end, 40 yd from A's
    ns.db.tracks[len(ns.db.tracks) + 1] = lua.table(op="unwall", drawn=True, continent=0, zone="?", time=1795239999,
                                                    pts=lua.table(2698.0, 765.0, 2700.0, 765.0))
    P.RefreshWalls()
    assert own_lines(ns) == [(2600.0, 760.0)]  # (only A drawn and routed)
    # a click by both, nearer B's line: A, the one shown
    sel = Rec.WallAt(0, 2630.0, 764.0)
    assert sel and sel.t.time != b_edit.time and sel.t.cl[1] == 70
    assert all(t.time != b_edit.time for t in Rec.EditableWalls(0).values())
    # Edit Wall's click and Delete: A goes, off the list with the wall it was drawn as (nothing to come back)
    G.SetEditWallMode(True)
    assert G.EditWallClick(0, 2630.0, 764.0)
    win = lua.globals().AzerothGPSWallEdit
    assert win._shown and G.wallEdit.sel.t.cl[1] == 70
    win.delete._scripts.OnClick(win.delete)
    G.askBox.yes._scripts.OnClick(G.askBox.yes)
    assert own_lines(ns) == [] and Rec.WallAt(0, 2630.0, 764.0) is None
    assert ops(ns) == ["wall", "wall", "unwall"] and a not in list(ns.db.tracks.values())
    assert P.WallHit(0, 2630.0, 750.0, 2630.0, 770.0) is None


def test_deleting_an_edit_of_the_maps_own_wall_leaves_nothing_to_pick(walls):
    """An edit whose wall the data has (or another wall depends on what it replaced): Delete erases it there, and the
    click afterwards picks nothing (it used to pick it again, though it was gone from the map and the routes)."""
    lua, ns = walls
    G, P, Rec = ns.GPS, ns.Passability, ns.Record
    w = draw(lua, ns, [2600.0, 760.0, 2615.0, 760.0, 2630.0, 760.0, 2645.0, 760.0, 2660.0, 760.0])
    assert Rec.EditWall(Rec.WallAt(0, 2630.0, 759.0), lua.table(kind="cliff", i=1, j=5, zl=75, zr=24))
    edit = ns.db.tracks[2]
    # the data has the wall first drawn now (the road watcher shipped it): the edit can't take it off the list
    ns.RoadTracksIn = lua.table()
    ns.RoadTracksIn[w.time] = True
    P.RefreshWalls()
    assert Rec.OwnWallChain(edit) is None
    sel = Rec.WallAt(0, 2630.0, 760.5)
    assert sel and sel.t.time == edit.time
    r = G.DeleteWallEdit(0, sel, 1, 5)
    assert isinstance(r, (int, float)) and ns.db.tracks[r].op == "unwall"
    P.RefreshWalls()
    assert own_lines(ns) == [] and Rec.WallAt(0, 2630.0, 760.5) is None


def test_a_section_deleted_then_a_piece_deleted_keeps_the_other_piece(walls):
    """Pieces of an edit both replace the wall it was drawn as: deleting one whole must not bring that wall back or
    take the other piece."""
    lua, ns = walls
    G, P, Rec = ns.GPS, ns.Passability, ns.Record
    draw(lua, ns, [2600.0, 760.0, 2615.0, 760.0, 2630.0, 760.0, 2645.0, 760.0, 2660.0, 760.0])
    assert Rec.EditWall(Rec.WallAt(0, 2630.0, 759.0), lua.table(kind="cliff", i=1, j=5, zl=75, zr=24))
    assert Rec.DeleteWall(0, Rec.WallAt(0, 2630.0, 759.0), 2, 4) == "own"  # (the middle out: two pieces)
    P.RefreshWalls()
    assert sorted(own_lines(ns)) == [(2600.0, 760.0), (2645.0, 760.0)]
    piece = Rec.WallAt(0, 2607.0, 760.0)
    assert piece and Rec.OwnWallChain(piece.t) is None
    G.DeleteWallEdit(0, piece, 1, 2)
    P.RefreshWalls()
    assert own_lines(ns) == [(2645.0, 760.0)]
    assert Rec.WallAt(0, 2607.0, 760.0) is None and Rec.WallAt(0, 2652.0, 760.0) is not None
