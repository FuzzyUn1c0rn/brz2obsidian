"""The expected facts come from raw archives, including self-consistent forgeries."""

import hashlib

import pytest

from brz2obsidian.application.wiring import default_workflow
from tests.local_acceptance.checker import check_vault, load_json
from tests.local_acceptance.test_checker_v2 import rewrite_record
from tests.support.combined_collection import combined_archive


@pytest.mark.parametrize("damage", ["literal_span", "image_bytes", "fake_counts"])
def test_combined_oracle_rejects_rehashed_recounted_forgery(tmp_path, damage):
    source = combined_archive(tmp_path / "source.brz")
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    check_vault(source, vault)
    record = load_json((vault / "migration-record.json").read_bytes())
    external = [
        a
        for a in record["asset_targets"]
        if a["availability"] == "external" and a["role"] == "file"
    ]
    documents = [d for t in record["item_targets"] for d in t["documents"]]
    literal = next(d for d in documents if d["text_adaptations"])
    sized = next(
        r for d in documents for r in d["references"] if r["presentation_normalization"]
    )
    image = next(a for a in record["asset_targets"] if a["asset_id"] == sized["target"])
    if damage == "drop_external":
        record["asset_targets"].remove(external[0])
    elif damage == "merge_external":
        external[1]["asset_id"] = external[0]["asset_id"]
    elif damage == "external_uri":
        external[0]["external_uri"] = external[0]["resource_link"] = (
            "file:///C:/wrong/manual.pdf"
        )
    elif damage == "location":
        evidence = next(
            e for e in record["original_evidence"] if e["key"] == "attachments.json"
        )
        row = next(a for a in evidence["records"] if a["Id"] == external[0]["asset_id"])
        row["Location"] = external[0]["original_name"] = r"C:\wrong\manual.pdf"
    elif damage in {"underescape", "overescape"}:
        path = vault / "Home — Opening.md"
        body = path.read_bytes()
        body = (
            body.replace(b"\\<Enter>", b"<Enter>", 1)
            if damage == "underescape"
            else body.replace(b"`<Code>", b"`\\<Code>", 1)
        )
        path.write_bytes(body)
    elif damage.startswith("literal_"):
        edit = literal["text_adaptations"][0]
        field = {
            "literal_span": "start",
            "literal_basis": "source_basis",
            "literal_digest": "source_digest",
        }[damage]
        edit[field] = edit[field] + 1 if field == "start" else "forged"
        adaptation = next(
            a
            for a in record["adaptations"]
            if a["kind"] == "literal_text" and a["document_key"] == literal["key"]
        )
        adaptation["text_edit"] = edit
    elif damage.startswith("sizing_"):
        sized["presentation_normalization"][
            "start" if damage == "sizing_span" else "basis"
        ] = 0 if damage == "sizing_span" else "original_bytes"
    elif damage == "wrong_owner":
        image["owner"] = external[0]["owner"]
    elif damage == "image_bytes":
        path = vault / image["relative_path"]
        body = path.read_bytes()
        path.write_bytes(body[:-1] + bytes([body[-1] ^ 1]))
        image["actual_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif damage == "warning":
        record["issues"] = [
            i for i in record["issues"] if i["code"] != "image_presentation_normalized"
        ]
    elif damage == "excluded":
        (vault / "private.bin").write_bytes(b"forgotten secret bytes")
    else:
        record["counts"]["present_assets"] += 3
        record["counts"]["planned_assets"] += 3
        record["counts"]["source_gaps"] += 3
        record["counts"]["text_adaptations"] -= 1
    rewrite_record(vault, record, result)
    with pytest.raises(AssertionError):
        check_vault(source, vault)
