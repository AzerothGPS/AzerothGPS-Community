"""A trip across the other faction's ground settles on the walk (item 51, Kooki3z 2026-11-24, a Horde orc at 60 in Dun
Morogh to north of Ironforge, ~3k yd: after ~165 s of "Working out the route..." a 24-minute hearth-and-zeppelin route).
Round the guards the grid's search ran out (the guard-free way is 11k yd, 476k nodes), the walk plan had no way and a
far-off plan won. Now a search round the guards is capped (WorldGrid.HOSTILE_CAP) and then the walk through them
searched (`throughGuards`)."""

import pytest

from test_map_redraw import game  # noqa: F401

START, STOP = (-5806.0, -417.6), (-3950.0, -2450.0)


def test_a_horde_60_in_dun_morogh_walks_not_hearths(game):  # noqa: F811
    lua, ns = game
    R, N, WG, st = ns.Router, ns.Nav, ns.WorldGrid, ns.settings.gps
    saved = (st.worldGrid, st.cityGrid, st.roadTolerance, st.safeDropYd, st.useClassSpells, st.avoidHostile)
    st.worldGrid, st.cityGrid, st.roadTolerance, st.safeDropYd, st.useClassSpells, st.avoidHostile = \
        True, True, 0, 39, True, True
    WG.Set(True)
    lua.execute("AGPS_51 = UnitFactionGroup; AGPS_LEVEL = 60; UnitFactionGroup = function() return 'Horde' end")
    ns.CharDB().faction = "Horde"
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    now = lua.eval("function() return os.clock() * 1000 end")
    R.Reset()
    R.SYNC_WALKS = False
    n0 = WG.stats.nodes
    settled = None
    try:
        N.Clear()
        lua.execute(f"AGPS_POS = {{ {START[0]}, {START[1]}, 0 }}")
        N.SetStops(lua.eval(f"{{ {{ x = {STOP[0]}, y = {STOP[1]}, cont = 0, name = 'stop' }} }}"), False, "red")
        for tick in range(800):
            lua.execute(f"AGPS_T = {tick * 0.5}")
            r = N.Route(START[0], START[1], 0)
            t1 = now()
            while R.HasWork() and now() - t1 < 15:
                res = R.Pump(now() + 4, now)
                done, fixed = res if isinstance(res, tuple) else (res, None)
                if done:
                    N.SearchDone(fixed)
            if r and not r.pending:
                settled = r
                break
        assert settled is not None
        rides = [settled.legs[i].ride for i in range(1, len(settled.legs) + 1) if settled.legs[i].ride]
        assert not rides and settled.totalYards < 7000, (len(rides), settled.totalYards)  # (walked, not hearthed)
        assert WG.stats.nodes - n0 <= 150000, WG.stats.nodes - n0
        # (item 53c: the way through guards asks "Take it?" first; yes keeps it)
        lua.execute("""
          AGPS_ASKED = nil
          AGPS_CH = AGPS_NS.GPS.ConfirmHostile
          AGPS_NS.GPS.ConfirmHostile = function(names, side, yes, no) AGPS_ASKED = { names = names, yes = yes } return true end""")
        try:
            # (as the game's frames go on: a search landing in the settling frame's own slice takes the route out
            # until the next frame works it out again, and the question waits for that frame; with the leg's best
            # way searched in a corridor, test_route_speed_140, searches land there far more often)
            asked = None
            for _ in range(20):
                N.Route(START[0], START[1], 0)
                N.CheckHostileRoute()
                while R.HasWork():
                    R.Pump(now() + 50, now)
                asked = lua.eval("AGPS_ASKED")
                if asked is not None:
                    break
            assert asked is not None and N.hostileAsking is not None
            asked.yes()
            assert N.hostileAsking is None and N.RiskAnswer(N.dest)
        finally:
            lua.execute("AGPS_NS.GPS.ConfirmHostile = AGPS_CH")
    finally:
        while R.HasWork():
            R.Pump(now() + 50, now)
        R.SYNC_WALKS = True
        lua.execute("UnitFactionGroup = AGPS_51; AGPS_LEVEL = nil")
        st.worldGrid, st.cityGrid, st.roadTolerance, st.safeDropYd, st.useClassSpells, st.avoidHostile = saved
        WG.Set(bool(saved[0]))
        N.Clear()


def test_a_way_round_the_guards_past_the_usual_detour_gives_way_to_the_way_through(game):  # noqa: F811
    """Item 53c: round the guards only within DETOUR_FACTOR / DETOUR_YD of the way through, else the way through (and
    Nav's "Take it?"). From item 51's spot with the cap raised the way round is found: 11.2k yd against 4.6k."""
    lua, ns = game
    R, WG, st = ns.Router, ns.WorldGrid, ns.settings.gps
    saved = (st.worldGrid, st.avoidHostile, WG.HOSTILE_CAP, WG.MAX_NODES, WG.NODES_BASE)
    st.worldGrid, st.avoidHostile = True, True
    WG.Set(True)
    lua.execute("AGPS_51 = UnitFactionGroup; AGPS_LEVEL = 60; UnitFactionGroup = function() return 'Horde' end")
    ns.CharDB().faction = "Horde"
    WG.HOSTILE_CAP, WG.MAX_NODES, WG.NODES_BASE = 1000000, 1000000, 1000000
    try:
        R.Reset()
        WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
        r = WG.Walk(WG.Cont(0), START[0], START[1], None, STOP[0], STOP[1], None, lua.table())
        assert r and r.throughGuards and r.length < 7000, r and (r.length, r.throughGuards)
    finally:
        lua.execute("UnitFactionGroup = AGPS_51; AGPS_LEVEL = nil")
        st.worldGrid, st.avoidHostile, WG.HOSTILE_CAP, WG.MAX_NODES, WG.NODES_BASE = saved
        WG.Set(bool(saved[0]))
        R.Reset()


def test_no_to_take_it_reroutes_round_the_guards(game):  # noqa: F811
    """Item 63b (Kooki3z: "Take it?" -> No and the route stayed through the enemy spot). From item 51's spot the way
    through Kharanos is taken and asked about; No: the trip worked out again round the guards (11k yd), not through."""
    lua, ns = game
    R, N, WG, st = ns.Router, ns.Nav, ns.WorldGrid, ns.settings.gps
    saved = (st.worldGrid, st.cityGrid, st.avoidHostile, WG.MAX_NODES, WG.NODES_BASE)
    st.worldGrid, st.cityGrid, st.avoidHostile = True, True, True
    WG.Set(True)
    lua.execute("AGPS_51 = UnitFactionGroup; AGPS_LEVEL = 60; UnitFactionGroup = function() return 'Horde' end")
    ns.CharDB().faction = "Horde"
    WG.MAX_NODES, WG.NODES_BASE = 1000000, 1000000
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    WG.failed, WG.failOrder = lua.table(), lua.table()
    now = lua.eval("function() return os.clock() * 1000 end")
    R.Reset()
    R.SYNC_WALKS = False

    clock = [1000.0]

    def settle():
        for tick in range(3000):
            clock[0] += 0.5  # (the game's clock goes on between the two answers)
            lua.execute(f"AGPS_T = {clock[0]}")
            r = N.Route(START[0], START[1], 0)
            t1 = now()
            while R.HasWork() and now() - t1 < 15:
                res = R.Pump(now() + 4, now)
                done, fixed = res if isinstance(res, tuple) else (res, None)
                if done:
                    N.SearchDone(fixed)
            if r and not r.pending:
                return r
        return None

    lua.execute("""
      AGPS_ASKED = nil
      AGPS_CH = AGPS_NS.GPS.ConfirmHostile
      AGPS_NS.GPS.ConfirmHostile = function(names, side, yes, no) AGPS_ASKED = { no = no } return true end""")
    try:
        N.Clear()
        lua.execute(f"AGPS_POS = {{ {START[0]}, {START[1]}, 0 }}")
        N.SetStops(lua.eval(f"{{ {{ x = {STOP[0]}, y = {STOP[1]}, cont = 0, name = 'stop' }} }}"), False, "red")
        r = settle()
        assert r is not None and r.totalYards < 7000  # (through Kharanos)
        N.CheckHostileRoute()
        while R.HasWork():
            R.Pump(now() + 50, now)
        asked = lua.eval("AGPS_ASKED")
        assert asked is not None
        asked.no(True)
        assert N.hostileAsking is None and N.RiskAnswer(N.dest) is False
        r = settle()
        assert r is not None
        hostile = lua.eval("function(x, y) local R = AGPS_NS.Router return R.HostileAt(0, x, y, 'H', nil) end")
        hits, info = [], []
        for pi in range(1, len(r.parts) + 1):
            part = r.parts[pi]
            pts = [(part.pts[i], part.pts[i + 1]) for i in range(1, len(part.pts), 2)]
            info.append((pi, round(part.length or 0) if part.length else None, len(pts), pts[0], pts[-1]))
            hits += [(round(x), round(y)) for x, y in pts[1:-1] if hostile(x, y)]
        rides = [str(r.legs[i].ride[8]) for i in range(1, len(r.legs) + 1) if r.legs[i].ride]
        import os
        if os.environ.get("ZO"):
            open(os.environ["ZO"], "w").write(f"yd {r.totalYards} rides {rides} parts {info} hits {hits[:10]}" + chr(10))
        # (round the guards: the long way, 11.3k yd, nowhere near Kharanos's guards the way through passed; past others
        # only where there's no way round them, the pass to the stop)
        near_kharanos = [h for h in hits if (h[0] + 5586) ** 2 + (h[1] + 482) ** 2 <= 300 ** 2]
        assert r.totalYards > 9000 and not near_kharanos, (r.totalYards, rides, near_kharanos[:5])
    finally:
        lua.execute("AGPS_NS.GPS.ConfirmHostile = AGPS_CH")
        while R.HasWork():
            R.Pump(now() + 50, now)
        R.SYNC_WALKS = True
        lua.execute("UnitFactionGroup = AGPS_51; AGPS_LEVEL = nil")
        st.worldGrid, st.cityGrid, st.avoidHostile, WG.MAX_NODES, WG.NODES_BASE = saved
        WG.Set(bool(saved[0]))
        N.Clear()
