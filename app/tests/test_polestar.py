"""Polestar Route (asked 2026-11-13: "add Polestar ... support like RestedXP"): with Polestar installed, a quick button
routes to each step of its guide in turn, from the place Polestar's own arrow guides to (its documented API:
Polestar.Nav.GetTarget / GetTargetWorld, IsHeld, IsOverride); a step's stop is done when Polestar moves on, never by
getting there. The whole addon (gameharness) with a stand-in for Polestar's Nav, as Zygor Route's tests."""
import pytest

pytest.importorskip("lupa.lua51")


def _game(polestar=True, off=True):
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    lua.execute("AGPS_PRINTS = {} AGPS_NS.Print = function(m) AGPS_PRINTS[#AGPS_PRINTS + 1] = m end")
    if polestar:
        # Polestar's Nav: the guide goal's waypoint (uiMap, x and y in percent) and its world point (continent, yards
        # north and west, the NPC's height when it has one)
        lua.execute("""
          AGPS_PS = { target = { map = 1411, x = 52, y = 44, label = "|cffffd100Talk to|r Gar'Thok", stepIndex = 7,
                                 goalIndex = 2, kind = "turnin" }, world = nil, held = false, override = false }
          Polestar = { Nav = {
            GetTarget = function() return AGPS_PS.target end,
            GetTargetWorld = function()
              local w = AGPS_PS.world
              if w then return w[1], w[2], w[3], w[4] end
            end,
            IsHeld = function() return AGPS_PS.held end,
            IsOverride = function() return AGPS_PS.override end } }
        """)
    if off:  # (a character who turned the guide routes off: on is the default, test_*_on_by_itself below)
        cdb = ns.CharDB()
        cdb.rxpFollow, cdb.zygorFollow, cdb.polestarFollow = False, False, False
    return lua, ns


def _stops(ns):
    return [(round(d.x), round(d.y), d.cont, str(d.name), d.polestar) for d in ns.Nav.stops.values()]


def test_the_button_is_there_only_with_polestar():
    lua, ns = _game(polestar=False)
    assert "polestarRoute" not in [str(t.id) for t in ns.GPS.QuickSlots().values()]
    lua.execute("Polestar = { Nav = { GetTarget = function() end, GetTargetWorld = function() end } }")
    assert "polestarRoute" in [str(t.id) for t in ns.GPS.QuickSlots().values()]


def test_each_polestar_step_is_the_next_stop_and_done_when_polestar_moves_on():
    lua, ns = _game()
    N, P = ns.Nav, ns.Polestar
    where = ns.Import.ToStop(lua.eval("{ mapID = 1411, x = 52, y = 44 }"))
    N.SetDestination(-9000.0, 400.0, 0, "Somewhere else")
    P.Toggle()
    assert P.On()
    # the route is Polestar's step, where its arrow is guiding (the label's color codes taken out)
    s = _stops(ns)
    assert len(s) == 1 and s[0][:3] == (round(where.x), round(where.y), 1) and s[0][3] == "Polestar: Talk to Gar'Thok"
    # getting there doesn't finish it: Polestar says when the goal is done
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {where.x}, {where.y}, 1")
    P.Tick()
    assert len(_stops(ns)) == 1 and N.stops[1].polestar
    # Polestar moves on to the next step's place: that stop done, the next one the stop (no label: "Step n")
    lua.execute("AGPS_PS.target = { map = 1411, x = 40, y = 30, stepIndex = 8, goalIndex = 1 }")
    P.Tick()
    s = _stops(ns)
    assert len(s) == 1 and s[0][3] == "Polestar: Step 8"
    # a done step has no waypoint; the death helper's corpse run and a point picked by hand aren't the guide's:
    # no stop, still following
    for setup in ("AGPS_PS.target = nil", "AGPS_PS.held = true", "AGPS_PS.override = true"):
        lua.execute("AGPS_PS.target = { map = 1411, x = 40, y = 30, stepIndex = 8, goalIndex = 1 } "
                    "AGPS_PS.held, AGPS_PS.override = false, false " + setup)
        P.Tick()
        assert _stops(ns) == [] and P.On(), setup
    # kept over a /reload (the stop saved with its key: not put in twice)
    lua.execute("AGPS_PS.held, AGPS_PS.override = false, false "
                "AGPS_PS.target = { map = 1411, x = 45, y = 35, stepIndex = 9, goalIndex = 1 }")
    P.Tick()
    assert len(_stops(ns)) == 1
    N.Restore()
    P.lastKey = None
    P.Tick()
    assert len(_stops(ns)) == 1


def test_polestars_own_world_point_and_height_are_used():
    # (its guides' coordinates may be on the older maps' frames, which Polestar places itself: its world point wins,
    # and the NPC's height it gives is the stop's)
    lua, ns = _game()
    lua.execute("AGPS_PS.world = { 1, -500.0, -4400.0, 12.5 }")
    ns.Polestar.Toggle()
    d = ns.Nav.stops[1]
    assert (round(d.x), round(d.y), d.cont) == (-500, -4400, 1) and d.z == pytest.approx(12.5)


def test_another_route_turns_it_off_and_one_guide_at_a_time():
    lua, ns = _game()
    N, P, Z = ns.Nav, ns.Polestar, ns.Zygor
    P.Toggle()
    assert len(_stops(ns)) == 1
    N.SetDestination(-9000.0, 400.0, 0, "Somewhere else")  # (Quest Route, a search, ...)
    P.Tick()
    assert not P.On() and [s[3] for s in _stops(ns)] == ["Somewhere else"]
    assert any("Polestar Route: off" in str(m) for m in lua.eval("AGPS_PRINTS").values())
    # Zygor Route turned on turns Polestar Route off, and the other way round
    lua.execute("""ZygorGuidesViewer = { Pointer = { DestinationWaypoint = { m = 1411, x = 0.52, y = 0.44, type = "way",
      goal = { num = 2, status = "incomplete", parentStep = { num = 7, parentGuide = { title = "G" } } } } } }""")
    P.Toggle()
    assert P.On()
    Z.Toggle()
    assert Z.On() and not P.On()
    P.Toggle()
    assert P.On() and not Z.On() and len(_stops(ns)) == 1 and _stops(ns)[0][4]


def test_polestar_route_is_on_by_itself_and_the_other_guides_first_where_several_are():
    lua, ns = _game(off=False)
    P = ns.Polestar
    assert P.On() and ns.CharDB().polestarFollow is None
    P.Tick()
    assert len(_stops(ns)) == 1 and _stops(ns)[0][4]
    P.Toggle()
    assert not P.On() and ns.CharDB().polestarFollow is False and _stops(ns) == []
    # (RestedXP's loaded too, neither set: RestedXP's; Polestar's once RestedXP's is turned off)
    lua, ns = _game(off=False)
    P, X = ns.Polestar, ns.RestedXP
    lua.execute("RXPG_ARROW = { element = { wx = 330.0, wy = 2270.0, instance = 0, step = { index = 3, active = true } } }")
    assert X.On() and not P.On()
    X.Toggle()
    assert not X.On() and P.On()
