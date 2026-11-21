"""Alliance routes never take Zephras Isle's zeppelin to Camp Gev'rek, Mulgore (the Horde's).

A player's report, relayed by Kooki3z 2026-11-21: "I was guided through the Zephras Isles skyships to Mulgore to get to
Stonetalon peak as Alliance and had to death run from the dock"; Kooki3z: "make sure alliance isn't routed there". The
ride's row was open to both (addon_data.TRANSPORT_FACTIONS, "both" until known in game), and the camp's guards are WoW
Forever's own, not in the 1.12 NPC dump, so the guards by its docks couldn't tell either."""

import re
from pathlib import Path

import pytest

RIDE = "Camp Gev'rek, Mulgore | Fairweather Stables, Zephras Isle"
STONETALON_PEAK = (2681.1, 1461.7, 1)  # (its flight master)
FAIRWEATHER = (2521, 1950.0, 1216.7, 2991)  # (uiMap, x, y, continent: Fairweather Stables, Zephras Isle)
ALTERAC = (1416, 600.0, 400.0, 0)  # (by Old Dalaran Ruins' zeppelin)
GEVREK_DOCK = (-802.0, 366.5)
TRANSPORTS = Path(__file__).resolve().parents[2] / "addon" / "AzerothGPS" / "Data" / "Transports.lua"


@pytest.fixture(scope="module")
def game():
    pytest.importorskip("lupa.lua51")
    from azerothgps.gameharness import start
    lua, ns = start()
    ns.Nav.FUN = False
    return lua, ns


def test_the_rides_faction_is_the_hordes_in_the_data():
    from azerothgps.addon_data import TRANSPORT_FACTIONS

    assert TRANSPORT_FACTIONS[RIDE] == "H"
    row = next(line for line in TRANSPORTS.read_text(encoding="utf-8").splitlines()
               if '"Camp Gev\'rek, Mulgore", "Fairweather Stables, Zephras Isle"' in line)
    assert 'faction = "H"' in row, row
    # (Old Dalaran's stays open to both: Alterac Mountains is contested, no guards by either dock)
    assert TRANSPORT_FACTIONS["Old Dalaran Ruins, Alterac Mountains | Valanaar Skydocks, Zephras Isle"] == "both"


def test_camp_gevreks_guards_are_in_the_hostile_data(game):
    # (WoW Forever's own camp, hostile.FOREVER_GUARDS: its dock and the camp are dangerous to Alliance players, so
    # the guards by the docks would tell even without the row's faction, and Alliance walks keep off the camp)
    lua, ns = game
    R, N = ns.Router, ns.Nav
    assert R.HostileAt(1, GEVREK_DOCK[0], GEVREK_DOCK[1], "A")
    assert R.HostileAt(1, -650.0, 416.7, "A")
    assert not R.HostileAt(1, GEVREK_DOCK[0], GEVREK_DOCK[1], "H")
    cdb = ns.CharDB()
    old = cdb.faction
    try:
        cdb.faction = "Alliance"
        bare = lua.eval('{ 1, -802.0, 366.5, 2991, 1952.1, 1017.1, 194, "zeppelin", "a", "b" }')  # (no `faction`)
        assert not N.TransportUsable(bare)
    finally:
        cdb.faction = old


def _steps(lua, ns, faction, start):
    N, G = ns.Nav, ns.GPS
    cdb = ns.CharDB()
    cdb.faction = faction
    N.FlightsChanged()
    mp, x, y, cont = start
    lua.execute(f"AGPS_MAP = {mp}; AGPS_POS = {{ {x}, {y}, {cont} }}")
    sx, sy, sc = STONETALON_PEAK
    N.SetStops(lua.eval(f"{{ {{ x = {sx}, y = {sy}, cont = {sc} }} }}"), False, "red")
    for _ in range(30):
        lua.execute("AGPS_T = (AGPS_T or 1000) + 0.5")
        G.Update()
    return N.StepsText(99)


@pytest.mark.parametrize("start", [FAIRWEATHER, ALTERAC], ids=["zephras-isle", "alterac"])
def test_alliance_to_stonetalon_peak_never_takes_the_ride_to_camp_gevrek(game, start):
    lua, ns = game
    old = ns.CharDB().faction
    try:
        steps = _steps(lua, ns, "Alliance", start)
    finally:
        ns.CharDB().faction = old
    assert "Walk" in steps, steps  # (a plan)
    assert "Camp Gev'rek" not in steps, steps
    assert not re.search(r"Take the zeppelin to [^|]*Mulgore", steps), steps


def test_horde_still_takes_the_ride_to_camp_gevrek(game):
    lua, ns = game
    old = ns.CharDB().faction
    try:
        steps = _steps(lua, ns, "Horde", FAIRWEATHER)
    finally:
        ns.CharDB().faction = old
    assert "Take the zeppelin to Camp Gev'rek, Mulgore" in steps, steps
