"""Road tolerance's slider, renamed (item 61, Kooki3z read +10 as "most road"): "Roads or shortcuts", "Stick to roads"
under its left end and "Cut across" under its right; the saved key and its values as they were; the old name still
found by the Options search."""

import pytest


def test_the_slider_s_name_its_ends_and_the_old_name_in_the_search():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start(locale="enUS")
    O, st = ns.Options, ns.settings.gps
    O.Show()
    was = st.roadTolerance
    s = O.roadSlider
    assert str(s.title._text) == "Roads or shortcuts"
    assert str(s.leftEnd._text) == "Stick to roads" and str(s.rightEnd._text) == "Cut across"
    assert s.leftEnd._pts.TOPLEFT[3] == "BOTTOMLEFT" and s.rightEnd._pts.TOPRIGHT[3] == "BOTTOMRIGHT"
    assert st.roadTolerance == was  # (the value as it was: the key and its meaning unchanged)
    by_key = {}
    for i in range(1, len(O.settingControls) + 1):
        c = O.settingControls[i]
        if not c.mirror:
            by_key[c.key] = c
    try:
        assert O.Search("road tolerance") is True
        assert by_key["roadTolerance"].control._shown is not False
        assert O.Search("shortcuts") is True
        assert by_key["roadTolerance"].control._shown is not False
    finally:
        O.Search("")
