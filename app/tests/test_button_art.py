"""The map's round buttons drawn sharp (asked 2026-11-18, for 1.3.9: "use right scaled images for that and all the menu
buttons"): the map menu button, Search, the quick buttons, their groups' and Quick Find's flyouts, the minimap square's
Resume button, their glows and the controller's focus ring, each on whole screen pixels its art is drawn at (coast.py's
FRAME_SIZES and discs, iconscale.py's icons; GPSFrame's G.RoundArt, G.FitRoundButton)."""
import re
from pathlib import Path

import numpy as np
import pytest

from azerothgps import coast, iconscale
from azerothgps.coast import RING_SIZES
from test_map_redraw import game  # noqa: F401
from test_world_map_host import SETUP

ADDON = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS"
ICONS = ADDON / "Media" / "Icons"
PREFIX = "Interface\\AddOns\\AzerothGPS\\"
# (screens and UI scales: pixels per unit from 0.6 (720p, UI scale 0.64) to 3.2 (4K at 1.15), and the world map's own)
SCREENS = ((1280, 720), (1366, 768), (1920, 1080), (2560, 1440), (3440, 1440), (3840, 2160))
UI_SCALES = (0.64, 0.71, 0.8, 0.9, 1.0, 1.15)


def _local(path):
    """The file on disk for an addon texture path (the client takes .tga or .jpg left off), or None for another's."""
    path = str(path)
    if not path.startswith(PREFIX):
        return None
    p = ADDON / path[len(PREFIX):].replace("\\", "/")
    for f in (p, p.with_name(p.name + ".tga")):
        if f.is_file():
            return f
    return p


def _size(f):
    if f.suffix == ".jpg":
        from PIL import Image

        return Image.open(f).size
    data = f.read_bytes()
    return tuple(int.from_bytes(data[i:i + 2], "little") for i in (12, 14))


def _table():
    text = (ADDON / "Data" / "IconSizes.lua").read_text(encoding="utf-8")
    return dict(re.findall(r'\["([^"]+)"\] = "([jt]\d+)"', text))


def test_the_sizes_drawn_are_the_addons_and_every_file_is_shipped():
    gps = (ADDON / "GPSFrame.lua").read_text(encoding="utf-8")
    m = re.search(r"G\.BUTTON_FRAME_SIZES = \{([\d,\s]+)\}", gps)
    assert tuple(int(n) for n in m.group(1).replace("\n", " ").split(",")) == coast.FRAME_SIZES
    # (all even: a button's icon on whole pixels in its middle)
    assert all(n % 2 == 0 for n in coast.FRAME_SIZES + tuple(RING_SIZES))
    for n in coast.FRAME_SIZES:
        f = coast.frame_file(n)
        assert f.is_file() and _size(f) == (n, n), n
    for n in coast.DISC_SIZES:
        f = coast.disc_file(n)
        assert f.is_file() and _size(f) == (n, n), n
    # (nothing else there; the shipped files are what the generator makes, byte for byte)
    want = coast.button_files()
    assert sorted(p.name for p in coast.BUTTON_DIR.iterdir()) == sorted(p.name for p in want)
    for p, data in want.items():
        assert p.read_bytes() == data, p.name


def test_the_frames_are_the_map_menus_art_and_the_discs_white_and_round():
    # (our own art: MapMenu.tga resized; the discs made from numbers, white, clear outside the circle)
    big = coast.read_tga_rgba(coast.MAP_MENU_FILE)
    assert big.shape == (64, 64, 4) and (coast.frame(64) == big).all()
    for n in coast.DISC_SIZES:
        d = coast.disc(n)
        assert (d[..., :3] == 255).all()
        assert d[n // 2, n // 2, 3] == 255 and d[0, 0, 3] == 0
    small = coast.frame(16)
    assert small.shape == (16, 16, 4) and small[8, 8, 3] == 255 and small[0, 0, 3] < 40


def test_every_button_icon_is_drawn_to_scale():
    # the quick buttons', the map styles', the groups', Quick Find's, the Resume button's and Search's icons are all in
    # Data/IconSizes.lua (drawn at every icon size up to 48; 64 is the game's own file)
    table = _table()
    gps = (ADDON / "GPSFrame.lua").read_text(encoding="utf-8")
    start = gps.index("  local STYLES = {")
    end = gps.index("  G.GROUP_IDLE = 8")
    paths = set(re.findall(r'"Interface\\\\Icons\\\\([A-Za-z0-9_]+)"', gps[start:end]))
    pins = (ADDON / "Pins.lua").read_text(encoding="utf-8")
    npc = pins[pins.index("P.NPC_ICONS = {"):pins.index("function P.NpcIcon")]
    paths |= set(re.findall(r'"Interface\\\\Icons\\\\([A-Za-z0-9_]+)"', npc))
    paths |= {"Spell_Nature_TimeStop", "INV_Pick_02", "INV_Misc_Bone_HumanSkull_01", "Ability_Tracking"}
    assert len(paths) > 30
    for name in sorted(paths):
        key = f"icons/{name.lower()}"
        assert table.get(key) == "j48", key
    assert table["atlas:common-search-magnifyingglass"] == "t22"  # (Search's: its own art is 24 px)


def _ppu(lua, w, h, k):
    lua.execute(f"GetPhysicalScreenSize = function() return {w}, {h} end")
    return h / 768 * k


def _set_scale(lua, buttons, k):
    f = lua.eval("function(b, k) b.GetEffectiveScale = function() return k end end")
    for b in buttons:
        f(b, k)


def _check_button(lua, ns, b, ppu, label):
    """`b`'s art on whole pixels, each texture a file drawn at exactly its size (or the game's own at its own size)."""
    G = ns.GPS
    a = b.agpsArt
    F = a.F
    assert F in coast.FRAME_SIZES, label
    assert b._w * ppu == pytest.approx(F, abs=1e-6), label
    for t in a.frames.values():
        f = _local(t._tex)
        assert f and f.is_file() and _size(f) == (F, F), (label, t._tex)
        assert t._filter in (None, "LINEAR"), label
    if a.share is None:
        return
    icon, I = a.icon, a.I
    assert I in RING_SIZES and I <= F - 2 and (F - I) % 2 == 0, (label, F, I)
    assert icon._w * ppu == pytest.approx(I, abs=1e-6), label
    assert icon._filter in (None, "LINEAR"), label
    if a.mask is not None:
        f = _local(a.mask._tex)
        assert f and _size(f) == (I, I), (label, a.mask._tex)
        assert a.mask._filter in (None, "LINEAR"), label
    key = G.ScaledIconKey(icon.agpsSrc)
    if I == 64 or key is None:
        # (the game's own file: 64 px, as drawn at 64; or one not drawn to scale, a custom search's)
        assert icon.scaledFile is None, label
        return
    largest = int(_table()[key][1:])
    if I > largest:
        assert icon.scaledFile is None, label  # (bigger than its own art: the game's file, never shrunk)
        return
    f = _local(icon.scaledFile)
    assert f and f.is_file() and _size(f) == (I, I), (label, icon.scaledFile)
    assert str(icon._tex) == str(icon.scaledFile), label


def _buttons(lua, ns):
    G = ns.GPS
    return list(G.roundButtons.values())


def test_each_round_button_uses_art_drawn_at_its_exact_size(game):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    old = lua.eval("GetPhysicalScreenSize")
    buttons = _buttons(lua, ns)
    ids = lua.eval("""function()
      local m = {}
      for _, t in ipairs(AGPS_NS.GPS.QUICK) do if t.button then m[t.button] = t.id end end
      return m
    end""")()
    names = [str(ids[b] or "") for b in buttons]
    same = lua.eval("rawequal")
    assert len(buttons) > 40 and "pauseRoute" in names and "questRoute" in names
    assert any(same(b, G.mapButton) for b in buttons) and any(same(b, G.searchButton) for b in buttons)
    try:
        seen = set()
        for w, h in SCREENS:
            for k in UI_SCALES:
                ppu = _ppu(lua, w, h, k)
                _set_scale(lua, buttons, k)
                G.FitRoundButtons()
                for i, b in enumerate(buttons):
                    _check_button(lua, ns, b, ppu, f"{names[i] or i} at {w}x{h} x{k}")
                    seen.add((b.agpsArt.F, b.agpsArt.I))
        assert len(seen) > 20  # (many sizes taken: 720p to 4K)
        # (a quick button at 1080p and the UI scale at 1, 1.41 px a unit: 36 px, its icon 22; 4K at 1.15: 84 -> 80, 48)
        ppu = _ppu(lua, 1920, 1080, 1)
        _set_scale(lua, buttons, 1)
        G.FitRoundButtons()
        qr = next(b for i, b in enumerate(buttons) if names[i] == "questRoute")
        assert (qr.agpsArt.F, qr.agpsArt.I) == (36, 22)
        assert str(qr.agpsArt.icon._tex) == PREFIX + "Media\\Icons\\icons_ability_rogue_sprint_22.jpg"
        assert str(qr.agpsArt.mask._tex) == PREFIX + "Media\\Buttons\\Disc22"
        assert str(qr.agpsArt.frames[1]._tex) == PREFIX + "Media\\Buttons\\Frame36"
    finally:
        lua.globals().GetPhysicalScreenSize = old
        _set_scale(lua, buttons, 1)
        G.FitRoundButtons()


def test_a_buttons_icon_set_again_keeps_its_size(game):  # noqa: F811
    # (a group's icon follows its active member, a custom search's its row: G.SetButtonIcon draws it at the size)
    lua, ns = game
    G = ns.GPS
    G.RefreshQuick()
    grp = G.groupOf.styles
    a = grp.button.agpsArt
    assert grp.iconTex.scaledFile is not None and f"_{a.I}.jpg" in str(grp.iconTex.scaledFile)
    G.SetButtonIcon(grp.iconTex, "Interface\\Icons\\INV_Misc_Map02")
    assert str(grp.iconTex._tex) == PREFIX + f"Media\\Icons\\icons_inv_misc_map02_{a.I}.jpg"


def test_glows_and_the_focus_ring_are_drawn_at_their_size(game):  # noqa: F811
    lua, ns = game
    G = ns.GPS
    b = G.mapButton
    g = G.MakeGlow(b)
    try:
        a = b.agpsArt
        n = G.NearestSize(G.BUTTON_FRAME_SIZES, a.F * G.GLOW_SHARE)
        assert g.agpsArtPx == n and _size(_local(g._tex)) == (n, n)
        assert g._w * a.ppu == pytest.approx(n)
        assert g._filter in (None, "LINEAR")
    finally:
        g.Hide(g)
    P = ns.Pad
    P.SetFocus(G.searchButton)
    try:
        ring = P.ring
        a = G.searchButton.agpsArt
        n = G.NearestSize(G.BUTTON_FRAME_SIZES, a.F * P.RING_SHARE)
        assert ring.tex.agpsArtPx == n and _size(_local(ring.tex._tex)) == (n, n)
        assert ring._w * a.ppu == pytest.approx(n)
    finally:
        P.SetFocus(None)


def test_a_file_the_client_doesnt_know_yet_falls_back_to_the_old_art(game):  # noqa: F811
    # (new files need a full relog: till then GetTextureFileID is nil for them, and the button keeps the old art: the
    # 64 px frame and the game's round mask, not a green square)
    lua, ns = game
    G = ns.GPS
    b = G.groupOf.gather.button
    lua.execute("AGPS_GTF = AGPS_NS.GPS.TextureLoaded AGPS_NS.GPS.TextureLoaded = function() return false end")
    G.artKnown = lua.eval("{}")
    try:
        G.FitRoundButton(b)
        a = b.agpsArt
        assert str(a.frames[1]._tex) == G.MAP_MENU_ART and str(a.frames[2]._tex) == G.MAP_MENU_ART
        assert str(a.mask._tex) == G.ROUND_MASK
    finally:
        lua.execute("AGPS_NS.GPS.TextureLoaded = AGPS_GTF")
        G.artKnown = lua.eval("{}")
        G.FitRoundButton(b)
    assert "Buttons\\Frame" in str(b.agpsArt.frames[1]._tex) and "Buttons\\Disc" in str(b.agpsArt.mask._tex)


def test_the_resume_button_gets_exact_art_from_the_smallest_logo_to_the_largest(game):  # noqa: F811
    # (its size follows the logo's, MINIMAP_RESUME_SHARE of it, any value: snapped to the nearest size drawn)
    lua, ns = game
    G, N, st = ns.GPS, ns.Nav, ns.settings.gps
    r = G.MakeMinimapResume()
    old_btn, old_paused = G.mmButton, N.paused
    old = lua.eval("GetPhysicalScreenSize")
    btn = lua.eval("CreateFrame('Button', nil, UIParent)")
    on = lua.eval("CreateFrame('Frame', nil, UIParent)")
    logos = [16, 20, 24, 28, 32, 36, 40, 44, 48, 56, 64, 72, 80, 96, 112, 128, 144, 160, 176, 192, 208, 224, 256, 288]
    try:
        G.mmButton = btn
        N.paused = "manual"
        st.replaceMinimapResume = True
        for w, h in SCREENS:
            for k in UI_SCALES:
                ppu = _ppu(lua, w, h, k)
                _set_scale(lua, [r, btn], k)
                for px in (logos[0], logos[-1]) + tuple(logos):
                    btn.logoSize = px / ppu
                    assert G.PlaceMinimapResume(on)
                    _check_button(lua, ns, r, ppu, f"Resume, logo {px} px at {w}x{h} x{k}")
                    assert r._w < btn.logoSize + 1e-9 or px <= 24  # (smaller than the logo: but at the least size)
                    assert "timestop" in str(r.icon.agpsSrc).lower()
                    g = r.glow
                    assert _size(_local(g._tex)) == (g.agpsArtPx, g.agpsArtPx)
        # (the smallest logo at 1080p: 16 px -> 12 px (the least drawn), its icon 10; the largest: 288 -> 96, 64)
        ppu = _ppu(lua, 1920, 1080, 1)
        _set_scale(lua, [r, btn], 1)
        btn.logoSize = 16 / ppu
        G.PlaceMinimapResume(on)
        assert (r.agpsArt.F, r.agpsArt.I) == (12, 10)
        btn.logoSize = 288 / ppu
        G.PlaceMinimapResume(on)
        assert (r.agpsArt.F, r.agpsArt.I) == (96, 64) and r.icon.scaledFile is None
    finally:
        lua.globals().GetPhysicalScreenSize = old
        G.mmButton, N.paused = old_btn, old_paused
        r.Hide(r)


def test_no_filter_above_linear_on_any_button_texture():
    # (the client crashes on any filter above LINEAR: TRILINEAR did; the stand-in fails the same way, and none is
    # passed by the buttons' code)
    gps = (ADDON / "GPSFrame.lua").read_text(encoding="utf-8")
    start = gps.index("-- The map's round buttons drawn sharp")
    block = gps[start:gps.index("G.ROUND_RING_GOLD = ")]
    assert "TRILINEAR" not in block and "ANISOTROPIC" not in block
    code = [line.split("--", 1)[0] for line in gps.splitlines() + (ADDON / "Pad.lua").read_text(encoding="utf-8").splitlines()]
    assert not any(re.search(r'"(TRILINEAR|ANISOTROPIC)"', line) for line in code)


def test_the_buttons_are_exact_in_the_world_map_too(game):  # noqa: F811
    # (CLAUDE.md "Both maps, same features": the map in the game's world map takes that window's scale; the buttons are
    # fitted again to it, G.FitRoundButtonsIfScaled from the quick buttons' watch)
    lua, ns = game
    lua.execute(SETUP)
    G, st = ns.GPS, ns.settings.gps
    keys = ("useWorldMap", "shown", "minimized")
    was = {k: st[k] for k in keys}
    old = lua.eval("GetPhysicalScreenSize")
    buttons = _buttons(lua, ns)
    try:
        st.useWorldMap, st.shown, st.minimized = True, True, None
        G.ApplySettings()
        lua.globals().AzerothGPS_ToggleMap()
        assert G.WorldMapHosted()
        ppu = _ppu(lua, 2560, 1440, 0.83)
        _set_scale(lua, buttons, 0.83)
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()  # (the watch sees the new scale)
        assert G.buttonsPpu == pytest.approx(ppu)
        for b in buttons:
            _check_button(lua, ns, b, ppu, "world map")
    finally:
        lua.globals().GetPhysicalScreenSize = old
        _set_scale(lua, buttons, 1)
        lua.execute("WorldMapFrame:Hide() ToggleWorldMap = nil")
        for k, v in was.items():
            st[k] = v
        G.ApplySettings()
        G.FitRoundButtons()


def test_the_generator_draws_the_search_magnifier_from_its_raw_atlas():
    # (its atlas is a BLP of plain BGRA pixels, which Pillow doesn't read: iconscale._blp_raw)
    import struct

    w = h = 2
    px = bytes([10, 20, 30, 255] * 4)  # (B, G, R, A)
    head = b"BLP2" + struct.pack("<I", 1) + bytes([3, 8, 8, 0]) + struct.pack("<II", w, h)
    offs = struct.pack("<16I", 1172, *([0] * 15)) + struct.pack("<16I", len(px), *([0] * 15))
    data = head + offs + bytes(1024) + px
    img = iconscale._blp_raw(data)
    assert img.size == (2, 2) and img.getpixel((0, 0)) == (30, 20, 10, 255)
    assert iconscale._blp_raw(b"BLP2" + bytes(200)) is None
    assert "common-search-magnifyingglass" in iconscale.ATLASES
    assert np.asarray(img).shape == (2, 2, 4)
