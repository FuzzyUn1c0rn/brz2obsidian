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
TIMINGS = None


def pytest_sessionstart():
    global TIMINGS
    TIMINGS = Path(os.environ["BRZ_CHECK_COUNTS"]).with_name(
        "pytest-timings.jsonl"
    ).open("w", encoding="utf-8", buffering=1)


def pytest_collection_modifyitems(items):
    COUNTS["collected"] = len(items)
    GUI.update(item.nodeid for item in items if item.get_closest_marker("gui"))


def pytest_collectreport(report):
    if report.skipped:
        COUNTS["skipped"] += 1
    elif report.failed:
        COUNTS["errors"] += 1


def pytest_runtest_logreport(report):
    TIMINGS.write(
        json.dumps(
            {
                "nodeid": report.nodeid,
                "when": report.when,
                "duration": report.duration,
                "outcome": report.outcome,
            }
        )
        + "\n"
    )
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
    try:
        Path(os.environ["BRZ_CHECK_COUNTS"]).write_text(
            json.dumps({**COUNTS, "executed_nodes": sorted(EXECUTED)}), encoding="utf-8"
        )
    finally:
        if TIMINGS is not None:
            TIMINGS.close()
