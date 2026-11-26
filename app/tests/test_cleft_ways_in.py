"""Orgrimmar's Cleft of Shadow: only its two ways in (item 55b/c, Kooki3z 2026-11-24). With Expert jumper on, from the
Valley of Strength south of the bank (Orgrimmar map 49.9, 64.3) to the Warlock Trainer the route was 210 yd: drops off
the rock (28 yd down to 6, then to the Cleft's floor) read "Stairs down in 103 yd", through the wall. The Cleft's ways
in are its tunnel from the Valley of Strength and the Drag's; no drop lands in it (CityGrid.NO_DROP_IN), and a drop is
never stairs (Turns.Stairs)."""

import pytest

from test_map_redraw import game  # noqa: F401


def _world(ns, mapid, mx, my):
    b = ns.Maps[mapid].bounds
    return b[3] - my / 100 * (b[3] - b[1]), b[4] - mx / 100 * (b[4] - b[2])


@pytest.mark.parametrize("expert", [False, True], ids=["expert_off", "expert_on"])
def test_valley_of_strength_to_the_warlock_trainer_never_drops_into_the_cleft(game, expert):  # noqa: F811
    lua, ns = game
    R, st, CG = ns.Router, ns.settings.gps, ns.CityGrid
    saved = (st.cityGrid, st.worldGrid, st.expertJumper, st.useClassSpells)
    st.cityGrid, st.worldGrid, st.expertJumper, st.useClassSpells = True, True, expert, True
    CG.Set(True)
    ns.WorldGrid.Set(True)
    try:
        CG.routes, CG.order = lua.table(), lua.table()
        R.Reset()
        a, b = _world(ns, 1454, 49.9, 64.3), _world(ns, 1454, 48.3, 46.3)
        r = R.Route(1, a[0], a[1], b[0], b[1], lua.table(tz=-14.8))
        assert r.cityGrid == "Orgrimmar"
        kinds = [r.kinds[i] for i in range(1, len(r.kinds) + 1)]
        assert R.KIND_DROP not in kinds, kinds
        assert r.length > 400  # (the Drag's way in: 474 yd; the drop off the rock was 210)
    finally:
        st.cityGrid, st.worldGrid, st.expertJumper, st.useClassSpells = saved
        CG.Set(bool(saved[0]))
        R.Reset()


def test_a_drop_with_heights_is_never_stairs(game):  # noqa: F811
    lua, ns = game
    R = ns.Router
    pts = [(0, 0), (0, -100), (0, -104), (0, -200)]
    zs = [28, 28, 6, 6]
    part = lua.table(cont=20036, pts=lua.table(*[v for q in pts for v in q]), kinds=lua.table(0, R.KIND_DROP, 0),
                     stop=1, zs=lua.table(*zs))
    p = ns.Turns.Path(lua.table(parts=lua.table(part), legs=lua.table(lua.table(walk=True))))
    assert len(ns.Turns.Stairs(p)) == 0
    # (the same heights on a walked piece: stairs, as before)
    part2 = lua.table(cont=20036, pts=lua.table(*[v for q in pts for v in q]), kinds=lua.table(0, 0, 0),
                      stop=1, zs=lua.table(*zs))
    p2 = ns.Turns.Path(lua.table(parts=lua.table(part2), legs=lua.table(lua.table(walk=True))))
    assert len(ns.Turns.Stairs(p2)) == 1
