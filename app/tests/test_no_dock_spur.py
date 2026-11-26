"""No out-and-back spur where two walks meet (items 65/65b, Kooki3z 2026-11-24: north of Ratchet the route went out
along the pier to the dock and back, "make a U-turn"; west of Orgrimmar down to the zeppelin towers and back, the line
drawn twice; no ride taken either time). A plan may walk past a dock or flight master (a waypoint: the walk round
blocked ground, Valormok's flight master), but where the two walks meeting there go out and back along the same line,
Nav.TrimSpur cuts it."""

from test_map_redraw import game  # noqa: F401


def test_an_out_and_back_spur_is_cut(game):  # noqa: F811
    lua, ns = game
    N = ns.Nav
    # (south down a road to (0, -100), out along a pier east to (0, 60) ... and back, then on west)
    a = lua.table(0, 100, 0, 0, 0, 60)
    b = lua.table(0, 60, 0, 2, 0, -10, -50, -60)
    a2, b2, cut = N.TrimSpur(a, b)
    assert cut is not None and cut > 100
    end_a, start_b = (a2[len(a2) - 1], a2[len(a2)]), (b2[1], b2[2])
    assert end_a == start_b and abs(end_a[1] - 0) < 6  # (cut where the two part: about the pier's foot)


def test_a_waypoint_walked_past_is_kept(game):  # noqa: F811
    lua, ns = game
    N = ns.Nav
    a = lua.table(0, 0, 100, 0)  # (east to a flight master)
    b = lua.table(100, 0, 100, -100)  # (then south: no way back along the same line)
    assert N.TrimSpur(a, b) is None
