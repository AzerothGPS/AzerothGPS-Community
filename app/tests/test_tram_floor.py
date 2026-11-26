"""The Deeprun Tram's way in under Stormwind's Royal Gallery (Kooki3z 2026-11-23, standing at it at (-8355.85, 525.93,
91.80): "This is the deeprun tram entrance in stormwind but routing takes me to the area above it in the royal
gallery"). The tram's ends carry their floors (Data/Transports.lua's z1, z2: Stormwind's measured there, Ironforge's
the city grid's under its trigger; the triggers' own heights are their boxes' middles), the search's tram docks carry
them to the stop, and a stop put there with no height gets the way in's floor: the route ends down there, not on the
Royal Gallery's floor 31 yd over it."""

import pytest

pytest.importorskip("lupa")

GALLERY_Z = 122.8  # (Stormwind's Royal Gallery, over the way in)


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.settings.gps.cityGrid = True
    return lua, ns


def _tram(ns):
    return next(t for t in ns.Transports.values() if t[8] == "tram")


def _end_z(lua, ns, cont, x, y, z=None):
    d = {"x": x, "y": y, "cont": cont}
    if z is not None:
        d["z"] = z
    ns.Nav.SetStops(lua.eval("{}"), False, "red")
    ns.Nav.SetStops(lua.table_from([lua.table_from(d)]), False, "red")
    s = ns.Nav.stops[1]
    ns.Router.Reset()
    tz = ns.Nav.StopZ(s)  # (the route's height for it)
    r = ns.Router.Route(0, -8800.0, 640.0, x, y, lua.table_from({"z": 96.0, "tz": tz}))
    return tz, r


def test_the_tram_s_ends_are_on_their_floors(game):
    lua, ns = game
    t = _tram(ns)
    assert t.z1 == pytest.approx(91.8) and t.z2 == pytest.approx(502.0)


def test_the_search_s_tram_dock_carries_its_floor(game):
    lua, ns = game
    was = ns.CharDB().faction
    ns.CharDB().faction = "Alliance"  # (the tram's offered to the Alliance)
    lua.execute('UnitFactionGroup = function() return "Alliance", "Alliance" end')
    try:
        hits = [e for e in ns.GPS.SearchPlacesPlain("Stormwind City", 50).values()
                if e.cont == 0 and abs(e.x + 8346.5) < 1]
    finally:
        ns.CharDB().faction = was
        lua.execute('UnitFactionGroup = function() return "Horde", "Horde" end')
    assert hits and hits[0].z == pytest.approx(91.8), [(e.name, e.sub, e.z) for e in hits]


@pytest.mark.parametrize("z", [91.8, None])  # (the dock's, and a stop put there with no height of its own)
def test_a_route_to_the_deeprun_tram_in_stormwind_ends_on_its_way_in_not_the_royal_gallery(game, z):
    lua, ns = game
    t = _tram(ns)
    tz, r = _end_z(lua, ns, 0, t[2], t[3], z)
    assert tz is not None and abs(tz - 92) < 2, tz
    n = len(r.pts) // 2
    assert r.cityGrid == "Stormwind City" and abs(r.fz[n] - 92) < 2, r.fz[n]
    assert all(abs(r.fz[i] - GALLERY_Z) > 5 for i in range(n - 3, n + 1))


def test_ironforge_s_tram_end_is_on_the_city_s_floor(game):
    lua, ns = game
    t = _tram(ns)
    z, src = ns.Nav.GuessStopZ(lua.table_from({"x": t[5], "y": t[6], "cont": 0}))
    assert abs(z - 502) < 2 and abs(t.z2 - z) < 2, (z, src)
