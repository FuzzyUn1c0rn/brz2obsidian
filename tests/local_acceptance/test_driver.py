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
from tests.support.combined_collection import combined_archive
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


def test_expected_fact_oracle_has_only_reviewed_imports():
    root = Path(__file__).parent
    modules = {
        "api_checker",
        "api_manifest",
        "api_generated",
        "api_image_proofs",
        "api_note_text",
        "api_scope",
        "api_scope_inputs",
        "api_svg",
        "checker",
        "facts",
        "support",
        "scope",
        "images",
        "gaps",
        "text",
    }
    assert {
        p.stem for p in root.glob("*.py") if not p.stem.startswith("test_")
    } == modules | {"run", "__init__"}
    for name in (m + ".py" for m in modules):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(
                    a.name.split(".")[0] in sys.stdlib_module_names for a in node.names
                ) or (
                    name == "api_checker.py"
                    and len(node.names) == 1
                    and node.names[0].name == "yaml"
                    and node.names[0].asname is None
                )
            elif isinstance(node, ast.ImportFrom):
                assert (node.level == 1 and node.module in modules) or (
                    node.level == 0
                    and node.module.split(".")[0] in sys.stdlib_module_names
                )


def test_five_input_driver_executes_fifteen_complete_synthetic_outputs(
    tmp_path, monkeypatch
):
    selected = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("PYTHONPATH", str(selected / "src") + ";" + str(selected))
    sources = {
        key: (combined_archive if key == "E" else mixed_v3_archive)(
            tmp_path / (key + ".brz")
        )
        for key in "ABCDE"
    }
    pins = {key: fingerprint(path) for key, path in sources.items()}
    output = tmp_path / "out"
    run.run_acceptance(sources, output, pins)
    operations = json.loads((output / "operations.json").read_bytes())
    assert len(operations) == 15
    assert {(r["source"], r["variant"]) for r in operations} == {
        (key, variant)
        for key in "ABCDE"
        for variant in ("exact", "repeat", "reordered")
    }
    assert all(r["summary"]["generated_embeds"] == 2 for r in operations)
    assert all(
        r["raw_inventory_before_inclusion"]["thoughts.json"]
        > r["summary"]["source_items"]
        for r in operations
    )
    e = [r for r in operations if r["source"] == "E"]
    assert all(
        r["summary"]["external_files"] == 3
        and r["summary"]["literal_owners"] == 2
        and r["summary"]["sized_image_owners"] == 2
        for r in e
    )
    assert all(fingerprint(path) == pins[key] for key, path in sources.items())
    assert all(
        (output / (key + suffix) / "migration-record.json").is_file()
        for key in "ABCDE"
        for suffix in ("", "-repeat", "-reordered")
    )


def test_driver_help_requires_five_original_arguments():
    help_result = subprocess.run(
        [sys.executable, "-m", "tests.local_acceptance.run", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert all("--source-" + key in help_result.stdout for key in "abcde")
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
    assert (
        missing.returncode == 2
        and "--source-d" in missing.stderr
        and "--source-e" in missing.stderr
    )


def test_driver_final_guard_rejects_original_drift_after_all_fifteen_outputs(
    tmp_path, monkeypatch
):
    selected = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("PYTHONPATH", str(selected / "src") + ";" + str(selected))
    sources = {key: mixed_archive(tmp_path / (key + ".brz")) for key in "ABCDE"}
    pins = {key: fingerprint(path) for key, path in sources.items()}
    output = tmp_path / "out"
    guard = run.check_reordering

    def change_after_last_operation(source, reordered):
        guard(source, reordered)
        if (
            source == sources["E"]
            and (output / "E-reordered/migration-record.json").is_file()
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
        for key in "ABCDE"
        for suffix in ("", "-repeat", "-reordered")
    )
    assert not (output / "aggregate.json").exists()


def test_driver_refuses_missing_fifth_input_and_existing_output_without_writes(
    tmp_path, monkeypatch
):
    selected = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("PYTHONPATH", str(selected / "src") + ";" + str(selected))
    sources = {key: mixed_archive(tmp_path / (key + ".brz")) for key in "ABCDE"}
    pins = {key: fingerprint(path) for key, path in sources.items()}
    output = tmp_path / "caller"
    output.mkdir()
    marker = output / "caller.bin"
    marker.write_bytes(b"caller bytes")
    with pytest.raises(AssertionError, match="five mandatory original"):
        run.run_acceptance(
            {key: path for key, path in sources.items() if key != "E"}, output, pins
        )
    with pytest.raises(FileExistsError):
        run.run_acceptance(sources, output, pins)
    assert {p.name: p.read_bytes() for p in output.iterdir()} == {
        "caller.bin": b"caller bytes"
    }


def test_driver_pins_complete_original_e_and_checks_pre_inclusion_inventory():
    assert run.INPUTS["E"] == (
        219504950,
        "bc55f68c9ab3febaa770bfc7a9a90621bcd82107d876664371e1ff8558b4cf68",
    )
    accepted = {"thoughts.json": 756, "links.json": 963, "attachments.json": 1364}
    run.check_source_e_raw_inventory(accepted)
    for key, count in accepted.items():
        with pytest.raises(AssertionError, match="before inclusion"):
            run.check_source_e_raw_inventory(accepted | {key: count - 1})


def test_driver_inspection_parity_rejects_consistent_conversion_identity_or_counts():
    inspection = {
        "outcome": "warnings",
        "issues": [{"code": "image_presentation_normalized"}],
        "source_identity": {"source_sha256": "a"},
        "counts": {
            "text_adaptations": 7,
            "image_presentation_normalizations": 2,
            "actual_assets": None,
        },
    }
    conversion = inspection | {"counts": inspection["counts"] | {"actual_assets": 12}}
    run.check_inspection(inspection, conversion)
    for altered in (
        conversion | {"source_identity": {"source_sha256": "b"}},
        conversion | {"issues": []},
        conversion | {"counts": conversion["counts"] | {"text_adaptations": 6}},
    ):
        with pytest.raises(AssertionError):
            run.check_inspection(inspection, altered)
