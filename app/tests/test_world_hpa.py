"""HPA* over the world grid (item 127, 1.4.2; WorldHPA.lua, app/azerothgps/worldhpa.py): the tiles' ways ship in their
own load-on-demand folder (AzerothGPS_WGHPA, a file a continent, the grid's own bake, each tile's for its map data); a long leg searched tile to tile
in a small share of the nodes the grid's own search took, its way as cheap within a few percent of that search's best
in the same corridor; "no way" said at once from the tiles' ways at the bake's own drop limit, and nothing said for sure
at another (the grid's own search then)."""

import re

import pytest

from test_map_redraw import game  # noqa: F401
from azerothgps.paths import REPO

ADDONS = REPO / "addon"
TAURAJO, UNGORO = (-2292.7, -2142.6), (-7446.7, -1316.7)
RAZOR_HILL, CROSSROADS = (318.0, -4706.0), (-441.8, -2596.1)
DARKSHORE, FELWOOD = (5529.9, 308.6), (5322.0, -655.0)


def _bake(cont):
    head = (ADDONS / "AzerothGPS" / "Data" / f"WorldGrid{cont}.lua").read_text(encoding="utf-8")
    return re.search(r'bake = "([^"]+)"', head).group(1)


HPA_DIR = ADDONS / "AzerothGPS_WGHPA"


def test_the_ways_ship_in_their_own_load_on_demand_folder_from_the_grid_s_own_bake():
    toc = (HPA_DIR / "AzerothGPS_WGHPA.toc").read_text(encoding="utf-8")
    assert "## LoadOnDemand: 1" in toc and "## Dependencies: AzerothGPS" in toc
    assert [ln for ln in toc.splitlines() if ln and not ln.startswith("#")] == ["Hpa0.lua", "Hpa1.lua", "Hpa2991.lua"]
    main = (ADDONS / "AzerothGPS" / "AzerothGPS.toc").read_text(encoding="utf-8")
    iface = re.search(r"^## Interface: *(\S+)", main, re.M).group(1)
    assert f"## Interface: {iface}" in toc
    for cont in (0, 1, 2991):
        text = (HPA_DIR / f"Hpa{cont}.lua").read_text(encoding="utf-8")
        m = re.search(r'all\[(\d+)\] = \{ bake = "([^"]+)", road = ([\d.]+), swim = ([\d.]+), drop = (\d+)', text)
        assert m and int(m.group(1)) == cont and m.group(2) == _bake(cont), cont
        assert int(m.group(5)) == 39


def test_every_tile_s_ways_are_for_its_shipped_map_data():
    """A region baked again since (its surfaces renumbered) needs `agps world-grid hpa --write`: WorldHPA.lua's HP.Fresh
    leaves a stale tile's ways out, so the long legs there lose HPA*."""
    from azerothgps import worldhpa
    tile = re.compile(r'^  \[(\d+)\] = "([^"]*)",$', re.M)
    alpha = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"

    def num(v):
        n = 0
        for ch in v:
            n = n * 64 + alpha.index(ch)
        return n
    checked = 0
    for cont in (0, 1, 2991):
        raw = {}
        for f in ADDONS.glob(f"AzerothGPS_WG{cont}_*"):
            raw.update(tile.findall((f / "Data.lua").read_text(encoding="utf-8")))
        ways = tile.findall((HPA_DIR / f"Hpa{cont}.lua").read_text(encoding="utf-8"))
        assert {k for k, _ in ways} == set(raw), cont  # (every tile of the grid: one with no ways as "none")
        for k, v in ways:
            assert (num(v[0:4]), num(v[4:6])) == worldhpa.check(raw[k]), (cont, k)
            checked += 1
    assert checked > 1000


def test_the_ways_are_well_under_the_size_budget():
    total = sum(f.stat().st_size for f in HPA_DIR.glob("Hpa*.lua"))
    assert total < 2.5e6, total


@pytest.fixture
def grid(game):  # noqa: F811
    lua, ns = game
    st, WG = ns.settings.gps, ns.WorldGrid
    saved = (st.worldGrid, st.useClassSpells, st.safeDropYd, st.roadTolerance, st.avoidHostile, st.avoidElites)
    # (the guards and elite areas not avoided: a leg past them is the grid's own search's, test_enemy_ground_trip.py)
    st.worldGrid, st.useClassSpells, st.safeDropYd, st.roadTolerance, st.avoidHostile, st.avoidElites = (
        True, False, 39, 0, False, False)
    WG.Set(True)
    lua.execute("AGPS_HPA_SP = IsPlayerSpell; IsPlayerSpell = function() return false end")
    ns.FallSpells.Refresh()
    yield lua, ns, WG.Cont(1)
    st.worldGrid, st.useClassSpells, st.safeDropYd, st.roadTolerance, st.avoidHostile, st.avoidElites = saved
    WG.Set(bool(saved[0]))
    lua.execute("IsPlayerSpell = AGPS_HPA_SP")
    ns.FallSpells.Refresh()
    WG.hpaOff = None
    ns.Router.Reset()


def _ends(lua, ns, c, a, b, opts=None):
    WG = ns.WorldGrid
    starts = WG.Ends(c, a[0], a[1], None)
    goals = lua.table()
    for e in WG.Ends(c, b[0], b[1], None).values():
        goals[e.id] = e.cost
    x = WG.Costs(c, a[0], a[1], b[0], b[1], opts or lua.table())
    # (the land's own costs: no guards, which send a leg near them to the grid's own search, test_enemy_ground_trip.py)
    x.side, x.exempt, x.light, x.block = None, None, None, None
    x.any = x.red is not None
    assert ns.WorldHPA.Load(c)
    return starts, goals, x


def test_the_ways_load_once_from_their_folder(grid):
    lua, ns, c = grid
    assert ns.WorldHPA.Load(c)
    assert c.hpa and c.hpaHead and c.hpaHead.drop == 39
    key = next(iter(c.hpa.keys()))
    d = ns.WorldHPA.TileData(c, key)
    assert d and len(d.E) + len(d.X) > 0


# (budgets about 1.1 times what they took at the bake of 2026-11-27: Un'Goro 42k nodes (the grid's own search 217k as
# 1.4.1 searched it), Felwood 33k (433k), the Crossroads 14k (16k))
@pytest.mark.parametrize("a,b,budget", [(TAURAJO, UNGORO, 46000), (RAZOR_HILL, CROSSROADS, 16000),
                                        (DARKSHORE, FELWOOD, 37000)], ids=["ungoro", "crossroads", "felwood"])
def test_a_long_leg_is_searched_tile_to_tile(grid, a, b, budget):
    lua, ns, c = grid
    WG, HP = ns.WorldGrid, ns.WorldHPA
    starts, goals, x = _ends(lua, ns, c, a, b)
    HP.debug = lua.table()
    try:
        steps = HP.Search(c, starts, goals, b[0], b[1], x)
    finally:
        log = [HP.debug[i] for i in range(1, len(HP.debug) + 1)]
        HP.debug = None
    assert steps and len(steps) > 50, (steps, log, dict(HP.stats.items()))
    nodes, cost = WG.lastNodes, WG.lastCost
    assert nodes <= budget, nodes
    # (as cheap as the grid's own first search as 1.4.1 made it, within a few percent: weighed HEUR_LONG on a long leg,
    # the whole budget on a short one)
    x0 = WG.Costs(c, a[0], a[1], b[0], b[1], lua.table())
    x0.side, x0.exempt, x0.light, x0.block = None, None, None, None
    x0.any = x0.red is not None
    if ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 >= WG.LONG_LEG_YD:
        x0.heur = WG.HEUR_LONG
    x0.wholeBudget, x0.noLimit = True, True
    old = WG.Search(c, starts, goals, b[0], b[1], None, x0)
    assert old
    assert cost <= WG.lastCost * 1.03, (cost, WG.lastCost)
    # (and the walk the leg takes: found tile to tile)
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    h0 = WG.stats.hpa or 0
    r = WG.Walk(c, a[0], a[1], None, b[0], b[1], None, lua.table())
    assert r and r.length > 1500
    if b == FELWOOD:  # (tile to tile only when the grid's own search is cut short: the others it finds, as 1.4.1)
        assert (WG.stats.hpa or 0) > h0


def test_the_steps_are_the_grid_s_own_moves(grid):
    lua, ns, c = grid
    WG, HP = ns.WorldGrid, ns.WorldHPA
    starts, goals, x = _ends(lua, ns, c, RAZOR_HILL, CROSSROADS)
    steps = HP.Search(c, starts, goals, CROSSROADS[0], CROSSROADS[1], x)
    assert steps
    ids = [int(steps[i].id) for i in range(1, len(steps) + 1)]
    assert len(set(ids)) == len(ids)  # (no surface twice: the tiles' refines put together end to end)
    for i in range(2, len(steps) + 1):  # (each step a link, a road link or a drop from the one before, or a neighbor)
        p, q = steps[i - 1], steps[i]
        pk, qk = int(p.id) // 131072, int(q.id) // 131072
        px, py = WG.Pt(c, WG.Tile(c, pk), int(p.id) - pk * 131072, p.ci)
        qx, qy = WG.Pt(c, WG.Tile(c, qk), int(q.id) - qk * 131072, q.ci)
        assert q.link or ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5 < 8.34 * 13, (i, px, py, qx, qy)


def test_no_way_between_the_tiles_is_said_at_once(grid):
    lua, ns, c = grid
    WG, HP = ns.WorldGrid, ns.WorldHPA
    starts, goals, x = _ends(lua, ns, c, TAURAJO, UNGORO)
    # (the stop's tile's ways in all left out: nothing reaches it)
    gk = next(int(k) // 131072 for k in goals.keys())
    d = HP.TileData(c, gk)
    saved = d.inAt
    d.inAt = lua.table()
    try:
        got = HP.Search(c, starts, goals, UNGORO[0], UNGORO[1], x)
        assert got is False
        assert WG.lastNodes < 15000
        # (and at another drop limit, nothing said for sure: the grid's own search's to tell)
        x.maxDrop, x.slopeDrop = 60, 60
        assert HP.Search(c, starts, goals, UNGORO[0], UNGORO[1], x) is None
    finally:
        d.inAt = saved


def test_a_player_s_own_roads_and_short_legs_keep_the_grid_s_own_search(grid):
    lua, ns, c = grid
    HP = ns.WorldHPA
    _, _, x = _ends(lua, ns, c, TAURAJO, UNGORO)
    assert HP.Usable(c, TAURAJO[0], TAURAJO[1], UNGORO[0], UNGORO[1], x)
    assert not HP.Usable(c, TAURAJO[0], TAURAJO[1], TAURAJO[0] + 300, TAURAJO[1], x)
    assert HP.Usable(c, TAURAJO[0], TAURAJO[1], TAURAJO[0] + 300, TAURAJO[1], x, True)  # (after the grid's own ran out)
    x.roadCells = lua.table()
    assert not HP.Usable(c, TAURAJO[0], TAURAJO[1], UNGORO[0], UNGORO[1], x)
