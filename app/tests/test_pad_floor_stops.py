"""A controller's stop inside a cave or building (item 121, Kooki3z 2026-11-26: "on a controller if viewing inside a
building/cave and a stop is set that should count the same as double clicking a stop to add inside the building/cave to
route inside it").

The controller's Select (A) at the crosshair goes through the double-click's own G.AddPending at the map's middle, so the
stop takes the height G.MapStopZ gives a double-click there: a cave's floor under its overlay (the crosshair hovering it,
as the mouse does in the opened-out map), the floor picked on a cave's or building's map (its floor bar's + and -, item 121: before,
neither the mouse's nor the pad's stop took it), a map drawn from its cells (item 115) too, the floor picker's (item 114c).
The route then goes inside to it (test_cave_inside_routes.py's Wailing Caverns walk). In the GPS map and world-map mode.
"""

from __future__ import annotations

import pytest

from test_cave_inside_routes import START, STOP, WC, points, settle
from test_controller import PAD_STUBS, _fake_buttons, _hold, _press
from test_world_map_host import SETUP as WM_SETUP

pytest.importorskip("lupa.lua51")

ASTRANAAR_INN = "in239623"  # (test_auto_maps.py's: a night elf inn, no art, two floors)


@pytest.fixture(scope="module")
def game():
    from test_atlas import _seamless
    lua, ns = _seamless()
    st = ns.settings.gps
    st.worldGrid, st.cityGrid = True, True
    ns.WorldGrid.Set(True)
    ns.CityGrid.Set(True)
    lua.execute("AGPS_LEVEL = 60; UnitFactionGroup = function() return 'Horde' end")
    ns.CharDB().faction = "Horde"
    lua.execute(PAD_STUBS)
    _fake_buttons(lua)
    ns.db.padOffered = True
    st.padControl = True
    yield lua, ns


@pytest.fixture
def pad(game):
    lua, ns = game
    P, G = ns.Pad, ns.GPS
    P.used = True
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3], AGPS_POS[4] = {START[0]}, {START[1]}, 1, 0 "
                "IsIndoors = function() return false end AGPS_T = (AGPS_T or 0) + 1000 "
                "AGPS_NS.GPS.CursorWorld = function() return nil end")
    ns.settings.gps.zoom = 80.0
    ns.Nav.Clear()
    G.Follow()
    G.Update()
    assert P.Apply() and P.marksOn
    try:
        yield lua, ns
    finally:
        while G.PendingStop(1):
            G.RemovePending(1)
        ns.Nav.Clear()
        G.Follow()
        P.used = False
        P.Clear()


def _tap(lua, key):
    _hold(lua, key)
    _press(lua, key)
    _press(lua, key, False)
    _hold(lua, key, False)


def _crosshair(lua, ns, cont, x, y):
    """The crosshair panned onto (x, y): the view there, its inside map hovered as the mouse would (G.BuildingHover)."""
    G = ns.GPS
    G.PadLookAt(cont, x, y)
    for _ in range(3):
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        G.BuildingHover()
        G.Update()


def _pad_stop(lua, ns):
    """A at the crosshair: the stop it set (removed again), as (x, y, z, cont)."""
    G = ns.GPS
    _tap(lua, "PAD1")
    d = G.PendingStop(1)
    assert d is not None, "no stop"
    out = (d.x, d.y, d.z, d.cont)
    G.RemovePending(1)
    return out


def _wailing_caverns(lua, ns):
    G = ns.GPS
    _crosshair(lua, ns, 1, *STOP)
    assert G.hoveredCave == WC and G.shownView.cave is not None  # (the crosshair hovers it, as the mouse)
    want = G.MapStopZ(1, *STOP)  # (a double-click's at the map's middle)
    x, y, z, cont = _pad_stop(lua, ns)
    assert (x, y, cont) == (pytest.approx(STOP[0]), pytest.approx(STOP[1]), 1)
    assert z is not None and z == pytest.approx(want) and z < 40, (z, want)  # (the cave's floor, not the hill over it)
    return z


def test_a_controller_stop_inside_a_cave_goes_on_its_floor_with_the_route_inside(pad):
    lua, ns = pad
    z = _wailing_caverns(lua, ns)
    ticks, r, nodes = settle(lua, ns, START, STOP, z)
    assert ticks is not None and r is not None and not r.noWay, (ticks, nodes)
    pts = points(r)
    zs = [fz for _, _, fz in pts if fz is not None]
    assert max(zs) < 100 and abs(zs[-1] - z) <= 3, (max(zs), zs[-1], z)  # (in by the mouth, never over the hill)
    WG = ns.WorldGrid
    inside = [p for p in pts if p[2] is not None and WG.InCave(1, p[0], p[1], p[2], WG.CAVE_DOOR_Z) == WC]
    assert len(inside) >= 10, len(inside)


def test_a_controller_stop_inside_a_cave_in_the_world_map_too(pad):
    lua, ns = pad
    G, st = ns.GPS, ns.settings.gps
    lua.execute(WM_SETUP)
    was = {k: st[k] for k in ("useWorldMap", "replaceMinimap", "shown", "minimized")}
    try:
        st.shown, st.minimized, st.useWorldMap = True, None, True
        G.ApplySettings()
        lua.globals().AzerothGPS_ToggleMap()
        assert G.WorldMapHosted()
        lua.execute("AGPS_T = AGPS_T + 0.5")
        G.Update()
        assert ns.Pad.Apply()
        _wailing_caverns(lua, ns)
    finally:
        lua.execute("WorldMapFrame:Hide() ToggleWorldMap = nil")
        for k, v in was.items():
            st[k] = v
        G.WorldMapChanged()
        G.ApplySettings()


def test_a_controller_stop_on_a_buildings_floor_picked_goes_on_that_floor(pad):
    lua, ns = pad
    G, N = ns.GPS, ns.Nav
    art = G.AutoArt(1, ASTRANAAR_INN)
    assert art and len(art.floors) == 2
    up = art.floors[2]
    spot = (art.auto[2][1], art.auto[2][2])  # (a spot on its upper floor)
    cdb = ns.CharDB()
    lua.execute("UnitFactionGroup = function() return 'Alliance' end")
    cdb.faction = "Alliance"
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {spot[0] + 60}, {spot[1] + 60}, 1")
    try:
        _crosshair(lua, ns, 1, *spot)
        assert G.hoveredCave == ASTRANAAR_INN and G.shownView.cave is not None
        # (all its floors shown: no floor of its own, as before)
        assert G.shownView.floor == 0 and G.ShownFloorZ(1, *spot) is None
        G.FloorStep(False)  # (the floor bar's -: from all of them, the top one)
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert G.shownView.floor == 1
        want = G.MapStopZ(1, *spot)  # (a double-click's)
        x, y, z, cont = _pad_stop(lua, ns)
        assert z is not None and z == pytest.approx(want), (z, want)
        assert up[1] - 1 <= z <= up[2] + 1, (z, up[1], up[2])
        # (the route goes up to it)
        ticks, r, nodes = settle(lua, ns, (spot[0] + 60, spot[1] + 60), spot, z)
        assert ticks is not None and r is not None and not r.noWay, (ticks, nodes)
        zs = [fz for _, _, fz in points(r) if fz is not None]
        assert zs and abs(zs[-1] - z) <= 3, (zs[-1:], z)
        # (the lower floor picked: that one)
        G.FloorStep(False)
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert G.shownView.floor == 2
        low = G.ShownFloorZ(1, *spot)
        assert low is None or art.floors[1][1] - 1 <= low <= art.floors[1][2] + 1
    finally:
        lua.execute("UnitFactionGroup = function() return 'Horde' end")
        cdb.faction = "Horde"
