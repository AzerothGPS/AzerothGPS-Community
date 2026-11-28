"""1.4.0's world routing, being tested (WorldGrid.lua, Data/WorldGrid<cont>.lua, worldgrid.py / worldbake.py;
docs/world-grid-1.4.0.md): the data, the option off, routes on the grid, the city grid inside the capitals, the
background search's slices."""

from __future__ import annotations

import math
import re

import pytest

from azerothgps import worldbake as B
from azerothgps.paths import ADDON_DIR

pytest.importorskip("lupa.lua51")

FRAME_MS = 40
DATA = {c: ADDON_DIR / "Data" / f"WorldGrid{c}.lua" for c in (0, 1, 2991)}

# (shipped NPCs' spawns, Data/Npcs.lua: level, x, y, z)
GRYSHKA = (1, 1634.0, -4439.4, 15.5)  # Orgrimmar's inn
ZEVROST = (1, 1849.0, -4360.4, -14.8)  # the Cleft of Shadow, under the Drag
RAZOR_HILL = (1, 300.0, -4700.0, None)  # Durotar, by Razor Hill
SEN_JIN = (1, -600.0, -4250.0, None)  # Durotar's west, toward Sen'jin Village
GOLDSHIRE = (0, -9460.0, 60.0, None)  # Elwynn Forest
LAKE = (0, -9050.0, -40.0, None)
# (Loch Modan's hop test, test_routecheck_regressions: the road north of Stonesplinter Valley, the Maker's Terrace)
LOCH_NORTH = (0, -5743.0, -2820.0, None)
TERRACE = (0, -6116.7, -3250.0, None)


@pytest.fixture(scope="module")
def game():
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Router.SYNC_WALKS = True
    yield lua, ns
    ns.settings.gps.worldGrid = False


def _list(t):
    return [t[i] for i in range(1, len(t) + 1)] if t is not None else None


def _route(lua, ns, a, b, on=True):
    ns.settings.gps.worldGrid = on
    try:
        o = lua.table()
        if a[3] is not None:
            o.z = a[3]
        if b[3] is not None:
            o.tz = b[3]
        return ns.Router.Route(a[0], a[1], a[2], b[1], b[2], o)
    finally:
        ns.settings.gps.worldGrid = False


# --- the data -------------------------------------------------------------------------------------------------------

def _head(c):
    txt = DATA[c].read_text(encoding="utf-8")
    m = re.search(r'ns\.WorldGridData\[%d\] = \{ per = (\d+), cell = ([\d.]+).*?bake = "(\w+)", n = (\d+), implied = (\d+), '
                  r'rb = (\d+), regions = \{ (.*?) \} \}' % c, txt)
    regions = dict(re.findall(r'\["(\d+:\d+)"\] = (\d+)', m.group(7)))
    return m, {k: int(v) for k, v in regions.items()}


def _region_files(c):
    return sorted(p for p in ADDON_DIR.parent.glob(f"AzerothGPS_WG{c}_*") if p.is_dir())


def _tiles(c):
    out = {}
    for folder in _region_files(c):
        txt = (folder / "Data.lua").read_text(encoding="utf-8")
        out.update(dict(re.findall(r'\n  \[(\d+)\] = "([^"]*)",', txt)))
    return out


def _tokens(part, width):
    n, i = 0, 0
    while i < len(part):
        if part[i] == B.REP:
            n += B.ALPHA.index(part[i + 1]) + 2
            i += 2
        else:
            n += 1
            i += width(part[i])
    return n


def _counts(part):
    out, i, last = [], 0, None
    while i < len(part):
        if part[i] == B.REP:
            out += [last] * (B.ALPHA.index(part[i + 1]) + 2)
            i += 2
        else:
            last = B.ALPHA.index(part[i])
            out.append(last)
            i += 1
    return out


@pytest.mark.parametrize("cont", [0, 1, 2991])
def test_the_grids_are_numbers_only_and_whole(cont):
    head, regions = _head(cont)
    tiles = _tiles(cont)
    assert head and tiles
    per, n = int(head.group(1)), int(head.group(4))
    total = 0
    for key, s in tiles.items():
        assert set(s) <= set(B.ALPHA + B.REP + "|"), key
        counts, recs, hs, lks = s.split("|")
        c = _counts(counts)
        assert len(c) == per * per, key
        k = sum(c)
        assert _tokens(recs, lambda ch: 2) == k, key
        assert _tokens(hs, lambda ch: 4 if B.ALPHA.index(ch) == B.ZESC else 1) == k, key
        assert _tokens(lks, lambda ch: 1 if ch == "0" else 5) == k, key
        total += k
    assert total == n
    # (every region the header names has its folder with its tiles, and no other folder of this continent's is there)
    names = {f"AzerothGPS_WG{cont}_{r.replace(':', '_')}" for r in regions}
    assert {p.name for p in _region_files(cont)} == names
    by = {}
    for key in tiles:
        r = B.region_of(int(key))
        by[f"{r[0]}:{r[1]}"] = by.get(f"{r[0]}:{r[1]}", 0) + 1
    assert by == regions


@pytest.mark.parametrize("cont", [0, 1, 2991])
def test_the_grids_are_baked_with_the_parameters_there_now(cont):
    head, _r = _head(cont)
    assert head.group(3) == B.bake_stamp(), "worldbake's or worldgrid's parameters changed: agps world-grid bake --write"
    for folder in _region_files(cont):
        assert f'bake = "{head.group(3)}"' in (folder / "Data.lua").read_text(encoding="utf-8"), folder.name


def test_the_regions_are_load_on_demand_addons_of_azerothgps():
    toc = (ADDON_DIR / "AzerothGPS.toc").read_text(encoding="utf-8")
    iface = re.search(r"^## Interface: *(\S+)", toc, re.M).group(1)
    for cont in (0, 1, 2991):
        for folder in _region_files(cont):
            t = (folder / f"{folder.name}.toc").read_text(encoding="utf-8")
            assert "## LoadOnDemand: 1" in t and "## Dependencies: AzerothGPS" in t, folder.name
            assert f"## Interface: {iface}" in t, folder.name
            # (and its landmark fields, item 33: test_world_grid_alt.py)
            # (and its buildings' grids where it has buildings, 1.4.2: test_building_grid.py)
            bld = ["Buildings.lua"] if (folder / "Buildings.lua").is_file() else []
            assert [ln for ln in t.splitlines() if ln and not ln.startswith("#")] == ["Data.lua", "Alt.lua"] + bld
    # (none of it loads with AzerothGPS: its toc lists only the headers)
    assert "AzerothGPS_WG" not in toc


def test_the_release_zip_and_the_install_take_the_regions():
    from azerothgps.paths import REPO
    wf = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "AzerothGPS_WG*" in wf
    cli = (REPO / "app" / "azerothgps" / "cli.py").read_text(encoding="utf-8")
    assert 'glob("AzerothGPS_WG*")' in cli


def test_with_the_option_off_the_grid_is_never_asked(game):
    lua, ns = game
    WG = ns.WorldGrid
    was = WG.Leg
    WG.Leg = lua.eval("function() error('asked with the option off') end")
    try:
        r = _route(lua, ns, RAZOR_HILL, SEN_JIN, on=False)
        assert r.worldGrid is None and len(r.pts) >= 4
    finally:
        WG.Leg = was


# --- routes -----------------------------------------------------------------------------------------------------------

def _heights(r):
    return [h for h in _list(r.fz)] if r.fz is not None else None


@pytest.mark.parametrize("a, b", [(RAZOR_HILL, SEN_JIN), (GOLDSHIRE, LAKE)])
def test_an_open_world_leg_walks_the_grid(game, a, b):
    lua, ns = game
    r = _route(lua, ns, a, b)
    assert r.worldGrid and not r.pending
    pts = _list(r.pts)
    assert (pts[0], pts[1]) == (a[1], a[2]) and (pts[-2], pts[-1]) == (b[1], b[2])
    assert len(_heights(r)) == len(pts) // 2 and all(h is not False for h in _heights(r))
    own = _route(lua, ns, a, b, on=False)
    assert r.length < own.length * 1.15  # (the ground's own way: about as short as the roads' or shorter)


def test_loch_modan_s_cliffs_are_walked_round_not_hopped(game):
    # (test_loch_modan_no_hop_over_the_cliffs_by_the_makers_terrace, on the grid: every straight piece of the walk is
    # one the terrain grid has no wall across, and the grid's way is longer than the straight line over the cliffs)
    lua, ns = game
    P = ns.Passability
    r = _route(lua, ns, LOCH_NORTH, TERRACE)
    assert r.worldGrid
    pts, kinds = _list(r.pts), _list(r.kinds)
    hops = [(pts[2 * i], pts[2 * i + 1]) for i, k in enumerate(kinds)
            if k == 1 and P.CrossesWall(0, pts[2 * i], pts[2 * i + 1], pts[2 * i + 2], pts[2 * i + 3])]
    assert hops == []
    assert r.length > math.dist(LOCH_NORTH[1:3], TERRACE[1:3]) * 1.15


def test_inside_a_capital_only_the_city_grid_routes(game):
    lua, ns = game
    r = _route(lua, ns, GRYSHKA, ZEVROST)
    assert r.cityGrid == "Orgrimmar" and not r.worldGrid  # (CG.Leg's: the world grid leaves the city to it)


def test_from_the_land_into_a_capital_the_grids_are_spliced_at_the_gate(game):
    lua, ns = game
    s0 = ns.WorldGrid.stats.spliced
    r = _route(lua, ns, RAZOR_HILL, ZEVROST)
    assert r.worldGrid and r.cityGrid == "Orgrimmar"
    assert ns.WorldGrid.stats.spliced == s0 + 1
    hs = _list(r.fz)
    assert abs(hs[-1] - ZEVROST[3]) < 4  # (down in the Cleft, not on the Drag over it)


def test_the_search_runs_in_short_slices_in_the_background(game):
    lua, ns = game
    R, WG = ns.Router, ns.WorldGrid
    lua.execute("AGPS_CLOCK_WAS = GetTime; GetTime = function() return os.clock() end")
    R.SYNC_WALKS = False
    ns.settings.gps.worldGrid = True
    try:
        WG.routes, WG.order, WG.conts = lua.table(), lua.table(), lua.table()  # (tiles decoded afresh too)
        r = R.Route(1, RAZOR_HILL[1], RAZOR_HILL[2], SEN_JIN[1], SEN_JIN[2], lua.table())
        assert r.pending  # (the Router's own meanwhile)
        clock = lua.eval("function() return os.clock() * 1000 end")
        worst, n = 0.0, 0
        while R.HasWork():
            a = clock()
            R.Pump(clock() + 1, clock)
            worst = max(worst, clock() - a)
            n += 1
        assert n > 3, "the search ran in one go"
        assert worst < FRAME_MS, f"a slice of the search ran {worst:.0f} ms"
        r = R.Route(1, RAZOR_HILL[1], RAZOR_HILL[2], SEN_JIN[1], SEN_JIN[2], lua.table())
        assert r.worldGrid and not r.pending
    finally:
        R.SYNC_WALKS = True
        ns.settings.gps.worldGrid = False
        lua.execute("GetTime = AGPS_CLOCK_WAS")


def test_the_command_says_its_stats_and_switches_nothing(game):
    # (item 74: the grid system always on, no switch for players; /agps worldgrid is its stats)
    lua, ns = game
    said = []
    was = ns.Print
    ns.Print = lambda s: said.append(s)
    st = ns.settings.gps
    on = st.worldGrid
    try:
        for b in ("stats", "off", "on", ""):
            ns.WorldGrid.Slash(b)
        assert st.worldGrid == on
    finally:
        ns.Print = was
    assert any("world grid" in s for s in said)


def test_teldrassil_s_heights_are_its_own(game):
    # (the first file's heights were 2 characters from -1000: Teldrassil's crown, 1,300-1,500 yd up, came out 1,047)
    lua, ns = game
    a = (1, 10464.0, 829.5, 1381.0)  # Mardant Strongoak, up in Aldrassil
    b = (1, 9844.8, 1030.8, 1304.8)  # Huntress Nhemai, by Dolanaar
    r = _route(lua, ns, a, b)
    assert r.worldGrid
    hs = _list(r.fz)
    assert abs(hs[-1] - b[3]) < 5 and min(hs) > 1250, (hs[0], hs[-1], min(hs))


# --- loading only what a route needs (asked 2026-11-22: "only load data thats needed for the route") -----------------

def _loaded(ns):
    out = {}
    for c in (0, 1, 2991):
        cc = ns.WorldGrid.conts[c]
        if cc is not None:
            out[c] = (sorted(k for k, v in cc.regions.items() if v), sum(1 for _ in cc.tiles.items()))
    return out


def test_nothing_of_the_grid_loads_at_login():
    from azerothgps.gameharness import start
    lua, ns = start()
    assert lua.eval("rawget(_G, 'AzerothGPS_WorldGridTiles')") is None
    assert next(iter(ns.WorldGrid.conts.items()), None) is None
    # (the headers alone: under 2 KB a continent)
    for c in (0, 1, 2991):
        assert DATA[c].stat().st_size < 2000


def test_a_trip_over_two_continents_loads_only_its_legs_regions_and_tiles():
    # (the planner's two walking legs of a trip from Durotar to Elwynn Forest, a zeppelin between: each leg's search
    # loads the regions its tiles are in and decodes those tiles, never a continent's)
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Router.SYNC_WALKS = True
    ns.settings.gps.worldGrid = True
    try:
        for a, b in ((RAZOR_HILL, SEN_JIN), (GOLDSHIRE, LAKE)):
            r = ns.Router.Route(a[0], a[1], a[2], b[1], b[2], lua.table())
            assert r.worldGrid
    finally:
        ns.settings.gps.worldGrid = False
    got = _loaded(ns)
    assert set(got) == {0, 1}
    for c, (regions, tiles) in got.items():
        assert 1 <= len(regions) <= 4, (c, regions)  # (Durotar's leg is where four regions meet)
        assert 1 <= tiles <= 16, (c, tiles)
    assert ns.WorldGrid.stats.rawBytes < 8e6  # (of the map's ~25 MB)


def test_a_harness_let_go_is_freed_at_once_its_regions_loaded_too():
    # (no cycle through Python: a dead harness waited for Python's cycle collector, which counts Python's objects, not
    # Lua's memory; on CI every test's harness, its grids and searches, piled up to GBs a worker, 2026-11-23)
    import gc
    import weakref

    from azerothgps.gameharness import start

    class Seen:
        pass

    was = gc.isenabled()
    gc.disable()
    try:
        lua, ns = start()
        assert lua.eval("C_AddOns.LoadAddOn")("AzerothGPS_WG1_0_0") is True
        assert lua.eval("C_AddOns.LoadAddOn")("AzerothGPS_WG1_0_0") is not True  # (once)
        seen = Seen()
        lua.globals().AGPS_SEEN = seen
        gone = weakref.ref(seen)
        del lua, ns, seen
        assert gone() is None
    finally:
        if was:
            gc.enable()


def test_the_decoded_tiles_stay_under_their_cap():
    from azerothgps.gameharness import start
    lua, ns = start()
    WG = ns.WorldGrid
    ns.Router.SYNC_WALKS = True
    ns.settings.gps.worldGrid = True
    WG.TILE_CACHE_MB = 0.25
    biggest = 0
    try:
        for a, b in ((RAZOR_HILL, SEN_JIN), (GOLDSHIRE, LAKE), (LOCH_NORTH, TERRACE)):
            WG.routes, WG.order = lua.table(), lua.table()
            r = ns.Router.Route(a[0], a[1], a[2], b[1], b[2], lua.table())
            assert r.worldGrid
            for c in (0, 1):
                cc = WG.conts[c]
                if cc is not None:
                    for _k, t in cc.tiles.items():
                        biggest = max(biggest, t.bytes)
            assert WG.TileBytesKept() <= 0.25 * 1048576 + 2 * biggest
    finally:
        ns.settings.gps.worldGrid = False


# --- the Router's routing considerations on the grid (asked 2026-11-22) ------------------------------------------------

def _costs(lua, ns, cont, a, b, **opts):
    WG = ns.WorldGrid
    c = WG.Cont(cont)
    return c, WG.Costs(c, a[0], a[1], b[0], b[1], lua.table(**opts))


def test_the_other_faction_s_guards_cost_as_the_router_s(game):
    lua, ns = game
    R, st, cdb = ns.Router, ns.settings.gps, ns.CharDB()
    was = (cdb.faction, st.avoidHostile)
    cdb.faction = "Horde"
    st.avoidHostile = True
    st.avoidHighZones = False  # (the guards' alone here)
    st.avoidElites = False  # (... no elite areas either, item 91: test_elite_areas.py)
    try:
        guard = ns.Hostile[0].H  # (the Alliance's guards, dangerous to a Horde player)
        gx, gy = guard[1], guard[2]
        c, x = _costs(lua, ns, 0, (gx + 2000, gy), (gx + 2500, gy))
        assert x.side == "H"
        assert ns.WorldGrid.Extra(x, -1, gx, gy) == R.HOSTILE_FACTOR - 1
        # (a town the leg ends in isn't paid for: Router.HostileTownsNear)
        c, x = _costs(lua, ns, 0, (gx + 2000, gy), (gx, gy))
        assert ns.WorldGrid.Extra(x, -1, gx, gy) == 0
        st.avoidHostile = False
        c, x = _costs(lua, ns, 0, (gx + 2000, gy), (gx + 2500, gy))
        assert x.side is None
    finally:
        cdb.faction, st.avoidHostile = was
        st.avoidHighZones = True
        st.avoidElites = None


def test_an_alliance_walk_goes_round_the_horde_s_guards(game):
    lua, ns = game
    R, st, cdb = ns.Router, ns.settings.gps, ns.CharDB()
    was = (cdb.faction, st.avoidHostile)
    a, b = (1, 150.0, -4700.0, None), (1, 500.0, -4700.0, None)  # (either side of Razor Hill)
    cdb.faction = "Alliance"
    try:
        yards = {}
        for avoid in (True, False):
            st.avoidHostile = avoid
            ns.WorldGrid.routes, ns.WorldGrid.order = lua.table(), lua.table()
            r = _route(lua, ns, a, b)
            assert r.worldGrid
            p = _list(r.pts)
            yards[avoid] = sum(R.HostileYards(1, p[2 * i], p[2 * i + 1], p[2 * i + 2], p[2 * i + 3], "A")
                               for i in range(len(p) // 2 - 1))
        assert yards[True] == 0 and yards[False] > 100, yards  # (straight through the town with the option off)
    finally:
        cdb.faction, st.avoidHostile = was
        ns.WorldGrid.routes, ns.WorldGrid.order = lua.table(), lua.table()


def test_zones_too_high_cost_as_the_router_s_but_the_ends_own(game):
    lua, ns = game
    R, st = ns.Router, ns.settings.gps
    lua.execute("AGPS_LEVEL = 1")
    try:
        c, x = _costs(lua, ns, 0, GOLDSHIRE[1:3], LAKE[1:3])
        assert x.red is not None
        dusk = (-10500.0, -400.0)  # (Duskwood: 18-30)
        assert R.RedZones()[R.ZoneAt(0, *dusk)]
        assert ns.WorldGrid.Extra(x, -1, *dusk) == R.LEVEL_FACTOR - 1
        assert ns.WorldGrid.Extra(x, -2, *GOLDSHIRE[1:3]) == 0
        c, x = _costs(lua, ns, 0, GOLDSHIRE[1:3], dusk)  # (the stop's own zone isn't too high for its trip)
        assert ns.WorldGrid.Extra(x, -1, *dusk) == 0
        st.avoidHighZones = False
        c, x = _costs(lua, ns, 0, GOLDSHIRE[1:3], LAKE[1:3])
        assert x.red is None
    finally:
        st.avoidHighZones = True
        lua.execute("AGPS_LEVEL = nil")


def test_swimming_left_out_costs_as_the_router_s(game):
    lua, ns = game
    P = ns.Passability
    c, x = _costs(lua, ns, 0, GOLDSHIRE[1:3], LAKE[1:3])
    assert x.swim == pytest.approx(ns.WorldGrid.SwimWeight())  # (the player's run over swim speed, about SWIM_COST)
    P.SetAvoidSwim(True)
    try:
        c, x = _costs(lua, ns, 0, GOLDSHIRE[1:3], LAKE[1:3])
        assert x.swim == P.AVOID_SWIM_COST
    finally:
        P.SetAvoidSwim(False)


def test_the_safe_drop_bounds_the_grid_s_drops(game):
    lua, ns = game
    c, x = _costs(lua, ns, 0, GOLDSHIRE[1:3], LAKE[1:3])
    assert x.maxDrop == ns.Nav.SafeDrop()
    c, x = _costs(lua, ns, 0, GOLDSHIRE[1:3], LAKE[1:3], maxDrop=0)
    assert x.maxDrop == 0


def _with_track(lua, ns, **t):
    if ns.db.tracks is None:
        ns.db.tracks = lua.table()
    tracks = ns.db.tracks
    tracks[len(tracks) + 1] = lua.table_from(t)
    return len(tracks)


def test_the_player_s_wall_cuts_the_grid_s_way(game):
    lua, ns = game
    WG, P, R = ns.WorldGrid, ns.Passability, ns.Router
    WG.routes, WG.order = lua.table(), lua.table()
    base = _route(lua, ns, RAZOR_HILL, SEN_JIN)
    assert base.worldGrid
    pts = _list(base.pts)
    m = (len(pts) // 4) * 2
    mx, my = (pts[m] + pts[m + 2]) / 2, (pts[m + 1] + pts[m + 3]) / 2  # (a piece's middle)
    dx, dy = pts[m + 2] - pts[m], pts[m + 3] - pts[m + 1]
    L = math.hypot(dx, dy)
    nx, ny = -dy / L * 80, dx / L * 80  # (across the way there)
    k = _with_track(lua, ns, op="wall", continent=1, pts=lua.table(mx - nx, my - ny, mx + nx, my + ny), time=999999001)
    try:
        P.RefreshWalls()  # (as the road tools do after a wall is drawn)
        R.WallsChanged()
        WG.routes, WG.order = lua.table(), lua.table()
        r = _route(lua, ns, RAZOR_HILL, SEN_JIN)
        assert r.worldGrid
        p2 = _list(r.pts)
        crossing = [i for i in range(len(p2) // 2 - 1)
                    if P.CrossesWall(1, p2[2 * i], p2[2 * i + 1], p2[2 * i + 2], p2[2 * i + 3])]
        assert crossing == []
        # (the first way did, through the wall's middle)
        assert P.CrossesWall(1, pts[m], pts[m + 1], pts[m + 2], pts[m + 3])
    finally:
        ns.db.tracks[k] = None
        P.RefreshWalls()
        R.WallsChanged()
        WG.routes, WG.order = lua.table(), lua.table()


def test_the_player_s_own_road_is_road_ground(game):
    lua, ns = game
    k1 = _with_track(lua, ns, continent=1, pts=lua.table(0.0, -4500.0, 100.0, -4500.0), time=999999002)
    k2 = _with_track(lua, ns, op="remove", continent=1, pts=lua.table(0.0, -4800.0, 100.0, -4800.0), time=999999003)
    try:
        c, x = _costs(lua, ns, 1, RAZOR_HILL[1:3], SEN_JIN[1:3])
        cell = c.cell
        assert x.roadCells[math.floor(50 / cell) * 65536 + math.floor(-4500 / cell)]
        assert x.unroadCells[math.floor(50 / cell) * 65536 + math.floor(-4800 / cell)]
    finally:
        ns.db.tracks[k2] = None
        ns.db.tracks[k1] = None


def _mesh(polys):
    """A small mesh for worldgrid.mesh_walk: polys [(verts [(x, y, z)], neighbors per edge)]."""
    from azerothgps import worldgrid as W
    raw = [(p[0], p[1], 1) for p in polys]
    nbs = [{q for q in p[1] if q >= 0} for p in polys]
    return W._mesh(raw, nbs)


def test_the_mesh_walk_climbs_only_what_the_mesh_joins():
    # (the bake's links, worldgrid.walked_links: a ledge's top and foot are joined only one way down, a drop; a ramp both
    # ways; the 10,000-route test's impossible climbs were links joining a ledge's top and foot round its end)
    from azerothgps import worldgrid as W
    # (a ramp: two joined polys rising 3 yd; a ledge: a top 6 yd over a foot it doesn't join)
    ramp = _mesh([([(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)], [-1, 1, -1, -1]),
                  ([(10, 0, 0), (20, 0, 3), (20, 10, 3), (10, 10, 0)], [-1, -1, -1, 0])])
    near = lambda x, y: {0, 1}  # noqa: E731
    assert W.mesh_walk(ramp, near, (5, 5, 0), 0, (15, 5), {1}, 1.5) == W.WALK
    assert W.mesh_walk(ramp, near, (15, 5, 1.5), 1, (5, 5), {0}, 0) == W.WALK
    ledge = _mesh([([(0, 0, 6), (10, 0, 6), (10, 10, 6), (0, 10, 6)], [-1, -1, -1, -1]),
                   ([(10, 0, 0), (20, 0, 0), (20, 10, 0), (10, 10, 0)], [-1, -1, -1, -1])])
    assert W.mesh_walk(ledge, near, (5, 5, 6), 0, (15, 5), {1}, 0) == W.DROP
    assert W.mesh_walk(ledge, near, (15, 5, 0), 1, (5, 5), {0}, 6) is None
    # (the walked links' drops go to DROP_FAR (bake8, Expert jumper: a fall spell makes any height safe; the game takes
    # one only within the player's own safe drop), none past it; a walk's DROP_MAX stays the default)
    for h, want in ((W.DROP_MAX + 20, W.DROP), (W.DROP_FAR + 20, None)):
        cliff = _mesh([([(0, 0, h), (10, 0, h), (10, 10, h), (0, 10, h)], [-1, -1, -1, -1]),
                       ([(10, 0, 0), (20, 0, 0), (20, 10, 0), (10, 10, 0)], [-1, -1, -1, -1])])
        assert W.mesh_walk(cliff, near, (5, 5, h), 0, (15, 5), {1}, 0, W.DROP_FAR) == want
    assert W.mesh_walk(cliff, near, (5, 5, W.DROP_MAX + 20), 0, (15, 5), {1}, 0) is None
    assert W.DROP_MAX < W.DROP_FAR <= 400  # (FallSpells.lua's DROP_CAP: the most any spell's drop is taken as safe for)


def test_the_mesh_walk_arrives_only_on_its_floor_not_on_a_corner_another_piece_of_the_mesh_shares():
    # (bake8, Gurubashi Arena: the Battle Ring's floor and the ground outside its wall are two pieces of the mesh
    # touching at a corner, about level; a link's walk ending on that corner from the outside piece counted as arrived
    # by the height alone, and the ring was walked into through its wall)
    from azerothgps import worldgrid as W
    near = lambda x, y: {0, 1, 2}  # noqa: E731
    apart = _mesh([([(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)], [-1, -1, -1, -1]),
                   ([(10, 10, 0), (20, 10, 0), (20, 20, 0), (10, 20, 0)], [-1, -1, -1, -1])])
    assert W.mesh_walk(apart, near, (5, 5, 0), 0, (10, 10), {1}, 0) is None
    # (joined by a poly between them across edges: arrived, a neighbor's within HOPS)
    joined = _mesh([([(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)], [-1, 2, -1, -1]),
                    ([(10, 10, 0), (20, 10, 0), (20, 20, 0), (10, 20, 0)], [2, -1, -1, -1]),
                    ([(10, 0, 0), (20, 0, 0), (20, 10, 0), (10, 10, 0)], [-1, -1, 1, 0])])
    assert W.mesh_walk(joined, near, (5, 5, 0), 0, (10, 10), {1}, 0) == W.WALK


def test_the_grid_s_drops_are_one_way_and_within_the_bake_s_drop(game):
    from azerothgps import worldgrid as W
    lua, ns = game
    WG = ns.WorldGrid
    c = WG.Cont(1)
    key = 32 * 64 + 41  # (a Durotar tile)
    t = WG.Tile(c, key)
    assert t
    ups = drops = 0
    for ci in range(c.per * c.per):
        n = WG.Count(t, ci)
        if not n:
            continue
        f = WG.First(t, ci)
        for s in range(f, f + n):
            zs = WG.Z(c, t, s)
            for d in range(1, 9):
                kk = WG.Link(t, s, d)
                nkey, nci = WG.Step(c, key, ci, d)
                if kk == 0 or nkey != key:
                    continue
                s2 = WG.First(t, nci) + kk - 1
                dz = WG.Z(c, t, s2) - zs
                if WG.Drop(t, s, ci, d, t, s2, dz):
                    drops += 1
                    assert -dz <= W.DROP_FAR + 1
                elif dz >= WG.DROP_Z:
                    ups += 1
    assert ups > 0


# --- a player walking on while the grid works a leg out (Kooki3z 2026-11-22 in game: "Working out the route..." for
# good, and the addon's memory past 500 MB): keyed on the exact yard, each step started a new search and each finished
# one re-planned the trip, and a stop the grid couldn't reach flooded 600,000 nodes before giving up

def test_a_walking_player_s_leg_is_searched_once_and_joined_onto():
    from azerothgps.gameharness import start
    lua, ns = start()
    R, WG = ns.Router, ns.WorldGrid
    R.SYNC_WALKS = False
    ns.settings.gps.worldGrid = True
    kb = lua.eval("function() collectgarbage('collect') collectgarbage('collect') return collectgarbage('count') end")
    base = kb()
    try:
        a, b = GOLDSHIRE, (0, -9100.0, -700.0, None)
        x, y = a[1], a[2]
        for step in range(40):  # (7 yd a step along it, the leg asked again each time as Nav does, its search pumped)
            r = R.Route(0, x, y, b[1], b[2], lua.table())
            assert r and r.pts and len(r.pts) >= 4  # (the Router's own meanwhile, drawn: never nothing)
            assert WG.jobCount <= WG.MAX_JOBS
            for _ in range(20):
                if not R.HasWork():
                    break
                R.Pump(1e18, lua.eval("function() return 0 end"))
            # (on along the route drawn: 7 yd toward its next point)
            p = _list(r.pts)
            k = 2
            while k < len(p) - 2 and math.dist((x, y), (p[k], p[k + 1])) < 1:
                k += 2
            d = math.dist((x, y), (p[k], p[k + 1])) or 1
            x, y = x + (p[k] - x) / d * min(7, d), y + (p[k + 1] - y) / d * min(7, d)
        assert WG.stats.pending <= 3, WG.stats.pending  # (searched once, maybe again; not once a step)
        r = R.Route(0, x, y, b[1], b[2], lua.table())
        assert r.worldGrid and not r.pending
        assert (kb() - base) / 1024 < 40  # (MB: the regions loaded, the tiles kept, the routes)
    finally:
        R.SYNC_WALKS = True
        ns.settings.gps.worldGrid = False


def test_a_leg_waits_only_on_a_search_to_its_stop_from_near_its_start():
    # (a search to the same stop from within WG.REUSE_YD is waited for, the player having moved on a few yards; one from
    # further away is another leg, a plan's: its own search, as many as WG.MAX_JOBS. 2026-11-23: from the sand south of
    # Gadgetzan the walk to Uldum's entrance waited 4 s on a plan's leg there from Steamwheedle Port)
    from azerothgps.gameharness import start
    lua, ns = start()
    R, WG = ns.Router, ns.WorldGrid
    R.SYNC_WALKS = False
    ns.settings.gps.worldGrid = True
    b = SEN_JIN
    try:
        def ask(x, y):
            return R.Route(1, x, y, b[1], b[2], lua.table())
        a = (RAZOR_HILL[1], RAZOR_HILL[2])
        assert ask(*a).pending and WG.jobCount == 1
        assert ask(a[0] + 30, a[1] + 30).pending and WG.jobCount == 1  # (from 42 yd off: waited for)
        far = (a[0] + 150, a[1] - 300)  # (335 yd off: a leg of its own)
        assert ask(*far).pending and WG.jobCount == 2
        keys = [str(j.sx) + "," + str(j.sy) for j in WG.jobs.values()]
        assert len(keys) == 2
        assert ask(a[0] - 250, a[1] + 150).pending and WG.jobCount == WG.MAX_JOBS  # (no more than MAX_JOBS at once)
        for _ in range(100000):
            if not R.HasWork():
                break
            R.Pump(1e18, lua.eval("function() return 0 end"))
        r = ask(*far)
        assert r.worldGrid and not r.pending  # (its own search, found)
    finally:
        R.SYNC_WALKS = True
        ns.settings.gps.worldGrid = False


def test_a_long_leg_over_dun_morogh_s_mountains_is_legal_and_within_its_budget(game):
    # (no way on the grid here before falls over empty cells (WorldGrid.FarDrops, from 8 yd since 2026-11-24). Now a
    # 3.5k yd way over the mountains, down by slopes: fine by Kooki3z's drop rules (the coordinator, 2026-11-24) as long
    # as every drop is within the player's drop limit and it crosses no wall; the search within its node budget)
    lua, ns = game
    WG, R, P = ns.WorldGrid, ns.Router, ns.Passability
    a, b = (0, -5600.0, -500.0, None), (0, -6100.0, -1500.0, None)
    WG.routes, WG.order = lua.table(), lua.table()
    r = _route(lua, ns, a, b)
    far = math.dist(a[1:3], b[1:3])
    assert WG.lastNodes <= WG.NODES_BASE + WG.NODES_PER_YD * (far + 60) + 1
    if r.noWay:
        assert r.gridGap
        return
    k, z, p = _list(r.kinds), _list(r.fz), _list(r.pts)
    for i, kk in enumerate(k):
        if kk == R.KIND_DROP:
            assert z[i] - z[i + 1] <= ns.Nav.SafeDrop() + 0.5, (i, z[i], z[i + 1])
        assert not P.CrossesWall(0, p[2 * i], p[2 * i + 1], p[2 * i + 2], p[2 * i + 3]), i


# --- Nethergarde Keep (Kooki3z 2026-11-22 in game, Road tolerance -10): to Bernie Heisten in the keep's building and on
# out of it. The way out zig-zagged along the building (a chain of a road's short links, each back to its cell's point)
# and -10 kept no more to the roads than 0

BERNIE = (0, -10946.6, -3369.3, 66.6)
NETHER_WEST = (0, -10991.0, -3224.0, None)
NETHER_SOUTH = (0, -11250.0, -3550.0, None)  # (on the road south of the keep: (-11170, -3500) is on its walls since the bake keeps roads on their own surfaces)


def _sharp_turns(r):
    p = _list(r.pts)
    n = 0
    for i in range(1, len(p) // 2 - 1):
        ax, ay = p[2 * i] - p[2 * i - 2], p[2 * i + 1] - p[2 * i - 1]
        bx, by = p[2 * i + 2] - p[2 * i], p[2 * i + 3] - p[2 * i + 1]
        la, lb = math.hypot(ax, ay), math.hypot(bx, by)
        if la and lb and (ax * bx + ay * by) / (la * lb) < 0.5:
            n += 1
    return n


def _road_share(r):
    p, k = _list(r.pts), _list(r.kinds)
    road = sum(math.dist(p[2 * i:2 * i + 2], p[2 * i + 2:2 * i + 4]) for i, kk in enumerate(k) if kk == 0)
    return road / max(r.length, 1)


def test_nethergarde_keep_s_ways_in_and_out_don_t_zig_zag(game):
    lua, ns = game
    st = ns.settings.gps
    was = st.roadTolerance
    try:
        st.roadTolerance = -10
        ns.WorldGrid.routes, ns.WorldGrid.order = lua.table(), lua.table()
        into = _route(lua, ns, NETHER_WEST, BERNIE)
        out = _route(lua, ns, NETHER_WEST, NETHER_SOUTH)  # (by the keep's building; from inside it the grid has no way
        # since the bake's road-link height check: the Router's own, through its door)
        assert into.worldGrid and out.worldGrid
        assert _sharp_turns(into) <= 4, _sharp_turns(into)  # (7 before)
        assert _sharp_turns(out) <= 12, _sharp_turns(out)  # (19 before)
        assert abs(_list(into.fz)[-1] - BERNIE[3]) < 3  # (on his floor)
    finally:
        st.roadTolerance = was


def test_road_tolerance_minus_ten_keeps_to_the_roads_on_the_grid(game):
    lua, ns = game
    st, WG = ns.settings.gps, ns.WorldGrid
    was = st.roadTolerance
    try:
        shares = {}
        for t in (0, -10):
            st.roadTolerance = t
            WG.routes, WG.order = lua.table(), lua.table()
            r = _route(lua, ns, NETHER_WEST, NETHER_SOUTH)
            shares[t] = _road_share(r) * r.length  # (its yards on roads: -10 goes 300 yd round for them since the
            # rebake of 2026-11-23, so a share of the longer way says less)
            c = WG.Cont(0)
            x = WG.Costs(c, 0, 0, 1, 1, lua.table())
            if t == -10:
                # (a yard of road ground never cheaper than ROAD_PRICE_MIN of one off it: item 83, Kooki3z at -10 in the
                # Barrens, the road's yard a sixth of one took the route past the stop and back, twice the open way)
                assert abs(x.road - WG.ROAD_PRICE_MIN) < 1e-9
        # (still about as much on the roads: within 5%, item 57's merges shaped on each way, 157 yd to 160)
        assert shares[-10] >= 0.95 * shares[0], shares
    finally:
        st.roadTolerance = was


# --- straightening (Kooki3z 2026-11-22: "Straighten out lines when this happens": a line along a building's wall
# stepping cell by cell). WG.Straighten: any-angle pieces the grid walks straight (WG.Clear: checked every yard, a body's
# width off cell sides with no link, on one floor), then near-collinear points dropped

GOLDSHIRE_INN = ((0, -9400.0, -50.0, None), (0, -9490.0, 120.0, None))


def _turns(r, cos=0.95):
    p = _list(r.pts)
    n = 0
    for i in range(1, len(p) // 2 - 1):
        ax, ay = p[2 * i] - p[2 * i - 2], p[2 * i + 1] - p[2 * i - 1]
        bx, by = p[2 * i + 2] - p[2 * i], p[2 * i + 3] - p[2 * i + 1]
        la, lb = math.hypot(ax, ay), math.hypot(bx, by)
        if la and lb and (ax * bx + ay * by) / (la * lb) < cos:
            n += 1
    return n


@pytest.mark.parametrize("a, b, most", [(NETHER_WEST, NETHER_SOUTH, 28), (GOLDSHIRE_INN[0], GOLDSHIRE_INN[1], 8)])
def test_a_walk_beside_a_building_is_straightened(game, a, b, most):
    lua, ns = game
    WG, st = ns.WorldGrid, ns.settings.gps
    was = (WG.STRAIGHT_TRIES, WG.COLLINEAR_DEG, st.roadTolerance, WG.SNAP_MIN_YD)
    st.roadTolerance = 3
    WG.SNAP_MIN_YD = 1e9  # (the straightening alone: no merges onto roads shaped after it, item 57's)
    try:
        got = {}
        for on in (False, True):
            WG.STRAIGHT_TRIES, WG.COLLINEAR_DEG = (was[0], was[1]) if on else (0, 0)
            WG.routes, WG.order = lua.table(), lua.table()
            got[on] = _route(lua, ns, a, b)
            assert got[on].worldGrid
        assert _turns(got[True]) <= most, _turns(got[True])  # (32 and 11 turns before)
        assert len(got[True].pts) <= 0.8 * len(got[False].pts)
        assert got[True].length <= got[False].length + 1  # (never longer: straighter)
        # (every piece it made straighter is one the grid walks: no more pieces off it than before)
        c = WG.Cont(a[0])

        def unclear(r):
            p, h = _list(r.pts), _list(r.fz)
            return sum(1 for i in range(len(p) // 2 - 1)
                       if not WG.Clear(c, p[2 * i], p[2 * i + 1], h[i], p[2 * i + 2], p[2 * i + 3], h[i + 1]))
        assert unclear(got[True]) <= unclear(got[False])
    finally:
        WG.STRAIGHT_TRIES, WG.COLLINEAR_DEG, st.roadTolerance, WG.SNAP_MIN_YD = was


# --- the player's swim speed (Kooki3z 2026-11-22: "yes use my current swim speed in the grid too")

def test_the_grid_s_swim_weight_is_the_player_s_run_over_swim_speed(game):
    lua, ns = game
    WG = ns.WorldGrid
    old = lua.eval("GetUnitSpeed")
    try:
        lua.execute("GetUnitSpeed = function() return 0, 7, 7, 4.72 end")
        ns.Nav.Speeds()
        slow, k1 = WG.SwimWeight(), WG.CostKey()
        assert slow == pytest.approx(7 / 4.72)
        lua.execute("GetUnitSpeed = function() return 0, 7, 7, 7 end")  # (a swim speed item: as fast as running)
        ns.Nav.Speeds()
        # (never under SWIM_MIN without water walking, item 62: a yard swum never as cheap as one walked)
        assert WG.SwimWeight() == WG.SWIM_MIN and WG.CostKey() != k1  # (a changed speed: the legs searched again)
        c, x = _costs(lua, ns, 0, GOLDSHIRE[1:3], LAKE[1:3])
        assert x.swim == WG.SWIM_MIN
        lua.execute("GetUnitSpeed = function() return 0, 7, 7, 1 end")
        ns.Nav.Speeds()
        assert WG.SwimWeight() == WG.SWIM_MAX
    finally:
        lua.globals().GetUnitSpeed = old
        ns.Nav.Speeds()


# --- Orgrimmar's Valley of Honor (Kooki3z 2026-11-22: the route cut over the raised ground beside the street, and "doesn't
# seem to calculate if its opposing faction territory?"): the city grid prices what the world grid does (WG.Costs) and
# keeps to its streets as the Road tolerance says

def _street_share(ns, c, r):
    CG = ns.CityGrid
    st = CG.Streets(c)
    p = _list(r.pts)
    n = on = 0
    for i in range(len(p) // 2 - 1):
        L = math.dist(p[2 * i:2 * i + 2], p[2 * i + 2:2 * i + 4])
        m = max(1, int(L))
        for q in range(m):
            x = p[2 * i] + (p[2 * i + 2] - p[2 * i]) * q / m
            y = p[2 * i + 1] + (p[2 * i + 3] - p[2 * i + 1]) * q / m
            n += 1
            ci = CG.CellAt(c, x, y)
            if ci is not None and st[ci]:
                on += 1
    return on / max(n, 1)


def test_the_city_grid_keeps_to_its_streets_as_the_road_tolerance_says(game):
    lua, ns = game
    CG, st = ns.CityGrid, ns.settings.gps
    c = CG.City("Orgrimmar")
    a, b = (1, 2038.2, -4672.6, 25.2), (1, 2085.0, -4623.8, 58.7)  # (the Orphan Matron to Xor'juul, up the valley)
    was = st.roadTolerance
    try:
        share = {}
        for t in (10, -10):
            st.roadTolerance = t
            CG.routes, CG.order = lua.table(), lua.table()
            r = _route(lua, ns, a, b)
            assert r.cityGrid == "Orgrimmar"
            share[t] = _street_share(ns, c, r)
        assert share[-10] > share[10] + 0.3, share  # (0.26 and 0.79)
    finally:
        st.roadTolerance = was
        CG.routes, CG.order = lua.table(), lua.table()


def test_the_city_grid_prices_the_other_faction_as_the_world_grid(game):
    lua, ns = game
    CG, R, cdb, st = ns.CityGrid, ns.Router, ns.CharDB(), ns.settings.gps
    was = (cdb.faction, st.avoidHostile)
    cdb.faction = "Alliance"
    st.avoidHostile = True
    st.avoidElites = False  # (the guards' alone, item 91)
    try:
        c = CG.City("Orgrimmar")
        x = CG.Costs(c, 2038.2, -4672.6, 2085.0, -4623.8)
        assert x.side == "A" and x.any and x.streets
        # (one of the lighter NPCs there, dangerous to an Alliance player: dearer, as the Router's walks price it)
        light = ns.Hostile[1].a
        for i in range(1, len(light) + 1, 3):
            lx, ly = light[i], light[i + 1]
            if CG.CellAt(c, lx, ly) is not None and min(math.dist((lx, ly), (2038.2, -4672.6)),
                                                         math.dist((lx, ly), (2085.0, -4623.8))) > R.LIGHT_END_YD + 5:
                assert ns.WorldGrid.Extra(x, -7, lx, ly) >= R.HOSTILE_LIGHT_FACTOR - 1
                break
        else:
            pytest.skip("no lighter NPC in Orgrimmar's grid")
    finally:
        cdb.faction, st.avoidHostile = was
        st.avoidElites = None


# --- never through guards today's routing goes round (Kooki3z 2026-11-22, an Alliance player in Mulgore: the grid's way
# went through Bloodhoof Village and over Thunder Bluff's mesas, and nothing was asked)

# --- Thousand Needles below Darkcloud Pinnacle (Kooki3z 2026-11-22: "thinks I can get to that bridge, impossible to do
# this route"): a road along a mesa's edge went from the canyon's floor to the mesa's top cell by cell and its links
# joined them, a climb of 100 yd in a yard. The bake keeps a road on its own surface and refuses a link climbing more
# than its road can (worldbake.ROAD_LINK_DZ, ROAD_LINK_SLOPE)

NEEDLES_FLOOR = (1, -4800.0, -1978.0, None)  # (map 35.1, 28.4)
NEEDLES_TOP = (1, -4742.5, -2103.0, 83.7)  # (Lakota Windsong, up on the mesa)


CELL_YD = 8.333333  # (the grid's cell: its heights are known a cell apart, never closer)


def _climbs(r, most=6.0, near=6.0):
    p, h, k = _list(r.pts), _list(r.fz), _list(r.kinds)
    bad = []
    for i in range(len(p) // 2 - 1):
        d = math.dist(p[2 * i:2 * i + 2], p[2 * i + 2:2 * i + 4])
        dz = h[i + 1] - h[i]
        # (over a cell at least: the pulled line puts two neighbor cells' heights where it crosses their side, maybe a
        # yard apart, and a 47-degree slope the mesh walks then read as a wall; Thousand Needles, 2026-11-23)
        if k[i] != 4 and dz > most + max(d, CELL_YD) * 1.43 and d <= near * 10:
            bad.append((round(p[2 * i]), round(p[2 * i + 1]), round(h[i]), round(h[i + 1]), round(d)))
    return bad


class _Seq:
    def __init__(self, v):
        self.v = v

    def __len__(self):
        return len(self.v)

    def __getitem__(self, i):  # (1-based, as a Lua table)
        return self.v[i - 1]


def _fake_route(steps):
    """A route of (yards along x, height) points, every piece a walk (kind 1)."""
    import types
    pts, fz = [], []
    for x, z in steps:
        pts += [x, 0.0]
        fz.append(z)
    return types.SimpleNamespace(pts=_Seq(pts), fz=_Seq(fz), kinds=_Seq([1] * (len(steps) - 1)))


def test_climbs_are_judged_over_a_cell_at_least():
    # (a 47-degree slope between two neighbor cells, 8.9 yd up, drawn where the line crosses their side 0.9 yd apart:
    # the mesh walks it)
    assert _climbs(_fake_route([(0, -41.3), (0.9, -32.4), (20, -36)])) == []
    # (a step far past any slope between neighbor cells, 25 yd up: still a climb)
    assert len(_climbs(_fake_route([(0, 0), (0.9, 25), (20, 25)]))) == 1
    # (a mesa's 100 yd edge, and Thousand Needles' 299 yd up the cliff, as before)
    assert len(_climbs(_fake_route([(0, -50), (1, 50)]))) == 1
    assert len(_climbs(_fake_route([(0, -54), (50, 245)]))) == 1


def test_from_the_canyon_floor_the_mesa_is_reached_by_its_own_way_up(game):
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    r = _route(lua, ns, NEEDLES_FLOOR, NEEDLES_TOP)
    if r.worldGrid:
        assert _climbs(r) == []  # (no step up steeper than a walk's: never the cliff)
    assert r.length > 1000  # (the way up is far round: 299 yd up the cliff before)


def test_from_the_mesa_down_a_drop_is_within_the_safe_drop(game):
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    r = _route(lua, ns, NEEDLES_TOP, NEEDLES_FLOOR)
    p, h, k = _list(r.pts), _list(r.fz) if r.fz is not None else None, _list(r.kinds)
    if r.worldGrid and h:
        safe = ns.Nav.SafeDrop()
        for i, kk in enumerate(k):
            if kk == 4:
                assert h[i] - h[i + 1] <= safe + 1
        assert _climbs(r) == []


def test_to_bernie_heisten_from_outside_the_keep_s_building_never_through_its_wall(game):
    # (Kooki3z 2026-11-22, the player outside south-west of the building (map 63.8, 18.0): a straight line through its
    # wall. The start's cell had two pieces of floor at the ground's height a fence apart; the one taken was shut in,
    # the grid found no way, and the Router's own was its straight walk. Both are starts now: in by the door)
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    a = (0, -11014.0, -3358.0, None)
    r = _route(lua, ns, a, BERNIE)
    assert r.worldGrid
    p = _list(r.pts)
    assert len(p) // 2 > 2 and r.length > math.dist(a[1:3], BERNIE[1:3]) * 1.2
    assert abs(_list(r.fz)[-1] - BERNIE[3]) < 3


NETHER_SPOTS = [(0, -11041.0, -3353.0, None), (0, -11025.0, -3356.0, None), (0, -11014.0, -3358.0, None)]


@pytest.mark.parametrize("a", NETHER_SPOTS)
def test_into_the_keep_s_building_never_a_straight_line(game, a):
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    r = _route(lua, ns, a, BERNIE)
    assert r.noWay or (len(r.pts) // 2 > 2 and r.length > math.dist(a[1:3], BERNIE[1:3]) * 1.2)


def test_with_no_way_on_the_grid_a_straight_line_through_walls_is_no_way(game):
    # (Kooki3z's rule: never a straight line route through walls. The grid made to find nothing: no way, logged as a
    # gap, for the keep and for an open-ground leg alike; never the Router's own, Kooki3z 2026-11-23)
    lua, ns = game
    WG = ns.WorldGrid
    was = WG.Search
    WG.Search = lua.eval("function() return nil end")
    try:
        WG.routes, WG.order = lua.table(), lua.table()
        r = _route(lua, ns, NETHER_SPOTS[2], BERNIE)
        assert r.noWay and r.gridGap
        WG.routes, WG.order = lua.table(), lua.table()
        r = _route(lua, ns, RAZOR_HILL, SEN_JIN)
        assert r.noWay and r.gridGap
    finally:
        WG.Search = was
        WG.routes, WG.order = lua.table(), lua.table()


@pytest.mark.parametrize("a, b", [
    ((0, -14444.0, 434.0, 4.0), (0, -14459.0, 503.0, 26.0)),  # (Booty Bay: Wigcik on the dock to Deeg up the walkways)
    ((0, -4964.0, -1014.0, 504.0), (0, -5033.0, -1139.0, 505.0)),  # (Ironforge: Pithwick to Dolkin Craghelm)
    ((1, -3616.0, -4475.0, 14.0), (1, -3750.0, -4454.0, 65.0)),  # (Theramore: the inn's bartender to Jaina's tower)
])
def test_in_a_town_the_grid_walks_to_the_stop_itself_no_router_walk_stands_in(game, a, b):
    # (bake6's 10,000 routes: 37 short trips in towns said "No way there found", the grid's cells missing the walkways,
    # stairs and doors. #952's stopgap let the Router's own walk stand there; bake8 takes it out (Kooki3z 2026-11-23:
    # "fall back can't be trusted ... just correct it"): the bake's stop links (worldbake.stop_links) and the city grid's
    # halls (WG.CityWalk) walk them, `agps world-grid coverage` lists any left)
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    r = _route(lua, ns, a, b)
    assert not r.noWay and (r.worldGrid or r.cityGrid) and len(r.pts) >= 4
    assert r.length < 4 * math.dist(a[1:3], b[1:3])
    fz = _list(r.fz)
    assert fz and abs(fz[-1] - b[3]) <= 6  # (on the stop's own floor, not at the foot of its building)


def test_the_town_stopgap_is_gone_where_the_grid_has_no_way_the_router_s_walk_through_a_building_is_no_way(game):
    # (#952's WG.RouterClosed kept the Router's own straight walk where its own ground was open, though the grid had
    # no way: the walls of a building or an arena the Router's data lacks. Now any short leg's straight piece the grid
    # can't walk is "No way there found")
    lua, ns = game
    WG = ns.WorldGrid
    assert WG.RouterClosed is None
    was = WG.Search
    WG.Search = lua.eval("function() return nil end")
    try:
        WG.routes, WG.order = lua.table(), lua.table()
        # (the world grid's own: Booty Bay's walkways are a building's grid since 1.4.2, BuildingGrid.lua)
        ns.settings.gps.buildingGrid = False
        try:
            r = _route(lua, ns, (0, -14444.0, 434.0, 4.0), (0, -14459.0, 503.0, 26.0))  # (Booty Bay's walkways)
        finally:
            ns.settings.gps.buildingGrid = True
        assert r.noWay and r.gridGap
    finally:
        WG.Search = was
        WG.routes, WG.order = lua.table(), lua.table()


def test_a_long_walk_the_grid_has_no_way_for_is_no_way_never_the_router_s_own(game):
    # (Kooki3z 2026-11-23: "we have to get rid of the fallback option": a long leg the grid finds no way for is no way,
    # logged as a gap for the data, never the Router's own)
    lua, ns = game
    WG = ns.WorldGrid
    was = WG.Search
    WG.Search = lua.eval("function() return nil end")
    try:
        for a, b in (((0, -5600.0, -500.0, None), (0, -5380.0, -2950.0, None)),
                     ((0, -5023.0, -829.0, None), (0, -5250.0, -3150.0, None))):
            WG.routes, WG.order = lua.table(), lua.table()
            r = _route(lua, ns, a, b)
            assert r.noWay and r.gridGap
    finally:
        WG.Search = was
        WG.routes, WG.order = lua.table(), lua.table()


@pytest.mark.parametrize("b", [(0, -4900.0, -3400.0, None), (0, -5000.0, -3100.0, None), (0, -4800.0, -3500.0, None)])
def test_from_ironforge_s_gate_to_loch_modan_s_north_east_shore(game, b):
    # (Kooki3z 2026-11-22: Ironforge to a stop north-east of Loch Modan's lake took the tram and walked round by
    # Redridge: the grid found no way in the corridor round the Router's own route up those hills; searched again in a
    # wider one, CORRIDOR_WIDE_YD)
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    a = (0, -5023.0, -829.0, None)
    r = _route(lua, ns, a, b)
    assert r.worldGrid and not r.noWay and r.length < 6000


@pytest.mark.parametrize("b", [(-4444.0, -2622.0), (-4424.0, -2476.0), (-4130.0, -2463.0), (-4000.0, -2700.0)])
def test_from_loch_modan_through_dun_algaz_into_the_wetlands_on_the_grid(game, b):
    # (2026-11-22: the grid reached the Wetlands only to (-4450, -2684). North of the tunnel the gorge runs under an
    # overhang; its land roads, with no heights, started on the mountain top's surfaces (the terrain's height there), so
    # the gorge floor wasn't road ground and its 3 yd step under the gate got no road link. worldbake.road_floors)
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    ns.settings.gps.worldGrid = True
    try:
        r = WG.Walk(WG.Cont(0), -4950, -2750, None, b[0], b[1], None, lua.table())
    finally:
        ns.settings.gps.worldGrid = False
    assert r and r.length < 2 * math.dist((-4950, -2750), b) + 400


def test_from_ironforge_s_gate_to_the_wetlands_through_dun_algaz(game):
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    a, b = (0, -5023.0, -829.0, None), (0, -4000.0, -2700.0, None)
    r = _route(lua, ns, a, b)
    assert r.worldGrid and not r.noWay
    p = _list(r.pts)
    xy = [(p[2 * i], p[2 * i + 1]) for i in range(len(p) // 2)]
    # (through the gorge north of the tunnel, not round by the coast or a straight line over the mountains)
    def near(q, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / ((dx * dx + dy * dy) or 1)))
        return math.dist(q, (a[0] + dx * t, a[1] + dy * t))
    assert any(near((-4440.0, -2590.0), xy[i], xy[i + 1]) < 30 for i in range(len(xy) - 1)), xy
    assert r.length < 1.25 * _route(lua, ns, a, b, on=False).length


# --- the two caves north of Dun Algaz (Kooki3z 2026-11-22 in game, the Wetlands' map at 50.6, 71.1: "routing is sending
# me off the edge, should follow red here, I connected the 2 caves for you by color"). The green cave runs from by Dun
# Algaz north to a mouth under the mountain (GREEN_N); the orange one from its west mouth (ORANGE_W), a little north-west
# of there, through the mountain to the east mouth (ORANGE_E) over the Wetlands' plain. Between them the way is the drawn
# road north and round to ORANGE_W, not east from GREEN_N off the ledge (115 yd down) to ORANGE_E. The orange tunnel's
# road links were refused as climbs (a ramp's 4 yd counted over the road's yard, not its surfaces' 8: ROAD_LINK_SPAN_SLOPE),
# and the grid had no way into the Wetlands' east: the Router's own line off the ledge.

GREEN_S, GREEN_N = (0, -4318.0, -2443.0, None), (0, -4106.0, -2471.0, None)
ORANGE_W, ORANGE_E = (-4089.0, -2411.0), (-4086.0, -2631.0)
PAST_ORANGE = (0, -4082.0, -2761.0, None)  # (the stop east of the orange cave's east mouth, as in the screenshot)


def _near(q, xy):
    best = math.inf
    for (ax, ay), (bx, by) in zip(xy, xy[1:]):
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((q[0] - ax) * dx + (q[1] - ay) * dy) / ((dx * dx + dy * dy) or 1)))
        best = min(best, math.dist(q, (ax + dx * t, ay + dy * t)))
    return best


@pytest.mark.parametrize("a", [GREEN_N, GREEN_S])
def test_the_caves_north_of_dun_algaz_the_red_way_not_off_the_ledge(game, a):
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    r = _route(lua, ns, a, PAST_ORANGE)
    assert r.worldGrid and not r.noWay
    p = _list(r.pts)
    xy = [(p[2 * i], p[2 * i + 1]) for i in range(len(p) // 2)]
    assert _near(ORANGE_W, xy) < 20, xy  # (in by the orange cave's west mouth)
    assert _near((-4089.0, -2540.0), xy) < 10, xy  # (through its tunnel)
    assert _near(ORANGE_E, xy) < 10, xy
    # (never a piece from by the green cave's north mouth straight to the orange's east: off the ledge)
    assert not any(math.dist(u, GREEN_N[1:3]) < 40 and math.dist(v, ORANGE_E) < 60 for u, v in zip(xy, xy[1:])), xy


@pytest.mark.parametrize("on", [False, True])
def test_from_the_ruins_of_lordaeron_s_gate_to_undercity_s_rogues_through_the_courtyard(on):
    # (Kooki3z 2026-11-22: the world grid's way to the lifts went round the ruins' east side: Undercity's model, the
    # ruins up top with it, isn't in the grid's meshes. The ruins are the Router's own, WG.NOT_MESHED; the same with the
    # grids off)
    from azerothgps.gameharness import start
    lua, ns = start()
    N = ns.Nav
    lua.execute('UnitFactionGroup = function() return "Horde", "Horde" end; AGPS_LEVEL = 60')
    ns.CharDB().faction = "Horde"
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 1900.0, 240.0, 0")
    ns.settings.gps.worldGrid = on
    try:
        N.SetStops(lua.eval("{ { x = 1416.6, y = 68.7, cont = 10001, z = -62.2, name = 'Carolyn Ward' } }"), False, "red")
        N.Invalidate(True, True)
        ns.GPS.Follow()
        for _ in range(6):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            ns.GPS.Update()
        r = N.route
        assert r
        part = next(p for p in r.parts.values() if p.cont == 0)
        p = _list(part.pts)
        ys = [p[2 * i + 1] for i in range(len(p) // 2) if 1650 < p[2 * i] < 1850]
        assert ys and min(ys) > 200 and max(ys) < 280, ys  # (through the courtyard, not round the east side)
    finally:
        ns.settings.gps.worldGrid = False


# --- the open world's lifts (Kooki3z 2026-11-22: "freewind post lift seems to be ignored, its a must for passage to
# freewind post"): the Router's lift roads (source 5) are the grid's lift links (worldbake._lift_link), joined at the
# cars' stops' floors (lifts.py: the CMaNGOS dump's elevators), whatever their heights apart

@pytest.mark.parametrize("a, b, kind", [
    ((1, -5350.0, -2500.0, None), (1, -5407.1, -2419.6, 89.7), 6),  # (below Freewind Post up to Nyse)
    ((1, -5407.1, -2419.6, 89.7), (1, -5350.0, -2500.0, None), 5),  # (and down)
    # (Kooki3z 2026-11-23 at the lift's foot, map 45.3, 46.6: "if lifts are fixed should be this way is valid too and is
    # shorter"; the route went out round the mesa and up its long ramp)
    ((1, -5333.6, -2426.5, None), (1, -5407.1, -2419.6, 89.7), 6),
    ((1, -5407.1, -2419.6, 89.7), (1, -5333.6, -2426.5, None), 5),
    ((1, -4700.0, -1880.0, None), (1, -4602.1, -1835.4, 86.2), 6),  # (the Great Lift up to Grish Longrunner)
    ((1, -4602.1, -1835.4, 86.2), (1, -4700.0, -1880.0, None), 5),  # (and down)
])
def test_the_open_world_s_lifts_are_ridden(game, a, b, kind):
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    r = _route(lua, ns, a, b)
    assert r.worldGrid and kind in _list(r.kinds)
    assert r.length < 600  # (not round by the far ways up: 2.7 km and 3.8 km before)


# (Kooki3z 2026-11-23 at Freewind Post's lift towers: "freewind post still weird": from a tower's top the route rode the
# lift down and up again before the bridge. The cars' shafts (lifts.shafts): (-5399.2, -2504.6) and (-5382.5, -2489.4),
# their stops at -40.5 and 89; the bridge from the towers' tops onto the mesa)
FREEWIND_SHAFTS = [(-5399.2, -2504.6), (-5382.5, -2489.4)]


@pytest.mark.parametrize("shaft", FREEWIND_SHAFTS)
def test_from_a_freewind_lift_tower_s_top_straight_over_the_bridge(game, shaft):
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    r = _route(lua, ns, (1, shaft[0] + 4, shaft[1] + 4, 89.0), (1, -5407.1, -2419.6, 89.7))
    k = _list(r.kinds)
    assert r.worldGrid and 5 not in k and 6 not in k  # (no ride down and up again)
    assert r.length < 130


# (and Freewind Post's east car, 2026-11-23: from its foot the route climbed the tower as a road link (kind 0), with a
# ~25 yd zigzag over the foot's road ground to it, and the same on the top: Kooki3z's recorded walk rode the car up with
# Record on, and its 130 yd step was a walk link up and a drop down (worldbake.mark_recorded: a ride now, kind lift).
# The east car is boarded from the ground south of it (his walk: about 5 yd under the car's stop), the west car from its
# platform up the stairs)
FREEWIND_BRIDGE = (1, -5407.1, -2419.6, 89.7)
FREEWIND_FEET = [  # (a foot, the shaft whose car it rides)
    ((1, -5376.5, -2483.4, -40.0), FREEWIND_SHAFTS[1]),  # (the west car's platform)
    ((1, -5400.9, -2512.4, -45.5), FREEWIND_SHAFTS[0]),  # (the ground the east car is boarded from)
    ((1, -5393.2, -2498.6, -40.0), None),  # (between the two)
]


def _freewind_ride(r, shaft, up):
    """The route `r` rides a Freewind car (kind 6 up, 5 down; `shaft`'s when given), climbs nowhere else (no piece
    rising or falling 10 yd but the ride) and walks no zigzag to or from it (its yards off the ride at most 1.5 times
    the straight yards between its ends and the ride's, + 10)."""
    k, p, fz = _list(r.kinds), _list(r.pts), _list(r.fz)
    ride = 6 if up else 5
    assert r.worldGrid and ride in k, k
    on = [i for i, kk in enumerate(k) if kk == ride]
    if shaft:
        assert any(math.dist((p[2 * i], p[2 * i + 1]), shaft) < 3 for i in range(on[0], on[-1] + 2)), "another car"
    pts = [(p[2 * i], p[2 * i + 1], fz[i] if i < len(fz) else None) for i in range(len(p) // 2)]
    for i, kk in enumerate(k):
        if kk not in (5, 6) and pts[i][2] is not None and pts[i + 1][2] is not None:
            assert abs(pts[i + 1][2] - pts[i][2]) < 10, ("a climb off the car", pts[i], pts[i + 1], kk)
    for a, b in ((0, on[0]), (on[-1] + 1, len(pts) - 1)):
        yd = sum(math.dist(pts[i][:2], pts[i + 1][:2]) for i in range(a, b))
        assert yd <= 1.5 * math.dist(pts[a][:2], pts[b][:2]) + 10, ("a zigzag", pts[a:b + 1])


@pytest.mark.parametrize("foot,shaft", FREEWIND_FEET)
def test_from_a_freewind_lift_s_foot_up_the_car_then_over_the_bridge(game, foot, shaft):
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    r = _route(lua, ns, foot, FREEWIND_BRIDGE)
    _freewind_ride(r, shaft, True)
    assert r.length < 150


@pytest.mark.parametrize("foot,shaft", FREEWIND_FEET)
def test_from_freewind_s_bridge_down_a_car_to_the_lift_s_foot(game, foot, shaft):
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    r = _route(lua, ns, FREEWIND_BRIDGE, foot)
    _freewind_ride(r, shaft, False)
    assert r.length < 150


# (bake7, 2026-11-23: bake6's 10,000-route test lost 37 short trips in towns where the grid had the NPCs' floors and no
# links between them: each stop's floor is joined along the mesh now (worldbake.stop_links: a building's stairs, a
# walkway's step), and a leg over one city grid's floors that the Router's capital outline leaves out walks that grid
# (WG.CityWalk: Ironforge's halls under the mountain, the world grid's scraps between the capital's cells))
TOWN_TRIPS = [  # (from, to, yards at most)
    ((0, -14446.5, 448.4, 4.1), (0, -14437.8, 384.8, 32.4), 250),  # (Booty Bay: Auctioneer Kresky up to Grarnik Goodstitch)
    ((0, 2254.8, 238.4, 33.7), (0, 2054.6, 241.7, 99.9), 450),  # (Brill: Austil de Mon up the bat tower to Hin Denburg)
    ((1, 217.1, 1283.5, 190.4), (1, 132.2, 1363.8, 199.2), 200),  # (Nijel's Point: Shelgrayn up to Keeper Marandis)
    ((0, -4963.6, -1014.2, 504.0), (0, -5033.0, -1139.4, 505.4), 350),  # (Ironforge: Pithwick to Dolkin Craghelm)
]


@pytest.mark.parametrize("a,b,most", TOWN_TRIPS)
def test_a_town_s_floors_are_walked_on_a_grid(game, a, b, most):
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    r = _route(lua, ns, a, b)
    assert (r.worldGrid or r.cityGrid) and not r.noWay, "not on a grid"
    assert r.length < most


# (Kooki3z 2026-11-23 in Tanaris: from Gadgetzan, and from the sand south of it, to Uldum's entrance the route went west
# by Zul'Farrak and down Un'Goro's rim, or back into town and east to Steamwheedle Port first: "no roads really in this
# zone so its ok to just route across the open without wall collision". Straight over the Abyssal Sands)
ULDUM = (1, -9650.0, -2783.3, None)


@pytest.mark.parametrize("a", [(1, -7139.1, -3752.1, None), (1, -7290.0, -3760.0, None), (1, -7600.0, -3600.0, None)])
def test_from_gadgetzan_to_uldum_straight_over_the_sands(game, a):
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    r = _route(lua, ns, a, ULDUM)
    assert not r.noWay and r.length < 1.3 * math.dist(a[1:3], ULDUM[1:3])
    p = _list(r.pts)
    assert all(-3900 < p[2 * i + 1] < -2600 for i in range(len(p) // 2))  # (never west to Un'Goro or east to the port)


# (Kooki3z 2026-11-23: the grid searched 2.4-3.2 s of CPU, then gave up for the Router's own straight walk: it aimed
# at Uldum's gate's top, 64 and 72 over the sand's 8. Now the floors round a stop with no height at the terrain's height
# are goals too (WG.NearGoals' HIGH_GOAL_Z), and the grid walks it; no Router's own walk in any case)
TANARIS = [(1, -7139.1, -3752.1, None), (1, -7290.0, -3760.0, None)]  # (Gadgetzan; the sand south of it)


# (Kooki3z 2026-11-23, the sand south of Gadgetzan to Uldum's entrance: in the background the route settled on walking
# round by Steamwheedle Port, 4,915 yd, or never settled, the straight walk there (2,572) never landing: the ride check's
# 90 walks between docks and flight masters were queued ahead of it, and it was dropped half searched as the oldest of
# the walks from the player. The ride check and its walks are `low` now, after the route's own searches, and a search
# begun is never dropped for the newer ones. As in the game: the frames' own time and our work in them, the pump's
# budget GPS.PumpBudget's; a CI runner about twice as slow still lands well inside the bound)
@pytest.mark.parametrize("on, seconds", [(True, 90), (False, 300)])
def test_from_the_sand_to_uldum_the_background_lands_the_straight_walk(on, seconds):
    from azerothgps.gameharness import start
    lua, ns = start()
    N, R, G = ns.Nav, ns.Router, ns.GPS
    N.FUN = False
    lua.execute('UnitFactionGroup = function() return "Alliance", "Alliance" end; AGPS_LEVEL = 60')
    ns.CharDB().faction = "Alliance"
    a = TANARIS[1]
    lua.execute(f"AGPS_POS = {{ {a[1]}, {a[2]}, 1 }}")
    R.Route(1, a[1] + 300, a[2] + 300, a[1] + 600, a[2] + 200, lua.table())  # (Kalimdor's roads built first)
    R.WallsChanged()
    ns.settings.gps.worldGrid = on
    R.WARM, R.SYNC_WALKS = True, False
    lua.execute("""
      debugprofilestop = function() return AGPS_T * 1000 + os.clock() * 1000 end
      AGPS_FRAME = function(dt)
        for _, w in ipairs(AGPS_WIDGETS) do
          local f = w._scripts.OnUpdate
          if f and w._shown then f(w, dt) end
        end
      end""")
    frame = lua.eval("AGPS_FRAME")
    try:
        N.SetStops(lua.eval(f"{{ {{ x = {ULDUM[1]}, y = {ULDUM[2]}, cont = 1, name = 'Uldum' }} }}"), False, "red")
        G.Follow()
        t, landed = float(lua.eval("AGPS_T")), None
        for i in range(60 * seconds):
            t += 1 / 60
            lua.execute(f"AGPS_T = {t}")
            frame(1 / 60)
            if N.route is not None and not N.route.pending:
                landed = i
                break
        assert landed is not None, f"no route landed in {seconds} s"
        r = N.route
        assert len(r.legs) == 1 and not r.legs[1].ride, "not the walk straight there"
        assert r.length < 1.3 * math.dist(a[1:3], ULDUM[1:3]), r.length  # (not round by Steamwheedle Port: 4,915 yd)
    finally:
        R.WARM, R.SYNC_WALKS = False, True
        ns.settings.gps.worldGrid = False


# (route-quality 2026-11-23, trip 145 of seed 21, "A10 The Lost Fleet -> Crown Guard Tower": with world routing on, the
# ride check flew to Aerie Peak by its plan's straight lines, its walk on the grid 5,570 yd, not a long way round, and
# never tried Chillwind Camp's, its walk 3,102 yd: 3,170 s against 2,074 with the grid off. The grid's walk counts as
# the roads' does in Nav.WalkLonger: where it goes is the ground, so a walk that long past its line has the next plan
# tried, the best kept)
def test_a10_with_world_routing_flies_to_chillwind_camp_as_without(monkeypatch):
    from azerothgps import routequality as rq
    monkeypatch.setenv("AGPS_WORLD_GRID", "1")
    row = rq.weigh_trips(146, 21, None, log=lambda *a: None, shard=(145, 146))[0]
    assert row["trip"] == "A10 The Lost Fleet -> Crown Guard Tower", row["trip"]
    assert any("Chillwind Camp" in r for r in row["rides"]), row["rides"]
    assert row["secs"] <= 2074, row["secs"]  # (the walk's grid route: no slower than the Router's own, grid off)


def test_a_long_leg_over_cliffs_is_still_searched_on_the_grid(game):
    # (Dun Morogh's mountains, as the frame budget's long leg: the Router's own goes round by the roads, its straight
    # line over cliffs; the grid's search finds the way)
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    a, b = (0, -5600.0, -500.0, None), (0, -5380.0, -2950.0, None)
    searches = WG.stats.searches
    r = _route(lua, ns, a, b)
    assert WG.stats.searches > searches and r.worldGrid


# --- the stand-in while the searches land (Kooki3z 2026-11-23: about a minute of a straight line through a ridge in the
# Wetlands, or a road detour in Tanaris, followed as the route): with world routing on, a route's first full answer keeps
# the warm-up's slices till it lands (Nav.Landing), then 1 ms again; meanwhile it's drawn faded, and the directions say
# "Working out the route..." with no turns (Nav.StandIn)

WETLANDS = (0, -4106.0, -2471.0)  # (the green cave's north mouth, the measured trip's start)
WETLANDS_STOP = "{ { x = -3800, y = -2700, cont = 0, name = 'there' } }"


def _stand_in_game():
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {WETLANDS[1]}, {WETLANDS[2]}, 0; AGPS_LEVEL = 60")
    ns.settings.gps.worldGrid = True
    return lua, ns


def _pending_routes(lua, on):
    """Every leg routed marked pending (a search still to land), or as it is again."""
    if on:
        lua.execute("""
          local R = AGPS_NS.Router
          AGPS_ROUTE_WAS = R.Route
          R.Route = function(...)
            local r = AGPS_ROUTE_WAS(...)
            if type(r) ~= "table" then return r end
            local c = {} -- (a copy: the grids keep the routes they found)
            for k, v in pairs(r) do c[k] = v end
            c.pending = true
            return c
          end""")
    else:
        lua.execute("AGPS_NS.Router.Route = AGPS_ROUTE_WAS")


def test_a_route_s_first_answer_keeps_the_warm_budget_till_it_lands():
    lua, ns = _stand_in_game()
    N, G = ns.Nav, ns.GPS
    lua.execute("""
      local R = AGPS_NS.Router
      AGPS_BUDGETS, AGPS_DPS = {}, 0
      AGPS_REAL = { R.Pump, R.HasWork, R.Warming, debugprofilestop }
      debugprofilestop = function() return AGPS_DPS end -- (the frames' clock: 16 ms a frame, below)
      R.HasWork = function() return true end
      R.Warming = function() return false end
      R.Pump = function(deadline) AGPS_BUDGETS[#AGPS_BUDGETS + 1] = deadline - AGPS_DPS return false end""")
    budgets = lua.eval("AGPS_BUDGETS")

    def budget():
        lua.execute("AGPS_DPS = AGPS_DPS + 16")
        G.PumpSearches()
        return budgets[len(budgets)]

    def stale():  # (past Nav.Fresh's seconds: only the landing keeps the bigger slices)
        lua.execute(f"AGPS_T = AGPS_T + {N.FRESH_SECONDS + 1}")
    warm, keep = G.PumpBudget(16, True), G.PumpBudget(16, False)
    assert warm == 4 and keep == 1  # (a quarter of the 16 ms frame; 1 ms: the caps as they were)
    try:
        N.SetStops(lua.eval(WETLANDS_STOP), False, "red")
        budget()
        stale()
        assert not N.Fresh() and N.Landing() and budget() == warm  # (nothing shown yet)
        _pending_routes(lua, True)
        try:
            N.Route(WETLANDS[1], WETLANDS[2], 0)
        finally:
            _pending_routes(lua, False)
        assert N.route.pending and N.Landing() and budget() == warm  # (the stand-in: its searches still to land)
        N.Invalidate(True)
        N.Route(WETLANDS[1], WETLANDS[2], 0)
        assert not N.route.pending and not N.Landing() and budget() == keep  # (landed: 1 ms again)
        N.route.pending = True  # (a reroute's search as the player walks on: kept up at 1 ms, issue #316)
        assert budget() == keep
        # (never landing: no longer than LANDING_SECONDS from the stops changing)
        N.SetStops(lua.eval(WETLANDS_STOP), False, "red")
        stale()
        assert budget() == warm
        lua.execute(f"AGPS_T = AGPS_T + {N.LANDING_SECONDS}")
        assert not N.Landing() and budget() == keep
        # (world routing off: Nav.Fresh's seconds only, as before)
        ns.settings.gps.worldGrid = False
        N.SetStops(lua.eval(WETLANDS_STOP), False, "red")
        stale()
        assert not N.Landing() and budget() == keep
    finally:
        lua.execute("""
          local R = AGPS_NS.Router
          R.Pump, R.HasWork, R.Warming, debugprofilestop = AGPS_REAL[1], AGPS_REAL[2], AGPS_REAL[3], AGPS_REAL[4]""")
        ns.settings.gps.worldGrid = False


def _arrow_texts(lua, ns):
    A = ns.Arrow
    A.frame._scripts.OnUpdate(A.frame, 1)
    return [str(w._text) for w in lua.eval("AGPS_WIDGETS").values() if w._text and w._shown]


def test_a_stand_in_is_faded_and_says_working_out_the_route_with_no_turns():
    lua, ns = _stand_in_game()
    N, G = ns.Nav, ns.GPS
    lua.execute("""
      AGPS_ROT = {}
      for _, w in ipairs(AGPS_WIDGETS) do
        if w._kind == "Texture" then w.SetRotation = function(s, a) AGPS_ROT[s] = a end end
      end""")
    gray = """(function()
      for _, w in ipairs(AGPS_WIDGETS) do
        if w._kind == "Texture" and w._vc == "0.60,0.60,0.60" and AGPS_ROT[w] == 0 then return true end
      end
      return false
    end)()"""
    x, y = WETLANDS[1], WETLANDS[2]
    try:
        N.SetStops(lua.eval(WETLANDS_STOP), False, "red")
        _pending_routes(lua, True)
        try:
            N.Route(x, y, 0)
            assert N.route.pending and N.StandIn()
            assert N.Status(x, y, 0) == N.WORKING_TEXT
            G.Follow()
            G.Update()
            assert G.routeFade == G.CHECKING_ALPHA
            assert G.walkTurns is None  # (no turns listed in the directions panel)
            texts = _arrow_texts(lua, ns)
            assert any("Working out the route..." in t for t in texts), texts
            assert not any(t.startswith("Then:") for t in texts), texts
            assert lua.eval(gray), "the arrow isn't up and gray"
        finally:
            _pending_routes(lua, False)
        # (landed: the route and its turns)
        N.Invalidate(True)
        N.Route(x, y, 0)
        assert not N.route.pending and not N.StandIn()
        assert "Working out the route" not in (N.Status(x, y, 0) or "")
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert G.routeFade == 1 or N.Checking()
        assert not any("Working out the route..." in t for t in _arrow_texts(lua, ns))
        # (a route pending again after it landed: the grid's line meanwhile, no turns from it either; Kooki3z 2026-11-23,
        # no directions on a guess)
        N.route.pending = True
        assert N.StandIn() and N.Status(x, y, 0) == N.WORKING_TEXT
        N.route.pending = False
        # (world routing off: a pending route shows as before, Nav.Checking's look)
        ns.settings.gps.worldGrid = False
        N.SetStops(lua.eval(WETLANDS_STOP), False, "red")
        _pending_routes(lua, True)
        try:
            N.Route(x, y, 0)
            assert N.route.pending and not N.StandIn() and N.Status(x, y, 0) != N.WORKING_TEXT
        finally:
            _pending_routes(lua, False)
    finally:
        ns.settings.gps.worldGrid = False
        N.Clear()


def test_the_lifts_inventory_lists_every_elevator_and_why_one_isn_t_modeled():
    from azerothgps import lifts
    from azerothgps.paths import data_dir
    if not (data_dir() / lifts.DUMP).exists():
        pytest.skip("no CMaNGOS dump")
    spawns = lifts.elevators()
    rows = lifts.lifts(spawns)
    assert len(rows) == 2  # (the Great Lift, Freewind Post's)
    for e in {s[0] for s in spawns}:
        assert e in lifts.LIFT_SKIPPED or e in (11898, 11899)


# --- the players' recorded walks and drawn roads with heights are truth (Kooki3z 2026-11-22: "I already recorded pathing
# for darkcloud pinnacle, use that"): worldbake.mark_recorded's links, WG.OwnLinks in game

KOOKI3Z_FLOOR = (1, -5080.0, -1772.6, -60.3)  # (the canyon's floor at the foot of the needles' way up, map 32.0, 24.7)
DARKCLOUD_WALK = range(1795211366, 1795211396)  # (the recorded walk from the Pinnacle's needles down to that floor)


def _walk_line(times):
    from azerothgps import worldbake as WB
    return [p[:2] for t, _part, pts, _s in WB.recorded_walks(1) if t in times for p in pts]


def _near_line(p, line):
    return min(math.dist(p, q) for q in line)


@pytest.mark.parametrize("a, b", [(KOOKI3Z_FLOOR, NEEDLES_TOP), (NEEDLES_TOP, KOOKI3Z_FLOOR)])
def test_from_the_canyon_floor_darkcloud_pinnacle_is_up_kooki3z_s_recorded_walk(game, a, b):
    # (the grid went 1.5 km round by the Great Lift; the walk's bridges and ledges the 8.33 yd cells miss are its links)
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    r = _route(lua, ns, a, b)
    assert r.worldGrid and r.length < 1000
    k = _list(r.kinds)
    assert ns.Router.KIND_LIFT_UP not in k and ns.Router.KIND_LIFT_DOWN not in k
    line = _walk_line(DARKCLOUD_WALK)
    p = _list(r.pts)
    pts = [(p[2 * i], p[2 * i + 1]) for i in range(len(p) // 2)]
    on = [q for q in pts if _near_line(q, line) <= 12]
    assert len(on) >= 0.6 * len(pts)  # (along the walk)
    if a is KOOKI3Z_FLOOR:
        assert _climbs(r) == []  # (up as walked: no step steeper than its own)


def _recorded_grid(zs, links_across=()):
    """A strip of ten 8.33 yd cells (gx 0-9, gy 0), one surface each at heights `zs`, linked to their neighbors both
    ways except across `links_across` (cell i to i + 1)."""
    import numpy as np
    from collections import defaultdict
    from azerothgps import worldgrid as W
    g = W.Grid.__new__(W.Grid)
    n = len(zs)
    g.cont, g.per_tile, g.cell = 1, 64, W.cell_yd(64)
    g.gx, g.gy = np.arange(n, dtype=np.int32), np.zeros(n, np.int32)
    g.z = np.array(zs, np.float32)
    g.off = np.full(n, 36, np.uint8)
    g.kind = np.zeros(n, np.uint8)
    g.flags = np.zeros(n, np.uint8)
    g.gxmin, g.gymin, g.W, g.H, g.n = 0, 0, n, 1, n
    g.first, g.count = np.arange(n, dtype=np.int64), np.ones(n, np.int8)
    g.links = np.full((n, 8), -1, np.int64)
    for i in range(n - 1):
        if i not in links_across:
            g.links[i, 0], g.links[i + 1, 2] = i + 1, i
    g.road, g.road_out, g._ground = [], defaultdict(list), None
    return g


def test_a_recorded_walk_is_the_grid_s_links_where_it_has_none_at_its_own_heights():
    from azerothgps import citygrid as CGP
    from azerothgps import worldbake as WB
    cell = _recorded_grid([0] * 10).cell
    line = [((i + 0.5) * cell, 4.0) for i in range(10)]
    # (a ramp walked up 3 yd a cell where the grid's cells 4 and 5 aren't joined (a ledge the mesh misses): links both
    # ways at the walk's own heights, never refused for the height between them)
    zs = [3.0 * i for i in range(10)]
    g = _recorded_grid(zs, links_across={4})
    n = WB.mark_recorded(g, [(1, 0, [(x, y, z) for (x, y), z in zip(line, zs)], False)])
    ways = {(a, b): (k, pts) for a, b, _c, k, pts in g.road}
    assert n == 2 and set(ways) == {(4, 5), (5, 4)}
    assert ways[(4, 5)][0] == CGP.KIND_WALK and ways[(5, 4)][0] == CGP.KIND_WALK
    assert all(abs(z - (3.0 * (x / cell - 0.5))) < 0.6 for x, _y, z in ways[(4, 5)][1])
    assert (g.flags > 0).all()  # (road ground all along)
    # (a drop walked off the ledge: one way, down)
    zs = [20.0] * 5 + [0.0] * 5
    g = _recorded_grid(zs, links_across={4})
    WB.mark_recorded(g, [(1, 0, [(x, y, z) for (x, y), z in zip(line, zs)], False)])
    assert [(a, b, k) for a, b, _c, k, _p in g.road] == [(4, 5, CGP.KIND_DROP)]
    # (walked the other way, up that step (a jump): both ways, the way down a drop)
    g = _recorded_grid(zs, links_across={4})
    WB.mark_recorded(g, [(1, 0, [(x, y, z) for (x, y), z in reversed(list(zip(line, zs)))], False)])
    assert sorted((a, b, k) for a, b, _c, k, _p in g.road) == [(4, 5, CGP.KIND_DROP), (5, 4, CGP.KIND_WALK)]
    # (a walk the import put on the ground, no heights: on the grid's surfaces, never a drop)
    g = _recorded_grid(zs, links_across={4})
    WB.mark_recorded(g, [(1, 0, [(x, y, None) for x, y in line], False)])
    assert all(k != CGP.KIND_DROP for _a, _b, _c, k, _p in g.road)


def test_the_baked_recorded_walks_are_in_the_data():
    # (Thousand Needles' region: its recorded links, Kooki3z's walk's bridges among them)
    txt = (ADDON_DIR.parent / "AzerothGPS_WG1_4_5" / "Data.lua").read_text(encoding="utf-8")
    links = re.search(r'\n  links = "([^"]*)",', txt).group(1).split(";")
    line = _walk_line(DARKCLOUD_WALK)
    on = 0
    for item in links:
        nums = [float(v) for v in item.split(",")[2:]]
        pts = [(nums[q], nums[q + 1]) for q in range(2, len(nums) - 2, 3)]
        if nums[1] in (0, 4, 6) and pts and all(_near_line(p, line) < 3 for p in pts):
            on += 1
    assert on >= 4


def test_the_player_s_own_walk_with_heights_is_the_grid_s_link(game):
    # (in game, a walk not yet in the data, as the bake's: Kooki3z's own road up the Great Lift's cliff (no way there on
    # the grid but the lift) with its heights, both ways; and one walked down a drop, one way)
    lua, ns = game
    WG = ns.WorldGrid
    foot, top = (1, -4700.0, -1880.0, None), (1, -4605.0, -1880.0, None)
    c = WG.Cont(1)

    def heights(x0, x1):
        return [ns.Ground.Sample(1, x0 + (x1 - x0) * i / 20, -1880.0) for i in range(21)]
    zs = heights(foot[1], top[1])
    pts = [v for i in range(21) for v in (foot[1] + (top[1] - foot[1]) * i / 20, -1880.0)]
    k = _with_track(lua, ns, continent=1, pts=lua.table(*pts), zs=lua.table(*zs), time=999999101, recorded=True)
    try:
        own = [L for L in _list(WG.OwnLinks(c, ns.db.tracks[k]))]
        assert own and any(L.kind == 0 for L in own)
        WG.routes, WG.order = lua.table(), lua.table()
        r = _route(lua, ns, foot, top)
        assert r.worldGrid and r.length < 200  # (up the road: 95 yd straight; by the lift 300 and its wait)
    finally:
        ns.db.tracks[k] = None
        WG.routes, WG.order = lua.table(), lua.table()
    # (down the cliff by a fall: one way)
    zs = [86.0] * 10 + [-44.0] * 11
    k = _with_track(lua, ns, continent=1, pts=lua.table(*reversed_pairs(pts)), zs=lua.table(*zs), time=999999102,
                    recorded=True)
    try:
        own = _list(WG.OwnLinks(c, ns.db.tracks[k]))
        assert own and all(L.kind == 4 for L in own if L.pts[1][3] - L.pts[len(L.pts)][3] > 20)
        assert not any(L.pts[len(L.pts)][3] - L.pts[1][3] > 20 for L in own)
    finally:
        ns.db.tracks[k] = None
        WG.routes, WG.order = lua.table(), lua.table()


def reversed_pairs(flat):
    return [v for i in range(len(flat) // 2 - 1, -1, -1) for v in (flat[2 * i], flat[2 * i + 1])]


# --- every lift car its own shaft, boarded from its platform (Kooki3z 2026-11-22 at the Great Lift: "there are 2, ramp
# to them is in red"; at Thunder Bluff's west lifts the ride was joined to the ground at the stairs' foot)

def _lift_board(r, ns):
    """The route's lift ride: (the point where it's boarded (x, y, z), where it's left), or None."""
    p, k, h = _list(r.pts), _list(r.kinds), _list(r.fz)
    R = ns.Router
    for i, kk in enumerate(k):
        if kk in (R.KIND_LIFT_UP, R.KIND_LIFT_DOWN):
            j = i
            while j < len(k) and k[j] == kk:
                j += 1
            return (p[2 * i], p[2 * i + 1], h[i]), (p[2 * j], p[2 * j + 1], h[j])
    return None


def _says(lua, ns, r):
    part = lua.table(pts=r.pts, kinds=r.kinds, cont=1, stop=1)
    ms = ns.Turns.Maneuvers(ns.Turns.Path(lua.table(parts=lua.table(part))))
    return [str(ms[i].text) for i in range(1, len(ms) + 1)]


GREAT_LIFT_SHAFTS = [(-4665.4, -1827.7), (-4670.8, -1849.6)]
GRISH = (1, -4602.1, -1835.4, 86.2)  # (Grish Longrunner, up top in the Barrens)


@pytest.mark.parametrize("a, b", [(KOOKI3Z_FLOOR, GRISH), (GRISH, KOOKI3Z_FLOOR)])
def test_the_great_lift_is_boarded_from_a_car_s_platform_up_its_ramp(game, a, b):
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    r = _route(lua, ns, a, b)
    assert r.worldGrid and r.length < 700
    on, off = _lift_board(r, ns)
    foot, top = (on, off) if on[2] < off[2] else (off, on)
    # (the foot's platform (its stop at -44), never the ground under it (-49 and lower), by a car's own shaft; the top's
    # walkway at 86)
    assert abs(foot[2] - (-44.1)) <= 2.5 and abs(top[2] - 85.4) <= 2.5
    assert min(math.dist(foot[:2], s) for s in GREAT_LIFT_SHAFTS) <= 10
    assert min(math.dist(top[:2], s) for s in GREAT_LIFT_SHAFTS) <= 10
    said = _says(lua, ns, r)
    assert "Leave the road" not in said and not any("U-turn" in t for t in said)


def test_both_of_the_great_lift_s_cars_are_ridden():
    # (each car's own links up and down, at its shaft: the region's lift links' rides)
    txt = (ADDON_DIR.parent / "AzerothGPS_WG1_4_5" / "Data.lua").read_text(encoding="utf-8")
    links = re.search(r'\n  links = "([^"]*)",', txt).group(1).split(";")
    shafts = set()
    for item in links:
        nums = [float(v) for v in item.split(",")[2:]]
        if nums[1] == 5:
            pts = [(nums[q], nums[q + 1], nums[q + 2]) for q in range(2, len(nums) - 2, 3)]
            for s in GREAT_LIFT_SHAFTS:
                if any(math.dist(p[:2], s) < 0.5 for p in pts):
                    shafts.add(s)
    assert shafts == set(GREAT_LIFT_SHAFTS)


TB_STAIRS = [((1, -1262.0, 213.0, 59.6), (-1286.2, 189.7)), ((1, -1340.0, 179.0, 58.5), (-1308.4, 185.3))]
PALA = (1, -1300.3, 38.5, 129.3)  # (Innkeeper Pala, up on Thunder Bluff)


@pytest.mark.parametrize("a, shaft", TB_STAIRS)
def test_thunder_bluff_s_west_lifts_are_boarded_up_their_stairs(game, a, shaft):
    # (the city grid's: from the foot of each car's stairs, up them onto its platform (69), its own shaft up, never the
    # ground beside it (60) nor the other car's)
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    r = _route(lua, ns, a, PALA)
    on, off = _lift_board(r, ns)
    assert abs(on[2] - 68.6) <= 2.5 and abs(off[2] - 130.1) <= 2.5
    assert math.dist(on[:2], shaft) <= 10
    assert r.length < 260
    said = _says(lua, ns, r)
    assert "Take the lift up" in said and "Leave the road" not in said and not any("U-turn" in t for t in said)


# (Kooki3z 2026-11-22, in Ironforge by the Great Forge: every route stayed on "Working out the route..." for ever, the
# grids on. A recorded road of theirs ran through the Great Forge (no heights, as a recording has); the city grid's costs
# (CG.Costs) called WG.Costs with a stand-in grid, no tiles, and its own links (WG.OwnLinks) errored on it in the route's
# background job: the error swallowed (Router.Pump) and the job queued again every frame)
IF_FORGE = (0, -4826.0, -1138.0, None)  # (the Forge's edge, 3 yd off its pit: the city grid's floor, 502.8)
IF_GRYPHONS = (0, -4821.1, -1152.4, 502.3)  # (Gryth Thurden, the Gryphon Master)
IF_RECORDED = [(-4838.8 + 0.4 * i, -1054.5 - 4.0 * i) for i in range(40)]  # (by the Forge, toward the gryphons)


def test_a_recorded_road_inside_a_capital_never_breaks_the_city_grid_s_costs(game):
    lua, ns = game
    CG, WG = ns.CityGrid, ns.WorldGrid
    pts = [v for p in IF_RECORDED for v in p]
    k = _with_track(lua, ns, continent=0, pts=lua.table(*pts), time=999999201, recorded=True)
    try:
        c = CG.City("Ironforge")
        x = CG.Costs(c, IF_FORGE[1], IF_FORGE[2], IF_GRYPHONS[1], IF_GRYPHONS[2])
        assert x.roadCells  # (still road ground)
        CG.routes, CG.order = lua.table(), lua.table()
        WG.routes, WG.order = lua.table(), lua.table()
        r = _route(lua, ns, IF_FORGE, IF_GRYPHONS)
        assert r and r.cityGrid == "Ironforge"
    finally:
        ns.db.tracks[k] = None
        CG.routes, CG.order = lua.table(), lua.table()
        WG.routes, WG.order = lua.table(), lua.table()


def test_with_a_recorded_road_by_the_great_forge_the_route_to_the_gryphons_settles():
    # (the game's way: Nav's route worked out in the background, the roads built first, the grids on)
    from azerothgps.gameharness import start
    lua, ns = start()
    N, R = ns.Nav, ns.Router
    N.FUN = False
    lua.execute('UnitFactionGroup = function() return "Alliance", "Alliance" end; AGPS_LEVEL = 30')
    ns.CharDB().faction = "Alliance"
    ns.settings.gps.worldGrid = True
    lua.execute(f"AGPS_MAP = 1455; AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {IF_FORGE[1]}, {IF_FORGE[2]}, 0")
    pts = [v for p in IF_RECORDED for v in p]
    _with_track(lua, ns, continent=0, pts=lua.table(*pts), time=999999202, recorded=True)
    R.WARM, R.SYNC_WALKS = True, False
    clock = lua.eval("function() return os.clock() * 1000 end")
    errors = lua.eval("{}")
    lua.globals().AGPS_CO_ERRORS = errors
    lua.execute("""
      local resume = coroutine.resume
      AGPS_RESUME_WAS = resume
      coroutine.resume = function(co, ...)
        local r = { resume(co, ...) }
        if r[1] == false then AGPS_CO_ERRORS[#AGPS_CO_ERRORS + 1] = tostring(r[2]) end
        return unpack(r)
      end""")
    try:
        N.SetStops(lua.eval(f"{{ {{ x = {IF_GRYPHONS[1]}, y = {IF_GRYPHONS[2]}, z = {IF_GRYPHONS[3]}, cont = 0, "
                            "name = 'Ironforge Gryphon Master' } }"), False, "red")
        settled = None
        for f in range(6000):
            lua.execute("AGPS_T = AGPS_T + 0.05")
            N.Status(IF_FORGE[1], IF_FORGE[2], 0)
            if R.HasWork():
                R.Pump(clock() + 20, clock)
            if N.route and not R.HasWork():
                settled = f
                break
            if len(errors) > 0:
                break
        assert len(errors) == 0, list(errors.values())
        assert settled is not None, "the route never settled"
    finally:
        lua.execute("coroutine.resume = AGPS_RESUME_WAS")
        R.WARM, R.SYNC_WALKS = False, True
        ns.settings.gps.worldGrid = False


# --- Mulgore's plain (Kooki3z 2026-11-23, screenshots: from Skywatcher Plateau to a stop on the plain north of Elder
# Rise the route went round by the Barrens and through Thunder Bluff; "we need to make it to where leaving the road is
# ok to reach a destination using worldgrid navigation") ----------------------------------------------------------------

SKYWATCHER = (1, -472.0, 245.0, None)  # (his spot on Skywatcher Plateau)
BY_WILDMANE = (1, -800.0, -431.0, None)  # (his stop: the plain east of Wildmane Water Well, north of Elder Rise)


def test_from_skywatcher_plateau_the_grid_leaves_the_road_down_across_the_plain(game):
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    r = _route(lua, ns, SKYWATCHER, BY_WILDMANE)
    assert r.worldGrid and not r.noWay and not r.pending
    straight = math.dist(SKYWATCHER[1:3], BY_WILDMANE[1:3])
    assert r.length <= 1.3 * straight  # (the road to the pass, then the plain: not round by the Barrens' roads)
    p, k = _list(r.pts), _list(r.kinds)
    pts = [(p[2 * i], p[2 * i + 1]) for i in range(len(p) // 2)]
    assert min(x for x, _y in pts) > -900  # (never by Thunder Bluff's mesas, south of the stop)
    off, run = 0.0, 0.0
    for i, kind in enumerate(k):
        if kind == ns.Router.KIND_ROAD:
            run = 0.0
        else:
            run += math.dist(pts[i], pts[i + 1])
            off = max(off, run)
    assert off >= 300  # (off the road down the plain, one stretch)


# --- Falls over empty cells (WorldGrid.FarDrops; Kooki3z 2026-11-23). A face too steep for the mesh has no floor on
# it, and the walked links join a cell's 8 neighbors only: a fall past an empty cell was no link at any drop limit.
# Kooki3z's rule: "too steep only blocks going UP"; down it is a drop of its height, a walk within the Safe drop and
# deeper a spell jump. Skywatcher Plateau's east edge (130 yd over Mulgore's plain); the Barrens' hills north of the
# Crossroads' south road (Route Studio: "this should be acceptable like SPF", 1,574 yd there against our 2,946 by the
# road), whose way down is 85 yd and more of a 65 degree hillside: a spell's drop, not the Safe drop's 39

BARRENS_A, BARRENS_B = (1, -2241.0, -1916.9, None), (1, -2743.5, -2892.9, None)
SKY_EAST, SKY_PLAIN = (1, -460.0, 160.0, None), (1, -470.0, 40.0, None)


def _falls(lua, ns, a, b, md):
    WG, R = ns.WorldGrid, ns.Router
    WG.routes, WG.order = lua.table(), lua.table()
    WG.targets = lua.table()
    r = WG.Walk(WG.Cont(a[0]), a[1], a[2], None, b[1], b[2], None, lua.table(maxDrop=md))
    assert r
    k, z = _list(r.kinds), _list(r.fz)
    return r.length, [z[i] - z[i + 1] for i, kk in enumerate(k) if kk == R.KIND_DROP]


def test_the_barrens_hills_way_down_is_a_spell_jump_not_the_safe_drop(game):
    lua, ns = game
    yd, falls = _falls(lua, ns, BARRENS_A, BARRENS_B, 196)  # (Slow Fall cast at the edge)
    assert yd <= 1574 and falls and max(falls) >= 80, (yd, falls)  # (down the hillside: shorter than SPF's line)
    yd39, falls39 = _falls(lua, ns, BARRENS_A, BARRENS_B, 39)
    assert not falls39 or max(falls39) <= 39, falls39
    assert yd39 > yd


def test_off_skywatcher_plateau_s_east_edge_a_fall_spell_s_drop(game):
    lua, ns = game
    yd, falls = _falls(lua, ns, SKY_EAST, SKY_PLAIN, 1000)
    assert falls and max(falls) >= 100, (yd, falls)
    assert yd <= 1.5 * math.dist(SKY_EAST[1:3], SKY_PLAIN[1:3])


# --- bake8's cases (Kooki3z in game, 2026-11-23) ----------------------------------------------------------------------

ARENA = (0, -13205.9, 271.8, 22.2)  # (Gurubashi Arena's Battle Ring, its middle)
ARENA_SE = (0, -13255.0, 145.0, None)  # (just outside its south-east wall: the grass south of the east gatehouse)
RING_R = 46.0  # (the Battle Ring's wall round its middle, about)


def _crosses_circle(a, b, c, r):
    """Whether segment a-b goes from inside the circle (c, r) to outside or back."""
    return (math.dist(a, c) < r) != (math.dist(b, c) < r)


def test_gurubashi_arena_from_outside_its_wall_never_a_line_through_the_wall_and_stands(game):
    # (the route went straight through the outer wall and the stands into the Battle Ring: the Router's own walk, kept
    # by #952's stopgap (WG.RouterClosed: its data hasn't the arena's walls), where the grid had no way. bake8: the grid
    # no longer walks into the ring through its wall's end (worldgrid.mesh_walk's arrival), and with no way on the grid
    # (our mesh has the ring and stands apart from the ground outside: the gate tunnels don't join them) it's "No way
    # there found" until the bake covers it)
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order = lua.table(), lua.table()
    r = _route(lua, ns, ARENA_SE, ARENA)
    if r.noWay:
        return
    p, fz = _list(r.pts), _list(r.fz) or []
    pts = [(p[2 * i], p[2 * i + 1]) for i in range(len(p) // 2)]
    for i in range(len(pts) - 1):
        low = (fz[i] if i < len(fz) and fz[i] else 0) < 30 and (fz[i + 1] if i + 1 < len(fz) and fz[i + 1] else 0) < 30
        assert not (low and _crosses_circle(pts[i], pts[i + 1], ARENA[1:3], RING_R)), (i, pts[i], pts[i + 1])
    assert r.length > 1.5 * math.dist(ARENA_SE[1:3], ARENA[1:3])  # (round by a gate, never straight in)


DEN = (1, -545.6, -4218.8, 63.3)  # (route-compare open:122: a spot in the Den, Valley of Trials, on its raised ground)
DEN_TO = (1, -646.6, -3447.2, 92.2)


def test_off_the_den_s_raised_ground_a_drop_never_a_walk_line_off_its_edge(game):
    # (route-compare 2026-11-23: the grid's line stepped off 14 yd of raised ground at (-560.5, -4224.0), a walk over
    # the edge. The way down is the mesh's drop (kind drop: one way, within the safe drop), the walks keep their slopes)
    lua, ns = game
    WG = ns.WorldGrid
    R = ns.Router
    WG.routes, WG.order = lua.table(), lua.table()
    r = _route(lua, ns, DEN, DEN_TO)
    assert r.worldGrid and not r.noWay
    p, fz, k = _list(r.pts), _list(r.fz), _list(r.kinds)
    for i, kind in enumerate(k):
        if kind in (R.KIND_ROAD, R.KIND_OFFROAD) and fz[i] is not None and fz[i + 1] is not None:
            L = math.dist((p[2 * i], p[2 * i + 1]), (p[2 * i + 2], p[2 * i + 3]))
            assert abs(fz[i + 1] - fz[i]) <= max(6.0, 1.2 * L), (i, fz[i], fz[i + 1], L)


# --- Freewind Post's mesa (Kooki3z 2026-11-23, Expert jumper with Slow Fall and Light Feathers: from the mesa's top to
# the canyon road below the route went over the west bridge and down the next mesa's road; his way, off the north-west
# edge and down). The bake's drops go to worldgrid.DROP_FAR (400 yd): with a drop that big allowed (Expert jumper's,
# the player's own x.maxDrop) the grid's way is the 119 yd drop off the edge; without one, the roads.

FREEWIND_TOP = (1, -5404.0, -2405.0, None)  # (on the mesa, about map 44.8, 49)
CANYON_ROAD = (1, -5404.0 - 260 * math.cos(math.pi / 4), -2405.0 + 260 * math.sin(math.pi / 4), None)


def test_off_freewind_post_s_mesa_an_expert_jumper_s_drop_never_the_far_road(game):
    lua, ns = game
    WG, R = ns.WorldGrid, ns.Router
    c = WG.Cont(1)
    straight = math.dist(FREEWIND_TOP[1:3], CANYON_ROAD[1:3])
    got = {}
    for md in (39, 1000):
        WG.routes, WG.order = lua.table(), lua.table()
        WG.targets = lua.table()
        r = WG.Walk(c, FREEWIND_TOP[1], FREEWIND_TOP[2], None, CANYON_ROAD[1], CANYON_ROAD[2], None, lua.table(maxDrop=md))
        assert r
        k, z = _list(r.kinds), _list(r.fz)
        got[md] = (r.length, [z[i] - z[i + 1] for i, kk in enumerate(k) if kk == R.KIND_DROP])
    assert got[39][1] == [] or max(got[39][1]) <= 39
    assert got[1000][1] and max(got[1000][1]) >= 100  # (the drop off the mesa's edge)
    assert got[1000][0] <= 1.3 * straight < got[39][0]  # (and not round by the roads)


# --- Darkmist Cavern (Kooki3z 2026-11-23, the Barrens' ridge to Dustwallow: the grid's way jumped 176 yd from the ridge
# straight down into the cavern's tunnels and walked out its east mouth; "those should only be routes available outside
# the cave once going through the entrance"). bake9: no drop from the ground onto a cell of a cave's grid under it
# (worldbake.cut_ceiling_drops), nor a landing with the ground going on over it (worldgrid._clear_over)

DARKMIST_RIDGE = (1, -2766.0, -2574.0, 208.0)
DARKMIST_TUNNEL = (1, -2825.0, -2624.0, 38.0)


def test_from_the_barrens_ridge_never_a_drop_into_darkmist_cavern_s_tunnels(game):
    lua, ns = game
    WG = ns.WorldGrid
    c = WG.Cont(1)
    falls = []
    for x in range(-2900, -2700, 8):
        for y in range(-2700, -2500, 8):
            for s in _list(WG.SurfacesAt(c, x, y)):
                if s.z < 120:
                    continue
                t = WG.Tile(c, s.key)
                for d in range(1, 9):
                    kk = WG.Link(t, s.s, d)
                    nkey, nci = WG.Step(c, s.key, s.ci, d)
                    nt = kk and nkey and WG.Tile(c, nkey)
                    if nt and WG.Z(c, nt, WG.First(nt, nci) + kk - 1) < 80:
                        falls.append((round(s.x), round(s.y), round(s.z)))
    assert falls == []
    WG.routes, WG.order = lua.table(), lua.table()
    r = WG.Walk(c, *DARKMIST_RIDGE[1:], *DARKMIST_TUNNEL[1:], lua.table(maxDrop=1000))
    assert not r or r.length > 3 * math.dist(DARKMIST_RIDGE[1:3], DARKMIST_TUNNEL[1:3])  # (by a mouth, if at all)


# --- The Deadmines from Moonbrook (Kooki3z 2026-11-23, build 3ae5a417: from Moonbrook's ground the way to the portal must
# go in by the Defias hideout's house and never drop through the ground). The house sits over a hole in the terrain
# (no height there); bake9's grid fell from its floor, 45, straight down to the tunnel, 24, under the ramp's floor, 36.
# Now a drop onto a cave's floor under a hole with another floor over its foot is cut (worldbake.cut_ceiling_drops): the
# ramp's walked

MOONBROOK = (-11173.3, 1651.7)  # (Moonbrook's ground north of the house, about map 39, 76)
DEADMINES_PORTAL = (-11208.7, 1675.9)
HIDEOUT_DOOR = (-11090.0, 1500.0)  # (the house's floor by the ramp's head)


def test_from_moonbrook_the_deadmines_are_entered_by_the_hideout_s_ramp_never_a_drop_through_its_floors(game):
    lua, ns = game
    WG = ns.WorldGrid
    c = WG.Cont(0)
    falls = []
    for x in range(-11136, -11084, 4):
        for y in range(1490, 1546, 4):
            for s in _list(WG.SurfacesAt(c, x, y)):
                if s.z < 40:
                    continue
                t = WG.Tile(c, s.key)
                for d in range(1, 9):
                    kk = WG.Link(t, s.s, d)
                    nkey, nci = WG.Step(c, s.key, s.ci, d)
                    nt = kk and nkey and WG.Tile(c, nkey)
                    if nt and WG.Z(c, nt, WG.First(nt, nci) + kk - 1) < 29:
                        falls.append((round(s.x), round(s.y), round(s.z)))
    assert falls == []
    WG.routes, WG.order = lua.table(), lua.table()
    ns.settings.gps.worldGrid = True
    ns.settings.gps.roadTolerance = 0
    r = WG.Leg(0, *MOONBROOK, *DEADMINES_PORTAL, lua.table(tz=26.3))
    assert r and not r.pending
    pts = [(r.pts[i], r.pts[i + 1]) for i in range(1, len(r.pts), 2)]
    assert min(math.dist(p, HIDEOUT_DOOR) for p in pts) < 15, pts  # (by the house's way in)


# --- a stop on a slope the bake doesn't reach (Kooki3z 2026-11-23, Agpsdaddio, an Alliance player at level 60 in
# Stranglethorn: from north of Booty Bay to a stop on the hillside east of Kurzen's Compound, the settled route went
# up into the Mosh'Ogg hills and back, 4.5k yd for 2.6k straight, "a critical routing issue". The stop's cell's
# surfaces aren't F_REACH (the slope, 40 yd over the valley's reached ground), so no search could arrive: both
# corridors and the whole grid flooded, gave up, and the leg was the Router's own. WG.NearGoals: the reached ground
# nearest the stop is a goal too)

STV_START = (0, -13968.0, 281.0, None)  # (north of Booty Bay, where he stood)
STV_SLOPE = (0, -11705.0, -1036.0, None)  # (his stop, read off the screenshot: about 51, 12)


def test_to_a_stop_on_an_unreached_slope_the_grid_walks_up_stranglethorn_s_valley(game):
    lua, ns = game
    WG, cdb, st = ns.WorldGrid, ns.CharDB(), ns.settings.gps
    c = WG.Cont(0)
    assert not any(int(f.f) & 4 for f in WG.SurfacesAt(c, STV_SLOPE[1], STV_SLOPE[2]).values())  # (none reached)
    was = (cdb.faction, st.avoidHostile)
    lua.execute('AGPS_UFG_WAS = UnitFactionGroup; UnitFactionGroup = function() return "Alliance", "Alliance" end')
    cdb.faction, st.avoidHostile = "Alliance", True
    try:
        for side in ("Alliance", "Horde"):
            if side == "Horde":
                lua.execute("UnitFactionGroup = AGPS_UFG_WAS")
                cdb.faction = "Horde"
            WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
            r = _route(lua, ns, STV_START, STV_SLOPE)
            assert r.worldGrid and not r.noWay and not r.pending, side
            straight = math.dist(STV_START[1:3], STV_SLOPE[1:3])
            assert r.length <= 1.2 * straight, (side, r.length, straight)  # (the Router's own: 1.71x as an Alliance)
            p = _list(r.pts)
            pts = [(p[2 * i], p[2 * i + 1]) for i in range(len(p) // 2)]
            assert (pts[-1][0], pts[-1][1]) == STV_SLOPE[1:3]
            # (never east up into the Mosh'Ogg hills: the Router's own left the valley road, y about -715, south from
            # x -12530 by y -816 and -851 to -953 at the ogre mound. bake9's grid walks along that road, y -704 and
            # -745 at x -12430 to -12160, 1.14x straight: the valley, not the hills)
            assert all(y > -790 for x, y in pts if x < -12100), (side, [q for q in pts if q[0] < -12100 and q[1] <= -790])
    finally:
        lua.execute("UnitFactionGroup = AGPS_UFG_WAS")
        cdb.faction, st.avoidHostile = was
        WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()


# --- the same trip, its search dropped (Kooki3z 2026-11-23, after the fix above: the route still up the Mosh'Ogg hills,
# 4.0k yd. The Router's reset (R.Reset: the guards changed, R.HostileChanged; the player's edits) emptied its queue with
# the grid's search in it, and the grid's own list of jobs kept it: asked again for the stop, the grid waited on a search
# that was gone, and the trip settled on the Router's own. R.Background's `dropped`: out of the list, asked again)

STV_START2 = (0, -13793.0, 249.0, None)  # (north of Booty Bay, the second screenshot)
STV_STOP2 = (0, -11782.0, -721.0, None)  # (north of Lake Nazferiti: about 46, 14)


def test_a_grid_search_dropped_by_a_router_reset_is_searched_again_not_left_to_the_router_s_own(game):
    lua, ns = game
    R, N, G, WG, cdb, st = ns.Router, ns.Nav, ns.GPS, ns.WorldGrid, ns.CharDB(), ns.settings.gps
    was = (R.WARM, R.SYNC_WALKS, cdb.faction, st.avoidHostile, st.worldGrid)
    lua.execute('AGPS_UFG_WAS = UnitFactionGroup; UnitFactionGroup = function() return "Alliance", "Alliance" end')
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {STV_START2[1]}, {STV_START2[2]}, 0; AGPS_LEVEL = 60")
    clock = lua.eval("function() return os.clock() * 1000 end")
    try:
        cdb.faction, st.avoidHostile, st.worldGrid = "Alliance", True, True
        WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
        R.Reset()
        R.WARM, R.SYNC_WALKS = True, False
        N.Clear()
        N.SetStops(lua.eval(f"{{ {{ x = {STV_STOP2[1]}, y = {STV_STOP2[2]}, cont = 0, name = 'stop' }} }}"), False, "red")
        reset = False
        for _ in range(4000):
            lua.execute("AGPS_T = AGPS_T + 0.1")
            G.Update()
            if R.HasWork():
                R.Pump(clock() + 8, clock)
            if not reset and WG.jobCount > 0:
                reset = True
                R.HostileChanged()  # (the guards changed mid-search: the Router's queue emptied)
            if reset and N.route and not N.route.pending and not R.HasWork():
                break
        assert reset and N.route and not N.route.pending and not R.HasWork()
        assert WG.jobCount == 0
        straight = math.dist(STV_START2[1:3], STV_STOP2[1:3])
        assert N.route.totalYards <= 1.3 * straight, (N.route.totalYards, straight)  # (the Router's own: 3.9k, 1.76x)
    finally:
        lua.execute("UnitFactionGroup = AGPS_UFG_WAS")
        N.Clear()
        R.WARM, R.SYNC_WALKS, cdb.faction, st.avoidHostile, st.worldGrid = was
        WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()



# --- Kooki3z's rule for fall spells on steep slopes (2026-11-23): a lasting buff (Slow Fall) keeps going when the player
# touches the slope and slides, so the Barrens' hillside (48 degrees on the whole, 119 yd down) is its drop; a glide that
# ends on landing (a warrior's Walk on Air, its only one) ends at the face: there no more than the Safe drop. A clean
# drop (Tanaris' rim, 65 degrees) is a glide's too (WorldGrid.FAR_DROP_CLEAN_SLOPE, FallSpells.EndsOnLanding)

def _with_spell(lua, ns, spell, expert, fn):
    st = ns.settings.gps
    was = (st.expertJumper, st.safeDropYd)
    st.expertJumper, st.safeDropYd = expert, 39
    lua.execute("AGPS_SPELLS_WAS = { IsPlayerSpell, GetItemCount }; "
                f"IsPlayerSpell = function(id) return id == {spell} end; "
                "GetItemCount = function(id) return id == 17056 and 5 or 0 end")
    ns.FallSpells.Refresh()
    try:
        return fn()
    finally:
        lua.execute("IsPlayerSpell, GetItemCount = AGPS_SPELLS_WAS[1], AGPS_SPELLS_WAS[2]")
        st.expertJumper, st.safeDropYd = was
        ns.FallSpells.Refresh()


def _falls_now(lua, ns, a, b, steepness=False):
    WG, R = ns.WorldGrid, ns.Router
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    r = WG.Walk(WG.Cont(a[0]), a[1], a[2], None, b[1], b[2], None, lua.table())
    assert r
    k, z, p = _list(r.kinds), _list(r.fz), _list(r.pts)
    out = []
    for i, kk in enumerate(k):
        if kk == R.KIND_DROP:
            run = max(1.0, math.dist((p[2 * i], p[2 * i + 1]), (p[2 * i + 2], p[2 * i + 3])))
            out.append((z[i] - z[i + 1], (z[i] - z[i + 1]) / run) if steepness else z[i] - z[i + 1])
    return r.length, out


def test_a_warrior_s_walk_on_air_never_goes_down_the_barrens_hillside_a_mage_s_slow_fall_does(game):
    lua, ns = game
    _yd, falls = _with_spell(lua, ns, 1259416, True, lambda: _falls_now(lua, ns, BARRENS_A, BARRENS_B, True))
    # (Walk on Air: past the Safe drop only clean drops, steeper than 55 degrees on the whole; the hillside's 48 isn't)
    slopes = [(round(f), round(math.degrees(math.atan(t)))) for f, t in falls if f > 39 and t < math.tan(math.radians(54))]
    assert slopes == [], falls
    _yd, falls = _with_spell(lua, ns, 130, False, lambda: _falls_now(lua, ns, BARRENS_A, BARRENS_B))
    assert falls and max(falls) >= 80, falls  # (Slow Fall: down the hillside)


def test_a_warrior_s_walk_on_air_still_jumps_tanaris_clean_rim(game):
    lua, ns = game
    a, b = (1, -6969.1, -2931.5, None), (1, -6969.1, -1957.5, None)
    yd, falls = _with_spell(lua, ns, 1259416, True, lambda: _falls_now(lua, ns, a, b))
    assert falls and max(falls) >= 150 and yd <= 1.3 * math.dist(a[1:3], b[1:3]), (yd, falls)


# Bluefen's ridge (Kooki3z 2026-11-24, Dustwallow map 43.4, 7.9 to the stop by Bluefen, ~43, 15): "Straight, then
# arrive", a plain walk down the steep face below the ridge, slantwise; "this one is clearly a jump". A face too steep to
# stand on is a drop by its full height, judged by the terrain's own slope (WorldGrid.TerrainSlope), left down the fall
# line. And Stonetalon's Webwinder Path (his Safe drop 60): "its not even that far down", a face under 40 yd too steep
# to walk got neither a walk nor a drop: falls over empty cells from 8 yd (FAR_DROP_MIN)
BLUEFEN_RIDGE, BLUEFEN_STOP = (1, -2309.8, -3253.5, None), (1, -2558.3, -3232.5, None)
WEBWINDER_TOP, WEBWINDER_STOP = (1, 921.8, 401.6, 68.5), (1, 955.0, 207.0, None)


def test_off_bluefen_s_ridge_a_warrior_s_walk_on_air_jump_and_without_no_walk_down_the_face(game):
    lua, ns = game
    a, b = BLUEFEN_RIDGE, BLUEFEN_STOP
    yd, falls = _with_spell(lua, ns, 1259416, True, lambda: _falls_now(lua, ns, a, b, True))
    assert falls and max(f for f, _t in falls) >= 100 and yd <= 1.3 * math.dist(a[1:3], b[1:3]), (yd, falls)
    yd, falls = _with_spell(lua, ns, 0, False, lambda: _falls_now(lua, ns, a, b, True))
    assert all(f <= 39.5 for f, _t in falls), falls  # (no spell: never the face, nor a fall past the Safe drop)
    assert yd > 2 * math.dist(a[1:3], b[1:3])  # (the long way round)


@pytest.mark.parametrize("safe", [60, 10])
def test_down_webwinder_path_s_hill_within_the_safe_drop_round_it_below(game, safe):
    lua, ns = game
    st = ns.settings.gps
    was = st.safeDropYd
    st.safeDropYd = safe
    try:
        yd, falls = _falls_now(lua, ns, WEBWINDER_TOP, WEBWINDER_STOP)
    finally:
        st.safeDropYd = was
    assert all(f <= safe + 0.5 for f in falls), falls
    if safe == 60:
        assert yd <= 260 and max(falls) >= 20, (yd, falls)  # (down the east face)
    else:
        assert yd > 300, yd  # (round the hill's foot)


def test_into_the_wailing_caverns_never_by_a_drop_through_the_ground(game):
    # (2026-11-24: with Expert jumper's drop limit the grid's way to the portal's floor went up the hills over the
    # caverns and fell from 180 straight down to 26 in them, the terrain 168 over the landing: a baked drop the bake's
    # cave cut missed (the caverns aren't in Data/Caves.lua). Caves only by their mouths: WorldGrid.IntoGround at search
    # time for any fall from the ground into it. No way yet, or the tunnels; never over the ground into them)
    lua, ns = game
    WG, R = ns.WorldGrid, ns.Router
    c = WG.Cont(1)
    mouth, portal = (-846.0, -2003.0), (-738.5, -2217.8)
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    r = WG.Walk(c, mouth[0], mouth[1], None, portal[0], portal[1], 15.6, lua.table(maxDrop=1000, slopeDrop=1000))
    if not r:
        return
    k, z = _list(r.kinds), _list(r.fz)
    assert max(z) <= 120, max(z)  # (not up on the hills over the caverns, 150-180)
    assert not [i for i, kk in enumerate(k) if kk == R.KIND_DROP and z[i] - z[i + 1] >= 20]


# --- A cave's way in from a recorded walk (docs/world-grid-1.4.0.md section 11): skipped until the place has one in the
# overrides (a recorded walk reaching within RECORDED_NEAR_YD of the portal), then the grid's way in by it is required,
# never a fall from the ground into the cave
RECORDED_NEAR_YD = 30
CAVE_WALKS = {  # (the portal: cont, x, y, its floor's height or None)
    "wailing_caverns": (1, -738.5, -2217.8, 15.6),
    "gnomeregan_front": (0, -5162.6, 927.8, None),
    "gnomeregan_depot": (0, -4859.0, 770.2, None),
}


def _recorded_near(cont, x, y):
    from azerothgps import worldbake
    return any(math.dist(p[:2], (x, y)) <= RECORDED_NEAR_YD for _t, _part, pts, _s in worldbake.recorded_walks(cont)
               for p in pts)


@pytest.mark.parametrize("place", list(CAVE_WALKS))
def test_a_recorded_walk_into_a_cave_is_its_way_in(game, place):
    from azerothgps import worldcoverage as WC
    b = CAVE_WALKS[place]
    if not _recorded_near(b[0], b[1], b[2]):
        # (a known gap, not a skip: the CI gate lists it and stays green, as it can't for a skip)
        pytest.xfail(f"no recorded walk to {place}'s portal yet (Grid gaps: Kooki3z records it, then the region's bake)")
    lua, ns = game
    WG, R = ns.WorldGrid, ns.Router
    c = WG.Cont(b[0])
    d = {"cont": b[0], "x": b[1], "y": b[2], "z": b[3], "name": place, "kind": "portal"}
    starts = WC.starts_for(ns, c, d)  # (the ground round it, as the coverage check walks from)
    assert starts
    for s0 in starts:
        WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
        r = WG.Walk(c, s0["x"], s0["y"], s0["z"], b[1], b[2], b[3], lua.table())
        assert r, f"{place}: no way on the grid from {s0} with its recorded walk in (baked? docs section 11)"
        k, z = _list(r.kinds), _list(r.fz)
        assert not [i for i, kk in enumerate(k) if kk == R.KIND_DROP and z[i] - z[i + 1] >= 20]  # (walked in, no fall)
