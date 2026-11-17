"""Zygor Route (asked 2026-11-09: "support zygor in the same way we support restedxp"): with Zygor Guides Viewer
installed, a quick button routes to each step of its guide in turn, from the place Zygor's arrow is taking the player
(ZygorGuidesViewer.Pointer.DestinationWaypoint); a step's stop is done when Zygor moves on, never by getting there.
The whole addon (gameharness) with a stand-in for Zygor's pointer, as RestedXP Route's tests (test_restedxp.py)."""
import pytest

pytest.importorskip("lupa.lua51")


def _game(zygor=True, off=True):
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    lua.execute("AGPS_PRINTS = {} AGPS_NS.Print = function(m) AGPS_PRINTS[#AGPS_PRINTS + 1] = m end")
    if zygor:
        # Zygor's pointer: the destination waypoint of the guide goal it's taking the player to (uiMap, x and y 0-1)
        lua.execute("""
          AGPS_GUIDE = { title = "LEVELING\\\\Horde 1-10" }
          AGPS_ZSTEP7 = { num = 7, parentGuide = AGPS_GUIDE }
          AGPS_ZSTEP8 = { num = 8, parentGuide = AGPS_GUIDE }
          ZygorGuidesViewer = { Pointer = { DestinationWaypoint = { m = 1411, x = 0.52, y = 0.44, type = "way",
            title = "|cffffee00Razor Hill|r\\n(in Durotar)",
            goal = { num = 2, status = "incomplete", parentStep = AGPS_ZSTEP7 } } } }
        """)
    if off:  # (a character who turned the guide routes off: on is the default, test_*_on_by_itself below)
        cdb = ns.CharDB()
        cdb.rxpFollow, cdb.zygorFollow = False, False
    return lua, ns


def _stops(ns):
    return [(round(d.x), round(d.y), d.cont, str(d.name), d.zygor) for d in ns.Nav.stops.values()]


def test_the_button_is_there_only_with_zygor():
    lua, ns = _game(zygor=False)
    assert "zygorRoute" not in [str(t.id) for t in ns.GPS.QuickSlots().values()]
    lua.execute("ZygorGuidesViewer = { Pointer = {} }")
    assert "zygorRoute" in [str(t.id) for t in ns.GPS.QuickSlots().values()]


def test_each_zygor_step_is_the_next_stop_and_done_when_zygor_moves_on():
    lua, ns = _game()
    N, Z = ns.Nav, ns.Zygor
    where = ns.Import.ToStop(lua.eval("{ mapID = 1411, x = 52, y = 44 }"))
    N.SetDestination(-9000.0, 400.0, 0, "Somewhere else")
    Z.Toggle()
    assert Z.On()
    # the route is Zygor's step, where its arrow is taking the player (the title's color codes and zone line taken out)
    s = _stops(ns)
    assert len(s) == 1 and s[0][:3] == (round(where.x), round(where.y), 1) and s[0][3] == "Zygor: Razor Hill"
    # getting there doesn't finish it: Zygor says when the goal is done
    lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {where.x}, {where.y}, 1")
    Z.Tick()
    assert len(_stops(ns)) == 1 and N.stops[1].zygor
    # Zygor moves on to the next step's place: that stop done, the next one the stop
    lua.execute("""ZygorGuidesViewer.Pointer.DestinationWaypoint = { m = 1411, x = 0.40, y = 0.30, type = "way",
      goal = { num = 1, status = "incomplete", parentStep = AGPS_ZSTEP8 } }""")
    Z.Tick()
    s = _stops(ns)
    assert len(s) == 1 and s[0][3] == "Zygor: Step 8"
    # its goal done (or no place to go, or a waypoint set by hand in Zygor, no goal): no stop, still following
    lua.execute("ZygorGuidesViewer.Pointer.DestinationWaypoint.goal.status = 'complete'")
    Z.Tick()
    assert _stops(ns) == [] and Z.On()
    lua.execute("ZygorGuidesViewer.Pointer.DestinationWaypoint = { m = 1411, x = 0.5, y = 0.5, type = 'manual' }")
    Z.Tick()
    assert _stops(ns) == [] and Z.On()
    # kept over a /reload (the stop saved with its key: not put in twice)
    lua.execute("""ZygorGuidesViewer.Pointer.DestinationWaypoint = { m = 1411, x = 0.45, y = 0.35, type = "way",
      goal = { num = 1, status = "incomplete", parentStep = { num = 9, parentGuide = AGPS_GUIDE } } }""")
    Z.Tick()
    assert len(_stops(ns)) == 1
    N.Restore()
    Z.lastKey = None
    Z.Tick()
    assert len(_stops(ns)) == 1


def test_another_route_turns_it_off_and_one_guide_at_a_time():
    lua, ns = _game()
    N, Z, X = ns.Nav, ns.Zygor, ns.RestedXP
    Z.Toggle()
    assert len(_stops(ns)) == 1
    N.SetDestination(-9000.0, 400.0, 0, "Somewhere else")  # (Quest Route, a search, ...)
    Z.Tick()
    assert not Z.On() and [s[3] for s in _stops(ns)] == ["Somewhere else"]
    assert any("Zygor Route: off" in str(m) for m in lua.eval("AGPS_PRINTS").values())
    # RestedXP Route turned on turns Zygor Route off, and the other way round
    lua.execute("RXPG_ARROW = { element = { wx = 330.0, wy = 2270.0, instance = 0, step = { index = 3, active = true } } }")
    Z.Toggle()
    assert Z.On()
    X.Toggle()
    assert X.On() and not Z.On() and [s[4] for s in _stops(ns)] == [None]
    Z.Toggle()
    assert Z.On() and not X.On() and len(_stops(ns)) == 1 and _stops(ns)[0][4]


def test_a_zygor_stop_takes_the_floor_of_an_npc_talked_to_there():
    # (as RestedXP Route: Zygor gives no height; where floors stack, an NPC the player talked to there tells it)
    lua, ns = _game()
    where = ns.Import.ToStop(lua.eval("{ mapID = 1411, x = 52, y = 44 }"))
    lua.execute(f"AGPS_NS.db.npcs = {{ ['Someone'] = {{ x = {where.x + 3}, y = {where.y}, cont = 1, z = -17.3 }} }}")
    ns.Zygor.Toggle()
    assert ns.Nav.stops[1].z == pytest.approx(-17.3)


def test_a_zygor_step_down_in_the_cleft_of_shadow_is_on_the_cleft_s_floor():
    # (the user, 2026-11-09: the shipped guide heights "use it for both") Zygor's own waypoint for Neeru Fireblade,
    # `turnin Neeru Fireblade##829 |goto Orgrimmar/0 49.48,50.60`, is in Data/GuideFloors.lua with her height
    lua, ns = _game()
    lua.execute("""ZygorGuidesViewer.Pointer.DestinationWaypoint = { m = 1454, x = 0.4948, y = 0.5060, type = "way",
      title = "Neeru Fireblade", goal = { num = 1, status = "incomplete", parentStep = AGPS_ZSTEP7 } }""")
    ns.Zygor.Toggle()
    d = ns.Nav.stops[1]
    assert d.z == pytest.approx(-17.3, abs=1.5)
    assert ns.Nav.StopZ(d) == pytest.approx(d.z, abs=0.5)


def test_zygor_route_is_on_by_itself_with_zygor_and_restedxps_first_where_both_are():
    # (asked 2026-11-10: "RestedXP and Zygor routing, have these on by default"; one guide at a time)
    lua, ns = _game(off=False)
    Z, X = ns.Zygor, ns.RestedXP
    assert Z.On() and not X.On() and ns.CharDB().zygorFollow is None
    Z.Tick()
    assert len(_stops(ns)) == 1 and _stops(ns)[0][4]
    Z.Toggle()
    assert not Z.On() and ns.CharDB().zygorFollow is False and _stops(ns) == []
    # (both guide addons loaded, neither set: RestedXP's; Zygor's once RestedXP's is turned off)
    lua, ns = _game(off=False)
    Z, X = ns.Zygor, ns.RestedXP
    lua.execute("RXPG_ARROW = { element = { wx = 330.0, wy = 2270.0, instance = 0, step = { index = 3, active = true } } }")
    assert X.On() and not Z.On()
    X.Toggle()
    assert not X.On() and Z.On()
