"""TEMPORARY DEBUG PROBE - REVERT BEFORE MERGE.

Arms a faulthandler watchdog before every test so the macOS CI hang dumps
the stuck thread's traceback instead of wedging the job until timeout.
Re-armed at each test's logstart, so it covers setup, call, and the
previous test's teardown.
"""

import faulthandler


def pytest_runtest_logstart(nodeid, location):
    faulthandler.dump_traceback_later(240, exit=True)


def pytest_sessionfinish(session, exitstatus):
    faulthandler.cancel_dump_traceback_later()
