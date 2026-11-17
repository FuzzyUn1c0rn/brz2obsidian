"""Native storage context never supplies originals, policy grants or readiness."""

import hashlib
import json

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_subjects import review_subjects
from brz2obsidian.contracts import ContentVersion, SourceIdentity
from brz2obsidian.core import prepare_review, resolve_review, resume_review
from tests.application.test_format_transition_native import user_git_state
from tests.application.test_onboarding import owned_case
from tests.application.test_update_lifecycle import git
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, with_review_links


def saved_onboarding():
    root = owned_case()
    vault, source = root / "vault", root / "source"
    for directory, raw in (
        (vault, b"Exact authored bytes.\r\n"),
        (source, b"incoming\n"),
    ):
        (directory / "Notes").mkdir(parents=True)
        (directory / "Notes/Opening.md").write_bytes(raw)
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    git(vault, "add", "Notes/Opening.md")
    git(vault, "commit", "-qm", "Independent authored history")
    facts = request(current=b"Exact authored bytes.\r\n")
    facts = with_review_links(
        facts.model_copy(
            update={
                "incoming_identity": facts.incoming_identity.model_copy(
                    update={"output_format": 8}
                ),
                "subjects": (
                    facts.subjects[0].model_copy(
                        update={
                            "baseline": ContentVersion(
                                status="unknown", content=None, unavailable_digest=None
                            )
                        }
                    ),
                ),
                "format_operation": facts.format_operation.model_copy(
                    update={
                        "kind": "onboarding",
                        "recorded_generation": "unavailable",
                        "baseline_source_version": None,
                        "established_baseline": None,
                    }
                ),
            }
        )
    )
    operations = Operations()
    absent = operations.inspect_history(vault, new_operation="format_transition")
    assert absent.status == "absent"
    assert absent.admission.preflight.state_status == "absent"
    plan = prepare_review(facts, preflight=absent.admission.preflight)
    kept = resolve_review(
        plan,
        action(plan, domain="format", choice="current", decision_id="keep-unknown"),
    )
    assert kept.status == "accepted" and kept.plan.ready
    observed = SourceIdentity(
        source_id=facts.incoming_identity.collection_id,
        module_id=facts.incoming_identity.module_id,
        module_version="1",
        format_version="test/1",
        source_sha256=hashlib.sha256(b"incoming\n").hexdigest(),
        snapshot_digest="source:b",
    )
    saved = operations.capture_checkpoint(
        vault,
        source,
        vault_id="context-vault",
        import_id="context-import",
        identity=facts.baseline_identity,
        admission=absent.admission,
        review=kept.plan,
        source_binding=operations.observe_reviewed_source(source, kept.plan),
        observed_source=observed,
    )
    assert saved.status == "captured", saved.code
    return operations, vault, source, facts, kept.plan


def test_new_format_context_requires_real_history_and_keeps_onboarding_replay():
    operations, vault, _, facts, onboarding = saved_onboarding()
    before = user_git_state(vault)
    default = operations.inspect_history(vault)
    physical = operations.inspect_history(vault, new_operation="format_transition")
    assert default.checkpoint.locator == physical.checkpoint.locator
    assert default.admission.preflight.state_status == "absent"
    assert physical.admission.preflight.state_status == "supported"
    assert (
        physical.admission.preflight.state_schema == "brz2obsidian.checkpoint-manifest"
    )
    assert physical.admission.preflight.state_version == 1
    assert physical.admission.preflight.consents == ()
    assert physical.admission.preflight.state_fingerprint != (
        default.admission.preflight.state_fingerprint
    )
    replayed = resume_review(
        default.checkpoint.review, facts, preflight=default.admission.preflight
    )
    assert replayed.status == "resumed"
    assert replayed.plan.approvals == onboarding.approvals
    assert replayed.plan.facts.subjects[0].baseline.content is None
    assert replayed.plan.facts.subjects[0].baseline.status == "unknown"
    with pytest.raises(ValueError):
        operations.inspect_history(vault, new_operation="source_update")

    locator = vault / ".brz2obsidian/locator.json"
    original = locator.read_bytes()
    foreign = json.loads(original)
    foreign["association"]["collection_id"] = "foreign:collection"
    try:
        locator.write_text(json.dumps(foreign), encoding="utf-8")
        refused = operations.inspect_history(vault, new_operation="format_transition")
        assert refused.status == "unavailable"
        assert refused.admission.status != "supported"
    finally:
        locator.write_bytes(original)
    with operations.inspect_update_inputs(vault) as reader:
        ref = "refs/heads/context-currentness-probe"
        git(vault, "update-ref", ref, physical.checkpoint.locator.commit)
        try:
            with pytest.raises(OSError):
                reader.inspect(subjects=(), new_operation="format_transition")
        finally:
            git(vault, "update-ref", "-d", ref)
    assert (vault / "Notes/Opening.md").read_bytes() == b"Exact authored bytes.\r\n"
    assert user_git_state(vault) == before


def test_format_parent_requires_its_own_current_storage_consent():
    operations, vault, source, onboarding, _ = saved_onboarding()
    before = user_git_state(vault)
    (vault / ".gitattributes").write_bytes(b"Notes/*.md text eol=lf\n")
    facts = onboarding.model_copy(
        update={
            "proposal_id": "new-format-context",
            "format_operation": onboarding.format_operation.model_copy(
                update={
                    "kind": "format_transition",
                    "baseline_source_version": "source:b",
                }
            ),
        }
    )
    subjects = review_subjects(facts)
    history = operations.inspect_history(
        vault, subjects=subjects, new_operation="format_transition"
    )
    assert history.admission.status == "supported"
    assert history.admission.preflight.state_status == "supported"
    assert history.admission.preflight.consents
    assert all(
        c.kind == "storage" and c.requirement == "required"
        for c in history.admission.preflight.consents
    )
    prepared = prepare_review(facts, preflight=history.admission.preflight)
    kept = resolve_review(
        prepared,
        action(
            prepared, domain="format", choice="current", decision_id="format-current"
        ),
    )
    assert kept.status == "accepted" and not kept.plan.ready
    pending = kept.plan
    locator = (vault / ".brz2obsidian/locator.json").read_bytes()

    def capture(plan):
        return operations.capture_checkpoint(
            vault,
            source,
            vault_id="context-vault",
            import_id="context-import",
            identity=facts.baseline_identity,
            admission=history.admission,
            subjects=subjects,
            review=plan,
            review_source=source,
            source_binding=operations.observe_reviewed_source(source, plan),
        )

    denied = capture(pending)
    assert denied.status == "refused" and denied.code == "scoped_review_required"
    required = next(r for r in pending.requirements if r.domain == "storage")
    declined = resolve_review(
        pending,
        action(
            pending,
            domain="storage",
            choice="decline",
            decision_id="decline-new-policy",
            change_id=required.change_id,
            reviewed_assumptions=required.assumptions,
        ),
    )
    assert declined.status == "accepted" and not declined.plan.ready
    rejected = capture(declined.plan)
    assert rejected.status == "refused" and rejected.code == "scoped_review_required"
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator
    accepted = resolve_review(
        pending,
        action(
            pending,
            domain="storage",
            choice="accept",
            decision_id="accept-own-new-policy",
            change_id=required.change_id,
            reviewed_assumptions=required.assumptions,
        ),
    )
    assert accepted.status == "accepted" and accepted.plan.ready
    stored = capture(accepted.plan)
    assert stored.status == "captured", stored.code
    fresh = operations.inspect_history(vault, subjects=subjects)
    assert fresh.admission.preflight == accepted.plan.preflight
    resumed = resume_review(
        fresh.checkpoint.review, facts, preflight=fresh.admission.preflight
    )
    assert resumed.status == "resumed" and resumed.plan.ready
    assert resumed.plan.consents == accepted.plan.consents
    assert resumed.plan.facts.subjects[0].baseline.content is None
    (vault / ".gitattributes").write_bytes(b"Notes/*.md text eol=crlf\n")
    changed = operations.inspect_history(vault, subjects=subjects)
    stale = resume_review(
        fresh.checkpoint.review,
        facts.model_copy(update={"generation": facts.generation + 1}),
        preflight=changed.admission.preflight,
    )
    assert stale.status == "resumed" and not stale.plan.ready
    assert any(r.domain == "storage" for r in stale.plan.requirements)
    assert stale.plan.consents == ()
    assert (vault / "Notes/Opening.md").read_bytes() == b"Exact authored bytes.\r\n"
    assert user_git_state(vault) == before
