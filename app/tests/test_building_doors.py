"""Into the open world's buildings by their doors (item 70, Kooki3z 2026-11-24 at the Crossroads: "I thought routes to
locations inside of buildings are routed to go through the door now?"; the world grid's line ran through the inn's
wall). WorldGrid.BuildingLeg: a stop inside a building of Data/Indoors.lua, the start outside it: the grid walks to its
door (where the Router's own way along the inside roads goes in), the inside roads from there."""

import pytest

from test_map_redraw import game  # noqa: F401

INN, R_INN = (-402.0, -2644.0), 35  # (The Crossroads: orcinn)


def _route(lua, ns, a, b, tz):
    R, WG, st = ns.Router, ns.WorldGrid, ns.settings.gps
    st.worldGrid, st.cityGrid = True, True
    WG.Set(True)
    R.Reset()
    return R.Route(1, a[0], a[1], b[0], b[1], lua.table(tz=tz))


@pytest.mark.parametrize("start", [(-441.8, -2596.1), (-360.0, -2700.0)], ids=["flight_master", "south_east"])
def test_into_the_crossroads_inn_through_its_door(game, start):  # noqa: F811
    lua, ns = game
    r = _route(lua, ns, start, INN, 96.5)
    pts = [(r.pts[i], r.pts[i + 1]) for i in range(1, len(r.pts), 2)]
    inside = [((x - INN[0]) ** 2 + (y - INN[1]) ** 2) ** 0.5 <= R_INN for x, y in pts]
    # (in for good from here: a road skirting the inn's south wall passes within R_INN of its middle outside, item 57's
    # merge onto it)
    first_in = len(inside) - inside[::-1].index(False)
    # (the last point outside is the door's: the Router's own way's, west side; never a straight line in through the wall)
    door = pts[first_in - 1]
    assert door[0] < -425, (door, pts)  # (the west doors: the line from the flight master went in at x -421, the wall)
    assert all(inside[first_in:]), pts  # (once in, in)


def test_a_stop_outside_buildings_is_as_before(game):  # noqa: F811
    lua, ns = game
    r = _route(lua, ns, (-441.8, -2596.1), (-470.0, -2620.0), None)
    assert r and r.building is None
