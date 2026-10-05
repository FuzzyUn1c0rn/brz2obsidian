"""Independent archive order/conservation and accepted-source corruption controls."""

import ast
import json
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.local_acceptance.run import (
    check_input,
    check_reordering,
    fingerprint,
    reordered_archive,
)
from tests.sources.test_reader import rewrite
from tests.support.v2_collection import mixed_archive


@pytest.mark.parametrize("damage", ["history", "payload", "omitted", "duplicated"])
def test_reordered_input_must_preserve_every_raw_record_and_payload(tmp_path, damage):
    source = mixed_archive(tmp_path / "source.brz")
    rewrite(
        source, "modificationlogs.json", b'{"Opaque":"initial independent history"}'
    )
    destination = tmp_path / "reordered.brz"
    before = fingerprint(source)
    reordered_archive(source, destination)
    check_reordering(source, destination)
    assert fingerprint(source) == before
    with ZipFile(destination) as archive:
        if damage == "payload":
            name = next(n for n in archive.namelist() if n.endswith("manual.pdf"))
            data = archive.read(name).replace(b"synthetic", b"different")
        else:
            name = (
                "thoughts.json"
                if damage in {"omitted", "duplicated"}
                else "modificationlogs.json"
            )
            rows = archive.read(name).decode("utf-8-sig").encode().splitlines()
            if damage == "omitted":
                rows.pop()
            elif damage == "duplicated":
                rows.append(rows[0])
            else:
                rows = [
                    json.dumps({"opaque_history": "same-count changed source"}).encode()
                ]
            data = b"\n".join(rows)
    rewrite(destination, name, data)
    with pytest.raises(AssertionError, match="reorder"):
        check_reordering(source, destination)


def test_final_fingerprint_guard_detects_same_count_opaque_source_change(tmp_path):
    source = mixed_archive(tmp_path / "source.brz")
    rewrite(
        source, "modificationlogs.json", b'{"Opaque":"initial independent history"}'
    )
    before = fingerprint(source)
    check_input(source, before)
    rewrite(
        source,
        "modificationlogs.json",
        b'{"Opaque":"changed without converter meanings"}',
    )
    with pytest.raises(AssertionError, match="accepted source changed"):
        check_input(source, before)


def test_expected_fact_oracle_has_only_stdlib_and_local_oracle_imports():
    root = Path(__file__).parent
    for name in ("checker.py", "facts.py", "support.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(
                    a.name.split(".")[0] in sys.stdlib_module_names for a in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                assert (node.level == 1 and node.module in {"facts", "support"}) or (
                    node.level == 0
                    and node.module.split(".")[0] in sys.stdlib_module_names
                )
