"""Independent raw-archive evidence qualifies the explicit absent TXT warning."""

import hashlib
import json
import shutil
from copy import deepcopy

import pytest

from brz2obsidian.application.wiring import default_workflow
from tests.local_acceptance.checker import check_vault
from tests.local_acceptance.test_checker_v2 import rewrite_record
from tests.sources.test_brz_absent_txt_declarations import (
    RULE,
    TXT,
    WARNING,
    absent_txt_source,
)


@pytest.fixture(scope="module")
def absent_txt_output(tmp_path_factory):
    root = tmp_path_factory.mktemp("absent-txt-audit")
    source = absent_txt_source(root, "authored_note")
    vault = root / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "warnings" and result.receipt.verified
    check_vault(source, vault)
    return source, vault, result


def test_complete_independent_brz_audit_accepts_missing_txt_without_pdf(
    absent_txt_output,
):
    source, vault, _ = absent_txt_output
    assert check_vault(source, vault)["payloads"] == 1


@pytest.mark.parametrize(
    "damage,guard",
    [
        ("remove_declaration", "all attachment identities"),
        ("invent_actual_bytes", "no fabricated payload"),
        ("remove_finding", "warning finding cardinality"),
        ("borrow_pdf_rule", "warning finding identity"),
        ("false_absence", "warning predicate evidence"),
        ("claim_recovered", "unrecovered archived TXT warning meaning"),
    ],
)
def test_independent_txt_audit_rejects_rehashed_missing_payload_and_finding_claims(
    absent_txt_output, tmp_path, damage, guard
):
    source, pristine, result = absent_txt_output
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    vault = tmp_path / "forged"
    shutil.copytree(pristine, vault)
    record = json.loads((vault / "migration-record.json").read_bytes())
    identity = deepcopy(record["source_identity"])
    asset = next(row for row in record["asset_targets"] if row["asset_id"] == TXT)
    issue = next(row for row in record["issues"] if row["rule_id"] == RULE)
    finding = asset["source_findings"][0]
    if damage == "remove_declaration":
        record["asset_targets"].remove(asset)
    elif damage == "invent_actual_bytes":
        asset.update(actual_length=17, actual_sha256="0" * 64)
    elif damage == "remove_finding":
        asset["source_findings"] = []
        record["issues"].remove(issue)
    elif damage == "borrow_pdf_rule":
        finding["rule_id"] = issue["rule_id"] = "thebrain-format5/absent-txt/v1"
        issue["message"] = (
            "Absent source file; its metadata is retained and an intact PDF exists under the same owner. "
            "Observed: " + finding["observed_json"]
        )
    elif damage == "false_absence":
        observation = json.loads(finding["observed_json"])
        observation["present"] = True
        finding["observed_json"] = json.dumps(observation)
        issue["message"] = WARNING + " Observed: " + finding["observed_json"]
    else:
        issue["message"] = (
            "The missing TXT bytes were recovered. Observed: "
            + finding["observed_json"]
        )
    forged_result = result.model_dump(mode="json")
    forged_result["receipt"]["destination"] = str(vault.resolve())
    if damage == "remove_finding":
        forged_result["outcome"] = "clean"
    rewrite_record(vault, record, forged_result)
    (tmp_path / "forged-result.json").write_text(
        json.dumps(forged_result), encoding="utf-8"
    )
    assert record["source_identity"] == identity
    with pytest.raises(AssertionError) as error:
        check_vault(source, vault)
    assert str(error.value).startswith(guard)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
