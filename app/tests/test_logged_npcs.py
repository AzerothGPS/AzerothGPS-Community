"""NPCs not shipped yet, logged in game by a plugin's NPC logger (marks with `source` "logger"): `agps npc-spots
--import` keeps them in overrides/logged_npcs.json, and both it and the generator (`agps npcs`, npcs.build) add them to
Data/Npcs.lua (npcspots.py). Asked 2026-11-23: Riverglades has no NPCs in any data source."""
import json
import types

from azerothgps import cli, npcs, npcspots
from azerothgps.npcs import lua_text

RENEE = 6741


def _shipped():
    return {RENEE: {"name": "Innkeeper Renee", "sub": "Innkeeper", "svc": "gvi", "trainer": "", "side": "H",
                    "spawns": [(0, 2269.5, 244.9, 34.3)]}}


def _mark(nid, x, y, t, name="Grukk Stonetusk", **kw):
    m = {"id": nid, "name": name, "level": 0, "cont": 0, "x": x, "y": y, "zone": "Riverglades", "time": t,
         "source": "logger", "svc": "merchant", "faction": "Horde", "title": "Trade Goods", "npcLevel": 30}
    m.update(kw)
    return m


def _run(tmp_path, marks, write):
    lua = tmp_path / "Npcs.lua"
    if not lua.exists():
        lua.write_text(lua_text(_shipped()), encoding="utf-8", newline="\n")
    mf = tmp_path / "marks.json"
    mf.write_text(json.dumps(marks), encoding="utf-8")
    args = types.SimpleNamespace(import_file=str(mf), write=write, overrides=str(tmp_path / "npc_spots.json"),
                                 logged=str(tmp_path / "logged_npcs.json"), npcs_lua=str(lua))
    assert cli.cmd_npc_spots(args) == 0
    return lua, args


def test_logger_marks_of_unshipped_npcs_become_shipped_npcs(tmp_path, capsys):
    marks = [
        _mark(990001, -7950.0, -4750.0, 1795000000, z=12.34),
        _mark(990001, -7955.0, -4752.0, 1795000005, svc="gossip,quest"),  # (the same NPC, 5 yd off: one spawn)
        _mark(990001, -8550.0, -4783.0, 1795000010),  # (far: a second spawn)
        _mark(990002, -9183.0, -4983.0, 1795000020, name="Flight Master Ana", title="Flight Master",
              svc="flight,gossip", faction="Alliance"),
        _mark(990003, -9000.0, -4000.0, 1795000030, name="Sam", title=None, svc=None, faction=None),
        _mark(RENEE, 2254.0, 293.0, 1795000040, name="Innkeeper Renee", svc="gossip"),  # (shipped: moves its spawn)
    ]
    lua, args = _run(tmp_path, marks, write=False)
    out = capsys.readouterr().out
    assert "5 new spot(s) of NPCs not shipped yet, from 5 logger mark(s)" in out and "moved 50.5 yd" in out
    assert not (tmp_path / "logged_npcs.json").exists()  # (without --write: said only)
    lua, args = _run(tmp_path, marks, write=True)
    text = lua.read_text(encoding="utf-8")
    assert "990001|Grukk Stonetusk|Trade Goods|gqv||H|0 -8550.0 -4783.0 0.0;0 -7955.0 -4752.0 12.3\n" in text  # (height kept)
    assert "990002|Flight Master Ana|Flight Master|gf||A|0 -9183.0 -4983.0 0.0\n" in text
    assert "990003|Sam||||B|0 -9000.0 -4000.0 0.0\n" in text
    assert "6741|Innkeeper Renee|Innkeeper|gvi||H|0 2254.0 293.0 34.3\n" in text
    doc = json.loads((tmp_path / "logged_npcs.json").read_text(encoding="utf-8"))
    g = doc["npcs"]["990001"]
    assert g["source"] == "logger" and len(g["spawns"]) == 3 and g["spawns"][0]["z"] == 12.3
    assert g["spawns"][0]["npcLevel"] == 30
    assert "6741" not in doc["npcs"]
    # again: nothing new, the same file
    _run(tmp_path, marks, write=True)
    assert lua.read_text(encoding="utf-8") == text
    # a later mark of a logged NPC (shipped now, by the logger) still goes to the logged file
    _run(tmp_path, [_mark(990003, -9100.0, -4100.0, 1795000050, name="Sam", svc="trainer", title="Mage Trainer")],
         write=True)
    text2 = lua.read_text(encoding="utf-8")
    assert "990003|Sam|Mage Trainer|t|MAGE|H|0 -9100.0 -4100.0 0.0;0 -9000.0 -4000.0 0.0\n" in text2


def test_hand_marks_of_unshipped_npcs_stay_spot_fixes(tmp_path):
    _run(tmp_path, [_mark(990009, 1.0, 1.0, 1795000000, source=None)], write=True)
    assert not (tmp_path / "logged_npcs.json").exists()
    assert "990009" in json.loads((tmp_path / "npc_spots.json").read_text(encoding="utf-8"))["npcs"]


def test_the_generator_adds_logged_npcs_the_dump_lacks():
    doc = {"npcs": {"990001": {"name": "Grukk", "sub": "", "svc": "v", "side": "H", "source": "logger",
                               "spawns": [{"level": 0, "x": 1.0, "y": 2.0, "zone": "Riverglades", "time": 5,
                                           "live": True}]},
                    str(RENEE): {"name": "Renee?", "sub": "", "svc": "g", "side": "B", "source": "logger",
                                 "spawns": [{"level": 0, "x": 9.0, "y": 9.0, "zone": "", "time": 6, "live": True}]}}}
    got, report = _shipped(), {"logged": 0}
    from collections import defaultdict
    report = defaultdict(int)
    npcs._add_logged(got, report, doc)
    assert got[990001]["spawns"] == [(0, 1.0, 2.0, 0.0)] and got[990001]["side"] == "H"
    assert got[RENEE]["name"] == "Innkeeper Renee"  # (the dump's wins)
    assert report["logged"] == 1


def test_the_logged_file_keeps_to_its_shape():
    doc = npcspots.load_logged()
    for key, n in doc["npcs"].items():
        assert int(key) > 0 and n["source"] == "logger" and n["name"] and n["side"] in ("A", "H", "B")
        assert set(n["svc"]) <= set(npcspots.SVC_ORDER)
        for s in n["spawns"]:
            assert s["level"] in npcspots.LEVELS and isinstance(s["time"], int)
