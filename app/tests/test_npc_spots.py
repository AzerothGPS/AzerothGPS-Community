"""NPC spots marked in game (some shipped NPCs stand elsewhere in this game than the dump's spawn, and the search sent
players there): the marks into overrides/npc_spots.json, and the overrides into Data/Npcs.lua (npcspots.py,
`agps npc-spots --import FILE --write`; `agps npcs --write` applies them too)."""
import json
import types

from azerothgps import cli, npcspots
from azerothgps.npcs import lua_text
from azerothgps.paths import ADDON_DIR

NPCS = ADDON_DIR / "Data" / "Npcs.lua"
RENEE = 6741  # (an innkeeper id: the tests give it their own spawns)


def _npcs():
    return {
        RENEE: {"name": "Innkeeper Renee", "sub": "Innkeeper", "svc": "gvi", "trainer": "", "side": "H",
                "spawns": [(0, 2269.5, 244.9, 34.3)]},
        100: {"name": "Two Towns", "sub": "", "svc": "v", "trainer": "", "side": "B",
              "spawns": [(0, 100.0, 100.0, 5.0), (0, 5000.0, 5000.0, 50.0), (10001, 1500.0, 240.0, -40.0)]},
    }


def _mark(nid, x, y, t, level=0, cont=0, client="live", z=None, name="NPC"):
    m = {"id": nid, "name": name, "level": level, "cont": cont, "x": x, "y": y, "zone": "Tirisfal Glades",
         "time": t, "client": client}
    if z is not None:
        m["z"] = z
    return m


def test_the_shipped_file_reads_back_as_it_was_written():
    text = NPCS.read_text(encoding="utf-8")
    head, npcs = npcspots.parse_lua(text)
    assert len(npcs) > 2000 and npcs[RENEE]["name"].startswith("Innkeeper")
    assert lua_text(npcs) == text  # (patching with no spots changes nothing)
    assert npcspots.patch_lua(text, {"npcs": {}})[0] == text


def test_a_mark_moves_the_nearest_spawn_on_its_level_and_keeps_its_height(tmp_path):
    path = tmp_path / "npc_spots.json"
    new = npcspots.merge_marks([_mark(RENEE, 2254.04, 293.06, 1795000000, name="Innkeeper Renee"),
                                _mark(100, 4990.0, 5010.0, 1795000001, name="Two Towns")], path)
    assert [n for n, _ in new] == [RENEE, 100]
    doc = npcspots.load(path)
    assert doc["npcs"][str(RENEE)] == [{"name": "Innkeeper Renee", "level": 0, "x": 2254.0, "y": 293.1,
                                        "zone": "Tirisfal Glades", "time": 1795000000, "live": True}]
    npcs = _npcs()
    applied = npcspots.apply(npcs, doc)
    assert npcs[RENEE]["spawns"] == [(0, 2254.0, 293.1, 34.3)]  # (no height marked: the spawn's kept)
    assert applied[RENEE][0][1] == 50.6  # (yards moved)
    # an NPC with spawns in two towns: only the one it was marked by moves
    assert npcs[100]["spawns"] == [(0, 100.0, 100.0, 5.0), (0, 4990.0, 5010.0, 50.0), (10001, 1500.0, 240.0, -40.0)]
    # again: by their times, nothing new
    assert npcspots.merge_marks([_mark(RENEE, 1.0, 1.0, 1795000000)], path) == []


def test_live_marks_win_over_the_other_clients_and_then_the_newest(tmp_path):
    path = tmp_path / "npc_spots.json"
    npcspots.merge_marks([
        _mark(RENEE, 2260.0, 260.0, 1795000300, client="private"),  # (newest, but another server's)
        _mark(RENEE, 2255.0, 290.0, 1795000100),
        _mark(RENEE, 2256.0, 291.0, 1795000200),  # (the newest live one)
    ], path)
    npcs = _npcs()
    npcspots.apply(npcs, npcspots.load(path))
    assert npcs[RENEE]["spawns"] == [(0, 2256.0, 291.0, 34.3)]
    # only another client's: it's taken (the user marks there on purpose too), labeled in the overrides
    path2 = tmp_path / "other.json"
    npcspots.merge_marks([_mark(RENEE, 2260.0, 260.0, 1795000300, client="private")], path2)
    assert npcspots.load(path2)["npcs"][str(RENEE)][0]["live"] is False
    npcs = _npcs()
    npcspots.apply(npcs, npcspots.load(path2))
    assert npcs[RENEE]["spawns"] == [(0, 2260.0, 260.0, 34.3)]


def test_undercity_a_height_another_level_and_npcs_not_shipped(tmp_path):
    path = tmp_path / "npc_spots.json"
    npcspots.merge_marks([
        _mark(100, 1510.0, 250.0, 1, level=10001, cont=0, z=-42.25),  # (down in Undercity, its floor followed)
        _mark(100, -900.0, -3000.0, 2, level=1, cont=1),  # (Kalimdor: no spawn there yet, added)
        _mark(999999, 1.0, 1.0, 3),  # (not shipped)
        _mark(100, 1.0, 1.0, 4, level=2991, cont=2991),  # (Zephras Isle: its NPCs shipped since 1.3.14, taken in)
        _mark(100, 1.0, 1.0, 6, level=5000, cont=5000),  # (a level no NPC is shipped on: never taken in)
        {"id": "x", "x": 1, "y": 1, "time": 5},  # (not a mark)
    ], path)
    doc = npcspots.load(path)
    assert sorted(s["time"] for v in doc["npcs"].values() for s in v) == [1, 2, 3, 4]
    npcs = _npcs()
    said = []
    applied = npcspots.apply(npcs, doc, log=said.append)
    assert npcs[100]["spawns"][2] == (10001, 1510.0, 250.0, -42.2)
    assert npcs[100]["spawns"][3] == (1, -900.0, -3000.0, 0.0) and (doc["npcs"]["100"][1], None) in applied[100]
    assert (2991, 1.0, 1.0, 0.0) in npcs[100]["spawns"]
    assert 999999 not in npcs and "999999" in said[0]


def test_the_command_takes_marks_in_and_patches_only_the_npcs_marked(tmp_path, capsys):
    lua = tmp_path / "Npcs.lua"
    lua.write_text(lua_text(_npcs()), encoding="utf-8", newline="\n")
    before = lua.read_text(encoding="utf-8")
    marks = tmp_path / "marks.json"
    marks.write_text(json.dumps([_mark(RENEE, 2254.0, 293.0, 1795000000, name="Innkeeper Renee")]), encoding="utf-8")
    over = tmp_path / "npc_spots.json"
    args = types.SimpleNamespace(import_file=str(marks), write=False, overrides=str(over), npcs_lua=str(lua))
    assert cli.cmd_npc_spots(args) == 0
    assert not over.exists() and lua.read_text(encoding="utf-8") == before  # (without --write: said only)
    assert "moved 50.5 yd" in capsys.readouterr().out
    args.write = True
    assert cli.cmd_npc_spots(args) == 0
    after = lua.read_text(encoding="utf-8")
    assert "6741|Innkeeper Renee|Innkeeper|gvi||H|0 2254.0 293.0 34.3\n" in after
    assert [l for l in after.splitlines() if not l.startswith("6741|")] == \
        [l for l in before.splitlines() if not l.startswith("6741|")]
    # again with the overrides alone: the same file (the spot moved onto itself)
    args.import_file = None
    assert cli.cmd_npc_spots(args) == 0
    assert lua.read_text(encoding="utf-8") == after


def test_the_overrides_file_keeps_to_its_shape():
    doc = npcspots.load()
    for key, spots in doc["npcs"].items():
        assert int(key) > 0
        for s in spots:
            assert set(s) <= {"name", "level", "x", "y", "z", "zone", "time", "live"}
            assert s["level"] in npcspots.LEVELS and isinstance(s["time"], int)
