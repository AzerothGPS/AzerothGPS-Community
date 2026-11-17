"""The directions ahead cost little as the route is trimmed (reported 2026-11-13: heavy stuttering running through
Orgrimmar; the debug log had the redraw's text and the arrow window at 100-240 ms a second). The route is trimmed every
2 yd the player goes on, and each trim the arrow window and the map's panel each worked out the directions again, a
nearest-road search for every stretch of road in Turns.Places (Router.PlaceAt), 20-30 ms each in Orgrimmar."""

from azerothgps.gameharness import start

TRIM = """function(r, i)
  local p1 = r.parts[1]
  local skip = math.min(i, #p1.pts / 2 - 2)
  local ax, ay, bx, by = p1.pts[2*skip+1], p1.pts[2*skip+2], p1.pts[2*skip+3], p1.pts[2*skip+4]
  local pts, kinds = { ax + (bx - ax) * 0.3, ay + (by - ay) * 0.3 }, {}
  for k = 2*skip+3, #p1.pts do pts[#pts+1] = p1.pts[k] end
  for k = skip+1, #p1.kinds do kinds[#kinds+1] = p1.kinds[k] end
  local part = {}
  for k, v in pairs(p1) do part[k] = v end
  part.pts, part.kinds, part.zs, part.fz = pts, kinds, nil, nil
  local route = {}
  for k, v in pairs(r) do route[k] = v end
  route.parts = { part }
  for k = 2, #r.parts do route.parts[k] = r.parts[k] end
  return route
end"""


def test_a_trimmed_route_through_orgrimmar_reworks_its_directions_cheaply():
    lua, ns = start()
    N, T, R = ns.Nav, ns.Turns, ns.Router
    lua.execute("AGPS_POS[1], AGPS_POS[2], AGPS_POS[3] = 1505.4, -4419.3, 1")  # (the Valley of Strength)
    N.SetStops(lua.eval("{ { x = 2000.0, y = -4700.0, cont = 1, name = 'Valley of Honor' } }"), False, "red")
    route = N.Route(1505.4, -4419.3, 1)
    assert route and len(route.parts[1].pts) > 20
    trim = lua.eval(TRIM)

    # (the arrow's label and the panel's: worked out once, each its own arrival)
    runs = T.aheadRuns or 0
    _, a = T.Ahead(route, "Stop 1")
    _, b = T.Ahead(route, "Valley of Honor")
    assert (T.aheadRuns or 0) == runs + 1
    assert a[len(a)].text == "Arrive at Stop 1" and b[len(b)].text == "Arrive at Valley of Honor"
    assert len(a) == len(b) and all(a[k].text == b[k].text for k in range(1, len(a)))

    # (trimmed: only the new stretches' places are looked up again)
    lua.execute("""
      AGPS_NEAREST_CALLS = 0
      local real = AGPS_NS.Router.NearestEdges
      AGPS_NS.Router.NearestEdges = function(...) AGPS_NEAREST_CALLS = AGPS_NEAREST_CALLS + 1 return real(...) end
      AGPS_NEAREST_REAL = real
    """)
    try:
        for i in range(1, 6):
            lua.execute("AGPS_NEAREST_CALLS = 0")
            r = trim(route, i)
            _, ms = T.Ahead(r, "Stop 1")
            T.Ahead(r, "Valley of Honor")
            assert lua.eval("AGPS_NEAREST_CALLS") <= 4, lua.eval("AGPS_NEAREST_CALLS")
            # (the same directions as worked out with nothing kept)
            fresh = T.Maneuvers(T.Path(r), "Stop 1", T.HORIZON_YD)
            assert [ms[k].text for k in range(1, len(ms) + 1)] == [fresh[k].text for k in range(1, len(fresh) + 1)]
    finally:
        lua.execute("AGPS_NS.Router.NearestEdges = AGPS_NEAREST_REAL")
