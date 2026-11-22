"""`agps install-addon`: the addon copied into the game's AddOns folder, and into every other one listed in
~/.agps-installs (a second install of the game, a test server's; asked 2026-10-01)."""

from pathlib import Path
from types import SimpleNamespace

from azerothgps import cli


def test_install_goes_into_every_listed_addons_folder(tmp_path, monkeypatch):
    real = tmp_path / "World of Warcraft" / "_forever_" / "Interface" / "AddOns"
    private = tmp_path / "Private" / "beta" / "Interface" / "AddOns"
    real.mkdir(parents=True)
    private.mkdir(parents=True)
    listed = tmp_path / "installs"
    listed.write_text(f"# a test server's\n\n{private}\n{tmp_path / 'missing'}\n{real}\n", encoding="utf-8")
    monkeypatch.setattr(cli, "EXTRA_INSTALLS", listed)
    monkeypatch.setattr("azerothgps.hpa.refresh", lambda: None)  # (the terrain's blocks: not this test's)
    (private / "AzerothGPS").mkdir()
    (private / "AzerothGPS" / "Stale.lua").write_text("-- gone from the addon", encoding="utf-8")
    assert cli.extra_addons_dirs() == [private, tmp_path / "missing", real]
    rc = cli.cmd_install_addon(SimpleNamespace(wow_path=str(tmp_path / "World of Warcraft"), flavor="_forever_", dev=False))
    assert rc == 0
    for addons in (real, private):
        assert (addons / "AzerothGPS" / "AzerothGPS.toc").is_file()
    assert not (private / "AzerothGPS" / "Stale.lua").exists()  # (a clean copy there too)


def test_no_list_means_just_the_game(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "EXTRA_INSTALLS", Path(tmp_path / "none"))
    assert cli.extra_addons_dirs() == []


def test_the_dev_tools_go_only_where_private_paths_allow(tmp_path, monkeypatch):
    # (Kooki3z, 2026-11-22, 1.3.14: never the live game) `--dev` puts the developer addon only into the folders
    # private_paths' rule allows, and the floor survey's and route review's lists are written after it's copied (not
    # wiped by the copy)
    live = tmp_path / "World of Warcraft" / "_forever_" / "Interface" / "AddOns"
    other = tmp_path / "Other" / "beta" / "Interface" / "AddOns"
    for d in (live, other):
        d.mkdir(parents=True)
    dev = tmp_path / "dev" / "DevTools"
    dev.mkdir(parents=True)
    (dev / "DevTools.toc").write_text("Dev.lua\nRouteReview.lua\n", encoding="utf-8")
    listed = tmp_path / "installs"
    listed.write_text(f"{other}\n", encoding="utf-8")
    monkeypatch.setattr(cli, "EXTRA_INSTALLS", listed)
    monkeypatch.setattr(cli, "_dev_addon", lambda: dev)
    monkeypatch.setattr(cli, "private_client", lambda addons: Path(addons) == other)
    monkeypatch.setattr("azerothgps.hpa.refresh", lambda: None)
    wrote = []
    monkeypatch.setattr("azerothgps.routereview.export_review",
                        lambda dirs: wrote.extend((d / "DevTools").is_dir() for d in dirs))
    rc = cli.cmd_install_addon(SimpleNamespace(wow_path=str(tmp_path / "World of Warcraft"), flavor="_forever_", dev=True))
    assert rc == 0
    assert not (live / "DevTools").exists() and (live / "AzerothGPS" / "AzerothGPS.toc").is_file()
    assert (other / "DevTools" / "DevTools.toc").is_file()
    assert wrote == [False, True]  # (the lists after the dev copy: in it where it went)


def test_with_no_rule_the_dev_tools_go_nowhere(tmp_path, monkeypatch):
    import builtins
    real = builtins.__import__

    def no_private(name, *a, **kw):
        if name.endswith("private_paths"):
            raise ImportError(name)
        return real(name, *a, **kw)
    monkeypatch.setattr(builtins, "__import__", no_private)
    assert cli.private_client(tmp_path) is False
