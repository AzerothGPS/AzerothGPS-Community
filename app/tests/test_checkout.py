from pathlib import Path


def test_the_tests_import_this_checkouts_code():
    # The venv's editable install points at one checkout. A second one (another clone, a
    # worktree) imported that one's azerothgps, whose paths load that one's addon: a data refresh's tests ran on
    # main's data and failed. pytest's `pythonpath` puts this checkout's app first.
    import azerothgps

    assert Path(azerothgps.__file__).resolve().parents[1] == Path(__file__).resolve().parents[1], azerothgps.__file__
