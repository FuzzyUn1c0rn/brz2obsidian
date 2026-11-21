"""Qualified namespaces through public source and publication boundaries."""

import json

import pytest

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_forgotten_workflow import forget, rewrite
from tests.application.test_graph_workflow import graph_archive, identity

BRAIN_TOKEN = "EREREREREUGBEREREREREQ"
TARGET_TOKEN = "AAAAAAAAAAAAAAAAAAAAAg"
QUALIFIED = f"brain://api.thebrain.com/{BRAIN_TOKEN}/{TARGET_TOKEN}"


def test_current_brz_qualified_reference_inspects_and_publishes_exact_evidence(
    tmp_path,
):
    prefix = "> - Before café\r\n>   - Nested\r\n>\t\t"
    phrase = f"[Authored **label**]({QUALIFIED}/Other-name)"
    authored = f"{prefix}{phrase} after `*kept*`.\r\n"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Target"},
        notes={1: (authored.encode(), 4)},
    )
    workflow = default_workflow()
    inspection = workflow.inspect(source)
    assert inspection.outcome == "clean", inspection.issues
    assert inspection.counts.source_references == 1
    vault = tmp_path / "vault"
    result = workflow.convert(source, vault)
    assert result.outcome == "clean", result.issues
    assert result.receipt.verified
    body = (vault / "Home — Home.md").read_bytes()
    assert (
        "> - Before café\r\n>   - Nested\r\n>\t\t"
        "[[Notes/Target.md|Authored label]] after `*kept*`.\r\n"
    ).encode() in body
    assert next(vault.rglob("*.original")).read_bytes() == authored.encode()
    record = json.loads((vault / "migration-record.json").read_bytes())
    document = next(d for row in record["item_targets"] for d in row["documents"])
    reference = document["references"][0]
    assert reference["target"] == identity(2)
    assert reference["source_target"] == QUALIFIED + "/Other-name"
    assert reference["expected_original"] == phrase
    assert (reference["start"], reference["end"]) == (34, 34 + len(phrase))


def test_foreign_included_identity_collision_publishes_exact_external_span(tmp_path):
    foreign = f"brain://api.thebrain.com/MzMzMzMzM0ODMzMzMzMzMw/{TARGET_TOKEN}/caf%C3%A9%2Fname"
    authored = f"α\r\n[Foreign **label**]({foreign})\r\n"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Target"},
        notes={1: (authored.encode(), 4)},
    )
    workflow = default_workflow()
    inspection = workflow.inspect(source)
    assert inspection.outcome == "clean", inspection.issues
    assert inspection.counts.source_references == 0
    vault = tmp_path / "vault"
    result = workflow.convert(source, vault)
    assert result.outcome == "clean", result.issues
    assert authored.encode() in (vault / "Home — Home.md").read_bytes()
    assert next(vault.rglob("*.original")).read_bytes() == authored.encode()
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert record["relationships"] == []
    assert all(
        not d["references"] for row in record["item_targets"] for d in row["documents"]
    )


@pytest.mark.parametrize("location", ["target", "label", "suffix", "literal"])
def test_foreign_omitted_token_refuses_privately_without_publication(
    tmp_path, location
):
    foreign = f"brain://api.thebrain.com/MzMzMzMzM0ODMzMzMzMzMw/{BRAIN_TOKEN}"
    body = {
        "target": f"[Foreign]({foreign.replace(BRAIN_TOKEN, TARGET_TOKEN)})",
        "label": f"[{TARGET_TOKEN}]({foreign})",
        "suffix": f"[Foreign]({foreign}/{TARGET_TOKEN})",
        "literal": f"[Foreign]({foreign}) `brain://{TARGET_TOKEN}/private`",
    }[location]
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private subject"},
        notes={1: (body.encode(), 4)},
    )
    rewrite(source, lambda parts: forget(parts, 2))
    original = source.read_bytes()
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "refused", result.issues
    assert result.issues[0].code == "invalid_reference"
    assert not vault.exists()
    for private in (TARGET_TOKEN, identity(2), "Private subject", foreign):
        assert private not in result.model_dump_json()
    assert source.read_bytes() == original


def test_current_qualified_excluded_reference_removes_phrase_and_unsafe_backup(
    tmp_path,
):
    body = f"α before\r\n[Private **label**]({QUALIFIED}/private-name) after\rTail"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private subject"},
        notes={1: (body.encode(), 4)},
    )
    rewrite(source, lambda parts: forget(parts, 2))
    workflow = default_workflow()
    inspection = workflow.inspect(source)
    assert inspection.outcome == "clean", inspection.issues
    assert inspection.counts.source_references == 0
    vault = tmp_path / "vault"
    result = workflow.convert(source, vault)
    assert result.outcome == "clean", result.issues
    assert (
        "α before\r\n after\rTail".encode() in (vault / "Home — Home.md").read_bytes()
    )
    assert not list(vault.rglob("*.original"))
    output = b"\n".join(
        path.read_bytes() for path in vault.rglob("*") if path.is_file()
    )
    for private in (TARGET_TOKEN, identity(2), "private-name", "Private **label**"):
        assert private.encode() not in output
