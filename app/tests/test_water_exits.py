"""Ways out of the water only where you can climb out (item 123, 1.4.1; Kooki3z 2026-11-26 in Booty Bay: "routing from
the water to a NPC tells me to get out of the water at places on the pier that isn't possible").

The world grid joins the water's surface to land only within its SHORE_Z (a step), and Booty Bay's one way up from the
water onto the lower deck is a plank: its foot in the water where Kooki3z stood (-14432.8, 459.2), its top on the deck
4 yd up. Four things took routes elsewhere:
- WG.Straighten cut the swim's corner from under the lower deck straight onto its edge 4.5 yd up (WG.Clear checked the
  line's height only on entering a cell): over the water a straight line keeps within WG.SWIM_CLEAR_Z of its top;
- standing on the plank's foot, not swimming, the start was the upper deck 15 yd over him (item 106's dry floor over
  the water): a surface under the water's top within WADE_STAND_Z, well over the sea's bottom, is stood on (DrySplit);
- swimming, a route along a deck overhead was still followed ("Make a U-turn onto the road"), and a walk from the water
  with a height began on the lower deck within FLOOR_Z: swimming, the water's surfaces are the start;
- "Above you, 26 yd up": the player's height was the sea's bottom, not the floor the grid followed.
"""

import math

import pytest

from test_map_redraw import game  # noqa: F401

KOOKI = (-14432.76, 459.16)  # (his spot: the plank's foot, in the water; server Z -0.27, the water's top 0)
PLANK_TOP = (-14434.5, 453.9)  # (the plank's top on the lower deck, z 4)
MACKINLEY = (-14447.4, 448.0, 15.8)  # ("Sea Wolf" MacKinley, the upper deck)
SKINDLE = (-14457.7, 495.3, 15.2)  # (Innkeeper Skindle)
GRINGER = (-14448.6, 506.1, 26.4)  # (Gringer, the wind rider master)
UNDER_DECK = (-14440.0, 440.0)  # (in the water under the lower deck, 4.5 yd over it)
BAY_SOUTH = (-14420.0, 400.0)
BAY_NORTH = (-14400.0, 500.0)
BAY_EAST = (-14360.0, 440.0)  # (the bay's east side: up its beach)


@pytest.fixture
def grids(game):  # noqa: F811
    lua, ns = game
    st, WG, R = ns.settings.gps, ns.WorldGrid, ns.Router
    was = (st.worldGrid, st.cityGrid, R.SYNC_WALKS)
    st.worldGrid = st.cityGrid = True
    WG.Set(True)
    R.SYNC_WALKS = True
    lua.execute("AGPS_WX = { swim = false }"
                " AGPS_WX_SAVED = { IsSwimming = rawget(_G, 'IsSwimming'), IsFalling = rawget(_G, 'IsFalling'),"
                "   IsIndoors = rawget(_G, 'IsIndoors') }"
                " IsSwimming = function() return AGPS_WX.swim end"
                " IsFalling = function() return false end IsIndoors = function() return false end")
    _fresh(lua, ns)
    yield lua, ns
    lua.execute("IsSwimming, IsFalling, IsIndoors = AGPS_WX_SAVED.IsSwimming, AGPS_WX_SAVED.IsFalling,"
                " AGPS_WX_SAVED.IsIndoors AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0")
    ns.Nav.Clear()
    _fresh(lua, ns)
    st.worldGrid, st.cityGrid, R.SYNC_WALKS = was
    WG.Set(bool(was[0]))


def _fresh(lua, ns):
    N = ns.Nav
    N.ResetGridTrack()
    N.ResetTrack()
    N.ResetCityTrack()
    lua.execute("AGPS_T = AGPS_T + 30")


def _swim(lua, on):
    lua.execute(f"AGPS_WX.swim = {'true' if on else 'false'}")


def _walk(lua, ns, cont, start, stop, swimming=True, sz=None):
    WG = ns.WorldGrid
    r = WG.Walk(WG.Cont(cont), start[0], start[1], sz, stop[0], stop[1], stop[2], lua.table(swimming=swimming))
    assert r and r != "pending", (start, stop)
    n = len(r.pts) // 2
    return [(r.pts[2 * i - 1], r.pts[2 * i], r.fz[i]) for i in range(1, n + 1)]


def _climbs_from_the_water(pts, top=0.0, ways_out=()):
    """The route's pieces from the water's surface (its height exactly: the grid's swim surfaces are its top) straight up
    more than a step (WG.SWIM_CLEAR_Z): none may be, but from the foot of a way up out of it (`ways_out`: Booty Bay's
    plank, a piece from its foot up it). A beach's or a ramp's land at the water's level and up it is land."""
    bad = []
    for (ax, ay, az), (bx, by, bz) in zip(pts, pts[1:]):
        if az is not None and bz is not None and abs(az - top) < 0.05 and bz > top + 1.5 + 0.5:
            if not any(math.hypot(ax - w[0], ay - w[1]) <= 3 for w in ways_out):
                bad.append(((round(ax, 1), round(ay, 1), az), (round(bx, 1), round(by, 1), bz)))
    return bad


def _near(pts, spot, yd):
    return min(math.hypot(x - spot[0], y - spot[1]) for x, y, _ in pts) <= yd


# --- the router's swims: out only up the plank --------------------------------------------------------------------

@pytest.mark.parametrize("start", [KOOKI, UNDER_DECK, BAY_SOUTH, BAY_NORTH], ids=["his_spot", "under_deck", "south", "north"])
@pytest.mark.parametrize("stop", [MACKINLEY, SKINDLE, GRINGER], ids=["mackinley", "innkeeper", "wind_rider"])
def test_a_swim_to_a_booty_bay_npc_climbs_out_up_the_plank(grids, start, stop):
    lua, ns = grids
    pts = _walk(lua, ns, 0, start, stop)
    assert not _climbs_from_the_water(pts, ways_out=[KOOKI]), pts
    # (out of the water at the plank's foot, Kooki3z's spot, then up it: never onto a deck's edge from under it)
    out = next(i for i, p in enumerate(pts) if p[2] is not None and p[2] > 0.6)
    assert any(math.hypot(p[0] - KOOKI[0], p[1] - KOOKI[1]) <= 3 for p in pts[max(0, out - 1):out + 1]), pts


def test_a_straight_line_never_climbs_from_the_water_onto_a_deck(grids):
    lua, ns = grids
    WG = ns.WorldGrid
    c = WG.Cont(0)
    # (the cut WG.Straighten took: from under the lower deck onto its edge 4.5 yd up)
    assert not WG.Clear(c, -14428.6, 446.4, 0, -14437.0, 446.4, 4.5)
    # (a swim at the water's top in the open bay: clear)
    assert WG.Clear(c, -14400.0, 470.0, 0, -14400.0, 500.0, 0)
    assert not WG.Clear(c, -14400.0, 470.0, 0, -14400.0, 500.0, 4)  # (... not rising off it)


def test_the_bays_east_side_climbs_out_up_its_beach(grids):
    lua, ns = grids
    pts = _walk(lua, ns, 0, BAY_EAST, MACKINLEY)
    assert not _climbs_from_the_water(pts), pts
    assert _near(pts, (-14338.3, 434.9), 4)  # (its beach's foot)


# --- standing on the plank's foot, swimming under the decks ---------------------------------------------------------

def test_standing_on_the_planks_foot_starts_there_not_on_the_deck_over_it(grids):
    lua, ns = grids
    N = ns.Nav
    _swim(lua, False)
    # (nothing followed: a login there, a reload; not swimming, waist deep on the plank)
    N.TrackGridZ(0, *KOOKI)
    z, zs = N.StartFloor(0, *KOOKI)
    assert z is not None and z < 1.5 and zs is None, (z, zs)
    pts = _walk(lua, ns, 0, KOOKI, MACKINLEY, swimming=False)
    assert _near(pts[:3], PLANK_TOP, 3), pts  # (up the plank first)
    assert not _climbs_from_the_water(pts, ways_out=[KOOKI]), pts
    # (its height for "Above you": the plank's, not the sea's bottom 10 yd under it, "26 yd up")
    assert ns.Ground.Sample(0, *KOOKI) < -8
    assert N.PlayerHeightNear(0, *KOOKI) > -3


def test_the_pier_decks_are_still_the_start_when_not_swimming(grids):
    lua, ns = grids
    WG = ns.WorldGrid
    c = WG.Cont(0)
    # (item 106's: Booty Bay's dock to Ratchet and Menethil's, the deck over the water, not the water under it)
    for cont, x, y, deck in [(0, -14313.7, 506.9, 9.0), (0, -3925.2, -621.8, 5.5)]:
        dry = WG.Ends(WG.Cont(cont), x, y, None, False, False)
        assert dry[1].z == pytest.approx(deck, abs=0.5)
        assert all(e.cost >= WG.OTHER_FLOOR_YD for e in dry.values() if int(e.f) % 2 == 1)
    # (swimming, with a height the lower deck 4 yd over the water is within FLOOR_Z of: the water's still)
    wet = WG.Ends(c, *UNDER_DECK, 0, True, False)
    assert all(int(e.f) % 2 == 1 for e in wet.values())


def test_swimming_under_a_route_along_the_deck_reroutes_up_the_plank(grids):
    lua, ns = grids
    N, R = ns.Nav, ns.Router
    cdb = ns.CharDB()
    saved = cdb.faction
    cdb.faction = "Horde"

    def put(x, y, swim):
        _swim(lua, swim)
        lua.execute(f"AGPS_POS[1], AGPS_POS[2] = {x}, {y} AGPS_T = AGPS_T + 0.5")
        ns.GPS.Update()
        while R.HasWork():
            R.Pump(math.inf, lua.eval("function() return 0 end"))

    try:
        N.Clear()
        R.Reset()
        put(-14437.0, 446.4, False)  # (on the lower deck)
        N.SetStops(lua.eval(f"{{ {{ x = {MACKINLEY[0]}, y = {MACKINLEY[1]}, z = {MACKINLEY[2]}, cont = 0,"
                            " name = 'stop' } }"), False, "red")
        N.Invalidate(True, True)
        for _ in range(4):
            put(-14437.0, 446.4, False)
        assert N.route and N.route.fullFirst.fz[1] > 3  # (along the deck)
        # (in the water under it, along the route overhead: not on it)
        for k in range(21):
            put(-14437.0 - k * 0.45, 446.4 - k * 0.62, True)
        full = N.route.fullFirst
        n = len(full.pts) // 2
        pts = [(full.pts[2 * i - 1], full.pts[2 * i], full.fz[i]) for i in range(1, n + 1)]
        assert pts[0][2] == pytest.approx(0, abs=0.5), pts  # (from the water)
        assert _near(pts[:3], KOOKI, 3), pts  # (to the plank)
        assert not _climbs_from_the_water(pts, ways_out=[KOOKI]), pts
    finally:
        cdb.faction = saved
        N.Clear()


# --- the shore pointed to with no route -----------------------------------------------------------------------------

@pytest.mark.parametrize("start", [KOOKI, UNDER_DECK, BAY_SOUTH], ids=["his_spot", "under_deck", "south"])
def test_the_shore_pointed_to_in_booty_bay_is_the_plank(grids, start):
    lua, ns = grids
    e = ns.Shore.Find(0, *start)
    assert e is not None
    assert math.hypot(e.x - KOOKI[0], e.y - KOOKI[1]) <= 3 and abs(e.z) <= 1.5


# --- other harbors --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("cont, start, stop", [
    (0, (-4020.0, -720.0), (-3827.9, -831.9, 10.1)),  # (Menethil's harbor to Innkeeper Helbrek)
    (0, (-3920.0, -640.0), (-3793.2, -782.1, 9.1)),  # (... from by its docks to Shellei Brondir)
    (1, (-1080.0, -3960.0), (-898.2, -3769.7, 11.8)),  # (off Ratchet to Bragok)
    (1, (-1040.0, -3840.0), (-1050.0, -3664.8, 24.0)),  # (Ratchet's docks to Innkeeper Wiley)
], ids=["menethil_inn", "menethil_flight", "ratchet_flight", "ratchet_inn"])
def test_other_harbors_climb_out_only_where_the_land_meets_the_water(grids, cont, start, stop):
    lua, ns = grids
    pts = _walk(lua, ns, cont, start, stop)
    assert not _climbs_from_the_water(pts), pts
    e = ns.Shore.Find(cont, *start)
    assert e is not None and abs(e.z) <= 1.5 + 0.5
