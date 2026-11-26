"""Floor evidence (item 106, 1.4.1, SPF parity; the idea from Shortest Path Forever, GPL-3, our own code): the floors the
player may be on are kept until the game gives evidence they left one (a fall seen via IsFalling, swimming via IsSwimming,
a lift, a teleport), not dropped just because the grid has no way from it to the new spot (Nav.TrackGridZ,
CityGrid.TrackFloor). With more than one left, a walk starts from each and keeps the cheapest (WorldGrid's and
CityGrid's Ends). On a pier or a dock, not swimming, the walk starts on the deck, not the water under it."""

import pytest

from test_map_redraw import game  # noqa: F401

# (the world grid's surfaces there: the water's at 0 (swim), the deck over it; the shipped ground the sea's bottom)
MENETHIL_PIER = (0, -3925.2, -621.8, 5.5)  # Menethil Harbor's docks, the boats to Theramore and Auberdine
BOOTY_PIER = (0, -14313.7, 506.9, 9.0)  # Booty Bay's docks, the boat to Ratchet
MENETHIL_OFF_DECK = (-3937.2, -621.8)  # (a few yards off the deck's west edge: only the water)
MENETHIL_TOWN = (-3860.0, -650.0)  # (ashore)
MARAUDON = (1, -1244.0, 2896.0)  # Maraudon's outer cave: passages 73.5 and 87.5 under the hill's 128.5
MARAUDON_EAST = (-1191.3, 2896.0, 86.5)  # (along the 87.5 passage, test_grid_floor_track's spot)
# Undercity: a walkway at -34.5 whose grid cell next to it has only the floor under it, -47.5 (a gap in the grid's
# walkway: the cell after has the walkway again)
UC = 10001
UC_WALKWAY = (1568.4, 205.4, -34.5)
UC_GAP = (1571.9, 205.9, -47.5)


@pytest.fixture
def grids(game):  # noqa: F811
    lua, ns = game
    st, WG, R = ns.settings.gps, ns.WorldGrid, ns.Router
    was = (st.worldGrid, st.cityGrid, R.SYNC_WALKS)
    st.worldGrid = st.cityGrid = True
    WG.Set(True)
    R.SYNC_WALKS = True
    lua.execute("AGPS_FE = { swim = false, fall = false, indoors = false }"
                " AGPS_FE_SAVED = { IsSwimming = rawget(_G, 'IsSwimming'), IsFalling = rawget(_G, 'IsFalling'),"
                "   IsIndoors = rawget(_G, 'IsIndoors') }"
                " IsSwimming = function() return AGPS_FE.swim end"
                " IsFalling = function() return AGPS_FE.fall end"
                " IsIndoors = function() return AGPS_FE.indoors end")
    _fresh(lua, ns)
    yield lua, ns
    lua.execute("IsSwimming, IsFalling, IsIndoors = AGPS_FE_SAVED.IsSwimming, AGPS_FE_SAVED.IsFalling,"
                " AGPS_FE_SAVED.IsIndoors")
    _fresh(lua, ns)
    st.worldGrid, st.cityGrid, R.SYNC_WALKS = was
    WG.Set(bool(was[0]))


def _fresh(lua, ns):
    """A teleport, a login: nothing followed, a while later."""
    N = ns.Nav
    N.ResetGridTrack()
    N.ResetTrack()
    N.ResetCityTrack()
    N.fellAt = None
    _tick(lua, 30)


def _tick(lua, s=0.3):
    lua.execute(f"AGPS_T = AGPS_T + {s}")


def _set(lua, **kw):
    for k, v in kw.items():
        lua.execute(f"AGPS_FE.{k} = {'true' if v else 'false'}")


# --- piers and docks: the deck, not the water under it ---------------------------------------------------------------

@pytest.mark.parametrize("pier", [MENETHIL_PIER, BOOTY_PIER], ids=["menethil", "booty_bay"])
def test_on_a_pier_the_start_is_the_deck_and_swimming_the_water(grids, pier):
    lua, ns = grids
    WG, N = ns.WorldGrid, ns.Nav
    cont, x, y, deck = pier
    c = WG.Cont(cont)
    zs = sorted(e.z for e in WG.SurfacesAt(c, x, y).values())
    assert zs[0] == pytest.approx(0, abs=0.5) and zs[-1] == pytest.approx(deck, abs=0.5), zs
    # (the shipped ground there is the sea's bottom: the floor nearest it was the water's)
    assert ns.Ground.Sample(cont, x, y) < -5
    dry = WG.Ends(c, x, y, None, False, False)
    assert dry[1].z == pytest.approx(deck, abs=0.5) and int(dry[1].f) % 2 == 0
    assert any(int(e.f) % 2 == 1 and e.cost >= WG.OTHER_FLOOR_YD for e in dry.values())  # (the water: dearer)
    wet = WG.Ends(c, x, y, None, True, False)
    assert wet[1].z == pytest.approx(0, abs=0.5)
    # (the floor followed there: the deck alone, known; swimming under it, the water's)
    N.TrackGridZ(cont, x, y)
    assert N.GridTrackZ(cont) == pytest.approx(deck, abs=0.5)
    assert N.GridCandidates(cont, x, y) is None
    _fresh(lua, ns)
    _set(lua, swim=True)
    N.TrackGridZ(cont, x, y)
    assert N.GridTrackZ(cont) == pytest.approx(0, abs=0.5)


def test_a_walk_from_menethils_pier_starts_on_the_deck(grids):
    lua, ns = grids
    WG = ns.WorldGrid
    cont, x, y, deck = MENETHIL_PIER
    r = WG.Walk(WG.Cont(cont), x, y, None, *MENETHIL_TOWN, None, lua.table(swimming=False))
    assert r and r.fz[1] == pytest.approx(deck, abs=0.5)
    assert r.length < 120  # (along the deck ashore, not a swim round from under it)


# --- a floor kept with no way on the grid until there's evidence -----------------------------------------------------

def test_off_the_decks_edge_the_deck_is_held_until_a_fall_or_a_swim(grids):
    lua, ns = grids
    N = ns.Nav
    cont, x, y, deck = MENETHIL_PIER
    N.TrackGridZ(cont, x, y)
    assert N.GridTrackZ(cont) == pytest.approx(deck, abs=0.5)
    # (a few yards on, the grid has only the water there: no way from the deck to it, no fall, no swim: the deck held)
    _tick(lua)
    N.TrackGridZ(cont, *MENETHIL_OFF_DECK)
    assert N.GridTrackZ(cont) == pytest.approx(deck, abs=0.5)
    # (a fall seen meanwhile, between two looks (the status updates): the floor under it, the water's)
    _set(lua, fall=True)
    N.NoteFloorEvidence()
    _set(lua, fall=False)
    _tick(lua)
    N.TrackGridZ(cont, MENETHIL_OFF_DECK[0] - 0.5, MENETHIL_OFF_DECK[1])
    assert N.GridTrackZ(cont) == pytest.approx(0, abs=0.5)
    # (again from the deck: swimming is evidence too)
    _fresh(lua, ns)
    N.TrackGridZ(cont, x, y)
    _tick(lua)
    _set(lua, swim=True)
    N.TrackGridZ(cont, *MENETHIL_OFF_DECK)
    assert N.GridTrackZ(cont) == pytest.approx(0, abs=0.5)
    # (and held only so far: past GRID_HOLD_YD from where the deck was last seen, it's let go)
    _fresh(lua, ns)
    N.TrackGridZ(cont, x, y)
    for k in range(1, 8):
        _tick(lua)
        N.TrackGridZ(cont, MENETHIL_OFF_DECK[0] - 4 * k, MENETHIL_OFF_DECK[1])
    assert N.GridTrackZ(cont) == pytest.approx(0, abs=0.5)


def test_undercitys_walkway_is_held_over_the_grids_gap_until_a_fall(grids):
    lua, ns = grids
    CG, N = ns.CityGrid, ns.Nav
    x, y, z = UC_WALKWAY
    assert CG.TrackFloor(UC, x, y) == pytest.approx(z, abs=0.5)
    # (the next cell has only the floor 13 yd under it and no way down to it: before, the floor followed went down)
    _tick(lua)
    assert CG.TrackFloor(UC, UC_GAP[0], UC_GAP[1]) == pytest.approx(z, abs=0.5)
    _tick(lua)
    assert CG.TrackFloor(UC, x, y) == pytest.approx(z, abs=0.5)  # (and back onto it)
    # (a fall seen there: the floor under it)
    _tick(lua)
    _set(lua, fall=True)
    try:
        assert CG.TrackFloor(UC, UC_GAP[0], UC_GAP[1]) == pytest.approx(UC_GAP[2], abs=0.5)
    finally:
        _set(lua, fall=False)
    # (with no walk from the last floors and nothing held, a teleport's start: every floor there, as before)
    _fresh(lua, ns)
    CG.track = None
    assert CG.TrackFloor(UC, UC_GAP[0], UC_GAP[1]) == pytest.approx(UC_GAP[2], abs=0.5)


# --- unsure: the walk starts from every candidate and keeps the cheapest -----------------------------------------------

def test_in_maraudons_crossing_passages_an_unsure_start_takes_the_cheapest_candidate(grids):
    lua, ns = grids
    WG, N = ns.WorldGrid, ns.Nav
    cont, x, y = MARAUDON
    c = WG.Cont(cont)
    # (indoors with nothing followed: the highest floor under the hill's ground, as before (item 89's rule: a better
    # guess there than the cheapest), known)
    _set(lua, indoors=True)
    assert N.TrackGridZ(cont, x, y) == pytest.approx(87.5, abs=0.5)
    assert N.GridCandidates(cont, x, y) is None
    # (outdoors with nothing followed: the floor nearest the shipped ground, the hill's top, known; never the cheapest
    # there, which would put a player on a cliff's rim at the canyon's floor under it)
    _fresh(lua, ns)
    _set(lua, indoors=False)
    N.TrackGridZ(cont, x, y)
    assert N.GridTrackZ(cont) == pytest.approx(128.5, abs=0.5)
    assert N.GridCandidates(cont, x, y) is None
    # (the floors followed still all three, held over a gap in the grid: unsure which)
    N.SetGridTrackForTests(cont, x, y, lua.table(73.5, 87.5, 128.5))
    zs = N.GridCandidates(cont, x, y)
    got = [zs[i] for i in range(1, len(zs) + 1)] if zs is not None else None
    assert got is not None and [round(v * 2) / 2 for v in got] == [73.5, 87.5, 128.5], got
    assert N.GridCandidates(cont, x + 20, y) is None  # (only for a start where they were followed)
    tx, ty, tz = MARAUDON_EAST
    lengths = []
    for z in got:
        r = WG.Walk(c, x, y, z, tx, ty, tz, lua.table())
        assert r, z
        lengths.append(r.length)
    assert min(lengths) == lengths[1]  # (from the passage at 87.5: it runs on east to the spot)
    both = WG.Walk(c, x, y, None, tx, ty, tz, lua.table(zs=zs))
    assert both and both.fz[1] == pytest.approx(got[1], abs=0.5)
    assert both.length <= lengths[1] + 0.5
    # (from elsewhere in the leg, a door, a city's edge: not the player's candidates)
    assert WG.StartZs(lua.table(zs=zs), x + 10, y) is None


def test_a_city_grid_start_with_no_floor_picked_starts_on_the_candidates_only(grids):
    lua, ns = grids
    CG = ns.CityGrid
    c = CG.City("Undercity")
    x, y, z = UC_WALKWAY
    CG.track = None
    CG.TrackFloor(UC, x, y)
    ends = CG.Ends(c, x, y, None, lua.table(z))
    assert len(ends) >= 1 and all(abs(e.z - z) <= CG.FLOOR_Z for e in ends.values())
    assert list(CG.PlayerFloorZs(UC, x, y) or []) == []  # (a floor known: no candidates)
