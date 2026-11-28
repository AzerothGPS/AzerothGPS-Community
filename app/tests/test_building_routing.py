"""Routing inside the open world's buildings on their own grids (1.4.2, item 119 steps 3-4; BuildingGrid.lua): the
region's Buildings.lua decoded into the city grid's layout (read in place by CityGrid.lua's search), and the world grid's
legs handing over to a building's grid at its doors."""

import math

import pytest

from azerothgps import buildinggrid as BG

pytest.importorskip("lupa.lua51")

FRAME_MS = 40  # (test_frame_budget.py's)

# (shipped NPCs' spawns, Data/Npcs.lua: level, x, y, z; the walk's start outside, no height)
BERYL = (0, 2265.2, 251.1, 41.2)  # Brill's inn, upstairs (Dark Cleric Beryl)
BRILL_OUT = (0, 2230.0, 200.0, None)
KERYN = (0, -9465.8, 12.6, 63.9)  # Goldshire's inn, upstairs (Keryn Sylvius)
GOLDSHIRE_OUT = (0, -9440.0, 60.0, None)
JAINA = (1, -3749.7, -4454.1, 65.0)  # the top of her tower in Theramore
THERAMORE_OUT = (1, -3700.0, -4400.0, None)
RIELL = (0, -10504.8, 1033.2, 95.8)  # Sentinel Hill's tower top (Scout Riell)
SENTINEL_OUT = (0, -10480.0, 1100.0, None)
CROSSROADS_INN = (1, -402.0, -2644.0, 96.5)  # (test_building_doors' stop in the Crossroads' inn)
CROSSROADS_SE = (1, -360.0, -2700.0, None)
TRIPS = [(BRILL_OUT, BERYL), (GOLDSHIRE_OUT, KERYN), (THERAMORE_OUT, JAINA), (SENTINEL_OUT, RIELL),
         (CROSSROADS_SE, CROSSROADS_INN)]
IDS = ["brill-upstairs", "goldshire-upstairs", "jaina-tower", "sentinel-hill-top", "crossroads-inn"]


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.settings.gps.worldGrid = True
    yield lua, ns


def _list(t):
    return [t[i] for i in range(1, len(t) + 1)] if t is not None else []


def _route(lua, ns, a, b):
    return ns.Router.Route(a[0], a[1], a[2], b[1], b[2], lua.table(z=a[3], tz=b[3]))


def test_the_addon_reads_each_grid_as_the_bake_wrote_it(game):
    """Every surface the bake wrote (buildinggrid.decode) is in the addon's decoding (BG.Decode, the city grid's layout:
    CityGrid.lua's Count/First/Z/Link read it in place) with its height, flags and links."""
    lua, ns = game
    CG, B = ns.CityGrid, ns.BuildingGrid
    data = BG.shipped()
    checked = 0
    for (cont, rx, ry), reg in sorted(data.items())[:4]:
        for vid, s in sorted(reg["m"].items())[:6]:
            py = BG.decode(s)
            d = B.Decode(s, BG.CELL, BG.ZQ, BG.Z0, BG.IMPLIED_Q)
            c = lua.table(cells=d.cells, s=d.s, base=d.base, block=d.block, h=d.h, w=d.w, zmin=d.zmin, zq=d.zq,
                          first=lua.table(), firstN=0)
            assert d.w == py["w"] and d.h == py["h"]
            for (a, b), ss in py["cells"].items():
                ci = a * py["h"] + b
                assert CG.Count(c, ci) == len(ss)
                f = CG.First(c, ci)
                for k, (z, flags, _ox, _oy, links) in enumerate(ss):
                    assert abs(CG.Z(c, f + k) - z) < 1e-6
                    assert ns.BuildingGrid.Flags(d, f + k) == flags
                    assert [CG.Link(c, f + k, dd) for dd in range(1, 9)] == links
            checked += 1
    assert checked >= 12


@pytest.mark.parametrize("a, b", TRIPS, ids=IDS)
def test_into_the_building_by_its_door_ending_on_the_npc_s_floor(game, a, b):
    lua, ns = game
    r = _route(lua, ns, a, b)
    assert r is not None and not r.noWay and not r.pending
    assert r.buildingGrid, "not the building's grid"
    pts, fz = _list(r.pts), _list(r.fz)
    assert math.hypot(pts[-2] - b[1], pts[-1] - b[2]) < 3
    assert abs(fz[-1] - b[3]) < 3, f"the walk ends at {fz[-1]:.1f}, not on the NPC's floor ({b[3]})"
    # (no fall through a floor: never down more than a step down a city's walk takes, CityGrid.CITY_STEP_DOWN, past the
    # slope's yards between two points)
    for k in range(len(fz) - 1):
        if fz[k] is not False and fz[k + 1] is not False:
            run = math.hypot(pts[2 * k + 2] - pts[2 * k], pts[2 * k + 3] - pts[2 * k + 1])
            assert fz[k] - fz[k + 1] <= ns.CityGrid.CITY_STEP_DOWN + run, (k, fz[k], fz[k + 1], run)


@pytest.mark.parametrize("a, b", TRIPS[:2], ids=IDS[:2])
def test_out_of_the_building_by_its_door(game, a, b):
    lua, ns = game
    out = (b[0], b[1], b[2], b[3])
    r = _route(lua, ns, out, (a[0], a[1], a[2], None))
    assert r is not None and not r.noWay and r.buildingGrid
    fz = _list(r.fz)
    assert abs(fz[0] - b[3]) < 3


def test_with_the_option_off_or_outside_the_towns_the_older_indoor_roads(game):
    lua, ns = game
    st = ns.settings.gps
    st.buildingGrid = False
    try:
        ns.WorldGrid.Reset()
        r = _route(lua, ns, BRILL_OUT, BERYL)
        assert not r.buildingGrid
    finally:
        st.buildingGrid = True
        ns.WorldGrid.Reset()
    # (a building of the data outside the test's towns: Stromgarde's keep, none)
    assert ns.BuildingGrid.At(0, -1655.0, -1804.0, 40.0) is None


def test_the_search_runs_in_short_slices_in_the_background(game):
    lua, ns = game
    R, BGl = ns.Router, ns.BuildingGrid
    lua.execute("AGPS_CLOCK_WAS = GetTime; GetTime = function() return os.clock() end")
    R.SYNC_WALKS = False
    try:
        ns.WorldGrid.Reset()
        clock = lua.eval("function() return os.clock() * 1000 end")
        worst, n, r = 0.0, 0, None
        for _ in range(20):
            r = _route(lua, ns, THERAMORE_OUT, JAINA)
            if not r.pending:
                break
            while R.HasWork() and n < 5000:
                t = clock()
                R.Pump(clock() + 1, clock)
                worst = max(worst, clock() - t)
                n += 1
        assert r.buildingGrid and not r.pending
        assert worst < FRAME_MS, f"a slice ran {worst:.0f} ms"
        assert BGl.stats.doors >= 1
    finally:
        R.SYNC_WALKS = True
        lua.execute("GetTime = AGPS_CLOCK_WAS")


def test_the_floor_followed_up_the_inn_s_stairs_and_the_floor_picker_follows(game):
    """Step 5: indoors, CityGrid.TrackFloor follows the building's own grid (its frame, its heights the placement's):
    walked from the door along the route up to Beryl's floor, the floor followed ends upstairs; the floor picker (the
    map's middle there) lists the inn's floors from the building's grid."""
    lua, ns = game
    CG, MX = ns.CityGrid, ns.MapExtras
    r = _route(lua, ns, BRILL_OUT, BERYL)
    pts, fz = _list(r.pts), _list(r.fz)
    lua.execute("AGPS_IND_WAS = IsIndoors; IsIndoors = function() return true end")
    try:
        CG.track = None
        z = None
        for k in range(len(fz) - 1):
            ax, ay, bx, by = pts[2 * k], pts[2 * k + 1], pts[2 * k + 2], pts[2 * k + 3]
            n = max(1, int(math.hypot(bx - ax, by - ay)))
            for q in range(n):
                lua.execute("AGPS_T = AGPS_T + 0.25")
                # (Nav's floor followed outside, the land's: the route's own height there, until the building's)
                nav = fz[k] + (fz[k + 1] - fz[k]) * q / n if z is None else None
                got = CG.TrackFloor(0, ax + (bx - ax) * q / n, ay + (by - ay) * q / n, nav)
                z = got if got is not None else z
        lua.execute("AGPS_T = AGPS_T + 0.25")
        z = CG.TrackFloor(0, BERYL[1], BERYL[2]) or z
        assert z is not None and abs(z - BERYL[3]) < 2, z
        assert CG.track.place is not None
    finally:
        lua.execute("IsIndoors = AGPS_IND_WAS")
        CG.track = None
    hs, cell, kind = MX.GridHeights(0, BERYL[1], BERYL[2])
    assert str(kind) == "building" and cell == 2
    floors, _k = MX.FloorsAt(0, BERYL[1], BERYL[2])
    assert len(_list(floors)) >= 2


@pytest.mark.parametrize("a, b", [(THERAMORE_OUT, JAINA), (SENTINEL_OUT, RIELL), (BRILL_OUT, BERYL)],
                         ids=["jaina-tower", "sentinel-hill-top", "brill-upstairs"])
def test_up_a_tower_the_directions_say_the_way_up(game, a, b):
    """The climb on a building's own grid is said: "Take the stairs up" (T.BuildingStairs: steep, on its floors) or,
    up a gentler built way (Jaina's tower's spiral ramp), "Take the ramp up" (T.Ramps)."""
    lua, ns = game
    T = ns.Turns
    r = _route(lua, ns, a, b)
    part = lua.table(cont=a[0], pts=r.pts, kinds=r.kinds, stop=1, fz=r.fz, zs=r.zs)
    p = T.Path(lua.table(parts=lua.table(part), legs=lua.table(lua.table(walk=True))))
    ms = T.Maneuvers(p)
    said = [str(ms[i].text) for i in range(1, len(ms) + 1)]
    assert any("stairs up" in s.lower() or "ramp up" in s.lower() for s in said), said
