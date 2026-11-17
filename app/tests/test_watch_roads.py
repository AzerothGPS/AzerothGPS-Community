"""agps watch-roads: drawn roads imported on every /reload, and the addon installed again; with --no-install, imported
only (2026-10-06: the 1.1.5 build installed for its test pass, which each import would have replaced with main's)."""

import argparse

from azerothgps import cli


def test_the_road_watcher_can_leave_the_installed_addon_alone(tmp_path, monkeypatch):
    import azerothgps.roads.build as build
    import azerothgps.roads.export as export
    import azerothgps.roads.recorded as recorded
    import azerothgps.roads.tracks as tracks

    saved = tmp_path / "ACCOUNT" / "SavedVariables"
    saved.mkdir(parents=True)
    (saved / "AzerothGPS.lua").write_text("AzerothGPSDB = {}\n", encoding="utf-8")
    monkeypatch.setattr(cli, "wtf_account_dir", lambda *a: tmp_path)
    monkeypatch.setattr(recorded, "Walks", lambda *a, **k: None)

    def one_road(wtf, overrides, per, walks=None):  # (a new drawn road on the Eastern Kingdoms)
        per[0] = 1
        return 1
    monkeypatch.setattr(tracks, "import_tracks", one_road)
    imported = []
    monkeypatch.setattr(build, "reapply_overrides", lambda data, conts: imported.append(list(conts)))
    monkeypatch.setattr(export, "write_roads_lua", lambda *a, **k: None)
    monkeypatch.setattr(cli, "_override_keys", lambda *a: set())
    monkeypatch.setattr(cli, "_import_saved_entrances", lambda *a: 0)
    monkeypatch.setattr(cli, "_touches_capital", lambda *a: False)
    installs = []
    monkeypatch.setattr(cli, "cmd_install_addon", lambda args: installs.append(True) or 0)
    args = argparse.Namespace(wow_path="wow", flavor="flavor", product="product", once=True, interval=0.0,
                              no_install=True)
    assert cli.cmd_watch_roads(args) == 0
    assert imported == [[0]] and installs == []  # (into the road data, the installed addon left alone)
    args.no_install = False
    assert cli.cmd_watch_roads(args) == 0
    assert imported == [[0], [0]] and installs == [True]  # (as before: installed again)


def test_the_road_watcher_also_reads_another_clients_recorded_walks(tmp_path, monkeypatch):
    """--also-wtf: another client's account folders watched too (a test client's saved files, copied here,
    2026-10-08: the user records roads there), but only its walks recorded since --also-since: never its strokes or
    walls (its test runs draw them) nor its dungeons' ways in (a GM's teleport into one would be learned as one)."""
    import time

    import azerothgps.roads.build as build
    import azerothgps.roads.export as export
    import azerothgps.roads.recorded as recorded
    import azerothgps.roads.tracks as tracks

    real, other = tmp_path / "real", tmp_path / "other"
    for wtf in (real, other):
        saved = wtf / "ACCOUNT" / "SavedVariables"
        saved.mkdir(parents=True)
        (saved / "AzerothGPS.lua").write_text("AzerothGPSDB = {}\n", encoding="utf-8")
    monkeypatch.setattr(cli, "wtf_account_dir", lambda *a: real)
    monkeypatch.setattr(recorded, "Walks", lambda *a, **k: "walks")
    read = []

    def one_road_in_the_other(wtf, overrides, per, walks=None, only=None):
        read.append((wtf, walks, only))
        if wtf == other:
            per[0] = 1
            return 1
        return 0
    monkeypatch.setattr(tracks, "import_tracks", one_road_in_the_other)
    imported = []
    monkeypatch.setattr(build, "reapply_overrides", lambda data, conts: imported.append(list(conts)))
    monkeypatch.setattr(export, "write_roads_lua", lambda *a, **k: None)
    monkeypatch.setattr(cli, "_override_keys", lambda *a: set())
    entrances = []
    monkeypatch.setattr(cli, "_import_saved_entrances", lambda wtf: entrances.append(wtf) or 0)
    monkeypatch.setattr(cli, "_touches_capital", lambda *a: False)
    args = argparse.Namespace(wow_path="wow", flavor="flavor", product="product", once=True, interval=0.0,
                              no_install=True, also_wtf=[str(other)], also_since="2026-10-08 08:00")
    assert cli.cmd_watch_roads(args) == 0
    (w1, walks1, only1), (w2, walks2, only2) = read
    assert (w1, walks1, only1) == (real, "walks", None) and w2 == other and callable(walks2)
    assert entrances == [real] and imported == [[0]]
    at = time.mktime(time.strptime("2026-10-08 08:30", "%Y-%m-%d %H:%M"))
    assert only2({"recorded": True, "time": at})
    assert not only2({"recorded": True, "time": at - 3600})  # (before --also-since: an older test run's)
    assert not only2({"op": "add", "time": at}) and not only2({"op": "wall", "time": at})  # (strokes, walls)


def test_the_road_watcher_takes_all_of_an_own_clients_edits(tmp_path, monkeypatch):
    """--own-wtf: a client the user plays on themselves (a second client, 2026-10-14): its strokes and
    walls count too, read as the game's own are, but never its dungeons' ways in (GM teleports). --wtf: a snapshot's
    account folders read instead of the game's."""
    import azerothgps.roads.build as build
    import azerothgps.roads.export as export
    import azerothgps.roads.recorded as recorded
    import azerothgps.roads.tracks as tracks

    live, own = tmp_path / "live", tmp_path / "own"
    for wtf in (live, own):
        saved = wtf / "ACCOUNT" / "SavedVariables"
        saved.mkdir(parents=True)
        (saved / "AzerothGPS.lua").write_text("AzerothGPSDB = {}\n", encoding="utf-8")
    monkeypatch.setattr(cli, "wtf_account_dir", lambda *a: tmp_path / "the game's")
    monkeypatch.setattr(recorded, "Walks", lambda *a, **k: "walks")
    read = []

    def one_road_in_the_own(wtf, overrides, per, walks=None, only=None):
        read.append((wtf, walks, only))
        if wtf == own:
            per[1] = 1
            return 1
        return 0
    monkeypatch.setattr(tracks, "import_tracks", one_road_in_the_own)
    imported = []
    monkeypatch.setattr(build, "reapply_overrides", lambda data, conts: imported.append(list(conts)))
    monkeypatch.setattr(export, "write_roads_lua", lambda *a, **k: None)
    monkeypatch.setattr(cli, "_override_keys", lambda *a: set())
    entrances = []
    monkeypatch.setattr(cli, "_import_saved_entrances", lambda wtf: entrances.append(wtf) or 0)
    monkeypatch.setattr(cli, "_touches_capital", lambda *a: False)
    args = argparse.Namespace(wow_path="wow", flavor="flavor", product="product", once=True, interval=0.0,
                              no_install=True, wtf=str(live), own_wtf=[str(own)])
    assert cli.cmd_watch_roads(args) == 0
    assert read == [(live, "walks", None), (own, "walks", None)]  # (every edit of both, no filter)
    assert entrances == [live] and imported == [[1]]
