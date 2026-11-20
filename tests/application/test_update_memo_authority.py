"""A proved first local memo keeps its actual parent's review authority."""

import hashlib
import json
import tempfile
from collections import namedtuple
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_subjects import review_subjects
from brz2obsidian.contracts import CurrentContent, ExactContent, ReviewPlan
from brz2obsidian.core import (
    load_review,
    prepare_review,
    resolve_review,
    resume_review,
    save_review,
)
from brz2obsidian.publication import vault_history
from brz2obsidian.publication.vault_native import verify_directory
from tests.application.test_attachment_cleanup_application import (
    cleanup_asset_action,
    literal_cleanup_case,
)
from tests.application.test_update_lifecycle_admission import NOTE, note
from tests.application.test_vault_admission import git
from tests.application.test_vault_recovery_process import _AFTER, _two_note_case
from tests.reconciliation.test_resolution import action, with_review_links


def test_first_memo_over_completed_source_result_keeps_choices_after_prior_policy_edit():
    vault, source, plan_path, _, _ = _two_note_case()
    operations = Operations()
    prior = ReviewPlan.model_validate_json(plan_path.read_bytes())
    applied = operations.apply_reviewed_update(
        vault,
        source,
        review=prior,
        source_binding=operations.observe_reviewed_source(source, prior),
        vault_id="vault-one",
        import_id="import-one",
    )
    assert applied.status == "applied", applied.code
    # This topology change precedes review; the memo must prove its OWN fresh
    # policy, without pretending the publication's old policy still applies.
    (vault / "Manual.md").write_text("Independent authored note.\n", encoding="utf-8")
    for path, raw in _AFTER.items():
        (vault / path).write_bytes(raw + b"local prose\n")
    currents = {
        subject.path: CurrentContent(
            existence="present",
            path=subject.path,
            content=ExactContent(data=(vault / subject.path).read_bytes()),
        )
        for subject in prior.facts.subjects
    }
    facts = with_review_links(
        prior.facts.model_copy(
            update={
                "link_context": None,
                "identity_inventory": tuple(
                    entry.model_copy(update={"current": currents[entry.current.path]})
                    for entry in prior.facts.identity_inventory
                ),
                "subjects": tuple(
                    subject.model_copy(update={"current": currents[subject.path]})
                    for subject in prior.facts.subjects
                ),
            }
        )
    )
    (vault / ".gitattributes").write_bytes(b"Notes/*.md text eol=lf\n")
    subjects = review_subjects(facts)
    observed = operations.inspect_history(vault, subjects=subjects)
    assert observed.status == "intact"
    assert observed.admission.preflight.consents
    assert all(
        row.kind == "storage" and row.requirement == "required"
        for row in observed.admission.preflight.consents
    )
    reviewed = prepare_review(facts, preflight=observed.admission.preflight)
    change = next(
        row for row in reviewed.proposal.changes if row.path == "Notes/Opening.md"
    )
    selected = resolve_review(
        reviewed,
        action(reviewed, change, choice="current", decision_id="retain:opening"),
    )
    assert selected.status == "accepted", selected.code
    reviewed = selected.plan
    assert not reviewed.ready
    locator_file = vault / ".brz2obsidian/locator.json"
    locator_before = locator_file.read_bytes()

    def capture(plan, admission):
        return operations.capture_checkpoint(
            vault,
            source,
            vault_id="vault-one",
            import_id="import-one",
            identity=facts.incoming_identity,
            admission=admission,
            subjects=subjects,
            review=plan,
        )

    # Historical publication permission is never permission for this new policy.
    pending = capture(reviewed, observed.admission)
    assert pending.status == "refused" and pending.code == "scoped_review_required"
    assert locator_file.read_bytes() == locator_before
    requirement = next(row for row in reviewed.requirements if row.domain == "storage")
    declined = resolve_review(
        reviewed,
        action(
            reviewed,
            domain="storage",
            choice="decline",
            decision_id="decline:current-policy",
            change_id=requirement.change_id,
            reviewed_assumptions=requirement.assumptions,
        ),
    )
    assert declined.status == "accepted" and not declined.plan.ready
    refusal = capture(declined.plan, observed.admission)
    assert refusal.status == "refused" and refusal.code == "scoped_review_required"
    assert locator_file.read_bytes() == locator_before
    while any(row.domain == "storage" for row in reviewed.requirements):
        requirement = next(
            row for row in reviewed.requirements if row.domain == "storage"
        )
        accepted = resolve_review(
            reviewed,
            action(
                reviewed,
                domain="storage",
                choice="accept",
                decision_id="accept:" + requirement.requirement_id,
                change_id=requirement.change_id,
                reviewed_assumptions=requirement.assumptions,
            ),
        )
        assert accepted.status == "accepted", accepted.code
        reviewed = accepted.plan
    assert reviewed.consents and not reviewed.ready
    before = {
        str(path.relative_to(vault)): path.read_bytes()
        for path in vault.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and ".brz2obsidian" not in path.parts
    }
    saved = capture(reviewed, observed.admission)
    assert saved.status == "captured", saved.code
    fresh = Operations().inspect_history(vault, subjects=subjects)
    assert fresh.status == "intact" and fresh.admission.status == "supported"
    assert (
        fresh.checkpoint.manifest.policy_fingerprint
        != observed.checkpoint.manifest.policy_fingerprint
    )
    assert (
        fresh.admission.preflight.state_fingerprint
        == reviewed.preflight.state_fingerprint
    )
    resumed = resume_review(
        fresh.checkpoint.review,
        facts.model_copy(update={"generation": facts.generation + 1}),
        preflight=fresh.admission.preflight,
    )
    assert resumed.status == "resumed", resumed.code
    assert resumed.plan.approvals == reviewed.approvals
    assert resumed.plan.consents == reviewed.consents
    assert not resumed.plan.ready
    closing = next(
        row for row in resumed.plan.proposal.changes if row.path == "Notes/Closing.md"
    )
    chosen = resolve_review(
        resumed.plan,
        action(resumed.plan, closing, choice="current", decision_id="retain:closing"),
    )
    assert chosen.status == "accepted" and not chosen.plan.ready
    second_review = chosen.plan
    assert any(row.domain == "storage" for row in second_review.requirements)
    while any(row.domain == "storage" for row in second_review.requirements):
        requirement = next(
            row for row in second_review.requirements if row.domain == "storage"
        )
        accepted = resolve_review(
            second_review,
            action(
                second_review,
                domain="storage",
                choice="accept",
                decision_id="accept:second:" + requirement.requirement_id,
                change_id=requirement.change_id,
                reviewed_assumptions=requirement.assumptions,
            ),
        )
        assert accepted.status == "accepted", accepted.code
        second_review = accepted.plan
    assert second_review.ready
    second = capture(second_review, fresh.admission)
    assert second.status == "captured", second.code
    after_second = Operations().inspect_history(vault, subjects=subjects)
    assert (
        after_second.admission.preflight.state_fingerprint
        == reviewed.preflight.state_fingerprint
    )
    again = resume_review(
        after_second.checkpoint.review,
        facts.model_copy(update={"generation": facts.generation + 2}),
        preflight=after_second.admission.preflight,
    )
    assert after_second.checkpoint.review.ready is False
    assert again.status == "resumed" and again.plan.ready
    assert again.plan.approvals == second_review.approvals
    assert again.plan.consents == second_review.consents
    assert before == {
        str(path.relative_to(vault)): path.read_bytes()
        for path in vault.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and ".brz2obsidian" not in path.parts
    }
    # A later policy edit needs fresh permission; the old grant cannot authorize it.
    (vault / ".gitattributes").write_bytes(b"Notes/*.md text eol=crlf\n")
    changed = Operations().inspect_history(vault, subjects=subjects)
    assert changed.admission.status == "supported"
    assert (
        changed.admission.preflight.state_fingerprint
        != reviewed.preflight.state_fingerprint
    )
    assert changed.admission.preflight.consents != reviewed.preflight.consents
    stale = resume_review(
        after_second.checkpoint.review,
        facts.model_copy(update={"generation": facts.generation + 2}),
        preflight=changed.admission.preflight,
    )
    assert stale.status == "resumed" and not stale.plan.ready
    assert any(row.domain == "storage" for row in stale.plan.requirements)
    assert not stale.plan.consents


def test_first_local_memo_keeps_proved_result_parent_and_original_remove_decision(
    monkeypatch,
):
    owned = Path(tempfile.mkdtemp(prefix="brz2obsidian-285-memo-"))
    marker = {"owner": uuid4().hex, "root": str(owned.resolve())}
    (owned / ".fixture-owner.json").write_text(json.dumps(marker))
    case = literal_cleanup_case(owned, independent_keep=True, output_format=8)
    vault = case.vault
    git(vault, "init", "-q")
    git(vault, "add", "--all")
    git(vault, "commit", "-qm", "Independent authored fixture")
    association = case.history.checkpoint.locator.association.model_copy(
        update={
            "vault_anchor": verify_directory(vault),
            "git_anchor": verify_directory(vault / ".git"),
        }
    )
    parent = case.history.checkpoint.locator.model_copy(
        update={
            "association": association,
            "generation": 3,
            "commit": "b" * 40,
        }
    )
    # With a LOCAL review tip the validated reader computes memo fingerprints
    # for all ancestors, including this RESULT; None is not its actual shape.
    # The controlled native reader declares a common context over already
    # validated metadata. Runtime graph/manifest validation remains native-owned.
    fields = tuple(
        dict.fromkeys(
            vault_history._CheckpointRole._fields + ("review_context_fingerprint",)
        )
    )
    ContextRole = namedtuple("ContextRole", fields)
    source_inventory = tuple(
        {
            "path": path,
            "mode": "100644",
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "object_id": hashlib.sha1(
                b"blob " + str(len(raw)).encode() + b"\x00" + raw
            ).hexdigest(),
        }
        for path, raw in sorted(case.retained.items())
    )
    context = {
        "association": association.model_dump(mode="json"),
        "identity": case.history.checkpoint.manifest.identity.model_dump(mode="json"),
        "source": source_inventory,
        "recovery_gaps": (),
        "policy_fingerprint": "1" * 64,
        "policy_continuity_fingerprint": "2" * 64,
    }

    def projected(role, *, proposed=(), **changes):
        declared = context | changes
        proof = hashlib.sha256(
            json.dumps(declared, sort_keys=True).encode()
        ).hexdigest()
        if (
            role.boundary not in ("result", "local")
            or role.boundary == "local"
            and proposed
        ):
            proof = None
        return ContextRole(**(role._asdict() | {"review_context_fingerprint": proof}))

    role = vault_history._CheckpointRole(
        parent.commit,
        None,
        parent.generation,
        "result",
        None,
        None,
        None,
        None,
        None,
        "e" * 64,
    )
    role = projected(role)
    active = {"locator": parent, "roles": (role,)}
    metadata = vault / ".brz2obsidian"
    metadata.mkdir()
    locator_file = metadata / "locator.json"
    locator_file.write_text(parent.model_dump_json())

    def read_validated(root, git_reader, **kwargs):
        assert Path(root) == vault
        kwargs["checkpoint_roles"].extend(active["roles"])
        return SimpleNamespace(status="valid", locator=active["locator"])

    monkeypatch.setattr(vault_history, "_read", read_validated)
    before = Operations().inspect_vault(vault)
    assert before.status == "supported" and before.preflight.operation_status == "idle"
    case.history.admission.preflight = before.preflight
    case.history.checkpoint.locator = parent
    cleanup_result = case.operations.prepare_attachment_cleanup(vault)
    assert cleanup_result.status == "prepared_review", cleanup_result
    assert cleanup_result.preparation is not None, cleanup_result
    prepared = cleanup_result.preparation
    for item, choice in (("keep-asset", "current"), ("remove-asset", "remove")):
        selected = case.operations.resolve_update(
            prepared,
            cleanup_asset_action(
                prepared.review,
                item,
                choice,
                document_edits={
                    NOTE: note("Authored ."),
                    "Manual.md": b"Manual . `[[Assets/remove.bin]]`\r\n",
                }
                if choice == "remove"
                else None,
            ),
        )
        assert selected.code == "accepted"
        prepared = selected.preparation
    assert selected.ready
    original_ids = tuple(row.decision_id for row in prepared.review.approvals)
    assert "cleanup:remove-asset" in original_ids
    saved = save_review(prepared.review)
    loaded = load_review(saved.record.model_dump_json())
    assert loaded.status == "loaded" and not loaded.loaded.ready
    local = parent.model_copy(update={"commit": "c" * 40, "generation": 4})
    memo = vault_history._CheckpointRole(
        local.commit,
        parent.commit,
        local.generation,
        "local",
        None,
        None,
        None,
        None,
        None,
        "f" * 64,
        before.preflight.state_fingerprint,
    )
    memo = projected(memo)
    active.update(locator=local, roles=(memo, role))
    locator_file.write_text(local.model_dump_json())
    after = Operations().inspect_vault(vault)
    assert after.status == "supported"
    assert after.preflight == before.preflight
    resumed = resume_review(
        loaded.loaded, prepared.review.facts, preflight=after.preflight
    )
    assert resumed.status == "resumed" and resumed.ready
    assert tuple(row.decision_id for row in resumed.plan.approvals) == original_ids
    removed = next(
        row
        for row in resumed.plan.approvals
        if row.decision_id == "cleanup:remove-asset"
    )
    assert removed.attachment_selection.choice == "remove"
    assert all(
        row.replacement == b"" for row in removed.attachment_selection.link_choices
    )

    for invalid in (
        memo._replace(previous="d" * 40),
        memo._replace(review_parent_fingerprint="foreign-history"),
        memo._replace(operation_intent_commit="d" * 40),
        memo._replace(generation=5),
        projected(memo, policy_fingerprint="3" * 64),
        projected(memo, policy_continuity_fingerprint="4" * 64),
        projected(memo, source=()),
        projected(memo, proposed=("new-output",)),
        memo._replace(review_context_fingerprint="invalid"),
    ):
        active["roles"] = (invalid, role)
        refused = Operations().inspect_vault(vault)
        assert refused.preflight.state_fingerprint != before.preflight.state_fingerprint
    active["roles"] = (memo, role)
    # Physical current/link changes still retire the relevant original decision.
    case.history.checkpoint.locator = local
    case.history.admission.preflight = after.preflight
    (vault / "Manual.md").write_bytes(
        b"New authored reference [[Assets/remove.bin]].\r\n"
    )
    changed = case.operations.refresh_update(
        prepared.model_copy(update={"locator": local})
    )
    assert not changed.ready
    assert "cleanup:remove-asset" not in {
        row.decision_id for row in changed.preparation.review.approvals
    }
