"""First LOCAL history never converts unknown or ordinary review into absence."""

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.core import prepare_review
from tests.application.test_onboarding import owned_case
from tests.application.test_vault_checkpoints import git
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import with_review_links


@pytest.mark.parametrize("shape", ("non_onboarding", "unknown_state"))
def test_first_local_requires_exact_onboarding_absence_shape(shape):
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
    operations = Operations()
    before = operations.inspect_history(vault)
    assert (
        before.status == "absent"
        and before.admission.preflight.state_status == "absent"
    )
    facts = request(current=b"Exact authored bytes.\r\n")
    preflight = before.admission.preflight
    if shape == "unknown_state":
        facts = facts.model_copy(
            update={
                "format_operation": facts.format_operation.model_copy(
                    update={
                        "kind": "onboarding",
                        "target_source_version": "source:a",
                    }
                )
            }
        )
        preflight = preflight.model_copy(update={"state_status": "unknown"})
    facts = with_review_links(facts)
    plan = prepare_review(facts, preflight=preflight)
    assert not plan.ready
    captured = operations.capture_checkpoint(
        vault,
        source,
        vault_id="new-vault",
        import_id="new-import",
        identity=facts.incoming_identity,
        admission=before.admission,
        review=plan,
    )
    assert captured.status == "captured", captured
    current = operations.inspect_history(vault)
    assert current.status == "intact" and current.checkpoint.manifest.generation == 1
    assert current.admission.preflight.state_status == "supported"
    assert (
        current.admission.preflight.state_schema == "brz2obsidian.checkpoint-manifest"
    )
    assert (
        current.admission.preflight.state_fingerprint
        != before.admission.preflight.state_fingerprint
    )
    assert (vault / "Notes/Opening.md").read_bytes() == b"Exact authored bytes.\r\n"


def test_first_onboarding_checkpoint_keeps_recorded_generation_pending_transition():
    import hashlib

    from brz2obsidian.contracts import ContentVersion, SourceIdentity
    from brz2obsidian.core import resolve_review, resume_review
    from tests.reconciliation.test_resolution import action

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
    operations = Operations()
    before = operations.inspect_history(vault)
    facts = request(current=b"Exact authored bytes.\r\n")
    old = facts.baseline_identity.model_copy(update={"output_format": 6})
    facts = with_review_links(
        facts.model_copy(
            update={
                "baseline_identity": old,
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
    plan = prepare_review(facts, preflight=before.admission.preflight)
    kept = resolve_review(
        plan,
        action(
            plan, domain="format", choice="current", decision_id="keep-recorded-six"
        ),
    )
    assert kept.status == "accepted" and kept.plan.ready
    binding = operations.observe_reviewed_source(source, kept.plan)
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
        vault_id="new-vault",
        import_id="new-import",
        identity=old,
        admission=before.admission,
        review=kept.plan,
        source_binding=binding,
        observed_source=observed,
    )
    assert saved.status == "captured", saved
    stored = operations.read_checkpoint(vault)
    assert stored.status == "valid" and not stored.review.ready
    assert stored.manifest.identity.output_format == 6
    assert stored.manifest.reviewed_source.incoming_identity.output_format == 7
    assert stored.review.saved.plan.facts.subjects[0].baseline.status == "unknown"
    current = operations.inspect_history(vault)
    reopened = resume_review(
        stored.review, facts, preflight=current.admission.preflight
    )
    assert reopened.status == "resumed" and reopened.plan.ready
    assert [a.decision_id for a in reopened.plan.approvals] == ["keep-recorded-six"]
    loaded = operations.load_update(vault)
    assert (
        loaded.kind == "onboarding" and loaded.loaded is not None and not loaded.ready
    )
    ordinary = operations.prepare_update(vault, "unopened.brz")
    assert ordinary.code == "format_transition_required" and not ordinary.ready
    assert (vault / "Notes/Opening.md").read_bytes() == b"Exact authored bytes.\r\n"
