"""Azeroth Pilot Route (asked 2026-11-17: "can we add another leveling guide support like restedXP called Azeroth Pilot
Reloaded?"): with Azeroth Pilot Reloaded (APR) installed, a quick button routes to each step of its guide in turn, from
the place APR's arrow points at (APR.Arrow: Active, x and y in world yards swapped from ours); a step's stop is done
when APR moves on, never by getting there. The whole addon (gameharness) with a stand-in for APR's arrow and current
step, as Questify Route's tests."""
import pytest

pytest.importorskip("lupa.lua51")


def _game(apr=True, off=True):
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    lua.execute("AGPS_PRINTS = {} AGPS_NS.Print = function(m) AGPS_PRINTS[#AGPS_PRINTS + 1] = m end")
    if apr:
        # APR's arrow (x: east-west, y: north-south, UnitPosition's second and first) and its current step
        lua.execute("""
          AGPS_STEP = { index = 12, step = { title = "Turn in |cffffd100Vanquish the Betrayers|r" } }
          APR = { ActiveRoute = "Forever-Durotar",
            Arrow = { Active = true, x = 2270.0, y = 330.0 },
            GetCurrentStep = function(self) return AGPS_STEP.step, AGPS_STEP.index, {} end }
        """)
    if off:
        cdb = ns.CharDB()
        cdb.rxpFollow, cdb.zygorFollow, cdb.polestarFollow, cdb.questifyFollow, cdb.aprFollow = (
            False, False, False, False, False)
    return lua, ns


def _stops(ns):
    return [(round(d.x), round(d.y), d.cont, str(d.name), d.apr) for d in ns.Nav.stops.values()]


def test_the_button_is_there_only_with_azeroth_pilot():
    lua, ns = _game(apr=False)
    assert "aprRoute" not in [str(t.id) for t in ns.GPS.QuickSlots().values()]
    lua.execute("APR = { Arrow = { Active = false, x = 0, y = 0 } }")
    assert "aprRoute" in [str(t.id) for t in ns.GPS.QuickSlots().values()]


def test_each_step_is_the_next_stop_and_done_when_azeroth_pilot_moves_on():
    lua, ns = _game()
    N, A = ns.Nav, ns.AzerothPilot
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 300.0, 2200.0, 1")
    N.SetDestination(-9000.0, 400.0, 0, "Somewhere else")
    A.Toggle()
    assert A.On()
    s = _stops(ns)
    # (the arrow's y is our x, its x our y; on the player's continent; the step's text without its colors)
    assert len(s) == 1 and s[0][:3] == (330, 2270, 1)
    assert s[0][3] == "Azeroth Pilot: Turn in Vanquish the Betrayers"
    # getting there doesn't finish it
    lua.execute("AGPS_POS[1], AGPS_POS[2] = 330.0, 2270.0")
    A.Tick()
    assert len(_stops(ns)) == 1 and N.stops[1].apr
    # APR moves on: that stop done, the next one the stop (no text: "Step")
    lua.execute("AGPS_STEP.index = 13 AGPS_STEP.step = {} APR.Arrow.x, APR.Arrow.y = 2300.0, 360.0")
    A.Tick()
    s = _stops(ns)
    assert len(s) == 1 and s[0][:2] == (360, 2300) and s[0][3] == "Azeroth Pilot: Step"
    # no arrow, a step reached (its x set to 0), one with no place (0, 0): no stop, still following
    for setup in ("APR.Arrow.Active = false", "APR.Arrow.x = 0", "APR.Arrow.x, APR.Arrow.y = 0, 0"):
        lua.execute("APR.Arrow.Active, APR.Arrow.x, APR.Arrow.y = true, 2300.0, 360.0 " + setup)
        A.Tick()
        assert _stops(ns) == [] and A.On(), setup
    # kept over a /reload
    lua.execute("APR.Arrow.Active, APR.Arrow.x, APR.Arrow.y = true, 2310.0, 370.0")
    A.Tick()
    assert len(_stops(ns)) == 1
    N.Restore()
    A.lastKey = None
    A.Tick()
    assert len(_stops(ns)) == 1


def test_another_route_picked_turns_it_off():
    lua, ns = _game()
    N, A = ns.Nav, ns.AzerothPilot
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 300.0, 2200.0, 1")
    A.Toggle()
    assert len(_stops(ns)) == 1
    N.Clear()
    N.SetDestination(320.0, 2250.0, 1, "My own place")
    A.Tick()
    assert not A.On() and [str(d.name) for d in N.stops.values()] == ["My own place"]


def test_one_guide_at_a_time():
    lua, ns = _game()
    A = ns.AzerothPilot
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 300.0, 2200.0, 1")
    lua.execute("Questify = { Nav = { Status = function(self) return { target = { mapId = 1411, x = 52, y = 44 } } end } }")
    Q = ns.Questify
    A.Toggle()
    assert A.On()
    Q.Toggle()
    assert Q.On() and not A.On()
    A.Toggle()
    assert A.On() and not Q.On() and len(_stops(ns)) == 1 and _stops(ns)[0][4]


def test_azeroth_pilot_route_is_on_by_itself_and_the_other_guides_first():
    lua, ns = _game(off=False)
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 300.0, 2200.0, 1")
    A = ns.AzerothPilot
    assert A.On() and ns.CharDB().aprFollow is None
    A.Tick()
    assert len(_stops(ns)) == 1
    lua, ns = _game(off=False)
    lua.execute("RXPG_ARROW = { element = { wx = 330.0, wy = 2270.0, instance = 0, step = { index = 3, active = true } } }")
    A, X = ns.AzerothPilot, ns.RestedXP
    assert X.On() and not A.On()
    X.Toggle()
    assert not X.On() and A.On()
