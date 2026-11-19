"""Flight masters known only from the flight map or "New flight path discovered!" (issue #652, Kooki3z 2026-11-18:
"while flying to tarren mill, AzerothGPS seemed to think knew Kargath, Badlands flight path but I don't. Then after I
landed it went back to unknown flight path"). A Horde character knowing The Sepulcher, Undercity, Tarren Mill and
Grom'gol, flying Undercity to Tarren Mill on a route to Loch Modan and back to Hillsbrad: the route's later leg walks to
Kargath to learn it and flies on from there, and that flight's pin was the known flight master's icon, over Kargath's
own not-learned one. Reads made on a flight, at a login or a /reload never mark a flight master known either."""

import pytest

SEPULCHER, UNDERCITY, TARREN_MILL, GROMGOL, KARGATH = 10, 11, 13, 20, 21
KNOWN = (SEPULCHER, UNDERCITY, TARREN_MILL, GROMGOL)
LOCH_MODAN = (-4717.4, -3226.7)
HILLSBRAD = (-427.7, -1909.3)


def _start(on_taxi=False, saved=None):
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    pre = ("AGPS_T = 1000; AGPS_ST = 50000; GetServerTime = function() return AGPS_ST end; "
           f"AGPS_TAXI = {'true' if on_taxi else 'false'}; UnitOnTaxi = function() return AGPS_TAXI end; "
           "UnitFactionGroup = function() return 'Horde', 'Horde' end; AGPS_LEVEL = 24\n")
    hook = ("TakeTaxiNode = function() end\n"
            "hooksecurefunc = function(name, fn) if name == 'TakeTaxiNode' then AGPS_TAKE = fn end end\n")
    lua, ns = start(saved=pre + (saved or ""), pre=hook)
    ns.Nav.FUN = False
    lua.execute("C_Timer.After = function(_, fn) fn() end; ERR_NEWTAXIPATH = 'New flight path discovered!'")
    return lua, ns


def _masters(lua):
    return {int(p[5]): (p[4], p[2], p[3]) for p in lua.eval("AGPS_NS.Pois[0]").values() if p[1] == 1}


def _game_reads(lua, masters, kargath_state):
    lua.execute(_reads(masters, kargath_state))


def _reads(masters, kargath_state, nodes=(SEPULCHER, UNDERCITY, TARREN_MILL, GROMGOL, KARGATH)):
    """The game's reads (Lua): the continent's map (no states, as this client's) but Kargath read `kargath_state` (a
    flight's network reported reachable), and the flight map open at Undercity."""
    def entry(n, state):
        s = "nil" if state is None else state
        return f"{{ nodeID = {n}, name = {masters[n][0]!r}, state = {s}, slotIndex = {n}, position = {{ x = 0, y = 0 }} }}"
    cont = ", ".join(entry(n, kargath_state if n == KARGATH else None) for n in nodes)
    fmap = ", ".join(entry(n, 0 if n == UNDERCITY else 1 if n in KNOWN else kargath_state) for n in nodes)
    return (f"""
      C_TaxiMap.GetTaxiNodesForMap = function(mapID) if mapID == 1415 then return {{ {cont} }} end return {{}} end
      C_TaxiMap.GetAllTaxiNodes = function() return {{ {fmap} }} end
      GetTaxiMapID = function() return 1415 end
    """)


def _learn_known(lua, ns, masters):
    """The flight map opened at Undercity: the four known, Kargath not."""
    _game_reads(lua, masters, 2)
    lua.eval("AGPS_FIRE")("TAXIMAP_OPENED")
    lua.eval("AGPS_FIRE")("TAXIMAP_CLOSED")
    assert _known(ns) == set(KNOWN)


def _known(ns):
    return {int(k) for k, v in ns.Nav.KnownFlightNodes()[0].items() if v}


def _saved_known(ns):
    out = {}
    for m, e in ns.CharDB().taxiNodes.items():
        for n in e.nodes.values():
            out[(int(m), int(n.nodeID))] = bool(n.known)
    return out


def test_a_node_read_reachable_on_a_flight_stays_unknown_in_the_air_and_after_landing():
    lua, ns = _start()
    masters = _masters(lua)
    _learn_known(lua, ns, masters)
    lua.execute("AGPS_TAXI = true")  # (in the air)
    _game_reads(lua, masters, 1)  # (every node on the flight's network reported reachable, Kargath too)
    ns.Taxi.Refresh("login")
    ns.Taxi.StoreNodes(1415, lua.eval("C_TaxiMap.GetAllTaxiNodes()"), "taximap")  # (no flight map on a flight)
    lua.eval("AGPS_FIRE")("UI_INFO_MESSAGE", 0, "New flight path discovered!")
    assert ns.Taxi.MarkNearest() is None
    assert KARGATH not in _known(ns)
    assert not any(k for (m, n), k in _saved_known(ns).items() if n == KARGATH)
    lua.execute("AGPS_TAXI = false")  # (landed)
    ns.Taxi.Refresh("login")  # (a read away from a flight master, as at the next login: it says nothing either)
    assert _known(ns) == set(KNOWN)


def test_the_flight_map_and_the_discovery_still_mark_nodes_known_and_they_stay_known():
    lua, ns = _start()
    masters = _masters(lua)
    _learn_known(lua, ns, masters)
    # (Kargath's flight master talked to: "New flight path discovered!", the game's list has it)
    _game_reads(lua, masters, 1)
    lua.eval("AGPS_FIRE")("UI_INFO_MESSAGE", 0, "New flight path discovered!")
    assert _known(ns) == set(KNOWN) | {KARGATH}
    # (read again at a login, and on a flight saying otherwise: still known)
    _game_reads(lua, masters, None)
    ns.Taxi.Refresh("login")
    lua.execute("AGPS_TAXI = true")
    _game_reads(lua, masters, 2)
    ns.Taxi.Refresh("login")
    assert _known(ns) == set(KNOWN) | {KARGATH}

    # a real flight map open at a flight master: known from its states
    lua2, ns2 = _start()
    _game_reads(lua2, masters, 1)
    lua2.eval("AGPS_FIRE")("TAXIMAP_OPENED")
    assert _known(ns2) == set(KNOWN) | {KARGATH}


def _fly(lua, ns, masters, steps=120):
    """Boarded at Undercity for Tarren Mill and carried along. The routes seen."""
    _, tx, ty = masters[TARREN_MILL]
    x, y = lua.eval("AGPS_POS[1]"), lua.eval("AGPS_POS[2]")
    seen = []
    for _ in range(steps):
        x += (tx - x) * 0.01
        y += (ty - y) * 0.01
        lua.execute(f"AGPS_T = AGPS_T + 0.5; AGPS_ST = AGPS_ST + 0.5; AGPS_POS = {{ {x}, {y}, 0 }}")
        ns.GPS.Update()
        seen.append(ns.Nav.route)
    return seen


def _rides(r):
    out = []
    for leg in (r.legs or {}).values():
        if leg.ride:
            out.append(leg.ride)
    for i, st in (r.stretches or {}).items():
        if i > 1 and st:
            out.extend(leg.ride for leg in st.legs.values() if leg.ride)
    return out


def _assert_kargath_unlearned(ns, r):
    for t in _rides(r):
        if t[8] == "flight" and t.to is not None:
            assert int(t.to) != KARGATH, "a flight landing at Kargath, not learned"
            assert t["from"] != KARGATH or t.learn, "a flight from Kargath as if learned"
    pins = [p for p in ns.Nav.RidePins(r).values() if p.kind == "flight"]
    at = [p for p in pins if p.ride.hops and int(p.ride.hops[p.hop]) == KARGATH]
    for p in at:
        assert p.learn and "Learn the flight path" in str(p.title)
        assert ns.GPS.RideIcon(p).endswith("Gray"), "Kargath's pin is the known flight master's icon"
    return at


def test_the_route_flying_to_tarren_mill_never_takes_kargath_as_known():
    lua, ns = _start()
    masters = _masters(lua)
    _learn_known(lua, ns, masters)
    ns.CharDB().faction = "Horde"
    _, x, y = masters[UNDERCITY]
    lua.execute(f"AGPS_MAP = 1420; AGPS_POS = {{ {x}, {y}, 0 }}")
    ns.Nav.SetStops(lua.eval(f"{{ {{ x = {LOCH_MODAN[0]}, y = {LOCH_MODAN[1]}, cont = 0 }},"
                             f" {{ x = {HILLSBRAD[0]}, y = {HILLSBRAD[1]}, cont = 0 }} }}"), False, "red", True)
    # (as Kooki3z's: the stops in their listed order, and yes said to Stranglethorn, Arathi and the Badlands)
    ns.Nav.redOk = lua.eval("{ [1434] = true, [1417] = true, [1418] = true }")
    for _ in range(6):
        lua.execute("AGPS_T = AGPS_T + 0.5")
        ns.GPS.Update()
    pinned = _assert_kargath_unlearned(ns, ns.Nav.route)
    assert pinned, "the route's later leg learns Kargath and flies on: its pin checked"
    lua.execute(f"NumTaxiNodes = function() return 2 end; TaxiNodeName = function(i) return i == {UNDERCITY} and "
                f"{masters[UNDERCITY][0]!r} or {masters[TARREN_MILL][0]!r} end;"
                f"TaxiNodeGetType = function(i) return i == {UNDERCITY} and 'CURRENT' or 'REACHABLE' end")
    lua.execute(f"AGPS_TAKE({TARREN_MILL}); AGPS_TAXI = true")
    _game_reads(lua, masters, 1)  # (the flight's network read reachable in the air)
    ns.Taxi.Refresh("login")
    for r in _fly(lua, ns, masters):
        assert r.flying and r.flying.to == masters[TARREN_MILL][0]
        pinned += _assert_kargath_unlearned(ns, r)
        assert KARGATH not in _known(ns)
    assert pinned, "the route's later leg learns Kargath and flies on: its pin checked"
    lua.execute(f"AGPS_TAXI = false; AGPS_POS = {{ {masters[TARREN_MILL][1]}, {masters[TARREN_MILL][2]}, 0 }}")
    for _ in range(25):
        lua.execute("AGPS_T = AGPS_T + 0.5; AGPS_ST = AGPS_ST + 0.5")
        ns.GPS.Update()
    assert not ns.Nav.route.flying
    _assert_kargath_unlearned(ns, ns.Nav.route)
    assert _known(ns) == set(KNOWN)


DUMP = r"""
local function dump(v, seen)
  local t = type(v)
  if t == "string" then return string.format("%q", v) end
  if t == "number" then return string.format("%.17g", v) end
  if t == "boolean" then return tostring(v) end
  if t ~= "table" or seen[v] then return "nil" end
  seen[v] = true
  local out = {}
  for k, x in pairs(v) do
    local tk = type(k)
    if (tk == "string" or tk == "number" or tk == "boolean") and type(x) ~= "function" and type(x) ~= "userdata" then
      out[#out + 1] = "[" .. dump(k, seen) .. "] = " .. dump(x, seen)
    end
  end
  seen[v] = nil
  return "{" .. table.concat(out, ",\n") .. "}"
end
return function() return "AzerothGPSDB = " .. dump(AzerothGPSDB, {}) end
"""


def test_a_reload_in_the_air_changes_no_flight_master_known():
    lua, ns = _start()
    masters = _masters(lua)
    _learn_known(lua, ns, masters)
    before = _saved_known(ns)
    lua.execute("AGPS_TAXI = true")
    lua.eval("AGPS_FIRE")("PLAYER_LOGOUT")
    text = lua.execute(DUMP)()
    # (back in the air after the /reload: the login's read gives Kargath reachable)
    lua, ns = _start(on_taxi=True, saved=text + "\n" + _reads(masters, 1))
    ns.Taxi.OnLogin()
    assert _saved_known(ns) == before
    assert _known(ns) == set(KNOWN)
