"""The expected facts come from raw archives, including self-consistent forgeries."""

import hashlib

import pytest

from brz2obsidian.application.wiring import default_workflow
from tests.local_acceptance.checker import check_run_result, check_vault, load_json
from tests.local_acceptance.test_checker_v2 import rewrite_record
from tests.local_acceptance.text import literal_edits
from tests.support.combined_collection import combined_archive


def test_combined_raw_oracle_establishes_every_adaptation_and_payload(tmp_path):
    source = combined_archive(tmp_path / "source.brz")
    before = source.read_bytes()
    operation = default_workflow()
    inspected = operation.inspect(source)
    assert inspected.outcome == "warnings", inspected.model_dump_json()
    assert inspected.receipt is None
    vault = tmp_path / "vault"
    result = operation.convert(source, vault)
    assert result.outcome == "warnings", result.model_dump_json()
    summary = check_vault(source, vault)
    assert summary["external_files"] == 3
    assert summary["literal_owners"] == 2
    assert summary["image_presentation_normalizations"] == 2
    assert summary["sized_image_owners"] == 2
    check_run_result(result.model_dump(mode="json"), vault, summary)
    assert source.read_bytes() == before


@pytest.mark.parametrize(
    "damage",
    [
        "drop_external",
        "merge_external",
        "external_uri",
        "location",
        "underescape",
        "overescape",
        "literal_span",
        "literal_basis",
        "literal_digest",
        "sizing_span",
        "sizing_basis",
        "wrong_owner",
        "image_bytes",
        "warning",
        "excluded",
        "fake_counts",
    ],
)
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


@pytest.mark.parametrize(
    "body,expected",
    [
        ("<Enter>\n\n```\n</Enter>\n```\n<Value>", ["<Enter>", "<Value>"]),
        ("    <Code></Code>\n\n<Value>", ["<Value>"]),
        ("text\n    <Value>\n", ["<Value>"]),
        (
            r"\<Escaped> `<Code>` ``<Another>`` <https://example.invalid> <a@b.invalid> <Value>",
            ["<Value>"],
        ),
        (
            "<!-- <Code> -->\n[<Value>](https://example.invalid) ![<Alt>](remote.png)",
            ["<Value>", "<Alt>"],
        ),
        ("é <Value>\r<Enter>\r\n<type>\n", ["<Value>", "<Enter>", "<type>"]),
        (
            '[<Value>](<relative> "title <Hidden></Hidden>") <Enter>',
            ["<Value>", "<Enter>"],
        ),
    ],
)
def test_independent_activity_scanner_has_exact_protected_and_label_boundaries(
    body, expected
):
    adapted, edits = literal_edits(body)
    assert [e["before"] for e in edits] == expected
    for e in edits:
        assert body[e["start"] : e["end"]] == e["before"]
        assert adapted[e["adapted_start"] : e["adapted_end"]] == "\\" + e["before"]


@pytest.mark.parametrize(
    "body",
    [
        "<Value>\n\n</Value>",
        "<script>",
        "<selectedcontent>",
        "<template>",
        "<Value x='y'>",
        "<?xml?>",
        "<!DOCTYPE html>",
        "<Value/>",
    ],
)
def test_independent_activity_scanner_fails_closed_on_unestablished_markup(body):
    with pytest.raises(AssertionError, match="active HTML"):
        literal_edits(body)


def test_raw_oracle_refuses_unsupported_brain_autolinks_adjacent_to_literals(tmp_path):
    from tests.application.test_graph_workflow import graph_archive
    from tests.support.combined_collection import compact

    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Live"},
        notes={1: (f"Use <Enter> <brain://{compact(2)}/ignored>".encode(), 4)},
    )
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert (
        result.outcome == "refused" and result.issues[0].code == "unsupported_feature"
    )
    with pytest.raises(AssertionError, match="source-local autolink"):
        literal_edits(f"Use <Enter> <brain://{compact(2)}/ignored>")


def test_unlinked_closing_bracket_does_not_hide_active_angle_prose():
    _, edits = literal_edits("not a link ](<Value>)")
    assert [e["before"] for e in edits] == ["<Value>"]


def test_raw_oracle_distinguishes_nested_list_fence_from_active_angle_prose(tmp_path):
    from tests.application.test_graph_workflow import graph_archive

    body = "- ```md\n  <Code></Code>\n  ```\n\n<Value>"
    source = graph_archive(
        tmp_path / "source.brz", {1: "Home"}, notes={1: (body.encode(), 4)}
    )
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean" and result.counts.text_adaptations == 1
    assert check_vault(source, vault)["text_adaptations"] == 1


def test_excluded_external_foreign_collection_cannot_pass_forged_complete_audit(
    tmp_path,
):
    import json
    from zipfile import ZipFile

    from tests.application.test_forgotten_workflow import rewrite
    from tests.application.test_graph_workflow import identity

    source = combined_archive(tmp_path / "source.brz")
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    record = load_json((vault / "migration-record.json").read_bytes())

    def malformed(parts):
        rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
        next(a for a in rows if a["Id"] == identity(6014))["BrainId"] = identity(999)
        parts["attachments.json"] = b"\n".join(json.dumps(a).encode() for a in rows)

    rewrite(source, malformed)
    refused = default_workflow().inspect(source)
    assert (
        refused.outcome == "refused"
        and not refused.issues[0].affected
        and not refused.issues[0].evidence
    )
    record["source_identity"]["source_sha256"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    rewrite_record(vault, record, result)
    with ZipFile(source) as archive:
        assert archive.testzip() is None
    with pytest.raises(AssertionError, match="ownership"):
        check_vault(source, vault)
