"""The Deeprun Tram's ends round and to scale like the map's other icons (Kooki3z, 2026-11-23: "Make the deeprun tram
icons rendered to scale and round like the other icons"). The tram's gear is a game icon: with Round icons on it is cut
round inside the ring (G.RoundIcon, G.PoiGameIcon) and drawn from the round file at its size; it grows with Icon size
as a flight master does. The ride's pin over it (and a lift's) is round the same way. Both maps (CLAUDE.md)."""

import pytest

from test_map_redraw import game  # noqa: F401
from test_world_map_host import SETUP

GEAR = "Interface\\Icons\\INV_Misc_Gear_01"


def _shown(lua, test):
    return [w for w in lua.eval("AGPS_WIDGETS").values() if w._shown and test(w)]


@pytest.fixture
def at_the_tram(game):  # noqa: F811
    lua, ns = game
    st = ns.settings.gps
    keys = ("iconSize", "roundIcons", "zoom", "useWorldMap", "shown", "minimized")
    was = {k: st[k] for k in keys}
    cdb = ns.CharDB()
    faction = cdb.faction
    cdb.faction = "Alliance"  # (the tram is the Alliance's: N.TransportUsable)
    lua.execute("AGPS_OLD_POS_TRAM = AGPS_POS")
    # (out in Elwynn, Stormwind's end in view: in close the city's own map is drawn instead)
    lua.execute("AGPS_OLD_MAP_TRAM = AGPS_MAP AGPS_MAP = 1429 AGPS_POS = { -8000.0, 300.0, 0 }")
    st.zoom = 2000.0

    def draw(size="medium", round_on=True):
        st.iconSize, st.roundIcons = size, round_on
        ns.GPS.ApplySettings()
        lua.execute("AGPS_T = AGPS_T + 1")
        ns.GPS.Update()
        tram = _shown(lua, lambda w: w.kind == 10 and w.dock is not None and w.icon is not None
                      and str(w.icon.agpsSrc) == GEAR)
        fm = _shown(lua, lambda w: w.kind == 1 and w.icon is not None)
        return tram, fm

    yield lua, ns, draw
    lua.execute("AGPS_POS = AGPS_OLD_POS_TRAM AGPS_MAP = AGPS_OLD_MAP_TRAM")
    cdb.faction = faction
    for k, v in was.items():
        st[k] = v
    ns.GPS.ApplySettings()


def _round(icon):
    return bool(icon.roundOn) and icon.ring is not None and icon.ring._shown


def test_the_tram_end_is_round_and_grows_with_icon_size_like_a_flight_master(at_the_tram):
    lua, ns, draw = at_the_tram
    tram, fm = draw("small")
    assert tram, "the Stormwind end of the Deeprun Tram is on the map"
    b = tram[0]
    assert _round(b.icon)
    small = b._w
    fm_small = fm[0]._w if fm else None
    tram, fm = draw("xlarge")
    b = tram[0]
    assert _round(b.icon)
    assert b._w == pytest.approx(small * 2)  # (Icon size's scale, as every map icon: G.PoiSize)
    assert fm_small
    if fm_small:
        assert fm[0]._w == pytest.approx(fm_small * 2)
    # (Round icons off: square again, no ring)
    tram, _ = draw("medium", round_on=False)
    assert not tram[0].icon.roundOn and not (tram[0].icon.ring and tram[0].icon.ring._shown)


def test_our_own_dock_art_is_left_as_it_is(game):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    assert str(G.PoiGameIcon(lua.eval(f"{{ 10, 0, 0, kind = 'tram' }}"))) == GEAR
    assert G.PoiGameIcon(lua.eval("{ 10, 0, 0, kind = 'zeppelin' }")) is None
    assert G.PoiGameIcon(lua.eval("{ 10, 0, 0, kind = 'boat' }")) is None


def test_the_tram_end_is_round_in_the_world_map_too(at_the_tram):
    lua, ns, draw = at_the_tram
    lua.execute(SETUP)
    st, G = ns.settings.gps, ns.GPS
    try:
        st.useWorldMap, st.shown, st.minimized = True, True, None
        G.ApplySettings()
        lua.globals().AzerothGPS_ToggleMap()
        assert G.WorldMapHosted()
        tram, _ = draw("large")
        assert tram and _round(tram[0].icon)
    finally:
        lua.execute("WorldMapFrame:Hide() ToggleWorldMap = nil")
