"""A long trip across zones settles (item 38, Kooki3z 2026-11-24, video on 3c85cf49: an Alliance warrior at level 25
south of Camp Taurajo to Un'Goro, south-east of Fire Plume Ridge; after 3.5 minutes still the faded line). The one walk
is 10.4k yd round by Thousand Needles and Tanaris; the grid's search took 685k nodes (cap 200k: "No way found yet").
Now: no high-zone cost once he said yes to the prompt, and a long leg's search weighed (WorldGrid.HEUR_LONG) finds a way
in ~90k nodes, its best way searched again in the background (WG.Refine). Budget: nodes, not the clock."""

import pytest

from test_map_redraw import game  # noqa: F401

START, STOP = (-2292.7, -2142.6), (-7446.7, -1316.7)
NODE_BUDGET = 120000


@pytest.mark.parametrize("spells", [False, True], ids=["class_spells_off", "class_spells_on"])
def test_camp_taurajo_to_un_goro_settles_on_a_real_walk(game, spells):  # noqa: F811
    lua, ns = game
    R, N, WG, st = ns.Router, ns.Nav, ns.WorldGrid, ns.settings.gps
    saved = (st.worldGrid, st.cityGrid, st.roadTolerance, st.safeDropYd, st.useClassSpells, st.avoidHighZones,
             st.avoidHostile)
    st.worldGrid, st.cityGrid, st.roadTolerance, st.safeDropYd = True, True, 10, 60
    st.useClassSpells, st.avoidHighZones, st.avoidHostile = spells, True, True
    WG.Set(True)
    lua.execute("AGPS_38 = { UnitFactionGroup, IsPlayerSpell }; AGPS_LEVEL = 25; "
                "UnitFactionGroup = function() return 'Alliance' end; IsPlayerSpell = function() return false end")
    ns.CharDB().faction = "Alliance"
    ns.FallSpells.Refresh()
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    now = lua.eval("function() return os.clock() * 1000 end")
    R.Reset()
    R.SYNC_WALKS = False
    n0 = WG.stats.nodes
    settled = None
    try:
        N.Clear()
        lua.execute(f"AGPS_POS = {{ {START[0]}, {START[1]}, 1 }}")
        N.SetStops(lua.eval(f"{{ {{ x = {STOP[0]}, y = {STOP[1]}, cont = 1, name = 'stop' }} }}"), False, "red")
        lua.execute("AGPS_NS.Nav.redOk = { all = true }")  # (he said yes to the zones too high)
        for tick in range(600):
            lua.execute(f"AGPS_T = {tick * 0.5}")
            r = N.Route(START[0], START[1], 1)
            t1 = now()
            while R.HasWork() and now() - t1 < 15:
                res = R.Pump(now() + 4, now)
                done, fixed = res if isinstance(res, tuple) else (res, None)
                if done:
                    N.SearchDone(fixed)
            if r and not r.pending:
                settled = r
                break
        assert settled is not None and 9000 < settled.totalYards < 12500, settled and settled.totalYards
        assert WG.stats.nodes - n0 <= NODE_BUDGET, WG.stats.nodes - n0
    finally:
        while R.HasWork():
            R.Pump(now() + 50, now)
        R.SYNC_WALKS = True
        lua.execute("UnitFactionGroup, IsPlayerSpell = AGPS_38[1], AGPS_38[2]; AGPS_LEVEL = nil; AGPS_NS.Nav.redOk = {}")
        (st.worldGrid, st.cityGrid, st.roadTolerance, st.safeDropYd, st.useClassSpells, st.avoidHighZones,
         st.avoidHostile) = saved
        WG.Set(bool(saved[0]))
        ns.FallSpells.Refresh()
        N.Clear()
