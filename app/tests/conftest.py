"""The `timing` mark: a test that holds work to a budget by a clock (a slice of background work under FRAME_MS, a click
under its limit, as many frames of work as a reference PC's CPU gets done).

On CI (the self-hosted runners: 2-CPU containers, up to 15 of them on one 8-core PC, among other repos' jobs) a timing test
that fails an assert is run again, up to TIMING_RERUNS times (pytest-rerunfailures, app[dev]); the gate lists every
test that passed only on a rerun (.github/scripts/ci_gate.py skips). A preempted slice there runs 2-25x long once
(5 ms here, 151 against 150 there): never twice in a row in the same spot. A slice really over its budget fails every
try. Here, on a dev PC, nothing is run again: one failure is a failure.

Shards: with AGPS_SHARD=i/n (CI's pytest jobs, .github/workflows/tests.yml) only shard i of n's test files run. The files
are split by their seconds in tests/data/shard_seconds.json (the longest first, each onto the shard with the least so
far; a file not listed counts as the median), a whole file to one shard, so its module fixtures are built once. Every
shard works it out from the same files, so each file runs in exactly one. Refresh the seconds from a run's junit.xml:
`python -P .github/scripts/ci_gate.py shard-seconds <junit.xml>...` (2026-11-27: the suite took 36 minutes on one CI job
of 2 CPUs when quiet and passed its 40-minute limit when the runners were busy).
"""

import gc
import json
import os
from pathlib import Path

import pytest

TIMING_RERUNS = 2
SHARD_SECONDS = Path(__file__).parent / "data" / "shard_seconds.json"


def pytest_configure(config):
    config.addinivalue_line("markers", "timing: holds work to a budget by a clock; run again on CI when it fails "
                                       "(tests/conftest.py)")


def shard_of_files(files, n, seconds):
    """{file: shard 1..n}: the longest files first, each onto the shard with the fewest seconds so far (ties: the lower
    shard; equal seconds: by name)."""
    known = sorted(s for f, s in seconds.items() if f in files)
    median = known[len(known) // 2] if known else 1.0
    load = [0.0] * n
    out = {}
    for f in sorted(files, key=lambda f: (-seconds.get(f, median), f)):
        i = min(range(n), key=lambda k: (load[k], k))
        out[f] = i + 1
        load[i] += seconds.get(f, median)
    return out


def _shard(config, items):
    spec = os.environ.get("AGPS_SHARD", "").strip()
    if not spec:
        return
    i, n = (int(v) for v in spec.split("/"))
    assert 1 <= i <= n, f"AGPS_SHARD={spec}: want i/n with 1 <= i <= n"
    seconds = json.loads(SHARD_SECONDS.read_text(encoding="utf-8")) if SHARD_SECONDS.exists() else {}
    files = {item.nodeid.split("::")[0] for item in items}
    where = shard_of_files(files, n, seconds)
    keep = [item for item in items if where[item.nodeid.split("::")[0]] == i]
    dropped = [item for item in items if where[item.nodeid.split("::")[0]] != i]
    if dropped:
        config.hook.pytest_deselected(items=dropped)
        items[:] = keep


def pytest_collection_modifyitems(config, items):
    _shard(config, items)
    if os.environ.get("CI") != "true" or not config.pluginmanager.hasplugin("rerunfailures"):
        return
    for item in items:
        if item.get_closest_marker("timing"):
            item.add_marker(pytest.mark.flaky(reruns=TIMING_RERUNS, only_rerun=["AssertionError"]))


@pytest.fixture(autouse=True, scope="module")
def _a_modules_harnesses_freed_after_it():
    """Python's cycle collector run after each test file: a harness (gameharness.start, a LuaRuntime) a test left in a
    cycle (a Python function it gave Lua that refers back to the runtime) is freed then, not whenever Python's own
    allocations next trigger it, which never sees Lua's memory (2026-11-23: dead harnesses, GBs a CI worker)."""
    yield
    gc.collect()
