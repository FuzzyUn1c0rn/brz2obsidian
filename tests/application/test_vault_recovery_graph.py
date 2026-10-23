"""Recovery direction is authority only through the complete retained Git graph."""

import json
import shutil

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.core import prepare_review, resolve_review
from brz2obsidian.publication.vault_apply import _acquire, _release
from brz2obsidian.publication.vault_replace import retained_metadata
from tests.application.test_vault_apply import _ready_case
from tests.application.test_vault_checkpoints import git, user_state
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, with_review_links


def _record(vault, name, payload, parents):
    blob = git(
        vault, "hash-object", "-w", "--stdin", input=json.dumps(payload).encode()
    ).strip()
    tree = (
        git(
            vault,
            "mktree",
            "-z",
            input=b"100644 blob " + blob + b"\t" + name.encode() + b"\0",
        )
        .strip()
        .decode()
    )
    return (
        git(
            vault,
            "commit-tree",
            tree,
            *(argument for parent in parents for argument in ("-p", parent)),
            input=b"independent recovery graph\n",
        )
        .strip()
        .decode()
    )


def _prepared(
    vault, source, operations, review, target, *, operation_id=None, direction=None
):
    staged = vault.parent / target
    shutil.copytree(vault / "Notes", staged / "Notes")
    if target == "incoming":
        (staged / "Notes/Opening.md").write_bytes(b"incoming opening\n")
    captured = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=review.facts.incoming_identity,
        admission=operations.inspect_history(
            vault, active_operation=operation_id
        ).admission,
        review=review,
        boundary="prepared",
        proposed=staged,
        active_operation=operation_id,
        recovery_direction=direction,
    )
    assert captured.status == "captured", captured.code
    return captured.commit, json.loads(
        git(vault, "show", captured.commit + ":manifest.json")
    )


def _recovery_case():
    vault, source, operations, reviewed, _ = _ready_case()
    original_commit, original_manifest = _prepared(
        vault, source, operations, reviewed, "incoming"
    )
    current = prepare_review(reviewed.facts, preflight=reviewed.preflight)
    current = resolve_review(
        current, action(current, choice="current", decision_id="retain:current")
    ).plan
    operation_id = "e" * 32
    mode, attributes, security = retained_metadata(vault / "Notes/Opening.md")
    metadata = [
        {
            "path": "Notes/Opening.md",
            "mode": mode,
            "attributes": attributes,
            "security": security,
        }
    ]
    original = {
        "schema_id": "brz2obsidian.vault-operation-intent",
        "schema_version": 1,
        "operation_id": operation_id,
        "kind": "apply",
        "generation": original_manifest["generation"],
        "direction": "finish",
        "association_id": original_manifest["association_id"],
        "prepared_commit": original_commit,
        "before": original_manifest["preimage"],
        "proposed": original_manifest["proposed"],
        "affected_paths": ["Notes/Opening.md"],
        "protected_paths": ["Notes/Local.md"],
        "before_metadata": metadata,
        "result_metadata": metadata,
        "created_directories": [],
    }
    origin = _record(vault, "intent.json", original, (original_commit,))
    ref = (
        "refs/brz2obsidian/imports/"
        + original_manifest["association_id"]
        + "/operations/"
        + operation_id
    )
    git(vault, "update-ref", ref, origin)
    _acquire(vault, operation_id)
    try:
        prepared, manifest = _prepared(
            vault,
            source,
            operations,
            current,
            "current",
            operation_id=operation_id,
            direction="finish",
        )
    finally:
        _release(vault, operation_id)
    recovery = dict(
        original,
        schema_id="brz2obsidian.vault-recovery-intent",
        direction="finish",
        generation=manifest["generation"],
        review_generation=current.proposal.generation,
        origin_intent_commit=origin,
        previous_operation_commit=origin,
        prepared_commit=prepared,
        before=manifest["preimage"],
        proposed=manifest["proposed"],
        affected_paths=[],
        protected_paths=["Notes/Local.md", "Notes/Opening.md"],
        before_metadata=[],
        result_metadata=[],
    )
    commit = _record(vault, "recovery.json", recovery, (origin, prepared))
    git(vault, "update-ref", ref, commit)
    return vault, operations, original, recovery, origin, commit, ref


@pytest.fixture(scope="module")
def recovery_graph():
    return _recovery_case()


def test_recovery_status_exposes_saved_finish_and_selected_review_generation(
    recovery_graph,
):
    vault, operations, _, recovery, _, commit, _ = recovery_graph
    before = user_state(vault)
    observed = Operations().inspect_update_status(vault)
    assert (
        observed.status,
        observed.publication,
        observed.kind,
        observed.direction,
    ) == (
        "content_complete",
        "complete",
        "apply",
        "finish",
    )
    assert observed.intent_commit == commit
    assert observed.generation == recovery["generation"]
    assert observed.review_generation == 1
    assert observed.recovery_required
    details = operations.read_update_details(vault)
    assert details.status == "available"
    assert [(row.path, row.before_size, row.after_size) for row in details.items] == [
        ("Notes/Local.md", 9, 9),
        ("Notes/Opening.md", 18, 18),
    ]
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert user_state(vault) == before


def test_second_stop_preserves_saved_kind_direction_and_generation(recovery_graph):
    vault, _, _, recovery, _, commit, ref = recovery_graph
    before = user_state(vault)
    stopped = {
        "schema_id": "brz2obsidian.vault-operation-stop",
        "schema_version": 1,
        "operation_id": recovery["operation_id"],
        "kind": "apply",
        "generation": recovery["generation"],
        "direction": "finish",
        "status": "cancelled",
        "intent_commit": commit,
        "acknowledged_after_files": 0,
    }
    tip = _record(vault, "stop.json", stopped, (commit,))
    try:
        git(vault, "update-ref", ref, tip)
        observed = Operations().inspect_update_status(vault)
        assert (
            observed.status,
            observed.kind,
            observed.direction,
            observed.generation,
        ) == ("cancelled", "apply", "finish", 3)
        assert observed.intent_commit == commit and observed.stop_commit == tip
        assert observed.review_generation == 1 and observed.recovery_required
    finally:
        git(vault, "update-ref", ref, commit)
    assert user_state(vault) == before


def test_inconsistent_recovery_graph_never_becomes_operation_authority(recovery_graph):
    vault, operations, _, recovery, origin, commit, ref = recovery_graph
    before = user_state(vault)
    variants = [
        (dict(recovery, review_generation=2), (origin, recovery["prepared_commit"])),
        (
            dict(recovery, origin_intent_commit=recovery["prepared_commit"]),
            (origin, recovery["prepared_commit"]),
        ),
        (dict(recovery, generation=2), (origin, recovery["prepared_commit"])),
        (dict(recovery, kind="undo"), (origin, recovery["prepared_commit"])),
        (dict(recovery), (recovery["prepared_commit"], origin)),
    ]
    for index, (payload, parents) in enumerate(variants):
        corrupted = _record(vault, "recovery.json", payload, parents)
        try:
            git(vault, "update-ref", ref, corrupted)
            observed = Operations().inspect_update_status(vault)
            assert observed.status == "unknown" and observed.recovery_required
            if index == 0:
                assert operations.read_update_details(vault).status == "unavailable"
            assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
        finally:
            git(vault, "update-ref", ref, commit)
    assert user_state(vault) == before


def test_restore_label_cannot_authorize_the_finish_target_review(recovery_graph):
    vault, _, _, recovery, origin, commit, ref = recovery_graph
    counterfeit = _record(
        vault,
        "recovery.json",
        dict(recovery, direction="restore"),
        (origin, recovery["prepared_commit"]),
    )
    try:
        git(vault, "update-ref", ref, counterfeit)
        observed = Operations().inspect_update_status(vault)
        assert observed.status == "unknown" and observed.recovery_required
        assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    finally:
        git(vault, "update-ref", ref, commit)


def test_later_edit_to_selected_current_requires_review(recovery_graph):
    vault, _, _, _, _, _, _ = recovery_graph
    path = vault / "Notes/Opening.md"
    saved = path.read_bytes()
    try:
        path.write_bytes(b"later protected writing\r\n")
        observed = Operations().inspect_update_status(vault)
        assert observed.status == "unknown" and observed.recovery_required
        assert path.read_bytes() == b"later protected writing\r\n"
    finally:
        path.write_bytes(saved)


def test_restore_review_binds_the_saved_prior_source_lineage():
    vault, source, operations, reviewed, _ = _ready_case()
    (source / "Notes/Opening.md").write_bytes(b"authored opening\r\n")
    prior = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=reviewed.facts.incoming_identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert prior.status == "captured", prior.code
    (source / "Notes/Opening.md").write_bytes(b"incoming opening\n")
    offered = prepare_review(reviewed.facts, preflight=reviewed.preflight)
    kept = resolve_review(
        offered, action(offered, choice="current", decision_id="restore:origin-current")
    ).plan
    original_commit, original_manifest = _prepared(
        vault, source, operations, kept, "restore-origin"
    )
    # A fixture source version happens to equal the restoration target. The
    # complete recovery integration owns the distinct-source/authored case.
    (source / "Notes/Opening.md").write_bytes(b"authored opening\r\n")
    facts = with_review_links(
        request(
            original=b"original\r\n",
            current=b"authored opening\r\n",
            incoming=b"authored opening\r\n",
        )
    )
    plan = prepare_review(facts, preflight=operations.inspect_vault(vault).preflight)
    plan = resolve_review(
        plan, action(plan, choice="current", decision_id="restore:retain")
    ).plan
    original = {
        "schema_id": "brz2obsidian.vault-operation-intent",
        "schema_version": 1,
        "operation_id": "d" * 32,
        "kind": "apply",
        "generation": original_manifest["generation"],
        "direction": "finish",
        "association_id": original_manifest["association_id"],
        "prepared_commit": original_commit,
        "before": original_manifest["preimage"],
        "proposed": original_manifest["proposed"],
        "affected_paths": [],
        "protected_paths": ["Notes/Local.md", "Notes/Opening.md"],
        "before_metadata": [],
        "result_metadata": [],
        "created_directories": [],
    }
    origin = _record(vault, "intent.json", original, (original_commit,))
    ref = (
        "refs/brz2obsidian/imports/"
        + original_manifest["association_id"]
        + "/operations/"
        + original["operation_id"]
    )
    git(vault, "update-ref", ref, origin)
    _acquire(vault, original["operation_id"])
    try:
        prepared, manifest = _prepared(
            vault,
            source,
            operations,
            plan,
            "restore-proposed",
            operation_id=original["operation_id"],
            direction="restore",
        )
    finally:
        _release(vault, original["operation_id"])
    selected = dict(
        original,
        schema_id="brz2obsidian.vault-recovery-intent",
        direction="restore",
        generation=manifest["generation"],
        prepared_commit=prepared,
        review_generation=1,
        origin_intent_commit=origin,
        previous_operation_commit=origin,
    )
    authority = _record(vault, "recovery.json", selected, (origin, prepared))
    git(vault, "update-ref", ref, authority)
    observed = Operations().inspect_update_status(vault)
    assert (observed.status, observed.kind, observed.direction) == (
        "content_complete",
        "apply",
        "restore",
    )
    assert observed.intent_commit == authority and observed.recovery_required
    assert operations.read_update_details(vault).status == "available"
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
