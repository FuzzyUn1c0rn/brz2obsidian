"""Finish preserves raw source evidence separately from reviewed edited output."""

import hashlib

from brz2obsidian.contracts import ExactContent
from brz2obsidian.core import prepare_review, resolve_review
from brz2obsidian.obsidian import inspect_text_candidate
from tests.application.test_vault_apply import _apply, _ready_case
from tests.application.test_vault_checkpoints import user_state
from tests.reconciliation.test_resolution import action


def test_finish_of_edited_output_retains_distinct_raw_incoming_source(monkeypatch):
    from brz2obsidian.publication.vault_history import _Git

    vault, source, operations, incoming, _ = _ready_case()
    facts = incoming.producer_facts
    offered = prepare_review(facts, preflight=incoming.preflight)
    selected_bytes = b"Reviewed selected C.\r\n"
    candidate = inspect_text_candidate(
        ExactContent(data=selected_bytes),
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
    edited = resolve_review(
        offered,
        action(offered, choice="edited", candidate=candidate, decision_id="edited-C"),
    )
    assert edited.status == "accepted" and edited.plan.ready
    original_call = _Git.call

    def reject_terminal_ref(self, *args, **kwargs):
        if (
            args[0] == "update-ref"
            and "/operations/" in args[1]
            and args[3] != "0" * 40
        ):
            raise OSError("Selected-result fixture stops before terminal receipt")
        return original_call(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(_Git, "call", reject_terminal_ref)
        stopped = _apply(
            operations,
            vault,
            source,
            review=edited.plan,
            vault_id="vault-one",
            import_id="import-one",
        )
    assert stopped.status == "content_complete" and stopped.recovery_required
    assert (vault / "Notes/Opening.md").read_bytes() == selected_bytes
    assert (source / "Notes/Opening.md").read_bytes() == b"incoming opening\n"
    before = user_state(vault)
    prepared = operations.prepare_recovery(vault, direction="finish")
    assert prepared.status == "offered" and not prepared.review.blockers
    current = operations.resolve_recovery(
        vault,
        prepared,
        action(prepared.review, choice="current", decision_id="finish-selected-C"),
    )
    assert current.status == "offered" and current.review.ready
    finished = operations.execute_recovery(vault, current)
    assert finished.status == "applied" and not finished.recovery_required, (
        finished.code
    )
    assert (vault / "Notes/Opening.md").read_bytes() == selected_bytes
    after = user_state(vault)
    for key in ("head", "index", "config", "stages"):
        assert after[key] == before[key]
    assert tuple(
        r for r in after["refs"] if not r.startswith(b"refs/brz2obsidian/")
    ) == (tuple(r for r in before["refs"] if not r.startswith(b"refs/brz2obsidian/")))
    checkpoint = operations.read_checkpoint(vault)
    assert checkpoint.status == "valid"
    assert (
        checkpoint.manifest.source[0].sha256
        == hashlib.sha256(b"incoming opening\n").hexdigest()
    )
    selected = next(
        r for r in checkpoint.manifest.vault if r.path == "Notes/Opening.md"
    )
    assert selected.sha256 == hashlib.sha256(selected_bytes).hexdigest()
    restarted = operations.inspect_update_status(vault)
    assert (
        restarted.status == "applied"
        and restarted.receipt_commit == finished.receipt_commit
    )
