"""Where the player may be inside a dungeon, from range checks to the mobs round them (item 105, 1.4.1; DungeonFix.lua),
and the dungeons' spawns it matches them against (`agps dungeon-spawns`, dungeonspawns.py).

The dungeon here is a stand-in: two corridors one over the other (the lower at height 0, the upper at 20, the same
ground across), a room off the lower one's west end, guards (several spawns of one kind), a sentry upstairs, rats and a
patrol. The range
checks are worked out from the true 3D distances, as the client does."""

import math

import pytest

from test_map_redraw import game  # noqa: F401

LEVEL = 29990  # (no real instance's)
SPELLS = (10, 20, 30, 41)
INTERACT = {2: (11.11, 7), 3: (9.9, 7), 4: (28, 28)}
GUARD, RAT, PATROL, SENTRY = 1001, 1002, 1003, 1004
SPAWNS = [  # id, x, y, z, move, wander
    (GUARD, 20, 0, 0, 0, 0), (GUARD, 80, 0, 0, 0, 0), (GUARD, 0, 60, 0, 0, 0), (SENTRY, 50, 0, 20, 0, 0),
    (RAT, 90, 0, 20, 0, 0), (RAT, -100, 0, 0, 1, 5),
    (PATROL, 50, 0, 0, 2, 0),
]
MOBS = {GUARD: ("Guard", 18, 19, 1, 1, "B"), RAT: ("Rat", 15, 15, 0, 1, "B"), PATROL: ("Patrol", 18, 18, 0, 1, "B"),
        SENTRY: ("Sentry", 20, 20, 1, 1, "B")}

_ROADS = """
ns.Roads[%d] = {
  n = { 0, 0, 100, 0, 0, 1, 100, 1, 0, 60 },
  z = { 0, 0, 20, 20, 0 },
  e = { { 1, 2, 100, 0 }, { 3, 4, 100, 0 }, { 1, 5, 60, 0, "W0Wy" } },
}
"""


def _spawns_text():
    return "\n".join(f"{i} {x:.1f} {y:.1f} {z:.1f} {m} {w}" for i, x, y, z, m, w in SPAWNS)


@pytest.fixture
def dungeon(game):  # noqa: F811
    lua, ns = game
    roads = lua.eval("function(ns, s) return assert(loadstring('local ns = ...; ' .. s))(ns) end")
    roads(ns, _ROADS % LEVEL)
    DF = ns.DungeonFix
    DF.ResetSpots()
    spawns = DF.ParseSpawns(_spawns_text())
    mobs = lua.table_from({k: lua.table_from(list(v)) for k, v in MOBS.items()})
    yield lua, ns, DF, spawns, mobs
    ns.Roads[LEVEL] = None
    DF.ResetSpots()


def _checks(lua, player, mob):
    """The client's answers for a mob at `mob` (x, y, z) to a player at `player`: { r, inside } each."""
    d = math.dist(player, mob)
    out = [lua.table(r=r, inside=d <= r) for r in SPELLS]
    for _, (inside_yd, out_yd) in INTERACT.items():
        out.append(lua.table(r=inside_yd if d <= inside_yd else out_yd, inside=d <= inside_yd))
    return lua.table_from(out)


def _sights(lua, DF, spawns, mobs, player, seen, ids=True):
    """Sightings of the mobs at `seen` ((id, x, y, z, level, class) each): by creature id, or (ids False: the game made
    them secret) by level, classification and enemy."""
    out = []
    for npc, x, y, z, level, cls in seen:
        sight = lua.table(npc=npc) if ids else lua.table(level=level, **{"class": cls}, enemy=True)
        sight.checks = _checks(lua, player, (x, y, z))
        sight.cands = DF.Candidates(sight, spawns, mobs)
        out.append(sight)
    return lua.table_from(out)


def _estimate(DF, sights, prior=None, now=0):
    lst, grid = DF.Spots(LEVEL, None)
    return DF.Estimate(sights, lst, grid, prior, now)


# --- the data ---------------------------------------------------------------------------------------------------------

def test_spawns_parse_and_candidates_by_id_or_fingerprint(dungeon):
    lua, ns, DF, spawns, mobs = dungeon
    assert len(spawns) == len(SPAWNS)
    s = spawns[6]
    assert (s.id, s.x, s.y, s.z, s.move, s.wander) == (RAT, -100, 0, 0, 1, 5)
    assert DF.Wander(spawns[1]) == DF.WANDER and DF.Wander(s) == DF.WANDER + 5 and DF.Wander(spawns[7]) == DF.PATROL
    by_id = DF.Candidates(lua.table(npc=GUARD), spawns, mobs)
    assert len(by_id) == 3
    # (secret ids: a level-18 elite enemy is a guard, not the level-18 normal patrol nor a rat)
    elite = DF.Candidates(lua.table(level=18, **{"class": "elite"}, enemy=True), spawns, mobs)
    assert sorted({c.id for c in elite.values()}) == [GUARD]
    normal = DF.Candidates(lua.table(level=18, **{"class": "normal"}), spawns, mobs)
    assert sorted({c.id for c in normal.values()}) == [PATROL]
    assert len(DF.Candidates(lua.table(level=15), spawns, mobs)) == 2  # (rats)
    assert len(DF.Candidates(lua.table(level=-1, **{"class": "elite"}), spawns, mobs)) == 4  # (a "??" level: any elite)
    assert len(DF.Candidates(lua.table(level=15, enemy=False), spawns, mobs)) == 0  # (a rat is an enemy)


def test_the_spots_are_the_roads_every_few_yards_with_their_heights(dungeon):
    lua, ns, DF, spawns, mobs = dungeon
    lst, _ = DF.Spots(LEVEL, None)
    pts = [(p.x, p.y, p.z) for p in lst.values()]
    lower = [p for p in pts if p[1] == 0 and p[2] == 0]
    upper = [p for p in pts if p[2] == 20]
    assert len(lower) >= 100 // DF.POINT_STEP and len(upper) >= 100 // DF.POINT_STEP
    assert all(0 <= p[0] <= 100 for p in lower + upper)
    # (the packed road west: (0, 0) up to (0, 60), its height 0 all the way)
    west = [p for p in pts if p[0] == 0 and 1 < p[1] < 60]
    assert west and all(p[2] == 0 for p in west)
    gaps = sorted(p[0] for p in lower)
    assert max(b - a for a, b in zip(gaps, gaps[1:])) <= DF.POINT_STEP + 1e-6


# --- the estimate -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("ids", [True, False], ids=["ids", "secret ids"])
def test_two_mobs_put_the_player_by_the_right_guard(dungeon, ids):
    """By the east guard on the lower floor, a rat up on the upper floor in sight, the west guard far off: of the three
    guards alike, the east one is the one that fits, and the spot is within the radius of the truth."""
    lua, ns, DF, spawns, mobs = dungeon
    player = (75, 0, 0)
    seen = [(GUARD, 80, 0, 0, 18, "elite"), (RAT, 90, 0, 20, 15, "normal"), (GUARD, 20, 0, 0, 19, "elite")]
    est = _estimate(DF, _sights(lua, DF, spawns, mobs, player, seen, ids))
    assert est is not None
    err = math.dist(player, (est.x, est.y, est.z))
    assert err <= est.r, (est.x, est.y, est.z, est.r)
    assert est.r < 20 and est.score == 3 and est.of == 3
    pick = est.picks[1]
    assert (pick.x, pick.y, pick.z) == (80, 0, 0)  # (the east guard, not the west one or the one upstairs)
    assert abs(est.z - 0) < 3


def test_the_floor_over_is_told_from_the_one_under(dungeon):
    """Up on the upper corridor by the sentry: in reach of him, the lower west guard out of 30 but in 41: the height
    comes out 20, not 0 (the same ground across)."""
    lua, ns, DF, spawns, mobs = dungeon
    player = (50, 0, 20)
    seen = [(SENTRY, 50, 0, 20, 20, "elite"), (GUARD, 20, 0, 0, 18, "elite")]
    est = _estimate(DF, _sights(lua, DF, spawns, mobs, player, seen, ids=False))
    assert est is not None and abs(est.z - 20) < 3, (est and est.z)
    assert math.dist(player, (est.x, est.y, est.z)) <= est.r


def test_no_check_in_range_says_nothing(dungeon):
    lua, ns, DF, spawns, mobs = dungeon
    seen = [(GUARD, 20, 0, 0, 18, "elite")]
    est, why = _estimate(DF, _sights(lua, DF, spawns, mobs, (100, 0, 0), seen))
    assert est is None and why == "no checks in range"
    est, why = _estimate(DF, lua.table())
    assert est is None and why == "no checks in range"
    lst, grid = DF.Spots(LEVEL + 1, None)  # (no roads, no spawns: no spots)
    assert DF.Estimate(_sights(lua, DF, spawns, mobs, (80, 0, 0), seen), lst, grid)[1] == "no spots"


def test_the_prior_keeps_to_where_the_player_can_have_got(dungeon):
    """Only a guard in reach (ids secret: any of the three): alone it can't tell which; with the last estimate a
    second ago by the west room, the room's guard it is."""
    lua, ns, DF, spawns, mobs = dungeon
    player = (0, 56, 0)
    seen = [(GUARD, 0, 60, 0, 18, "elite")]
    sights = _sights(lua, DF, spawns, mobs, player, seen, ids=False)
    est, why = _estimate(DF, sights)[0], _estimate(DF, sights)[1]
    assert est is None and why == "ambiguous"
    prior = lua.table(x=0, y=40, z=0, r=8, at=10)
    est = _estimate(DF, sights, prior, 11)
    assert est is not None and math.dist(player, (est.x, est.y, est.z)) <= est.r
    # (a prior with no spot near: left out, never no answer for it)
    far = lua.table(x=500, y=500, z=0, r=5, at=10)
    assert _estimate(DF, _sights(lua, DF, spawns, mobs, (75, 0, 0), [(GUARD, 80, 0, 0, 18, "elite")]), far, 11)
    # (a prior gone astray, by the west guard after a teleport east: fewer fit there than by the east guard, it's left
    # out)
    player = (75, 0, 0)
    seen = [(GUARD, 80, 0, 0, 18, "elite"), (RAT, 90, 0, 20, 15, "normal"), (GUARD, 20, 0, 0, 19, "elite")]
    wrong = lua.table(x=20, y=0, z=0, r=8, at=10)
    est = _estimate(DF, _sights(lua, DF, spawns, mobs, player, seen, ids=False), wrong, 10)
    assert est is not None and math.dist(player, (est.x, est.y, est.z)) <= est.r and est.score == 3


def test_the_way_in_is_the_first_prior(game):  # noqa: F811
    lua, ns = game
    w = ns.DungeonFix.WayIn(20036)  # (the Deadmines: its entrance's inside end)
    assert w is not None and (round(w.x, 1), round(w.y, 1)) == (-14.6, -385.5) and w.r > 0
    assert ns.DungeonFix.WayIn(LEVEL) is None


# --- the generator ----------------------------------------------------------------------------------------------------

def test_the_generator_keeps_every_spawn_on_the_instance_maps():
    from azerothgps.dungeonspawns import build_rows, instance_maps, lua_text

    maps = instance_maps()
    assert maps[36] == "Deadmines" and maps[389] == "Ragefire Chasm" and maps[43] == "Wailing Caverns"
    ft = {1: {"id": 1}, 2: {"id": 2}, 14: {"id": 14}, 35: {"id": 35}}
    import azerothgps.dungeonspawns as dsp
    sides = {14: "B", 35: None}
    real = dsp.mob_side
    dsp.mob_side = lambda f, a, h: sides.get(f["id"])
    try:
        tpl = {
            "598": {"Name": "Defias Miner", "MinLevel": "17", "MaxLevel": "18", "Faction": "14", "CreatureType": "7",
                    "UnitFlags": "0", "ExtraFlags": "0", "Rank": "0", "UnitClass": "1"},
            "1": {"Name": "Rat", "MinLevel": "1", "MaxLevel": "1", "Faction": "14", "CreatureType": "8",
                  "UnitFlags": "0", "ExtraFlags": "0", "Rank": "0", "UnitClass": "1"},
            "9": {"Name": "Helper", "MinLevel": "20", "MaxLevel": "20", "Faction": "35", "CreatureType": "7",
                  "UnitFlags": "0", "ExtraFlags": "0", "Rank": "1", "UnitClass": "8"},
        }

        def row(cid, m, x, mv="0", dist="0"):
            return {"id": cid, "map": str(m), "position_x": str(x), "position_y": "-400.25", "position_z": "55.68",
                    "MovementType": mv, "spawndist": dist}

        rows = [row("598", 36, -50.26), row("598", 36, -73.1, "1", "5"), row("1", 36, 0),  # (a critter: left out)
                row("9", 36, 10, "2"), row("598", 0, 1)]  # (a neutral helper kept; the open world's left out)
        levels, rep = build_rows(tpl, rows, ft, {36})
    finally:
        dsp.mob_side = real
    lv = levels[20036]
    assert rep == {"kept": 3, "critter": 1}
    assert lv["mobs"][598] == ("Defias Miner", 17, 18, 0, 1, "B") and lv["mobs"][9][5] == "N"
    text = lua_text(levels, {36: "Deadmines"})
    assert "-- Deadmines (map 36)" in text and "ns.DungeonSpawns[20036]" in text
    assert "9 10.0 -400.2 55.7 2 0\n598 -73.1 -400.2 55.7 1 5\n598 -50.3 -400.2 55.7 0 0" in text
    assert '[598] = { "Defias Miner", 17, 18, 0, 1, "B" }' in text
