"""The FAQ window (item 48, Kooki3z 2026-11-24): Options > Help's FAQ button and `/agps faq` open it; every question and
answer is in every locale; it shows over the game's world map."""

import re
from pathlib import Path

from test_setup import _start
from test_whatsnew import UPDATING

ADDON = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS"
LOCALES = ["deDE", "esES", "esMX", "frFR", "itIT", "koKR", "ptBR", "ruRU", "zhCN", "zhTW"]


def test_the_help_page_button_and_the_command_open_it():
    lua, ns = _start(saved=UPDATING)
    F, O = ns.Faq, ns.Options
    O.Show()
    O.ShowPage("Help")
    lua.globals().AGPS_CLICK(O.faqButton)
    assert F.Shown()
    f = F.window
    assert len(f.lines) == len(F.ITEMS) == 14  # (item 74: "How do I turn the new routing off?" removed)
    assert f._strata == ns.POPUP_OVER_STRATA  # (over the game's world map too)
    assert f.child._h > 400  # (all of it in the scrolling area)
    lua.globals().AGPS_CLICK(f.close)
    assert not F.Shown()
    lua.globals().SlashCmdList.AZEROTHGPS("faq")
    assert F.Shown()
    f.Hide(f)
    assert not F.Shown()


def test_every_question_and_answer_is_in_every_locale():
    text = (ADDON / "Faq.lua").read_text(encoding="utf-8")
    keys = re.findall(r'L\["((?:[^"\\]|\\.)*)"\]', text)
    assert len(keys) >= 30
    for loc in LOCALES:
        have = (ADDON / "Locales" / f"{loc}.lua").read_text(encoding="utf-8")
        missing = [k for k in keys if f'L["{k}"] =' not in have]
        assert not missing, (loc, missing[:3])
