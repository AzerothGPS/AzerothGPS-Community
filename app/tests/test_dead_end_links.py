"""A road's loose end linked to the roads near it that are far along the roads (Router.DeadEndLinks; issue #411).

Reported 2026-11-15 with two screenshots: Horde, Orgrimmar to Zephras Isle, the plan flew to Thunder Bluff and walked
9.8k yd round by the Barrens to Camp Gev'rek's zeppelin. The road up the gap north of the Wildmane Water Well to
Gev'rek ends in the gap, 600 yd over the plains from Thunder Bluff's roads; it's on the same network by the Barrens, so
no gap link joined it (those join pieces only), and the stop's and start's nearest roads were all Thunder Bluff's."""

import math

import pytest

LIFT_FOOT = (-1290.0, 140.0)  # (Thunder Bluff's lift, at its foot)
WELL = (-750.0, -150.0)  # (the Wildmane Water Well)
TOWER = (-802.0, 366.5)  # (Camp Gev'rek's zeppelin)


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    return lua, ns


def _route(lua, ns, a, b):
    R = ns.Router
    idle = lua.eval("function() return 0 end")
    r = R.Route(1, a[0], a[1], b[0], b[1])
    for _ in range(50):
        if not r.pending:
            break
        while R.HasWork():
            R.Pump(1e18, idle)
        r = R.Route(1, a[0], a[1], b[0], b[1])
    assert not r.pending and not r.unconnected
    return r


@pytest.mark.parametrize("start", [LIFT_FOOT, WELL])
def test_thunder_bluff_to_camp_gevreks_zeppelin_goes_up_the_gap(game, start):
    lua, ns = game
    r = _route(lua, ns, start, TOWER)
    assert r.length < 3000, f"{r.length:.0f} yd (9.4k round by the Barrens)"
    pts = [(r.pts[i], r.pts[i + 1]) for i in range(1, len(r.pts), 2)]
    assert max(x for x, _ in pts) < 0, "north into the Barrens"  # (the gap's road tops out about x -324)


def test_orgrimmar_to_zephras_isle_walks_from_thunder_bluff_up_the_gap(game):
    lua, ns = game
    N, G = ns.Nav, ns.GPS
    cdb = ns.CharDB()
    cdb.faction = "Horde"
    cdb.taxiNodes = lua.eval("{ [1414] = { nodes = { { nodeID = 23, known = true }, { nodeID = 22, known = true } } } }")
    N.FlightsChanged()
    lua.execute("AGPS_MAP = 1454; AGPS_POS = { 1676, -4313, 1 }")
    N.SetStops(lua.eval("{ { x = 1952, y = 1017, cont = 2991 } }"), False, "red")
    for _ in range(30):
        lua.execute("AGPS_T = (AGPS_T or 1000) + 0.5")
        G.Update()
    steps = N.StepsText(99)
    assert "Thunder Bluff" in steps and "Camp Gev'rek" in steps, steps
    walks = [float(m.replace("k", "")) * (1000 if "k" in m else 1)
             for m in __import__("re").findall(r"Walk ([\d.]+k?) yd", steps)]
    assert walks and max(walks) < 3000, steps  # (was 3.1k and 6.6k round by the Barrens)


def test_a_loose_roads_end_gets_links_only_to_roads_far_along_the_roads(game):
    lua, ns = game
    _route(lua, ns, WELL, TOWER)
    g = ns.Router.DebugGraph(1)
    n_ = g.n

    def node_at(x, y):
        return min(range(1, len(n_) // 2 + 1), key=lambda i: math.dist((n_[2 * i - 1], n_[2 * i]), (x, y)))

    end = node_at(-476.8, 10.3)  # (the gap road's end)
    links = [b for b in (g.bridges[end] or {}).values() if b.deadEnd]
    assert 1 <= len(links) <= ns.Router.DEAD_END_LINKS
    assert all(b[2] <= ns.Router.DEAD_END_LINK_YD for b in links)
    # (not to the gap road's own next node, 221 yd along it)
    assert node_at(-324.2, 170.2) not in [b[1] for b in links]



def test_with_walks_in_the_background_the_route_goes_up_the_gap_meanwhile():
    # (AzerothGPS#420, QA of 706fb62: a Tauren with no flight paths, Teleport: Thunder Bluff, Orgrimmar to
    # Zephras Isle: "Walk 2.9k yd, learn the flight path at Camp Taurajo, walk 6.6k yd to the zeppelin". In game the
    # loose end's walk is searched in the background over seconds; the route meanwhile left its link out, so it went
    # round the Barrens until then. The tests above search walks at once)
    from azerothgps.gameharness import start
    lua, ns = start()  # (its own: no walk searched yet)
    N, G, R = ns.Nav, ns.GPS, ns.Router
    N.FUN = False
    R.SYNC_WALKS = False
    cdb = ns.CharDB()
    cdb.faction = "Horde"
    lua.execute("""
      UnitRace = function() return "Tauren", "Tauren" end
      IsPlayerSpell = function(id) return id == 3566 end
      GetItemCount = function(id) return id == 17031 and 5 or 0 end
      if C_Item then C_Item.GetItemCount = GetItemCount end
      if AGPS_NS.Teleports.Changed then AGPS_NS.Teleports.Changed() end
    """)
    N.FlightsChanged()
    lua.execute("AGPS_MAP = 1454; AGPS_POS = { 1676, -4313, 1 }")
    N.SetStops(lua.eval("{ { x = 1952, y = 1017, cont = 2991 } }"), False, "red")
    # (frames until the background searches go quiet, not a fixed count: on a loaded CI runner each frame's slice of
    # search (wall-clock, GPSFrame.PumpBudget) does less, and 400 frames weren't always enough. The steps read as the
    # frame draws them, right after G.Update: read after the pump, a search just landed (Nav.SearchDone) left them
    # empty until the next frame's update, and the 400th frame was such a one on CI, run 45764259051)
    # (the first frames' plans skipped, as before: the very first is made before any walk is in)
    shown, busy, quiet = [], [], 0
    for i in range(20000):
        lua.execute("AGPS_T = (AGPS_T or 1000) + 0.05")
        G.Update()
        steps = N.StepsText(99)
        G.PumpSearches()
        quiet = 0 if R.HasWork() else quiet + 1
        if i >= 5:
            shown.append(steps)
            busy.append(quiet == 0)
        if quiet >= 40:
            break
    assert quiet >= 40, "the background searches never went quiet"
    assert "Thunder Bluff" in shown[-1] and "Camp Gev'rek" in shown[-1], shown[-1]
    # (a plan up meanwhile: shown while the walks were still searched, and every frame from then on)
    first = next(i for i, s in enumerate(shown) if "Walk" in s)
    assert any(busy[first:]), "the plan only came once the background searches were done"
    assert all("Walk" in s for s in shown[first:]), "a frame without the plan"
    for steps in shown:
        assert "Camp Taurajo" not in steps, steps  # (round the Barrens, before the walk was in)
        walks = [float(m.replace("k", "")) * (1000 if "k" in m else 1)
                 for m in __import__("re").findall(r"Walk ([\d.]+k?) yd", steps)]
        assert not walks or max(walks) < 3000, steps  # (none yet: the plan still worked out)
