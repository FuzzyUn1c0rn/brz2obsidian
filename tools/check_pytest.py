"""Execution counters for the check runner; no converter or Qt dependencies."""

import json
import os
from pathlib import Path

import pytest

COUNTS = {
    "collected": 0,
    "passed": 0,
    "failed": 0,
    "skipped": 0,
    "errors": 0,
    "gui_executed": 0,
}
EXECUTED = set()
TIMINGS = None
WORKER = False
COLLECTED = False


def pytest_sessionstart(session):
    global TIMINGS, WORKER
    WORKER = hasattr(session.config, "workerinput")
    if WORKER:
        return
    TIMINGS = (
        Path(os.environ["BRZ_CHECK_COUNTS"])
        .with_name("pytest-timings.jsonl")
        .open("w", encoding="utf-8", buffering=1)
    )


def pytest_collection_modifyitems(items):
    if WORKER:
        return
    COUNTS["collected"] = len(items)


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_node_collection_finished(node, ids):
    global COLLECTED
    if not COLLECTED:
        COLLECTED = True
        COUNTS["collected"] = len(ids)


def pytest_collectreport(report):
    if WORKER:
        return
    if report.skipped:
        COUNTS["skipped"] += 1
    elif report.failed:
        COUNTS["errors"] += 1


def pytest_runtest_logreport(report):
    if WORKER:
        return
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
        if "gui" in report.keywords and not report.skipped:
            COUNTS["gui_executed"] += 1
        COUNTS[
            "passed" if report.passed else "failed" if report.failed else "skipped"
        ] += 1
    elif report.skipped:
        COUNTS["skipped"] += 1
    elif report.failed:
        COUNTS["errors"] += 1


def pytest_sessionfinish():
    if WORKER:
        return
    try:
        Path(os.environ["BRZ_CHECK_COUNTS"]).write_text(
            json.dumps({**COUNTS, "executed_nodes": sorted(EXECUTED)}), encoding="utf-8"
        )
    finally:
        if TIMINGS is not None:
            TIMINGS.close()
