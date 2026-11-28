"""The UI's text style on our HUD text (Kooki3z for 1.4.2: "can we by default for directions use the UI's themed text
style?"; UIFont.lua): with DaylightUI or EllesmereUI loaded, the directions (the arrow's panel, the map's route panel),
the map's info line and the height strip's label take that UI's font face and its outline or shadow, our sizes and
colors kept; the player's "AzerothGPS default" wins; a font that doesn't load falls back to ours; a UI font changed while
playing is followed; without a UI nothing changes. Each UI is a stand-in for what it has (read from its files: DaylightUI
2.4.1's API.lua, EllesmereUI's EllesmereUI_Fonts.lua)."""

import pytest

DUI_FONT = "Interface\\AddOns\\DaylightUI\\Media\\fonts\\Expressway.ttf"
DUI_FONT2 = "Interface\\AddOns\\DaylightUI\\Media\\fonts\\Lato-Bold.ttf"
EUI_FONT = "Interface\\AddOns\\EllesmereUI\\media\\fonts\\Expressway.TTF"

# The loaded addons, a real hooksecurefunc (the mock's does nothing) and C_Timer.After at once.
LOADED = """
  AGPS_LOADED = {}
  AGPS_OLD = { C_AddOns.IsAddOnLoaded, IsAddOnLoaded, hooksecurefunc, C_Timer.After }
  C_AddOns.IsAddOnLoaded = function(name) return AGPS_LOADED[name] == true end
  IsAddOnLoaded = C_AddOns.IsAddOnLoaded
  hooksecurefunc = function(t, name, post)
    local was = t[name]
    t[name] = function(...)
      local r = { was(...) }
      post(...)
      return unpack(r)
    end
  end
  C_Timer.After = function(_, fn) fn() end
"""
# DaylightUI 2.4.1: DaylightUI.API.Font() (the player's font, DUI.Style.FONT), GetSetting("general", "textOutline" /
# "textShadow"), On("StyleChanged", fn, owner).
DAYLIGHT = """
  AGPS_LOADED.DaylightUI = true
  AGPS_DUI = { font = %r, general = { textOutline = "THICKOUTLINE", textShadow = true }, on = {} }
  DaylightUI = { API = {
    Font = function() return AGPS_DUI.font end,
    GetSetting = function(scope, path) if scope == "general" then return AGPS_DUI.general[path] end end,
    On = function(event, fn, owner) AGPS_DUI.on[event] = fn; AGPS_DUI.owner = owner; return { event = event } end,
  } }
""" % DUI_FONT
# EllesmereUI: its global font (GetFontPath(nil)), outline (GetFontOutlineFlag(nil)) and shadow (GetFontUseShadow(nil)),
# and InvalidateFontCache, called when a font is picked or a profile switched.
ELLESMERE = """
  AGPS_LOADED.EllesmereUI = true
  AGPS_EUI = { font = %r, flag = "OUTLINE, SLUG", shadow = false, dropped = 0 }
  EllesmereUI = {
    GetFontPath = function(key) return AGPS_EUI.font end,
    GetFontOutlineFlag = function(key) return AGPS_EUI.flag end,
    GetFontUseShadow = function(key) return AGPS_EUI.shadow end,
    InvalidateFontCache = function() AGPS_EUI.dropped = AGPS_EUI.dropped + 1 end,
  }
""" % EUI_FONT
UNDO = """
  C_AddOns.IsAddOnLoaded, IsAddOnLoaded, hooksecurefunc, C_Timer.After = AGPS_OLD[1], AGPS_OLD[2], AGPS_OLD[3], AGPS_OLD[4]
  DaylightUI, EllesmereUI, AGPS_MISSING_FONTS = nil, nil, nil
"""


@pytest.fixture(scope="module")
def harness():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    return start()


@pytest.fixture
def ui(harness):
    lua, ns = harness
    st = ns.settings.gps
    lua.execute(LOADED)
    yield lua, ns
    lua.execute(UNDO)
    st.dirTextStyle = "ui"
    U = ns.UIFont
    U.hooked, U.bad = lua.table(), lua.table()
    U.Refresh(True)


def _texts(ns):
    """Our HUD texts that take the style: the arrow's directions, the map's route panel, its info line, the strip's."""
    A, G = ns.Arrow, ns.GPS
    out = {"directions": A.line1, "route panel": G.navText, "steps": G.stepsText, "info line": G.infoText}
    if G.mx is not None and G.mx.strip is not None:
        out["height strip"] = G.mx.strip.text
    return out


def _font(fs):
    f = fs._font
    return (f[1], f[2], f[3]) if f is not None else None


def test_the_texts_are_registered_and_the_menus_are_not(harness):
    lua, ns = harness
    U = ns.UIFont
    has = lua.eval("function(t, x) for _, v in ipairs(t) do if rawequal(v, x) then return true end end return false end")
    for name, fs in _texts(ns).items():
        assert has(U.texts, fs), name
    assert len(U.texts) <= 16  # (a handful of HUD texts, never the options window's or the menus')


def test_without_a_ui_nothing_changes(ui):
    lua, ns = ui
    U = ns.UIFont
    U.OnEnteringWorld()
    assert U.Source() is None and U.Wanted() is None
    for name, fs in _texts(ns).items():
        assert fs._font is None, name  # (never SetFont: the template's font, all its alphabets)
        assert fs.agpsUIStyled is None, name
    assert ns.Arrow.line1._fontObject == "GameFontNormal"


def test_the_directions_take_daylightuis_font_outline_and_shadow(ui):
    lua, ns = ui
    U, st = ns.UIFont, ns.settings.gps
    lua.execute(DAYLIGHT)
    U.OnEnteringWorld()
    assert U.Source() == "DaylightUI"
    for name, fs in _texts(ns).items():
        assert _font(fs) == (DUI_FONT, 12, "THICKOUTLINE"), name
        assert fs._shadowOffset[1] == 1 and fs._shadowOffset[2] == -1, name
        assert fs._shadowColor[4] == pytest.approx(0.6), name
    # (our size kept: the font object's size, times the directions' Text size)
    st.dirTextScale = 1.3
    ns.Arrow.Apply()
    assert ns.Arrow.line1._textScale == pytest.approx(1.3) and ns.Arrow.line1._font[2] == 12
    st.dirTextScale = 1
    ns.Arrow.Apply()
    # (DaylightUI's Shadow off and Outline none: neither)
    lua.execute('AGPS_DUI.general.textOutline, AGPS_DUI.general.textShadow = "", false')
    U.Refresh()
    assert _font(ns.Arrow.line1) == (DUI_FONT, 12, "") and ns.Arrow.line1._shadowColor[4] == 0
    # (listening to its StyleChanged, as our own addon)
    assert lua.eval("AGPS_DUI.on.StyleChanged") is not None and lua.eval("AGPS_DUI.owner") == "AzerothGPS"


def test_the_directions_take_ellesmereuis_font_and_outline(ui):
    lua, ns = ui
    U = ns.UIFont
    lua.execute(ELLESMERE)
    U.OnEnteringWorld()
    assert U.Source() == "EllesmereUI"
    for name, fs in _texts(ns).items():
        assert _font(fs) == (EUI_FONT, 12, "OUTLINE, SLUG"), name
        assert fs._shadowColor[4] == 0, name  # (its outline mode: no drop shadow)
    lua.execute('AGPS_EUI.flag, AGPS_EUI.shadow = "", true')  # (its "shadow" outline mode)
    lua.execute("EllesmereUI.InvalidateFontCache()")
    assert _font(ns.GPS.infoText) == (EUI_FONT, 12, "") and ns.GPS.infoText._shadowColor[4] == 1


def test_the_players_own_choice_wins(ui):
    lua, ns = ui
    U, st, O = ns.UIFont, ns.settings.gps, ns.Options
    lua.execute(DAYLIGHT)
    U.OnEnteringWorld()
    assert _font(ns.Arrow.line1)[0] == DUI_FONT
    O.Show()
    O.ShowPage("Directions")
    O.Refresh()
    by_key = {c.key: c.control for c in O.settingControls.values() if not c.mirror}
    buttons = by_key["dirTextStyle"]
    radio = {buttons[i].value: buttons[i] for i in range(1, len(buttons) + 1)}
    assert list(radio) == ["ui", "agps"] and buttons.agpsOn is True and radio["ui"]._checked
    radio["agps"]._scripts.OnClick(radio["agps"])
    assert st.dirTextStyle == "agps"
    for name, fs in _texts(ns).items():
        assert fs._font is None, name  # (back to its own font object)
        assert fs.agpsUIStyled is None, name
    assert ns.Arrow.line1._fontObject == "GameFontNormal" and ns.GPS.infoText._fontObject == "GameFontHighlightSmall"
    assert ns.GPS.infoText._shadowOffset[1] == 1  # (its own shadow back)
    # (a UI style change doesn't take it back)
    lua.execute('AGPS_DUI.font = %r' % DUI_FONT2)
    lua.execute('AGPS_DUI.on.StyleChanged()')
    assert ns.Arrow.line1._font is None
    radio["ui"]._scripts.OnClick(radio["ui"])
    assert st.dirTextStyle == "ui" and _font(ns.Arrow.line1)[0] == DUI_FONT2
    # (gray without a supported UI)
    lua.execute("AGPS_LOADED.DaylightUI = false")
    O.Refresh()
    assert buttons.agpsOn is False


def test_a_font_that_doesnt_load_falls_back_to_ours(ui):
    lua, ns = ui
    U = ns.UIFont
    lua.execute(ELLESMERE)
    lua.execute("AGPS_MISSING_FONTS = { [%r] = true }" % EUI_FONT)
    U.OnEnteringWorld()
    for name, fs in _texts(ns).items():
        assert fs._font is None and fs.agpsUIStyled is None, name
    assert U.Wanted() is None
    # (picked again in that UI, one that loads: taken)
    lua.execute('AGPS_EUI.font = %r' % DUI_FONT2)
    lua.execute("EllesmereUI.InvalidateFontCache()")
    assert _font(ns.Arrow.line1)[0] == DUI_FONT2


def test_a_ui_font_changed_while_playing_is_followed(ui):
    lua, ns = ui
    U = ns.UIFont
    lua.execute(DAYLIGHT)
    U.OnEnteringWorld()
    assert _font(ns.GPS.navText)[0] == DUI_FONT
    # (its Appearance font picked, or a profile switched: DaylightUI fires StyleChanged)
    lua.execute('AGPS_DUI.font = %r' % DUI_FONT2)
    lua.execute('AGPS_DUI.on.StyleChanged()')
    for name, fs in _texts(ns).items():
        assert _font(fs)[0] == DUI_FONT2, name
    # (EllesmereUI: a profile switched drops its font cache; the hook is ours, its own function still runs)
    lua.execute("DaylightUI, AGPS_LOADED.DaylightUI = nil, false")
    lua.execute(ELLESMERE)
    U.OnEnteringWorld()
    assert _font(ns.GPS.navText)[0] == EUI_FONT
    lua.execute('AGPS_EUI.font = %r' % DUI_FONT)
    lua.execute("EllesmereUI.InvalidateFontCache()")
    assert lua.eval("AGPS_EUI.dropped") == 1
    assert _font(ns.GPS.navText)[0] == DUI_FONT and _font(ns.Arrow.line1)[0] == DUI_FONT
    # (the UI gone: ours again)
    lua.execute("EllesmereUI, AGPS_LOADED.EllesmereUI = nil, false")
    U.OnEnteringWorld()
    assert ns.GPS.navText._font is None and ns.GPS.navText._fontObject == "GameFontHighlightSmall"


def test_our_text_in_another_alphabet_than_the_clients_keeps_ours(ui):
    # (the UI's font is picked for the client's language: our text in Korean on an English client would be squares)
    lua, ns = ui
    U = ns.UIFont
    lua.execute(DAYLIGHT)
    was = ns.LOCALE
    try:
        ns.LOCALE = "koKR"
        U.Refresh()
        assert ns.Arrow.line1._font is None
        ns.LOCALE = "deDE"
        U.Refresh()
        assert _font(ns.Arrow.line1)[0] == DUI_FONT
    finally:
        ns.LOCALE = was
