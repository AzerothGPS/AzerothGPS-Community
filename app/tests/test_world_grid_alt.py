"""The world grid's landmark distance fields (item 33; WorldGrid.lua's WG.AltSearch, app/azerothgps/worldalt.py): shipped
in every region folder (Alt.lua, listed in its toc, the grid's own bake), loaded with the region, a bound never above
the true grid cost (sampled pairs, the exact search's own cost), and the long trips round rims and ridges within node
budgets (Tanaris' warrior with no spell, Bluefen, the Barrens)."""

import random
import re

import pytest

from test_map_redraw import game  # noqa: F401
from azerothgps.paths import REPO

ADDONS = REPO / "addon"
TANARIS_SANDS, UNGORO = (-6915.0, -2848.0), (-6830.0, -1975.0)
TAURAJO_EAST, BLUEFEN = (-2268.0, -2058.0), (-2800.0, -2780.0)
TAURAJO_FM, BRACKENWALL = (-2380.7, -1882.7), (-3083.3, -2850.0)


def _bake(cont):
    head = (ADDONS / "AzerothGPS" / "Data" / f"WorldGrid{cont}.lua").read_text(encoding="utf-8")
    return re.search(r'bake = "([^"]+)"', head).group(1)


def test_every_region_folder_ships_its_fields_from_the_grid_s_own_bake():
    # (the regions' folders: not AzerothGPS_WGHPA, HPA*'s ways, test_world_hpa.py)
    folders = sorted(p for p in ADDONS.glob("AzerothGPS_WG*") if p.is_dir() and re.match(r"AzerothGPS_WG\d+_", p.name))
    assert folders
    ns_seen = set()
    for f in folders:
        cont = int(re.match(r"AzerothGPS_WG(\d+)_", f.name).group(1))
        toc = (f / f"{f.name}.toc").read_text(encoding="utf-8")
        assert re.search(r"^Alt\.lua\s*$", toc, re.M), f.name
        alt = (f / "Alt.lua").read_text(encoding="utf-8")
        m = re.search(r'bake = "([^"]+)", n = (\d+)', alt)
        assert m and m.group(1) == _bake(cont), f.name
        ns_seen.add((cont, int(m.group(2))))
    for cont in {c for c, _ in ns_seen}:
        assert len({n for c, n in ns_seen if c == cont}) == 1  # (one landmark count a continent)


@pytest.fixture
def grid(game):  # noqa: F811
    lua, ns = game
    st, WG = ns.settings.gps, ns.WorldGrid
    saved = (st.worldGrid, st.useClassSpells, st.safeDropYd, st.roadTolerance)
    st.worldGrid, st.useClassSpells, st.safeDropYd, st.roadTolerance = True, False, 39, 0
    WG.Set(True)
    lua.execute("AGPS_ALT_SP = IsPlayerSpell; IsPlayerSpell = function() return false end")
    ns.FallSpells.Refresh()
    yield lua, ns, WG.Cont(1)
    st.worldGrid, st.useClassSpells, st.safeDropYd, st.roadTolerance = saved
    WG.Set(bool(saved[0]))
    lua.execute("IsPlayerSpell = AGPS_ALT_SP")
    ns.FallSpells.Refresh()
    WG.altOff, WG.HEUR = None, 1.1
    ns.Router.Reset()


def test_the_fields_load_with_the_region(grid):
    lua, ns, c = grid
    ns.WorldGrid.LoadRegion(c, 4, 4)
    assert c.alt and c.altN and c.altN >= 8


def _exact(lua, ns, c, a, b):
    """The exact search's cost from a to b (HEUR 1, no fields) and the fields' bound at a's surface."""
    WG = ns.WorldGrid
    starts = WG.Ends(c, a[0], a[1], None)
    ends = WG.Ends(c, b[0], b[1], None)
    if not (starts[1] and ends[1]):
        return None, None
    goals = lua.table()
    for i in range(1, len(ends) + 1):
        goals[ends[i].id] = ends[i].cost
    x = WG.Costs(c, a[0], a[1], b[0], b[1], lua.table())
    AB = WG.AltSearch(c, goals) if WG.AltAllowed(x) else None
    bound = None
    if AB:
        s = starts[1]
        bound = AB(int(s.id) // 131072, s.ci)
    WG.altOff, WG.HEUR = True, 1.0
    try:
        steps = WG.Search(c, starts, goals, b[0], b[1], None, x)
    finally:
        WG.altOff, WG.HEUR = None, 1.1
    return (WG.lastCost if steps else None), bound


def test_the_bound_never_passes_the_true_grid_cost(grid):
    lua, ns, c = grid
    rng = random.Random(33)
    pairs = [(TANARIS_SANDS, UNGORO), (TAURAJO_EAST, BLUEFEN), (TAURAJO_FM, BRACKENWALL)]
    for _ in range(9):  # (and random ones round Tanaris, Un'Goro and the Barrens)
        box = rng.choice([(-7600, -6200, -3600, -1000), (-3200, -2000, -3000, -1700)])
        a = (rng.uniform(box[0], box[1]), rng.uniform(box[2], box[3]))
        b = (rng.uniform(box[0], box[1]), rng.uniform(box[2], box[3]))
        pairs.append((a, b))
    checked = 0
    for a, b in pairs:
        cost, bound = _exact(lua, ns, c, a, b)
        if cost is None or bound is None:
            continue
        assert bound <= cost + 1e-6, (a, b, bound, cost)
        checked += 1
    assert checked >= 6


# (node budgets with the fields, the walk searched once, about 1.2 times what they took at the bake of 2026-11-24:
# warrior 62k -> 41k, Bluefen 55k -> 53k, the Barrens 40k -> 25k; target ~3 s in game)
@pytest.mark.parametrize("a,b,budget", [(TANARIS_SANDS, UNGORO, 50000), (TAURAJO_EAST, BLUEFEN, 64000),
                                        (TAURAJO_FM, BRACKENWALL, 30000)], ids=["warrior", "bluefen", "barrens"])
def test_the_long_way_round_is_within_its_node_budget(grid, a, b, budget):
    lua, ns, c = grid
    WG = ns.WorldGrid
    WG.routes, WG.order, WG.targets = lua.table(), lua.table(), lua.table()
    n0 = WG.stats.nodes
    r = WG.Walk(c, a[0], a[1], None, b[0], b[1], None, lua.table())
    assert r and r.length > 1500
    assert WG.stats.nodes - n0 <= budget, WG.stats.nodes - n0
