"""The no-spell way round settles faster (item 27, Kooki3z on bbc4c8c4: with Use class spells / Expert jumper off the
Tanaris-to-Un'Goro trip took a long time to settle). Profiled from item 12's start and stop (a warrior, class spells
off; and on with Expert jumper off): 204k grid nodes in 4 searches, about 5 s of search. Two of them were the trip's
ride check walking from its start rounded 15 yd off the player's, its straight join onto the route found blocked
(WorldGrid's JoinBySearch now reaches it in a few nodes); and each walk was searched again with no road preference
though only 215 of its 3.4k yd were road (WorldGrid.ROAD_DETOUR_SLACK's bound: only when the roads could make it so).
Now 62k nodes, one search. Budget: nodes, not the clock (wall-clock flags under load)."""

import pytest

from test_map_redraw import game  # noqa: F401
from test_stand_in import WARRIOR_SANDS, WARRIOR_STOP, _ride

NODE_BUDGET = 90000


@pytest.mark.parametrize("spells", [False, True], ids=["class_spells_off", "spell_on_expert_off"])
def test_the_way_round_settles_within_the_node_budget(game, spells):  # noqa: F811
    lua, ns = game
    st, WG = ns.settings.gps, ns.WorldGrid
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    saved = (st.safeDropYd, st.cityGrid, st.useClassSpells, st.expertJumper, st.avoidElites)
    st.safeDropYd, st.cityGrid, st.useClassSpells, st.expertJumper = 39, True, spells, False
    # (the elite areas off, item 91: the start is among Tanaris' level 42-46 elites, which the harness's level 14
    # avoids, a search round them on top of the budget measured here for item 27's trip)
    st.avoidElites = False
    lua.execute("AGPS_NS_SW = { IsPlayerSpell, GetItemCount }; IsPlayerSpell = function(id) return id == 1259416 end; "
                "GetItemCount = function() return 0 end")
    ns.FallSpells.Refresh()
    n0, s0 = WG.stats.nodes, WG.stats.searches
    try:
        rows = _ride(lua, ns, WARRIOR_SANDS, WARRIOR_STOP, ticks=400, step=0, faction="Horde")
    finally:
        lua.execute("IsPlayerSpell, GetItemCount = AGPS_NS_SW[1], AGPS_NS_SW[2]")
        st.safeDropYd, st.cityGrid, st.useClassSpells, st.expertJumper, st.avoidElites = saved
        ns.FallSpells.Refresh()
    settled = [(t, yd) for t, yd, pending, _ in rows if yd is not None and not pending]
    assert settled and 3000 < settled[-1][1] < 3800, rows[-1]  # (the way round, by the southern way down)
    assert WG.stats.nodes - n0 <= NODE_BUDGET, (WG.stats.nodes - n0, WG.stats.searches - s0)


def test_a_blocked_join_reaches_the_route_by_a_small_search(game):  # noqa: F811
    lua, ns = game
    R, WG = ns.Router, ns.WorldGrid
    st = ns.settings.gps
    was = st.worldGrid
    st.worldGrid = True
    WG.Set(True)
    try:
        R.Reset()
        c = WG.Cont(1)
        r = WG.Walk(c, WARRIOR_SANDS[0], WARRIOR_SANDS[1], None, WARRIOR_STOP[0], WARRIOR_STOP[1], None, lua.table())
        assert r and r.length > 1000
        j = WG.JoinBySearch(c, r, -6900.0, -2850.0, None, lua.table())
        assert j and abs(j.length - r.length) < 60 and j.pts[1] == -6900.0, (j and j.length, r.length)
    finally:
        st.worldGrid = was
        WG.Set(bool(was))
