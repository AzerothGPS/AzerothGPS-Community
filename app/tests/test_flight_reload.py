"""A /reload in the air (reported 2026-11-17: "/reload on a flight breaks the routing pause and timer"). The flight
being flown (where it lands, when it took off) was kept only in Taxi.lua's locals: after a /reload the route was
worked out again from the moving player, "lands in" was lost, and the flight's time was never learned. It's kept in
the character's saved data now: the flight goes on as one, its time counted from the real take-off, and learned once
on landing. A relog the game keeps them flying through too (GetTime starts again then: the server's clock)."""

import pytest

TARREN_MILL, UNDERCITY = "Tarren Mill, Hillsbrad", "Undercity, Tirisfal"
KEY = f"{TARREN_MILL} > {UNDERCITY}"
LEARNED = 400.0  # (s: the flight's time learned before, so its countdown is the clock's, not its distance's)
STOP = (-35.0, -935.0)  # (Southshore)

# The saved variables as the game writes them (strings, numbers, booleans and tables; nothing else is saved).
DUMP = r"""
local function dump(v, seen)
  local t = type(v)
  if t == "string" then return string.format("%q", v) end
  if t == "number" then
    if v ~= v or v == math.huge or v == -math.huge then return "0" end
    return string.format("%.17g", v)
  end
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

# The game's taxi functions (the flight map open at Tarren Mill: slot 1 here, slot 2 Undercity).
TAXI_API = """
  NumTaxiNodes = function() return 2 end
  TaxiNodeGetType = function(i) return i == 1 and 'CURRENT' or 'REACHABLE' end
  TaxiNodeName = function(i) return i == 1 and '{tm}' or '{uc}' end
  GetTaxiMapID = function() return 1415 end
  C_TaxiMap.GetAllTaxiNodes = function() return {{
    {{ nodeID = {tmNode}, slotIndex = 1, state = 0, name = '{tm}' }},
    {{ nodeID = {ucNode}, slotIndex = 2, state = 1, name = '{uc}' }} }} end
"""


def _masters(lua):
    out = {}
    for p in lua.eval("AGPS_NS.Pois[0]").values():
        if p[1] == 1:
            out[p[4]] = (p[5], p[2], p[3])
    return out


def _session(saved=None, t=None, server=None, on_taxi=False):
    """A game session: the addon loaded with `saved` (the saved variables' text) at GetTime `t`, server time
    `server`, on a taxi or not."""
    from azerothgps.gameharness import start
    clock = (f"AGPS_T = {t}; " if t is not None else "") + (f"AGPS_ST = {server}; " if server is not None else "")
    pre = (clock + "GetServerTime = function() return AGPS_ST end; "
           + f"UnitOnTaxi = function() return {'true' if on_taxi else 'false'} end; "
           + 'UnitFactionGroup = function() return "Horde", "Horde" end\n')
    # (the game's TakeTaxiNode, hooked by Taxi.lua as it loads: the flight map's click)
    hook = ("TakeTaxiNode = function() end\n"
            "hooksecurefunc = function(name, fn) if name == 'TakeTaxiNode' then AGPS_TAKE = fn end end\n")
    lua, ns = start(saved=pre + (saved or "AGPS_ST = AGPS_ST or 50000"), pre=hook)
    ns.Nav.FUN = False
    masters = _masters(lua)
    lua.execute(TAXI_API.format(tm=TARREN_MILL, uc=UNDERCITY, tmNode=masters[TARREN_MILL][0],
                                ucNode=masters[UNDERCITY][0]))
    return lua, ns, masters


def _first_session(lua, ns, masters):
    """Boarded at Tarren Mill for Undercity, the route to Southshore set; flown a minute. The player's (x, y)."""
    cdb = ns.CharDB()
    cdb.faction = "Horde"
    nodes = "".join(f"{{ nodeID = {m[0]}, known = true }}, " for m in masters.values())
    cdb.taxiNodes = lua.eval(f"{{ [1415] = {{ nodes = {{ {nodes} }} }} }}")
    cdb.flights[KEY] = lua.eval(f"{{ from = '{TARREN_MILL}', to = '{UNDERCITY}', seconds = {LEARNED}, samples = 1 }}")
    ns.Nav.FlightsChanged()
    _, x, y = masters[TARREN_MILL]
    lua.execute(f"AGPS_MAP = 1424; AGPS_POS = {{ {x}, {y}, 0 }}; AGPS_T = 1000; AGPS_ST = 50000")
    ns.Nav.SetStops(lua.eval(f"{{ {{ x = {STOP[0]}, y = {STOP[1]}, cont = 0 }} }}"), False, "red")
    for _ in range(10):
        lua.execute("AGPS_T = AGPS_T + 0.5")
        ns.GPS.Update()
    lua.execute("AGPS_TAKE(2)")  # (Undercity clicked on the flight map: the TakeTaxiNode hook)
    lua.execute("UnitOnTaxi = function() return true end")
    return _fly(lua, ns, masters, x, y, 60)


def _fly(lua, ns, masters, x, y, seconds, step=0.5):
    """Carried towards Undercity for `seconds` (GetTime and the server's clock on), the map redrawn. The routes seen."""
    _, tx, ty = masters[UNDERCITY]
    seen = []
    for _ in range(int(seconds / step)):
        x += (tx - x) * 0.004
        y += (ty - y) * 0.004
        lua.execute(f"AGPS_T = AGPS_T + {step}; AGPS_ST = AGPS_ST + {step}; AGPS_POS = {{ {x}, {y}, 0 }}")
        ns.GPS.Update()
        seen.append(ns.Nav.route)
    return x, y, seen


def _reload(lua, gap, relog=False):
    """The saved variables written (PLAYER_LOGOUT, as at a /reload), and the game `gap` seconds on: the same GetTime
    after a /reload, a new one after a relog."""
    lua.eval("AGPS_FIRE")("PLAYER_LOGOUT")
    text = lua.execute(DUMP)()
    t = 50 if relog else lua.eval("AGPS_T") + gap
    return text, t, lua.eval("AGPS_ST") + gap, lua.eval("AGPS_POS")


def _assert_flying(ns, seen, x, y):
    for r in seen:
        assert r and r.flying and r.flying.to == UNDERCITY, "the route was worked out again in the air"
        assert r.legs[1].ride[8] == "flight" and r.legs[1].ride.flying
    r = seen[-1]
    assert (r.pts[1], r.pts[2]) == pytest.approx((x, y)), "the flight's line isn't from the player"
    status = ns.Nav.Status(x, y, 0)
    assert "Flying to " + UNDERCITY in status and "lands in" in status


@pytest.mark.parametrize("relog", [False, True], ids=["reload", "relog"])
def test_a_reload_in_the_air_keeps_the_flight_its_countdown_and_learns_its_time_once(relog):
    pytest.importorskip("lupa.lua51")
    lua, ns, masters = _session()
    x, y, seen = _first_session(lua, ns, masters)
    _assert_flying(ns, seen, x, y)
    took_off = lua.eval("AGPS_ST") - 59.5  # (seen in the air at the first redraw)
    left_before = seen[-1].flying.seconds
    assert left_before == pytest.approx(LEARNED - 60, abs=1.5)

    gap = 20  # (the loading screen)
    text, t, server, pos = _reload(lua, gap, relog)
    lua, ns, masters = _session(text, t=t, server=server, on_taxi=True)
    lua.execute(f"AGPS_MAP = 1424; AGPS_POS = {{ {pos[1]}, {pos[2]}, 0 }}")
    assert len(ns.Nav.stops) == 1  # (the route's stop restored, as at any /reload)
    x, y, seen = _fly(lua, ns, masters, pos[1], pos[2], 30)
    _assert_flying(ns, seen, x, y)
    # (counting down from the real take-off: not the whole flight again from the /reload)
    assert seen[0].flying.seconds == pytest.approx(left_before - gap - 0.5, abs=1.5)
    assert seen[-1].flying.seconds == pytest.approx(LEARNED - 60 - gap - 30, abs=1.5)

    # landed at Undercity: its time learned once, as the whole flight (not the part after the /reload)
    _, ux, uy = masters[UNDERCITY]
    flown = LEARNED - 5
    lua.execute(f"AGPS_T = AGPS_T + ({took_off + flown} - AGPS_ST); AGPS_ST = {took_off + flown}; "
                f"UnitOnTaxi = function() return false end; AGPS_MAP = 1458; AGPS_POS = {{ {ux}, {uy}, 0 }}")
    for _ in range(4):
        lua.execute("AGPS_T = AGPS_T + 0.5")
        ns.GPS.Update()
    cdb = ns.CharDB()
    f = cdb.flights[KEY]
    assert f.samples == 2, "the flight's time wasn't learned once"
    assert f.seconds == pytest.approx((LEARNED + flown) / 2, abs=1)
    assert cdb.flying is None
    r = ns.Nav.route
    assert not (r and r.flying), "the route didn't go on from the landing"


def test_a_saved_flight_not_flown_any_more_is_dropped_and_never_restored():
    # (logged in on the ground after a flight saved in the air, then a quest's flight, no flight map: not that one)
    pytest.importorskip("lupa.lua51")
    lua, ns, masters = _session()
    x, y, _ = _first_session(lua, ns, masters)
    text, t, server, pos = _reload(lua, 20)
    lua, ns, masters = _session(text, t=t, server=server, on_taxi=False)
    T = ns.Taxi
    assert T.Current() is None
    assert ns.CharDB().flying is not None  # (a moment after loading: the game may not have put them back yet)
    lua.execute(f"AGPS_T = AGPS_T + {T.RESTORE_GRACE + 1}")
    assert T.Current() is None and ns.CharDB().flying is None
    lua.execute("UnitOnTaxi = function() return true end")
    f = T.Current()
    assert f and f.to is None and f.start == lua.eval("AGPS_T")


def test_a_saved_flight_long_ago_is_not_restored():
    pytest.importorskip("lupa.lua51")
    lua, ns, masters = _session()
    _first_session(lua, ns, masters)
    text, t, server, _ = _reload(lua, 0)
    lua, ns, masters = _session(text, t=t, server=server + 3600, on_taxi=True)
    f = ns.Taxi.Current()
    assert f and f.to is None and f.start == lua.eval("AGPS_T")
