"""The route's flight on the flight map (a player's request, 2026-11-17: "When my route has a flight leg ... and I open
the flight master's map, please put a ring round X, so I can click the right one straight away"): a ring round the
flight master the route flies to, only the route's next flight, only at the flight master it boards at, display
only, and an option to turn it off (Taxi.MarkTaxiMap)."""

from azerothgps.gameharness import start


def _setup(lua, ns, here=7, legs=None, frame="taxi"):
    """At flight master node `here` (slot 1) with nodes 7 (slot 1), 12 (slot 2) and 40 (slot 3) on the flight map;
    the route: walk, flight 7 > 12, walk, flight 12 > 40 (or `legs`)."""
    lua.execute(f"""
      C_Timer.After = function(_, fn) fn() end
      GetTaxiMapID = function() return 1415 end
      local here = {here}
      C_TaxiMap.GetAllTaxiNodes = function()
        return {{
          {{ nodeID = 7, slotIndex = 1, name = "Menethil Harbor, Wetlands", state = here == 7 and 0 or 1 }},
          {{ nodeID = 12, slotIndex = 2, name = "Ironforge, Dun Morogh", state = here == 12 and 0 or 1 }},
          {{ nodeID = 40, slotIndex = 3, name = "Thelsamar, Loch Modan", state = here == 40 and 0 or 1 }},
        }}
      end
      NumTaxiNodes = function() return 3 end
      TaxiNodeName = function(i) return ({{ "Menethil Harbor, Wetlands", "Ironforge, Dun Morogh", "Thelsamar, Loch Modan" }})[i] end
      TaxiNodeGetType = function(i) return ({{ [7] = 1, [12] = 2, [40] = 3 }})[here] == i and "CURRENT" or "REACHABLE" end
    """)
    if frame == "taxi":
        lua.execute("""
          TaxiFrame = CreateFrame("Frame", "TaxiFrame", UIParent)
          TaxiFrame:Show()
          for i = 1, 3 do _G["TaxiButton" .. i] = CreateFrame("Button", "TaxiButton" .. i, TaxiFrame) end
        """)
    route = legs or """{
      { walk = true },
      { ride = { 0, 1, 1, 0, 2, 2, 60, "flight", "Menethil Harbor, Wetlands", "Ironforge, Dun Morogh", "flight master", from = 7, to = 12 }, from = 1 },
      { walk = true },
      { ride = { 0, 2, 2, 0, 3, 3, 60, "flight", "Ironforge, Dun Morogh", "Thelsamar, Loch Modan", "flight master", from = 12, to = 40 }, from = 1 },
    }"""
    lua.execute(f"AGPS_NS.Nav.route = {{ legs = {route} }}")


def _ring_on(lua):
    """The slot whose button (or pin) the ring is shown on, else None."""
    return lua.eval("""(function()
      local r = AGPS_NS.Taxi.ring
      if not (r and r:IsShown()) then return nil end
      for i = 1, 3 do
        if rawget(_G, "TaxiButton" .. i) and r:GetParent() == _G["TaxiButton" .. i] then return i end
        if AGPS_PINS and r:GetParent() == AGPS_PINS[i] then return i end
      end
      return -1
    end)()""")


def test_the_flight_master_the_route_flies_to_is_ringed_on_the_flight_map():
    lua, ns = start()
    _setup(lua, ns)
    # (the timers held: the flights read for the first time put the route aside, then it's worked out again)
    lua.execute("AGPS_LATER = {} C_Timer.After = function(_, fn) AGPS_LATER[#AGPS_LATER + 1] = fn end")
    route = lua.eval("AGPS_NS.Nav.route")
    lua.eval("AGPS_FIRE")("TAXIMAP_OPENED")
    lua.execute("AGPS_NS.Nav.route = nil")
    lua.execute("AGPS_LATER[1]() AGPS_LATER[2]()")
    assert _ring_on(lua) is None
    ns.Nav.route = route
    lua.execute("for i = 3, #AGPS_LATER do AGPS_LATER[i]() end")
    assert _ring_on(lua) == 2  # (Ironforge, the route's first flight; not the later Thelsamar)
    lua.eval("AGPS_FIRE")("TAXIMAP_CLOSED")
    assert _ring_on(lua) is None


def test_only_the_next_flight_and_only_where_the_route_boards():
    lua, ns = start()
    _setup(lua, ns, here=12)  # (Ironforge's flight master: the route's first flight boards at Menethil)
    assert ns.Taxi.MarkTaxiMap() is False
    assert _ring_on(lua) is None


def test_no_flight_in_the_route_rings_nothing():
    lua, ns = start()
    _setup(lua, ns, legs="{ { walk = true } }")
    assert ns.Taxi.MarkTaxiMap() is False


def test_the_option_turns_it_off():
    lua, ns = start()
    _setup(lua, ns)
    ns.settings.gps.flightMapRing = False
    assert ns.Taxi.MarkTaxiMap() is False
    assert _ring_on(lua) is None
    ns.settings.gps.flightMapRing = True
    assert ns.Taxi.MarkTaxiMap() is True


def test_by_name_when_the_game_gives_no_node_ids():
    lua, ns = start()
    _setup(lua, ns)
    lua.execute("C_TaxiMap.GetAllTaxiNodes = function() return {} end")
    assert ns.Taxi.MarkTaxiMap() is True
    assert _ring_on(lua) == 2


def test_the_flight_maps_pin_when_that_map_is_used():
    lua, ns = start()
    _setup(lua, ns, frame="flightmap")
    lua.execute("""
      FlightMapFrame = CreateFrame("Frame", "FlightMapFrame", UIParent)
      FlightMapFrame:Show()
      local pins = {}
      for i, id in ipairs({ 7, 12, 40 }) do
        local p = CreateFrame("Button", nil, FlightMapFrame)
        p.taxiNodeData = { nodeID = id, slotIndex = i }
        pins[i] = p
      end
      AGPS_PINS = pins
      FlightMapFrame.EnumeratePinsByTemplate = function(self, t)
        local i = 0
        return function() i = i + 1 return pins[i] end
      end
    """)
    assert ns.Taxi.MarkTaxiMap() is True
    assert _ring_on(lua) == 2
