"""A LOCAL source baseline and pending incoming module release stay distinct."""

import hashlib

from brz2obsidian.application.operations import Operations
from brz2obsidian.contracts import SourceIdentity
from brz2obsidian.core import prepare_review, resolve_review, resume_review
from tests.application.test_vault_checkpoints import fixture_case, git
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, with_review_links


def test_local_review_retains_baseline_release_and_full_incoming_release():
    vault, source_a = fixture_case()
    source_b = vault.parent / "incoming-B"
    source_b.mkdir()
    for root, raw in (
        (vault, b"authored current\r\n"),
        (source_a, b"original\r\n"),
        (source_b, b"incoming\n"),
    ):
        (root / "Notes").mkdir()
        (root / "Notes/Opening.md").write_bytes(raw)
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    initial = request(current=b"authored current\r\n")
    baseline = initial.baseline_identity.model_copy(update={"module_version": "10"})
    incoming = initial.incoming_identity.model_copy(update={"module_version": "11"})
    operation = initial.format_operation.model_copy(
        update={
            "established_baseline": initial.format_operation.established_baseline.model_copy(
                update={"identity": baseline}
            )
        }
    )
    facts = with_review_links(
        initial.model_copy(
            update={
                "baseline_identity": baseline,
                "incoming_identity": incoming,
                "format_operation": operation,
            }
        )
    )
    operations = Operations()
    seeded = operations.capture_checkpoint(
        vault,
        source_a,
        vault_id="identity-vault",
        import_id="identity-import",
        identity=baseline,
        admission=operations.inspect_history(vault).admission,
    )
    assert seeded.status == "captured", seeded.code
    admission = operations.inspect_history(vault).admission
    offered = prepare_review(facts, preflight=admission.preflight)
    chosen = resolve_review(
        offered, action(offered, choice="current", decision_id="pending-B11")
    )
    assert chosen.status == "accepted" and chosen.plan.ready
    binding = operations.observe_reviewed_source(source_b, chosen.plan)
    observed = SourceIdentity(
        source_id=incoming.collection_id,
        module_id=incoming.module_id,
        module_version="11",
        format_version="5",
        source_sha256="c" * 64,
        snapshot_digest=facts.format_operation.target_source_version,
    )
    captured = operations.capture_checkpoint(
        vault,
        source_a,
        vault_id="identity-vault",
        import_id="identity-import",
        identity=baseline,
        admission=admission,
        review=chosen.plan,
        review_source=source_b,
        source_binding=binding,
        observed_source=observed,
    )
    assert captured.status == "captured", captured.code
    stored = operations.read_checkpoint(vault)
    assert stored.status == "valid" and not stored.review.ready
    assert stored.manifest.identity.module_version == "10"
    assert stored.manifest.reviewed_source.incoming_identity.module_version == "11"
    assert stored.manifest.observed_source.module_version == "11"
    assert (
        stored.manifest.source[0].sha256 == hashlib.sha256(b"original\r\n").hexdigest()
    )
    current = operations.inspect_history(vault)
    resumed = resume_review(stored.review, facts, preflight=current.admission.preflight)
    assert resumed.status == "resumed" and resumed.plan.ready, resumed.code
    assert resumed.plan.proposal.generation == 1
    assert [a.decision_id for a in resumed.plan.approvals] == ["pending-B11"]
    repeated = operations.capture_checkpoint(
        vault,
        source_a,
        vault_id="identity-vault",
        import_id="identity-import",
        identity=baseline,
        admission=current.admission,
        review=resumed.plan,
        review_source=source_b,
        source_binding=operations.observe_reviewed_source(source_b, resumed.plan),
        observed_source=observed,
    )
    assert repeated.status == "unchanged", repeated.code
    assert operations.read_checkpoint(vault).manifest.identity.module_version == "10"
