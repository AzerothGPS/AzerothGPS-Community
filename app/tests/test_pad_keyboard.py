"""Search Places with a controller (PadKeys.lua; Kooki3z 2026-11-20: "How difficult would it be to add a qwerty
keyboard to search for controller users? can we also support keyboards in other languages?", and on a screenshot of
the search panel: "legend for search controls in purple, keyboard in green (X or open/close keyboard or something like
that, A fading on highlighted letter, D-Pad also closes keyboard and navigates the list)"). A legend of the search's
buttons over the panel and an on-screen keyboard under it, only with the controller in use; the D-pad moves on the keys
(never a stick: "We can't take left stick unfortunately it moves the character"), up from the top row into the list;
A types, B deletes (closes the search with the keyboard shut), X opens and closes it. The keys by the addon's language,
Korean composing syllables; the caps pixel art (keyicons.py: "Keep keyboard themed with pixel art buttons like the
controller"). And the player moving closes the controller's map menu and the search ("it moves the character, which
btw would and should close map menu")."""
import struct

import pytest

from azerothgps import keyicons
from azerothgps.paths import ADDON_DIR

from test_controller import pad, _plain  # noqa: F401 (the fixture)
from test_search_keys import ENTRIES, arrow, lit

lupa = pytest.importorskip("lupa")


# ---------------------------------------------------------------- text: UTF-8 and Hangul

@pytest.fixture(scope="module")
def keys():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    return lua, ns.PadKeys


def _ko(K, jamo, text=""):
    for j in jamo:
        text = K.HangulType(text, j)
    return text


@pytest.mark.parametrize("jamo, want", [
    ("ㅎㅏㄴ", "한"),
    ("ㄱㅡㄹ", "글"),
    ("ㅎㅏㄴㄱㅡㄹ", "한글"),
    ("ㅎㅏㄴㅏ", "하나"),  # (a vowel after a final: the final moves on)
    ("ㄷㅏㄹㄱ", "닭"),  # (a double final)
    ("ㄷㅏㄹㄱㅏ", "달가"),  # (a double final's second half moves on)
    ("ㄱㅗㅏ", "과"),  # (a compound vowel)
    ("ㅇㅗㅏㄴ", "완"),
    ("ㅅㅓㅇㅜㄹ", "서울"),
    ("ㄱ", "ㄱ"),
    ("ㄱㄴ", "ㄱㄴ"),  # (two consonants alone: no syllable)
    ("ㅏ", "ㅏ"),
])
def test_korean_jamo_compose_into_syllables(keys, jamo, want):
    lua, K = keys
    assert _ko(K, jamo) == want


def test_korean_delete_takes_the_last_jamo_off(keys):
    lua, K = keys
    steps = []
    text = "닭"
    while text:
        text = K.HangulBack(text)
        steps.append(text)
    assert steps == ["달", "다", "ㄷ", ""]
    assert K.HangulBack("과") == "고" and K.HangulBack("하나") == "하ㄴ" and K.HangulBack("ab") == "a"


def test_delete_takes_a_whole_utf8_character(keys):
    lua, K = keys
    assert K.BackText("Straße", False) == "Straß"
    assert K.BackText("Straß", False) == "Stra"
    assert K.BackText("ёлка", False) == "ёлк" and K.BackText("é", False) == "" and K.BackText("", False) == ""
    assert K.Len("ñandú") == 5
    # (the box's 40 letters, counted as characters)
    full = "ä" * 40
    assert K.TypeText(full, "b", False) == full and K.TypeText("ä" * 39, "ö", False) == "ä" * 39 + "ö"


# ---------------------------------------------------------------- layouts

def _layout(code):
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start(locale=code)
    rows, hangul = ns.PadKeys.Rows()
    out = []
    for r in rows.values():
        out.append([str(k.ch) if k.ch else str(k.kind) for k in r.values()])
    return out, hangul


@pytest.mark.parametrize("code, first, has", [
    ("enUS", "qwertyuiop", ""),
    ("enGB", "qwertyuiop", ""),
    ("deDE", "qwertzuiopü", "äöüß"),
    ("frFR", "azertyuiop", "éèàçù"),
    ("esES", "qwertyuiop", "ñáéíóúü"),
    ("esMX", "qwertyuiop", "ñáéíóúü"),
    ("itIT", "qwertyuiop", "àèéìòù"),
    ("ptBR", "qwertyuiop", "çáâãéêíóôõú"),
    ("ruRU", "йцукенгшщзхъ", "ёэ"),
    ("koKR", "ㅂㅈㄷㄱㅅㅛㅕㅑㅐㅔ", "ㅃㅉㄸㄲㅆㅒㅖ"),
    ("zhCN", "qwertyuiop", ""),  # (Chinese needs an input method: the Latin keys for now)
    ("zhTW", "qwertyuiop", ""),
])
def test_the_keys_follow_the_games_language(code, first, has):
    rows, hangul = _layout(code)
    assert "".join(rows[0]) == first
    letters = "".join("".join(r) for r in rows[:-1])
    assert all(c in letters for c in has), (code, has)
    assert rows[-1] == ["space", "back", "done"]
    assert hangul == (code == "koKR")
    if code == "frFR":
        assert "".join(rows[1]) == "qsdfghjklm" and "".join(rows[2]).startswith("wxcvbn")
    if code == "deDE":
        assert "".join(rows[2]).startswith("yxcvbnm")


# ---------------------------------------------------------------- the key caps' art

def _tga_size(path):
    return struct.unpack("<HH", path.read_bytes()[12:16])


def test_the_caps_are_ours_up_to_date_and_drawn_at_the_size_shown(keys):
    lua, K = keys
    assert list(K.ART_PX.values()) == list(keyicons.ICON_PX)
    assert dict(K.ART_WIDE.items()) == keyicons.WIDE
    for name in keyicons.ICONS:
        for n in keyicons.ICON_PX:
            f = keyicons.icon_file(name, n)
            assert f.parent == ADDON_DIR / "Media" / "Keyboard" and f.is_file(), f
            w, h = keyicons.canvas_size(name, n)
            assert _tga_size(f) == (w, h) and w & (w - 1) == 0 and h & (h - 1) == 0, f  # (powers of two)
            assert f.read_bytes() == keyicons.tga_rgba(keyicons.on_canvas(name, n)), f
            art = keyicons.icon(name, n)
            assert art.shape == (n, keyicons.wide(name) * n, 4)
    shipped = {p.name for p in (ADDON_DIR / "Media" / "Keyboard").iterdir()}
    assert shipped == {keyicons.icon_file(n, px).name for n in keyicons.ICONS for px in keyicons.ICON_PX}
    # (lit: a gold rim; not lit: a dark outline)
    for n in keyicons.ICON_PX:
        a, b = keyicons.icon("Key", n), keyicons.icon("KeyLit", n)
        assert tuple(b[0, n // 2, :3]) == (255, 209, 0) and tuple(a[0, n // 2, :3]) == keyicons.OUTLINE


# ---------------------------------------------------------------- on the map, with the pad

@pytest.fixture()
def kb(pad):  # noqa: F811
    """The pad bound and in use, the search open with three results for 2+ letters; picks recorded, not made."""
    lua, ns = pad
    lua.execute("""
      local G = AGPS_NS.GPS
      AGPS_ENTRIES = (function() """ + ENTRIES + """ end)()
      AGPS_PICKED, AGPS_SEARCHED = {}, {}
      G.SearchPlaces = function(text)
        AGPS_SEARCHED[#AGPS_SEARCHED + 1] = text
        if #(text or "") < 2 then return {} end
        return AGPS_ENTRIES
      end
      G.AddStopAt = function(x, y, name) AGPS_PICKED[#AGPS_PICKED + 1] = name return true end
      AGPS_MOVING = false
      G.PlayerMoving = function() return AGPS_MOVING end
    """)
    P, G = ns.Pad, ns.GPS
    assert P.Apply()
    P.Tick(0.016)
    yield lua, ns, G.searchPanel


def _tick(P, *dts):
    for dt in dts or (0.016,):
        P.Tick(dt)


def _press(lua, key, down=True):
    return lua.eval("AGPS_PRESS")(key, down)


def _tap(lua, P, key):
    _press(lua, key, True)
    P.Tick(0.016)
    _press(lua, key, False)
    P.Tick(0.016)


def _open_search(ns, text=None):
    G = ns.GPS
    G.FocusSearch()
    if text is not None:
        G.SearchSetText(text)
    ns.Pad.Tick(0.016)


def _text(panel):
    return str(panel.box._text)


def _same(lua, a, b):
    return lua.eval("rawequal")(a, b)


def _at(K):
    return (K.at[1], K.at[2])


def test_the_legend_shows_with_the_search_open_and_the_pad_in_use(kb):
    lua, ns, panel = kb
    P, K = ns.Pad, ns.PadKeys
    assert not (K.legend and K.legend._shown)  # (no search: no legend)
    _open_search(ns)
    lg = K.legend
    assert lg._shown and _same(lua, lg._parent, panel)
    assert _same(lua, lg._pts["BOTTOMLEFT"][2], panel) and lg._pts["BOTTOMLEFT"][3] == "TOPLEFT"  # (over the panel)
    assert _plain(lg.text._text) == "D-pad: Choose   A: Pick   X: Keyboard   B: Close"
    # (the player's own buttons: X's control moved to Y's button)
    assert P.Assign("menu", "PADFORWARD") is True and P.Assign("pause", "PADPADDLE1") is True
    assert P.Assign("remove", "PAD4") is True
    _tick(P)
    assert "Y: Keyboard" in _plain(lg.text._text)
    _tap(lua, P, "PAD4")
    assert K.open and K.frame._shown
    # the mouse in use: gone, the keyboard too
    P.SawInput(False)
    _tick(P)
    assert not lg._shown and not K.open and not K.frame._shown
    panel.Hide(panel)
    _tick(P)
    assert not lg._shown


def test_a_mouse_player_sees_nothing_new(kb):
    lua, ns, panel = kb
    P, K = ns.Pad, ns.PadKeys
    P.SawInput(False)
    _open_search(ns, "re")
    assert not (K.legend and K.legend._shown) and not K.open
    assert P.Run(lua.table("remove"), True) is not True or not K.open  # (X: not the keyboard's)
    assert not K.open


def test_x_opens_and_closes_the_keyboard_under_the_panel(kb):
    lua, ns, panel = kb
    P, K = ns.Pad, ns.PadKeys
    _open_search(ns)
    _tap(lua, P, "PAD3")
    f = K.frame
    assert K.open and f._shown and _same(lua, f._parent, panel)
    assert _same(lua, f._pts["TOPLEFT"][2], panel) and f._pts["TOPLEFT"][3] == "BOTTOMLEFT"  # (under it)
    assert _plain(K.legend.text._text) == "D-pad: Move   A: Type   X: Close Keyboard   B: Delete"
    # the keys: pixel-art caps, the letters as text over them
    keys = [k for k in f["keys"].values() if k._shown]
    assert [str(k.label._text) for k in keys[:10]] == list("qwertyuiop")
    assert {str(k.cap.name) for k in keys} == {"Key", "KeyLit", "Key2", "Key4"}
    assert [str(k.label._text) for k in keys[-3:]] == ["Space", "Delete", "Done"]
    lit_keys = [k for k in keys if k.lit]
    assert len(lit_keys) == 1 and str(lit_keys[0].cap.name) == "KeyLit"
    px = f.px
    assert str(lit_keys[0].cap._tex).endswith(f"\\Media\\Keyboard\\KeyLit_{px}")
    # (the A button's icon on the lit key, pulsing gently)
    assert _same(lua, f.hint._parent, lit_keys[0]) and _plain(f.hint.text._text) == "A" and f.hint._shown
    assert K.PulseAlpha(0) == pytest.approx(1) and K.PulseAlpha(K.PULSE / 2) == pytest.approx(0.3)
    _tap(lua, P, "PAD3")
    assert not K.open and not f._shown


def test_the_dpad_moves_the_lit_key_and_repeats_while_held(kb):
    lua, ns, panel = kb
    P, K = ns.Pad, ns.PadKeys
    _open_search(ns)
    _tap(lua, P, "PAD3")
    K.at[1], K.at[2] = 1, 1
    K.Light()
    view0 = tuple(ns.GPS.PadView())[:2]
    _press(lua, "PADDRIGHT")
    _tick(P)
    assert _at(K) == (1, 2)  # (a press: one key)
    _tick(P, 0.1)
    assert _at(K) == (1, 2)  # (held: not yet repeating)
    _tick(P, 0.3)
    assert _at(K) == (1, 3)  # (past the first wait: the next)
    _tick(P, 0.1)
    assert _at(K) == (1, 4)
    _press(lua, "PADDRIGHT", False)
    _tick(P)
    _tap(lua, P, "PADDDOWN")
    assert _at(K) == (2, 4)  # (r -> f: the key below)
    _tap(lua, P, "PADDLEFT")
    assert _at(K) == (2, 3)
    for _ in range(3):
        _tap(lua, P, "PADDDOWN")
    assert K.at[1] == 4 and str(K.Key().kind) == "space"  # (the bottom row: Space, Delete, Done)
    _tap(lua, P, "PADDDOWN")
    assert K.at[1] == 4  # (nothing below)
    assert tuple(ns.GPS.PadView())[:2] == view0  # (the map wasn't panned meanwhile)


def test_a_types_the_lit_key_and_the_results_follow(kb):
    lua, ns, panel = kb
    P, K = ns.Pad, ns.PadKeys
    _open_search(ns)
    _tap(lua, P, "PAD3")
    K.at[1], K.at[2] = 1, 4  # (r)
    _tap(lua, P, "PAD1")
    K.at[1], K.at[2] = 1, 3  # (e)
    _tap(lua, P, "PAD1")
    assert _text(panel) == "re"
    assert str(lua.eval("AGPS_SEARCHED[#AGPS_SEARCHED]")) == "re"
    assert ns.GPS.SearchCount() == 3  # (the results shown)
    K.at[1], K.at[2] = 4, 1  # (Space)
    _tap(lua, P, "PAD1")
    assert _text(panel) == "re "
    K.at[1], K.at[2] = 4, 3  # (Done: the keyboard closed)
    _tap(lua, P, "PAD1")
    assert not K.open and _text(panel) == "re "


def test_b_deletes_a_whole_letter_and_closes_the_search_with_the_keyboard_shut(kb):
    lua, ns, panel = kb
    P, K = ns.Pad, ns.PadKeys
    _open_search(ns, "Straße")
    _tap(lua, P, "PAD3")
    _tap(lua, P, "PAD2")
    assert _text(panel) == "Straß"
    _tap(lua, P, "PAD2")
    assert _text(panel) == "Stra" and panel._shown
    K.at[1], K.at[2] = 4, 2  # (the Delete key: the same)
    _tap(lua, P, "PAD1")
    assert _text(panel) == "Str"
    _tap(lua, P, "PAD3")  # (the keyboard shut: B closes the search)
    _tap(lua, P, "PAD2")
    assert not panel._shown and not K.legend._shown


def test_up_from_the_top_row_goes_into_the_list_and_x_comes_back_on_the_same_key(kb):
    lua, ns, panel = kb
    P, K = ns.Pad, ns.PadKeys
    _open_search(ns, "re")
    _tap(lua, P, "PAD3")
    K.at[1], K.at[2] = 2, 5
    K.Light()
    _tap(lua, P, "PADDUP")
    assert K.open and _at(K) == (1, 5)
    _tap(lua, P, "PADDUP")
    assert not K.open and not K.frame._shown
    assert lit(lua, panel) == [3]  # (the list's last row, the one nearest the keyboard)
    _tap(lua, P, "PADDUP")
    assert lit(lua, panel) == [2]  # (the D-pad walks the list now)
    _tap(lua, P, "PAD3")
    assert K.open and _at(K) == (1, 5) and lit(lua, panel) == []
    _tap(lua, P, "PAD3")
    _tap(lua, P, "PADDDOWN")
    assert lit(lua, panel) == [1]
    _tap(lua, P, "PAD1")  # (A with the keyboard shut: the row picked)
    assert [str(v) for v in lua.eval("AGPS_PICKED").values()] == ["Rekkul"]


def test_the_search_beats_the_map_menu_it_was_opened_from(kb):
    lua, ns, panel = kb
    P, K = ns.Pad, ns.PadKeys
    assert P.OpenMenu() and P.MenuOpen()
    _open_search(ns, "re")
    _tap(lua, P, "PADDDOWN")
    assert lit(lua, panel) == [1] and P.focus is None  # (the list's, not the menu's ring)
    _tap(lua, P, "PAD3")
    assert K.open


def test_moving_the_character_closes_the_map_menu_and_the_search(kb):
    lua, ns, panel = kb
    P, K = ns.Pad, ns.PadKeys
    G = ns.GPS
    assert P.OpenMenu() and P.MenuOpen()
    # (the D-pad pans: the view only, the player still; nothing closes)
    lua.execute("AzerothGPSFrame:Show()")
    _tick(P, 0.016, 0.3)
    assert P.MenuOpen()
    lua.execute("AGPS_MOVING = true")
    _tick(P)
    assert not P.MenuOpen()
    # moving on: a menu opened meanwhile stays till the next start
    assert P.OpenMenu()
    _tick(P)
    assert P.MenuOpen()
    lua.execute("AGPS_MOVING = false")
    _tick(P)
    P.CloseMenu()
    _open_search(ns, "re")
    _tap(lua, P, "PAD3")
    assert K.open and panel._shown
    _press(lua, "PADDRIGHT")  # (moving on the keys: not the player)
    _tick(P, 0.016, 0.3)
    _press(lua, "PADDRIGHT", False)
    _tick(P)
    assert panel._shown and K.open
    lua.execute("AGPS_MOVING = true")
    _tick(P)
    assert not panel._shown
    _tick(P)
    assert not K.open and not K.frame._shown
    # the mouse in use: its menu keeps its own timer
    lua.execute("AGPS_MOVING = false")
    _tick(P)
    G.mapMenu.Show(G.mapMenu)
    P.SawInput(False)
    lua.execute("AGPS_MOVING = true")
    _tick(P)
    assert G.mapMenu._shown


# ---------------------------------------------------------------- Find Herbs and Ore, the same way
# (Kooki3z 2026-11-20, of the Find Herbs and Ore window: "add D pad controller and keyboard functions to this too"; its
# box's arrow keys as Search Places': Up and Down move a highlight through the rows, stopping at the ends, the first
# Down the first row, the list scrolled to keep it in view; Enter clicks the highlighted row; the text changing resets
# it; the mouse over a row moves it)

def _finder_rows(f):
    """(name, highlighted) for each row shown."""
    return [(str(r.entry.name), bool(r.hl._shown)) for r in f.rows.values() if r._shown and r.entry]


def _finder_lit(f):
    return [n for n, on in _finder_rows(f) if on]


def _names(ns):
    return [str(e.name) for e in ns.Layers.NodeNames("").values()]


@pytest.fixture()
def finder(pad):  # noqa: F811
    lua, ns = pad
    Lay = ns.Layers
    st = ns.settings.gps
    st.nodeAvailable, st.nodeFilter = False, lua.eval("{}")
    lua.execute("AGPS_MOVING = false; AGPS_NS.GPS.PlayerMoving = function() return AGPS_MOVING end")
    assert ns.Pad.Apply()
    f = Lay.ShowNodeFinder()
    try:
        yield lua, ns, f
    finally:
        f.Hide(f)
        Lay.SetFinderKind(None)
        if Lay.AvailableOnly():
            Lay.SetAvailableOnly(False)
        Lay.SetNodeFilter(None, False)


def test_the_finders_arrow_keys_move_a_highlight_that_scrolls_and_enter_clicks_it(finder):
    lua, ns, f = finder
    Lay = ns.Layers
    names = _names(ns)
    rows_n = Lay.FINDER_ROWS
    assert len(names) > rows_n + 2
    box = f.box
    assert _finder_lit(f) == []
    arrow(box, "UP")
    assert _finder_lit(f) == []  # (none yet: Up does nothing)
    arrow(box, "DOWN")
    assert f.sel == 1 and _finder_lit(f) == [names[0]]
    arrow(box, "UP")
    assert f.sel == 1  # (stops at the top)
    for _ in range(rows_n):
        arrow(box, "DOWN")
    assert f.sel == rows_n + 1 and _finder_lit(f) == [names[rows_n]]
    shown = [n for n, _ in _finder_rows(f)]
    assert shown[-1] == names[rows_n] and shown[0] == names[1]  # (scrolled one row to keep it in view)
    for _ in range(rows_n + 5):
        arrow(box, "UP")
    assert f.sel == 1 and [n for n, _ in _finder_rows(f)][0] == names[0]  # (back to the top)
    for _ in range(len(names) + 3):
        arrow(box, "DOWN")
    assert f.sel == len(names) and _finder_lit(f) == [names[-1]]  # (stops at the end)
    # Enter: the highlighted one picked
    box._scripts.OnEnterPressed(box)
    assert list(Lay.NodeFilter().keys()) == [names[-1]]
    # the mouse over a row: the same highlight
    rs = [r for r in f.rows.values() if r._shown]
    rs[2]._scripts.OnEnter(rs[2])
    assert _finder_lit(f) == [str(rs[2].entry.name)]
    arrow(box, "DOWN")
    assert _finder_lit(f) == [str(rs[3].entry.name)]
    # the text changed: none, and Enter as before (the first, with text typed)
    box._text = "peace"
    box._scripts.OnTextChanged(box)
    assert f.sel is None and _finder_lit(f) == []
    box._scripts.OnEnterPressed(box)
    assert "Peacebloom" in list(Lay.NodeFilter().keys())


def test_the_dpad_walks_the_finders_list_and_a_picks_and_b_closes(finder):
    lua, ns, f = finder
    P, K, Lay = ns.Pad, ns.PadKeys, ns.Layers
    names = _names(ns)
    _tick(P)
    assert K.legend._shown and _same(lua, K.legend._parent, f)  # (the legend over the finder)
    assert _plain(K.legend.text._text) == ("D-pad up/D-pad down: Choose   D-pad left/D-pad right: Buttons   A: Pick   "
                                           "X: Keyboard   B: Close")
    _press(lua, "PADDDOWN")
    _tick(P)
    assert f.sel == 1
    _tick(P, 0.1)
    assert f.sel == 1
    _tick(P, 0.3)
    assert f.sel == 2  # (held: repeating)
    for _ in range(Lay.FINDER_ROWS + 2):
        _tick(P, 0.1)
    _press(lua, "PADDDOWN", False)
    _tick(P)
    assert f.sel == Lay.FINDER_ROWS + 4 and _finder_lit(f) == [names[f.sel - 1]]  # (scrolled with it)
    _tap(lua, P, "PAD1")  # (A: as a click on it)
    assert list(Lay.NodeFilter().keys()) == [names[Lay.FINDER_ROWS + 3]]
    assert f._shown
    _tap(lua, P, "PAD2")  # (B with the keyboard shut: closed, as Escape)
    assert not f._shown


def test_x_types_into_the_finders_box_with_the_same_keyboard(finder):
    lua, ns, f = finder
    P, K, Lay = ns.Pad, ns.PadKeys, ns.Layers
    _tick(P)
    _tap(lua, P, "PAD3")
    kbf = K.frame
    assert K.open and kbf._shown and _same(lua, kbf._parent, f)  # (under the finder now)
    assert _plain(K.legend.text._text) == "D-pad: Move   A: Type   X: Close Keyboard   B: Delete"
    for ch in "peace":
        r, i = _find_key(K, ch)
        K.at[1], K.at[2] = r, i
        _tap(lua, P, "PAD1")
    assert str(f.box._text) == "peace"
    assert [n for n, _ in _finder_rows(f)] == ["Peacebloom"]  # (the list followed)
    _tap(lua, P, "PAD2")
    assert str(f.box._text) == "peac" and f._shown  # (B: a letter off)
    # up from the top row: back into the list, on its last row shown
    K.at[1], K.at[2] = 1, 1
    _tap(lua, P, "PADDUP")
    assert not K.open and _finder_lit(f) == ["Peacebloom"]
    _tap(lua, P, "PAD1")
    assert list(Lay.NodeFilter().keys()) == ["Peacebloom"]
    _tap(lua, P, "PAD3")
    assert K.open
    f.Hide(f)  # (closed: the keyboard and legend with it)
    _tick(P)
    assert not K.open and not kbf._shown and not K.legend._shown


def _find_key(K, ch):
    rows = K.frame.rows
    for r in range(1, len(rows) + 1):
        row = rows[r]
        for i in range(1, len(row) + 1):
            if row[i].ch is not None and str(row[i].ch) == ch:
                return r, i
    raise AssertionError(ch)


def test_the_dpads_left_and_right_go_through_the_finders_buttons(finder):
    # (Kooki3z 2026-11-20, the herbs and ore buttons, Available and Show All circled: "Make D pad left and right on this
    # screen toggle through these 4 options, fading select button (A by default) to choose it")
    lua, ns, f = finder
    P, K, Lay = ns.Pad, ns.PadKeys, ns.Layers
    herb, ore, avail, show_all = f.kindButtons.herb, f.kindButtons.ore, f.available, f.showAll
    _tick(P)
    assert not show_all._enabled  # (nothing filtered: Show All grayed out, skipped)
    view0 = tuple(ns.GPS.PadView())[:2]
    seen = []
    for _ in range(4):
        _tap(lua, P, "PADDRIGHT")
        seen.append(K.btn)
    assert [_same(lua, a, b) for a, b in zip(seen, [herb, ore, avail, herb])] == [True] * 4  # (round, Show All skipped)
    _tap(lua, P, "PADDLEFT")
    assert _same(lua, K.btn, avail)
    assert tuple(ns.GPS.PadView())[:2] == view0  # (the map wasn't panned)
    # the focus: a gold wash and the Select button's icon pulsing on it
    m = K.mark
    assert m._shown and _same(lua, m._parent, avail) and _plain(m.icon.text._text) == "A"
    assert m.wash._tex.startswith("color:1.00,0.82")
    # A clicks it, as the mouse does: Available on, so Show All can be pressed now
    _tap(lua, P, "PAD1")
    assert Lay.AvailableOnly() and show_all._enabled
    _tap(lua, P, "PADDRIGHT")
    assert _same(lua, K.btn, show_all)
    _tap(lua, P, "PAD1")  # (Show All: Available off, itself grayed out; the focus on the one before it)
    assert not Lay.AvailableOnly() and not show_all._enabled and _same(lua, K.btn, avail)
    _tap(lua, P, "PADDLEFT")
    _tap(lua, P, "PADDLEFT")
    assert _same(lua, K.btn, herb)
    _tap(lua, P, "PAD1")
    assert Lay.finderKind == "herb"
    # up or down: back to the list (the first row, none before), the focus gone
    _tap(lua, P, "PADDDOWN")
    assert K.btn is None and not m._shown and f.sel == 1
    _tap(lua, P, "PADDDOWN")
    assert f.sel == 2
    _tap(lua, P, "PADDRIGHT")
    assert _same(lua, K.btn, herb) and f.sel is None  # (A is the button's: no row lit)
    _tap(lua, P, "PADDUP")
    assert K.btn is None and f.sel == 2  # (back on its row from before)
    # the keyboard open: left and right are its keys'
    _tap(lua, P, "PAD3")
    K.at[1], K.at[2] = 1, 1
    _tap(lua, P, "PADDRIGHT")
    assert K.open and K.btn is None and _at(K) == (1, 2)


# ---------------------------------------------------------------- Options' search box
# (Kooki3z 2026-11-20: "add the keyboard function to the search bar in Options to when controller is detected"): the
# same keyboard and legend on Options' search box, with Options' own fixed buttons (PadOptions.lua), the settings
# filtering as the letters are typed; without a controller nothing new.

from test_controller import _opts  # noqa: E402


def _opt_type(lua, K, word):
    """Each letter of `word` typed with A on its key (the lit key set straight on it: the D-pad has its own test)."""
    rows = K.frame.rows
    for ch in word:
        r, i = next((r, i) for r in range(1, len(rows) + 1) for i in range(1, len(rows[r]) + 1) if rows[r][i].ch == ch)
        K.at[1], K.at[2] = r, i
        _press(lua, "PAD1")


def test_options_search_opens_the_keyboard_and_typing_filters_the_settings(pad):  # noqa: F811
    lua, ns = pad
    O, P, PO = _opts(lua, ns)
    K = ns.PadKeys
    O.ShowPage("General")
    assert not K.open and not (K.legend and K.legend._shown)  # (the page list in focus: nothing of the keyboard's)
    PO.FocusSearch("list")
    K.Refresh()
    t, box = PO.keysTarget, O.search.box
    assert K.Wants() and _same(lua, K.Target(), t)
    lg = K.legend
    assert lg._shown and _same(lua, lg._pts["RIGHT"][2], box)  # (beside the box)
    assert _plain(lg.text._text) == "D-pad: Move   A: Keyboard   B: Close"
    _press(lua, "PAD1")  # (A: the keyboard, not a cursor waiting for a real one)
    f = K.frame
    assert K.open and f._shown and PO.KeysOpen() and PO.typing is None and _same(lua, f._parent, t)
    assert _same(lua, f._pts["TOPRIGHT"][2], box) and f._pts["TOPRIGHT"][3] == "BOTTOMRIGHT"  # (inside Options, under the box)
    assert _plain(lg.text._text) == "D-pad: Move   A: Type   X: Close Keyboard   B: Delete"
    # the D-pad on the keys (Options' own bindings, not the map's)
    K.at[1], K.at[2] = 1, 1
    K.Light()
    _press(lua, "PADDRIGHT")
    assert _at(K) == (1, 2)
    # typed: the box's text, the settings filtered as each letter goes in
    _opt_type(lua, K, "opac")
    assert str(box._text) == "opac" and O.search.on and O.search.results._shown
    rows = list(PO.Rows().values())
    assert rows  # (the opacity settings found)
    _press(lua, "PAD2")  # (B: a letter off)
    assert str(box._text) == "opa" and lua.eval("AzerothGPSOptions._shown")
    _opt_type(lua, K, "city")
    assert str(box._text) == "opacity" and O.search.results._shown
    # up off the keys' top row: the keyboard closed, the focus on the first result
    K.at[1], K.at[2] = 1, 1
    _press(lua, "PADDUP")
    assert not K.open and not f._shown and PO.side == "page"
    assert _is_in(lua, O.search.resultsChild, PO.focus)
    assert not lg._shown  # (off the box: no legend)
    # back on the box, X opens it, Done closes it
    PO.FocusSearch("page")
    _press(lua, "PAD3")
    assert K.open
    K.at[1], K.at[2] = len(K.frame.rows), 3
    assert str(K.Key().kind) == "done"
    _press(lua, "PAD1")
    assert not K.open and PO.side == "search" and str(box._text) == "opacity"
    # the player starting to move closes it, as on the map
    _press(lua, "PAD1")
    assert K.open
    lua.execute("AGPS_OPT_MOVING = true AGPS_NS.GPS.PlayerMoving = function() return AGPS_OPT_MOVING end")
    t._scripts.OnUpdate(t, 0.016)
    assert not K.open
    # Options closed: the keyboard and the legend with it
    lua.execute("AGPS_OPT_MOVING = false")
    t._scripts.OnUpdate(t, 0.016)
    _press(lua, "PAD1")
    assert K.open
    lua.execute("AzerothGPSOptions:Hide()")
    P.Apply()
    assert not K.open and not f._shown and not lg._shown
    O.Search("")


def _is_in(lua, top, f):
    return lua.eval("""function(top, f)
      local a = f
      while a do if a == top then return true end a = a:GetParent() end
      return false
    end""")(top, f)


def test_options_search_without_a_controller_has_no_keyboard(pad):  # noqa: F811
    lua, ns = pad
    K = ns.PadKeys
    # no pad connected: Options' buttons aren't bound, the box is the mouse's and the keyboard's as before
    lua.execute("AGPS_PAD.id = -1")
    O, P, PO = _opts(lua, ns)
    assert not PO.bound and "PAD3" not in {str(k) for k in lua.eval("AGPS_BINDS").keys()}
    assert _press(lua, "PAD1") is False
    box = O.search.box
    box.SetText(box, "opacity")
    if not O.search.on:
        O.Search("opacity")
    K.Refresh()
    assert O.search.results._shown and not K.open and not (K.legend and K.legend._shown)
    assert not K.Wants() and PO.keysTarget is None
    lua.execute("AzerothGPSOptions:Hide()")
    O.Search("")
    # a pad on but the mouse in use: no legend or keyboard on the box either
    lua.execute("AGPS_PAD.id = 1")
    O, P, PO = _opts(lua, ns)
    PO.FocusSearch("list")
    P.SawInput(False)
    K.Refresh()
    assert not K.Wants() and not K.open and not (K.legend and K.legend._shown)
