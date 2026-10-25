"""One explicit complete vault-wide configuration choice stays separate from format approval."""

import hashlib

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.source_payload_contracts import (
    ReviewedSourceBinding,
    SourcePayloadFile,
)
from brz2obsidian.application.update_contracts import UpdatePreparation
from brz2obsidian.contracts import ContentVersion, CurrentContent, ExactContent
from brz2obsidian.core import prepare_review, select_review_effects
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_identity import inventory_item, with_subjects
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, preflight, with_review_links

CONFIGURATION = {
    ".obsidian/app.json": (
        b'{"old":true}\n',
        b'{"user":"keep app"}\r\n',
        b'{"target":"app"}\n',
    ),
    ".obsidian/core-plugins.json": (
        b'["old"]\n',
        b'["user-plugin"]\r\n',
        b'["target-plugin"]\n',
    ),
}


def configuration_preparation():
    facts = request(
        original=b"Old presentation.\n",
        current=b"Local presentation.\r\n",
        incoming=b"Target presentation.\n",
    )
    subjects, inventory = [facts.subjects[0]], list(facts.identity_inventory)
    for path, (old, current, incoming) in CONFIGURATION.items():
        subject = facts.subjects[0].model_copy(
            update={
                "item_id": "support:" + path,
                "path": path,
                "title": path,
                "output_role": "configuration",
                "baseline": ContentVersion(
                    status="known",
                    content=ExactContent(data=old),
                    unavailable_digest=None,
                ),
                "current": CurrentContent(
                    existence="present", path=path, content=ExactContent(data=current)
                ),
                "incoming": ExactContent(data=incoming),
                "source_target": facts.subjects[0].source_target.model_copy(
                    update={"normalized_path": path.casefold()}
                ),
            }
        )
        subjects.append(subject)
        inventory.append(
            inventory_item(path, subject.item_id, path, current, title=path)
        )
    facts = with_subjects(facts, tuple(subjects), tuple(inventory))
    operation = facts.format_operation
    facts = with_review_links(
        facts.model_copy(
            update={
                "format_operation": operation.model_copy(
                    update={
                        "kind": "format_transition",
                        "target_source_version": operation.baseline_source_version,
                    }
                )
            }
        )
    )
    plan = prepare_review(facts, preflight=preflight())
    old = preparation()
    files = tuple(
        sorted(
            (
                SourcePayloadFile(
                    path=s.path,
                    mode="100644",
                    size=len(s.incoming.data),
                    sha256=hashlib.sha256(s.incoming.data).hexdigest(),
                )
                for s in facts.subjects
            ),
            key=lambda row: row.path,
        )
    )
    return UpdatePreparation.model_validate(
        old.model_dump()
        | {
            "kind": "format_transition",
            "review": plan,
            "source_binding": old.source_binding.model_copy(
                update={
                    "target_source_version": operation.baseline_source_version,
                    "files": files,
                    "fingerprint": ReviewedSourceBinding.digest(files),
                }
            ),
        }
    )


@pytest.mark.parametrize("choice", ("current", "incoming"))
def test_complete_vault_configuration_choice_survives_later_format_approval(choice):
    prepared = configuration_preparation()
    configs = [
        c
        for c in prepared.review.proposal.changes
        if c.format_review.configuration_choice
    ]
    assert len(configs) == 2 and all(c.format_review.target_eligible for c in configs)
    actions = tuple(
        action(
            prepared.review,
            c,
            domain="configuration",
            choice=choice,
            decision_id="explicit-config-" + str(i),
        )
        for i, c in enumerate(configs)
    )
    operations = Operations()
    chosen = operations.resolve_configuration(prepared, actions)
    assert chosen.code == "accepted", chosen
    assert len(chosen.preparation.review.approvals) == 2
    # A note/format approval is a separate request and cannot replace config decisions.
    note = next(
        c
        for c in chosen.preparation.review.proposal.changes
        if c.item_id == "entry:opening"
    )
    approved = operations.resolve_update(
        chosen.preparation,
        action(
            chosen.preparation.review,
            note,
            domain="format",
            choice="incoming",
            decision_id="explicit-format-note",
        ),
    )
    assert approved.code == "accepted" and approved.ready, approved
    selected = select_review_effects(approved.preparation.review)
    assert selected.status == "selected", selected
    expected = {"Notes/Opening.md": b"Target presentation.\n"} | {
        path: values[1 if choice == "current" else 2]
        for path, values in CONFIGURATION.items()
    }
    assert {row.path: row.content.data for row in selected.files} == expected
    assert all(
        a.domain == "configuration" and a.choice == choice
        for a in approved.preparation.review.approvals
        if a.decision_id.startswith("explicit-config-")
    )


def test_incomplete_configuration_group_records_no_partial_decision():
    prepared = configuration_preparation()
    config = next(
        c
        for c in prepared.review.proposal.changes
        if c.format_review.configuration_choice
    )
    requested = (
        action(prepared.review, config, domain="configuration", choice="current"),
    )
    result = Operations().resolve_configuration(prepared, requested)
    assert result.status == "refused" and not result.ready
    assert result.preparation.review == prepared.review
    assert not result.preparation.review.approvals
    assert result.history_retained and result.checkpoint == prepared.locator
    assert result.vault == prepared.vault and result.changes == result.unresolved == 3
