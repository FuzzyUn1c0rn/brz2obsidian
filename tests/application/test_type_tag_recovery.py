"""Actual stopped publication requalifies the selected native provider graph."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_facts import link_state
from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
from brz2obsidian.obsidian import inspect_text_candidate
from tests.application.test_recovery_link_context import inventory
from tests.application.test_vault_checkpoints import fixture_case, git
from tests.reconciliation.test_resolution import action
from tests.reconciliation.test_type_tag_dependencies import (
    BLUE,
    facts_for,
    graph_payload,
    note,
    selected_candidate,
)


def stopped_provider_update():
    baseline = graph_payload()
    baseline["Categories/C.md"] = note("category:C")
    incoming = dict(baseline)
    incoming["Categories/C.md"] = note(
        "category:C", provider="[[Categories/A.md]]", body="Incoming C."
    )
    vault, source = fixture_case()
    for folder in (vault, source):
        for name, raw in baseline.items():
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    git(vault, "add", ".")
    git(vault, "commit", "-qm", "Literal current provider graph")
    facts = facts_for(baseline, incoming, baseline)
    operations = Operations()
    captured = operations.capture_checkpoint(
        vault,
        source,
        vault_id="type-provider-recovery",
        import_id="type-provider-import",
        identity=facts.incoming_identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert captured.status == "captured", captured.code
    for name, raw in incoming.items():
        (source / name).write_bytes(raw)
    reviewed = prepare_review(
        facts, preflight=operations.inspect_history(vault).admission.preflight
    )
    change = next(
        change for change in reviewed.proposal.changes if change.item_id == "category:C"
    )
    chosen = resolve_review(
        reviewed,
        action(
            reviewed,
            change,
            choice="incoming",
            candidate=selected_candidate(facts, facts, "category:C"),
            decision_id="explicit-C-provider-A",
        ),
    )
    assert chosen.status == "accepted", chosen.code
    reviewed = chosen.plan
    assert reviewed.ready, (reviewed.requirements, reviewed.blockers)
    calls = 0

    def cancel_after_intent():
        nonlocal calls
        calls += 1
        return calls == 2

    stopped = operations.apply_reviewed_update(
        vault,
        source,
        review=reviewed,
        source_binding=operations.observe_reviewed_source(source, reviewed),
        vault_id="type-provider-recovery",
        import_id="type-provider-import",
        cancel=cancel_after_intent,
    )
    assert stopped.status == "cancelled" and stopped.recovery_required, stopped
    assert stopped.intent_commit and stopped.publication == "not_published"
    assert (vault / "Categories/C.md").read_bytes() == baseline["Categories/C.md"]
    return vault, stopped


def test_current8_recovery_requalifies_native_chain_and_finishes_in_fresh_process():
    vault, stopped = stopped_provider_update()
    user_head = git(vault, "rev-parse", "HEAD")
    user_index = (vault / ".git/index").read_bytes()
    current = note("category:A", icon="[[A.svg]]", body="Later provider writing.")
    (vault / "Categories/A.md").write_bytes(current)
    before = inventory(vault)
    offered = Operations().prepare_recovery(vault, direction="finish")
    assert offered.status == "offered" and offered.review is not None, offered.code
    assert offered.intent_commit == stopped.intent_commit
    assert inventory(vault) == before
    context = offered.review.producer_facts.link_context
    provider = next(
        target
        for target in context.current_targets
        if target.canonical_path == "Categories/A.md"
    )
    state = next(
        state
        for state in context.current_target_facts
        if state.target_id == provider.target_id
    )
    assert state.content.data == current
    assert state.file_roles is not None
    assert state.file_roles.category
    assert state.file_roles.path == "Categories/A.md"
    assert state.file_roles.content_sha256 == hashlib.sha256(current).hexdigest()
    assert state.structure.output_format == 8
    assert "selected_provider_invalid" not in offered.review.blockers
    change = next(
        change
        for change in offered.review.proposal.changes
        if change.item_id == "category:C"
    )
    chosen = Operations().resolve_recovery(
        vault,
        offered,
        action(
            offered.review,
            change,
            choice="incoming",
            candidate=recovery_candidate(offered.review, change),
        ),
    )
    assert chosen.status == "offered" and chosen.review.ready, chosen.code
    assert inventory(vault) == before
    restored = Operations().prepare_recovery(vault, direction="restore")
    assert restored.status == "offered" and restored.review is not None, restored.code
    restored_context = restored.review.producer_facts.link_context
    member = next(
        target
        for target in restored_context.incoming_targets
        if target.canonical_path == "Categories/C.md"
    )
    member_state = next(
        state
        for state in restored_context.incoming_target_facts
        if state.target_id == member.target_id
    )
    assert member_state.file_roles is not None
    assert member_state.file_roles.category
    assert member_state.content.data == note("category:C")
    assert member_state.structure.output_format == 8
    assert inventory(vault) == before
    icon = vault / "Attachments/A.svg"
    original_image = icon.read_bytes()
    icon.write_bytes(b"")
    empty_before = inventory(vault)
    invalid = Operations().prepare_recovery(vault, direction="finish")
    assert invalid.status == "offered" and invalid.review is not None, invalid.code
    change = next(
        row for row in invalid.review.proposal.changes if row.item_id == "category:C"
    )
    unsafe = Operations().resolve_recovery(
        vault,
        invalid,
        action(
            invalid.review,
            change,
            choice="incoming",
            candidate=recovery_candidate(invalid.review, change),
        ),
    )
    assert unsafe.status == "offered" and not unsafe.review.ready, unsafe.code
    assert "selected_provider_invalid" in unsafe.review.blockers
    refused = Operations().execute_recovery(vault, unsafe)
    assert refused.status == "refused" and not refused.authored_files_changed
    assert inventory(vault) == empty_before
    icon.write_bytes(original_image)
    completed = fresh_finish(vault)
    assert completed["operation_id"] == stopped.operation_id
    assert completed["status"] == "applied" and completed["history"] == "terminal"
    assert completed["publication"] == "complete" and not completed["recovery_required"]
    assert (vault / "Categories/A.md").read_bytes() == current
    assert (vault / "Categories/C.md").read_bytes() == note(
        "category:C", provider="[[Categories/A.md]]", body="Incoming C."
    )
    assert (vault / "Notes/Independent.md").read_bytes() == note(
        "entry:I", category=False
    )
    assert icon.read_bytes() == original_image
    undone = Operations().prepare_undo(vault)
    assert undone.status == "offered" and undone.review is not None, undone.code
    change = next(
        row for row in undone.review.proposal.changes if row.item_id == "category:C"
    )
    selected_undo = Operations().resolve_undo(
        vault,
        undone,
        action(
            undone.review,
            change,
            choice="incoming",
            candidate=recovery_candidate(undone.review, change),
        ),
    )
    assert selected_undo.status == "offered" and selected_undo.review.ready, (
        selected_undo.code,
        None if selected_undo.review is None else selected_undo.review.blockers,
    )
    assert [c.item_id for c in selected_undo.review.proposal.changes] == ["category:C"]
    assert [f.path for f in select_review_effects(selected_undo.review).files] == [
        "Categories/C.md"
    ]
    original_undo_bytes = inventory(vault)
    for key, value in (
        ("source_version", "older-unrelated-source"),
        ("mapping_sha256", "0" * 64),
    ):
        forged = selected_undo.model_copy(
            update={"review": canonical_origin_change(selected_undo.review, key, value)}
        )
        refused = Operations().execute_undo(vault, forged)
        assert refused.status == "refused" and refused.code == "undo_review_stale"
        assert inventory(vault) == original_undo_bytes
    icon.write_bytes(BLUE)
    changed_icon = inventory(vault)
    stale = Operations().execute_undo(vault, selected_undo)
    assert stale.status == "refused" and stale.code == "undo_review_stale"
    assert inventory(vault) == changed_icon
    icon.write_bytes(original_image)
    result = Operations().execute_undo(vault, selected_undo)
    assert result.status == "undone" and result.publication == "complete", result.code
    assert (vault / "Categories/C.md").read_bytes() == note("category:C")
    assert (vault / "Categories/A.md").read_bytes() == current
    assert (vault / "Notes/Independent.md").read_bytes() == note(
        "entry:I", category=False
    )
    assert icon.read_bytes() == original_image
    assert git(vault, "rev-parse", "HEAD") == user_head
    assert (vault / ".git/index").read_bytes() == user_index


def recovery_candidate(plan, change):
    """Explicitly qualify the incoming member against the actual Current provider."""
    context = plan.producer_facts.link_context
    owner = next(
        target
        for target in context.current_targets
        if target.canonical_path == change.target_path
    )
    document = next(
        row for row in context.current_documents if row.document_id == owner.target_id
    )
    state = link_state(
        change.incoming,
        target_id=owner.target_id,
        existence="present",
        membership_targets=context.current_targets,
        source_path=change.target_path,
        output_format=8,
    )
    states = tuple(
        row for row in context.current_target_facts if row.target_id != owner.target_id
    ) + (state,)
    return inspect_text_candidate(
        change.incoming,
        identity=owner.identity,
        target=owner.target,
        output_format=8,
        source_path=change.target_path,
        document_id=owner.target_id,
        path_mode=document.path_mode,
        link_targets=context.current_targets,
        link_target_facts=states,
        link_inventory="complete",
        membership_targets=context.current_targets,
    )


def canonical_origin_change(plan, key, value):
    """A coherent caller plan still cannot attest a different native origin."""
    facts = plan.producer_facts
    context = facts.link_context
    facts = facts.model_copy(
        update={
            "link_context": context.model_copy(
                update={
                    "current_target_facts": tuple(
                        state.model_copy(
                            update={
                                "resource_origin": state.resource_origin.model_copy(
                                    update={key: value}
                                )
                            }
                        )
                        if state.resource_origin is not None
                        else state
                        for state in context.current_target_facts
                    )
                }
            )
        }
    )
    offered = prepare_review(facts, preflight=plan.preflight)
    change = next(c for c in offered.proposal.changes if c.item_id == "category:C")
    selected = resolve_review(
        offered,
        action(
            offered,
            change,
            choice="incoming",
            candidate=recovery_candidate(offered, change),
        ),
    )
    assert selected.status == "accepted" and selected.plan.ready, selected.code
    assert [f.path for f in select_review_effects(selected.plan).files] == [
        "Categories/C.md"
    ]
    return selected.plan


def fresh_finish(vault):
    checkout = Path(__file__).resolve().parents[2]
    script = """
import pathlib,sys
import brz2obsidian.application.operations as module
assert pathlib.Path(module.__file__).resolve() == pathlib.Path(sys.argv[2]).resolve(), module.__file__
from brz2obsidian.application.operations import Operations
from tests.application.test_type_tag_recovery import recovery_candidate
from tests.reconciliation.test_resolution import action
ops=Operations()
offered=ops.prepare_recovery(sys.argv[1],direction='finish')
assert offered.status=='offered' and offered.review is not None,offered.code
change=next(c for c in offered.review.proposal.changes if c.item_id=='category:C')
chosen=ops.resolve_recovery(sys.argv[1],offered,action(offered.review,change,choice='incoming',candidate=recovery_candidate(offered.review,change)))
assert chosen.status=='offered' and chosen.review.ready,(chosen.code,chosen.review.blockers if chosen.review else None)
completed=ops.execute_recovery(sys.argv[1],chosen)
print(completed.model_dump_json())
"""
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(vault),
            str(checkout / "src/brz2obsidian/application/operations.py"),
        ],
        cwd=checkout,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join((str(checkout / "src"), str(checkout))),
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert process.returncode == 0, (process.stdout, process.stderr)
    return json.loads(process.stdout)
