""""Take it?" for a walk across an elite area at its own end (item 124, Kooki3z 2026-11-27, a level 25 on the private
client: "shouldn't I get a popup for this as well with the "take it?" question for elites?"). From Hearthglen's west
edge (Western Plaguelands, 23 yd out of its 55-63 Scarlet elites) to a stop at its north edge (map 46, 13) the walk went
straight through the middle, drawn red, with no question. Both ends were within Router.ELITE_NEAR of the area, so the
whole area was the walk's own (item 91, df3b8695: a walk starting or ending in an elite area isn't priced for it) and
Nav.HostileOnRoute left it out of the question too. The router still leaves it out; the question now leaves out only
the walk's way out of the start's area and in to the stop's (Nav.EliteCrossing), and asks about the rest."""

import pytest

from test_map_redraw import game  # noqa: F401
from test_world_map_host import SETUP

# (Kooki3z's GM.log: .go xyz 2954 -1321 165 0; the stop: Western Plaguelands 46, 13, by Data/Maps.lua's bounds)
HG_START, HG_STOP = (2954.0, -1321.0), (2994.0, -1561.0)
# (Thousand Needles to Camp Taurajo at level 45, Horde: round Razorfen Downs' elites, test_elite_areas)
DARKCLOUD, TAURAJO = (-4950.0, -1983.0), (-2380.0, -1882.0)


@pytest.fixture
def char(game):  # noqa: F811
    lua, ns = game
    st = ns.settings.gps
    lua.execute("AGPS_P_UFG = UnitFactionGroup AGPS_P_POS = AGPS_POS AGPS_P_LVL = AGPS_LEVEL")
    saved = (ns.CharDB().faction, st.avoidElites, st.eliteOffset, st.avoidHostile, st.useFlights)
    st.useFlights, st.avoidElites, st.eliteOffset, st.avoidHostile = False, None, None, None
    lua.execute("""
      AGPS_P_ASKED = {}
      AGPS_P_CH = AGPS_NS.GPS.ConfirmHostile
      AGPS_NS.GPS.ConfirmHostile = function(names, side, yes, no, elite)
        AGPS_P_ASKED[#AGPS_P_ASKED + 1] = { names = table.concat(names, ", "), elite = elite }
        return AGPS_P_CH(names, side, yes, no, elite)
      end""")

    def be(faction, level):
        lua.execute(f"UnitFactionGroup = function() return '{faction}' end; AGPS_LEVEL = {level}")
        ns.CharDB().faction = faction

    yield lua, ns, be
    lua.execute("AGPS_NS.GPS.ConfirmHostile = AGPS_P_CH")
    pending = ns.GPS.PendingQuestion()
    if pending:
        pending.no._scripts.OnClick(pending.no, "LeftButton")
    ns.Nav.Clear()
    ns.Nav.route = None
    (ns.CharDB().faction, st.avoidElites, st.eliteOffset, st.avoidHostile, st.useFlights) = saved
    lua.execute("UnitFactionGroup = AGPS_P_UFG AGPS_POS = AGPS_P_POS AGPS_LEVEL = AGPS_P_LVL")
    ns.Router.Reset()


def _route(lua, ns, cont, a, b):
    N, R = ns.Nav, ns.Router
    N.Clear()
    lua.execute(f"AGPS_POS = {{ {a[0]}, {a[1]}, {cont} }}")
    N.SetStops(lua.eval(f"{{ {{ x = {b[0]}, y = {b[1]}, cont = {cont}, name = 'stop' }} }}"), False, "red")
    N.Invalidate(True, True)
    R.WallsChanged()
    r = N.Route(a[0], a[1], cont)
    assert r and not r.pending
    return r


def _ask(lua, ns):
    """Nav's look for enemies on the route (its background job run out): the questions asked."""
    R, N = ns.Router, ns.Nav
    now = lua.eval("function() return os.clock() * 1000 end")
    lua.execute("AGPS_P_ASKED = {}")
    N.CheckHostileRoute()
    while R.HasWork():
        R.Pump(now() + 50, now)
    asked = lua.eval("AGPS_P_ASKED")
    return [(str(asked[i].names), asked[i].elite is True) for i in range(1, len(asked) + 1)]


def _red_yards(ns, r):
    """Yards of the walk drawn red (N.HostileSpans, the map's own)."""
    N = ns.Nav
    yd = 0.0
    for part in r.parts.values():
        pts = part.pts
        for i in range(1, len(pts) // 2):
            spans = N.HostileSpans(part, i)
            if spans:
                d = ((pts[2 * i + 1] - pts[2 * i - 1]) ** 2 + (pts[2 * i + 2] - pts[2 * i]) ** 2) ** 0.5
                yd += d * sum(spans[j + 1] - spans[j] for j in range(1, len(spans), 2))
    return yd


def test_hearthglen_at_level_25_asks_take_it_in_both_map_modes(char):
    lua, ns, be = char
    G, N, R, st = ns.GPS, ns.Nav, ns.Router, ns.settings.gps
    be("Alliance", 25)
    # (the level rule: Hearthglen's 55-63 elites far above a level 25 are avoided, never skipped)
    assert R.EliteMin() is not None and R.EliteMin() <= 63
    key = R.HostileSide()
    assert R.EliteTownsAt(0, 2850.0, -1450.0, key)  # (among them, Hearthglen's middle)
    # (both ends at the area: Router.ELITE_NEAR, the walk's own area, not priced, item 91)
    hg = R.EliteTownsAt(0, 2850.0, -1450.0, key)
    for p in (HG_START, HG_STOP):
        near = R.HostileTownsNear(0, key, p[0], p[1])
        assert near and any(t in near.keys() for t in hg.keys())
    lua.execute(SETUP)
    was = {k: st[k] for k in ("useWorldMap", "replaceMinimap", "shown", "minimized")}
    try:
        st.shown, st.minimized, st.replaceMinimap = True, None, False
        for world_map in (False, True):
            st.useWorldMap = world_map
            G.ApplySettings()
            if world_map:
                lua.execute("ToggleWorldMap()")
                assert G.WorldMapHosted()
            r = _route(lua, ns, 0, HG_START, HG_STOP)
            assert _red_yards(ns, r) > 100  # (through the middle, drawn red as in his screenshot)
            towns = N.HostileOnRoute(r)
            assert towns and towns[1][3] is True and towns[1][2] > 100, towns and [tuple(t.values()) for t in towns.values()]
            asked = _ask(lua, ns)
            assert len(asked) == 1 and asked[0][1], asked
            box = G.PendingQuestion()
            assert box and "(elite enemies). Take it?" in str(box.text._text) and box._shown
            box.yes._scripts.OnClick(box.yes, "LeftButton")
            assert N.RiskAnswer(N.dest) is True and N.hostileAsking is None
            if world_map:
                lua.execute("ToggleWorldMap()")
    finally:
        lua.execute("WorldMapFrame:Hide() ToggleWorldMap = nil")
        for k, v in was.items():
            st[k] = v
        G.WorldMapChanged()
        G.ApplySettings()


def test_a_walk_into_an_elite_area_from_its_edge_isnt_asked_about(char):
    """The way in to a stop inside the area (and out from a start inside it) is still the walk's own: not asked."""
    lua, ns, be = char
    R, N = ns.Router, ns.Nav
    be("Alliance", 25)
    key = R.HostileSide()
    # (from just outside Hearthglen's west edge to a stop just inside it)
    hg = R.EliteTownsAt(0, 2850.0, -1450.0, key)
    inside = None
    for d in range(0, 120, 4):
        p = (HG_START[0], HG_START[1] - d)
        at = R.EliteTownsAt(0, p[0], p[1], key)
        if at and any(t in at.keys() for t in hg.keys()):
            inside = (p[0], p[1] - 15)
            break
    assert inside
    r = _route(lua, ns, 0, HG_START, inside)
    assert not N.HostileOnRoute(r)
    assert _ask(lua, ns) == []


def test_a_trip_that_goes_round_the_elites_isnt_asked_about(char):
    lua, ns, be = char
    N = ns.Nav
    be("Horde", 45)
    r = _route(lua, ns, 1, DARKCLOUD, TAURAJO)
    assert not any(t[3] for t in (N.HostileOnRoute(r) or {}).values())
    assert not any(e for _, e in _ask(lua, ns))


def test_the_guards_take_it_is_as_before(char):
    """The other faction's guards: the same towns, the same question, with the elite areas avoided or not; a guards'
    town at a walk's end still the walk's own (R.TOWN_NEAR)."""
    lua, ns, be = char
    N, st = ns.Nav, ns.settings.gps
    be("Horde", 60)
    # (Dun Morogh, Gol'Bolar Quarry to past Dun Algaz: through Kharanos's guards, item 87)
    a, b = (-5659.9, -1389.3), (-5193.4, -2083.7)
    seen = {}
    for elites in (False, None):
        st.avoidElites = elites
        r = _route(lua, ns, 0, a, b)
        towns = N.HostileOnRoute(r)
        seen[elites] = sorted((str(t[1]), round(t[2])) for t in (towns or {}).values() if not t[3])
        asked = _ask(lua, ns)
        assert asked and not asked[0][1], asked
        assert "Alliance guards" in str(ns.GPS.PendingQuestion().text._text)
        q = ns.GPS.PendingQuestion()
        q.yes._scripts.OnClick(q.yes, "LeftButton")
    assert seen[False] and seen[False] == seen[None], seen
    # (a stop in Kharanos itself: its guards are the walk's own, not asked about)
    r = _route(lua, ns, 0, a, (-5586.0, -482.0))
    assert not [t for t in (N.HostileOnRoute(r) or {}).values() if str(t[1]) == "Kharanos"]
