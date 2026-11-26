"""A cliff by the Dun Algaz pass taken with Slow Fall is a spell jump from afar (item 88, Kooki3z 2026-11-25, a Horde
mage, Use class spells and Expert jumper on, the world grid; his spot Wetlands map 55.6, 83.3, between the Alliance
camps' two red guard zones, heading north). The route's first stretch went down the cliff drawn dotted, partly red,
with no cast step, and turned into the spell jump's coil only once he stood near the edge. The world grid's way off the
rim is a step down of a few yards, then the 187 yd fall, two drop pieces in a row; the fall was read at the run's top
alone (the step's), so the drop was a plain walk-down (Router.JumpCalledOut, Turns, the tooltip, Nav.SpellJumps). Now
the biggest fall along the run is the drop's (Router.DropFall). With no fall spell the way is through the pass (88c).
Through the other faction's guards only the color turns red: the coil stays a coil, a swim stays wavy (88d)."""

import pytest

from test_map_redraw import game  # noqa: F401
from test_spell_jumping import MAGE, feathers, trip, world_grid  # noqa: F401

pytest.importorskip("lupa")

WETLANDS = (-4904.17, -4525.00, -2147.92, -389.58)  # (uiMap 1437's bounds, Data/Maps.lua)


def wetlands(u, v):
    b = WETLANDS
    return b[2] - v * (b[2] - b[0]), b[3] - u * (b[3] - b[1])


HIS_SPOT = wetlands(0.556, 0.833)
NORTH = wetlands(0.556, 0.70)  # (north down the cliff, toward Thelgen Rock)
# (his spot, and further back from the edge and to either side: the same jump from each)
STARTS = [(0, 0), (-20, 0), (-40, 0), (0, 20), (-30, 25), (10, -10)]


def runs(ns, r):
    """Each drop on route r: (part, first piece, the drop's fall)."""
    R = ns.Router
    out = []
    for p in range(1, len(r.parts) + 1):
        part = r.parts[p]
        for i in range(1, len(part.pts) // 2):
            if part.kinds[i] == R.KIND_DROP and (i == 1 or part.kinds[i - 1] != R.KIND_DROP):
                dz = R.DropFall(part.pts, part.kinds, i)
                out.append((part, i, dz[0] if isinstance(dz, tuple) else dz))
    return out


@pytest.mark.parametrize("d", STARTS, ids=[f"{x}_{y}" for x, y in STARTS])
def test_a_mage_s_route_off_the_cliff_is_a_spell_jump_from_the_start(game, trip, world_grid, d):  # noqa: F811
    lua, ns = game
    R, G, N = ns.Router, ns.GPS, ns.Nav
    ns.settings.gps.expertJumper = True
    a = (HIS_SPOT[0] + d[0], HIS_SPOT[1] + d[1])
    r = trip("{}", MAGE, feathers(5), a=a, b=NORTH, cont=0, uimap=1437, faction="Horde")
    big = [(part, i, dz) for part, i, dz in runs(ns, r) if dz and dz > N.PlainSafeDrop() + 0.5]
    assert big and big[0][2] > 150, [(i, dz) for _, i, dz in runs(ns, r)]
    part, i, dz = big[0]
    k = i
    while part.kinds[k] == R.KIND_DROP:
        assert R.JumpCalledOut(part.pts, part.kinds, k), k  # (every piece of it a coil, none a dotted walk-down)
        k += 1
    # (its step from the start: "Jump down" with its fall, so the cast's)
    _, ms = ns.Turns.Ahead(r)
    m = [ms[j] for j in range(1, len(ms) + 1) if ms[j].kind == "drop"]
    assert m and m[0].dropYd > 150 and m[0].dist < 100, [(str(ms[j].kind), ms[j].dist) for j in range(1, len(ms) + 1)]
    assert len(N.SpellJumps(r)) >= 1
    G.Update()
    assert G.jumpSegN > 0
    info = G.JumpInfo(G.jumpSegs[1])
    assert info.dz > 150 and info.spell


def test_the_coil_through_the_guards_is_red_and_still_a_coil(game, trip, world_grid):  # noqa: F811
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    ns.settings.gps.expertJumper = True
    trip("{}", MAGE, feathers(5), a=HIS_SPOT, b=NORTH, cont=0, uimap=1437, faction="Horde")
    G.Update()
    red = lua.eval("function(c) return rawequal(c, AGPS_NS.Nav.HOSTILE_COLOR) end")
    cols = [red(G.jumpSegs[j].color) for j in range(1, G.jumpSegN + 1)]
    assert any(cols) and not all(cols), cols  # (red in their reach, its own color beyond)


def test_a_warrior_goes_through_the_pass_never_down_the_face(game, trip, world_grid):  # noqa: F811
    lua, ns = game
    N = ns.Nav
    ns.settings.gps.expertJumper = True
    for setup in (("IsPlayerSpell = function() return false end", feathers(0)),  # (a warrior)
                  (MAGE, feathers(5), "AGPS_NS.settings.gps.useClassSpells = false")):  # (88c: class spells off)
        try:
            r = trip("{}", *setup, a=HIS_SPOT, b=NORTH, cont=0, uimap=1437, faction="Horde")
            falls = [dz for _, _, dz in runs(ns, r) if dz]
            assert all(dz <= N.PlainSafeDrop() + 0.5 for dz in falls), falls
            assert r.totalYards > 600, r.totalYards  # (round by the pass, not the 390 yd off the cliff)
        finally:
            ns.settings.gps.useClassSpells = True


def test_a_swim_and_a_jump_through_the_guards_are_red_waves_and_a_red_coil(game, trip, world_grid):  # noqa: F811
    """88d: a stretch in the guards' reach swum is drawn wavy in red (never dotted), and the jump a red coil."""
    lua, ns = game
    G, N = ns.GPS, ns.Nav
    ns.settings.gps.expertJumper = True
    r = trip("{}", MAGE, feathers(5), a=HIS_SPOT, b=NORTH, cont=0, uimap=1437, faction="Horde")
    part = r.parts[1]
    walk = [i for i in range(1, len(part.pts) // 2) if part.kinds[i] in (0, 1) and N.HostileSpans(part, i)]
    assert walk
    lua.execute("AGPS_88 = AGPS_NS.Nav.SwimSpans")
    try:
        # (the first walk past the guards swum, as if over water)
        lua.execute(f"""local N = AGPS_NS.Nav
          N.SwimSpans = function(part, i) if part == AGPS_NS.Nav.route.parts[1] and i == {walk[0]} then return {{ 0, 1 }} end
            return false end""")
        G.Update()
        red = lua.eval("function(c) return rawequal(c, AGPS_NS.Nav.HOSTILE_COLOR) end")
        assert G.swimSegN > 0 and all(red(G.swimSegs[j].color) for j in range(1, G.swimSegN + 1))
        assert G.jumpSegN > 0 and any(red(G.jumpSegs[j].color) for j in range(1, G.jumpSegN + 1))
    finally:
        lua.execute("AGPS_NS.Nav.SwimSpans = AGPS_88")
