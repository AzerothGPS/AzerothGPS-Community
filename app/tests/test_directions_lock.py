"""The directions text's own lock (1.3.9, asked 2026-11-18: "add a separate lock option for the directions text than the
arrow, update the tutorial for that"): `arrowLocked` locks the arrow alone, `dirLocked` the directions text alone, each
window dragged, sized, right-clicked and clicked through by its own lock; the old shared lock's value carried over to the
text's once, at load and for each profile; both kept over a /reload."""

import pytest


def _start(saved=None):
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    return start(saved=saved)


@pytest.fixture(scope="module")
def game():
    lua, ns = _start()
    # (recorded: the stand-in's are no-ops)
    for name in ("AzerothGPSArrow", "AzerothGPSDirections"):
        lua.execute(f"""
          {name}.SetMovable = function(s, v) s._movable = v end
          {name}.SetResizable = function(s, v) s._resizable = v end
          {name}.EnableMouse = function(s, v) s._mouse = v end
          {name}.StartMoving = function(s) AGPS_MOVED = s end
          {name}.StartSizing = function(s) AGPS_SIZED = s end
        """)
    return lua, ns


_KEYS = ("arrow", "arrowLocked", "dirLocked", "dirShown", "arrowSnap", "arrowSide", "arrowFreePoint",
         "clickThroughCombat", "clickThroughMoving")


@pytest.fixture
def arrow(game):
    lua, ns = game
    st = ns.settings.gps
    saved = {k: st[k] for k in _KEYS}
    st.arrow, st.dirShown, st.arrowSnap, st.arrowSide = True, True, True, "left"
    st.clickThroughCombat, st.clickThroughMoving = False, False
    yield lua, ns, st
    for k, v in saved.items():
        st[k] = v
    if ns.Arrow.lockAsk:
        ns.Arrow.lockAsk.Hide(ns.Arrow.lockAsk)
    if ns.Arrow.lockTold:
        ns.Arrow.lockTold.Hide(ns.Arrow.lockTold)
    lua.execute("AGPS_MOVED, AGPS_SIZED = nil, nil")
    ns.Arrow.sizing = None
    ns.Arrow.Apply()


def _drag(lua, f):
    lua.execute("AGPS_MOVED = nil")
    f._scripts.OnDragStart(f)
    moved = lua.eval("AGPS_MOVED")
    f._scripts.OnDragStop(f)
    return moved is not None and lua.eval("function(a, b) return rawequal(a, b) end")(moved, f)


def _size(lua, ns):
    A = ns.Arrow
    lua.execute("AGPS_SIZED = nil")
    A.sizing = None
    A.grip._scripts.OnMouseDown(A.grip)
    sized = lua.eval("AGPS_SIZED") is not None
    if A.sizing:
        A.grip._scripts.OnMouseUp(A.grip)
    return sized


def _mouse(lua, ns):
    # (the windows' clicks, from the next text update)
    # (with no route they're placed with Options open: closed, the placeholder is hidden, 1.3.11)
    A = ns.Arrow
    ns.Options.Show()
    A.Apply()
    A.still = False
    A.frame._scripts.OnUpdate(A.frame, 1)
    lua.execute("AzerothGPSOptions:Hide()")
    return A.frame._mouse, A.dir._mouse


def test_the_defaults_and_the_option(game):
    lua, ns = game
    assert ns.DEFAULTS.gps.arrowLocked is False and ns.DEFAULTS.gps.dirLocked is False
    ns.Options.Show()  # (its pages built)
    keys = {c.key: c.page for c in ns.Options.settingControls.values() if not c.mirror}
    lua.execute("AzerothGPSOptions:Hide()")
    assert keys["arrowLocked"] == "Directions" and keys["dirLocked"] == "Directions"


@pytest.mark.parametrize("arrow_locked", [True, False])
def test_each_lock_blocks_only_its_own_windows_drag_and_resize(arrow, arrow_locked):
    lua, ns, st = arrow
    A = ns.Arrow
    st.arrowLocked, st.dirLocked = arrow_locked, not arrow_locked
    A.Apply()
    af, df = A.frame, A.dir
    assert af._movable is (not arrow_locked) and df._movable is arrow_locked
    assert df._resizable is arrow_locked
    assert A.grip._shown is arrow_locked  # (the directions' corner: the text's lock)
    # dragged: only the unlocked one moves
    assert _drag(lua, df) is arrow_locked
    st.arrowSnap = True
    A.Apply()
    assert _drag(lua, af) is (not arrow_locked)
    assert A.Snapped() is arrow_locked  # (the arrow dragged off the text only while it's unlocked)
    # sized by the directions' corner: only while the text is unlocked
    st.arrowSnap = True
    A.Apply()
    assert _size(lua, ns) is arrow_locked
    # clicks: a locked window passes them through to the game world, the other takes them
    assert _mouse(lua, ns) == (not arrow_locked, arrow_locked)


def test_both_locked_and_both_unlocked(arrow):
    lua, ns, st = arrow
    A = ns.Arrow
    st.arrowLocked, st.dirLocked = True, True
    A.Apply()
    assert not _drag(lua, A.dir) and not _drag(lua, A.frame) and not _size(lua, ns)
    assert _mouse(lua, ns) == (False, False)
    st.arrowLocked, st.dirLocked = False, False
    A.Apply()
    assert _drag(lua, A.dir) and _size(lua, ns)
    assert _mouse(lua, ns) == (True, True)


def test_a_right_click_asks_to_lock_only_that_window(arrow):
    lua, ns, st = arrow
    A = ns.Arrow
    click = lambda b: b._scripts.OnClick(b)  # noqa: E731
    text = lambda f: lua.eval("function(f) return f.text:GetText() end")(f)  # noqa: E731
    st.arrowLocked, st.dirLocked = False, False
    A.Apply()
    # the directions text: asked about the text, Yes locks it alone and says where its option is
    A.dir._scripts.OnMouseUp(A.dir, "RightButton")
    assert text(A.lockAsk) == "Lock the directions text in place here?"
    click(A.lockAsk.yes)
    assert st.dirLocked is True and st.arrowLocked is False
    assert text(A.lockTold) == "Locked. To unlock it later: Options > Directions > Lock directions text position."
    click(A.lockTold.yes)
    assert A.AskLock(A.dir) is None  # (locked: nothing to ask)
    # the arrow: asked about the arrow, Yes locks it alone
    A.frame._scripts.OnMouseUp(A.frame, "RightButton")
    assert text(A.lockAsk) == "Lock the arrow in place here?"
    st.dirLocked = False
    click(A.lockAsk.yes)
    assert st.arrowLocked is True and st.dirLocked is False
    assert text(A.lockTold) == "Locked. To unlock it later: Options > Directions > Lock arrow position."
    click(A.lockTold.yes)
    assert A.AskLock(A.frame) is None and A.AskLock(A.dir) is not None


def test_the_slash_command_locks_all_or_one(arrow):
    lua, ns, st = arrow
    slash = lua.eval("SlashCmdList.AZEROTHGPS")
    was = st.locked
    try:
        slash("unlock")
        assert (st.locked, st.arrowLocked, st.dirLocked) == (False, False, False)
        slash("lock directions")
        assert (st.locked, st.arrowLocked, st.dirLocked) == (False, False, True)
        slash("lock arrow")
        assert (st.locked, st.arrowLocked, st.dirLocked) == (False, True, True)
        slash("unlock text")
        assert (st.locked, st.arrowLocked, st.dirLocked) == (False, True, False)
        slash("lock")
        assert (st.locked, st.arrowLocked, st.dirLocked) == (True, True, True)
        slash("unlock map")
        assert (st.locked, st.arrowLocked, st.dirLocked) == (False, True, True)
    finally:
        st.locked = was
        ns.GPS.ApplySettings()


def test_the_old_unlock_offer_unlocks_and_locks_both(arrow):
    lua, ns, st = arrow
    A, db = ns.Arrow, ns.db
    was = (db.arrowUnlockOffered, ns.inCombat)
    try:
        ns.inCombat = False
        st.arrowLocked, st.dirLocked, db.arrowUnlockOffered = True, True, None
        ask = A.OfferUnlock()
        assert ask is not None and st.arrowLocked is False and st.dirLocked is False
        ask.no._scripts.OnClick(ask.no)  # (Lock)
        assert st.arrowLocked is True and st.dirLocked is True
        # only the text locked (a choice made since the split): offered too
        st.arrowLocked, st.dirLocked, db.arrowUnlockOffered = False, True, None
        ask = A.OfferUnlock()
        assert ask is not None and st.dirLocked is False
        ask.yes._scripts.OnClick(ask.yes)  # (Leave Unlocked)
        assert st.arrowLocked is False and st.dirLocked is False
    finally:
        db.arrowUnlockOffered, ns.inCombat = was
        if A.unlockAsk:
            A.unlockAsk.answered = True
            A.unlockAsk.Hide(A.unlockAsk)


def test_the_split_carries_the_old_shared_lock_over_once(game):
    lua, ns = game
    t = lua.eval("{ arrowLocked = true }")
    ns.SplitDirLock(t)
    assert t.dirLocked is True
    t = lua.eval("{ arrowLocked = false }")
    ns.SplitDirLock(t)
    assert t.dirLocked is False
    t = lua.eval("{ arrowLocked = true, dirLocked = false }")  # (set apart since: kept)
    ns.SplitDirLock(t)
    assert t.dirLocked is False
    ns.SplitDirLock(None)  # (no settings yet: nothing)


@pytest.mark.parametrize("old", [True, False])
def test_a_save_from_before_the_split_starts_the_text_locked_as_the_arrow_was(old):
    v = "true" if old else "false"
    lua, ns = _start(f"AzerothGPSDB = {{ settings = {{ gps = {{ arrowLocked = {v} }} }},"
                     f" profiles = {{ Other = {{ gps = {{ arrowLocked = {v} }} }} }} }}")
    st = ns.settings.gps
    assert st.arrowLocked is old and st.dirLocked is old
    assert ns.db.settings.gps.dirLocked is old  # (saved: its own from now on)
    # a profile from before: the same, when it's used
    assert ns.UseProfile("Other") is True
    assert ns.settings.gps.arrowLocked is old and ns.settings.gps.dirLocked is old
    ns.UseProfile(None)
    # unlocked apart after: the arrow's lock no longer moves the text's
    st.arrowLocked = not old
    assert st.dirLocked is old


@pytest.mark.parametrize("arrow_locked,dir_locked", [(True, False), (False, True)])
def test_the_two_locks_are_kept_over_a_reload(arrow_locked, dir_locked):
    a, d = ("true" if arrow_locked else "false"), ("true" if dir_locked else "false")
    lua, ns = _start(f"AzerothGPSDB = {{ settings = {{ gps = {{ arrowLocked = {a}, dirLocked = {d} }} }} }}")
    st = ns.settings.gps
    assert st.arrowLocked is arrow_locked and st.dirLocked is dir_locked
    A = ns.Arrow
    assert A.Locked(A.frame) is arrow_locked and A.Locked(A.dir) is dir_locked
    assert A.grip._shown is (not dir_locked)


def test_with_no_route_the_unlocked_placeholder_shows_only_while_options_is_open(arrow):
    # (1.3.10, a player: "I did not find the option to turn off the arrow when I'm not following any routes". Unlocked,
    # the default, its "No route" placeholder showed all the time; now only while Options (or the tutorial) is open,
    # where it's placed and sized.)
    lua, ns, st = arrow
    A = ns.Arrow
    st.arrowLocked, st.dirLocked = False, False
    ns.Nav.Clear()
    win = lua.globals().AzerothGPSArrow

    def tick():
        A.still = False
        win._scripts.OnUpdate(win, 1)
        return win._alpha, A.dir._alpha

    if ns.Options.IsShown():
        ns.Options.Toggle()
    assert tick() == (0, 0)
    ns.Options.Show()
    a, d = tick()
    assert a > 0 and d > 0
    ns.Options.Toggle()
    assert ns.Options.IsShown() is False and tick() == (0, 0)
