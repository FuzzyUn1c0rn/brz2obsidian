"""Execution counters for the check runner; no converter or Qt dependencies."""

import json
import os
from pathlib import Path

COUNTS = {
    "collected": 0,
    "passed": 0,
    "failed": 0,
    "skipped": 0,
    "errors": 0,
    "gui_executed": 0,
}
GUI = set()
EXECUTED = set()


def pytest_collection_modifyitems(items):
    COUNTS["collected"] = len(items)
    GUI.update(item.nodeid for item in items if item.get_closest_marker("gui"))


def pytest_collectreport(report):
    if report.skipped:
        COUNTS["skipped"] += 1
    elif report.failed:
        COUNTS["errors"] += 1


def pytest_runtest_logreport(report):
    if report.when == "call":
        if not report.skipped:
            EXECUTED.add(report.nodeid)
        if report.nodeid in GUI and not report.skipped:
            COUNTS["gui_executed"] += 1
        COUNTS[
            "passed" if report.passed else "failed" if report.failed else "skipped"
        ] += 1
    elif report.skipped:
        COUNTS["skipped"] += 1
    elif report.failed:
        COUNTS["errors"] += 1


def pytest_sessionfinish():
    Path(os.environ["BRZ_CHECK_COUNTS"]).write_text(
        json.dumps({**COUNTS, "executed_nodes": sorted(EXECUTED)}), encoding="utf-8"
    )
