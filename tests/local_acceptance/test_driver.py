"""Independent archive order/conservation and accepted-source corruption controls."""

import ast
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.local_acceptance import run
from tests.local_acceptance.run import (
    check_input,
    check_reordering,
    fingerprint,
    reordered_archive,
)
from tests.local_acceptance.test_checker_v3 import mixed_v3_archive
from tests.sources.test_reader import rewrite
from tests.support.v2_collection import mixed_archive


@pytest.mark.parametrize(
    "damage",
    [
        "history",
        "payload",
        "omitted",
        "duplicated",
        "payload_omitted",
        "payload_duplicated",
    ],
)
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
    if damage in {"payload_omitted", "payload_duplicated"}:
        with ZipFile(destination) as archive:
            parts = {n: archive.read(n) for n in archive.namelist()}
            name = next(n for n in parts if n.endswith("manual.pdf"))
        if damage == "payload_omitted":
            parts.pop(name)
            with ZipFile(destination, "w") as archive:
                for filename, data in parts.items():
                    archive.writestr(filename, data)
        else:
            with (
                pytest.warns(UserWarning, match="Duplicate name"),
                ZipFile(destination, "a") as archive,
            ):
                archive.writestr(name, parts[name])
        with pytest.raises(AssertionError, match="reorder"):
            check_reordering(source, destination)
        return
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
    modules = {"checker", "facts", "support", "scope", "images", "gaps"}
    assert {
        p.stem for p in root.glob("*.py") if not p.stem.startswith("test_")
    } == modules | {"run", "__init__"}
    for name in (m + ".py" for m in modules):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(
                    a.name.split(".")[0] in sys.stdlib_module_names for a in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                assert (node.level == 1 and node.module in modules) or (
                    node.level == 0
                    and node.module.split(".")[0] in sys.stdlib_module_names
                )


def test_four_input_driver_executes_twelve_complete_synthetic_outputs(
    tmp_path, monkeypatch
):
    selected = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("PYTHONPATH", str(selected / "src") + ";" + str(selected))
    sources = {key: mixed_v3_archive(tmp_path / (key + ".brz")) for key in "ABCD"}
    pins = {key: fingerprint(path) for key, path in sources.items()}
    output = tmp_path / "out"
    run.run_acceptance(sources, output, pins)
    operations = json.loads((output / "operations.json").read_bytes())
    assert len(operations) == 12
    assert {(r["source"], r["variant"]) for r in operations} == {
        (key, variant) for key in "ABCD" for variant in ("exact", "repeat", "reordered")
    }
    assert all(r["summary"]["generated_embeds"] == 2 for r in operations)
    assert all(fingerprint(path) == pins[key] for key, path in sources.items())
    assert all(
        (output / (key + suffix) / "migration-record.json").is_file()
        for key in "ABCD"
        for suffix in ("", "-repeat", "-reordered")
    )


def test_driver_help_requires_four_original_arguments():
    help_result = subprocess.run(
        [sys.executable, "-m", "tests.local_acceptance.run", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert all("--source-" + key in help_result.stdout for key in "abcd")
    missing = subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.local_acceptance.run",
            "--source-a",
            "A.brz",
            "--source-b",
            "B.brz",
            "--source-c",
            "C.brz",
            "--output",
            "tmp/audit",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode == 2 and "--source-d" in missing.stderr


def test_driver_final_guard_rejects_original_drift_after_all_twelve_outputs(
    tmp_path, monkeypatch
):
    selected = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("PYTHONPATH", str(selected / "src") + ";" + str(selected))
    sources = {key: mixed_archive(tmp_path / (key + ".brz")) for key in "ABCD"}
    pins = {key: fingerprint(path) for key, path in sources.items()}
    output = tmp_path / "out"
    guard = run.check_reordering

    def change_after_last_operation(source, reordered):
        guard(source, reordered)
        if (
            source == sources["D"]
            and (output / "D-reordered/migration-record.json").is_file()
        ):
            rewrite(
                sources["A"],
                "modificationlogs.json",
                b'{"Opaque":"drift after final conversion"}',
            )

    monkeypatch.setattr(run, "check_reordering", change_after_last_operation)
    with pytest.raises(AssertionError, match="accepted source changed"):
        run.run_acceptance(sources, output, pins)
    assert all(
        (output / (key + suffix) / "migration-record.json").is_file()
        for key in "ABCD"
        for suffix in ("", "-repeat", "-reordered")
    )
    assert not (output / "aggregate.json").exists()


def test_driver_refuses_missing_fourth_input_and_existing_output_without_writes(
    tmp_path, monkeypatch
):
    selected = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("PYTHONPATH", str(selected / "src") + ";" + str(selected))
    sources = {key: mixed_archive(tmp_path / (key + ".brz")) for key in "ABCD"}
    pins = {key: fingerprint(path) for key, path in sources.items()}
    output = tmp_path / "caller"
    output.mkdir()
    marker = output / "caller.bin"
    marker.write_bytes(b"caller bytes")
    with pytest.raises(AssertionError, match="four mandatory original"):
        run.run_acceptance(
            {key: path for key, path in sources.items() if key != "D"}, output, pins
        )
    with pytest.raises(FileExistsError):
        run.run_acceptance(sources, output, pins)
    assert {p.name: p.read_bytes() for p in output.iterdir()} == {
        "caller.bin": b"caller bytes"
    }
