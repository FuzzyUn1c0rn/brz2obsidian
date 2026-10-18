"""Synthetic controls against internally consistent false migration receipts."""

import hashlib
import json
import shutil
from copy import deepcopy

import pytest

from brz2obsidian.application.wiring import default_workflow
from tests.local_acceptance.checker import check_run_result, check_vault
from tests.local_acceptance.scope import dump_json
from tests.support.v2_collection import mixed_archive


def rewrite_record(vault, record, result):
    (vault / "migration-record.json").write_text(dump_json(record), encoding="utf-8")
    result["counts"] = record["counts"] | {
        "actual_notes": record["counts"]["planned_notes"],
        "actual_assets": record["counts"]["planned_assets"],
        "actual_category_notes": record["counts"]["planned_category_notes"],
        "actual_support_files": record["counts"]["planned_support_files"],
        "actual_files": sum(p.is_file() for p in vault.rglob("*")),
    }
    result["receipt"]["counts"] = result["counts"]
    result["issues"] = record["issues"]
    result["source_identity"] = result["receipt"]["source_identity"] = record[
        "source_identity"
    ]
    result["receipt"]["manifest"] = [
        {
            "relative_path": p.relative_to(vault).as_posix(),
            "length": len(p.read_bytes()),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
        for p in vault.rglob("*")
        if p.is_file()
    ]
    assert all(
        (vault / m["relative_path"]).stat().st_size == m["length"]
        and hashlib.sha256((vault / m["relative_path"]).read_bytes()).hexdigest()
        == m["sha256"]
        for m in result["receipt"]["manifest"]
    )


def fixture(tmp_path):
    source = mixed_archive(tmp_path / "source.brz")
    vault = tmp_path / "vault"
    result = (
        default_workflow().convert(source, vault).model_dump(mode="json", by_alias=True)
    )
    check_vault(source, vault)
    record = json.loads((vault / "migration-record.json").read_bytes())
    return source, vault, result, record


def copy_case(prepared, destination):
    source, vault, result, record = prepared
    destination.mkdir()
    copied_source = destination / "source.brz"
    copied_vault = destination / "vault"
    shutil.copy2(source, copied_source)
    shutil.copytree(vault, copied_vault)
    copied_result, copied_record = deepcopy((result, record))
    copied_result["receipt"]["destination"] = str(copied_vault.resolve())
    return copied_source, copied_vault, copied_result, copied_record


def isolation_sample(prepared):
    source, vault, _, record = prepared
    return (
        source.read_bytes(),
        (vault / "migration-record.json").read_bytes(),
        deepcopy(
            next(
                e for e in record["original_evidence"] if e["key"] == "attachments.json"
            )
        ),
        deepcopy(record["adaptations"]),
    )


@pytest.fixture(scope="module")
def verified_v2_seed(tmp_path_factory):
    root = tmp_path_factory.mktemp("verified-v2")
    source = mixed_archive(root / "source.brz")
    vault = root / "vault"
    result = (
        default_workflow().convert(source, vault).model_dump(mode="json", by_alias=True)
    )
    summary = check_vault(source, vault)
    check_run_result(result, vault, summary)
    assert tuple(
        summary[key]
        for key in ("notes", "payloads", "backups", "references", "warnings", "videos")
    ) == (7, 8, 3, 2, 1, 1)
    record = json.loads((vault / "migration-record.json").read_bytes())
    prepared = source, vault, result, record
    # A second private case witnesses both file and nested-data isolation.
    sentinel = copy_case(prepared, root / "sentinel")
    expected = isolation_sample(prepared)

    def assert_untouched():
        # Check before reuse: a tainted seed must never prepare another case.
        assert isolation_sample(prepared) == expected, "verified seed was mutated"
        assert isolation_sample(sentinel) == expected, "separate case was mutated"

    yield prepared, assert_untouched
    assert_untouched()


@pytest.fixture
def isolated_v2_case(tmp_path, verified_v2_seed, request):
    prepared, assert_untouched = verified_v2_seed
    assert_untouched()
    copied = copy_case(prepared, tmp_path / "case")
    yield copied
    damage = request.node.callspec.params["damage"]
    if damage in {"ordinary_url_video", "adaptation_fact"}:
        source, vault, _, record = copied
        seed_source, seed_vault, _, seed_record = prepared
        if damage == "ordinary_url_video":
            assert source.read_bytes() != seed_source.read_bytes()
            assert record["original_evidence"] != seed_record["original_evidence"]
        else:
            assert record["adaptations"] != seed_record["adaptations"]
            assert (vault / "migration-record.json").read_bytes() != (
                seed_vault / "migration-record.json"
            ).read_bytes()
        assert_untouched()
