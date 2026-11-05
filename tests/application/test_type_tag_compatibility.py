"""Actual old output remains distinct from current generation and originals."""

import hashlib
import shutil

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.contracts import ExactContent, OutputIdentity
from brz2obsidian.obsidian import interpret_attachment_mapping
from tests.application.test_format_transition_completion import finish_transition
from tests.application.test_format_transition_native import user_git_state
from tests.application.test_type_tag_updates import (
    fresh_resume,
    measured,
    update_root,
    use_incoming,
)
from tests.application.test_update_lifecycle import git
from tests.reconciliation.test_resolution import action
from tests.support.recorded_format6 import changed_source
from tests.support.recorded_format6 import historical_payload as format6_payload
from tests.support.recorded_format7 import FIXTURE, NOTE, ORIGINAL, historical_payload
from tests.support.type_tag_sources import BRAIN, ICON, PNG, brz_source

__all__ = ["update_root"]


def seed_format7(root, *, category_edit=False):
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
    current_path = NOTE
    if category_edit:
        # This is an authored destination role on the genuine ordinary source
        # item, rather than fabricated historical source-definition output.
        current = current.replace(b"tags: []", b"tags: [categories]").replace(
            b"---\n\n#", b"custom: [one, two]\n---\n\n#"
        )
        current_path = "Categories/Local category.md"
        (vault / NOTE).unlink()
        (vault / current_path).parent.mkdir(parents=True, exist_ok=True)
    (vault / current_path).write_bytes(current)
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
    operations, vault, source, current = seed_format7(update_root, category_edit=True)
    configuration = b'{"user":"retain legacy7 configuration"}\r\n'
    (vault / ".obsidian/app.json").write_bytes(configuration)
    support_path = "Templates/New note.md"
    support = (vault / support_path).read_bytes() + b"\nLocal template writing.\n"
    (vault / support_path).write_bytes(support)
    user_before = user_git_state(vault)
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
    assert note.baseline.content.data == ORIGINAL
    assert note.current.content is not None
    assert note.current.content.data == current
    assert note.current.path == "Categories/Local category.md"
    assert note.item_id == "5f71e626-527e-47b4-abaa-e53d124619f8"
    context = prepared.review.producer_facts.link_context
    current_target = next(
        target
        for target in context.current_targets
        if target.canonical_path == "Categories/Local category.md"
    )
    assert current_target.kind == "note"
    assert current_target.identity.item_id == note.item_id
    assert current_target.identity.collection_id == (
        "7b170eec-a7e4-49f6-a0b4-bd553528a201"
    )
    current_state = next(
        state
        for state in context.current_target_facts
        if state.target_id == current_target.target_id
    )
    assert current_state.content.data == current
    assert current_state.file_roles.category
    assert current_state.file_roles.path == "Categories/Local category.md"
    assert current_state.structure.output_format == 7
    assert current_state.structure.status == "unsupported"
    assert all(
        state.file_roles is not None
        for state in context.current_target_facts
        if state.content is not None
    )
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
    assert (vault / "Categories/Local category.md").read_bytes() == current
    prepared = chosen.preparation
    template = next(
        change
        for change in prepared.review.proposal.changes
        if change.item_id == "support:" + support_path
    )
    preserved = operations.resolve_update(
        prepared,
        action(
            prepared.review,
            template,
            domain="format",
            choice="current",
            decision_id="retain-local-template",
        ),
    )
    assert preserved.code == "accepted", preserved.code
    prepared = measured(
        update_root,
        "format7-resolve",
        finish_transition,
        operations,
        preserved.preparation,
        update_root,
        resolved_only=True,
    )
    # Explicitly resubmit these exact texts against the now-selected target
    # versions. Current Home and template bytes retain their authored contents;
    # stock guide and report references name their explicitly selected versions.
    for index, item in enumerate(
        (note.item_id, "support:MIGRATION REPORT.md", "support:Vault guide.md")
    ):
        plan = prepared.review
        comparison = next(c for c in plan.proposal.changes if c.item_id == item)
        approved = next(
            a for a in plan.approvals if a.change_id == comparison.change_id
        )
        exact = approved.result.data
        requalified = operations.resolve_update(
            prepared,
            action(
                plan,
                comparison,
                domain="format",
                choice="edited",
                decision_id=f"explicit-selected-text-{index}",
            ),
            edited=exact,
        )
        assert requalified.code == "accepted", requalified.code
        assert (
            next(
                a.result.data
                for a in requalified.preparation.review.approvals
                if a.change_id == comparison.change_id
            )
            == exact
        )
        prepared = requalified.preparation
    assert prepared.review.ready
    decisions = prepared.review.approvals
    saved = measured(update_root, "format7-save", operations.save_update, prepared)
    assert saved.code == "saved", saved.code
    resumed = measured(
        update_root,
        "format7-fresh-resume",
        fresh_resume,
        vault,
        update_root / "format7-resumed.json",
    )
    assert resumed.review.approvals == decisions
    assert resumed.review.ready and resumed.kind == "format_transition"
    applied = measured(update_root, "format7-apply", operations.apply_update, resumed)
    assert applied.status == "applied" and applied.kind == "format_transition", (
        applied.code
    )
    assert applied.application.history == "terminal"
    assert (vault / "Categories/Local category.md").read_bytes() == current
    assert (vault / support_path).read_bytes() == support
    assert (vault / ".obsidian/app.json").read_bytes() == configuration
    assert user_git_state(vault) == user_before
    checkpoint = operations.read_checkpoint(vault)
    assert (
        checkpoint.status == "valid" and checkpoint.manifest.identity.output_format == 8
    )
    assert checkpoint.review.saved.plan.facts.baseline_identity.output_format == 7
    assert operations.prepare_undo(vault).code == "latest_operation_is_maintenance"
    archive_b = changed_source(update_root / "separate-source-b.brz")
    updated = measured(
        update_root,
        "after7-source-b-prepare",
        operations.prepare_update,
        vault,
        archive_b,
    )
    assert updated.status == "prepared_review" and updated.kind == "source_update", (
        updated.code
    )
    assert updated.preparation.review.facts.baseline_identity.output_format == 8
    assert updated.preparation.review.facts.incoming_identity.output_format == 8
    assert (
        updated.preparation.review.facts.format_operation.baseline_source_version
        != updated.preparation.review.facts.format_operation.target_source_version
    )
    plan = updated.preparation.review
    change = next(c for c in plan.proposal.changes if c.item_id == note.item_id)
    expected = current.replace(
        b"Independent legacy source body.", b"Separate source B body."
    )
    selected = operations.resolve_update(
        updated.preparation,
        action(plan, change, choice="edited", decision_id="source-b-local-prose"),
        edited=expected,
    )
    assert selected.code == "accepted", selected.code
    ready = measured(
        update_root,
        "after7-source-b-resolve",
        use_incoming,
        operations,
        selected.preparation,
    )
    published = measured(
        update_root, "after7-source-b-apply", operations.apply_update, ready
    )
    assert published.status == "applied" and published.kind == "source_update", (
        published.code
    )
    assert published.application.history == "terminal"
    assert (vault / "Categories/Local category.md").read_bytes() == expected
    assert (vault / support_path).read_bytes() == support
    assert (vault / ".obsidian/app.json").read_bytes() == configuration
    assert user_git_state(vault) == user_before


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
