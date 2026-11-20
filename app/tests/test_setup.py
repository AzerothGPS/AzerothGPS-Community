"""The first-run setup and the first route's tips (Setup.lua, 1.3.10; Kooki3z: "A one-time popup that lets users choose
cards for major options ... One popup for setup on initial install. Then tutorials would not be a popup, just a dialog
panel message where route directions go, until the player does their first route"; 2026-11-19: "Setup runs once for
everyone after the next update"): shown once to everyone (a stamp in the saved settings), a player updating's own
settings lit; the minimap's live preview put back by Skip or closing (or a /reload meanwhile); Finish keeps the picks;
the tutorial's offer only after the setup is closed; the cards' pictures from Media/Setup or the drawing; the tips in
the route panel's place (on the map and detached) until the first route is done, a first install's only; no tutorial
popup on a first install; the cards driven by a controller."""

import os
import struct

import pytest

UPGRADE = 'AzerothGPSDB = { settings = { gps = { size = 400, iconSize = "large", useWorldMap = true } }, chars = {} }'


def _start(saved=None):
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start(saved=saved)
    lua.execute("""
      AGPS_PRINTS = {}
      AGPS_NS.Print = function(...) AGPS_PRINTS[#AGPS_PRINTS + 1] = tostring((...)) end
      AGPS_CLICK = function(b) assert(b:GetScript("OnClick"), "nothing to click")(b, "LeftButton") end
      AGPS_AFTER = {}
      C_Timer.After = function(s, fn) AGPS_AFTER[#AGPS_AFTER + 1] = fn end
      function AGPS_SAVED() -- (the saved variables as the game writes them, for the next session)
        local function Lit(v)
          local t = type(v)
          if t == "string" then return string.format("%q", v) end
          if t == "number" then return string.format("%.17g", v) end
          if t ~= "table" then return tostring(v) end
          local out = {}
          for k, x in pairs(v) do out[#out + 1] = "[" .. Lit(k) .. "]=" .. Lit(x) end
          return "{" .. table.concat(out, ",") .. "}"
        end
        return "AzerothGPSDB = " .. Lit(AzerothGPSDB)
      end
    """)
    return lua, ns


def _close(f):
    """The X or Escape: hidden, its OnHide run (as the game does)."""
    f.Hide(f)
    f._scripts.OnHide(f)


def _cards(ns):
    return [b for b in ns.Setup.window.cards.values() if b._shown]


def _redraw(lua, ns):
    lua.execute("AGPS_T = AGPS_T + 1")
    ns.GPS.Update()


# ---------------------------------------------------------------- shown once, to everyone

def test_the_setup_shows_on_a_first_install_once():
    lua, ns = _start()
    S = ns.Setup
    assert ns.db.setup.shown is None and ns.db.tips.due is True and S.Due() is True
    # (some seconds after the world is entered)
    S.OnEnteringWorld()
    assert S.Shown() is False
    lua.eval("AGPS_AFTER[#AGPS_AFTER]")()
    f = S.window
    assert S.Shown() is True and f._shown
    # the popup window style: ns.Window's (the map window's frame and corner logo where the client has the template;
    # test_map_redraw's test_a_popup_window_has_the_map_windows_frame_and_a_small_logo), a popup lifted over the map
    assert lua.eval("AGPS_NS.popups[AzerothGPSSetup] ~= nil") and f.SetWindowTitle is not None
    assert [str(b.title._text) for b in _cards(ns)] == ["GPS minimap", "The game's minimap"]
    assert str(f.step._text) == "Step 1 of 2" and str(f.heading._text) == "Your minimap"
    assert [str(b._text) for b in (f.skip, f.back, f.next)] == ["Skip", "Back", "Next"]
    lua.globals().AGPS_CLICK(f.skip)
    assert S.Shown() is False and ns.db.setup.shown == S.VERSION
    S.asked = None
    S.OnEnteringWorld()
    assert S.MaybeShow() is False and S.Shown() is False  # (not again by itself)


def _relog(lua):
    """The game left and entered again: the saved variables written and read by a new session."""
    lua.eval("AGPS_FIRE")("PLAYER_LOGOUT")
    return _start(saved=lua.eval("AGPS_SAVED()"))


@pytest.mark.parametrize("leave", ["finish", "skip"])
def test_a_player_updating_sees_it_once_on_their_own_settings_and_never_again(leave):
    # (saved settings from before the setup, no stamp: shown once, some seconds after the world is entered)
    lua, ns = _start(saved=UPGRADE)
    S = ns.Setup
    st = ns.settings.gps
    assert st.size == 400 and st.iconSize == "large" and st.useWorldMap is True  # (their settings kept)
    assert ns.db.tips.due is None  # (no first-route tips for a player who has done routes)
    assert S.Due() is True
    S.OnEnteringWorld()
    lua.eval("AGPS_AFTER[#AGPS_AFTER]")()
    f = S.window
    assert S.Shown() is True and ns.db.setup.shown == S.VERSION
    _redraw(lua, ns)
    assert S.tipPanel is None or not S.tipPanel._shown
    click = lua.globals().AGPS_CLICK
    click(f.next)
    assert str(f.heading._text) == "Where the map opens"
    assert [bool(b.lit._shown) for b in _cards(ns)] == [False, True]  # (lit to what they have)
    click(_cards(ns)[0])
    if leave == "finish":
        click(f.next)
        assert st.useWorldMap is False
    else:
        click(f.skip)
        assert st.useWorldMap is True  # (theirs, as it was)
    assert S.Shown() is False and ns.db.setup.shown == S.VERSION
    # the next login: not again
    lua, ns = _relog(lua)
    S = ns.Setup
    assert S.Due() is False and ns.settings.gps.useWorldMap is (leave != "finish")
    S.OnEnteringWorld()
    assert lua.eval("#AGPS_AFTER") == 0 and S.MaybeShow() is False and S.window is None


def test_a_reload_with_the_setup_open_puts_their_settings_back_and_doesnt_show_it_again():
    lua, ns = _start(saved=UPGRADE)
    S = ns.Setup
    S.MaybeShow()
    assert S.Shown() is True
    lua.globals().AGPS_CLICK(_cards(ns)[0])  # (the GPS minimap: applied at once)
    assert ns.settings.gps.replaceMinimap is True
    lua, ns = _relog(lua)  # (a /reload: no OnHide, no Skip)
    assert ns.settings.gps.replaceMinimap is not True and ns.settings.gps.iconSize == "large"
    assert ns.db.setup.before is None and ns.Setup.Due() is False


def test_a_later_version_of_the_setup_shows_once_more():
    lua, ns = _start(saved=UPGRADE)
    S = ns.Setup
    S.Open()
    S.Close(True)
    assert S.Due() is False
    S.VERSION = S.VERSION + 1
    assert S.Due() is True


def test_a_first_install_in_combat_gets_the_setup_when_the_fight_ends():
    lua, ns = _start()
    S = ns.Setup
    lua.execute("AGPS_NS.inCombat = true")
    assert S.MaybeShow() is False and S.waiting is True
    lua.execute("AGPS_NS.inCombat = false")
    S.events._scripts.OnEvent(S.events, "PLAYER_REGEN_ENABLED")
    assert S.Shown() is True
    _close(S.window)


def test_run_setup_again_from_options_and_the_slash_command():
    lua, ns = _start(saved=UPGRADE)
    S, O = ns.Setup, ns.Options
    O.Show()
    assert O.ShowPage("Help") is True
    ws = lua.eval("AGPS_WIDGETS")
    again = next(w for w in ws.values() if w._kind == "Button" and w._text == "Run Setup Again")
    lua.globals().AGPS_CLICK(again)
    assert S.Shown() is True and lua.eval("AzerothGPSOptions._shown") is False  # (Options out of the way)
    _close(S.window)
    assert ns.settings.gps.useWorldMap is True  # (closed: theirs as it was)
    lua.eval("SlashCmdList.AZEROTHGPS")("setup")
    assert S.Shown() is True
    _close(S.window)


# ---------------------------------------------------------------- the live preview and Finish

def test_the_minimap_preview_is_live_and_skip_or_closing_puts_it_back():
    lua, ns = _start()
    S, G = ns.Setup, ns.GPS
    st = ns.settings.gps
    size = st.replaceMinimapSize
    for leave in ("skip", "close"):
        assert S.Open() is True
        f = S.window
        assert st.replaceMinimap is False and G.mmState.on is False
        assert not f.sizes[1]._shown  # (the size row: with the GPS minimap only)
        gps_card, game_card = _cards(ns)
        assert game_card.lit._shown and not gps_card.lit._shown
        lua.globals().AGPS_CLICK(gps_card)
        # applied at once: the GPS map is the minimap now, at the size shown lit
        assert st.replaceMinimap is True and G.mmState.on is True and gps_card.lit._shown
        assert [str(b._text) for b in f.sizes.values()] == ["Small", "Medium", "Large"]
        assert f.sizes[1]._shown and f.sizes[1].lit._shown
        lua.globals().AGPS_CLICK(f.sizes[3])
        assert st.replaceMinimapSize == "large" and f.sizes[3].lit._shown and not f.sizes[1].lit._shown
        lua.globals().AGPS_CLICK(f.next)  # (a pick on another page is put back too)
        lua.globals().AGPS_CLICK(_cards(ns)[1])
        assert st.useWorldMap is True
        if leave == "skip":
            lua.globals().AGPS_CLICK(f.skip)
        else:
            _close(f)
        assert S.Shown() is False
        assert st.replaceMinimap is False and st.replaceMinimapSize == size and st.useWorldMap is False
        assert G.mmState.on is False


def test_finish_keeps_every_pick():
    lua, ns = _start()
    S, G = ns.Setup, ns.GPS
    st = ns.settings.gps
    S.Open()
    f = S.window
    click = lua.globals().AGPS_CLICK
    assert str(f.back._text) == "Back" and f.back._enabled is False
    click(_cards(ns)[0])
    click(f.sizes[2])
    click(f.next)
    assert str(f.heading._text) == "Where the map opens" and f.back._enabled is True
    assert [str(b.title._text) for b in _cards(ns)] == ["GPS map window", "In the world map"]
    click(_cards(ns)[1])
    # (two pages since 2026-11-19: the route directions and icon size pages taken out)
    assert str(f.next._text) == "Finish" and str(f.step._text) == "Step 2 of 2"
    click(f.back)
    assert str(f.heading._text) == "Your minimap" and _cards(ns)[0].lit._shown  # (Back shows what's picked)
    assert f.sizes[2].lit._shown
    click(f.next)
    assert _cards(ns)[1].lit._shown
    click(f.next)  # Finish
    assert S.Shown() is False and ns.db.setup.shown == S.VERSION and ns.db.setup.done
    assert (st.replaceMinimap, st.replaceMinimapSize, st.useWorldMap) == (True, "medium", True)
    assert G.mmState.on is True
    assert [str(p.id) for p in S.PAGES.values()] == ["minimap", "map"]
    assert "Setup done." in str(lua.eval("AGPS_PRINTS[#AGPS_PRINTS]"))


def test_a_disabled_card_cant_be_picked():
    # (the world map with the game's controller UI on: as Options' own, gray)
    lua, ns = _start()
    S = ns.Setup
    lua.execute("AGPS_NS.GPS.ControllerUI = function() return true end")
    S.Open()
    S.Go(1)
    world = _cards(ns)[1]
    assert world.agpsOn is False
    lua.globals().AGPS_CLICK(world)
    assert ns.settings.gps.useWorldMap is False
    _close(S.window)


# ---------------------------------------------------------------- the tips, in the route panel's place

def test_the_tips_show_where_the_route_goes_until_the_first_route_is_done():
    lua, ns = _start()
    S, G, N = ns.Setup, ns.GPS, ns.Nav
    _redraw(lua, ns)
    p = S.tipPanel
    assert p is not None and p._shown and not G.navPanel._shown
    same = lua.eval("function(a, b) return a == b end")
    assert same(p.GetParent(p), G.navPanel.GetParent(G.navPanel))  # (on the map, where the route panel goes)
    assert str(p.head._text) == "Tip 1 of 5: Place a stop"
    assert str(p.text._text) == "Double-click anywhere on the map to place a stop."
    assert [str(b._text) for b in (p.next, p.hide)] == ["Next", "Hide Tips"]
    lua.globals().AGPS_CLICK(p.next)
    assert str(p.head._text) == "Tip 2 of 5: Start the route" and ns.db.tips.at == 2
    # a route: the panel shows it, the tip makes way
    N.SetDestination(2304.0, 293.0, 0, "Somewhere")
    _redraw(lua, ns)
    assert G.navPanel._shown and not p._shown
    # the route done (its last stop reached): no more tips, ever
    N.TellArrived(lua.eval("{ x = 2304, y = 293, cont = 0, name = 'Somewhere' }"), True)
    N.Clear()
    _redraw(lua, ns)
    assert ns.db.tips.due is None and not p._shown and S.TipsOn() is False


def test_the_tips_follow_a_detached_route_panel_and_hide_with_the_map():
    lua, ns = _start()
    S, G = ns.Setup, ns.GPS
    ns.settings.gps.navPanelDetached = True
    G.ApplySettings()
    _redraw(lua, ns)
    p = S.tipPanel
    assert G.navDetached is True and p._shown
    same = lua.eval("function(a, b) return a == b end")
    assert same(p.GetParent(p), G.navPanel.GetParent(G.navPanel)) and same(p.GetParent(p), lua.eval("UIParent"))
    # the map closed: the detached tip with it
    lua.execute("AzerothGPSFrame:Hide()")
    p._scripts.OnUpdate(p, 0.1)
    assert not p._shown
    # the minimap square: no tips on it
    lua.execute("AzerothGPSFrame:Show()")
    lua.execute("AGPS_NS.GPS.MinimapMode = function() return true end")
    assert S.TipsWanted(G) is False


def test_the_tip_buttons_sit_above_the_tip_panel_so_they_take_clicks():
    # (1.3.10, a player: "Hide Tips" and "Next" weren't clickable, on the map and detached. The buttons were made while
    # the panel was on UIParent and kept that low level when it was raised; the panel's own mouse took their clicks.)
    for detached in (False, True):
        lua, ns = _start()
        S, G = ns.Setup, ns.GPS
        if detached:
            ns.settings.gps.navPanelDetached = True
            G.ApplySettings()
        _redraw(lua, ns)
        p = S.tipPanel
        assert p._shown
        for b in (p.next, p.hide):  # (the levels set: the stand-in's GetFrameLevel is always 5)
            assert b._level is not None and b._level > p._level, (detached, b._level, p._level)


def test_got_it_on_the_last_tip_and_hide_tips_stop_them():
    lua, ns = _start()
    S = ns.Setup
    _redraw(lua, ns)
    p = S.tipPanel
    for i in range(1, 5):
        assert str(p.next._text) == "Next"
        lua.globals().AGPS_CLICK(p.next)
    assert str(p.head._text).startswith("Tip 5 of 5") and str(p.next._text) == "Got It"
    lua.globals().AGPS_CLICK(p.next)
    assert ns.db.tips.due is None and not p._shown
    lua, ns = _start()
    _redraw(lua, ns)
    p = ns.Setup.tipPanel
    lua.globals().AGPS_CLICK(p.hide)
    _redraw(lua, ns)
    assert ns.db.tips.due is None and not p._shown


def test_no_tutorial_popup_on_a_first_install_and_the_offer_stays_for_an_update():
    lua, ns = _start()
    T, S = ns.Tutorial, ns.Setup
    lua.execute("AGPS_NS.Tutorial.CanPrompt = function() return true end")
    assert T.MaybePrompt() is False and T.prompt is None  # (the setup first)
    S.MaybeShow()
    lua.globals().AGPS_CLICK(S.window.skip)
    lua.eval("AGPS_AFTER[#AGPS_AFTER]")()  # (the offer that waited: a moment after)
    assert T.prompt is None
    assert ns.db.tutorial.offered == T.Newest()  # (counted as offered: no "what's new" for these sections later)
    # (still there to play: Options > Help and /agps tutorial)
    assert "tutorial" in [str(e.id) for e in ns.Options.helpSections.values()]


def test_the_whats_new_offer_waits_for_the_setup_and_never_shows_with_it():
    lua, ns = _start(saved='AzerothGPSDB = { settings = { gps = {} }, chars = {} }')
    T, S = ns.Tutorial, ns.Setup
    lua.execute("AGPS_NS.Tutorial.CanPrompt = function() return true end")
    # (both at login: the setup after S.DELAY s, the offer after T.PROMPT_DELAY s)
    S.OnEnteringWorld()
    T.OnEnteringWorld()
    for fn in list(lua.eval("AGPS_AFTER").values()):
        fn()
    assert S.Shown() is True and T.prompt is None and T.prompted is None  # (the setup first, alone)
    T.MaybePrompt()
    assert T.prompt is None
    lua.execute("AGPS_AFTER = {}")
    _close(S.window)  # (the X)
    assert T.prompt is None  # (not at the same moment)
    lua.eval("AGPS_AFTER[#AGPS_AFTER]")()
    assert T.prompt._shown and ns.db.tutorial.declined == 0  # (now, alone)
    # the setup opened by hand over the offer: the offer put away (not a Not Now) and back after
    lua.eval("SlashCmdList.AZEROTHGPS")("setup")
    assert S.Shown() is True and not T.prompt._shown and ns.db.tutorial.declined == 0
    assert T.MaybePrompt() is False and not T.prompt._shown
    lua.execute("AGPS_AFTER = {}")
    lua.globals().AGPS_CLICK(S.window.skip)
    lua.eval("AGPS_AFTER[#AGPS_AFTER]")()
    assert T.prompt._shown and not S.Shown()


# ---------------------------------------------------------------- the cards' pictures

def test_a_card_shows_its_picture_file_and_the_drawing_without_one():
    lua, ns = _start()
    S = ns.Setup
    assert not any(S.ImageKnown(a) for a in S.ART.keys())  # (no files in the harness: the drawings)
    lua.execute("""
      local S = AGPS_NS.Setup
      AGPS_DRAWN = {}
      for name, fn in pairs(S.ART) do S.ART[name] = function(a) AGPS_DRAWN[name] = true return fn(a) end end
    """)
    S.Open()
    assert _cards(ns)[0].art.image is None and lua.eval("AGPS_DRAWN.gpsMinimap and AGPS_DRAWN.gameMinimap")
    _close(S.window)
    lua.execute("AGPS_DRAWN = {}")
    # a file the client has: shown pixel for pixel, cropped from its power-of-two canvas, filtered no higher than LINEAR
    # (as at a new session's first open: the files are read at login, the cards made then)
    lua.execute("""
      local S = AGPS_NS.Setup
      S.imageKnown.gpsMinimap = true
      for _, b in ipairs(S.window.cards) do b.drawn = nil end
    """)
    S.Open()
    a = _cards(ns)[0].art
    img = a.image
    assert img is not None and str(img._tex).endswith("Media\\Setup\\gpsMinimap")
    assert [float(c) for c in img._coords.values()] == [0, 300 / 512, 0, 180 / 256]
    assert img._filter in (None, "LINEAR")
    # (cut out with a glow: the card's own background behind it, no screen box; the drawings keep theirs)
    assert a.screen is not None and not a.screen._shown and _cards(ns)[1].art.screen._shown
    w, h = a._w, a._h
    assert (round(w * S.REF_PPU), round(h * S.REF_PPU)) == (300, 180)
    assert _cards(ns)[1].art.image is None  # (the game's minimap: no file, its drawing)
    assert lua.eval("AGPS_DRAWN.gameMinimap and not AGPS_DRAWN.gpsMinimap")
    _close(S.window)


def test_every_setup_picture_file_is_a_cards_and_exactly_its_size():
    # (Media/Setup/<art>.tga: a card's art name, its picture S.IMAGE_PX big in the top left of a power-of-two canvas,
    # the rest clear; every card has one since 2026-11-19, Kooki3z's screenshots, `agps setup-art`)
    lua, ns = _start()
    S = ns.Setup
    sizes = {}
    for p in S.PAGES.values():
        n = len(list(p.cards.values()))
        for c in p.cards.values():
            sizes[str(c.art)] = tuple(S.IMAGE_PX[n].values())
    here = os.path.dirname(os.path.abspath(__file__))
    media = os.path.join(here, "..", "..", "addon", "AzerothGPS", "Media", "Setup")
    files = os.listdir(media) if os.path.isdir(media) else []
    for name in files:
        art, ext = os.path.splitext(name)
        assert art in sizes and ext.lower() in (".tga", ".blp"), name
        if ext.lower() == ".tga":
            with open(os.path.join(media, name), "rb") as fh:
                w, h = struct.unpack("<HH", fh.read(18)[12:16])
            pw, ph = sizes[art]
            assert w >= pw and h >= ph and w & (w - 1) == 0 and h & (h - 1) == 0, name
            from PIL import Image
            with Image.open(os.path.join(media, name)) as im:
                im = im.convert("RGBA")
                # (the picture the right way up in the top left, the rest of the canvas clear; cut out, with alpha)
                assert im.getpixel((pw // 2, ph // 2))[3] == 255, name
                assert im.crop((pw, 0, w, h)).getchannel("A").getextrema()[1] == 0, name
                assert im.crop((0, ph, w, h)).getchannel("A").getextrema()[1] == 0, name
                assert im.getpixel((0, 0))[3] < 255 and im.getpixel((pw - 1, ph - 1))[3] < 255, name
    assert sorted(os.path.splitext(n)[0] for n in files) == sorted(sizes)  # (a picture for every card)


# ---------------------------------------------------------------- the controller

PAD = """
  C_GamePad = {
    IsEnabled = function() return true end,
    GetActiveDeviceID = function() return 1 end,
    GetDeviceMappedState = function() return { labelStyle = "Letters", sticks = {}, buttons = {} } end,
  }
  AGPS_LOCK = false
  InCombatLockdown = function() return AGPS_LOCK end
  AGPS_BINDS = {}
  SetOverrideBindingClick = function(owner, prio, key, button)
    if AGPS_LOCK then error("blocked: SetOverrideBindingClick in combat") end
    AGPS_BINDS[key] = { owner = owner, button = button }
  end
  ClearOverrideBindings = function(owner)
    if AGPS_LOCK then error("blocked: ClearOverrideBindings in combat") end
    for k, v in pairs(AGPS_BINDS) do if v.owner == owner then AGPS_BINDS[k] = nil end end
  end
  AGPS_PRESS = function(key)
    local b = AGPS_BINDS[key]
    if not b then return false end
    local btn = _G[b.button]
    btn._scripts.OnClick(btn, "LeftButton", true)
    return true
  end
"""


def test_the_cards_are_picked_with_a_controller():
    lua, ns = _start()
    lua.execute(PAD)
    S = ns.Setup
    st = ns.settings.gps
    press = lua.eval("AGPS_PRESS")
    same = lua.eval("function(a, b) return a == b end")
    S.Open()
    f = S.window
    binds = {str(k): str(v.button) for k, v in lua.eval("AGPS_BINDS").items()}
    assert binds["PAD1"] == "AzerothGPSSetupPad_PAD1" and binds["PADDRIGHT"] == "AzerothGPSSetupPad_PADDRIGHT"
    assert ns.Pad.bound is False  # (the map's own off meanwhile)
    # (no page of its own for the controller: 2026-11-19, "not necessary")
    assert str(f.step._text) == "Step 1 of 2"
    assert same(S.focus, _cards(ns)[1]) and f.focus._shown  # (the card picked: the game's minimap)
    press("PADDLEFT")
    assert same(S.focus, _cards(ns)[0])
    press("PAD1")
    assert st.replaceMinimap is True and ns.GPS.mmState.on is True
    press("PADDDOWN")
    assert same(S.focus, f.sizes[1])
    press("PADDRIGHT")
    press("PAD1")
    assert st.replaceMinimapSize == "medium"
    press("PADDDOWN")
    assert same(S.focus, f.next)
    press("PAD1")
    assert str(f.heading._text) == "Where the map opens"
    press("PAD2")  # B: back a page
    assert str(f.heading._text) == "Your minimap"
    press("PADRSHOULDER")
    assert str(f.heading._text) == "Where the map opens" and "Controller" not in [str(p.title) for p in S.PAGES.values()]
    press("PADDRIGHT")  # (from the map window, lit as it opened)
    press("PAD1")
    assert st.useWorldMap is True and S.padBound is True
    press("PADRSHOULDER")  # Finish
    assert S.Shown() is False and st.useWorldMap is True and st.replaceMinimap is True
    assert not any(str(v.button).startswith("AzerothGPSSetupPad_") for v in lua.eval("AGPS_BINDS").values())


def test_the_controller_is_let_go_before_combat_and_b_on_the_first_page_closes():
    lua, ns = _start()
    lua.execute(PAD)
    S = ns.Setup
    S.Open()
    assert S.padBound is True
    ns.Pad.Clear()  # (PLAYER_REGEN_DISABLED: before the lockdown)
    assert S.padBound is False and not list(lua.eval("AGPS_BINDS").values())
    S.PadApply()
    assert S.padBound is True
    lua.eval("AGPS_PRESS")("PAD2")
    assert S.Shown() is False and S.padBound is False
