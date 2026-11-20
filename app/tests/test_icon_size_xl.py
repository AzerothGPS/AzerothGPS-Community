"""Extra large map icons (1.3.9, asked 2026-11-18: "add option for Extra Large map icons, make sure you consider scaling
for all map icons like flight paths etc"): Options > Map icons' Icon size has Extra large (`iconSize` "xlarge", twice
Small, GPSFrame's G.ICON_SIZES); every icon the map draws grows with it, in the map's window and in the game's world
map, on the minimap too, with its hit area; the art is drawn at the sizes it lands on (no filter above LINEAR: the
client crashes on one); the setting is kept over a /reload."""

import re
from pathlib import Path

import pytest

from azerothgps import iconscale
from azerothgps.coast import RING_SIZES, ring_file
from test_map_redraw import game  # noqa: F401
from test_world_map_host import SETUP

ADDON = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS"
LOCALES = ("deDE", "esES", "esMX", "frFR", "itIT", "koKR", "ptBR", "ruRU", "zhCN", "zhTW")
# the map's own icons' sizes before Icon size (GPSFrame's DrawPois: G.PoiSize), and the game icons' G.ICON_PX
POI_SIZES = (12, 13, 14, 16, 18, 20, 22)


def test_the_option_has_extra_large_in_every_language():
    text = (ADDON / "Options.lua").read_text(encoding="utf-8")
    # (a dropdown: radio buttons under pictures for a day, 2026-11-19, then a dropdown again)
    block = text[text.index('Dropdown(L["Icon size"]'):]
    block = block[:block.index("GPS().iconSize = v")]
    order = re.findall(r'value = "(\w+)"', block)
    assert order == ["small", "medium", "large", "xlarge"] and 'text = L["Extra large"]' in block
    for loc in LOCALES:
        lines = (ADDON / "Locales" / f"{loc}.lua").read_text(encoding="utf-8")
        m = re.search(r'^L\["Extra large"\] = "([^"]+)"$', lines, re.M)
        assert m and m.group(1) != "Extra large", loc


def test_extra_large_lands_on_sizes_drawn_pixel_for_pixel():
    # (the client shrinks art by its LINEAR filter alone: each size an icon is shown at is drawn, iconscale.py and the
    # rings, and Extra large's sizes are among them)
    table = (ADDON / "Data" / "IconSizes.lua").read_text(encoding="utf-8")
    sizes = [int(n) for n in re.search(r"sizes = \{ ([\d, ]+) \}", table).group(1).split(", ")]
    assert sizes == list(RING_SIZES)
    gps = (ADDON / "GPSFrame.lua").read_text(encoding="utf-8")
    ring = [int(n) for n in re.search(r"G\.RING_SIZES = \{ ([\d, ]+) \}", gps).group(1).split(", ")]
    assert ring == list(RING_SIZES)
    for n in POI_SIZES:
        assert n * 2 in RING_SIZES, n
        assert ring_file(n * 2).exists(), n
    icons = ADDON / "Media" / "Icons"
    for key in ("icons/inv_misc_book_09", "icons/inv_misc_herb_01"):
        base = iconscale.base_name(key)
        for n in (26, 32, 36, 44):
            assert (icons / f"{base}_{n}.jpg").exists() and (icons / f"{base}_{n}r.jpg").exists(), (key, n)


@pytest.fixture
def sized(game):  # noqa: F811
    lua, ns = game
    st = ns.settings.gps
    was = st.iconSize
    lua.execute("AGPS_OLD_PSS_XL = GetPhysicalScreenSize\nGetPhysicalScreenSize = function() return 2560, 1440 end")

    def use(size):
        st.iconSize = size
        ns.GPS.ApplySettings()
        lua.execute("AGPS_T = AGPS_T + 1")
        ns.GPS.Update()

    yield lua, ns, use
    lua.execute("GetPhysicalScreenSize = AGPS_OLD_PSS_XL")
    st.iconSize = was
    ns.GPS.ApplySettings()


def _shown(lua, test):
    return [w for w in lua.eval("AGPS_WIDGETS").values() if w._shown and test(w)]


def test_the_scales(game):  # noqa: F811
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    was = st.iconSize
    try:
        want = {"small": (1, 1), "medium": (1.25, 1), "large": (1.5, 1.2), "xlarge": (2, 1.6)}
        for size, (k, grow) in want.items():
            st.iconSize = size
            assert G.PoiScale() == k and G.IconGrow() == pytest.approx(grow), size
            assert ns.OtherPins.Grow() == pytest.approx(grow)
            assert G.MinimapIconSize(14) == pytest.approx(14 * grow)
        st.iconSize = "huge"  # (a value it doesn't know: Medium)
        assert G.PoiScale() == 1.25
    finally:
        st.iconSize = was


def test_every_map_icon_doubles_from_small_to_extra_large_hit_area_and_all(sized):
    lua, ns, use = sized
    G, P = ns.GPS, ns.Pins
    pin = P.Add(lua.eval("{ level = 0, x = 2254, y = 293, name = 'Big', icon = 136777 }"))
    try:
        got = {}
        for size in ("small", "xlarge"):
            use(size)
            # (the map's own: flight masters, docks, dungeons, caves, capitals, quests, NPCs, nodes, city places,
            # pins: DrawPois' buttons, the button the hit area)
            got[size] = {(w.kind, str(w.name)): (w._w, w._h) for w in _shown(lua, lambda w: w.kind is not None
                                                                              and w.kind != 16 and w.icon)}
        assert len(got["xlarge"]) >= 2 and set(got["small"]) == set(got["xlarge"])
        for k, (w, h) in got["small"].items():
            assert got["xlarge"][k] == (pytest.approx(w * 2), pytest.approx(h * 2)), k
        (b,) = _shown(lua, lambda w: w.pin is not None and w.pin.name == "Big")
        ppu = 1440 / 768
        assert b._w * ppu == pytest.approx(32)  # (G.ICON_PX twice: the 32 px file, pixel for pixel)
        assert b.icon._filter in (None, "LINEAR")
        # (each Extra large size picks the file drawn at it, round or square, and the ring drawn at it)
        for px in (26, 32, 36, 40, 44):
            f, r = G.ScaledIconFile(r"Interface\Icons\INV_Misc_Book_09", px, True)
            assert str(f).endswith(f"inv_misc_book_09_{px}r.jpg") and r, px
            f, _ = G.ScaledIconFile(r"Interface\Icons\INV_Misc_Book_09", px, False)
            assert str(f).endswith(f"inv_misc_book_09_{px}.jpg"), px
            t = lua.eval("CreateFrame('Frame'):CreateTexture()")
            t.SetSize(t, G.PxUnits(b, px), G.PxUnits(b, px))
            lua.eval("function(t) t.GetWidth = function(s) return s._w end end")(t)
            assert str(G.RingTexture(t, b)).endswith(f"IconRing{px}"), px
        # the stop made from it: its marker and its stairs badge grown, and the "you" pin's class icon
        b._scripts.OnDoubleClick(b)
        sizes = {}
        for size in ("medium", "xlarge"):
            use(size)
            (s,) = _shown(lua, lambda w: w.pendingIndex == 1)
            sizes[size] = (s._w * ppu, s.floorBadge._w)
            assert s.icon._filter in (None, "LINEAR")
        assert sizes["medium"] == (pytest.approx(16), 12)
        assert sizes["xlarge"] == (pytest.approx(26), pytest.approx(12 * 1.6))  # (16 x 1.6 on a whole pixel: drawn)
        G.RemovePending(1)
    finally:
        P.Remove(pin)


def test_the_stops_markers_grow(sized):
    lua, ns, use = sized
    N = ns.Nav
    N.Clear()
    N.SetStops(lua.eval("{ { x = 2000, y = 250, cont = 0, name = 'There' } }"), False, "red")
    try:
        w = {}
        for size in ("medium", "large", "xlarge"):
            use(size)
            stops = _shown(lua, lambda b: b.stopIndex == 1)
            assert stops, size
            w[size] = stops[0]._w
        assert w["large"] == pytest.approx(w["medium"] * 1.2) and w["xlarge"] == pytest.approx(w["medium"] * 1.6)
    finally:
        N.Clear()


def test_the_players_arrow_grows(sized):
    lua, ns, use = sized
    G = ns.GPS
    arrow = lua.eval("AGPS_WIDGETS")
    use("medium")
    a = [w for w in arrow.values() if getattr(w, "agpsGrow", None) is not None]
    assert len(a) == 1
    base = a[0]._w
    use("xlarge")
    assert a[0]._w == pytest.approx(base * 1.6) and a[0].agpsGrow == pytest.approx(1.6)
    use("small")
    assert a[0]._w == pytest.approx(base)  # (never smaller than it was before Icon size)
    assert G.ARROW_DEFAULT.width == 32


def test_the_minimaps_icons_and_their_hover_grow(sized):
    lua, ns, use = sized
    G = ns.GPS
    lists = {}
    for size in ("medium", "xlarge"):
        use(size)
        lists[size] = [e[5] for e in G.MinimapIconList(2254, 293, 0, 2000).values()]
    assert lists["medium"] and len(lists["medium"]) == len(lists["xlarge"])
    for a, b in zip(lists["medium"], lists["xlarge"]):
        assert b == pytest.approx(a * 1.6)
    src = (ADDON / "GPSFrame.lua").read_text(encoding="utf-8")
    # (the hover's hit boxes are the drawn sizes: the stop's and party members' grown the same way)
    assert "over(mm.stop, G.MinimapIconSize(14))" in src
    assert "over(b, G.MinimapIconSize(G.MINIMAP_ICON_SIZE + 2))" in src


def test_extra_large_in_the_world_map_too(game):  # noqa: F811
    # (CLAUDE.md "Both maps, same features")
    lua, ns = game
    lua.execute(SETUP)
    G, P, st = ns.GPS, ns.Pins, ns.settings.gps
    keys = ("useWorldMap", "shown", "minimized", "iconSize")
    was = {k: st[k] for k in keys}
    lua.execute("AGPS_OLD_PSS_XLW = GetPhysicalScreenSize\nGetPhysicalScreenSize = function() return 2560, 1440 end")
    pin = P.Add(lua.eval("{ level = 0, x = 2254, y = 293, name = 'Wide', icon = 136777 }"))
    try:
        st.useWorldMap, st.shown, st.minimized, st.iconSize = True, True, None, "xlarge"
        G.ApplySettings()
        lua.globals().AzerothGPS_ToggleMap()
        assert G.WorldMapHosted()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        (b,) = _shown(lua, lambda w: w.pin is not None and w.pin.name == "Wide")
        assert b._w == pytest.approx(G.PxUnits(b, 32))
        assert b.icon._filter in (None, "LINEAR")
    finally:
        P.Remove(pin)
        lua.execute("GetPhysicalScreenSize = AGPS_OLD_PSS_XLW WorldMapFrame:Hide() ToggleWorldMap = nil")
        for k, v in was.items():
            st[k] = v
        G.ApplySettings()


def test_extra_large_is_kept_over_a_reload():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start

    lua, ns = start(saved="AzerothGPSDB = { settings = { gps = { iconSize = 'xlarge' } } }")
    assert ns.settings.gps.iconSize == "xlarge" and ns.GPS.PoiScale() == 2
