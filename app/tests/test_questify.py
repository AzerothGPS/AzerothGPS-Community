"""Questify Route (asked 2026-11-13: "add Polestar and Questify support like RestedXP"): with Questify installed, a
quick button routes to each step of its guide in turn, from the place Questify guides to (Questify.Nav:Status()'s
target; never a point picked by hand); a step's stop is done when Questify moves on, never by getting there. The whole
addon (gameharness) with a stand-in for Questify's navigation state, as Polestar Route's tests."""
import pytest

pytest.importorskip("lupa.lua51")


def _game(questify=True, off=True):
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    lua.execute("AGPS_PRINTS = {} AGPS_NS.Print = function(m) AGPS_PRINTS[#AGPS_PRINTS + 1] = m end")
    if questify:
        # Questify's navigation state: the step's target (uiMap, x and y 0-100, title), and whether it was picked by hand
        lua.execute("""
          AGPS_QF = { target = { mapId = 1411, x = 52, y = 44, title = "Turn in Vanquish the Betrayers" }, manual = false }
          Questify = { Nav = { Status = function(self)
            return { target = AGPS_QF.target, manual = AGPS_QF.manual, provider = "native" }
          end } }
        """)
    if off:
        cdb = ns.CharDB()
        cdb.rxpFollow, cdb.zygorFollow, cdb.polestarFollow, cdb.questifyFollow = False, False, False, False
    return lua, ns


def _stops(ns):
    return [(round(d.x), round(d.y), d.cont, str(d.name), d.questify) for d in ns.Nav.stops.values()]


def test_the_button_is_there_only_with_questify():
    lua, ns = _game(questify=False)
    assert "questifyRoute" not in [str(t.id) for t in ns.GPS.QuickSlots().values()]
    lua.execute("Questify = { Nav = { Status = function() return {} end } }")
    assert "questifyRoute" in [str(t.id) for t in ns.GPS.QuickSlots().values()]


def test_each_questify_step_is_the_next_stop_and_done_when_questify_moves_on():
    lua, ns = _game()
    N, Q = ns.Nav, ns.Questify
    where = ns.Import.ToStop(lua.eval("{ mapID = 1411, x = 52, y = 44 }"))
    N.SetDestination(-9000.0, 400.0, 0, "Somewhere else")
    Q.Toggle()
    assert Q.On()
    s = _stops(ns)
    assert len(s) == 1 and s[0][:3] == (round(where.x), round(where.y), 1)
    assert s[0][3] == "Questify: Turn in Vanquish the Betrayers"
    # getting there doesn't finish it
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {where.x}, {where.y}, 1")
    Q.Tick()
    assert len(_stops(ns)) == 1 and N.stops[1].questify
    # Questify moves on: that stop done, the next one the stop (no title: "Step")
    lua.execute("AGPS_QF.target = { mapId = 1411, x = 40, y = 30 }")
    Q.Tick()
    s = _stops(ns)
    assert len(s) == 1 and s[0][3] == "Questify: Step"
    # no target, or one the player picked on Questify's map: no stop, still following
    for setup in ("AGPS_QF.target = nil", "AGPS_QF.manual = true"):
        lua.execute("AGPS_QF.target = { mapId = 1411, x = 40, y = 30 } AGPS_QF.manual = false " + setup)
        Q.Tick()
        assert _stops(ns) == [] and Q.On(), setup
    # kept over a /reload
    lua.execute("AGPS_QF.manual = false AGPS_QF.target = { mapId = 1411, x = 45, y = 35, title = 'Kill raptors' }")
    Q.Tick()
    assert len(_stops(ns)) == 1
    N.Restore()
    Q.lastKey = None
    Q.Tick()
    assert len(_stops(ns)) == 1


def test_one_guide_at_a_time():
    lua, ns = _game()
    Q = ns.Questify
    lua.execute("""Polestar = { Nav = { GetTarget = function() return { map = 1411, x = 50, y = 50, stepIndex = 1 } end,
      GetTargetWorld = function() end } }""")
    P = ns.Polestar
    Q.Toggle()
    assert Q.On()
    P.Toggle()
    assert P.On() and not Q.On()
    Q.Toggle()
    assert Q.On() and not P.On() and len(_stops(ns)) == 1 and _stops(ns)[0][4]


def test_questify_route_is_on_by_itself_and_the_other_guides_first():
    lua, ns = _game(off=False)
    Q = ns.Questify
    assert Q.On() and ns.CharDB().questifyFollow is None
    Q.Tick()
    assert len(_stops(ns)) == 1
    lua, ns = _game(off=False)
    lua.execute("RXPG_ARROW = { element = { wx = 330.0, wy = 2270.0, instance = 0, step = { index = 3, active = true } } }")
    Q, X = ns.Questify, ns.RestedXP
    assert X.On() and not Q.On()
    X.Toggle()
    assert not X.On() and Q.On()
