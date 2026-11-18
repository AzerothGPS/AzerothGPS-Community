"""RestedXP Route (asked 2026-11-08): with RestedXP Guides installed, a quick button routes to each step of its guide in
turn, from the step RestedXP's arrow points at (its global frame RXPG_ARROW); a step's stop is done when RestedXP checks
the step off, never by getting there. The whole addon (gameharness) with a stand-in for RestedXP's arrow."""
import pytest

pytest.importorskip("lupa.lua51")


def _game(rxp=True, off=True):
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    lua.execute("AGPS_PRINTS = {} local p = AGPS_NS.Print AGPS_NS.Print = function(m) AGPS_PRINTS[#AGPS_PRINTS + 1] = m end")
    if rxp:
        # RestedXP's arrow: HereBeDragons' world yards (wx = UnitPosition's second, wy its first), steps as RestedXP's
        lua.execute("""
          AGPS_STEP3 = { index = 3, title = "Go to |cFFFFFF00RXP_FRIENDLY_Executor Zygand|r", active = true }
          AGPS_STEP4 = { index = 4, active = true }
          RXPG_ARROW = { element = { wx = 330.0, wy = 2270.0, instance = 0, step = AGPS_STEP3 } }
        """)
    if off:  # (a character who turned the guide routes off: on is the default, test_*_on_by_itself below)
        cdb = ns.CharDB()
        cdb.rxpFollow, cdb.zygorFollow = False, False
    return lua, ns


def _stops(ns):
    return [(round(d.x), round(d.y), d.cont, str(d.name), d.rxp) for d in ns.Nav.stops.values()]


def test_the_button_is_there_only_with_restedxp():
    lua, ns = _game(rxp=False)
    assert "rxpRoute" not in [str(t.id) for t in ns.GPS.QuickSlots().values()]
    lua.execute("RXPG_ARROW = {}")
    assert "rxpRoute" in [str(t.id) for t in ns.GPS.QuickSlots().values()]
    # (asked 2026-11-16 for 1.3.5: "if using RestedXP or any of the supported questing addons, these buttons are always
    # shown by default to the right") on the bar to the right, shown; a place the player chose stays theirs
    G = ns.GPS
    for i in ("rxpRoute", "zygorRoute", "polestarRoute", "questifyRoute", "aprRoute"):
        assert G.QuickPlace(i) == "barRight", i
    G.LayoutQuick()
    b = next(t for t in G.QUICK.values() if t.id == "rxpRoute").button
    assert b._shown
    ns.settings.gps.quick = lua.eval("{ rxpRoute = 'menuUp' }")
    try:
        assert G.QuickPlace("rxpRoute") == "menuUp"
    finally:
        ns.settings.gps.quick = None


def test_the_button_is_lit_while_on_and_gray_while_off():
    # (asked 2026-11-16 for 1.3.5: "restedxp icon use to fade to grey when off, doesn't now") its look follows RestedXP's
    # route: clicked, and turned on or off anywhere else (/agps, RestedXP itself), seen within half a second
    lua, ns = _game()
    G, X = ns.GPS, ns.RestedXP
    G.LayoutQuick()
    G.RefreshQuick()
    t = next(t for t in G.QUICK.values() if t.id == "rxpRoute")

    def gray():
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        return t.iconTex._desat

    assert not X.On() and gray()
    t.button._scripts.OnClick(t.button, "LeftButton")
    assert X.On() and not t.iconTex._desat  # (at once, from the click)
    t.button._scripts.OnClick(t.button, "LeftButton")
    assert not X.On() and t.iconTex._desat
    X.Toggle()  # (not the button)
    assert X.On() and not gray()
    X.Toggle()
    assert not X.On() and gray()


def test_each_restedxp_step_is_the_next_stop_and_done_when_restedxp_checks_it_off():
    lua, ns = _game()
    N, X = ns.Nav, ns.RestedXP
    N.SetDestination(-9000.0, 400.0, 0, "Somewhere else")
    X.Toggle()
    assert X.On()
    # the route is RestedXP's step, where its arrow points (AzerothGPS's x, y = HereBeDragons' wy, wx)
    s = _stops(ns)
    assert len(s) == 1 and s[0][:3] == (2270, 330, 0) and s[0][3] == "RestedXP: Go to Executor Zygand"
    # getting there doesn't finish it: RestedXP says when the step is done
    assert N.Status(2270.0, 330.0, 0) != "|cff40ff40Arrived|r"
    X.Tick()
    assert len(_stops(ns)) == 1 and N.stops[1].rxp
    # RestedXP checks the step off and points at the next one: that stop done, the next step's place the stop
    lua.execute("AGPS_STEP3.completed = true AGPS_STEP3.active = false "
                "RXPG_ARROW.element = { wx = 500.0, wy = 2000.0, instance = 0, step = AGPS_STEP4 }")
    X.Tick()
    s = _stops(ns)
    assert len(s) == 1 and s[0][:3] == (2000, 500, 0) and s[0][3] == "RestedXP: Step 4"
    # a step with no place to go: no stop, still following; the next one with a place is the stop again
    lua.execute("AGPS_STEP4.completed = true RXPG_ARROW.element = nil")
    X.Tick()
    assert _stops(ns) == [] and X.On()
    lua.execute("RXPG_ARROW.element = { wx = 600.0, wy = 1900.0, instance = 0, step = { index = 6, active = true } }")
    X.Tick()
    assert [s[:3] for s in _stops(ns)] == [(1900, 600, 0)]
    # kept over a /reload (the stop saved with its step's key: not put in twice)
    N.Restore()
    X.lastKey = None
    X.Tick()
    assert len(_stops(ns)) == 1


def test_another_route_turns_it_off():
    lua, ns = _game()
    N, X = ns.Nav, ns.RestedXP
    X.Toggle()
    assert len(_stops(ns)) == 1
    N.SetDestination(-9000.0, 400.0, 0, "Somewhere else")  # (Quest Route, a search, ...)
    X.Tick()
    assert not X.On() and [s[3] for s in _stops(ns)] == ["Somewhere else"]
    assert any("RestedXP Route: off" in str(m) for m in lua.eval("AGPS_PRINTS").values())
    # clicked again: on, the route RestedXP's step again; and off by the button leaves no RestedXP stop
    X.Toggle()
    assert X.On() and [s[3] for s in _stops(ns)] == ["RestedXP: Go to Executor Zygand"]
    X.Toggle()
    assert not X.On() and _stops(ns) == []


def test_a_step_down_in_undercity_is_on_undercitys_level():
    """2026-11-08, in game: "Enter the Royal Quarter" (RestedXP's goto in Undercity, its uiMap 1458) went in on the
    surface (RestedXP's instance 0), so the route went up the lift and out to the ruins over it. A place whose zone is
    a city's own level is a stop on that level; one already in the route on the surface is put right."""
    lua, ns = _game()
    N, X = ns.Nav, ns.RestedXP
    lua.execute("RXPG_ARROW.element = { wx = 320.0, wy = 1290.0, instance = 0, zone = 1458, x = 50.0, y = 50.0, "
                "step = { index = 12, title = 'Enter the Royal Quarter', active = true } }")
    X.Toggle()
    s = _stops(ns)
    assert len(s) == 1 and s[0][:3] == (1290, 320, 10001)
    # (the same place saved on the surface by the first version: replaced by the one on Undercity's level)
    N.stops[1].cont = 0
    N.stops[1].rxp = "12:320.0,1290.0"
    X.lastKey = None
    X.Tick()
    assert [s[:3] for s in _stops(ns)] == [(1290, 320, 10001)]
    # a place in a zone on the surface stays on its continent
    lua.execute("RXPG_ARROW.element = { wx = 330.0, wy = 2270.0, instance = 0, zone = 1420, x = 60.0, y = 50.0, "
                "step = { index = 13, active = true } }")
    X.Tick()
    assert [s[:3] for s in _stops(ns)] == [(2270, 330, 0)]

def test_a_step_down_in_the_cleft_of_shadow_is_on_the_cleft_s_floor():
    # (2026-11-08: "Talk to Neeru Fireblade", 55 yd ahead down in Orgrimmar's Cleft of Shadow, was routed 600 yd round
    # by the Drag: RestedXP gives no height, and the stop went on the Drag's street over her)
    import math
    lua, ns = _game()
    N, X, R = ns.Nav, ns.RestedXP, ns.Router
    neeru, me = (1800.66, -4374.51), (1846.4, -4405.7)  # (her spawn, about -17; the player in the Cleft too)
    lua.execute("RXPG_ARROW.element = { wx = %r, wy = %r, instance = 1, zone = 1454, "
                "step = { index = 37, title = 'Talk to Neeru Fireblade', active = true } }" % (neeru[1], neeru[0]))
    # the guides' waypoints over stacked floors ship with their NPC's height (Data/GuideFloors.lua): hers
    X.Toggle()
    assert N.stops[1].z == pytest.approx(-17.3)
    X.Toggle()
    # without it (a waypoint the table hasn't: a guide changed since), her spot's shipped height (Data/NpcFloors.lua,
    # 2026-11-14: every NPC in the capitals)
    ns.GuideFloors = lua.table()
    X.Toggle()
    assert N.stops[1].z == pytest.approx(-17.3)
    X.Toggle()
    # and without that either, nothing to tell the floor by: no height
    ns.NpcFloors = lua.table()
    X.Toggle()
    assert N.stops[1].z is None
    # the player followed down in the Cleft: the stop on its floor, and the route there short
    N.playerX, N.playerY = me
    N.FollowedZ = lua.eval("function() return -14.0 end")
    X.Tick()
    z = N.stops[1].z
    assert z is not None and -20 < z < -12
    r = R.Route(1, me[0], me[1], neeru[0], neeru[1], lua.table(offroad=False, z=-14.0, tz=z))
    assert r.length < 2.5 * math.dist(me, neeru), r.length
    # an NPC talked to there tells it without the player's floor (one far away: not it)
    X.Toggle()
    N.FollowedZ = lua.eval("function() return nil end")
    ns.db.npcs = lua.eval("{ [3216] = { name = 'Neeru Fireblade', cont = 1, x = 1801.0, y = -4374.0, z = -17.3 }, "
                          "[1] = { name = 'Far', cont = 1, x = 1830.0, y = -4374.0, z = 40.0 } }")
    X.Toggle()
    assert N.stops[1].z == pytest.approx(-17.3)


def test_a_step_under_undercitys_walkways_is_on_its_ring():
    # (the guides checked, 2026-11-08: 14 of Undercity's 50 NPC steps over stacked floors got the walkway over them,
    # the floor under a stop's spot being the top one) Benijah Fenner, on the Trade Quarter's ring under a walkway
    lua, ns = _game()
    N, X = ns.Nav, ns.RestedXP
    lua.execute("RXPG_ARROW.element = { wx = 308.9, wy = 1667.8, instance = 0, zone = 1458, "
                "step = { index = 5, title = 'Talk to Benijah Fenner', active = true } }")
    X.Toggle()
    d = N.stops[1]
    assert d.cont == 10001 and d.z == pytest.approx(-62.1)
    assert abs(N.StopZ(d) - -62.1) < 1


def test_the_restedxp_floors_ship_heights_only():
    # (the user, 2026-11-08: an exception to "no shipped NPC data" for RestedXP Route, and Zygor Route's too,
    # 2026-11-09: "use it for both"; no names, nothing drawn)
    import re
    from azerothgps.paths import ADDON_DIR

    text = (ADDON_DIR / "Data" / "GuideFloors.lua").read_text(encoding="utf-8")
    body = text.split("ns.GuideFloors = {", 1)[1]
    assert re.fullmatch(r"(\s*\[\d+\] = \{ [-\d.,\s]+ \},)*\s*\}\s*", body)
    readers = [f.name for f in ADDON_DIR.rglob("*.lua") if "GuideFloors" in f.read_text(encoding="utf-8", errors="replace")]
    assert sorted(readers) == ["GuideFloors.lua", "RestedXP.lua", "Zygor.lua"]


def test_restedxp_route_is_on_by_itself_with_restedxp_until_turned_off():
    # (asked 2026-11-10: "RestedXP and Zygor routing, have these on by default")
    lua, ns = _game(off=False)
    N, X = ns.Nav, ns.RestedXP
    assert X.On() and ns.CharDB().rxpFollow is None
    X.Tick()
    s = _stops(ns)
    assert len(s) == 1 and s[0][:3] == (2270, 330, 0)  # (the guide's step is the stop, nothing clicked)
    X.Toggle()  # (the button: off, and kept off)
    assert not X.On() and ns.CharDB().rxpFollow is False and _stops(ns) == []
    X.Tick()
    assert _stops(ns) == []
    X.Toggle()
    assert X.On() and len(_stops(ns)) == 1
    # (another route picked turns it off, as ever, and it stays off)
    N.SetDestination(-9000.0, 400.0, 0, "Somewhere else")
    X.Tick()
    assert not X.On() and ns.CharDB().rxpFollow is False


def test_restedxp_route_is_not_on_without_restedxp():
    lua, ns = _game(rxp=False, off=False)
    assert not ns.RestedXP.On() and not ns.Zygor.On()
    ns.RestedXP.Tick()
    assert _stops(ns) == []


def test_a_travel_step_already_done_by_the_player_goes_to_the_place_it_leads_to():
    # (seen in game 2026-11-12: beside Apothecary Zamah in Thunder Bluff's Pools of Vision, RestedXP still on its
    # "Travel to the Spirit Rise and enter the pools of vision" step, its waypoint the way in on top: the route went
    # back up and out. The next step's place, Zamah's, is the stop instead, on the pools' floor.)
    lua, ns = _game()
    N, X = ns.Nav, ns.RestedXP
    entrance = (-1051.4, 219.1)  # (Thunder Bluff 28.51, 28.95: on top of Spirit Rise)
    zamah = (-995.3, 278.5)  # (22.82, 20.88: down in the pools)
    lua.execute("""
      AGPS_TRAVEL = { index = 93, active = true, completewith = "next" }
      AGPS_ZAMAH = { index = 94, active = true, title = "Talk to Zamah",
        elements = { { tag = "goto", wx = %r, wy = %r, instance = 1, zone = 1456 } } }
      RXP = { currentGuide = { steps = { [93] = AGPS_TRAVEL, [94] = AGPS_ZAMAH }, labels = {} } }
      RXPG_ARROW.element = { wx = %r, wy = %r, instance = 1, zone = 1456, step = AGPS_TRAVEL }
    """ % (zamah[1], zamah[0], entrance[1], entrance[0]))
    try:
        # far from both: the travel step's way in, as RestedXP points
        N.playerX, N.playerY = -900.0, 100.0
        X.Toggle()
        assert (N.stops[1].x, N.stops[1].y) == pytest.approx(entrance)
        X.Toggle()
        # beside Zamah already: his place, on the pools' floor (the shipped height there)
        N.playerX, N.playerY = -998.0, 281.0
        X.Toggle()
        d = N.stops[1]
        assert (d.x, d.y) == pytest.approx(zamah) and d.z == pytest.approx(112.0)
        # and RestedXP moving on from it (Zamah done, the arrow past the travel step) ends that stop
        X.Tick()
        assert N.stops[1].rxp == d.rxp
        lua.execute("AGPS_ZAMAH.completed = true AGPS_TRAVEL.completed = true RXPG_ARROW.element = nil")
        X.Tick()
        assert not [s for s in N.stops.values() if s.rxp]
    finally:
        lua.execute("RXP = nil")

