"""The floor followed over the world grid's stacked surfaces (item 45, Kooki3z 2026-11-24: in Maraudon's outer cave the
route flipped where passages cross over and under each other; nothing followed the floor there, so each route started on
whichever passage's surface came first). Nav.TrackGridZ keeps the surface at about the height last followed."""

from test_map_redraw import game  # noqa: F401


def test_walking_into_maraudons_crossing_passages_keeps_the_floor_walked_on(game):  # noqa: F811
    lua, ns = game
    N, WG, st = ns.Nav, ns.WorldGrid, ns.settings.gps
    was = st.worldGrid
    st.worldGrid = True
    WG.Set(True)
    try:
        c = WG.Cont(1)
        # (where three are stacked, 74, 88 and 128; his spot, 86.5 under the hill's 139: indoors, the cave's floor)
        assert len(WG.SurfacesAt(c, -1244.0, 2896.0)) >= 3
        lua.execute("AGPS_T = 1000; IsIndoors = function() return true end")
        assert abs(N.TrackGridZ(1, -1191.3, 2896.0) - 86.5) <= 1
        # (walked on from there: that floor, not the passage over or under)
        lua.execute("AGPS_T = 2000")
        z = None
        for k in range(0, 8):
            x = -1191.3 - k * 7.5
            lua.execute(f"AGPS_T = AGPS_T + 0.5")
            z = N.TrackGridZ(1, x, 2896.0) or z
        lua.execute("AGPS_T = AGPS_T + 0.5")
        z = N.TrackGridZ(1, -1244.0, 2896.0)
        assert z is not None and abs(z - 88) <= 3, z
    finally:
        lua.execute("IsIndoors = function() return false end")
        st.worldGrid = was
        WG.Set(bool(was))
