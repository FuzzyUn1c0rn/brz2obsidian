"""Public update journeys for format 9 and saved format-8 authority."""

import json
import shutil

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_facts import output_identity
from brz2obsidian.application.update_lifecycle import text_choice_action
from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.core import inspect_review_choices
from tests.application.test_format_transition_completion import StopAfterPublication
from tests.application.test_format_transition_native import user_git_state
from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_type_tag_updates import fresh_resume, use_incoming
from tests.application.test_update_lifecycle import case_path, git
from tests.reconciliation.test_resolution import action
from tests.support.recorded_format6 import NOTE, ORIGINAL
from tests.support.recorded_format7 import FIXTURE, historical_payload
from tests.support.recorded_format8 import format8_workflow

__all__ = ["case_path"]

LEAF = "Notes/Leaf.md"
LISTING = "Uncreated targets.md"
REPORT = "MIGRATION REPORT.md"
RECORD = "migration-record.json"
TITLES = {1: "Entry", 2: "Leaf", 3: "Jump A", 4: "Jump B"}
RELATIONSHIPS = ((1, 2, 1, 1, -1), (3, 4, 3, 1, -1))


def checkpoint(root, source, workflow):
    vault = root / "vault"
    converted = workflow.convert(source, vault)
    assert converted.receipt is not None and converted.receipt.verified, converted
    original = root / "original"
    shutil.copytree(vault, original)
    identity = output_identity(json.loads((original / RECORD).read_bytes()))
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    authored = b"Read [[Notes/Leaf.md|Leaf]].\r\n"
    (vault / "Manual.md").write_bytes(authored)
    git(vault, "add", "Manual.md")
    git(vault, "commit", "-qm", "Independent vault history")
    git(vault, "branch", "user-owned")
    operations = Operations(workflow=workflow)
    captured = operations.capture_checkpoint(
        vault,
        original,
        identity=identity,
        vault_id="navigation-test-vault",
        import_id="navigation-test-import",
        admission=operations.inspect_history(vault).admission,
    )
    assert captured.status == "captured", captured
    return vault, original, authored


def review_plan(result):
    assert result.status == "prepared_review" and result.preparation is not None, result
    return result.preparation


def test_tracked_format8_upgrade_cold_resume_retains_authored_link_and_listing(
    case_path,
):
    source = graph_archive(case_path / "original.brz", TITLES, RELATIONSHIPS)
    vault, original, authored = checkpoint(case_path, source, format8_workflow())
    user_before = user_git_state(vault)
    assert not (vault / LEAF).exists()
    listing = (original / LISTING).read_bytes() + b"\nMy retained annotation.\r\n"
    (vault / LISTING).write_bytes(listing)
    operations = Operations()
    assert operations.prepare_update(vault, source).code == "format_transition_required"
    offered = operations.prepare_format_transition(vault, source)
    prepared = review_plan(offered)
    facts = prepared.review.facts
    assert (
        facts.baseline_identity.output_format,
        facts.incoming_identity.output_format,
    ) == (8, 9)
    assert facts.format_operation.baseline_source_version == (
        facts.format_operation.target_source_version
    )
    assert LISTING in offered.summary
    leaf = next(c for c in prepared.review.proposal.changes if c.item_id == identity(2))
    assert leaf.original is None and leaf.current is None
    assert b"## Parents" in leaf.incoming.data
    ready = use_incoming(operations, prepared)
    saved = operations.save_update(ready)
    assert saved.code == "saved", saved
    assert not (vault / LEAF).exists()
    resumed = fresh_resume(vault, case_path / "transition-resumed.json")
    assert resumed.review.ready
    assert resumed.kind == "format_transition"
    result = operations.apply_update(resumed)
    assert result.status == "applied", result
    assert (vault / LEAF).read_bytes() == leaf.incoming.data
    assert (vault / "Manual.md").read_bytes() == authored
    assert (vault / LISTING).read_bytes() == listing
    assert b"[[Uncreated targets.md|" not in (vault / REPORT).read_bytes()
    generated = json.loads((vault / RECORD).read_bytes())
    assert generated["schema_version"] == 9
    assert LISTING not in {
        row["relative_path"] for row in generated["support_artifacts"]
    }
    assert user_git_state(vault) == user_before
    undo = operations.prepare_undo(vault)
    assert (undo.status, undo.code) == ("none", "latest_operation_is_maintenance")
    history = operations.inspect_history(vault).checkpoint.locator
    assert operations.prepare_format_transition(vault, source).code == (
        "format_transition_not_required"
    )
    repeated = review_plan(operations.prepare_update(vault, source))
    assert operations.apply_update(repeated).code == "already_current"
    assert operations.inspect_history(vault).checkpoint.locator == history


def test_saved_format8_source_update_reassembles_in_current_format9_process(case_path):
    initial = graph_archive(
        case_path / "original.brz",
        {1: "Entry"},
        notes={1: (b"Original body.\r\n", 4)},
    )
    incoming = graph_archive(
        case_path / "incoming.brz",
        {1: "Entry"},
        notes={1: (b"Incoming body.\r\n", 4)},
    )
    workflow = format8_workflow()
    vault, _, _ = checkpoint(case_path, initial, workflow)
    old_operations = Operations(workflow=workflow)
    prepared = review_plan(old_operations.prepare_update(vault, incoming))
    saved = old_operations.save_update(use_incoming(old_operations, prepared))
    assert saved.code == "saved", saved
    current = Operations()
    assert default_workflow().metadata_factory().renderer_version == "9"
    resumed = fresh_resume(vault, case_path / "old-source-update-resumed.json")
    assert resumed.kind == "source_update" and resumed.review.ready
    assert resumed.review.facts.baseline_identity.output_format == 8
    assert resumed.review.facts.incoming_identity.output_format == 8
    refreshed = review_plan(current.refresh_update(resumed, source=incoming))
    assert refreshed.review.facts.incoming_identity.output_format == 8
    assert current.apply_update(use_incoming(current, refreshed)).status == "applied"
    assert json.loads((vault / RECORD).read_bytes())["schema_version"] == 8


def test_format9_retirement_and_requalification_keep_local_deletion_after_cold_resume(
    case_path,
):
    titles = {1: "Entry", 2: "Leaf", 3: "Kept"}
    initial = graph_archive(
        case_path / "generated.brz",
        titles,
        ((1, 2, 1, 1, -1), (1, 3, 1, 1, -1)),
    )
    dormant = graph_archive(case_path / "dormant.brz", titles)
    qualifying = graph_archive(
        case_path / "requalified.brz", titles, ((1, 2, 3, 1, -1), (1, 3, 3, 1, -1))
    )
    vault, _, authored = checkpoint(case_path, initial, default_workflow())
    (vault / LEAF).unlink()
    kept_path = vault / "Notes/Kept.md"
    retained = kept_path.read_bytes() + b"\nAuthored during the first import.\r\n"
    kept_path.write_bytes(retained)
    # This test exercises a prior recorded deletion without an authored
    # reference to the deleted file. The upgrade test covers authored links.
    (vault / "Manual.md").write_bytes(
        authored.replace(b"[[Notes/Leaf.md|Leaf]]", b"it")
    )
    operations = Operations()
    retirement = operations.prepare_update(vault, dormant)
    prepared = review_plan(retirement)
    assert "still exist but no longer qualify" in retirement.summary
    assert prepared.review.facts.retired_note_ids == (identity(2), identity(3))
    result = operations.apply_update(use_incoming(operations, prepared))
    assert result.status == "applied", result
    assert not (vault / LEAF).exists()
    assert kept_path.read_bytes() == retained

    # A new process reconstructs the private reviews from the authenticated
    # recorded generation and reobserves the current working directory.
    moved = vault / "Moved/Kept.md"
    moved.parent.mkdir()
    kept_path.rename(moved)
    offered = review_plan(operations.prepare_update(vault, qualifying))
    saved = operations.save_update(offered)
    assert saved.code == "saved", saved
    resumed = fresh_resume(vault, case_path / "requalified-resumed.json")
    rows = {row.item_id: row for row in resumed.review.proposal.changes}
    deletion = rows[identity(2)]
    assert deletion.original is None and deletion.current is None
    assert deletion.disposition == "local_deleted" and not deletion.requires_decision
    retained_note = rows[identity(3)]
    assert retained_note.original is None
    assert retained_note.identity_review.selected_entry_id == "file:Moved/Kept.md"
    assert retained_note.current.data == retained
    assert b"## Related" in retained_note.incoming.data
    assert moved.read_bytes() == retained and not kept_path.exists()
    assert not (vault / LEAF).exists()
    kept = choose_text(
        operations,
        resumed,
        retained_note,
        retained_note.incoming.data + b"\nAuthored during the first import.\r\n",
    )
    home = next(c for c in kept.review.proposal.changes if c.item_id == identity(1))
    deleted_reference = b"- [[Notes/Leaf.md|Leaf]]\n"
    assert deleted_reference not in home.current.data
    assert home.incoming.data.count(deleted_reference) == 1
    # Keep the current absence of this link along with the note's deletion.
    edited = home.incoming.data.replace(deleted_reference, b"").replace(
        b"[[Notes/Kept.md|Kept]]", b"[[Moved/Kept.md|Kept]]"
    )
    ready = use_incoming(operations, choose_text(operations, kept, home, edited))
    assert operations.apply_update(ready).status == "applied"
    assert edited == (vault / home.path).read_bytes()
    assert b"Authored during the first import." in moved.read_bytes()
    assert not kept_path.exists() and not (vault / LEAF).exists()
    identical = review_plan(operations.prepare_update(vault, qualifying))
    assert identical.review.ready
    assert operations.apply_update(identical).code == "already_current"


def choose_text(operations, prepared, change, edited):
    (offer,) = [
        row
        for row in inspect_review_choices(prepared.review)
        if row.change_id == change.change_id and "edited" in row.enabled_choices
    ]
    result = operations.resolve_update(
        prepared,
        action(
            prepared.review,
            change,
            domain=offer.domain,
            choice="edited",
            decision_id=f"requalify:{change.item_id}",
        ),
        edited=edited,
    )
    assert result.code == "accepted", result
    return result.preparation


def test_recorded_format7_routes_to_current_and_reopens_saved_format8(case_path):
    payload, _ = historical_payload()
    original, vault = case_path / "recorded-original", case_path / "vault"
    for name, raw in payload.items():
        for directory in (original, vault):
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    source = FIXTURE / "source.brz"
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    current = Operations()
    captured = current.capture_checkpoint(
        vault,
        original,
        identity=output_identity(json.loads(payload[RECORD])),
        vault_id="navigation-legacy-vault",
        import_id="navigation-legacy-import",
        admission=current.inspect_history(vault).admission,
    )
    assert captured.status == "captured", captured
    direct = review_plan(current.prepare_format_transition(vault, source))
    assert direct.review.facts.baseline_identity.profile_version == "10"
    assert direct.review.facts.baseline_identity.output_format == 7
    assert direct.review.facts.incoming_identity.output_format == 9
    assert current.inspect_history(vault).checkpoint.locator == captured.locator

    historical = Operations(workflow=format8_workflow())
    legacy = review_plan(historical.prepare_format_transition(vault, source))
    saved = historical.save_update(legacy)
    assert saved.code == "saved", saved
    resumed = fresh_resume(vault, case_path / "old-transition-resumed.json")
    assert resumed.kind == "format_transition"
    assert resumed.review.facts.baseline_identity.output_format == 7
    assert resumed.review.facts.incoming_identity.output_format == 8
    (row,) = [r for r in resumed.review.proposal.changes if r.path == NOTE]
    assert row.original.data == row.current.data == ORIGINAL
    assert resumed.review.facts.format_operation.baseline_source_version == (
        resumed.review.facts.format_operation.target_source_version
    )


def test_interrupted_format9_upgrade_finishes_with_authored_reserved_links(case_path):
    source = graph_archive(case_path / "original.brz", TITLES, RELATIONSHIPS)
    vault, _, authored = checkpoint(case_path, source, format8_workflow())
    warm = Operations(vault_executor=StopAfterPublication())
    prepared = use_incoming(
        warm, review_plan(warm.prepare_format_transition(vault, source))
    )
    stopped = warm.apply_update(prepared)
    assert (
        stopped.status == "recovery_required" and warm.vault_executor.moved is not None
    )
    assert stopped.application.published_files == 1

    cold = Operations()
    assert cold.inspect_update_status(vault).recovery_required
    recovery = cold.prepare_recovery(vault, direction="finish")
    assert recovery.status == "offered"
    for index in range(len(recovery.review.proposal.changes)):
        plan = recovery.review
        if plan.ready:
            break
        assert plan.requirements, plan.blockers
        requirement = plan.requirements[0]
        change = next(
            row
            for row in plan.proposal.changes
            if row.change_id == requirement.change_id
        )
        decision = action(
            plan,
            change,
            domain=requirement.domain,
            choice="incoming",
            decision_id=f"finish-9:{index}",
        )
        recovery = cold.resolve_recovery(
            vault, recovery, text_choice_action(plan, decision)
        )
        assert recovery.status == "offered", recovery
    assert recovery.review.ready, (
        recovery.review.requirements,
        recovery.review.blockers,
    )
    result = cold.execute_recovery(vault, recovery)
    assert result.status == "applied" and not result.recovery_required, result
    assert b"## Parents" in (vault / LEAF).read_bytes()
    assert (vault / "Manual.md").read_bytes() == authored
    assert json.loads((vault / RECORD).read_bytes())["schema_version"] == 9


@pytest.mark.parametrize("save_first", (False, True), ids=("direct", "saved-first"))
def test_unavailable_format9_intent_ref_keeps_the_edited_review_resumable(
    case_path, monkeypatch, save_first
):
    from brz2obsidian.publication.vault_history import _Git

    source = graph_archive(
        case_path / "original.brz", {1: "Entry", 2: "Leaf"}, (RELATIONSHIPS[0],)
    )
    vault, original, authored = checkpoint(case_path, source, format8_workflow())
    home = next(vault.glob("Home*.md"))
    home_before = home.read_bytes()
    occupant_path = vault / LEAF
    occupant_path.parent.mkdir(exist_ok=True)
    occupant = b"# Unrelated occupant\r\n"
    occupant_path.write_bytes(occupant)
    moved = vault / "Moved/Leaf.md"
    moved.parent.mkdir()
    local = (
        b'---\nsource_collection_id: "11111111-1111-4111-8111-111111111111"\n'
        b'source_item_id: "00000000-0000-0000-0000-000000000002"\n'
        b"---\n\n# Leaf\n\nLocal prose.\r\n"
    )
    moved.write_bytes(local)
    operations = Operations()
    if save_first:
        # Record the current authored inventory at the old source generation
        # so the subsequent LOCAL review memo can retain this authority.
        history = operations.inspect_history(vault)
        association = history.checkpoint.locator.association
        baseline = operations.capture_checkpoint(
            vault,
            original,
            identity=history.checkpoint.manifest.identity,
            vault_id=association.vault_id,
            import_id=association.import_id,
            admission=history.admission,
        )
        assert baseline.status == "captured", baseline
    prepared = review_plan(operations.prepare_format_transition(vault, source))
    leaf = next(c for c in prepared.review.proposal.changes if c.item_id == identity(2))
    leaf_result = leaf.incoming.data + b"\nLocal prose.\r\n"
    with_leaf = choose_text(operations, prepared, leaf, leaf_result)
    referrer = next(
        c for c in with_leaf.review.proposal.changes if c.item_id == identity(1)
    )
    edited = home_before.replace(b"[[Notes/Leaf.md|Leaf]]", b"[[Moved/Leaf.md|Leaf]]")
    ready = use_incoming(
        operations, choose_text(operations, with_leaf, referrer, edited)
    )
    assert ready.review.ready
    approvals = tuple(
        a.decision_id for a in ready.review.approvals if a.result is not None
    )
    if save_first:
        saved = operations.save_update(ready)
        assert saved.code == "saved", saved
        assert saved.checkpoint != baseline.locator
        ready_from_memo = review_plan(Operations().resume_update(vault))
        assert ready_from_memo.review.ready
        assert ready_from_memo.locator == saved.checkpoint
        assert ready_from_memo.review.preflight == ready.review.preflight
        ready = ready_from_memo
    call = _Git.call

    def refuse_operation_ref(self, *args, **kwargs):
        if args[0] == "update-ref" and "/operations/" in args[1]:
            raise OSError("Deterministic failure before the intent ref write")
        return call(self, *args, **kwargs)

    with monkeypatch.context() as fault:
        fault.setattr(_Git, "call", refuse_operation_ref)
        failed = operations.apply_update(ready)
    assert (failed.status, failed.code, failed.publication) == (
        "failed",
        "intent_ref_unavailable",
        "not_published",
    ), failed
    assert failed.next_actions == ("resume_update",)
    assert failed.application.history == "prepared"
    assert (
        not failed.application.recovery_required
        and not failed.application.intent_commit
    )
    assert failed.application.published_files == 0
    assert Operations().inspect_update_status(vault).code == "operation_absent"
    assert home.read_bytes() == home_before and moved.read_bytes() == local
    assert occupant_path.read_bytes() == occupant
    assert (vault / "Manual.md").read_bytes() == authored

    restarted = Operations()
    resumed = review_plan(restarted.resume_update(vault))
    assert resumed.review.ready
    assert resumed.review.facts.baseline_identity.output_format == 8
    assert resumed.review.facts.incoming_identity.output_format == 9
    assert {approval.result.data for approval in resumed.review.approvals} >= {
        edited,
        leaf_result,
    }

    assert (
        tuple(a.decision_id for a in resumed.review.approvals if a.result is not None)
        == approvals
    )
    applied = restarted.apply_update(resumed)
    assert applied.status == "applied", applied
    assert home.read_bytes() == edited
    assert moved.read_bytes() == leaf_result
    assert occupant_path.read_bytes() == occupant
    assert (vault / "Manual.md").read_bytes() == authored
    assert json.loads((vault / RECORD).read_bytes())["schema_version"] == 9
