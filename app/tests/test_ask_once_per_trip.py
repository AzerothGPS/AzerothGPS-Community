"""A trip of several stops asks each routing question once (the whole addon, gameharness).

Reported 2026-11-18 by Kooki3z, playing a multi-stop trip at level 24: "after reaching a stop in a multiple stop trip I
keep getting these pop ups, they should only be asked once in a multi stop route". The popup was "The only way there
walks through Badlands (level 35-45): too high for your level 24. Keep this route?"; earlier the same kind of trip asked
"Risk enemy territory?" about Dun Algaz at every stop. Each stop reached brought the next leg into the route, and its
zones too high (yes was remembered per zone) or its stop's "risk it?" (remembered per stop) were asked again; and a
question left up unanswered was asked again at every stop.

Now each kind of question is asked once a trip (Nav.redOk's `all` and `no`, Nav.riskOk's `trip`), kept through the
stops reached, the route worked out again off course and a /reload, and forgotten by a new trip (Nav.SameTrip).
"""

import pytest

WETLANDS = (-3900.0, -2550.0)  # (south of Thelgen Rock, north of Dun Algaz)
LOCH_MODAN = (-5600.0, -3300.0)


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start

    lua, ns = start()
    ns.Nav.FUN = False
    ns.settings.gps.fastestOrder = False
    return lua, ns


def _at(ns, name, u, v):
    z = next(k for k in ns.Maps.keys() if ns.Maps[k].name == name and ns.Maps[k].type == 3)
    b = ns.Maps[z].bounds
    return b[3] - v / 100 * (b[3] - b[1]), b[4] - u / 100 * (b[4] - b[2])


@pytest.fixture
def trip(game):
    """trip(start, stops, level): a Horde character at `level` with every flight master known, the trip `stops` set
    from `start` on the Eastern Kingdoms, one stop routed ahead at a time (each stop reached brings the next leg in).
    The map's questions are kept to answer (trip.asks()), none answered by themselves."""
    from azerothgps import tripsweep as ts

    lua, ns = game
    N, st = ns.Nav, ns.settings.gps
    cdb = ns.CharDB()
    saved = (cdb.faction, cdb.taxiNodes, st.avoidHostile, st.zoom, st.stopsAhead)
    said = lua.eval("{}")
    old_print = ns.Print
    ns.Print = lua.eval("function(t) return function(msg) t[#t + 1] = msg end end")(said)
    lua.execute("""
      AGPS_ASKS = {}
      AGPS_CONFIRM = AGPS_NS.GPS.Confirm
      AGPS_NS.GPS.Confirm = function(text, yes, no) AGPS_ASKS[#AGPS_ASKS + 1] = { text = text, yes = yes, no = no } return true end
    """)

    def settle(n=6):
        for _ in range(n):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            ns.GPS.Update()

    def to(p):
        lua.execute(f"AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = {p[0]}, {p[1]}, 0")

    def set_stops(stops, force=None):
        N.SetStops(lua.eval("{ " + "".join(f"{{ x = {x}, y = {y}, cont = 0, name = 's{i}' }}, "
                                            for i, (x, y) in enumerate(stops)) + "}"), False, force)
        N.Invalidate(True, True)
        ns.GPS.Follow()
        settle()

    def run(start, stops, level):
        lua.execute("AGPS_ASKS = {}")
        st.avoidHostile, st.zoom, st.stopsAhead = True, 600, 1
        lua.execute(f"AGPS_LEVEL = {level}")
        cdb.faction = "Horde"
        cdb.taxiNodes = lua.eval("{ [1415] = { nodes = { "
                                 + "".join(f"{{ nodeID = {n}, known = true }}, " for n in ts._masters(ns, 0, "H")) + "} } }")
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        ns.Router.Reset()
        to(start)
        set_stops(stops, "red")  # ("red": the stops' own zones not asked about first; the walks between them are)

    def asks():
        a = lua.eval("AGPS_ASKS")
        return [a[i] for i in range(1, len(a) + 1)]

    def reach(p):
        """The player at `p` (the next stop): it's reached, the next leg comes in."""
        n = len(N.stops)
        to(p)
        settle()
        assert len(N.stops) == n - 1, "the stop wasn't reached"
        settle()

    def reload():
        """As a /reload: the trip and its answers back from the saved stops."""
        N.redOk, N.riskOk = lua.eval("{}"), lua.eval("{}")
        N.Restore()
        N.Invalidate(True, True)
        settle()

    run.settle, run.to, run.asks, run.reach, run.reload, run.set_stops = settle, to, asks, reach, reload, set_stops
    run.said = lambda: [str(said[i]) for i in range(1, len(said) + 1)]
    try:
        yield run
    finally:
        ns.Print = old_print
        lua.execute("AGPS_NS.GPS.Confirm = AGPS_CONFIRM AGPS_LEVEL = nil")
        cdb.faction, cdb.taxiNodes, st.avoidHostile, st.zoom, st.stopsAhead = saved
        ns.Teleports.Changed()
        N.FlightsChanged()
        N.Clear()
        lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 2254.0, 293.0, 0 AGPS_T = AGPS_T + 1")
        ns.GPS.Follow()


def test_zones_too_high_are_asked_about_once_a_trip(game, trip):
    # level 24 from the Wetlands: to Tarren Mill through the Arathi Highlands, then to Loch Modan through the Badlands.
    # Asked about the Arathi Highlands; the Badlands leg came in at Tarren Mill and asked again (Kooki3z's popup)
    lua, ns = game
    N = ns.Nav
    tarren, loch = _at(ns, "Hillsbrad Foothills", 61, 20), _at(ns, "Loch Modan", 35, 45)
    trip(_at(ns, "Wetlands", 50, 40), [tarren, loch], 24)
    asks = trip.asks()
    assert len(asks) == 1 and "Arathi Highlands" in str(asks[0].text) and "Keep this route?" in str(asks[0].text)
    asks[0].yes()
    trip.settle()
    trip.reach(tarren)
    assert len(trip.asks()) == 1, [str(a.text) for a in trip.asks()]  # (the Badlands leg: not asked)
    assert N.redOk.all and ns.CharDB().redOk  # (the trip's answer, saved with it)
    # off course: the route worked out again from somewhere else, not asked
    trip.to(_at(ns, "Hillsbrad Foothills", 40, 45))
    trip.settle()
    assert N.route and len(trip.asks()) == 1
    # a /reload mid-trip: the answer comes back with the trip
    trip.reload()
    assert N.redOk.all and len(N.stops) == 1 and len(trip.asks()) == 1
    # a new trip (a new single stop, not the one left) asks again
    trip.to(_at(ns, "Wetlands", 50, 40))
    trip.set_stops([_at(ns, "Hillsbrad Foothills", 60, 22)])
    assert not N.redOk.all
    asks = trip.asks()
    assert len(asks) == 2 and "Arathi Highlands" in str(asks[1].text)


def test_enemy_territory_is_asked_about_once_a_trip(game, trip):
    # level 30 from the Wetlands to Loch Modan and back: both legs past the Alliance's guards at Dun Algaz, the safe way
    # round much slower. "Risk enemy territory?" was asked for each stop (remembered per stop)
    lua, ns = game
    N = ns.Nav
    trip(WETLANDS, [LOCH_MODAN, WETLANDS], 30)
    asks = trip.asks()
    assert len(asks) == 1 and "Risk enemy territory" in str(asks[0].text)
    asks[0].yes()
    trip.settle()
    trip.reach(LOCH_MODAN)
    assert len(trip.asks()) == 1, [str(a.text) for a in trip.asks()]
    assert N.riskOk.trip is True and ns.CharDB().riskOk.trip is True  # (the trip's answer, saved with it)
    assert N.RiskAnswer(N.dest) is True
    # off course, then a /reload: not asked
    trip.to((LOCH_MODAN[0] + 150, LOCH_MODAN[1] + 150))
    trip.settle()
    trip.reload()
    assert N.riskOk.trip is True and len(trip.asks()) == 1
    # a new trip (a new single stop) asks again
    N.Clear()
    trip.to(WETLANDS)
    trip.set_stops([LOCH_MODAN])
    assert N.RiskAnswer(N.dest) is None
    assert len(trip.asks()) == 2 and "Risk enemy territory" in str(trip.asks()[1].text)


def test_a_no_is_remembered_for_the_trip(game, trip):
    lua, ns = game
    N = ns.Nav
    # "Keep this route?" No, in a trip of several stops: the trip kept (it goes round those zones where it can), said in
    # chat, and not asked again at the next stop or after a /reload. (The only stop: No still clears the route.)
    tarren, loch = _at(ns, "Hillsbrad Foothills", 61, 20), _at(ns, "Loch Modan", 35, 45)
    trip(_at(ns, "Wetlands", 50, 40), [tarren, loch], 24)
    asks = trip.asks()
    assert len(asks) == 1
    asks[0].no(True)
    trip.settle()
    assert len(N.stops) == 2 and N.redOk.no and not N.RedAsking()
    assert any("won't ask again this trip" in s for s in trip.said())
    trip.reach(tarren)
    trip.reload()
    assert N.redOk.no and len(trip.asks()) == 1
    # "Risk enemy territory?" No: the safe way for the rest of the trip, not asked again
    trip(WETLANDS, [LOCH_MODAN, WETLANDS], 30)
    asks = trip.asks()
    assert len(asks) == 1 and "Risk enemy territory" in str(asks[0].text)
    asks[0].no(True)
    trip.settle()
    assert N.riskOk.trip is False
    trip.reach(LOCH_MODAN)
    assert len(trip.asks()) == 1 and N.RiskAnswer(N.dest) is False


def test_a_question_left_up_isnt_asked_again_at_the_next_stop(game, trip):
    # the popup up, unanswered, while the player goes on to the stop: the next leg's route isn't asked about in a new
    # popup (it came up again at every stop); answered, it's the trip's answer
    lua, ns = game
    N, G = ns.Nav, ns.GPS
    tarren, loch = _at(ns, "Hillsbrad Foothills", 61, 20), _at(ns, "Loch Modan", 35, 45)
    lua.execute("""
      AGPS_REAL_ASKS = 0
      AGPS_NS.GPS.Confirm = AGPS_CONFIRM -- (the fixture's stand-in put back: the real popup)
      local ask = AGPS_NS.Ask
      AGPS_NS.Ask = function(name, ...)
        if name == "AzerothGPSConfirm" then AGPS_REAL_ASKS = AGPS_REAL_ASKS + 1 end
        return ask(name, ...)
      end
      AGPS_ASK = ask
    """)
    try:
        trip(_at(ns, "Wetlands", 50, 40), [tarren, loch], 24)
        assert lua.eval("AGPS_REAL_ASKS") == 1 and G.confirmBox.IsShown(G.confirmBox) and N.RedAsking()
        trip.to(tarren)
        trip.settle()
        assert len(N.stops) == 1
        trip.settle()
        assert lua.eval("AGPS_REAL_ASKS") == 1 and N.RedAsking()  # (still up, the same question)
        G.confirmBox.onYes()
        trip.settle()
        assert N.redOk.all and not N.RedAsking() and N.route
    finally:
        lua.execute("AGPS_NS.Ask = AGPS_ASK")


def test_group_quests_kept_or_left_out_come_back_after_a_reload(game, trip):
    # the quest route's "Keep it in your route?" answers (GPS.groupChoice, once a session) are saved with the trip: a
    # /reload mid-trip doesn't ask them again
    lua, ns = game
    N, G = ns.Nav, ns.GPS
    trip(WETLANDS, [(-3950.0, -2550.0), (-4000.0, -2550.0)], 30)
    G.groupChoice[4242] = "leave"
    N.SaveStops()
    assert ns.CharDB().groupChoice[4242] == "leave"
    G.groupChoice = lua.eval("{}")
    trip.reload()
    assert G.groupChoice[4242] == "leave"
    G.groupChoice = lua.eval("{}")
