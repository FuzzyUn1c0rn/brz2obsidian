"""Adopting future history is meaningful even when current files are retained."""

from types import SimpleNamespace

import pytest

from brz2obsidian.application.checkpoint_contracts import (
    CheckpointLocator,
    VaultAssociation,
)
from tests.application.test_onboarding import legacy_inputs
from tests.application.test_update_lifecycle_admission import refused_publication
from tests.reconciliation.test_resolution import action


@pytest.mark.parametrize("saved", (False, True))
def test_current_only_onboarding_requires_first_history_and_real_completion(
    tmp_path, monkeypatch, saved
):
    operations, vault, source, _ = legacy_inputs(tmp_path, monkeypatch)
    offered = operations.prepare_onboarding(vault, source)
    prepared = offered.preparation
    assert prepared is not None, offered
    initial = prepared.review
    while prepared.review.requirements:
        requirement = prepared.review.requirements[0]
        change = next(
            c
            for c in prepared.review.proposal.changes
            if c.change_id == requirement.change_id
        )
        chosen = operations.resolve_update(
            prepared,
            action(
                prepared.review,
                change,
                domain=requirement.domain,
                choice="current",
                decision_id="keep-" + change.item_id,
            ),
        )
        assert chosen.code == "accepted", chosen
        prepared = chosen.preparation
    assert prepared.review.ready
    identity = prepared.review.facts.incoming_identity
    locator = CheckpointLocator(
        schema_id="brz2obsidian.checkpoint-locator",
        schema_version=1,
        generation=1,
        commit="b" * 40,
        association=VaultAssociation(
            schema_id="brz2obsidian.vault-association",
            schema_version=1,
            association_id="a" * 64,
            vault_id="new-vault",
            import_id="new-import",
            collection_id=identity.collection_id,
            module_id=identity.module_id,
            vault_anchor="actual-vault-observation",
            git_anchor="actual-git-observation",
            ref="refs/brz2obsidian/imports/" + "a" * 64 + "/checkpoints",
        ),
    )
    history = operations.inspect_history(vault)
    if saved:
        history.status = "intact"
        history.checkpoint = SimpleNamespace(
            status="valid",
            locator=locator,
            manifest=SimpleNamespace(
                boundary="local",
                identity=identity,
                source=prepared.source_binding.files,
                vault=history.admission.inventory,
            ),
            review=SimpleNamespace(saved=SimpleNamespace(plan=initial)),
        )
        prepared = prepared.model_copy(update={"locator": locator})
    monkeypatch.setattr(
        operations,
        "apply_reviewed_update",
        lambda *args, **kwargs: refused_publication(),
    )
    result = operations.apply_update(prepared)
    assert result.kind == "onboarding"
    if saved:
        assert (
            result.status == "refused" and result.code == "publication_boundary_reached"
        ), result
        assert result.application is not None
        assert result.history_retained
    else:
        assert result.code == "first_checkpoint_required", result
        assert not result.ready and result.next_actions == ("save_update",)
        assert not result.history_retained and result.checkpoint is None


@pytest.mark.parametrize("operation", ("resolve", "refresh", "save", "apply"))
def test_onboarding_failure_keeps_role(monkeypatch, operation):
    from brz2obsidian.application.operations import Operations
    from brz2obsidian.application.update_contracts import UpdatePreparation
    from brz2obsidian.core import prepare_review
    from tests.application.test_update_lifecycle_contracts import preparation

    old = preparation()
    facts = old.review.facts.model_copy(
        update={
            "format_operation": old.review.facts.format_operation.model_copy(
                update={"kind": "onboarding"}
            ),
        }
    )
    prepared = UpdatePreparation.model_validate(
        old.model_dump()
        | {
            "kind": "onboarding",
            "review": prepare_review(facts, preflight=old.review.preflight),
        }
    )
    operations = Operations()

    def unavailable(*args, **kwargs):
        raise OSError("Current inspection is unavailable")

    monkeypatch.setattr(operations, "inspect_history", unavailable)
    monkeypatch.setattr(operations, "inspect_update_inputs", unavailable)
    if operation == "resolve":
        result = operations.resolve_update(prepared, None)
    elif operation == "refresh":
        result = operations.refresh_update(prepared, source="unopened.brz")
    elif operation == "save":
        result = operations.save_update(prepared)
    else:
        result = operations.apply_update(prepared)
    assert result.kind == "onboarding", result
    assert result.status == "refused" and not result.ready
    assert result.preparation is None and result.publication == "not_started"
