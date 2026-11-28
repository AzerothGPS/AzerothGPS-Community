"""The detached route panel locked is click-through (1.4.2, Kooki3z: "on route panel detach, when locked, make it click
through like the directions are when locked"): locked (`navPanelLocked`, detached), the panel and every frame in it take
no clicks, wheel or mouse over, so the mouse goes to the game world; unlocked, or put back on the map, they take it as
before; kept over a /reload. The use and target buttons are the game's secure buttons on UIParent, not the panel's: they
still take clicks, as on the locked directions text (Arrow.lua)."""

import pytest

from test_map_redraw import game  # noqa: F401
from test_route_panel import _detach, rp  # noqa: F401

# (the stand-in's mouse calls are no-ops: recorded here as the game's are. EnableMouse sets clicks and mouse over
# both; a Button takes the mouse till it's told not to, a Frame doesn't)
RECORD = """
AGPS_WMT = getmetatable(WorldFrame)
AGPS_IDX = AGPS_IDX or AGPS_WMT.__index
local REC = {
  EnableMouse = function(s, v) s._click = v and true or false s._motion = s._click end,
  SetMouseClickEnabled = function(s, v) s._click = v and true or false end,
  SetMouseMotionEnabled = function(s, v) s._motion = v and true or false end,
  EnableMouseWheel = function(s, v) s._wheel = v and true or false end,
  IsMouseClickEnabled = function(s) if s._click == nil then return s._kind == "Button" end return s._click end,
  IsMouseMotionEnabled = function(s) if s._motion == nil then return s._kind == "Button" end return s._motion end,
  IsMouseWheelEnabled = function(s) return s._wheel or false end,
}
REC.IsMouseEnabled = function(s) return REC.IsMouseClickEnabled(s) or REC.IsMouseMotionEnabled(s) end
AGPS_WMT.__index = function(s, k) return REC[k] or AGPS_IDX(s, k) end
"""


@pytest.fixture
def rec(rp):  # noqa: F811
    lua, ns = rp
    lua.execute(RECORD)
    yield lua, ns
    lua.execute("AGPS_WMT.__index = AGPS_IDX AGPS_IDX = nil")


def _frames(p):
    # (the panel and every frame in it)
    out, todo = [], [p]
    while todo:
        f = todo.pop()
        out.append(f)
        todo.extend((f._kids or {}).values())
    return out


def _mouse(f):
    return f.IsMouseClickEnabled(f), f.IsMouseMotionEnabled(f), f.IsMouseWheelEnabled(f)


def _key(f):
    return str(f)  # (the Lua table's address: the same frame however it's reached)


def _taken(ns):
    # (each frame of the panel that takes the mouse, by its Lua table: (clicks, mouse over, wheel))
    return {_key(f): _mouse(f) for f in _frames(ns.GPS.navPanel) if any(_mouse(f))}


def test_locked_it_takes_no_mouse_and_unlocked_it_does_again(rec):
    lua, ns = rec
    G, st = ns.GPS, ns.settings.gps
    p = _detach(lua, ns, navPanelLocked=False)
    assert not G.NavLocked()
    unlocked = _taken(ns)
    # unlocked: as today, the panel (dragged, right-clicked) and its buttons take the mouse
    assert _mouse(p)[:2] == (True, True)
    for b in (G.navCancel, G.navDetach, G.navLock, G.stepsToggle, G.stepsMore, G.navGrip):
        assert _mouse(b)[:2] == (True, True)
    # locked by its padlock: the panel and everything in it click-through (clicks, mouse over, wheel)
    G.navLock._scripts.OnClick(G.navLock, "LeftButton")
    assert G.NavLocked() and st.navPanelLocked is True
    assert _taken(ns) == {}
    assert len(_frames(p)) > 8  # (its buttons, grip and edge looked at, not the panel alone)
    # (laid out again, settings applied again: still click-through)
    G.navPanelSig = None
    G.ApplySettings()
    G.Update()
    assert _taken(ns) == {}
    # (a quest row's Leave Out made while it's locked: click-through too)
    row = G.MakeGroupRow(p)
    assert not any(_mouse(row)) and not any(_mouse(row.button))
    # unlocked in the options: back as it was, the row's button with them
    st.navPanelLocked = False
    G.ApplySettings()
    assert not G.NavLocked()
    back = _taken(ns)
    assert {k: v for k, v in back.items() if k in unlocked} == unlocked
    assert _mouse(row.button)[:2] == (True, True)
    assert _mouse(p)[:2] == (True, True)


def test_put_back_on_the_map_while_locked_its_buttons_take_clicks_again(rec):
    lua, ns = rec
    G, st = ns.GPS, ns.settings.gps
    p = _detach(lua, ns, navPanelLocked=True)
    assert G.NavLocked() and _taken(ns) == {}
    st.navPanelDetached = False
    G.ApplySettings()
    assert not G.NavLocked()
    assert _mouse(p)[:2] == (False, False)  # (on the map the panel itself takes no mouse: the map under it drags)
    for b in (G.navCancel, G.navDetach, G.stepsToggle):
        assert _mouse(b)[:2] == (True, True)
    # detached again, still locked: click-through again
    st.navPanelDetached = True
    G.ApplySettings()
    assert G.NavLocked() and _taken(ns) == {}


def test_the_use_and_target_buttons_are_not_the_panels(rec):
    # (as on the locked directions text: the secure use and target buttons still take clicks)
    lua, ns = rec
    G = ns.GPS
    _detach(lua, ns, navPanelLocked=True)
    inside = {_key(f) for f in _frames(G.navPanel)}
    for b in (G.useBtn, G.targetBtn):
        if b is not None:
            assert _key(b) not in inside


def test_locked_and_click_through_after_a_reload():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start(pre=RECORD.replace("AGPS_IDX or ", ""),
                    saved="AzerothGPSDB = { settings = { gps = { navPanelDetached = true, navPanelLocked = true } } }")
    G = ns.GPS
    assert ns.settings.gps.navPanelLocked is True and G.navDetached and G.NavLocked()
    assert _taken(ns) == {}
    ns.settings.gps.navPanelLocked = False
    G.ApplySettings()
    assert _mouse(G.navPanel)[:2] == (True, True) and _mouse(G.navCancel)[:2] == (True, True)
