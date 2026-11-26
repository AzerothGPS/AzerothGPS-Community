"""A controller on the map, phase 1 (Pad.lua; asked 2026-11-16: "for the next AzerothGPS version lets plan on full
controller support", the plan: "go with the recommendations"). The pad's buttons are override
bindings of our own owner frame while the map is open and out of combat; a fake pad (C_GamePad), the bindings
recorded (blocked in combat lockdown, as the game blocks them) and a press runs the bound button as the client does."""
import re
from pathlib import Path

import pytest

ADDON = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS"


# a fake pad (C_GamePad) and the game's binding calls, recorded (blocked in combat lockdown, as the game blocks them);
# AGPS_PRESS(key, down) runs the bound button as the client does
PAD_STUBS = """
      AGPS_PAD = { enabled = true, id = 1, style = "Letters", sticks = { { x = 0, y = 0 }, { x = 0, y = 0 } } }
      C_GamePad = {
        IsEnabled = function() return AGPS_PAD.enabled end,
        GetActiveDeviceID = function() return AGPS_PAD.id end,
        GetDeviceMappedState = function() return { labelStyle = AGPS_PAD.style, sticks = AGPS_PAD.sticks, buttons = {} } end,
        StickIndexToConfigName = function(i) return i == 1 and "Movement" or "Camera" end,
      }
      AGPS_LOCK = false
      InCombatLockdown = function() return AGPS_LOCK end
      AGPS_BINDS, AGPS_SETBIND = {}, {}
      SetOverrideBindingClick = function(owner, prio, key, button)
        if AGPS_LOCK then error("blocked: SetOverrideBindingClick in combat") end
        AGPS_BINDS[key] = { owner = owner, button = button }
      end
      ClearOverrideBindings = function(owner)
        if AGPS_LOCK then error("blocked: ClearOverrideBindings in combat") end
        for k, v in pairs(AGPS_BINDS) do if v.owner == owner then AGPS_BINDS[k] = nil end end
      end
      SetBinding = function(key, action) AGPS_SETBIND[key] = action return true end
      GetBindingAction = function(key) return AGPS_SETBIND[key] or "TOGGLEWORLDMAP" end
      AGPS_PRESS = function(key, down)
        local b = AGPS_BINDS[key]
        if not b then return false end
        local btn = _G[b.button]
        btn._scripts.OnClick(btn, "LeftButton", down)
        return true
      end
    """


@pytest.fixture()
def pad():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start

    lua, ns = start()
    lua.execute(PAD_STUBS)
    # (the defaults that take LB and RB, 2026-11-16: off here, these tests' free buttons as before; the defaults
    # themselves: test_the_defaults_put_the_route_controls_on_lb)
    lua.execute("""
      AGPS_DEF = {}
      for _, a in ipairs(AGPS_NS.Pad.ACTIONS) do
        if a[1] == "click" or a[1] == "viewControls" or a[1] == "clear" or a[1] == "questRoute" or a[1] == "pause"
            or a[1] == "avoids" then
          AGPS_DEF[a[1]] = a[2]
          a[2] = nil
        end
      end
    """)
    ns.db.padOffered = True  # (the one offer: its own test)
    ns.settings.gps.padControl = True
    ns.Pad.used = True  # (the pad in use: its marks; the input check has its own test)
    lua.execute("AGPS_T = AGPS_T + 1")
    ns.GPS.Update()
    yield lua, ns
    lua.execute("AGPS_LOCK = false")
    ns.Pad.Clear()


def _bound(lua):
    return {str(k): str(v.button) for k, v in lua.eval("AGPS_BINDS").items()}


def _press(lua, key, down=True):
    return lua.eval("AGPS_PRESS")(key, down)


def _event(lua, e):
    lua.execute("AzerothGPSPadOwner._scripts.OnEvent(AzerothGPSPadOwner, '%s')" % e)


# the buttons' icons on the map (Pad.KeyIcon, test_pad_icons.py) read back as the names Pad.KeyLabel gives them
ICON_TEXT = {"LStickPress": "Left stick press", "RStickPress": "Right stick press", "DPadUp": "D-pad up",
             "DPadDown": "D-pad down", "DPadLeft": "D-pad left", "DPadRight": "D-pad right", "DPad": "D-pad",
             "View": "Back", "Menu": "Start"}


def _plain(text):
    """The map's legend or box line with its button icons as their names ("|T...A_14.tga:14:14|t" -> "A", a pair's
    icons "LB + Y")."""
    text = str(text).replace("|t+|T", "|t + |T")
    return re.sub(r"\|T[^|]*\\Pad\\([A-Za-z0-9]+)_\d+\.tga:\d+:\d+\|t", lambda m: ICON_TEXT.get(m.group(1), m.group(1)),
                  text)


def test_the_pads_buttons_are_ours_while_the_map_is_open_and_never_in_combat(pad):
    lua, ns = pad
    P = ns.Pad
    assert P.Apply() is True
    b = _bound(lua)
    assert set(b) == {"PAD1", "PAD2", "PAD3", "PAD4", "PADDUP", "PADDDOWN", "PADDLEFT", "PADDRIGHT", "PADLTRIGGER",
                      "PADRTRIGGER", "PADLSTICK", "PADRSTICK"}
    assert b["PAD1"] == "AzerothGPSPad_PAD1" and b["PAD2"] == "AzerothGPSPad_PAD2"  # (a button per key bound)
    owners = {str(v.owner._name) for v in lua.eval("AGPS_BINDS").values()}
    assert owners == {"AzerothGPSPadOwner"}  # (our own frame, never UIParent)
    assert P.reticle._shown and (P.legend._shown or P.box._shown)  # (the buttons listed: the box, or the line)
    # (the map's own crosshair's look, white, not yellow: asked 2026-11-16; and never two: hidden while the map's own
    # crosshair shows, looking around)
    assert P.reticle.h._tex == "color:1.00,1.00,1.00" and P.reticle.v._tex == "color:1.00,1.00,1.00"
    G = ns.GPS
    G.PadPan(0, 120)  # (panned: looking around, the map's own crosshair up)
    lua.execute("AGPS_T = AGPS_T + 1")
    G.Update()
    assert G.crossShown and not P.reticle._shown
    G.Follow()
    lua.execute("AGPS_T = AGPS_T + 1")
    G.Update()
    assert not G.crossShown and P.reticle._shown
    # closed: gone
    lua.execute("AzerothGPSFrame:Hide()")
    P.Apply()
    assert _bound(lua) == {} and not P.reticle._shown
    lua.execute("AzerothGPSFrame:Show()")
    assert P.Apply() and _bound(lua)
    # combat: cleared before the lockdown, nothing touched in it, back after
    _event(lua, "PLAYER_REGEN_DISABLED")
    assert _bound(lua) == {}
    lua.execute("AGPS_LOCK = true")
    assert P.Apply() is False and _bound(lua) == {}  # (no binding call in the lockdown: it would be blocked)
    lua.execute("AGPS_LOCK = false")
    _event(lua, "PLAYER_REGEN_ENABLED")
    assert _bound(lua)
    _event(lua, "PLAYER_LOGOUT")
    assert _bound(lua) == {}


def test_on_by_itself_with_a_pad_active_and_off_by_the_option(pad):
    lua, ns = pad
    P, st = ns.Pad, ns.settings.gps
    lua.execute("AGPS_PAD.id = nil")
    assert P.Apply() is False and _bound(lua) == {}  # (no pad in use: the map is the mouse's)
    lua.execute("AGPS_PAD.id = 1")
    assert P.Apply() is True
    st.padControl = False
    assert P.Apply() is False and _bound(lua) == {}
    st.padControl = True
    # (the minimap square only, the map not opened out: not ours)
    ns.GPS.MinimapMode, real = (lambda: True), ns.GPS.MinimapMode
    try:
        assert P.Apply() is False
    finally:
        ns.GPS.MinimapMode = real


def test_a_sets_a_stop_at_the_reticle_or_routes_to_the_icon_under_it(pad):
    lua, ns = pad
    G, P = ns.GPS, ns.Pad
    P.Apply()
    x, y = float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]"))
    G.LookAt(0, x + 400, y + 400)
    lua.execute("AGPS_T = AGPS_T + 1")
    G.Update()
    vx, vy = G.PadView()[0], G.PadView()[1]
    assert _press(lua, "PAD1")
    d = G.PendingStop(1)
    assert d and abs(d.x - vx) < 1 and abs(d.y - vy) < 1  # (the map's middle, as a double-click there)
    G.RemovePending(1)
    # an icon under the reticle: its own double-click (routes to it, with its name and icon)
    lua.execute("""
      AGPS_DBL = 0
      AGPS_ICON = NewWidget("Button", nil)
      AGPS_ICON.wx, AGPS_ICON.wy = %r, %r
      AGPS_ICON._scripts.OnDoubleClick = function() AGPS_DBL = AGPS_DBL + 1 end
    """ % (vx + 0.5, vy + 0.5))
    pois = G.poiButtons
    pois[len(pois) + 1] = lua.eval("AGPS_ICON")
    assert _press(lua, "PAD1")
    assert lua.eval("AGPS_DBL") == 1 and G.PendingStop(1) is None


def test_x_removes_the_stop_under_the_reticle_after_its_question(pad):
    lua, ns = pad
    G, N, P = ns.GPS, ns.Nav, ns.Pad
    P.Apply()
    x, y = float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]"))
    N.SetStops(lua.eval("{ { x = %r, y = %r, cont = 0, name = 'Spot' } }" % (x + 300, y + 300)), False, "red")
    G.LookAt(0, x + 300, y + 300)
    for _ in range(3):
        lua.execute("AGPS_T = AGPS_T + 0.5")
        G.Update()
    assert len(N.stops) == 1
    assert _press(lua, "PAD3")
    assert G.removeAsk and G.removeAsk._shown  # ("Remove?", as a right-click asks)
    # (the hint: the confirm's icon over Remove?, not X over the stop; asked 2026-11-16, "when Remove? is up, we should
    # fade the select icon instead to signify a confirm")
    P.SawInput(True)
    P.ShowMarks(True)
    targets = [(t[1], t[2]) for t in P.HintTargets().values()]
    same = lua.eval("rawequal")
    assert any(same(b, G.removeAsk) and str(i) in ("yes", "select") for b, i in targets)
    assert not any(str(i) == "remove" for _, i in targets)
    _press(lua, "PAD1")
    assert len(N.stops) == 0
    # nothing under it: nothing happens
    assert ns.Pad.Press("X", True) is False


def test_a_and_b_answer_a_question(pad):
    lua, ns = pad
    G, P = ns.GPS, ns.Pad
    P.Apply()
    lua.execute("AGPS_ANS = nil")
    G.Confirm("Keep this route?", lua.eval("function() AGPS_ANS = 'yes' end"), lua.eval("function() AGPS_ANS = 'no' end"))
    _press(lua, "PAD1")
    assert lua.eval("AGPS_ANS") == "yes"
    G.Confirm("Keep this route?", lua.eval("function() AGPS_ANS = 'yes' end"), lua.eval("function() AGPS_ANS = 'no' end"))
    _press(lua, "PAD2")
    assert lua.eval("AGPS_ANS") == "no"


def test_b_backs_out_a_menu_first_then_closes_the_map(pad):
    lua, ns = pad
    G, P, st = ns.GPS, ns.Pad, ns.settings.gps
    P.Apply()
    menu = G.mapMenu
    menu.Show(menu)
    _press(lua, "PAD2")
    assert not menu._shown and st.shown  # (the menu, not the map)
    _press(lua, "PAD2")
    assert not st.shown  # (then the map)
    assert _bound(lua) == {}  # (and the pad is the game's again)


def test_the_d_pad_pans_and_the_right_stick_only_with_its_option(pad):
    lua, ns = pad
    G, P, st = ns.GPS, ns.Pad, ns.settings.gps
    P.Apply()
    x0, y0 = G.PadView()[0], G.PadView()[1]
    _press(lua, "PADDRIGHT", True)
    P.Tick(0.5)
    _press(lua, "PADDRIGHT", False)
    lua.execute("AGPS_T = AGPS_T + 1")
    G.Update()
    x1, y1 = G.PadView()[0], G.PadView()[1]
    assert G.IsFree() and (abs(x1 - x0) + abs(y1 - y0)) > 1  # (moved, and held no more: stops)
    P.Tick(0.5)
    lua.execute("AGPS_T = AGPS_T + 1")
    G.Update()
    assert (G.PadView()[0], G.PadView()[1]) == (x1, y1)
    # the sticks: nothing (their options taken out, asked 2026-11-16: "remove the L and R stick pan options they don't
    # work")
    lua.execute("AGPS_PAD.sticks[2] = { x = 1, y = 0 } AGPS_PAD.sticks[1] = { x = 1, y = 0 }")
    P.Tick(0.5)
    lua.execute("AGPS_T = AGPS_T + 1")
    G.Update()
    assert (G.PadView()[0], G.PadView()[1]) == (x1, y1)
    lua.execute("AGPS_PAD.sticks = { { x = 0, y = 0 }, { x = 0, y = 0 } }")


def test_the_triggers_zoom_and_the_left_stick_press_recenters(pad):
    lua, ns = pad
    G, P, st = ns.GPS, ns.Pad, ns.settings.gps
    P.Apply()
    z0 = st.zoom
    _press(lua, "PADRTRIGGER", True)
    P.Tick(0.5)
    _press(lua, "PADRTRIGGER", False)
    assert st.zoom < z0  # (in)
    z1 = st.zoom
    _press(lua, "PADLTRIGGER", True)
    P.Tick(0.5)
    _press(lua, "PADLTRIGGER", False)
    assert st.zoom > z1  # (out)
    x, y = float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]"))
    G.LookAt(0, x + 300, y)
    assert G.IsFree()
    _press(lua, "PADLSTICK")
    assert not G.IsFree()


def test_the_legend_names_the_pads_own_buttons(pad):
    lua, ns = pad
    P = ns.Pad
    P.Apply()
    assert _plain(P.legend._text).startswith("A: Set Stop") and "X: Remove" in _plain(P.legend._text)
    lua.execute("AGPS_PAD.style = 'Shapes'")
    assert P.LegendText().startswith("Cross: Set Stop")


def test_nothing_of_blizzards_is_touched_by_the_controller_code():
    # (the game's controller UI: its focus and panels are secure; 1.2.2's world map, AzerothGPS#508's queue eye)
    text = "\n".join(line.split("--")[0] for p in ADDON.glob("*.lua")
                     for line in p.read_text(encoding="utf-8").splitlines())  # (the code, not its comments)
    for name in ("EnableGamePadButton", "EnableGamePadStick", "SetPreferredGamepadInteractTarget",
                 "GamePadSmartNavigation"):
        assert name not in text, name
    pad = (ADDON / "Pad.lua").read_text(encoding="utf-8")
    code = "\n".join(line.split("--")[0] for line in pad.splitlines())
    assert not re.search(r"SetOverrideBinding\w*\(\s*UIParent", code)
    assert not re.search(r"\b(WorldMapFrame|ShowUIPanel|HideUIPanel|QueueStatusButton)\b", code)
    assert "Pad.lua" in (ADDON / "AzerothGPS.toc").read_text(encoding="utf-8")


# --- Options > Controller: the map's pad buttons, each changeable (asked 2026-11-16: "For Options, add a new Controller
# section and make a keybinding list for each map control for the controller there")

def _fake_buttons(lua):
    # (the pad's buttons as the client gives them: a list of held states, ButtonIndexToBinding naming each one's key)
    lua.execute("""
      AGPS_KEYS = { "PAD1", "PAD2", "PAD3", "PAD4", "PADLSHOULDER", "PADRSHOULDER", "PADLTRIGGER", "PADRTRIGGER",
        "PADLSTICK", "PADRSTICK", "PADDUP", "PADDDOWN", "PADDLEFT", "PADDRIGHT", "PADBACK", "PADFORWARD" }
      AGPS_PAD.buttons = {}
      for i = 1, #AGPS_KEYS do AGPS_PAD.buttons[i] = false end
      C_GamePad.GetDeviceMappedState = function()
        return { labelStyle = AGPS_PAD.style, sticks = AGPS_PAD.sticks, buttons = AGPS_PAD.buttons }
      end
      C_GamePad.ButtonIndexToBinding = function(i) return AGPS_KEYS[i + 1] end
      AGPS_HOLD = function(key, on)
        for i, k in ipairs(AGPS_KEYS) do if k == key then AGPS_PAD.buttons[i] = on end end
      end
    """)


def _hold(lua, key, on=True):
    lua.eval("AGPS_HOLD")(key, on)


def test_the_controller_page_has_the_drawing_and_no_list_of_controls(pad):
    lua, ns = pad
    O, P = ns.Options, ns.Pad
    O.Show()
    assert O.pages.Controller is not None and O.padDiagram is not None
    # (the list under the drawing taken out: asked 2026-11-16, "with new layout don't need this bottom section")
    assert O.padRows is None and O.padReset is not None
    labels = {str(a): str(P.ActionLabel(a)) for a in ("select", "remove", "back", "zoomIn", "panUp", "recenter")}
    assert labels == {"select": "A", "remove": "X", "back": "B", "zoomIn": "RT", "panUp": "D-pad up",
                      "recenter": "Left stick press"}
    # (the controller options moved here from General: on this page's controls)
    assert {c.key: c.page for c in O.settingControls.values() if c.key in ("padControl", "padLegend")} == \
        {"padControl": "Controller", "padLegend": "Controller"}
    lua.execute("AGPS_PAD.style = 'Shapes'")
    assert str(P.ActionLabel("select")) == "Cross"


def _diagram_label(O, key):
    return next(b for b in O.padDiagram.labels.values() if b.key == key)


def test_change_takes_the_next_button_pressed_and_b_held_or_escape_cancels(pad):
    lua, ns = pad
    O, P = ns.Options, ns.Pad
    _fake_buttons(lua)
    O.Show()
    cap = lua.eval("function(P) AGPS_WHY = nil P.BeginCapture('remove', function(r, _, why) AGPS_WHY = why end) end")
    try:
        _hold(lua, "PAD1")  # (held as the capture starts: not taken till pressed again)
        cap(P)
        assert P.Capturing() == "remove"
        P.CaptureTick()
        assert P.Capturing() == "remove"
        _hold(lua, "PAD1", False)
        _hold(lua, "PADFORWARD")
        P.CaptureTick()
        assert P.Capturing() is None and P.Key("remove") == "PADFORWARD"
        assert ns.settings.gps.padBinds.remove == "PADFORWARD"  # (saved in the profile's settings)
        assert str(P.ActionLabel("remove")) == "Start"
        _hold(lua, "PADFORWARD", False)
        # B held cancels (a tap of it is B: asked 2026-11-16, "can't bind B because it cancels the input"), and
        # Escape does
        cap(P)
        _hold(lua, "PAD2")
        P.CaptureTick()
        assert P.Capturing() == "remove"  # (not yet: a tap or a hold)
        lua.execute("AGPS_T = AGPS_T + %s" % (P.CANCEL_HOLD + 0.1))
        P.CaptureTick()
        _hold(lua, "PAD2", False)
        assert P.Capturing() is None and P.Key("remove") == "PADFORWARD" and "Canceled" in str(lua.eval("AGPS_WHY"))
        cap(P)
        P.captureFrame._scripts.OnKeyDown(P.captureFrame, "ESCAPE")
        assert P.Capturing() is None and P.Key("remove") == "PADFORWARD"
        # (and nothing pressed for long enough: given up)
        cap(P)
        lua.execute("AGPS_T = AGPS_T + %d" % (int(P.CAPTURE_SECONDS) + 1))
        P.CaptureTick()
        assert P.Capturing() is None
    finally:
        P.ResetBinds()


def test_a_button_another_control_has_is_refused_and_back_always_has_one(pad):
    lua, ns = pad
    P = ns.Pad
    ok, why = P.SetBind("remove", "PAD1")
    assert ok is False and "Already used" in str(why) and "Set a stop" in str(why)
    assert P.Key("remove") == "PAD3"
    ok, why = P.SetBind("back", None)
    assert ok is False and P.Key("back") == "PAD2"
    assert P.SetBind("yes", "PAD1") is True  # (the stop's and Yes's: one button, as by default)
    assert P.SetBind("zoomIn", "PADRSHOULDER") is True
    ok, why = P.SetBind("toggle", "PADRSHOULDER")  # (the game's Show/Hide key too: not on a map control's button)
    assert ok is False
    P.ResetBinds()


def test_reset_puts_the_defaults_back(pad):
    lua, ns = pad
    O, P = ns.Options, ns.Pad
    O.Show()
    assert P.SetBind("remove", "PADFORWARD") is True and P.SetBind("recenter", "PADRSHOULDER") is True
    O.padReset._scripts.OnClick(O.padReset)
    assert P.Key("remove") == "PAD3" and P.Key("recenter") == "PADLSTICK"
    assert ns.settings.gps.padBinds is None


def test_the_saved_buttons_are_the_ones_bound_and_the_legend_follows(pad):
    lua, ns = pad
    G, P = ns.GPS, ns.Pad
    try:
        P.Apply()
        assert _bound(lua)["PAD3"] == "AzerothGPSPad_PAD3"
        assert P.SetBind("remove", "PADFORWARD") is True
        b = _bound(lua)
        assert "PAD3" not in b and b["PADFORWARD"] == "AzerothGPSPad_PADFORWARD"  # (bound again at once, the map open)
        assert "Start: Remove" in _plain(P.legend._text)
        # pressing it removes the stop under the reticle, as X did
        x, y = float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]"))
        ns.Nav.SetStops(lua.eval("{ { x = %r, y = %r, cont = 0, name = 'Spot' } }" % (x, y)), False, "red")
        G.Follow()
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        if P.StopAt() is not None:
            assert _press(lua, "PADFORWARD") and G.removeAsk._shown
        assert P.SetBind("zoomIn", "PADRSHOULDER") is True and "LT/RB: Zoom" in _plain(P.legend._text)
    finally:
        P.ResetBinds()
        ns.Nav.Clear()
    assert "X: Remove" in _plain(P.legend._text) and _bound(lua)["PAD3"] == "AzerothGPSPad_PAD3"


def test_a_change_in_a_fight_waits_for_its_end(pad):
    lua, ns = pad
    P = ns.Pad
    P.Apply()
    _event(lua, "PLAYER_REGEN_DISABLED")
    lua.execute("AGPS_LOCK = true")  # (the lockdown: any binding call would be blocked)
    try:
        r, why = P.SetBind("remove", "PADFORWARD")
        assert r == "wait" and "after the fight" in str(why)
        assert P.Key("remove") == "PAD3" and ns.settings.gps.padBinds is None
        r = P.ResetBinds()
        assert (r[0] if isinstance(r, tuple) else r) == "wait"
        assert P.BeginCapture("remove") is False  # (no capture in a fight)
    finally:
        lua.execute("AGPS_LOCK = false")
    P.pending.reset = None
    _event(lua, "PLAYER_REGEN_ENABLED")
    assert P.Key("remove") == "PADFORWARD"  # (done once the fight's over)
    P.ResetBinds()


def _spy(lua):
    # (the controls' own effects, counted: a stop at the reticle, recentering)
    lua.execute("""
      AGPS_COUNT = { stop = 0, follow = 0 }
      AGPS_REAL = AGPS_REAL or { add = AGPS_NS.GPS.AddPending, follow = AGPS_NS.GPS.Follow, icon = AGPS_NS.Pad.IconAt }
      AGPS_NS.Pad.IconAt = function() return nil end -- (no icon under the reticle: A's is a stop)
      AGPS_NS.GPS.AddPending = function() AGPS_COUNT.stop = AGPS_COUNT.stop + 1 end
      AGPS_NS.GPS.Follow = function() AGPS_COUNT.follow = AGPS_COUNT.follow + 1 end
    """)
    return lua.eval("AGPS_COUNT")


def _unspy(lua):
    lua.execute("if AGPS_REAL then AGPS_NS.GPS.AddPending, AGPS_NS.GPS.Follow = AGPS_REAL.add, AGPS_REAL.follow "
                "AGPS_NS.Pad.IconAt = AGPS_REAL.icon end AGPS_REAL = nil")


def _frames(lua, n=30):
    # (the frames' own OnUpdates, as the client runs them: the drawer slides out)
    lua.execute("""for _ = 1, %d do
      AGPS_T = AGPS_T + 0.05
      for _, w in ipairs(AGPS_WIDGETS) do
        local f = w._scripts and w._scripts.OnUpdate
        if f and w._shown then pcall(f, w, 0.05) end
      end
    end""" % n)


def test_a_pair_fires_its_own_control_and_not_the_plain_one(pad):
    # (asked 2026-11-16: "need to support 2 selections like LT + A") LT + A recenters, A alone still sets a stop
    lua, ns = pad
    P = ns.Pad
    _fake_buttons(lua)
    assert P.SetBind("recenter", "PADLTRIGGER+PAD1") is True
    P.Apply()
    c = _spy(lua)
    try:
        _hold(lua, "PADLTRIGGER")
        _press(lua, "PAD1")
        _press(lua, "PAD1", False)
        assert c.follow == 1 and c.stop == 0  # (the pair's, not A's)
        _hold(lua, "PADLTRIGGER", False)
        _press(lua, "PAD1")
        _press(lua, "PAD1", False)
        assert c.follow == 1 and c.stop == 1  # (A alone: its own)
        assert "LT + A: Recenter" in P.LegendText() and P.BindLabel("PADLTRIGGER+PAD1") == "LT + A"
    finally:
        _unspy(lua)


def test_a_modifier_used_in_a_pair_waits_before_its_own_hold(pad):
    # LT zooms out while held, and is LT + A's modifier: its zoom only after MOD_HOLD_DELAY alone, none once a pair used it
    lua, ns = pad
    P, st = ns.Pad, ns.settings.gps
    _fake_buttons(lua)
    assert P.SetBind("recenter", "PADLTRIGGER+PAD1") is True
    P.Apply()
    c = _spy(lua)
    try:
        z0 = st.zoom
        _hold(lua, "PADLTRIGGER")
        _press(lua, "PADLTRIGGER")
        P.Tick(0.1)
        assert st.zoom == z0  # (not yet: it may be a pair's)
        _press(lua, "PAD1")
        _press(lua, "PAD1", False)
        lua.execute("AGPS_T = AGPS_T + 1")
        P.Tick(0.5)
        assert st.zoom == z0 and c.follow == 1  # (a pair: its own hold let go)
        _hold(lua, "PADLTRIGGER", False)
        _press(lua, "PADLTRIGGER", False)
        _hold(lua, "PADLTRIGGER")
        _press(lua, "PADLTRIGGER")
        lua.execute("AGPS_T = AGPS_T + 0.5")
        P.Tick(0.5)
        assert st.zoom > z0  # (held alone a moment: zooms out)
        _press(lua, "PADLTRIGGER", False)
    finally:
        _unspy(lua)


def test_change_records_a_pair_or_a_modifier_alone(pad):
    lua, ns = pad
    P = ns.Pad
    _fake_buttons(lua)
    P.BeginCapture("recenter")
    _hold(lua, "PADLTRIGGER")
    P.CaptureTick()
    assert P.Capturing() == "recenter"  # (a modifier: waiting for the other button)
    _hold(lua, "PAD3")
    P.CaptureTick()
    assert P.Capturing() is None and P.Key("recenter") == "PADLTRIGGER+PAD3"
    _hold(lua, "PAD3", False)
    _hold(lua, "PADLTRIGGER", False)
    P.BeginCapture("recenter")
    _hold(lua, "PADRSHOULDER")
    P.CaptureTick()
    _hold(lua, "PADRSHOULDER", False)
    P.CaptureTick()
    assert P.Capturing() is None and P.Key("recenter") == "PADRSHOULDER"  # (let go alone: itself)


def test_pairs_are_told_apart_from_their_button_alone(pad):
    lua, ns = pad
    P = ns.Pad
    assert P.SetBind("recenter", "PADLTRIGGER+PAD1") is True  # (A alone is the stop's: another binding)
    assert P.BindLabel(P.Key("recenter")) == "LT + A" and P.Key("select") == "PAD1"
    r, why = P.SetBind("remove", "PADLTRIGGER+PAD1")
    assert r is False and "Recenter" in str(why)
    r, why = P.SetBind("toggle", "PADLTRIGGER+PAD1")  # (the game's own key: one button)
    assert r is False


def test_the_map_menu_button_opens_and_closes_the_menu_and_the_pan_moves_its_focus(pad):
    # (asked 2026-11-16: "need a map menu button and when it opens the map pan controls navigate the buttons, Set a stop
    # button selects the map icon. Pressing the map menu controller button again closes it")
    lua, ns = pad
    same = lua.eval("rawequal")
    G, P = ns.GPS, ns.Pad
    P.Apply()
    assert P.Key("menu") == "PAD4" and _bound(lua)["PAD4"]
    _press(lua, "PAD4")
    assert G.mapMenu._shown and P.MenuOpen()
    G.LayoutQuick()  # (the menu's OnShow hook, which the stand-in game doesn't run)
    _frames(lua)
    P.Apply()
    assert not P.reticle._shown and "Close Menu" in _plain(P.legend._text)
    order = list(P.MenuButtons().values())
    assert len(order) >= 2 and same(P.focus, order[0]) and P.ring._shown
    # (up and down along the column only, right and left along the row only; across: the other's first. Asked
    # 2026-11-16: "Up/Down is only the vertical column and left/right is only the bottom right row")
    col, row = P.MenuParts()
    col, row = list(col.values()), list(row.values())
    assert len(col) >= 2 and len(row) >= 2 and same(order[0], col[0])
    _press(lua, "PADDUP")
    assert same(P.focus, col[1])
    _press(lua, "PADDRIGHT")  # (halfway up the column: the row's first)
    assert same(P.focus, row[0])
    _press(lua, "PADDRIGHT")
    assert same(P.focus, row[1])
    _press(lua, "PADDLEFT")
    _press(lua, "PADDLEFT")
    assert same(P.focus, row[-1])  # (round to the row's last)
    _press(lua, "PADDUP")  # (from the row: the column's first)
    assert same(P.focus, col[0])
    _press(lua, "PADDDOWN")
    assert same(P.focus, col[-1])  # (round to the column's last)
    _press(lua, "PAD4")
    assert not G.mapMenu._shown and P.focus is None and P.reticle._shown


def test_the_mouse_used_takes_the_map_menus_focus_away(pad):
    # (asked 2026-11-16: "if the player starts using the mouse again stop the map menu highlighting for a selection,
    # its fighting the mouse selection and shows tooltips")
    lua, ns = pad
    same = lua.eval("rawequal")
    G, P = ns.GPS, ns.Pad
    P.Apply()
    _press(lua, "PAD4")
    G.LayoutQuick()
    _frames(lua)
    P.Apply()
    order = list(P.MenuButtons().values())
    assert same(P.focus, order[0]) and P.ring._shown
    P.SawInput(False)  # (the mouse clicked)
    assert P.focus is None and not P.ring._shown
    P.Tick(0.1)  # (and not put back while the mouse is in use)
    assert P.focus is None
    _press(lua, "PADDUP")  # (the controller again: its focus back)
    P.Tick(0.1)
    assert P.focus is not None and P.ring._shown
    _press(lua, "PAD4")


def test_in_the_menu_a_presses_the_focused_button_and_b_backs_out(pad):
    lua, ns = pad
    same = lua.eval("rawequal")
    G, P = ns.GPS, ns.Pad
    P.Apply()
    _press(lua, "PAD4")
    G.LayoutQuick()
    _frames(lua)
    grp = next((g for g in G.groupOf.values() if g.button._shown and not g.keep), None)
    assert grp is not None
    P.SetFocus(grp.button)
    _press(lua, "PAD1")  # (a group: its buttons out, the focus on its first)
    assert lua.eval("rawequal")(G.OpenGroupSlot(), grp)
    members = list(P.MenuButtons().values())
    assert members and same(P.focus, members[0]) and not same(P.focus, grp.button)
    _press(lua, "PAD2")  # (back: the group shut, the focus on it)
    assert G.OpenGroupSlot() is None and same(P.focus, grp.button) and G.mapMenu._shown
    _press(lua, "PAD2")  # (then the menu)
    assert not G.mapMenu._shown and ns.settings.gps.shown


def test_the_map_pans_and_stops_wait_while_the_menu_is_open(pad):
    lua, ns = pad
    G, P = ns.GPS, ns.Pad
    P.Apply()
    _press(lua, "PAD4")
    G.LayoutQuick()
    _frames(lua)
    c = _spy(lua)
    try:
        v0 = (G.PadView()[0], G.PadView()[1])
        _press(lua, "PADDRIGHT", True)
        P.Tick(0.5)
        _press(lua, "PADDRIGHT", False)
        assert (G.PadView()[0], G.PadView()[1]) == v0 and not P.held.panRight
        P.SetFocus(None)
        _press(lua, "PAD1")
        assert c.stop == 0  # (A in the menu: a button, never a stop)
    finally:
        _unspy(lua)


def test_held_controls_tap_or_hold_on_one_button(pad):
    # (asked 2026-11-16: "support a 'hold' keybinding, holding a key more than 2 seconds ... A could be 1 control and A
    # (hold) would be another. Defined by a check box next to the controller key binding")
    lua, ns = pad
    P = ns.Pad
    assert P.SetHold("recenter", True) is True
    assert P.SetBind("recenter", "PAD1") is True  # (A held: another control than A)
    P.Apply()
    c = _spy(lua)
    try:
        _press(lua, "PAD1")
        assert c.stop == 0  # (A has a held control: its other one waits for the let go)
        _press(lua, "PAD1", False)
        assert c.stop == 1 and c.follow == 0
        _press(lua, "PAD1")
        lua.execute("AGPS_T = AGPS_T + 2.1")
        P.HoldTick()
        assert c.follow == 1 and c.stop == 1  # (held 2 seconds: the held control, as it's held)
        lua.execute("AGPS_T = AGPS_T + 3")
        P.HoldTick()
        _press(lua, "PAD1", False)
        assert c.follow == 1 and c.stop == 1  # (once; letting go does nothing more)
        assert "A (hold): Recenter" in P.LegendText()
        # (a button with no held control: at once, as ever)
        _press(lua, "PAD3")
        assert P.holds["PAD3"] is None
    finally:
        _unspy(lua)


def test_the_hold_box_is_saved_used_and_told_apart(pad):
    lua, ns = pad
    P, st = ns.Pad, ns.settings.gps
    assert P.SetHold("recenter", True) is True
    assert st.padHold.recenter is True and P.IsHold("recenter")
    # (the pan and zoom controls, done while held: refused)
    r, _ = P.SetHold("zoomIn", True)
    assert r is False
    # (duplicates by button and hold: A held is recenter's, so remove can't be A held, but A alone is the stop's)
    assert P.SetBind("recenter", "PAD1") is True
    assert P.SetHold("remove", True) is True
    r, why = P.SetBind("remove", "PAD1")
    assert r is False and "Recenter" in str(why)


def _line_ids(ln):
    return [str(i) for i in ln.ids.values()] if ln.ids else None


def test_a_buttons_window_has_its_control_then_a_line_a_combination(pad):
    """(asked 2026-11-16, then with a sketch: "First row should always be shown. Drop down is action and one selection
    at the top is "Unassigned" where it does nothing. Next row, left side, RED is a drop down of the modifier icons
    (LT/RT/etc) ORANGE is just the button icon ... GREEN is a check box (off by default) with Hold beside it in yellow
    color. All of these are greyed out while the action drop down next to it is set to Unassigned. IF the player selects
    another action to bind here they can now make choices on the left and another row is added for the next modifier
    option." Half again the old window's size, a scroll bar when long.)"""
    lua, ns = pad
    O, P = ns.Options, ns.Pad
    O.Show()
    try:
        # the button clicked on the drawing: its window (Recenter: the left stick press)
        b = _diagram_label(O, "PADLSTICK")
        b._scripts.OnClick(b)
        f = O.padButton
        assert f._shown and f.key == "PADLSTICK" and (f._w, f._h) == (510, 300)
        # (at Options' strata, under the game's menus (FULLSCREEN_DIALOG): nothing of the game's touched to be over it)
        assert str(f.GetFrameStrata(f)) == "DIALOG" and f.base.OnMenuUp is None
        # (each line's control list ends inside the lines' scroll: not cut off, asked 2026-11-16)
        assert 4 + O.BUTTON_ACTION_X + O.BUTTON_ACTION_W <= O.BUTTON_W - 12 - 30
        assert f.base.padGet() == "recenter" and f.base.agpsOn and str(f.baseLabel._text) == "Pressed"
        # the list: Unassigned first; hovering a control says what it does, and its macro
        ch = O.ActionChoices()
        assert ch[1].value == "none" and str(ch[1].text) == "Not bound"
        tips = {str(o.value): [str(t) for t in o.tip.values()] for o in ch.values()}
        assert tips["clear"] == ["Clears the whole route.", "Macro: /agps clear"]
        assert tips["select"][0].startswith("Sets a stop at the crosshair") and "Answers Yes" in tips["select"][1]
        # (the stop and Yes are one, Select; Back is Back: asked 2026-11-16)
        texts = {str(o.value): str(o.text) for o in ch.values()}
        assert "yes" not in texts and texts["select"] == "Set Stop" and texts["back"] == "Back"
        # one more line, Unassigned: on the first combination free (LT, no Hold), its left side greyed
        assert len(f.shown) == 1 and f.shown[1].empty
        ln = f.lines[1]
        assert ln.action.padGet() == "none" and ln.action.agpsOn
        assert not ln.mod.agpsOn and not ln.hold.agpsOn and not ln.hold._checked
        assert ln.mod.padGet() == "PADLTRIGGER" and str(ln.plus._text) == "+"
        assert str(ln.icon._tex).endswith("LStickPress_20.tga")
        # (greyed: nothing moves)
        assert O.ButtonCombo(ln, "PADRTRIGGER", False) is False and P.Key("clear") is None
        def apply():
            f.apply._scripts.OnClick(f.apply)
        # nothing changed yet: Apply grayed (asked 2026-11-16, "Apply is grey until change is made and that change is
        # only applied when this is clicked to prevent accidentally unassigning another key")
        assert not f.dirty and f.apply._enabled is False
        # a control picked: on LT + the stick press in the window, the left side now open, a new line for the next;
        # nothing changed till Apply
        ln.action.padSet("clear")
        assert P.Key("clear") is None and f.dirty and f.apply._enabled is not False
        assert ln.mod.agpsOn and ln.hold.agpsOn and not f.shown[1].empty
        assert len(f.shown) == 2 and f.shown[2].empty and f.lines[2].mod.padGet() == "PADRTRIGGER"
        apply()
        assert P.Key("clear") == "PADLTRIGGER+PADLSTICK" and not P.IsHold("clear") and not f.dirty
        # its modifier's icons in the list; one another line has, greyed
        mods = {str(o.value): o for o in O.ModChoices(f.lines[2]).values()}
        assert "LT_16.tga" in str(mods["PADLTRIGGER"].text) and mods["PADLTRIGGER"].off
        assert not mods["PADRTRIGGER"].off and "PADLSTICK" not in mods and mods[""].off  # (no modifier: Hold only)
        # Hold ticked, then no modifier: the stick press held, once applied
        ln.hold.SetChecked(ln.hold, True)
        ln.hold._scripts.OnClick(ln.hold)
        ln = next(x for x in f.lines.values() if x.id == "clear")
        ln.mod.padSet("")
        assert P.Key("clear") == "PADLTRIGGER+PADLSTICK" and not P.IsHold("clear")
        apply()
        assert P.Key("clear") == "PADLSTICK" and P.IsHold("clear")
        ln = next(x for x in f.lines.values() if x.id == "clear")
        # neither: refused
        ln.hold.SetChecked(ln.hold, False)
        ln.hold._scripts.OnClick(ln.hold)
        assert not f.dirty and "Pick LT, RT, LB or RB, or Hold" in str(f.note._text)
        # a pan control can't be held: refused at once, nothing changed
        ln.action.padSet("panUp")
        assert ln.id == "clear" and "can't be a hold" in str(f.note._text)
        # the pressed alone control changed: the note says what comes off where; applied, the one before off it
        f.base.padSet("options")
        assert P.Key("options") == "PADRSTICK" and P.Key("recenter") == "PADLSTICK"
        assert "Options comes off" in str(f.note._text) and "Recenter on you will have no button." in str(f.note._text)
        apply()
        assert P.Key("options") == "PADLSTICK" and P.Key("recenter") is None
        # Not bound: off the button, its line gone
        ln = next(x for x in f.lines.values() if x.id == "clear")
        n = len(f.shown)
        ln.action.padSet("none")
        apply()
        assert P.Key("clear") is None and len(f.shown) == n - 1
        # Select on a line: Yes on a question with it
        ln = f.lines[1]
        ln.action.padSet("select")
        apply()
        assert P.Key("select") == P.Key("yes") and P.IsHold("select") == P.IsHold("yes")
        assert next(x for x in f.lines.values() if x.id == "select") is not None
        # Done closes, a change not applied left as it was
        ln = next(x for x in f.lines.values() if x.id == "select")
        ln.action.padSet("menu")
        f.done._scripts.OnClick(f.done)
        assert not f._shown and P.Key("menu") == "PAD4"
        # a trigger or bumper's own window: its first line only (asked 2026-11-16, "Shouldn't allow LT itself to + with
        # a modifier. All modifiers only show the top row")
        O.PadButton("PADLTRIGGER")
        assert len(f.shown) == 0 and len(O.ButtonCombos("PADLTRIGGER")) == 0 and f.base.padGet() == "zoomOut"
        # Back always has a button
        O.PadButton("PAD2")
        f.base.padSet("none")
        apply()
        assert P.Key("back") == "PAD2" and "Back can't be left" in str(f.note._text)
        # all nine combinations used: no Unassigned line
        for bind, hold, a in (("PAD3", True, "clear"), ("PADLTRIGGER+PAD3", False, "panUp"),
                              ("PADRTRIGGER+PAD3", False, "panDown"), ("PADLSHOULDER+PAD3", False, "panLeft"),
                              ("PADRSHOULDER+PAD3", False, "panRight"), ("PADLTRIGGER+PAD3", True, "recenter"),
                              ("PADRTRIGGER+PAD3", True, "menu"), ("PADLSHOULDER+PAD3", True, "options"),
                              ("PADRSHOULDER+PAD3", True, "select")):
            assert P.Assign(a, bind, hold) is True, a
        O.PadButton("PAD3")
        assert len(f.shown) == 9 and not any(i.empty for i in f.shown.values())
        f.Hide(f)
    finally:
        P.ResetBinds()


def test_a_hold_change_in_a_fight_waits(pad):
    lua, ns = pad
    P = ns.Pad
    lua.execute("AGPS_LOCK = true")
    ns.inCombat = True
    try:
        r, _ = P.SetHold("recenter", True)
        assert r == "wait" and not P.IsHold("recenter")
    finally:
        lua.execute("AGPS_LOCK = false")
        ns.inCombat = None
    _event(lua, "PLAYER_REGEN_ENABLED")
    assert P.IsHold("recenter")


# --- Clear Route, the map menu's pair and hold, the controls as macros (asked 2026-11-16: "Need a clear route key
# binding for controller, also map menu needs to support hold and combo buttons. Also if the Player could make a macro
# instead and put that as a controller binding to do the same function, add it as a indicator tool tip on that like
# that tells them what the macro is to do the same control")

def _a_route(lua):
    lua.execute("AGPS_NS.Nav.stops[1] = { x = -600, y = -4180, cont = 1, name = 'A' }")


def test_clear_route_is_a_control_with_no_button_until_one_is_given(pad):
    lua, ns = pad
    O, P = ns.Options, ns.Pad
    assert P.Action("clear") is not None and P.Key("clear") is None
    O.Show()
    O.Refresh()
    assert str(P.ActionLabel("clear")) == "Not bound"
    _fake_buttons(lua)
    assert P.SetBind("clear", "PADLSHOULDER+PAD1") is True
    lua.execute("AzerothGPSOptions:Hide()")  # (Options open: the pad is its own, PadOptions.lua)
    P.Apply()
    c = _spy(lua)
    try:
        _a_route(lua)
        _hold(lua, "PADLSHOULDER")
        _press(lua, "PAD1")
        _press(lua, "PAD1", False)
        assert len(ns.Nav.stops) == 0 and c.follow == 0 and c.stop == 0  # (gone, the view left where it is: asked 2026-11-16)
        _press(lua, "PAD1")
        _press(lua, "PAD1", False)
        assert c.follow == 0  # (no route: nothing)
        assert "LB + A" in str(P.ActionLabel("clear"))
    finally:
        _unspy(lua)


def test_the_map_menu_control_takes_a_pair(pad):
    lua, ns = pad
    G, P = ns.GPS, ns.Pad
    _fake_buttons(lua)
    assert P.SetBind("menu", "PADLSHOULDER+PAD4") is True
    P.Apply()
    _press(lua, "PAD4")
    _press(lua, "PAD4", False)
    assert not G.mapMenu._shown  # (Y alone: not the menu's now)
    _hold(lua, "PADLSHOULDER")
    _press(lua, "PAD4")
    _press(lua, "PAD4", False)
    assert G.mapMenu._shown and P.MenuOpen()
    G.LayoutQuick()
    P.Tick(0.1)
    P.Apply()
    assert "LB + Y: Close Menu" in _plain(P.legend._text)
    _press(lua, "PAD4")
    _press(lua, "PAD4", False)
    assert not G.mapMenu._shown


def test_the_map_menu_control_takes_the_hold_box(pad):
    lua, ns = pad
    G, P = ns.GPS, ns.Pad
    _fake_buttons(lua)
    assert P.CanHold("menu") and P.SetHold("menu", True) is True
    P.Apply()
    _hold(lua, "PAD4")
    _press(lua, "PAD4")
    assert not G.mapMenu._shown  # (not yet: held 2 seconds)
    lua.execute("AGPS_T = AGPS_T + 2.1")
    P.HoldTick()
    assert G.mapMenu._shown
    _hold(lua, "PAD4", False)
    _press(lua, "PAD4", False)
    G.LayoutQuick()
    P.Tick(0.1)
    P.Apply()
    assert "Y (hold): Close Menu" in _plain(P.legend._text)
    _hold(lua, "PAD4")
    _press(lua, "PAD4")
    _hold(lua, "PAD4", False)
    _press(lua, "PAD4", False)
    assert G.mapMenu._shown  # (only pressed: the menu stays)
    _hold(lua, "PAD4")
    _press(lua, "PAD4")
    lua.execute("AGPS_T = AGPS_T + 2.1")
    P.HoldTick()
    assert not G.mapMenu._shown  # (held again: closed)
    _hold(lua, "PAD4", False)
    _press(lua, "PAD4", False)


def _slash(lua, macro):
    assert macro.startswith("/agps ")
    lua.eval("SlashCmdList.AZEROTHGPS")(macro[len("/agps "):])


def test_every_controls_macro_does_that_control(pad):
    lua, ns = pad
    G, P, st = ns.GPS, ns.Pad, ns.settings.gps
    M = {str(k): str(v) for k, v in P.MACROS.items()}
    assert set(M) == {str(a[1]) for a in P.ACTIONS.values()}  # (every control has one)
    P.Apply()
    c = _spy(lua)
    lua.execute("""
      AGPS_DID = {}
      AGPS_REAL.stopAt = AGPS_NS.Pad.StopAt
      AGPS_NS.Pad.StopAt = function() return { stopIndex = 1 } end
      AGPS_REAL.ask = AGPS_NS.GPS.AskRemove
      AGPS_NS.GPS.AskRemove = function() AGPS_DID.remove = true end
      AGPS_REAL.tog = AzerothGPS_ToggleMap
      AzerothGPS_ToggleMap = function() AGPS_DID.toggleMap = (AGPS_DID.toggleMap or 0) + 1 end
    """)
    try:
        _slash(lua, M["select"])
        assert c.stop == 1
        _slash(lua, M["remove"])
        assert lua.eval("AGPS_DID.remove")
        _slash(lua, M["recenter"])
        assert c.follow == 1
        _a_route(lua)
        _slash(lua, M["clear"])
        assert len(ns.Nav.stops) == 0 and c.follow == 1  # (/agps clear: the view left where it is, asked 2026-11-19)
        _slash(lua, M["back"])
        assert lua.eval("AGPS_DID.toggleMap") == 1  # (nothing open: the map closed, as B)
        lua.execute("""
          AGPS_Q = CreateFrame("Frame") AGPS_Q:Show()
          AGPS_Q.yes = CreateFrame("Button") AGPS_Q.yes:SetScript("OnClick", function() AGPS_DID.yes = true end)
          AGPS_Q.no = CreateFrame("Button")
          AGPS_NS.lastAsk = AGPS_Q
        """)
        _slash(lua, M["yes"])
        assert lua.eval("AGPS_DID.yes")
        lua.execute("AGPS_NS.lastAsk = nil")
        z = st.zoom
        _slash(lua, M["zoomIn"])
        assert st.zoom < z  # (one step in: fewer yards)
        z = st.zoom
        _slash(lua, M["zoomOut"])
        assert st.zoom > z
        for d, (sx, sy) in {"panRight": (1, 0), "panLeft": (-1, 0), "panUp": (0, 1), "panDown": (0, -1)}.items():
            G.Update()
            x0, y0 = G.PadView()[0], G.PadView()[1]
            _slash(lua, M[d])
            G.Update()
            x1, y1 = G.PadView()[0], G.PadView()[1]
            assert (x1, y1) != (x0, y0), d
        _slash(lua, M["menu"])
        assert G.mapMenu._shown and P.MenuOpen()
        _slash(lua, M["menu"])
        assert not G.mapMenu._shown
        P.Clear()  # (no pad in use: the menu still opens and closes)
        _slash(lua, M["menu"])
        assert G.mapMenu._shown and not P.reticle._shown
        _slash(lua, M["menu"])
        assert not G.mapMenu._shown
        shown = st.shown
        _slash(lua, M["toggle"])
        assert st.shown != shown
    finally:
        lua.execute("""
          AGPS_NS.GPS.AskRemove = AGPS_REAL.ask
          AzerothGPS_ToggleMap = AGPS_REAL.tog
          AGPS_NS.Pad.StopAt = AGPS_REAL.stopAt
        """)
        _unspy(lua)


def test_each_controls_macro_tag_tells_its_macro(pad):
    lua, ns = pad
    O, P = ns.Options, ns.Pad
    O.Show()
    lua.execute("AGPS_TIPR = { s = GameTooltip.SetText, a = GameTooltip.AddLine } "
                "AGPS_TIP = {} GameTooltip.SetText = function(_, t) AGPS_TIP[#AGPS_TIP + 1] = t end "
                "GameTooltip.AddLine = function(_, t) AGPS_TIP[#AGPS_TIP + 1] = t end")
    try:
        def tip(id):
            # (on hover in a button window's list of controls: asked 2026-11-16, "hovering this in the dropdown
            # explains the action")
            o = next(o for o in O.ActionChoices().values() if o.value == id)
            return ([str(x) for x in o.tip.values() if str(x).startswith("Macro:")]
                    + [str(x) for x in (P.MacroTip(id) or {}).values()][1:])
        t = tip("clear")
        assert t[0] == "Macro: /agps clear" and "action bar" in t[1] and "Key Bindings" in t[1]
        t = tip("zoomIn")
        assert t[0] == "Macro: /agps zoom in" and any("one step a press" in x for x in t)
        assert tip("menu")[0] == "Macro: /agps menu" and tip("select")[0] == "Macro: /agps pad select"
    finally:
        lua.execute("GameTooltip.SetText, GameTooltip.AddLine = AGPS_TIPR.s, AGPS_TIPR.a")



# --- Options with a controller (PadOptions.lua; asked 2026-11-16, Blizzard's settings with Gamepad UI on shown: "can
# we do this in our options?"): our own highlight and bindings, never the game's gamepad focus

def _opts(lua, ns):
    O, P = ns.Options, ns.Pad
    O.Show()
    O.Refresh()
    P.Apply()
    return O, P, P.Opt


def _is(lua, a, b):
    return bool(lua.eval("rawequal")(a, b))


def _page(O, name):
    return O.pages[name].index


def _control(ns, key):
    return next(c.control for c in ns.Options.settingControls.values() if c.key == key)


def test_the_page_list_moves_and_the_bumpers_change_the_page(pad):
    lua, ns = pad
    O, P, PO = _opts(lua, ns)
    b = _bound(lua)
    assert {k for k, v in b.items() if v.startswith("AzerothGPSPadOpt_")} == {
        "PADDUP", "PADDDOWN", "PADDLEFT", "PADDRIGHT", "PAD1", "PAD2", "PAD3", "PADLSHOULDER", "PADRSHOULDER"}
    assert "PADLSTICK" not in b  # (the map's own: off while Options has the pad)
    cur = O.CurrentPage()
    assert PO.side == "list" and _is(lua, PO.focus, O.tabs[cur]) and PO.bar._shown
    assert "LB/RB: Page" in str(PO.hint._text) and PO.hint._shown
    _press(lua, "PADDDOWN")
    assert _is(lua, PO.focus, O.tabs[cur + 1]) and O.CurrentPage() == cur  # (moved, not opened)
    _press(lua, "PAD1")
    assert O.CurrentPage() == cur + 1 and lua.eval("rawequal")(PO.arrow._parent, O.tabs[cur + 1]) and PO.arrow._shown
    _press(lua, "PADRSHOULDER")
    assert O.CurrentPage() == cur + 2 and _is(lua, PO.focus, O.tabs[cur + 2])
    _press(lua, "PADLSHOULDER")
    _press(lua, "PADLSHOULDER")
    assert O.CurrentPage() == cur and _is(lua, PO.focus, O.tabs[cur])


def test_into_a_page_and_back_ticking_a_checkbox(pad):
    lua, ns = pad
    O, P, PO = _opts(lua, ns)
    st = ns.settings.gps
    O.ShowPage("Controller")
    PO.Refocus()
    _press(lua, "PADDRIGHT")
    rows = PO.Rows()
    assert PO.side == "page" and _is(lua, PO.focus, rows[1][1])  # (its first: Controller support)
    _press(lua, "PADDDOWN")  # (Show the controller's buttons on the map)
    assert _is(lua, PO.focus, rows[2][1]) and st.padLegend is not False
    _press(lua, "PAD1")
    assert st.padLegend is False and _is(lua, PO.focus, rows[2][1])
    _press(lua, "PAD1")
    assert st.padLegend is True
    _press(lua, "PADDLEFT")  # (the first column: back to the list)
    assert PO.side == "list" and _is(lua, PO.focus, O.tabs[_page(O, "Controller")])


def test_a_slider_steps_and_a_dropdown_opens_picks_and_closes(pad):
    lua, ns = pad
    O, P, PO = _opts(lua, ns)
    st = ns.settings.gps
    # (map redraws a second, the slider here before, is radio buttons since 2026-11-19; Tools' Map Editing slider went
    # with the map editor in 1.3.14: Routing's road tolerance)
    O.ShowPage("Routing")
    hz = _control(ns, "roadTolerance")
    assert PO.FocusOn(hz.slider)
    v = st.roadTolerance or 0
    _press(lua, "PADDRIGHT")
    assert st.roadTolerance == v + 1
    _press(lua, "PADDLEFT")
    _press(lua, "PADDLEFT")
    assert st.roadTolerance == v - 1 and PO.side == "page"  # (a slider's left: a step, never the list)
    st.roadTolerance = v
    O.ShowPage("General")
    dd = _control(ns, "distanceUnits")
    assert PO.FocusOn(dd)
    st.distanceUnits = "yards"
    _press(lua, "PADDRIGHT")
    assert st.distanceUnits == "metric"  # (left and right: the choice before and after)
    _press(lua, "PADDLEFT")
    assert st.distanceUnits == "yards"
    _press(lua, "PAD1")
    assert PO.listOpen and PO.list._shown and "Pick" in str(PO.hint._text)
    _press(lua, "PADDDOWN")
    _press(lua, "PADDDOWN")
    assert st.distanceUnits == "yards"  # (moving in the list picks nothing yet)
    _press(lua, "PAD1")
    assert st.distanceUnits == "imperial" and not PO.listOpen and not PO.list._shown
    _press(lua, "PAD1")
    _press(lua, "PADDUP")
    _press(lua, "PAD2")  # (B: closed, nothing picked; Options still open)
    assert st.distanceUnits == "imperial" and not PO.listOpen and lua.eval("AzerothGPSOptions._shown")


def test_buttons_are_pressed(pad):
    lua, ns = pad
    O, P, PO = _opts(lua, ns)
    O.ShowPage("Controller")
    lab = _diagram_label(O, "PADLSTICK")
    assert PO.FocusOn(lab)
    _press(lua, "PAD1")  # (the drawing's button pressed: its window)
    f = O.padButton
    assert f._shown and f.key == "PADLSTICK"
    # (the focus moved into it, the highlight on it, not left on Options behind: asked 2026-11-16)
    assert PO.side == "popup" and _is(lua, PO.bar.GetParent(PO.bar), f) and PO.bar._level > f.GetFrameLevel(f)
    _press(lua, "PAD2")  # (B: the window closed, Options stays)
    assert not f._shown and lua.eval("AzerothGPSOptions._shown")
    assert P.SetBind("recenter", "PADRSHOULDER") is True
    O.Refresh()
    assert PO.FocusOn(O.padReset)
    _press(lua, "PAD1")
    assert P.Key("recenter") == "PADLSTICK"  # (Reset to defaults pressed)
    assert PO.FocusOn(lab)
    _press(lua, "PAD1")
    assert f._shown
    items = list(PO.Collect(f).values())  # (the window's own controls, one after another)
    ln = f.lines[1]
    assert any(_is(lua, x, ln.action) for x in items) and any(_is(lua, x, f.base) for x in items)
    PO.side = "popup"
    PO.SetFocus(ln.action)
    _press(lua, "PAD1")  # (A: its list open; down to the first control, A picks it)
    assert PO.listOpen
    _press(lua, "PADDDOWN")
    _press(lua, "PAD1")
    assert ln.action.padGet() != "none" and not f.shown[1].empty
    # a list opened in the window: over it, not behind (asked 2026-11-16, "dropdown goes behind window")
    assert PO.OpenList(f.base) and PO.list._shown and PO.list._level > f.GetFrameLevel(f)
    assert PO.list._strata == "FULLSCREEN" and str(f.GetFrameStrata(f)) == "DIALOG"  # (a strata over the window)
    assert _is(lua, PO.list.GetParent(PO.list), f)  # (the window it's for)
    PO.CloseList()
    f.Hide(f)
    P.ResetBinds()


def test_the_page_scrolls_to_keep_the_highlight_in_view(pad):
    lua, ns = pad
    O, P, PO = _opts(lua, ns)
    O.ShowPage("General")
    sf = O.search.pages[O.CurrentPage()].scroll
    assert sf.GetVerticalScroll(sf) == 0
    PO.Refocus()
    _press(lua, "PADDRIGHT")
    rows = PO.Rows()
    # (the first row that ends below the 400-high view; General got shorter 2026-11-17, "Remind me to save" gone)
    deep = next(i for i, r in enumerate(rows.values(), 1) if -r.y + r.h > 400)
    for _ in range(deep - 1):
        _press(lua, "PADDDOWN")
    r = rows[deep]
    vs = sf.GetVerticalScroll(sf)
    assert _is(lua, PO.focus, r[1]) and vs > 0 and vs <= -r.y and -r.y + r.h <= vs + 400  # (the view: 400 high in the harness)
    for _ in range(deep - 1):
        _press(lua, "PADDUP")
    assert _is(lua, PO.focus, rows[1][1]) and sf.GetVerticalScroll(sf) <= -rows[1].y


def test_b_closes_options_and_the_map_has_the_pad_again(pad):
    lua, ns = pad
    O, P, PO = _opts(lua, ns)
    _press(lua, "PAD2")
    assert not lua.eval("AzerothGPSOptions._shown") and not PO.bound and not PO.bar._shown
    P.Apply()
    b = _bound(lua)
    assert b["PADLSTICK"] == "AzerothGPSPad_PADLSTICK" and b["PAD1"] == "AzerothGPSPad_PAD1"


def test_a_question_and_a_popup_over_options(pad):
    lua, ns = pad
    O, P, PO = _opts(lua, ns)
    st = ns.settings.gps
    st.distanceUnits = "metric"
    items = PO.ListItems()
    assert _is(lua, items[len(items)], O.footerReset)
    for _ in range(len(items)):
        _press(lua, "PADDDOWN")
    assert _is(lua, PO.focus, O.footerReset)
    _press(lua, "PAD1")
    assert P.Question() is not None  # (Reset to defaults asks)
    _press(lua, "PAD2")
    assert P.Question() is None and st.distanceUnits == "metric" and lua.eval("AzerothGPSOptions._shown")  # (No)
    ns.Searches.Edit(None)
    ed = ns.Searches.editor
    assert ed._shown and lua.eval("rawequal")(PO.Popup(), ed)
    for _ in range(3):  # (down to the name: the window's own button first)
        _press(lua, "PADDDOWN")
        if _is(lua, PO.focus, ed.name):
            break
    assert _is(lua, PO.focus, ed.name)
    _press(lua, "PAD1")
    assert _is(lua, PO.typing, ed.name)
    _press(lua, "PAD2")
    assert PO.typing is None and ed._shown  # (out of the box first)
    _press(lua, "PAD2")
    assert not ed._shown and lua.eval("AzerothGPSOptions._shown")  # (then the popup)


def test_nothing_in_options_in_combat(pad):
    lua, ns = pad
    O, P, PO = _opts(lua, ns)
    assert PO.bound
    ns.inCombat = True
    try:
        _event(lua, "PLAYER_REGEN_DISABLED")  # (as a fight begins: before the lockdown)
        lua.execute("AGPS_LOCK = true")
        assert not PO.bound and not any(str(v).startswith("AzerothGPSPadOpt_") for v in _bound(lua).values())
        P.Apply()
        assert _press(lua, "PAD2") is False and lua.eval("AzerothGPSOptions._shown")
    finally:
        lua.execute("AGPS_LOCK = false")
        ns.inCombat = None
    _event(lua, "PLAYER_REGEN_ENABLED")
    assert PO.bound and _bound(lua)["PAD2"] == "AzerothGPSPadOpt_PAD2"


def test_nothing_of_blizzards_in_the_options_controller_code():
    text = (ADDON / "PadOptions.lua").read_text(encoding="utf-8")
    code = "\n".join(line.split("--")[0] for line in text.splitlines())
    assert not re.search(r"SetOverrideBinding\w*\(\s*UIParent", code)
    assert not re.search(r"\b(SettingsPanel|WorldMapFrame|ShowUIPanel|HideUIPanel|GamePad\w*Focus|SetGamePadFreeLook|"
                         r"EnableGamePad\w*|UIDropDownMenu\w*|ColorPickerFrame)\b", code)
    assert "PadOptions.lua" in (ADDON / "AzerothGPS.toc").read_text(encoding="utf-8")


# --- The game's Show/Hide key: no button assumed, the game's binding asked about, its modifiers a true pair
# (asked 2026-11-16: "Back is already taken by default controller controls though")

def _game_keys(lua, cvars=None, game=None):
    # (the game's own: its bindings by key, GetBindingKey's reverse, a Gamepad modifier cvar or none)
    lua.execute("""
      AGPS_GAME, AGPS_CVARS = {}, {}
      GetBindingAction = function(k) return AGPS_SETBIND[k] or AGPS_GAME[k] or "" end
      GetBindingKey = function(action)
        local out = {}
        for k, a in pairs(AGPS_SETBIND) do if a == action then out[#out + 1] = k end end
        table.sort(out)
        return unpack(out)
      end
      AGPS_OLDCVAR = C_CVar
      C_CVar = { GetCVar = function(n) return AGPS_CVARS[n] or "none" end }
      BINDING_NAME_TOGGLEGAMEMENU = "Toggle Game Menu"
      AGPS_ASKED = {} AGPS_CONF = AGPS_NS.GPS.Confirm
      AGPS_NS.GPS.Confirm = function(text, yes, no)
        AGPS_ASKED[#AGPS_ASKED + 1] = { text = text, yes = yes, no = no }
        return true
      end
    """)
    for k, v in (cvars or {}).items():
        lua.execute("AGPS_CVARS['%s'] = '%s'" % (k, v))
    for k, v in (game or {}).items():
        lua.execute("AGPS_GAME['%s'] = '%s'" % (k, v))
    _fake_buttons(lua)


def _ungame(lua):
    lua.execute("C_CVar = AGPS_OLDCVAR AGPS_NS.GPS.Confirm = AGPS_CONF")


def _tap(lua, P, key):
    _hold(lua, key)
    P.CaptureTick()
    _hold(lua, key, False)
    P.CaptureTick()


def test_the_offer_waits_for_a_press_and_assumes_no_button(pad):
    # (asked 2026-11-16: "Back is already taken by default controller controls though")
    lua, ns = pad
    P = ns.Pad
    P.Clear()
    ns.db.padOffered = None
    _game_keys(lua, game={"PADBACK": "TOGGLEGAMEMENU"})
    try:
        P.Apply()
        assert ns.db.padOffered and P.Capturing() == "toggle"  # (offered: waiting for a press, no button assumed)
        prompt = ns.lastAsk
        assert prompt._shown and "Press the controller button for Show/Hide GPS" in str(prompt.text._text)
        assert "AZEROTHGPS_TOGGLE" not in [str(v) for v in lua.eval("AGPS_SETBIND").values()]
        _tap(lua, P, "PADFORWARD")  # (Start: nothing of the game's on it)
        assert lua.eval("AGPS_SETBIND.PADFORWARD") == "AZEROTHGPS_TOGGLE" and P.Capturing() is None
        assert not prompt._shown and P.Key("toggle") == "PADFORWARD"
        P.Clear()
        P.Apply()
        assert P.Capturing() is None  # (offered once)
        lua.execute("SlashCmdList.AZEROTHGPS('pad')")
        assert P.Capturing() == "toggle"  # (/agps pad: again)
        _hold(lua, "PAD2")  # (B held cancels)
        P.CaptureTick()
        lua.execute("AGPS_T = AGPS_T + %s" % (P.CANCEL_HOLD + 0.1))
        P.CaptureTick()
        _hold(lua, "PAD2", False)
        assert P.Capturing() is None and P.Key("toggle") == "PADFORWARD"
    finally:
        _ungame(lua)


def test_a_button_the_game_uses_is_asked_about_and_no_waits_for_another(pad):
    lua, ns = pad
    P = ns.Pad
    _game_keys(lua, game={"PADBACK": "TOGGLEGAMEMENU"})
    try:
        P.Offer()
        _tap(lua, P, "PADBACK")
        asked = lua.eval("AGPS_ASKED")
        assert len(asked) == 1 and "Back is Toggle Game Menu: use it for Show/Hide GPS instead?" in str(asked[1].text)
        assert lua.eval("AGPS_SETBIND.PADBACK") is None  # (never taken unasked)
        asked[1].no(True)
        assert P.Capturing() == "toggle"  # (No: another press)
        _tap(lua, P, "PADBACK")
        asked = lua.eval("AGPS_ASKED")
        assert len(asked) == 2
        asked[2].yes()
        assert lua.eval("AGPS_SETBIND.PADBACK") == "AZEROTHGPS_TOGGLE" and P.Capturing() is None  # (Yes: replaced)
    finally:
        _ungame(lua)


def test_with_a_trigger_as_the_games_shift_lt_and_back_is_a_game_binding(pad):
    lua, ns = pad
    O, P = ns.Options, ns.Pad
    _game_keys(lua, cvars={"GamePadEmulateShift": "PADLTRIGGER"}, game={"PADBACK": "TOGGLEGAMEMENU"})
    try:
        assert P.GameMods().PADLTRIGGER == "SHIFT"
        P.Offer()
        assert "hold LT (Shift)" in str(ns.lastAsk.text._text)
        _hold(lua, "PADLTRIGGER")
        P.CaptureTick()
        assert P.Capturing() == "toggle"  # (the game's Shift held: waiting for the other button)
        _hold(lua, "PADBACK")
        P.CaptureTick()
        assert lua.eval("AGPS_SETBIND['SHIFT-PADBACK']") == "AZEROTHGPS_TOGGLE"  # (a true game binding)
        assert len(lua.eval("AGPS_ASKED")) == 0 and lua.eval("AGPS_SETBIND.PADBACK") is None  # (Back left the game's)
        assert P.Key("toggle") == "SHIFT-PADBACK" and P.ActionLabel("toggle") == "LT + Back"
    finally:
        _ungame(lua)


def test_without_the_games_modifiers_a_held_trigger_makes_no_pair(pad):
    lua, ns = pad
    O, P = ns.Options, ns.Pad
    _game_keys(lua)
    try:
        assert next(iter(P.GameMods().items()), None) is None
        P.BeginCapture("toggle")
        assert P.Capturing() == "toggle" and "No trigger or bumper is a Shift, Ctrl or Alt" in str(P.captureHint)
        _hold(lua, "PADLSHOULDER")
        P.CaptureTick()
        assert P.Capturing() is None  # (not a modifier here: bound by itself at once)
        assert lua.eval("AGPS_SETBIND.PADLSHOULDER") == "AZEROTHGPS_TOGGLE" and P.ActionLabel("toggle") == "LB"
    finally:
        _ungame(lua)


def test_no_offer_or_capture_of_the_games_key_in_a_fight(pad):
    lua, ns = pad
    P = ns.Pad
    _game_keys(lua)
    try:
        P.Offer()
        prompt = ns.lastAsk
        assert P.Capturing() == "toggle" and prompt._shown
        ns.inCombat = True
        _event(lua, "PLAYER_REGEN_DISABLED")  # (a fight begins mid-capture: canceled, its prompt gone)
        assert P.Capturing() is None and not prompt._shown
        _tap(lua, P, "PADFORWARD")
        assert P.Offer() is False and P.Capturing() is None
        lua.execute("AGPS_R = nil")
        P.BeginCapture("toggle", lua.eval("function(r) AGPS_R = r end"), True)
        assert P.Capturing() is None and lua.eval("AGPS_R") == "wait"
        assert "AZEROTHGPS_TOGGLE" not in [str(v) for v in lua.eval("AGPS_SETBIND").values()]
    finally:
        ns.inCombat = None
        _ungame(lua)


# --- The controller's buttons in a box on the map's left (asked 2026-11-16: "Have a option to show gamepad controls on
# the map and show them with a light tinted background in this box area, map menu buttons would open on top of them or
# maybe hide them when map menu is expanded")

def _room(lua, ns, nav_bottom=550, height=730, width=1100, logo_bottom=None):
    # (the stand-in has no layout: the map 1100 x 730, the directions panel's bottom `nav_bottom` up from the map's)
    G = ns.GPS
    top = G.mapButton.GetParent(G.mapButton)
    nav = G.mapButtons.toppanel
    lua.execute("AGPS_ROOM = {}")
    room = lua.eval("AGPS_ROOM")
    room.top, room.nav = top, nav
    lua.execute("""
      local t, n = AGPS_ROOM.top, AGPS_ROOM.nav
      t.GetTop = function() return %d end
      t.GetBottom = function() return 0 end
      t.GetWidth = function() return %d end
      n.GetBottom = function() return %d end
      n:Show()
      local lg = AGPS_NS.GPS.logo and AGPS_NS.GPS.logo.plate
      if lg then lg.GetBottom = function() return %d end lg:Show() end
    """ % (height, width, nav_bottom, height if logo_bottom is None else logo_bottom))
    return top


def _lines(P):
    b = P.box
    return [_plain(b.shownLines[i]) for i in range(1, len(b.shownLines) + 1)]


def test_the_box_shows_with_the_option_and_the_line_without(pad):
    lua, ns = pad
    P, st = ns.Pad, ns.settings.gps
    _room(lua, ns)
    P.Apply()
    P.ShowMarks(True)
    assert P.box._shown and not P.legend._shown  # (on by default: the box, not the line at the bottom)
    st.padLegend = False
    P.ShowMarks(True)
    assert not P.box._shown and P.legend._shown
    st.padLegend = None
    P.ShowMarks(True)
    assert P.box._shown
    lua.execute("AzerothGPSFrame:Hide()")  # (the map closed: neither)
    P.Apply()
    assert not P.box._shown


def test_the_box_is_on_the_left_between_the_directions_and_the_map_menu_buttons(pad):
    lua, ns = pad
    G, P = ns.GPS, ns.Pad
    top = _room(lua, ns, nav_bottom=550)
    P.Apply()
    P.ShowMarks(True)
    b = P.box
    pt = b._pts.TOPLEFT
    assert lua.eval("rawequal")(pt[2], top) and pt[1] == "TOPLEFT" and pt[3] == "TOPLEFT"
    assert pt[4] == 6 and pt[5] == 550 - 730 - 6  # (along the left edge, just under the directions)
    _, x, y, w, h = G.PadBoxRoom()
    assert b._h <= h and 730 + y - b._h >= 3 + 32 + 4  # (its bottom over the map menu button and its column)
    assert 110 <= b._w <= 170 and b._w == 132  # (12% of the map's width)
    assert len(_lines(P)) >= 5 and _lines(P)[0] == "A: Set Stop"
    # (under the corner logo where it hangs lower than the directions: asked 2026-11-16, "need to move this down just a
    # bit")
    lua.execute("AGPS_NS.GPS.logo = AGPS_NS.GPS.logo or { plate = CreateFrame('Frame') }")  # (no chrome in the stand-in)
    _room(lua, ns, nav_bottom=700, logo_bottom=640)
    P.ShowMarks(True)
    assert P.box._pts.TOPLEFT[5] == 640 - 730 - 6


def test_the_box_is_lightly_tinted(pad):
    lua, ns = pad
    P = ns.Pad
    _room(lua, ns)
    P.Apply()
    P.ShowMarks(True)
    assert P.box.bg._tex == "color:0.00,0.00,0.00" and P.BOX_TINT == 0.35  # (black, a third see-through)


def test_the_box_hides_while_the_map_menu_is_open_and_its_controls_are_on_the_line(pad):
    lua, ns = pad
    G, P = ns.GPS, ns.Pad
    _room(lua, ns)
    P.Apply()
    P.ShowMarks(True)
    assert P.box._shown
    _press(lua, "PAD4")  # (Y: the map menu)
    G.LayoutQuick()
    P.Apply()
    assert G.mapMenu._shown and not P.box._shown
    assert P.legend._shown and "A: Press" in _plain(P.legend._text) and "Y: Close Menu" in _plain(P.legend._text)
    _press(lua, "PAD4")
    P.Apply()
    assert not G.mapMenu._shown and P.box._shown and not P.legend._shown


def test_the_box_follows_a_binding_change(pad):
    lua, ns = pad
    P = ns.Pad
    _room(lua, ns)
    P.Apply()
    P.ShowMarks(True)
    assert "Left stick press: Recenter" in _lines(P)
    assert P.SetBind("recenter", "PADLSHOULDER+PAD1") is True
    assert "LB + A: Recenter" in _lines(P)  # (at once, no redraw waited for)
    assert P.SetBind("viewControls", "PADRSHOULDER") is True
    assert "RB: View Controls" == _lines(P)[-1]  # (last)
    assert P.SetBind("clear", "PADLSHOULDER+PAD3") is True
    assert not any("Clear Route" in t for t in _lines(P))  # (Remove, Map Menu, Clear Route off the box: asked 2026-11-16)


def test_the_box_shows_fewer_lines_where_they_dont_fit(pad):
    lua, ns = pad
    G, P = ns.GPS, ns.Pad
    _room(lua, ns, nav_bottom=550)
    P.Apply()
    P.ShowMarks(True)
    full = _lines(P)
    _, _, _, _, h = G.PadBoxRoom()
    fit = 4
    _room(lua, ns, nav_bottom=550 - (h - (2 * P.BOX_PAD + fit * P.BOX_LINE + 2)))  # (room for 4 lines)
    P.ShowMarks(True)
    assert _lines(P) == full[:3] + ["..."]  # (the most used first, then "...")
    _room(lua, ns, nav_bottom=3 + 32 + 4 + 6 + 2 * P.BOX_PAD + P.BOX_LINE + 6)  # (room for one: none, the line instead)
    P.ShowMarks(True)
    assert not P.box._shown and P.legend._shown


def test_the_controls_show_only_once_the_pad_is_used(pad):
    # (asked 2026-11-16: "Only show the gamepad controls if controller input is detected") a pad plugged in but the
    # mouse in use: no legend, box or reticle; a pad button: they show; the mouse clicked: gone again. Bound throughout
    lua, ns = pad
    P, G = ns.Pad, ns.GPS
    P.used = False
    P.Apply()
    assert P.bound
    def shown():
        return bool((P.legend and P.legend._shown) or (P.box and P.box._shown) or (P.reticle and P.reticle._shown))
    assert not shown()
    key = P.Key("zoomIn")
    assert lua.eval("AGPS_PRESS")(key, True)
    lua.eval("AGPS_PRESS")(key, False)
    assert P.used and shown()
    owner = lua.globals()[str(P.OWNER)]
    ev = lua.eval("function(o, e, a) o._scripts.OnEvent(o, e, a) end")
    ev = (lambda f, o: (lambda e, a: f(o, e, a)))(ev, owner)
    ev("GLOBAL_MOUSE_DOWN", "LeftButton")
    assert not P.used and not shown() and P.bound
    ev("GAME_PAD_ACTIVE_CHANGED", True)
    assert P.used and shown()
    ev("GAME_PAD_ACTIVE_CHANGED", False)
    assert not shown()


def test_b_tapped_in_a_change_is_bound(pad):
    # (asked 2026-11-16 with Clear Route's row, Hold ticked: "can't bind B because it cancels the input")
    lua, ns = pad
    P = ns.Pad
    _fake_buttons(lua)
    try:
        assert P.SetHold("clear", True)  # (its Hold box ticked: B held, not B's tap that's Back)
        results = []
        P.BeginCapture("clear", lambda r, k, why: results.append((r, k and str(k), why and str(why))))
        _tap(lua, P, "PAD2")
        assert P.Capturing() is None and results and results[-1][0] is True, results
        assert P.Key("clear") == "PAD2" and P.Key("back") == "PAD2"
    finally:
        P.SetHold("clear", False)
        P.ResetBinds()


def test_the_right_stick_press_opens_options(pad):
    # (asked 2026-11-16: "Need a way to open options page with a controller") the map open: the right stick press
    # (changeable, Options > Controller's "Options" row) opens Options, which then moves with the pad itself
    lua, ns = pad
    P = ns.Pad
    assert P.Apply() is True and P.Key("options") == "PADRSTICK"
    assert P.MACROS.options == "/agps options"
    assert lua.eval("AGPS_PRESS")("PADRSTICK", True)
    lua.eval("AGPS_PRESS")("PADRSTICK", False)
    assert lua.eval("AzerothGPSOptions and AzerothGPSOptions._shown")
    assert P.Apply() is False  # (the map's buttons off: Options' own)
    lua.execute("AzerothGPSOptions:Hide()")


def test_show_hide_on_back_held_leaves_the_games_tap(pad):
    # (asked 2026-11-16 with Gamepad UI's Back, "No interface frame to focus!": "Ideally Back (hold) would be an option
    # here") Show/Hide's Hold box: Back is captured without asking about the game's binding, none of ours is set on it,
    # and Back held HOLD_SECONDS toggles the map, once a press
    lua, ns = pad
    P = ns.Pad
    _game_keys(lua, game={"PADBACK": "TOGGLEGAMEMENU"})
    lua.execute("AGPS_TOGGLED = 0 AGPS_TOG = AzerothGPS_ToggleMap AzerothGPS_ToggleMap = function() AGPS_TOGGLED = AGPS_TOGGLED + 1 end")
    try:
        assert P.CanHold("toggle")
        assert P.SetHold("toggle", True) is True
        results = []
        P.BeginCapture("toggle", lambda r, k, why: results.append((r, k and str(k))))
        _tap(lua, P, "PADBACK")
        assert results[-1] == (True, "PADBACK") and lua.eval("AGPS_ASKED[1]") is None  # (not asked: the game's stays)
        assert lua.eval("AGPS_SETBIND.PADBACK") is None and P.Key("toggle") == "PADBACK"
        _hold(lua, "PADBACK")
        P.ToggleHoldTick(0.1)
        lua.execute("AGPS_T = AGPS_T + %s" % (P.HOLD_SECONDS - 0.5))
        P.ToggleHoldTick(0.1)
        assert lua.eval("AGPS_TOGGLED") == 0  # (a tap: the game's)
        lua.execute("AGPS_T = AGPS_T + 1")
        P.ToggleHoldTick(0.1)
        lua.execute("AGPS_T = AGPS_T + 1")
        P.ToggleHoldTick(0.1)
        assert lua.eval("AGPS_TOGGLED") == 1  # (held: once)
        _hold(lua, "PADBACK", False)
        P.ToggleHoldTick(0.1)
        assert P.toggleHeld is None
    finally:
        P.SetHold("toggle", False)
        lua.execute("AzerothGPS_ToggleMap = AGPS_TOG")
        _ungame(lua)


def test_yes_on_its_own_button_takes_a_stops_remove(pad):
    # (asked 2026-11-16: the stop's "Remove?" up, the crosshair not on it, the "Yes on a question" button removes it)
    lua, ns = pad
    G, N, P = ns.GPS, ns.Nav, ns.Pad
    try:
        assert P.SetBind("yes", "PADRSHOULDER") is True
        P.Apply()
        x, y = float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]"))
        N.SetStops(lua.eval("{ { x = %r, y = %r, cont = 0, name = 'Spot' } }" % (x + 300, y + 300)), False, "red")
        G.LookAt(0, x + 300, y + 300)
        for _ in range(3):
            lua.execute("AGPS_T = AGPS_T + 0.5")
            G.Update()
        assert _press(lua, "PAD3") and G.removeAsk._shown
        G.LookAt(0, x + 900, y + 900)  # (the crosshair moved off it)
        G.Update()
        _press(lua, "PADRSHOULDER")
        assert len(N.stops) == 0
    finally:
        P.ResetBinds()


def test_a_on_another_addons_icon_routes_to_it(pad):
    # (asked 2026-11-16: "if crosshairs are over an icon and route is selected, consider that the same as double click
    # to route to it"; another addon's icon on the map, OtherPins.lua's copy)
    lua, ns = pad
    G, P = ns.GPS, ns.Pad
    P.Apply()
    x, y = float(lua.eval("AGPS_POS[1]")), float(lua.eval("AGPS_POS[2]"))
    G.LookAt(0, x + 300, y + 300)
    G.Update()
    lua.execute("""
      AGPS_OPC = AGPS_NS.OtherPins.copies
      AGPS_NS.OtherPins.copies = { NewWidget("Button", "AGPSTestOtherPin") }
      local b = AGPS_NS.OtherPins.copies[1]
      b.wx, b.wy, b.cont, b.title = %r, %r, 0, "Questie thing"
      b:SetScript("OnDoubleClick", AGPS_NS.OtherPins.OnDoubleClick)
      b:Show()
      AGPS_ADDED = nil
      AGPS_ADDSTOP = AGPS_NS.GPS.AddStopAt
      AGPS_NS.GPS.AddStopAt = function(wx, wy, name) AGPS_ADDED = name end
    """ % (x + 302, y + 301))
    try:
        _press(lua, "PAD1")
        assert lua.eval("AGPS_ADDED") == "Questie thing"
    finally:
        lua.execute("AGPS_NS.OtherPins.copies = AGPS_OPC AGPS_NS.GPS.AddStopAt = AGPS_ADDSTOP")


def test_up_from_a_pages_first_row_is_the_search_box(pad):
    # (asked 2026-11-16: "pressing up on the d pad from here id expect the search bar to be selectable")
    lua, ns = pad
    O, P, PO = _opts(lua, ns)
    O.ShowPage("General")
    PO.Refocus()
    _press(lua, "PADDRIGHT")
    first = PO.focus
    assert PO.side == "page"
    _press(lua, "PADDUP")
    box = O.search.box
    assert PO.side == "search" and _is(lua, PO.focus, box)
    # (A: the controller's on-screen keyboard on it, Kooki3z 2026-11-20; test_pad_keyboard.py has the typing)
    _press(lua, "PAD1")
    assert PO.KeysOpen() and PO.typing is None
    _press(lua, "PAD3")  # (X: closed again, the focus still on the box)
    assert not PO.KeysOpen() and PO.side == "search"
    _press(lua, "PADDDOWN")  # (back to the page's first row)
    assert PO.typing is None and PO.side == "page" and _is(lua, PO.focus, first)
    _press(lua, "PADDUP")
    _press(lua, "PADDLEFT")
    assert PO.side == "list"
    # (and up from the page list's first page: asked 2026-11-16, "still can't highlight search in options pane yet")
    PO.ShowPage(1)
    _press(lua, "PADDUP")
    assert PO.side == "search" and _is(lua, PO.focus, box)
    _press(lua, "PADDDOWN")
    assert PO.side == "list"


def test_options_shows_the_controllers_look_only_while_one_is_in_use(pad):
    # (asked 2026-11-16: "If controller support is on but one isn't connected we shouldn't still show controller
    # highlights on options page or the controls at the bottom")
    lua, ns = pad
    O, P, PO = _opts(lua, ns)
    P.SawInput(False)  # (none in use: the mouse's, or none connected)
    assert PO.bound and not PO.LookOn() and not (PO.hint and PO.hint._shown)
    _press(lua, "PADDDOWN")  # (a controller's button: its look on)
    _press(lua, "PADDDOWN", False)
    assert P.used and PO.LookOn() and PO.hint._shown
    P.SawInput(False)  # (the mouse used, or the controller gone)
    assert not PO.LookOn() and not PO.hint._shown
    _event(lua, "GAME_PAD_DISCONNECTED")
    assert not PO.hint._shown


def test_with_the_games_controller_ui_show_hide_is_explained_not_set(pad):
    # (asked 2026-11-16: "for Show/Hide GPS we need to explain why this won't work in controller UI mode but they can
    # create a macro and assign that to a button to open the map. Other functions are expected to work")
    lua, ns = pad
    O, P = ns.Options, ns.Pad
    lua.execute("""
      AGPS_STYLE = { C = C_InputInterfaceStyle, E = Enum.InputDeviceInterfaceType }
      Enum.InputDeviceInterfaceType = { KeyboardAndMouse = 0, Gamepad = 1 }
      C_InputInterfaceStyle = { GetCurrentStyle = function() return AGPS_UI_STYLE or 0 end }
    """)
    O.Show()
    try:
        def toggle_choice():
            return next(o for o in O.ActionChoices().values() if o.value == "toggle")
        assert not P.ToggleBlocked() and not toggle_choice().off
        lua.execute("AGPS_UI_STYLE = 1")
        assert P.ToggleBlocked()
        o = toggle_choice()
        tips = [str(t) for t in o.tip.values()]
        assert o.off and any("/agps toggle" in t and "controller button" in t for t in tips)
        # (picked anyway: refused with the why; other controls go on as ever)
        f = O.PadButton("PAD4")
        f.base.padSet("toggle")
        assert f.base.padGet() == "menu" and "/agps toggle" in str(f.note._text)
        # (a red NOTICE: over it, the macro's line in yellow; on the drawing, Show/Hide GPS red where it's set)
        assert str(f.note._text).startswith("|cffff4040NOTICE:|r") and "|cffffd100/agps toggle|r" in str(f.note._text)
        lua.execute("AGPS_PB = AGPS_NS.settings.gps.padBinds AGPS_NS.settings.gps.padBinds = { toggle = 'PADBACK' }")
        text = str(lua.eval("(AGPS_NS.Pad.DiagramLabel('PADBACK'))"))
        lua.execute("AGPS_NS.settings.gps.padBinds = AGPS_PB")
        assert "|cffff4040Show/Hide GPS|r" in text
        # (the note the window's whole width, three lines over Apply and Done: not cut off, asked 2026-11-16)
        assert O.BUTTON_NOTE_H >= 3 * 12 and O.BUTTON_W - 36 >= 470
        f.base.padSet("clear")
        f.apply._scripts.OnClick(f.apply)
        assert P.Key("clear") == "PAD4"
        f.Hide(f)
    finally:
        P.ResetBinds()
        lua.execute("""
          AGPS_UI_STYLE = nil
          C_InputInterfaceStyle, Enum.InputDeviceInterfaceType = AGPS_STYLE.C, AGPS_STYLE.E
        """)
        _ungame(lua)
# Drawing a farming area with the pad (asked 2026-11-16: "add controller support for drawing areas too like for drawing
# farming area, when controller input is detected switch wording to those controls instead").
def _pad_look(lua, ns, level, x, y):
    ns.GPS.LookAt(level, x, y)
    lua.execute("AGPS_T = AGPS_T + 1")
    ns.GPS.Update()


def _pad_tap(lua, key):
    assert _press(lua, key, True)
    _press(lua, key, False)


def _farm_start(lua, ns):
    G, P = ns.GPS, ns.Pad
    assert P.Apply()
    ns.Tutorial.DemoNodes()  # (herbs and ore round the player)
    x, y, level = ns.Tutorial.Here()
    G.StartDrawing()
    assert G.drawMode
    return G, P, float(x), float(y), level


def test_a_marks_corners_x_undoes_and_y_finishes_a_farming_area(pad):
    lua, ns = pad
    G, P, x, y, level = _farm_start(lua, ns)
    corners = [(150, 150), (150, -150), (-150, -150), (-150, 150)]
    for dx, dy in corners:
        _pad_look(lua, ns, level, x + dx, y + dy)
        _pad_tap(lua, "PAD1")
    l = G.lasso
    assert l and l.pad and len(list(l.pts.values())) == 8
    assert abs(l.pts[7] - (x - 150)) < 1 and abs(l.pts[8] - (y + 150)) < 1  # (each at the crosshair)
    assert len(list(G.PendingStops().values())) == 0  # (A draws a corner, no stop)
    G.Update()  # (the pointer adds nothing to the pad's corners)
    assert len(list(G.lasso.pts.values())) == 8
    _pad_tap(lua, "PAD3")  # X: the last corner off
    assert len(list(G.lasso.pts.values())) == 6
    _pad_tap(lua, "PAD1")  # (the crosshair still there: back on)
    assert len(list(G.lasso.pts.values())) == 8
    _pad_look(lua, ns, level, x - 40, y + 160)  # (panned on: the reticle moves, the drawing waits)
    assert G.drawMode and len(list(G.lasso.pts.values())) == 8
    _pad_tap(lua, "PAD4")  # Y: done, as the mouse let go
    assert not G.drawMode and not G.lasso
    assert len(list(ns.Nav.stops.values())) > 1  # (the loop round the nodes inside)
    assert not P.MenuOpen()  # (Y finished the drawing: the map menu not opened)


def test_a_on_the_first_corner_closes_the_area(pad):
    lua, ns = pad
    G, P, x, y, level = _farm_start(lua, ns)
    for dx, dy in [(150, 150), (150, -150), (-150, -150)]:
        _pad_look(lua, ns, level, x + dx, y + dy)
        _pad_tap(lua, "PAD1")
    assert G.drawMode
    _pad_look(lua, ns, level, x + 150, y + 150)
    _pad_tap(lua, "PAD1")
    assert not G.drawMode and len(list(ns.Nav.stops.values())) > 0


def test_b_cancels_the_drawing_and_y_waits_for_enough_corners(pad):
    lua, ns = pad
    G, P, x, y, level = _farm_start(lua, ns)
    _pad_look(lua, ns, level, x + 150, y + 150)
    _pad_tap(lua, "PAD1")
    _pad_look(lua, ns, level, x - 150, y + 150)
    _pad_tap(lua, "PAD1")
    _pad_tap(lua, "PAD4")  # (two corners: not an area yet)
    assert G.drawMode and len(list(G.lasso.pts.values())) == 4
    _pad_tap(lua, "PAD2")  # B: the drawing canceled, the map still open
    assert not G.drawMode and not G.lasso and len(list(ns.Nav.stops.values())) == 0
    assert lua.eval("AzerothGPSFrame:IsShown()")
    _pad_tap(lua, "PAD1")  # (not drawing: A sets a stop again)
    assert len(list(G.PendingStops().values())) == 1


def test_the_drawing_wording_names_the_pads_buttons_while_it_is_used(pad):
    lua, ns = pad
    G, P, x, y, level = _farm_start(lua, ns)
    L = ns.L
    text = str(G.drawHint.GetText(G.drawHint))
    assert "A adds one" in text and "X: undo" in text and "Y: finish" in text and "(B cancels)" in text
    assert G.drawHint._shown
    assert "A: Add Corner" in str(P.LegendText()) and "Y: Finish Area" in str(P.LegendText())
    assert "A: Add Corner" in [str(s) for s in P.BoxLines().values()]
    tip = [t for t in G.QUICK.values() if t.id == "farm"][0]
    assert "press A to mark" in str(tip.padTip())
    # the mouse used: its own words again
    _event(lua, "GLOBAL_MOUSE_DOWN")
    assert not P.used
    assert str(G.drawHint.GetText(G.drawHint)) == str(L["Drag around the nodes to farm  |cff9d9d9d(right-click cancels)|r"])
    # the pad again, a button changed: the hint follows the binding
    assert P.SetBind("menu", "PADRSHOULDER") is True
    P.SawInput(True)
    assert "RB: finish" in str(G.drawHint.GetText(G.drawHint))
    _pad_look(lua, ns, level, x, y)
    for dx, dy in [(150, 150), (150, -150), (-150, -150)]:
        _pad_look(lua, ns, level, x + dx, y + dy)
        _pad_tap(lua, "PAD1")
    _pad_tap(lua, "PADRSHOULDER")
    assert not G.drawMode
    # (done: the map's own controls on the legend again)
    assert "Set Stop" in str(P.LegendText())


def test_quest_route_and_pause_are_controls(pad):
    # (asked 2026-11-16: "I want quest route and pause route to allow be assignable actions")
    lua, ns = pad
    O, P, G, N = ns.Options, ns.Pad, ns.GPS, ns.Nav
    assert P.Action("questRoute") and P.Action("pause") and P.Key("questRoute") is None and P.Key("pause") is None
    assert str(P.MacroTip("questRoute")[1]) == "Macro: /agps questroute" and str(P.MacroTip("pause")[1]) == "Macro: /agps pause"
    values = [str(o.value) for o in O.ActionChoices().values()]
    assert "questRoute" in values and "pause" in values
    lua.execute("AGPS_QR = 0 AGPS_QRF = AGPS_NS.GPS.QuestRoute AGPS_NS.GPS.QuestRoute = function() AGPS_QR = AGPS_QR + 1 end")
    try:
        assert P.Assign("questRoute", "PADLSHOULDER+PAD3", False) is True
        assert P.Assign("pause", "PADRSHOULDER+PAD3", False) is True
        P.Apply()
        assert P.Run(lua.eval('{ "questRoute" }'), True) is True and lua.eval("AGPS_QR") == 1
        assert P.Run(lua.eval('{ "pause" }'), True) is False  # (no route: nothing to pause)
        lua.execute("AGPS_NS.Nav.stops[1] = { x = -600, y = -4180, cont = 1, name = 'A' }")
        N.dest = N.stops[1]
        assert P.Run(lua.eval('{ "pause" }'), True) is True and N.paused
        assert P.Run(lua.eval('{ "pause" }'), True) is True and not N.paused
        # (the slash command for the macro)
        lua.execute("SlashCmdList.AZEROTHGPS('questroute')")
        assert lua.eval("AGPS_QR") == 2
    finally:
        lua.execute("AGPS_NS.GPS.QuestRoute = AGPS_QRF")
        N.dest = None
        P.ResetBinds()



def test_debug_toggle_prints_the_maps_state_before_and_after(pad):
    # (for the /agps toggle macro doing nothing with the game's controller UI on, 2026-11-16)
    lua, ns = pad
    lua.execute("AGPS_PR = {} AGPS_PRF = AGPS_NS.Print AGPS_NS.Print = function(t) AGPS_PR[#AGPS_PR + 1] = t end")
    try:
        lua.eval("SlashCmdList.AZEROTHGPS")("debug toggle")
        out = [str(t) for t in lua.eval("AGPS_PR").values()]
        assert out[0].startswith("before: shown=") and any(t.startswith("after: shown=") for t in out) and "controllerUI=" in out[0]
    finally:
        lua.execute("AGPS_NS.Print = AGPS_PRF")


def test_each_toggle_is_kept_in_the_saved_log(pad):
    # (asked 2026-11-16: "for the toggle debug have it write after reload for you to read")
    lua, ns = pad
    ns.db.toggleLog = None
    lua.eval("AzerothGPS_ToggleMap")()
    lua.eval("SlashCmdList.AZEROTHGPS")("toggle")
    log = list(ns.db.toggleLog.values())
    assert [str(e.src) for e in log] == ["key", "/agps toggle"]
    assert str(log[0].before).startswith("shown=") and str(log[0].after).startswith("shown=")
    for _ in range(25):
        lua.eval("AzerothGPS_ToggleMap")()
    assert len(ns.db.toggleLog) == ns.TOGGLE_LOG_KEEP


def test_with_the_controller_ui_the_button_windows_dropdowns_are_ours(pad):
    # (AzerothGPS's own forbiddenLog, 2026-11-16: the game's menu shown or hidden with the controller UI on ran
    # SetPreferredGamepadInteractTarget from Blizzard_GamepadSmartNavigation and got blocked; with it on, our own list
    # for the mouse and the pad alike, the game's menu with it off)
    lua, ns = pad
    O, P, PO = _opts(lua, ns)
    lua.execute("""
      AGPS_STYLE = { C = C_InputInterfaceStyle, E = Enum.InputDeviceInterfaceType }
      Enum.InputDeviceInterfaceType = { KeyboardAndMouse = 0, Gamepad = 1 }
      C_InputInterfaceStyle = { GetCurrentStyle = function() return AGPS_UI_STYLE or 0 end }
    """)
    try:
        f = O.PadButton("PADLSTICK")
        own = f.base.own
        assert own is not None and f.base._shown and not own._shown  # (the controller UI off: the game's)
        lua.execute("AGPS_UI_STYLE = 1")
        O.PadButtonRefresh()
        assert not f.base._shown and own._shown and own.padGet() == "recenter"
        own._scripts.OnClick(own)  # (the mouse: our list)
        lst = PO.list
        assert PO.listOpen and lst._shown
        row = lst.rows[2]
        row._scripts.OnEnter(row)
        row._scripts.OnClick(row)
        assert not PO.listOpen and f.dirty
        f.Hide(f)
    finally:
        lua.execute("""
          AGPS_UI_STYLE = nil
          C_InputInterfaceStyle, Enum.InputDeviceInterfaceType = AGPS_STYLE.C, AGPS_STYLE.E
        """)

def test_the_controller_moves_through_the_search_results(pad):
    # (asked 2026-11-16: "when using the search bar in Options and results popup I can't move to them with the
    # controller")
    lua, ns = pad
    O, P, PO = _opts(lua, ns)
    O.ShowPage("General")
    O.Search("opacity")
    s = O.search
    assert s.results._shown
    rows = list(PO.Rows().values())
    assert len(rows) >= 1
    parent_ok = lua.eval("""function(top, f)
      local a = f
      while a do if a == top then return true end a = a:GetParent() end
      return false
    end""")
    assert all(parent_ok(s.resultsChild, r[1]) for r in rows)  # (the results' rows, not the page's)
    ys = [r.y for r in rows]
    assert ys == sorted(ys, reverse=True)  # (top to bottom as the results show them)
    PO.FocusSearch("page")
    _press(lua, "PADDDOWN")  # (down from the search box: the first result)
    assert PO.side == "page" and _is(lua, PO.focus, rows[0][1])
    O.Search("")



def test_a_blocked_action_is_kept_for_a_bug_report(pad):
    # (asked 2026-11-16: the button window's dropdowns "caused UI error again": what the game blocked, kept)
    lua, ns = pad
    ns.db.forbiddenLog = None
    lua.execute("""
      for _, w in ipairs(AGPS_WIDGETS) do
        if w._events and w._events.ADDON_ACTION_FORBIDDEN then
          w._scripts.OnEvent(w, "ADDON_ACTION_FORBIDDEN", "AzerothGPS", "SetPreferredGamepadInteractTarget()")
          w._scripts.OnEvent(w, "ADDON_ACTION_FORBIDDEN", "OtherAddon", "Foo()")
        end
      end
    """)
    log = list(ns.db.forbiddenLog.values())
    assert len(log) == 1 and str(log[0].func) == "SetPreferredGamepadInteractTarget()" and str(log[0].event) == "ADDON_ACTION_FORBIDDEN"


def test_left_click_clicks_what_is_under_the_crosshair(pad):
    # (asked 2026-11-16: "Need another action to do the same action as left click to open dungeon maps for example")
    lua, ns = pad
    P, G = ns.Pad, ns.GPS
    P.Apply()
    assert P.Action("click") and P.Key("click") is None and str(P.MacroTip("click")[1]) == "Macro: /agps pad click"
    lua.execute("""
      AGPS_CLICKED, AGPS_CAVE = 0, 0
      AGPS_CC = AGPS_NS.GPS.CaveClick
      AGPS_NS.GPS.CaveClick = function(dx, dy) AGPS_CAVE = AGPS_CAVE + 1 return true end
      AGPS_POIS = AGPS_NS.GPS.poiButtons
      AGPS_NS.GPS.poiButtons = {}
    """)
    try:
        assert P.Run(lua.eval('{ "click" }'), True) is True and lua.eval("AGPS_CAVE") == 1  # (nothing under it: the map)
        lua.execute("""
          local vx, vy = AGPS_NS.GPS.PadView()
          AGPS_ENTR = CreateFrame("Button")
          AGPS_ENTR.wx, AGPS_ENTR.wy = vx, vy
          AGPS_ENTR:SetScript("OnClick", function(_, btn) if btn == "LeftButton" then AGPS_CLICKED = AGPS_CLICKED + 1 end end)
          AGPS_NS.GPS.poiButtons[#AGPS_NS.GPS.poiButtons + 1] = AGPS_ENTR
        """)
        assert P.Run(lua.eval('{ "click" }'), True) is True and lua.eval("AGPS_CLICKED") == 1  # (an entrance: its click)
    finally:
        lua.execute("""
          AGPS_NS.GPS.CaveClick = AGPS_CC
          AGPS_NS.GPS.poiButtons = AGPS_POIS
        """)


def test_with_the_controller_ui_every_options_dropdown_is_ours(pad):
    # (asked 2026-11-16: "swap all dropdowns to this when controller UI is enabled and the use the other dropdown style
    # when its not enabled because this works now but other dropdowns cause the error")
    lua, ns = pad
    O, P, PO = _opts(lua, ns)
    lua.execute("""
      AGPS_STYLE = { C = C_InputInterfaceStyle, E = Enum.InputDeviceInterfaceType }
      Enum.InputDeviceInterfaceType = { KeyboardAndMouse = 0, Gamepad = 1 }
      C_InputInterfaceStyle = { GetCurrentStyle = function() return AGPS_UI_STYLE or 0 end }
    """)
    try:
        dds = [w for w in lua.eval("AGPS_WIDGETS").values() if w.own is not None and w.padGet is not None and w.padList is None]  # (the pages' own)
        assert len(dds) >= 3
        O.Refresh()
        assert all(not d.own._shown for d in dds)
        lua.execute("AGPS_UI_STYLE = 1")
        O.Refresh()
        shown = [d for d in dds if not d.agpsSearchHid]
        assert all(not d._shown and d.own._shown for d in shown)
        d = shown[0]
        d.own._scripts.OnClick(d.own)  # (our list, the mouse's)
        assert PO.listOpen
        row = PO.list.rows[1]
        row._scripts.OnEnter(row)
        PO.CloseList()
    finally:
        lua.execute("""
          AGPS_UI_STYLE = nil
          C_InputInterfaceStyle, Enum.InputDeviceInterfaceType = AGPS_STYLE.C, AGPS_STYLE.E
        """)
        O.Refresh()


def test_back_leaves_a_dungeons_map_first_then_closes_the_map(pad):
    # (asked 2026-11-16: "the Back button does the same as a right click in that view so it goes back to the map first.
    # another Back press would close the map")
    lua, ns = pad
    G, P, st = ns.GPS, ns.Pad, ns.settings.gps
    P.Apply()
    G.ShowInstance(20036)  # (the Deadmines, opened from its icon)
    G.Update()
    assert G.shownView.instance == 20036
    lua.execute("AGPS_TOGGLED = 0 AGPS_TOG = AzerothGPS_ToggleMap AzerothGPS_ToggleMap = function() AGPS_TOGGLED = AGPS_TOGGLED + 1 end")
    try:
        assert P.Run(lua.eval('{ "back" }'), True) is True
        G.Update()
        assert not G.shownView.instance and lua.eval("AGPS_TOGGLED") == 0  # (out of it, the map still open)
        assert P.Run(lua.eval('{ "back" }'), True) is True
        assert lua.eval("AGPS_TOGGLED") == 1  # (the next Back: the map closed)
    finally:
        lua.execute("AzerothGPS_ToggleMap = AGPS_TOG")


def test_open_is_on_the_maps_controls_once_it_has_a_button(pad):
    # (asked 2026-11-16: "Change Left-Click action to "Open" and show it on the map controls")
    lua, ns = pad
    P = ns.Pad
    assert str(P.Action("click")[3]) == "Select"
    assert not any("LB + A" in str(t) for t in P.BoxLines(False).values())
    try:
        assert P.Assign("click", "PADLSHOULDER+PAD1", False) is True
        assert "LB + A: Select" in [str(t) for t in P.BoxLines(False).values()]
    finally:
        P.ResetBinds()


def test_select_confirms_a_route_while_confirm_route_shows(pad):
    # (asked 2026-11-16: "After a route is set, allow the Select button to be used to Confirm Route"; never the button's
    # other job, Clear Route with a route: "clear route still jumped back to player position")
    lua, ns = pad
    P, G = ns.Pad, ns.GPS
    P.Apply()
    lua.execute("""
      AGPS_CONF = 0
      AGPS_SAVE = { ps = AGPS_NS.GPS.PendingStop, cr = AGPS_NS.GPS.ConfirmRoute }
      AGPS_PEND = true
      AGPS_NS.GPS.PendingStop = function(i) return AGPS_PEND and { x = 1, y = 1 } or nil end
      AGPS_NS.GPS.ConfirmRoute = function() AGPS_CONF = AGPS_CONF + 1 end
    """)
    try:
        assert P.Run(lua.eval('{ "click" }'), True) is True and lua.eval("AGPS_CONF") == 1  # (stops waiting: confirmed)
        assert P.Assign("click", "PADLSHOULDER+PAD1", False) is True
        P.SawInput(True)
        P.ShowMarks(True)
        lua.execute("AGPS_NS.GPS.confirmRouteBtn:Show()")
        same = lua.eval("rawequal")
        assert any(same(t[1], G.confirmRouteBtn) and str(t[2]) == "click" for t in P.HintTargets().values())
        # (stops marked: Select's only; none yet: Set Stop's only; asked 2026-11-16)
        ids = [str(t[2]) for t in P.HintTargets().values() if same(t[1], G.confirmRouteBtn)]
        assert ids == ["click"]
        lua.execute("AGPS_PEND = false")
        ids = [str(t[2]) for t in P.HintTargets().values() if same(t[1], G.confirmRouteBtn)]
        assert ids == ["select"]
        # a route and nothing waiting: Select doesn't clear it
        lua.execute("AGPS_PEND = false")
        _a_route(lua)
        P.Run(lua.eval('{ "click" }'), True)
        assert len(ns.Nav.stops) == 1 and lua.eval("AGPS_CONF") == 1
    finally:
        lua.execute("AGPS_NS.GPS.PendingStop, AGPS_NS.GPS.ConfirmRoute = AGPS_SAVE.ps, AGPS_SAVE.cr AGPS_NS.GPS.confirmRouteBtn:Hide()")
        ns.Nav.Clear()
        P.ResetBinds()

def test_the_defaults_put_the_route_controls_on_lb(pad):
    # (asked 2026-11-16: "update the default controller settings to what you think would be most optimal")
    lua, ns = pad
    P = ns.Pad
    lua.execute("for _, a in ipairs(AGPS_NS.Pad.ACTIONS) do if AGPS_DEF[a[1]] then a[2] = AGPS_DEF[a[1]] end end")
    try:
        assert P.ResetBinds() is True
        keys = {a: str(P.Key(a)) for a in ("select", "yes", "back", "remove", "menu", "zoomIn", "zoomOut", "recenter",
                                          "options", "click", "viewControls", "clear", "questRoute", "pause",
                                          "avoids")}
        assert keys == {"select": "PAD1", "yes": "PAD1", "back": "PAD2", "remove": "PAD3", "menu": "PAD4",
                        "zoomIn": "PADRTRIGGER", "zoomOut": "PADLTRIGGER", "recenter": "PADLSTICK", "options": "PADRSTICK",
                        "click": "PADLSHOULDER", "viewControls": "PADRSHOULDER", "clear": "PADLSHOULDER+PAD3",
                        "questRoute": "PADLSHOULDER+PAD4", "pause": "PADFORWARD",  # (Start: 1.3.9)
                        "avoids": "PADLSHOULDER+PAD1"}  # (the route's jumps and swims: item 96, 1.4.1)
        # (no two the same way: each default its own button or pair)
        seen = set()
        for a in P.ACTIONS.values():
            k = P.Key(a[1])
            if k and a[1] != "yes":
                assert (str(k), P.IsHold(a[1])) not in seen, a[1]
                seen.add((str(k), P.IsHold(a[1])))
        # the box: View Controls last
        P.Apply()
        assert str(list(P.BoxLines(False).values())[-1]) == "RB: View Controls"
    finally:
        lua.execute("for _, a in ipairs(AGPS_NS.Pad.ACTIONS) do if AGPS_DEF[a[1]] then a[2] = nil end end")
        P.ResetBinds()


def test_the_pads_pan_keeps_the_opened_map_from_its_quiet_close(pad):
    # (asked 2026-11-16: "the map is closing now while I'm using the controller to pan, this should count as activity")
    lua, ns = pad
    G, P = ns.GPS, ns.Pad
    P.Apply()
    lua.execute("AGPS_T0 = GetTime()")
    lua.execute("AGPS_T = AGPS_T + 30")
    G.PadPan(10, 0)
    lua.execute("""
      AGPS_M = AGPS_NS.GPS.mmState
      AGPS_M.expanded, AGPS_M.tween, AGPS_M.activeAt = true, nil, 0
    """)
    lua.execute("AGPS_SAVED_SME = AGPS_NS.GPS.SetMinimapExpanded AGPS_CLOSED = false AGPS_NS.GPS.SetMinimapExpanded = function() AGPS_CLOSED = true end")
    try:
        G.MinimapIdle(lua.eval("GetTime()"))
        assert lua.eval("AGPS_M.activeAt") >= lua.eval("GetTime()") - 0.01 and not lua.eval("AGPS_CLOSED")
    finally:
        lua.execute("AGPS_NS.GPS.SetMinimapExpanded = AGPS_SAVED_SME AGPS_M.expanded = nil")


def test_view_controls_shows_the_controller_then_fades(pad):
    # (asked 2026-11-16: "show the controller image over a black faded background that matches the same background as
    # the map controls ... stays visible for 10 secs and fades away over the next 5 secs ... View Controls")
    lua, ns = pad
    P = ns.Pad
    P.Apply()
    assert P.Action("viewControls") and P.Run(lua.eval('{ "viewControls" }'), True) is True
    ov = P.controls
    assert ov._strata == "TOOLTIP" and ov._pts.LEFT[3] == "LEFT"  # (over the land zoomed in too; the map's left middle)
    # (smaller with a smaller map window: at most 45% of its width, 60% of its height; full size on a big one)
    small = lua.eval("{ GetWidth = function() return 600 end, GetHeight = function() return 400 end }")
    big = lua.eval("{ GetWidth = function() return 2000 end, GetHeight = function() return 1200 end }")
    assert abs(P.ControlsScale(small) - min(600 * 0.45 / 480, 400 * 0.6 / 320)) < 1e-9 and P.ControlsScale(big) == 1
    assert ov._shown and ov.bg._tex == "color:0.00,0.00,0.00" and ov.diag.tex is not None and len(ov.diag.labels) == 16
    up = ov._scripts.OnUpdate
    up(ov, 9.9)
    assert ov._shown and ov._alpha == 1
    up(ov, 2.6)  # (12.5 s: half faded)
    assert ov._shown and abs(ov._alpha - 0.5) < 0.01
    up(ov, 3)  # (15.5 s: gone)
    assert not ov._shown
    # (the map back in the minimap square: not shown, and gone if it was; asked 2026-11-16)
    assert P.Run(lua.eval('{ "viewControls" }'), True) is True and ov._shown
    lua.execute("AGPS_MMM = AGPS_NS.GPS.MinimapMode AGPS_NS.GPS.MinimapMode = function() return true end")
    try:
        up(ov, 0.1)
        assert not ov._shown
        assert P.Run(lua.eval('{ "viewControls" }'), True) is False and not ov._shown
    finally:
        lua.execute("AGPS_NS.GPS.MinimapMode = AGPS_MMM")
    # (Options open: not over it, asked 2026-11-16)
    assert P.Run(lua.eval('{ "viewControls" }'), True) is True and ov._shown
    ns.Options.Show()
    try:
        up(ov, 0.1)
        assert not ov._shown and P.Run(lua.eval('{ "viewControls" }'), True) is False
    finally:
        lua.execute("AzerothGPSOptions:Hide()")


def test_a_default_steps_aside_for_a_button_the_player_gave_another(pad):
    # (2026-11-16: View Controls' new default RB where the player had put Pause Routing: RB stays Pause Routing)
    lua, ns = pad
    P = ns.Pad
    lua.execute("for _, a in ipairs(AGPS_NS.Pad.ACTIONS) do if AGPS_DEF[a[1]] then a[2] = AGPS_DEF[a[1]] end end")
    try:
        ns.settings.gps.padBinds = lua.eval("{ pause = 'PADRSHOULDER' }")
        assert str(P.Key("pause")) == "PADRSHOULDER" and P.Key("viewControls") is None
    finally:
        lua.execute("for _, a in ipairs(AGPS_NS.Pad.ACTIONS) do if AGPS_DEF[a[1]] then a[2] = nil end end")
        P.ResetBinds()


def test_select_with_the_games_click_too_sets_no_stop(pad):
    # (asked 2026-11-16 with the controller UI on: "Select button still sets a route stop instead of clicking to open a
    # dungeon view": the game's own click and ours, a double-click, made a stop)
    lua, ns = pad
    G, P = ns.GPS, ns.Pad
    P.Apply()
    lua.execute("AGPS_POIS = AGPS_NS.GPS.poiButtons AGPS_NS.GPS.poiButtons = {} AGPS_CC = AGPS_NS.GPS.CaveClick AGPS_NS.GPS.CaveClick = function() return false end")
    try:
        P.Run(lua.eval('{ "click" }'), True)
        assert G.PadClickedJustNow()
        lua.execute("AGPS_T = AGPS_T + 1")
        assert not G.PadClickedJustNow()
    finally:
        lua.execute("AGPS_NS.GPS.poiButtons = AGPS_POIS AGPS_NS.GPS.CaveClick = AGPS_CC")


def test_a_flyout_in_quick_find_is_navigated_and_backed_out_of(pad):
    # (asked 2026-11-16: "I cant use the controller to select one of these, we need to support sub menu nesting
    # navigation": Quick Find's Ammo, its arrows and bullets)
    lua, ns = pad
    G, P = ns.GPS, ns.Pad
    P.Apply()
    lua.execute("""
      AGPS_QF = { b = {} }
      local function btn() local b = CreateFrame("Button") b:Show() return b end
      AGPS_QF.ammo, AGPS_QF.arrows, AGPS_QF.bullets = btn(), btn(), btn()
      AGPS_NS.GPS.quickFindButtons.ammo, AGPS_NS.GPS.quickFindButtons.arrows, AGPS_NS.GPS.quickFindButtons.bullets = AGPS_QF.ammo, AGPS_QF.arrows, AGPS_QF.bullets
      AGPS_NS.GPS.quickFindOpen = true
      AGPS_NS.GPS.quickFindSub = { kind = "ammo", sub = { { kind = "arrows" }, { kind = "bullets" } } }
      AGPS_SQO = AGPS_NS.GPS.SetQuickFindOpen
      AGPS_NS.GPS.SetQuickFindOpen = function(on, sub) AGPS_NS.GPS.quickFindOpen = on AGPS_NS.GPS.quickFindSub = sub end
    """)
    same = lua.eval("rawequal")
    try:
        lst = list(P.MenuButtons().values())
        assert len(lst) == 2 and same(lst[0], lua.eval("AGPS_QF.arrows"))  # (the inner flyout's own buttons)
        assert same(P.MenuParent(), lua.eval("AGPS_QF.ammo"))  # (B's hint over Ammo)
        lua.execute("AGPS_NS.GPS.mapMenu:Show()")
        P.MenuRun(lua.eval('{ back = true }'), True)
        assert lua.eval("AGPS_NS.GPS.quickFindSub") is None and lua.eval("AGPS_NS.GPS.quickFindOpen")
        assert same(P.focus, lua.eval("AGPS_QF.ammo"))  # (back on Ammo, Quick Find still open)
    finally:
        lua.execute("AGPS_NS.GPS.SetQuickFindOpen = AGPS_SQO AGPS_NS.GPS.quickFindOpen = false AGPS_NS.GPS.quickFindSub = nil AGPS_NS.GPS.mapMenu:Hide()")
        P.SetFocus(None)


def test_a_red_buttons_hint_sits_at_its_right_end_and_stays(pad):
    # (asked 2026-11-16: "Anytime there is a red button being used on the map, including zone too high level popups lets
    # move the button to press to this pink area and not fade. Just for buttons")
    lua, ns = pad
    P = ns.Pad
    wide = lua.eval("(function() local b = CreateFrame('Button') b.GetWidth = function() return 128 end b.GetHeight = function() return 22 end return b end)()")
    roundb = lua.eval("(function() local b = CreateFrame('Button') b.GetWidth = function() return 26 end b.GetHeight = function() return 26 end return b end)()")
    assert P.HintWide(wide) and not P.HintWide(roundb)
    lua.execute("AGPS_HT = AGPS_NS.Pad.HintTargets")
    try:
        lua.globals().AGPS_W, lua.globals().AGPS_R = wide, roundb
        lua.execute("AGPS_NS.Pad.HintTargets = function() return { { AGPS_W, 'yes' }, { AGPS_R, 'menu' } } end AGPS_NS.Pad.hintTargets = nil")
        P.HintTick(1.5)  # (the round one's pulse faded out by then)
        hs = [h for h in P.hints.values() if h._shown]
        same = lua.eval("rawequal")
        hw = next(h for h in hs if same(h.target, wide))
        hr = next(h for h in hs if same(h.target, roundb))
        assert hw.alpha == 1 and hw._pts.LEFT[3] == "RIGHT"  # (from its right end outward, steady)
        assert hw.text._pts.LEFT is not None  # (a pair's icons run outward, both past its text)
        assert hr.alpha < 1 and hr._pts.CENTER[3] == "CENTER"
    finally:
        lua.execute("AGPS_NS.Pad.HintTargets = AGPS_HT AGPS_NS.Pad.hintTargets = nil")


def test_clear_routes_buttons_show_on_the_red_clear_route_button(pad):
    # (asked 2026-11-16: "Its LB + X but not on the button": the map's bottom button is Clear Route with a route up)
    lua, ns = pad
    P, G = ns.Pad, ns.GPS
    P.Apply()
    try:
        assert P.Assign("clear", "PADLSHOULDER+PAD3", False) is True
        _a_route(lua)
        lua.execute("AGPS_NS.GPS.confirmRouteBtn:Show()")
        P.SawInput(True)
        P.ShowMarks(True)
        same = lua.eval("rawequal")
        assert any(same(t[1], G.confirmRouteBtn) and str(t[2]) == "clear" for t in P.HintTargets().values())
        assert "LB" in str(P.HintText("clear")) or "LB_" in str(P.HintText("clear"))  # (both buttons of the pair)
    finally:
        lua.execute("AGPS_NS.GPS.confirmRouteBtn:Hide()")
        ns.Nav.Clear()
        P.ResetBinds()


def test_a_trigger_the_game_makes_a_shift_still_zooms_while_held(pad):
    # (asked 2026-11-16: "When not in controller UI, LT zoom out doesn't work when holding but zooming in does": the
    # game's Gamepad settings make LT a Shift, and no binding of ours on it is pressed)
    lua, ns = pad
    P = ns.Pad
    P.Apply()
    lua.execute("""
      AGPS_SV = { cv = GetCVar, kd = AGPS_NS.Pad.KeysDown, wz = AGPS_NS.GPS.WheelZoom }
      GetCVar = function(n) if n == "GamePadEmulateShift" then return "PADLTRIGGER" end return "none" end
      AGPS_LTDOWN = true
      AGPS_NS.Pad.KeysDown = function() return { PADLTRIGGER = AGPS_LTDOWN or nil } end
      AGPS_ZF = nil
      AGPS_NS.GPS.WheelZoom = function(f) AGPS_ZF = f end
    """)
    try:
        assert P.Key("zoomOut") == "PADLTRIGGER" and P.HeldNow("zoomOut")
        P.Tick(0.1)
        assert lua.eval("AGPS_ZF") is not None and lua.eval("AGPS_ZF") > 1  # (out: more yards in view)
        lua.execute("AGPS_LTDOWN = false AGPS_ZF = nil")
        P.Tick(0.1)
        assert lua.eval("AGPS_ZF") is None
    finally:
        lua.execute("GetCVar, AGPS_NS.Pad.KeysDown, AGPS_NS.GPS.WheelZoom = AGPS_SV.cv, AGPS_SV.kd, AGPS_SV.wz")


def test_a_quest_areas_tooltip_shows_at_the_crosshair(pad):
    # (asked 2026-11-16: "possible when using a controller to pan map to show tooltips based on crosshair like this?")
    lua, ns = pad
    G, P = ns.GPS, ns.Pad
    P.Apply()
    P.SawInput(True)
    P.ShowMarks(True)
    lua.execute("""
      AGPS_SV = { qa = AGPS_NS.Layers.QuestsAt, add = AGPS_NS.Layers.AddQuestToTooltip, on = AGPS_NS.GPS.QuestAreasOn }
      AGPS_AT = nil
      AGPS_NS.Layers.QuestsAt = function(c, x, y) AGPS_AT = { x, y } return { 123 } end
      AGPS_NS.Layers.AddQuestToTooltip = function(tip, q) tip:AddLine("Quest " .. q) end
      AGPS_NS.GPS.QuestAreasOn = function() return true end
      GameTooltip:Hide()
    """)
    try:
        G.AreaTooltip(1)
        vx, vy = G.PadView()[0], G.PadView()[1]
        at = lua.eval("AGPS_AT")
        assert at is not None and (at[1], at[2]) == (vx, vy)  # (the crosshair's spot, not the pointer's)
        assert G.areaTip
    finally:
        lua.execute("AGPS_NS.Layers.QuestsAt, AGPS_NS.Layers.AddQuestToTooltip, AGPS_NS.GPS.QuestAreasOn = AGPS_SV.qa, AGPS_SV.add, AGPS_SV.on")
def test_the_crosshair_shows_an_icons_tooltip_with_the_pads_buttons(pad):
    # (asked 2026-11-16: "crosshair on an icon should show its tool tip when using a controller and the tool tip
    # controls should be the controller's not mouse instructions")
    lua, ns = pad
    G, P = ns.GPS, ns.Pad
    P.Apply()
    vx, vy = G.PadView()[0], G.PadView()[1]
    lua.execute("""
      AGPS_IN, AGPS_OUT = 0, 0
      AGPS_ICON2 = NewWidget("Button", nil)
      AGPS_ICON2.wx, AGPS_ICON2.wy = %r, %r
      AGPS_ICON2._scripts.OnEnter = function() AGPS_IN = AGPS_IN + 1 end
      AGPS_ICON2._scripts.OnLeave = function() AGPS_OUT = AGPS_OUT + 1 end
      AGPS_ICON2:Show()
    """ % (vx + 0.5, vy + 0.5))
    pois = G.poiButtons
    n = len(pois) + 1
    pois[n] = lua.eval("AGPS_ICON2")
    try:
        P.used = False
        P.HoverTick(1)
        assert lua.eval("AGPS_IN") == 0  # (the mouse in use: its own hover)
        P.used = True
        P.HoverTick(1)
        P.HoverTick(1)
        assert lua.eval("AGPS_IN") == 1 and lua.eval("AGPS_OUT") == 0  # (once, while it stays under it)
        lua.execute("AGPS_ICON2.wx = AGPS_ICON2.wx + 5000")
        P.HoverTick(1)
        assert lua.eval("AGPS_OUT") == 1
        # the tooltip's lines: the controller's button, not "Double-click"
        lua.execute("""
          AGPS_TL = {} AGPS_TADD = GameTooltip.AddLine
          GameTooltip.AddLine = function(_, t) AGPS_TL[#AGPS_TL + 1] = tostring(t) end
        """)
        tip = lua.eval("GameTooltip")
        assert G.PadTipLine(tip, "select") is True
        assert G.PadTipLine(tip, "remove") is True
        P.used = False
        assert G.PadTipLine(tip, "select") is False
        lines = [str(v) for v in lua.eval("AGPS_TL").values()]
        assert lines == ["A: add as a stop", "X: remove this stop"], lines
    finally:
        pois[n] = None
        P.SetHovered(None)
        lua.execute("if AGPS_TADD then GameTooltip.AddLine = AGPS_TADD end")


# -- Pause/Unpause on Start, its hint over the glowing Resume buttons (1.3.9, asked 2026-11-18: "Make a new controller
# action 'Pause/Unpause' default keybind to Start button. When map is open and controller in use and pause is active the
# button needed to unpause the route fades like the others") ------------------------------------------------------------

def _defaults_on(lua):
    lua.execute("for _, a in ipairs(AGPS_NS.Pad.ACTIONS) do if AGPS_DEF[a[1]] then a[2] = AGPS_DEF[a[1]] end end")


def _defaults_off(lua):
    lua.execute("for _, a in ipairs(AGPS_NS.Pad.ACTIONS) do if AGPS_DEF[a[1]] then a[2] = nil end end")


def test_pause_unpause_is_on_start_by_default_and_toggles_pause(pad):
    lua, ns = pad
    P, N, G = ns.Pad, ns.Nav, ns.GPS
    _defaults_on(lua)
    try:
        P.ResetBinds()
        assert str(P.Action("pause")[3]) == "Pause/Unpause"
        assert str(P.Key("pause")) == "PADFORWARD" and str(P.ActionLabel("pause")) == "Start"
        # (no other control on Start by default, and Start is the game's game menu only: ours only while the map's open)
        assert [str(a[1]) for a in P.ACTIONS.values() if P.Key(a[1]) == "PADFORWARD"] == ["pause"]
        P.Clear()
        assert P.Apply() is True and "PADFORWARD" in _bound(lua)
        assert _press(lua, "PADFORWARD") and not N.paused  # (no route: nothing to pause)
        _press(lua, "PADFORWARD", False)
        _a_route(lua)
        N.dest = N.stops[1]
        _press(lua, "PADFORWARD")
        _press(lua, "PADFORWARD", False)
        assert N.paused == "manual"
        _press(lua, "PADFORWARD")
        _press(lua, "PADFORWARD", False)
        assert N.paused is None
    finally:
        N.Clear()
        N.dest = None
        _defaults_off(lua)
        P.ResetBinds()
        P.Clear()


def test_start_given_to_another_control_or_pause_on_its_own_button_is_kept(pad):
    lua, ns = pad
    P, st = ns.Pad, ns.settings.gps
    _defaults_on(lua)
    try:
        # (an existing player's own Start: theirs; Pause/Unpause then on none, never over it)
        st.padBinds = lua.eval("{ remove = 'PADFORWARD' }")
        assert str(P.Key("remove")) == "PADFORWARD" and P.Key("pause") is None
        # (their own button for it, from before: kept)
        st.padBinds = lua.eval("{ pause = 'PADLSHOULDER+PAD2' }")
        assert str(P.Key("pause")) == "PADLSHOULDER+PAD2"
        # (none of their own: the new default)
        st.padBinds = lua.eval("{}")
        assert str(P.Key("pause")) == "PADFORWARD"
    finally:
        _defaults_off(lua)
        P.ResetBinds()


def _hint_ids(lua, P, frame):
    same = lua.eval("rawequal")
    return [str(t[2]) for t in P.HintTargets().values() if same(t[1], frame)]


def test_the_pause_hint_shows_over_the_glowing_button_only_while_paused_with_a_controller(pad):
    lua, ns = pad
    P, N, G = ns.Pad, ns.Nav, ns.GPS
    _defaults_on(lua)
    try:
        P.ResetBinds()
        P.Clear()
        P.Apply()
        P.SawInput(True)
        P.ShowMarks(True)
        _a_route(lua)
        N.dest = N.stops[1]
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        b = G.PauseButton()
        assert b is not None
        assert _hint_ids(lua, P, b) == []  # (not paused: no hint)
        N.SetPaused(True, "manual")
        lua.execute("AGPS_T = AGPS_T + 1")
        G.Update()
        assert b._shown and _hint_ids(lua, P, b) == ["pause"]  # (on the bar, glowing, Start's icon over it)
        assert "Menu_" in str(P.HintText("pause"))  # (Start's own icon, as the other hints draw theirs)
        # (the minimap square's Resume button too, while it shows: the square kept beside the opened map)
        r = G.MakeMinimapResume()
        r.Show(r)
        assert _hint_ids(lua, P, r) == ["pause"]
        r.Hide(r)
        assert _hint_ids(lua, P, r) == []
        # (faded in and out as the others: the round button's pulse, Pad.HintAlpha)
        lua.execute("AGPS_NS.Pad.hintTargets = nil")
        P.hintT = 0
        P.HintTick(0.5)
        h = next(h for h in P.hints.values() if h._shown and lua.eval("rawequal")(h.target, b))
        assert abs(h.alpha - P.HintAlpha(0.5)) < 1e-9 and h.alpha > 0.9
        P.HintTick(1.0)
        assert h.alpha == 0  # (clear the rest of the period)
        # (rebound: the hint shows their button)
        assert P.Assign("pause", "PADLSHOULDER+PAD2", False) is True
        assert "LB_" in str(P.HintText("pause")) and "Menu_" not in str(P.HintText("pause"))
        # (no controller in use: no marks, no hint)
        P.SawInput(False)
        P.ShowMarks(False)
        assert _hint_ids(lua, P, b) == []
        P.SawInput(True)
        P.ShowMarks(True)
        assert _hint_ids(lua, P, b) == ["pause"]
        # (resumed: gone)
        N.SetPaused(False)
        assert _hint_ids(lua, P, b) == []
    finally:
        N.Clear()
        N.dest = None
        _defaults_off(lua)
        P.ResetBinds()


def test_the_show_hide_keys_set_key_takes_a_controller_button_too(pad):
    # (a player's report for 1.3.14: "no way to bind opening the map to a controller button through the menus"; Options >
    # Keys and buttons' Set Key took keyboard keys only. Now it waits for a controller button as well, Pad's capture: the
    # button pressed is the game's Show/Hide key, saved; Escape or B held cancels as the keyboard's Escape does)
    lua, ns = pad
    O, P = ns.Options, ns.Pad
    _game_keys(lua, game={"PADBACK": "TOGGLEGAMEMENU"})
    lua.execute("AGPS_SAVED = 0 SaveBindings = function() AGPS_SAVED = AGPS_SAVED + 1 end "
                "GetCurrentBindingSet = function() return 1 end")
    O.Show()
    holder = O.keyBinds[O.BINDING]
    b = holder.button
    try:
        b._scripts.OnClick(b, "LeftButton")
        assert P.Capturing() == "toggle" and "button" in str(b._text)
        _tap(lua, P, "PADFORWARD")  # (Start: nothing of the game's on it)
        assert lua.eval("AGPS_SETBIND.PADFORWARD") == "AZEROTHGPS_TOGGLE" and lua.eval("AGPS_SAVED") > 0
        assert P.Capturing() is None and str(b._text) == "Start"
        assert "Start opens and closes the map" in str(holder.msg._text)
        # a keyboard key as well: the button kept, both show it
        b._scripts.OnClick(b, "LeftButton")
        b._scripts.OnKeyDown(b, "M")
        assert P.Capturing() is None  # (the key taken: the controller's wait over too)
        assert lua.eval("AGPS_SETBIND.M") == "AZEROTHGPS_TOGGLE"
        assert lua.eval("AGPS_SETBIND.PADFORWARD") == "AZEROTHGPS_TOGGLE"
        # Escape cancels both waits; B held cancels the controller's (and the keyboard's) wait
        b._scripts.OnClick(b, "LeftButton")
        b._scripts.OnKeyDown(b, "ESCAPE")
        assert P.Capturing() is None and "button" not in str(b._text)
        b._scripts.OnClick(b, "LeftButton")
        _hold(lua, "PAD2")
        P.CaptureTick()
        lua.execute("AGPS_T = AGPS_T + %s" % (P.CANCEL_HOLD + 0.1))
        P.CaptureTick()
        _hold(lua, "PAD2", False)
        assert P.Capturing() is None and "button" not in str(b._text)
        assert lua.eval("AGPS_SETBIND.PAD2") is None and P.Key("toggle") == "PADFORWARD"
        # with the game's controller UI on a button press can't open it (Pad.ToggleBlocked): a keyboard key only, said so
        lua.execute("AGPS_CUI = AGPS_NS.GPS.ControllerUI AGPS_NS.GPS.ControllerUI = function() return true end")
        try:
            b._scripts.OnClick(b, "LeftButton")
            assert P.Capturing() is None and "keyboard key only" in str(holder.msg._text)
            b._scripts.OnKeyDown(b, "ESCAPE")
        finally:
            lua.execute("AGPS_NS.GPS.ControllerUI = AGPS_CUI")
        # no controller: the keyboard's alone, as ever
        lua.execute("AGPS_PAD.id = -1")
        b._scripts.OnClick(b, "LeftButton")
        assert P.Capturing() is None and str(b._text) == "Press a key..."
        b._scripts.OnKeyDown(b, "ESCAPE")
    finally:
        lua.execute("AGPS_PAD.id = 1")
        if P.Capturing():
            P.CancelCapture()
        P.ResetBinds()
        _ungame(lua)
