"""The Gurubashi Arena carries one label, its own: no separate "Battle Ring" (AreaTable 2177)."""
from pathlib import Path

from azerothgps.addon_data import SKIP_PLACE_LABELS

POIS = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS" / "Data" / "Pois.lua"


def test_arena_labeled_gurubashi_arena_only():
    text = POIS.read_text(encoding="utf-8")
    assert 2177 in SKIP_PLACE_LABELS  # the generator leaves the Battle Ring out
    assert "Battle Ring" not in text and ",2177}" not in text
    assert text.count('"Gurubashi Arena",33,1741}') == 1
