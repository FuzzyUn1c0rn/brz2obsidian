"""Explicit shared refresh rebinds a current producer without saving it."""

from uuid import uuid4

from brz2obsidian.application.checkpoint_contracts import CheckpointRead
from brz2obsidian.application.update_context import UpdateContext
from tests.application.test_onboarding_refresh import two_note_legacy_inputs
from tests.application.test_update_context import worker_context_call


def test_worker_refresh_reobserves_current_and_keeps_the_independent_decision(
    tmp_path, monkeypatch
):
    operations, vault, source, authored, second = two_note_legacy_inputs(
        tmp_path, monkeypatch
    )
    absent = CheckpointRead(
        schema_id="brz2obsidian.checkpoint-read",
        schema_version=1,
        status="absent",
        code="no_owned_checkpoint",
        locator=None,
        manifest=None,
        review=None,
        message="Controlled native absence.",
    )
    monkeypatch.setattr(operations, "read_checkpoint", lambda *args, **kwargs: absent)
    context = UpdateContext(operations=operations)
    opened = worker_context_call(
        context,
        {
            "command": "prepare",
            "kind": "onboarding",
            "vault": str(vault),
            "source": str(source),
            "selection_id": str(uuid4()),
        },
    )
    assert opened.kind == "onboarding" and opened.binding is not None
    binding = opened.binding
    decisions = {}
    for item in ("entry:opening", "entry:second"):
        page = worker_context_call(
            context, {"command": "page", "binding": binding, "byte_limit": 0}
        )
        change = next(row for row in page.page.items if row.item_id == item)
        offers = worker_context_call(
            context, {"command": "choices", "binding": binding}
        )
        offer = next(row for row in offers.offers if row.change_id == change.change_id)
        selected = worker_context_call(
            context,
            {
                "command": "choose",
                "binding": binding,
                "requirement_id": offer.requirement_id,
                "choice": "current",
                "assumptions_digest": offer.assumptions_digest,
            },
        )
        assert selected.code == "accepted"
        binding = selected.binding
        offers = worker_context_call(
            context, {"command": "choices", "binding": binding}
        )
        decisions[item] = next(
            row.decision_id
            for row in offers.offers
            if row.change_id == change.change_id
        )
        assert decisions[item] is not None
    later = authored + b"Later writing.\r\n"
    (vault / "Home \u2014 Opening.md").write_bytes(later)
    before = {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    }
    refreshed = worker_context_call(
        context, {"command": "refresh", "binding": binding, "source": None}
    )
    assert (
        refreshed.kind == "onboarding"
        and refreshed.status == "stale_review"
        and not refreshed.ready
    )
    assert (
        refreshed.binding.proposal_id == binding.proposal_id
        and refreshed.binding.generation == 2
    )
    assert refreshed.binding.revision > binding.revision
    assert (
        worker_context_call(context, {"command": "choices", "binding": binding}).code
        == "context_changed"
    )
    page = worker_context_call(
        context, {"command": "page", "binding": refreshed.binding}
    )
    offers = worker_context_call(
        context, {"command": "choices", "binding": refreshed.binding}
    )
    for item in ("entry:opening", "entry:second"):
        change = next(row for row in page.page.items if row.item_id == item)
        offer = next(row for row in offers.offers if row.change_id == change.change_id)
        if item == "entry:opening":
            assert (
                change.current == later
                and offer.selected is None
                and offer.decision_id is None
            )
        else:
            assert (
                change.current == second
                and offer.selected == "current"
                and offer.decision_id == decisions[item]
            )
    assert not refreshed.history_retained and refreshed.checkpoint_commit is None
    assert {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    } == before
