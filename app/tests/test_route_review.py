"""The city route review (routereview.py): the candidates out to the addon that loads RouteReview.lua as plain data,
the decisions made in game back from its SavedVariables (read only)."""
import json

import pytest

from azerothgps import routereview as RR


def _rows():
    return [
        {"id": "orgrimmar-1", "city": "Orgrimmar", "level": 1, "trip": 7,
         "start": {"x": 1600.0, "y": -4400.0, "z": 10.0, "name": 'Gate "west"'},
         "stop": {"x": 1700.0, "y": -4300.0, "z": 20.0, "name": "Bank\nupstairs"},
         "agps": {"yd": 300, "pts": [[1600, -4400, 10], [1650.04, -4350, 12], [1700, -4300, 20]]},
         "spf": {"yd": 150, "pts": [[1600, -4400, 10], [1700, -4300, 20]]},
         "why": "the lines part at (1650, -4350) \\ end"},
        {"id": "undercity-1", "city": "Undercity", "level": 10001,
         "start": {"x": 1630.4, "y": 275.1, "z": -43.0, "name": "Walter"},
         "stop": {"x": 1600.0, "y": 240.0, "z": -50.0, "name": "Bank"},
         "agps": {"yd": 90, "pts": [[1630.4, 275.1, -42.7], [1600, 240, -50]]},
         "spf": {"yd": 60, "pts": [[1630.4, 275.1, -42.7], [1600, 240, -50]]},
         "why": "x"},
    ]


def _addons(tmp_path):
    addons = tmp_path / "Interface" / "AddOns"
    other = addons / "Something"
    other.mkdir(parents=True)
    (other / "Something.toc").write_text("## Interface: 16001\nSomething.lua\n", encoding="utf-8")
    rv = addons / "Review"
    rv.mkdir()
    (rv / "Review.toc").write_text("## Interface: 16001\n## SavedVariables: ReviewDB\nRouteReview.lua\nReview.lua\n",
                                   encoding="utf-8")
    return addons, rv, other


def test_the_candidates_go_out_as_plain_data_to_the_addon_that_loads_them(tmp_path):
    addons, rv, other = _addons(tmp_path)
    rows = _rows()
    assert RR.export_review([addons], rows, log=lambda *_: None) == 1
    assert not (other / RR.REVIEW_FILE).exists()
    text = (rv / RR.REVIEW_FILE).read_text(encoding="utf-8")
    lupa = pytest.importorskip("lupa")
    lua = lupa.LuaRuntime()
    ns = lua.table()
    lua.eval("function(src, ns) assert(load(src))('Review', ns) end")(text, ns)
    a, u = ns.RouteReview[1], ns.RouteReview[2]
    assert a.id == "orgrimmar-1" and a.level == 1 and a.map == 1 and a.sig == RR.sig_of(rows[0])
    assert a.start.name == 'Gate "west"' and a.stop.name == "Bank upstairs"  # (quoted; a newline is a space)
    assert a.why == "the lines part at (1650, -4350) \\ end"
    assert [a.agps.pts[i] for i in range(1, 7)] == [1600, -4400, 1650, -4350, 1700, -4300]  # (x, y, flat, 0.1 yd)
    assert a.agps.yd == 300 and a.spf.yd == 150 and len(a.spf.pts) == 4
    assert u.level == 10001 and u.map == 0 and u.start.z == -43  # (Undercity: .go on its base continent, game z)


def test_a_bad_number_is_refused_never_written():
    rows = _rows()
    rows[0]["start"]["x"] = "1); os.exit()"
    with pytest.raises(ValueError):
        RR.review_lua(rows, {10001: 0})


def test_no_list_keeps_the_addons_file(tmp_path, monkeypatch):
    addons, rv, _ = _addons(tmp_path)
    (rv / RR.REVIEW_FILE).write_text("kept", encoding="utf-8")
    monkeypatch.setattr(RR, "REVIEW", tmp_path / "missing.json")
    assert RR.export_review([addons], log=lambda *_: None) == 0
    assert (rv / RR.REVIEW_FILE).read_text(encoding="utf-8") == "kept"


def test_the_decisions_come_back_from_the_saved_variables(tmp_path):
    addons, _rv, _ = _addons(tmp_path)
    rows = _rows()
    s0, s1 = RR.sig_of(rows[0]), RR.sig_of(rows[1])
    sv = tmp_path / "WTF" / "Account" / "ACC" / "SavedVariables"
    sv.mkdir(parents=True)
    before = (f'ReviewDB = {{ ["routeReview"] = {{ ["on"] = true, ["decisions"] = {{\n'
              f'  ["orgrimmar-1"] = {{ ["decision"] = "correct", ["sig"] = "{s0}", ["at"] = 50, '
              f'["tracks"] = {{ 1700000001, 1700000002, }}, ["yd"] = 171.6, ["level"] = 1 }},\n'
              f'  ["undercity-1"] = {{ ["decision"] = "approve", ["sig"] = "{s1}", ["at"] = 40 }},\n'
              f'  ["old-1"] = {{ ["decision"] = "reject", ["sig"] = "zzz", ["at"] = 30 }},\n'
              f'}} }} }}\n')
    (sv / "Review.lua").write_text(before, encoding="utf-8")
    got, stale = RR.read_decisions([addons], rows)
    assert got == {"orgrimmar-1": {"decision": "correct", "tracks": [1700000001, 1700000002], "yd": 172, "level": 1},
                   "undercity-1": "approve"}
    assert stale == 1  # (made on a candidate not in this list)
    assert (sv / "Review.lua").read_text(encoding="utf-8") == before  # (read only)
    # a second account's newer decision on the same candidate wins
    sv2 = tmp_path / "WTF" / "Account" / "ACC2" / "SavedVariables"
    sv2.mkdir(parents=True)
    (sv2 / "Review.lua").write_text(
        f'ReviewDB = {{ ["routeReview"] = {{ ["decisions"] = {{ ["undercity-1"] = {{ ["decision"] = "reject", '
        f'["sig"] = "{s1}", ["at"] = 45 }} }} }} }}\n', encoding="utf-8")
    got, _ = RR.read_decisions([addons], rows)
    assert got["undercity-1"] == "reject"
    out = tmp_path / "decisions.json"
    RR.write_decisions(got, out)
    assert json.loads(out.read_text(encoding="utf-8"))["orgrimmar-1"]["tracks"] == [1700000001, 1700000002]


def test_city_levels_map_to_their_base_continent():
    bases = RR.base_maps()
    assert bases.get(10001) == 0
    assert RR.map_of(10001, bases) == 0 and RR.map_of(1, bases) == 1 and RR.map_of(20389, bases) == 389
