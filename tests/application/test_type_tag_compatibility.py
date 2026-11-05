"""Actual old output remains distinct from current generation and originals."""

import hashlib
import shutil

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.contracts import ExactContent, OutputIdentity
from brz2obsidian.obsidian import interpret_attachment_mapping
from tests.application.test_type_tag_updates import update_root
from tests.application.test_update_lifecycle import git
from tests.reconciliation.test_resolution import action
from tests.support.recorded_format6 import historical_payload as format6_payload
from tests.support.recorded_format7 import FIXTURE, NOTE, ORIGINAL, historical_payload
from tests.support.type_tag_sources import BRAIN, ICON, PNG, brz_source

__all__ = ["update_root"]


def seed_format7(root):
    payload, _ = historical_payload()
    original, vault = root / "original7", root / "vault"
    for relative, raw in payload.items():
        for folder in (original, vault):
            path = folder / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    source = root / "unchanged.brz"
    shutil.copyfile(FIXTURE / "source.brz", source)
    current = ORIGINAL + b"\nIndependent old-vault local writing.\n"
    (vault / NOTE).write_bytes(current)
    (vault / "Manual.md").write_bytes(b"Independent user history.\n")
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    git(vault, "add", "Manual.md")
    git(vault, "commit", "-qm", "Retained independent user history")
    operations = Operations()
    identity = OutputIdentity(
        collection_id="7b170eec-a7e4-49f6-a0b4-bd553528a201",
        module_id="thebrain-brz",
        module_version="10",
        profile_id="thebrain-format5-reviewed",
        profile_version="10",
        output_format=7,
        settings_digest=hashlib.sha256(b"{}").hexdigest(),
    )
    captured = operations.capture_checkpoint(
        vault,
        original,
        vault_id="recorded7-vault",
        import_id="recorded7-import",
        identity=identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert captured.status == "captured", captured
    return operations, vault, source, current


def test_actual_format7_requires_source_stable_transition_and_accepts_target8_choice(
    update_root,
):
    operations, vault, source, current = seed_format7(update_root)
    ordinary = operations.prepare_update(vault, source)
    assert (ordinary.code, ordinary.next_actions) == (
        "format_transition_required",
        ("review_format_transition",),
    )
    offered = operations.prepare_format_transition(vault, source)
    assert offered.status == "prepared_review", offered
    prepared = offered.preparation
    assert offered.kind == "format_transition" and not offered.ready
    facts = prepared.review.facts
    assert (
        facts.baseline_identity.profile_version,
        facts.baseline_identity.output_format,
    ) == ("10", 7)
    assert (
        facts.incoming_identity.profile_version,
        facts.incoming_identity.output_format,
    ) == ("11", 8)
    assert (
        facts.format_operation.baseline_source_version
        == facts.format_operation.target_source_version
    )
    note = next(
        s for s in facts.subjects if s.item_id == "5f71e626-527e-47b4-abaa-e53d124619f8"
    )
    assert (
        note.baseline.content.data == ORIGINAL and note.current.content.data == current
    )
    context = prepared.review.producer_facts.link_context
    assert {
        state.structure.output_format
        for state in context.current_target_facts
        if state.structure
    } == {7}
    assert {
        state.structure.output_format
        for state in context.incoming_target_facts
        if state.structure
    } == {8}
    guide = next(
        c
        for c in prepared.review.proposal.changes
        if c.item_id == "support:Vault guide.md"
    )
    assert guide.format_review.target_eligible
    chosen = operations.resolve_update(
        prepared,
        action(
            prepared.review,
            guide,
            domain="format",
            choice="incoming",
            decision_id="explicit-target8-guide",
        ),
    )
    assert chosen.code == "accepted", chosen
    approval = next(
        a for a in chosen.preparation.review.approvals if a.change_id == guide.change_id
    )
    assert approval.result.data == guide.incoming.data
    assert (vault / NOTE).read_bytes() == current


@pytest.mark.parametrize("version,profile", [(6, "9"), (7, "10"), (8, "11")])
def test_attachment_mapping_keeps_qualified7_and_current8_distinct_from_legacy6(
    tmp_path, version, profile
):
    if version == 8:
        vault = tmp_path / "fresh8"
        result = default_workflow().convert(brz_source(tmp_path / "source.brz"), vault)
        assert result.outcome == "clean", result.issues
        raw = (vault / "migration-record.json").read_bytes()
        collection = BRAIN
    else:
        payload, _ = (historical_payload if version == 7 else format6_payload)()
        raw = payload["migration-record.json"]
        collection = "7b170eec-a7e4-49f6-a0b4-bd553528a201"
    identity = OutputIdentity(
        collection_id=collection,
        module_id="thebrain-brz",
        module_version=profile,
        profile_id="thebrain-format5-reviewed",
        profile_version=profile,
        output_format=version,
        settings_digest=hashlib.sha256(b"{}").hexdigest(),
    )
    if version == 6:
        with pytest.raises(ValueError, match="unqualified"):
            interpret_attachment_mapping(ExactContent(data=raw), identity=identity)
        return
    source, targets = interpret_attachment_mapping(
        ExactContent(data=raw), identity=identity
    )
    assert source.module_version == profile
    assert len(targets) == 1
    if version == 8:
        assert targets[0].asset_id == ICON
        assert (
            targets[0].relative_path
            == "Attachments/0000000000000000000000000000000a/Icon.png"
        )
        assert (vault / targets[0].relative_path).read_bytes() == PNG
    else:
        assert targets[0].relative_path == "Attachments/5f71e626/Notes.md.original"
