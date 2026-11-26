"""What's New in v1.4.0 (WhatsNew.lua, item 34): a picture of a spell jump, a line, 1.4.0's new options live, Reset
Defaults (lit only while one of THESE differs from its default; resets only these) and Close. A player updating sees
the popup once; a first install gets the setup with it as the last page instead (Kooki3z), never both; Options >
Help's What's New and /agps whatsnew open it again; it works with the map in the game's world map too."""

import pytest

from test_setup import _close, _relog, _start

# (a player who's had the addon a while: the setup seen, no What's New stamp)
UPDATING = 'AzerothGPSDB = { setup = { shown = 1, done = "1.3.14" }, settings = { gps = { size = 400 } }, chars = {} }'


def _login(lua, ns):
    ns.WhatsNew.asked = None
    ns.Setup.asked = None
    lua.execute("AGPS_AFTER = {}")
    ns.WhatsNew.OnEnteringWorld()
    ns.Setup.OnEnteringWorld()
    for fn in list(lua.eval("AGPS_AFTER").values()):
        fn()


def test_a_player_updating_sees_it_once():
    lua, ns = _start(saved=UPDATING)
    W, S = ns.WhatsNew, ns.Setup
    assert S.Due() is False and W.Due() is True
    _login(lua, ns)
    f = W.window
    assert W.Shown() and str(f.title._text if hasattr(f, "title") and f.title else "") in ("", "What's new in v1.4.0")
    assert ns.db.whatsNewSeen == "1.4.0" and S.Shown() is False
    assert str(f.close._text) == "Close" and str(f.content.reset._text) == "Reset Defaults"
    # (the picture: its own pixels of the canvas, never filtered above LINEAR)
    img = f.content.image
    assert "WhatsNew" in str(img._tex) and str(img._filter) == "LINEAR"
    _close(f)
    lua, ns = _relog(lua)
    _login(lua, ns)
    assert not ns.WhatsNew.Shown() and ns.WhatsNew.Due() is False  # (not again)


def test_a_first_install_gets_the_setup_with_what_s_new_as_its_last_page_never_both():
    lua, ns = _start()
    W, S = ns.WhatsNew, ns.Setup
    assert S.Due() is True and W.Due() is False
    _login(lua, ns)
    assert S.Shown() and not W.Shown()
    assert ns.db.whatsNewSeen == "1.4.0"  # (set as the setup opens)
    click = lua.globals().AGPS_CLICK
    f = S.window
    click(f.next)
    click(f.next)
    assert str(f.heading._text) == "What's new in v1.4.0" and f.whatsNew._shown
    click(f.next)  # Finish
    lua, ns = _relog(lua)
    _login(lua, ns)
    assert not ns.WhatsNew.Shown() and not ns.Setup.Shown()


def _controls(c):
    return {str(ctl.key): ctl for ctl in c.controls.values()}


def test_the_options_are_live_and_reset_defaults_lights_and_resets_only_these():
    lua, ns = _start(saved=UPDATING)
    W = ns.WhatsNew
    st = ns.settings.gps
    W.Open()
    c = W.window.content
    ctl = _controls(c)
    # (the grid system's Cities and World: gone, item 74: always on)
    assert set(ctl) == {"useClassSpells", "expertJumper", "safeDropYd"}
    assert str(c.heading._text) == "Jumping"
    assert c.reset._enabled is False  # (everything at its default: not lit)
    click = lua.globals().AGPS_CLICK
    cb = ctl["expertJumper"]
    cb._checked = True
    click(cb)
    assert st.expertJumper is True  # (applied at once, as Options does)
    assert c.reset._enabled is True
    s = ctl["safeDropYd"].slider
    s._scripts.OnValueChanged(s, 55)
    assert st.safeDropYd == 55
    st.size = 333  # (another setting: never reset here)
    click(c.reset)
    assert not st.expertJumper and st.safeDropYd == 39 and st.size == 333
    assert c.reset._enabled is False
    # (Expert jumper gray without class spells, as in Options)
    ctl["useClassSpells"]._checked = False
    click(ctl["useClassSpells"])
    assert st.useClassSpells is False and ctl["expertJumper"].agpsOn is False
    click(c.reset)
    assert st.useClassSpells is True and ctl["expertJumper"].agpsOn is True


def test_the_setup_s_skip_puts_back_what_its_what_s_new_page_changed():
    lua, ns = _start()
    S, W = ns.Setup, ns.WhatsNew
    st = ns.settings.gps
    S.Open()
    click = lua.globals().AGPS_CLICK
    click(S.window.next)
    click(S.window.next)
    cb = _controls(S.window.whatsNew)["useClassSpells"]
    cb._checked = False
    click(cb)
    assert st.useClassSpells is False
    click(S.window.skip)
    assert st.useClassSpells is not False


def test_options_help_and_the_command_open_it_again_and_it_works_in_world_map_mode():
    lua, ns = _start(saved=UPDATING)
    W, O = ns.WhatsNew, ns.Options
    ns.db.whatsNewSeen = "1.4.0"
    O.Show()
    O.ShowPage("Help")
    click = lua.globals().AGPS_CLICK
    click(O.whatsNewButton)
    assert W.Shown()
    _close(W.window)
    lua.globals().SlashCmdList.AZEROTHGPS("whatsnew")
    assert W.Shown()
    _close(W.window)
    # (the map in the game's world map: the popup over it, its options still live)
    st = ns.settings.gps
    st.useWorldMap = True
    ns.GPS.ApplySettings()
    W.Open()
    assert W.Shown() and lua.eval("AGPS_NS.popups[AGPS_NS.WhatsNew.window] ~= nil")  # (lifted over the map as any popup)
    cb = _controls(W.window.content)["useClassSpells"]
    cb._checked = False
    click(cb)
    assert st.useClassSpells is False
    click(W.window.content.reset)
    assert st.useClassSpells is True


def test_never_in_combat():
    lua, ns = _start(saved=UPDATING)
    ns.inCombat = True
    try:
        assert ns.WhatsNew.Open() is False and not ns.WhatsNew.Shown()
        assert ns.WhatsNew.MaybeShow() is False and ns.WhatsNew.waiting
    finally:
        ns.inCombat = None


LOCALES = ["enUS", "deDE", "esES", "esMX", "frFR", "itIT", "koKR", "ptBR", "ruRU", "zhCN", "zhTW"]


@pytest.mark.parametrize("locale", LOCALES)
def test_the_layout_picture_centered_settings_under_it_and_the_window_fits(locale):
    # (item 37, Kooki3z's screenshot on 3c85cf49: the picture centered under the line in a gold glow, the settings one
    # block under it, nothing over the line, Reset Defaults and Close bottom right under it all; the setup's page too)
    from azerothgps.gameharness import start
    lua, ns = start(locale=locale, saved=UPDATING)
    W = ns.WhatsNew
    W.Open()
    f = W.window
    c = f.content
    at, bt = c.imageAt, c.blockAt
    assert at.x == 0 and bt.x == 0  # (both centered)
    assert -at.y >= 30  # (under the line: nothing over its second line)
    assert -bt.y >= -at.y + at.h  # (the settings under the picture, not beside it)
    assert len(c.glow) >= 2 and str(c.image._tex).endswith("spellJump")  # (the gold edge and the glow round it)
    # (the content ends above the buttons: the window's height holds the top, the content and the bottom row)
    assert f._h >= -f.top + 8 + c.height + 16 + 22 + 14 - 0.5
    assert str(f.close._pt[1]) == "BOTTOMRIGHT" and str(c.reset._pt[1]) == "RIGHT"
    # (the setup's last page: its window grown for it, Reset Defaults under the settings)
    S = ns.Setup
    S.Open()
    S.ShowPage(3)
    sw = S.window
    assert sw.whatsNew._shown and sw._h >= -sw.top + 50 + sw.whatsNew.height + 30 + 16 + 22 + 14 - 0.5
    S.ShowPage(1)
    assert sw._h == S.H


def test_the_setup_s_last_page_shows_only_its_own_widgets_gold_and_done():
    """Item 64 (Kooki3z on 1173b42f): step 3 of 3 had step 2's cards and the focus box over it, the line cut off, a pink
    picture edge, Reset Defaults in the middle and "Next". Now: only its own widgets, the line given its lines, the gold
    edge, Reset Defaults at the bottom right over Back and Next, "Done"; the same after going Back and on again."""
    lua, ns = _start()
    S, W = ns.Setup, ns.WhatsNew
    S.Open()
    click = lua.globals().AGPS_CLICK
    f = S.window
    click(f.next)
    click(f.next)
    for again in (False, True):
        assert S.at == 3 and str(f.next._text) == "Done"
        assert not any(f.cards[i]._shown for i in range(1, len(f.cards) + 1))
        c = f.whatsNew
        assert c._shown and not f.focus._shown or f.focus._parent != f.cards[1]
        edge = W.GLOW[1]
        assert (edge[2], edge[3], edge[4]) == (1, 0.82, 0.25)  # (gold: r, g, b)
        assert c.imageAt["y"] <= -(28 + 10)  # (the line's lines kept clear of the picture)
        p = c.reset._pts.BOTTOMRIGHT
        assert p[3] == "BOTTOMRIGHT" and p[4] < 0 and p[5] > 22  # (bottom right, over Back and Next)
        if not again:
            click(f.back)
            assert S.at == 2 and not c._shown
            click(f.next)
    S.Close(False)


def test_the_picture_is_kooki3z_s_shot_power_of_two_and_shown_at_its_own_pixels():
    # (item 94: his shot of a spell jump with its tooltip; at 1:1 in the popup and on the setup's page, so the tooltip's
    # text stays readable; a power-of-two TGA its pixels in the top left of)
    from pathlib import Path
    from PIL import Image
    from azerothgps.gameharness import start
    lua, ns = start(saved=UPDATING)
    W = ns.WhatsNew
    tga = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS" / "Media" / "WhatsNew" / "spellJump.tga"
    with Image.open(tga) as im:
        assert im.size == (W.IMAGE_CANVAS[1], W.IMAGE_CANVAS[2]) and im.mode == "RGBA"
        assert all(n & (n - 1) == 0 for n in im.size)
        assert W.IMAGE_PX[1] <= im.size[0] and W.IMAGE_PX[2] <= im.size[1]
        assert im.getpixel((W.IMAGE_PX[1] - 1, W.IMAGE_PX[2] - 1))[3] == 255  # (the picture's last pixel)
        assert im.getpixel((0, W.IMAGE_PX[2]))[3] == 0  # (and nothing under it)
    W.Open()
    assert W.window.content.imageAt.w == W.IMAGE_PX[1]
    S = ns.Setup
    S.Open()
    S.ShowPage(3)
    assert S.window.whatsNew.imageAt.w == W.IMAGE_PX[1]
