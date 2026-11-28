"""The directions' line for a route through enemy ground, by its kind (1.4.2, Kooki3z 2026-11-27): "when going through
elite areas the directions say "Through enemy territory" in red but its should be "Through elite territory" in orange.
If a route has both, say both." Nav.HostileNote: the other faction's guards only, "Through enemy territory" in red as
before; elite areas only, "Through elite territory" in the map's gold (GPSFrame's ELITE_COLOR); both, "Through enemy
and elite territory", each word its own color. The chat line once a trip the same way."""

import pytest

from test_elite_prompt import HG_START, HG_STOP, _ask, _route, char  # noqa: F401
from test_map_redraw import game  # noqa: F401

RED, ORANGE = "|cffff4040", "|cffffc71a"
# (a Horde 30 by Dun Algaz to Loch Modan, no ride: through the Alliance's guards, test_enemy_territory)
BY_DUN_ALGAZ, LOCH_MODAN = (-4300.0, -2500.0), (-5600.0, -3300.0)


@pytest.fixture
def said(char):  # noqa: F811
    lua, ns, be = char
    out = lua.eval("{}")
    old = ns.Print
    ns.Print = lua.eval("function(t) return function(msg) t[#t + 1] = msg end end")(out)
    ns.Nav.hostileSaid = lua.eval("{}")
    yield lambda: [str(out[i]) for i in range(1, len(out) + 1)]
    ns.Print = old
    lua.execute("AGPS_NS.Nav.HostileOnRoute = AGPS_T_HOR or AGPS_NS.Nav.HostileOnRoute AGPS_T_HOR = nil")


def _panel(ns):
    """The directions panel's own copy of the line (GPSFrame's G.hostileNote, under the times)."""
    ns.GPS.Update()
    return ns.GPS.hostileNote


def test_the_orange_is_the_maps_elite_gold(game):  # noqa: F811
    _, ns = game
    c = ns.GPS.ELITE_COLOR
    assert ORANGE == "|cff" + "".join("%02x" % round(c[i] * 255) for i in (1, 2, 3))


def test_a_route_through_only_an_elite_area_says_elite_territory_in_orange(char, said):  # noqa: F811
    # (Hearthglen's 55-63 Scarlet elites at level 25, test_elite_prompt: no guards of the other faction there)
    lua, ns, be = char
    N = ns.Nav
    be("Alliance", 25)
    _route(lua, ns, 0, HG_START, HG_STOP)
    _ask(lua, ns)
    note = str(N.HostileNote())
    assert note.startswith(ORANGE + "Through elite territory: ") and note.endswith("|r"), note
    assert RED not in note and "enemy" not in note
    assert N.hostileElite is True and not N.hostileMixed
    chat = [m for m in said() if "Elite enemies" in m]
    assert len(chat) == 1 and chat[0].startswith(ORANGE + "Elite enemies:|r") and RED not in chat[0], said()
    assert not [m for m in said() if "Enemy territory" in m]


def test_a_route_through_only_enemy_territory_says_it_in_red_as_before(char, said):  # noqa: F811
    lua, ns, be = char
    N, st = ns.Nav, ns.settings.gps
    be("Horde", 30)
    st.avoidElites = False  # (the guards alone)
    _route(lua, ns, 0, BY_DUN_ALGAZ, LOCH_MODAN)
    _ask(lua, ns)
    note = str(N.HostileNote())
    assert note == RED + "Through enemy territory: Dun Algaz|r" or (
        note.startswith(RED + "Through enemy territory: ") and "Dun Algaz" in note), note
    assert ORANGE not in note and "elite" not in note
    assert not N.hostileElite and not N.hostileMixed
    assert _panel(ns) in (None, note)
    chat = [m for m in said() if "Enemy territory" in m]
    assert len(chat) == 1 and chat[0].startswith(RED + "Enemy territory:|r") and ORANGE not in chat[0], said()


def test_a_route_through_both_says_both_each_in_its_color(char, said):  # noqa: F811
    # (the walk past Dun Algaz's guards, with an elite area on the same route: as N.HostileOnRoute lists them, an
    # elite area's entry its third value true)
    lua, ns, be = char
    N, st = ns.Nav, ns.settings.gps
    be("Horde", 30)
    st.avoidElites = False
    _route(lua, ns, 0, BY_DUN_ALGAZ, LOCH_MODAN)
    lua.execute("""
      AGPS_T_HOR = AGPS_NS.Nav.HostileOnRoute
      AGPS_NS.Nav.HostileOnRoute = function(r)
        local out = AGPS_T_HOR(r) or {}
        out[#out + 1] = { "Thelgen Rock", 60, true }
        return out
      end""")
    _ask(lua, ns)
    note = str(N.HostileNote())
    assert note.startswith(RED + "Through enemy|r and " + ORANGE + "elite|r territory: "), note
    assert "Dun Algaz" in note and "Thelgen Rock" in note
    assert N.hostileMixed is True and not N.hostileElite
    chat = [m for m in said() if "territory" in m]
    assert len(chat) == 1 and chat[0].startswith(RED + "Enemy|r and " + ORANGE + "elite|r territory: "), said()
    assert "Dun Algaz" in chat[0] and "Thelgen Rock" in chat[0] and "red and gold on the map" in chat[0]


def test_the_new_lines_are_in_every_language():
    from azerothgps.paths import ADDON_DIR

    keys = ['L["' + ORANGE + 'Through elite territory: %s|r"]',
            'L["' + RED + 'Through enemy|r and ' + ORANGE + 'elite|r territory: %s"]',
            'L["' + ORANGE + 'Elite enemies:|r the route passes the elites at %s (gold on the map)."]']
    for code in ("deDE", "esES", "esMX", "frFR", "itIT", "koKR", "ptBR", "ruRU", "zhCN", "zhTW"):
        text = (ADDON_DIR / "Locales" / f"{code}.lua").read_text(encoding="utf-8")
        for k in keys:
            line = next((ln for ln in text.splitlines() if ln.startswith(k + " = ")), None)
            assert line, (code, k)
            if "Through enemy|r" in k:
                assert line.split(" = ", 1)[1].startswith('"' + RED) and ORANGE in line.split(" = ", 1)[1], line
            else:
                assert line.split(" = ", 1)[1].startswith('"' + ORANGE), line
