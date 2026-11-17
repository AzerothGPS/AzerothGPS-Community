"""The trip sweep's `wallcut` flag (the user's wall check, part 3, 2026-10-07): one straight piece off the roads that
crosses WALLCUT_YD or more of blocked ground in one go stands out from the summed `blocked` flags (gap links over
passes the grid is strict about)."""

import pytest


def test_a_line_through_the_mountains_is_a_wallcut_and_a_road_isnt():
    pytest.importorskip("lupa.lua51")
    from azerothgps import tripsweep
    from azerothgps.gameharness import start

    lua, ns = start()
    tripsweep.install_helpers(lua)
    R = ns.Router

    def route(*pts, kind=None):
        flat = [v for p in pts for v in p]
        k = R.KIND_OFFROAD if kind is None else kind
        part = lua.table(leg=1, cont=0, pts=lua.table(*flat), kinds=lua.table(*([k] * (len(pts) - 1))))
        return lua.table(parts=lua.table(part))

    # (Brill straight to Arathi's west: over Alterac's mountains)
    over = tripsweep._longest_blocked(lua, route((2254.0, 293.0), (-1441.0, -2332.0)))
    assert over >= tripsweep.WALLCUT_YD
    # (the same line as a road: roads aren't judged here)
    assert tripsweep._longest_blocked(lua, route((2254.0, 293.0), (-1441.0, -2332.0), kind=R.KIND_ROAD)) == 0
    # (a short walk across Brill's square: nothing blocked in one go that long)
    assert tripsweep._longest_blocked(lua, route((2254.0, 293.0), (2235.0, 260.0))) < tripsweep.WALLCUT_YD
