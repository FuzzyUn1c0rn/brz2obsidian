"""Public existing-vault application over disposable authored files and Git."""

import json
import subprocess
import sys

from brz2obsidian.application.operations import Operations
from brz2obsidian.contracts import ExactContent
from brz2obsidian.core import prepare_review, resolve_review
from brz2obsidian.obsidian import inspect_text_candidate
from tests.application.test_vault_checkpoints import fixture_case, git, user_state
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, preflight, with_review_links


def test_unresolved_review_refuses_before_owned_history_or_authored_files_change():
    vault, source = fixture_case()
    git(vault, "init", "-q")
    (vault / "Notes").mkdir()
    (vault / "Notes/Opening.md").write_bytes(b"original\r\n")
    git(vault, "add", "Notes/Opening.md")
    git(vault, "commit", "-qm", "user baseline")
    (source / "Notes").mkdir()
    (source / "Notes/Opening.md").write_bytes(b"incoming\n")
    before = user_state(vault)
    plan = prepare_review(with_review_links(request()), preflight=preflight())
    assert not plan.ready

    outcome = Operations().apply_reviewed_update(
        vault,
        source,
        review=plan,
        vault_id="vault-one",
        import_id="import-one",
    )

    assert outcome.status == "refused" and outcome.code == "review_not_ready"
    assert outcome.operation_id is None and not outcome.authored_files_changed
    assert user_state(vault) == before
    assert Operations().read_checkpoint(vault).status == "absent"


def _apply(operations, vault, source, *, review, source_binding=None, **kwargs):
    binding = (
        source_binding
        if source_binding is not None
        else operations.observe_reviewed_source(source, review)
    )
    return operations.apply_reviewed_update(
        vault, source, review=review, source_binding=binding, **kwargs
    )


def _ready_case(
    *, storage_transform=False, tracking_ignore=False, unaffected_auto=False
):
    vault, source = fixture_case()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "Notes").mkdir()
    (vault / "Notes/Opening.md").write_bytes(b"original\r\n")
    (vault / "Notes/Local.md").write_bytes(b"local \xff\r\n")
    git(vault, "add", "Notes/Local.md")
    if not tracking_ignore:
        git(vault, "add", "Notes/Opening.md")
    git(vault, "commit", "-qm", "user baseline")
    git(vault, "update-ref", "refs/notes/user-proof", "HEAD")
    (source / "Notes").mkdir()
    (source / "Notes/Opening.md").write_bytes(b"original\r\n")
    facts = request(
        original=b"original\r\n",
        current=b"authored opening\r\n",
        incoming=b"incoming opening\n",
    )
    if unaffected_auto:
        from brz2obsidian.contracts import FormatBaselineOutput

        (vault / "Notes/Unchanged.md").write_bytes(b"unchanged note\n")
        (source / "Notes/Unchanged.md").write_bytes(b"unchanged note\n")
        extra = request(
            original=b"unchanged note\n",
            current=b"unchanged note\n",
            incoming=b"unchanged note\n",
        )
        current = extra.subjects[0].current.model_copy(
            update={"path": "Notes/Unchanged.md"}
        )
        target = extra.subjects[0].source_target.model_copy(
            update={"normalized_path": "notes/unchanged.md"}
        )
        subject = extra.subjects[0].model_copy(
            update={
                "item_id": "entry:unchanged",
                "path": "Notes/Unchanged.md",
                "current": current,
                "source_target": target,
                "title": "Unchanged",
            }
        )
        entry = extra.identity_inventory[0].model_copy(
            update={
                "entry_id": "unchanged-entry",
                "identity": extra.identity_inventory[0].identity.model_copy(
                    update={"item_id": "entry:unchanged"}
                ),
                "current": current,
                "target": target,
                "title": "Unchanged",
            }
        )
        baseline = facts.format_operation.established_baseline
        operation = facts.format_operation.model_copy(
            update={
                "established_baseline": baseline.model_copy(
                    update={
                        "outputs": baseline.outputs
                        + (
                            FormatBaselineOutput(
                                item_id=subject.item_id,
                                facet=subject.facet,
                                content=ExactContent(data=b"unchanged note\n"),
                            ),
                        )
                    }
                )
            }
        )
        facts = facts.model_copy(
            update={
                "subjects": facts.subjects + (subject,),
                "identity_inventory": facts.identity_inventory + (entry,),
                "format_operation": operation,
            }
        )
        git(vault, "add", "Notes/Unchanged.md")
    facts = with_review_links(facts)
    operations = Operations()
    initial = operations.inspect_history(vault).admission
    seeded = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=facts.incoming_identity,
        admission=initial,
    )
    assert seeded.status == "captured", seeded.code

    if storage_transform:
        (vault / ".gitattributes").write_bytes(b"Notes/Opening.md text\n")
        git(vault, "add", ".gitattributes")
    if tracking_ignore:
        (vault / ".gitignore").write_bytes(b"Notes/Opening.md\nScratch/\n")
        git(vault, "add", ".gitignore")
        (vault / "Scratch").mkdir()
        (vault / "Scratch/Unrelated.bin").write_bytes(b"ignored unrelated \xff\n")

    (vault / "Notes/Opening.md").write_bytes(b"staged opening\n")
    if not tracking_ignore:
        git(vault, "add", "Notes/Opening.md")
    (vault / "Notes/Opening.md").write_bytes(b"authored opening\r\n")
    (source / "Notes/Opening.md").write_bytes(b"incoming opening\n")

    if storage_transform or tracking_ignore:
        from brz2obsidian.application.vault_contracts import VaultSubject
        from brz2obsidian.contracts import reconciliation_subject_id

        subject_id = reconciliation_subject_id(
            facts.incoming_identity.module_id,
            facts.incoming_identity.collection_id,
            facts.subjects[0].item_id,
            facts.subjects[0].facet,
        )
        admission = operations.inspect_history(
            vault,
            subjects=(VaultSubject(path="Notes/Opening.md", subject_id=subject_id),),
        ).admission
        expected = (["storage"] if storage_transform else []) + (
            ["tracking"] if tracking_ignore else []
        )
        assert [consent.kind for consent in admission.preflight.consents] == expected
    else:
        admission = operations.inspect_history(vault).admission
    offered = prepare_review(facts, preflight=admission.preflight)
    candidate = inspect_text_candidate(
        ExactContent(data=b"incoming opening\n"),
        identity=facts.identity_inventory[0].identity,
        target=facts.subjects[0].source_target,
        output_format=7,
        source_path="Notes/Opening.md",
        document_id="review:opening",
        path_mode="vault",
        link_targets=(),
        link_target_facts=(),
        link_inventory="complete",
    )
    reviewed = resolve_review(
        offered, action(offered, choice="incoming", candidate=candidate)
    ).plan
    for domain in (
        ("storage" if storage_transform else None),
        ("tracking" if tracking_ignore else None),
    ):
        if domain is None:
            continue
        requirement = next(r for r in reviewed.requirements if r.domain == domain)
        reviewed = resolve_review(
            reviewed,
            action(
                reviewed,
                domain=domain,
                choice="accept",
                decision_id=domain + ":accept",
                change_id=requirement.change_id,
                reviewed_assumptions=requirement.assumptions,
            ),
        ).plan
    assert reviewed.ready, (reviewed.requirements, reviewed.blockers)
    before = user_state(vault)
    return vault, source, operations, reviewed, before


def test_ready_whole_review_applies_exact_note_and_retains_unrelated_user_state():
    vault, source, operations, reviewed, before = _ready_case()

    outcome = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
    )

    assert outcome.status == "applied", (outcome.phase, outcome.history, outcome.code)
    restarted = Operations().inspect_update_status(vault)
    assert (
        restarted.status == "applied"
        and restarted.receipt_commit == outcome.receipt_commit
    )
    assert outcome.generation == restarted.generation
    assert outcome.publication == "complete" and outcome.history == "terminal"
    assert outcome.operation_id and not outcome.recovery_required
    assert (vault / "Notes/Opening.md").read_bytes() == b"incoming opening\n"
    assert (vault / "Notes/Local.md").read_bytes() == b"local \xff\r\n"
    after = user_state(vault)
    assert after["index"] == before["index"]
    assert after["head"] == before["head"]
    assert after["config"] == before["config"]
    assert after["stages"] == before["stages"]
    assert tuple(
        row
        for row in after["refs"]
        if not row.startswith(b"refs/brz2obsidian/imports/")
    ) == tuple(
        row
        for row in before["refs"]
        if not row.startswith(b"refs/brz2obsidian/imports/")
    )
    checkpoint = operations.read_checkpoint(vault)
    assert checkpoint.status == "valid" and checkpoint.manifest.boundary == "result"
    assert [(row.path, row.size) for row in checkpoint.manifest.preimage] == [
        ("Notes/Local.md", 9),
        ("Notes/Opening.md", 18),
    ]
    assert [(row.path, row.size) for row in checkpoint.manifest.proposed] == [
        ("Notes/Local.md", 9),
        ("Notes/Opening.md", 17),
    ]
    first_page = operations.read_update_details(vault, offset=0, limit=1)
    second_page = operations.read_update_details(vault, offset=1, limit=1)
    assert first_page.status == second_page.status == "available"
    assert first_page.operation_id == second_page.operation_id == outcome.operation_id
    assert first_page.total == second_page.total == 2
    assert first_page.next_offset == 1 and second_page.next_offset is None
    assert [
        (row.path, row.before_size, row.after_size) for row in first_page.items
    ] == [
        ("Notes/Local.md", 9, 9),
    ]
    assert [
        (row.path, row.before_size, row.after_size) for row in second_page.items
    ] == [
        ("Notes/Opening.md", 18, 17),
    ]
    assert second_page.items[0].before_sha256 != second_page.items[0].after_sha256

    (vault / "Notes/Local.md").write_bytes(b"later local edit \xfe\n")
    later = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=reviewed.facts.incoming_identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert later.status == "captured" and later.commit != checkpoint.locator.commit
    later_status = Operations().inspect_update_status(vault)
    assert later_status.status == "applied"
    assert later_status.receipt_commit == outcome.receipt_commit
    assert (vault / "Notes/Local.md").read_bytes() == b"later local edit \xfe\n"
    operation_ref = (
        "refs/brz2obsidian/imports/"
        + checkpoint.locator.association.association_id
        + "/operations/"
        + outcome.operation_id
    )
    git(vault, "update-ref", "-d", operation_ref, outcome.receipt_commit)
    missing_root = operations.inspect_history(vault)
    assert missing_root.admission.status == "recovery_first"
    assert Operations().inspect_update_status(vault).code == "operation_record_missing"
    git(vault, "update-ref", operation_ref, outcome.receipt_commit)
    assert Operations().inspect_update_status(vault).status == "applied"

    # A real receipt-shaped ref still needs its actual result parent and graph.
    invalid = json.loads(git(vault, "show", f"{outcome.receipt_commit}:receipt.json"))
    invalid["result_commit"] = outcome.checkpoint_commit
    blob = git(
        vault,
        "hash-object",
        "-w",
        "--stdin",
        input=json.dumps(invalid, separators=(",", ":")).encode(),
    ).strip()
    tree = git(
        vault, "mktree", "-z", input=b"100644 blob " + blob + b"\treceipt.json\0"
    ).strip()
    false_terminal = (
        git(
            vault,
            "commit-tree",
            tree.decode(),
            "-p",
            outcome.intent_commit,
            "-p",
            outcome.checkpoint_commit,
            input=b"receipt with a prepared parent in the result role\n",
        )
        .strip()
        .decode()
    )
    git(vault, "update-ref", operation_ref, false_terminal, outcome.receipt_commit)
    assert Operations().inspect_update_status(vault).status == "unknown"
    blocked = operations.inspect_history(vault)
    assert blocked.admission.status == "recovery_first"
    assert (vault / "Notes/Opening.md").read_bytes() == b"incoming opening\n"
    assert user_state(vault)["index"] == before["index"]


def test_selected_current_bytes_report_no_content_change_with_terminal_history():
    vault, source, operations, reviewed, before = _ready_case()
    offered = prepare_review(reviewed.facts, preflight=reviewed.preflight)
    kept = resolve_review(
        offered, action(offered, choice="current", decision_id="keep:current")
    ).plan
    assert kept.ready

    outcome = _apply(
        operations,
        vault,
        source,
        review=kept,
        vault_id="vault-one",
        import_id="import-one",
    )

    assert outcome.status == "no_content_change" and outcome.code == "no_content_change"
    assert outcome.planned_files == outcome.published_files == 0
    assert outcome.history == "terminal" and outcome.receipt_commit
    assert not outcome.authored_files_changed and not outcome.recovery_required
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert user_state(vault)["index"] == before["index"]
    restarted = Operations().inspect_update_status(vault)
    assert restarted.status == "no_content_change"
    assert restarted.receipt_commit == outcome.receipt_commit


def test_prepared_storage_retains_unready_s1_review_with_original_subject_scope():
    from brz2obsidian.application.vault_contracts import VaultSubject
    from brz2obsidian.contracts import reconciliation_subject_id

    vault, source, operations, reviewed, before = _ready_case()
    offered = prepare_review(reviewed.facts, preflight=reviewed.preflight)
    assert not offered.ready
    proposed = vault.parent / "proposed-unready"
    (proposed / "Notes").mkdir(parents=True)
    for name in ("Local.md", "Opening.md"):
        (proposed / "Notes" / name).write_bytes((vault / "Notes" / name).read_bytes())
    subject = reviewed.facts.subjects[0]
    subject_id = reconciliation_subject_id(
        reviewed.facts.incoming_identity.module_id,
        reviewed.facts.incoming_identity.collection_id,
        subject.item_id,
        subject.facet,
    )
    subjects = (VaultSubject(path="Notes/Opening.md", subject_id=subject_id),)

    captured = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=reviewed.facts.incoming_identity,
        admission=operations.inspect_history(vault, subjects=subjects).admission,
        review=offered,
        boundary="prepared",
        proposed=proposed,
        subjects=subjects,
    )

    assert captured.status == "captured", captured.code
    stored = operations.read_checkpoint(vault)
    assert stored.status == "valid" and stored.manifest.boundary == "prepared"
    assert stored.review is not None and not stored.review.ready
    assert user_state(vault)["index"] == before["index"]
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"

    from brz2obsidian.application.vault_update_contracts import VaultOperationIntent

    assert stored.manifest.preimage == stored.manifest.proposed
    operation_id = "f" * 32
    intent = VaultOperationIntent(
        schema_id="brz2obsidian.vault-operation-intent",
        schema_version=1,
        operation_id=operation_id,
        kind="apply",
        generation=stored.manifest.generation,
        direction="finish",
        association_id=stored.manifest.association_id,
        prepared_commit=stored.locator.commit,
        before=stored.manifest.preimage,
        proposed=stored.manifest.proposed,
        affected_paths=(),
        protected_paths=tuple(row.path for row in stored.manifest.preimage),
        before_metadata=(),
        result_metadata=(),
        created_directories=(),
    )
    blob = git(
        vault,
        "hash-object",
        "-w",
        "--stdin",
        input=intent.model_dump_json().encode(),
    ).strip()
    tree = git(
        vault, "mktree", "-z", input=b"100644 blob " + blob + b"\tintent.json\0"
    ).strip()
    commit = (
        git(
            vault,
            "commit-tree",
            tree.decode(),
            "-p",
            stored.locator.commit,
            input=b"unready prepared review must not authorize an intent\n",
        )
        .strip()
        .decode()
    )
    ref = (
        "refs/brz2obsidian/imports/"
        + stored.locator.association.association_id
        + "/operations/"
        + operation_id
    )
    git(vault, "update-ref", ref, commit)
    assert Operations().inspect_update_status(vault).status == "unknown"
    assert operations.inspect_history(vault).admission.status == "recovery_first"
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert user_state(vault)["index"] == before["index"]


def test_scoped_builtin_storage_consent_applies_reviewed_exact_raw_bytes():
    vault, source, operations, reviewed, before = _ready_case(storage_transform=True)
    assert reviewed.preflight.consents[0].policy == "builtin_transform"
    assert reviewed.consents[0].choice == "accept"

    outcome = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
    )

    assert outcome.status == "applied", (outcome.code, outcome.phase)
    assert (vault / "Notes/Opening.md").read_bytes() == b"incoming opening\n"
    assert operations.read_checkpoint(vault).manifest.boundary == "result"
    assert user_state(vault)["index"] == before["index"]


def test_accepted_scoped_storage_and_tracking_include_only_reviewed_ignored_note():
    vault, source, operations, reviewed, before = _ready_case(
        storage_transform=True, tracking_ignore=True
    )
    assert [consent.kind for consent in reviewed.preflight.consents] == [
        "storage",
        "tracking",
    ]
    assert [decision.choice for decision in reviewed.consents] == ["accept", "accept"]
    unrelated = (vault / "Scratch/Unrelated.bin").read_bytes()

    outcome = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
    )

    assert outcome.status == "applied", (outcome.code, outcome.phase)
    assert outcome.planned_files == outcome.published_files == 1
    assert (vault / "Notes/Opening.md").read_bytes() == b"incoming opening\n"
    assert (vault / "Scratch/Unrelated.bin").read_bytes() == unrelated
    assert user_state(vault)["index"] == before["index"]
    result = operations.read_checkpoint(vault)
    assert result.status == "valid" and result.manifest.boundary == "result"
    assert "Notes/Opening.md" in {row.path for row in result.manifest.vault}
    assert "Scratch/Unrelated.bin" not in {row.path for row in result.manifest.vault}


def test_cancel_after_intent_retains_stop_and_requires_exact_recovery():
    vault, source, operations, reviewed, before = _ready_case()
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls == 2

    outcome = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
        cancel=cancel,
    )

    assert outcome.status == "cancelled" and outcome.code == "cancelled_after_intent"
    assert outcome.intent_commit and outcome.stop_commit and outcome.recovery_required
    assert outcome.published_files == 0 and not outcome.authored_files_changed
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert (vault / "Notes/Local.md").read_bytes() == b"local \xff\r\n"
    assert user_state(vault)["index"] == before["index"]
    restarted = Operations().inspect_update_status(vault)
    assert restarted.status == "cancelled" and restarted.publication == "not_published"
    assert outcome.generation == restarted.generation
    assert restarted.stop_commit == outcome.stop_commit
    assert operations.inspect_history(vault).admission.status == "recovery_first"


def test_valid_schema_stop_with_wrong_direction_is_not_operation_authority():
    import pytest
    from pydantic import ValidationError

    from brz2obsidian.application.vault_update_contracts import VaultOperationIntent

    vault, source, operations, reviewed, before = _ready_case()
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls == 2

    outcome = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
        cancel=cancel,
    )
    assert outcome.status == "cancelled" and outcome.stop_commit
    incomplete_intent = json.loads(
        git(vault, "show", f"{outcome.intent_commit}:intent.json")
    )
    assert "created_directories" in incomplete_intent
    del incomplete_intent["created_directories"]
    with pytest.raises(ValidationError, match="created_directories"):
        VaultOperationIntent.model_validate_json(json.dumps(incomplete_intent))
    original = json.loads(git(vault, "show", f"{outcome.stop_commit}:stop.json"))
    assert original["direction"] == "finish"
    original["direction"] = "restore"
    blob = git(
        vault,
        "hash-object",
        "-w",
        "--stdin",
        input=json.dumps(original, separators=(",", ":")).encode(),
    ).strip()
    tree = git(
        vault, "mktree", "-z", input=b"100644 blob " + blob + b"\tstop.json\0"
    ).strip()
    changed = (
        git(
            vault,
            "commit-tree",
            tree.decode(),
            "-p",
            outcome.intent_commit,
            input=b"valid schema wrong direction\n",
        )
        .strip()
        .decode()
    )
    ref = (
        git(
            vault,
            "for-each-ref",
            "--format=%(refname)",
            "refs/brz2obsidian/imports",
        )
        .decode()
        .splitlines()
    )
    operation_refs = [
        row for row in ref if row.endswith("/operations/" + outcome.operation_id)
    ]
    assert len(operation_refs) == 1
    git(vault, "update-ref", operation_refs[0], changed, outcome.stop_commit)

    status = Operations().inspect_update_status(vault)
    assert status.status == "unknown" and status.code == "operation_history_invalid"
    assert status.recovery_required and not status.authored_files_changed
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert user_state(vault)["index"] == before["index"]

    # Matching restore tokens are still unsupported for an apply/finish writer.
    changed_intent = json.loads(
        git(vault, "show", f"{outcome.intent_commit}:intent.json")
    )
    changed_intent["direction"] = "restore"
    blob = git(
        vault,
        "hash-object",
        "-w",
        "--stdin",
        input=json.dumps(changed_intent, separators=(",", ":")).encode(),
    ).strip()
    tree = git(
        vault, "mktree", "-z", input=b"100644 blob " + blob + b"\tintent.json\0"
    ).strip()
    restore_intent = (
        git(
            vault,
            "commit-tree",
            tree.decode(),
            "-p",
            outcome.checkpoint_commit,
            input=b"coherent unsupported restore intent\n",
        )
        .strip()
        .decode()
    )
    original["intent_commit"] = restore_intent
    blob = git(
        vault,
        "hash-object",
        "-w",
        "--stdin",
        input=json.dumps(original, separators=(",", ":")).encode(),
    ).strip()
    tree = git(
        vault, "mktree", "-z", input=b"100644 blob " + blob + b"\tstop.json\0"
    ).strip()
    restore_stop = (
        git(
            vault,
            "commit-tree",
            tree.decode(),
            "-p",
            restore_intent,
            input=b"coherent unsupported restore stop\n",
        )
        .strip()
        .decode()
    )
    git(vault, "update-ref", operation_refs[0], restore_stop, changed)
    coherent = Operations().inspect_update_status(vault)
    assert coherent.status == "unknown" and coherent.code == "operation_history_invalid"
    assert operations.inspect_history(vault).admission.status == "recovery_first"
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert user_state(vault)["index"] == before["index"]


def test_cancel_before_intent_retains_preparation_without_publication():
    vault, source, operations, reviewed, before = _ready_case()
    outcome = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
        cancel=lambda: True,
    )

    assert outcome.status == "cancelled" and outcome.code == "cancelled_before_intent"
    assert outcome.checkpoint_commit and not outcome.intent_commit
    assert outcome.history == "prepared" and outcome.publication == "not_started"
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert user_state(vault)["index"] == before["index"]
    assert Operations().inspect_update_status(vault).status == "unknown"
    assert Operations().read_checkpoint(vault).manifest.boundary == "prepared"


def test_bogus_same_owner_id_cannot_hide_retained_incomplete_intent():
    from pathlib import Path

    from brz2obsidian.application.vault_update_contracts import VaultApplyResult

    vault, source, operations, reviewed, before = _ready_case()
    review_path = vault.parent / "review-for-stopped-child.json"
    review_path.write_text(reviewed.model_dump_json(), encoding="utf-8")
    stopped = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from pathlib import Path
from brz2obsidian.application.operations import Operations
from brz2obsidian.contracts import ReviewPlan

calls = 0
def cancel():
    global calls
    calls += 1
    return calls > 1

review = ReviewPlan.model_validate_json(Path(sys.argv[3]).read_bytes())
outcome = Operations().apply_reviewed_update(
    sys.argv[1], sys.argv[2], review=review,
    source_binding=Operations().observe_reviewed_source(sys.argv[2], review),
    vault_id="vault-one", import_id="import-one", cancel=cancel,
)
print(outcome.model_dump_json())
""",
            str(vault),
            str(source),
            str(review_path),
        ],
        capture_output=True,
        timeout=90,
        check=True,
    )
    outcome = VaultApplyResult.model_validate_json(stopped.stdout)
    assert (
        outcome.status == "cancelled" and outcome.intent_commit and outcome.stop_commit
    )
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    marker = Path(vault / ".git/brz2obsidian")
    assert {path.name for path in marker.iterdir()} == {"owner.json", "held"}
    owner = json.loads((marker / "owner.json").read_text())
    assert owner["operation_id"] == outcome.operation_id
    (marker / "owner.json").unlink()
    (marker / "held").unlink()
    marker.rmdir()

    observed = operations.inspect_history(vault, active_operation="bogus-operation")
    assert observed.admission.status == "recovery_first"
    assert observed.status == "unavailable"
    recapture = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=reviewed.facts.incoming_identity,
        admission=observed.admission,
        active_operation="bogus-operation",
    )
    assert recapture.status == "refused" and not recapture.history_retained
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert user_state(vault)["index"] == before["index"]


def test_pre_intent_owned_cleanup_failure_requires_recovery_without_publication(
    monkeypatch,
):
    from pathlib import Path

    vault, source, operations, reviewed, before = _ready_case()
    unlink = Path.unlink

    def fail_owner_cleanup(path, *args, **kwargs):
        if path == vault / ".git/brz2obsidian/owner.json":
            raise OSError("Injected pre-intent owner cleanup failure")
        return unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_owner_cleanup)
        outcome = _apply(
            operations,
            vault,
            source,
            review=reviewed,
            vault_id="vault-one",
            import_id="import-one",
            cancel=lambda: True,
        )

    assert outcome.status == "incomplete" and outcome.code == "owned_cleanup_failed"
    assert outcome.publication == "not_started" and outcome.history == "prepared"
    assert outcome.recovery_required and outcome.intent_commit is None
    assert not outcome.authored_files_changed
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert user_state(vault)["index"] == before["index"]
    assert operations.inspect_history(vault).admission.status == "recovery_first"
    marker = vault / ".git/brz2obsidian"
    (marker / "owner.json").unlink()
    (marker / "held").unlink()
    marker.rmdir()


def test_partial_owner_acquisition_cleanup_failure_reports_recovery(monkeypatch):
    from pathlib import Path

    vault, source, operations, reviewed, before = _ready_case()
    marker = vault / ".git/brz2obsidian"
    original_open, original_unlink = Path.open, Path.unlink

    def fail_held(path, mode="r", *args, **kwargs):
        if path == marker / "held" and mode == "xb":
            raise OSError("Injected held-file creation failure")
        return original_open(path, mode, *args, **kwargs)

    def fail_owner_cleanup(path, *args, **kwargs):
        if path == marker / "owner.json":
            raise OSError("Injected partial acquisition cleanup failure")
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", fail_held)
        patch.setattr(Path, "unlink", fail_owner_cleanup)
        outcome = _apply(
            operations,
            vault,
            source,
            review=reviewed,
            vault_id="vault-one",
            import_id="import-one",
        )

    assert outcome.status == "unknown" and outcome.code == "owned_acquire_failed"
    assert outcome.publication == "not_started" and outcome.history == "none"
    assert outcome.recovery_required and outcome.intent_commit is None
    assert not outcome.authored_files_changed
    assert {path.name for path in marker.iterdir()} == {"owner.json"}
    assert operations.inspect_history(vault).admission.status == "recovery_first"
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert user_state(vault)["index"] == before["index"]
    (marker / "owner.json").unlink()
    marker.rmdir()


def test_ready_review_requires_actual_source_and_current_fact_bytes():
    vault, source, operations, reviewed, before = _ready_case()
    initial = operations.read_checkpoint(vault).locator.commit
    incoming_path = source / "Notes/Opening.md"
    incoming_path.write_bytes(b"different source bytes\n")

    stale_source = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
    )
    assert (
        stale_source.status == "refused"
        and stale_source.code == "review_inputs_changed"
    )
    assert (
        stale_source.intent_commit is None and not stale_source.authored_files_changed
    )
    assert operations.read_checkpoint(vault).locator.commit == initial
    incoming_path.write_bytes(b"incoming opening\n")

    facts = with_review_links(
        request(
            original=b"original\r\n",
            current=b"different reviewed current\r\n",
            incoming=b"incoming opening\n",
        )
    )
    offered = prepare_review(
        facts, preflight=operations.inspect_history(vault).admission.preflight
    )
    candidate = inspect_text_candidate(
        ExactContent(data=b"incoming opening\n"),
        identity=facts.identity_inventory[0].identity,
        target=facts.subjects[0].source_target,
        output_format=7,
        source_path="Notes/Opening.md",
        document_id="review:opening",
        path_mode="vault",
        link_targets=(),
        link_target_facts=(),
        link_inventory="complete",
    )
    false_current = resolve_review(
        offered, action(offered, choice="incoming", candidate=candidate)
    ).plan
    assert false_current.ready
    stale_current = _apply(
        operations,
        vault,
        source,
        review=false_current,
        vault_id="vault-one",
        import_id="import-one",
    )
    assert (
        stale_current.status == "refused"
        and stale_current.code == "review_inputs_changed"
    )
    assert (
        stale_current.intent_commit is None and not stale_current.authored_files_changed
    )
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert user_state(vault)["index"] == before["index"]
    assert operations.read_checkpoint(vault).locator.commit == initial


def test_complete_reviewed_source_binding_refuses_unreviewed_added_payload():
    vault, source, operations, reviewed, before = _ready_case()
    offered = prepare_review(reviewed.facts, preflight=reviewed.preflight)
    assert not offered.ready and offered.proposal == reviewed.proposal
    binding = operations.observe_reviewed_source(source, offered)
    checkpoint = operations.read_checkpoint(vault).locator.commit
    (source / "Notes/Unreviewed.bin").write_bytes(b"unreviewed source\x00\xff")

    outcome = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        source_binding=binding,
        vault_id="vault-one",
        import_id="import-one",
    )

    assert outcome.status == "refused" and outcome.code == "source_payload_changed"
    assert outcome.intent_commit is None and not outcome.authored_files_changed
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert operations.read_checkpoint(vault).locator.commit == checkpoint
    assert user_state(vault) == before


def test_unsupported_durable_volume_refuses_before_authored_publication(monkeypatch):
    from brz2obsidian.publication import vault_apply

    vault, source, operations, reviewed, before = _ready_case()
    checkpoint = operations.read_checkpoint(vault).locator.commit
    monkeypatch.setattr(vault_apply, "supported_durable_volume", lambda root: False)

    outcome = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
    )

    assert outcome.status == "refused" and outcome.code == "unsupported_durable_volume"
    assert outcome.intent_commit is None and not outcome.authored_files_changed
    assert operations.read_checkpoint(vault).locator.commit == checkpoint
    assert user_state(vault) == before


def test_stage_capacity_observation_refuses_before_copied_or_authored_files(
    monkeypatch,
):
    from collections import namedtuple

    from brz2obsidian.publication import vault_apply

    vault, source, operations, reviewed, before = _ready_case()
    checkpoint = operations.read_checkpoint(vault).locator.commit
    Usage = namedtuple("Usage", "total used free")
    actual_shutil = vault_apply.shutil

    class LowCapacity:
        def disk_usage(self, path):
            return Usage(1, 0, 1)

        def __getattr__(self, name):
            return getattr(actual_shutil, name)

    monkeypatch.setattr(vault_apply, "shutil", LowCapacity())

    outcome = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
    )

    assert (
        outcome.status == "refused" and outcome.code == "insufficient_stage_resources"
    )
    assert outcome.intent_commit is None and not outcome.authored_files_changed
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert operations.read_checkpoint(vault).locator.commit == checkpoint
    assert user_state(vault) == before


def test_owned_cleanup_failure_after_terminal_receipt_reports_complete_content(
    monkeypatch,
):
    from pathlib import Path

    vault, source, operations, reviewed, before = _ready_case()
    unlink = Path.unlink

    def fail_owned_cleanup(path, *args, **kwargs):
        if path == vault / ".git/brz2obsidian/owner.json":
            raise OSError("Injected owned-marker cleanup failure")
        return unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_owned_cleanup)
        outcome = _apply(
            operations,
            vault,
            source,
            review=reviewed,
            vault_id="vault-one",
            import_id="import-one",
        )

    assert outcome.status == "content_complete" and outcome.publication == "complete"
    assert outcome.history == "terminal" and outcome.receipt_commit
    assert outcome.planned_files == outcome.published_files == 1
    assert outcome.authored_files_changed and outcome.recovery_required
    assert (vault / "Notes/Opening.md").read_bytes() == b"incoming opening\n"
    assert user_state(vault)["index"] == before["index"]
    assert Operations().inspect_update_status(vault).status == "content_complete"
    marker = vault / ".git/brz2obsidian"
    (marker / "owner.json").unlink()
    (marker / "held").unlink()
    marker.rmdir()
    assert Operations().inspect_update_status(vault).status == "applied"


def _binary_link_case(*, payload_current=b"\x00authored"):
    from brz2obsidian.contracts import ExactContent, LinkOccurrenceChoice
    from brz2obsidian.obsidian import interpret_link_target, interpret_links
    from tests.reconciliation.test_attachments import (
        attachment_candidate,
        linked_attachment_request,
    )

    vault, source = fixture_case()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "Assets").mkdir()
    (source / "Assets").mkdir()
    (vault / "Notes").mkdir()
    (source / "Notes").mkdir()
    (vault / "Assets/data.bin").write_bytes(b"\x00original")
    (source / "Assets/data.bin").write_bytes(b"\x00original")
    facts = linked_attachment_request(payload_current=payload_current)
    old_document = facts.link_context.current_documents[0]
    (vault / "Notes/Owner.md").write_bytes(old_document.content.data)
    (source / "Notes/Owner.md").write_bytes(old_document.content.data)
    git(vault, "add", "Assets/data.bin", "Notes/Owner.md")
    git(vault, "commit", "-qm", "user baseline")
    operations = Operations()
    seeded = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=facts.incoming_identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert seeded.status == "captured"
    (vault / "Assets/data.bin").write_bytes(payload_current)
    (source / "Assets/data.bin").write_bytes(b"abc")
    offered = prepare_review(
        facts, preflight=operations.inspect_history(vault).admission.preflight
    )
    selection, candidate = attachment_candidate(facts, "both")
    changed_document = b"[[Assets/data.bin|Keep first]] and [Second edited alias](Assets/data%20%28incoming-ba7816bf%29.bin)"
    document = interpret_links(
        ExactContent(data=changed_document),
        document_id=old_document.document_id,
        source_path=old_document.source_path,
        path_mode="vault",
        targets=candidate.targets,
        target_facts=candidate.target_facts,
        inventory="complete",
    )
    choice = LinkOccurrenceChoice(
        document_id=old_document.document_id,
        occurrence_id=old_document.occurrences[1].occurrence_id,
        old=old_document.occurrences[1].meaning,
        replacement=b"[Second edited alias](Assets/data%20%28incoming-ba7816bf%29.bin)",
        selected=document.occurrences[1].meaning,
        expected_memberships=(),
        provenance="explicit_user",
    )
    selection = selection.model_copy(update={"link_choices": (choice,)})
    states = tuple(
        interpret_link_target(
            document.content,
            target_id="owner:note",
            existence="present",
            memberships=(),
        )
        if state.target_id == "owner:note"
        else state
        for state in candidate.target_facts
    )
    candidate = candidate.model_copy(
        update={"documents": (document,), "target_facts": states}
    )
    reviewed = resolve_review(
        offered,
        action(
            offered,
            domain="attachment",
            choice="both",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    ).plan
    assert reviewed.ready and reviewed.approvals[0].result is None
    before = user_state(vault)
    return vault, source, operations, reviewed, before, changed_document


def test_binary_both_and_literal_link_publish_two_selected_effects():
    vault, source, operations, reviewed, before, changed_document = _binary_link_case()

    outcome = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
    )

    assert outcome.status == "applied", (outcome.code, outcome.phase)
    assert outcome.planned_files == outcome.published_files == 2
    assert (vault / "Assets/data.bin").read_bytes() == b"\x00authored"
    assert (vault / "Assets/data (incoming-ba7816bf).bin").read_bytes() == b"abc"
    assert (vault / "Notes/Owner.md").read_bytes() == changed_document
    assert user_state(vault)["index"] == before["index"]
    checkpoint = operations.read_checkpoint(vault)
    assert [(row.path, row.size) for row in checkpoint.manifest.proposed] == [
        ("Assets/data (incoming-ba7816bf).bin", 3),
        ("Assets/data.bin", 9),
        ("Notes/Owner.md", len(changed_document)),
    ]


def test_partial_move_fault_reports_actual_new_asset_and_old_link_document():
    from brz2obsidian.publication.vault_replace import move_file

    vault, source, _, reviewed, before, changed_document = _binary_link_case()
    original_link = (vault / "Notes/Owner.md").read_bytes()

    class StopAfterFirstMove:
        calls = 0

        def move(self, stage, target, *, replace):
            move_file(stage, target, replace=replace)
            self.calls += 1
            if self.calls == 1:
                raise OSError("Injected stop after actual native transition")

        def remove(self, target, destination):
            raise AssertionError("No reviewed removal was selected")

    executor = StopAfterFirstMove()
    outcome = Operations(vault_executor=executor).apply_reviewed_update(
        vault,
        source,
        review=reviewed,
        source_binding=Operations().observe_reviewed_source(source, reviewed),
        vault_id="vault-one",
        import_id="import-one",
    )

    assert executor.calls == 1
    assert outcome.status == "incomplete" and outcome.recovery_required
    assert outcome.publication == "partial" and outcome.published_files == 1
    assert outcome.planned_files == 2 and outcome.intent_commit
    assert (vault / "Assets/data (incoming-ba7816bf).bin").read_bytes() == b"abc"
    assert (vault / "Assets/data.bin").read_bytes() == b"\x00authored"
    assert (vault / "Notes/Owner.md").read_bytes() == original_link
    assert (vault / "Notes/Owner.md").read_bytes() != changed_document
    assert user_state(vault)["index"] == before["index"]
    fresh = Operations().inspect_update_status(vault)
    assert fresh.status == "incomplete" and fresh.code == "partial_publication"
    assert fresh.operation_id == outcome.operation_id and fresh.published_files == 1
    assert Operations().inspect_history(vault).admission.status == "recovery_first"


def test_first_native_move_failure_reports_known_nonpublication():
    vault, source, operations, reviewed, before = _ready_case()

    class MoveFails:
        def move(self, stage, target, *, replace):
            assert stage.read_bytes() == b"incoming opening\n"
            assert target.read_bytes() == b"authored opening\r\n"
            assert replace
            raise OSError("Injected native rename failure")

        def remove(self, target, destination):
            raise AssertionError("No removal was selected")

    outcome = Operations(vault_executor=MoveFails()).apply_reviewed_update(
        vault,
        source,
        review=reviewed,
        source_binding=operations.observe_reviewed_source(source, reviewed),
        vault_id="vault-one",
        import_id="import-one",
    )

    assert outcome.status == "incomplete" and outcome.publication == "not_published"
    assert outcome.planned_files == 1 and outcome.published_files == 0
    assert not outcome.authored_files_changed and outcome.recovery_required
    assert outcome.intent_commit and not outcome.receipt_commit
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert user_state(vault)["index"] == before["index"]
    fresh = Operations().inspect_update_status(vault)
    assert fresh.status == "incomplete" and fresh.publication == "not_published"
    assert fresh.operation_id == outcome.operation_id


def test_ambiguous_intent_ref_and_failed_discovery_never_claim_prepared_only(
    monkeypatch,
):
    from brz2obsidian.publication.vault_history import _Git

    vault, source, operations, reviewed, before = _ready_case()
    original_call = _Git.call
    ambiguous = False

    def lose_intent_ack_and_discovery(self, *args, **kwargs):
        nonlocal ambiguous
        if ambiguous:
            raise OSError("Injected loss of Git observation after ref write")
        if args[0] == "update-ref" and "/operations/" in args[1]:
            original_call(self, *args, **kwargs)
            ambiguous = True
            raise OSError("Injected lost intent-ref acknowledgement")
        return original_call(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(_Git, "call", lose_intent_ack_and_discovery)
        outcome = _apply(
            operations,
            vault,
            source,
            review=reviewed,
            vault_id="vault-one",
            import_id="import-one",
        )

    assert outcome.status == "unknown" and outcome.recovery_required
    assert outcome.publication == "not_published" and outcome.history == "unknown"
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert user_state(vault)["index"] == before["index"]
    actual = Operations().inspect_update_status(vault)
    assert actual.status == "incomplete" and actual.intent_commit
    assert actual.publication == "not_published"


def test_real_move_with_unavailable_discovery_reports_unknown_publication(monkeypatch):
    from brz2obsidian.publication.vault_history import _Git
    from brz2obsidian.publication.vault_replace import move_file

    vault, source, operations, reviewed, before = _ready_case()
    original_call = _Git.call
    moved = False

    class LostAfterMove:
        def move(self, stage, target, *, replace):
            nonlocal moved
            move_file(stage, target, replace=replace)
            moved = True
            raise OSError("Injected loss after actual file transition")

        def directory(self, stage, target):
            raise AssertionError("Existing parent needs no new directory")

        def remove(self, target, destination):
            raise AssertionError("This review selects no removal")

    def lose_discovery(self, *args, **kwargs):
        if moved:
            raise OSError("Injected failure of recovery inspection")
        return original_call(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(_Git, "call", lose_discovery)
        outcome = Operations(vault_executor=LostAfterMove()).apply_reviewed_update(
            vault,
            source,
            review=reviewed,
            source_binding=operations.observe_reviewed_source(source, reviewed),
            vault_id="vault-one",
            import_id="import-one",
        )

    assert moved
    assert outcome.status == "unknown" and outcome.publication == "unknown"
    assert outcome.authored_files_changed is None and outcome.recovery_required
    assert outcome.intent_commit and not outcome.receipt_commit
    assert (vault / "Notes/Opening.md").read_bytes() == b"incoming opening\n"
    assert user_state(vault)["index"] == before["index"]
    actual = Operations().inspect_update_status(vault)
    assert actual.status == "content_complete" and actual.publication == "complete"


def test_terminal_ref_failure_retains_complete_bytes_and_result_checkpoint(monkeypatch):
    from brz2obsidian.publication.vault_history import _Git

    vault, source, operations, reviewed, before = _ready_case()
    original_call = _Git.call

    def reject_terminal_ref(self, *args, **kwargs):
        if (
            args[0] == "update-ref"
            and "/operations/" in args[1]
            and args[3] != "0" * 40
        ):
            raise OSError("Injected terminal ref failure")
        return original_call(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(_Git, "call", reject_terminal_ref)
        outcome = _apply(
            operations,
            vault,
            source,
            review=reviewed,
            vault_id="vault-one",
            import_id="import-one",
        )

    assert outcome.status == "content_complete" and outcome.recovery_required
    assert outcome.publication == "complete" and outcome.history == "result"
    assert outcome.result_commit and not outcome.receipt_commit
    assert (vault / "Notes/Opening.md").read_bytes() == b"incoming opening\n"
    assert user_state(vault)["index"] == before["index"]
    assert operations.inspect_history(vault).admission.status == "recovery_first"
    locator = json.loads((vault / ".brz2obsidian/locator.json").read_text())
    association = locator["association"]["association_id"]
    checkpoint_ref = f"refs/brz2obsidian/imports/{association}/checkpoints"
    assert (
        git(vault, "rev-parse", "--verify", checkpoint_ref).strip().decode()
        == outcome.result_commit
    )
    assert git(vault, "cat-file", "-t", outcome.result_commit).strip() == b"commit"
    fresh = Operations().inspect_update_status(vault)
    assert fresh.status == "content_complete" and fresh.recovery_required


def test_interrupted_child_after_real_move_is_discovered_in_fresh_process():
    from brz2obsidian.application.vault_update_contracts import VaultApplyResult

    vault, source, _, reviewed, before, changed_document = _binary_link_case()
    original_link = (vault / "Notes/Owner.md").read_bytes()
    review_path = vault.parent / "approved-review.json"
    review_path.write_text(reviewed.model_dump_json(), encoding="utf-8")
    interrupted = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import os
import sys
from pathlib import Path
from brz2obsidian.application.operations import Operations
from brz2obsidian.contracts import ReviewPlan
from brz2obsidian.publication.vault_replace import move_file

class StopAfterMove:
    def move(self, stage, target, *, replace):
        move_file(stage, target, replace=replace)
        os._exit(73)

    def remove(self, target, destination):
        os._exit(74)

review = ReviewPlan.model_validate_json(Path(sys.argv[3]).read_bytes())
Operations(vault_executor=StopAfterMove()).apply_reviewed_update(
    sys.argv[1], sys.argv[2], review=review,
    source_binding=Operations().observe_reviewed_source(sys.argv[2], review),
    vault_id="vault-one", import_id="import-one",
)
os._exit(75)
""",
            str(vault),
            str(source),
            str(review_path),
        ],
        capture_output=True,
        timeout=90,
        check=False,
    )
    assert interrupted.returncode == 73, interrupted.stderr.decode(errors="replace")
    assert (vault / "Assets/data (incoming-ba7816bf).bin").read_bytes() == b"abc"
    assert (vault / "Notes/Owner.md").read_bytes() == original_link
    assert (vault / "Notes/Owner.md").read_bytes() != changed_document
    assert user_state(vault)["index"] == before["index"]

    inspected = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from brz2obsidian.application.operations import Operations; "
                "print(Operations().inspect_update_status(sys.argv[1]).model_dump_json())"
            ),
            str(vault),
        ],
        capture_output=True,
        timeout=60,
        check=True,
    )
    fresh = VaultApplyResult.model_validate_json(inspected.stdout)
    assert fresh.status == "incomplete" and fresh.code == "partial_publication"
    assert fresh.publication == "partial" and fresh.published_files == 1
    assert fresh.planned_files == 2 and fresh.recovery_required and fresh.intent_commit
    assert Operations().inspect_history(vault).admission.status == "recovery_first"


def _restored_note_case():
    from tests.reconciliation.test_absence import facts_for

    vault, source = fixture_case()
    git(vault, "init", "-q")
    (vault / "Unrelated.md").write_bytes(b"user remains\n")
    git(vault, "add", "Unrelated.md")
    git(vault, "commit", "-qm", "user baseline")
    (source / "Notes").mkdir()
    (source / "Notes/Opening.md").write_bytes(b"old")
    facts = with_review_links(
        facts_for(existence="absent", original=b"old", incoming=b"new note\n")
    )
    operations = Operations()
    seeded = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=facts.incoming_identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert seeded.status == "captured"
    (source / "Notes/Opening.md").write_bytes(b"new note\n")
    offered = prepare_review(
        facts, preflight=operations.inspect_history(vault).admission.preflight
    )
    candidate = inspect_text_candidate(
        ExactContent(data=b"new note\n"),
        identity=facts.identity_inventory[0].identity,
        target=facts.subjects[0].source_target,
        output_format=7,
        source_path="Notes/Opening.md",
        document_id="review:opening",
        path_mode="vault",
        link_targets=(),
        link_target_facts=(),
        link_inventory="complete",
    )
    reviewed = resolve_review(
        offered,
        action(
            offered,
            domain="restoration",
            choice="restore_incoming",
            candidate=candidate,
        ),
    ).plan
    assert reviewed.ready
    before = user_state(vault)
    return vault, source, operations, reviewed, before


def _renamed_case(*, local_name="Local.md"):
    from tests.reconciliation.test_identity import inventory_item

    vault, source = fixture_case()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "Notes").mkdir()
    (vault / "Notes/Opening.md").write_bytes(b"base\r\n")
    (vault / local_name).write_bytes(b"user \xff\n")
    git(vault, "add", "Notes/Opening.md", local_name)
    git(vault, "commit", "-qm", "user baseline")
    (source / "Notes").mkdir()
    (source / "Notes/Opening.md").write_bytes(b"base\r\n")
    facts = request(original=b"base\r\n", current=b"base\r\n", incoming=b"new\r\n")
    facts = with_review_links(
        facts.model_copy(
            update={
                "identity_inventory": (
                    inventory_item(
                        "moved", "entry:opening", "Authored/Name.md", b"base\r\n"
                    ),
                ),
            }
        )
    )
    operations = Operations()
    seeded = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=facts.incoming_identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert seeded.status == "captured"
    (vault / "Authored").mkdir()
    git(vault, "mv", "Notes/Opening.md", "Authored/Name.md")
    (source / "Notes/Opening.md").write_bytes(b"new\r\n")
    offered = prepare_review(
        facts, preflight=operations.inspect_history(vault).admission.preflight
    )
    renamed = resolve_review(
        offered, action(offered, domain="rename", choice="source_path")
    )
    reviewed = resolve_review(
        renamed.plan, action(renamed.plan, decision_id="content:after-rename")
    ).plan
    assert reviewed.ready
    before = user_state(vault)
    return vault, source, operations, reviewed, before


def test_approved_rename_publishes_new_path_and_only_removes_displaced_note():
    vault, source, operations, reviewed, before = _renamed_case()

    outcome = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
    )

    assert outcome.status == "applied", (outcome.code, outcome.phase)
    assert outcome.planned_files == outcome.published_files == 2
    assert not (vault / "Authored/Name.md").exists()
    assert (vault / "Notes/Opening.md").read_bytes() == b"new\r\n"
    assert (vault / "Local.md").read_bytes() == b"user \xff\n"
    after = user_state(vault)
    assert after["index"] == before["index"]
    assert after["head"] == before["head"]
    assert after["stages"] == before["stages"]
    assert Operations().inspect_update_status(vault).status == "applied"


def test_reviewed_format_transition_uses_retained_baseline_identity():
    vault, source = fixture_case()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "Notes").mkdir()
    (vault / "Notes/Opening.md").write_bytes(b"old generated\r\n")
    git(vault, "add", "Notes/Opening.md")
    git(vault, "commit", "-qm", "user baseline")
    (source / "Notes").mkdir()
    (source / "Notes/Opening.md").write_bytes(b"old generated\r\n")
    facts = request(
        original=b"old generated\r\n",
        current=b"authored \xff\r\n",
        incoming=b"target generated\n",
    )
    baseline_identity = facts.incoming_identity.model_copy(update={"output_format": 6})
    baseline = facts.format_operation.established_baseline.model_copy(
        update={"identity": baseline_identity}
    )
    facts = with_review_links(
        facts.model_copy(
            update={
                "baseline_identity": baseline_identity,
                "format_operation": facts.format_operation.model_copy(
                    update={
                        "kind": "format_transition",
                        "target_source_version": "source:a",
                        "established_baseline": baseline,
                    }
                ),
            }
        ),
        opaque_link_free=True,
    )
    operations = Operations()
    seeded = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=baseline_identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert seeded.status == "captured"
    (vault / "Notes/Opening.md").write_bytes(b"authored \xff\r\n")
    (source / "Notes/Opening.md").write_bytes(b"target generated\n")
    offered = prepare_review(
        facts, preflight=operations.inspect_history(vault).admission.preflight
    )
    candidate = inspect_text_candidate(
        ExactContent(data=b"target generated\n"),
        identity=facts.identity_inventory[0].identity,
        target=facts.subjects[0].source_target,
        output_format=7,
        source_path="Notes/Opening.md",
        document_id="review:format",
        path_mode="vault",
        link_targets=(),
        link_target_facts=(),
        link_inventory="complete",
    )
    accepted = resolve_review(
        offered,
        action(offered, domain="format", choice="incoming", candidate=candidate),
    )
    assert accepted.status == "accepted" and accepted.plan.ready
    before = user_state(vault)

    outcome = _apply(
        operations,
        vault,
        source,
        review=accepted.plan,
        vault_id="vault-one",
        import_id="import-one",
    )

    assert outcome.status == "applied", (outcome.code, outcome.phase)
    assert (vault / "Notes/Opening.md").read_bytes() == b"target generated\n"
    assert user_state(vault)["index"] == before["index"]
    result = operations.read_checkpoint(vault)
    assert (
        result.status == "valid" and result.manifest.identity == facts.incoming_identity
    )


def test_restored_note_in_new_parent_publishes_directory_before_file():
    from brz2obsidian.publication.vault_replace import move_file

    vault, source, operations, reviewed, before = _restored_note_case()
    transitions = []

    class ObservingExecutor:
        def directory(self, stage, target):
            assert stage.is_dir() and not target.exists()
            move_file(stage, target, replace=False)
            transitions.append(("directory", target.relative_to(vault).as_posix()))

        def move(self, stage, target, *, replace):
            assert target.parent.is_dir() and not target.exists() and not replace
            move_file(stage, target, replace=replace)
            transitions.append(("file", target.relative_to(vault).as_posix()))

        def remove(self, target, destination):
            raise AssertionError("Restoration did not select a removal")

    outcome = Operations(vault_executor=ObservingExecutor()).apply_reviewed_update(
        vault,
        source,
        review=reviewed,
        source_binding=operations.observe_reviewed_source(source, reviewed),
        vault_id="vault-one",
        import_id="import-one",
    )
    assert outcome.status == "applied", (outcome.code, outcome.phase)
    assert transitions == [
        ("directory", "Notes"),
        ("file", "Notes/Opening.md"),
    ]
    assert (vault / "Notes/Opening.md").read_bytes() == b"new note\n"
    assert (vault / "Unrelated.md").read_bytes() == b"user remains\n"
    assert user_state(vault)["index"] == before["index"]


def test_interrupted_new_parent_move_is_partial_authored_publication():
    from brz2obsidian.publication.vault_replace import move_file

    vault, source, operations, reviewed, before = _restored_note_case()

    class StopAfterDirectory:
        def directory(self, stage, target):
            move_file(stage, target, replace=False)
            raise OSError("Injected stop after actual parent move")

        def move(self, stage, target, *, replace):
            raise AssertionError("No file was published")

        def remove(self, target, destination):
            raise AssertionError("No file was removed")

    outcome = Operations(vault_executor=StopAfterDirectory()).apply_reviewed_update(
        vault,
        source,
        review=reviewed,
        source_binding=operations.observe_reviewed_source(source, reviewed),
        vault_id="vault-one",
        import_id="import-one",
    )

    assert outcome.status == "incomplete" and outcome.publication == "partial"
    assert outcome.published_files == 0 and outcome.authored_files_changed
    assert outcome.intent_commit and outcome.recovery_required
    assert (vault / "Notes").is_dir()
    assert not (vault / "Notes/Opening.md").exists()
    assert (vault / "Unrelated.md").read_bytes() == b"user remains\n"
    assert user_state(vault)["index"] == before["index"]
    fresh = Operations().inspect_update_status(vault)
    assert fresh.status == "incomplete" and fresh.publication == "partial"
    assert fresh.published_files == 0 and fresh.authored_files_changed


def test_ready_attachment_refuses_false_current_link_document_before_publication():
    from tests.reconciliation.test_attachments import (
        attachment_candidate,
        linked_attachment_request,
    )

    vault, source = fixture_case()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "Assets").mkdir()
    (source / "Assets").mkdir()
    (vault / "Notes").mkdir()
    (source / "Notes").mkdir()
    (vault / "Assets/data.bin").write_bytes(b"\x00original")
    (source / "Assets/data.bin").write_bytes(b"\x00original")
    physical_document = b"actual unrelated authored note\n"
    (vault / "Notes/Owner.md").write_bytes(physical_document)
    (source / "Notes/Owner.md").write_bytes(physical_document)
    git(vault, "add", "Assets/data.bin", "Notes/Owner.md")
    git(vault, "commit", "-qm", "user baseline")
    facts = linked_attachment_request()
    operations = Operations()
    seeded = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=facts.incoming_identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert seeded.status == "captured"
    (vault / "Assets/data.bin").write_bytes(b"\x00authored")
    (source / "Assets/data.bin").write_bytes(b"abc")
    offered = prepare_review(
        facts, preflight=operations.inspect_history(vault).admission.preflight
    )
    selection, candidate = attachment_candidate(facts, "both")
    reviewed = resolve_review(
        offered,
        action(
            offered,
            domain="attachment",
            choice="both",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    ).plan
    assert reviewed.ready
    before = user_state(vault)

    outcome = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
    )

    assert outcome.status == "refused" and outcome.code == "review_inputs_changed"
    assert outcome.intent_commit is None and not outcome.authored_files_changed
    assert not (vault / "Assets/data (incoming-ba7816bf).bin").exists()
    assert (vault / "Notes/Owner.md").read_bytes() == physical_document
    assert user_state(vault)["index"] == before["index"]
    assert operations.read_checkpoint(vault).locator.commit == seeded.commit
