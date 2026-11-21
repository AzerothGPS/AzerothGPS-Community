"""Search Places from the keyboard and its pin button's art (asked 2026-11-19 for 1.3.10): while typing, Up and Down move
a highlight through the result rows (the first Down the first row, stopping at the ends), Enter takes the highlighted
row as a click on it (none highlighted: the first, as before), the highlight resets when the text changes, and the mouse
over a row moves the same highlight. The NPC rows' red "Pin" text button is a pixel-art map pin (toolicons.py's Pin and
PinLit, drawn at each size and shown pixel for pixel, no filter above LINEAR), its head brighter under the mouse; it
still pins. On both maps."""

import pytest

from azerothgps import toolicons

ENTRIES = """
  return {
    { name = "Rekkul", sub = "Poison Vendor, Orgrimmar", x = 1800.0, y = -4400.0, cont = 1, npc = 1234 },
    { name = "Red Rocks", sub = "Place", x = -1000.0, y = 500.0, cont = 1 },
    { name = "Rebel Camp", sub = "Place", x = -11000.0, y = -500.0, cont = 0, yd = 11300 },
  }
"""


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    lua.execute("AGPS_T = AGPS_T + 1")
    ns.GPS.Update()
    return lua, ns


@pytest.fixture()
def search(game):
    """The search panel open with three results; picks and pins recorded instead of made."""
    lua, ns = game
    G = ns.GPS
    lua.execute("""
      local G = AGPS_NS.GPS
      AGPS_SEARCH_REAL = { G.SearchPlaces, G.AddStopAt, G.PinSearchEntry, IsShiftKeyDown }
      AGPS_ENTRIES = (function() """ + ENTRIES + """ end)()
      AGPS_PICKED, AGPS_PINNED = {}, {}
      G.SearchPlaces = function(text) if #(text or "") < 2 then return {} end return AGPS_ENTRIES end
      G.AddStopAt = function(x, y, name) AGPS_PICKED[#AGPS_PICKED + 1] = name return true end
      G.PinSearchEntry = function(e) AGPS_PINNED[#AGPS_PINNED + 1] = e.name end
      IsShiftKeyDown = function() return false end
    """)
    panel = G.searchPanel
    assert panel is not None
    G.FocusSearch()
    type_text(panel.box, "re")
    try:
        yield lua, ns, panel
    finally:
        lua.execute("""
          local G = AGPS_NS.GPS
          G.SearchPlaces, G.AddStopAt, G.PinSearchEntry, IsShiftKeyDown = unpack(AGPS_SEARCH_REAL)
        """)
        panel.Hide(panel)


def type_text(box, text):
    box._text = text
    box._scripts.OnTextChanged(box)


def arrow(box, key):
    box._scripts.OnArrowPressed(box, key)


def rows(lua, panel):
    same = lua.eval("rawequal")
    out = [w for w in lua.eval("AGPS_WIDGETS").values() if same(w._parent, panel) and w.index is not None]
    return sorted(out, key=lambda r: r.index)


def lit(lua, panel):
    """The row numbers highlighted (shown rows whose highlight shows)."""
    return [r.index for r in rows(lua, panel) if r._shown and r.hl._shown]


def picked(lua):
    return [str(v) for v in lua.eval("AGPS_PICKED").values()]


def test_the_arrows_move_the_highlight_and_stop_at_the_ends(search):
    lua, ns, panel = search
    box = panel.box
    assert panel.sel is None and lit(lua, panel) == []
    arrow(box, "UP")  # (nothing highlighted: Up does nothing)
    assert panel.sel is None
    arrow(box, "DOWN")
    assert panel.sel == 1 and lit(lua, panel) == [1]
    arrow(box, "DOWN")
    arrow(box, "DOWN")
    assert panel.sel == 3 and lit(lua, panel) == [3]
    arrow(box, "DOWN")  # (stops at the last)
    assert panel.sel == 3 and lit(lua, panel) == [3]
    arrow(box, "UP")
    assert panel.sel == 2 and lit(lua, panel) == [2]
    arrow(box, "UP")
    arrow(box, "UP")  # (stops at the first)
    assert panel.sel == 1 and lit(lua, panel) == [1]
    # Left and Right are the text cursor's: no highlight change
    arrow(box, "LEFT")
    arrow(box, "RIGHT")
    assert panel.sel == 1
    # (the box keeps the arrow keys: its OnArrowPressed, the client's alt-arrow mode off)
    assert box._scripts.OnArrowPressed is not None


def test_enter_takes_the_highlighted_row_as_a_click_and_none_the_first(search):
    lua, ns, panel = search
    box = panel.box
    arrow(box, "DOWN")
    arrow(box, "DOWN")
    box._scripts.OnEnterPressed(box)
    assert picked(lua) == ["Red Rocks"] and not panel._shown
    # the same as a click on that row
    ns.GPS.FocusSearch()
    type_text(box, "re")
    r = rows(lua, panel)[1]
    r._scripts.OnClick(r, "LeftButton")
    assert picked(lua) == ["Red Rocks", "Red Rocks"]
    # nothing highlighted: the first, as before
    ns.GPS.FocusSearch()
    type_text(box, "re")
    box._scripts.OnEnterPressed(box)
    assert picked(lua) == ["Red Rocks", "Red Rocks", "Rekkul"]


def test_a_text_change_resets_the_highlight(search):
    lua, ns, panel = search
    box = panel.box
    arrow(box, "DOWN")
    arrow(box, "DOWN")
    assert panel.sel == 2
    type_text(box, "reb")
    assert panel.sel is None and lit(lua, panel) == []
    arrow(box, "DOWN")
    assert panel.sel == 1
    type_text(box, "")  # (no results: the arrows do nothing)
    arrow(box, "DOWN")
    assert panel.sel is None and lit(lua, panel) == []


def test_the_mouse_over_a_row_moves_the_same_highlight(search):
    lua, ns, panel = search
    box = panel.box
    arrow(box, "DOWN")
    rs = rows(lua, panel)
    rs[2]._scripts.OnEnter(rs[2])
    assert panel.sel == 3 and lit(lua, panel) == [3]
    arrow(box, "UP")  # (the keys go on from where the mouse left it)
    assert panel.sel == 2 and lit(lua, panel) == [2]
    rs[0].pin._scripts.OnEnter(rs[0].pin)  # (over a row's pin: that row)
    assert panel.sel == 1
    rs[0].pin._scripts.OnLeave(rs[0].pin)
    box._scripts.OnEnterPressed(box)
    assert picked(lua) == ["Rekkul"]


# ---------------------------------------------------------------- the pin button

def test_the_pin_is_drawn_at_each_size_with_a_red_head_and_a_silver_needle():
    for name in ("Pin", "PinLit"):
        assert name in toolicons.ICONS
        for n in toolicons.ICON_PX:
            assert toolicons.icon_file(name, n).exists()
            art = toolicons.icon(name, n)
            assert art.shape == (n, n, 4)
            rgb = art[..., :3].astype(int)
            on = art[..., 3] > 0
            red = on & (rgb[..., 0] > 140) & (rgb[..., 1] < 80) & (rgb[..., 2] < 80)
            silver = on & (abs(rgb[..., 0] - rgb[..., 2]) < 20) & (rgb[..., 0] > 110)
            assert red[: n // 2, n // 2:].sum() >= 4, (name, n)  # (the head: up right)
            assert silver[n // 2:, : n // 2].sum() >= 2, (name, n)  # (the needle: down left)
            assert not red[n // 2 + 2:, : n // 3].any(), (name, n)
    # the hovered head brighter
    for n in toolicons.ICON_PX:
        a, b = toolicons.icon("Pin", n).astype(int), toolicons.icon("PinLit", n).astype(int)
        head = (a[..., 0] > 140) & (a[..., 1] < 80)
        assert b[head][:, :3].sum() > a[head][:, :3].sum()


def test_the_pin_button_shows_the_art_pixel_for_pixel_and_still_pins(search):
    lua, ns, panel = search
    G = ns.GPS
    rs = rows(lua, panel)
    pin = rs[0].pin
    assert pin._shown and not rs[1].pin._shown  # (an NPC's row: a pin; a place without one: none)
    ppu = ns.PixelsPerUnit(panel.GetEffectiveScale(panel))
    t = pin.art
    for want, hover in (("Pin", False), ("PinLit", True), ("Pin", False)):
        if hover:
            pin._scripts.OnEnter(pin)
        else:
            pin._scripts.OnLeave(pin)
        px = t.agpsArtPx
        assert px in toolicons.ICON_PX and str(t._tex).endswith(f"\\Media\\Tools\\{want}_{px}")
        side = toolicons.canvas_side(want, px)
        assert list(t._coords.values()) == pytest.approx([0, px / side, 0, px / side])
        assert (t._w, t._h) == pytest.approx((px / ppu, px / ppu))
        assert t._filter in (None, "LINEAR", "NEAREST")
        assert t._shown and not pin.label._shown
    assert pin._w >= G.SEARCH_PIN_W and pin._h == 16  # (its hit area)
    # its tooltip: Pin, and what it does
    pin._scripts.OnEnter(pin)
    pin._scripts.OnLeave(pin)
    # still pins
    pin._scripts.OnClick(pin)
    assert [str(v) for v in lua.eval("AGPS_PINNED").values()] == ["Rekkul"]


def test_before_a_relog_the_pin_button_says_pin(search):
    lua, ns, panel = search
    G = ns.GPS
    pin = rows(lua, panel)[0].pin
    known = G.artKnown
    try:
        for name in ("Pin", "PinLit"):
            for n in toolicons.ICON_PX:
                known[G.ToolIconFile(name, n)] = False
        G.SetSearchPinArt(pin, False)
        assert not pin.art._shown and pin.label._shown and str(pin.label._text) == "Pin"
    finally:
        for name in ("Pin", "PinLit"):
            for n in toolicons.ICON_PX:
                known[G.ToolIconFile(name, n)] = None
        G.SetSearchPinArt(pin, False)
    assert pin.art._shown


def test_the_keys_on_the_world_map_too(game):
    from test_world_map_host import SETUP
    lua, ns = game
    G, st = ns.GPS, ns.settings.gps
    lua.execute(SETUP)
    was = {k: st[k] for k in ("useWorldMap", "shown", "minimized")}
    try:
        st.shown, st.minimized, st.useWorldMap = True, None, True
        G.ApplySettings()
        lua.execute("WorldMapFrame:Show()")
        G.WorldMapChanged()
        assert G.WorldMapHosted()
        lua.execute("""
          local G = AGPS_NS.GPS
          AGPS_WM_REAL = { G.SearchPlaces, G.AddStopAt }
          AGPS_ENTRIES = (function() """ + ENTRIES + """ end)()
          AGPS_PICKED = {}
          G.SearchPlaces = function(text) if #(text or "") < 2 then return {} end return AGPS_ENTRIES end
          G.AddStopAt = function(x, y, name) AGPS_PICKED[#AGPS_PICKED + 1] = name return true end
        """)
        panel = G.searchPanel
        G.FocusSearch()
        assert panel._shown
        type_text(panel.box, "re")
        arrow(panel.box, "DOWN")
        arrow(panel.box, "DOWN")
        arrow(panel.box, "DOWN")
        panel.box._scripts.OnEnterPressed(panel.box)
        assert picked(lua) == ["Rebel Camp"]
        assert rows(lua, panel)[0].pin.art._shown
    finally:
        lua.execute("""
          local G = AGPS_NS.GPS
          if AGPS_WM_REAL then G.SearchPlaces, G.AddStopAt = unpack(AGPS_WM_REAL) end
          AGPS_WM_REAL = nil
        """)
        if G.searchPanel:
            G.searchPanel.Hide(G.searchPanel)
        lua.execute("WorldMapFrame:Hide() ToggleWorldMap = nil")
        for k, v in was.items():
            st[k] = v
        G.WorldMapChanged()
        G.ApplySettings()


def test_the_controllers_dpad_steps_through_the_results_and_select_takes_one(search):
    # (Kooki3z 2026-11-20: "When search is active and controller is on, support D-pad for selecting line like arrow keys
    # do")
    lua, ns, panel = search
    P = ns.Pad
    lua.execute("""
      AGPS_PADREAL = { AGPS_NS.Pad.HeldNow, AGPS_NS.Pad.bound, AGPS_NS.Pad.MenuOpen }
      AGPS_HELD = {}
      AGPS_NS.Pad.HeldNow = function(id) return AGPS_HELD[id] end
      AGPS_NS.Pad.bound = true
      AGPS_NS.Pad.MenuOpen = function() return false end
    """)
    G = ns.GPS
    try:
        view0 = tuple(G.PadView())[:2]
        held = lua.eval("AGPS_HELD")
        held.panDown = True
        P.Tick(0.016)
        assert lit(lua, panel) == [1]  # (a press: one step)
        P.Tick(0.1)
        assert lit(lua, panel) == [1]  # (held: not yet repeating)
        P.Tick(0.3)
        assert lit(lua, panel) == [2]  # (held past the first wait: the next)
        held.panDown = None
        P.Tick(0.016)
        held.panUp = True
        P.Tick(0.016)
        assert lit(lua, panel) == [1]
        held.panUp = None
        P.Tick(0.016)
        assert tuple(G.PadView())[:2] == view0  # (the map wasn't panned meanwhile)
        # Select: the highlighted row, as Enter
        assert P.Run(lua.table("select"), True)
        assert list(lua.eval("AGPS_PICKED").values()) == ["Rekkul"]
    finally:
        lua.execute("AGPS_NS.Pad.HeldNow, AGPS_NS.Pad.bound, AGPS_NS.Pad.MenuOpen = unpack(AGPS_PADREAL)")
