"""Current8 Restore keeps a real new Both image while reversing another note."""

import json
from pathlib import Path

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_choices import (
    requirement_digest,
    review_plan_attachment_reference_page,
    review_plan_choice_action,
)
from brz2obsidian.application.update_facts import assemble_facts
from brz2obsidian.application.update_lifecycle import text_choice_action
from brz2obsidian.core import (
    inspect_review_choices,
    prepare_review,
    resolve_review,
    select_review_effects,
)
from brz2obsidian.publication.vault_replace import move_file
from tests.application.test_update_lifecycle_contracts import preparation
from tests.application.test_vault_checkpoints import fixture_case, git
from tests.reconciliation.test_resolution import action
from tests.reconciliation.test_type_tag_dependencies import (
    BLUE,
    RED,
    graph_payload,
    note,
)


def test_restore_keeps_new_both_image_and_owner_while_reversing_category_provider():
    baseline = {
        name: raw.replace(b"[[A.svg]]", b"[[Attachments/A.svg]]")
        for name, raw in graph_payload().items()
    }
    record = json.loads(baseline["migration-record.json"])
    record["item_targets"].append(
        {
            "original_identity": "category:E",
            "original_title": "E",
            "relative_path": "Categories/E.md",
            "created": True,
            "creation_reasons": ["definition"],
        }
    )
    baseline["migration-record.json"] = json.dumps(record).encode()
    baseline["Categories/E.md"] = note("category:E")
    baseline["Categories/B.md"] = note("category:B")
    incoming = dict(baseline)
    incoming["Attachments/A.svg"] = BLUE
    incoming["Categories/B.md"] = note(
        "category:B", provider="[[Categories/A.md]]", body="Incoming B."
    )
    incoming["Categories/C.md"] = note(
        "category:C", provider="[[Categories/E.md]]", body="Incoming C."
    )
    record["source_identity"].update(source_sha256="e" * 64, snapshot_digest="f" * 64)
    incoming["migration-record.json"] = json.dumps(record).encode()
    facts = assemble_facts(
        baseline, incoming, baseline, proposal_id="both-image-recovery", generation=1
    )
    operations = Operations()
    prepared = preparation(facts)
    for item in ("support:migration-record.json", "category:B", "category:C"):
        change = next(c for c in prepared.review.proposal.changes if c.item_id == item)
        result = operations.resolve_update(
            prepared,
            action(prepared.review, change, choice="incoming", decision_id=item),
        )
        assert result.code == "accepted", result.code
        prepared = result.preparation
    offered = next(
        r for r in inspect_review_choices(prepared.review) if r.domain == "attachment"
    )
    refs, total, following = review_plan_attachment_reference_page(
        prepared.review, offered.requirement_id
    )
    assert total == 1 and following is None
    selected = operations.resolve_update_choice(
        prepared,
        requirement_id=offered.requirement_id,
        choice="both",
        assumptions_digest=requirement_digest(offered),
        references=tuple(
            {"reference_id": row.reference_id, "choice": "use_secondary"}
            for row in refs
        ),
    )
    assert selected.code == "accepted", (
        selected.code,
        selected.preparation.review.blockers,
    )
    # The selected image changes A's icon reference. Explicitly bind that
    # selected owner and B's Incoming provider to their actual chosen versions;
    # C's Incoming provider remains independent until the later Restore choice.
    prepared = selected.preparation
    allocation = next(
        a.attachment_candidate
        for a in prepared.review.approvals
        if a.attachment_candidate is not None
    )
    new_path = next(
        row.path for row in allocation.outputs if row.path != "Attachments/A.svg"
    )
    expected_owner = baseline["Categories/A.md"].replace(
        b"[[Attachments/A.svg]]",
        f"[[{new_path}|Attachments/A.svg]]".encode(),
    )
    for item, raw in (
        ("category:A", expected_owner),
        ("category:B", incoming["Categories/B.md"]),
    ):
        change = next(c for c in prepared.review.proposal.changes if c.item_id == item)
        result = operations.resolve_update(
            prepared,
            action(
                prepared.review, change, choice="edited", decision_id="explicit:" + item
            ),
            edited=raw,
        )
        assert result.code == "accepted", result.code
        prepared = result.preparation
    plan = prepared.review
    assert plan.ready, plan.blockers
    effects = select_review_effects(plan)
    assert effects.status == "selected"
    files = {row.path: row.content.data for row in effects.files}
    assert new_path.endswith(".svg") and files[new_path] == BLUE
    assert files["Categories/A.md"] == expected_owner
    assert files["Attachments/A.svg"] == RED

    vault, source = fixture_case()
    for directory in (vault, source):
        for name, raw in baseline.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    git(vault, "add", ".")
    git(vault, "commit", "-qm", "Known current8 image graph")
    captured = operations.capture_checkpoint(
        vault,
        source,
        vault_id="both-image-vault",
        import_id="both-image-import",
        identity=facts.baseline_identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert captured.status == "captured", captured.code
    for name, raw in incoming.items():
        (source / name).write_bytes(raw)
    # Rebuild this real Native operation's preflight; the earlier pure public
    # choices established the exact user-selected resource and owner bytes.
    current_preflight = operations.inspect_history(vault).admission.preflight
    real = prepare_review(facts, preflight=current_preflight)
    for event in plan.actions:
        # Actions retain their independently checked choices/candidates and are
        # admitted against this fresh canonical review, not copied as grants.
        replayed = resolve_review(real, event)
        assert replayed.status == "accepted", replayed.code
        real = replayed.plan
    assert real.ready, real.blockers

    class StopAfterCategoryPublication:
        def move(self, stage, target, *, replace):
            move_file(stage, target, replace=replace)
            if Path(target) == vault / "Categories/C.md":
                raise OSError("Controlled stop after real category publication")

        def remove(self, target, destination):
            raise AssertionError("Both creates outputs without removals")

    stopped = Operations(
        vault_executor=StopAfterCategoryPublication()
    ).apply_reviewed_update(
        vault,
        source,
        review=real,
        source_binding=operations.observe_reviewed_source(source, real),
        vault_id="both-image-vault",
        import_id="both-image-import",
    )
    assert stopped.recovery_required and stopped.status in (
        "incomplete",
        "content_complete",
    ), stopped.code
    assert (vault / new_path).read_bytes() == BLUE
    assert (vault / "Attachments/A.svg").read_bytes() == RED
    assert (vault / "Categories/A.md").read_bytes() == expected_owner
    assert (vault / "Categories/C.md").read_bytes() == incoming["Categories/C.md"]
    before = {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    }
    restored = operations.prepare_recovery(vault, direction="restore")
    assert restored.status == "offered" and restored.review is not None, restored.code
    owned = [
        row
        for subject in restored.review.producer_facts.subjects
        if subject.operation_reversal is not None
        for row in subject.operation_reversal.outputs
        if row.path == new_path
    ]
    assert (
        len(owned) == 1
        and owned[0].produced.data == owned[0].current.content.data == BLUE
    )
    assert owned[0].target is None
    context = restored.review.producer_facts.link_context
    image_target = next(
        target
        for target in context.current_targets
        if target.canonical_path == new_path
    )
    image_state = next(
        state
        for state in context.current_target_facts
        if state.target_id == image_target.target_id
    )
    assert image_state.content.data == BLUE
    assert image_state.file_roles.path == new_path
    assert image_state.file_roles.image_path and not image_state.file_roles.category
    # Keep the new valid image and its owner. Only C returns to B->A; that
    # selected chain must qualify the actually owned new image, not assume7.
    while restored.review.requirements:
        requirement = next(
            (
                r
                for r in restored.review.requirements
                if next(
                    c.item_id
                    for c in restored.review.proposal.changes
                    if c.change_id == r.change_id
                )
                != "category:C"
            ),
            restored.review.requirements[0],
        )
        change = next(
            c
            for c in restored.review.proposal.changes
            if c.change_id == requirement.change_id
        )
        choice = "incoming" if change.item_id == "category:C" else "current"
        offer = next(
            r
            for r in inspect_review_choices(restored.review)
            if r.requirement_id == requirement.requirement_id
        )
        assert choice in offer.enabled_choices, (change.item_id, offer.enabled_choices)
        request = review_plan_choice_action(
            restored.review,
            requirement_id=offer.requirement_id,
            choice=choice,
            assumptions_digest=requirement_digest(offer),
        )
        request = text_choice_action(restored.review, request)
        if change.item_id == "category:C":
            restored = operations.resolve_recovery(vault, restored, request)
            assert restored.status == "offered", restored.code
        else:
            transition = resolve_review(restored.review, request)
            assert transition.status == "accepted", transition.code
            restored = restored.model_copy(update={"review": transition.plan})
    assert restored.review.ready, restored.review.blockers
    selected = select_review_effects(restored.review)
    assert selected.status == "selected"
    selected_files = {row.path: row.content.data for row in selected.files}
    assert selected_files["Categories/C.md"] == baseline["Categories/C.md"]
    assert selected_files.get("Categories/A.md", expected_owner) == expected_owner
    assert (
        selected_files.get(new_path, BLUE) == BLUE
        and new_path not in selected.remove_paths
    )
    assert {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    } == before
    user_head = git(vault, "rev-parse", "HEAD")
    user_index = (vault / ".git/index").read_bytes()
    user_refs = tuple(
        row
        for row in git(
            vault, "for-each-ref", "--format=%(refname) %(objectname)"
        ).splitlines()
        if not row.startswith(b"refs/brz2obsidian/")
    )
    completed = operations.execute_recovery(vault, restored)
    assert completed.status == "restored", completed.code
    assert completed.publication == "complete" and completed.history == "terminal"
    assert completed.result_commit and completed.receipt_commit
    assert (vault / "Categories/C.md").read_bytes() == baseline["Categories/C.md"]
    assert (vault / "Categories/A.md").read_bytes() == expected_owner
    assert (vault / new_path).read_bytes() == BLUE
    assert (vault / "Attachments/A.svg").read_bytes() == RED
    assert git(vault, "rev-parse", "HEAD") == user_head
    assert (vault / ".git/index").read_bytes() == user_index
    assert (
        tuple(
            row
            for row in git(
                vault, "for-each-ref", "--format=%(refname) %(objectname)"
            ).splitlines()
            if not row.startswith(b"refs/brz2obsidian/")
        )
        == user_refs
    )
