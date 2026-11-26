"""With world routing on, the route shown while the grid works a walk leg out, and when it has none.

Kooki3z 2026-11-23: "we have to get rid of the fallback option, its fighting routing too much". The Router's own route
(by the roads, round by Steamwheedle Port from Tanaris' sands to Uldum, 5.9k yd for 1.8k straight; North Point Tower's
road from the Barrens' ridge; over the Wailing Caverns' ground) is never shown or followed: while the grid works, the
straight line to the stop, faded, "Working out the route..." and no turns (Router.GridWaiting, Nav.StandIn); with no way
on the grid, "No way found yet", the gap logged for the data (WorldGrid.NoWay, WG.gaps, Nav.gridGapHook). The leg to
the stop itself is searched first (Router.SetFocus)."""

from __future__ import annotations

import math

import pytest

pytest.importorskip("lupa.lua51")

from azerothgps import undergroundsweep as U  # noqa: E402

SANDS = (-8063.0, -3567.0)  # (Tanaris, the sands south of Gadgetzan: Kooki3z's spot, about map 48, 53)
ULDUM = (-9650.0, -2783.3)  # (Uldum's entrance)
SLICE_MS, TICK_S, STEP_YD = 15, 0.5, 7  # (a mounted player's half second, and the background's share of it)


@pytest.fixture(scope="module")
def game():
    lua, ns = U._game()
    yield lua, ns
    ns.Router.SYNC_WALKS = True
    ns.settings.gps.worldGrid = False
    ns.settings.gps.cityGrid = False


def _ride(lua, ns, start, stop, ticks=40, cont=1, step=STEP_YD, faction="Alliance", seen=None, routes=None):
    """The player riding along the route shown (world routing on), the background pumped SLICE_MS a tick as the game
    does, the route worked out again when a search lands (Nav.SearchDone): [(tick, route yards, pending, straight yards
    left)]; route yards None while there's no route (no way)."""
    R, N = ns.Router, ns.Nav
    now = lua.eval("function() return os.clock() * 1000 end")
    lua.execute(f"UnitFactionGroup = function() return '{faction}' end")
    ns.CharDB().faction = faction
    ns.settings.gps.roadTolerance = 0
    grid_was = ns.settings.gps.worldGrid
    ns.settings.gps.worldGrid = True
    R.Reset()
    R.SYNC_WALKS = False
    try:
        N.Clear()
        x, y = start
        lua.execute(f"AGPS_POS = {{ {x}, {y}, {cont} }}")
        N.SetStops(lua.eval(f"{{ {{ x = {stop[0]}, y = {stop[1]}, cont = {cont}, name = 'stop' }} }}"), False, "red")
        out = []
        for tick in range(ticks):
            lua.execute(f"AGPS_POS = {{ {x}, {y}, {cont} }}; AGPS_T = {tick * TICK_S}")
            r = N.Route(x, y, cont)
            t0 = now()
            while R.HasWork() and now() - t0 < SLICE_MS:
                res = R.Pump(now() + 4, now)
                done, fixed = res if isinstance(res, tuple) else (res, None)
                if done:
                    N.SearchDone(fixed)
            if r is None:
                out.append((tick, None, False, math.dist((x, y), stop)))
                continue
            out.append((tick, r.totalYards or 0, bool(r.pending), math.dist((x, y), stop)))
            if routes is not None:
                routes.append(r)
            p = r.parts[1].pts
            if seen is not None:
                pts = []
                for j in range(1, len(r.parts) + 1):
                    q = r.parts[j].pts
                    pts += [(q[i], q[i + 1]) for i in range(1, len(q), 2)]
                seen.append((tick, bool(r.pending), pts))
            if p[3] is None:
                continue  # (a part of one point: the player is at the stop, rode there before the ticks ran out)
            ax, ay, bx, by = p[1], p[2], p[3], p[4]
            L = math.hypot(bx - ax, by - ay)
            if L > 0:
                f = min(1.0, step / L)
                x, y = x + (bx - x) * f, y + (by - y) * f
        return out
    finally:
        while R.HasWork():
            R.Pump(now() + 50, now)
        R.SYNC_WALKS = True
        ns.settings.gps.worldGrid = grid_was
        N.Clear()


def _gaps(ns):
    G = ns.WorldGrid.gaps
    return [G[i] for i in range(1, len(G) + 1)]


def test_from_tanaris_sands_to_uldum_the_line_meanwhile_then_the_grid_s_walk_never_the_roads(game):
    # (while the grid works: the line; then its walk over the sands, Uldum's entrance reached at the sand's height
    # (WorldGrid.NearGoals' HIGH_GOAL_Z), never the Router's own round by Steamwheedle Port)
    lua, ns = game
    rows = _ride(lua, ns, SANDS, ULDUM, ticks=150, step=0)  # (1.2 s of search at the test's 30 ms a second)
    assert all(r[1] is not None and (not r[2] or r[1] <= r[3] + 1) for r in rows), rows[:5]
    done = [r for r in rows if not r[2]]
    assert done and done[-1][1] <= 1.3 * done[-1][3], done[-1:]  # (straight over the sands)


def test_the_walk_to_the_stop_is_searched_before_the_planner_s_others(game):
    lua, ns = game
    R, N = ns.Router, ns.Nav
    R.Reset()
    R.SYNC_WALKS = False
    ns.settings.gps.worldGrid = True
    WG = ns.WorldGrid
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()  # (none known from the tests before)
    try:
        N.Clear()
        lua.execute(f"AGPS_POS = {{ {SANDS[0]}, {SANDS[1]}, 1 }}")
        N.SetStops(lua.eval(f"{{ {{ x = {ULDUM[0]}, y = {ULDUM[1]}, cont = 1, name = 'stop' }} }}"), False, "red")
        N.Route(SANDS[0], SANDS[1], 1)
        assert R.IsFocus(1, ULDUM[0], ULDUM[1])
        lua.execute("QJOBS = function() local _, j = debug.getupvalue(AGPS_NS.Router.HasWork, 1); return j end")
        jobs = lua.eval("QJOBS()")
        keys = [str(jobs[i].key) for i in range(1, len(jobs) + 1)]
        # (the grid's search for the walk to the stop, first; and no Router's own walk queued for it at all)
        assert keys[0].startswith("worldgrid:%.0f:%.0f:" % SANDS) and ">1>%.0f:%.0f:" % ULDUM in keys[0], keys[:3]
        assert "1:%.0f:%.0f:%.0f:%.0f" % (SANDS[0], SANDS[1], ULDUM[0], ULDUM[1]) not in keys
    finally:
        now = lua.eval("function() return os.clock() * 1000 end")
        while R.HasWork():
            R.Pump(now() + 50, now)
        R.SYNC_WALKS = True
        ns.settings.gps.worldGrid = False
        N.Clear()


DUSTWALLOW_RIDGE, DUSTWALLOW_MARSH = (-2339.0, -2923.0), (-2501.0, -2904.0)  # (the Barrens' ridge top, the marsh 163 yd off)
SKYWATCHER, BY_WILDMANE = (-472.0, 245.0), (-800.0, -431.0)


@pytest.mark.parametrize("start, stop", [(DUSTWALLOW_RIDGE, DUSTWALLOW_MARSH), (SKYWATCHER, BY_WILDMANE)])  # (Uldum: above)
def test_the_route_shown_meanwhile_is_the_line_never_a_road_s_way_round(game, start, stop):
    # (Kooki3z 2026-11-23, Dustwallow: from the ridge to the marsh 163 yd below the route went 700 yd to North Point
    # Tower's road junction and 700 back, for a minute; Tanaris by Gadgetzan and Steamwheedle Port; Mulgore round by the
    # Barrens. While the grid works the leg out: the straight line, pending, never the Router's own)
    lua, ns = game
    rows = _ride(lua, ns, start, stop, ticks=30)
    bad = [r for r in rows if r[2] and r[1] > r[3] + 1]
    assert bad == [], bad[:3]



# A mage's trip (Kooki3z 2026-11-23, build 8921e21f; a Horde mage, Slow Fall and feathers, Safe drop 60): from Tanaris's
# sands north-west of Gadgetzan, well back from the west rim, to Un'Goro north-west of Fire Plume Ridge. The route shown
# went east to Gadgetzan's gate, then a straight line south-west across the sands to the southern ramp: the road-snap
# stand-in's shape. Never by Gadgetzan, the stand-in meanwhile or the route settled (with the spell jumping routes,
# PR #983, off the rim: test_spell_jumping's far-back trip, the same spots)
DADDIO_FAR, DADDIO_STOP = (-6950.0, -2950.0), (-6827.2, -1833.35)
GADGETZAN_WEST_Y = -3400.0  # (Gadgetzan's gate, y about -3670; the start's y -2950: east of this is the way round by it)


def test_a_mage_s_trip_from_tanaris_s_sands_to_un_goro_never_goes_by_gadgetzan(game):
    lua, ns = game
    st = ns.settings.gps
    was = (st.safeDropYd, st.expertJumper)
    st.safeDropYd, st.expertJumper = 60, True
    lua.execute("AGPS_SPELLS_WAS = { IsPlayerSpell, GetItemCount }; IsPlayerSpell = function(id) return id == 130 end; "
                "GetItemCount = function(id) return id == 17056 and 5 or 0 end")  # (Slow Fall, Light Feathers)
    seen = []
    try:
        _ride(lua, ns, DADDIO_FAR, DADDIO_STOP, ticks=30, faction="Horde", seen=seen)
    finally:
        lua.execute("IsPlayerSpell, GetItemCount = AGPS_SPELLS_WAS[1], AGPS_SPELLS_WAS[2]")
        st.safeDropYd, st.expertJumper = was
    assert seen and all(pts for _, _, pts in seen)
    east = [(t, pend, min(y for _, y in pts)) for t, pend, pts in seen if pts and min(y for _, y in pts) < GADGETZAN_WEST_Y]
    assert east == [], east[:3]

# Kooki3z in game, build 7d8bd83d (2026-11-23; city and world routing on, Use class spells and Expert jumper, Safe drop
# 39, Road tolerance +0): standing on Tanaris' sands north-west of Gadgetzan, a stop 974 yd west down in Un'Goro, and
# after a full minute still "Consulting the Tinker Town schematics...", the stand-in east to the Gadgetzan road. The rim
# between is a 188 yd fall down a face 60 yd deep that no floor of the grid covers: no link off it at any drop limit,
# so the grid's search flooded Tanaris for a way down (4.5 s of background here, the far southern ramp's 3.4k yd). Now
# a fall over empty cells is a drop (WorldGrid.FarDrops): settled in seconds, over the rim, and marked as a jump
TINKER_SANDS, TINKER_STOP = (-6969.1, -2931.5), (-6969.1, -1957.5)


def test_from_tanaris_sands_by_the_rim_the_route_settles_over_it_as_a_jump(game):
    lua, ns = game
    st = ns.settings.gps
    was = (st.safeDropYd, st.expertJumper, st.worldGrid, st.cityGrid)
    st.safeDropYd, st.expertJumper, st.worldGrid, st.cityGrid = 39, True, True, True
    lua.execute("AGPS_SPELLS_WAS = { IsPlayerSpell, GetItemCount }; IsPlayerSpell = function(id) return id == 130 end; "
                "GetItemCount = function(id) return id == 17056 and 5 or 0 end")  # (Slow Fall, Light Feathers)
    ns.FallSpells.Refresh()
    routes = []
    try:
        rows = _ride(lua, ns, TINKER_SANDS, TINKER_STOP, ticks=40, step=0, faction="Horde", routes=routes)
    finally:
        lua.execute("IsPlayerSpell, GetItemCount = AGPS_SPELLS_WAS[1], AGPS_SPELLS_WAS[2]")
        st.safeDropYd, st.expertJumper, st.worldGrid, st.cityGrid = was
        ns.FallSpells.Refresh()
    settled = [t for t, _yd, pending, _left in rows if not pending]
    assert settled and settled[0] <= 30, rows[-1]  # (within 15 s of a 30 ms a second background: the game's is more)
    straight = math.dist(TINKER_SANDS, TINKER_STOP)
    assert rows[-1][1] <= 1.3 * straight, rows[-1]  # (over the rim, not round by the southern ramp)
    r = routes[-1]
    R = ns.Router
    kinds = [r.parts[p].kinds[i] for p in range(1, len(r.parts) + 1)
             for i in range(1, len(r.parts[p].pts) // 2)]
    assert R.KIND_DROP in kinds  # (the fall off the rim is a jump: its callout and the spell's)


DEADMINES_DOOR = (-11213.27, 1654.50)  # (Kooki3z's spot in front of the Deadmines' way in, build 3ae5a417)
DEADMINES_PORTAL = (-11208.7, 1675.9)


def test_in_front_of_the_deadmines_the_route_is_the_22_yards_there_not_round_the_hideout(game):
    # (standing at the way in, the route shown ran east along the lower tunnel, round the hideout's eastern caves and
    # back on the upper level, 295 yd, for as long as he stood there (the build before: 30 of 30 half seconds): the
    # Router's own by the caves' roads, its walk to the portal queued behind the planner's walks)
    lua, ns = game
    rows = _ride(lua, ns, DEADMINES_DOOR, DEADMINES_PORTAL, ticks=12, cont=0, step=0)
    assert all(r[1] is not None and r[1] <= 30 for r in rows[6:]), rows
    assert all(not r[2] or r[1] <= r[3] + 1 for r in rows), rows


# The Wailing Caverns (Kooki3z 2026-11-23, build 8921e21f; the "all 5 floors" map): from outside the cave's mouth in
# the oasis to the instance's portal the route went east over the ground above and came back down through it into the
# caverns' east lobe. Interiors only through their entrances: in at the mouth, north up the west tunnels, across the
# top and down to the portal; never up on the ground over the caverns (85 to 165 there; the tunnels 82 down to 18)
WC_MOUTH, WC_PORTAL = (-846.0, -2003.0), (-738.5, -2217.8)


def test_from_the_oasis_the_wailing_caverns_portal_is_never_routed_over_the_ground(game):
    # (the grid's tunnels don't reach the portal's floor, z 19, from the mouth yet (a gap in its data, logged): "No way
    # found yet", never the Router's own route, nor one over the ground; the tunnels walked once the data links them)
    lua, ns = game
    N, R = ns.Nav, ns.Router
    st = ns.settings.gps
    st.worldGrid = True
    lua.execute("UnitFactionGroup = function() return 'Horde' end")
    ns.CharDB().faction = "Horde"
    try:
        R.Reset()
        N.Clear()
        lua.execute(f"AGPS_POS = {{ {WC_MOUTH[0]}, {WC_MOUTH[1]}, 1 }}")
        N.SetStops(lua.eval(f"{{ {{ x = {WC_PORTAL[0]}, y = {WC_PORTAL[1]}, cont = 1, name = 'stop' }} }}"), False, "red")
        r = N.Route(WC_MOUTH[0], WC_MOUTH[1], 1)
        if r is None:
            assert N.noWayGrid and any(math.dist((g.x2, g.y2), WC_PORTAL) < 1 for g in _gaps(ns))
        else:
            pts, zs = [], []
            for j in range(1, len(r.parts) + 1):
                p = r.parts[j]
                pts += [(p.pts[i], p.pts[i + 1]) for i in range(1, len(p.pts), 2)]
                h = p.zs or p.fz
                zs += [h[i] for i in range(1, len(h) + 1) if h[i] is not None] if h is not None else []
            assert not r.pending and math.dist(pts[-1], WC_PORTAL) < 5
            assert zs and max(zs[3:]) <= 95, max(zs)  # (past the mouth's first steps: down in the tunnels)
    finally:
        st.worldGrid = False
        N.Clear()
    # (and every route shown meanwhile, the line aside: never east over the ground from the mouth, x under -700 with
    # y -2090 to -2200, the ground's way to the east lobe. Since 48a626d9 the stop is reached by the cave's own road
    # from the mouth (WorldGrid.CaveLeg), which passes under that ground, 150 yd down: only a point at most 10 yd
    # under the ground there, or with no height, is over it)
    routes = []
    _ride(lua, ns, WC_MOUTH, WC_PORTAL, ticks=20, cont=1, step=0, faction="Horde", routes=routes)
    over = []
    for t, r in enumerate(routes):
        if r.pending:
            continue
        for j in range(1, len(r.parts) + 1):
            p = r.parts[j]
            h = p.zs or p.fz
            for i in range(len(p.pts) // 2):
                x, y = p.pts[2 * i + 1], p.pts[2 * i + 2]
                if x < -700 and -2200 < y < -2090:
                    z, g = (h[i + 1] if h is not None else None), R.GroundZ(1, x, y)
                    if z is None or g is None or z > g - 10:
                        over.append((t, round(x), round(y), z, g))
    assert routes and over == [], over[:5]


# Kooki3z's video (2026-11-23, build 6526d718; a level 25 character with Walk on Air, Expert jumper): from the Barrens'
# hills by Northwatch Hold down to Bluefen in Dustwallow. "the only expected route suggestion should've been the last
# one, the others suggested impossible scaling or going all the way around": round by the coast (1.6k, then 4.9k yd),
# and the Router's own spell jumps, straight lines up hills that can't be climbed to a 109 yd jump. The right one, from a
# hilltop, "Jump down here", 84 yd down. And once landed, "Working out the route..." for ~45 s for the 209 yd left.
# Now: the grid's walk only (no Router's own, no spell jump of its own), its climbs its walked links, the fall off the
# ridge one of its falls (WorldGrid.FarDrops, one way down); once landed, the walk left in a second or two
NW_START, NW_HILLTOP, NW_LANDING, BLUEFEN = (-2002.0, -3457.0), (-2327.0, -3217.0), (-2466.0, -3180.0), (-2674.0, -3125.0)


def _settle_at(lua, ns, spots, stop, now):
    """The player at each of `spots` [(x, y, ticks)] in turn, the background pumped as _ride's: [(spot index, tick there,
    route)] for each tick."""
    R, N = ns.Router, ns.Nav
    out, t = [], 0
    for si, (x, y, ticks) in enumerate(spots):
        for k in range(ticks):
            lua.execute(f"AGPS_POS = {{ {x}, {y}, 1 }}; AGPS_T = {t * TICK_S}")
            t += 1
            r = N.Route(x, y, 1)
            t0 = now()
            while R.HasWork() and now() - t0 < SLICE_MS:
                res = R.Pump(now() + 4, now)
                done, fixed = res if isinstance(res, tuple) else (res, None)
                if done:
                    N.SearchDone(fixed)
            out.append((si, k, r))
    return out


def test_from_northwatch_s_hills_to_bluefen_the_grid_s_jump_and_a_quick_walk_once_landed(game):
    lua, ns = game
    st, R, N, WG = ns.settings.gps, ns.Router, ns.Nav, ns.WorldGrid
    was = (st.safeDropYd, st.expertJumper, st.worldGrid, st.cityGrid)
    st.safeDropYd, st.expertJumper, st.worldGrid, st.cityGrid = 39, True, True, True
    lua.execute("AGPS_SPELLS_WAS = { IsPlayerSpell, GetItemCount }; IsPlayerSpell = function(id) return id == 1259416 end; "
                "GetItemCount = function() return 0 end")  # (Walk on Air)
    ns.FallSpells.Refresh()
    lua.execute("UnitFactionGroup = function() return 'Alliance' end")
    ns.CharDB().faction = "Alliance"
    now = lua.eval("function() return os.clock() * 1000 end")
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    R.Reset()
    R.SYNC_WALKS = False
    try:
        N.Clear()
        N.SetStops(lua.eval(f"{{ {{ x = {BLUEFEN[0]}, y = {BLUEFEN[1]}, cont = 1, name = 'stop' }} }}"), False, "red")
        rows = _settle_at(lua, ns, [(*NW_START, 60), (*NW_HILLTOP, 20), (*NW_LANDING, 12)], BLUEFEN, now)
    finally:
        while R.HasWork():
            R.Pump(now() + 50, now)
        R.SYNC_WALKS = True
        lua.execute("IsPlayerSpell, GetItemCount = AGPS_SPELLS_WAS[1], AGPS_SPELLS_WAS[2]")
        st.safeDropYd, st.expertJumper, st.worldGrid, st.cityGrid = was
        ns.FallSpells.Refresh()
        N.Clear()

    def kinds(r):
        out = []
        for p in range(1, len(r.parts) + 1):
            k = r.parts[p].kinds
            out += [k[i] for i in range(1, len(k) + 1)] if k else []
        return out
    # (every route shown: the grid's, or the line while it works; never round by the coast, never the Router's own)
    for si, k, r in rows:
        assert r is not None
        spot = (NW_START, NW_HILLTOP, NW_LANDING)[si]
        straight = math.dist(spot, BLUEFEN)
        assert (r.pending and r.totalYards <= straight + 1) or (not r.pending and r.totalYards <= 1.8 * straight + 50), \
            (si, k, r.totalYards, straight)
    start = [r for si, _k, r in rows if si == 0 and not r.pending]
    assert start and R.KIND_DROP in kinds(start[-1])  # (from the start: off the hills by a jump, not round)
    hill = [r for si, _k, r in rows if si == 1]
    # (on the hilltop: "Jump down here" within 2 s, its own short search when the way from the start
    # went by another spot of the ridge)
    assert any(not r.pending and R.KIND_DROP in kinds(r) for r in hill[:4]), \
        [(r.pending, round(r.totalYards)) for r in hill[:4]]
    landed = [(k, r) for si, k, r in rows if si == 2]
    settled = [k for k, r in landed if not r.pending]
    assert settled and settled[0] <= 4, [(k, r.pending, r.totalYards) for k, r in landed]  # (2 s at most, not 45)


def test_the_grid_s_way_off_northwatch_s_hills_climbs_only_its_walked_links(game):
    # (no "impossible scaling": every piece up is the grid's own walked link (under its 55 degree walk slope); the falls
    # one way down only)
    lua, ns = game
    WG, R = ns.WorldGrid, ns.Router
    c = WG.Cont(1)
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    r = WG.Walk(c, NW_START[0], NW_START[1], None, BLUEFEN[0], BLUEFEN[1], None, lua.table(maxDrop=1000))
    k = [r.kinds[i] for i in range(1, len(r.kinds) + 1)]
    z = [r.fz[i] for i in range(1, len(r.fz) + 1)]
    p = [r.pts[i] for i in range(1, len(r.pts) + 1)]
    for i, kk in enumerate(k):
        seg = math.dist((p[2 * i], p[2 * i + 1]), (p[2 * i + 2], p[2 * i + 3]))
        dz = z[i + 1] - z[i]
        if kk == R.KIND_DROP:
            assert dz < 0, (i, dz)
        elif seg > 0:
            assert dz / seg <= math.tan(math.radians(55)), (i, round(dz), round(seg))


# Kooki3z's video (2026-11-23, build 6526d718; a warrior with Walk on Air, its only fall spell, ready; Expert jumper):
# from Tanaris' sands by the west rim (map 38.1, 22.6) to Un'Goro, 894 yd. "Working out the route..." for over a minute,
# then walking on toward the ledge the route flipped to 5.2k yd by Gadgetzan's flight. The jump ban the spell-jump
# planner sets to weigh the walk round is a wall (Router.WallsChanged): it dropped the world grid's searches without a
# word, they stayed in its list, and every walk to the stop waited on them for good
WARRIOR_SANDS, WARRIOR_STOP = (-6915.0, -2848.0), (-6830.0, -1975.0)


def _walk_on_air(lua, ns, cd=0):
    st = ns.settings.gps
    st.safeDropYd, st.expertJumper, st.cityGrid = 39, True, True
    lua.execute("AGPS_SPELLS_WAS = { IsPlayerSpell, GetItemCount, GetSpellCooldown }; "
                "IsPlayerSpell = function(id) return id == 1259416 end; GetItemCount = function() return 0 end; "
                f"AGPS_CD0 = 0; GetSpellCooldown = function(id) if id == 1259416 and {cd} > 0 then "
                f"return AGPS_CD0, {cd}, 1 end return 0, 0, 1 end")
    ns.FallSpells.Refresh()


def _spells_back(lua, ns):
    lua.execute("IsPlayerSpell, GetItemCount, GetSpellCooldown = AGPS_SPELLS_WAS[1], AGPS_SPELLS_WAS[2], AGPS_SPELLS_WAS[3]")
    st = ns.settings.gps
    st.safeDropYd, st.expertJumper, st.cityGrid = 39, False, False
    ns.FallSpells.Refresh()


@pytest.mark.parametrize("cd", [0, 45])
def test_a_warrior_s_walk_on_air_trip_off_tanaris_rim_settles_and_never_flips_to_the_loop(game, cd):
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    _walk_on_air(lua, ns, cd)
    try:
        rows = _ride(lua, ns, WARRIOR_SANDS, WARRIOR_STOP, ticks=150, step=4, faction="Horde")
    finally:
        _spells_back(lua, ns)
    settled = [t for t, yd, pending, _ in rows if yd is not None and not pending]
    # (within 22 s of the test's 30 ms a second, the game's is more; with the spell's cooldown to wait out the planner
    # weighs the walk round at each ledge spot in turn, a search each, so longer (wall-clock slices: loaded PCs slower))
    assert settled and settled[0] <= (45 if cd == 0 else 120), rows[-1]
    # (never the loop by Gadgetzan's flight, 5.2k, walking toward the ledge: about the line over the rim)
    assert all(yd is not None and yd <= 1.3 * left + 120 for _t, yd, _p, left in rows), \
        [(t, yd, left) for t, yd, _p, left in rows if yd is None or yd > 1.3 * left + 120][:3]
    if cd == 0:
        assert not rows[-1][2]  # (and settled again at the end, not waiting on a search that's gone)


def test_walls_changed_drops_the_world_grid_s_searches_with_a_word(game):
    # (a jump ban or a wall drawn mid-search: the grid's own list and count let go of the searches the Router dropped,
    # and the walk to the stop is searched again, never waited on for good)
    lua, ns = game
    R, WG = ns.Router, ns.WorldGrid
    st = ns.settings.gps
    st.worldGrid = True
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    R.Reset()
    R.SYNC_WALKS = False
    try:
        assert R.Route(1, WARRIOR_SANDS[0], WARRIOR_SANDS[1], WARRIOR_STOP[0], WARRIOR_STOP[1], lua.table()).pending
        assert WG.jobCount == 1
        R.WallsChanged()
        assert WG.jobCount == 0 and next(iter(WG.jobs.keys()), None) is None
        assert R.Route(1, WARRIOR_SANDS[0], WARRIOR_SANDS[1], WARRIOR_STOP[0], WARRIOR_STOP[1], lua.table()).pending
        assert R.HasWork() and WG.jobCount == 1  # (searched again)
    finally:
        now = lua.eval("function() return os.clock() * 1000 end")
        while R.HasWork():
            R.Pump(now() + 50, now)
        R.SYNC_WALKS = True
        st.worldGrid = False


# Kooki3z 2026-11-23 (a mage with Slow Fall; screenshot): from the Field of Giants in the Southern Barrens (map 43.0,
# 70.1) to the Rolling Plains north-west (map ~29, 56) the route went straight up the ridge west of the Field of
# Giants, then "Cast Slow Fall, then jump down, 49 yd down": up a hill that can't be climbed. That was the Router's own
# spell-jump route (SpellJumpOwn's straight legs), not the grid's; with world routing on the leg is the grid's only,
# whose climbs are its walked links
FIELD_OF_GIANTS, ROLLING_PLAINS = (-2986.4, -1649.8, 121.9), (-2171.0, -316.0)


def test_from_the_field_of_giants_a_slow_fall_mage_is_never_routed_up_the_ridge(game):
    lua, ns = game
    R, WG, st = ns.Router, ns.WorldGrid, ns.settings.gps
    st.worldGrid = True
    lua.execute("AGPS_SPELLS_WAS = { IsPlayerSpell, GetItemCount }; IsPlayerSpell = function(id) return id == 130 end; "
                "GetItemCount = function(id) return id == 17056 and 5 or 0 end")  # (Slow Fall, Light Feathers)
    ns.FallSpells.Refresh()
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    try:
        a, b = FIELD_OF_GIANTS, ROLLING_PLAINS
        N = ns.Nav
        N.Clear()
        lua.execute(f"AGPS_POS = {{ {a[0]}, {a[1]}, 1 }}")
        N.SetStops(lua.eval(f"{{ {{ x = {b[0]}, y = {b[1]}, cont = 1, name = 'stop' }} }}"), False, "red")
        r = N.Route(a[0], a[1], 1)
        assert r and not r.pending
        for j in range(1, len(r.parts) + 1):
            part = r.parts[j]
            h = part.fz or part.zs
            if h is None:
                continue
            k = [part.kinds[i] for i in range(1, len(part.kinds) + 1)]
            z = [h[i] for i in range(1, len(h) + 1)]
            p = [part.pts[i] for i in range(1, len(part.pts) + 1)]
            for i, kk in enumerate(k):
                seg = math.dist((p[2 * i], p[2 * i + 1]), (p[2 * i + 2], p[2 * i + 3]))
                if kk != R.KIND_DROP and seg > 0 and z[i] and z[i + 1]:
                    assert (z[i + 1] - z[i]) / seg <= math.tan(math.radians(55)), (j, i, round(z[i]), round(z[i + 1]), round(seg))
        # (and as in the game, the searches in the background: no route shown meanwhile jumps off that ridge either)
        WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
        routes = []
        _ride(lua, ns, a[:2], b, ticks=40, step=0, faction="Horde", routes=routes)
        jumps = [t for t, rr in enumerate(routes) if rr is not None and any(
            R.KIND_DROP in [rr.parts[j].kinds[i] for i in range(1, len(rr.parts[j].kinds) + 1)]
            for j in range(1, len(rr.parts) + 1) if rr.parts[j].kinds)]
        assert jumps == [], jumps[:5]
    finally:
        ns.Nav.Clear()
        lua.execute("IsPlayerSpell, GetItemCount = AGPS_SPELLS_WAS[1], AGPS_SPELLS_WAS[2]")
        ns.FallSpells.Refresh()
        st.worldGrid = False


@pytest.mark.parametrize("cd", [0, 45])
def test_a_warrior_s_walk_on_air_trip_settles_within_about_3_s_of_the_game_s_background(game, cd):
    # (Kooki3z 2026-11-23 on dbec4ca9: "tanaris is working as intended just slow to make a decision", 20-60 s of
    # "Working out the route...": the spell-jump planner banned the rim spot by spot (Nav.CheckSpellJumps), a grid
    # search each, and then searched the trip once more without spell jumps. Settled for good within 60 of the test's
    # 15 ms slices: 900 ms of background, about 3 s at the game's ~5 ms a frame while a route lands)
    lua, ns = game
    WG = ns.WorldGrid
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    _walk_on_air(lua, ns, cd)
    try:
        rows = _ride(lua, ns, WARRIOR_SANDS, WARRIOR_STOP, ticks=90, step=4, faction="Horde")  # (walking to the rim)
    finally:
        _spells_back(lua, ns)
    pending = [t for t, _yd, p, _ in rows if p]
    assert len(pending) <= 60, [(t, round(yd or 0), p) for t, yd, p, _ in rows[::6]]  # (all the waiting, walking on)
    assert rows[-1][1] <= 1.3 * rows[-1][3] + 120, rows[-1]  # (over the rim, not round)
