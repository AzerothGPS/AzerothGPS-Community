"""A talk to a flight master leaves the route alone unless the flights known changed (a player's report, 2026-11-10:
"Whenever I talk to FP it also refreshes": every TAXIMAP_OPENED threw the route away and worked it out again)."""

from azerothgps.gameharness import start


def _nodes(lua, known):
    return lua.eval("{ " + ", ".join(f"{{ nodeID = {n}, name = 'n{n}', state = {0 if k else 2} }}" for n, k in known) + " }")


def test_the_same_flights_again_leave_the_route_alone():
    lua, ns = start()
    calls = []
    real = ns.Nav.FlightsChanged
    ns.Nav.FlightsChanged = lambda *a: calls.append(1)
    try:
        T = ns.Taxi
        T.StoreNodes(1415, _nodes(lua, [(28, True), (33, False)]), "taximap")
        first = len(calls)
        assert first == 1  # (flights known for the first time: routes may fly now)
        T.StoreNodes(1415, _nodes(lua, [(33, False), (28, True)]), "taximap")  # (the same, in another order)
        T.StoreNodes(1415, _nodes(lua, [(28, True), (33, False)]), "login")
        assert len(calls) == first
        T.StoreNodes(1415, _nodes(lua, [(28, True), (33, True)]), "taximap")  # (a flight path learned)
        assert len(calls) == first + 1
        assert ns.CharDB().taxiNodes[1415].source == "taximap"  # (still stored each time)
    finally:
        ns.Nav.FlightsChanged = real


def _discover(lua, ns, game_has_it, at=(0.5, 0.5)):
    """A character who knows node 28, standing at node 33's flight master: "New flight path discovered!"."""
    T = ns.Taxi
    T.StoreNodes(1415, lua.eval("{ { nodeID = 28, state = 1, position = { x = 0.2, y = 0.2 } },"
                                " { nodeID = 33, state = 2, position = { x = 0.5, y = 0.5 } } }"), "taximap")
    T.StoreNodes(1414, lua.eval("{ { nodeID = 2, state = 1, position = { x = 0.5, y = 0.5 } } }"), "taximap")
    lua.execute(f"""
      ERR_NEWTAXIPATH = "New flight path discovered!"
      C_Timer.After = function(_, fn) fn() end
      C_TaxiMap = C_TaxiMap or {{}}
      C_TaxiMap.GetTaxiNodesForMap = function(mapID)
        if mapID == 1414 then return {{ {{ nodeID = 2, state = 1, position = {{ x = 0.5, y = 0.5 }} }} }} end
        return {{ {{ nodeID = 28, state = 1, position = {{ x = 0.2, y = 0.2 }} }},
                 {{ nodeID = 33, state = {1 if game_has_it else 2}, position = {{ x = 0.5, y = 0.5 }} }} }}
      end
      C_Map = C_Map or {{}}
      C_Map.GetPlayerMapPosition = function(mapID) if mapID == 1415 then return {{ x = {at[0]}, y = {at[1]} }} end end
    """)
    calls = []
    ns.Nav.FlightsChanged = lambda *a: calls.append(1)
    lua.eval("AGPS_FIRE")("UI_INFO_MESSAGE", 0, "Some other message")
    assert not calls
    lua.eval("AGPS_FIRE")("UI_INFO_MESSAGE", 0, "New flight path discovered!")
    nodes = {int(n.nodeID): bool(n.known) for n in ns.CharDB().taxiNodes[1415].nodes.values()}
    return calls, nodes


def test_a_flight_path_discovered_is_known_without_the_flight_map():
    # (asked 2026-11-10: a right-click on the flight master, "new flight path discovered", the map never opened)
    lua, ns = start()
    calls, nodes = _discover(lua, ns, game_has_it=True)
    assert nodes == {28: True, 33: True} and len(calls) == 1


def test_a_flight_path_the_games_list_lacks_yet_is_the_flight_master_stood_at():
    lua, ns = start()
    calls, nodes = _discover(lua, ns, game_has_it=False)
    assert nodes == {28: True, 33: True} and len(calls) == 1
    assert ns.CharDB().taxiNodes[1414].nodes[1].known  # (the other continent's left alone)


def test_no_flight_master_near_marks_nothing():
    lua, ns = start()
    calls, nodes = _discover(lua, ns, game_has_it=False, at=(0.52, 0.5))
    assert nodes == {28: True, 33: False} and not calls


def test_a_flight_path_discovered_stays_known_after_the_next_login():
    # (reported 2026-11-13: talked to Zoram'gar's flight master, never opened the flight map, logged out and in: "you
    # don't know it". The login read, the continents' maps, gives every node with no state and wrote them all unknown)
    lua, ns = start()
    T = ns.Taxi
    stateless = "{ { nodeID = 2, position = { x = 0.5, y = 0.5 } }, { nodeID = 7, position = { x = 0.1, y = 0.1 } } }"
    T.StoreNodes(1414, lua.eval(stateless), "login")
    lua.execute("""
      C_Map = C_Map or {}
      C_Map.GetPlayerMapPosition = function(mapID) if mapID == 1414 then return { x = 0.5, y = 0.5 } end end
    """)
    assert T.MarkNearest().nodeID == 2
    T.StoreNodes(1414, lua.eval(stateless), "login")  # (logged out and back in)
    known = {int(n.nodeID): bool(n.known) for n in ns.CharDB().taxiNodes[1414].nodes.values()}
    assert known == {2: True, 7: False}
    assert ns.Nav.KnownFlightNodes()[0][2]
    # (the flight map's own read, which does give states, still has the last word)
    T.StoreNodes(1414, lua.eval("{ { nodeID = 2, state = 2 }, { nodeID = 7, state = 2 } }"), "taximap")
    assert not ns.CharDB().taxiNodes[1414].nodes[1].known
