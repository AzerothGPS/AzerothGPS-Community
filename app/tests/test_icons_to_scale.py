"""The map's game icons drawn at each size they're shown at (asked 2026-11-16: "for all map icons and borders ... render
the icons to scale like we did for icon rings to look better"; iconscale.py, GPSFrame's G.ScaledIcon)."""
import re
from pathlib import Path

import pytest
from PIL import Image

from azerothgps import iconscale
from azerothgps.coast import RING_SIZES

ADDON = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS"
ICONS = ADDON / "Media" / "Icons"


def _table():
    text = (ADDON / "Data" / "IconSizes.lua").read_text(encoding="utf-8")
    return dict(re.findall(r'\["([^"]+)"\] = "([jt]\d+)"', text))


def test_the_generator_draws_every_size_under_the_arts_own():
    # a 64 px opaque icon: each ring size under 64, square and round (its border cropped), as JPG; one with an alpha
    # (a quest mark): TGA, square only; the 64 px one left to the game's own file
    opaque = {"key": "icons/x", "fid": 1, "image": Image.new("RGBA", (64, 64), (200, 30, 30, 255)), "opaque": True,
              "round": True}
    files = iconscale.files_for(opaque)
    want = [n for n in RING_SIZES if n < 64]
    assert sorted(files) == sorted([f"icons_x_{n}.jpg" for n in want] + [f"icons_x_{n}r.jpg" for n in want])
    for n in want:
        assert Image.open(__import__("io").BytesIO(files[f"icons_x_{n}r.jpg"])).size == (n, n)
    clear = {"key": "gossipframe/q", "fid": 2, "image": Image.new("RGBA", (32, 32), (0, 0, 0, 0)), "opaque": False,
             "round": False}
    assert sorted(iconscale.files_for(clear)) == sorted(f"gossipframe_q_{n}.tga" for n in RING_SIZES if n < 32)
    assert '["icons/x"] = "j48"' in iconscale.lua_text([opaque]) and "[1] = \"icons/x\"" in iconscale.lua_text([opaque])


def test_every_icon_listed_is_shipped_at_each_of_its_sizes():
    table = _table()
    assert len(table) > 100 and "icons/inv_misc_book_09" in table and "atlas:classicon-shaman" in table
    shipped = {p.name for p in ICONS.iterdir()}
    for key, kind in table.items():
        base = iconscale.base_name(key)
        for n in (n for n in RING_SIZES if n <= int(kind[1:])):
            if kind[0] == "j":
                assert {f"{base}_{n}.jpg", f"{base}_{n}r.jpg"} <= shipped, (key, n)
            else:
                assert f"{base}_{n}.tga" in shipped, (key, n)
    # (nothing else there: the generator removes what it no longer makes)
    bases = {iconscale.base_name(k) for k in table}
    assert all(name.rsplit("_", 1)[0] in bases for name in shipped)


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start

    return start()


def _icon(lua, ns, icon, px):
    """A texture showing `icon` (ns.SetIcon) `px` screen pixels across on a frame, rounded or not by G.RoundIcon."""
    G = ns.GPS
    f = lua.eval("CreateFrame('Frame', nil, UIParent)")
    t = f.CreateTexture(f)
    ns.SetIcon(t, icon)
    u = G.PxUnits(f, px)
    t.SetSize(t, u, u)
    _sized(lua, t)
    return f, t


def _sized(lua, t):
    # (the stand-in's GetWidth is the same for every widget: the size set instead)
    lua.eval("function(t) t.GetWidth = function(s) return s._w end end")(t)


def test_an_icon_on_the_map_at_16_px_uses_the_16_px_file(game):
    lua, ns = game
    G = ns.GPS
    path = "Interface\\AddOns\\AzerothGPS\\Media\\Icons\\"
    st = ns.settings.gps
    was = st.roundIcons
    try:
        st.roundIcons = True
        f, t = _icon(lua, ns, "Interface\\Icons\\INV_Misc_Book_09", 16)
        assert G.RoundIcon(f, t, "Interface\\Icons\\INV_Misc_Book_09")
        assert t.scaledFile == path + "icons_inv_misc_book_09_16r.jpg" and t.scaledRound
        assert str(t._tex) == t.scaledFile
        st.roundIcons = False  # (square: the uncropped file)
        f, t = _icon(lua, ns, "Interface\\Icons\\INV_Misc_Book_09", 16.4)
        G.RoundIcon(f, t, "Interface\\Icons\\INV_Misc_Book_09")
        assert t.scaledFile == path + "icons_inv_misc_book_09_16.jpg" and not t.scaledRound
        # an item's icon by its file id (a herb's: GetItemIconByID), at 23.6 px: the 24 px file
        f, t = _icon(lua, ns, 133939, 23.6)
        G.RoundIcon(f, t, 133939)
        assert t.scaledFile == path + "icons_inv_misc_flower_02_24.jpg"
        # bigger than the largest drawn: the game's own file again
        f, t = _icon(lua, ns, "Interface\\Icons\\INV_Misc_Book_09", 70)
        G.RoundIcon(f, t, "Interface\\Icons\\INV_Misc_Book_09")
        assert t.scaledFile is None and str(t._tex) == "Interface\\Icons\\INV_Misc_Book_09"
    finally:
        st.roundIcons = was


def test_an_icon_not_drawn_to_scale_is_the_games_own(game):
    lua, ns = game
    G = ns.GPS
    for icon in ("Interface\\Icons\\INV_Some_Learned_Herb", 999999999, "atlas:Dungeon"):
        f, t = _icon(lua, ns, icon, 16)
        G.RoundIcon(f, t, icon)
        assert t.scaledFile is None and not t.scaledRound, icon
    # a file the client doesn't know yet (added since the last login): the game's file, not a green square
    lua.execute("AGPS_GTFID = nil")
    f, t = _icon(lua, ns, "Interface\\Icons\\INV_Misc_Book_09", 20)
    lua.eval("function(t) t.GetTextureFileID = function() return nil end end")(t)
    G.RoundIcon(f, t, "Interface\\Icons\\INV_Misc_Book_09")
    assert t.scaledFile is None and str(t._tex) == "Interface\\Icons\\INV_Misc_Book_09"
    G.scaledMissing = lua.eval("{}")


def test_the_class_icons_are_drawn_to_scale_too(game):
    lua, ns = game
    G = ns.GPS
    lua.execute("AGPS_OLD_CT = C_Texture C_Texture = { GetAtlasInfo = function() return {} end }")
    try:
        f = lua.eval("CreateFrame('Frame', nil, UIParent)")
        t = f.CreateTexture(f)
        assert G.ClassIcon(t, "SHAMAN")
        u = G.PxUnits(f, 18)
        t.SetSize(t, u, u)
        _sized(lua, t)
        assert G.ScaledIcon(f, t, False)
        assert t.scaledFile == "Interface\\AddOns\\AzerothGPS\\Media\\Icons\\atlas_classicon_shaman_18"
    finally:
        lua.execute("C_Texture = AGPS_OLD_CT")
