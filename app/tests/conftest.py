"""The `timing` mark: a test that holds work to a budget by a clock (a slice of background work under FRAME_MS, a click
under its limit, as many frames of work as a reference PC's CPU gets done).

On CI (the self-hosted runners: 2-CPU containers, up to 15 of them on one 8-core PC, among other repos' jobs) a timing test
that fails an assert is run again, up to TIMING_RERUNS times (pytest-rerunfailures, app[dev]); the gate lists every
test that passed only on a rerun (.github/scripts/ci_gate.py skips). A preempted slice there runs 2-25x long once
(5 ms here, 151 against 150 there): never twice in a row in the same spot. A slice really over its budget fails every
try. Here, on a dev PC, nothing is run again: one failure is a failure.
"""

import gc
import os

import pytest

TIMING_RERUNS = 2


def pytest_configure(config):
    config.addinivalue_line("markers", "timing: holds work to a budget by a clock; run again on CI when it fails "
                                       "(tests/conftest.py)")


def pytest_collection_modifyitems(config, items):
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
