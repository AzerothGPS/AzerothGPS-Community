"""A flight master's stop is its NPC's, and never "Arrived" far under it (Kooki3z, 2026-11-23: "Thunderbluff flight
master says arrived 45yd under it"). Its map icon (the taxi node, POI kind 1, 3.6 yd off Tal) made a stop with no NPC
and no height, so no floor rule applied and the plain 10 yd circle arrived at the tower's foot, 50 yd under him."""

import pytest

TAL = 2995
TAL_XYZ = (-1196.8, 26.1, 177.0)
ARRIVED = "Arrived"


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    return lua, ns


@pytest.fixture()
def clean(game):
    lua, ns = game
    ns.Nav.ResetTrack()
    lua.execute("AGPS_OLD_INDOORS = IsIndoors")
    yield lua, ns
    lua.execute("IsIndoors = AGPS_OLD_INDOORS AGPS_GUIDS = nil")
    ns.Nav.Clear()
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
    ns.GPS.Follow()


def _at(lua, x, y, cont):
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {x}, {y}, {cont}")


def test_thunder_bluffs_flight_master_icon_makes_tals_stop_with_his_height(clean):
    lua, ns = clean
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    x, y, z = TAL_XYZ
    ns.CharDB().faction = "Horde"
    _at(lua, x + 60, y, 1)
    zoom = st.zoom
    try:
        st.zoom = 150.0
        G.Follow()
        lua.execute("AGPS_T = (AGPS_T or 0) + 6")
        G.Redraw()
        G.Update()
        icons = [w for w in lua.eval("AGPS_WIDGETS").values()
                 if w._shown and w.kind == 1 and w.wx and abs(w.wx - x) < 10 and abs(w.wy - y) < 10]
        assert icons, "no flight master icon at Thunder Bluff"
        N.Clear()
        icons[0]._scripts.OnDoubleClick(icons[0])
        G.ConfirmPendingOnClose()
    finally:
        st.zoom = zoom
    d = N.dest
    assert d.npcId == TAL and str(d.npcName) == "Tal" and d.z == pytest.approx(z)


def test_45_yards_under_tal_is_not_arrived_on_his_tower_it_is(clean):
    lua, ns = clean
    N = ns.Nav
    x, y, z = TAL_XYZ
    N.SetStops(lua.eval(f"{{ {{ x = {x + 3.6 * 0.1}, y = {y + 3.6}, cont = 1, z = {z}, name = 'Thunder Bluff, Mulgore', "
                        f"npcId = {TAL}, npcName = 'Tal' }} }}"), False, "red")
    lua.execute("AGPS_T = 900 IsIndoors = function() return true end")
    px, py = x + 6, y + 2
    _at(lua, px, py, 1)
    N.AnchorFloor(1, px, py, 128.0)  # (the ground's floor under the tower followed)
    assert N.FollowedZ(1) == pytest.approx(128.0, abs=1)
    assert ARRIVED not in (N.Status(px, py, 1) or "") and N.dest is not None
    N.AnchorFloor(1, x + 1, y, 176.0)  # (up on the tower)
    assert ARRIVED in (N.Status(x + 1, y, 1) or "")


def test_a_stop_on_a_mesa_top_is_not_arrived_from_the_ground_under_its_cliff(clean):
    # (out of the capitals, no road to tell the floor by: the stop on a mesa's top (its ground's height its own), the
    # player at the cliff's foot 7 yd off, 45 yd lower: the ground under the player tells)
    lua, ns = clean
    N = ns.Nav
    x, y = -1800.0, 1600.0  # (Mulgore's open ground, north of Thunder Bluff's mesas)
    assert not N.InCapital(1, x, y)
    lua.execute(f"""AGPS_OLD_GROUND = AGPS_NS.Nav.GroundAt
      AGPS_NS.Nav.GroundAt = function(c, gx, gy) if gx < {x} + 4 then return 200 end return 155 end""")
    try:
        N.SetStops(lua.eval(f"{{ {{ x = {x}, y = {y}, cont = 1, z = 200.5, name = 'Mesa top' }} }}"), False, "red")
        assert N.StopOffGround(N.dest)[0] is None  # (on its own ground)
        _at(lua, x + 7, y, 1)
        assert ARRIVED not in (N.Status(x + 7, y, 1) or "") and N.dest is not None
        assert ARRIVED in (N.Status(x + 2, y, 1) or "")  # (up on the top by it)
        # (a stop down on the ground by the cliff: arrived from there as before)
        N.SetStops(lua.eval(f"{{ {{ x = {x + 3}, y = {y}, cont = 1, z = 156, name = 'Foot' }} }}"), False, "red")
        assert ARRIVED in (N.Status(x + 9, y, 1) or "")
    finally:
        lua.execute("AGPS_NS.Nav.GroundAt = AGPS_OLD_GROUND")
